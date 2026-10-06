"""The durable records of the first commit (spec 9.8, review ruling OD-4): the op, its install
bytes and the receipt, all under `<data_root>/git/setup/`.

The op record only says how far the product got; what is true is read from the repository on
every retry. Its order of effects is fixed here: the install bytes are published first, then the
op record (read back and checked against the bytes), and only after both may a caller lay a copy
in `.git`. A record never names bytes that are missing. Retirement runs the other way round: the
op record goes first and its install bytes after, so a crash between the two leaves an orphan file
that nothing names, never a live op without the bytes it is restored from.

The op record is the one file of this lane replaced in place (a stage advance of the product's own
file in its own namespace, never a name inside `.git`); the install bytes and the receipt are
published once, without replacing.

What the order proves is a claim about a process crash. Only the file contents are fsynced; the
directory fsync is best-effort (it returns silently where a directory cannot be opened, as on
Windows), so after a power cut the order in which names appear or vanish is not guaranteed on
every system. The retirement order is chosen so that the worst state it can leave is a refusal,
never a silent wrong action.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from conductor.ownership import data_root
from .accept_manifest import SnapshotRefused, sha256
from .accept_records import _object, _text
from .accept_snapshot import _hold, _put, _read
from .authorization_terms import human_identity
from .contract_values import _digest, _timestamp
from .git_setup_first_resume import LOCKED, PREPARED, REF_MOVED, STAGES
from .git_setup_records import SetupRefused
from .git_setup_snapshot import MAX_FILES
from .run_files import _fsync_dir, _replace_bytes

OP_NAME = "first_commit.op.json"
RECEIPT_NAME = "first_commit.json"
INSTALL = "first_commit.index-"
OP_LIMIT = 16 * 1024
RECEIPT_LIMIT = 16 * 1024
INDEX_LIMIT = 32 * 1024 * 1024        # 5000 paths of 4096 characters stay under it
AWAITING_SIGNATURE = "awaiting_signature"
OP_STAGES = (AWAITING_SIGNATURE, *STAGES)
#: The version of the digest scope the op was confirmed under. The preview carries its own
#: constant (`git_setup_modes.DIGEST_VERSION`); a test pins the two equal.
DIGEST_VERSION = 2

_MODES = ("snapshot", "empty")
_OID = {"sha1": re.compile(r"[0-9a-f]{40}"), "sha256": re.compile(r"[0-9a-f]{64}")}
_NONCE = re.compile(r"[0-9a-f]{16}")
_INSTALL_NAME = re.compile(re.escape(INSTALL) + r"[0-9a-f]{16}")
_HEADS = "refs/heads/"
_OP_KEYS = frozenset({
    "schema_version", "stage", "nonce", "mode", "paths_digest", "digest_version", "target_ref",
    "object_format", "expected_tree", "commit", "install_sha256", "message_sha256", "file_count",
    "requested_by", "author", "signing", "started_at"})
_RECEIPT_KEYS = frozenset({
    "schema_version", "step", "mode", "paths_digest", "digest_version", "target_ref", "commit",
    "tree", "object_format", "file_count", "signature", "requested_by", "recorded_at"})


@dataclass(frozen=True)
class Op:
    """One first commit in progress; `stage` says how far the product got, never what is true."""

    stage: str
    nonce: str
    mode: str
    paths_digest: str | None
    digest_version: int
    target_ref: str
    object_format: str
    expected_tree: str
    commit: str | None            # None exactly at awaiting_signature
    install_sha256: str
    message_sha256: str
    file_count: int
    requested_by: str
    author: dict                  # {"name", "email"} as the preview showed them, frozen
    signing: bool                 # the signing flag as the preview showed it, frozen
    started_at: str


def _setup(root: Path) -> Path:
    return data_root(root) / "git" / "setup"


def _held(root: Path, path: Path) -> None:
    try:
        _hold(root, path)
    except SnapshotRefused:
        raise SetupRefused("setup_damaged") from None


def _unlink_plain(root: Path, path: Path) -> None:
    """Remove one plain regular file of the product; a missing file is fine, anything else is
    refused as damage and left where it is."""
    _held(root, path)
    path.unlink(missing_ok=True)


def _encode(row: dict) -> bytes:
    raw = json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return (raw + "\n").encode("ascii")


def _oid(value: object, object_format: str) -> str:
    if type(value) is not str or _OID[object_format].fullmatch(value) is None:
        raise ValueError("object id")
    return value


def _utf8(value: object, limit: int = 1024) -> str:
    """`_text`, and text that encodes as strict UTF-8. JSON lets a lone surrogate through, and
    the answer that shows a stored text is written as UTF-8: one such character would end the
    GET without an answer, so a record that holds one is damage."""
    text = _text(value, limit)
    text.encode("utf-8")                    # UnicodeEncodeError is a ValueError: damage
    return text


def _terms(row: dict, tree: str) -> None:
    """The fields an op and its receipt both carry, judged once for both."""
    if type(row["object_format"]) is not str or row["object_format"] not in _OID:
        raise ValueError("object format")
    _oid(tree, row["object_format"])
    if row["mode"] not in _MODES or (row["paths_digest"] is None) != (row["mode"] == "empty"):
        raise ValueError("mode and digest")
    if row["paths_digest"] is not None:
        _digest("paths_digest", row["paths_digest"])
    if type(row["digest_version"]) is not int or row["digest_version"] != DIGEST_VERSION:
        raise ValueError("digest version")
    count = row["file_count"]
    if type(count) is not int or not 0 <= count <= MAX_FILES:
        raise ValueError("file count")
    ref = _utf8(row["target_ref"], 240)
    if not ref.startswith(_HEADS) or len(ref) == len(_HEADS):
        raise ValueError("target ref")
    human_identity("requested_by", row["requested_by"])
    _text(row["requested_by"])


def _check(op: Op) -> None:
    """Raise ValueError unless every field is what the contract allows."""
    row = asdict(op)
    if type(op.stage) is not str or op.stage not in OP_STAGES:
        raise ValueError("stage")
    if type(op.nonce) is not str or _NONCE.fullmatch(op.nonce) is None:
        raise ValueError("nonce")
    _terms(row, op.expected_tree)
    if (op.commit is None) != (op.stage == AWAITING_SIGNATURE):
        raise ValueError("commit and stage")
    if op.commit is not None:
        _oid(op.commit, op.object_format)
    _digest("install_sha256", op.install_sha256)
    _digest("message_sha256", op.message_sha256)
    if type(op.signing) is not bool:
        raise ValueError("signing")
    author = op.author
    if type(author) is not dict or set(author) != {"name", "email"}:
        raise ValueError("author")
    for field in ("name", "email"):
        _utf8(author[field])
    _timestamp("started_at", op.started_at)


def _op(row: object) -> Op:
    if type(row) is not dict or set(row) != _OP_KEYS:
        raise ValueError("op shape")
    if type(row["schema_version"]) is not int or row["schema_version"] != 2:
        raise ValueError("schema version")
    op = Op(**{key: value for key, value in row.items() if key != "schema_version"})
    _check(op)
    return op


def _encode_op(op: Op) -> bytes:
    return _encode(asdict(op) | {"schema_version": 2})


def read_op(root: Path) -> Op | None:
    """The record, VERIFIED: its install bytes must exist and hash to `install_sha256`.

    Returns None when no op stands; any damage raises SetupRefused('setup_damaged').
    """
    path = _setup(root) / OP_NAME
    try:
        _hold(root, path)
        if not os.path.lexists(path):
            return None
        op = _op(json.loads(_read(root, path, OP_LIMIT), object_pairs_hook=_object))
        read_install(root, op)
        return op
    except (OSError, ValueError, TypeError, RecursionError):   # the decoder's depth limit
        raise SetupRefused("setup_damaged") from None


def read_install(root: Path, op: Op) -> bytes:
    """The bytes this op installs, VERIFIED against the digest the record carries."""
    try:
        data = _read(root, _setup(root) / f"{INSTALL}{op.nonce}", INDEX_LIMIT)
    except (OSError, ValueError):
        raise SetupRefused("setup_damaged") from None
    if sha256(data) != op.install_sha256:
        raise SetupRefused("setup_damaged")
    return data


def sweep_orphans(root: Path) -> None:
    """Remove install files that no op names, and only while no op record stands at all, so the
    bytes of a live operation can never be touched. Other names in the folder are left alone."""
    setup = _setup(root)
    _held(root, setup / OP_NAME)
    if os.path.lexists(setup / OP_NAME) or not os.path.isdir(setup):
        return
    for entry in sorted(os.listdir(setup)):
        if _INSTALL_NAME.fullmatch(entry):
            _unlink_plain(root, setup / entry)


def start(root: Path, op: Op, data: bytes) -> Op:
    """Publish the install bytes, then the op record, then read the record back (OD-4).

    Nothing is written for an invalid op or for bytes that do not hash to `op.install_sha256`; a
    standing op is never overwritten (an equal one is returned as it is); orphan install bytes of
    an earlier attempt are swept first. The bytes are read back before the record is published,
    so a record never names bytes that are missing or other than meant.
    """
    try:
        _check(op)
    except (ValueError, TypeError):
        raise SetupRefused("setup_damaged") from None
    if (op.stage not in (PREPARED, AWAITING_SIGNATURE) or len(data) > INDEX_LIMIT
            or sha256(data) != op.install_sha256):
        raise SetupRefused("setup_damaged")
    standing = read_op(root)
    if standing is not None:
        if standing == op:
            return op
        raise SetupRefused("setup_damaged")
    sweep_orphans(root)
    try:
        _put(root, _setup(root) / f"{INSTALL}{op.nonce}", data)
        read_install(root, op)
        _put(root, _setup(root) / OP_NAME, _encode_op(op))
    except SnapshotRefused:
        raise SetupRefused("setup_damaged") from None
    if read_op(root) != op:
        raise SetupRefused("setup_damaged")
    return op


#: The only moves of the record. `prepared -> locked` is MARK_LOCKED; `-> ref_moved` is
#: MARK_REF_MOVED, which also answers a ref found at the commit while the record still says
#: `prepared`; the signed road's move takes the commit the owner made.
_FORWARD = frozenset({(PREPARED, LOCKED), (LOCKED, REF_MOVED), (PREPARED, REF_MOVED),
                      (AWAITING_SIGNATURE, REF_MOVED)})


def advance(root: Path, op: Op, stage: str, *, commit: str | None = None) -> Op:
    """Replace the stored record with a later stage: never backwards, never in place.

    `op` must be the record as it is stored; a stale copy cannot move it. `commit` is given
    exactly when the move leaves `awaiting_signature`, and only then.
    """
    leaving = op.stage == AWAITING_SIGNATURE
    if (op.stage, stage) not in _FORWARD or leaving != (commit is not None):
        raise SetupRefused("setup_damaged")
    moved = replace(op, stage=stage, commit=commit) if leaving else replace(op, stage=stage)
    try:
        _check(moved)
    except (ValueError, TypeError):
        raise SetupRefused("setup_damaged") from None
    if read_op(root) != op:
        raise SetupRefused("setup_damaged")
    path = _setup(root) / OP_NAME
    _held(root, path)
    _replace_bytes(path, _encode_op(moved))
    _fsync_dir(path.parent)
    return moved


def retire(root: Path, op: Op) -> None:
    """Retire a finished or cancelled op: the record FIRST, its install bytes after (OD-4).

    A crash between the two leaves an orphan file that nothing names; the reverse order would
    leave a live op without the bytes it is restored from. Only a caller that already holds the
    receipt (finish) or has removed every own artifact of `.git` (supersede) may call it. Nothing
    is removed unless `op` is the stored, verified record.
    """
    if read_op(root) != op:
        raise SetupRefused("setup_damaged")
    setup = _setup(root)
    _unlink_plain(root, setup / OP_NAME)
    _fsync_dir(setup)
    _unlink_plain(root, setup / f"{INSTALL}{op.nonce}")


def new_op(mode: str, digest: str | None, actor: str, shown: dict, made: Any, now: str,
           message: bytes) -> Op:
    """The op for a confirmation: the shown terms are frozen into it (OD-4).

    `made` is the preparation (it needs `nonce`, `tree`, `commit` and `install`); `commit` is
    None exactly when signing is required, and the op then waits for the owner's signature.
    """
    return Op(
        stage=AWAITING_SIGNATURE if shown["signing"] else PREPARED, nonce=made.nonce, mode=mode,
        paths_digest=digest, digest_version=shown["digest_version"],
        target_ref=shown["target_ref"], object_format=shown["object_format"],
        expected_tree=made.tree, commit=made.commit, install_sha256=sha256(made.install),
        message_sha256=sha256(message), file_count=len(shown["files"]), requested_by=actor,
        author=dict(shown["author"]), signing=shown["signing"], started_at=now)


def receipt_of(op: Op, now: str) -> dict:
    """The receipt of a finished op; it needs the commit, so not an op that still waits."""
    if op.commit is None:
        raise SetupRefused("setup_damaged")
    return dict(
        schema_version=1, step="first_commit", mode=op.mode, paths_digest=op.paths_digest,
        digest_version=op.digest_version, target_ref=op.target_ref, commit=op.commit,
        tree=op.expected_tree, object_format=op.object_format, file_count=op.file_count,
        signature="present" if op.signing else "not_required", requested_by=op.requested_by,
        recorded_at=now)


def _receipt(row: object) -> dict:
    if type(row) is not dict or set(row) != _RECEIPT_KEYS:
        raise ValueError("receipt shape")
    if type(row["schema_version"]) is not int or row["schema_version"] != 1:
        raise ValueError("schema version")
    if row["step"] != "first_commit" or row["signature"] not in ("not_required", "present"):
        raise ValueError("receipt words")
    _terms(row, row["tree"])
    _oid(row["commit"], row["object_format"])
    _timestamp("recorded_at", row["recorded_at"])
    return row


def write_receipt(root: Path, row: dict) -> dict:
    """Publish the receipt once; an equal repeat is fine, another row is damage."""
    try:
        _receipt(row)
        _put(root, _setup(root) / RECEIPT_NAME, _encode(row))
    except (ValueError, TypeError):
        raise SetupRefused("setup_damaged") from None
    return row


def read_receipt(root: Path) -> dict | None:
    """The receipt in its closed shape, or None when the first commit was not completed."""
    path = _setup(root) / RECEIPT_NAME
    try:
        _hold(root, path)
        if not os.path.lexists(path):
            return None
        return _receipt(json.loads(_read(root, path, RECEIPT_LIMIT), object_pairs_hook=_object))
    except (OSError, ValueError, TypeError, RecursionError):   # the decoder's depth limit
        raise SetupRefused("setup_damaged") from None
