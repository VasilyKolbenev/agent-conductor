"""Whose words a failure record carries, and how many times each was said.

`91614c4` put the page channels where a page is born, and made two claims about
them that were not true. The handoff said events were scoped to one test; the
edit that would have done it never landed, and the record of any failure
carried every page of every earlier test in the same process. And each ordinary
page was registered twice -- once by a wrapped `new_page` and once by the
context's own `page` event -- so one console error was written down twice and
every count in the record was a count of listeners, not of events.

A diagnosis channel that blames the wrong test, or doubles what it saw, is worse
than an empty one: it is read, and believed.

The ownership half is driven through a REAL pytest session in a child process,
with this gate's own conftest copied in unchanged. What is under test is a hook
ordering -- a test's record must outlive its own teardown report and must not
outlive its protocol -- and calling the writer by hand would test a sequence
somebody chose rather than the one pytest runs.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import Browser

from browser_tests import conftest

#: The copied gate runs these, in this order. A says something and passes; B
#: fails with nothing of its own to say; C's fixture speaks and dies before it
#: yields; D's fixture speaks and dies after it yielded; E fails last, and checks
#: on its way that nothing earlier is still held.
INNER_TESTS = '''
import pytest


def _say(page, word):
    with page.expect_event("console"):
        page.evaluate("(word) => console.error(word)", word)


def _page(chromium):
    context = chromium.new_context()
    page = context.new_page()
    page.goto("about:blank")
    return context, page


def test_a_says_its_marker_and_passes(chromium):
    context, page = _page(chromium)
    _say(page, "INNER-MARKER-A")
    context.close()


def test_b_fails_with_nothing_of_its_own(chromium):
    assert False, "B fails and said nothing"


@pytest.fixture
def dies_in_setup(chromium):
    _context, page = _page(chromium)
    _say(page, "INNER-MARKER-SETUP")
    raise RuntimeError("the fixture dies before it yields")
    yield page


def test_c_never_runs(dies_in_setup):
    pass


@pytest.fixture
def dies_in_teardown(chromium):
    _context, page = _page(chromium)
    yield page
    _say(page, "INNER-MARKER-TEARDOWN")
    raise RuntimeError("the fixture dies after it yielded")


def test_d_passes_then_its_fixture_dies(dies_in_teardown):
    pass


def test_e_fails_last(chromium):
    import conftest
    held = [line for lines in conftest._SAID.values() for line in lines]
    assert not held, f"RETAINED {held}"
    assert False, "E fails and said nothing"
'''


def _inner_session(tmp_path: Path) -> tuple[Path, str]:
    """Run the gate's own conftest over the five tests above, in a child."""
    (tmp_path / "conftest.py").write_text(
        Path(conftest.__file__).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "test_inner.py").write_text(INNER_TESTS, encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    environment = {**os.environ, conftest.ARTIFACTS_ENV: str(artifacts)}
    environment.pop("PYTEST_ADDOPTS", None)
    done = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", str(tmp_path), "-q",
         "-p", "no:cacheprovider", "-o", "addopts=",
         "--rootdir", str(tmp_path), "--basetemp", str(tmp_path / "bt")],
        cwd=tmp_path, env=environment, capture_output=True, text=True,
        timeout=180)
    return artifacts, done.stdout[-3000:] + done.stderr[-1500:]


def _record(artifacts: Path, test: str, phase: str, output: str) -> str:
    found = sorted(artifacts.glob(f"*{test}.{phase}.failure.txt"))
    assert len(found) == 1, (test, phase, output)
    return found[0].read_text(encoding="utf-8")


def _said_in(record: str) -> list[str]:
    """The page-events section of a record, and nothing from its traceback.

    pytest prints each failing function's source beside its traceback, so a
    fixture's own `_say(page, "INNER-MARKER-...")` line is in the record whether
    or not the event it sent was kept. The first version of this witness read
    the whole record, and stayed green under a mutation that emptied the store
    before the teardown report -- the source line said the marker for it.

    The section's own count is checked against what is read, so a record whose
    layout changed fails here loudly rather than reading as empty.
    """
    _head, _, rest = record.partition("page events: ")
    count, _, body = rest.partition("\n\n")
    said = []
    for row in body.split("\n"):
        if not row:
            break
        if row.startswith("  "):
            said.append(row.strip())
    assert len(said) == int(count), (count, said, record)
    return said


def test_a_failure_record_holds_its_own_tests_words_and_no_one_elses(
        tmp_path: Path) -> None:
    """Five tests, four records, and each record owned by the test it names.

    B and E fail with nothing to say: neither may carry A's words, and E may not
    carry the teardown words of the test just before it. C's words survive a
    fixture that never yielded; D's survive a teardown that raised -- which is
    the proof that a test's record is kept until AFTER its teardown report, not
    emptied before it. And E, looking at the gate's store before it fails, must
    find nothing earlier still held there.
    """
    artifacts, output = _inner_session(tmp_path)

    first = _record(artifacts, "test_b_fails_with_nothing_of_its_own", "call",
                    output)
    assert _said_in(first) == [], first

    setup = _record(artifacts, "test_c_never_runs", "setup", output)
    assert any("INNER-MARKER-SETUP" in line for line in _said_in(setup)), setup

    teardown = _record(artifacts, "test_d_passes_then_its_fixture_dies",
                       "teardown", output)
    assert any("INNER-MARKER-TEARDOWN" in line
               for line in _said_in(teardown)), teardown

    last = _record(artifacts, "test_e_fails_last", "call", output)
    assert _said_in(last) == [], last
    # Read as the RAISED message, never as a bare word, for the same reason:
    # the retention check's own source text is in every record of E.
    assert "AssertionError: RETAINED" not in last, last
    assert "AssertionError: E fails and said nothing" in last, last


def _say(page, *words: str) -> None:
    for word in words:
        with page.expect_event("console"):
            page.evaluate("(word) => console.error(word)", word)


def test_a_page_is_registered_before_the_test_can_use_it(
        chromium: Browser) -> None:
    """ONE road registers a page, so it has to be a road that is never late.

    Registered at birth, before `new_page` has even returned. A page first
    noticed once it had loaded, or once something had happened on it, would
    miss what a failing boot says first -- and what a failing boot says first
    is the whole reason these channels exist.
    """
    context = chromium.new_context()
    try:
        page = context.new_page()

        assert page in conftest._SAID, "the page was not registered at birth"
        assert conftest._SAID[page] == []
    finally:
        context.close()


def test_one_console_error_is_one_record(chromium: Browser) -> None:
    """One road, one set of listeners, one record per event.

    The first version registered an ordinary page on two roads, and every event
    on it was written down twice.
    """
    context = chromium.new_context()
    page = context.new_page()
    try:
        page.goto("about:blank")
        _say(page, "EXACTLY-ONCE")

        said = [line for line in conftest._SAID[page] if "EXACTLY-ONCE" in line]
        assert len(said) == 1, said
    finally:
        context.close()


def test_two_identical_errors_are_two_records(chromium: Browser) -> None:
    """The fix is one registration, never a filter on repeated text.

    A page that really said the same thing twice said it twice, and a record
    that folded them would understate exactly the repeated failure a reader is
    trying to count.
    """
    context = chromium.new_context()
    page = context.new_page()
    try:
        page.goto("about:blank")
        _say(page, "SAID-TWICE", "SAID-TWICE")

        said = [line for line in conftest._SAID[page] if "SAID-TWICE" in line]
        assert len(said) == 2, said
    finally:
        context.close()


def test_a_popup_no_fixture_created_is_registered_once_on_its_own(
        chromium: Browser) -> None:
    """The page a page opens, which no fixture's `new_page` ever sees."""
    context = chromium.new_context()
    page = context.new_page()
    try:
        page.goto("about:blank")
        with context.expect_page() as opened:
            page.evaluate("() => { window.open('about:blank'); }")
        popup = opened.value
        _say(popup, "FROM-THE-POPUP")

        said = [line for line in conftest._SAID[popup]
                if "FROM-THE-POPUP" in line]
        assert len(said) == 1, said
    finally:
        context.close()
