"""The write target `cyclePin` goes through the one mutation door to the live pin route.

`desk-transport.js` names the project's pinned cycle as a write target (spec 7.10, 5.6.8): one
POST path, the closed body `{workflow_id, actor}` (a workflow id, or null to unpin) and the
session token and the refusal door of every other closed target. The wizard and the header of the
Schema write the pin through it; the read of the pin is the path `projectCycle`, which was
already there. The real module runs under Node with a fake `fetch`. What it puts on the wire is
then handed to the server's own route table and the pin handler over a real template store, so
the name, the path and the body are held against the route they claim, not against a copy of it.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.api_refusals import ApiRefusal
from conductor.command.command_routes import match_route
from tests.desk_node import run_js
from tests.test_command_flow_routes import ACTOR, WORKFLOW_ID, good, pinning, write
from tests.test_command_workflow_routes import api, code_of, get, post
from tests.test_desk_transport_git_setup import _through_the_door

MODULES = {"transport": "desk-transport.js"}
PIN_PATH = "/command/project/cycle/pin"
CYCLE_PATH = "/command/project/cycle"
PIN = {"workflow_id": WORKFLOW_ID, "actor": ACTOR}
UNPIN = {"workflow_id": None, "actor": ACTOR}


def _paths(names: list[str]) -> list[str]:
    """`path.<name>()` for each name, under Node."""
    return run_js("console.log(JSON.stringify(d.map((name) => transport.path[name]())));",
                  MODULES, names)


def _pinned(subject) -> dict:
    return get(subject, CYCLE_PATH).payload


def test_the_pin_target_is_the_post_only_pin_route_beside_the_get_only_cycle_read():
    read, pin = _paths(["projectCycle", "cyclePin"])
    assert (read, pin) == (CYCLE_PATH, PIN_PATH)
    assert match_route("GET", read).name == "project_cycle"
    assert match_route("POST", pin).name == "project_cycle_pin"
    for method, path in (("POST", read), ("GET", pin)):
        with pytest.raises(ApiRefusal) as refused:
            match_route(method, path)
        assert refused.value.code == "method_not_allowed", (method, path)


def test_the_pin_target_posts_the_pin_and_the_unpin_body_to_the_pin_route_under_one_token():
    answers = [{"body": body, "status": 200, "wire": {"pinned": None}} for body in (PIN, UNPIN)]
    out = _through_the_door(answers, "cyclePin")
    assert [call["url"] for call in out["calls"]] == ["/command/session", PIN_PATH, PIN_PATH]
    first, *writes = out["calls"]
    assert first["method"] == "GET"
    for call, body in zip(writes, (PIN, UNPIN), strict=True):
        assert call["method"] == "POST" and json.loads(call["body"]) == body
        assert call["headers"]["X-Conduct-CSRF"] == "tok"
        assert call["headers"]["Content-Type"] == "application/json"
    assert out["results"] == [{"status": "accepted", "payload": {"pinned": None}}] * 2


def test_what_the_door_sends_for_a_pin_and_an_unpin_is_taken_by_the_live_route_and_read_back(
        tmp_path):
    subject, *_ = api(tmp_path)
    assert write(subject, good(), publish=1).status == 201
    out = _through_the_door([{"body": body, "status": 200, "wire": {}} for body in (PIN, UNPIN)],
                            "cyclePin")
    pin, unpin = out["calls"][1:]
    assert pin["url"] == unpin["url"] == PIN_PATH
    pinned = post(subject, pin["url"], json.loads(pin["body"]))
    assert pinned.status == 200 and pinned.payload["pinned"]["workflow_id"] == WORKFLOW_ID
    assert pinned.payload["pinned"]["set_by"] == ACTOR
    assert _pinned(subject) == pinned.payload
    unpinned = post(subject, unpin["url"], json.loads(unpin["body"]))
    assert (unpinned.status, unpinned.payload) == (200, {"pinned": None})
    assert _pinned(subject) == {"pinned": None}


def test_a_pin_the_server_refuses_comes_back_through_the_door_as_the_server_wrote_it(tmp_path):
    subject, *_ = api(tmp_path)
    refused = pinning(subject)                 # no revision is published: nothing to pin
    assert (refused.status, code_of(refused)) == (422, "contract_invalid")
    out = _through_the_door([{"body": PIN, "status": refused.status, "wire": refused.payload}],
                            "cyclePin")
    result, = out["results"]
    assert (result["status"], result["code"]) == ("refused", "contract_invalid")
    assert json.dumps(result["payload"]) == json.dumps(refused.payload)
