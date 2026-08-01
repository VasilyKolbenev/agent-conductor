"""Tests for conductor.store — tolerant loading of a project's conductor/ directory.

`write_project` and `good_lane` are shared helpers imported by later test files
(`from tests.test_store import write_project, good_lane`) — keep names and
signatures stable.
"""
import json
from conductor import store

def write_project(tmp_path, map_toml=None, lanes=None, events=None):
    c = tmp_path / "conductor"; (c / "lanes").mkdir(parents=True)
    (c / "map.toml").write_text(map_toml if map_toml is not None else
        'schema_version = 1\nproject = "p"\n[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n',
        encoding="utf-8")
    for name, body in (lanes or {}).items():
        (c / "lanes" / f"{name}.json").write_text(body, encoding="utf-8")
    if events is not None:
        (c / "events.jsonl").write_text(events, encoding="utf-8")
    return tmp_path

def good_lane(author="claude"):
    return json.dumps({"schema_version": 1, "author": author,
                       "updated": "2026-07-30T11:00:00+00:00"})


def test_loads_valid_project(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()},
                         events='{"ts":"2026-07-30T10:00:00+00:00","author":"claude","kind":"ok","text":"hi"}\n')
    loaded = store.load(root)
    assert loaded.map_data is not None and loaded.map_error is None
    assert loaded.lanes[0]["author"] == "claude" and loaded.lanes[0]["error"] is None
    assert len(loaded.events) == 1 and loaded.skipped_events == 0

def test_malformed_lane_becomes_broken_entry_not_crash(tmp_path):
    root = write_project(tmp_path, lanes={"bad": "{not json"})
    loaded = store.load(root)
    assert loaded.lanes[0]["data"] is None and "bad" == loaded.lanes[0]["author"]
    assert loaded.lanes[0]["error"]

def test_author_filename_mismatch_is_broken(tmp_path):
    root = write_project(tmp_path, lanes={"impostor": good_lane(author="claude")})
    loaded = store.load(root)
    assert loaded.lanes[0]["data"] is None and "author" in loaded.lanes[0]["error"]

def test_malformed_event_lines_are_skipped_and_counted(tmp_path):
    root = write_project(tmp_path, events="not json\n" +
        '{"ts":"2026-07-30T10:00:00+00:00","author":"a","kind":"ok","text":"x"}\n')
    loaded = store.load(root)
    assert len(loaded.events) == 1 and loaded.skipped_events == 1

def test_broken_map_reported_not_raised(tmp_path):
    root = write_project(tmp_path, map_toml="= not toml")
    loaded = store.load(root)
    assert loaded.map_data is None and loaded.map_error

def test_schema_version_2_lane_surfaces_a_warning(tmp_path):
    body = good_lane().replace('"schema_version": 1', '"schema_version": 2')
    root = write_project(tmp_path, lanes={"claude": body})
    loaded = store.load(root)
    assert loaded.lanes[0]["error"] is None            # accepted, not rejected
    assert any("schema_version" in w for w in loaded.warnings)

def test_missing_conductor_dir_raises_clean_error(tmp_path):
    try:
        store.load(tmp_path)
        assert False, "expected StoreError"
    except store.StoreError as e:
        assert "conductor" in str(e)


# --- additional coverage beyond the mandated set ---

def test_missing_map_toml_reported_not_raised(tmp_path):
    root = write_project(tmp_path)
    (root / "conductor" / "map.toml").unlink()
    loaded = store.load(root)
    assert loaded.map_data is None and "missing" in loaded.map_error

def test_map_schema_version_2_surfaces_a_warning(tmp_path):
    root = write_project(tmp_path, map_toml=(
        'schema_version = 2\n[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n'))
    loaded = store.load(root)
    assert loaded.map_data is not None and loaded.map_error is None
    assert any("schema_version" in w for w in loaded.warnings)

def test_invalid_map_semantics_reported_as_map_error(tmp_path):
    root = write_project(tmp_path, map_toml="schema_version = 1\n")  # no nodes
    loaded = store.load(root)
    assert loaded.map_data is None and "node" in loaded.map_error

def test_non_dict_lane_json_is_broken_not_crash(tmp_path):
    root = write_project(tmp_path, lanes={"listy": "[1, 2]", "stringy": '"str"'})
    loaded = store.load(root)
    by_author = {lane["author"]: lane for lane in loaded.lanes}
    assert by_author["listy"]["data"] is None and by_author["listy"]["error"]
    assert by_author["stringy"]["data"] is None and by_author["stringy"]["error"]

def test_invalid_author_filename_is_broken(tmp_path):
    root = write_project(tmp_path)
    lane_path = root / "conductor" / "lanes" / "dot.ted.json"  # stem "dot.ted"
    lane_path.write_text(good_lane(author="dot.ted"), encoding="utf-8")
    loaded = store.load(root)
    assert loaded.lanes[0]["data"] is None
    assert "filename" in loaded.lanes[0]["error"]

def test_lanes_sorted_by_filename(tmp_path):
    root = write_project(tmp_path, lanes={"zeta": good_lane(author="zeta"),
                                          "alpha": good_lane(author="alpha")})
    loaded = store.load(root)
    assert [lane["author"] for lane in loaded.lanes] == ["alpha", "zeta"]

def test_missing_lanes_dir_and_events_file_are_fine(tmp_path):
    c = tmp_path / "conductor"; c.mkdir()
    (c / "map.toml").write_text(
        'schema_version = 1\n[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n',
        encoding="utf-8")
    loaded = store.load(tmp_path)
    assert loaded.lanes == [] and loaded.events == [] and loaded.skipped_events == 0

def test_blank_event_lines_are_ignored_not_counted(tmp_path):
    root = write_project(tmp_path, events="\n   \n" +
        '{"ts":"2026-07-30T10:00:00+00:00","author":"a","kind":"ok","text":"x"}\n\n')
    loaded = store.load(root)
    assert len(loaded.events) == 1 and loaded.skipped_events == 0

def test_valid_json_but_invalid_event_is_counted_as_skipped(tmp_path):
    root = write_project(tmp_path, events='{"ts":"nope","author":"","kind":"???"}\n')
    loaded = store.load(root)
    assert loaded.events == [] and loaded.skipped_events == 1
