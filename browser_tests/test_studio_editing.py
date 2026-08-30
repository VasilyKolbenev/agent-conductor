"""Editing a workflow in a real Chromium: the canvas, the inspector, and refusal.

The Studio's editing surface makes one promise the source gates cannot check:
every editing road exists TWICE, once for a pointer and once for a keyboard.
``studio-canvas.KEY_LEGEND`` writes that promise on the canvas itself. This
module drives both roads against the real loopback server, with a real draft
read out of the real ``TemplateStore``, and counts what changed in the drawing.

FOUR TESTS HERE WERE WRITTEN RED, against three production defects this module
found by rendering the surface. All three are fixed and all four are green now,
and each one is kept as the guard that holds its fix closed. What each caught,
so a reader meeting the test later knows why it is worded the way it is:

- ``test_a_drag_from_a_port_onto_another_step_connects_the_two`` --
  ``studio.css`` declared no rule for ``.studio-port``, so every connect handle
  kept ``position: static``, piled up at the stage's origin and was painted
  over by the absolutely positioned steps. The canvas's connect gesture was
  unreachable by pointer.
- ``test_two_steps_in_one_column_never_overlap_on_screen`` -- a step rendered
  158px tall against a 148px row pitch, so every step in a column was drawn on
  top of the one above it.
- ``test_enter_on_a_connection_selects_it_and_delete_removes_it`` and
  ``test_a_keystroke_that_changes_nothing_never_calls_the_draft_unsaved`` --
  ``editKey`` spelled a delete-edge edit with ``{from, to}`` while the reducer
  read ``{fromId, toId}``, so the keyboard road for removing a connection was
  dead AND reported itself as an edit.

One asymmetry is by design rather than a defect: a connection cannot be made
from the canvas by keyboard -- the port answers a click with a sentence and
connects only on a drag -- and the legend sends a keyboard reader to the
inspector's Transitions section instead. That control is proved reachable by
Tab and operable by Enter below, so the CAPABILITY is keyboard-complete.

WHAT MOVED OUT. This module crossed 800 lines carrying two circuits, so the
second one went to ``browser_tests/test_studio_refusal.py``: everything about
what this window will NOT write -- the inspector edit that stays in the tab
until a Human asks for it, the name the inspector refuses outright, the
immutable published revision, and the two diagnostic lists that are never
merged. The seam is real rather than convenient: what is left here is the
editing gestures themselves, each proved on both roads, and every test below
ends with a drawing that changed. The seeded draft, the bench and the pointer
helpers stay here and that module imports them, so one draft is still described
in one place.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from tests.test_store import good_lane, write_project

WORKFLOW_ID = "editing-bench"
SAVED_AT = "2026-08-20T10:00:00Z"
#: Three unbound task steps and no connection, so every one of them lands in
#: one column, in declaration order -- which is the fact a drag and Alt+Arrow
#: both edit, and the fact the row layout reads.
DRAFT = {
    "schema_version": 1,
    "title": "Editing bench",
    "nodes": [
        {"node_id": "alpha", "kind": "task", "title": "Alpha", "resources": []},
        {"node_id": "beta", "kind": "task", "title": "Beta", "resources": []},
        {"node_id": "gamma", "kind": "task", "title": "Gamma", "resources": []},
    ],
    "edges": [],
}
#: How far the vertical drag below is made to travel. It is NOT the row pitch,
#: and it has not been since the overlap defect was fixed: `studio-canvas.CELL`
#: carries a `height` that is the `min-height` FLOOR `.studio-node` declares, a
#: step grows past it, and `restack` now measures the pitch from the tallest
#: step the browser really laid out. This distance is that floor plus the gap,
#: so it is a little SHORT of one real row -- and short is enough, because the
#: drag handler reads a gesture as `Math.round(dy / (zoom * pitch))` and half a
#: row rounds to one place moved. No number of pixels is asserted anywhere: what
#: the drag test reads back is the ORDER the document holds.
DRAG_ONE_ROW = 112 + 36
#: The DRAWN connections, and only those. The inspector's Transitions rows
#: carry `data-edge` as well, so every query for a connection is scoped to the
#: edge layer or it counts one connection twice.
EDGES = "#workflowEdges [data-edge]"


@pytest.fixture
def studio_url(tmp_path) -> Iterator[str]:
    """A real server over a project that already holds one editable draft."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    TemplateStore(root).save_draft(WorkflowDraft(
        workflow_id=WORKFLOW_ID, saved_at=SAVED_AT, document=DRAFT))
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


class _Recorder:
    """Every request the page issues, so a silent write cannot hide."""

    def __init__(self, page: Page) -> None:
        self.rows: list[tuple[str, str]] = []
        page.on("request", lambda request: self.rows.append(
            (request.method, request.url)))

    def writes(self, fragment: str) -> int:
        return len([row for row in self.rows
                    if row[0] == "POST" and fragment in row[1]])


class _Bench:
    """One opened Studio, its problem log, and its request log."""

    def __init__(self, page: Page, problems: list[str],
                 recorder: _Recorder) -> None:
        self.page = page
        self.problems = problems
        self.recorder = recorder

    # -- the drawing, read back off the rendered canvas --------------------
    def node_ids(self) -> list[str]:
        """Every step on the canvas, in the order the document holds them.

        Read off the DOM rather than out of a store: `mountCanvas` appends one
        button per node in document order, so this is both "what is drawn" and
        "in what order", which is the pair a reorder edit moves.
        """
        return self.page.locator("[data-node-id]").evaluate_all(
            "nodes => nodes.map(node => node.dataset.nodeId)")

    def edge_ids(self) -> list[str]:
        """Every connection DRAWN, scoped to the edge layer on purpose.

        `data-edge` is spelled twice on this screen -- once on the canvas's hit
        path and once on the inspector's Transitions row -- so an unscoped
        query counts one connection as two.
        """
        return self.page.locator(EDGES).evaluate_all(
            "paths => paths.map(path => path.getAttribute('data-edge'))")

    def stage(self):
        return self.page.locator('[data-focus="canvas-stage"]')

    def node(self, node_id: str):
        return self.page.locator(f'[data-node-id="{node_id}"]')

    def status(self) -> str:
        return self.page.locator("#studioStatus").inner_text()

    def selection(self) -> tuple[str | None, str | None]:
        """What the canvas says is selected, read off `aria-pressed` alone."""
        node = self.page.locator('[data-node-id][aria-pressed="true"]')
        if node.count():
            return "node", node.first.get_attribute("data-node-id")
        edge = self.page.locator(f'{EDGES}[aria-pressed="true"]')
        if edge.count():
            return "edge", edge.first.get_attribute("data-edge")
        return None, None

    def wait_for_nodes(self, count: int) -> None:
        self.page.wait_for_function(
            "n => document.querySelectorAll('[data-node-id]').length === n",
            arg=count)

    def wait_for_edges(self, count: int) -> None:
        self.page.wait_for_function(
            "n => document.querySelectorAll('#workflowEdges [data-edge]')"
            ".length === n", arg=count)


def _watch(page: Page) -> list[str]:
    problems: list[str] = []
    page.on("console", lambda message: problems.append(
        getattr(message, "text", ""))
        if getattr(message, "type", "") == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    return problems


@pytest.fixture
def bench(chromium: Browser, studio_url: str) -> Iterator[_Bench]:
    """The Workflow screen, on the seeded draft, ready to be written to."""
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    page = context.new_page()
    problems = _watch(page)
    recorder = _Recorder(page)
    page.goto(studio_url, wait_until="load")
    page.wait_for_function(
        "() => document.getElementById('studioPrimary').children.length > 0")
    page.wait_for_selector('#studioConnection[data-connection="open"]')
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
    page.wait_for_function(
        "() => document.querySelectorAll('[data-node-id]').length === 3")
    # The write door is opened by the READ that landed, never by the socket, so
    # this waits for the door rather than for a moment.
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
    try:
        yield _Bench(page, problems, recorder)
    finally:
        context.close()


def _drag(page: Page, start: tuple[float, float],
          end: tuple[float, float]) -> None:
    """A real pointer gesture, in enough steps to cross the drag threshold."""
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, steps=6)
    page.mouse.move(*end, steps=6)
    page.mouse.up()


def _edge_point(page: Page, edge_id: str) -> tuple[float, float]:
    """The screen point halfway along one drawn connection.

    A straight horizontal connection has a geometric bounding box of zero
    height, so a locator click is refused as "not visible" even though the
    16px-wide ``pointer-events="stroke"`` twin is exactly what a person's
    pointer lands on. The point is therefore taken off the path's own geometry
    and clicked with the real mouse, which is the gesture under test anyway.
    """
    point = page.evaluate(
        """id => {
          const path = document.querySelector(
            `#workflowEdges [data-edge="${id}"]`);
          // Brought into view first, and the point taken AFTER: these are live
          // screen coordinates, and the canvas well plus the page around it
          // scroll under a control that was just pressed.
          path.scrollIntoView({block: "center", inline: "center"});
          const matrix = path.getScreenCTM();
          const raw = path.getPointAtLength(path.getTotalLength() / 2);
          const on = new DOMPoint(raw.x, raw.y).matrixTransform(matrix);
          return [on.x, on.y];
        }""", edge_id)
    return point[0], point[1]


def _centre(page: Page, selector: str) -> tuple[float, float]:
    locator = page.locator(selector)
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    assert box is not None, f"{selector} has no box to point at"
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _port_geometry(page: Page, node_id: str) -> dict:
    """One connect handle's box, its step's box, and what is painted over it.

    All three are read in ONE evaluation, after the handle has been brought
    into view: they have to describe the same layout, and `elementFromPoint`
    answers about the live screen rather than about a box measured earlier.
    """
    page.locator(f'[data-port="{node_id}"]').scroll_into_view_if_needed()
    return page.evaluate(
        """id => {
          const port = document.querySelector(`[data-port="${id}"]`);
          const node = document.querySelector(`[data-node-id="${id}"]`);
          const pb = port.getBoundingClientRect();
          const nb = node.getBoundingClientRect();
          const under = document.elementFromPoint(
            pb.x + pb.width / 2, pb.y + pb.height / 2);
          return {port: {x: pb.x, y: pb.y}, node: {x: nb.x, y: nb.y,
                  right: nb.right}, position: getComputedStyle(port).position,
                  under: under === null ? null : under.className.toString()};
        }""", node_id)


def _connect_alpha_to_beta(bench: _Bench) -> None:
    """The one connection several tests below need before they can start.

    The inspector's Connect is used rather than a drag from a port: its picker
    defaults to the first other step, so selecting `alpha` and pressing it is
    the whole gesture and which two ends the connection has is not in question.
    Both roads to a connection are proved on their own elsewhere in this file;
    here it is arranging, not the subject.
    """
    bench.node("alpha").click()
    bench.page.locator('[data-focus="connect-go"]').click()
    bench.wait_for_edges(1)


# -- the seeded draft is what a person is editing ---------------------------


def test_the_stored_draft_is_what_the_canvas_draws_and_it_is_editable(
        bench: _Bench) -> None:
    """The read path, end to end, before anything is edited on top of it.

    A DRAFT wins over a published revision because it is the editable document,
    and the canvas says which of the two it is drawing. Every step of the
    stored draft is on screen, in the stored order.
    """
    assert bench.node_ids() == ["alpha", "beta", "gamma"]
    assert bench.edge_ids() == []
    banner = bench.page.locator(".studio-canvas__document").inner_text()
    assert "Editing the DRAFT" in banner, banner
    assert bench.stage().get_attribute("data-editable") == "true"
    assert bench.page.locator('[data-add-kind="task"]').is_enabled()
    assert bench.problems == []


# -- adding a step: both roads ----------------------------------------------


def test_the_palette_adds_a_step_under_the_pointer_and_says_what_it_added(
        bench: _Bench) -> None:
    """A pointer road onto the canvas, and it names its own consequence.

    The new step is unbound, so the notice says exactly that rather than
    letting a reader assume something would carry it out.
    """
    bench.page.locator('[data-add-kind="task"]').click()
    bench.wait_for_nodes(4)
    assert bench.node_ids() == ["alpha", "beta", "gamma", "step-4"]
    assert "Added step-4" in bench.status()
    assert "names no role yet" in bench.status()
    assert bench.problems == []


def test_the_three_add_keys_add_the_three_step_kinds_by_keyboard_alone(
        bench: _Bench) -> None:
    """`t`, `g`, `l` -- the canvas's own legend, driven as real key events.

    Each kind is checked by the shape-and-word the step wears, not by a class:
    a glyph is carried in text so it survives a stylesheet that never landed.
    """
    for key, mark in (("t", "Task"), ("g", "Human gate"), ("l", "Loop")):
        before = len(bench.node_ids())
        bench.stage().press(key)
        bench.wait_for_nodes(before + 1)
        added = bench.node_ids()[-1]
        assert mark in bench.node(added).inner_text(), (key, mark)
    assert bench.node_ids() == ["alpha", "beta", "gamma", "step-4", "step-5",
                                "step-6"]
    assert bench.problems == []


def test_a_step_added_after_the_selected_one_arrives_connected_to_it(
        bench: _Bench) -> None:
    """The selection is what an add is anchored to, on both roads.

    Without this, "add" would mean "append somewhere", and the connection a
    person expected would have to be drawn by hand every time.
    """
    bench.node("beta").click()
    assert bench.selection() == ("node", "beta")
    bench.page.locator('[data-add-kind="task"]').click()
    bench.wait_for_nodes(4)
    assert bench.edge_ids() == ["beta step-4"]
    assert bench.problems == []


# -- selecting: both roads ---------------------------------------------------


def test_a_pointer_selects_a_step_and_the_inspector_opens_on_it(
        bench: _Bench) -> None:
    """One click, one selection, and the six sections for that step."""
    bench.node("beta").click()
    assert bench.selection() == ("node", "beta")
    inspector = bench.page.locator("#workflowInspector")
    assert inspector.locator("[data-section]").evaluate_all(
        "boxes => boxes.map(box => box.dataset.section)") == [
        "general", "assignment", "execution", "artifacts", "verification",
        "transitions"]
    assert "beta" in inspector.locator(
        '[data-context="stable-id"]').inner_text()
    assert bench.problems == []


def test_the_arrow_keys_move_the_selection_between_steps_by_keyboard_alone(
        bench: _Bench) -> None:
    """With nothing selected an arrow takes the first step; then it walks.

    Down and up are asserted as a round trip, because a build that only ever
    answered with `nodes[0]` would pass the first half on its own.
    """
    bench.stage().press("ArrowDown")
    assert bench.selection() == ("node", "alpha")
    bench.stage().press("ArrowDown")
    assert bench.selection() == ("node", "beta")
    bench.stage().press("ArrowDown")
    assert bench.selection() == ("node", "gamma")
    bench.stage().press("ArrowUp")
    assert bench.selection() == ("node", "beta")
    bench.stage().press("Escape")
    assert bench.selection() == (None, None)
    assert bench.problems == []


# -- connecting: the pointer road, and the keyboard road that replaces it ----


def test_the_inspector_connects_two_steps_under_the_pointer(
        bench: _Bench) -> None:
    """The inspector's pointer road to a connection, beside the canvas's own.

    Select a step, then press Connect. The picker defaults to the first other
    step, so two clicks is the whole gesture.
    """
    bench.node("alpha").click()
    bench.page.locator('[data-focus="connect-go"]').click()
    bench.wait_for_edges(1)
    assert bench.edge_ids() == ["alpha beta"]
    assert bench.problems == []


def test_a_drag_from_a_port_onto_another_step_connects_the_two(
        bench: _Bench) -> None:
    """The canvas's own connect gesture -- and the guard on a fixed defect.

    Written red, against a defect rendering the surface found.
    ``studio-canvas.portButton`` writes ``--x``/``--y`` custom properties on
    every connect handle and calls it "a real button beside the step", and
    ``studio.css`` declared NO rule for ``.studio-port`` -- the string did not
    occur in the file. Nothing consumed the two custom properties, so the
    handle kept ``position: static`` with ``left``/``top`` at ``auto`` and
    landed in normal flow at the stage's content origin. Measured in Chromium
    on the three-step draft below, as it then stood:

        stage box            x=83  y=683
        alpha's step         x=83  y=683   210x158
        alpha's port         x=83  y=683    24x44     (should be x=293 y=739)
        beta's port          x=107 y=683    24x44     (should be x=293 y=887)
        gamma's port         x=131 y=683    24x44     (should be x=293 y=1035)

    So every handle sat on the FIRST step rather than on its own, and because
    ``.studio-node`` is ``position:absolute`` it painted over all of them:
    ``document.elementFromPoint`` at any port's own centre answered
    ``studio-node__kind``. The handles were unreachable by pointer, and with
    them the canvas's only connect gesture -- ``bindConnectDrag`` never saw a
    ``pointerdown``.

    ``studio.css`` now positions ``.studio-port`` absolutely at
    ``var(--x)``/``var(--y)`` inside the stage, the way ``.studio-node`` always
    did, so each handle sits on its own step's right edge and the drag reaches
    ``bindConnectDrag``. The two geometry assertions come FIRST on purpose and
    are what hold that closed: a handle that lost its rule again fails them
    before the drag is attempted, instead of leaving a green test whose gesture
    silently landed somewhere else.
    """
    boxes = _port_geometry(bench.page, "alpha")
    assert boxes["position"] == "absolute", (
        "`.studio-port` is unstyled: studio.css declares no rule for it, so "
        f"the connect handle is {boxes['position']} and lands at the stage "
        "origin instead of beside its step")
    assert boxes["port"]["x"] >= boxes["node"]["right"] - 1, boxes
    start = _centre(bench.page, '[data-port="alpha"]')
    end = _centre(bench.page, '[data-node-id="beta"]')
    _drag(bench.page, start, end)
    bench.wait_for_edges(1)
    assert bench.edge_ids() == ["alpha beta"]
    assert bench.problems == []


def test_two_steps_in_one_column_never_overlap_on_screen(
        bench: _Bench) -> None:
    """No step may be drawn on top of another -- and the guard on a fixed defect.

    Written red, against a defect rendering the surface found.
    ``studio-canvas.CELL`` laid rows out at a constant pitch of
    ``height + gapY`` = ``112 + 36`` = 148px, and ``studio.css`` gives
    ``.studio-node`` a ``min-height`` of 112px. But the height is a FLOOR and a
    step grows: the plainest possible task -- kind, title, id, "no role",
    "start" -- rendered at 158px in Chromium, 10px taller than the whole pitch.
    Measured on the three unconnected steps below, as they then stood:

        alpha  y=683  height=158  bottom=841
        beta   y=831  height=158  bottom=989   <- overlaps alpha by 10px
        gamma  y=979  height=158  bottom=1137

    Every step in a column therefore sat on the one above it, and the overlap
    grew with each optional line a step carries (a stage, a gate id, a loop,
    and the whole run strip when a run is in view). The stage's own box was
    sized to ``rows * pitch`` as well, so the drawing overflowed the box that is
    supposed to contain it.

    ``studio-canvas.restack`` now MEASURES the pitch from the tallest step the
    browser really laid out, so the layout follows the height instead of
    predicting it. This test is the guard on that, and it is written as the
    Graph window's own browser gate writes it -- every pair of boxes, zero
    overlaps -- rather than against the two constants, which is what let the
    original pitch look correct in the source.
    """
    overlaps = bench.page.evaluate(
        """() => {
          const boxes = [...document.querySelectorAll('[data-node-id]')].map(
            node => ({id: node.dataset.nodeId,
                      ...node.getBoundingClientRect().toJSON()}));
          const hit = [];
          boxes.forEach((a, i) => boxes.slice(i + 1).forEach(b => {
            if (a.left < b.right && a.right > b.left
                && a.top < b.bottom && a.bottom > b.top) {
              hit.push(`${a.id}/${b.id}`);
            }
          }));
          return {hit, boxes};
        }""")
    assert overlaps["hit"] == [], (
        "steps are drawn on top of one another: " + str(overlaps))
    assert bench.problems == []


def test_the_inspector_connect_control_is_reachable_and_operable_by_tab_alone(
        bench: _Bench) -> None:
    """The keyboard road for connecting, because the canvas gesture has none.

    A port answers a click with a sentence and connects only on a pointer drag,
    so the canvas cannot be connected from a keyboard at all. The legend sends
    a keyboard reader to the inspector instead, and this walks that road with
    nothing but Tab and Enter -- reachability and activation both, since a
    control that is operable and unreachable is not a road.
    """
    page = bench.page
    bench.stage().press("ArrowDown")
    assert bench.selection() == ("node", "alpha")
    page.locator("#navWorkflow").focus()
    reached = None
    for pressed in range(1, 400):
        page.keyboard.press("Tab")
        if page.evaluate(
                "() => document.activeElement.getAttribute('data-focus')"
        ) == "connect-go":
            reached = pressed
            break
    assert reached is not None, "the inspector's Connect is not Tab-reachable"
    page.keyboard.press("Enter")
    bench.wait_for_edges(1)
    # The select defaults to the first other step, so this is the connection a
    # keyboard reader gets by pressing Enter without touching the picker.
    assert bench.edge_ids() == ["alpha beta"]
    assert bench.problems == []


# -- an edge is a first-class selection, on both roads -----------------------


def test_a_pointer_selects_a_connection_and_the_inspector_names_its_two_ends(
        bench: _Bench) -> None:
    """The wide unpainted twin is what a pointer hits, at any zoom.

    The connection is arranged through the inspector rather than by dragging a
    port. Either road would do -- both are proved above -- and the shorter one
    keeps the gesture under test here the CLICK on the drawn line.
    """
    _connect_alpha_to_beta(bench)
    bench.page.mouse.click(*_edge_point(bench.page, "alpha beta"))
    assert bench.selection() == ("edge", "alpha beta")
    panel = bench.page.locator('[data-panel="edge"]')
    assert "alpha" in panel.locator('[data-context="from"]').inner_text()
    assert "beta" in panel.locator('[data-context="to"]').inner_text()
    # And the pointer road that removes it: the panel's own Disconnect.
    bench.page.locator('[data-action="delete-edge"]').click()
    bench.wait_for_edges(0)
    assert bench.node_ids() == ["alpha", "beta", "gamma"], (
        "disconnecting removed a step")
    assert bench.problems == []


def test_enter_on_a_connection_selects_it_and_delete_removes_it(
        bench: _Bench) -> None:
    """The keyboard road to removing a connection -- and a fixed defect's guard.

    Written red, against a defect rendering the surface found. Selecting the
    connection by keyboard already worked -- the hit path is focusable and Enter
    sets ``aria-pressed`` -- and then Delete did nothing at all.

    ``studio-canvas.editKey`` spread the ends of the selected connection into
    the edit::

        {type: "delete-edge", ...edgeEnds(selection.id)}

    and ``edgeEnds`` answers ``{from, to}``, while the reducer's arm in
    ``studio-store.js`` reads ``edit.fromId`` and ``edit.toId``::

        edges: draft.edges.filter((edge) =>
          !(edge.from_node === edit.fromId && edge.to_node === edit.toId))

    Both were ``undefined``, so the predicate was never true and no connection
    was ever removed. The two inspector callers passed the same edit with the
    RIGHT names, which is why only the keyboard road was dead.

    It was worse than a no-op. That arm always answered with a NEW draft
    object, so ``edited`` took the "something changed" branch: the drawing was
    replaced by an identical copy, ``provenance`` became ``local``, and the
    Overview began telling the reader the server had not been given their
    changes -- for a keystroke that changed nothing. Its own guard is the test
    below.

    ``editKey`` now spells the edit ``{type: "delete-edge", fromId, toId}``,
    the way both inspector callers always did. What is measured here is the
    whole keyboard road end to end: focus lands on the path, Enter selects it,
    Delete removes the connection and takes no step with it.
    """
    _connect_alpha_to_beta(bench)
    bench.page.locator(f'{EDGES}[data-edge="alpha beta"]').focus()
    assert bench.page.evaluate(
        "() => document.activeElement.getAttribute('data-edge')") == "alpha beta"
    bench.page.keyboard.press("Enter")
    assert bench.selection() == ("edge", "alpha beta")
    bench.page.keyboard.press("Delete")
    bench.wait_for_edges(0)
    assert bench.edge_ids() == []
    assert bench.node_ids() == ["alpha", "beta", "gamma"], (
        "deleting a connection removed a step")
    assert bench.problems == []


def test_a_keystroke_that_changes_nothing_never_calls_the_draft_unsaved(
        bench: _Bench) -> None:
    """The half of the dead-keyboard defect that MISLED rather than merely failed.

    A no-op is recoverable; a no-op that reports itself as an edit is not. The
    ``delete-edge`` arm used to hand back a fresh draft object whatever it had
    removed, so a keystroke that removed nothing still marked the drawing
    ``local`` and the Overview began saying the server had not been given
    changes that were never made. A reader who then saves writes a document
    identical to the one already stored; a reader who does not is told they have
    unsaved work they cannot find.

    The keystroke used here removes nothing because the connection it names is
    already gone -- the same key, pressed twice, with the second press landing on
    a selection the drawing no longer holds.
    """
    page = bench.page
    bench.node("alpha").click()
    page.locator('[data-focus="connect-go"]').click()
    bench.wait_for_edges(1)
    _save_and_confirm_clean(bench)

    page.locator("#navWorkflow").click()
    page.locator(f'{EDGES}[data-edge="alpha beta"]').focus()
    page.keyboard.press("Enter")
    page.keyboard.press("Delete")
    bench.wait_for_edges(0)
    # That press DID change the drawing, so the draft is honestly unsaved. Save
    # it, or the second press below would be measured against a dirty mark it
    # did not make.
    _save_and_confirm_clean(bench)

    page.locator("#navWorkflow").click()
    page.keyboard.press("Delete")
    assert bench.edge_ids() == [], "a second Delete removed something that was gone"
    assert bench.node_ids() == ["alpha", "beta", "gamma"], (
        "a keystroke that removed nothing took a step with it")
    page.locator("#navOverview").click()
    assert "the server has not been given" not in page.locator(
        "#bodyOverview").inner_text(), (
        "a keystroke that removed nothing marked the stored draft unsaved")
    assert bench.problems == []


def _save_and_confirm_clean(bench: _Bench) -> None:
    """Store the draft, and prove the Overview agrees there is nothing unsaved.

    Both halves matter. Saving alone would leave the next assertion measuring a
    dirty mark left over from an earlier edit, and the Overview is where the
    misleading sentence actually reaches a reader.
    """
    page = bench.page
    page.locator("#navWorkflow").click()
    page.locator('#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    page.wait_for_selector('#workflowToolbar [data-save="saved"]')
    page.locator("#navOverview").click()
    assert "the server has not been given" not in page.locator(
        "#bodyOverview").inner_text()


# -- deleting and duplicating: both roads ------------------------------------


def test_the_inspector_deletes_the_selected_step_under_the_pointer(
        bench: _Bench) -> None:
    """One click, and the connections naming that step go with it.

    The second half is the one a silent build gets wrong: a removed step whose
    edges survived would leave a line drawn from nothing.
    """
    bench.node("alpha").click()
    bench.page.locator('[data-focus="connect-go"]').click()
    bench.wait_for_edges(1)
    bench.node("alpha").click()
    bench.page.locator('[data-action="delete"]').click()
    bench.wait_for_nodes(2)
    assert bench.node_ids() == ["beta", "gamma"]
    assert bench.edge_ids() == []
    assert "Removed alpha and every connection naming it" in bench.status()
    assert bench.problems == []


def test_the_delete_key_removes_the_selected_step_by_keyboard_alone(
        bench: _Bench) -> None:
    """The same edit, on the key the legend advertises."""
    bench.stage().press("ArrowDown")
    bench.stage().press("ArrowDown")
    assert bench.selection() == ("node", "beta")
    bench.stage().press("Delete")
    bench.wait_for_nodes(2)
    assert bench.node_ids() == ["alpha", "gamma"]
    assert bench.problems == []


def test_the_inspector_duplicates_a_step_and_refuses_to_copy_a_gate_identity(
        bench: _Bench) -> None:
    """A copy under the pointer, and the one field a copy may never carry.

    A gate id names ONE decision. Two steps answering to one receipt is a plan
    that cannot say which of them a Human decided, so the copy arrives with no
    gate id and the notice says so.
    """
    bench.stage().press("g")
    bench.wait_for_nodes(4)
    gate = bench.node_ids()[-1]
    bench.node(gate).click()
    bench.page.locator('[data-edit-field="gate_id"]').fill("release-gate")
    bench.page.locator('[data-edit-field="gate_id"]').press("Tab")
    bench.page.wait_for_function(
        "id => document.querySelector(`[data-node-id='${id}']`).innerText"
        ".includes('release-gate')", arg=gate)
    bench.page.locator('[data-action="duplicate"]').click()
    bench.wait_for_nodes(5)
    copy = bench.node_ids()[-1]
    assert "(copy)" in bench.node(copy).inner_text()
    assert "release-gate" not in bench.node(copy).inner_text()
    assert "names no gate id yet" in bench.status()
    assert bench.problems == []


def test_the_d_key_duplicates_the_selected_step_by_keyboard_alone(
        bench: _Bench) -> None:
    """The same edit, on the key the legend advertises."""
    bench.stage().press("ArrowDown")
    assert bench.selection() == ("node", "alpha")
    bench.stage().press("d")
    bench.wait_for_nodes(4)
    copy = bench.node_ids()[-1]
    assert "Alpha (copy)" in bench.node(copy).inner_text()
    assert bench.problems == []
