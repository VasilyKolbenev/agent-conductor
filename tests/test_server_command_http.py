"""Real loopback coverage for the frozen Cockpit command routes."""
from __future__ import annotations

import http.client
import json
import socket
import threading

from conductor import server
from conductor.command.adapters import AdapterRegistry
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_adapters import FakeAdapter
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


def _read_frame(response) -> str:
    """Read exactly one SSE frame, blocking until its terminating blank line."""
    lines: list[bytes] = []
    while True:
        line = response.readline()
        assert line, "the SSE stream ended before its next frame"
        lines.append(line)
        if line == b"\n":
            return b"".join(lines).decode("utf-8")


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
    adapter = FakeAdapter()
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
    subject, store = _start(tmp_path, adapters=(FakeAdapter(),))
    # The stream is read while a loaded machine may still be delivering; the
    # derivation module waits this long for the same reason.
    connection = http.client.HTTPConnection(
        "127.0.0.1", subject.server_address[1], timeout=20)
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
        assert (refused[0], refused[1]["error"]["code"]) == (
            409, "capability_unsupported")
        assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    finally:
        subject.shutdown()
        subject.server_close()


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
            assert response.startswith(b"HTTP/1.0 400")
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
        assert response.startswith(b"HTTP/1.0 400")
        assert b'"code":"malformed_request"' in response
        assert b"Traceback" not in response
        assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    finally:
        subject.shutdown()
        subject.server_close()
