"""`hub-state.json`: who is active, who waits, who is still closing (spec 4.3.2, 4.3.4, 4.1.7).

The hub keeps one active project, an ordered queue of projects whose continue-after flag is
standing, the flag each project was last handed (`handed_flags`, so that a flag handed to a
transition never queues its project again), the list `closing` of projects that stopped being
active and are not yet proven closed, and the `transition` that is being carried out. Nothing
here starts or stops a process: `HubState` is data, and every move is a function that returns a
new state or refuses with a reason the hub words.

The file is canonical JSON, strict to read (an unknown key, a key twice, broken JSON, a file over
256 KiB or a broken invariant is `hub_state_invalid` by name, and the file is never rewritten over
it) and written whole, atomically, only by the hub that holds `hub.lock` and under it
(`HubStateStore`). The invariants: a project is closing at most once, is never both active and
closing, and a transition names the project that is active.

`proven_closed` is the rule of 4.1.7 that decides when a next project may start as active: its
process is dead by `(pid, process_started)` AND the head of its ownership, read without
writing, is not `opened`. Anything short of both is not proven.
"""
from __future__ import annotations

import json
import re
import threading
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from conductor import atomic_replace, ownership_records, process_identity
from conductor.hub import home, instance
from conductor.ownership_errors import OwnerRefused

SCHEMA_VERSION = 1
FILE_NAME = "hub-state.json"
MAX_BYTES = 256 * 1024
KINDS = ("queue", "manual")
#: The reasons a move is refused; the hub words each one (`already_active`,
#: `active_not_closed` and `project_queue_changed` are codes of 4.6.5).
REFUSALS = frozenset({"already_active", "active_not_closed", "project_queue_changed",
                      "already_spawned"})
#: Proposals: the spec names no code for a hub-state file that is not the schema, nor for one
#: that cannot be written. `registry_invalid` and `registry_unwritable` are the analogues.
PROPOSED_CODES = frozenset({"hub_state_invalid", "hub_state_unwritable"})

_ID = re.compile(r"[0-9a-f]{32}")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_STARTED = re.compile(r"windows:\d+|linux:[0-9a-f-]{36}:\d+|darwin:\d+\.\d{6}")
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"
_TOP_KEYS = frozenset({"schema_version", "active_project_id", "queue", "handed_flags",
                       "closing", "transition"})
_CLOSING_KEYS = frozenset({"project_id", "pid", "process_started", "activation_nonce", "since"})
_TRANSITION_KEYS = frozenset({"id", "project_id", "kind", "flag", "spawned_at"})
_NOT_OPENED = frozenset({"active", "closed", "recovered", "rolled_back"})


class HubStateError(Exception):
    """A refusal of the store: a closed code and one line of detail.

    Raises:
        ValueError: `code` is not one of `PROPOSED_CODES`.
    """

    def __init__(self, code: str, detail: str) -> None:
        if code not in PROPOSED_CODES:
            raise ValueError(f"{code!r} is not a code of the hub state")
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


class TransitionRefused(Exception):
    """A move the state does not allow; `reason` is one of `REFUSALS`."""

    def __init__(self, reason: str, detail: str = "") -> None:
        if reason not in REFUSALS:
            raise ValueError(f"{reason!r} is not a reason a move can be refused for")
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


@dataclass(frozen=True)
class Flag:
    """The continue-after flag a transition carries: its id and revision (4.3.4)."""

    flag_id: str
    revision: int


@dataclass(frozen=True)
class ClosingEntry:
    """A project that stopped being active and is not yet proven closed (S1)."""

    project_id: str
    pid: int
    process_started: str | None
    activation_nonce: str
    since: str


@dataclass(frozen=True)
class Transition:
    """The switch being carried out: `spawned_at` stays `None` until the child is started."""

    id: str
    project_id: str
    kind: str
    flag: Flag | None
    spawned_at: str | None


@dataclass(frozen=True)
class HubState:
    """The whole file. `handed_flags` is read-only; every move returns a new state."""

    active_project_id: str | None = None
    queue: tuple[str, ...] = ()
    handed_flags: Mapping[str, str] = field(default_factory=dict)
    closing: tuple[ClosingEntry, ...] = ()
    transition: Transition | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "handed_flags", MappingProxyType(dict(self.handed_flags)))


# -- the grammar and the invariants ------------------------------------------------------------


def _is_instant(value: object) -> bool:
    try:
        return isinstance(value, str) and bool(datetime.strptime(value, _INSTANT))
    except ValueError:
        return False


def _is_id(value: object) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _closing_problem(entry: ClosingEntry) -> str | None:
    checks = (
        (_is_id(entry.project_id), "project_id must be 32 lowercase hex characters"),
        (type(entry.pid) is int and 1 <= entry.pid < 2**31, "pid must be a positive integer"),
        (entry.process_started is None or (isinstance(entry.process_started, str)
                                           and _STARTED.fullmatch(entry.process_started)),
         "process_started must be null or the spelling of an OS"),
        (_is_id(entry.activation_nonce), "activation_nonce must be 32 lowercase hex characters"),
        (_is_instant(entry.since), "since must be a UTC time like 2026-09-30T10:00:00Z"))
    return next((message for holds, message in checks if not holds), None)


def _transition_problem(transition: Transition, active: str | None) -> str | None:
    flag = transition.flag
    checks = (
        (isinstance(transition.id, str) and _UUID.fullmatch(transition.id),
         "transition.id must be a uuid"),
        (transition.kind in KINDS, f"transition.kind must be one of {', '.join(KINDS)}"),
        (transition.project_id == active, "a transition must name the project that is active"),
        (flag is None or (isinstance(flag.flag_id, str) and _UUID.fullmatch(flag.flag_id)
                          and type(flag.revision) is int and flag.revision >= 1),
         "transition.flag must be null or a uuid and a revision from 1"),
        (transition.spawned_at is None or _is_instant(transition.spawned_at),
         "transition.spawned_at must be null or a UTC time"))
    return next((message for holds, message in checks if not holds), None)


def problem_with(current: HubState) -> str | None:
    """The first invariant or grammar rule `current` breaks, or `None` when it is whole."""
    if current.active_project_id is not None and not _is_id(current.active_project_id):
        return "active_project_id must be null or 32 lowercase hex characters"
    if not all(_is_id(p) for p in current.queue) or len(set(current.queue)) != len(current.queue):
        return "queue must hold each project at most once, by its 32-hex id"
    if not all(_is_id(k) and isinstance(v, str) and v for k, v in current.handed_flags.items()):
        return "handed_flags must map a project id to a flag id"
    for index, entry in enumerate(current.closing):
        found = _closing_problem(entry)
        if found is not None:
            return f"closing[{index}]: {found}"
    closing_ids = [entry.project_id for entry in current.closing]
    if len(set(closing_ids)) != len(closing_ids):
        return "a project is closing twice"
    if current.active_project_id in closing_ids:
        return "a project cannot be both active and closing"
    if current.transition is not None:
        return _transition_problem(current.transition, current.active_project_id)
    return None


# -- reading: strict about the schema ----------------------------------------------------------


def _invalid(detail: str) -> HubStateError:
    return HubStateError("hub_state_invalid", f"{FILE_NAME}: {detail}")


def _strict_json(text: str) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict:
        if len({key for key, _ in pairs}) != len(pairs):
            raise ValueError("a key appears twice")
        return dict(pairs)

    def refuse(constant: str) -> object:
        raise ValueError(f"{constant} is not JSON")

    return json.loads(text, object_pairs_hook=unique, parse_constant=refuse)


def _keys(value: object, keys: frozenset[str], what: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise _invalid(f"{what} must be an object with exactly its keys")
    return value


def _closing_from(raw: object, index: int) -> ClosingEntry:
    entry = _keys(raw, _CLOSING_KEYS, f"closing[{index}]")
    return ClosingEntry(entry["project_id"], entry["pid"], entry["process_started"],
                        entry["activation_nonce"], entry["since"])


def _transition_from(raw: object) -> Transition | None:
    if raw is None:
        return None
    entry = _keys(raw, _TRANSITION_KEYS, "transition")
    flag = entry["flag"]
    if flag is not None:
        held = _keys(flag, frozenset({"flag_id", "revision"}), "transition.flag")
        flag = Flag(held["flag_id"], held["revision"])
    return Transition(entry["id"], entry["project_id"], entry["kind"], flag, entry["spawned_at"])


def _parse(data: bytes) -> HubState:
    try:
        raw = _strict_json(data.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise _invalid(f"is not JSON the hub accepts: {error}") from error
    document = _keys(raw, _TOP_KEYS, "the file")
    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise _invalid(f"schema_version must be the number {SCHEMA_VERSION}")
    queue, closing, handed = document["queue"], document["closing"], document["handed_flags"]
    if not isinstance(queue, list) or not isinstance(closing, list) \
            or not isinstance(handed, dict):
        raise _invalid("queue and closing must be lists and handed_flags an object")
    parsed = HubState(document["active_project_id"], tuple(queue), handed,
                      tuple(_closing_from(row, n) for n, row in enumerate(closing)),
                      _transition_from(document["transition"]))
    found = problem_with(parsed)
    if found is not None:
        raise _invalid(found)
    return parsed


def state_file(folder: Path | str | None = None) -> Path:
    """`<conduct-home>/hub-state.json`, or the same name in `folder`."""
    return (home.conduct_home_path() if folder is None else Path(folder)) / FILE_NAME


def load(folder: Path | str | None = None) -> HubState:
    """Read the file; a missing file is the empty state, and reading writes nothing.

    Raises:
        HubStateError: `hub_state_invalid`: the file exists and is not the schema.
    """
    path = state_file(folder)
    try:
        if path.stat().st_size > MAX_BYTES:
            raise _invalid(f"is larger than {MAX_BYTES // 1024} KiB")
        data = path.read_bytes()
    except FileNotFoundError:
        return HubState()
    except OSError as error:
        raise _invalid(f"cannot be read: {error}") from error
    return _parse(data)


# -- writing: one writer, under the hub's lock ---------------------------------------------------


def _document(current: HubState) -> dict:
    def flag(value: Flag | None) -> dict | None:
        return None if value is None else {"flag_id": value.flag_id, "revision": value.revision}

    transition = current.transition
    return {
        "schema_version": SCHEMA_VERSION, "active_project_id": current.active_project_id,
        "queue": list(current.queue), "handed_flags": dict(current.handed_flags),
        "closing": [{"project_id": c.project_id, "pid": c.pid,
                     "process_started": c.process_started,
                     "activation_nonce": c.activation_nonce, "since": c.since}
                    for c in current.closing],
        "transition": None if transition is None else {
            "id": transition.id, "project_id": transition.project_id, "kind": transition.kind,
            "flag": flag(transition.flag), "spawned_at": transition.spawned_at}}


class HubStateStore:
    """The one writer of `hub-state.json`: the hub that holds `hub.lock`, under that lock."""

    def __init__(self, folder: Path | str | None, hub: instance.HubInstance) -> None:
        self._folder = None if folder is None else Path(folder)
        self._hub = hub
        self._mutex = threading.Lock()

    def load(self) -> HubState:
        """The state as it stands on disk."""
        return load(self._folder)

    def update(self, change: Callable[[HubState], HubState]) -> HubState:
        """Read the state, apply `change` and publish the result if it differs.

        Args:
            change: A pure function of the state read here; it may raise `TransitionRefused`.

        Raises:
            HubLockLost: The hub no longer holds `hub.lock`; nothing is written.
            HubStateError: The file is not the schema, the result would break an invariant, or
                the file could not be written.
            TransitionRefused: `change` refused.
        """
        with self._mutex:
            self._hub.check()
            current = self.load()
            updated = change(current)
            if updated != current:
                self._write(updated)
            return updated

    def _write(self, updated: HubState) -> None:
        found = problem_with(updated)
        if found is not None:
            raise _invalid(f"would not be the schema: {found}")
        payload = ownership_records.canonical(_document(updated))
        try:
            atomic_replace.replace_bytes(state_file(self._folder), payload)
        except OSError as error:
            raise HubStateError("hub_state_unwritable",
                                f"{FILE_NAME} could not be written: {error}") from error


# -- the moves ------------------------------------------------------------------------------------


def begin_switch(current: HubState, new_id: str, *, kind: str, transition_id: str, since: str,
                 flag: Flag | None, previous: ClosingEntry | None) -> HubState:
    """Make `new_id` the active project, recording the intent in one state (4.1.7, step 1).

    The new project leaves the queue, the old active one goes to `closing` (nothing is stopped
    here), the transition is recorded unspawned, and the flag handed to it is remembered.

    Args:
        previous: The closing entry of the project that is active now. `None` when nothing is
            active, or when the active project has nothing left to close (no process of it ever
            ran, or it is already proven closed): the caller has judged that, this function
            cannot.

    Raises:
        TransitionRefused: `already_active`, or `active_not_closed` when the new project is
            itself still closing.
        ValueError: `kind` is not a kind, or `previous` is not the entry of the active project.
    """
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    if new_id == current.active_project_id:
        raise TransitionRefused("already_active", new_id)
    if any(entry.project_id == new_id for entry in current.closing):
        raise TransitionRefused("active_not_closed", f"{new_id} has not finished closing")
    active = current.active_project_id
    if previous is not None and previous.project_id != active:
        raise ValueError("previous must be the closing entry of the project that is active")
    handed = dict(current.handed_flags)
    if flag is not None:
        handed[new_id] = flag.flag_id
    return replace(
        current, active_project_id=new_id,
        queue=tuple(p for p in current.queue if p != new_id), handed_flags=handed,
        closing=(*current.closing, *(() if previous is None else (previous,))),
        transition=Transition(transition_id, new_id, kind, flag, None))


def settle_closed(current: HubState, closed_ids: Iterable[str], *,
                  spawned_at: str | None = None, transition_id: str | None = None) -> HubState:
    """Take the proven-closed projects off `closing`, and stamp the spawn in the same state.

    Giving `spawned_at` is the decision to start the child of the pending transition
    `transition_id`: it is refused while anything is still closing (`active_not_closed`) and
    when the transition was already spawned (`already_spawned`).

    Raises:
        ValueError: `spawned_at` is given and `transition_id` is not the pending transition's.
        TransitionRefused: see above.
    """
    gone = set(closed_ids)
    remaining = tuple(entry for entry in current.closing if entry.project_id not in gone)
    transition = current.transition
    if spawned_at is not None:
        if transition is None or transition.id != transition_id:
            raise ValueError("transition_id must be the id of the pending transition")
        if transition.spawned_at is not None:
            raise TransitionRefused("already_spawned", transition.id)
        if remaining:
            raise TransitionRefused("active_not_closed", "a project is still closing")
        transition = replace(transition, spawned_at=spawned_at)
    if remaining == current.closing and transition is current.transition:
        return current
    return replace(current, closing=remaining, transition=transition)


def enqueue(current: HubState, project_id: str, flag_id: str) -> HubState:
    """Put a project at the end of the queue because it reads a standing flag (4.3.4).

    Nothing changes when the project is already queued or when `flag_id` is the one last
    handed to a transition (a flag handed to a child that did not consume it is not handed
    again: the desk says so).
    """
    if project_id in current.queue or current.handed_flags.get(project_id) == flag_id:
        return current
    return replace(current, queue=(*current.queue, project_id))


def dequeue(current: HubState, project_id: str) -> HubState:
    """Take a project off the queue (its flag was taken down, or it left the list)."""
    if project_id not in current.queue:
        return current
    return replace(current, queue=tuple(p for p in current.queue if p != project_id))


def forget(current: HubState, project_id: str, *,
           closing: ClosingEntry | None = None) -> HubState:
    """A project leaves the list: out of the queue, the handed flags and the active place.

    A closing entry that already stands stays (the hub cannot prove a closure of a project it
    no longer lists, so the entry keeps blocking until the project is listed again). `closing`
    is the entry the caller judged the forgotten ACTIVE project owes: it is added when the project
    was active and is not on the list yet, so that forgetting cannot shed the obligation.

    Raises:
        ValueError: `closing` names another project.
    """
    if closing is not None and closing.project_id != project_id:
        raise ValueError("closing must be the entry of the project that is forgotten")
    was_active = current.active_project_id == project_id
    owed = was_active and closing is not None and all(
        entry.project_id != project_id for entry in current.closing)
    return replace(
        current, active_project_id=None if was_active else current.active_project_id,
        queue=tuple(p for p in current.queue if p != project_id),
        handed_flags={k: v for k, v in current.handed_flags.items() if k != project_id},
        transition=None if was_active else current.transition,
        closing=(*current.closing, *((closing,) if owed else ())))


def reorder(current: HubState, order: Sequence[str]) -> HubState:
    """The queue in `order`, which must be a permutation of the queue as it stands.

    Raises:
        TransitionRefused: `project_queue_changed`: a project short, over, twice or a stranger.
    """
    if Counter(order) != Counter(current.queue):
        raise TransitionRefused("project_queue_changed", "the order is not a permutation")
    return current if tuple(order) == current.queue else replace(current, queue=tuple(order))


def stop_active(current: HubState, stopped: ClosingEntry, *, transition_id: str, since: str,
                next_flag: Flag | None = None) -> HubState:
    """Stop the active project and hand its place to the next queued one (4.1.7, 4.3.4).

    The next is the first project of the queue other than the one just stopped; with nobody
    else queued there is no active project until a person makes one.

    Raises:
        ValueError: `stopped` is not the entry of the active project.
        TransitionRefused: As `begin_switch`, for the next project.
    """
    if current.active_project_id != stopped.project_id:
        raise ValueError("stopped must be the closing entry of the active project")
    following = next((p for p in current.queue if p != stopped.project_id), None)
    if following is None:
        return replace(current, active_project_id=None, transition=None,
                       closing=(*current.closing, stopped))
    return begin_switch(current, following, kind="queue", transition_id=transition_id,
                        since=since, flag=next_flag, previous=stopped)


# -- proven closed --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Closure:
    """Whether a project is proven closed, and the one word that says why or why not."""

    closed: bool
    reason: str


def proven_closed(entry: ClosingEntry, root: Path | str, *,
                  probe: Callable[[int, str | None], str] = process_identity.probe,
                  head_of: Callable[[Path | str], tuple] = ownership_records.state) -> Closure:
    """The rule of 4.1.7: the process is dead AND the ownership head is not `opened`.

    Args:
        entry: The pair the project's child recorded, and the activation it belonged to.
        root: The project folder; its ownership head is read, never written.
        probe: `process_identity.probe` unless a test stands in.
        head_of: `ownership_records.state` unless a test stands in.

    Returns:
        `Closure(True, "proven")`, or `Closure(False, <why>)`: `process_alive`,
        `process_unproven`, `head_opened`, `head_<ownership code>` or `head_unreadable`
        (the head could not be read), `not_activated`, `identity_changed` (the head belongs to
        another activation than the entry's), `head_unsettled`.
    """
    seen = probe(entry.pid, entry.process_started)
    if seen != "dead":
        return Closure(False, "process_alive" if seen == "alive" else "process_unproven")
    try:
        _, head = head_of(root)
    except OwnerRefused as refused:
        return Closure(False, f"head_{refused.code}")
    except OSError:
        return Closure(False, "head_unreadable")
    if head is None:
        return Closure(False, "not_activated")
    if head["phase"] == "opened":
        return Closure(False, "head_opened")
    if head["nonce"] != entry.activation_nonce:
        return Closure(False, "identity_changed")
    if head["phase"] not in _NOT_OPENED:
        return Closure(False, "head_unsettled")
    return Closure(True, "proven")
