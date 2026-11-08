"""Bounded read-only projection of the latest independently verified Codex patch."""
from .accept_manifest import SnapshotRefused
from .accept_snapshot import read_snapshot_index
from .adapters.deep_commands import PATCH_PROFILE
from .adapters.result_manifest import marked_policy
from .contracts import ActionRequest, ActionResultReceipt, EvidenceRef, frozen_config_bindings
from .graph_definition import GraphDefinition
from .task_contracts import frozen_config_task

MAX_SHOWN = 32


def checked_changes(root, recovered):
    if recovered.warnings:
        return None
    values = [row.value for row in recovered.records]
    request = next((v for v in reversed(values) if isinstance(v, ActionRequest)
                    and v.capability == "dispatch"), None)
    if (request is None or not marked_policy(request)
            or request.arguments.get("profile") != PATCH_PROFILE):
        return None
    task = frozen_config_task(recovered.config)
    if not task or request.arguments.get("work_scope") != task.work_scope:
        return None
    plan = next((v for v in values if isinstance(v, GraphDefinition)), None)
    node = next((n for n in plan.nodes if n.node_id == request.node_id), None) if plan else None
    if (node is None or node.arguments.get("profile") != PATCH_PROFILE
            or node.instance_id != request.instance_id or not node.verifier_instance_id
            or node.verifier_instance_id == request.instance_id):
        return None
    result = next((v for v in values if isinstance(v, ActionResultReceipt)
                   and v.action_id == request.action_id and v.attempt_id == request.attempt_id),
                  None)
    if result is None or result.outcome != "succeeded":
        return None
    adapter = frozen_config_bindings(recovered.config).get(node.verifier_instance_id)
    proofs = [v for v in values if isinstance(v, EvidenceRef)
              and v.evidence_id in result.evidence_refs
              and v.kind == "verification" and v.verification == "verified"
              and v.verifier_instance_id == node.verifier_instance_id and v.verified_by == adapter
              and v.uri == f"verification/{request.action_id}"]
    if len(proofs) != 1:
        return None
    digest = proofs[0].extra.get("accept_manifest_digest")
    if not isinstance(digest, str) or not proofs[0].extra.get("work_tree_digest"):
        return None  # Historical or unseeded work has no sealed filename list.
    view = {"action_id": request.action_id, "attempt_id": request.attempt_id,
            "verifier": node.verifier_instance_id, "digest": digest}
    try:
        rows = read_snapshot_index(root, request.run_id, digest)
    except SnapshotRefused:
        return {**view, "total": None, "files": []}
    return {**view, "total": len(rows),
            "files": [{"path": row.path, "state": row.state} for row in rows[:MAX_SHOWN]]}
