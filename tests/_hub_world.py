"""The world a supervisor watches, made of fakes: for `test_hub_supervisor.py` (not a test file).

A hub's folder with three registered projects (`a`, `b`, `c`, whose ids are 32 of that letter), a
clock that moves when told, a table of which pids are alive and of what each project's ownership
head reads, a spawner that starts no process and records how it was asked, and helpers that put
a status file on disk exactly as a child would write it. Nothing here is the supervisor's own:
the supervisor is built over it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conductor.hub import instance, registry, spawn, state, supervisor
from conductor.ownership_errors import OwnerRefused

START = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
PIDS = {"a": 101, "b": 202, "c": 303}


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def id_of(name: str) -> str:
    return name[0] * 32


class Clock:
    """A clock that moves only when it is told to."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class FakeChild:
    """A child that is a record of what was asked of it."""

    def __init__(self, **arguments) -> None:
        self.arguments, self.closed, self.code = arguments, False, None
        self.project_id, self.mode = arguments["project_id"], arguments["mode"]

    def poll(self):
        return self.code

    def close_stdin(self) -> None:
        self.closed = True

    def leave(self, code: int = 0) -> None:
        self.code = code


class FakeSpawner:
    """Starts nothing: records each start, and can be told that no start is possible."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.children: list[FakeChild] = []
        self.refusal: spawn.SpawnRefused | None = None
        self.before_start = None             # called with the arguments just before a start

    def require_startable(self) -> None:
        if self.refusal is not None:
            raise self.refusal

    def start(self, **arguments) -> FakeChild:
        self.require_startable()
        if self.before_start is not None:
            self.before_start(arguments)
        self.calls.append(arguments)
        child = FakeChild(**arguments)
        self.children.append(child)
        return child

    def started(self, name: str) -> list[dict]:
        return [call for call in self.calls if call["project_id"] == id_of(name)]


class World:
    """A hub's folder, three projects, and the supervisor over them."""

    def __init__(self, tmp_path: Path, *, hub_port: int = 7700) -> None:
        self.home = tmp_path / "home"
        self.clock = Clock()
        self.alive: set[int] = set()
        self.heads: dict[str, str | None] = {}
        self.unreadable: set[str] = set()          # projects whose head cannot be read
        self.nonces: dict[str, str] = {}           # a head that belongs to another activation
        self.spawner = FakeSpawner()
        self.hub = instance.HubInstance.acquire(self.home)
        self.store = state.HubStateStore(self.home, self.hub)
        self.hub_port = hub_port
        self.roots: dict[str, str] = {}
        for number, name in enumerate("abc", start=1):
            root = str(tmp_path / "projects" / name)
            self.roots[name] = root
            registry.add_project(project_id=id_of(name), root=root, root_identity=(number, 1),
                                 name=name, folder=self.home, now=iso(START))
            self.heads[name] = "closed"
        self.ids = (str(uuid.UUID(int=number)) for number in range(1, 10_000))
        self.supervisor = self.new_supervisor(self.spawner)

    def new_supervisor(self, spawner: FakeSpawner) -> supervisor.Supervisor:
        return supervisor.Supervisor(
            self.home, self.store, spawner, hub_port=self.hub_port, clock=self.clock,
            probe=self._probe, head_of=self._head_of, new_id=lambda: next(self.ids))

    def close(self) -> None:
        self.hub.close()

    # -- what the fakes answer --------------------------------------------------------------

    def _probe(self, pid: int, started: str | None) -> str:
        return "alive" if pid in self.alive else "dead"

    def _head_of(self, root):
        name = next(n for n, known in self.roots.items() if known == str(root))
        if name in self.unreadable:
            raise OwnerRefused("ownership_lost", "the ownership head cannot be read")
        if self.heads[name] is None:               # a project that was never activated
            return root, None
        return root, {"phase": self.heads[name], "nonce": self.nonces.get(name, id_of(name))}

    # -- what a child leaves on disk ----------------------------------------------------------

    def put_status(self, name: str, status: str, *, mode: str = "active", code: str | None = None,
                   at: datetime | None = None, port: int | None = None,
                   started: str | None = "windows:1") -> None:
        folder = self.home / "run"
        folder.mkdir(parents=True, exist_ok=True)
        record = {"schema_version": 1, "project_id": id_of(name), "pid": PIDS[name],
                  "process_started": started, "port": 7701 if port is None else port,
                  "mode": mode, "state": status, "code": code, "drain_deadline": None,
                  "updated_at": iso(at or self.clock.now)}
        (folder / f"{id_of(name)}.json").write_text(json.dumps(record), encoding="utf-8")

    def running(self, name: str, *, mode: str = "active") -> None:
        """The project's child is serving and its process lives."""
        self.alive.add(PIDS[name])
        self.put_status(name, "serving", mode=mode)

    def gone(self, name: str, status: str = "stopped", *, head: str = "closed",
             code: str | None = None) -> None:
        """The project's process has left, with this last word, leaving its head as given."""
        self.alive.discard(PIDS[name])
        self.heads[name] = head
        self.put_status(name, status, code=code)
        for child in self.spawner.children:
            if child.project_id == id_of(name) and child.code is None:
                child.leave(0)

    # -- reading back ----------------------------------------------------------------------------

    def hub_state(self) -> state.HubState:
        return self.store.load()
