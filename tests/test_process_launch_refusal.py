"""A confined launch the runner refused is one narrow, typed refusal; nothing else looks like it.

The transports catch `ProcessRunnerError`. Until now a refused confined launch reached them as a
bare `OSError`, so they caught the whole of `OSError` to handle it, and with it every other thing
that could go wrong. `LaunchRefused` is the one member of the family for the known fact that the OS
refused to create the confined child, or that the container policy was not on the still suspended
child and the child was ended before it ran. It carries a closed code and the OS error number, and
nothing of the original error's text. An outcome that is unknown because the child may have run, and
an ending of the child that did not finish, keep the errors they had.
"""
from __future__ import annotations

import os
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path

import pytest

from conductor.command.adapters import process as process_module
from conductor.command.adapters.process import (
    CommandSpec, LaunchRefused, ProcessRunner, ProcessRunnerError)
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.process_ownership_values import ProcessLease, ProcessOwnership

SID = "S-1-15-2-1-2-3-4-5-6-7"
SECRET = "token=hunter2-SECRET"


class SuspendedChild:
    """What the native launch hands back: a child that has not run, and records its ending."""

    def __init__(self, *, ending_fails: bool = False) -> None:
        self.stdin = self.stdout = self.stderr = None
        self.returncode, self.killed, self.released = None, False, False
        self.ending_fails, self._handle = ending_fails, 1

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed, self.returncode = True, 1

    def wait(self, timeout=None):
        if self.ending_fails:
            raise subprocess.TimeoutExpired("confined child", timeout)
        return self.returncode

    def release_handle(self):
        self.released = True


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A runner over a project with an owner scope that records how each loan was retired."""
    root = tmp_path.resolve()
    (root / "work").mkdir()
    retired = []
    scope = ProcessOwnership(
        check=lambda: None, claim=lambda: ProcessLease((1,), retired.append),
        borrow=nullcontext, resource=lambda _home: nullcontext())
    ProcessRunner.ownership_scopes.install(root, scope)
    spec = CommandSpec((str(Path(sys.executable)),), "work", boundary=WindowsContainer(SID),
                       timeout_seconds=5)
    try:
        yield ProcessRunner(root, environ={}), spec, retired, monkeypatch
    finally:
        ProcessRunner.ownership_scopes.remove(root, scope)


def native(monkeypatch, *, launch, policy=lambda child, sid: None):
    from conductor.command.adapters import _winlaunch
    monkeypatch.setattr(_winlaunch, "launch", launch)
    monkeypatch.setattr(_winlaunch, "require_policy", policy)


def refuses_the_launch(_spec, _cwd, _env, _payload, _loan):
    raise OSError(5, f"CreateProcessW failed for C:\\private\\path {SECRET}")


def test_the_launch_refusal_is_a_member_of_the_runner_error_family_with_a_closed_vocabulary():
    assert issubclass(LaunchRefused, ProcessRunnerError) and not issubclass(LaunchRefused, OSError)
    assert LaunchRefused("launch_failed").code == "launch_failed"
    assert LaunchRefused("policy_not_applied", 3).os_error == 3
    with pytest.raises(ValueError):
        LaunchRefused("anything else")


@pytest.mark.skipif(os.name != "nt", reason="the confined launch is Windows")
def test_a_confined_child_the_os_refuses_to_create_is_a_launch_refusal_with_no_text_of_the_error(
        site):
    runner, spec, retired, monkeypatch = site
    native(monkeypatch, launch=refuses_the_launch)
    with pytest.raises(LaunchRefused) as caught:
        runner.run(spec)
    error = caught.value
    assert (error.code, error.os_error) == ("launch_failed", 5)
    for shown in (str(error), repr(error), repr(error.args)):
        assert SECRET not in shown and "private" not in shown
    assert error.__cause__ is None and error.__context__ is None, "the original is not kept"
    assert retired == [False], "the loan is retired unproven, as it always was"
    assert runner.active_tokens() == ()


@pytest.mark.skipif(os.name != "nt", reason="the confined launch is Windows")
def test_a_policy_that_was_not_applied_to_the_suspended_child_is_a_launch_refusal_once_it_is_ended(
        site):
    runner, spec, retired, monkeypatch = site
    child = SuspendedChild()

    def not_applied(_child, _sid):
        raise OSError(f"AppContainer policy was not applied {SECRET}")

    native(monkeypatch, launch=lambda *_: child, policy=not_applied)
    with pytest.raises(LaunchRefused) as caught:
        runner.run(spec)
    assert caught.value.code == "policy_not_applied" and caught.value.os_error is None
    assert SECRET not in str(caught.value) and caught.value.__context__ is None
    assert child.killed and child.released, "the child was ended and reaped before it ran"
    assert retired == [False]


@pytest.mark.skipif(os.name != "nt", reason="the confined launch is Windows")
def test_a_child_that_could_not_be_ended_after_a_policy_failure_is_not_made_a_safe_refusal(site):
    runner, spec, retired, monkeypatch = site
    child = SuspendedChild(ending_fails=True)

    def not_applied(_child, _sid):
        raise OSError("AppContainer policy was not applied")

    native(monkeypatch, launch=lambda *_: child, policy=not_applied)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        runner.run(spec)
    assert not isinstance(caught.value, ProcessRunnerError)
    assert child.killed and child.released
    assert retired == [False]


@pytest.mark.skipif(os.name != "nt", reason="the confined launch is Windows")
def test_a_failure_after_the_policy_held_may_mean_the_child_ran_and_is_not_a_launch_refusal(
        site):
    runner, spec, retired, monkeypatch = site
    child = SuspendedChild()
    native(monkeypatch, launch=lambda *_: child)

    def job_fails(_proc):
        raise OSError("NtResumeProcess failed with NTSTATUS 0xc0000001")

    monkeypatch.setattr(process_module._procgroup, "make_group", job_fails)
    with pytest.raises(OSError, match="NtResumeProcess") as caught:
        runner.run(spec)
    assert not isinstance(caught.value, ProcessRunnerError)
    assert child.killed and retired == [False]


def test_a_plain_launch_that_fails_keeps_the_error_it_had_and_is_not_a_launch_refusal(tmp_path):
    root = tmp_path.resolve()
    (root / "work").mkdir()
    spec = CommandSpec(("a-program-that-is-not-installed-h5",), "work", timeout_seconds=5)
    with pytest.raises(OSError) as caught:
        ProcessRunner(root, environ={}).run(spec)
    assert not isinstance(caught.value, ProcessRunnerError)
