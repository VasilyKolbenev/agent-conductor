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

Beside it sits a passive count of Windows' ``connect failed: 10055`` (R1.3-E1),
armed by the same variable and only observing -- no verdict, outcome or test
changes: see ``_note_netfail``, ``_note_no_buffer_space`` and
``pytest_sessionfinish``, and ``<artifacts>/netfail/<module>.jsonl``.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
import weakref
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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

#: What the reaper met, for the module's closing picture (browser_tests/host_snapshot.py).
#: A `close()` that raised used to vanish here, so whether reaping WORKED after the
#: Windows 10055 setup failure could not be read; the first few errors are kept verbatim.
_REAPED: "dict[str, object]" = {"returned": 0, "raised": 0, "errors": []}


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
            _REAPED["returned"] += 1
        except Exception as error:  # noqa: BLE001 -- a closed context is the goal; kept, not raised
            _REAPED["raised"] += 1
            if len(_REAPED["errors"]) < 5:
                _REAPED["errors"].append(repr(error)[:300])


#: Chromium's own line for a refused connect, as Playwright's `pw:browser` channel relays it:
#: ``<time> pw:browser [pid=N][err] [..:ERROR:net\socket\tcp_socket_win.cc:1148] connect failed:
#: 10055``. Matched as a WHOLE line, never as a substring: a pid of 10055, another error code,
#: or this line quoted in a traceback are lines that mention the number, not the event.
_CHROMIUM_10055 = re.compile(
    r"^(?:\S+\s+)?pw:browser\s.*tcp_socket_win\.cc:\d+\]\s*connect failed: 10055$")

#: The count's process clocks (R1.3-E1): contexts minted so far, when ANY context last closed
#: (`time.monotonic()`), and the module last named by a test id.
_CLOCK: "dict[str, Any]" = {"opened": 0, "last_close": None, "label": None}

#: Each context's ordinal in this process and the moment it was minted. Weak: the count never
#: keeps a closed context alive.
_BORN: "weakref.WeakKeyDictionary[object, tuple[int, float]]" = weakref.WeakKeyDictionary()

#: What each module has shown so far, for its closing line (`pytest_sessionfinish`). The two event
#: counts are two views of what can be ONE incident -- the line Chromium says and the request the
#: page then sees fail -- so there is deliberately no field that adds them (R1.3-E1, review F2).
_NETFAIL: "dict[str, dict[str, int]]" = {}
_TOTALS = ("contexts_opened", "contexts_closed", "chromium_lines", "requestfailed",
           "write_errors")

#: The `netfail` files this process has already opened, by full path. The FIRST open of a file
#: replaces what an earlier run left there, as the gate's other per-module artifacts are replaced;
#: every later open appends. A process is a session here: the gate runs one process per module.
_NETFAIL_OPENED: "set[str]" = set()


def _totals(label: str) -> "dict[str, int]":
    """This module's running counts, started at zero the first time it is named."""
    return _NETFAIL.setdefault(label, dict.fromkeys(_TOTALS, 0))


def _module_label(nodeid: str = "") -> str:
    """The module a record belongs to: its file stem, the name the host pictures use too.

    From the node id when there is one, else from the test pytest is running now, else from the
    last module named, so a close heard after the final test still lands in that module's file.
    """
    current = nodeid or os.environ.get("PYTEST_CURRENT_TEST", "")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(current.split("::", 1)[0]).stem)
    if stem:
        _CLOCK["label"] = stem
    return stem or str(_CLOCK["label"] or f"pid{os.getpid()}")


def _netfail_write(label: str, record: "dict[str, object]") -> bool:
    """Write one JSON line to the module's `netfail/<module>.jsonl`; say whether it landed.

    The one writer of the count. The first line a session writes to a file replaces the file (a
    run's data must not be mixed with an earlier run's in the same artifacts directory); the
    session's later lines are appended. It never raises: a directory that cannot be written costs
    the count a line, which the closing line then reports as `write_errors`, and never the test
    its outcome.
    """
    try:
        directory = Path(os.environ[ARTIFACTS_ENV]) / "netfail"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{label}.jsonl"
        with open(path, "a" if str(path) in _NETFAIL_OPENED else "w", encoding="utf-8",
                  newline="\n") as handle:
            _NETFAIL_OPENED.add(str(path))
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return True
    except Exception:  # noqa: BLE001 -- observing never costs a test
        _totals(label)["write_errors"] += 1
        return False


def _track_context(context: object) -> None:
    """Stamp a context's birth and hear its close, for the count. Never raises.

    The ordinal and the minting time are what a `requestfailed` is later set against; the close
    is heard by subscription, because a context closes by many roads (its fixture, the reaper,
    the browser) and the count must see all of them. Unarmed, it does nothing at all.
    """
    if not os.environ.get(ARTIFACTS_ENV):
        return
    try:
        _CLOCK["opened"] += 1
        _BORN[context] = (_CLOCK["opened"], time.monotonic())
        _totals(_module_label())["contexts_opened"] += 1

        def closed(*_heard: object) -> None:
            try:
                _CLOCK["last_close"] = time.monotonic()
                _totals(_module_label())["contexts_closed"] += 1
            except Exception:  # noqa: BLE001 -- a listener that raised would reach the test
                pass

        context.on("close", closed)
    except Exception:  # noqa: BLE001 -- counting never costs a context
        pass


def _note_no_buffer_space(page: object, request: object) -> None:
    """Write down a request Chromium refused for want of buffer space, the moment it is heard.

    UTC time, the running test, the URL's PATH (never its query or fragment), Chromium's words,
    the context's ordinal, and two clocks in milliseconds: since the page's context was minted
    and since ANY context of this process last closed (null when none has). The sync API
    delivers an event only inside a Playwright call, so both clocks can trail the event itself
    by that call. A page whose context is unknown is still written, without its clocks: the
    event is the datum. Never raises -- this runs inside a Playwright listener.
    """
    try:
        if not os.environ.get(ARTIFACTS_ENV):
            return
        failure = str(getattr(request, "failure", None) or "")
        if "ERR_NO_BUFFER_SPACE" not in failure:
            return
        heard = time.monotonic()
        index = since_open = since_close = None
        try:
            index, minted = _BORN[page.context]
            since_open = round((heard - minted) * 1000)
        except Exception:  # noqa: BLE001 -- the clocks are extras
            pass
        if _CLOCK["last_close"] is not None:
            since_close = round((heard - _CLOCK["last_close"]) * 1000)
        try:
            path = urlsplit(str(request.url)).path[:300]
        except Exception:  # noqa: BLE001
            path = ""
        label = _module_label()
        _totals(label)["requestfailed"] += 1
        _netfail_write(label, {
            "kind": "requestfailed",
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds"),
            "node": os.environ.get("PYTEST_CURRENT_TEST", ""),
            "path": path, "failure": failure[:300], "context_index": index,
            "ms_since_open": since_open, "ms_since_last_close": since_close})
    except Exception:  # noqa: BLE001 -- see the docstring
        pass


def _note_netfail(report: pytest.TestReport) -> None:
    """Pass over one report's captured stderr for Chromium's own 10055 line. Never raises.

    Called for EVERY report -- setup, call and teardown, passed, failed or skipped -- because the
    question is how often the line is said in tests that pass, and CI kept it only for a test
    that failed. What is read is what pytest drained from stderr in the report's OWN phase, which
    includes the Playwright driver's `pw:browser` output (the driver writes to the stderr pytest
    is capturing); a line the driver wrote between two phases is drained by the next, so the
    phase is the one that drained it, and the time in the line itself is Chromium's.

    Not `report.capstderr`: pytest keeps every phase's captured sections on the test item and
    puts all of them on each later report, so the teardown report's `capstderr` holds the setup's
    and the call's lines again and one line would be counted up to three times. Each matching
    line is one record: the node, the phase, the outcome, and the line cut at 300 characters.
    """
    try:
        label = _module_label(report.nodeid)
        totals = _totals(label)  # a module that heard nothing is still named, for its closing line
        text = "\n".join(content for name, content in report.sections
                         if name == f"Captured stderr {report.when}")
        if "10055" not in text:
            return
        for line in text.splitlines():
            row = line.rstrip()
            if _CHROMIUM_10055.match(row):
                totals["chromium_lines"] += 1
                _netfail_write(label, {
                    "kind": "chromium-line", "node": report.nodeid, "phase": report.when,
                    "outcome": report.outcome, "line": row[:300]})
    except Exception:  # noqa: BLE001 -- see the docstring
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
    # When this process heard of the failure, in UTC, the clock a host trace stamps
    # its events with. The sync API delivers events only inside a Playwright call,
    # so this can trail the failure itself; the browser's own start time is 0 on a
    # request that got no response, so it is the nearest time there is.
    page.on("requestfailed", lambda request: said.append(
        f"requestfailed {request.url} {(request.failure or '')!s} at="
        f"{datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')}"))
    # A request refused for want of buffer space (Windows' 10055) is also written down in the
    # count's own file the moment it is heard (`_note_no_buffer_space`); the line above is not
    # touched, and this is a different listener, so no event is written twice to either.
    page.on("requestfailed", lambda request: _note_no_buffer_space(page, request))
    return said


def _instrumented(browser: Browser) -> Browser:
    """Make every context and page this browser mints record what it saw.

    Wrapped HERE rather than in each fixture because there are eleven of them
    and the next one will not remember either. Contexts are also collected, so
    one that a dead fixture never closed is still closed by this file.
    """
    minting = browser.new_context

    def new_context(**options):
        # Every scenario names its locale: the English selectors below are not
        # a bet on the host's language, and the RU/EN scenarios pass their own.
        options.setdefault("locale", "en-US")
        context = minting(**options)
        _OPEN_CONTEXTS.append(context)
        # Every page this context will ever hold, however it was opened.
        context.on("page", _remember)
        _track_context(context)  # its ordinal, its birth and its close, for the 10055 count
        return context

    browser.new_context = new_context
    return browser


@pytest.fixture(scope="session")
def chromium() -> Iterator[Browser]:
    """Launch the same Chromium engine the independent CI job installs."""
    with sync_playwright() as playwright:
        log_path = os.environ.get("CHROME_LOG_FILE")
        log_args = [f"--log-file={log_path}"] if log_path else []
        browser = _instrumented(playwright.chromium.launch(headless=True, args=log_args))
        boundary = None
        if os.environ.get(ARTIFACTS_ENV):
            try:  # a picture of the module's start; never a reason to stop the gate
                from browser_tests.host_snapshot import ModuleBoundary
                boundary = ModuleBoundary(os.environ[ARTIFACTS_ENV])
            except Exception:  # noqa: BLE001 -- the gate runs without its picture
                boundary = None
        try:
            yield browser
        finally:
            left = len(browser.contexts)
            try:
                browser.close()
            finally:  # a close that raises is the flake's class: its picture is kept too
                if boundary is not None:
                    boundary.finish(contexts_left=left, reaped=_REAPED)


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
    if report.when != "teardown":
        # After the traceback and the screenshots, still before teardown: a picture that
        # cannot be taken says why in its place, and never costs the failure it follows.
        try:
            from browser_tests.host_snapshot import failure_section
            words = "\n".join(line for _page, lines in said for line in lines)
            section = failure_section(item.funcargs, words, _OPEN_CONTEXTS)
        except Exception as error:  # noqa: BLE001 -- the failure above is the record
            section = f"host snapshot unavailable: {error!r}\n"
        with open(f"{stem}.failure.txt", "a", encoding="utf-8") as record:
            record.write("\n" + section)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """On failure IN ANY PHASE, write evidence while pages still live.

    Teardown included on purpose: the recurring flake's known class is a
    teardown error, and the hook exists for exactly that sighting. The
    writer is guarded whole — evidence that raises would abort the session
    as INTERNALERROR and destroy the very report it was gathering.

    EVERY report, whatever its phase or outcome, is also handed to the passive
    10055 count (`_note_netfail`), which only reads it.
    """
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    if report.failed and os.environ.get(ARTIFACTS_ENV):
        try:
            _write_failure_evidence(item, report)
        except Exception as error:  # noqa: BLE001 — see the docstring
            report.sections.append(
                ("gate evidence", f"evidence writing failed: {error!r}"))
    if os.environ.get(ARTIFACTS_ENV):
        _note_netfail(report)


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


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Close each module's `netfail` file with its totals, once the session is over.

    By now the session-scoped browser is closed, so the totals are final: contexts opened and
    closed, Chromium lines, `requestfailed` events, and the writes that failed. The two event
    counts are never added: one refused connect can be both a Chromium line and a failed request,
    and a sum would count that incident twice. The decision rule of R1.3 ("5 per order") reads
    `chromium_lines`, whose records carry the outcome of the test; `requestfailed` is the same
    kind of incident seen from the page, kept for its clocks. A module that heard nothing gets
    the line too -- it is what says the count was armed and saw zero. A line that cannot be
    written is said on stderr, which the gate keeps beside the module's record; nothing here can
    change the session's exit status.
    """
    if not os.environ.get(ARTIFACTS_ENV):
        return
    try:
        for label, totals in list(_NETFAIL.items()):
            closing = {"kind": "summary", "module": label, **totals,
                       "time": datetime.datetime.now(datetime.timezone.utc).isoformat(
                           timespec="milliseconds")}
            if not _netfail_write(label, closing):
                sys.stderr.write(f"netfail closing line not written for {label}\n")
    except Exception:  # noqa: BLE001 -- see the docstring
        pass
