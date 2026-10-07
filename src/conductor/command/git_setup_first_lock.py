"""Ownership of `index.lock` proved by the whole binding, and the moves that never replace (S4).

An `index.lock` is this product's only when it is a plain regular file whose every extra name is
this operation's own, and whose bytes carry this operation's whole binding: the digest of the
verified op record, the marker's nonce and terms hash, the expected tree, the entry count and the
object format (`git_setup_first_index.verify_binding`). An empty file is not: Git creates its lock
empty before it writes, so an empty lock is somebody's `git add` in progress. Neither are the
bytes Git itself writes for an empty index, the product's own bytes without their marker, or a
file that only carries this operation's marker. Nothing here follows a link, reads more than the
index limit, or removes a name it has not proved; a name whose state cannot be read is somebody
else's, never absent.

The moves never replace (review ruling OD-2): Windows renames, which refuses an existing target,
and every other system links and then unlinks. No call of this module replaces a name, and a file
system that refuses a link is a refusal, never a reason to try another call. A move by link that
dies between its two halves leaves two names for one inode (three, with the copy): `lock_state`
counts the extra names and accepts only this operation's own copy and its own installed index
among them, so the decision table can finish such an operation and never calls its lock foreign.

Pure file operations on one folder (`git_dir`): no process, no Git. The bytes come from the
verified install file of the op record, never from a rebuild.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

from .containment import portal_violation
from .git_setup_first_index import Binding, verify_binding
from .git_setup_first_records import INDEX_LIMIT
from .git_setup_first_resume import Lock
from .git_setup_records import SetupRefused
from .run_files import _O_BINARY, _write_all

LOCK, INDEX = "index.lock", "index"
#: Whether a name is moved by a link and an unlink. A fact of the host (Windows renames); a test
#: sets it to run the link road, and its two-name states, on a host that renames.
LINK_MOVES = os.name != "nt"
_unlink = os.unlink          # a fault seam: tests make the second half of a move fail
_MISSING, _ODD = "missing", "odd"


class NameTaken(Exception):
    """The name to take already exists; nothing was replaced."""


class MoveRefused(Exception):
    """The file system refused the move for another reason than a taken name; nothing moved."""


def copy_path(git_dir: Path, nonce: str) -> Path:
    """The operation's private copy, beside the target so that a move stays on one volume."""
    return git_dir / f"conduct-first-index-{nonce}"


def _look(path: Path) -> os.stat_result | str:
    """The lstat of a plain regular file; `missing`, or `odd` for a link, a portal, a non-file
    and a name whose state cannot be read (never taken for an absent one)."""
    try:
        found = os.lstat(path)
    except FileNotFoundError:
        return _MISSING
    except OSError:
        return _ODD
    if portal_violation(path, found) is not None or not stat.S_ISREG(found.st_mode):
        return _ODD
    return found


def _stamp(found: os.stat_result) -> tuple[int, int, int, int]:
    return found.st_dev, found.st_ino, found.st_size, found.st_mtime_ns


def _bytes_of(path: Path, found: os.stat_result) -> bytes | None:
    """The bytes of a plain file, bounded; None when too big or changed under the read."""
    if found.st_size > INDEX_LIMIT:
        return None
    try:
        with open(path, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (found.st_dev, found.st_ino):
                return None
            data = stream.read(INDEX_LIMIT + 1)
    except OSError:
        return None
    return data if len(data) == found.st_size else None


def _shares(path: Path, found: os.stat_result) -> bool:
    """Whether `path` is a plain file that is the very inode `found` describes. A file system
    that gives no file id cannot say so, and is never taken to."""
    other = _look(path)
    if isinstance(other, str) or not found.st_ino or not other.st_ino:
        return False
    return (other.st_dev, other.st_ino) == (found.st_dev, found.st_ino)


def _own_names(found: os.stat_result, *others: Path) -> int:
    """How many of `others` are further names of the file `found` describes."""
    return sum(_shares(other, found) for other in others)


def _prove(git_dir: Path, binding: Binding) -> os.stat_result | None:
    """The stat of index.lock when the WHOLE binding proves it is this operation's, else None."""
    path = git_dir / LOCK
    found = _look(path)
    if isinstance(found, str):
        return None
    # Every extra name must be this operation's own copy or its own installed index (the states
    # of one inode after a move by link): one name more than those makes it somebody else's.
    own = _own_names(found, copy_path(git_dir, binding.nonce), git_dir / INDEX)
    if found.st_nlink != 1 + own:
        return None
    data = _bytes_of(path, found)
    return found if data is not None and verify_binding(data, binding) else None


def lock_state(git_dir: Path, binding: Binding) -> Lock:
    """NONE when there is no name, OWN when the whole binding proves it, FOREIGN otherwise."""
    if _look(git_dir / LOCK) == _MISSING:
        return Lock.NONE
    return Lock.OWN if _prove(git_dir, binding) is not None else Lock.FOREIGN


def ensure_copy(git_dir: Path, nonce: str, data: bytes) -> None:
    """Lay the private copy down from the durable bytes; replace only a copy never finished.

    Raises:
        SetupRefused: `setup_damaged` for a copy that is not a plain file, or holds other bytes
            than a start of `data`, or a start that has another name. It is never deleted then.
    """
    path = copy_path(git_dir, nonce)
    found = _look(path)
    if found == _ODD:
        raise SetupRefused("setup_damaged")
    if not isinstance(found, str) and _is_whole_or_cleared(path, found, data):
        return
    _write_new(path, data)


def _is_whole_or_cleared(path: Path, found: os.stat_result, data: bytes) -> bool:
    """True when the standing copy holds all of `data`; a copy that holds only a start of it
    (a write that died) is removed and False says to write it again; anything else is damage."""
    held = _bytes_of(path, found)
    if held == data:
        return True
    unfinished = held is not None and len(held) < len(data) and data.startswith(held)
    if not unfinished or found.st_nlink != 1:
        raise SetupRefused("setup_damaged")
    _unlink(path)
    return False


def drop_copy(git_dir: Path, nonce: str, data: bytes) -> None:
    """Remove this operation's own copy NAME, proved by its bytes; else leave it.

    The copy may still be another name of the lock or of the installed index, or of both (a move
    that died between its two halves); unlinking only this name leaves the others intact. It is
    dropped only when every extra name it has is one of those two.
    """
    path = copy_path(git_dir, nonce)
    found = _look(path)
    if isinstance(found, str) or _bytes_of(path, found) != data:
        return
    if found.st_nlink == 1 + _own_names(found, git_dir / LOCK, git_dir / INDEX):
        _unlink(path)


def take_lock(git_dir: Path, nonce: str, data: bytes) -> None:
    """Move the copy onto index.lock without replacing anything (S4 step 3).

    Raises:
        NameTaken: `index.lock` exists; it is untouched and the copy still stands.
        MoveRefused: The file system refused the move; nothing moved.
        SetupRefused: The copy is damaged (see `ensure_copy`).
    """
    ensure_copy(git_dir, nonce, data)
    _move(copy_path(git_dir, nonce), git_dir / LOCK)


def install_index(git_dir: Path, binding: Binding, data: bytes) -> bool:
    """Drop the own copy name, re-prove the lock, then move it onto `index` without replacing.

    The copy name goes first so that the driver itself never makes the three names of one inode
    (copy, lock, index); the proof still counts them, so a state left by hand or by an earlier
    build is completed and not stranded (S4 step 6).

    Returns:
        False when the whole binding does not prove the lock to be this operation's; nothing moved.

    Raises:
        NameTaken: `index` exists; it is untouched and the lock still stands.
        MoveRefused: The file system refused the move; nothing moved.
    """
    drop_copy(git_dir, binding.nonce, data)
    if _prove(git_dir, binding) is None:
        return False
    _move(git_dir / LOCK, git_dir / INDEX)
    return True


def release_own_lock(git_dir: Path, binding: Binding) -> bool:
    """Remove index.lock only when the whole binding proves it is ours and the file did not change.

    Returns:
        True when the lock name was removed; False, with nothing removed, when it was not proved
        or changed between the proof and the removal.
    """
    found = _prove(git_dir, binding)
    if found is None:
        return False
    again = _look(git_dir / LOCK)
    if isinstance(again, str) or _stamp(again) != _stamp(found):
        return False
    _unlink(git_dir / LOCK)
    return True


def _move(source: Path, target: Path) -> None:
    """Move `source` to `target` and refuse an existing target; nothing is ever replaced."""
    if os.name != "nt" or LINK_MOVES:
        _move_by_link(source, target)
    else:
        _move_by_rename(source, target)


def _move_by_rename(source: Path, target: Path) -> None:
    """The Windows move: one rename, which refuses an existing target and leaves one name."""
    try:
        os.rename(source, target)
    except OSError as error:
        if os.path.lexists(target):
            raise NameTaken(target.name) from error
        raise MoveRefused(target.name) from error


def _move_by_link(source: Path, target: Path) -> None:
    """The move of every other system: a link (refused by an existing name), then an unlink."""
    try:
        os.link(source, target)
    except FileExistsError as error:
        raise NameTaken(target.name) from error
    except OSError as error:
        raise MoveRefused(target.name) from error
    _unlink(source)


def _write_new(path: Path, data: bytes) -> None:
    """Create `path` exclusively and write all of `data` into it, synced."""
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_BINARY, 0o644)
    except FileExistsError:
        raise SetupRefused("setup_damaged") from None
    try:
        _write_all(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
