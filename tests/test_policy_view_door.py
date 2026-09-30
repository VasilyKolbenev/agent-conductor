"""The door of a process that starts nothing: authorize and resume say `project_not_active`.

A process opened for viewing builds no policy driver (spec 4.3.1). Past the owner check a missing
driver therefore means exactly that mode, and authorize and resume refuse `project_not_active`
before `hold_activation`, where they used to say `contract_invalid` with a sentence nobody could
act on (spec 4.4.1, 11.1). The order of the refusals is part of the claim: the owner first, an
unsettled action before the mode on resume, and a human's pause or revoke still works, because
withdrawing permission starts nothing.
"""
from __future__ import annotations

import pytest

from conductor.command.api_refusals import ApiRefusal
from conductor.command.contract_values import ContractError
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.runtime_values import AuthorizationError
from tests.test_command_http_api import PORT, TOKEN, post
from tests.test_policy_runtime import ASK, approve, pause, propose, setup

CODE = "project_not_active"


def journal(f):
    return f.store.read("run").records


def authorize_body(f):
    preview = f.policy.preview("run", ASK)
    return {"authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None}


def resume_body(grant, expected):
    return {"control_id": "resume", "authorization_id": grant.authorization_id,
            "authorization_digest": grant.authorization_digest, "action": "resume",
            "actor": "owner", "expected_control_id": expected}


def door(f):
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=lambda run_id: None)
    api._policy = f.policy
    return api


def test_authorize_without_a_driver_is_project_not_active_and_writes_nothing(tmp_path):
    f = setup(tmp_path)
    body = authorize_body(f)
    f.policy.driver = None
    before = journal(f)
    with pytest.raises(ApiRefusal) as refused:
        f.policy.authorize("run", body)
    assert (refused.value.status, refused.value.code, dict(refused.value.detail)) == (
        409, CODE, {})
    assert refused.value.message == "the project is open for viewing and starts no agent"
    assert journal(f) == before


def test_resume_without_a_driver_is_project_not_active_and_writes_nothing(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    pause(f, grant)
    f.policy.driver = None
    before = journal(f)
    with pytest.raises(ApiRefusal) as refused:
        f.policy.control("run", resume_body(grant, "pause"))
    assert (refused.value.status, refused.value.code) == (409, CODE)
    assert journal(f) == before


def test_pause_and_revoke_without_a_driver_still_write_because_they_start_nothing(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    f.policy.driver = None
    paused, created = f.policy.control("run", {**resume_body(grant, None), "control_id": "pause",
                                               "action": "pause"})
    assert created and paused.action == "pause"
    revoked, created = f.policy.control("run", {**resume_body(grant, "pause"),
                                                "control_id": "revoke", "action": "revoke"})
    assert created and revoked.action == "revoke"


def test_an_unsettled_action_refuses_resume_before_the_mode_is_judged(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    propose(f)
    f.runtime.authorize_policy("run", "proposal", grant.authorization_id)  # an open action
    pause(f, grant)
    f.policy.driver = None
    before = journal(f)
    with pytest.raises(ContractError, match="settled") as refused:
        f.policy.control("run", resume_body(grant, "pause"))
    assert not isinstance(refused.value, ApiRefusal)
    assert journal(f) == before


@pytest.mark.parametrize("which", ["authorize", "resume"])
def test_a_missing_owner_is_refused_before_the_mode_is_judged(tmp_path, which):
    f = setup(tmp_path)
    if which == "authorize":
        call, body = f.policy.authorize, authorize_body(f)
    else:
        grant, _ = approve(f)
        pause(f, grant)
        call, body = f.policy.control, resume_body(grant, "pause")
    f.policy.driver = None

    def no_owner():
        raise AuthorizationError("a live project owner is required for bounded execution")
    f.policy.owner_check = no_owner
    with pytest.raises(AuthorizationError):
        call("run", body)


def test_the_exact_retry_of_a_granted_authorization_is_answered_with_no_driver(tmp_path):
    f = setup(tmp_path)
    grant, body = approve(f)
    f.policy.driver = None
    assert f.policy.authorize("run", body) == (grant, False)


def test_the_two_doors_answer_409_project_not_active_on_the_wire(tmp_path):
    fresh, paused = setup(tmp_path / "fresh"), setup(tmp_path / "paused")
    body = authorize_body(fresh)
    grant, _ = approve(paused)
    pause(paused, grant)
    for f, path, payload in (
            (fresh, "/command/runs/run/automation/authorize", body),
            (paused, "/command/runs/run/automation/control", resume_body(grant, "pause"))):
        f.policy.driver = None
        before = journal(f)
        answer = post(door(f), path, payload)
        assert answer.status == 409
        assert answer.payload["error"]["code"] == CODE
        assert answer.payload["error"]["detail"] == {}
        assert journal(f) == before
