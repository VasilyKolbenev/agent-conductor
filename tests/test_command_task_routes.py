"""The three task routes, and what a run read says about the task it froze.

Project -> Task -> Run. ``POST /command/tasks`` is where a browser's request
becomes a durable task record, and it is idempotent under a lost reply: the
same request again answers the standing record and writes nothing, a different
request under one id is a conflict. ``GET /command/tasks`` lists what the
store holds and lists a corrupt directory rather than hiding it, the way the
run list does. ``GET /command/tasks/<task_id>`` answers one record and the
runs bound to it -- DERIVED from each run's own frozen binding at projection
time, because the record keeps no run list that could disagree with them.

The seam is ``task_routes`` behind ``http_api``, driven through the same door
as every other command route. The API factory, the transport helpers and the
run-open body come from the modules beside this one, so a task and the run
that binds to it go through the SAME allowlist and the SAME store.
"""
from __future__ import annotations

import os
import shutil

import pytest

from conductor.command.api_contracts import ApiRefusal, ERROR_STATUS
from conductor.command.studio_contracts import parse_run, parse_task
from conductor.command.studio_routes import recovered_payload
from conductor.command.task_contracts import (
    MAX_TASK_ID,
    MAX_TASK_TITLE,
    TaskRecord,
    frozen_config_task,
)
from conductor.command.task_store import TaskStore

from tests.test_command_run_routes import RUN_ID, a_project, a_run, journal_of
from tests.test_command_workflow_routes import (
    HOST,
    NOW,
    TASK,
    api,
    code_of,
    durable_digest,
    get,
    post,
)

TITLE = "Ship the task store"


def a_task_body(**changes):
    """One request to create a task: exactly the two caller-owned facts."""
    body = {"task_id": TASK, "title": TITLE}
    body.update(changes)
    return body


def a_record(task_id=TASK, title=TITLE, created_at=NOW):
    """The stored shape the route answers with, spelled by hand."""
    return {"schema_version": 1, "task_id": task_id, "title": title,
            "work_scope": task_id, "created_at": created_at}


def a_bound_run(**changes):
    """A run-open body that binds to :data:`TASK` and follows no workflow."""
    body = {"task_id": TASK, "workflow_id": None, "revision": None,
            "assignments": {}}
    body.update(changes)
    return a_run(**body)


def a_portal(link, target):
    """Make one symlink to a plain file, or report that this machine will not."""
    try:
        link.symlink_to(target, target_is_directory=False)
    except (OSError, NotImplementedError):
        return False
    return True


def corrupt_task_at(tmp_path, task_id):
    directory = tmp_path / "conductor" / "tasks" / task_id
    directory.mkdir(parents=True)
    (directory / "task.json").write_bytes(b'{"nope": 1}\n')


# --- creating one ------------------------------------------------------------


def test_creating_a_task_answers_201_and_the_record_reads_back_through_the_store(
        tmp_path):
    """No run is involved, so no run frame is published on any outcome.

    Mutation: answer 201 without `tasks.create_task(record)` -> the store reads
    nothing back -> red.
    """
    subject, _store, _templates, events = api(tmp_path)
    created = post(subject, "/command/tasks", a_task_body())
    assert created.status == 201, created.payload
    assert created.payload == {"task": a_record()}
    assert TaskStore(tmp_path).read(TASK).as_dict() == a_record()
    assert events == []


def test_creating_the_same_task_again_answers_the_standing_task_and_writes_nothing(
        tmp_path):
    """A client whose reply was lost is entitled to the same answer.

    The second API starts with a different clock: what it is asking about is
    already durable, so ``created_at`` is the standing record's and not the
    retry's, and exactly one directory stands afterwards.

    Mutation: skip `tasks.standing` and always create -> `TaskExists`, a
    store_error, in place of 200 -> red.
    """
    subject, _store, _templates, _events = api(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    standing = durable_digest(tmp_path)

    later, _s, _t, events = api(tmp_path, clock=lambda: "2099-01-01T00:00:00Z")
    again = post(later, "/command/tasks", a_task_body())
    assert (again.status, again.payload) == (200, {"task": a_record()})
    assert durable_digest(tmp_path) == standing
    assert [p.name for p in (tmp_path / "conductor" / "tasks").iterdir()] == [TASK]
    assert events == []


def test_a_different_title_under_one_task_id_is_a_conflict(tmp_path):
    """A task identity is written once, so a second create IS it or conflicts.

    Mutation: M6, answer 200 for any standing task -> red.
    """
    subject, _store, _templates, _events = api(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    standing = durable_digest(tmp_path)

    refused = post(subject, "/command/tasks", a_task_body(title="Another title"))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["record_conflict"], "record_conflict")
    assert durable_digest(tmp_path) == standing


@pytest.mark.parametrize("body,reason", [
    (a_task_body(extra="x"), "a key nobody wrote"),
    ({"task_id": TASK}, "no title"),
    ({"title": TITLE}, "no task id"),
    (a_task_body(title=""), "an empty title"),
    (a_task_body(title="   "), "a whitespace title"),
    (a_task_body(title="a\x01b"), "a control character"),
    (a_task_body(title="\x7f"), "DEL is a control character"),
    (a_task_body(title="t" * (MAX_TASK_TITLE + 1)), "one character too long"),
    (a_task_body(title=5), "a title is text"),
    (a_task_body(title=None), "a title is text, not null"),
    (a_task_body(task_id="t" * (MAX_TASK_ID + 1)), "an id past the task bound"),
    (a_task_body(task_id="has space"), "not an id"),
    (a_task_body(task_id=None), "a task id is never null here"),
])
def test_the_task_document_is_closed_to_what_it_cannot_mean(tmp_path, body, reason):
    """Mutation: read the two keys with `body.get` in place of `_closed`, or drop
    a `_title` bound or the id bound (core A) -> that row's refusal vanishes ->
    red."""
    subject, _store, _templates, events = api(tmp_path)
    refused = post(subject, "/command/tasks", body)
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid"), reason
    assert not (tmp_path / "conductor" / "tasks").exists()
    assert events == []


@pytest.mark.parametrize("body", [[], "a string", 7, None, [{"task_id": TASK}]])
def test_a_task_request_that_is_not_an_object_is_refused_by_the_parser(body):
    """The transport refuses a non-object body first; the parser refuses it too,
    so a caller of `parse_task` that is not the transport gets the same answer.

    Mutation: drop `_closed`'s Mapping check -> `7` and `None` reach
    `for key in body` as a TypeError, never `contract_invalid` -> red.
    """
    with pytest.raises(ApiRefusal) as refused:
        parse_task(body)
    assert refused.value.code == "contract_invalid"


def test_the_longest_admissible_title_and_id_are_admitted(tmp_path):
    """The bound is the bound: one under it is a task, one over it is not.

    Control for: core A narrowed rather than dropped (63 or 199) -> red; the
    one-past rows above catch it widened.
    """
    subject, _store, _templates, _events = api(tmp_path)
    body = a_task_body(task_id="t" * MAX_TASK_ID, title="x" * MAX_TASK_TITLE)
    created = post(subject, "/command/tasks", body)
    assert created.status == 201, created.payload
    assert created.payload["task"]["work_scope"] == "t" * MAX_TASK_ID


# --- listing them ------------------------------------------------------------


def test_listing_tasks_answers_sorted_rows_and_lists_a_corrupt_directory_unreadable(
        tmp_path):
    """A task you cannot see is worse than one you cannot read.

    The row convention is the run list's: every row carries the same keys and
    an ``unreadable`` word, and a directory whose record does not read is
    listed with that word true and every stored field null.

    Mutation: M12, the list hides a corrupt task -> red.
    """
    subject, _store, _templates, events = api(tmp_path)
    assert post(subject, "/command/tasks", a_task_body(task_id="task-b")).status == 201
    assert post(subject, "/command/tasks", a_task_body(task_id="task-a")).status == 201
    corrupt_task_at(tmp_path, "task-c")
    before = durable_digest(tmp_path)

    listed = get(subject, "/command/tasks")
    assert listed.status == 200
    assert listed.payload == {"tasks": [
        {**a_record("task-a"), "unreadable": False},
        {**a_record("task-b"), "unreadable": False},
        {"schema_version": None, "task_id": "task-c", "title": None,
         "work_scope": None, "created_at": None, "unreadable": True},
    ]}
    assert durable_digest(tmp_path) == before and events == []


def test_a_task_whose_record_carries_a_second_name_is_listed_unreadable_not_refused(
        tmp_path):
    """The run row's per-row convention, held for the route refusal too.

    One record reachable by another name is the store's `RouteNotOwned`, and
    it makes THAT row unreadable while its neighbour stays readable; nothing
    moves. Refusing the whole list for one entry would hide the neighbour.

    Mutation: let `RouteNotOwned` propagate from `_task_row` -> the whole list
    is refused -> red.
    """
    subject, _store, _templates, events = api(tmp_path)
    assert post(subject, "/command/tasks", a_task_body(task_id="task-a")).status == 201
    assert post(subject, "/command/tasks", a_task_body(task_id="task-b")).status == 201
    try:
        os.link(tmp_path / "conductor" / "tasks" / "task-a" / "task.json",
                tmp_path / "twin.json")
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not permit creating a hard link")
    before = durable_digest(tmp_path)

    listed = get(subject, "/command/tasks")
    assert listed.status == 200, listed.payload
    assert listed.payload == {"tasks": [
        {"schema_version": None, "task_id": "task-a", "title": None,
         "work_scope": None, "created_at": None, "unreadable": True},
        {**a_record("task-b"), "unreadable": False},
    ]}
    assert durable_digest(tmp_path) == before and events == []


def test_a_task_whose_content_lives_elsewhere_is_one_unreadable_row_beside_a_readable_one(
        tmp_path):
    """The contract the list promises: task-a readable, task-b unreadable.

    A portal is the one damage that used to cost the WHOLE listing -- the store
    refused while enumerating, so a healthy task was hidden behind a broken
    neighbour and the route answered nothing at all. It is now one row like any
    other unreadable one. ``task-c`` is itself a portal aimed at a plain file,
    so a listing that followed links would drop it instead of naming it.

    Mutation: refuse on the portal inside `TaskStore._listed` again -> the
    whole list is refused and task-a is unreachable -> red.
    """
    subject, _store, _templates, events = api(tmp_path)
    for task_id in ("task-a", "task-b"):
        assert post(subject, "/command/tasks",
                    a_task_body(task_id=task_id)).status == 201
    tasks_root = tmp_path / "conductor" / "tasks"
    outside = tmp_path / "elsewhere.json"
    outside.write_bytes(b'{"nope": 1}\n')
    (tasks_root / "task-b" / "task.json").unlink()
    if not (a_portal(tasks_root / "task-b" / "task.json", outside)
            and a_portal(tasks_root / "task-c", outside)):
        pytest.skip("this machine does not permit creating a symbolic link")
    before = durable_digest(tmp_path)

    listed = get(subject, "/command/tasks")
    assert listed.status == 200, listed.payload
    assert listed.payload == {"tasks": [
        {**a_record("task-a"), "unreadable": False},
        {"schema_version": None, "task_id": "task-b", "title": None,
         "work_scope": None, "created_at": None, "unreadable": True},
        {"schema_version": None, "task_id": "task-c", "title": None,
         "work_scope": None, "created_at": None, "unreadable": True},
    ]}
    assert durable_digest(tmp_path) == before and events == []


def test_a_project_with_no_tasks_answers_an_empty_list(tmp_path):
    """The state every project starts in, and it is not a refusal.

    Mutation: `tasks()` creates `tasks_root` before listing -> a read created a
    root -> red.
    """
    subject, _store, _templates, _events = api(tmp_path)
    assert not (tmp_path / "conductor" / "tasks").exists()
    listed = get(subject, "/command/tasks")
    assert (listed.status, listed.payload) == (200, {"tasks": []})
    assert not (tmp_path / "conductor" / "tasks").exists(), "a read created a root"


# --- reading one -------------------------------------------------------------


def test_reading_an_absent_task_is_service_refused_and_names_the_id(tmp_path):
    """Mutation: `_stored` lets `tasks.read`'s `StoreError` stand in for
    `ApiRefusal.missing_task` -> store_error with no `detail.task_id` -> red."""
    subject, _store, _templates, _events = api(tmp_path)
    refused = get(subject, "/command/tasks/ghost-task")
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["service_refused"], "service_refused")
    assert refused.payload["error"]["detail"] == {"task_id": "ghost-task"}
    assert refused.payload["error"]["message"] == "no stored task 'ghost-task'"
    assert str(tmp_path) not in refused.payload["error"]["message"]


def test_reading_a_corrupt_task_is_a_store_fault_and_never_a_missing_task(tmp_path):
    """Absent and corrupt are two refusals: a corrupt record is THERE.

    Mutation: `_stored` catches `CorruptTask` and answers `missing_task` -> red.
    """
    subject, _store, _templates, _events = api(tmp_path)
    corrupt_task_at(tmp_path, "task-c")
    refused = get(subject, "/command/tasks/task-c")
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["store_error"], "store_error")


def test_a_task_id_past_the_bound_names_no_route(tmp_path):
    """The route grammar admits exactly the names the store can address, as the
    run route does for runs: a name past the task bound is not a task route.

    Mutation: M9, the route admits 128 characters -> `task_path` refuses after
    the match, a store_error in place of route_not_found -> red.
    """
    subject, _store, _templates, _events = api(tmp_path)
    refused = get(subject, f"/command/tasks/{'t' * (MAX_TASK_ID + 1)}")
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["route_not_found"], "route_not_found")
    admitted = get(subject, f"/command/tasks/{'t' * MAX_TASK_ID}")
    assert code_of(admitted) == "service_refused"


def test_the_task_read_derives_its_runs_from_the_bindings_and_nothing_else(
        tmp_path):
    """Two runs bound to it, one legacy, one bound elsewhere: exactly the two.

    The list is derived at projection time from each run's frozen ``task``
    binding. A run whose journal does not replay is skipped from THIS list and
    is still listed unreadable by the run list, so nothing is hidden anywhere.

    Mutation: M7, list every readable run as bound -> run-legacy joins the
    list -> red.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    assert post(subject, "/command/tasks", a_task_body(task_id="task-other")).status == 201
    assert post(subject, "/command/runs", a_bound_run(run_id="run-b")).status == 201
    assert post(subject, "/command/runs", a_bound_run(run_id="run-a")).status == 201
    assert post(subject, "/command/runs", a_bound_run(
        run_id="run-legacy", task_id=None)).status == 201
    assert post(subject, "/command/runs", a_bound_run(
        run_id="run-other", task_id="task-other")).status == 201
    assert post(subject, "/command/runs", a_bound_run(run_id="run-broken")).status == 201
    (store.run_path("run-broken") / "records.jsonl").write_text(
        "this is not a durable record\n", encoding="utf-8", newline="\n")

    read = get(subject, f"/command/tasks/{TASK}")
    assert read.status == 200, read.payload
    assert read.payload == {"task": a_record(), "runs": ["run-a", "run-b"]}
    other = get(subject, "/command/tasks/task-other")
    assert other.payload["runs"] == ["run-other"]
    rows = {row["run_id"]: row for row in get(subject, "/command/runs").payload["runs"]}
    assert rows["run-broken"]["unreadable"] is True
    assert rows["run-a"]["task_id"] == TASK and rows["run-legacy"]["task_id"] is None


def test_a_task_with_no_runs_is_a_valid_task(tmp_path):
    """A task with zero runs is valid by the owner's contract.

    Mutation: `read_task` refuses when `_bound_runs` answers nothing -> red.
    """
    subject, _store, _templates, _events = api(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    read = get(subject, f"/command/tasks/{TASK}")
    assert (read.status, read.payload) == (200, {"task": a_record(), "runs": []})


# --- the binding a run freezes -----------------------------------------------


def test_a_second_run_of_the_same_task_keeps_the_same_work_scope(tmp_path):
    """Two runs of one task file their work under ONE scope, read off the record.

    Mutation: M10, the snapshot omits the task -> no `config.task` on either
    run -> red.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    first = post(subject, "/command/runs", a_bound_run(run_id="run-a"))
    second = post(subject, "/command/runs", a_bound_run(run_id="run-b"))
    assert (first.status, second.status) == (201, 201)
    binding = {"id": TASK, "work_scope": TASK}
    assert first.payload["config"]["task"] == binding
    assert second.payload["config"]["task"] == binding
    assert (frozen_config_task(store.read("run-a").config)
            == frozen_config_task(store.read("run-b").config))


def test_the_frozen_scope_is_the_records_and_never_the_callers_id(tmp_path):
    """A record whose scope differs from its id is the one case that can tell
    "the store's own scope" from "the caller's word for it": the run freezes
    the record's, and its plan files the work under that.

    Mutation: M5, freeze `TaskBinding(task_id, task_id)` without the store ->
    the config says `work_scope: t1` and the step carries `t1` -> red.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    TaskStore(tmp_path).create_task(TaskRecord(
        task_id="t1", title="Scoped apart from its id", work_scope="scope-x",
        created_at=NOW))

    opened = post(subject, "/command/runs", a_run(task_id="t1"))
    assert opened.status == 201, opened.payload
    assert opened.payload["config"]["task"] == {"id": "t1", "work_scope": "scope-x"}
    step = next(node for node in opened.payload["graph"]["nodes"]
                if node["node_id"] == "do")
    assert step["arguments"]["work_item_id"] == "work-001"
    assert step["arguments"]["work_scope"] == "scope-x"
    assert frozen_config_task(store.read(RUN_ID).config).work_scope == "scope-x"


def test_an_exact_retry_answers_the_standing_run_before_the_task_store_is_asked(
        tmp_path):
    """A client whose reply was lost is owed the standing run whatever the task
    store holds NOW: the binding it froze is durable, and the record vanishing
    or going corrupt out of band changes nothing about what was written.

    Mutation: resolve the task through the store before the standing run is
    looked for -> service_refused / store_error instead of 200 -> red.
    """
    subject, store, _templates, events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    first = post(subject, "/command/runs", a_bound_run())
    assert first.status == 201, first.payload
    standing = journal_of(store)

    shutil.rmtree(tmp_path / "conductor" / "tasks" / TASK)
    vanished = post(subject, "/command/runs", a_bound_run())
    assert (vanished.status, vanished.payload) == (200, first.payload)
    corrupt_task_at(tmp_path, TASK)
    corrupt = post(subject, "/command/runs", a_bound_run())
    assert (corrupt.status, corrupt.payload) == (200, first.payload)
    assert journal_of(store) == standing and events == [RUN_ID]


def test_a_retry_naming_another_task_under_a_standing_run_is_a_conflict_not_a_lookup(
        tmp_path):
    """The standing run is looked for FIRST, so a different task under its id
    is `record_conflict` -- even a task the store holds no record of, which a
    lookup-first road would call `service_refused`. Nothing is written.

    Mutation: resolve through the store before the standing lookup ->
    service_refused -> red.
    """
    subject, store, _templates, events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    assert post(subject, "/command/runs", a_bound_run()).status == 201
    standing = journal_of(store)
    before = durable_digest(tmp_path)

    refused = post(subject, "/command/runs", a_bound_run(task_id="task-nobody-made"))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["record_conflict"], "record_conflict")
    assert journal_of(store) == standing
    assert durable_digest(tmp_path) == before and events == [RUN_ID]


def test_the_run_read_carries_the_tasks_title_beside_its_frozen_binding(tmp_path):
    """The binding is the run's frozen fact; the title is the record's, joined
    at read time and stored in the run nowhere. A task-less run says ``null``.

    Mutation: `_task_payload` drops `record.title` (the title always null) ->
    red.
    """
    subject, _store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    assert post(subject, "/command/runs", a_bound_run()).status == 201
    assert post(subject, "/command/runs", a_bound_run(
        run_id="run-legacy", task_id=None)).status == 201

    read = subject.handle("GET", f"/command/runs/{RUN_ID}", (("Host", HOST),))
    assert read.status == 200
    assert read.payload["task"] == {
        "id": TASK, "work_scope": TASK, "title": TITLE, "unreadable": False}
    assert read.payload["config"]["task"] == {"id": TASK, "work_scope": TASK}
    legacy = subject.handle("GET", "/command/runs/run-legacy", (("Host", HOST),))
    assert legacy.payload["task"] is None
    assert "task" not in legacy.payload["config"]


def test_a_bound_task_whose_record_vanished_reads_as_unreadable_not_untitled(
        tmp_path):
    """The binding still stands -- it is frozen -- and the title cannot be had.

    Absent and corrupt records answer alike here: the run is bound to a task
    this store cannot currently read, and ``unreadable`` says so rather than
    an empty title that would read as a task called nothing.

    Mutation: M8, an absent record reads ``unreadable: false`` -> red.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    assert post(subject, "/command/runs", a_bound_run()).status == 201
    standing = journal_of(store)
    unreadable = {"id": TASK, "work_scope": TASK, "title": None, "unreadable": True}

    shutil.rmtree(tmp_path / "conductor" / "tasks" / TASK)
    vanished = subject.handle("GET", f"/command/runs/{RUN_ID}", (("Host", HOST),))
    assert vanished.status == 200 and vanished.payload["task"] == unreadable

    corrupt_task_at(tmp_path, TASK)
    corrupt = subject.handle("GET", f"/command/runs/{RUN_ID}", (("Host", HOST),))
    assert corrupt.status == 200 and corrupt.payload["task"] == unreadable
    assert journal_of(store) == standing


def test_a_bound_task_whose_record_carries_a_second_name_reads_as_unreadable_not_refused(
        tmp_path):
    """The run's own route is clean; only the TASK record answers to another
    name. That is the store's `RouteNotOwned` about the record, and on the run
    read it makes the task unreadable exactly as it does on the task list --
    the run read is never `route_unsafe` for a fact about a different route.

    Mutation: `_task_payload` catches `CorruptTask` only -> the run read is
    refused whole as `route_unsafe` -> red.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    assert post(subject, "/command/runs", a_bound_run()).status == 201
    standing = journal_of(store)
    try:
        os.link(tmp_path / "conductor" / "tasks" / TASK / "task.json",
                tmp_path / "twin.json")
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not permit creating a hard link")

    read = subject.handle("GET", f"/command/runs/{RUN_ID}", (("Host", HOST),))
    assert read.status == 200, read.payload
    assert read.payload["task"] == {
        "id": TASK, "work_scope": TASK, "title": None, "unreadable": True}
    assert journal_of(store) == standing


def test_a_retry_over_a_standing_run_whose_frozen_task_is_malformed_is_run_corrupt(
        tmp_path):
    """Frozen bytes that will not read as a binding are corrupt on the retry
    road exactly as on every other: the standing run is looked for first, and
    what it froze is judged by the one `_task` rule before any id is compared,
    so the caller's word -- the same task, or none -- changes nothing.

    Mutation: `_standing_binding` reads through `frozen_config_task` instead of
    `_task` -> 422 contract_invalid, the caller blamed for frozen bytes -> red.
    """
    subject, store, _templates, events = a_project(tmp_path)
    asked = parse_run(a_run(task_id=None))
    snapshot = {**asked.snapshot(), "task": {"id": "t1"}}
    store.create_run(asked.build(snapshot, NOW), snapshot)
    standing = journal_of(store)

    for body in (a_run(task_id="t1"), a_run(task_id=None)):
        refused = post(subject, "/command/runs", body)
        assert (refused.status, code_of(refused)) == (
            ERROR_STATUS["run_corrupt"], "run_corrupt"), body
    assert journal_of(store) == standing and events == []


def test_recovered_payload_without_a_task_store_reads_a_bound_task_as_unreadable(
        tmp_path):
    """The two-argument callers get a truthful answer, never an invented title.

    A `RecoveredRun` cannot name its project root, so a caller that hands no
    `TaskStore` cannot be given the record; what it is given is the frozen
    binding and the honest word for "the title is not in hand".

    Mutation: M8 -> the two-argument caller is answered ``unreadable: false``
    beside a null title -> red.
    """
    subject, store, _templates, _events = a_project(tmp_path)
    assert post(subject, "/command/tasks", a_task_body()).status == 201
    assert post(subject, "/command/runs", a_bound_run()).status == 201

    payload = recovered_payload(store.read(RUN_ID))
    assert payload["task"] == {
        "id": TASK, "work_scope": TASK, "title": None, "unreadable": True}
    assert recovered_payload(store.read(RUN_ID), TaskStore(tmp_path))["task"] == {
        "id": TASK, "work_scope": TASK, "title": TITLE, "unreadable": False}
