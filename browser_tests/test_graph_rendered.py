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
        ".g-chip--wait").first.text_content() == "● health: busy"
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
    # The composer answers beside the composer, not in the page-top shell.
    assert "Nothing was executed" in graph_page.locator(
        "#composeStatus").inner_text()
    assert "Nothing was executed" not in graph_page.locator(
        "#notice").inner_text()
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


def _availability_registry() -> list[dict]:
    """The one registry, with fixture-side availability on six rows."""
    stated = {"claude-code": "available", "codex": "available",
              "deepseek-harness": "experimental", "kimi-code": "unavailable",
              "cursor": "available", "gemini-cli": "experimental"}
    rows = []
    for row in _registry_payload():
        extra = ({"availability": stated[row["id"]]}
                 if row["id"] in stated else {})
        rows.append({**row, **extra})
    return rows


def _load_provider_mix(page: Page) -> None:
    payload = dict(_FIXTURES["provider_mix"])
    payload["registry"] = _availability_registry()
    assert page.evaluate("payload => window.conductGraph.load(payload)", payload)


def test_six_providers_share_the_field_and_each_wears_its_own_accent(
        graph_page: Page) -> None:
    """Vendor difference is registry data: six accents, one code path."""
    _load_provider_mix(graph_page)
    dark = graph_page.evaluate(
        "matchMedia('(prefers-color-scheme: dark)').matches")
    field = "accent_dark" if dark else "accent_light"
    accents = {row["id"]: _hex_to_rgb(row[field]) for row in _registry_payload()}
    placed = {"plan": "claude-code", "impl-a": "codex",
              "impl-b": "deepseek-harness", "impl-c": "kimi-code",
              "probe": "gemini-cli", "review": "cursor"}
    seen = set()
    for node_id, harness in placed.items():
        swatch = graph_page.locator(f'[data-node-id="{node_id}"] .hb__m')
        colour = swatch.evaluate("n => getComputedStyle(n).borderTopColor")
        assert colour == accents[harness], (node_id, harness)
        seen.add(colour)
    assert len(seen) == 6, "six products must be six distinguishable accents"
    assert graph_page.locator('[data-node-id="ship-gate"] .hb__m').count() == 0


def test_availability_arrives_as_data_and_absence_claims_nothing(
        graph_page: Page) -> None:
    """available, experimental and unavailable are three distinct chips; a
    row that states none shows none."""
    _load_provider_mix(graph_page)
    palette = graph_page.locator("#paletteCard")
    for state, channel in (("available", "pass"), ("experimental", "wait"),
                           ("unavailable", "fail")):
        chips = palette.locator(f".g-chip--{channel}")
        texts = [chips.nth(i).text_content() for i in range(chips.count())]
        assert any(state in (text or "") for text in texts), state
    total = sum(
        1 for row in _availability_registry() if "availability" in row)
    assert palette.locator(
        ".g-chip--pass, .g-chip--wait, .g-chip--fail").count() == total
    # An out-of-vocabulary availability drops the row, as any ill-formed
    # presentational row is dropped: the harness keeps its neutral badge.
    payload = dict(_FIXTURES["provider_mix"])
    payload["registry"] = [
        {**row, "availability": "beta"} if row["id"] == "codex" else row
        for row in _availability_registry()]
    assert graph_page.evaluate(
        "payload => window.conductGraph.load(payload)", payload)
    assert graph_page.locator(
        '[data-node-id="impl-a"] .hb').get_attribute("style") is None
    assert graph_page.locator("#paletteCard").locator(
        ".g-palette__row").count() == len(_registry_payload()) - 1


def test_the_palette_claims_no_capability_for_any_product(
        graph_page: Page) -> None:
    """A capability is proven per node by the fixture or absent; the palette
    never presents one."""
    _load_provider_mix(graph_page)
    palette = graph_page.locator("#paletteCard").inner_text()
    for name in ("dispatch", "review", "evidence", "stop", "retry", "switch"):
        assert name not in palette, name


def test_no_viewport_lets_the_page_scroll_sideways_or_nodes_collide(
        graph_page: Page) -> None:
    """360, 768 and 1440: the page never scrolls horizontally (the field
    scrolls inside itself), and placed nodes never overlap."""
    _load_provider_mix(graph_page)
    for width in (360, 768, 1440):
        graph_page.set_viewport_size({"width": width, "height": 1200})
        assert graph_page.evaluate(
            "document.documentElement.scrollWidth"
            " <= document.documentElement.clientWidth"), width
        if width >= 768:
            geometry = graph_page.locator("#field").evaluate(_GEOMETRY)
            assert geometry["overlaps"] == 0, width


def test_every_form_control_offers_at_least_a_44px_target(
        graph_page: Page) -> None:
    """Measured boxes, not declared intent: composer and decision controls."""
    _load_provider_mix(graph_page)
    graph_page.locator('[data-node-id="ship-gate"]').click()
    controls = graph_page.locator(
        "#composerCard input, #composerCard select, #composerCard button,"
        " #detailCard input, #detailCard select, #detailCard button")
    assert controls.count() >= 9
    for index in range(controls.count()):
        box = controls.nth(index).bounding_box()
        assert box is not None and box["height"] >= 44, index
