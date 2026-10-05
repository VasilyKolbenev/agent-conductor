"""The queue pump: what starts when the slot is free, and what a crash at each write leaves (4.4.4).

A preauthorization is the human's advance permission, so the pump starts only what this process
admitted, only when the slot is free, and only after asking the preview again and finding the very
digest the human confirmed. The journal is the single source of the fact that a grant or a control
was accepted; the receipt and the entry are servants of it, and every state a crash can leave
between the three writes is reconciled by the next pass without writing a second record.
The driver doubles are `queue_fixtures.Holder`; the real driver runs in the last tests.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from conductor.command import queue_pump
from conductor.command.api_contracts import refusal_from_exception
from conductor.command.artifacts import ArtifactDocument
from conductor.command.policy_driver import SlotBusy
from conductor.command.policy_view import automation_view
from conductor.command.queue_bodies import parse_write
from conductor.command.queue_reading import record_digest
from conductor.command.queue_service import QueueService
from conductor.command.queue_store import (
    Dropped, QueueEntry, Receipt, ReceiptExists, StartPreauth)
from conductor.command.run_authorization import RunAuthorization, RunAuthorizationControl
from conductor.command.run_store import RunStore
from conductor.command.store_errors import StoreError
from conductor.command.task_store import TaskStore
from tests.queue_fixtures import Holder, NOW, ask, project, resume_body, start_body
from tests.test_command_queue import ended_run
from tests.test_policy_driver import attach_driver, authorize

LATER = "2026-08-11T12:01:00Z"
EXPIRED = "2026-08-11T12:07:00Z"


@pytest.fixture
def q(tmp_path):
    f = project(tmp_path, "run-b", "run-c")
    f.policy.driver = Holder()
    frames = []
    f.policy.notify = frames.append
    service = QueueService(f.policy, TaskStore(tmp_path), mode="active")
    f.policy.queue = service
    return SimpleNamespace(f=f, service=service, frames=frames, root=tmp_path,
                           driver=f.policy.driver)


def put(q, run_id="run", authorization_id="grant-1", **changes):
    body = start_body(q.f, run_id, authorization_id, **changes)
    return q.service.enqueue(parse_write({"run_id": run_id, "start": body},
                                         q.f.policy.clock()))


def put_resume(q, grant, control_id="resume-1", expected="pause", run_id="run"):
    body = resume_body(grant, control_id, expected)
    return q.service.enqueue(parse_write({"run_id": run_id, "resume": body},
                                         q.f.policy.clock()))


def records(q, run_id, kind):
    return [row.value for row in q.f.store.read(run_id).records if row.kind == kind]


def grants(q, run_id="run"):
    return records(q, run_id, "run_authorization")


def controls(q, run_id="run"):
    return records(q, run_id, "run_authorization_control")


def queued(q):
    return [row.run_id for row in q.service.store.read().entries]


def restart(q):
    """The process dies and another takes the root: a new service, a driver that holds nothing."""
    q.driver = q.f.policy.driver = Holder()
    q.service = QueueService(q.f.policy, TaskStore(q.root), mode="active")
    q.f.policy.queue = q.service


def paused_grant(q, run_id="run", grant_id="grant-1"):
    granted, _ = q.f.policy.authorize(run_id, start_body(q.f, run_id, grant_id))
    q.driver.active = None
    q.f.policy.control(run_id, {"control_id": "pause", "authorization_id": grant_id,
        "authorization_digest": granted.authorization_digest, "action": "pause",
        "actor": "owner", "expected_control_id": None})
    return granted


# --- the pass that starts a run -------------------------------------------------------------------


def test_freed_slot_starts_the_head_under_its_preauthorization(q):
    put(q, "run"), put(q, "run-b")
    confirmed = q.service.store.read().entries[0].preauthorization.preview_digest
    q.f.ticks[0] = LATER
    q.frames.clear()
    assert q.service.start_next() is True
    granted, = grants(q)
    assert (granted.authorization_id, granted.authorized_by) == ("grant-1", "vasily")
    assert granted.authorized_at == LATER and granted.expires_at == "2026-08-11T12:06:00Z"
    receipt = q.service.store.read_receipt("run", "run_authorization", "grant-1")
    assert (receipt.preauthorized_at, receipt.started_at, receipt.admission) == (
        NOW, LATER, "confirmation")
    assert receipt.digest == confirmed and receipt.record_digest == granted.authorization_digest
    assert q.driver.active == ("run", "grant-1")
    assert queued(q) == ["run-b"] and grants(q, "run-b") == []   # one start per pass
    assert "run" in q.frames


def test_a_pass_with_the_slot_taken_starts_nothing_and_keeps_the_entry(q):
    put(q, "run"), put(q, "run-b")
    assert q.service.start_next() is True
    before = q.service.store.path.read_bytes()
    assert q.service.start_next() is False                 # run holds the slot now
    assert q.service.store.path.read_bytes() == before and grants(q, "run-b") == []


def changed_run(q, run_id):
    q.f.store.append(ArtifactDocument(artifact_id="instruction-2", run_id=run_id,
        artifact_ref="instructions", created_at=NOW, media_type="text/plain", content="Changed"))


def test_a_document_published_after_enqueue_needs_confirmation_and_the_next_entry_starts(q):
    put(q, "run"), put(q, "run-b")
    changed_run(q, "run")
    q.f.ticks[0] = LATER
    assert q.service.start_next() is True
    assert grants(q) == [] and len(grants(q, "run-b")) == 1
    assert queued(q) == ["run"]                            # the started entry went, this stays
    entry, = q.service.store.read().entries
    assert entry.preauthorization is None and entry.dropped == Dropped("terms_changed", LATER)
    row, = q.service.read()["entries"]
    assert (row["state"], row["reason_code"], row["state_since"]) == (
        "confirmation_required", "terms_changed", LATER)


def test_an_entry_that_needs_confirmation_does_not_hold_the_ones_behind_it_and_keeps_its_place(q):
    put(q, "run"), put(q, "run-b"), put(q, "run-c")
    changed_run(q, "run")
    assert q.service.start_next() is True
    assert len(grants(q, "run-b")) == 1 and grants(q, "run-c") == []
    assert queued(q) == ["run", "run-c"]                   # run kept the first place, unconfirmed


def test_a_dropped_entry_keeps_its_place_and_a_new_confirmation_fills_it_again(q):
    put(q, "run"), put(q, "run-b")
    changed_run(q, "run")
    q.service.start_next()                                 # run-b starts, run is dropped
    q.driver.active = None
    put(q, "run", authorization_id="grant-2")
    entry, = q.service.store.read().entries
    assert entry.run_id == "run" and entry.dropped is None
    assert entry.preauthorization.authorization_id == "grant-2"
    assert entry.key in q.service.admitted


def test_nothing_starts_after_restart_without_the_flag_until_a_new_confirmation(q):
    put(q, "run")
    restart(q)
    before = q.f.store.read("run").records
    assert q.service.start_next() is False
    assert q.f.store.read("run").records == before and q.driver.active is None
    row, = q.service.read()["entries"]
    assert (row["state"], row["reason_code"]) == ("confirmation_required", "server_restarted")
    put(q, "run", authorization_id="grant-2")              # the human confirms again
    assert q.service.start_next() is True
    assert [grant.authorization_id for grant in grants(q)] == ["grant-2"]


def test_a_preauthorization_written_in_a_view_process_is_not_admitted_after_activation(q):
    q.f.policy.driver = None
    view = QueueService(q.f.policy, TaskStore(q.root), mode="view")
    q.f.policy.queue = view
    body = start_body(q.f, "run", "grant-1")
    view.enqueue(parse_write({"run_id": "run", "start": body}, q.f.policy.clock()))
    restart(q)                                             # the same root, now an active child
    assert q.service.start_next() is False and grants(q) == []


# --- resume ---------------------------------------------------------------------------------------


def test_resume_entry_resumes_the_paused_grant_and_an_expired_grant_needs_confirmation(q):
    granted = paused_grant(q, "run")
    put_resume(q, granted)
    q.f.ticks[0] = LATER
    assert q.service.start_next() is True
    control, = [row for row in controls(q) if row.control_id == "resume-1"]
    assert (control.action, control.actor, control.recorded_at) == ("resume", "vasily", LATER)
    assert control.expected_control_id == "pause"
    assert q.driver.active == ("run", "grant-1") and queued(q) == []
    receipt = q.service.store.read_receipt("run", "run_authorization_control", "resume-1")
    assert (receipt.preauthorized_at, receipt.started_at) == (NOW, LATER)
    assert receipt.record_digest == record_digest(control)
    q.driver.active = None                                 # the first run let the slot go
    second = paused_grant(q, "run-b")                      # a grant whose time then runs out
    put_resume(q, second, run_id="run-b")
    q.driver.active = None
    q.f.ticks[0] = EXPIRED
    assert q.service.start_next() is False
    entry, = q.service.store.read().entries
    assert entry.dropped == Dropped("grant_expired", EXPIRED) and entry.preauthorization is None
    assert [row.control_id for row in controls(q, "run-b")] == ["pause"]


def test_a_resume_whose_grant_moved_on_since_the_confirmation_is_dropped_as_grant_changed(q):
    granted = paused_grant(q, "run")
    put_resume(q, granted)
    q.f.policy.queue = None                                # the owner resumed by hand elsewhere
    q.f.policy.control("run", {**resume_body(granted, "by-hand", "pause"), "action": "resume"})
    q.driver.active = None
    assert q.service.start_next() is False
    entry, = q.service.store.read().entries
    assert entry.dropped.reason_code == "grant_changed"
    assert [row.control_id for row in controls(q)] == ["pause", "by-hand"]


# --- who keeps the slot ---------------------------------------------------------------------------


def test_holder_waiting_at_a_gate_keeps_the_slot(q):
    q.f.policy.authorize("run-c", start_body(q.f, "run-c", "live-1"))
    q.driver.reasons["run-c"] = "waiting"
    put(q, "run")
    assert q.service.start_next() is False and grants(q) == []
    assert q.service.read()["slot"]["state"] == "busy"
    assert queued(q) == ["run"] and q.service.read()["entries"][0]["reason_code"] == "slot_busy"


def test_paused_runs_action_in_flight_keeps_the_slot_until_its_result(q):
    put(q, "run")
    q.driver.inflight = ("run-c", "action-1")
    assert q.service.start_next() is False and grants(q) == []
    q.driver.inflight = None                               # the result was written
    assert q.service.start_next() is True and len(grants(q)) == 1


@pytest.mark.parametrize("why", ["stalled", "feedback_required", "expired"])
def test_expired_stalled_and_feedback_required_holders_keep_the_slot_until_pause_or_revoke(q, why):
    holder, _ = q.f.policy.authorize("run-c", start_body(q.f, "run-c", "live-1"))
    put(q, "run")
    if why == "expired":
        q.f.ticks[0] = EXPIRED
    else:
        q.driver.reasons["run-c"] = why
    slot = q.service.read()["slot"]
    assert (slot["state"], slot["reason_code"], slot["run_id"]) == ("stuck", why, "run-c")
    assert q.service.start_next() is False and grants(q) == []
    q.f.policy.control("run-c", {"control_id": "pause", "authorization_id": "live-1",
        "authorization_digest": holder.authorization_digest, "action": "pause",
        "actor": "owner", "expected_control_id": None})   # the human lets the holder go
    assert q.service.read()["slot"]["state"] == "free"
    assert q.service.start_next() is True and len(grants(q)) == 1


def test_seed_blocked_holder_reads_stalled_and_keeps_the_slot(q):
    q.f.policy.authorize("run-c", start_body(q.f, "run-c", "live-1"))
    q.driver.reasons["run-c"] = "seed_blocked"
    view = automation_view(q.f.policy, "run-c")
    assert (view["state"], view["reason_code"]) == ("stalled", "seed_blocked")
    slot = q.service.read()["slot"]
    assert (slot["state"], slot["reason_code"], slot["run_id"]) == (
        "stuck", "seed_blocked", "run-c")
    put(q, "run")
    assert q.service.start_next() is False and grants(q) == []


def test_slot_busy_names_the_holder_on_authorize_and_on_resume(q):
    paused = paused_grant(q, "run-b", "grant-b")
    q.f.policy.authorize("run-c", start_body(q.f, "run-c", "live-1"))
    resume = {**resume_body(paused, "resume-b", "pause"), "action": "resume"}
    for call in (lambda: q.f.policy.authorize("run", start_body(q.f, "run", "grant-1")),
                 lambda: q.f.policy.control("run-b", resume)):
        with pytest.raises(SlotBusy) as refused:
            call()
        refusal = refusal_from_exception(refused.value)
        assert (refusal.status, refusal.code, dict(refusal.detail)) == (
            409, "slot_busy", {"run_id": "run-c"})


def test_direct_authorize_of_a_queued_run_removes_its_entry_under_the_same_root_gate(q):
    put(q, "run"), put(q, "run-b")
    seen, original = [], q.service.commit

    def commit(entries, touched):
        seen.append(RunStore.current_thread_holds_transaction())
        return original(entries, touched)
    q.service.commit = commit
    q.f.policy.authorize("run", start_body(q.f, "run", "by-hand"))
    assert queued(q) == ["run-b"] and seen == [True]
    assert [row.authorization_id for row in grants(q)] == ["by-hand"]


# --- the drain, the owner, an ended run -----------------------------------------------------------


def test_drain_hold_starts_nothing(q):
    put(q, "run")
    q.driver.holding = True
    assert q.service.start_next() is False and grants(q) == [] and queued(q) == ["run"]
    q.driver.holding = False
    assert q.service.start_next() is True


def test_owner_absent_keeps_preauthorizations_and_starts_nothing(q):
    put(q, "run")
    clock = {"now": 100.0}
    q.service.monotonic = lambda: clock["now"]
    asked = []

    def no_owner():
        asked.append(clock["now"])
        raise RuntimeError("no live owner")
    q.f.policy.owner_check = no_owner
    before = q.service.store.path.read_bytes()
    assert q.service.start_next() is False
    clock["now"] = 102.0
    assert q.service.start_next() is False                 # too soon: the owner is not asked
    clock["now"] = 105.5
    assert q.service.start_next() is False
    assert asked == [100.0, 105.5]
    assert q.service.store.path.read_bytes() == before and grants(q) == []
    q.f.policy.owner_check = lambda: None
    clock["now"] = 120.0
    assert q.service.start_next() is True


def test_entry_of_a_run_that_ended_while_queued_is_removed(q):
    ended_run(q.f, "done")
    done = StartPreauth("grant-1", "sha256:" + "a" * 64, "sha256:" + "b" * 64, ask(), None,
                        "vasily", NOW)
    q.service.store.write((QueueEntry("done", "start", NOW, "vasily", done, None),))
    q.frames.clear()
    assert q.service.start_next() is False
    assert queued(q) == [] and "done" in q.frames


# --- the pair, the orphan and the receipt that disagrees ------------------------------------------


def test_an_existing_matching_pair_is_recognised_before_a_new_preview(q, monkeypatch):
    put(q, "run")
    q.service.start_next()                                 # grant, receipt, activation, removal
    confirmed = q.service.store.read_receipt("run", "run_authorization", "grant-1").digest
    entry = QueueEntry("run", "start", NOW, "vasily", StartPreauth(
        "grant-1", confirmed, "sha256:" + "b" * 64, ask(), None, "vasily", NOW), None)
    q.service.store.write((entry,))                        # a removal that never happened
    q.driver.active = None

    def no_preview(*args, **kwargs):
        raise AssertionError("a preview was built for a key the journal already holds")
    monkeypatch.setattr(queue_pump, "build_preview", no_preview)
    before = q.f.store.read("run").records
    assert q.service.start_next() is False
    assert queued(q) == [] and q.f.store.read("run").records == before
    assert q.driver.active is None, "a reconciliation never activates"


def test_equal_record_ids_in_two_runs_or_two_record_kinds_keep_separate_receipts(q):
    put(q, "run", authorization_id="same")
    q.service.start_next()
    q.driver.active = None
    put(q, "run-b", authorization_id="same")
    q.service.start_next()
    q.driver.active = None
    first = grants(q, "run")[0]
    q.f.policy.control("run", {"control_id": "pause", "authorization_id": "same",
        "authorization_digest": first.authorization_digest, "action": "pause",
        "actor": "owner", "expected_control_id": None})
    put_resume(q, first, control_id="same", expected="pause")
    q.service.start_next()
    keys = [("run", "run_authorization"), ("run-b", "run_authorization"),
            ("run", "run_authorization_control")]
    receipts = [q.service.store.read_receipt(run, kind, "same") for run, kind in keys]
    assert all(receipts)
    assert len({q.service.store.receipt_path(run, kind, "same") for run, kind in keys}) == 3
    assert [row.record_digest for row in receipts] == [
        grants(q, "run")[0].authorization_digest, grants(q, "run-b")[0].authorization_digest,
        record_digest([row for row in controls(q) if row.control_id == "same"][0])]
    assert queued(q) == []


def direct_grant_with_receipt(q, *, disagree=None):
    """A grant written by hand, its entry, and a receipt: the state a crash after append leaves."""
    f = q.f
    body = start_body(f, "run", "grant-1")
    asked = parse_write({"run_id": "run", "start": body}, NOW)
    f.policy.queue = None
    granted, _ = f.policy.authorize("run", body)
    q.driver.active = None
    values = dict(run_id="run", kind="run_authorization", record_id="grant-1",
                  authorized_by="vasily", preauthorized_at=NOW, digest=body["preview_digest"],
                  record_digest=granted.authorization_digest, started_at=granted.authorized_at,
                  admission="confirmation")
    if disagree:
        values[disagree[0]] = disagree[1]
    q.service.store.write((QueueEntry("run", "start", NOW, "vasily", asked.preauth, None),))
    q.service.store.write_receipt(Receipt(**values))
    q.service.admitted.add(("run", "run_authorization", "grant-1"))


@pytest.mark.parametrize("field, value", [
    ("digest", "sha256:" + "d" * 64), ("authorized_by", "someone-else"),
    ("preauthorized_at", LATER), ("started_at", LATER),
    ("record_digest", "sha256:" + "d" * 64)])
def test_a_receipt_that_disagrees_with_the_journal_blocks_the_entry_and_writes_nothing(
        q, field, value):
    direct_grant_with_receipt(q, disagree=(field, value))
    path = q.service.store.receipt_path("run", "run_authorization", "grant-1")
    journal, queue_bytes, receipt_bytes = (
        q.f.store.read("run").records, q.service.store.path.read_bytes(), path.read_bytes())
    q.f.ticks[0] = LATER
    assert q.service.start_next() is False
    assert q.f.store.read("run").records == journal and q.driver.active is None
    assert q.service.store.path.read_bytes() == queue_bytes and path.read_bytes() == receipt_bytes
    row, = q.service.read()["entries"]
    assert (row["state"], row["reason_code"]) == ("blocked", "receipt_conflict")


def test_an_orphan_receipt_is_replaced_on_retry_and_a_paired_receipt_never_is(q):
    put(q, "run")
    path = q.service.store.receipt_path("run", "run_authorization", "grant-1")
    junk = Receipt("run", "run_authorization", "grant-1", "vasily", NOW, "sha256:" + "e" * 64,
                   "sha256:" + "f" * 64, NOW, "confirmation")
    q.service.store.write_receipt(junk)                    # a receipt with no journal record
    q.f.ticks[0] = LATER
    assert q.service.start_next() is True
    mended = q.service.store.read_receipt("run", "run_authorization", "grant-1")
    assert mended != junk and mended.started_at == LATER
    assert mended.record_digest == grants(q)[0].authorization_digest
    paired_bytes = path.read_bytes()
    q.service.store.write((QueueEntry("run", "start", NOW, "vasily", StartPreauth(
        "grant-1", mended.digest, "sha256:" + "b" * 64, ask(), None, "vasily", NOW), None),))
    q.driver.active = None
    for _ in range(3):
        q.service.start_next()
    assert path.read_bytes() == paired_bytes and len(grants(q)) == 1
    with pytest.raises(ReceiptExists):
        q.service.store.write_receipt(mended)


# --- a fault at every write boundary --------------------------------------------------------------


class Crash(BaseException):
    """The process dies here: nothing after this line of the pump runs."""


BOUNDARIES = ("after_receipt", "after_append", "after_activate", "after_removal")


def arm(q, boundary, failure):
    """Make the pump fail right AFTER the named write; returns what `disarm` puts back."""
    saved = []

    def after(owner, name, only=lambda *args: True):
        original = getattr(owner, name)
        saved.append((owner, name, original, name in vars(owner)))

        def wrapped(*args, **kwargs):
            value = original(*args, **kwargs)
            if only(*args):
                raise failure("the write boundary")
            return value
        setattr(owner, name, wrapped)
    if boundary == "after_receipt":
        after(q.service.store, "write_receipt")
        after(q.service.store, "replace_receipt")
    elif boundary == "after_append":
        after(q.f.policy.store, "append",
              lambda value: type(value) in (RunAuthorization, RunAuthorizationControl))
    elif boundary == "after_activate":
        after(q.f.policy.driver, "activate")
    else:
        after(q.f.policy, "notify")                        # the frame that follows the removal
    return saved


def disarm(saved):
    for owner, name, original, was_instance in saved:
        if was_instance:
            setattr(owner, name, original)
        else:
            vars(owner).pop(name, None)


def named(q, kind):
    if kind == "start":
        return [row.authorization_id for row in grants(q)]
    return [row.control_id for row in controls(q) if row.control_id == "resume-1"]


def arrange(q, kind):
    if kind == "start":
        put(q, "run")
    else:
        put_resume(q, paused_grant(q, "run"))


@pytest.mark.parametrize("kind", ["start", "resume"])
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_a_fault_at_every_write_boundary_reconciles_idempotently_and_restores_no_preauthorization(
        q, kind, boundary):
    """A StoreError in the same process: the next passes write at most one record, and once."""
    arrange(q, kind)
    saved = arm(q, boundary, StoreError)
    assert q.service.start_next() in (True, False)   # the StoreError ends or follows it
    disarm(saved)
    if boundary == "after_receipt":
        assert named(q, kind) == []                        # nothing but the receipt was written
    q.service.start_next()
    q.service.start_next()
    assert len(named(q, kind)) == 1, "the run was started twice or never"
    assert q.service.store.read().entries == ()
    assert q.driver.active is not None or boundary == "after_append"


@pytest.mark.parametrize("kind", ["start", "resume"])
@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_a_process_that_dies_at_a_write_boundary_leaves_a_state_the_next_one_reconciles(
        q, kind, boundary):
    arrange(q, kind)
    saved = arm(q, boundary, Crash)
    with pytest.raises(Crash):
        q.service.start_next()
    disarm(saved)
    written = named(q, kind)
    restart(q)
    assert q.service.admitted == set(), "a restart restores no preauthorization"
    for _ in range(3):
        assert q.service.start_next() is False
    assert named(q, kind) == written and len(written) <= 1
    assert q.driver.active is None, "a new process activates nothing it did not write"
    if written:                          # recorded and never activated: a human resumes
        view = automation_view(q.f.policy, "run")
        assert (view["state"], view["reason_code"]) == (
            "restart_required", "explicit_resume_required")
        assert queued(q) == []
    else:                                # only a receipt: the human confirms again
        row, = q.service.read()["entries"]
        assert (row["state"], row["reason_code"]) == (
            "confirmation_required", "server_restarted")


def test_a_crash_between_the_grant_append_and_the_entry_removal_never_starts_the_run_twice(q):
    put(q, "run")
    original = q.service.store.write

    def failing(entries):
        raise StoreError("the owner went away")
    q.service.store.write = failing
    assert q.service.start_next() is True                  # the start stood: it is in the journal
    q.service.store.write = original
    assert queued(q) == ["run"] and len(grants(q)) == 1
    q.driver.active = None
    assert q.service.start_next() is False                 # the pair is recognised, not repeated
    assert queued(q) == [] and len(grants(q)) == 1 and controls(q) == []


# --- the real driver ------------------------------------------------------------------------------


def wait_until(check, seconds=10):
    for _ in range(int(seconds / 0.02)):
        if check():
            return True
        time.sleep(.02)
    return False


def terminal(f, run_id):
    return any(row.kind == "run_terminal" for row in f.store.read(run_id).records)


def test_complete_deactivation_publishes_a_run_frame(tmp_path):
    f = project(tmp_path)
    driver, execution = attach_driver(f)
    frames = []
    f.policy.notify = lambda run_id: frames.append((run_id, driver.slot().active_run_id))
    try:
        authorize(f)
        assert wait_until(lambda: terminal(f, "run"))
        assert wait_until(lambda: frames and frames[-1] == ("run", None))
        assert frames[0] == ("run", "run")
    finally:
        driver.stop()
        execution.shutdown()


def test_a_run_that_completes_frees_the_slot_for_the_next_entry_through_the_real_driver(
        tmp_path):
    f = project(tmp_path, "run-b")
    service = QueueService(f.policy, TaskStore(tmp_path), mode="active")
    f.policy.queue = service
    driver, execution = attach_driver(f)
    try:
        for run_id in ("run", "run-b"):
            body = start_body(f, run_id, f"grant-{run_id}")
            service.enqueue(parse_write({"run_id": run_id, "start": body}, f.policy.clock()))
        driver.wake_queue()
        assert wait_until(lambda: terminal(f, "run") and terminal(f, "run-b"), 20)
        first = [row.value for row in f.store.read("run").records if row.kind == "run_terminal"]
        assert first and [row.authorization_id for row in
                          (r.value for r in f.store.read("run-b").records
                           if r.kind == "run_authorization")] == ["grant-run-b"]
        assert service.store.read().entries == ()
        # The terminal record is written by the execution; the driver frees the slot on its
        # next tick, when it reads the plan as complete. So the slot is waited for.
        assert wait_until(lambda: driver.slot().active_run_id is None)
    finally:
        driver.stop()
        execution.shutdown()
