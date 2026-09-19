"""The task a run binds to, at the door where a browser opens one.

Seam: ``POST /command/runs`` with the ``task_id`` key, over the same API
factory and the same workflow the module beside this one drives. The claims
are about the BINDING rather than about opening a run: the key is required and
nullable, an unknown task is refused before any byte, a retry keeps the
binding the standing run froze, another task under one run id is a conflict,
and a work item the task's scope pushes out of the id grammar is refused with
nothing written.

Split out of ``test_command_run_routes`` when that module reached the line
cap; every helper still comes from it, so both files drive one door.
"""
from __future__ import annotations

from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.task_contracts import MAX_TASK_ID

from tests.test_command_run_routes import (
    PROVIDER,
    RUN_ID,
    a_project,
    a_run,
    journal_of,
)
from tests.test_command_workflow_draft import WORKFLOW, a_document
from tests.test_command_workflow_routes import (
    TASK,
    code_of,
    durable_digest,
    post,
)



def test_a_run_request_that_omits_the_task_key_is_refused_by_the_closed_set(
        tmp_path):
    """Every key is required: a browser that omits the key and a browser that
    says "no task" must not be the same request.

    Mutation: M11, the task key optional on the wire -> 201 -> red.
    """
    subject, store, _templates, events = a_project(tmp_path)
    body = a_run()
    del body["task_id"]
    refused = post(subject, "/command/runs", body)
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid")
    assert not store.run_path(RUN_ID).exists() and events == []


def test_a_run_naming_a_task_this_build_does_not_hold_is_refused_and_creates_nothing(
        tmp_path):
    """Mutation: M5, freeze the caller's id without consulting the store -> a
    201 bound to a task nobody made -> red."""
    subject, store, _templates, events = a_project(tmp_path)
    before = durable_digest(tmp_path)
    refused = post(subject, "/command/runs", a_run(task_id="ghost-task"))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["service_refused"], "service_refused")
    assert refused.payload["error"]["detail"] == {"task_id": "ghost-task"}
    assert not store.run_path(RUN_ID).exists()
    assert durable_digest(tmp_path) == before and events == []


def test_a_retried_run_open_keeps_its_task_binding(tmp_path):
    """The binding is inside the snapshot, so an exact retry IS the standing run.

    Mutation: M10, the snapshot omits the task -> no ``config.task`` -> red.
    """
    subject, store, _templates, events = a_project(tmp_path)
    assert post(subject, "/command/tasks",
                {"task_id": TASK, "title": "A task"}).status == 201
    first = post(subject, "/command/runs", a_run(task_id=TASK))
    assert first.status == 201, first.payload
    assert first.payload["config"]["task"] == {"id": TASK, "work_scope": TASK}
    standing = journal_of(store)

    again = post(subject, "/command/runs", a_run(task_id=TASK))
    assert (again.status, again.payload) == (200, first.payload)
    assert journal_of(store) == standing and events == [RUN_ID]


def test_a_run_open_naming_another_task_under_one_run_id_is_a_conflict(tmp_path):
    """A different task under one run id is a 409, and so is no task at all
    against a run that froze one. The standing run is looked for FIRST, so the
    conflict is `_standing_binding` comparing the task the run froze with the
    one the caller names -- none and none included -- before any task-store
    read and before the whole-snapshot compare, which can no longer differ on
    the task key because the standing road copies it off the frozen config.

    Mutation: `_standing_binding` hands the standing binding back without
    comparing ids -> both retries repeat the standing task and answer 200 ->
    red. Also M10, the snapshot omits the task -> red.
    """
    subject, store, _templates, events = a_project(tmp_path)
    for task in (TASK, "task-other"):
        assert post(subject, "/command/tasks",
                    {"task_id": task, "title": "A task"}).status == 201
    assert post(subject, "/command/runs", a_run(task_id=TASK)).status == 201
    standing = journal_of(store)

    for changed in (a_run(task_id="task-other"), a_run(task_id=None)):
        refused = post(subject, "/command/runs", changed)
        assert (refused.status, code_of(refused)) == (
            ERROR_STATUS["record_conflict"], "record_conflict"), changed
    assert journal_of(store) == standing and events == [RUN_ID]


def test_the_run_open_door_refuses_a_task_less_run_a_step_that_names_a_task(tmp_path):
    """A published revision may carry `work_scope` in a step -- the capability
    schema admits the key -- and `materialize` leaves a task-less run's payload
    exactly as written, so opening a run with NO task on that revision would file
    its work in the named task's directory. The run-open door refuses it before
    any byte of the run exists; the same revision under a task is overridden by
    that task's own scope and opens.

    Mutation: drop `work_scope_admits` from `_judged_revision` -> the task-less
    run opens with the borrowed scope -> red.
    """
    subject, store, _templates, events = a_project(tmp_path)
    borrowed = a_document()
    borrowed["nodes"][1]["arguments"]["work_scope"] = "victim-task"
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 2, "document": borrowed}).status == 201
    events.clear()

    refused = post(subject, "/command/runs", a_run(run_id="run-studio-002", revision=2))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid"), refused.payload
    assert not store.run_path("run-studio-002").exists() and events == []

    assert post(subject, "/command/tasks",
                {"task_id": TASK, "title": "A task"}).status == 201
    opened = post(subject, "/command/runs",
                  a_run(run_id="run-studio-003", revision=2, task_id=TASK))
    assert opened.status == 201, opened.payload
    step = next(node for node in opened.payload["graph"]["nodes"] if node["node_id"] == "do")
    assert step["arguments"]["work_scope"] == TASK


def test_the_widest_scope_and_the_widest_item_open_a_run_as_two_components(tmp_path):
    """The retired encoding summed scope and item into one 128-character id and
    refused a run the sum overflowed -- a refusal about a spelling, not about the
    work. Two path components have no sum: a scope as wide as a task id may be
    and an item as wide as the id grammar allows each stand on their own, and
    the run opens with both carried exactly.

    Mutation: materialize joins scope and item into one id again -> the second
    open is refused -> red.
    """
    subject, _store, _templates, _events = a_project(tmp_path)
    scope = "s" * MAX_TASK_ID
    assert post(subject, "/command/tasks",
                {"task_id": scope, "title": "As wide as a scope may be"}).status == 201
    wide = a_document()
    wide["nodes"][1]["arguments"]["work_item_id"] = "w" * 64
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 2, "document": wide}).status == 201

    opened = post(subject, "/command/runs",
                  a_run(run_id="run-studio-002", task_id=scope, revision=2))
    assert opened.status == 201, opened.payload
    step = next(node for node in opened.payload["graph"]["nodes"]
                if node["node_id"] == "do")
    assert (step["arguments"]["work_item_id"], step["arguments"]["work_scope"]) == (
        "w" * 64, scope)
