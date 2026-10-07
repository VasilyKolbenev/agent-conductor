"""Support for running the AppContainer probe through the ONE ``ProcessRunner``.

``RunnerBox`` replaces only ``ProcessRunner._launch`` (the spawn) and puts a check in
front of ``_procgroup.make_group`` (the child exists, is suspended, and has run
nothing). The ownership scope is the production ``ProcessOwnership`` value with a real
inheritable handle to a lease file and a recorded ``retire``, installed under the
runner's own root exactly as an owner installs it. The runner's Job, timeout, stop and
fail-closed cleanup are untouched.
"""
from __future__ import annotations

import subprocess
import threading
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from conductor.command.adapters import _procgroup
from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_ownership_values import ProcessLease, ProcessOwnership
from tests import os_boundary_windows as ac
from tests.os_boundary_box import WITHOUT_CMDLETS, Box, base_environment, require_child_shell
from tests.os_boundary_layout import Layout, make_layout, published_pid, render

_WAIT = 60.0


class LeaseScope:
    """An ownership scope with one inheritable lease handle per claim and a retire record."""

    def __init__(self, lease_path: Path) -> None:
        self.lease_path = lease_path
        self.claims = 0
        self.borrows = 0
        self.retired: list[bool] = []
        self.ownership = ProcessOwnership(
            check=lambda: None, claim=self._claim, borrow=self._borrow,
            resource=lambda auth_home: nullcontext())

    def _claim(self) -> ProcessLease:
        self.claims += 1
        handle = ac.open_inheritable_file(self.lease_path)
        closed = [False]

        def retire(proven: bool) -> None:
            if not closed[0]:
                closed[0] = True
                ac.close_handle(handle)
            self.retired.append(proven)

        return ProcessLease((handle,), retire)

    @contextmanager
    def _borrow(self):
        self.borrows += 1
        yield


class RunnerBox:
    """A runner over a layout, a container, and a scope; the launch mode is switchable."""

    def __init__(self, layout: Layout, container: ac.Container, runner: ProcessRunner,
                 scope: LeaseScope) -> None:
        self.layout, self.container, self.runner, self.scope = layout, container, runner, scope
        self.created: list[ac.ConfinedProcess] = []
        self.confinement_seen: list[str | None] = []
        self.watches: list[ac.ProcessWatch] = []
        self._sid: str | None = container.sid
        self._tokens = {**layout.tokens(), "POWERSHELL": str(ac.POWERSHELL)}

    def spec(self, script: str, *, timeout: float | None = None,
             without: tuple[str, ...] = ()) -> CommandSpec:
        env = base_environment(self.layout.tmp)
        for name in without:
            env.pop(name)
        argv = (str(ac.POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                "Bypass", "-Command", WITHOUT_CMDLETS + render(script, self._tokens))
        return CommandSpec(argv=argv, cwd="work", env=env, timeout_seconds=timeout)

    def require_child_shell(self) -> None:
        """Skip the calling test when this host's container cannot start a shell of its own."""
        require_child_shell(Box(self.layout, self.container))

    def use_container_sid(self, sid: str) -> None:
        self._sid = sid

    def use_unconfined_launch(self) -> None:
        """The launch succeeds but the container attribute is left off: policy not applied."""
        self._sid = None

    def _launch(self, spec, cwd, env, payload, loan):
        handles = tuple(loan.handles) if loan is not None else ()
        child_env = dict(env)
        if handles:
            child_env["LEASE_HANDLE"] = str(handles[0])
        proc = ac.launch(subprocess.list2cmdline(list(spec.argv)), sid=self._sid,
                         cwd=str(cwd), env=child_env, suspended=True, inherit=handles)
        self.created.append(proc)
        return proc

    def _checked_make_group(self, real):
        def make_group(proc):
            self.confinement_seen.append(ac.confinement_of(proc.handle))
            ac.require_confinement(proc.handle, self.container.sid)
            return real(proc)
        return make_group

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(ProcessRunner, "_launch", staticmethod(self._launch))
        monkeypatch.setattr(_procgroup, "make_group",
                            self._checked_make_group(_procgroup.make_group))

    def watch(self, pid: int) -> ac.ProcessWatch:
        """A handle to a process that is alive now; closed with the box."""
        watch = ac.ProcessWatch(pid)
        self.watches.append(watch)
        return watch

    def wait_for_pid_file(self, timeout: float = _WAIT) -> ac.ProcessWatch:
        """Wait for the grandchild's id and take a handle to it at once, while it is alive."""
        pid_file = self.layout.tmp / "gc.pid"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if pid_file.exists():
                return self.watch(published_pid(pid_file))
            time.sleep(0.05)
        raise AssertionError("the confined child never published the grandchild's id")

    def run_until_pid_file(self, script: str, *, timeout: float):
        """``run`` on a thread, so the test can see the grandchild live before the timeout."""
        result: list = []
        worker = threading.Thread(
            target=lambda: result.append(self.runner.run(self.spec(script, timeout=timeout))))
        worker.start()
        grandchild = self.wait_for_pid_file()
        worker.join(timeout + _WAIT)
        assert result, "the runner did not return"
        return result[0], grandchild


@pytest.fixture
def runner_box(tmp_path, container, monkeypatch):
    layout = make_layout(tmp_path)
    for directory in (layout.tmp, layout.home, layout.vendor_home, layout.work):
        ac.grant(directory, container.sid, ac.MODIFY)
    root = Path(layout.base).resolve()
    lease = layout.base / "lease.bin"
    lease.write_bytes(b"")
    scope = LeaseScope(lease)
    ProcessRunner.ownership_scopes.install(root, scope.ownership)
    runner = ProcessRunner(root)
    box = RunnerBox(layout, container, runner, scope)
    box.install(monkeypatch)
    try:
        yield box
    finally:
        for watch in box.watches:
            watch.close()
        for token in runner.active_tokens():
            try:
                runner.stop(token)
            except Exception:
                pass
        ProcessRunner.ownership_scopes.remove(root, scope.ownership)
