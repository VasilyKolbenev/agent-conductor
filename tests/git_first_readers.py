"""The Git a first-commit probe runs against: the current one and the isolated lower bound.

The pin accepts Git 2.31 and later, so a probe that is meant to prove the marked index bytes must
also run with 2.31 as the reader. That binary is never the owner's: it is unpacked in a folder of
its own, never on the path, never pinned, and named by the environment variable `CONDUCT_OLD_GIT`.
While the variable is unset the `old_git` ids are collected and SKIPPED with the reason, so every
run shows that the gate is open; a variable that names the wrong binary FAILS and never skips, so
the gate cannot be closed by pointing it at some other Git.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest

from conductor.command.adapters.process import ProcessRunner
from conductor.command.project_git import process_git_read
from tests.git_repo_helpers import GIT, ISOLATED, KEPT, empty_home_environment

READERS = [pytest.param("current", id="current_git"), pytest.param("old", id="old_git")]
_VERSION = re.compile(r"git version (\d+)\.(\d+)\.(\d+)")


def old_git_problem(path: str, version_text: str) -> str | None:
    """Why `path` is not the isolated 2.31 (a 2.31.x that is not the current Git), or None."""
    found = _VERSION.match(version_text.strip())
    if found is None or (int(found[1]), int(found[2])) != (2, 31):
        return "CONDUCT_OLD_GIT must be an isolated Git 2.31.x"
    if GIT is not None and os.path.exists(path) and os.path.samefile(path, GIT):
        return "CONDUCT_OLD_GIT is the current Git"
    return None


def _version_text(path: str) -> str:
    """What `<path> --version` prints, or nothing when it cannot be run."""
    try:
        shown = subprocess.run([path, "--version"], capture_output=True, check=False,
                               env={**os.environ, **ISOLATED})
    except OSError:
        return ""
    return shown.stdout.decode(errors="replace")


def reader_binary(which: str) -> str:
    """The binary of a `READERS` id; `old` skips while unset and FAILS on a wrong binary."""
    if which == "current":
        if GIT is None:
            pytest.skip("git is not installed")
        return GIT
    path = os.environ.get("CONDUCT_OLD_GIT")
    if not path:
        pytest.skip("CONDUCT_OLD_GIT is not set: gate G-old is open")
    problem = old_git_problem(path, _version_text(path))
    if problem is not None:
        pytest.fail(problem)
    return path


def product_reader(root, binary, cwd, *, env=None, index_root=None):
    """The product's own Git reader as a test builds it: the real runner and `process_git_read`.

    Its Git cannot see the account's configuration, on any Git: `GIT_CONFIG_GLOBAL` (in `ISOLATED`)
    arrived in 2.32, so the home variables point at an empty folder as well. They are given in the
    literal environment, which the runner applies last: it passes HOME and USERPROFILE on from its
    own (`KEPT`), and XDG_CONFIG_HOME is not among the names it lets through.
    """
    runner = ProcessRunner(root, environ={name: os.environ[name] for name in KEPT
                                          if name in os.environ})
    literal = {**ISOLATED, **empty_home_environment(), **(env or {})}
    return process_git_read(runner, binary, str(cwd), env_allow=KEPT, env=literal,
                            index_root=index_root)
