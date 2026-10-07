"""A gate that may not be set aside, on both screens that touch it.

The rule is held at three doors and only one of them is a screen. The server
refuses a waiver before anything is appended and the store refuses a journal
carrying one, and both of those are witnessed in Python where they belong. What
only a rendered test can hold is the pair of claims a PERSON meets:

- the drawing surface offers the demand where a gate is drawn, and writes it to
  the durable draft under the label the mandate names;
- the Decisions surface stops offering the answer that demand removes, and says
  why -- because a control that is offered and then refused on save teaches a
  person the product is broken, when the plan said this before the run opened.

The second is driven on a SEEDED run whose plan protects one gate and leaves
another waivable, so every assertion has its own control on the same screen: a
build that hid `waive` everywhere would satisfy the first half and fail the
second.
"""
from __future__ import annotations

import json
from typing import Iterator

import pytest
from playwright.sync_api import Browser, Page

from conductor.command.template_store import TemplateStore

from browser_tests.test_studio_lifecycle import (  # noqa: F401
    STUDIO_CONFIG,
    _Project,
    _open,
    _save_draft,
    _settle,
    project,
)

WORKFLOW_ID = "no-waive-bench"
SAVED_AT = "2026-09-02T10:00:00Z"
#: The run this module seeds. Its own id, so the shipped seed keeps its journal
#: and this one keeps its two gates -- one protected, one not.
GATED_RUN = "run-no-waive"
PROTECTED_GATE = "gate-protected"
WAIVABLE_GATE = "gate-waivable"
FIELD = '[data-edit-field="success_requires"]'
#: The label the mandate names, verbatim. A control a person cannot find by the
#: words they were told to look for is a control they do not have.
LABEL = "Require explicit human approval — waiver disabled"

DRAFT = {
    "schema_version": 1,
    "title": "No-waive bench",
    "nodes": [
        {"node_id": "gate", "kind": "gate", "title": "Human gate",
         "gate_id": PROTECTED_GATE, "resources": []},
        {"node_id": "after", "kind": "task", "title": "After the gate",
         "resources": []},
    ],
    "edges": [{"from_node": "gate", "to_node": "after"}],
}


def _stored(project: _Project) -> dict:
    draft = TemplateStore(project.root).load_draft(WORKFLOW_ID)
    assert draft is not None, "no draft is stored for this workflow"
    return next(row for row in draft.document["nodes"]
                if row["node_id"] == "gate")


def _open_the_workflow(page: Page) -> None:
    page.locator("#navWorkflow").click()
    page.locator("#workflowToolbar select[name='workflow']").select_option(
        WORKFLOW_ID)
    page.wait_for_selector('.studio-canvas__banner[data-document="draft"]')
    page.wait_for_function(
        "() => document.querySelectorAll('[data-node-id]').length === 2")
    page.wait_for_selector(
        '#workflowToolbar [data-focus="action:onSaveDraft"]:not([disabled])')


@pytest.fixture
def bench(chromium: Browser, project: _Project) -> Iterator[tuple]:
    from conductor.command.template_store import WorkflowDraft

    TemplateStore(project.root).save_draft(WorkflowDraft(
        workflow_id=WORKFLOW_ID, saved_at=SAVED_AT, document=DRAFT))
    _seed_gated_run(project.root)
    page, window = _open(chromium, project)
    try:
        yield page, window, project
    finally:
        page.context.close()


def _seed_gated_run(root) -> None:
    """One run, two gates: one protected, one not.

    Both on one plan and on one screen, so the Decisions witnesses below carry
    their own control -- a build that stopped offering `waive` at all would pass
    the protected half and fail the waivable one.
    """
    from conductor.command.graph_definition import (
        GraphDefinition,
        GraphEdge,
        GraphNode,
    )
    from conductor.command.run_store import RunStore, snapshot_digest
    from tests.test_command_run_store import a_run

    nodes = (
        GraphNode(node_id="protected", kind="gate", title="Protected gate",
                  gate_id=PROTECTED_GATE, success_requires="human_approval"),
        GraphNode(node_id="waivable", kind="gate", title="Waivable gate",
                  gate_id=WAIVABLE_GATE),
        GraphNode(node_id="work", kind="task", title="The work"),
    )
    edges = (GraphEdge(from_node="protected", to_node="work"),
             GraphEdge(from_node="waivable", to_node="work"))
    store = RunStore(root)
    store.create_run(
        a_run(run_id=GATED_RUN, mode="confirm",
              config_digest=snapshot_digest(STUDIO_CONFIG)), STUDIO_CONFIG)
    store.append(GraphDefinition(
        graph_id="graph-no-waive", run_id=GATED_RUN,
        created_at=SAVED_AT, nodes=nodes, edges=edges))


# -- 1. where a gate is drawn -------------------------------------------------


def test_the_demand_is_offered_on_a_gate_under_the_label_the_mandate_names(
        bench) -> None:
    """The control exists, is found by its own words, and is a gate's alone."""
    page, window, _project = bench
    _open_the_workflow(page)

    page.locator('[data-node-id="gate"]').click()
    page.wait_for_selector('[data-section="transitions"]')
    assert page.locator(FIELD).count() == 1
    labels = page.locator('[data-section="transitions"] label').evaluate_all(
        "rows => rows.map(row => row.innerText)")
    assert any(LABEL in text for text in labels), labels

    # And a step that is not a gate is offered none, because the contract
    # refuses one there and a control whose every use is refused is worse than
    # no control.
    page.locator('[data-node-id="after"]').click()
    page.wait_for_selector('[data-section="transitions"]')
    assert page.locator(FIELD).count() == 0
    assert window.problems == []


def test_the_demand_reaches_the_durable_draft_and_reads_back(bench) -> None:
    """Read off the STORE and then off a reloaded page, never off the drawing
    this window is holding."""
    page, window, project = bench
    _open_the_workflow(page)
    page.locator('[data-node-id="gate"]').click()
    page.wait_for_selector('[data-section="transitions"]')
    assert "success_requires" not in _stored(project)

    page.locator(FIELD).select_option("human_approval")
    _save_draft(page)

    assert _stored(project)["success_requires"] == "human_approval"
    page.reload(wait_until="load")
    _settle(page)
    _open_the_workflow(page)
    page.locator('[data-node-id="gate"]').click()
    page.wait_for_selector('[data-section="transitions"]')
    assert page.locator(FIELD).input_value() == "human_approval"
    assert window.problems == []


def test_the_control_offers_exactly_the_words_the_python_layer_carries(
        bench) -> None:
    """Read out of the module the PAGE loaded, against the Python owner, both
    directions: a third word would offer a plan the store refuses."""
    from conductor.command.graph_values import GATE_SUCCESS_DEMANDS

    page, _window, _project = bench
    _open_the_workflow(page)
    page.locator('[data-node-id="gate"]').click()
    page.wait_for_selector('[data-section="transitions"]')

    offered = page.locator(f"{FIELD} option").evaluate_all(
        "rows => rows.map(row => row.value)")

    assert offered[0] == "", offered
    assert set(offered) - {""} == set(GATE_SUCCESS_DEMANDS), offered


def test_the_control_says_what_the_demand_removes_and_what_it_leaves(
        bench) -> None:
    """The promise beside the control. A person choosing it is entitled to know
    which answer disappears and which ones stay -- and that this can only make
    the gate harder to pass."""
    page, _window, _project = bench
    _open_the_workflow(page)
    page.locator('[data-node-id="gate"]').click()
    page.wait_for_selector('[data-section="transitions"]')

    said = page.locator('[data-section="transitions"]').inner_text()

    assert "Waiving is the one answer that closes a gate without judging" in said
    assert "Rejecting and requesting changes stay available" in said
    assert "harder to pass, never harder to fail" in said
    assert "refused when it is read" in said


# -- 2. where a gate is answered ----------------------------------------------


def _open_the_gate(page: Page, gate_id: str) -> None:
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{GATED_RUN}"]').click()
    page.wait_for_selector("ol.studio-timeline")
    page.locator('[data-focus-key="action:showDecisions"]').click()
    page.wait_for_selector("#screenDecisions:not([hidden])")
    page.locator(f'[data-focus-key="decision:{GATED_RUN}/{gate_id}"]').click()
    page.wait_for_selector(".studio-decisions__detail")


def _choices(page: Page) -> list[str]:
    return page.locator(".studio-decide .studio-choice input").evaluate_all(
        "rows => rows.map(row => row.value)")


def test_a_protected_gate_is_not_offered_the_answer_it_refuses(bench) -> None:
    """WRITTEN RED. The screen stops offering `waive`, and says why.

    Offering it and refusing the save would teach a person the product is
    broken. The plan said this before the run opened, so the screen says it
    where the answer is chosen.
    """
    page, window, _project = bench
    _open_the_gate(page, PROTECTED_GATE)

    offered = _choices(page)
    said = page.locator(".studio-decisions__detail").inner_text()

    assert "waive" not in offered, offered
    assert "requires explicit human approval" in said, said
    assert "cannot be waived" in said, said
    assert window.problems == []


def test_the_answers_it_does_not_refuse_are_still_offered(bench) -> None:
    """This makes a gate harder to PASS, never harder to fail: the two answers
    that refuse the work stay, on the very same gate."""
    page, _window, _project = bench
    _open_the_gate(page, PROTECTED_GATE)

    offered = _choices(page)

    assert "approve" in offered, offered
    assert "reject" in offered, offered
    assert "request_changes" in offered, offered


def test_a_waivable_gate_on_the_same_run_still_offers_it(bench) -> None:
    """The discriminating control, on the same screen and the same journal: a
    build that hid `waive` everywhere would pass the witnesses above."""
    page, window, _project = bench
    _open_the_gate(page, WAIVABLE_GATE)

    offered = _choices(page)
    said = page.locator(".studio-decisions__detail").inner_text()

    assert "waive" in offered, offered
    assert "cannot be waived" not in said, said
    assert window.problems == []
