from datetime import datetime, timezone
from conductor import merge
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

MAP = {"schema_version": 1, "project": "p",
       "nodes": [{"id": "n", "label": "n", "kind": "artifact"}],
       "cycle": {"phases": [],
                 "roles": [{"id": "impl", "harness": "cc", "reviews": []},
                           {"id": "rev", "harness": "cx", "reviews": ["impl"]},
                           {"id": "sec", "harness": "cx", "reviews": ["impl"]}]}}

def lane(author, role=None, findings=(), verdicts=None, updated="2026-07-30T11:00:00+00:00"):
    data = {"schema_version": 1, "author": author, "updated": updated,
            "findings": list(findings), "verdicts": verdicts or {}}
    if role:
        data["role"] = role
    return {"author": author, "data": data, "error": None}

def finding(fid="D-1", severity="blocker"):
    return {"id": fid, "title": "t", "severity": severity, "claim": "defect",
            "detail": "d", "evidence": "e", "refs": ["n"]}

def _f(state, fid):
    return next(f for f in state["findings"] if f["id"] == fid)


def test_confirmed_by_all_reviewing_roles_is_agreed():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "agreed"

def test_refuted_by_any_lane_is_disagreement():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "refuted", "note": "no"}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "disagreement"
    assert state["kpi"]["disagreements"] == 1

def test_observer_can_dispute_without_role():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("watcher", None, verdicts={"D-1": {"disposition": "partial", "note": "hm"}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "disagreement"

def test_silent_reviewing_role_is_unreviewed_never_agreed():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec")]                       # sec present but silent
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "unreviewed"

def test_absent_reviewing_role_is_uncovered():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)   # nobody holds "sec"
    assert _f(state, "D-1")["review_state"] == "uncovered"

def test_two_lanes_same_role_any_one_satisfies():
    m = {**MAP, "cycle": {"phases": [], "roles": [
        {"id": "impl", "harness": "cc", "reviews": []},
        {"id": "rev", "harness": "cx", "reviews": ["impl"]}]}}
    ls = [lane("claude", "impl", [finding()]),
          lane("codex1", "rev"),
          lane("codex2", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(m, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["review_state"] == "agreed"

def test_self_verdict_visible_but_ignored_in_computation():
    # Spec §5: self-verdicts are ignored in ALL review-state computation, yet
    # "per-author detail always remains visible in the finding's verdicts".
    ls = [lane("claude", "impl", [finding()],
               verdicts={"D-1": {"disposition": "refuted", "note": "self-doubt"}}),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    f = _f(state, "D-1")
    assert f["review_state"] == "agreed"                      # self-refute ignored
    assert f["verdicts"]["claude"]["disposition"] == "refuted"  # but still visible

def test_unknown_role_becomes_observer_with_warning():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}}),
          lane("mystery", "ghost-role",
               verdicts={"D-1": {"disposition": "refuted", "note": "x"}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert any("ghost-role" in w for w in state["warnings"])
    # observer verdicts still count for disputes:
    assert _f(state, "D-1")["review_state"] == "disagreement"
    assert _f(state, "D-1")["verdicts"]["mystery"]["role"] is None

def test_unknown_finding_refs_dropped_with_warning():
    bad = finding(); bad["refs"] = ["n", "ghost-node"]
    ls = [lane("claude", "impl", [bad])]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "D-1")["refs"] == ["n"]
    assert any("ghost-node" in w for w in state["warnings"])

def test_finding_with_no_reviewing_roles_is_vacuously_agreed():
    ls = [lane("watcher", None, [finding("O-1")])]   # observer's finding
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert _f(state, "O-1")["review_state"] == "agreed"

def test_id_collision_suspends_and_warns():
    ls = [lane("claude", "impl", [finding()]),
          lane("scan", "sec", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "refuted", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    collided = [f for f in state["findings"] if f["id"] == "D-1"]
    assert len(collided) == 2
    assert all(f["review_state"] == "suspended" for f in collided)
    assert any("id-collision" in w for w in state["warnings"])
    assert state["kpi"]["disagreements"] == 0
    # PROTOCOL Clarification: foreign verdicts stay VISIBLE on both collided rows
    assert all("codex" in f["verdicts"] for f in collided)

def test_stale_verdict_warns_and_is_excluded():
    ls = [lane("codex", "rev", verdicts={"GONE": {"disposition": "refuted", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    assert any("stale verdict" in w for w in state["warnings"])
    assert state["findings"] == []

def test_verdicts_keyed_by_author_with_role_inside():
    ls = [lane("claude", "impl", [finding()]),
          lane("codex", "rev", verdicts={"D-1": {"disposition": "confirmed", "note": "ok"}}),
          lane("scan", "sec", verdicts={"D-1": {"disposition": "confirmed", "note": ""}})]
    state = merge.merge(MAP, None, ls, [], 0, NOW)
    v = _f(state, "D-1")["verdicts"]["codex"]
    assert v == {"disposition": "confirmed", "note": "ok", "role": "rev"}
