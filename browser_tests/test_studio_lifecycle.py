"""The Studio's durable life, in a real Chromium against the real server.

What ``test_studio_editing`` proves stops at the edge of this window: an edit
lives in one tab until a Human presses a button. This module crosses that edge
and comes back. Every fact below is written through a production route, read
back through a production route, and checked a THIRD time against the durable
files themselves -- because "the screen says it was saved" and "the store holds
it" are two claims, and a browser test that only makes the first one is
measuring a render.

The three subjects, in the order a person meets them:

1. a draft survives a full page reload, and it comes back from the SERVER --
   both browser stores are measured empty on the way out and on the way back;
2. publishing turns that draft into an immutable revision, clears the draft,
   and the revision is read back through its own route before the window says
   a word about it;
3. a dropped stream shuts the write door, and a REFUSED READ does not take the
   drawing. That last one is the most expensive invariant this product has --
   it was measured once as "nine steps on screen, zero after the socket came
   back" -- and it is the reason this module exists at all.

WHAT MOVED OUT. This module crossed 800 lines carrying two circuits, so the
second one went to ``browser_tests/test_studio_run_journal.py``: everything
about a RUN's own durable records -- the timeline in append order, the
``verification_failed`` sentence, and the decision receipt a Human writes into
the journal. The seam is real rather than convenient: what is left here is
about a workflow DOCUMENT and the socket it is read over, and a run appears
below only as the stage a dropped stream is measured on. The seeded project,
the page helpers and the stream double stay here and that module imports them,
so one run is still described in one place.

THE STREAM DOUBLE IS NOT A PRODUCTION SEAM. ``studio.js`` exposes nothing on
``window`` -- there is no ``window.conductStudio`` answering to the graph
window's ``window.conductGraph`` -- and none was added for these tests. What is
replaced below is the BROWSER's own ``EventSource``, installed with
``add_init_script`` before any page script runs, exactly as
``test_graph_wire._STREAM_DOUBLE`` does it. The production ``open`` and
``error`` handlers in ``studio.js`` are what run; every other fact on screen
arrives through a real read of a real route.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command import control_loop, preview
from conductor.command.adapters.base import AdapterRegistry
from conductor.command.contracts import DecisionReceipt
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import draft_digest

from tests.alpha3_graph_artifacts import dalio_definition
from tests.test_command_graph_projection import (
    a_proposal,
    a_request,
    a_result,
    an_event,
    an_evidence,
)
from tests.test_command_run_store import a_run
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_store import good_lane, write_project

#: The seeded run's id is the frozen artifact's own: `dalio_definition` builds
#: its document for one run, and every journal helper beside it is written for
#: the same one. A different id here would be a different document.
RUN_ID = "run-001"
CONFIRM_GATE = "gate-confirm-do"
DECIDER = "release-owner"
#: The bundled starter this module draws from, and what it carries.
STARTER = "dalio-v1"
STARTER_STEPS = 8
#: The control that copies a published revision into a draft, spelled the way
#: `studio-view.saveControls` spells it, and named once for every importer.
NEW_DRAFT = "Edit as new draft"
NEW_DRAFT_CONTROL = '#workflowToolbar [data-focus="action:onEditPublished"]'
TOKEN = "browser-only-process-token"
#: The frozen configuration the Studio's OWN open-run route writes, spelled the
#: way ``studio_contracts.RunInput.snapshot`` spells it: a cycle that is exactly
#: an id, and instances that are exactly an id, an adapter, and a model only
#: when one is pinned. It is written here rather than borrowed from the
#: Cockpit-era test fixture because the two are not the same document -- the
#: older one carries a credential-variable name on an instance, which the
#: Studio's boundary still refuses and should. Its `phases` on the cycle is a
#: different story: the boundary refused that too, until a run written by
#: `conduct preview` -- this product's own road, into this same runs directory
#: -- turned out to be listable and unopenable here. `studio-model.CYCLE_KEYS`
#: admits `phases` now and reads nothing out of it, and the guard on that lives
#: in `test_studio_run_journal`, on the run `_seed_preview_shaped_run` writes.
STUDIO_CONFIG = {
    "cycle": {"id": "default-orbit"},
    "instances": [{"id": "claude-dev", "adapter": "claude-code"}],
}
DIGEST = snapshot_digest(STUDIO_CONFIG)
#: The run seeded with a configuration THIS PRODUCT writes on another road.
#: `conduct preview`'s own fixed run id, taken from the module that mints it
#: rather than spelled here: the seed below drives that road for real, so a
#: name of this test's own choosing would simply not be the run it created.
PREVIEW_RUN = preview._RUN_ID


def _seed_run(root: Path) -> None:
    """One run whose journal walks the whole progression and ends unverified.

    The last two records are the point. An attempt boundary was OBSERVED with
    its own ``succeeded`` and exit code 0 -- a watched process really did
    finish -- and the immutable result written for it says
    ``verification_failed``. Exit 0 is a fact about a process; verification is
    a fact about the work, and this journal is the sharpest form of the case
    where a build that read one as the other would report a success.
    """
    store = RunStore(root)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm", config_digest=DIGEST),
        STUDIO_CONFIG)
    store.append(dalio_definition(run_id=RUN_ID))
    proposal = a_proposal(node_id="do", index=1, config_digest=DIGEST)
    store.append(proposal)
    request = a_request(proposal, index=1)
    store.append(request)
    store.append(an_event(request, "effect_lease", index=1))
    store.append(an_event(request, "execution_observed", index=1,
                          outcome="succeeded", exit_code=0))
    # `unverified` names no verifier and no instant, and the contract refuses a
    # row that claims one -- so both are cleared rather than left at the
    # helper's verified defaults.
    store.append(an_evidence(request, index=1, verification="unverified",
                             verified_by=None, verified_at=None))
    # No `evidence_refs`: the store refuses a result that is not a succeeded,
    # event-bearing one from referencing evidence at all -- which is the same
    # rule from the other side, and exactly why this journal is honest.
    store.append(a_result(request, index=1, outcome="verification_failed",
                          exit_code=0, evidence_refs=()))


def _seed_preview_shaped_run(root: Path) -> None:
    """One run whose frozen configuration is written by THIS product's own
    ``conduct preview`` road -- the constant itself, never a copy of it.

    ``preview.FROZEN_CONFIG`` and ``control_loop.FROZEN_CONFIG`` both write a
    cycle carrying ``phases`` beside ``id``. Importing the constant is what
    makes the test below a statement about the product rather than about a
    document written down beside it: a build that changed the shape on either
    side moves this run with it.
    """
    assert preview.FROZEN_CONFIG["cycle"].keys() == {"id", "phases"}
    assert control_loop.FROZEN_CONFIG["cycle"].keys() == {"id", "phases"}
    # The production road itself, not a reconstruction of what it leaves. It
    # creates the run under its own fixed id AND appends the one proposal a real
    # `conduct preview` mints, so the Studio is asked to open a run that IS the
    # product's output rather than a fixture shaped like one -- and the journal
    # it must render has something in it, which an empty run would not.
    preview.render_dispatch_preview(str(root))
    replayed = RunStore(root).read(PREVIEW_RUN)
    assert [row.kind for row in replayed.records] == ["action_proposal"]


class _Project:
    """The served URL and the durable tree behind it, for the third check."""

    def __init__(self, url: str, root: Path) -> None:
        self.url = url
        self.root = root

    def templates(self) -> TemplateStore:
        return TemplateStore(self.root)

    def record_kinds(self) -> list[str]:
        """The seeded journal's kinds, in append order, off the store itself."""
        return [row.kind for row in RunStore(self.root).read(RUN_ID).records]

    def receipts(self) -> list[DecisionReceipt]:
        return [row.value for row in RunStore(self.root).read(RUN_ID).records
                if isinstance(row.value, DecisionReceipt)]


@pytest.fixture
def project(tmp_path) -> Iterator[_Project]:
    """A real server over a project holding one seeded run and no workflow."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    _seed_run(root)
    _seed_preview_shaped_run(root)
    httpd = server.build(
        root, 0,
        registry=AdapterRegistry([
            DeepPlanAdapter(name) for name in
            sorted({row["adapter"] for row in STUDIO_CONFIG["instances"]})]),
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield _Project(f"http://{host}:{port}/", root)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "studio server did not stop"


#: A stand-in for the browser's own EventSource, installed before any page
#: script runs, so the drop and the reconnect can be driven exactly. It calls
#: the REAL production handlers -- nothing about the window is doubled but the
#: socket -- and it opens the way a real one does, on the turn after the
#: constructor returns, because the page attaches its listener on the line
#: after `new EventSource(...)`.
_STREAM_DOUBLE = """
class TestStream {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.onmessage = null;
    window.__stream = this;
    setTimeout(() => this.fire("open"), 0);
  }
  addEventListener(name, handler) {
    (this.listeners[name] = this.listeners[name] || []).push(handler);
  }
  emit(data) { if (this.onmessage) this.onmessage({data}); }
  fire(name) { for (const h of this.listeners[name] || []) h({}); }
  close() {}
}
window.EventSource = TestStream;
"""


class _Window:
    """One opened Studio, its console log and its request log."""

    def __init__(self, page: Page) -> None:
        self.page = page
        #: Kept apart on purpose. A page error is always the window's; a
        #: console error can also be the BROWSER's own note that a resource
        #: answered non-2xx, which is what a refused read looks like from the
        #: network stack and is not a fault in the code under test.
        self.console_errors: list[str] = []
        self.page_errors: list[str] = []
        #: Method, url and BODY: the draft route's expectation is a fact a
        #: window can drop with no rendered assertion noticing.
        self.rows: list[tuple[str, str, str | None]] = []
        page.on("console", lambda message: self.console_errors.append(
            getattr(message, "text", ""))
            if getattr(message, "type", "") == "error" else None)
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.on("request", lambda request: self.rows.append(
            (request.method, request.url, request.post_data)))

    @property
    def problems(self) -> list[str]:
        return self.console_errors + self.page_errors

    def writes(self, fragment: str) -> int:
        return len([row for row in self.rows
                    if row[0] == "POST" and fragment in row[1]])

    def posted(self, fragment: str) -> list[dict]:
        """Every body this window POSTed to a matching route, parsed."""
        return [json.loads(row[2]) for row in self.rows
                if row[0] == "POST" and fragment in row[1] and row[2]]

    def node_ids(self) -> list[str]:
        return self.page.locator("[data-node-id]").evaluate_all(
            "nodes => nodes.map(node => node.dataset.nodeId)")

    def storage(self) -> list[int]:
        return self.page.evaluate(
            "() => [localStorage.length, sessionStorage.length]")


def _open(chromium: Browser, project: _Project, *,
          double: bool = False) -> tuple[Page, _Window]:
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    if double:
        context.add_init_script(_STREAM_DOUBLE)
    page = context.new_page()
    window = _Window(page)
    page.goto(project.url, wait_until="load")
    _settle(page)
    return page, window


def _settle(page: Page) -> None:
    """Boot, then the open stream: both waited on as real signals."""
    page.wait_for_function(
        "() => document.getElementById('studioPrimary').children.length > 0")
    page.wait_for_selector('#studioConnection[data-connection="open"]')


def _start_from_starter(page: Page, workflow_id: str) -> None:
    """Open a new workflow id on a bundled starting document."""
    page.locator("#navWorkflow").click()
    page.locator('[data-focus="new-workflow"]').fill(workflow_id)
    page.locator("#workflowToolbar select[name='new-from']").select_option(
        STARTER)
    page.locator('[data-focus="action:onStartWorkflow"]').click()
    page.wait_for_function(
        "n => document.querySelectorAll('[data-node-id]').length === n",
        arg=STARTER_STEPS)


def _save_draft(page: Page) -> None:
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
    page.locator('#workflowToolbar [data-focus="action:onSaveDraft"]').click()
    page.wait_for_selector('#workflowToolbar [data-save="saved"]')


def _publish(page: Page) -> None:
    """Publish through the REVIEW, which is the only road there is now.

    Publishing used to be one click. It is two: the first opens a panel naming
    the revision about to be created and what would change, and only the
    Confirm inside it reaches the wire. A helper rather than four copies of the
    sequence, so a third step added to the road moves every caller at once.
    """
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onPublish"]:not([disabled])')
    page.locator('#workflowToolbar [data-focus="action:onPublish"]').click()
    page.wait_for_selector('[data-review="publish"]')
    page.locator('[data-focus="action:onPublishConfirm"]').click()


def _read_the_run(page: Page) -> None:
    """Open the seeded run whole, waiting on its journal being drawn.

    Defined here as well as in ``test_studio_run_journal``: that module owns
    the run's own subject and this one needs the run only as the stage a
    dropped socket is measured on, and an import in that direction would make
    two modules that share a fixture into two modules that import each other.
    """
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
    page.wait_for_selector("ol.studio-timeline")


def _choose(page: Page, workflow_id: str) -> None:
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        workflow_id)


def _refuse_reads_of(page: Page, workflow_id: str) -> None:
    """Make one workflow's read LAND and be refused, in the server's vocabulary.

    Not a transport error, and not a payload this window failed to parse: a 503
    carrying the store's own error code, which is what a refused read really is
    from the other side. The caller unroutes it in its own `finally`.
    """
    page.route(
        f"**/command/workflows/{workflow_id}",
        lambda route: route.fulfill(
            status=503, content_type="application/json",
            body=json.dumps({"error": {"code": "store_error",
                                       "message": "refused for this test"}})))


def _wait_for_the_reconnects_reads(page: Page) -> None:
    """Wait on the REQUESTS having been answered, never on a word.

    A reconnect fires three reads at once and two of them write the same
    ``workflows.phase`` and the same ``notice``, so any sentence on screen may
    be overwritten by whichever response lands last. The drawing being present
    and the write door being shut are the deterministic signals.
    """
    page.wait_for_function(
        "() => document.querySelectorAll("
        "'#workflowEdges [data-edge], [data-node-id]').length > 0")
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"][disabled]')


# -- 1. a draft outlives the tab that drew it --------------------------------


def test_a_saved_draft_comes_back_from_the_server_after_a_full_reload(
        chromium: Browser, project: _Project) -> None:
    """The draft is durable, and the browser is provably not where it lived.

    Both storages are measured on the way out and on the way back. A window
    that cached the drawing locally would pass every visible assertion here and
    fail exactly one of these two, which is why they are measured rather than
    reasoned about.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, "reload-bench")
        assert window.storage() == [0, 0]
        _save_draft(page)
        # The third check: the durable file, read with the production store.
        stored = project.templates().load_draft("reload-bench")
        assert stored is not None
        document = stored.settled()
        assert sorted(document) == ["edges", "nodes", "schema_version", "title"]
        assert len(document["nodes"]) == STARTER_STEPS
        drawn = window.node_ids()

        page.reload(wait_until="load")
        _settle(page)
        assert window.storage() == [0, 0], (
            "the window put something in browser storage across a reload")
        assert window.node_ids() == [], (
            "a drawing survived a reload without a read; it came from the tab")
        _choose(page, "reload-bench")
        page.wait_for_selector(
            '.studio-canvas__banner[data-document="draft"]')
        page.wait_for_function(
            "n => document.querySelectorAll('[data-node-id]').length === n",
            arg=STARTER_STEPS)
        assert window.node_ids() == drawn
        # And it is the SERVER's draft, stamped with the server's own instant.
        assert stored.saved_at in page.locator(
            "#workflowDiagnostics").inner_text()
        assert window.problems == []
    finally:
        page.context.close()


def test_saving_the_same_drawing_twice_does_not_move_the_stored_instant(
        chromium: Browser, project: _Project) -> None:
    """Idempotence is about the DOCUMENT, not about the request.

    A client whose reply was lost re-sends the same drawing. Stamping it with a
    new clock would rewrite the file and move a timestamp the screen is showing
    for a request that changed nothing.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, "twice-bench")
        _save_draft(page)
        first = project.templates().load_draft("twice-bench")
        assert first is not None
        page.locator(
            '#workflowToolbar [data-focus="action:onSaveDraft"]').click()
        page.wait_for_function(
            "() => document.querySelector('#workflowToolbar [data-save]')"
            ".dataset.save === 'saved'")
        again = project.templates().load_draft("twice-bench")
        assert again is not None
        assert again.saved_at == first.saved_at
        assert again.settled() == first.settled()
        assert window.writes("/draft") == 2, (
            "the second save never reached the server, so this proved nothing")
        # Two saves, two claims: the second names the draft the first stored.
        sent = window.posted("/draft")
        assert [sorted(set(body) - {"document"}) for body in sent] == [
            ["expected_absent"], ["expected_digest"]]
        assert sent[1]["expected_digest"] == draft_digest(first.settled())
        assert window.problems == []
    finally:
        page.context.close()


# -- 2. publishing --------------------------------------------------------


def test_publishing_makes_one_revision_clears_the_draft_and_reads_it_back(
        chromium: Browser, project: _Project) -> None:
    """The whole publish, and the read-back is what licenses the sentence.

    The window says nothing about a publish until it has read the revision back
    through the revision's OWN route: `confirmedBy` compares the number and the
    workflow the write asked for against a payload that answered. So the
    sentence on screen is itself evidence of the read-back, and the durable
    tree is checked beside it.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, "publish-bench")
        _save_draft(page)
        publish = page.locator(
            '#workflowToolbar [data-focus="action:onPublish"]')
        page.wait_for_selector(
            '#workflowToolbar [data-focus="action:onPublish"]:not([disabled])')
        assert publish.inner_text() == "Publish revision 1"
        # The review stands between the pointer and the write, naming the
        # number about to be created before anything is written.
        publish.click()
        _review_names_the_number(page, project, "publish-bench", 1)
        page.locator('[data-focus="action:onPublishConfirm"]').click()
        page.wait_for_selector(
            '.studio-canvas__banner[data-document="published"]')

        said = page.locator('#workflowToolbar [data-save]').inner_text()
        assert "The revision is published and read back" in said, said
        assert "immutable" in said, said
        templates = project.templates()
        assert templates.revisions("publish-bench") == (1,)
        assert templates.load_draft("publish-bench") is None, (
            "the draft outlived the revision it became")
        assert templates.load("publish-bench", 1).title == \
            "Dalio five-step cycle"
        # The window read it back through the revision route, once.
        assert len([row for row in window.rows if row[0] == "GET"
                    and row[1].endswith(
                        "/command/workflows/publish-bench/revisions/1")]) == 1
        assert page.locator(".studio-canvas__document").inner_text().startswith(
            "Showing published revision 1")
        assert len(window.node_ids()) == STARTER_STEPS
        assert window.problems == []
    finally:
        page.context.close()


def _review_names_the_number(page, project, workflow_id: str, number: int) -> None:
    """The panel is open, says which revision, and has written nothing yet."""
    page.wait_for_selector('[data-review="publish"]')
    # Lowered because `inner_text` answers with what is PAINTED, and the
    # stylesheet upper-cases this heading. Matching the source casing would be
    # pinning the stylesheet by accident.
    said = page.locator('[data-review="publish"]').inner_text().lower()
    assert f"publish revision {number}?" in said, said
    assert "immutable" in said, said
    assert project.templates().revisions(workflow_id) == (), (
        "the review wrote a revision before anybody confirmed it")


def _nothing_was_written(project, window, workflow_id: str) -> None:
    """"Wrote nothing" has three meanings, and they can come apart.

    No revision on disk, no POST on the wire, and the draft still there to keep
    editing. A Cancel that discarded the drawing would satisfy the first two and
    still lose the user's work.
    """
    templates = project.templates()
    assert templates.revisions(workflow_id) == ()
    assert templates.load_draft(workflow_id) is not None, (
        "cancelling the review discarded the draft")
    assert window.writes("/revisions") == 0


def test_cancelling_the_publish_review_writes_absolutely_nothing(
        chromium: Browser, project: _Project) -> None:
    """Cancel is a way out, and a way out that writes is not one.

    Asserted on three surfaces because "wrote nothing" has three meanings that
    can come apart: no revision on disk, no POST on the wire, and the draft
    still there to keep editing. A Cancel that discarded the drawing would
    satisfy the first two and still lose the user's work.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, "cancel-bench")
        _save_draft(page)
        page.wait_for_selector(
            '#workflowToolbar [data-focus="action:onPublish"]:not([disabled])')
        page.locator('#workflowToolbar [data-focus="action:onPublish"]').click()
        page.wait_for_selector('[data-review="publish"]')

        page.locator('[data-focus="action:onPublishCancel"]').click()
        page.wait_for_selector('[data-review="publish"]', state="detached")

        _nothing_was_written(project, window, "cancel-bench")
        # And the road is still open: the button is back, not spent.
        assert not page.locator(
            '#workflowToolbar [data-focus="action:onPublish"]').is_disabled()
        assert window.problems == []
    finally:
        page.context.close()


def test_the_window_cannot_publish_the_same_document_a_second_time(
        chromium: Browser, project: _Project) -> None:
    """One document, one revision, and the second attempt is unreachable.

    After a publish the draft is gone, so there is nothing to publish and
    nothing to save -- and both controls say exactly that rather than sitting
    there ready to write a second identical revision. The durable tree is
    checked too, because "the button is grey" is a claim about a button. What
    may NOT follow is a dead end, and this test used to record one: three
    disabled controls and no road on at all.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, "once-bench")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector(
            '.studio-canvas__banner[data-document="published"]')

        publish = page.locator(
            '#workflowToolbar [data-focus="action:onPublish"]')
        save = page.locator(
            '#workflowToolbar [data-focus="action:onSaveDraft"]')
        fresh = page.locator(NEW_DRAFT_CONTROL)
        assert publish.is_disabled()
        assert "Publishing needs a SAVED draft" in publish.get_attribute("title")
        assert save.is_disabled()
        assert save.get_attribute("title") == (
            "There is no drawing to save. Edit as new draft copies the "
            "published revision into one you can change.")
        assert not fresh.is_disabled(), "no road on was offered"
        assert fresh.inner_text() == NEW_DRAFT
        assert fresh.get_attribute("title") is None, "an excuse on a live road"
        assert window.writes("/revisions") == 1
        assert project.templates().revisions("once-bench") == (1,)
        assert window.problems == []
    finally:
        page.context.close()



# -- 3. the socket, and the read that follows it -----------------------------


def test_a_dropped_stream_says_so_on_every_screen_and_shuts_the_write_door(
        chromium: Browser, project: _Project) -> None:
    """A dropped stream outranks every read: the facts may be true and stale.

    Both carriers are asserted -- the machine word on each screen container and
    the sentence in the header -- and then the two workflow write controls,
    which are the doors a drop actually closes.
    """
    page, window = _open(chromium, project, double=True)
    try:
        _start_from_starter(page, "socket-bench")
        _save_draft(page)
        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_selector('#studioConnection[data-connection="closed"]')

        said = page.locator("#studioConnection").inner_text()
        assert "Connection lost" in said, said
        assert "nothing may be written until it is back" in said, said
        for container in ("screenOverview", "screenWorkflow", "screenRuns",
                          "screenDecisions", "screenAgents"):
            assert page.locator(f"#{container}").get_attribute(
                "data-state") == "disconnected", container
        assert page.locator(
            '#workflowToolbar [data-focus="action:onSaveDraft"]').is_disabled()
        assert page.locator(
            '#workflowToolbar [data-focus="action:onPublish"]').is_disabled()
        assert page.locator(
            '#studioPrimary [data-focus="action:onSaveDraft"]').is_disabled()
        assert window.problems == []
    finally:
        page.context.close()


def test_a_decision_pressed_while_the_stream_is_down_refuses_and_writes_nothing(
        chromium: Browser, project: _Project) -> None:
    """With the stream down the decision control closes, and says why.

    This test first held the opposite: the control stayed pressable while the
    two workflow write controls disabled themselves, which was reported as a
    minor asymmetry rather than a defect because the door refused loudly and
    nothing durable moved. It was still a control that looked available while
    nothing could be written, which is the thing this screen exists not to do.
    It now matches its neighbours.

    Disabled is not enough on its own, and the assertions below say so: a greyed
    button with no sentence is a dead end, so the reason has to be on screen,
    the typed actor has to survive, and nothing may reach the durable store.
    """
    page, window = _open(chromium, project, double=True)
    try:
        _read_the_run(page)
        page.locator('[data-focus-key="action:showDecisions"]').click()
        page.locator(
            f'[data-focus-key="decision:{RUN_ID}/{CONFIRM_GATE}"]').click()
        page.locator('[data-focus-key="field:actor"]').fill(DECIDER)
        page.locator('[data-focus-key="field:actor"]').press("Tab")
        submit = page.locator('[data-focus-key="action:submitDecision"]')
        page.wait_for_selector(
            '[data-focus-key="action:submitDecision"]:not([disabled])')
        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_selector('#studioConnection[data-connection="closed"]')

        assert submit.is_disabled(), (
            "the decision control stayed pressable while nothing could be written")
        said = page.locator(".studio-decide").inner_text()
        assert "connection is down" in said, (
            "the control closed without saying why: " + said)
        assert page.locator(
            '[data-focus-key="field:actor"]').input_value() == DECIDER, (
            "the drop discarded what the reader had already typed")
        assert window.writes("/decisions") == 0
        assert project.receipts() == []
        assert window.problems == []
    finally:
        page.context.close()


def test_a_refused_read_after_a_reconnect_keeps_the_whole_drawing(
        chromium: Browser, project: _Project) -> None:
    """The measured regression, held in the surface it was measured on.

    A reconnect always ends in a re-read. When that read is REFUSED it brings
    no durable fact and it is not the Human doing anything, so it may not take
    the work they have not written -- the failure this guards was eight steps
    of a nine-step plan disappearing when a socket came back.

    Three things are asserted, because any one alone passes on a build that got
    the others wrong: the drawing is whole, the write door is shut, and nothing
    was written on the way through.

    Deliberately NOT asserted here: what the screen SAYS about the refusal. A
    reconnect fires three reads at once and two of them write the same
    ``workflows.phase`` and the same ``notice``, so whether the refusal is
    still on screen afterwards depends on which response lands last -- measured
    both ways on this machine, and reported. The refusal's own words are
    asserted in the test below, where exactly one read is in flight.
    """
    page, window = _open(chromium, project, double=True)
    try:
        _start_from_starter(page, "survive-bench")
        drawn = window.node_ids()
        assert len(drawn) == STARTER_STEPS
        writes = window.writes("/draft")

        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_selector('#studioConnection[data-connection="closed"]')
        _refuse_reads_of(page, "survive-bench")
        page.evaluate("() => window.__stream.fire('open')")
        _wait_for_the_reconnects_reads(page)

        assert window.node_ids() == drawn, (
            "a refused read erased the plan the Human was about to write")
        assert page.locator(
            '#workflowToolbar [data-focus="action:onSaveDraft"]').is_disabled()
        assert window.writes("/draft") == writes, (
            "keeping a drawing became submitting one")
        # The window itself raised nothing. The one console line is Chromium's
        # own note that a fetch answered 503, which is what a refused read IS
        # from the network stack -- the refusal this test asked for.
        assert window.page_errors == []
        assert [line for line in window.console_errors
                if "Failed to load resource" not in line] == []
    finally:
        page.unroute("**/command/workflows/survive-bench")
        page.context.close()



def test_a_refused_read_says_who_holds_what_is_on_screen_and_keeps_it(
        chromium: Browser, project: _Project) -> None:
    """The refusal in its own words, with exactly one read in flight.

    ``Validate`` re-reads the chosen workflow and nothing else, so what the
    screen says about the refusal cannot be overwritten by a list read that
    happened to answer later. Both carriers are asked for: the machine word in
    ``data-state`` and the sentence naming who holds the drawing.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, "stated-bench")
        drawn = window.node_ids()
        _refuse_reads_of(page, "stated-bench")
        page.locator('#workflowToolbar [data-focus="action:onValidate"]').click()
        page.wait_for_selector('#screenWorkflow[data-state="refused"]',
                               state="attached")

        notice = page.locator("#studioStatus").inner_text()
        assert "The run store is unavailable." in notice, notice
        assert "held in this window and has not been saved" in notice, notice
        assert window.node_ids() == drawn
        assert page.locator(
            '#workflowToolbar [data-focus="action:onSaveDraft"]').is_disabled()
        assert window.page_errors == []
        assert [line for line in window.console_errors
                if "Failed to load resource" not in line] == []
    finally:
        page.unroute("**/command/workflows/stated-bench")
        page.context.close()


def test_a_reconnect_whose_read_lands_gives_the_write_door_back(
        chromium: Browser, project: _Project) -> None:
    """The over-correction control: a shut door must open again.

    Readiness names one answer about one workflow and it is granted by the
    READ, never by the socket. Without this, a build that simply never
    re-opened the door would pass every assertion in the test above.
    """
    page, window = _open(chromium, project, double=True)
    try:
        _start_from_starter(page, "reopen-bench")
        _save_draft(page)
        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_selector(
            '#workflowToolbar [data-focus="action:onSaveDraft"][disabled]')
        page.evaluate("() => window.__stream.fire('open')")
        page.wait_for_selector(
            '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')
        assert page.locator("#screenWorkflow").get_attribute(
            "data-state") == "ready"
        assert len(window.node_ids()) == STARTER_STEPS
        assert window.problems == []
    finally:
        page.context.close()
