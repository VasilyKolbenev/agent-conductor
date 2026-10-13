"""The pull request step of an accepted result (spec 9.7): its door, its body and its first gate."""
import pytest

from conductor.command.accept_pull_request import BODY_LIMIT, TITLE_LIMIT, parse_body
from tests.test_accept_push import ACCEPTANCE, active, code_of
from tests.test_accept_context import RUN
from tests.test_command_http_api import post

PATH = f"/command/runs/{RUN}/accept/pull-request"
BODY = {"acceptance_id": ACCEPTANCE, "base": "main", "title": "Add the result",
        "body": "Line one\nLine two\n", "draft": False, "actor": "Owner"}


def test_a_server_started_to_view_the_project_refuses_the_pull_request_before_the_body(tmp_path):
    from tests.test_accept_context import prepared
    api = prepared(tmp_path)
    for body in (BODY, {}):
        assert code_of(post(api, PATH, body)) == ("project_not_active", {})


@pytest.mark.parametrize("change", [
    {"acceptance_id": "acc-short"}, {"base": ""}, {"base": "-main"}, {"base": "a..b"},
    {"base": "a//b"}, {"base": "main/"}, {"base": "x.lock"}, {"base": "has space"},
    {"base": 1}, {"title": ""}, {"title": "  "}, {"title": "two\nlines"}, {"title": "x" * 257},
    {"title": 1}, {"body": 1}, {"body": "x" * (BODY_LIMIT + 1)}, {"body": "nul\x00inside"},
    {"body": "bell\x07"}, {"body": "\ud800"}, {"draft": "false"}, {"draft": 0}, {"draft": None},
    {"actor": ""}, {"actor": 1}, {"check": False}, {"check": 1}, {"unknown": 1}])
def test_the_pull_request_body_is_exactly_its_closed_shape(tmp_path, change):
    answer = post(active(tmp_path), PATH, {**BODY, **change})
    assert answer.payload["error"]["code"] == "contract_invalid"


@pytest.mark.parametrize("missing", sorted(set(BODY)))
def test_a_pull_request_body_without_one_of_its_keys_is_refused(tmp_path, missing):
    body = {key: value for key, value in BODY.items() if key != missing}
    assert post(active(tmp_path), PATH, body).payload["error"]["code"] == "contract_invalid"


def test_an_exact_body_is_read_whole_and_a_check_press_is_the_same_body_with_one_key():
    plain, check = parse_body(BODY), parse_body({**BODY, "check": True})
    assert (plain.check, check.check) == (False, True)
    assert (plain.base, plain.title, plain.body, plain.draft) == (
        "main", "Add the result", "Line one\nLine two\n", False)
    assert parse_body({**BODY, "title": "x" * TITLE_LIMIT, "body": "", "base": "release/1.0"})
    assert parse_body({**BODY, "body": "ж" * BODY_LIMIT}).body == "ж" * BODY_LIMIT


def test_the_pull_request_needs_a_recorded_push_before_it_asks_anything_else(tmp_path):
    api = active(tmp_path)
    for body in (BODY, {**BODY, "check": True}):
        answer = post(api, PATH, body)
        assert answer.status == 409
        assert code_of(answer) == ("accept_refused", {"reason": "pr_requires_push"})
