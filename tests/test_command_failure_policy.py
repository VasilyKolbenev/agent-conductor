"""One step's failure stopping a whole run, and the field that says so.

`halt_run` is a TIGHTENING and it is not routing. An `on_failed` edge says
where the plan goes NEXT; this says nothing further may be authorized in this
run at all -- including branches no road from the failing step could ever
reach. Neither can express the other, which is the whole argument for the field
existing beside the conditions rather than instead of them.

It needs no new record and no new run word, and the four claims below are why:

- **the plan carries it, and only where it could fire.** A gate and a loop are
  carried out by nobody, so they cannot fail and the contract refuses a policy
  on one. Absent stays absent, so no shipped document moves a byte.
- **the schedule spends it.** A settled step whose standing outcome is one of
  the failed words and whose policy says halt makes every step that could still
  run `blocked`; `runnable` is then empty and `blocked` is not, and §5.3's own
  arithmetic reads `stalled`. The halt is one of the TWO facts that word has,
  and it beats a document wait: a run stopped for good will never authorize
  anything again, whoever publishes what it was waiting for.
- **the ending is recorded through the road that already existed**, and
  `_hold_run_terminal` recomputes it from the plan's own bytes on replay -- so
  a journal that strips the field to soften the verdict is corrupt.
- **`unknown` is not a failure.** It is this product's word for *the journal
  supports no answer*, and an unanswered question stays askable.

The discriminating control matters as much as the halt itself: the SAME journal
on the SAME plan without the field stays open on its `on_failed` road. Without
it, every assertion here would also pass on a build that stalled every failing
run whatever its plan said.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.contracts import ContractError
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
)
from conductor.command.graph_schedule import FAILED_OUTCOMES, schedule
from conductor.command.graph_values import (
    FAILURE_POLICIES,
    settled_failure_policy,
)
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import (
    CorruptRun,
    RunStore,
    snapshot_digest,
)
from tests.schedule_journal import DIGEST, NOW, RUN_ID, Journal, row_of
from conductor.command.contracts import DecisionReceipt
from tests.test_command_run_store import CONFIG, a_run

#: The store-backed witnesses use their own run id: their plan is the
#: shipped Do node's, and the helpers that build store-valid records for
#: it are written against that document.
STORE_RUN = "run-001"

#: `do` fails, and `rescue` is the road that failure opens. A second, parallel
#: branch hangs off the gate and no road from `do` reaches it -- which is the
#: half routing cannot answer and the policy can.
def a_plan(*, policy=None, routed=True) -> GraphDefinition:
    nodes = (
        GraphNode(node_id="gate", kind="gate", title="Gate", gate_id="gate-1"),
        GraphNode(node_id="do", kind="task", title="Do",
                  instance_id="solo", capability="dispatch",
                  failure_policy=policy),
        GraphNode(node_id="rescue", kind="task", title="Rescue",
                  instance_id="solo", capability="review"),
        GraphNode(node_id="elsewhere", kind="task", title="Elsewhere",
                  instance_id="solo", capability="review"),
    )
    roads = [GraphEdge(from_node="gate", to_node="do"),
             GraphEdge(from_node="gate", to_node="elsewhere"),
             GraphEdge(from_node="do", to_node="rescue",
                       condition="on_failed" if routed else None)]
    return GraphDefinition(graph_id="graph-halt", run_id=RUN_ID,
                           created_at=NOW, nodes=tuple(nodes),
                           edges=tuple(roads))


def a_failing_journal(outcome="failed") -> Journal:
    """The gate answered, the work attempted, and the work reporting failure."""
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.result(journal.request("do"), outcome)
    return journal


#: The store-backed witnesses use the SHIPPED Do node verbatim, because the
#: store holds a request to its node's own instance, capability and arguments --
#: and the helpers that build store-valid records are written for that node. The
#: only thing this adds to it is the policy under test.
def a_stored_plan(*, policy, waiting=False):
    from tests.alpha3_graph_artifacts import dalio_definition

    doing = next(row for row in dalio_definition(run_id=STORE_RUN).nodes
                 if row.node_id == "do")
    nodes = (
        GraphNode(node_id="gate", kind="gate", title="Gate", gate_id="gate-1"),
        GraphNode.from_dict({**doing.as_dict(),
                             **({"failure_policy": policy} if policy else {})}),
        GraphNode(node_id="elsewhere", kind="task", title="Elsewhere",
                  instance_id=doing.instance_id, capability="review",
                  arguments={}),
    )
    if waiting:
        nodes = (*nodes, a_waiting_node(doing.instance_id))
    return GraphDefinition(
        graph_id="graph-halt", run_id=STORE_RUN, created_at=NOW, nodes=nodes,
        edges=(GraphEdge(from_node="gate", to_node="do"),
               GraphEdge(from_node="gate", to_node="elsewhere")))


def a_waiting_node(instance_id: str) -> GraphNode:
    """A step with no roads in whose plan says to wait for a document.

    A ROOT, so nothing about the drawing can hold it back: the only thing
    standing between it and being offered is an artifact nobody published --
    which is exactly the wait a halted run must not be kept open by.
    """
    return GraphNode(
        node_id="check", kind="task", title="Check it",
        instance_id=instance_id, capability="review",
        arguments={"work_item_id": "work-1",
                   "target_artifact_refs": ["artifact-brief"],
                   "result_artifact_ref": "artifact-verdict",
                   "review_profile": "quality"},
        missing_artifact_policy="block")


def a_store(tmp_path, *, policy, outcome="failed", decided=True,
            waiting=False):
    """One real run: the gate answered, the work attempted, the work failing.

    ``decided=False`` leaves the gate open, so the ANSWER is the settling fact
    and can be delivered through the decision route rather than written here.
    """
    from tests.test_command_graph_projection import (
        CONFIG as PLAN_CONFIG,
        a_proposal,
        a_request,
        a_result,
    )

    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=STORE_RUN, mode="confirm",
              config_digest=snapshot_digest(PLAN_CONFIG)), PLAN_CONFIG)
    store.append(a_stored_plan(policy=policy, waiting=waiting))
    if decided:
        store.append(DecisionReceipt(
            receipt_id="decision-1", run_id=STORE_RUN, gate_id="gate-1",
            action="approve", actor="release-owner", decided_at=NOW,
            reason="Let the work through.", scope_refs=("src",),
            config_digest=snapshot_digest(PLAN_CONFIG)))
    proposal = a_proposal(node_id="do", index=1, run_id=STORE_RUN)
    store.append(proposal)
    request = a_request(proposal, index=1, run_id=STORE_RUN)
    store.append(request)
    store.append(a_result(request, index=1, run_id=STORE_RUN,
                          outcome=outcome, evidence_refs=()))
    return store


# -- the plan carries it, and only where it could fire ------------------------


def test_the_vocabulary_is_one_word_and_it_only_ever_tightens():
    """There is no word for "carry on": carrying on is what silence already
    buys, and a vocabulary that could loosen would be a bypass."""
    assert FAILURE_POLICIES == {"halt_run"}
    assert settled_failure_policy("halt_run") == "halt_run"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_saying_nothing_and_saying_blank_are_the_same_answer(value):
    assert settled_failure_policy(value) is None


@pytest.mark.parametrize("value", [
    "continue", "carry_on", "none", "HALT_RUN", "halt", 1, True, []])
def test_a_policy_this_build_has_no_behaviour_for_is_refused(value):
    with pytest.raises(ContractError):
        settled_failure_policy(value)


@pytest.mark.parametrize("kind, extra", [
    ("gate", {"gate_id": "gate-2"}),
    ("loop", {"loop": GraphLoop(bound=2, back_to="do")}),
])
def test_a_step_that_carries_nothing_out_may_name_no_policy(kind, extra):
    """It cannot fail, so there is no failure for a policy to answer."""
    with pytest.raises(ContractError, match="cannot fail"):
        GraphNode(node_id="idle", kind=kind, title="Idle",
                  failure_policy="halt_run", **extra)


def test_a_capability_less_task_may_name_no_policy_either():
    with pytest.raises(ContractError, match="carries nothing out cannot fail"):
        GraphNode(node_id="note", kind="task", title="Note",
                  failure_policy="halt_run")


def test_a_plan_naming_no_policy_writes_no_key_and_moves_no_digest():
    """Omit-when-absent, at the one place a digest is taken over."""
    plain, halting = a_plan(), a_plan(policy="halt_run")

    assert all("failure_policy" not in node.as_dict()
               for node in plain.nodes)
    assert next(node for node in halting.nodes
                if node.node_id == "do").as_dict()["failure_policy"] == "halt_run"
    assert plain.digest() != halting.digest()


def test_a_document_writing_an_explicit_null_is_not_the_canonical_spelling():
    """Present-and-null is read as absent and re-rendered without the key, so
    the store refuses such a line as non-canonical."""
    written = {**next(node for node in a_plan().nodes
                      if node.node_id == "do").as_dict(),
               "failure_policy": None}

    rebuilt = GraphNode.from_dict(written)

    assert rebuilt.failure_policy is None
    assert "failure_policy" not in rebuilt.as_dict()


# -- the schedule spends it, and the control that proves it is the field ------


def test_a_failure_under_the_policy_stalls_the_whole_run():
    """Including the branch no road from the failing step can reach.

    `elsewhere` hangs off the gate and is runnable the moment the gate is
    answered. Routing could never close it; the policy does.
    """
    computed = schedule(a_plan(policy="halt_run"),
                        a_failing_journal().rows())

    assert computed.run_state == "stalled"
    assert computed.runnable == ()
    assert row_of(computed, "elsewhere").state == "blocked"
    assert row_of(computed, "rescue").state == "blocked"
    assert row_of(computed, "do").state == "settled"


def test_the_same_journal_without_the_field_stays_open_on_its_failed_road():
    """The discriminating control, and the whole point of it.

    Same plan, same records, one field absent: the `on_failed` road opens,
    `rescue` becomes runnable and the parallel branch is untouched. Without
    this every assertion above would also pass on a build that stalled every
    failing run whatever its plan said.
    """
    computed = schedule(a_plan(policy=None), a_failing_journal().rows())

    assert computed.run_state == "open"
    assert set(computed.runnable) == {"rescue", "elsewhere"}


def test_the_policy_leaves_unreachable_steps_where_they_were():
    """A halted run's terminal must still say which steps were impossible."""
    computed = schedule(a_plan(policy="halt_run", routed=False),
                        a_failing_journal("verification_failed").rows())

    assert computed.run_state == "stalled"
    # `rescue` sits behind an unconditional road out of a settled step, so it
    # was reachable and is merely stopped; nothing here is unreachable.
    assert computed.unreachable == ()


@pytest.mark.parametrize("outcome", sorted(FAILED_OUTCOMES))
def test_every_failed_word_this_build_records_fires_the_policy(outcome):
    """ONE definition of "this step failed", shared with the edge condition."""
    computed = schedule(a_plan(policy="halt_run"),
                        a_failing_journal(outcome).rows())

    assert computed.run_state == "stalled", outcome


def test_a_succeeded_step_never_fires_it():
    computed = schedule(a_plan(policy="halt_run"),
                        a_failing_journal("succeeded").rows())

    assert computed.run_state == "open"
    assert "rescue" not in computed.runnable  # its road opens on failure only


def test_unknown_is_not_a_failure_and_leaves_the_question_askable():
    """The owner's Q1 ruling: `unknown` is the journal supporting no answer."""
    computed = schedule(a_plan(policy="halt_run"),
                        a_failing_journal("unknown").rows())

    assert "unknown" not in FAILED_OUTCOMES
    assert computed.run_state == "open"
    assert "do" in computed.runnable


# -- the ending is recorded, and replay recomputes it -------------------------


def test_the_halted_run_records_a_stalled_terminal(tmp_path):
    """Through `close_if_terminal`'s existing road: no new record, no new word."""
    store = a_store(tmp_path, policy="halt_run")

    terminal = close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                                 ids=lambda kind: f"{kind}-001")

    assert terminal is not None
    assert terminal.state == "stalled"
    assert terminal.settled_nodes == ("gate", "do")
    assert [row.kind for row in store.read(STORE_RUN).records][-1] == "run_terminal"


def _computed(store):
    """This run's schedule, taken over the journal the store really holds."""
    recovered = store.read(STORE_RUN)
    return schedule(
        next(row.value for row in recovered.records
             if row.kind == "graph_definition"),
        tuple(row.value for row in recovered.records))


def a_pending_attempt(store, node):
    """One attempt authorized on this step and never answered.

    Written straight into the journal rather than driven through `authorize`,
    because what the witness needs is the RECORD: driving it would take a
    runtime, an adapter and a confirmation to say the same thing. `elsewhere`
    is this module's own node, so its documents are built here -- the
    projection's helpers are written against the shipped plan's nodes.
    """
    from conductor.command.contracts import ActionProposal
    from tests.test_command_graph_projection import a_request

    proposal = ActionProposal(
        proposal_id="proposal-2", run_id=STORE_RUN, attempt_id="attempt-002",
        instance_id=node.instance_id, capability=node.capability,
        arguments=node.payload(), scope=("src",), proposed_by="claude-dev",
        proposed_at=NOW, timeout_seconds=900,
        rationale=f"Carry out {node.node_id}.",
        config_digest=snapshot_digest(CONFIG), node_id=node.node_id)
    store.append(proposal)
    request = a_request(proposal, index=2, run_id=STORE_RUN)
    store.append(request)
    return request


def test_a_halted_run_with_an_attempt_still_in_flight_is_not_over_yet(tmp_path):
    """What a halt does NOT take back, and the ordering that says so.

    A halt stops what could still be offered, and a document wait is one of
    those: nobody may spend the document, so waiting for it is not a reason to
    keep the run open. An attempt already RUNNING is the other way round. The
    halt cannot recall it, the worker is going to append whatever the plan now
    says, and an ending recorded in front of that append is the same durable
    lie -- and bricks the same journal.

    So the run stays open until that attempt answers, and the ending is
    recorded on its road, after its own record.
    """
    from tests.test_command_graph_projection import a_result

    store = a_store(tmp_path, policy="halt_run")
    elsewhere = next(row for row in a_stored_plan(policy="halt_run").nodes
                     if row.node_id == "elsewhere")
    request = a_pending_attempt(store, elsewhere)
    path = store.run_path(STORE_RUN) / "records.jsonl"
    before = path.read_bytes()

    assert _computed(store).run_state == "open"
    assert close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                             ids=lambda kind: f"{kind}-001") is None
    assert path.read_bytes() == before

    store.append(a_result(request, index=2, run_id=STORE_RUN,
                          outcome="unknown", evidence_refs=()))
    terminal = close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                                 ids=lambda kind: f"{kind}-001")

    assert terminal is not None and terminal.state == "stalled"
    replayed = store.read(STORE_RUN)
    assert [row.kind for row in replayed.records][-2:] == [
        "action_result", "run_terminal"]
    assert replayed.warnings == ()


def test_a_halt_takes_back_a_document_wait_and_not_an_attempt_in_flight():
    """The two halves side by side, over one differing record.

    The same plan and the same halt. In the first journal the second step's
    attempt is unanswered and the run is open; in the second that attempt has
    been answered `unknown`, and with nothing left in flight the halt is the
    whole of what remains -- so the run is over and says so.
    """
    running, answered = Journal(), Journal()
    for journal in (running, answered):
        journal.decide("gate-1", "approve")
    running.request("elsewhere")
    answered.result(answered.request("elsewhere"), "unknown")
    for journal in (running, answered):
        journal.result(journal.request("do"), "failed")

    assert schedule(a_plan(policy="halt_run"),
                    running.rows()).run_state == "open"
    assert schedule(a_plan(policy="halt_run"),
                    answered.rows()).run_state == "stalled"


def test_a_halted_run_carrying_a_waiting_step_is_still_stalled(tmp_path):
    """A halt beats a wait, and the ordering is the whole of this witness.

    A document wait keeps a run open because publishing the document is
    something a person can still go and do. Under a halt it is not: nothing may
    be authorized in this run again whatever arrives, so the waiting step is not
    work that is pending -- it is one more thing that will never happen.
    """
    store = a_store(tmp_path, policy="halt_run", waiting=True)
    computed = _computed(store)

    waiting = row_of(computed, "check")

    assert waiting.state == "blocked"
    assert waiting.awaiting_artifacts == ("artifact-brief",)
    assert waiting.attempts_spent is False and waiting.blocked_by == ()
    assert computed.run_state == "stalled"

    terminal = close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                                 ids=lambda kind: f"{kind}-001")

    assert terminal is not None and terminal.state == "stalled"
    assert [row.kind for row in store.read(STORE_RUN).records][-1] == (
        "run_terminal")


def test_the_unhalted_twin_records_no_terminal_at_all(tmp_path):
    """The control again, on the closing road: an open plan ends nothing."""
    store = a_store(tmp_path, policy=None)

    assert close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                             ids=lambda kind: f"{kind}-001") is None
    assert [row.kind for row in store.read(STORE_RUN).records][-1] != "run_terminal"


def test_a_journal_that_strips_the_policy_from_the_plan_is_corrupt(tmp_path):
    """The verdict is recomputed from the plan's own bytes, so softening it by
    editing the plan makes the standing terminal disagree with the records."""
    store = a_store(tmp_path, policy="halt_run")
    close_if_terminal(store, STORE_RUN, clock=lambda: NOW,
                      ids=lambda kind: f"{kind}-001")
    path = store.run_path(STORE_RUN) / "records.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    forged = []
    for line in lines:
        row = json.loads(line)
        if row["record_type"] == "graph_definition":
            for node in row["record"]["nodes"]:
                node.pop("failure_policy", None)
        forged.append(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")))
    path.write_text("\n".join(forged) + "\n", encoding="utf-8", newline="\n")

    with pytest.raises(CorruptRun, match="does not match what this run"):
        RunStore(tmp_path).read(STORE_RUN)


def test_the_halted_run_authorizes_nothing_further(tmp_path):
    """The refusal a person meets, and it is the plan's own.

    `elsewhere` is the branch no road from the failing step reaches. It was
    runnable the moment the gate was answered and routing could never close it;
    the policy does, so `authorize` refuses it as blocked rather than minting a
    request for work the run has stopped doing.
    """
    from conductor.command.authorize_holds import _hold_node_is_eligible
    from conductor.command.runtime_values import AuthorizationError

    store = a_store(tmp_path, policy="halt_run")
    recovered = store.read(STORE_RUN)

    with pytest.raises(AuthorizationError, match="is blocked"):
        _hold_node_is_eligible(_As("elsewhere"), recovered)


def test_the_unhalted_twin_still_authorizes_that_branch(tmp_path):
    """The control on the refusal road: the field is what closed the branch."""
    from conductor.command.authorize_holds import _hold_node_is_eligible

    store = a_store(tmp_path, policy=None)

    assert _hold_node_is_eligible(
        _As("elsewhere"), store.read(STORE_RUN)) is None


class _As:
    """The one fact `_hold_node_is_eligible` reads off a proposal."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id


# -- the decision ROUTE, which is where a person meets all of this ------------
#
# Everything above judges the schedule and the closing road directly. A Human
# never calls either: they answer a gate, and the route answers them. The route
# runs `close_if_terminal` inside the decision's own transaction, so this arm is
# spent on EVERY decision every run of this product will ever take -- including
# the overwhelming majority written against plans that name no policy at all.
# That is the road a browser test found stalling, and neither half of it was
# covered by anything above.


def _decided_through_the_route(tmp_path, *, policy):
    """One real decision, delivered the way a person delivers one."""
    from tests.test_command_graph_route import an_api_over
    from tests.test_command_http_api import decision_body, post

    store = a_store(tmp_path, policy=policy, decided=False)
    subject = an_api_over(tmp_path, adapters=[])
    answered = post(subject, f"/command/runs/{STORE_RUN}/decisions",
                    decision_body(receipt_id="decision-1", gate_id="gate-1"))
    return answered, [row.kind for row in store.read(STORE_RUN).records]


def test_a_decision_on_a_plan_that_names_no_policy_answers_and_ends_nothing(
        tmp_path):
    """The compat control, on the road every decision in this product takes.

    A plan carrying no `failure_policy` is what every workflow drawn before this
    field existed is, and what most drawn after it will be. The answer is the
    receipt, the status is 201, and the run is left open -- `elsewhere` is still
    unsettled, so there is nothing to end.
    """
    answered, kinds = _decided_through_the_route(tmp_path, policy=None)

    assert answered.status == 201
    assert answered.payload["gate_id"] == "gate-1"
    assert kinds[-1] == "decision" and "run_terminal" not in kinds


def test_the_same_route_on_a_plan_that_carries_it_records_the_stalled_ending(
        tmp_path):
    """And the discriminating twin: the field is what changes the answer.

    One journal, one route, one decision body. The only difference is the word
    on the `do` node -- so a `run_terminal` appearing here and not above is the
    policy being spent, rather than the route having ended the run for some
    reason of its own.
    """
    answered, kinds = _decided_through_the_route(tmp_path, policy="halt_run")

    assert answered.status == 201
    assert kinds[-1] == "run_terminal"


# -- the template road: drawn, refused, and carried into the plan -------------


def a_template(*, policy=None, bound=True):
    """One reusable step that binds a role, or one that binds none."""
    from conductor.command.graph_template import GraphTemplate, TemplateNode

    return GraphTemplate(
        template_id="halting", revision=1, title="Halting",
        nodes=(TemplateNode(node_id="gate", kind="gate", title="Gate",
                            gate_id="gate-1"),
               TemplateNode(node_id="do", kind="task", title="Do",
                            role_id="doer" if bound else None,
                            capability="dispatch" if bound else None,
                            failure_policy=policy)),
        edges=(GraphEdge(from_node="gate", to_node="do"),))


def test_a_template_step_binding_no_role_may_name_no_policy():
    """The definition's pairing rule said in the TEMPLATE's own vocabulary.

    The message is what is asserted, and that is the whole point of the rule
    existing twice. A template validates by building a definition, so the layer
    below would refuse this anyway -- in the definition's words, about a
    `capability`. A person drawing a workflow does not name capabilities; they
    name ROLES, and being told about a field they cannot see is being told
    nothing. So the template refuses first and says `binds no role of its own`.
    """
    from conductor.command.graph_template import TemplateError

    with pytest.raises(TemplateError, match="binds no role of its own"):
        a_template(policy="halt_run", bound=False)
    # And the definition's own rule stands behind it, in its own words.
    with pytest.raises(ContractError, match="names a failure policy and no "
                       "capability"):
        GraphNode(node_id="do", kind="task", title="Do",
                  failure_policy="halt_run")


def test_a_template_step_that_does_bind_one_may_name_it():
    """The positive control: the refusal above is about the binding."""
    assert next(node for node in a_template(policy="halt_run").nodes
                if node.node_id == "do").failure_policy == "halt_run"


def test_the_policy_survives_the_road_from_a_drawing_to_a_frozen_plan():
    """Copied, never resolved: it names no role and no deployment.

    A field a template stores and `materialize` drops is a plan that says
    something the drawing never said -- and nothing downstream could tell.
    """
    from conductor.command.graph_template import RunBinding, materialize

    plan = materialize(
        a_template(policy="halt_run"),
        RunBinding(assignments={"doer": "solo"}),
        {"instances": [{"id": "solo", "adapter": "claude-code"}]},
        graph_id="graph-halt", run_id=STORE_RUN, created_at=NOW)

    planned = next(row for row in plan.nodes if row.node_id == "do")
    assert planned.failure_policy == "halt_run"
    # And it is in the plan's own BYTES, which is what the store replays.
    assert planned.as_dict()["failure_policy"] == "halt_run"


def test_a_template_naming_no_policy_carries_none_into_the_plan():
    """Absent stays absent all the way down, so no digest moves."""
    from conductor.command.graph_template import RunBinding, materialize

    plan = materialize(
        a_template(policy=None), RunBinding(assignments={"doer": "solo"}),
        {"instances": [{"id": "solo", "adapter": "claude-code"}]},
        graph_id="graph-halt", run_id=STORE_RUN, created_at=NOW)

    assert all(row.failure_policy is None for row in plan.nodes)
    assert all("failure_policy" not in row.as_dict() for row in plan.nodes)
