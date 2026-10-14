"""The second shown step of an accepted result: send its commit to GitHub (spec 9.7).

One handler answers both bodies of the route, the terms and the confirmation. It is never
reached from the commit route, and it asks nothing of the project until the body is exact.

What a confirmation does, in order, and why it can be pressed again:

1. it reads the terms again (the commit of the record, the push address git resolves now, the
   repository gh confirms) and refuses `push_terms_changed` when their digest is not the one the
   card showed;
2. it looks at the ref on the remote FIRST. The commit already there means the push stands and
   only the record is missing; another commit there is `push_rejected`; nothing there lets it go
   on. A press that only checks (`"check": true`) stops here;
3. it pushes that commit by address, with a lease that says the ref must not exist, and looks at
   the ref once more. Whatever the push said, only that look decides: no answer of the push is a
   record, and no unknown answer is ever repeated without the look that comes first.

The network calls run outside the store's transaction; only the small write of `push.json` holds
it. One press at a time acts on a run in this process.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from . import accept_github as github
from .accept_context import read_accept
from .accept_records import _validate
from .accept_snapshot import _folder, _put
from .accept_store import _bytes
from .adapters.process import ProcessRunner
from .authorization_terms import human_identity
from .contract_values import ContractError, _digest, _id
from .project_routes import _hold_git_allowed

_ACCEPTANCE = re.compile(r"acc-[0-9a-f]{32}\Z")
_TERMS_KEYS = frozenset({"acceptance_id", "remote", "preview"})
_CONFIRM_KEYS = frozenset({"acceptance_id", "remote", "push_digest", "actor"})
#: One line of `git push --porcelain`: flag, `from:to`, summary.
_PORCELAIN = re.compile(r"(.)\t([^\t:]+):([^\t]+)\t.*\Z")
_SENT = " *+="


@dataclass(frozen=True)
class PushRequest:
    """One press of the push step: the terms (`preview`), or the confirmation."""

    acceptance_id: str
    remote: str
    preview: bool
    push_digest: str | None = None
    actor: str | None = None
    check: bool = False


def acceptance_id(value: object) -> str:
    """`acc-` and 32 lowercase hex, the identity the commit record carries."""
    if type(value) is not str or _ACCEPTANCE.fullmatch(value) is None:
        raise ContractError("acceptance_id must be acc- and 32 lowercase hex digits")
    return value


def parse_body(body: object) -> PushRequest:
    """The closed body of the terms or of the confirmation, else `ContractError`."""
    if type(body) is not dict:
        raise ContractError("accept push needs a JSON object")
    keys = set(body)
    check = "check" in keys
    if check and body["check"] is not True:
        raise ContractError("check must be true when it is sent")
    keys.discard("check")
    if keys == _TERMS_KEYS and not check:
        if body["preview"] is not True:
            raise ContractError("preview must be true")
        return PushRequest(acceptance_id(body["acceptance_id"]), _id("remote", body["remote"]),
                           True)
    if keys != _CONFIRM_KEYS:
        raise ContractError("accept push needs the terms or the confirmation, exactly")
    return PushRequest(
        acceptance_id(body["acceptance_id"]), _id("remote", body["remote"]), False,
        _digest("push_digest", body["push_digest"]), human_identity("actor", body["actor"]),
        check)


def push(api, run_id, body):
    _hold_git_allowed(api)
    request = parse_body(body)
    try:
        return _answer(api, run_id, request)
    except github.FAULTS as error:
        raise github.refusal(error) from None


def _answer(api, run_id, request):
    commit = read_accept(api, run_id)[1]["commit"]
    if commit is None:
        raise github.PublishRefused("push_requires_commit")
    if request.acceptance_id != commit["acceptance_id"]:
        raise ContractError("acceptance_id is not the acceptance of this run")
    git, gh = github.readers(api)
    root = api._store.project_root
    if request.preview:
        return 200, {"push_terms": _current_terms(git, gh, root, commit, request.remote)}
    with github.publish_lock(root, run_id):
        record = read_accept(api, run_id)[1]["push"]
        if record is not None:
            return 200, {"push": _repeat(record, request)}
        terms = _current_terms(git, gh, root, commit, request.remote)
        if terms["push_digest"] != request.push_digest:
            raise github.PublishRefused("push_terms_changed")
        return _send(api, run_id, request, commit, terms, git)


def _repeat(record, request):
    """The standing record, for the press that repeats exactly the one that made it."""
    if record["push_digest"] != request.push_digest:
        raise github.PublishRefused("push_terms_changed")
    if record["requested_by"] != request.actor:
        raise github.PublishRefused("acceptance_exists")
    return record


def _current_terms(git, gh, root, commit, remote):
    found = github.read_facts(git, gh, root, remote)
    if not found.can_push:
        raise github.PublishRefused("push_not_permitted")
    ref = "refs/heads/" + commit["branch"]
    core = {"acceptance_id": commit["acceptance_id"], "commit": commit["commit"],
            "remote": remote, "push_url": found.push_url, "repo": found.repo, "ref": ref}
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = "sha256:" + hashlib.sha256(canonical.encode("ascii")).hexdigest()
    return {"commit": commit["commit"], "remote": remote, "push_url": found.push_url,
            "repo": found.repo, "ref": ref, "push_digest": digest,
            "command": " ".join(github.shell_word(word) for word in
                                ["git", *push_arguments(found.push_url, commit["commit"], ref)])}


def push_arguments(url, oid, ref):
    """The arguments of the push, after `git` and the path of the repository (spec 9.7).

    No `-u`, no `--tags`, no bare `--force`: the lease (`<ref>:` with an empty expectation) says
    the ref must not exist, and the remote itself judges it. The push goes by address, so it
    writes no remote-tracking ref.
    """
    return ["push", "--porcelain", "--no-follow-tags", "--recurse-submodules=no",
            f"--force-with-lease={ref}:", url, f"{oid}:{ref}"]


def _look(git, root, terms):
    """The commit the remote holds at the ref now, or None; no answer is a refusal."""
    try:
        return github.ls_remote(git, root, terms["push_url"], terms["ref"])
    except github.RemoteUnanswered as error:
        raise github.PublishRefused(
            "push_auth_failed" if error.auth else "push_unconfirmed") from None


def _send(api, run_id, request, commit, terms, git):
    root = api._store.project_root
    seen = _look(git, root, terms)
    if seen == commit["commit"]:
        return 201, {"push": _record(api, run_id, request, commit, terms, seen)}
    if seen is not None:
        raise github.PublishRefused("push_rejected")
    if request.check:
        return 200, {"push": None}
    attempt = git(["-C", str(root), *push_arguments(terms["push_url"], commit["commit"],
                                                    terms["ref"])],
                  False, timeout=github.PUSH_TIMEOUT_SECONDS)
    kind = _kind(attempt, terms["ref"])
    if kind == "auth":
        raise github.PublishRefused("push_auth_failed")
    seen = _look(git, root, terms)
    if seen == commit["commit"]:
        return 201, {"push": _record(api, run_id, request, commit, terms, seen)}
    if seen is not None or kind == "rejected":
        raise github.PublishRefused("push_rejected")
    raise github.PublishRefused("push_unconfirmed" if kind == "sent" else (
        "push_timed_out" if attempt.timed_out else "git_failed"))


def _kind(attempt, ref):
    """What the push itself said about the ref: sent, rejected, auth or uncertain.

    Only the look at the remote decides what a push did; this says what to call the failure when
    the look finds the ref absent. A timeout, a broken connection and an exit with no porcelain
    line for the ref are all `uncertain`.
    """
    if attempt.timed_out or attempt.exit_code is None:
        return "uncertain"
    flag = _flag(attempt.output, ref)
    if flag == "!":
        return "rejected"
    if flag is not None and flag in _SENT and attempt.exit_code == 0:
        return "sent"
    if attempt.exit_code != 0 and github.looks_unauthorized(attempt.output):
        return "auth"
    return "uncertain"


def _flag(output, ref):
    for row in output.decode("utf-8", errors="replace").splitlines():
        found = _PORCELAIN.fullmatch(row.rstrip("\r"))
        if found is not None and found[3] == ref:
            return found[1]
    return None


def _record(api, run_id, request, commit, terms, seen):
    value = {
        "schema_version": 1, "acceptance_id": commit["acceptance_id"], "remote": request.remote,
        "push_url": terms["push_url"], "remote_repo": terms["repo"], "ref": terms["ref"],
        "commit": commit["commit"], "push_digest": terms["push_digest"], "remote_oid": seen,
        "requested_by": request.actor, "pushed_at": api._clock()}
    return write_push(api, run_id, value)


def write_push(api, run_id, value):
    """Write `push.json` once, under the project's guard; the same bytes again change nothing."""
    root = api._store.project_root
    _validate("push", value)
    with api._store.transaction(), ProcessRunner.project_write_guard(root):
        _put(root, _folder(root, run_id) / "push.json", _bytes(value))
    return value
