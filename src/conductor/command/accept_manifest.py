"""Immutable accumulated result values (spec 9.4.1), before any acceptance authority.

Both inputs are already captured regular files, relative to one work item. The caller
must prove the source route and supply the seed's base, not the previous attempt.
This module neither reads a live folder nor says that a reviewer approved these bytes.
Deleted rows bind the OLD file's mode, length and hashes; they have no stored blob.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .path_admission import WindowsNameError, admit_name
from .product_names import is_product_path

MAX_FILES = 2000
MAX_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_FIELDS = {"path", "state", "mode", "length", "sha256", "git_oid"}
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")


class SnapshotRefused(ValueError):
    """A closed reason for a result which cannot become an immutable snapshot."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def blob_oid(data: bytes, object_format: str) -> str:
    if object_format not in {"sha1", "sha256"}:
        raise SnapshotRefused("snapshot_damaged")
    return hashlib.new(object_format, b"blob " + str(len(data)).encode("ascii")
                       + b"\0" + data).hexdigest()


def _path(value: object) -> str:
    if (type(value) is not str or not value or len(value) > 4096
            or any(char in value for char in '\\"<>|?*')
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise SnapshotRefused("unportable_name")
    parts = value.split("/")
    if any(part in {"", ".", ".."} or ":" in part for part in parts):
        raise SnapshotRefused("unportable_name")
    try:
        for part in parts:
            admit_name(part, "result path")
    except WindowsNameError:
        raise SnapshotRefused("unportable_name") from None
    if is_product_path(value) or any(part.casefold() == ".git" for part in parts):
        raise SnapshotRefused("reserved_path")
    return value


@dataclass(frozen=True)
class FileImage:
    """Captured file bytes and their Git mode; Windows mode is chosen by the capture."""

    data: bytes
    mode: str = "100644"

    def __post_init__(self) -> None:
        if type(self.data) is not bytes or self.mode not in {"100644", "100755"}:
            raise SnapshotRefused("irregular_result")


@dataclass(frozen=True)
class ManifestRow:
    path: str
    state: str
    mode: str
    length: int
    sha256: str
    git_oid: str

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in (
            "path", "state", "mode", "length", "sha256", "git_oid")}


def manifest_bytes(rows: tuple[ManifestRow, ...]) -> bytes:
    return json.dumps([row.as_dict() for row in rows], sort_keys=True,
                      ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


@dataclass(frozen=True)
class Snapshot:
    """A manifest plus captured added/modified bytes, keyed by prefixed SHA-256."""

    rows: tuple[ManifestRow, ...]
    blobs: Mapping[str, bytes]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "blobs", MappingProxyType(dict(self.blobs)))

    @property
    def payload(self) -> bytes:
        return manifest_bytes(self.rows)

    @property
    def digest(self) -> str:
        return sha256(self.payload)


def build_snapshot(base: Mapping[str, FileImage], current: Mapping[str, FileImage], *,
                   object_format: str, seed_skipped: frozenset[str] = frozenset()) -> Snapshot:
    """Accumulate against the seed, including deletions and mode-only changes.

    Seed skips are absent by design, never deletions. Reintroducing one is refused;
    ignore/instruction filtering belongs to the common capture before this function.
    """
    if object_format not in {"sha1", "sha256"}:
        raise SnapshotRefused("snapshot_damaged")
    rows, blobs = [], {}
    folded = set()
    for name in sorted(set(base) | set(current)):
        if any(name.casefold() == skip.casefold()
               or name.casefold().startswith(skip.casefold().rstrip("/") + "/")
               for skip in seed_skipped):
            if name in current:
                raise SnapshotRefused("reserved_path")
            continue
        _path(name)
        if name.casefold() in folded:
            raise SnapshotRefused("case_collision")
        folded.add(name.casefold())
        old, new = base.get(name), current.get(name)
        if any(image is not None and type(image) is not FileImage for image in (old, new)):
            raise SnapshotRefused("irregular_result")
        if old == new:
            continue
        state = "deleted" if new is None else "added" if old is None else "modified"
        image = old if new is None else new
        digest = sha256(image.data)
        rows.append(ManifestRow(name, state, image.mode, len(image.data), digest,
                                blob_oid(image.data, object_format)))
        if new is not None:
            blobs[digest] = image.data
    result = Snapshot(tuple(rows), blobs)
    validate_snapshot(result, object_format=object_format)
    return result


def read_manifest(payload: bytes, *, object_format: str) -> tuple[ManifestRow, ...]:
    """Read only canonical, closed rows; duplicate JSON keys cannot be canonical."""
    if len(payload) > MAX_MANIFEST_BYTES:
        raise SnapshotRefused("result_too_large")
    try:
        values = json.loads(payload)
        if type(values) is not list or any(type(row) is not dict or set(row) != _FIELDS
                                          for row in values):
            raise ValueError("shape")
        rows = tuple(ManifestRow(**row) for row in values)
        _validate_rows(rows, object_format)
        if manifest_bytes(rows) != payload:
            raise ValueError("noncanonical")
        return rows
    except (TypeError, ValueError, UnicodeError):
        raise SnapshotRefused("snapshot_damaged") from None


def _validate_rows(rows: tuple[ManifestRow, ...], object_format: str) -> None:
    if object_format not in {"sha1", "sha256"}:
        raise SnapshotRefused("snapshot_damaged")
    if len(rows) > MAX_FILES:
        raise SnapshotRefused("result_too_large")
    names, total = [], 0
    for row in rows:
        if type(row) is not ManifestRow:
            raise SnapshotRefused("snapshot_damaged")
        names.append(_path(row.path))
        if (row.state not in {"added", "modified", "deleted"}
                or row.mode not in {"100644", "100755"}
                or type(row.length) is not int or row.length < 0
                or type(row.sha256) is not str or _SHA.fullmatch(row.sha256) is None
                or type(row.git_oid) is not str
                or re.fullmatch(r"[0-9a-f]{" + ("40" if object_format == "sha1" else "64")
                                + r"}", row.git_oid) is None):
            raise SnapshotRefused("snapshot_damaged")
        if row.state != "deleted":
            total += row.length
    if names != sorted(set(names)) or len({name.casefold() for name in names}) != len(names):
        raise SnapshotRefused("snapshot_damaged")
    if total > MAX_BYTES or len(manifest_bytes(rows)) > MAX_MANIFEST_BYTES:
        raise SnapshotRefused("result_too_large")


def validate_snapshot(snapshot: Snapshot, *, object_format: str) -> None:
    _validate_rows(snapshot.rows, object_format)
    wanted = {row.sha256 for row in snapshot.rows if row.state != "deleted"}
    if set(snapshot.blobs) != wanted:
        raise SnapshotRefused("snapshot_damaged")
    for row in snapshot.rows:
        if row.state == "deleted":
            continue
        data = snapshot.blobs[row.sha256]
        if (type(data) is not bytes or len(data) != row.length or sha256(data) != row.sha256
                or blob_oid(data, object_format) != row.git_oid):
            raise SnapshotRefused("snapshot_damaged")
