"""The merge engine — pure functions implementing spec §5 exactly.

Every computed value is derived; no author can write a disagreement, a stale
flag, or a queue de-dup. Silence is never consent.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from conductor import schema
from conductor.schema import DEFAULT_STALENESS_MINUTES

EVENTS_TAIL = 500


def _lane_view(entry: dict, now: datetime, warnings: list[str]) -> dict:
    author = entry["author"]
    data = entry.get("data")
    if data is None:
        return {"author": author, "role": None, "updated": None, "stale": False,
                "broken": True, "error": entry.get("error") or "unreadable",
                "now": {}, "_data": None, "_dt": None, "_future": False}
    dt = schema.parse_iso(data.get("updated"))
    threshold = data.get("staleness_after_minutes", DEFAULT_STALENESS_MINUTES)
    future = dt is not None and dt > now
    if future:
        warnings.append(f"lane {author}: updated is in the future (clock skew?)")
    stale = dt is not None and not future and (now - dt) > timedelta(minutes=threshold)
    return {"author": author, "role": data.get("role"), "updated": data.get("updated"),
            "stale": stale, "broken": False, "error": None,
            "now": data.get("now", {}), "_data": data, "_dt": dt, "_future": future}


def merge(map_data: dict | None, map_error: str | None, lanes: list[dict],
          events: list[dict], skipped_events: int, now: datetime,
          *, extra_warnings: tuple[str, ...] | list[str] = ()) -> dict:
    """Merge a parsed map, raw lanes, and events into a `state.json` dict.

    All rules are pure functions of the inputs, per PROTOCOL.md §6: no
    author can write a disagreement, a stale flag, or a contested-node
    verdict directly — silence is never consent.

    Args:
        map_data: The parsed `map.toml`, already passed through
            `schema.validate_map`, or None if the map failed to load.
        map_error: The map's load/validation error, when `map_data` is None.
        lanes: Raw lane entries, each `{"author", "data", "error"}`. When
            `data` is not None it has already passed `schema.validate_lane` —
            that upstream guarantee is why a live lane always has a
            parseable `updated`.
        events: Parsed `events.jsonl` records, oldest first.
        skipped_events: Count of malformed event lines skipped by the loader.
        now: The current time, used for staleness and future-dating checks.
            MUST be tz-aware — `schema.parse_iso` yields aware datetimes, and
            comparing them against a naive `now` raises TypeError.
        extra_warnings: Loader-level warnings (e.g. schema-version mismatches)
            to fold into the output `warnings` list.

    Returns:
        The `state.json` dict per PROTOCOL.md §6.1.
    """
    # extra_warnings: schema-version and other loader-level warnings (§4.5) —
    # store.load collects them, callers pass them through so they surface in state.
    warnings: list[str] = list(extra_warnings)
    if map_data is None:
        warnings.append(f"map is unreadable: {map_error}")
        map_data = {"nodes": [], "cycle": {}, "invariants": []}
    if skipped_events:
        warnings.append(f"events.jsonl: skipped {skipped_events} malformed line(s)")

    views = [_lane_view(entry, now, warnings) for entry in lanes]
    live = [v for v in views if not v["broken"]]

    nodes = _nodes(map_data, live, warnings)
    findings = _findings(map_data, views, warnings)
    queue = _human_queue(live)
    invariants = _invariants(map_data, live, warnings)
    cycle = _cycle(map_data, live, warnings)

    lanes_out = [{k: v for k, v in view.items() if not k.startswith("_")}
                 for view in views]
    disagreements = [f for f in findings if f["review_state"] == "disagreement"]
    kpi = {
        "nodes_pass": sum(1 for n in nodes if n["status"] == "pass"),
        "nodes_total": len(nodes),
        "blockers": sum(1 for f in findings if f["severity"] == "blocker"),
        "queue": len(queue),
        "disagreements": len(disagreements),
        "broken_lanes": sum(1 for v in views if v["broken"]),
        "stale_lanes": sum(1 for v in views if v["stale"]),
    }
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "project": map_data.get("project", ""),
        "map": {"nodes": nodes},
        "cycle": cycle,
        "lanes": lanes_out,
        "findings": findings,
        "disagreements": disagreements,
        "human_queue": queue,
        "invariants": invariants,
        "events_tail": list(reversed(events[-EVENTS_TAIL:])),
        "kpi": kpi,
        "warnings": warnings,
    }


# Under no-last-write-wins, the recency race only runs among AGREEING
# voters, where the value is identical — recency is deliberately
# unobservable and untested (documented in the plan).
def _nodes(map_data: dict, live: list[dict], warnings: list[str]) -> list[dict]:
    known = {n["id"] for n in map_data.get("nodes", [])}
    votes: dict[str, list[tuple]] = {}          # node_id -> [(dt, future, author, status)]
    for v in live:
        for nid, status in (v["_data"].get("map_status") or {}).items():
            if nid not in known:
                warnings.append(
                    f"lane {v['author']}: map_status key {nid!r} is not a map node — ignored")
                continue
            votes.setdefault(nid, []).append((v["_dt"], v["_future"], v["author"], status))
    out = []
    for n in map_data.get("nodes", []):
        cast = votes.get(n["id"], [])
        statuses = {s for (_, _, _, s) in cast}
        eligible = [c for c in cast if not c[1]]   # future voters never win (owner decision)
        if len(statuses) > 1:
            status, contested = "contested", sorted(a for (_, _, a, _) in cast)
        elif eligible:
            eligible.sort(key=lambda c: (c[0] is not None, c[0]))
            status, contested = eligible[-1][3], []
        else:
            status, contested = "idle", []   # sole-future-voter node stays idle (§6)
        out.append({"id": n["id"], "label": n.get("label", n["id"]),
                    "kind": n.get("kind", ""), "depends_on": n.get("depends_on", []),
                    "status": status, "contested_by": contested})
    return out

def _findings(map_data: dict, views: list[dict], warnings: list[str]) -> list[dict]:
    live = [v for v in views if not v["broken"]]
    roles = {r["id"]: r for r in (map_data.get("cycle", {}) or {}).get("roles", [])}
    role_holders: dict[str, list] = {}
    for v in live:
        role = v["role"]
        if role is not None and role not in roles:
            warnings.append(f"lane {v['author']}: role {role!r} is not in cycle.roles — "
                            "treated as observer")
            v = {**v, "role": None}
        if v["role"]:
            role_holders.setdefault(v["role"], []).append(v)

    owners: dict[str, list] = {}                      # finding id -> [(view, finding)]
    for v in live:
        for f in v["_data"].get("findings", []):
            owners.setdefault(f["id"], []).append((v, f))
    known_ids = set(owners)

    verdicts_on: dict[str, dict[str, dict]] = {}      # fid -> author -> verdict
    for v in live:
        for fid, verdict in (v["_data"].get("verdicts") or {}).items():
            if fid not in known_ids:
                warnings.append(f"lane {v['author']}: stale verdict on {fid!r} "
                                "(finding no longer exists) — excluded")
                continue
            verdicts_on.setdefault(fid, {})[v["author"]] = {
                "disposition": verdict.get("disposition"),
                "note": verdict.get("note", ""),
                "role": v["role"] if v["role"] in roles else None,
            }

    out = []
    for fid, owner_list in owners.items():
        collided = len(owner_list) > 1
        if collided:
            warnings.append(f"id-collision: finding {fid!r} authored by "
                            f"{sorted(v['author'] for v, _ in owner_list)}")
        for view, f in owner_list:
            author_role = view["role"] if view["role"] in roles else None
            all_verdicts = dict(verdicts_on.get(fid, {}))
            # Self-verdicts stay VISIBLE in output but are ignored in computation (§5).
            others = {a: v for a, v in all_verdicts.items() if a != view["author"]}
            reviewing = [r for r in roles.values() if author_role in r.get("reviews", [])]
            if collided:
                review_state = "suspended"
            elif any(v["disposition"] in ("refuted", "partial")
                     for v in others.values()):
                review_state = "disagreement"
            else:
                unreviewed = uncovered = False
                for r in reviewing:
                    holders = role_holders.get(r["id"], [])
                    if not holders:
                        uncovered = True
                    elif not any(a in others and others[a]["role"] == r["id"]
                                 for a in (h["author"] for h in holders)):
                        unreviewed = True
                review_state = ("unreviewed" if unreviewed
                                else "uncovered" if uncovered else "agreed")
            out.append({"id": fid, "title": f.get("title", ""),
                        "severity": f.get("severity", "note"),
                        "claim": f.get("claim", ""), "author": view["author"],
                        "refs": [r for r in f.get("refs", [])],
                        "verdicts": all_verdicts, "review_state": review_state})
    _warn_unknown_refs(map_data, out, warnings)
    return out


def _warn_unknown_refs(map_data: dict, findings: list[dict], warnings: list[str]) -> None:
    known = {n["id"] for n in map_data.get("nodes", [])}
    for f in findings:
        unknown = [r for r in f["refs"] if r not in known]
        if unknown:
            warnings.append(f"finding {f['id']!r}: refs {unknown} are not map nodes — ignored")
        f["refs"] = [r for r in f["refs"] if r in known]


def _human_queue(live): return []
def _invariants(map_data, live, warnings): return []
def _cycle(map_data, live, warnings):
    cyc = map_data.get("cycle", {}) or {}
    return {"phases": cyc.get("phases", []),
            "roles": [{"id": r["id"], "harness": r.get("harness", ""),
                       "reviews": r.get("reviews", [])}
                      for r in cyc.get("roles", [])]}
