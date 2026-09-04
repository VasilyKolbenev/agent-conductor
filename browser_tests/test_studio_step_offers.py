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

from browser_tests.test_studio_demo import demo_url  # noqa: F401
from browser_tests.test_studio_lifecycle import _Window, _settle
from browser_tests.test_studio_step import (  # noqa: F401
    CLOSED_RUN,
    DONE_RUN,
    FLIGHT_RUN,
    HALTED_RUN,
    LONE,
    OBSERVED_RUN,
    RESTALE_RUN,
    RUN_ID,
    STEP,
    _Bench,
    _offered,
    _open,
    _read,
    _row,
    bench,
)


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
