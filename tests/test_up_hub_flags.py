"""The hub flags of `conduct up` and the refusals of a start (spec 4.1.4, 4.1.5, 4.1.13 item 2).

Three layers, each judged where it is cheapest to be exact. The flag table is pure:
`up_flags.settle` over the real parser, no process. The refusal contract (exit 1,
ONE stderr line, no traceback, `state="refused"`) is read from `main` in process,
with `server.build` replaced by a function that fails the test if it is reached, so
"before any IO" is a measured claim. A handful of real processes then confirm the
contract survives an interpreter: nothing else can show that no traceback escapes.

Not here on purpose: the child-side kill-on-close job check (with the supervisor,
4.1.13 item 3).
"""
from __future__ import annotations

import errno
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import conductor
from conductor import server, store, up_flags
from conductor.__main__ import _build_parser, main
from conductor.command import operator_config
from conductor.ownership_errors import OwnerRefused
from conductor.store import StoreError
from tests._drain_harness import DrainProject
from tests.test_store import good_lane, write_project

GOOD_ID = "3f9c0d5a7b2e4c168a90d3e1f4b7a625"
OTHER_ID = "8a41b6e2c9d04f7385e1a2b6c0d94f13"
ORIGIN = "http://127.0.0.1:7700"
TRANSITION = "b71e4d09-c2a8-4f35-a6d8-1c0e9f3b5274"
SOURCE_ROOT = Path(conductor.__file__).resolve().parents[1]
CODE_TABLE = {
    "hub_flags_incomplete", "project_id_invalid", "hub_origin_invalid",
    "status_file_invalid", "stdin_is_terminal", "mode_invalid",
    "project_identity_changed", "hub_in_kill_on_close_job", "owner_busy",
    "recovery_required", "ownership_lost", "transition_conflict",
    "ownership_unavailable", "store_error", "providers_invalid", "bind_failed",
    "start_failed"}


class Reached(Exception):
    """`server.build` was called: every check that comes before it has passed."""


def _never_build(*args, **kwargs):
    raise Reached("server.build was reached")


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "home"
    (folder / "run").mkdir(parents=True)
    monkeypatch.setenv("CONDUCT_HOME", str(folder))
    return folder


def _hub(home: Path, project_id: str = GOOD_ID) -> list[str]:
    return ["--project-id", project_id, "--hub-origin", ORIGIN,
            "--status-file", str(home / "run" / f"{project_id}.json"), "--stop-on-stdin-eof"]


def _plan(argv: list[str], *, tty: bool = False) -> up_flags.UpPlan:
    args = _build_parser().parse_args(["up", "--dir", ".", *argv])
    return up_flags.settle(args, stdin_isatty=lambda: tty)


def _code(argv: list[str], *, tty: bool = False) -> str:
    with pytest.raises(up_flags.UpRefusal) as caught:
        _plan(argv, tty=tty)
    return caught.value.code


def _without(argv: list[str], flag: str) -> list[str]:
    """`argv` minus one flag and its value (or the bare switch)."""
    at = argv.index(flag)
    width = 1 if flag == "--stop-on-stdin-eof" else 2
    return argv[:at] + argv[at + width:]


# -- the table of 4.1.4 -----------------------------------------------------------


def test_the_closed_code_table_is_exactly_the_child_rows_of_section_4_1_5():
    assert up_flags.START_CODES == CODE_TABLE


def test_a_start_without_hub_flags_settles_to_the_standalone_plan():
    plan = _plan([])
    assert plan == up_flags.STANDALONE
    assert plan.mode == "active" and plan.hub_origin is None and not plan.stop_on_stdin_eof


def test_a_full_hub_command_line_settles_with_every_value_kept(home):
    plan = _plan([*_hub(home), "--mode", "active", "--transition", TRANSITION,
                  "--auto-continue", f"{TRANSITION}@3"])
    assert (plan.project_id, plan.hub_origin, plan.mode) == (GOOD_ID, ORIGIN, "active")
    assert plan.status_file == home / "run" / f"{GOOD_ID}.json"
    assert plan.stop_on_stdin_eof and plan.transition == TRANSITION
    assert plan.auto_continue == f"{TRANSITION}@3"


def test_a_project_id_alone_is_allowed_for_a_standalone_up():
    assert _plan(["--project-id", GOOD_ID]).project_id == GOOD_ID


@pytest.mark.parametrize("value", [
    "", GOOD_ID.upper(), GOOD_ID[:31], GOOD_ID + "0", "g" * 32, GOOD_ID + "\n",
    " " + GOOD_ID, "0x" + GOOD_ID[:30], "-".join([GOOD_ID[:8], GOOD_ID[8:]])])
def test_a_project_id_that_is_not_32_lowercase_hex_is_refused(value):
    assert _code(["--project-id", value]) == "project_id_invalid"


@pytest.mark.parametrize("value", [
    "http://localhost:7700", "https://127.0.0.1:7700", "http://127.0.0.1:7700/",
    "http://127.0.0.1:7700/hub", "http://127.0.0.1:07700", "http://127.0.0.1:0",
    "http://127.0.0.1:65536", "http://127.0.0.1:100000", "http://127.0.0.2:7700",
    "http://127.0.0.1", "HTTP://127.0.0.1:7700", "http://127.0.0.1:7700 ", "",
    "http://[::1]:7700", "http://user@127.0.0.1:7700", "http://127.0.0.1:7700?x=1"])
def test_every_refused_spelling_of_the_hub_origin_is_refused(home, value):
    argv = _hub(home)
    argv[argv.index("--hub-origin") + 1] = value
    assert _code(argv) == "hub_origin_invalid"


@pytest.mark.parametrize("port", ["1", "7700", "65535"])
def test_the_hub_origin_accepts_a_loopback_literal_and_a_port_up_to_65535(home, port):
    argv = _hub(home)
    argv[argv.index("--hub-origin") + 1] = f"http://127.0.0.1:{port}"
    assert _plan(argv).hub_origin == f"http://127.0.0.1:{port}"


def _with_status(home: Path, name: str) -> list[str]:
    argv = _hub(home)
    argv[argv.index("--status-file") + 1] = name
    return argv


def test_a_relative_status_file_is_refused(home):
    assert _code(_with_status(home, f"run/{GOOD_ID}.json")) == "status_file_invalid"


def test_a_status_file_named_for_another_project_is_refused(home):
    assert _code(_with_status(home, str(home / "run" / f"{OTHER_ID}.json"))) \
        == "status_file_invalid"
    assert _code(_with_status(home, str(home / "run" / "status.json"))) == "status_file_invalid"


@pytest.mark.parametrize("parent", ["", "runs", "run/sub", ".."])
def test_a_status_file_outside_the_run_folder_of_the_home_is_refused(home, tmp_path, parent):
    target = (home / parent / f"{GOOD_ID}.json") if parent != ".." \
        else (tmp_path / f"{GOOD_ID}.json")
    assert _code(_with_status(home, str(target))) == "status_file_invalid"


def test_resolved_paths_are_compared_so_a_dotdot_spelling_of_the_right_parent_passes(home):
    spelled = str(home / "run" / ".." / "run" / f"{GOOD_ID}.json")
    assert _plan(_with_status(home, spelled)).project_id == GOOD_ID


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive volumes only")
def test_a_status_file_that_differs_only_in_letter_case_passes_on_windows(home):
    spelled = str(home / "RUN" / f"{GOOD_ID}.json")
    assert _plan(_with_status(home, spelled)).project_id == GOOD_ID


def test_a_relative_conduct_home_makes_the_status_file_check_refuse(home, monkeypatch):
    monkeypatch.setenv("CONDUCT_HOME", "relative")
    assert _code(_hub(home)) == "status_file_invalid"


def test_an_stdin_that_is_a_terminal_is_refused_only_when_the_flag_asks_to_watch_it(home):
    assert _code(_hub(home), tty=True) == "stdin_is_terminal"
    assert _plan(["--project-id", GOOD_ID], tty=True).project_id == GOOD_ID


@pytest.mark.parametrize("value", ["", "Active", "both", "views", " view"])
def test_a_mode_outside_active_or_view_is_refused(home, value):
    assert _code([*_hub(home), "--mode", value]) == "mode_invalid"


def test_a_mode_given_twice_is_not_exactly_one_value(home):
    assert _code([*_hub(home), "--mode", "active", "--mode", "active"]) == "mode_invalid"


def test_mode_view_is_settled_with_the_hub_flags_and_active_is_the_default(home):
    assert _plan([*_hub(home), "--mode", "view"]).mode == "view"
    assert _plan(_hub(home)).mode == "active"


def test_mode_view_without_the_hub_flags_is_hub_flags_incomplete():
    assert _code(["--mode", "view"]) == "hub_flags_incomplete"
    assert _code(["--project-id", GOOD_ID, "--mode", "view"]) == "hub_flags_incomplete"


@pytest.mark.parametrize("dropped", ["--hub-origin", "--status-file", "--stop-on-stdin-eof",
                                     "--project-id"])
def test_the_hub_set_is_all_or_nothing_and_needs_the_project_id(home, dropped):
    assert _code(_without(_hub(home), dropped)) == "hub_flags_incomplete"


@pytest.mark.parametrize("keep", ["--hub-origin", "--status-file", "--stop-on-stdin-eof"])
def test_one_hub_flag_alone_is_hub_flags_incomplete(home, keep):
    whole = _hub(home)
    at = whole.index(keep)
    argv = [keep] if keep == "--stop-on-stdin-eof" else whole[at:at + 2]
    assert _code(argv) == "hub_flags_incomplete"


def test_a_transition_needs_the_hub_flags_and_mode_active(home):
    assert _code(["--transition", TRANSITION]) == "hub_flags_incomplete"
    assert _code([*_hub(home), "--mode", "view", "--transition", TRANSITION]) \
        == "hub_flags_incomplete"
    assert _plan([*_hub(home), "--transition", TRANSITION]).transition == TRANSITION


def test_an_auto_continue_flag_needs_a_transition(home):
    assert _code([*_hub(home), "--auto-continue", f"{TRANSITION}@3"]) == "hub_flags_incomplete"


@pytest.mark.parametrize("value", ["", "abc", TRANSITION.upper(), TRANSITION[:-1],
                                   TRANSITION + "0"])
def test_a_transition_that_is_not_a_lowercase_uuid_is_refused_naming_the_flag(home, value):
    with pytest.raises(up_flags.UpRefusal) as caught:
        _plan([*_hub(home), "--transition", value])
    assert caught.value.code == "hub_flags_incomplete" and "--transition" in caught.value.detail


@pytest.mark.parametrize("value", ["", TRANSITION, f"{TRANSITION}@", f"{TRANSITION}@0",
                                   f"{TRANSITION}@-1", f"{TRANSITION}@01", f"x@1",
                                   f"{TRANSITION}@1@2"])
def test_an_auto_continue_that_is_not_flag_id_at_revision_is_refused_naming_the_flag(
        home, value):
    with pytest.raises(up_flags.UpRefusal) as caught:
        _plan([*_hub(home), "--transition", TRANSITION, "--auto-continue", value])
    assert caught.value.code == "hub_flags_incomplete"
    assert "--auto-continue" in caught.value.detail


def test_the_flags_are_judged_in_the_documented_order(home):
    """Mode value, then completeness, then the values in the order of the table."""
    assert _code(["--mode", "nope", "--hub-origin", "bad"]) == "mode_invalid"
    assert _code(["--hub-origin", "https://bad"]) == "hub_flags_incomplete"
    assert _code(["--project-id", "BAD", "--mode", "view"]) == "hub_flags_incomplete"
    argv = _hub(home, "not-an-id")
    assert _code(argv) == "project_id_invalid"
    argv = _with_status(home, "relative")
    argv[argv.index("--hub-origin") + 1] = "bad"
    assert _code(argv) == "hub_origin_invalid"


# -- the refusal contract, read from `main` ---------------------------------------


def _up(tmp_path: Path, argv: list[str], capsys, monkeypatch):
    monkeypatch.setattr("conductor.server.build", _never_build)
    root = write_project(tmp_path / "plain", lanes={"claude": good_lane()})
    code = main(["up", "--dir", str(root), "--port", "0", *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _status(home: Path, project_id: str = GOOD_ID) -> dict | None:
    path = home / "run" / f"{project_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@pytest.mark.parametrize("extra, code", [
    (["--mode", "both"], "mode_invalid"),
    (["--transition", "nope"], "hub_flags_incomplete"),
])
def test_a_refused_flag_is_one_stderr_line_exit_1_and_a_refused_record(
        tmp_path, capsys, monkeypatch, home, extra, code):
    exit_code, out, err = _up(tmp_path, [*_hub(home), *extra], capsys, monkeypatch)
    assert exit_code == 1 and out == ""
    lines = err.splitlines()
    assert len(lines) == 1 and lines[0].startswith(f"conduct up: refused {code}: ")
    record = _status(home)
    assert record["state"] == "refused" and record["code"] == code
    assert record["mode"] is None if code == "mode_invalid" else record["mode"] == "active"


def test_a_refusal_caused_by_the_status_file_flag_itself_writes_no_record(
        tmp_path, capsys, monkeypatch, home):
    argv = _with_status(home, str(home / "run" / f"{OTHER_ID}.json"))
    exit_code, out, err = _up(tmp_path, argv, capsys, monkeypatch)
    assert exit_code == 1 and out == ""
    assert err.startswith("conduct up: refused status_file_invalid: ")
    assert list((home / "run").iterdir()) == []


def test_a_terminal_stdin_is_refused_before_anything_is_built(
        tmp_path, capsys, monkeypatch, home):
    monkeypatch.setattr(sys, "stdin", type("Tty", (), {"isatty": lambda self: True})())
    exit_code, _, err = _up(tmp_path, _hub(home), capsys, monkeypatch)
    assert exit_code == 1 and err.startswith("conduct up: refused stdin_is_terminal: ")
    assert _status(home)["code"] == "stdin_is_terminal"


def test_a_refusal_line_never_carries_a_second_line_of_detail():
    line = up_flags.refusal_line("start_failed", "first\nsecond\r\n  third")
    assert line == "conduct up: refused start_failed: first second third"


def test_mode_view_reaches_build_as_a_view_launch_and_the_status_file_says_view(
        tmp_path, monkeypatch):
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    seen: list[dict] = []
    monkeypatch.setattr("conductor.server.build", _spying_build(seen))
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0",
              *_hub(project.home, project.project_id), "--mode", "view"])
    from conductor.command.project_claim import Launch
    assert [call["launch"] for call in seen] == [Launch("view", False, None, None)]
    record = _status(project.home, project.project_id)
    assert (record["state"], record["mode"]) == ("starting", "view")


# -- identity: the nonce of the folder must be the one the hub was told -----------


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


def test_a_folder_that_is_not_activated_is_refused_project_identity_changed_before_build(
        tmp_path, capsys, monkeypatch, home):
    exit_code, out, err = _up(tmp_path, _hub(home), capsys, monkeypatch)
    assert exit_code == 1 and out == ""
    assert err.startswith("conduct up: refused project_identity_changed: ")
    record = _status(home)
    assert record["state"] == "refused" and record["code"] == "project_identity_changed"


def test_another_nonce_is_refused_project_identity_changed_and_writes_no_ownership_record(
        tmp_path, capsys, monkeypatch):
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    monkeypatch.setattr("conductor.server.build", _never_build)
    before = _tree_bytes(project.root)
    argv = _hub(project.home, OTHER_ID)
    code = main(["up", "--dir", str(project.root), "--port", "0", *argv])
    err = capsys.readouterr().err
    assert code == 1 and err.startswith("conduct up: refused project_identity_changed: ")
    assert before and _tree_bytes(project.root) == before
    assert project.head_phase() == "active"


def _spying_build(seen: list[dict]):
    def build(*args, **kwargs):
        seen.append(kwargs)
        raise Reached("server.build was reached")
    return build


def test_the_settled_hub_origin_reaches_build_and_a_standalone_up_passes_none(
        tmp_path, monkeypatch):
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    seen: list[dict] = []
    monkeypatch.setattr("conductor.server.build", _spying_build(seen))
    hub = _hub(project.home, project.project_id)
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0", *hub])
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0"])
    assert [call["hub_origin"] for call in seen] == [ORIGIN, None]


def test_the_launch_facts_of_the_plan_reach_build_and_a_standalone_up_launches_plain(
        tmp_path, monkeypatch):
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    seen: list[dict] = []
    monkeypatch.setattr("conductor.server.build", _spying_build(seen))
    handover = ["--mode", "active", "--transition", TRANSITION,
                "--auto-continue", "6d0f2c1a-3b4e-4f5a-8b9c-0d1e2f3a4b5c@3"]
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0",
              *_hub(project.home, project.project_id), *handover])
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0"])
    from conductor.command.project_claim import Launch
    assert [call["launch"] for call in seen] == [
        Launch("active", False, TRANSITION, "6d0f2c1a-3b4e-4f5a-8b9c-0d1e2f3a4b5c@3"),
        Launch("active", False, None, None)]


def test_up_asks_build_to_confirm_the_project_id_and_a_standalone_up_asks_for_none(
        tmp_path, monkeypatch):
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    seen: list[dict] = []
    monkeypatch.setattr("conductor.server.build", _spying_build(seen))
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0",
              *_hub(project.home, project.project_id)])
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0"])
    assert [call["expected_project_id"] for call in seen] == [project.project_id, None]


def test_a_root_taken_over_between_the_check_and_the_hold_is_refused_on_one_line_and_closed(
        tmp_path, monkeypatch, capsys):
    from conductor import ownership
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    monkeypatch.setattr(ownership.ProjectOwner, "project_id", property(lambda self: OTHER_ID))
    code = main(["up", "--dir", str(project.root), "--port", "0",
                 *_hub(project.home, project.project_id)])
    err = capsys.readouterr().err
    assert code == 1 and len(err.splitlines()) == 1
    assert err.startswith("conduct up: refused project_identity_changed: ")
    assert json.loads(project.status_file.read_text(encoding="utf-8"))["state"] == "refused"
    assert project.head_phase() == "closed"          # the owner opened, saw, and let go


def test_the_matching_nonce_passes_the_identity_check_and_reaches_build(
        tmp_path, monkeypatch):
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    monkeypatch.setattr("conductor.server.build", _never_build)
    argv = _hub(project.home, project.project_id)
    with pytest.raises(Reached):
        main(["up", "--dir", str(project.root), "--port", "0", *argv])
    assert _status(project.home, project.project_id)["state"] == "starting"


# -- the table of 4.1.5, one exception at a time ----------------------------------


def _raising(error: BaseException):
    def build(*args, **kwargs):
        raise error
    return build


OWNER_ROWS = [("owner_busy", "owner_busy"), ("recovery_required", "recovery_required"),
              ("ownership_lost", "ownership_lost"),
              ("transition_conflict", "transition_conflict"),
              ("ownership_unavailable", "ownership_unavailable"),
              ("login_recovery_required", "start_failed")]


@pytest.fixture
def activated(tmp_path, monkeypatch) -> DrainProject:
    """An activated project and its home, with the identity check ready to pass."""
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    return project


def _up_activated(project: DrainProject, capsys, *, port: int = 0) -> tuple[int, str]:
    argv = _hub(project.home, project.project_id)
    code = main(["up", "--dir", str(project.root), "--port", str(port), *argv])
    return code, capsys.readouterr().err


def _record(project: DrainProject) -> dict:
    return _status(project.home, project.project_id)


@pytest.mark.parametrize("raised, code", OWNER_ROWS)
def test_an_owner_refusal_keeps_its_code_and_an_unknown_one_is_start_failed(
        capsys, monkeypatch, activated, raised, code):
    monkeypatch.setattr("conductor.server.build", _raising(OwnerRefused(raised, "why")))
    exit_code, err = _up_activated(activated, capsys)
    assert exit_code == 1 and len(err.splitlines()) == 1
    assert err.startswith(f"conduct up: refused {code}: ") and "Traceback" not in err
    record = _record(activated)
    assert record["state"] == "refused" and record["code"] == code


def test_a_store_error_from_build_is_store_error(capsys, monkeypatch, activated):
    monkeypatch.setattr("conductor.server.build", _raising(StoreError("no conductor/ here")))
    exit_code, err = _up_activated(activated, capsys)
    assert exit_code == 1 and err == "conduct up: refused store_error: no conductor/ here\n"
    assert _record(activated)["code"] == "store_error"


def test_a_broken_provider_file_is_providers_invalid_and_names_the_file(
        capsys, monkeypatch, activated):
    monkeypatch.setattr("conductor.server.build", _never_build)
    broken = operator_config.provider_config_path(store.conductor_dir(activated.root))
    broken.write_text("{ not json", encoding="utf-8")
    exit_code, err = _up_activated(activated, capsys)
    assert exit_code == 1 and len(err.splitlines()) == 1
    assert err.startswith("conduct up: refused providers_invalid: ") and str(broken) in err
    assert _record(activated)["code"] == "providers_invalid"


def test_a_bind_error_from_build_is_bind_failed_with_the_old_words_and_the_port_flag(
        capsys, monkeypatch, activated):
    busy = server.ServerBindError(errno.EADDRINUSE, "address already in use")
    monkeypatch.setattr("conductor.server.build", _raising(busy))
    exit_code, err = _up_activated(activated, capsys, port=7901)
    assert exit_code == 1
    assert err.startswith("conduct up: refused bind_failed: cannot serve on 127.0.0.1:7901")
    assert "address already in use" in err and "--port PORT" in err
    assert _record(activated)["code"] == "bind_failed"


def test_an_oserror_that_is_not_the_bind_is_start_failed_and_names_no_port_flag(
        capsys, monkeypatch, activated):
    monkeypatch.setattr("conductor.server.build",
                        _raising(OSError("the run store could not be created")))
    exit_code, err = _up_activated(activated, capsys, port=7901)
    assert exit_code == 1 and len(err.splitlines()) == 1
    assert err.startswith("conduct up: refused start_failed: ")
    assert "the run store could not be created" in err and "--port" not in err
    assert _record(activated)["code"] == "start_failed"


def test_a_status_file_that_cannot_be_written_is_start_failed_on_one_line(
        tmp_path, capsys, monkeypatch, home):
    monkeypatch.setattr("conductor.server.build", _never_build)

    def refuse_every_write(path, payload, **options):
        raise PermissionError(13, "the run folder is read-only")

    monkeypatch.setattr("conductor.atomic_replace.replace_bytes", refuse_every_write)
    root = write_project(tmp_path / "plain", lanes={"claude": good_lane()})
    assert main(["up", "--dir", str(root), "--port", "0", *_hub(home)]) == 1
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1 and "refused start_failed" in err
    assert "read-only" in err and "could not be written" in err


# -- real processes: nothing can show "no traceback" but an interpreter -----------


def _run(argv: list[str], home: Path | None, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(SOURCE_ROOT), PYTHONDONTWRITEBYTECODE="1")
    env.pop("CONDUCT_HOME", None)
    if home is not None:
        env["CONDUCT_HOME"] = str(home)
    return subprocess.run([sys.executable, "-m", "conductor", "up", *argv], env=env,
                          cwd=cwd, stdin=subprocess.PIPE if home else subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=90)


def _one_refusal(done: subprocess.CompletedProcess, code: str) -> None:
    assert done.returncode == 1, done.stderr
    assert done.stdout == ""
    lines = done.stderr.splitlines()
    assert len(lines) == 1 and "Traceback" not in done.stderr
    assert lines[0].startswith(f"conduct up: refused {code}: "), lines[0]


@pytest.mark.parametrize("mutate, code", [
    (lambda argv: [*argv, "--mode", "both"], "mode_invalid"),
    (lambda argv: _without(argv, "--hub-origin"), "hub_flags_incomplete"),
    (lambda argv: [*_without(argv, "--project-id"), "--project-id", "BAD"],
     "project_id_invalid"),
    (lambda argv: [*_without(argv, "--hub-origin"), "--hub-origin", "http://localhost:7700"],
     "hub_origin_invalid"),
    (lambda argv: [*_without(argv, "--status-file"), "--status-file", "relative.json"],
     "status_file_invalid"),
])
def test_a_real_process_refuses_each_flag_code_on_one_line(tmp_path, home, mutate, code):
    root = write_project(tmp_path / "plain", lanes={"claude": good_lane()})
    done = _run(["--dir", str(root), "--port", "0", *mutate(_hub(home))], home, tmp_path)
    _one_refusal(done, code)


def test_a_real_process_refuses_an_unactivated_folder_and_leaves_a_refused_record(
        tmp_path, home):
    root = write_project(tmp_path / "plain", lanes={"claude": good_lane()})
    done = _run(["--dir", str(root), "--port", "0", *_hub(home)], home, tmp_path)
    _one_refusal(done, "project_identity_changed")
    record = _status(home)
    assert record["state"] == "refused" and record["code"] == "project_identity_changed"
    assert record["pid"] != os.getpid()


def test_a_real_process_on_a_busy_port_refuses_bind_failed_on_one_line(tmp_path):
    root = write_project(tmp_path / "plain", lanes={"claude": good_lane()})
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            blocker.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        done = _run(["--dir", str(root), "--port", str(port)], None, tmp_path)
    finally:
        blocker.close()
    _one_refusal(done, "bind_failed")
    assert f"127.0.0.1:{port}" in done.stderr and "--port PORT" in done.stderr


def test_a_real_process_with_a_broken_provider_file_refuses_providers_invalid(tmp_path):
    root = write_project(tmp_path / "plain", lanes={"claude": good_lane()})
    (root / "conductor" / "providers.json").write_text("{ nope", encoding="utf-8")
    _one_refusal(_run(["--dir", str(root), "--port", "0"], None, tmp_path), "providers_invalid")


def test_a_real_process_pointed_at_a_folder_without_conductor_refuses_store_error(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    _one_refusal(_run(["--dir", str(empty), "--port", "0"], None, tmp_path), "store_error")
