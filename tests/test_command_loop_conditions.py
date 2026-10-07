"""A road between two loops opens on the word its source PRODUCES, never on arrival.

R03 of the Codex review of `8dec0e4`. `_routed_count` answered a loop node's road
with the loop's arrivals whatever the road said, on the stated ground that a step
which settles by arriving "could not have delivered a different number of them on
a conditional road than on a plain one". True of a task carrying no capability --
the contract refuses a condition on its roads -- and false of a loop, which
produces one of TWO words per lap. The scheduler design (§5.2) already gave each
its own count: `on_bound_remaining` delivers `min(arrivals, bound - 1)` laps and
`on_bound_reached` delivers one lap once the bound is reached. Without that arm
the three roads out of an exhausted inner loop were one road, and an outer loop
asking for `on_bound_remaining` reopened the body the inner loop had just spent:
the extra `goal` was proposed AND authorized, 201/201, through the live API.

Three claims, three layers: the pure trajectory of each road over a real journal;
the live authorization that must refuse the extra step and must still admit it on
the roads that legitimately reopen; and the grammar, which is not narrowed --
every one of the three roads still publishes.
"""
from __future__ import annotations

import pytest

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
)
from conductor.command.graph_schedule import loop_position, schedule
from tests.schedule_journal import NOW, RUN_ID, Journal, row_of

#: The one acting step both loops go back to. Outside neither body: it IS the
#: body, which is what makes "reopen" and "authorize goal again" one fact.
GOAL = GraphNode(node_id="goal", kind="task", title="Goal",
                 instance_id="solo", capability="review")


def nested_loops(condition: str | None, *, inner_bound: int,
                 outer_bound: int) -> GraphDefinition:
    """`goal -> inner -> outer`, both loops returning to `goal`.

    The road between the loops carries `condition`; the road into the inner
    loop carries none. Every other shape here is the reviewer's own probe.
    """
    return GraphDefinition(
        graph_id="graph-nested-loops", run_id=RUN_ID, created_at=NOW,
        nodes=(GOAL,
               GraphNode(node_id="inner", kind="loop", title="Inner",
                         loop=GraphLoop(bound=inner_bound, back_to="goal")),
               GraphNode(node_id="outer", kind="loop", title="Outer",
                         loop=GraphLoop(bound=outer_bound, back_to="goal"))),
        edges=(GraphEdge(from_node="goal", to_node="inner"),
               GraphEdge(from_node="inner", to_node="outer",
                         condition=condition)))


def after_laps(plan: GraphDefinition, laps: int):
    """`goal` carried out `laps` times, and what the plan then permits."""
    journal = Journal()
    for _lap in range(laps):
        journal.did("goal")
    return schedule(plan, journal.rows()), journal


# -- the pure reading -----------------------------------------------------------


def test_an_exhausted_inner_loop_does_not_reopen_the_body_for_an_outer_loop_that_asks_for_bound_remaining():
    """The reported defect, as the schedule's own reading.

    One pass, inner bound 1: the inner loop is at its ceiling, so the word it
    produces is `on_bound_reached` and a road asking for `on_bound_remaining`
    is CLOSED. Nothing delivers a lap to the outer loop, so nothing owes a
    second pass and the run is over. Before the arm existed the outer loop was
    told one lap had arrived, demanded a second of `goal`, and `goal` stood
    `runnable` with the road that would have carried its result already shut.
    """
    plan = nested_loops("on_bound_remaining", inner_bound=1, outer_bound=2)
    computed, journal = after_laps(plan, 1)

    assert loop_position(journal.rows(), plan.nodes[1]) == (1, True)
    assert computed.state_of("goal") == "settled"
    assert row_of(computed, "goal").required_pass == 1
    assert computed.state_of("inner") == "settled"
    assert computed.state_of("outer") == "unreachable"
    assert row_of(computed, "outer").closed_by == ("inner",)
    assert computed.runnable == ()
    assert computed.run_state == "complete"


@pytest.mark.parametrize("condition, laps_to_complete, outer_at_the_end", [
    ("on_bound_remaining", 2, "unreachable"),
    ("on_bound_reached", 2, "settled"),
    (None, 3, "settled"),
])
def test_the_three_roads_out_of_a_loop_are_three_different_trajectories(
        condition, laps_to_complete, outer_at_the_end):
    """Inner bound 2, outer bound 3, and the three roads part ways.

    `on_bound_remaining` delivers the inner loop's one unreached lap and then
    closes when the bound is reached, so the outer loop never reopens anything
    and dead-ends. `on_bound_reached` delivers exactly one lap, once, when the
    inner loop is spent -- the outer loop settles and the run ends on the same
    pass. An unconditional road delivers every arrival, so the outer loop asks
    for one pass more than the inner loop did. A build on which the three read
    alike -- the reviewer's `CONDITION_CONTROL` rows -- fails two of these.
    """
    plan = nested_loops(condition, inner_bound=2, outer_bound=3)

    for laps in range(1, laps_to_complete):
        computed, _journal = after_laps(plan, laps)
        assert computed.run_state == "open", (condition, laps)
        assert computed.state_of("goal") == "runnable", (condition, laps)
    done, _journal = after_laps(plan, laps_to_complete)

    assert done.run_state == "complete", condition
    assert done.state_of("goal") == "settled", condition
    assert done.state_of("outer") == outer_at_the_end, condition


def test_an_outer_loop_asking_for_bound_reached_is_owed_a_lap_exactly_when_the_inner_bound_is_reached():
    """`>= bound` and not `>= bound - 1`, pinned where the threshold shows.

    On a shared `back_to` the inner loop's own demand hides the outer's, so the
    trajectories above stay green under a threshold one lap early; the outer
    row's `required_pass` does not. A mutant that survived the slice review,
    made a witness.
    """
    plan = nested_loops("on_bound_reached", inner_bound=3, outer_bound=3)

    owed = [row_of(after_laps(plan, laps)[0], "outer").required_pass
            for laps in range(4)]

    assert owed == [1, 1, 1, 2], owed


# -- a source no road reaches ---------------------------------------------------


def a_loop_fed_by_a_rootless_loop(condition: str) -> GraphDefinition:
    """`goal -> l`, and a second loop `p` with no road in delivering to `l` on `condition`.

    The grammar admits a loop nobody reaches (`_settle_loops` asks only that
    `back_to` exists and is another step). What such a loop delivers on a
    conditional road is the question: §5.2 defines both of its words over
    arrivals(p), and a step nobody reaches has none.
    """
    return GraphDefinition(
        graph_id="graph-rootless-loop", run_id=RUN_ID, created_at=NOW,
        nodes=(GOAL,
               GraphNode(node_id="p", kind="loop", title="Rootless",
                         loop=GraphLoop(bound=5, back_to="goal")),
               GraphNode(node_id="l", kind="loop", title="Loop",
                         loop=GraphLoop(bound=2, back_to="goal"))),
        edges=(GraphEdge(from_node="goal", to_node="l"),
               GraphEdge(from_node="p", to_node="l", condition=condition)))


def test_a_loop_no_road_reaches_delivers_no_lap_on_a_conditional_road():
    """arrivals(p) is 0 for a loop with no road in, on both of its words.

    Before the arm read its own placeholder: the DEMANDING loop's ceiling stood
    in for arrivals and `on_bound_remaining` delivered `min(2, 4) = 2` laps from
    a loop that had been reached zero times, so `goal` was owed a second pass by
    a road nothing had travelled. The ceiling belongs to the unconditional road
    alone (next test), where its one job is never to bind the `min`.
    """
    remaining, _journal = after_laps(
        a_loop_fed_by_a_rootless_loop("on_bound_remaining"), 1)
    assert remaining.state_of("goal") == "settled"
    assert row_of(remaining, "goal").required_pass == 1
    assert remaining.run_state == "complete", remaining

    reached, _journal = after_laps(
        a_loop_fed_by_a_rootless_loop("on_bound_reached"), 1)
    assert reached.state_of("goal") == "settled"
    assert reached.state_of("l") == "unreachable"
    assert reached.run_state == "complete", reached


def a_note_fed_loop() -> GraphDefinition:
    """A step carrying no work and reached by nothing, on an unconditional road into a loop.

    `work -> gate -> loop[on_changes_requested]`, the loop returning to `work`
    with a bound of three, and a `seed` note with no road in feeding the loop
    unconditionally. The note can never be the slowest road: §5.2 has it stand
    at the demanding loop's ceiling so it never binds the `min`.
    """
    return GraphDefinition(
        graph_id="graph-note-fed", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="seed", kind="task", title="Seed"),
               GraphNode(node_id="work", kind="task", title="Work",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="gate-1"),
               GraphNode(node_id="loop", kind="loop", title="Loop",
                         loop=GraphLoop(bound=3, back_to="work"))),
        edges=(GraphEdge(from_node="seed", to_node="loop"),
               GraphEdge(from_node="work", to_node="gate"),
               GraphEdge(from_node="gate", to_node="loop",
                         condition="on_changes_requested")))


def test_a_note_no_road_reaches_never_binds_the_arrivals_of_the_loop_it_feeds():
    """The unconditional arm: the ceiling stands in, and stands in whole.

    Two mutants survived the slice review -- the ceiling replaced by 0 and by
    1 -- and neither is equivalent: with 0 the note is the slowest road and the
    body is never reopened; with 1 it binds after one lap and the third pass is
    never owed. Three laps of `changes_requested` distinguish both from the
    tree: owed 2, then 3, then the cap and the ending.
    """
    plan = a_note_fed_loop()
    journal = Journal()
    owed = []
    for _lap in range(3):
        journal.did("work")
        journal.decide("gate-1", "request_changes")
        computed = schedule(plan, journal.rows())
        owed.append((row_of(computed, "work").required_pass,
                     computed.state_of("work"), computed.run_state))

    assert owed == [(2, "runnable", "open"), (3, "runnable", "open"),
                    (3, "settled", "complete")], owed


def a_pair_with_different_returns() -> GraphDefinition:
    """`goal -> a -> inner(2, back to a) -> outer(3, back to goal)`."""
    return GraphDefinition(
        graph_id="graph-two-returns", run_id=RUN_ID, created_at=NOW,
        nodes=(GOAL,
               GraphNode(node_id="a", kind="task", title="A",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="inner", kind="loop", title="Inner",
                         loop=GraphLoop(bound=2, back_to="a")),
               GraphNode(node_id="outer", kind="loop", title="Outer",
                         loop=GraphLoop(bound=3, back_to="goal"))),
        edges=(GraphEdge(from_node="goal", to_node="a"),
               GraphEdge(from_node="a", to_node="inner"),
               GraphEdge(from_node="inner", to_node="outer")))


def test_nested_loops_with_different_returns_end_and_the_counts_are_stated():
    """Design §5.2 as written, pinned so it is a fact and not an accident.

    Arrivals count a lap the moment a road delivers, independently of the
    delivering loop settling, so the inner loop's second pass of `a` waits on a
    re-run of `goal`: the run ends with three of each. Not a defect this slice
    introduced or corrected -- stated because the review asked for linked loops
    beyond one shared `back_to`.
    """
    plan = a_pair_with_different_returns()
    journal = Journal()
    for _step in range(12):
        computed = schedule(plan, journal.rows())
        if computed.run_state != "open":
            break
        assert computed.runnable, computed
        journal.did(computed.runnable[0])
    else:
        raise AssertionError("the pair never ended")

    assert computed.run_state == "complete"
    authorized = {}
    for value in journal.rows():
        if type(value).__name__ == "ActionRequest":
            authorized[value.node_id] = authorized.get(value.node_id, 0) + 1
    assert authorized == {"goal": 3, "a": 3}, authorized


# -- the live door ---------------------------------------------------------------


def _live(tmp_path, condition: str | None):
    """The reviewer's plan, landed on a real run through the graph route.

    The acting step is borrowed from a materialized `dalio-v3` so its payload is
    one the argument door admits; the loops and the road under test are drawn
    here. `post_graph` answering 201 for every road is itself the grammar
    control: no condition a loop can produce is refused at publication.
    """
    from tests.test_command_decision_doors import a_planned_run
    from tests.test_command_graph_route import post_graph
    from tests.test_command_http_api import api
    from tests.test_command_schema_doubles import DeepPlanAdapter

    _subject, _store, _events, donor = a_planned_run(tmp_path / "donor")
    goal = next(node for node in donor.nodes if node.node_id == "goal")
    subject, store, events = api(tmp_path / "live", adapters=[DeepPlanAdapter()])
    plan = GraphDefinition(
        graph_id="graph-nested-live", run_id=RUN_ID, created_at=donor.created_at,
        nodes=(goal,
               GraphNode(node_id="inner", kind="loop", title="Inner",
                         loop=GraphLoop(bound=1, back_to="goal")),
               GraphNode(node_id="outer", kind="loop", title="Outer",
                         loop=GraphLoop(bound=2, back_to="goal"))),
        edges=(GraphEdge(from_node="goal", to_node="inner"),
               GraphEdge(from_node="inner", to_node="outer",
                         condition=condition)))
    submitted = plan.as_dict()
    for owned in ("schema_version", "run_id", "created_at"):
        submitted.pop(owned)
    assert post_graph(subject, submitted).status == 201, condition
    return subject, store, events, plan, goal


def _propose_goal_again(subject, goal):
    from tests.test_command_http_api import post, proposal_body

    return post(subject, f"/command/runs/{RUN_ID}/proposals", {
        **proposal_body(), "node_id": "goal", "attempt_id": "attempt-goal-extra",
        "instance_id": goal.instance_id, "capability": goal.capability,
        "arguments": goal.payload()})


@pytest.mark.parametrize("condition, admitted", [
    ("on_bound_remaining", False),
    ("on_bound_reached", True),
    (None, True),
])
def test_the_extra_pass_is_authorized_only_on_a_road_that_really_reopens(
        tmp_path, condition, admitted):
    """The live half: authorize spends the schedule, and the schedule reads the road.

    The propose door holds no schedule check and answers 201 on every road; the
    authorize door is where the plan is a permission. On `on_bound_remaining`
    the extra pass is refused with nothing written after the proposal; on the
    two roads that legitimately reopen the body it is admitted -- the control
    that this is a reading of the road and not a ban on second passes.
    """
    from tests.test_command_decision_doors import refusal_of, settle
    from tests.test_command_http_api import confirm_body, post
    from tests.test_command_run_terminal_doors import journal_bytes

    subject, store, _events, plan, goal = _live(tmp_path, condition)
    settle(store, plan, "goal", index=1)
    values = tuple(row.value for row in store.read(RUN_ID).records)
    assert loop_position(values, plan.nodes[1]) == (1, True)

    proposed = _propose_goal_again(subject, goal)
    assert proposed.status == 201, proposed.payload
    before = journal_bytes(store)
    authorized = post(subject, f"/command/runs/{RUN_ID}/actions",
                      confirm_body(proposed.payload))

    if admitted:
        assert authorized.status == 201, authorized.payload
        assert authorized.payload["node_id"] == "goal"
    else:
        assert authorized.status == ERROR_STATUS["authorization_refused"] == 409
        assert refusal_of(authorized)["code"] == "authorization_refused"
        assert journal_bytes(store) == before
        computed = schedule(plan, values)
        assert computed.run_state == "complete"
        assert computed.state_of("outer") == "unreachable"
