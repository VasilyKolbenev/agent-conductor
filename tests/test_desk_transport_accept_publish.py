"""The write targets `acceptPush` and `acceptPullRequest` go through the one mutation door.

`desk-transport.js` opens the push and the pull request of an accepted result (spec 9.7) as two
targets: one POST path each, the closed bodies of the route, the session token and the refusal
door of every other closed target. The real module runs under Node with a fake `fetch`, so what
is held here is what the door puts on the wire and what it hands back. The refusal bodies are the
server's own: `ApiRefusal` builds each one and its `as_dict()` is what the fake answers. The accept
card reads `error.detail` off the payload, the one `reason` and, for `pr_mismatch`, the second
word `mismatch`, so the door must hand it back as it came and never rebuild it.
"""
from __future__ import annotations

import json

from conductor.command.api_refusals import (
    ACCEPT_REASONS, ERROR_STATUS, PR_MISMATCH_REASONS, ApiRefusal)
from conductor.command.command_routes import match_route
from tests.desk_node import run_js

MODULES = {"transport": "desk-transport.js"}
ORIGIN = "http://127.0.0.1:7777"
RUN = "run-2026-10-14.a"
ACCEPTANCE = "acc-" + "a" * 32
DIGEST = "sha256:" + "d" * 64
#: The closed bodies of each route: the terms, the confirmation, and the confirmation that only
#: checks (spec 9.7; the push body is the terms or the confirmation, the pull request has one).
PUSH_BODIES = [
    {"acceptance_id": ACCEPTANCE, "remote": "origin", "preview": True},
    {"acceptance_id": ACCEPTANCE, "remote": "origin", "push_digest": DIGEST, "actor": "Owner"},
    {"acceptance_id": ACCEPTANCE, "remote": "origin", "push_digest": DIGEST, "actor": "Owner",
     "check": True},
]
PR_BODIES = [
    {"acceptance_id": ACCEPTANCE, "base": "main", "title": "T", "body": "B\nC", "draft": False,
     "actor": "Owner"},
    {"acceptance_id": ACCEPTANCE, "base": "main", "title": "T", "body": "", "draft": True,
     "actor": "Owner", "check": True},
]
#: The reasons the push and the pull request add to `accept_refused` (spec 9.7).
NEW_REASONS = ACCEPT_REASONS[ACCEPT_REASONS.index("push_requires_commit"):]
#: A window's wire: `fetch` answers the session read, then each row of `d.answers` in turn.
FAKE_WIRE = """
  const calls = [];
  globalThis.location = {origin: d.origin};
  const reply = (status, wire) => ({ok: status < 400, status, json: async () => JSON.parse(wire)});
  let next = 0;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({url, method: init.method || "GET", headers: init.headers || {},
      body: init.body === undefined ? null : init.body});
    if (url === "/command/session") {
      return reply(200, JSON.stringify({csrf_token: "tok", origin: d.origin}));
    }
    const row = d.answers[next];
    next += 1;
    return reply(row.status, JSON.stringify(row.wire));
  };
  const door = transport.createTransport(() => "en");
"""


def _through_the_door(answers: list[dict], target: str) -> dict:
    """Submit `target` once per row of `answers` and return its answers and the requests made."""
    return run_js(FAKE_WIRE + """
      const results = [];
      for (const row of d.answers) results.push(await door.submit(d.target, d.run, row.body));
      console.log(JSON.stringify({results, calls}));
    """, MODULES, {"origin": ORIGIN, "answers": answers, "target": target, "run": RUN})


def _paths(rows: list[list[str]]) -> list[str]:
    """`path.<name>(arg)` for each row of (name, argument) under Node."""
    return run_js("""
      console.log(JSON.stringify(d.map(([name, arg]) => transport.path[name](arg))));
    """, MODULES, rows)


def _refusals() -> list[dict]:
    """The wire body of each reason the two steps add, then each word of `pr_mismatch`."""
    reasons = [ApiRefusal.accept_refused(reason).as_dict() for reason in NEW_REASONS]
    words = [ApiRefusal.pr_mismatch(word).as_dict() for word in PR_MISMATCH_REASONS]
    return reasons + words


def test_the_two_paths_are_the_routes_of_the_command_canon_and_no_other():
    push, pull = _paths([["acceptPush", RUN], ["acceptPullRequest", RUN]])
    assert push == f"/command/runs/{RUN}/accept/push"
    assert pull == f"/command/runs/{RUN}/accept/pull-request"
    assert (match_route("POST", push).name, match_route("POST", push).run_id) == (
        "accept_push", RUN)
    assert (match_route("POST", pull).name, match_route("POST", pull).run_id) == (
        "accept_pull_request", RUN)


def test_a_run_id_with_a_slash_stays_one_segment_of_the_push_path():
    push, pull = _paths([["acceptPush", "a/b"], ["acceptPullRequest", "a/../b"]])
    assert push == "/command/runs/a%2Fb/accept/push"
    assert pull == "/command/runs/a%2F..%2Fb/accept/pull-request"


def test_the_push_target_posts_each_closed_body_to_the_push_route_under_one_token():
    answers = [{"body": body, "status": 200, "wire": {"push_terms": {}}} for body in PUSH_BODIES]
    out = _through_the_door(answers, "acceptPush")
    path = f"/command/runs/{RUN}/accept/push"
    assert [call["url"] for call in out["calls"]] == ["/command/session"] + [path] * 3
    first, *writes = out["calls"]
    assert first["method"] == "GET"
    for call, body in zip(writes, PUSH_BODIES, strict=True):
        assert call["method"] == "POST" and json.loads(call["body"]) == body
        assert call["headers"]["X-Conduct-CSRF"] == "tok"
        assert call["headers"]["Content-Type"] == "application/json"
    assert out["results"] == [{"status": "accepted", "payload": row["wire"]} for row in answers]


def test_the_pull_request_target_posts_each_closed_body_to_its_route_under_one_token():
    answers = [{"body": body, "status": 201, "wire": {"pull_request": {"number": 7}}}
               for body in PR_BODIES]
    out = _through_the_door(answers, "acceptPullRequest")
    path = f"/command/runs/{RUN}/accept/pull-request"
    assert [call["url"] for call in out["calls"]] == ["/command/session"] + [path] * 2
    for call, body in zip(out["calls"][1:], PR_BODIES, strict=True):
        assert call["method"] == "POST" and json.loads(call["body"]) == body
        assert call["headers"]["X-Conduct-CSRF"] == "tok"
    assert out["results"] == [{"status": "accepted", "payload": row["wire"]} for row in answers]


def test_a_push_or_pull_request_refusal_comes_back_with_its_detail_as_the_server_wrote_it():
    wires = _refusals()
    assert len(wires) == len(NEW_REASONS) + len(PR_MISMATCH_REASONS) == 18
    assert all(set(wire["error"]["detail"]) == {"reason"} for wire in wires[:14])
    assert all(set(wire["error"]["detail"]) == {"reason", "mismatch"} for wire in wires[14:])
    status = ERROR_STATUS["accept_refused"]
    for target, body in (("acceptPush", PUSH_BODIES[1]), ("acceptPullRequest", PR_BODIES[0])):
        out = _through_the_door([{"body": body, "status": status, "wire": wire}
                                 for wire in wires], target)
        assert len(out["results"]) == len(wires)
        for result, wire in zip(out["results"], wires, strict=True):
            assert (result["status"], result["code"]) == ("refused", "accept_refused"), target
            assert json.dumps(result["payload"]) == json.dumps(wire), target


def test_a_tool_refusal_of_gh_comes_back_whole_from_both_targets():
    wire = ApiRefusal.tool_unavailable("gh", "not_pinned").as_dict()
    status = ERROR_STATUS["tool_unavailable"]
    for target, body in (("acceptPush", PUSH_BODIES[0]), ("acceptPullRequest", PR_BODIES[0])):
        out = _through_the_door([{"body": body, "status": status, "wire": wire}], target)
        (result,) = out["results"]
        assert (result["status"], result["code"]) == ("refused", "tool_unavailable"), target
        assert json.dumps(result["payload"]) == json.dumps(wire), target


def test_the_door_refuses_a_spelling_its_list_does_not_name_before_it_makes_any_request():
    for target in ("acceptpush", "accept_push", "push", "acceptPullrequest", "acceptPr",
                   "acceptPull", "accept_pull_request", "pullRequest"):
        out = _through_the_door([{"body": PUSH_BODIES[0], "status": 200, "wire": {}}], target)
        assert out["results"] == [{"status": "refused", "code": "route_not_found"}], target
        assert out["calls"] == [], target
