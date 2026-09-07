"""A named checker cannot be erased by erasing the result's evidence list.

All refusal cases begin as honest succeeded runs. They remove the verification
and then ask both durable doors about the resulting claim: append and raw replay.
Ordinary historical rows and non-successful named attempts retain their meaning.
"""
from dataclasses import replace
import json

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.contracts import canonical_json
from conductor.command.run_store import CorruptRun, RunStore, StoreError
from conductor.command.runtime import AttemptState, ControlRuntime
from tests.test_command_plan_verifier import (
    RUN_ID, _Signing, _a_verified_run, a_bound_store,
)
from tests.test_command_runtime_authorize import (
    a_budget, a_confirmation, a_proposal, fixed_clock, fixed_ids,
)


def _honest_run(path, named):
    if named:
        return _a_verified_run(path)
    store = a_bound_store(path, verifier=None)
    doer = _Signing(store, adapter_id="claude-code")
    runtime = ControlRuntime(store, AdapterRegistry([doer]),
                             clock=fixed_clock(), ids=fixed_ids())
    proposal = a_proposal(store, node_id="do")
    result = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert result.state is AttemptState.SUCCEEDED
    return store


def _without_verification(path, *, named, eventless, road, outcome="succeeded"):
    store = _honest_run(path, named)
    recovered = store.read(RUN_ID)
    result = next(row.value for row in recovered.records if row.kind == "action_result")
    evidence = [row.value for row in recovered.records if row.kind == "evidence"]
    assert result.outcome == "succeeded" and len(result.evidence_refs) == len(evidence) == 1
    assert (evidence[0].verifier_instance_id is not None) is named
    changed = replace(result, evidence_refs=(), outcome=outcome,
                      exit_code=0 if outcome == "succeeded" else None)
    journal = store.run_path(RUN_ID) / "records.jsonl"
    rows = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    kept = []
    for row in rows:
        kind = row["record_type"]
        if kind in ("evidence", "run_terminal") or (eventless and kind == "attempt_event"):
            continue
        if kind == "action_result":
            if road == "append":
                continue
            row["record"] = changed.as_dict()
        kept.append(row)
    journal.write_text("".join(canonical_json(row) + "\n" for row in kept),
                       encoding="utf-8", newline="\n")
    return RunStore(path), changed


def _read_or_append(store, result, road):
    if road == "append":
        # Establish a readable pre-terminal state. A refusal must be about the
        # appended success, not a stale terminal summary left by the fixture.
        before = store.read(RUN_ID)
        assert not any(row.kind == "action_result" for row in before.records)
        store.append(result)
    return store.read(RUN_ID)


@pytest.mark.parametrize("road", ["append", "raw"])
@pytest.mark.parametrize("eventless", [False, True])
def test_named_checker_success_requires_evidence_on_both_durable_roads(tmp_path, road, eventless):
    store, result = _without_verification(tmp_path, named=True, eventless=eventless, road=road)
    with pytest.raises((StoreError, CorruptRun), match="evidence|lease"):
        _read_or_append(store, result, road)


@pytest.mark.parametrize("road", ["append", "raw"])
@pytest.mark.parametrize("eventless", [False, True])
def test_plain_historical_success_keeps_its_old_evidence_semantics(tmp_path, road, eventless):
    store, result = _without_verification(tmp_path, named=False, eventless=eventless, road=road)
    recovered = _read_or_append(store, result, road)
    found = [row.value for row in recovered.records if row.kind == "action_result"]
    assert found == [result] and found[0].outcome == "succeeded"


@pytest.mark.parametrize("road", ["append", "raw"])
def test_eventless_named_unknown_is_not_promoted_or_made_unreadable(tmp_path, road):
    store, result = _without_verification(tmp_path, named=True, eventless=True,
                                         road=road, outcome="unknown")
    recovered = _read_or_append(store, result, road)
    found = [row.value for row in recovered.records if row.kind == "action_result"]
    assert found == [result] and found[0].outcome == "unknown"
