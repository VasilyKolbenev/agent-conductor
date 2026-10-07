"""Build result facts from a bounded file-road read, never model claims."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping

from ..contracts import ABSENT, ControlMode, rebuild_manifest, manifest_digest


class MaterialManifestError(ValueError):
    """The supplied file-road read cannot prove this full-byte handoff."""

    def __init__(self, reason="material_unavailable"):
        self.reason = reason
        super().__init__(reason)


def marked_policy(request):
    return (request.mode is ControlMode.POLICY
            and request.run_authorization_id is not ABSENT)


def _scan(values, sensitive):
    for value in values:
        payload = value.encode("utf-8") if isinstance(value, str) else value
        if any(secret and secret in payload for secret in sensitive):
            raise MaterialManifestError("frame_env_echo")


def _row(path, tree, contents, absent):
    if path in absent:
        if path in tree or path in contents:
            raise MaterialManifestError()
        return {"path": path, "state": "deleted", "length": 0, "sha256": None}
    content = contents.get(path)
    if type(content) is not bytes:
        raise MaterialManifestError()
    digest = hashlib.sha256(content).hexdigest()
    if tree.get(path) != digest:
        raise MaterialManifestError()
    return {"path": path, "state": "present", "length": len(content),
            "sha256": "sha256:" + digest}


def build_result_manifest(request, input_ids, changed, tree, contents, *,
                          subtree, absent, sensitive=()):
    """`absent` comes from actual leaf checks under the same workspace turn.

    A missing digest alone does not establish deletion: the old file may have
    become a directory or another unreported kind. Each present member needs
    complete bytes matching the current read's digest, within its existing cap.
    """
    if (not isinstance(tree, Mapping) or not isinstance(contents, Mapping)
            or type(changed) is not tuple or type(absent) is not tuple
            or any(type(path) is not str for path in changed + absent)
            or type(subtree) is not str or not subtree.endswith("/")):
        raise MaterialManifestError()
    if (not changed or len(set(changed)) != len(changed)
            or len(set(absent)) != len(absent)
            or any(not path.startswith(subtree) for path in changed)
            or not set(absent) <= set(changed)
            or set(contents) != set(changed) - set(absent)):
        raise MaterialManifestError()
    _scan((*changed, *input_ids, *contents.values()), sensitive)
    return rebuild_manifest({"action_id": request.action_id,
        "attempt_id": request.attempt_id, "input_artifact_ids": list(input_ids),
        "files": [_row(path, tree, contents, absent) for path in sorted(changed)]})


def check_result_manifest(value, request, input_ids, changed, tree, contents, **read):
    rebuilt = build_result_manifest(request, input_ids, changed, tree, contents, **read)
    if rebuild_manifest(value) != rebuilt:
        raise MaterialManifestError()
    return rebuilt
