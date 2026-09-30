"""Throwaway box and runner support for the macOS Seatbelt checks.

Everything here is POSIX and imports cleanly on any host; only the darwin tests apply the
real ``sandbox-exec``. A ``SeatbeltBox`` owns a layout and one profile: ``run_body`` runs a
shell body under that profile. A launch is judged applied only when its shell first failed
to write the box's CANARY (a path in an empty directory no profile makes writable) and the
canary is still absent afterwards; a wrapper that execs the command without a profile fails
that test and the body never runs. ``SeatbeltRunner`` builds a ``ProcessRunner`` over the same layout with
a production ``ProcessOwnership`` scope, and does not replace any part of the runner.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

import pytest

from conductor.command.adapters.process import CommandSpec, ProcessRunner
from conductor.command.adapters.process_ownership_values import ProcessLease, ProcessOwnership
from tests import os_boundary_darwin as sb
from tests.os_boundary_layout import (
    Layout, Operation, make_layout, published_pid, render, snapshot)

_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
_STEP_TIMEOUT = 90.0
_WAIT = 60.0


@dataclass(frozen=True)
class Outcome:
    """One shell run: was it confined (the canary witness), how it ended, what it printed."""

    applied: bool
    exit_code: int
    output: str


def make_canary(layout: Layout) -> Path:
    """The path a launch's witness writes to, in an empty directory no profile makes writable."""
    directory = layout.base / "canary"
    directory.mkdir(exist_ok=True)
    return directory / "witness"


def _judged_applied(output: str, canary: Path) -> bool:
    try:
        sb.require_applied(output, canary)
    except sb.PolicyNotApplied:
        return False
    return True


class SeatbeltBox:
    """A layout and the profile every sandboxed run in it is subject to."""

    def __init__(self, layout: Layout, **profile_arguments) -> None:
        self.layout = layout
        self.canary = make_canary(layout)
        self._arguments = profile_arguments
        self.profile = sb.seatbelt_profile(**profile_arguments)

    def variant(self, **changes) -> "SeatbeltBox":
        """The same layout under a profile with some arguments replaced."""
        return SeatbeltBox(self.layout, **{**self._arguments, **changes})

    def snapshot(self, root_name: str):
        return snapshot(self.layout.root(root_name))

    def tokens(self, root_name: str = "source") -> dict[str, str]:
        return self.layout.tokens(root_name)

    def run_body(self, body: str, *, root: str = "source") -> Outcome:
        script = render(body, self.tokens(root))
        command = ["/bin/sh", "-c", sb.witnessed_script(self.canary, script)]
        argv = sb.sandbox_argv(self.profile, command)
        done = subprocess.run(argv, capture_output=True, timeout=_STEP_TIMEOUT, env=dict(_ENV),
                              cwd=str(self.layout.tmp), check=False)
        text = (done.stdout + done.stderr).decode("utf-8", errors="replace")
        return Outcome(_judged_applied(text, self.canary), done.returncode, text)

    def run(self, operation: Operation, *, root: str = "source") -> list[Outcome]:
        return [self.run_body(step.body, root=root) for step in operation.posix]

    def control_write(self) -> bool:
        """A sandboxed launch built the same way writes to the attempt's own tmp."""
        marker = self.layout.tmp / "control.txt"
        marker.unlink(missing_ok=True)
        self.run_body('printf ok > "@TMPD@/control.txt"')
        return marker.exists() and marker.read_bytes() == b"ok"

    def write_inner_script(self, text: str) -> None:
        (self.layout.tmp / "inner.sh").write_bytes(render(text, self.tokens()).encode("utf-8"))


def _layout(tmp_path) -> Layout:
    """A layout in a directory of its own, so two boxes of one test never share a vendor home."""
    return make_layout(Path(tempfile.mkdtemp(prefix="box-", dir=tmp_path)).resolve())


def _writable(layout: Layout, *, review: bool = False) -> list[Path]:
    roots = [layout.tmp, layout.home, layout.vendor_home]
    return roots if review else roots + [layout.work]


def _vendor_entries(layout: Layout) -> list[Path]:
    """An empty directory and an empty file the vendor home must keep, as it would hold them."""
    (layout.vendor_home / "hooks").mkdir()
    (layout.vendor_home / "hooks-paths").write_bytes(b"")
    return [layout.vendor_home / "hooks", layout.vendor_home / "hooks-paths"]


@pytest.fixture
def implement_box(tmp_path):
    layout = _layout(tmp_path)
    return SeatbeltBox(layout, writable=_writable(layout))


@pytest.fixture
def review_box(tmp_path):
    layout = _layout(tmp_path)
    return SeatbeltBox(layout, writable=_writable(layout, review=True))


@pytest.fixture
def linked_box(tmp_path):
    layout = _layout(tmp_path)
    return SeatbeltBox(layout, writable=_writable(layout), deny_links=[layout.source])


@pytest.fixture
def protected_box(tmp_path):
    layout = _layout(tmp_path)
    return SeatbeltBox(layout, writable=_writable(layout), protected=_vendor_entries(layout))


@pytest.fixture
def unprotected_box(tmp_path):
    layout = _layout(tmp_path)
    _vendor_entries(layout)
    return SeatbeltBox(layout, writable=_writable(layout))


@pytest.fixture
def absent_box(tmp_path):
    layout = _layout(tmp_path)
    names = [layout.vendor_home / "hooks", layout.vendor_home / "hooks-paths"]
    return SeatbeltBox(layout, writable=_writable(layout), protected=names)


class LeaseScope:
    """An ownership scope with one inheritable descriptor per claim and a retire record."""

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
        descriptor = os.open(self.lease_path, os.O_WRONLY)
        os.set_inheritable(descriptor, True)
        closed = [False]

        def retire(proven: bool) -> None:
            if not closed[0]:
                closed[0] = True
                os.close(descriptor)
            self.retired.append(proven)

        return ProcessLease((descriptor,), retire)

    @contextmanager
    def _borrow(self):
        self.borrows += 1
        yield


class PosixWatch:
    """A process identified by its number AND its start time, taken while it is alive.

    A process id is reused, so "is pid N gone" can answer for a different process. The
    start time pins the identity; a zombie is not running and counts as gone.
    """

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._birth = self._state(pid)
        if not self._birth:
            raise AssertionError(f"process {pid} was not alive when it was to be watched")

    @staticmethod
    def _state(pid: int) -> str:
        done = subprocess.run(["ps", "-o", "stat=,lstart=", "-p", str(pid)],
                              capture_output=True, text=True, check=False)
        return done.stdout.strip()

    def is_gone(self) -> bool:
        now = self._state(self.pid)
        return not now or now.startswith("Z") or now != self._birth


class SeatbeltRunner:
    """A ``ProcessRunner`` over a layout, its scope, and the profile its commands carry."""

    def __init__(self, layout: Layout, runner: ProcessRunner, scope: LeaseScope,
                 profile: str) -> None:
        self.layout, self.runner, self.scope, self.profile = layout, runner, scope, profile
        self.canary = make_canary(layout)
        self.watches: list[PosixWatch] = []

    def spec(self, script: str, *, timeout: float | None = None, profile: str | None = None,
             executable: str | None = None) -> CommandSpec:
        body = sb.witnessed_script(self.canary, render(script, self.layout.tokens()))
        argv = sb.sandbox_argv(profile or self.profile, ["/bin/sh", "-c", body])
        if executable is not None:
            argv[0] = executable
        return CommandSpec(argv=tuple(argv), cwd="work", env=dict(_ENV), timeout_seconds=timeout)

    def watch(self, pid: int) -> PosixWatch:
        watch = PosixWatch(pid)
        self.watches.append(watch)
        return watch

    def wait_for_pid_file(self, timeout: float = _WAIT) -> PosixWatch:
        pid_file = self.layout.tmp / "gc.pid"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if pid_file.exists():
                return self.watch(published_pid(pid_file))
            time.sleep(0.05)
        raise AssertionError("the sandboxed child never published the grandchild's id")

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
def seatbelt_runner(tmp_path):
    layout = _layout(tmp_path)
    profile = sb.seatbelt_profile(writable=_writable(layout))
    root = Path(layout.base).resolve()
    lease = layout.base / "lease.bin"
    lease.write_bytes(b"")
    scope = LeaseScope(lease)
    ProcessRunner.ownership_scopes.install(root, scope.ownership)
    box = SeatbeltRunner(layout, ProcessRunner(root), scope, profile)
    try:
        yield box
    finally:
        for token in box.runner.active_tokens():
            try:
                box.runner.stop(token)
            except Exception:
                pass
        ProcessRunner.ownership_scopes.remove(root, scope.ownership)
