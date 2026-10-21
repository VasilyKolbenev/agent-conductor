"""A plan that has ended reads `complete` with `plan_ended`, whatever holds its grant (spec 4.4.1).

A plan ends on one of two words, and a run that has recorded its ending takes no pause, resume,
revoke or new grant. The read asked the plan only whether it was `complete`, so a plan that ended
`stalled` read whatever the driver, the owner, the controls or the clock said: `stalled` while the
driver held it (the Studio offered a resume and a revoke), `restart_required` with
`explicit_resume_required` once it did not (the desk asked for a continuation, the hub offered
one, the flag listed the run), `paused` (a resume), `expired` (a form for a new grant). Each was a
promise the doors refuse. An ended plan is now judged right after the grant and before all of
them, as a completed one always was. A run nothing was granted to still reads `unconfigured`: the
Studio's model holds that word to a read with no grant.

The plan's word is the one fact the test sets: `schedule` is replaced by one that answers it. The
journal of a run that really ended `stalled` is driven in `tests/test_policy_driver_stalled.py`.
"""
from __future__ import annotations

import pytest

from conductor.command import policy_view
from tests.test_policy_runtime import approve, pause, setup
from tests.test_policy_view_expired import AFTER, revoke
from tests.test_policy_view_reasons import Holding, Idle, no_owner


class Word:
    """What `schedule` says of a plan, cut to what the read asks of it."""

    def __init__(self, run_state):
        self.run_state, self.runnable = run_state, ()


def read(f, monkeypatch, word):
    monkeypatch.setattr(policy_view, "schedule", lambda definition, values: Word(word))
    view = policy_view.automation_view(f.policy, "run")
    return view["state"], view["reason_code"]


def holding_a_stall(f, grant):
    f.policy.driver = Holding("stalled")


def holding_ready(f, grant):
    f.policy.driver = Holding("ready")


def holding_nothing(f, grant):
    f.policy.driver = Idle()


def viewing(f, grant):
    f.policy.driver = None


def ownerless(f, grant):
    f.policy.owner_check = no_owner


def paused(f, grant):
    pause(f, grant)


def revoked(f, grant):
    revoke(f, grant)


def expired(f, grant):
    f.ticks[0] = AFTER


SITUATIONS = [holding_a_stall, holding_ready, holding_nothing, viewing, ownerless, paused,
              revoked, expired]


@pytest.mark.parametrize("situation", SITUATIONS, ids=lambda one: one.__name__)
@pytest.mark.parametrize("word", ["stalled", "complete"])
def test_an_ended_plan_reads_complete_plan_ended_whatever_holds_its_grant(
        tmp_path, monkeypatch, word, situation):
    f = setup(tmp_path)
    grant, _ = approve(f)
    situation(f, grant)
    assert read(f, monkeypatch, word) == ("complete", "plan_ended")


@pytest.mark.parametrize("situation, expected", [
    (holding_a_stall, ("stalled", "stalled")),
    (holding_nothing, ("restart_required", "explicit_resume_required")),
    (paused, ("paused", "paused"))], ids=["holding_a_stall", "holding_nothing", "paused"])
def test_an_open_plan_still_reads_what_holds_its_grant(tmp_path, monkeypatch, situation,
                                                        expected):
    """The calibration: the word the test sets is the word the read follows."""
    f = setup(tmp_path)
    grant, _ = approve(f)
    situation(f, grant)
    assert read(f, monkeypatch, "open") == expected


@pytest.mark.parametrize("word", ["stalled", "complete"])
def test_an_ended_plan_nothing_was_granted_to_still_reads_unconfigured(tmp_path, monkeypatch,
                                                                       word):
    f = setup(tmp_path)
    assert read(f, monkeypatch, word) == ("unconfigured", "authorization_required")
