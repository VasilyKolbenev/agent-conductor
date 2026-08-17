"""The dsh harness's durability and evidence door, confined to one module.

The harness adapter needs three filesystem facts and nothing else: a FRESH
profile home per spawn, a marker that survives a crash so a task is never run
twice, and content digests of the authorized work tree so verification can read
what actually changed instead of believing what the task said. All three live
here, apart from the adapter's value logic, for the same reason the owned-process
runner lives apart from the adapters that use it: a door should be one small
module a reviewer can read whole.

This is a durability door, NOT an execution door. It imports no subprocess, no
socket and no import machinery, and the package-wide door guard checks that here
exactly as it checks every other module -- the exemption this module carries is
only from the adapters' value-core import allowlist, never from the execution
ban.

Two properties are mechanical rather than advisory. A home is created with
``exist_ok=False``, so reusing one is an error rather than a silent overwrite.
And the digest walk never follows a symlink: a link is recorded by name and its
target is never read, so evidence cannot be forged by pointing inside the tree at
a file outside it.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

#: Subtrees this door owns beneath the project root.
WORK_DIR = "work"
HOME_DIR = ".dsh-home"
MARKER_DIR = ".dsh-marker"


@dataclass(frozen=True)
class DshWorkspace:
    """Every filesystem effect the harness is allowed, bound to one project root."""

    root: Path

    @classmethod
    def at(cls, root: str | os.PathLike[str]) -> "DshWorkspace":
        return cls(root=Path(root).resolve())

    # -- the isolated, single-use profile home --------------------------------

    def mint_home(self, name: str) -> Path:
        """A fresh home. ``exist_ok=False`` makes reuse a hard error, not a merge."""
        home = self.root / HOME_DIR / name
        home.mkdir(parents=True, exist_ok=False)
        return home

    # -- the crash-proof marker -----------------------------------------------

    def marker_path(self, action_id: str) -> Path:
        return self.root / MARKER_DIR / f"{action_id}.marker"

    def is_claimed(self, action_id: str) -> bool:
        """True once a marker exists, which outlives the process that wrote it."""
        return self.marker_path(action_id).exists()

    def claim(self, action_id: str) -> None:
        """Claim the action BEFORE its task spawns, so a crash cannot un-claim it."""
        marker = self.marker_path(action_id)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(action_id, encoding="utf-8", newline="\n")

    # -- the authorized work tree and its evidence ----------------------------

    def work_root(self) -> Path:
        root = self.root / WORK_DIR
        root.mkdir(parents=True, exist_ok=True)
        return root

    def work_dir(self, work_item_id: str) -> Path:
        work = self.work_root() / work_item_id
        work.mkdir(parents=True, exist_ok=True)
        return work

    def digest_work_tree(self) -> dict[str, str]:
        """Content digests of every regular file under the work tree."""
        base = self.root / WORK_DIR
        rows: dict[str, str] = {}
        if not base.is_dir():
            return rows
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base).as_posix()
            if path.is_symlink():
                # Recorded, never followed: a link is a name, not evidence.
                rows[relative] = "symlink"
                continue
            if not path.is_file():
                continue
            rows[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return rows
