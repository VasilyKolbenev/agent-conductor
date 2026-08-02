"""Protocol v1 validation. Pure: dicts in, (errors, warnings) out. Spec §4."""
from __future__ import annotations

import math
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


def _validate_nodes(data: dict, errors: list[str], warnings: list[str]) -> None:
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
        for key in ("label", "kind"):
            # TOML yields datetime.date/int for unquoted values — they would
            # crash json.dumps(state) or type-pollute it (task 15.5).
            if key in n and not isinstance(n[key], str):
                errors.append(f"map: node {nid!r} {key} must be a string, got {n[key]!r}")
        if "row" in n:
            warnings.append(f"map: node {nid!r} row is deprecated and ignored")  # ADR 0001
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
        if "harness" in r and not isinstance(r["harness"], str):
            errors.append(f"map: role {rid!r} harness must be a string, got {r['harness']!r}")
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
        if "text" in inv and not isinstance(inv["text"], str):
            errors.append(f"map: invariant {iid!r} text must be a string, got {inv['text']!r}")


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
        `schema_version`, accepted without guessing per spec section 5,
        or a deprecated node `row` key, accepted and ignored per
        ADR 0001) and never block.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return (["map: top level must be a table"], warnings)
    _version_check(data, "map", errors, warnings)
    if "project" in data and not isinstance(data["project"], str):
        errors.append(f"map: project must be a string, got {data['project']!r}")
    _validate_nodes(data, errors, warnings)
    _validate_cycle(data, errors)
    _validate_invariants(data, errors)
    return errors, warnings


def _in_vocab(value: Any, vocab: frozenset[str]) -> bool:
    """True iff `value` is a string member of `vocab` — never raises on unhashable input."""
    return isinstance(value, str) and value in vocab


def _validate_lane_core(data: dict, filename_stem: str, where: str, errors: list[str]) -> None:
    """Check author/updated/role/staleness_after_minutes/now (spec §3, §5)."""
    if data.get("author") != filename_stem:
        errors.append(f"{where}: author {data.get('author')!r} must equal filename stem")
    if parse_iso(data.get("updated")) is None:
        errors.append(f"{where}: updated must be ISO-8601")
    role = data.get("role")
    if role is not None and (not isinstance(role, str) or not role):
        errors.append(f"{where}: role must be a non-empty string when present")
    threshold = data.get("staleness_after_minutes")
    if threshold is not None:
        # NaN/inf pass isinstance(float) but crash timedelta in merge; NaN also
        # fails every comparison, so the check is spelled out positively.
        numeric = isinstance(threshold, (int, float)) and not isinstance(threshold, bool)
        if not (numeric and math.isfinite(threshold) and threshold > 0):
            errors.append(f"{where}: staleness_after_minutes must be a finite "
                          f"number > 0, got {threshold!r}")
    now = data.get("now")
    if now is not None and not isinstance(now, dict):
        errors.append(f"{where}: now must be an object")


def _validate_lane_map_status(data: dict, where: str, errors: list[str]) -> None:
    if "map_status" not in data:
        return
    map_status = data["map_status"]
    if not isinstance(map_status, dict):
        errors.append(f"{where}: map_status must be an object")
        return
    for node_id, status in map_status.items():
        if not _in_vocab(status, NODE_STATUSES):
            errors.append(f"{where}: map_status[{node_id!r}]={status!r} not in "
                          f"{sorted(NODE_STATUSES)}")


def _validate_lane_findings(data: dict, where: str, errors: list[str]) -> None:
    if "findings" not in data:
        return
    findings = data["findings"]
    if not isinstance(findings, list):
        errors.append(f"{where}: findings must be a list")
        return
    seen: set[str] = set()
    for f in findings:
        fid = f.get("id") if isinstance(f, dict) else None
        if not isinstance(fid, str) or not fid:
            errors.append(f"{where}: every finding needs a non-empty string id")
            continue
        if fid in seen:
            errors.append(f"{where}: duplicate finding id {fid!r}")
        seen.add(fid)
        if not _in_vocab(f.get("severity"), SEVERITIES):
            errors.append(f"{where}: finding {fid!r} severity {f.get('severity')!r} "
                          f"not in {sorted(SEVERITIES)}")
        for key in ("title", "claim"):
            if not isinstance(f.get(key), str) or not f.get(key):
                errors.append(f"{where}: finding {fid!r} needs a non-empty {key}")
        if "refs" in f:
            refs = f["refs"]
            if not isinstance(refs, list):
                errors.append(f"{where}: finding {fid!r} refs must be a list")
            else:
                for ref in refs:
                    if not isinstance(ref, str):
                        errors.append(
                            f"{where}: finding {fid!r} refs element must be a string, "
                            f"got {ref!r}")


def _validate_lane_verdicts(data: dict, where: str, errors: list[str]) -> None:
    if "verdicts" not in data:
        return
    verdicts = data["verdicts"]
    if not isinstance(verdicts, dict):
        errors.append(f"{where}: verdicts must be an object")
        return
    for fid, v in verdicts.items():
        if not isinstance(v, dict) or not _in_vocab(v.get("disposition"), DISPOSITIONS):
            errors.append(f"{where}: verdict {fid!r} disposition must be one of "
                          f"{sorted(DISPOSITIONS)}")


def _validate_lane_waits(data: dict, where: str, errors: list[str]) -> None:
    if "waits_on_human" not in data:
        return
    waits = data["waits_on_human"]
    if not isinstance(waits, list):
        errors.append(f"{where}: waits_on_human must be a list")
        return
    seen: set[str] = set()
    for w in waits:
        wid = w.get("id") if isinstance(w, dict) else None
        if not isinstance(wid, str) or not wid:
            errors.append(f"{where}: every waits_on_human item needs an id")
            continue
        if wid in seen:
            errors.append(f"{where}: duplicate waits_on_human id {wid!r}")
        seen.add(wid)
        if not _in_vocab(w.get("kind"), WAIT_KINDS):
            errors.append(f"{where}: wait {wid!r} kind {w.get('kind')!r} "
                          f"not in {sorted(WAIT_KINDS)}")
        if "blocks" in w:
            blocks = w["blocks"]
            if not isinstance(blocks, list):
                errors.append(f"{where}: wait {wid!r} blocks must be a list")
            else:
                for b in blocks:
                    if not isinstance(b, str):
                        errors.append(
                            f"{where}: wait {wid!r} blocks element must be a string, "
                            f"got {b!r}")


def _validate_lane_invariants(data: dict, where: str, errors: list[str]) -> None:
    if "invariants" not in data:
        return
    invariants = data["invariants"]
    if not isinstance(invariants, list):
        errors.append(f"{where}: invariants must be a list")
        return
    for inv in invariants:
        if not isinstance(inv, dict) or not isinstance(inv.get("id"), str) \
                or not isinstance(inv.get("ok"), bool):
            errors.append(f"{where}: invariants need string id + boolean ok")


def validate_lane(data: Any, *, filename_stem: str) -> Result:
    """Validate a parsed lane file against Protocol v1 (spec section 3).

    Every collection field (`map_status`, `findings`, `verdicts`,
    `waits_on_human`, `invariants`, `now`) is shape-guarded before it is
    iterated: a wrong-typed present field produces exactly one clear error
    instead of a silent bypass or per-character garbage, mirroring
    `validate_map`.

    Args:
        data: The parsed lane JSON. Expected to be a dict; any other
            top-level shape is itself an error.
        filename_stem: The lane's filename without extension (e.g.
            `"claude"` for `conductor/lanes/claude.json`) — must equal
            `data["author"]`.

    Returns:
        A `(errors, warnings)` pair, same contract as `validate_map`.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(data, dict):
        return ([f"lane {filename_stem}: top level must be an object"], warnings)
    where = f"lane {filename_stem}"
    _version_check(data, where, errors, warnings)
    _validate_lane_core(data, filename_stem, where, errors)
    _validate_lane_map_status(data, where, errors)
    _validate_lane_findings(data, where, errors)
    _validate_lane_verdicts(data, where, errors)
    _validate_lane_waits(data, where, errors)
    _validate_lane_invariants(data, where, errors)
    return errors, warnings


def validate_event(obj: Any) -> list[str]:
    """Validate one parsed line of `events.jsonl` against Protocol v1 (spec section 4).

    Args:
        obj: The parsed JSON object for one event line.

    Returns:
        A list of human-readable error strings; empty means the event
        line is valid. Per spec, malformed lines are skipped by readers
        rather than fatal — this function only classifies one line.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["event line must be an object"]
    if parse_iso(obj.get("ts")) is None:
        errors.append("event: ts must be ISO-8601")
    if not isinstance(obj.get("author"), str) or not obj.get("author"):
        errors.append("event: author is required")
    if not _in_vocab(obj.get("kind"), EVENT_KINDS):
        errors.append(f"event: kind {obj.get('kind')!r} not in {sorted(EVENT_KINDS)}")
    if not isinstance(obj.get("text"), str) or not obj.get("text"):
        errors.append("event: text is required")
    return errors
