"""Read the three immutable acceptance records without inventing absent or damaged facts.

Every returned field belongs to the closed wire schema;
remote credentials and unrelated run/task identities cannot become a GET response.
"""
from __future__ import annotations

import json
import os
import re

from .accept_snapshot import _folder, _hold, _read
from .authorization_terms import human_identity
from .contract_values import _digest, _id, _timestamp
from .project_git_state import _remote_target
from .run_store import CorruptRun, _root_gate

_FIELDS = {
    "commit": {"schema_version", "acceptance_id", "run_id", "task_id", "kind", "base_commit",
               "commit", "tree", "branch", "accept_digest", "accept_manifest_digest", "file_count",
               "requested_by", "recorded_at"},
    "push": {"schema_version", "acceptance_id", "remote", "push_url", "remote_repo", "ref", "commit",
             "push_digest", "remote_oid", "requested_by", "pushed_at"},
    "pr": {"schema_version", "acceptance_id", "repo", "number", "url", "draft", "base", "head_ref",
           "head_oid", "requested_by", "created_at"},
}
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _text(value, limit=1024):
    if (type(value) is not str or not value.strip() or len(value) > limit
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("text")
    return value


def _oid(value):
    if type(value) is not str or _OID.fullmatch(value) is None:
        raise ValueError("object id")


def _validate(kind, value):
    if (type(value) is not dict or set(value) != _FIELDS[kind]
            or type(value["schema_version"]) is not int or value["schema_version"] != 1):
        raise ValueError("shape")
    if re.fullmatch(r"acc-[0-9a-f]{32}", _text(value["acceptance_id"])) is None:
        raise ValueError("acceptance id")
    human_identity("requested_by", value["requested_by"])
    _timestamp("recorded_at", value[{"commit": "recorded_at", "push": "pushed_at", "pr": "created_at"}[kind]])
    if kind == "commit":
        for name in ("run_id", "task_id"):
            _id(name, value[name])
        if value["kind"] not in {"files", "documents"}:
            raise ValueError("kind")
        for name in ("base_commit", "commit", "tree"):
            _oid(value[name])
        if len({len(value[name]) for name in ("base_commit", "commit", "tree")}) != 1:
            raise ValueError("format")
        _digest("accept_digest", value["accept_digest"])
        if value["kind"] == "files":
            _digest("accept_manifest_digest", value["accept_manifest_digest"])
        elif value["accept_manifest_digest"] is not None:
            raise ValueError("document snapshot")
        if not _text(value["branch"]).startswith("conduct/"):
            raise ValueError("branch")
        if type(value["file_count"]) is not int or not 0 <= value["file_count"] <= 2000:
            raise ValueError("file count")
    elif kind == "push":
        _id("remote", value["remote"])
        _digest("push_digest", value["push_digest"])
        repo, credentials = _remote_target(_text(value["push_url"]))
        if credentials or repo is None or repo != value["remote_repo"]:
            raise ValueError("remote")
        if not _text(value["ref"]).startswith("refs/heads/conduct/"):
            raise ValueError("ref")
        _oid(value["commit"])
        _oid(value["remote_oid"])
    else:
        if type(value["number"]) is not int or value["number"] <= 0 or type(value["draft"]) is not bool:
            raise ValueError("pull request")
        if value["url"] != f"https://github.com/{_text(value['repo'])}/pull/{value['number']}":
            raise ValueError("url")
        _text(value["base"])
        if not _text(value["head_ref"]).startswith("conduct/"):
            raise ValueError("head ref")
        _oid(value["head_oid"])
    return value


def read_records(root, run_id, *, task_id=None, kind=None):
    folder = _folder(root, run_id)
    gate = _root_gate(root)
    result = {}
    try:
        with gate.lock:
            for name in _FIELDS:
                path = folder / f"{name}.json"
                _hold(root, path)
                result[name] = (None if not os.path.lexists(path) else _validate(name,
                    json.loads(_read(root, path, 256 * 1024), object_pairs_hook=_object)))
            commit, push, pr = (result[name] for name in _FIELDS)
            if commit is not None and (commit["run_id"] != run_id or commit["task_id"] != task_id
                                       or commit["kind"] != kind):
                raise ValueError("foreign commit")
            if push is not None and (commit is None or push["acceptance_id"] != commit["acceptance_id"]
                    or push["commit"] != commit["commit"] or push["remote_oid"] != commit["commit"]
                    or push["ref"] != "refs/heads/" + commit["branch"]):
                raise ValueError("foreign push")
            if pr is not None and (push is None or pr["acceptance_id"] != push["acceptance_id"]
                    or pr["repo"] != push["remote_repo"] or pr["head_oid"] != push["commit"]
                    or "refs/heads/" + pr["head_ref"] != push["ref"]):
                raise ValueError("foreign pull request")
    except (OSError, ValueError, TypeError) as error:
        raise CorruptRun("stored acceptance records are damaged or disagree") from error
    return {"commit": result["commit"], "push": result["push"], "pull_request": result["pr"]}
