"""Keyed controls that keep the keyboard through a render, where only an editable draft or
a project with no run can draw them.

Review of the CI3 slice measured the class on the Overview: controls sharing one focus key
lose the keyboard to the page body on any render, because the focus net (studio-focus.js)
rightly refuses to choose among several successors. Found beside it on the Workflow screen:
the shell's main Save and the toolbar's Save shared `action:onSaveDraft`. Each case here
rests the keyboard on a control, runs one ordinary render through the language door -- the
same `render()` an answered read runs -- in both languages, and reads where the keyboard is.
"""
from __future__ import annotations

from playwright.sync_api import Browser, Page, expect

from browser_tests.test_studio_demo import _RENDER_UNDER_FOCUS
from browser_tests.test_studio_editing import _Bench, bench, studio_url  # noqa: F401


def _kept(page: Page, selector: str, key: str) -> None:
    said = set()
    for language in ("ru", "en"):
        after = page.evaluate(_RENDER_UNDER_FOCUS, [selector, language])
        assert (after["replaced"], after["key"], after["same"]) == (True, key, True), (
            selector, language, after)
        said.add(after["words"])
    assert len(said) == 2, (selector, said)


def test_both_saves_on_the_workflow_screen_keep_the_keyboard_through_a_render(
        bench: _Bench) -> None:
    page = bench.page
    header = "#studioPrimary button"
    toolbar = '#workflowToolbar [data-focus="action:onSaveDraft"]'
    expect(page.locator(header)).to_be_enabled()
    _kept(page, header, "primary:onSaveDraft")
    _kept(page, toolbar, "action:onSaveDraft")
    assert bench.problems == []


def test_the_overview_runs_button_keeps_the_keyboard_on_a_project_with_no_run(
        chromium: Browser, studio_url: str) -> None:
    context = chromium.new_context(viewport={"width": 1500, "height": 1200})
    try:
        page = context.new_page()
        page.goto(studio_url, wait_until="load")
        page.wait_for_selector('#studioConnection[data-connection="open"]')
        runs = "#bodyOverview .studio-overview__latest button"
        expect(page.locator(runs)).to_have_text("Open the Runs screen")
        _kept(page, runs, "overview:runs")
    finally:
        context.close()
