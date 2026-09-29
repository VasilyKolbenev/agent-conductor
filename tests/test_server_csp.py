"""`frame-ancestors` on every answer of a child, from ONE place (spec 4.6.6, 4.6.7 item 1).

Nothing in the product said who may frame it: any site could embed the desk under a
transparent layer (clickjacking on the gate). The value is `frame-ancestors 'self'`, plus
the hub's origin when the child was started with `--hub-origin`, and it is written by
`KeptConnection.end_headers`, the one call every answer of `BaseHTTPRequestHandler` ends
its headers with: the routes, the event stream, and `send_error` (400, 501) which goes
past every route. Each kind of answer is read as raw bytes off a real socket, because a
client library would merge or hide a second header, and "exactly one, exactly this" is
the claim. The sabotage that removes the override is kept as a test: the reading must
report a fault on EVERY kind of answer, or a passing run would prove nothing.

Not here, because it cannot be: a reply to a request line whose version does not parse
(or that says HTTP/0.9) is an HTTP/0.9 reply, which has no status line and no headers.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass
from threading import Thread

import pytest

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.http_framing import KeptConnection
from tests.test_store import good_lane, write_project

HUB = "http://127.0.0.1:7700"
HEADER = "content-security-policy"


@dataclass(frozen=True)
class Served:
    port: int
    expected: str


@pytest.fixture(params=[None, HUB], ids=["standalone", "with-hub-origin"])
def serving(request, tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    subject = server.build(root, 0, registry=AdapterRegistry(), hub_origin=request.param)
    loop = Thread(target=subject.serve_forever, daemon=True)
    loop.start()
    expected = "frame-ancestors 'self'" + ("" if request.param is None else f" {request.param}")
    yield Served(subject.server_address[1], expected)
    subject.shutdown()
    subject.server_close()
    loop.join(10)


def _request(port: int, method: str, target: str, *, host: str | None = None,
             body: bool = False) -> bytes:
    head = [f"{method} {target} HTTP/1.1", f"Host: {host or f'127.0.0.1:{port}'}",
            "Connection: close"]
    if body:
        head.append("Content-Length: 0")
    return ("\r\n".join(head) + "\r\n\r\n").encode("ascii")


def _cases(port: int) -> dict[str, bytes]:
    """One raw request per kind of answer the spec names."""
    return {
        "the entry page": _request(port, "GET", "/"),
        "a panel asset": _request(port, "GET", "/panel/studio.js"),
        "the classic panel": _request(port, "GET", "/panel/index.html"),
        "the graph window": _request(port, "GET", "/panel/graph.html"),
        "the desk": _request(port, "GET", "/panel/desk.html"),
        "the state document": _request(port, "GET", "/state.json"),
        "the head of the event stream": _request(port, "GET", "/events"),
        "a command GET": _request(port, "GET", "/command/session"),
        "a command GET refused for its Host": _request(
            port, "GET", "/command/session", host="evil.example"),
        "a command POST refused": _request(port, "POST", "/command/session", body=True),
        "a 404": _request(port, "GET", "/nowhere"),
        "a HEAD": _request(port, "HEAD", "/state.json"),
        "send_error 400 (a request line of four words)": _request(port, "GET", "/ extra"),
        "send_error 501 (an unknown method)": _request(port, "FOO", "/"),
        "send_error 501 on a command route": _request(port, "FOO", "/command/session"),
    }


def _read_head(port: int, raw: bytes) -> tuple[str, list[tuple[str, str]]]:
    """The status line and header pairs of the answer, read off the socket as bytes.

    Only the head is read: an event stream has no end, and the header is all that is judged.
    """
    with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
        connection.sendall(raw)
        received = b""
        while b"\r\n\r\n" not in received:
            chunk = connection.recv(65536)
            if not chunk:
                break
            received += chunk
    lines = received.split(b"\r\n\r\n", 1)[0].decode("iso-8859-1").split("\r\n")
    pairs = [tuple(part.strip() for part in line.split(":", 1))
             for line in lines[1:] if ":" in line]
    return lines[0], pairs


def _faults(served: Served) -> dict[str, list[str]]:
    """Every kind of answer whose CSP header is not exactly one and exactly the expected value."""
    found: dict[str, list[str]] = {}
    for name, raw in _cases(served.port).items():
        status, pairs = _read_head(served.port, raw)
        values = [value for key, value in pairs if key.lower() == HEADER]
        if values != [served.expected]:
            found[name] = [status, *values]
    return found


def test_every_kind_of_answer_carries_exactly_one_frame_ancestors_header_with_the_exact_value(
        serving):
    assert _faults(serving) == {}


def test_the_reading_reports_every_kind_of_answer_when_the_end_headers_override_is_removed(
        serving, monkeypatch):
    """The sabotage of the spec, kept: without the override nothing carries the header."""
    monkeypatch.delattr(KeptConnection, "end_headers")
    assert set(_faults(serving)) == set(_cases(serving.port)), "a kind of answer escaped"


def test_the_policy_is_built_once_and_cannot_be_reassigned_after_the_start(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    subject = server.build(root, 0, registry=AdapterRegistry(), hub_origin=HUB)
    try:
        assert subject.content_security_policy == f"frame-ancestors 'self' {HUB}"
        with pytest.raises(AttributeError):
            subject.content_security_policy = "frame-ancestors *"
    finally:
        subject.server_close()


@pytest.fixture
def bind_spy(monkeypatch) -> list[tuple[str, int]]:
    """Every call of `ConductServer.server_bind`, recorded; the bind itself still happens.

    `TCPServer.__init__` binds through this method, so an empty list means nothing bound.
    """
    binds: list[tuple[str, int]] = []
    real = server.ConductServer.server_bind

    def recording(self) -> None:
        binds.append(self.server_address)
        real(self)

    monkeypatch.setattr(server.ConductServer, "server_bind", recording)
    return binds


@pytest.mark.parametrize("origin", [
    "", "*", "http://localhost:7700", "https://127.0.0.1:7700", "http://127.0.0.1",
    "http://127.0.0.1:7700/", "http://127.0.0.1:0", "http://127.0.0.1:07700",
    "http://127.0.0.1:65536", "http://127.0.0.1:7700 https://evil.example",
    "http://127.0.0.1:7700\r\nX-Injected: 1", "http://127.0.0.1:7700;"])
def test_a_hub_origin_outside_the_one_grammar_is_refused_before_anything_binds(
        tmp_path, origin, bind_spy):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    with pytest.raises(ValueError, match="hub origin"):
        server.build(root, 0, registry=AdapterRegistry(), hub_origin=origin)
    assert bind_spy == [], "the server bound before it judged the hub origin"


def test_a_valid_build_binds_exactly_once_so_the_bind_spy_is_not_blind(tmp_path, bind_spy):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    subject = server.build(root, 0, registry=AdapterRegistry(), hub_origin=HUB)
    try:
        assert len(bind_spy) == 1
    finally:
        subject.server_close()
