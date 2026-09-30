"""A fake door of the continue-after flag, for the desk's browser tests (spec 4.3.4).

Not a test module: pytest does not collect it (no `test_` prefix). The routes of
`GET`/`POST /command/project/auto-continue` were not in lane D1's branch when the block that
uses them was written, so the tests answer them in the page, with a memory: the flag a `GET`
reads is the one the last `POST` wrote, in the record shape lane H's hand-off fixes (nine keys;
a flag that is turned on is always a new one, one that is turned off keeps its id). What the
desk sent, and with which headers, is kept for the test to read. `refuse` makes the next and
every later write answer a refusal.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Route

ABSENT = {"schema_version": 2, "flag_id": None, "revision": 0, "enabled": False, "actor": None,
          "set_at": None, "resume_runs": [], "start_task_queue": False, "consumed": None}
SET_AT = "2026-09-30T14:05:00Z"
DIGEST = "sha256:" + "0" * 64


def record(**changes: Any) -> dict:
    """A record of the flag: the absent one, with `changes` laid over it."""
    return {**copy.deepcopy(ABSENT), **changes}


def standing(actor: str = "vasya", runs: tuple[str, ...] = (), queue: bool = False) -> dict:
    """A flag that stands, listing `runs`."""
    return record(flag_id="5d8b7f0e-2c64-4d3a-9f1e-0a6c1d2b3e4f", revision=3, enabled=True,
                  actor=actor, set_at=SET_AT, start_task_queue=queue,
                  resume_runs=[_bound(run) for run in runs])


def consumed(actor: str = "vasya", runs: tuple[str, ...] = ()) -> dict:
    """A flag an activation has consumed."""
    return {**standing(actor, runs), "enabled": False, "revision": 4, "consumed": {
        "at": "2026-09-30T16:40:00Z", "transition_id": "b7c1e3d4-0000-4000-8000-000000000001",
        "activation_nonce": "0123456789abcdef0123456789abcdef"}}


def _bound(run_id: str) -> dict:
    return {"run_id": run_id, "authorization_id": f"auth-{run_id}",
            "authorization_digest": DIGEST, "last_control_id": None}


def automation(run_id: str, state: str, reason: str) -> dict:
    """The body of `GET /command/runs/<run_id>/automation` for a run in `state`."""
    return {"run_id": run_id, "authorization": None, "control": None, "state": state,
            "reason_code": reason, "active_action_id": None, "next_node_id": None,
            "spent_actions": 0, "remaining_actions": 0, "spent_task_seconds": 0,
            "remaining_task_seconds": 0, "expires_at": None, "owner_present": True}


@dataclass
class FlagServer:
    """The door, with a memory: `record` is what a read answers, `posts` what was written."""

    record: dict = field(default_factory=lambda: copy.deepcopy(ABSENT))
    posts: list[dict] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    reads: int = 0
    refuse: tuple[int, object] | None = None

    def handle(self, route: Route) -> None:
        request = route.request
        if request.method == "GET":
            self.reads += 1
            self._say(route, 200, self.record)
            return
        self.posts.append(json.loads(request.post_data or "null"))
        self.headers.append(dict(request.headers))
        if self.refuse is not None:
            self._say(route, *self.refuse)
            return
        self.record = self._apply(self.posts[-1])
        self._say(route, 200, self.record)

    def _apply(self, body: dict) -> dict:
        if not body["enabled"]:
            return {**self.record, "enabled": False, "revision": self.record["revision"] + 1,
                    "resume_runs": [], "start_task_queue": False}
        return standing(body["actor"], tuple(body["resume_runs"]), body["start_task_queue"]) | {
            "revision": self.record["revision"] + 1,
            "flag_id": f"flag-{self.record['revision'] + 1:04d}"}

    @staticmethod
    def _say(route: Route, status: int, body: object) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
