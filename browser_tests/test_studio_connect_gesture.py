"""A connection drag belongs to the drawing it began on, whatever renders meanwhile.

Measured in review of the CI3 slice (26.09): the third task read of the Studio's start,
answered between pointerdown and pointerup, redrew the canvas. The port holding the
pointer was replaced, its own `pointerup` never came, and the drag wrote nothing, with no
error anywhere. A person gets no warning that a read is about to land. The drag's end is
now heard on the document for the gesture's life (studio-canvas.js, `bindConnectDrag`)
and judged against the drawing on screen then.

Every case uses real mouse events. The task answer is the server's own, held and then
let go, never replaced: an ordinary drag; the unrelated answer landing mid-drag; and a
different document chosen mid-drag, which must take nothing from a gesture begun on
another.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, expect

from conductor import server
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from browser_tests.test_studio_editing import (  # noqa: F401 -- fixtures register
    _COUNT_TASK_ASKS, DRAFT, SAVED_AT, WORKFLOW_ID, _Bench, _centres, _drag, _open_bench,
    bench, studio_url)
from tests.test_store import good_lane, write_project

#: A second editable draft drawn exactly like the first, so a step named `beta` stands
#: under the pointer in either document.
OTHER_ID = "editing-bench-other"

#: The start's THIRD real task answer held as it came, until the test lets it go -- and its
#: SECOND held until the third ask has begun. Each ask shows the "Reading tasks" row, and only
#: an answer landing after the LAST ask hides it (studio-taskflow.js, `refreshTasks`). On the
#: Ubuntu gate (CI run 36391406861), the row stayed visible. A controlled probe reproduced
#: this when answers 1 and 2 landed before ask 3; CI did not trace their order. Answer 2 lands after
#: ask 3 in either order of arrival -- the barrier remembers that ask 3 began -- and
#: `secondApplied` says so once the page has drawn it; the held third answer is then the only
#: task render left for the test to let go.
_HOLD_THIRD_TASK_ANSWER = """(() => {
  const read = window.fetch.bind(window);
  const held = window.heldAnswer = {asked: 0, held: false, thirdAsked: false,
    secondApplied: false};
  let letSecondGo = null;
  const drawn = (response) => {
    const parse = response.json.bind(response);
    response.json = () => {
      const body = parse();
      body.then(() => setTimeout(() => { held.secondApplied = true; }), () => {});
      return body;
    };
    return response;
  };
  window.fetch = (target, options) => {
    const answer = read(target, options);
    if (target !== "/command/tasks") return answer;
    const asked = ++held.asked;
    if (asked === 2) return answer.then((response) => new Promise((resolve) => {
      letSecondGo = () => resolve(drawn(response));
      if (held.thirdAsked) letSecondGo();
    }));
    if (asked !== 3) return answer;
    held.thirdAsked = true;
    if (letSecondGo) letSecondGo();
    return answer.then((response) => new Promise((resolve) => {
      held.held = true;
      window.releaseHeldAnswer = () => resolve(response);
    }));
  };
})()"""

#: The port the next press lands on, and the pointer that pressed it.
_NOTE_THE_GRIP = """() => document.addEventListener("pointerdown", (event) => {
  window.grip = {port: event.target.closest("[data-port]"), pointer: event.pointerId};
}, {capture: true, once: true})"""

_GRIPPED = """() => ({held: window.grip.port.hasPointerCapture(window.grip.pointer),
  attached: window.grip.port.isConnected})"""


@pytest.fixture
def two_drafts_url(tmp_path) -> Iterator[str]:
    """The editing bench's server, over a project holding the same draft twice."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    for workflow_id in (WORKFLOW_ID, OTHER_ID):
        TemplateStore(root).save_draft(WorkflowDraft(
            workflow_id=workflow_id, saved_at=SAVED_AT, document=DRAFT))
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "studio server did not stop"


@pytest.fixture
def held_bench(chromium: Browser, two_drafts_url: str) -> Iterator[_Bench]:
    """The editing bench on the first draft, with the start's third task answer held."""
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    context.add_init_script(_COUNT_TASK_ASKS)
    context.add_init_script(_HOLD_THIRD_TASK_ANSWER)
    try:
        bench = _open_bench(context, two_drafts_url)
        bench.page.wait_for_function(
            "() => window.heldAnswer.held === true && window.heldAnswer.secondApplied === true")
        yield bench
    finally:
        context.close()


def _press_on_the_port(page: Page) -> tuple[tuple[float, float], tuple[float, float]]:
    start, end = _centres(page, '[data-port="alpha"]', '[data-node-id="beta"]')
    page.evaluate(_NOTE_THE_GRIP)
    page.mouse.move(*start)
    page.mouse.down()
    assert page.evaluate(_GRIPPED) == {"held": True, "attached": True}
    return start, end


def _release_over(page: Page, start: tuple[float, float], end: tuple[float, float]) -> None:
    page.mouse.move((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, steps=6)
    page.mouse.move(*end, steps=6)
    page.mouse.up()


def test_an_ordinary_connection_drag_draws_its_connection(held_bench: _Bench) -> None:
    """The control: the held answer is let go and drawn BEFORE the press, so nothing
    redraws the canvas during the gesture."""
    page = held_bench.page
    page.evaluate("() => { window.drawnBefore = document.querySelector('[data-port=\"alpha\"]'); }")
    page.evaluate("() => window.releaseHeldAnswer()")
    page.wait_for_function("() => window.drawnBefore.isConnected === false")
    start, end = _centres(page, '[data-port="alpha"]', '[data-node-id="beta"]')
    _drag(page, start, end)
    held_bench.wait_for_edges(1)
    assert held_bench.edge_ids() == ["alpha beta"]
    assert held_bench.problems == []


def test_a_task_answer_landing_mid_drag_does_not_cost_the_connection(
        held_bench: _Bench) -> None:
    """Pressed on alpha's port, the held answer let go: its render replaces the port that
    holds the pointer. The release over beta still draws the connection."""
    page = held_bench.page
    start, end = _press_on_the_port(page)
    page.evaluate("() => window.releaseHeldAnswer()")
    page.wait_for_function("() => window.grip.port.isConnected === false")
    assert page.evaluate(_GRIPPED) == {"held": False, "attached": False}
    _release_over(page, start, end)
    held_bench.wait_for_edges(1)
    assert held_bench.edge_ids() == ["alpha beta"]
    assert held_bench.problems == []


def test_a_drag_begun_on_one_draft_writes_nothing_into_another(held_bench: _Bench) -> None:
    """Pressed on the first draft's port, then the other draft chosen through the toolbar's
    own control: the release lands on a `beta` of a document the gesture never began on,
    and neither document gains a connection."""
    page = held_bench.page
    start, end = _press_on_the_port(page)
    page.evaluate("""other => {
      const pick = document.querySelector("#workflowToolbar select[name='workflow']");
      pick.value = other;
      pick.dispatchEvent(new Event("change", {bubbles: true}));
    }""", OTHER_ID)
    _drawn(page, OTHER_ID)
    _release_over(page, start, end)
    assert held_bench.edge_ids() == []
    page.locator("#workflowToolbar select[name='workflow']").select_option(WORKFLOW_ID)
    _drawn(page, WORKFLOW_ID)
    assert held_bench.edge_ids() == []
    assert held_bench.problems == []


def test_a_press_whose_release_never_came_arms_nothing_for_the_next_click(
        bench: _Bench) -> None:
    """Found in review of this fix: a press on a port whose release the page never got (the
    window lost the mouse mid-drag) left the gesture's end listening on the document, and the
    person's next ordinary click on a step wrote a connection nobody drew. Trusted input
    through the browser's own road: the mouse comes back with no button down, then clicks
    beta. The click's press ends the lost gesture, writing nothing, and selects its step."""
    page = bench.page
    start, end = _centres(page, '[data-port="alpha"]', '[data-node-id="beta"]')
    session = page.context.new_cdp_session(page)

    def mouse(kind: str, at: tuple[float, float], button: str, buttons: int) -> None:
        session.send("Input.dispatchMouseEvent", {"type": kind, "x": at[0], "y": at[1],
                                                  "button": button, "buttons": buttons,
                                                  "clickCount": 1})

    mouse("mouseMoved", start, "none", 0)
    mouse("mousePressed", start, "left", 1)   # its release never reaches the page
    mouse("mouseMoved", end, "none", 0)
    mouse("mousePressed", end, "left", 1)
    mouse("mouseReleased", end, "left", 0)
    expect(page.locator('[data-node-id="beta"]')).to_have_attribute("aria-pressed", "true")
    assert bench.edge_ids() == []
    assert bench.problems == []
    session.detach()


def test_a_touch_drag_from_a_port_draws_its_connection(
        chromium: Browser, two_drafts_url: str) -> None:
    """Found by review, and older than the fix above: with no `touch-action` on the port the
    browser took a touch drag as a page pan and cancelled the pointer, so a finger could not
    connect two steps and was told nothing. Real touch input through the browser's own road."""
    context = chromium.new_context(viewport={"width": 1700, "height": 1400}, has_touch=True)
    context.add_init_script(_COUNT_TASK_ASKS)
    try:
        bench = _open_bench(context, two_drafts_url)
        page = bench.page
        start, end = _centres(page, '[data-port="alpha"]', '[data-node-id="beta"]')
        session = context.new_cdp_session(page)
        for step in range(13):
            at = {"x": start[0] + (end[0] - start[0]) * step / 12,
                  "y": start[1] + (end[1] - start[1]) * step / 12, "id": 1}
            session.send("Input.dispatchTouchEvent", {
                "type": "touchStart" if step == 0 else "touchMove", "touchPoints": [at]})
        session.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
        bench.wait_for_edges(1)
        assert bench.edge_ids() == ["alpha beta"]
        assert bench.problems == []
    finally:
        context.close()


def _drawn(page: Page, workflow_id: str) -> None:
    """That draft read and on screen, editable, its `beta` in place -- visible facts only.
    Choosing shuts the write door at once (studio.js, `refreshWorkflow`); only the new
    draft's read opens it again."""
    expect(page.locator("#workflowToolbar select[name='workflow']")).to_have_value(workflow_id)
    page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
    page.wait_for_function("() => document.querySelectorAll('[data-node-id]').length === 3")
