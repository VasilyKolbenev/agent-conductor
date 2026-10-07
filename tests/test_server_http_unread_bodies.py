"""Every way into this server settles the body it was sent, read off one socket.

`91614c4` kept the connection open and then closed the roads it had LISTED:
HEAD, the event stream, and six methods that answer without reading. The list
was the defect. A GET -- on the legacy read and on the command surface -- and a
method this server has no handler for at all each answered over a body still
sitting on the connection, and the server then parsed that body as the next
request. Measured with a truthful `Content-Length` and ONE outer request: an
unsolicited second answer arrived, for the request carried inside the body.

That is not two names missing from a list; it is the wrong shape of rule. A rule
that names which requests must drain misses the next entrance by construction.
So these are organised by ENTRANCE, and each entrance is asked three things:

- a declared, well-framed body is consumed, and the next real request on the
  same socket gets its own answer;
- no body at all keeps the connection -- an ordinary browser GET must stay
  reusable, or the churn this repair exists to end comes straight back;
- a body whose framing this server will not trust is never dispatched and never
  read on the client's word: the connection ends, and ends promptly.

The third is read on the SERVER's side of the socket. Closing over bytes the
client already sent can make Windows answer with a reset, which may take the
refusal with it before the client reads it; what the connection did with those
bytes is a fact the handler knows either way.
"""
from __future__ import annotations

import json
import socket
import threading

import pytest

from tests.test_server_http_framing import (  # noqa: F401 -- `live` is a fixture
    PATIENCE, Wire, _status, _wire, live)

#: The three entrances the finite list missed, named for what they ARE: the
#: legacy read, the command surface's read, and a method no handler exists for,
#: which reaches the command refusal by another road entirely (`send_error`).
ENTRANCES = [
    pytest.param("GET /state.json HTTP/1.1", id="legacy-read"),
    pytest.param("GET /command/session HTTP/1.1", id="command-read"),
    pytest.param("PROBE /command/session HTTP/1.1", id="unhandled-method"),
]
#: Framings this server does not take on the client's word: an ambiguous
#: length, a chunked body, and a length past the bounded door's ceiling.
UNTRUSTED = ["two-lengths", "chunked", "over-the-ceiling"]


def _inner(host: str) -> bytes:
    """A complete, harmless request, carried AS a body.

    If the body is left on the connection the server reads this as a second
    request and answers it: an answer to a question nobody asked on this socket.
    """
    return f"GET /harnesses.json HTTP/1.1\r\nHost: {host}\r\n\r\n".encode("ascii")


def _raw(wire: Wire, head: str, body: bytes = b"") -> None:
    """Send exactly these header lines, with no length added on our behalf."""
    wire.sock.sendall(head.encode("ascii") + b"\r\n\r\n" + body)


def _nothing_unasked(wire: Wire, probe: float = 0.4) -> bool:
    """No answer arrived that nobody asked for, and the server did not hang up."""
    wire.sock.settimeout(probe)
    try:
        wire._fill()
    except (TimeoutError, socket.timeout):
        return wire.buffer == b""
    finally:
        wire.sock.settimeout(PATIENCE)
    return False


def _framed(kind: str, inner: bytes) -> tuple[str, bytes]:
    if kind == "two-lengths":
        return (f"Content-Length: {len(inner)}\r\n"
                f"Content-Length: {len(inner) + 1}"), inner
    if kind == "chunked":
        return ("Transfer-Encoding: chunked",
                f"{len(inner):x}\r\n".encode("ascii") + inner + b"\r\n0\r\n\r\n")
    return "Content-Length: 10000000", inner


@pytest.fixture()
def recorded(live):
    """The live server, with every request line its handler READ written down."""
    srv, address = live
    lines: list[bytes] = []
    ended = threading.Event()

    class Recording(srv.RequestHandlerClass):
        def handle_one_request(self) -> None:
            super().handle_one_request()
            if self.raw_requestline:
                lines.append(self.raw_requestline)

        def finish(self) -> None:
            try:
                super().finish()
            finally:
                ended.set()

    srv.RequestHandlerClass = Recording
    return address, lines, ended


@pytest.mark.parametrize("line", ENTRANCES)
def test_a_declared_body_is_consumed_and_the_next_request_gets_its_own_answer(
        live, line):
    """The defect's own shape, and the reuse the repair is for, together."""
    wire = _wire(live)
    try:
        inner = _inner(wire.host)
        _raw(wire, f"{line}\r\nHost: {wire.host}\r\n"
                   f"Content-Length: {len(inner)}", inner)
        first, _, _ = wire.answer()
        assert _status(first) < 500, first
        assert _nothing_unasked(wire), (
            f"the body was answered as a request: {wire.buffer[:120]!r}")

        wire.send("GET /state.json HTTP/1.1")
        second, _, payload = wire.answer()
        assert _status(second) == 200 and json.loads(payload)["project"], second
        assert wire.buffer == b""
    finally:
        wire.close()


@pytest.mark.parametrize("line", ENTRANCES)
def test_no_body_at_all_keeps_the_connection_for_the_next_request(live, line):
    """The control against over-correction: a browser's bodyless read stays kept.

    No `Content-Length` and no `Transfer-Encoding`, exactly as a browser sends a
    GET. Closing here would satisfy every other test in this module and bring
    back one connection per request.
    """
    wire = _wire(live)
    try:
        _raw(wire, f"{line}\r\nHost: {wire.host}")
        _first, headers, _ = wire.answer()
        assert headers.get("connection") != "close", headers
        assert _nothing_unasked(wire), wire.buffer[:120]

        _raw(wire, f"GET /state.json HTTP/1.1\r\nHost: {wire.host}")
        second, _, payload = wire.answer()
        assert _status(second) == 200 and json.loads(payload)["project"], second
        assert wire.buffer == b""
    finally:
        wire.close()


@pytest.mark.parametrize("kind", UNTRUSTED)
@pytest.mark.parametrize("line", ENTRANCES)
def test_a_body_whose_framing_is_not_trusted_is_never_read_as_a_request(
        recorded, line, kind):
    """One request line read, and the connection ended without waiting.

    Read on the server's side: the handler's own record of every request line it
    parsed on this connection must hold the outer one and nothing else, and the
    connection must end well inside the patience -- a server that waited to read
    ten megabytes on the client's word would still be waiting.
    """
    address, lines, ended = recorded
    host = f"127.0.0.1:{address[1]}"
    extra, body = _framed(kind, _inner(host))
    sock = socket.create_connection(address, timeout=PATIENCE)
    try:
        sock.sendall(f"{line}\r\nHost: {host}\r\n{extra}\r\n\r\n".encode("ascii")
                     + body)
        assert ended.wait(PATIENCE), "the connection was held open on that body"
    finally:
        sock.close()

    assert [row.split(b" ", 1)[0] for row in lines] == [
        line.split(" ", 1)[0].encode("ascii")], lines


# -- what an adversarial sweep found after the entrance landed -----------------
#
# 211 cases across six attack families, every claimed finding re-run by an
# independent skeptic. Two more ways to desynchronize a kept connection were
# confirmed, and both live in how the standard library READS a request before
# any code here sees it -- which is why no list of verbs could have closed them.


#: A header line this parser cannot read -- a space before its colon -- ends the
#: parsed header block THERE. Every header after it, `Content-Length` included,
#: is dropped from `self.headers`, though its bytes were already read off the
#: socket; so the entrance saw no body to settle and the real body was parsed as
#: the next request. Two shapes: one that also hides the client's own close
#: intent, and one that hides nothing but the headers after it.
UNREADABLE_LINES = [
    pytest.param("Connection : close", id="connection-with-space"),
    pytest.param("X-Probe : 1", id="unknown-with-space"),
]


@pytest.fixture()
def watched(live):
    """Every request line a handler read, its end, and anything it raised."""
    srv, address = live
    lines: list[bytes] = []
    errors: list[BaseException] = []
    ended = threading.Event()

    class Watching(srv.RequestHandlerClass):
        def handle(self) -> None:
            try:
                super().handle()
            except Exception as error:  # noqa: BLE001 -- recorded, then re-raised
                errors.append(error)
                raise

        def handle_one_request(self) -> None:
            super().handle_one_request()
            if self.raw_requestline:
                lines.append(self.raw_requestline)

        def finish(self) -> None:
            try:
                super().finish()
            finally:
                ended.set()

    srv.RequestHandlerClass = Watching
    return address, lines, ended, errors


@pytest.mark.parametrize("unreadable", UNREADABLE_LINES)
@pytest.mark.parametrize("line", ENTRANCES)
def test_a_header_block_that_did_not_parse_whole_never_keeps_its_connection(
        watched, line, unreadable):
    """A length the parser hid is a length this server does not know.

    The entrance asked `self.headers` whether a body was announced, and
    `self.headers` had been cut short at the unreadable line. The repair does not
    try to recover what was hidden -- a second reading of the same bytes is a
    second parser to disagree with the first -- it refuses to keep a connection
    whose header block did not parse whole. One request line read; the
    connection ends; nothing raised.
    """
    address, lines, ended, errors = watched
    host = f"127.0.0.1:{address[1]}"
    inner = _inner(host)
    sock = socket.create_connection(address, timeout=PATIENCE)
    try:
        sock.sendall(f"{line}\r\nHost: {host}\r\n{unreadable}\r\n"
                     f"Content-Length: {len(inner)}\r\n\r\n".encode("ascii")
                     + inner)
        assert ended.wait(PATIENCE), "a cut header block kept its connection"
    finally:
        sock.close()

    assert [row.split(b" ", 1)[0] for row in lines] == [
        line.split(" ", 1)[0].encode("ascii")], lines
    assert errors == [], errors


def test_a_cut_header_block_on_the_command_surface_keeps_its_json_refusal(live):
    """The connection now ends; the refusal a command client reads does not change.

    The frozen command surface answers every refusal as its JSON envelope, and a
    request whose header block was cut short is still refused by the same doors
    as before -- it no longer keeps the connection afterwards. Sent with no body
    bytes, so nothing unread is on the socket when the server closes, and the
    answer cannot be lost to a reset.
    """
    wire = _wire(live)
    try:
        _raw(wire, f"POST /command/runs HTTP/1.1\r\nHost: {wire.host}\r\n"
                   "X-Probe : 1\r\nContent-Type: application/json\r\n"
                   "Content-Length: 2")
        first, headers, body = wire.answer()

        assert _status(first) >= 400, first
        assert set(json.loads(body)) == {"error"}, body
        assert headers.get("connection") == "close", headers
    finally:
        wire.close()


@pytest.mark.parametrize("shape", ["bare", "keep-alive-and-pipelined"])
@pytest.mark.parametrize("path", ["/state.json", "/command/session"])
def test_an_http_0_9_request_is_refused_and_never_keeps_its_connection(
        watched, path, shape):
    """No version, no status line, no length: the close is the only frame it has.

    Two failures, on two interpreters, from one missing rule. On the ones CI runs,
    such a request carrying `Connection: keep-alive` was answered with no status
    line and no length on a connection this server then KEPT, so the next request
    was read from the end of an unframed answer. On the one this repository's
    venv runs, the standard library hands the request a plain `dict` for headers
    and the handler raised on it -- a traceback and no answer. That crash predates
    the repair (the Host gate raised the same way one frame later); refusing at
    the entrance ends it on every road.
    """
    address, lines, ended, errors = watched
    host = f"127.0.0.1:{address[1]}"
    request = f"GET {path}\r\n".encode("ascii")
    if shape == "bare":
        request += b"\r\n"
    else:
        request += (f"Host: {host}\r\nConnection: keep-alive\r\n\r\n"
                    f"GET /harnesses.json HTTP/1.1\r\nHost: {host}\r\n\r\n"
                    ).encode("ascii")
    sock = socket.create_connection(address, timeout=PATIENCE)
    try:
        sock.sendall(request)
        assert ended.wait(PATIENCE), "an HTTP/0.9 connection was kept"
    finally:
        sock.close()

    assert len(lines) == 1, lines
    assert errors == [], errors
