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


def judge(method: str, target: str, reply: Reply) -> None:
    """Hold an answer to the list of its row; raise `AssertionError` when it is not.

    An error answer is a transport code or one the row names; there is no other way through.
    """
    found = undeclared(method, target, reply)
    assert found is None, f"{method} {target} answered {found!r}, which its row does not list"


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
             body: bytes | None = None, host: str | None = "default",
             extra: dict | None = None) -> Reply:
        """A write with every header right unless the test says otherwise.

        Every refusal it gets back, in whatever test, must be in the list of the route's row or a
        transport one (`judge`).
        """
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
        judge("POST", target, reply)
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
