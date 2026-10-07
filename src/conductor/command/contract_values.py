"""The values every December Command document is built out of, and their rules.

Split out of ``contracts`` when that module crossed the 800-line cap: this file
is the self-contained validation circuit -- the identifier, instant, digest and
JSON grammars, the closed state vocabularies, and the canonical-JSON spelling
every digest in the product is taken over. The record contracts next door are
built ENTIRELY from these, and import them back under their old names, so no
caller anywhere learns that the split happened.

Like its parent it has no filesystem, subprocess, server or adapter imports: a
value's rules must be checkable without anything being able to run.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any


class ContractError(ValueError):
    """A v2 document is malformed or asks for authority it cannot express."""


class ControlMode(str, Enum):
    """The complete authority ladder; there is no hidden autonomous mode."""

    OBSERVE = "observe"
    PROPOSE = "propose"
    CONFIRM = "confirm"
    POLICY = "policy"


_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
# The one UTC instant spelling this contract will ever hold, character for
# character the same grammar the Cockpit's UTC_INSTANT holds. The digit classes
# are spelled [0-9] rather than \d on purpose: Python's \d also matches non-ASCII
# decimal digits, which JavaScript's does not, and int() would then read them.
_UTC_INSTANT_RE = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.[0-9]+)?(?:Z|\+00:00)\Z")
_RUN_STATES = frozenset({
    "created", "active", "paused", "blocked", "complete", "failed",
    "cancelled", "unknown",
})
_RESULT_OUTCOMES = frozenset({
    "succeeded", "failed", "cancelled", "rejected", "unknown",
    "verification_failed",
})
_VERIFICATION_STATES = frozenset({
    "unverified", "verified", "unavailable", "mismatch", "error",
})
_DECISION_ACTIONS = frozenset({
    "approve", "reject", "request_changes", "waive",
})
# The observation health vocabulary lives in the contract layer so the durable
# ObservationRecord and the live AdapterObservation read one source of truth; an
# unknown is one of these states, never silently promoted to a ready.
HEALTH_STATES = frozenset({"ready", "busy", "offline", "degraded", "unknown"})


def _id(name: str, value: object) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ContractError(
            f"{name} must match [A-Za-z0-9][A-Za-z0-9._-]{{0,127}}, got {value!r}")
    return value


def _text(name: str, value: object, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ContractError(f"{name} must be a non-empty string, got {value!r}")
    if "\x00" in value:
        raise ContractError(f"{name} must not contain NUL")
    return value


def _timestamp(name: str, value: object) -> str:
    """Accept exactly one frozen UTC grammar, identically on every Python we support.

    The grammar is ``YYYY-MM-DDTHH:MM:SS`` with an optional fractional second and a
    ``Z`` or ``+00:00`` suffix; the hour is 00..23, so ``24:00:00`` names no instant
    here, and ``instantIsValid`` in ``panel/command-projection.js`` holds the same
    grammar. The accept path deliberately never calls ``datetime.fromisoformat``,
    whose accepted set widens between the Pythons this package supports: here the
    regex fixes the spelling, the captured integers are range-checked outright, and
    calendar truth comes from the ``datetime`` constructor.
    ``tests/test_command_instant_parity.py`` records the interpreter differences.

    Raises:
        ContractError: The value is not a string, does not match the frozen grammar,
            or names no day on the proleptic Gregorian calendar.
    """
    matched = _UTC_INSTANT_RE.fullmatch(value) if isinstance(value, str) else None
    if matched is None:
        raise ContractError(f"{name} must be an RFC 3339 UTC string, got {value!r}")
    year, month, day, hour, minute, second = (int(part) for part in matched.groups())
    if hour > 23 or minute > 59 or second > 59:
        raise ContractError(f"{name} must be an RFC 3339 UTC string, got {value!r}")
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError as e:
        raise ContractError(f"{name} must be an RFC 3339 UTC string, got {value!r}") from e
    return value


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise ContractError(f"{name} must be sha256 followed by 64 lowercase hex digits")
    return value


def _schema(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise ContractError(f"schema_version must be an integer >= 2, got {value!r}")
    return value


def _enum(name: str, value: object, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{name} must be one of {sorted(allowed)}, got {value!r}")
    return value


def _mode(value: object) -> ControlMode:
    try:
        return value if isinstance(value, ControlMode) else ControlMode(value)
    except (TypeError, ValueError) as e:
        raise ContractError(
            f"mode must be one of {[m.value for m in ControlMode]}, got {value!r}") from e


def _json_copy(name: str, value: object) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        return json.loads(encoded)
    except (TypeError, ValueError) as e:
        raise ContractError(f"{name} must contain canonical JSON data: {e}") from e


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _object(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be a JSON object, got {value!r}")
    if any(not isinstance(k, str) for k in value):
        raise ContractError(f"{name} keys must be strings")
    copied = _json_copy(name, dict(value))
    assert isinstance(copied, dict)  # established by the Mapping check and JSON round-trip
    return _freeze_json(copied)


def _extra(value: object, reserved: Iterable[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"extra must be a JSON object, got {value!r}")
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ContractError("extra keys must be strings")
        copied[key] = _freeze_json(_json_copy(f"extra field {key!r}", item))
    collision = sorted(set(copied) & set(reserved))
    if collision:
        raise ContractError(f"extra must not replace known fields: {collision}")
    return MappingProxyType(copied)


def _scope(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ContractError("scope must be a non-empty list of canonical project-relative paths")
    result: list[str] = []
    for raw in value:
        if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
            raise ContractError(f"scope contains a non-canonical path: {raw!r}")
        if re.match(r"[A-Za-z]:", raw) or ":" in raw:
            raise ContractError(f"scope path must not name a drive or URI: {raw!r}")
        path = PurePosixPath(raw)
        if path.is_absolute() or ".." in path.parts or str(path) != raw:
            raise ContractError(f"scope path must stay project-relative and canonical: {raw!r}")
        result.append(raw)
    return tuple(result)


def _ids(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractError(f"{name} must be a list of ids")
    return tuple(_id(name, item) for item in value)


def _unique_ids(name: str, value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ContractError(f"{name} must be a list of ids, not a single string")
    refs = _ids(name, value)
    if len(set(refs)) != len(refs):
        raise ContractError(f"{name} must not contain duplicates")
    return refs


#: Tells "the field was not there" apart from "the field was there and was
#: null". They are different sentences: absence says this action belongs to no
#: graph node, while a present null is a caller naming a node and naming nothing.
ABSENT = object()


def _bound_id(name: str, value: object) -> str | None:
    """An optional identifier: absent, or a real id. Never a present null.

    A field that may be missing is not a field that may be empty. Allowing
    ``null`` would give two spellings for "unbound", and every reader would then
    have to treat them as one -- which is how a binding quietly becomes optional
    to check as well as optional to carry.
    """
    if value is ABSENT:
        return None
    if value is None:
        raise ContractError(
            f"{name} must be omitted when there is none; null is not a spelling of absent")
    return _id(name, value)


def _raw(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"contract document must be a JSON object, got {value!r}")
    return dict(value)


def _take(data: dict[str, Any], name: str) -> Any:
    try:
        return data.pop(name)
    except KeyError as e:
        raise ContractError(f"missing required field {name}") from e


def canonical_json(value: object) -> str:
    """Return the one JSON spelling used for digests, receipts, and previews."""
    payload = value.as_dict() if hasattr(value, "as_dict") else value
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as e:
        raise ContractError(f"value is not canonical JSON data: {e}") from e


def _content_digest(payload: Mapping[str, Any]) -> str:
    """Digest the canonical JSON of a payload; the one spelling a preview pins."""
    return "sha256:" + hashlib.sha256(
        canonical_json(dict(payload)).encode("utf-8")).hexdigest()
