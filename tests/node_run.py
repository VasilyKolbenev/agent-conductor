"""Run Node for a test as `subprocess.run` would, and when it times out say what state it was in.

CI run 43 failed once with a bare `TimeoutExpired`: a Node call from `tests/desk_wizard_node.py`
had not ended in 30 s, and the log held nothing to tell why. `run_node` keeps everything the
verdict rests on exactly as it was -- the arguments, the deadline, one attempt, the same
exception -- and only adds text: notes on that exception, read before the process is killed, and
a `UserWarning` for a call that passed but was slow. It states facts and never guesses a cause.

Standard library only; it writes no file and reads no environment variable. The notes are for
a person reading a red CI log, so every fact is one line.
"""
from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import sys
import threading
import time
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

#: How long the output is collected after the kill before another process holding the pipes is
#: given up on; how long one question put to the OS may take; the length from which a call that
#: passed is reported; how many such reports one process gives.
DRAIN_AFTER_KILL = 10.0
QUERY_TIMEOUT = 5.0
SLOW_CALL = 2.0
SLOW_WARNINGS = 10

#: What this process has seen: Node calls made, when the last one ended, warnings given.
_state: dict = {"calls": 0, "last_end": None, "warned": 0}
#: Windows background work that can slow a fresh process down.
_SUSPECTS = ("msmpeng.exe", "mpcmdrun.exe", "mpdefendercoreservice.exe", "tiworker.exe",
             "trustedinstaller.exe", "searchindexer.exe", "compattelrunner.exe", "msiexec.exe")
_STILL_ACTIVE = 259
_NOT_DIGITS = re.compile(r"\D")


@dataclass
class _Call:
    """What is known about one call before it has a verdict."""

    index: int
    gap: float | None  # seconds since the previous call of this process ended
    utc: str
    uptime: str
    began: float = 0.0  # `perf_counter` just before the spawn
    spawned: float = 0.0  # and just after it

    @property
    def spawn(self) -> float:
        return self.spawned - self.began

    def started(self) -> str:
        return f"started {self.utc} UTC at uptime {self.uptime} s"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _uptime() -> str:
    """Seconds since the machine booted; `monotonic()` on Windows counts from there."""
    try:
        if sys.platform == "win32":
            import ctypes

            tick = ctypes.WinDLL("kernel32").GetTickCount64
            tick.restype = ctypes.c_ulonglong
            return f"{tick() / 1000:.3f}"
        with open("/proc/uptime", encoding="ascii") as handle:
            return f"{float(handle.read().split()[0]):.3f}"
    except Exception:  # noqa: BLE001 - a fact that cannot be read is named, never raised
        return "unknown"


def _windows_profile(pid: int) -> str:
    """The process as the OS counts it: alive or not, CPU, memory, handles, page faults."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD),
                    ("peak_ws", ctypes.c_size_t), ("ws", ctypes.c_size_t)] + [
                        (f"quota_{n}", ctypes.c_size_t) for n in range(6)]

    k32, pointer = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.POINTER
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [pointer(wintypes.FILETIME)] * 4
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, pointer(wintypes.DWORD)]
    k32.GetProcessHandleCount.argtypes = [wintypes.HANDLE, pointer(wintypes.DWORD)]
    k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, pointer(Counters), wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    def check(result: int) -> None:
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    handle = k32.OpenProcess(0x1000 | 0x0010, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
    check(handle)
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        code, count, memory = wintypes.DWORD(), wintypes.DWORD(), Counters()
        memory.cb = ctypes.sizeof(Counters)
        check(k32.GetProcessTimes(handle, *times))
        check(k32.GetExitCodeProcess(handle, ctypes.byref(code)))
        check(k32.GetProcessHandleCount(handle, ctypes.byref(count)))
        check(k32.K32GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb))
    finally:
        k32.CloseHandle(handle)
    kernel, user = [((t.dwHighDateTime << 32) | t.dwLowDateTime) / 1e7 for t in times[2:]]
    state = "alive" if code.value == _STILL_ACTIVE else f"exited with {code.value}"
    return (f"{state}; cpu user {user:.3f} s, kernel {kernel:.3f} s; working set "
            f"{memory.ws / 2**20:.1f} MB (peak {memory.peak_ws / 2**20:.1f}); handles "
            f"{count.value}; page faults {memory.faults}")


def _profile(proc: subprocess.Popen) -> str:
    if sys.platform == "win32":
        return _windows_profile(proc.pid)
    return f"poll() = {proc.poll()}"


def _parse_tasklist(text: str) -> list[list[str]]:
    """`tasklist /FO CSV /NH`: image, pid, session name, session number, memory."""
    return [row for row in csv.reader(io.StringIO(text)) if len(row) >= 5]


def _parse_ps(text: str) -> list[list[str]]:
    """`ps -A -o pid=,ppid=,stat=,time=,rss=,comm=`: one six-field row per process."""
    return [row for row in (line.split(None, 5) for line in text.splitlines()) if len(row) == 6]


def _process_table() -> list[list[str]]:
    if sys.platform == "win32":
        argv, encoding, parse = ["tasklist", "/FO", "CSV", "/NH"], "oem", _parse_tasklist
    else:
        argv = ["ps", "-A", "-o", "pid=,ppid=,stat=,time=,rss=,comm="]
        encoding, parse = "utf-8", _parse_ps
    done = subprocess.run(argv, capture_output=True, text=True, encoding=encoding,
                          errors="replace", stdin=subprocess.DEVNULL, timeout=QUERY_TIMEOUT,
                          check=False)
    rows = parse(done.stdout)
    if not rows:
        raise RuntimeError(f"{argv[0]} listed nothing (rc {done.returncode})")
    return rows


def _kilobytes(cell: str) -> str:
    """Windows writes `47 488 K` with a no-break space: keep the digits only."""
    return f"{_NOT_DIGITS.sub('', cell)} K"


def _windows_table_notes(rows: list[list[str]], image: str) -> list[str]:
    same = [f"{row[1]} ({_kilobytes(row[4])})" for row in rows if row[0].lower() == image.lower()]
    seen = [f"{row[0]} {_kilobytes(row[4])}" for row in rows if row[0].lower() in _SUSPECTS]
    return [f"processes now: {len(rows)}; {image} alive: {len(same)} [{', '.join(same[:8])}]",
            f"background suspects: {', '.join(seen) if seen else 'none listed'}"]


def _posix_table_notes(rows: list[list[str]], pid: int, image: str) -> list[str]:
    same = [f"{row[0]} ({row[4]} K)" for row in rows if os.path.basename(row[5]) == image]
    mine = [" ".join(row) for row in rows if row[0] == str(pid)]
    return [f"processes now: {len(rows)}; {image} alive: {len(same)} [{', '.join(same[:8])}]",
            "the timed-out process (pid ppid stat time rss comm): "
            f"{mine[0] if mine else 'not listed'}"]


def _table_notes(proc: subprocess.Popen, image: str) -> list[str]:
    rows = _process_table()
    if sys.platform == "win32":
        return _windows_table_notes(rows, image)
    return _posix_table_notes(rows, proc.pid, image)


def _text(value: str | bytes | None) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value or ""


def _clip(value: str | bytes | None, head: int = 1500, tail: int = 500) -> str:
    text = _text(value)
    if len(text) <= head + tail:
        return repr(text)
    return f"{text[:head]!r} ... [{len(text) - head - tail} chars] ... {text[-tail:]!r}"


def _stdin_note(source: str) -> str:
    first = source.splitlines()[0][:200] if source.strip() else ""
    return (f"{len(source)} chars, {len(source.encode('utf-8', 'replace'))} bytes; "
            f"first line: {first!r}")


def _probe(executable: str) -> str:
    """Ask the same executable for its version: does Node start at all on this machine now?"""
    began = time.perf_counter()
    done = subprocess.run([executable, "--version"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                          timeout=QUERY_TIMEOUT, check=False)
    return (f"{(done.stdout or done.stderr).strip()!r} rc {done.returncode} in "
            f"{time.perf_counter() - began:.3f} s")


def _fact(notes: list[str], label: str, read: Callable[[], str | list[str]]) -> None:
    """One fact for the notes; one that cannot be read is named, not raised."""
    try:
        value = read()
    except Exception as exc:  # noqa: BLE001 - a broken question must not hide the timeout
        notes.append(f"{label}: unavailable ({type(exc).__name__}: {exc})")
        return
    notes.extend(value if isinstance(value, list) else [f"{label}: {value}"])


def _drain(exc: subprocess.TimeoutExpired, proc: subprocess.Popen) -> str:
    """Collect what the killed process wrote; a process holding its pipes is not waited for."""
    began = time.perf_counter()
    try:
        exc.stdout, exc.stderr = proc.communicate(timeout=DRAIN_AFTER_KILL)
    except subprocess.TimeoutExpired:
        # A reader thread still sits on the pipes: leaving them to `Popen.__exit__` to close
        # would wait for their holder, which is the very wait this note stands in for.
        proc.stdout = proc.stderr = None
        return (f"returncode {proc.poll()}; pipes still open after "
                f"{DRAIN_AFTER_KILL} s: another process holds them")
    return f"returncode {proc.returncode}; pipes closed in {time.perf_counter() - began:.3f} s"


def _stream_note(name: str, value: str | bytes | None) -> list[str]:
    return [f"{name} ({len(_text(value))} chars): {_clip(value)}"]


def _diagnose(exc: subprocess.TimeoutExpired, proc: subprocess.Popen, argv: list[str],
              source: str, call: _Call, notes: list[str]) -> None:
    """Fill `notes`: the process and the table are read first, then it is killed.

    Every fact that asks the OS or the process goes through `_fact`: on any system one that
    cannot be read leaves a line `<fact>: unavailable (<Type>: <text>)` and the rest follow.
    """
    waited, image = time.perf_counter() - call.spawned, os.path.basename(argv[0])
    notes.append(f"node-run: timed out after {exc.timeout} s; the deadline and the verdict are "
                 "unchanged, no retry")
    notes.append(f"call #{call.index} of this process" + (
        ": the first Node call of it" if call.gap is None else
        f"; the previous Node call ended {call.gap:.3f} s before this one"))
    notes.append(f"{call.started()}; spawn took {call.spawn:.3f} s; waited {waited:.3f} s")
    _fact(notes, "stdin", lambda: _stdin_note(source))
    _fact(notes, "at the deadline", lambda: _profile(proc))
    _fact(notes, "process table", lambda: _table_notes(proc, image))
    notes.append(f"threads in this Python: {threading.active_count()}")
    proc.kill()
    _fact(notes, "after kill", lambda: _drain(exc, proc))
    _fact(notes, "stdout", lambda: _stream_note("stdout", exc.stdout))
    _fact(notes, "stderr", lambda: _stream_note("stderr", exc.stderr))
    _fact(notes, f"{image} --version after the kill", lambda: _probe(argv[0]))


def _explain(exc: subprocess.TimeoutExpired, proc: subprocess.Popen, argv: list[str],
             source: str, call: _Call) -> None:
    """Attach the notes to `exc`; whatever goes wrong here, `exc` is still what gets raised."""
    notes: list[str] = []
    try:
        _diagnose(exc, proc, argv, source, call, notes)
    except Exception as broken:  # noqa: BLE001 - the diagnostics must never replace the timeout
        notes.append(f"node-run: the diagnostics failed: {type(broken).__name__}: {broken}")
    finally:
        if proc.poll() is None:
            proc.kill()
        for note in notes:
            exc.add_note(note)


def _report_slow(call: _Call, took: float) -> None:
    if took < SLOW_CALL or _state["warned"] >= SLOW_WARNINGS:
        return
    _state["warned"] += 1
    warnings.warn(f"node-run: a Node call took {took:.1f} s and passed (call #{call.index} of "
                  f"this process, {call.started()}, spawn {call.spawn:.3f} s)", UserWarning,
                  stacklevel=3)


def run_node(argv: list[str], source: str, *, timeout: float) -> subprocess.CompletedProcess[str]:
    """Run `argv` with `source` on stdin: `subprocess.run`'s answer, and its failure on a timeout.

    The result of a call that ends is `subprocess.run(argv, input=source, capture_output=True,
    text=True, encoding="utf-8", timeout=timeout, check=False)`'s. A call that does not end in
    `timeout` seconds raises that call's own `TimeoutExpired`, once, with the notes of
    `_diagnose` added; its output so far is in `stdout` and `stderr` as text.
    """
    _state["calls"] += 1
    ended = _state["last_end"]
    call = _Call(_state["calls"], None if ended is None else time.perf_counter() - ended,
                 _utc(), _uptime())
    call.began = time.perf_counter()
    try:
        with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, encoding="utf-8") as proc:
            call.spawned = time.perf_counter()
            try:
                out, err = proc.communicate(source, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _explain(exc, proc, argv, source, call)
                raise
            except BaseException:  # including KeyboardInterrupt, as `subprocess.run` does
                proc.kill()
                raise
            done = subprocess.CompletedProcess(proc.args, proc.poll(), out, err)
    finally:
        _state["last_end"] = time.perf_counter()
    _report_slow(call, _state["last_end"] - call.began)
    return done
