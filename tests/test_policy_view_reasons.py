"""The two reasons spec 4.4.1 adds to the automation read, and only reasons: no new state.

`project_not_active` is the reason of `restart_required` in a process opened for viewing: an owner
is held and no driver exists, so nothing will ever continue the run there. It replaces
`explicit_resume_required`, which promises that a resume would. `seed_blocked` is a reason of
`stalled` (spec 9.1.4): the driver names it when the seed of a run is what blocks it.
"""
from __future__ import annotations

import pytest

from conductor.command.policy_view import automation_view
from tests.test_policy_runtime import approve, pause, setup


class Holding:
    """A driver that holds the granted run and says what it last decided."""

    def __init__(self, reason="ready"):
        self._reason = reason

    def is_active(self, run_id, grant_id):
        return True

    def reason(self, run_id):
        return self._reason


class Idle:
    """A driver that holds nothing: after a restart, before a resume."""

    def is_active(self, run_id, grant_id):
        return False


def read(f):
    view = automation_view(f.policy, "run")
    return view["state"], view["reason_code"]


def no_owner():
    raise RuntimeError("no live owner")


def test_a_process_with_an_owner_and_no_driver_reads_restart_required_project_not_active(tmp_path):
    f = setup(tmp_path)
    approve(f)
    f.policy.driver = None
    assert read(f) == ("restart_required", "project_not_active")


def test_a_process_with_no_owner_still_reads_owner_required_whatever_its_driver(tmp_path):
    f = setup(tmp_path)
    approve(f)
    f.policy.owner_check = no_owner
    for driver in (None, Idle(), Holding()):
        f.policy.driver = driver
        assert read(f) == ("restart_required", "owner_required"), driver


def test_a_driver_that_does_not_hold_the_run_still_reads_explicit_resume_required(tmp_path):
    f = setup(tmp_path)
    approve(f)
    f.policy.driver = Idle()
    assert read(f) == ("restart_required", "explicit_resume_required")


def test_a_paused_run_reads_paused_even_with_no_driver(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    pause(f, grant)
    f.policy.driver = None
    assert read(f) == ("paused", "paused")


def test_a_run_nothing_granted_reads_unconfigured_with_no_driver(tmp_path):
    f = setup(tmp_path)
    f.policy.driver = None
    assert read(f) == ("unconfigured", "authorization_required")


@pytest.mark.parametrize("reason", ["seed_blocked", "admission_refused", "feedback_required",
                                    "unknown_action", "stalled"])
def test_a_reason_the_driver_names_as_a_stall_reads_stalled_with_that_reason(tmp_path, reason):
    f = setup(tmp_path)
    approve(f)
    f.policy.driver = Holding(reason)
    assert read(f) == ("stalled", reason)


def test_a_reason_that_is_not_a_stall_reads_ready(tmp_path):
    f = setup(tmp_path)
    approve(f)
    f.policy.driver = Holding("ready")
    assert read(f) == ("ready", "ready")
