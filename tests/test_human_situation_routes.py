"""Future atomic-wire witnesses; prepared externally, not executed or accepted.

The native witness uses the existing bounded HTTP/T5 fixture. An actual live
queue and a fresh durable-only reader must agree on uncertainty, without a GET
reconciling, authorizing or releasing the queued worker.
"""
from conductor.command import studio_routes
from conductor.command.graph_projection import graph_payload
from conductor.command.run_store import RunStore, snapshot_digest
from tests.test_command_http_api import api, get_headers, RUN_ID
from tests.test_command_run_store import CONFIG, a_run
from tests.test_server_attempt_scope import HostedAttempt, WAIT, PROBE
from tests.test_server_command_http import _request

READ_AT = "2026-09-21T15:00:00.123Z"


def durable_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def get(subject, path):
    return subject.handle("GET", path, get_headers())


def test_run_detail_and_list_derive_the_same_state_and_get_never_writes(tmp_path):
    subject, _store, published = api(tmp_path, clock=lambda: READ_AT)
    before = durable_bytes(tmp_path)
    detail = get(subject, f"/command/runs/{RUN_ID}")
    listed = get(subject, "/command/runs")
    assert detail.status == listed.status == 200
    situation = detail.payload["graph"]["situation"]
    assert situation["state"] == "not_required" and situation["computed_at"] == READ_AT
    assert listed.payload["runs"][0]["human_state"] == situation["state"]
    assert len(situation["checked"]) == 6 and situation["unknown_because"] == []
    assert published == [] and durable_bytes(tmp_path) == before


def test_one_list_read_supplies_one_instant_to_every_run_row(tmp_path, monkeypatch):
    calls, reads = [], []

    def clock():
        calls.append(READ_AT)
        return READ_AT

    subject, store, _published = api(tmp_path, clock=clock)
    store.create_run(a_run(run_id="run-002", mode="confirm",
        config_digest=snapshot_digest(CONFIG)), CONFIG)
    original = studio_routes.graph_payload

    def observed(recovered, *, computed_at):
        reads.append((recovered.envelope.run_id, computed_at))
        return original(recovered, computed_at=computed_at)

    monkeypatch.setattr(studio_routes, "graph_payload", observed)
    calls.clear()
    response = get(subject, "/command/runs")
    assert response.status == 200 and len(response.payload["runs"]) == 2
    assert calls == [READ_AT]
    assert reads == [(RUN_ID, READ_AT), ("run-002", READ_AT)]


def test_an_unreadable_run_is_listed_without_inventing_a_human_state(tmp_path):
    subject, store, _published = api(tmp_path, clock=lambda: READ_AT)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    journal.write_bytes(b"invalid-json\n")
    before = durable_bytes(tmp_path)
    listed = get(subject, "/command/runs")
    assert listed.status == 200
    row = listed.payload["runs"][0]
    assert row["run_id"] == RUN_ID and row["unreadable"] is True
    assert row["human_state"] is None
    assert durable_bytes(tmp_path) == before


def assert_queued_unknown(situation, action_id):
    assert situation["state"] == "unknown"
    assert situation["unknown_because"] == ["unobserved_request"]
    checked = {row["reason"]: row for row in situation["checked"]}
    assert checked["reconcile"] == {"reason": "reconcile", "count": 0, "sources": []}
    assert checked["confirmation"]["count"] == 0
    unknown = {row["reason"]: row for row in situation["unknown_sources"]}
    assert unknown["unobserved_request"]["count"] == 1
    assert unknown["unobserved_request"]["sources"] == [action_id]


def test_http_request_waiting_for_t5_is_unknown_and_fresh_read_cannot_call_it_abandoned(
        tmp_path, monkeypatch):
    flight = HostedAttempt(tmp_path, monkeypatch, window="before-check", reject=False)
    try:
        first = flight.confirm("a")
        assert first[0] == 201 and flight.reached.wait(WAIT)
        second = flight.confirm("b")
        assert second[0] == 201 and flight.gate.lock.waiting.wait(WAIT)
        assert not flight.gate.lock.entered.wait(PROBE) and not flight.path("b").exists()
        values = flight.store.read("run-b").records
        requests = [row.value.action_id for row in values if row.kind == "action_request"]
        assert len(requests) == 1
        assert not any(row.kind in {"attempt_event", "action_result"} for row in values)
        before = durable_bytes(flight.store.run_path("run-b"))
        calls = []

        def refuse_reconcile(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("a GET tried to reconcile a live queued request")

        monkeypatch.setattr(flight.subject.command_api.runtime, "reconcile", refuse_reconcile)
        status, body, _headers = _request(flight.subject, "GET", "/command/runs/run-b")
        assert status == 200
        situation = body["graph"]["situation"]
        assert_queued_unknown(situation, requests[0])
        fresh = RunStore(flight.root).read("run-b")
        assert graph_payload(fresh, computed_at=situation["computed_at"])["situation"] == situation
        assert calls == [] and not flight.gate.lock.entered.is_set()
        assert flight.subject.command_execution.placements() == 2
        assert durable_bytes(flight.store.run_path("run-b")) == before
    finally:
        flight.finish()
