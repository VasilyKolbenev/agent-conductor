"""What happens to a plan this window HOLDS when an answer arrives.

Split from ``test_graph_wire_races`` at the 800-line cap, along a real seam
rather than at a convenient line. That module is about the moments between a
request going out and its answer coming back -- doors, epochs, superseded reads.
This one is about a different subject entirely: the plan a Human has drawn and
not written, and which answers may take it away.

The rule the cases below hold, in one sentence: **a read replaces the drawing
when it BRINGS something.** A durable plan does, and it wins, with composed
steps carried on top. A run that follows no graph brings nothing, and neither
does a read this window cannot understand -- and neither is the Human doing
anything, so neither may take work they have not written. The one door a held
plan goes through is the Human's own: choosing another run.

Why this matters more than it looks: a run's plan is IMMUTABLE, so the only run
a plan can ever be written to is a run that follows none. `empty -> start from
the default -> compose -> save` is therefore the whole writable road, and every
step of it stands on a drawing this window holds and the run does not.

The seeded server, the page helper and the stream double come from
``test_graph_wire``: one run described in one place.
"""
from __future__ import annotations

from playwright.sync_api import Browser

from browser_tests.test_graph_wire import (  # noqa: F401
    DURABLE_RUN,
    EMPTY_RUN,
    OTHER_RUN,
    SECOND_RUN,
    _load_run,
    _open,
    wire_url,
)

def _compose_a_local_step(page, title: str = "Shadow review") -> str:
    """Compose one step onto whatever the run's plan already holds.

    The anchor is taken from the form's own first option rather than named
    here: which ids a run's durable plan carries is that fixture's business,
    and a test that hardcoded one would fail for a reason that is not its own.
    Answers with the composed node's id, read back from the drawing.
    """
    form = page.locator("#composerCard .g-compose")
    anchor = form.locator('[name="anchor"]')
    first = anchor.evaluate("node => node.options[0].value")
    form.locator('[name="title"]').fill(title)
    anchor.select_option(first)
    before = page.locator(".g-node").count()
    form.locator('button[type="submit"]').click()
    page.wait_for_function(
        "n => document.querySelectorAll('.g-node').length === n + 1",
        arg=before)
    return page.locator(".g-node").last.get_attribute("data-node-id")


def test_a_composed_local_step_survives_a_drop_and_the_read_that_follows(
        chromium: Browser, wire_url: str) -> None:
    """Born red. A reconnect's authoritative read used to erase a local draft.

    **The DURABLE half of the rule.** Here the read really does bring a plan,
    so that plan wins and only the composed steps ride on top of it. The cases
    below hold the other half, where the read brings nothing and the whole
    local plan stays.

    Four assertions, because any one alone passes on a build that got the
    others wrong.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, DURABLE_RUN)
        composed = _compose_a_local_step(page)
        assert "LOCAL DRAFT" in page.locator(
            f'[data-node-id="{composed}"]').inner_text()
        writes = len(recorder.matching("POST", "/graph"))

        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_function(
            "() => document.querySelector('[name=\\'save\\']').disabled")
        page.evaluate("() => window.__stream.fire('open')")
        page.wait_for_function(
            "() => !document.querySelector('[name=\\'save\\']').disabled")

        # 1. The unwritten step is still on the drawing, still labelled.
        assert page.locator(f'[data-node-id="{composed}"]').count() == 1, (
            "the authoritative read erased a step the Human had not written")
        assert "LOCAL DRAFT" in page.locator(
            f'[data-node-id="{composed}"]').inner_text()
        # 2. And it is not called plain durable: saying only that would offer
        #    the Human's own unwritten step back to them as the run's.
        assert "local draft" in page.locator("#runFacts").inner_text()
        # 3. A reconnect writes nothing. Preserving a draft may not become
        #    submitting one behind the Human's back.
        assert len(recorder.matching("POST", "/graph")) == writes
        # 4. Neither kind was rewritten as the other. Exactly the composed step
        #    wears the label; the run's own nodes arrived from the read and did
        #    not acquire one by standing beside it.
        assert page.locator('.g-node:has-text("LOCAL DRAFT")').count() == 1
    finally:
        page.context.close()


def test_the_whole_local_plan_survives_a_drop_on_a_run_that_follows_none(
        chromium: Browser, wire_url: str) -> None:
    """Born red, and this is the path a plan is actually WRITTEN on.

    A run's graph is immutable, so the only run a Human can ever write one to is
    a run that follows none. That makes `empty -> start from the default ->
    compose -> save` the whole writable road, and every step of it stands on a
    drawing this window holds and the run does not.

    The first fix here missed it. It held composed nodes on top of a DURABLE
    read, which is the one case where nothing can be saved anyway, and left the
    `absent` arm resetting to EMPTY -- so the eight fixture steps and the ninth
    composed one all vanished on the reconnect that follows any dropped socket.
    Zero nodes where there had been nine.

    So the whole local plan of the CURRENT run is held, not merely the nodes
    marked draft: a run that follows no graph contributes no durable fact, and
    there is nothing for the drawing to be hiding.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function(
            "() => document.querySelectorAll('.g-node').length === 8")
        composed = _compose_a_local_step(page)
        assert page.locator(".g-node").count() == 9
        writes = len(recorder.matching("POST", "/graph"))

        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_function(
            "() => document.querySelector('[name=\\'save\\']').disabled")
        page.evaluate("() => window.__stream.fire('open')")
        page.wait_for_function(
            "() => !document.querySelector('[name=\\'save\\']').disabled")

        assert page.locator(".g-node").count() == 9, (
            "the reconnect erased the plan the Human was about to write")
        assert page.locator(f'[data-node-id="{composed}"]').count() == 1
        assert page.locator('.g-node:has-text("LOCAL DRAFT")').count() == 1
        # Held, never sent. Preserving a plan may not become writing one.
        assert len(recorder.matching("POST", "/graph")) == writes
    finally:
        page.context.close()


def test_a_read_this_window_cannot_understand_keeps_the_plan_it_was_holding(
        chromium: Browser, wire_url: str) -> None:
    """Born red. A refused READ is not a reason to destroy unwritten work.

    An unreadable answer brings no durable fact -- exactly like a run that
    follows none -- and it is not the Human doing anything. It shuts the write
    door and says so, because this window can no longer claim the screen belongs
    to the chosen run; it may not also take the plan they were about to write.
    Measured before the fix: nine steps, then zero.

    A refused FIXTURE is a different event and keeps its own ruling -- there the
    Human handed this window a drawing it could not read, and `test_graph_
    boundary` holds that the drawing goes. `event.read` tells the two apart.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function(
            "() => document.querySelectorAll('.g-node').length === 8")
        composed = _compose_a_local_step(page)
        assert page.locator(".g-node").count() == 9
        writes = len(recorder.matching("POST", "/graph"))

        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_function(
            "() => document.querySelector('[name=\\'save\\']').disabled")
        # Landed, HTTP 200, unreadable as a run: not a transport error.
        page.route(f"**/command/runs/{EMPTY_RUN}",
                   lambda route: route.fulfill(json={}))
        page.evaluate("() => window.__stream.fire('open')")
        page.wait_for_function(
            "() => document.getElementById('notice').innerText"
            ".toLowerCase().includes('could not be read')")

        assert page.locator(".g-node").count() == 9, (
            "an unreadable read erased the plan the Human was about to write")
        assert page.locator(f'[data-node-id="{composed}"]').count() == 1
        # Shut: nothing is written on a screen this window cannot vouch for.
        assert page.evaluate(
            "() => document.querySelector('[name=\\'save\\']').disabled") is True
        assert len(recorder.matching("POST", "/graph")) == writes
        # No two contradictory sentences at once: `phase` hides the "No run
        # graph loaded" card, which would otherwise sit beside nine steps.
        assert page.locator("#fieldEmpty").is_hidden(), (
            "the empty-state card is on screen beside a drawn plan")
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()


def test_a_run_that_does_follow_a_plan_still_shows_it_over_a_local_drawing(
        chromium: Browser, wire_url: str) -> None:
    """The over-correction control: durable facts must not stop showing.

    Holding a local drawing is only honest while the run contributes nothing.
    The moment a read says the run DOES follow a plan, that plan is what the
    window owes the Human -- otherwise the rule above would quietly turn this
    window into one that shows a durable run whatever it drew last, which is
    the larger defect of the two.
    """
    page, _recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function(
            "() => document.querySelectorAll('.g-node').length === 8")
        composed = _compose_a_local_step(page)
        assert page.locator(".g-node").count() == 9

        _load_run(page, DURABLE_RUN)

        assert "DURABLE" in page.locator("#sourceLine").inner_text(), (
            "a run that follows a plan did not show it")
        assert page.locator(f'[data-node-id="{composed}"]').count() == 0
        assert page.locator('.g-node:has-text("LOCAL DRAFT")').count() == 0
    finally:
        page.context.close()


def test_a_written_plan_is_never_held_into_another_runs_emptiness(
        chromium: Browser, wire_url: str) -> None:
    """The mixing guard in its worst direction.

    Holding a drawing is only ever honest for a plan this window HOLDS. A
    durable plan belongs to the run that answered with it, and carrying it into
    a different run's "follows no graph" would show one run's WRITTEN plan as
    another run's unwritten one -- a lie in both directions at once, and the one
    a Human would act on by pressing save.
    """
    page, _recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, DURABLE_RUN)
        assert page.locator(".g-node").count() > 0

        _load_run(page, EMPTY_RUN)

        assert page.locator(".g-node").count() == 0, (
            "a run's written plan was held into another run's emptiness")
        notice = page.locator("#notice").inner_text()
        assert "follows no graph yet" in notice, notice
        assert "held in this window" not in notice, notice
    finally:
        page.context.close()


def test_a_local_plan_is_let_go_when_another_graphless_run_is_chosen(
        chromium: Browser, wire_url: str) -> None:
    """Two runs that both follow nothing -- where a silent carry would hide.

    Every other run change lands on a plan, which replaces the drawing for its
    own reason. Between two graph-less runs there is nothing to replace it, so
    only the discard at the Human's own action stops one run's unwritten work
    from becoming another's.
    """
    page, _recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function(
            "() => document.querySelectorAll('.g-node').length === 8")
        composed = _compose_a_local_step(page)

        _load_run(page, OTHER_RUN)

        assert page.locator(".g-node").count() == 0, (
            "a plan drawn against one graph-less run was carried to another")
        assert page.locator(f'[data-node-id="{composed}"]').count() == 0
    finally:
        page.context.close()


def test_choosing_another_run_never_carries_a_composed_step_onto_it(
        chromium: Browser, wire_url: str) -> None:
    """A draft is held for ONE run, and moves to no other.

    The holding rule above exists so a transport event cannot take a Human's
    unwritten work. Choosing a different run is not a transport event -- it is
    the Human saying they are looking at something else, and carrying a step
    composed against one run onto another run's screen would offer it as that
    run's. Worse, the save door beside it writes to whichever run is selected.

    So the rule is bounded by the run id the facts carry, and this is the
    control that says the bound is real rather than incidental.
    """
    page, _recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, DURABLE_RUN)
        composed = _compose_a_local_step(page)
        assert page.locator(f'[data-node-id="{composed}"]').count() == 1

        # A run that also FOLLOWS a plan, on purpose. Switching to a run that
        # follows none replaces the drawing for a different reason entirely, so
        # the bound is never exercised and a mutation removing it stayed green.
        _load_run(page, SECOND_RUN)

        assert page.locator(f'[data-node-id="{composed}"]').count() == 0, (
            "a step composed against one run was carried onto another")
        # Asked of the DRAWING and not of the run line. A run that follows no
        # graph says "local draft" there for its own reason -- its drawing came
        # from no durable read -- so that phrase cannot tell a carried step
        # from an empty run, and asserting on it would pass for the wrong one.
        assert page.locator('.g-node:has-text("LOCAL DRAFT")').count() == 0
    finally:
        page.context.close()
