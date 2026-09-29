"""`GET /command/project` and the project claim, through the router (spec 4.5.1, 12.4).

Lane H wrote the handler (`project_claim.read_project`) and the table of the claim
(`ProjectIdentity.check`) and tested them without a router. These are the same facts reached the
way a desk reaches them: a request into `CommandApi.handle`, so the row of the table, the
constructor parameter, the one `check` call and the `read_route` branch each have a test that
fails when the line is missing or stands in the wrong place. The cases are the ones lane H walked
over a real socket (`H-to-L-project-route.md`), one test each.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import HEADER, UNCLAIMED, ProjectIdentity
from conductor.command.run_store import RunStore

from tests.test_command_adapters import FakeAdapter
from tests.test_command_http_api import (
    NOW, PORT, TOKEN, encode, get_headers, ids, post_headers)

PROJECT_ID = "ab" * 16
OTHER_ID = "cd" * 16
ORIGIN = "http://127.0.0.1:7700"
IDENTITY = ProjectIdentity(PROJECT_ID, ORIGIN, False, "active", None, None)
PATH = "/command/project"


def serving(tmp_path, identity=IDENTITY, **more):
    """One API over an empty project, with the identity a server would build for itself."""
    events = []
    subject = CommandApi(
        RunStore(tmp_path), AdapterRegistry([FakeAdapter()]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=events.append, identity=identity, **more)
    return subject, events


def read(subject, path=PATH, *claims, host=None):
    headers = get_headers() if host is None else get_headers(host)
    return subject.handle("GET", path, (*headers, *((HEADER, claim) for claim in claims)))


def write(subject, path, body, *claims, **transport):
    headers = post_headers(body, **transport)
    return subject.handle(
        "POST", path, (*headers, *((HEADER, claim) for claim in claims)), encode(body))


def refused(answer):
    return answer.status, answer.payload["error"]["code"]


# --- the read ------------------------------------------------------------------------------------


def test_the_project_read_answers_the_identity_in_exactly_four_keys(tmp_path):
    subject, _ = serving(tmp_path)
    answer = read(subject)
    assert answer.status == 200
    assert answer.payload == {
        "project_id": PROJECT_ID, "hub_origin": ORIGIN, "demo": False, "mode": "active"}


def test_a_project_read_that_names_the_right_project_is_answered_like_one_that_names_none(
        tmp_path):
    subject, _ = serving(tmp_path)
    assert read(subject, PATH, PROJECT_ID).payload == read(subject).payload


def test_a_server_built_without_an_identity_answers_the_unclaimed_one(tmp_path):
    events = []
    subject = CommandApi(
        RunStore(tmp_path), AdapterRegistry([FakeAdapter()]),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=lambda: NOW, ids=ids(), publish_run=events.append)
    assert read(subject).payload == UNCLAIMED.payload()
    assert refused(read(subject, PATH, PROJECT_ID)) == (409, "project_mismatch")


def test_the_project_read_is_get_only_and_writes_and_publishes_nothing(tmp_path):
    subject, events = serving(tmp_path)
    wrong = write(subject, PATH, {})
    assert refused(wrong) == (405, "method_not_allowed")
    read(subject)
    assert events == [] and not list(tmp_path.rglob("*.json*"))


def test_a_constructor_refuses_an_identity_that_is_not_a_project_identity(tmp_path):
    with pytest.raises(TypeError, match="ProjectIdentity"):
        serving(tmp_path, identity={"project_id": PROJECT_ID})


# --- the claim, on the read road and on the write road ---------------------------------------------


@pytest.mark.parametrize("claims", [(OTHER_ID,), ("not-an-id",), (PROJECT_ID, PROJECT_ID)],
                         ids=["another project", "not a grammar", "the right one twice"])
def test_a_wrong_claim_on_a_read_is_project_mismatch_whatever_the_route(tmp_path, claims):
    subject, _ = serving(tmp_path)
    for path in (PATH, "/command/session", "/command/workflows"):
        answer = read(subject, path, *claims)
        assert refused(answer) == (409, "project_mismatch"), path
        assert answer.payload["error"]["detail"] == {}
        assert not any(claim in str(answer.payload) for claim in claims if claim != PROJECT_ID)


def test_a_lowercase_header_name_is_the_same_claim(tmp_path):
    subject, _ = serving(tmp_path)
    headers = (*get_headers(), (HEADER.lower(), OTHER_ID))
    assert refused(subject.handle("GET", PATH, headers)) == (409, "project_mismatch")


def test_the_right_claim_reaches_the_session_read_and_a_wrong_one_does_not(tmp_path):
    subject, _ = serving(tmp_path)
    assert read(subject, "/command/session", PROJECT_ID).status == 200
    assert refused(read(subject, "/command/session", OTHER_ID)) == (409, "project_mismatch")


def test_a_wrong_claim_on_a_write_is_refused_before_the_body_is_read_and_writes_nothing(
        tmp_path):
    subject, events = serving(tmp_path)
    task = {"task_id": "task-claim-1", "title": "Claimed"}
    assert refused(write(subject, "/command/tasks", task, OTHER_ID)) == (409, "project_mismatch")
    assert read(subject, "/command/tasks").payload == {"tasks": []} and events == []
    assert write(subject, "/command/tasks", task, PROJECT_ID).status == 201


def test_the_right_claim_lets_a_body_that_is_wrong_reach_the_contract(tmp_path):
    subject, _ = serving(tmp_path)
    answer = write(subject, "/command/tasks", {}, PROJECT_ID)
    assert refused(answer) == (422, "contract_invalid")


# --- the order of the transport does not change --------------------------------------------------------


def test_a_wrong_host_with_a_wrong_claim_is_a_wrong_host(tmp_path):
    subject, _ = serving(tmp_path)
    answer = read(subject, PATH, OTHER_ID, host="attacker.test")
    assert refused(answer) == (403, "same_origin_denied")


def test_a_wrong_csrf_token_with_a_wrong_claim_is_a_wrong_token(tmp_path):
    subject, _ = serving(tmp_path)
    answer = write(subject, "/command/tasks", {}, OTHER_ID, token="stale-token")
    assert refused(answer) == (403, "csrf_denied")


def test_a_wrong_origin_with_a_wrong_claim_is_a_wrong_origin(tmp_path):
    subject, _ = serving(tmp_path)
    answer = write(subject, "/command/tasks", {}, OTHER_ID, origin="http://attacker.test")
    assert refused(answer) == (403, "same_origin_denied")
