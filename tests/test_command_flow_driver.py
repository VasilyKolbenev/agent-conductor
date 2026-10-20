"""The driver on fake providers over the compiled cycles: the tester, the branches, the loop order.

Spec 7.5 to 7.7 make claims about what the core does with a cycle the desk draws; 7.11 item 5
asks for each of them to be proved on the driver and not only on the schedule. Every test here is
a real server on a real owner (`tests/flow_driver_bench.py`), the flow compiled by the product,
the grant drafted by the server, the harnesses scripted doubles.
"""
from __future__ import annotations

from threading import Event

import pytest

from conductor.command import policy_driver
from conductor.command.authorization_inputs import executable_nodes
from conductor.command.graph_template_document import TemplateError
from conductor.command.flow_rules import flow_rules
from tests.flow_driver_bench import FlowCycle, template_of
from tests.test_command_workflow_flow import CANONICAL, chain, looped_flows, review, step
from tests.test_policy_feedback import PAYLOAD
from tests.test_server_command_http import _request

TESTER = looped_flows()["tester"]
DOER = step("do", "agent", verifier_role_id="role-checker")
LOOP_OF = {"do": "do-fix", "tester": "tester-fix"}


@pytest.fixture
def cycle(tmp_path):
    made = []

    def make(flow, **script):
        made.append(FlowCycle(tmp_path / f"project-{len(made)}", flow, **script))
        return made[-1]
    yield make
    for one in made:
        one.close()


def with_loop(flow, *loops):
    """`flow` and, for each `(name, back_to, bound, source, when)`, one loop step and its road."""
    steps = [*flow["steps"], *(step(name, "loop", back_to=back, bound=bound)
                               for name, back, bound, _source, _when in loops)]
    links = [*flow["links"], *({"from": source, "to": name, "when": when}
                               for name, _back, _bound, source, when in loops)]
    return {**flow, "steps": steps, "links": links}


def at_result_gate(run):
    return run.until("the result gate", lambda: run.plan_state() == "open" and run.reason() ==
                     "waiting")


def test_tester_rejection_returns_to_the_doer_with_the_testers_checker_feedback(cycle):
    """L43: the tester's checker rejects; the doer is asked again with that exact feedback."""
    run = cycle(TESTER, verdicts=[("do", "accept"), ("tester", "typed"), ("do", "accept"),
                                  ("tester", "accept")])
    run.start()
    run.until("the result gate", lambda: run.outcomes("tester") == [
        "verification_failed", "succeeded"])
    assert run.steps() == ["analyst", "do", "tester", "do", "tester"]
    feedback = run.records("correction_feedback")
    assert len(feedback) == 1 and feedback[0].as_dict()["payload"] == PAYLOAD
    assert feedback[0].source_node_id == "tester" and feedback[0].checker_instance_id == "checker"
    doers = [p for p in run.records("action_proposal") if p.node_id == "do"]
    assert doers[1].feedback_ids == (feedback[0].feedback_id,)
    assert [given for name, _args, given in run.doer.dispatches
            if name == "do"] == [(), (feedback[0].as_dict(),)]
    assert run.checker.mismatches == [] and not run.terminal()
    assert run.reason() == "waiting", "the run stands at the result gate, a human's"


def test_second_tester_rejection_at_two_passes_completes_the_run(cycle):
    run = cycle(TESTER, verdicts=[("do", "accept"), ("tester", "typed"), ("do", "accept"),
                                  ("tester", "typed")])
    run.start()
    run.until("the end", lambda: run.plan_state() == "complete")
    assert run.steps() == ["analyst", "do", "tester", "do", "tester"], "no third pass"
    assert run.outcomes("tester") == ["verification_failed", "verification_failed"]
    assert run.holder() is None, "a complete run frees the slot"
    assert run.checker.mismatches == []
    assert run.automation()[0] == "complete"
    status, _body = run.decide("result", "approve-anyway")
    assert status != 201, "the result gate never opened on a failed result"


def test_doer_rejection_during_a_tester_return_completes_without_correction(cycle):
    run = cycle(TESTER, verdicts=[("do", "accept"), ("tester", "typed"), ("do", "typed")])
    run.start()
    run.until("the end", lambda: run.plan_state() == "complete")
    assert run.steps() == ["analyst", "do", "tester", "do"], "the doer's own road is closed"
    assert run.outcomes("do") == ["succeeded", "verification_failed"]
    assert len(run.records("correction_feedback")) == 2
    assert run.holder() is None and run.checker.mismatches == []
    assert run.settle() == 4, "nothing more was asked"


def test_tester_rejection_after_a_doer_correction_stands_feedback_required(cycle):
    run = cycle(TESTER, verdicts=[("do", "typed"), ("do", "accept"), ("tester", "typed")])
    run.start()
    reason = run.until("the honest stop", lambda: run.outcomes("tester") == [
        "verification_failed"])
    assert reason == "feedback_required"
    assert run.steps() == ["analyst", "do", "do", "tester"]
    assert run.plan_state() == "open" and not run.terminal()
    assert run.holder() == "run", "the run keeps the slot: only a human ends it"
    assert run.automation() == ("stalled", "feedback_required")
    assert run.settle() == 4 and run.checker.mismatches == []


def test_exhausted_correction_completes_and_frees_the_slot(cycle):
    flow = with_loop(chain(review("analyst"), DOER, step("result", "human")),
                     ("do-fix", "do", 2, "do", "failed"))
    run = cycle(flow, verdicts=[("do", "typed"), ("do", "typed")])
    run.start()
    run.until("the end", lambda: run.plan_state() == "complete")
    assert run.outcomes("do") == ["verification_failed", "verification_failed"]
    assert run.steps() == ["analyst", "do", "do"], "no third pass: the loop's bound is spent"
    assert run.holder() is None and run.automation()[0] == "complete"
    assert all(outcome != "succeeded" for outcome in run.outcomes("do"))
    status, _body = run.decide("result", "approve-anyway")
    assert status != 201, "a person's approval cannot stand in for the check"


@pytest.mark.parametrize("how", ["the human rejects the result", "an agent review fails"])
def test_rejected_review_completes_the_run(cycle, how):
    flow = chain(review("analyst"), DOER, step("result", "human"))
    run = cycle(flow, outcomes={"analyst": ["failed"]} if how.startswith("an agent") else None)
    run.start()
    if how.startswith("the human"):
        at_result_gate(run)
        status, body = run.decide("result", "reject-result", action="reject")
        assert status == 201, body
    # A decision ends the plan in the journal at once and the driver frees the slot on its next
    # tick; until then its last reason (`waiting`) reads as quiet. So the slot is waited for.
    run.until("the end and the slot freed",
              lambda: run.plan_state() == "complete" and run.holder() is None)
    assert run.holder() is None and run.automation()[0] == "complete"
    assert run.steps() == (["analyst"] if how.startswith("an agent") else ["analyst", "do"])
    assert run.outcomes("do") in ([], ["succeeded"])


class HeldTick:
    """Stands where the run's seed settler stands, counts the ticks that see a decision and holds
    the first of them.

    The tick waits here, before it reads the plan and outside every store lock, until `go` is
    set. A tick that starts before the decision passes; the settler itself always answers.
    `seen` counts every tick that found a decision in the journal, held or not (armed or not):
    the driver is one thread, so each such tick whose settler answers yes then reads the plan.
    """

    def __init__(self, seeds, store):
        self.seeds, self.store = seeds, store
        self.armed, self.entered, self.go = Event(), Event(), Event()
        self.seen = 0

    def settle(self, run_id):
        if any(row.kind == "decision" for row in self.store.read(run_id).records):
            self.seen += 1
            if self.armed.is_set():
                self.entered.set()
                assert self.go.wait(10), "the test never let the tick go"
        return self.seeds.settle(run_id)


def slot_of(run):
    """The slot the queue door reports, as the desk reads it."""
    status, payload, _ = _request(run.subject, "GET", "/command/queue")
    assert status == 200, payload
    return payload["slot"]


def test_a_human_ending_wakes_the_driver_that_frees_the_slot_and_then_publishes_a_frame(
        cycle, monkeypatch):
    """Two facts in order (spec 4.4.4, 4.4.6): the decision door writes the ending and wakes the
    driver; the tick it woke frees the slot and only then publishes one frame. Between them the
    run is complete and still holds the slot, which the queue reads as busy with `plan_ended`.
    The once-a-second tick is moved away and the test never wakes the driver, so the held tick
    exists only if the decision woke it. The driver can wake itself too (`deactivate` and
    `activate` set the flag), so the slot is freed by that tick only if no other tick saw the
    decision before the frame: `held.seen == 1` once it is out, and the one frame comes from it."""
    monkeypatch.setattr(policy_driver, "TICK_SECONDS", 60)
    run = cycle(chain(review("analyst"), DOER, step("result", "human")))
    run.start()
    at_result_gate(run)
    policy = run.subject.command_api._policy
    held = policy.seeds = HeldTick(policy.seeds, run.store)
    frames, publish = [], policy.notify
    policy.notify = lambda run_id: (frames.append((run_id, run.holder())), publish(run_id))
    held.armed.set()
    try:
        status, body = run.decide("result", "reject-result", action="reject")
        assert status == 201, body
        assert held.entered.wait(15), "the decision never woke the driver"
        assert run.plan_state() == "complete" and run.terminal()
        assert run.automation() == ("complete", "plan_ended")
        assert run.holder() == "run" and frames == []
        assert slot_of(run) == {"state": "busy", "run_id": "run", "reason_code": "plan_ended"}
    finally:  # a failure above must not leave the driver's thread held past the teardown
        held.armed.clear()
        held.go.set()
    run.until("the frame after the slot is freed", lambda: frames == [("run", None)])
    assert held.seen == 1, (f"{held.seen} ticks saw the decision: the slot is freed by the tick "
                            "the decision woke, and not by one the driver woke for itself")
    assert run.holder() is None and run.automation()[0] == "complete"
    assert slot_of(run) == {"state": "free", "run_id": None, "reason_code": None}


def fork(order=("left", "right")):
    """`plan` opens two branches that `join` needs both of, then a human answer."""
    branches = {"left": review("left", role_id="role-reviewer"),
                "right": review("right", role_id="role-designer")}
    return {"flow_version": 1, "title": "Fork", "ext": {}, "links": [
        {"from": "plan", "to": "left", "when": "success"},
        {"from": "plan", "to": "right", "when": "success"},
        {"from": "left", "to": "join", "when": "success"},
        {"from": "right", "to": "join", "when": "success"},
        {"from": "join", "to": "result", "when": "success"}],
        "steps": [review("plan"), *(branches[name] for name in order),
                  step("join", "agent", verifier_role_id="role-checker"),
                  step("result", "human")]}


def alternating(run):
    """Whether every request of the journal came after the result of the one before it."""
    kinds = [row.kind for row in run.store.read("run").records
             if row.kind in ("action_request", "action_result")]
    return kinds == ["action_request", "action_result"] * (len(kinds) // 2)


@pytest.mark.parametrize("order", [("left", "right"), ("right", "left")])
def test_branches_run_one_at_a_time_in_node_order(cycle, order):
    run = cycle(fork(order))
    run.start()
    at_result_gate(run)
    assert run.steps() == ["plan", *order, "join"]
    assert run.doer.most_in_flight == 1 and alternating(run)
    assert run.checker.mismatches == [] and run.checker.checked == [("join", "accept")]


def test_a_failed_branch_leaves_the_other_branch_feedback_required(cycle):
    run = cycle(fork(), outcomes={"left": ["failed"]})
    run.start()
    reason = run.until("the honest stop", lambda: run.outcomes("left") == ["failed"])
    assert reason == "feedback_required"
    assert run.steps() == ["plan", "left"], "the right branch was ready and was not started"
    assert run.plan_state() == "open" and run.holder() == "run"
    assert run.automation() == ("stalled", "feedback_required")
    assert run.settle() == 2 and not run.terminal()


def rework_cycle(rework_first):
    """A checked doer with a correction loop and a rework loop that goes back to the analyst.

    The two loops count their laps by different steps (`analyst` and `do`), and the doer is in the
    body of both, so which of the two stands earlier in the plan decides whose count it is judged
    by (spec 7.5, `_lap_demands`): the order of the steps below is the order of the loops.
    """
    flow = chain(review("analyst"), DOER, step("result", "human"))
    loops = [("redo", "analyst", 3, "result", "changes_requested"),
             ("do-fix", "do", 3, "do", "failed")]
    return with_loop(flow, *(loops if rework_first else loops[::-1]))


def rework_after_one_correction(cycle, rework_first):
    """One typed rejection corrected, then the human asks for changes at the result gate."""
    run = cycle(rework_cycle(rework_first), verdicts=[("do", "typed"), ("do", "accept"),
                                                      ("do", "accept")])
    run.start()
    at_result_gate(run)
    assert run.steps() == ["analyst", "do", "do"]
    status, body = run.decide("result", "changes", action="request_changes")
    assert status == 201, body
    return run


def test_rework_placed_before_correction_reruns_the_doer_after_one_correction(cycle):
    run = rework_after_one_correction(cycle, rework_first=True)
    run.until("the reworked result", lambda: run.outcomes("do") == [
        "verification_failed", "succeeded", "succeeded"])
    assert run.steps() == ["analyst", "do", "do", "analyst", "do"], "the doer ran again"
    assert run.checker.mismatches == [] and not run.terminal()
    assert run.reason() == "waiting", "the gate is asked again with a new result"


def test_correction_placed_before_rework_reasks_the_gate_with_the_old_result(cycle):
    run = rework_after_one_correction(cycle, rework_first=False)
    run.until("the gate asked again", lambda: run.outcomes("analyst") == ["succeeded"] * 2)
    assert run.settle() == 4, "the analyst ran again and the doer did not"
    assert run.steps() == ["analyst", "do", "do", "analyst"] and run.outcomes("do") == [
        "verification_failed", "succeeded"]
    assert run.plan_state() == "open" and not run.terminal() and run.reason() == "waiting"
    status, body = run.decide("result", "approve-old", supersedes="changes")
    assert status == 201, body
    run.until("the end", lambda: run.plan_state() == "complete")


# --- every canonical flow, through the doors, on fake providers -------------------------------


#: The one corpus entry that draws a route step, which carries out no work: it exists to round-trip
#: typed fields through the compiler and the importer, and no template is built from it.
WITH_A_ROUTE = "a route, another capability and typed extras"


def test_the_corpus_flow_that_draws_a_route_step_is_refused_where_the_template_is_built():
    rows = flow_rules(CANONICAL[WITH_A_ROUTE])
    assert "when_invalid" in [row["code"] for row in rows if row["severity"] == "error"]
    with pytest.raises(TemplateError, match="carries out no work"):
        template_of(CANONICAL[WITH_A_ROUTE])


@pytest.mark.parametrize("name", sorted(set(CANONICAL) - {WITH_A_ROUTE}))
def test_every_canonical_flow_publishes_opens_and_previews_on_fake_providers(cycle, name):
    """`from_dict` -> publish -> open_run -> build_preview (spec 13.1), each by its own door."""
    run = cycle(CANONICAL[name], through_doors=True)
    assert run.published["template_id"] == run.template.template_id, "the revision is on file"
    assert run.graph.run_id == "run" and run.graph.graph_id, "the run was opened with its plan"
    assert {node.node_id for node in run.graph.nodes} == {
        row["node_id"] for row in run.template.as_dict()["nodes"]}, "the plan is the template's"
    run.prepare()
    preview = run.preview()
    limits = preview["terms"]["node_limits"]
    assert [row["node_id"] for row in limits] == [
        node.node_id for node in executable_nodes(run.graph)], "each step the plan performs"
    assert all(row["max_attempts"] >= 1 and row["timeout_seconds"] >= 1 for row in limits)
    assert preview["terms"]["max_actions"] >= len(limits) and preview["preview_digest"]
