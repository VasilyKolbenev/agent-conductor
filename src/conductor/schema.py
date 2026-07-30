"""Protocol v1 validation. Pure: dicts in, (errors, warnings) out. Spec §4."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
SEVERITIES = frozenset({"blocker", "major", "minor", "note"})
DISPOSITIONS = frozenset({"confirmed", "refuted", "partial"})
NODE_STATUSES = frozenset({"pass", "fail", "blocked", "running", "idle"})
WAIT_KINDS = frozenset({"decision", "action", "review"})
EVENT_KINDS = frozenset({"ok", "fail", "warn", "stop", "info"})
DEFAULT_STALENESS_MINUTES = 360

Result = tuple[list[str], list[str]]  # (errors, warnings)


def _version_check(data: dict, where: str, errors: list, warnings: list) -> None:
    if "schema_version" not in data:
        errors.append(f"{where}: schema_version is required")
    elif data["schema_version"] != SCHEMA_VERSION:
        warnings.append(
            f"{where}: schema_version {data['schema_version']!r} is not {SCHEMA_VERSION}; "
            "proceeding without guessing")


def parse_iso(value: Any) -> datetime | None:
    """Tolerant ISO-8601 parse; None on failure (caller decides error vs warning).

    Naive timestamps are coerced to UTC: a tz-naive `updated` is sloppy but legal
    input, and comparing naive vs aware datetimes would crash the whole merge —
    a tolerant-reader violation (spec §3.5)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)   # timezone imported at header
    return parsed


def validate_map(data: Any) -> Result:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return (["map: top level must be a table"], warnings)
    _version_check(data, "map", errors, warnings)

    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("map: at least one node is required")
        nodes = []
    ids: set[str] = set()
    for n in nodes:
        nid = n.get("id") if isinstance(n, dict) else None
        if not isinstance(nid, str) or not nid:
            errors.append("map: every node needs a non-empty string id")
            continue
        if nid in ids:
            errors.append(f"map: duplicate node id {nid!r}")
        ids.add(nid)
    for n in nodes:
        if not isinstance(n, dict):
            continue
        for dep in n.get("depends_on", []):
            if dep not in ids:
                errors.append(f"map: node {n.get('id')!r} depends_on unknown id {dep!r}")

    cycle = data.get("cycle", {})
    roles = cycle.get("roles", []) if isinstance(cycle, dict) else []
    role_ids: set[str] = set()
    for r in roles:
        rid = r.get("id") if isinstance(r, dict) else None
        if not isinstance(rid, str) or not rid:
            errors.append("map: every role needs a non-empty string id")
            continue
        if rid in role_ids:
            errors.append(f"map: duplicate role id {rid!r}")
        role_ids.add(rid)
    for r in roles:
        if not isinstance(r, dict):
            continue
        for reviewed in r.get("reviews", []):
            if reviewed not in role_ids:
                errors.append(f"map: role {r.get('id')!r} reviews unknown role {reviewed!r}")

    phases = cycle.get("phases", []) if isinstance(cycle, dict) else []
    if not all(isinstance(p, str) for p in phases):
        errors.append("map: cycle.phases must be strings")

    inv_ids: set[str] = set()
    for inv in data.get("invariants", []):
        iid = inv.get("id") if isinstance(inv, dict) else None
        if not isinstance(iid, str) or not iid:
            errors.append("map: every invariant needs a non-empty string id")
            continue
        if iid in inv_ids:
            errors.append(f"map: duplicate invariant id {iid!r}")
        inv_ids.add(iid)
    return errors, warnings
