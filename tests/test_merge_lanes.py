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

def _event(i):
    # store.load hands merge the events oldest-first; the text carries the index
    # so ordering is observable in the output.
    return {"ts": "2026-07-30T10:00:00+00:00", "author": "claude",
            "kind": "ok", "text": f"e{i}"}


def test_events_tail_is_newest_first():
    state = merge.merge(_map(), None, [], [_event(i) for i in range(3)], 0, NOW)
    assert [e["text"] for e in state["events_tail"]] == ["e2", "e1", "e0"]

def test_events_tail_caps_at_the_tail_limit_and_keeps_the_newest():
    n = merge.EVENTS_TAIL + 25
    state = merge.merge(_map(), None, [], [_event(i) for i in range(n)], 0, NOW)
    tail = state["events_tail"]
    assert len(tail) == merge.EVENTS_TAIL
    assert tail[0]["text"] == f"e{n - 1}"                 # newest survives the cap
    assert tail[-1]["text"] == f"e{n - merge.EVENTS_TAIL}"  # the 25 oldest are dropped


def test_null_now_is_emitted_as_an_empty_object():
    # §6.1 sketches "now": {}. A lane may legally write null — schema.py only
    # rejects a non-dict non-null `now` — so state must still emit an object.
    state = merge.merge(_map(), None, [lane(now=None)], [], 0, NOW)
    assert state["lanes"][0]["now"] == {}

def test_absent_now_is_emitted_as_an_empty_object():
    state = merge.merge(_map(), None, [lane()], [], 0, NOW)
    assert state["lanes"][0]["now"] == {}

def test_present_now_is_carried_through_verbatim():
    payload = {"task": "fixing gate D", "phase": "review"}
    state = merge.merge(_map(), None, [lane(now=payload)], [], 0, NOW)
    assert state["lanes"][0]["now"] == payload

def test_staleness_boundary_exact_threshold_is_not_stale():
    edge = lane(updated="2026-07-30T06:00:00+00:00")   # exactly 360 min before NOW
    state = merge.merge(_map(), None, [edge], [], 0, NOW)
    assert state["lanes"][0]["stale"] is False          # strict >, spec §6
