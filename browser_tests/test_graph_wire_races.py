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
        # That read is authoritative, so it also REPLACES the drawing: this
        # run follows no graph, and a draft made before the drop is not a fact
        # about it. What a Human does next is draw again, and the writing half
        # is proven by the tests that write.
        assert page.locator(".g-node").count() == 0
        assert "follows no graph yet" in page.locator("#notice").inner_text()
    finally:
        page.unroute(f"**/command/runs/{EMPTY_RUN}")
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

