"""The Workflow screen fits an ordinary window.

R08 of the review of ``8dec0e4``, measured in a real Chromium at 1280×800: the
document was 1399px wide, because the ``new-from`` select carried a starter's
whole caveat -- 191 characters -- as a native option's text, and an option's
text is the select's intrinsic width. The forms above the canvas then stood
395px tall, so the drawing began at 653 of 800.

Four circuits, each a number read off the engine rather than a claim about a
stylesheet:

- the page never scrolls sideways, at 1280, 1440 and a narrow 900, with both
  disclosures folded and with both open;
- the canvas begins within the first screen at 1280×800;
- the chosen starter's note is drawn whole under the control and moves with
  the choice -- no information left the screen, it left the option;
- every fold is reached by Tab and toggled by Enter, so the disclosure costs
  a keyboard user nothing the pointer user does not pay.

The project is the lifecycle bench's: a served tree holding no workflow, so the
start box is the one the state opens and the run box the one it folds.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Browser, Page

from browser_tests.test_studio_lifecycle import (  # noqa: F401
    _Project,
    _Window,
    _settle,
    project,
)

#: An ordinary laptop, a common desktop, and a window narrower than either.
SIZES = [(1280, 800), (1440, 900), (900, 700)]
#: The most an option may say. The longest shipped label is 49 characters;
#: the caveat that overflowed was 191.
OPTION_BUDGET = 64
MEASURE = """() => {
  const doc = document.documentElement;
  const sel = document.querySelector('select[name="new-from"]');
  const canvas = document.querySelector('#workflowCanvas');
  return {
    overflow: doc.scrollWidth - doc.clientWidth,
    body_overflow: document.body.scrollWidth - doc.clientWidth,
    select_width: Math.round(sel.getBoundingClientRect().width),
    select_right: Math.round(sel.getBoundingClientRect().right),
    longest_option: Math.max(...[...sel.options].map(o => o.text.length)),
    canvas_top: Math.round(canvas.getBoundingClientRect().top),
    folds: [...document.querySelectorAll('#workflowToolbar details')]
      .map(d => [d.dataset.fold, d.open]),
  };
}"""


def _workflow_screen(chromium: Browser, served: _Project, width: int,
                     height: int) -> tuple[Page, _Window]:
    context = chromium.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    window = _Window(page)
    page.goto(served.url, wait_until="load")
    _settle(page)
    page.locator("#navWorkflow").click()
    page.wait_for_selector("#screenWorkflow:not([hidden])")
    page.wait_for_function(
        "() => { const s = document.querySelector('select[name=\"new-from\"]');"
        " return s !== null && s.options.length >= 2; }")
    return page, window


@pytest.mark.parametrize("width,height", SIZES, ids=lambda size: str(size))
def test_the_workflow_screen_never_scrolls_sideways(
        chromium: Browser, project: _Project, width: int, height: int) -> None:
    """No horizontal overflow, folded or open, and no option past its budget.

    Measured with the folds as the state left them, and again with both
    forced open: a screen that fits only while its forms are hidden has moved
    the overflow behind a click rather than removed it.
    """
    page, window = _workflow_screen(chromium, project, width, height)
    try:
        before = page.evaluate(MEASURE)
        assert before["overflow"] == 0 and before["body_overflow"] <= 0, before
        assert before["select_right"] <= width, before
        assert before["longest_option"] <= OPTION_BUDGET, before
        # No workflow is chosen, so the start box is open; nothing is
        # published, so the run box is folded behind its sentence.
        assert before["folds"] == [["start", True], ["run", False]], before
        page.evaluate("() => document.querySelectorAll('#workflowToolbar "
                      "details').forEach(d => { d.open = true; })")
        after = page.evaluate(MEASURE)
        assert after["folds"] == [["start", True], ["run", True]], after
        assert after["overflow"] == 0 and after["body_overflow"] <= 0, after
        assert after["select_right"] <= width, after
    finally:
        assert window.problems == []
        page.context.close()


def test_the_canvas_begins_within_the_first_screen_once_a_workflow_is_chosen(
        chromium: Browser, project: _Project) -> None:
    """At 1280×800 the drawing a person is editing starts above the fold.

    The reviewer's block of forms stood over the EDITING screen -- a workflow
    chosen, its drawing on the canvas -- and the canvas began at 653 of 800.
    In that state both boxes are folded by the state itself: the start box
    because a workflow is chosen, the run box because nothing is published.
    A person who opens either gets its height back, deliberately.
    """
    page, window = _workflow_screen(chromium, project, 1280, 800)
    try:
        fresh = page.evaluate(MEASURE)
        page.locator('[data-focus="new-workflow"]').fill("laid-out")
        page.locator('[data-focus="action:onStartWorkflow"]').click()
        page.wait_for_function(
            "() => document.querySelector(\"#workflowToolbar select[name='workflow']\")"
            ".value === 'laid-out'")
        editing = page.evaluate(MEASURE)
        assert editing["folds"] == [["start", False], ["run", False]], editing
        assert editing["canvas_top"] <= 400, editing
        # And folding costs the fresh screen nothing it needs: the start box
        # is open there, and the drawing still begins well within the window.
        assert fresh["folds"] == [["start", True], ["run", False]], fresh
        assert fresh["canvas_top"] < editing["canvas_top"] + 200, fresh
    finally:
        assert window.problems == []
        page.context.close()


def test_the_chosen_starters_note_is_drawn_whole_under_the_control(
        chromium: Browser, project: _Project) -> None:
    """The caveat left the option and not the screen.

    Exactly one shipped starter carries a note and two are ready; the option
    says which is which in a few words, and the note under the control says
    the whole of it for the starter chosen -- the derived sentence naming the
    steps it read -- and changes with the choice.
    """
    page, window = _workflow_screen(chromium, project, 1280, 800)
    try:
        select = page.locator("#workflowToolbar select[name='new-from']")
        options = select.locator("option").all_inner_texts()
        values = select.locator("option").evaluate_all(
            "items => items.map(item => item.value)")
        noted = [row for row in options if row.endswith("— see the note")]
        ready = [row for row in options if row.endswith("— ready to run")]
        assert len(noted) == 1 and len(ready) == 2, options
        note = page.locator("#workflowToolbar [data-starter-note]")
        assert note.inner_text() == "A blank start is an empty drawing."
        select.select_option(values[options.index(noted[0])])
        said = note.inner_text()
        assert "4 review step(s) name no result artifact" in said, said
        assert said not in options, "the whole note is still an option's text"
        box = note.bounding_box()
        assert box is not None and box["x"] + box["width"] <= 1280, box
        assert box["y"] + box["height"] <= 800, box
        select.select_option(values[options.index(ready[0])])
        assert note.inner_text().endswith("is ready to run."), note.inner_text()
        select.select_option("")
        assert note.inner_text() == "A blank start is an empty drawing."
    finally:
        assert window.problems == []
        page.context.close()


def _active(page: Page) -> dict:
    return page.evaluate(
        "() => ({tag: document.activeElement.tagName, "
        "text: document.activeElement.innerText.trim()})")


def test_every_fold_is_reached_by_tab_and_toggled_by_enter(
        chromium: Browser, project: _Project) -> None:
    """The disclosure is the platform's, so the keyboard already drives it.

    Tab from the workflow picker lands on the start summary; Enter folds it.
    Tab onward reaches the run summary within the toolbar's own controls, and
    Enter opens the box that was folded. No script, no focus trap, and the
    focus ring the stylesheet declares is what a person sees at each stop.
    """
    page, window = _workflow_screen(chromium, project, 1280, 800)
    try:
        page.locator("#workflowToolbar select[name='workflow']").focus()
        page.keyboard.press("Tab")
        assert _active(page) == {"tag": "SUMMARY",
                                 "text": "Start a new workflow"}, _active(page)
        page.keyboard.press("Enter")
        assert page.evaluate(
            "() => document.querySelector('[data-fold=\"start\"]').open") is False
        stops = []
        for _ in range(12):
            page.keyboard.press("Tab")
            stops.append(_active(page))
            if stops[-1]["tag"] == "SUMMARY":
                break
        assert stops[-1] == {"tag": "SUMMARY",
                             "text": "Open a run — publish a revision first"}, stops
        page.keyboard.press("Enter")
        assert page.evaluate(
            "() => document.querySelector('[data-fold=\"run\"]').open") is True
        assert "A run follows a PUBLISHED revision" in page.locator(
            "#workflowToolbar [data-fold='run']").inner_text()
    finally:
        assert window.problems == []
        page.context.close()
