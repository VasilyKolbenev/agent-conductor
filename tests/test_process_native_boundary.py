"""The production runner applies and verifies the native policy before any child code."""
from dataclasses import replace
import os
import time

import pytest

from conductor.command.adapters.process import CommandSpec, CommandSpecError, ProcessRunner
from conductor.command.adapters.process_boundary import WindowsContainer
from conductor.command.adapters.process_projection import _payload_from_spec
from conductor.command.adapters.base import AdapterContractError

SID = "S-1-15-2-1-2-3-4-5-6-7"


def test_native_policy_is_typed_private_and_cannot_be_erased_by_payload_projection():
    spec = CommandSpec(("not-started",), "work", boundary=WindowsContainer(SID))
    assert SID not in repr(spec)
    with pytest.raises(CommandSpecError):
        replace(spec, boundary={"sid": SID})
    with pytest.raises(AdapterContractError, match="native policy"):
        _payload_from_spec(spec)
    for sid in ("S-1-15-2-1", "S-1-15-3-1", SID + "-8", SID.replace("-7", "-4294967296")):
        with pytest.raises(ValueError):
            WindowsContainer(sid)


@pytest.fixture
def native_box(tmp_path):
    if os.name != "nt":
        pytest.skip("AppContainer product launch is Windows-only")
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import base_environment, WITHOUT_CMDLETS
    from tests.os_boundary_runner import LeaseScope
    work, scratch = tmp_path / "work", tmp_path / "scratch"
    work.mkdir()
    scratch.mkdir()
    lease = tmp_path / "lease"
    lease.write_bytes(b"")
    scope = LeaseScope(lease)
    root = tmp_path.resolve()
    runner = ProcessRunner(root)
    ProcessRunner.ownership_scopes.install(root, scope.ownership)
    with ac.Container() as container:
        for path in (work, scratch):
            ac.grant(path, container.sid, ac.MODIFY)
        def spec(script, **kwargs):
            return CommandSpec((str(ac.POWERSHELL), "-NoProfile", "-NonInteractive",
                "-Command", WITHOUT_CMDLETS + script), "work", env=base_environment(scratch),
                boundary=WindowsContainer(container.sid), timeout_seconds=20, **kwargs)
        try:
            yield runner, scope, work, spec
        finally:
            for token in runner.active_tokens():
                runner.stop(token)
            ProcessRunner.ownership_scopes.remove(root, scope.ownership)


def test_native_launch_delivers_stdin_and_keeps_stderr_out_of_the_result(native_box):
    runner, scope, work, spec = native_box
    body = ("[Console]::Out.Write([Console]::In.ReadToEnd()); "
            "[Console]::Error.Write('private diagnostic'); "
            "[IO.File]::WriteAllText('result.txt', 'written')")
    result = runner.run(spec(body, stdin_bytes=b"actual input", separate_stderr=True))
    assert result.status == "completed" and result.exit_code == 0
    assert result.stdin_state == "delivered" and result.output == b"actual input"
    assert (work / "result.txt").read_text() == "written"
    assert scope.retired == [True] and runner.active_tokens() == ()


def test_unapplied_policy_is_refused_before_resume_and_retires_loan_unproven(native_box, monkeypatch):
    runner, scope, work, spec = native_box
    real = ProcessRunner._launch
    children = []
    def unconfined(spec, cwd, env, payload, loan):
        proc = real(replace(spec, boundary=None), cwd, env, payload, loan)
        children.append(proc)
        return proc
    monkeypatch.setattr(ProcessRunner, "_launch", staticmethod(unconfined))
    with pytest.raises(OSError, match="policy was not applied"):
        runner.run(spec("[IO.File]::WriteAllText('escaped.txt','bad')"))
    assert not (work / "escaped.txt").exists()
    assert len(children) == 1 and children[0].poll() is not None
    assert children[0].stdout.closed
    assert scope.retired == [False] and runner.active_tokens() == ()


def test_native_timeout_keeps_the_existing_runner_stop_and_loan_contract(native_box):
    runner, scope, _work, spec = native_box
    result = runner.run(replace(spec("[Threading.Thread]::Sleep(30000)"), timeout_seconds=.3))
    assert result.status == "timed_out" and result.exit_code is None
    assert scope.retired == [True] and runner.active_tokens() == ()


def test_native_launch_inherits_the_ownership_loan_handle_without_path_access(native_box, monkeypatch):
    from tests.os_boundary_layout import render
    from tests.test_os_boundary_windows_runner import _THROUGH_HANDLE
    runner, scope, _work, spec = native_box
    real = ProcessRunner._launch
    def with_handle(spec, cwd, env, payload, loan):
        return real(spec, cwd, {**env, "LEASE_HANDLE": str(loan.handles[0])}, payload, loan)
    monkeypatch.setattr(ProcessRunner, "_launch", staticmethod(with_handle))
    result = runner.run(spec(render(_THROUGH_HANDLE, {"LEASE": str(scope.lease_path)})))
    assert result.exit_code == 0 and b"open-by-path=denied" in result.output
    assert scope.lease_path.read_bytes() == b"through-the-handle"
    assert scope.retired == [True]


def test_native_token_stop_reaps_the_actual_descendant(native_box):
    from tests import os_boundary_windows as ac
    runner, scope, work, spec = native_box
    body = ("$i=[Diagnostics.ProcessStartInfo]::new(); "
        f"$i.FileName='{ac.POWERSHELL}'; "
        "$i.Arguments='-NoProfile -NonInteractive -Command [Threading.Thread]::Sleep(120000)'; "
        "$i.UseShellExecute=$false; $p=[Diagnostics.Process]::Start($i); "
        "[IO.File]::WriteAllText('child.pid.tmp',[string]$p.Id); "
        "[IO.File]::Move('child.pid.tmp','child.pid'); [Threading.Thread]::Sleep(150000)")
    owned = runner.start(spec(body))
    deadline = time.monotonic() + 60
    while not (work / "child.pid").exists() and time.monotonic() < deadline:
        time.sleep(.05)
    assert (work / "child.pid").exists(), "native child never published its descendant"
    watch = ac.ProcessWatch(int((work / "child.pid").read_text()))
    try:
        assert not watch.is_gone()
        result = runner.stop(owned.token)
        assert result.status == "stopped" and watch.wait_gone()
    finally:
        watch.close()
    assert runner.active_tokens() == () and scope.retired == [True]
