"""The canvas's two other pointer gestures keep their whole life through the renders around them.

Found by review of the CI3 slice and confirmed on d945c11, beside the connect drag
(test_studio_connect_gesture.py): a background drag panned by its FIRST pointermove only,
because the pan's own view change redrew the stage holding the gesture; and a step's move
drag was lost whenever an unrelated read landed mid-drag. Both now live on the document for
the gesture's life (studio-canvas.js, `follow`) and change only the drawing they began on.

Real mouse events throughout; the task answer is the server's own, held and let go. Each
gesture is also taken past the two ways it can end badly: another document chosen mid-drag,
and a release the page never got (the mouse comes back with no button held).
"""
from __future__ import annotations

from playwright.sync_api import Page, expect

from browser_tests.test_studio_connect_gesture import (  # noqa: F401 -- fixtures register
    OTHER_ID, _drawn, held_bench, two_drafts_url)
from browser_tests.test_studio_editing import (  # noqa: F401 -- fixtures register
    WORKFLOW_ID, _Bench, _centres, bench, studio_url)
from browser_tests.test_studio_positions import _placed_at

STAGE = '[data-focus="canvas-stage"]'

#: A point on the drawing's background: on the stage, on no step, port or connection.
_BACKGROUND = """() => {
  const box = document.querySelector('[data-focus="canvas-stage"]').getBoundingClientRect();
  for (let y = Math.ceil(box.top) + 20; y < box.bottom - 20; y += 10)
    for (let x = Math.ceil(box.left) + 20; x < box.right - 20; x += 10) {
      const hit = document.elementFromPoint(x, y);
      if (hit && hit.closest('[data-focus="canvas-stage"]')
          && !hit.closest("[data-node-id],[data-port],[data-edge]")) return [x, y];
    }
  return null;
}"""

#: The pan the drawing on screen is placed by, read off its own transform.
_PAN = """() => {
  const moved = /translate\\(([-\\d.]+)px, ([-\\d.]+)px\\)/.exec(
    document.querySelector('[data-focus="canvas-stage"]').style.transform);
  return [Math.round(moved[1] * 100) / 100, Math.round(moved[2] * 100) / 100];
}"""


#: Where the step alpha drawn NOW is shown dragged to (its transform), "" when it is not.
_SHOWN_AT = "() => document.querySelector('[data-node-id=\"alpha\"]').style.transform"


#: The step alpha drawn now: its box on screen, its transform and the place it is set at.
_DRAWN_ALPHA = """() => {
  const step = document.querySelector('[data-node-id="alpha"]'), box = step.getBoundingClientRect();
  return {x: box.x, y: box.y, transform: step.style.transform,
    at: [step.style.getPropertyValue('--x'), step.style.getPropertyValue('--y')]};
}"""


def _mark(page: Page, selector: str) -> None:
    page.evaluate("s => { window.marked = document.querySelector(s); }", selector)


def _redrawn(page: Page) -> None:
    page.wait_for_function("() => window.marked.isConnected === false")


def _choose(page: Page, workflow_id: str) -> None:
    """The other draft chosen through the toolbar's own control, the mouse still held."""
    page.evaluate("""other => {
      const pick = document.querySelector("#workflowToolbar select[name='workflow']");
      pick.value = other;
      pick.dispatchEvent(new Event("change", {bubbles: true}));
    }""", workflow_id)
    _drawn(page, workflow_id)


def _cdp_mouse(page: Page):
    session = page.context.new_cdp_session(page)

    def send(kind: str, at: tuple[float, float], button: str = "none", buttons: int = 0):
        session.send("Input.dispatchMouseEvent", {"type": kind, "x": at[0], "y": at[1],
                                                  "button": button, "buttons": buttons,
                                                  "clickCount": 1})
    return send


def test_a_background_drag_pans_its_whole_distance_through_the_renders_around_it(
        held_bench: _Bench) -> None:
    """100px in ten moves is 100px: every move redraws the stage, and an unrelated answer
    let go mid-drag redraws it once more. The release ends the pan."""
    page = held_bench.page
    x, y = page.evaluate(_BACKGROUND)
    before = page.evaluate(_PAN)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 50, y, steps=5)
    _mark(page, STAGE)
    page.evaluate("() => window.releaseHeldAnswer()")
    _redrawn(page)
    page.mouse.move(x + 100, y, steps=5)
    assert page.evaluate(_PAN) == [before[0] + 100, before[1]]
    page.mouse.up()
    page.mouse.move(x + 160, y, steps=3)
    assert page.evaluate(_PAN) == [before[0] + 100, before[1]]
    assert held_bench.problems == []


def test_a_pan_begun_on_one_draft_stops_once_another_is_on_screen(held_bench: _Bench) -> None:
    page = held_bench.page
    x, y = page.evaluate(_BACKGROUND)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 40, y, steps=4)
    _choose(page, OTHER_ID)
    shown = page.evaluate(_PAN)
    page.mouse.move(x + 100, y, steps=6)
    assert page.evaluate(_PAN) == shown
    page.mouse.up()
    assert held_bench.problems == []


def test_a_pan_whose_release_never_came_does_not_follow_the_mouse_back(bench: _Bench) -> None:
    """The mouse comes back with no button held: the pan is over, and hovering moves nothing."""
    page = bench.page
    x, y = page.evaluate(_BACKGROUND)
    before = page.evaluate(_PAN)
    mouse = _cdp_mouse(page)
    mouse("mouseMoved", (x, y))
    mouse("mousePressed", (x, y), "left", 1)
    mouse("mouseMoved", (x + 50, y), "left", 1)
    assert page.evaluate(_PAN) == [before[0] + 50, before[1]]
    mouse("mouseMoved", (x + 80, y))
    mouse("mouseMoved", (x + 150, y))
    assert page.evaluate(_PAN) == [before[0] + 50, before[1]]
    assert bench.problems == []


def test_a_step_move_lands_when_a_task_answer_lands_mid_drag(held_bench: _Bench) -> None:
    """Pressed on alpha, the held answer let go: its render replaces the step being dragged.
    The drag goes on showing on the step now drawn, and the release places it."""
    page = held_bench.page
    before = _placed_at(page, "alpha")
    [(x, y)] = _centres(page, '[data-node-id="alpha"]')
    _mark(page, '[data-node-id="alpha"]')
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 150, y, steps=6)
    page.evaluate("() => window.releaseHeldAnswer()")
    _redrawn(page)
    page.mouse.move(x + 300, y, steps=6)
    assert page.evaluate(_SHOWN_AT) == "translate(300px, 0px)"
    page.mouse.up()
    page.wait_for_function(
        "was => parseFloat(document.querySelector('[data-node-id=\"alpha\"]')"
        ".style.getPropertyValue('--x')) > was", arg=before[0])
    assert held_bench.problems == []


def test_a_step_move_begun_on_one_draft_moves_nothing_in_another(held_bench: _Bench) -> None:
    page = held_bench.page
    first = _placed_at(page, "alpha")
    [(x, y)] = _centres(page, '[data-node-id="alpha"]')
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 150, y, steps=6)
    _choose(page, OTHER_ID)
    other = _placed_at(page, "alpha")
    # Where the other draft's alpha is DRAWN, read again while the old gesture goes on: before
    # the release, when a transform it lent that step would still be showing.
    drawn = page.evaluate(_DRAWN_ALPHA)
    page.mouse.move(x + 300, y, steps=6)
    assert page.evaluate(_DRAWN_ALPHA) == drawn
    page.mouse.up()
    assert _placed_at(page, "alpha") == other
    page.locator("#workflowToolbar select[name='workflow']").select_option(WORKFLOW_ID)
    _drawn(page, WORKFLOW_ID)
    assert _placed_at(page, "alpha") == first
    assert held_bench.problems == []


def test_a_step_drag_whose_release_never_came_moves_nothing_and_takes_no_later_click(
        bench: _Bench) -> None:
    """Dragged, then the mouse comes back with no button held: nothing is placed, the step is
    drawn where it stands, and the next ordinary activation -- keyboard, then pointer -- still
    selects its step."""
    page = bench.page
    before = _placed_at(page, "alpha")
    [(x, y)] = _centres(page, '[data-node-id="alpha"]')
    mouse = _cdp_mouse(page)
    mouse("mouseMoved", (x, y))
    mouse("mousePressed", (x, y), "left", 1)
    mouse("mouseMoved", (x + 150, y), "left", 1)
    mouse("mouseMoved", (x + 160, y))
    assert _placed_at(page, "alpha") == before
    assert page.evaluate(_SHOWN_AT) == ""
    page.locator('[data-node-id="alpha"]').focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-node-id="alpha"]')).to_have_attribute("aria-pressed", "true")
    [(bx, by)] = _centres(page, '[data-node-id="beta"]')
    mouse("mouseMoved", (bx, by))
    mouse("mousePressed", (bx, by), "left", 1)
    mouse("mouseReleased", (bx, by), "left", 0)
    expect(page.locator('[data-node-id="beta"]')).to_have_attribute("aria-pressed", "true")
    assert _placed_at(page, "alpha") == before
    assert bench.problems == []
