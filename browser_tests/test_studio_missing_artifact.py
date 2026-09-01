"""What a step does about an input that is not there, in a real Chromium.

The fifth section of the artifact bench, split off when that module crossed the
project's line cap and along the seam the register itself drew: sections a--d
are about the artifact TRIO -- what a step requires, what it publishes, and who
hands it over -- and this is about what happens when one of those documents does
not exist. It shares the bench, so it is one description read twice rather than
a second seeded project.

Two words and no third, both fail-closed. `fail` is what this build has always
done and what saying nothing still means: the step is offered, reached, and
refused when the input will not resolve, with no task spawned. `block` is the
new one: the step is never offered while the document is absent.

WHAT ONLY A RENDERED TEST CAN HOLD HERE, and each of these is a defect that
passed every source guard at some point in this slice:

* **the control writes to the durable draft.** Read back off the STORE and then
  off a RELOADED page, never off the drawing this window is holding.
* **the vocabulary is the Python layer's.** Read out of the module the PAGE
  loaded, against `graph_values.MISSING_ARTIFACT_POLICIES`, in both directions.
* **the empty "Waiting on".** The Runs screen renders a blocked step's
  `blocked_by` under that label followed by the rule that ALL incoming roads
  must open. `blocked_by` carries PREDECESSORS, and until `block` shipped a step
  could not be blocked for any other reason -- so the branch was always true.
  A step waiting only for a document would have printed an empty "Waiting on"
  beside a sentence about roads: a true sentence about the wrong thing. Both a
  step waiting for BOTH reasons and a step waiting for only the document are
  driven, because only the second one shows it.
"""
from __future__ import annotations

from browser_tests.test_studio_artifacts import (  # noqa: F401
    AWAITED_REF,
    LONE_AWAITED_REF,
    LONE_WAITING_NODE,
    RUN_ID,
    WAITING_NODE,
    WORKFLOW_ID,
    _Bench,
    _open_the_workflow,
    _save_draft,
    _settle,
    bench,
    project,
)
from browser_tests.test_studio_artifacts import _Project
from conductor.command.template_store import TemplateStore



def _stored_node(project: _Project, node_id: str) -> dict:
    draft = TemplateStore(project.root).load_draft(WORKFLOW_ID)
    assert draft is not None, "no draft is stored for this workflow"
    return next(row for row in draft.document["nodes"]
                if row["node_id"] == node_id)


def test_the_missing_artifact_behaviour_is_chosen_stored_and_read_back(
        bench: _Bench, project: _Project) -> None:
    """The register's second-to-last label became a control that writes.

    Read back off the STORE and then off a reloaded page, never off the drawing
    this window is holding -- a control that only moved the draft in memory
    would satisfy every source guard and lose the answer on the next read.
    """
    bench.select_step("build")
    control = bench.page.locator(
        '[data-section="artifacts"] [data-edit-field="missing_artifact_policy"]')
    assert control.count() == 1
    assert "missing_artifact_policy" not in _stored_node(project, "build")

    control.select_option("block")
    _save_draft(bench.page)

    assert _stored_node(project, "build")["missing_artifact_policy"] == "block"
    bench.page.reload(wait_until="load")
    _settle(bench.page)
    _open_the_workflow(bench.page)
    bench.select_step("build")
    assert bench.page.locator(
        '[data-section="artifacts"] '
        '[data-edit-field="missing_artifact_policy"]').input_value() == "block"
    assert bench.problems == []


def test_the_control_offers_exactly_the_words_the_python_layer_carries(
        bench: _Bench) -> None:
    """Read out of the module the PAGE loaded, against the Python owner.

    A window offering a third word would offer a plan the store refuses; one
    offering a word Python dropped would hide a real change. Both directions.
    """
    from conductor.command.graph_values import MISSING_ARTIFACT_POLICIES

    bench.select_step("build")
    offered = bench.page.locator(
        '[data-section="artifacts"] '
        '[data-edit-field="missing_artifact_policy"] option').evaluate_all(
            "rows => rows.map(row => row.value)")

    # The empty option is "say nothing", which the contract reads as `fail`.
    assert offered[0] == ""
    assert set(offered) - {""} == set(MISSING_ARTIFACT_POLICIES), offered


def test_the_control_says_both_words_are_fail_closed_and_what_silence_means(
        bench: _Bench) -> None:
    """The promise beside the control, rendered rather than merely written.

    A person choosing between two words needs to be told that NEITHER of them
    skips the step, and that saying nothing is already one of them -- otherwise
    the default reads as "no behaviour" and every plan written before this
    field existed looks unexplained.
    """
    bench.select_step("build")
    said = bench.section()

    assert "Both answers are fail-closed" in said, said
    assert "nothing here skips the step" in said, said
    assert "no task is spawned" in said, said
    assert "never offered at all while the artifact is absent" in said, said
    assert "which is also what saying nothing means" in said, said


def test_a_step_that_is_given_no_documents_says_so_instead_of_offering_it(
        bench: _Bench) -> None:
    """The pairing rule, on screen, in the vocabulary a person drew in.

    The contract refuses a policy on a step nothing hands a document to, so a
    select whose every use would be refused on save is worse than no select --
    the reason is stated where the control would have been.
    """
    bench.select_step("approve")
    said = bench.section()

    assert bench.page.locator(
        '[data-section="artifacts"] '
        '[data-edit-field="missing_artifact_policy"]').count() == 0
    assert "this step is given no input artifacts" in said, said
    assert bench.problems == []


def test_clearing_the_role_takes_the_missing_artifact_behaviour_with_it(
        bench: _Bench, project: _Project) -> None:
    """A control a person did not touch may not make their draft unsavable.

    The pairing rule is the tightest of the four on this step, so a binding
    cleared to nothing strands the policy just as surely as it strands the
    verifier -- and the person would meet a refusal naming a field they never
    opened.
    """
    bench.select_step("build")
    bench.page.locator(
        '[data-section="artifacts"] '
        '[data-edit-field="missing_artifact_policy"]').select_option("block")
    _save_draft(bench.page)
    assert _stored_node(project, "build")["missing_artifact_policy"] == "block"

    role = bench.page.locator('[data-edit-field="role_id"]')
    role.fill("")
    role.press("Tab")
    # The control goes with the binding, on screen, before anything is saved.
    bench.page.wait_for_selector(
        '[data-section="artifacts"] '
        '[data-edit-field="missing_artifact_policy"]', state="detached")
    _save_draft(bench.page)

    stored = _stored_node(project, "build")
    assert "missing_artifact_policy" not in stored, stored
    assert "role_id" not in stored and "capability" not in stored, stored
    assert bench.problems == []


def test_an_open_run_names_the_document_the_waiting_step_is_waiting_for(
        bench: _Bench) -> None:
    """WRITTEN AGAINST A DEFECT THIS FIELD MADE REACHABLE.

    The Runs screen renders a blocked step's `blocked_by` under "Waiting on"
    followed by the rule that ALL incoming roads must open. `blocked_by`
    carries PREDECESSORS, and until `block` shipped a step could not be blocked
    for any other reason -- so the branch was always true. A step waiting for a
    document has a third reason, and the old render would have printed an empty
    "Waiting on" beside a sentence about roads: a true sentence about the wrong
    thing, sending a person to look for a step that does not exist.

    Both halves are asserted on ONE step, because `do` really is waiting for
    both: its gate is unanswered AND the document its plan requires was never
    published. Each is named, and neither is described as the other.
    """
    page = bench.page
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
    page.wait_for_selector("ol.studio-timeline")

    rows = page.locator("li.studio-position").evaluate_all(
        "items => items.map(item => item.innerText)")
    waiting = next(row for row in rows if f"{WAITING_NODE} · task" in row)

    assert "Waiting for artifact" in waiting, waiting
    assert AWAITED_REF in waiting, waiting
    assert "not offered until every artifact named here exists" in waiting
    # The road half is still said, and still says which step.
    assert "Waiting on" in waiting, waiting
    assert "confirm-gate" in waiting, waiting
    assert "ALL incoming roads must open" in waiting, waiting

    # And the step waiting for a document and for NOTHING ELSE is where the
    # defect really lived: no road reaches it, so `blocked_by` is empty, and
    # the old render printed "Waiting on" with nothing after it beside a rule
    # about roads. It says what it is waiting for and says nothing about roads.
    alone = next(row for row in rows
                 if f"{LONE_WAITING_NODE} · task" in row)
    assert "Waiting for artifact" in alone, alone
    assert LONE_AWAITED_REF in alone, alone
    assert "Waiting on" not in alone, alone
    assert "ALL incoming roads must open" not in alone, alone
    assert bench.problems == []


def test_a_step_that_is_not_waiting_is_told_nothing_about_waiting(
        bench: _Bench) -> None:
    """The other direction, on the inspector's run half.

    The line is drawn off the schedule row and only when that row carries
    something, so a step with nothing to wait for gets no sentence at all -- a
    line saying "waiting for nothing" is a line about nothing, and a screen
    that printed one for every step would teach a person to stop reading it.

    The waiting step itself cannot be selected here: this bench's DRAFT and the
    seeded RUN are two different documents, and `do` belongs to the run's plan.
    What the inspector renders for a waiting step is held by the source guard
    in tests/test_studio_completeness.py, and the rendered proof of the wait
    lives on the Runs screen above, which reads the same row.
    """
    page = bench.page
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
    page.wait_for_selector("ol.studio-timeline")
    _open_the_workflow(page)

    bench.select_step("build")
    assert "Waiting for" not in bench.section(), bench.section()
