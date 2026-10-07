"""The second revision: copying a published one into a draft, and publishing it.

A published workflow with no draft used to be the end of the road. Every
control was disabled, the canvas said the revision was immutable and stopped
there, and the only way to a revision 2 was to start a differently named
workflow. The revision is still immutable -- nothing here edits one -- and the
road on is a COPY: the standing revision is rebuilt as a draft this window
holds, saved through the draft route that already exists, and published as the
NEXT revision.

Three circuits, and each is a different question:

1. the road itself, end to end, checked against the durable tree at every step
   -- the copy is local until it is saved, the edit reaches the draft, the
   review names revision 2 and what changed, and revision 1 comes back out of
   the store byte for byte the same afterwards;
2. what a reload does to a copy nobody saved. It is lost, and that is the
   honest answer rather than a defect: nothing was sent, so there is nothing
   for a read to bring back, and the window must come back to the published
   revision rather than to a blank;
3. two windows racing for revision 2. Whoever writes it first wins, and the
   loser must be REFUSED rather than silently overwritten -- twice, because
   there are two ways to lose and they answer with two different codes.

Its own module rather than more of ``test_studio_lifecycle``: that one is at
the 800-line cap and its subject is a draft's durability and the socket it is
read over. This one is about the revision AFTER the first, which is a circuit
that module never had. The project fixture, the page helpers and the publish
road stay there and are imported here, so one seeded project is still described
in one place.
"""
from __future__ import annotations

from playwright.sync_api import Browser, Page

from conductor.command.graph_template import GraphTemplate
from conductor.command.template_store import TemplateStore

from browser_tests.test_studio_lifecycle import (  # noqa: F401
    NEW_DRAFT,
    NEW_DRAFT_CONTROL,
    STARTER_STEPS,
    _Project,
    _Window,
    _choose,
    _open,
    _publish,
    _save_draft,
    _settle,
    _start_from_starter,
    project,
)

WORKFLOW_ID = "second-bench"
#: What each window renames the first step to. Two different words, so a
#: document read back out of the store says WHICH window wrote it.
MINE = "Renamed by this window"
THEIRS = "Renamed by the other window"
SAVE_LINE = "#workflowToolbar [data-save]"
PUBLISH = '#workflowToolbar [data-focus="action:onPublish"]'


# -- the road ----------------------------------------------------------------


def _publish_the_first_revision(page: Page, project: _Project) -> None:
    """Start from the bundled starter and publish it, which is revision 1."""
    _start_from_starter(page, WORKFLOW_ID)
    _save_draft(page)
    _publish(page)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    assert project.templates().revisions(WORKFLOW_ID) == (1,)


def _copy_the_published_revision(page: Page) -> None:
    """Press the one road on, and wait for the draft it seeds to be drawn."""
    page.wait_for_selector(f"{NEW_DRAFT_CONTROL}:not([disabled])")
    page.locator(NEW_DRAFT_CONTROL).click()
    page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')


def _rename_the_first_step(page: Page, name: str) -> str:
    """One real edit, made through the inspector, waited on in the drawing."""
    node = page.locator("[data-node-id]").first
    node_id = node.get_attribute("data-node-id")
    node.click()
    field = page.locator('[data-edit-field="title"]')
    field.fill(name)
    field.press("Tab")
    page.wait_for_function(
        "given => document.querySelector('[data-node-id=\"' + given.id"
        + "+ '\"] .studio-node__title').textContent === given.name",
        arg={"id": node_id, "name": name})
    return node_id


def _step_title(document: dict, node_id: str) -> str:
    return next(row["title"] for row in document["nodes"]
                if row["node_id"] == node_id)


def expectations(window: _Window) -> list[dict]:
    """What each draft save this window sent claimed it was replacing.

    The expectation is the half of the save contract no rendered assertion can
    see: a window that stopped sending it would draw exactly the same screen
    and be back to writing blind. So it is read off the wire.
    """
    return [{key: value for key, value in body.items() if key != "document"}
            for body in window.posted("/draft")]


def _the_window_itself_raised_nothing(window: _Window) -> None:
    """Page errors are the window's; a resource line is the browser's.

    Most tests here want an empty problem log outright. The racing ones make
    the browser receive a 4xx, and running four windows against one loopback
    server on Windows has also produced ``ERR_NO_BUFFER_SPACE`` from the socket
    layer -- both are logged by Chromium as "Failed to load resource" whether
    or not the page handles them, and neither is a fault in the code under
    test. Naming that one prefix keeps every other console error and every page
    error failing as before.
    """
    assert window.page_errors == []
    assert [line for line in window.console_errors
            if "Failed to load resource" not in line] == [], window.problems


def _the_copy_is_held_here_and_nowhere_else(
        page: Page, window: _Window, project: _Project,
        drawn: list[str]) -> None:
    """What a copy IS, on four surfaces that can come apart.

    It carries the published document; nothing was sent, so the server still
    holds no draft; the workflow this window is on did not move underneath it,
    which a seed that re-chose the workflow would have done -- and the number
    about to be created is read off exactly the read a re-choose would clear.
    The road is also SPENT: pressing it again would replace the drawing, so it
    is shut, and it says that rather than going grey.
    """
    assert window.node_ids() == drawn
    assert project.templates().load_draft(WORKFLOW_ID) is None, (
        "copying a revision wrote a draft nobody asked to save")
    assert window.writes("/draft") == 1, (
        "the copy reached the wire; it is a local drawing until saved")
    assert page.locator(
        "#workflowToolbar select[name='workflow']").input_value() == WORKFLOW_ID
    assert page.locator(PUBLISH).inner_text() == "Publish revision 2"
    assert page.locator(NEW_DRAFT_CONTROL).is_disabled(), (
        "a second copy could be taken over the drawing already on screen")
    assert page.locator(NEW_DRAFT_CONTROL).get_attribute("title") == (
        "There is already a drawing on screen; edit it and save the draft.")


def _review_and_publish_the_copy(page: Page, node_id: str) -> None:
    """The review names the number and the change, and only Confirm writes."""
    page.wait_for_selector(f"{PUBLISH}:not([disabled])")
    page.locator(PUBLISH).click()
    page.wait_for_selector('[data-review="publish"]')
    review = page.locator('[data-review="publish"]').inner_text().lower()
    assert "publish revision 2?" in review, review
    assert f"steps changed (1): {node_id}" in review, review
    page.locator('[data-focus="action:onPublishConfirm"]').click()
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')


def test_the_published_revision_is_copied_into_a_draft_that_becomes_the_next(
        chromium: Browser, project: _Project) -> None:
    """The whole road, with the durable tree checked at every step.

    The claim being made is not "a button appeared". It is that the document
    the canvas was showing read-only is the document that comes back editable,
    that it is this window's until a Human saves it, that saving it puts it on
    the server through the draft route this product already had, and that
    publishing it writes a SECOND revision while the first is left exactly as
    it was. Each of those is checked against the store rather than the screen.
    """
    page, window = _open(chromium, project)
    try:
        _publish_the_first_revision(page, project)
        templates = project.templates()
        first = templates.load(WORKFLOW_ID, 1).as_dict()
        drawn = window.node_ids()

        _copy_the_published_revision(page)
        _the_copy_is_held_here_and_nowhere_else(page, window, project, drawn)

        node_id = _rename_the_first_step(page, MINE)
        _save_draft(page)
        stored = templates.load_draft(WORKFLOW_ID)
        assert stored is not None, "the saved copy never reached the server"
        assert _step_title(stored.settled(), node_id) == MINE
        # Both saves on this road are first saves -- the starter's, and this
        # one over the draft the publish consumed -- so each says out loud that
        # it looked and found nothing. A save that named no expectation at all
        # would be refused by the route, and one that named the wrong one would
        # be a window writing blind.
        assert expectations(window) == [
            {"expected_absent": True}, {"expected_absent": True}]

        _review_and_publish_the_copy(page, node_id)

        assert templates.revisions(WORKFLOW_ID) == (1, 2)
        assert templates.load(WORKFLOW_ID, 1).as_dict() == first, (
            "publishing the next revision changed the one it was copied from")
        assert _step_title(templates.load(WORKFLOW_ID, 2).as_dict(),
                           node_id) == MINE
        assert templates.load_draft(WORKFLOW_ID) is None, (
            "the draft outlived the revision it became")
        assert page.locator(
            ".studio-canvas__document").inner_text().startswith(
                "Showing published revision 2")
        assert window.problems == []
    finally:
        page.context.close()


def test_a_copy_nobody_saved_is_gone_after_a_reload_and_the_revision_stands(
        chromium: Browser, project: _Project) -> None:
    """The honest behaviour, asserted rather than assumed.

    A copy is a local drawing: it is held in the tab and no byte of it has been
    sent. So a reload cannot bring it back -- there is nothing on the server to
    bring -- and what the window must come back to is the published revision it
    was copied from, never a blank canvas and never a phantom draft.
    """
    page, window = _open(chromium, project)
    try:
        _publish_the_first_revision(page, project)
        drawn = window.node_ids()
        _copy_the_published_revision(page)
        _rename_the_first_step(page, MINE)
        writes = window.writes("/draft")

        page.reload(wait_until="load")
        _settle(page)
        assert window.storage() == [0, 0], (
            "the window put the unsaved copy in browser storage")
        _choose(page, WORKFLOW_ID)
        page.wait_for_selector(
            '.studio-canvas__banner[data-document="published"]')

        assert window.node_ids() == drawn
        assert MINE not in page.locator("#workflowNodes").inner_text(), (
            "an unsaved copy came back from somewhere after a reload")
        assert window.writes("/draft") == writes, (
            "a reload sent the copy nobody had asked to save")
        assert project.templates().load_draft(WORKFLOW_ID) is None
        assert project.templates().revisions(WORKFLOW_ID) == (1,)
        assert window.problems == []
    finally:
        page.context.close()


# -- two windows racing for revision 2 ---------------------------------------


def _hold_a_review_of_the_next_revision(page: Page) -> str:
    """Copy, edit, save, and open the review -- the state a race interrupts."""
    _copy_the_published_revision(page)
    node_id = _rename_the_first_step(page, MINE)
    _save_draft(page)
    page.wait_for_selector(f"{PUBLISH}:not([disabled])")
    page.locator(PUBLISH).click()
    page.wait_for_selector('[data-review="publish"]')
    return node_id


def _read_until_the_stored_draft_is_shown(page: Page, title: str) -> None:
    """Read the workflow again, and wait for what the OTHER window stored.

    ``Validate`` re-reads the chosen workflow and nothing else. It is the road a
    refused save leaves open, and it is a road the person takes: nothing here
    reads on their behalf, because a read merges the stored draft into what is
    on screen and doing that automatically is the overwrite this whole seam
    refuses.
    """
    page.locator('#workflowToolbar [data-focus="action:onValidate"]').click()
    page.wait_for_function(
        "given => document.getElementById('workflowNodes').innerText"
        ".includes(given)", arg=title)


def _second_step_id(page: Page) -> str:
    """A step this window has not renamed, so two edits cannot collide."""
    return page.locator("[data-node-id]").nth(1).get_attribute("data-node-id")


def _rename_a_step(page: Page, node_id: str, name: str) -> None:
    """Rename one NAMED step, waiting on the drawing rather than on a clock."""
    page.locator(f'[data-node-id="{node_id}"]').click()
    field = page.locator('[data-edit-field="title"]')
    field.fill(name)
    field.press("Tab")
    page.wait_for_function(
        "given => document.querySelector('[data-node-id=\"' + given.id"
        + "+ '\"] .studio-node__title').textContent === given.name",
        arg={"id": node_id, "name": name})


def _neither_drawing_was_destroyed(
        second: Page, templates, stored: bytes, node_id: str) -> None:
    """The refusal said why, kept the winner's bytes, and kept the loser's work.

    Three different failures, so three assertions: a refusal with no sentence is
    a dead end, a refusal that wrote anyway is the defect, and a refusal that
    loaded the other window's draft over this one would trade the work loss for
    a different one.
    """
    said = second.locator(SAVE_LINE).inner_text()
    assert "not the one this window last read" in said, said
    assert "your drawing is untouched" in said, said
    assert templates.draft_path(WORKFLOW_ID).read_bytes() == stored, (
        "the second window's save replaced the first window's stored work")
    assert _step_title(
        templates.load_draft(WORKFLOW_ID).settled(), node_id) == MINE
    drawn = second.locator("#workflowNodes").inner_text()
    assert THEIRS in drawn, "the refusal discarded this window's own drawing"
    assert MINE not in drawn, (
        "the refusal quietly loaded the other window's draft over this one")


def test_a_second_windows_save_is_refused_and_neither_drawing_is_destroyed(
        chromium: Browser, project: _Project) -> None:
    """The work-loss defect this contract exists to close, driven for real.

    Two windows open the same published workflow, both take the road on, and
    both save. A workflow holds ONE draft, so before this contract the second
    write simply replaced the first's stored document: no revision held it, no
    record said it had existed, and neither person was told anything at all.

    Four things are asserted because they are four different failures. The
    second save is REFUSED rather than written. It is refused as a conflict and
    says so in words a person can act on. The first window's stored bytes are
    exactly what it wrote. And the second window still has its own drawing on
    screen -- a refusal that discarded the loser's work would trade one kind of
    work loss for another.
    """
    first, watching = _open(chromium, project)
    second: Page | None = None
    try:
        _publish_the_first_revision(first, project)
        templates = project.templates()
        second, other = _open(chromium, project)
        _choose(second, WORKFLOW_ID)
        second.wait_for_selector(
            '.studio-canvas__banner[data-document="published"]')

        _copy_the_published_revision(first)
        node_id = _rename_the_first_step(first, MINE)
        _save_draft(first)
        stored = templates.draft_path(WORKFLOW_ID).read_bytes()

        _copy_the_published_revision(second)
        _rename_the_first_step(second, THEIRS)
        second.locator(
            '#workflowToolbar [data-focus="action:onSaveDraft"]').click()
        second.wait_for_selector(f'{SAVE_LINE}[data-save="refused"]')

        _neither_drawing_was_destroyed(second, templates, stored, node_id)
        assert watching.problems == []
        _the_window_itself_raised_nothing(other)
    finally:
        if second is not None:
            second.context.close()
        first.context.close()


def test_the_refused_window_reads_again_and_its_next_save_is_accepted(
        chromium: Browser, project: _Project) -> None:
    """The over-correction control: refusing must not close the road.

    A contract that only ever said no would make two people editing one
    workflow impossible rather than safe. After reading again, the second
    window is looking at what actually stands, edits THAT, and its save lands --
    carrying both people's work, because it was built on the document the first
    person stored rather than over the top of it.
    """
    first, watching = _open(chromium, project)
    second: Page | None = None
    try:
        _publish_the_first_revision(first, project)
        templates = project.templates()
        second, other = _open(chromium, project)
        _choose(second, WORKFLOW_ID)
        second.wait_for_selector(
            '.studio-canvas__banner[data-document="published"]')

        _copy_the_published_revision(first)
        mine = _rename_the_first_step(first, MINE)
        _save_draft(first)
        _copy_the_published_revision(second)
        _rename_the_first_step(second, THEIRS)
        second.locator(
            '#workflowToolbar [data-focus="action:onSaveDraft"]').click()
        second.wait_for_selector(f'{SAVE_LINE}[data-save="refused"]')

        _read_until_the_stored_draft_is_shown(second, MINE)
        theirs = _second_step_id(second)
        assert theirs != mine
        _rename_a_step(second, theirs, THEIRS)
        _save_draft(second)

        settled = templates.load_draft(WORKFLOW_ID).settled()
        assert _step_title(settled, mine) == MINE, (
            "the accepted save overwrote the other window's work after all")
        assert _step_title(settled, theirs) == THEIRS
        assert watching.problems == []
        _the_window_itself_raised_nothing(other)
    finally:
        if second is not None:
            second.context.close()
        first.context.close()


def _the_other_window_takes_revision_two(
        page: Page, project: _Project, node_id: str) -> dict:
    """A second window reads the standing draft, edits it, and publishes first.

    It has to READ first now: a save that named no expectation, or a stale one,
    is refused. So this is the legitimate collaborative road driven to its end,
    and its end is that the one draft this workflow has is CONSUMED by the
    publish -- which is what leaves the first window reviewing a document the
    server no longer holds.
    """
    _read_until_the_stored_draft_is_shown(page, MINE)
    _rename_a_step(page, _second_step_id(page), THEIRS)
    _save_draft(page)
    _publish(page)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    templates = project.templates()
    assert templates.revisions(WORKFLOW_ID) == (1, 2)
    written = templates.load(WORKFLOW_ID, 2).as_dict()
    assert _step_title(written, node_id) == MINE
    assert templates.load_draft(WORKFLOW_ID) is None
    return written


def _the_stale_window_recovered_to_the_standing_revision(page: Page) -> None:
    """The refusal is not the end: the window ends up somewhere it can act.

    The stale review is taken off the screen, the workflow is read again, and
    what comes back is the revision the OTHER window published -- with the one
    road on from it enabled. A window that only printed the refusal would leave
    a person looking at a drawing the server does not hold, above a Confirm
    guaranteed to fail every time it is pressed.
    """
    page.wait_for_selector('[data-review="publish"]', state="detached")
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')
    page.wait_for_selector(f"{NEW_DRAFT_CONTROL}:not([disabled])")
    shown = page.locator(".studio-canvas__document").inner_text()
    assert shown.startswith("Showing published revision 2"), shown
    assert page.locator(NEW_DRAFT_CONTROL).inner_text() == NEW_DRAFT


def _the_stale_confirm_wrote_nothing(
        first: Page, watching: _Window, templates, standing: dict,
        written: dict) -> None:
    """Refused in words a person can act on, and no durable byte moved.

    The write is asserted to have REACHED the server: a window that refused it
    locally would satisfy every durable assertion here and prove nothing at all
    about what the route does with a confirm of a draft that is gone.
    """
    said = first.locator(SAVE_LINE).inner_text()
    assert "not the one this window last read" in said, said
    assert "Nothing here was written" in said, said
    assert "The request shape is invalid." not in said, said
    assert templates.revisions(WORKFLOW_ID) == (1, 2), (
        "the losing window wrote a third revision")
    assert templates.load(WORKFLOW_ID, 1).as_dict() == standing
    assert templates.load(WORKFLOW_ID, 2).as_dict() == written, (
        "the losing window overwrote the revision the other one published")
    assert watching.writes("/revisions") == 2, (
        "the refused confirm never reached the server")


def test_a_second_window_that_publishes_first_refuses_the_stale_confirm(
        chromium: Browser, project: _Project) -> None:
    """Two windows, one revision number, and the loser writes nothing.

    The first window saves a draft and opens its review. The second reads that
    draft, edits it and publishes -- the legitimate collaborative road -- which
    CONSUMES the one draft this workflow has. The first then confirms a review
    of a document the server no longer holds.

    Three things must be true. It is refused and nothing durable moves. It is
    told what actually happened -- this arm answered ``contract_invalid`` until
    the browser drove it, so a person whose draft another window had published
    was told their request shape was wrong, which is safe and unrecoverable at
    once. And the window recovers to the revision that now stands, where the
    road on is a copy.
    """
    first, watching = _open(chromium, project)
    second: Page | None = None
    try:
        _publish_the_first_revision(first, project)
        templates = project.templates()
        standing = templates.load(WORKFLOW_ID, 1).as_dict()
        # Opened after the revision exists and before the first window saves.
        second, other = _open(chromium, project)
        _choose(second, WORKFLOW_ID)
        second.wait_for_selector(
            '.studio-canvas__banner[data-document="published"]')

        node_id = _hold_a_review_of_the_next_revision(first)
        written = _the_other_window_takes_revision_two(second, project, node_id)

        first.locator('[data-focus="action:onPublishConfirm"]').click()
        first.wait_for_selector(f'{SAVE_LINE}[data-save="refused"]')

        _the_stale_confirm_wrote_nothing(
            first, watching, templates, standing, written)
        _the_stale_window_recovered_to_the_standing_revision(first)
        _the_window_itself_raised_nothing(watching)
        _the_window_itself_raised_nothing(other)
    finally:
        if second is not None:
            second.context.close()
        first.context.close()


def _another_writer_takes_revision_two(
        project: _Project, standing: dict, node_id: str) -> None:
    """Revision 2 is written by the store this product's own route writes with.

    It leaves the draft alone, which is what makes this a different failure
    from the one above: the reviewing window's draft is still there, so the
    route reaches the store and the store is what refuses.
    """
    taken = {**standing, "revision": 2,
             "nodes": [{**row, "title": THEIRS} if row["node_id"] == node_id
                       else row for row in standing["nodes"]]}
    TemplateStore(project.root).save(GraphTemplate.from_dict(taken))


def test_a_revision_written_under_an_open_review_is_refused_and_keeps_the_draft(
        chromium: Browser, project: _Project) -> None:
    """The other way to lose the race, and the one the draft survives.

    One revision is one identity, so a second document under that name is a
    conflict rather than an overwrite. Three things are asserted because they
    can come apart: nothing new is on disk, both standing revisions are byte
    for byte what they were, and the draft the person spent their work on is
    still there to publish as the revision after this one.
    """
    page, window = _open(chromium, project)
    try:
        _publish_the_first_revision(page, project)
        templates = project.templates()
        standing = templates.load(WORKFLOW_ID, 1).as_dict()
        node_id = _hold_a_review_of_the_next_revision(page)
        mine = templates.load_draft(WORKFLOW_ID)
        assert mine is not None

        _another_writer_takes_revision_two(project, standing, node_id)

        page.locator('[data-focus="action:onPublishConfirm"]').click()
        page.wait_for_selector(f'{SAVE_LINE}[data-save="refused"]')

        said = page.locator(SAVE_LINE).inner_text()
        assert "The durable record conflicts with an existing fact." in said, said
        assert templates.revisions(WORKFLOW_ID) == (1, 2)
        assert templates.load(WORKFLOW_ID, 1).as_dict() == standing
        assert _step_title(templates.load(WORKFLOW_ID, 2).as_dict(),
                           node_id) == THEIRS, (
            "the refused publish overwrote the revision that beat it")
        survived = templates.load_draft(WORKFLOW_ID)
        assert survived is not None, (
            "a refused publish consumed the draft it did not publish")
        assert survived.settled() == mine.settled()
        assert _step_title(survived.settled(), node_id) == MINE
        _the_window_itself_raised_nothing(window)
    finally:
        page.context.close()
