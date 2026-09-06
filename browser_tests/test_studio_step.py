"""Driving a planned run from the Studio, in a real Chromium against the server.

This is the circuit the Runs screen did not have. A person could open a run,
watch it say `plan: runnable` about its first step, and find nothing anywhere on
the screen that would propose or confirm it: the only road to an attempt was the
legacy composer, which cannot emit a `node_id` and is refused on every planned
run. The product could draw a plan, freeze it into a run, and then not run it.

What this module drives is the ROAD, and every claim on it is about something
DURABLE:

- propose, confirm, and the records that follow -- read out of the STORE, not
  off the screen. Both bodies this window put on the wire are read back out of
  the request log and judged key by key, because a window that showed the right
  facts and posted the wrong ones would pass every source guard here;
- what the control SAYS it will carry, and that it offers no way to change any
  of it;
- the two numbers a body carries that no default produces: an attempt id past
  the one this run already holds, and a ceiling smaller than the window's own;
- and what survives a write that was refused, or a read that landed while
  somebody was typing.

WHICH rows are offered a control at all -- and what every row that gets none
says instead -- is ``browser_tests/test_studio_step_offers.py``, split off when
this module reached the line cap. It imports the bench and the helpers below, so
the seven runs are still described in one place.

The provider registry is the executing fake the coordinator's own tests admit
through the real provider door, so the attempt that follows a confirmation is a
real attempt through the real runtime.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    ActionResultReceipt,
)
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.run_store import RunStore, snapshot_digest

from conductor.command.attempts import action_request_digest

from browser_tests.test_studio_lifecycle import (
    STUDIO_CONFIG,
    TOKEN,
    _Window,
    _settle,
)
from tests.alpha3_graph_artifacts import dalio_definition
from tests.schedule_journal import routed_dalio
from tests.test_command_execution_coordinator import ids, provider_registry
from tests.test_command_graph_projection import (
    a_decision,
    a_proposal,
    a_request,
    an_event,
    settle_node,
    settle_to_the_confirm_gate,
)
from tests.test_command_run_store import a_run
from tests.test_store import good_lane, write_project

DIGEST = snapshot_digest(STUDIO_CONFIG)
#: The run every step of the road is driven on: the shipped plan, nothing
#: attempted, so its first step is the one thing the schedule offers.
RUN_ID = "run-001"
#: One whose only attempt has been authorized and has not answered. Its runtime
#: phase is `requested`: nothing has crossed a durable boundary yet.
FLIGHT_RUN = "run-flight"
#: The same unanswered attempt, one boundary further on: both attempt events
#: written and no result. The phase is `observed` and the outcome is still
#: null, which is the shape a reader of the phase alone gets right by accident
#: and a reader of the records gets right for the reason.
OBSERVED_RUN = "run-observed"
#: An unanswered request with a LATER proposal appended over it -- a stale
#: second window, or any caller: `POST /proposals` holds no schedule check. The
#: node's current action is then the proposal, so its phase reads `proposed`
#: with a null outcome while a worker is still executing.
RESTALE_RUN = "run-restale"
#: One whose first step is finished, so the plan has moved on to the second.
DONE_RUN = "run-done"
#: One on the ROUTED plan whose gate was rejected, so the effecting step is
#: closed rather than merely waiting.
CLOSED_RUN = "run-closed"
#: One a HALT stopped, whose own step answered `unknown` -- which settles
#: nothing, because an unanswered question stays askable. Its row is `blocked`
#: with no road, no document and attempts left, exactly like a step whose
#: worker is still running, and its runtime phase is `observed` for both. The
#: only fact that tells them apart is the outcome.
HALTED_RUN = "run-halted"
#: One whose offered step already carries an authorized attempt, numbered with
#: a GAP: a mint that counted the set would ask for an id this run already
#: holds, and `_hold_attempt_is_not_taken` refuses that forever.
LAP_RUN = "run-lap"
#: One whose offered step names a ceiling of its own, below what this window
#: would otherwise ask for.
CEILING_RUN = "run-ceiling"
CONFIRM_GATE = "gate-confirm-do"
STEP = "goal"
#: The one step of the two-node plan the three runs above follow, and the step
#: beside it that can stop the whole run.
LONE = "alpha"
HALTING = "omega"
#: The ceiling `run-ceiling`'s step names, and the attempt its `run-lap`
#: sibling already holds. Both are chosen to be numbers no default produces.
NODE_CEILING = 120
SPENT_ATTEMPT = f"attempt-{LONE}-1"
ACTOR = "release-owner"
WHY = "Start the plan at its first step."
#: What the run's journal holds once one step has been carried out whole. Five
#: records after the plan, and the two attempt events are the durable boundaries
#: of the one attempt.
WALKED = ["graph_definition", "action_proposal", "action_request",
          "attempt_event", "attempt_event", "action_result"]
#: `api_contracts._CONFIRM_FIELDS`. Spelled here because this module asserts
#: what a BROWSER posted; the derivation from the contract lives in
#: `tests/test_studio_step_source.py`, and the two disagreeing is the point of
#: having both.
CONFIRM_KEYS = {"proposal_id", "preview_digest", "capability", "scope",
                "config_digest", "confirmed_by"}
#: The instant every seeded record carries. Fixed, so a journal this module
#: writes twice is the same journal.
NOW = "2026-08-19T09:00:00Z"


class _Bench:
    """The served URL and the durable tree behind it, for the third check."""

    def __init__(self, url: str, root: Path) -> None:
        self.url = url
        self.root = root

    def kinds(self, run_id: str = RUN_ID) -> list[str]:
        return [row.kind for row in RunStore(self.root).read(run_id).records]

    def records(self, run_id: str, kind: str) -> list[object]:
        return [row.value for row in RunStore(self.root).read(run_id).records
                if row.kind == kind]

    def node(self, node_id: str, run_id: str = RUN_ID):
        """One step of the plan this run really froze, off the store itself."""
        plan = self.records(run_id, "graph_definition")[0]
        return next(row for row in plan.nodes if row.node_id == node_id)

    def node_attempts(self, run_id: str, node_id: str) -> list[str]:
        """Every attempt id this run has AUTHORIZED on one step."""
        return [row.attempt_id for row in self.records(run_id, "action_request")
                if row.node_id == node_id]


def _open_run(store: RunStore, run_id: str) -> None:
    store.create_run(
        a_run(run_id=run_id, mode="confirm", config_digest=DIGEST),
        STUDIO_CONFIG)


#: The arguments the shipped plan's first step carries, borrowed for the small
#: two-node plan below so both are payloads the argument door really admits.
ARGUMENTS = dict(
    next(row for row in dalio_definition().nodes
         if row.node_id == STEP).payload())


def _review(node_id: str, **extra) -> GraphNode:
    return GraphNode(node_id=node_id, kind="task", title=node_id.title(),
                     instance_id="claude-dev", capability="review",
                     arguments=dict(ARGUMENTS), **extra)


def _two_steps(run_id: str, nodes) -> GraphDefinition:
    """A plan of independent steps: no edges, so no row waits on a road.

    The shipped Dalio plan is a chain, and every row of it after the first is
    blocked BY A ROAD -- which is a different sentence and a different branch.
    The rows these three runs are about must be blocked, or runnable, for
    reasons that have nothing to do with what comes before them.
    """
    return GraphDefinition(graph_id="graph-two", run_id=run_id,
                           created_at=NOW, nodes=nodes, edges=())


def _a_proposal(run_id: str, node_id: str, *, index: int, attempt_id: str):
    return ActionProposal(
        proposal_id=f"proposal-{index}", run_id=run_id, attempt_id=attempt_id,
        instance_id="claude-dev", capability="review", arguments=ARGUMENTS,
        scope=("src",), proposed_by="seed", proposed_at=NOW,
        timeout_seconds=900, rationale=f"Carry out {node_id}.",
        config_digest=DIGEST, node_id=node_id)


def _unanswered(store: RunStore, run_id: str, node_id: str, *, index: int,
                attempt_id: str):
    """A proposal and the request it authorizes, and no answer to either.

    Both records, because the store holds them to each other: a request naming
    a node must repeat a proposal the run already holds.
    """
    proposal = _a_proposal(run_id, node_id, index=index, attempt_id=attempt_id)
    store.append(proposal)
    return _authorize(store, proposal, index=index)


def _authorize(store: RunStore, proposal, *, index: int):
    """The request one proposal authorizes, appended and answered by nothing."""
    request = ActionRequest(
        action_id=f"action-{index}", run_id=proposal.run_id,
        attempt_id=proposal.attempt_id, instance_id="claude-dev",
        capability="review", arguments=ARGUMENTS, scope=("src",),
        requested_by="seed", requested_at=NOW,
        idempotency_key=f"dispatch-{proposal.proposal_id}",
        timeout_seconds=900, preview_digest=proposal.preview_digest,
        mode="confirm", node_id=proposal.node_id)
    store.append(request)
    return request


def _one_attempt(store: RunStore, run_id: str, node_id: str, *, index: int,
                 attempt_id: str, outcome: str) -> None:
    """One authorized attempt on one step, answered.

    Written through the contracts rather than through `settle_node`, because
    both the ATTEMPT ID and the OUTCOME are under test here and that helper
    chooses each for its own reasons.
    """
    proposal = _a_proposal(run_id, node_id, index=index, attempt_id=attempt_id)
    store.append(proposal)
    request = _authorize(store, proposal, index=index)
    store.append(ActionResultReceipt(
        receipt_id=f"result-{index}", action_id=request.action_id,
        run_id=run_id, attempt_id=attempt_id, instance_id="claude-dev",
        outcome=outcome, exit_code=1, observed_at=NOW, evidence_refs=()))


def _seed(root: Path) -> None:
    """Seven runs, each stopped somewhere different.

    Nothing here is hand-written JSON: every record is built through the same
    contract the runtime writes, so a journal this seed produces is one the
    store would have produced. Two halves, because they follow two plans: the
    SHIPPED one, whose chain is what makes a row wait on a road, and a small
    plan of independent steps, whose rows can only be blocked for reasons that
    are about themselves.
    """
    store = RunStore(root)
    _seed_the_shipped_plan(store)
    _seed_the_independent_steps(store)
    _seed_the_unanswered_attempts(store)


def _seed_the_shipped_plan(store: RunStore) -> None:
    """Four runs of the Dalio cycle: fresh, in flight, one step done, closed."""
    _open_run(store, RUN_ID)
    store.append(dalio_definition(run_id=RUN_ID))

    # An attempt authorized and unanswered: `attempt_in_flight` blocks the step
    # it names, and the row must say which of the two blocked situations it is.
    _open_run(store, FLIGHT_RUN)
    store.append(dalio_definition(run_id=FLIGHT_RUN))
    proposal = a_proposal(node_id=STEP, index=1, run_id=FLIGHT_RUN,
                          config_digest=DIGEST)
    store.append(proposal)
    store.append(a_request(proposal, index=1, run_id=FLIGHT_RUN))

    # One step carried out whole, so it is settled and the next is offered.
    _open_run(store, DONE_RUN)
    store.append(dalio_definition(run_id=DONE_RUN))
    settle_node(store, STEP, index=21, run_id=DONE_RUN, config_digest=DIGEST)

    # The routed plan, and a gate answered the way that CLOSES the road out of
    # it: `confirm-gate -> do` opens only `on_approved`, so a rejection makes
    # the effecting step unreachable rather than merely blocked.
    _open_run(store, CLOSED_RUN)
    drawn = routed_dalio()
    store.append(GraphDefinition(
        graph_id=drawn.graph_id, run_id=CLOSED_RUN, created_at=drawn.created_at,
        nodes=drawn.nodes, edges=drawn.edges))
    settle_to_the_confirm_gate(store, run_id=CLOSED_RUN, config_digest=DIGEST)
    store.append(a_decision(index=1, gate_id=CONFIRM_GATE, run_id=CLOSED_RUN,
                            action="reject", config_digest=DIGEST))


def _seed_the_independent_steps(store: RunStore) -> None:
    """Three runs of a plan with no roads: a halt, a lap, and a ceiling."""
    # A run a HALT stopped, whose own step answered `unknown`. `unknown` is
    # this product's word for "the journal supports no answer", so the step is
    # not settled and its attempts are not spent -- and `_stop_runnable` then
    # rewrote it from runnable to blocked. It is the halt case wearing the
    # in-flight case's clothes: same state, same empty roads, same `observed`
    # phase, and only the outcome tells the two apart.
    _open_run(store, HALTED_RUN)
    store.append(_two_steps(HALTED_RUN, (
        _review(LONE), _review(HALTING, failure_policy="halt_run"))))
    _one_attempt(store, HALTED_RUN, LONE, index=1,
                 attempt_id=f"attempt-{LONE}-0", outcome="unknown")
    _one_attempt(store, HALTED_RUN, HALTING, index=2,
                 attempt_id=f"attempt-{HALTING}-0", outcome="failed")

    # The same `unknown`, with nothing to halt the run: the step stays RUNNABLE
    # and already holds an attempt -- numbered 1, with no 0 before it.
    _open_run(store, LAP_RUN)
    store.append(_two_steps(LAP_RUN, (_review(LONE),)))
    _one_attempt(store, LAP_RUN, LONE, index=3, attempt_id=SPENT_ATTEMPT,
                 outcome="unknown")

    # A step that names a ceiling of its own, below this window's.
    _open_run(store, CEILING_RUN)
    store.append(_two_steps(
        CEILING_RUN, (_review(LONE, timeout_seconds=NODE_CEILING),)))


def _seed_the_unanswered_attempts(store: RunStore) -> None:
    """Two runs whose worker is executing, and whose PHASE says two things.

    Both hold one authorized attempt that no result closes. The phase reports
    the node's CURRENT action, so one reads `observed` and the other -- a later
    proposal appended over the same unanswered request -- reads `proposed`.
    """
    # An unanswered attempt one boundary further on: both attempt events, no
    # result. The phase reads `observed` and the outcome is still null.
    #
    # A SECOND step beside it carries an attempt that DID answer, so this run
    # holds results as well as an outstanding request. That is what makes the
    # rule "no result closes THIS action_id" different from the weaker "this
    # run holds no result", which would otherwise agree on every seed here.
    _open_run(store, OBSERVED_RUN)
    store.append(_two_steps(OBSERVED_RUN, (_review(LONE), _review(HALTING))))
    _one_attempt(store, OBSERVED_RUN, HALTING, index=7,
                 attempt_id=f"attempt-{HALTING}-0", outcome="failed")
    watched = _unanswered(store, OBSERVED_RUN, LONE, index=4,
                          attempt_id=f"attempt-{LONE}-0")
    store.append(an_event(watched, "effect_lease", index=4,
                          run_id=OBSERVED_RUN,
                          request_digest=action_request_digest(watched)))
    store.append(an_event(watched, "execution_observed", index=4,
                          run_id=OBSERVED_RUN, outcome="succeeded", exit_code=0,
                          request_digest=action_request_digest(watched)))

    # …and the shape the PHASE cannot answer at all: a later proposal appended
    # over that unanswered request. `POST /proposals` holds no schedule check,
    # so a stale second window really can write one -- and the node's current
    # action is then the PROPOSAL, whose phase is `proposed` with a null
    # outcome, while the worker the request authorized is still executing.
    _open_run(store, RESTALE_RUN)
    store.append(_two_steps(RESTALE_RUN, (_review(LONE),)))
    _unanswered(store, RESTALE_RUN, LONE, index=5,
                attempt_id=f"attempt-{LONE}-0")
    store.append(_a_proposal(RESTALE_RUN, LONE, index=6,
                             attempt_id=f"attempt-{LONE}-1"))


@pytest.fixture
def bench(tmp_path) -> Iterator[_Bench]:
    """A real server whose bound adapter can actually EXECUTE.

    The fake is the one `tests/test_command_execution_coordinator.py` admits
    through the real provider door -- resolved by `resolve_providers`, built by
    the real factory, registered in a real `ProviderRegistry` -- so what a
    confirmation authorizes here is driven by the production runtime and the
    server's own execution coordinator. `DeepPlanAdapter`, which the other
    Studio benches use, declares schemas and executes nothing, so a run driven
    against it would stop at the request and prove half the road.
    """
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    _seed(root)
    mint = ids()
    harness = tmp_path / "harness"
    harness.mkdir()
    httpd = server.build(
        root, 0, registry=provider_registry(harness, mint), ids=mint,
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield _Bench(f"http://{host}:{port}/", root)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "step bench server did not stop"


def _open(chromium: Browser, bench: _Bench) -> tuple[Page, _Window]:
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    page = context.new_page()
    window = _Window(page)
    page.goto(bench.url, wait_until="load")
    _settle(page)
    return page, window


def _read(page: Page, run_id: str) -> None:
    """Open one run whole, waiting on the DETAIL being the one asked for."""
    page.locator("#navRuns").click()
    page.wait_for_selector("#screenRuns:not([hidden])")
    page.locator(f'[data-focus-key="run:{run_id}"]').click()
    page.wait_for_function(
        "id => { const head = document.querySelector("
        "'.studio-runs__detail h2'); return head "
        "&& head.innerText.trim() === id; }", arg=run_id)
    page.wait_for_selector("ul.studio-positions")


def _row(page: Page, node_id: str) -> str:
    """One position row's whole text, found by the step it is about."""
    rows = page.locator("li.studio-position").evaluate_all(
        "items => items.map(item => item.innerText)")
    found = [row for row in rows if f"{node_id} · " in row]
    assert len(found) == 1, (node_id, rows)
    return found[0]


def _offered(page: Page) -> list[str]:
    """Every step this screen is offering a control for, in document order."""
    return page.locator('[data-focus-key^="propose:"], '
                        '[data-focus-key^="confirm:"]').evaluate_all(
        "items => items.map(item => item.dataset.focusKey)")


def _type(page: Page, key: str, value: str) -> None:
    """Type into one field the way a person does, and commit it.

    By KEYSTROKE rather than `fill`, and the difference is measured: a read
    landing between a fill and its blur -- the `run` frame that follows every
    accepted write -- replaced the control and discarded the filled value,
    which is the disabled-Confirm stall the review's `studio_modes` probe met
    (3 of 6 runs) and this module met on its own confirm road. Typed
    characters survive that re-render: Chromium commits a focused control's
    value when the control is removed, and the window restores focus to the
    control drawn in its place.
    """
    control = page.locator(f'[data-focus-key="{key}"]')
    control.click()
    page.keyboard.type(value)
    page.keyboard.press("Tab")


# -- 1. the whole road --------------------------------------------------------


def _drive(page: Page, window: _Window, node: str = STEP) -> None:
    """Propose the step the plan offers, then confirm what stands on it.

    Two presses and four keystrokes, in the order a person makes them -- except
    that Propose is pressed TWICE. A proposal's identity is minted by the
    SERVER, so a second press that reached the wire would be a second durable
    proposal rather than a retry of the first, and nothing downstream could
    tell which one a person meant.

    The MECHANISM is asserted as well as its effect, because the effect alone
    could not fail. Two back-to-back `click()` calls measured one proposal
    whatever the window did -- the second synthesized press does not survive
    the subtree being replaced under it -- so this reads the control's own
    state first, and then forces a press through anyway: a disabled button
    fires no click and no submit, and the count says so.

    The Confirm control is WAITED for rather than assumed: it exists only once
    the read that follows the write shows the proposal, which is what makes the
    second half of this road a statement about a durable record.
    """
    _type(page, "field:proposed_by", ACTOR)
    _type(page, "field:rationale", WHY)
    press = page.locator(f'[data-focus-key="propose:{node}"]')
    press.click()
    shut = page.evaluate(
        "key => { const button = document.querySelector("
        "`[data-focus-key='${key}']`); return button === null ? \"gone\" "
        ": (button.disabled ? \"shut\" : \"open\"); }", f"propose:{node}")
    assert shut in ("gone", "shut"), (
        "the control stayed pressable while its own write was in flight")
    # Forced only while the button is still THERE. On a fast host the read has
    # already landed and replaced the form, and a forced click on a locator
    # that resolves to nothing waits out its own timeout for no reason.
    if shut == "shut":
        press.click(force=True, no_wait_after=True, timeout=3000)
    page.wait_for_selector(f'[data-focus-key="confirm:{node}"]')
    assert len(window.posted("/proposals")) == 1, window.posted("/proposals")
    _type(page, "field:confirmed_by", ACTOR)
    page.locator(f'[data-focus-key="confirm:{node}"]').click()
    # Waited on as AT LEAST, never as exactly: reads are coalesced, so a window
    # can go from two rows to six without ever drawing three.
    page.wait_for_function(
        "n => document.querySelectorAll('ol.studio-timeline > li').length >= n",
        arg=len(WALKED), timeout=20000)


def _settled(page: Page, node: str) -> None:
    """Wait until the SCREEN says this step is finished with.

    The deterministic signal for a road driven on a plan of one step. A row
    count cannot serve: those journals hold a seeded attempt as well, so the
    timeline is already past any threshold the drive itself would wait on.
    """
    page.wait_for_function(
        "id => [...document.querySelectorAll('li.studio-position')].some("
        "item => item.innerText.includes(id + ' \\u00b7 ') "
        "&& item.innerText.includes('plan: settled'))", arg=node, timeout=20000)


def _fact(page: Page, step: str, label: str) -> str:
    """One labelled fact of one step form, read as its own row.

    Read as a ROW rather than as a substring of the whole form: every sentence
    beside these numbers mentions numbers too, so "900s is not on this form"
    was a claim about the prose and not about the fact under it.
    """
    found = page.locator(f'[data-step="{step}"] .studio-fact').evaluate_all(
        "(items, key) => items.filter(item => item.children[0]"
        " && item.children[0].innerText === key)"
        ".map(item => item.children[1].innerText)", label)
    assert len(found) == 1, (label, found)
    return found[0]


def _judge_the_bodies(window: _Window, bench: _Bench) -> None:
    """What the browser really PUT ON THE WIRE, key by key.

    Read out of the request log rather than off the screen, and judged against
    the plan the run froze and the proposal the journal holds. A window that
    showed the right facts and posted different ones would pass every other
    assertion in this module.
    """
    node = bench.node(STEP)
    proposals = window.posted("/proposals")
    assert len(proposals) == 1, proposals
    sent = proposals[0]
    assert sent["node_id"] == STEP
    assert sent["instance_id"] == node.instance_id
    assert sent["capability"] == node.capability
    assert sent["arguments"] == node.payload()
    assert sent["proposed_by"] == ACTOR and sent["rationale"] == WHY

    actions = window.posted("/actions")
    assert len(actions) == 1, actions
    confirmed = actions[0]
    assert set(confirmed) == CONFIRM_KEYS, sorted(confirmed)
    stored = bench.records(RUN_ID, "action_proposal")[0]
    assert confirmed["preview_digest"] == stored.preview_digest
    assert confirmed["proposal_id"] == stored.proposal_id
    assert confirmed["confirmed_by"] == ACTOR


def test_a_runnable_step_is_proposed_confirmed_and_observed_from_the_runs_screen(
        chromium: Browser, bench: _Bench) -> None:
    """The circuit that did not exist, driven the way a person drives it.

    Every claim here is about something DURABLE. The two bodies are read out of
    the browser's own request log and judged against the plan the run froze; the
    journal is read with the production store; and the screen is asked last,
    because "the screen says it happened" is the weakest of the three.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        assert bench.kinds() == ["graph_definition"], "the seed already ran"
        assert _offered(page) == [f"propose:{STEP}"], _offered(page)

        _drive(page, window)

        assert bench.kinds() == WALKED, bench.kinds()
        _judge_the_bodies(window, bench)
        # The request the runtime minted carries the plan's binding, copied
        # from the stored proposal and never from a body this window sent.
        assert bench.records(RUN_ID, "action_request")[0].node_id == STEP
        # And what the screen says about it, last and least.
        assert "plan: settled" in _row(page, STEP), _row(page, STEP)
        assert "plan: runnable" in _row(page, "identify")
        assert _offered(page) == ["propose:identify"], _offered(page)
    finally:
        assert window.problems == []
        page.context.close()


# -- 2. and nothing else is offered -------------------------------------------


def test_the_step_control_says_what_a_proposal_will_carry_and_offers_no_edit(
        chromium: Browser, bench: _Bench) -> None:
    """The plan's facts are SHOWN, and there is no control over any of them.

    A person about to authorize work is entitled to see exactly what it is; a
    person is not entitled to change it, because the server refuses arguments
    that are not the node's own bytes and a form that invited the edit would be
    inviting a refusal.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        form = page.locator(f'[data-step="propose:{STEP}"]')
        said = form.inner_text()
        node = bench.node(STEP)

        assert node.instance_id in said and node.capability in said
        assert "work-001" in said and "artifact-brief" in said
        assert f"attempt-{STEP}-0" in said, said
        assert "900s" in said, said
        assert "Scope is a declaration this run's records carry" in said, said
        # TWO text controls on this form -- who is proposing and why -- and
        # nothing else on the screen that could touch a step: no select, no
        # argument box, no way to name another step. The only other controls
        # on the screen are the document form's, and every one of them sits
        # inside it. The third of the three a person ever types,
        # `confirmed_by`, belongs to the form that replaces this one.
        assert form.locator("input").count() == 2
        assert form.locator("select").count() == 0
        assert form.locator("textarea").count() == 0
        for tag in ("select", "textarea"):
            assert page.locator(f"#bodyRuns {tag}").count() == page.locator(
                f'#bodyRuns [data-step="document"] {tag}').count(), tag
        assert sorted(form.locator("input").evaluate_all(
            "items => items.map(item => item.name)")) == [
                "proposed_by", "rationale"]
    finally:
        assert window.problems == []
        page.context.close()


def test_a_refused_write_gives_the_control_back_with_the_words_still_in_it(
        chromium: Browser, bench: _Bench) -> None:
    """The promise beside every shut step control, kept.

    The draft used to be destroyed at the door -- which did make a second press
    impossible, and also emptied the form on every refusal that brings no read.
    A person met a blank form beside a sentence saying what they typed is kept,
    with nothing to press and nothing to press it with.

    The refusal is made to LAND rather than simulated: a 400 in the boundary's
    own vocabulary, which is what a body it will not admit really answers. The
    write flag is what shuts the control, so it is the write flag that has to
    come back off -- and the fields are read for their values afterwards.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        page.route(f"**/command/runs/{RUN_ID}/proposals", lambda route:
                   route.fulfill(status=400, content_type="application/json",
                                 body=json.dumps({"error": {
                                     "code": "contract_invalid",
                                     "message": "refused for this test"}})))
        try:
            _type(page, "field:proposed_by", ACTOR)
            _type(page, "field:rationale", WHY)
            page.locator(f'[data-focus-key="propose:{STEP}"]').click()
            page.wait_for_selector(
                f'[data-focus-key="propose:{STEP}"]:not([disabled])')

            assert page.locator(
                '[data-focus-key="field:proposed_by"]').input_value() == ACTOR
            assert page.locator(
                '[data-focus-key="field:rationale"]').input_value() == WHY
            assert len(window.posted("/proposals")) == 1
            assert bench.kinds() == ["graph_definition"], bench.kinds()
            # And the refusal is on screen, in the window's own words.
            assert "Writing…" not in page.locator("#studioStatus").inner_text()
        finally:
            page.unroute(f"**/command/runs/{RUN_ID}/proposals")
    finally:
        # The two logs are kept apart for exactly this test. A page error is
        # always the window's; the console also carries the BROWSER's own note
        # that a resource answered non-2xx, which is what a refusal looks like
        # from the network stack and is not a fault in the code under test.
        assert window.page_errors == []
        assert all("400" in row for row in window.console_errors), (
            window.console_errors)
        page.context.close()


def test_a_read_of_the_same_run_leaves_the_words_a_person_is_typing_alone(
        chromium: Browser, bench: _Bench) -> None:
    """Owner acceptance step 16, as the reducer's rule and as a gesture.

    Every run frame ends in a re-read -- an attempt event on another branch, a
    reconnect, a `state` frame -- and the read used to reset the step draft.
    So the words vanished under a person's hands while the control beside them
    promised that what they typed is kept.

    The re-read here is a real one and it is PROVEN to have landed: a record is
    appended to this run first, and the assertion waits for the timeline to
    grow before it reads the fields back. Without that wait this would pass on
    the DOM the person was already looking at.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        before = page.locator("ol.studio-timeline > li").count()

        # A record on ANOTHER step of this run: the sort of thing a worker's
        # progress writes, and exactly what a `run` frame arrives about.
        RunStore(bench.root).append(a_proposal(
            node_id="identify", index=41, run_id=RUN_ID, config_digest=DIGEST))
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        page.wait_for_function(
            "n => document.querySelectorAll('ol.studio-timeline > li').length"
            " > n", arg=before)

        assert page.locator(
            '[data-focus-key="field:proposed_by"]').input_value() == ACTOR
        assert page.locator(
            '[data-focus-key="field:rationale"]').input_value() == WHY
        # …and the read really did replace the subtree: the control is live,
        # drawn from what came back rather than left over from before.
        assert page.locator(
            f'[data-focus-key="propose:{STEP}"]').is_enabled()
    finally:
        assert window.problems == []
        page.context.close()


def test_the_attempt_id_counts_past_the_one_this_run_already_holds(
        chromium: Browser, bench: _Bench) -> None:
    """A second lap asks for an id no earlier attempt has taken.

    The seeded attempt is numbered 1 with no 0 before it, which is the shape a
    COUNT gets wrong: one attempt counted as one would ask for
    `attempt-alpha-1` again, `_hold_attempt_is_not_taken` would refuse it, and
    the refusal would be permanent -- the same journal mints the same id every
    time, so that step could never be proposed again from this window.

    Both halves are asserted: the id on the wire, and the road completing --
    because the collision is not a rendering fault, it is a 409 at the Confirm.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, LAP_RUN)
        assert _offered(page) == [f"propose:{LONE}"], _offered(page)
        assert SPENT_ATTEMPT in bench.node_attempts(LAP_RUN, LONE)
        assert _fact(page, f"propose:{LONE}", "Attempt id") == f"attempt-{LONE}-2"

        _drive(page, window, node=LONE)
        _settled(page, LONE)

        assert window.posted("/proposals")[0]["attempt_id"] == f"attempt-{LONE}-2"
        assert bench.node_attempts(LAP_RUN, LONE) == [
            SPENT_ATTEMPT, f"attempt-{LONE}-2"]
        # The plan of one step has nothing left to open, so it also records its
        # ending -- which is what a road that really completed looks like.
        assert bench.kinds(LAP_RUN)[-2:] == ["action_result", "run_terminal"]
    finally:
        assert window.problems == []
        page.context.close()


def test_the_window_asks_for_the_steps_own_ceiling_when_it_is_the_smaller(
        chromium: Browser, bench: _Bench) -> None:
    """The plan's number reaches the wire, and the sentence beside it is true.

    Both halves of `timeoutOf` were invisible while no seeded plan named a
    ceiling: `return DEFAULT_TIMEOUT` unconditionally drew the same 900 and
    posted the same 900. This step names 120, which is smaller, so the plan's
    own number is what a person reads and what the body carries.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, CEILING_RUN)

        assert _fact(page, f"propose:{LONE}", "Longest this may run") == (
            f"{NODE_CEILING}s")
        assert "whichever is smaller" in page.locator(
            f'[data-step="propose:{LONE}"]').inner_text()

        _drive(page, window, node=LONE)
        _settled(page, LONE)

        assert window.posted("/proposals")[0][
            "timeout_seconds"] == NODE_CEILING
        assert bench.records(CEILING_RUN, "action_request")[0].timeout_seconds \
            == NODE_CEILING
    finally:
        assert window.problems == []
        page.context.close()
