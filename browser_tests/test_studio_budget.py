"""The output budget a step names, chosen in a real Chromium and read back.

``output_limit_profile`` was the release verdict's own example of a field built
and never reached: declared on every dispatch, validated against a closed
vocabulary, carried in every shipped starter, and spent for real by
``headless_cli._spawn`` -- while the one window that draws a workflow could only
STATE it. This module drives the control that closes that, against the real
loopback server and the real ``TemplateStore``.

Two things are held here that source text cannot hold, and they are the two
ways this control could be wrong while looking right:

* **The choices are the reviewed schema's own.** They are compared against
  ``CAPABILITY_FIELDS`` read out of the module the PAGE loaded, so this is a
  relation between the rendered options and the projection the Cockpit's
  proposal composer is built from -- not a list of words written here. A
  control that had grown its own copy passes every literal-free source guard
  and reds here the moment the projection moves.
* **Every other argument survives.** A dispatch payload carries four more
  fields. An edit that rebuilt the map around its own key would delete them
  into a draft that saves cleanly, and the loss would surface much later as a
  run that will not open. The siblings are compared byte for byte against the
  seeded document, off the store rather than off the screen.

WHAT IS NOT ASSERTED, and why the obvious version of it would be false: there is
no witness here that the draft route refuses a profile outside the enum, because
it does not. ``TemplateNode._settle_arguments`` asks for JSON and for a role to
read it, and judges no capability schema at all -- the schema is enforced at run
open, by ``http_api._servable_pair``, and at the proposal door. So the guard
against an out-of-enum value is that the control cannot OFFER one: its options
are the projection's row, held to it above. A test claiming a refusal would be
green for reasons that have nothing to do with the claim it makes.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.adapters.deep_commands import OUTPUT_LIMIT_BYTES
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from browser_tests.test_studio_editing import _Recorder, _watch
from browser_tests.test_studio_lifecycle import _publish, _save_draft, _settle
from tests.test_store import good_lane, write_project

WORKFLOW_ID = "budget-bench"
SAVED_AT = "2026-08-20T10:00:00Z"
CAPABILITY = "dispatch"
#: The four arguments that are NOT the budget. They are what an edit to the
#: budget must leave alone, so they are named once and compared whole.
SIBLINGS = {
    "work_item_id": "wi-001",
    "instruction_ref": "instructions-v1",
    "profile": "implement",
    "artifact_refs": ["notes-v1", "spec-v1"],
}
SEEDED_PROFILE = "normal"
#: A gate in front of the acting step, because `_settle_effect_roads` refuses a
#: revision whose effecting step is reachable without one. The document has to
#: PUBLISH for the read-only half of this module to have anything to read.
DRAFT = {
    "schema_version": 1,
    "title": "Budget bench",
    "nodes": [
        {"node_id": "approve", "kind": "gate", "title": "Approve the work",
         "gate_id": "gate-approve", "resources": []},
        {"node_id": "build", "kind": "task", "title": "Carry it out",
         "role_id": "builder", "capability": CAPABILITY,
         "arguments": {**SIBLINGS, "output_limit_profile": SEEDED_PROFILE},
         "resources": []},
    ],
    "edges": [{"from_node": "approve", "to_node": "build"}],
}
BUDGET_FIELD = '[data-edit-field="output_limit_profile"]'
#: `studio-fields.slug("Output budget")`, which is how the read-only line beside
#: the control is addressed without matching prose that may be rewritten.
BUDGET_LINE = '[data-context="output-budget"]'


class _Project:
    def __init__(self, url: str, root: Path) -> None:
        self.url = url
        self.root = root

    def templates(self) -> TemplateStore:
        return TemplateStore(self.root)

    def stored_arguments(self) -> dict:
        """The acting step's arguments, off the draft the SERVER holds."""
        draft = self.templates().load_draft(WORKFLOW_ID)
        assert draft is not None, "no draft is stored for this workflow"
        node = next(row for row in draft.document["nodes"]
                    if row["node_id"] == "build")
        return node["arguments"]


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


def _declared_enum(page: Page, capability: str, field: str) -> list[str]:
    """The enum one capability's REVIEWED projection declares for one field.

    Read out of the module the page really loaded, so this is the shipped
    table rather than a copy of it kept beside the test. That is what makes
    the comparison below a relation: move the projection and the control has
    to move with it or this reds.
    """
    return page.evaluate(
        """([capability, field]) => import("/panel/command-projection.js")
             .then(module => {
               const row = module.CAPABILITY_FIELDS[capability].find(
                 (entry) => entry[0] === field && entry[1] === "enum");
               return row === undefined ? null : [...row[2]];
             })""",
        [capability, field])


def _without_budget(arguments) -> dict:
    """One argument map with the field under edit taken out of it."""
    return {name: value for name, value in arguments.items()
            if name != "output_limit_profile"}


class _Bench:
    def __init__(self, page: Page, problems: list[str],
                 recorder: _Recorder) -> None:
        self.page = page
        self.problems = problems
        self.recorder = recorder

    def select_step(self, node_id: str) -> None:
        self.page.locator(f'[data-node-id="{node_id}"]').click()
        self.page.wait_for_selector('[data-section="execution"]')

    def budget(self):
        return self.page.locator(BUDGET_FIELD)

    def options(self) -> list[str]:
        return self.page.locator(f"{BUDGET_FIELD} option").evaluate_all(
            "rows => rows.map(row => row.value)")

    def budget_line(self) -> str:
        return self.page.locator(BUDGET_LINE).inner_text()


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


# -- 1. the choices are the reviewed schema's, read off the running page -------


def test_the_budget_offers_exactly_the_enum_the_projection_declares(
        bench: _Bench) -> None:
    """A relation, so a control with its own copy of the words cannot pass.

    The empty option is asserted too, and it is first: an absent profile is the
    state every dispatch step this window draws starts in, so a control that
    could not represent it would be describing documents that do not exist.
    """
    bench.select_step("build")
    declared = _declared_enum(bench.page, CAPABILITY, "output_limit_profile")
    assert declared, "the page's own projection declares no profile enum"

    assert bench.options() == [""] + declared, bench.options()
    # The gate step names no capability, so the reviewed schema declares no
    # profile for it and the section says so instead of offering a control.
    bench.select_step("approve")
    assert bench.budget().count() == 0
    assert "declares no output limit profile" in bench.budget_line()
    assert bench.problems == []


# -- 2. the bytes beside the control are the bytes the spawn would spend -------


def test_the_line_beside_the_control_names_the_bytes_of_what_is_chosen(
        bench: _Bench) -> None:
    """The number moves with the choice, and it is the PYTHON number.

    A window that showed a budget the spawn does not use would be worse than
    showing none, so the expected bytes are read from `deep_commands` -- the
    table `bounded_output` really spends -- rather than from the JS copy the
    screen is being asked about.
    """
    bench.select_step("build")
    assert f"{OUTPUT_LIMIT_BYTES[SEEDED_PROFILE]} bytes" in bench.budget_line()

    other = next(word for word in OUTPUT_LIMIT_BYTES if word != SEEDED_PROFILE)
    bench.budget().select_option(other)
    bench.page.wait_for_function(
        "expected => document.querySelector('[data-context=\\'output-budget\\']')"
        ".innerText.includes(expected)", arg=f"{OUTPUT_LIMIT_BYTES[other]} bytes")
    assert other in bench.budget_line()
    assert bench.problems == []


# -- 3. it round-trips, and the other four arguments are untouched -------------


def test_choosing_a_profile_reaches_the_stored_draft_and_keeps_its_siblings(
        bench: _Bench, project: _Project) -> None:
    """The whole point of the slice, and the whole risk of it, in one test.

    The profile has to arrive in the durable draft -- so it is read back off
    the store and then off a reloaded page, never off the drawing this window
    is holding. And the four arguments nobody touched have to be there exactly
    as they were: an edit that rebuilt the map around its own key would save
    cleanly, and the loss would only appear as a run that will not open.

    The siblings are compared against what the STORE held before the edit, not
    against the literal seeded above, and the difference matters: the contract
    freezes a JSON array into a tuple on the way back out, so a comparison
    against the literal fails on a document nothing touched. Reading the
    baseline through the same door as the result asks the question that was
    meant -- did this edit change anything but the budget -- and asks it about
    the bytes that are really stored.
    """
    before = project.stored_arguments()
    assert before["output_limit_profile"] == SEEDED_PROFILE, before
    other = next(word for word in OUTPUT_LIMIT_BYTES if word != SEEDED_PROFILE)
    bench.select_step("build")
    bench.budget().select_option(other)
    _save_draft(bench.page)

    after = project.stored_arguments()
    assert after["output_limit_profile"] == other, after
    assert _without_budget(after) == _without_budget(before), after
    # And the comparison is not vacuous: there really are four other arguments
    # on this step, so "nothing else changed" is a claim about something.
    assert set(_without_budget(after)) == set(SIBLINGS), after

    bench.page.reload(wait_until="load")
    _settle(bench.page)
    _open_the_workflow(bench.page)
    bench.select_step("build")
    assert bench.budget().input_value() == other
    assert bench.problems == []


# -- 4. an immutable revision states it and refuses to be edited ---------------


def test_a_published_revision_shows_the_budget_and_disables_the_control(
        bench: _Bench) -> None:
    """The read-only half, which is the one a shrinking register loses first.

    A control disabled by being deleted would satisfy every "cannot be edited"
    assertion and tell a reader of a published revision nothing about the
    ceiling its step will be spawned under. Both are held: the value is on the
    screen, the bytes are beside it, and the control is shut.
    """
    page = bench.page
    _save_draft(page)
    _publish(page)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')

    bench.select_step("build")
    assert bench.budget().input_value() == SEEDED_PROFILE
    assert bench.budget().is_disabled(), (
        "a published revision is immutable and its controls say so by being shut")
    assert f"{OUTPUT_LIMIT_BYTES[SEEDED_PROFILE]} bytes" in bench.budget_line()
    assert bench.problems == []
