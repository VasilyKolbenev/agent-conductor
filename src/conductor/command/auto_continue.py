"""The continue-after flag: one file, one door, and the one conditional write (spec 4.3.4).

`<data_root>/auto-continue.json` records what the owner of a project decided while looking at
its desk: when this project is next made active, resume these runs and start the task queue.
It is a human's advance permission, like a queued task's (4.4.2), and it is written by the
child of the project the hub cannot write into (4.5), so the door lives here.

The record (schema 2) is `flag_id` (a new uuid for every flag that is switched on), `revision`
(grows with every write of the file), `enabled`, `actor`, `set_at`, `resume_runs`,
`start_task_queue` and `consumed`. Each run in `resume_runs` carries what the owner was looking
at when he decided: the grant (`authorization_id`, `authorization_digest`) and the last control
of that grant (`last_control_id`, `None` when there was none). The server reads those from the
run journal, in the same root-gate transaction that writes the file; the client never names them.

The door (`read_flag`, `set_flag`) answers the same in every mode of the server: it reads no
driver, no policy and no mode. This module never RUNS a flag either: the queue pump of lane L
does, and only through `consume`, which rewrites the file (`enabled: false`, `consumed` with the
transition and the activation nonce of the child that consumed it, `revision + 1`) only if it
still holds the `flag_id` and `revision` the hub handed that child, still enabled and not
consumed. A flag taken down or replaced after the hub read it is not run, and a newer flag of
the owner is never overwritten: it waits for the next activation. A consumed record keeps its
`resume_runs` and `start_task_queue` because the queue admits its pre-authorizations only in a
child that consumed a flag with `start_task_queue` true (4.3.4).
"""
from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from ..ownership import data_root, owned_write
from .api_refusals import ApiRefusal
from .authorization_terms import _time_parts, human_identity
from .containment import first_directory_violation
from .contract_values import ContractError, _digest, _id, _timestamp
from .contracts import ActionRequest, ActionResultReceipt
from .graph_schedule import schedule
from .policy_history import current_authorization, current_control
from .run_files import _canonical_bytes, _fsync_dir, _json_object, _replace_bytes
from .run_store import _ROOT_TRANSACTION_STATE, RunStore, _root_gate
from .run_terminal import RunTerminal
from .store_errors import CorruptRun, StoreError
from .template_store import RouteNotOwned, _leaf_violation

#: The one file this store holds, beside `tasks`, `runs`, `templates` and the pinned cycle.
FLAG_FILE = "auto-continue.json"
SCHEMA_VERSION = 2
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_BODY = frozenset({"enabled", "actor", "resume_runs", "start_task_queue"})
_FIELDS = ("schema_version", "flag_id", "revision", "enabled", "actor", "set_at",
           "resume_runs", "start_task_queue", "consumed")


class CorruptFlag(StoreError):
    """The flag file is not a record of this contract; no path is named."""


def _closed(value: object, keys: tuple[str, ...], what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ContractError(f"{what} carries exactly {list(keys)!r}")
    return value


def _uuid(name: str, value: object) -> str:
    if not isinstance(value, str) or _UUID.fullmatch(value) is None:
        raise ContractError(f"{name} must be a lower-case uuid")
    return value


@dataclass(frozen=True)
class ResumeRun:
    """A run the owner let the flag resume, bound to the grant and control he was looking at."""

    run_id: str
    authorization_id: str
    authorization_digest: str
    last_control_id: str | None

    _KEYS = ("run_id", "authorization_id", "authorization_digest", "last_control_id")

    def __post_init__(self) -> None:
        _id("run_id", self.run_id)
        _id("authorization_id", self.authorization_id)
        _digest("authorization_digest", self.authorization_digest)
        if self.last_control_id is not None:
            _id("last_control_id", self.last_control_id)

    def as_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self._KEYS}

    @classmethod
    def from_dict(cls, value: object) -> "ResumeRun":
        return cls(**_closed(value, cls._KEYS, "a resume run"))


@dataclass(frozen=True)
class Consumed:
    """Which child consumed the flag, and when: the transition it was started by and its nonce."""

    at: str
    transition_id: str
    activation_nonce: str

    _KEYS = ("at", "transition_id", "activation_nonce")

    def __post_init__(self) -> None:
        _timestamp("at", self.at)
        _uuid("transition_id", self.transition_id)
        if not isinstance(self.activation_nonce, str) or not _NONCE.fullmatch(
                self.activation_nonce):
            raise ContractError("activation_nonce must be 32 lower-case hex characters")

    def as_dict(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in self._KEYS}

    @classmethod
    def from_dict(cls, value: object) -> "Consumed":
        return cls(**_closed(value, cls._KEYS, "a consumption"))


@dataclass(frozen=True)
class FlagRecord:
    """The flag as stored and as `GET` shows it: the fields are the same."""

    flag_id: str
    revision: int
    enabled: bool
    actor: str
    set_at: str
    resume_runs: tuple[ResumeRun, ...]
    start_task_queue: bool
    consumed: Consumed | None

    def __post_init__(self) -> None:
        _uuid("flag_id", self.flag_id)
        if type(self.revision) is not int or self.revision < 1:
            raise ContractError("revision must be a positive integer")
        if type(self.enabled) is not bool or type(self.start_task_queue) is not bool:
            raise ContractError("enabled and start_task_queue must be booleans")
        human_identity("actor", self.actor)
        _timestamp("set_at", self.set_at)
        runs = tuple(self.resume_runs)
        object.__setattr__(self, "resume_runs", runs)
        if len({run.run_id for run in runs}) != len(runs):
            raise ContractError("resume_runs must not repeat a run")
        if self.consumed is not None and self.enabled:
            raise ContractError("a consumed flag is not enabled")
        if not self.enabled and self.consumed is None and (runs or self.start_task_queue):
            raise ContractError("a flag that is off carries no runs and no queue start")

    def as_dict(self) -> dict[str, Any]:
        """The stored shape, self-describing, keys in the one fixed order."""
        return {"schema_version": SCHEMA_VERSION, "flag_id": self.flag_id,
                "revision": self.revision, "enabled": self.enabled, "actor": self.actor,
                "set_at": self.set_at, "resume_runs": [run.as_dict() for run in self.resume_runs],
                "start_task_queue": self.start_task_queue,
                "consumed": None if self.consumed is None else self.consumed.as_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "FlagRecord":
        """Admit one stored record: closed at every key, exact at the version.

        Raises:
            ContractError: Not an object, a key too many or too few, another schema version,
                or a value or a combination of values the record refuses.
        """
        data = _closed(value, _FIELDS, "a flag record")
        if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
            raise ContractError("a flag record speaks schema version 2")
        if not isinstance(data["resume_runs"], list):
            raise ContractError("resume_runs must be a list")
        consumed = data["consumed"]
        return cls(data["flag_id"], data["revision"], data["enabled"], data["actor"],
                   data["set_at"], tuple(ResumeRun.from_dict(run) for run in data["resume_runs"]),
                   data["start_task_queue"], None if consumed is None
                   else Consumed.from_dict(consumed))


def absent_form() -> dict[str, Any]:
    """What `GET` answers when the file is absent: the record's fields, off and empty."""
    return {"schema_version": SCHEMA_VERSION, "flag_id": None, "revision": 0, "enabled": False,
            "actor": None, "set_at": None, "resume_runs": [], "start_task_queue": False,
            "consumed": None}


class AutoContinueStore:
    """The flag file of one project, read and written under the project's root gate."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        # The gate every store of this root shares, held strongly: the module table is weak.
        self._root_gate = _root_gate(self.project_root)

    @property
    def path(self) -> Path:
        """Where the flag lives now: the data root can move when the project is activated."""
        return data_root(self.project_root) / FLAG_FILE

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """One process-local transaction for this root, the depth `RunStore` keeps included."""
        with self._root_gate.lock:
            depth = getattr(_ROOT_TRANSACTION_STATE, "depth", 0)
            _ROOT_TRANSACTION_STATE.depth = depth + 1
            try:
                yield
            finally:
                _ROOT_TRANSACTION_STATE.depth = depth

    def _owned(self) -> Path:
        path = self.path
        if first_directory_violation((path.parent,)) or _leaf_violation(path) is not None:
            raise RouteNotOwned("the route of the continue-after flag is not this store's")
        return path

    def read(self) -> FlagRecord | None:
        """The standing record, or `None` when the file is absent.

        Raises:
            CorruptFlag: The file is unreadable or is not a record of this contract.
            RouteNotOwned: The route reaches state this store cannot account for.
        """
        with self.transaction():
            path = self._owned()
            if not path.exists():
                return None
            try:
                document = _json_object(path, FLAG_FILE)
            except CorruptRun:
                raise CorruptFlag("the continue-after flag is unreadable") from None
            try:
                return FlagRecord.from_dict(document)
            except ContractError:
                raise CorruptFlag("the continue-after flag violates its contract") from None

    @owned_write
    def write(self, record: FlagRecord) -> None:
        """Replace the flag file with this record, all or nothing.

        Raises:
            RouteNotOwned: The route reaches state this store cannot account for.
            StoreError: The owner's guard refuses, or the bytes could not be written.
        """
        if type(record) is not FlagRecord:
            raise StoreError("write takes exactly a FlagRecord")
        with self.transaction():
            path = self._owned()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._owned()
            try:
                _replace_bytes(path, _canonical_bytes(record.as_dict()))
                _fsync_dir(path.parent)
            except OSError as error:
                raise StoreError(f"cannot write the continue-after flag: {error}") from error


# --- the body ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Asked:
    """One `POST`, judged for shape."""

    enabled: bool
    actor: str
    run_ids: tuple[str, ...]
    start_task_queue: bool


def _contract(check: Callable[..., Any], *arguments: Any) -> Any:
    try:
        return check(*arguments)
    except ContractError:
        raise ApiRefusal.fixed("contract_invalid") from None


def parse_body(body: object) -> Asked:
    """A closed body; a flag that is off names no run and no queue start."""
    if not isinstance(body, Mapping) or set(body) != _BODY:
        raise ApiRefusal.fixed("contract_invalid")
    enabled, queue, runs = body["enabled"], body["start_task_queue"], body["resume_runs"]
    if type(enabled) is not bool or type(queue) is not bool or not isinstance(runs, list):
        raise ApiRefusal.fixed("contract_invalid")
    actor = _contract(human_identity, "actor", body["actor"])
    run_ids = tuple(_contract(_id, "run_id", run) for run in runs)
    if len(set(run_ids)) != len(run_ids) or (not enabled and (run_ids or queue)):
        raise ApiRefusal.fixed("contract_invalid")
    return Asked(enabled, actor, run_ids, queue)


# --- the binding -------------------------------------------------------------------------------


def _open_action(values: tuple[Any, ...]) -> bool:
    answered = {v.action_id for v in values if type(v) is ActionResultReceipt}
    return any(type(v) is ActionRequest and v.action_id not in answered for v in values)


def _ended(recovered: Any, values: tuple[Any, ...]) -> bool:
    if any(type(v) is RunTerminal for v in values):
        return True
    definition = next((row.value for row in recovered.records if row.kind == "graph_definition"),
                      None)
    return definition is not None and schedule(definition, values).run_state == "complete"


def _standing(grant: Any, control: Any, now: str) -> bool:
    if control is not None and control.action == "revoke":
        return False
    return _time_parts("now", now) < _time_parts("expires_at", grant.expires_at)


def bind_run(runs: RunStore, run_id: str, now: str) -> ResumeRun:
    """The grant and last control this run stands on at `now`, or the refusal that names it.

    A flag can carry on a run only while a grant stands (not expired, not revoked, the plan not
    complete, no terminal recorded) and no action is open. A run this project does not hold is
    refused the same way: the caller learns which id, and nothing about why.

    Raises:
        ApiRefusal: `contract_invalid` with `detail.run_id`.
    """
    if not runs.run_path(run_id).is_dir():
        raise ApiRefusal.run_cannot_continue(run_id)
    recovered = runs.read(run_id)
    values = tuple(row.value for row in recovered.records)
    grant = current_authorization(values)
    control = None if grant is None else current_control(values, grant)
    if (grant is None or _ended(recovered, values) or _open_action(values)
            or not _standing(grant, control, now)):
        raise ApiRefusal.run_cannot_continue(run_id)
    return ResumeRun(run_id, grant.authorization_id, grant.authorization_digest,
                     None if control is None else control.control_id)


# --- the door ----------------------------------------------------------------------------------


def read_flag(store: AutoContinueStore) -> tuple[int, dict[str, Any]]:
    """`GET /command/project/auto-continue`: the standing record, or the form of no flag."""
    record = store.read()
    return 200, absent_form() if record is None else record.as_dict()


def _new_flag_id() -> str:
    return str(uuid.uuid4())


def set_flag(store: AutoContinueStore, runs: RunStore, body: object, clock: Callable[[], str],
             new_flag_id: Callable[[], str] = _new_flag_id) -> tuple[int, dict[str, Any]]:
    """`POST /command/project/auto-continue`: switch a flag on, or take the standing one down.

    Every flag switched on is a new flag: a new `flag_id`, `consumed` null, `revision` one more
    than the file held. Taking one down keeps its `flag_id`, empties the lists and bumps the
    revision; taking down a flag that is not on writes nothing. The runs are bound and the file
    is written in one root-gate transaction, so what is stored is what the journal said.

    Raises:
        ApiRefusal: `contract_invalid` for a body that is not the closed shape, or, with
            `detail.run_id`, for a run the flag cannot carry on.
    """
    asked = parse_body(body)
    with store.transaction():
        standing = store.read()
        if not asked.enabled:
            return 200, _take_down(store, standing, asked, clock)
        now = clock()
        bound = tuple(bind_run(runs, run_id, now) for run_id in asked.run_ids)
        record = FlagRecord(new_flag_id(), 1 if standing is None else standing.revision + 1,
                            True, asked.actor, now, bound, asked.start_task_queue, None)
        store.write(record)
    return 200, record.as_dict()


def _take_down(store: AutoContinueStore, standing: FlagRecord | None, asked: Asked,
               clock: Callable[[], str]) -> dict[str, Any]:
    if standing is None:
        return absent_form()
    if not standing.enabled:
        return standing.as_dict()
    record = FlagRecord(standing.flag_id, standing.revision + 1, False, asked.actor, clock(),
                        (), False, None)
    store.write(record)
    return record.as_dict()


def consume(store: AutoContinueStore, *, expected_flag_id: str, expected_revision: int,
            transition_id: str, activation_nonce: str,
            clock: Callable[[], str]) -> FlagRecord | None:
    """Consume the flag a hub handed a child, only if it is still the one standing.

    Args:
        store: The project's flag file.
        expected_flag_id: The `flag_id` of `--auto-continue <flag_id>@<revision>`.
        expected_revision: Its `revision`.
        transition_id: The child's `--transition`.
        activation_nonce: The child's project id, the activation nonce it holds.
        clock: The server clock, for `consumed.at`.

    Returns:
        The record written (disabled, `consumed` set, `resume_runs` and `start_task_queue` as
        they were: what the pump executes), or `None` when the flag is not consumed: absent,
        another `flag_id`, another `revision`, or off (taken down, or already consumed).
        Nothing is written then.

    Raises:
        ContractError: `transition_id` or `activation_nonce` is not the shape of one, and the
            flag would have been consumed.
        CorruptFlag: The file is not a record of this contract.
    """
    with store.transaction():
        standing = store.read()
        # `enabled` also says "not consumed yet": a consumed record is never on (`FlagRecord`).
        if (standing is None or standing.flag_id != expected_flag_id
                or standing.revision != expected_revision or not standing.enabled):
            return None
        record = replace(standing, revision=standing.revision + 1, enabled=False,
                         consumed=Consumed(clock(), transition_id, activation_nonce))
        store.write(record)
        return record
