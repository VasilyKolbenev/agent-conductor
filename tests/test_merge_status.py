"""Tests for `project_status` / `next_action` — the first-screen summary (§6.1).

The precedence table is normative and ordered: every row is pinned here, and
so is the ordering between adjacent rows. `complete` is the only state that
may read as success, so each of its conditions gets its own refusal test.
"""
from datetime import datetime, timezone

from conductor import merge, store
from tests.test_merge_review import MAP, finding, lane
from tests.test_store import write_project

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


def review_state_of(state, fid):
    return next(f["review_state"] for f in state["findings"] if f["id"] == fid)


def blocked_project(*, queue=True, broken=True, invariant=True):
    """A project tripping every blocked row, minus the ones switched off."""
    extra = {"map_status": {"n": "fail"}}
    if invariant:
        extra["invariants"] = [{"id": "i-1", "ok": False}]
    if queue:
        extra["waits_on_human"] = [wait()]
    lanes = [with_data(lane("claude", "impl"), **extra)]
    return lanes + [broken_lane()] if broken else lanes


def rung(lanes):
    """The (reason, kind) pair a lane set lands on."""
    state = merge.merge(INVARIANT_MAP, None, lanes, [], 0, NOW)
    return status(state)["reason"], state["next_action"]["kind"]


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
                             "detail": "1 request waiting on you"}

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
                             "detail": "1 of 1 node failing or blocked"}

def test_blocked_node_is_blocked_too():
    state = merge.merge(MAP, None, [with_data(lane("claude", "impl"),
                                              map_status={"n": "blocked"})], [], 0, NOW)
    assert status(state)["reason"] == "node_failing"

def test_all_clear_project_is_complete():
    state = merge.merge(MAP, None, [passing()], [], 0, NOW)
    assert status(state) == {"state": "complete", "reason": "all_clear",
                             "detail": "1 of 1 node passing"}

def test_live_lane_that_has_not_finished_is_active():
    state = merge.merge(MAP, None, [lane("claude", "impl")], [], 0, NOW)
    assert status(state) == {"state": "active", "reason": "work_in_progress",
                             "detail": "0 of 1 node passing"}

def test_no_lanes_is_ready():
    state = merge.merge(MAP, None, [], [], 0, NOW)
    assert status(state) == {"state": "ready", "reason": "no_lanes_yet",
                             "detail": "no lanes have reported yet"}


# --- complete is refused when any single one of its conditions fails ---
# Three of these document intent rather than discriminate: the queued-wait and
# broken-lane cases never reach `_is_complete` (rows 2-3 of the status ladder
# divert them), and the review-obligation case is refused by its open finding
# first. Deleting those clauses from `_is_complete` would leave all three
# green — they pin the promise, not the code that keeps it.

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
    # The open finding refuses first; pending_verdicts cannot be non-empty with
    # an empty findings list, so its clause is a spec-literal belt on braces.
    ls = [passing("claude", "impl", findings=[finding()])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {"rev": ["D-1"], "sec": ["D-1"]}
    assert status(state)["state"] == "active"

def test_complete_refused_when_a_wait_is_queued():
    # Row 2 diverts this before _is_complete runs; the clause stays in the spec
    # and in the code so complete is right on its own terms either way.
    state = merge.merge(MAP, None, [with_data(passing(), waits_on_human=[wait()])],
                        [], 0, NOW)
    assert status(state)["state"] == "blocked"        # never complete

def test_complete_refused_when_a_lane_is_stale():
    state = merge.merge(MAP, None, [passing(updated=STALE_UPDATED)], [], 0, NOW)
    assert state["kpi"]["stale_lanes"] == 1
    assert status(state)["state"] == "active"         # stale never reads as success

def test_complete_refused_when_a_lane_is_broken():
    # Row 3 diverts this too — same deliberate redundancy as the queue clause.
    state = merge.merge(MAP, None, [passing(), broken_lane()], [], 0, NOW)
    assert status(state)["state"] == "blocked"

def test_complete_refused_when_no_nodes_are_declared():
    state = merge.merge({**MAP, "nodes": []}, None, [lane("claude", "impl")], [], 0, NOW)
    assert status(state) == {"state": "active", "reason": "work_in_progress",
                             "detail": "no nodes declared in map.toml"}


# --- the two ladders are written twice by hand; pin them in agreement ---

def test_next_action_kind_matches_the_blocked_reason_at_every_rung():
    # Each rung keeps every LOWER condition in play, so swapping any adjacent
    # pair in either ladder shows up here. The panel renders reason and kind
    # side by side; nothing else keeps the two orders together.
    assert rung(blocked_project()) == ("human_decision", "answer_wait")
    assert rung(blocked_project(queue=False)) == ("broken_lane", "fix_lane")
    assert rung(blocked_project(queue=False, broken=False)) == (
        "invariant_broken", "fix_invariant")
    assert rung(blocked_project(queue=False, broken=False, invariant=False)) == (
        "node_failing", "fix_node")


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

def test_next_action_lead_in_fits_every_wait_kind():
    # A wait is not always a question: WAIT_KINDS covers decision, action, review.
    for kind, lead in (("decision", "Answer the decision"), ("action", "Do the action"),
                       ("review", "Do the review")):
        ls = [with_data(passing(), waits_on_human=[wait(kind=kind, title="Rotate the key")])]
        state = merge.merge(MAP, None, ls, [], 0, NOW)
        assert state["next_action"]["text"] == f"{lead}: Rotate the key"

def test_queue_detail_is_kind_neutral_and_pluralized():
    for kind in ("decision", "action", "review"):
        ls = [with_data(passing(), waits_on_human=[wait(kind=kind)])]
        state = merge.merge(MAP, None, ls, [], 0, NOW)
        assert status(state)["detail"] == "1 request waiting on you"
    two = [with_data(passing(), waits_on_human=[wait("w-1"), wait("w-2", kind="action")])]
    assert status(merge.merge(MAP, None, two, [], 0, NOW))["detail"] == (
        "2 requests waiting on you")

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

def test_next_action_review_finding_asks_the_running_reviewer_for_a_verdict():
    ls = [passing("claude", "impl", findings=[finding()]),
          passing("codex", "rev"), passing("scan", "sec")]       # both reviewers running
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    action = state["next_action"]
    assert action["kind"] == "review_finding" and action["ref"] == "D-1"
    assert action["text"] == "Get a verdict from rev on finding D-1."   # lowest role owing

def test_next_action_review_finding_asks_to_start_a_role_nobody_holds():
    state = merge.merge(MAP, None, [passing("claude", "impl", findings=[finding()])],
                        [], 0, NOW)
    assert review_state_of(state, "D-1") == "uncovered"
    assert state["next_action"] == {
        "text": "Nobody is running the rev role — start one to review finding D-1.",
        "kind": "review_finding", "ref": "D-1"}

def test_next_action_names_the_absent_role_even_when_another_is_merely_silent():
    # review_state is a per-finding aggregate (unreviewed outranks uncovered),
    # so branching the copy on it would chase an agent nobody is running. The
    # text follows the picked role's own lane instead.
    m = {**MAP, "cycle": {"phases": [], "roles": [
        {"id": "impl", "harness": "cc", "reviews": []},
        {"id": "arev", "harness": "cx", "reviews": ["impl"]},     # sorts first, absent
        {"id": "zrev", "harness": "cx", "reviews": ["impl"]}]}}   # present but silent
    ls = [passing("claude", "impl", findings=[finding()]), passing("codex", "zrev")]
    state = merge.merge(m, None, ls, [], 0, NOW)
    assert review_state_of(state, "D-1") == "unreviewed"
    assert state["next_action"]["ref"] == "D-1"
    assert state["next_action"]["text"].startswith("Nobody is running the arev role")

def test_next_action_resolve_disagreement_once_every_verdict_is_in():
    ls = [passing("claude", "impl", findings=[finding()]),
          passing("codex", "rev", verdicts={"D-1": {"disposition": "refuted", "note": "no"}}),
          passing("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {}       # nothing owed; the dispute remains
    action = state["next_action"]
    assert action["kind"] == "resolve_disagreement" and action["ref"] == "D-1"
    assert "D-1" in action["text"]

def test_next_action_review_finding_beats_a_disagreement():
    # Both rows apply: D-1 is disputed AND sec still owes a verdict on it.
    ls = [passing("claude", "impl", findings=[finding("D-1"), finding("D-2")]),
          passing("codex", "rev", verdicts={"D-1": {"disposition": "refuted", "note": "no"}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["disagreements"] and merge.pending_verdicts(state)
    assert state["next_action"]["kind"] == "review_finding"

def test_next_action_resolve_contested_node_names_the_disputing_lanes():
    ls = [with_data(lane("claude", "impl"), map_status={"n": "pass"}),
          with_data(lane("codex", "rev"), map_status={"n": "running"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["map"]["nodes"][0]["status"] == "contested"
    assert state["next_action"] == {
        "text": "Settle node n — claude, codex disagree on its status.",
        "kind": "resolve_contested_node", "ref": "n"}
    assert status(state)["state"] == "active"      # contested is not a hard blocker

def test_next_action_disagreement_beats_a_contested_node():
    ls = [passing("claude", "impl", findings=[finding()]),
          with_data(lane("codex", "rev",
                         verdicts={"D-1": {"disposition": "refuted", "note": "no"}}),
                    map_status={"n": "running"}),
          passing("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["map"]["nodes"][0]["status"] == "contested"
    assert merge.pending_verdicts(state) == {}
    assert state["next_action"]["kind"] == "resolve_disagreement"

def test_next_action_contested_node_beats_a_collision():
    ls = [with_data(lane("claude", "impl", findings=[finding()]), map_status={"n": "pass"}),
          with_data(lane("scan", "sec", findings=[finding()]), map_status={"n": "running"})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["map"]["nodes"][0]["status"] == "contested"
    assert any(f["review_state"] == "suspended" for f in state["findings"])
    assert state["next_action"]["kind"] == "resolve_contested_node"

def test_next_action_resolve_collision_names_the_duplicate_id():
    ls = [passing("claude", "impl", findings=[finding()]),
          passing("scan", "sec", findings=[finding()])]        # same id from two lanes
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert all(f["review_state"] == "suspended" for f in state["findings"])
    assert state["next_action"] == {
        "text": "Rename the duplicate finding id D-1 — 2 lanes are using it.",
        "kind": "resolve_collision", "ref": "D-1"}
    assert status(state)["state"] == "active"      # a collision is not a hard blocker

def test_next_action_picks_the_lowest_collided_finding_id():
    ls = [passing("claude", "impl", findings=[finding("D-1"), finding("D-2")]),
          passing("scan", "sec", findings=[finding("D-1"), finding("D-2")])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["next_action"]["ref"] == "D-1"

def test_next_action_disagreement_beats_a_collision():
    ls = [passing("claude", "impl", findings=[finding("D-1"), finding("D-2")]),
          passing("scan", "sec", findings=[finding("D-1")],
                  verdicts={"D-2": {"disposition": "confirmed", "note": ""}}),
          passing("codex", "rev", verdicts={"D-2": {"disposition": "refuted", "note": "no"}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert merge.pending_verdicts(state) == {}     # only the two rows below compete
    assert any(f["review_state"] == "suspended" for f in state["findings"])
    assert state["next_action"]["kind"] == "resolve_disagreement"
    assert state["next_action"]["ref"] == "D-2"

def test_next_action_collision_beats_a_stale_lane():
    ls = [passing("claude", "impl", findings=[finding()], updated=STALE_UPDATED),
          passing("scan", "sec", findings=[finding()])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["kpi"]["stale_lanes"] == 1
    assert state["next_action"]["kind"] == "resolve_collision"

def test_next_action_check_stale_lane_names_the_author():
    state = merge.merge(MAP, None, [passing(updated=STALE_UPDATED)], [], 0, NOW)
    action = state["next_action"]
    assert action["kind"] == "check_stale_lane" and action["ref"] == "claude"
    assert "claude" in action["text"]

def test_next_action_picks_the_lowest_stale_lane_author():
    ls = [passing("zeta", "impl", updated=STALE_UPDATED),
          passing("alpha", "impl", updated=STALE_UPDATED)]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert state["next_action"]["ref"] == "alpha"

def test_next_action_picks_the_lowest_broken_invariant_id():
    ls = [with_data(passing(), invariants=[{"id": "i-2", "ok": False},
                                           {"id": "i-1", "ok": False}])]
    state = merge.merge(INVARIANT_MAP, None, ls, [], 0, NOW)
    assert state["next_action"]["ref"] == "i-1"
    assert status(state)["detail"] == "2 invariants are broken"

def test_next_action_start_work_names_the_command_to_run():
    # No internal jargon on the first screen: this is a command a user can paste.
    action = merge.merge(MAP, None, [], [], 0, NOW)["next_action"]
    assert action == {"text": "Start the impl agent — run: conduct prompt --role impl",
                      "kind": "start_work", "ref": "impl"}

def test_next_action_start_work_uses_declaration_order_not_alphabetical():
    m = {**MAP, "cycle": {"phases": [], "roles": [
        {"id": "zeta", "harness": "cc", "reviews": []},
        {"id": "alpha", "harness": "cx", "reviews": []}]}}
    action = merge.merge(m, None, [], [], 0, NOW)["next_action"]
    assert action["kind"] == "start_work" and action["ref"] == "zeta"

def test_next_action_without_roles_asks_for_a_role_declaration():
    # There is no role to start, so pointing at `conduct prompt` is unfollowable.
    m = {**MAP, "cycle": {"phases": [], "roles": []}}
    action = merge.merge(m, None, [], [], 0, NOW)["next_action"]
    assert action == {"text": "Declare a role in conductor/map.toml to start work.",
                      "kind": "start_work", "ref": None}

def test_next_action_is_null_when_the_project_is_complete():
    state = merge.merge(MAP, None, [passing()], [], 0, NOW)
    assert status(state)["state"] == "complete"
    assert state["next_action"] is None

def test_next_action_is_null_when_active_with_nothing_outstanding():
    # Honest silence: work is running and nothing needs the user. start_work
    # belongs to `ready` alone — widening that guard would nag mid-flight.
    state = merge.merge(MAP, None, [lane("claude", "impl")], [], 0, NOW)
    assert status(state)["state"] == "active"
    assert state["next_action"] is None


# --- the emitted vocabulary is exactly what merge exports ---

def test_every_emitted_state_reason_and_kind_is_exported():
    contested = [with_data(lane("claude", "impl"), map_status={"n": "pass"}),
                 with_data(lane("codex", "rev"), map_status={"n": "running"})]
    collided = [passing("claude", "impl", findings=[finding()]),
                passing("scan", "sec", findings=[finding()])]
    disputed = [passing("claude", "impl", findings=[finding()]),
                passing("codex", "rev",
                        verdicts={"D-1": {"disposition": "refuted", "note": "x"}}),
                passing("scan", "sec",
                        verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    scenarios = [
        (None, "boom", []),                                            # unknown / fix_map
        (MAP, None, [with_data(passing(), waits_on_human=[wait()])]),  # answer_wait
        (MAP, None, [passing(), broken_lane()]),                       # fix_lane
        (INVARIANT_MAP, None,
         [with_data(passing(), invariants=[{"id": "i-1", "ok": False}])]),
        (MAP, None, [with_data(lane("claude", "impl"), map_status={"n": "fail"})]),
        (MAP, None, [passing()]),                                      # complete / null
        (MAP, None, [passing("claude", "impl", findings=[finding()])]),
        (MAP, None, disputed),
        (MAP, None, contested),
        (MAP, None, collided),
        (MAP, None, [passing(updated=STALE_UPDATED)]),                 # check_stale_lane
        (MAP, None, []),                                               # ready / start_work
    ]
    states, reasons, kinds = set(), set(), set()
    for map_data, err, lanes in scenarios:
        state = merge.merge(map_data, err, lanes, [], 0, NOW)
        states.add(status(state)["state"])
        reasons.add(status(state)["reason"])
        if state["next_action"] is not None:
            kinds.add(state["next_action"]["kind"])
    # Equality both ways: no value escapes the vocabulary, and no exported
    # token is dead weight the panel would render a branch for.
    assert states == merge.PROJECT_STATES
    assert reasons == merge.STATUS_REASONS
    assert kinds == merge.NEXT_ACTION_KINDS


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
    loaded = store.load(write_project(tmp_path))
    state = merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                        loaded.events, loaded.skipped_events, NOW)
    assert status(state)["state"] == "ready"
    assert state["next_action"]["kind"] == "start_work"
    assert state["next_action"]["ref"] is None       # that map declares no roles
