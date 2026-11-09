"""Project-local utility registry and explicit text exchanges; no peer is launched here."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re

from ..ownership import OwnerRefused, data_root, write_guard
from .accept_snapshot import SnapshotRefused, _hold, _put, _read
from .api_contracts import ApiRefusal
from .path_admission import WindowsNameError, admit_name
from .run_store import _root_gate

_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,47}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TEXT_BYTES = 8192
_PACKET_BYTES = _TEXT_BYTES * 2 + 1024
_FIELDS = {
    "attach": {"utility_id", "mode", "label"},
    "send": {"utility_id", "exchange_id", "text"},
    "manual_reply": {"utility_id", "exchange_id", "text"},
    "claim": {"utility_id", "exchange_id", "claim_token"},
    "finish": {"utility_id", "exchange_id", "claim_token", "outcome"},
    "mark_unknown": {"utility_id", "exchange_id"},
}


def _valid_id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        return False
    try:
        admit_name(value, "utility id")
        return True
    except WindowsNameError:
        return False


def _text(value):
    if not isinstance(value, str) or not value.strip():
        return False
    if any(ord(char) < 32 and char not in "\r\n\t" for char in value):
        return False
    try:
        return len(value.encode("utf-8")) <= _TEXT_BYTES
    except UnicodeEncodeError:
        return False


def _label(value):
    return _text(value) and len(value) <= 80 and value.isprintable()


def _hex(value):
    return isinstance(value, str) and bool(_HEX.fullmatch(value))


def _validate(body):
    op = body.get("op")
    if not isinstance(op, str) or op not in _FIELDS:
        raise ApiRefusal.fixed("contract_invalid")
    fields = _FIELDS[op] | {"op"}
    if op == "finish" and body.get("outcome") == "answered":
        fields |= {"text"}
    if (set(body) != fields or not _valid_id(body["utility_id"])
            or ("exchange_id" in fields and not _valid_id(body["exchange_id"]))
            or ("text" in fields and not _text(body["text"]))
            or ("label" in fields and not _label(body["label"]))
            or ("mode" in fields and body["mode"] not in ("manual", "stdio-v1"))
            or ("claim_token" in fields and not _hex(body["claim_token"]))
            or ("outcome" in fields and body["outcome"] not in ("answered", "unknown"))):
        raise ApiRefusal.fixed("contract_invalid")


def _canonical(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _read_record(root, path, keys, identity):
    _hold(root, path)
    if not os.path.lexists(path):
        return None
    raw = _read(root, path, _PACKET_BYTES)
    try:
        record = json.loads(raw)
    except (ValueError, RecursionError):
        raise ApiRefusal.fixed("store_error") from None
    if (not isinstance(record, dict) or set(record) != set(identity) | set(keys)
            or any(record[key] != value for key, value in identity.items())
            or _canonical(record) != raw):
        raise ApiRefusal.fixed("store_error")
    return record


def _publish(root, path, previous, record):
    if previous is not None:
        if previous != record:
            raise ApiRefusal.fixed("record_conflict")
        return 200
    _put(root, path, _canonical(record))
    return 201


def _registration(root, folder):
    row = _read_record(
        root, folder / "utility.json", ("label", "mode"), {"utility_id": folder.name})
    if row and (row["mode"] not in ("manual", "stdio-v1") or not _label(row["label"])):
        raise ApiRefusal.fixed("store_error")
    return row


def _valid_result(result, mode, claim):
    if mode == "stdio-v1" and not claim:
        return False
    if result["state"] == "answered":
        return _text(result["reply"])
    return mode == "stdio-v1" and result["state"] == "unknown" and result["reply"] is None


def _state(root, utility, folder):
    identity = {"utility_id": utility["utility_id"], "exchange_id": folder.name}
    request = _read_record(root, folder / "request", ("text",), identity)
    claim = _read_record(root, folder / "claim", ("digest",), identity)
    result = _read_record(root, folder / "result", ("state", "reply"), identity)
    if request is None and (claim or result) or request and not _text(request["text"]):
        raise ApiRefusal.fixed("store_error")
    if claim and (utility["mode"] != "stdio-v1" or not _hex(claim["digest"])):
        raise ApiRefusal.fixed("store_error")
    if result and not _valid_result(result, utility["mode"], claim):
        raise ApiRefusal.fixed("store_error")
    return request, claim, result


def _exchange(request, claim, result):
    state = result["state"] if result else ("claimed" if claim else "pending")
    return {**request, "state": state, "reply": result["reply"] if result else None}


def _folders(root, parent, *, exclude=None):
    # Validate all directory components before enumerating, including an absent registry.
    _hold(root, parent / ".directory-check")
    if not parent.exists():
        return []
    folders = []
    for child in parent.iterdir():
        if child.name == exclude:
            continue
        if exclude and child.name.startswith(f".{exclude}.") and child.name.endswith(".tmp"):
            continue  # private staging file left before atomic registration
        if not _valid_id(child.name):
            raise ApiRefusal.fixed("store_error")
        _hold(root, child / ".directory-check")
        folders.append(child)
    return sorted(folders)


@contextmanager
def _safe_store():
    try:
        yield
    except (SnapshotRefused, OSError, OwnerRefused, UnicodeError, RecursionError):
        raise ApiRefusal.fixed("store_error") from None


def list_utilities(root):
    root = Path(root)
    utilities, exchanges = [], []
    gate = _root_gate(root)
    with _safe_store(), gate.lock:
        for folder in _folders(root, data_root(root) / "utilities"):
            utility = _registration(root, folder)
            exchange_dirs = _folders(root, folder, exclude="utility.json")
            if not utility:
                if exchange_dirs:
                    raise ApiRefusal.fixed("store_error")
                continue  # registration interrupted before first-file publication
            utilities.append(utility)
            for directory in exchange_dirs:
                request, claim, result = _state(root, utility, directory)
                if request:
                    exchanges.append(_exchange(request, claim, result))
    return {"utilities": utilities, "exchanges": exchanges}


def _exchange_op(root, utility, body):
    op = body["op"]
    identity = {key: body[key] for key in ("utility_id", "exchange_id")}
    folder = data_root(root) / "utilities" / utility["utility_id"] / body["exchange_id"]
    request, claim, result = _state(root, utility, folder)
    if op == "send":
        new = {**identity, "text": body["text"]}
        status = _publish(root, folder / "request", request, new)
        return status, {"exchange": _exchange(new, claim, result)}
    if not request or (utility["mode"] == "manual") != (op == "manual_reply"):
        raise ApiRefusal.fixed("record_conflict")
    if "claim_token" in body:
        digest = hashlib.sha256(body["claim_token"].encode("ascii")).hexdigest()
        if claim and not hmac.compare_digest(claim["digest"], digest):
            raise ApiRefusal.fixed("record_conflict")
        if op == "claim":
            new = {**identity, "digest": digest}
            status = _publish(root, folder / "claim", claim, new)
            return status, {"exchange": _exchange(request, new, result)}
    if utility["mode"] == "stdio-v1" and not claim:
        raise ApiRefusal.fixed("record_conflict")
    outcome = {"manual_reply": "answered", "mark_unknown": "unknown"}.get(op, body.get("outcome"))
    new = {**identity, "state": outcome, "reply": body.get("text")}
    status = _publish(root, folder / "result", result, new)
    return status, {"exchange": _exchange(request, claim, new)}


def apply(root, body):
    """Only a first claim (201) authorizes its peer to invoke; 200 is a receipt."""
    _validate(body)
    root = Path(root)
    gate = _root_gate(root)
    with _safe_store(), gate.lock, write_guard(root):
        folder = data_root(root) / "utilities" / body["utility_id"]
        utility = _registration(root, folder)
        if body["op"] == "attach":
            row = {key: body[key] for key in ("utility_id", "mode", "label")}
            if not utility and _folders(root, folder, exclude="utility.json"):
                raise ApiRefusal.fixed("store_error")
            status = _publish(root, folder / "utility.json", utility, row)
            return status, {"utility": row}
        if not utility:
            raise ApiRefusal.fixed("record_conflict")
        return _exchange_op(root, utility, body)
