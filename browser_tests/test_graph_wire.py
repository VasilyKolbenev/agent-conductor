"""The Graph window on the wire, driven in a real browser against the real server.

``test_graph_rendered`` proves the fixture path; this module proves the durable
one. A real loopback server, a real run whose journal already holds the frozen
Dalio plan and some records against it, Chromium executing the shipped module
graph from ``/panel/graph.html``, and every request the page makes recorded --
so "the plan and the run are drawn apart", "only a Human's click writes", and
"a signal buys a re-read and never a fact" are counted rather than argued.

It lives outside pytest's configured ``testpaths`` for the same reason as the
other browser modules: Playwright stays an explicit development/CI dependency.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, Route

from conductor import server
from conductor.command.adapters.base import AdapterRegistry
from conductor.command.run_store import RunStore, snapshot_digest

from tests.alpha3_graph_artifacts import dalio_definition, load
from tests.test_command_graph_projection import (
    a_proposal,
    a_request,
    an_event,
)
from tests.test_command_run_store import CONFIG, a_run
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_store import good_lane, write_project

#: The run whose journal already holds the frozen plan. Its id is the artifact's
#: own, because the digest covers `run_id` and `created_at` -- a plan appended
#: under any other run would be a different document with a different digest,
#: and the exact-digest assertion below would then prove nothing.
DURABLE_RUN = "run-001"
EMPTY_RUN = "run-empty"
OTHER_RUN = "run-other"
TOKEN = "browser-only-process-token"
FROZEN = load("alpha3_dalio_definition")
DIGEST = FROZEN["definition_digest"]
GRAPH_ID = FROZEN["definition"]["graph_id"]
#: Every name a plan may never carry, exactly as the durable contract spells
#: them. The submitted body is read against this list in the browser.
RUNTIME_WORDS = (
    "attempt_id", "attempt_ids", "attempts", "availability", "bound_reached",
    "decided_at", "decision", "decisions", "evidence", "evidence_refs",
    "health", "observed_at", "outcome", "outcomes", "pass", "passes", "phase",
    "started_at", "state", "status", "timeline",
)


def _seed(root: Path) -> None:
    """One run carrying the frozen plan and a few records against it.

    `goal` gets a proposal and nothing more, so it reads `proposed`. `do` gets
    a confirmed request and an OBSERVED attempt boundary whose own outcome
    says ``succeeded`` -- and NO result receipt. That is the sharpest form of
    the case safety law 9 exists for: the journal contains the word, a watched
    process really did exit zero, and the immutable result a product success
    requires was never written. The window must show the boundary and must not
    show the word.
    """
    store = RunStore(root)
    for run_id in (DURABLE_RUN, EMPTY_RUN, OTHER_RUN):
        store.create_run(
            a_run(run_id=run_id, mode="confirm",
                  config_digest=snapshot_digest(CONFIG)), CONFIG)
    store.append(dalio_definition(run_id=DURABLE_RUN))
    store.append(a_proposal(node_id="goal", index=1))
    doing = a_proposal(node_id="do", index=2)
    store.append(doing)
    request = a_request(doing, index=2)
    store.append(request)
    store.append(an_event(request, "effect_lease", index=2))
    store.append(an_event(request, "execution_observed", index=2,
                          outcome="succeeded", exit_code=0))


@pytest.fixture
def wire_url(tmp_path) -> Iterator[str]:
    """The Graph window at its production route, over a seeded real server."""
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    _seed(root)
    httpd = server.build(
        # One adapter per adapter the CONFIGURATION binds, which is what an
        # install IS. This registry used to hold one, while the frozen config
        # declared two instances on two products -- so `codex-review` was an
        # instance that deployment could never serve, and any plan naming it was
        # answered `service_refused`. The narrower registry was invisible while
        # every fixture step bound the other instance.
        root, 0, registry=AdapterRegistry([
            DeepPlanAdapter(name) for name in
            sorted({row["adapter"] for row in CONFIG["instances"]})]),
        token_factory=lambda _size: TOKEN)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/panel/graph.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "wire server did not stop"


class _Recorder:
    """Every request the page issues, so each route can be counted."""

    def __init__(self, page: Page) -> None:
        self.rows: list[tuple[str, str, str | None]] = []
        page.on("request", lambda request: self.rows.append(
            (request.method, request.url, request.post_data)))

    def matching(self, method: str, fragment: str) -> list[tuple[str, str, str | None]]:
        return [row for row in self.rows
                if row[0] == method and fragment in row[1]]

    def reads(self, run_id: str) -> int:
        """Authoritative run reads, which are the only door durable facts use."""
        return len([row for row in self.rows
                    if row[0] == "GET" and row[1].endswith(f"/command/runs/{run_id}")])


#: A stand-in for the browser's own EventSource, installed before any page
#: script runs. It drives the REAL production handler with frames a real server
#: would never emit -- malformed, foreign, unknown -- which is the only way to
#: prove the handler is inert for them rather than merely never asked.
#:
#: It connects the way a real one does: `open` is announced after the
#: constructor returns, because the page attaches its listener on the line
#: after `new EventSource(...)`. A double that never opened would leave the
#: window permanently believing its stream was down, and every test built on
#: it would be testing the disconnected window by accident.
_STREAM_DOUBLE = """
window.__streamOpens = 0;
class TestStream {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.onmessage = null;
    window.__stream = this;
    window.__streamOpens += 1;
    setTimeout(() => this.fire("open"), 0);
  }
  addEventListener(name, handler) {
    (this.listeners[name] = this.listeners[name] || []).push(handler);
  }
  emit(data) { if (this.onmessage) this.onmessage({data}); }
  fire(name) { for (const h of this.listeners[name] || []) h({}); }
  close() {}
}
window.EventSource = TestStream;
"""


def _open(chromium: Browser, url: str, *, double: bool = False,
          **context: object) -> tuple[Page, _Recorder]:
    browser_context = chromium.new_context(**context)
    if double:
        browser_context.add_init_script(_STREAM_DOUBLE)
    page = browser_context.new_page()
    recorder = _Recorder(page)
    page.goto(url, wait_until="load")
    page.wait_for_function("Boolean(window.conductGraph)")
    return page, recorder


def _load_run(page: Page, run_id: str) -> None:
    page.locator("#graphRunId").fill(run_id)
    page.get_by_role("button", name="Load run").click()
    page.wait_for_function(
        "id => document.getElementById('runFacts').innerText.includes(id)",
        arg=run_id)


def _save(page: Page, graph_id: str) -> None:
    page.locator('[name="graphId"]').fill(graph_id)
    page.get_by_role("button", name="Save plan to run").click()


def _hold_first(reads: dict):
    """Hold the FIRST matching request open; let every later one through.

    Every race in ``test_graph_wire_races`` lives in the moment between a
    request going out and its answer coming back, and that moment cannot be
    reached by waiting -- it has to be held. It lives here because the fixture
    it is used with lives here.
    """
    def handler(route: Route) -> None:
        if "held" in reads:
            route.continue_()
            return
        reads["held"] = route
    return handler


def _card_for(page: Page, node_id: str) -> str:
    page.locator(f'[data-node-id="{node_id}"]').click()
    page.locator(".g-det__title").wait_for(state="visible")
    return page.locator("#detailBody").inner_text()


def test_the_graph_window_is_served_by_the_production_route_it_names(
        chromium: Browser, wire_url: str) -> None:
    """Every module file answers from the allowlist, under its literal name."""
    page, recorder = _open(chromium, wire_url)
    try:
        served = {row[1].rsplit("/", 1)[1] for row in recorder.matching(
            "GET", "/panel/")}
        assert served == {
            "graph.html", "graph.css", "graph.js", "graph-adapter.js",
            "graph-default.js", "graph-payload.js", "graph-store.js",
            "graph-view.js",
            "command-projection.js", "command-view.js"}
        assert page.locator(".g-node").count() == 8
        # It opens on the default as a LOCAL DRAFT and says so before any run
        # is named: nothing durable is on screen until a run read puts it there.
        assert "LOCAL DRAFT" in page.locator("#sourceLine").inner_text()
        assert recorder.reads(DURABLE_RUN) == 0
    finally:
        page.context.close()


def test_loading_and_writing_a_run_raises_nothing_the_console_hears(
        chromium: Browser, wire_url: str) -> None:
    """The whole wire path, with the console as the assertion.

    The boot test cannot see this: an HTML `pattern` is compiled when the
    form is first validated, not when the page loads, so a pattern that does
    not compile stays silent until a Human submits. It also stays INERT --
    the attribute is ignored rather than enforced -- which leaves a control
    wearing a constraint it does not have. Both forms here are submitted.
    """
    context = chromium.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    problems: list[str] = []
    page.on("console", lambda message: problems.append(message.text)
            if message.type == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    try:
        page.goto(wire_url, wait_until="load")
        page.wait_for_function("Boolean(window.conductGraph)")
        # A run with no plan yet, so the write SUCCEEDS: a refusal would have
        # the browser log the status itself, and this assertion is about what
        # the PAGE raises, not about what a refused request sounds like.
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('The plan is written')")
        assert problems == []
        # And the constraint the attribute claims is real: the browser itself
        # refuses a run id the grammar does not admit, before any handler.
        page.locator("#graphRunId").fill("not a run id!")
        assert page.evaluate(
            "() => document.getElementById('graphRunId').checkValidity()") is False
        page.locator("#graphRunId").fill(DURABLE_RUN)
        assert page.evaluate(
            "() => document.getElementById('graphRunId').checkValidity()") is True
    finally:
        context.close()


def test_a_durable_read_draws_the_plan_and_the_run_in_separate_places(
        chromium: Browser, wire_url: str) -> None:
    """The two documents share the screen, never a chip.

    The plan's ceiling and the run's position are the pair the December
    Command keeps apart by name: `loop.bound` is the plan's and `pass` is the
    run's. Here they are also apart on screen -- the bound sits among the
    plan's chips and the pass sits inside the labelled run group, so no chip
    carries both and no reader has to know which is which.
    """
    page, _ = _open(chromium, wire_url)
    try:
        _load_run(page, DURABLE_RUN)
        source = page.locator("#sourceLine").inner_text()
        assert "DURABLE" in source and GRAPH_ID in source
        # The digest the server computed on THIS read, byte for byte the one
        # the frozen artifact carries.
        assert DIGEST in source
        loop = page.locator('[data-node-id="retry-loop"]')
        assert "×3" in loop.locator(".g-loop-bound").inner_text()
        assert "pass 1 of ×3" in loop.locator(".g-node__run").inner_text()
        # …and the plan's bound is NOT inside the run group.
        assert loop.locator(".g-node__run .g-loop-bound").count() == 0
        # The headings are uppercased by the stylesheet, so the rendered text
        # is what a reader sees and what this reads back.
        card = _card_for(page, "do")
        assert "PLAN BINDING" in card and "RUN POSITION" in card
        assert "instance: claude-dev" in card and "capability: dispatch" in card
        assert "instruction_ref" in card and "instruction-plan" in card
        assert "attempts: attempt-002" in card
        # Vendor rows are DATA the server's registry supplies, never a branch:
        # the palette fills from `/harnesses.json`, and the step's own badge
        # stays neutral because the plan names an INSTANCE the registry has no
        # row for. Both are the same rule, applied to two different strings.
        palette = page.locator("#paletteCard").inner_text()
        assert "Claude Code" in palette and "DeepSeek Harness" in palette
        badge = page.locator('[data-node-id="do"] .hb__n').inner_text()
        assert badge == "claude-dev"
        # The DEPLOYMENT section is the other half of that same rule, and the
        # one place a product NAME appears on a step. The plan named the
        # instance; the run's frozen configuration says which adapter serves it,
        # and that id DOES have a registry row -- so a reader sees "Claude Code"
        # here and `claude-dev` on the badge, which is exactly the distinction
        # this window exists to keep. The static default cannot show this: it
        # carries no registry copy, on purpose.
        assert "DEPLOYMENT" in card
        deployment = page.locator("#detailCard .hb__n").last.inner_text()
        assert deployment == "Claude Code"
    finally:
        page.context.close()


def test_an_observed_boundary_with_no_receipt_never_reads_as_success(
        chromium: Browser, wire_url: str) -> None:
    """`observed` is a boundary reached, and this window says exactly that.

    The seeded run holds an execution-observed attempt event for `do` whose
    own outcome is ``succeeded``, and no result receipt. So the word IS in the
    journal, one join away — and a window that reached for it would show a
    finished green step for work no immutable result stands behind. The last
    assertion is that the word appears nowhere on the page at all.
    """
    page, _ = _open(chromium, wire_url)
    try:
        _load_run(page, DURABLE_RUN)
        run_chips = page.locator(
            '[data-node-id="do"] .g-node__run').inner_text()
        assert "observed" in run_chips
        assert "no result recorded" in run_chips
        card = _card_for(page, "do")
        assert "is not success" in " ".join(card.split())
        assert "succeeded" not in page.locator("body").inner_text()
        # The gate the plan puts before `do` is pending, because no receipt
        # stands -- never because a gate was assumed to pass.
        gates = page.locator("#gatesCard").inner_text()
        assert "gate-confirm-do" in gates and "pending" in gates
        assert "approved" not in gates
    finally:
        page.context.close()


def test_a_run_following_no_graph_says_so_and_infers_nothing(
        chromium: Browser, wire_url: str) -> None:
    page, _ = _open(chromium, wire_url)
    try:
        _load_run(page, EMPTY_RUN)
        notice = page.locator("#notice").inner_text()
        assert "follows no graph yet" in notice
        assert page.locator(".g-node").count() == 0
        assert "DURABLE" not in page.locator("#sourceLine").inner_text()
        assert page.locator("#fieldEmpty").is_visible()
    finally:
        page.context.close()


def test_the_plan_is_written_only_when_a_human_presses_save(
        chromium: Browser, wire_url: str) -> None:
    """No auto-POST anywhere: not on load, not on seeding, not on compose.

    The count is the assertion. Loading a run, drawing the default and adding
    a step are three separate acts that each change the screen, and none of
    them may put a byte in an immutable record.
    """
    page, recorder = _open(chromium, wire_url)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        assert "LOCAL DRAFT" in page.locator("#sourceLine").inner_text()
        assert recorder.matching("POST", "/graph") == []
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('The plan is written')")
        writes = recorder.matching("POST", "/graph")
        assert len(writes) == 1
        # And what the screen shows afterwards came from the re-read, not from
        # the local copy: the digest is one only the server can compute.
        source = page.locator("#sourceLine").inner_text()
        assert "DURABLE" in source and "sha256:" in source
        assert recorder.reads(EMPTY_RUN) >= 2
    finally:
        page.context.close()


def test_the_submitted_plan_carries_no_word_the_run_owns(
        chromium: Browser, wire_url: str) -> None:
    """A plan is immutable once written, so the screen is before the door.

    The body is captured off the wire and read against the durable contract's
    own refusal list. A phase, an outcome, a pass or a decision reaching an
    immutable record could never be taken back out of it.
    """
    page, recorder = _open(chromium, wire_url)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('The plan is written')")
        body = json.loads(recorder.matching("POST", "/graph")[0][2])
        assert sorted(body) == ["edges", "graph_id", "nodes"]

        def keys(value: object) -> list[str]:
            if isinstance(value, list):
                return [name for item in value for name in keys(item)]
            if not isinstance(value, dict):
                return []
            rest = {k: v for k, v in value.items() if k != "arguments"}
            return list(rest) + [n for v in rest.values() for n in keys(v)]

        assert not set(keys(body)) & set(RUNTIME_WORDS)
        assert [node["node_id"] for node in body["nodes"]] == [
            node["node_id"] for node in FROZEN["definition"]["nodes"]]
    finally:
        page.context.close()


def test_an_exact_retry_answers_from_the_journal_without_a_second_record(
        chromium: Browser, wire_url: str) -> None:
    """The plan read back rebuilds the plan sent, so the retry is EXACT.

    That is the round trip this window owes: what it drew from the durable
    read, offered again, must be the same document -- otherwise a lost reply
    would turn into a conflict against the record the client itself wrote.
    """
    page, recorder = _open(chromium, wire_url)
    try:
        _load_run(page, EMPTY_RUN)
        page.get_by_role("button", name="Start from the default").click()
        page.wait_for_function("() => document.querySelectorAll('.g-node').length === 8")
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('The plan is written')")
        first = page.locator("#sourceLine").inner_text()
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('already stands')")
        status = page.locator("#saveStatus").inner_text()
        assert "Nothing was appended" in status
        assert "The plan is written" not in status
        # The same record, digest included: no second identity was minted.
        assert page.locator("#sourceLine").inner_text() == first
        assert len(recorder.matching("POST", "/graph")) == 2
    finally:
        page.context.close()


def test_a_conflicting_plan_is_refused_and_the_screen_stays_what_the_run_holds(
        chromium: Browser, wire_url: str) -> None:
    """A run carries one graph. The refusal changes nothing on screen."""
    page, _ = _open(chromium, wire_url)
    try:
        _load_run(page, DURABLE_RUN)
        before = page.locator("#sourceLine").inner_text()
        _save(page, "graph-second-opinion")
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('conflicts')")
        assert page.locator("#sourceLine").inner_text() == before
        assert DIGEST in page.locator("#sourceLine").inner_text()
        assert "succeeded" not in page.locator("body").inner_text()
    finally:
        page.context.close()



@pytest.mark.parametrize("width", (360, 768, 1440))
def test_the_wire_window_never_scrolls_sideways_at_any_approved_width(
        chromium: Browser, wire_url: str, width: int) -> None:
    """A 71-character digest and a bound plan must both fit the reading column."""
    page, _ = _open(chromium, wire_url,
                    viewport={"width": width, "height": 900})
    try:
        _load_run(page, DURABLE_RUN)
        assert DIGEST in page.locator("#sourceLine").inner_text()
        overflow = page.evaluate(
            """() => document.documentElement.scrollWidth
                   - document.documentElement.clientWidth""")
        assert overflow <= 0, f"{width}px scrolls sideways by {overflow}px"
    finally:
        page.context.close()


@pytest.mark.parametrize("scheme", ("dark", "light"))
def test_the_wire_surfaces_answer_the_reader_scheme_and_keep_a_focus_ring(
        chromium: Browser, wire_url: str, scheme: str) -> None:
    page, _ = _open(chromium, wire_url, color_scheme=scheme,
                    viewport={"width": 1440, "height": 1000})
    try:
        _load_run(page, DURABLE_RUN)
        ink = page.evaluate(
            "() => getComputedStyle(document.body).color")
        assert ink == ("rgb(243, 246, 248)" if scheme == "dark"
                       else "rgb(17, 22, 29)")
        page.locator("#graphRunId").focus()
        page.keyboard.press("Tab")
        outline = page.evaluate(
            """() => {
                 const style = getComputedStyle(document.activeElement);
                 return [document.activeElement.tagName, style.outlineWidth];
               }""")
        assert outline[0] == "BUTTON"
        assert outline[1] not in ("", "0px")
    finally:
        page.context.close()


def test_reduced_motion_removes_the_only_transition_this_window_declares(
        chromium: Browser, wire_url: str) -> None:
    page, _ = _open(chromium, wire_url, reduced_motion="reduce",
                    viewport={"width": 1440, "height": 1000})
    try:
        _load_run(page, DURABLE_RUN)
        duration = page.evaluate(
            """() => getComputedStyle(
                 document.querySelector(".g-node")).transitionDuration""")
        assert duration == "0s"
    finally:
        page.context.close()
