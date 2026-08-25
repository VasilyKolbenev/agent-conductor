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
  red gate, full stop, and the gate stops at the first one. Every way a test
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
  timed-out, and the gate report is rewritten after every module, so even a
  killed gate leaves the records accumulated so far.

Not a test module: pytest ignores it (no ``test_`` prefix), and the fast
suite pins its discipline in tests/test_browser_gate.py.

Usage:
    python -m browser_tests.gate [--reverse] [--artifacts DIR]
                                 [--modules-dir DIR] [--skip-version-probe]
                                 [--module-timeout SECONDS]
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
        browser = api.chromium.launch(headless=True, env=probe_environment)
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
    basetemp = _own_basetemp(artifacts, module)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", str(module), "-q", "--tb=long",
             "-rEf", "-p", "no:cacheprovider", "-o", "addopts=",
             "--basetemp", str(basetemp)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(repo), env=_child_environment(artifacts, repo, module),
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


def _write_report(artifacts: Path, reverse: bool, result: str,
                  records: list[dict[str, object]]) -> None:
    (artifacts / "gate.json").write_text(
        json.dumps({"order": "reverse" if reverse else "normal",
                    "result": result, "records": records}, indent=2),
        encoding="utf-8")


def run_gate(modules_dir: Path, artifacts: Path, reverse: bool,
             skip_version_probe: bool,
             timeout: float = MODULE_TIMEOUT_SECONDS) -> int:
    """The gate: modules in order, one process and one chance each."""
    repo = modules_dir.resolve().parent
    artifacts.mkdir(parents=True, exist_ok=True)
    if not skip_version_probe:
        versions = probe_versions(artifacts)
        LOG.info("engine: playwright %s, chromium %s",
                 versions["playwright"], versions["chromium"])
    records: list[dict[str, object]] = []
    for module in discover_modules(modules_dir, reverse):
        record = run_module(module, artifacts, repo, timeout)
        records.append(record)
        LOG.info("%s: exit %s in %ss %s", record["module"], record["exit_code"],
                 record["duration_seconds"], record["tail"])
        red = is_red(record)
        # The report survives a kill: rewritten after every module.
        _write_report(artifacts, reverse, "red" if red else "running", records)
        if red:
            LOG.error("gate stops at first failure: %s (nodes: %s, waived: %s)",
                      record["module"], record["failed_nodes"],
                      {name: record[name] for name in WAIVER_OUTCOMES
                       if record[name]})
            return 1
    _write_report(artifacts, reverse, "green", records)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry: parse, run, and answer with the gate's exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reverse", action="store_true",
                        help="run the modules in reverse collection order")
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
    artifacts = arguments.artifacts or Path(tempfile.gettempdir()) / (
        "conduct-browser-gate-" + time.strftime("%Y%m%d-%H%M%S"))
    LOG.info("artifacts: %s", artifacts)
    return run_gate(arguments.modules_dir, artifacts, arguments.reverse,
                    arguments.skip_version_probe, arguments.module_timeout)


if __name__ == "__main__":
    raise SystemExit(main())
