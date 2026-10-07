"""Independent checking spends live authority, not a second reading of an old grant."""
import json

import pytest

from conductor.command.adapters import AdapterRegistry, AdapterVerification
from conductor.command.adapters.base import Published
from conductor.command.contracts import ActionResultReceipt, DecisionReceipt, canonical_json
from conductor.command.run_store import CorruptRun, RunStore, StoreError
from conductor.command.runtime import AuthorizationError, AttemptState, ControlRuntime
from conductor.command.verify_road import PUBLISH_REASONS
from conductor.command import verify_holds as words

from tests.test_command_plan_verifier import (
    CHECKER, DOER, NODE, RUN_ID, _Signing, _a_verified_run, a_bound_store,
)
from tests.test_command_runtime_authorize import (
    NOW, a_budget, a_confirmation, a_proposal, fixed_clock, fixed_ids,
)


def circuit(path, *, checker_knobs=None, timeout=30):
    store = a_bound_store(path, verifier=CHECKER)
    doer = _Signing(store, adapter_id="claude-code")
    checker = _Signing(store, adapter_id="codex", **(checker_knobs or {}))
    registry = AdapterRegistry([doer, checker])
    runtime = ControlRuntime(store, registry, clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(store, instance_id=DOER, node_id=NODE,
                          timeout_seconds=timeout)
    return store, doer, checker, registry, runtime, proposal


@pytest.mark.parametrize("knobs,detail", [
    ({"verify_state": "mismatch"}, words.CHECKER_REJECTED),
    ({"verify_raises": True}, words.VERIFY_RAISED),
])
def test_checker_refusal_and_raise_release_the_doer_without_promoting_it(
        tmp_path, knobs, detail):
    store, doer, checker, _, runtime, proposal = circuit(tmp_path, checker_knobs=knobs)
    attempt = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.detail == detail
    assert doer.publish_calls == doer.release_calls == len(checker.independent_calls) == 1
    assert not [row for row in store.read(RUN_ID).records if row.kind == "evidence"]
    assert "private output" not in canonical_json(attempt.receipt.as_dict())


@pytest.mark.parametrize("refusal,detail", sorted(PUBLISH_REASONS.items()))
def test_the_doers_publish_hold_runs_before_any_checker(tmp_path, refusal, detail):
    """Every refusal a publication may carry, DERIVED and not listed.

    This was five hand-written rows while the closed set held six: a fold added
    a refusal, the enumeration that reads as exhaustive stayed as it was, and
    nothing said the road for the new key had never been driven. Taking the
    rows from the map itself makes the next widening arrive here on its own --
    and a sibling witness holds that map equal to the door's closed set, so a
    key legal anywhere is a key driven here.
    """
    store, doer, checker, _, _, proposal = circuit(tmp_path)
    doer.publish = lambda request, result: Published(refusal, (), None, (), ())
    # Registry snapshots optional seams at registration, not at the later call.
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    attempt = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.detail == detail
    assert checker.independent_calls == [] and doer.release_calls == 1


def _crash(*args, **kwargs):
    raise RuntimeError("simulated crash")


@pytest.mark.parametrize("started", [False, True])
def test_restart_with_no_checker_evidence_never_spends_a_second_grant(
        tmp_path, monkeypatch, started):
    store, doer, checker, registry, runtime, proposal = circuit(tmp_path)
    authorization = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    monkeypatch.setattr(runtime, "_resolve", _crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runtime.execute(authorization)
    checker.started = started
    resumed = ControlRuntime(store, registry, clock=fixed_clock(), ids=fixed_ids())
    attempt = resumed.execute(authorization)
    assert attempt.state is AttemptState.VERIFICATION_FAILED
    assert attempt.receipt.detail == (
        words.NOT_RESUMABLE_LOST if started else words.NOT_RESUMABLE_NEVER)
    assert doer.execute_calls == 1 and doer.publish_calls == 0
    assert checker.independent_calls == [] and doer.release_calls == 1


def test_restart_after_standing_checker_evidence_finishes_without_another_check(
        tmp_path, monkeypatch):
    store, doer, checker, registry, runtime, proposal = circuit(tmp_path)
    authorization = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    monkeypatch.setattr(runtime, "_finish", _crash)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runtime.execute(authorization)
    assert len(checker.independent_calls) == doer.publish_calls == doer.release_calls == 1
    resumed = ControlRuntime(store, registry, clock=fixed_clock(), ids=fixed_ids())
    attempt = resumed.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.verification_evidence[0].verifier_instance_id == CHECKER
    assert doer.execute_calls == doer.publish_calls == len(checker.independent_calls) == 1
    assert doer.release_calls == 2
    # Terminal replay touches NO seam, even a cleanup seam.
    assert resumed.execute(authorization).receipt == attempt.receipt
    assert doer.release_calls == 2


def test_one_action_budget_covers_the_attempt_and_its_independent_check(tmp_path):
    store, _, _, _, runtime, proposal = circuit(tmp_path, timeout=30)
    with pytest.raises(AuthorizationError, match="2 × timeout"):
        runtime.authorize(a_confirmation(proposal), budget=a_budget(max_action_seconds=59))
    assert not any(row.kind == "action_request" for row in store.read(RUN_ID).records)
    accepted = runtime.authorize(a_confirmation(proposal), budget=a_budget(max_action_seconds=60))
    assert accepted.record_created


@pytest.mark.parametrize("field,value", [
    ("verifier_instance_id", DOER), ("verified_by", "claude-code"),
])
def test_raw_journal_cannot_reassign_who_checked(tmp_path, field, value):
    store = _a_verified_run(tmp_path)
    path = store.run_path(RUN_ID) / "records.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    evidence = [row["record"] for row in rows if row["record_type"] == "evidence"]
    assert len(evidence) == 1
    evidence[0][field] = value
    path.write_text("".join(canonical_json(row) + "\n" for row in rows),
                    encoding="utf-8", newline="\n")
    with pytest.raises(CorruptRun):
        RunStore(tmp_path).read(RUN_ID)


@pytest.mark.parametrize("outcome", ["failed", "unknown"])
def test_unsuccessful_doer_has_no_checker_turn_but_releases_its_material(tmp_path, outcome):
    store, doer, checker, _, _, proposal = circuit(tmp_path)
    doer._execute_outcome = outcome
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    attempt = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.receipt.outcome == outcome
    assert checker.independent_calls == []
    assert doer.publish_calls == 0 and doer.release_calls == 1


@pytest.mark.parametrize("state,detail,expected", [
    ("error", "frame_over_limit", words.FRAME_OVER_LIMIT),
    ("mismatch", "frame_over_limit", "adapter verification was mismatch"),
    ("error", "arbitrary private text", "adapter verification was error"),
])
def test_checker_reason_is_a_closed_state_pair_not_copied_prose(
        tmp_path, state, detail, expected):
    store, doer, checker, _, _, proposal = circuit(tmp_path)
    checker.verify_for = lambda request, result, verifier, material: AdapterVerification(
        adapter_id="codex", action_id=request.action_id, state=state,
        observed_at=NOW, detail=detail)
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    attempt = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.receipt.detail == expected
    assert attempt.state is AttemptState.VERIFICATION_FAILED


def _change_plan_verifier(path, name):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    plans = [row["record"] for row in rows if row["record_type"] == "graph_definition"]
    assert len(plans) == 1
    node = next(row for row in plans[0]["nodes"] if row["node_id"] == NODE)
    node["verifier_instance_id"] = name
    path.write_text("".join(canonical_json(row) + "\n" for row in rows),
                    encoding="utf-8", newline="\n")


def test_undeclared_checker_cannot_replay_a_terminal_even_without_success_evidence(tmp_path):
    store, _, _, _, runtime, proposal = circuit(tmp_path, checker_knobs={"verify_state": "mismatch"})
    attempt = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.receipt.outcome == "verification_failed"
    path = store.run_path(RUN_ID) / "records.jsonl"
    _change_plan_verifier(path, "missing-participant")
    with pytest.raises(CorruptRun, match="missing-participant"):
        RunStore(tmp_path).read(RUN_ID)


def test_undeclared_checker_cannot_append_even_an_eventless_terminal(tmp_path):
    store, _, _, _, runtime, proposal = circuit(tmp_path)
    authorization = runtime.authorize(a_confirmation(proposal), budget=a_budget())
    # No event yet: this asks the ANY-terminal rule, not the evidence guard.
    path = store.run_path(RUN_ID) / "records.jsonl"
    _change_plan_verifier(path, "missing-participant")
    assert RunStore(tmp_path).read(RUN_ID).records
    request = authorization.request
    with pytest.raises(StoreError, match="missing-participant"):
        store.append(ActionResultReceipt(
            receipt_id="r-refused", run_id=RUN_ID, action_id=request.action_id,
            attempt_id=request.attempt_id, instance_id=DOER,
            outcome="unknown", observed_at=NOW))


def test_publishing_failure_also_releases_the_doers_cached_material(tmp_path):
    store, doer, checker, _, _, proposal = circuit(tmp_path)
    doer.publish = _crash
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    attempt = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.receipt.detail == words.VERIFY_RAISED
    assert checker.independent_calls == [] and doer.release_calls == 1


def test_the_checked_participant_and_model_are_both_the_frozen_bindings(tmp_path):
    from conductor.command.graph_template import materialize, RunBinding
    from conductor.command.run_store import snapshot_digest
    from tests.test_command_plan_verifier import a_template
    from tests.test_command_run_store import CONFIG, a_run
    config = json.loads(json.dumps(CONFIG))
    config["instances"][1]["model"] = "checker-model-pinned"
    store = RunStore(tmp_path)
    store.create_run(a_run(mode="confirm", config_digest=snapshot_digest(config)), config)
    store.append(materialize(a_template(verifier_role="role-checker"),
        RunBinding(assignments={"role-implementer": DOER, "role-checker": CHECKER}),
        config, graph_id="g", run_id=RUN_ID, created_at=NOW))
    store.append(DecisionReceipt(
        receipt_id="gate-pinned-model", run_id=RUN_ID, gate_id="gate-confirm-do",
        action="approve", actor="owner", decided_at=NOW, reason="Start the test.",
        scope_refs=("src",), config_digest=snapshot_digest(config)))
    doer, checker = _Signing(store, adapter_id="claude-code"), _Signing(store, adapter_id="codex")
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(store, node_id=NODE, config_digest=snapshot_digest(config))
    attempt = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert attempt.state is AttemptState.SUCCEEDED
    binding = checker.independent_calls[0][0]
    assert (binding.instance_id, binding.adapter_id, binding.model) == (
        CHECKER, "codex", "checker-model-pinned")
    assert "model" not in attempt.verification_evidence[0].as_dict()
