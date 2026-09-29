"""The budget of a cycle: how many actions and seconds a run may need (spec 7.8, L18).

Pure. It reads the nodes and edges of a template or of a frozen plan alike, because both carry the
same facts under the same names (a template names the verifier by role, a plan by instance). The
limits arrive from the caller, so no product limit is written here; what is written here is the
arithmetic of the spec: the attempts of a step from the loops that reopen it, the time a checked
step reserves, the clean pass and the worst case, and the terms of the grant a run starts with or
is replaced by.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .graph_definition import EFFECTING_CAPABILITIES
from .graph_roads import loop_body
from .workflow_flow import ENTRY_INPUTS

#: What a step is given when its plan names no timeout (spec 7.2.3).
DEFAULT_TIMEOUT_SECONDS = 1800
#: The time a run is given to wait for one human answer, and the least and most it may be given.
HUMAN_WINDOW_SECONDS = 3600
MIN_WINDOW_SECONDS = 3600
MAX_WINDOW_SECONDS = 86400
#: The roads of the clean pass: a step that succeeded, a gate that approved, an unconditional road.
_CLEAN_CONDITIONS = frozenset({None, "on_succeeded", "on_approved"})


def product_limits(budget: Any) -> dict[str, int]:
    """The three limits `plan_budget` is given, from the boundary's own `Budget`.

    The total is the ceiling the preview checks (`max_actions` reservations of the longest one).
    """
    return {"max_actions": budget.max_actions, "max_action_seconds": budget.max_action_seconds,
            "max_total_task_seconds": budget.max_actions * budget.max_action_seconds}


def plan_budget(nodes: Iterable[Any], edges: Iterable[Any], limits: Mapping[str, int],
                spent: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The `Budget` of spec 7.8 for these nodes and edges under these limits.

    Args:
        nodes: Template nodes or frozen plan nodes, in document order.
        edges: The edges between them.
        limits: `max_actions`, `max_action_seconds` and `max_total_task_seconds`, from the route.
        spent: What the run already used, for the grant that replaces one (spec 6.4.4):
            `{"actions", "seconds", "attempts": [{"step_id", "attempts"}]}`. None for a fresh plan.
    """
    known = [node for node in nodes]
    names = {node.node_id for node in known}
    roads = [edge for edge in edges if edge.from_node in names and edge.to_node in names]
    rows = _step_rows(known, roads, limits)
    reached = _clean_pass(known, roads)
    clean = [row for row in rows if row["step_id"] in reached]
    humans = sum(1 for node in known if node.kind == "gate" and node.node_id in reached)
    terms, exhausted = _terms(rows, humans, limits, spent)
    return {
        "limits": {key: limits[key] for key in
                   ("max_actions", "max_action_seconds", "max_total_task_seconds")},
        "clean": {"actions": len(clean), "seconds": sum(row["reserve_seconds"] for row in clean)},
        "worst": {"actions": sum(row["attempts"] for row in rows),
                  "seconds": sum(row["attempts"] * row["reserve_seconds"] for row in rows)},
        "steps": rows, "terms_draft": terms, "spent": _copy_of(spent), "exhausted": exhausted,
        "inputs": {"instructions": _instructions(known), "documents": list(ENTRY_INPUTS)},
    }


def _step_rows(nodes: list[Any], edges: list[Any], limits: Mapping[str, int]) -> list[dict]:
    """One row per step that carries out work: its attempts and the time it reserves."""
    frames = _attempt_frames(nodes, edges)
    rows = []
    for node in nodes:
        if node.capability is None:
            continue
        checkers = 2 if _verifier(node) else 1
        wanted = node.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        held = min(wanted, limits["max_action_seconds"] // checkers)
        attempts = 1 + sum(bound - 1 for bound in frames.get(node.node_id, {}).values())
        if node.attempt_bound is not None:
            attempts = min(attempts, node.attempt_bound)
        rows.append({"step_id": node.node_id, "attempts": attempts, "timeout_seconds": held,
                     "reserve_seconds": held * checkers, "clamped": held < wanted})
    return rows


def _verifier(node: Any) -> Any:
    return getattr(node, "verifier_role_id", None) or getattr(node, "verifier_instance_id", None)


def _attempt_frames(nodes: list[Any], edges: list[Any]) -> dict[str, dict[str, int]]:
    """For each step, the largest bound of the loops that reopen it, by the step they reopen.

    Loops that return to the same step count the same attempts, so within one such frame only the
    largest bound counts; the frames of different steps add (spec 7.8).
    """
    names = {node.node_id for node in nodes}
    frames: dict[str, dict[str, int]] = {}
    for loop in nodes:
        if loop.loop is None or loop.loop.back_to not in names:
            continue
        for member in loop_body(nodes, edges, loop):
            held = frames.setdefault(member, {})
            held[loop.loop.back_to] = max(held.get(loop.loop.back_to, 0), loop.loop.bound)
    return frames


def _clean_pass(nodes: list[Any], edges: list[Any]) -> set[str]:
    """The steps reached from the start along the roads of a pass with no failure and no loop."""
    by_id = {node.node_id: node for node in nodes}
    entered = {edge.to_node for edge in edges}
    onward: dict[str, list[str]] = {}
    for edge in edges:
        if edge.condition in _CLEAN_CONDITIONS:
            onward.setdefault(edge.from_node, []).append(edge.to_node)
    pending = [node.node_id for node in nodes if node.node_id not in entered]
    reached: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reached or by_id[name].loop is not None:
            continue
        reached.add(name)
        pending.extend(onward.get(name, ()))
    return reached


def _terms(rows: list[dict], humans: int, limits: Mapping[str, int],
           spent: Mapping[str, Any] | None) -> tuple[dict[str, Any], bool]:
    """The terms of the grant, and whether a replacement has room for one more action."""
    used = {row["step_id"]: row["attempts"] for row in (spent or {}).get("attempts", ())}
    left = {row["step_id"]: max(0, row["attempts"] - used.get(row["step_id"], 0)) for row in rows}
    done_actions = (spent or {}).get("actions", 0)
    done_seconds = (spent or {}).get("seconds", 0)
    ahead = sum(left[row["step_id"]] * row["reserve_seconds"] for row in rows)
    total = min(limits["max_total_task_seconds"], done_seconds + ahead)
    window = total if spent is None else ahead
    terms = {
        "node_limits": [{"node_id": row["step_id"], "timeout_seconds": row["timeout_seconds"],
                         "max_attempts": max(row["attempts"], used.get(row["step_id"], 0))}
                        for row in rows],
        "max_actions": min(limits["max_actions"], done_actions + sum(left.values())),
        "max_action_seconds": max((row["reserve_seconds"] for row in rows), default=0),
        "max_total_task_seconds": total,
        "duration_seconds": min(MAX_WINDOW_SECONDS, max(
            MIN_WINDOW_SECONDS, window + HUMAN_WINDOW_SECONDS * humans)),
    }
    room = [row for row in rows if left[row["step_id"]] > 0
            and done_actions < limits["max_actions"]
            and done_seconds + row["reserve_seconds"] <= limits["max_total_task_seconds"]]
    return terms, spent is not None and not room


def _instructions(nodes: list[Any]) -> list[dict[str, Any]]:
    return [{"step_id": node.node_id, "instruction_ref": node.payload().get("instruction_ref")}
            for node in nodes if node.capability in EFFECTING_CAPABILITIES]


def _copy_of(spent: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if spent is None:
        return None
    return {"actions": spent["actions"], "seconds": spent["seconds"],
            "attempts": [{"step_id": row["step_id"], "attempts": row["attempts"]}
                         for row in spent["attempts"]]}
