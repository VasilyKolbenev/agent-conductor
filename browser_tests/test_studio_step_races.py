"""Three races on the Runs screen's step controls, each held open with a
route and released on purpose.

R07 of the review of ``8dec0e4``, A and B, and the owner's third control C:

- **A. a read under a pending write.** The write flag lived on the draft and a
  landed read turned it off, so *Read run* pressed while a proposal was still
  on the wire gave the control back, and a second press wrote a second durable
  proposal. The same for Confirm, where only the server's idempotency stood
  between a person and a second execution.
- **B. one step's answer and another step's words.** The accepted road cleared
  the whole draft, so alpha's answer landing while a person typed into omega
  emptied omega's fields.
- **C. ownership across navigation.** A write in flight for run A must stay
  A's while the person opens run B and comes back: a map cleared on the change
  of run would hand the control back and admit a second write.

The rule under all three is one shape: a write in flight is a fact about ONE
step of ONE run, kept apart from the draft, and only the write's own end takes
it away; the accepted road spends only the draft it was minted from. Every
POST is counted on the wire and every record in the journal, because a control
that merely looked shut could still have written.

The bench, the seeded runs and the page helpers are `test_studio_step.py`'s
and are imported; the gate runs every module in its own process.
"""
from __future__ import annotations

from playwright.sync_api import Browser, Page

from conductor.command.run_store import RunStore

from browser_tests.test_studio_step import (  # noqa: F401
    ACTOR,
    DIGEST,
    DONE_RUN,
    HALTING,
    LONE,
    RUN_ID,
    STEP,
    WHY,
    _Bench,
    _open,
    _open_run,
    _read,
    _review,
    _two_steps,
    _type,
    bench,
)
from browser_tests.test_studio_step_offers import _type_into
from tests.test_command_graph_projection import a_proposal

#: A plan of two independent steps, both runnable at once.
TWO_LIVE = "run-two-live"
#: The sentence the shut control carries while its own write is in flight.
WRITING = "Writing… this control is shut until the server answers"


def _hold(page: Page, run_id: str, target: str) -> list:
    """Hold every POST to one route of one run; the list is what was held."""
    held: list = []
    page.route(f"**/command/runs/{run_id}/{target}",
               lambda route: held.append(route))
    return held


def _press_and_hold(page: Page, key: str, run_id: str, target: str) -> list:
    """Press one control and wait until its POST is on the wire, held.

    The press shuts the control at once, but the request leaves only after
    the window has read its session -- so the wire is waited on, never the
    button: a count taken off the button alone measured nothing.
    """
    held = _hold(page, run_id, target)
    with page.expect_request(lambda request: request.method == "POST"
                             and request.url.endswith(f"/{target}")):
        page.locator(f'[data-focus-key="{key}"]').click()
    # The request event lands before the route handler has run: the handler
    # runs on the connection's next turn, which a bounded wait hands it.
    for _ in range(40):
        if held:
            break
        page.wait_for_timeout(25)
    assert len(held) == 1, held
    assert _state_of(page, key) == "shut"
    return held


def _release(held: list) -> None:
    for route in held:
        route.continue_()


def _unhold(page: Page, run_id: str, target: str) -> None:
    """Stop holding that route: a later POST to it must reach the server."""
    page.unroute(f"**/command/runs/{run_id}/{target}")


def _state_of(page: Page, key: str) -> str:
    """`open`, `shut` or `gone`: what a press on this control could do."""
    return page.evaluate(
        "key => { const b = document.querySelector(`[data-focus-key='${key}']`);"
        " return b === null ? 'gone' : (b.disabled ? 'shut' : 'open'); }", key)


def _press_anyway(page: Page, key: str) -> None:
    """Force a press on a control that reads shut.

    A disabled button fires no click and no submit, so what this proves is
    on the wire afterwards: a synthesized press that reached the handler would
    be a second POST.
    """
    page.locator(f'[data-focus-key="{key}"]').click(
        force=True, no_wait_after=True, timeout=3000)


def _a_read_lands(page: Page, bench: _Bench, run_id: str, index: int) -> None:
    """Provoke a read of this run and PROVE it landed.

    A record on ANOTHER step is appended first and the timeline is waited on
    to grow, exactly as `test_a_read_of_the_same_run_leaves_the_words…` does:
    without the wait, every assertion after this would be about the DOM the
    person was already looking at.
    """
    before = page.locator("ol.studio-timeline > li").count()
    RunStore(bench.root).append(a_proposal(
        node_id="identify", index=index, run_id=run_id, config_digest=DIGEST))
    page.locator(f'[data-focus-key="run:{run_id}"]').click()
    page.wait_for_function(
        "n => document.querySelectorAll('ol.studio-timeline > li').length > n",
        arg=before)


def _durable_on(bench: _Bench, run_id: str, kind: str, node_id: str) -> int:
    return len([row for row in bench.records(run_id, kind)
                if row.node_id == node_id])


# -- A. a read under a pending write -------------------------------------------


def _a_held_write_survives_a_read(page: Page, window, bench: _Bench, *,
                                  key: str, target: str, index: int) -> None:
    """Press, hold the POST, let a real read land, force a second press.

    The control drawn by the read is STILL shut, says so, and the forced
    press reaches no wire; then the one held request is released.
    """
    held = _press_and_hold(page, key, RUN_ID, target)
    _a_read_lands(page, bench, RUN_ID, index=index)
    assert _state_of(page, key) == "shut"
    assert WRITING in page.locator(f'[data-step="{key}"]').inner_text()
    _press_anyway(page, key)
    assert window.writes(f"/{target}") == 1 and len(held) == 1
    _release(held)


def test_a_read_landing_under_a_pending_write_leaves_the_control_shut(
        chromium: Browser, bench: _Bench) -> None:
    """R07A, both halves of the road: one proposal, then one request.

    The proposal is held on the wire; a real read of the same run lands and
    replaces the form; the control drawn by that read is STILL shut, says so,
    and a forced press reaches no wire. Released, exactly one proposal stands.
    The Confirm half repeats it: one request, one result -- the server's
    idempotency is no longer the only thing between a person and a second
    execution.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        _a_held_write_survives_a_read(page, window, bench, key=f"propose:{STEP}",
                                      target="proposals", index=41)
        page.wait_for_selector(f'[data-focus-key="confirm:{STEP}"]')
        assert _durable_on(bench, RUN_ID, "action_proposal", STEP) == 1

        _type(page, "field:confirmed_by", ACTOR)
        _a_held_write_survives_a_read(page, window, bench, key=f"confirm:{STEP}",
                                      target="actions", index=42)
        page.wait_for_function(
            "() => [...document.querySelectorAll('ol.studio-timeline > li')]"
            ".some(item => item.innerText.includes('action_result'))",
            timeout=20000)
        assert _durable_on(bench, RUN_ID, "action_request", STEP) == 1
        assert len(bench.records(RUN_ID, "action_result")) == 1
    finally:
        assert window.problems == []
        page.context.close()


# -- B. one step's answer and another step's words -----------------------------


def test_one_steps_accepted_write_leaves_another_steps_unsent_words_alone(
        chromium: Browser, bench: _Bench) -> None:
    """R07B: alpha's answer lands while a person is typing into omega.

    Alpha's proposal is held; omega's two fields are typed; alpha is released
    and its Confirm appears. Omega's words are still there, and the POST
    omega then makes carries omega's words -- not alpha's, not none.
    """
    store = RunStore(bench.root)
    _open_run(store, TWO_LIVE)
    store.append(_two_steps(TWO_LIVE, (_review(LONE), _review(HALTING))))
    page, window = _open(chromium, bench)
    try:
        _read(page, TWO_LIVE)
        _type_into(page, LONE, "proposed_by", "alice")
        _type_into(page, LONE, "rationale", "First step")
        held = _press_and_hold(page, f"propose:{LONE}", TWO_LIVE, "proposals")
        # One press shuts ONE step: omega's form carries no writing sentence
        # while alpha's write is in flight, and once its two facts are typed
        # its control is open -- a person can press it, and the shut one is
        # alpha's alone.
        omega = page.locator(f'[data-step="propose:{HALTING}"]')
        assert WRITING not in omega.inner_text(), omega.inner_text()
        _type_into(page, HALTING, "proposed_by", "bob")
        _type_into(page, HALTING, "rationale", "Do not discard these words")
        assert _state_of(page, f"propose:{HALTING}") == "open"
        assert _state_of(page, f"propose:{LONE}") == "shut"
        assert len(held) == 1, held

        _release(held)
        _unhold(page, TWO_LIVE, "proposals")
        page.wait_for_selector(f'[data-step="confirm:{LONE}"]')
        assert omega.locator('[name="proposed_by"]').input_value() == "bob"
        assert omega.locator('[name="rationale"]').input_value() == (
            "Do not discard these words")
        assert _state_of(page, f"propose:{HALTING}") == "open"

        with page.expect_response(
                lambda answer: answer.url.endswith("/proposals")) as waited:
            page.locator(f'[data-focus-key="propose:{HALTING}"]').click()
        assert waited.value.status == 201, waited.value.json()
        posted = window.posted("/proposals")
        assert [row["proposed_by"] for row in posted] == ["alice", "bob"], posted
        assert posted[1]["rationale"] == "Do not discard these words", posted
        assert posted[1]["node_id"] == HALTING
    finally:
        assert window.problems == []
        page.context.close()


# -- C. ownership across navigation --------------------------------------------


def test_a_write_in_flight_stays_its_runs_own_while_another_run_is_opened(
        chromium: Browser, bench: _Bench) -> None:
    """The owner's control: hold A's POST, open B, come back to A, press.

    The control on A is still shut -- the write's ownership is keyed by run
    and step and no change of run touches it -- and a forced press reaches no
    wire. Released, A holds exactly one proposal.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        held = _press_and_hold(page, f"propose:{STEP}", RUN_ID, "proposals")

        _read(page, DONE_RUN)
        _read(page, RUN_ID)
        assert _state_of(page, f"propose:{STEP}") == "shut"
        assert WRITING in page.locator(f'[data-step="propose:{STEP}"]').inner_text()
        _press_anyway(page, f"propose:{STEP}")
        assert window.writes("/proposals") == 1 and len(held) == 1

        _release(held)
        page.wait_for_selector(f'[data-focus-key="confirm:{STEP}"]')
        assert _durable_on(bench, RUN_ID, "action_proposal", STEP) == 1
        assert bench.kinds() == ["graph_definition", "action_proposal"]
    finally:
        assert window.problems == []
        page.context.close()
