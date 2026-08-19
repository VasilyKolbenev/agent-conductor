"""What a run was OBSERVED to do, computed from the records it already holds.

``graph_definition`` next door owns what was INTENDED. This module owns the
other half, and it is a COMPUTATION over the journal rather than a second
durable record. A stored projection is a copy that can come to disagree with
the facts it was copied from; a computed one cannot, and it costs one pass over
records the read has already replayed.

The two halves share no vocabulary by construction. Every word a node carries
here is a word the definition REFUSES as a field name
(:data:`~conductor.command.graph_definition.RUNTIME_ONLY_FIELDS`), and the one
name they share is ``node_id``, which is the join and nothing else. So no
reader can take a plan for a position: the ceiling is ``loop.bound`` over
there, the position is ``pass`` here.

What never reaches this projection: raw adapter output, filesystem paths,
tokens, vendor prose, recovery references, and any record body at all. Every
value below is an identifier, a word from a closed vocabulary, a count, or a
timestamp some contract already validated. A consumer that wants a record reads
it from the run's own ``records``, which is the same authoritative bytes.

An action that names no node is not projected. A graph does not make every
action part of it, and giving an unbound action a home would be this
computation deciding a fact the plan never stated.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .attempts import AttemptEvent
from .contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    DecisionReceipt,
    gate_decision,
)
from .graph_definition import GraphDefinition, GraphEdge, GraphNode

if TYPE_CHECKING:  # pragma: no cover -- import cycle avoided at runtime
    from .run_store import RecoveredRun

#: How far a node's own durable records carry it, in the order they can only
#: happen: a proposal, the request a Human confirmed from it, the lease an
#: attempt took, and the observation that ended it. Acceptance is NOT success --
#: ``observed`` says a boundary was reached, and ``outcome`` says what came of
#: it, from the immutable result record and from nothing else (safety law 9).
NODE_PHASES = ("idle", "proposed", "requested", "running", "observed")

#: What a gate is. The first five are ``contracts.gate_decision``'s own answers
#: and are not restated here -- a test holds this tuple to that function over
#: every decision action. ``unknown`` is this projection's own word for a
#: journal that holds more than one standing decision for one gate: the plan
#: cannot say which is current, so neither does this.
GATE_STATES = (
    "idle", "satisfied", "failed", "changes_requested", "waived", "unknown")


def graph_payload(recovered: "RecoveredRun") -> dict[str, Any]:
    """The whole graph half of a run read: the plan, its digest, and the run.

    A run that follows no graph answers three nulls rather than an absent key,
    because a reader that has to tell "no graph" from "old server" by the shape
    of a response is a reader guessing.
    """
    definition = _definition(recovered)
    if definition is None:
        return {"definition": None, "definition_digest": None, "runtime": None}
    return {
        "definition": definition.as_dict(),
        # Computed here rather than stored beside the document, exactly as the
        # definition contract computes it: a digest of oneself that is written
        # down can disagree with oneself.
        "definition_digest": definition.digest(),
        "runtime": graph_runtime(recovered, definition),
    }


def graph_runtime(
        recovered: "RecoveredRun", definition: GraphDefinition) -> dict[str, Any]:
    """Project this run's records onto the plan it says it follows.

    The run's own phase is not restated here: it is ``run.status``, which the
    read already carries from the durable envelope, and a second spelling of it
    could disagree with the first.
    """
    values = tuple(row.value for row in recovered.records)
    return {
        "run_id": definition.run_id,
        "graph_id": definition.graph_id,
        "nodes": [_node_runtime(values, definition, node)
                  for node in definition.nodes],
    }


def _definition(recovered: "RecoveredRun") -> GraphDefinition | None:
    return next((row.value for row in recovered.records
                 if row.kind == "graph_definition"), None)


def _node_runtime(
        values: tuple[Any, ...], definition: GraphDefinition,
        node: GraphNode) -> dict[str, Any]:
    """One node's position, from the records that name it and no others."""
    named = {node.node_id}
    actions = {value.action_id for value in values
               if isinstance(value, ActionRequest) and value.node_id in named}
    results = [value for value in values
               if isinstance(value, ActionResultReceipt)
               and value.action_id in actions]
    events = [value for value in values
              if isinstance(value, AttemptEvent) and value.action_id in actions]
    # The journal is append-ordered, so the last result is the most recent one
    # this node produced; earlier ones stay readable in `records`.
    standing = results[-1] if results else None
    row: dict[str, Any] = {
        "node_id": node.node_id,
        "phase": _phase(values, named, actions, results, events),
        "attempt_ids": sorted(_attempt_ids(values, named)),
        "outcome": None if standing is None else standing.outcome,
        "observed_at": None if standing is None else standing.observed_at,
        "evidence_refs": sorted(
            {ref for result in results for ref in result.evidence_refs}),
    }
    if node.gate_id is not None:
        row["decision"] = _gate_state(values, definition.run_id, node.gate_id)
    if node.loop is not None:
        reopened = len(_attempt_ids(values, _cycle(definition, node)))
        row["pass"] = reopened
        row["bound_reached"] = reopened >= node.loop.bound
    return row


def _phase(
        values: tuple[Any, ...], named: set[str], actions: set[str],
        results: list[ActionResultReceipt],
        events: list[AttemptEvent]) -> str:
    """Where this node's records carry it, and never one step further."""
    if results or any(row.phase == "execution_observed" for row in events):
        return "observed"
    if events:
        return "running"
    if actions:
        return "requested"
    if any(isinstance(value, ActionProposal) and value.node_id in named
           for value in values):
        return "proposed"
    return "idle"


def _attempt_ids(values: tuple[Any, ...], named: set[str]) -> set[str]:
    """Every attempt the named nodes were ever asked to carry out."""
    return {value.attempt_id for value in values
            if isinstance(value, (ActionProposal, ActionRequest))
            and value.node_id in named}


def _gate_state(values: tuple[Any, ...], run_id: str, gate_id: str) -> str:
    """What this gate is, through the one function that already decides it.

    ``gate_decision`` refuses rather than choosing when a run holds more than
    one standing decision for one gate -- and the store takes those receipts,
    because neither supersedes the other. So the refusal is answered with
    ``unknown``: this projection reports what the journal supports, and a
    journal that supports two answers supports neither.
    """
    receipts = [value for value in values if isinstance(value, DecisionReceipt)]
    try:
        return gate_decision(receipts, run_id, gate_id)
    except ContractError:
        return "unknown"


def _cycle(definition: GraphDefinition, loop: GraphNode) -> set[str]:
    """The nodes a loop actually reopens: forward from ``back_to``, back to it.

    A loop's pass count is about the work it sends around again, so the nodes
    that count are the ones on a road from the step it reopens to the loop
    itself. Nodes before that step ran once and are not repeated by it, and
    nodes after the loop are not reached by going around.
    """
    assert loop.loop is not None
    forward = _reachable(definition.edges, loop.loop.back_to, forward=True)
    backward = _reachable(definition.edges, loop.node_id, forward=False)
    return forward & backward


def _reachable(
        edges: tuple[GraphEdge, ...], start: str, *, forward: bool) -> set[str]:
    """Every node reachable from ``start`` along the edges, in one direction."""
    following: dict[str, list[str]] = {}
    for edge in edges:
        source, target = (
            (edge.from_node, edge.to_node) if forward
            else (edge.to_node, edge.from_node))
        following.setdefault(source, []).append(target)
    seen = {start}
    pending = [start]
    while pending:
        for target in following.get(pending.pop(), ()):
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return seen
