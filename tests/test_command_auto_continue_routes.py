"""`GET` and `POST /command/project/auto-continue` through the router (spec 4.3.4, 4.4.9).

The door itself (the file, the closed body, the binding of each run, the conditional consume) is
lane H's `command/auto_continue.py` and is tested in `test_auto_continue.py`. What is lane L's is
the row: the path is the fifth that both verbs reach, it is handled the same in `active` and in
`view`, a third verb on it is `method_not_allowed`, a query string is `route_not_found`, and the
answers the desk and the hub are written against are the ones H measured over a real socket, here
walked through `CommandApi.handle`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conductor.command.command_routes import COMMAND_ROUTES, match_route
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.queue_routes import make_queue
from tests.queue_fixtures import Holder, project, start_body
from tests.test_command_http_api import PORT, TOKEN, get_headers, post

PATH = "/command/project/auto-continue"
PROJECT_ID = "a" * 32
TRANSITION = "b71e4d09-c2a8-4f35-a6d8-1c0e9f3b5274"
ABSENT_FORM = {"schema_version": 2, "flag_id": None, "revision": 0, "enabled": False,
               "actor": None, "set_at": None, "resume_runs": [], "start_task_queue": False,
               "consumed": None}


def door(tmp_path, mode="active", *, handed=None, granted=False):
    """A real API over a project; `granted` gives `run` a grant while a driver still exists."""
    f = project(tmp_path)
    f.policy.driver = Holder()
    if granted:
        f.policy.authorize("run", start_body(f, "run", "grant-run"))
    f.policy.driver = Holder() if mode == "active" else None
    identity = ProjectIdentity(PROJECT_ID, None, False, mode,
                               None if handed is None else TRANSITION, handed)
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=PRODUCT_COMMAND_BUDGET, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=lambda run_id: None, identity=identity)
    api._policy = f.policy
    api._queue = make_queue(api)
    return SimpleNamespace(f=f, api=api)


def read(w):
    return w.api.handle("GET", PATH, get_headers())


def write(w, **body):
    return post(w.api, PATH, {"enabled": True, "actor": "Вы: Анна", "resume_runs": ["run"],
                              "start_task_queue": True, **body})


def error(answer):
    return answer.status, answer.payload["error"]["code"], answer.payload["error"]["detail"]


def test_the_table_names_the_two_rows_after_the_cycle_pin():
    rows = list(COMMAND_ROUTES)
    at = rows.index(("POST", "/command/project/cycle/pin"))
    assert rows[at + 1:at + 3] == [("GET", PATH), ("POST", PATH)]


def test_the_path_names_one_route_for_both_verbs_and_the_other_verbs_are_refused():
    from conductor.command.api_contracts import ApiRefusal
    for method in ("GET", "POST"):
        assert match_route(method, PATH).name == "project_auto_continue"
    for method in ("DELETE", "PUT", "PATCH"):
        with pytest.raises(ApiRefusal) as refused:
            match_route(method, PATH)
        assert refused.value.code == "method_not_allowed"
    for path in (PATH + "/", PATH + "/x", "/command/project/auto-continues",
                 "/command/project/auto_continue"):
        with pytest.raises(ApiRefusal) as refused:
            match_route("GET", path)
        assert refused.value.code == "route_not_found"


def test_a_query_string_is_route_not_found(tmp_path):
    w = door(tmp_path)
    assert error(w.api.handle("GET", PATH + "?x=1", get_headers())) == (
        404, "route_not_found", {})


@pytest.mark.parametrize("mode", ["active", "view"])
def test_the_door_answers_the_same_walk_in_both_modes(tmp_path, mode):
    w = door(tmp_path, mode, granted=True)
    assert read(w).payload == ABSENT_FORM and read(w).status == 200
    assert error(post(w.api, PATH, {})) == (422, "contract_invalid", {})
    assert error(write(w, set_at="2026-01-01T00:00:00Z"))[1] == "contract_invalid"
    ghost = write(w, resume_runs=["ghost"])
    assert error(ghost) == (422, "contract_invalid", {"run_id": "ghost"})
    assert read(w).payload == ABSENT_FORM                  # nothing written by a refusal
    on = write(w)
    assert on.status == 200 and on.payload["revision"] == 1 and on.payload["enabled"] is True
    assert on.payload["resume_runs"][0]["run_id"] == "run" and read(w).payload == on.payload
    again = write(w)
    assert again.payload["revision"] == 2 and again.payload["flag_id"] != on.payload["flag_id"]
    off = write(w, enabled=False, resume_runs=[], start_task_queue=False)
    assert off.payload["revision"] == 3 and off.payload["flag_id"] == again.payload["flag_id"]
    assert off.payload["enabled"] is False
    assert write(w, enabled=False, resume_runs=[], start_task_queue=False).payload == off.payload
    assert error(write(w, enabled=False))[1] == "contract_invalid"     # off names runs: refused


def test_the_queue_is_built_with_the_hand_over_of_the_identity_and_the_flag_file(tmp_path):
    handed = "5a4b3c2d-1e0f-4a9b-8c7d-6e5f4a3b2c1d@4"
    w = door(tmp_path, handed=handed)
    queue = w.api._queue
    assert (queue.project_id, queue.transition_id, queue.auto_continue) == (
        PROJECT_ID, TRANSITION, handed)
    assert queue.flags is w.api._flag and queue.hands_over_a_flag()
    standalone = door(tmp_path / "second")
    assert not standalone.api._queue.hands_over_a_flag()
    viewing = door(tmp_path / "third", "view", handed=handed)
    assert not viewing.api._queue.hands_over_a_flag()
