"""Strict value-contract tests for RT-2 AttemptEvent facts."""
from __future__ import annotations

import pytest

from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.contracts import ActionRequest, ContractError, canonical_json


NOW = "2026-08-13T18:00:00Z"


def an_action(**changes):
    values = {
        "action_id": "action-001", "run_id": "run-001",
        "attempt_id": "attempt-001", "instance_id": "claude-dev",
        "capability": "dispatch", "arguments": {"handoff": "packet-001"},
        "scope": ("src",), "requested_by": "owner", "requested_at": NOW,
        "idempotency_key": "dispatch-001", "timeout_seconds": 900,
        "preview_digest": "sha256:" + "b" * 64, "mode": "confirm",
    }
    values.update(changes)
    return ActionRequest(**values)


def an_event(**changes):
    request = changes.pop("request", an_action())
    values = {
        "event_id": "event-lease", "run_id": request.run_id,
        "action_id": request.action_id, "attempt_id": request.attempt_id,
        "instance_id": request.instance_id, "adapter_id": "claude-code",
        "phase": "lease", "recorded_at": NOW,
        "request_digest": action_request_digest(request),
        "recovery_ref": "recovery-001", "outcome": None, "exit_code": None,
        "schema_version": 2,
    }
    values.update(changes)
    return AttemptEvent(**values)


def test_attempt_event_round_trip_is_frozen_and_has_exactly_thirteen_fields():
    event = an_event()
    payload = event.as_dict()
    assert len(payload) == 13
    assert tuple(payload) == (
        "event_id", "run_id", "action_id", "attempt_id", "instance_id",
        "adapter_id", "phase", "recorded_at", "request_digest", "recovery_ref",
        "outcome", "exit_code", "schema_version")
    assert payload["outcome"] is None and payload["exit_code"] is None
    assert AttemptEvent.from_dict(payload) == event
    with pytest.raises(AttributeError):
        event.phase = "observed"


@pytest.mark.parametrize("change", [
    {"phase": "started"},
    {"phase": "lease", "outcome": "unknown"},
    {"phase": "lease", "exit_code": 0},
    {"phase": "observed", "outcome": None},
    {"phase": "observed", "outcome": "verification_failed"},
    {"phase": "observed", "outcome": "succeeded", "exit_code": True},
    {"recovery_ref": "not an id"},
])
def test_phase_outcome_exit_and_recovery_ref_contract_is_strict(change):
    with pytest.raises(ContractError):
        an_event(**change)


def test_observed_accepts_only_the_five_effect_facts_and_nullable_integer_exit():
    outcomes = ("succeeded", "failed", "cancelled", "rejected", "unknown")
    for index, outcome in enumerate(outcomes):
        event = an_event(
            event_id=f"event-{index}", phase="observed", outcome=outcome,
            exit_code=None if outcome in {"cancelled", "unknown"} else index)
        assert event.outcome == outcome


def test_from_dict_refuses_missing_or_extra_fields_instead_of_preserving_them():
    payload = an_event().as_dict()
    for changed in ({key: value for key, value in payload.items() if key != "exit_code"},
                    {**payload, "future": "meaning"}):
        with pytest.raises(ContractError, match="fields must be exact"):
            AttemptEvent.from_dict(changed)


def test_request_digest_covers_every_canonical_request_field_and_extra():
    baseline = an_action()
    assert action_request_digest(baseline).startswith("sha256:")
    variants = [
        an_action(arguments={"handoff": "changed"}),
        an_action(scope=("tests",)),
        an_action(timeout_seconds=901),
        an_action(extra={"future_authority": "pinned"}),
    ]
    digests = {action_request_digest(baseline)}
    digests.update(action_request_digest(variant) for variant in variants)
    assert len(digests) == 5
    canonical_json(baseline.as_dict())
    with pytest.raises(ContractError, match="validated ActionRequest"):
        action_request_digest(baseline.as_dict())
