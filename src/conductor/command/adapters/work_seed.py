"""Walk the authorized work tree: content digests and bounded inline reads.

Extracted from the workspace door when it reached its module limit, so the rules
that read the work tree can change without touching the door itself. Both walks
take a base directory the door has already proved contained, and the two readers
they need from the door -- the one that looks at a name without following it and
the one that hashes a leaf -- so this module holds no route of its own and does
not import the door.
"""
from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable
from pathlib import Path

from ..containment import RouteViolationCode, portal_violation


class CaptureRefused(ValueError):
    pass


def capture_work_tree(base, leaf, read_file, *, max_files=7000, max_bytes=128 * 1024 * 1024):
    """One bounded byte capture; a portal/alias never supplies snapshot content.

    File modes are raw stat bits. The consumer chooses Git modes against the seed.
    The seed permits 5000 files/64 MiB and its accumulated diff 2000 rows/64 MiB. Their
    sum bounds this read without charging unchanged seed bytes to the diff twice.
    """
    result, total = {}, 0
    found = leaf(base)
    if found is None or not stat.S_ISDIR(found.st_mode):
        raise CaptureRefused("material_unavailable")
    stack = [base]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            entry = leaf(path)
            if entry is None or portal_violation(path, entry) is not None:
                raise CaptureRefused("irregular_result")
            if stat.S_ISDIR(entry.st_mode):
                stack.append(path)
                continue
            if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
                raise CaptureRefused("irregular_result")
            if len(result) >= max_files or total + entry.st_size > max_bytes:
                raise CaptureRefused("result_too_large")
            _digest, data = read_file(path, entry, True, max_bytes - total)
            if data is None:
                raise CaptureRefused("result_too_large")
            result[path.relative_to(base).as_posix()] = (entry.st_mode, data)
            total += len(data)
    return result


def work_modes(base, leaf):
    """Recheck executable bits without a second content capture for the frame."""
    result, stack = {}, [base]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            entry = leaf(path)
            if entry is None or portal_violation(path, entry) is not None:
                raise CaptureRefused("irregular_result")
            if stat.S_ISDIR(entry.st_mode):
                stack.append(path)
            elif stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1:
                result[path.relative_to(base).as_posix()] = bool(entry.st_mode & 0o111)
            else:
                raise CaptureRefused("irregular_result")
    return result


def digest_work_tree(
        base: Path, leaf: Callable[[Path], os.stat_result | None],
) -> dict[str, str]:
    """Digest every local regular file under ``base``, keyed relative to it.

    The contract, and the reason a portal or an aliased file is recorded by
    kind rather than by content, is on ``HarnessWorkspace.digest_work_tree``.
    """
    rows: dict[str, str] = {}
    found = leaf(base)
    if found is None or not stat.S_ISDIR(found.st_mode):
        return rows
    stack = [base]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            relative = path.relative_to(base).as_posix()
            entry = leaf(path)
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


def read_work_tree(
        base: Path, work_root: Path, changed: tuple[str, ...], budget: int,
        leaf: Callable[[Path], os.stat_result | None],
        read_file: Callable[[Path, os.stat_result, bool, int], tuple[str, bytes | None]],
) -> tuple[dict[str, str], dict[str, bytes]]:
    """List the work item at ``base``, keyed relative to ``work_root``.

    Only changed regular leaves within ``budget`` are inlined; the contract is
    on ``HarnessWorkspace.read_work_tree``, which validates its arguments before
    this walk runs.
    """
    tree, contents = {}, {}
    if leaf(base) is None:
        return tree, contents
    stack = [base]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            relative = path.relative_to(work_root).as_posix()
            entry = leaf(path)
            if entry is None:
                continue
            violation = portal_violation(path, entry)
            if violation is not None:
                tree[relative] = violation.code.value
            elif stat.S_ISDIR(entry.st_mode):
                stack.append(path)
            elif not stat.S_ISREG(entry.st_mode):
                tree[relative] = RouteViolationCode.IRREGULAR_FILE.value
            elif entry.st_nlink != 1:
                tree[relative] = RouteViolationCode.HARD_LINK.value
            else:
                digest, content = read_file(path, entry, relative in changed, budget)
                tree[relative] = digest
                if content is not None:
                    contents[relative] = content
    return tree, contents
