"""Structural containment checks shared by preview, Confirm, and process runners.

The checks follow no link: callers receive facts established with ``os.lstat``
and decide how their own public boundary phrases a refusal.  Passing proves the
route only at the instant it was read.  It is deliberately not an OS sandbox:
a concurrent component swap (check-then-act) and NTFS alternate data streams
are outside this structural door, while a ``RunStore`` project root is already
resolved from the operator's ``--dir`` choice.
"""
from __future__ import annotations

import os
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
STORE_OWNED_FILES = frozenset({"run.json", "config.json", "records.jsonl"})
RECEIPTS_DIR, RECEIPT_SUFFIX = "decisions", ".json"


class StoreRoute(Protocol):
    """The path-only part of RunStore needed by this module."""

    project_root: Path
    runs_root: Path

    def run_path(self, run_id: str) -> Path: ...


def detected_portal(found: os.stat_result) -> str | None:
    """Name a symlink/junction/other reparse point, else return ``None``."""
    if stat.S_ISLNK(found.st_mode):
        return "a symbolic link"
    tag = getattr(found, "st_reparse_tag", 0)
    if tag == JUNCTION_TAG:
        return "a directory junction"
    if tag:
        return f"a reparse point (tag {tag:#010x})"
    return None


def lstat_or_none(path: Path) -> os.stat_result | None:
    """Read one name without following it; ``None`` leaves its state unestablished.

    Absence and an unreadable name are deliberately not guessed apart here.
    Creation/replay owns their diagnostic and must still fail if it cannot act.
    """
    try:
        return os.lstat(path)
    except OSError:
        return None


def portal_entry(path: Path, portal: str) -> str:
    """One stable structural fact for a name whose content lies elsewhere."""
    return f"route: {str(path)!r} is {portal}: a name whose content lies elsewhere"


def first_directory_violation(paths: Iterable[Path]) -> str | None:
    """Find the first portal and stop before looking below it.

    A plain-file component is not classified here: preview historically leaves
    that state to RunStore's creation/replay refusal.  Callers that require a
    present directory use :func:`contained_directory` instead.
    """
    for path in paths:
        found = lstat_or_none(path)
        if found is None:
            continue
        portal = detected_portal(found)
        if portal is not None:
            return portal_entry(path, portal)
    return None


def owned_file_violations(run_path: Path) -> tuple[str, ...]:
    """Judge every present store-owned file as regular, local, and singly named.

    A second hard link makes the same bytes reachable through a name outside the
    inspected tree.  Writing or publishing at the owned name can then affect, or
    replace only one view of, state the caller cannot account for.  The relation
    is uniform over the three top-level files and receipt-shaped decision files.
    """
    receipts = run_path / RECEIPTS_DIR
    try:
        entries = sorted(receipts.iterdir())
    except OSError:
        entries = []
    violations: list[str] = []
    paths = (*(run_path / name for name in sorted(STORE_OWNED_FILES)), *entries)
    for path in paths:
        found = lstat_or_none(path)
        if found is None:
            continue
        portal = detected_portal(found)
        if portal is not None:
            violations.append(portal_entry(path, portal))
            continue
        if path.parent == receipts and (
                path.suffix != RECEIPT_SUFFIX or not stat.S_ISREG(found.st_mode)):
            continue
        if not stat.S_ISREG(found.st_mode):
            violations.append(
                f"route: {str(path)!r} is not a regular file where the store writes one")
        elif found.st_nlink != 1:
            violations.append(
                f"route: {str(path)!r} carries {found.st_nlink} hard links: "
                "its bytes stand at another name as well")
    return tuple(violations)


def run_route_violations(store: StoreRoute, run_id: str) -> tuple[str, ...]:
    """Inspect the whole writable store route and every owned file behind it."""
    run_path = store.run_path(run_id)
    first = first_directory_violation((
        store.project_root / "conductor", store.runs_root,
        run_path, run_path / RECEIPTS_DIR,
    ))
    return (first,) if first is not None else owned_file_violations(run_path)


def unowned_paths(run_path: Path, *, all_reparse: bool = False) -> tuple[str, ...]:
    """Name objects below a run that RunStore neither reads nor writes.

    Plain empty directories carry no bytes and remain admissible.  Portals are
    named by their local entry and never traversed; receipt-shaped files are
    owned only directly beneath ``decisions``.
    """
    receipts = run_path / RECEIPTS_DIR
    unowned: list[str] = []
    stack = [run_path]
    while stack:
        entries = sorted(stack.pop().iterdir())
        for path in entries:
            found = lstat_or_none(path)
            if found is None:
                raise OSError(f"cannot lstat run object {str(path)!r}")
            name = path.relative_to(run_path).as_posix()
            tag = getattr(found, "st_reparse_tag", 0)
            is_portal = stat.S_ISLNK(found.st_mode) or tag == JUNCTION_TAG
            if is_portal or (all_reparse and tag):
                unowned.append(name)
            elif stat.S_ISDIR(found.st_mode):
                stack.append(path)
            elif path.parent == run_path and path.name in STORE_OWNED_FILES:
                continue
            elif (path.parent == receipts and path.suffix == RECEIPT_SUFFIX
                  and stat.S_ISREG(found.st_mode)):
                continue
            else:
                unowned.append(name)
    return tuple(sorted(unowned))


def contained_directory(root: Path, relative: Path) -> tuple[Path, str | None]:
    """Return an unresolved contained directory and the first structural violation.

    ``root`` is the caller's already-resolved authority root.  ``relative`` must
    contain only a strict descendant route; no component is resolved or followed.
    """
    walked = root
    for part in relative.parts:
        walked = walked / part
        found = lstat_or_none(walked)
        if found is None:
            return walked, f"route: {str(walked)!r} does not exist or cannot be read"
        portal = detected_portal(found)
        if portal is not None:
            return walked, portal_entry(walked, portal)
        if not stat.S_ISDIR(found.st_mode):
            return walked, f"route: {str(walked)!r} is not a directory"
    return walked, None
