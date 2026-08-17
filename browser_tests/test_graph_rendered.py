"""Rendered checks for the ALPHA-2 Graph window.

The Graph window has no production route yet — server.py is frozen until the
runtime side hands over its API fixtures — so this module serves the packaged
panel directory through its own static loopback server and feeds the window
through the one seam it exposes: ``window.conductGraph.load``. Everything a
test asserts here is what a person would see: rendered nodes, measured
geometry, computed styles, and the exact honesty strings beside local-only
actions.
"""
from __future__ import annotations

import http.server
import json
import threading
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

_REPO = Path(__file__).resolve().parents[1]
_PANEL = _REPO / "src" / "conductor" / "panel"
_FIXTURES = json.loads(
    (_REPO / "tests" / "fixtures" / "graph_alpha_fixtures.json")
    .read_text(encoding="utf-8"))
_CORPUS = json.loads(
    (_REPO / "tests" / "fixtures" / "utc_instant_parity_corpus.json")
    .read_text(encoding="utf-8"))
_MIME = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}


def _registry_payload() -> list[dict[str, str]]:
    """The bundled registry, guarded against resolving in another checkout."""
    from conductor import harnesses

    module = Path(harnesses.__file__).resolve()
    assert _REPO in module.parents, (
        f"conductor resolved outside this tree: {module}")
    return harnesses.as_payload()


class _PanelHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with explicit MIME types (Windows registries lie about .js)."""

    def guess_type(self, path: str) -> str:  # noqa: D102 — base contract
        for suffix, mime in _MIME.items():
            if str(path).endswith(suffix):
                return f"{mime}; charset=utf-8"
        return super().guess_type(path)

    def log_message(self, *_args: object) -> None:
        """Keep the pytest output to the assertions."""


@pytest.fixture(scope="session")
def graph_url() -> Iterator[str]:
    """Serve the packaged panel directory over a loopback static server."""
    handler = partial(_PanelHandler, directory=str(_PANEL))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/graph.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "graph static server did not stop"


@pytest.fixture(params=("dark", "light"))
def graph_page(chromium: Browser, graph_url: str,
               request: pytest.FixtureRequest) -> Iterator[Page]:
    """One isolated Graph window per approved colour scheme."""
    context = chromium.new_context(
        color_scheme=request.param,
        viewport={"width": 1440, "height": 1200},
    )
    page = context.new_page()
    page.goto(graph_url, wait_until="load")
    page.wait_for_function("Boolean(window.conductGraph)")
    try:
        yield page
    finally:
        context.close()


def _load(page: Page, name: str) -> None:
    """Feed one named fixture through the seam, registry injected as data."""
    payload = dict(_FIXTURES[name])
    payload["registry"] = _registry_payload()
    assert page.evaluate("payload => window.conductGraph.load(payload)", payload)


def test_the_graph_modules_boot_without_a_console_error_and_render_empty(
        chromium: Browser, graph_url: str) -> None:
    """Chromium resolves the module graph; the empty state names its honesty."""
    context = chromium.new_context(viewport={"width": 1440, "height": 1200})
    page = context.new_page()
    problems: list[str] = []
    served: list[tuple[str, int]] = []
    page.on("console", lambda message: problems.append(
        getattr(message, "text", ""))
        if getattr(message, "type", "") == "error" else None)
    page.on("pageerror", lambda error: problems.append(str(error)))
    page.on("response", lambda response: served.append(
        (response.url, response.status)))
    try:
        page.goto(graph_url, wait_until="load")
        page.wait_for_function("Boolean(window.conductGraph)")
        assert page.locator("#fieldEmpty").is_visible()
        assert "fixture data only" in page.locator("#notice").inner_text()
        assert page.locator(".g-node").count() == 0
        names = {url.rsplit("/", 1)[1]: status for url, status in served}
        assert names == {
            "graph.html": 200, "graph.css": 200, "graph.js": 200,
            "graph-store.js": 200, "graph-view.js": 200,
            "command-projection.js": 200, "command-view.js": 200,
        }
        assert problems == []
    finally:
        context.close()


def test_a_refused_payload_reports_refusal_and_loads_nothing(
        graph_page: Page) -> None:
    """The boundary refuses rather than repairs, and says so out loud."""
    accepted = graph_page.evaluate(
        "window.conductGraph.load({fixture_schema: 1, run: {run_id: 'r-1'},"
        " nodes: [{node_id: 'a'}], edges: [], timeline: []})")
    assert accepted is False
    assert "refused" in graph_page.locator("#notice").inner_text()
    assert graph_page.locator(".g-node").count() == 0


def test_the_store_utc_instant_grammar_answers_the_parity_corpus(
        graph_page: Page) -> None:
    """One corpus, three copies of the grammar — this one answers it too."""
    verdicts = graph_page.evaluate(
        """cases => import("./graph-store.js").then(store =>
             cases.map(row => store.instantIsValid(row.value)))""",
        _CORPUS)
    assert verdicts == [row["verdict"] == "accept" for row in _CORPUS]


def test_the_unregistered_monogram_rule_matches_the_registry_module(
        graph_page: Page) -> None:
    """graph-view's copy answers the same strings as conductor/harnesses.py."""
    from conductor import harnesses

    module = Path(harnesses.__file__).resolve()
    assert _REPO in module.parents
    ids = ["local-fork", "x", "Кодекс", "中文", "ß", "---", "one two three",
           "c++", "a-"]
    rendered = graph_page.evaluate(
        """ids => import("./graph-view.js").then(view =>
             ids.map(id => view.monogramOf(id)))""",
        ids)
    assert rendered == [harnesses.resolve(name).monogram for name in ids]


_GEOMETRY = """field => {
  const buttons = [...field.querySelectorAll(".g-node")];
  const centers = buttons.map(node => {
    const box = node.getBoundingClientRect();
    return {id: node.dataset.nodeId, box,
            x: box.left + box.width / 2, y: box.top + box.height / 2};
  });
  const nearest = point => centers.reduce((best, center) => {
    const distance = Math.hypot(center.x - point.x, center.y - point.y);
    return distance < best.distance ? {distance, id: center.id} : best;
  }, {distance: Infinity, id: null}).id;
  const links = [...field.querySelectorAll(".g-edge")].map(path => {
    const matrix = path.getScreenCTM(), length = path.getTotalLength();
    const at = offset => {
      const raw = path.getPointAtLength(offset);
      return new DOMPoint(raw.x, raw.y).matrixTransform(matrix);
    };
    return [nearest(at(0)), nearest(at(length))];
  });
  const overlaps = centers.flatMap((a, i) => centers.slice(i + 1).map(b =>
    a.box.left < b.box.right && a.box.right > b.box.left &&
    a.box.top < b.box.bottom && a.box.bottom > b.box.top
  )).filter(Boolean).length;
  const columns = {};
  for (const center of centers) {
    (columns[Math.round(center.box.left)] ||= []).push(center.id);
  }
  return {links, overlaps, columns: Object.values(columns)};
}"""


def test_a_parallel_fixture_renders_lanes_edges_and_no_overlap(
        graph_page: Page) -> None:
    """Three branches share one column; every edge connects its declared pair."""
    _load(graph_page, "parallel_review")
    assert graph_page.locator(".g-node").count() == 6
    assert graph_page.locator(".g-edge").count() == 7
    geometry = graph_page.locator("#field").evaluate(_GEOMETRY)
    assert geometry["overlaps"] == 0
    assert geometry["links"] == [
        ["plan", "impl-a"], ["plan", "impl-b"], ["plan", "impl-c"],
        ["impl-a", "review"], ["impl-b", "review"], ["impl-c", "review"],
        ["review", "ship-gate"],
    ]
    assert sorted(map(sorted, geometry["columns"]), key=len, reverse=True) == [
        ["impl-a", "impl-b", "impl-c"], ["plan"], ["review"], ["ship-gate"]]


def test_narrow_viewport_stacks_nodes_and_carries_edges_as_text(
        graph_page: Page) -> None:
    """At 360 the geometry leaves and the 'after …' words carry each edge."""
    _load(graph_page, "parallel_review")
    graph_page.set_viewport_size({"width": 360, "height": 1400})
    svg_display = graph_page.locator("#edges").evaluate(
        "svg => getComputedStyle(svg).display")
    assert svg_display == "none"
    positions = graph_page.locator("#field").evaluate(
        """field => [...field.querySelectorAll(".g-node")].map(node => ({
             id: node.dataset.nodeId,
             position: getComputedStyle(node).position,
             top: node.getBoundingClientRect().top}))""")
    assert [row["position"] for row in positions] == ["static"] * 6
    tops = [row["top"] for row in positions]
    assert tops == sorted(tops)
    origin = graph_page.locator('[data-node-id="impl-a"] .g-node__from')
    assert origin.is_visible()
    assert origin.inner_text() == "after plan"
    assert graph_page.locator(
        '[data-node-id="plan"] .g-node__from').inner_text() == "start"


def test_node_card_shows_provider_availability_capability_phase_evidence(
        graph_page: Page) -> None:
    """The five card facts arrive as data, registered or not."""
    _load(graph_page, "parallel_review")
    node = graph_page.locator('[data-node-id="impl-a"]')
    node.click()
    assert node.get_attribute("aria-pressed") == "true"
    detail = graph_page.locator("#detailCard")
    assert detail.locator(".g-det__title").inner_text() == "Implement lane A"
    assert detail.locator(".hb__n").first.inner_text() == "Claude Code"
    assert detail.locator(
        ".g-chip--wait").first.text_content() == "● availability: busy"
    assert "phase: requested" in detail.inner_text()
    # The fixture declares ["stop", "dispatch", "evidence"]; the sorted line
    # below is therefore the projection's doing, not the fixture's.
    assert "capabilities: dispatch, evidence, stop" in detail.inner_text()
    evidence = detail.locator(".g-evidence")
    assert evidence.count() == 1
    assert "diff ev-a-diff" in evidence.inner_text()
    assert "unverified" in evidence.inner_text()

    graph_page.locator('[data-node-id="impl-c"]').click()
    assert detail.locator(".hb__n").first.inner_text() == "local-fork"
    assert detail.locator(".hb__m").first.inner_text() == "LF"
    badge_style = detail.locator(".hb").first.get_attribute("style")
    assert not badge_style, "unregistered harness must keep the neutral badge"


def _hex_to_rgb(value: str) -> str:
    return f"rgb({int(value[1:3], 16)}, {int(value[3:5], 16)}, {int(value[5:7], 16)})"


def test_a_registered_accent_reaches_the_swatch_in_the_active_scheme(
        graph_page: Page) -> None:
    """The validated accent pair is not inert: the composited swatch wears it."""
    _load(graph_page, "parallel_review")
    dark = graph_page.evaluate(
        "matchMedia('(prefers-color-scheme: dark)').matches")
    row = next(r for r in _registry_payload() if r["id"] == "claude-code")
    expected = _hex_to_rgb(row["accent_dark" if dark else "accent_light"])
    swatch = graph_page.locator('[data-node-id="impl-a"] .hb__m')
    assert swatch.evaluate(
        "node => getComputedStyle(node).borderTopColor") == expected
    neutral = graph_page.locator('[data-node-id="impl-c"] .hb__m')
    assert neutral.evaluate(
        "node => getComputedStyle(node).borderTopColor") != expected


def test_docs_links_render_only_for_https_targets_and_leave_this_window(
        graph_page: Page) -> None:
    """A javascript: docs string is data that never becomes an anchor."""
    payload = dict(_FIXTURES["gate_satisfied"])
    payload["registry"] = [
        {"id": "honest", "display_name": "Honest", "monogram": "HO",
         "accent_dark": "#6ea8ff", "accent_light": "#2258c9",
         "docs": "https://example.com/docs"},
        {"id": "hostile", "display_name": "Hostile", "monogram": "HX",
         "accent_dark": "#63c8b3", "accent_light": "#176b5b",
         "docs": "javascript:document.title='pwned'"},
    ]
    assert graph_page.evaluate(
        "payload => window.conductGraph.load(payload)", payload)
    palette = graph_page.locator("#paletteCard")
    assert palette.locator(".g-palette__row").count() == 2
    anchors = palette.locator("a.hb__d")
    assert anchors.count() == 1
    assert anchors.get_attribute("href") == "https://example.com/docs"
    assert anchors.get_attribute("target") == "_blank"
    assert anchors.get_attribute("rel") == "noreferrer noopener"


def test_gate_decision_form_updates_the_gate_and_stays_fixture_only(
        graph_page: Page) -> None:
    """A refused draft keeps what was typed; a valid one lands locally only."""
    _load(graph_page, "parallel_review")
    graph_page.locator('[data-node-id="ship-gate"]').click()
    detail = graph_page.locator("#detailCard")
    assert "○ pending" in detail.inner_text()
    assert "Nothing is executed or sent" in detail.inner_text()
    form = detail.locator(".g-decide")
    form.locator('[name="action"]').select_option("request_changes")
    form.locator('[name="actor"]').fill("reviewer-1")
    form.locator('button[type="submit"]').click()
    assert "give a reason" in detail.locator(".g-decide-status").inner_text()
    # The refusal changed nothing durable and erased nothing typed: the gate
    # is still pending, the ledger is empty, the draft survived the
    # re-render, and focus stayed on the control that submitted.
    assert graph_page.evaluate("window.conductGraph.state().decisions") == {}
    assert "○ pending" in detail.inner_text()
    form = detail.locator(".g-decide")
    assert form.locator('[name="action"]').input_value() == "request_changes"
    assert form.locator('[name="actor"]').input_value() == "reviewer-1"
    assert graph_page.evaluate(
        "document.activeElement.getAttribute('name')") == "record"

    form.locator('[name="reason"]').fill("needs tests")
    form.locator('button[type="submit"]').click()
    assert "Nothing was executed" in detail.locator(
        ".g-decide-status").inner_text()
    gates = graph_page.locator("#gatesCard")
    assert "■ changes requested" in gates.inner_text()
    assert "by reviewer-1 (fixture-only)" in gates.inner_text()
    assert "■ changes requested" in graph_page.locator(
        '[data-node-id="ship-gate"]').inner_text()
    recorded = graph_page.evaluate("window.conductGraph.state().decisions")
    assert recorded == {"gate-release": {
        "action": "request_changes", "actor": "reviewer-1",
        "reason": "needs tests", "recorded": "fixture-only"}}
    # A landed decision clears the draft for the next one.
    assert graph_page.locator('[name="actor"]').input_value() == ""

    _load(graph_page, "gate_satisfied")
    assert "✓ approved" in graph_page.locator("#gatesCard").inner_text()


def test_composer_adds_a_parallel_step_as_data_and_keeps_geometry_closed(
        graph_page: Page) -> None:
    """A composed step is fixture data: placed, drawn, and executed nowhere."""
    _load(graph_page, "parallel_review")
    form = graph_page.locator("#composerCard .g-compose")
    form.locator('[name="title"]').fill("Shadow review")
    form.locator('[name="harness"]').select_option("codex")
    form.locator('[name="placement"]').select_option("parallel")
    form.locator('[name="anchor"]').select_option("impl-a")
    form.locator('button[type="submit"]').click()
    assert "Nothing was executed" in graph_page.locator("#notice").inner_text()
    assert graph_page.locator(".g-node").count() == 7
    added = graph_page.locator('[data-node-id="step-7"]')
    assert "Shadow review" in added.inner_text()
    # Clipped at 1440 (the SVG carries the edge there); the fact still holds.
    assert added.locator(".g-node__from").text_content() == "after plan"
    geometry = graph_page.locator("#field").evaluate(_GEOMETRY)
    assert geometry["overlaps"] == 0
    assert ["plan", "step-7"] in geometry["links"]
    # A landed composition clears the drafted title for the next step.
    assert graph_page.locator('[name="title"]').input_value() == ""


def test_a_composer_draft_survives_selecting_a_node_mid_thought(
        graph_page: Page) -> None:
    """Inspecting a node to pick an anchor must not erase the typed step."""
    _load(graph_page, "parallel_review")
    graph_page.locator('[name="title"]').fill("Half-typed step")
    graph_page.locator('[name="placement"]').select_option("parallel")
    graph_page.locator('[data-node-id="impl-b"]').click()
    assert graph_page.locator('[name="title"]').input_value() == "Half-typed step"
    assert graph_page.locator('[name="placement"]').input_value() == "parallel"


def test_selecting_a_node_keeps_focus_on_that_node_through_the_rerender(
        graph_page: Page) -> None:
    """A keyboard selection must not drop the Human to the document body."""
    _load(graph_page, "parallel_review")
    node = graph_page.locator('[data-node-id="impl-b"]')
    node.focus()
    graph_page.keyboard.press("Enter")
    assert node.get_attribute("aria-pressed") == "true"
    assert graph_page.evaluate(
        "document.activeElement.dataset.nodeId") == "impl-b"


def test_the_seam_is_load_and_state_and_nothing_else(graph_page: Page) -> None:
    """No public door may commit facts that skipped the boundary."""
    assert graph_page.evaluate(
        "Object.keys(window.conductGraph).sort()") == ["load", "state"]


def test_timeline_and_palette_render_every_row_the_fixture_holds(
        graph_page: Page) -> None:
    """The two cards are rendered claims, not dead fixture weight."""
    _load(graph_page, "parallel_review")
    rows = graph_page.locator("#timelineCard .g-timeline__row")
    assert rows.count() == 5
    assert "plan" in rows.first.inner_text()
    assert "2026-08-17T09:00:00Z" in rows.first.inner_text()
    assert "impl-c" in rows.last.inner_text()
    assert graph_page.locator("#paletteCard .g-palette__row").count() == len(
        _registry_payload())


def test_a_refused_load_clears_the_previous_canvas(graph_page: Page) -> None:
    """The last graph's SVG must not outlive the state that drew it."""
    _load(graph_page, "parallel_review")
    assert graph_page.locator("#edges").get_attribute("width") is not None
    assert not graph_page.evaluate("window.conductGraph.load({})")
    assert graph_page.locator("#edges").get_attribute("width") is None
    assert graph_page.locator(".g-edge").count() == 0
    assert graph_page.locator(".g-node").count() == 0


def _one_fault_cases() -> list[tuple[str, object]]:
    """One structural fault per case, applied to a copy of parallel_review."""
    def fault(name: str, apply) -> tuple[str, object]:
        return (name, apply)

    return [
        fault("wrong-schema", lambda p: p.update(fixture_schema=2)),
        fault("bad-run-id", lambda p: p["run"].update(run_id="bad id!")),
        fault("health-out-of-vocab", lambda p: p["nodes"][0].update(health="excellent")),
        fault("phase-out-of-vocab", lambda p: p["nodes"][0].update(phase="running")),
        fault("kind-out-of-vocab", lambda p: p["nodes"][0].update(kind="step")),
        fault("title-over-limit", lambda p: p["nodes"][0].update(title="x" * 81)),
        fault("title-blank", lambda p: p["nodes"][0].update(title="   ")),
        fault("capability-duplicate",
              lambda p: p["nodes"][1].update(capabilities=["dispatch", "dispatch"])),
        fault("capability-out-of-vocab",
              lambda p: p["nodes"][1].update(capabilities=["deploy"])),
        fault("evidence-kind", lambda p: p["nodes"][1]["evidence"][0].update(kind="log")),
        fault("evidence-verification",
              lambda p: p["nodes"][1]["evidence"][0].update(verification="maybe")),
        fault("gate-on-task",
              lambda p: p["nodes"][0].update(gate={"gate_id": "g-x", "state": "pending"})),
        fault("gate-missing-on-gate", lambda p: p["nodes"][5].update(gate=None)),
        fault("gate-state-out-of-vocab",
              lambda p: p["nodes"][5]["gate"].update(state="open")),
        fault("duplicate-node-id", lambda p: p["nodes"][1].update(node_id="plan")),
        fault("duplicate-gate-id", lambda p: p["nodes"].append(
            {**p["nodes"][5], "node_id": "ship-gate-2"})),
        fault("dangling-edge", lambda p: p["edges"].append(
            {"from": "ghost", "to": "review"})),
        fault("duplicate-edge", lambda p: p["edges"].append(dict(p["edges"][0]))),
        fault("self-loop", lambda p: p["edges"].append({"from": "plan", "to": "plan"})),
        fault("cycle", lambda p: p["edges"].append({"from": "ship-gate", "to": "plan"})),
        fault("bad-instant", lambda p: p["timeline"][0].update(at="2026-02-30T09:00:00Z")),
        fault("timeline-ghost-node", lambda p: p["timeline"][0].update(node_id="ghost")),
        fault("duplicate-event-id", lambda p: p["timeline"][1].update(
            event_id=p["timeline"][0]["event_id"])),
        fault("timeline-phase-out-of-vocab",
              lambda p: p["timeline"][0].update(phase="warming")),
    ]


def test_each_boundary_arm_refuses_its_own_single_fault(
        graph_page: Page) -> None:
    """One fault per payload, so no refusal can hide behind a neighbour's."""
    registry = _registry_payload()
    for name, apply in _one_fault_cases():
        payload = json.loads(json.dumps(_FIXTURES["parallel_review"]))
        payload["registry"] = registry
        apply(payload)
        accepted = graph_page.evaluate(
            "payload => window.conductGraph.load(payload)", payload)
        assert accepted is False, f"{name}: the boundary accepted the fault"
        assert graph_page.locator(".g-node").count() == 0, name
    # The unfaulted copy still loads, so every refusal above was the fault's.
    payload = json.loads(json.dumps(_FIXTURES["parallel_review"]))
    payload["registry"] = registry
    assert graph_page.evaluate(
        "payload => window.conductGraph.load(payload)", payload)


_STORE_UNIT = """([payload, event]) => import("./graph-store.js").then(store => {
  const facts = store.projectPayload(payload);
  if (!facts) return {loaded: false};
  const loaded = store.reduce(store.EMPTY, {type: "loaded", facts});
  const next = store.reduce(loaded, event);
  return {
    loaded: true,
    notice: next.notice,
    decisionNotice: next.decisionNotice,
    nodes: next.nodes.length,
    gateStates: next.nodes.flatMap(n => n.gate ? [n.gate.state] : []),
    decisions: Object.keys(next.decisions),
    timeline: next.timeline.map(row => row.event_id),
  };
})"""


def test_the_reducer_refuses_what_the_forms_cannot_send(
        graph_page: Page) -> None:
    """The compose and decide arms hold even against events no UI can build."""
    payload = dict(_FIXTURES["parallel_review"])
    payload["registry"] = _registry_payload()
    cases = [
        ({"type": "compose", "nodeId": "step-x", "title": "T",
          "harness": "not-registered", "placement": "after",
          "anchorId": "plan"}, "unregistered harness"),
        ({"type": "compose", "nodeId": "plan", "title": "T", "harness": None,
          "placement": "after", "anchorId": "review"}, "duplicate node id"),
        ({"type": "compose", "nodeId": "step-x", "title": "x" * 81,
          "harness": None, "placement": "after", "anchorId": "plan"},
         "over-limit title"),
        ({"type": "compose", "nodeId": "step-x", "title": "T", "harness": None,
          "placement": "sideways", "anchorId": "plan"}, "unknown placement"),
    ]
    for event, why in cases:
        result = graph_page.evaluate(_STORE_UNIT, [payload, event])
        assert result["loaded"], why
        assert result["nodes"] == 6, why
        assert "Composition refused" in result["notice"], why
    for event, why in [
        ({"type": "decide", "gateId": "gate-release", "action": "constructor",
          "actor": "reviewer-1", "reason": ""}, "inherited action name"),
        ({"type": "decide", "gateId": "gate-release", "action": "approve",
          "actor": "reviewer-1", "reason": "x" * 201}, "over-limit reason"),
    ]:
        result = graph_page.evaluate(_STORE_UNIT, [payload, event])
        assert result["gateStates"] == ["pending"], why
        assert result["decisions"] == [], why
        assert "Name the deciding Human" in result["decisionNotice"], why


def test_a_selection_change_dismisses_the_recorded_decision_status(
        graph_page: Page) -> None:
    """The status names the gate on screen when it was made, or nothing."""
    _load(graph_page, "parallel_review")
    graph_page.locator('[data-node-id="ship-gate"]').click()
    form = graph_page.locator("#detailCard .g-decide")
    form.locator('[name="actor"]').fill("reviewer-1")
    form.locator('button[type="submit"]').click()
    status = graph_page.locator("#decideStatus")
    assert "Decision recorded" in status.inner_text()
    graph_page.locator('[data-node-id="plan"]').click()
    assert status.inner_text() == ""


def test_fractional_instants_order_by_time_not_by_string(
        graph_page: Page) -> None:
    """…00Z sorts before …00.900Z even though the strings say otherwise."""
    payload = json.loads(json.dumps(_FIXTURES["gate_satisfied"]))
    payload["registry"] = _registry_payload()
    payload["timeline"] = [
        {"event_id": "t-frac", "at": "2026-08-17T09:00:00.900Z",
         "node_id": "plan", "phase": "requested"},
        {"event_id": "t-whole", "at": "2026-08-17T09:00:00Z",
         "node_id": "plan", "phase": "proposed"},
        {"event_id": "t-offset", "at": "2026-08-17T08:59:59+00:00",
         "node_id": "plan", "phase": "idle"},
    ]
    result = graph_page.evaluate(_STORE_UNIT, [payload, {"type": "deselect"}])
    assert result["timeline"] == ["t-offset", "t-whole", "t-frac"]
