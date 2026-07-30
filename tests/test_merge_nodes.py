from datetime import datetime, timezone
from conductor import merge
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

def _map():
    return {"schema_version": 1, "project": "p",
            "nodes": [{"id": "a", "label": "a", "kind": "artifact"},
                      {"id": "b", "label": "b", "kind": "artifact"}]}

def lane(author, updated, status_map, **over):
    data = {"schema_version": 1, "author": author, "updated": updated,
            "map_status": status_map}
    data.update(over)
    return {"author": author, "data": data, "error": None}


def _node(state, nid):
    return next(n for n in state["map"]["nodes"] if n["id"] == nid)

# NOTE (spec insight): the §5 "most recently updated lane wins" clause can only
# ever run when all voters AGREE — any disagreement is contested first. So
# recency is unobservable in output and deliberately has no dedicated test.
def test_single_lane_sets_node_status():
    l1 = lane("only", "2026-07-30T11:00:00+00:00", {"a": "pass"})
    state = merge.merge(_map(), None, [l1], [], 0, NOW)
    assert _node(state, "a")["status"] == "pass"

def test_agreeing_lanes_are_not_contested():
    l1 = lane("x", "2026-07-30T10:00:00+00:00", {"a": "pass"})
    l2 = lane("y", "2026-07-30T11:00:00+00:00", {"a": "pass"})
    state = merge.merge(_map(), None, [l1, l2], [], 0, NOW)
    assert _node(state, "a")["status"] == "pass"
    assert _node(state, "a")["contested_by"] == []

def test_disagreeing_lanes_contest_the_node_with_all_authors():
    ls = [lane("z", "2026-07-30T09:00:00+00:00", {"a": "blocked"}),
          lane("x", "2026-07-30T10:00:00+00:00", {"a": "pass"}),
          lane("y", "2026-07-30T11:00:00+00:00", {"a": "fail"})]
    state = merge.merge(_map(), None, ls, [], 0, NOW)
    node = _node(state, "a")
    assert node["status"] == "contested"
    assert sorted(node["contested_by"]) == ["x", "y", "z"]

def test_unmentioned_node_is_idle():
    state = merge.merge(_map(), None, [], [], 0, NOW)
    assert _node(state, "b")["status"] == "idle"

def test_future_dated_lane_excluded_from_race_but_counts_for_contested():
    l1 = lane("past", "2026-07-30T11:00:00+00:00", {"a": "pass"})
    l2 = lane("fut", "2026-07-30T13:00:00+00:00", {"a": "pass"})
    state = merge.merge(_map(), None, [l1, l2], [], 0, NOW)
    assert _node(state, "a")["status"] == "pass"   # agreement → future lane harmless
    l3 = lane("fut2", "2026-07-30T13:00:00+00:00", {"a": "fail"})
    state2 = merge.merge(_map(), None, [l1, l3], [], 0, NOW)
    assert _node(state2, "a")["status"] == "contested"

def test_stale_lane_still_counts_for_node_status():
    old = lane("old", "2026-07-30T01:00:00+00:00", {"a": "fail"})
    state = merge.merge(_map(), None, [old], [], 0, NOW)
    assert _node(state, "a")["status"] == "fail"

def test_unknown_map_status_key_ignored_with_warning():
    l1 = lane("x", "2026-07-30T11:00:00+00:00", {"ghost": "pass"})
    state = merge.merge(_map(), None, [l1], [], 0, NOW)
    assert all(n["status"] == "idle" for n in state["map"]["nodes"])
    assert any("ghost" in w for w in state["warnings"])

def test_sole_future_voter_leaves_node_idle():
    fut = lane("fut", "2026-07-30T13:00:00+00:00", {"a": "pass"})   # future vs NOW
    state = merge.merge(_map(), None, [fut], [], 0, NOW)
    assert _node(state, "a")["status"] == "idle"                     # exclusion is total
    assert any("future" in w for w in state["warnings"])
