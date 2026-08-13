"""Closed value and refusal contracts for the unwired C/API-1 boundary."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conductor.command.adapters import UnsupportedCapability
from conductor.command.api_contracts import (
    ARGUMENT_SCHEMAS,
    ERROR_STATUS,
    ApiRefusal,
    parse_confirmation,
    parse_decision,
    parse_proposal,
    refusal_from_exception,
)
from conductor.command.contracts import ContractError
from conductor.command.run_store import CorruptRun, RecordConflict, StoreError
from conductor.command.runtime import AuthorizationError, Confirmation
from conductor.command.service import ServiceError


_ROOT = Path(__file__).resolve().parents[1]
_BOUNDARY = json.loads((
    _ROOT / "tests" / "fixtures" / "cockpit_command_boundary_fixtures.json"
).read_text(encoding="utf-8"))
_SPEC = (_ROOT / "docs" / "specs" / "2026-08-13-cockpit-command-api.md")


def _canon(name):
    marker = f"<!-- CANONICAL:{name} -->\n```json\n"
    text = _SPEC.read_text(encoding="utf-8")
    return json.loads(text.split(marker, 1)[1].split("\n```", 1)[0])


@pytest.mark.parametrize(
    "row", _BOUNDARY["proposal_cases"], ids=lambda row: row["name"])
def test_frozen_proposal_fixtures_drive_the_real_closed_mapper(row):
    try:
        parsed = parse_proposal(
            row["body"], adapter_capabilities=row["adapter_capabilities"])
    except ApiRefusal as refusal:
        actual = ("refuse", refusal.code)
    else:
        actual = ("accept", None)
        assert parsed.capability == row["body"]["capability"]
    assert actual == (
        row["expected"]["disposition"], row["expected"]["error_code"])


@pytest.mark.parametrize(
    "row", _BOUNDARY["closed_request_cases"], ids=lambda row: row["name"])
def test_every_server_owned_or_unknown_confirm_decision_field_is_refused(row):
    name = "confirm_request" if row["endpoint"] == "confirm" else "decision_request"
    parser = parse_confirmation if row["endpoint"] == "confirm" else parse_decision
    submitted = {**_canon(name), row["field"]: row["value"]}
    with pytest.raises(ApiRefusal) as caught:
        parser(submitted)
    assert caught.value.code == row["expected"]["error_code"] == "contract_invalid"


def test_confirmation_mapper_accepts_only_caller_facts_and_injects_server_facts():
    body = _canon("confirm_request")
    parsed = parse_confirmation(body)
    confirmation = parsed.build(
        confirmation_id="confirmation-api-001", run_id="run-cockpit-001",
        confirmed_at="2026-08-13T12:02:00Z")
    assert isinstance(confirmation, Confirmation)
    assert confirmation.confirmation_id == "confirmation-api-001"
    assert confirmation.run_id == "run-cockpit-001"
    assert confirmation.confirmed_at == "2026-08-13T12:02:00Z"
    assert confirmation.mode.value == "confirm"


def test_decision_mapper_accepts_only_caller_facts_and_injects_server_facts():
    parsed = parse_decision(_canon("decision_request"))
    receipt = parsed.build(
        run_id="run-cockpit-001", decided_at="2026-08-13T12:30:00Z",
        config_digest="sha256:" + "a" * 64)
    assert receipt.run_id == "run-cockpit-001"
    assert receipt.decided_at == "2026-08-13T12:30:00Z"
    assert receipt.config_digest == "sha256:" + "a" * 64


def test_argument_schema_and_error_vocabularies_equal_the_frozen_examples():
    assert {key: list(value) for key, value in ARGUMENT_SCHEMAS.items()} == _canon(
        "argument_schemas")
    expected = {row["code"]: row["status"] for row in _canon("error_codes")}
    assert dict(ERROR_STATUS) == expected


@pytest.mark.parametrize("error,code", [
    (CorruptRun("APIKEY_SECRET_OS_PATH"), "run_corrupt"),
    (RecordConflict("APIKEY_SECRET_OS_PATH"), "record_conflict"),
    (StoreError("APIKEY_SECRET_OS_PATH"), "store_error"),
    (UnsupportedCapability("APIKEY_SECRET_OS_PATH"), "capability_unsupported"),
    (ServiceError("APIKEY_SECRET_OS_PATH"), "service_refused"),
    (AuthorizationError("APIKEY_SECRET_OS_PATH"), "authorization_refused"),
    (ContractError("APIKEY_SECRET_OS_PATH"), "contract_invalid"),
])
def test_exception_mapping_is_by_type_and_discards_all_exception_prose(error, code):
    refusal = refusal_from_exception(error)
    assert refusal.code == code
    assert refusal.status == ERROR_STATUS[code]
    assert "APIKEY_SECRET_OS_PATH" not in json.dumps(refusal.as_dict())


def test_exception_type_precedence_distinguishes_store_subclasses():
    assert refusal_from_exception(CorruptRun("same prose")).code == "run_corrupt"
    assert refusal_from_exception(RecordConflict("same prose")).code == "record_conflict"
    assert refusal_from_exception(StoreError("same prose")).code == "store_error"
    assert refusal_from_exception(ServiceError("same prose")).code == "service_refused"
    with pytest.raises(TypeError, match="no frozen API translation"):
        refusal_from_exception(RuntimeError("same prose"))


def test_api_refusal_shape_is_exact_and_rejects_secret_or_path_detail_fields():
    refusal = ApiRefusal.fixed(
        "service_refused", {"run_id": "run-001", "instance_id": "instance-001"})
    assert set(refusal.as_dict()) == {"error"}
    assert set(refusal.as_dict()["error"]) == {"code", "message", "detail"}
    for key in ("csrf_token", "secret", "filesystem_path", "cookie"):
        with pytest.raises(ValueError):
            ApiRefusal.fixed("service_refused", {key: "unsafe"})


def test_api_refusal_cannot_be_constructed_with_submitted_or_exception_prose():
    with pytest.raises(ValueError, match="fixed code message"):
        ApiRefusal("store_error", "APIKEY_SECRET exception prose", {})


@pytest.mark.parametrize("parser,name", [
    (parse_confirmation, "confirm_request"),
    (parse_decision, "decision_request"),
])
def test_nested_unknown_authority_is_refused_before_tolerant_contract_extra(parser, name):
    body = {**_canon(name), "future_hint": {
        "argv": ["powershell"], "env": {"SECRET": "value"}, "pid": 42}}
    with pytest.raises(ApiRefusal) as caught:
        parser(body)
    assert caught.value.code == "contract_invalid"


@pytest.mark.parametrize("field", [
    "action_result", "evidence", "observation", "csrf_token", "pid", "argv",
    "cwd", "path", "env",
])
def test_proposal_cannot_author_runtime_adapter_transport_or_result_fields(field):
    body = {**_BOUNDARY["proposal_cases"][0]["body"], field: "forbidden"}
    with pytest.raises(ApiRefusal) as caught:
        parse_proposal(body, adapter_capabilities={"dispatch"})
    assert caught.value.code == "contract_invalid"


@pytest.mark.parametrize("bad", ["src", None, {"path": "src"}])
@pytest.mark.parametrize("parser,name,field", [
    (lambda body: parse_proposal(body, adapter_capabilities={"dispatch"}),
     "propose_request", "scope"),
    (parse_confirmation, "confirm_request", "scope"),
    (parse_decision, "decision_request", "scope_refs"),
    (parse_decision, "decision_request", "evidence_refs"),
])
def test_every_browser_array_field_requires_a_json_array(parser, name, field, bad):
    body = {**_canon(name), field: bad}
    with pytest.raises(ApiRefusal) as caught:
        parser(body)
    assert caught.value.code == "contract_invalid"


def test_every_frozen_code_builds_one_exact_sanitized_refusal_shape():
    expected = {row["code"]: row["status"] for row in _canon("error_codes")}
    assert set(ERROR_STATUS) == set(expected)
    for code, status in expected.items():
        refusal = ApiRefusal.fixed(code)
        assert refusal.status == status
        assert set(refusal.as_dict()) == {"error"}
        assert set(refusal.as_dict()["error"]) == {"code", "message", "detail"}
