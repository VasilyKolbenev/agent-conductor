"""The AppContainer through the ONE runner: ownership loan, timeout, tree stop, refusal.

There is no second launcher. ``ProcessRunner._launch`` is replaced by the probe's
container launch, and ``_procgroup.make_group`` gets a check in front of it (the
child exists, is suspended, and has run nothing). Everything after that is the
runner's own code: the ownership scope it borrows and the loan it claims and retires,
the kill-on-close Job it assigns the child to, ``run``'s timeout, ``stop``, and the
fail-closed cleanup between launch and publication. A launch whose policy was not
applied must leave no token, no live process, no code run, and a loan retired unproven.
"""
from __future__ import annotations

import os
import time

import pytest

from tests.os_boundary_layout import render

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="needs Windows: AppContainer is a Windows mechanism")

if os.name == "nt":
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import container  # noqa: F401
    from tests.os_boundary_runner import runner_box  # noqa: F401

#: How long a stop or a timeout may take. A tree stop is milliseconds; an orphaned grandchild
#: sleeping 120 s that the runner had to wait out would exceed this and fail the test.
_PROMPTLY = 60.0
#: The runner's own timeout for the child that outlives it. It counts from the launch, so it
#: must outlast the start of a shell and of the shell that shell starts: 12 s was measured on a
#: desktop, and a slower host would kill the child before it had published anything.
_TIMEOUT = 30.0
_RAN = ("[IO.File]::WriteAllText('@TMPD@\\ran.txt','ran'); "
        "[Console]::Out.WriteLine('child-output')")
_WITH_GRANDCHILD = (
    "$i = [Diagnostics.ProcessStartInfo]::new(); $i.FileName = '@POWERSHELL@'; "
    "$i.Arguments = '-NoProfile -NonInteractive -Command [Threading.Thread]::Sleep(120000)'; "
    "$i.UseShellExecute = $false; $p = [Diagnostics.Process]::Start($i); "
    "[IO.File]::WriteAllText('@TMPD@\\gc.pid.tmp', [string]$p.Id); "
    "[IO.File]::Move('@TMPD@\\gc.pid.tmp','@TMPD@\\gc.pid'); [Threading.Thread]::Sleep(150000)"
)
_THROUGH_HANDLE = (
    "$h = [Environment]::GetEnvironmentVariable('LEASE_HANDLE'); "
    "$s = [Microsoft.Win32.SafeHandles.SafeFileHandle]::new([IntPtr][int]$h,$false); "
    "$f = [IO.FileStream]::new($s,[IO.FileAccess]::Write); "
    "$b = [Text.Encoding]::ASCII.GetBytes('through-the-handle'); $f.Write($b,0,$b.Length); "
    "$f.Flush(); "
    "try { [void][IO.File]::ReadAllText('@LEASE@'); "
    "[Console]::Out.WriteLine('open-by-path=allowed') } "
    "catch { [Console]::Out.WriteLine('open-by-path=denied') }"
)


def test_a_confined_child_run_by_the_runner_completes_with_its_output_and_the_loan_retired(
        runner_box):
    rb = runner_box
    outcome = rb.runner.run(rb.spec(_RAN))
    assert outcome.status == "completed" and outcome.exit_code == 0, outcome
    assert b"child-output" in outcome.output
    assert (rb.layout.tmp / "ran.txt").read_bytes() == b"ran"
    assert rb.runner.active_tokens() == ()
    assert rb.scope.claims == 1 and rb.scope.borrows >= 1, "the ownership guard was not entered"
    assert rb.scope.retired == [True]
    assert rb.confinement_seen == [rb.container.sid], "the child was not in the container"


def test_a_confined_child_that_outlives_its_timeout_dies_with_the_process_it_started(
        runner_box):
    rb = runner_box
    rb.require_child_shell()
    started = time.monotonic()
    outcome, grandchild = rb.run_until_pid_file(_WITH_GRANDCHILD, timeout=_TIMEOUT)
    assert time.monotonic() - started < _PROMPTLY, "the runner waited out an orphan"
    assert outcome.status == "timed_out", outcome
    assert rb.runner.active_tokens() == ()
    assert rb.scope.retired == [True]
    assert grandchild.wait_gone(), "the grandchild outlived the Job"


def test_a_confined_child_started_and_stopped_by_token_leaves_no_live_process(runner_box):
    rb = runner_box
    rb.require_child_shell()
    owned = rb.runner.start(rb.spec(_WITH_GRANDCHILD))
    leader = rb.watch(owned.pid)
    grandchild = rb.wait_for_pid_file()
    assert not grandchild.is_gone(), "the grandchild never started"
    started = time.monotonic()
    outcome = rb.runner.stop(owned.token)
    assert time.monotonic() - started < _PROMPTLY, "stop waited out an orphan"
    assert outcome.status == "stopped"
    assert rb.runner.active_tokens() == ()
    assert rb.scope.retired == [True]
    assert grandchild.wait_gone() and leader.is_gone()


def test_a_script_run_by_the_runner_gets_no_utility_cmdlet_and_still_gets_dotnet(runner_box):
    """The same contract as the box's: the probe must not depend on what the CI host lost."""
    rb = runner_box
    outcome = rb.runner.run(rb.spec(
        "[Console]::Out.WriteLine('dotnet-ran'); Write-Output 'cmdlet-ran'"))
    assert b"dotnet-ran" in outcome.output and outcome.exit_code != 0, outcome
    assert b"cmdlet-ran" not in outcome.output, outcome


def test_a_launch_for_a_container_that_does_not_exist_is_refused_with_no_token(runner_box):
    rb = runner_box
    rb.use_container_sid("S-1-15-2-1-2-3-4-5-6-7")
    with pytest.raises(OSError):
        rb.runner.run(rb.spec(_RAN))
    assert rb.runner.active_tokens() == ()
    assert rb.scope.retired == [False], "an unproven loan must be retired unproven"
    assert not (rb.layout.tmp / "ran.txt").exists()


def test_a_launch_without_localappdata_in_the_child_environment_is_refused_by_the_os(
        runner_box):
    rb = runner_box
    with pytest.raises(OSError) as refusal:
        rb.runner.run(rb.spec(_RAN, without=("LOCALAPPDATA",)))
    assert refusal.value.errno == 203, refusal.value
    assert rb.runner.active_tokens() == ()
    assert rb.scope.retired == [False]
    assert not (rb.layout.tmp / "ran.txt").exists()


def test_a_launch_that_silently_produced_an_unconfined_child_is_refused_before_it_runs(
        runner_box):
    rb = runner_box
    rb.use_unconfined_launch()
    with pytest.raises(ac.PolicyNotApplied):
        rb.runner.run(rb.spec(_RAN))
    assert rb.runner.active_tokens() == ()
    assert rb.scope.retired == [False]
    assert not (rb.layout.tmp / "ran.txt").exists(), "the unconfined child ran code"
    assert [proc.poll() is not None for proc in rb.created] == [True], "the child was left alive"


def test_the_lease_handle_reaches_a_confined_child_that_cannot_open_the_file_behind_it(
        runner_box):
    rb = runner_box
    script = render(_THROUGH_HANDLE, {"LEASE": str(rb.scope.lease_path)})
    outcome = rb.runner.run(rb.spec(script))
    assert outcome.status == "completed" and b"open-by-path=denied" in outcome.output, outcome
    assert rb.scope.lease_path.read_bytes() == b"through-the-handle"
