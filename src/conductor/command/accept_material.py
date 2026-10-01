"""Transfer rows derive from immutable evidence. The live tree supplies only its seal."""
from __future__ import annotations

from .accept_capture import _base, _images, tree_digest
from .accept_manifest import FileImage, ManifestRow, SnapshotRefused, _path, blob_oid, sha256
from .accept_snapshot import read_snapshot
from .acceptance_basis import STARTER_DOC_PATHS
from .adapters.harness_workspace import HarnessWorkspace, WorkspaceNotContained
from .adapters.work_seed import CaptureRefused
from .artifacts import ArtifactDocument, REVIEW_CAPABILITY, latest_artifacts
from .contracts import ActionRequest, EvidenceRef
from .seed_plan import _is_instruction
from .work_layout import work_route

def files(context, facts, listing):
    seed, basis = context.seed, context.basis
    snapshot = read_snapshot(facts.root, context.recovered.envelope.run_id,
                             basis.accept_manifest_digest, object_format=facts.object_format)
    base, fmt = _base(facts.root, seed, lambda: facts.git)
    if fmt != facts.object_format:
        raise SnapshotRefused("object_format_changed")
    workspace = HarnessWorkspace.at(facts.root, home_dir=".accept-unused", marker_dir=".accept-unused-markers")
    try:
        raw = workspace.capture_work_tree("work-001", work_scope=context.task.work_scope)
    except (OSError, WorkspaceNotContained, CaptureRefused) as error:
        reason = str(error) if isinstance(error, CaptureRefused) else "irregular_result"
        raise SnapshotRefused(reason if reason in {"irregular_result", "result_too_large"}
                              else "work_changed_since_verification") from None
    if tree_digest(_images(raw, base)) != basis.work_tree_digest:
        raise SnapshotRefused("work_changed_since_verification")
    work = facts.root / work_route("work-001", context.task.work_scope)
    rows, after, skipped = [], {}, []
    ignored = facts.ignored([row.path for row in snapshot.rows if row.state == "added"
                             and not (seed.source == "empty" and row.path in listing)], work)
    for row in snapshot.rows:
        if row.path in ignored:
            skipped.append({"path": row.path, "reason": "ignored_by_project"})
            continue
        rows.append(row)
        if row.state != "deleted":
            after[row.path] = snapshot.blobs[row.sha256]
    skipped += [{"path": row.path, "reason": "seed_skipped"} for row in seed.skipped]
    skipped += [{"path": path, "reason": "agent_instructions"} for path in seed.agent_instructions_skipped]
    known = {row["path"] for row in skipped}
    for path in raw:
        reason = ("agent_git_dir" if any(part.casefold() == ".git" for part in path.split("/")) else
                  "agent_instructions" if not seed.include_agent_instructions and _is_instruction(path) else None)
        if reason is not None and path not in known:
            skipped.append({"path": path, "reason": reason})
    return rows, after, skipped, len(snapshot.rows)


def documents(context, selected):
    values = tuple(row.value for row in context.recovered.records)
    nodes = {node.node_id: node for node in context.definition.nodes if node.capability == REVIEW_CAPABILITY}
    refs = {node.payload().get("result_artifact_ref") for node in nodes.values()}
    refs.discard(None)
    starter_paths = {} if context.workflow is None else STARTER_DOC_PATHS.get(context.workflow[0], {})
    starter = bool(starter_paths)
    if starter:
        refs = set(starter_paths)
    if selected is None:
        selected = sorted(refs) if context.basis.kind == "documents" else []
    if not set(selected) <= refs:
        raise SnapshotRefused("result_not_verified")
    try:
        docs = latest_artifacts((row for row in values if isinstance(row, ArtifactDocument)), selected)
    except ValueError:
        raise SnapshotRefused("result_not_verified") from None
    actions = {row.action_id: row for row in values if isinstance(row, ActionRequest)}
    decision_at = next(at for at, row in enumerate(values)
                       if getattr(row, "receipt_id", None) == context.basis.decision_id)
    result = []
    for doc in docs:
        if values.index(doc) >= decision_at:
            raise SnapshotRefused("decision_precedes_result")
        human_brief = starter and doc.artifact_ref == "artifact-brief" and doc.source_action_id is None
        action = actions.get(doc.source_action_id)
        if not human_brief:
            if (action is None or action.capability != REVIEW_CAPABILITY or action.node_id not in nodes
                    or nodes[action.node_id].payload().get("result_artifact_ref") != doc.artifact_ref):
                raise SnapshotRefused("result_not_verified")
            proof = [row for row in values if isinstance(row, EvidenceRef)
                     and row.kind == "verification" and row.uri == f"verification/{action.action_id}"]
            if len(proof) != 1 or proof[0].verification != "verified" or proof[0].digest != doc.digest():
                raise SnapshotRefused("result_not_verified")
            if values.index(proof[0]) >= decision_at:
                raise SnapshotRefused("decision_precedes_result")
        name = (starter_paths[doc.artifact_ref].removeprefix("docs/") if starter else
                doc.artifact_ref.removeprefix("artifact-") +
                (".md" if doc.media_type == "text/markdown" else ".txt"))
        prefix = "docs/" if context.basis.kind == "documents" else f"docs/conduct/{context.task.task_id}/"
        path = _path(prefix + name)
        if any(path.casefold() == previous[0].casefold() for previous in result):
            raise SnapshotRefused("document_name_collision")
        result.append((path, doc))
    return result


def overlay(rows, after, listing, facts, *, overlay_base=False):
    """Attach selected base bytes for patch; empty seed may only overlay saved rows."""
    before, adjusted = {}, []
    for row in rows:
        old = listing.get(row.path)
        if old is not None:
            before[row.path] = facts.blob(old)
        if overlay_base:
            if row.state == "deleted":
                raise SnapshotRefused("snapshot_damaged")
            row = ManifestRow(row.path, "modified" if old else "added", row.mode,
                               row.length, row.sha256, row.git_oid)
        adjusted.append(row)
    return adjusted, before


def add_documents(rows, after, docs, listing, facts):
    shown = []
    for path, document in docs:
        if any(row.path.casefold() == path.casefold() for row in rows):
            raise SnapshotRefused("document_name_collision")
        data = document.content.encode("utf-8")
        old = listing.get(path)
        mode = old.mode if old is not None else "100644"
        row = ManifestRow(path, "modified" if old else "added", mode, len(data), sha256(data),
                          blob_oid(data, facts.object_format))
        FileImage(data, mode)
        rows.append(row)
        after[path] = data
        shown.append({"artifact_ref": document.artifact_ref, "artifact_id": document.artifact_id,
                      "path": path, "state": row.state})
    return shown


def hold_overlay_paths(rows, listing):
    deleted = {row.path for row in rows if row.state == "deleted"}
    folded = {path.casefold(): path for path in listing if path not in deleted}
    for row in rows:
        if row.state == "deleted":
            continue
        other = folded.get(row.path.casefold())
        if other is not None and other != row.path:
            raise SnapshotRefused("case_collision")
        ancestors = ["/".join(row.path.split("/")[:index]) for index in range(1, len(row.path.split("/")))]
        if any(path in listing and path not in deleted for path in ancestors):
            raise SnapshotRefused("reserved_path")
        if any(path.startswith(row.path + "/") and path not in deleted for path in listing):
            raise SnapshotRefused("reserved_path")
