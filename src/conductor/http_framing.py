"""How one answer is framed on a connection this server means to keep.

Split out of ``server`` when that module reached its line cap with this subject
owed, and the subject is a real one: everything here is about the SHAPE of an
answer on the wire, and nothing about which answer a route chooses.

It earned its own file the day this server stopped closing the connection after
every response. Under HTTP/1.0 the close WAS the frame, so a badly framed answer
could not be observed: a HEAD that wrote a body, a stream with no length, a
request body nobody read -- each ended at the same hang-up as a correct one. One
page boot cost 34 accepted TCP connections that way; the browser gate runs
hundreds of pages; Windows ran out of socket buffer space, a Studio module
failed to load with WSAENOBUFS, and the reverse gate went red.

Keeping the connection is the repair, and it moves those three from invisible to
fatal: whatever is left on the connection is read as the start of the next
request. So the obligations live together, in front of the routes that spend
them, and `tests/test_server_http_framing.py` reads each one off a real socket.
"""
from __future__ import annotations

from conductor.command.http_transport import (
    HttpRefusal, announces_a_body, command_content_length)

#: How long a kept connection may sit idle before this server gives it up.
#: A persistent connection holds a thread here, one per socket, and the browser
#: gate opens hundreds of pages per run -- so an unreaped connection trades a
#: socket storm for a thread leak. Five seconds is far longer than the ~90ms a
#: whole page boot takes, so every request of one boot still shares the six
#: connections it opened, and far shorter than a browser's own idle keep-alive.
IDLE_CONNECTION_SECONDS = 5.0


class KeptConnection:
    """The framing half of the handler: its version, its lifetime, its answers.

    A mixin rather than free functions because every one of these speaks
    through ``BaseHTTPRequestHandler``'s own writing surface --
    ``send_response``, ``send_header``, ``rfile``, ``close_connection`` -- and a
    function taking the handler as an argument would be the same coupling with
    a longer name.

    What it needs from the class it is mixed into is stated rather than assumed:
    that writing surface, and nothing else. It chooses no route, reads no path,
    and knows nothing about what this server serves.
    """

    #: Answer HTTP/1.1 and keep the connection. Under HTTP/1.0 every response
    #: ended by hanging up, so one Studio boot cost 34 accepted TCP connections
    #: instead of 6 -- measured -- and that churn is what exhausts Windows
    #: socket buffers and fails a JS module with WSAENOBUFS mid-gate.
    #:
    #: Keeping it is not free of obligations, and they are why this is more than
    #: one line: a HEAD may write no body, a stream with no length must say the
    #: close is its frame, and a body this server answers without reading must
    #: be consumed or the connection ended.
    #: `tests/test_server_http_framing.py` reads each of those off a socket.
    protocol_version = "HTTP/1.1"
    timeout = IDLE_CONNECTION_SECONDS
    #: The ONE method whose handlers own their request body. Every other body
    #: is settled at the entrance below, before any route runs -- so a GET that
    #: carries one, a method no handler exists for, and whatever method is added
    #: next are covered BECAUSE they are not named. What this replaces was a
    #: list of the requests that must drain, and it missed two entrances by
    #: construction: GET on both surfaces, and the road `send_error(501)` takes.
    #:
    #: POST keeps its body because both of its roads decide about it before a
    #: byte is read. The command route checks Host, Origin, CSRF, content type
    #: and framing and refuses WITHOUT reading on any failure; the refused-POST
    #: road consumes through the bounded door or closes. Settling a POST body at
    #: the entrance would read it before those checks had spoken.
    BODY_READING_METHODS = frozenset({"POST"})

    def parse_request(self) -> bool:
        """Parse as the standard library does, then settle the body before any route.

        Every request crosses this, and crosses it before dispatch -- including
        the ones no handler exists for, which go on to `send_error(501)` and
        from there to the command refusal. That is what makes it the entrance: a
        route chosen afterwards cannot answer over bytes still on the
        connection, because by then there are none, or the connection is
        already ending and says so.

        Nothing is loosened by moving it here. The body goes through the same
        bounded door as before -- one `Content-Length`, no `Transfer-Encoding`,
        under the ceiling -- and a framing that door will not trust is never
        read on the client's word: the connection ends instead. A request that
        announces no body at all is untouched, so a browser's ordinary GET
        keeps its connection.

        Two more ways in were found by an adversarial sweep after this entrance
        landed, and both are about what the standard library READ before any
        code here runs -- which is why they are settled here and not per route.
        """
        if not super().parse_request():
            return False
        if self.request_version == "HTTP/0.9":
            # No status line, no headers, no length: the close is the only frame
            # such an answer can have, and no route here serves without headers.
            # On the newer standard library these arrive with `headers = {}` and
            # the first route to read one raised; on the older one a 0.9 request
            # carrying `Connection: keep-alive` was answered unframed on a
            # connection this server KEPT. `send_error` says `Connection: close`,
            # which is what ends it on both.
            self.send_error(505, "HTTP/0.9 is not served")
            return False
        if self.headers.get_payload():
            # The header block did not parse whole. The parser stops at the
            # first line it cannot read as a header -- a space before the colon
            # is enough -- and keeps every line after it as payload: those bytes
            # are already off the socket, but `Content-Length` among them never
            # reached `self.headers`, so the body would read as "none" and be
            # parsed as the next request. A length this server does not know is
            # not one it guesses at: the route still answers -- a command
            # refusal keeps its JSON envelope -- and the connection ends.
            self.close_connection = True
            return True
        if self.command not in self.BODY_READING_METHODS:
            self._drain_unread_body()
        return True

    def _drain_refused_body(self) -> None:
        """Consume a refused POST body before answering it with a 404.

        A route this server does not own still owes an ANSWER, and answering
        over a body still sitting unread leaves what the client reads to the
        platform rather than to this code. Draining first removes that from
        chance. It is deliberately not claimed to fix an observed reset: on the
        machine this landed on, the 404 arrived either way at every size the
        ceiling admits.

        The framing is the SAME bounded door the command route trusts -- one
        Content-Length, no Transfer-Encoding, under the fixed ceiling -- so
        there is no second dialect here, and nothing parses, retains or serves a
        byte of what it drains. A body that door cannot measure is not consumed
        on the client's word at all, and neither is one the client never
        finishes: both close the connection, which is the only honest end for a
        request whose length this server does not know.
        """
        try:
            length = command_content_length(self.headers.raw_items())
        except HttpRefusal:
            self.close_connection = True
            return
        try:
            drained = self.rfile.read(length)
        except OSError:
            self.close_connection = True
            return
        if len(drained) != length:
            self.close_connection = True
    def _send_body(
            self, status: int, content_type: str, body: bytes, *,
            write_body: bool = True) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        if self.close_connection:
            # Already decided to hang up -- a body this server could not read,
            # a length it would not trust. Say so, rather than letting the
            # client discover it by reading end-of-file where it expected the
            # next answer.
            self.send_header("Connection", "close")
        self.end_headers()
        if write_body:
            self.wfile.write(body)
    def _drain_unread_body(self) -> None:
        """A road that answers without reading still owes the connection an end.

        A request naming neither `Content-Length` nor `Transfer-Encoding`
        carries no body at all: nothing was sent, nothing is left, and the
        connection is already exactly where the next request starts. Asking that
        FIRST is what lets a browser's bodyless `HEAD` or `OPTIONS` keep its
        connection instead of being retired for a body it never had.

        Anything else goes through the same bounded door the POST road trusts,
        with the same answer when that door refuses: a length this server will
        not take on the client's word ends the connection.
        """
        if not announces_a_body(self.headers.raw_items()):
            return
        self._drain_refused_body()
    def _send_404(self, *, head: bool = False) -> None:
        self._send_body(404, "text/plain; charset=utf-8", b"not found\n",
                        write_body=not head)
