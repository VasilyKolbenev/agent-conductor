"""A durable probe of the boot witness, for the owner to run around an OS state change.

    python -m conductor.boot_probe --log <file> --label "before restart"

Each run appends one canonical JSON line to the log and prints the same line. The line carries the
witness the product would record, the old class-90 string, the time facts of the OS and how this
boot relates to the previous line of the log (`restart_proven`, `same_boot`, or the refusal code).
It reads the OS, writes only the log, needs no privilege and never touches a project or a login.
The diagnostics (times, the process telemetry boot id, the Fast Startup setting) explain a result;
none of them is ever an authority for a recovery.

Exit code: 0 recorded, 2 the log cannot be written, 3 recorded but the reader refused.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import struct
import sys

from . import boot_kuser, boot_witness
from .boot_witness import BootRefused

_FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
_TELEMETRY_CLASS = 64
_TELEMETRY_BOOT_ID_OFFSET = 60


def read_witness() -> str:
    """The witness the product would record now (a typed refusal if it cannot be read)."""
    return boot_kuser.current_witness()


def legacy_identity() -> str | None:
    """The old `windows:<uuid>` string, kept in the log for comparison with earlier facts."""
    if os.name != "nt":
        return None
    from .ownership_native import boot_identity
    try:
        return boot_identity()
    except OSError:
        return None


def _filetime(value: int) -> str:
    moment = _FILETIME_EPOCH + timedelta(microseconds=value // 10)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _kernel():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetTickCount64.restype = ctypes.c_ulonglong
    kernel.QueryUnbiasedInterruptTime.argtypes = [ctypes.POINTER(ctypes.c_ulonglong)]
    kernel.QueryUnbiasedInterruptTime.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    return kernel


def _times() -> dict:
    import ctypes
    kernel = _kernel()
    unbiased = ctypes.c_ulonglong(0)
    ticks = int(kernel.GetTickCount64())
    ok = kernel.QueryUnbiasedInterruptTime(ctypes.byref(unbiased))
    now = datetime.now(timezone.utc)
    return {"tick_ms": ticks, "unbiased_ms": int(unbiased.value // 10_000) if ok else None,
            "boot_time_estimate_utc": (now - timedelta(milliseconds=ticks)).isoformat()}


def _ntdll_call(name: str, argtypes: list):
    import ctypes
    from ctypes import wintypes
    call = getattr(ctypes.WinDLL("ntdll"), name)
    call.argtypes, call.restype = argtypes, wintypes.LONG
    return call


def _system_boot_time() -> str | None:
    import ctypes
    from ctypes import wintypes
    call = _ntdll_call("NtQuerySystemInformation",
                       [ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p])
    data = ctypes.create_string_buffer(48)
    if call(3, data, len(data), None) != 0:
        return None
    return _filetime(struct.unpack_from("<Q", data.raw, 0)[0])


def _telemetry_boot_id() -> int | None:
    import ctypes
    from ctypes import wintypes
    call = _ntdll_call("NtQueryInformationProcess", [wintypes.HANDLE, ctypes.c_int,
                       ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p])
    data = ctypes.create_string_buffer(4096)
    if call(_kernel().GetCurrentProcess(), _TELEMETRY_CLASS, data, len(data), None) != 0:
        return None
    if struct.unpack_from("<I", data.raw, 4)[0] != os.getpid():
        return None
    return struct.unpack_from("<I", data.raw, _TELEMETRY_BOOT_ID_OFFSET)[0]


def _fast_startup() -> int | None:
    import winreg
    path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Power"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
            return int(winreg.QueryValueEx(key, "HiberbootEnabled")[0])
    except OSError:
        return None


def _elevated() -> bool:
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def diagnostics() -> dict:
    """Explanatory facts of the OS, each `None` when it cannot be read. Never an authority."""
    if os.name != "nt":
        return {}
    found = {"elevated": _elevated(), "hiberboot_enabled": _fast_startup()}
    for name, read in (("times", _times), ("system_boot_time_utc", _system_boot_time),
                       ("process_telemetry_boot_id", _telemetry_boot_id)):
        try:
            value = read()
        except (OSError, AttributeError, ValueError, struct.error):
            value = None
        if name == "times":
            found.update(value or {"tick_ms": None, "unbiased_ms": None})
        else:
            found[name] = value
    return found


def _last_line(path: str) -> bytes | None:
    try:
        with open(path, "rb") as stream:
            rows = [row for row in stream.read().splitlines() if row.strip()]
    except FileNotFoundError:
        return None
    return rows[-1] if rows else None


def _relation(previous: bytes | None, current: str | None) -> str:
    if current is None:
        return "unmeasured"
    if previous is None:
        return "first_record"
    try:
        before = json.loads(previous)["boot_witness"]
    except (ValueError, KeyError, TypeError):
        return "previous_unreadable"
    if before is None:
        return "previous_unmeasured"
    try:
        boot_witness.prove_restart(before, current)
    except BootRefused as error:
        return error.code
    return "restart_proven"


def collect(label: str, previous: bytes | None) -> dict:
    """One measurement: the record that will be appended."""
    witness, error = None, None
    try:
        witness = read_witness()
    except BootRefused as refused:
        error = {"code": refused.code, "detail": refused.detail}
    parsed = boot_witness.parse(witness) if witness is not None else None
    return {"taken_at": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
            "label": label, "boot_witness": witness,
            "boot_counter": None if parsed is None else parsed.counter,
            "environment_guid": None if parsed is None else parsed.scope,
            "legacy_boot_identity": legacy_identity(), "diagnostics": diagnostics(),
            "error": error, "relation_to_previous": _relation(previous, witness)}


def _canonical(record: dict) -> bytes:
    text = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8") + b"\n"


def _append(path: str, line: bytes) -> None:
    with open(path, "ab+") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() > 0:
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b"\n":
                stream.write(b"\n")
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    """Take one measurement and append it to `--log`."""
    parser = argparse.ArgumentParser(prog="python -m conductor.boot_probe", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", required=True, help="the file the line is appended to")
    parser.add_argument("--label", default="", help="what is about to happen or just happened")
    args = parser.parse_args(argv)
    folder = os.path.dirname(os.path.abspath(args.log))
    if not os.path.isdir(folder):
        sys.stderr.write(f"boot_probe: the directory of the log does not exist: {folder}\n")
        return 2
    record = collect(args.label, _last_line(args.log))
    line = _canonical(record)
    try:
        _append(args.log, line)
    except OSError as error:
        sys.stderr.write(f"boot_probe: the log cannot be written: {error}\n")
        return 2
    sys.stdout.write(line.decode("utf-8"))
    return 3 if record["error"] is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
