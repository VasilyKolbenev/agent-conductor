"""The guard of `Stack.post`: a refusal a live write answers is one its row lists (spec 4.6.3).

`tests/_hub_stack.py` judges every error answer of every write the hub tests make: its code must
be a transport refusal or one the route's row names. A code outside the row passes only as a
case `PENDING_RULING` names (module, route, code) and the call itself says so, so a code that
nobody asked a ruling for fails the test that met it, and a named case that stops answering its
code fails the call that waits for it. The guard is a check on the rows, so it is shown here to
name a code that is not listed, and to be quiet for the codes that are.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from conductor.hub import routes
from tests._hub_stack import (A, ASKED, FOUND, PENDING_RULING, TRANSPORT, Reply, Stack,
                              judge, undeclared)

FORGET = "POST", "/hub/projects/<project_id>/forget"
TARGET = f"/hub/projects/{A}/forget"
NAMED = frozenset({("tests.test_x", "POST /hub/projects/<project_id>/forget", "project_busy")})
#: What the table names today: the two cases of the question to the reviewer of the rows, and the
#: three the guard found beside them (not in that question).
ASKED_NOW = {
    ("tests.test_hub_handlers_http", "POST /hub/projects/<project_id>/forget", "project_busy"),
    ("tests.test_hub_handlers_http", "POST /hub/logins/<login_key>/recover", "operation_busy"),
}
FOUND_NOW = {
    ("tests.test_hub_http_surface", "POST /hub/projects/<project_id>/activate",
     "registry_invalid"),
    ("tests.test_hub_http_surface", "POST /hub/projects/<project_id>/view", "registry_invalid"),
    ("tests.test_hub_new_projects", "POST /hub/setup/projects-home", "operation_busy"),
}


def _error(status: int, code: str) -> Reply:
    body = {"error": {"code": code, "message": "x", "detail": {}}}
    return Reply(status, [], json.dumps(body).encode("utf-8"))


def _row(method: str, path: str) -> routes.HubRoute:
    return next(row for row in routes.HUB_ROUTES if (row.method, row.path) == (method, path))


@pytest.fixture
def stack(tmp_path):
    made = Stack(tmp_path)
    yield made
    made.close()


def test_the_guard_names_a_code_the_row_does_not_list():
    assert "project_busy" not in _row(*FORGET).refusals
    assert undeclared("POST", TARGET, _error(409, "project_busy")) == "project_busy"


def test_the_guard_passes_every_code_the_row_lists_and_every_transport_code():
    row = _row(*FORGET)
    assert set(row.refusals) == {"project_not_found", "project_running"}
    for code in (*row.refusals, *sorted(TRANSPORT)):
        assert undeclared("POST", TARGET, _error(409, code)) is None, code


def test_the_guard_judges_neither_a_success_nor_a_body_that_is_no_envelope_nor_an_unknown_target():
    assert undeclared("POST", TARGET, Reply(200, [], b'{"project_id": "x"}')) is None
    assert undeclared("POST", TARGET, Reply(500, [], b"not json")) is None
    assert undeclared("POST", TARGET, Reply(409, [], b'{"error": 3}')) is None
    assert undeclared("POST", "/hub/nothing", _error(409, "project_busy")) is None


def test_an_answer_outside_its_row_that_no_ruling_is_waiting_for_fails_the_test_that_met_it():
    with pytest.raises(AssertionError, match="answered 'project_busy', which its row does not"):
        judge("POST", TARGET, _error(409, "project_busy"), module="tests.test_x",
              pending=frozenset())
    with pytest.raises(AssertionError, match="answered 'project_busy', which its row does not"):
        judge("POST", TARGET, _error(409, "project_busy"), module="tests.test_y", pending=NAMED)


def test_a_call_that_waits_for_a_case_nobody_named_fails_before_it_looks_at_the_answer():
    with pytest.raises(AssertionError, match="is not named as waiting for a ruling"):
        judge("POST", TARGET, _error(409, "project_busy"), module="tests.test_x",
              unlisted="project_busy", pending=frozenset())
    with pytest.raises(AssertionError, match="is not named as waiting for a ruling"):
        judge("POST", TARGET, _error(409, "project_busy"), module="tests.test_x",
              unlisted="project_running", pending=NAMED)


def test_a_named_case_passes_when_the_call_names_it_and_that_code_is_what_came_back():
    judge("POST", TARGET, _error(409, "project_busy"), module="tests.test_x",
          unlisted="project_busy", pending=NAMED)


def test_a_named_case_that_stops_answering_its_code_fails_the_call_that_waits_for_it():
    for came in (_error(409, "project_running"), _error(409, "route_not_found"),
                 Reply(200, [], b'{"project_id": "x"}')):
        with pytest.raises(AssertionError, match="was to answer 'project_busy' outside its row"):
            judge("POST", TARGET, came, module="tests.test_x", unlisted="project_busy",
                  pending=NAMED)
    with pytest.raises(AssertionError, match="was to answer 'project_busy'.*answered 'other'"):
        judge("POST", TARGET, _error(409, "other"), module="tests.test_x",
              unlisted="project_busy", pending=NAMED)


def test_a_live_write_that_answers_a_code_outside_its_row_fails_in_a_module_no_ruling_names(stack):
    stack.world.gone("a")
    stack.service._operations.open_project_row("recover", A, "recover")     # stays running
    with pytest.raises(AssertionError, match="answered 'project_busy', which its row does not"):
        stack.post(TARGET)
    with pytest.raises(AssertionError, match="is not named as waiting for a ruling"):
        stack.post(TARGET, unlisted="project_busy")


def test_a_live_write_whose_row_lists_its_refusal_passes_the_guard(stack):
    assert stack.post(f"/hub/projects/{'f' * 32}/forget").status == 404


def test_the_cases_waiting_for_a_ruling_are_exactly_the_two_asked_and_the_three_found():
    assert set(ASKED) == ASKED_NOW and set(FOUND) == FOUND_NOW
    assert set(PENDING_RULING) == ASKED_NOW | FOUND_NOW


def test_each_case_waiting_for_a_ruling_is_a_live_row_that_does_not_list_its_code():
    for _module, route, code in sorted(PENDING_RULING):
        method, path = route.split(" ", 1)
        row = _row(method, path)
        assert code not in row.refusals and code not in TRANSPORT, (
            f"{route} lists {code!r} now: the ruling is made, remove it from PENDING_RULING")


def test_each_case_waiting_for_a_ruling_has_a_call_in_its_module_that_names_it():
    for module, route, code in sorted(PENDING_RULING):
        source = Path(importlib.import_module(module).__file__).read_text(encoding="utf-8")
        assert f'unlisted="{code}"' in source, f"{module} no longer waits for {code!r} on {route}"
