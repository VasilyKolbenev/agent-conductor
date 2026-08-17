"""The loopback server performs the confirmed effect off the request thread.

These are the whole-server witnesses: a real socket, a real SSE stream, and the
server's own coordinator. The provider is the deterministic fixture admitted
through the session-1 provider door, and its effect blocks on an Event this test
owns, so "while the effect is still running" is held by a barrier, not a sleep.
"""
from __future__ import annotations

import http.client
import json
import threading

from conductor import server
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_execution_coordinator import (
    NOW,
    PROVIDER_ID,
    confirm_body,
    ids,
    proposal_body,
    provider_registry,
)
from tests.test_command_http_api import RUN_ID, TOKEN
from tests.test_command_run_store import CONFIG, a_run
from tests.test_server_command_http import _request
from tests.test_server_run_events import STATE_FRAME, _next_payload, _stream
from tests.test_store import good_lane, write_project


def _start(tmp_path):
    """Build a real server whose registry came out of the provider factory."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    store = RunStore(root)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)), CONFIG)
    mint = ids()
    registry = provider_registry(tmp_path, mint)
    subject = server.build(
        root, 0, registry=registry, clock=lambda: NOW, ids=mint,
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    return subject, store, registry.resolve(PROVIDER_ID)


def _propose(subject):
    status, payload, _headers = _request(
        subject, "POST", f"/command/runs/{RUN_ID}/proposals", proposal_body())
    assert status == 201, payload
    return payload


def _records(store):
    return [row.kind for row in store.read(RUN_ID).records]


def _confirm_and_abandon(subject, proposal):
    """Send one Confirm and drop the connection without reading the response."""
    port = subject.server_address[1]
    body = json.dumps(
        confirm_body(proposal), separators=(",", ":")).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(
        "POST", f"/command/runs/{RUN_ID}/actions", body=body, headers={
            "Origin": f"http://127.0.0.1:{port}",
            "X-Conduct-CSRF": TOKEN,
            "Content-Type": "application/json",
        })
    return connection


def test_a_client_that_vanishes_mid_effect_neither_cancels_nor_repeats_it(tmp_path):
    subject, store, adapter = _start(tmp_path)
    try:
        adapter.gate.clear()
        connection = _confirm_and_abandon(subject, _propose(subject))
        assert adapter.entered.wait(10) is True
        connection.close()             # the browser is gone mid-effect
        adapter.gate.set()
        assert subject.command_execution.wait_idle(10) is True
        assert adapter.executions == 1
        assert _records(store) == [
            "action_proposal", "action_request", "attempt_event", "attempt_event",
            "action_result"]
        results = [row.value for row in store.read(RUN_ID).records
                   if row.kind == "action_result"]
        assert [row.outcome for row in results] == ["succeeded"]
    finally:
        adapter.gate.set()
        subject.shutdown()
        subject.server_close()


def test_the_confirm_response_arrives_while_the_effect_is_still_unfinished(tmp_path):
    subject, store, adapter = _start(tmp_path)
    try:
        adapter.gate.clear()
        proposal = _propose(subject)
        status, payload, _headers = _request(
            subject, "POST", f"/command/runs/{RUN_ID}/actions",
            confirm_body(proposal))
        assert status == 201
        assert payload["action_id"] and payload["mode"] == "confirm"
        assert adapter.gate.is_set() is False
        assert "action_result" not in _records(store)
        adapter.gate.set()
        assert subject.command_execution.wait_idle(10) is True
        assert _records(store).count("action_result") == 1
    finally:
        adapter.gate.set()
        subject.shutdown()
        subject.server_close()


def test_execution_signals_stay_identifier_only_beside_the_v1_state_frame(tmp_path):
    subject, _store, adapter = _start(tmp_path)
    opened = None
    try:
        adapter.gate.clear()
        opened = _stream(subject)      # asserts the v1 state frame byte for byte
        proposal = _propose(subject)
        assert _next_payload(opened[1]) == {"kind": "run", "run_id": RUN_ID}
        status, _payload, _headers = _request(
            subject, "POST", f"/command/runs/{RUN_ID}/actions",
            confirm_body(proposal))
        assert status == 201
        assert _next_payload(opened[1]) == {"kind": "run", "run_id": RUN_ID}
        adapter.gate.set()
        assert subject.command_execution.wait_idle(10) is True
        # The observation and the terminal receipt announce the run and nothing
        # else: no outcome, no detail, no exit code, no captured output.
        assert _next_payload(opened[1]) == {"kind": "run", "run_id": RUN_ID}
        assert STATE_FRAME == b'data: {"kind":"state"}\n'
    finally:
        adapter.gate.set()
        if opened is not None:
            opened[1].close()
            opened[0].close()
        subject.shutdown()
        subject.server_close()


def test_server_shutdown_retires_every_worker_token_the_server_minted(tmp_path):
    subject, _store, _adapter = _start(tmp_path)
    coordinator = subject.command_execution
    try:
        assert len(coordinator.owned_tokens()) == server.EXECUTION_WORKERS
        assert coordinator.runtime is subject.command_api.runtime
    finally:
        subject.shutdown()
        subject.server_close()
    assert coordinator.owned_tokens() == ()
