"""The write target `gitSetup` goes through the one mutation door and brings a refusal back whole.

`desk-transport.js` opens the wizard's Git step as the target `gitSetup` (spec 5.6.8, 12): one POST
path, four closed bodies, the session token and the refusal door of every other closed target. The
real module runs under Node with a fake `fetch`, so what is held here is what the door puts on the
wire and what it hands back. The refusal bodies are the server's own: `ApiRefusal` builds each one
and its `as_dict()` is what the fake answers. The wizard reads `error.detail` off the payload, the
one `reason` and, for `signing_required`, the four facts the owner's two commands are built from, so
the door must hand it back as it came and never rebuild it.
"""
from __future__ import annotations

import json

from conductor.command.api_refusals import ERROR_STATUS, GIT_SETUP_REASONS, ApiRefusal
from tests.desk_node import run_js

MODULES = {"transport": "desk-transport.js"}
ORIGIN = "http://127.0.0.1:7777"
SETUP_PATH = "/command/project/git/setup"
TREE = "a" * 40
MESSAGE = "conductor.v3/git/msg-first-" + "c" * 32 + ".txt"
FOUR = {"reason", "tree", "target_ref", "message_path"}
#: The four closed bodies of the route (the confirm twice: with a digest and without one).
BODIES = [
    {"step": "init", "actor": "Owner"},
    {"step": "exclude", "actor": "Owner"},
    {"step": "first_commit", "mode": "snapshot", "preview": True},
    {"step": "first_commit", "mode": "snapshot", "paths_digest": "sha256:" + "d" * 64,
     "actor": "Owner"},
    {"step": "first_commit", "mode": "empty", "paths_digest": None, "actor": "Owner"},
]
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


def _through_the_door(answers: list[dict], target: str = "gitSetup") -> dict:
    """Submit `target` once per row of `answers` and return its answers and the requests made."""
    return run_js(FAKE_WIRE + """
      const results = [];
      for (const row of d.answers) results.push(await door.submit(d.target, null, row.body));
      console.log(JSON.stringify({results, calls}));
    """, MODULES, {"origin": ORIGIN, "answers": answers, "target": target})


def _refusals() -> list[dict]:
    """The wire body of the signing refusal, then one of each other reason of the route."""
    signing = ApiRefusal.signing_required_setup(TREE, "refs/heads/trunk", MESSAGE).as_dict()
    others = [ApiRefusal.git_setup_refused(reason).as_dict()
              for reason in GIT_SETUP_REASONS if reason != "signing_required"]
    return [signing, *others]


def test_the_git_setup_target_posts_each_closed_body_to_the_setup_route_under_one_token():
    answers = [{"body": body, "status": 201, "wire": {"step": body["step"]}} for body in BODIES]
    out = _through_the_door(answers)
    assert [call["url"] for call in out["calls"]] == ["/command/session"] + [SETUP_PATH] * 5
    first, *writes = out["calls"]
    assert first["method"] == "GET"
    for call, body in zip(writes, BODIES, strict=True):
        assert call["method"] == "POST" and json.loads(call["body"]) == body
        assert call["headers"]["X-Conduct-CSRF"] == "tok"
        assert call["headers"]["Content-Type"] == "application/json"
    assert out["results"] == [{"status": "accepted", "payload": row["wire"]} for row in answers]


def test_a_git_setup_refusal_comes_back_with_its_detail_exactly_as_the_server_wrote_it():
    wires = _refusals()
    assert set(wires[0]["error"]["detail"]) == FOUR
    assert all(set(wire["error"]["detail"]) == {"reason"} for wire in wires[1:])
    assert len(wires) == len(GIT_SETUP_REASONS)
    status = ERROR_STATUS["git_setup_refused"]
    out = _through_the_door([{"body": BODIES[0], "status": status, "wire": wire}
                             for wire in wires])
    assert len(out["results"]) == len(wires)
    for result, wire in zip(out["results"], wires, strict=True):
        assert (result["status"], result["code"]) == ("refused", "git_setup_refused")
        assert json.dumps(result["payload"]) == json.dumps(wire)


def test_the_door_refuses_a_target_its_list_does_not_name_before_it_makes_any_request():
    for target in ("gitsetup", "git_setup", "setup"):
        out = _through_the_door([{"body": BODIES[0], "status": 201, "wire": {}}], target)
        assert out["results"] == [{"status": "refused", "code": "route_not_found"}], target
        assert out["calls"] == [], target
