"""The reader parameter of the first-commit probes: which Git runs, and when the gate is open.

No Git runs here. The version text of the old binary is stubbed, and `subprocess.run` is stood in
for where the helper's argument list and environment are the witness.
"""
import os
import subprocess

import pytest

from tests import git_first_readers as readers
from tests import git_repo_helpers as helpers
from tests.git_first_readers import READERS, old_git_problem, reader_binary

WRONG = "CONDUCT_OLD_GIT must be an isolated Git 2.31.x"


@pytest.fixture
def two_files(tmp_path, monkeypatch):
    """Two different files that stand for two Git binaries; the first is 'the current Git'."""
    current, other = tmp_path / "current-git", tmp_path / "other-git"
    current.write_bytes(b"one")
    other.write_bytes(b"two")
    monkeypatch.setattr(readers, "GIT", str(current))
    return current, other


@pytest.mark.parametrize("text, problem", [
    pytest.param("git version 2.52.0.windows.1", WRONG, id="2_52"),
    pytest.param("git version 2.32.0", WRONG, id="2_32"),
    pytest.param("git version 2.30.9", WRONG, id="2_30"),
    pytest.param("", WRONG, id="an_unreadable_version"),
    pytest.param("not git at all", WRONG, id="other_text"),
    pytest.param("git version 2.31.1", None, id="2_31_1"),
    pytest.param("git version 2.31.1.windows.1\n", None, id="2_31_1_windows"),
])
def test_the_old_git_reader_refuses_a_binary_that_is_not_the_isolated_2_31(
        two_files, text, problem):
    _, other = two_files
    assert old_git_problem(str(other), text) == problem


def test_the_old_git_reader_refuses_the_current_git_even_when_it_says_2_31(two_files):
    current, other = two_files
    problem = old_git_problem(str(current), "git version 2.31.1")
    assert problem == "CONDUCT_OLD_GIT is the current Git"
    assert old_git_problem(str(other), "git version 2.31.1") is None


def test_the_old_reader_skips_with_its_reason_while_the_variable_is_unset(monkeypatch):
    monkeypatch.delenv("CONDUCT_OLD_GIT", raising=False)
    with pytest.raises(pytest.skip.Exception) as skipped:
        reader_binary("old")
    assert "gate G-old is open" in str(skipped.value)


def test_the_old_reader_fails_and_never_skips_when_the_variable_names_the_wrong_binary(
        two_files, monkeypatch):
    current, other = two_files
    monkeypatch.setenv("CONDUCT_OLD_GIT", str(other))
    monkeypatch.setattr(readers, "_version_text", lambda path: "git version 2.52.0.windows.1")
    with pytest.raises(pytest.fail.Exception):
        reader_binary("old")
    monkeypatch.setattr(readers, "_version_text", lambda path: "git version 2.31.1")
    monkeypatch.setenv("CONDUCT_OLD_GIT", str(current))
    with pytest.raises(pytest.fail.Exception):
        reader_binary("old")


def test_the_old_reader_names_the_binary_when_it_is_the_isolated_2_31(two_files, monkeypatch):
    _, other = two_files
    monkeypatch.setenv("CONDUCT_OLD_GIT", str(other))
    monkeypatch.setattr(readers, "_version_text", lambda path: "git version 2.31.1.windows.1")
    assert reader_binary("old") == str(other)


def test_an_old_binary_that_cannot_be_run_is_a_failure_and_not_a_skip(two_files, monkeypatch):
    _, other = two_files

    def refused(*args, **keywords):
        raise OSError("not runnable")

    monkeypatch.setenv("CONDUCT_OLD_GIT", str(other))
    monkeypatch.setattr(readers.subprocess, "run", refused)
    with pytest.raises(pytest.fail.Exception):
        reader_binary("old")


def test_the_current_reader_is_the_git_every_other_test_uses(two_files):
    current, _ = two_files
    assert reader_binary("current") == str(current)


def test_the_reader_ids_say_which_git_runs():
    assert [param.id for param in READERS] == ["current_git", "old_git"]
    assert [param.values[0] for param in READERS] == ["current", "old"]


class Run:
    """A stand-in for `subprocess.run` that keeps the argument list and the environment."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, **keywords):
        self.calls.append((argv, keywords["env"]))
        return subprocess.CompletedProcess(argv, 0, b"", b"")


@pytest.fixture
def run(monkeypatch):
    stand_in = Run()
    monkeypatch.setattr(helpers.subprocess, "run", stand_in)
    return stand_in


def test_git_runs_the_binary_it_is_given_and_points_every_home_at_one_empty_folder(run, tmp_path):
    helpers.git("status", cwd=tmp_path, binary="C:/old/git.exe")
    argv, env = run.calls[0]
    assert argv[0] == "C:/old/git.exe" and argv[-1] == "status"
    homes = {env[name] for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME")}
    assert len(homes) == 1 and os.path.isdir(homes.pop())
    assert env["GIT_CONFIG_NOSYSTEM"] == "1" and env["GIT_CONFIG_GLOBAL"] == os.devnull


def test_git_without_a_binary_runs_the_default_git_and_leaves_the_home_alone(run, tmp_path):
    helpers.git("status", cwd=tmp_path)
    argv, env = run.calls[0]
    assert argv[0] == helpers.GIT
    assert all(env.get(name) == os.environ.get(name)
               for name in ("HOME", "USERPROFILE", "XDG_CONFIG_HOME"))


def test_git_adds_the_environment_it_is_given_over_the_isolated_one(run, tmp_path):
    helpers.git("status", cwd=tmp_path, env={"GIT_INDEX_FILE": "elsewhere", "LC_ALL": "C.UTF-8"})
    _, env = run.calls[0]
    assert env["GIT_INDEX_FILE"] == "elsewhere" and env["LC_ALL"] == "C.UTF-8"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
