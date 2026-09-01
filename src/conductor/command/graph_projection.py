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
from .graph_definition import GraphDefinition, GraphNode
from .graph_schedule import loop_position, schedule

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
        return {"definition": None, "definition_digest": None, "runtime": None,
                "schedule": None}
    values = tuple(row.value for row in recovered.records)
    return {
        "definition": definition.as_dict(),
        # Computed here rather than stored beside the document, exactly as the
        # definition contract computes it: a digest of oneself that is written
        # down can disagree with oneself.
        "definition_digest": definition.digest(),
        "runtime": graph_runtime(recovered, definition),
        "schedule": _schedule_payload(definition, values),
    }


def _schedule_payload(
        definition: GraphDefinition, values: tuple[Any, ...]) -> dict[str, Any]:
    """What the plan says may happen now, as the wire spells it.

    A THIRD reading beside the other two, and deliberately not folded into
    either. The definition says what was intended and the runtime says what was
    observed; this says what those two together permit, and it is a pure
    function of both -- so it is computed here on every read rather than stored,
    for the reason the digest beside it is.

    It is the browser's only source for "where could this step go next". The
    window used to walk the edge list itself and call every out-edge an
    unblocking, which was true only while no edge could carry a condition. One
    successor computation, in Python, is what stops a screen and a refusal
    disagreeing about which step may run.
    """
    computed = schedule(definition, values)
    return {
        "run_state": computed.run_state,
        "runnable": list(computed.runnable),
        "settled": list(computed.settled),
        "unreachable": list(computed.unreachable),
        "nodes": [{
            "node_id": row.node_id,
            "state": row.state,
            "opened_by": list(row.opened_by),
            "blocked_by": list(row.blocked_by),
            "closed_by": list(row.closed_by),
            "opens": [{"to_node": to_node, "condition": condition}
                      for to_node, condition in row.opens],
            "required_pass": row.required_pass,
            "settled_laps": row.settled_laps,
            "attempts_spent": row.attempts_spent,
            "awaiting_artifacts": list(row.awaiting_artifacts),
        } for row in computed.nodes],
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
    """One node's position: its CURRENT action, and its whole attempt history.

    Aggregating a node's history was a lie a Cockpit would have shown as
    green. A node whose first attempt finished `succeeded` and whose second is
    already requested reported the old outcome, the old evidence and `observed`
    -- a finished step, while the work was being done again. So everything that
    describes a position comes from the current action alone; only
    ``attempt_ids`` is the whole history, because it is the key a reader needs
    to go find an earlier attempt in ``records``.
    """
    named = {node.node_id}
    current = _current_action(values, named)
    action_id = current.action_id if isinstance(current, ActionRequest) else None
    results = [value for value in values
               if isinstance(value, ActionResultReceipt)
               and value.action_id == action_id]
    events = [value for value in values
              if isinstance(value, AttemptEvent) and value.action_id == action_id]
    standing = results[-1] if results else None
    row: dict[str, Any] = {
        "node_id": node.node_id,
        "phase": _phase(current, results, events),
        "attempt_ids": sorted(_attempt_ids(values, named)),
        "outcome": None if standing is None else standing.outcome,
        "observed_at": None if standing is None else standing.observed_at,
        "evidence_refs": sorted(
            {ref for result in results for ref in result.evidence_refs}),
    }
    if node.gate_id is not None:
        row["decision"] = _gate_state(values, definition.run_id, node.gate_id)
    if node.loop is not None:
        # The trip this run is on, read off the ONE node the loop reopens --
        # asked of `graph_schedule`, which owns the arithmetic, rather than
        # computed a second time here. The reading is unchanged and its reasons
        # are recorded at that owner; what changes is that the module which
        # ROUTES on this position and the screen that DISPLAYS it can no longer
        # come to disagree about it.
        row["pass"], row["bound_reached"] = loop_position(values, node)
    return row


def _current_action(
        values: tuple[Any, ...],
        named: set[str]) -> ActionProposal | ActionRequest | None:
    """The LAST document in append order that binds one of these nodes.

    A proposal appended after a finished request is a new attempt being asked
    for, and it is what the node is doing now -- so it supersedes the finished
    one for every field except the attempt history.
    """
    latest: ActionProposal | ActionRequest | None = None
    for value in values:
        if (isinstance(value, (ActionProposal, ActionRequest))
                and value.node_id in named):
            latest = value
    return latest


def _phase(
        current: ActionProposal | ActionRequest | None,
        results: list[ActionResultReceipt],
        events: list[AttemptEvent]) -> str:
    """Where the current action's records carry it, and never one step further."""
    if current is None:
        return "idle"
    if not isinstance(current, ActionRequest):
        return "proposed"
    if results or any(row.phase == "execution_observed" for row in events):
        return "observed"
    if events:
        return "running"
    return "requested"


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
