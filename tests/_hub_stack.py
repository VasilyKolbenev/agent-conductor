"""A whole hub on a fake world, with a real socket in front (not a test file).

`Stack` builds over the world of fakes of `tests/_hub_world.py` (three registered projects, a clock,
a spawner that starts no process) the parts the HTTP hub is made of: the reader with a clock of its
own, the snapshot store, the ledger, the service, and a real `HubServer` on a free loopback port
served by a thread. Children are `FakeChild` sockets: `put_status(..., port=child.port)` makes the
supervisor say a project runs there, and the reader reads it for real.

`request` speaks HTTP by hand so a test can send any Host, any header or none, and see every header
that comes back.
"""
from __future__ import annotations

import http.client
import json
import socket
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conductor.hub import reader, routes, server, service, snapshots, summary
from conductor.hub.refusals import HubRefusal
from tests._hub_fake_child import HUB_ORIGIN
from tests._hub_world import World

A, B, C = "a" * 32, "b" * 32, "c" * 32
#: The refusals that act on every row and are not repeated in it (spec 4.6.3).
TRANSPORT = frozenset({"same_origin_denied", "csrf_denied", "malformed_request",
                       "route_not_found", "method_not_allowed", "contract_invalid"})
#: The test modules whose writes `Stack.post` holds to the list of the row: the hub handler tests.
#: The tests of earlier slices that also use `Stack` are not judged.
JUDGED = frozenset({"tests.test_hub_handlers_http", "tests.test_hub_tool_pin_route"})
#: The answers a live route gives in a judged module that its row does not list, each waiting for
#: a ruling, as (module of the test that sends the request, `METHOD path-template`, code).
#: `Stack.post` lets one through only when the call says so with `unlisted=<code>`; every other
#: code outside a row fails the test that met it.
#:
#: These are the two of the question to the reviewer of the rows
#: (OPUS-H-REFUSAL-LIST-QUESTION-2026-10-07). A project whose own operation runs stays on the
#: list: `forget` says `project_busy`, which its row (`project_not_found`, `project_running`)
#: does not name. A login recovery asked of a hub that is closing says `operation_busy`; its row
#: names `login_not_found` and `recover_not_needed`.
PENDING_RULING = frozenset({
    ("tests.test_hub_handlers_http", "POST /hub/projects/<project_id>/forget", "project_busy"),
    ("tests.test_hub_handlers_http", "POST /hub/logins/<login_key>/recover", "operation_busy"),
})


class Mono:
    """A monotonic clock that moves when told to."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class Reply:
    """What came back: the status, every header as a list of pairs, and the body."""

    status: int
    headers: list[tuple[str, str]]
    body: bytes = b""
    raw: bytes = field(default=b"", repr=False)

    def header(self, name: str) -> list[str]:
        return [value for key, value in self.headers if key.lower() == name.lower()]

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


def request(port: int, method: str, target: str, *, headers: dict[str, str] | None = None,
            body: bytes | None = None, host: str | None = "default",
            read_body: bool = True) -> Reply:
    """One request by hand. `host="default"` sends the hub's own Host, `None` sends none."""
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.putrequest(method, target, skip_host=True, skip_accept_encoding=True)
        if host == "default":
            host = f"127.0.0.1:{port}"
        if host is not None:
            connection.putheader("Host", host)
        for name, value in (headers or {}).items():
            connection.putheader(name, value)
        if body is not None and "Content-Length" not in (headers or {}):
            connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body if body is not None else None)
        response = connection.getresponse()
        data = response.read() if read_body else b""
        return Reply(response.status, response.getheaders(), data)
    finally:
        connection.close()


def undeclared(method: str, target: str, reply: Reply) -> str | None:
    """The code of an error answer that its row does not list, or `None` when it lists it.

    A refusal is in the table when it is one of the transport refusals or one the row names. An
    answer that is not an error envelope, or a target no row names, is not judged here.
    """
    if reply.status < 400:
        return None
    try:
        code = reply.json()["error"]["code"]
        row = routes.match(method, target).route
    except (ValueError, KeyError, TypeError, HubRefusal):
        return None
    return None if code in TRANSPORT or code in row.refusals else code


def judge(method: str, target: str, reply: Reply, *, module: str, unlisted: str | None = None,
          pending: frozenset[tuple[str, str, str]] = PENDING_RULING) -> None:
    """Hold an answer to the list of its row; raise `AssertionError` when it is not.

    An error answer is a transport code or one the row names. The one way outside is a case that
    `pending` names for this `module`, and then the call must say `unlisted=<code>` and that code,
    no other, must be what came back: a call that waits for a case nobody named fails, and so does
    a call whose named case no longer answers.
    """
    if unlisted is not None:
        try:
            route = f"{method} {routes.match(method, target).route.path}"
        except HubRefusal:
            route = target
        assert (module, route, unlisted) in pending, (
            f"{module}: {route} -> {unlisted!r} is not named as waiting for a ruling")
    found = undeclared(method, target, reply)
    assert found == unlisted, (
        f"{method} {target} answered {found!r}, which its row does not list" if unlisted is None
        else f"{method} {target} was to answer {unlisted!r} outside its row, and answered "
        f"{found or reply.status!r}")


def raw_exchange(port: int, payload: bytes, *, wait: float = 3.0) -> bytes:
    """Send bytes exactly as given and read until the hub closes (or `wait` s pass)."""
    with socket.create_connection(("127.0.0.1", port), timeout=wait) as sock:
        sock.sendall(payload)
        chunks = []
        try:
            while True:
                piece = sock.recv(65536)
                if not piece:
                    break
                chunks.append(piece)
        except (TimeoutError, OSError):
            pass
        return b"".join(chunks)


class Stack:
    """The parts of a hub over the fake world, and a server on a free port."""

    def __init__(self, tmp_path: Path, **service_options: Any) -> None:
        """`service_options` are handed to `HubService` over the defaults below."""
        self.world = World(tmp_path)
        self.mono = Mono()
        self.server = server.HubServer(0)
        self.port = self.server.server_port
        self.bus = self.server.bus
        self.snapshots = snapshots.SnapshotStore(self.world.home, clock=self.mono)
        self.ledger = summary.ObservedLedger()
        self.reader = reader.ChildReader(
            self.world.home, self.world.supervisor, self.world.store, self.snapshots,
            self.ledger, self.bus, hub_origin=HUB_ORIGIN, now=self.world.clock,
            monotonic=self.mono, follow=None)
        options: dict[str, Any] = {
            "verify_tool": lambda tool, **_kw: (_ for _ in ()).throw(
                AssertionError("no tool is verified here")),
            "job_policy": lambda: "none", "folder_ok": lambda project: True, **service_options}
        self.service = service.HubService(
            self.world.home, self.world.supervisor, self.world.store, self.snapshots,
            self.reader, self.ledger, self.bus, now=self.world.clock, **options)
        self.server.attach(self.service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._token: str | None = None

    @property
    def token(self) -> str:
        if self._token is None:
            self._token = request(self.port, "GET", "/hub/session").json()["csrf_token"]
        return self._token

    def get(self, target: str, **kwargs: Any) -> Reply:
        return request(self.port, "GET", target, **kwargs)

    def post(self, target: str, payload: Any = None, *, token: str | None = "default",
             origin: str | None = "default", content_type: str | None = "application/json",
             body: bytes | None = None, host: str | None = "default", extra: dict | None = None,
             unlisted: str | None = None) -> Reply:
        """A write with every header right unless the test says otherwise.

        In a module of `JUDGED`, every refusal it gets back must be in the list of the route's row
        (or a transport one), or be a case of `PENDING_RULING` that the call names with
        `unlisted=<code>` (`judge`). A module outside `JUDGED` is not judged and may not say
        `unlisted=`: a call that waits for a ruling nobody reads would be dead.
        """
        module = sys._getframe(1).f_globals.get("__name__", "")
        raw = body if body is not None else json.dumps({} if payload is None else payload
                                                       ).encode("utf-8")
        headers: dict[str, str] = {}
        if origin == "default":
            origin = f"http://127.0.0.1:{self.port}"
        if origin is not None:
            headers["Origin"] = origin
        if token == "default":
            token = self.token
        if token is not None:
            headers["X-Conduct-CSRF"] = token
        if content_type is not None:
            headers["Content-Type"] = content_type
        headers.update(extra or {})
        reply = request(self.port, "POST", target, headers=headers, body=raw, host=host)
        if module in JUDGED:
            judge("POST", target, reply, unlisted=unlisted, module=module)
        else:
            assert unlisted is None, (
                f"{module} is not judged, so it has no ruling to wait for ({unlisted!r})")
        return reply

    def state_bytes(self) -> bytes | None:
        path = self.world.home / "hub-state.json"
        return path.read_bytes() if path.exists() else None

    def tick(self, seconds: float = 0.0) -> None:
        """One pass of the hub's loop, `seconds` of the reader's clock later."""
        self.mono.advance(seconds)
        self.service.tick()

    def close(self) -> None:
        self.reader.close()
        self.server.shutdown()
        self.server.server_close()
        self.world.close()
