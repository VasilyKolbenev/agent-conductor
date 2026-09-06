"""WHICH rows the Runs screen offers a step control, and what the rest say.

Split out of ``browser_tests/test_studio_step.py`` when that module reached the
project's line cap, along the seam its own section headers already drew. That
module drives the ROAD -- propose, confirm, the records that follow, and what
the two bodies carried. This one asks the other question, which fails in
completely different ways: of the eight rows a person is looking at, which one
carries a control, and does every row that carries none say why.

The four circuits here:

- the four ordinary ways to not be runnable: waiting on a road, finished with,
  closed by a branch not taken, and an attempt that has not answered;
- a halt and an unanswered attempt, which are the same `blocked` row with the
  same empty roads and the same `observed` phase, and are opposite facts;
- three journals whose runtime PHASE says three different things about one
  fact, which is why the phase is not what decides it;
- and the front door, where the control is drawn and SHUT because this machine
  resolved no provider.

The bench, the seeded runs and the page helpers stay next door and are imported:
seven runs described in one place. The gate runs every module in its own
process, so nothing about that import is shared state.
"""
from __future__ import annotations

from playwright.sync_api import Browser

from conductor.command.run_store import RunStore

from browser_tests.test_studio_demo import demo_url  # noqa: F401
from browser_tests.test_studio_lifecycle import STUDIO_CONFIG, _Window, _settle
from browser_tests.test_studio_step import (  # noqa: F401
    ACTOR,
    CLOSED_RUN,
    DIGEST,
    DONE_RUN,
    FLIGHT_RUN,
    HALTED_RUN,
    LONE,
    OBSERVED_RUN,
    RESTALE_RUN,
    RUN_ID,
    STEP,
    WHY,
    _Bench,
    _fact,
    _offered,
    _one_attempt,
    _open,
    _open_run,
    _read,
    _review,
    _row,
    _two_steps,
    bench,
)
from tests.test_command_run_store import a_run


def test_a_step_the_plan_does_not_call_runnable_is_offered_no_control_and_says_why(
        chromium: Browser, bench: _Bench) -> None:
    """Four ways to not be runnable, four sentences, and no control anywhere.

    The offer rule is the server's schedule and nothing weaker, so this walks
    the four rows a person really meets: waiting on a road, finished with,
    closed by a branch not taken, and an attempt that has not answered. Each
    says its own reason -- a shut control with no sentence teaches a person the
    product is broken.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, RUN_ID)
        assert _offered(page) == [f"propose:{STEP}"], _offered(page)
        waiting = _row(page, "identify")
        assert "plan: blocked" in waiting, waiting
        assert "ALL incoming roads must open" in waiting, waiting
        assert "Waiting on" in waiting and "goal" in waiting

        _read(page, DONE_RUN)
        assert _offered(page) == ["propose:identify"], _offered(page)
        finished = _row(page, STEP)
        assert "plan: settled" in finished, finished
        assert ("This step has settled; the plan offers it no further attempt "
                "unless a loop reopens it.") in finished, finished

        _read(page, CLOSED_RUN)
        assert _offered(page) == [], _offered(page)
        closed = _row(page, "do")
        assert "plan: unreachable" in closed, closed
        # The whole sentence, naming the road that closed. The `or` this
        # replaced could not fail: its right half was a substring of its left.
        assert ("No run reaches this step: confirm-gate took another road."
                ) in closed, closed

        _read(page, FLIGHT_RUN)
        assert _offered(page) == [], _offered(page)
        flying = _row(page, STEP)
        assert "plan: blocked" in flying, flying
        assert ("An attempt on this step is still in flight; the plan offers "
                "it again only after that attempt answers.") in flying, flying
    finally:
        assert window.problems == []
        page.context.close()


def test_a_halt_and_an_unanswered_attempt_are_told_apart_by_the_records(
        chromium: Browser, bench: _Bench) -> None:
    """The two blocked rows that look identical, and what separates them.

    They agree on everything the screen used to read: state `blocked`, no road,
    no awaited document, attempts not spent, and a runtime phase of `observed`.
    One is a worker still running. One is a run that has STOPPED, whose step
    answered `unknown` -- which settles nothing, because an unanswered question
    stays askable -- and was then rewritten to blocked by a halt on another
    branch.

    Reading the phase alone said "still in flight" about the second, which is
    the reverse of the truth: the run's own word is `stalled` and nothing is
    ever coming. Both rows are read here so neither sentence can be reached by
    accident.
    """
    page, window = _open(chromium, bench)
    try:
        _read(page, HALTED_RUN)
        assert _offered(page) == [], _offered(page)
        stopped = _row(page, LONE)

        assert "plan: blocked" in stopped, stopped
        assert "Nothing further is offered in this run: it was halted." in (
            stopped), stopped
        assert "still in flight" not in stopped, stopped
        # The run itself says so, in the word the schedule computed.
        assert "stalled" in page.locator("#bodyRuns").inner_text()

        # …and the row that really IS in flight still says it is.
        _read(page, FLIGHT_RUN)
        assert "still in flight" in _row(page, STEP)
    finally:
        assert window.problems == []
        page.context.close()


def test_an_unanswered_attempt_is_read_from_the_records_and_not_from_the_phase(
        chromium: Browser, bench: _Bench) -> None:
    """Three journals whose runtime PHASE says three different things.

    The phase reports how far a node's CURRENT action got, and
    `graph_projection._current_action` is the LAST proposal or request naming
    it. So the same fact -- a worker executing right now -- reads `requested`,
    `observed`, or, once a stale second window appends a proposal over the
    unanswered request, `proposed`. `POST /proposals` holds no schedule check,
    so that last journal is one any caller can write.

    A phase reader answered the third one "Nothing further is offered in this
    run: it was halted" about an open run with a live worker. All three say the
    same true sentence now, because the question is asked of the RECORDS: a
    request naming this step that no result closes.
    """
    page, window = _open(chromium, bench)
    try:
        for run_id, step in ((FLIGHT_RUN, STEP), (OBSERVED_RUN, LONE),
                             (RESTALE_RUN, LONE)):
            _read(page, run_id)
            said = _row(page, step)
            assert "plan: blocked" in said, (run_id, said)
            assert ("An attempt on this step is still in flight; the plan "
                    "offers it again only after that attempt answers.") in said, (
                run_id, said)
            assert "was halted" not in said, (run_id, said)
            # And no control: an attempt is outstanding, so the schedule offers
            # this step nothing whatever its phase reads.
            assert _offered(page) == [], (run_id, _offered(page))
    finally:
        assert window.problems == []
        page.context.close()


# -- 5. an attempt id that fits, whatever the step is called -------------------


def fnv64(text: str) -> str:
    """FNV-1a, 64 bits, over UTF-8 -- the reference the window's digest is held to.

    Spelled here independently of `studio-runstep.js`: a window that changed
    its hash would mint a different DIGEST form and this test would name a
    twin that is no longer a twin, so the two implementations pin each other.
    """
    digest = 0xcbf29ce484222325
    for byte in text.encode("utf-8"):
        digest ^= byte
        digest = (digest * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return f"{digest:016x}"


#: A step whose name fits the named form with room for one digit, one that
#: fills the whole budget, and a step literally NAMED as the second one's
#: digest -- the collision the revision-1 design admitted and this one refuses
#: by construction.
FITS = "m" * 118
FULL = "n" * 128
TWIN = fnv64(FULL)
LONG_RUN = "run-long-ids"
COUNTED_RUN = "run-digest-counted"


def _type_into(page, step: str, field: str, value: str) -> None:
    """Type into ONE step form's field the way a person does, and commit it.

    Scoped to the form, because three runnable steps draw three `proposed_by`
    fields; and typed by KEYSTROKE rather than filled, because a read landing
    between a fill and its blur discards the filled value (measured: the
    studio_modes stall), while typed characters survive the re-render.
    """
    control = page.locator(f'[data-step="propose:{step}"] [name="{field}"]')
    control.click()
    page.keyboard.type(value)
    page.keyboard.press("Tab")


def test_a_step_whose_name_fills_the_id_budget_is_proposed_beside_its_digest_twin(
        chromium: Browser, bench: _Bench) -> None:
    """R09 of the review of `8dec0e4`, made a test, and its collision closed.

    `attempt-<node>-<n>` spent the node's own name inside the 128 the contract
    allows, so a node of 119 characters was refused `contract_invalid` at the
    boundary while `GraphNode` and the plan both admitted the name. The window
    now mints a DIGEST form for a name that does not fit -- and the digest form
    begins `attempt.` where the named form begins `attempt-`, so a step
    literally named as another step's digest (the revision-1 collision) mints
    a different id. Three steps, three proposals, three distinct ids, all 201.
    """
    store = RunStore(bench.root)
    _open_run(store, LONG_RUN)
    store.append(_two_steps(
        LONG_RUN, (_review(FITS), _review(FULL), _review(TWIN))))
    expected = {FITS: f"attempt-{FITS}-0", FULL: f"attempt.{TWIN}-0",
                TWIN: f"attempt-{TWIN}-0"}
    page, window = _open(chromium, bench)
    try:
        _read(page, LONG_RUN)
        for step in (FITS, FULL, TWIN):
            records = len(RunStore(bench.root).read(LONG_RUN).records)
            page.wait_for_function(
                "n => document.querySelectorAll('ol.studio-timeline > li')"
                ".length === n", arg=records)
            assert _fact(page, f"propose:{step}", "Attempt id") == expected[step]
            _type_into(page, step, "proposed_by", ACTOR)
            _type_into(page, step, "rationale", WHY)
            with page.expect_response(
                    lambda answer: answer.url.endswith("/proposals")) as waited:
                page.locator(f'[data-focus-key="propose:{step}"]').click()
            assert waited.value.status == 201, (len(step), waited.value.json())
            page.wait_for_selector(f'[data-focus-key="confirm:{step}"]')

        posted = [row["attempt_id"] for row in window.posted("/proposals")]
        assert posted == [expected[FITS], expected[FULL], expected[TWIN]], posted
        assert len(set(posted)) == 3
        assert all(len(name) <= 128 for name in posted), posted
        durable = [row.attempt_id for row in
                   bench.records(LONG_RUN, "action_proposal")]
        assert durable == posted, durable
    finally:
        assert window.problems == []
        page.context.close()


def test_the_counter_is_read_under_both_forms_of_one_step(
        chromium: Browser, bench: _Bench) -> None:
    """An attempt already spent under the DIGEST form is counted PAST, not filled in.

    The step that fills the budget already carries `attempt.<digest>-1` -- with
    no `-0` before it, the gap shape `run-lap` seeds for the named form --
    answered `unknown` so it stays runnable. The next id must be `-2`: the
    greatest counter already spelled under this form plus one. A scan that read
    only the named form would find nothing, start at 0, and hand out the FIRST
    FREE id instead -- `-0`, which no earlier attempt holds -- so a free-id
    check alone cannot tell the two rules apart; the seeded gap can.
    """
    store = RunStore(bench.root)
    _open_run(store, COUNTED_RUN)
    store.append(_two_steps(COUNTED_RUN, (_review(FULL),)))
    _one_attempt(store, COUNTED_RUN, FULL, index=91,
                 attempt_id=f"attempt.{TWIN}-1", outcome="unknown")
    page, window = _open(chromium, bench)
    try:
        _read(page, COUNTED_RUN)
        assert _fact(page, f"propose:{FULL}", "Attempt id") == f"attempt.{TWIN}-2"
        _type_into(page, FULL, "proposed_by", ACTOR)
        _type_into(page, FULL, "rationale", WHY)
        with page.expect_response(
                lambda answer: answer.url.endswith("/proposals")) as waited:
            page.locator(f'[data-focus-key="propose:{FULL}"]').click()
        assert waited.value.status == 201, waited.value.json()

        assert window.posted("/proposals")[0]["attempt_id"] == f"attempt.{TWIN}-2"
    finally:
        assert window.problems == []
        page.context.close()


# -- 6. the front door ---------------------------------------------------------


def test_the_demo_offers_the_step_but_says_this_build_serves_no_adapter(
        chromium: Browser, demo_url: str) -> None:
    """`conduct demo` resolves no provider, and the screen says which pair.

    The control is DRAWN and shut rather than absent. A person meeting an empty
    row learns that this product cannot drive a step; a person meeting a shut
    one with this sentence learns that this MACHINE has no provider for it,
    which is a configuration they can go and fix.
    """
    context = chromium.new_context(viewport={"width": 1700, "height": 1400})
    page = context.new_page()
    window = _Window(page)
    try:
        page.goto(demo_url, wait_until="load")
        _settle(page)
        page.locator("#navRuns").click()
        page.wait_for_selector("#screenRuns:not([hidden])")
        page.locator('[data-focus-key^="run:"]').first.click()
        page.wait_for_selector("ul.studio-positions")

        control = page.locator(f'[data-focus-key="propose:{STEP}"]')
        assert control.count() == 1, _offered(page)
        assert control.is_disabled()
        said = page.locator(f'[data-step="propose:{STEP}"]').inner_text()
        assert "This build serves no adapter for" in said, said
        assert "demo-implementer/review" in said, said
        assert "The step is offered and the control is shut." in said, said
    finally:
        assert window.problems == []
        context.close()


# -- 7. the run's authority ----------------------------------------------------

#: One plan of one step, opened under each word of the authority ladder. R06 of
#: the review of `8dec0e4`: the controls read the schedule and never the run's
#: `mode`, so an observe run offered a Propose the server refused and a propose
#: run offered a Confirm it refused, each under a sentence sending a person to
#: a plan that had not moved.
MODE_RUNS = {mode: f"run-mode-{mode}"
             for mode in ("observe", "propose", "policy", "confirm")}


def _open_run_under(store: RunStore, run_id: str, mode: str) -> None:
    """`_open_run`, with the authority chosen rather than always `confirm`."""
    store.create_run(
        a_run(run_id=run_id, mode=mode, config_digest=DIGEST), STUDIO_CONFIG)
    store.append(_two_steps(run_id, (_review(LONE),)))


def _propose(page, step: str) -> int:
    """Type the two facts, press Propose, and answer with the wire's status."""
    _type_into(page, step, "proposed_by", ACTOR)
    _type_into(page, step, "rationale", WHY)
    with page.expect_response(
            lambda answer: answer.url.endswith("/proposals")) as waited:
        page.locator(f'[data-focus-key="propose:{step}"]').click()
    return waited.value.status


def _row_says(page, node: str, sentence: str) -> None:
    """Wait until this step's row carries the sentence.

    The read that follows a write is what draws it, so it is waited for as a
    signal rather than read off the screen the press left behind.
    """
    page.wait_for_function(
        "([id, said]) => [...document.querySelectorAll('li.studio-position')]"
        ".some(item => item.innerText.includes(id + ' \\u00b7 ') "
        "&& item.innerText.includes(said))", arg=[node, sentence])


def test_the_controls_offer_only_what_the_runs_frozen_authority_permits(
        chromium: Browser, bench: _Bench) -> None:
    """Observe is offered nothing; propose and policy a proposal and no
    Confirm; confirm both -- and every withheld control says where the
    authority is granted.

    The confirm run is the positive control: a rule that read the mode and
    shut too much would pass the three rows above it and fail here. What the
    two lesser authorities write is checked in the journal, because the
    server admits their proposals (201): the record is real and what the
    screen says about it -- durable, carried out by nothing here -- is true.
    """
    store = RunStore(bench.root)
    for mode, run_id in MODE_RUNS.items():
        _open_run_under(store, run_id, mode)
    page, window = _open(chromium, bench)
    try:
        # observe: no control at all, one sentence, and nothing on the wire.
        _read(page, MODE_RUNS["observe"])
        assert _offered(page) == [], _offered(page)
        row = _row(page, LONE)
        assert "This run's authority is observe: nothing may be proposed" in row
        assert "Open a run form on the Workflow screen" in row, row
        assert window.writes("/proposals") == 0
        # propose and policy: a proposal the server admits, then no Confirm.
        for mode in ("propose", "policy"):
            _read(page, MODE_RUNS[mode])
            assert _offered(page) == [f"propose:{LONE}"], (mode, _offered(page))
            form = page.locator(f'[data-step="propose:{LONE}"]').inner_text()
            assert f"In a {mode} run a proposal is a durable record" in form
            assert _propose(page, LONE) == 201, mode
            _row_says(page, LONE, "nothing can confirm it here")
            assert _offered(page) == [], (mode, _offered(page))
            row = _row(page, LONE)
            assert f"this run's authority is {mode}" in row, row
            assert "Open a run form on the Workflow screen" in row, row
            assert bench.kinds(MODE_RUNS[mode]) == [
                "graph_definition", "action_proposal"], mode
        # confirm: the whole road stays open, and the lesser-authority
        # sentence is not on its form.
        _read(page, MODE_RUNS["confirm"])
        assert _offered(page) == [f"propose:{LONE}"], _offered(page)
        form = page.locator(f'[data-step="propose:{LONE}"]').inner_text()
        assert "a proposal is a durable record and nothing carries" not in form
        assert _propose(page, LONE) == 201
        page.wait_for_selector(f'[data-focus-key="confirm:{LONE}"]')
        assert window.writes("/proposals") == 3
    finally:
        assert window.problems == []
        page.context.close()
