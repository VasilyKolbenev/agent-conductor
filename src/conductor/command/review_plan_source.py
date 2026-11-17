"""Resolve an operator-accepted procedure in the current project's immutable run journal."""
from __future__ import annotations

import json

from .api_refusals import ApiRefusal
from .containment import run_route_violations
from .task_contracts import frozen_config_task
from .task_routes import resolve_task_binding


def _text(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _valid_notes(document, receipt, source):
    if not _text(document.content, 49152):
        return False
    try:
        notes = json.loads(document.content)
    except (ValueError, RecursionError):
        return False
    if not isinstance(notes, dict):
        return False
    checks = notes.get("checks")
    return (type(notes.get("schema_version")) is int and notes["schema_version"] == 1
            and notes.get("task_id") == source["task_id"]
            and notes.get("run_id") == source["run_id"]
            and notes.get("actor_id") == receipt.actor and _text(notes.get("reviewer"), 160)
            and isinstance(checks, list) and 1 <= len(checks) <= 20
            and all(isinstance(check, dict) and _text(check.get("step"), 320)
                    and _text(check.get("result"), 2048) for check in checks))


def require_accepted_source(tasks, runs, target_id, source):
    invalid = ApiRefusal.fixed("contract_invalid")
    if target_id == source["task_id"]:
        raise invalid
    task = resolve_task_binding(tasks, source["task_id"])
    run_id = source["run_id"]
    if run_route_violations(runs, run_id):
        raise ApiRefusal.fixed("route_unsafe")
    if not runs.run_path(run_id).is_dir():
        raise invalid
    run = runs.read(run_id)
    if (run.warnings or run.envelope.run_id != run_id or frozen_config_task(run.config) != task
            or tuple(row.kind for row in run.records) != (
                "graph_definition", "artifact", "decision", "run_terminal")):
        raise invalid
    graph, doc, receipt, end = (row.value for row in run.records)
    if graph.edges or len(graph.nodes) != 1:
        raise invalid
    node = graph.nodes[0]
    if (node.kind != "gate" or node.node_id != "operator-review"
            or node.gate_id != "gate-operator-review"
            or doc.artifact_id != source["artifact_id"]
            or doc.artifact_ref != "operator-review-procedure-v1"
            or doc.media_type != "text/plain" or doc.source_action_id is not None
            or receipt.receipt_id != source["receipt_id"] or receipt.action != "approve"
            or receipt.gate_id != node.gate_id
            or receipt.config_digest != run.envelope.config_digest
            or receipt.scope_refs != (doc.artifact_id,)
            or receipt.reason != "Принята запись выполненных проверок. " + doc.digest()
            or end.state != "complete" or end.settled_nodes != (node.node_id,)
            or not _valid_notes(doc, receipt, source)):
        raise invalid
