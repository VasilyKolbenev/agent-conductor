"""The gate's own evidence channels, shown to record something.

The reverse gate went red for weeks with three evidence channels that were
named and empty: `*.stderr.txt` at 0 bytes on red runs and green ones,
`*.chromium.log` at 0 bytes always, and no `requestfailed` listener anywhere in
`browser_tests` at all. The failing URL was therefore never written down, and
the record of the last such failure had to say so.

A channel nobody has watched fail is a channel nobody should trust. These drive
the two this repair added -- the page's own words, and the closing of a context
whose fixture died before its `try` -- against real Chromium, and assert that
each one really holds what it claims.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser

from browser_tests import conftest


def test_a_resource_that_fails_to_load_names_itself_in_this_gates_record(
        chromium: Browser) -> None:
    """`requestfailed`, connected where a page is born rather than nowhere.

    This is the channel that was missing, and it is the one that finally named
    the reverse gate's cause: a Studio module answering
    `net::ERR_NO_BUFFER_SPACE`. Without it a failed import is invisible --
    `mountShell` never runs, the shell stays empty, and every wait after that
    times out saying only that the shell stayed empty.

    The failure is provoked honestly: a request to a port nothing is listening
    on. Playwright's own event is what this waits for, and what is ASSERTED is
    that the gate's record caught it too -- so the test cannot pass on
    Playwright's behalf.
    """
    context = chromium.new_context()
    page = context.new_page()
    try:
        said = conftest._SAID[page]
        page.goto("about:blank")

        with page.expect_event("requestfailed"):
            page.evaluate(
                """() => { const tag = document.createElement('script');
                   tag.src = 'http://127.0.0.1:1/never-listening.js';
                   document.head.append(tag); }""")

        failed = [line for line in said if line.startswith("requestfailed")]
        assert failed, said
        assert "never-listening.js" in failed[0], failed
        # The URL and the engine's own words, and nothing else: no header, no
        # body, no cookie. These artifacts are read by people.
        assert "cookie" not in failed[0].lower()
    finally:
        context.close()


def test_a_page_error_and_a_console_error_are_kept_apart_and_both_kept(
        chromium: Browser) -> None:
    """The other two channels, which existed but died with their fixture.

    They were collected into a list inside the fixture frame, so a failure
    during setup -- the shape the flake actually takes -- destroyed them. They
    are kept outside it now, and this asserts both still arrive and stay
    distinguishable.
    """
    context = chromium.new_context()
    page = context.new_page()
    try:
        said = conftest._SAID[page]
        page.goto("about:blank")

        with page.expect_event("console"):
            page.evaluate("() => console.error('a console error')")
        with page.expect_event("pageerror"):
            page.evaluate(
                "() => setTimeout(() => { throw new Error('an uncaught one'); })")

        assert any(line.startswith("console-error") and "a console error" in line
                   for line in said), said
        assert any(line.startswith("pageerror") and "an uncaught one" in line
                   for line in said), said
    finally:
        context.close()


def test_a_context_its_fixture_never_closed_is_closed_by_this_file(
        chromium: Browser) -> None:
    """The leak eleven fixtures have, closed in the one place that can.

    Every one of them creates a context, navigates and waits for a first render
    BEFORE its `try`. A failure in any of those three never reaches the
    `finally`, and the context then stays open for the rest of the session --
    holding a page, a renderer and its sockets, on a gate that runs 34 modules
    back to back.

    The reaper is called directly here rather than left to fire between tests,
    because a test cannot watch its own teardown: what is proved is that the
    thing the teardown calls really closes what a dead fixture left.
    """
    context = chromium.new_context()
    page = context.new_page()
    assert any(context is kept for kept in conftest._OPEN_CONTEXTS)

    conftest._reap_contexts()

    assert page.is_closed(), "the abandoned page was left running"
    assert conftest._OPEN_CONTEXTS == []
    with pytest.raises(Exception):
        context.new_page()
