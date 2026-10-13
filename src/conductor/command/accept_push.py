"""The second shown step of an accepted result: send its commit to GitHub (spec 9.7).

One handler answers both bodies of the route, the terms and the confirmation. It is never
reached from the commit route, and it asks nothing of the project until the body is exact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .accept_context import read_accept
from .api_refusals import ApiRefusal
from .authorization_terms import human_identity
from .contract_values import ContractError, _digest, _id
from .project_routes import _hold_git_allowed

_ACCEPTANCE = re.compile(r"acc-[0-9a-f]{32}\Z")
_TERMS_KEYS = frozenset({"acceptance_id", "remote", "preview"})
_CONFIRM_KEYS = frozenset({"acceptance_id", "remote", "push_digest", "actor"})


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
    parse_body(body)
    if read_accept(api, run_id)[1]["commit"] is None:
        raise ApiRefusal.accept_refused("push_requires_commit")
    raise ApiRefusal.tool_unavailable("gh", "not_pinned")
