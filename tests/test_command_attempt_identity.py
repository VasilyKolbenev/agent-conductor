"""One attempt id names one action, on both roads that can write one.

`validate_attempt_event` has refused an event whose `attempt_id` "already
belongs to another action" since attempt events existed. The REQUESTS those
events describe were held to no such rule, and the gap was not theoretical in
either direction:

- the attempt bound counted DISTINCT `attempt_id`s, so three confirmations
  carrying one id measured as one attempt and a ceiling of two admitted all
  three -- the bound was bypassable by repeating a string the caller chose;
- the journal that produced was internally contradictory in a way nothing in it
  explained. The first of those actions to record an attempt event claimed the
  id; every other action holding it could then never record one, so authorized
  work sat unable to proceed with no durable fact saying why.

The relation is held twice on purpose, and the two askings are not redundant.
`authorize_holds._hold_attempt_identity` runs before `admit`, so the run never
reaches the state at all; `attempt_replay.validate_action_request` is a causal
rule of the store, so it is also true of bytes this process did not write and of
a journal replayed from disk. A module that tested only the first would pass
while a hand-appended record walked straight past it.

The bound itself is now a count of ROWS. Its old justification -- that a
byte-identical retry must not spend it twice -- was false on both legs, and the
last two tests here are what say so rather than a comment claiming it.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.run_store import RunStore, StoreError, snapshot_digest
from conductor.command.runtime import AuthorizationError
from tests.alpha3_graph_artifacts import dalio_definition
from tests.test_command_graph_binding import (
    CONFIG, RUN_ID, a_budget, a_confirmation, a_proposal, a_run, a_runtime)


def a_bounded_run(tmp_path, **bounds):
    """A real run on the shipped Dalio plan, with the Do node given ceilings."""
    plan = dalio_definition(run_id=RUN_ID)
    bounded = plan.stage_node("do").node_id
    nodes = tuple(
        GraphNode.from_dict({**row.as_dict(), **bounds})
        if row.node_id == bounded else row
        for row in plan.nodes)
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    store.append(GraphDefinition(
        graph_id=plan.graph_id, run_id=plan.run_id,
        created_at=plan.created_at, nodes=nodes, edges=plan.edges))
    return store


def standing_proposals(store, count, *, attempt_id):
    """`count` distinct proposals on the bounded node, sharing one attempt id."""
    proposals = []
    for index in range(1, count + 1):
        proposal = a_proposal(proposal_id=f"proposal-{index}", attempt_id=attempt_id)
        store.append(proposal)
        proposals.append(proposal)
    return proposals


def authorize(runtime, proposal, index, budget):
    return runtime.authorize(
        a_confirmation(proposal, confirmation_id=f"confirmation-{index:03d}"),
        budget=budget)


def a_request_restating(held, proposal):
    """The request `authorize` WOULD have minted for `proposal`, hand-written.

    Every proposal-derived fact is the second proposal's own, because the store
    holds a request to its proposal (`_request_repeats_its_proposal`) one
    identity above the relation under test. A forgery that failed that check
    would be refused for the wrong reason, and this module would be measuring a
    rule it is not about.
    """
    return type(held).from_dict({
        **held.as_dict(),
        "action_id": "action-second",
        "idempotency_key": f"dispatch-{proposal.proposal_id}",
        "preview_digest": proposal.preview_digest})


# -- the runtime road: refused before anything is admitted --------------------


def test_a_second_action_may_not_take_an_attempt_id_the_first_one_holds(tmp_path):
    """The relation on its own, with no bound anywhere near it.

    The node names no `attempt_bound` at all, so nothing about ceilings can be
    what refuses this. If the bound were doing the work, this test would pass
    while the defect stood.
    """
    store = a_bounded_run(tmp_path)
    first, second = standing_proposals(store, 2, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    authorize(runtime, first, 1, budget)

    with pytest.raises(AuthorizationError, match="already belongs to another action"):
        authorize(runtime, second, 2, budget)


def test_the_refusal_names_the_action_that_already_holds_the_id(tmp_path):
    """An operator told only "refused" cannot find the action to look at."""
    store = a_bounded_run(tmp_path)
    first, second = standing_proposals(store, 2, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    held = authorize(runtime, first, 1, budget).request.action_id

    with pytest.raises(AuthorizationError, match=held):
        authorize(runtime, second, 2, budget)


def test_the_refusal_lands_before_admit_and_writes_nothing(tmp_path):
    """Pre-durable is the whole reason the hold sits where it sits.

    `admit` is the last gate before the append. A refusal that reached it has
    already been counted by the caller's admission control; a refusal that wrote
    a record has already spent the identity it was refusing.
    """
    store = a_bounded_run(tmp_path)
    first, second = standing_proposals(store, 2, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    authorize(runtime, first, 1, budget)
    before = [row.kind for row in store.read(RUN_ID).records]
    admitted = []

    with pytest.raises(AuthorizationError):
        runtime.authorize(
            a_confirmation(second, confirmation_id="confirmation-002"),
            budget=budget, admit=lambda: admitted.append(True))

    assert admitted == []
    assert [row.kind for row in store.read(RUN_ID).records] == before


def test_an_attempt_bound_of_two_is_not_bought_off_by_repeating_one_id(tmp_path):
    """The reported defect, end to end: `attempt_bound=2` admitted three.

    Measured before the fix as `AUTHORIZED [1, 2, 3]` with one attempt id and
    three action ids in the journal.
    """
    store = a_bounded_run(tmp_path, attempt_bound=2)
    proposals = standing_proposals(store, 3, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    authorize(runtime, proposals[0], 1, budget)

    for index, proposal in enumerate(proposals[1:], start=2):
        with pytest.raises(AuthorizationError):
            authorize(runtime, proposal, index, budget)

    requests = [row.value for row in store.read(RUN_ID).records
                if row.kind == "action_request"]
    assert len(requests) == 1


def test_the_contradiction_the_gap_produced_can_no_longer_be_reached(tmp_path):
    """Two actions on one attempt id, and only one of them may ever be observed.

    This is the durable end state the old journal could hold: the attempt event
    road refuses the second action's event because the first claimed the id, so
    authorized work could not proceed and nothing recorded why. The rule that
    refused the event is quoted here from the module that owns it, so the two
    halves of "one attempt id, one action" are visibly the same sentence.
    """
    from conductor.command.attempt_replay import AttemptRelationError, validate_action_request

    store = a_bounded_run(tmp_path)
    first, second = standing_proposals(store, 2, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    held = authorize(runtime, first, 1, budget).request
    forged = a_request_restating(held, second)

    with pytest.raises(AttemptRelationError, match="already belongs to another action"):
        validate_action_request([held], forged)


# -- the store road: true of bytes this process did not write -----------------


def test_the_store_refuses_a_second_request_appended_under_a_held_attempt_id(
        tmp_path):
    """A record appended directly reaches the store without passing the runtime."""
    store = a_bounded_run(tmp_path)
    first, second = standing_proposals(store, 2, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    held = authorize(runtime, first, 1, budget).request
    forged = a_request_restating(held, second)

    with pytest.raises(StoreError, match="already belongs to another action"):
        store.append(forged)


def test_a_journal_written_outside_this_process_is_refused_on_replay(tmp_path):
    """The raw-bytes road, which no in-process gate can stand in front of.

    The second request is written straight into `records.jsonl`, so nothing in
    the runtime or in `append` is between it and the reader. Replay is the only
    thing that can still refuse it, which is why the rule is a causal relation
    of the store rather than a check inside `append`.
    """
    from conductor.command.run_store import CorruptRun

    store = a_bounded_run(tmp_path)
    first, second = standing_proposals(store, 2, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    held = authorize(runtime, first, 1, budget).request
    forged = a_request_restating(held, second).as_dict()
    journal = store.run_path(RUN_ID) / "records.jsonl"
    with journal.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"record": forged, "record_type": "action_request"},
                                separators=(",", ":"), sort_keys=True) + "\n")

    with pytest.raises(CorruptRun, match="already belongs to another action"):
        store.read(RUN_ID)


# -- the over-correction controls --------------------------------------------


def test_an_exact_retry_is_still_answered_by_its_own_standing_request(tmp_path):
    """The road the old set claimed to protect, and the reason it protected nothing.

    A client whose reply was lost re-confirms the same proposal. It carries the
    attempt id its own standing request already holds, so a relation asked above
    the retry answer would refuse the very case it was written for. It is asked
    below, and the retry is answered exactly as before: the standing request,
    `record_created=False`, and not one new durable byte.
    """
    store = a_bounded_run(tmp_path, attempt_bound=1)
    first, = standing_proposals(store, 1, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    original = authorize(runtime, first, 1, budget)
    before = (store.run_path(RUN_ID) / "records.jsonl").read_bytes()

    again = runtime.authorize(a_confirmation(first), budget=budget)

    assert again.record_created is False
    assert again.request == original.request
    assert (store.run_path(RUN_ID) / "records.jsonl").read_bytes() == before


def test_distinct_attempt_ids_still_authorize_up_to_the_bound(tmp_path):
    """The bound counts rows, and it counts them exactly.

    Two distinct attempt ids under a bound of two both authorize; the third is
    refused BY THE BOUND, naming it, and not by the identity relation.
    """
    store = a_bounded_run(tmp_path, attempt_bound=2)
    proposals = [a_proposal(proposal_id=f"proposal-{index}",
                            attempt_id=f"attempt-{index:03d}")
                 for index in (1, 2, 3)]
    for proposal in proposals:
        store.append(proposal)
    runtime, budget = a_runtime(store), a_budget()

    for index, proposal in enumerate(proposals[:2], start=1):
        authorize(runtime, proposal, index, budget)

    with pytest.raises(AuthorizationError, match="allows 2 attempt"):
        authorize(runtime, proposals[2], 3, budget)


def test_an_unbounded_node_still_authorizes_distinct_attempts_without_limit(
        tmp_path):
    """A plan that named no ceiling must still name none."""
    store = a_bounded_run(tmp_path)
    proposals = [a_proposal(proposal_id=f"proposal-{index}",
                            attempt_id=f"attempt-{index:03d}")
                 for index in (1, 2, 3)]
    for proposal in proposals:
        store.append(proposal)
    runtime, budget = a_runtime(store), a_budget()

    for index, proposal in enumerate(proposals, start=1):
        authorize(runtime, proposal, index, budget)

    assert sum(1 for row in store.read(RUN_ID).records
               if row.kind == "action_request") == 3


# -- the bound must be right on its own, not right because of its neighbour ---


def test_the_bound_counts_rows_and_does_not_lean_on_the_identity_rule(tmp_path):
    """Two requests, one attempt id, a ceiling of two: spent, not one.

    With the identity relation in place `authorize` can no longer produce this
    journal, which is exactly why the bound has to be asked about it directly.
    Counting distinct ids gives 1 here and admits a third attempt; counting rows
    gives 2 and refuses it. A bound that is correct only while a DIFFERENT rule
    holds is a derived value checking itself, and the first review of this field
    was lost to precisely that shape.
    """
    from conductor.command.authorize_holds import _hold_plan_bounds
    from conductor.command.run_store import RecoveredRun, StoredRecord

    store = a_bounded_run(tmp_path, attempt_bound=2)
    first, second, third = standing_proposals(store, 3, attempt_id="attempt-shared")
    runtime, budget = a_runtime(store), a_budget()
    held = authorize(runtime, first, 1, budget).request
    replayed = store.read(RUN_ID)
    twice = RecoveredRun(
        envelope=replayed.envelope, config=replayed.config,
        records=replayed.records + (
            StoredRecord(kind="action_request",
                         value=a_request_restating(held, second)),),
        warnings=())

    with pytest.raises(AuthorizationError, match="allows 2 attempt"):
        _hold_plan_bounds(third, twice)
