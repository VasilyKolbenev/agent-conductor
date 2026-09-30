"""The REAL hub as a bench for the hub page's browser tests (not a test module).

`hub_bench.py` is a fake hub that answers the contract fixtures. This is the other half of the
same promise: the page against the hub that lane H wrote. It builds the parts `tests/_hub_stack.py`
builds (the real `HubServer` with its transport checks, its CSP, its routes and its stream, the real
`HubService`, the real `ChildReader`, the real supervisor and registry) over the same world of fakes
(`tests/_hub_world.py`: three registered projects `a`, `b`, `c`, a spawner that starts no process, a
clock that moves when told), with ONE difference that a page needs and `Stack` does not give: the
reader's `hub_origin` is the server's real origin, so a desk that names this hub as its own is read
as this hub's child, and a frame policy built from it admits this hub's page.

A child is a `FakeChild` socket (or, for the frame tests, a real desk server); `run_project` puts a
status file on disk exactly as a child would and marks its process alive, and `tick` makes one pass
of the hub's loop by hand (no thread, so what the page reads is what the test has arranged).
Everything the page asks is written down by the page's own `request` event in the test, because the
hub's real surface answers a path it does not serve with a refusal and not with a fault list.
"""
from __future__ import annotations

import threading
from pathlib import Path

from conductor.hub import reader, server, service, snapshots, summary
from tests._hub_fake_child import FakeChild, serve_standard, task_row
from tests._hub_stack import Mono, request
from tests._hub_world import PIDS, World, id_of

NAMES = ("a", "b", "c")
ACTIVATE = "/hub/projects/{}/activate"


class LiveHub:
    """The hub's whole stack over the fake world, with a real socket in front."""

    def __init__(self, tmp_path: Path) -> None:
        self.world = World(tmp_path)
        self.mono = Mono()
        self.server = server.HubServer(0)
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"
        self.snapshots = snapshots.SnapshotStore(self.world.home, clock=self.mono)
        self.ledger = summary.ObservedLedger()
        self.reader = reader.ChildReader(
            self.world.home, self.world.supervisor, self.world.store, self.snapshots,
            self.ledger, self.server.bus, hub_origin=self.origin, now=self.world.clock,
            monotonic=self.mono, follow=None)
        self.service = service.HubService(
            self.world.home, self.world.supervisor, self.world.store, self.snapshots,
            self.reader, self.ledger, self.server.bus, now=self.world.clock,
            verify_tool=lambda tool, **_kw: (_ for _ in ()).throw(
                AssertionError("no tool is verified here")),
            job_policy=lambda: "none", folder_ok=lambda project: True)
        self.server.attach(self.service)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.children: list[FakeChild] = []

    # -- what a test arranges ---------------------------------------------------------------------

    @staticmethod
    def project_id(name: str) -> str:
        """The id of the registered project called `name` (`a`, `b` or `c`)."""
        return id_of(name)

    def child(self, name: str, *, tasks: list[dict] | None = None,
              runs: list[dict] | None = None, mode: str = "active") -> FakeChild:
        """A fake child of the project `name` that names this hub as its own and answers a cycle."""
        child = FakeChild(id_of(name), mode=mode, hub_origin=self.origin)
        serve_standard(child, tasks if tasks is not None else [task_row("task-1", "Fix payment")],
                       runs if runs is not None else [])
        self.children.append(child)
        return child

    def run_project(self, name: str, port: int, *, mode: str = "active") -> None:
        """The project's child serves on `port` and its process lives (what `conduct up` leaves)."""
        self.world.alive.add(PIDS[name])
        self.world.put_status(name, "serving", mode=mode, port=port)

    def tick(self, seconds: float = 1.1) -> None:
        """One pass of the hub's loop, `seconds` of the reader's clock later."""
        self.mono.advance(seconds)
        self.service.tick()

    def post(self, target: str) -> int:
        """A write made the way the page makes it, for a test that arranges state by the hub's door."""
        token = request(self.port, "GET", "/hub/session").json()["csrf_token"]
        return request(self.port, "POST", target, body=b"{}", headers={
            "Origin": self.origin, "X-Conduct-CSRF": token,
            "Content-Type": "application/json"}).status

    def close(self) -> None:
        for child in self.children:
            child.close()
        self.reader.close()
        self.server.shutdown()
        self.server.server_close()
        self.world.close()
