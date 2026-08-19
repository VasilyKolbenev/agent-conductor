"""RunStore causality for RT-2 attempt events and terminal receipts."""
from __future__ import annotations

import json

import pytest

from conductor.command import run_store as run_store_module
from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.graph_definition import GraphDefinition
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    DecisionReceipt,
    EvidenceRef,
    ObservationRecord,
)
from conductor.command.run_store import CorruptRun, RunStore, StoreError

from tests.test_command_run_store import (
    CONFIG,
    a_decision,
    a_run,
    an_action,
    write_decision_file,
)


NOW = "2026-08-13T18:00:00Z"
FINAL_OUTCOMES = (
    "succeeded", "failed", "cancelled", "rejected", "unknown",
    "verification_failed",
)
OBSERVED_FINALS = {
    "succeeded": frozenset({"succeeded", "verification_failed"}),
    "failed": frozenset({"failed"}),
    "cancelled": frozenset({"cancelled"}),
    "rejected": frozenset({"failed"}),
    "unknown": frozenset({"unknown"}),
}
OBSERVED_EXITS = {
    "succeeded": 0, "failed": -1, "cancelled": None,
    "rejected": None, "unknown": None,
}
OBSERVED_PRIMARY_FINAL = {
    "succeeded": "succeeded", "failed": "failed", "cancelled": "cancelled",
    "rejected": "failed", "unknown": "unknown",
}


def an_event(phase="effect_lease", **changes):
    action = changes.pop("action", an_action())
    observed = phase == "execution_observed"
    values = {
        "event_id": "event-observed" if observed else "event-lease",
        "run_id": action.run_id, "action_id": action.action_id,
        "attempt_id": action.attempt_id, "instance_id": action.instance_id,
        "adapter_id": "claude-code", "phase": phase, "recorded_at": NOW,
        "request_digest": action_request_digest(action), "recovery_ref": "recovery-001",
        "outcome": "succeeded" if observed else None,
        "exit_code": 0 if observed else None, "schema_version": 2,
    }
    values.update(changes)
    return AttemptEvent(**values)


def a_result(**changes):
    values = {
        "receipt_id": "result-001", "action_id": "action-001",
        "run_id": "run-001", "attempt_id": "attempt-001",
        "instance_id": "claude-dev", "outcome": "succeeded",
        "observed_at": NOW, "evidence_refs": (), "exit_code": 0,
    }
    values.update(changes)
    return ActionResultReceipt(**values)


def verified_evidence(**changes):
    values = {
        "evidence_id": "evidence-001", "run_id": "run-001",
        "kind": "verification", "uri": "verification/action-001",
        "label": "verified effect", "created_by": "claude-code",
        "observed_at": NOW, "verification": "verified",
        "verified_by": "claude-code", "verified_at": NOW,
    }
    values.update(changes)
    return EvidenceRef(**values)


def a_store(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(an_action())
    return store


def journal(store):
    return store.run_path("run-001") / "records.jsonl"


def raw_append(store, value, kind="attempt_event"):
    wrapper = {"record": value.as_dict(), "record_type": kind}
    payload = json.dumps(
        wrapper, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    with journal(store).open("ab") as stream:
        stream.write(payload.encode("utf-8"))


def test_the_record_registry_is_exactly_this_closed_set_of_contract_identity_pairs():
    """The whole durable vocabulary, written out so a new kind cannot arrive quietly.

    The name used to count the rows, which made adding an honest kind look like
    breaking a rule; what the store actually promises is that this mapping is
    CLOSED, not that it has a particular size.
    """
    assert run_store_module._RECORDS == {
        "action_request": (ActionRequest, "action_id"),
        "action_result": (ActionResultReceipt, "receipt_id"),
        "evidence": (EvidenceRef, "evidence_id"),
        "decision": (DecisionReceipt, "receipt_id"),
        "action_proposal": (ActionProposal, "proposal_id"),
        "adapter_observation": (ObservationRecord, "observation_id"),
        "attempt_event": (AttemptEvent, "event_id"),
        "graph_definition": (GraphDefinition, "graph_id"),
    }


def test_attempt_event_wrapper_has_one_exact_canonical_spelling_and_round_trips(tmp_path):
    store = a_store(tmp_path)
    event = an_event()
    assert store.append(event) is True
    expected = json.dumps(
        {"record": event.as_dict(), "record_type": "attempt_event"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    assert journal(store).read_text(encoding="utf-8").splitlines(keepends=True)[-1] == expected
    replayed = store.read("run-001").records[-1]
    assert replayed.kind == "attempt_event" and replayed.value == event


def test_legacy_six_kind_history_without_attempt_events_stays_valid(tmp_path):
    store = a_store(tmp_path)
    assert store.append(a_result()) is True
    assert [row.kind for row in store.read("run-001").records] == [
        "action_request", "action_result"]


def test_lease_observed_and_matching_terminal_result_append_and_replay(tmp_path):
    store = a_store(tmp_path)
    assert store.append(an_event()) is True
    assert store.append(an_event("execution_observed")) is True
    assert store.append(a_result()) is True
    assert [row.kind for row in store.read("run-001").records] == [
        "action_request", "attempt_event", "attempt_event", "action_result"]


def test_journal_order_not_timestamps_establishes_lease_before_observed(tmp_path):
    store = a_store(tmp_path)
    store.append(an_event(recorded_at="2026-08-13T19:00:00Z"))
    store.append(an_event(
        "execution_observed", recorded_at="2026-08-13T17:00:00Z"))
    assert store.append(a_result()) is True


@pytest.mark.parametrize("changes,match", [
    ({"action_id": "action-missing"}, "unknown action"),
    ({"attempt_id": "attempt-other"}, "attempt_id"),
    ({"instance_id": "codex-review"}, "instance_id"),
    ({"request_digest": "sha256:" + "f" * 64}, "request_digest"),
    ({"adapter_id": "codex"}, "frozen binding"),
])
def test_attempt_event_must_match_exact_request_and_frozen_binding(
        tmp_path, changes, match):
    store = a_store(tmp_path)
    before = journal(store).read_bytes()
    with pytest.raises(StoreError, match=match):
        store.append(an_event(**changes))
    assert journal(store).read_bytes() == before


def test_phase_uniqueness_and_observed_lease_relation_are_held(tmp_path):
    store = a_store(tmp_path)
    with pytest.raises(StoreError, match="no lease"):
        store.append(an_event("execution_observed"))
    store.append(an_event())
    with pytest.raises(StoreError, match="already has"):
        store.append(an_event(event_id="event-lease-two"))
    for changes, match in [
        ({"request_digest": "sha256:" + "f" * 64}, "request_digest"),
        ({"adapter_id": "codex"}, "adapter"),
        ({"recovery_ref": "recovery-other"}, "recovery_ref"),
    ]:
        with pytest.raises(StoreError, match=match):
            store.append(an_event("execution_observed", **changes))


def test_recovery_ref_is_exclusive_to_one_action_identity(tmp_path):
    store = a_store(tmp_path)
    store.append(an_event())
    second = an_action(
        action_id="action-002", attempt_id="attempt-002", idempotency_key="dispatch-002")
    store.append(second)
    with pytest.raises(StoreError, match="another action"):
        store.append(an_event(event_id="event-other", action=second))


def test_attempt_id_is_exclusive_to_one_action_identity(tmp_path):
    store = a_store(tmp_path)
    store.append(an_event())
    second = an_action(
        action_id="action-002", idempotency_key="dispatch-002")
    store.append(second)
    with pytest.raises(StoreError, match="attempt_id.*another action"):
        store.append(an_event(
            event_id="event-other", action=second, recovery_ref="recovery-002"))


@pytest.mark.parametrize("phase", ["effect_lease", "execution_observed"])
def test_no_attempt_event_may_follow_terminal_result(tmp_path, phase):
    store = a_store(tmp_path)
    store.append(a_result())
    before = journal(store).read_bytes()
    with pytest.raises(StoreError, match="cannot follow terminal result"):
        store.append(an_event(phase))
    assert journal(store).read_bytes() == before


def test_event_bearing_action_has_at_most_one_terminal_result(tmp_path):
    store = a_store(tmp_path)
    store.append(an_event())
    store.append(a_result(outcome="unknown", exit_code=None))
    with pytest.raises(StoreError, match="already has a terminal result"):
        store.append(a_result(receipt_id="result-002", outcome="unknown", exit_code=None))


@pytest.mark.parametrize("outcome", FINAL_OUTCOMES)
def test_lease_only_final_matrix_allows_exactly_unknown_null_and_evidence_free(
        tmp_path, outcome):
    store = a_store(tmp_path)
    store.append(an_event())
    before = journal(store).read_bytes()
    result = a_result(outcome=outcome, exit_code=None)
    if outcome == "unknown":
        assert store.append(result) is True
    else:
        with pytest.raises(StoreError, match="lease-only"):
            store.append(result)
        assert journal(store).read_bytes() == before


@pytest.mark.parametrize("outcome,exit_code,evidence_refs", [
    ("unknown", 1, ()),
    ("unknown", None, ("evidence-001",)),
])
def test_lease_only_unknown_still_requires_null_exit_and_empty_evidence(
        tmp_path, outcome, exit_code, evidence_refs):
    store = a_store(tmp_path)
    store.append(an_event())
    before = journal(store).read_bytes()
    with pytest.raises(StoreError, match="lease-only"):
        store.append(a_result(
            outcome=outcome, exit_code=exit_code, evidence_refs=evidence_refs))
    assert journal(store).read_bytes() == before


@pytest.mark.parametrize("observed", tuple(OBSERVED_FINALS))
@pytest.mark.parametrize("final", FINAL_OUTCOMES)
def test_observed_to_final_cross_product_holds_the_exact_frozen_map(
        tmp_path, observed, final):
    store = a_store(tmp_path)
    store.append(an_event())
    exit_code = OBSERVED_EXITS[observed]
    store.append(an_event(
        "execution_observed", outcome=observed, exit_code=exit_code))
    result = a_result(outcome=final, exit_code=exit_code)
    if final in OBSERVED_FINALS[observed]:
        assert store.append(result) is True
    else:
        with pytest.raises(StoreError, match="contradicts"):
            store.append(result)


@pytest.mark.parametrize("observed,event_exit,result_exit", [
    ("succeeded", 0, None),
    ("succeeded", None, 0),
    ("failed", -1, None),
    ("failed", None, -1),
    ("cancelled", None, 1),
    ("rejected", None, 1),
    ("unknown", None, 1),
])
def test_result_exit_must_exactly_equal_every_valid_observed_exit_form(
        tmp_path, observed, event_exit, result_exit):
    store = a_store(tmp_path)
    store.append(an_event())
    store.append(an_event(
        "execution_observed", outcome=observed, exit_code=event_exit))
    final = OBSERVED_PRIMARY_FINAL[observed]
    with pytest.raises(StoreError, match="exit_code"):
        store.append(a_result(outcome=final, exit_code=result_exit))


def test_verified_evidence_must_follow_observed_and_precede_succeeded_result(tmp_path):
    store = a_store(tmp_path)
    store.append(an_event())
    store.append(an_event("execution_observed"))
    store.append(verified_evidence())
    assert store.append(a_result(evidence_refs=("evidence-001",))) is True


@pytest.mark.parametrize("final,observed", [
    ("succeeded", "succeeded"),
    ("failed", "failed"),
    ("cancelled", "cancelled"),
    ("failed", "rejected"),
    ("unknown", "unknown"),
    ("verification_failed", "succeeded"),
])
def test_causal_bound_evidence_is_accepted_if_and_only_if_final_succeeded(
        tmp_path, final, observed):
    store = a_store(tmp_path)
    store.append(an_event())
    exit_code = OBSERVED_EXITS[observed]
    store.append(an_event(
        "execution_observed", outcome=observed, exit_code=exit_code))
    store.append(verified_evidence())
    result = a_result(
        outcome=final, exit_code=exit_code, evidence_refs=("evidence-001",))
    if final == "succeeded":
        assert store.append(result) is True
    else:
        with pytest.raises(StoreError):
            store.append(result)


@pytest.mark.parametrize("changes", [
    {"run_id": "run-other"}, {"kind": "test"}, {"uri": "verification/action-other"},
    {"created_by": "codex"}, {"verified_by": "codex"},
    {"verification": "unavailable", "verified_by": "codex"},
])
def test_result_evidence_is_bound_to_run_action_adapter_and_verified_state(
        tmp_path, changes):
    store = a_store(tmp_path)
    store.append(an_event())
    store.append(an_event("execution_observed"))
    evidence = verified_evidence(**changes)
    if evidence.run_id == "run-001":
        store.append(evidence)
    else:
        raw_append(store, evidence, "evidence")
    before = journal(store).read_bytes()
    with pytest.raises((StoreError, CorruptRun)):
        store.append(a_result(evidence_refs=(evidence.evidence_id,)))
    assert journal(store).read_bytes() == before


def test_evidence_before_observed_is_not_causal_even_if_every_field_matches(tmp_path):
    store = a_store(tmp_path)
    store.append(an_event())
    store.append(verified_evidence())
    store.append(an_event("execution_observed"))
    with pytest.raises(StoreError, match="must follow"):
        store.append(a_result(evidence_refs=("evidence-001",)))


def test_duplicate_evidence_refs_are_refused_for_event_bearing_result(tmp_path):
    store = a_store(tmp_path)
    store.append(an_event())
    store.append(an_event("execution_observed"))
    store.append(verified_evidence())
    with pytest.raises(StoreError, match="unique"):
        store.append(a_result(evidence_refs=("evidence-001", "evidence-001")))


@pytest.mark.parametrize("order", ["result-lease", "lease-result-observed"])
def test_raw_canonical_terminal_event_reordering_breaks_read_recover_and_later_append(
        tmp_path, order):
    store = a_store(tmp_path)
    if order == "result-lease":
        raw_append(store, a_result(), "action_result")
        raw_append(store, an_event())
    else:
        raw_append(store, an_event())
        raw_append(store, a_result(outcome="unknown", exit_code=None), "action_result")
        raw_append(store, an_event("execution_observed"))
    before = journal(store).read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001"),
            lambda: store.append(verified_evidence())):
        with pytest.raises(CorruptRun, match="replay causality"):
            operation()
        assert journal(store).read_bytes() == before


@pytest.mark.parametrize("changes", [
    {"action_id": "action-missing"},
    {"attempt_id": "attempt-other"},
    {"instance_id": "codex-review"},
    {"request_digest": "sha256:" + "f" * 64},
    {"adapter_id": "codex"},
])
def test_raw_canonical_event_relation_damage_breaks_every_store_entry_inertly(
        tmp_path, changes):
    store = a_store(tmp_path)
    raw_append(store, an_event(**changes))
    before = journal(store).read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001"),
            lambda: store.append(verified_evidence())):
        with pytest.raises(CorruptRun, match="replay causality"):
            operation()
        assert journal(store).read_bytes() == before


def test_raw_observed_without_lease_and_mismatched_lease_are_replay_corruption(tmp_path):
    for suffix, rows in [
        ("missing", [an_event("execution_observed")]),
        ("mismatch", [an_event(), an_event(
            "execution_observed", recovery_ref="recovery-other")]),
    ]:
        store = a_store(tmp_path / suffix)
        for row in rows:
            raw_append(store, row)
        before = journal(store).read_bytes()
        with pytest.raises(CorruptRun, match="replay causality"):
            store.read("run-001")
        with pytest.raises(CorruptRun, match="replay causality"):
            store.recover("run-001")
        assert journal(store).read_bytes() == before


def test_real_config_binding_is_threaded_through_orphan_decision_prospective_replay(tmp_path):
    store = a_store(tmp_path)
    raw_append(store, an_event(adapter_id="codex"))
    receipt = a_decision()
    receipt_file = write_decision_file(store, receipt)
    journal_before = journal(store).read_bytes()
    receipt_before = receipt_file.read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001")):
        with pytest.raises(CorruptRun, match="frozen binding"):
            operation()
        assert journal(store).read_bytes() == journal_before
        assert receipt_file.read_bytes() == receipt_before


@pytest.mark.parametrize("second", [
    an_event(event_id="event-lease-two"),
    an_event("execution_observed", recovery_ref="recovery-other"),
])
def test_raw_duplicate_phase_or_observed_mismatch_breaks_every_store_entry(
        tmp_path, second):
    store = a_store(tmp_path)
    raw_append(store, an_event())
    raw_append(store, second)
    before = journal(store).read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001"),
            lambda: store.append(verified_evidence())):
        with pytest.raises(CorruptRun, match="replay causality"):
            operation()
        assert journal(store).read_bytes() == before


@pytest.mark.parametrize("result", [
    a_result(outcome="failed", exit_code=0),
    a_result(outcome="succeeded", exit_code=None),
    a_result(evidence_refs=("evidence-missing",)),
])
def test_raw_terminal_mapping_exit_or_evidence_damage_breaks_replay_inertly(
        tmp_path, result):
    store = a_store(tmp_path)
    raw_append(store, an_event())
    raw_append(store, an_event("execution_observed"))
    raw_append(store, result, "action_result")
    before = journal(store).read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001"),
            lambda: store.append(verified_evidence())):
        with pytest.raises(CorruptRun, match="replay causality"):
            operation()
        assert journal(store).read_bytes() == before


def test_raw_second_terminal_identity_for_event_bearing_action_is_corruption(tmp_path):
    store = a_store(tmp_path)
    raw_append(store, an_event())
    raw_append(store, a_result(outcome="unknown", exit_code=None), "action_result")
    raw_append(store, a_result(
        receipt_id="result-002", outcome="unknown", exit_code=None), "action_result")
    before = journal(store).read_bytes()
    with pytest.raises(CorruptRun, match="already has a terminal result"):
        store.read("run-001")
    with pytest.raises(CorruptRun, match="already has a terminal result"):
        store.recover("run-001")
    assert journal(store).read_bytes() == before


def test_raw_attempt_id_rebound_to_another_action_breaks_every_store_entry(tmp_path):
    store = a_store(tmp_path)
    raw_append(store, an_event())
    second = an_action(action_id="action-002", idempotency_key="dispatch-002")
    raw_append(store, second, "action_request")
    raw_append(store, an_event(
        event_id="event-other", action=second, recovery_ref="recovery-002"))
    before = journal(store).read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001"),
            lambda: store.append(verified_evidence())):
        with pytest.raises(CorruptRun, match="attempt_id.*another action"):
            operation()
        assert journal(store).read_bytes() == before


def test_event_for_unbound_request_instance_fails_append_and_raw_replay(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    action = an_action(instance_id="unbound-instance")
    store.append(action)
    event = an_event(action=action)
    before = journal(store).read_bytes()
    with pytest.raises(StoreError, match="declares no instance"):
        store.append(event)
    assert journal(store).read_bytes() == before
    raw_append(store, event)
    damaged = journal(store).read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001"),
            lambda: store.append(verified_evidence())):
        with pytest.raises(CorruptRun, match="declares no instance"):
            operation()
        assert journal(store).read_bytes() == damaged


def test_raw_preplanted_evidence_cannot_become_causal_after_observed(tmp_path):
    store = a_store(tmp_path)
    raw_append(store, an_event())
    raw_append(store, verified_evidence(), "evidence")
    raw_append(store, an_event("execution_observed"))
    raw_append(store, a_result(evidence_refs=("evidence-001",)), "action_result")
    before = journal(store).read_bytes()
    for operation in (
            lambda: store.read("run-001"), lambda: store.recover("run-001"),
            lambda: store.append(verified_evidence(evidence_id="evidence-002"))):
        with pytest.raises(CorruptRun, match="must follow"):
            operation()
        assert journal(store).read_bytes() == before
