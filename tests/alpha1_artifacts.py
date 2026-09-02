"""Derive the five frozen ALPHA-1 artifacts the Fable UI lane consumes.

Nothing here is hand-written. Every document is produced by driving two REAL
runs through the coordinator path and reading back what actually happened:

* the **gated run** is a ``CommandApi`` with one attached ``ExecutionCoordinator``
  worker, so a second confirmed action is provably still in the memory-only
  queue while the first is parked inside its adapter's execute seam. That is what
  makes the per-state visibility document honest rather than imagined.
* the **served run** is the real loopback server: a real socket, the frozen
  routes, a real SSE stream, and the server's own worker pool. It is the backend
  half of owner gate A, driven without a browser.

The documents are written to ``tests/fixtures/alpha1_*.json`` once and then
compared, by ``tests/test_alpha1_ui_lane_artifacts.py``, against a fresh
derivation on every run -- so production drifting away from a frozen artifact
reds instead of silently handing the UI lane a stale shape.
"""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

from conductor import server
from conductor.command.adapters.provider import (
    AVAILABILITY_STATES,
    IMPLEMENTATION_STATES,
    ProviderConfig,
    ProviderContract,
    provider_projection,
)
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.attempts import ATTEMPT_PHASES, OBSERVED_OUTCOMES
from conductor.command.contracts import (
    ActionResultReceipt,
    ContractError,
    canonical_json,
)
from conductor.command.coordinator import ExecutionCoordinator
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore
from conductor.command.runtime import AttemptState

from tests.alpha1_providers import NOW, a_proposal, a_store, ids, resolve
from tests.test_command_http_api import (
    PORT,
    RUN_ID,
    TOKEN,
    confirm_body,
    encode,
    post_headers,
)
from tests.test_server_command_http import _read_frame, _request
from tests.test_store import good_lane, write_project


FIXTURES = Path(__file__).resolve().parent / "fixtures"
#: Every frozen artifact, by the basename of its JSON document.
ARTIFACTS = (
    "alpha1_provider_projection",
    "alpha1_record_states",
    "alpha1_vocabulary",
    "alpha1_end_to_end",
    "alpha1_sse_relation",
)
PROVIDER_ID = "claude-code"
TAMPERED_DIGEST = "sha256:" + "0" * 64
WAIT = 20.0


def load(name: str) -> dict:
    """Read one frozen artifact document.

    Args:
        name: One of :data:`ARTIFACTS`.

    Returns:
        The parsed JSON document.

    Raises:
        ValueError: `name` is not a frozen artifact.
    """
    if name not in ARTIFACTS:
        raise ValueError(f"{name!r} is not an ALPHA-1 artifact")
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def plain(value: object) -> object:
    """Re-read one contract value as the exact JSON data a consumer receives."""
    return json.loads(canonical_json(value))


# -- the gated run: provider projection and per-state durable visibility --


def _records_for(recovered, action_id: str) -> list[dict]:
    """Every durable record a consumer can attribute to one action, in order."""
    request = next((
        row.value for row in recovered.records
        if row.kind == "action_request" and row.value.action_id == action_id), None)
    proposal_id = (
        None if request is None
        else request.idempotency_key[len("dispatch-"):])
    rows = []
    for row in recovered.records:
        if row.kind == "action_proposal":
            keep = row.value.proposal_id == proposal_id
        elif row.kind == "evidence":
            keep = row.value.uri == f"verification/{action_id}"
        else:
            keep = getattr(row.value, "action_id", None) == action_id
        if keep:
            rows.append({
                "record_type": row.kind, "record": plain(row.value.as_dict())})
    return rows


def _state_view(
        store, action_id: str, *, state: str, durable: bool, note: str,
        evidence: dict | None = None) -> dict:
    """Freeze what a consumer can see for one action at this exact instant."""
    rows = _records_for(store.read(RUN_ID), action_id)
    view = {
        "state": state,
        "durable": durable,
        "durable_record_types": [row["record_type"] for row in rows],
        "durable_records": rows,
    }
    if evidence is not None:
        view["evidence"] = evidence
    view["note"] = note
    return view


def _confirm(api, *, instance_id: str, attempt_id: str, work_item_id: str) -> str:
    proposal = a_proposal(
        instance_id=instance_id, attempt_id=attempt_id, work_item_id=work_item_id)
    proposed = api.handle(
        "POST", f"/command/runs/{RUN_ID}/proposals",
        post_headers(proposal), encode(proposal))
    assert proposed.status == 201, proposed.payload
    body = confirm_body(proposed.payload)
    confirmed = api.handle(
        "POST", f"/command/runs/{RUN_ID}/actions", post_headers(body), encode(body))
    assert confirmed.status == 201, confirmed.payload
    return confirmed.payload["action_id"]


def _gated_run(root: Path) -> dict:
    """Execute one gated run and read the five moments a consumer may observe."""
    mint = ids()
    store = a_store(root)
    resolution = resolve(root, mint)
    api = CommandApi(
        store, resolution.registry, session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=mint,
        publish_run=lambda _run_id: None)
    coordinator = ExecutionCoordinator(api.runtime)
    api.attach_execution(coordinator)
    coordinator.start()          # exactly one worker: a second action stays queued
    adapter = resolution.registry.resolve(PROVIDER_ID)
    adapter.evidence_sink = store.append
    adapter.verifies_with_evidence = True
    adapter.gates["execute"].clear()
    adapter.gates["verify"].clear()
    try:
        states = _gated_states(api, store, adapter, coordinator)
    finally:
        for gate in adapter.gates.values():
            gate.set()
        coordinator.shutdown()
    return {
        "projection": _projection_document(resolution),
        "states": {
            "run_id": RUN_ID,
            "derived_from": "one gated run through CommandApi + ExecutionCoordinator",
            "states": states,
        },
        "observed": _observed_vocabulary(store, resolution),
    }


def _observed_vocabulary(store, resolution) -> dict:
    """Read back only the vocabulary these real records and contracts produced."""
    rows = store.read(RUN_ID).records
    return {
        "attempt_event_phases": sorted({
            row.value.phase for row in rows if row.kind == "attempt_event"}),
        "observed_outcomes": sorted({
            row.value.outcome for row in rows
            if row.kind == "attempt_event" and row.value.outcome is not None}),
        "terminal_outcomes": sorted({
            row.value.outcome for row in rows if row.kind == "action_result"}),
        "availability_states": sorted(
            {row.availability for row in resolution.contracts}),
        "implementation_states": sorted(
            {row.implementation for row in resolution.contracts}),
    }


def _gated_states(api, store, adapter, coordinator) -> list[dict]:
    """Read each state at the instant a gate proves the run is standing in it."""
    first = _confirm(
        api, instance_id="claude-dev", attempt_id="attempt-001",
        work_item_id="work-001")
    assert adapter.wait_for("execute", first) is True
    second = _confirm(
        api, instance_id="claude-dev", attempt_id="attempt-002",
        work_item_id="work-002")
    states = [
        _queued_view(store, second, adapter, coordinator),
        _state_view(
            store, first, state="leased", durable=True,
            note=("The effect_lease attempt_event is appended before the first "
                  "adapter effect seam, so a consumer that sees it must treat "
                  "the effect as possibly performed.")),
    ]
    adapter.gates["execute"].set()
    assert adapter.wait_for("verify", first) is True
    states.append(_state_view(
        store, first, state="execution_observed", durable=True,
        note=("The execution_observed attempt_event records the outcome the "
              "adapter reported. It is durable and it is not yet the terminal "
              "word: no action_result exists.")))
    states.append(_state_view(
        store, first, state="verifying", durable=False,
        note=("Verifying is transient and no record names it. A consumer can "
              "only bracket it: it begins after the execution_observed event "
              "and ends when the action_result receipt lands, and its durable "
              "visibility is identical to execution_observed.")))
    adapter.gates["verify"].set()
    assert coordinator.wait_idle(WAIT) is True
    states.append(_state_view(
        store, first, state="terminal", durable=True,
        note=("The action_result receipt is the one terminal record. Verified "
              "evidence appears as an evidence record appended after the "
              "observation and referenced by the receipt.")))
    return states


def _queued_view(store, action_id: str, adapter, coordinator) -> dict:
    """Freeze the queued moment, with the counts that prove it is really queued."""
    return _state_view(
        store, action_id, state="queued", durable=False,
        evidence={
            "actions_placed_on_the_one_worker": coordinator.placements(),
            "adapter_execute_arrivals": [
                action for seam, action in adapter.arrivals if seam == "execute"],
        },
        note=("The queue is memory-only and holds no record of its own: the only "
              "durable trace of a queued action is its action_request, which does "
              "not say 'queued'. This action is provably queued because the "
              "coordinator placed two actions on its one worker and that worker "
              "is parked inside the other action's execute seam."))


def _projection_document(resolution) -> dict:
    """Freeze the projection rows and the availability vocabulary behind them."""
    rows = provider_projection(resolution.contracts)
    row_fields = sorted(rows[0])
    carried = set(ProviderConfig._FIELDS) | set(ProviderContract._FIELDS)
    return {
        "derived_from": (
            "conductor.command.adapters.provider.provider_projection over the "
            "ProviderResolution that drove the gated run"),
        "availability_vocabulary": sorted(AVAILABILITY_STATES),
        "implementation_vocabulary": sorted(IMPLEMENTATION_STATES),
        "resolved_availability": {
            row.provider_id: row.availability for row in resolution.contracts},
        "declared_implementation": {
            row.provider_id: row.implementation for row in resolution.contracts},
        "row_fields": row_fields,
        "rows": rows,
        "withheld_from_rows": sorted(carried - set(row_fields)),
        "note": ("A row answers two separate questions and keeps them apart: "
                 "`availability` is about the operator's machine, "
                 "`implementation` is about this build's transport, and the two "
                 "vocabularies share no value. Rows are joined by `provider_id`; "
                 "`display_name` is a label to render and never a fact to parse. "
                 "Everything else the operator config and the reviewed contract "
                 "carry is withheld."),
    }


# -- the served run: the HTTP/SSE end-to-end and the identifier-only relation --


def _served_run(root_parent: Path) -> dict:
    root = write_project(root_parent, lanes={"claude": good_lane()})
    mint = ids()
    store = a_store(root)
    resolution = resolve(root_parent, mint)
    adapter = resolution.registry.resolve(PROVIDER_ID)
    adapter.evidence_sink = store.append
    adapter.verifies_with_evidence = True
    adapter.gates["execute"].clear()
    subject = server.build(
        root, 0, registry=resolution.registry, clock=lambda: NOW, ids=mint,
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection(
        "127.0.0.1", subject.server_address[1], timeout=WAIT)
    try:
        connection.request("GET", "/events")
        stream = connection.getresponse()
        assert stream.status == 200
        return _served_steps(subject, store, adapter, stream)
    finally:
        adapter.gates["execute"].set()
        connection.close()
        subject.shutdown()
        subject.server_close()


def _served_steps(subject, store, adapter, stream) -> dict:
    """Drive propose -> Confirm -> async execute -> evidence -> refresh over HTTP."""
    frames = [_read_frame(stream)]
    proposed = _request(
        subject, "POST", f"/command/runs/{RUN_ID}/proposals",
        a_proposal(instance_id="claude-dev", attempt_id="attempt-001",
                   work_item_id="work-001"))
    assert proposed[0] == 201, proposed[1]
    frames.append(_read_frame(stream))
    body = confirm_body(proposed[1])
    confirmed = _request(subject, "POST", f"/command/runs/{RUN_ID}/actions", body)
    assert confirmed[0] == 201, confirmed[1]
    frames.append(_read_frame(stream))
    action_id = confirmed[1]["action_id"]
    at_response = [
        row["record_type"] for row in _records_for(store.read(RUN_ID), action_id)]

    adapter.gates["execute"].set()
    assert subject.command_execution.wait_idle(WAIT) is True
    frames.append(_read_frame(stream))
    duplicate = _request(subject, "POST", f"/command/runs/{RUN_ID}/actions", body)
    journal = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()
    tampered = _request(
        subject, "POST", f"/command/runs/{RUN_ID}/actions",
        {**body, "preview_digest": TAMPERED_DIGEST})
    assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == journal
    refreshed = _request(subject, "GET", f"/command/runs/{RUN_ID}")
    return {
        "end_to_end": _end_to_end_document(
            proposed, confirmed, at_response, duplicate, tampered, refreshed),
        "sse": _sse_document(frames),
    }


def _step(name: str, method: str, path: str, response, **extra) -> dict:
    return {
        "step": name, "method": method, "path": path,
        "status": response[0], "response": response[1], **extra}


def _end_to_end_document(
        proposed, confirmed, at_response, duplicate, tampered, refreshed) -> dict:
    """One deterministic backend transcript: the backend half of owner gate A."""
    return {
        "run_id": RUN_ID,
        "transport": "the frozen command routes over a real loopback socket",
        "steps": [
            _step("propose", "POST", f"/command/runs/{RUN_ID}/proposals", proposed),
            _step(
                "confirm", "POST", f"/command/runs/{RUN_ID}/actions", confirmed,
                durable_record_types_at_response=at_response,
                note=("The Confirm answered with the recorded action_request "
                      "while the adapter was still held inside execute, so no "
                      "result existed yet: the effect is asynchronous.")),
            _step(
                "duplicate_confirm", "POST", f"/command/runs/{RUN_ID}/actions",
                duplicate,
                note="The same request, answered 200, queued nothing and re-ran nothing."),
            _step(
                "refused_confirm", "POST", f"/command/runs/{RUN_ID}/actions",
                tampered,
                note=("A confirmation restating a changed preview digest is "
                      "refused before preparation and writes no durable byte.")),
            _step(
                "authoritative_refresh", "GET", f"/command/runs/{RUN_ID}", refreshed,
                note=("The durable truth after the effect: the request, both "
                      "attempt_events, the verification evidence and the "
                      "terminal action_result. The computed graph half is "
                      "present and empty: this run follows no plan.")),
        ],
    }


def _sse_document(frames: list[str]) -> dict:
    """Freeze the identifier-only stream relation, byte for byte."""
    return {
        "connect_frame": 'data: {"kind":"state"}\n\n',
        "run_frame": 'data: {"kind":"run","run_id":"%s"}\n\n' % RUN_ID,
        "run_frame_payload_keys": ["kind", "run_id"],
        "frames_read_in_order": frames,
        "note": ("A run frame carries the run id and nothing else -- no outcome, "
                 "no detail, no exit code, no adapter output -- and the v1 "
                 "state frame keeps flowing beside it unchanged."),
    }


# -- the vocabulary artifact --


def _receipt_outcomes() -> list[str]:
    """Every candidate outcome a canonical terminal receipt really accepts.

    Asked of the contract rather than copied from it: a state is terminal
    exactly when the one durable result receipt will hold it.
    """
    candidates = {state.value for state in AttemptState} | set(OBSERVED_OUTCOMES)
    accepted = []
    for candidate in sorted(candidates):
        try:
            ActionResultReceipt(
                receipt_id="probe-receipt", action_id="probe-action", run_id=RUN_ID,
                attempt_id="probe-attempt", instance_id="probe-instance",
                outcome=candidate, observed_at=NOW)
        except ContractError:
            continue
        accepted.append(candidate)
    return accepted


def _vocabulary_document(observed: dict) -> dict:
    """Hold every closed set the UI lane must not widen or narrow, as DATA."""
    receipt_outcomes = _receipt_outcomes()
    states = [state.value for state in AttemptState]
    return {
        "refusal_codes": dict(sorted(ERROR_STATUS.items())),
        "attempt_states": states,
        "terminal_states": [row for row in states if row in receipt_outcomes],
        "pre_terminal_states": [row for row in states if row not in receipt_outcomes],
        "receipt_outcomes": receipt_outcomes,
        "receipt_only_outcomes": [
            row for row in receipt_outcomes if row not in states],
        "observed_outcomes": sorted(OBSERVED_OUTCOMES),
        "attempt_event_phases": sorted(ATTEMPT_PHASES),
        "availability_states": sorted(AVAILABILITY_STATES),
        "implementation_states": sorted(IMPLEMENTATION_STATES),
        "observed_in_the_derived_runs": observed,
        "note": ("`rejected` is an outcome an adapter may report and a durable "
                 "receipt will hold, but it is never an attempt state: the "
                 "runtime resolves a rejected report to the terminal state "
                 "`failed`, which the pinning contract test drives and asserts."),
    }


def derive_all(gated_root: Path, served_root: Path) -> dict[str, dict]:
    """Execute both real runs and return all five artifact documents."""
    gated = _gated_run(gated_root)
    served = _served_run(served_root)
    observed = dict(gated["observed"])
    observed["refusal_codes"] = sorted({
        step["response"]["error"]["code"]
        for step in served["end_to_end"]["steps"] if step["status"] >= 400})
    return {
        "alpha1_provider_projection": gated["projection"],
        "alpha1_record_states": gated["states"],
        "alpha1_vocabulary": _vocabulary_document(observed),
        "alpha1_end_to_end": served["end_to_end"],
        "alpha1_sse_relation": served["sse"],
    }


def write_all(gated_root: Path, served_root: Path) -> None:
    """Re-freeze every artifact from a fresh pair of real runs."""
    for name, document in derive_all(gated_root, served_root).items():
        (FIXTURES / f"{name}.json").write_text(
            json.dumps(document, indent=2, sort_keys=False) + "\n",
            encoding="utf-8", newline="\n")


def a_run_store(root: Path) -> RunStore:
    """A reader that never saw the writing process, for replay comparisons."""
    return RunStore(root)
