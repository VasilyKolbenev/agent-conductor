"""A grant whose time has passed reads `expired`, whether or not it was paused (spec 4.4.1, 5.8).

The automation read used to judge the last control before the clock, so a paused grant that then
expired still read `paused`: the desk offered a resume that the server could only refuse, and
every other reader called a grant that can no longer be resumed "paused". The clock is now judged
before a pause. A revoke stays `revoked`: it is the human's own final word and says more than the
time does. The slot keeps its own row for a paused holder whose action is still in flight: the
action will end by itself, so that slot is busy, never stuck.
"""
from __future__ import annotations

from types import SimpleNamespace

from conductor.command.policy_view import automation_view
from conductor.command.queue_reading import slot_reading
from tests.test_policy_runtime import approve, pause, setup

AFTER = "2026-08-11T13:00:00Z"


def read(f):
    view = automation_view(f.policy, "run")
    return view["state"], view["reason_code"]


def revoke(f, grant):
    f.policy.control("run", {"control_id": "revoke", "authorization_id": grant.authorization_id,
        "authorization_digest": grant.authorization_digest, "action": "revoke", "actor": "owner",
        "expected_control_id": None})


def test_a_paused_grant_whose_time_has_passed_reads_expired(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    pause(f, grant)
    f.ticks[0] = AFTER
    assert read(f) == ("expired", "expired")


def test_a_paused_grant_inside_its_time_still_reads_paused(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    pause(f, grant)
    assert read(f) == ("paused", "paused")


def test_a_paused_and_expired_grant_reads_expired_with_no_driver_too(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    pause(f, grant)
    f.ticks[0] = AFTER
    f.policy.driver = None
    assert read(f) == ("expired", "expired")


def test_a_pause_written_after_the_time_passed_reads_expired(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    f.ticks[0] = AFTER
    pause(f, grant)
    assert read(f) == ("expired", "expired")


def test_a_revoked_grant_whose_time_has_passed_still_reads_revoked(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    revoke(f, grant)
    f.ticks[0] = AFTER
    assert read(f) == ("revoked", "revoked")


def test_a_grant_with_no_control_whose_time_has_passed_reads_expired(tmp_path):
    f = setup(tmp_path)
    approve(f)
    f.ticks[0] = AFTER
    assert read(f) == ("expired", "expired")


def holder_slot(f):
    """The slot of a process whose only holder is `run`, in flight, read the way the queue does."""
    snapshot = SimpleNamespace(active_run_id=None, inflight_run_id="run", holding_new_work=False)
    driver = SimpleNamespace(slot=lambda: snapshot)
    return slot_reading(driver, "active", lambda run_id: automation_view(f.policy, run_id))


def test_a_paused_holder_whose_action_is_in_flight_keeps_the_slot_busy_after_its_grant_expires(
        tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    pause(f, grant)
    assert holder_slot(f) == {"state": "busy", "run_id": "run", "reason_code": "paused"}
    f.ticks[0] = AFTER
    assert read(f) == ("expired", "expired")
    assert holder_slot(f) == {"state": "busy", "run_id": "run", "reason_code": "paused"}


def test_an_expired_holder_with_no_pause_is_stuck_until_a_human_acts(tmp_path):
    f = setup(tmp_path)
    approve(f)
    f.ticks[0] = AFTER
    assert holder_slot(f) == {"state": "stuck", "run_id": "run", "reason_code": "expired"}
