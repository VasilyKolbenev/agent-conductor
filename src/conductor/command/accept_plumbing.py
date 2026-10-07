"""Local Git plumbing against an owned temporary index, never the owner's checkout."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .accept_manifest import SnapshotRefused, sha256
from .accept_snapshot import _folder, _put
from .git_index import temporary_index
from .project_git import GitReadFailed
from .project_git_state import _checked
from conductor.ownership import data_root

_OID = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_AUTHOR = re.compile(r"(.+) <([^<>\r\n]+)> -?\d+ [+-]\d{4}\Z")


class SigningRequired(Exception):
    def __init__(self, tree, base_commit, branch, message_path):
        self.detail = dict(tree=tree, base_commit=base_commit, branch=branch, message_path=message_path)
        super().__init__("signing_required")


def acceptance_id(run_id, digest):
    return "acc-" + hashlib.sha256((run_id + digest).encode("ascii")).hexdigest()[:32]


def call(root, git, *args, **kwargs):
    return _checked(git(["-C", str(root), *args], True, **kwargs))


def oid(raw):
    value = raw.strip()
    if _OID.fullmatch(value) is None:
        raise GitReadFailed("git_failed")
    return value.decode("ascii")


def ref_oid(root, git, branch):
    ref = "refs/heads/" + branch
    answer = git(["-C", str(root), "show-ref", "--verify", "--quiet", ref], True)
    if answer.exit_code == 1 and not answer.output and not answer.truncated and not answer.timed_out:
        # Git's quiet missing-ref result must not hide a broken loose ref. Packed-ref
        # parse/read failures are non-1 failures and never reach this absence branch.
        raw = call(root, git, "rev-parse", "--git-path", ref).decode("utf-8").strip()
        if not raw:
            raise GitReadFailed("git_failed")
        path = Path(raw)
        try:
            os.lstat(path if path.is_absolute() else Path(root) / path)
        except FileNotFoundError:
            return None
        raise GitReadFailed("git_failed")
    _checked(answer)
    return oid(call(root, git, "show-ref", "--verify", "--hash", ref))


def materialize(root, git, view, contents):
    identity = acceptance_id(view["run_id"], view["accept_digest"])
    fmt = "sha1" if len(view["base"]["commit"]) == 40 else "sha256"
    _objects(root, git, view, contents)
    with temporary_index(root, identity, fmt) as index:
        call(root, git, "read-tree", view["base"]["commit"], index_file=index)
        pending, size = [], 0
        for row in view["files"]:
            mode, object_id = (("0", "0" * len(row["git_oid"])) if row["state"] == "deleted" else
                               (row["mode"], row["git_oid"]))
            line = f"{mode} {object_id}\t{row['path']}\n".encode("utf-8")
            if size + len(line) > 128 * 1024:
                call(root, git, "update-index", "--index-info", stdin=b"".join(pending), index_file=index)
                pending, size = [], 0
            pending.append(line)
            size += len(line)
        if pending:
            call(root, git, "update-index", "--index-info", stdin=b"".join(pending), index_file=index)
        tree = oid(call(root, git, "write-tree", index_file=index))
    existing = ref_oid(root, git, view["branch"])
    if existing is not None:
        hold_commit(root, git, existing, view, tree)
        return identity, tree, existing
    signing = _checked(git(["-C", str(root), "config", "--get", "--type=bool", "commit.gpgSign"], True),
                       absent=True).strip()
    if signing == b"true":
        path = data_root(root) / "git" / f"msg-{identity}.txt"
        _put(root, path, view["message"].encode("utf-8"))
        raise SigningRequired(tree, view["base"]["commit"], view["branch"], path.relative_to(root).as_posix())
    if signing not in (b"", b"false"):
        raise GitReadFailed("git_failed")
    commit = oid(call(root, git, "commit-tree", "--no-gpg-sign", tree, "-p", view["base"]["commit"], "-F", "-",
                      stdin=view["message"].encode("utf-8")))
    hold_commit(root, git, commit, view, tree)
    answer = git(["-C", str(root), "update-ref", "refs/heads/" + view["branch"], commit, "0" * len(commit)], True)
    if answer.exit_code != 0 or answer.timed_out or answer.truncated:
        current = ref_oid(root, git, view["branch"])
        if current != commit:
            raise SnapshotRefused("branch_exists" if current is not None else "git_failed")
    return identity, tree, commit


def _objects(root, git, view, contents):
    rows = [row for row in view["files"] if row["state"] != "deleted"]
    paths, expected, size = [], [], 0
    for row in rows:
        data = contents[row["path"]]
        if len(data) != row["length"] or sha256(data) != row["sha256"]:
            raise SnapshotRefused("snapshot_damaged")
        path = _folder(root, view["run_id"]) / "blobs" / row["sha256"].removeprefix("sha256:")
        _put(root, path, data)  # saved file bytes or immutable journal document bytes
        line = (json.dumps(path.as_posix(), ensure_ascii=False) + "\n").encode("utf-8")
        if size + len(line) > 128 * 1024:
            _write_objects(root, git, paths, expected)
            paths, expected, size = [], [], 0
        paths.append(line)
        expected.append(row["git_oid"])
        size += len(line)
    if paths:
        _write_objects(root, git, paths, expected)


def _write_objects(root, git, paths, expected):
    result = call(root, git, "hash-object", "-w", "--no-filters", "--stdin-paths", stdin=b"".join(paths))
    if result.decode("ascii").splitlines() != expected:
        raise SnapshotRefused("blob_mismatch")


def hold_commit(root, git, commit, view, tree):
    raw = call(root, git, "cat-file", "commit", commit)
    header, separator, message = raw.partition(b"\n\n")
    if not separator:
        raise SnapshotRefused("branch_exists")
    rows = header.decode("utf-8").splitlines()
    trees = [line.removeprefix("tree ") for line in rows if line.startswith("tree ")]
    parents = [line.removeprefix("parent ") for line in rows if line.startswith("parent ")]
    authors = [line.removeprefix("author ") for line in rows if line.startswith("author ")]
    author = _AUTHOR.fullmatch(authors[0]) if len(authors) == 1 else None
    if (trees != [tree] or parents != [view["base"]["commit"]] or author is None
            or {"name": author[1], "email": author[2]} != view["author"]
            or message != view["message"].encode("utf-8")):
        raise SnapshotRefused("branch_exists")
