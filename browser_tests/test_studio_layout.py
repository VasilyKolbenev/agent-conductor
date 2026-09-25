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

The slice-3 review measured three more states and this module holds them
too: a legal 128-character workflow id must not stretch the page (the picker
is a `command-field` the first rule did not reach); the PUBLISHED state, where
the run box opens by state, must still begin the canvas within the first
screen; and a fold a person opened by hand, with the id typed into it, must
survive a frame -- the folds were recomputed from state on every render, so
the next frame closed the box and the typed id went with it.

The project is the lifecycle bench's: a served tree holding no workflow, so the
start box is the one the state opens and the run box the one it folds.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Browser, Page

from browser_tests.test_studio_lifecycle import (  # noqa: F401
    RUN_ID,
    STARTER,
    _Project,
    _Window,
    _open,
    _publish,
    _save_draft,
    _settle,
    _start_from_starter,
    project,
)
from conductor import server
from conductor.command.adapters.claude_code import CLAUDE_PROTOCOL
from conductor.command.operator_config import ProviderConfig
from conductor.command.run_store import RunStore
from tests import _fakeclaude
from browser_tests.task_picker import create_task

#: An ordinary laptop, a common desktop, and a window narrower than either.
SIZES = [(1280, 800), (1440, 900), (900, 700)]
#: The most an option may say. The longest shipped label is 49 characters;
#: the caveat that overflowed was 191.
OPTION_BUDGET = 64
#: A workflow id that fills the contract's budget (`contract_values._id`).
LONG_ID = "w" * 128
MEASURE = """() => {
  const doc = document.documentElement;
  const sel = document.querySelector('select[name="new-from"]');
  const pick = document.querySelector('#workflowToolbar select[name="workflow"]');
  const canvas = document.querySelector('#workflowCanvas');
  return {
    overflow: doc.scrollWidth - doc.clientWidth,
    body_overflow: document.body.scrollWidth - doc.clientWidth,
    select_width: Math.round(sel.getBoundingClientRect().width),
    select_right: Math.round(sel.getBoundingClientRect().right),
    picker_right: Math.round(pick.getBoundingClientRect().right),
    longest_option: Math.max(...[...sel.options].map(o => o.text.length)),
    canvas_top: Math.round(canvas.getBoundingClientRect().top),
    folds: [...document.querySelectorAll('#workflowToolbar details')]
      .map(d => [d.dataset.fold, d.open]),
    summaries: [...document.querySelectorAll('#workflowToolbar details')]
      .map(d => d.querySelector('summary').innerText),
  };
}"""
#: One `run` frame on the stream double, for a run this window is not
#: reading: it buys a read of the run list and nothing else, so the render it
#: ends in is a frame arriving from elsewhere and not anything the person did.
A_FRAME = "() => window.__stream.emit(%s)" % json.dumps(
    json.dumps({"kind": "run", "run_id": RUN_ID}))
READS_OF_THE_LIST = ("() => performance.getEntriesByType('resource')"
                     ".filter(e => e.name.endsWith('/command/runs')).length")


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
        # A legal id of 128 characters, chosen: the picker names it whole as
        # an option and the page still does not stretch (the slice-3 review
        # measured 1386px of picker in a 1280px window).
        page.locator('[data-focus="new-workflow"]').fill(LONG_ID)
        page.locator('[data-focus="action:onStartWorkflow"]').click()
        page.wait_for_function(
            "id => document.querySelector(\"#workflowToolbar select[name='workflow']\")"
            ".value === id", arg=LONG_ID)
        named = page.evaluate(MEASURE)
        assert named["overflow"] == 0 and named["body_overflow"] <= 0, named
        assert named["picker_right"] <= width, named
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
        page.wait_for_function(
            "() => document.querySelector('[data-fold=run] > summary').innerText"
            " === 'Open a run — publish a revision first'")
        editing = page.evaluate(MEASURE)
        assert editing["folds"] == [["start", False], ["run", False]], editing
        assert editing["canvas_top"] <= 400, editing
        # The folded run box says what stands in its way, for this workflow.
        assert editing["summaries"][1] == "Open a run — publish a revision first"
        # And folding costs the fresh screen nothing it needs: the start box
        # is open there, and the drawing still begins well within the window.
        assert fresh["folds"] == [["start", True], ["run", False]], fresh
        assert fresh["canvas_top"] < editing["canvas_top"] + 200, fresh
    finally:
        assert window.problems == []
        page.context.close()


@pytest.mark.parametrize("workflow_id", ["laid-out", LONG_ID], ids=["short", "128"])
def test_the_canvas_begins_within_the_first_screen_once_a_revision_is_published(
        chromium: Browser, project: _Project, workflow_id: str) -> None:
    """The state a person meets right after publishing, at 1280×800.

    The run box opens by state there -- the next thing to do is to open a run
    -- and the slice-3 review measured the canvas beginning at 945 of 800
    under it: the form's fields stood in one column, four role pickers and
    three sentences tall. In rows the same form leaves the canvas beginning
    within the first screen: measured 649 with a short id and 701 with a
    128-character one, which takes a row of its own in the picker. The
    doc's own claim is the bound -- within the first screen -- and a margin
    under it holds a return towards 945 red.
    """
    page, window = _workflow_screen(chromium, project, 1280, 800)
    try:
        _start_from_starter(page, workflow_id)
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
        page.wait_for_selector('[data-focus="run-mode"]', state="attached")
        published = page.evaluate(MEASURE)
        assert published["folds"] == [["start", False], ["run", True]], published
        assert published["summaries"][1] == (
            "Open a run — revision 1 is published"), published
        assert published["overflow"] == 0, published
        assert published["canvas_top"] < 800, published
        assert published["canvas_top"] <= 760, published
    finally:
        assert window.problems == []
        page.context.close()


def test_in_a_narrow_window_folding_the_run_box_gives_the_canvas_back(
        chromium: Browser, project: _Project) -> None:
    """At 900×700 the open run box pushes the canvas below the first screen
    (measured 734 of 700 by the fold review), which the doc now says; the
    fold is the road back, and one click on it is what this holds."""
    page, window = _workflow_screen(chromium, project, 900, 700)
    try:
        _start_from_starter(page, "narrow")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
        page.wait_for_selector('[data-focus="run-mode"]', state="attached")
        opened = page.evaluate(MEASURE)
        assert opened["folds"] == [["start", False], ["run", True]], opened
        assert opened["overflow"] == 0, opened
        page.locator('details[data-fold="run"] > summary').click()
        folded = page.evaluate(MEASURE)
        assert folded["folds"] == [["start", False], ["run", False]], folded
        assert folded["canvas_top"] < 700, folded
    finally:
        assert window.problems == []
        page.context.close()


# -- a fold opened by hand, and what is typed into it, across a frame ----------


def _the_frame_lands(page: Page) -> None:
    """Emit one frame on the double and wait for the read it buys to land."""
    before = page.evaluate(READS_OF_THE_LIST)
    page.evaluate(A_FRAME)
    page.wait_for_function(f"n => ({READS_OF_THE_LIST})() > n", arg=before)
    page.wait_for_timeout(300)


def _folds(page: Page) -> dict:
    return dict(page.evaluate(
        "() => [...document.querySelectorAll('#workflowToolbar details')]"
        ".map(d => [d.dataset.fold, d.open])"))


def test_a_fold_opened_by_hand_and_the_id_typed_into_it_survive_a_frame(
        chromium: Browser, project: _Project) -> None:
    """The fold is the person's once they touched it, and so are their words.

    A workflow is chosen, so the state folds the start box; the person opens
    it and types the next id -- mid-word, no blur. A frame arrives from
    elsewhere. The box is still open, the id is still typed, and the caret is
    still in the field.
    """
    page, window = _open(chromium, project, double=True)
    try:
        page.locator("#navWorkflow").click()
        page.locator('[data-focus="new-workflow"]').fill("laid-out")
        page.locator('[data-focus="action:onStartWorkflow"]').click()
        page.wait_for_function(
            "() => document.querySelector(\"#workflowToolbar select[name='workflow']\")"
            ".value === 'laid-out'")
        assert _folds(page) == {"start": False, "run": False}
        page.locator('details[data-fold="start"] > summary').click()
        assert _folds(page)["start"] is True
        page.locator('[data-focus="new-from"]').select_option(STARTER)
        name = page.locator('[data-focus="new-workflow"]')
        name.click()
        page.keyboard.type("my-next-flow")
        _the_frame_lands(page)
        assert _folds(page)["start"] is True
        assert page.locator('[data-focus="new-workflow"]').input_value() == "my-next-flow"
        assert page.locator('[data-focus="new-from"]').input_value() == STARTER
        assert page.evaluate("() => document.activeElement.dataset.focus") == "new-workflow"
        # The caret travels with the words: left mid-word, a frame lands, and
        # the next letters go where the caret stood (the fold review's R1).
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowLeft")
        page.keyboard.press("ArrowLeft")
        _the_frame_lands(page)
        page.keyboard.type("X")
        assert page.locator('[data-focus="new-workflow"]').input_value() == "my-nextX-flow"
        assert page.evaluate("() => document.activeElement.selectionStart") == 8
        # And the fold closed by hand stays closed through the next frame.
        page.locator('details[data-fold="start"] > summary').click()
        assert _folds(page)["start"] is False
        _the_frame_lands(page)
        assert _folds(page)["start"] is False
    finally:
        assert window.problems == []
        page.context.close()


def _compose(page: Page, key: str) -> str:
    """Type `run` through an IME -- three composition updates, then the
    commit -- into one control, the way a Japanese, Chinese or Korean
    keyboard delivers ASCII, and answer what the control holds."""
    page.locator(f'[data-focus="{key}"]').click()
    cdp = page.context.new_cdp_session(page)
    for text in ("r", "ru", "run"):
        cdp.send("Input.imeSetComposition",
                 {"text": text, "selectionStart": len(text),
                  "selectionEnd": len(text)})
    cdp.send("Input.insertText", {"text": "run"})
    cdp.detach()
    return page.locator(f'[data-focus="{key}"]').input_value()


def test_an_ime_composition_lands_once_in_the_toolbars_fields(
        chromium: Browser, project: _Project) -> None:
    """A render per keystroke doubled every composition update (the fold
    review's R2: `rrurunrun` for `run`). Committed on change, the field holds
    exactly what was composed, and a frame carries it whole."""
    page, window = _open(chromium, project, double=True)
    try:
        page.locator("#navWorkflow").click()
        page.wait_for_selector('[data-focus="new-workflow"]')
        assert _compose(page, "new-workflow") == "run"
        _the_frame_lands(page)
        assert page.locator('[data-focus="new-workflow"]').input_value() == "run"
        _start_from_starter(page, "composed")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('[data-focus="run-id"]', state="attached")
        assert _compose(page, "run-id") == "run"
        page.keyboard.press("Tab")
        _the_frame_lands(page)
        assert page.locator('[data-focus="run-id"]').input_value() == "run"
    finally:
        assert window.problems == []
        page.context.close()


def test_the_run_forms_typed_facts_survive_a_frame(
        chromium: Browser, project: _Project) -> None:
    """The run form, open by state after a publish, keeps what was chosen.

    A run id typed mid-word and an authority chosen from the ladder are
    still there after a frame, and a person who folded the box by hand finds
    it folded.
    """
    page, window = _open(chromium, project, double=True)
    try:
        _start_from_starter(page, "laid-out")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('[data-focus="run-mode"]', state="attached")
        assert _folds(page)["run"] is True
        page.locator('[data-focus="run-mode"]').select_option("confirm")
        page.locator('[data-focus="cycle-id"]').fill("cycle-typed")
        page.locator('[data-focus="run-id"]').click()
        page.keyboard.type("runtyped")
        for _ in range(5):
            page.keyboard.press("ArrowLeft")
        _the_frame_lands(page)
        page.keyboard.type("-x")
        assert page.locator('[data-focus="run-id"]').input_value() == "run-xtyped"
        assert page.evaluate("() => document.activeElement.selectionStart") == 5
        assert page.locator('[data-focus="cycle-id"]').input_value() == "cycle-typed"
        assert page.locator('[data-focus="run-mode"]').input_value() == "confirm"
        assert "Every effecting step waits for a person" in page.locator(
            "#workflowToolbar [data-fold='run']").inner_text()
        # A toggle by keyboard keeps the keyboard on the summary it pressed
        # (the fold review's R3), and one Tab from the opened box lands on
        # its first field rather than at the top of the toolbar.
        page.locator('details[data-fold="run"] > summary').focus()
        page.keyboard.press("Enter")
        assert _folds(page)["run"] is False
        assert page.evaluate("() => document.activeElement.dataset.focus") == "fold:run"
        _the_frame_lands(page)
        assert _folds(page)["run"] is False
        page.keyboard.press("Enter")
        assert _folds(page)["run"] is True
        assert page.evaluate("() => document.activeElement.dataset.focus") == "fold:run"
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement.dataset.focus") == "run-id"
    finally:
        assert window.problems == []
        page.context.close()


@pytest.fixture
def configured_project(monkeypatch, tmp_path, request) -> _Project:
    """One available deterministic provider, configured through the real door.

    It is never executed here: the subject is a participant selection, not a
    real vendor installation or a smoke run.
    """
    executable = _fakeclaude.build_executable(tmp_path)
    assert executable is not None, "the native fake executable is required"
    configured = ProviderConfig(provider_id="claude-code",
        executable=str(executable), protocol=CLAUDE_PROTOCOL, env_allow=())
    build = server.build

    def configured_build(root, port, **kwargs):
        kwargs.pop("registry", None)
        return build(root, port, providers=[configured], **kwargs)

    monkeypatch.setattr(server, "build", configured_build)
    return request.getfixturevalue("project")


def test_a_role_unbound_by_the_person_stays_unbound_after_a_frame(
        chromium: Browser, configured_project: _Project) -> None:
    """Binding and then clearing a role replaces, rather than merges, facts.

    The read is real; the stream double only delivers its notification. No
    run is opened: silently resurrecting a participant already fails here.
    """
    page, window = _open(chromium, configured_project, double=True)
    try:
        _start_from_starter(page, "roles-again")
        _save_draft(page)
        _publish(page)
        pick = page.locator('[data-focus^="role-"]').first
        pick.wait_for(state="visible")
        key = pick.get_attribute("data-focus")
        pick.select_option("claude-code")
        _the_frame_lands(page)
        assert page.locator(f'[data-focus="{key}"]').input_value() == "claude-code"
        page.locator(f'[data-focus="{key}"]').select_option("")
        _the_frame_lands(page)
        assert page.locator(f'[data-focus="{key}"]').input_value() == ""
        assert window.writes("/open") == 0
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
        assert len(noted) == 1 and len(ready) == 4, options
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
        # The render the toggle provokes gives the keyboard its summary back.
        assert _active(page) == {"tag": "SUMMARY", "text": "Start a new workflow"}
        stops = []
        for _ in range(12):
            page.keyboard.press("Tab")
            stops.append(_active(page))
            if stops[-1]["tag"] == "SUMMARY":
                break
        # No workflow is chosen on this screen, so the first thing to do is
        # not to publish but to choose or start one, and the fold says so.
        assert stops[-1] == {"tag": "SUMMARY",
                             "text": "Open a run — choose or start a workflow first"
                             }, stops
        page.keyboard.press("Enter")
        assert page.evaluate(
            "() => document.querySelector('[data-fold=\"run\"]').open") is True
        assert "A run follows a PUBLISHED revision" in page.locator(
            "#workflowToolbar [data-fold='run']").inner_text()
    finally:
        assert window.problems == []
        page.context.close()


def _model_form(page: Page, workflow_id: str) -> list[str]:
    create_task(page)
    _start_from_starter(page, workflow_id)
    _save_draft(page)
    _publish(page)
    page.wait_for_selector('[data-focus="run-mode"]', state="attached")
    roles = page.locator('[data-focus^="role-"]').evaluate_all(
        "items => items.map(item => item.dataset.focus.slice(5))")
    assert roles and page.locator('[data-focus^="model-"]').count() == len(roles)
    for role in roles:
        page.locator(f'[data-focus="role-{role}"]').select_option("claude-code")
    return roles


def test_each_roles_model_reaches_the_open_request_and_frozen_read_back(
        chromium: Browser, configured_project: _Project) -> None:
    """A chosen full id is frozen; a sibling blank means unpinned, not a guess."""
    page, window = _open(chromium, configured_project, double=True)
    try:
        roles = _model_form(page, "model-pins")
        assert len(roles) >= 2
        page.locator('[data-focus="run-id"]').fill("run-model-pins")
        page.locator('[data-focus="cycle-id"]').fill("cycle-model-pins")
        model = "claude-reviewed-20260907"
        page.locator(f'[data-focus="model-{roles[0]}"]').fill(model)
        # A single click from the still-focused model field must submit.
        with page.expect_response(lambda response: response.request.method == "POST"
                                  and response.url.endswith("/command/runs")) as opened:
            page.locator('[data-focus="action:onOpenRun"]').click()
        assert opened.value.status == 201, opened.value.json()
        posted = window.posted("/command/runs")[-1]["participants"]
        assert {row["instance_id"]: row["model"] for row in posted} == {
            f"instance-{role}": model if role == roles[0] else None for role in roles}
        recovered = RunStore(configured_project.root).read("run-model-pins")
        assert {row["id"]: row.get("model") for row in recovered.config["instances"]} == {
            f"instance-{role}": model if role == roles[0] else None for role in roles}
        assert all("model" not in row for row in recovered.config["instances"]
                   if row["id"] != f"instance-{roles[0]}")
        page.reload(wait_until="load")
        _settle(page)
        page.locator("#navRuns").click()
        from browser_tests.run_picker import choose_run
        choose_run(page, "run-model-pins")
        page.locator('[data-run-lens="orbit"]').click()
        page.locator(f'[data-instance="instance-{roles[0]}"]').click()
        page.locator("#studioParticipantInspector").get_by_text("Parameters", exact=True).click()
        page.wait_for_function("model => document.querySelector('#screenRuns')"
                               ".innerText.includes(model)", arg=model)
    finally:
        assert window.problems == []
        page.context.close()


def test_a_roles_model_keeps_its_caret_but_not_a_replaced_harness_binding(
        chromium: Browser, configured_project: _Project) -> None:
    """Frames/reconnect retain words; changing the harness discards its pin."""
    page, window = _open(chromium, configured_project, double=True)
    try:
        roles = _model_form(page, "model-draft")
        key = f"model-{roles[0]}"
        model = page.locator(f'[data-focus="{key}"]')
        assert "unpinned" in model.get_attribute("placeholder")
        model.fill("model-ab")
        model.press("ArrowLeft")
        _the_frame_lands(page)
        page.keyboard.type("X")
        assert model.input_value() == "model-aXb"
        assert page.evaluate("() => document.activeElement.selectionStart") == 8
        model.fill("")
        assert _compose(page, key) == "run"
        page.keyboard.press("Tab")
        page.evaluate("() => { window.__stream.fire('error'); window.__stream.fire('open'); }")
        _the_frame_lands(page)
        assert model.input_value() == "run"
        pick = page.locator(f'[data-focus="role-{roles[0]}"]')
        pick.select_option("")
        _the_frame_lands(page)
        assert model.input_value() == "" and model.is_disabled()
        pick.select_option("claude-code")
        assert model.input_value() == "" and model.is_enabled()
        assert window.writes("/command/runs") == 0
    finally:
        assert window.problems == []
        page.context.close()


def test_a_model_outside_the_existing_identifier_contract_cannot_be_submitted(
        chromium: Browser, configured_project: _Project) -> None:
    """The UI checks syntax, not whether a vendor offers a model today."""
    page, window = _open(chromium, configured_project, double=True)
    try:
        roles = _model_form(page, "model-syntax")
        page.locator('[data-focus="run-id"]').fill("run-model-syntax")
        page.locator('[data-focus="cycle-id"]').fill("cycle-model-syntax")
        model = page.locator(f'[data-focus="model-{roles[0]}"]')
        for invalid in ("--flag", "vendor/model", "a b", "x" * 129):
            model.evaluate("(field, value) => { field.value = value; }", invalid)
            if len(invalid) <= 128:
                assert model.evaluate("field => field.validity.patternMismatch")
            assert not model.evaluate("field => field.checkValidity()")
            page.locator('[data-focus="action:onOpenRun"]').click()
            assert window.writes("/command/runs") == 0
        model.fill("Model.7_2026-09")
        assert model.evaluate("field => field.checkValidity()")
    finally:
        assert window.problems == []
        page.context.close()


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_real_toolbar_fields_share_the_inspector_surface(
        chromium: Browser, project: _Project, theme: str) -> None:
    """Read computed paint on real controls, not a list of CSS selectors."""
    page, window = _workflow_screen(chromium, project, 1280, 800)
    try:
        page.emulate_media(color_scheme=theme)
        # Found and measured in ONE evaluation, as the Overview geometry is: a live render
        # replaces these fields, and a locator's evaluate_all finds in one round trip and
        # measures in the next (browser_tests/test_studio_demo.py, _overview_geometry).
        painted = page.evaluate("""() => [...document.querySelectorAll(
            '#workflowToolbar .command-field input, #workflowToolbar .command-field select')]
          .map(field => {
          const style = getComputedStyle(field);
          const well = getComputedStyle(document.querySelector('#workflowCanvas'));
          return {background: style.backgroundColor, surface: well.backgroundColor,
            size: parseFloat(style.fontSize), height: field.getBoundingClientRect().height,
            visible: field.getClientRects().length > 0};
        })""")
        shown = [row for row in painted if row["visible"]]
        assert len(shown) >= 3, "the real picker and new-workflow fields disappeared"
        assert all(row["background"] == row["surface"] for row in shown), shown
        assert all(row["size"] >= 13 and row["height"] >= 44 for row in shown), shown
    finally:
        assert window.problems == []
        page.context.close()


def test_canvas_help_is_keyboard_accessible_and_keeps_its_fold_over_frames(
        chromium: Browser, project: _Project) -> None:
    """Disclosure is local UI state; opening it must not write or reset focus."""
    page, window = _open(chromium, project, double=True)
    page.set_viewport_size({"width": 1280, "height": 800})
    try:
        _start_from_starter(page, "help-fold")
        help_box = page.locator(".studio-canvas__help")
        assert help_box.count() == 1, "canvas instructions need a native disclosure"
        summary = help_box.locator("summary")
        assert not help_box.evaluate("node => node.open")
        before = window.posted("/command/")
        summary.focus()
        page.keyboard.press("Enter")
        assert help_box.evaluate("node => node.open")
        assert page.locator(".studio-canvas__keys").is_visible()
        assert "Drag a step to place it" in help_box.inner_text()
        _the_frame_lands(page)
        assert help_box.evaluate("node => node.open")
        assert summary.evaluate("node => node === document.activeElement")
        page.keyboard.press("Enter")
        _the_frame_lands(page)
        assert not help_box.evaluate("node => node.open")
        assert summary.evaluate("node => node === document.activeElement")
        assert window.posted("/command/") == before, "a help gesture crossed a write door"
    finally:
        assert window.problems == []
        page.context.close()


def test_a_real_step_not_just_the_canvas_container_is_above_the_fold(
        chromium: Browser, project: _Project) -> None:
    """At laptop size the editor shows a whole step without scrolling first."""
    page, window = _workflow_screen(chromium, project, 1280, 800)
    try:
        _start_from_starter(page, "visible-step")
        # MEASURED on the first remote run (frozen-19, Ubuntu): every step read off-screen -- the
        # answer detached nodes give, and the find-then-measure race proven on the Overview. One
        # evaluation finds and measures, so a red here now is a layout fact, not that race.
        drawn = page.evaluate("""() => {
          const nodes = [...document.querySelectorAll('.studio-node')];
          const well = document.querySelector('#workflowCanvas').getBoundingClientRect();
          return nodes.map(node => {
            const r = node.getBoundingClientRect();
            return r.top >= 0 && r.bottom <= innerHeight && r.left >= well.left
              && r.right <= well.right;
          });
        }""")
        assert drawn and any(drawn), "toolbar chrome pushed every real step off-screen"
    finally:
        assert window.problems == []
        page.context.close()


def test_header_and_toolbar_save_share_the_drafts_real_availability(
        chromium: Browser, project: _Project) -> None:
    """A prominent save must not offer a known refusal or a duplicate write."""
    page, window = _workflow_screen(chromium, project, 1280, 800)
    try:
        _start_from_starter(page, "primary-save")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
        header = page.locator('#studioPrimary [data-focus="action:onSaveDraft"]')
        toolbar = page.locator('#workflowToolbar [data-focus="action:onSaveDraft"]')
        assert header.is_disabled() and toolbar.is_disabled(), "no draft exists to save"
        assert header.get_attribute("title") == toolbar.get_attribute("title")
        assert "Edit as new draft" in header.get_attribute("title")
        page.locator('[data-focus="action:onEditPublished"]').click()
        page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
        assert header.is_enabled() and toolbar.is_enabled(), "a drawing can be saved"
        parked = []
        page.route("**/command/workflows/primary-save/draft",
                   lambda route: parked.append(route) if route.request.method == "POST"
                   else route.continue_())
        with page.expect_request(lambda request: request.method == "POST"
                                 and request.url.endswith("/primary-save/draft")):
            header.click()
        # The route callback follows the request event, not the local disabled UI.
        for _ in range(40):
            if parked:
                break
            page.wait_for_timeout(25)
        assert len(parked) == 1, "the draft POST never reached the held route"
        assert header.is_disabled() and toolbar.is_disabled()
        assert "being saved" in header.get_attribute("title")
        assert header.get_attribute("title") == toolbar.get_attribute("title")
        parked.pop().continue_()
        page.wait_for_selector('#workflowToolbar [data-save="saved"]')
        assert header.is_enabled() and toolbar.is_enabled()
    finally:
        assert window.problems == []
        page.context.close()
