"""The pump executes the continue-after flag (spec 4.3.4 S2, 4.4.4 step 3).

The flag is the owner's advance permission to resume some runs and to start the task queue when
the project is next made active. It is executed only by the child a hub started for a planned
transition (`--mode active --transition <id> --auto-continue <flag_id>@<revision>`), on the first
pass, by the conditional write of lane H's `consume`: the file is rewritten (off, `consumed`) only
if it still holds exactly that flag. Then each run the owner listed is resumed by a control of the
flag's actor, one per free slot, only while the grant, its digest and its last control are the ones
the flag recorded; a run that moved on waits for a human. A crash after the consumption restores
nothing: the list lives in this process alone.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from itertools import count
from types import SimpleNamespace

import pytest

from conductor.command import auto_continue, queue_flag
from conductor.command.artifacts import ArtifactDocument
from conductor.command.auto_continue import AutoContinueStore
from conductor.command.queue_bodies import parse_write
from conductor.command.queue_reading import record_digest
from conductor.command.queue_service import QueueService
from conductor.command.queue_store import QueueStore
from conductor.command.store_errors import StoreError
from conductor.command.task_store import TaskStore
from tests.queue_fixtures import (
    Holder, NOW, long_root, project, refuse_receipt_budget, start_body)
from tests.test_policy_runtime import ARGS
from tests.test_queue_pump import grants, paused_grant, queued

TRANSITION = "b71e4d09-c2a8-4f35-a6d8-1c0e9f3b5274"
NONCE = "3f9c0a1b2c3d4e5f60718293a4b5c6d7"
FLAGS = iter(f"{number:08x}-1111-4222-8333-444444444444" for number in range(1, 99))
ACTOR = "Вы: Анна"
LATER = "2026-08-11T12:01:00Z"


def make_q(root, *more):
    f = project(root, "run-b", "run-c", *more)
    f.policy.driver = Holder()
    frames = []
    f.policy.notify = frames.append
    q = SimpleNamespace(f=f, frames=frames, root=root, flags=AutoContinueStore(root),
                        driver=f.policy.driver, service=None)
    q.service = child(q)
    f.policy.queue = q.service
    return q


@pytest.fixture
def q(tmp_path):
    return make_q(tmp_path)


def set_flag(q, runs=(), *, queue=False, actor=ACTOR, enabled=True):
    """The owner sets (or takes down) the flag in the desk: the door of lane H."""
    body = {"enabled": enabled, "actor": actor, "resume_runs": list(runs),
            "start_task_queue": queue}
    status, record = auto_continue.set_flag(q.flags, q.f.store, body, q.f.policy.clock,
                                            new_flag_id=lambda: next(FLAGS))
    assert status == 200
    return record


def child(q, *, handed=None, transition=TRANSITION, mode="active"):
    """The queue of a child the hub started; `handed` is the flag record it was handed, or None."""
    spec = None if handed is None else f"{handed['flag_id']}@{handed['revision']}"
    return QueueService(q.f.policy, TaskStore(q.root), mode=mode, project_id=NONCE,
                        transition_id=None if handed is None else transition,
                        auto_continue=spec, flags=q.flags)


def activate(q, record, **changes):
    """Start the child the hub would start for this flag: a driver that holds nothing."""
    q.driver.active = None
    q.service = child(q, handed=record, **changes)
    q.f.policy.queue = q.service
    return q.service


def controls(q, run_id):
    return [row.value for row in q.f.store.read(run_id).records
            if row.kind == "run_authorization_control"]


def resumed(q, run_id):
    return [row for row in controls(q, run_id) if row.action == "resume"]


def three_paused(q):
    for run_id in ("run", "run-b", "run-c"):
        paused_grant(q, run_id, f"grant-{run_id}")
        q.driver.active = None


def digest_of(q, run_id):
    return next(row.value.authorization_digest for row in q.f.store.read(run_id).records
                if row.kind == "run_authorization")


def enqueue_in_view(q, *pairs):
    """What a process opened for viewing wrote to the queue before the project was activated."""
    q.f.policy.driver = None
    viewer = QueueService(q.f.policy, TaskStore(q.root), mode="view")
    q.f.policy.queue = viewer
    for run_id, grant_id in pairs:
        body = start_body(q.f, run_id, grant_id)
        viewer.enqueue(parse_write({"run_id": run_id, "start": body}, q.f.policy.clock()))
    q.f.policy.driver = q.driver = Holder()


def test_auto_continue_resumes_only_the_runs_the_owner_listed_with_the_flag_actor(q):
    three_paused(q)
    service = activate(q, set_flag(q, ["run", "run-b"]))
    q.f.ticks[0] = LATER
    assert service.start_next() is True
    control, = resumed(q, "run")
    assert (control.actor, control.recorded_at, control.expected_control_id) == (
        ACTOR, LATER, "pause")
    assert q.driver.active == ("run", "grant-run")
    assert resumed(q, "run-b") == [] and resumed(q, "run-c") == []


def test_flag_resumes_go_first_one_per_free_slot_with_an_auto_continue_receipt(q):
    three_paused(q)
    record = set_flag(q, ["run", "run-b"], queue=True)
    service = activate(q, record)
    assert service.start_next() is True and q.driver.active[0] == "run"
    assert service.start_next() is False                   # the slot is taken: one at a time
    assert resumed(q, "run-b") == []
    q.driver.active = None                                 # run leaves the slot
    assert service.start_next() is True and q.driver.active[0] == "run-b"
    control, = resumed(q, "run")
    receipt = service.store.read_receipt("run", "run_authorization_control", control.control_id)
    assert (receipt.admission, receipt.flag_id, receipt.transition_id) == (
        "auto_continue", record["flag_id"], TRANSITION)
    assert (receipt.authorized_by, receipt.preauthorized_at) == (ACTOR, record["set_at"])
    assert receipt.digest == digest_of(q, "run")
    assert receipt.record_digest == record_digest(control)


def test_activation_consumes_the_flag_before_the_first_resume_and_a_crash_restores_nothing(q):
    three_paused(q)
    record = set_flag(q, ["run", "run-b"])
    service = activate(q, record)
    seen, original = [], q.f.policy.store.append

    def watching(value):
        if getattr(value, "action", None) == "resume":
            seen.append(q.flags.read())
        return original(value)
    q.f.policy.store.append = watching
    assert service.start_next() is True
    q.f.policy.store.append = original
    at_the_resume, = seen
    assert at_the_resume.enabled is False and at_the_resume.consumed is not None
    consumed = q.flags.read()
    assert (consumed.consumed.transition_id, consumed.consumed.activation_nonce) == (
        TRANSITION, NONCE)
    assert consumed.revision == record["revision"] + 1
    assert [row.run_id for row in consumed.resume_runs] == ["run", "run-b"]   # kept, consumed
    q.driver.active = None                                 # the child dies; nothing is handed again
    for restarted in (child(q), child(q, handed=record)):
        q.f.policy.queue = restarted
        assert restarted.start_next() is False
    assert resumed(q, "run-b") == [] and q.flags.read() == consumed


def test_a_new_grant_or_control_after_the_flag_makes_the_run_wait_for_a_human(q):
    three_paused(q)
    record = set_flag(q, ["run", "run-b", "run-c"])
    q.f.policy.queue = None
    by_hand = {"control_id": "by-hand", "authorization_id": "grant-run",
               "authorization_digest": digest_of(q, "run"), "action": "resume",
               "actor": "owner", "expected_control_id": "pause"}
    q.f.policy.control("run", by_hand)                     # run: resumed and paused again
    q.f.policy.control("run", {**by_hand, "control_id": "by-hand-2", "action": "pause",
                               "expected_control_id": "by-hand"})
    q.f.policy.control("run-b", {**by_hand, "control_id": "rev", "action": "revoke",   # run-b:
        "authorization_id": "grant-run-b", "authorization_digest": digest_of(q, "run-b"),
        "expected_control_id": "pause"})                   # revoked after the flag
    service = activate(q, record)
    before = {run_id: q.f.store.read(run_id).records for run_id in ("run", "run-b")}
    assert service.start_next() is True                    # only run-c is what the flag recorded
    assert resumed(q, "run-c") and [row.control_id for row in resumed(q, "run")] == ["by-hand"]
    assert q.f.store.read("run").records == before["run"]
    assert q.f.store.read("run-b").records == before["run-b"]
    assert service.flag_runs == []


def test_a_flag_removed_or_replaced_before_consumption_is_not_executed_and_the_new_flag_survives(
        q):
    three_paused(q)
    old = set_flag(q, ["run"])
    newer = set_flag(q, ["run-b"])                         # replaced after the hub read `old`
    service = activate(q, old)
    before = q.flags.read()
    assert service.start_next() is False
    assert q.flags.read() == before
    assert before.flag_id == newer["flag_id"] and before.enabled
    assert resumed(q, "run") == [] and resumed(q, "run-b") == []
    set_flag(q, enabled=False)                             # taken down after the hub read it
    service = activate(q, newer)
    assert service.start_next() is False
    assert q.flags.read().enabled is False and resumed(q, "run-b") == []


@pytest.mark.parametrize("how", ["standalone", "hub_restart_or_recovered", "view",
                                 "flag_without_transition", "transition_without_flag"])
def test_a_child_without_a_transition_or_started_after_recovery_never_consumes_the_flag(q, how):
    three_paused(q)
    record = set_flag(q, ["run"], queue=True)
    before = q.flags.read()
    spec = f"{record['flag_id']}@{record['revision']}"
    if how == "view":
        q.f.policy.driver = None
        service = child(q, handed=record, mode="view")
    elif how == "flag_without_transition":
        service = QueueService(q.f.policy, TaskStore(q.root), project_id=NONCE,
                               auto_continue=spec, flags=q.flags)
    elif how == "transition_without_flag":
        service = QueueService(q.f.policy, TaskStore(q.root), project_id=NONCE,
                               transition_id=TRANSITION, flags=q.flags)
    else:
        service = child(q)                                 # no --transition, no --auto-continue
    q.f.policy.queue = service
    assert service.start_next() is False
    assert q.flags.read() == before and resumed(q, "run") == []


def test_a_planned_view_to_active_transition_consumes_the_same_flag_once_and_admits_the_queue(q):
    enqueue_in_view(q, ("run", "queued-1"), ("run-b", "queued-2"))
    record = set_flag(q, [], queue=True)
    service = activate(q, record)
    assert service.admitted == set()                       # nothing is admitted before the pass
    assert service.start_next() is True                    # consumes, admits, starts the head
    assert [row.authorization_id for row in grants(q)] == ["queued-1"]
    assert q.flags.read().consumed.transition_id == TRANSITION
    again = child(q, handed=record)
    q.f.policy.queue = again
    q.driver.active = None
    assert again.start_next() is False, "the same flag is never consumed twice"
    assert queued(q) == ["run-b"] and grants(q, "run-b") == []


def test_an_action_left_open_after_the_flag_makes_the_run_wait_for_a_human(q):
    q.f.policy.authorize("run", start_body(q.f, "run", "grant-run"))    # granted, never paused
    q.driver.active = None
    paused_grant(q, "run-c", "grant-run-c")
    q.driver.active = None
    record = set_flag(q, ["run", "run-c"])                 # `run` has no control: last is None
    q.f.policy.queue = None
    q.driver.active = ("run", "grant-run")                 # the grant is live again, by hand
    proposal = q.f.service.propose(run_id="run", attempt_id="attempt", instance_id="doer",
        capability="dispatch", arguments=ARGS, scope=("work/item",), proposed_by="run-driver",
        rationale="Approved work", timeout_seconds=30, node_id="do", proposal_id="proposal")
    q.f.runtime.authorize_policy("run", proposal.proposal_id, "grant-run")   # open, never settled
    service = activate(q, record)
    assert service.start_next() is True                    # run-c is still what was seen
    assert resumed(q, "run") == [] and resumed(q, "run-c")


def test_a_flag_without_the_queue_start_admits_no_preauthorization(q):
    enqueue_in_view(q, ("run", "queued-1"))
    service = activate(q, set_flag(q, [], queue=False))
    assert service.start_next() is False and grants(q) == []
    row, = service.read()["entries"]
    assert (row["state"], row["reason_code"]) == ("confirmation_required", "server_restarted")


def test_auto_continue_flag_admits_the_preauthorizations_on_file_and_the_digest_still_decides(q):
    enqueue_in_view(q, ("run", "queued-1"), ("run-b", "queued-2"))
    q.f.store.append(ArtifactDocument(artifact_id="instruction-2", run_id="run",
        artifact_ref="instructions", created_at=NOW, media_type="text/plain", content="Changed"))
    service = activate(q, set_flag(q, [], queue=True))
    assert service.start_next() is True
    assert grants(q) == [] and [row.authorization_id for row in grants(q, "run-b")] == ["queued-2"]
    entry, = service.store.read().entries
    assert entry.run_id == "run" and entry.dropped.reason_code == "terms_changed"


def test_a_store_error_after_the_receipt_of_a_flag_resume_retries_it_once(q):
    three_paused(q)
    service = activate(q, set_flag(q, ["run"]))
    original = service.store.write_receipt

    def failing(receipt):
        original(receipt)
        raise StoreError("the write boundary")
    service.store.write_receipt = failing
    assert service.start_next() is False and resumed(q, "run") == []
    service.store.write_receipt = original
    assert service.start_next() is True and len(resumed(q, "run")) == 1
    assert service.start_next() is False and len(resumed(q, "run")) == 1


def test_a_flag_resume_written_but_not_activated_is_never_written_twice(q):
    three_paused(q)
    service = activate(q, set_flag(q, ["run"]))
    original = q.f.policy.driver.activate

    def failing(run_id, grant_id):
        raise StoreError("the write boundary")
    q.f.policy.driver.activate = failing
    assert service.start_next() is False                   # the control is in the journal
    q.f.policy.driver.activate = original
    assert len(resumed(q, "run")) == 1
    assert service.start_next() is False                   # the retry finds it and writes no more
    assert len(resumed(q, "run")) == 1 and q.driver.active is None


def ticking(start):
    """A clock that moves one second on every call, so the order of two reads is visible."""
    base, calls = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ"), count()
    return lambda: (base + timedelta(seconds=next(calls))).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_a_flag_resume_is_recorded_no_earlier_than_the_flag_was_consumed(q):
    three_paused(q)
    service = activate(q, set_flag(q, ["run"]))
    q.f.policy.clock = ticking(LATER)
    assert service.start_next() is True
    consumed = q.flags.read().consumed
    control, = resumed(q, "run")
    receipt = service.store.read_receipt("run", "run_authorization_control", control.control_id)
    assert control.recorded_at >= consumed.at and receipt.started_at == control.recorded_at


def test_a_flag_resume_control_is_named_flag_and_thirty_two_hex_by_the_flag_and_the_run(q):
    three_paused(q)
    record = set_flag(q, ["run", "run-b"])
    service = activate(q, record)
    assert service.start_next() is True
    q.driver.active = None
    assert service.start_next() is True
    names = [resumed(q, "run")[0].control_id, resumed(q, "run-b")[0].control_id]
    assert all(re.fullmatch(r"flag-[0-9a-f]{32}", name) for name in names) and names[0] != names[1]
    assert names == [queue_flag.control_id_of(record["flag_id"], run) for run in ("run", "run-b")]
    assert queue_flag.control_id_of("another-flag", "run") != names[0]


def test_a_listed_run_whose_receipt_cannot_be_written_is_struck_and_what_is_behind_it_goes_on(
        q, monkeypatch):
    for run_id in ("run", "run-c"):
        paused_grant(q, run_id, f"grant-{run_id}")
        q.driver.active = None
    enqueue_in_view(q, ("run-b", "queued-b"))
    service = activate(q, set_flag(q, ["run", "run-c"], queue=True))
    refuse_receipt_budget(monkeypatch, "run")
    assert service.start_next() is True                    # `run` is struck, `run-c` is resumed
    assert service.flag_runs == [] and resumed(q, "run") == []
    assert q.driver.active[0] == "run-c" and len(resumed(q, "run-c")) == 1
    q.driver.active = None
    assert service.start_next() is True                    # and the queue behind the flag starts
    assert [row.authorization_id for row in grants(q, "run-b")] == ["queued-b"]


@pytest.mark.skipif(os.name != "nt", reason="the Windows path budget applies to Windows paths")
def test_at_a_real_root_a_listed_run_whose_flag_receipt_is_over_the_budget_is_struck(tmp_path):
    long_run = "run-" + "x" * 40
    kind = "run_authorization_control"
    probe = QueueStore(tmp_path).receipt_path(long_run, kind, queue_flag.control_id_of("f", "f"))
    q = make_q(long_root(tmp_path, 262 - 14 - (len(str(probe)) - len(str(tmp_path)))), long_run)
    for run_id in (long_run, "run"):
        paused_grant(q, run_id, f"grant-{run_id}")
        q.driver.active = None
    service = activate(q, set_flag(q, [long_run, "run"]))
    assert service.start_next() is True                    # the long id is struck, `run` resumes
    assert service.flag_runs == [] and resumed(q, long_run) == []
    assert q.driver.active[0] == "run" and len(resumed(q, "run")) == 1
