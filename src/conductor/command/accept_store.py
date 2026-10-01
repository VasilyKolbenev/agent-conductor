"""Immutable human-confirmed intents and the final acceptance receipt, never run records."""
from __future__ import annotations

import json
import os
import re

from .accept_records import _object, _validate
from .accept_snapshot import _folder, _hold, _put, _read
from .accept_terms import asked
from .authorization_terms import human_identity
from .contract_values import ContractError, _digest, _id, _timestamp
from .run_store import CorruptRun

_FIELDS = {"schema_version", "run_id", "task_id", "accept_digest", "options", "requested_by", "requested_at"}
_NAME = re.compile(r"intent-([0-9a-f]{64})\.json\Z")


def intents(root, run_id, task_id):
    folder = _folder(root, run_id)
    _hold(root, folder / "commit.json")
    if not os.path.lexists(folder):
        return ()
    try:
        paths = [path for path in folder.iterdir() if path.name.startswith("intent-")]
        if len(paths) > 32:
            raise ValueError("too many acceptance intents")
        result = []
        for path in sorted(paths):
            match = _NAME.fullmatch(path.name)
            if match is None:
                raise ValueError("intent name")
            value = json.loads(_read(root, path, 1024 * 1024), object_pairs_hook=_object)
            if (type(value) is not dict or set(value) != _FIELDS
                    or type(value["schema_version"]) is not int or value["schema_version"] != 1):
                raise ValueError("intent shape")
            if value["run_id"] != run_id or value["task_id"] != task_id:
                raise ValueError("intent binding")
            _id("run_id", value["run_id"])
            _id("task_id", value["task_id"])
            _digest("accept_digest", value["accept_digest"])
            if match[1] != value["accept_digest"].removeprefix("sha256:"):
                raise ValueError("intent digest")
            asked(value["options"])
            human_identity("actor", value["requested_by"])
            _timestamp("requested_at", value["requested_at"])
            result.append(value)
        return tuple(result)
    except (OSError, ValueError, TypeError) as error:
        raise CorruptRun("acceptance intent is damaged or disagrees") from error


def write_intent(root, run_id, task_id, digest, options, actor, now):
    standing = intents(root, run_id, task_id)
    matching = next((row for row in standing if row["accept_digest"] == digest), None)
    if matching is not None:
        if matching["options"] != options or matching["requested_by"] != actor:
            raise CorruptRun("acceptance intent cannot change")
        return matching
    if len(standing) >= 32:
        raise ContractError("this run already has the bounded number of acceptance intents")
    value = {"schema_version": 1, "run_id": run_id, "task_id": task_id, "accept_digest": digest,
             "options": asked(options), "requested_by": human_identity("actor", actor),
             "requested_at": _timestamp("requested_at", now)}
    path = _folder(root, run_id) / f"intent-{digest.removeprefix('sha256:')}.json"
    _put(root, path, _bytes(value))
    return value


def write_commit(root, value):
    _validate("commit", value)
    path = _folder(root, value["run_id"]) / "commit.json"
    _put(root, path, _bytes(value))
    return value


def _bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
