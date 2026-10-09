"""The folders below a plain `.git` that Git writes through when a first commit is made.

The project's write guard covers the root and the tracked product paths, not the places where Git
puts its own files: a loose object goes into `objects/<two hex digits>/`, a new branch into
`refs/heads/<name>` (the name may nest), and its reflogs into `logs/refs/heads/<name>` and
`logs/HEAD`. A symlink, a junction or any other reparse point on such a path sends the write
outside the project. These checks read the existing names on the actual destinations with `lstat`,
top down and following nothing, and refuse `unsafe_git_route` at the first portal. A name that does
not exist yet is Git's to create as a plain folder, and a file where a folder belongs is Git's own
refusal to give. A passing check proves the route only at the instant it was read: it is not
isolation from a process that swaps a folder between the check and the write.
"""
from __future__ import annotations

import os
import stat
import string
from collections.abc import Sequence
from pathlib import Path

from .containment import portal_violation
from .git_setup_records import SetupRefused

_HEX = frozenset(string.hexdigits)
_BAD_PART = frozenset("\\:\0")


def _portal_on(top: Path, parts: Sequence[str]) -> bool:
    """Walk `parts` below `top` without following anything: True at the first existing portal.

    The walk stops quietly at a name that is absent (nothing below it exists) and at one that is
    not a folder (nothing can be written through it); a name that exists but cannot be read is
    never taken for a plain one."""
    walked = top
    for part in parts:
        walked = walked / part
        try:
            found = os.lstat(walked)
        except FileNotFoundError:
            return False
        except OSError:
            return True
        if portal_violation(walked, found) is not None:
            return True
        if not stat.S_ISDIR(found.st_mode):
            return False
    return False


def _is_fan_out(name: str) -> bool:
    """A folder of loose objects is two hex digits (in either case: a name is the same file
    system object on a host that ignores case)."""
    return len(name) == 2 and all(c in _HEX for c in name)


def objects_route(git_dir: Path) -> None:
    """Refuse `unsafe_git_route` when a loose object could be written through a portal.

    The tree and the commit are named only once they are written, so every existing fan-out
    folder is judged, with `objects` itself; a folder Git creates later is a plain one.

    Raises:
        SetupRefused: `unsafe_git_route`; nothing was written.
    """
    objects = git_dir / "objects"
    refused = SetupRefused("unsafe_git_route")
    if _portal_on(git_dir, ("objects",)):
        raise refused
    try:
        names = os.listdir(objects)
    except (FileNotFoundError, NotADirectoryError):
        return
    except OSError:
        raise refused from None
    if any(_is_fan_out(name) and _portal_on(objects, (name,)) for name in names):
        raise refused


def ref_route(git_dir: Path, target_ref: str) -> None:
    """Refuse `unsafe_git_route` when the ref or either of its reflogs lies behind a portal.

    Every existing component is judged, the nested ones of the branch name included: the ref
    `refs/heads/a/b`, its reflog `logs/refs/heads/a/b` and the reflog of `HEAD`, which Git appends
    to when the branch HEAD names moves.

    Raises:
        SetupRefused: `unsafe_git_route`; nothing was written.
    """
    parts = tuple(target_ref.split("/"))
    if any(not part or part in (".", "..") or _BAD_PART & set(part) for part in parts):
        raise SetupRefused("unsafe_git_route")
    routes = (parts, ("logs", *parts), ("logs", "HEAD"))
    if any(_portal_on(git_dir, route) for route in routes):
        raise SetupRefused("unsafe_git_route")


def dot_git_is_no_portal(root: Path) -> None:
    """Refuse `unsafe_git_route` when the name `<root>/.git` is itself a portal.

    Git names the target of a link or a junction as the git dir, so a route judged by Git's answer
    has lost the name that led there. This reads the name first. A `.git` that is a regular file
    (a linked worktree) is not a portal and passes: its common directory has its own contract.

    Raises:
        SetupRefused: `unsafe_git_route`; nothing was written.
    """
    named = Path(root) / ".git"
    try:
        found = os.lstat(named)
    except FileNotFoundError:
        return                                   # no repository here: Git's answer says so
    except OSError:
        raise SetupRefused("unsafe_git_route") from None
    if portal_violation(named, found) is not None:
        raise SetupRefused("unsafe_git_route")
