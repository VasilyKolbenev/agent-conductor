"""The hub's HTTP shell: transport checks, the route table, assets and the event stream (spec 4.6).

Everything about WHICH route a request names is `routes`, everything about WHAT it answers is
`HubService`; this module only carries a request from one to the other and writes the answer.
Every request meets the same gates in the same order:

1. the Host (exactly `127.0.0.1:<hub>`, for every method, before any route: `localhost:<hub>` is
   `403 same_origin_denied` and the refusal names the address that works);
2. the route (`route_not_found` / `method_not_allowed`, no query, no redirect, no proxying);
3. for a write: Origin, the hub's CSRF token, `Content-Type: application/json`, one JSON object of
   at most 64 KiB (the commands' own checks over the hub's one host), then the keys of the body
   (a place on disk at any depth, or a key the row does not take, is `contract_invalid`);
4. the handler, whose refusals are of the closed list of `refusals`.

The Content-Security-Policy of the hub is written by the one `end_headers` of `KeptConnection` on
every answer, the event stream and `send_error` included; there is no CORS header anywhere. A route
of `HUB_ROUTES` that has no handler yet (`LIVE_ROUTES` says which have) answers `route_not_found`.
"""
from __future__ import annotations

import importlib.resources
import os
import secrets
import socketserver
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from conductor.command.contracts import canonical_json
from conductor.command.http_transport import HttpRefusal
from conductor.hub import events, routes
from conductor.hub.assets import HUB_ASSETS
from conductor.hub.refusals import HubRefusal
from conductor.hub.service import HubService
from conductor.hub.session import HubSession
from conductor.http_framing import KeptConnection

HUB_CSP = ("default-src 'self'; frame-src http://127.0.0.1:*; frame-ancestors 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
PAGE = "hub.html"
PING_EVERY = 15
_JSON = "application/json; charset=utf-8"

_GET: dict[str, Callable[[HubService], tuple[int, Any]]] = {
    "/hub/projects": lambda service: (200, service.projects()),
    "/hub/limits": lambda service: (200, service.limits()),
    "/hub/setup": lambda service: (200, service.setup()),
    "/hub/github/status": lambda service: (200, service.github_status()),
    "/hub/github/repos": lambda service: (200, service.github_repos()),
}
_POST: dict[str, Callable[[HubService, dict, dict], tuple[int, Any]]] = {
    "/hub/setup/projects-home": lambda service, _params, body: service.projects_home(body),
    "/hub/dialogs/folder": lambda service, _params, body: service.folder_dialog(body),
    "/hub/dialogs/<pick_id>/cancel":
        lambda service, params, _body: service.cancel_dialog(params["pick_id"]),
    "/hub/projects": lambda service, _params, body: service.add_project(body),
    "/hub/operations/<operation_id>/cancel":
        lambda service, params, _body: service.cancel_operation(params["operation_id"]),
    "/hub/projects/<project_id>/activate":
        lambda service, params, _body: service.activate(params["project_id"]),
    "/hub/projects/<project_id>/view":
        lambda service, params, _body: service.view(params["project_id"]),
    "/hub/projects/<project_id>/stop":
        lambda service, params, _body: service.stop(params["project_id"]),
    "/hub/projects/<project_id>/forget":
        lambda service, params, _body: service.forget(params["project_id"]),
    "/hub/projects/<project_id>/recover":
        lambda service, params, _body: service.recover(params["project_id"]),
    "/hub/queue/order": lambda service, _params, body: service.queue_order(body["order"]),
}
#: The rows of `HUB_ROUTES` this build answers, as (method, path). The others are `route_not_found`.
LIVE_ROUTES = frozenset(
    {("GET", "/"), ("GET", routes.ASSET_PATH), ("GET", "/hub/session"),
     ("GET", "/hub/events"), ("GET", "/hub/operations/<operation_id>"),
     ("GET", "/hub/dialogs/<pick_id>"), ("GET", "/hub/github/repos/<owner>")}
    | {("GET", path) for path in _GET} | {("POST", path) for path in _POST})


class HubBindError(OSError):
    """The port could not be bound (`hub_bind_failed`); nothing else in the start raises this."""


class HubServer(ThreadingHTTPServer):
    """The listening socket on `127.0.0.1:<port>`, the session and the clients of the stream."""

    daemon_threads = True
    # Windows lets a second bind hijack a live port when the address is reusable.
    allow_reuse_address = os.name != "nt"

    def __init__(self, port: int, *, token_factory: Callable[[int], str] = secrets.token_urlsafe
                 ) -> None:
        self.bus = events.EventBus()
        self.shutting_down = False
        self.service: HubService | None = None
        super().__init__(("127.0.0.1", port), HubHandler)
        self.session = HubSession.mint(self.server_address[1], token_factory)

    def server_bind(self) -> None:
        """Bind, and name the server by its literal (no reverse lookup of a loopback address)."""
        try:
            socketserver.TCPServer.server_bind(self)
        except OSError as error:
            raise HubBindError(*error.args) from error
        self.server_name, self.server_port = self.server_address[:2]

    @property
    def content_security_policy(self) -> str:
        """The policy of every answer of the hub: built once, never changed."""
        return HUB_CSP

    def attach(self, service: HubService) -> None:
        """Give the server the service it answers with (built once the port is known)."""
        self.service = service

    def shutdown(self) -> None:
        """Stop serving and wake every waiting stream."""
        self.shutting_down = True
        self.bus.wake_all()
        if self.service is not None:
            self.clone_shutdown_proven = self.service.close_operations()
            self.service.close_dialog()
        super().shutdown()
        if getattr(self, "clone_shutdown_proven", True) is False:
            print("conduct hub: clone retirement unproven; recovery record retained", file=sys.stderr)

    def handle_error(self, request: object, client_address: object) -> None:
        """A client that vanished is not an error worth a traceback."""
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


class HubHandler(KeptConnection, BaseHTTPRequestHandler):
    """One request of the hub."""

    server: HubServer
    _body_read = False

    def do_GET(self) -> None:  # noqa: N802
        self._serve("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._serve("POST")

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve("HEAD")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._serve("OPTIONS")

    def do_PUT(self) -> None:  # noqa: N802
        self._serve("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._serve("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._serve("DELETE")

    def do_TRACE(self) -> None:  # noqa: N802
        self._serve("TRACE")

    def do_CONNECT(self) -> None:  # noqa: N802
        self._serve("CONNECT")

    def log_message(self, format: str, *args: object) -> None:
        """No line per request on stderr."""

    def send_error(self, code: int, message: str | None = None,
                   explain: str | None = None) -> None:
        """A method with no handler is answered by the route table, not by a page of HTML."""
        if code == 501 and getattr(self, "path", None) is not None:
            self._serve(getattr(self, "command", "") or "")
            return
        super().send_error(code, message, explain)

    # -- one request -----------------------------------------------------------------------------

    def _serve(self, method: str) -> None:
        head = method == "HEAD"
        self._body_read = False
        try:
            self.server.session.check_host(self.headers.raw_items())
            matched = routes.match(method, self.path)
            if method == "POST":
                self._post(matched)
            else:
                self._get(matched)
        except HubRefusal as refusal:
            self._refuse(refusal, head=head)
        except HttpRefusal as refusal:
            self._refuse(self._transport(refusal), head=head)

    def _transport(self, refusal: HttpRefusal) -> HubRefusal:
        """The commands' transport refusal, as the hub's; a wrong Host names the right address."""
        if refusal.code == "same_origin_denied":
            return HubRefusal("same_origin_denied", {"address": self.server.session.origin})
        return HubRefusal(refusal.code)

    def _refuse(self, refusal: HubRefusal, *, head: bool = False) -> None:
        if self.command == "POST" and not self._body_read and not self.close_connection:
            self._drain_refused_body()
        self._send_body(refusal.status, _JSON, canonical_json(refusal.as_dict()).encode("utf-8"),
                        write_body=not head)

    def _reply(self, status: int, payload: Any) -> None:
        self._send_body(status, _JSON, canonical_json(payload).encode("utf-8"))

    def _service(self) -> HubService:
        if self.server.service is None:
            raise HubRefusal("route_not_found", {"reason": "the hub is starting"})
        return self.server.service

    # -- reads -------------------------------------------------------------------------------------

    def _get(self, matched: routes.Matched) -> None:
        path = matched.route.path
        if ("GET", path) not in LIVE_ROUTES:
            raise HubRefusal("route_not_found", {"reason": "not in this build"})
        if path == "/":
            self._file("text/html; charset=utf-8", PAGE)
        elif path == routes.ASSET_PATH:
            content_type, name = HUB_ASSETS[self.path]
            self._file(content_type, name)
        elif path == "/hub/session":
            self._reply(200, self.server.session.session_response(self.headers["Host"]))
        elif path == "/hub/events":
            self._stream()
        elif path == "/hub/operations/<operation_id>":
            self._reply(200, self._service().operation(matched.params["operation_id"]))
        elif path == "/hub/dialogs/<pick_id>":
            self._reply(200, self._service().dialog(matched.params["pick_id"]))
        elif path == "/hub/github/repos/<owner>":
            self._reply(200, self._service().github_repos(matched.params["owner"]))
        else:
            status, payload = _GET[path](self._service())
            self._reply(status, payload)

    def _file(self, content_type: str, name: str) -> None:
        packaged = importlib.resources.files("conductor") / "panel" / name
        self._send_body(200, content_type, packaged.read_bytes())

    def _stream(self) -> None:
        """`GET /hub/events`: the first frame is `projects`, then one per change, ids only."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        box = self.server.bus.register()
        try:
            self._write(events.encode({"kind": "projects"}))
            quiet = 0
            while not self.server.shutting_down:
                if not box.wait(1.0):
                    quiet += 1
                    if quiet % PING_EVERY == 0:
                        self._write(b": ping\n\n")
                    continue
                if self.server.shutting_down:
                    break
                for chunk in box.drain():
                    self._write(chunk)
        except OSError:
            pass                              # the client left: this loop only
        finally:
            self.server.bus.unregister(box)

    def _write(self, chunk: bytes) -> None:
        self.wfile.write(chunk)
        self.wfile.flush()

    # -- writes ------------------------------------------------------------------------------------

    def _post(self, matched: routes.Matched) -> None:
        pairs = tuple(self.headers.raw_items())
        session = self.server.session
        try:
            length = session.body_length(pairs)
        except HttpRefusal:
            # A refused write is answered over a wire that is clear: a body whose length can be
            # trusted (one Content-Length, under the limit) is consumed first, and one that cannot
            # ends the connection. Answering over unread bytes lets the client lose the answer.
            self._drain_refused_body()
            self._body_read = True
            raise
        raw = self.rfile.read(length)
        self._body_read = True
        if len(raw) != length:
            self.close_connection = True
        body = session.validate_mutation(pairs, raw)
        routes.check_body(matched.route, body)
        if ("POST", matched.route.path) not in LIVE_ROUTES:
            raise HubRefusal("route_not_found", {"reason": "not in this build"})
        status, payload = _POST[matched.route.path](self._service(), dict(matched.params), body)
        self._reply(status, payload)


class HubLoop(threading.Thread):
    """The hub's once-a-second pass: `service.tick()`, kept alive through a fault of one pass."""

    def __init__(self, service: HubService, *, interval: float = 1.0,
                 report: Callable[[str], object] | None = None) -> None:
        super().__init__(name="hub-loop", daemon=True)
        self._service, self._interval = service, interval
        self._report = report or (lambda line: print(line, file=sys.stderr))
        self._stop_event = threading.Event()
        self._last = ""

    def stop(self) -> None:
        """Ask the loop to end after the pass it is in."""
        self._stop_event.set()

    def run(self) -> None:
        """Tick until stopped; a fault is said once per distinct message and does not end it."""
        while not self._stop_event.is_set():
            try:
                self._service.tick()
            except Exception as error:  # noqa: BLE001 -- a background pass must not die of one fault
                line = f"conduct hub: {type(error).__name__}: {' '.join(str(error).split())}"
                if line != self._last:
                    self._last = line
                    self._report(line)
            self._stop_event.wait(self._interval)
