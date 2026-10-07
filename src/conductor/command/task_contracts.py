"""The task: the durable record that stands between a project and its runs.

Project -> Task -> Run. A task is a first-class record with its own identity
and its own WORK CONTEXT: ``work_scope``, the namespace every work item the
task's runs dispatch is filed under. A display title may change one day; a
scope may not, which is why the scope is recorded explicitly even though it
equals the task id at creation.

A run binds to a task by a validated, immutable field inside its frozen
configuration snapshot -- ``{"task": {"id", "work_scope"}}`` -- so the binding
is covered by ``config_digest`` exactly as the workflow reference is, and it is
read back by the same kind of strict reader: absent is a real answer (a run
opened with no task is task-less, and nothing here derives a task from
``cycle_id``), and a malformed key is CORRUPT, never legacy. Which runs belong
to a task is derived from those bindings at projection time; the record keeps
no run list, mutable or otherwise.

Like ``contracts`` this module has no filesystem, subprocess, server or adapter
imports: a task's rules must be checkable without anything being able to run.
The store next door writes only what this module admits.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contract_values import ABSENT, ContractError, _id, _timestamp

#: Held EXACTLY, the way a stored draft envelope is (``DRAFT_SCHEMA_VERSION``)
#: rather than ``>= 2`` the way a run envelope is: the record is closed at every
#: key, so it cannot honestly read a version of itself it has never seen.
TASK_SCHEMA_VERSION = 1
#: A task id and a work scope are bounded well inside the 128-character id
#: grammar: the scope is a directory name under ``work/_tasks`` and one
#: path component should not be allowed to spend a platform's path budget.
MAX_TASK_ID = 64
MAX_TASK_TITLE = 200
#: The stored record's own shape, closed. `as_dict` spells them in this order.
_RECORD_FIELDS = frozenset({
    "schema_version", "task_id", "title", "work_scope", "created_at"})
#: The keys a frozen ``task`` binding carries. Both are required: an id without
#: its scope would leave a reader to guess the namespace, which is the one
#: thing the binding exists to stop.
_TASK_FIELDS = frozenset({"id", "work_scope"})
#: C0 controls and DEL: a title is one line of text a person can see.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _bounded_id(name: str, value: object) -> str:
    """An id of the contract's grammar, no longer than `MAX_TASK_ID`."""
    safe = _id(name, value)
    if len(safe) > MAX_TASK_ID:
        raise ContractError(
            f"{name} must be at most {MAX_TASK_ID} characters, got {len(safe)}")
    return safe


def _title(value: object) -> str:
    """A display title: text, bounded, one visible line; stored exactly as given."""
    if not isinstance(value, str):
        raise ContractError(f"title must be a string, got {value!r}")
    if not value.strip():
        raise ContractError("title must not be empty or whitespace")
    if len(value) > MAX_TASK_TITLE:
        raise ContractError(
            f"title must be at most {MAX_TASK_TITLE} characters, got {len(value)}")
    if _CONTROL_RE.search(value) is not None:
        raise ContractError("title must not contain control characters")
    return value


def _version(value: object) -> int:
    if type(value) is not int or value != TASK_SCHEMA_VERSION:
        raise ContractError(
            f"this build speaks task schema_version {TASK_SCHEMA_VERSION} and "
            f"this record claims {value!r}")
    return value


@dataclass(frozen=True)
class TaskRecord:
    """One stored task: its identity, its title, its work scope, and when it began."""

    task_id: str
    title: str
    work_scope: str
    created_at: str
    schema_version: int = TASK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _bounded_id("task_id", self.task_id))
        object.__setattr__(self, "title", _title(self.title))
        object.__setattr__(
            self, "work_scope", _bounded_id("work_scope", self.work_scope))
        object.__setattr__(
            self, "created_at", _timestamp("created_at", self.created_at))
        object.__setattr__(self, "schema_version", _version(self.schema_version))

    def as_dict(self) -> dict[str, Any]:
        """The stored shape, self-describing, keys in the one fixed order."""
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "title": self.title,
            "work_scope": self.work_scope,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "TaskRecord":
        """Admit one stored record: closed at every key, exact at the version.

        Args:
            value: The document as read back from ``task.json``.

        Returns:
            The record the document describes.

        Raises:
            ContractError: The document is not an object, carries a key this
                record does not, lacks one it must, or claims a schema version
                this build does not speak.
        """
        if not isinstance(value, Mapping):
            raise ContractError(f"task record must be a JSON object, got {value!r}")
        if any(not isinstance(key, str) for key in value):
            raise ContractError("task record keys must be strings")
        supplied = set(value)
        if supplied != _RECORD_FIELDS:
            raise ContractError(
                f"a task record carries exactly {sorted(_RECORD_FIELDS)!r}, "
                f"got {sorted(supplied)!r}")
        return cls(
            task_id=value["task_id"], title=value["title"],
            work_scope=value["work_scope"], created_at=value["created_at"],
            schema_version=value["schema_version"])


@dataclass(frozen=True)
class TaskBinding:
    """What a run freezes about its task: the identity and the work scope."""

    task_id: str
    work_scope: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _bounded_id("task_id", self.task_id))
        object.__setattr__(
            self, "work_scope", _bounded_id("work_scope", self.work_scope))


def frozen_config_task(config: Mapping[str, Any]) -> TaskBinding | None:
    """Read WHICH task this run froze itself to belong to.

    Mirrors `frozen_config_workflow` exactly, and for its reason. The key is
    optional and absence is a real answer: a run opened with no task belongs to
    none, and ``None`` says exactly that. What it must never do is guess --
    not from ``cycle_id``, not from a half-written key. A binding that is
    present and malformed is refused as strictly as an id is refused anywhere
    else, because a wrong task is worse than no task.

    Args:
        config: The frozen configuration snapshot, as replayed from a run.

    Returns:
        The binding this run froze, or ``None`` when it froze none.

    Raises:
        ContractError: The snapshot is not an object, or the binding is not an
            object, carries keys other than exactly ``id`` and ``work_scope``,
            or names an id the task contract refuses.
    """
    if not isinstance(config, Mapping):
        raise ContractError("frozen config must be a JSON object")
    reference = config.get("task", ABSENT)
    if reference is ABSENT:
        return None
    if not isinstance(reference, Mapping):
        raise ContractError("frozen config task must be a JSON object")
    supplied = set(reference)
    if supplied != _TASK_FIELDS:
        raise ContractError(
            f"frozen config task carries {sorted(supplied)!r} and must carry "
            f"exactly {sorted(_TASK_FIELDS)!r}")
    return TaskBinding(
        task_id=_bounded_id("frozen config task id", reference["id"]),
        work_scope=_bounded_id("frozen config task work_scope", reference["work_scope"]))


def work_scope_disagreement(arguments: Mapping[str, Any],
                            task: TaskBinding | None) -> str | None:
    """Why these arguments may not write where they would, or None when they may.

    ONE rule, spent at every door that lets work be given to a run: the plan doors
    (`plan_admission.work_scope_admits`), the proposal door
    (`service._hold_proposal_writes_in_its_task`) and the authority to execute
    (`authorize_holds._hold_work_scope`). Arguments that carry a work item write
    into ``work/_tasks/<work_scope>/<item>``, or into ``work/<item>`` with no
    scope. So a run bound to no task may name no scope, and a run bound to a task
    may name exactly its own -- naming none would file its work among task-less
    history. The scope is judged as the CALLER wrote it: never inferred from a
    directory and never filled in, because a scope this build supplied after the
    preview would be work nobody confirmed.

    Args:
        arguments: A step's or a proposal's capability arguments.
        task: The task the run froze, or ``None`` when it froze none.

    Returns:
        The refusal's words, or ``None`` when the arguments carry no work item
        or name exactly the run's own scope.
    """
    if "work_item_id" not in arguments:
        return None
    said = arguments.get("work_scope")
    bound = None if task is None else task.work_scope
    if said == bound:
        return None
    return f"files its work under task scope {said!r} and this run is bound to {bound!r}"
