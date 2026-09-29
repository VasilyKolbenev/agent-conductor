"""Seatbelt through the ONE runner: ownership loan, timeout, tree stop, refusal.

Nothing in the runner changes. ``sandbox-exec -p <profile> <command>`` applies the profile
and then execs the command, so the child keeps its pid and session and the runner's own
group stop (``killpg`` on the session it started) reaches it and everything it started.
The ownership scope is the production ``ProcessOwnership`` value with a real inheritable
descriptor and a recorded ``retire``. The refusal differs from Windows: there is no moment
to check a token before the child runs, so "policy applied" is a witness the sandboxed
shell prints first, and a profile that never applied is judged from the outcome.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

from tests import os_boundary_darwin as sb
from tests.os_boundary_seatbelt_box import seatbelt_runner  # noqa: F401

darwin_only = pytest.mark.skipif(
    sys.platform != "darwin", reason="needs macOS: Seatbelt (sandbox-exec) is a macOS mechanism")
posix_only = pytest.mark.skipif(
    os.name == "nt", reason="needs a POSIX runner: pass_fds and process groups are POSIX")

_PROMPTLY = 30.0
_WITH_GRANDCHILD = (
    'sleep 45 & echo $! > "@TMPD@/gc.pid.tmp"; mv "@TMPD@/gc.pid.tmp" "@TMPD@/gc.pid"; sleep 60'
)


@darwin_only
def test_a_sandboxed_child_run_by_the_runner_completes_and_the_loan_is_retired(seatbelt_runner):
    rb = seatbelt_runner
    outcome = rb.runner.run(rb.spec('printf x > "@TMPD@/ran"; echo child-output'))
    assert outcome.status == "completed" and outcome.exit_code == 0, outcome
    sb.require_applied(outcome.output.decode("utf-8", errors="replace"))
    assert b"child-output" in outcome.output
    assert (rb.layout.tmp / "ran").read_bytes() == b"x"
    assert rb.runner.active_tokens() == ()
    assert rb.scope.claims == 1 and rb.scope.borrows >= 1 and rb.scope.retired == [True]


@darwin_only
def test_a_sandboxed_child_that_outlives_its_timeout_dies_with_the_process_it_started(
        seatbelt_runner):
    rb = seatbelt_runner
    started = time.monotonic()
    outcome, grandchild = rb.run_until_pid_file(_WITH_GRANDCHILD, timeout=12.0)
    assert time.monotonic() - started < _PROMPTLY, "the runner waited out an orphan"
    assert outcome.status == "timed_out", outcome
    assert rb.runner.active_tokens() == () and rb.scope.retired == [True]
    assert grandchild.is_gone(), "the grandchild outlived the process group"


@darwin_only
def test_a_sandboxed_child_started_and_stopped_by_token_leaves_no_live_process(
        seatbelt_runner):
    rb = seatbelt_runner
    owned = rb.runner.start(rb.spec(_WITH_GRANDCHILD))
    leader = rb.watch(owned.pid)
    grandchild = rb.wait_for_pid_file()
    assert not grandchild.is_gone(), "the grandchild never started"
    started = time.monotonic()
    outcome = rb.runner.stop(owned.token)
    assert time.monotonic() - started < _PROMPTLY, "stop waited out an orphan"
    assert outcome.status == "stopped"
    assert rb.runner.active_tokens() == () and rb.scope.retired == [True]
    assert grandchild.is_gone() and leader.is_gone()


@darwin_only
def test_a_profile_that_cannot_be_applied_is_judged_not_applied_and_leaves_nothing_behind(
        seatbelt_runner):
    rb = seatbelt_runner
    marker = rb.layout.tmp / "ran"
    outcome = rb.runner.run(rb.spec(f'touch "{marker}"',
                                    profile="(version 1)\n(allow default)\n(bogus-rule)\n"))
    assert outcome.status == "completed" and outcome.exit_code != 0, outcome
    with pytest.raises(sb.PolicyNotApplied):
        sb.require_applied(outcome.output.decode("utf-8", errors="replace"))
    assert not marker.exists(), "the target ran although the profile was never applied"
    assert rb.runner.active_tokens() == () and rb.scope.retired == [True]


@posix_only
def test_a_missing_sandbox_wrapper_is_refused_by_the_runner_with_no_token_and_an_unproven_loan(
        seatbelt_runner):
    rb = seatbelt_runner
    with pytest.raises(FileNotFoundError):
        rb.runner.run(rb.spec("true", executable="/nonexistent/sandbox-exec"))
    assert rb.runner.active_tokens() == ()
    assert rb.scope.retired == [False], "an unproven loan must be retired unproven"
