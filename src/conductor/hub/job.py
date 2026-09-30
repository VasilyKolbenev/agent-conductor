"""The hub's own Windows job (spec 4.1.4, ADR-1b).

A job that ends its processes when it closes (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) would end
every child the hub starts when the window that holds the hub is closed, an attempt in flight
included, which is `recovery_required` for the project. The hub therefore reads its own job at
start (`IsProcessInJob`, then `QueryInformationJobObject` with the extended limits) and says one
of three words:

- `none`: no job, or one that does not end its processes; children are started as usual;
- `breakaway`: a job that ends its processes but lets a child leave (`BREAKAWAY_OK` or
  `SILENT_BREAKAWAY_OK`); children are started with `CREATE_BREAKAWAY_FROM_JOB`;
- `kill_on_close`: a job that ends its processes and does not let a child leave; no project is
  started from this hub, and the banner says how to start the hub outside of it.

Off Windows there is no such job and the word is always `none`. A job that cannot be read is
taken as `kill_on_close`: a wrong `none` would end the children with the window, a wrong
`kill_on_close` only asks the owner to start the hub from another terminal.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

POLICIES = ("none", "breakaway", "kill_on_close")
KILL_ON_JOB_CLOSE = 0x2000
BREAKAWAY_OK = 0x0800
SILENT_BREAKAWAY_OK = 0x1000
_EXTENDED_LIMITS = 9          # JobObjectExtendedLimitInformation


def policy_of(in_job: bool, limit_flags: int) -> str:
    """The word for a job of these limit flags, or for no job at all."""
    if not in_job or not limit_flags & KILL_ON_JOB_CLOSE:
        return "none"
    if limit_flags & (BREAKAWAY_OK | SILENT_BREAKAWAY_OK):
        return "breakaway"
    return "kill_on_close"


class _Basic(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD), ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _Io(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]


class _Extended(ctypes.Structure):
    _fields_ = [("Basic", _Basic), ("Io", _Io), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def read_own_job() -> tuple[bool, int]:
    """`(in_job, limit_flags)` of the job this process is in; Windows only.

    Raises:
        OSError: The OS would not say, or this is not Windows.
    """
    if os.name != "nt":
        raise OSError("only Windows has this kind of job")
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    k32.IsProcessInJob.restype = wintypes.BOOL
    k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    k32.QueryInformationJobObject.restype = wintypes.BOOL
    found = wintypes.BOOL()
    if not k32.IsProcessInJob(k32.GetCurrentProcess(), None, ctypes.byref(found)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not found.value:
        return False, 0
    info = _Extended()
    if not k32.QueryInformationJobObject(None, _EXTENDED_LIMITS, ctypes.byref(info),
                                         ctypes.sizeof(info), None):
        raise ctypes.WinError(ctypes.get_last_error())
    return True, int(info.Basic.LimitFlags)


def own_policy() -> str:
    """The word for the job this process is in: `none`, `breakaway` or `kill_on_close`."""
    if os.name != "nt":
        return "none"
    try:
        return policy_of(*read_own_job())
    except OSError:
        return "kill_on_close"
