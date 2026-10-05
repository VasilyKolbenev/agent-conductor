"""The browser release gate: one fresh process per module, no second chances.

The recurring Chromium flake (four sightings across ~20 suite runs, always a
single test, always green on an identical rerun) made the December Command
declare a plain ``pytest browser_tests`` run insufficient as a release gate.
This runner is the replacement discipline:

- every browser module runs in its OWN pytest process, so it gets its own
  Playwright driver and its own Chromium — a renderer dying under one module
  cannot poison the next, and the crash surface is one module wide;
- a module runs exactly once. There is no retry, no rerun flag, no xfail
  ladder and no statistical waiver anywhere in this file — a red module is a
  red gate, full stop. By default the gate stops at the first one; with
  ``--keep-going`` (what CI asks for) it runs every other module once as
  well, so one run names every ordinary failure, and a later green module
  never turns the verdict back to green. Every way a test
  can leave the count without passing is a waiver by another name: skipped,
  xfailed, xpassed and deselected all red the gate, because a marker applied
  dynamically in a conftest hook is invisible to any scan of test sources.
  Ambient pytest configuration is stripped from the child on all four of its
  channels — PYTEST_ADDOPTS and PYTEST_PLUGINS leave the environment,
  ``-o addopts=`` empties the project's own, and plugin autoload is
  disabled, so nothing outside this file can soften the command line;
- every module gets its OWN empty temporary root inside the artifacts
  directory, handed over with ``--basetemp`` and reused by nothing: the
  gate's verdict must not depend on the state or the permissions of the
  machine's shared temporary directory, and a module's temporary files must
  not outlive their process into the next one;
- every run leaves a record (module, exit code, duration, skip count, output
  tail, the engine versions) plus its full stderr with Playwright's browser
  channel logging (DEBUG=pw:browser*), ALWAYS — a green run's stderr is
  where a near-miss crash leaves its words. A failing run also leaves full
  stdout and the failing node ids, beside whatever screenshots and
  tracebacks the conftest evidence hook captured while the failing test's
  pages were still alive;
- a module that hangs is killed at a stated timeout and recorded as
  timed-out. Killing the pytest process does not prove its own children (a
  browser) are gone, so a timeout ends the order in every mode, keep-going
  included, and the report says the run is incomplete. So does a module
  process that ended with a code pytest never returns (a crash, a kill,
  ``os._exit``): it skipped the session teardown that closes the browser;
- the gate report keeps the run's progress apart from its verdict: the
  planned modules, those done, those remaining, whether the order completed,
  the failures so far and why it stopped. It is written before the first
  module and after every result, so even a killed gate leaves a report, and
  that report is never green unless every planned module ran and passed.
  ``--completed-report`` answers, from a report alone, whether that order ran
  to an ordinary end -- the condition CI puts on running the other order on
  the same runner.

Not a test module: pytest ignores it (no ``test_`` prefix), and the fast
suite pins its discipline in tests/test_browser_gate.py.

Usage:
    python -m browser_tests.gate [--reverse] [--keep-going] [--artifacts DIR]
                                 [--modules-dir DIR] [--skip-version-probe]
                                 [--module-timeout SECONDS]
    python -m browser_tests.gate --completed-report REPORT
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

LOG = logging.getLogger("browser-gate")
#: The whole node id from a -rEf summary line, without the trailing message —
#: a parametrized id may contain spaces, so this must not stop at the first.
_FAILED_NODE = re.compile(r"^(?:FAILED|ERROR) (.+?)(?:\s+-\s.*)?$", re.MULTILINE)
#: Every outcome that is a test not passing while the exit code stays 0.
#: A dynamic marker in a conftest hook leaves no trace in any test source,
#: so these counts — not a text scan — are what closes that door.
WAIVER_OUTCOMES = ("skipped", "xfailed", "xpassed", "deselected")
_WAIVERS = {name: re.compile(rf"(\d+) {name}") for name in WAIVER_OUTCOMES}
MODULE_TIMEOUT_SECONDS = 600
#: The codes a pytest process returns when it ends through pytest itself, read
#: from the pytest the modules run on (the gate launches them with this
#: interpreter). Any other code is a process that never reached its teardown.
PYTEST_EXIT_CODES = frozenset(int(code) for code in pytest.ExitCode)


def discover_modules(modules_dir: Path, reverse: bool) -> list[Path]:
    """Every browser test module, in a stated order — never a sampled subset."""
    modules = sorted(modules_dir.glob("test_*.py"))
    if not modules:
        raise SystemExit(f"no test modules found under {modules_dir}")
    return list(reversed(modules)) if reverse else modules


def chromium_log(artifacts: Path, name: str) -> Path:
    """Where Chromium must write its OWN log for one launch of this gate.

    Chromium logs without being asked to: an engine that hits a socket, a
    GPU or a profile error writes it to a file it picks itself, and on
    Windows that default sits beside the executable — a location shared by
    every gate run this machine has ever made and by every checkout on it.
    So the engine's account of a stalled context, which is exactly the
    evidence a red gate needs, ends up outside the run's artifacts, mixed
    with strangers, and outside what ``--artifacts`` promises to hold.

    The gate therefore NAMES the file instead of letting Chromium choose:
    an absolute path, inside the artifacts, one per launch. Absolute
    because neither a working directory nor an install location may decide
    where a gate's evidence lands; per launch because a shared file cannot
    say which module was speaking.
    """
    directory = artifacts / "chromium"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{name}.chromium.log"


def probe_versions(artifacts: Path) -> dict[str, str]:
    """Record the exact engine the gate ran on, once per gate."""
    from importlib.metadata import version

    from playwright.sync_api import sync_playwright

    # This launch happens in the GATE's own process, so no child environment
    # reaches it: it must be contained here or not at all.
    probe_environment = {**os.environ, "CHROME_LOG_FILE":
                         str(chromium_log(artifacts, "version-probe"))}
    with sync_playwright() as api:
        browser = api.chromium.launch(headless=True, env=probe_environment,
            args=[f"--log-file={probe_environment['CHROME_LOG_FILE']}"])
        try:
            versions = {"playwright": version("playwright"),
                        "chromium": browser.version,
                        "python": sys.version}
        finally:
            browser.close()
    (artifacts / "versions.json").write_text(
        json.dumps(versions, indent=2), encoding="utf-8")
    return versions


def _child_environment(artifacts: Path, repo: Path,
                       module: Path) -> dict[str, str]:
    """The child's world: evidence armed, ambient pytest channels stripped."""
    environment = dict(os.environ)
    environment["CONDUCT_GATE_ARTIFACTS"] = str(artifacts)
    environment["PYTHONPATH"] = str(repo / "src")
    environment["PYTHONIOENCODING"] = "utf-8"
    # The engine this child launches keeps its own log; the gate says where.
    environment["CHROME_LOG_FILE"] = str(chromium_log(artifacts, module.stem))
    # Playwright's browser channel: launch lines and Chromium's own stderr
    # land in the subprocess stderr, so a renderer crash leaves its words.
    environment["DEBUG"] = "pw:browser*"
    # Ambient configuration could append --collect-only or a rerun flag to
    # the pinned command line below; the gate listens to nobody but itself.
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTEST_PLUGINS", None)
    # And no third-party plugin loads itself into the run: the browser suite
    # asks for none (it builds its own Playwright fixture), so an installed
    # rerun or xfail-manipulating plugin has no way in.
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _own_basetemp(artifacts: Path, module: Path) -> Path:
    """A fresh, empty, gate-owned temporary root for one module process.

    Never the machine's shared temporary directory and never reused: a
    stale ACL or a neighbour's leftovers there once turned a trivially
    green module red, which would make the gate's verdict a fact about the
    host rather than about the code.
    """
    basetemp = artifacts / "basetemp" / module.stem
    if basetemp.exists():
        shutil.rmtree(basetemp, ignore_errors=True)
    basetemp.mkdir(parents=True)
    return basetemp


def run_module(module: Path, artifacts: Path, repo: Path,
               timeout: float) -> dict[str, object]:
    """Run one module once, in a fresh pytest/Chromium process."""
    module, artifacts, repo = (path.resolve() for path in (module, artifacts, repo))
    basetemp = _own_basetemp(artifacts, module)
    # GPU subprocesses can ignore CHROME_LOG_FILE. Keep their fallback logs
    # inside this module's artifacts too, outside pytest's replaceable basetemp.
    working = artifacts / "working" / module.stem
    working.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", str(module), "-q", "--tb=long",
             "-rEf", "-p", "no:cacheprovider", "-o", "addopts=",
             "--basetemp", str(basetemp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(working), env=_child_environment(artifacts, repo, module),
            timeout=timeout, check=False)
        exit_code: object = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as expired:
        exit_code = "timed-out"
        stdout = (expired.stdout or b"").decode("utf-8", "replace") \
            if isinstance(expired.stdout, bytes) else (expired.stdout or "")
        stderr = (expired.stderr or b"").decode("utf-8", "replace") \
            if isinstance(expired.stderr, bytes) else (expired.stderr or "")
    duration = round(time.monotonic() - started, 2)
    waivers = {name: int(found.group(1)) if (found := pattern.search(stdout))
               else 0 for name, pattern in _WAIVERS.items()}
    record = {
        "module": module.name,
        "exit_code": exit_code,
        "duration_seconds": duration,
        "basetemp": str(basetemp),
        "cwd": str(working),
        "failed_nodes": _FAILED_NODE.findall(stdout),
        "tail": stdout.strip().splitlines()[-1:],
        **waivers,
    }
    stem = artifacts / module.stem
    # stderr is recorded ALWAYS: a green run's browser channel is the
    # diagnostic corpus a crash-on-close flake leaves its near-misses in.
    stem.with_suffix(".stderr.txt").write_text(stderr, encoding="utf-8")
    if is_red(record):
        stem.with_suffix(".stdout.txt").write_text(stdout, encoding="utf-8")
    return record


def is_red(record: dict[str, object]) -> bool:
    """A module is red on any non-zero exit and on any waived outcome."""
    return record["exit_code"] != 0 or any(
        record[name] for name in WAIVER_OUTCOMES)


def gate_report(reverse: bool, keep_going: bool, planned: list[str],
                records: list[dict[str, object]], progress: str,
                stopped: dict[str, str] | None = None) -> dict[str, object]:
    """The report: the run's progress (running, stopped, complete) kept apart
    from its verdict. Green only when the order completed with no red module;
    any red module, or an order that stopped, is red; otherwise running."""
    done = [str(row["module"]) for row in records]
    failures = [str(row["module"]) for row in records if is_red(row)]
    if progress == "complete":
        result = "red" if failures else "green"
    else:
        result = "red" if failures or progress == "stopped" else "running"
    return {"order": "reverse" if reverse else "normal", "keep_going": keep_going,
            "result": result, "progress": progress, "complete": progress == "complete",
            "planned": planned, "done": done, "remaining": planned[len(done):],
            "failures": failures, "stopped": stopped, "records": records}


def _write_report(artifacts: Path, report: dict[str, object]) -> None:
    (artifacts / "gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


def stop_reason(record: dict[str, object], keep_going: bool) -> str | None:
    """Why the order ends after this record, or None when it goes on.

    A timed-out module ends it in every mode: the kill reached the pytest
    process, which proves nothing about the browser it started, so no later
    module could be read as a run of its own. So does an exit code pytest
    never returns: that process did not reach its session teardown. Any other
    red module ends it only without keep-going.
    """
    if record["exit_code"] == "timed-out":
        return "timed-out"
    if record["exit_code"] not in PYTEST_EXIT_CODES:
        return "abnormal-exit"
    if is_red(record) and not keep_going:
        return "first-failure"
    return None


def _log_red(record: dict[str, object], stopping: bool) -> None:
    LOG.error("%s: %s (nodes: %s, waived: %s)",
              "gate stops at" if stopping else "red module, the gate goes on",
              record["module"], record["failed_nodes"],
              {name: record[name] for name in WAIVER_OUTCOMES if record[name]})


def run_gate(modules_dir: Path, artifacts: Path, reverse: bool,
             skip_version_probe: bool,
             timeout: float = MODULE_TIMEOUT_SECONDS, keep_going: bool = False) -> int:
    """The gate: modules in order, one process and one chance each."""
    modules_dir, artifacts = modules_dir.resolve(), artifacts.resolve()
    repo = modules_dir.resolve().parent
    artifacts.mkdir(parents=True, exist_ok=True)
    # An earlier run's report must not answer for this one if anything below fails.
    (artifacts / "gate.json").unlink(missing_ok=True)
    if not skip_version_probe:
        versions = probe_versions(artifacts)
        LOG.info("engine: playwright %s, chromium %s",
                 versions["playwright"], versions["chromium"])
    modules = discover_modules(modules_dir, reverse)
    planned = [module.name for module in modules]
    records: list[dict[str, object]] = []

    def report(progress: str, stopped: dict[str, str] | None = None) -> None:
        _write_report(artifacts, gate_report(reverse, keep_going, planned, records,
                                             progress, stopped))

    report("running")  # before the first module: a gate killed now is not green
    for module in modules:
        try:
            record = run_module(module, artifacts, repo, timeout)
        except BaseException as error:  # the environment failed, not a module: no verdict past it
            report("stopped", {"reason": "error", "module": module.name,
                               "detail": type(error).__name__})
            raise
        records.append(record)
        LOG.info("%s: exit %s in %ss %s", record["module"], record["exit_code"],
                 record["duration_seconds"], record["tail"])
        reason = stop_reason(record, keep_going)
        if is_red(record):
            _log_red(record, reason is not None)
        if reason is not None:
            report("stopped", {"reason": reason, "module": module.name})
            return 1
        report("running")  # the report survives a kill: rewritten after every module
    report("complete")
    return 1 if any(is_red(row) for row in records) else 0


def completed_report(path: Path) -> bool:
    """Whether a gate report shows an order that ran every planned module to an
    ordinary end -- the condition for running the other order on the same runner.
    An unreadable, partial or stopped report answers no."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(report, dict) or not isinstance(report.get("planned"), list):
        return False
    return (report.get("progress") == "complete" and report.get("complete") is True
            and report.get("remaining") == [] and report.get("stopped") is None
            and report.get("done") == report["planned"] and bool(report["planned"]))


def main(argv: list[str] | None = None) -> int:
    """CLI entry: parse, run, and answer with the gate's exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reverse", action="store_true",
                        help="run the modules in reverse collection order")
    parser.add_argument("--keep-going", action="store_true",
                        help="after an ordinary red module run the next one too; "
                             "the verdict stays red (a timeout still ends the order)")
    parser.add_argument("--completed-report", type=Path, default=None, metavar="REPORT",
                        help="run nothing: exit 0 when REPORT shows a completed order")
    parser.add_argument("--artifacts", type=Path, default=None,
                        help="directory for records and failure evidence")
    parser.add_argument("--modules-dir", type=Path,
                        default=Path(__file__).resolve().parent,
                        help="directory holding the browser test modules")
    parser.add_argument("--skip-version-probe", action="store_true",
                        help="skip the engine version launch (unit tests)")
    parser.add_argument("--module-timeout", type=float,
                        default=MODULE_TIMEOUT_SECONDS,
                        help="seconds before a hanging module is killed")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if arguments.completed_report is not None:
        completed = completed_report(arguments.completed_report)
        LOG.info("%s: %s", arguments.completed_report,
                 "the order completed" if completed else "the order did not complete")
        return 0 if completed else 1
    artifacts = arguments.artifacts or Path(tempfile.gettempdir()) / (
        "conduct-browser-gate-" + time.strftime("%Y%m%d-%H%M%S"))
    LOG.info("artifacts: %s", artifacts)
    return run_gate(arguments.modules_dir, artifacts, arguments.reverse,
                    arguments.skip_version_probe, arguments.module_timeout,
                    arguments.keep_going)


if __name__ == "__main__":
    raise SystemExit(main())
