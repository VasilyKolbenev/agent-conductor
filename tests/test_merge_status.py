"""Tests for `project_status` / `next_action` — the first-screen summary (§6.1).

The precedence table is normative and ordered: every row is pinned here, and
so is the ordering between adjacent rows. `complete` is the only state that
may read as success, so each of its conditions gets its own refusal test.
"""
from datetime import datetime, timezone

from conductor import merge
from tests.test_merge_review import MAP, finding, lane

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
STALE_UPDATED = "2026-07-29T00:00:00+00:00"        # > 360 min before NOW

INVARIANT_MAP = {**MAP, "invariants": [{"id": "i-1", "text": "x"},
                                       {"id": "i-2", "text": "y"}]}
TWO_NODE_MAP = {**MAP, "nodes": [{"id": "beta", "label": "b", "kind": "artifact"},
                                 {"id": "alpha", "label": "a", "kind": "artifact"}]}


def with_data(entry, **extra):
    """A lane from `lane()` carrying extra lane-file fields."""
    entry["data"].update(extra)
    return entry


def broken_lane(author="junk"):
    return {"author": author, "data": None, "error": "unreadable"}


def wait(wid="w-1", kind="decision", title="Ship it or hold?"):
    return {"id": wid, "kind": kind, "title": title, "why": "", "blocks": []}


def passing(author="claude", role="impl", **extra):
    """A live lane voting MAP's single node `n` to pass."""
    return with_data(lane(author, role, **extra), map_status={"n": "pass"})


def status(state):
    return state["project_status"]


# --- precedence table, row by row, plus the ordering between rows ---

def test_unreadable_map_is_unknown():
    state = merge.merge(None, "map.toml: bad toml", [], [], 0, NOW)
    assert status(state) == {"state": "unknown", "reason": "map_unreadable",
                             "detail": "map.toml is unreadable"}

def test_unreadable_map_wins_over_every_other_signal():
    ls = [with_data(lane("claude", "impl", [finding()]), waits_on_human=[wait()]),
          broken_lane()]
    state = merge.merge(None, "boom", ls, [], 0, NOW)
    assert state["human_queue"] and state["kpi"]["broken_lanes"] == 1   # both present
    assert status(state)["state"] == "unknown"
    assert status(state)["reason"] == "map_unreadable"

def test_human_queue_is_blocked_on_a_human_decision():
    state = merge.merge(MAP, None, [with_data(passing(), waits_on_human=[wait()])],
                        [], 0, NOW)
    assert status(state) == {"state": "blocked", "reason": "human_decision",
                             "detail": "1 decision waiting on you"}

def test_human_queue_beats_a_broken_lane():
    ls = [with_data(passing(), waits_on_human=[wait()]), broken_lane()]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert status(state)["reason"] == "human_decision"

def test_broken_lane_is_blocked():
    state = merge.merge(MAP, None, [passing(), broken_lane()], [], 0, NOW)
    assert status(state) == {"state": "blocked", "reason": "broken_lane",
                             "detail": "lane junk is unreadable"}

def test_broken_lane_beats_a_broken_invariant():
    ls = [with_data(passing(), invariants=[{"id": "i-1", "ok": False}]), broken_lane()]
    state = merge.merge(INVARIANT_MAP, None, ls, [], 0, NOW)
    assert status(state)["reason"] == "broken_lane"

def test_broken_invariant_is_blocked():
    ls = [with_data(passing(), invariants=[{"id": "i-1", "ok": False}])]
    state = merge.merge(INVARIANT_MAP, None, ls, [], 0, NOW)
    assert status(state)["state"] == "blocked"
    assert status(state)["reason"] == "invariant_broken"
    assert "i-1" in status(state)["detail"]

def test_broken_invariant_beats_a_failing_node():
    ls = [with_data(lane("claude", "impl"), map_status={"n": "fail"},
                    invariants=[{"id": "i-1", "ok": False}])]
    state = merge.merge(INVARIANT_MAP, None, ls, [], 0, NOW)
    assert status(state)["reason"] == "invariant_broken"

def test_failing_node_is_blocked():
    state = merge.merge(MAP, None, [with_data(lane("claude", "impl"),
                                              map_status={"n": "fail"})], [], 0, NOW)
    assert status(state) == {"state": "blocked", "reason": "node_failing",
                             "detail": "1 of 1 nodes failing or blocked"}

def test_blocked_node_is_blocked_too():
    state = merge.merge(MAP, None, [with_data(lane("claude", "impl"),
                                              map_status={"n": "blocked"})], [], 0, NOW)
    assert status(state)["reason"] == "node_failing"

def test_all_clear_project_is_complete():
    state = merge.merge(MAP, None, [passing()], [], 0, NOW)
    assert status(state) == {"state": "complete", "reason": "all_clear",
                             "detail": "1 of 1 nodes passing"}

def test_live_lane_that_has_not_finished_is_active():
    state = merge.merge(MAP, None, [lane("claude", "impl")], [], 0, NOW)
    assert status(state) == {"state": "active", "reason": "work_in_progress",
                             "detail": "0 of 1 nodes passing"}

def test_no_lanes_is_ready():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    assert status(state) == {"state": "ready", "reason": "no_lanes_yet",
                             "detail": "no lanes have reported yet"}


# --- complete is refused when any single one of its conditions fails ---

def test_complete_refused_when_a_finding_is_open():
    ls = [passing("claude", "impl", findings=[finding()]),
          passing("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          passing("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {}        # every obligation met...
    assert status(state)["state"] == "active"         # ...the open finding still refuses

def test_complete_refused_when_a_node_is_not_passing():
    state = merge.merge(MAP, None, [lane("claude", "impl")], [], 0, NOW)
    assert state["map"]["nodes"][0]["status"] == "idle"   # neither passing nor failing
    assert status(state)["state"] == "active"

def test_complete_refused_when_a_review_obligation_is_unmet():
    ls = [passing("claude", "impl", findings=[finding()])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {"rev": ["D-1"], "sec": ["D-1"]}
    assert status(state)["state"] == "active"

def test_complete_refused_when_a_wait_is_queued():
    state = merge.merge(MAP, None, [with_data(passing(), waits_on_human=[wait()])],
                        [], 0, NOW)
    assert status(state)["state"] == "blocked"        # never complete

def test_complete_refused_when_a_lane_is_stale():
    state = merge.merge(MAP, None, [passing(updated=STALE_UPDATED)], [], 0, NOW)
    assert state["kpi"]["stale_lanes"] == 1
    assert status(state)["state"] == "active"         # stale never reads as success

def test_complete_refused_when_a_lane_is_broken():
    state = merge.merge(MAP, None, [passing(), broken_lane()], [], 0, NOW)
    assert status(state)["state"] == "blocked"

def test_complete_refused_when_no_nodes_are_declared():
    state = merge.merge({**MAP, "nodes": []}, None, [lane("claude", "impl")], [], 0, NOW)
    assert status(state) == {"state": "active", "reason": "work_in_progress",
                             "detail": "0 of 0 nodes passing"}


# --- next_action, one test per kind ---

def test_next_action_fix_map_names_the_file():
    action = merge.merge(None, "boom", [], [], 0, NOW)["next_action"]
    assert action["kind"] == "fix_map" and action["ref"] is None
    assert "map.toml" in action["text"]

def test_next_action_answer_wait_names_the_title():
    ls = [with_data(passing(), waits_on_human=[wait(title="Bake config or provision it?")])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["next_action"] == {
        "text": "Answer the decision: Bake config or provision it?",
        "kind": "answer_wait", "ref": "w-1"}

def test_next_action_picks_the_lowest_wait_id():
    ls = [with_data(passing(), waits_on_human=[wait("w-9"), wait("w-2")])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["next_action"]["ref"] == "w-2"

def test_next_action_fix_lane_names_the_lane_path():
    action = merge.merge(MAP, None, [passing(), broken_lane()], [], 0, NOW)["next_action"]
    assert action["kind"] == "fix_lane" and action["ref"] == "junk"
    assert "conductor/lanes/junk.json" in action["text"]

def test_next_action_picks_the_lowest_broken_lane_author():
    ls = [passing(), broken_lane("zeta"), broken_lane("alpha")]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["next_action"]["ref"] == "alpha"
    assert status(state)["detail"] == "2 lanes are unreadable"

def test_next_action_fix_invariant_names_the_invariant():
    ls = [with_data(passing(), invariants=[{"id": "i-2", "ok": False}])]
    action = merge.merge(INVARIANT_MAP, None, ls, [], 0, NOW)["next_action"]
    assert action["kind"] == "fix_invariant" and action["ref"] == "i-2"
    assert "i-2" in action["text"]

def test_next_action_fix_node_names_the_lowest_failing_node():
    ls = [with_data(lane("claude", "impl"), map_status={"beta": "fail", "alpha": "blocked"})]
    state = merge.merge(TWO_NODE_MAP, None, ls, [], 0, NOW)
    assert state["next_action"]["kind"] == "fix_node"
    assert state["next_action"]["ref"] == "alpha"     # sorted by id, not map order
    assert "alpha" in state["next_action"]["text"]
    assert status(state)["detail"] == "2 of 2 nodes failing or blocked"

def test_next_action_review_finding_names_the_finding_and_the_owing_role():
    state = merge.merge(MAP, None, [passing("claude", "impl", findings=[finding()])],
                        [], 0, NOW)
    action = state["next_action"]
    assert action["kind"] == "review_finding" and action["ref"] == "D-1"
    assert "D-1" in action["text"] and "rev" in action["text"]   # lowest role owing

def test_next_action_resolve_disagreement_once_every_verdict_is_in():
    ls = [passing("claude", "impl", findings=[finding()]),
          passing("codex", "rev", verdicts={"D-1": {"disposition": "refuted", "note": "no"}}),
          passing("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {}       # nothing owed; the dispute remains
    action = state["next_action"]
    assert action["kind"] == "resolve_disagreement" and action["ref"] == "D-1"
    assert "D-1" in action["text"]

def test_next_action_check_stale_lane_names_the_author():
    state = merge.merge(MAP, None, [passing(updated=STALE_UPDATED)], [], 0, NOW)
    action = state["next_action"]
    assert action["kind"] == "check_stale_lane" and action["ref"] == "claude"
    assert "claude" in action["text"]

def test_next_action_start_work_names_the_first_declared_role():
    action = merge.merge(MAP, None, [], [], 0, NOW)["next_action"]
    assert action["kind"] == "start_work" and action["ref"] == "impl"
    assert "impl" in action["text"]

def test_next_action_start_work_without_roles_has_no_ref():
    m = {**MAP, "cycle": {"phases": [], "roles": []}}
    action = merge.merge(m, None, [], [], 0, NOW)["next_action"]
    assert action["kind"] == "start_work" and action["ref"] is None

def test_next_action_is_null_when_the_project_is_complete():
    state = merge.merge(MAP, None, [passing()], [], 0, NOW)
    assert status(state)["state"] == "complete"
    assert state["next_action"] is None


# --- determinism: server.Broker's change detection depends on it ---

def test_status_and_action_are_identical_across_two_merges():
    ls = [with_data(passing("claude", "impl", findings=[finding()]),
                    waits_on_human=[wait("w-2"), wait("w-1")])]
    first = merge.merge(MAP, None, ls, [], 0, NOW)
    second = merge.merge(MAP, None, ls, [], 0, NOW)
    assert first["project_status"] == second["project_status"]
    assert first["next_action"] == second["next_action"]

def test_status_and_action_do_not_depend_on_lane_order():
    ls = [passing("claude", "impl", findings=[finding()]),
          broken_lane("zeta"), broken_lane("alpha")]
    first = merge.merge(MAP, None, ls, [], 0, NOW)
    second = merge.merge(MAP, None, list(reversed(ls)), [], 0, NOW)
    assert first["project_status"] == second["project_status"]
    assert first["next_action"] == second["next_action"]


# --- a legacy-shaped project (map only, no lanes) ---

def test_legacy_project_without_lanes_is_ready_to_start(tmp_path):
    from conductor import store
    from tests.test_store import write_project
    loaded = store.load(write_project(tmp_path))
    state = merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                        loaded.events, loaded.skipped_events, NOW)
    assert status(state)["state"] == "ready"
    assert state["next_action"]["kind"] == "start_work"
    assert state["next_action"]["ref"] is None       # that map declares no roles
