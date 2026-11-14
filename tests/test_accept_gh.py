"""The pinned gh that an `active` child hands to the push and the pull request (spec 9.3, 8.8, 8.9).

A child started for viewing builds no reader. An `active` one hands over a reader that does
nothing until it is first asked: then it checks the pinned gh once, builds the environment of
8.9, makes the folder of its own under the owner's guard and builds one runner that may spawn.
In file order: the builder on fakes, the reasons the tool is not usable, and the real runner
over the real scripted executable.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from conductor import ownership, server, tool_env, tool_pins
from conductor.command import accept_gh
from conductor.command.project_claim import Launch
from conductor.hub import home as conduct_home
from tests import _fakegh
from tests.test_command_http_api import NOW, TOKEN
from tests.test_server_project_git import _stop as stop
from tests.test_store import good_lane, write_project

PINNED = tool_pins.ToolPin("gh", str(Path(sys.executable).resolve()), "2.50.0")
FOLDER = "C:\\hub-home" if os.name == "nt" else "/hub-home"
SOURCE = {"HOME": "/home/owner", "GH_TOKEN": "t-1", "GITHUB_TOKEN": "t-2", "GH_HOST": "h.example",
          "GIT_ASKPASS": "/bin/askpass", "GIT_DIR": "/elsewhere/.git"}


class Runners:
    """A stand-in for `ProcessRunner` that records how it was built and what it was asked."""

    def __init__(self, **outcome) -> None:
        self.built, self.specs = [], []
        self.outcome = {"status": "completed", "exit_code": 0, "output": b"ok\n",
                        "output_truncated": False, "output_contains_env_value": False, **outcome}

    def __call__(self, root, *, environ, spawns_allowed):
        self.built.append({"root": Path(root), "environ": environ, "spawns": spawns_allowed})
        return SimpleNamespace(run=self._run)

    def _run(self, spec):
        self.specs.append(spec)
        return SimpleNamespace(**self.outcome)


class Verifier:
    """`tool_pins.verify_pin` as a fake: answers the pin, or raises what it was told to."""

    def __init__(self, fault=None) -> None:
        self.fault, self.calls = fault, 0

    def __call__(self, tool, *, folder=None, run=None, source=None):
        self.calls += 1
        assert tool == "gh"
        if self.fault is not None:
            raise self.fault
        return PINNED


@pytest.fixture
def pins(monkeypatch):
    monkeypatch.setattr(tool_pins, "load_pins", lambda folder=None: tool_pins.ToolPins(gh=PINNED))


def root_of(tmp_path):
    return write_project(tmp_path, lanes={"claude": good_lane()})


def reader(root, runners, verifier=None, **changes):
    options = dict(source=SOURCE, folder=FOLDER, verify=verifier or Verifier(),
                   runner_class=runners)
    return accept_gh.project_gh_reader(root, **{**options, **changes})


def test_an_active_reader_has_done_nothing_before_its_first_call(tmp_path, pins):
    root, runners, verifier = root_of(tmp_path), Runners(), Verifier()
    gh = reader(root, runners, verifier)
    assert callable(gh)
    assert (verifier.calls, runners.built) == (0, [])
    assert not (ownership.data_root(root) / "git").exists()


def test_the_first_call_checks_the_pin_once_and_builds_one_runner_that_may_spawn(tmp_path, pins):
    root, runners, verifier = root_of(tmp_path), Runners(), Verifier()
    gh = reader(root, runners, verifier)
    for _ in range(3):
        answer = gh(["repo", "view", "o/r"])
        assert (answer.exit_code, answer.output) == (0, b"ok\n")
    assert verifier.calls == 1
    assert runners.built == [{"root": root.resolve(), "environ": {}, "spawns": True}]
    assert len(runners.specs) == 3


def test_a_call_runs_the_pinned_path_in_a_folder_beneath_the_root_with_stderr_kept_out(
        tmp_path, pins):
    root, runners = root_of(tmp_path), Runners()
    reader(root, runners)(["pr", "list"], stdin=b"in", timeout=7, output_limit=99)
    spec, = runners.specs
    cwd = Path(spec.cwd)
    assert spec.argv == (PINNED.path, "pr", "list")
    assert cwd == ownership.data_root(root) / "git" / "cwd" and cwd.is_dir()
    assert cwd.is_relative_to(root.resolve()) and cwd != root.resolve()
    assert (spec.separate_stderr, spec.stdin_bytes) == (True, b"in")
    assert (spec.timeout_seconds, spec.output_limit) == (7, 99)
    reader(root, runners)(["pr", "list"])
    assert (runners.specs[1].timeout_seconds, runners.specs[1].output_limit) == (
        accept_gh.TIMEOUT_SECONDS, accept_gh.OUTPUT_LIMIT)
    assert runners.specs[1].stdin_bytes is None


def test_the_environment_is_the_one_builder_of_spec_8_9_and_holds_no_token(tmp_path, pins):
    root, runners = root_of(tmp_path), Runners()
    reader(root, runners)(["repo", "view", "o/r"])
    spec, = runners.specs
    expected = tool_env.tool_env(SOURCE, tool_pins.ToolPins(gh=PINNED), FOLDER)
    assert dict(spec.env) == expected and spec.env_allow == ()
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "GIT_ASKPASS", "GIT_DIR"):
        assert name not in spec.env
    assert spec.env["GH_PROMPT_DISABLED"] == "1" and spec.env["GH_NO_UPDATE_NOTIFIER"] == "1"


def test_the_answer_says_when_the_call_timed_out_was_cut_or_carried_an_environment_value(
        tmp_path, pins):
    root = root_of(tmp_path)
    timed = reader(root, Runners(status="timed_out", exit_code=None))(["x"])
    assert (timed.timed_out, timed.exit_code) == (True, None)
    cut = reader(root, Runners(output_truncated=True))(["x"])
    assert cut.truncated is True and cut.timed_out is False
    hidden = reader(root, Runners(output_contains_env_value=True))(["x"])
    assert hidden.hidden is True


@pytest.mark.parametrize("code,reason", [
    ("gh_not_pinned", "not_pinned"), ("tools_file_invalid", "not_pinned"),
    ("tools_file_unreadable", "not_pinned"), ("gh_changed", "version_changed"),
    ("tool_version_unreadable", "missing"), ("tools_file_unwritable", "missing")])
def test_a_pin_that_cannot_be_used_says_why_in_the_three_words_of_spec_9_3(
        tmp_path, code, reason):
    root, runners = root_of(tmp_path), Runners()
    verifier = Verifier(tool_pins.ToolPinError(code, "refused"))
    gh = reader(root, runners, verifier)
    for _ in range(2):
        with pytest.raises(accept_gh.GhUnavailable) as caught:
            gh(["repo", "view", "o/r"])
        assert caught.value.reason == reason
    assert (verifier.calls, runners.built, runners.specs) == (1, [], [])
    assert not (ownership.data_root(root) / "git").exists()


def test_a_home_that_cannot_be_named_is_a_pin_that_is_not_there(tmp_path):
    def nowhere(tool, *, folder=None, run=None, source=None):
        raise conduct_home.ConductHomeInvalid("no home")

    with pytest.raises(accept_gh.GhUnavailable) as caught:
        reader(root_of(tmp_path), Runners(), nowhere)(["x"])
    assert caught.value.reason == "not_pinned"
    with pytest.raises(ValueError):
        accept_gh.GhUnavailable("unknown")


def test_a_working_folder_that_cannot_be_made_is_a_fault_to_try_again_not_a_verdict(
        tmp_path, pins, monkeypatch):
    root, runners = root_of(tmp_path), Runners()
    gh = reader(root, runners)
    real = Path.mkdir
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    with pytest.raises(OSError):
        gh(["x"])
    monkeypatch.setattr(Path, "mkdir", real)
    assert gh(["x"]).exit_code == 0


def test_the_real_runner_hands_stdin_to_the_pinned_gh_and_gives_it_nothing_of_the_owner(tmp_path):
    exe = _fakegh.build_executable(tmp_path / "bin")
    assert exe is not None
    tokens = {name: SOURCE[name] for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "GIT_ASKPASS")}
    owner = {**os.environ, **tokens, "GIT_DIR": SOURCE["GIT_DIR"],
             "PATH": str(tmp_path / "owner-bin") + os.pathsep + os.environ.get("PATH", "")}
    hub = tmp_path / "hub-home"
    hub.mkdir()
    tool_pins.pin_tool("gh", str(exe), folder=hub, source=owner)
    _fakegh.script(exe.parent, {"pr create": [_fakegh.created(5)]})
    answer = accept_gh.project_gh_reader(root_of(tmp_path / "project"), source=owner, folder=hub)(
        ["pr", "create", "--body-file", "-"], stdin="Body\nof the request\n".encode())
    assert (answer.exit_code, answer.output) == (0, b"https://github.com/o/r/pull/5\n")
    row, = _fakegh.calls(exe.parent)
    assert row["argv"] == ["pr", "create", "--body-file", "-"]
    assert row["stdin"] == "Body\nof the request\n"
    names = set(row["env_names"])
    assert not names & {"GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "GIT_ASKPASS", "GIT_DIR"}
    assert {"GH_PROMPT_DISABLED", "GH_NO_UPDATE_NOTIFIER", "NO_COLOR"} <= names
    folders = row["path"].split(os.pathsep)
    assert Path(folders[0]) == exe.parent and str(tmp_path / "owner-bin") not in folders


# -- the wiring of start_command --------------------------------------------------------


def serve(tmp_path, mode):
    subject = server.build(root_of(tmp_path), 0, registry=None, providers=(), clock=lambda: NOW,
                           token_factory=lambda _: TOKEN, launch=Launch(mode=mode))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    return subject, thread


def test_a_view_child_builds_no_gh_reader_passes_none_and_never_reads_the_pins(
        tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the pins were read, or a gh reader was built, for a view process")

    for target, name in ((tool_pins, "load_pins"), (tool_pins, "verify_pin"),
                         (accept_gh, "project_gh_reader")):
        monkeypatch.setattr(target, name, refuse)
    subject, thread = serve(tmp_path, "view")
    try:
        assert subject.command_api._project_gh is None
    finally:
        stop(subject, thread)


def test_start_command_hands_an_active_child_the_gh_reader_the_builder_made(
        tmp_path, monkeypatch):
    made = []

    def reader(args, **keywords):
        raise AssertionError("nothing asks gh here")

    def builder(root, **options):
        made.append(Path(root).resolve())
        return reader

    monkeypatch.setattr(accept_gh, "project_gh_reader", builder)
    subject, thread = serve(tmp_path, "active")
    try:
        assert subject.command_api._project_gh is reader
    finally:
        stop(subject, thread)
    assert made == [tmp_path.resolve()]
