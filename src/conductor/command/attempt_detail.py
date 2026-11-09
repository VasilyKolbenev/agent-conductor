"""Read the files and checker owned by a selected action. The live work folder is irrelevant."""
import re

from .accept_capture import _included
from .accept_manifest import SnapshotRefused
from .accept_snapshot import read_snapshot, read_snapshot_index
from .accept_terms import binary, patch
from .api_contracts import ApiRefusal
from .checked_changes import MAX_SHOWN, patch_verifier
from .contracts import ActionRequest, ActionResultReceipt
from .seed_record import WORK_ITEM_ID, CorruptSeed, read_seed
from .store_errors import CorruptRun
from .task_contracts import frozen_config_task

_FILE_BYTES = 32 * 1024
_FILE_LINES = 600
_DIFF_BYTES = 128 * 1024
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PRIVATE = frozenset({".ssh", ".aws", ".azure", ".gnupg", ".config", ".git-credentials",
                      ".codex", ".grok", ".claude", ".npmrc", ".netrc", ".pypirc",
                      "auth.json", ".credentials.json", "credentials", "credentials.json",
                      "id_rsa", "id_dsa", "id_ed25519", "id_ecdsa"})
_SECRET = re.compile(
    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:sk-(?:proj-|ant-)?|gh[pousr]_|github_pat_)"
    rb"[a-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|(?:\bBearer[ \t]+[A-Za-z0-9._~-]{12,})|"
    rb"""["']?\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)"""
    rb"""["']?\s*[:=]\s*["'][^"'\r\n]+["']""", re.IGNORECASE)


def _private_path(path):
    parts = path.casefold().split("/")
    return (any(p in _PRIVATE or p == ".env" or p.startswith(".env.") for p in parts)
            or parts[-1].endswith((".key", ".pem", ".p12", ".pfx")))


def _source_status(name, data):
    if _private_path(name):
        return "withheld"
    if len(data) > _FILE_BYTES:
        return "too_large"
    if binary(data) or any(n < 32 and n not in (9, 10, 13) for n in data):
        return "binary"
    if len(data.decode("utf-8").splitlines()) > _FILE_LINES:
        return "too_large"
    return "withheld" if _SECRET.search(data) else "available"


def displayable_source(path, data):
    """The same presentation bounds apply to a diff and a test assertion from that file."""
    return _source_status(path, data) == "available"


def _file(row, before, snapshot, allowance):
    shown = {"path": row.path, "state": row.state, "diff_status": "base_unavailable", "lines": []}
    if _private_path(row.path):
        return {**shown, "diff_status": "withheld"}, 0
    if row.length > _FILE_BYTES:
        return {**shown, "diff_status": "too_large"}, 0
    if before is None or (row.state != "added" and row.path not in before):
        return shown, 0
    old = before.get(row.path, b"")
    new = b"" if row.state == "deleted" else snapshot.blobs[row.sha256]
    for raw in (old, new):
        status = _source_status(row.path, raw)
        if status != "available":
            return {**shown, "diff_status": status}, 0
    if allowance <= 0:
        return {**shown, "diff_status": "too_large"}, 0
    delta = patch([row.as_dict()], {row.path: old}, {row.path: new})
    size = len(delta["text"].encode("utf-8"))
    if delta["truncated"] or size > allowance:
        return {**shown, "diff_status": "too_large"}, 0
    # The name already appears as a validated field. Preserve hunks and EOF markers.
    return {**shown, "diff_status": "available", "lines": delta["text"].splitlines()[2:]}, size


def _snapshot(root, request, seed, digest):
    fmt = seed.object_format
    if fmt is None:
        rows = read_snapshot_index(root, request.run_id, digest)
        fmt = "sha256" if rows and len(rows[0].git_oid) == 64 else "sha1"
    return read_snapshot(root, request.run_id, digest, object_format=fmt)


def _project_files(root, request, seed, snapshot, git):
    rows = snapshot.rows[:MAX_SHOWN]
    # Do not fetch a before-image for a path which the client cannot view.
    permitted = [r for r in rows if not _private_path(r.path) and r.length <= _FILE_BYTES]
    if seed.source == "empty":
        before = {} if all(r.state == "added" for r in snapshot.rows) else None
    else:
        from .attempt_base import read_attempt_base
        try:
            before = read_attempt_base(root, request.run_id, seed, permitted, git=git)
        except SnapshotRefused:
            before = None
    files, remaining = [], _DIFF_BYTES
    for row in rows:
        file, size = _file(row, before, snapshot, remaining)
        files.append(file)
        remaining -= size
    return files


def read_attempt(root, recovered, node_id, action_id, *, git=None):
    """Resolve the selected action under its run and node; never select its successor."""
    if recovered.warnings:
        raise CorruptRun("incomplete action history")
    values = [row.value for row in recovered.records]
    requests = [v for v in values if isinstance(v, ActionRequest)
                and v.run_id == recovered.envelope.run_id and v.action_id == action_id
                and v.node_id == node_id]
    if len(requests) != 1:
        raise ApiRefusal.fixed("route_not_found")
    request = requests[0]
    results = [v for v in values if isinstance(v, ActionResultReceipt)
               and (v.run_id, v.action_id, v.attempt_id, v.instance_id) == (
                   request.run_id, action_id, request.attempt_id, request.instance_id)]
    if len(results) > 1:
        raise CorruptRun("ambiguous action result")
    result = results[0] if results else None
    view = {"run_id": request.run_id, "node_id": node_id, "action_id": action_id,
            "attempt_id": request.attempt_id, "outcome": result.outcome if result else None,
            "verdict": None, "manifest_digest": None, "files_total": None, "files": [],
            "tests": {"status": "not_recorded", "summary": None, "cases": [], "source": None}}
    proof = patch_verifier(recovered, request, result)
    if proof is None:
        return view
    view["verdict"] = {"status": proof.verification, "instance_id": proof.verifier_instance_id,
                       "adapter_id": proof.verified_by}
    digest = proof.extra.get("accept_manifest_digest")
    tree = proof.extra.get("work_tree_digest")
    if (result.outcome != "succeeded" or proof.verification != "verified"
            or type(digest) is not str or not _HASH.fullmatch(digest)
            or type(tree) is not str or not _HASH.fullmatch(tree)):
        return view
    view["manifest_digest"] = digest
    task = frozen_config_task(recovered.config)
    try:
        seed = read_seed(root, task.task_id)
        if (seed is None or request.arguments.get("work_item_id") != WORK_ITEM_ID
                or (seed.task_id, seed.work_scope, seed.work_item_id) != (
                    task.task_id, task.work_scope, WORK_ITEM_ID)):
            return view
        snapshot = _snapshot(root, request, seed, digest)
        if any(not _included(row.path, seed) for row in snapshot.rows):
            raise SnapshotRefused("snapshot_damaged")
    except (SnapshotRefused, CorruptSeed):
        view["tests"]["status"] = "unavailable"
        return view
    view["files_total"] = len(snapshot.rows)
    view["files"] = _project_files(root, request, seed, snapshot, git)
    from .attempt_test_evidence import read_test_evidence
    view["tests"] = read_test_evidence(root, request, digest, seed, snapshot)
    return view
