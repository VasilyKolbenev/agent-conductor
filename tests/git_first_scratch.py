"""A scratch repository for the probes of the first-commit index bytes.

One repository per reader (`tests.git_first_readers`) and object format, made in a folder outside
every repository. It builds the index the way the product will: a tree from a private index, then
a second private index by `read-tree <tree>` and `update-index --refresh` under the pin. Every
command runs the reader's own Git, so on the `old_git` id both the commands that build the bytes
and the owner's commands that read them are the old Git's.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from conductor.command.git_setup_first_index import INDEX_PIN
from tests.git_first_readers import reader_binary
from tests.git_repo_helpers import git

#: The one line a Git that does not know the marker prints for it (the accepted cost).
NOTICE = "ignoring CNDT extension"


@dataclass(frozen=True)
class Scratch:
    folder: Path
    binary: str
    fmt: str

    @property
    def git_dir(self) -> Path:
        return self.folder / ".git"

    def run(self, *args, check=True, env=None):
        return git(*args, cwd=self.folder, check=check, binary=self.binary, env=env)

    def text(self, *args) -> str:
        return self.run(*args).stdout.decode().strip()

    def _private(self, label: str) -> Path:
        path = self.folder.parent / f"{self.folder.name}-{label}.index"
        path.unlink(missing_ok=True)
        return path

    def write(self, files: dict) -> None:
        """Write `files`, each stamped a minute in the past so that none can be racily clean
        against an index file written right after (Git doubts a stat time it cannot order)."""
        stamp = time.time() - 60
        for name, content in files.items():
            target = self.folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content if isinstance(content, bytes) else content.encode())
            os.utime(target, (stamp, stamp))

    def _tree_of_private_index(self, *before: tuple) -> str:
        built = self._private("a")
        env = {"GIT_INDEX_FILE": str(built)}
        for command in before:
            self.run(*command, env=env)
        tree = self.run("write-tree", env=env).stdout.decode().strip()
        built.unlink(missing_ok=True)
        return tree

    def tree(self, files: dict) -> str:
        """Write `files`, add everything to a private index and return its tree (object written)."""
        self.write(files)
        return self._tree_of_private_index(("add", "-A"))

    def empty_tree(self) -> str:
        """The empty tree of this object format, whatever the work tree holds."""
        return self._tree_of_private_index()

    def base(self, tree: str, rows: int, *, pin: bool = True) -> bytes:
        """The bytes the product builds for `tree`: `read-tree` then the refresh (when there are
        rows) into a private index; `pin=False` leaves the pin off to show what it keeps out."""
        built = self._private("b")
        env, flags = {"GIT_INDEX_FILE": str(built)}, (INDEX_PIN if pin else ())
        self.run(*flags, "read-tree", tree, env=env)
        if rows:
            self.run(f"--work-tree={self.folder}", *flags, "update-index", "--refresh", env=env)
        data = built.read_bytes()
        built.unlink()
        return data

    def commit(self, tree: str, message: str = "first") -> str:
        """A parentless commit of `tree`, objects only (no ref moves)."""
        return self.text("commit-tree", tree, "-m", message)

    def publish(self, commit: str) -> None:
        """Point the branch HEAD names at `commit`, as the product does before it installs."""
        self.run("update-ref", "HEAD", commit)

    def install(self, data: bytes) -> None:
        (self.git_dir / "index").write_bytes(data)

    def installed(self) -> bytes:
        return (self.git_dir / "index").read_bytes()

    def shared_indexes(self) -> list[str]:
        return sorted(path.name for path in self.git_dir.glob("sharedindex.*"))


def scratch(tmp_path: Path, which: str, fmt: str, name: str = "repo") -> Scratch:
    """An empty repository of `fmt` for the reader `which`; skips where that Git cannot make it."""
    binary = reader_binary(which)
    folder = tmp_path / f"{name}-{which}-{fmt}"
    folder.mkdir()
    made = git("init", "-q", f"--object-format={fmt}", cwd=folder, check=False, binary=binary)
    if made.returncode != 0:
        said = made.stderr.decode(errors="replace").strip()
        if fmt == "sha256":
            pytest.skip(f"this Git cannot make a SHA-256 repository: {said}")
        raise AssertionError(said)
    return Scratch(folder, binary, fmt)


def notice_lines(done) -> list[str]:
    """What the command wrote to stderr, one entry per line."""
    return done.stderr.decode(errors="replace").splitlines()
