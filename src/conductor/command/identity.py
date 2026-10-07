"""Pure relations for deciding whether found durable state is the expected state."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .contracts import canonical_json
from .run_store import StoredRecord

_ABSENT: Any = object()


def mapping_differences(
        expected: Mapping[str, Any], found: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every differing key; the key set comes from the serialized values."""
    return tuple(
        name for name in sorted(set(expected) | set(found))
        if expected.get(name, _ABSENT) != found.get(name, _ABSENT))


def record_fingerprint(row: StoredRecord) -> tuple[str, str]:
    """A complete contract-derived record identity, including unknown fields."""
    return row.kind, canonical_json(row.value.as_dict())


def history_equals(
        found: Sequence[StoredRecord], expected: Sequence[StoredRecord]) -> bool:
    """Compare ordered histories by every serialized fact, never a hand list."""
    return tuple(map(record_fingerprint, found)) == tuple(map(record_fingerprint, expected))


def history_is_one_of(
        found: Sequence[StoredRecord], allowed: Sequence[Sequence[StoredRecord]]) -> bool:
    """True only when the complete found history equals one allowed history."""
    return any(history_equals(found, expected) for expected in allowed)
