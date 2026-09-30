"""A process is told by its pid AND the moment it started (spec 4.1.4).

A pid alone is not an identity: the OS hands a pid out again, and a launcher redirector makes
two or three processes of one child. The pair `(pid, process_started)` is what a child writes
into its status file and what the hub asks about later. `started_of` spells the start of a
running process in one string per OS:

- Windows: `windows:<creation time>` (`GetProcessTimes`, the 64-bit FILETIME);
- Linux: `linux:<boot id>:<starttime>` (field 22 of `/proc/<pid>/stat`, in clock ticks since
  boot, with the boot id so that a rebooted machine never matches);
- macOS: `darwin:<seconds>.<microseconds>` (`proc_pidinfo(PROC_PIDTBSDINFO)`).

A process that has exited has no identity even if its entry lingers (a zombie not yet reaped,
a handle somebody still holds), so `started_of` answers `None` for it. `probe` turns a
recorded pair into `alive`, `dead` or `unproven`: a pid that reads another start, or none, is
dead; a pid with nothing recorded against it is dead only when nothing runs there, and never
proven alive, so no caller may take a `null` start for a closed process.
"""
from __future__ import annotations

import errno
import functools
import os
import struct
import sys
from pathlib import Path
from typing import Literal

Liveness = Literal["alive", "dead", "unproven"]

#: `sizeof(struct proc_bsdinfo)`, and where the record keeps its status and start time.
BSDINFO_SIZE = 136
_STATUS_AT, _START_AT = 4, 120
_SZOMB = 5
_PROC_PIDTBSDINFO = 3
_ERROR_INVALID_PARAMETER = 87            # OpenProcess: no process has this pid
_QUERY_LIMITED, _SYNCHRONIZE, _WAIT_OBJECT_0 = 0x1000, 0x00100000, 0


class IdentityUnreadable(OSError):
    """A process exists (or may) and its start cannot be read: nothing is proven either way."""


def _checked(pid: object) -> int:
    if type(pid) is not int or not 1 <= pid < 2**31:
        raise ValueError(f"pid must be an integer from 1 to {2**31 - 1}, not {pid!r}")
    return pid


def started_of(pid: int) -> str | None:
    """The spelled start of the running process `pid`, or `None` when no such process runs.

    Raises:
        ValueError: `pid` cannot be a pid.
        IdentityUnreadable: The process may exist and the OS would not say when it started.
    """
    checked = _checked(pid)
    if os.name == "nt":
        return _windows_started(checked)
    if sys.platform == "darwin":
        return _darwin_started(checked)
    if sys.platform.startswith("linux"):
        return _linux_started(checked)
    raise IdentityUnreadable(f"no process identity is defined for {sys.platform}")


def current() -> str:
    """The spelled start of this process: what a child writes into its status file.

    Raises:
        IdentityUnreadable: The OS would not say.
    """
    found = started_of(os.getpid())
    if found is None:
        raise IdentityUnreadable("this process cannot find itself")
    return found


def probe(pid: int, started: str | None) -> Liveness:
    """Whether the process recorded as `(pid, started)` still runs.

    Returns:
        `alive` when the pid reads exactly that start; `dead` when it reads another or none;
        for a `started` of `None`, `dead` when nothing runs at the pid and `unproven` when
        something does; `unproven` also when the OS would not say.
    """
    try:
        found = started_of(pid)
    except IdentityUnreadable:
        return "unproven"
    if started is None:
        return "dead" if found is None else "unproven"
    return "alive" if found == started else "dead"


# -- Linux -----------------------------------------------------------------------------


def parse_proc_stat(text: str) -> tuple[str, str]:
    """`(state, starttime)` of a `/proc/<pid>/stat` line.

    The name in brackets may hold spaces and brackets of its own, so the fields are counted
    from the LAST closing bracket: state is field 3 and starttime is field 22.

    Raises:
        IdentityUnreadable: The line is not one.
    """
    close = text.rfind(")")
    fields = text[close + 1:].split() if close != -1 and text.lstrip().find("(") != -1 else []
    if len(fields) < 20 or not fields[19].isdigit():
        raise IdentityUnreadable("a /proc stat line has no start time")
    return fields[0], fields[19]


def started_from_proc(state: str, starttime: str, boot: str) -> str | None:
    """The Linux spelling, or `None` for a process that is a zombie or dead."""
    if state in ("Z", "X", "x"):
        return None
    return f"linux:{boot}:{starttime}"


@functools.cache
def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
    except OSError as error:
        raise IdentityUnreadable(f"the boot id cannot be read: {error}") from error


def _linux_started(pid: int) -> str | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, ProcessLookupError):
        return None
    except OSError as error:
        raise IdentityUnreadable(f"/proc/{pid}/stat cannot be read: {error}") from error
    state, starttime = parse_proc_stat(text)
    return started_from_proc(state, starttime, _boot_id())


# -- macOS -----------------------------------------------------------------------------


def parse_bsdinfo(buffer: bytes) -> tuple[str, bool]:
    """`(spelling, is_zombie)` of a `struct proc_bsdinfo`.

    Raises:
        IdentityUnreadable: The record is not `BSDINFO_SIZE` bytes.
    """
    if len(buffer) != BSDINFO_SIZE:
        raise IdentityUnreadable(f"a proc_bsdinfo record is {BSDINFO_SIZE} bytes, not "
                                 f"{len(buffer)}")
    status = struct.unpack_from("I", buffer, _STATUS_AT)[0]
    seconds, micros = struct.unpack_from("QQ", buffer, _START_AT)
    return f"darwin:{seconds}.{micros:06d}", status == _SZOMB


def _darwin_started(pid: int) -> str | None:
    import ctypes
    libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    libproc.proc_pidinfo.restype = ctypes.c_int
    libproc.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                     ctypes.c_void_p, ctypes.c_int]
    buffer = ctypes.create_string_buffer(BSDINFO_SIZE)
    got = libproc.proc_pidinfo(pid, _PROC_PIDTBSDINFO, 0, buffer, BSDINFO_SIZE)
    if got <= 0:
        found = ctypes.get_errno()
        if found == errno.ESRCH:
            return None
        raise IdentityUnreadable(f"proc_pidinfo({pid}) failed with errno {found}")
    spelled, zombie = parse_bsdinfo(buffer.raw[:got])
    return None if zombie else spelled


# -- Windows ---------------------------------------------------------------------------


@functools.cache
def _kernel32():
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.GetProcessTimes.restype = wintypes.BOOL
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    return k32


def _windows_started(pid: int) -> str | None:
    import ctypes
    from ctypes import wintypes
    k32 = _kernel32()
    handle = k32.OpenProcess(_QUERY_LIMITED | _SYNCHRONIZE, False, pid)
    if not handle:
        found = ctypes.get_last_error()
        if found == _ERROR_INVALID_PARAMETER:
            return None
        raise IdentityUnreadable(f"process {pid} cannot be opened (error {found})")
    try:
        if k32.WaitForSingleObject(handle, 0) == _WAIT_OBJECT_0:
            return None                          # it has exited; a handle keeps its entry
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not k32.GetProcessTimes(handle, *(ctypes.byref(t) for t in
                                             (created, exited, kernel, user))):
            raise IdentityUnreadable(f"the times of process {pid} cannot be read")
        return f"windows:{(created.dwHighDateTime << 32) | created.dwLowDateTime}"
    finally:
        k32.CloseHandle(handle)
