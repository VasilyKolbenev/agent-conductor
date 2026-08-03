"""The merge engine — pure functions implementing spec §5 exactly.

Every computed value is derived; no author can write a disagreement, a stale
flag, or a queue de-dup. Silence is never consent.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from conductor import schema
from conductor.schema import DEFAULT_STALENESS_MINUTES

EVENTS_TAIL = 500
BLOCKING_NODE_STATUSES = frozenset({"fail", "blocked"})


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
            "now": data.get("now") or {}, "_data": data, "_dt": dt, "_future": future}


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
    state = {
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
    # Derived from the finished state (both read `pending_verdicts`, which
    # takes a whole state dict); next_action reads project_status, so order
    # matters here.
    state["project_status"] = _project_status(state, map_error)
    state["next_action"] = _next_action(state, map_error)
    return state


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
                        "claim": f.get("claim", ""),
                        "detail": f.get("detail", ""),
                        "evidence": f.get("evidence", ""),
                        "author": view["author"],
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


def pending_verdicts(state: dict) -> dict[str, list[str]]:
    """Finding ids each reviewing role still owes a verdict on (for conduct prompt).

    Mirrors `_review_state`'s §6 self-verdict rule: an author's own verdict on
    their own finding never counts toward satisfying a reviewing role's
    obligation, even when a role reviews itself (schema-legal). Suspended
    (id-collided) findings are skipped entirely — there is nothing to owe a
    verdict on until the collision is resolved.

    Args:
        state: A `state.json` dict as produced by `merge()`.

    Returns:
        Mapping of role id to the sorted finding ids that role still owes a
        verdict on. Roles with zero pending findings are OMITTED from the
        result — callers must use `.get(role_id, [])`, not `[role_id]`.
    """
    roles = {r["id"]: r for r in state["cycle"]["roles"]}
    # lane roles are raw (schema-validated, not cross-checked against
    # cycle.roles here) — equivalent to _findings' known_role because a
    # role's `reviews` entries are themselves guaranteed-declared role ids.
    author_role = {ln["author"]: ln["role"] for ln in state["lanes"]}
    pending: dict[str, list[str]] = {rid: [] for rid in roles}
    for f in state["findings"]:
        if f["review_state"] == "suspended":
            continue
        for rid, role in roles.items():
            if author_role.get(f["author"]) not in role.get("reviews", []):
                continue
            if not any(v.get("role") == rid for a, v in f["verdicts"].items()
                       if a != f["author"]):
                pending[rid].append(f["id"])
    return {rid: sorted(ids) for rid, ids in pending.items() if ids}


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
        # Exact-`updated` ties break on phase-string order (tuple-sort artifact).
        # Accepted as-is: deterministic, unspecified by §6, pathological in practice.
        declaring.sort()
        out["current_phase"] = declaring[-1][1]
    return out


# PROTOCOL.md §6.1: project_status / next_action — is the project ready,
# active, blocked or complete, and what happens next.
def _project_status(state: dict, map_error: str | None) -> dict:
    """Classify the project, first match wins on a strict precedence.

    Order: unknown > human decision > broken lane > broken invariant >
    failing node > complete > active > ready. `complete` is the only state
    that may read as success, so its conditions are deliberately strict — a
    stale lane, an open finding or an unmet review obligation all keep the
    project out of it. Disagreements and stale lanes do NOT force `blocked`:
    `blocked` means a person must act before work can continue, and `active`
    is not a success claim. `detail` states the fact only; imperatives belong
    to `next_action`.

    Args:
        state: The `state.json` dict, complete except for these two keys.
        map_error: The map's load/validation error, or None.

    Returns:
        `{"state", "reason", "detail"}` per PROTOCOL.md §6.1.
    """
    if map_error is not None:
        return {"state": "unknown", "reason": "map_unreadable",
                "detail": "map.toml is unreadable"}
    blocked = _blocked_status(state)
    if blocked is not None:
        return blocked
    nodes = state["map"]["nodes"]
    detail = (f"{sum(1 for n in nodes if n['status'] == 'pass')} of "
              f"{len(nodes)} nodes passing")
    if _is_complete(state):
        return {"state": "complete", "reason": "all_clear", "detail": detail}
    if any(not ln["broken"] for ln in state["lanes"]):
        return {"state": "active", "reason": "work_in_progress", "detail": detail}
    return {"state": "ready", "reason": "no_lanes_yet",
            "detail": "no lanes have reported yet"}


def _blocked_status(state: dict) -> dict | None:
    """The four `blocked` rows of the §6.1 precedence table, in order."""
    queue = state["human_queue"]
    if queue:
        plural = "" if len(queue) == 1 else "s"
        return _blocked("human_decision", f"{len(queue)} decision{plural} waiting on you")
    broken = _broken_lanes(state)
    if broken:
        return _blocked("broken_lane", f"lane {broken[0]} is unreadable" if len(broken) == 1
                        else f"{len(broken)} lanes are unreadable")
    bad = _broken_invariants(state)
    if bad:
        return _blocked("invariant_broken", f"invariant {bad[0]} is broken" if len(bad) == 1
                        else f"{len(bad)} invariants are broken")
    failing = _failing_nodes(state)
    if failing:
        return _blocked("node_failing", f"{len(failing)} of {len(state['map']['nodes'])} "
                                        "nodes failing or blocked")
    return None


def _blocked(reason: str, detail: str) -> dict:
    return {"state": "blocked", "reason": reason, "detail": detail}


def _is_complete(state: dict) -> bool:
    """Every §6.1 `complete` condition — the owner's no-silent-success law."""
    nodes = state["map"]["nodes"]
    return (bool(nodes) and all(n["status"] == "pass" for n in nodes)
            and not state["findings"] and not state["human_queue"]
            and not pending_verdicts(state)
            and not any(ln["broken"] or ln["stale"] for ln in state["lanes"]))


# Ties inside one kind always break on sorted id, so two merges over identical
# inputs emit identical bytes (server.Broker's change detection depends on it).
def _broken_lanes(state: dict) -> list[str]:
    return sorted(ln["author"] for ln in state["lanes"] if ln["broken"])


def _broken_invariants(state: dict) -> list[str]:
    return sorted(i["id"] for i in state["invariants"] if not i["ok"])


def _failing_nodes(state: dict) -> list[dict]:
    return sorted((n for n in state["map"]["nodes"]
                   if n["status"] in BLOCKING_NODE_STATUSES), key=lambda n: n["id"])


def _next_action(state: dict, map_error: str | None) -> dict | None:
    """Pick the single most important next action, by §6.1 precedence.

    Rows 1-5 mirror `_project_status`; the rest are fallbacks (unmet review
    obligation, disagreement, stale lane, nothing started yet). A `complete`
    project matches no row and so gets None — as does an `active` project
    with nothing outstanding, where the next move belongs to the agents.

    Args:
        state: The `state.json` dict, with `project_status` already set.
        map_error: The map's load/validation error, or None.

    Returns:
        `{"text", "kind", "ref"}` per PROTOCOL.md §6.1, or None.
    """
    if map_error is not None:
        return _action("fix_map", None,
                       "Fix conductor/map.toml — the project map cannot be read.")
    queue = sorted(state["human_queue"], key=lambda w: w["id"])
    if queue:
        w = queue[0]
        # kind/title are schema-guaranteed; fall back for hand-built lanes.
        return _action("answer_wait", w["id"],
                       f"Answer the {w['kind'] or 'decision'}: {w['title'] or w['id']}")
    broken = _broken_lanes(state)
    if broken:
        return _action("fix_lane", broken[0],
                       f"Fix conductor/lanes/{broken[0]}.json — the lane cannot be read.")
    bad = _broken_invariants(state)
    if bad:
        return _action("fix_invariant", bad[0], f"Restore the broken invariant {bad[0]}.")
    failing = _failing_nodes(state)
    if failing:
        return _action("fix_node", failing[0]["id"],
                       f"Fix node {failing[0]['id']} — status is {failing[0]['status']}.")
    return _review_action(state)


def _review_action(state: dict) -> dict | None:
    """§6.1 fallbacks: review debt, disagreement, id collision, stale lane, start."""
    # (finding, role) pairs sorted so a tie between two owing roles is stable.
    owed = sorted((fid, rid) for rid, fids in pending_verdicts(state).items() for fid in fids)
    if owed:
        fid, rid = owed[0]
        return _action("review_finding", fid, f"Get a verdict from {rid} on finding {fid}.")
    disputed = sorted(f["id"] for f in state["disagreements"])
    if disputed:
        return _action("resolve_disagreement", disputed[0],
                       f"Resolve the disagreement on finding {disputed[0]}.")
    # A collision suspends review entirely, so it surfaces here rather than as a
    # blocker: a person must rename one of the ids before the finding can move.
    collided = Counter(f["id"] for f in state["findings"]
                       if f["review_state"] == "suspended")
    if collided:
        fid = min(collided)
        return _action("resolve_collision", fid,
                       f"Resolve the duplicate finding id {fid} — "
                       f"{collided[fid]} lanes claim it.")
    stale = sorted(ln["author"] for ln in state["lanes"] if ln["stale"])
    if stale:
        return _action("check_stale_lane", stale[0],
                       f"Check lane {stale[0]} — it has not reported recently.")
    if state["project_status"]["state"] == "ready":
        roles = state["cycle"]["roles"]
        rid = roles[0]["id"] if roles else None      # first DECLARED role, not sorted
        return _action("start_work", rid,
                       f"Vend a prompt for role {rid} to start work." if rid
                       else "Vend a prompt to start work.")
    return None


def _action(kind: str, ref: str | None, text: str) -> dict:
    return {"text": text, "kind": kind, "ref": ref}
