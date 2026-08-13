"""Executable pins for the C/API-0 cockpit command API freeze.

These tests bind the frozen interface spec
(``docs/specs/2026-08-13-cockpit-command-api.md``) to the CMD-1 contracts. Every
``<!-- CANONICAL:name -->`` example in that document is parsed out and pushed
through ``contracts.py`` (``from_dict`` / ``as_dict`` / ``canonical_json``),
proving the frozen shapes CAN carry each example and that each is already
canonical. The expected sides are written test-locally, so a pin trips if either
the spec example or a contract drifts -- the two sides never come from one
production function.

The same-origin / anti-CSRF section validates the request-shaped fixtures in
``tests/fixtures/cockpit_command_csrf_fixtures.json``. Those fixtures are data
for the PENDING Day-2 C/API-1 gate; no endpoint implements them at this SHA.
This module therefore checks only their structure and their internal
accept/refuse relation against the frozen error vocabulary -- it makes NO claim
that any server accepts or refuses them today.
"""
from __future__ import annotations

import hmac
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    DecisionReceipt,
    EvidenceRef,
    RunEnvelope,
    canonical_json,
    gate_decision,
)

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = _ROOT / "docs" / "specs" / "2026-08-13-cockpit-command-api.md"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cockpit_command_csrf_fixtures.json"
_BOUNDARY_FIXTURES = (
    Path(__file__).resolve().parent / "fixtures" / "cockpit_command_boundary_fixtures.json")
_SERVER = _ROOT / "src" / "conductor" / "server.py"

RUN_ID = "run-cockpit-001"

#: Every canonical example the freeze document is required to carry.
REQUIRED_EXAMPLES = frozenset({
    "route_table", "session_response", "refusal_shape", "error_codes", "config",
    "argument_schemas",
    "propose_request", "action_proposal", "confirm_request", "action_request",
    "decision_request", "decision_receipt", "run_read_response", "controls_response",
    "action_result_receipt", "evidence_ref", "stream_frames", "mutation_boundary",
})

#: Canonical examples that are a full contract serialization, mapped to the
#: contract that must round-trip them.
CONTRACT_EXAMPLES = {
    "action_proposal": ActionProposal,
    "action_request": ActionRequest,
    "decision_receipt": DecisionReceipt,
    "action_result_receipt": ActionResultReceipt,
    "evidence_ref": EvidenceRef,
}

#: The frozen refusal vocabulary, written out here so the spec cannot drift it
#: silently; the spec's ``error_codes`` example is checked against this set.
EXPECTED_ERRORS = {
    "same_origin_denied": (403, "http_security"),
    "csrf_denied": (403, "http_security"),
    "method_not_allowed": (405, "routing"),
    "route_not_found": (404, "routing"),
    "malformed_request": (400, "http_shape"),
    "contract_invalid": (422, "contract"),
    "run_corrupt": (409, "store"),
    "store_error": (500, "store"),
    "route_unsafe": (409, "route_gate"),
    "service_refused": (409, "service"),
    "capability_unsupported": (409, "capability"),
    "authorization_refused": (409, "authorization"),
    "record_conflict": (409, "store"),
}
EXPECTED_ERROR_CODES = frozenset(EXPECTED_ERRORS)

EXPECTED_ROUTES = (
    ("GET", "/command/session", False, False),
    ("GET", "/command/runs/<run_id>", False, False),
    ("GET", "/command/runs/<run_id>/controls", False, False),
    ("POST", "/command/runs/<run_id>/proposals", True, True),
    ("POST", "/command/runs/<run_id>/actions", True, True),
    ("POST", "/command/runs/<run_id>/decisions", True, True),
)

EXPECTED_ARGUMENT_SCHEMAS = {
    "message": ("message",), "dispatch": ("handoff",), "review": ("handoff",),
    "evidence": ("action_id",), "pause": ("action_id",),
    "resume": ("action_id",), "retry": ("action_id",),
    "stop": ("action_id",), "switch": ("action_id", "instance_id"),
    "notify": ("message",),
}

PROPOSE_REQUIRED = frozenset({
    "instance_id", "attempt_id", "capability", "arguments", "scope", "proposed_by",
    "rationale", "timeout_seconds",
})
PROPOSE_ALLOWED = PROPOSE_REQUIRED | {"adapter_id"}
CONFIRM_FIELDS = frozenset({
    "proposal_id", "preview_digest", "capability", "scope", "config_digest",
    "confirmed_by",
})
DECISION_FIELDS = frozenset({
    "receipt_id", "gate_id", "action", "actor", "reason", "scope_refs",
    "evidence_refs", "supersedes",
})
UNRESTRICTED_KEYS = frozenset({
    "cmd", "command", "script", "shell", "argv", "executable", "cwd", "path",
    "env", "env_allow",
})

_CANON_RE = re.compile(
    r"<!-- CANONICAL:(?P<name>[a-z0-9_]+) -->\n```json\n(?P<body>.*?)\n```",
    re.DOTALL,
)


def _load_canonical() -> dict[str, object]:
    text = _SPEC.read_text(encoding="utf-8")
    out: dict[str, object] = {}
    for match in _CANON_RE.finditer(text):
        name = match.group("name")
        if name in out:
            raise AssertionError(f"duplicate canonical example {name!r} in the spec")
        out[name] = json.loads(match.group("body"))
    return out


def _load_fixtures() -> dict:
    return json.loads(_FIXTURES.read_text(encoding="utf-8"))


def _load_boundary_fixtures() -> dict:
    return json.loads(_BOUNDARY_FIXTURES.read_text(encoding="utf-8"))


CANON = _load_canonical()


def test_the_spec_carries_every_required_canonical_example():
    assert REQUIRED_EXAMPLES <= set(CANON), REQUIRED_EXAMPLES - set(CANON)


def test_route_table_is_an_exact_allowlist_and_every_mutation_requires_csrf():
    rows = tuple(
        (row["method"], row["path"], row["mutation"], row["csrf"])
        for row in CANON["route_table"])
    assert rows == EXPECTED_ROUTES
    assert all(csrf for _method, _path, mutation, csrf in rows if mutation)
    assert {method for method, _path, mutation, _csrf in rows if mutation} == {"POST"}


def test_api_zero_has_no_production_command_endpoint_yet():
    server = _SERVER.read_text(encoding="utf-8")
    assert "/command/" not in server
    assert "X-Conduct-CSRF" not in server


def test_session_and_stream_shapes_carry_no_durable_payload_or_secret_field():
    assert CANON["session_response"] == {
        "csrf_token": "<process-token>", "origin": "http://127.0.0.1:7802"}
    assert CANON["stream_frames"] == [
        {"kind": "state"}, {"kind": "run", "run_id": RUN_ID}]
    assert all("record" not in frame for frame in CANON["stream_frames"])


def test_browser_mutation_boundary_has_no_generic_write_category():
    assert CANON["mutation_boundary"] == {
        "routed_now": [
            "validated_command_proposal", "fresh_action_confirmation",
            "human_decision_receipt",
        ],
        "reserved_after_own_freeze": ["explicitly_confirmed_design_edit"],
        "forbidden": [
            "agent_event", "agent_lane", "adapter_secret", "arbitrary_file",
            "prompt", "source_file",
        ],
    }


@pytest.mark.parametrize("name", sorted(CONTRACT_EXAMPLES))
def test_every_contract_example_round_trips_through_its_contract(name):
    example = CANON[name]
    contract = CONTRACT_EXAMPLES[name]
    obj = contract.from_dict(example)
    # The frozen shape carries the example and re-serializes to exactly it.
    assert obj.as_dict() == example
    # A second parse of that serialization is byte-stable in canonical form.
    assert canonical_json(contract.from_dict(obj.as_dict())) == canonical_json(obj)


def test_run_envelope_and_run_read_response_bind_to_the_run_contract():
    read = CANON["run_read_response"]
    assert set(read) == {"run", "config", "records", "warnings"}
    envelope = RunEnvelope.from_dict(read["run"])
    assert envelope.as_dict() == read["run"]
    assert envelope.run_id == RUN_ID
    # Every read record is wrapped exactly as RunStore wraps a journal line.
    for wrapper in read["records"]:
        assert set(wrapper) == {"record_type", "record"}
        assert wrapper["record_type"] == "action_proposal"
        proposal = ActionProposal.from_dict(wrapper["record"])
        assert proposal.as_dict() == wrapper["record"]


def test_proposal_response_is_the_request_plus_only_server_injected_fields():
    request = CANON["propose_request"]
    response = CANON["action_proposal"]
    # adapter_id is a routing hint, not an ActionProposal field.
    built = ActionProposal(
        proposal_id=response["proposal_id"],
        run_id=RUN_ID,
        attempt_id=request["attempt_id"],
        instance_id=request["instance_id"],
        capability=request["capability"],
        arguments=request["arguments"],
        scope=tuple(request["scope"]),
        proposed_by=request["proposed_by"],
        proposed_at=response["proposed_at"],
        timeout_seconds=request["timeout_seconds"],
        rationale=request["rationale"],
        config_digest=response["config_digest"],
    )
    # The digest is derived by the contract, never carried by the request.
    assert "preview_digest" not in request
    assert built.preview_digest == response["preview_digest"]
    assert built.as_dict() == response


def test_request_shapes_are_closed_and_do_not_borrow_contract_extra():
    proposal = CANON["propose_request"]
    assert PROPOSE_REQUIRED <= set(proposal) <= PROPOSE_ALLOWED
    assert set(CANON["confirm_request"]) == CONFIRM_FIELDS
    assert set(CANON["decision_request"]) == DECISION_FIELDS
    assert CANON["decision_request"]["receipt_id"] == CANON["decision_receipt"]["receipt_id"]


def test_argument_schema_registry_is_exact_and_has_no_command_escape_key():
    actual = {name: tuple(fields) for name, fields in CANON["argument_schemas"].items()}
    assert actual == EXPECTED_ARGUMENT_SCHEMAS
    assert "observe" not in actual
    assert not ({field for fields in actual.values() for field in fields}
                & UNRESTRICTED_KEYS)


def test_confirm_response_is_the_unchanged_proposal_plus_fresh_confirmation():
    request = CANON["confirm_request"]
    proposal = CANON["action_proposal"]
    response = CANON["action_request"]
    # The confirm echoes the stored proposal's digest unchanged.
    assert request["preview_digest"] == proposal["preview_digest"]
    assert response["preview_digest"] == proposal["preview_digest"]
    assert request["capability"] == proposal["capability"]
    assert request["scope"] == proposal["scope"]
    assert request["config_digest"] == proposal["config_digest"]
    assert response["requested_by"] == request["confirmed_by"]
    assert response["idempotency_key"] == f"dispatch-{proposal['proposal_id']}"
    assert response["mode"] == "confirm"
    # These fields are copied from the proposal, byte for byte.
    for shared in ("attempt_id", "instance_id", "capability", "arguments",
                   "scope", "timeout_seconds"):
        assert response[shared] == proposal[shared]
    built = ActionRequest(
        action_id=response["action_id"],
        run_id=RUN_ID,
        attempt_id=proposal["attempt_id"],
        instance_id=proposal["instance_id"],
        capability=proposal["capability"],
        arguments=proposal["arguments"],
        scope=tuple(proposal["scope"]),
        requested_by=request["confirmed_by"],
        requested_at=response["requested_at"],
        idempotency_key=f"dispatch-{proposal['proposal_id']}",
        timeout_seconds=proposal["timeout_seconds"],
        preview_digest=request["preview_digest"],
        mode=response["mode"],
    )
    assert built.as_dict() == response


def test_accepted_and_succeeded_never_collapse_into_one_record():
    action = CANON["action_request"]
    receipt = CANON["action_result_receipt"]
    # The request is one record; the result is a separate record that names it.
    assert "outcome" not in action
    assert receipt["action_id"] == action["action_id"]
    assert receipt["outcome"] == "succeeded"
    assert ActionRequest.from_dict(action).action_id == receipt["action_id"]


def test_gate_decision_projects_the_receipt_and_absence_stays_idle():
    receipt = DecisionReceipt.from_dict(CANON["decision_receipt"])
    assert gate_decision([receipt], RUN_ID, "release") == "satisfied"
    # Absence of any receipt is idle, never a pass (ADR 0001 section 4).
    assert gate_decision([], RUN_ID, "release") == "idle"
    reject = DecisionReceipt.from_dict(
        {**CANON["decision_receipt"], "receipt_id": "decision-cockpit-002",
         "action": "reject"})
    assert gate_decision([reject], RUN_ID, "release") == "failed"


def test_action_request_mode_cannot_be_observe_or_propose():
    for forbidden in ("observe", "propose"):
        with pytest.raises(ContractError):
            ActionRequest.from_dict({**CANON["action_request"], "mode": forbidden})


def test_a_malformed_identifier_is_refused_at_the_boundary():
    # Maps to contract_invalid (422): the boundary never stores an invented id.
    with pytest.raises(ContractError):
        RunEnvelope.from_dict({**CANON["run_read_response"]["run"],
                               "run_id": "not a valid id"})


def test_unknown_top_level_fields_survive_a_round_trip():
    extended = {**CANON["run_read_response"]["run"], "future_hint": {"x": 1}}
    assert RunEnvelope.from_dict(extended).as_dict()["future_hint"] == {"x": 1}


def test_controls_are_only_schema_backed_values_and_have_no_disabled_state():
    rows = CANON["controls_response"]["instances"]
    assert rows == sorted(rows, key=lambda row: row["instance_id"])
    for row in rows:
        assert set(row) == {"instance_id", "adapter_id", "controls"}
        assert row["controls"] == sorted(row["controls"])
        assert set(row["controls"]) <= set(EXPECTED_ARGUMENT_SCHEMAS)


def test_frozen_error_code_vocabulary_matches_the_spec():
    rows = CANON["error_codes"]
    actual = {row["code"]: (row["status"], row["source"]) for row in rows}
    assert actual == EXPECTED_ERRORS
    for row in rows:
        assert set(row) == {"code", "status", "source"}
        assert row["status"] in {400, 403, 404, 405, 409, 422, 500}
        assert isinstance(row["source"], str) and row["source"]


def test_refusal_shape_is_closed_and_carries_only_sanitized_identifiers():
    refusal = CANON["refusal_shape"]
    assert set(refusal) == {"error"}
    assert set(refusal["error"]) == {"code", "message", "detail"}
    assert refusal["error"]["code"] in EXPECTED_ERROR_CODES
    assert set(refusal["error"]["detail"]) == {"run_id", "instance_id"}
    encoded = json.dumps(refusal, sort_keys=True)
    assert "csrf" not in encoded.casefold()
    assert "traceback" not in encoded.casefold()


def test_store_taxonomy_never_invents_a_not_found_subtype_from_prose():
    statuses = {row["code"]: row["status"] for row in CANON["error_codes"]}
    assert statuses["run_corrupt"] == 409
    assert statuses["store_error"] == 500
    assert statuses["record_conflict"] == 409
    assert "run_not_found" not in statuses


# --- Fixtures for the PENDING Day-2 C/API-1 gate (structure only) -----------

def _status_for_code() -> dict[str, int]:
    return {row["code"]: row["status"] for row in CANON["error_codes"]}


def _fixtures():
    return _load_fixtures()["fixtures"]


def _same_request_origin(headers: dict[str, str], allowed_hosts: set[str]) -> bool:
    host = headers.get("Host")
    if host not in allowed_hosts:
        return False
    expected = f"http://{host}"
    if "Origin" in headers:
        return headers["Origin"] == expected
    referer = urlsplit(headers.get("Referer", ""))
    return f"{referer.scheme}://{referer.netloc}" == expected


def _json_content_type(headers: dict[str, str]) -> bool:
    return headers.get("Content-Type", "").casefold() in {
        "application/json", "application/json; charset=utf-8",
    }


def test_csrf_fixtures_are_marked_as_a_pending_gate_not_a_behaviour_claim():
    data = _load_fixtures()
    assert "PENDING" in data["_readme"] and "NOT" in data["_readme"]
    assert data["_pending_gate"] == "C/API-1 (Day 2)"
    assert data["csrf_header"] == "X-Conduct-CSRF"
    assert set(data["loopback_origins"]) == {
        f"http://{host}" for host in data["loopback_hosts"]}
    assert len({
        data["current_process_token"], data["prior_process_token"],
        data["attacker_token"],
    }) == 3


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["name"])
def test_each_csrf_fixture_is_wellformed(fixture):
    assert set(fixture) >= {"name", "note", "request", "expected"}
    request = fixture["request"]
    assert set(request) >= {"method", "path", "headers", "csrf_token_source"}
    assert request["csrf_token_source"] in {"current_process", "prior_process",
                                            "attacker", "none"}
    expected = fixture["expected"]
    assert expected["disposition"] in {"accept", "refuse"}
    if expected["disposition"] == "refuse":
        assert expected["error_code"] in EXPECTED_ERROR_CODES
        assert expected["status"] == _status_for_code()[expected["error_code"]]
    else:
        assert expected["error_code"] is None
        assert expected["status"] == 201


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["name"])
def test_token_provenance_label_and_literal_header_agree_independently(fixture):
    data = _load_fixtures()
    token_by_source = {
        "current_process": data["current_process_token"],
        "prior_process": data["prior_process_token"],
        "attacker": data["attacker_token"],
        "none": None,
    }
    presented = fixture["request"]["headers"].get(data["csrf_header"])
    assert presented == token_by_source[fixture["request"]["csrf_token_source"]]


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda f: f["name"])
def test_each_csrf_fixture_encodes_the_documented_accept_refuse_relation(fixture):
    data = _load_fixtures()
    request, headers = fixture["request"], fixture["request"]["headers"]
    origin_ok = _same_request_origin(headers, set(data["loopback_hosts"]))
    presented = headers.get(data["csrf_header"])
    expected_token = data["current_process_token"]
    token_ok = presented is not None and hmac.compare_digest(presented, expected_token)
    content_ok = _json_content_type(headers) and isinstance(request.get("json_body"), dict)
    disposition = fixture["expected"]["disposition"]
    # Accept iff origin, current-process token, and JSON-object body all hold.
    assert (disposition == "accept") == (origin_ok and token_ok and content_ok)
    if disposition == "refuse":
        if not origin_ok:
            expected_code = "same_origin_denied"
        elif not token_ok:
            expected_code = "csrf_denied"
        else:
            expected_code = "malformed_request"
        assert fixture["expected"]["error_code"] == expected_code


def test_presented_token_and_process_memory_token_are_two_real_sides():
    data = _load_fixtures()
    accepted = next(row for row in _fixtures()
                    if row["name"] == "valid_same_origin_with_token")
    presented = accepted["request"]["headers"][data["csrf_header"]]
    expected = data["current_process_token"]
    assert presented == expected
    assert not hmac.compare_digest(data["prior_process_token"], expected)
    assert not hmac.compare_digest(data["attacker_token"], expected)


def _boundary_cases():
    return _load_boundary_fixtures()["proposal_cases"]


def _proposal_disposition(case: dict) -> tuple[str, str | None]:
    body = case["body"]
    if not isinstance(body, dict) or not PROPOSE_REQUIRED <= set(body) <= PROPOSE_ALLOWED:
        return "refuse", "contract_invalid"
    capability = body["capability"]
    schema = EXPECTED_ARGUMENT_SCHEMAS.get(capability)
    if schema is None or capability not in case["adapter_capabilities"]:
        return "refuse", "capability_unsupported"
    arguments = body["arguments"]
    if not isinstance(arguments, dict) or set(arguments) != set(schema):
        return "refuse", "contract_invalid"
    if set(arguments) & UNRESTRICTED_KEYS:
        return "refuse", "contract_invalid"
    id_pattern = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
    for name, value in arguments.items():
        if name == "message":
            if not isinstance(value, str) or not value.strip() or "\x00" in value:
                return "refuse", "contract_invalid"
        elif not isinstance(value, str) or id_pattern.fullmatch(value) is None:
            return "refuse", "contract_invalid"
    try:
        ActionProposal(
            proposal_id="proposal-boundary", run_id=RUN_ID,
            attempt_id=body["attempt_id"], instance_id=body["instance_id"],
            capability=capability, arguments=arguments, scope=tuple(body["scope"]),
            proposed_by=body["proposed_by"], proposed_at="2026-08-13T12:01:00Z",
            timeout_seconds=body["timeout_seconds"], rationale=body["rationale"],
            config_digest="sha256:" + "a" * 64)
    except ContractError:
        return "refuse", "contract_invalid"
    return "accept", None


@pytest.mark.parametrize("case", _boundary_cases(), ids=lambda row: row["name"])
def test_boundary_fixture_relation_is_fail_closed(case):
    actual_disposition, actual_code = _proposal_disposition(case)
    assert actual_disposition == case["expected"]["disposition"]
    assert actual_code == case["expected"]["error_code"]


@pytest.mark.parametrize(
    "case", _load_boundary_fixtures()["control_cases"], ids=lambda row: row["name"])
def test_unsupported_controls_are_absent_not_decorative(case):
    controls = sorted(
        set(case["manifest_capabilities"]) & set(EXPECTED_ARGUMENT_SCHEMAS))
    assert controls == case["expected_controls"]
