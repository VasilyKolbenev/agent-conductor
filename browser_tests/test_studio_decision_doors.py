"""The Decisions screen against a plan that has not reached its gate.

Two rendered witnesses, both about the same rule the server now holds: a
decision stands only on a gate this run's plan has ARRIVED at, or as a
supersede of the receipt already standing there.

- **a gate the run has not reached offers nothing.** No submit control at all,
  and the AND-join sentence naming the steps still in front of it. A form
  offered there is a control whose only possible outcome is a refusal, which
  is the thing this screen exists not to do. Then the steps are carried out
  and the same gate offers the form.
- **the loop, answered three times from the screen.** Acceptance step 13's
  second pass, which could not be driven from this window at all: the receipt
  it posted always said `supersedes: null`, so the second answer left two
  unsuperseded receipts on one gate and the projection called it `unknown` --
  and the id it minted was spelled from the gate and the person alone, so the
  second answer collided with the first and was refused as a conflict before
  it ever got that far. Both halves are read off the POSTED BODIES and off the
  rendered text, never off pixels.

The plan is `schedule_journal.routed_dalio` -- the revision-3 drawing, whose
`result-gate -> retry-loop` road opens only `on_changes_requested`. The
conditions are what make the loop reopen, and the shipped `dalio-v2` seed the
other Studio modules use carries none.

Like every module here it lives outside pytest's configured ``testpaths``:
Playwright stays an explicit development/CI dependency.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.adapters.base import AdapterRegistry
from conductor.command.contracts import DecisionReceipt
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
)
from conductor.command.run_closing import close_if_terminal
from conductor.command.run_store import RunStore, snapshot_digest

from browser_tests.test_studio_lifecycle import (
    DECIDER,
    STUDIO_CONFIG,
    TOKEN,
    _Project,
    _settle,
    _Window,
)
from tests.schedule_journal import routed_dalio
from tests.test_command_graph_projection import settle_node  # noqa: F401
from tests.test_command_run_store import a_run
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_store import good_lane, write_project

GATED_RUN = "run-decision-doors"
#: A second run, and the only one that has ENDED. Kept apart from the first
#: because "this run is over" is true of every gate at once, and a run carrying
#: both states could not say which sentence belonged to which fact.
STALLED_RUN = "run-decision-stalled"
CONFIRM_GATE = "gate-confirm-do"
RESULT_GATE = "gate-result"
DIGEST = snapshot_digest(STUDIO_CONFIG)
NOW = "2026-08-30T10:00:00Z"
#: The ports this module may bind, and no others. A fixed window rather than
#: port 0, so a stray server left by a killed run is visible as a refusal to
#: start rather than as a second listener nobody can name.
PORTS = range(7940, 7950)
#: The steps the loop reopens, in the order the plan draws them. `goal` is
#: outside the body -- the loop goes back to `identify` -- so it is carried out
#: once and never again.
BODY = ("identify", "diagnose", "design")


def _seed(root: Path) -> None:
    """One run following the ROUTED plan, with nothing done against it yet."""
    drawn = routed_dalio()
    store = RunStore(root)
    store.create_run(
        a_run(run_id=GATED_RUN, mode="confirm", config_digest=DIGEST),
        STUDIO_CONFIG)
    # The same drawing bound to THIS run: a plan names the run it belongs to,
    # and the shared helper builds for the schedule module's own id.
    store.append(GraphDefinition(
        graph_id=drawn.graph_id, run_id=GATED_RUN,
        created_at=drawn.created_at, nodes=drawn.nodes, edges=drawn.edges))
    _seed_a_stalled_run(root)


def _seed_a_stalled_run(root: Path) -> None:
    """A second run that has ENDED: its one step spent the bound it was given.

    A gate, one effecting step behind it allowed a single attempt, that attempt
    authorized and answered `failed` -- so nothing is runnable, nothing is in
    flight, nothing waits for a document, and the step can never settle again.
    The plan's word is `stalled` and `close_if_terminal` records it, exactly as
    it does on the road a person takes.
    """
    drawn = routed_dalio()
    doing = next(row for row in drawn.nodes if row.node_id == "do")
    store = RunStore(root)
    store.create_run(
        a_run(run_id=STALLED_RUN, mode="confirm", config_digest=DIGEST),
        STUDIO_CONFIG)
    store.append(GraphDefinition(
        graph_id="graph-stalled", run_id=STALLED_RUN, created_at=NOW,
        nodes=(GraphNode(node_id="confirm-gate", kind="gate",
                         title="Human Gate", gate_id=CONFIRM_GATE),
               GraphNode.from_dict({**doing.as_dict(), "attempt_bound": 1})),
        edges=(GraphEdge(from_node="confirm-gate", to_node="do",
                         condition="on_approved"),)))
    _decide(store, run_id=STALLED_RUN, gate_id=CONFIRM_GATE,
            receipt_id="decision-stalled", action="approve")
    # `unknown` is the one terminal outcome that settles NOTHING: the attempt
    # is over and the journal supports no answer about it. With the bound spent
    # the step can never settle, which is what `stalled` means and what an
    # ordinary failure would not have produced -- a failed step settles, and
    # the plan would then be `complete`.
    settle_node(store, "do", index=1, run_id=STALLED_RUN, config_digest=DIGEST,
                outcome="unknown")
    close_if_terminal(store, STALLED_RUN, clock=lambda: NOW,
                      ids=lambda kind: f"{kind}-stalled")


def _decide(store: RunStore, *, gate_id: str, receipt_id: str, action: str,
            supersedes: str | None = None, run_id: str = GATED_RUN) -> str:
    """One receipt appended straight into the journal, as SETUP and never as
    the claim: what is under test is what the SCREEN posts, so the answers
    surrounding it are written the shortest honest way."""
    store.append(DecisionReceipt(
        receipt_id=receipt_id, run_id=run_id, gate_id=gate_id,
        action=action, actor="setup", decided_at=NOW,
        reason="Carried out around the answer under test.",
        scope_refs=("src",), config_digest=DIGEST, supersedes=supersedes))
    return receipt_id


def _carry_out_the_body(store: RunStore, *, start: int) -> None:
    """The three steps the loop reopens, carried out once each."""
    for offset, node_id in enumerate(BODY):
        settle_node(store, node_id, index=start + offset, run_id=GATED_RUN,
                    config_digest=DIGEST)


def _bind(root: Path):
    """The one server this module runs, on the first port of its own window."""
    for port in PORTS:
        try:
            return server.build(
                root, port,
                registry=AdapterRegistry([
                    DeepPlanAdapter(name) for name in
                    sorted({row["adapter"] for row in
                            STUDIO_CONFIG["instances"]})]),
                token_factory=lambda _size: TOKEN)
        except OSError:
            continue
    raise AssertionError(f"no port in {PORTS} was free for this module")


@pytest.fixture
def project(tmp_path) -> Iterator[_Project]:
    """A real server over a project holding the one routed run."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    _seed(root)
    httpd = _bind(root)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield _Project(f"http://{host}:{port}/", root)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "the decision-doors server did not stop"


def _open(chromium: Browser, project: _Project) -> tuple[Page, _Window]:
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    page = context.new_page()
    window = _Window(page)
    page.goto(project.url, wait_until="load")
    _settle(page)
    return page, window


def _read_the_run(page: Page, project: _Project, run: str = GATED_RUN) -> None:
    """Open the Runs screen, read this run, and wait for the read to LAND.

    Two barriers, and both are needed. The response barrier says the reads
    this click asked for have answered; the ROW barrier says the answer has
    been drawn, because the timeline draws one row per durable record and the
    journal on disk is what it is drawn from.

    Waiting for neither is a race with teeth: a read landing after a gate is
    chosen clears the decision draft with the rest of the run's facts, which
    deselects that gate a moment later -- so the form appears and then goes,
    and the next wait times out against a screen that is behaving correctly.
    """
    records = len(RunStore(project.root).read(run).records)
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    with page.expect_response(
            lambda answer: answer.url.endswith(
                f"/command/runs/{run}/controls")):
        page.locator(f'[data-focus-key="run:{run}"]').click()
    page.wait_for_function(
        "n => document.querySelectorAll('ol.studio-timeline > li').length === n",
        arg=records)


def _open_the_gate(page: Page, project: _Project, gate_id: str,
                   run: str = GATED_RUN) -> str:
    """Read the run, open its Decisions screen, and choose one gate."""
    _read_the_run(page, project, run)
    page.locator('[data-focus-key="action:showDecisions"]').click()
    page.wait_for_selector("#screenDecisions:not([hidden])")
    page.locator(f'[data-focus-key="decision:{run}/{gate_id}"]').click()
    page.wait_for_selector(".studio-decisions__detail")
    return page.locator(".studio-decisions__detail").inner_text()


def _answer(page: Page, project: _Project, gate_id: str, *,
            action: str, reason: str) -> None:
    """Answer one gate the way a person does, and wait for the read after it."""
    _open_the_gate(page, project, gate_id)
    page.wait_for_selector('[data-focus-key="action:submitDecision"]')
    page.locator('[data-focus-key="field:actor"]').fill(DECIDER)
    page.locator('[data-focus-key="field:actor"]').press("Tab")
    page.locator(f'[data-focus-key="choice:{action}"]').check()
    page.locator('[data-focus-key="field:reason"]').fill(reason)
    page.locator('[data-focus-key="field:reason"]').press("Tab")
    page.wait_for_selector(
        '[data-focus-key="action:submitDecision"]:not([disabled])')
    page.locator('[data-focus-key="action:submitDecision"]').click()
    page.wait_for_function(
        "() => document.getElementById('studioStatus')"
        ".innerText.includes('durable receipt')")


# -- 10. a gate the run has not reached ---------------------------------------


def test_a_gate_the_run_has_not_reached_offers_nothing_and_says_why(
        chromium: Browser, project: _Project) -> None:
    """WRITTEN RED against the reported defect, on the screen it reached through.

    The run has recorded nothing, so `confirm-gate` stands behind four steps
    that have not run. Before this rule the screen offered the whole form
    there, the POST was accepted, and the gate settled -- which made `do`
    runnable with `identify`, `diagnose` and `design` never carried out.

    Three things are asserted, and each excludes a different failure: the
    control must be ABSENT rather than merely disabled, the AND-only rule must
    be said, and the step actually being waited on must be named -- a sentence
    with no name in it sends a person looking for the wrong thing.
    """
    page, window = _open(chromium, project)
    try:
        said = _open_the_gate(page, project, CONFIRM_GATE)

        assert page.locator(
            '[data-focus-key="action:submitDecision"]').count() == 0, said
        assert "This gate cannot be answered yet." in said, said
        assert "ALL incoming roads must open" in said, said
        assert "Waiting on: design" in said, said
        # And the window wrote nothing at all on the way there.
        assert window.writes("/decisions") == 0
        assert window.problems == []
    finally:
        page.context.close()


def test_the_same_gate_offers_the_form_once_its_predecessors_settle(
        chromium: Browser, project: _Project) -> None:
    """The positive control: the rule is about the PLAN, not about the gate.

    The identical gate on the identical screen offers the whole form once the
    four steps in front of it have been carried out -- so a build that simply
    stopped offering decisions would fail here.
    """
    page, window = _open(chromium, project)
    try:
        assert page.locator(
            '[data-focus-key="action:submitDecision"]').count() == 0
        settle_node(RunStore(project.root), "goal", index=1,
                    run_id=GATED_RUN, config_digest=DIGEST)
        _carry_out_the_body(RunStore(project.root), start=2)
        page.reload(wait_until="load")
        _settle(page)

        said = _open_the_gate(page, project, CONFIRM_GATE)

        assert page.locator(
            '[data-focus-key="action:submitDecision"]').count() == 1, said
        assert "This gate cannot be answered yet." not in said, said
        assert window.problems == []
    finally:
        page.context.close()


def test_a_gate_answered_last_lap_offers_no_second_answer_until_this_lap_reaches_it(
        chromium: Browser, project: _Project) -> None:
    """R02 of the Codex review of `8dec0e4`, on the screen it reached through.

    The result gate sent the work back and `identify` has been carried out
    again, so a second lap has begun; `confirm-gate` -- approved in lap one --
    stands behind `diagnose` and `design` with that approval still standing.
    The screen used to offer the supersede form there, because a receipt stood,
    and the door accepted it: lap one's approval carried into lap two and `do`
    was authorized over two steps never carried out. Now the screen reads the
    door's own verdict off the run read and offers nothing, saying why; once
    the lap reaches the gate the form is back and names what it would replace.
    """
    _reach_the_result_gate(project, lap=1)
    store = RunStore(project.root)
    _decide(store, gate_id=RESULT_GATE, receipt_id="result-1",
            action="request_changes")
    settle_node(store, "identify", index=20, run_id=GATED_RUN,
                config_digest=DIGEST)
    page, window = _open(chromium, project)
    try:
        said = _open_the_gate(page, project, CONFIRM_GATE)

        assert page.locator(
            '[data-focus-key="action:submitDecision"]').count() == 0, said
        assert "This gate cannot be answered yet." in said, said
        assert "ALL incoming roads must open" in said, said
        assert "Waiting on: design" in said, said
        assert window.writes("/decisions") == 0

        settle_node(store, "diagnose", index=21, run_id=GATED_RUN,
                    config_digest=DIGEST)
        settle_node(store, "design", index=22, run_id=GATED_RUN,
                    config_digest=DIGEST)
        page.reload(wait_until="load")
        _settle(page)
        said = _open_the_gate(page, project, CONFIRM_GATE)

        assert page.locator(
            '[data-focus-key="action:submitDecision"]').count() == 1, said
        assert "supersedes confirm-1" in said, said
        assert window.problems == []
    finally:
        page.context.close()


def test_a_run_that_has_ended_offers_no_answer_and_says_it_has_ended(
        chromium: Browser, project: _Project) -> None:
    """A stalled run: the step spent its bound, and its terminal is recorded.

    Every gate on it is over at once, so the sentence is about the RUN and
    names the plan's own word for it. A screen reading only the gate's roads
    would have said "ALL incoming roads must open" here for ever -- about a
    gate whose road IS open, on a run where nothing will ever open anything.
    """
    page, window = _open(chromium, project)
    try:
        said = _open_the_gate(page, project, CONFIRM_GATE, run=STALLED_RUN)

        assert page.locator(
            '[data-focus-key="action:submitDecision"]').count() == 0, said
        assert "This run has ended (Plan: stalled)" in said, said
        assert "no decision can be recorded" in said, said
        assert "ALL incoming roads must open" not in said, said
        assert window.writes("/decisions") == 0
        assert window.problems == []
    finally:
        page.context.close()


def test_a_gate_unreached_refusal_re_reads_the_run_and_redraws_the_form(
        chromium: Browser, project: _Project) -> None:
    """The one decision refusal this window acts on rather than only reports.

    The server is doubled for one request so the refusal arrives exactly as it
    would from a run that moved under the screen. What must follow is a READ:
    a sentence alone would leave the same stale form under the same person,
    still offering the answer that was just refused. The read is counted, and
    the form is still there afterwards -- drawn from what came back.
    """
    _reach_the_result_gate(project, lap=1)
    page, window = _open(chromium, project)
    try:
        _open_the_gate(page, project, RESULT_GATE)
        page.route(f"**/command/runs/{GATED_RUN}/decisions", _refuse_once)
        before = _reads(window)
        page.locator('[data-focus-key="field:actor"]').fill(DECIDER)
        page.locator('[data-focus-key="field:actor"]').press("Tab")
        page.locator('[data-focus-key="choice:approve"]').check()
        page.wait_for_selector(
            '[data-focus-key="action:submitDecision"]:not([disabled])')
        page.locator('[data-focus-key="action:submitDecision"]').click()
        page.wait_for_function(
            "n => [...performance.getEntriesByType('resource')].filter("
            "row => row.name.endsWith('/command/runs/run-decision-doors'))"
            ".length > n", arg=before)

        assert _reads(window) > before, window.rows
        said = page.locator("#studioStatus").inner_text()
        assert "has not been reached yet" in said, said
        # That read cleared the decision draft with the rest of the run's
        # facts, which is the product behaving as designed and is why the
        # refusal is worth a read at all: what the person sees when they choose
        # the gate again is drawn from what came back, not from what was on
        # screen when the refusal arrived.
        page.locator(
            f'[data-focus-key="decision:{GATED_RUN}/{RESULT_GATE}"]').click()
        page.wait_for_selector('[data-focus-key="action:submitDecision"]')
        assert page.locator(
            '[data-focus-key="field:actor"]').input_value() == ""
        # The PAGE's own errors, not `problems`: a refused write is a non-2xx
        # response, and the browser writes its own console line about that. It
        # is the network stack reporting the refusal this test asked for, and
        # `_Window` keeps the two apart for exactly this reason.
        assert window.page_errors == []
    finally:
        page.unroute(f"**/command/runs/{GATED_RUN}/decisions")
        page.context.close()


def _refuse_once(route) -> None:
    """Answer one POST the way the server answers an unreached gate."""
    route.fulfill(status=409, content_type="application/json",
                  body=json.dumps({"error": {
                      "code": "gate_unreached",
                      "message": "a decision may stand only on a gate this "
                                 "run's plan has reached",
                      "detail": {}}}))


def _reads(window: _Window) -> int:
    """How many authoritative run reads this window has taken."""
    return len([row for row in window.rows if row[0] == "GET"
                and row[1].endswith(f"/command/runs/{GATED_RUN}")])


# -- 11. the loop, answered three times from the screen -----------------------


def _reach_the_result_gate(project: _Project, *, lap: int) -> None:
    """Carry the run round to its result gate once more.

    The body is carried out and the confirm gate answered, each answer
    superseding the one before it -- which is what a real lap does and what
    `gate_decision` requires: two unsuperseded receipts on one gate leave the
    projection unable to say which is current.
    """
    store = RunStore(project.root)
    if lap == 1:
        settle_node(store, "goal", index=1, run_id=GATED_RUN,
                    config_digest=DIGEST)
    _carry_out_the_body(store, start=10 * lap)
    _decide(store, gate_id=CONFIRM_GATE, receipt_id=f"confirm-{lap}",
            action="approve",
            supersedes=None if lap == 1 else f"confirm-{lap - 1}")
    settle_node(store, "do", index=10 * lap + 5, run_id=GATED_RUN,
                config_digest=DIGEST)


def _plan_words(page: Page, project: _Project) -> str:
    """What the Runs screen says about THIS run, and not about the list.

    The detail container alone: the list beside it carries a row per run in the
    project, and a word read off the whole screen could have come from a run
    this witness never touched.
    """
    _read_the_run(page, project)
    return page.locator(".studio-runs__detail").inner_text()


def _result_receipts(project: _Project) -> list[DecisionReceipt]:
    """Every durable answer this run holds for the result gate."""
    return [row.value for row in RunStore(project.root).read(GATED_RUN).records
            if isinstance(row.value, DecisionReceipt)
            and row.value.gate_id == RESULT_GATE]


def _three_answers(page: Page, project: _Project) -> None:
    """Three `request_changes` on the result gate, a real lap between each.

    The lap in the middle is what makes the second answer a second ANSWER and
    not a correction of the first: a superseding receipt written before the
    loop reopened replaces that lap's answer and adds no lap, and one written
    after it adds one. The Runs screen is read between them, so the loop's
    position is asserted while it is still moving rather than only at the end.
    """
    _answer(page, project, RESULT_GATE, action="request_changes",
            reason="Send it back around, pass one.")
    _reach_the_result_gate(project, lap=2)
    page.reload(wait_until="load")
    _settle(page)
    assert "pass 2 of 3" in _plan_words(page, project)

    _answer(page, project, RESULT_GATE, action="request_changes",
            reason="Send it back around, pass two.")
    _reach_the_result_gate(project, lap=3)
    page.reload(wait_until="load")
    _settle(page)
    _answer(page, project, RESULT_GATE, action="request_changes",
            reason="Send it back around, pass three.")


def test_the_result_gate_is_answered_three_times_from_the_screen(
        chromium: Browser, project: _Project) -> None:
    """Acceptance step 13's second pass, driven the way a person drives it.

    Each answer sends the work back around; the body is carried out again
    between them, so each lap really is a lap. What is held is the whole of
    what stopped this being drivable:

    - the FIRST answer supersedes nothing, because nothing stands yet;
    - the second and third NAME the receipt standing on that gate, so the
      projection can still say which answer is current -- it read `unknown`
      before, from two unsuperseded receipts on one gate;
    - and each carries an identity of its own, so the second is a new receipt
      rather than a conflicting retry of the first.

    The Runs screen is read between them: the loop's position is the run's own
    fact and the ceiling is the plan's, and the last answer reaches the bound.
    """
    _reach_the_result_gate(project, lap=1)
    page, window = _open(chromium, project)
    try:
        _three_answers(page, project)

        # The RENDERED half first, because it is the one a person meets:
        # `unknown` is what two unsuperseded answers on one gate produce, and
        # it is what this window used to write on the second press.
        said = _plan_words(page, project)
        assert "unknown" not in said, said
        # Named by the STEP, which is how the Runs screen names a gate: the
        # gate id is the decision's, and the plan's own word for where it sits
        # is the node.
        assert "result-gate — changes_requested" in said, said
        assert "retry-loop — bound reached" in said, said
        assert "the plan has nothing left to open" in said, said

        posted = window.posted("/decisions")
        assert len(posted) == 3, posted
        assert [row["gate_id"] for row in posted] == [RESULT_GATE] * 3
        assert [row["action"] for row in posted] == ["request_changes"] * 3
        # The first supersedes nothing; each later one names what stands.
        assert posted[0]["supersedes"] is None, posted[0]
        assert posted[1]["supersedes"] == posted[0]["receipt_id"], posted
        assert posted[2]["supersedes"] == posted[1]["receipt_id"], posted
        assert len({row["receipt_id"] for row in posted}) == 3, posted

        assert len(_result_receipts(project)) == 3
        assert window.problems == []
    finally:
        page.context.close()
