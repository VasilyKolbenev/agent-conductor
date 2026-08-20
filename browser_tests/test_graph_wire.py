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
from playwright.sync_api import Browser, Page

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
        root, 0, registry=AdapterRegistry([DeepPlanAdapter()]),
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
_STREAM_DOUBLE = """
window.__streamOpens = 0;
class TestStream {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.onmessage = null;
    window.__stream = this;
    window.__streamOpens += 1;
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
            "graph-default.js", "graph-store.js", "graph-view.js",
            "command-projection.js", "command-view.js"}
        assert page.locator(".g-node").count() == 8
        # It opens on the default as a LOCAL DRAFT and says so before any run
        # is named: nothing durable is on screen until a run read puts it there.
        assert "LOCAL DRAFT" in page.locator("#sourceLine").inner_text()
        assert recorder.reads(DURABLE_RUN) == 0
    finally:
        page.context.close()


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


def test_the_runtime_word_screen_fires_and_spares_the_payload_it_must_spare(
        chromium: Browser, wire_url: str) -> None:
    """The screen in front of the write door, opened directly.

    It cannot fire on a body `graphRequestBody` builds today, because that
    body is assembled from a whitelist — which is the whole reason it exists
    and the whole reason it has to be proven here instead. A door nobody can
    open is not a door that works.

    The middle case is the one that would quietly break the product: every
    field of a capability's payload belongs to that capability's schema, and
    a walk that judged those keys too would refuse a plan the contract itself
    accepts. Production lifts the payload out by name before walking; so does
    this, and this is where that is checked.
    """
    page, _ = _open(chromium, wire_url)
    try:
        verdicts = page.evaluate(
            """async cases => {
                 const adapter = await import("./graph-adapter.js");
                 return cases.map(body => adapter.carriesRuntimeWord(body));
               }""",
            [
                {"graph_id": "g", "nodes": [{"node_id": "a", "kind": "task"}]},
                {"nodes": [{"node_id": "a", "phase": "idle"}]},
                {"nodes": [{"node_id": "a", "loop": {"bound": 2, "pass": 1}}]},
                {"nodes": [{"node_id": "a", "resources": [{"status": "ok"}]}]},
                {"nodes": [{"node_id": "a", "arguments": {
                    "phase": "x", "outcome": "succeeded"}}]},
            ])
        assert verdicts == [False, True, True, True, False]
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


def test_a_dropped_stream_rotates_the_session_the_next_write_must_use(
        chromium: Browser, wire_url: str) -> None:
    """A write may not ride a credential issued before the connection died.

    The count of session reads is the witness: the token is cached across
    writes, so a second session read can only mean the first was thrown away.
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
        assert len(recorder.matching("GET", "/command/session")) == 1
        page.evaluate("() => window.__stream.fire('error')")
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('Connection lost')")
        _save(page, GRAPH_ID)
        page.wait_for_function(
            "() => document.getElementById('saveStatus').innerText"
            ".includes('already stands')")
        assert len(recorder.matching("GET", "/command/session")) == 2
    finally:
        page.context.close()


def _read(page: Page, run_id: str) -> dict:
    """The authoritative run read, as the production route answers it."""
    return page.evaluate(
        "id => fetch(`/command/runs/${id}`, {cache: 'no-store'})"
        ".then(answer => answer.json())", run_id)


_VERDICT = """
  async payload => {
    const adapter = await import("./graph-adapter.js");
    const store = await import("./graph-store.js");
    const answer = adapter.adaptRunGraph(payload, []);
    if (answer.state !== "loaded") return `refused-at-adapter:${answer.state}`;
    return store.projectPayload(answer.payload) === null
      ? "refused-at-store" : "accepted";
  }
"""


def _fault(read: dict, path: tuple, changes: dict) -> dict:
    """Apply one change at one place and hand the whole document back.

    `changes` is a dict rather than keyword arguments because two of the wire's
    own field names -- `pass` among them -- are Python keywords, and a case
    that had to spell one differently would be testing a different key than
    the one it names.
    """
    target = read
    for step in path:
        target = target[step]
    target.update(changes)
    return read


#: One fault at a time, applied to the REAL document this server answers with.
#: The baseline is asserted accepted first, so a case can only be refused for
#: the fault it names -- and every name below is a mutation that must stay
#: refused for as long as the relation it cuts is a relation.
_WIRE_FAULTS = (
    ("one-graph-key-answered-null-on-its-own",
     lambda read: _fault(read, ("graph",), {"definition_digest": None})),
    ("a-digest-that-is-not-a-string",
     lambda read: _fault(read, ("graph",), {"definition_digest": 42})),
    ("a-schema-version-this-window-cannot-read",
     lambda read: _fault(read, ("graph", "definition"), {"schema_version": 3})),
    ("a-plan-about-another-run",
     lambda read: _fault(read, ("graph", "definition"), {"run_id": OTHER_RUN})),
    ("two-documents-naming-two-graphs",
     lambda read: _fault(read, ("graph", "runtime"), {"graph_id": "graph-x"})),
    ("an-unknown-key-on-the-plan",
     lambda read: _fault(read, ("graph", "definition"), {"provider": "claude"})),
    ("an-unknown-key-on-the-projection",
     lambda read: _fault(read, ("graph", "runtime"), {"digest": "sha256:x"})),
    ("a-plan-step-with-no-position",
     lambda read: read["graph"]["runtime"]["nodes"].pop() and read),
    ("a-position-for-a-step-no-plan-declares",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"node_id": "ghost"})),
    ("two-positions-for-one-step",
     lambda read: read["graph"]["runtime"]["nodes"].append(
         dict(read["graph"]["runtime"]["nodes"][0])) or read),
    ("a-runtime-phase-no-layer-owns",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"phase": "warming"})),
    # The first of these came back GREEN when it was written: the mapping READ
    # named fields, so a word out of place was DROPPED rather than refused,
    # and the drawing then claimed to be the whole document. Dropping is
    # repair. The adapter now screens every level before reading it, and
    # these five cases hold the class rather than the one instance found.
    ("a-decision-attached-to-a-step-that-is-no-gate",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"decision": "satisfied"})),
    ("a-pass-attached-to-a-step-that-is-no-loop",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0), {"pass": 1})),
    ("an-unknown-key-on-one-position",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"health": "ready"})),
    ("an-unknown-key-on-one-plan-step",
     lambda read: _fault(read, ("graph", "definition", "nodes", 0),
                         {"provider": "claude-code"})),
    ("an-unknown-key-inside-a-plan-steps-loop",
     lambda read: _fault(read, ("graph", "definition", "nodes", -1, "loop"),
                         {"pass": 1})),
    ("an-evidence-ref-that-is-not-an-identifier",
     lambda read: _fault(read, ("graph", "runtime", "nodes", 0),
                         {"evidence_refs": ["not an id!"]})),
    ("a-bound-reached-that-disagrees-with-the-plans-ceiling",
     lambda read: _fault(read, ("graph", "runtime", "nodes", -1),
                         {"bound_reached": True})),
    ("a-capability-this-window-carries-no-word-for",
     lambda read: _fault(read, ("graph", "definition", "nodes", 5),
                         {"capability": "teleport"})),
)


def test_each_wire_arm_refuses_its_own_single_fault(
        chromium: Browser, wire_url: str) -> None:
    """Refuse, never repair — on the document the real route produced.

    One page for the whole table, as the fixture boundary module does: each
    case re-reads the run, applies its one fault to that fresh document and
    asks the two boundaries in turn, so no case can be refused for the
    leftovers of the one before it.
    """
    page, _ = _open(chromium, wire_url)
    try:
        assert page.evaluate(_VERDICT, _read(page, DURABLE_RUN)) == "accepted", (
            "the unfaulted read must be accepted or no case below means anything")
        for name, apply in _WIRE_FAULTS:
            verdict = page.evaluate(_VERDICT, apply(_read(page, DURABLE_RUN)))
            assert verdict != "accepted", f"{name}: the boundary accepted it"
    finally:
        page.context.close()


#: The same discipline one layer in: each of these cuts the ONE-SOURCE rule
#: that keeps the plan and the run from being read as each other. They are
#: applied to the adapted payload, so the adapter has already agreed the two
#: wire documents are a pair -- what is on trial here is the store alone.
_PAYLOAD_FAULTS = (
    ("a-node-answering-from-both-documents",
     lambda payload: _fault(payload, ("nodes", 0), {"phase": "idle"})),
    ("a-node-answering-from-neither",
     lambda payload: _fault(payload, ("nodes", 0), {"runtime": None})),
    ("a-gate-whose-durable-answer-was-written-into-the-plans-key",
     lambda payload: _fault(payload, ("nodes", 4, "gate"),
                            {"state": "satisfied"})),
    ("a-loop-carrying-the-runs-pass-in-the-plans-key",
     lambda payload: _fault(payload, ("nodes", 7, "loop"), {"pass": 1})),
    ("an-evidence-row-invented-for-a-position-that-states-none",
     lambda payload: _fault(payload, ("nodes", 0), {"evidence": [
         {"evidence_id": "evidence-1", "kind": "result",
          "verification": "verified"}]})),
    ("a-durable-payload-with-no-digest",
     lambda payload: _fault(payload, ("provenance",), {"digest": None})),
    ("a-durable-payload-calling-itself-a-fixture",
     lambda payload: _fault(payload, ("provenance",), {"source": "fixture"})),
    ("a-fixture-payload-wearing-a-digest",
     lambda payload: _fault(payload, ("provenance",),
                            {"source": "fixture", "graphId": None})),
)


_ADAPT = """async payload => {
    const adapter = await import("./graph-adapter.js");
    return adapter.adaptRunGraph(payload, []).payload;
}"""
_PROJECT = """async payload => {
    const store = await import("./graph-store.js");
    return store.projectPayload(payload) === null;
}"""


def test_the_store_refuses_a_fact_that_answers_from_two_sources(
        chromium: Browser, wire_url: str) -> None:
    """The one-source rule, cut one way at a time and never surviving."""
    page, _ = _open(chromium, wire_url)
    try:
        read = _read(page, DURABLE_RUN)
        assert page.evaluate(_PROJECT, page.evaluate(_ADAPT, read)) is False, (
            "the adapted payload must project or no case below means anything")
        for name, apply in _PAYLOAD_FAULTS:
            faulted = apply(page.evaluate(_ADAPT, read))
            assert page.evaluate(_PROJECT, faulted) is True, (
                f"{name}: the store accepted the fault")
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
