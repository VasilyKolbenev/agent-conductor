from datetime import datetime, timezone
from conductor import merge
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

MAP = {"schema_version": 1, "project": "p",
       "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
       "cycle": {"phases": ["plan", "implement", "review"], "roles": []},
       "invariants": [{"id": "inv-1", "text": "main untouched"}]}

def lane(author, updated="2026-07-30T11:00:00+00:00", **over):
    data = {"schema_version": 1, "author": author, "updated": updated}
    data.update(over)
    return {"author": author, "data": data, "error": None}

WAIT = {"id": "w-1", "kind": "decision", "title": "Bundle model?",
        "why": "size", "blocks": ["D-2"]}


def test_queue_dedupes_by_id_and_lists_all_sources():
    ls = [lane("a", waits_on_human=[WAIT]), lane("b", waits_on_human=[dict(WAIT)])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert len(state["human_queue"]) == 1
    assert sorted(state["human_queue"][0]["sources"]) == ["a", "b"]
    assert state["kpi"]["queue"] == 1

def test_invariant_broken_by_one_lane_is_broken_globally():
    ls = [lane("a", invariants=[{"id": "inv-1", "ok": True}]),
          lane("b", invariants=[{"id": "inv-1", "ok": False}])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    inv = state["invariants"][0]
    assert inv["ok"] is False and inv["broken_by"] == ["b"]

def test_unknown_invariant_id_ignored_with_warning():
    ls = [lane("a", invariants=[{"id": "ghost", "ok": False}])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert all(i["id"] != "ghost" for i in state["invariants"])
    assert any("ghost" in w for w in state["warnings"])

def test_current_phase_from_most_recent_declaring_lane():
    ls = [lane("a", updated="2026-07-30T10:00:00+00:00",
               now={"task": "x", "phase": "plan"}),
          lane("b", updated="2026-07-30T11:00:00+00:00",
               now={"task": "y", "phase": "review"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["cycle"]["current_phase"] == "review"

def test_stale_lane_does_not_set_current_phase():
    ls = [lane("a", updated="2026-07-30T01:00:00+00:00",   # stale
               now={"task": "x", "phase": "review"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert "current_phase" not in state["cycle"]

def test_unknown_phase_is_undeclared_plus_warning():
    ls = [lane("a", now={"task": "x", "phase": "shipping"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert "current_phase" not in state["cycle"]
    assert any("shipping" in w for w in state["warnings"])

def test_future_dated_lane_does_not_set_current_phase():
    ls = [lane("a", updated="2026-07-30T10:00:00+00:00",
               now={"task": "x", "phase": "plan"}),
          lane("b", updated="2026-07-30T13:00:00+00:00",   # future vs NOW
               now={"task": "y", "phase": "review"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["cycle"]["current_phase"] == "plan"       # future lane excluded


# --- cycle.roles[].stage: projected for presentation, read by no merge rule ---

ROLES_MAP = {**MAP, "cycle": {"phases": ["plan", "implement", "review"], "roles": [
    {"id": "impl", "harness": "cc", "reviews": []},
    {"id": "rev", "harness": "cx", "reviews": ["impl"]},
    {"id": "sec", "harness": "cx", "reviews": ["impl"]}]}}
STAGES = {"impl": "implement", "rev": "review", "sec": "review"}
FINDING = {"id": "D-1", "title": "t", "severity": "blocker", "claim": "defect",
           "detail": "d", "evidence": "e", "refs": ["n"]}


def staged(map_data):
    """The same map with every role assigned to a stage."""
    cyc = map_data["cycle"]
    return {**map_data, "cycle": {**cyc, "roles": [{**r, "stage": STAGES[r["id"]]}
                                                   for r in cyc["roles"]]}}


def rich_lanes():
    """Three roles, a disagreement, a queued wait, a stale lane, a contested node."""
    return [lane("claude", role="impl", map_status={"n": "pass"}, findings=[dict(FINDING)],
                 waits_on_human=[dict(WAIT)], now={"task": "x", "phase": "implement"}),
            lane("codex", role="rev",
                 verdicts={"D-1": {"disposition": "refuted", "note": "no"}}),
            lane("scan", role="sec",
                 verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
            lane("ghost", updated="2026-07-29T00:00:00+00:00",   # stale
                 role="impl", map_status={"n": "running"})]


def without_stage(state):
    """`state` with every role's `stage` dropped and `generated_at` neutralised."""
    roles = [{k: v for k, v in r.items() if k != "stage"} for r in state["cycle"]["roles"]]
    return {**state, "generated_at": "<fixed>",
            "cycle": {**state["cycle"], "roles": roles}}


def test_state_projects_role_stage():
    state = merge.merge(staged(ROLES_MAP), None, [], [], 0, NOW)
    assert state["cycle"]["roles"] == [
        {"id": "impl", "harness": "cc", "reviews": [], "stage": "implement"},
        {"id": "rev", "harness": "cx", "reviews": ["impl"], "stage": "review"},
        {"id": "sec", "harness": "cx", "reviews": ["impl"], "stage": "review"}]

def test_legacy_project_without_stage_is_unchanged():
    # Exact equality: a role with no stage must not gain a `"stage": None`,
    # which would change every existing consumer's view of the role shape.
    state = merge.merge(ROLES_MAP, None, [], [], 0, NOW)
    assert state["cycle"]["roles"] == [
        {"id": "impl", "harness": "cc", "reviews": []},
        {"id": "rev", "harness": "cx", "reviews": ["impl"]},
        {"id": "sec", "harness": "cx", "reviews": ["impl"]}]

def test_the_additivity_fixture_has_something_to_protect():
    # The equality below is only as strong as the state it compares; pin the
    # fixture so a later edit cannot quietly reduce it to an empty project.
    state = merge.merge(ROLES_MAP, None, rich_lanes(), [], 0, NOW)
    assert state["kpi"]["disagreements"] == 1 and state["kpi"]["queue"] == 1
    assert state["kpi"]["stale_lanes"] == 1
    assert state["map"]["nodes"][0]["status"] == "contested"

def test_stage_changes_nothing_but_the_role_projection():
    plain = merge.merge(ROLES_MAP, None, rich_lanes(), [], 0, NOW)
    with_stage = merge.merge(staged(ROLES_MAP), None, rich_lanes(), [], 0, NOW)
    assert [r["stage"] for r in with_stage["cycle"]["roles"]] == [
        "implement", "review", "review"]                  # the stages are really there
    assert without_stage(with_stage) == without_stage(plain)

def test_stage_changes_no_merge_computed_value():
    # The equality above would catch all of these; naming them says which
    # promises DO-1b is making, so a regression reads as a broken promise.
    plain = merge.merge(ROLES_MAP, None, rich_lanes(), [], 0, NOW)
    with_stage = merge.merge(staged(ROLES_MAP), None, rich_lanes(), [], 0, NOW)
    assert ([f["review_state"] for f in with_stage["findings"]]
            == [f["review_state"] for f in plain["findings"]] == ["disagreement"])
    assert with_stage["project_status"] == plain["project_status"]
    assert with_stage["next_action"] == plain["next_action"]
    assert with_stage["human_queue"] == plain["human_queue"]
    assert with_stage["invariants"] == plain["invariants"]
    assert with_stage["kpi"] == plain["kpi"]
    assert ([r["id"] for r in with_stage["cycle"]["roles"]]
            == [r["id"] for r in plain["cycle"]["roles"]] == ["impl", "rev", "sec"])


# --- the same equality across the `complete` branch, which rich_lanes never reaches ---
# rich_lanes queues a wait, so row 2 of the status ladder answers before
# `_is_complete` is ever evaluated: a completeness rule that read `stage` would
# survive the pair above untouched. These two fixtures walk the whole blocked
# ladder and then answer `_is_complete` differently — one True, one False — so
# a `stage`-dependent verdict has to move one of them.

def clear_lanes():
    """All-clear: every node passing, nothing open, no queue, no stale lane."""
    return [lane("claude", role="impl", map_status={"n": "pass"},
                 now={"task": "x", "phase": "review"}),
            lane("codex", role="rev", map_status={"n": "pass"}),
            lane("scan", role="sec", map_status={"n": "pass"})]


def open_finding_lanes():
    """Past the whole blocked ladder, but one open finding refuses `complete`."""
    verdict = {"D-1": {"disposition": "confirmed", "note": ""}}
    return [lane("claude", role="impl", map_status={"n": "pass"}, findings=[dict(FINDING)]),
            lane("codex", role="rev", map_status={"n": "pass"}, verdicts=dict(verdict)),
            lane("scan", role="sec", map_status={"n": "pass"}, verdicts=dict(verdict))]


def test_the_complete_branch_fixtures_reach_it_from_both_sides():
    clear = merge.merge(ROLES_MAP, None, clear_lanes(), [], 0, NOW)
    assert clear["project_status"]["state"] == "complete"
    assert clear["next_action"] is None
    unfinished = merge.merge(ROLES_MAP, None, open_finding_lanes(), [], 0, NOW)
    assert unfinished["project_status"]["state"] == "active"
    assert merge.pending_verdicts(unfinished) == {}    # only the open finding refuses

def test_stage_changes_nothing_on_a_complete_project():
    plain = merge.merge(ROLES_MAP, None, clear_lanes(), [], 0, NOW)
    with_stage = merge.merge(staged(ROLES_MAP), None, clear_lanes(), [], 0, NOW)
    assert without_stage(with_stage) == without_stage(plain)

def test_stage_cannot_declare_an_unfinished_project_complete():
    plain = merge.merge(ROLES_MAP, None, open_finding_lanes(), [], 0, NOW)
    with_stage = merge.merge(staged(ROLES_MAP), None, open_finding_lanes(), [], 0, NOW)
    assert without_stage(with_stage) == without_stage(plain)


# --- and on `ready`, the last branch where a stage could change the answer ---
# `_start_work_action` is the only fallback row that reads cycle.roles at all,
# so it is the one door left open: a pick that preferred a staged role would
# start `rev` here while the unstaged map still starts `impl`. The first
# DECLARED role is left unstaged on purpose to make that divergence visible —
# an all-staged fixture would pick `impl` either way and prove nothing.
#
# The coverage boundary stops there deliberately. `unknown` cannot host the
# dependence: merge() substitutes an empty cycle for an unreadable map, so no
# role survives to carry a stage. The broken-lane, invariant and failing-node
# rows read lanes, invariants and nodes — none of which carry `stage`, because
# it is projected into cycle.roles only and never copied into a lane.

def half_staged(map_data):
    """Stages every role but the first declared one, which stays bare."""
    cyc = map_data["cycle"]
    return {**map_data, "cycle": {**cyc, "roles": [
        r if r["id"] == "impl" else {**r, "stage": STAGES[r["id"]]}
        for r in cyc["roles"]]}}


def test_the_ready_fixture_reaches_start_work():
    state = merge.merge(half_staged(ROLES_MAP), None, [], [], 0, NOW)
    assert state["project_status"]["state"] == "ready"
    assert state["next_action"]["kind"] == "start_work"
    assert [("stage" in r) for r in state["cycle"]["roles"]] == [False, True, True]

def test_stage_does_not_choose_which_role_starts_work():
    plain = merge.merge(ROLES_MAP, None, [], [], 0, NOW)
    with_stage = merge.merge(half_staged(ROLES_MAP), None, [], [], 0, NOW)
    assert without_stage(with_stage) == without_stage(plain)
