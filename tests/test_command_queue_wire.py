"""The queue on the wire: route-canon 4, through `CommandApi.handle` (spec 4.4.5, 4.4.7, 4.4.9).

The four rows are `GET` and `POST /command/queue`, `POST /command/queue/order` and
`POST /command/queue/<run_id>/withdraw`. What is held here is what only a router can break: the
paths are exactly those four and nothing wider, `queue` is no longer a run id that the run tail
could swallow (and a run NAMED `queue` is still read at `/command/runs/queue`), every refusal is
the code and the status 4.4.7 says with nothing written, a refused request publishes no frame, and
a process opened for viewing answers the same doors without ever refusing `project_not_active`.
The transport gate (host, origin, CSRF, content type, body ceiling) is proved for every new route by
`test_command_studio_transport.py`, which derives its routes from the live table.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conductor.command.command_routes import COMMAND_ROUTES, match_route
from conductor.command.http_api import PRODUCT_COMMAND_BUDGET, CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.project_claim import ProjectIdentity
from conductor.command.queue_routes import make_queue
from conductor.command.queue_store import MAX_QUEUE
from tests.queue_fixtures import Holder, add_run, project, start_body
from tests.test_command_http_api import PORT, TOKEN, get_headers, post
from tests.test_command_queue import a_start, unreadable_entry

PROJECT_ID = "a" * 32


def wire(tmp_path, *run_ids, mode="active"):
    """A real API over a project of bounded runs, with its queue over the fixture's policy."""
    f = project(tmp_path, *run_ids)
    f.policy.driver = Holder() if mode == "active" else None
    events = []
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=PRODUCT_COMMAND_BUDGET, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=events.append,
                     identity=ProjectIdentity(PROJECT_ID, None, False, mode, None, None))
    api._policy = f.policy
    f.policy.notify = api._publish_run
    api._queue = make_queue(api)
    return SimpleNamespace(f=f, api=api, events=events, root=tmp_path)


def read(w):
    return w.api.handle("GET", "/command/queue", get_headers())


def put(w, run_id="run", authorization_id="grant-1", **body):
    start = start_body(w.f, run_id, authorization_id)
    return post(w.api, "/command/queue", {"run_id": run_id, "start": start, **body})


def error(answer):
    return answer.status, answer.payload["error"]["code"], answer.payload["error"]["detail"]


# --- the router -----------------------------------------------------------------------------------


def test_the_table_names_the_four_queue_rows_in_this_order():
    queue_rows = [row for row in COMMAND_ROUTES if "/queue" in row[1]]
    assert queue_rows == [("GET", "/command/queue"), ("POST", "/command/queue"),
                          ("POST", "/command/queue/order"),
                          ("POST", "/command/queue/<run_id>/withdraw")]


@pytest.mark.parametrize("method, path, name, run_id", [
    ("GET", "/command/queue", "queue", None), ("POST", "/command/queue", "queue", None),
    ("POST", "/command/queue/order", "queue_order", None),
    ("POST", "/command/queue/run-1/withdraw", "queue_withdraw", "run-1"),
    ("POST", "/command/queue/order/withdraw", "queue_withdraw", "order"),
    ("POST", "/command/queue/withdraw/withdraw", "queue_withdraw", "withdraw")])
def test_each_queue_path_names_its_route_and_a_run_called_order_or_withdraw_is_a_run(
        method, path, name, run_id):
    route = match_route(method, path)
    assert (route.name, route.run_id) == (name, run_id)


@pytest.mark.parametrize("method, path, code", [
    ("GET", "/command/queue/order", "method_not_allowed"),
    ("GET", "/command/queue/run-1/withdraw", "method_not_allowed"),
    ("DELETE", "/command/queue", "method_not_allowed"),
    ("PUT", "/command/queue/order", "method_not_allowed"),
    ("POST", "/command/queue/", "route_not_found"),
    ("POST", "/command/queue/order/", "route_not_found"),
    ("POST", "/command/queue/run-1", "route_not_found"),
    ("POST", "/command/queue/run-1/withdraw/", "route_not_found"),
    ("POST", "/command/queue/run-1/withdraw/x", "route_not_found"),
    ("POST", "/command/queue/-x/withdraw", "route_not_found"),
    ("POST", "/command/queue/" + "a" * 129 + "/withdraw", "route_not_found"),
    ("POST", "/command/queue/order/order", "route_not_found"),
    ("GET", "/command/queues", "route_not_found"),
    ("GET", "/command/queue?x=1", "route_not_found")])
def test_the_queue_paths_are_exactly_four_and_nothing_wider(method, path, code):
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.command_routes import target_path
    with pytest.raises(ApiRefusal) as refused:
        match_route(method, target_path(path))
    assert refused.value.code == code


def test_a_run_named_queue_is_still_read_at_runs_queue(tmp_path):
    w = wire(tmp_path)
    add_run(w.f, "queue")
    run = w.api.handle("GET", "/command/runs/queue", get_headers())
    assert run.status == 200 and run.payload["run"]["run_id"] == "queue"
    assert "entries" not in run.payload
    listing = read(w)
    assert listing.status == 200 and set(listing.payload) == {
        "schema_version", "revision", "slot", "entries"}
    assert w.api.handle("GET", "/command/runs/queue/automation", get_headers()).status == 200
    assert put(w, "queue").status == 201          # and the run named queue can be queued


# --- the four doors -------------------------------------------------------------------------------


def test_the_read_of_an_empty_queue_is_the_form_of_no_queue(tmp_path):
    w = wire(tmp_path)
    assert read(w).payload == {"schema_version": 1, "revision": 0, "entries": [],
                               "slot": {"state": "free", "run_id": None, "reason_code": None}}


def test_put_in_queue_order_and_withdraw_answer_through_the_router(tmp_path):
    w = wire(tmp_path, "run-b")
    first, second = put(w, "run"), put(w, "run-b")
    assert (first.status, second.status) == (201, 201)
    assert [row["run_id"] for row in second.payload["entries"]] == ["run", "run-b"]
    assert put(w, "run", authorization_id="grant-2").status == 200
    revision = read(w).payload["revision"]
    ordered = post(w.api, "/command/queue/order", {"expected_revision": revision,
                                                   "run_ids": ["run-b", "run"]})
    assert ordered.status == 200 and [row["run_id"] for row in ordered.payload["entries"]] == [
        "run-b", "run"]
    withdrawn = post(w.api, "/command/queue/run-b/withdraw", {})
    assert withdrawn.status == 200 and [row["run_id"] for row in withdrawn.payload["entries"]] == [
        "run"]
    assert post(w.api, "/command/queue/run-b/withdraw", {}).payload == withdrawn.payload
    assert read(w).payload == withdrawn.payload


def test_every_refusal_is_the_code_and_the_status_of_the_spec_and_writes_nothing(tmp_path):
    w = wire(tmp_path, "run-b")
    put(w, "run")
    revision = read(w).payload["revision"]
    journal = {run: w.f.store.read(run).records for run in ("run", "run-b")}
    before = w.f.policy.queue.store.path.read_bytes()
    stale = post(w.api, "/command/queue/order",
                 {"expected_revision": revision - 1, "run_ids": ["run", "run-b"]})
    assert error(stale) == (409, "queue_changed", {})
    not_ready = post(w.api, "/command/queue", {"run_id": "no-such-run", "start": a_start("x")})
    assert error(not_ready) == (409, "queue_not_ready", {})
    body = start_body(w.f, "run-b", "grant-b")
    lying = {**body, "preview_digest": "sha256:" + "0" * 64}         # not the digest of its terms
    assert error(post(w.api, "/command/queue", {"run_id": "run-b", "start": lying})) == (
        422, "contract_invalid", {})
    w.f.policy.previews.discard(w.f.policy.session, "run-b")
    stale_preview = post(w.api, "/command/queue", {"run_id": "run-b", "start": body})
    assert error(stale_preview) == (409, "preview_stale", {})
    for bad in ({}, {"run_id": "run-b"}, {"run_id": "run-b", "start": body, "root": "C:\\x"},
                {"run_id": "run-b", "start": {**body, "path": "x"}},
                {"run_id": "run-b", "start": body, "resume": body}):
        assert error(post(w.api, "/command/queue", bad)) == (422, "contract_invalid", {})
    assert post(w.api, "/command/queue/order", {"expected_revision": revision,
                                                "run_ids": ["run"]}).status == 200
    assert error(post(w.api, "/command/queue/order", {"expected_revision": revision,
                                                      "run_ids": ["run", "x"]})) == (
        422, "contract_invalid", {})
    assert error(post(w.api, "/command/queue/run/withdraw", {"x": 1})) == (
        422, "contract_invalid", {})
    assert {run: w.f.store.read(run).records for run in journal} == journal
    assert w.f.policy.queue.store.path.read_bytes() == before


def test_a_thirty_third_entry_is_refused_409_queue_full_on_the_wire(tmp_path):
    w = wire(tmp_path)
    w.f.policy.queue.store.write(tuple(unreadable_entry(f"gone-{n}", n) for n in range(MAX_QUEUE)))
    before = w.f.policy.queue.store.path.read_bytes()
    assert error(put(w)) == (409, "queue_full", {})
    assert w.f.policy.queue.store.path.read_bytes() == before


def test_a_write_publishes_a_frame_for_every_run_it_touched_and_a_refusal_publishes_none(tmp_path):
    w = wire(tmp_path, "run-b")
    put(w, "run"), put(w, "run-b")
    assert w.events.count("run") >= 1 and w.events.count("run-b") >= 1
    w.events.clear()
    revision = read(w).payload["revision"]
    post(w.api, "/command/queue/order", {"expected_revision": revision - 1,
                                         "run_ids": ["run-b", "run"]})
    post(w.api, "/command/queue", {})
    post(w.api, "/command/queue/run/withdraw", {"x": 1})
    assert w.events == []
    post(w.api, "/command/queue/run/withdraw", {})
    assert w.events == ["run"]


def test_a_read_writes_nothing_and_publishes_nothing(tmp_path):
    w = wire(tmp_path)
    put(w)
    w.events.clear()
    before = w.f.policy.queue.store.path.read_bytes()
    for _ in range(3):
        assert read(w).status == 200
    assert w.events == [] and w.f.policy.queue.store.path.read_bytes() == before


# --- a process opened for viewing -----------------------------------------------------------------


def test_a_process_opened_for_viewing_answers_every_queue_door_and_refuses_none_for_its_mode(
        tmp_path):
    w = wire(tmp_path, mode="view")
    first = put(w)
    assert first.status == 201
    assert first.payload["slot"] == {"state": "unavailable", "run_id": None,
                                     "reason_code": "project_not_active"}
    entry, = first.payload["entries"]
    assert (entry["state"], entry["reason_code"]) == ("preauthorized", "project_not_active")
    revision = first.payload["revision"]
    assert post(w.api, "/command/queue/order", {"expected_revision": revision,
                                                "run_ids": ["run"]}).status == 200
    assert post(w.api, "/command/queue/run/withdraw", {}).status == 200
    assert read(w).status == 200


def test_the_project_claim_header_applies_to_the_queue_doors_like_every_command_route(tmp_path):
    w = wire(tmp_path)
    wrong = w.api.handle("GET", "/command/queue",
                         (*get_headers(), ("X-Conduct-Project", "b" * 32)))
    right = w.api.handle("GET", "/command/queue",
                         (*get_headers(), ("X-Conduct-Project", PROJECT_ID)))
    assert error(wrong) == (409, "project_mismatch", {}) and right.status == 200
