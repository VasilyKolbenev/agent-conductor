"""Tolerant-reader hardening (task 15.5): whatever passes schema validation
must merge without exception AND survive `json.dumps(state)` — schema-valid
input never crashes downstream (PROTOCOL.md preamble). Almost-valid input
degrades to a broken lane / map_error, which IS the tolerant path.
"""
import json
from datetime import datetime, timezone

from conductor import demo, merge, store
from tests.test_store import write_project, good_lane


def _roundtrip(root):
    """load -> merge -> json.dumps: the guarantee under test. Returns state."""
    loaded = store.load(root)
    state = merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                        loaded.events, loaded.skipped_events,
                        datetime.now(timezone.utc), extra_warnings=loaded.warnings)
    json.dumps(state)
    return state


def test_demo_fixture_roundtrip_serializes(tmp_path):
    state = _roundtrip(demo.materialize(tmp_path))
    assert state["kpi"]["broken_lanes"] == 0


FULL_MAP = (
    'schema_version = 1\nproject = "p"\n'
    '[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\nrow = 0\n'
    '[[nodes]]\nid = "b"\nlabel = "b"\nkind = "gate"\ndepends_on = ["a"]\n'
    '[cycle]\nphases = ["plan", "review"]\n'
    '[[cycle.roles]]\nid = "implementer"\nharness = "claude-code"\nreviews = []\n'
    '[[cycle.roles]]\nid = "reviewer"\nharness = "codex"\nreviews = ["implementer"]\n'
    '[[invariants]]\nid = "inv-1"\ntext = "main is protected"\n'
)


def test_every_optional_section_roundtrips_and_row_warns(tmp_path):
    events = ('{"ts": "2026-07-30T10:00:00+00:00", "author": "claude", '
              '"kind": "ok", "text": "hi"}\n')
    state = _roundtrip(write_project(tmp_path, map_toml=FULL_MAP,
                                     lanes={"claude": good_lane()}, events=events))
    assert state["kpi"]["broken_lanes"] == 0 and state["project"] == "p"
    assert any("row is deprecated and ignored" in w for w in state["warnings"])


def test_nan_staleness_lane_degrades_to_broken_not_crash(tmp_path):
    # Reproducer A: json.loads accepts a bare NaN token — merge must not
    # see it (ValueError in timedelta). The lane becomes broken instead.
    body = good_lane().replace('"updated"', '"staleness_after_minutes": NaN, "updated"')
    state = _roundtrip(write_project(tmp_path, lanes={"claude": body}))
    (entry,) = state["lanes"]
    assert entry["broken"] and "staleness_after_minutes" in entry["error"]


def test_infinity_staleness_lane_degrades_to_broken_not_crash(tmp_path):
    # Reproducer C: Infinity would raise OverflowError in timedelta.
    body = good_lane().replace('"updated"',
                               '"staleness_after_minutes": Infinity, "updated"')
    state = _roundtrip(write_project(tmp_path, lanes={"claude": body}))
    (entry,) = state["lanes"]
    assert entry["broken"] and "staleness_after_minutes" in entry["error"]


def test_toml_date_label_degrades_to_map_error_not_crash(tmp_path):
    # Reproducer B: tomllib parses `label = 2026-07-30` as datetime.date,
    # which json.dumps cannot serialize. It must become a map error.
    map_toml = ('schema_version = 1\nproject = "p"\n'
                '[[nodes]]\nid = "a"\nlabel = 2026-07-30\nkind = "artifact"\n')
    state = _roundtrip(write_project(tmp_path, map_toml=map_toml))
    assert any("map is unreadable" in w and "label must be a string" in w
               for w in state["warnings"])
