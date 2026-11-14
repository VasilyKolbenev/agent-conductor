"""The guard of `Stack.post`: a refusal a live write answers is one its row lists (spec 4.6.3).

`tests/_hub_stack.py` judges every error answer of every write any test makes through the stack:
its code must be a transport refusal or one the route's row names. There is no module outside the
guard, no list of cases that wait for a ruling and no keyword with which a call lets a code
through: a code outside the row fails the test that met it. The guard is a check on the rows, so
it is shown here to name a code that is not listed, and to be quiet for the codes that are.
"""
from __future__ import annotations

import inspect
import json

import pytest

from conductor.hub import lifecycle, refusals, routes
from conductor.hub.refusals import HubRefusal
from tests import _hub_stack
from tests._hub_stack import A, TRANSPORT, Reply, Stack, judge, undeclared

FORGET = "POST", "/hub/projects/<project_id>/forget"
TARGET = f"/hub/projects/{A}/forget"
#: A code that none of the lists read by `_lists_of_codes` holds: the guard must name it on any
#: route.
UNKNOWN = "a_code_no_list_of_the_hub_holds"


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


def _lists_of_codes() -> dict[str, frozenset[str]]:
    """The lists of codes this test reads: the two closed lists of the spec, the transport names,
    the state codes a project can carry, and the refusals the rows name.

    The hub keeps other lists that are not read here, among them the proposed codes of the
    registry and of the state file, the refusals of the state file, the codes of the supervisor
    and of adding a project, the reasons beside an operation's detail and the file reasons of
    the tool pins (`service.PIN_FILE_REASONS`): what the test shows of its unknown code is that
    it is in none of the lists read.
    """
    return {
        "the route refusals": frozenset(refusals.HUB_ERROR_STATUS),
        "the operation codes": refusals.OPERATION_ERROR_CODES,
        "the transport names": TRANSPORT,
        "the state codes": lifecycle.STATE_CODES,
        "the refusals of the rows": frozenset(
            code for row in routes.HUB_ROUTES for code in row.refusals),
    }


def test_the_guard_names_a_code_the_row_does_not_list():
    lists = _lists_of_codes()
    assert all(lists.values()), "control: each list read holds codes"
    assert [name for name, codes in lists.items() if UNKNOWN in codes] == []
    assert undeclared("POST", TARGET, _error(409, UNKNOWN)) == UNKNOWN
    assert undeclared("GET", "/hub/limits", _error(409, UNKNOWN)) == UNKNOWN


def test_the_guard_passes_every_code_the_row_lists_and_every_transport_code():
    row = _row(*FORGET)
    assert set(row.refusals) == {"project_not_found", "project_running", "project_busy",
                                 "registry_invalid"}
    for code in (*row.refusals, *sorted(TRANSPORT)):
        assert undeclared("POST", TARGET, _error(409, code)) is None, code


def test_the_guard_judges_neither_a_success_nor_a_body_that_is_no_envelope_nor_an_unknown_target():
    assert undeclared("POST", TARGET, Reply(200, [], b'{"project_id": "x"}')) is None
    assert undeclared("POST", TARGET, Reply(500, [], b"not json")) is None
    assert undeclared("POST", TARGET, Reply(409, [], b'{"error": 3}')) is None
    assert undeclared("POST", "/hub/nothing", _error(409, UNKNOWN)) is None


def test_an_answer_outside_its_row_fails_the_judge_and_names_the_code():
    with pytest.raises(AssertionError, match=f"answered '{UNKNOWN}', which its row does not"):
        judge("POST", TARGET, _error(409, UNKNOWN))


def test_an_answer_the_row_lists_passes_the_judge():
    judge("POST", TARGET, _error(409, "project_busy"))
    judge("POST", TARGET, _error(409, "registry_invalid"))
    judge("POST", TARGET, _error(403, "csrf_denied"))
    judge("POST", TARGET, Reply(200, [], b'{"project_id": "x"}'))


def _forget_while_its_own_operation_runs(stack) -> None:
    stack.world.gone("a")
    stack.service._operations.open_project_row("recover", A, "recover")     # stays running


def test_a_live_write_that_answers_a_code_outside_its_row_fails_the_test_that_met_it(
        stack, monkeypatch):
    def forget(_project_id):
        raise HubRefusal("project_unavailable")        # a code of the route list, not of this row
    monkeypatch.setattr(stack.service, "forget", forget)
    with pytest.raises(AssertionError, match="answered 'project_unavailable', which its row does"):
        stack.post(TARGET)


def test_a_live_write_whose_row_lists_its_refusal_passes_the_guard(stack):
    assert stack.post(f"/hub/projects/{'f' * 32}/forget").status == 404
    _forget_while_its_own_operation_runs(stack)
    reply = stack.post(TARGET)
    assert (reply.status, reply.json()["error"]["code"]) == (409, "project_busy")


def test_nothing_in_the_stack_lets_an_answer_outside_its_row_through():
    for name in ("JUDGED", "PENDING_RULING"):
        assert not hasattr(_hub_stack, name), name
    assert list(inspect.signature(judge).parameters) == ["method", "target", "reply"]
    assert "unlisted" not in inspect.signature(Stack.post).parameters
