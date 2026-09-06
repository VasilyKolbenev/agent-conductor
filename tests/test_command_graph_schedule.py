"""What the plan says may happen now, driven over journals it must answer for.

The schedule is a pure function of two frozen things, so every witness here is
built by handing it a plan and a list of record values in journal order. No
store, no clock, no adapter: if a verdict here is wrong, it is wrong in the
arithmetic and nowhere else. The journals come from
`tests/schedule_journal.py`, shared with the lap module next door.

The §5 arithmetic -- lap index, arrivals, `required_pass`, the reopening trigger
and the three walk-throughs -- is `test_command_schedule_laps.py`, split off
when this module crossed the line cap. What stays here is everything that is
true of a single pass:

- **the vocabularies**, closed against the layers that own them: `GATE_ROUTES`
  against `contracts.gate_decision` driven over all four decision actions, and
  `RUN_SCHEDULE_STATES` against the durable `TERMINAL_STATES`.
- **routing**, per condition word: each of the eight opens its own road and
  closes every other, driven through `materialize` from a template so the road
  from a drawing to a verdict is the one a person actually walks.
- **joins**, which are AND-only, and the two states a gate can be in that are
  not answers at all.
- **the two extracted arithmetics**, `loop_position` and `authorized_attempts`,
  each held to the reader it was taken from.
- **order**, proved by two plans that differ only in the order of two roads, and
  pinned by construction: the emitting modules call `sorted` nowhere and no
  `set` reaches either answer shape.
"""
from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import pytest

from conductor.command import graph_schedule
from conductor.command.contracts import (
    DecisionReceipt,
    _DECISION_ACTIONS,
    _RESULT_OUTCOMES,
    gate_decision,
)
from conductor.command.graph_conditions import (
    EDGE_CONDITIONS,
    _CONDITIONS_BY_KIND,
)
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
)
from conductor.command.graph_projection import GATE_STATES
from conductor.command.graph_schedule import (
    FAILED_OUTCOMES,
    authorized_attempts,
    loop_position,
    schedule,
)
from conductor.command.graph_schedule_values import (
    GATE_ROUTES,
    NODE_SCHEDULE_STATES,
    RUN_SCHEDULE_STATES,
    NodeSchedule,
    RunSchedule,
)
from conductor.command.graph_template import (
    GraphTemplate,
    RunBinding,
    TemplateNode,
    materialize,
)
from conductor.command.run_terminal import TERMINAL_STATES
from tests.schedule_journal import (
    DIGEST,
    NOW,
    RUN_ID,
    SOLO,
    Journal,
    a_bounded_plan,
    loop_of,
    routed_dalio,
    row_of,
    through_the_body,
)


# -- the vocabularies, closed against the layers that own them -----------------


def test_every_gate_state_routes_and_the_map_is_the_projections_own():
    assert set(GATE_ROUTES) == set(GATE_STATES)
    assert len(GATE_ROUTES) == 6


@pytest.mark.parametrize("action", sorted(_DECISION_ACTIONS))
def test_each_decision_action_routes_to_the_word_its_gate_state_names(action):
    """Derived by asking `gate_decision`, never by copying its table."""
    receipt = DecisionReceipt(
        receipt_id="decision-1", run_id=RUN_ID, gate_id="gate-1", action=action,
        actor="operator", decided_at=NOW, reason="stated", scope_refs=("docs",),
        config_digest=DIGEST)
    state = gate_decision([receipt], RUN_ID, "gate-1")

    assert GATE_ROUTES[state] is not None
    assert GATE_ROUTES[state] in EDGE_CONDITIONS


def test_the_two_states_that_are_not_answers_route_to_nothing():
    """`idle` is no receipt and `unknown` is two; neither is a decision."""
    assert GATE_ROUTES["idle"] is None
    assert GATE_ROUTES["unknown"] is None
    assert sum(1 for word in GATE_ROUTES.values() if word is None) == 2


def test_every_gate_word_is_one_the_edge_vocabulary_carries():
    routed = {word for word in GATE_ROUTES.values() if word is not None}

    assert routed <= EDGE_CONDITIONS
    assert len(routed) == 4


def test_the_run_words_are_the_durable_endings_plus_the_one_that_is_not():
    """`open` is never durable, and the rest of this tuple IS the record's own
    vocabulary -- so a fourth run word could not be added to one alone."""
    assert set(RUN_SCHEDULE_STATES) - {"open"} == set(TERMINAL_STATES)
    assert "open" not in TERMINAL_STATES
    assert len(RUN_SCHEDULE_STATES) == 3


def test_the_failed_road_carries_every_terminal_outcome_but_success_and_unknown():
    assert FAILED_OUTCOMES == set(_RESULT_OUTCOMES) - {"succeeded", "unknown"}


# -- routing: each word opens its own road and closes the others ---------------


def a_routed_template(kind: str, condition: str) -> GraphTemplate:
    """One source of the named kind, two roads out, one carrying `condition`.

    The loop variant deliberately carries NO road from `seed` into the loop.
    An unconditional road into a loop node means every lap of the step behind it
    has arrived, so the body would immediately owe a second pass and the loop
    could never settle -- which is the shipped `dalio-v2` sink and is exactly
    what revision 3 adds a condition to fix. Here the question is routing, so
    the loop is reached by no road and its position is read off `seed`, which it
    reopens.
    """
    roads = [GraphEdge(from_node="seed", to_node="source")]
    if kind == "gate":
        source = TemplateNode(node_id="source", kind="gate", title="Gate",
                              gate_id="gate-1")
    elif kind == "loop":
        source = TemplateNode(node_id="source", kind="loop", title="Loop",
                              loop=GraphLoop(bound=2, back_to="seed"))
        roads = []
    else:
        source = TemplateNode(node_id="source", kind="task", title="Task",
                              role_id="doer", capability="review")
    return GraphTemplate(
        template_id="routed", revision=1, title="Routed",
        nodes=(TemplateNode(node_id="seed", kind="task", title="Seed",
                            role_id="doer", capability="review"),
               source,
               TemplateNode(node_id="taken", kind="task", title="Taken"),
               TemplateNode(node_id="other", kind="task", title="Other"),
               TemplateNode(node_id="beyond", kind="task", title="Beyond")),
        edges=(*roads,
               GraphEdge(from_node="source", to_node="taken",
                         condition=condition),
               GraphEdge(from_node="source", to_node="other",
                         condition=_sibling(kind, condition)),
               GraphEdge(from_node="other", to_node="beyond")))


def _sibling(kind: str, condition: str) -> str:
    """Another word the same kind can produce, so the roads are comparable."""
    family = sorted(_CONDITIONS_BY_KIND[kind])
    return next(word for word in family if word != condition)


def _delivers(kind: str, condition: str) -> Journal:
    """A journal in which `source` produces exactly the word `condition`."""
    journal = Journal()
    if kind == "gate":
        journal.did("seed")
        action = {"on_approved": "approve", "on_rejected": "reject",
                  "on_changes_requested": "request_changes",
                  "on_waived": "waive"}[condition]
        journal.decide("gate-1", action)
    elif kind == "loop":
        journal.did("seed")
        if condition == "on_bound_reached":
            journal.did("seed")
    else:
        journal.did("seed")
        journal.did("source",
                    "succeeded" if condition == "on_succeeded" else "failed")
    return journal


@pytest.mark.parametrize("kind, condition", [
    (kind, word)
    for kind, words in sorted(_CONDITIONS_BY_KIND.items())
    for word in sorted(words)])
def test_each_condition_opens_its_own_road_and_closes_every_other(kind, condition):
    """All eight words, driven from a drawn template through materialization.

    `beyond` is the propagation half: its own road was never closed -- it is
    merely waiting on a step that can never settle -- so a rule that looked only
    at closed roads would call it blocked and offer it as work one day.
    """
    plan = materialize(
        a_routed_template(kind, condition),
        RunBinding(assignments={"doer": "solo"}), SOLO,
        graph_id="graph-routed", run_id=RUN_ID, created_at=NOW)

    computed = schedule(plan, _delivers(kind, condition).rows())

    assert row_of(computed, "taken").opened_by == ("source",)
    assert row_of(computed, "other").closed_by == ("source",)
    assert computed.state_of("other") == "unreachable"
    assert computed.state_of("taken") in {"runnable", "settled"}
    assert row_of(computed, "beyond").closed_by == ()
    assert computed.state_of("beyond") == "unreachable"


def test_a_closed_road_dead_ends_everything_beyond_it():
    """Closure propagates: an unreachable step makes its successors unreachable."""
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "approve")

    computed = schedule(plan, journal.rows())

    assert row_of(computed, "retry-loop").closed_by == ("result-gate",)
    assert computed.unreachable == ("retry-loop",)


# -- joins are AND-only, and a gate with no answer settles nothing -------------


def a_join(condition: str | None = None) -> GraphDefinition:
    """Two independent roads into one step."""
    return GraphDefinition(
        graph_id="graph-join", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(node_id="left", kind="task", title="Left",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="right", kind="task", title="Right",
                         instance_id="solo", capability="review"),
               GraphNode(node_id="join", kind="task", title="Join",
                         instance_id="solo", capability="review")),
        edges=(GraphEdge(from_node="left", to_node="join", condition=condition),
               GraphEdge(from_node="right", to_node="join", condition=condition)))


def test_one_open_road_into_a_join_is_not_enough():
    """AND-only: a step at a join waits for ALL of them, never for any of them."""
    journal = Journal()
    journal.did("left")

    computed = schedule(a_join(), journal.rows())

    assert computed.state_of("join") == "blocked"
    assert row_of(computed, "join").opened_by == ("left",)
    assert row_of(computed, "join").blocked_by == ("right",)


def test_a_join_opens_when_every_road_into_it_has_opened():
    journal = Journal()
    journal.did("left")
    journal.did("right")

    computed = schedule(a_join(), journal.rows())

    assert computed.state_of("join") == "runnable"
    assert row_of(computed, "join").opened_by == ("left", "right")
    assert row_of(computed, "join").blocked_by == ()


def test_a_gate_nobody_answered_is_not_settled_and_blocks_rather_than_closes():
    """`idle` is not a decision, so the road behind it is pending, not closed --
    a question nobody asked is not a question answered no."""
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    for node_id in ("identify", "diagnose", "design"):
        journal.did(node_id)

    computed = schedule(plan, journal.rows())

    assert computed.state_of("confirm-gate") == "runnable"
    assert computed.state_of("do") == "blocked"
    assert row_of(computed, "do").blocked_by == ("confirm-gate",)
    assert "do" not in computed.unreachable


def test_a_gate_holding_two_standing_answers_is_not_settled_either():
    """`unknown` is the journal supporting two answers, so it supports neither."""
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    for node_id in ("identify", "diagnose", "design"):
        journal.did(node_id)
    journal.decide("gate-confirm-do", "approve")
    journal.decide("gate-confirm-do", "reject", supersede=False)

    computed = schedule(plan, journal.rows())

    assert computed.state_of("confirm-gate") == "runnable"
    assert computed.state_of("do") == "blocked"
    assert row_of(computed, "do").blocked_by == ("confirm-gate",)


# -- the two extracted arithmetics ---------------------------------------------


def test_the_projection_reads_its_position_from_the_one_owner(tmp_path):
    """Witness: the numbers did not move when the arithmetic moved.

    Asserted against the projection's own published row rather than against a
    copy of the formula, so this reds if either reader drifts from the other.
    """
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    rows = journal.rows()
    loop = loop_of(plan)

    assert loop_position(rows, loop) == (1, False)
    assert graph_schedule.loop_position(rows, loop) == loop_position(rows, loop)


def test_a_proposal_alone_moves_the_position_exactly_as_it_always_did():
    """The position counts attempt IDENTITIES over proposals and requests, which
    is the shipped reading and is not the same question as an authorization."""
    plan = routed_dalio()
    journal = Journal()
    journal.propose("identify", attempt="attempt-x")

    assert loop_position(journal.rows(), loop_of(plan)) == (1, False)
    assert authorized_attempts(journal.rows(), "identify") == 0


def test_authorized_attempts_counts_rows_and_never_identities():
    """Witness 20: one ROW is one authorization, over a journal with a retry
    inside one lap -- three confirmations under one attempt id are three."""
    journal = Journal()
    for _ in range(3):
        journal.request("do", attempt="attempt-shared")

    assert authorized_attempts(journal.rows(), "do") == 3
    assert authorized_attempts(journal.rows(), "elsewhere") == 0


def test_the_hold_and_the_schedule_count_the_same_journal_identically(tmp_path):
    """The two readers of one number, driven over the same records.

    A second spelling would let the refusal and the screen disagree about
    whether a step is spent, which is a screen offering work the runtime will
    not take.
    """
    journal = Journal()
    journal.decide("gate-1", "approve")
    journal.request("do")
    rows = journal.rows()

    computed = schedule(a_bounded_plan(1), rows)

    assert authorized_attempts(rows, "do") == 1
    assert row_of(computed, "do").attempts_spent is True


# -- order is the document's own, and nothing invents one ----------------------


def test_two_plans_differing_only_in_edge_order_answer_in_their_own_order():
    """Witness 8. A sort would have made these two answer alike."""
    nodes = (GraphNode(node_id="seed", kind="task", title="Seed",
                       instance_id="solo", capability="review"),
             GraphNode(node_id="alpha", kind="task", title="Alpha",
                       instance_id="solo", capability="review"),
             GraphNode(node_id="beta", kind="task", title="Beta",
                       instance_id="solo", capability="review"))
    roads = (GraphEdge(from_node="seed", to_node="alpha"),
             GraphEdge(from_node="seed", to_node="beta"))
    journal = Journal()
    journal.did("seed")

    forward = schedule(GraphDefinition(
        graph_id="g", run_id=RUN_ID, created_at=NOW, nodes=nodes,
        edges=roads), journal.rows())
    reversed_roads = schedule(GraphDefinition(
        graph_id="g", run_id=RUN_ID, created_at=NOW, nodes=nodes,
        edges=roads[::-1]), journal.rows())

    assert row_of(forward, "seed").opens == (("alpha", None), ("beta", None))
    assert row_of(reversed_roads, "seed").opens == (("beta", None), ("alpha", None))
    assert forward.runnable == reversed_roads.runnable == ("alpha", "beta")


def test_the_subsets_are_in_the_plans_own_node_order():
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "approve")

    computed = schedule(plan, journal.rows())
    planned = [node.node_id for node in plan.nodes]

    assert list(computed.settled) == [
        name for name in planned if name in set(computed.settled)]
    assert [row.node_id for row in computed.nodes] == planned


def test_the_schedule_never_sorts_and_never_answers_with_a_set():
    """The style pin, held by construction and in both directions.

    A `sorted(` anywhere in the emitting module would be a second answer to an
    order the document already fixed; a `set` on either answer shape would have
    destroyed it outright.
    """
    for module in (graph_schedule, __import__(
            "conductor.command.graph_schedule_values", fromlist=["x"]),
            __import__("conductor.command.graph_roads", fromlist=["x"])):
        source = Path(module.__file__).read_text(encoding="utf-8")
        called = {node.func.id for node in ast.walk(ast.parse(source))
                  if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name)}
        assert "sorted" not in called, module.__name__
    shapes = [field.type for shape in (NodeSchedule, RunSchedule)
              for field in fields(shape)]
    assert not [name for name in shapes if "set" in name]
    assert all(isinstance(getattr(row, name), tuple)
               for row in (NodeSchedule(
                   node_id="n", state="blocked", opened_by=(), blocked_by=(),
                   closed_by=(), opens=(), required_pass=1, settled_laps=0,
                   attempts_spent=False, awaiting_artifacts=()),)
               for name in ("opened_by", "blocked_by", "closed_by", "opens",
                            "awaiting_artifacts"))


def test_every_state_a_step_can_hold_is_one_of_the_four_words():
    plan = routed_dalio()
    journal = Journal()
    journal.did("goal")
    through_the_body(journal)
    journal.decide("gate-result", "approve")

    computed = schedule(plan, journal.rows())

    assert {row.state for row in computed.nodes} <= set(NODE_SCHEDULE_STATES)
    assert computed.run_state in RUN_SCHEDULE_STATES


def test_a_step_the_plan_does_not_carry_is_somewhere_the_plan_cannot_reach():
    computed = schedule(routed_dalio(), ())

    assert computed.state_of("nowhere") == "unreachable"
    assert computed.state_of("goal") == "runnable"
