"""Proposal and durable-observation contracts for December Command v2.

An ActionProposal proposes; it prepares and executes nothing. Its preview
digest is a function of the whole proposal content, so a change to any
significant field invalidates it. A durable ObservationRecord carries what an
adapter reported, and never lets absence or an unknown become ready.
"""
from __future__ import annotations

import hashlib

import pytest

from conductor.command.contracts import (
    ActionProposal,
    ContractError,
    ObservationRecord,
    canonical_json,
)


NOW = "2026-08-11T07:30:00Z"
DIGEST = "sha256:" + "a" * 64


def a_proposal(**changes):
    values = {
        "proposal_id": "proposal-001",
        "run_id": "run-001",
        "attempt_id": "attempt-001",
        "instance_id": "claude-dev",
        "capability": "dispatch",
        "arguments": {"handoff": "packet-001"},
        "scope": ("src", "tests/test_api.py"),
        "proposed_by": "claude-dev",
        "proposed_at": NOW,
        "timeout_seconds": 900,
        "rationale": "The lane finished its handoff and asks to dispatch review.",
        "config_digest": DIGEST,
    }
    values.update(changes)
    return ActionProposal(**values)


def an_observation(**changes):
    values = {
        "observation_id": "observation-001",
        "run_id": "run-001",
        "adapter_id": "claude-code",
        "instance_id": "claude-dev",
        "observed_at": NOW,
        "health": "ready",
        "available_capabilities": ("observe", "dispatch"),
        "detail": "Connected through the configured transport.",
    }
    values.update(changes)
    return ObservationRecord(**values)


def test_a_proposal_computes_its_preview_digest_from_its_own_canonical_content():
    proposal = a_proposal()
    body = proposal.as_dict()
    body.pop("preview_digest")
    expected = "sha256:" + hashlib.sha256(
        canonical_json(body).encode("utf-8")).hexdigest()
    assert proposal.preview_digest == expected


# Each significant field, changed to a value the base proposal does not hold.
# The digest must move for every one of them; a screen that covered only some
# fields would leave the uncovered ones free to change under a stable digest.
_SIGNIFICANT = [
    ("proposal_id", "proposal-002"),
    ("run_id", "run-002"),
    ("attempt_id", "attempt-002"),
    ("instance_id", "codex-review"),
    ("capability", "review"),
    ("arguments", {"handoff": "packet-002"}),
    ("scope", ("docs",)),
    ("proposed_by", "someone-else"),
    ("proposed_at", "2026-08-11T08:00:00Z"),
    ("timeout_seconds", 600),
    ("rationale", "A different but equally honest reason."),
    ("config_digest", "sha256:" + "c" * 64),
    ("schema_version", 3),
    ("extra", {"future": {"budget": [1, 2]}}),
]


@pytest.mark.parametrize("field,value", _SIGNIFICANT)
def test_changing_any_significant_field_invalidates_the_preview_digest(field, value):
    base = a_proposal()
    changed = a_proposal(**{field: value})
    assert changed.preview_digest != base.preview_digest


@pytest.mark.parametrize("field,value", _SIGNIFICANT)
def test_a_durable_proposal_whose_field_was_edited_without_its_digest_is_refused(
        field, value):
    raw = a_proposal().as_dict()
    if field == "schema_version":
        raw[field] = value
    elif field == "extra":
        raw.update(value)
    else:
        raw[field] = list(value) if isinstance(value, tuple) else value
    # The preview_digest still names the untampered content, so reconstruction
    # must catch the disagreement rather than trust the stored digest.
    with pytest.raises(ContractError, match="preview_digest"):
        ActionProposal.from_dict(raw)


def test_a_proposal_carries_a_bounded_timeout_an_honest_reason_and_a_frozen_config():
    with pytest.raises(ContractError, match="timeout_seconds"):
        a_proposal(timeout_seconds=0)
    with pytest.raises(ContractError, match="timeout_seconds"):
        a_proposal(timeout_seconds=86401)
    with pytest.raises(ContractError, match="rationale"):
        a_proposal(rationale="   ")
    with pytest.raises(ContractError, match="config_digest"):
        a_proposal(config_digest="not-a-digest")
    with pytest.raises(ContractError, match="scope"):
        a_proposal(scope=("../secrets",))


def test_a_proposal_preserves_unknown_fields_and_stays_immutable_after_creation():
    # An unknown field is significant content, so the digest must be computed
    # over it; a proposal born with the field round-trips against its own digest.
    raw = a_proposal().as_dict()
    raw.pop("preview_digest")
    raw["future"] = {"budget": [1, 2]}
    proposal = ActionProposal.from_dict(raw)
    assert proposal.as_dict()["future"] == {"budget": [1, 2]}
    with pytest.raises(TypeError):
        proposal.arguments["handoff"] = "changed"
    with pytest.raises(AttributeError):
        proposal.extra["future"]["budget"].append(3)
    assert canonical_json(proposal) == canonical_json(
        ActionProposal.from_dict(proposal.as_dict()))


def test_a_proposal_is_not_an_action_request_and_names_no_idempotency_key():
    raw = a_proposal().as_dict()
    assert "idempotency_key" not in raw
    assert "preview_digest" in raw
    assert raw["schema_version"] == 2


def test_a_durable_observation_keeps_an_unknown_unknown_and_preserves_future_fields():
    observation = ObservationRecord.from_dict({
        **an_observation(health="unknown", available_capabilities=()).as_dict(),
        "future": {"probe": ["kept"]},
    })
    assert observation.health == "unknown"
    assert observation.available_capabilities == ()
    assert observation.as_dict()["future"] == {"probe": ["kept"]}
    assert canonical_json(observation) == canonical_json(
        ObservationRecord.from_dict(observation.as_dict()))


def test_a_durable_observation_rejects_an_invented_health_and_duplicate_capabilities():
    with pytest.raises(ContractError, match="health"):
        an_observation(health="totally-ready")
    with pytest.raises(ContractError, match="available_capabilities"):
        an_observation(available_capabilities=("observe", "observe"))
    with pytest.raises(ContractError, match="observed_at"):
        an_observation(observed_at="2026-08-11T07:30:00")


def test_a_durable_observation_carries_run_instance_and_adapter_identity():
    observation = an_observation()
    assert (observation.run_id, observation.instance_id, observation.adapter_id) == (
        "run-001", "claude-dev", "claude-code")
    with pytest.raises(ContractError, match="run_id"):
        an_observation(run_id="../escape")
    with pytest.raises(ContractError, match="evidence_refs"):
        an_observation(evidence_refs=("evidence-001", "evidence-001"))
