"""Routing, in a real browser: a condition drawn, and a plan word read.

The three register rows that became real in this slice all concern ONE idea --
a connection may now carry a condition, and what the plan permits follows from
it. Source guards hold that the controls exist and write the right edit word;
this module holds that a person can actually use them, and that what the window
then shows came from the server rather than from a walk of the edge list.

Four circuits, each a different question:

1. **the control offers what the step can produce.** A gate's roads offer the
   four gate words; a task carrying no capability is offered no condition at
   all, because the contract refuses one and a select whose every use is
   refused on save is worse than none.
2. **choosing one reaches the document.** The edit is `set-edge-condition`, it
   travels the ordinary draft road, and the saved revision carries the word --
   read back out of the durable tree, not off the screen.
3. **the edge panel and the section agree.** One control, exported once, so the
   two surfaces cannot offer different words for one road.
4. **the Runs screen states the plan word and never dresses it as success.**
   `complete` says the plan has nothing left to open; a run that exhausted its
   retries reaches the same word, so the chip is neutral and the facts that
   tell the two apart are beside it.

Its own module rather than more of ``test_studio_editing``: that one is near
the line cap and its subject is the drawing itself. The project fixture and the
page helpers stay in ``test_studio_lifecycle`` and are imported here, so one
seeded project is still described in one place.
"""
from __future__ import annotations

import json

from playwright.sync_api import Browser, Page

from conductor.command.template_store import TemplateStore

from browser_tests.test_studio_lifecycle import (  # noqa: F401
    CONFIRM_GATE,
    RUN_ID,
    STARTER_STEPS,
    STUDIO_CONFIG,
    _Project,
    _Window,
    _open,
    _publish,
    _save_draft,
    _settle,
    _start_from_starter,
    project,
)

WORKFLOW_ID = "routing-bench"
#: A second seeded run, on the ROUTED plan. Its own id, so the shipped
#: seed keeps its journal and this one keeps its unanswered gates.
ROUTED_RUN = "run-routed"
#: `studio-runs.PLAN_WORDS`, spelled here so this module asserts the SENTENCE a
#: person reads and not only the machine word beside it. `complete` is the one
#: that must never travel alone: a run that exhausted its retries reaches it too.
SENTENCES = {
    "open": "steps remain that this run may still take",
    "complete": "does NOT mean the run succeeded",
    "stalled": "nothing is runnable, no attempt is still running, and what is "
               "still owed can never be spent: a bound is exhausted or the run "
               "was halted",
}
#: The gate the shipped starter puts in front of its one effecting step, and
#: the step behind it. Named once so a starter that renames either moves one
#: line rather than six.
GATE = "confirm-gate"
DOING = "do"
#: Every task the shipped starter draws carries a capability, so a step that
#: produces NO word has to be added -- which the palette does, and which is
#: the only way this window can reach that case at all.


def _select_step(page: Page, node_id: str) -> None:
    page.locator(f'[data-node-id="{node_id}"]').click()
    page.wait_for_selector('[data-section="transitions"]')


def _condition_control(page: Page, from_id: str, to_id: str):
    return page.locator(f'[data-edge-condition="{from_id} {to_id}"]')


def _offered(page: Page, from_id: str, to_id: str) -> list[str]:
    """Every value the condition select offers for one road, in its own order."""
    return _condition_control(page, from_id, to_id).evaluate(
        "node => Array.from(node.options).map(row => row.value)")


def _stored_edges(project: _Project, workflow_id: str, revision: int):
    """The road list as the DURABLE tree holds it, never as the screen shows it."""
    template = TemplateStore(project.root).load(workflow_id, revision)
    return {(edge.from_node, edge.to_node): edge.condition
            for edge in template.settled()[1]}


def _open_the_seeded_run(page: Page) -> None:
    """The Runs screen, and the one run this project was seeded with."""
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
    page.wait_for_selector("ol.studio-timeline")
# -- 1. the control offers what the step behind the road can produce ----------


def test_a_gates_road_offers_the_four_words_a_gate_can_produce(
        chromium: Browser, project: _Project) -> None:
    """And `always`, which is what an unconditional road already is."""
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, WORKFLOW_ID)
        _select_step(page, GATE)

        offered = _offered(page, GATE, DOING)

        assert offered == ["", "on_approved", "on_rejected",
                           "on_changes_requested", "on_waived"]
        assert _condition_control(page, GATE, DOING).input_value() == ""
    finally:
        assert window.problems == []
        page.context.close()


def test_a_step_that_carries_out_no_work_is_offered_no_condition(
        chromium: Browser, project: _Project) -> None:
    """The contract refuses one on its roads, so the window offers none.

    Stated rather than silently missing: a control that is simply absent looks
    like a window that forgot, and a person has no way to learn why.

    The step is ADDED here, because the shipped starter has none: every task it
    draws carries a capability, both its gates produce gate words and its loop
    produces loop words. A fresh task is the only step in this product that
    produces nothing at all, which is exactly the case under test.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, WORKFLOW_ID)
        _select_step(page, "goal")
        page.locator('[data-focus="add-task"]').click()
        page.wait_for_function(
            "n => document.querySelectorAll('[data-node-id]').length === n",
            arg=STARTER_STEPS + 1)
        fresh = [row for row in window.node_ids() if row.startswith("step-")]
        assert len(fresh) == 1, fresh
        _select_step(page, fresh[0])
        # A step with no road out has no condition row to show, so one is drawn
        # first: what is under test is the road's control, not its absence.
        page.locator('[data-focus="connect-target"]').select_option(DOING)
        page.locator('[data-focus="connect-go"]').click()
        page.wait_for_selector(f'[data-edge="{fresh[0]} {DOING}"]')

        note = page.locator(
            '[data-section="transitions"] .studio-edge-row__note')

        assert note.count() >= 1
        assert note.first.inner_text().strip() == (
            "carries out no work — no condition")
        assert page.locator(
            '[data-section="transitions"] select[name="edge_condition"]'
        ).count() == 0
    finally:
        assert window.problems == []
        page.context.close()


# -- 2. choosing one reaches the durable document -----------------------------


def test_choosing_a_condition_reaches_the_saved_revision(
        chromium: Browser, project: _Project) -> None:
    """The whole road, and the last step is read out of the STORE.

    A window that showed the word and sent nothing would pass every source
    guard in this repository. This asks the durable tree what it holds.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, WORKFLOW_ID)
        _select_step(page, GATE)
        _condition_control(page, GATE, DOING).select_option("on_approved")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('#workflowToolbar [data-save="saved"]')

        stored = _stored_edges(project, WORKFLOW_ID, 1)

        assert stored[(GATE, DOING)] == "on_approved"
        # And ONLY that road moved: an edit names one connection.
        assert [pair for pair, word in stored.items() if word is not None] == [
            (GATE, DOING)]
    finally:
        assert window.problems == []
        page.context.close()


def test_clearing_it_again_removes_the_condition_from_the_document(
        chromium: Browser, project: _Project) -> None:
    """`always` is not a ninth word: it is the field being absent.

    A document that stored `"condition": null` would not be canonical, and the
    store would refuse the line it wrote.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, WORKFLOW_ID)
        _select_step(page, GATE)
        _condition_control(page, GATE, DOING).select_option("on_approved")
        _condition_control(page, GATE, DOING).select_option("")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('#workflowToolbar [data-save="saved"]')

        stored = _stored_edges(project, WORKFLOW_ID, 1)

        assert stored[(GATE, DOING)] is None
        assert all(word is None for word in stored.values())
    finally:
        assert window.problems == []
        page.context.close()


# -- 3. the edge panel offers the SAME control --------------------------------


def test_the_edge_panel_offers_the_same_words_and_writes_the_same_edit(
        chromium: Browser, project: _Project) -> None:
    """Selecting the ROAD rather than the step reaches one control, not two."""
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, WORKFLOW_ID)
        _select_step(page, GATE)
        page.locator(f'[data-focus="edge-select-{GATE} {DOING}"]').click()
        page.wait_for_selector('[data-panel="edge"]')

        panel = page.locator('[data-panel="edge"]')
        control = panel.locator(f'[data-edge-condition="{GATE} {DOING}"]')
        assert control.count() == 1
        assert control.evaluate(
            "node => Array.from(node.options).map(row => row.value)") == [
                "", "on_approved", "on_rejected", "on_changes_requested",
                "on_waived"]

        control.select_option("on_rejected")
        _save_draft(page)
        _publish(page)
        page.wait_for_selector('#workflowToolbar [data-save="saved"]')

        assert _stored_edges(project, WORKFLOW_ID, 1)[(GATE, DOING)] == (
            "on_rejected")
    finally:
        assert window.problems == []
        page.context.close()


def test_decision_routing_reads_back_the_road_that_was_just_drawn(
        chromium: Browser, project: _Project) -> None:
    """The derived reading, and it is a reading: it writes no edit.

    Before a condition is chosen the gate says every answer opens the same
    step, which is the truth about an unconditional road; afterwards it names
    the answer and where that answer goes.
    """
    page, window = _open(chromium, project)
    try:
        _start_from_starter(page, WORKFLOW_ID)
        _select_step(page, GATE)
        section = page.locator('[data-section="transitions"]')
        assert "every answer opens" in section.inner_text()

        _condition_control(page, GATE, DOING).select_option("on_approved")
        page.wait_for_selector(f'[data-route="on_approved {DOING}"]')

        assert page.locator(
            f'[data-route="on_approved {DOING}"]').inner_text().strip() == (
                f"approved → {DOING}")
    finally:
        assert window.problems == []
        page.context.close()


# -- 4. the Runs screen states the plan word, and never as a success ----------


def test_the_runs_screen_states_the_plan_word_without_dressing_it_as_success(
        chromium: Browser, project: _Project) -> None:
    """The seeded run follows a plan, so the Runs screen has a word to say.

    What is asserted is the CHANNEL as much as the word: a green tick against
    `complete` would tell somebody their run worked when all the product knows
    is that there is nothing left to do.
    """
    page, window = _open(chromium, project)
    try:
        _open_the_seeded_run(page)

        text = page.locator("#bodyRuns").inner_text()

        # The word, and the sentence that belongs to it -- so a screen showing
        # `complete` without its warning would red here as loudly as one
        # showing no word at all.
        chip = page.locator(".studio-fact .studio-chip").first
        # The chip's own word, past the glyph beside it -- and the glyph is the
        # neutral one, which is half of what this test is about.
        word = chip.locator("span").last.inner_text().strip()

        assert word in ("open", "complete", "stalled"), word
        assert chip.locator("i").inner_text().strip() == "·"
        assert SENTENCES[word] in text, text
        # And whatever the word is, it is never drawn on the success channel.
        assert "studio-chip--pass" not in (chip.get_attribute("class") or "")
    finally:
        assert window.problems == []
        page.context.close()


def test_a_step_waiting_at_a_join_is_told_that_ALL_roads_are_required(
        chromium: Browser, project: _Project) -> None:
    """AND-only, said in words a person reads rather than implied by a shape.

    "Waiting for a predecessor" reads as ANY, and a person told that would
    expect the step to start as soon as one branch arrived.
    """
    page, window = _open(chromium, project)
    try:
        _open_the_seeded_run(page)
        page.wait_for_selector(".studio-positions")

        text = page.inner_text(".studio-positions")

        assert "ALL incoming roads must open" in text
        assert "waiting for a predecessor" not in text.lower()
    finally:
        assert window.problems == []
        page.context.close()


# -- 5. the Decisions screen names what an answer really unblocks -------------
#
# The gap this closes was found by mutation, not by reading: `opensOf` could be
# gutted to `return []` with its call site intact and the WHOLE tree stayed
# green. Source guards held that the function is called and that it does not
# consult the edge list; nothing drove a real journal to the screen and read
# the answer off the row. So "What becomes runnable once this is answered" --
# the only place this product surfaces its one successor computation, and the
# whole of owner acceptance step 12 -- could silently become empty for every
# gate on every run.


def _seed_routed_run(root) -> None:
    """A second run on the ROUTED plan, with both its gates unanswered.

    The shipped seed follows `dalio-v2`, whose roads carry no condition -- and
    an implementation that fell back to walking the edge list would name the
    same successor for it, so it could not tell the two apart. This run follows
    the revision-3 shape, where `confirm-gate` opens `do` only `on_approved`:
    the word is carried by the SCHEDULE and by nothing else on the wire.
    """
    from conductor.command.graph_definition import GraphDefinition
    from conductor.command.run_store import RunStore, snapshot_digest
    from tests.schedule_journal import routed_dalio
    from tests.test_command_run_store import a_run

    drawn = routed_dalio()
    store = RunStore(root)
    store.create_run(
        a_run(run_id=ROUTED_RUN, mode="confirm",
              config_digest=snapshot_digest(STUDIO_CONFIG)), STUDIO_CONFIG)
    # The same drawing, bound to THIS run: a plan names the run it belongs to,
    # and the shared helper builds for the shipped seed's id.
    store.append(GraphDefinition(
        graph_id=drawn.graph_id, run_id=ROUTED_RUN,
        created_at=drawn.created_at, nodes=drawn.nodes, edges=drawn.edges))


def _open_the_routed_gate(page: Page) -> None:
    """Read the routed run, then open its unanswered gate.

    The Decisions screen answers about the run this window has READ -- a gate
    is a step of one run's plan, and there is no list of everybody's gates. So
    the run is opened first, exactly as a person reaches it.
    """
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{ROUTED_RUN}"]').click()
    page.wait_for_selector("ol.studio-timeline")
    page.locator("#navDecisions").click()
    page.wait_for_selector("#screenDecisions:not([hidden])")
    page.locator(
        f'[data-focus-key="decision:{ROUTED_RUN}/{CONFIRM_GATE}"]').click()
    page.wait_for_selector(
        "#screenDecisions .studio-unblocks, #screenDecisions .studio-note")


def test_the_decisions_screen_names_the_step_this_answer_unblocks(
        chromium: Browser, project: _Project) -> None:
    """The row NAMES the successor, and names the word it opens on.

    Both halves are read off `graph.schedule`: the title comes from the plan
    joined by `node_id`, and the condition exists nowhere else on the wire. An
    empty list here is not a smaller truth -- it is the section saying it does
    not know, which is what this witness exists to stop being silently true.
    """
    _seed_routed_run(project.root)
    page, window = _open(chromium, project)
    try:
        _open_the_routed_gate(page)

        listed = page.locator("#screenDecisions .studio-unblocks li")

        assert listed.count() == 1, listed.all_inner_texts()
        said = listed.first.inner_text()
        assert "do" in said, said
        assert "opens on on_approved" in said, said
        # And the fallback sentence is NOT what a person is reading.
        detail = page.locator("#screenDecisions").inner_text()
        assert "nothing here claims to know" not in detail, detail
    finally:
        assert window.problems == []
        page.context.close()


def test_a_build_that_answers_no_schedule_says_so_rather_than_nothing(
        chromium: Browser, project: _Project) -> None:
    """The honest fallback arm, driven by taking the key away.

    An older server answers a run read with no `schedule`. The window must then
    SAY it was not given the roads for this gate -- not draw an empty list,
    which reads as "this answer unblocks nothing" and is a different claim
    entirely. The key is stripped from the real response rather than a body
    being invented, so what is exercised is the production reader.
    """
    _seed_routed_run(project.root)
    page, window = _open(chromium, project)
    try:
        def without_the_schedule(route):
            answer = route.fetch()
            body = answer.json()
            if isinstance(body.get("graph"), dict):
                body["graph"]["schedule"] = None
            route.fulfill(status=answer.status, content_type="application/json",
                          body=json.dumps(body))

        page.route(f"**/command/runs/{ROUTED_RUN}", without_the_schedule)
        try:
            _open_the_routed_gate(page)

            detail = page.locator("#screenDecisions").inner_text()

            assert "nothing here claims to know" in detail, detail
            assert page.locator(
                "#screenDecisions .studio-unblocks li").count() == 0
        finally:
            page.unroute(f"**/command/runs/{ROUTED_RUN}")
    finally:
        assert window.problems == []
        page.context.close()
