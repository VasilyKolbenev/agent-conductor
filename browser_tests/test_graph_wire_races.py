"""Every race between the run-event stream, a write, and the run on screen.

Split out of ``test_graph_wire`` when that module reached its line cap. What
lives here is one circuit: the moments where the window has asked for
something and not yet been answered, and what it may say or do in them. Each
of these was a defect first -- a write announced on the wrong run's screen, a
plan written with nothing saying so, a live button beside a notice promising
the opposite -- so each is held by a case that cannot pass by waiting.

The seeded server, the page helper and the stream double come from
``test_graph_wire``: one run described in one place.
"""
from __future__ import annotations

import json

import pytest
from playwright.sync_api import Browser, Route

# ``wire_url`` is imported to be used as a fixture: the seeded server whose
# journal already holds the frozen plan and some records against it.
from browser_tests.test_graph_wire import (  # noqa: F401
    DIGEST,
    DURABLE_RUN,
    EMPTY_RUN,
    GRAPH_ID,
    OTHER_RUN,
    SECOND_RUN,
    _hold_first,
    _load_run,
    _open,
    _save,
    wire_url,
)

def test_a_run_frame_for_the_selected_run_buys_a_re_read_and_the_graph_moves(
        chromium: Browser, wire_url: str) -> None:
    """The real stream, the real frame, and a visibly different gate after it.

    The decision is recorded through the run's own route from inside the page,
    so the server publishes exactly the identifier-only frame it publishes for
    any mutation. Nothing in that frame is a fact: the gate below changes
    because the authoritative read was taken again.
    """
    page, recorder = _open(chromium, wire_url)
    try:
        _load_run(page, DURABLE_RUN)
        assert "pending" in page.locator("#gatesCard").inner_text()
        before = recorder.reads(DURABLE_RUN)
        status = page.evaluate(
            """async ([runId, body]) => {
                 const session = await (await fetch("/command/session")).json();
                 const answer = await fetch(`/command/runs/${runId}/decisions`, {
                   method: "POST", body: JSON.stringify(body),
                   headers: {"Content-Type": "application/json",
                             "X-Conduct-CSRF": session.csrf_token}});
                 return answer.status;
               }""",
            [DURABLE_RUN, {"receipt_id": "decision-wire-1",
                           "gate_id": "gate-confirm-do", "action": "approve",
                           "actor": "release-owner",
                           "reason": "Confirmed from the Graph window test.",
                           "scope_refs": ["src"], "evidence_refs": [],
                           "supersedes": None}])
        assert status == 201
        page.wait_for_function(
            "() => document.getElementById('gatesCard').innerText"
            ".includes('approved')")
        assert recorder.reads(DURABLE_RUN) > before
        assert "gate-result" in page.locator("#gatesCard").inner_text()
    finally:
        page.context.close()


def test_a_foreign_or_unreadable_frame_moves_nothing_on_screen(
        chromium: Browser, wire_url: str) -> None:
    """Every frame a real server would never send, answered with nothing.

    The last frame is the valid one, and the stream keeps order -- so a single
    read after all of them is proof the others bought none. A test that only
    waited a while could not tell "inert" from "not yet".
    """
    page, recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, DURABLE_RUN)
        page.wait_for_function("() => Boolean(window.__stream)")
        before = recorder.reads(DURABLE_RUN)
        for frame in ("not json at all",
                      "null",
                      '"a string"',
                      '{"kind":"run"}',
                      '{"kind":"run","run_id":""}',
                      '{"kind":"run","run_id":"../etc/passwd"}',
                      f'{{"kind":"run","run_id":"{OTHER_RUN}"}}',
                      '{"kind":"weather","run_id":"run-001"}',
                      '{"kind":"run","run_id":"run-001","records":[1]}'):
            page.evaluate("frame => window.__stream.emit(frame)", frame)
        # Only the last frame names this run with a readable id, and the
        # stream keeps order — so waiting for ONE further read and then
        # counting is proof the eight before it bought none.
        page.wait_for_function(
            """expected => performance.getEntriesByType("resource")
                 .filter(entry => entry.name.endsWith("/command/runs/run-001"))
                 .length >= expected""",
            arg=before + 1)
        assert recorder.reads(DURABLE_RUN) == before + 1
        assert recorder.reads(OTHER_RUN) == 0
        assert DIGEST in page.locator("#sourceLine").inner_text()
    finally:
        page.context.close()


def test_a_dropped_stream_shuts_the_write_door_until_the_run_is_read_again(
        chromium: Browser, wire_url: str) -> None:
    """The window promises this in words, so the code has to keep it.

    An earlier version of this test asserted the opposite -- it counted a
    SECOND session read after the drop and called that the point, which is a
    test pinning a write the notice beside it said could not happen. What the
    sentence claims is that nothing may be written until the stream is back,
    and the witnesses for that are counts of zero: no session read, no POST.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('The plan is written')")
        sessions = len(recorder.matching("GET", "/command/session"))
        writes = len(recorder.matching("POST", "/graph"))
        assert sessions == 1 and writes == 1

        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_function(
            "() => document.querySelector('[name=\\'save\\']').disabled")
        assert "Connection lost" in page.locator("#saveStatus").inner_text()
        assert "stream is not carrying" in page.locator("#saveCard").inner_text()
        # Pressed anyway, through the DOM: a disabled control must be inert in
        # fact, not merely styled as though it were.
        page.locator('[name="graphId"]').fill(GRAPH_ID)
        page.evaluate("() => document.querySelector('[name=\\'save\\']').click()")
        page.evaluate("() => new Promise(done => requestAnimationFrame(done))")
        assert len(recorder.matching("GET", "/command/session")) == sessions
        assert len(recorder.matching("POST", "/graph")) == writes
    finally:
        page.context.close()


def test_a_reconnect_reopens_the_write_door_only_after_the_run_is_read(
        chromium: Browser, wire_url: str) -> None:
    """An open socket is not a current screen.

    What the stream missed while it was down is unknown, so the door stays
    shut across the reconnect itself and opens on the authoritative read that
    follows it -- the read is the thing that makes this window current again.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    reads: dict[str, Route] = {}
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_function(
            "() => document.querySelector('[name=\\'save\\']').disabled")
        before = recorder.reads(EMPTY_RUN)
        # The read is held open, so the window sits in the one moment this
        # test is about: socket back, answer not yet. An end-state assertion
        # could not tell "after the read" from "on the reconnect, with a read
        # happening to follow" -- a mutation granting readiness on `open`
        # passed a test written that way.
        page.route(f"**/command/runs/{EMPTY_RUN}", _hold_first(reads))
        page.evaluate("() => window.__stream.fire('open')")
        while "held" not in reads:
            page.evaluate("() => new Promise(done => setTimeout(done, 20))")
        assert page.evaluate(
            "() => document.querySelector('[name=\\'save\\']').disabled") is True
        reads["held"].continue_()
        page.wait_for_function(
            "() => !document.querySelector('[name=\\'save\\']').disabled")
        assert recorder.reads(EMPTY_RUN) == before + 1
        # This used to assert the read REPLACES the drawing -- zero nodes -- on
        # the reasoning that "a draft made before the drop is not a fact about
        # the run". True, and the conclusion was wrong; overturned on purpose.
        # A run's plan is IMMUTABLE, so the only run one can be written to is a
        # run that follows none: this exact screen is the whole writable road,
        # and replacing it meant a dropped socket threw away the work a Human
        # was in the middle of. The drawing is not claimed as the run's -- the
        # run still says it follows no graph, and the window says who holds it.
        assert page.locator(".g-node").count() == 8
        notice = page.locator("#notice").inner_text()
        assert "follows no graph yet" in notice, notice
        assert "held in this window" in notice, notice
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()


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

    The read replaced the whole drawing, so a step a Human had composed and not
    written was gone the moment the socket came back -- silently, with nothing
    saying so and nothing to recover it from.

    **Scoped to COMPOSED steps and nothing wider.** Only `compose` marks a node
    `draft`; every projected node, fixture or durable, carries `draft: false`.
    A drawing seeded from the product's default is therefore still replaced,
    which is what `test_a_reconnect_reopens_the_write_door_...` above holds and
    what its comment argues for. That ruling is not reopened here.

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


def test_a_read_answering_after_the_human_moved_on_paints_no_screen(
        chromium: Browser, wire_url: str) -> None:
    """A superseded read is not a fact about the run now on screen.

    The window guards this with a read epoch, and the guard had no test of its
    own: a mutation deleting it stayed green, because the module's other cases
    are about the write DOOR rather than about the drawing, and a door held
    shut says nothing about what got painted while it was.
    """
    page, _recorder = _open(chromium, wire_url, double=True)
    held: dict[str, Route] = {}
    marker = "STALE-PAINT-MARKER"
    try:
        _load_run(page, DURABLE_RUN)
        # The paint is TRANSIENT, so it is WATCHED rather than looked for after
        # the fact: a serialized re-read always follows a superseded one, so by
        # the time any end-state assertion runs the correct facts have landed on
        # top -- and an end-state test passes with the guard deleted.
        page.evaluate(
            "m => { window.__seen = false;"
            " new MutationObserver(() => {"
            "   if (document.body.innerText.includes(m)) window.__seen = true;"
            " }).observe(document.body,"
            "   {subtree: true, childList: true, characterData: true}); }",
            marker)
        page.route(f"**/command/runs/{DURABLE_RUN}", _hold_first(held))
        page.evaluate(
            "id => window.__stream.emit("
            "JSON.stringify({kind: 'run', run_id: id}))", DURABLE_RUN)
        while "held" not in held:
            page.evaluate("() => new Promise(done => setTimeout(done, 20))")

        page.locator("#graphRunId").fill(EMPTY_RUN)
        page.get_by_role("button", name="Load run").click()
        # Answered at last, and answered VISIBLY: the same document with one
        # title replaced, so painting it would put a word on screen that this
        # run's real plan does not carry.
        route = held["held"]
        body = route.fetch().json()
        body["graph"]["definition"]["nodes"][0]["title"] = marker
        route.fulfill(json=body)
        page.wait_for_function(
            "id => document.getElementById('runFacts').innerText.includes(id)",
            arg=EMPTY_RUN)

        assert page.evaluate("() => window.__seen") is False, (
            "a superseded read painted the screen the Human had already left")
    finally:
        page.unroute(f"**/command/runs/{DURABLE_RUN}")
        page.context.close()


def test_choosing_a_run_shuts_the_door_before_its_facts_have_arrived(
        chromium: Browser, wire_url: str) -> None:
    """The mirror of the delayed-POST case, and the worse of the two.

    Load A, then choose B and hold B's read open. In that gap `selectedRun` is
    already B while the drawing on screen is still A's -- so a write taken
    then would have built A's plan and sent it to B's IMMUTABLE graph route,
    which no later read could take back. The door is therefore shut the
    instant a run is chosen, not when its answer arrives.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    reads: dict[str, Route] = {}
    try:
        _load_run(page, DURABLE_RUN)
        assert page.evaluate(
            "() => document.querySelector('[name=\\'save\\']').disabled") is False
        sessions = len(recorder.matching("GET", "/command/session"))
        page.route(f"**/command/runs/{EMPTY_RUN}", _hold_first(reads))
        page.locator("#graphRunId").fill(EMPTY_RUN)
        page.get_by_role("button", name="Load run").click()
        while "held" not in reads:
            page.evaluate("() => new Promise(done => setTimeout(done, 20))")
        assert page.evaluate(
            "() => document.querySelector('[name=\\'save\\']').disabled") is True
        # Still A's graph on screen, and the run now chosen is B.
        assert DIGEST in page.locator("#sourceLine").inner_text()
        page.locator('[name="graphId"]').fill(GRAPH_ID)
        page.evaluate("() => document.querySelector('[name=\\'save\\']').click()")
        page.evaluate("() => new Promise(done => requestAnimationFrame(done))")
        assert len(recorder.matching("GET", "/command/session")) == sessions
        assert recorder.matching("POST", "/graph") == []
        reads["held"].continue_()
        page.wait_for_function(
            "() => !document.querySelector('[name=\\'save\\']').disabled")
        assert "follows no graph yet" in page.locator("#notice").inner_text()
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()


def test_a_run_that_follows_no_graph_confirms_no_write_of_ours(
        chromium: Browser, wire_url: str) -> None:
    """A clean read is not a confirmation. It is only a read.

    The write is accepted and the re-read answers, canonically and correctly,
    that this run follows no graph at all. Both sentences were on screen at
    once -- "This run follows no graph yet" and "The plan is written" -- which
    is a window contradicting itself about the one fact it exists to report.
    """
    page, recorder = _open(chromium, wire_url, double=True)

    def empty_graph(route: Route) -> None:
        body = route.fetch().json()
        body["graph"] = {"definition": None, "definition_digest": None,
                         "runtime": None}
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(body))

    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        page.route(f"**/command/runs/{EMPTY_RUN}", empty_graph)
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('Outcome unknown')")
        assert page.locator("#saveStatus").inner_text() == \
            "Outcome unknown. Reload the authoritative run."
        # The read itself was fine and is reported as such: this window IS
        # current, it simply did not see the plan it wrote.
        assert "follows no graph yet" in page.locator("#notice").inner_text()
        assert page.evaluate(
            "() => document.querySelector('[name=\\'save\\']').disabled") is False
        assert len(recorder.matching("POST", "/graph")) == 1
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()


def test_a_read_showing_another_graph_confirms_no_write_of_ours(
        chromium: Browser, wire_url: str) -> None:
    """Somebody else's plan is not proof that ours was written.

    The re-read projects perfectly -- one definition, one runtime, agreeing
    with each other -- but the graph it describes is not the one submitted.
    The screen must show what the run actually follows and say nothing about
    a write it did not witness.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    other = "graph-somebody-elses"

    def another_graph(route: Route) -> None:
        body = route.fetch().json()
        body["graph"]["definition"]["graph_id"] = other
        body["graph"]["runtime"]["graph_id"] = other
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(body))

    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        page.route(f"**/command/runs/{EMPTY_RUN}", another_graph)
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('Outcome unknown')")
        assert page.locator("#saveStatus").inner_text() == \
            "Outcome unknown. Reload the authoritative run."
        source = page.locator("#sourceLine").inner_text()
        assert other in source and GRAPH_ID not in source
        assert "DURABLE" in source
        assert len(recorder.matching("POST", "/graph")) == 1
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()


def test_a_read_showing_the_written_plan_is_what_confirms_it(
        chromium: Browser, wire_url: str) -> None:
    """The positive control, so the comparison cannot pass by refusing all.

    No routing here: the real server answers, the read shows the plan that
    was written, and both words a write can honestly earn are earned -- one
    for the record it created, one for the record a retry found standing.
    """
    page, _ = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('The plan is written')")
        assert GRAPH_ID in page.locator("#sourceLine").inner_text()
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('already stands')")
        assert "Outcome unknown" not in page.locator("#saveStatus").inner_text()
    finally:
        page.context.close()


def test_a_read_that_arrives_whole_and_unreadable_confirms_nothing_either(
        chromium: Browser, wire_url: str) -> None:
    """The half of the law a transport failure does not reach.

    Here the re-read after the write SUCCEEDS at every level a status code
    can describe: HTTP 200, a complete run document, every other key intact.
    One graph detail is corrupted -- the projection names a different graph
    than the plan does -- so the window correctly refuses to read it as one
    plan and one position.

    It refused, and it still said the plan was written. A refusal is not an
    answer about what a run holds, and 200 bytes of valid HTTP do not make it
    one; the only honest word here is that the outcome is unknown.
    """
    page, recorder = _open(chromium, wire_url, double=True)

    def corrupt(route: Route) -> None:
        answer = route.fetch()
        body = answer.json()
        body["graph"]["runtime"]["graph_id"] = "graph-somebody-elses"
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps(body))

    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        page.route(f"**/command/runs/{EMPTY_RUN}", corrupt)
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('Outcome unknown')")
        status = page.locator("#saveStatus").inner_text()
        assert status == "Outcome unknown. Reload the authoritative run."
        assert "The plan is written" not in status
        assert "already stands" not in status
        assert "could not be read as one plan" in page.locator("#notice").inner_text()
        assert page.evaluate(
            "() => document.querySelector('[name=\\'save\\']').disabled") is True
        # The write itself did land: this is about what may be CLAIMED of it.
        assert len(recorder.matching("POST", "/graph")) == 1
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()


def test_a_read_that_fails_after_a_write_confirms_nothing_about_it(
        chromium: Browser, wire_url: str) -> None:
    """A 201 is an answer about a request, not about what the run now holds.

    The write is accepted and the authoritative re-read that would confirm it
    is answered with a refusal. The window must not say the plan is written --
    it did not manage to see that it was -- and the door it could not confirm
    through stays shut.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        page.route(f"**/command/runs/{EMPTY_RUN}", lambda route: route.fulfill(
            status=409, content_type="application/json",
            body=json.dumps({"error": {"code": "run_corrupt"}})))
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('Outcome unknown')")
        assert "The plan is written" not in page.locator("#saveStatus").inner_text()
        assert page.evaluate(
            "() => document.querySelector('[name=\\'save\\']').disabled") is True
        # The write itself did happen: this is about what may be CLAIMED of it.
        assert len(recorder.matching("POST", "/graph")) == 1
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()


def test_a_write_that_lands_after_the_human_moved_on_is_not_that_runs_answer(
        chromium: Browser, wire_url: str) -> None:
    """A POST for one run may not report itself on another run's screen.

    The write is held open on the wire while the Human loads a different run,
    and only then answered. Nothing about the first run may appear on the
    second: not its success, and not an authoritative re-read of it.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    held: dict[str, Route] = {}
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        page.route("**/graph", lambda route: held.setdefault("route", route))
        _save(page, GRAPH_ID)
        page.wait_for_function("() => document.getElementById('saveStatus')"
                               ".innerText.includes('Writing one immutable')")
        _load_run(page, DURABLE_RUN)
        before = recorder.reads(EMPTY_RUN)
        held["route"].fulfill(status=201, content_type="application/json",
                              body=json.dumps({"graph_id": GRAPH_ID}))
        page.evaluate("() => new Promise(done => setTimeout(done, 250))")
        status = page.locator("#saveStatus").inner_text()
        assert "The plan is written" not in status
        assert recorder.reads(EMPTY_RUN) == before
        # And the screen still belongs to the run the Human is looking at.
        assert DIGEST in page.locator("#sourceLine").inner_text()
    finally:
        page.unroute("**/graph")
        page.context.close()


def test_a_run_frame_arriving_mid_refetch_does_not_swallow_the_write_outcome(
        chromium: Browser, wire_url: str) -> None:
    """The plan was written; the sentence saying so must survive the race.

    The authoritative re-read that follows a write is held open, a run frame
    lands while it is in flight, and that read is therefore superseded. The
    outcome must still be announced by the read that replaces it -- otherwise
    a graph reaches the journal and the window never says a word about it.
    """
    page, recorder = _open(chromium, wire_url, double=True)
    reads: dict[str, Route] = {}
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        page.route(f"**/command/runs/{EMPTY_RUN}", _hold_first(reads))
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('Writing one immutable')")
        # The save's own re-read is now held open. A run frame supersedes it.
        while "held" not in reads:
            page.evaluate("() => new Promise(done => setTimeout(done, 20))")
        page.evaluate(
            "id => window.__stream.emit(JSON.stringify({kind: 'run', run_id: id}))",
            EMPTY_RUN)
        reads["held"].continue_()
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('The plan is written')")
        assert "DURABLE" in page.locator("#sourceLine").inner_text()
        assert len(recorder.matching("POST", "/graph")) == 1
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
        page.context.close()
