"""ADR-7e: a child that stands in the work tree is told where git must stop looking upward.

``GIT_CEILING_DIRECTORIES=<project root>`` is extra protection against git walking up from
``<root>/work/<id>`` into the owner's ``.git``. It is not the boundary (spec 10.6): an explicit
``git -C``, ``--git-dir`` and a plain file write are not stopped by it. The runner sets it, last,
for every child whose working folder is ``work`` or beneath it, where all five harnesses stand.

A child that stands anywhere else keeps git's own search. ``conduct projects add`` reads a
candidate folder with ``git -C <candidate>`` through a runner rooted at the candidate's PARENT: a
ceiling there would hide the repository that encloses a subfolder, and ``not_repo_root`` would turn
into ``git_failed``. The last test of this file keeps that reason.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conductor.command.adapters.process import CommandSpec, ProcessRunner
from tests._fakeproc import DUMP_ENV, fake_argv
from tests.git_repo_helpers import GIT, ISOLATED, KEPT, git, needs_git, repository

NAME = "GIT_CEILING_DIRECTORIES"


@pytest.fixture
def root(tmp_path):
    folder = (tmp_path / "project").resolve()
    for route in ("work/task-1", "reader"):
        (folder / route).mkdir(parents=True)
    return folder


@pytest.fixture
def runners():
    built = []

    def make(project_root, **kwargs):
        runner = ProcessRunner(project_root, **kwargs)
        built.append(runner)
        return runner

    yield make
    for runner in built:
        for token in runner.active_tokens():
            runner.stop(token)


def _child_env(runner, cwd, *, env_allow=(), env=None):
    outcome = runner.run(CommandSpec(argv=fake_argv(), cwd=cwd, timeout_seconds=20,
                                     env_allow=env_allow, env={DUMP_ENV: "1", **(env or {})}))
    line = outcome.output.decode("utf-8").splitlines()[0]
    assert line.startswith("ENV "), outcome.output
    return json.loads(line[len("ENV "):])


@pytest.mark.parametrize("cwd", ["work/task-1", "work"])
def test_a_child_standing_in_the_work_tree_sees_the_project_root_as_its_git_ceiling(
        root, runners, cwd):
    received = _child_env(runners(root), cwd)
    assert received[NAME] == str(root)


def test_the_runner_replaces_a_git_ceiling_that_the_environment_or_the_caller_names(
        root, runners):
    runner = runners(root, environ={NAME: str(root.parent)})
    received = _child_env(runner, "work/task-1", env_allow=(NAME,),
                          env={NAME: str(root / "reader")})
    assert received[NAME] == str(root)


def test_a_child_standing_outside_the_work_tree_gets_no_git_ceiling(root, runners):
    assert NAME not in _child_env(runners(root), "reader")


ROOT = Path("/p")


def git_ceiling_environment(env, root, cwd, **keywords):
    """The pure rule, imported when used, so a missing rule fails these tests and not the file."""
    from conductor.command.adapters.environment_values import git_ceiling_environment as rule
    return rule(env, root, Path(root) / "work", cwd, **keywords)


def test_on_windows_every_spelling_of_the_name_is_replaced_by_the_one() -> None:
    given = {"Keep": "1", "git_ceiling_directories": "x", NAME: "y"}
    done = git_ceiling_environment(given, ROOT, ROOT / "work" / "t", windows=True)
    assert done == {"Keep": "1", NAME: str(ROOT)}


def test_on_posix_another_case_is_another_variable_and_stays() -> None:
    given = {"git_ceiling_directories": "x", NAME: "y"}
    done = git_ceiling_environment(given, ROOT, ROOT / "work", windows=False)
    assert done == {"git_ceiling_directories": "x", NAME: str(ROOT)}


@pytest.mark.parametrize("cwd", ["reader", "workshop", "other/work"])
def test_a_folder_that_is_not_the_work_tree_keeps_the_environment_it_was_given(cwd) -> None:
    given = {"Keep": "1", NAME: "kept"}
    assert git_ceiling_environment(given, ROOT, ROOT / cwd, windows=False) == given


def _git_in(runner, cwd, *args):
    return runner.run(CommandSpec(argv=(GIT, *args), cwd=cwd, env_allow=KEPT, env=ISOLATED,
                                  timeout_seconds=30))


@needs_git
def test_git_started_by_the_runner_in_a_task_folder_does_not_find_the_owners_repository(
        root, runners):
    git("init", "-q", cwd=root)
    # The control: the same git, in the same folder, without the variable, does find it.
    plain = git("rev-parse", "--show-toplevel", cwd=root / "work" / "task-1")
    assert Path(plain.stdout.decode().strip()).samefile(root)
    ceilinged = _git_in(runners(root), "work/task-1", "rev-parse", "--show-toplevel")
    assert ceilinged.exit_code == 128 and b"not a git repository" in ceilinged.output


@needs_git
def test_the_product_s_reader_that_names_the_root_with_c_still_finds_it_from_a_task_folder(
        root, runners):
    git("init", "-q", cwd=root)
    answer = _git_in(runners(root), "work/task-1", "-C", str(root), "rev-parse", "--show-toplevel")
    assert answer.exit_code == 0
    assert Path(answer.output.decode().strip()).samefile(root)


@needs_git
def test_a_reader_folder_beneath_a_runner_rooted_at_a_parent_still_finds_the_enclosing_repository(
        tmp_path, runners):
    repo = repository(tmp_path).resolve()
    (repo / "sub").mkdir()
    # What `conduct projects add` builds: the runner is rooted at the candidate's parent.
    answer = _git_in(runners(repo), "sub", "-C", str(repo / "sub"), "rev-parse", "--show-toplevel")
    assert answer.exit_code == 0
    assert Path(answer.output.decode().strip()).samefile(repo)
