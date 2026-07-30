"""Lane classification: broken, stale, future-dated. Spec §5 rows Staleness/Broken."""
from datetime import datetime, timezone
from conductor import merge

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

def _map():
    return {"schema_version": 1, "project": "p",
            "nodes": [{"id": "a", "label": "a", "kind": "artifact"}]}

def lane(author="claude", updated="2026-07-30T11:00:00+00:00", **over):
    data = {"schema_version": 1, "author": author, "updated": updated}
    data.update(over)
    return {"author": author, "data": data, "error": None}


def test_broken_lane_is_listed_and_nothing_inferred():
    state = merge.merge(_map(), None,
                        [{"author": "bad", "data": None, "error": "invalid JSON"}],
                        [], 0, NOW)
    assert state["lanes"][0]["broken"] is True
    assert state["lanes"][0]["error"] == "invalid JSON"
    assert state["kpi"]["broken_lanes"] == 1

def test_stale_lane_flagged_by_default_threshold():
    old = lane(updated="2026-07-30T05:00:00+00:00")   # 7h ago > 360min
    state = merge.merge(_map(), None, [old], [], 0, NOW)
    assert state["lanes"][0]["stale"] is True
    assert state["kpi"]["stale_lanes"] == 1

def test_custom_staleness_threshold_respected():
    old = lane(updated="2026-07-30T05:00:00+00:00",
               staleness_after_minutes=600)            # 7h < 10h
    state = merge.merge(_map(), None, [old], [], 0, NOW)
    assert state["lanes"][0]["stale"] is False

def test_future_dated_lane_warns():
    fut = lane(updated="2026-07-30T13:00:00+00:00")
    state = merge.merge(_map(), None, [fut], [], 0, NOW)
    assert any("future" in w for w in state["warnings"])

def test_naive_timestamp_is_coerced_to_utc_not_crash():
    naive = lane(updated="2026-07-30T11:00:00")        # no offset — sloppy but legal
    state = merge.merge(_map(), None, [naive], [], 0, NOW)
    assert state["lanes"][0]["stale"] is False          # 1h ago in UTC

def test_state_shape_minimum():
    state = merge.merge(_map(), None, [], [], 0, NOW)
    for key in ("schema_version", "generated_at", "project", "map", "cycle",
                "lanes", "findings", "disagreements", "human_queue",
                "invariants", "events_tail", "kpi", "warnings"):
        assert key in state

def test_broken_map_is_surfaced():
    state = merge.merge(None, "map: at least one node is required", [], [], 0, NOW)
    assert any("map" in w for w in state["warnings"])
    assert state["map"]["nodes"] == []

def test_extra_warnings_flow_into_state():
    state = merge.merge(_map(), None, [], [], 0, NOW,
                        extra_warnings=["lane x: schema_version 2 ..."])
    assert any("schema_version 2" in w for w in state["warnings"])

def test_skipped_events_produce_a_warning():
    state = merge.merge(_map(), None, [], [], 0, NOW,
                        extra_warnings=())
    assert not any("skipped" in w for w in state["warnings"])
    state2 = merge.merge(_map(), None, [], [], 3, NOW)
    assert any("skipped 3" in w for w in state2["warnings"])
