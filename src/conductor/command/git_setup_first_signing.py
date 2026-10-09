"""The first commit when Git is set to sign: the intent, the wait and the way back (plan Task 9).

The product never signs, never makes the commit and never moves a ref on this road. Before it
shows the owner anything it STORES the intent: the install bytes, the exact message in a file of
its own, and an operation record at `awaiting_signature` that holds every term the owner's commit
will later be judged against (who confirmed, the mode, the digest and its version, the branch, the
object format, the tree, the author as shown, the message digest). Only then does the refusal
`signing_required` go out with the three facts the two commands need.

A repeat reads that record, never a new preview: a preview of a folder that changed since would
carry another digest, and once the owner's commit exists the preview refuses `head_exists`. The
record has a table of its own, apart from the driver's: the ref is absent (the wait goes on) or it
is not. Nothing in this module can write a ref, a lock or an index.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NoReturn

from . import git_setup_first_records as records
from .accept_manifest import SnapshotRefused, sha256
from .accept_plumbing import ref_oid
from .accept_snapshot import _put, _read
from .git_setup_first_pending import message_path_of
from .git_setup_first_records import Op
from .git_setup_records import SetupRefused
from .project_git import GitReadFailed

#: A commit message of this product is a few lines; the file is read back at no more than this.
MESSAGE_LIMIT = 4096


class SigningWait(SetupRefused):
    """The refusal of a first commit that waits for the owner's signature.

    It is a `SetupRefused` of the reason `signing_required` that also carries the three facts the
    owner's two commands are built from: the tree, the branch and the file of the message."""

    def __init__(self, tree: str, target_ref: str, message_path: str) -> None:
        super().__init__("signing_required")
        self.tree, self.target_ref, self.message_path = tree, target_ref, message_path


def message_file(root: Path, op: Op) -> Path:
    """The file that holds the exact message, named by the first 32 hex of its digest."""
    return root / message_path_of(root, op)


def await_signature(root: Path, op: Op, install: bytes, message: bytes) -> NoReturn:
    """Store the intent, then refuse with the facts of the two commands.

    The message file goes first and the record last: the record is what names the others, so it
    never names a file that is not there. A crash between the steps leaves files that nothing
    names, and the next attempt writes the same bytes again. Nothing of `.git` is touched.

    Raises:
        SigningWait: Always, once the intent is stored.
        SetupRefused: `setup_damaged`, a stored file is not the one this intent would write.
    """
    if sha256(message) != op.message_sha256:
        raise SetupRefused("setup_damaged")
    try:
        _put(root, message_file(root, op), message)
    except SnapshotRefused:
        raise SetupRefused("setup_damaged") from None
    records.start(root, op, install)
    raise _waiting(root, op)


def _waiting(root: Path, op: Op) -> SigningWait:
    return SigningWait(op.expected_tree, op.target_ref, message_path_of(root, op))


def stored_message(root: Path, op: Op) -> bytes:
    """The message bytes of the stored intent, proved by the digest the record carries."""
    try:
        data = _read(root, message_file(root, op), MESSAGE_LIMIT)
    except (OSError, SnapshotRefused):
        raise SetupRefused("setup_damaged") from None
    if sha256(data) != op.message_sha256:
        raise SetupRefused("setup_damaged")
    return data


def _tree_present(root: Path, git, tree: str) -> None:
    """The tree the owner commits must still be an object of the repository."""
    answer = git(["--no-optional-locks", "-C", str(root), "cat-file", "-t", tree], True)
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if answer.exit_code != 0 or answer.truncated or answer.output.strip() != b"tree":
        raise SetupRefused("setup_damaged")


def _branch(op: Op) -> str:
    return op.target_ref.removeprefix("refs/heads/")


def wait(root: Path, git, op: Op) -> NoReturn:
    """Judge a wait whose terms still hold: the ref is absent, or it is not.

    The intent is checked first (the message file and the tree object), and a missing or damaged
    one is `setup_damaged` with nothing removed. While the ref is absent the answer is the same
    refusal as the first, built from the STORED intent. A ref that exists is not the product's
    commit: `head_exists`.

    Raises:
        SigningWait: The ref is absent and the owner has not made the commit yet.
        SetupRefused: `setup_damaged` or `head_exists`.
    """
    stored_message(root, op)
    _tree_present(root, git, op.expected_tree)
    if ref_oid(root, git, _branch(op)) is None:
        raise _waiting(root, op)
    raise SetupRefused("head_exists")


def supersede_wait(root: Path, git, op: Op) -> None:
    """Replace a wait whose terms changed, and only while the ref is absent (review ruling OD-6).

    Nothing of `.git` is the product's yet, so nothing is released. The operation record goes
    FIRST (`retire` then removes the install bytes), and the message file last, so a crash between
    the steps leaves a file that nothing names and never a record without its files. A ref that
    exists is judged, not replaced.

    Raises:
        SetupRefused: `head_exists`, the ref exists.
    """
    if ref_oid(root, git, _branch(op)) is not None:
        raise SetupRefused("head_exists")
    records.retire(root, op)
    _remove_message(root, op)


def _remove_message(root: Path, op: Op) -> None:
    """Remove the message file only when it is the plain file this intent wrote."""
    path = message_file(root, op)
    try:
        if os.path.lexists(path) and sha256(_read(root, path, MESSAGE_LIMIT)) == op.message_sha256:
            path.unlink()
    except (OSError, SnapshotRefused):
        return                                  # a file that is not the stored message is not ours
