"""Tests for conductor.__main__ — the `conduct` CLI, subprocess-free.

Every test calls `main(argv)` directly and inspects the return code plus
capsys-captured stdout/stderr.
"""
import json
import tomllib

import pytest
import conductor.__main__
from conductor import prompts, store
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


# --- C6.1: conduct prompt --role/--author (positional role deprecated) ---


def test_prompt_positional_role_warns_deprecated_but_works(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES,
                         lanes={"claude": good_lane()})
    assert main(["prompt", "reviewer", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert "deprecated" in captured.err and "--role" in captured.err
    assert "reviewer" in captured.out

def test_prompt_role_flag_exits_0_without_warning(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and "reviewer" in captured.out

def test_prompt_author_flag_renders_author_lane(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--author", "codex",
                 "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "conductor/lanes/codex.json" in out and '"author": "codex"' in out

def test_prompt_invalid_author_exits_1(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--author", "bad name",
                 "--dir", str(root)]) == 1
    assert "author" in capsys.readouterr().err

def test_prompt_positional_plus_role_flag_is_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["prompt", "reviewer", "--role", "reviewer", "--dir", str(tmp_path)])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err

def test_prompt_no_role_at_all_is_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["prompt", "--dir", str(tmp_path)])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err


# --- the stream contract ---
#
# stdout carries only the command's primary result, suitable for redirection.
# stderr carries dialogue, progress, explanations, usage warnings and
# operational errors. Validation findings are `validate`'s result, so they stay
# on stdout even when the exit code is 1. `init`'s half lives in test_init.py.


class _FakeServer:
    """A bound server that returns from `serve_forever` at once, as Ctrl-C does."""

    server_address = ("127.0.0.1", 7777)

    def serve_forever(self):
        raise KeyboardInterrupt

    def server_close(self):
        pass


def test_prompt_stdout_is_exactly_the_rendered_prompt(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    state = conductor.__main__._merged_state(store.load(root))
    assert captured.out == prompts.role_prompt(state, "reviewer")
    assert captured.err == ""


def test_prompt_stdout_has_no_trailing_blank_line(tmp_path, capsys):
    # role_prompt() already ends in a newline, so print() added a second one
    # and every redirected prompt carried a stray blank line.
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_prompt_deprecation_warning_never_reaches_stdout(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "reviewer", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert "deprecated" in captured.err and "deprecated" not in captured.out


@pytest.mark.parametrize("argv, scaffolded", [
    (["prompt", "--role", "reviewer"], False),                   # no conductor/
    (["prompt", "--role", "ghost"], True),                       # unknown role
    (["prompt", "--role", "reviewer", "--author", "bad name"], True),
    (["prompt", "--role", "reviewer"], True),                    # broken map
])
def test_operational_errors_leave_stdout_empty(tmp_path, capsys, argv, scaffolded):
    broken = argv == ["prompt", "--role", "reviewer"] and scaffolded
    root = tmp_path
    if scaffolded:
        root = write_project(tmp_path,
                             map_toml="= not toml" if broken else MAP_WITH_ROLES)
    assert main([*argv, "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err != ""


def test_validate_findings_are_the_result_and_stay_on_stdout(tmp_path, capsys):
    # Deliberate exception: what validate found IS what validate is for, so it
    # belongs on stdout even though the command failed.
    root = write_project(tmp_path, lanes={"bad": "{not json"})
    assert main(["validate", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert "bad" in captured.out and captured.err == ""


def test_validate_on_a_clean_project_writes_zero_bytes(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["validate", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_validate_load_error_is_stderr_with_empty_stdout(tmp_path, capsys):
    # A missing conductor/ is not a finding about the project — it is the
    # command failing to run at all.
    assert main(["validate", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "conductor" in captured.err


def test_up_stdout_is_exactly_the_url(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("conductor.server.build", lambda *a, **k: _FakeServer())
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["up", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "http://127.0.0.1:7777/\n"    # pipeable, on its own
    assert "Ctrl+C" in captured.err


def test_demo_stdout_is_the_url_and_the_temp_path_is_not(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("conductor.server.build", lambda *a, **k: _FakeServer())
    assert main(["demo"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "http://127.0.0.1:7777/\n"
    assert "materialized" in captured.err and "materialized" not in captured.out


def test_up_bind_failure_leaves_stdout_empty(tmp_path, capsys, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("address already in use")

    monkeypatch.setattr("conductor.server.build", refuse)
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["up", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "cannot serve" in captured.err


def test_demo_rejects_dir_flag(capsys):
    # Pin: demo materializes its own throwaway root — --dir is deliberately
    # not accepted (argparse usage error, exit 2). Demo behavior itself is
    # covered in tests/test_demo.py.
    with pytest.raises(SystemExit) as e:
        main(["demo", "--dir", "."])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err
