"""The pure Cockpit route facade binds frozen transport to durable facts."""
from __future__ import annotations

import json
import os

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.http_api import COMMAND_ROUTES, CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession, MAX_COMMAND_BODY_BYTES
from conductor.command.run_store import RunStore, snapshot_digest

from tests.test_command_adapters import FakeAdapter
from tests.test_command_run_store import CONFIG, a_run


RUN_ID = "run-001"
NOW = "2026-08-13T12:00:00Z"
TOKEN = "current-process-token"
PORT = 7802


def ids():
    counters = {}

    def mint(kind):
        counters[kind] = counters.get(kind, 0) + 1
        return f"{kind}-api-{counters[kind]}"

    return mint


def api(tmp_path, *, adapters=None, published=None, clock=lambda: NOW):
    store = RunStore(tmp_path)
    store.create_run(a_run(
        run_id=RUN_ID, mode="confirm", config_digest=snapshot_digest(CONFIG)), CONFIG)
    registry = AdapterRegistry(
        [FakeAdapter()] if adapters is None else adapters)
    events = [] if published is None else published
    subject = CommandApi(
        store, registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=clock, ids=ids(),
        publish_run=events.append)
    return subject, store, events


def get_headers(host=f"127.0.0.1:{PORT}"):
    return (("Host", host),)


def post_headers(body, *, token=TOKEN, origin=f"http://127.0.0.1:{PORT}",
                 host=f"127.0.0.1:{PORT}", length=None):
    encoded = encode(body)
    return (
        ("Host", host), ("Origin", origin), ("X-Conduct-CSRF", token),
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(encoded) if length is None else length)),
    )


def encode(body):
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def proposal_body():
    return {
        "instance_id": "claude-dev",
        "attempt_id": "attempt-001",
        "capability": "dispatch",
        "arguments": {
            "work_item_id": "work-001",
            "instruction_ref": "instruction-001",
            "profile": "implement",
            "artifact_refs": ["artifact-001"],
            "output_limit_profile": "small",
        },
        "scope": ["src", "tests"],
        "proposed_by": "claude-dev",
        "rationale": "Implement the reviewed work item.",
        "timeout_seconds": 900,
    }


def confirm_body(proposal):
    return {
        "proposal_id": proposal["proposal_id"],
        "preview_digest": proposal["preview_digest"],
        "capability": proposal["capability"],
        "scope": proposal["scope"],
        "config_digest": proposal["config_digest"],
        "confirmed_by": "release-owner",
    }


def decision_body(**changes):
    values = {
        "receipt_id": "decision-001",
        "gate_id": "release",
        "action": "approve",
        "actor": "release-owner",
        "reason": "Reviewed the durable result.",
        "scope_refs": ["src", "tests"],
        "evidence_refs": [],
        "supersedes": None,
    }
    values.update(changes)
    return values


def post(subject, path, body, **header_changes):
    return subject.handle(
        "POST", path, post_headers(body, **header_changes), encode(body))


def test_exact_route_allowlist_and_wrong_method_or_path_are_closed(tmp_path):
    assert COMMAND_ROUTES == (
        ("GET", "/command/session"),
        ("GET", "/command/runs/<run_id>"),
        ("GET", "/command/runs/<run_id>/controls"),
        ("POST", "/command/runs/<run_id>/proposals"),
        ("POST", "/command/runs/<run_id>/actions"),
        ("POST", "/command/runs/<run_id>/decisions"),
        ("POST", "/command/runs/<run_id>/graph"),
    )
    subject, _, _ = api(tmp_path)
    wrong = subject.handle("POST", "/command/session", (), b"")
    absent = subject.handle("GET", "/command/runs/run-001/future", get_headers())
    assert (wrong.status, wrong.payload["error"]["code"]) == (
        ERROR_STATUS["method_not_allowed"], "method_not_allowed")
    assert (absent.status, absent.payload["error"]["code"]) == (
        ERROR_STATUS["route_not_found"], "route_not_found")


@pytest.mark.parametrize(
    "path", [path for method, path in COMMAND_ROUTES if method == "POST"])
def test_no_mutating_route_signals_anything_it_was_refused(tmp_path, path):
    """The signal half of the transport rule, closed as a class.

    Each route's own tests prove it publishes when it appended. This proves the
    other direction for ALL of them at once, derived from the allowlist rather
    than remembered: a route that announced a change before validating one
    would tell every listening browser to re-read bytes that never moved, and a
    route added later inherits the check without anyone remembering to add it.
    """
    subject, store, events = api(tmp_path)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    before = journal.read_bytes()

    # A real token and a real route, so the HANDLER runs and refuses -- a stale
    # token would be turned away by the transport and would prove nothing about
    # what the handler does with a body it cannot use.
    refused = post(subject, path.replace("<run_id>", RUN_ID), {})

    assert (refused.status, refused.payload["error"]["code"]) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid")
    assert events == [] and journal.read_bytes() == before


def test_session_and_run_read_use_host_gate_and_exact_store_wrappers(tmp_path):
    subject, store, _ = api(tmp_path)
    session = subject.handle("GET", "/command/session", get_headers())
    read = subject.handle("GET", f"/command/runs/{RUN_ID}", get_headers())
    recovered = store.read(RUN_ID)
    assert session == type(session)(200, {
        "csrf_token": TOKEN, "origin": f"http://127.0.0.1:{PORT}"})
    assert read.status == 200
    assert read.payload["run"] == recovered.envelope.as_dict()
    assert read.payload["config"] == CONFIG
    assert read.payload["records"] == [] and read.payload["warnings"] == []
    denied = subject.handle(
        "GET", f"/command/runs/{RUN_ID}", (("Host", "attacker.test"),))
    assert denied.payload["error"]["code"] == "same_origin_denied"


def test_controls_are_frozen_binding_manifest_schema_intersection(tmp_path):
    subject, _, _ = api(tmp_path)
    response = subject.handle(
        "GET", f"/command/runs/{RUN_ID}/controls", get_headers())
    assert response.payload == {"instances": [{
        "instance_id": "claude-dev",
        "adapter_id": "claude-code",
        "controls": ["dispatch"],
    }, {
        "instance_id": "codex-review",
        "adapter_id": "codex",
        "controls": [],
    }], "providers": []}


def test_empty_registry_keeps_reads_and_decisions_but_refuses_proposals(tmp_path):
    subject, _, events = api(tmp_path, adapters=[])
    assert subject.handle(
        "GET", f"/command/runs/{RUN_ID}", get_headers()).status == 200
    controls = subject.handle(
        "GET", f"/command/runs/{RUN_ID}/controls", get_headers())
    assert controls.payload["instances"][0]["controls"] == []
    refused = post(subject, f"/command/runs/{RUN_ID}/proposals", proposal_body())
    assert refused.payload["error"]["code"] == "capability_unsupported"
    decision = post(subject, f"/command/runs/{RUN_ID}/decisions", decision_body())
    assert decision.status == 201 and events == [RUN_ID]


def test_propose_confirm_decide_and_exact_retries_have_honest_status(tmp_path):
    adapter = FakeAdapter()
    subject, store, events = api(tmp_path, adapters=[adapter])
    proposed = post(subject, f"/command/runs/{RUN_ID}/proposals", proposal_body())
    confirmed = post(
        subject, f"/command/runs/{RUN_ID}/actions",
        confirm_body(proposed.payload))
    retry = post(
        subject, f"/command/runs/{RUN_ID}/actions",
        confirm_body(proposed.payload))
    decided = post(subject, f"/command/runs/{RUN_ID}/decisions", decision_body())
    decision_retry = post(
        subject, f"/command/runs/{RUN_ID}/decisions", decision_body())

    assert (proposed.status, confirmed.status, retry.status) == (201, 201, 200)
    assert retry.payload == confirmed.payload
    assert (decided.status, decision_retry.status) == (201, 200)
    assert decision_retry.payload == decided.payload
    assert events == [RUN_ID, RUN_ID, RUN_ID]
    assert [row.kind for row in store.read(RUN_ID).records] == [
        "action_proposal", "action_request", "decision"]
    assert adapter.preparations == 0


def test_changed_decision_retry_is_conflict_and_emits_no_event(tmp_path):
    subject, store, events = api(tmp_path)
    first = post(subject, f"/command/runs/{RUN_ID}/decisions", decision_body())
    journal = store.run_path(RUN_ID) / "records.jsonl"
    before = journal.read_bytes()
    conflict = post(subject, f"/command/runs/{RUN_ID}/decisions", decision_body(
        action="reject", reason="Rejected after review."))
    assert first.status == 201
    assert (conflict.status, conflict.payload["error"]["code"]) == (
        409, "record_conflict")
    assert journal.read_bytes() == before and events == [RUN_ID]


@pytest.mark.parametrize("length", [None, -1, MAX_COMMAND_BODY_BYTES + 1])
def test_content_length_is_exactly_one_nonnegative_bounded_value(tmp_path, length):
    subject, store, events = api(tmp_path)
    body = proposal_body()
    headers = list(post_headers(body))
    if length is None:
        headers = [row for row in headers if row[0] != "Content-Length"]
    else:
        headers[-1] = ("Content-Length", str(length))
    before = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()
    response = subject.handle(
        "POST", f"/command/runs/{RUN_ID}/proposals", headers, encode(body))
    assert (response.status, response.payload["error"]["code"]) == (
        400, "malformed_request")
    assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    assert events == []


def test_duplicate_content_length_and_declared_byte_mismatch_are_malformed(tmp_path):
    subject, _, _ = api(tmp_path)
    body = proposal_body()
    headers = post_headers(body)
    duplicate = (*headers, ("content-length", str(len(encode(body)))))
    for planted in (duplicate, post_headers(body, length=len(encode(body)) - 1)):
        response = subject.handle(
            "POST", f"/command/runs/{RUN_ID}/proposals", planted, encode(body))
        assert response.payload["error"]["code"] == "malformed_request"


def test_transport_precedence_stays_host_then_origin_csrf_content_and_body(tmp_path):
    subject, _, _ = api(tmp_path)
    body = proposal_body()
    oversized = post_headers(
        body, host="attacker.test", origin="http://attacker.test",
        token="foreign", length=MAX_COMMAND_BODY_BYTES + 1)
    response = subject.handle(
        "POST", f"/command/runs/{RUN_ID}/proposals", oversized, encode(body))
    assert response.payload["error"]["code"] == "same_origin_denied"


@pytest.mark.parametrize("change,expected_message", [
    ({"origin": "http://attacker.test"}, "request origin is not allowed"),
    ({"token": "foreign"}, "request CSRF token is not current"),
])
def test_transfer_encoding_does_not_jump_ahead_of_origin_or_csrf(
        tmp_path, change, expected_message):
    subject, _, _ = api(tmp_path)
    body = proposal_body()
    raw = (*post_headers(body, **change), ("Transfer-Encoding", "chunked"))
    response = subject.handle(
        "POST", f"/command/runs/{RUN_ID}/proposals", raw, encode(body))
    assert response.payload["error"] == {
        "code": "same_origin_denied" if "origin" in change else "csrf_denied",
        "message": expected_message,
        "detail": {},
    }


def test_content_type_precedes_transfer_encoding_in_the_body_phase(tmp_path):
    subject, _, _ = api(tmp_path)
    body = proposal_body()
    raw = tuple(
        (name, "text/plain") if name == "Content-Type" else (name, value)
        for name, value in post_headers(body))
    raw = (*raw, ("Transfer-Encoding", "chunked"))
    response = subject.handle(
        "POST", f"/command/runs/{RUN_ID}/proposals", raw, encode(body))
    assert response.payload["error"]["message"] == (
        "request Content-Type is not supported")


def test_typed_route_violation_refuses_before_append_and_event(tmp_path):
    subject, store, events = api(tmp_path)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    alias = tmp_path / "foreign-journal"
    try:
        os.link(journal, alias)
    except OSError as error:
        pytest.skip(f"hard links unavailable: {error}")
    before = journal.read_bytes()
    response = post(subject, f"/command/runs/{RUN_ID}/proposals", proposal_body())
    assert (response.status, response.payload["error"]["code"]) == (
        409, "route_unsafe")
    assert journal.read_bytes() == before and events == []


def test_no_expected_refusal_retains_exception_prose(tmp_path):
    subject, _, _ = api(tmp_path, adapters=[])
    response = post(subject, f"/command/runs/{RUN_ID}/proposals", proposal_body())
    encoded = json.dumps(response.payload)
    assert "not registered" not in encoded and "Traceback" not in encoded


def test_unknown_instance_uses_the_closed_structured_service_fact(tmp_path):
    subject, store, events = api(tmp_path)
    body = {**proposal_body(), "instance_id": "ghost-dev"}
    before = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()
    response = post(subject, f"/command/runs/{RUN_ID}/proposals", body)
    assert response.payload == {"error": {
        "code": "service_refused",
        "message": "frozen config declares no instance 'ghost-dev'",
        "detail": {"run_id": RUN_ID, "instance_id": "ghost-dev"},
    }}
    assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before
    assert events == []


def test_missing_run_stays_the_frozen_generic_store_error(tmp_path):
    subject, _, _ = api(tmp_path)
    response = subject.handle(
        "GET", "/command/runs/missing-run", get_headers())
    assert (response.status, response.payload["error"]["code"]) == (
        500, "store_error")
