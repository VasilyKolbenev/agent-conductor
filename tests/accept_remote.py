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
#: The name the push asks for first as its one command-line remote (spec 9.7).
GUARD = "conduct-no-tracking"


def guard_pair(name=GUARD, url=URL):
    """The two words before the verb that give a push by address its command-line remote."""
    return ["-c", f"remote.{name}.url={url}"]


def words_of(call):
    """What a recorded call gave git after `-C <root>`: the words the terms must show."""
    assert call[:1] == ["-C"], call
    return call[2:]


def guard_of(call):
    """The name of the command-line remote a recorded push was given, or None."""
    words = words_of(call)
    pairs = words[:words.index("push")]
    assert pairs[:1] in ([], ["-c"]) and len(pairs) in (0, 2), pairs
    return pairs[1].split(".")[1] if pairs else None


def config_text(root):
    """Every setting git resolves for the project, one text, to see that a push added none."""
    return git("config", "--list", "--show-origin", cwd=root).stdout


def refs_text(root):
    """Every ref of the project, one text, to see that a push added none and removed none."""
    return git("for-each-ref", "--format=%(refname) %(objectname)", cwd=root).stdout


def remotes_with_push_address(root, pairs, url):
    """The configured remotes whose push address is `url`, read the way Git 2.56 reads them.

    A remote's push address is its `pushurl` list when it has one, else its `url` list. `pairs`
    are the `-c` pairs the push is given, so a remote that only the command line defines is
    counted too. This is the condition of the tracking rule, not its effect: the effect is that
    of the git 2.56 job, and this host's git is older.
    """
    listed = git(*pairs, "config", "--get-regexp", r"^remote\..*\.(url|pushurl)$",
                 cwd=root).stdout.decode()
    urls, pushurls = {}, {}
    for row in listed.splitlines():
        key, _, value = row.partition(" ")
        name, _, kind = key[len("remote."):].rpartition(".")
        (pushurls if kind == "pushurl" else urls).setdefault(name, []).append(value)
    return sorted(name for name, found in urls.items() if url in (pushurls.get(name) or found))


def announce_git(capsys):
    """Print the version of the git under test where the run's output shows it, even with -q.

    The property these tests guard exists only from git 2.56: a green run on an older git does
    not show it, so the output must say which git it was.
    """
    version = git("--version", cwd=Path.cwd()).stdout.decode().strip()
    with capsys.disabled():
        print(f"\n[git under test] {version}")


def verb_of(args):
    """The git verb of one call: what follows `-C <root>` and any `-c <key=value>` pairs."""
    at = 2 if args[:1] == ["-C"] else 0
    while args[at] == "-c":
        at += 2
    return args[at]


class Remote:
    """The git reader, with the GitHub address of the tests rewritten to the bare repository."""

    def __init__(self, reader, bare, *, on_push=None, on_look=None):
        self.reader, self.bare = reader, Path(bare)
        self.on_push, self.on_look, self.calls = on_push, on_look, []

    def __call__(self, args, separate_stderr=False, **keywords):
        args = list(args)
        verb = verb_of(args)
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
        return [verb_of(call) for call in self.calls if call[:1] == ["-C"]]

    def pushes(self):
        return [call for call in self.calls if call[:1] == ["-C"] and verb_of(call) == "push"]


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
