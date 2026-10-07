"""The project's git reader that an `active` child hands to the command API (spec 9.3, 8.8, 9.1.6).

A child started for viewing builds no reader at all and never looks at the pins: a view process
creates no child process, and a reader that existed would be a second place that could start
one. An `active` child hands over a reader that does nothing until it is first asked: then it
checks the pinned git once, builds the environment of 8.9, makes the folder of its own under
the owner's guard and builds one runner that may spawn. When the pin is not usable the reader
raises `ToolUnavailable` on every call, a `GitReadFailed` whose `code` is `tool_unavailable`
and whose `reason` is one of the three of 9.3, so lane L can say it without a new exception.

In file order: the builder on fakes (what it makes and when), the three reasons and the faults
that are not the tool's, the wiring of `server_command.start_command` in both modes, and one
real repository read through the real runner and a real pinned git.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest

from conductor import ownership, ownership_transition, server, server_git, tool_env, tool_pins
from conductor.command import project_git
from conductor.command.project_claim import Launch
from conductor.hub import home as conduct_home
from tests.git_repo_helpers import GIT, commit, needs_git, repository
from tests.test_command_http_api import NOW, TOKEN
from tests.test_server_command_http import _request
from tests.test_store import good_lane, write_project

PINNED = tool_pins.ToolPin("git", str(Path(sys.executable).resolve()), "2.47.1")
FOLDER = "C:\\hub-home" if os.name == "nt" else "/hub-home"
SOURCE = {"HOME": "/home/owner", "GIT_DIR": "/elsewhere/.git", "GH_TOKEN": "secret"}


class Runners:
    """A stand-in for `ProcessRunner` that records how it was built and what it was asked."""

    def __init__(self) -> None:
        self.built: list[dict] = []
        self.specs: list = []

    def __call__(self, root, *, environ, spawns_allowed):
        self.built.append({"root": Path(root), "spawns_allowed": spawns_allowed})
        return SimpleNamespace(run=self._run)

    def _run(self, spec):
        self.specs.append(spec)
        return SimpleNamespace(exit_code=0, output=b"ok\n", output_truncated=False,
                               status="completed")


class Verifier:
    """`tool_pins.verify_pin` as a fake: answers the pin, or raises what it was told to."""

    def __init__(self, fault: tool_pins.ToolPinError | None = None) -> None:
        self.fault, self.calls = fault, 0

    def __call__(self, tool, *, folder=None, run=None, source=None):
        self.calls += 1
        if self.fault is not None:
            raise self.fault
        return PINNED


@pytest.fixture
def pins(monkeypatch):
    """`tools.json` read as one git pin, in a home that is not the machine's."""
    monkeypatch.setattr(tool_pins, "load_pins", lambda folder=None: tool_pins.ToolPins(git=PINNED))


def _root(tmp_path: Path) -> Path:
    return write_project(tmp_path, lanes={"claude": good_lane()})


def _reader(root, runners, verifier=None, **changes):
    options = dict(source=SOURCE, folder=FOLDER, verify=verifier or Verifier(),
                   runner_class=runners)
    return server_git.project_git_reader(root, **{**options, **changes})


# -- the builder on fakes --------------------------------------------------------------


def test_an_active_reader_has_done_nothing_before_its_first_call(tmp_path, pins):
    root, runners, verifier = _root(tmp_path), Runners(), Verifier()
    reader = _reader(root, runners, verifier)
    assert callable(reader)
    assert (verifier.calls, runners.built) == (0, [])
    assert not (ownership.data_root(root) / "git").exists()


def test_the_first_call_checks_the_pin_once_and_builds_one_runner_that_may_spawn(tmp_path, pins):
    root, runners, verifier = _root(tmp_path), Runners(), Verifier()
    reader = _reader(root, runners, verifier)
    for _ in range(3):
        assert reader(["rev-parse", "HEAD"]).output == b"ok\n"
    assert verifier.calls == 1
    assert runners.built == [{"root": root.resolve(), "spawns_allowed": True}]
    assert len(runners.specs) == 3


def test_the_keywords_of_a_seed_read_reach_the_runner_as_the_specs_own_fields(tmp_path, pins):
    """`cat-file --batch` names its objects on stdin and answers with their bytes (spec 9.1.2)."""
    root, runners = _root(tmp_path), Runners()
    reader = _reader(root, runners)
    reader(["cat-file", "--batch"], True, stdin=b"abc\n", output_limit=4096, timeout=30)
    reader(["rev-parse", "HEAD"])
    batch, plain = runners.specs
    assert (batch.stdin_bytes, batch.output_limit, batch.timeout_seconds) == (b"abc\n", 4096, 30)
    assert (plain.stdin_bytes, plain.output_limit) == (None, project_git.READ_OUTPUT_LIMIT)


def test_the_command_runs_the_pinned_path_in_a_folder_of_its_own_beneath_the_root(tmp_path, pins):
    root, runners = _root(tmp_path), Runners()
    _reader(root, runners)(["rev-parse", "HEAD"], separate_stderr=True)
    spec = runners.specs[0]
    cwd = Path(spec.cwd)
    assert spec.argv[0] == PINNED.path and spec.argv[-2:] == ("rev-parse", "HEAD")
    assert cwd == ownership.data_root(root) / "git" / "cwd" and cwd.is_dir()
    assert cwd.is_relative_to(root.resolve()) and cwd != root.resolve()
    assert spec.separate_stderr is True


def test_the_environment_is_the_one_builder_of_spec_8_9_and_nothing_of_the_owners_git(
        tmp_path, pins):
    root, runners = _root(tmp_path), Runners()
    _reader(root, runners)(["status"])
    spec = runners.specs[0]
    expected = tool_env.tool_env(SOURCE, tool_pins.ToolPins(git=PINNED), FOLDER)
    assert dict(spec.env) == expected and spec.env_allow == ()
    assert "GIT_DIR" not in spec.env and "GH_TOKEN" not in spec.env
    assert spec.env["LC_ALL"] == "C" and spec.env["GIT_TERMINAL_PROMPT"] == "0"


# -- when the tool is not usable -------------------------------------------------------

REASONS = [
    ("git_not_pinned", "not_pinned"), ("tools_file_invalid", "not_pinned"),
    ("tools_file_unreadable", "not_pinned"),
    ("git_changed", "version_changed"), ("tool_version_unreadable", "missing")]


def test_a_tool_unavailable_is_a_git_read_failure_with_its_code_and_one_of_three_reasons():
    error = server_git.ToolUnavailable("missing")
    assert isinstance(error, project_git.GitReadFailed)
    assert (error.code, error.reason, error.exit_code) == ("tool_unavailable", "missing", None)
    assert server_git.REASONS == ("not_pinned", "version_changed", "missing")
    with pytest.raises(ValueError, match="reason"):
        server_git.ToolUnavailable("gone")


@pytest.mark.parametrize(("code", "reason"), REASONS)
def test_a_pin_that_cannot_be_used_raises_its_reason_on_every_call_and_is_checked_once(
        tmp_path, code, reason):
    runners = Runners()
    verifier = Verifier(tool_pins.ToolPinError(code, "because"))
    reader = _reader(_root(tmp_path), runners, verifier)
    for _ in range(3):
        with pytest.raises(server_git.ToolUnavailable) as caught:
            reader(["rev-parse", "HEAD"])
        assert (caught.value.code, caught.value.reason) == ("tool_unavailable", reason)
    assert verifier.calls == 1 and runners.built == [] and runners.specs == []


def test_a_conduct_home_that_cannot_be_named_is_a_git_that_is_not_pinned(
        tmp_path, pins, monkeypatch):
    def refuse(*args, **kwargs):
        raise conduct_home.ConductHomeInvalid("CONDUCT_HOME must be an absolute path")
    monkeypatch.setattr(conduct_home, "conduct_home_path", refuse)
    runners = Runners()
    reader = _reader(_root(tmp_path), runners, Verifier(), folder=None)
    with pytest.raises(server_git.ToolUnavailable) as caught:
        reader(["status"])
    assert caught.value.reason == "not_pinned" and runners.built == []


def test_a_folder_that_cannot_be_made_is_a_git_failure_and_not_a_missing_tool(tmp_path, pins):
    root, runners, verifier = _root(tmp_path), Runners(), Verifier()
    data = ownership.data_root(root)
    data.joinpath("git").write_text("a file where the folder must go", encoding="utf-8")
    reader = _reader(root, runners, verifier)
    for _ in range(2):
        with pytest.raises(project_git.GitReadFailed) as caught:
            reader(["status"])
        assert caught.value.code == "git_failed"
        assert not isinstance(caught.value, server_git.ToolUnavailable)
    assert verifier.calls == 1, "the tool was judged once; only the folder is tried again"
    data.joinpath("git").unlink()
    assert _reader(root, Runners(), Verifier())(["status"]).output == b"ok\n"


# -- the wiring of start_command --------------------------------------------------------


def _serve(tmp_path, mode, monkeypatch, builder):
    monkeypatch.setattr(server_git, "project_git_reader", builder)
    root = _root(tmp_path)
    subject = server.build(root, 0, registry=None, providers=(), clock=lambda: NOW,
                           token_factory=lambda _: TOKEN, launch=Launch(mode=mode))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    return subject, thread


def _stop(subject, thread) -> None:
    subject.shutdown()
    subject.server_close()
    thread.join(10)
    assert not thread.is_alive()


def test_a_view_child_builds_no_reader_passes_none_and_never_reads_the_pins(
        tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the pins were read, or a reader was built, for a view process")
    monkeypatch.setattr(tool_pins, "load_pins", refuse)
    monkeypatch.setattr(tool_pins, "verify_pin", refuse)
    subject, thread = _serve(tmp_path, "view", monkeypatch, refuse)
    try:
        assert subject.command_api._project_git is None
    finally:
        _stop(subject, thread)


def test_start_command_hands_an_active_child_the_reader_the_builder_made(tmp_path, monkeypatch):
    made = []

    def reader(args, separate_stderr=False):
        raise AssertionError("nothing asks git here")

    def builder(root, **options):
        made.append(Path(root).resolve())
        return reader

    subject, thread = _serve(tmp_path, "active", monkeypatch, builder)
    try:
        assert subject.command_api._project_git is reader
    finally:
        _stop(subject, thread)
    assert made == [tmp_path.resolve()]


# -- one real repository, the real runner and a real pinned git -------------------------


@needs_git
def test_an_active_server_lists_the_tracked_documents_of_its_repository_through_real_git(
        tmp_path, monkeypatch):
    home = tmp_path / "hub-home"
    home.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    tool_pins.pin_tool("git", GIT, folder=home)
    root = repository(tmp_path, "project")
    write_project(root, lanes={"claude": good_lane()})
    commit(root, {"README.md": "# Project\n", "docs/spec.md": "The spec.\n"})
    ownership_transition.activate(root, legacy_writers_stopped=True)
    subject = server.build(root, 0, providers=(), clock=lambda: NOW,
                           token_factory=lambda _: TOKEN, launch=Launch(mode="active"))
    thread = Thread(target=subject.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload, _ = _request(subject, "GET", "/command/project/documents")
    finally:
        _stop(subject, thread)
    assert status == 200, payload
    assert [row["path"] for row in payload["documents"]] == ["README.md", "docs/spec.md"]
    assert payload["base"]["commit"] and payload["truncated"] is False
    assert subprocess.run([GIT, "-C", str(root), "status", "--porcelain", "--", "README.md",
                           "docs"], capture_output=True).stdout == b""
