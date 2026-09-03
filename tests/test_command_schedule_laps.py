"""Laps: when a body reopens, when it does not, and what a lap is worth.

Split from `test_command_graph_schedule.py` when that module crossed the
800-line cap, along the seam the design itself draws: the vocabulary, the
routing and the join rules are one circuit, and the arithmetic of §5 -- lap
index, arrivals, `required_pass`, and the reopening trigger -- is another. Both
build their journals through `tests/schedule_journal.py`, so neither can drift
from the other about what a run's records look like.

The three walk-throughs live here, and the first of them is why the arithmetic
was rewritten. Under the withdrawn reading -- "a body reopens while the loop's
bound is not reached" -- approving on the first pass UNSETTLED the body that had
just been approved: the bound had not been reached, and nothing in that formula
knew the loop's road had never opened. `test_approving_on_the_first_pass_...`
below is written to fail against it. The trigger is now the durable fact of that
road ACTUALLY opening, which an approval closes for good.

The other four claims here:

- **a retraction inside one lap is a correction and never a trip.** Distinct
  laps are counted, not receipts, and the LAST answer in a lap is that lap's
  answer -- so fixing a mistake does not send the run round again.
- **the cap bites.** `required_pass` is `min(1 + arrivals, bound)`, and at the
  last lap the arithmetic asks for one more than the plan allows. The cap is
  what ends the cycle rather than letting it run on.
- **`unknown` is not an answer, and the owner's refinement has two halves.** A
  step whose terminal result is `unknown` stays askable while attempts remain
  and is `blocked` when they are spent -- and that second half is one of the two
  facts that produce a stalled run, the other being a halted one.
- **an attempt in flight is not an ending.** An authorized attempt with no
  result yet blocks its own step and holds the whole run open -- whatever the
  bound says, and even where the step it names is already settled by an earlier
  answer, because an ending minted then stands in front of records that are
  still coming.
"""
from __future__ import annotations

from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
)
from conductor.command.graph_schedule import loop_position, schedule
from tests.schedule_journal import (
    NOW,
    RUN_ID,
    Journal,
    a_bounded_plan,
    loop_of,
    routed_dalio,
    row_of,
    through_the_body,
    with_a_note,
)


# -- the three walk-throughs ---------------------------------------------------


def test_approving_on_the_first_pass_completes_the_run_and_unsettles_nothing():
    """Walk-through (a), and the witness the withdrawn formula fails.

    The bound is 3 and one pass has happened, so a formula reading "reopen while
    the bound is unreached" demanded a second pass of every body step:
    `result-gate` would have gone from settled back to unsettled the instant it
    was approved, and `identify` would have been offered as runnable again after
    the run had finished.
    """
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "approve")

    computed = schedule(plan, journal.rows())

    assert computed.run_state == "complete"
    assert computed.settled == ("goal", "identify", "diagnose", "design",
                                "confirm-gate", "do", "result-gate")
    assert computed.unreachable == ("retry-loop",)
    assert computed.runnable == ()
    for node_id in ("identify", "diagnose", "design", "result-gate"):
        assert row_of(computed, node_id).required_pass == 1, node_id


def test_changes_requested_three_times_is_two_reopenings_and_then_complete():
    """Walk-through (b): bound 3 means three passes and two reopenings.

    `required_pass` is asserted at each lap, so the cap is proved to BITE: at
    the third answer the arithmetic asks for 4 and the bound holds it to 3,
    which is what ends the cycle instead of letting it run on.
    """
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")

    demanded = []
    for _lap in (2, 3):
        computed = schedule(plan, journal.rows())
        demanded.append(row_of(computed, "result-gate").required_pass)
        assert computed.state_of("result-gate") == "blocked"
        assert computed.state_of("identify") == "runnable"
        assert computed.state_of("retry-loop") == "blocked"
        through_the_body(journal)
        journal.decide("gate-result", "request_changes")

    final = schedule(plan, journal.rows())

    assert demanded == [2, 3]
    assert row_of(final, "result-gate").required_pass == 3
    assert row_of(final, "result-gate").settled_laps == 3
    assert final.run_state == "complete"
    assert final.state_of("retry-loop") == "settled"
    assert loop_position(journal.rows(), loop_of(plan)) == (3, True)


def test_the_body_is_reopened_by_the_road_opening_and_not_by_the_bound():
    """The trigger, isolated: same bound, same lap, two different answers.

    One journal ends in an approval and one in a request for changes, and
    nothing else differs. The bound is unreached in BOTH, so a formula reading
    the bound would reopen both; only the one whose loop road actually opened
    does.
    """
    plan = routed_dalio()
    approved, changed = Journal(), Journal()
    for journal, answer in ((approved, "approve"), (changed, "request_changes")):
        journal.did("goal")
        through_the_body(journal)
        journal.decide("gate-result", answer)

    ended = schedule(plan, approved.rows())
    reopened = schedule(plan, changed.rows())

    assert loop_position(approved.rows(), loop_of(plan)) == (1, False)
    assert loop_position(changed.rows(), loop_of(plan)) == (1, False)
    assert row_of(ended, "identify").required_pass == 1
    assert row_of(reopened, "identify").required_pass == 2
    assert ended.state_of("identify") == "settled"
    assert reopened.state_of("identify") == "runnable"


def test_a_retraction_inside_one_lap_is_a_correction_and_never_a_trip():
    """Walk-through (c): the LAST answer in a lap is that lap's answer.

    Two receipts, one lap, the second superseding the first. Distinct laps is
    still one, the standing word is approval, and the loop's road has never
    opened -- so the body stays settled and correcting a mistake does not send
    the run round again.
    """
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")
    journal.decide("gate-result", "approve")

    computed = schedule(plan, journal.rows())

    assert row_of(computed, "result-gate").required_pass == 1
    assert row_of(computed, "result-gate").settled_laps == 1
    assert computed.run_state == "complete"
    assert computed.unreachable == ("retry-loop",)


def test_a_retry_inside_one_lap_does_not_pre_pay_the_next():
    """The same fact for a task: two attempts in one lap answer one lap."""
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    journal.did("identify", "failed")
    journal.did("identify")

    computed = schedule(plan, journal.rows())

    assert row_of(computed, "identify").settled_laps == 1
    assert computed.state_of("identify") == "settled"


def a_retry_on_failure_plan() -> GraphDefinition:
    """A body reopened by a TASK's own road, with no gate anywhere in it.

    Routing is not only a gate's business: `on_failed` is a word a step
    produces, and a plan may retry on it. Without this the task arm of the lap
    arithmetic is never asked a question -- every other witness here reopens
    through a decision.
    """
    return GraphDefinition(
        graph_id="graph-retry", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="work", kind="task", title="Work",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="again", kind="loop", title="Again",
                         loop=GraphLoop(bound=3, back_to="work"))),
        edges=(GraphEdge(from_node="work", to_node="again",
                         condition="on_failed"),))


def test_a_failing_step_reopens_its_own_body_and_a_succeeding_one_does_not():
    """The task arm of the trigger, both directions over one plan.

    A failure delivers `on_failed`, the loop's road opens, and the body owes a
    second lap. A success delivers `on_succeeded`, that road closes, and the
    body is done -- with the loop node dead-ended behind it.
    """
    plan = a_retry_on_failure_plan()
    failed, passed = Journal(), Journal()
    failed.did("work", "failed")
    passed.did("work")

    reopened = schedule(plan, failed.rows())
    ended = schedule(plan, passed.rows())

    assert row_of(reopened, "work").required_pass == 2
    assert reopened.state_of("work") == "runnable"
    assert reopened.state_of("again") == "blocked"
    assert reopened.run_state == "open"

    assert row_of(ended, "work").required_pass == 1
    assert ended.state_of("work") == "settled"
    assert ended.unreachable == ("again",)
    assert ended.run_state == "complete"


def test_a_failure_then_a_success_delivers_both_laps_and_closes_the_road():
    """A retry of the step the loop itself reopens IS a second lap.

    `back_to` is `work`, so every authorization of `work` opens a lap by
    definition -- unlike a retry of some other body step, which stays inside the
    lap it was authorized in. The failure delivers lap 1 down the `on_failed`
    road, the loop asks for a second, and the success delivers it: two laps
    owed, two laps answered, and the road closed by the word that stands.
    """
    plan = a_retry_on_failure_plan()
    journal = Journal()
    journal.did("work", "failed")
    journal.did("work")

    computed = schedule(plan, journal.rows())

    assert (row_of(computed, "work").required_pass,
            row_of(computed, "work").settled_laps) == (2, 2)
    assert computed.state_of("work") == "settled"
    assert computed.unreachable == ("again",)
    assert computed.run_state == "complete"


def test_a_lap_whose_gate_answer_is_ambiguous_delivers_no_word():
    """Two standing answers in one lap is a lap that routed nowhere.

    The gate's word is read over the journal AS IT STOOD at that lap's last
    receipt, so a lap holding two unsuperseded answers supports neither and
    delivers nothing -- and the loop's road does not open on it. A reading that
    took the receipt's own action instead would have counted the lap.
    """
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")
    journal.decide("gate-result", "request_changes", supersede=False)

    computed = schedule(plan, journal.rows())

    assert row_of(computed, "identify").required_pass == 1
    assert computed.state_of("result-gate") == "runnable"
    assert computed.state_of("retry-loop") == "blocked"


# -- auto-settling steps, and the count that would deadlock them ---------------


def test_a_step_carrying_no_work_re_traverses_a_reopened_body_and_settles_again():
    """Witness 13. A body reopens, and the step that does no work follows it.

    Mid-lap the step is BLOCKED, because the step behind it has unsettled for
    the new lap and its road went pending -- which is how such a step
    re-traverses instead of standing settled through a lap it never saw. Once
    the lap is delivered it is settled again, on a `required_pass` of 3 and with
    zero settling facts to its name.

    That second half is the anti-deadlock claim, and comparing a count here
    would break it: 0 laps delivered is never >= 3, so both this step and the
    loop node beyond it would be stuck forever on the second lap of any body.
    """
    plan = with_a_note(routed_dalio())
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")

    midway = schedule(plan, journal.rows())

    assert row_of(midway, "note").required_pass == 3
    assert midway.state_of("identify") == "runnable"
    assert midway.state_of("note") == "blocked"
    assert row_of(midway, "note").blocked_by == ("identify",)

    through_the_body(journal)
    journal.decide("gate-result", "request_changes")
    delivered = schedule(plan, journal.rows())

    for node_id in ("note", "retry-loop"):
        row = row_of(delivered, node_id)
        assert (row.required_pass, row.settled_laps) == (3, 0), node_id
        assert delivered.state_of(node_id) == "settled", node_id
    assert delivered.run_state == "complete"


def test_a_settling_fact_written_before_the_loop_reopened_belongs_to_lap_one():
    """Records before the first authorization of `back_to` are the FIRST lap.

    The clamp, driven where it bites -- which is only where a body is actually
    owed a second lap, since a step outside every reopened body is judged in the
    frame where every record is lap 1 anyway.

    `do` is answered once before the loop's step was ever authorized and once
    inside the first traversal. That is ONE lap: everything ahead of the first
    reopening is part of the first trip round, not a trip of its own. Without
    the clamp those two facts fall in laps 0 and 1, `do` reads as having
    delivered the two laps it owes, and a step settles on a lap that never ran.
    """
    plan = routed_dalio()
    journal = Journal()
    journal.did("do")
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")

    computed = schedule(plan, journal.rows())

    assert row_of(computed, "do").required_pass == 2
    assert row_of(computed, "do").settled_laps == 1
    assert computed.state_of("do") != "settled"


def test_an_earlier_laps_answer_is_not_rewritten_by_the_one_standing_now():
    """A gate's word is read as it STOOD at that lap, not as it reads today.

    Lap 1 asked for changes and lap 2 approved. The approval supersedes the
    request, so asking the gate now says `satisfied` for the whole run -- and a
    reading that did that would report a run which went round twice as one that
    never reopened. The lap that reopened the body is a fact of the journal, and
    it stays one.
    """
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "request_changes")
    through_the_body(journal)
    journal.decide("gate-result", "approve")

    computed = schedule(plan, journal.rows())

    assert row_of(computed, "identify").required_pass == 2
    assert row_of(computed, "identify").settled_laps == 2
    assert computed.run_state == "complete"
    assert computed.unreachable == ("retry-loop",)


def a_two_road_loop() -> GraphDefinition:
    """A loop reached by two roads, so its arrivals are a real join."""
    return GraphDefinition(
        graph_id="graph-join-loop", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="seed", kind="task", title="Seed",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="left", kind="task", title="Left",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="right", kind="task", title="Right",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="again", kind="loop", title="Again",
                         loop=GraphLoop(bound=4, back_to="seed"))),
        edges=(GraphEdge(from_node="seed", to_node="left"),
               GraphEdge(from_node="seed", to_node="right"),
               GraphEdge(from_node="left", to_node="again",
                         condition="on_failed"),
               GraphEdge(from_node="right", to_node="again",
                         condition="on_failed")))


def test_a_loop_has_arrived_as_often_as_its_slowest_road_has_delivered():
    """Arrivals are a `min`, because a join needs every road.

    Two laps happened. `left` failed in both; `right` failed only in the first.
    The loop has therefore been reached once, not twice -- taking the faster
    road would ask the body for a third lap on the strength of one branch.
    """
    plan = a_two_road_loop()
    journal = Journal()
    journal.request("seed")
    journal.did("left", "failed")
    journal.did("right", "failed")
    journal.request("seed")
    journal.did("left", "failed")

    computed = schedule(plan, journal.rows())

    assert row_of(computed, "seed").required_pass == 2
    assert row_of(computed, "left").required_pass == 2


def test_a_loop_no_road_reaches_demands_nothing_of_anybody():
    """Why the arrivals of an unreached loop cannot be observed.

    A body is what the loop reopens INTERSECTED with what reaches the loop, and
    nothing reaches this one -- so its body is empty and its demand lands on no
    step. That is what makes the empty-road answer in `_arrivals` a totality of
    `min` rather than a number anything depends on.
    """
    plan = GraphDefinition(
        graph_id="graph-lonely", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="seed", kind="task", title="Seed",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="again", kind="loop", title="Again",
                         loop=GraphLoop(bound=2, back_to="seed"))),
        edges=())
    journal = Journal()
    journal.did("seed")
    journal.did("seed")

    computed = schedule(plan, journal.rows())

    assert loop_position(journal.rows(), loop_of(plan)) == (2, True)
    assert [row.required_pass for row in computed.nodes] == [1, 1]
    assert computed.run_state == "complete"


def test_a_step_carrying_no_work_is_settled_the_moment_the_plan_is_written():
    plan = GraphDefinition(
        graph_id="graph-note", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="note", kind="task", title="Note"),), edges=())

    computed = schedule(plan, ())

    assert computed.run_state == "complete"
    assert computed.settled == ("note",)


# -- `unknown` is not an answer, and the ruling has two halves -----------------


def test_a_terminal_unknown_does_not_settle_and_the_step_stays_askable():
    """Witness 14, first half: attempts remain, so the question stays open."""
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.result(journal.request("do"), "unknown")

    computed = schedule(a_bounded_plan(2), journal.rows())

    assert row_of(computed, "do").settled_laps == 0
    assert computed.state_of("do") == "runnable"
    assert row_of(computed, "do").attempts_spent is False


def test_a_later_success_settles_the_step_the_unknown_left_open():
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.result(journal.request("do"), "unknown")
    journal.did("do")

    computed = schedule(a_bounded_plan(2), journal.rows())

    assert computed.state_of("do") == "settled"
    assert computed.run_state == "complete"


def test_the_same_unknown_with_the_bound_spent_blocks_the_step_and_stalls_the_run():
    """Witness 14, second half, and one of the two producers of a stalled run.

    A step that can never settle again must not be offered as runnable, because
    that is a button `authorize` is bound to refuse. The attempt here is
    ANSWERED -- `unknown` is a reading the journal holds -- which is the one
    fact that tells this apart from the attempt still in flight below.
    """
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.result(journal.request("do"), "unknown")

    computed = schedule(a_bounded_plan(1), journal.rows())

    assert row_of(computed, "do").attempts_spent is True
    assert computed.state_of("do") == "blocked"
    assert computed.runnable == ()
    assert computed.run_state == "stalled"


def test_a_step_with_attempts_left_is_runnable_where_a_spent_one_is_not():
    """The positive control for the arm above, over the one differing fact."""
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.result(journal.request("do"), "unknown")
    rows = journal.rows()

    assert schedule(a_bounded_plan(2), rows).run_state == "open"
    assert schedule(a_bounded_plan(1), rows).run_state == "stalled"


def test_a_run_whose_attempt_is_in_flight_stays_open_with_nothing_runnable():
    """The journal above one record short, and that record is the whole rule.

    The bound is spent the moment the attempt is AUTHORIZED, so this step is
    `blocked` and nothing at all is runnable -- and yet a worker is executing
    right now and will append. `stalled` here would mint an ending in front of
    records that are still coming, which is exactly what bricked the journal.
    """
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.request("do")

    computed = schedule(a_bounded_plan(1), journal.rows())

    assert row_of(computed, "do").attempts_spent is True
    assert computed.state_of("do") == "blocked"
    assert computed.runnable == ()
    assert computed.run_state == "open"


def test_an_unanswered_request_blocks_its_own_step_at_every_bound():
    """`complete` is refused while any attempt is unanswered, at every bound.

    A first draft of this argued the two could not MEET -- a request settles
    nothing, so the step it names must be blocked or runnable -- and that was
    false in the one shape nobody drove: a SECOND attempt on a step an earlier
    answer already settled. The step is `settled`, nothing is blocked, and the
    run read `complete` while a worker was still holding an authorization. The
    word is now refused on the fact itself, and this holds every bound to it.
    """
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.request("do")
    rows = journal.rows()

    for bound in (1, 2, None):
        computed = schedule(a_bounded_plan(bound), rows)
        assert computed.state_of("do") == "blocked", bound
        assert computed.run_state == "open", bound


def test_a_second_attempt_in_flight_keeps_a_settled_step_from_ending_the_run():
    """The shape that read `complete` with a worker still executing.

    Two attempts are authorized on one step and only the first is answered.
    That answer SETTLES the step -- so nothing is runnable, nothing is blocked,
    and the plan has nothing left to open -- while the second attempt is still
    in flight and about to append. `complete` recorded there is a terminal in
    front of records that are still coming, which is how the journal bricked.

    Answering the second is what ends it, on the word its own journal supports.
    """
    journal = Journal()
    journal.decide("gate-1", "approve")
    answered = journal.request("do")
    in_flight = journal.request("do")
    journal.result(answered, "failed")

    computed = schedule(a_bounded_plan(None), journal.rows())

    assert computed.state_of("do") == "settled"
    assert computed.runnable == ()
    assert computed.run_state == "open"

    journal.result(in_flight, "failed")

    assert schedule(a_bounded_plan(None), journal.rows()).run_state == "complete"


def test_a_second_attempt_in_flight_on_a_spent_bound_keeps_the_run_open():
    """The same rule where the first answer settles nothing at all.

    `unknown` leaves the step unsettled and the bound of two is gone, so this
    step is `blocked` rather than `settled` -- a different row and the same
    verdict, because what holds the run open is the unanswered attempt and not
    anything about the step's own standing.
    """
    journal = Journal()
    journal.decide("gate-1", "approve")
    answered = journal.request("do")
    in_flight = journal.request("do")
    journal.result(answered, "unknown")

    computed = schedule(a_bounded_plan(2), journal.rows())

    assert row_of(computed, "do").attempts_spent is True
    assert computed.state_of("do") == "blocked"
    assert computed.run_state == "open"

    journal.result(in_flight, "unknown")

    assert schedule(a_bounded_plan(2), journal.rows()).run_state == "stalled"


def test_a_succeeded_step_settles_where_the_same_step_with_unknown_does_not():
    """The calibration for every `unknown` witness above: the outcome is the
    only difference, so what those tests measure is the word and not the road."""
    settled, askable = Journal(), Journal()
    for journal, outcome in ((settled, "succeeded"), (askable, "unknown")):
        journal.decide("gate-1", "approve")
        journal.result(journal.request("do"), outcome)

    assert schedule(a_bounded_plan(1), settled.rows()).run_state == "complete"
    assert schedule(a_bounded_plan(1), askable.rows()).run_state == "stalled"
