"""The third shown step of an accepted result: open a pull request for its pushed branch (spec 9.7).

It is reached only after a push record stands, and it asks nothing of the project until the
body is exact. A pull request is made for ONE head: the commit the push record names, on the
branch it names, in the repository it names, against the base the owner chose.

What a press does, in order, and why it can be pressed again:

1. the check BEFORE any creation, which changes nothing outside: the remote head must still be
   that commit (else `pr_mismatch`, `remote_head_moved`), and the pull requests already on the
   branch are read. One that is the head's own is recorded and nothing is created; one that is
   not (another commit, another base, a fork) is `pr_mismatch` and nothing is created. A press
   that only checks (`"check": true`) stops here. One difference, for every press: if the
   remote head has moved it still reads the list, since it may follow a creation whose answer
   was unknown, and a pull request found there is recorded as in 3; only a press that finds
   none refuses `remote_head_moved`. Nothing is created on a moved head;
2. the creation, with the body on standard input;
3. the same check again, the remote head and the list. The branch may have moved between the
   check and the creation: the check narrows that window and cannot close it, and this module
   never claims it did. A pull request that is not the head's own is recorded all the same, with
   what it is (`mismatch`), and is never created again.

A creation whose answer is unknown (a timeout, a broken connection, any failure but "not signed
in") is not repeated: the list is read first, and a press that finds nothing starts again at 1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import accept_github as github
from .accept_context import read_accept
from .accept_push import acceptance_id
from .accept_records import _OID, _validate
from .accept_snapshot import _folder, _put
from .accept_store import _bytes
from .adapters.process import ProcessRunner
from .authorization_terms import human_identity
from .contract_values import ContractError
from .project_routes import _hold_git_allowed

_KEYS = frozenset({"acceptance_id", "base", "title", "body", "draft", "actor"})
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\Z")
TITLE_LIMIT = 256
BODY_LIMIT = 32768
LIST_FIELDS = ("number,url,state,headRefName,headRefOid,baseRefName,isCrossRepository,"
               "isDraft")
_ROW_KEYS = frozenset(LIST_FIELDS.split(","))


@dataclass(frozen=True)
class PullRequestBody:
    """The closed body of one press of the pull request step."""

    acceptance_id: str
    base: str
    title: str
    body: str
    draft: bool
    actor: str
    check: bool = False


@dataclass(frozen=True)
class Listed:
    """One pull request of the branch, as `gh pr list` names it."""

    number: int
    head_oid: str
    base: str
    cross_repository: bool
    draft: bool

    def is_own(self, commit: str, base: str) -> bool:
        return self.head_oid == commit and self.base == base and not self.cross_repository

    def mismatch(self, commit: str) -> str:
        """The first word of `PR_MISMATCH_REASONS` that tells this one from the head's own."""
        if self.cross_repository:
            return "cross_repository"
        return "other_head" if self.head_oid != commit else "other_base"


def _base(value: object) -> str:
    if (type(value) is not str or _BRANCH.fullmatch(value) is None or ".." in value
            or "//" in value or value.endswith(("/", ".", ".lock"))):
        raise ContractError("base must be a branch name")
    return value


def _title(value: object) -> str:
    if (type(value) is not str or not value.strip() or len(value) > TITLE_LIMIT
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ContractError("title must be one line of text")
    return value


def _text(value: object) -> str:
    if (type(value) is not str or len(value) > BODY_LIMIT
            or any((ord(c) < 32 and c not in "\n\r\t") or ord(c) == 127 for c in value)):
        raise ContractError("body must be text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ContractError("body must be valid UTF-8 text") from None
    return value


def parse_body(body: object) -> PullRequestBody:
    """The closed body of the pull request step, else `ContractError`."""
    if type(body) is not dict:
        raise ContractError("accept pull-request needs a JSON object")
    keys = set(body)
    check = "check" in keys
    if check and body["check"] is not True:
        raise ContractError("check must be true when it is sent")
    keys.discard("check")
    if keys != _KEYS or type(body["draft"]) is not bool:
        raise ContractError("accept pull-request needs its closed body")
    return PullRequestBody(
        acceptance_id(body["acceptance_id"]), _base(body["base"]), _title(body["title"]),
        _text(body["body"]), body["draft"], human_identity("actor", body["actor"]), check)


def pull_request(api, run_id, body):
    _hold_git_allowed(api)
    request = parse_body(body)
    try:
        return _answer(api, run_id, request)
    except github.FAULTS as error:
        raise github.refusal(error) from None


def _answer(api, run_id, request):
    push = read_accept(api, run_id)[1]["push"]
    if push is None:
        raise github.PublishRefused("pr_requires_push")
    if request.acceptance_id != push["acceptance_id"]:
        raise ContractError("acceptance_id is not the acceptance of this run")
    git, gh = github.readers(api)
    with github.publish_lock(api._store.project_root, run_id):
        record = read_accept(api, run_id)[1]["pull_request"]
        if record is not None:
            return 200, {"pull_request": _repeat(record, request)}
        return _publish(api, run_id, request, push, (git, gh))


def _repeat(record, request):
    """The standing record, for a press that names the base it was made against."""
    if record["base"] != request.base:
        raise github.PublishRefused("pr_mismatch", "other_base")
    return record


def _publish(api, run_id, request, push, readers):
    git, gh = readers
    head = push["ref"].removeprefix("refs/heads/")
    seen = _remote_head(git, api._store.project_root, push)
    if seen != push["commit"]:
        return 200, {"pull_request": _moved(api, run_id, request, push, (gh, head), seen)}
    own = _existing(gh, push, head, request.base)
    if own is not None:
        return 200, {"pull_request": _record(api, run_id, request, push, own)}
    if request.check:
        return 200, {"pull_request": None}
    return 201, {"pull_request": _create(api, run_id, request, push, head, (git, gh))}


def _remote_head(git, root, push):
    """The commit the branch holds on the remote now (None: no such ref), else a refusal."""
    try:
        return github.ls_remote(git, root, push["push_url"], push["ref"])
    except github.RemoteUnanswered as error:
        raise github.PublishRefused(
            "push_auth_failed" if error.auth else "pr_create_failed") from None


def _existing(gh, push, head, base):
    """The head's own pull request on the branch, or None, or `pr_mismatch` for another one."""
    listed = _list(gh, push["remote_repo"], head)
    own = next((row for row in listed if row.is_own(push["commit"], base)), None)
    if own is None and listed:
        raise github.PublishRefused("pr_mismatch", listed[0].mismatch(push["commit"]))
    return own


def _moved(api, run_id, request, push, where, seen):
    """The remote head is not the pushed commit: no creation, and the list is read first.

    Any press may follow a creation whose answer was unknown, and that creation may have made a
    pull request nobody read back. The card that knew the answer was unknown is gone after a
    reload or a change of run, the server is not, so refusing here without a look would leave
    that pull request unrecorded for good. So the list is read (it changes nothing outside) and
    a pull request found there is recorded as what it is (its `mismatch`), the way a pull
    request created for a branch that moved is. None found is `pr_mismatch`, `remote_head_moved`.
    """
    gh, head = where
    listed = _list(gh, push["remote_repo"], head)
    if not listed:
        raise github.PublishRefused("pr_mismatch", "remote_head_moved")
    row = next((row for row in listed if row.is_own(push["commit"], request.base)), listed[0])
    return _record(api, run_id, request, push, row, seen)


def _list(gh, repo, head):
    """Every pull request of the branch, any state; a failure is `pr_create_failed`."""
    answer = gh(["pr", "list", "--repo", repo, "--head", head, "--state", "all",
                 "--json", LIST_FIELDS])
    data = github.gh_json(answer, failed="pr_create_failed", timed_out="pr_create_failed")
    if type(data) is not list:
        raise github.PublishRefused("pr_create_failed")
    rows = [_row(item) for item in data]
    return sorted((row for row, name in rows if name == head), key=lambda row: row.number)


def _row(item):
    """One listed pull request and the branch it names, else `pr_create_failed`."""
    if (type(item) is not dict or set(item) != _ROW_KEYS or type(item["number"]) is not int
            or item["number"] < 1 or type(item["headRefName"]) is not str
            or type(item["headRefOid"]) is not str or not _OID.fullmatch(item["headRefOid"])
            or type(item["baseRefName"]) is not str or not item["baseRefName"].strip()
            or type(item["isCrossRepository"]) is not bool or type(item["isDraft"]) is not bool):
        raise github.PublishRefused("pr_create_failed")
    return (Listed(item["number"], item["headRefOid"], item["baseRefName"],
                   item["isCrossRepository"], item["isDraft"]), item["headRefName"])


def _create(api, run_id, request, push, head, readers):
    git, gh = readers
    repo = push["remote_repo"]
    argv = ["pr", "create", "--repo", repo, "--base", request.base, "--head", head,
            "--title", request.title, "--body-file", "-"]
    made = gh(argv + (["--draft"] if request.draft else []), stdin=request.body.encode("utf-8"))
    number = _number(made, repo)
    listed = _list(gh, repo, head)
    row = next((row for row in listed if number is None or row.number == number), None)
    if row is None:
        raise github.PublishRefused("pr_create_failed")
    return _record(api, run_id, request, push, row,
                   _moved_to(git, api._store.project_root, push))


def _moved_to(git, root, push):
    """The commit the branch holds now when it is not the pushed one, else None.

    This is the second half of the check after a creation. The pull request exists whatever the
    remote says now, so a remote that does not answer, or has no such ref, adds nothing here.
    """
    try:
        seen = github.ls_remote(git, root, push["push_url"], push["ref"])
    except github.RemoteUnanswered:
        return None
    return seen if seen not in (None, push["commit"]) else None


def _number(made, repo):
    """The number gh printed for the pull request it made, or None when that is not known.

    Not signed in is the one failure with a certain meaning (gh asks before it creates). Every
    other failure, and an answer that names no pull request, is unknown: it is read back from
    the list, never repeated.
    """
    if not made.timed_out and made.exit_code == 4:
        raise github.PublishRefused("gh_not_logged_in")
    if made.timed_out or made.exit_code != 0 or made.truncated or made.hidden:
        return None
    lines = made.output.decode("utf-8", errors="replace").split()
    found = re.fullmatch(rf"https://github\.com/{re.escape(repo)}/pull/([0-9]+)",
                         lines[-1], re.IGNORECASE) if lines else None
    return int(found[1]) if found else None


def _record(api, run_id, request, push, row, moved=None):
    own = moved is None and row.is_own(push["commit"], request.base)
    value = {
        "schema_version": 1, "acceptance_id": push["acceptance_id"], "repo": push["remote_repo"],
        "number": row.number, "url": f"https://github.com/{push['remote_repo']}/pull/{row.number}",
        "draft": row.draft, "base": request.base,
        "head_ref": push["ref"].removeprefix("refs/heads/"), "head_oid": push["commit"],
        "mismatch": None if own else {
            "head_oid": moved or row.head_oid, "base": row.base,
            "cross_repository": row.cross_repository},
        "requested_by": request.actor, "created_at": api._clock()}
    return write_pull_request(api, run_id, value)


def write_pull_request(api, run_id, value):
    """Write `pr.json` once, under the project's guard; the same bytes again change nothing."""
    root = api._store.project_root
    _validate("pr", value)
    with api._store.transaction(), ProcessRunner.project_write_guard(root):
        _put(root, _folder(root, run_id) / "pr.json", _bytes(value))
    return value
