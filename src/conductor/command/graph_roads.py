"""The drawing's own topology: roads in and out, a walk order, and a loop's body.

Split from `graph_schedule` when that module reached the project's line cap,
along the seam the design already draws: everything here is asked of NODES and
EDGES alone. No record is read, no lap is counted, no state is decided -- which
is why a TEMPLATE can be asked the same questions a plan can, one revision
before any run exists, and why `workflow_draft`'s publish-time warning imports
`loop_body` from the schedule's namespace and still gets this answer.

**Nothing sorts, and no `set` reaches an output.** The order is the document's
own -- `definition.nodes` for steps, `definition.edges` for roads -- exactly as
the module this was cut from promises. `loop_body` answers a frozenset because
membership is the only question anybody asks of it.
"""
from __future__ import annotations

from collections.abc import Mapping

from .graph_definition import GraphDefinition, GraphEdge


def _roads(nodes, edges) -> tuple[dict, dict]:
    """Each step's in-edges and out-edges, both in document order.

    Takes the two sequences rather than the document that carries them, so
    a TEMPLATE can be asked the same questions a plan can -- which is what
    the publish-time warning needs, one revision before a plan exists.
    """
    incoming: dict[str, list[GraphEdge]] = {
        node.node_id: [] for node in nodes}
    outgoing: dict[str, list[GraphEdge]] = {
        node.node_id: [] for node in nodes}
    for edge in edges:
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


def loop_body(nodes, edges, loop) -> frozenset[str]:
    """The steps one loop reopens: forward from `back_to`, backward from the loop.

    Both ends inclusive, and over the drawing alone -- no record is read, so
    which steps a loop owns cannot change while a run is in flight.

    Public, and asked of a template as well as of a plan: the publish-time
    warning has to know which steps a loop reopens BEFORE any run exists, and
    a second implementation of "what a loop owns" would be a second answer to
    the question the schedule decides laps by.
    """
    incoming, outgoing = _roads(nodes, edges)
    forward = _reachable(loop.loop.back_to, outgoing, "to_node")
    backward = _reachable(loop.node_id, incoming, "from_node")
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
