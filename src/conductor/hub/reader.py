"""The reading loop: one pass over every running child, once a second (spec 4.1.9, 4.5.6).

`ChildReader.step()` looks at each registered project; for the ones whose child runs it keeps one
event stream open (a frame is only a signal) and reads the child again when a signal came a second
ago, when the child is a new process, or when 30 s went by. A pass is a `child_client.read_cycle`
made into rows (`summary.live_from_cycle`) and then acted on:

- the pass is remembered as the project's live data, and the page is told with a `project` frame;
- a COMPLETE pass is offered to the snapshot store (which writes only what changed, at most once in
  5 s); an incomplete one writes nothing;
- the continue-after flag it read puts the project on the queue of projects or takes it off
  (4.3.4), the flags of one step in the order they were set;
- the quotas it read, if the project is the ACTIVE one, go to `limits.json` and a `limits` frame.

A project whose child is gone loses its live data (its last snapshot stays) and its stream.
Nothing here writes to a child or to the registry. The loop that calls `step()` belongs to the hub.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from conductor.hub import (
    child_client, events, instance, registry, snapshots, state, summary, supervisor)

READ_DELAY_SECONDS = 1.0
CONTROL_SECONDS = 30.0
_INSTANT = "%Y-%m-%dT%H:%M:%SZ"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _Stream:
    port: int
    instance: str
    stop: threading.Event
    thread: threading.Thread | None


class ChildReader:
    """The live data of the running children, and the acts each pass of them causes."""

    def __init__(self, home, sup: supervisor.Supervisor, store: state.HubStateStore,
                 snapshot_store: snapshots.SnapshotStore, ledger: summary.ObservedLedger,
                 bus: events.EventBus, *, hub_origin: str,
                 now: Callable[[], datetime] = _utc_now,
                 monotonic: Callable[[], float] = time.monotonic,
                 follow: Callable[..., object] | None = child_client.ChildEvents,
                 read: Callable[..., child_client.Cycle] = child_client.read_cycle,
                 client: Callable[..., child_client.ChildClient] = child_client.ChildClient
                 ) -> None:
        self._home, self._sup, self._store = home, sup, store
        self._snapshots, self._ledger, self._bus = snapshot_store, ledger, bus
        self._origin, self._now, self._monotonic = hub_origin, now, monotonic
        self._follow, self._read, self._client = follow, read, client
        self._lock = threading.RLock()
        self._live: dict[str, summary.Live] = {}
        self._instance: dict[str, str] = {}
        self._dirty: dict[str, float] = {}
        self._next_control: dict[str, float] = {}
        self._streams: dict[str, _Stream] = {}

    # -- what the rest of the hub reads -------------------------------------------------------

    def live(self, project_id: str) -> summary.Live | None:
        """The last pass over a project's running child, or `None` when its child is not read."""
        with self._lock:
            return self._live.get(project_id)

    def mark(self, project_id: str) -> None:
        """A child signalled: read it again a second from now (a signal already waiting stands)."""
        with self._lock:
            self._dirty.setdefault(project_id, self._monotonic() + READ_DELAY_SECONDS)

    def close(self) -> None:
        """Stop every stream; the live data is left as it is."""
        with self._lock:
            for project_id in list(self._streams):
                self._stop_stream(project_id)

    # -- one pass ----------------------------------------------------------------------------

    def step(self) -> None:
        """Read what is due and forget what has gone; see the module text."""
        try:
            projects = registry.load(self._home).projects
        except registry.RegistryError:
            return
        now, read = self._monotonic(), []
        for project in projects:
            found = self._running(project)
            if found is None:
                self._forget(project.project_id)
                continue
            port, token = found
            self._keep_stream(project.project_id, port, token)
            if self._due(project.project_id, token, now):
                read.append(self._read_project(project, port, token, now))
        for project_id in [p for p in self._live if p not in {q.project_id for q in projects}]:
            self._forget(project_id)
        self._move_flags([one for one in read if one is not None])

    def _running(self, project: registry.Project) -> tuple[int, str] | None:
        try:
            status = self._sup.status(project.project_id)
        except supervisor.SupervisorRefused:
            return None
        if status.lifecycle.state != "running" or not status.port or not status.instance:
            return None
        return status.port, status.instance

    def _due(self, project_id: str, token: str, now: float) -> bool:
        with self._lock:
            if self._instance.get(project_id) != token:
                return True
            due = self._dirty.get(project_id)
            return (due is not None and now >= due) or now >= self._next_control.get(
                project_id, 0.0)

    def _read_project(self, project: registry.Project, port: int, token: str, now: float
                      ) -> tuple[str, dict[str, Any] | None] | None:
        pid = project.project_id
        status = self._sup.status(pid)
        with self._lock:
            previous = self._live.get(pid)
        memory = {} if previous is None else previous.cycle.memory
        cycle = self._read(self._client(port, pid), hub_origin=self._origin, mode=status.mode,
                           previous=memory)
        taken = self._now().astimezone(timezone.utc).strftime(_INSTANT)
        live = summary.live_from_cycle(pid, cycle, self._ledger, taken)
        with self._lock:
            self._live[pid], self._instance[pid] = live, token
            self._dirty.pop(pid, None)
            self._next_control[pid] = now + CONTROL_SECONDS
        self._after(pid, live)
        self._bus.publish("project", project_id=pid)
        flag_read = cycle.verdict == "live" and "auto_continue" not in cycle.failures
        return (pid, cycle.auto_continue) if flag_read else None

    def _after(self, project_id: str, live: summary.Live) -> None:
        cycle = live.cycle
        if cycle.complete:
            self._snapshots.put(project_id, taken_at=live.taken_at, tasks=list(live.rows),
                                task_queue=cycle.queue, auto_continue=cycle.auto_continue,
                                quotas=cycle.quotas)
        try:
            active = self._store.load().active_project_id
        except state.HubStateError:
            return
        if project_id == active and cycle.verdict == "live" and cycle.quotas is not None:
            self._snapshots.put_limits(project_id, taken_at=live.taken_at, quotas=cycle.quotas)
            self._bus.publish("limits")

    def _move_flags(self, flags: list[tuple[str, dict[str, Any] | None]]) -> None:
        """Put the projects that read a standing flag on the queue, and take the others off."""
        standing = sorted(((_set_at(flag), pid, flag["flag_id"]) for pid, flag in flags
                           if _stands(flag)), key=lambda one: (one[0], one[1]))
        gone = [pid for pid, flag in flags if not _stands(flag)]
        try:
            for _, pid, flag_id in standing:
                self._store.update(lambda s, p=pid, f=flag_id: state.enqueue(s, p, f))
            for pid in gone:
                self._store.update(lambda s, p=pid: state.dequeue(s, p))
        except (state.HubStateError, instance.HubLockLost):
            return

    # -- streams and the forgetting of what has gone -------------------------------------------

    def _keep_stream(self, project_id: str, port: int, token: str) -> None:
        if self._follow is None:
            return
        with self._lock:
            held = self._streams.get(project_id)
            if held is not None and (held.port, held.instance) == (port, token):
                return
            self._stop_stream(project_id)
            stop = threading.Event()
            events_client = self._follow(port, project_id, lambda: self.mark(project_id))
            thread = threading.Thread(target=events_client.follow, args=(stop,), daemon=True,
                                      name=f"hub-events-{project_id[:8]}")
            self._streams[project_id] = _Stream(port, token, stop, thread)
            thread.start()

    def _stop_stream(self, project_id: str) -> None:
        held = self._streams.pop(project_id, None)
        if held is not None:
            held.stop.set()

    def _forget(self, project_id: str) -> None:
        """The child is gone: its live data and stream go, its snapshot stays."""
        with self._lock:
            self._stop_stream(project_id)
            had = self._live.pop(project_id, None)
            self._instance.pop(project_id, None)
            self._dirty.pop(project_id, None)
            self._next_control.pop(project_id, None)
        if had is not None:
            self._bus.publish("project", project_id=project_id)


def _stands(flag: object) -> bool:
    return (isinstance(flag, dict) and flag.get("enabled") is True and flag.get("consumed") is None
            and isinstance(flag.get("flag_id"), str))


def _set_at(flag: dict[str, Any]) -> str:
    moment = flag.get("set_at")
    return moment if isinstance(moment, str) else ""
