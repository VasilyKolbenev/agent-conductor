"""The boundary fixtures, and the disposition re-derived independently of them.

Split from ``test_cockpit_command_api_freeze.py`` when that module crossed its
800-line cap. This is the self-contained fixture circuit: the propose
dispositions, the closed confirm/decision request matrix, and the control
cases. Its parent owns the spec loader and the shared constants imported below,
exactly as the graph circuit next door does.

The disposition here is computed WITHOUT calling the production mapper, so the
fixture and the code never come from one function. What it may answer for
narrowed this round: whether a bound adapter declares a capability is the pair
authority's verdict and needs a run and a registry, so it is driven against a
real one in ``test_command_graph_route.py`` and not guessed at here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conductor.command.adapters.deep_commands import DEEP_ARGUMENT_TYPES
from conductor.command.adapters.deep_contracts import DeepContractError
from conductor.command.contracts import ActionProposal, ContractError

from tests.test_cockpit_command_api_freeze import (
    CANON,
    CONFIRM_FIELDS,
    CONFIRM_FORBIDDEN,
    DECISION_FIELDS,
    DECISION_FORBIDDEN,
    EXPECTED_ARGUMENT_SCHEMAS,
    PROPOSE_ALLOWED,
    PROPOSE_REQUIRED,
    RUN_ID,
)

_BOUNDARY_FIXTURES = (
    Path(__file__).resolve().parent / "fixtures" / "cockpit_command_boundary_fixtures.json")


def _load_boundary_fixtures() -> dict:
    return json.loads(_BOUNDARY_FIXTURES.read_text(encoding="utf-8"))


def _boundary_cases():
    return _load_boundary_fixtures()["proposal_cases"]


def _proposal_disposition(case: dict) -> tuple[str, str | None]:
    body = case["body"]
    if not isinstance(body, dict) or not PROPOSE_REQUIRED <= set(body) <= PROPOSE_ALLOWED:
        return "refuse", "contract_invalid"
    capability = body["capability"]
    argument_type = DEEP_ARGUMENT_TYPES.get(capability)
    # Whether a bound adapter declares the capability is the PAIR's verdict and
    # cannot be reached without a run and a registry; this layer answers only
    # for what the frozen API itself carries.
    if argument_type is None:
        return "refuse", "capability_unsupported"
    try:
        arguments = argument_type.from_dict(body["arguments"]).as_dict()
    except DeepContractError:
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


def _closed_request_cases():
    return _load_boundary_fixtures()["closed_request_cases"]


@pytest.mark.parametrize("case", _closed_request_cases(), ids=lambda row: row["name"])
def test_confirm_and_decision_requests_refuse_every_extra_field(case):
    fields = CONFIRM_FIELDS if case["endpoint"] == "confirm" else DECISION_FIELDS
    base_name = "confirm_request" if case["endpoint"] == "confirm" else "decision_request"
    submitted = {**CANON[base_name], case["field"]: case["value"]}
    assert set(submitted) - fields == {case["field"]}
    assert case["expected"] == {
        "disposition": "refuse", "error_code": "contract_invalid"}


def test_closed_request_fixture_matrix_is_exhaustive_and_pins_nested_extras():
    by_endpoint = {
        endpoint: {row["field"] for row in _closed_request_cases()
                   if row["endpoint"] == endpoint}
        for endpoint in ("confirm", "decision")
    }
    assert by_endpoint == {
        "confirm": set(CONFIRM_FORBIDDEN), "decision": set(DECISION_FORBIDDEN)}
    nested = [row for row in _closed_request_cases() if row["field"] == "future_hint"]
    assert {row["endpoint"] for row in nested} == {"confirm", "decision"}
    assert all(isinstance(row["value"].get("nested"), dict) for row in nested)


@pytest.mark.parametrize(
    "case", _load_boundary_fixtures()["control_cases"], ids=lambda row: row["name"])
def test_unsupported_controls_are_absent_not_decorative(case):
    controls = sorted(
        set(case["manifest_capabilities"]) & set(EXPECTED_ARGUMENT_SCHEMAS))
    assert controls == case["expected_controls"]
