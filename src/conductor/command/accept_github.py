"""What the push and the pull request know of GitHub (spec 9.7): where to send, and who may.

The push address is read from git (`remote get-url --push --all`, which expands `pushurl`,
`insteadOf` and `pushInsteadOf`), judged against the three forms the spec admits, and then
confirmed by the pinned gh (`repo view`). The address is never echoed: a refusal names a reason
and nothing of the text that caused it.

Whatever lives here is shared by the two steps: the refusal they raise from deep in a helper
(`PublishRefused`) and the one place that turns it, and the other faults of the road, into an
`ApiRefusal`; the lock that lets one press at a time act on a run; the remote look
(`ls_remote`) that both steps make before they act; and the reading of an answer from gh.
"""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass

from .accept_gh import GhAnswer, GhUnavailable
from .accept_manifest import SnapshotRefused
from .api_refusals import ApiRefusal
from .project_git import GitReadFailed
from .project_git_state import _remote_target

#: One git call may take a minute (spec 9.3); the push itself may take two.
GIT_TIMEOUT_SECONDS = 60
PUSH_TIMEOUT_SECONDS = 120
PERMITTED = ("ADMIN", "MAINTAIN", "WRITE")
VIEW_FIELDS = "nameWithOwner,defaultBranchRef,viewerPermission,isArchived"
#: The repository as hub/github reads it: its first character is never a dash, so no value of
#: this grammar can be read by gh as an option.
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}\Z")
_LISTED = re.compile(r"([0-9a-f]{40}|[0-9a-f]{64})\t(\S+)\Z")
#: What git (run with `LC_ALL=C`) says when it could not sign in. Matched in lower case.
_UNAUTHORIZED = (
    "authentication failed", "could not read username", "could not read password",
    "terminal prompts disabled", "permission denied", "invalid username or password",
    "access denied", "returned error: 401", "returned error: 403")
_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_REGISTRY = threading.Lock()


class PublishRefused(Exception):
    """A step of the push or the pull request is refused for one word of the closed list.

    `mismatch` is set only with `pr_mismatch` and is one word of `PR_MISMATCH_REASONS`.
    """

    def __init__(self, reason: str, mismatch: str | None = None) -> None:
        super().__init__(reason)
        self.reason, self.mismatch = reason, mismatch


class RemoteUnanswered(Exception):
    """The remote did not answer a look at one ref; `auth` says it refused to sign git in."""

    def __init__(self, auth: bool) -> None:
        super().__init__("remote unanswered")
        self.auth = auth


@dataclass(frozen=True)
class GithubFacts:
    """The destination of a push, as git names it and gh confirms it."""

    push_url: str
    repo: str
    can_push: bool
    default_branch: str | None


def refusal(error: Exception) -> ApiRefusal:
    """The one answer for every fault of the push and the pull request road."""
    if isinstance(error, PublishRefused):
        if error.mismatch is not None:
            return ApiRefusal.pr_mismatch(error.mismatch)
        return ApiRefusal.accept_refused(error.reason)
    if isinstance(error, SnapshotRefused):
        return ApiRefusal.accept_refused(error.reason)
    if isinstance(error, GhUnavailable):
        return ApiRefusal.tool_unavailable("gh", error.reason)
    if isinstance(error, GitReadFailed):
        if error.code == "tool_unavailable":
            return ApiRefusal.tool_unavailable("git", error.reason)
        return ApiRefusal.accept_refused(error.code)
    return ApiRefusal.accept_refused("git_failed")


#: Everything the road below a handler may raise that `refusal` answers for.
FAULTS = (PublishRefused, SnapshotRefused, GhUnavailable, GitReadFailed, OSError, UnicodeError)


def readers(api) -> tuple[object, object]:
    """The git reader and the gh reader of this server, or `tool_unavailable` for a missing one."""
    if api._project_git is None:
        raise ApiRefusal.tool_unavailable("git", "not_pinned")
    if api._project_gh is None:
        raise ApiRefusal.tool_unavailable("gh", "not_pinned")
    return api._project_git, api._project_gh


def publish_lock(root: object, run_id: str) -> threading.Lock:
    """The lock of one run in this process: one press at a time acts on it."""
    with _REGISTRY:
        return _LOCKS.setdefault((str(root), run_id), threading.Lock())


def looks_unauthorized(output: bytes) -> bool:
    """Whether git's own words say it could not sign in; the text itself is never kept."""
    text = output.decode("utf-8", errors="replace").lower()
    return any(phrase in text for phrase in _UNAUTHORIZED)


def read_facts(git, gh, root: object, remote: str) -> GithubFacts:
    """The push address, the repository gh confirms for it, and whether the owner may push.

    Raises:
        PublishRefused: `push_url_ambiguous`, `remote_url_has_credentials`,
            `push_destination_mismatch` (also for a remote that is not there or not GitHub's),
            `gh_not_logged_in`, or a failure of git or gh.
    """
    url = push_address(git, root, remote)
    repo, credentials = _remote_target(url)
    if credentials:
        raise PublishRefused("remote_url_has_credentials")
    if repo is None or REPO.fullmatch(repo) is None or not _admitted(url, repo):
        raise PublishRefused("push_destination_mismatch")
    confirmed = _repository_view(gh, repo)
    if confirmed["nameWithOwner"].casefold() != repo.casefold():
        raise PublishRefused("push_destination_mismatch")
    default = confirmed["defaultBranchRef"]
    return GithubFacts(url, repo, confirmed["viewerPermission"] in PERMITTED
                       and not confirmed["isArchived"],
                       None if default is None else default["name"])


def push_address(git, root: object, remote: str) -> str:
    """The one address a push to `remote` would use; more than one is ambiguous."""
    answer = git(["-C", str(root), "remote", "get-url", "--push", "--all", remote], True,
                 timeout=GIT_TIMEOUT_SECONDS)
    if answer.timed_out or answer.exit_code is None:
        raise GitReadFailed("git_timed_out")
    if answer.exit_code == 2:                      # git's word for "no such remote"
        raise PublishRefused("push_destination_mismatch")
    if answer.exit_code != 0 or answer.truncated:
        raise GitReadFailed("git_failed", answer.exit_code)
    lines = [line.strip() for line in answer.output.decode("utf-8").splitlines() if line.strip()]
    if len(lines) > 1:
        raise PublishRefused("push_url_ambiguous")
    if not lines:
        raise PublishRefused("push_destination_mismatch")
    return lines[0]


def _admitted(url: str, repo: str) -> bool:
    """One of the three forms of spec 9.7, spelled exactly: no port, no user but `git`."""
    stems = (f"https://github.com/{repo}", f"git@github.com:{repo}",
             f"ssh://git@github.com/{repo}")
    return any(url in (stem, stem + ".git", stem + "/", stem + ".git/") for stem in stems)


def _repository_view(gh, repo: str) -> Mapping[str, object]:
    answer = gh(["repo", "view", repo, "--json", VIEW_FIELDS])
    data = gh_json(answer)
    if (type(data) is not dict or set(data) != set(VIEW_FIELDS.split(","))
            or type(data["nameWithOwner"]) is not str
            or type(data["viewerPermission"]) is not str
            or type(data["isArchived"]) is not bool
            or not (data["defaultBranchRef"] is None
                    or type(data["defaultBranchRef"]) is dict
                    and type(data["defaultBranchRef"].get("name")) is str)):
        raise PublishRefused("git_failed")
    return data


def gh_checked(answer: GhAnswer, *, failed: str = "git_failed",
               timed_out: str = "git_timed_out") -> bytes:
    """The output of a gh call that succeeded, else the refusal its failure comes to.

    Exit code 4 is gh's own word for "not signed in". Output that carries a value of the
    environment the child ran in is hidden: it is a failure and is never read.
    """
    if answer.timed_out or answer.exit_code is None:
        raise PublishRefused(timed_out)
    if answer.exit_code == 4:
        raise PublishRefused("gh_not_logged_in")
    if answer.exit_code != 0 or answer.truncated or answer.hidden:
        raise PublishRefused(failed)
    return answer.output


def gh_json(answer: GhAnswer, *, failed: str = "git_failed",
            timed_out: str = "git_timed_out") -> object:
    """The JSON document of a gh call that succeeded; anything else is its refusal."""
    output = gh_checked(answer, failed=failed, timed_out=timed_out)
    try:
        return json.loads(output.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise PublishRefused(failed) from None


def ls_remote(git, root: object, url: str, ref: str) -> str | None:
    """The object id `ref` has at `url` now, or None when the remote has no such ref.

    Raises:
        RemoteUnanswered: the remote did not answer, or answered in a way that is not one ref.
    """
    answer = git(["-C", str(root), "ls-remote", url, ref], False, timeout=GIT_TIMEOUT_SECONDS)
    if answer.timed_out or answer.exit_code is None or answer.truncated:
        raise RemoteUnanswered(False)
    if answer.exit_code != 0:
        raise RemoteUnanswered(looks_unauthorized(answer.output))
    rows = answer.output.decode("utf-8", errors="replace").splitlines()
    found = [seen[1] for row in rows if (seen := _LISTED.fullmatch(row.strip())) and seen[2] == ref]
    if len(found) > 1:
        raise RemoteUnanswered(False)
    return found[0] if found else None


def shell_word(text: str) -> str:
    """`text` as one word a terminal reads back as the same text."""
    if re.fullmatch(r"[A-Za-z0-9._/:@=+-]+", text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"
