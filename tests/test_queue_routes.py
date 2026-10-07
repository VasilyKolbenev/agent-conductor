"""The four queue handlers, reached by name (spec 4.4.5); the wire is in `test_command_queue.py`.

The handlers put the checks in the order of the spec and choose the status: the closed body first,
`_hold_route` next, the service last; 201 only for an entry that is new; and every write answers
with the read as it stands after it. They are called here through a real `CommandApi`, whose queue
is attached to the policy of the fixture, because no route row reaches them before route-canon 4.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conductor.command.api_refusals import ApiRefusal
from conductor.command.contract_values import ContractError
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.queue_routes import (
    make_queue, read_queue, write_order, write_queue, write_withdraw)
from conductor.command.queue_service import QueueService
from conductor.command.task_store import TaskStore
from tests.queue_fixtures import Holder, NOW, project, resume_body, start_body
from tests.test_command_http_api import PORT, TOKEN


def door(f, mode="active", project_id="a" * 32):
    """A real CommandApi over the fixture's store, its policy and the queue made for it."""
    identity = ProjectIdentity(project_id, None, False, mode, None, None)
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=PRODUCT_COMMAND_BUDGET, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=lambda run_id: None, identity=identity)
    api._policy = f.policy
    api._queue = make_queue(api)
    return api


@pytest.fixture
def api(tmp_path):
    f = project(tmp_path, "run-b")
    f.policy.driver = Holder()
    return SimpleNamespace(f=f, api=door(f))


def write(api, run_id="run", authorization_id="grant-1"):
    body = start_body(api.f, run_id, authorization_id)
    return write_queue(api.api, {"run_id": run_id, "start": body})


def test_a_new_entry_answers_201_and_the_read_that_shows_it(api):
    status, payload = write(api)
    assert status == 201
    assert [row["run_id"] for row in payload["entries"]] == ["run"]
    assert payload["entries"][0]["state"] == "preauthorized"
    assert payload == read_queue(api.api)[1]


def test_a_renewed_preauthorization_and_an_exact_repeat_answer_200(api):
    body = start_body(api.f, "run", "grant-1")
    assert write_queue(api.api, {"run_id": "run", "start": body})[0] == 201
    assert write_queue(api.api, {"run_id": "run", "start": body})[0] == 200
    assert write(api, "run", "grant-2")[0] == 200
    assert [row["position"] for row in read_queue(api.api)[1]["entries"]] == [1]


def test_the_closed_body_is_judged_before_the_route_and_the_route_before_the_queue(api):
    order = []
    spy = SimpleNamespace(
        _clock=api.api._clock, _hold_route=lambda run_id: order.append(("route", run_id)),
        _queue=SimpleNamespace(enqueue=lambda ask: order.append(("queue", ask.run_id)) or True,
                               read=lambda: {"entries": []}))
    with pytest.raises(ContractError):
        write_queue(spy, {"run_id": "run", "start": {}, "root": "x"})
    assert order == []
    body = start_body(api.f, "run", "grant-1")
    assert write_queue(spy, {"run_id": "run", "start": body})[0] == 201
    assert order == [("route", "run"), ("queue", "run")]


def test_an_unsafe_route_is_refused_before_the_queue_writes_anything(api):
    def unsafe(run_id):
        raise ApiRefusal.fixed("route_unsafe")
    api.api._hold_route = unsafe
    with pytest.raises(ApiRefusal) as refused:
        write(api)
    assert refused.value.code == "route_unsafe"
    assert api.api._queue.store.read().entries == ()


def test_order_answers_200_with_the_read_and_a_stale_revision_is_queue_changed(api):
    write(api, "run"), write(api, "run-b")
    revision = read_queue(api.api)[1]["revision"]
    status, payload = write_order(api.api, {"expected_revision": revision,
                                            "run_ids": ["run-b", "run"]})
    assert status == 200 and [row["run_id"] for row in payload["entries"]] == ["run-b", "run"]
    assert payload["revision"] == revision + 1
    with pytest.raises(ApiRefusal) as refused:
        write_order(api.api, {"expected_revision": revision, "run_ids": ["run", "run-b"]})
    assert refused.value.code == "queue_changed"


def test_withdraw_answers_200_with_the_read_whether_or_not_the_run_was_there(api):
    write(api, "run"), write(api, "run-b")
    status, payload = write_withdraw(api.api, "run", {})
    assert status == 200 and [row["run_id"] for row in payload["entries"]] == ["run-b"]
    assert write_withdraw(api.api, "run", {})[1] == payload
    with pytest.raises(ContractError):
        write_withdraw(api.api, "run-b", {"run_id": "run"})
    assert [row["run_id"] for row in read_queue(api.api)[1]["entries"]] == ["run-b"]


def test_a_resume_is_put_in_the_queue_through_the_same_route(api):
    granted, _ = api.f.policy.authorize("run", start_body(api.f, "run", "grant-1"))
    api.f.policy.driver.active = None
    api.f.policy.control("run", {"control_id": "pause", "authorization_id": "grant-1",
        "authorization_digest": granted.authorization_digest, "action": "pause",
        "actor": "owner", "expected_control_id": None})
    status, payload = write_queue(api.api, {
        "run_id": "run", "resume": resume_body(granted, "resume-1", "pause")})
    assert status == 201 and payload["entries"][0]["kind"] == "resume"


def test_every_handler_works_in_a_process_opened_for_viewing_and_refuses_no_one_for_it(tmp_path):
    f = project(tmp_path)
    f.policy.driver = None
    view = SimpleNamespace(f=f, api=door(f, mode="view"))
    status, payload = write(view)
    assert status == 201 and payload["slot"]["reason_code"] == "project_not_active"
    assert payload["entries"][0]["reason_code"] == "project_not_active"
    revision = payload["revision"]
    assert write_order(view.api, {"expected_revision": revision, "run_ids": ["run"]})[0] == 200
    assert write_withdraw(view.api, "run", {})[0] == 200 and read_queue(view.api)[0] == 200


def test_the_queue_is_attached_to_the_policy_and_holds_the_mode_of_the_identity(tmp_path):
    f = project(tmp_path)
    for mode in ("active", "view"):
        built = door(f, mode=mode)
        assert isinstance(built._queue, QueueService) and built._queue.mode == mode
        assert built._policy.queue is built._queue


def test_a_command_api_builds_its_own_queue_and_attaches_it_to_its_own_policy(tmp_path):
    f = project(tmp_path)
    built = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                       budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=f.runtime._ids,
                       publish_run=lambda run_id: None)
    assert isinstance(built._queue, QueueService) and built._policy.queue is built._queue
    assert built._queue.policy is built._policy and built._queue.mode == "active"


def test_building_a_command_api_and_its_queue_reads_the_server_clock_not_once(tmp_path):
    """Tests that count the ticks of the clock (a retry mints no new time) hold the constructor."""
    f = project(tmp_path)
    ticks = []
    CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
               budget=PRODUCT_COMMAND_BUDGET, clock=lambda: ticks.append(1) or NOW,
               ids=f.runtime._ids, publish_run=lambda run_id: None)
    assert ticks == []
    service = QueueService(f.policy, TaskStore(tmp_path))
    assert service.started_at.endswith("Z") and len(service.started_at) == 20
    assert QueueService(f.policy, TaskStore(tmp_path), started_at=NOW).started_at == NOW
