"""Tests for conductor.demo — the bundled real-case fixture and `conduct demo`."""
import pytest

from conductor import demo
from conductor.__main__ import main


def test_demo_fixture_is_schema_valid(tmp_path):
    root = demo.materialize(tmp_path)
    assert main(["validate", "--dir", str(root)]) == 0

def test_demo_state_tells_the_story(tmp_path):
    root = demo.materialize(tmp_path)
    from conductor import store, merge
    from datetime import datetime, timezone
    loaded = store.load(root)
    state = merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                        loaded.events, loaded.skipped_events,
                        datetime.now(timezone.utc))
    assert state["kpi"]["disagreements"] == 1          # D-3 partial
    assert state["kpi"]["queue"] == 1                  # w-stt
    assert state["kpi"]["blockers"] == 3
    smoke = next(n for n in state["map"]["nodes"] if n["id"] == "smoke")
    assert smoke["status"] == "fail"


# --- additional coverage beyond the mandated set ---

def _demo_state(tmp_path):
    from datetime import datetime, timezone
    from conductor import merge, store
    loaded = store.load(demo.materialize(tmp_path))
    return merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                       loaded.events, loaded.skipped_events,
                       datetime.now(timezone.utc), extra_warnings=loaded.warnings)


def test_materialize_returns_target_with_conductor_tree(tmp_path):
    root = demo.materialize(tmp_path)
    assert root == tmp_path
    for rel in ("map.toml", "events.jsonl", "lanes/claude.json", "lanes/codex.json"):
        assert (root / "conductor" / rel).is_file()

def test_demo_disagreement_is_d3_with_reviewer_partial(tmp_path):
    state = _demo_state(tmp_path)
    (d3,) = state["disagreements"]
    assert d3["id"] == "D-3" and d3["review_state"] == "disagreement"
    assert d3["verdicts"]["codex"]["disposition"] == "partial"

def test_demo_state_is_warning_free_and_never_stale(tmp_path):
    # The fixture must render clean: no referential drift, no stale lanes,
    # no skipped events — a demo with warnings would be a fixture bug.
    state = _demo_state(tmp_path)
    assert state["warnings"] == []
    assert state["kpi"]["stale_lanes"] == 0 and state["kpi"]["broken_lanes"] == 0
    assert len(state["events_tail"]) == 10

def test_demo_help_exits_0(capsys):
    with pytest.raises(SystemExit) as e:
        main(["demo", "--help"])
    assert e.value.code == 0
