"""The hub starts a project's child the way spec 4.1.4 says.

What is judged: the command line, exactly (the flags of the table, in that order, and the ones
that may not go together refused before anything starts); the command itself (`sys.executable
-m conductor`, never `conduct` from PATH); the shape of the start (a pipe the hub keeps and
writes nothing into, stdout discarded, stderr in the project's log with one rotation at start,
the hub's folder as the working folder and in the child's environment, no inherited handles, a
group or session of its own); the policy of the hub's own Windows job (a child breaks away when
the job allows it, and none is created when it does not); that the module has no `ProcessRunner`
and no job of its own; and one real child, the real `conduct up`, reaching `serving` and leaving
cleanly on the end of its stdin.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conductor import up_status
from conductor.hub import spawn
from tests._drain_harness import CHILD, WAIT, DrainProject, _kill_tree, wait_until

PROJECT_ID = "3f9c0d5a7b2e4c168a90d3e1f4b7a625"
ORIGIN = "http://127.0.0.1:7700"
TRANSITION = "11111111-1111-4111-8111-111111111111"
FLAG = "f1f1f1f1-f1f1-41f1-81f1-f1f1f1f1f1f1@3"


class Launches:
    """A `Popen` that records how it was called and starts nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, argv, **options):
        self.calls.append((list(argv), options))
        return _FakeProcess()


class _FakeProcess:
    pid = 4242
    stdin = None

    def poll(self):
        return None


def _spawner(tmp_path: Path, launches: Launches, **options) -> spawn.Spawner:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return spawn.Spawner(home, hub_origin=ORIGIN, popen=launches, **options)


def _start(spawner: spawn.Spawner, **changes):
    arguments = dict(project_id=PROJECT_ID, root=Path("/project"), port=7701, mode="active")
    return spawner.start(**{**arguments, **changes})


# -- the command line ---------------------------------------------------------------------------


def test_the_command_line_is_the_one_of_the_spec_in_the_order_of_its_table(tmp_path):
    launches = Launches()
    spawner = _spawner(tmp_path, launches)
    child = _start(spawner)
    status = str(tmp_path / "home" / "run" / f"{PROJECT_ID}.json")
    assert launches.calls[0][0] == [
        sys.executable, "-m", "conductor", "up", "--dir", str(Path("/project")), "--port", "7701",
        "--project-id", PROJECT_ID, "--hub-origin", ORIGIN, "--status-file", status,
        "--stop-on-stdin-eof", "--mode", "active"]
    assert child.argv == launches.calls[0][0] and child.project_id == PROJECT_ID


def test_the_command_is_this_interpreter_running_the_package_and_not_a_conduct_from_path(
        tmp_path):
    launches = Launches()
    _start(_spawner(tmp_path, launches))
    argv = launches.calls[0][0]
    assert argv[:3] == [sys.executable, "-m", "conductor"] and "conduct" not in argv[:1]


def test_a_transition_and_a_flag_are_added_last_and_only_when_given(tmp_path):
    launches = Launches()
    spawner = _spawner(tmp_path, launches)
    _start(spawner)
    _start(spawner, transition=TRANSITION)
    _start(spawner, transition=TRANSITION, auto_continue=FLAG)
    plain, with_transition, with_flag = (call[0] for call in launches.calls)
    assert "--transition" not in plain and "--auto-continue" not in plain
    assert with_transition[-2:] == ["--transition", TRANSITION]
    assert "--auto-continue" not in with_transition
    assert with_flag[-4:] == ["--transition", TRANSITION, "--auto-continue", FLAG]


def test_a_view_child_is_asked_for_view_with_the_same_flags(tmp_path):
    launches = Launches()
    _start(_spawner(tmp_path, launches), mode="view")
    argv = launches.calls[0][0]
    assert argv[argv.index("--mode") + 1] == "view" and "--transition" not in argv


@pytest.mark.parametrize("changes", [
    {"auto_continue": FLAG}, {"transition": TRANSITION, "mode": "view"}, {"mode": "passive"},
    {"project_id": "nope"}, {"port": -1}, {"port": 65536}, {"port": "7701"},
    {"transition": "not-a-uuid"}, {"transition": TRANSITION, "auto_continue": "flag"}],
    ids=["a flag without a transition", "a transition in view", "a mode off the list",
         "a project id off the grammar", "a port below zero", "a port over 65535",
         "a port that is text", "a transition that is not a uuid", "a flag off the grammar"])
def test_a_combination_the_child_would_refuse_is_refused_before_anything_starts(
        tmp_path, changes):
    launches = Launches()
    with pytest.raises(ValueError):
        _start(_spawner(tmp_path, launches), **changes)
    assert launches.calls == []


def test_a_hub_origin_that_is_not_the_loopback_origin_is_refused_when_the_spawner_is_made(
        tmp_path):
    for origin in ("http://localhost:7700", "http://127.0.0.1", "https://127.0.0.1:7700"):
        with pytest.raises(ValueError, match="hub_origin"):
            spawn.Spawner(tmp_path, hub_origin=origin, popen=Launches())


# -- the shape of the start ---------------------------------------------------------------------


def test_the_child_gets_a_pipe_the_hub_keeps_no_stdout_its_log_as_stderr_and_the_hubs_folder(
        tmp_path):
    launches = Launches()
    _start(_spawner(tmp_path, launches))
    options = launches.calls[0][1]
    assert options["stdin"] == subprocess.PIPE and options["stdout"] == subprocess.DEVNULL
    assert str(options["stderr"].name) == str(
        tmp_path / "home" / "logs" / f"{PROJECT_ID}.log")
    assert options["cwd"] == str(tmp_path / "home") and options["close_fds"] is True
    assert options.get("shell", False) is False
    assert options["env"]["CONDUCT_HOME"] == str(tmp_path / "home")


def test_the_spawner_closes_its_own_copy_of_the_log_so_the_child_alone_holds_it(tmp_path):
    launches = Launches()
    _start(_spawner(tmp_path, launches))
    assert launches.calls[0][1]["stderr"].closed


@pytest.mark.skipif(os.name != "nt", reason="the flags are Windows'")
def test_on_windows_the_child_has_a_group_of_its_own_and_no_window_and_does_not_break_away(
        tmp_path):
    launches = Launches()
    _start(_spawner(tmp_path, launches))
    flags = launches.calls[0][1]["creationflags"]
    assert flags & subprocess.CREATE_NEW_PROCESS_GROUP and flags & subprocess.CREATE_NO_WINDOW
    assert not flags & 0x01000000, "CREATE_BREAKAWAY_FROM_JOB without a reason"


@pytest.mark.skipif(os.name == "nt", reason="a session is POSIX's")
def test_on_posix_the_child_has_a_session_of_its_own(tmp_path):
    launches = Launches()
    _start(_spawner(tmp_path, launches))
    assert launches.calls[0][1]["start_new_session"] is True


def test_the_environment_passes_the_hubs_but_a_folder_the_caller_gave_wins(tmp_path):
    launches = Launches()
    spawner = _spawner(tmp_path, launches, environ={"PATH": "x", "CONDUCT_HOME": "elsewhere"})
    _start(spawner)
    env = launches.calls[0][1]["env"]
    assert env["PATH"] == "x" and env["CONDUCT_HOME"] == str(tmp_path / "home")


# -- the log, rotated once at every start ------------------------------------------------------


def test_the_previous_log_is_kept_once_as_dot_one_at_every_start(tmp_path):
    launches = Launches()
    spawner = _spawner(tmp_path, launches)
    logs = tmp_path / "home" / "logs"
    _start(spawner)
    (logs / f"{PROJECT_ID}.log").write_text("first run", encoding="utf-8")
    _start(spawner)
    assert (logs / f"{PROJECT_ID}.log.1").read_text(encoding="utf-8") == "first run"
    assert (logs / f"{PROJECT_ID}.log").read_text(encoding="utf-8") == ""
    (logs / f"{PROJECT_ID}.log").write_text("second run", encoding="utf-8")
    _start(spawner)
    assert (logs / f"{PROJECT_ID}.log.1").read_text(encoding="utf-8") == "second run"
    assert sorted(entry.name for entry in logs.iterdir()) == [
        f"{PROJECT_ID}.log", f"{PROJECT_ID}.log.1"]


# -- the policy of the hub's own job -------------------------------------------------------------


@pytest.mark.skipif(os.name != "nt", reason="a job is Windows'")
def test_in_a_job_that_allows_it_the_child_breaks_away(tmp_path):
    launches = Launches()
    _start(_spawner(tmp_path, launches, job_policy=lambda: "breakaway"))
    assert launches.calls[0][1]["creationflags"] & 0x01000000


def test_in_a_kill_on_close_job_nothing_is_started_and_the_code_is_the_spec_s(tmp_path):
    launches = Launches()
    with pytest.raises(spawn.SpawnRefused) as caught:
        _start(_spawner(tmp_path, launches, job_policy=lambda: "kill_on_close"))
    assert caught.value.code == "hub_in_kill_on_close_job" and launches.calls == []
    assert not (tmp_path / "home" / "logs").exists(), "a log was made for a child never started"


def test_a_job_policy_that_is_not_one_of_the_three_is_a_fault_of_the_caller(tmp_path):
    with pytest.raises(ValueError, match="job"):
        _start(_spawner(tmp_path, Launches(), job_policy=lambda: "maybe"))


def test_an_operating_system_that_cannot_start_the_process_is_start_failed(tmp_path):
    def cannot(argv, **options):
        raise FileNotFoundError("no interpreter")

    spawner = spawn.Spawner(tmp_path, hub_origin=ORIGIN, popen=cannot)
    with pytest.raises(spawn.SpawnRefused) as caught:
        _start(spawner)
    assert caught.value.code == "start_failed" and "no interpreter" in caught.value.detail


# -- what the module may not hold ------------------------------------------------------------------


def test_the_module_has_no_process_runner_no_job_of_its_own_and_no_command_package():
    tree = ast.parse(Path(spawn.__file__).read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names}
    imported |= {f"{'.' * node.level}{node.module}" for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom)}
    assert not names & {"ProcessRunner", "CreateJobObject", "CreateJobObjectW",
                        "SetInformationJobObject", "AssignProcessToJobObject"}, names
    assert not any("command" in name or "procgroup" in name for name in imported), imported


# -- one real child --------------------------------------------------------------------------------


def test_a_real_child_reaches_serving_and_leaves_cleanly_when_its_stdin_ends(tmp_path):
    project = DrainProject.build(tmp_path)
    environment = project._environment(False, None, None, "none", 0.0, None)
    spawner = spawn.Spawner(project.home, hub_origin=ORIGIN, head=(sys.executable, str(CHILD)),
                            environ=environment)
    child = spawner.start(project_id=project.project_id, root=project.root, port=0,
                          mode="active")
    try:
        def state():
            found = up_status.read_status(project.status_file)
            return None if found is None else found.state

        wait_until(lambda: state() == "serving", WAIT, "the real child to say serving")
        assert child.poll() is None
        child.close_stdin()
        assert child.wait(WAIT) == 0
        assert state() == "stopped"
        assert (project.home / "logs" / f"{project.project_id}.log").exists()
    finally:
        _kill_tree(child.popen)
