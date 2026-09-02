"""The artifact trio in a real Chromium: required, produced, and who hands it over.

Three inspector fields said "not supported by this harness" while every fact
behind them was already durable, already validated, already materialized into a
run's plan and already replay-guarded -- as the capability's own reviewed
ARGUMENTS. ``artifact_refs`` and ``target_artifact_refs`` are what
``artifact_handoff.resolve`` spends and what a step is refused for lacking;
``result_artifact_ref`` is where a step's own output is published. This module
drives the controls that close that, against the real loopback server and the
real ``TemplateStore``.

FOUR THINGS ARE HELD HERE THAT SOURCE TEXT CANNOT HOLD:

* **The control is drawn for the field the SCHEMA marks, not for a field this
  window names.** The rendered control's ``data-edit-field`` is compared against
  ``CAPABILITY_FIELDS`` read out of the module the PAGE loaded. A section that
  had grown its own idea of which argument carries artifacts passes every
  literal-free source guard and reds here the moment the projection moves.
* **Every other argument survives an edit.** A dispatch payload carries four
  more fields. An edit that rebuilt the map around its own key would delete them
  into a draft that saves, and the loss would surface later as a run that will
  not open. The siblings are compared against what the STORE held before the
  edit -- never against the literal seeded here, because the contract freezes a
  JSON array into a TUPLE on the way back out and a comparison against the
  literal fails on a document nothing touched.
* **The handoff mapping is a real join over the document.** Both arms are driven
  on ONE document: a reference some step produces, and a reference none does.
  The second is not a hypothetical -- it is the shipped starters' own shape, and
  a mapping that could only say "produced by X" would be silent about exactly
  the case a person needs told.
* **A run's artifacts reach the step that produced them.** That join needs two
  records -- an artifact names its source ACTION, a request names its NODE --
  so it is driven off a seeded journal that carries both.

WHAT IS NOT ASSERTED, and why the obvious version would be false: there is no
witness that the draft route refuses a malformed reference, because it does not.
``TemplateNode._settle_arguments`` asks for JSON and for a role to read it and
judges no capability schema at all -- the schema is enforced at run open, by
``http_api._servable_pair``. So the guard against a bad reference is that the
control refuses to WRITE one, which is asserted directly: the store is read
after the attempt and is unchanged.
"""
from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.artifacts import ArtifactDocument
from conductor.command.graph_definition import GraphNode
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import WorkflowDraft

from browser_tests.test_studio_editing import _Recorder, _watch
from browser_tests.test_studio_lifecycle import _publish, _save_draft, _settle
from tests.alpha3_graph_artifacts import dalio_definition, dalio_nodes
from tests.test_command_graph_projection import a_proposal, a_request, an_event
from tests.test_command_run_store import a_run
from tests.test_store import good_lane, write_project

WORKFLOW_ID = "artifact-bench"
SAVED_AT = "2026-08-21T10:00:00Z"
NOW = "2026-08-19T09:00:00Z"
#: The seeded run, and the step of it whose artifact the runtime half must find.
#: Both names are the frozen ALPHA-3 definition's own, because that is the
#: document the run really froze.
RUN_ID = "run-001"
PRODUCING_NODE = "goal"
#: The step this run's plan tells to WAIT, and the document it waits
#: for. Nothing in the seeded journal publishes `artifact-plan`, which
#: is what makes the wait real rather than described.
WAITING_NODE = "do"
AWAITED_REF = "artifact-plan"
#: And a step waiting for a document and for nothing else: no road
#: reaches it, so its row is the one that shows what a screen says when
#: the ONLY reason is the document.
LONE_WAITING_NODE = "cross-check"
LONE_AWAITED_REF = "artifact-audit"
#: The reference the first step of the cycle is GIVEN, which nothing in the
#: document produces -- the shipped starters' own external input.
EXTERNAL_REF = "artifact-brief"
#: What the first step publishes and the second requires: the one reference
#: this module's mapping arm is really about.
HANDOFF_REF = "artifact-goal"
PRODUCED_ID = "artifact-goal-1"
#: The four arguments on the acting step that are NOT its artifact list. They
#: are what an edit to that list must leave alone, named once, compared whole.
SIBLINGS = {
    "work_item_id": "wi-001",
    "instruction_ref": "instructions-v1",
    "profile": "implement",
    "output_limit_profile": "normal",
}
DRAFT = {
    "schema_version": 1,
    "title": "Artifact bench",
    "nodes": [
        {"node_id": PRODUCING_NODE, "kind": "task", "title": "Settle the goal",
         "role_id": "thinker", "capability": "review", "resources": [],
         "arguments": {"work_item_id": "wi-001",
                       "target_artifact_refs": [EXTERNAL_REF],
                       "result_artifact_ref": HANDOFF_REF,
                       "review_profile": "quality"}},
        {"node_id": "identify", "kind": "task", "title": "Identify problems",
         "role_id": "thinker", "capability": "review", "resources": [],
         "arguments": {"work_item_id": "wi-001",
                       "target_artifact_refs": [HANDOFF_REF],
                       "result_artifact_ref": "artifact-problems",
                       "review_profile": "quality"}},
        {"node_id": "approve", "kind": "gate", "title": "Approve the work",
         "gate_id": "gate-approve", "resources": []},
        {"node_id": "build", "kind": "task", "title": "Carry it out",
         "role_id": "builder", "capability": "dispatch", "resources": [],
         "arguments": {**SIBLINGS, "artifact_refs": ["artifact-problems"]}},
    ],
    "edges": [
        {"from_node": PRODUCING_NODE, "to_node": "identify"},
        {"from_node": "identify", "to_node": "approve"},
        {"from_node": "approve", "to_node": "build"},
    ],
}
INPUT_LIST = '[data-context="required-input-artifacts"]'
RESULT_FIELD = '[data-edit-field="result_artifact_ref"]'
RESULT_LINE = '[data-context="produced-artifacts"]'
HANDOFF_LINE = '[data-context="handoff-mapping"]'
PRODUCED_LINE = '[data-context="produced-in-this-run"]'


def _run_definition():
    """The frozen ALPHA-3 plan, with ONE node taught to publish its output.

    The frozen artifact is revision-1 shaped: its review nodes carry no
    ``result_artifact_ref``, because the field did not exist when those bytes
    were written and they are a historical witness that may not move. The store
    refuses an artifact whose reference is not the one its source action asked
    for, so a journal carrying a produced document needs a plan whose acting
    node asked for it.

    So the node is COPIED through the production contract with one argument
    added, and every other field is carried across by name -- the house rule
    for a snapshot: a `GraphNode` rebuilt from a partial reading is a different
    node wearing the same id.
    """
    nodes = [_publishing(node) if node.node_id == PRODUCING_NODE
             else _waiting(node) if node.node_id == WAITING_NODE
             else node
             for node in dalio_nodes()]
    nodes.append(_lone_waiter(nodes[0].instance_id))
    return dalio_definition(run_id=RUN_ID, nodes=tuple(nodes))



def _copy(node, **changes):
    """One node through the production contract, every field carried by name.

    The house rule for a snapshot: a `GraphNode` rebuilt from a partial reading
    is a different node wearing the same id. `payload()` rather than
    `arguments`, because the contract freezes the map and sees a replacement by
    identity.
    """
    values = dict(
        node_id=node.node_id, kind=node.kind, title=node.title,
        stage=node.stage, instance_id=node.instance_id,
        capability=node.capability, arguments=node.payload(),
        resources=node.resources, gate_id=node.gate_id, loop=node.loop,
        timeout_seconds=node.timeout_seconds,
        attempt_bound=node.attempt_bound, purpose=node.purpose,
        verifier_instance_id=node.verifier_instance_id)
    values.update(changes)
    return GraphNode(**values)


def _publishing(node):
    """The one node taught to publish its output, so the seed can carry one."""
    return _copy(node, arguments={**node.payload(),
                                  "result_artifact_ref": HANDOFF_REF})


def _waiting(node):
    """The step told to WAIT, which is also behind an unanswered gate.

    It requires `artifact-plan`, which this run's journal never publishes, so
    its row carries both reasons a step can be held back at once.
    """
    return _copy(node, missing_artifact_policy="block")


def _lone_waiter(instance_id):
    """A step waiting for a document and for NOTHING else.

    No road reaches it, which a review may do -- it is offerable the moment its
    document exists. `do` cannot show what a screen says when only the document
    is missing, because its gate is unanswered too, and the empty "Waiting on"
    this field made reachable is exactly that case.
    """
    return GraphNode(
        node_id=LONE_WAITING_NODE, kind="task", title="Cross-check",
        instance_id=instance_id, capability="review",
        arguments={"work_item_id": "wi-001",
                   "target_artifact_refs": [LONE_AWAITED_REF],
                   "result_artifact_ref": "artifact-crosscheck",
                   "review_profile": "quality"},
        missing_artifact_policy="block")


def _seed_run(root: Path) -> None:
    """A journal carrying both halves of the join the runtime section makes.

    An `ArtifactDocument` names its source ACTION; an `ActionRequest` names the
    step that action was bound to. So the seed is a whole chain rather than an
    artifact dropped beside a plan -- and it has to be, because the store
    refuses each link on the way in: the source action must be known, it must
    be OBSERVED, it must be a reviewing action, its result reference must be
    the one the document carries, and the document's inputs must be exactly
    what that request's own references resolve to, in order.

    No verification and no result: an artifact standing without them is an
    honest crash prefix and replays, which keeps this seed to the two records
    the join actually needs.
    """
    definition = _run_definition()
    config = {"cycle": {"id": "default-orbit"},
              "instances": [{"id": "claude-dev", "adapter": "claude-code"}]}
    store = RunStore(root)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(config)), config)
    store.append(definition)
    node = next(row for row in definition.nodes
                if row.node_id == PRODUCING_NODE)
    proposal = a_proposal(node_id=PRODUCING_NODE, index=1,
                          arguments=node.arguments,
                          instance_id=node.instance_id,
                          capability=node.capability,
                          config_digest=snapshot_digest(config))
    store.append(proposal)
    request = a_request(proposal, index=1)
    store.append(request)
    store.append(an_event(request, "effect_lease", index=1))
    store.append(an_event(request, "execution_observed", index=1,
                          outcome="succeeded", exit_code=0))
    given = ArtifactDocument(
        artifact_id="artifact-brief-1", artifact_ref=EXTERNAL_REF,
        run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
        content="# Brief\n\nWhat this cycle is for.")
    store.append(given)
    store.append(ArtifactDocument(
        artifact_id=PRODUCED_ID, artifact_ref=HANDOFF_REF, run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown",
        content="# Goal\n\nThe settled goal of the cycle.",
        source_action_id=request.action_id,
        input_artifact_ids=(given.artifact_id,)))


class _Project:
    def __init__(self, url: str, root: Path) -> None:
        self.url = url
        self.root = root

    def stored_arguments(self, node_id: str) -> dict:
        """One step's arguments, off the draft the SERVER holds."""
        draft = TemplateStore(self.root).load_draft(WORKFLOW_ID)
        assert draft is not None, "no draft is stored for this workflow"
        node = next(row for row in draft.document["nodes"]
                    if row["node_id"] == node_id)
        return node["arguments"]


@pytest.fixture
def project(tmp_path) -> Iterator[_Project]:
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    TemplateStore(root).save_draft(WorkflowDraft(
        workflow_id=WORKFLOW_ID, saved_at=SAVED_AT, document=DRAFT))
    _seed_run(root)
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
        "() => document.querySelectorAll('[data-node-id]').length === 4")
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')


def _marked_field(page: Page, capability: str, kind: str) -> str | None:
    """Which argument the PAGE's own projection marks with one artifact kind.

    Read out of the module the page really loaded, so the comparisons below are
    relations rather than restatements of a list kept beside the test: move the
    projection and the control has to move with it or this reds.
    """
    return page.evaluate(
        """([capability, kind]) => import("/panel/command-projection.js")
             .then(module => {
               const row = module.CAPABILITY_FIELDS[capability].find(
                 (entry) => entry[1] === kind);
               return row === undefined ? null : row[0];
             })""",
        [capability, kind])


class _Bench:
    def __init__(self, page: Page, problems: list[str],
                 recorder: _Recorder) -> None:
        self.page = page
        self.problems = problems
        self.recorder = recorder

    def select_step(self, node_id: str) -> None:
        self.page.locator(f'[data-node-id="{node_id}"]').click()
        self.page.wait_for_selector('[data-section="artifacts"]')

    def section(self) -> str:
        return self.page.locator('[data-section="artifacts"]').inner_text()

    def refs(self) -> list[str]:
        return self.page.locator(
            '[data-section="artifacts"] .studio-ref').evaluate_all(
                "rows => rows.map(row => row.dataset.ref)")

    def require(self, ref: str) -> None:
        self.page.locator('[data-focus="ref-name"]').fill(ref)
        self.page.locator('[data-focus="ref-add"]').click()

    def handoffs(self) -> dict[str, str]:
        return self.page.locator(
            '[data-section="artifacts"] .studio-handoff').evaluate_all(
                "rows => Object.fromEntries(rows.map("
                "row => [row.dataset.handoff, row.innerText]))")


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


# -- a. a required reference round-trips, and its siblings survive -------------


def test_requiring_an_artifact_reaches_the_stored_draft_and_keeps_its_siblings(
        bench: _Bench, project: _Project) -> None:
    """The whole point of the slice, and the whole risk of it, in one test.

    The reference has to arrive in the durable draft -- read back off the store
    and then off a RELOADED page, never off the drawing this window is holding.
    And the four arguments nobody touched have to be there exactly as they
    were: an edit that rebuilt the map around its own key would save cleanly,
    and the loss would only appear as a run that will not open.

    The baseline is read through the same door as the result, because the
    contract freezes a JSON array into a tuple on the way back out -- a
    comparison against the seeded literal fails on a document nothing touched.
    """
    bench.select_step("build")
    marked = _marked_field(bench.page, "dispatch", "artifact-ids")
    # The RELATION FIRST, and it is why this reads the page's own projection:
    # the control announces which argument it writes, and that must be the one
    # the reviewed schema marks. A section that had grown its own idea of it
    # renders identically and satisfies every literal-free source guard, so
    # this is the assertion that has to fail first and say so -- the pin below
    # is a change detector on the projection, and reporting it first would
    # describe a disagreement as a rename.
    assert bench.page.locator('[data-focus="ref-name"]').get_attribute(
        "data-edit-field") == marked, (
        "the control writes an argument the reviewed schema does not mark as "
        "carrying artifact references")
    assert marked == "artifact_refs", marked
    before = project.stored_arguments("build")
    assert list(before[marked]) == ["artifact-problems"], before
    assert bench.refs() == ["artifact-problems"]
    bench.require("artifact-notes")
    _save_draft(bench.page)

    after = project.stored_arguments("build")
    assert list(after[marked]) == ["artifact-problems", "artifact-notes"]
    assert {name: value for name, value in after.items() if name != marked} == {
        name: value for name, value in before.items() if name != marked}
    # And the comparison is not vacuous: there really are four other arguments
    # on this step, so "nothing else changed" is a claim about something.
    assert set(after) - {marked} == set(SIBLINGS), after

    bench.page.reload(wait_until="load")
    _settle(bench.page)
    _open_the_workflow(bench.page)
    bench.select_step("build")
    assert bench.refs() == ["artifact-problems", "artifact-notes"]
    assert bench.problems == []


def test_a_reference_the_grammar_refuses_never_reaches_the_stored_draft(
        bench: _Bench, project: _Project) -> None:
    """The control refuses, and it says so instead of posting a body.

    Two refusals and each is one this window can honestly make: the id grammar,
    and the duplicate `latest_artifacts` resolves through `_unique_ids`. The
    store is read after each attempt, because "the screen did not change" and
    "nothing was written" are two claims.
    """
    before = project.stored_arguments("build")
    bench.select_step("build")

    bench.require("not a valid id")
    assert "must match" in bench.page.locator("#studioStatus").inner_text()
    assert bench.refs() == ["artifact-problems"]

    bench.require("artifact-problems")
    said = bench.page.locator("#studioStatus").inner_text()
    assert "already requires" in said, said
    assert bench.refs() == ["artifact-problems"]

    _save_draft(bench.page)
    assert project.stored_arguments("build") == before
    assert bench.problems == []


def test_a_required_reference_can_be_taken_off_again(
        bench: _Bench, project: _Project) -> None:
    """Requiring must not be a one-way door, and the empty list is a real state.

    A dispatching step's schema ADMITS an empty list, which is why the removal
    leaves an empty list rather than dropping the key: an absent field and an
    empty one are different answers, and only one of them is what this document
    says. The KEY is what is asserted first, for that reason.

    The value is read through `list(...)`, and that is the tuple trap
    `test_studio_budget` names: the contract freezes a JSON array into a TUPLE
    on the way back out, so `== []` compares an empty tuple against an empty
    list and fails on a document that is exactly right.
    """
    bench.select_step("build")
    bench.page.locator('[data-focus="ref-drop-0"]').click()
    bench.page.wait_for_function(
        "() => document.querySelectorAll("
        "'[data-section=\\'artifacts\\'] .studio-ref').length === 0")
    _save_draft(bench.page)

    after = project.stored_arguments("build")
    assert "artifact_refs" in after, after
    assert list(after["artifact_refs"]) == []
    assert set(after) - {"artifact_refs"} == set(SIBLINGS), after
    assert bench.problems == []


# -- b. what a step publishes, and what clearing it costs ----------------------


def test_the_result_reference_is_editable_where_the_schema_declares_one(
        bench: _Bench) -> None:
    """Drawn for the field the schema marks, and only for the capability that
    publishes at all.

    A step that carries work out publishes no document -- its evidence is a
    digest of the change it made -- so the control must not appear on one, and
    the section says what stands in its place instead of leaving a gap.
    """
    marked = _marked_field(bench.page, "review", "artifact-id")
    assert marked == "result_artifact_ref", marked

    bench.select_step(PRODUCING_NODE)
    assert bench.page.locator(RESULT_FIELD).input_value() == HANDOFF_REF
    assert HANDOFF_REF in bench.page.locator(RESULT_LINE).inner_text()

    bench.select_step("build")
    assert bench.page.locator(RESULT_FIELD).count() == 0
    line = bench.page.locator(RESULT_LINE).inner_text()
    assert "declares no result artifact reference" in line, line
    assert "digests" in bench.section()
    assert bench.problems == []


def test_clearing_the_result_reference_is_allowed_and_its_cost_is_stated(
        bench: _Bench, project: _Project) -> None:
    """The clearing road, which is the one a person meets a refusal on later.

    Emptying it writes a document that saves and that no longer names where
    this step's output goes -- and the run refuses such a step without spawning
    anything. So the cost is asserted to be ON SCREEN beside the control, not
    only met at a run: this is the one field whose honest answer costs
    something the window is obliged to say out loud.
    """
    bench.select_step(PRODUCING_NODE)
    assert "no task is spawned" in bench.section()

    bench.page.locator(RESULT_FIELD).fill("")
    bench.page.locator(RESULT_FIELD).press("Tab")
    _save_draft(bench.page)

    stored = project.stored_arguments(PRODUCING_NODE)
    assert "result_artifact_ref" not in stored, stored
    assert set(stored) == {"work_item_id", "target_artifact_refs",
                           "review_profile"}, stored
    bench.select_step(PRODUCING_NODE)
    assert "names no result artifact" in bench.page.locator(
        RESULT_LINE).inner_text()
    assert bench.problems == []


# -- c. where each requirement is met, both arms on one document ---------------


def test_the_handoff_mapping_names_the_producer_or_says_nobody_produces_it(
        bench: _Bench) -> None:
    """Both arms, driven on ONE document, because both are real here.

    `identify` requires what `goal` publishes, so the mapping names that step
    by its TITLE -- a person reading a workflow thinks in titles, and the id is
    beside it on the canvas. `goal` requires `artifact-brief`, which no step in
    this document produces: that is not a defect and not a hypothetical, it is
    the shape every shipped starter really has, so the mapping says where such
    a reference has to come from instead of leaving the line blank.
    """
    bench.select_step("identify")
    met = bench.handoffs()
    assert list(met) == [HANDOFF_REF], met
    assert "Settle the goal" in met[HANDOFF_REF], met
    assert "1 of 1 met" in bench.page.locator(HANDOFF_LINE).inner_text()

    bench.select_step(PRODUCING_NODE)
    unmet = bench.handoffs()
    assert list(unmet) == [EXTERNAL_REF], unmet
    assert "no step in this workflow produces it" in unmet[EXTERNAL_REF]
    assert "artifacts route" in unmet[EXTERNAL_REF]
    assert "0 of 1 met" in bench.page.locator(HANDOFF_LINE).inner_text()
    assert bench.problems == []


def test_the_handoff_mapping_follows_the_document_as_it_is_edited(
        bench: _Bench) -> None:
    """Derived, so it moves when the document does -- with no save in between.

    The mapping is computed on every render out of the steps on screen. Taking
    the producer's result reference away must turn its consumer's line from a
    named producer into the external-input sentence, immediately: a mapping
    that only refreshed on reload would tell a person the handoff still stands
    while they were removing it.
    """
    bench.select_step("identify")
    assert "Settle the goal" in bench.handoffs()[HANDOFF_REF]

    bench.select_step(PRODUCING_NODE)
    bench.page.locator(RESULT_FIELD).fill("")
    bench.page.locator(RESULT_FIELD).press("Tab")

    bench.select_step("identify")
    assert "no step in this workflow produces it" in bench.handoffs()[
        HANDOFF_REF]
    assert "0 of 1 met" in bench.page.locator(HANDOFF_LINE).inner_text()
    assert bench.problems == []


# -- d. a published revision states all three and refuses to be edited ---------


def test_a_published_revision_shows_the_trio_and_shuts_every_control(
        bench: _Bench) -> None:
    """The read-only half, which is the one a shrinking register loses first.

    A control disabled by being deleted satisfies every "cannot be edited"
    assertion and tells a reader of a published revision nothing about what
    that step needs or leaves. So all three are asserted PRESENT and shut: the
    references are listed, the result reference carries its value, the mapping
    still names the producer, and the two writers are disabled.
    """
    page = bench.page
    _save_draft(page)
    _publish(page)
    page.wait_for_selector('.studio-canvas__banner[data-document="published"]')

    bench.select_step(PRODUCING_NODE)
    assert bench.refs() == [EXTERNAL_REF]
    assert page.locator(RESULT_FIELD).input_value() == HANDOFF_REF
    assert page.locator(RESULT_FIELD).is_disabled(), (
        "a published revision is immutable and its controls say so by being shut")
    assert page.locator('[data-focus="ref-add"]').is_disabled()
    assert page.locator('[data-focus="ref-name"]').is_disabled()
    assert page.locator('[data-focus="ref-drop-0"]').is_disabled()
    # The derived half is not a control and stays readable.
    assert "no step in this workflow produces it" in bench.handoffs()[
        EXTERNAL_REF]
    bench.select_step("identify")
    assert "Settle the goal" in bench.handoffs()[HANDOFF_REF]
    assert bench.problems == []


# -- e. the runtime half: what THIS step's actions really produced -------------


def test_a_runs_artifact_is_shown_under_the_step_whose_action_produced_it(
        bench: _Bench) -> None:
    """The two-hop join, driven off a real journal through a real read.

    The seeded run's `goal` step produced one artifact; no other step produced
    anything. Both arms are asserted, because a build that ignored the join
    would show a run's every artifact under every step -- which looks correct
    on the step that really produced one.

    The CONTENT is not on screen and that is deliberate: an artifact is durable
    material a run hands between roles, and this window says what exists. The
    seeded document's own words are asserted absent.
    """
    page = bench.page
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
    page.wait_for_selector("ol.studio-timeline")
    _open_the_workflow(page)

    bench.select_step(PRODUCING_NODE)
    shown = page.locator(PRODUCED_LINE).inner_text()
    assert HANDOFF_REF in shown, shown
    assert page.locator(
        f'[data-section="artifacts"] [data-artifact="{PRODUCED_ID}"]').count() == 1
    listed = page.locator(
        f'[data-section="artifacts"] [data-artifact="{PRODUCED_ID}"]').inner_text()
    assert "text/markdown" in listed, listed
    assert "The settled goal of the cycle" not in bench.section()

    # A step of the same run that produced nothing says so, rather than
    # borrowing its neighbour's artifact.
    bench.select_step("identify")
    assert "was published by an action of this step" in page.locator(
        PRODUCED_LINE).inner_text()
    assert page.locator(
        '[data-section="artifacts"] [data-artifact]').count() == 0
    assert bench.problems == []
