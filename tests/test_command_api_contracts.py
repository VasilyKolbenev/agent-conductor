"""Closed value and refusal contracts for the unwired C/API-1 boundary."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dataclasses import FrozenInstanceError

from conductor.command import api_contracts
from conductor.command.adapters import base as adapter_base
from conductor.command.adapters.deep_adapters import DEEP_ARGUMENT_SCHEMA
from conductor.command.run_store import RunStore
from conductor.command.adapters import UnsupportedCapability
from conductor.command.adapters.deep_commands import (
    DEEP_ARGUMENT_TYPES,
    DeepDispatchArgs,
    DeepEvidenceArgs,
    DeepRetryArgs,
    DeepReviewArgs,
    DeepStopArgs,
    DeepSwitchArgs,
)
from conductor.command.api_contracts import (
    ARGUMENT_SCHEMAS,
    canonical_arguments,
    COMMAND_ARGUMENT_SCHEMA,
    ERROR_STATUS,
    ApiRefusal,
    parse_confirmation,
    parse_decision,
    parse_proposal,
    refusal_from_exception,
)
from conductor.command.contracts import ContractError, canonical_json
from conductor.command.http_transport import HttpRefusal
from conductor.command.run_store import (
    CorruptRun,
    RecordConflict,
    RunClosed,
    StoreError,
)
from conductor.command.runtime import AuthorizationError, Confirmation
from conductor.command.service import ServiceError

_ROOT = Path(__file__).resolve().parents[1]
_BOUNDARY = json.loads((
    _ROOT / "tests" / "fixtures" / "cockpit_command_boundary_fixtures.json"
).read_text(encoding="utf-8"))
_SPEC = (_ROOT / "docs" / "specs" / "2026-08-13-cockpit-command-api.md")

#: `step_purpose` stands LAST on the review road, and the order is part of what
#: is pinned: `ARGUMENT_SCHEMAS` is built from `fields()`, so a field carrying a
#: default has to come last, and moving one that does not would slide values
#: between positional arguments at every construction site.
#:
#: The dispatch road carries one more behind it. `instruction_digest` is the
#: promise about the instruction's BYTES, and it is the only road that resolves
#: an instruction at all -- so it is the only road where the question exists.
#: Omittable, like the purpose in front of it: a payload written before the
#: field existed still reads, and promises nothing about those bytes.
EXPECTED_DEEP_ARGUMENTS = {
    "dispatch": (DeepDispatchArgs, (
        "work_item_id", "instruction_ref", "profile", "artifact_refs",
        "output_limit_profile", "step_purpose", "instruction_digest", "work_scope")),
    "review": (DeepReviewArgs, (
        "work_item_id", "target_artifact_refs", "result_artifact_ref",
        "review_profile", "step_purpose", "work_scope")),
    "evidence": (DeepEvidenceArgs, ("target_action_id", "kinds")),
    "stop": (DeepStopArgs, ("target_attempt_id", "reason")),
    "retry": (DeepRetryArgs, ("prior_action_id", "reason")),
    "switch": (DeepSwitchArgs, (
        "prior_action_id", "target_instance_id", "handoff_ref")),
}


def _canon(name):
    marker = f"<!-- CANONICAL:{name} -->\n```json\n"
    text = _SPEC.read_text(encoding="utf-8")
    return json.loads(text.split(marker, 1)[1].split("\n```", 1)[0])


def a_submitted_proposal(body):
    """The two value doors of a propose request, in their contracted order.

    The envelope is parsed first and answers for the request's own shape; the
    payload is judged second, and only its capability's schema judges it. On
    the route the pair authority stands between them and needs an adapter
    registry, which this value layer deliberately has none of -- so what is
    driven here is the pair of value doors and the order they keep.

    They used to be one call, and that WAS the defect: an unsupported pair with
    an invalid payload answered for the payload, so the propose road said
    `contract_invalid` where the plan road said `capability_unsupported` about
    the very same pair.
    """
    submitted = parse_proposal(body)
    return submitted, canonical_arguments(submitted.capability, submitted.arguments)


@pytest.mark.parametrize(
    "row", _BOUNDARY["proposal_cases"], ids=lambda row: row["name"])
def test_frozen_proposal_fixtures_drive_the_real_closed_mapper(row):
    try:
        parsed, arguments = a_submitted_proposal(row["body"])
    except ApiRefusal as refusal:
        actual = ("refuse", refusal.code)
    else:
        actual = ("accept", None)
        assert parsed.capability == row["body"]["capability"]
        contract = EXPECTED_DEEP_ARGUMENTS[parsed.capability][0]
        assert json.loads(canonical_json(dict(arguments))) == contract.from_dict(
            row["body"]["arguments"]).as_dict()
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
    expected_schemas = {
        name: fields for name, (_contract, fields) in EXPECTED_DEEP_ARGUMENTS.items()}
    assert dict(DEEP_ARGUMENT_TYPES) == {
        name: contract for name, (contract, _fields) in EXPECTED_DEEP_ARGUMENTS.items()}
    assert dict(ARGUMENT_SCHEMAS) == expected_schemas
    assert {key: list(value) for key, value in expected_schemas.items()} == _canon(
        "argument_schemas")
    expected = {row["code"]: row["status"] for row in _canon("error_codes")}
    assert dict(ERROR_STATUS) == expected


def test_fixture_has_one_real_positive_for_each_deep_capability():
    accepted = {
        row["body"]["capability"] for row in _BOUNDARY["proposal_cases"]
        if row["expected"] == {"disposition": "accept", "error_code": None}}
    assert accepted == set(EXPECTED_DEEP_ARGUMENTS)


@pytest.mark.parametrize(
    "row", _BOUNDARY["retired_argument_cases"], ids=lambda row: row["capability"])
def test_each_retired_shallow_argument_shape_is_contract_invalid(row):
    body = {
        **_canon("propose_request"), "capability": row["capability"],
        "arguments": row["arguments"],
    }
    with pytest.raises(ApiRefusal) as caught:
        a_submitted_proposal(body)
    assert (caught.value.code, caught.value.status) == ("contract_invalid", 422)


@pytest.mark.parametrize("capability", _BOUNDARY["retired_capabilities"])
def test_a_retired_capability_is_unsupported_because_this_api_carries_no_schema(
        capability):
    """Not because nobody declares it -- because this surface has no shape for it.

    Who declares a capability is a fact about a bound adapter, and no value
    door can reach one. What this layer answers for is narrower and firmer: the
    frozen registry of section 4.1 carries no schema for these names, so no
    request can be written in them whoever offers to serve them.
    """
    body = {**_canon("propose_request"), "capability": capability, "arguments": {}}
    with pytest.raises(ApiRefusal) as caught:
        a_submitted_proposal(body)
    assert (caught.value.code, caught.value.status) == ("capability_unsupported", 409)


@pytest.mark.parametrize("capability,array_field", [
    ("dispatch", "artifact_refs"),
    ("review", "target_artifact_refs"),
    ("evidence", "kinds"),
])
def test_deep_argument_arrays_must_arrive_as_json_lists(capability, array_field):
    row = next(
        item for item in _BOUNDARY["proposal_cases"]
        if item["expected"]["disposition"] == "accept"
        and item["body"]["capability"] == capability)
    arguments = dict(row["body"]["arguments"])
    arguments[array_field] = tuple(arguments[array_field])
    with pytest.raises(ApiRefusal) as caught:
        a_submitted_proposal(
            {**row["body"], "arguments": arguments})
    assert (caught.value.code, caught.value.status) == ("contract_invalid", 422)


@pytest.mark.parametrize("error,code", [
    (CorruptRun("APIKEY_SECRET_OS_PATH"), "run_corrupt"),
    (RecordConflict("APIKEY_SECRET_OS_PATH"), "record_conflict"),
    (RunClosed("APIKEY_SECRET_OS_PATH"), "run_terminal"),
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
    assert refusal_from_exception(RunClosed("same prose")).code == "run_terminal"
    assert refusal_from_exception(StoreError("same prose")).code == "store_error"
    assert refusal_from_exception(ServiceError("same prose")).code == "service_refused"
    with pytest.raises(TypeError, match="no frozen API translation"):
        refusal_from_exception(RuntimeError("same prose"))


def test_api_refusal_shape_is_exact_and_validates_each_detail_identifier():
    refusal = ApiRefusal.service_missing_instance("run-001", "instance-001")
    assert set(refusal.as_dict()) == {"error"}
    assert set(refusal.as_dict()["error"]) == {"code", "message", "detail"}
    assert set(refusal.detail) == {"run_id", "instance_id"}
    for value in ("../run", "ghost/dev", "secret key", "", None, True):
        with pytest.raises(ValueError):
            ApiRefusal.service_missing_instance("run-001", value)
        with pytest.raises(ValueError):
            ApiRefusal.service_missing_instance(value, "instance-001")


def test_api_refusal_cannot_be_constructed_with_submitted_or_exception_prose():
    with pytest.raises(ValueError, match="reviewed factory"):
        ApiRefusal(
            object(), "store_error", "APIKEY_SECRET exception prose",
            {"arbitrary": "C:/APIKEY_SECRET"})
    with pytest.raises(ValueError, match="reviewed template"):
        ApiRefusal(
            api_contracts._REFUSAL_BUILD, "store_error",
            "APIKEY_SECRET exception prose", {})
    with pytest.raises(ValueError, match="reviewed fact"):
        ApiRefusal(
            api_contracts._REFUSAL_BUILD, "service_refused",
            "frozen config declares no instance 'different'",
            {"run_id": "run-001", "instance_id": "instance-001"})


def test_service_missing_instance_factory_equals_the_frozen_refusal_example():
    assert ApiRefusal.service_missing_instance(
        "run-cockpit-001", "ghost-dev").as_dict() == _canon("refusal_shape")


def test_http_translation_preserves_each_reviewed_phase_message():
    host = refusal_from_exception(HttpRefusal("host"))
    origin = refusal_from_exception(HttpRefusal("origin"))
    assert host.code == origin.code == "same_origin_denied"
    assert host.message == "request Host is not allowed"
    assert origin.message == "request origin is not allowed"
    assert host.message != origin.message


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
        parse_proposal(body)
    assert caught.value.code == "contract_invalid"


@pytest.mark.parametrize("bad", ["src", None, {"path": "src"}])
@pytest.mark.parametrize("parser,name,field", [
    (lambda body: parse_proposal(body),
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


def test_every_fixed_code_has_one_test_owned_exact_message_and_empty_detail():
    expected = {
        "same_origin_denied": "request origin is not allowed",
        "csrf_denied": "request CSRF token is not current",
        "method_not_allowed": "request method is not allowed for this route",
        "route_not_found": "command route does not exist",
        "malformed_request": "request transport or JSON shape is malformed",
        "contract_invalid": "request values do not satisfy the contract",
        "run_corrupt": "stored run is corrupt",
        "store_error": "run store could not complete the request",
        "route_unsafe": "run route is not structurally contained",
        "service_refused": "command service refused the request",
        "capability_unsupported": "adapter does not support this capability",
        "authorization_refused": "confirmation did not authorize the request",
        "proposal_rebind_required": "this proposal predates material binding; "
                                    "create a new proposal and review it before confirming",
        "record_conflict": "durable record identity conflicts",
        "draft_changed": "the draft changed since it was reviewed; read it again",
        "draft_conflict": "the stored draft is not the one this request was "
                          "working from",
        "run_terminal": "run has recorded its terminal and accepts no further "
                        "records",
        "gate_unreached": "a decision may stand only on a gate this run's plan "
                          "has reached",
    }
    assert set(expected) == set(ERROR_STATUS)
    for code, message in expected.items():
        refusal = ApiRefusal.fixed(code)
        assert refusal.message == message
        assert refusal.detail == {}


def test_structured_service_fact_requires_exact_keys_values_and_template():
    build = api_contracts._REFUSAL_BUILD
    wrong_details = (
        {"run_id": "run-001"},
        {"run_id": "run-001", "instance": "ghost-dev"},
        {"run_id": "run-001", "instance_id": "ghost-dev", "field": "extra"},
    )
    for detail in wrong_details:
        with pytest.raises(ValueError, match="reviewed fact"):
            ApiRefusal(
                build, "service_refused",
                "frozen config declares no instance 'ghost-dev'", detail)


@pytest.mark.parametrize("capability", [None, True, False, "", 7, [], {}])
def test_malformed_capability_is_a_contract_error(capability):
    body = {**_canon("propose_request"), "capability": capability}
    with pytest.raises(ApiRefusal) as caught:
        parse_proposal(body)
    assert caught.value.code == "contract_invalid"
    assert caught.value.status == 422


@pytest.mark.parametrize("capability", ["observe", "future-capability"])
def test_a_capability_this_api_carries_no_schema_for_is_unsupported(capability):
    """`stop` used to sit in this list and no longer can.

    It was here because no adapter in the case declared it -- a fact about a
    binding, which this layer cannot see and must not guess at. `stop` IS a
    capability the frozen registry carries, so the value doors admit it and the
    PAIR decides whether the bound adapter serves it; that case is driven
    against a real registry in `test_command_graph_route.py`.
    """
    body = {**_canon("propose_request"), "capability": capability}
    with pytest.raises(ApiRefusal) as caught:
        a_submitted_proposal(body)
    assert caught.value.code == "capability_unsupported"
    assert caught.value.status == 409


@pytest.mark.parametrize("adapter_id", [None, True, False, "", "bad/id", [], {}])
def test_adapter_id_may_be_omitted_but_never_present_with_an_invalid_value(adapter_id):
    body = {**_canon("propose_request"), "adapter_id": adapter_id}
    with pytest.raises(ApiRefusal) as caught:
        parse_proposal(body)
    assert caught.value.code == "contract_invalid"


def test_omitted_adapter_id_remains_the_only_empty_optional_form():
    body = _canon("propose_request")
    body.pop("adapter_id")
    assert parse_proposal(body).adapter_id is None


def _assert_refusal_graph_is_detached(refusal, sentinel):
    assert refusal.__cause__ is None
    assert refusal.__context__ is None
    graph = repr((refusal, refusal.args, refusal.__dict__))
    assert sentinel not in graph


@pytest.mark.parametrize("parser,name,field", [
    (lambda body: parse_proposal(body),
     "propose_request", "attempt_id"),
    (parse_confirmation, "confirm_request", "confirmed_by"),
    (parse_decision, "decision_request", "reason"),
])
def test_contract_sanitization_drops_submitted_values_from_exception_graph(
        parser, name, field):
    sentinel = "APIKEY_SECRET_SUBMITTED_VALUE"
    body = {**_canon(name), field: {"value": sentinel}}
    with pytest.raises(ApiRefusal) as caught:
        parser(body)
    _assert_refusal_graph_is_detached(caught.value, sentinel)


# -- a refusal is a frozen value that still travels as an exception ------------


#: The attributes Python's own exception machinery assigns through setattr.
#: `__notes__` joins the four the review named because `add_note` assigns it
#: the same way, and a refusal that crashed on add_note would be the same
#: defect one door along.
SERVICE_ATTRIBUTES = frozenset({
    "__traceback__", "__cause__", "__context__", "__suppress_context__",
    "__notes__"})


def test_only_the_interpreters_own_attributes_may_be_assigned():
    """Frozen as a value, mobile as an exception -- and nothing in between.

    The four the review named must pass, because the plumbing that carries an
    exception assigns them. Everything else is refused: the three reviewed
    fields, and any new name at all, so this cannot become a bag a caller
    widens later.
    """
    assert {"__traceback__", "__cause__", "__context__",
            "__suppress_context__"} <= SERVICE_ATTRIBUTES
    assert SERVICE_ATTRIBUTES == api_contracts._EXCEPTION_SLOTS
    assert all(name.startswith("__") and name.endswith("__")
               for name in SERVICE_ATTRIBUTES)

    # Each one takes the type the interpreter gives it, so this proves the
    # assignment reaches the real slot rather than a look-alike.
    permitted = {"__traceback__": None, "__cause__": None, "__context__": None,
                 "__suppress_context__": True, "__notes__": ["a note"]}
    assert set(permitted) == SERVICE_ATTRIBUTES
    refusal = ApiRefusal.fixed("route_unsafe")
    for name, value in sorted(permitted.items()):
        setattr(refusal, name, value)
        assert getattr(refusal, name) == value
    for name in ("code", "message", "detail", "status", "surprise", "__dict__"):
        with pytest.raises(FrozenInstanceError):
            setattr(refusal, name, "moved")
    assert (refusal.code, refusal.status) == ("route_unsafe", 409)
    assert refusal.as_dict()["error"]["message"] == (
        "run route is not structurally contained")


def test_a_refusal_survives_the_store_transaction_it_is_raised_inside(tmp_path):
    """Every mutating route re-checks containment INSIDE the transaction.

    A frozen dataclass refuses every assignment, and `contextlib` assigns
    `__traceback__` to an exception on its way out of a context manager -- so
    that second refusal never arrived. What reached the boundary was an
    untranslatable `TypeError`, and the one closed 409 this surface promises
    was replaced by a crash.
    """
    store = RunStore(tmp_path)
    with pytest.raises(ApiRefusal) as refused:
        with store.transaction():
            raise ApiRefusal.fixed("route_unsafe")
    assert (refused.value.code, refused.value.status) == ("route_unsafe", 409)
    assert refused.value.as_dict()["error"]["detail"] == {}


def test_the_argument_family_this_api_speaks_is_one_the_registry_reviews():
    """Two spellings of one word, pinned by relation rather than by copy.

    The API names the family it can write plans in; the adapter package names
    the family its deep adapters declare; the registry holds the closed set of
    families it will register at all. A change to any one of the three has to
    move the others deliberately.
    """
    assert COMMAND_ARGUMENT_SCHEMA == DEEP_ARGUMENT_SCHEMA
    assert COMMAND_ARGUMENT_SCHEMA in adapter_base._ARGUMENT_SCHEMAS
    assert "structured-process-v1" in adapter_base._ARGUMENT_SCHEMAS
    assert COMMAND_ARGUMENT_SCHEMA != "structured-process-v1"
