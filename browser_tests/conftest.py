"""One browser for the whole browser gate, and the gate's failure evidence.

Each module used to enter its own ``sync_playwright``, so whether the gate
passed depended on the order its files were collected in: a second context
manager entered while a session-scoped one is still open raises "Playwright
Sync API inside the asyncio loop", and the same suite therefore passed named
one way and errored named the other. One session-scoped fixture, here, takes
the ordering out of the answer.

This file holds that fixture and the failure-evidence hook, and nothing
else. The hook exists for the release gate (browser_tests/gate.py): when a
test fails and the gate has named an artifacts directory, the failing node's
id, its traceback, and a screenshot of every page the test still holds are
written there BEFORE any fixture teardown can close the pages — because the
recurring Chromium flake dies with its context, and evidence gathered after
teardown is no evidence at all. Without the environment variable the hook
does nothing: an ordinary local run stays an ordinary local run.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, sync_playwright

ARTIFACTS_ENV = "CONDUCT_GATE_ARTIFACTS"


@pytest.fixture(scope="session")
def chromium() -> Iterator[Browser]:
    """Launch the same Chromium engine the independent CI job installs."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            yield browser
        finally:
            browser.close()


def _evidence_stem(directory: Path, node_id: str) -> Path:
    """A filesystem-safe stem for one failing node's evidence files."""
    return directory / re.sub(r"[^A-Za-z0-9._-]+", "_", node_id)[:150]


def _write_failure_evidence(item: pytest.Item, report: pytest.TestReport) -> None:
    """Record what the gate needs: node id, traceback, live-page screenshots."""
    directory = Path(os.environ[ARTIFACTS_ENV])
    directory.mkdir(parents=True, exist_ok=True)
    stem = _evidence_stem(directory, report.nodeid)
    with open(f"{stem}.failure.txt", "w", encoding="utf-8") as record:
        record.write(f"node id: {report.nodeid}\n")
        record.write(f"phase: {report.when}\n\n")
        record.write(report.longreprtext or "(no traceback text)")
        record.write("\n")
    shot = 0
    for value in item.funcargs.values():
        screenshot = getattr(value, "screenshot", None)
        is_closed = getattr(value, "is_closed", None)
        if not callable(screenshot) or not callable(is_closed) or is_closed():
            continue
        shot += 1
        try:
            screenshot(path=f"{stem}.page{shot}.png", full_page=True)
        except Exception as error:  # noqa: BLE001 — evidence must not mask the failure
            with open(f"{stem}.page{shot}.err.txt", "w", encoding="utf-8") as note:
                note.write(f"screenshot failed: {error!r}\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """On failure, write evidence while the failing test's pages still live."""
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    if report.when in ("call", "setup") and report.failed \
            and os.environ.get(ARTIFACTS_ENV):
        _write_failure_evidence(item, report)
