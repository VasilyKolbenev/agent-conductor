"""Closed future grant values, independent digest oracle, and no live activation."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import json

import pytest

from conductor.command.authorization_terms import (
    InitialInputBinding, InstructionBinding, NodeLimit, authorization_interval)
from conductor.command.contract_values import ContractError
from conductor.command.run_authorization import RunAuthorization, RunAuthorizationControl
from conductor.command.run_store import RunStore, StoreError


DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64
AT = "2026-09-21T14:00:00Z"
FIELDS = {"schema_version", "authorization_id", "run_id", "contract", "config_digest",
    "graph_digest", "provider_config_digest", "source_prefix_digest", "authorized_by",
    "authorized_at", "expires_at", "supersedes", "node_limits", "instruction_bindings",
    "initial_input_bindings", "max_actions", "max_action_seconds", "max_total_task_seconds",
    "concurrency", "failure_handling", "authorization_digest"}
CONTROL_FIELDS = {"schema_version", "control_id", "run_id", "authorization_id",
    "authorization_digest", "action", "actor", "recorded_at", "expected_control_id"}


def grant(**changes):
    values = dict(authorization_id="grant-one", run_id="run-one", config_digest=DIGEST,
        graph_digest=DIGEST, provider_config_digest=DIGEST, source_prefix_digest=DIGEST,
        authorized_by="Project owner", authorized_at=AT, expires_at="2026-09-21T15:00:00Z",
        supersedes=None, node_limits=(NodeLimit("do", 30, 2), NodeLimit("review", 15, 1)),
        instruction_bindings=(InstructionBinding("do", "instruction-one", DIGEST),),
        initial_input_bindings=(InitialInputBinding("brief", "brief-one", DIGEST),),
        max_actions=4, max_action_seconds=60, max_total_task_seconds=240)
    return RunAuthorization(**{**values, **changes})


def control(**changes):
    return RunAuthorizationControl(**{**dict(control_id="pause-one", run_id="run-one",
        authorization_id="grant-one", authorization_digest=grant().authorization_digest,
        action="pause", actor="Project owner", recorded_at=AT, expected_control_id=None), **changes})


def independently_digest(body):
    terms = {name: value for name, value in body.items() if name != "authorization_digest"}
    encoded = json.dumps(terms, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def test_exact_record_roundtrip_digest_and_detached_terms():
    subject = grant()
    body = subject.as_dict()
    assert set(body) == FIELDS and body["schema_version"] == 2
    assert body["contract"] == "bounded-run-v1"
    assert body["concurrency"] == 1 and body["failure_handling"] == "explicit-failure-route-only"
    assert body["authorization_digest"] == independently_digest(body)
    assert RunAuthorization.from_dict(json.loads(json.dumps(body))) == subject
    body["node_limits"][0]["timeout_seconds"] = 999
    body["instruction_bindings"][0]["content_digest"] = OTHER_DIGEST
    assert subject.node_limits[0].timeout_seconds == 30
    assert subject.instruction_bindings[0].content_digest == DIGEST
    with pytest.raises(FrozenInstanceError):
        subject.max_actions = 100


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_every_grant_field_is_required_on_wire(field):
    body = grant().as_dict()
    body.pop(field)
    with pytest.raises(ContractError):
        RunAuthorization.from_dict(body)


@pytest.mark.parametrize("field", sorted(FIELDS - {"supersedes"}))
def test_required_grant_fields_reject_explicit_null(field):
    body = grant().as_dict()
    body[field] = None
    with pytest.raises(ContractError):
        RunAuthorization.from_dict(body)


@pytest.mark.parametrize("field,value", [
    ("authorization_id", "grant-two"), ("run_id", "run-two"),
    ("config_digest", OTHER_DIGEST), ("graph_digest", OTHER_DIGEST),
    ("provider_config_digest", OTHER_DIGEST), ("source_prefix_digest", OTHER_DIGEST),
    ("authorized_by", "Another owner"), ("authorized_at", "2026-09-21T14:01:00Z"),
    ("expires_at", "2026-09-21T16:00:00Z"), ("supersedes", "grant-before"),
    ("max_actions", 5), ("max_action_seconds", 61), ("max_total_task_seconds", 241),
])
def test_altering_any_scalar_term_invalidates_the_previous_digest(field, value):
    body = grant().as_dict()
    body[field] = value
    with pytest.raises(ContractError, match="digest does not match"):
        RunAuthorization.from_dict(body)
    body["authorization_digest"] = independently_digest(body)
    assert RunAuthorization.from_dict(body).as_dict() == body


@pytest.mark.parametrize("field,nested,value", [
    ("node_limits", "timeout_seconds", 31), ("node_limits", "max_attempts", 3),
    ("instruction_bindings", "artifact_id", "instruction-two"),
    ("instruction_bindings", "content_digest", OTHER_DIGEST),
    ("initial_input_bindings", "artifact_ref", "source"),
    ("initial_input_bindings", "artifact_id", "brief-two"),
    ("initial_input_bindings", "content_digest", OTHER_DIGEST),
])
def test_nested_terms_are_covered_by_the_grant_digest(field, nested, value):
    body = grant().as_dict()
    body[field][0][nested] = value
    with pytest.raises(ContractError, match="digest does not match"):
        RunAuthorization.from_dict(body)


@pytest.mark.parametrize("field,value", [
    ("schema_version", 3), ("schema_version", True), ("schema_version", 2.0),
    ("contract", "bounded-run-v2"), ("concurrency", 2), ("concurrency", True),
    ("failure_handling", "continue"), ("supersedes", "grant-one"),
    ("max_actions", 0), ("max_actions", True), ("max_actions", 1.5),
    ("max_action_seconds", -1), ("max_total_task_seconds", float("inf")),
    ("authorization_digest", "sha256:" + "0" * 64),
])
def test_constructor_refuses_open_authority_or_invalid_ceilings(field, value):
    with pytest.raises(ContractError):
        grant(**{field: value})


@pytest.mark.parametrize("field", ["node_limits", "instruction_bindings", "initial_input_bindings"])
def test_nested_arrays_refuse_unknown_fields_duplicates_and_explicit_null(field):
    baseline = grant().as_dict()[field]
    for value in ([{**baseline[0], "unreviewed": "authority"}], baseline * 2, [None], None):
        with pytest.raises(ContractError):
            grant(**{field: value})


def test_input_arrays_are_detached_and_mutated_frozen_rows_are_revalidated():
    limits = [NodeLimit("do", 30, 1)]
    value = grant(node_limits=limits)
    limits.clear()
    assert value.node_limits == (NodeLimit("do", 30, 1),)
    hostile = NodeLimit("do", 30, 1)
    object.__setattr__(hostile, "timeout_seconds", False)
    with pytest.raises(ContractError):
        grant(node_limits=(hostile,))


def test_node_order_is_preserved_and_instruction_rows_follow_it():
    limits = (NodeLimit("second", 10, 1), NodeLimit("first", 10, 1))
    instructions = (InstructionBinding("second", "two", DIGEST),
                    InstructionBinding("first", "one", DIGEST))
    value = grant(node_limits=limits, instruction_bindings=instructions)
    assert [row.node_id for row in value.node_limits] == ["second", "first"]
    with pytest.raises(ContractError, match="authorized node order"):
        grant(node_limits=limits, instruction_bindings=tuple(reversed(instructions)))
    with pytest.raises(ContractError, match="authorized node order"):
        grant(instruction_bindings=(InstructionBinding("foreign", "one", DIGEST),))


def test_initial_references_use_canonical_order_without_sorting_unreviewed_input():
    ordered = (InitialInputBinding("a", "one", DIGEST), InitialInputBinding("b", "two", DIGEST))
    assert grant(initial_input_bindings=ordered).initial_input_bindings == ordered
    with pytest.raises(ContractError, match="canonical reference order"):
        grant(initial_input_bindings=tuple(reversed(ordered)))


@pytest.mark.parametrize("start,end", [
    (AT, AT), (AT, "2026-09-21T13:59:59Z"), (AT, "2026-09-22T14:00:00.0000001Z"),
    ("2026-09-21T14:00:00.123456789Z", "2026-09-21T14:00:00.123456788Z"),
    ("2026-09-21T14:00:00.10Z", "2026-09-21T14:00:00.100Z"),
    (AT, "2026-09-21T15:00:00+01:00"), (AT, "2026-09-31T15:00:00Z"),
])
def test_expiry_refuses_exact_boundary_violations_and_invalid_instants(start, end):
    with pytest.raises(ContractError):
        authorization_interval(start, end)


@pytest.mark.parametrize("start,end", [
    (AT, "2026-09-22T14:00:00Z"), (AT, "2026-09-21T14:00:00.000000001Z"),
    ("2026-09-21T14:00:00.123456789Z", "2026-09-21T14:00:00.123456790Z"),
    ("2026-09-21T14:00:00.12+00:00", "2026-09-22T14:00:00.120Z"),
    ("2028-02-28T14:00:00Z", "2028-02-29T14:00:00Z"),
])
def test_expiry_accepts_exact_submicrosecond_and_calendar_boundaries(start, end):
    authorization_interval(start, end)
    assert grant(authorized_at=start, expires_at=end).expires_at == end


@pytest.mark.parametrize("action", ["pause", "resume", "revoke"])
def test_control_is_exact_detached_data_and_records_the_actual_actor(action):
    subject = control(action=action, expected_control_id="previous-control")
    assert set(subject.as_dict()) == CONTROL_FIELDS
    assert RunAuthorizationControl.from_dict(subject.as_dict()) == subject
    assert subject.actor == "Project owner" and subject.action == action


@pytest.mark.parametrize("field", sorted(CONTROL_FIELDS))
def test_every_control_field_is_required(field):
    body = control().as_dict()
    body.pop(field)
    with pytest.raises(ContractError):
        RunAuthorizationControl.from_dict(body)


@pytest.mark.parametrize("changes", [
    {"schema_version": 3}, {"action": "start"}, {"action": None},
    {"expected_control_id": "pause-one"}, {"actor": ""},
    {"authorization_digest": None}, {"recorded_at": "2026-09-21"},
])
def test_control_refuses_invalid_values(changes):
    with pytest.raises(ContractError):
        control(**changes)


def test_new_types_cannot_be_appended_or_activate_existing_store(tmp_path):
    from tests.test_command_run_store import CONFIG, a_run
    subject = RunStore(tmp_path)
    subject.create_run(a_run(run_id="run-one"), CONFIG)
    before = {path.relative_to(tmp_path): path.read_bytes()
              for path in tmp_path.rglob("*") if path.is_file()}
    for value in (grant(), control()):
        with pytest.raises(StoreError, match="frozen Policy opt-in"):
            subject.append(value)
    assert {path.relative_to(tmp_path): path.read_bytes()
            for path in tmp_path.rglob("*") if path.is_file()} == before


def test_wire_cannot_request_digest_derivation_or_smuggle_extra_grant_fields():
    for patch in ({"authorization_digest": ""}, {"raw_prompt": "do unbounded work"}):
        with pytest.raises(ContractError):
            RunAuthorization.from_dict({**grant().as_dict(), **patch})
    with pytest.raises(ContractError):
        RunAuthorizationControl.from_dict({**control().as_dict(), "automatic": True})


@pytest.mark.parametrize("name", ["\ud800", "\udfff"])
@pytest.mark.parametrize("kind", ["grant", "control"])
def test_human_identity_must_be_encodable_as_exact_utf8(name, kind):
    with pytest.raises(ContractError):
        if kind == "grant":
            grant(authorized_by=name)
        else:
            control(actor=name)


def test_human_identity_keeps_valid_unicode_and_emoji():
    name = "Владелец проекта 🧭"
    assert grant(authorized_by=name).authorized_by == name
    assert control(actor=name).actor == name
    assert grant(authorized_by=name).authorization_digest == independently_digest(
        grant(authorized_by=name).as_dict())
