"""How the queue is read: the slot, what each entry stands on, and why it waits (spec 4.4.6).

The read is pure over facts the service gathers (the recovered run, the receipt, who holds the
slot), so every rule of 4.4.6 is a row here: the slot table with existing names only, the pairing
of a receipt with the journal (digest, person and both times), which entries are processed and
hidden, and the state of an entry in the order the spec gives. Runs are real (`queue_fixtures`);
the driver is a table of (state, reason) pairs, because that pair is all the read takes from it.
"""
from __future__ import annotations

import copy

import pytest

from conductor.command.authorization_history import journal_prefix_digest
from conductor.command.contract_values import _content_digest
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import DecisionReceipt, RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.policy_driver import SlotSnapshot
from conductor.command.queue_reading import (
    CORRUPT, SLOT_STATES, Facts, assemble, grant_standing, pairing, processed_reason,
    record_digest, run_ended, slot_reading, terms_changed)
from conductor.command.queue_store import (
    Dropped, QueueEntry, Receipt, ResumePreauth, StartPreauth)
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import snapshot_digest
from conductor.command.store_errors import StoreError
from tests.queue_fixtures import NOW, ask, project, resume_body, start_body
from tests.test_policy_runtime import pause

LATER = "2026-08-11T12:02:00Z"
AFTER = "2026-08-11T12:10:00Z"      # past a 300 s grant that began at NOW
PROCESS_STARTED = "2026-08-11T11:59:00Z"
DIGEST = "sha256:" + "c" * 64


# --- the slot -------------------------------------------------------------------------------------


class Driver:
    """What `slot_reading` asks of a driver: one snapshot."""

    def __init__(self, active=None, inflight=None, holding=False):
        self._snapshot = SlotSnapshot(active, inflight, holding)

    def slot(self):
        return self._snapshot


def view_of(state, reason):
    return lambda run_id: {"state": state, "reason_code": reason}


#: The pairs `automation_view` can give (policy_view.py and spec 4.4.1) and the row each lands on.
HOLDER_ROWS = [
    (("running", "action_in_flight"), ("busy", "action_in_flight")),
    (("ready", "ready"), ("busy", "ready")),
    (("waiting", "plan_waiting"), ("busy", "plan_waiting")),
    (("paused", "paused"), ("busy", "paused")),
    (("revoked", "revoked"), ("busy", "revoked")),
    (("complete", "plan_ended"), ("busy", "plan_ended")),
    (("stalled", "unknown_action"), ("stuck", "unknown_action")),
    (("stalled", "feedback_required"), ("stuck", "feedback_required")),
    (("stalled", "admission_refused"), ("stuck", "admission_refused")),
    (("stalled", "stalled"), ("stuck", "stalled")),
    (("stalled", "seed_blocked"), ("stuck", "seed_blocked")),
    (("stalled", "ambiguous_actions"), ("stuck", "ambiguous_actions")),
    (("stalled", "plan_stalled"), ("stuck", "plan_stalled")),
    (("expired", "expired"), ("stuck", "expired")),
    (("restart_required", "owner_required"), ("unavailable", "owner_required")),
    (("restart_required", "explicit_resume_required"), ("unavailable", "owner_required")),
]
#: Every reason a slot can carry: the reasons of `policy_view`, and the codes the spec introduced.
EXISTING_REASONS = {
    "action_in_flight", "ready", "plan_waiting", "paused", "revoked", "plan_ended",
    "unknown_action", "feedback_required", "admission_refused", "stalled", "seed_blocked",
    "ambiguous_actions", "plan_stalled", "expired", "owner_required", "project_not_active",
    "server_stopping", "run_unreadable"}


@pytest.mark.parametrize("held, expected", HOLDER_ROWS)
def test_a_holder_state_lands_on_the_row_of_the_table(held, expected):
    slot = slot_reading(Driver(active="run-a"), "active", view_of(*held))
    assert (slot["state"], slot["reason_code"], slot["run_id"]) == (*expected, "run-a")


def test_no_holder_is_a_free_slot_with_no_reason_and_no_run():
    assert slot_reading(Driver(), "active", view_of("ready", "ready")) == {
        "state": "free", "run_id": None, "reason_code": None}


@pytest.mark.parametrize("mode, reason", [("view", "project_not_active"),
                                          ("active", "owner_required")])
def test_a_process_with_no_driver_has_an_unavailable_slot_named_for_its_mode(mode, reason):
    assert slot_reading(None, mode, view_of("ready", "ready")) == {
        "state": "unavailable", "run_id": None, "reason_code": reason}


def test_a_drain_makes_the_slot_unavailable_before_anything_else_is_asked():
    asked = []

    def holder(run_id):
        asked.append(run_id)
        return {"state": "ready", "reason_code": "ready"}
    free = slot_reading(Driver(holding=True), "active", holder)
    held = slot_reading(Driver(active="run-a", holding=True), "active", holder)
    assert (free["state"], free["reason_code"], free["run_id"]) == (
        "unavailable", "server_stopping", None)
    assert (held["state"], held["reason_code"], held["run_id"]) == (
        "unavailable", "server_stopping", "run-a")
    assert asked == []


@pytest.mark.parametrize("driver, holder", [
    (Driver(active="run-a"), "run-a"), (Driver(inflight="run-a"), "run-a"),
    (Driver(active="run-a", inflight="run-a"), "run-a")])
def test_the_holder_is_the_run_the_driver_holds_by_activation_or_by_an_action(driver, holder):
    assert slot_reading(driver, "active", view_of("ready", "ready"))["run_id"] == holder


def test_a_holder_that_cannot_be_read_is_a_stuck_slot_not_a_free_one():
    def unreadable(run_id):
        raise StoreError("the run does not replay")
    slot = slot_reading(Driver(active="run-a"), "active", unreadable)
    assert (slot["state"], slot["reason_code"], slot["run_id"]) == (
        "stuck", "run_unreadable", "run-a")


def test_a_state_the_table_does_not_name_is_stuck_under_the_reason_the_holder_gave():
    slot = slot_reading(Driver(active="run-a"), "active", view_of("unconfigured", "no_reason_yet"))
    assert (slot["state"], slot["reason_code"]) == ("stuck", "no_reason_yet")


def test_every_row_of_the_table_uses_a_state_and_a_reason_that_already_exist():
    seen = set()
    for held, expected in HOLDER_ROWS:
        slot = slot_reading(Driver(active="run-a"), "active", view_of(*held))
        assert slot["state"] in SLOT_STATES and slot["reason_code"] in EXISTING_REASONS
        seen.add(slot["state"])
    assert seen == {"busy", "stuck", "unavailable"} and SLOT_STATES == (
        "free", "busy", "stuck", "unavailable")


# --- the pairing of a receipt with the journal ----------------------------------------------------


def granted(tmp_path, *, by="vasily"):
    """One run with a grant written by a human: the grant, its body and the matching entry."""
    f = project(tmp_path)
    body = start_body(f, "run", "grant-1", by=by)
    grant, _ = f.policy.authorize("run", body)
    preauth = StartPreauth("grant-1", body["preview_digest"], body["terms"]["source_prefix_digest"],
                           {key: body["terms"][key] for key in (
                               "node_limits", "max_actions", "max_action_seconds",
                               "max_total_task_seconds", "duration_seconds")},
                           None, by, NOW)
    entry = QueueEntry("run", "start", NOW, by, preauth, None)
    receipt = Receipt("run", "run_authorization", "grant-1", by, NOW, body["preview_digest"],
                      grant.authorization_digest, grant.authorized_at, "confirmation")
    return f, grant, entry, receipt


def journal_of(f):
    return f.store.read("run")


def test_a_key_with_nothing_on_it_is_none(tmp_path):
    f = project(tmp_path)
    entry = QueueEntry("run", "start", NOW, "vasily", StartPreauth(
        "grant-1", DIGEST, DIGEST, ask(), None, "vasily", NOW), None)
    assert pairing(entry.preauthorization, "run_authorization", None, None) == "none"


def test_a_receipt_with_no_journal_record_is_an_orphan(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    assert pairing(entry.preauthorization, "run_authorization", receipt, None) == "orphan"
    assert pairing(entry.preauthorization, "run_authorization", CORRUPT, None) == "orphan"


def test_a_journal_record_with_no_receipt_was_started_another_way(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    assert pairing(entry.preauthorization, "run_authorization", None, grant) == "elsewhere"


def test_a_receipt_and_a_journal_record_that_agree_are_a_pair(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    assert pairing(entry.preauthorization, "run_authorization", receipt, grant) == "paired"


@pytest.mark.parametrize("field, value", [
    ("digest", "sha256:" + "d" * 64),               # not what the human preauthorized
    ("authorized_by", "someone-else"),              # not the person of the preauthorization
    ("preauthorized_at", LATER),                    # not the time he confirmed
    ("record_digest", "sha256:" + "d" * 64),        # not the record the journal holds
    ("started_at", LATER),                          # not the time the record was written
])
def test_a_receipt_that_disagrees_with_the_entry_or_the_journal_is_a_conflict(
        tmp_path, field, value):
    f, grant, entry, receipt = granted(tmp_path)
    changed = Receipt(**{**receipt.__dict__, field: value})
    assert pairing(entry.preauthorization, "run_authorization", changed, grant) == "conflict"


@pytest.mark.parametrize("field, value", [("record_id", "grant-2"),
                                          ("kind", "run_authorization_control")])
def test_a_receipt_that_names_another_key_than_the_entry_is_a_conflict_though_all_else_agrees(
        tmp_path, field, value):
    f, grant, entry, receipt = granted(tmp_path)
    other = Receipt(**{**receipt.__dict__, field: value})
    assert pairing(entry.preauthorization, "run_authorization", other, grant) == "conflict"


def test_a_journal_record_written_by_another_person_than_the_receipt_says_is_a_conflict(
        tmp_path):
    f, grant, entry, receipt = granted(tmp_path, by="someone-else")
    claimed = Receipt(**{**receipt.__dict__, "authorized_by": "vasily"})
    body_entry = QueueEntry("run", "start", NOW, "vasily", StartPreauth(
        **{**entry.preauthorization.__dict__, "authorized_by": "vasily"}), None)
    assert pairing(body_entry.preauthorization, "run_authorization", claimed, grant) == "conflict"


def test_a_receipt_and_a_record_that_agree_on_another_person_than_the_one_who_confirmed_conflict(
        tmp_path):
    f, grant, entry, receipt = granted(tmp_path, by="someone-else")
    confirmed_by_another = StartPreauth(
        **{**entry.preauthorization.__dict__, "authorized_by": "vasily"})
    assert pairing(confirmed_by_another, "run_authorization", receipt, grant) == "conflict"


def test_a_receipt_nothing_can_read_beside_a_journal_record_is_a_conflict(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    assert pairing(entry.preauthorization, "run_authorization", CORRUPT, grant) == "conflict"


def test_a_control_pairs_by_the_digest_of_its_whole_record_and_the_grant_it_was_about(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    pause(f, grant)
    control, _ = f.policy.control("run", {**resume_body(grant, "resume-1", "pause"),
                                          "action": "resume"})
    assert record_digest(control) == _content_digest(control.as_dict())
    preauth = ResumePreauth("resume-1", "grant-1", grant.authorization_digest, "pause",
                            "vasily", NOW)
    receipt = Receipt("run", "run_authorization_control", "resume-1", "vasily", NOW,
                      grant.authorization_digest, record_digest(control), control.recorded_at,
                      "confirmation")
    assert pairing(preauth, "run_authorization_control", receipt, control) == "paired"
    wrong = Receipt(**{**receipt.__dict__, "digest": DIGEST})
    assert pairing(preauth, "run_authorization_control", wrong, control) == "conflict"


# --- ended, standing, processed, changed ----------------------------------------------------------


def gate_only_run(f, run_id):
    config = {"cycle": {"id": "cycle"}, "instances": [],
              "workflow": {"id": "custom", "revision": 1},
              "automation_contract": "bounded-run-v1"}
    f.store.create_run(RunEnvelope(run_id, "cycle", NOW, snapshot_digest(config),
                                   mode="policy"), config)
    f.store.append(GraphDefinition("graph", run_id, NOW, nodes=(
        GraphNode("gate", "gate", "Approve", gate_id="gate-id"),), edges=()))
    f.store.append(DecisionReceipt("decision", run_id, "gate-id", "approve", "owner", NOW,
                                   "Reviewed", ("gate-id",), snapshot_digest(config)))


def test_a_run_is_ended_by_a_recorded_terminal_or_by_a_plan_that_is_complete(tmp_path):
    f = project(tmp_path)
    gate_only_run(f, "done")
    assert run_ended(journal_of(f)) is False                       # the open run
    assert run_ended(f.store.read("done")) is True                 # complete, nothing recorded
    ids = iter(range(9))
    close_if_terminal(f.store, "done", clock=lambda: NOW, ids=lambda kind: f"{kind}-{next(ids)}")
    assert run_ended(f.store.read("done")) is True                 # complete and recorded


def test_a_grant_stands_until_it_is_revoked_or_its_time_is_over_and_a_pause_does_not_end_it(
        tmp_path):
    f = project(tmp_path)
    assert grant_standing(journal_of(f), NOW) is False             # no grant at all
    body = start_body(f, "run", "grant-1")
    grant, _ = f.policy.authorize("run", body)
    assert grant_standing(journal_of(f), NOW) is True
    assert grant_standing(journal_of(f), AFTER) is False           # expired: 300 s from NOW
    pause(f, grant)
    assert grant_standing(journal_of(f), NOW) is True
    f.policy.control("run", {**resume_body(grant, "revoke-1", "pause"), "action": "revoke"})
    assert grant_standing(journal_of(f), NOW) is False


def test_a_start_entry_is_processed_when_its_own_grant_is_paired_or_another_road_started_it(
        tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    recovered = journal_of(f)
    for kind, expected in (("paired", "started"), ("elsewhere", "started_elsewhere"),
                           ("conflict", None)):
        assert processed_reason(entry, recovered, NOW, pairing=kind, holds=False) == expected


def test_a_start_entry_is_processed_when_another_live_grant_holds_the_run(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    other = QueueEntry("run", "start", NOW, "vasily", StartPreauth(
        **{**entry.preauthorization.__dict__, "authorization_id": "grant-9"}), None)
    recovered = journal_of(f)
    assert processed_reason(other, recovered, NOW, pairing="none", holds=False) == (
        "started_elsewhere")
    assert processed_reason(other, recovered, AFTER, pairing="none", holds=False) is None


def test_a_start_entry_of_a_run_with_no_grant_is_not_processed(tmp_path):
    f = project(tmp_path)
    entry = QueueEntry("run", "start", NOW, "vasily", StartPreauth(
        "grant-1", DIGEST, DIGEST, ask(), None, "vasily", NOW), None)
    assert processed_reason(entry, journal_of(f), NOW, pairing="none", holds=False) is None


def test_an_entry_of_an_ended_run_is_processed_whatever_its_kind_or_pairing(tmp_path):
    f = project(tmp_path)
    gate_only_run(f, "done")
    entry = QueueEntry("done", "start", NOW, "vasily", StartPreauth(
        "grant-1", DIGEST, DIGEST, ask(), None, "vasily", NOW), None)
    for kind in ("none", "orphan", "conflict"):
        assert processed_reason(entry, f.store.read("done"), NOW, pairing=kind,
                                holds=False) == "ended"


def test_a_resume_entry_is_processed_by_its_own_control_a_revoke_or_a_driver_that_holds_it(
        tmp_path):
    f, grant, _, _ = granted(tmp_path)
    pause(f, grant)
    preauth = ResumePreauth("resume-1", "grant-1", grant.authorization_digest, "pause",
                            "vasily", NOW)
    entry = QueueEntry("run", "resume", NOW, "vasily", preauth, None)
    assert processed_reason(entry, journal_of(f), NOW, pairing="none", holds=False) is None
    assert processed_reason(entry, journal_of(f), NOW, pairing="none", holds=True) == "held"
    f.policy.control("run", {**resume_body(grant, "resume-1", "pause"), "action": "resume"})
    assert processed_reason(entry, journal_of(f), NOW, pairing="elsewhere",
                            holds=False) == "resumed"
    f.policy.control("run", {**resume_body(grant, "revoke-1", "resume-1"), "action": "revoke"})
    other = QueueEntry("run", "resume", NOW, "vasily", ResumePreauth(
        "resume-2", "grant-1", grant.authorization_digest, "resume-1", "vasily", NOW), None)
    assert processed_reason(other, journal_of(f), NOW, pairing="none", holds=False) == "revoked"


def test_terms_changed_is_a_journal_prefix_that_is_no_longer_the_one_the_human_reviewed(
        tmp_path):
    f = project(tmp_path)
    body = start_body(f, "run", "grant-1")
    preauth = StartPreauth("grant-1", body["preview_digest"],
                           body["terms"]["source_prefix_digest"], ask(), None, "vasily", NOW)
    entry = QueueEntry("run", "start", NOW, "vasily", preauth, None)
    assert journal_prefix_digest(journal_of(f).records) == preauth.source_prefix_digest
    assert terms_changed(entry, journal_of(f)) is False
    f.store.append(ArtifactDocument(artifact_id="instruction-2", run_id="run",
        artifact_ref="instructions", created_at=NOW, media_type="text/plain", content="Changed"))
    assert terms_changed(entry, journal_of(f)) is True


def test_a_resume_entry_and_a_dropped_entry_never_read_as_changed_terms(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    resume = QueueEntry("run", "resume", NOW, "vasily", ResumePreauth(
        "resume-1", "grant-1", grant.authorization_digest, None, "vasily", NOW), None)
    dropped = QueueEntry("run", "start", NOW, "vasily", None, Dropped("terms_changed", LATER))
    assert terms_changed(resume, journal_of(f)) is False
    assert terms_changed(dropped, journal_of(f)) is False


# --- the read -------------------------------------------------------------------------------------

FREE = {"state": "free", "run_id": None, "reason_code": None}
BUSY = {"state": "busy", "run_id": "other", "reason_code": "ready"}
STUCK = {"state": "stuck", "run_id": "other", "reason_code": "expired"}
GONE = {"state": "unavailable", "run_id": None, "reason_code": "owner_required"}


def start_entry(run_id="run", *, source=None, at=NOW, by="vasily", authorization_id="grant-1"):
    preauth = StartPreauth(authorization_id, DIGEST, source or DIGEST, ask(), None, by, at)
    return QueueEntry(run_id, "start", NOW, by, preauth, None)


def facts_for(f, entry, **changes):
    values = {"entry": entry, "recovered": f.store.read(entry.run_id), "receipt": None,
              "admitted": True, "holds": False, "task_id": None, "title": None}
    return Facts(**{**values, **changes})


def rows(f, facts, *, slot=FREE, mode="active", now=NOW):
    payload = assemble(7, facts, slot=slot, mode=mode, now=now, process_started=PROCESS_STARTED)
    return payload["entries"]


def source_of(f, run_id="run"):
    return journal_prefix_digest(f.store.read(run_id).records)


def test_the_payload_has_the_keys_of_the_spec_and_the_revision_and_the_slot_it_was_given(
        tmp_path):
    f = project(tmp_path)
    facts = [facts_for(f, start_entry(source=source_of(f)), title="Fix it", task_id="task-1")]
    payload = assemble(7, facts, slot=BUSY, mode="active", now=NOW,
                       process_started=PROCESS_STARTED)
    assert list(payload) == ["schema_version", "revision", "slot", "entries"]
    assert payload["schema_version"] == 1 and payload["revision"] == 7
    assert payload["slot"] == BUSY
    assert list(payload["entries"][0]) == [
        "run_id", "task_id", "title", "position", "kind", "enqueued_at", "enqueued_by", "state",
        "reason_code", "state_since", "preauthorization"]
    first = payload["entries"][0]
    assert (first["title"], first["task_id"]) == ("Fix it", "task-1")


def test_a_preauthorized_entry_shows_who_confirmed_when_and_what(tmp_path):
    f = project(tmp_path)
    row, = rows(f, [facts_for(f, start_entry(source=source_of(f)))])
    assert row["preauthorization"] == {"authorized_by": "vasily", "preauthorized_at": NOW,
                                       "digest": DIGEST}
    assert (row["state"], row["reason_code"], row["state_since"]) == ("preauthorized", None, NOW)


def test_a_run_that_cannot_be_read_is_blocked_run_unreadable_even_with_no_preauthorization(
        tmp_path):
    f = project(tmp_path)
    dropped = QueueEntry("run", "start", NOW, "vasily", None, Dropped("terms_changed", LATER))
    for entry in (start_entry(), dropped):
        row, = rows(f, [Facts(entry, None, None, True, False, None, None)])
        assert (row["state"], row["reason_code"], row["state_since"]) == (
            "blocked", "run_unreadable", None)


def test_a_receipt_that_disagrees_blocks_the_entry_before_any_other_rule_is_asked(tmp_path):
    f, grant, entry, receipt = granted(tmp_path)
    wrong = Receipt(**{**receipt.__dict__, "digest": DIGEST})
    row, = rows(f, [facts_for(f, entry, receipt=wrong, admitted=False)], mode="view")
    assert (row["state"], row["reason_code"], row["state_since"]) == (
        "blocked", "receipt_conflict", None)


def test_an_entry_without_a_preauthorization_needs_confirmation_for_the_reason_it_lost_it(
        tmp_path):
    f = project(tmp_path)
    dropped = QueueEntry("run", "start", NOW, "vasily", None, Dropped("grant_expired", LATER))
    row, = rows(f, [facts_for(f, dropped)], mode="view")
    assert (row["state"], row["reason_code"], row["state_since"]) == (
        "confirmation_required", "grant_expired", LATER)
    assert row["preauthorization"] is None


def test_terms_that_changed_are_seen_at_once_with_no_time_and_before_the_mode_is_asked(tmp_path):
    f = project(tmp_path)
    stale = start_entry(source="sha256:" + "e" * 64)
    for mode in ("view", "active"):
        row, = rows(f, [facts_for(f, stale)], mode=mode)
        assert (row["state"], row["reason_code"], row["state_since"]) == (
            "confirmation_required", "terms_changed", None)


def test_in_a_process_opened_for_viewing_a_preauthorized_entry_reads_project_not_active(tmp_path):
    f = project(tmp_path)
    row, = rows(f, [facts_for(f, start_entry(source=source_of(f)), admitted=False)],
                slot={**GONE, "reason_code": "project_not_active"}, mode="view")
    assert (row["state"], row["reason_code"], row["state_since"]) == (
        "preauthorized", "project_not_active", NOW)


def test_an_entry_that_was_not_admitted_since_the_restart_waits_for_confirmation_from_the_start(
        tmp_path):
    f = project(tmp_path)
    row, = rows(f, [facts_for(f, start_entry(source=source_of(f)), admitted=False)])
    assert (row["state"], row["reason_code"], row["state_since"]) == (
        "confirmation_required", "server_restarted", PROCESS_STARTED)


@pytest.mark.parametrize("slot, reason", [(FREE, None), (BUSY, "slot_busy"), (STUCK, "slot_busy"),
                                          (GONE, "slot_unavailable")])
def test_the_head_of_the_queue_says_why_it_has_not_started_from_the_slot(tmp_path, slot, reason):
    f = project(tmp_path)
    row, = rows(f, [facts_for(f, start_entry(source=source_of(f)))], slot=slot)
    assert (row["state"], row["reason_code"]) == ("preauthorized", reason)


def test_an_entry_behind_another_preauthorized_one_says_behind_and_an_unconfirmed_one_holds_nobody(
        tmp_path):
    f = project(tmp_path, "run-b", "run-c")
    first = facts_for(f, start_entry("run", source=source_of(f, "run")))
    waiting = facts_for(f, start_entry("run-b", source=source_of(f, "run-b")), admitted=False)
    third = facts_for(f, start_entry("run-c", source=source_of(f, "run-c")))
    got = rows(f, [waiting, first, third], slot=BUSY)
    assert [(row["run_id"], row["position"], row["state"], row["reason_code"]) for row in got] == [
        ("run-b", 1, "confirmation_required", "server_restarted"),
        ("run", 2, "preauthorized", "slot_busy"),
        ("run-c", 3, "preauthorized", "behind")]


def test_a_processed_entry_is_not_shown_and_the_positions_count_the_visible_ones(tmp_path):
    f, grant, started, receipt = granted(tmp_path)
    add = project(tmp_path / "second", "run-b")
    other = facts_for(add, start_entry("run-b", source=source_of(add, "run-b")))
    hidden = facts_for(f, started, receipt=receipt)
    got = rows(f, [hidden, other], slot=FREE)
    assert [(row["run_id"], row["position"]) for row in got] == [("run-b", 1)]


def test_the_title_and_the_task_are_null_for_a_run_with_no_task(tmp_path):
    f = project(tmp_path)
    row, = rows(f, [facts_for(f, start_entry(source=source_of(f)))])
    assert row["task_id"] is None and row["title"] is None


def test_the_read_does_not_change_the_facts_it_was_given(tmp_path):
    f = project(tmp_path)
    facts = [facts_for(f, start_entry(source=source_of(f)))]
    before = copy.deepcopy(facts[0].entry.as_dict())
    rows(f, facts)
    assert facts[0].entry.as_dict() == before
