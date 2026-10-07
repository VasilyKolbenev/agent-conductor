"""Contract tests for the December Command v2 decision boundary.

These objects do not execute a Harness or write runtime state. They make the
facts every later writable surface must carry explicit and serializable first.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.contracts import (
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    ControlMode,
    DecisionReceipt,
    EvidenceRef,
    RunEnvelope,
    canonical_json,
    frozen_config_bindings,
    gate_decision,
)


NOW = "2026-08-11T07:30:00Z"
DIGEST = "sha256:" + "a" * 64
PREVIEW = "sha256:" + "b" * 64


def a_run(**changes):
    values = {
        "run_id": "run-001",
        "cycle_id": "default-orbit",
        "created_at": NOW,
        "mode": "observe",
        "config_digest": DIGEST,
    }
    values.update(changes)
    return RunEnvelope(**values)


def an_action(**changes):
    values = {
        "action_id": "action-001",
        "run_id": "run-001",
        "attempt_id": "attempt-001",
        "instance_id": "claude-dev",
        "capability": "dispatch",
        "arguments": {"handoff": "packet-001"},
        "scope": ("src", "tests/test_api.py"),
        "requested_by": "owner",
        "requested_at": NOW,
        "idempotency_key": "dispatch-default-orbit-001",
        "timeout_seconds": 900,
        "preview_digest": PREVIEW,
        "mode": "confirm",
    }
    values.update(changes)
    return ActionRequest(**values)


def a_decision(**changes):
    values = {
        "receipt_id": "decision-001",
        "run_id": "run-001",
        "gate_id": "release",
        "action": "approve",
        "actor": "release-owner",
        "decided_at": NOW,
        "reason": "Reviewed the attached evidence.",
        "scope_refs": ("release",),
        "config_digest": DIGEST,
        "evidence_refs": ("evidence-001",),
    }
    values.update(changes)
    return DecisionReceipt(**values)


def test_new_runs_default_to_observe_and_never_invent_an_execution_mode():
    run = RunEnvelope(
        run_id="run-001", cycle_id="default-orbit", created_at=NOW,
        config_digest=DIGEST)
    assert run.mode is ControlMode.OBSERVE
    assert run.status == "created"


@pytest.mark.parametrize("field,value", [
    ("run_id", "../run"),
    ("cycle_id", ""),
    ("created_at", "2026-08-11T07:30:00"),
    ("created_at", "2026-08-11T10:30:00+03:00"),
    ("config_digest", "a" * 64),
    ("config_digest", "sha256:not-hex"),
    ("mode", "autonomous"),
])
def test_run_boundary_rejects_ambiguous_identity_time_digest_and_authority(field, value):
    with pytest.raises(ContractError, match=field):
        a_run(**{field: value})


def test_the_authority_ladder_is_exactly_these_four_modes_and_hides_no_fifth():
    # Relational pin, not a single spelling: the whole serialized member set is
    # compared against an independent literal, so any added, removed, or renamed
    # mode reddens here -- a hidden fifth authority cannot slip in named anything.
    assert {member.value for member in ControlMode} == {
        "observe", "propose", "confirm", "policy"}


def test_tolerant_run_reader_preserves_unknown_fields_without_aliasing_input():
    raw = a_run().as_dict()
    raw["schema_version"] = 3
    raw["future"] = {"budget": [1, 2]}
    parsed = RunEnvelope.from_dict(raw)
    raw["future"]["budget"].append(3)
    assert parsed.schema_version == 3
    assert parsed.as_dict()["future"] == {"budget": [1, 2]}


@pytest.mark.parametrize("scope", [
    ("../secrets",),
    ("/etc/passwd",),
    ("C:/Windows/System32",),
    ("src\\outside",),
    ("",),
])
def test_action_scope_is_canonical_and_cannot_escape_the_project(scope):
    with pytest.raises(ContractError, match="scope"):
        an_action(scope=scope)


@pytest.mark.parametrize("field,value", [
    ("timeout_seconds", 0),
    ("timeout_seconds", 86401),
    ("idempotency_key", ""),
    ("preview_digest", "sha256:1234"),
    ("mode", "observe"),
])
def test_executable_action_requires_a_bounded_confirmed_or_policy_preview(field, value):
    with pytest.raises(ContractError, match=field):
        an_action(**{field: value})


def test_action_arguments_are_copied_and_canonical_json_does_not_follow_input_order():
    left_args = {"z": [2, 1], "a": {"enabled": True}}
    right_args = {"a": {"enabled": True}, "z": [2, 1]}
    left = an_action(arguments=left_args)
    right = an_action(arguments=right_args)
    left_args["z"].append(9)
    assert left.as_dict()["arguments"] == {"z": [2, 1], "a": {"enabled": True}}
    assert canonical_json(left) == canonical_json(right)
    assert json.loads(canonical_json(left))["action_id"] == "action-001"


def test_action_arguments_and_unknown_fields_cannot_change_after_preview_creation():
    action = ActionRequest.from_dict({
        **an_action().as_dict(),
        "future": {"budget": [1, 2]},
    })
    with pytest.raises(TypeError):
        action.arguments["handoff"] = "changed"
    with pytest.raises(AttributeError):
        action.extra["future"]["budget"].append(3)
    assert action.as_dict()["future"] == {"budget": [1, 2]}


def test_action_result_cannot_report_acceptance_as_success():
    with pytest.raises(ContractError, match="outcome"):
        ActionResultReceipt(
            receipt_id="result-001", action_id="action-001", run_id="run-001",
            attempt_id="attempt-001", instance_id="claude-dev",
            outcome="accepted", observed_at=NOW)
    result = ActionResultReceipt(
        receipt_id="result-001", action_id="action-001", run_id="run-001",
        attempt_id="attempt-001", instance_id="claude-dev",
        outcome="succeeded", observed_at=NOW, evidence_refs=("evidence-001",))
    assert result.outcome == "succeeded"
    assert "accepted" not in result.as_dict().values()


def test_evidence_with_a_digest_remains_unverified_until_a_verifier_records_observation():
    claim = EvidenceRef(
        evidence_id="evidence-001", run_id="run-001", kind="test", uri="artifacts/test.json",
        label="pytest result", created_by="claude-dev", observed_at=NOW,
        digest=DIGEST)
    assert claim.verification == "unverified"
    with pytest.raises(ContractError, match="verified_by"):
        EvidenceRef(
            evidence_id="evidence-001", run_id="run-001", kind="test", uri="artifacts/test.json",
            label="pytest result", created_by="claude-dev", observed_at=NOW,
            digest=DIGEST, verification="verified")
    verified = EvidenceRef(
        evidence_id="evidence-001", run_id="run-001", kind="test", uri="artifacts/test.json",
        label="pytest result", created_by="claude-dev", observed_at=NOW,
        digest=DIGEST, verification="verified", verified_by="codex-review",
        verified_at=NOW)
    assert verified.verification == "verified"


@pytest.mark.parametrize("action,reason", [
    ("request_changes", ""),
    ("waive", ""),
    ("silence", "Nobody objected."),
])
def test_human_decision_boundary_rejects_reasonless_exceptions_and_silence(action, reason):
    with pytest.raises(ContractError, match="action|reason"):
        a_decision(action=action, reason=reason)


def test_a_human_gate_is_idle_without_a_receipt_and_follows_the_latest_unsuperseded_one():
    assert gate_decision([], "run-001", "release") == "idle"
    approved = a_decision()
    assert gate_decision([approved], "run-001", "release") == "satisfied"
    rejected = a_decision(
        receipt_id="decision-002", action="reject",
        decided_at="2026-08-11T07:31:00Z", supersedes="decision-001")
    assert gate_decision([approved, rejected], "run-001", "release") == "failed"
    waived = a_decision(action="waive", reason="Emergency exception is recorded.")
    assert gate_decision([waived], "run-001", "release") == "waived"


def test_a_decision_from_an_older_run_cannot_satisfy_the_same_gate_in_this_run():
    old = a_decision(run_id="run-old")
    assert gate_decision([old], "run-001", "release") == "idle"


def test_parallel_human_decisions_are_a_conflict_until_one_explicitly_supersedes_the_other():
    first = a_decision()
    second = a_decision(
        receipt_id="decision-002", action="reject",
        decided_at="2026-08-11T07:31:00Z")
    with pytest.raises(ContractError, match="multiple unsuperseded"):
        gate_decision([first, second], "run-001", "release")
    orphan = a_decision(receipt_id="decision-003", supersedes="decision-missing")
    with pytest.raises(ContractError, match="unknown receipt"):
        gate_decision([orphan], "run-001", "release")


def test_frozen_config_bindings_read_each_instances_declared_adapter():
    config = {
        "instances": [
            {"id": "claude-dev", "adapter": "claude-code"},
            {"id": "codex-review", "adapter": "codex", "api_key_env": "OPENAI_API_KEY"},
        ],
    }
    assert frozen_config_bindings(config) == {
        "claude-dev": "claude-code", "codex-review": "codex"}
    # A config that declares no instances binds nothing, so every instance is unknown.
    assert frozen_config_bindings({"cycle": {"id": "orbit"}}) == {}


@pytest.mark.parametrize("config,match", [
    ({"instances": {"id": "a", "adapter": "b"}}, "must be a list"),
    ({"instances": ["claude-dev"]}, "must be a JSON object"),
    ({"instances": [{"adapter": "claude-code"}]}, "configured instance id"),
    ({"instances": [{"id": "claude-dev"}]}, "configured adapter id"),
    ({"instances": [{"id": "a/b", "adapter": "claude-code"}]}, "configured instance id"),
    ({"instances": [{"id": "a", "adapter": "claude-code"},
                    {"id": "a", "adapter": "codex"}]}, "more than once"),
])
def test_frozen_config_bindings_reject_a_malformed_or_ambiguous_declaration(config, match):
    with pytest.raises(ContractError, match=match):
        frozen_config_bindings(config)


def test_unknown_contract_values_must_still_be_canonical_json_data():
    raw = a_run().as_dict()
    raw["future"] = {"not_json": float("nan")}
    with pytest.raises(ContractError, match="future"):
        RunEnvelope.from_dict(raw)


def test_every_receipt_reader_preserves_future_fields_on_a_round_trip():
    result = ActionResultReceipt(
        receipt_id="result-001", action_id="action-001", run_id="run-001",
        attempt_id="attempt-001", instance_id="claude-dev",
        outcome="failed", observed_at=NOW, detail="adapter refused")
    evidence = EvidenceRef(
        evidence_id="evidence-001", run_id="run-001", kind="test", uri="artifacts/test.json",
        label="pytest result", created_by="claude-dev", observed_at=NOW)
    for value, reader in (
        (result, ActionResultReceipt.from_dict),
        (evidence, EvidenceRef.from_dict),
        (a_decision(), DecisionReceipt.from_dict),
    ):
        raw = value.as_dict()
        raw["schema_version"] = 7
        raw["future"] = {"extension": ["kept"]}
        restored = reader(raw)
        assert restored.schema_version == 7
        assert restored.as_dict()["future"] == {"extension": ["kept"]}
        assert canonical_json(restored) == canonical_json(reader(restored.as_dict()))
