"""Where a step SITS, and that it is still there after a reload.

Split from ``test_studio_editing`` when that module reached the 800-line cap,
along a seam the product had just grown. That module is about the editing
GESTURES -- add, select, connect, delete, duplicate -- each proved twice, once
for a pointer and once for a keyboard. This one is about a fact those gestures
did not use to have: a workflow step now carries a POSITION, and a drag places
it rather than reordering it.

The three claims here fail in different ways and are therefore three tests:

- a drag moves the step on both axes and leaves the document's ORDER alone.
  Placing and ordering used to be one gesture because only one of them could be
  stored, and a build that quietly kept them welded would pass any test that
  looked at only one;
- what was placed is on the SERVER. Measured through the production reader
  before the page is asked again, then measured again after a full reload --
  a position kept in the window would be indistinguishable from a stored one
  until somebody closed the tab;
- Alt and the four arrows reach every axis a pointer can drag, and the round
  trip back to the start says the moves are equal and opposite rather than
  merely both present.

The seeded draft, the bench and its request log stay in ``test_studio_editing``
and are imported: one draft described in one place. The gate runs every module
in its own process, so nothing about that import is shared state.
"""
from __future__ import annotations

from conductor.command.template_store import TemplateStore

from browser_tests.test_studio_editing import (  # noqa: F401
    DRAG_ONE_ROW,
    WORKFLOW_ID,
    _Bench,
    _centre,
    _drag,
    bench,
    studio_url,
)


def _placed_at(page, node_id: str) -> tuple[float, float]:
    """Where a step is DRAWN, read off the two custom properties it is placed by."""
    return tuple(page.locator(f'[data-node-id="{node_id}"]').evaluate(
        "node => [parseFloat(node.style.getPropertyValue('--x')),"
        " parseFloat(node.style.getPropertyValue('--y'))]"))


def test_dragging_a_step_moves_it_on_the_canvas_and_leaves_the_order_alone(
        bench: _Bench) -> None:
    """A drag PLACES a step now, and placing is not ordering.

    It used to reorder, because a step had no coordinates and a drag that moved
    only pixels would have been a control writing nothing. Both halves are
    measured here: the step really moved on both axes, and the document's order
    -- a different fact, edited in the inspector -- did not change with it.
    """
    # Read the instructions through their native disclosure; measure the drag
    # only after folding it again, in the editor's normal compact layout.
    help_summary = bench.page.locator(".studio-canvas__help summary")
    help_summary.click()
    assert "Drag a step to place it" in bench.page.locator(
        ".studio-canvas__positions").inner_text()
    help_summary.click()
    before_order = bench.node_ids()
    before_x, before_y = _placed_at(bench.page, "alpha")
    x, y = _centre(bench.page, '[data-node-id="alpha"]')

    _drag(bench.page, (x, y), (x + 120, y + DRAG_ONE_ROW))

    bench.page.wait_for_function(
        "([id, was]) => parseFloat(document.querySelector("
        "`[data-node-id='${id}']`).style.getPropertyValue('--y')) !== was",
        arg=["alpha", before_y])
    after_x, after_y = _placed_at(bench.page, "alpha")
    assert after_x > before_x and after_y > before_y
    assert bench.node_ids() == before_order, "a placement reordered the document"
    assert bench.problems == []


def _reopened_from_the_server(bench: _Bench) -> None:
    """Reload the whole page and let URL navigation read its workflow again.

    Hold that read so an empty canvas proves no drawing came from the tab.
    Only the real server's released response may restore the saved document.
    """
    from playwright.sync_api import Error

    page = bench.page
    read_url = next(url for method, url in reversed(bench.recorder.rows)
                    if method == "GET" and url.endswith(f"/command/workflows/{WORKFLOW_ID}"))
    posts = [row for row in bench.recorder.rows if row[0] == "POST"]
    held = []
    released = False

    def hold_read(route):
        if route.request.method == "GET" and not released:
            held.append(route)
        else:
            route.continue_()

    page.route(read_url, hold_read)
    try:
        with page.expect_request(lambda request: request.method == "GET"
                                 and request.url == read_url):
            page.reload(wait_until="load")
        page.wait_for_function(
            "() => document.getElementById('studioPrimary').children.length > 0")
        assert held, "restored navigation must read the selected workflow"
        assert bench.node_ids() == [], "a drawing appeared before its server read"
        with page.expect_response(lambda response: response.request.method == "GET"
                                  and response.url == read_url) as read:
            released = True
            while held:
                held.pop(0).continue_()
        assert read.value.status == 200
        page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
        page.wait_for_function(
            "() => document.querySelectorAll('[data-node-id]').length === 3")
        assert [row for row in bench.recorder.rows if row[0] == "POST"] == posts
    finally:
        while held:
            try:
                held.pop(0).abort()
            except Error:
                pass  # A cancelled request must not mask the original assertion.
        page.unroute(read_url, hold_read)


def test_a_placed_step_is_written_to_the_draft_and_survives_a_reload(
        bench: _Bench, tmp_path) -> None:
    """The witness the whole field exists for: it comes BACK.

    A position kept only in the window would be indistinguishable from this one
    until the moment somebody closed the tab. So the draft is saved, the page is
    reloaded whole, and what is measured after is the step's drawn position --
    which can only have arrived from the server.
    """
    x, y = _centre(bench.page, '[data-node-id="beta"]')
    before_y = _placed_at(bench.page, "beta")[1]
    _drag(bench.page, (x, y), (x + 96, y + DRAG_ONE_ROW))
    bench.page.wait_for_function(
        "([id, was]) => parseFloat(document.querySelector("
        "`[data-node-id='${id}']`).style.getPropertyValue('--y')) !== was",
        arg=["beta", before_y])
    placed = _placed_at(bench.page, "beta")
    # The same wait `test_studio_lifecycle._save_draft` uses: the machine word
    # on the attribute, not the sentence beside it. A test that waited on prose
    # would red the day somebody rewrote a sentence for a reader.
    bench.page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
    bench.page.locator(
        '#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    bench.page.wait_for_selector('#workflowToolbar [data-save="saved"]')

    # On disk, through the production reader, before the page is asked again.
    stored = TemplateStore(tmp_path).load_draft(WORKFLOW_ID)
    kept = {row["node_id"]: row.get("position")
            for row in stored.document["nodes"]}
    assert kept["beta"] == {"x": int(placed[0]), "y": int(placed[1])}
    assert kept["alpha"] is None, "a step nobody moved was given a position"

    _reopened_from_the_server(bench)

    assert _placed_at(bench.page, "beta") == placed
    assert bench.problems == []


def test_alt_and_an_arrow_move_the_selected_step_on_all_four_axes(
        bench: _Bench) -> None:
    """Keyboard parity: every axis a pointer can drag, two keys can reach.

    A canvas that moved a step by pointer alone would be a pointer-only surface
    with a keyboard story told about it, so the two roads are held to the same
    vocabulary -- and the round trip back to the start is what says the moves
    are equal and opposite rather than merely both present.
    """
    bench.stage().press("ArrowDown")
    assert bench.selection() == ("node", "alpha")
    start = _placed_at(bench.page, "alpha")

    for key in ("Alt+ArrowRight", "Alt+ArrowDown"):
        bench.stage().press(key)
    bench.page.wait_for_function(
        "(was) => parseFloat(document.querySelector("
        "`[data-node-id='alpha']`).style.getPropertyValue('--y')) !== was",
        arg=start[1])
    moved = _placed_at(bench.page, "alpha")
    assert moved[0] > start[0] and moved[1] > start[1]

    for key in ("Alt+ArrowLeft", "Alt+ArrowUp"):
        bench.stage().press(key)
    bench.page.wait_for_function(
        "(was) => parseFloat(document.querySelector("
        "`[data-node-id='alpha']`).style.getPropertyValue('--y')) === was",
        arg=start[1])
    assert _placed_at(bench.page, "alpha") == start
    assert bench.problems == []


def _inspect(bench: _Bench, node_id: str) -> None:
    """Select a step so the inspector renders its sections for it."""
    bench.node(node_id).click()
    bench.page.wait_for_selector('#workflowInspector [data-section="general"]')


def _axis(bench: _Bench, name: str):
    return bench.page.locator(f'#workflowInspector [data-focus="edit-position-{name}"]')


def test_typing_a_coordinate_in_the_inspector_places_the_step(
        bench: _Bench, tmp_path) -> None:
    """The canvas must not be the only way to place a step.

    A position was reachable by drag and by Alt+arrow and by nothing anybody
    could TYPE, which is the pointer-only affordance this product counts as a
    defect. The inspector emits the SAME `move` edit the drag emits, so what is
    proved here is not a second placing mechanism but the same one reached from
    the other surface -- and it is proved the way the drag is: on the server,
    through the production reader, after a real save.
    """
    _inspect(bench, "alpha")
    assert _axis(bench, "x").input_value() == "", (
        "a step nobody placed came up with a coordinate already typed in")

    _axis(bench, "x").fill("320")
    _axis(bench, "x").press("Tab")
    _axis(bench, "y").fill("176")
    _axis(bench, "y").press("Tab")
    bench.page.wait_for_function(
        "() => document.querySelector(\"[data-node-id='alpha']\")"
        ".style.getPropertyValue('--x').trim() === '320px'")
    assert _placed_at(bench.page, "alpha") == (320.0, 176.0)

    bench.page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
    bench.page.locator(
        '#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    bench.page.wait_for_selector('#workflowToolbar [data-save="saved"]')

    stored = TemplateStore(tmp_path).load_draft(WORKFLOW_ID)
    kept = {row["node_id"]: row.get("position")
            for row in stored.document["nodes"]}
    assert kept["alpha"] == {"x": 320, "y": 176}
    assert kept["beta"] is None, "a step nobody touched was given a position"
    assert bench.problems == []


def test_a_placed_step_can_be_handed_back_to_the_automatic_layout(
        bench: _Bench) -> None:
    """Placing is not a one-way door, and the control says which state it is in.

    Without this, the first drag takes a step out of the automatic layout for
    good. The two halves are separate failures: the button must be absent for a
    step nobody has placed -- offering to un-place an unplaced step is a control
    that does nothing -- and it must actually clear the coordinate when it is
    there.
    """
    _inspect(bench, "alpha")
    unplace = bench.page.locator('#workflowInspector [data-action="unplace"]')
    assert unplace.count() == 0, (
        "an unplaced step was offered a control to unplace it")

    _axis(bench, "x").fill("288")
    _axis(bench, "x").press("Tab")
    bench.page.wait_for_function(
        "() => document.querySelector(\"[data-node-id='alpha']\")"
        ".style.getPropertyValue('--x').trim() === '288px'")
    was = _placed_at(bench.page, "alpha")

    bench.page.locator('#workflowInspector [data-action="unplace"]').click()
    bench.page.wait_for_function(
        "(was) => parseFloat(document.querySelector("
        "\"[data-node-id='alpha']\").style.getPropertyValue('--x')) !== was",
        arg=was[0])
    assert _placed_at(bench.page, "alpha") != was
    _inspect(bench, "alpha")
    assert _axis(bench, "x").input_value() == ""
    assert bench.page.locator(
        '#workflowInspector [data-action="unplace"]').count() == 0
    assert bench.problems == []


def _in_page(bench: _Bench, module: str, script: str):
    """Run one expression against a SHIPPED module, inside the real browser.

    The two functions below are pure, and this repository has no JavaScript
    unit harness: source guards run in the fast suite and behaviour runs in
    Chromium. So behaviour is what this asks for -- the browser imports the
    module from the production `/panel/` route, exactly as the Studio does, and
    the function is called with values no gesture on the screen can produce.

    That is the point. Both guards below refuse a shape the durable contract
    also refuses, so no ROUTE can deliver one: a draft carrying half a position
    is FOREIGN and `TemplateNode.from_dict` will not parse it. Defence at a
    boundary is worth keeping and worth proving, and this is the only way left
    to prove it.
    """
    return bench.page.evaluate(
        f"async () => {{ const m = await import('/panel/{module}');"
        f" return ({script}); }}")


def test_the_layout_refuses_a_position_it_could_not_have_drawn(
        bench: _Bench) -> None:
    """A half-placed step would be drawn at a coordinate this window invented.

    Nobody could tell that from one they chose, so `placement` answers null and
    the step goes back to the grid, where at least the drawing explains itself.
    Both axes, both directions, and the over-correction control beside them.
    """
    refused = _in_page(bench, "studio-layout.js", """[
      m.placement({position: {x: 10}}),
      m.placement({position: {y: 10}}),
      m.placement({position: {x: 10, y: 1.5}}),
      m.placement({position: {x: "10", y: "20"}}),
      m.placement({position: [10, 20]}),
      m.placement({position: null}),
      m.placement({})
    ]""")
    assert refused == [None] * 7, refused
    assert _in_page(bench, "studio-layout.js",
                    "m.placement({position: {x: -48, y: 96}})") == {
        "x": -48, "y": 96}


def test_the_reducer_refuses_a_coordinate_the_document_could_not_store(
        bench: _Bench) -> None:
    """`POSITION_LIMIT` is refused HERE as well as in Python, and that is why.

    A drag or a spinner that produced an out-of-range coordinate would write a
    draft the save route then rejects, and the person would meet it as a save
    that failed for a reason nothing on the screen explains. Refusing at the
    edit says so while the gesture is still in their hand.
    """
    draft = {"nodes": [{"node_id": "alpha", "kind": "task", "title": "A"}],
             "edges": []}
    # Each refusal is a catalogue key; the page's own renderer says it as a person reads it.
    answered = _in_page(bench, "studio-edits.js", """await import("/panel/studio-i18n.js").then((i18n) => [
      m.applyEdit(%s, {type: "move", nodeId: "alpha", x: 100001, y: 0}).notice,
      m.applyEdit(%s, {type: "move", nodeId: "alpha", x: 0, y: -100001}).notice,
      m.applyEdit(%s, {type: "move", nodeId: "alpha", x: "far", y: 0}).notice,
      m.applyEdit(%s, {type: "move", nodeId: "alpha", x: 100000, y: 0}).notice
    ].map((notice) => i18n.noticeText({locale: "en"}, notice)))""" % ((__import__("json").dumps(draft),) * 4))
    assert all("within the canvas" in said for said in answered[:3]), answered
    # The boundary itself is a legal placement: an off-by-one here would refuse
    # a coordinate the document is perfectly willing to hold.
    assert answered[3] == "", answered
    kept = _in_page(bench, "studio-edits.js",
                    'm.applyEdit(%s, {type: "move", nodeId: "alpha", '
                    'x: 100000, y: 0}).draft.nodes[0].position'
                    % __import__("json").dumps(draft))
    assert kept == {"x": 100000, "y": 0}, kept
