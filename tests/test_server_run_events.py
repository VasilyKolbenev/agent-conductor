"""Identifier-only command signals are additive to the existing state SSE."""
from __future__ import annotations

import http.client
import json

import pytest

from conductor import server

from tests.test_command_http_api import RUN_ID, decision_body
from tests.test_server_command_http import _request, _start


STATE_FRAME = b'data: {"kind":"state"}\n'


def _stream(subject):
    connection = http.client.HTTPConnection(
        "127.0.0.1", subject.server_address[1], timeout=5)
    connection.request("GET", "/events")
    response = connection.getresponse()
    assert response.status == 200
    assert response.readline() == STATE_FRAME
    assert response.readline() == b"\n"
    return connection, response


def _next_payload(response):
    while True:
        line = response.readline()
        assert line, "SSE stream ended before its queued signal"
        if line.strip():
            assert line.startswith(b"data: ")
            return json.loads(line[len(b"data: "):])


def test_new_durable_record_publishes_one_identifier_only_frame_to_each_client(
        tmp_path):
    subject, _store = _start(tmp_path)
    first = second = None
    try:
        first = _stream(subject)
        second = _stream(subject)
        response = _request(
            subject, "POST", f"/command/runs/{RUN_ID}/decisions",
            decision_body())
        assert response[0] == 201
        assert _next_payload(first[1]) == {"kind": "run", "run_id": RUN_ID}
        assert _next_payload(second[1]) == {"kind": "run", "run_id": RUN_ID}
    finally:
        for opened in (first, second):
            if opened is not None:
                opened[1].close()
                opened[0].close()
        subject.shutdown()
        subject.server_close()


def test_mailbox_coalesces_duplicates_without_losing_distinct_run_ids():
    mailbox = server._Mailbox()
    mailbox.publish_run("run-a")
    mailbox.publish_run("run-a")
    mailbox.publish_run("run-b")
    frames = mailbox.drain()
    assert frames == (
        b'data: {"kind":"run","run_id":"run-a"}\n\n',
        b'data: {"kind":"run","run_id":"run-b"}\n\n',
    )
    mailbox.publish_run("run-c")
    assert mailbox.drain() == (
        b'data: {"kind":"run","run_id":"run-c"}\n\n',)


def test_slow_client_queue_is_bounded_and_uses_state_resync_on_overflow():
    mailbox = server._Mailbox()
    for index in range(server.MAX_PENDING_RUNS + 20):
        mailbox.publish_run(f"run-{index}")
    frames = mailbox.drain()
    assert len(frames) == server.MAX_PENDING_RUNS + 1
    assert frames[0] == b'data: {"kind":"state"}\n\n'
    assert all(b'"kind":"run"' in frame for frame in frames[1:])


def test_shutdown_wake_does_not_fabricate_a_state_or_run_frame():
    mailbox = server._Mailbox()
    mailbox.wake()
    assert mailbox.wait(0.01) is True
    assert mailbox.drain() == ()


@pytest.mark.parametrize("run_id", ["", "../foreign", "run\nsecret", 17])
def test_run_signal_refuses_unvalidated_identity_without_rendering_it(run_id):
    with pytest.raises(ValueError, match="validated run id"):
        server._run_frame(run_id)
