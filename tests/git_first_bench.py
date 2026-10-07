"""A project with an unborn repository, a reader that may use an owned index, and a spy on it.

The first half of the bench of the first-commit tests (plan Task 6.1): `project` builds the folder,
its repository and the product's own Git reader for one reader (`tests.git_first_readers`) and one
object format; `seal` takes the preview the desk would show; `Spy` keeps every call the product
makes, in order. The product's reader is built by `product_reader` and by nothing else here, so
that the isolation from the account's Git settings, which holds on every Git and is proven once,
cannot be gone around by a later test (gate G-old, row 9).
"""
from __future__ import annotations

import functools

import pytest

from conductor.command import git_setup, git_setup_first
from conductor.command.run_store import StoreError
from conductor.ownership import data_root
from tests.git_first_readers import product_reader, reader_binary
from tests.git_repo_helpers import git
from tests.test_command_project_doors import request
from tests.test_git_setup import PATH, step
from tests.test_seed_routes import Folder


class Spy:
    """A Git reader that keeps every call, in order, and forwards it."""

    def __init__(self, read):
        self.read, self.calls = read, []

    def __call__(self, args, *positional, **keywords):
        self.calls.append((tuple(args), dict(keywords)))
        return self.read(args, *positional, **keywords)

    def argv(self, word):
        """The argument lists of the calls that name `word`."""
        return [args for args, _ in self.calls if word in args]


def project(tmp_path, files=None, name="first", branch="trunk", *, which="current", fmt="sha1"):
    """An unborn project; its reader (the current or the isolated old Git) runs no hook and may
    use an owned index. `folder.git(...)` is the reader's own Git, for every look at the repo."""
    binary = reader_binary(which)                # `old` skips while G-old is open; wrong one fails
    folder = Folder(tmp_path, name=name)
    root = folder.root
    cwd = data_root(root) / "git" / "cwd"
    cwd.mkdir(parents=True)
    hooks = cwd.parent / "hooks-empty"
    hooks.mkdir()
    env = {"GIT_CONFIG_COUNT": "2",
           "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(hooks),
           "GIT_CONFIG_KEY_1": "init.defaultBranch", "GIT_CONFIG_VALUE_1": branch}
    folder.spy = Spy(product_reader(root, binary, cwd, env=env, index_root=root))
    folder.api._project_git = folder.spy
    folder.git = functools.partial(git, binary=binary)
    if fmt == "sha256":
        made = folder.git("init", "-q", "--object-format=sha256", "-b", branch, str(root),
                          cwd=tmp_path, check=False)
        if made.returncode != 0:
            pytest.skip("this git cannot make a sha256 repository")
        assert step(folder, "exclude").status == 201     # the exclusion block, as init writes it
    else:
        assert step(folder).status == 201        # the explicit init the desk does first
    for key, value in (("user.name", "First Author"), ("user.email", "first@example.invalid"),
                       ("core.autocrlf", "false")):
        folder.git("config", key, value, cwd=root)
    for relative, data in (files or {}).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return folder


def seal(folder, mode="snapshot"):
    """The preview of the first commit as the route answers it: the terms a person is shown."""
    body = dict(step="first_commit", mode=mode, preview=True)
    return request(folder, "POST", PATH, body).payload["setup"]


@pytest.fixture
def confirm_door(monkeypatch):
    """The tests of the driver prove it with the route's confirm door open; the real door opens
    only after the compatibility gate on the lowest supported Git is closed (plan Task 8.7).
    Nothing outside a test ever sets this."""
    monkeypatch.setattr(git_setup, "_CONFIRM_OPEN", True)


def confirm(folder, mode="snapshot", digest=None, actor="Owner"):
    """The confirm body as the route takes it; a snapshot without a digest is sealed first."""
    if digest is None and mode == "snapshot":
        digest = seal(folder)["paths_digest"]
    body = dict(step="first_commit", mode=mode, paths_digest=digest, actor=actor)
    return request(folder, "POST", PATH, body)


def op_file(folder):
    """Where the operation record of the first commit stands."""
    return data_root(folder.root) / "git" / "setup" / "first_commit.op.json"


def terms_of(folder, mode="snapshot"):
    """The digest a confirmation of `mode` carries, taken from a preview now: None for `empty`.
    A repeat after a crash cannot ask for it again (the preview refuses while the lock stands)."""
    return seal(folder)["paths_digest"] if mode == "snapshot" else None


def crash_after(monkeypatch, name, *, owner=git_setup_first, times=1):
    """Let the named function of `owner` do its effect, then fail like a crash (HTTP 500).

    Returns the function that puts the real one back: the process that died has restarted."""
    real, left = getattr(owner, name), [times]

    def wrapper(*args, **kwargs):
        result = real(*args, **kwargs)
        left[0] -= 1
        if left[0] == 0:
            raise StoreError("simulated interruption after " + name)
        return result

    monkeypatch.setattr(owner, name, wrapper)
    return lambda: monkeypatch.setattr(owner, name, real)


def crashed(monkeypatch, folder, name, mode="snapshot", digest=None, *, owner=git_setup_first):
    """Confirm, crash right after `name` has done its effect, and restart: what is left is the
    state a process that died there leaves, and the next confirm is the exact repeat of this one."""
    restart = crash_after(monkeypatch, name, owner=owner)
    answer = confirm(folder, mode, digest=digest)
    restart()
    assert answer.status == 500, answer.payload
