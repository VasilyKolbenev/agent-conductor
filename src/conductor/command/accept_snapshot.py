"""Exclusive, content-addressed snapshots for independent review and later transfer.

Publication is manifest-last under the existing project writer and root lock. A failed
write may leave owned blobs, but never a manifest which claims missing bytes. Reuse
compares existing bytes and refuses damage; it never repairs or replaces evidence.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..ownership import data_root, write_guard
from .accept_manifest import (
    MAX_BYTES, MAX_MANIFEST_BYTES, Snapshot, SnapshotRefused, read_manifest,
    sha256, validate_snapshot,
)
from .containment import first_directory_violation
from .contract_values import _id
from .path_admission import admit_file, admit_name
from .run_store import _exclusive_bytes, _fsync_dir, _root_gate
from .template_store import _leaf_violation

_DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")


def _hex(digest: str) -> str:
    match = _DIGEST.fullmatch(digest) if type(digest) is str else None
    if match is None:
        raise SnapshotRefused("snapshot_damaged")
    return match[1]


def _folder(root: Path, run_id: str) -> Path:
    safe = _id("run_id", run_id)
    admit_name(safe, "run_id")
    return data_root(root) / "accept" / safe


def _hold(root: Path, path: Path) -> None:
    # Include every product-owned component, not just the last snapshots/blobs folder.
    parts = path.relative_to(root).parts
    directories = [root.joinpath(*parts[:index]) for index in range(len(parts))]
    if first_directory_violation(directories) or _leaf_violation(path):
        raise SnapshotRefused("snapshot_damaged")


def _read(root: Path, path: Path, limit: int) -> bytes:
    _hold(root, path)
    with path.open("rb") as stream:
        found = os.fstat(stream.fileno())
        named = os.lstat(path)
        if ((found.st_dev, found.st_ino) != (named.st_dev, named.st_ino)
                or found.st_nlink != 1 or found.st_size > limit):
            raise SnapshotRefused("snapshot_damaged")
        payload = stream.read(limit + 1)
    _hold(root, path)
    if len(payload) > limit:
        raise SnapshotRefused("snapshot_damaged")
    return payload


def _put(root: Path, path: Path, payload: bytes) -> None:
    admit_file(path, "accept snapshot")
    _hold(root, path)
    if os.path.lexists(path):
        if _read(root, path, len(payload)) != payload:
            raise SnapshotRefused("snapshot_damaged")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _hold(root, path)
    try:
        _exclusive_bytes(path, payload)
    except FileExistsError:
        if _read(root, path, len(payload)) != payload:
            raise SnapshotRefused("snapshot_damaged") from None
    _fsync_dir(path.parent)


def write_snapshot(project_root: str | os.PathLike[str], run_id: str, snapshot: Snapshot, *,
                   object_format: str) -> str:
    """Persist captured bytes; return their digest, never a verification verdict."""
    validate_snapshot(snapshot, object_format=object_format)
    root = Path(project_root).resolve()
    folder = _folder(root, run_id)
    manifest = folder / "snapshots" / (_hex(snapshot.digest) + ".json")
    gate = _root_gate(root)  # keep the weakly indexed lock alive for the whole operation
    try:
        with gate.lock, write_guard(root):
            _hold(root, manifest)
            if os.path.lexists(manifest):
                # Once published, even a missing blob is damaged evidence, not unfinished
                # publication. Validate before considering any content-addressed writes.
                existing = read_snapshot(root, run_id, snapshot.digest,
                                         object_format=object_format)
                if existing.payload != snapshot.payload:
                    raise SnapshotRefused("snapshot_damaged")
                return snapshot.digest
            # Preflight every output route before publishing the first blob.
            paths = [(folder / "blobs" / _hex(digest), data)
                     for digest, data in snapshot.blobs.items()]
            for path, _data in [*paths, (manifest, snapshot.payload)]:
                admit_file(path, "accept snapshot")
                _hold(root, path)
            for path, data in paths:
                _put(root, path, data)
            _put(root, manifest, snapshot.payload)
    except OSError:
        raise SnapshotRefused("snapshot_damaged") from None
    return snapshot.digest


def read_snapshot(project_root: str | os.PathLike[str], run_id: str, digest: str, *,
                  object_format: str) -> Snapshot:
    """Rehash the manifest and every referenced blob, without reading the work item."""
    root = Path(project_root).resolve()
    folder = _folder(root, run_id)
    manifest = folder / "snapshots" / (_hex(digest) + ".json")
    gate = _root_gate(root)
    try:
        with gate.lock:
            payload = _read(root, manifest, MAX_MANIFEST_BYTES)
            if sha256(payload) != digest:
                raise SnapshotRefused("snapshot_damaged")
            rows = read_manifest(payload, object_format=object_format)
            blobs = {}
            for row in rows:
                if row.state != "deleted" and row.sha256 not in blobs:
                    blobs[row.sha256] = _read(root, folder / "blobs" / _hex(row.sha256),
                                              min(row.length, MAX_BYTES))
            result = Snapshot(rows, blobs)
            validate_snapshot(result, object_format=object_format)
            return result
    except OSError:
        raise SnapshotRefused("snapshot_damaged") from None
