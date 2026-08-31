"""What the plan says may happen now, as a pure function of the journal.

`graph_definition` owns what was INTENDED and `graph_projection` owns what was
OBSERVED. This is the third question, and it is the only one that is neither:
given the plan and the records, WHICH steps may run. It is a computation and not
a daemon -- nothing here dispatches, nothing runs on a timer, and the product's
shipped claim that it is not an orchestrator stays true. A computation plus the
refusals that spend it is the whole of *the plan constrains what may run*.

It imports the two contracts and nothing else: no store, no clock, no adapter,
no filesystem. `values` is exactly `tuple(row.value for row in
recovered.records)`, the spelling `graph_runtime` already builds, **in journal
order** -- which the lap arithmetic below depends on and which the store already
fixes and replay already reproduces.

**Nothing sorts, and no `set` reaches an output.** The total order is the
document's own: `definition.nodes` for steps, `definition.edges` for roads. A
test holds this module to zero `sorted(` calls, because an order invented here
would be a second answer to a question the document already settled.

Three ideas carry the whole of it:

- **a step is SETTLED or it is not**, by one rule per kind (§4.1). A road out of
  a settled step is open when its condition equals the one word that step
  produced, closed when it does not, and pending until then. Joins are AND-only:
  every road in must open.
- **a LAP is read off the journal's own order** -- the number of authorizations
  of the loop's `back_to` at or before a record. No record gains a field, and a
  retry inside one lap is not a trip round the loop.
- **reopening is a durable fact of the loop's road actually OPENING**, not of a
  bound being unreached. The earlier reading of this unsettled a body that had
  just been approved, which is the defect the arithmetic here exists to avoid.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    DecisionReceipt,
    gate_decision,
)
from .graph_definition import GraphDefinition, GraphEdge, GraphNode
from .graph_schedule_values import (  # noqa: F401 -- this module's own words
    GATE_ROUTES,
    NODE_SCHEDULE_STATES,
    RUN_SCHEDULE_STATES,
    NodeSchedule,
    RunSchedule,
)

#: The outcomes an `on_failed` road opens on: every terminal answer that is not
#: success and not `unknown`. `unknown` is absent by owner ruling -- it is this
#: product's word for *the journal supports no answer*, and an unanswered
#: question stays askable rather than being routed as a failure.
FAILED_OUTCOMES = frozenset({
    "failed", "cancelled", "rejected", "verification_failed"})


def authorized_attempts(values: tuple[Any, ...], node_id: str) -> int:
    """How many attempts this step has been AUTHORIZED, over the whole run.

    One durable `action_request` row naming the node is one authorization.
    Proposals are not counted: a proposal is a request for an attempt and not an
    attempt, and nothing is spent until a Human confirms one.

    Defined once, here, and spent by both readers -- `_hold_plan_bounds` refuses
    an attempt past the plan's ceiling, and §4's spent arm calls the same step
    `blocked` rather than offering a button that refusal would answer. A second
    spelling would let the hold and the schedule disagree about whether a step
    is spent, which is a screen offering work the runtime will not take.

    It is NOT reset per lap, and that is the shipped meaning of `attempt_bound`:
    a ceiling on the whole run. The publish-time warning is where the
    interaction with a loop's bound is explained.
    """
    return sum(1 for value in values
               if isinstance(value, ActionRequest) and value.node_id == node_id)


def loop_position(values: tuple[Any, ...],
                  node: GraphNode) -> tuple[int, bool]:
    """The trip this run is on, and whether the plan's ceiling is reached.

    Moved here from `graph_projection` so there is ONE owner of the arithmetic
    and no second copy: the projection displays these two numbers and this
    module routes on them, and a display that computed them separately could
    disagree with the routing that acted on them.

    The reading is unchanged, deliberately and to the row: the position is the
    number of distinct attempt identities the loop's `back_to` step was ever
    given, because that step is attempted exactly once per trip. Counting
    attempts across the whole cycle instead scored one pass per acting step of a
    single traversal. The two words this returns are the projection's own and
    are never spelled here -- a module that decides what a run does may not
    reach for a display value, which is why they come back as a pair.

    Args:
        values: The run's record values, in journal order.
        node: The loop node whose position is asked. It carries a `GraphLoop`.

    Returns:
        The position, and whether it has reached the plan's ceiling.
    """
    entered = len({value.attempt_id for value in values
                   if isinstance(value, (ActionProposal, ActionRequest))
                   and value.node_id == node.loop.back_to})
    return entered, entered >= node.loop.bound


def _lap_marks(values: tuple[Any, ...], back_to: str | None) -> tuple[int, ...]:
    """Which lap each record belongs to, read off the journal's own order.

    The lap of a record is the number of authorizations of the loop's `back_to`
    step at or before it -- counting the record itself when it is one -- and
    never less than 1. The first authorization of `back_to` opens lap 1; every
    record between it and the second belongs to lap 1; the second opens lap 2.
    Records written before any authorization of `back_to` are lap 1 by the
    clamp, which is what makes a plain top-to-bottom traversal one lap.

    Nothing is stored and no record gains a field. The lap is a fact of the
    order the store already fixes and replay already reproduces, so two readers
    of one journal can never disagree about it.

    `back_to` of None is the frame of a step in no loop body: every record is
    lap 1, and the whole lap machinery collapses to "once".
    """
    marks: list[int] = []
    seen = 0
    for value in values:
        if back_to is not None and isinstance(value, ActionRequest) \
                and value.node_id == back_to:
            seen += 1
        marks.append(max(seen, 1))
    return tuple(marks)


@dataclass(frozen=True)
class _Plan:
    """The frozen facts every question below is asked against, bundled once."""

    run_id: str
    values: tuple[Any, ...]
    by_id: Mapping[str, GraphNode]
    incoming: Mapping[str, tuple[GraphEdge, ...]]


@dataclass(frozen=True)
class _Frame:
    """One loop's lap partition, and the ceiling its arithmetic is capped by."""

    marks: tuple[int, ...]
    ceiling: int


def _roads(definition: GraphDefinition) -> tuple[dict, dict]:
    """Each step's in-edges and out-edges, both in `definition.edges` order."""
    incoming: dict[str, list[GraphEdge]] = {
        node.node_id: [] for node in definition.nodes}
    outgoing: dict[str, list[GraphEdge]] = {
        node.node_id: [] for node in definition.nodes}
    for edge in definition.edges:
        incoming[edge.to_node].append(edge)
        outgoing[edge.from_node].append(edge)
    return ({key: tuple(rows) for key, rows in incoming.items()},
            {key: tuple(rows) for key, rows in outgoing.items()})


def _walk_order(definition: GraphDefinition,
                incoming: Mapping[str, tuple[GraphEdge, ...]]) -> tuple[str, ...]:
    """Every step once, predecessors first, ties broken by document order.

    An explicit stack rather than recursion, for `_acyclic`'s reason one module
    over: a plan's depth is the caller's, and a walk that can exhaust the
    interpreter's stack is a refusal this contract never wrote. The edge set is
    already proved a DAG before this runs, so the walk terminates by
    construction and there is no cycle arm here to be dead code.
    """
    placed: list[str] = []
    seen: set[str] = set()
    for node in definition.nodes:
        if node.node_id in seen:
            continue
        seen.add(node.node_id)
        stack = [(node.node_id, iter(incoming[node.node_id]))]
        while stack:
            node_id, roads = stack[-1]
            edge = next(roads, None)
            if edge is None:
                placed.append(node_id)
                stack.pop()
            elif edge.from_node not in seen:
                seen.add(edge.from_node)
                stack.append((edge.from_node, iter(incoming[edge.from_node])))
    return tuple(placed)


def _auto_settling(node: GraphNode) -> bool:
    """Whether this step delivers its lap by arriving rather than by working.

    A loop node and a task carrying no capability are both carried out by
    nobody: no adapter runs them, no receipt is ever written for them, and no
    Human answers them. So they have no settling fact to count, and they settle
    exactly when every road into them is open. Counting laps for them instead
    would deadlock the second lap of every body they sit in.
    """
    return node.loop is not None or (
        node.kind == "task" and node.capability is None)


def _settling_receipts(plan: _Plan, node: GraphNode) -> tuple[int, ...]:
    """The journal positions of the facts that settle this step.

    A task with a capability is settled by a terminal result for a request that
    names it, whose outcome is not `unknown`; a gate by a decision in this run
    naming its `gate_id`. Positions rather than records, so the caller can ask
    which lap each fact fell in without this function knowing about laps.
    """
    if node.kind == "gate":
        return tuple(
            index for index, value in enumerate(plan.values)
            if isinstance(value, DecisionReceipt)
            and value.run_id == plan.run_id and value.gate_id == node.gate_id)
    actions = {value.action_id for value in plan.values
               if isinstance(value, ActionRequest)
               and value.node_id == node.node_id}
    return tuple(
        index for index, value in enumerate(plan.values)
        if isinstance(value, ActionResultReceipt)
        and value.action_id in actions and value.outcome != "unknown")


def _settled_laps(plan: _Plan, node: GraphNode, frame: _Frame) -> int:
    """How many distinct laps this step has answered.

    Lap-partitioned rather than a plain count, and that is the whole of what
    stops a retry inside one lap from pre-paying the next: a superseding
    decision written before the loop was reopened replaces that lap's answer and
    adds no lap, because correcting a mistake is not a trip round the cycle.
    """
    return len({frame.marks[index] for index in _settling_receipts(plan, node)})


def _produced_word(plan: _Plan, node: GraphNode) -> str | None:
    """The ONE word a settled step produces, or None when it produces none.

    A gate routes through `GATE_ROUTES` and through nothing else. A task with a
    capability produces success or failure from its standing terminal outcome. A
    loop produces its own position against its own ceiling. A task carrying no
    capability produces nothing at all, which is why the contract refuses a
    condition on any road out of one.
    """
    if node.kind == "gate":
        return GATE_ROUTES[_gate_state(plan, node.gate_id)]
    if node.loop is not None:
        _position, reached = loop_position(plan.values, node)
        return "on_bound_reached" if reached else "on_bound_remaining"
    if node.capability is None:
        return None
    standing = _standing_outcome(plan, node)
    if standing is None or standing == "unknown":
        return None
    return "on_succeeded" if standing == "succeeded" else "on_failed"


def _gate_state(plan: _Plan, gate_id: str) -> str:
    """What this gate is, through the one function that already decides it.

    `unknown` for a journal holding two standing decisions, exactly as
    `graph_projection` answers: the plan cannot say which is current, so neither
    does this, and a gate in that state is not settled at all.
    """
    receipts = [value for value in plan.values
                if isinstance(value, DecisionReceipt)]
    try:
        return gate_decision(receipts, plan.run_id, gate_id)
    except ContractError:
        return "unknown"


def _standing_outcome(plan: _Plan, node: GraphNode) -> str | None:
    """The outcome of the LAST terminal result written for this step."""
    positions = _settling_receipts(plan, node)
    if not positions:
        return None
    return plan.values[positions[-1]].outcome


def _routed_count(plan: _Plan, node: GraphNode, condition: str | None,
                  frame: _Frame) -> int:
    """How many laps have delivered this word at this step.

    The reopening trigger, per road. An unconditional road delivers whatever the
    step delivered; a conditional one delivers only the laps whose LAST answer
    routed to its word, which is what makes a retraction inside a lap a
    correction rather than a trip.

    A step that settles by arriving is answered by its own arrivals, whatever
    the road says: it produces one word per lap and could not have delivered a
    different number of them on a conditional road than on a plain one. That
    also covers every loop node, so there is deliberately no fourth arm here for
    one -- a branch nothing can reach is a branch nothing can prove.
    """
    if _auto_settling(node):
        return _arrivals(plan, node, frame) if plan.incoming[node.node_id] \
            else frame.ceiling
    if condition is None:
        return _settled_laps(plan, node, frame)
    return len(_lapsed_words(plan, node, frame, condition))


def _lapsed_words(plan: _Plan, node: GraphNode, frame: _Frame,
                  condition: str) -> set[int]:
    """The laps whose LAST settling fact at this step routed to `condition`."""
    last: dict[int, int] = {}
    for index in _settling_receipts(plan, node):
        last[frame.marks[index]] = index
    delivered = set()
    for lap, index in last.items():
        value = plan.values[index]
        if isinstance(value, DecisionReceipt):
            word = GATE_ROUTES[_gate_state_at(plan, node, index)]
        else:
            word = ("on_succeeded" if value.outcome == "succeeded"
                    else "on_failed" if value.outcome in FAILED_OUTCOMES
                    else None)
        if word == condition:
            delivered.add(lap)
    return delivered


def _gate_state_at(plan: _Plan, node: GraphNode, index: int) -> str:
    """What this gate stood at, judged over the journal up to and including a row.

    Asked of a PREFIX rather than of one receipt, because a receipt does not
    answer for itself: what a gate says is whichever of its receipts nothing has
    superseded, and that is a fact of the records around it.
    """
    receipts = [value for value in plan.values[:index + 1]
                if isinstance(value, DecisionReceipt)]
    try:
        return gate_decision(receipts, plan.run_id, node.gate_id)
    except ContractError:
        return "unknown"


def _arrivals(plan: _Plan, node: GraphNode, frame: _Frame) -> int:
    """How many laps have reached this step by EVERY road into it.

    A `min`, because joins are AND-only: a step is reached on its second lap
    only once every road into it has delivered twice.

    A step with no road in has arrived zero times. That answer is the `min`'s
    own totality and not a branch, because it could never be observed: a loop
    with no road into it lies in nobody's body -- `body` intersects with what
    reaches the loop, and nothing reaches it -- so whatever it demanded would be
    demanded of no step at all. Written as a default rather than as an arm, so
    there is no constant here that a reader could believe was load-bearing.
    """
    return min((_routed_count(plan, plan.by_id[edge.from_node],
                              edge.condition, frame)
                for edge in plan.incoming[node.node_id]), default=0)


def _body(plan: _Plan, outgoing: Mapping[str, tuple[GraphEdge, ...]],
          loop: GraphNode) -> frozenset[str]:
    """The steps one loop reopens: forward from `back_to`, backward from the loop.

    Both ends inclusive, and over the immutable plan alone -- no record is read,
    so which steps a loop owns is a property of the drawing and cannot change
    while a run is in flight.
    """
    forward = _reachable(loop.loop.back_to, outgoing, "to_node")
    backward = _reachable(loop.node_id, plan.incoming, "from_node")
    return forward & backward


def _reachable(start: str, roads: Mapping[str, tuple[GraphEdge, ...]],
               following: str) -> frozenset[str]:
    """Every step reachable from one, along whichever end of the road is named."""
    found = {start}
    stack = [start]
    while stack:
        for edge in roads[stack.pop()]:
            beyond = getattr(edge, following)
            if beyond not in found:
                found.add(beyond)
                stack.append(beyond)
    return frozenset(found)


def _lap_demands(definition: GraphDefinition, plan: _Plan,
                 outgoing: Mapping[str, tuple[GraphEdge, ...]]) -> tuple[dict, dict]:
    """Which lap each step owes, and the lap frame that question was asked in.

    A step outside every loop body owes one pass, in the frame where every
    record is lap 1. A step inside one owes `1 + arrivals(loop)`, capped by the
    loop's own bound -- so the ceiling is never exceeded whatever the roads say,
    and the invariant `1 <= required_pass <= bound` holds by construction.

    A step inside several bodies takes the loop demanding the most, and a tie
    goes to the loop standing earlier in `definition.nodes`: loops are walked in
    document order and a later one must strictly beat the standing answer.
    """
    plain = _Frame(marks=_lap_marks(plan.values, None), ceiling=0)
    owed = {node.node_id: 1 for node in definition.nodes}
    frames = {node.node_id: plain for node in definition.nodes}
    for loop in definition.nodes:
        if loop.loop is None:
            continue
        frame = _Frame(marks=_lap_marks(plan.values, loop.loop.back_to),
                       ceiling=loop.loop.bound)
        demand = min(1 + _arrivals(plan, loop, frame), loop.loop.bound)
        for node_id in _body(plan, outgoing, loop):
            if demand > owed[node_id]:
                owed[node_id] = demand
                frames[node_id] = frame
    return owed, frames


def _edge_state(edge: GraphEdge, settled: Mapping[str, bool],
                words: Mapping[str, str | None]) -> str:
    """Whether one road is open, closed, or still pending.

    Pending until the step behind it settles; then open when the road names no
    condition or names the one word that step produced, and closed otherwise. A
    closed road is a branch that was not taken, and it dead-ends whatever stands
    beyond it.
    """
    if not settled[edge.from_node]:
        return "pending"
    if edge.condition is None or edge.condition == words[edge.from_node]:
        return "open"
    return "closed"


def _is_settled(plan: _Plan, node: GraphNode, frame: _Frame, owed: int,
                roads: Mapping[str, str]) -> bool:
    """The ONE settled-ness rule, by kind, with no second definition anywhere.

    An auto-settling step settles when every road into it is open: it satisfies
    its lap by construction and never by count. A gate settles when it is in one
    of the four DECIDED states -- `idle` and `unknown` are not answers -- and has
    answered every lap it owes. A task with a capability settles on the count
    alone.
    """
    if _auto_settling(node):
        return all(roads[_road_key(edge)] == "open"
                   for edge in plan.incoming[node.node_id])
    if node.kind == "gate" and GATE_ROUTES[_gate_state(plan, node.gate_id)] is None:
        return False
    return _settled_laps(plan, node, frame) >= owed


def _road_key(edge: GraphEdge) -> tuple[str, str]:
    """One road's identity. The document already refuses a repeated pair."""
    return (edge.from_node, edge.to_node)


def _node_state(plan: _Plan, node: GraphNode, settled: bool, spent: bool,
                roads: Mapping[str, str], states: Mapping[str, str]) -> str:
    """Where one step stands, asked in the one order the answers permit.

    Settled first: a settled step is settled whatever its roads now say, which
    is what stops an approved body being un-approved by a later branch. Then
    unreachable, because a closed road or a dead predecessor ends the matter.
    Then spent, because a step that can never settle again must not be offered
    as runnable -- that would be a button `authorize` is bound to refuse. Then
    runnable, which needs EVERY road in to be open.
    """
    if settled:
        return "settled"
    ways = plan.incoming[node.node_id]
    if any(roads[_road_key(edge)] == "closed" for edge in ways) or any(
            states[edge.from_node] == "unreachable" for edge in ways):
        return "unreachable"
    if spent:
        return "blocked"
    if all(roads[_road_key(edge)] == "open" for edge in ways):
        return "runnable"
    return "blocked"


def _spent(plan: _Plan, node: GraphNode) -> bool:
    """Whether this step has authorized every attempt the plan allows it."""
    if node.attempt_bound is None or node.capability is None:
        return False
    return authorized_attempts(plan.values, node.node_id) >= node.attempt_bound


def _run_state(rows: tuple[NodeSchedule, ...]) -> str:
    """The plan's own word, and there is no fourth one.

    `complete` means nothing is runnable and nothing is still owed -- never that
    the run succeeded. `stalled` means nothing is runnable and something is
    still owed, which is exactly what a spent step leaves behind.

    The design also asked that `settled` be non-empty before `complete` is said,
    and that condition is PROVED here rather than checked: a graph carries at
    least one step, its edges are a DAG, so some step has no road into it -- and
    a step with no road in can be neither closed nor reached through anything
    unreachable, so it is never `unreachable`. If nothing is runnable and
    nothing is blocked, that step is settled. A condition that cannot be false
    is a guard nothing could ever show failing, so it is a test's claim and not
    a branch here.
    """
    states = tuple(row.state for row in rows)
    if "runnable" in states:
        return "open"
    return "complete" if "blocked" not in states else "stalled"


def schedule(definition: GraphDefinition,
             values: tuple[Any, ...]) -> RunSchedule:
    """What this plan says may happen now, given this run's records.

    Pure, and a pure function of two frozen things: the run's immutable plan and
    the records it already holds, in journal order. Identical bytes therefore
    compute an identical verdict, which is what lets a recorded ending be judged
    again on replay against the very journal that produced it.

    Args:
        definition: The run's immutable plan.
        values: The run's record values, oldest first.

    Returns:
        Every step's standing, the three subsets a reader acts on, and the
        plan's own word for the run.
    """
    incoming, outgoing = _roads(definition)
    plan = _Plan(run_id=definition.run_id, values=values,
                 by_id={node.node_id: node for node in definition.nodes},
                 incoming=incoming)
    owed, frames = _lap_demands(definition, plan, outgoing)
    words = {node.node_id: _produced_word(plan, node)
             for node in definition.nodes}
    rows = _walked_states(definition, plan, outgoing, owed, frames, words)
    ordered = tuple(rows[node.node_id] for node in definition.nodes)
    return RunSchedule(
        run_id=definition.run_id, graph_id=definition.graph_id, nodes=ordered,
        runnable=_subset(ordered, "runnable"),
        settled=_subset(ordered, "settled"),
        unreachable=_subset(ordered, "unreachable"),
        run_state=_run_state(ordered))


def _walked_states(definition: GraphDefinition, plan: _Plan,
                   outgoing: Mapping[str, tuple[GraphEdge, ...]],
                   owed: Mapping[str, int], frames: Mapping[str, _Frame],
                   words: Mapping[str, str | None]) -> dict[str, NodeSchedule]:
    """One forward pass, predecessors first, settling each step as it is reached."""
    settled: dict[str, bool] = {}
    states: dict[str, str] = {}
    roads: dict[tuple[str, str], str] = {}
    rows: dict[str, NodeSchedule] = {}
    for node_id in _walk_order(definition, plan.incoming):
        node = plan.by_id[node_id]
        for edge in plan.incoming[node_id]:
            roads[_road_key(edge)] = _edge_state(edge, settled, words)
        settled[node_id] = _is_settled(
            plan, node, frames[node_id], owed[node_id], roads)
        spent = _spent(plan, node)
        states[node_id] = _node_state(
            plan, node, settled[node_id], spent, roads, states)
        rows[node_id] = NodeSchedule(
            node_id=node_id, state=states[node_id],
            opened_by=_by_state(plan, node_id, roads, "open"),
            blocked_by=_by_state(plan, node_id, roads, "pending"),
            closed_by=_by_state(plan, node_id, roads, "closed"),
            opens=tuple((edge.to_node, edge.condition)
                        for edge in outgoing[node_id]),
            required_pass=owed[node_id],
            settled_laps=0 if _auto_settling(node) else _settled_laps(
                plan, node, frames[node_id]),
            attempts_spent=spent)
    return rows


def _by_state(plan: _Plan, node_id: str, roads: Mapping[tuple[str, str], str],
              wanted: str) -> tuple[str, ...]:
    """The predecessors whose road into this step is in one state, in edge order."""
    return tuple(edge.from_node for edge in plan.incoming[node_id]
                 if roads[_road_key(edge)] == wanted)


def _subset(rows: tuple[NodeSchedule, ...], wanted: str) -> tuple[str, ...]:
    """One state's steps, in the plan's own node order."""
    return tuple(row.node_id for row in rows if row.state == wanted)
