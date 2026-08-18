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
  red gate, full stop, and the gate stops at the first one;
- every run leaves a record (module, exit code, duration, output tail, the
  Playwright and Chromium versions the gate ran on), and a failing run
  leaves everything: full stdout, full stderr with Playwright's browser
  channel logging (DEBUG=pw:browser*), the failing node ids, and whatever
  screenshots and tracebacks the conftest evidence hook captured while the
  failing test's pages were still alive.

Not a test module: pytest ignores it (no ``test_`` prefix), and the fast
suite pins its discipline in tests/test_browser_gate.py.

Usage:
    python -m browser_tests.gate [--reverse] [--artifacts DIR]
                                 [--modules-dir DIR] [--skip-version-probe]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOG = logging.getLogger("browser-gate")
_FAILED_NODE = re.compile(r"^(?:FAILED|ERROR) (\S+)", re.MULTILINE)


def discover_modules(modules_dir: Path, reverse: bool) -> list[Path]:
    """Every browser test module, in a stated order — never a sampled subset."""
    modules = sorted(modules_dir.glob("test_*.py"))
    if not modules:
        raise SystemExit(f"no test modules found under {modules_dir}")
    return list(reversed(modules)) if reverse else modules


def probe_versions(artifacts: Path) -> dict[str, str]:
    """Record the exact engine the gate ran on, once per gate."""
    from importlib.metadata import version

    from playwright.sync_api import sync_playwright

    with sync_playwright() as api:
        browser = api.chromium.launch(headless=True)
        try:
            versions = {"playwright": version("playwright"),
                        "chromium": browser.version,
                        "python": sys.version}
        finally:
            browser.close()
    (artifacts / "versions.json").write_text(
        json.dumps(versions, indent=2), encoding="utf-8")
    return versions


def run_module(module: Path, artifacts: Path, repo: Path) -> dict[str, object]:
    """Run one module once, in a fresh pytest/Chromium process."""
    environment = dict(os.environ)
    environment["CONDUCT_GATE_ARTIFACTS"] = str(artifacts)
    environment["PYTHONPATH"] = str(repo / "src")
    # Playwright's browser channel: launch lines and Chromium's own stderr
    # land in the subprocess stderr, so a renderer crash leaves its words.
    environment["DEBUG"] = "pw:browser*"
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", str(module), "-q", "--tb=long", "-rEf",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(repo), env=environment, check=False)
    duration = round(time.monotonic() - started, 2)
    record = {
        "module": module.name,
        "exit_code": completed.returncode,
        "duration_seconds": duration,
        "failed_nodes": _FAILED_NODE.findall(completed.stdout),
        "tail": completed.stdout.strip().splitlines()[-1:],
    }
    if completed.returncode != 0:
        stem = artifacts / module.stem
        stem.with_suffix(".stdout.txt").write_text(
            completed.stdout, encoding="utf-8")
        stem.with_suffix(".stderr.txt").write_text(
            completed.stderr, encoding="utf-8")
    return record


def run_gate(modules_dir: Path, artifacts: Path, reverse: bool,
             skip_version_probe: bool) -> int:
    """The gate: modules in order, one process and one chance each."""
    repo = modules_dir.resolve().parent
    artifacts.mkdir(parents=True, exist_ok=True)
    if not skip_version_probe:
        versions = probe_versions(artifacts)
        LOG.info("engine: playwright %s, chromium %s",
                 versions["playwright"], versions["chromium"])
    records: list[dict[str, object]] = []
    exit_code = 0
    for module in discover_modules(modules_dir, reverse):
        record = run_module(module, artifacts, repo)
        records.append(record)
        LOG.info("%s: exit %s in %ss %s", record["module"], record["exit_code"],
                 record["duration_seconds"], record["tail"])
        if record["exit_code"] != 0:
            LOG.error("gate stops at first failure: %s (nodes: %s)",
                      record["module"], record["failed_nodes"])
            exit_code = 1
            break
    (artifacts / "gate.json").write_text(
        json.dumps({"order": "reverse" if reverse else "normal",
                    "result": "red" if exit_code else "green",
                    "records": records}, indent=2), encoding="utf-8")
    return exit_code


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
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    artifacts = arguments.artifacts or Path(tempfile.gettempdir()) / (
        "conduct-browser-gate-" + time.strftime("%Y%m%d-%H%M%S"))
    LOG.info("artifacts: %s", artifacts)
    return run_gate(arguments.modules_dir, artifacts, arguments.reverse,
                    arguments.skip_version_probe)


if __name__ == "__main__":
    raise SystemExit(main())
