"""What a project's child is, in the words of 4.6.4, and what the hub does about it (4.1.5, 4.1.7).

`derive` is the table of 4.1.5 and the state rows of 4.1.10 as a pure function of a status
record, the liveness of the process it names and what the hub itself knows (a child it started
that has not yet reported, a head that was left `opened`). `restart_action` is the restart table
of 4.1.7, row by row, including the cases the table leaves to its text or does not mention, each
named here so that a change to any of them is a decision. `working_of` is the order of 4.1.10.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from conductor import up_flags, up_status
from conductor.hub import lifecycle

NOW = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
ID = "a" * 32


def record(state: str = "serving", *, code: str | None = None, mode: str = "active",
           started: str | None = "windows:1") -> up_status.StatusRecord:
    return up_status.StatusRecord(ID, 4812, started, 7701, mode, state, code, None, NOW)


# -- the table of 4.1.5 -------------------------------------------------------------------------

REFUSED = {
    "hub_flags_incomplete": ("failed", "hub_flags_incomplete"),
    "project_id_invalid": ("failed", "project_id_invalid"),
    "hub_origin_invalid": ("failed", "hub_origin_invalid"),
    "status_file_invalid": ("failed", "status_file_invalid"),
    "stdin_is_terminal": ("failed", "stdin_is_terminal"),
    "mode_invalid": ("failed", "mode_invalid"),
    "project_identity_changed": ("identity_mismatch", None),
    "hub_in_kill_on_close_job": ("failed", "hub_in_kill_on_close_job"),
    "owner_busy": ("busy_elsewhere", None),
    "recovery_required": ("recovery_required", None),
    "ownership_lost": ("missing", None),
    "transition_conflict": ("failed", "transition_conflict"),
    "ownership_unavailable": ("failed", "ownership_unavailable"),
    "store_error": ("failed", "store_error"),
    "providers_invalid": ("failed", "providers_invalid"),
    "bind_failed": ("failed", "bind_failed"),
    "start_failed": ("failed", "start_failed"),
}


def test_the_table_names_every_code_a_child_can_refuse_with_and_no_other():
    assert set(REFUSED) == set(up_flags.START_CODES)


@pytest.mark.parametrize("code", sorted(REFUSED))
def test_a_refused_child_reads_as_the_state_and_code_of_its_row(code):
    found = lifecycle.derive(record("refused", code=code), "dead")
    assert (found.state, found.state_code) == REFUSED[code]


def test_an_owner_busy_refusal_while_our_own_earlier_child_lives_is_stopping_not_elsewhere():
    found = lifecycle.derive(record("refused", code="owner_busy"), "dead", prior_alive=True)
    assert (found.state, found.state_code) == ("stopping", None)


def test_every_state_and_code_is_one_of_the_closed_lists_of_the_spec():
    states = {lifecycle.derive(record(state, code="start_failed" if state == "refused" else None),
                               liveness).state
              for state in up_status.STATES for liveness in ("alive", "dead", "unproven")}
    assert states <= set(lifecycle.STATES)
    # The spec's list (4.1.5) and the one code the tech lead added on 30.09: a status file that is
    # not the record blocks a new active child and is said on the rows it concerns.
    assert lifecycle.STATE_CODES == set(up_flags.START_CODES) | {
        "start_timeout", "active_not_closed", "status_unreadable"}


def test_a_status_file_that_is_not_the_record_puts_its_code_on_a_row_and_fails_no_start():
    found = lifecycle.derive(None, "dead", hub_code="status_unreadable")
    assert (found.state, found.state_code) == ("stopped", "status_unreadable")
    pending = lifecycle.derive(None, "dead", pending="alive", hub_code="status_unreadable")
    assert (pending.state, pending.state_code) == ("starting", "status_unreadable")
    assert "status_unreadable" not in {
        lifecycle.derive(record("refused", code=code), "dead").state_code
        for code in up_flags.START_CODES}


# -- a live or dead process under each state of the file ---------------------------------------


@pytest.mark.parametrize(("state", "liveness", "expected"), [
    ("starting", "alive", "starting"), ("serving", "alive", "running"),
    ("stopping", "alive", "stopping"), ("stop_overdue", "alive", "stop_overdue"),
    ("stop_uncertain", "alive", "stop_uncertain"), ("stopped", "alive", "stopped"),
    ("serving", "unproven", "running"), ("stopping", "unproven", "stopping"),
    ("stop_uncertain", "dead", "stop_uncertain"), ("stopped", "dead", "stopped")])
def test_a_status_under_a_process_that_is_not_known_dead_reads_as_its_own_state(
        state, liveness, expected):
    assert lifecycle.derive(record(state), liveness).state == expected


@pytest.mark.parametrize("state", ["serving", "stopping", "stop_overdue"])
def test_a_child_that_died_in_its_work_reads_recovery_required_when_its_head_was_left_opened(
        state):
    assert lifecycle.derive(record(state), "dead", head_phase="opened").state == (
        "recovery_required")
    assert lifecycle.derive(record(state), "dead", head_phase="closed").state == "stopped"
    assert lifecycle.derive(record(state), "dead").state == "stopped"


def test_a_child_that_died_while_starting_is_a_start_that_failed():
    found = lifecycle.derive(record("starting"), "dead")
    assert (found.state, found.state_code) == ("failed", "start_failed")


def test_no_status_file_is_stopped_and_one_the_hub_is_waiting_for_is_starting_or_failed():
    assert lifecycle.derive(None, "dead").state == "stopped"
    assert lifecycle.derive(None, "dead", pending="alive").state == "starting"
    failed = lifecycle.derive(None, "dead", pending="exited")
    assert (failed.state, failed.state_code) == ("failed", "start_failed")


def test_the_hubs_own_codes_ride_on_the_state_they_belong_to():
    timed_out = lifecycle.derive(record("starting"), "alive", hub_code="start_timeout")
    assert (timed_out.state, timed_out.state_code) == ("failed", "start_timeout")
    waiting = lifecycle.derive(record("stopped"), "dead", hub_code="active_not_closed")
    assert (waiting.state, waiting.state_code) == ("stopped", "active_not_closed")


def test_a_hub_code_outside_the_list_is_a_fault_of_the_caller():
    with pytest.raises(ValueError, match="hub_code"):
        lifecycle.derive(record(), "alive", hub_code="gone_wrong")


# -- the restart table of 4.1.7 -----------------------------------------------------------------


@pytest.mark.parametrize(("state", "liveness", "action"), [
    (None, "dead", "start"), ("stopped", "dead", "start"), ("refused", "dead", "start"),
    ("starting", "alive", "wait"), ("serving", "alive", "wait"),
    ("stopping", "alive", "wait"), ("stop_overdue", "alive", "wait"),
    ("serving", "dead", "start"), ("stopping", "dead", "start"),
    ("stop_overdue", "dead", "start"), ("stop_uncertain", "dead", "offer_recover")],
    ids=lambda value: str(value))
def test_the_rows_of_the_restart_table(state, liveness, action):
    found = None if state is None else record(state, code="start_failed" if state == "refused"
                                              else None)
    assert lifecycle.restart_action(found, liveness) == action


@pytest.mark.parametrize(("state", "liveness", "action", "why"), [
    ("starting", "dead", "start", "a start that died: the table has no row, it reads as serving"),
    ("stop_uncertain", "alive", "wait", "it is leaving after writing it"),
    ("stopped", "alive", "start", "the table says the process does not matter"),
    ("refused", "alive", "start", "likewise"),
    ("serving", "unproven", "wait", "a pid that cannot be told is taken as alive"),
    ("stop_uncertain", "unproven", "wait", "likewise")])
def test_the_cases_the_table_leaves_open_are_decided_and_named(state, liveness, action, why):
    found = record(state, code="start_failed" if state == "refused" else None)
    assert lifecycle.restart_action(found, liveness) == action, why


# -- the working state, in the order of 4.1.10 -------------------------------------------------


def test_the_working_state_is_active_then_view_then_queued_then_stopped():
    other = "b" * 32
    assert lifecycle.working_of(ID, active=ID, queue=(ID,), viewing=(ID,)) == "active"
    assert lifecycle.working_of(ID, active=other, queue=(ID,), viewing=(ID,)) == "view"
    assert lifecycle.working_of(ID, active=other, queue=(ID,), viewing=()) == "queued"
    assert lifecycle.working_of(ID, active=other, queue=(), viewing=()) == "stopped"
    assert lifecycle.working_of(ID, active=None, queue=(), viewing=()) == "stopped"


@pytest.mark.parametrize("state", ["serving", "stopping", "stop_overdue"])
def test_a_dead_child_whose_head_holds_only_a_prepared_restart_still_reads_recovery_required(
        state):
    found = lifecycle.derive(record(state), "dead", head_phase="recovery_prepared")
    assert found.state == "recovery_required"


# -- a recovery leaves only the ownership head behind (review ruling D-H1) ---------------------

SETTLED = ["active", "closed", "recovered", "rolled_back"]

#: Every word a head can read as that is NOT a finished phase. `None` is "no head was asked for".
UNFINISHED = [None, "opened", "recovery_prepared", "prepared", "moved", "rollback_prepared",
              "fence_retired", "unreadable", "a_phase_a_later_build_adds", ""]
#: The same without `None`: the pure table keeps `None` as the default of a working record.
ASKED = [word for word in UNFINISHED if word is not None]


@pytest.mark.parametrize("head", SETTLED)
def test_a_stop_uncertain_record_under_a_dead_process_reads_stopped_once_its_head_is_settled(head):
    found = lifecycle.derive(record("stop_uncertain"), "dead", head_phase=head)
    assert (found.state, found.state_code) == ("stopped", None)


@pytest.mark.parametrize("head", UNFINISHED)
def test_a_stop_uncertain_record_stays_while_its_head_is_open_unsettled_unknown_or_unread(head):
    found = lifecycle.derive(record("stop_uncertain"), "dead", head_phase=head)
    assert found.state == "stop_uncertain"


@pytest.mark.parametrize("state", ["serving", "stopping", "stop_overdue"])
@pytest.mark.parametrize("head", ASKED)
def test_a_dead_working_record_is_recovery_required_for_every_head_that_is_not_finished(
        state, head):
    assert lifecycle.derive(record(state), "dead", head_phase=head).state == "recovery_required"


@pytest.mark.parametrize("state", ["serving", "stopping", "stop_overdue"])
@pytest.mark.parametrize("head", SETTLED)
def test_a_dead_working_record_reads_stopped_for_a_finished_head(state, head):
    assert lifecycle.derive(record(state), "dead", head_phase=head).state == "stopped"


@pytest.mark.parametrize("head", UNFINISHED)
def test_a_refused_recovery_required_record_stays_for_every_head_that_is_not_finished(head):
    found = lifecycle.derive(record("refused", code="recovery_required"), "dead", head_phase=head)
    assert (found.state, found.state_code) == ("recovery_required", None)


@pytest.mark.parametrize("liveness", ["alive", "unproven"])
@pytest.mark.parametrize("head", SETTLED)
def test_a_record_under_a_process_that_may_live_never_reads_stopped_whatever_its_head(
        liveness, head):
    uncertain = lifecycle.derive(record("stop_uncertain"), liveness, head_phase=head)
    refused = lifecycle.derive(record("refused", code="recovery_required"), liveness,
                               head_phase=head)
    assert uncertain.state == "stop_uncertain" and refused.state == "recovery_required"


@pytest.mark.parametrize("head", SETTLED)
def test_a_refused_recovery_required_record_reads_stopped_once_its_head_is_settled(head):
    found = lifecycle.derive(record("refused", code="recovery_required"), "dead", head_phase=head)
    assert (found.state, found.state_code) == ("stopped", None)


@pytest.mark.parametrize("code", sorted(set(REFUSED) - {"recovery_required"}))
def test_no_other_refusal_is_cleared_by_a_settled_head(code):
    found = lifecycle.derive(record("refused", code=code), "dead", head_phase="recovered")
    assert (found.state, found.state_code) == REFUSED[code]


def test_the_settled_heads_are_exactly_the_phases_the_proven_closed_rule_accepts():
    from conductor.hub import state
    assert lifecycle.SETTLED_HEADS == state._NOT_OPENED


def test_the_restart_table_starts_a_stop_uncertain_project_only_when_its_head_is_settled():
    found = record("stop_uncertain")
    assert lifecycle.restart_action(found, "dead", head_phase="recovered") == "start"
    assert lifecycle.restart_action(found, "dead", head_phase="opened") == "offer_recover"
    assert lifecycle.restart_action(found, "dead", head_phase="recovery_prepared") == (
        "offer_recover")
    assert lifecycle.restart_action(found, "dead", head_phase=lifecycle.UNREADABLE) == (
        "offer_recover")
    assert lifecycle.restart_action(found, "dead") == "offer_recover"      # unchanged default
    assert lifecycle.restart_action(found, "alive", head_phase="recovered") == "wait"
    assert lifecycle.restart_action(found, "unproven", head_phase="recovered") == "wait"
