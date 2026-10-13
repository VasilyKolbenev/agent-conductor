"""An accepted result whose remote is a bare repository on disk and whose gh is a scripted file.

The product reads the push address with `remote get-url --push --all`, which expands `insteadOf`
(spec 9.7). So the remote of these tests really is `https://github.com/o/r.git`; a wrapper around
the git reader rewrites that address to the bare repository for `push` and `ls-remote` ONLY, and
refuses any other address for those two, so no test can ever reach a real host. `get-url` is
passed through untouched and still shows the GitHub address. Production code is unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from conductor import tool_pins
from conductor.command import accept_gh
from conductor.command.project_git import GitAnswer
from tests import _fakegh
from tests.git_repo_helpers import git
from tests.test_accept_commit import PATH as COMMIT_PATH, prepared
from tests.test_accept_context import RUN
from tests.test_accept_preview import PATH as PREVIEW
from tests.test_command_http_api import post

URL = "https://github.com/o/r.git"
SSH_URL = "git@github.com:o/r.git"
PUSH = f"/command/runs/{RUN}/accept/push"
PULL_REQUEST = f"/command/runs/{RUN}/accept/pull-request"
BRANCH = f"conduct/{RUN}"
REF = f"refs/heads/{BRANCH}"
#: Names an owner's environment may carry; none may reach gh, and none is a real token.
OWNER = {"GH_TOKEN": "fake-token-one", "GITHUB_TOKEN": "fake-token-two",
         "GH_HOST": "host.example", "GIT_ASKPASS": "fake-askpass"}
TIMED_OUT = GitAnswer(exit_code=None, output=b"", timed_out=True)


class Remote:
    """The git reader, with the GitHub address of the tests rewritten to the bare repository."""

    def __init__(self, reader, bare, *, on_push=None, on_look=None):
        self.reader, self.bare = reader, Path(bare)
        self.on_push, self.on_look, self.calls = on_push, on_look, []

    def __call__(self, args, separate_stderr=False, **keywords):
        args = list(args)
        verb = args[2] if args[:1] == ["-C"] else args[0]
        self.calls.append(args)
        if verb not in ("push", "ls-remote"):
            return self.reader(args, separate_stderr, **keywords)
        assert URL in args or SSH_URL in args, f"a test reached for an address: {args}"
        base = self.bare.as_posix()
        rewritten = ["-c", f"url.{base}.insteadOf={URL}", "-c",
                     f"url.{base}.insteadOf={SSH_URL}", *args]

        def run():
            return self.reader(rewritten, separate_stderr, **keywords)

        hook = self.on_push if verb == "push" else self.on_look
        return run() if hook is None else hook(run)

    def verbs(self):
        return [call[2] for call in self.calls if call[:1] == ["-C"]]

    def pushes(self):
        return [call for call in self.calls if call[:1] == ["-C"] and call[2] == "push"]


def accepted(tmp_path):
    """-> api, root, the commit record, the remote reader, the bare repository."""
    api, root, _work, _saved = prepared(tmp_path)
    git("remote", "add", "origin", URL, cwd=root)
    bare = tmp_path / "remote.git"
    git("init", "--bare", "-q", str(bare), cwd=tmp_path)
    remote = Remote(api._project_git, bare)
    api._project_git = remote                    # in place before the commit, which must not push
    digest = post(api, PREVIEW, {}).payload["accept"]["accept_digest"]
    answer = post(api, COMMIT_PATH, {"accept_digest": digest, "actor": "Owner"})
    assert answer.status == 201, answer.payload
    return api, root, answer.payload["commit"], remote, bare


def with_gh(tmp_path, api, root, script=None):
    """Put the scripted gh on the API; -> its executable, the folder of that (which also holds
    the script and the log), the hub home it is pinned in and the owner's environment."""
    exe = _fakegh.build_executable(tmp_path / "ghbin")
    assert exe is not None, "this host has no way to build a real executable for the fake gh"
    hub = tmp_path / "hub-home"
    hub.mkdir()
    source = {**os.environ, **OWNER}
    tool_pins.pin_tool("gh", str(exe), folder=hub, source=source)
    _fakegh.script(exe.parent, {"repo view": [_fakegh.repo_view()], **(script or {})})
    api._project_gh = accept_gh.project_gh_reader(root, source=source, folder=hub)
    return SimpleNamespace(exe=exe, dir=exe.parent, hub=hub, source=source)


def remote_oid(bare, ref=REF):
    """The commit the bare repository holds at `ref`, or None."""
    done = git("rev-parse", "--verify", "-q", ref, cwd=bare, check=False)
    return done.stdout.decode().strip() or None


def seed_remote_ref(root, bare, oid, ref=REF):
    """Put `oid` at `ref` in the bare repository by a plain push, outside the product."""
    git("push", "-q", str(bare), f"{oid}:{ref}", cwd=root)


def terms(api, record, remote="origin"):
    return post(api, PUSH, {"acceptance_id": record["acceptance_id"], "remote": remote,
                            "preview": True})


def confirm(api, record, digest, *, actor="Owner", remote="origin", **more):
    return post(api, PUSH, {"acceptance_id": record["acceptance_id"], "remote": remote,
                            "push_digest": digest, "actor": actor, **more})


def digest_of(api, record):
    answer = terms(api, record)
    assert answer.status == 200, answer.payload
    return answer.payload["push_terms"]["push_digest"]
