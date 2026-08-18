"""The dsh harness's durability and evidence door, confined to one module.

The harness adapter needs a handful of filesystem facts and nothing else: a
FRESH profile home per spawn, a marker that survives a crash so a task is never
run twice, the instruction TEXT the task is actually asked to do, and content
digests of the authorized work tree so verification can read what actually
changed instead of believing what the task said. They live here, apart from the
adapter's value logic, for the same reason the owned-process runner lives apart
from the adapters that use it: a door should be one small module a reviewer can
read whole.

This is a durability door, NOT an execution door. It imports no subprocess, no
socket and no import machinery, and the package-wide door guard checks that here
exactly as it checks every other module -- the exemption this module carries is
only from the adapters' value-core import allowlist, never from the execution
ban.

EVERY name this door writes through is proved CONTAINED first, with the same
typed relation `conductor.command.containment` already holds for the preview's
run route and for the owned runner's cwd: `os.lstat` alone, following nothing,
classifying a symbolic link, an NTFS junction and any other reparse point by its
own tag, and refusing a store-owned file that is not regular or that carries a
second hard link. The root itself is a component of that route, because a portal
standing AT a container adopts external state exactly as one standing inside it
does. Without that walk a portal planted at `.dsh-home`, `.dsh-marker`,
`instructions` or `work` made this door create durable state outside the project
root it is bound to -- which is what it did before this walk existed.

The evidence walk is the same relation read rather than written. It never
follows a name: a portal is recorded by its typed kind, a file whose bytes also
answer to another name is recorded as `hard_link`, and neither is ever read for
content. Evidence cannot be forged by pointing a name inside the tree at bytes
outside it.

Cleanup is the same relation again, and it is the one place where getting it
wrong is worse than the leak it fixes. Every delete is bounded to ONE fixed
root -- `<project>/.dsh-home` -- and to a container this workspace itself
minted. A portal met inside such a container is removed by its OWN entry, so
whatever it named keeps every byte; a portal standing where a home would stand
is refused and named, never touched, because this door did not mint it and
cannot say whose it is. A name whose kind cannot be established at all refuses
rather than being guessed at.

Two properties stay mechanical rather than advisory. A home is created with
``exist_ok=False``, so reusing one is an error rather than a silent overwrite.
And the containment walk reads and then acts, so a writer that swaps a component
between the check and the write is not stopped: within one project this door is
single-writer by contract, and against a concurrent adversary the boundary is
best-effort, exactly as the preview's route gate states of itself.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from ..containment import (
    RouteViolation,
    RouteViolationCode,
    first_directory_violation,
    portal_violation,
    render_route_violation,
)

#: Subtrees this door owns beneath the project root.
WORK_DIR = "work"
HOME_DIR = ".dsh-home"
MARKER_DIR = ".dsh-marker"
INSTRUCTION_DIR = "instructions"
#: The one name shape an instruction is read from, and the bound on its size: a
#: task is a task, not a payload, and an unbounded read is an unbounded prompt.
INSTRUCTION_SUFFIX = ".md"
INSTRUCTION_LIMIT = 64 * 1024
#: Windows marks a reparse DIRECTORY here; removing its own entry needs rmdir.
_DIRECTORY_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_DIRECTORY", 0x10)


class WorkspaceNotContained(RuntimeError):
    """A name this door must write or read through is not locally contained."""


def _refuse(violation: RouteViolation) -> WorkspaceNotContained:
    return WorkspaceNotContained(render_route_violation(violation))


def _component(name: object) -> str:
    """Prove one route part names a child, never a route of its own."""
    if type(name) is not str or not name or name in (os.curdir, os.pardir):
        raise WorkspaceNotContained(f"{name!r} is not a single route component")
    separators = {os.sep, os.altsep or os.sep, "/", ":", "\x00"}
    if any(mark in name for mark in separators):
        raise WorkspaceNotContained(f"{name!r} is not a single route component")
    return name


def _leaf(path: Path) -> os.stat_result | None:
    """Read one name without following it; absence is None, unreadable refuses.

    Absence and unreadability are deliberately told apart here, unlike in the
    shared ``lstat_or_none``: this door decides whether to CREATE at the name, so
    "nothing is there" and "I could not establish what is there" cannot share an
    answer.
    """
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise _refuse(
            RouteViolation(RouteViolationCode.UNREADABLE, path)) from error


def _remove_portal(path: Path, found: os.stat_result) -> None:
    """Remove a portal's OWN entry, never anything it names."""
    directory = bool(
        stat.S_ISDIR(found.st_mode)
        or getattr(found, "st_file_attributes", 0) & _DIRECTORY_ATTRIBUTE)
    if directory:
        path.rmdir()
    else:
        path.unlink()


def _remove_tree(root: Path) -> None:
    """Delete everything beneath ``root`` and then ``root``, following nothing."""
    directories: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        directories.append(current)
        for path in sorted(current.iterdir()):
            found = _leaf(path)
            if found is None:
                continue
            if portal_violation(path, found) is not None:
                _remove_portal(path, found)
            elif stat.S_ISDIR(found.st_mode):
                stack.append(path)
            else:
                path.unlink()
    for path in reversed(directories):
        path.rmdir()


@dataclass(frozen=True)
class DshWorkspace:
    """Every filesystem effect the harness is allowed, bound to one project root."""

    root: Path

    @classmethod
    def at(cls, root: str | os.PathLike[str]) -> "DshWorkspace":
        return cls(root=Path(root).resolve())

    # -- the one containment relation every road below goes through -------------

    def _directory_route(self, *parts: str) -> Path:
        """Prove the whole route, root included, is a local directory route."""
        walked, route = self.root, [self.root]
        for part in parts:
            walked = walked / _component(part)
            route.append(walked)
        violation = first_directory_violation(route)
        if violation is not None:
            raise _refuse(violation)
        return walked

    def _file_route(self, *parts: str) -> tuple[Path, os.stat_result | None]:
        """Prove the route to a FILE: local directories, a local, singly named leaf."""
        parent = self._directory_route(*parts[:-1])
        path = parent / _component(parts[-1])
        found = _leaf(path)
        if found is None:
            return path, None
        violation = portal_violation(path, found)
        if violation is None and not stat.S_ISREG(found.st_mode):
            violation = RouteViolation(RouteViolationCode.IRREGULAR_FILE, path)
        elif violation is None and found.st_nlink != 1:
            violation = RouteViolation(
                RouteViolationCode.HARD_LINK, path, link_count=found.st_nlink)
        if violation is not None:
            raise _refuse(violation)
        return path, found

    # -- the isolated, single-use profile home --------------------------------

    def homes_root(self) -> Path:
        """The ONE root every home cleanup below is bounded to."""
        return self.root / HOME_DIR

    def mint_home(self, name: str) -> Path:
        """A fresh home. ``exist_ok=False`` makes reuse a hard error, not a merge."""
        home = self._directory_route(HOME_DIR, name)
        home.mkdir(parents=True, exist_ok=False)
        return home

    def discard_home(self, home: str | os.PathLike[str]) -> None:
        """Delete ONE attempt home, bounded to the fixed homes root, or refuse.

        The owner is this workspace and the root is ``<project>/.dsh-home``:
        a path that does not stand directly beneath it is refused without a
        single entry being read, so this cleanup cannot reach outside its own
        root even when it is handed a path that does.
        """
        path = Path(home)
        if path.parent != self.homes_root():
            raise WorkspaceNotContained(
                f"{str(path)!r} is not a home beneath this workspace's fixed root")
        target = self._directory_route(HOME_DIR, path.name)
        found = _leaf(target)
        if found is None:
            return
        if not stat.S_ISDIR(found.st_mode):
            raise _refuse(RouteViolation(RouteViolationCode.NOT_DIRECTORY, target))
        _remove_tree(target)

    def sweep_homes(self) -> tuple[str, ...]:
        """Discard every home a crashed attempt left, naming what it refused.

        A portal or a non-directory standing where a home would stand was never
        minted here, so it is named and left exactly as found; the names returned
        are the whole account of what this sweep declined to touch.
        """
        homes = self._directory_route(HOME_DIR)
        found = _leaf(homes)
        if found is None:
            return ()
        if not stat.S_ISDIR(found.st_mode):
            raise _refuse(RouteViolation(RouteViolationCode.NOT_DIRECTORY, homes))
        refused: list[str] = []
        for path in sorted(homes.iterdir()):
            entry = _leaf(path)
            if entry is None:
                continue
            if (portal_violation(path, entry) is not None
                    or not stat.S_ISDIR(entry.st_mode)):
                refused.append(path.name)
                continue
            _remove_tree(path)
        return tuple(refused)

    # -- the crash-proof marker -----------------------------------------------

    def marker_path(self, action_id: str) -> Path:
        """The marker's NAME. Nothing is established about it until it is read."""
        return self.root / MARKER_DIR / f"{action_id}.marker"

    def is_claimed(self, action_id: str) -> bool:
        """True once a marker exists, which outlives the process that wrote it."""
        _path, found = self._file_route(MARKER_DIR, f"{action_id}.marker")
        return found is not None

    def claim(self, action_id: str) -> None:
        """Claim the action BEFORE its task spawns, so a crash cannot un-claim it."""
        marker, _found = self._file_route(MARKER_DIR, f"{action_id}.marker")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(action_id, encoding="utf-8", newline="\n")

    # -- the instruction the task is actually asked to do ----------------------

    def read_instruction(self, instruction_ref: str) -> str:
        """The instruction TEXT, read from ONE contained name, or refuse.

        A dispatch that cannot read the instruction is refused by the caller
        rather than sent a sentence built from the reference alone: a prompt that
        is not the task is worse than no prompt at all.
        """
        path, found = self._file_route(
            INSTRUCTION_DIR, f"{_component(instruction_ref)}{INSTRUCTION_SUFFIX}")
        if found is None:
            raise WorkspaceNotContained(f"no instruction stands at {str(path)!r}")
        if found.st_size > INSTRUCTION_LIMIT:
            raise WorkspaceNotContained(
                f"the instruction at {str(path)!r} is past the "
                f"{INSTRUCTION_LIMIT} byte bound this door reads")
        failed = False
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, ValueError):  # noqa: BLE001 -- keep no decoder graph
            failed = True
            text = ""
        if failed or not text.strip() or "\x00" in text:
            raise WorkspaceNotContained(
                f"the instruction at {str(path)!r} is not readable task text")
        return text

    # -- the authorized work tree and its evidence ----------------------------

    def work_root(self) -> Path:
        root = self._directory_route(WORK_DIR)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def work_dir(self, work_item_id: str) -> Path:
        self.work_root()
        work = self._directory_route(WORK_DIR, work_item_id)
        work.mkdir(parents=True, exist_ok=True)
        return work

    def digest_work_tree(self) -> dict[str, str]:
        """Content digests of every LOCAL regular file under the work tree.

        A portal and an aliased file are recorded by their typed kind and never
        by content: a change of kind is still a change, while bytes that lie
        elsewhere -- or that answer to a second name -- are never read as this
        task's evidence.
        """
        base = self._directory_route(WORK_DIR)
        rows: dict[str, str] = {}
        found = _leaf(base)
        if found is None or not stat.S_ISDIR(found.st_mode):
            return rows
        stack = [base]
        while stack:
            for path in sorted(stack.pop().iterdir()):
                relative = path.relative_to(base).as_posix()
                entry = _leaf(path)
                if entry is None:
                    continue
                violation = portal_violation(path, entry)
                if violation is not None:
                    rows[relative] = violation.code.value
                elif stat.S_ISDIR(entry.st_mode):
                    stack.append(path)
                elif not stat.S_ISREG(entry.st_mode):
                    rows[relative] = RouteViolationCode.IRREGULAR_FILE.value
                elif entry.st_nlink != 1:
                    rows[relative] = RouteViolationCode.HARD_LINK.value
                else:
                    rows[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return rows
