"""What the Studio will NOT write, and what it says in the place it refused.

Split from ``test_studio_editing`` at the 800-line cap, along a real seam
rather than at a convenient line. That module is about the editing GESTURES --
add, select, connect, move, delete, duplicate -- each proved twice, once for a
pointer and once for a keyboard, and every test in it ends with a drawing that
changed. This one is about the opposite half: an edit that is held back, a
document that may not be edited at all, and the two refusals a save and a
publish can meet.

The circuit, in one sentence: **nothing reaches the server until a Human asks
for it, and whatever cannot be written is refused beside the control that asked
-- naming which document it is refusing.** The inspector's accepted edit proves
the first half by writing nothing; the name it rejects, the published revision
it will not touch, and the two diagnostic lists prove the second.

The refusal half is here for the same reason the editing half is over there: a
draft that cannot publish must SAY so, in the place the control was pressed, and
it must say it about the right document. Two documents are judged and they are
never merged: what this window can already see the save route would refuse (the
unsaved drawing) and what the server says about the draft it stored.

The seeded draft, the bench and its request log stay in ``test_studio_editing``
and are imported here: one draft described in one place. The gate runs every
module in its own process, so nothing about that import is shared state -- it is
one description read twice.
"""
from __future__ import annotations

from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from browser_tests.test_studio_lifecycle import (
    NEW_DRAFT,
    NEW_DRAFT_CONTROL,
    _publish,
)
from browser_tests.test_studio_editing import (  # noqa: F401
    DRAFT,
    SAVED_AT,
    WORKFLOW_ID,
    _Bench,
    bench,
    studio_url,
)


# -- the inspector writes the document the canvas draws ----------------------


def test_an_inspector_field_reaches_the_canvas_and_marks_the_draft_unsaved(
        bench: _Bench) -> None:
    """One field, three consequences, and the third is the one that matters.

    Changing a display name must move the drawing AND must say that the server
    has not been given the change: a window that showed the new name while
    still calling the draft stored would be lying about what is durable.
    """
    overview = bench.page.locator("#bodyOverview")
    bench.page.locator("#navOverview").click()
    assert "the server has not been given" not in overview.inner_text()

    bench.page.locator("#navWorkflow").click()
    bench.node("beta").click()
    bench.page.locator('[data-edit-field="title"]').fill("Beta, renamed")
    bench.page.locator('[data-edit-field="title"]').press("Tab")
    bench.page.wait_for_function(
        "() => document.querySelector('[data-node-id=\\'beta\\'] "
        ".studio-node__title').textContent === 'Beta, renamed'")

    bench.page.locator("#navOverview").click()
    assert "the server has not been given" in overview.inner_text()
    assert bench.recorder.writes("/draft") == 0, (
        "an inspector edit wrote to the server without a Human asking")
    assert bench.problems == []


def test_the_inspector_refuses_a_name_it_cannot_store_and_writes_nothing(
        bench: _Bench) -> None:
    """A control that validates, rather than one that posts and is rejected.

    The error sits beside the field from the first render, hidden until it has
    something to say, so a keyboard reader hears it through `aria-describedby`.
    """
    bench.node("beta").click()
    field = bench.page.locator('[data-edit-field="title"]')
    field.fill("   ")
    field.press("Tab")
    error = bench.page.locator("#studio-invalid-title")
    assert error.is_visible()
    assert "non-empty string" in error.inner_text()
    assert field.get_attribute("aria-invalid") == "true"
    assert field.get_attribute("aria-describedby") == "studio-invalid-title"
    assert "Beta" in bench.node("beta").inner_text(), (
        "a refused edit reached the drawing anyway")
    assert bench.problems == []


def test_a_published_revision_disables_every_editing_control_and_says_why(
        bench: _Bench) -> None:
    """The over-correction control: an editable canvas must not be universal.

    This is the same window, on a document that is immutable by design. Every
    control the editing tests press is disabled here, and the reason is ON
    SCREEN rather than implied by a grey box.

    Immutable is not the same as finished, and the second half of this test is
    that distinction. Every editing control stays shut -- nothing below this
    line was relaxed -- and the screen OFFERS the one road that does not edit
    the revision: copying it into a draft. Both surfaces that state the
    immutability name that road in the same words, so a reader is never told
    what they cannot do without being told what they can.
    """
    page = bench.page
    # A published revision arrives by publishing the seeded draft, which is the
    # only road this product has to one.
    _publish(page)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    assert page.locator(".studio-canvas__document").inner_text().startswith(
        "Showing published revision 1")
    assert page.locator('[data-add-kind="task"]').is_disabled()
    assert page.locator('[data-port="alpha"]').is_disabled()
    assert page.locator("#workflowInspector").inner_text().count(
        "immutable") >= 1
    page.locator('[data-node-id="alpha"]').click()
    assert page.locator('[data-edit-field="title"]').is_disabled()
    assert page.locator('[data-action="delete"]').is_disabled()
    # And the keyboard road is shut with it, not merely hidden.
    before = bench.node_ids()
    bench.stage().press("t")
    assert bench.node_ids() == before

    fresh = page.locator(NEW_DRAFT_CONTROL)
    assert not fresh.is_disabled(), (
        "every control was shut and no road was offered in their place")
    assert fresh.inner_text() == NEW_DRAFT
    for said in (page.locator(".studio-canvas__document").inner_text(),
                 page.locator("#workflowInspector").inner_text()):
        assert NEW_DRAFT in said, said
        assert "stays exactly as it is" in said, said
    assert bench.problems == []


# -- what stops publishing: two documents, judged apart ----------------------


def test_a_drawing_this_window_can_already_see_is_refused_before_the_wire(
        bench: _Bench) -> None:
    """Half a binding is a step nobody can carry out, and the save says so.

    The refusal lands beside the control that asked for it, names the step, and
    reaches no server at all -- which is the difference between a control that
    validates and one that posts a body for the server to reject.
    """
    page = bench.page
    bench.node("alpha").click()
    role = page.locator('[data-edit-field="role_id"]')
    role.fill("reviewer")
    role.press("Tab")
    diagnostics = page.locator("#workflowDiagnostics")
    page.wait_for_function(
        "() => document.getElementById('workflowDiagnostics').innerText"
        ".includes('half a binding')")
    local = diagnostics.locator(".studio-diag__code").all_inner_texts()
    assert "local" in local, local
    assert "Step alpha names half a binding" in diagnostics.inner_text()

    page.locator('#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    page.wait_for_selector('#workflowToolbar [data-save="refused"]')
    said = page.locator('#workflowToolbar [data-save="refused"]').inner_text()
    assert "refused before it was offered to the server" in said, said
    assert bench.recorder.writes("/draft") == 0, (
        "a drawing this window had already refused was sent anyway")
    assert bench.problems == []


def test_a_saved_draft_that_cannot_publish_names_what_stops_it_and_refuses(
        bench: _Bench) -> None:
    """The server's own answer about the document the server stored.

    A gate with no gate id is a perfectly legal DRAFT -- a draft is allowed to
    be incomplete -- and is not a revision. So the save succeeds, the server's
    diagnostics name the exact step, and the publish control is disabled with
    the reason written on it. Never a silent no-op.
    """
    page = bench.page
    bench.stage().press("g")
    bench.wait_for_nodes(4)
    gate = bench.node_ids()[-1]
    page.locator('#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    page.wait_for_selector('#workflowToolbar [data-save="saved"]')

    diagnostics = page.locator("#workflowDiagnostics")
    page.wait_for_function(
        "id => document.getElementById('workflowDiagnostics').innerText"
        ".includes(`gate node '${id}' must name a gate_id`)", arg=gate)
    assert "server" in diagnostics.locator(
        ".studio-diag__code").all_inner_texts()
    assert "The server's own answer about the draft it stored" in \
        diagnostics.inner_text()

    publish = page.locator('#workflowToolbar [data-focus="action:onPublish"]')
    assert publish.is_disabled()
    assert "Publishing needs a SAVED draft the server says would construct a " \
        "revision" in publish.get_attribute("title")
    # The canvas banner counts the same rows the panel lists. The COUNT is what
    # is pinned, never the whole sentence: this once rendered the singular as
    # "1 problem block publishing this draft.", with the plural `s` on the noun
    # instead of the verb, and a test pinned to that wording would have made the
    # fix red. `studio-canvas.banner` agrees the verb with the count now.
    counted = page.locator(".studio-canvas__diagnostics").inner_text()
    assert counted.startswith("1 problem"), counted
    assert "publishing this draft" in counted, counted
    assert bench.problems == []


def test_the_two_diagnostic_lists_never_answer_for_one_another(
        bench: _Bench) -> None:
    """Two documents, two lists, and each says which document it is about.

    A single merged list would let "the drawing on screen is broken" be read as
    "the stored draft is broken", which is a claim about a durable record this
    window has not made.
    """
    page = bench.page
    bench.node("alpha").click()
    role = page.locator('[data-edit-field="role_id"]')
    role.fill("reviewer")
    role.press("Tab")
    page.wait_for_function(
        "() => document.getElementById('workflowDiagnostics').innerText"
        ".includes('half a binding')")
    sections = page.locator("#workflowDiagnostics .studio-section")
    assert sections.count() == 2
    drawing = sections.nth(0).inner_text()
    stored = sections.nth(1).inner_text()
    assert "nothing has been sent" in drawing
    assert "half a binding" in drawing
    assert SAVED_AT in stored, stored
    assert "half a binding" not in stored, (
        "the unsaved drawing's problem was reported as the stored draft's")
    assert bench.problems == []


# -- a review that went stale while it was open ------------------------------


def _save_over_the_open_review(tmp_path) -> None:
    """Another client replaces the draft, through the production writer.

    Saving a draft publishes no stream frame -- there is nothing for the
    reviewing window to hear -- which is exactly why the window cannot know its
    review has gone stale until it tries to publish.
    """
    TemplateStore(tmp_path).save_draft(WorkflowDraft(
        workflow_id=WORKFLOW_ID, saved_at="2026-08-20T11:00:00Z",
        document={**DRAFT, "title": "UNREVIEWED SERVER CHANGE"}))


def _only_the_refusal_was_logged(bench: _Bench) -> None:
    """Exactly one console line, and it is Chromium narrating the 409.

    Every other test in this module asserts an EMPTY problem log, because every
    other refusal in it happens in the window before anything reaches the wire.
    These two are the first to make the browser receive a 4xx, and a browser
    logs "Failed to load resource" for one whether or not the page handles it.
    Allowing the log wholesale would blind the assertion; naming the one line
    keeps every other console error and every page error failing as before.
    """
    assert len(bench.problems) == 1, bench.problems
    said = bench.problems[0]
    assert "Failed to load resource" in said, said
    assert "409" in said, said


def _workflow_reads(bench: _Bench) -> int:
    """How many times this window has read the workflow whole."""
    return len([row for row in bench.recorder.rows
                if row[0] == "GET"
                and row[1].endswith(f"/command/workflows/{WORKFLOW_ID}")])


def test_a_review_that_went_stale_is_refused_and_reopened_on_the_new_draft(
        bench: _Bench, tmp_path) -> None:
    """The refusal a person can act on, driven in a real browser.

    The window opens a review of the draft it read, another client replaces
    that draft, and Confirm is pressed. Three things have to be true and only
    the first one was: nothing is published; the person is told what actually
    happened rather than that their request was malformed; and the stale review
    is taken off the screen and the newer draft loaded in its place.

    Without the third, the panel stayed open over a document the server no
    longer held, above a Confirm guaranteed to fail every time it was pressed.
    """
    page = bench.page
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
    page.locator('#workflowToolbar [data-focus="action:onPublish"]').click()
    page.wait_for_selector('[data-review="publish"]')

    reads_before = _workflow_reads(bench)
    _save_over_the_open_review(tmp_path)
    page.locator('[data-focus="action:onPublishConfirm"]').click()

    # The review is gone rather than left standing over a document that moved.
    page.wait_for_selector('[data-review="publish"]', state="detached")
    said = page.locator("#workflowToolbar [data-save]").inner_text()
    assert "draft changed while you were reviewing it" in said, said
    assert "The request shape is invalid" not in said, said
    # And the window went back to the server for the draft that now stands,
    # rather than only printing a sentence over the one it was holding.
    page.wait_for_function(
        "() => document.querySelector('#workflowToolbar [data-save]')"
        ".innerText.includes('draft changed')")
    assert _workflow_reads(bench) > reads_before, (
        "the window reported the conflict without re-reading the workflow")
    assert TemplateStore(tmp_path).revisions(WORKFLOW_ID) == (), (
        "a stale review published a revision")
    _only_the_refusal_was_logged(bench)


def test_the_reopened_review_publishes_the_draft_that_now_stands(
        bench: _Bench, tmp_path) -> None:
    """The over-correction control: the road must still lead somewhere.

    A refusal that closed the review and left the window unable to publish
    would trade one dead end for another. After looking again, the person
    publishes -- and what lands is the document they were shown the second
    time, not the one they first reviewed.
    """
    page = bench.page
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
    page.locator('#workflowToolbar [data-focus="action:onPublish"]').click()
    page.wait_for_selector('[data-review="publish"]')
    _save_over_the_open_review(tmp_path)
    page.locator('[data-focus="action:onPublishConfirm"]').click()
    page.wait_for_selector('[data-review="publish"]', state="detached")
    page.wait_for_function(
        "() => document.querySelector('#workflowToolbar [data-save]')"
        ".innerText.includes('draft changed')")

    _publish(page)

    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    templates = TemplateStore(tmp_path)
    assert templates.revisions(WORKFLOW_ID) == (1,)
    assert templates.load(WORKFLOW_ID, 1).title == "UNREVIEWED SERVER CHANGE"
    _only_the_refusal_was_logged(bench)
