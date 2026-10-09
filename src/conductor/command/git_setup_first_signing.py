"""The first commit when Git is set to sign: the intent, the wait and the way back (plan Task 9).

The product never signs, never makes the commit and never moves a ref on this road. Before it
shows the owner anything it STORES the intent: the install bytes, the exact message in a file of
its own, and an operation record at `awaiting_signature` that holds every term the owner's commit
will later be judged against (who confirmed, the mode, the digest and its version, the branch, the
object format, the tree, the author as shown, the message digest). Only then does the refusal
`signing_required` go out with the three facts the two commands need.

A repeat reads that record, never a new preview: a preview of a folder that changed since would
carry another digest, and once the owner's commit exists the preview refuses `head_exists`. The
record has a table of its own, apart from the driver's: the ref is absent (the wait goes on), it
is the owner's recognised commit (the record moves to `ref_moved` with that commit and the driver
installs the index, as on the unsigned road), or it is anything else (`head_exists`). Nothing in
this module can write a ref, a lock or an index. The message file lives until the receipt of the
finished road stands; then the finish removes it, and only the plain file this intent wrote.

What is checked of the signature is that it is PRESENT: the commit carries the signature header of
its object format and the first line of that header is an armour line. Whether the signature is
valid, and whether its key is trusted, is not checked, and no program that could check it is run:
Git's `verify-commit`, `gpg` and `ssh-keygen` are never started, and nothing here reads
`gpg.program`. The receipt says `present`; it never says verified.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NoReturn

from . import git_setup_first_records as records
from .accept_manifest import SnapshotRefused, sha256
from .accept_plumbing import _AUTHOR, ref_oid
from .accept_snapshot import _put, _read
from .git_setup_facts import REAL_OBJECTS
from .git_setup_first_pending import message_path_of
from .git_setup_first_records import Op
from .git_setup_first_resume import REF_MOVED
from .git_setup_records import SetupRefused
from .project_git import GitReadFailed

#: A commit message of this product is a few lines; the file is read back at no more than this.
MESSAGE_LIMIT = 4096
#: The owner's commit is read once and at no more than this; a longer one is not the intended one.
COMMIT_LIMIT = 64 * 1024
#: The signature header of each object format, and the armour lines a signature begins with.
_HEADER = {"sha1": "gpgsig", "sha256": "gpgsig-sha256"}
_ARMOUR = frozenset({"-----BEGIN PGP SIGNATURE-----", "-----BEGIN SSH SIGNATURE-----",
                     "-----BEGIN SIGNED MESSAGE-----"})


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
    """The tree the owner commits must still be an object of the repository, under its own name."""
    answer = git(["--no-optional-locks", "-C", str(root), REAL_OBJECTS, "cat-file", "-t", tree],
                 True)
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if answer.exit_code != 0 or answer.truncated or answer.output.strip() != b"tree":
        raise SetupRefused("setup_damaged")


def _branch(op: Op) -> str:
    return op.target_ref.removeprefix("refs/heads/")


def wait(root: Path, git, op: Op) -> Op:
    """Judge a wait whose terms still hold: the ref is absent, or it is not.

    The intent is checked first (the message file and the tree object), and a missing or damaged
    one is `setup_damaged` with nothing removed. While the ref is absent the answer is the same
    refusal as the first, built from the STORED intent. A ref at the owner's recognised commit
    moves the record to `ref_moved` with that commit; the caller then hands it to the driver,
    which installs the index and never moves the ref. Any other commit at the ref is `head_exists`
    (an unsigned one included) and the record stays as it is.

    Returns:
        The record at `ref_moved`, carrying the commit the owner made.

    Raises:
        SigningWait: The ref is absent and the owner has not made the commit yet.
        SetupRefused: `setup_damaged` or `head_exists`.
    """
    message = stored_message(root, op)
    _tree_present(root, git, op.expected_tree)
    found = ref_oid(root, git, _branch(op))
    if found is None:
        raise _waiting(root, op)
    if not recognised(root, git, op, message, found):
        raise SetupRefused("head_exists")
    return records.advance(root, op, REF_MOVED, commit=found)


def supersede_wait(root: Path, git, op: Op) -> None:
    """Replace a wait whose terms changed, and only while the ref is absent (review ruling OD-6).

    Nothing of `.git` is the product's yet, so nothing is released. The operation record goes
    FIRST (`retire` then removes the install bytes), and the message file last, so a crash between
    the steps leaves a file that nothing names and never a record without its files. A ref that
    exists is judged, not replaced: the owner's recognised commit makes the changed terms
    `setup_terms_changed` (the original terms can still complete it), any other is `head_exists`.

    Raises:
        SetupRefused: `setup_terms_changed` or `head_exists`, the ref exists.
    """
    found = ref_oid(root, git, _branch(op))
    if found is not None:
        raise SetupRefused(
            "setup_terms_changed" if _is_ours(root, git, op, found) else "head_exists")
    records.retire(root, op)
    _remove_message(root, op)


def _is_ours(root: Path, git, op: Op, found: str) -> bool:
    """Whether the commit at the ref is the intended one; a lost message file says no."""
    try:
        message = stored_message(root, op)
    except SetupRefused:
        return False
    return recognised(root, git, op, message, found)


def remove_finished_message(root: Path, op: Op) -> None:
    """Remove the message file of a signed road whose receipt stands; nothing for an unsigned op.

    The owner's `commit-tree -F` was its only reader and the commit is recognised, so the file has
    no use left. It goes BEFORE the operation record is retired: a crash in between leaves the
    record beside the receipt, and the next repeat finishes the cleanup; the other order would
    leave a file that no record names. Only the plain file this intent wrote is removed
    (`_remove_message` proves it by its place and its digest); a failure to remove never changes
    the answer that the receipt gives."""
    if op.signing:
        _remove_message(root, op)


def _remove_message(root: Path, op: Op) -> None:
    """Remove the message file only when it is the plain file this intent wrote."""
    path = message_file(root, op)
    try:
        if os.path.lexists(path) and sha256(_read(root, path, MESSAGE_LIMIT)) == op.message_sha256:
            path.unlink()
    except (OSError, SnapshotRefused):
        return                                  # a file that is not the stored message is not ours


def recognised(root: Path, git, op: Op, message: bytes, oid: str) -> bool:
    """Read the commit at `oid` once and judge it by the stored terms.

    The commit is read without replacement refs: the bytes judged are the bytes of the object
    the branch names, which is the object the receipt will record, never those of another commit
    that a `refs/replace/<oid>` ref says should be read in its place.

    Raises:
        GitReadFailed: `git_timed_out`, Git did not answer in time.
    """
    answer = git(["--no-optional-locks", "-C", str(root), REAL_OBJECTS, "cat-file", "commit", oid],
                 True, output_limit=COMMIT_LIMIT)
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if answer.exit_code != 0 or answer.truncated:
        return False                            # no commit, or more than the intended one holds
    return recognises(answer.output, op, message)


def recognises(raw: bytes, op: Op, message: bytes) -> bool:
    """Whether `raw`, a commit object, is the owner's signed root commit for the stored terms.

    The tree is the stored tree, there is no parent, the one author is the author shown, the body
    is the stored message to the byte, and a signature header of the repository's object format is
    present and begins with an armour line. The committer is whoever ran the command and is not
    compared. Presence is all that is judged of the signature: not its validity, not its key.
    """
    head, divider, body = raw.partition(b"\n\n")
    if not divider or body != message:
        return False
    try:
        rows = _headers(head.decode("utf-8"))
    except UnicodeDecodeError:
        return False

    def named(key: str) -> list[str]:
        return [value for name, value in rows if name == key]

    return (named("tree") == [op.expected_tree] and not named("parent")
            and _is_author(named("author"), op.author)
            and _is_armoured(named(_HEADER[op.object_format])))


def _headers(block: str) -> list[tuple[str, str]]:
    """The header lines of a commit; a line that starts with a space continues the one before."""
    rows: list[list[str]] = []
    for line in block.split("\n"):
        if line.startswith(" ") and rows:
            rows[-1][1] += "\n" + line[1:]
        else:
            key, _, value = line.partition(" ")
            rows.append([key, value])
    return [(key, value) for key, value in rows]


def _is_author(values: list[str], author: dict) -> bool:
    found = _AUTHOR.fullmatch(values[0]) if len(values) == 1 else None
    return found is not None and {"name": found[1], "email": found[2]} == author


def _is_armoured(values: list[str]) -> bool:
    return len(values) == 1 and values[0].split("\n", 1)[0] in _ARMOUR
