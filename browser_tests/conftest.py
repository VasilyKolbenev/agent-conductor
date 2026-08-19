"""One browser for the whole browser gate, and the gate's failure evidence.

Each module used to enter its own ``sync_playwright``, so whether the gate
passed depended on the order its files were collected in: a second context
manager entered while a session-scoped one is still open raises "Playwright
Sync API inside the asyncio loop", and the same suite therefore passed named
one way and errored named the other. One session-scoped fixture, here, takes
the ordering out of the answer.

This file holds that fixture and the failure-evidence hook, and nothing
else. The hook exists for the release gate (browser_tests/gate.py): when a
test fails IN ANY PHASE — setup, call, or the teardown where the recurring
Chromium flake actually lives — and the gate has named an artifacts
directory, the failing node's id, its traceback, and a screenshot of every
page still alive are written at the moment of the report, phase-stamped so
a call failure's record survives a teardown error on the same node. Without
the environment variable the hook does nothing: an ordinary local run stays
an ordinary local run.
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


def _evidence_stem(directory: Path, node_id: str, phase: str) -> Path:
    """A filesystem-safe stem for one failing node's evidence, per phase —
    a node can fail in call AND error in teardown, and the second record
    must not clobber the first."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", node_id)[:120]
    return directory / f"{safe}.{phase}"


def _live_pages(item: pytest.Item) -> list[object]:
    """Every page the failing test still holds, however it was created.

    The funcargs walk sees pages a fixture yielded directly; the browser
    walk (chromium.contexts[*].pages) sees the rest — tuple-yielding
    fixtures, helper-created pages, inline contexts. Both, deduplicated,
    because the flake will not choose a convenient shape.
    """
    pages: list[object] = []
    for value in item.funcargs.values():
        if callable(getattr(value, "screenshot", None)) \
                and callable(getattr(value, "is_closed", None)):
            pages.append(value)
        for context in getattr(value, "contexts", None) or []:
            pages.extend(getattr(context, "pages", None) or [])
    unique: list[object] = []
    for page in pages:
        if not any(page is seen for seen in unique) and not page.is_closed():
            unique.append(page)
    return unique


def _write_failure_evidence(item: pytest.Item, report: pytest.TestReport) -> None:
    """Record what the gate needs: node id, traceback, live-page screenshots."""
    directory = Path(os.environ[ARTIFACTS_ENV])
    directory.mkdir(parents=True, exist_ok=True)
    stem = _evidence_stem(directory, report.nodeid, report.when)
    pages = _live_pages(item)
    with open(f"{stem}.failure.txt", "w", encoding="utf-8") as record:
        record.write(f"node id: {report.nodeid}\n")
        record.write(f"phase: {report.when}\n")
        record.write(f"live pages: {len(pages)}\n\n")
        record.write(report.longreprtext or "(no traceback text)")
        record.write("\n")
    for shot, page in enumerate(pages, start=1):
        try:
            page.screenshot(path=f"{stem}.page{shot}.png", full_page=True)
        except Exception as error:  # noqa: BLE001 — evidence must not mask the failure
            with open(f"{stem}.page{shot}.err.txt", "w", encoding="utf-8") as note:
                note.write(f"screenshot failed: {error!r}\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """On failure IN ANY PHASE, write evidence while pages still live.

    Teardown included on purpose: the recurring flake's known class is a
    teardown error, and the hook exists for exactly that sighting. The
    writer is guarded whole — evidence that raises would abort the session
    as INTERNALERROR and destroy the very report it was gathering.
    """
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    if report.failed and os.environ.get(ARTIFACTS_ENV):
        try:
            _write_failure_evidence(item, report)
        except Exception as error:  # noqa: BLE001 — see the docstring
            report.sections.append(
                ("gate evidence", f"evidence writing failed: {error!r}"))
