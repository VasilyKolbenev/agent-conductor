"""A fake hub for the hub page's browser tests: the contract fixtures under the hub's own CSP.

The page is served exactly as the hub will serve it: `GET /` answers `hub.html`, `/hub/<name>`
answers the files of `HUB_ASSETS` and nothing else, and every response carries the policy of spec
4.6.2 (no inline script or style, frames only of a loopback address, no other origin), so a page
that needs anything the policy forbids fails here and not on the owner's machine. The GET routes
answer the fixtures of `tests/fixtures/hub/` (one response per route, as lane H's contract wrote
them), each replaceable by a test; `GET /hub/events` is a live stream a test pushes frames into;
every POST is checked as the hub checks it (the CSRF token of `GET /hub/session`, an exact Origin, a
JSON body) and recorded, then answered with what the test configured. Nothing here is a child's
server: the page reads no `/command/*` path, and a request for one is recorded as a fault.

Not a test module: pytest does not collect it (no `test_` prefix). The fixtures live here and each
test file imports them, because the conftest's surface is pinned by a guard.
"""
from __future__ import annotations

import copy
import json
import queue
import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from conductor.hub.assets import HUB_ASSETS

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "hub"
#: The policy the hub puts on every response (spec 4.6.2).
CSP = ("default-src 'self'; frame-src http://127.0.0.1:*; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'none'; object-src 'none'")
#: The GET routes that answer a fixture, by path.
FIXTURE_ROUTES = {"/hub/projects": "hub_projects.json", "/hub/limits": "hub_limits.json",
                  "/hub/setup": "hub_setup.json", "/hub/session": "hub_session.json"}
POST_ROUTE = re.compile(r"^/hub/(?:projects/[0-9a-f]{32}/(?:activate|view|stop|recover|forget|"
                        r"providers)|queue/order|logins/[0-9a-f]{64}/recover)$")
KEEPALIVE_SECONDS = 0.2


def fixture(name: str) -> dict[str, Any]:
    """The body of one contract fixture: the response it gives, parsed."""
    document = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return document["response"] if "response" in document else document


class FakeHub:
    """One running fake hub: its address, what it answered, what it was asked, and its stream."""

    def __init__(self) -> None:
        self.answers: dict[str, tuple[int, Any]] = {
            path: (200, fixture(name)) for path, name in FIXTURE_ROUTES.items()}
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []
        self.faults: list[str] = []
        self.refusals: dict[str, tuple[int, dict[str, Any]]] = {}
        self.stream: queue.Queue[bytes | None] = queue.Queue()
        self.streams_opened = 0
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(self))
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stream.put(None)
        self.server.shutdown()
        self.server.server_close()

    def answer(self, path: str, body: Any, status: int = 200) -> None:
        """Replace what a GET route answers (a test's own copy of a fixture, or a refusal)."""
        with self.lock:
            self.answers[path] = (status, copy.deepcopy(body))

    def refuse(self, path: str, status: int, code: str) -> None:
        """Make a POST path answer a hub refusal, the envelope of spec 4.6.2."""
        body = {"error": {"code": code, "message": "", "detail": None}}
        with self.lock:
            self.refusals[path] = (status, body)

    def push(self, frame: dict[str, Any]) -> None:
        """Send one frame down the open stream (an id, never a fact: spec 4.6.4)."""
        self.stream.put(f"data: {json.dumps(frame)}\n\n".encode())

    def requests(self, path: str) -> int:
        """How many times a GET path was asked."""
        return self.gets.count(path)


def _handler(hub: FakeHub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            return

        def _send(self, status: int, body: bytes, kind: str, extra: dict[str, str] | None = None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, body: Any) -> None:
            self._send(status, json.dumps(body).encode(), "application/json")

        def _refuse(self, status: int, code: str) -> None:
            self._json(status, {"error": {"code": code, "message": "", "detail": None}})

        def do_GET(self) -> None:  # noqa: N802 (the method name the server calls)
            path = self.path
            with hub.lock:
                hub.gets.append(path)
            if path.startswith("/command"):
                hub.faults.append(f"the page asked a child's path: {path}")
            if path == "/":
                self._send(200, (PANEL / "hub.html").read_bytes(), "text/html; charset=utf-8")
            elif path in {route for route in HUB_ASSETS}:
                kind, name = HUB_ASSETS[path]
                self._send(200, (PANEL / name).read_bytes(), kind)
            elif path == "/hub/events":
                self._events()
            elif path in hub.answers:
                status, body = hub.answers[path]
                self._json(status, body)
            else:
                hub.faults.append(f"a path the hub does not serve: {path}")
                self._refuse(404, "route_not_found")

        def _events(self) -> None:
            hub.streams_opened += 1
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            try:
                self.wfile.write(b'data: {"kind": "projects"}\n\n')
                self.wfile.flush()
                while True:
                    try:
                        frame = hub.stream.get(timeout=KEEPALIVE_SECONDS)
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        continue
                    if frame is None:
                        return
                    self.wfile.write(frame)
                    self.wfile.flush()
            except OSError:
                return

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            token = hub.answers["/hub/session"][1]["csrf_token"]
            ok = (self.headers.get("Origin") == hub.url
                  and self.headers.get("X-Conduct-CSRF") == token
                  and self.headers.get("Content-Type") == "application/json")
            if not POST_ROUTE.match(self.path):
                self._refuse(404, "route_not_found")
            elif not ok:
                hub.faults.append(f"a POST the hub would refuse: {self.path}")
                self._refuse(403, "csrf_denied")
            else:
                body = json.loads(raw or b"{}")
                hub.posts.append({"path": self.path, "body": body})
                if self.path in hub.refusals:
                    status, answer = hub.refusals[self.path]
                    self._json(status, answer)
                else:
                    self._json(202, {"project_id": self.path.split("/")[3]
                                     if self.path.startswith("/hub/projects/") else None})

    return Handler


class HubPage:
    """One page on the fake hub, in one language, with its problem log."""

    def __init__(self, page: Page, hub: FakeHub, problems: list[str]) -> None:
        self.page = page
        self.hub = hub
        self.problems = problems


def say(page: HubPage, key: str, **params: str) -> str:
    """A message of the page's own catalogue, in the language the page is in."""
    return page.page.evaluate("""async ([key, params]) => {
      const copy = await import("/hub/hub-copy.js");
      return copy.hubText(document.documentElement.lang, key, params);
    }""", [key, params])


def short(page: HubPage, iso: str) -> str:
    """The short text of an instant, in the page's language and zone."""
    return page.page.evaluate("""async (iso) => (await import("/hub/desk-time.js"))
      .instantText(document.documentElement.lang, iso).short""", iso)


def ready(page: HubPage) -> None:
    """Wait until the page has read the hub once and says so."""
    expect(page.page.locator("#hubShell")).to_have_attribute("data-state", "ready")


def fields(hash_text: str) -> dict[str, str]:
    """The key and value pairs of an address hash."""
    return dict(part.split("=", 1) for part in hash_text.lstrip("#").split("&") if part)


def watch(page: Page) -> list[str]:
    """Every error the page raised or logged, and every violation of the hub's own policy."""
    problems: list[str] = []

    def heard(message: Any) -> None:
        #: The browser logs a refusal it was sent on purpose (a write the hub refuses, a read a
        #: test made fail); any other error is a problem.
        sent = "Failed to load resource" in message.text and any(
            f"status of {code}" in message.text for code in (409, 500))
        if message.type == "error" and not sent:
            problems.append(message.text)

    page.on("console", heard)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.add_init_script("""
      window.__violations = [];
      document.addEventListener("securitypolicyviolation", (event) => {
        window.__violations.push(event.violatedDirective + " " + event.blockedURI);
      });
    """)
    return problems


@pytest.fixture(params=["en", "ru"])
def lang(request: pytest.FixtureRequest) -> str:
    """The reader's language: every test of the page is run in both."""
    return str(request.param)


@pytest.fixture
def hub() -> Iterator[FakeHub]:
    """A fake hub over the contract fixtures."""
    started = FakeHub()
    started.start()
    try:
        yield started
    finally:
        started.stop()


@pytest.fixture
def hub_page(chromium: Browser, hub: FakeHub, lang: str) -> Iterator[HubPage]:
    """The hub's page, opened in one language, on the fake hub."""
    context = chromium.new_context(viewport={"width": 1300, "height": 1000}, locale=lang)
    try:
        page = context.new_page()
        page.set_default_timeout(8000)
        problems = watch(page)
        page.goto(f"{hub.url}/#lang={lang}", wait_until="load")
        opened = HubPage(page, hub, problems)
        yield opened
        assert problems == []
        assert hub.faults == []
        assert page.evaluate("window.__violations") == []
    finally:
        context.close()
