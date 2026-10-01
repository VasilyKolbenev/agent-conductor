"""A fresh, plain Git index owned by this operation; no arbitrary environment override."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import struct
from contextlib import contextmanager
from pathlib import Path

from .accept_manifest import SnapshotRefused
from .accept_snapshot import _hold
from .path_admission import admit_file
from conductor.ownership import data_root


def _identity(path):
    found = os.lstat(path)
    return found.st_dev, found.st_ino


class OwnedIndex:
    def __init__(self, root, path, identity):
        self.root, self.path = root, path
        self._identity, self._lock_identity = identity, None

    def environment(self, root):
        if Path(root).resolve() != self.root or self.path.parent != data_root(self.root) / "git":
            raise SnapshotRefused("irregular_result")
        _hold(self.root, self.path)
        if _identity(self.path) != self._identity or os.path.lexists(str(self.path) + ".lock"):
            raise SnapshotRefused("irregular_result")
        return {"GIT_INDEX_FILE": str(self.path)}

    def observed(self):
        # Git updates an index with an atomic rename. Adopt only the plain result of this
        # completed owned command, then require that same identity during cleanup.
        _hold(self.root, self.path)
        self._identity = _identity(self.path)
        lock = self.path.with_name(self.path.name + ".lock")
        if os.path.lexists(lock):
            _hold(self.root, lock)
            self._lock_identity = _identity(lock)

    def close(self):
        for path, identity in ((self.path, self._identity),
                               (self.path.with_name(self.path.name + ".lock"), self._lock_identity)):
            if identity is None or not os.path.lexists(path):
                continue
            _hold(self.root, path)
            if _identity(path) != identity:
                raise SnapshotRefused("irregular_result")
            path.unlink()


@contextmanager
def temporary_index(root, acceptance_id, object_format):
    if re.fullmatch(r"acc-[0-9a-f]{32}", acceptance_id) is None or object_format not in {"sha1", "sha256"}:
        raise SnapshotRefused("irregular_result")
    root = Path(root).resolve()
    path = data_root(root) / "git" / f"index-{acceptance_id}-{secrets.token_hex(8)}"
    admit_file(path, "acceptance index")
    _hold(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _hold(root, path)
    header = struct.pack(">4sII", b"DIRC", 2, 0)
    with path.open("xb") as stream:
        stream.write(header + hashlib.new(object_format, header).digest())
        stream.flush()
        os.fsync(stream.fileno())
        found = os.fstat(stream.fileno())
        identity = found.st_dev, found.st_ino
    index = OwnedIndex(root, path, identity)
    try:
        index.environment(root)
        yield index
    finally:
        index.close()
