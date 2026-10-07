"""Closed, immutable facts about the exact full-byte dispatch handoff."""
from __future__ import annotations

from collections.abc import Mapping

from .contract_values import (ContractError, _content_digest, _digest, _freeze_json,
                              _id, _ids, _thaw_json)

_FIELDS = frozenset({"action_id", "attempt_id", "input_artifact_ids", "files"})
_FILE_FIELDS = frozenset({"path", "state", "length", "sha256"})


class ResultManifestError(ContractError):
    """The result facts cannot be a canonical full-byte manifest."""


def _path(value):
    if type(value) is not str or not value or "\\" in value or ":" in value:
        raise ResultManifestError("result file path must be canonical relative POSIX")
    if any(part in {"", ".", ".."} for part in value.split("/")):
        raise ResultManifestError("result file path contains an empty, dot or parent component")
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ResultManifestError("result file path contains a control or surrogate")
    return value


def _file(value):
    if not isinstance(value, Mapping) or set(value) != _FILE_FIELDS:
        raise ResultManifestError("result file has unknown or missing fields")
    path = _path(value["path"])
    state, length, sha256 = value["state"], value["length"], value["sha256"]
    if type(state) is not str or state not in {"present", "deleted"}:
        raise ResultManifestError("result file state must be present or deleted")
    if type(length) is not int or length < 0:
        raise ResultManifestError("result file length must be an exact nonnegative integer")
    if state == "deleted":
        if length != 0 or sha256 is not None:
            raise ResultManifestError("deleted result file must have zero length and null digest")
    else:
        _digest("result file sha256", sha256)
    return {"path": path, "state": state, "length": length, "sha256": sha256}


def rebuild_manifest(value):
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ResultManifestError("result manifest has unknown or missing fields")
    files = value["files"]
    if type(files) not in (list, tuple):
        raise ResultManifestError("result manifest files must be an ordered sequence")
    rebuilt = [_file(row) for row in files]
    paths = [row["path"] for row in rebuilt]
    if paths != sorted(set(paths)):
        raise ResultManifestError("result file paths must be unique and already sorted")
    return _freeze_json({"action_id": _id("action_id", value["action_id"]),
        "attempt_id": _id("attempt_id", value["attempt_id"]),
        "input_artifact_ids": list(_ids("input_artifact_ids", value["input_artifact_ids"])),
        "files": rebuilt})


def manifest_digest(value):
    return _content_digest(_thaw_json(rebuild_manifest(value)))
