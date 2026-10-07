"""Every response road, read off a live socket, one request after another.

A browser gate went red when a Studio module failed to load with
`net::ERR_NO_BUFFER_SPACE` -- Chromium's name for WSAENOBUFS. Part of the socket
churn under it was this server's own: answering HTTP/1.0 closes the connection
after every response, so one page boot cost 34 accepted TCP connections instead
of 6. Keeping connections cut that churn. It did not end the error, and which
resource runs out is still unassigned.

Keeping the connection open is NOT a one-line switch.
HTTP/1.0 forgives a badly framed response because the close IS the frame: a
body nobody asked for, a stream with no length, a request body left unread --
each of them is invisible while every answer ends by hanging up. Persistent
connections turn all three into the same failure, and it is the worst kind:
the next response is read starting from somebody else's bytes, so a client
gets a valid-looking answer to the wrong question.

So these read RAW BYTES off a real socket and ask, for every road this server
answers on, whether the connection is still exactly where the next request
should start. They are written against the socket rather than through
`urllib` because a client library hides precisely what is under test -- it
will resynchronize, retry, or open a second connection, and report success.

What is NOT here: nothing raises a timeout, waives, skips or retries. A road
that cannot be framed honestly must close, and closing is an answer these
assert for, not a failure they hide.
"""
from __future__ import annotations

import json
import socket
import threading

import pytest

from conductor import server
from tests.test_store import good_lane, write_project

#: Long enough that a real answer always arrives, short enough that a hung read
#: fails the test instead of the suite. Never raised to make a road pass.
PATIENCE = 5.0


def _serving(root_dir, idle: float | None = None):
    """Start one real server, optionally with its idle reaper set short."""
    root = write_project(root_dir, lanes={"claude": good_lane()})
    if idle is None:
        srv = server.build(root, port=0)
    else:
        class Impatient(server.Handler):
            timeout = idle

        srv = server.build(root, port=0)
        srv.RequestHandlerClass = Impatient
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return root, srv, thread, ("127.0.0.1", srv.server_address[1])


@pytest.fixture()
def live(tmp_path):
    """A real ConductServer on a real port, and its socket address."""
    _root, srv, thread, address = _serving(tmp_path)
    try:
        yield srv, address
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=PATIENCE)


class Wire:
    """One connection, read as bytes, with the reader kept where a client is."""

    def __init__(self, address, host_header: str) -> None:
        self.sock = socket.create_connection(address, timeout=PATIENCE)
        self.buffer = b""
        self.host = host_header

    def send(self, line: str, *, body: bytes = b"", headers: str = "") -> None:
        request = (f"{line}\r\nHost: {self.host}\r\n{headers}"
                   f"Content-Length: {len(body)}\r\n\r\n").encode("ascii")
        self.sock.sendall(request + body)

    def _fill(self) -> bool:
        chunk = self.sock.recv(65536)
        if not chunk:
            return False
        self.buffer += chunk
        return True

    def answer(self, *, to_a_head: bool = False
               ) -> tuple[str, dict[str, str], bytes]:
        """One whole response, and the buffer left standing at the next byte.

        `to_a_head` because a HEAD's `Content-Length` is the length a GET WOULD
        have sent, with no bytes after it. A reader that waited for them would
        hang on a correct answer -- and a reader that did not know the
        difference would call a HEAD that really wrote a body correct.
        """
        while b"\r\n\r\n" not in self.buffer:
            assert self._fill(), f"the connection closed mid-header: {self.buffer!r}"
        head, _, rest = self.buffer.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        headers = {}
        for row in lines[1:]:
            name, _, value = row.partition(":")
            headers[name.strip().lower()] = value.strip()
        length = 0 if to_a_head else int(headers.get("content-length", 0))
        while len(rest) < length:
            self.buffer = rest
            assert self._fill(), "the connection closed mid-body"
            rest = self.buffer
        self.buffer = rest[length:]
        return lines[0], headers, rest[:length]

    def closed_by_the_server(self, probe: float = 0.4) -> bool:
        """Whether the server hung up, with nothing unread left behind.

        Asked with a SHORT patience of its own. Waiting the full patience here
        would race the server's own idle reaper, and the test would then be
        measuring which of the two timers fired first rather than what the road
        did with the body it was sent.
        """
        self.sock.settimeout(probe)
        try:
            return not self._fill()
        except (TimeoutError, socket.timeout):
            return False
        finally:
            self.sock.settimeout(PATIENCE)

    def close(self) -> None:
        self.sock.close()


def _wire(live) -> Wire:
    srv, address = live
    return Wire(address, f"127.0.0.1:{address[1]}")


def _status(line: str) -> int:
    return int(line.split(" ")[1])


# -- the connection is kept, and one answer does not run into the next --------


def test_two_reads_share_one_connection_and_do_not_mix(live):
    """The repair itself: a second request on the SAME socket, answered whole.

    This is the evidence the churn is really gone. Counting connections
    elsewhere says a page opened fewer of them; this says the ones it opened
    carried more than one exchange and that the second answer began exactly
    where the first ended.
    """
    wire = _wire(live)
    try:
        wire.send("GET /state.json HTTP/1.1")
        first, headers, body = wire.answer()

        wire.send("GET /harnesses.json HTTP/1.1")
        second, _, other = wire.answer()

        assert _status(first) == 200 and _status(second) == 200
        assert headers.get("content-length") == str(len(body))
        # Each answer is whole JSON, and the second is the second question's.
        assert json.loads(body)["project"]
        assert isinstance(json.loads(other), list) and json.loads(other)
        assert wire.buffer == b"", f"bytes left over: {wire.buffer[:80]!r}"
    finally:
        wire.close()


def test_a_head_answers_with_no_body_at_all(live):
    """HEAD promises the length a GET would send and sends none of it.

    Left as it was, `HEAD /` wrote `not found\\n` after its headers. Under
    HTTP/1.0 nobody could tell: the close ended the response either way. On a
    kept connection those nine bytes are the first nine bytes of the NEXT
    answer, and the client reads them as a status line.
    """
    wire = _wire(live)
    try:
        wire.send("HEAD /panel/studio.js HTTP/1.1")
        line, headers, body = wire.answer(to_a_head=True)

        assert body == b"", f"HEAD answered with a body: {body!r}"
        assert "content-length" in headers
        # Nothing followed the headers, which is what makes the next read the
        # next ANSWER: a body here would be read as its status line.
        assert wire.buffer == b"", f"HEAD wrote {wire.buffer[:40]!r} after them"
        # And the connection is still usable, which is the whole point.
        wire.send("GET /state.json HTTP/1.1")
        second, _, payload = wire.answer()
        assert _status(second) == 200 and json.loads(payload)["project"]
        assert wire.buffer == b""
        assert _status(line) in (200, 404)
    finally:
        wire.close()


@pytest.mark.parametrize("line,body", [
    ("POST /nowhere HTTP/1.1", b'{"unwanted": true}'),
    ("PUT /command/runs HTTP/1.1", b'{"unwanted": true}'),
    ("DELETE /state.json HTTP/1.1", b"x" * 64),
])
def test_a_body_this_server_does_not_read_never_becomes_the_next_request(
        live, line, body):
    """A refused road still owes the connection an honest end.

    Every one of these answers without reading what it was sent. The bytes have
    to go somewhere: either the server consumes them, or it closes. What it may
    not do is answer and leave them in the buffer, because then the client's
    next request is appended to a body the server is still expecting to read,
    and the two are parsed as one.
    """
    wire = _wire(live)
    try:
        wire.send(line, body=body)
        answered, _, _ = wire.answer()
        assert _status(answered) >= 400

        if wire.closed_by_the_server():
            return                          # the honest end for a body it kept
        wire.send("GET /state.json HTTP/1.1")
        second, _, payload = wire.answer()
        assert _status(second) == 200, (
            f"the refused body was read as a request: {second}")
        assert json.loads(payload)["project"]
        assert wire.buffer == b""
    finally:
        wire.close()


def test_a_refused_read_still_frames_its_own_answer(live):
    """The Host gate answers prose, and prose needs a length like anything else.

    The refusal roads are the ones a client meets when something is already
    wrong, so a badly framed refusal is a second failure on top of the first.
    """
    _srv, address = live
    wire = Wire(address, "evil.example")
    try:
        wire.send("GET /state.json HTTP/1.1")
        line, headers, body = wire.answer()

        assert _status(line) == 403
        assert headers.get("content-length") == str(len(body))
        assert wire.buffer == b""
    finally:
        wire.close()


def test_the_event_stream_says_it_owns_the_connection_to_its_end(live):
    """SSE has no length and never will, so it must say the close is the frame.

    An unbounded body on a persistent connection is the one response shape
    HTTP/1.1 cannot carry silently: without `Connection: close` a client is
    entitled to look for a second answer after it, and there is no second
    answer -- there is more of the first, forever.
    """
    wire = _wire(live)
    try:
        wire.send("GET /events HTTP/1.1")
        while b"\r\n\r\n" not in wire.buffer:
            assert wire._fill(), "the stream sent no header"
        head = wire.buffer.split(b"\r\n\r\n")[0].decode("latin-1").lower()

        assert "text/event-stream" in head
        assert "connection: close" in head, head
        assert "content-length" not in head
        # The first frame really arrives on that same connection.
        while b"data:" not in wire.buffer:
            assert wire._fill(), "the stream opened and said nothing"
    finally:
        wire.close()


def test_an_idle_connection_is_given_up_rather_than_held_for_ever(
        tmp_path_factory):
    """A kept connection is a held thread, and this server threads per socket.

    Keeping connections open is what removes the churn; keeping them open
    FOREVER trades a socket storm for a thread leak, and the gate opens
    hundreds of pages per run. So the server reaps a connection nobody is
    using, and this reads that end off the socket rather than trusting a
    setting.
    """
    # The shipped value is asserted as a value: bounded, and long enough that a
    # whole page boot -- measured at about 90ms -- never loses its connections
    # part-way through.
    assert server.IDLE_CONNECTION_SECONDS is not None
    assert 1.0 <= server.IDLE_CONNECTION_SECONDS <= 30.0
    assert server.Handler.timeout == server.IDLE_CONNECTION_SECONDS

    # And the CLOSE is then read off a socket, on a server whose reaper is set
    # short for the reading. Shortening it is what keeps this test fast; the
    # shipped number is checked above, so nothing here is proved by the patch.
    _root, srv, thread, address = _serving(tmp_path_factory.mktemp("idle"), 0.5)
    wire = Wire(address, f"127.0.0.1:{address[1]}")
    try:
        wire.send("GET /state.json HTTP/1.1")
        line, _, _ = wire.answer()
        assert _status(line) == 200

        assert wire.closed_by_the_server(probe=PATIENCE), (
            "an idle connection was held open")
    finally:
        wire.close()
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=PATIENCE)


def test_this_server_answers_the_version_that_keeps_the_connection(live):
    """The version itself, pinned once and here.

    Everything else in this module is about the obligations that come WITH the
    version; this is the version. It is asserted in one place on purpose --
    every other suite reads the refusal it is about and leaves the protocol to
    this one, so a deliberate change lands in a single expectation rather than
    in whichever rows happened to spell a status line out.
    """
    wire = _wire(live)
    try:
        wire.send("GET /state.json HTTP/1.1")
        line, _, _ = wire.answer()

        assert line.startswith("HTTP/1.1 200"), line
        assert server.Handler.protocol_version == "HTTP/1.1"
    finally:
        wire.close()


def test_a_client_that_vanishes_mid_stream_takes_nothing_with_it(live):
    """The other half of the stream's story: the client leaves first.

    A stream is the one road here that outlives its request, so it is also the
    one where a client going away is ordinary rather than exceptional. It must
    cost this server the connection and nothing else -- not the thread, not the
    next client, and not the shutdown.

    Checked separately from the framing above because they are separate
    claims: that one says the stream announces how it ends, this one says the
    server survives the end it did not choose.
    """
    _srv, address = live
    watcher = Wire(address, f"127.0.0.1:{address[1]}")
    watcher.send("GET /events HTTP/1.1")
    while b"data:" not in watcher.buffer:
        assert watcher._fill(), "the stream opened and said nothing"

    watcher.close()                        # gone, mid-frame, with no goodbye

    after = _wire(live)
    try:
        after.send("GET /state.json HTTP/1.1")
        line, _, payload = after.answer()
        assert _status(line) == 200 and json.loads(payload)["project"]
        # And a second stream still opens: the registry did not keep the seat
        # of a client that is not there.
        again = _wire(live)
        try:
            again.send("GET /events HTTP/1.1")
            while b"data:" not in again.buffer:
                assert again._fill(), "no stream after a client vanished"
        finally:
            again.close()
    finally:
        after.close()
