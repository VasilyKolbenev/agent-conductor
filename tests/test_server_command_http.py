"""Real loopback coverage for the frozen Cockpit command routes."""
from __future__ import annotations

import contextlib
import http.client
import io
import json
import socket
import threading
import time

import pytest

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_adapters import FakeAdapter
from tests.test_command_schema_doubles import DeepDispatchAdapter
from tests.test_command_graph_route import graph_body
from tests.test_command_http_api import (
    NOW,
    RUN_ID,
    TOKEN,
    confirm_body,
    decision_body,
    proposal_body,
)
from tests.test_command_run_store import CONFIG, a_run
from tests.test_store import good_lane, write_project


def _ids():
    counts = {}

    def mint(kind):
        counts[kind] = counts.get(kind, 0) + 1
        return f"{kind}-server-{counts[kind]}"

    return mint


def _start(tmp_path, *, adapters=()):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    store = RunStore(root)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)), CONFIG)
    subject = server.build(
        root, 0, registry=AdapterRegistry(adapters), clock=lambda: NOW,
        ids=_ids(), token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    return subject, store


#: How long one frame may take to arrive. The loaded-machine allowance these tests always had;
#: the connections that read frames are opened with it too.
FRAME_BUDGET = 20.0


def _wait_at_most(response, seconds: float) -> None:
    """Let the next read of a real HTTP response wait no longer than `seconds`.

    The socket's own wait is a per-read figure and a heartbeat renews it; a stream with no
    socket (an in-memory one, a double) has no wait to cut.
    """
    if isinstance(response, http.client.HTTPResponse):
        response.fp.raw._sock.settimeout(seconds)


def _read_frame(response, *, budget: float = FRAME_BUDGET, clock=time.monotonic) -> str:
    """Read exactly one SSE frame, blocking until its terminating blank line.

    A block of comments only -- the stream's ": ping" heartbeat after a quiet
    spell -- is not a frame, exactly as an EventSource ignores it: on a loaded
    machine a signal can take longer than one heartbeat period to arrive.

    The heartbeat comes more often than the socket gives up, so skipping comments must not
    renew the wait: the whole read has ONE deadline on the monotonic clock, and every read
    inside it waits no longer than what is left of it.
    """
    deadline = clock() + budget
    failure = f"no SSE frame within {budget} s"
    lines: list[bytes] = []
    while True:
        remaining = deadline - clock()
        assert remaining > 0, failure
        _wait_at_most(response, remaining)
        try:
            line = response.readline()
        except TimeoutError:
            raise AssertionError(failure) from None
        assert line, "the SSE stream ended before its next frame"
        if line.startswith(b":") or (line == b"\n" and not lines):
            continue
        lines.append(line)
        if line == b"\n":
            return b"".join(lines).decode("utf-8")


def test_the_frame_reader_passes_over_a_heartbeat_as_an_event_source_does():
    stream = io.BytesIO(b": ping\n\n: ping\n\ndata: {\"kind\":\"state\"}\n\n")
    assert _read_frame(stream) == 'data: {"kind":"state"}\n\n'


class _OnlyHeartbeats:
    """A stream that says nothing but ": ping", and a clock that moves one second per line."""

    RUNAWAY = 1000

    def __init__(self) -> None:
        self.now = 0.0
        self.lines = 0

    def clock(self) -> float:
        return self.now

    def readline(self) -> bytes:
        self.lines += 1
        if self.lines > self.RUNAWAY:
            raise RuntimeError(f"still reading comments after {self.RUNAWAY} lines")
        self.now += 1.0
        return b": ping\n" if self.lines % 2 else b"\n"


def test_a_frame_reader_that_hears_only_heartbeats_fails_at_its_deadline_and_not_never():
    feed = _OnlyHeartbeats()
    with pytest.raises(AssertionError, match="no SSE frame within 5.0 s"):
        _read_frame(feed, budget=5.0, clock=feed.clock)
    assert feed.lines == 5, "the reader read on past the second its deadline fell"


@contextlib.contextmanager
def _response_over(sent: bytes, *, socket_wait: float):
    """A real `HTTPResponse` on one end of a socket pair, `sent` already written by the other.

    Yields the response and the socket it reads from.
    """
    ours, theirs = socket.socketpair()
    try:
        theirs.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                       b"Connection: close\r\n\r\n" + sent)
        ours.settimeout(socket_wait)
        response = http.client.HTTPResponse(ours)
        response.begin()
        try:
            yield response, ours
        finally:
            response.close()
    finally:
        ours.close()
        theirs.close()


def test_the_frame_reader_returns_data_that_follows_heartbeats_on_a_real_socket():
    sent = b": ping\n\n: ping\n\ndata: {\"kind\":\"state\"}\n\n"
    with _response_over(sent, socket_wait=3.0) as (response, _socket):
        assert _read_frame(response, budget=3.0) == 'data: {"kind":"state"}\n\n'


def test_a_later_read_on_a_real_socket_waits_only_what_is_left_of_the_deadline():
    """Two lines of one heartbeat are read; the third read is given what is left, not the budget.

    The clock is a script and nothing more is ever sent: the deadline is taken at 0.0 and the
    reads are made at 0.1, 0.2 and 0.3 s, so the third has 0.35 - 0.3 = 0.05 s left. A reader
    that gave every read the whole budget, or cut the wait once before its loop, leaves the
    socket at 0.35 s here; one that left the socket's own wait alone leaves 4 s.
    """
    ticks = iter([0.0, 0.1, 0.2, 0.3])      # the deadline, then one tick before each read
    with _response_over(b": ping\n\n", socket_wait=4.0) as (response, held):
        with pytest.raises(AssertionError, match="no SSE frame within 0.35 s"):
            _read_frame(response, budget=0.35, clock=lambda: next(ticks))
        assert held.gettimeout() == pytest.approx(0.05), held.gettimeout()


def _request(subject, method, path, body=None, *, headers=None):
    port = subject.server_address[1]
    encoded = None if body is None else json.dumps(
        body, separators=(",", ":")).encode("utf-8")
    supplied = {} if headers is None else dict(headers)
    if encoded is not None:
        supplied.update({
            "Origin": f"http://127.0.0.1:{port}",
            "X-Conduct-CSRF": TOKEN,
            "Content-Type": "application/json",
        })
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=encoded, headers=supplied)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw), dict(response.headers)
    finally:
        connection.close()


def _raw(subject, headers, body=b""):
    port = subject.server_address[1]
    request = (
        f"POST /command/runs/{RUN_ID}/decisions HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        f"Origin: http://127.0.0.1:{port}\r\n"
        f"X-Conduct-CSRF: {TOKEN}\r\n"
        "Content-Type: application/json\r\n"
        + "".join(f"{name}: {value}\r\n" for name, value in headers)
        + "Connection: close\r\n\r\n"
    ).encode("ascii") + body
    with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
        client.sendall(request)
        client.shutdown(socket.SHUT_WR)
        response = bytearray()
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
    return bytes(response)


def test_session_uses_assigned_port_and_process_token(tmp_path):
    subject, _store = _start(tmp_path)
    try:
        status, payload, headers = _request(subject, "GET", "/command/session")
        port = subject.server_address[1]
        assert status == 200
        assert payload == {
            "csrf_token": TOKEN, "origin": f"http://127.0.0.1:{port}"}
        assert headers["Cache-Control"] == "no-store"
        assert "Set-Cookie" not in headers and "Access-Control-Allow-Origin" not in headers
    finally:
        subject.shutdown()
        subject.server_close()


def test_real_http_propose_confirm_decide_and_retries_are_durable(tmp_path):
    # Declares the argument family it serves: a proposal meets the same pair
    # authority a plan does, and a schema-less double is refused before append.
    adapter = DeepDispatchAdapter()
    subject, store = _start(tmp_path, adapters=(adapter,))
    try:
        prefix = f"/command/runs/{RUN_ID}"
        proposed = _request(subject, "POST", prefix + "/proposals", proposal_body())
        confirmed = _request(
            subject, "POST", prefix + "/actions", confirm_body(proposed[1]))
        retry = _request(
            subject, "POST", prefix + "/actions", confirm_body(proposed[1]))
        # The server performs the confirmed effect on its own worker; waiting for
        # that worker to settle is what makes the durable order below fixed.
        assert subject.command_execution.wait_idle(10) is True
        decided = _request(subject, "POST", prefix + "/decisions", decision_body())
        decision_retry = _request(
            subject, "POST", prefix + "/decisions", decision_body())
        read = _request(subject, "GET", prefix)

        assert [row[0] for row in (proposed, confirmed, retry)] == [201, 201, 200]
        assert retry[1] == confirmed[1]
        assert [row[0] for row in (decided, decision_retry)] == [201, 200]
        assert decision_retry[1] == decided[1]
        expected = [
            "action_proposal", "action_request", "attempt_event", "attempt_event",
            "action_result", "decision"]
        assert [row["record_type"] for row in read[1]["records"]] == expected
        assert [row.kind for row in store.read(RUN_ID).records] == expected
        # The duplicate Confirm authorized nothing new, so exactly one action was
        # prepared. This fixture refuses to execute, and a lost result closes the
        # attempt `unknown` -- it is never promoted to success.
        assert adapter.preparations == 1
        assert [row["record"]["outcome"] for row in read[1]["records"]
                if row["record_type"] == "action_result"] == ["unknown"]
    finally:
        subject.shutdown()
        subject.server_close()


def test_real_http_writes_a_plan_once_and_signals_it_by_identifier_only(tmp_path):
    """The graph over a real socket: one write, one signal, one authoritative read.

    The signal is the whole point of the shape. A browser learns that something
    happened and re-reads bytes the contracts validated; the plan itself never
    travels on the stream, where safety law 8 would have to police it.
    """
    # The adapter DECLARES the argument family it serves: the graph route holds
    # every bound node to the schema the registry recorded for that pair, and a
    # schema-less double would be refused before a signal was ever published.
    subject, store = _start(tmp_path, adapters=(DeepDispatchAdapter(),))
    # The stream is read while a loaded machine may still be delivering; the
    # derivation module waits this long for the same reason.
    connection = http.client.HTTPConnection(
        "127.0.0.1", subject.server_address[1], timeout=FRAME_BUDGET)
    try:
        connection.request("GET", "/events")
        stream = connection.getresponse()
        assert stream.status == 200
        assert _read_frame(stream) == 'data: {"kind":"state"}\n\n'

        prefix = f"/command/runs/{RUN_ID}"
        written = _request(subject, "POST", prefix + "/graph", graph_body())
        signal = _read_frame(stream)
        again = _request(subject, "POST", prefix + "/graph", graph_body())
        read = _request(subject, "GET", prefix)

        assert written[0] == 201 and again[0] == 200
        assert again[1] == written[1]
        assert signal == 'data: {"kind":"run","run_id":"%s"}\n\n' % RUN_ID
        assert set(json.loads(signal[len("data: "):])) == {"kind", "run_id"}
        assert read[1]["graph"]["definition"] == written[1]
        assert read[1]["graph"]["runtime"]["graph_id"] == "graph-001"
        assert [row.kind for row in store.read(RUN_ID).records] == [
            "graph_definition"]
    finally:
        connection.close()
        subject.shutdown()
        subject.server_close()


def test_real_http_publishes_an_artifact_and_only_its_run_identifier(tmp_path):
    subject, store = _start(tmp_path)
    connection = http.client.HTTPConnection(
        "127.0.0.1", subject.server_address[1], timeout=FRAME_BUDGET)
    document = {
        "artifact_id": "artifact-document-001",
        "artifact_ref": "artifact-brief",
        "media_type": "text/markdown",
        "content": "# Brief\nReview the durable handoff, not a path.",
    }
    try:
        connection.request("GET", "/events")
        stream = connection.getresponse()
        assert stream.status == 200
        assert _read_frame(stream) == 'data: {"kind":"state"}\n\n'

        prefix = f"/command/runs/{RUN_ID}"
        created = _request(subject, "POST", prefix + "/artifacts", document)
        signal = _read_frame(stream)
        retried = _request(subject, "POST", prefix + "/artifacts", document)
        read = _request(subject, "GET", prefix)
        no_collection = _request(subject, "GET", prefix + "/artifacts")

        assert created[0] == 201 and retried[0] == 200
        assert retried[1] == created[1]
        assert signal == 'data: {"kind":"run","run_id":"%s"}\n\n' % RUN_ID
        assert set(json.loads(signal[len("data: "):])) == {"kind", "run_id"}
        assert read[1]["records"] == [{
            "record_type": "artifact", "record": created[1]}]
        assert [row.kind for row in store.read(RUN_ID).records] == ["artifact"]
        assert no_collection[0] == 405
    finally:
        connection.close()
        subject.shutdown()
        subject.server_close()


def test_wrong_command_methods_and_unknown_routes_are_closed_json(tmp_path):
    subject, _store = _start(tmp_path)
    try:
        known = _request(subject, "OPTIONS", "/command/session")
        arbitrary = _request(subject, "FROB", "/command/session")
        unknown = _request(subject, "DELETE", "/command/future")
        queried = _request(subject, "GET", "/command/session?extra=1")
        assert (known[0], known[1]["error"]["code"]) == (
            405, "method_not_allowed")
        assert (arbitrary[0], arbitrary[1]["error"]["code"]) == (
            405, "method_not_allowed")
        assert (unknown[0], unknown[1]["error"]["code"]) == (
            404, "route_not_found")
        assert (queried[0], queried[1]["error"]["code"]) == (
            404, "route_not_found")
    finally:
        subject.shutdown()
        subject.server_close()


def test_default_empty_registry_keeps_reads_but_refuses_proposals(tmp_path):
    subject, store = _start(tmp_path)
    try:
        prefix = f"/command/runs/{RUN_ID}"
        controls = _request(subject, "GET", prefix + "/controls")
        before = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()
        refused = _request(subject, "POST", prefix + "/proposals", proposal_body())
        assert controls[1]["instances"][0]["controls"] == []
        # The binding is resolved before the capability is asked about, so an
        # adapter this process never registered is a service fact.
        assert (refused[0], refused[1]["error"]["code"]) == (
            409, "service_refused")
        assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    finally:
        subject.shutdown()
        subject.server_close()


def _status_code(response: bytes) -> int:
    """The code off a raw status line, without pinning the HTTP version here.

    The version is a real decision -- this server answers HTTP/1.1 and keeps
    the connection, which is what stopped one page boot costing 34 of them --
    and it is pinned once, in `tests/test_server_http_framing.py`, beside the
    framing obligations that come with it. These rows are about a REFUSAL, so
    they read the refusal and let that module own the version.
    """
    return int(response.split(b"\r\n", 1)[0].split(b" ")[1])


def test_invalid_framing_refuses_without_waiting_for_or_reading_a_body(tmp_path):
    subject, store = _start(tmp_path)
    try:
        before = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()
        cases = (
            (("Content-Length", "65537"),),
            (("Content-Length", "2"), ("content-length", "2")),
            (("Transfer-Encoding", "chunked"),),
            (("Content-Length", "2"), ("Transfer-Encoding", "chunked")),
        )
        for headers in cases:
            response = _raw(subject, headers)
            assert _status_code(response) == 400
            assert b'"code":"malformed_request"' in response
        assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    finally:
        subject.shutdown()
        subject.server_close()


def test_short_body_is_fixed_malformed_and_connection_is_retired(tmp_path):
    subject, store = _start(tmp_path)
    try:
        before = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()
        response = _raw(subject, (("Content-Length", "10"),), b"{}")
        assert _status_code(response) == 400
        assert b'"code":"malformed_request"' in response
        assert b"Traceback" not in response
        assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    finally:
        subject.shutdown()
        subject.server_close()
