"""The three task routes, and the one question a run open asks of them.

Project -> Task -> Run, spoken on the wire. ``create_task`` is idempotent under
a lost reply the way opening a run is: the standing record is looked for FIRST,
under the same transaction the write takes, and the same request again answers
it and writes nothing while a different request under one id is a
``RecordConflict``. ``list_tasks`` reads the directory and lists a corrupt
record rather than hiding it. ``read_task`` answers one record and the runs
bound to it -- DERIVED at projection time from each run's frozen ``task``
binding, because the record keeps no run list that could come to disagree with
the runs. ``resolve_task_binding`` is what ``open_run`` asks before it freezes a
snapshot: the id a browser named must be a task this store holds, and what is
frozen is the record's own scope, never the caller's word for it.

Split from ``studio_routes`` for its line cap, along the noun. The seam is the
same ``(status, payload)`` pair, for the same reason: the boundary owns the
response type, and nothing here knows how one is shaped on the wire. The two
modules import each other by MODULE and not by name -- `open_run` needs the
binding resolved here, `read_task` needs the run listing kept there -- so
neither import order asks a half-initialized module for a name it has not
bound yet.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from . import studio_routes
from .api_contracts import ApiRefusal
from .containment import run_route_violations
from .contracts import ContractError
from .store_errors import RecordConflict, StoreError
from .studio_contracts import parse_task
from .task_contracts import TaskBinding, TaskRecord, frozen_config_task
from .task_store import CorruptTask
from .template_store import RouteNotOwned

if TYPE_CHECKING:  # pragma: no cover - collaborators, never constructed here
    from .run_store import RunStore
    from .task_store import TaskStore

Answer = tuple[int, dict[str, Any]]

#: A listed task that cannot be read: every stored field null and the word that
#: says so -- the run row's convention, so a reader of the two lists needs one
#: rule for "present and unreadable".
_UNREADABLE_TASK = {
    "schema_version": None, "task_id": None, "title": None,
    "work_scope": None, "created_at": None}


def create_task(
        tasks: "TaskStore", body: object, *, clock: Callable[[], str]) -> Answer:
    """Create one task, or agree it is already created.

    The standing record is looked for FIRST, before the clock is read, and
    under the SAME transaction the create takes: the read decides whether the
    write may happen, and a create landing between the two is what the store's
    exclusive rename then refuses. The comparison is the whole record rebuilt on
    the standing ``created_at`` -- the caller never supplied one, so comparing
    anything else would call every honest retry a conflict.

    Args:
        tasks: This project's task store.
        body: The request body, judged by `parse_task`.
        clock: The server's clock, read only for a task about to be written.

    Returns:
        ``201`` with the record when this call created it, ``200`` with the
        standing record when an identical request already had.

    Raises:
        RecordConflict: A different request already stands under this id.
        CorruptTask: The directory under this id holds no readable record.
    """
    asked = parse_task(body)
    with tasks.transaction():
        if not tasks.task_path(asked.task_id).is_dir():
            tasks.admit_task_creation(asked.task_id)
        standing = tasks.standing(asked.task_id)
        if standing is not None:
            if standing.as_dict() != asked.build(standing.created_at).as_dict():
                raise RecordConflict(
                    f"task {asked.task_id!r} already records different facts")
            return 200, {"task": standing.as_dict()}
        record = asked.build(clock())
        tasks.create_task(record)
    return 201, {"task": record.as_dict()}


def list_tasks(tasks: "TaskStore") -> Answer:
    """Every task this project holds, in the store's own order, and nothing else.

    A directory whose record does not read is LISTED, with ``unreadable`` true
    and every stored field null -- the run row's convention, because a task you
    cannot see is worse than one you cannot read. A record the store refuses to
    reach, because its route holds bytes the store cannot account for, is the
    same row: the refusal is about that entry, and its neighbours are still
    there to be seen. A readable row carries the record and ``unreadable``
    false, so every row has the one shape.
    """
    return 200, {"tasks": [_task_row(tasks, task_id) for task_id in tasks.tasks()]}


def _task_row(tasks: "TaskStore", task_id: str) -> dict[str, Any]:
    try:
        record = tasks.read(task_id)
    except (CorruptTask, RouteNotOwned):
        return {**_UNREADABLE_TASK, "task_id": task_id, "unreadable": True}
    return {**record.as_dict(), "unreadable": False}


def read_task(tasks: "TaskStore", store: "RunStore", task_id: str) -> Answer:
    """One task, and the runs bound to it -- derived, never stored.

    The record keeps no run list. Which runs belong to it is read off each
    run's own frozen ``task`` binding, so the answer cannot disagree with the
    runs. A run that does not replay, or whose binding is corrupt, is skipped
    from THIS list and hidden nowhere: the run list still shows it unreadable.

    Raises:
        ApiRefusal: ``service_refused``, naming the id, when no task stands.
        CorruptTask: The directory under this id holds no readable record.
    """
    record = _stored(tasks, task_id)
    return 200, {"task": record.as_dict(), "runs": _bound_runs(store, task_id)}


def _bound_runs(store: "RunStore", task_id: str) -> list[str]:
    """Every run whose frozen binding names this task, ascending by id."""
    found = []
    for run_id in studio_routes.run_ids(store):
        if run_route_violations(store, run_id):
            continue
        try:
            binding = frozen_config_task(store.read(run_id).config)
        except (StoreError, ContractError):
            continue
        if binding is not None and binding.task_id == task_id:
            found.append(run_id)
    return sorted(found)


def resolve_task_binding(
        tasks: "TaskStore", task_id: str | None) -> TaskBinding | None:
    """The binding a run freezes for the task it named, or ``None`` for none.

    Read off the RECORD, so what a run freezes is the task's own scope and
    never a scope the caller spelled. A name this store holds no task under is
    refused by the id the caller sent and by nothing else.

    Raises:
        ApiRefusal: ``service_refused``, naming the id, when no task stands.
        CorruptTask: The directory under this id holds no readable record.
    """
    if task_id is None:
        return None
    record = _stored(tasks, task_id)
    return TaskBinding(task_id=record.task_id, work_scope=record.work_scope)


def _stored(tasks: "TaskStore", task_id: str) -> TaskRecord:
    record = tasks.standing(task_id)
    if record is None:
        raise ApiRefusal.missing_task(task_id)
    return record
