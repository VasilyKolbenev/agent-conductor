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
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page, expect

from browser_tests.desk_identity import identify
from browser_tests.hub_bench import lang, watch  # noqa: F401
from browser_tests.test_hub_page_reads import RAIL
from conductor import server as desk_server
from conductor.hub import reader, server, service, snapshots, summary
from conductor.hub.assets import HUB_ASSETS
from tests._hub_fake_child import FakeChild, serve_standard, task_row
from tests._hub_stack import Mono, request
from tests._hub_world import PIDS, World, id_of

NAMES = ("a", "b", "c")
ACTIVATE = "/hub/projects/{}/activate"
DOORS = {"/hub/session", "/hub/projects", "/hub/limits", "/hub/setup", "/hub/events"}
#: What a browser asks of any page by itself and the hub answers with a refusal.
BROWSER_OWN = {"/favicon.ico"}


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
        self.desks: list[tuple[desk_server.ConductServer, threading.Thread]] = []

    # -- what a test arranges ---------------------------------------------------------------------

    @staticmethod
    def project_id(name: str) -> str:
        """The id of the registered project called `name` (`a`, `b` or `c`)."""
        return id_of(name)

    def child(self, name: str, *, tasks: list[dict] | None = None,
              runs: list[dict] | None = None, mode: str = "active",
              automations: dict[str, dict] | None = None) -> FakeChild:
        """A fake child of the project `name` that names this hub as its own and answers a cycle."""
        child = FakeChild(id_of(name), mode=mode, hub_origin=self.origin)
        serve_standard(child, tasks if tasks is not None else [task_row("task-1", "Fix payment")],
                       runs if runs is not None else [], automations=automations)
        self.children.append(child)
        return child

    def desk(self, name: str, root: Path, *, mode: str = "active") -> int:
        """Serve `root` as the desk of the project `name`, naming THIS hub as its own; its port.

        A real desk server, identified as the project (D1's `identify`), so the hub reads it as it
        reads a child and a page framing it is admitted by its frame policy.
        """
        httpd = desk_server.build(root, 0, hub_origin=self.origin)
        identify(httpd, id_of(name), hub_origin=self.origin, mode=mode)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.desks.append((httpd, thread))
        return int(httpd.server_address[1])

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
        for httpd, thread in self.desks:
            httpd.shutdown()
            thread.join(timeout=5)
            httpd.server_close()
        self.reader.close()
        self.server.shutdown()
        self.server.server_close()
        self.world.close()


# -- the page on the real hub: fixtures and helpers the test modules share -----------------------------

A, B, C = (id_of(name) for name in NAMES)


@dataclass
class LivePage:
    """One page on the real hub, in one language, with what it asked and what it logged."""

    page: Page
    live: LiveHub
    problems: list[str]
    asked: list[tuple[str, str]] = field(default_factory=list)
    #: The port of the desk a test runs as project `a` (0 until it does).
    port: int = 0

    def reads(self, path: str) -> int:
        return self.asked.count(("GET", path))

    def writes(self) -> list[str]:
        return [path for method, path in self.asked if method == "POST"]


@pytest.fixture
def live(tmp_path: Path) -> Iterator[LiveHub]:
    """The real hub over the world of fakes: three registered projects and no process."""
    made = LiveHub(tmp_path)
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def live_page(chromium: Browser, live: LiveHub, lang: str) -> Iterator[LivePage]:
    """The hub's page opened on the real hub, in one language."""
    context = chromium.new_context(viewport={"width": 1300, "height": 1000}, locale=lang)
    try:
        page = context.new_page()
        page.set_default_timeout(8000)
        opened = LivePage(page, live, watch(page))
        foreign: list[str] = []

        def noted(one) -> None:
            """What the page itself asked: a desk in its frame asks its own server, not the hub's."""
            if one.frame.parent_frame is not None:
                return
            opened.asked.append((one.method, urlsplit(one.url).path))
            if not one.url.startswith(live.origin):
                foreign.append(one.url)

        page.on("request", noted)
        page.goto(f"{live.origin}/#lang={lang}", wait_until="load")
        yield opened
        assert opened.problems == []
        assert page.evaluate("window.__violations") == []
        allowed = {"/", *HUB_ASSETS, *DOORS, *BROWSER_OWN}
        strays = {path for method, path in opened.asked
                  if method == "GET" and path not in allowed}
        assert strays == set(), "the page asked for something the hub does not list"
        assert foreign == [], "the page itself asked another origin for something"
    finally:
        context.close()


def ready(one: LivePage) -> None:
    expect(one.page.locator("#hubShell")).to_have_attribute("data-state", "ready")


def press(one: LivePage, key: str) -> None:
    one.page.locator(f'[data-focus="{key}"]').click()


def wait_for(one: LivePage, what: str, condition, seconds: float = 8.0):
    """Poll the page's own rail until `condition(facts)` holds; the facts are returned."""
    facts = None
    for _ in range(int(seconds * 20)):
        facts = one.page.evaluate(RAIL)
        if condition(facts):
            return facts
        one.page.wait_for_timeout(50)
    raise AssertionError(f"timed out waiting for {what}: {facts}")


def wait_reads(one: LivePage, path: str, count: int) -> None:
    """Wait until the page has read `path` at least `count` times: the stream's first frame is
    `projects`, and the page reads again on it, so the second read of the projects is that frame's."""
    for _ in range(160):
        if one.reads(path) >= count:
            return
        one.page.wait_for_timeout(50)
    raise AssertionError(f"{path} was read {one.reads(path)} times, not {count}")


def line_of(facts: dict, project_id: str) -> dict:
    return next(row for row in facts["projects"] if row["id"] == project_id)
