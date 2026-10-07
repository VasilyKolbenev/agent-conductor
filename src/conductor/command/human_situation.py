"""Present human needs supported by this read, never permission or a heartbeat.

The schedule owns arrival, laps, documents and bounds. A request-only journal
cannot distinguish an ordinary queue from a lost process: its action IDs make
this reading unknown, never an instruction to reconcile live work.
"""
from __future__ import annotations

from typing import Any

from .attempt_replay import attempt_events_for, proposal_named_by, terminal_result_for
from .contracts import ActionProposal, ActionRequest, ControlMode, _id, _timestamp
from .graph_causality import (
    _gate_has_arrived, decision_is_reached, gate_answer, standing_receipt,
)
from .graph_definition import GraphDefinition, GraphNode
from .graph_schedule import (
    _waits_for_a_document, attempt_in_flight, lap_is_current, run_is_halted,
)
from .graph_schedule_values import RunSchedule
from .run_terminal import RunTerminal

HUMAN_STATES = ("required", "not_required", "unknown")
CHECKED_REASONS = (
    "gate_decision", "confirmation", "input_document", "reconcile", "attempt_bound", "run_ended",
)
UNKNOWN_REASONS = ("contradictory_gate_receipts", "replay_warnings", "unobserved_request")
GATE_WHY_NOT = (
    "run_ended", "decision_unknown", "answered_current_lap", "branch_closed", "road_not_open",
)


def gate_answerability(definition: GraphDefinition, values: tuple[Any, ...],
                node: GraphNode) -> str | None:
    """The decision door's verdict for a receipt offered on this gate NOW.

    `first` when nothing stands and the plan has reached the gate; `supersede`
    when the standing answer may be replaced -- this lap's correction, or a
    reopened lap the plan has reached again; `none` when the door would refuse;
    and None on a step that is not a gate at all.

    Asked of `decision_is_reached` itself and never re-derived: R02 of the
    review of `8dec0e4` was a screen spelling the door's arms for itself and
    offering a supersede the door refused. One of the arms -- whether the
    standing answer belongs to the lap the gate is on now -- needs the lap
    arithmetic, and a second copy of that in a browser is how the two came to
    disagree. Served on the read, the screen has nothing left to compute.

    A run that has recorded its ending answers `none` on every gate: the door
    refuses every receipt there (`run_terminal`) before it asks the plan
    anything, and a word served from the plan alone said `supersede` about a
    run nothing can be added to.
    """
    if node.gate_id is None:
        return None
    if any(isinstance(value, RunTerminal) for value in values):
        return "none"
    stands = standing_receipt(values, definition.run_id, node.gate_id)
    admitted = decision_is_reached(
        definition, values, node.gate_id,
        None if stands is None else stands.receipt_id)
    if not admitted:
        return "none"
    return "first" if stands is None else "supersede"


def _gate_reason(row, *, ended: bool, decision: str, needed: bool) -> str | None:
    if ended:
        return "run_ended"
    if decision == "unknown":
        return "decision_unknown"
    if needed:
        return None
    if row.state == "settled":
        return "answered_current_lap"
    if row.state == "unreachable" or row.closed_by:
        return "branch_closed"
    return "road_not_open"


def _gate_row(definition, values, computed, node, *, ended):
    row = next(value for value in computed.nodes if value.node_id == node.node_id)
    answer = gate_answer(values, definition.run_id, node.gate_id)
    decision = "unknown" if answer is None else answer
    standing = standing_receipt(values, definition.run_id, node.gate_id)
    current = None
    if standing is not None:
        index = next(index for index, value in enumerate(values) if value is standing)
        current = lap_is_current(definition, values, node.node_id, index)
    arrived = _gate_has_arrived(computed, node.node_id)
    needed = arrived and decision != "unknown" and not ended
    return {"node_id": node.node_id, "gate_id": node.gate_id, "arrived": arrived,
            "decision": decision, "answerable": gate_answerability(definition, values, node),
            "lap": {"required_pass": row.required_pass, "settled_laps": row.settled_laps},
            "standing_receipt": None if standing is None else standing.receipt_id,
            "standing_belongs_to_current_lap": current, "needs_decision": needed,
            "why_not": _gate_reason(row, ended=ended, decision=decision, needed=needed)}


def _unobserved_requests(values, run_id):
    return [value.action_id for value in values if isinstance(value, ActionRequest)
            and value.run_id == run_id and not attempt_events_for(values, value.action_id)
            and terminal_result_for(values, value.action_id) is None]


def _proposal_unavailable(values, proposal):
    # The existing authorize/store relation claims attempt_id for the whole run,
    # across instances and after completion. A different attempt may fan out.
    if any(isinstance(value, ActionRequest) and value.run_id == proposal.run_id
           and value.attempt_id == proposal.attempt_id for value in values):
        return True
    return proposal.node_id is not None and attempt_in_flight(values, proposal.node_id)


def _confirmation_sources(definition, values, computed, *, run_id, mode):
    if mode not in (ControlMode.CONFIRM, ControlMode.PROPOSE):
        return []
    requested = {proposal_named_by(value) for value in values
                 if isinstance(value, ActionRequest) and value.run_id == run_id}
    latest = {}
    for index, value in enumerate(values):
        if isinstance(value, ActionProposal) and value.run_id == run_id:
            key = ("node", value.node_id) if value.node_id else ("proposal", value.proposal_id)
            latest[key] = (index, value)
    found = []
    for index, proposal in latest.values():
        if proposal.proposal_id in requested or _proposal_unavailable(values, proposal):
            continue
        if definition is not None:
            if computed.state_of(proposal.node_id) != "runnable":
                continue
            if not lap_is_current(definition, values, proposal.node_id, index):
                continue
        found.append(proposal.proposal_id)
    return found


def _work_needs(definition, values, computed):
    if definition is None:
        return [], []
    documents = []
    if not run_is_halted(definition, values, computed):
        documents = [row.node_id for row in computed.nodes
                     if _waits_for_a_document(row) and not row.closed_by
                     and not attempt_in_flight(values, row.node_id)]
    spent = [row.node_id for row in computed.nodes
             if computed.run_state == "stalled" and row.state == "blocked"
             and row.attempts_spent]
    return documents, spent


def _entries(reasons, sources):
    return [{"reason": reason, "count": len(sources.get(reason, [])),
             "sources": list(sources.get(reason, []))} for reason in reasons]


def human_situation(
        definition: GraphDefinition | None, values: tuple[Any, ...],
        computed: RunSchedule | None, *, run_id: str, mode: str,
        warnings: tuple[str, ...], computed_at: str) -> dict[str, Any]:
    """Read one replay without a store, runtime, mutable adapter or local clock."""
    _id("run_id", run_id)
    mode = ControlMode(mode)
    instant = _timestamp("computed_at", computed_at)
    terminals = [value.terminal_id for value in values if isinstance(value, RunTerminal)
                 and value.run_id == run_id]
    ended = bool(terminals)
    gates = [] if definition is None else [
        _gate_row(definition, values, computed, node, ended=ended)
        for node in definition.nodes if node.gate_id is not None]
    documents, spent = ([], []) if ended else _work_needs(definition, values, computed)
    checked = _entries(CHECKED_REASONS, {
        "gate_decision": [row["node_id"] for row in gates if row["needs_decision"]],
        "confirmation": [] if ended else _confirmation_sources(
            definition, values, computed, run_id=run_id, mode=mode),
        "input_document": documents, "attempt_bound": spent, "run_ended": terminals,
    })
    unknown = _entries(UNKNOWN_REASONS, {
        "contradictory_gate_receipts": [row["gate_id"] for row in gates
                                        if row["decision"] == "unknown"],
        "unobserved_request": [] if ended else _unobserved_requests(values, run_id),
    })
    next(row for row in unknown if row["reason"] == "replay_warnings")["count"] = len(warnings)
    because = [row["reason"] for row in unknown if row["count"]]
    needed = any(row["count"] for row in checked if row["reason"] != "run_ended")
    return {"state": "unknown" if because else ("required" if needed else "not_required"),
            "computed_at": instant, "gates": gates, "checked": checked,
            "unknown_because": because, "unknown_sources": unknown}
