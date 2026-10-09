"""One built-in AFD ETW trace around one forward browser gate, on a CI runner.

The Windows gate has gone red with ``net::ERR_NO_BUFFER_SPACE`` (WSAENOBUFS,
10055) on a new loopback connect from Chromium to a module's own server, in
modules that change from run to run and never on Linux or macOS. Host
snapshots taken after the failure did not name the resource. The review ruling
of 07.10 allows exactly one more look: the built-in ``netsh trace`` with the one
provider ``Microsoft-Windows-Winsock-AFD`` at level 4, on a temporary runner,
around one forward order.

This wraps that order, and it never changes what the gate decides:

- the gate runs as a child with its own command line, and the child's exit
  code is this process's exit code, whatever happened to the trace;
- the trace starts only on a GitHub runner and only inside its temp (a
  developer's machine is never traced), only after the provider and every
  parameter it uses are found in netsh's own answers, and only when no other
  trace session is in progress: a session this did not start is never stopped;
- it stops at the first failure record line that reports 10055 -- Chromium's
  ERR_NO_BUFFER_SPACE on the page, or the Winsock error on a pytest ``E`` line
  -- while the circular file still holds the failing connect; at 45 minutes;
  or when the gate ends, whichever comes first;
- whatever is unavailable is written down as a gap, never filled in.

ONE attempt is the workflow's to keep: its switch (``AFD_TRACE`` in the browser
job) is true only on a Windows push of the integration branch, first run
attempt, whose head commit names that attempt. Every other run calls the gate
directly.

``--stop`` runs before the reversed order may start and stops the session if it
is still ours. ``--extract`` runs after both orders, so the reversed order starts
on the host state it always starts on: it decodes the file with the built-in
``tracerpt`` and keeps only the selected loopback events (``afd_extract``). The
raw trace stays in its own directory and is never published.

Usage:
    python -m browser_tests.gate_trace --trace-dir DIR --record DIR --watch DIR -- GATE...
    python -m browser_tests.gate_trace --stop --record DIR
    python -m browser_tests.gate_trace --extract --record DIR --watch DIR
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import logging
import os
import platform
import re
import secrets
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from browser_tests import afd_extract

LOG = logging.getLogger("browser-gate-trace")
PROVIDER = "Microsoft-Windows-Winsock-AFD"
PROVIDER_GUID = "e53c6823-7bb8-44bb-90dc-3f86090d48a6"
LEVEL = 4
#: The review ruling's collection settings, in netsh's own spelling, and no others.
PARAMETERS = ("capture=no", "report=disabled", "correlation=disabled", "persistent=no",
              "fileMode=circular", "maxSize=64")
#: Every parameter name the start command uses: each must be in netsh's own help.
NAMES = ("provider", "level", "traceFile", *(item.split("=")[0] for item in PARAMETERS))
MAX_SECONDS = 45 * 60
NO_SESSION = "no trace session currently in progress"
#: A status line naming a trace file at all: "Trace File:   <path>".
_OTHER_FILE = re.compile(r"^\s*trace file\s*:\s*\S", re.IGNORECASE | re.MULTILINE)
POLL_SECONDS = 1.0
NETSH_SECONDS = 120
STOP_SECONDS = 600
DECODE_SECONDS = 1800
CONFIG, STOP, STOP_AGAIN, BEFORE_REVERSE, BEFORE_DECODE, EXTRACT = (
    "trace-config.json", "trace-stop.json", "trace-stop-second.json",
    "trace-stop-before-reverse.json", "trace-stop-before-decode.json", "afd-extract.json")
WINDOWS = sys.platform == "win32"


@dataclass(frozen=True)
class Session:
    """The one trace session this started: its unique file and its deadline."""
    trace_file: Path
    deadline: float


def _tool(name: str) -> Path:
    """A built-in Windows tool by its absolute path, never by a PATH search."""
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / name


def _call(argv: list[str], timeout: float, cwd: Path | None = None) -> tuple[object, str]:
    """Run one tool and return its exit code and everything it said."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                              timeout=timeout, check=False, cwd=cwd)
    except subprocess.TimeoutExpired:
        return "timed-out", ""
    except OSError as error:
        return "not-started", f"{type(error).__name__}: {error}"
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def _netsh(*arguments: str, timeout: float = NETSH_SECONDS) -> tuple[object, str]:
    return _call([str(_tool("netsh.exe")), "trace", *arguments], timeout)


def _tail(text: str, lines: int = 20) -> list[str]:
    return [line for line in text.strip().splitlines() if line.strip()][-lines:]


def _now() -> str:
    """Now, in UTC with milliseconds, as the gate's requestfailed lines stamp it."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def _write(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read(path: Path) -> dict[str, object] | None:
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _identity() -> dict[str, object]:
    """What this trace was taken on. The Chromium version is the gate's own
    probe (versions.json), which the extract carries."""
    return {"sha": os.environ.get("GITHUB_SHA"), "ref": os.environ.get("GITHUB_REF"),
            "run": os.environ.get("GITHUB_RUN_ID"),
            "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "image": [os.environ.get("ImageOS"), os.environ.get("ImageVersion")],
            "windows": platform.platform(), "windows_version": platform.version(),
            "python": sys.version}


def _gap_before_start(trace_dir: Path) -> dict[str, object] | None:
    """Why the trace may not start here, or None when every check passed."""
    if not WINDOWS:
        return {"reason": "not-windows"}
    # A developer's machine is never traced: only a GitHub runner, in its own temp.
    runner_temp = os.environ.get("RUNNER_TEMP")
    if os.environ.get("GITHUB_ACTIONS") != "true" or not runner_temp:
        return {"reason": "not-a-ci-runner"}
    if not trace_dir.resolve().is_relative_to(Path(runner_temp).resolve()):
        return {"reason": "trace-dir-outside-runner-temp"}
    code, said = _netsh("show", "provider", PROVIDER)
    if PROVIDER_GUID not in said.lower():
        return {"reason": "provider-unknown", "exit": code, "said": _tail(said)}
    code, said = _netsh("start", "help")
    missing = [name for name in NAMES if f"{name.lower()}=" not in said.lower()]
    if missing:
        return {"reason": "parameter-unsupported", "missing": missing, "exit": code,
                "said": _tail(said, 60)}
    code, said = _netsh("show", "status")
    if NO_SESSION not in said.lower():
        return {"reason": "another-session-in-progress", "exit": code, "said": _tail(said)}
    return None


def start(trace_dir: Path, record: Path,
          clock: Callable[[], float] = time.monotonic) -> Session | None:
    """Start the one trace, or record why not.

    Once the start is sent, this answers for the session even when netsh's status
    could not confirm it: only a status that answers "no session" proves there is
    nothing to watch. A stop still needs netsh to name this file. The deadline
    counts from before the start, so a slow start never extends it.
    """
    config: dict[str, object] = {"provider": PROVIDER, "level": LEVEL,
                                 "parameters": list(PARAMETERS),
                                 "max_seconds": MAX_SECONDS, **_identity()}
    gap = _gap_before_start(trace_dir)
    if gap is not None:
        _write(record / CONFIG, {**config, "available": False, "gap": gap})
        return None
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_file = trace_dir.resolve() / f"afd-{secrets.token_hex(16)}.etl"
    arguments = ["start", f"provider={PROVIDER}", f"level={LEVEL}", *PARAMETERS,
                 f"traceFile={trace_file}"]
    config = {**config, "command": ["netsh", "trace", *arguments], "trace_file": str(trace_file)}
    # Written BEFORE the start: whatever fails after it, a stop knows the file.
    _write(record / CONFIG, {**config, "available": False, "gap": {"reason": "starting"}})
    deadline, sent_at = clock() + MAX_SECONDS, _now()
    code, said = _netsh(*arguments)
    status_code, status = _netsh("show", "status")
    config = {**config, "start_exit": code, "start_said": _tail(said), "start_sent_at": sent_at,
              "status_exit": status_code, "status": _tail(status)}
    absent = _not_running(status_code, status, trace_file)
    if absent is True:
        _write(record / CONFIG, {**config, "available": False, "gap": {"reason": "start-failed"}})
        return None
    if absent is False:
        _write(record / CONFIG, {**config, "available": True})
    else:  # sent and not confirmed: it may run, so it is watched as ours
        _write(record / CONFIG, {**config, "available": "unknown",
                                 "gap": {"reason": "start-unconfirmed"}})
    return Session(trace_file, deadline)


def _configured_file(record: Path) -> Path | None:
    config = _read(record / CONFIG) or {}
    return Path(str(config["trace_file"])) if config.get("trace_file") else None


def _start_or_stop(trace_dir: Path, record: Path) -> Session | None:
    """Start the trace; if starting broke after netsh may have begun, stop what is ours
    now, so no session runs past its deadline unwatched."""
    try:
        return start(trace_dir, record)
    except Exception:
        trace_file = _configured_file(record)
        if trace_file is not None:
            stop_own(trace_file, record, "start-broke", None)
        raise


def first_no_buffer(watch_dir: Path, seen: dict[str, int]) -> dict[str, str] | None:
    """The first failure record line that reports a 10055, if any.

    ``seen`` remembers each record's size, so a record is read again only after
    it grew: one read while it was still being written does not lose it.
    """
    for path in sorted(watch_dir.glob("*.failure.txt")):
        try:
            size = path.stat().st_size
            if seen.get(path.name) == size:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen[path.name] = size
        for line in text.splitlines():
            if afd_extract.names_10055(line):
                return {"record": path.name, "line": line.strip()[:300]}
    return None


def watch(child: subprocess.Popen[bytes], session: Session, watch_dir: Path,
          clock: Callable[[], float] = time.monotonic) -> tuple[str, dict[str, str] | None]:
    """Why to stop, and the record that said so. The end of the gate is read
    BEFORE the last look, so a record written just before it ended still counts."""
    seen: dict[str, int] = {}
    while True:
        ended = child.poll() is not None
        hit = first_no_buffer(watch_dir, seen)
        if hit is not None:
            return "first-no-buffer-space", hit
        if ended:
            return "gate-ended", None
        if clock() >= session.deadline:
            return "deadline", None
        time.sleep(POLL_SECONDS)


def _not_running(code: object, status: str, trace_file: Path) -> bool | None:
    """What netsh's status PROVES about this trace's session: True when it answered
    "no session", or answered 0 naming another trace file (one netsh session runs
    at a time, and this never starts a second); False when it names this file; None
    when it cannot say (no answer, or text it does not recognise)."""
    text = status.lower()
    if trace_file.name.lower() in text:
        return False
    if isinstance(code, int) and NO_SESSION in text:
        return True
    if code == 0 and _OTHER_FILE.search(status):
        return True
    return None


def stop_own(trace_file: Path, record: Path, reason: str,
             hit: dict[str, str] | None, name: str = STOP) -> dict[str, object]:
    """Stop the trace session only while netsh's status names this trace's file.

    The stop comes first, before anything that could fail on the way to the
    record. "stopped" means netsh's LAST answer proves the session is not
    running; a status that never answered proves nothing either way.
    """
    code, status = _netsh("show", "status")
    before = _not_running(code, status, trace_file)
    ours = before is False
    stop_code, said, after_code, after = None, "", code, status
    if ours:
        stop_code, said = _netsh("stop", timeout=STOP_SECONDS)
        after_code, after = _netsh("show", "status")
    absent = _not_running(after_code, after, trace_file)
    result: dict[str, object] = {
        "reason": reason, "hit": hit, "at": _now(), "ours_running": ours,
        "status_unknown": before is None, "stopped": absent is True,
        "last_status_unknown": absent is None, "last_status_exit": after_code}
    result = {**result, "stop_exit": stop_code, "stop_said": _tail(said)} if ours \
        else {**result, "status": _tail(status)}
    _write(record / name, result)
    LOG.info("AFD trace: %s (stop %s; proven gone: %s)", reason,
             "sent" if ours else "not sent", absent is True)
    return result


def _guarded(record: Path, function: Callable[..., object], *arguments: object) -> object:
    """A failure of the trace is a gap in its evidence, never a change to the gate."""
    try:
        return function(*arguments)
    except Exception as error:  # the gate's verdict must not depend on the trace
        LOG.exception("AFD trace: %s failed", function.__name__)
        with contextlib.suppress(OSError):
            _write(record / f"{function.__name__}-error.json",
                   {"error": type(error).__name__, "detail": str(error), "at": _now()})
        return None


def _trace_until_stop(child: subprocess.Popen[bytes], session: Session, record: Path,
                      watch_dir: Path, clock: Callable[[], float] = time.monotonic) -> None:
    """Watch, then stop. A stop netsh does not prove gets ONE more at the next
    boundary -- the deadline or the gate's end, whichever comes first."""
    reason, hit = "watch-failed", None
    try:
        reason, hit = watch(child, session, watch_dir)
    finally:
        first = stop_own(session.trace_file, record, reason, hit)
    if first["stopped"] is True:
        return
    while child.poll() is None and clock() < session.deadline:
        time.sleep(POLL_SECONDS)
    stop_own(session.trace_file, record, "second-stop", None, name=STOP_AGAIN)


def run(trace_dir: Path, record: Path, watch_dir: Path, gate: list[str]) -> int:
    """Run the gate once under the trace and answer with the gate's own exit code."""
    found = _guarded(record, _start_or_stop, trace_dir, record)
    session = found if isinstance(found, Session) else None
    try:
        child = subprocess.Popen(gate)
    except OSError:
        if session is not None:
            _guarded(record, stop_own, session.trace_file, record, "gate-not-started", None)
        raise
    if session is not None:
        _guarded(record, _trace_until_stop, child, session, record, watch_dir)
    return child.wait()


def decode(trace_file: Path, watch_dir: Path) -> dict[str, object]:
    """The selected events from the stopped trace, or the gap that prevents them."""
    if not trace_file.is_file():
        return {"decoded": False, "reason": "the trace file is missing"}
    xml = trace_file.with_suffix(".xml")
    argv = [str(_tool("tracerpt.exe")), str(trace_file), "-o", str(xml), "-of", "XML", "-y"]
    # Run beside the trace, so whatever the decoder writes lands there and never in the checkout.
    code, said = _call(argv, DECODE_SECONDS, cwd=trace_file.parent)
    decoder = {"command": ["tracerpt", trace_file.name, "-o", xml.name, "-of", "XML", "-y"],
               "exit": code, "said": _tail(said, 5)}
    if not xml.is_file():
        return {"decoded": False, "reason": "tracerpt wrote no output", "decoder": decoder}
    rows, total = afd_extract.failures(watch_dir)
    return {"decoder": decoder, **afd_extract.extract(
        xml, rows, total, _read(watch_dir / "versions.json"))}


def stop_step(record: Path) -> None:
    """Before the reversed order: stop the session if it is still ours. When netsh
    cannot prove it is gone, the record says the reversed order may have run traced."""
    trace_file = _configured_file(record)
    if trace_file is None:
        return
    result = stop_own(trace_file, record, "before-the-reversed-order", None,
                      name=BEFORE_REVERSE)
    if result["stopped"] is not True:
        _write(record / BEFORE_REVERSE, {**result, "limitation": (
            "netsh did not prove the session gone before the reversed order; that order "
            "may have run while it was still tracing")})


def _proven_gone(record: Path) -> bool:
    """Whether an earlier stop record already proved the session gone. It cannot
    come back: nothing here ever starts a second session."""
    return any((_read(record / name) or {}).get("stopped") is True
               for name in (STOP, STOP_AGAIN, BEFORE_REVERSE))


def extract_step(record: Path, watch_dir: Path) -> None:
    """After both orders: stop once more if still ours, then decode and select once.
    Only a session netsh proves gone is decoded; a possibly live file never is."""
    config = _read(record / CONFIG) or {}
    trace_file = _configured_file(record)
    before_reverse = _read(record / BEFORE_REVERSE)
    gap = config.get("gap") if isinstance(config.get("gap"), dict) else {}
    # "starting" was left by a start that broke after netsh may have begun: not "none".
    if trace_file is None or (config.get("available") is False
                              and gap.get("reason") != "starting"):
        _write(record / EXTRACT, {"decoded": False, "reason": "no trace was collected",
                                  "gap": config.get("gap")})
        return
    stopped = stop_own(trace_file, record, "before-decoding", None, name=BEFORE_DECODE)
    if stopped["stopped"] is not True and not _proven_gone(record):
        _write(record / EXTRACT, {"decoded": False, "reason":
                                  "the session may still run; a live file is not decoded",
                                  "before_reverse": before_reverse})
        return
    _write(record / EXTRACT, {**decode(trace_file, watch_dir), "start": config.get("available"),
                              "before_reverse": before_reverse})


def main(argv: list[str] | None = None) -> int:
    """CLI entry: run the gate under the trace, stop it, or read it."""
    arguments = sys.argv[1:] if argv is None else argv
    split = arguments.index("--") if "--" in arguments else len(arguments)
    own, gate = arguments[:split], arguments[split + 1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", type=Path, default=None,
                        help="where the raw trace is written; never published")
    parser.add_argument("--record", type=Path, required=True,
                        help="where the trace's own records and the extract go")
    parser.add_argument("--watch", type=Path, default=None,
                        help="the gate's artifacts directory, read for failure records")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--stop", action="store_true",
                      help="stop the session if it is still ours")
    mode.add_argument("--extract", action="store_true",
                      help="stop once more if still ours, then decode and select")
    parsed = parser.parse_args(own)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if (parsed.stop or parsed.extract) and gate:
        parser.error("--stop and --extract run no gate")
    if parsed.stop:
        _guarded(parsed.record, stop_step, parsed.record)
        return 0
    if parsed.watch is None:
        parser.error("a run and --extract need --watch")
    if parsed.extract:
        _guarded(parsed.record, extract_step, parsed.record, parsed.watch)
        return 0
    if not gate or parsed.trace_dir is None:
        parser.error("a run needs --trace-dir, and the gate's command after --")
    return run(parsed.trace_dir, parsed.record, parsed.watch, gate)


if __name__ == "__main__":
    raise SystemExit(main())
