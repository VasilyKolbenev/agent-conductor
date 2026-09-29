"""The identity of one project's server, and the claim a request may make on it (spec 4.5.1).

A desk is bound to a project by the activation nonce, not by a display name. `ProjectIdentity`
freezes what a `conduct up` process is and was started with: the nonce of the root it owns
(`None` for a root that was never activated), the origin of the hub that started it (`None`
for a standalone `up` or a demo), whether it is the demo, its mode, and the transition and
continue-after flag a hub handed it. The last two are for the queue pump of lane L and are
never shown by any answer.

`payload()` is the answer of `GET /command/project`: exactly four keys, so the desk learns the
mode (`view` or `active`) from one place. `check(pairs)` is the door for the request header
`X-Conduct-Project`: a request that names another project, or names one of a server that has
none, or names it twice, is refused `409 project_mismatch` with fixed words and no detail,
and the value it sent is never echoed. A request without the header passes as it always did.

Wiring lives in lane L's files (the route row, the constructor parameter of `CommandApi`, one
call of `check` after the transport checks); this module has no server, store or clock.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .api_refusals import ApiRefusal

HEADER = "X-Conduct-Project"
MODES = ("active", "view")
_PROJECT_ID = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class ProjectIdentity:
    """What this server is: see the module text for each field."""

    project_id: str | None
    hub_origin: str | None
    demo: bool
    mode: str
    transition_id: str | None
    auto_continue: str | None

    def __post_init__(self) -> None:
        if self.project_id is not None and not (
                isinstance(self.project_id, str) and _PROJECT_ID.fullmatch(self.project_id)):
            raise ValueError("project_id must be 32 lowercase hex characters, or None")
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")

    def payload(self) -> dict[str, Any]:
        """The answer of `GET /command/project`: exactly four keys."""
        return {"project_id": self.project_id, "hub_origin": self.hub_origin,
                "demo": self.demo, "mode": self.mode}

    def check(self, pairs: Iterable[tuple[str, str]]) -> None:
        """Hold a request's `X-Conduct-Project` claim to this server's project.

        Args:
            pairs: The raw ordered header pairs, already accepted by the transport checks.

        Raises:
            ApiRefusal: `project_mismatch` (409): the header is present and is not exactly
                one value equal to `project_id`; a server without a project id equals nothing.
        """
        claims = [value for name, value in pairs if name.casefold() == HEADER.casefold()]
        if not claims:
            return
        if len(claims) == 1 and self.project_id is not None and claims[0] == self.project_id:
            return
        raise ApiRefusal.fixed("project_mismatch")


def read_project(identity: ProjectIdentity) -> tuple[int, dict[str, Any]]:
    """The handler of `GET /command/project`: status 200 and the four keys of the identity."""
    return 200, identity.payload()
