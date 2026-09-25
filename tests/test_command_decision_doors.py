"""A decision stands only on a gate the run's plan has reached.

The plan is a permission as well as a description. `authorize` has held that
rule for attempts since the eligibility slice; nothing held it for DECISIONS,
and a gate settles from its own receipts alone -- so one POST to
``/decisions`` on a plan-less gate settled it, the step behind it became
runnable at once, and every predecessor was skipped. On the shipped
``dalio-v3`` starter that meant `identify`, `diagnose` and `design` were never
carried out and the work went straight to `do`.

Two doors close it, and they are two orderings of one defect. THIS module holds
the first: the decision arrives after the plan, and `_hold_gate_is_reached`
admits it only for a gate the plan has ARRIVED at with nothing standing on it,
or as a receipt superseding what does stand -- which is how a reopened loop is
answered a second time and how a person takes back an answer. The second
ordering, where the plan arrives after the decision, is refused on the
plan-writing roads and its witnesses are in
``tests/test_command_plan_pre_answer_door.py``.

The scheduler is deliberately untouched, and `tests/test_demo_scenario.py`
is the calibration that says so: a receipt appended straight into a journal
still settles its gate on replay, which is what keeps every fixture, every
older journal and the demo readable. These are LIVE doors only.

Every refusal witness reads ``records.jsonl`` as BYTES either side of the
refused call, because "the record is absent" would also be true of a journal
that had been rewritten.
"""
from __future__ import annotations
from tests.human_situation_samples import READ_AT

import pytest

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    DecisionReceipt,
)
from conductor.command.graph_causality import (
    decision_is_reached,
    gate_answer,
    standing_receipt,
)
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.graph_projection import graph_payload
from conductor.command.graph_schedule import schedule
from conductor.command.graph_template import RunBinding, load_template, materialize
from tests.test_command_http_api import (
    NOW,
    RUN_ID,
    api,
    confirm_body,
    decision_body,
    post,
    proposal_body,
)
from tests.test_command_run_terminal_doors import journal_bytes, kinds
from tests.test_command_schema_doubles import DeepDispatchAdapter

DECISIONS = f"/command/runs/{RUN_ID}/decisions"
GRAPH_ID = "graph-dalio-v3"
#: The four steps `dalio-v3` puts in front of its first gate. Answering that
#: gate is the defect's whole subject, and settling these is what earns it.
BODY = ("goal", "identify", "diagnose", "design")


def a_planned_run(tmp_path):
    """One real run following the shipped `dalio-v3` starter, materialized.

    Through `materialize` and the shipped template file rather than a plan
    written here: the defect was found on the product's own default cycle, and
    a hand-drawn stand-in could differ from it in exactly the edge that matters.
    """
    subject, store, events = api(tmp_path, adapters=[DeepDispatchAdapter()])
    template = load_template("dalio-v3")
    binding = RunBinding.from_dict(
        {"assignments": {role: "claude-dev" for role in template.roles}})
    definition = materialize(
        template, binding, store.read(RUN_ID).config, graph_id=GRAPH_ID,
        run_id=RUN_ID, created_at=NOW)
    store.append(definition)
    return subject, store, events, definition


def settle(store, definition, node_id, *, index):
    """Carry one acting step out, by appending the records a real one writes.

    Directly rather than through the routes, for the reason the eligibility
    witnesses next door append their own: what is under test here is the
    DECISION door, and driving four steps through propose/authorize/execute to
    reach it would make every one of these tests a test of those roads too.

    The outcome is `failed` on purpose. A step settles on any terminal result
    that is not `unknown`, the roads out of these four carry no condition, so
    a failure opens them exactly as a success would -- and a `succeeded`
    receipt would drag in the verification evidence a success must name, which
    is a different rule with its own witnesses.
    """
    node = next(row for row in definition.nodes if row.node_id == node_id)
    digest = store.read(RUN_ID).envelope.config_digest
    proposal = ActionProposal(
        proposal_id=f"proposal-{index}", run_id=RUN_ID,
        attempt_id=f"attempt-{index:03d}", instance_id=node.instance_id,
        capability=node.capability, arguments=node.payload(), scope=("src",),
        proposed_by="claude-dev", proposed_at=NOW, timeout_seconds=900,
        rationale=f"Carry out {node_id}.", config_digest=digest,
        node_id=node_id)
    store.append(proposal)
    request = ActionRequest(
        action_id=f"action-{index}", run_id=RUN_ID,
        attempt_id=proposal.attempt_id, instance_id=proposal.instance_id,
        capability=proposal.capability, arguments=dict(proposal.arguments),
        scope=tuple(proposal.scope), requested_by="release-owner",
        requested_at=NOW, idempotency_key=f"dispatch-{proposal.proposal_id}",
        timeout_seconds=proposal.timeout_seconds,
        preview_digest=proposal.preview_digest, mode="confirm",
        node_id=proposal.node_id)
    store.append(request)
    store.append(ActionResultReceipt(
        receipt_id=f"result-{index}", action_id=request.action_id,
        run_id=RUN_ID, attempt_id=request.attempt_id,
        instance_id=request.instance_id, outcome="failed", exit_code=1,
        observed_at=NOW, evidence_refs=()))


def settle_the_body(store, definition, *, start=1, skip=()):
    """Every step `dalio-v3` puts in front of its first gate, carried out.

    `skip` names the steps a LAP does not reopen: the loop goes back to
    `identify`, so `goal` is carried out once and never again.
    """
    for offset, node_id in enumerate(BODY):
        if node_id not in skip:
            settle(store, definition, node_id, index=start + offset)


def a_receipt(store, receipt_id, *, gate_id="release", action="approve"):
    """One receipt written straight into the journal, around every door.

    The shape a forged or hand-written journal has, and the only way to reach
    the states the live door refuses to create -- two answers standing on one
    gate is exactly such a state.
    """
    return DecisionReceipt(
        receipt_id=receipt_id, run_id=RUN_ID, gate_id=gate_id, action=action,
        actor="operator", decided_at=NOW, reason="Written around the door.",
        scope_refs=("src",),
        config_digest=store.read(RUN_ID).envelope.config_digest)


def standing(store, definition, node_id):
    """Where one step stands, computed the way every reader computes it."""
    return row_of(store, definition, node_id).state


def row_of(store, definition, node_id):
    """One step's whole schedule row: its state and each road into it."""
    records = tuple(row.value for row in store.read(RUN_ID).records)
    return next(row for row in schedule(definition, records).nodes
                if row.node_id == node_id)


def laps_of(store, definition, node_id):
    """How many laps this step has answered, off the schedule's own row."""
    return row_of(store, definition, node_id).settled_laps


def run_word(store, definition):
    records = tuple(row.value for row in store.read(RUN_ID).records)
    return schedule(definition, records).run_state


def refusal_of(response):
    return response.payload["error"]


# -- the gate a run has not arrived at ----------------------------------------


def test_a_decision_on_a_gate_the_plan_has_not_reached_is_refused(tmp_path):
    """The reported defect, at the door it came through.

    Nothing durable moves and no frame is published: the refusal is taken
    inside the transaction and strictly before the clock, so a caller who is
    told no has left no trace at all.
    """
    subject, store, events, definition = a_planned_run(tmp_path)
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-early"))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert refusal_of(refused)["detail"] == {}
    assert journal_bytes(store) == before
    assert events == []
    assert standing(store, definition, "confirm-gate") == "blocked"
    assert standing(store, definition, "do") == "blocked"


def test_the_same_decision_is_accepted_once_every_predecessor_settles(tmp_path):
    """The positive control: the rule is about the PLAN's state, not the gate.

    The identical body goes through once the four steps in front of the gate
    have been carried out -- so a build that refused every decision on a
    planned run would fail here.
    """
    subject, store, events, definition = a_planned_run(tmp_path)
    settle_the_body(store, definition)
    assert standing(store, definition, "confirm-gate") == "runnable"

    answered = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-early"))

    assert answered.status == 201
    assert answered.payload["gate_id"] == "gate-confirm-do"
    assert kinds(store)[-1] == "decision"
    assert events == [RUN_ID]
    assert standing(store, definition, "do") == "runnable"


def test_a_step_behind_an_unreached_gate_is_never_offered_by_the_plan(tmp_path):
    """The consequence the defect actually had, held as its own claim.

    The refusal above is only worth having because of this: a gate settled
    early made `do` runnable, and the proposal and the Confirm behind it were
    then perfectly legal. With the door in place the plan never offers the
    step at all, so the two rules agree about one run.
    """
    subject, store, _events, definition = a_planned_run(tmp_path)

    post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-early"))

    assert standing(store, definition, "do") == "blocked"
    assert "decision" not in kinds(store)


# -- correcting an answer: the supersede arm ----------------------------------


def a_reopened_result_gate(tmp_path):
    """One run answered all the way to its result gate, then sent back around.

    `request_changes` on the result gate opens the loop's road, which reopens
    the body -- so the gate now owes a SECOND lap and is `blocked` behind a
    `do` that has delivered one. That is the state a person is in when they
    want to take an answer back, and the only way to answer it again is to
    supersede what stands.
    """
    subject, store, events, definition = a_planned_run(tmp_path)
    settle_the_body(store, definition)
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm")).status == 201
    settle(store, definition, "do", index=5)
    assert standing(store, definition, "result-gate") == "runnable"
    first = post(subject, DECISIONS, decision_body(
        gate_id="gate-result", receipt_id="decision-result-1",
        action="request_changes"))
    assert first.status == 201
    assert standing(store, definition, "result-gate") == "blocked"
    return subject, store, events, definition


def test_a_supersede_of_the_standing_receipt_is_accepted_while_blocked(tmp_path):
    """Walkthrough (c): the answer a person takes back on a reopened lap.

    The gate is NOT runnable -- the loop has just reopened everything behind it
    -- and the receipt is still admitted, because it names the receipt already
    standing. It replaces that answer rather than adding a second, which is
    exactly what `gate_decision` can read and what the schedule counts as one
    lap.
    """
    subject, store, _events, definition = a_reopened_result_gate(tmp_path)

    corrected = post(subject, DECISIONS, decision_body(
        gate_id="gate-result", receipt_id="decision-result-2",
        action="approve", supersedes="decision-result-1"))

    assert corrected.status == 201
    assert corrected.payload["supersedes"] == "decision-result-1"
    assert run_word(store, definition) == "complete"


def test_a_supersede_naming_a_receipt_that_is_not_standing_is_refused(tmp_path):
    """The other half of the same arm, and the one that keeps it narrow.

    Once a second receipt has superseded the first, the first is no longer
    what stands -- so a THIRD naming it again is not a correction, it is a
    second standing answer on one gate. Two of those are the journal
    `gate_decision` refuses to read, and the gate would then be `unknown`.
    """
    subject, store, _events, definition = a_reopened_result_gate(tmp_path)
    again = post(subject, DECISIONS, decision_body(
        gate_id="gate-result", receipt_id="decision-result-2",
        action="request_changes", supersedes="decision-result-1"))
    assert again.status == 201
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-result", receipt_id="decision-result-3",
        action="approve", supersedes="decision-result-1"))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before


def test_a_supersede_cannot_carry_an_approval_into_a_lap_the_plan_has_not_reached(
        tmp_path):
    """R02 of the Codex review of `8dec0e4`, at the door it came through.

    The result gate sent the work back around and `identify` has been carried
    out again, so a SECOND lap has begun -- and `confirm-gate`, answered in the
    first, stands behind `diagnose` and `design` with its lap-one approval
    still the standing receipt. A supersede naming that receipt is neither a
    correction of this lap's answer (there is none) nor the reopened lap's
    answer (the plan has not reached the gate in this lap). Before the rule it
    landed 201, the gate read two laps settled, and `do` was proposed and
    AUTHORIZED with two thinking steps never carried out.

    The propose door holds no schedule check and answers 201 either way; the
    authorize door is where the plan is a permission, so both are driven.
    """
    subject, store, events, definition = a_reopened_result_gate(tmp_path)
    settle(store, definition, "identify", index=6)
    assert standing(store, definition, "diagnose") == "runnable"
    assert standing(store, definition, "confirm-gate") == "blocked"
    # What the run READ serves about this gate, before the door is asked: the
    # word the screen gates its form on must be the door's own answer.
    assert served_word(store, "confirm-gate") == "none"
    before = journal_bytes(store)
    events.clear()

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="early-lap-2",
        supersedes="decision-confirm"))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before
    assert events == []
    assert laps_of(store, definition, "confirm-gate") == 1
    assert standing(store, definition, "do") == "blocked"

    node = next(row for row in definition.nodes if row.node_id == "do")
    proposed = post(subject, f"/command/runs/{RUN_ID}/proposals", {
        **proposal_body(), "node_id": "do", "attempt_id": "attempt-do-2",
        "instance_id": node.instance_id, "capability": node.capability,
        "arguments": node.payload()})
    assert proposed.status == 201, proposed.payload
    authorized = post(subject, f"/command/runs/{RUN_ID}/actions",
                      confirm_body(proposed.payload))
    assert authorized.status == ERROR_STATUS["authorization_refused"] == 409
    assert refusal_of(authorized)["code"] == "authorization_refused"


def test_a_correction_of_this_laps_answer_is_admitted_on_a_settled_gate(tmp_path):
    """The over-correction control: taking back an approval before the loop moves.

    Every road into `confirm-gate` is open, this lap's answer stands, and no
    later lap has begun -- so the gate is SETTLED, not arrived at, and a rule
    that admitted a supersede only on an arrived gate would refuse the very
    correction §5.4(c) protects. It lands, the lap count does not move, and the
    road the approval had opened closes behind it.
    """
    subject, store, _events, definition = a_planned_run(tmp_path)
    settle_the_body(store, definition)
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm")).status == 201
    assert standing(store, definition, "confirm-gate") == "settled"
    assert standing(store, definition, "do") == "runnable"
    assert served_word(store, "confirm-gate") == "supersede"

    corrected = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm-2",
        action="reject", supersedes="decision-confirm"))

    assert corrected.status == 201
    assert laps_of(store, definition, "confirm-gate") == 1
    assert standing(store, definition, "do") == "unreachable"


def served_word(store, node_id: str) -> str | None:
    """The `answerable` word the run read serves for one gate, off the store.

    `graph_payload` is what the run route answers with; asking it here beside
    the POST is what ties the served word to the live door with two independent
    instruments -- the projection and the HTTP boundary -- rather than to a copy
    of the door's own predicate.
    """
    rows = graph_payload(store.read(RUN_ID), computed_at=READ_AT)["schedule"]["nodes"]
    return next(row["answerable"] for row in rows if row["node_id"] == node_id)


def a_reopened_confirm_gate(tmp_path):
    """One run whose FIRST gate is askable again, with an answer still standing.

    The state a loop puts a person in, and the one the door was blind to: the
    body has been carried out a second time, so `confirm-gate` is arrived at
    again -- and the answer from the first lap is still the standing one. A
    predicate that asked arrival before it asked what stands admitted a second
    receipt superseding nothing here, and the gate read `unknown` from then on.
    """
    subject, store, events, definition = a_planned_run(tmp_path)
    settle_the_body(store, definition)
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm")).status == 201
    settle(store, definition, "do", index=5)
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-result", receipt_id="decision-result-1",
        action="request_changes")).status == 201
    settle_the_body(store, definition, start=6, skip=("goal",))
    assert standing(store, definition, "confirm-gate") == "runnable"
    return subject, store, events, definition


def test_a_reopened_gate_refuses_an_answer_that_supersedes_nothing(tmp_path):
    """THE defect the review found, and the reason the order of the arms is the
    rule rather than a detail.

    The gate is arrived at, so the old predicate said yes and stopped asking.
    The receipt that landed superseded nothing, two receipts stood on one gate,
    and `gate_decision` could no longer say which was current -- so the gate
    read `unknown` for the rest of the run, nothing settled it, and no later
    receipt could repair it either: a correction supersedes ONE receipt and
    there were two.
    """
    subject, store, events, definition = a_reopened_confirm_gate(tmp_path)
    before = journal_bytes(store)
    events.clear()

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm-2"))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before
    assert events == []


def test_a_reopened_gate_is_answered_again_by_superseding_what_stands(tmp_path):
    """The positive control, and the lap it buys.

    The same gate, the same moment, the same body but for one field -- so a
    build that refused every answer on a reopened gate would fail here. The
    second receipt falls in the second lap, which is what makes it an ANSWER
    rather than a correction: `settled_laps` moves.
    """
    subject, store, _events, definition = a_reopened_confirm_gate(tmp_path)

    answered = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm-2",
        supersedes="decision-confirm"))

    assert answered.status == 201
    assert laps_of(store, definition, "confirm-gate") == 2
    assert standing(store, definition, "confirm-gate") == "settled"


def test_a_reopened_gate_refuses_a_receipt_that_has_itself_been_superseded(
        tmp_path):
    """Only what STANDS may be replaced, on an arrived gate as on a blocked one.

    Once the second receipt has replaced the first, the first is no longer the
    current answer -- so a third naming it is not a correction, it is a second
    standing answer arriving by another road.
    """
    subject, store, _events, _definition = a_reopened_confirm_gate(tmp_path)
    assert post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm-2",
        supersedes="decision-confirm")).status == 201
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm-3",
        supersedes="decision-confirm"))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before


@pytest.mark.parametrize("named", ["decision-result-1", "never-written"])
def test_a_supersede_the_run_cannot_resolve_is_the_callers_fault(
        tmp_path, named):
    """A `supersedes` naming another gate's receipt, or none at all.

    Both used to reach the STORE, which reports a `supersedes` it cannot
    resolve as a `store_error` -- a 500, the word for a server fault, for a
    caller who named the wrong receipt. The same body one road earlier, on a
    gate the run had not reached, already answered `gate_unreached`. One
    mistake had two words depending on where the plan happened to be.
    """
    subject, store, _events, _definition = a_reopened_confirm_gate(tmp_path)
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm-2",
        supersedes=named))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before


@pytest.mark.parametrize("named", ["decision-nothing", "decision-elsewhere"])
def test_a_first_answer_may_not_claim_to_replace_anything(tmp_path, named):
    """The gate is arrived at and nobody has answered it, so there is nothing
    to supersede -- and a receipt that says it replaces something is a claim
    about a journal this run does not have.

    A receipt naming ITSELF is not driven here: the contract refuses that one
    door earlier, as `contract_invalid`, and a witness written over it would be
    asserting the parser's rule under this door's name.
    """
    subject, store, _events, definition = a_planned_run(tmp_path)
    settle_the_body(store, definition)
    assert standing(store, definition, "confirm-gate") == "runnable"
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-confirm-do", receipt_id="decision-confirm",
        supersedes=named))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before


def test_a_settled_gate_refuses_a_second_answer_that_replaces_nothing(tmp_path):
    """A gate every road into which is open, already answered, asked again.

    Arrival says nothing about this one: the roads are open and stay open. What
    refuses it is that an answer already stands and this receipt replaces none.
    """
    subject, store, _events, plan = a_root_gate_run(tmp_path)
    assert post(subject, DECISIONS, decision_body()).status == 201
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body(receipt_id="decision-002"))

    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before


def test_a_gate_whose_answers_contradict_accepts_nothing_further(tmp_path):
    """An `unknown` gate is not a state a further receipt may be written into.

    Two receipts nothing supersedes are a journal the projection cannot read.
    There is no current answer to replace, so a correction cannot name one --
    and a receipt superseding nothing would be a third. The door says so rather
    than letting the store decide it one record later.

    The BARE answer is the one that needs this arm, and it is why the arm is
    asked before arrival. An `unknown` gate is not settled, so the schedule
    calls it runnable and every road into this one is open: arrival says yes.
    Only asking whether the journal can be read at all says no.
    """
    subject, store, _events, plan = a_root_gate_run(tmp_path)
    for index in (1, 2):
        store.append(a_receipt(store, f"decision-standing-{index}"))
    values = tuple(row.value for row in store.read(RUN_ID).records)
    assert gate_answer(values, RUN_ID, "release") is None
    assert row_of(store, plan, "root-gate").state == "runnable"
    before = journal_bytes(store)

    for body in (decision_body(receipt_id="decision-003"),
                 decision_body(receipt_id="decision-004",
                               supersedes="decision-standing-1")):
        refused = post(subject, DECISIONS, body)

        assert refused.status == ERROR_STATUS["gate_unreached"] == 409, body
        assert refusal_of(refused)["code"] == "gate_unreached"
        assert journal_bytes(store) == before


# -- a road the plan CLOSED, which is a different absence ---------------------


def a_closed_road_run(tmp_path, *, through_a_dead_step=False):
    """A plan whose gate stands behind a road the run's own outcome closed.

    `check` fails, and the road out of it opens only `on_succeeded` -- so the
    gate is `unreachable` rather than merely waiting, and it names the step
    that took the other road in `closed_by`. With `through_a_dead_step` the
    gate sits one step further on, behind a node that is itself unreachable:
    the road into the gate is then PENDING and `closed_by` is empty, which is
    the other shape and the one a rule written only about closed roads misses.
    """
    subject, store, events = api(tmp_path, adapters=[DeepDispatchAdapter()])
    template = load_template("dalio-v3")
    binding = RunBinding.from_dict(
        {"assignments": {role: "claude-dev" for role in template.roles}})
    check = next(row for row in materialize(
        template, binding, store.read(RUN_ID).config, graph_id=GRAPH_ID,
        run_id=RUN_ID, created_at=NOW).nodes if row.node_id == "goal")
    gate = GraphNode(node_id="road-gate", kind="gate", title="Behind the road",
                     gate_id="release")
    beyond = GraphNode(node_id="beyond", kind="task", title="Beyond")
    nodes = (check, gate) if not through_a_dead_step else (check, beyond, gate)
    edges = (
        (GraphEdge(from_node="goal", to_node="road-gate",
                   condition="on_succeeded"),)
        if not through_a_dead_step else
        (GraphEdge(from_node="goal", to_node="beyond",
                   condition="on_succeeded"),
         GraphEdge(from_node="beyond", to_node="road-gate")))
    plan = GraphDefinition(graph_id="graph-closed-road", run_id=RUN_ID,
                           created_at=NOW, nodes=nodes, edges=edges)
    store.append(plan)
    settle(store, plan, "goal", index=1)
    return subject, store, events, plan


def test_a_gate_behind_a_closed_road_is_refused_and_names_that_road(tmp_path):
    """The road was not slow, it was NOT TAKEN, and the two are different.

    A rule written only about roads still pending would admit this one: nothing
    here is waiting. The schedule says `unreachable` and names the step that
    went the other way, and the door refuses on exactly that.
    """
    subject, store, _events, plan = a_closed_road_run(tmp_path)
    row = row_of(store, plan, "road-gate")
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body())

    assert (row.state, row.closed_by, row.blocked_by) == (
        "unreachable", ("goal",), ())
    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert refusal_of(refused)["code"] == "gate_unreached"
    assert journal_bytes(store) == before
    assert decision_is_reached(
        plan, tuple(row.value for row in store.read(RUN_ID).records),
        "release", None) is False


def test_a_gate_beyond_a_dead_step_is_refused_with_no_closed_road_of_its_own(
        tmp_path):
    """The other unreachable shape, and it names nothing in `closed_by`.

    What is closed is the road into the step BEFORE this gate. The road into
    the gate itself never closes -- it stays pending forever, because the step
    behind it will never settle -- so a rule that only read `closed_by` would
    let this one through.
    """
    subject, store, _events, plan = a_closed_road_run(
        tmp_path, through_a_dead_step=True)
    row = row_of(store, plan, "road-gate")

    refused = post(subject, DECISIONS, decision_body())

    assert (row.state, row.closed_by, row.blocked_by) == (
        "unreachable", (), ("beyond",))
    assert refused.status == ERROR_STATUS["gate_unreached"] == 409
    assert decision_is_reached(
        plan, tuple(row.value for row in store.read(RUN_ID).records),
        "release", None) is False


# -- the exact retry, which is answered before either hold is asked ------------


def a_root_gate_run(tmp_path):
    """A plan whose gate has no roads into it at all, and one step after it.

    A gate nothing stands in front of is `runnable` from the moment the plan
    lands, so answering it is legal at once -- which is what makes it the right
    journal for the RETRY question. What is being asked there is not whether
    the gate was reached; it is whether a repeat of a receipt that already
    stands is still answered after the answer settled the gate.
    """
    subject, store, events = api(tmp_path, adapters=[DeepDispatchAdapter()])
    template = load_template("dalio-v3")
    binding = RunBinding.from_dict(
        {"assignments": {role: "claude-dev" for role in template.roles}})
    # Materialized only to borrow one acting step, so the plan below names work
    # this run's frozen configuration really binds rather than work invented
    # here. It is never appended: a run carries one graph.
    goal = next(row for row in materialize(
        template, binding, store.read(RUN_ID).config, graph_id=GRAPH_ID,
        run_id=RUN_ID, created_at=NOW).nodes if row.node_id == "goal")
    plan = GraphDefinition(
        graph_id="graph-root-gate", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="root-gate", kind="gate", title="Root gate",
                         gate_id="release"), goal),
        edges=(GraphEdge(from_node="root-gate", to_node="goal"),))
    store.append(plan)
    return subject, store, events, plan


def test_an_exact_retry_answers_200_after_the_answer_settled_its_gate(tmp_path):
    """The ordering the decision door has always had, kept.

    `_hold_gate_is_reached` is asked AFTER the prior-receipt lookup, exactly as
    `_hold_not_terminal` is: the refusal is about a NEW record and an exact
    retry appends none. Asked before that lookup, this retry would be refused
    for a gate the very receipt being retried had settled.
    """
    subject, store, _events, plan = a_root_gate_run(tmp_path)

    first = post(subject, DECISIONS, decision_body())
    assert standing(store, plan, "root-gate") == "settled"
    retried = post(subject, DECISIONS, decision_body())

    assert first.status == 201
    assert retried.status == 200
    assert retried.payload == first.payload
    assert kinds(store).count("decision") == 1


def a_plan_less_run(tmp_path):
    """A real run following no plan at all, which is the legal starting point.

    The starting journal of the OTHER ordering of this defect -- the decision
    written before the plan -- whose door is next door in
    ``tests/test_command_plan_pre_answer_door.py``, and which reads this.
    """
    return api(tmp_path, adapters=[DeepDispatchAdapter()])


# -- the predicate itself, asked directly --------------------------------------


@pytest.mark.parametrize("gate_id", ["gate-confirm-do", "gate-result"])
def test_a_gate_no_road_has_opened_is_not_reached(tmp_path, gate_id):
    """Both gates of the shipped starter, on a run that has recorded nothing."""
    _subject, _store, _events, definition = a_planned_run(tmp_path)

    assert decision_is_reached(definition, (), gate_id, None) is False


def test_a_gate_no_node_of_the_plan_carries_is_left_to_the_store(tmp_path):
    """The plan says nothing about it, so this predicate says nothing either.

    `_decision_names_a_planned_gate` already refuses such a receipt beneath
    this door, in its own words and about the gate the caller named. A second
    refusal here would take that sentence away from it.
    """
    _subject, _store, _events, definition = a_planned_run(tmp_path)

    assert decision_is_reached(definition, (), "gate-nobody-planned", None)


def test_a_gate_the_plan_does_not_carry_is_refused_in_the_stores_own_words(
        tmp_path):
    """And the live door proves the predicate's silence is not a hole.

    The receipt is refused, by the rule that owns the sentence: a `gate_id`
    nobody planned is a Human answer to a question the plan never asked. It is
    NOT `gate_unreached` -- that word says the run has not got there yet, which
    invites a caller to wait for something that will never come.
    """
    subject, store, _events, _definition = a_planned_run(tmp_path)
    before = journal_bytes(store)

    refused = post(subject, DECISIONS, decision_body(
        gate_id="gate-nobody-planned", receipt_id="decision-stranger"))

    assert refused.payload["error"]["code"] != "gate_unreached"
    assert "does not carry" in refused.payload["error"]["message"] or (
        refused.payload["error"]["code"] == "store_error")
    assert journal_bytes(store) == before


def test_the_standing_receipt_is_none_while_two_answers_contradict(tmp_path):
    """`gate_decision` refuses to choose, and so does this.

    A journal holding two unsuperseded receipts for one gate is one the
    projection calls `unknown`, and there is no receipt in it for anybody to
    supersede. Answering with either of them would be this module picking a
    current answer the product says it cannot pick.

    `gate_answer` is what tells the two absences apart -- nobody has answered,
    against the answers contradict -- and the door needs both: the first admits
    a first answer and the second admits nothing at all.
    """
    _subject, store, _events, _plan = a_root_gate_run(tmp_path)
    one, two = (a_receipt(store, "decision-1"), a_receipt(store, "decision-2"))

    assert standing_receipt((), RUN_ID, "release") is None
    assert standing_receipt((one,), RUN_ID, "release") is one
    assert standing_receipt((one, two), RUN_ID, "release") is None
    assert gate_answer((), RUN_ID, "release") == "idle"
    assert gate_answer((one,), RUN_ID, "release") == "satisfied"
    assert gate_answer((one, two), RUN_ID, "release") is None
