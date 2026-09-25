"""Closed immutable ownership generations and non-authorizing layout reads."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from .ownership_errors import OwnerRefused

HOME = ".conduct"
RECORDS = "ownership"
ANCHOR = ".conduct-owner"
TREE = ".conduct-owner-tree"
LEGACY = "conductor"
ACTIVE = "conductor.v3"
_GENERATION = re.compile(r"gen-([0-9]{8})\.json")
_FIELDS = frozenset({"schema", "generation", "previous_digest", "phase", "nonce",
    "root_identity", "data_identity", "fence_identity", "fence_digest", "data_digest",
    "session_id", "boot_id", "recovered_session"})
_NEXT = {None: {"prepared"}, "prepared": {"moved"}, "moved": {"active"},
    "active": {"opened", "rollback_prepared"}, "opened": {"closed", "recovered"},
    "closed": {"opened"}, "recovered": {"opened"},
    "rollback_prepared": {"fence_retired"}, "fence_retired": {"rolled_back"},
    "rolled_back": set()}


def identity(path):
    from .ownership_native import identity as native_identity
    return native_identity(path)


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def digest(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def refuse_os(error, detail):
    raise OwnerRefused("ownership_unavailable", detail) from error


def plain(path, *, directory):
    found = os.lstat(path)
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(found.st_mode) or stat.S_ISLNK(found.st_mode) or getattr(found, "st_reparse_tag", 0):
        raise OwnerRefused("transition_conflict", "ownership route is not a plain local object")
    if not directory and found.st_nlink != 1:
        raise OwnerRefused("transition_conflict", "ownership file has multiple names")
    return found


def exclusive(path, payload):
    with open(path, "xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _pair(value):
    return type(value) is list and len(value) == 2 and all(type(n) is int and n >= 0 for n in value)


def _hex(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None


def _digest(value):
    return type(value) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def validate_record(value, previous):
    if type(value) is not dict or set(value) != _FIELDS or type(value["schema"]) is not int or value["schema"] != 1:
        raise OwnerRefused("transition_conflict", "ownership generation has an unknown shape")
    if type(value["generation"]) is not int or value["generation"] != (0 if previous is None else previous["generation"] + 1):
        raise OwnerRefused("transition_conflict", "ownership generation sequence is incomplete")
    expected = None if previous is None else digest(canonical(previous))
    phase = None if previous is None else previous["phase"]
    if (value["previous_digest"] != expected or type(value["phase"]) is not str
            or value["phase"] not in _NEXT.get(phase, set())):
        raise OwnerRefused("transition_conflict", "ownership generation does not extend its predecessor")
    if not _hex(value["nonce"]) or not _pair(value["root_identity"]) or not _pair(value["data_identity"]):
        raise OwnerRefused("transition_conflict", "ownership identities are malformed")
    if not _digest(value["data_digest"]) or not _digest(value["fence_digest"]):
        raise OwnerRefused("transition_conflict", "ownership content facts are malformed")
    if value["fence_digest"] != digest(fence_bytes(value["nonce"])):
        raise OwnerRefused("transition_conflict", "fence bytes do not bind the transition nonce")
    if value["phase"] in {"prepared", "moved"}:
        if value["fence_identity"] is not None:
            raise OwnerRefused("transition_conflict", "uncreated fence cannot have provenance")
    elif not _pair(value["fence_identity"]):
        raise OwnerRefused("transition_conflict", "fence creation identity is missing")
    _validate_session(value, previous)
    if previous is not None:
        for key in ("nonce", "root_identity", "data_identity", "data_digest", "fence_digest"):
            if value[key] != previous[key]:
                raise OwnerRefused("transition_conflict", "ownership generation changed immutable subject")
        if previous["fence_identity"] is not None and value["fence_identity"] != previous["fence_identity"]:
            raise OwnerRefused("transition_conflict", "ownership generation changed its fence")


def _validate_session(value, previous):
    phase = value["phase"]
    if phase not in {"opened", "closed", "recovered"}:
        if any(value[k] is not None for k in ("session_id", "boot_id", "recovered_session")):
            raise OwnerRefused("transition_conflict", "transition cannot claim a live session")
        return
    if (not _hex(value["session_id"]) or type(value["boot_id"]) is not str
            or re.fullmatch(r"(?:windows|linux|darwin):[0-9a-f-]{36}", value["boot_id"]) is None):
        raise OwnerRefused("transition_conflict", "owner session identity is malformed")
    if phase == "opened":
        if value["recovered_session"] is not None or value["session_id"] == previous["session_id"]:
            raise OwnerRefused("transition_conflict", "new owner cannot impersonate recovery")
    else:
        if value["session_id"] != previous["session_id"]:
            raise OwnerRefused("transition_conflict", "session ending names another owner")
        if phase == "closed" and (value["boot_id"] != previous["boot_id"] or value["recovered_session"] is not None):
            raise OwnerRefused("transition_conflict", "clean close changed boot identity")
        if phase == "recovered" and (value["boot_id"] == previous["boot_id"]
                or value["recovered_session"] != previous["session_id"]):
            raise OwnerRefused("transition_conflict", "crash recovery requires a different OS boot")


def chain(root):
    folder = root / HOME / RECORDS
    plain(root / HOME, directory=True)
    plain(folder, directory=True)
    names = sorted(folder.iterdir())
    if not names or len(names) > 100_000:
        raise OwnerRefused("transition_conflict", "ownership generations are absent or exceed the bound")
    previous = None
    for number, path in enumerate(names):
        match = _GENERATION.fullmatch(path.name)
        if match is None or int(match[1]) != number:
            raise OwnerRefused("transition_conflict", "ownership namespace contains an unknown or missing generation")
        plain(path, directory=False)
        payload = path.read_bytes()
        if len(payload) > 8192:
            raise OwnerRefused("transition_conflict", "ownership generation is oversized")
        try:
            value = json.loads(payload)
        except (UnicodeError, ValueError) as error:
            raise OwnerRefused("transition_conflict", "ownership generation is incomplete or invalid") from error
        try:
            if canonical(value) != payload:
                raise OwnerRefused("transition_conflict", "ownership generation is not canonical")
        except (UnicodeError, ValueError, TypeError) as error:
            raise OwnerRefused("transition_conflict", "ownership generation has invalid JSON values") from error
        validate_record(value, previous)
        previous = value
    return previous


def publish(root, previous, **changes):
    value = dict(previous or {})
    value.update(changes, schema=1, generation=0 if previous is None else previous["generation"] + 1,
        previous_digest=None if previous is None else digest(canonical(previous)))
    validate_record(value, previous)
    target = root / HOME / RECORDS / f"gen-{value['generation']:08d}.json"
    exclusive(target, canonical(value))
    return value


def fence_bytes(nonce):
    return f"December Command owned namespace\n{nonce}\n".encode("ascii")


def validate_live(root, head):
    if tuple(head["root_identity"]) != identity(root):
        raise OwnerRefused("ownership_lost", "project root identity changed; copy/restore requires explicit rebind")
    moved = root / ACTIVE
    plain(moved, directory=True)
    if tuple(head["data_identity"]) != identity(moved):
        raise OwnerRefused("ownership_lost", "owned data directory identity changed")
    fence = root / LEGACY
    plain(fence, directory=False)
    if tuple(head["fence_identity"]) != identity(fence) or fence.read_bytes() != fence_bytes(head["nonce"]):
        raise OwnerRefused("ownership_lost", "legacy-writer fence is absent, replaced or changed")


def state(root):
    root = Path(root).resolve()
    if not os.path.lexists(root / HOME):
        if os.path.lexists(root / ACTIVE) or (os.path.lexists(root / LEGACY) and not (root / LEGACY).is_dir()):
            raise OwnerRefused("transition_conflict", "owned namespace has no verified transition history")
        return root, None
    try:
        head = chain(root)
        if head["phase"] == "rolled_back":
            plain(root / LEGACY, directory=True)
            if identity(root / LEGACY) != tuple(head["data_identity"]) or os.path.lexists(root / ACTIVE):
                raise OwnerRefused("transition_conflict", "rolled-back namespace changed")
        elif head["phase"] in {"active", "opened", "closed", "recovered"}:
            validate_live(root, head)
        else:
            raise OwnerRefused("recovery_required", "ownership transition was interrupted; preserve both names")
        return root, head
    except OSError as error:
        refuse_os(error, "ownership state cannot be established")
