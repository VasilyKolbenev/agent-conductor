"""The closed `first_commit_pending` description of `GET /command/project/git` (spec 9.8, review
ruling OD-9): what a page that was closed in the middle of the first commit shows when it opens
again.

It is a READ and never a permission. It reads the op record of the first commit and the receipt
(`git_setup_first_records`, both under `<data_root>/git/setup/`) and shapes what they store. It
starts no process, writes no file and repeats nothing; a reload, a GET and a server start only
show the unfinished operation. A record that cannot be read or proven (torn, foreign, stale, or
beyond what the closed reader accepts) is described as `damaged` and the answer still goes out;
nothing is deleted or mended here.

The answer is `None`, or one of three closed shapes:

    {"state": "unfinished", "terms": TERMS}
    {"state": "awaiting_signature", "terms": TERMS,
     "signing": {"tree": ..., "target_ref": ..., "message_path": ...}}
    {"state": "damaged"}

`unfinished` covers the stages `prepared`, `locked` and `ref_moved`: the stage is how far the
product got, never what is true, so it is not shown. `None` stands when no op record stands and
when the receipt stands (the receipt is authoritative; the next confirmation only cleans up).

The description is the CONTINUE contract: the person repeats the confirmation
`{step: "first_commit", mode, paths_digest, actor}` with `mode` and `paths_digest` taken from
`terms` and `actor` the person acting now. The server judges that repeat again, from the stored
terms: another actor or other terms do not inherit the old confirmation.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from conductor.ownership import data_root
from conductor.ownership_errors import OwnerRefused
from . import git_setup_first_records as records
from .git_setup_first_records import AWAITING_SIGNATURE, Op

UNFINISHED = "unfinished"
DAMAGED = "damaged"
#: The 32 hex digits of the message digest that name the owner's message file.
_FILE_DIGITS = 32


def describe(root: Path) -> dict[str, Any] | None:
    """The stored first commit of the project at `root`, in the closed shape, or None.

    Never raises for a record it cannot prove: that is `{"state": "damaged"}`. SetupRefused and
    SnapshotRefused are ValueErrors; a layout of ownership that refuses is a record that cannot
    be located, so it is damage too.
    """
    try:
        op = records.read_op(root)
        if op is None or records.read_receipt(root) is not None:
            return None
        return _shape(root, op)
    except (OwnerRefused, OSError, ValueError):
        return {"state": DAMAGED}


def message_path_of(root: Path, op: Op) -> str:
    """Where the owner's commit message waits, relative to the project and in forward slashes:
    `conductor[.v3]/git/msg-first-<32 hex>.txt`, named by the first 32 hex of its digest."""
    digits = op.message_sha256.removeprefix("sha256:")[:_FILE_DIGITS]
    return f"{data_root(root).name}/git/msg-first-{digits}.txt"


def _terms(op: Op) -> dict[str, Any]:
    """The conditions the confirmation was made under, as stored; copies, never the record."""
    return {"mode": op.mode, "paths_digest": op.paths_digest, "digest_version": op.digest_version,
            "requested_by": op.requested_by, "file_count": op.file_count,
            "target_ref": op.target_ref,
            "author": {"name": op.author["name"], "email": op.author["email"]}}


def _shape(root: Path, op: Op) -> dict[str, Any]:
    if op.stage != AWAITING_SIGNATURE:
        return {"state": UNFINISHED, "terms": _terms(op)}
    if not op.signing:              # a wait for a signature that was never asked for is no wait
        return {"state": DAMAGED}
    return {"state": AWAITING_SIGNATURE, "terms": _terms(op),
            "signing": {"tree": op.expected_tree, "target_ref": op.target_ref,
                        "message_path": message_path_of(root, op)}}
