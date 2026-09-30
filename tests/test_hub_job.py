"""The hub's own Windows job (spec 4.1.4, ADR-1b, 4.1.13 item 3).

A job that ends its processes when it closes (`KILL_ON_JOB_CLOSE`) would end every child a hub
starts when the window that holds the hub is closed, and with them any attempt in flight, which
is `recovery_required` for the project. So the hub reads its own job at start: no job, or one
that does not end its processes, is nothing to fear (`none`); a job that ends them but lets a
child leave (`BREAKAWAY_OK`, `SILENT_BREAKAWAY_OK`) is `breakaway`, and the spawner starts
children with `CREATE_BREAKAWAY_FROM_JOB`; one that ends them and does not let them leave is
`kill_on_close`, and no child is started from this hub.

The decision is a pure function and is judged on every combination of flags. The reading of the
real job and the behaviour of real children are Windows': a job is made here, a stand-in for the
hub is put into it, and the test closes the job. The instrument proves itself first: a child that
was started without breakaway is gone when its job is closed.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

import pytest

from conductor import process_identity
from conductor.hub import job
from tests._drain_harness import WAIT, wait_until

STANDIN = Path(__file__).resolve().with_name("_hub_job_standin.py")
#: The interpreter itself. In a virtual environment `sys.executable` is a launcher that starts the
#: interpreter as its child, inside a job of the launcher's own (limit flags 0x3000); the process
#: a test puts into a job must be the one that reads it, so the stand-in is started from the
#: base interpreter, which needs the folder that holds `conductor` on its path.
INTERPRETER = sys._base_executable
SOURCE = str(Path(job.__file__).resolve().parents[2])
KILL, BREAKAWAY, SILENT = 0x2000, 0x0800, 0x1000
windows = pytest.mark.skipif(os.name != "nt", reason="a job is Windows'")


@pytest.mark.parametrize(("flags", "expected"), [
    (0, "none"), (0x0040, "none"), (BREAKAWAY, "none"), (SILENT, "none"),
    (KILL, "kill_on_close"), (KILL | 0x0040, "kill_on_close"),
    (KILL | BREAKAWAY, "breakaway"), (KILL | SILENT, "breakaway"),
    (KILL | BREAKAWAY | SILENT, "breakaway")])
def test_a_job_that_ends_its_processes_is_breakaway_or_kill_on_close_by_whether_they_may_leave(
        flags, expected):
    assert job.policy_of(True, flags) == expected


def test_a_hub_that_is_in_no_job_has_no_policy_to_fear_whatever_the_flags_would_say():
    assert job.policy_of(False, KILL) == "none"


def test_the_words_are_the_three_of_the_spec():
    assert job.POLICIES == ("none", "breakaway", "kill_on_close")


@pytest.mark.skipif(os.name == "nt", reason="off Windows there is no job")
def test_off_windows_there_is_no_job_and_the_policy_is_none():
    assert job.own_policy() == "none"


@windows
def test_a_process_reads_the_job_it_is_in_the_way_the_os_says():
    in_job, flags = job.read_own_job()
    assert isinstance(in_job, bool) and (flags >= 0)
    assert job.own_policy() == job.policy_of(in_job, flags)


# -- a real job, a stand-in for the hub in it, and the closing of the job ---------------------


class _Basic(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _Io(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in "abcdef"]


class _Extended(ctypes.Structure):
    _fields_ = [("Basic", _Basic), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _kernel():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    return k32


class _Job:
    """A job that ends its processes when it closes, and may let them leave."""

    def __init__(self, *, may_leave: bool) -> None:
        self.k32 = _kernel()
        self.handle = self.k32.CreateJobObjectW(None, None)
        assert self.handle, ctypes.get_last_error()
        info = _Extended()
        self.flags = KILL | (BREAKAWAY if may_leave else 0)
        info.Basic.LimitFlags = self.flags
        assert self.k32.SetInformationJobObject(self.handle, 9, ctypes.byref(info),
                                                ctypes.sizeof(info)), ctypes.get_last_error()

    def hold(self, proc: subprocess.Popen) -> None:
        process = self.k32.OpenProcess(0x0100 | 0x0001, False, proc.pid)   # SET_QUOTA, TERMINATE
        assert process, ctypes.get_last_error()
        try:
            assert self.k32.AssignProcessToJobObject(self.handle, process), (
                f"the stand-in could not be put into the job: {ctypes.get_last_error()}")
        finally:
            self.k32.CloseHandle(process)

    def close(self) -> None:
        if self.handle:
            self.k32.CloseHandle(self.handle)
            self.handle = None


class _Standin:
    """The stand-in for a hub, in a job (or in two, the second nested in the first), and what
    it reported. `which` is the policy its spawner is given: `real` (the job it reads),
    `breakaway` or `none` (whatever the job says)."""

    def __init__(self, tmp_path: Path, *, may_leave: bool, which: str,
                 inner_may_leave: bool | None = None) -> None:
        self.go, self.result = tmp_path / "go", tmp_path / "result.json"
        self.pidfile = tmp_path / "sleeper.pid"
        env = {**os.environ, "SLEEPER_PIDFILE": str(self.pidfile),
               "PYTHONPATH": os.pathsep.join(filter(None, [SOURCE, os.environ.get("PYTHONPATH")]))}
        self.jobs = [_Job(may_leave=may_leave)]
        if inner_may_leave is not None:
            self.jobs.append(_Job(may_leave=inner_may_leave))
        self.proc = subprocess.Popen(
            [INTERPRETER, str(STANDIN), str(self.go), str(self.result), str(tmp_path / "home"),
             which], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)
        for each in self.jobs:
            each.hold(self.proc)
        self.go.write_text("go", encoding="ascii")
        wait_until(self.result.exists, WAIT, "the stand-in to report")
        self.report = json.loads(self.result.read_text(encoding="utf-8"))

    def assert_it_read_the_job_made_here(self) -> None:
        """The process in the job is the stand-in itself, and its own reading is the innermost
        job made here.

        A job that holds a launcher in front of the interpreter is a job the stand-in is not in
        (the launcher's child is in the launcher's own job, not in this one), so every claim
        about "the job made here" is first judged by what the stand-in says of itself.
        """
        report, flags = self.report, self.jobs[-1].flags
        assert report["pid"] == self.proc.pid, (
            f"the process put into the job ({self.proc.pid}) is not the stand-in "
            f"({report['pid']}): a launcher stands in front of it")
        assert report["in_job"] is True
        assert report["flags"] == flags, (
            f"the stand-in read limit flags {report['flags']:#x}, not the {flags:#x} "
            "set on the job made here")

    def sleeper(self) -> int:
        """The pid the sleeper wrote; the file is made before it is filled, so wait for digits."""
        def written() -> bool:
            return self.pidfile.exists() and self.pidfile.read_text(encoding="ascii").isdigit()

        wait_until(written, WAIT, "the sleeper to write its pid")
        return int(self.pidfile.read_text(encoding="ascii"))

    def close_the_job(self) -> None:
        for each in reversed(self.jobs):
            each.close()
        self.proc.wait(timeout=WAIT)

    def clean_up(self, pid: int | None) -> None:
        for each in reversed(self.jobs):
            each.close()
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=WAIT)
        if pid is not None and process_identity.started_of(pid) is not None:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


@windows
def test_the_instrument_a_child_started_without_breakaway_is_gone_when_its_job_closes(tmp_path):
    standin = _Standin(tmp_path, may_leave=True, which="none")
    pid = None
    try:
        standin.assert_it_read_the_job_made_here()
        assert standin.report["started"] is True
        pid = standin.sleeper()
        assert process_identity.started_of(pid) is not None
        standin.close_the_job()
        wait_until(lambda: process_identity.started_of(pid) is None, WAIT,
                   "the child that stayed in the job to be ended with it")
    finally:
        standin.clean_up(pid)


@windows
def test_in_a_job_that_allows_it_a_child_breaks_away_and_outlives_the_job(tmp_path):
    standin = _Standin(tmp_path, may_leave=True, which="real")
    pid = None
    try:
        standin.assert_it_read_the_job_made_here()
        assert (standin.report["policy"], standin.report["started"]) == ("breakaway", True)
        pid = standin.sleeper()
        standin.close_the_job()
        assert process_identity.started_of(pid) is not None, "the child died with the job"
    finally:
        standin.clean_up(pid)


@windows
def test_in_a_job_that_does_not_allow_it_every_project_start_is_refused_and_nothing_is_made(
        tmp_path):
    standin = _Standin(tmp_path, may_leave=False, which="real")
    try:
        standin.assert_it_read_the_job_made_here()
        report = standin.report
        assert (report["policy"], report["started"], report["code"]) == (
            "kill_on_close", False, "hub_in_kill_on_close_job")
        assert not standin.pidfile.exists()
        assert not (tmp_path / "home" / "logs").exists(), "a log was made for a child not started"
    finally:
        standin.clean_up(None)


@windows
def test_a_breakaway_the_real_os_refuses_in_a_job_that_does_not_allow_it_is_that_same_refusal(
        tmp_path):
    standin = _Standin(tmp_path, may_leave=False, which="breakaway")
    try:
        standin.assert_it_read_the_job_made_here()
        report = standin.report
        assert (report["started"], report["code"]) == (False, "hub_in_kill_on_close_job")
        assert not standin.pidfile.exists(), "a child was started in a job that forbids it"
    finally:
        standin.clean_up(None)


@windows
def test_a_process_in_nested_jobs_reads_the_innermost_one_and_not_the_outermost(tmp_path):
    standin = _Standin(tmp_path, may_leave=True, which="real", inner_may_leave=False)
    try:
        standin.assert_it_read_the_job_made_here()
        report = standin.report
        assert (report["flags"], report["policy"], report["started"]) == (
            KILL, "kill_on_close", False), "the outer job allows a breakaway and the inner one not"
    finally:
        standin.clean_up(None)


@windows
def test_a_child_that_leaves_the_inner_job_is_still_ended_by_an_outer_job_that_forbids_it(
        tmp_path):
    """The limit of reading only the immediate job, shown on the OS: the read says `breakaway`."""
    standin = _Standin(tmp_path, may_leave=False, which="real", inner_may_leave=True)
    pid = None
    try:
        standin.assert_it_read_the_job_made_here()
        assert (standin.report["policy"], standin.report["started"]) == ("breakaway", True)
        pid = standin.sleeper()
        standin.jobs[1].close()
        standin.proc.wait(timeout=WAIT)
        assert process_identity.started_of(pid) is not None, "the child died with the inner job"
        standin.jobs[0].close()
        wait_until(lambda: process_identity.started_of(pid) is None, WAIT,
                   "the child that left the inner job to be ended with the outer one")
    finally:
        standin.clean_up(pid)
