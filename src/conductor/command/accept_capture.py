"""Capture one seeded work item for R6, through the existing workspace and pinned Git doors.

The live bytes are read once for both the attempt check and accumulated snapshot. Later tree
guards still rehash the work tree, but neither the frame nor the seal is rebuilt from that read.
No owner HEAD is a comparison base, and no Git write is made here.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass

from .accept_manifest import FileImage, Snapshot, SnapshotRefused, blob_oid, build_snapshot
from .accept_snapshot import read_snapshot, write_snapshot
from .adapters.harness_workspace import FILE_BUDGET
from .adapters.work_seed import CaptureRefused
from .project_git import has_git_entry
from .seed_plan import SeedPlan, _is_instruction, blob_batches, shown
from .seed_record import WORK_ITEM_ID, read_seed
from .seed_stage import _listing, _read_batch, _single, _OID
from .task_contracts import frozen_config_task
from .work_layout import work_route


@dataclass(frozen=True)
class CapturedResult:
    snapshot: Snapshot
    object_format: str
    work_tree_digest: str
    tree: dict[str, str]
    contents: dict[str, bytes]
    subtree: str
    modes: dict[str, bool]


def tree_digest(images: dict[str, FileImage]) -> str:
    """Canonical full-subtree seal shared with the future accept preview.

    Includes unchanged files and mode; Git object format does not change this seal.
    """
    rows = [{"path": name, "mode": image.mode, "length": len(image.data),
             "sha256": hashlib.sha256(image.data).hexdigest()}
            for name, image in sorted(images.items())]
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def capture_dispatch(store, request, args, workspace, git_factory, *, sensitive=()):
    """Return None for legacy unseeded work; it never acquires acceptance evidence extras."""
    recovered = store.read(request.run_id)
    if recovered.warnings:
        raise SnapshotRefused("material_unavailable")
    task = frozen_config_task(recovered.config)
    if task is None:
        return None
    if args.task_scope != task.work_scope:
        raise SnapshotRefused("material_unavailable")
    seed = read_seed(store.project_root, task.task_id)
    if seed is None:
        return None
    if args.work_item_id != WORK_ITEM_ID or (seed.task_id, seed.work_scope, seed.work_item_id) != (
            task.task_id, task.work_scope, args.work_item_id):
        raise SnapshotRefused("material_unavailable")
    base, fmt = _base(store.project_root, seed, git_factory)
    try:
        raw = workspace.capture_work_tree(args.work_item_id, work_scope=task.work_scope)
    except CaptureRefused as error:
        raise SnapshotRefused(str(error)) from error
    images = _images(raw, base)
    # Irregular/reserved paths must refuse before they can be treated as omitted files.
    if any(_under(name, tuple(row.path for row in seed.skipped)) for name in images):
        raise SnapshotRefused("reserved_path")
    transferable = {name: value for name, value in images.items() if _included(name, seed)}
    snapshot = build_snapshot(base, transferable, object_format=fmt)
    # Scan raw semantic bytes before writing an immutable artifact or JSON/hex encoding it.
    from .adapters.independent_check import scan_material
    scan_material(([row.as_dict() for row in snapshot.rows], tuple(snapshot.blobs.values())), sensitive)
    digest = write_snapshot(store.project_root, request.run_id, snapshot, object_format=fmt)
    saved = read_snapshot(store.project_root, request.run_id, digest, object_format=fmt)
    prefix = work_route(args.work_item_id, task.work_scope).removeprefix("work/") + "/"
    tree = {prefix + name: hashlib.sha256(image.data).hexdigest() for name, image in images.items()}
    return CapturedResult(saved, fmt, tree_digest(images), tree,
                          {prefix + name: image.data for name, image in images.items()}, prefix,
                          {name: bool(mode & 0o111) for name, (mode, _data) in raw.items()})


def attempt_material(captured, changed):
    """Project the existing per-attempt check from the very same capture."""
    if any(not path.startswith(captured.subtree) for path in changed):
        raise SnapshotRefused("material_unavailable")
    contents = {path: captured.contents[path] for path in changed if path in captured.contents}
    if any(len(data) > FILE_BUDGET for data in contents.values()):
        raise SnapshotRefused("frame_over_limit")
    absent = tuple(path for path in changed if path not in captured.tree)
    return captured.tree, contents, absent, captured.subtree


def _images(raw, base):
    return {name: FileImage(data, (base[name].mode if name in base else "100644")
                           if sys.platform == "win32" else
                           "100755" if mode & 0o111 else "100644")
            for name, (mode, data) in raw.items()}


def _under(name, paths):
    folded = name.casefold()
    return any(folded == path.casefold() or folded.startswith(path.casefold().rstrip("/") + "/")
               or shown(name).casefold() == path.casefold() for path in paths)


def _included(name, seed):
    return (not any(part.casefold() == ".git" for part in name.split("/"))
            and not _under(name, tuple(row.path for row in seed.skipped))
            and (seed.include_agent_instructions or not _is_instruction(name))
            and not _under(name, seed.agent_instructions_skipped))


def _base(root, seed, git_factory):
    if seed.source == "empty" and not has_git_entry(root):
        return {}, "sha1"  # ADR-R6-EMPTY-SEED-FORMAT: future setup must explicitly init SHA-1.
    git = git_factory()
    fmt = _single(git(["-C", str(root), "rev-parse", "--show-object-format"], True), None)
    if fmt not in {"sha1", "sha256"} or seed.source == "git" and fmt != seed.object_format:
        raise SnapshotRefused("object_format_changed")
    if seed.source == "empty":
        return {}, fmt
    tree = _single(git(["-C", str(root), "rev-parse", f"{seed.base_commit}^{{tree}}"], True), _OID)
    if tree != seed.base_tree:
        raise SnapshotRefused("base_missing")
    rows = tuple(row for row in _listing(root, git, seed.base_tree) if _included(row.path, seed))
    if any(row.kind != "blob" or row.mode not in {"100644", "100755"} for row in rows):
        raise SnapshotRefused("reserved_path")
    if len(rows) > 5000 or sum(row.size for row in rows) > 64 * 1024 * 1024:
        raise SnapshotRefused("result_too_large")
    plan = SeedPlan(rows, (), (), len(rows), sum(row.size for row in rows))
    objects = {}
    for batch in blob_batches(plan):
        objects.update(_read_batch(root, git, batch))
    if any(blob_oid(objects[row.oid], fmt) != row.oid for row in rows):
        raise SnapshotRefused("snapshot_damaged")
    return {row.path: FileImage(objects[row.oid], row.mode) for row in rows}, fmt
