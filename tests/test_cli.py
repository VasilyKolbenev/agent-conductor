"""Tests for conductor.__main__ — the `conduct` CLI, subprocess-free.

Every test calls `main(argv)` directly and inspects the return code plus
capsys-captured stdout/stderr.
"""
import json
import tomllib
import pytest
from conductor.__main__ import main
from tests.test_store import write_project, good_lane


def test_validate_ok_project_exits_0(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["validate", "--dir", str(root)]) == 0

def test_validate_schema_error_exits_1(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"bad": "{not json"})
    assert main(["validate", "--dir", str(root)]) == 1
    assert "bad" in capsys.readouterr().out

def test_validate_referential_drift_warns_but_exits_0(tmp_path, capsys):
    lane_body = json.dumps({"schema_version": 1, "author": "claude",
                            "updated": "2026-07-30T11:00:00+00:00",
                            "map_status": {"ghost": "pass"}})
    root = write_project(tmp_path, lanes={"claude": lane_body})
    assert main(["validate", "--dir", str(root)]) == 0
    assert "ghost" in capsys.readouterr().out

def test_init_scaffolds_and_prints_bootstrap(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "conductor" / "map.toml").is_file()
    assert (tmp_path / "conductor" / "lanes").is_dir()
    assert "map.toml" in capsys.readouterr().out

def test_init_refuses_existing(tmp_path, capsys):
    (tmp_path / "conductor").mkdir()
    assert main(["init", "--dir", str(tmp_path)]) == 1

def test_prompt_renders_role_and_fails_on_unknown(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    # map from write_project has no roles → unknown role must exit 1
    assert main(["prompt", "ghost", "--dir", str(root)]) == 1


# --- additional coverage beyond the mandated set ---

MAP_WITH_ROLES = (
    'schema_version = 1\nproject = "p"\n'
    '[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n'
    '[[cycle.roles]]\nid = "reviewer"\nreviews = []\n'
)


def test_validate_broken_map_prints_error_and_exits_1(tmp_path, capsys):
    root = write_project(tmp_path, map_toml="= not toml")
    assert main(["validate", "--dir", str(root)]) == 1
    assert "map.toml" in capsys.readouterr().out

def test_validate_missing_conductor_dir_exits_1_with_stderr(tmp_path, capsys):
    assert main(["validate", "--dir", str(tmp_path)]) == 1
    assert "conductor" in capsys.readouterr().err

def test_init_writes_empty_events_and_valid_toml_map(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "conductor" / "events.jsonl").read_text(encoding="utf-8") == ""
    data = tomllib.loads((tmp_path / "conductor" / "map.toml").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["nodes"]

def test_init_then_validate_is_clean(tmp_path, capsys):
    # The scaffold must satisfy its own validation rules end-to-end and print
    # zero warnings (subsumes the deprecated-row check, ADR 0001).
    assert main(["init", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()                       # isolate validate's output from init's
    assert main(["validate", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""

def test_validate_schema_version_warning_surfaces_in_stdout(tmp_path, capsys):
    # Pin: validate must pass loaded.warnings into merge (extra_warnings=...) —
    # dropping the pass-through would lose loader-level schema-version warnings.
    body = good_lane().replace('"schema_version": 1', '"schema_version": 2')
    root = write_project(tmp_path, lanes={"claude": body})
    assert main(["validate", "--dir", str(root)]) == 0
    assert "schema_version" in capsys.readouterr().out

def test_validate_map_error_printed_before_lane_error(tmp_path, capsys):
    # Pin: the map error is inserted at position 0, ahead of broken-lane errors.
    root = write_project(tmp_path, map_toml="= not toml", lanes={"bad": "{not json"})
    assert main(["validate", "--dir", str(root)]) == 1
    out = capsys.readouterr().out
    assert "map.toml" in out and "lane bad" in out
    assert out.index("map.toml") < out.index("lane bad")

def test_prompt_known_role_prints_prompt(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES,
                         lanes={"claude": good_lane()})
    assert main(["prompt", "reviewer", "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "reviewer" in out and "lanes/" in out

def test_prompt_unknown_role_message_goes_to_stderr(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "ghost", "--dir", str(root)]) == 1
    err = capsys.readouterr().err
    assert "ghost" in err and "reviewer" in err

def test_prompt_broken_map_exits_1_before_rendering(tmp_path, capsys):
    root = write_project(tmp_path, map_toml="= not toml")
    assert main(["prompt", "reviewer", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert "map.toml" in captured.err and captured.out == ""

def test_prompt_missing_conductor_dir_exits_1_with_stderr(tmp_path, capsys):
    assert main(["prompt", "reviewer", "--dir", str(tmp_path)]) == 1
    assert "conductor" in capsys.readouterr().err

def test_demo_rejects_dir_flag(capsys):
    # Pin: demo materializes its own throwaway root — --dir is deliberately
    # not accepted (argparse usage error, exit 2). Demo behavior itself is
    # covered in tests/test_demo.py.
    with pytest.raises(SystemExit) as e:
        main(["demo", "--dir", "."])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err
