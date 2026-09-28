"""A compact, read-only picture of this run's processes and the host's TCP sockets.

It exists for one unexplained class: Chromium's ``connect failed: 10055``
(``ERR_NO_BUFFER_SPACE``) on a Windows runner, CI run 36258690638, in a
fixture's navigation before any check of the page ran. Who held the missing
resource is not known, so the gate's records say what THIS run held -- its
pytest, Playwright driver and Chromium processes with their handles, threads,
memory and pool charge, and their sockets by state -- beside what the host held
overall: at the failure, before teardown, and at the module's two boundaries.

Nothing here changes a setting, raises a limit, waits between tests or ends a
process. Names, ids, counts and ports only: no argv, no environment, no
headers. Processes and sockets are read on Windows; elsewhere the picture says
so. A part that cannot be read records its error in its own place, and nothing
here ever raises into the gate.
"""
from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

#: The one child this reads through; a picture is taken, never waited for.
NETSTAT_TIMEOUT = 10.0
#: Pictures taken at failures, per process. A cascade of red tests in one module then
#: costs at most this many bounded reads, and the first failures carry the picture.
FAILURE_PICTURES = 3
_TAKEN = {"failures": 0}
#: FILETIME counts 100 ns from 1601; the Unix epoch is this many of them later.
_EPOCH_AS_FILETIME = 116_444_736_000_000_000
_LOOPBACK_PORT = re.compile(r"(?:127\.0\.0\.1|localhost|\[::1\]):(\d{1,5})")
_MB = 1024 * 1024

if sys.platform == "win32":
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _QUERY = 0x1000                      # PROCESS_QUERY_LIMITED_INFORMATION
    _SNAP_PROCESSES = 0x2                # TH32CS_SNAPPROCESS

    class _Entry(ctypes.Structure):      # PROCESSENTRY32W
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    class _Memory(ctypes.Structure):     # PROCESS_MEMORY_COUNTERS
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    class _Performance(ctypes.Structure):  # PERFORMANCE_INFORMATION
        _fields_ = [("cb", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal",
                "PhysicalAvailable", "SystemCache", "KernelTotal", "KernelPaged",
                "KernelNonpaged", "PageSize")] + [
            ("HandleCount", wintypes.DWORD), ("ProcessCount", wintypes.DWORD),
            ("ThreadCount", wintypes.DWORD)]

    _KERNEL32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _KERNEL32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    for _walk in (_KERNEL32.Process32FirstW, _KERNEL32.Process32NextW):
        _walk.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entry)]
    _KERNEL32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
        ctypes.POINTER(wintypes.FILETIME)] * 4
    _KERNEL32.GetProcessHandleCount.argtypes = [wintypes.HANDLE,
                                                ctypes.POINTER(wintypes.DWORD)]
    _KERNEL32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Memory),
                                                  wintypes.DWORD]
    _KERNEL32.K32GetPerformanceInfo.argtypes = [ctypes.POINTER(_Performance), wintypes.DWORD]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _guarded(read: Callable[..., Any], *args: Any) -> Any:
    """A part of the picture, or the error that kept it out -- never a raise."""
    try:
        return read(*args)
    except Exception as error:  # noqa: BLE001 -- one missing part must not cost the rest
        return {"error": repr(error)[:300]}


def _process_table() -> dict[int, dict[str, object]]:
    """Every process: id, parent, executable name and thread count (Toolhelp32)."""
    handle = _KERNEL32.CreateToolhelp32Snapshot(_SNAP_PROCESSES, 0)
    if handle in (None, ctypes.c_void_p(-1).value):
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot")
    table: dict[int, dict[str, object]] = {}
    try:
        entry = _Entry()
        entry.dwSize = ctypes.sizeof(_Entry)
        found = _KERNEL32.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            table[entry.th32ProcessID] = {
                "pid": entry.th32ProcessID, "ppid": entry.th32ParentProcessID,
                "name": entry.szExeFile, "threads": entry.cntThreads}
            found = _KERNEL32.Process32NextW(handle, ctypes.byref(entry))
    finally:
        _KERNEL32.CloseHandle(handle)
    return table


def _details(pid: int) -> dict[str, object]:
    """Creation time, handles, working set and pool charge of one process."""
    handle = _KERNEL32.OpenProcess(_QUERY, False, pid)
    if not handle:
        return {"open_error": ctypes.get_last_error()}
    try:
        created, spare = wintypes.FILETIME(), wintypes.FILETIME()
        facts: dict[str, object] = {}
        if _KERNEL32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(spare),
                                     ctypes.byref(spare), ctypes.byref(spare)):
            ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
            facts["created_ft"] = ticks
            facts["created"] = datetime.fromtimestamp(
                (ticks - _EPOCH_AS_FILETIME) / 1e7, timezone.utc).isoformat(
                    timespec="milliseconds")
        count = wintypes.DWORD()
        if _KERNEL32.GetProcessHandleCount(handle, ctypes.byref(count)):
            facts["handles"] = count.value
        memory = _Memory()
        memory.cb = ctypes.sizeof(_Memory)
        if _KERNEL32.K32GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
            facts["working_set_mb"] = round(memory.WorkingSetSize / _MB, 1)
            facts["nonpaged_pool_kb"] = memory.QuotaNonPagedPoolUsage // 1024
        return facts
    finally:
        _KERNEL32.CloseHandle(handle)


def _this_run(table: dict[int, dict[str, object]], root: int) -> list[dict[str, object]]:
    """This pytest and every descendant, a child admitted only if born after its parent.

    A parent id is only a number: Windows reuses it, so a process whose recorded parent
    is a LATER process of the same id is someone else's child, not this run's.
    """
    chosen = [{**table.get(root, {"pid": root}), **_details(root)}]
    frontier, seen = [chosen[0]], {root}
    while frontier:
        parent = frontier.pop()
        for row in table.values():
            if row["ppid"] != parent["pid"] or row["pid"] in seen:
                continue
            seen.add(row["pid"])
            child = {**row, **_details(int(row["pid"]))}
            if child.get("created_ft", 0) < parent.get("created_ft", 0):
                continue
            chosen.append(child)
            frontier.append(child)
    for row in chosen:
        row.pop("created_ft", None)
    return chosen


def _system() -> dict[str, object]:
    """The host's totals, to set this run's share against (GetPerformanceInfo)."""
    facts = _Performance()
    facts.cb = ctypes.sizeof(_Performance)
    if not _KERNEL32.K32GetPerformanceInfo(ctypes.byref(facts), facts.cb):
        raise OSError(ctypes.get_last_error(), "GetPerformanceInfo")
    page = facts.PageSize
    return {"processes": facts.ProcessCount, "threads": facts.ThreadCount,
            "handles": facts.HandleCount,
            "kernel_nonpaged_mb": round(facts.KernelNonpaged * page / _MB, 1),
            "commit_mb": round(facts.CommitTotal * page / _MB),
            "commit_limit_mb": round(facts.CommitLimit * page / _MB),
            "physical_available_mb": round(facts.PhysicalAvailable * page / _MB)}


def _port(address: str) -> int | None:
    tail = address.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else None


def parse_netstat(text: str) -> list[dict[str, object]]:
    """TCP rows of ``netstat -ano``: local, remote, state, ports and owning pid.

    The state is kept as printed, which a localized host translates (in words that may
    be more than one); a listener is therefore recognised by its unspecified remote
    end, not by the word.
    """
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "TCP" or not parts[-1].isdigit():
            continue
        _proto, local, remote, *state, pid = parts
        rows.append({"local": local, "remote": remote, "state": " ".join(state),
                     "pid": int(pid),
                     "local_port": _port(local), "remote_port": _port(remote),
                     "listening": remote in ("0.0.0.0:0", "[::]:0")})
    return rows


def tcp_summary(rows: list[dict[str, object]], ports: Iterable[int],
                run: Iterable[int], names: dict[int, str]) -> dict[str, object]:
    """Sockets by state for the host, for loopback, for this run, and at the named ports."""
    run = set(run)
    mine: dict[str, Counter] = {}
    for row in rows:
        if row["pid"] in run:
            mine.setdefault(str(row["pid"]), Counter())[row["state"]] += 1
    at_ports = {}
    for port in sorted(set(ports)):
        touching = [row for row in rows if port in (row["local_port"], row["remote_port"])]
        at_ports[str(port)] = {
            "listeners": sorted({row["pid"] for row in touching
                                 if row["listening"] and row["local_port"] == port}),
            "by_state": dict(Counter(row["state"] for row in touching)),
            "owners": dict(Counter(str(row["pid"]) for row in touching))}
    owners = Counter(row["pid"] for row in rows)
    return {"total": len(rows),
            "by_state": dict(Counter(row["state"] for row in rows)),
            "loopback_by_state": dict(Counter(
                row["state"] for row in rows
                if str(row["local"]).startswith(("127.", "[::1]")))),
            "this_run": {pid: dict(states) for pid, states in mine.items()},
            "ports": at_ports,
            "top_owners": [[pid, names.get(pid, "?"), count]
                           for pid, count in owners.most_common(5)]}


def _netstat() -> list[dict[str, object]]:
    # The system's own copy by full path: a bare name is looked up in the working
    # directory first.
    tool = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "netstat.exe"
    completed = subprocess.run([str(tool), "-ano"], capture_output=True, encoding="oem",
                               errors="replace", timeout=NETSTAT_TIMEOUT, check=False)
    return parse_netstat(completed.stdout)


def snapshot(ports: Iterable[int] = ()) -> dict[str, object]:
    """The picture: this run's processes, the host's totals and its TCP sockets."""
    began = time.monotonic()
    picture: dict[str, object] = {"time": _now(), "pytest_pid": os.getpid(),
                                  "platform": sys.platform}
    if sys.platform != "win32":
        picture["host"] = f"processes and sockets are read on Windows only, not {sys.platform}"
        return picture
    picture["system"] = _guarded(_system)
    table = _guarded(_process_table)
    if "error" in table:
        picture["this_run"], table = table, {}
    else:
        picture["this_run"] = _guarded(_this_run, table, os.getpid())
    run = [row["pid"] for row in picture["this_run"]] \
        if isinstance(picture["this_run"], list) else [os.getpid()]
    names = {pid: str(row["name"]) for pid, row in table.items()}
    rows = _guarded(_netstat)
    picture["tcp"] = rows if isinstance(rows, dict) else _guarded(
        tcp_summary, rows, ports, run, names)
    picture["seconds"] = round(time.monotonic() - began, 3)
    return picture


def loopback_ports(values: Iterable[object], said: str) -> list[int]:
    """The loopback ports a failing test was talking to: its fixtures' URLs and its pages' words."""
    text = "\n".join([said, *(value for value in values if isinstance(value, str))])
    return sorted({int(port) for port in _LOOPBACK_PORT.findall(text)})


def _contexts(contexts: Iterable[object]) -> list[dict[str, object]]:
    rows = []
    for context in contexts:
        pages = list(getattr(context, "pages", None) or [])
        rows.append({"pages": len(pages),
                     "open_pages": sum(1 for page in pages if not page.is_closed()),
                     "urls": [str(getattr(page, "url", "?"))[:200] for page in pages]})
    return rows


def failure_section(funcargs: dict[str, object], said: str, contexts: list[object]) -> str:
    """The picture at a setup or call failure, as text for the end of its record."""
    if _TAKEN["failures"] >= FAILURE_PICTURES:
        return (f"host snapshot skipped: {FAILURE_PICTURES} failures in this process "
                "already carry one\n")
    _TAKEN["failures"] += 1
    ports = loopback_ports(funcargs.values(), said)
    picture = snapshot(ports)
    picture["loopback_ports"] = ports
    picture["known_contexts"] = _guarded(_contexts, contexts)
    return ("host snapshot at the failure, before teardown:\n"
            + json.dumps(picture, indent=1, sort_keys=True) + "\n")


class ModuleBoundary:
    """One picture as the module's browser starts and one once it has closed."""

    def __init__(self, artifacts: str) -> None:
        current = os.environ.get("PYTEST_CURRENT_TEST", "")
        label = Path(current.split("::", 1)[0]).stem or f"pid{os.getpid()}"
        self._path = Path(artifacts) / "host" / f"{label}.json"
        self._start = _guarded(snapshot)

    def finish(self, *, contexts_left: int, reaped: dict[str, object]) -> None:
        """Write both pictures, with what the module left open and what its reaper met."""
        try:
            record = {"start": self._start, "end": _guarded(snapshot),
                      "contexts_left_at_close": contexts_left, "reaped": reaped}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(record, indent=1, sort_keys=True),
                                  encoding="utf-8")
        except Exception as error:  # noqa: BLE001 -- a picture never stops the gate
            sys.stderr.write(f"host snapshot not written to {self._path}: {error!r}\n")
