"""What `GET /command/quotas` answers in a project opened for viewing (spec 4.1.9, 4.5.4).

A view child never polls a quota source: nothing in it spawns, and the login is the active
project's to take. The desk still shows limits, so the hub keeps the last good answer of the
ACTIVE project in `<conduct-home>/limits.json` (`{"schema_version": 1, "project_id",
"taken_at", "quotas": <that answer as it was>}`) and `HubLimitsView` gives it back: the same
four keys an active answer has, taken as they were, plus `hub_snapshot` naming the project and
the time the hub took it. It has the one method `QuotaView` has, `payload(contracts, now)`, so
a `CommandApi` can hold either.

The file is another process's. It is read whole at every answer, refused past a size cap, and
admitted only when every key is exactly what the hub writes; anything else is "no data": an
empty `snapshots`, `hub_snapshot: null`, and this project's own provider rows. "No data" is
never a zero and never a partial answer. The reader writes nothing.
"""
from __future__ import annotations

import copy
import json
import math
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Any

from .adapters.provider import ProviderContract, provider_projection
from .contract_values import ContractError, _timestamp
from .quota_views import DEFAULT_QUOTA_MAX_AGE

#: The hub's file, directly inside `<conduct-home>`.
LIMITS_FILE = "limits.json"
#: Larger than any answer of a bounded provider roster: a bigger file is not the hub's.
MAX_BYTES = 512 * 1024
_SCHEMA = 1
_FILE_KEYS = frozenset({"schema_version", "project_id", "taken_at", "quotas"})
_ANSWER_KEYS = ("as_of", "max_age_seconds", "providers", "snapshots")
_HEX = frozenset("0123456789abcdef")


def _is_project_id(value: object) -> bool:
    return isinstance(value, str) and len(value) == 32 and set(value) <= _HEX


def _is_time(value: object) -> bool:
    try:
        _timestamp("taken_at", value)
    except ContractError:
        return False
    return isinstance(value, str) and value.endswith("Z")


def _is_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _is_rows(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(row, dict) for row in value)


def is_answer(quotas: object) -> bool:
    """Whether `quotas` is exactly the four-key answer of an active child, each key of its kind.

    The one test of the stored form: the hub writes only what passes it, and this module's
    reader admits only what passes it, so the file never holds what its own reader turns away.
    """
    return (isinstance(quotas, dict) and set(quotas) == set(_ANSWER_KEYS)
            and isinstance(quotas["as_of"], str) and _is_number(quotas["max_age_seconds"])
            and _is_rows(quotas["providers"]) and _is_rows(quotas["snapshots"]))


def _admitted(document: object) -> dict[str, Any] | None:
    """The stored answer with its `hub_snapshot`, or `None` when the file is not the hub's."""
    if not isinstance(document, dict) or set(document) != _FILE_KEYS:
        return None
    version = document["schema_version"]
    if type(version) is not int or version != _SCHEMA:
        return None
    if not _is_project_id(document["project_id"]) or not _is_time(document["taken_at"]):
        return None
    quotas = document["quotas"]
    if not is_answer(quotas):
        return None
    return {**{key: copy.deepcopy(quotas[key]) for key in _ANSWER_KEYS},
            "hub_snapshot": {"project_id": document["project_id"],
                             "taken_at": document["taken_at"]}}


class HubLimitsView:
    """The quota answer of a view child: the hub's last snapshot, or an honest "no data"."""

    def __init__(self, path: str | Path | None,
                 max_age: timedelta = DEFAULT_QUOTA_MAX_AGE) -> None:
        self._path = None if path is None else Path(path)
        self._max_age = max_age

    def payload(self, contracts: Iterable[ProviderContract], now: str) -> dict[str, Any]:
        """Answer from the snapshot file; this project's own provider rows when it is no data.

        Args:
            contracts: The reviewed provider descriptors of THIS project.
            now: The server clock, an RFC 3339 instant with `Z`.

        Returns:
            Exactly `as_of`, `max_age_seconds`, `providers`, `snapshots`, `hub_snapshot`.
        """
        stored = self._read()
        if stored is not None:
            return stored
        return {"as_of": now, "max_age_seconds": self._max_age.total_seconds(),
                "providers": provider_projection(contracts), "snapshots": [],
                "hub_snapshot": None}

    def _read(self) -> dict[str, Any] | None:
        if self._path is None:
            return None
        try:
            with self._path.open("rb") as handle:
                raw = handle.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                return None
            return _admitted(json.loads(raw.decode("utf-8")))
        except (OSError, ValueError):
            return None
