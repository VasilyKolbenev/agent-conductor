"""The supervisor of the hub's children: start, restart, switch, stop (spec 4.1.4, 4.1.5, 4.1.7).

It holds the hub's children, reads their status files, and makes the moves of 4.1.7 through the
pure pieces around it: `state` (what is active, queued, closing, and the rule that a project is
proven closed), `lifecycle` (the words of a child and the restart table) and `spawn` (the start
itself). It has a `tick()` and no thread of its own: the loop that calls it once a second belongs
to the HTTP hub, which does not exist yet, and every decision here is judged on fakes.

Two rules carry the invariant "at most one active child", and both are here in one place, `_busy`
and `_can_begin`: a child is started in `active` only when no `active` process of any project is
alive, no process of that same project is alive in any mode, and `closing` is empty, which is to
say every project that stopped being active is proven closed. "Any project" is every status file
under `run/` and every child of the hub, whether or not the registry still lists the project: a
project taken off the list keeps its process, and keeps its place on `closing` until it is
proven closed (it can be only once it is listed again, for its root is what says its head).
Starting is then one decision carried out in two writes that cannot be told apart by a crash: the
state records the start (`spawned_at`, with the closure settled in the same write) and only then
the child is started, so that a restart of the hub never starts the same transition twice and
never hands the flag again.

The hub does not start a dead child again. A child that died left its owner session `opened`, so
any start of it reads `recovery_required`; the hub's loop leaves it, and only the restart of the
hub (`restart`) decides, by the table of 4.1.7, to start the active project once more, without a
transition and without a flag.
"""
from __future__ import annotations

import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from conductor import ownership_records, process_identity, up_status
from conductor.hub import lifecycle as words
from conductor.hub import registry, spawn, state
from conductor.ownership_errors import OwnerRefused

START_TIMEOUT_SECONDS = 30.0
#: The refusals of a route that changes who is active or starts a child (4.6.5).
CODES = frozenset({"project_not_found", "project_running", "project_not_running",
                   "project_busy", "already_active", "active_not_closed",
                   "hub_in_kill_on_close_job", "project_queue_changed"})
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"
_WORKING = ("serving", "stopping", "stop_overdue")
#: The only name a child's status file can have (`--status-file` must be `<project-id>.json`).
_STATUS_NAME = re.compile(r"[0-9a-f]{32}\.json")


class SupervisorRefused(Exception):
    """A move the supervisor will not make: `code` is one of `CODES`, `detail` one line."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in CODES:
            raise ValueError(f"{code!r} is not a code a route refuses with")
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class Seen:
    """What one look at a project found: its status file, its process, and the hub's own child."""

    record: up_status.StatusRecord | None
    fresh: bool
    own: spawn.Child | None
    liveness: str
    live: bool
    mode: str | None
    unreadable: bool = False


@dataclass(frozen=True)
class RunScan:
    """What `run/` says: the mode of every live process, and the status files nobody can read."""

    live: dict[str, str]
    unreadable: tuple[str, ...]


@dataclass(frozen=True)
class UnlistedClosing:
    """A project that left the list while it still owes a closure (tech lead, 30.09, rule b).

    The hub cannot prove it closed without its root, so the entry blocks every next active child.
    `action` is what the page offers: put the project back in the list (the add dialog with the
    same folder, which finds the same root and id again).
    """

    project_id: str
    since: str
    action: str = "relist"


@dataclass(frozen=True)
class ProjectStatus:
    """A project in the words of 4.6.4: its lifecycle, working state, mode and drain deadline."""

    lifecycle: words.Lifecycle
    working: str
    mode: str | None
    drain_deadline: datetime | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Supervisor:
    """The hub's children and the moves of 4.1.7 over them."""

    def __init__(self, home: Path | str, store: state.HubStateStore, spawner: spawn.Spawner, *,
                 hub_port: int, clock: Callable[[], datetime] = _utc_now,
                 probe: Callable[[int, str | None], str] = process_identity.probe,
                 head_of: Callable[[Path | str], tuple] = ownership_records.state,
                 start_timeout: float = START_TIMEOUT_SECONDS,
                 new_id: Callable[[], str] = lambda: str(uuid.uuid4())) -> None:
        self._home, self._store, self._spawner = Path(home), store, spawner
        self._hub_port, self._clock, self._probe = hub_port, clock, probe
        self._head_of, self._timeout, self._new_id = head_of, start_timeout, new_id
        self._lock = threading.RLock()
        self._children: dict[str, spawn.Child] = {}
        self._prior: dict[str, spawn.Child] = {}
        self._started: dict[str, datetime] = {}
        self._last: dict[str, dict] = {}
        self._awaiting: set[str] = set()
        self._timed_out: set[str] = set()
        self._retried: set[str] = set()
        self._codes: dict[str, str] = {}
        self._failed: dict[str, str] = {}

    # -- the moves a person asks for ------------------------------------------------------------

    def activate(self, project_id: str, *, flag: state.Flag | None = None) -> state.HubState:
        """Make a project the active one: record the intent, and ask the old child to drain.

        The new child is started by a later `tick`, once the old one is proven closed.

        Raises:
            SupervisorRefused: `project_not_found`, `hub_in_kill_on_close_job` (before anything
                changes), `already_active`, or `active_not_closed` (the project is itself still
                closing).
        """
        with self._lock:
            self._project(project_id)
            self._require_startable()
            current = self._store.load()
            previous = self._previous_entry(current)
            updated = self._switch(lambda s: state.begin_switch(
                s, project_id, kind="manual", transition_id=self._new_id(),
                since=self._now_iso(), flag=flag, previous=previous))
            self._drain(current.active_project_id, project_id)
            self._codes.pop(project_id, None)
            self._awaiting.discard(project_id)
            return updated

    def view(self, project_id: str) -> None:
        """Open a project for viewing: a child in `view` mode, which starts nothing itself.

        Raises:
            SupervisorRefused: `project_not_found`, `hub_in_kill_on_close_job`,
                `already_active`, `project_running`.
        """
        with self._lock:
            project = self._project(project_id)
            self._require_startable()
            if self._store.load().active_project_id == project_id:
                raise SupervisorRefused("already_active", project_id)
            if self._seen(project).live:
                raise SupervisorRefused("project_running", project_id)
            self._launch(project, mode="view")

    def stop(self, project_id: str, *, next_flag: state.Flag | None = None) -> None:
        """Stop a project on its checkpoint: drain it, and hand the active place on.

        A view child is drained and nothing else changes. The active project leaves the place to
        the first queued one (`next_flag` is that project's flag as the hub just read it).

        Raises:
            SupervisorRefused: `project_not_found`, `project_not_running`, `project_busy` (the
                child has not reported yet, so there is nothing to record it by).
        """
        with self._lock:
            project = self._project(project_id)
            seen = self._seen(project)
            if not seen.live:
                raise SupervisorRefused("project_not_running", project_id)
            current = self._store.load()
            if current.active_project_id != project_id:
                self._drain(project_id)
                return
            entry = self._entry(project_id, seen) if seen.fresh else None
            if entry is None:
                raise SupervisorRefused("project_busy", "the child has not reported yet")
            self._switch(lambda s: state.stop_active(
                s, entry, transition_id=self._new_id(), since=self._now_iso(),
                next_flag=next_flag))
            self._drain(project_id)
            self._awaiting.discard(project_id)

    def status(self, project_id: str) -> ProjectStatus:
        """A project in the words of 4.6.4.

        Raises:
            SupervisorRefused: `project_not_found`.
        """
        with self._lock:
            project = self._project(project_id)
            seen = self._seen(project)
            current = self._store.load()
            return ProjectStatus(
                self._lifecycle(project, seen), words.working_of(
                    project_id, active=current.active_project_id, queue=current.queue,
                    viewing=(project_id,) if seen.live and seen.mode == "view" else ()),
                seen.mode, seen.record.drain_deadline if seen.record and seen.live else None)

    def forget(self, project_id: str) -> None:
        """Take a project off the list ("Убрать из списка"); its files are not touched.

        The project leaves the registry, the queue, the handed flags and, if it was active, the
        active place. An active project that is not yet proven closed leaves its obligation on
        `closing` first, in the same state write: forgetting never sheds it (rule b of 30.09).

        Raises:
            SupervisorRefused: `project_not_found`, `project_running` (a child of it lives).
        """
        with self._lock:
            project = self._project(project_id)
            seen = self._seen(project)
            if seen.live:
                raise SupervisorRefused("project_running", project_id)
            current = self._store.load()
            owed = None
            if current.active_project_id == project_id:
                entry = self._entry(project_id, seen)
                if entry is not None and not state.proven_closed(
                        entry, project.root, probe=self._probe, head_of=self._head_of).closed:
                    owed = entry
            self._switch(lambda s: state.forget(s, project_id, closing=owed))
            try:
                registry.remove_project(project_id, self._home)
            except registry.RegistryError as error:
                raise SupervisorRefused("project_not_found", error.detail) from error
            self._awaiting.discard(project_id)

    def unlisted_closing(self) -> tuple[UnlistedClosing, ...]:
        """The closing entries of projects the registry does not list (rule b of 30.09).

        Empty when the registry cannot be read: nothing can then be said to be unlisted.
        """
        with self._lock:
            try:
                listed = {p.project_id for p in registry.load(self._home).projects}
            except registry.RegistryError:
                return ()
            return tuple(UnlistedClosing(entry.project_id, entry.since)
                         for entry in self._store.load().closing
                         if entry.project_id not in listed)

    # -- the loop --------------------------------------------------------------------------------

    def restart(self) -> None:
        """The procedure of 4.1.7 at the hub's own start.

        The active project, if a transition is not still waiting to begin, is started by the table
        (no transition, no flag) as soon as nothing stands in the way; what is proven closed is
        settled; view children are not restored. The work is a `tick`, then.
        """
        with self._lock:
            current = self._store.load()
            if current.active_project_id is not None and self._waiting(current) is None:
                self._awaiting.add(current.active_project_id)
            self.tick()

    def tick(self) -> None:
        """One pass: bind retries, start timeouts, what is proven closed, what may now start."""
        with self._lock:
            try:
                projects = registry.load(self._home).projects
            except registry.RegistryError:
                return
            self._retry_failed_binds(projects)
            self._enforce_start_timeouts(projects)
            current = self._store.load()
            verdicts = self._verdicts(current, projects)
            closed = [pid for pid, verdict in verdicts.items() if verdict.closed]
            waiting = self._waiting(current)
            # A project that left the registry while it waited is not started, and the transition
            # is not stamped: its flag is not spent on a child that was never started.
            registered = None if waiting is None else next(
                (p for p in projects if p.project_id == waiting.project_id), None)
            if registered is not None and self._can_begin(current, closed, waiting):
                self._begin(waiting, closed, registered)
            elif closed:
                self._store.update(lambda s: state.settle_closed(s, closed))
            self._mark_stuck(current, verdicts, waiting)
            self._start_awaiting(projects)

    # -- looking ---------------------------------------------------------------------------------

    def _now_iso(self) -> str:
        return self._clock().strftime(_INSTANT)

    def _project(self, project_id: str) -> registry.Project:
        try:
            found = registry.load(self._home).project(project_id)
        except registry.RegistryError as error:
            raise SupervisorRefused("project_not_found", error.detail) from error
        if found is None:
            raise SupervisorRefused("project_not_found", project_id)
        return found

    def _seen(self, project: registry.Project) -> Seen:
        return self._seen_id(project.project_id)

    def _seen_id(self, pid: str) -> Seen:
        """One look at a project by its id; the project need not be in the registry."""
        own = self._children.get(pid)
        unreadable = False
        try:
            record = up_status.read_status(spawn.status_path(self._home, pid))
        except up_status.StatusInvalid:
            record, unreadable = None, True
        started = self._started.get(pid)
        fresh = record is not None and (
            started is None or record.updated_at >= started.replace(microsecond=0))
        liveness = "dead" if record is None else self._probe(record.pid, record.process_started)
        own_alive = own is not None and own.poll() is None
        mode = own.mode if own_alive else (
            record.mode if record is not None and liveness != "dead" else None)
        return Seen(record, fresh, own, liveness, own_alive or liveness != "dead", mode,
                    unreadable)

    def _head_phase(self, project: registry.Project) -> str | None:
        try:
            _, head = self._head_of(project.root)
        except (OwnerRefused, OSError):
            return None
        return None if head is None else head["phase"]

    def _lifecycle(self, project: registry.Project, seen: Seen) -> words.Lifecycle:
        pid = project.project_id
        if pid in self._failed and seen.own is None:
            return words.Lifecycle("failed", self._failed[pid])
        record = seen.record if seen.fresh else None
        own_alive = seen.own is not None and seen.own.poll() is None
        pending = None if seen.own is None or record is not None else (
            "alive" if own_alive else "exited")
        head = None
        if record is not None and seen.liveness == "dead" and record.state in _WORKING:
            head = self._head_phase(project)
        prior = self._prior.get(pid)
        found = words.derive(record, seen.liveness, pending=pending, head_phase=head,
                             prior_alive=prior is not None and prior.poll() is None,
                             hub_code=self._codes.get(pid))
        if seen.unreadable and found.state_code is None:
            return replace(found, state_code="status_unreadable")
        return found

    def _entry(self, project_id: str, seen: Seen) -> state.ClosingEntry | None:
        """The closing entry of a project by what its status file says; `None` with no file."""
        if seen.record is None:
            return None
        return state.ClosingEntry(project_id, seen.record.pid, seen.record.process_started,
                                  project_id, self._now_iso())

    def _previous_entry(self, current: state.HubState) -> state.ClosingEntry | None:
        """What the active project leaves to close: an entry, or `None` for nothing to close.

        A project that left the registry still leaves its entry (its process may live): with no
        root to read its ownership head from, the entry can never be proven closed here, which
        blocks the next child (`project_unknown`) until the project is registered again.
        """
        active = current.active_project_id
        if active is None:
            return None
        seen = self._seen_id(active)
        own_alive = seen.own is not None and seen.own.poll() is None
        if own_alive and not seen.fresh:
            # Nothing names this child's process yet, so nothing could be put on `closing`.
            raise SupervisorRefused("project_busy", "the active child has not reported yet")
        entry = self._entry(active, seen)
        if entry is None or own_alive:
            return entry
        try:
            project = self._project(active)
        except SupervisorRefused:
            return entry
        if seen.liveness == "dead" and state.proven_closed(
                entry, project.root, probe=self._probe, head_of=self._head_of).closed:
            return None
        return entry

    def _verdicts(self, current: state.HubState,
                  projects: tuple[registry.Project, ...]) -> dict[str, state.Closure]:
        known = {project.project_id: project for project in projects}
        verdicts = {}
        for entry in current.closing:
            project = known.get(entry.project_id)
            verdicts[entry.project_id] = state.Closure(False, "project_unknown") \
                if project is None else state.proven_closed(
                    entry, project.root, probe=self._probe, head_of=self._head_of)
        return verdicts

    def _waiting(self, current: state.HubState) -> state.Transition | None:
        """The transition recorded and not yet begun, if the active project is its project."""
        found = current.transition
        if found is not None and found.spawned_at is None:
            return found
        return None

    def _scan(self) -> RunScan:
        """Every live process, registered or not, and every status file that is not the record.

        The hub's own children, and every status file under `run/` (4.1.7, restart steps 1 and
        2: all `run/*.json`, not the files of the projects the registry happens to list). A file
        named like a status file that is not the record FAILS CLOSED (tech lead, 30.09): it may
        be the file of a live process, so it is reported, and `_busy` counts it. A file with any
        other name is not one a child writes and is left alone.
        """
        live = {pid: child.mode for pid, child in self._children.items() if child.poll() is None}
        unreadable: list[str] = []
        for path in sorted((self._home / "run").glob("*.json")):
            if _STATUS_NAME.fullmatch(path.name) is None:
                continue
            try:
                record = up_status.read_status(path)
            except up_status.StatusInvalid:
                unreadable.append(path.stem)
                continue
            if record is not None and record.project_id not in live and self._probe(
                    record.pid, record.process_started) != "dead":
                live[record.project_id] = record.mode
        return RunScan(live, tuple(unreadable))

    def _busy(self, project_id: str) -> bool:
        """Whether something stands in the way of starting this project in `active`."""
        found = self._scan()
        return (bool(found.unreadable) or project_id in found.live
                or "active" in found.live.values())

    # -- carrying out ----------------------------------------------------------------------------

    def _require_startable(self) -> None:
        try:
            self._spawner.require_startable()
        except spawn.SpawnRefused as refused:
            raise SupervisorRefused(refused.code, refused.detail) from refused

    def _switch(self, change: Callable[[state.HubState], state.HubState]) -> state.HubState:
        try:
            return self._store.update(change)
        except state.TransitionRefused as refused:
            raise SupervisorRefused(refused.reason, str(refused)) from refused

    def _drain(self, *project_ids: str | None) -> None:
        for project_id in project_ids:
            child = self._children.get(project_id) if project_id else None
            if child is not None and child.poll() is None:
                child.close_stdin()

    def _can_begin(self, current: state.HubState, closed: list[str],
                   waiting: state.Transition) -> bool:
        still_closing = [e for e in current.closing if e.project_id not in closed]
        return not still_closing and not self._busy(waiting.project_id)

    def _begin(self, waiting: state.Transition, closed: list[str],
               project: registry.Project) -> None:
        """Settle the closure and stamp the spawn in one write, then start the child."""
        self._store.update(lambda s: state.settle_closed(
            s, closed, spawned_at=self._now_iso(), transition_id=waiting.id))
        flag = waiting.flag
        self._launch(project, mode="active", transition=waiting.id,
                     auto_continue=None if flag is None else f"{flag.flag_id}@{flag.revision}")

    def _start_awaiting(self, projects: tuple[registry.Project, ...]) -> None:
        """Start the active project of a restart, by the table, once nothing stands in the way."""
        current = self._store.load()
        by_id = {project.project_id: project for project in projects}
        for project_id in sorted(self._awaiting):
            project = by_id.get(project_id)
            if project is None or current.active_project_id != project_id:
                self._awaiting.discard(project_id)
                continue
            seen = self._seen(project)
            action = words.restart_action(seen.record, seen.liveness)
            if action == "offer_recover":
                self._awaiting.discard(project_id)
            elif action == "start" and not current.closing and not self._busy(project_id):
                self._awaiting.discard(project_id)
                self._launch(project, mode="active")

    def _launch(self, project: registry.Project, *, mode: str, transition: str | None = None,
                auto_continue: str | None = None, port: int | None = None,
                retry: bool = False) -> None:
        """Start a child; a start the OS or the job refuses is remembered as the failure."""
        pid = project.project_id
        asked = port if port is not None else (0 if project.port == self._hub_port
                                               else project.port)
        arguments = {"project_id": pid, "root": project.root, "port": asked, "mode": mode,
                     "transition": transition, "auto_continue": auto_continue}
        try:
            child = self._spawner.start(**arguments)
        except spawn.SpawnRefused as refused:
            self._failed[pid] = refused.code
            return
        earlier = self._children.get(pid)
        if earlier is not None and earlier.poll() is None:
            self._prior[pid] = earlier
        self._children[pid], self._started[pid], self._last[pid] = child, self._clock(), arguments
        self._codes.pop(pid, None)
        self._failed.pop(pid, None)
        self._timed_out.discard(pid)
        if not retry:
            self._retried.discard(pid)

    def _mark_stuck(self, current: state.HubState, verdicts: dict[str, state.Closure],
                    waiting: state.Transition | None) -> None:
        """Say why the project that waits cannot start: a closure not proven, or a file unread."""
        target = waiting.project_id if waiting is not None else (
            current.active_project_id if current.active_project_id in self._awaiting else None)
        if target is None:
            return
        stuck = any(not v.closed and v.reason != "process_alive" for v in verdicts.values())
        code = "active_not_closed" if stuck else (
            "status_unreadable" if self._scan().unreadable else None)
        if code is not None:
            self._codes[target] = code
        elif self._codes.get(target) in ("active_not_closed", "status_unreadable"):
            self._codes.pop(target)

    def _enforce_start_timeouts(self, projects: tuple[registry.Project, ...]) -> None:
        """A child that has not come to `serving` in time is asked to drain (4.1.4)."""
        now = self._clock()
        for project in projects:
            pid = project.project_id
            seen = self._seen(project)
            started = self._started.get(pid)
            if seen.own is None or seen.own.poll() is not None or started is None \
                    or pid in self._timed_out:
                continue
            ready = seen.fresh and seen.record is not None and seen.record.state != "starting"
            if not ready and (now - started).total_seconds() >= self._timeout:
                seen.own.close_stdin()
                self._timed_out.add(pid)
                self._codes[pid] = "start_timeout"

    def _retry_failed_binds(self, projects: tuple[registry.Project, ...]) -> None:
        """A bind that failed is tried once more on port 0; the registry keeps its port (4.1.4)."""
        for project in projects:
            pid = project.project_id
            seen = self._seen(project)
            last = self._last.get(pid)
            refused = (seen.own is not None and seen.own.poll() is not None and seen.fresh
                       and seen.record is not None and seen.record.state == "refused"
                       and seen.record.code == "bind_failed")
            if refused and last is not None and pid not in self._retried and last["port"] != 0:
                self._retried.add(pid)
                self._launch(project, mode=last["mode"], transition=last["transition"],
                             auto_continue=last["auto_continue"], port=0, retry=True)
