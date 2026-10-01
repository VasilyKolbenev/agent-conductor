"""Immutable receipts for explicitly confirmed init/exclude steps."""
from __future__ import annotations

import json
import os

from conductor.ownership import data_root
from .accept_records import _object
from .accept_snapshot import _hold, _put, _read
from .authorization_terms import human_identity
from .contract_values import _timestamp


class SetupRefused(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def receipt(root, step):
    path = data_root(root) / "git" / "setup" / f"{step}.json"
    try:
        _hold(root, path)
        if not os.path.lexists(path):
            return None
        row = json.loads(_read(root, path, 256 * 1024), object_pairs_hook=_object)
        if (type(row) is not dict or set(row) != {"schema_version", "step", "requested_by",
                "recorded_at", "object_format", "exclude", "warnings"}
                or type(row["schema_version"]) is not int or row["schema_version"] != 1
                or row["step"] != step or row["object_format"] not in {"sha1", "sha256"}
                or row["exclude"] not in {"written", "present"}
                or row["warnings"] not in ([], ["nested_repository"])):
            raise ValueError("setup receipt shape")
        human_identity("requested_by", row["requested_by"])
        _timestamp("recorded_at", row["recorded_at"])
        return row
    except (OSError, ValueError, TypeError):
        raise SetupRefused("setup_damaged") from None


def publish(root, step, actor, now, object_format, exclude, warnings):
    row = dict(schema_version=1, step=step, requested_by=actor, recorded_at=now,
               object_format=object_format, exclude=exclude, warnings=warnings)
    raw = (json.dumps(row, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
    _put(root, data_root(root) / "git" / "setup" / f"{step}.json", raw)
    return row
