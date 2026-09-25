"""Terminate the exact process group a runner started, and nothing else.

The runner records the child it spawned and hands the *handle* it received at
spawn time to the group this module builds. Termination targets that handle's
group -- on POSIX the child's own session, on Windows a kill-on-close Job
Object the child is assigned to -- so the child and the descendants it spawned
die together while every other process on the machine is untouched. No function
here accepts a caller-supplied PID: there is no name for "some other process"
to pass, which is the property the foreign-PID sabotage leans on.

On Windows ``CreateProcess`` starts the child suspended.  A configured
kill-on-close Job is created and assigned before ``NtResumeProcess`` lets any
child code run, so a grandchild cannot escape through the assignment race.  A
Job creation, configuration, assignment, or resume failure is fail-closed: the
suspended child is terminated and reaped by the caller.  The POSIX branch uses
``start_new_session`` so ``killpg`` reaches the whole child session.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Protocol


class ProcessGroup(Protocol):
    """A handle to the started child's group; terminate reaches only that group."""

    def terminate(self) -> None: ...

    def close(self) -> None: ...

    def retired(self, *, timeout: float) -> bool: ...


def popen_kwargs() -> dict[str, object]:
    """Spawn flags that put the child in its own killable group on each platform."""
    if os.name == "nt":
        return {"creationflags": _CREATE_NO_WINDOW | _CREATE_SUSPENDED}
    return {"start_new_session": True}


#: CreateProcess's bound on the command line it is handed, in UTF-16 code units INCLUDING the
#: terminating NUL. MEASURED 25.09.2026 (r1-cmdline-boundary.log): 32,766 units and the NUL start,
#: 32,767 and the NUL refuse with WinError 206 -- ASCII and non-BMP text alike.
COMMAND_LINE_LIMIT = 32_767


def command_line_units(argv) -> int:
    """UTF-16 code units of the command line Windows builds from ``argv``, its NUL included.

    The serializer is the one ``Popen`` hands ``CreateProcess`` (``subprocess.list2cmdline``),
    counted the way Windows counts it: a character past the BMP is two units. Spawns nothing.
    """
    line = subprocess.list2cmdline(list(argv))
    return len(line) + sum(1 for char in line if ord(char) > 0xFFFF) + 1


class _SessionGroup:
    """POSIX: the child leads its own session; the whole session is signalled."""

    def __init__(self, proc: "subprocess.Popen[bytes]") -> None:
        self._proc = proc
        self._pgid = proc.pid  # start_new_session -> pgid == the child's pid

    def terminate(self) -> None:
        try:
            os.killpg(self._pgid, signal.SIGKILL)
        except ProcessLookupError:
            if self._proc.poll() is None:
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    return

    def retired(self, *, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                os.killpg(self._pgid, 0)
            except ProcessLookupError:
                return True
            except PermissionError:
                return False
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def close(self) -> None:
        return None


_CREATE_NO_WINDOW = 0x08000000
_CREATE_SUSPENDED = 0x00000004


if os.name == "nt":  # pragma: win32 cover
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _k32.AssignProcessToJobObject.restype = wintypes.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.TerminateJobObject.restype = wintypes.BOOL
    _k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.SetInformationJobObject.restype = wintypes.BOOL
    _k32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
        wintypes.LPVOID, wintypes.DWORD, ctypes.c_void_p]

    class _ACCOUNTING(ctypes.Structure):
        _fields_ = [("total_user", ctypes.c_int64), ("total_kernel", ctypes.c_int64),
            ("period_user", ctypes.c_int64), ("period_kernel", ctypes.c_int64),
            ("page_faults", wintypes.DWORD), ("total_processes", wintypes.DWORD),
            ("active_processes", wintypes.DWORD), ("terminated_processes", wintypes.DWORD)]
    _ntdll = ctypes.WinDLL("ntdll")
    _ntdll.NtResumeProcess.restype = wintypes.LONG
    _ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]

    _JOB_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    class _BASIC_LIMIT(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.POINTER(wintypes.ULONG)),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BASIC_LIMIT),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def _win_error(operation: str) -> OSError:
        return OSError(ctypes.get_last_error(), f"{operation} failed")

    def _create_kill_on_close_job() -> "wintypes.HANDLE":
        job = _k32.CreateJobObjectW(None, None)
        if not job:
            raise _win_error("CreateJobObjectW")
        info = _EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = _JOB_LIMIT_KILL_ON_JOB_CLOSE
        if not _k32.SetInformationJobObject(
                job, _JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info),
                ctypes.sizeof(info)):
            error = _win_error("SetInformationJobObject")
            _k32.CloseHandle(job)
            raise error
        return job

    class _JobGroup:
        """Windows: the child is in a kill-on-close Job; killing the job kills the tree."""

        def __init__(self, job: "wintypes.HANDLE", proc: "subprocess.Popen[bytes]") -> None:
            self._job = job
            self._proc = proc

        def terminate(self) -> None:
            if not _k32.TerminateJobObject(self._job, 1):
                raise _win_error("TerminateJobObject")
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired as e:
                raise OSError("terminated Job did not reap its leader") from e

        def retired(self, *, timeout: float) -> bool:
            deadline = time.monotonic() + timeout
            while self._job:
                facts = _ACCOUNTING()
                if not _k32.QueryInformationJobObject(self._job, 1, ctypes.byref(facts),
                        ctypes.sizeof(facts), None):
                    raise _win_error("QueryInformationJobObject")
                if facts.active_processes == 0:
                    return True
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.01)
            return False

        def close(self) -> None:
            if self._job:
                _k32.CloseHandle(self._job)
                self._job = None

    def make_group(proc: "subprocess.Popen[bytes]") -> ProcessGroup:
        """Assign the still-suspended child to a Job, then and only then resume."""
        job = _create_kill_on_close_job()
        if not _k32.AssignProcessToJobObject(job, int(proc._handle)):
            error = _win_error("AssignProcessToJobObject")
            _k32.CloseHandle(job)
            raise error
        status = _ntdll.NtResumeProcess(int(proc._handle))
        if status != 0:
            _k32.TerminateJobObject(job, 1)
            _k32.CloseHandle(job)
            raise OSError(f"NtResumeProcess failed with NTSTATUS {status:#x}")
        return _JobGroup(job, proc)

else:

    def make_group(proc: "subprocess.Popen[bytes]") -> ProcessGroup:
        return _SessionGroup(proc)
