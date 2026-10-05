"""A wait for the desk goes on waiting while its document is not the desk yet.

The hub mounts the desk in a frame, and a test that asks the frame at once is asking a document
that has not drawn it: the shell is not there. A wait whose predicate dereferences the shell
ENDS with a TypeError in that moment (`Cannot read properties of null`) instead of waiting; the
shared predicates of `desk_settled.py` read through `?.`, so each of them says "not yet".
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Error, Frame, Page
from playwright.sync_api import TimeoutError as WaitTimeout

from browser_tests.desk_settled import FOREIGN_SAID, SETTLED, shell_is
from browser_tests.desk_wizard_bench import desk_url  # noqa: F401  (the fixture)

#: What the waits of the desk tests were before they were shared: the shell dereferenced.
UNGUARDED = ('() => ["ready", "refused", "failed"].includes('
             'document.getElementById("deskShell").getAttribute("data-state"))')
#: A wait that has not been answered by now is a wait that went on.
SHORT = 300


def _frame_that_is_not_the_desk(page: Page) -> Frame:
    """The window of a frame that has just been mounted: its document is empty."""
    page.set_content("<iframe></iframe>")
    return page.wait_for_selector("iframe").content_frame()


def test_a_wait_that_dereferences_the_shell_ends_with_a_type_error_in_a_frame_that_is_not_the_desk(
        chromium: Browser):
    context = chromium.new_context()
    try:
        frame = _frame_that_is_not_the_desk(context.new_page())
        with pytest.raises(Error, match="Cannot read properties of null") as ended:
            frame.wait_for_function(UNGUARDED, timeout=2000)
        assert not isinstance(ended.value, WaitTimeout), "it ended by itself, it did not time out"
    finally:
        context.close()


@pytest.mark.parametrize("predicate", [
    SETTLED, FOREIGN_SAID, shell_is("ready"), shell_is("loading"), shell_is("refused"),
    shell_is("failed")], ids=["settled", "foreign", "ready", "loading", "refused", "failed"])
def test_a_shared_wait_goes_on_waiting_in_a_frame_that_is_not_the_desk(
        chromium: Browser, predicate: str):
    context = chromium.new_context()
    try:
        frame = _frame_that_is_not_the_desk(context.new_page())
        with pytest.raises(WaitTimeout):
            frame.wait_for_function(predicate, timeout=SHORT)
    finally:
        context.close()


def test_a_wait_begun_before_the_desk_arrived_ends_when_the_desk_has_settled(
        chromium: Browser, desk_url: str):  # noqa: F811
    context = chromium.new_context()
    try:
        page = context.new_page()
        page.goto("about:blank")
        page.evaluate("url => setTimeout(() => location.assign(url), 100)",
                      f"{desk_url}/panel/desk.html")
        page.wait_for_function(SETTLED)
        assert page.locator("#deskShell").get_attribute("data-state") in {
            "ready", "refused", "failed"}
    finally:
        context.close()
