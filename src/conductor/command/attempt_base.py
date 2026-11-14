"""Prove selected before images from the seed tree. A view never starts Git.

Offline import stores only the Git trees on the selected paths and their old regular blobs.
Object names include their type and length in the hash. An absent leaf needs the same tree
proof as a present one; a missing archive object is never proof of an empty file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from ..ownership import write_guard
from .accept_capture import _included
from .accept_manifest import ManifestRow, SnapshotRefused, result_path, sha256
from .accept_snapshot import _folder, _put, _read
from .git_setup_facts import REAL_OBJECTS
from .path_admission import WindowsNameError, WindowsPathError
from .project_git import GitReadFailed
from .project_git_state import _checked
from .run_store import _root_gate

MAX_ROWS = 32
MAX_BLOB = 256 * 1024
MAX_TREE = 1024 * 1024
MAX_TOTAL = 4 * MAX_TREE
MAX_OBJECTS = 128
MAX_DEPTH = 32
_TREE_MODE = b"40000"
_FILE_MODES = {b"100644", b"100755"}
_MODES = _FILE_MODES | {_TREE_MODE, b"120000", b"160000"}


def _damaged():
    return SnapshotRefused("snapshot_damaged")


def _object_id(kind, raw, fmt):
    return hashlib.new(fmt, kind.encode("ascii") + b" " + str(len(raw)).encode("ascii")
                       + b"\0" + raw).hexdigest()


def _entries(raw, width):
    entries = {}
    pos = 0
    while pos < len(raw):
        zero = raw.find(b"\0", pos)
        if zero < 0 or zero + 1 + width > len(raw):
            raise _damaged()
        mode, sep, name = raw[pos:zero].partition(b" ")
        if (not sep or mode not in _MODES or name in (b"", b".", b"..")
                or b"/" in name or name in entries):
            raise _damaged()
        pos = zero + 1 + width
        oid = raw[zero + 1:pos].hex()
        entries[name] = (mode, oid)
    return entries


class _Proof:
    def __init__(self, fmt, load):
        self.fmt, self.load = fmt, load
        self.width = 20 if fmt == "sha1" else 32
        self.objects = {}
        self.trees = {}
        self.bytes = 0

    def raw(self, kind, oid):
        if type(oid) is not str or not re.fullmatch("[a-f0-9]{%d}" % (self.width * 2), oid):
            raise _damaged()
        key = (kind, oid)
        if key not in self.objects:
            ceiling = min(MAX_TREE if kind == "tree" else MAX_BLOB, MAX_TOTAL - self.bytes)
            if len(self.objects) >= MAX_OBJECTS:
                raise SnapshotRefused("result_too_large")
            data = self.load(kind, oid, ceiling)
            if len(data) > ceiling:
                raise SnapshotRefused("result_too_large")
            if _object_id(kind, data, self.fmt) != oid:
                raise _damaged()
            self.objects[key] = data
            self.bytes += len(data)
        return self.objects[key]

    def find(self, tree, parts):
        for index, part in enumerate(parts):
            if tree not in self.trees:
                self.trees[tree] = _entries(self.raw("tree", tree), self.width)
            entry = self.trees[tree].get(part.encode("utf-8"))
            if entry is None:
                return None
            mode, oid = entry
            if index + 1 == len(parts):
                if mode not in _FILE_MODES:
                    raise SnapshotRefused("base_unavailable")
                return mode.decode("ascii"), oid, self.raw("blob", oid)
            if mode != _TREE_MODE:
                raise SnapshotRefused("base_unavailable")
            tree = oid
        raise _damaged()


def _resolve(seed, rows, load):
    if len(rows) > MAX_ROWS:
        raise SnapshotRefused("result_too_large")
    if seed.source not in {"git", "empty"}:
        raise SnapshotRefused("base_unavailable")
    if seed.source == "git" and seed.object_format not in {"sha1", "sha256"}:
        raise _damaged()
    proof = _Proof(seed.object_format, load)
    before = {}
    seen = set()
    for row in rows:
        if not isinstance(row, ManifestRow) or row.state not in {"added", "modified", "deleted"}:
            raise _damaged()
        name = result_path(row.path)
        if name.casefold() in seen or not _included(name, seed):
            raise _damaged()
        seen.add(name.casefold())
        parts = name.split("/")
        if len(parts) > MAX_DEPTH:
            raise SnapshotRefused("result_too_large")
        found = None if seed.source == "empty" else proof.find(seed.base_tree, parts)
        if row.state == "added" and found is None:
            continue
        if row.state == "added" or found is None:
            raise _damaged()
        mode, oid, content = found
        same = (mode, oid, len(content), sha256(content)) == (
            row.mode, row.git_oid, row.length, row.sha256)
        if (row.state == "deleted") != same:
            raise _damaged()
        before[name] = content
    return before, proof


def _git_loader(root, git):
    def load(kind, oid, ceiling):
        # An unseeded parent repository must never be discovered on an object read.
        cmd = ["--no-optional-locks", "-C", str(root), "--git-dir=.git", *REAL_OBJECTS,
               "cat-file", kind, oid]
        answer = git(cmd, True, output_limit=ceiling + 1)
        if answer.truncated:
            raise SnapshotRefused("result_too_large")
        return _checked(answer)
    return load


def read_attempt_base(root, run_id, seed, rows, *, git=None, package_initializers=()):
    """Read exact old regular blobs by the immutable tree in seed. Omit proven added paths."""
    root = Path(root).resolve()
    folder = _folder(root, run_id) / "base"
    load = _git_loader(root, git) if git is not None else (
        lambda kind, oid, ceiling: _read(root, folder / oid, ceiling))
    try:
        before, proof = _resolve(seed, rows, load)
        # A test may import a changed function through its unchanged package initializer.
        # Share the same verified tree and object budget. Missing optional evidence cannot
        # invalidate before-images already obtained for the diff.
        for name in package_initializers:
            if (seed.source != "git" or not re.fullmatch(r"[a-zA-Z_]\w*/__init__\.py", name)
                    or not _included(name, seed)):
                continue
            try:
                entry = proof.find(seed.base_tree, name.split("/"))
            except (GitReadFailed, OSError, ValueError):
                continue
            if entry is not None:
                before[name] = entry[2]
        return before
    except (GitReadFailed, OSError, WindowsNameError, WindowsPathError, UnicodeError):
        raise SnapshotRefused("base_unavailable") from None


def import_attempt_base(target, run_id, seed, rows, git, *, source_root=None, sensitive=()):
    """Verify all base objects before explicitly publishing them into an owned archive."""
    from .adapters.independent_check import CheckFrameError, scan_material

    root = Path(target).resolve()
    try:
        folder = _folder(root, run_id) / "base"
        _, proof = _resolve(seed, rows, _git_loader(source_root or root, git))
        scan_material(tuple(proof.objects.values()), sensitive)
        with _root_gate(root).lock, write_guard(root):
            for (_, oid), raw in proof.objects.items():
                _put(root, folder / oid, raw)
    except CheckFrameError:
        raise SnapshotRefused("base_unavailable") from None
    except (GitReadFailed, OSError, WindowsNameError, WindowsPathError, UnicodeError):
        raise SnapshotRefused("base_unavailable") from None
