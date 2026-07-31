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

# PROTOCOL.md §6: Disagreement, Unreviewed, Uncovered, Review state, Unknown
# referenced ids, Unknown role, Id collision.
def _findings(map_data: dict, views: list[dict], warnings: list[str]) -> list[dict]:
    live = [v for v in views if not v["broken"]]
    roles = {r["id"]: r for r in (map_data.get("cycle", {}) or {}).get("roles", [])}

    known_role: dict[str, str | None] = {}
    for v in live:
        role = v["role"]
        if role is not None and role not in roles:
            warnings.append(f"lane {v['author']}: role {role!r} is not in cycle.roles — "
                            "treated as observer")
        known_role[v["author"]] = role if role in roles else None

    role_holders: dict[str, list] = {}
    for v in live:
        holder_role = known_role[v["author"]]
        if holder_role:
            role_holders.setdefault(holder_role, []).append(v)

    owners, verdicts_on = _index_findings_and_verdicts(live, known_role, warnings)

    out = []
    for fid, owner_list in owners.items():
        collided = len(owner_list) > 1
        if collided:
            warnings.append(f"id-collision: finding {fid!r} authored by "
                            f"{sorted(view['author'] for view, _ in owner_list)}")
        for view, f in owner_list:
            author_role = known_role[view["author"]]
            all_verdicts = dict(verdicts_on.get(fid, {}))
            # Self-verdicts stay VISIBLE in output but are ignored in computation (§5).
            others = {a: vd for a, vd in all_verdicts.items() if a != view["author"]}
            reviewing = [r for r in roles.values() if author_role in r.get("reviews", [])]
            review_state = _review_state(collided, others, reviewing, role_holders)
            out.append({"id": fid, "title": f.get("title", ""),
                        "severity": f.get("severity", "note"),
                        "claim": f.get("claim", ""), "author": view["author"],
                        "refs": [r for r in f.get("refs", [])],
                        "verdicts": all_verdicts, "review_state": review_state})
    _warn_unknown_refs(map_data, out, warnings)
    return out


def _index_findings_and_verdicts(live: list[dict], known_role: dict[str, str | None],
                                  warnings: list[str]) -> tuple[dict, dict]:
    """Owners map + verdicts_on collection (§6 Id collision / stale verdicts)."""
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
                "role": known_role[v["author"]],
            }
    return owners, verdicts_on


def _review_state(collided: bool, others: dict[str, dict], reviewing: list[dict],
                   role_holders: dict[str, list]) -> str:
    """§6 Review state precedence: suspended > disagreement > unreviewed > uncovered > agreed."""
    if collided:
        return "suspended"
    if any(vd["disposition"] in ("refuted", "partial") for vd in others.values()):
        return "disagreement"
    unreviewed = uncovered = False
    for r in reviewing:
        holders = role_holders.get(r["id"], [])
        if not holders:
            uncovered = True
        elif not any(a in others and others[a]["role"] == r["id"]
                     for a in (h["author"] for h in holders)):
            unreviewed = True
    return "unreviewed" if unreviewed else "uncovered" if uncovered else "agreed"


def _warn_unknown_refs(map_data: dict, findings: list[dict], warnings: list[str]) -> None:
    known = {n["id"] for n in map_data.get("nodes", [])}
    for f in findings:
        unknown = [r for r in f["refs"] if r not in known]
        if unknown:
            warnings.append(f"finding {f['id']!r}: refs {unknown} are not map nodes — ignored")
        f["refs"] = [r for r in f["refs"] if r in known]


# PROTOCOL.md §6: Human queue — union of waits_on_human across lanes, keyed by id.
def _human_queue(live: list[dict]) -> list[dict]:
    queue: dict[str, dict] = {}
    for v in live:
        for w in v["_data"].get("waits_on_human", []):
            item = queue.setdefault(w["id"], {
                "id": w["id"], "kind": w.get("kind"), "title": w.get("title", ""),
                "why": w.get("why", ""), "blocks": list(w.get("blocks", [])),
                "sources": []})
            item["sources"].append(v["author"])
    return list(queue.values())


# PROTOCOL.md §6: Invariant state — ok only if every lane mentioning it says ok.
def _invariants(map_data: dict, live: list[dict], warnings: list[str]) -> list[dict]:
    declared = {i["id"]: i for i in map_data.get("invariants", [])}
    state = {iid: {"id": iid, "ok": True, "broken_by": []} for iid in declared}
    for v in live:
        for inv in v["_data"].get("invariants", []):
            iid = inv.get("id")
            if iid not in declared:
                warnings.append(f"lane {v['author']}: invariant {iid!r} is not declared "
                                "in the map — ignored")
                continue
            if inv.get("ok") is False:
                state[iid]["ok"] = False
                state[iid]["broken_by"].append(v["author"])
    return list(state.values())


# PROTOCOL.md §6: Current phase — most recently updated non-stale, non-future lane.
def _cycle(map_data: dict, live: list[dict], warnings: list[str]) -> dict:
    cyc = map_data.get("cycle", {}) or {}
    phases = cyc.get("phases", [])
    out = {"phases": phases,
           "roles": [{"id": r["id"], "harness": r.get("harness", ""),
                      "reviews": r.get("reviews", [])}
                     for r in cyc.get("roles", [])]}
    declaring = []
    for v in live:
        phase = (v["now"] or {}).get("phase")
        if phase is None or v["stale"] or v["_future"] or v["_dt"] is None:
            continue
        if phase not in phases:
            warnings.append(f"lane {v['author']}: now.phase {phase!r} is not a "
                            "cycle phase — treated as undeclared")
            continue
        declaring.append((v["_dt"], phase))
    if declaring:
        declaring.sort()
        out["current_phase"] = declaring[-1][1]
    return out
