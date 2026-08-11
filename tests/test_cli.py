"""Tests for conductor.__main__ — the `conduct` CLI.

Every test but two calls `main(argv)` directly and inspects the return code
plus capsys-captured stdout/stderr. The exceptions spawn a real child process
because what they pin cannot exist under capsys:
`test_up_flushes_the_url_while_it_is_still_serving` (a block-buffered stdout
holding the URL until the server stops) and
`test_up_on_a_genuinely_busy_port_prints_the_port_hint_from_a_real_process`
(the bind failure and its message produced by the OS, not by a mock). Adding
another subprocess test should need the same justification: they are slower,
and they can hang where an in-process test merely fails.

The stream contract these tests enforce is stated in `conductor.__main__`'s
module docstring; the contract section below is its enforcement.
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone

import pytest
import conductor.__main__
from conductor import prompts, report, store, validate
from conductor.__main__ import main
from conductor.command.contracts import ActionProposal, canonical_json
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


@pytest.mark.parametrize("argv", [
    ["prompt"],                                   # no role at all
    ["prompt", "scout", "--role", "scout"],       # both spellings at once
])
def test_a_prompt_usage_error_comes_from_the_prompt_subparser_not_the_top_level(
        argv, tmp_path, capsys):
    """The reader gets `prompt`'s own usage line, not the whole subcommand list.

    `_cmd_prompt` raises through the parser stored as `prompt_parser`. Binding
    that to the top-level parser still exits 2 with a usage line, so the suite
    stays green while the message loses --role/--author and gains the command
    list — this guards which parser reported it, not the sentence it chose.
    """
    with pytest.raises(SystemExit) as e:
        main([*argv, "--dir", str(tmp_path)])
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "conduct prompt: error:" in err
    assert "--role" in err and "--author" in err
    assert "{validate," not in err


# --- CMD-4 MAJOR-2: the Day-1 preview gate (create run -> propose dispatch -> inspect) ---
#
# `conduct preview` drives the fixed CommandService end to end from the CLI: it
# creates or opens a run with a frozen config and prints one dispatch proposal's
# canonical form for inspection. It prepares and executes nothing, and it honours
# the same stdout/stderr/exit-code contract as its neighbours.


def test_preview_creates_a_run_and_prints_a_canonical_dispatch_proposal(tmp_path, capsys):
    assert main(["preview", "--dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    out = captured.out
    assert out.endswith("\n") and out.count("\n") == 1  # one clean, redirectable line
    payload = json.loads(out)
    # It is a dispatch proposal for the configured instance, and its preview_digest
    # is a real digest of its own content: reconstructing the contract recomputes it.
    assert payload["capability"] == "dispatch"
    assert payload["instance_id"] == "claude-dev"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", payload["preview_digest"])
    assert canonical_json(ActionProposal.from_dict(payload)) == out.rstrip("\n")
    # The run and its proposal are durable under --dir; nothing was executed.
    records = tmp_path / "conductor" / "runs" / "preview-run" / "records.jsonl"
    assert records.is_file()


def test_preview_is_deterministic_across_reruns_and_fresh_directories(tmp_path, capsys):
    assert main(["preview", "--dir", str(tmp_path / "a")]) == 0
    first = capsys.readouterr().out
    # Re-running in the same dir opens the existing run and yields identical bytes.
    assert main(["preview", "--dir", str(tmp_path / "a")]) == 0
    assert capsys.readouterr().out == first
    # A fresh dir yields the very same canonical preview: nothing hidden leaks in.
    assert main(["preview", "--dir", str(tmp_path / "b")]) == 0
    assert capsys.readouterr().out == first


def test_preview_refuses_an_unknown_instance_on_stderr_with_empty_stdout(tmp_path, capsys):
    assert main(["preview", "--dir", str(tmp_path), "--instance", "ghost"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ghost" in captured.err


def test_preview_refuses_an_adapter_that_mismatches_the_frozen_binding(tmp_path, capsys):
    assert main(["preview", "--dir", str(tmp_path), "--adapter", "codex"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    # The refusal names the instance and the binding it violates, not the caller's word.
    assert "claude-dev" in captured.err and "codex" in captured.err


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
    state = validate.merged_state(store.load(root))
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


class _FrozenClock:
    """A `datetime` stand-in whose `now` never moves, so two merges agree.

    `generated_at` is the one field two merges of an unchanged project differ
    on, and comparing the command's stdout against a second merge is a byte
    comparison only if the clock holds still between them.
    """

    @staticmethod
    def now(tz=None):
        return datetime(2026, 7, 30, 12, 0, tzinfo=tz or timezone.utc)


def test_report_stdout_is_exactly_the_rendered_report(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(validate, "datetime", _FrozenClock)
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES,
                         lanes={"claude": good_lane()})
    assert main(["report", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out == report.render(validate.merged_state(store.load(root)))
    assert captured.err == ""


def test_report_stdout_has_no_trailing_blank_line(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["report", "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and not out.endswith("\n\n")


def test_report_without_a_conductor_directory_leaves_stdout_empty(tmp_path, capsys):
    assert main(["report", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err != ""


def test_report_dir_selects_which_project_is_reported(tmp_path, capsys):
    # `--dir` behaves as it does everywhere else: it chooses the project, and
    # the report follows it rather than describing the working directory.
    one = write_project(tmp_path / "one", map_toml=MAP_WITH_ROLES.replace(
        'project = "p"', 'project = "alpha"'))
    two = write_project(tmp_path / "two", map_toml=MAP_WITH_ROLES.replace(
        'project = "p"', 'project = "beta"'))
    assert main(["report", "--dir", str(one)]) == 0
    first = capsys.readouterr().out
    assert main(["report", "--dir", str(two)]) == 0
    second = capsys.readouterr().out
    assert first.splitlines()[0].endswith("alpha")
    assert second.splitlines()[0].endswith("beta")


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


def test_up_flushes_the_url_while_it_is_still_serving(tmp_path):
    # The one test here that needs a real child process. `capsys` cannot see
    # this defect: it does not buffer, and _FakeServer returns instead of
    # blocking. In the real thing stdout is block-buffered the moment it is
    # redirected — the very case the contract exists for — and the next
    # statement blocks in serve_forever(), so without flush=True the URL sits
    # in the buffer until the server stops and never arrives at all if the
    # server is killed. `conduct up | xargs open` would hang on an empty pipe.
    #
    # --port 0 lets the OS pick, so there is no free-port race. The read runs
    # on a thread with a timeout: unflushed, readline() blocks forever, and a
    # blocked reader must fail this test rather than hang the suite.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUNBUFFERED"}
    # stderr is captured, not discarded: an import error and an unflushed
    # build both present as twenty seconds of silence, and only stderr tells
    # them apart. Without it a broken environment reads as this exact defect.
    proc = subprocess.Popen(
        [sys.executable, "-m", "conductor", "up", "--dir", str(root), "--port", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    first: list[str] = []
    reader = threading.Thread(target=lambda: first.append(proc.stdout.readline()),
                              daemon=True)
    reader.start()
    reader.join(timeout=20)
    try:
        if not first:
            proc.terminate()          # unblocks the reader so stderr can be read
            assert first, ("no URL reached a redirected stdout in 20s; child "
                           f"stderr was: {proc.stderr.read()!r}")
        assert re.fullmatch(r"http://127\.0\.0\.1:\d+/", first[0].strip())
    finally:
        proc.terminate()
        reader.join(timeout=5)        # let the reader observe the closed pipe
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()               # never let cleanup mask a real assertion
        proc.stdout.close()
        proc.stderr.close()


def test_up_bind_failure_leaves_stdout_empty(tmp_path, capsys, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("address already in use")

    monkeypatch.setattr("conductor.server.build", refuse)
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["up", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "cannot serve" in captured.err


def test_up_bind_failure_names_the_requested_endpoint_and_the_port_flag(
        tmp_path, capsys, monkeypatch):
    # The error is the one place a person actually needs --port, so it must
    # carry: the endpoint the user asked for, the system's own reason, and the
    # literal `--port PORT` hint. The digit-set equality is the class guard:
    # stderr may name no number at all beyond the loopback address and the
    # port the user requested — a substituted default port and an invented
    # "free" alternative port both fail the same one assertion.
    def refuse(*args, **kwargs):
        raise OSError("address already in use")

    monkeypatch.setattr("conductor.server.build", refuse)
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["up", "--dir", str(root), "--port", "7901"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""                       # the stream contract holds
    assert "127.0.0.1:7901" in captured.err         # the endpoint actually asked for
    assert "address already in use" in captured.err  # the system error, verbatim
    assert "--port PORT" in captured.err            # placeholder, not a made-up number
    assert set(re.findall(r"\d+", captured.err)) == {"127", "0", "1", "7901"}


def test_demo_bind_failure_keeps_its_chatter_and_names_the_users_port(
        capsys, monkeypatch):
    # Same contract, reached through `demo`: the materialize note survives on
    # stderr, and the only port-shaped number anywhere on stderr is the one
    # the user passed. The class door is the up test's full digit-set
    # equality on the shared _serve; this looser case-insensitive scan
    # (numbers after `:` or `port `) is the demo-path net, tolerating the
    # digits of the throwaway temp path it must not red on.
    def refuse(*args, **kwargs):
        raise OSError("address already in use")

    monkeypatch.setattr("conductor.server.build", refuse)
    assert main(["demo", "--port", "7902"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "materialized" in captured.err
    assert "127.0.0.1:7902" in captured.err
    assert "--port PORT" in captured.err
    assert set(re.findall(r"(?:port\s+|:)(\d+)", captured.err,
                          flags=re.IGNORECASE)) == {"7902"}


def test_up_and_demo_reach_the_same_serve_function_with_the_users_port(
        tmp_path, capsys, monkeypatch):
    # The relation that keeps the two commands from drifting apart: one mock
    # of `_serve` intercepts both, so there is no second copy of the serving
    # (and failing) path for `demo` to take, and both hand it the port the
    # user typed rather than a default.
    calls = []

    def fake_serve(root, port):
        calls.append(port)
        return 23

    monkeypatch.setattr(conductor.__main__, "_serve", fake_serve)
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["up", "--dir", str(root), "--port", "7903"]) == 23
    assert main(["demo", "--port", "7904"]) == 23
    assert calls == [7903, 7904]


def test_up_on_a_genuinely_busy_port_prints_the_port_hint_from_a_real_process(tmp_path):
    # The second subprocess test this file allows itself, with the same kind
    # of justification as the flush test: the mocked tests above construct
    # their OSError, so only a real bind against a really occupied port can
    # prove the message a user sees is the one the mocks describe.
    #
    # SO_EXCLUSIVEADDRUSE hardens the fixture rather than enabling it:
    # ConductServer already keeps SO_REUSEADDR off on Windows (server.py)
    # precisely so a busy port refuses, so the child is refused either way.
    # Exclusivity makes the refusal deterministic regardless of the server's
    # socket options, keeping this test's premise intact even if that
    # design ever regressed.
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        proc = subprocess.run(
            [sys.executable, "-m", "conductor", "up", "--dir", str(root),
             "--port", str(port)],
            capture_output=True, text=True, timeout=60)
    finally:
        blocker.close()
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert f"127.0.0.1:{port}" in proc.stderr
    assert "--port PORT" in proc.stderr


def test_demo_rejects_dir_flag(capsys):
    # Pin: demo materializes its own throwaway root — --dir is deliberately
    # not accepted (argparse usage error, exit 2). Demo behavior itself is
    # covered in tests/test_demo.py.
    with pytest.raises(SystemExit) as e:
        main(["demo", "--dir", "."])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err
