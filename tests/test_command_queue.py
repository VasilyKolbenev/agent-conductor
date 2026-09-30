"""The project queue's human side: enqueue, order, withdraw, and the read (spec 4.4.5, 4.4.6).

A run is put in the queue with a preauthorization, the body of an authorize (for a start) or of a
control (for a resume). What is proved here is what the server checks before it writes a byte of
the queue: the closed body, readiness, an exact repeat, the owner, the preview, the conditions,
the room; and that none of it ever writes into a run's journal (a queue that could append a grant
would be an authorization road of its own). The pump that starts what was confirmed is
`test_queue_pump.py`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conductor.command.api_refusals import ApiRefusal
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contract_values import ContractError, _content_digest
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.policy_preview import PreviewStale
from conductor.command.queue_bodies import parse_order, parse_withdraw, parse_write
from conductor.command.queue_service import QueueService
from conductor.command.queue_store import (
    MAX_QUEUE, Dropped, QueueEntry, QueueStore, ResumePreauth, StartPreauth)
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import snapshot_digest
from conductor.command.runtime_values import AuthorizationError
from conductor.command.task_contracts import TaskRecord
from conductor.command.task_store import TaskStore
from tests.queue_fixtures import (
    Holder, NOW, add_run, ask, project, resume_body, start_body)
from tests.test_policy_runtime import ARGS, pause


@pytest.fixture
def q(tmp_path):
    """Three bounded runs, an active process with a driver double, and the queue over them."""
    f = project(tmp_path, "run-b", "run-c")
    f.policy.driver = Holder()
    frames = []
    f.policy.notify = frames.append
    service = QueueService(f.policy, TaskStore(tmp_path), mode="active")
    f.policy.queue = service
    return SimpleNamespace(f=f, service=service, frames=frames, root=tmp_path,
                           driver=f.policy.driver)


def now(q):
    return q.f.policy.clock()


def put(q, run_id="run", authorization_id="grant-1", **changes):
    """Preview the run, confirm it, and enqueue: what the card of conditions does."""
    body = start_body(q.f, run_id, authorization_id, **changes)
    return q.service.enqueue(parse_write({"run_id": run_id, "start": body}, now(q)))


def put_resume(q, grant, control_id="resume-1", expected="pause", run_id="run"):
    body = resume_body(grant, control_id, expected)
    return q.service.enqueue(parse_write({"run_id": run_id, "resume": body}, now(q)))


def file_bytes(q):
    path = q.service.store.path
    return path.read_bytes() if path.exists() else None


def journals(q):
    return {run_id: q.f.store.read(run_id).records for run_id in ("run", "run-b", "run-c")}


def codes(call):
    with pytest.raises(ApiRefusal) as refused:
        call()
    return refused.value.code


# --- the closed body ------------------------------------------------------------------------------


@pytest.mark.parametrize("extra", ["root", "path", "dir", "anything"])
def test_body_keys_root_path_dir_are_contract_invalid(q, extra):
    body = start_body(q.f, "run", "grant-1")
    with pytest.raises(ContractError):
        parse_write({"run_id": "run", "start": body, extra: "C:\\elsewhere"}, now(q))
    with pytest.raises(ContractError):
        parse_write({"run_id": "run", "start": {**body, extra: "C:\\elsewhere"}}, now(q))
    resume = resume_body(SimpleNamespace(authorization_id="grant-1",
                                         authorization_digest="sha256:" + "a" * 64),
                         "resume-1", None)
    with pytest.raises(ContractError):
        parse_write({"run_id": "run", "resume": {**resume, extra: "x"}}, now(q))
    assert file_bytes(q) is None


@pytest.mark.parametrize("body", [
    {}, {"run_id": "run"}, {"start": {}}, {"run_id": "run", "start": {}},
    {"run_id": "run", "start": {}, "resume": {}}, {"run_id": "not a safe id!", "start": {}},
    {"run_id": 3, "start": {}}, [], "start", None])
def test_a_queue_write_that_is_not_a_run_and_one_closed_kind_is_contract_invalid(q, body):
    with pytest.raises(ContractError):
        parse_write(body, now(q))


def test_a_body_that_contradicts_its_own_terms_is_contract_invalid_before_the_queue_is_asked(q):
    body = start_body(q.f, "run", "grant-1")
    with pytest.raises(ContractError):
        parse_write({"run_id": "run", "start": {**body, "preview_digest": "sha256:" + "0" * 64}},
                    now(q))


@pytest.mark.parametrize("body", [{"expected_revision": 1}, {"run_ids": []},
                                  {"expected_revision": "1", "run_ids": []},
                                  {"expected_revision": True, "run_ids": []},
                                  {"expected_revision": -1, "run_ids": []},
                                  {"expected_revision": 1, "run_ids": "run"},
                                  {"expected_revision": 1, "run_ids": ["a", "a"]},
                                  {"expected_revision": 1, "run_ids": [3]},
                                  {"expected_revision": 1, "run_ids": [], "root": "x"}, [], None])
def test_an_order_body_that_is_not_a_revision_and_distinct_run_ids_is_contract_invalid(body):
    with pytest.raises(ContractError):
        parse_order(body)


@pytest.mark.parametrize("body", [{"x": 1}, [], None, "{}"])
def test_a_withdraw_body_that_is_not_the_empty_object_is_contract_invalid(body):
    with pytest.raises(ContractError):
        parse_withdraw(body)
    assert parse_withdraw({}) is None


# --- enqueue --------------------------------------------------------------------------------------


def test_the_first_enqueue_writes_a_new_entry_at_the_end_and_admits_it_in_this_process(q):
    assert put(q, "run") is True and put(q, "run-b") is True
    entries = q.service.store.read().entries
    assert [row.run_id for row in entries] == ["run", "run-b"]
    assert [row.kind for row in entries] == ["start", "start"]
    assert q.service.admitted == {row.key for row in entries}
    assert q.frames.count("run") == 1 and q.frames.count("run-b") == 1
    assert q.driver.woken >= 2


def test_enqueue_repeat_with_the_same_preauthorization_writes_nothing(q):
    body = start_body(q.f, "run", "grant-1")
    first = parse_write({"run_id": "run", "start": body}, NOW)
    assert q.service.enqueue(first) is True
    before, frames = file_bytes(q), list(q.frames)
    q.f.ticks[0] = "2026-08-11T12:01:00Z"
    again = parse_write({"run_id": "run", "start": body}, now(q))
    assert again.preauth.preauthorized_at != first.preauth.preauthorized_at
    assert q.service.enqueue(again) is False
    assert file_bytes(q) == before and q.frames == frames


def test_enqueue_with_a_new_preauthorization_keeps_the_position(q):
    put(q, "run"), put(q, "run-b"), put(q, "run-c")
    first = q.service.store.read()
    q.f.ticks[0] = "2026-08-11T12:01:00Z"
    assert put(q, "run", authorization_id="grant-2", by="nadia") is False
    second = q.service.store.read()
    assert [row.run_id for row in second.entries] == ["run", "run-b", "run-c"]
    assert second.revision == first.revision + 1
    kept, renewed = first.entries[0], second.entries[0]
    assert (renewed.enqueued_at, renewed.enqueued_by) == (kept.enqueued_at, kept.enqueued_by)
    assert renewed.preauthorization.authorization_id == "grant-2"
    assert renewed.preauthorization.authorized_by == "nadia"
    assert renewed.preauthorization.preauthorized_at == "2026-08-11T12:01:00Z"
    assert renewed.key in q.service.admitted and kept.key not in q.service.admitted


def test_enqueue_requires_a_fresh_reviewed_preview_else_preview_stale(q):
    body = start_body(q.f, "run", "grant-1")
    asked = parse_write({"run_id": "run", "start": body}, now(q))
    q.f.policy.previews.discard(q.f.policy.session, "run")
    with pytest.raises(PreviewStale):                     # gone from the cache
        q.service.enqueue(asked)
    body = start_body(q.f, "run", "grant-1")
    q.f.ticks[0] = "2026-08-11T12:06:00Z"
    with pytest.raises(PreviewStale):                     # older than its 300 seconds
        q.service.enqueue(parse_write({"run_id": "run", "start": body}, now(q)))
    q.f.ticks[0] = NOW
    body = start_body(q.f, "run", "grant-1")
    q.f.store.append(ArtifactDocument(artifact_id="instruction-2", run_id="run",
        artifact_ref="instructions", created_at=NOW, media_type="text/plain", content="Changed"))
    with pytest.raises(PreviewStale):                     # the run moved under the preview
        q.service.enqueue(parse_write({"run_id": "run", "start": body}, now(q)))
    assert file_bytes(q) is None


def test_a_preview_of_another_run_is_not_the_preview_of_this_one(q):
    body = start_body(q.f, "run-b", "grant-1")
    with pytest.raises(PreviewStale):
        q.service.enqueue(parse_write({"run_id": "run", "start": body}, now(q)))
    assert file_bytes(q) is None


def test_enqueue_asks_the_owner_after_the_repeat_check_and_before_anything_is_written(q):
    def no_owner():
        raise AuthorizationError("a live project owner is required for bounded execution")
    body = start_body(q.f, "run", "grant-1")
    q.f.policy.owner_check = no_owner
    with pytest.raises(AuthorizationError):
        q.service.enqueue(parse_write({"run_id": "run", "start": body}, now(q)))
    assert file_bytes(q) is None


def test_the_owner_is_not_asked_for_an_exact_repeat(q):
    body = start_body(q.f, "run", "grant-1")
    asked = parse_write({"run_id": "run", "start": body}, now(q))
    q.service.enqueue(asked)
    q.f.policy.owner_check = lambda: (_ for _ in ()).throw(AssertionError("asked the owner"))
    assert q.service.enqueue(asked) is False


def test_a_start_whose_terms_cannot_admit_one_more_action_is_contract_invalid(q):
    f = q.f
    terms = {**ask(), "max_actions": 1, "max_total_task_seconds": 60}
    granted, _ = f.policy.authorize("run", start_body(f, "run", "grant-1", terms=terms))
    proposal = f.service.propose(run_id="run", attempt_id="attempt", instance_id="doer",
        capability="dispatch", arguments=ARGS, scope=("work/item",), proposed_by="run-driver",
        rationale="Approved work", timeout_seconds=30, node_id="do", proposal_id="proposal")
    f.runtime.execute(f.runtime.authorize_policy("run", proposal.proposal_id,
                                                 granted.authorization_id))
    f.ticks[0] = "2026-08-11T12:06:00Z"                   # the grant's 300 seconds are over
    q.driver.active = None
    too_small = start_body(f, "run", "grant-2", supersedes="grant-1", terms=terms)
    with pytest.raises(ContractError, match="no further action"):
        q.service.enqueue(parse_write({"run_id": "run", "start": too_small}, now(q)))
    assert file_bytes(q) is None
    roomy = start_body(f, "run", "grant-2", supersedes="grant-1",
                       terms={**ask(), "max_actions": 2, "max_total_task_seconds": 120})
    assert q.service.enqueue(parse_write({"run_id": "run", "start": roomy}, now(q))) is True


def test_a_start_that_supersedes_nothing_after_an_expired_grant_is_refused_by_the_history(q):
    f = q.f
    f.policy.authorize("run", start_body(f, "run", "grant-1"))
    f.ticks[0] = "2026-08-11T12:06:00Z"
    q.driver.active = None                     # the human let the expired grant go (spec 4.4.8)
    with pytest.raises(ContractError, match="immediate predecessor"):
        put(q, "run", authorization_id="grant-2")


# --- readiness ------------------------------------------------------------------------------------


def unbounded_run(f, run_id):
    config = {"cycle": {"id": "cycle"}, "instances": [], "workflow": {"id": "custom",
              "revision": 1}}
    f.store.create_run(RunEnvelope(run_id, "cycle", NOW, snapshot_digest(config),
                                   mode="confirm"), config)
    f.store.append(GraphDefinition("graph", run_id, NOW, nodes=(
        GraphNode("gate", "gate", "Approve", gate_id="gate-id"),), edges=()))


def ended_run(f, run_id):
    config = {"cycle": {"id": "cycle"}, "instances": [], "workflow": {"id": "custom",
              "revision": 1}, "automation_contract": "bounded-run-v1"}
    f.store.create_run(RunEnvelope(run_id, "cycle", NOW, snapshot_digest(config),
                                   mode="policy"), config)
    f.store.append(GraphDefinition("graph", run_id, NOW, nodes=(
        GraphNode("gate", "gate", "Approve", gate_id="gate-id"),), edges=()))
    f.store.append(DecisionReceipt("decision", run_id, "gate-id", "approve", "owner", NOW,
                                   "Reviewed", ("gate-id",), snapshot_digest(config)))
    ids = iter(range(9))
    close_if_terminal(f.store, run_id, clock=lambda: NOW, ids=lambda kind: f"{kind}-{next(ids)}")


PREVIEW_KEYS = ("node_limits", "max_actions", "max_action_seconds", "max_total_task_seconds",
                "duration_seconds")


def a_start(run_id):
    """A start body that is well formed in itself, for a run the queue will not take."""
    terms = {"run_id": run_id, "source_prefix_digest": "sha256:" + "b" * 64,
             **{key: ask()[key] for key in PREVIEW_KEYS}}
    return {"authorization_id": "grant-1", "preview_digest": _content_digest(terms),
            "terms": terms, "authorized_by": "vasily", "supersedes": None}


def not_ready(q, run_id, kind="start", grant=None):
    if kind == "start":
        write = {"run_id": run_id, "start": a_start(run_id)}
    else:
        write = {"run_id": run_id, "resume": resume_body(grant, "resume-1", None)}
    return codes(lambda: q.service.enqueue(parse_write(write, now(q))))


def test_queue_not_ready_for_unbounded_ended_slot_holding_and_actively_granted_runs(q):
    unbounded_run(q.f, "plain")
    ended_run(q.f, "done")
    q.f.policy.authorize("run-c", start_body(q.f, "run-c", "live-1"))    # a standing grant
    q.driver.active = ("run-b", "grant-x")                                # the driver holds run-b
    for run_id in ("plain", "done", "run-b", "run-c", "no-such-run"):
        assert not_ready(q, run_id) == "queue_not_ready", run_id
    assert file_bytes(q) is None


def test_queue_not_ready_for_a_resume_with_nothing_to_resume(q):
    f = q.f
    granted, _ = f.policy.authorize("run", start_body(f, "run", "grant-1"))
    q.driver.active = None
    pause(f, granted)
    f.ticks[0] = "2026-08-11T12:06:00Z"                    # expired
    assert not_ready(q, "run", "resume", granted) == "queue_not_ready"
    f.ticks[0] = NOW
    f.policy.control("run", {**resume_body(granted, "revoke-1", "pause"), "action": "revoke"})
    assert not_ready(q, "run", "resume", granted) == "queue_not_ready"
    assert not_ready(q, "run-b", "resume", granted) == "queue_not_ready"   # no grant at all


def test_a_resume_of_a_paused_grant_is_queued_and_the_entry_keeps_its_control(q):
    f = q.f
    granted, _ = f.policy.authorize("run", start_body(f, "run", "grant-1"))
    q.driver.active = None
    pause(f, granted)
    assert put_resume(q, granted) is True
    entry, = q.service.store.read().entries
    assert entry.kind == "resume" and entry.preauthorization.expected_control_id == "pause"
    assert entry.key == ("run", "run_authorization_control", "resume-1")


def test_a_resume_the_driver_already_holds_is_not_ready(q):
    f = q.f
    granted, _ = f.policy.authorize("run", start_body(f, "run", "grant-1"))
    q.driver.active = ("run", "grant-1")
    assert not_ready(q, "run", "resume", granted) == "queue_not_ready"


# --- room, order, withdraw ------------------------------------------------------------------------


def unreadable_entry(run_id, number=0):
    preauth = StartPreauth(f"grant-{number}", "sha256:" + "a" * 64, "sha256:" + "b" * 64, ask(),
                           None, "vasily", NOW)
    return QueueEntry(run_id, "start", NOW, "vasily", preauth, None)


def test_thirty_third_entry_is_queue_full(q):
    full = tuple(unreadable_entry(f"gone-{number}", number) for number in range(MAX_QUEUE))
    q.service.store.write(full)
    before = file_bytes(q)
    assert codes(lambda: put(q, "run")) == "queue_full"
    assert file_bytes(q) == before and len(q.service.store.read().entries) == MAX_QUEUE


def test_a_full_queue_still_takes_a_new_preauthorization_for_a_run_it_holds(q):
    put(q, "run")
    rest = tuple(unreadable_entry(f"gone-{number}", number) for number in range(MAX_QUEUE - 1))
    q.service.store.write((*q.service.store.read().entries, *rest))
    assert put(q, "run", authorization_id="grant-2") is False


def test_an_entry_that_is_done_does_not_count_toward_the_thirty_two(q):
    ended_run(q.f, "done")
    done = QueueEntry("done", "start", NOW, "vasily", StartPreauth(
        "grant-1", "sha256:" + "a" * 64, "sha256:" + "b" * 64, ask(), None, "vasily", NOW), None)
    rest = tuple(unreadable_entry(f"gone-{number}", number) for number in range(MAX_QUEUE - 1))
    q.service.store.write((done, *rest))
    assert put(q, "run") is True
    kept = [row.run_id for row in q.service.store.read().entries]
    assert "done" not in kept and kept[-1] == "run" and len(kept) == MAX_QUEUE


def test_order_with_a_stale_revision_is_queue_changed_and_the_same_order_writes_nothing(q):
    for run_id in ("run", "run-b", "run-c"):
        put(q, run_id)
    file = q.service.store.read()
    ids = ["run", "run-b", "run-c"]
    before, frames = file_bytes(q), list(q.frames)
    assert q.service.order(file.revision - 1, ids) is False            # the same order: nothing
    assert file_bytes(q) == before and q.frames == frames
    assert codes(lambda: q.service.order(file.revision - 1, ["run-c", "run", "run-b"])) == (
        "queue_changed")
    assert codes(lambda: q.service.order(file.revision - 1, ["run-c", "gone"])) == "queue_changed"
    assert file_bytes(q) == before
    assert q.service.order(file.revision, ["run-c", "run", "run-b"]) is True
    now_file = q.service.store.read()
    assert [row.run_id for row in now_file.entries] == ["run-c", "run", "run-b"]
    assert now_file.revision == file.revision + 1


def test_an_order_that_is_not_a_permutation_of_the_visible_entries_is_contract_invalid(q):
    for run_id in ("run", "run-b"):
        put(q, run_id)
    revision = q.service.store.read().revision
    before = file_bytes(q)
    for ids in (["run"], ["run", "run-b", "run-c"], ["run", "run-c"], []):
        with pytest.raises(ContractError):
            q.service.order(revision, ids)
    assert file_bytes(q) == before


def test_order_moves_only_the_runs_whose_place_changed_and_tells_the_desk_about_them(q):
    for run_id in ("run", "run-b", "run-c"):
        put(q, run_id)
    q.frames.clear()
    q.service.order(q.service.store.read().revision, ["run", "run-c", "run-b"])
    assert sorted(q.frames) == ["run-b", "run-c"]


def test_withdraw_of_an_absent_run_writes_nothing(q):
    put(q, "run")
    before, frames = file_bytes(q), list(q.frames)
    assert q.service.withdraw("run-b") is False
    assert q.service.withdraw("never-queued") is False
    assert file_bytes(q) == before and q.frames == frames


def test_withdraw_takes_the_entry_out_forgets_its_admission_and_tells_the_desk(q):
    put(q, "run"), put(q, "run-b")
    q.frames.clear()
    assert q.service.withdraw("run") is True
    assert [row.run_id for row in q.service.store.read().entries] == ["run-b"]
    assert {key[0] for key in q.service.admitted} == {"run-b"} and q.frames == ["run"]


def test_a_withdraw_asks_the_owner_only_when_it_is_about_to_write(q):
    put(q, "run")

    def no_owner():
        raise AuthorizationError("a live project owner is required for bounded execution")
    q.f.policy.owner_check = no_owner
    assert q.service.withdraw("run-b") is False
    with pytest.raises(AuthorizationError):
        q.service.withdraw("run")
    assert [row.run_id for row in q.service.store.read().entries] == ["run"]


def test_order_and_withdraw_never_append_a_grant_or_a_control(q):
    f = q.f
    granted, _ = f.policy.authorize("run-c", start_body(f, "run-c", "live-1"))
    for run_id in ("run", "run-b"):
        put(q, run_id)
    before = journals(q)
    q.service.order(q.service.store.read().revision, ["run-b", "run"])
    q.service.withdraw("run-b")
    q.service.withdraw("run")
    assert journals(q) == before
    assert granted.authorization_id == "live-1"


def test_a_run_started_by_hand_takes_its_entry_out_through_the_hook(q):
    put(q, "run"), put(q, "run-b")
    q.f.policy.authorize("run", start_body(q.f, "run", "grant-1"))
    assert [row.run_id for row in q.service.store.read().entries] == ["run-b"]


def test_a_revoke_takes_out_a_resume_entry_and_leaves_a_start_entry(q):
    f = q.f
    granted, _ = f.policy.authorize("run", start_body(f, "run", "grant-1"))
    q.driver.active = None
    pause(f, granted)
    put_resume(q, granted)
    put(q, "run-b")
    f.policy.control("run", {**resume_body(granted, "revoke-1", "pause"), "action": "revoke"})
    assert [row.run_id for row in q.service.store.read().entries] == ["run-b"]
    q.service.run_acted("run-b", "revoke")
    assert [row.run_id for row in q.service.store.read().entries] == ["run-b"]
    q.service.run_acted("run-b", "authorize")
    assert q.service.store.read().entries == ()


# --- the read -------------------------------------------------------------------------------------


def test_queue_file_and_its_preauthorizations_survive_a_new_api_on_the_same_root(q):
    put(q, "run"), put(q, "run-b")
    granted = q.service.store.read()
    fresh = QueueService(q.f.policy, TaskStore(q.root), mode="active")
    again = fresh.store.read()
    assert again == granted and again.entries[0].preauthorization is not None
    rows = fresh.read()["entries"]
    assert [(row["run_id"], row["state"], row["reason_code"]) for row in rows] == [
        ("run", "confirmation_required", "server_restarted"),
        ("run-b", "confirmation_required", "server_restarted")]
    assert rows[0]["preauthorization"]["authorized_by"] == "vasily"
    assert q.service.read()["entries"][0]["state"] == "preauthorized"


def test_enqueue_in_view_mode_is_recorded_and_the_entry_reads_project_not_active(q):
    q.f.policy.driver = None
    view = QueueService(q.f.policy, TaskStore(q.root), mode="view")
    q.f.policy.queue = view
    body = start_body(q.f, "run", "grant-1")
    assert view.enqueue(parse_write({"run_id": "run", "start": body}, now(q))) is True
    payload = view.read()
    assert payload["slot"] == {"state": "unavailable", "run_id": None,
                               "reason_code": "project_not_active"}
    assert [(row["state"], row["reason_code"]) for row in payload["entries"]] == [
        ("preauthorized", "project_not_active")]


def test_read_hides_a_start_entry_whose_run_holds_its_own_or_another_live_grant(q):
    put(q, "run"), put(q, "run-b"), put(q, "run-c")
    q.f.policy.queue = None                                # a direct road that does not tell
    q.f.policy.authorize("run", start_body(q.f, "run", "grant-1"))        # its own grant
    q.driver.active = None
    q.f.policy.authorize("run-b", start_body(q.f, "run-b", "someone-else"))  # another grant
    before = file_bytes(q)
    rows = q.service.read()["entries"]
    assert [(row["run_id"], row["position"]) for row in rows] == [("run-c", 1)]
    assert file_bytes(q) == before, "a read must not remove what it hides"
    assert len(q.service.store.read().entries) == 3


def test_a_read_carries_the_title_of_the_task_a_run_was_opened_for(q):
    TaskStore(q.root).create_task(TaskRecord(task_id="task-7", title="Seven", work_scope="task-7",
                                             created_at=NOW))
    add_run(q.f, "task-7-r1", task_id="task-7")
    put(q, "task-7-r1")
    row, = q.service.read()["entries"]
    assert (row["task_id"], row["title"]) == ("task-7", "Seven")


def test_slot_maps_every_holder_state_to_free_busy_stuck_or_unavailable_with_existing_names(q):
    free = q.service.read()["slot"]
    assert free == {"state": "free", "run_id": None, "reason_code": None}
    q.f.policy.authorize("run", start_body(q.f, "run", "grant-1"))
    q.driver.active = ("run", "grant-1")
    assert q.service.read()["slot"] == {"state": "busy", "run_id": "run", "reason_code": "ready"}
    q.driver.reasons["run"] = "seed_blocked"
    assert q.service.read()["slot"] == {"state": "stuck", "run_id": "run",
                                        "reason_code": "seed_blocked"}
    q.driver.reasons["run"] = "ready"
    q.f.ticks[0] = "2026-08-11T12:06:00Z"
    assert q.service.read()["slot"]["state"] == "stuck"
    assert q.service.read()["slot"]["reason_code"] == "expired"
    q.driver.holding = True
    assert q.service.read()["slot"] == {"state": "unavailable", "run_id": "run",
                                        "reason_code": "server_stopping"}
    q.f.policy.driver = None
    assert q.service.read()["slot"]["reason_code"] == "owner_required"
    viewing = QueueService(q.f.policy, TaskStore(q.root), mode="view")
    assert viewing.read()["slot"]["reason_code"] == "project_not_active"
