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

import ast
import hmac
import importlib
import json
import re
from pathlib import Path
from typing import get_args, get_origin, get_type_hints
from urllib.parse import urlsplit

import pytest

from conductor.command import run_store as run_store_module
from conductor.command.adapters.deep_commands import DEEP_ARGUMENT_TYPES
from conductor.command.api_contracts import (
    ApiRefusal,
    parse_confirmation,
    parse_proposal,
)
from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.artifacts import ArtifactDocument
from conductor.command.containment import RouteViolation, run_route_violations
from conductor.command.graph_definition import GraphDefinition
from conductor.command.run_terminal import RunTerminal
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    DecisionReceipt,
    EvidenceRef,
    ObservationRecord,
    RunEnvelope,
    _id,
    canonical_json,
    gate_decision,
)

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = _ROOT / "docs" / "specs" / "2026-08-13-cockpit-command-api.md"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cockpit_command_csrf_fixtures.json"
_SERVER = _ROOT / "src" / "conductor" / "server.py"

RUN_ID = "run-cockpit-001"

#: Every canonical example the freeze document is required to carry.
REQUIRED_EXAMPLES = frozenset({
    "route_table", "route_dependency", "session_response", "refusal_shape",
    "error_codes", "config", "argument_schemas",
    "propose_request", "action_proposal", "confirm_request", "action_request",
    "decision_request", "decision_receipt", "run_read_response", "controls_response",
    "action_result_receipt", "evidence_ref", "attempt_event_effect_lease",
    "attempt_event_execution_observed", "stream_frames", "mutation_boundary",
    "graph_bound_propose_request", "graph_definition_record",
    "graph_bound_action_proposal", "graph_bound_action_request",
    "graph_request", "graph_runtime_projection",
    "artifact_request",
})

#: Canonical examples that are a full contract serialization, mapped to the
#: contract that must round-trip them.
CONTRACT_EXAMPLES = {
    "graph_bound_action_proposal": ActionProposal,
    "graph_bound_action_request": ActionRequest,
    "action_proposal": ActionProposal,
    "action_request": ActionRequest,
    "decision_receipt": DecisionReceipt,
    "action_result_receipt": ActionResultReceipt,
    "evidence_ref": EvidenceRef,
    "attempt_event_effect_lease": AttemptEvent,
    "attempt_event_execution_observed": AttemptEvent,
}

EXPECTED_RECORDS = {
    "action_request": (ActionRequest, "action_id"),
    "action_result": (ActionResultReceipt, "receipt_id"),
    "evidence": (EvidenceRef, "evidence_id"),
    "decision": (DecisionReceipt, "receipt_id"),
    "action_proposal": (ActionProposal, "proposal_id"),
    "adapter_observation": (ObservationRecord, "observation_id"),
    "attempt_event": (AttemptEvent, "event_id"),
    "graph_definition": (GraphDefinition, "graph_id"),
    "artifact": (ArtifactDocument, "artifact_id"),
    "run_terminal": (RunTerminal, "terminal_id"),
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
    "draft_changed": (409, "concurrency"),
    "draft_conflict": (409, "concurrency"),
}
EXPECTED_ERROR_CODES = frozenset(EXPECTED_ERRORS)

EXPECTED_ROUTES = (
    ("GET", "/command/session", False, False),
    ("GET", "/command/runs/<run_id>", False, False),
    ("GET", "/command/runs/<run_id>/controls", False, False),
    ("POST", "/command/runs/<run_id>/proposals", True, True),
    ("POST", "/command/runs/<run_id>/actions", True, True),
    ("POST", "/command/runs/<run_id>/decisions", True, True),
    ("POST", "/command/runs/<run_id>/graph", True, True),
    ("POST", "/command/templates", True, True),
    ("POST", "/command/runs/<run_id>/graph/from-template", True, True),
    ("POST", "/command/runs/<run_id>/artifacts", True, True),
    ("GET", "/command/workflows", False, False),
    ("GET", "/command/workflows/<workflow_id>", False, False),
    ("GET", "/command/workflows/<workflow_id>/revisions/<revision>", False, False),
    ("POST", "/command/workflows/<workflow_id>/draft", True, True),
    ("POST", "/command/workflows/<workflow_id>/revisions", True, True),
    ("GET", "/command/runs", False, False),
    ("POST", "/command/runs", True, True),
)

#: `step_purpose` is the plan's own sentence about a step, and it is on exactly
#: the two roads that reach a child. It is not a command escape key and is held
#: against `UNRESTRICTED_KEYS` below like every other field: it names no
#: executable, no path, no argv and no environment, and the transport puts it
#: inside a code-owned frame rather than on a command line.
EXPECTED_ARGUMENT_SCHEMAS = {
    "dispatch": (
        "work_item_id", "instruction_ref", "profile", "artifact_refs",
        "output_limit_profile", "step_purpose"),
    "review": (
        "work_item_id", "target_artifact_refs", "result_artifact_ref",
        "review_profile", "step_purpose"),
    "evidence": ("target_action_id", "kinds"),
    "stop": ("target_attempt_id", "reason"),
    "retry": ("prior_action_id", "reason"),
    "switch": ("prior_action_id", "target_instance_id", "handoff_ref"),
}

PROPOSE_REQUIRED = frozenset({
    "instance_id", "attempt_id", "capability", "arguments", "scope", "proposed_by",
    "rationale", "timeout_seconds",
})
#: `node_id` joins `adapter_id` as an optional propose field. Optional and NOT
#: nullable: a caller omits the key or names a real node.
PROPOSE_ALLOWED = PROPOSE_REQUIRED | {"adapter_id", "node_id"}
CONFIRM_FIELDS = frozenset({
    "proposal_id", "preview_digest", "capability", "scope", "config_digest",
    "confirmed_by",
})
DECISION_FIELDS = frozenset({
    "receipt_id", "gate_id", "action", "actor", "reason", "scope_refs",
    "evidence_refs", "supersedes",
})
CONFIRM_FORBIDDEN = frozenset({
    "confirmation_id", "action_id", "idempotency_key", "mode", "confirmed_at",
    "requested_at", "budget", "max_actions", "max_action_seconds",
    "max_confirmation_age_seconds", "run_id", "schema_version", "attempt_id",
    "instance_id", "arguments", "requested_by", "timeout_seconds", "future_hint",
})
DECISION_FORBIDDEN = frozenset({
    "decided_at", "config_digest", "run_id", "schema_version", "action_id",
    "future_hint",
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


#: Request headers whose reading is the transport's job: same-origin, the CSRF
#: token, and framing. Response headers are deliberately absent -- `server.py`
#: writes `Content-Type` on its own answers, which is not judging what was sent.
_COMMAND_REQUEST_HEADERS = frozenset({
    "Host", "Origin", "Referer", "X-Conduct-CSRF", "Transfer-Encoding"})
_TRANSPORT = _ROOT / "src" / "conductor" / "command" / "http_transport.py"


def _spoken_request_headers(source: str) -> frozenset[str]:
    """The request headers a module spells out, read from the syntax tree so that
    a header named only in a comment or a docstring is not counted as one read."""
    spoken = {node.value for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    return frozenset(spoken & _COMMAND_REQUEST_HEADERS)


def test_command_header_judgement_lives_in_the_transport_and_never_in_the_server():
    """One module decides what a browser sent; the server only hands it the bytes.

    This replaces an API-0 guard asserting `server.py` carried no production
    command endpoint. That stopped being true when C/API-1 shipped, and it went on
    passing only because `server.py` happens to write `startswith("/command")`
    without the trailing slash: green on a false fact, which is worse than no
    guard. The boundary underneath it is still true. A second reader of these five
    headers is the real hazard -- two dialects of "same origin" drift apart and
    the laxer one is the one an attacker uses -- so the vocabulary must be present
    in the transport, absent from the server, and every name the server imports
    from the transport must really be there.
    """
    server_source = _SERVER.read_text(encoding="utf-8")
    assert _spoken_request_headers(
        _TRANSPORT.read_text(encoding="utf-8")) == _COMMAND_REQUEST_HEADERS
    assert _spoken_request_headers(server_source) == frozenset()
    transport = importlib.import_module("conductor.command.http_transport")
    delegated = {alias.name for node in ast.walk(ast.parse(server_source))
                 if isinstance(node, ast.ImportFrom)
                 and node.module == "conductor.command.http_transport"
                 for alias in node.names}
    assert delegated, "server.py reaches the transport by import, or it re-implements it"
    absent = sorted(name for name in delegated if not hasattr(transport, name))
    assert absent == [], absent
    # Calibration: the scan must catch a server that read a header itself, rather
    # than report nothing because it looks for nothing.
    smuggled = ("def do_POST(self):\n"
                "    if self.headers['Origin'] != 'http://' + self.headers['Host']:\n"
                "        return\n"
                "    if self.headers.get('X-Conduct-CSRF') != self.server.token:\n"
                "        return\n")
    assert _spoken_request_headers(smuggled) == {"Origin", "Host", "X-Conduct-CSRF"}


def _typed_route_dependency_ready(dependency: dict) -> bool:
    try:
        module = importlib.import_module(dependency["public_module"])
    except ModuleNotFoundError:
        return False
    violation = getattr(module, dependency["public_violation_type"], None)
    relation = getattr(module, dependency["public_relation"], None)
    if not isinstance(violation, type) or not callable(relation):
        return False
    try:
        returned = get_type_hints(relation)["return"]
    except (KeyError, NameError, TypeError):
        return False
    return get_origin(returned) is tuple and get_args(returned) == (violation, Ellipsis)


def test_route_unsafe_is_held_by_a_public_typed_relation_not_prose():
    dependency = CANON["route_dependency"]
    assert dependency == {
        "api_slice": "C/API-1",
        "public_module": "conductor.command.containment",
        "public_relation": "run_route_violations",
        "public_violation_type": "RouteViolation",
        "state": "held",
        "nonempty_result": "route_unsafe",
        "parse_exception_prose": False,
    }
    assert _typed_route_dependency_ready(dependency)


def test_held_route_relation_maps_nonempty_typed_facts_without_rendering(tmp_path):
    (tmp_path / "conductor").write_text("not a directory", encoding="utf-8")
    store = run_store_module.RunStore(tmp_path)
    violations = run_route_violations(store, RUN_ID)
    assert violations and all(type(row) is RouteViolation for row in violations)
    refusal = ApiRefusal.fixed(CANON["route_dependency"]["nonempty_result"])
    assert (refusal.code, refusal.status) == ("route_unsafe", 409)


def test_csrf_contract_names_its_trusted_local_process_limit():
    text = " ".join(_SPEC.read_text(encoding="utf-8").split())
    required = (
        "trusted single-user-host boundary",
        "not local-process authentication",
        "same OS user",
        "can call `GET /command/session`",
        "browser cross-origin requests and DNS rebinding only",
    )
    assert all(statement in text for statement in required)


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
    assert set(read) == {"run", "config", "records", "warnings", "graph"}
    # This run holds no graph_definition record, so its graph half is three
    # nulls -- an absent key would leave a reader guessing whether the server
    # is old or the run simply has no plan.
    assert read["graph"] == {
        "definition": None, "definition_digest": None, "runtime": None}
    assert not any(row["record_type"] == "graph_definition"
                   for row in read["records"])
    envelope = RunEnvelope.from_dict(read["run"])
    assert envelope.as_dict() == read["run"]
    assert envelope.run_id == RUN_ID
    assert envelope.config_digest == run_store_module.snapshot_digest(read["config"])
    kinds = ("action_proposal", "action_request", "attempt_event", "attempt_event")
    assert tuple(row["record_type"] for row in read["records"]) == kinds
    assert read["records"][0]["record"] == CANON["action_proposal"]
    assert read["records"][1]["record"] == CANON["action_request"]
    for wrapper, kind in zip(read["records"], kinds, strict=True):
        assert set(wrapper) == {"record_type", "record"}
        contract = EXPECTED_RECORDS[kind][0]
        assert contract.from_dict(wrapper["record"]).as_dict() == wrapper["record"]


def test_attempt_event_registry_and_two_phase_shapes_are_closed_and_causal():
    assert run_store_module._RECORDS == EXPECTED_RECORDS
    wrapped_request = CANON["run_read_response"]["records"][1]["record"]
    request = ActionRequest.from_dict(wrapped_request)
    lease = AttemptEvent.from_dict(CANON["attempt_event_effect_lease"])
    observed = AttemptEvent.from_dict(CANON["attempt_event_execution_observed"])
    expected_fields = {
        "event_id", "run_id", "action_id", "attempt_id", "instance_id",
        "adapter_id", "phase", "recorded_at", "request_digest", "recovery_ref",
        "outcome", "exit_code", "schema_version",
    }
    assert set(lease.as_dict()) == set(observed.as_dict()) == expected_fields
    assert (lease.phase, observed.phase) == ("effect_lease", "execution_observed")
    assert (lease.event_id, lease.recorded_at) == (
        "event-lease-cockpit-001", "2026-08-13T12:03:00Z")
    assert (observed.event_id, observed.recorded_at) == (
        "event-observed-cockpit-001", "2026-08-13T12:20:00Z")
    assert (lease.outcome, lease.exit_code) == (None, None)
    assert (observed.outcome, observed.exit_code) == ("succeeded", 0)
    for field in ("run_id", "action_id", "attempt_id", "instance_id", "adapter_id",
                  "request_digest", "recovery_ref"):
        assert getattr(lease, field) == getattr(observed, field)
    binding = {row["id"]: row["adapter"] for row in CANON["config"]["instances"]}
    assert binding[request.instance_id] == lease.adapter_id
    assert lease.request_digest == action_request_digest(request)


def test_attempt_event_mutations_are_born_red_at_the_frozen_read_boundary():
    rows = CANON["run_read_response"]["records"]
    assert rows[2]["record"] == CANON["attempt_event_effect_lease"]
    assert rows[3]["record"] == CANON["attempt_event_execution_observed"]
    assert set(EXPECTED_RECORDS) == {
        "action_request", "action_result", "evidence", "decision",
        "action_proposal", "adapter_observation", "attempt_event",
        "graph_definition", "artifact", "run_terminal",
    }


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
        assert set(row) == {"instance_id", "adapter_id", "model", "controls"}
        assert row["controls"] == sorted(row["controls"])
        assert set(row["controls"]) <= set(EXPECTED_ARGUMENT_SCHEMAS)


def test_an_instance_row_says_which_model_is_pinned_or_says_none_was():
    """The deployment fact the Cockpit joins a product name to, and its absence.

    Both states are exercised by the canonical example on purpose. `null` is the
    harder one to render honestly -- it means this build chose no model and the
    provider's own configuration decides -- so a consumer that has never seen a
    null here is a consumer that will print something false the first time one
    arrives.

    The id is held to the contract's own identifier grammar rather than to a
    vendor's naming, because this build catalogues no models and a shape read
    off one product's ids would refuse the next product's.
    """
    rows = CANON["controls_response"]["instances"]
    pinned = [row["model"] for row in rows]

    assert None in pinned, "the example must show an instance that pins no model"
    named = [model for model in pinned if model is not None]
    assert named, "the example must show an instance that pins one"
    for model in named:
        assert _id("model", model) == model



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
