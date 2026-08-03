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
