"""Real git repositories in a temporary folder, and a reader that runs git through the real runner.

The tests of the project's documents and of the materials door read a repository the way the
product does: through `project_git.process_git_read` over a `ProcessRunner`, with an environment
that cannot see the account's git configuration. `Script` is the other kind of witness, a reader
that answers from a table and records every call, so each branch and each argument is judged
without git.
"""
from __future__ import annotations

import atexit
import functools
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from conductor.command import project_git
from conductor.command.adapters.process import ProcessRunner

GIT = shutil.which("git")
needs_git = pytest.mark.skipif(GIT is None, reason="git is not installed")
ISOLATED = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C"}
KEPT = ("SystemRoot", "PATH", "HOME", "USERPROFILE", "TEMP", "TMP")
IDENTITY = ("-c", "user.name=Tester", "-c", "user.email=tester@example.invalid",
            "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false")


class Script:
    """A git reader that answers from a table and records what it was asked."""

    def __init__(self, *answers):
        self.answers, self.calls, self.keywords = list(answers), [], []

    def __call__(self, args, separate_stderr=False, **keywords):
        """`keywords` (`stdin`, `output_limit`, `timeout`) are kept beside `calls`, not in it."""
        self.calls.append((tuple(args), separate_stderr))
        self.keywords.append(keywords)
        return self.answers.pop(0)


def said(output=b"", code=0, **flags):
    return project_git.GitAnswer(exit_code=code, output=output, **flags)


_HOME_NAMES = ("HOME", "USERPROFILE", "XDG_CONFIG_HOME")


@functools.cache
def _empty_home():
    """A folder with no configuration in it. `GIT_CONFIG_GLOBAL` arrived in Git 2.32, so an older
    Git is kept away from the account's configuration by where it looks for it."""
    folder = tempfile.mkdtemp(prefix="conduct-empty-home-")
    atexit.register(shutil.rmtree, folder, True)
    return folder


def git(*args, cwd, check=True, binary=None, env=None):
    """Run the real git in `cwd` with the account's configuration out of sight.

    `binary` runs that Git instead of the one on the path (the isolated old Git of a
    compatibility probe) and also points every home variable at an empty folder; `env` adds
    environment variables (a private `GIT_INDEX_FILE`, for one).
    """
    environment = {**os.environ, **ISOLATED}
    if binary is not None:
        environment.update(dict.fromkeys(_HOME_NAMES, _empty_home()))
    environment.update(env or {})
    done = subprocess.run([binary or GIT, *IDENTITY, *args], cwd=cwd, env=environment,
                          capture_output=True)
    assert not check or done.returncode == 0, done.stderr.decode(errors="replace")
    return done


def real_reader(tmp_path):
    """A reader over the real runner, standing in a folder of its own."""
    home = tmp_path / "runner-home"
    (home / "cwd").mkdir(parents=True, exist_ok=True)
    runner = ProcessRunner(home, environ={name: os.environ[name] for name in KEPT
                                          if name in os.environ})
    return project_git.process_git_read(runner, GIT, str(home / "cwd"), env_allow=KEPT,
                                        env=ISOLATED)


def repository(tmp_path, name="repo"):
    """An empty repository (no commit yet) and the folder it lives in."""
    folder = tmp_path / name
    folder.mkdir()
    git("init", "-q", cwd=folder)
    return folder


def commit(folder, files, message="commit"):
    """Write `files` (path to text or bytes), stage exactly those, commit, return the commit oid.

    Only the named files are staged: the folder may hold the product's own run store by now, and
    a repository that tracked it would be one the product refuses.
    """
    for relative, content in files.items():
        target = folder / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    git("add", "--", *files, cwd=folder)
    git("commit", "-q", "-m", message, cwd=folder)
    return git("rev-parse", "HEAD", cwd=folder).stdout.decode().strip()


def blob_oid(folder, relative, revision="HEAD"):
    return git("rev-parse", f"{revision}:{relative}", cwd=folder).stdout.decode().strip()


def snapshot(git_dir):
    """Every file under a `.git` folder, by relative path, with its bytes."""
    return {path.relative_to(git_dir).as_posix(): path.read_bytes()
            for path in sorted(Path(git_dir).rglob("*")) if path.is_file()}
