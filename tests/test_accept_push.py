"""The push step of an accepted result (spec 9.7): its door, its bodies and what it asks first."""
from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.api_refusals import (
    ACCEPT_REASONS, PR_MISMATCH_REASONS, ApiRefusal, _reviewed_fact)
from conductor.command.command_routes import Route, match_route
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from tests.test_accept_context import RUN, prepared
from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import NOW, PORT, TOKEN, api as http_api, ids, post

PATH = f"/command/runs/{RUN}/accept/push"
ACCEPTANCE = "acc-" + "a" * 32
TERMS = {"acceptance_id": ACCEPTANCE, "remote": "origin", "preview": True}
CONFIRM = {"acceptance_id": ACCEPTANCE, "remote": "origin",
           "push_digest": "sha256:" + "b" * 64, "actor": "Owner"}
NEW_REASONS = (
    "push_requires_commit", "push_not_permitted", "push_rejected", "push_terms_changed",
    "push_url_ambiguous", "push_destination_mismatch", "remote_url_has_credentials",
    "push_auth_failed", "push_timed_out", "push_unconfirmed", "pr_requires_push",
    "gh_not_logged_in", "pr_mismatch", "pr_create_failed")
NOTICE = Path(__file__).parents[1] / "src/conductor/panel/studio-notice-copy.js"


def active(tmp_path):
    """A finished run whose project is served for work; its git reader fails the test if asked."""
    api = prepared(tmp_path)
    api._identity = ProjectIdentity("a" * 32, None, False, "active", None, None)
    return api


def code_of(answer):
    return answer.payload["error"]["code"], answer.payload["error"].get("detail")


def test_the_push_and_the_pull_request_are_two_routes_that_take_post_only():
    for tail, name in (("push", "accept_push"), ("pull-request", "accept_pull_request")):
        path = f"/command/runs/{RUN}/accept/{tail}"
        assert match_route("POST", path) == Route(name, RUN)
        with pytest.raises(ApiRefusal) as wrong:
            match_route("GET", path)
        assert wrong.value.code == "method_not_allowed"
        with pytest.raises(ApiRefusal) as absent:
            match_route("POST", path + "ed")
        assert absent.value.code == "route_not_found"
    assert match_route("GET", f"/command/runs/{RUN}/accept") == Route("accept", RUN)


def test_a_server_started_to_view_the_project_refuses_the_push_before_it_reads_the_body(tmp_path):
    api = prepared(tmp_path)                    # a view server: its git reader fails if asked
    for body in (TERMS, CONFIRM, {}):
        assert code_of(post(api, PATH, body)) == ("project_not_active", {})


@pytest.mark.parametrize("body", [
    {}, {**TERMS, "actor": "Owner"}, {**TERMS, "preview": False}, {**TERMS, "preview": 1},
    {**TERMS, "check": True}, {"acceptance_id": ACCEPTANCE, "remote": "origin"},
    {k: v for k, v in CONFIRM.items() if k != "actor"},
    {k: v for k, v in CONFIRM.items() if k != "push_digest"},
    {**CONFIRM, "preview": True}, {**CONFIRM, "check": False}, {**CONFIRM, "check": 1},
    {**CONFIRM, "unknown": 1}, {**CONFIRM, "acceptance_id": "acc-" + "A" * 32},
    {**CONFIRM, "acceptance_id": "acc-" + "a" * 31}, {**CONFIRM, "remote": "-origin"},
    {**CONFIRM, "remote": ""}, {**CONFIRM, "remote": 1}, {**CONFIRM, "actor": ""},
    {**CONFIRM, "push_digest": "sha256:" + "B" * 64}, {**CONFIRM, "push_digest": None}])
def test_the_push_body_is_exactly_the_terms_or_the_confirmation(tmp_path, body):
    assert post(active(tmp_path), PATH, body).payload["error"]["code"] == "contract_invalid"


def test_a_check_press_is_the_confirmation_with_one_more_key():
    from conductor.command.accept_push import parse_body
    assert parse_body(CONFIRM).check is False and parse_body(CONFIRM).preview is False
    assert parse_body({**CONFIRM, "check": True}).check is True
    assert parse_body(TERMS).preview is True


@pytest.mark.parametrize("body", [TERMS, CONFIRM, {**CONFIRM, "check": True}])
def test_the_push_needs_a_recorded_commit_before_it_asks_anything_else(tmp_path, body):
    answer = post(active(tmp_path), PATH, body)
    assert answer.status == 409
    assert code_of(answer) == ("accept_refused", {"reason": "push_requires_commit"})


def test_every_reason_of_the_push_and_the_pull_request_stands_with_both_languages():
    copy = NOTICE.read_text(encoding="utf-8")
    for reason in NEW_REASONS:
        assert reason in ACCEPT_REASONS
        assert f'"accept.reason.{reason}": [' in copy
        assert ApiRefusal.accept_refused(reason).as_dict()["error"]["detail"] == {"reason": reason}
    assert len(set(ACCEPT_REASONS)) == len(ACCEPT_REASONS)


def test_a_pull_request_mismatch_names_one_word_of_the_closed_list():
    assert PR_MISMATCH_REASONS == (
        "remote_head_moved", "other_head", "other_base", "cross_repository")
    for word in PR_MISMATCH_REASONS:
        refusal = ApiRefusal.pr_mismatch(word)
        assert refusal.status == 409
        assert refusal.as_dict()["error"]["detail"] == {"reason": "pr_mismatch", "mismatch": word}
    for forged in ("", "head moved", "other_head ", None, 1):
        with pytest.raises(ValueError):
            ApiRefusal.pr_mismatch(forged)
    message = "the result cannot be accepted: pr_mismatch (other_head)"
    assert _reviewed_fact("accept_refused", message,
                          {"reason": "pr_mismatch", "mismatch": "other_head"})
    assert not _reviewed_fact("accept_refused", message,
                              {"reason": "git_failed", "mismatch": "other_head"})
    assert not _reviewed_fact("accept_refused", message,
                              {"reason": "pr_mismatch", "mismatch": "free text"})


def test_the_command_api_holds_a_gh_reader_beside_the_git_reader(tmp_path):
    subject, store, _events = http_api(tmp_path)
    assert subject._project_gh is None

    def build(**more):
        return CommandApi(store, AdapterRegistry([FakeAdapter()]), session=CommandSession(
            PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=ids(),
            publish_run=lambda _: None, **more)

    def reader(args, **keywords):
        return None

    assert build(project_gh=reader)._project_gh is reader
    with pytest.raises(TypeError, match="gh reader"):
        build(project_gh="gh")
