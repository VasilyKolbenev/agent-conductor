"""The third shown step of an accepted result: open a pull request for its pushed branch (spec 9.7).

It is reached only after a push record stands, and it asks nothing of the project until the
body is exact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .accept_context import read_accept
from .accept_push import acceptance_id
from .api_refusals import ApiRefusal
from .authorization_terms import human_identity
from .contract_values import ContractError
from .project_routes import _hold_git_allowed

_KEYS = frozenset({"acceptance_id", "base", "title", "body", "draft", "actor"})
_BRANCH = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\Z")
TITLE_LIMIT = 256
BODY_LIMIT = 32768


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
    parse_body(body)
    if read_accept(api, run_id)[1]["push"] is None:
        raise ApiRefusal.accept_refused("pr_requires_push")
    raise ApiRefusal.tool_unavailable("gh", "not_pinned")
