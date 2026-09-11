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


#: What every page in this gate said, kept OUTSIDE the fixture that made it.
#: Eleven fixtures create a context, navigate, and wait for a first render
#: BEFORE their `try`, so a failure in setup -- which is the shape the recurring
#: flake really takes -- destroys the fixture's frame and the list it was
#: collecting with it. That is why the record of the last such failure said the
#: console list "was not preserved" and why the failed URL was never written
#: down: there was nowhere for it to live. Now there is, and it is keyed by the
#: page object so a module that opens three windows keeps them apart.
#:
#: And it is kept for exactly ONE test: emptied when a test's protocol ends,
#: after its last report (`pytest_runtest_protocol`). The first version of this
#: file never emptied it, so every failure record in a process carried the
#: words of every earlier test -- while its handoff said the events were scoped
#: to one test, from an edit that had never landed.
_SAID: "dict[object, list[str]]" = {}


#: Every context this gate has minted and not yet reaped. A fixture that closes
#: its own context leaves an already-closed one here, which costs nothing; a
#: fixture that died before it could leaves the one that matters.
_OPEN_CONTEXTS: "list[object]" = []


def _reap_contexts() -> None:
    """Close every context still registered, and forget it either way.

    A separate function so the thing the teardown does can be DRIVEN: a test
    cannot watch its own teardown, and a reaper nobody has seen work is the
    same kind of promise as the empty log files this repair is about.
    """
    while _OPEN_CONTEXTS:
        context = _OPEN_CONTEXTS.pop()
        try:
            context.close()
        except Exception:  # noqa: BLE001 -- a closed context is the goal, not an event
            pass


def _remember(page: object) -> list[str]:
    """Attach the channels to a page when it is born.

    ONE road registers every page: the context's own `page` event, which
    Playwright delivers for a page the context opens on request and for one
    the page opens itself -- a popup, `window.open` -- alike, and delivers
    before `new_page` returns. The first version ALSO wrapped `new_page`, so an
    ordinary page was registered twice and every event written twice: a count
    in a record was a count of listeners. Measured, the wrapper registered
    nothing the event had not already registered, so it is gone rather than
    guarded against.

    The store is reached through `setdefault` on purpose. Were a second road
    ever added back, a doubled registration doubles every record -- loud, and
    caught by `test_one_console_error_is_one_record` -- instead of quietly
    leaking listeners into a list nobody reads. Identical words said twice are
    still two records: nothing here filters text.

    `requestfailed` is the one that was never connected anywhere, and it is the
    one that mattered: a JS module that fails to load stops `mountShell`, the
    shell stays empty, and every wait after it times out with no clue which
    resource died. The failure carries a URL and Chromium's own error name.

    Nothing here records a header, a body or a cookie -- a URL, a console
    string and an error's text. The pages under this gate are served by a
    loopback fixture, and the gate's artifacts are read by people.
    """
    said = _SAID.setdefault(page, [])
    page.on("console", lambda message: said.append(
        f"console-error {getattr(message, 'text', '')}")
        if getattr(message, "type", "") == "error" else None)
    page.on("pageerror", lambda error: said.append(f"pageerror {error}"))
    # A response the server REFUSED. The console says only "400 (Bad Request)"
    # and never which request got it, which is the question a reader has first.
    # Method and URL, no headers and no body: these artifacts are read by people.
    page.on("response", lambda answer: said.append(
        f"refused {answer.status} {answer.request.method} {answer.url}")
        if answer.status >= 400 else None)
    page.on("requestfailed", lambda request: said.append(
        f"requestfailed {request.url} "
        f"{(request.failure or '')!s}"))
    return said


def _instrumented(browser: Browser) -> Browser:
    """Make every context and page this browser mints record what it saw.

    Wrapped HERE rather than in each fixture because there are eleven of them
    and the next one will not remember either. Contexts are also collected, so
    one that a dead fixture never closed is still closed by this file.
    """
    minting = browser.new_context

    def new_context(**options):
        context = minting(**options)
        _OPEN_CONTEXTS.append(context)
        # Every page this context will ever hold, however it was opened.
        context.on("page", _remember)
        return context

    browser.new_context = new_context
    return browser


@pytest.fixture(scope="session")
def chromium() -> Iterator[Browser]:
    """Launch the same Chromium engine the independent CI job installs."""
    with sync_playwright() as playwright:
        browser = _instrumented(playwright.chromium.launch(headless=True))
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture(autouse=True)
def _close_what_a_failed_setup_left() -> Iterator[None]:
    """Close every context still open when a test ends, however it ended.

    A fixture that dies before its `try` never reaches its `finally`, so its
    context stayed open for the rest of the session -- holding a page, its
    sockets and its renderer, on a gate that runs 34 modules. This teardown
    runs after the fixtures that failed, so it is the one place that can close
    what they could not.

    It closes nothing a living fixture still owns: by the time an autouse
    teardown runs, every function-scoped fixture of that test has already had
    its own turn.
    """
    yield
    _reap_contexts()


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
    """Record what the gate needs: node id, traceback, screenshots, and words."""
    directory = Path(os.environ[ARTIFACTS_ENV])
    directory.mkdir(parents=True, exist_ok=True)
    stem = _evidence_stem(directory, report.nodeid, report.when)
    pages = _live_pages(item)
    # What THIS test's pages said -- including the pages of a fixture that
    # never yielded, and pages already closed by the time the report is made.
    # Everything the store holds is this test's: it is emptied only when a
    # test's whole protocol is over, and one protocol runs at a time.
    said = [(page, list(lines)) for page, lines in _SAID.items() if lines]
    events = sum(len(lines) for _page, lines in said)
    with open(f"{stem}.failure.txt", "w", encoding="utf-8") as record:
        record.write(f"node id: {report.nodeid}\n")
        record.write(f"phase: {report.when}\n")
        record.write(f"live pages: {len(pages)}\n")
        record.write(f"page events: {events}\n\n")
        # Grouped BY PAGE and named by its URL. Ungrouped, a run that opens
        # three windows reads as one, and a reader spends the first minutes
        # ruling out a neighbour's expected refusals -- which is what happened
        # the first time this channel caught something.
        for index, (page, lines) in enumerate(said, start=1):
            record.write(f"page {index} ({getattr(page, 'url', '?')}):\n")
            for line in lines:
                record.write(f"  {line}\n")
        record.write("\n")
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


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item: pytest.Item):
    """Give the page store to one test, from its setup until after its last report.

    All three reports -- setup, call, teardown -- are made while this wraps the
    test, so a page that spoke during a teardown that raised is still held when
    that teardown's record is written. Only once the whole protocol is over is
    the store emptied: not at the test's teardown, which comes BEFORE the
    teardown's own report, and not never, which is how one test's words reached
    the next test's failure.

    The window IS the ownership, and it is exact here: pytest runs one protocol
    at a time in this process, and the reaper closes every context a test
    opened before that test's protocol ends. A separate owner map was tried and
    removed -- with the store emptied here, no mutation of it could be made to
    fail, and a guard nobody can show failing is not one to ship.
    """
    try:
        yield
    finally:
        _SAID.clear()
