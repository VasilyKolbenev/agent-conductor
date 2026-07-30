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


def _version_check(data: dict, where: str, errors: list[str], warnings: list[str]) -> None:
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _validate_nodes(data: dict, errors: list[str]) -> None:
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
        nid = n.get("id")
        depends_on = n.get("depends_on", [])
        if not isinstance(depends_on, list):
            errors.append(f"map: node {nid!r} depends_on must be a list")
            continue
        for dep in depends_on:
            if not isinstance(dep, str):
                errors.append(
                    f"map: node {nid!r} depends_on element must be a string, got {dep!r}")
            elif dep not in ids:
                errors.append(f"map: node {nid!r} depends_on unknown id {dep!r}")


def _validate_cycle(data: dict, errors: list[str]) -> None:
    if "cycle" not in data:
        return
    cycle = data["cycle"]
    if not isinstance(cycle, dict):
        errors.append("map: cycle must be a table")
        return

    roles = cycle.get("roles", [])
    if not isinstance(roles, list):
        errors.append("map: cycle.roles must be a list of tables")
        roles = []
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
        rid = r.get("id")
        reviews = r.get("reviews", [])
        if not isinstance(reviews, list):
            errors.append(f"map: role {rid!r} reviews must be a list")
            continue
        for reviewed in reviews:
            if not isinstance(reviewed, str):
                errors.append(
                    f"map: role {rid!r} reviews element must be a string, got {reviewed!r}")
            elif reviewed not in role_ids:
                errors.append(f"map: role {rid!r} reviews unknown role {reviewed!r}")

    if "phases" in cycle:
        phases = cycle["phases"]
        if not isinstance(phases, list) or not all(isinstance(p, str) for p in phases):
            errors.append("map: cycle.phases must be a list of strings")


def _validate_invariants(data: dict, errors: list[str]) -> None:
    if "invariants" not in data:
        return
    invariants = data["invariants"]
    if not isinstance(invariants, list):
        errors.append("map: invariants must be a list of tables")
        return
    inv_ids: set[str] = set()
    for inv in invariants:
        iid = inv.get("id") if isinstance(inv, dict) else None
        if not isinstance(iid, str) or not iid:
            errors.append("map: every invariant needs a non-empty string id")
            continue
        if iid in inv_ids:
            errors.append(f"map: duplicate invariant id {iid!r}")
        inv_ids.add(iid)


def validate_map(data: Any) -> Result:
    """Validate a parsed `map.toml` against Protocol v1 (spec section 2).

    Only `schema_version` and `nodes` are required. `project`, `cycle`
    (and its `cycle.roles` / `cycle.phases`), and `invariants` are all
    optional — a map containing only `nodes` is valid.

    Args:
        data: The parsed map. Expected to be a dict (table); any other
            top-level shape is itself an error.

    Returns:
        A `(errors, warnings)` pair of human-readable messages. Errors
        mean the map is invalid and MUST block further processing;
        warnings are informational only (e.g. an unrecognized
        `schema_version`, accepted without guessing per spec section 5)
        and never block.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return (["map: top level must be a table"], warnings)
    _version_check(data, "map", errors, warnings)
    _validate_nodes(data, errors)
    _validate_cycle(data, errors)
    _validate_invariants(data, errors)
    return errors, warnings
