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

Four more, from the slice-3 review of that fix:

- **D. words typed under a pending write.** The generation moved only on a
  choice or a clearing, so a name typed into the Confirm form the proposal's
  own frame drew -- while its answer was still on the wire -- was spent by that
  answer as "the draft this write was minted from".
- **E. the answer lands before its read.** The accepted write's entry left the
  map the moment the server answered, so the control was redrawn over the
  stale screen; it stayed shut only because the spent draft left a required
  field empty, and a draft NOT spent (D) would have opened it to a second
  press.
- **F. a sibling write retired the first.** One module-wide counter retired
  alpha's answer when omega's write began: a refusal that should have re-read
  the run said nothing at all.
- **H. a read this build cannot project.** A landed read of the SAME run that
  the projection refuses was treated as another run's, and both drafts were
  cleared on an error road.

The bench, the seeded runs and the page helpers are `test_studio_step.py`'s
and are imported; the gate runs every module in its own process.
"""
from __future__ import annotations

import json

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


# -- D. words typed under a pending write --------------------------------------


def _park_the_answer(page: Page, run_id: str, target: str) -> list:
    """Let every POST to one route REACH the server, and park its answer.

    The request lands -- the journal grows and the frame goes out -- so the
    window redraws from the read that frame buys while the write it made is
    still, from the window's side, on the wire.
    """
    parked: list = []
    page.route(f"**/command/runs/{run_id}/{target}",
               lambda route: parked.append((route, route.fetch())))
    return parked


def _release_parked(page: Page, run_id: str, target: str, parked: list) -> None:
    """Hand the parked answers over, then stop holding the route.

    In that order: a route un-routed while its request is still parked is
    handled by the un-routing, and a fulfil after that is refused.
    """
    for route, answer in parked:
        route.fulfill(response=answer)
    page.unroute(f"**/command/runs/{run_id}/{target}")


def _wait_until_open(page: Page, key: str) -> None:
    page.wait_for_function(
        "key => { const b = document.querySelector(`[data-focus-key='${key}']`);"
        " return b !== null && !b.disabled; }", arg=key, timeout=15000)


def test_words_typed_under_a_pending_write_survive_its_answer(
        chromium: Browser, bench: _Bench) -> None:
    """D: the proposal's answer is parked; its frame draws the Confirm form.

    The person types who confirms into that form while the proposal's own
    write is still in flight. When the answer lands, the words are still
    there, the control opens once the run is read again, and the request
    then written carries exactly those words.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        parked = _park_the_answer(page, RUN_ID, "proposals")
        page.locator(f'[data-focus-key="propose:{STEP}"]').click()
        page.wait_for_selector(f'[data-step="confirm:{STEP}"]', timeout=15000)
        assert parked, "the proposal never reached the server"
        form = page.locator(f'[data-step="confirm:{STEP}"]')
        assert _state_of(page, f"confirm:{STEP}") == "shut"
        assert WRITING in form.inner_text()
        _type(page, "field:confirmed_by", ACTOR)
        _release_parked(page, RUN_ID, "proposals", parked)
        _wait_until_open(page, f"confirm:{STEP}")
        assert form.locator('[name="confirmed_by"]').input_value() == ACTOR
        assert WRITING not in form.inner_text()

        with page.expect_response(
                lambda answer: answer.url.endswith("/actions")) as waited:
            page.locator(f'[data-focus-key="confirm:{STEP}"]').click()
        assert waited.value.status == 201, waited.value.json()
        assert window.posted("/actions")[0]["confirmed_by"] == ACTOR
        assert window.writes("/proposals") == 1
    finally:
        assert window.problems == []
        page.context.close()


# -- E. the answer lands before its read ---------------------------------------


def _hold_reads(page: Page, run_id: str) -> list:
    """Hold every read of one run; the list is what was held."""
    held: list = []
    page.route(f"**/command/runs/{run_id}", lambda route: held.append(route))
    return held


def _release_reads(page: Page, run_id: str, held: list) -> None:
    for route in held:
        route.continue_()
    page.unroute(f"**/command/runs/{run_id}")


def test_an_accepted_write_keeps_its_control_shut_until_the_run_is_read_again(
        chromium: Browser, bench: _Bench) -> None:
    """E: the POST is answered, the read it provokes is held.

    Between the two the screen is stale: the step still reads runnable and
    the words are still typed. The control is shut and says so, a forced
    press reaches no wire, and the read's landing is what opens the road on
    -- which is the sentence the shut control has always made.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        held = _press_and_hold(page, f"propose:{STEP}", RUN_ID, "proposals")
        reads = _hold_reads(page, RUN_ID)
        _release(held)
        _unhold(page, RUN_ID, "proposals")
        for _ in range(200):
            if reads:
                break
            page.wait_for_timeout(25)
        assert reads, "the answer provoked no read"
        page.wait_for_timeout(300)
        assert _state_of(page, f"propose:{STEP}") == "shut"
        assert WRITING in page.locator(f'[data-step="propose:{STEP}"]').inner_text()
        _press_anyway(page, f"propose:{STEP}")
        assert window.writes("/proposals") == 1

        _release_reads(page, RUN_ID, reads)
        page.wait_for_selector(f'[data-step="confirm:{STEP}"]')
        assert _durable_on(bench, RUN_ID, "action_proposal", STEP) == 1
    finally:
        assert window.problems == []
        page.context.close()


# -- F. a sibling write and the first's answer -----------------------------------


def _hold_the_first(page: Page, run_id: str, target: str) -> list:
    """Hold only the FIRST POST to one route; every later one goes through."""
    held: list = []

    def first_only(route) -> None:
        if held:
            route.continue_()
        else:
            held.append(route)

    page.route(f"**/command/runs/{run_id}/{target}", first_only)
    return held


def test_a_sibling_steps_write_does_not_retire_the_first_steps_answer(
        chromium: Browser, bench: _Bench) -> None:
    """F: alpha's POST is held; omega's is pressed and answered 201.

    Alpha's answer then comes back as a refusal of the kind that asks for a
    re-read. The window says so and reads the run again: a second write on
    another step is permitted by design and retires nothing.
    """
    store = RunStore(bench.root)
    _open_run(store, TWO_LIVE)
    store.append(_two_steps(TWO_LIVE, (_review(LONE), _review(HALTING))))
    page, window = _open(chromium, bench)
    try:
        _read(page, TWO_LIVE)
        held = _hold_the_first(page, TWO_LIVE, "proposals")
        _type_into(page, LONE, "proposed_by", "alice")
        _type_into(page, LONE, "rationale", "First step")
        with page.expect_request(lambda request: request.method == "POST"
                                 and request.url.endswith("/proposals")):
            page.locator(f'[data-focus-key="propose:{LONE}"]').click()
        for _ in range(40):
            if held:
                break
            page.wait_for_timeout(25)
        assert len(held) == 1, held
        _type_into(page, HALTING, "proposed_by", "bob")
        _type_into(page, HALTING, "rationale", "Second step")
        with page.expect_response(
                lambda answer: answer.url.endswith("/proposals")) as waited:
            page.locator(f'[data-focus-key="propose:{HALTING}"]').click()
        assert waited.value.status == 201, waited.value.json()
        page.wait_for_selector(f'[data-step="confirm:{HALTING}"]')

        held[0].fulfill(status=409, content_type="application/json",
                        body=json.dumps({"error": {"code": "service_refused",
                                                   "message": "held by the test"}}))
        page.wait_for_function(
            "() => document.getElementById('studioStatus').innerText"
            ".includes('the run was read again')", timeout=15000)
        assert _state_of(page, f"propose:{LONE}") == "shut"
        assert WRITING not in page.locator(f'[data-step="propose:{LONE}"]').inner_text()
        assert window.writes("/proposals") == 2
        assert [row.node_id for row in bench.records(TWO_LIVE, "action_proposal")] == [
            HALTING]
    finally:
        # The 409 is this test's own, and the browser notes every non-2xx
        # answer on its console; that note is not a fault in the window.
        assert [row for row in window.console_errors if "409" not in row] == []
        assert window.page_errors == []
        page.context.close()


# -- G. the caret, across a frame ------------------------------------------------

#: A frame from ANOTHER writer, without touching the page: a document is
#: published into the first run from page script, and the `run` frame the
#: route emits buys every window a read of the run list -- a render, with
#: the caret wherever it was.
A_DOCUMENT_FROM_ELSEWHERE = """async ([run, id]) => {
  const s = await (await fetch('/command/session', {cache: 'no-store'})).json();
  const r = await fetch(`/command/runs/${encodeURIComponent(run)}/artifacts`, {
    method: 'POST', headers: {'Content-Type': 'application/json',
      'X-Conduct-CSRF': s.csrf_token},
    body: JSON.stringify({artifact_id: id, artifact_ref: 'artifact-brief',
      media_type: 'text/plain', content: 'a frame, nothing more'})});
  return r.status;
}"""
READS_OF_THE_LIST = ("() => performance.getEntriesByType('resource')"
                     ".filter(e => e.name.endsWith('/command/runs')).length")
THE_FORM_IN_FOCUS = ("() => { const a = document.activeElement;"
                     " const f = a && a.closest ? a.closest('[data-step]') : null;"
                     " return f === null ? null : f.getAttribute('data-step'); }")


def _a_frame_from_elsewhere(page: Page, artifact_id: str) -> None:
    before = page.evaluate(READS_OF_THE_LIST)
    assert page.evaluate(A_DOCUMENT_FROM_ELSEWHERE, [RUN_ID, artifact_id]) == 201
    page.wait_for_function(f"n => ({READS_OF_THE_LIST})() > n", arg=before)
    page.wait_for_timeout(300)


def test_a_frame_leaves_the_caret_in_the_form_it_was_in(
        chromium: Browser, bench: _Bench) -> None:
    """G: two runnable steps draw two `proposed_by` fields under one key.

    The caret is left mid-word in omega's; a frame from another writer
    redraws the screen. Focus is restored WITHIN omega's form -- not to the
    first control carrying the key, which is alpha's -- so the next letters
    land in omega and alpha stays empty. Restored to alpha, the tail of the
    word went there and alpha's change re-chose the draft, emptying omega.
    """
    store = RunStore(bench.root)
    _open_run(store, TWO_LIVE)
    store.append(_two_steps(TWO_LIVE, (_review(LONE), _review(HALTING))))
    page, window = _open(chromium, bench)
    try:
        _read(page, TWO_LIVE)
        omega = page.locator(f'[data-step="propose:{HALTING}"] [name="proposed_by"]')
        alpha = page.locator(f'[data-step="propose:{LONE}"] [name="proposed_by"]')
        omega.click()
        page.keyboard.type("bo")
        assert page.evaluate(THE_FORM_IN_FOCUS) == f"propose:{HALTING}"
        _a_frame_from_elsewhere(page, "artifact-brief-from-elsewhere")
        assert page.evaluate(THE_FORM_IN_FOCUS) == f"propose:{HALTING}"
        assert omega.input_value() == "bo"
        page.keyboard.type("b")
        page.keyboard.press("Tab")
        assert omega.input_value() == "bob"
        assert alpha.input_value() == ""
        assert window.writes("/proposals") == 0
    finally:
        assert window.problems == []
        page.context.close()


# -- H. a read this build cannot project -----------------------------------------


def test_a_read_the_projection_refuses_leaves_the_words_alone(
        chromium: Browser, bench: _Bench) -> None:
    """H: the same run answers with a body the projection refuses.

    The screen says so; the words typed against the run are still there when
    the next read lands -- an error road is not a change of run.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        _type(page, "field:proposed_by", ACTOR)
        _type(page, "field:rationale", WHY)
        page.route(f"**/command/runs/{RUN_ID}", lambda route: route.fulfill(
            status=200, content_type="application/json", body="{}"))
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        page.wait_for_function(
            "() => document.body.innerText.includes("
            "'a payload this build cannot read')")
        page.unroute(f"**/command/runs/{RUN_ID}")
        page.locator(f'[data-focus-key="run:{RUN_ID}"]').click()
        page.wait_for_selector(f'[data-step="propose:{STEP}"]')
        form = page.locator(f'[data-step="propose:{STEP}"]')
        assert form.locator('[name="proposed_by"]').input_value() == ACTOR
        assert form.locator('[name="rationale"]').input_value() == WHY
        assert window.writes("/proposals") == 0
    finally:
        assert window.problems == []
        page.context.close()
