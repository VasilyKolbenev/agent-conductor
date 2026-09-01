"""What a step's verification must NAME, chosen in a real Chromium and read back.

``required_evidence`` is the one thing a plan can honestly tighten about the
proof a step rests on. Everything else the evidence contract holds is already
pinned: exactly one verification row, of one kind, at one uri, signed by the one
identity the plan makes authoritative. The single degree of freedom left is that
``EvidenceRef.digest`` is optional -- so a verification may stand without saying
WHAT was checked, and a ``succeeded`` receipt may rest on it.

The durable half and the four enforcement layers are held in Python
(``tests/test_command_required_evidence.py``, ``tests/test_command_evidence_demand.py``).
This module drives the half those cannot reach: a person choosing the demand on
a real screen, and the draft the SERVER stores afterwards.

Three things are held here that source text cannot hold:

* **the choice reaches the durable draft and comes back.** Read off the
  ``TemplateStore``, then off a reloaded page -- never off the drawing the
  window is holding, which a build keeping the change in a tab would satisfy
  just as well.
* **the pairing rule is met before the wire, twice.** A step that binds no role
  is verified by nobody, so ``TemplateNode.__post_init__`` refuses a demand made
  of a verification that will never exist. This window refuses it in two
  independent places: the screen offers no control on such a step, and
  ``saveProblems`` -- driven here through the module the PAGE loaded -- refuses
  the document if one arrives by any other road.
* **the register really shrank on screen.** The unsupported rows are COUNTED in
  the rendered DOM and held against ``UNSUPPORTED_FIELDS``, so a label that left
  the Python register by being deleted from the screen fails here rather than
  passing both.

A module of its own because ``test_studio_lifecycle`` is at the line cap. Its
boot, save and publish helpers are imported rather than re-spelled: one road to
a published revision, described in one place.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.graph_values import REQUIRED_EVIDENCE
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from browser_tests.test_studio_editing import _Recorder, _watch
from browser_tests.test_studio_lifecycle import _publish, _save_draft, _settle
from tests.test_store import good_lane, write_project
from tests.test_studio_completeness import UNSUPPORTED_FIELDS

WORKFLOW_ID = "evidence-bench"
SAVED_AT = "2026-08-20T10:00:00Z"
ROLE = "analyst"
#: The word this build carries. Read from the contract rather than typed, so a
#: vocabulary that moves takes this module with it.
DEMAND = "digest"
#: Two steps and one connection. The first carries something out and can
#: therefore be verified; the second binds nothing, which is what makes the
#: pairing rule drivable. `observe` rather than `dispatch` on purpose -- an
#: effecting step must stand behind a gate, and this document is about a
#: verification and not about gating. The edge exists so the register census
#: below can count the connection panel's own unsupported row.
DRAFT = {
    "schema_version": 1,
    "title": "Evidence bench",
    "nodes": [
        {"node_id": "study", "kind": "task", "title": "Study the problem",
         "role_id": ROLE, "capability": "observe", "resources": []},
        {"node_id": "loose", "kind": "task", "title": "Carries nothing out",
         "resources": []},
    ],
    "edges": [{"from_node": "study", "to_node": "loose"}],
}
EVIDENCE_FIELD = '[data-edit-field="required_evidence"]'
ROLE_FIELD = '[data-edit-field="role_id"]'
#: `studio-fields.slug("Evidence requirements")`, which is how the read-only
#: line beside the control is addressed without matching prose that may be
#: rewritten.
EVIDENCE_LINE = '[data-context="evidence-requirements"]'


class _Project:
    """The served URL and the durable tree behind it, read after every write."""

    def __init__(self, url: str, root: Path) -> None:
        self.url = url
        self.root = root

    def templates(self) -> TemplateStore:
        return TemplateStore(self.root)

    def stored_node(self, node_id: str) -> dict:
        """One step of the draft the SERVER holds, never the drawing on screen."""
        draft = self.templates().load_draft(WORKFLOW_ID)
        assert draft is not None, "no draft is stored for this workflow"
        return next(row for row in draft.document["nodes"]
                    if row["node_id"] == node_id)


@pytest.fixture
def project(tmp_path) -> Iterator[_Project]:
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    TemplateStore(root).save_draft(WorkflowDraft(
        workflow_id=WORKFLOW_ID, saved_at=SAVED_AT, document=DRAFT))
    httpd = server.build(root, 0)
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


def _open_the_workflow(page: Page) -> None:
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
    page.wait_for_function(
        "() => document.querySelectorAll('[data-node-id]').length === 2")
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')


class _Bench:
    """One opened Studio on the seeded draft, with its logs."""

    def __init__(self, page: Page, problems: list[str],
                 recorder: _Recorder) -> None:
        self.page = page
        self.problems = problems
        self.recorder = recorder

    def select(self, node_id: str) -> None:
        self.page.locator(f'[data-node-id="{node_id}"]').click()
        self.page.wait_for_selector('[data-section="verification"]')

    def select_edge(self, from_id: str, to_id: str) -> None:
        self.page.locator(
            f'[data-focus="edge-select-{from_id} {to_id}"]').click()
        self.page.wait_for_selector('[data-panel="edge"]')

    def requirement(self):
        return self.page.locator(EVIDENCE_FIELD)

    def options(self) -> list[str]:
        return self.page.locator(f"{EVIDENCE_FIELD} option").evaluate_all(
            "rows => rows.map(row => row.value)")

    def evidence_line(self) -> str:
        return self.page.locator(EVIDENCE_LINE).inner_text()

    def unsupported_rows(self) -> list[str]:
        return self.page.locator("[data-unsupported]").evaluate_all(
            "rows => rows.map(row => row.getAttribute('data-unsupported'))")


@pytest.fixture
def bench(chromium: Browser, project: _Project) -> Iterator[_Bench]:
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    page = context.new_page()
    problems = _watch(page)
    recorder = _Recorder(page)
    page.goto(project.url, wait_until="load")
    _settle(page)
    _open_the_workflow(page)
    try:
        yield _Bench(page, problems, recorder)
    finally:
        context.close()


# -- 1. the choices are the contract's, read off the running page -------------


def test_the_requirement_offers_the_contracts_words_and_a_way_back(
        bench: _Bench) -> None:
    """A relation between the rendered options and the Python vocabulary.

    The empty option is asserted, and it is FIRST: naming no requirement is the
    state every step this window draws starts in, so a control that could not
    return there would be the one-way door `unplaceNode` exists to refuse -- and
    a person who tightened a step by accident could never untighten it.
    """
    bench.select("study")

    assert bench.options() == [""] + sorted(REQUIRED_EVIDENCE), bench.options()
    assert bench.requirement().input_value() == "", (
        "the seeded step already names a requirement")
    assert "held to the runtime's own rule" in bench.evidence_line()
    assert bench.problems == []


# -- 2. it round-trips through the durable draft ------------------------------


def test_choosing_a_requirement_reaches_the_stored_draft_and_comes_back(
        bench: _Bench, project: _Project) -> None:
    """The whole point of the slice: a plan word a person can actually write.

    Asserted against the draft the SERVER stored and then against a reloaded
    page, so nothing here can be satisfied by a window holding the change in a
    tab. The line beside the control moves with it, because a field that leaves
    the unsupported register must keep SAYING what it is as well as letting it
    be set.
    """
    before = project.stored_node("study")
    assert "required_evidence" not in before, before

    bench.select("study")
    bench.requirement().select_option(DEMAND)
    bench.page.wait_for_function(
        "() => document.querySelector('[data-context=\\'evidence-requirements\\']')"
        ".innerText.includes('name what it checked')")
    _save_draft(bench.page)

    stored = project.stored_node("study")
    assert stored["required_evidence"] == DEMAND, stored
    assert stored["role_id"] == ROLE, stored

    bench.page.reload(wait_until="load")
    _settle(bench.page)
    _open_the_workflow(bench.page)
    bench.select("study")
    assert bench.requirement().input_value() == DEMAND
    assert "name what it checked" in bench.evidence_line()
    assert bench.problems == []


# -- 3. the pairing rule, refused in two independent places -------------------


def test_a_step_that_binds_no_role_is_told_why_and_offered_no_control(
        bench: _Bench) -> None:
    """The contract's rule, met beside the control instead of at the save.

    A step that binds no role carries nothing out, is verified by nobody, and
    has no verification for a demand to be made of -- so `TemplateNode` refuses
    one. Offering the control anyway would be offering a choice the save
    rejects, which is why this step gets the reason and no select.
    """
    bench.select("loose")

    assert bench.requirement().count() == 0, (
        "a step nobody verifies was offered a requirement to make of nobody")
    assert "nobody verifies it" in bench.evidence_line()
    assert bench.problems == []


def test_a_document_that_makes_the_demand_anyway_is_refused_before_the_wire(
        bench: _Bench) -> None:
    """The second, independent door -- and the one a future edit arm could need.

    The screen above cannot produce this document. `saveProblems` refuses it
    regardless, because the inspector is not the only road into a draft: a new
    edit arm, a duplicate, or a document from another client could all put a
    demand on a role-less step, and a save that reached the wire would come back
    as a refusal naming a field nobody had touched.

    Driven through the module the PAGE really loaded, so this is the shipped
    reducer answering and not a copy of its rule kept beside the test.
    """
    refused = bench.page.evaluate(
        """(demand) => import("/panel/studio-store.js").then((module) => [
             ...module.saveProblems({
               title: "Evidence bench",
               nodes: [{node_id: "loose", kind: "task", title: "Carries nothing",
                        required_evidence: demand, resources: []}],
               edges: []})])""", DEMAND)

    assert any("verification it will never have" in row for row in refused), (
        refused)
    # And it is this rule speaking rather than the whole document being unsavable
    # for some other reason: the same step without the demand raises nothing.
    clean = bench.page.evaluate(
        """() => import("/panel/studio-store.js").then((module) => [
             ...module.saveProblems({
               title: "Evidence bench",
               nodes: [{node_id: "loose", kind: "task", title: "Carries nothing",
                        resources: []}],
               edges: []})])""")
    assert clean == [], clean
    assert bench.problems == []


# -- 4. clearing the role takes the requirement with it -----------------------


def test_clearing_the_role_clears_the_requirement_and_the_draft_still_saves(
        bench: _Bench, project: _Project) -> None:
    """A control a person did not touch may not make their draft unsavable.

    Clearing the role is the gesture; the requirement going with it is the rule.
    Without it the document left behind is exactly the one the test above proves
    is refused, and the person would meet a refusal about a field they emptied
    nothing in. The save is what makes this a claim about a document the server
    accepted rather than about a control that looks blank.
    """
    page = bench.page
    bench.select("study")
    bench.requirement().select_option(DEMAND)
    page.wait_for_function(
        "() => document.querySelector('[data-edit-field=\\'required_evidence\\']')"
        ".value !== ''")

    role = page.locator(ROLE_FIELD)
    role.fill("")
    role.press("Tab")
    page.wait_for_selector(EVIDENCE_LINE)
    assert bench.requirement().count() == 0, (
        "the step binds no role now and is still offered a requirement")
    _save_draft(page)

    stored = project.stored_node("study")
    assert "required_evidence" not in stored, stored
    assert "role_id" not in stored and "capability" not in stored, stored
    assert bench.problems == []


# -- 5. a published revision states it and refuses to be edited ---------------


def test_a_published_revision_shows_the_requirement_and_shuts_the_control(
        bench: _Bench) -> None:
    """The read-only half, which is the one a shrinking register loses first.

    A control disabled by being deleted would satisfy every "cannot be edited"
    assertion and tell a reader of a published revision nothing about what its
    step's verification must name. Both halves are held: the value is on the
    screen, the sentence is beside it, and the control is shut.
    """
    page = bench.page
    bench.select("study")
    bench.requirement().select_option(DEMAND)
    _save_draft(page)
    _publish(page)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')

    bench.select("study")
    assert bench.requirement().input_value() == DEMAND
    assert bench.requirement().is_disabled(), (
        "a published revision is immutable and its controls say so by being shut")
    assert "name what it checked" in bench.evidence_line()
    assert bench.problems == []


# -- 6. the register really shrank, counted in the rendered DOM ---------------


def test_the_register_on_screen_is_the_register_the_census_pins(
        bench: _Bench) -> None:
    """The census counts SOURCE; this counts what a person actually meets.

    A label that left `UNSUPPORTED_FIELDS` by being deleted from the screen
    would satisfy the Python census and leave a gap where an honest "this build
    does not do that" belonged. So the rendered rows are counted and their union
    is held against the register itself -- all three on a step now, and NONE on
    a connection, because `Condition` became a control in the routing slice.
    """
    bench.select("study")
    on_a_step = bench.unsupported_rows()
    bench.select_edge("study", "loose")
    on_an_edge = bench.unsupported_rows()

    # The edge panel says nothing is unsupported any more: it offers the select.
    assert on_an_edge == [], on_an_edge
    assert bench.page.locator(
        '[data-panel="edge"] select[name="edge_condition"]').count() == 1
    assert set(on_a_step) | set(on_an_edge) == {
        row.lower().replace(" ", "-").replace("/", "-")
        for row in UNSUPPORTED_FIELDS}
    assert len(on_a_step) + len(on_an_edge) == len(UNSUPPORTED_FIELDS)
    assert "evidence-requirements" not in on_a_step, (
        "the requirement is a control now and must not also say it is unsupported")
    # The two rewritten rows still SAY something, and say the right thing.
    verification = bench.page.locator('[data-section="verification"]')
    bench.select("study")
    said = verification.inner_text()
    assert "already demands of every step" in said, said
    # And the failure-policy row no longer claims this build walks nothing: it
    # does now, and what a plan still cannot say is HALT.
    assert "the schedule walks it" in said, said
    assert "walks no connections" not in said, said
    assert bench.problems == []
