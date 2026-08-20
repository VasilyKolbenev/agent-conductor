"""Rendered checks for the Graph window's FIXTURE path.

The window is opened at its production route, ``/panel/graph.html``, served
by the real loopback server from the allowlist of literal names in
``server.py`` — the static stand-in this module used while no route existed
is gone, and with it the last place the served copy could differ from the
packaged one. What this module still feeds the window is a fixture, through
the one seam ``window.conductGraph.load``; the durable wire is driven in
``browser_tests/test_graph_wire.py``. Everything a test asserts here is what
a person would see: rendered nodes, measured geometry, computed styles, and
the exact honesty strings beside local-only actions.
"""
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page

from conductor import server

from tests.test_store import good_lane, write_project

_REPO = Path(__file__).resolve().parents[1]
_FIXTURES = json.loads(
    (_REPO / "tests" / "fixtures" / "graph_alpha_fixtures.json")
    .read_text(encoding="utf-8"))
_CORPUS = json.loads(
    (_REPO / "tests" / "fixtures" / "utc_instant_parity_corpus.json")
    .read_text(encoding="utf-8"))


def _registry_payload() -> list[dict[str, str]]:
    """The bundled registry, guarded against resolving in another checkout."""
    from conductor import harnesses

    module = Path(harnesses.__file__).resolve()
    assert _REPO in module.parents, (
        f"conductor resolved outside this tree: {module}")
    return harnesses.as_payload()


@pytest.fixture(scope="session")
def graph_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Serve the Graph window from the real production panel route."""
    root = write_project(tmp_path_factory.mktemp("graph-panel"),
                         lanes={"claude": good_lane()})
    httpd = server.build(root, 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    try:
        yield f"http://{host}:{port}/panel/graph.html"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive(), "graph server did not stop"


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


def test_the_graph_modules_boot_into_the_dalio_default_without_an_error(
        chromium: Browser, graph_url: str) -> None:
    """Chromium resolves the module graph and the window opens on the
    product's default five-step graph, loaded through the public seam."""
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
        assert not page.locator("#fieldEmpty").is_visible()
        assert page.locator(".g-node").count() == 8
        assert "run-dalio-default" in page.locator("#runFacts").inner_text()
        # The boot state says what it is: a fixture, reaching no server —
        # and the default ships an EMPTY registry, never a second copy of
        # vendor rows.
        assert page.locator("#runFacts").inner_text().endswith("· fixture")
        assert "Nothing here reaches a server" in page.locator(
            "#notice").inner_text()
        assert page.evaluate("window.conductGraph.state().registry") == []
        assert "No registry rows in this payload." in page.locator(
            "#paletteCard").inner_text()
        # Exactly the module graph, each file answered by the production
        # allowlist under its own literal name. The stream this window also
        # opens is not asserted here: its response arrives when it arrives,
        # and a count that waits on it would be a timing test.
        names = {url.rsplit("/", 1)[1]: status for url, status in served
                 if "/panel/" in url}
        assert names == {
            "graph.html": 200, "graph.css": 200, "graph.js": 200,
            "graph-adapter.js": 200, "graph-default.js": 200,
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
  const lefts = Object.fromEntries(
    centers.map(center => [center.id, center.box.left]));
  return {links, overlaps, columns: Object.values(columns), lefts};
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


def test_gate_decision_form_updates_the_gate_and_stays_window_only(
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
    assert "LOCAL DRAFT by reviewer-1 — not submitted" in gates.inner_text()
    assert "■ changes requested" in graph_page.locator(
        '[data-node-id="ship-gate"]').inner_text()
    recorded = graph_page.evaluate("window.conductGraph.state().decisions")
    assert recorded == {"gate-release": {
        "action": "request_changes", "actor": "reviewer-1",
        "reason": "needs tests", "recorded": "window-only"}}
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
    # The label is the vocabulary word in capitals — EXPERIMENTAL and
    # UNAVAILABLE must be unmistakable at a glance. Equality on the label
    # span, not containment: "AVAILABLE" is a substring of "UNAVAILABLE",
    # and this assertion must be able to tell them apart.
    for state, channel in (("AVAILABLE", "pass"), ("EXPERIMENTAL", "wait"),
                           ("UNAVAILABLE", "fail")):
        chips = palette.locator(f".g-chip--{channel}")
        labels = [chips.nth(i).locator("span").last.text_content()
                  for i in range(chips.count())]
        assert set(labels) == {state}, (state, labels)
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


def test_the_default_graph_is_dalios_five_steps_in_their_one_order(
        graph_page: Page) -> None:
    """Five numbered stages, each its own node: Identify never absorbs
    Diagnose, and the order is the process's, not the renderer's."""
    stages = graph_page.locator(".g-stage")
    assert [stages.nth(i).inner_text() for i in range(stages.count())] == [
        "1/5 · goal", "2/5 · identify", "3/5 · diagnose", "4/5 · design",
        "5/5 · do"]
    titles = {row["node_id"]: row["title"] for row in graph_page.evaluate(
        "window.conductGraph.state().nodes.map(n =>"
        " ({node_id: n.node_id, title: n.title, stage: n.stage}))")}
    assert titles["identify"] == "Identify Problems"
    assert titles["diagnose"] == "Diagnose Root Causes"
    geometry = graph_page.locator("#field").evaluate(_GEOMETRY)
    assert geometry["overlaps"] == 0
    assert geometry["links"] == [
        ["goal", "identify"], ["identify", "diagnose"],
        ["diagnose", "design"], ["design", "confirm-gate"],
        ["confirm-gate", "do"], ["do", "result-gate"],
        ["result-gate", "retry-loop"]]
    # Rendered left-to-right, not merely declared in order: a column remap
    # that mirrored or shuffled the flow would pass every link check while
    # drawing Do first. The measured x-positions are the process's order.
    lefts = geometry["lefts"]
    chain = ["goal", "identify", "diagnose", "design", "confirm-gate",
             "do", "result-gate", "retry-loop"]
    assert all(lefts[a] < lefts[b] for a, b in zip(chain, chain[1:])), lefts
    # The card names the stage the same way the node does.
    graph_page.locator('[data-node-id="do"]').click()
    assert "stage 5 of 5 — do" in graph_page.locator(
        "#detailCard").inner_text()


def test_do_is_the_only_effect_capable_step_and_sits_behind_its_own_gate(
        graph_page: Page) -> None:
    """One dispatch in the whole graph, and no path reaches it around the
    Human gate."""
    nodes = graph_page.evaluate(
        "window.conductGraph.state().nodes.map(n =>"
        " ({id: n.node_id, caps: n.capabilities}))")
    effectful = [row["id"] for row in nodes if "dispatch" in row["caps"]]
    assert effectful == ["do"]
    edges = graph_page.evaluate("window.conductGraph.state().edges")
    into_do = [edge["from"] for edge in edges if edge["to"] == "do"]
    assert into_do == ["confirm-gate"]
    assert {"from": "design", "to": "do"} not in edges


def test_the_loop_reopens_identify_and_never_executes(
        graph_page: Page) -> None:
    """pass 1/3 on the node; the card names the reopened step and the rule."""
    loop = graph_page.locator('[data-node-id="retry-loop"]')
    assert loop.locator(".g-loop-bound").inner_text() == "↻ pass 1/3"
    nodes = graph_page.evaluate(
        "window.conductGraph.state().nodes.map(n =>"
        " ({id: n.node_id, caps: n.capabilities, loop: n.loop}))")
    retry = next(row for row in nodes if row["id"] == "retry-loop")
    assert "dispatch" not in retry["caps"]
    assert retry["loop"] == {"bound": 3, "pass": 1, "backTo": "identify"}
    edges = graph_page.evaluate("window.conductGraph.state().edges")
    assert not [edge for edge in edges if edge["from"] == "retry-loop"]
    loop.click()
    detail = graph_page.locator("#detailCard")
    assert "pass 1 of 3" in detail.inner_text()
    assert "reopens: Identify Problems" in detail.inner_text()
    assert "it executes nothing" in detail.inner_text()
    assert "fresh Confirm" in detail.inner_text()


def test_the_default_never_claims_completion_without_a_verified_result(
        graph_page: Page) -> None:
    """Both gates pend, Do is idle with no evidence: nothing reads as done."""
    nodes = {row["id"]: row for row in graph_page.evaluate(
        "window.conductGraph.state().nodes.map(n => ({id: n.node_id,"
        " phase: n.phase, evidence: n.evidence,"
        " gate: n.gate ? n.gate.state : null}))")}
    assert nodes["do"]["phase"] == "idle" and nodes["do"]["evidence"] == []
    assert nodes["confirm-gate"]["gate"] == "pending"
    assert nodes["result-gate"]["gate"] == "pending"
    assert "✓ approved" not in graph_page.locator("#gatesCard").inner_text()


def test_the_default_spreads_the_steps_across_different_products(
        graph_page: Page) -> None:
    """Provider-neutrality shown, not claimed: four products hold the five
    stages as data, with no vendor branch to render any of them."""
    nodes = graph_page.evaluate(
        "window.conductGraph.state().nodes.map(n =>"
        " ({stage: n.stage, harness: n.harness}))")
    staffed = {row["stage"]: row["harness"] for row in nodes if row["stage"]}
    assert len(set(staffed.values())) >= 4
    assert staffed["do"] == "kimi-code"


def test_a_bounded_loop_renders_its_bound_and_the_field_stays_a_dag(
        graph_page: Page) -> None:
    """The one sanctioned cycle shape: an explicit loop step saying ×N."""
    _load(graph_page, "loop_and_resources")
    loop = graph_page.locator('[data-node-id="fix-loop"]')
    assert "g-node--loop" in (loop.get_attribute("class") or "")
    assert loop.locator(".g-loop-bound").inner_text() == "↻ ×3"
    geometry = graph_page.locator("#field").evaluate(_GEOMETRY)
    assert geometry["overlaps"] == 0
    assert geometry["links"] == [
        ["plan", "fix-loop"], ["fix-loop", "verify"], ["verify", "ship-gate"]]
    loop.click()
    detail = graph_page.locator("#detailCard")
    assert "bounded loop · at most ×3 passes" in detail.inner_text()


def test_resources_render_as_closed_attachments_of_their_node(
        graph_page: Page) -> None:
    """Configuration arrives as {kind, name} rows; absence claims nothing."""
    _load(graph_page, "loop_and_resources")
    graph_page.locator('[data-node-id="plan"]').click()
    detail = graph_page.locator("#detailCard")
    rows = detail.locator(".g-resources li")
    assert [rows.nth(i).inner_text() for i in range(rows.count())] == [
        "model: opus-5", "skill: writing-plans", "filesystem: workspace-ro"]
    graph_page.locator('[data-node-id="fix-loop"]').click()
    rows = detail.locator(".g-resources li")
    assert [rows.nth(i).inner_text() for i in range(rows.count())] == [
        "tool: pytest", "sandbox: worktree-a", "session: sess-41"]
    graph_page.locator('[data-node-id="verify"]').click()
    assert detail.locator(".g-resources").count() == 0
    assert "Resources" not in detail.inner_text()
    # A boundary-legal name is 128 unbroken characters; the row wraps it
    # rather than widening the page at 360.
    payload = json.loads(json.dumps(_FIXTURES["loop_and_resources"]))
    payload["registry"] = _registry_payload()
    payload["nodes"][0]["resources"] = [
        {"kind": "filesystem", "name": "a" * 128}]
    assert graph_page.evaluate(
        "payload => window.conductGraph.load(payload)", payload)
    graph_page.locator('[data-node-id="plan"]').click()
    graph_page.set_viewport_size({"width": 360, "height": 1400})
    assert graph_page.evaluate(
        "document.documentElement.scrollWidth"
        " <= document.documentElement.clientWidth")


def test_a_composed_step_wears_the_local_draft_label_everywhere_it_lands(
        graph_page: Page) -> None:
    """Nothing composed here may read as durable or submitted."""
    _load(graph_page, "loop_and_resources")
    form = graph_page.locator("#composerCard .g-compose")
    form.locator('[name="title"]').fill("Shadow check")
    form.locator('[name="anchor"]').select_option("verify")
    form.locator('button[type="submit"]').click()
    assert "LOCAL DRAFT" in graph_page.locator("#composeStatus").inner_text()
    added = graph_page.locator('[data-node-id="step-5"]')
    assert "LOCAL DRAFT" in added.inner_text()
    added.click()
    # "written to no run", not "submitted nowhere": a save door exists now,
    # and the label has to be true beside it — this step is held here and has
    # not been written, which is a narrower and still honest claim.
    assert "LOCAL DRAFT — held in this window, written to no run" in \
        graph_page.locator("#detailCard").inner_text()
    # Fixture-fed steps carry no such label: the claim is drafts-only.
    assert "LOCAL DRAFT" not in graph_page.locator(
        '[data-node-id="plan"]').inner_text()
    # The anchor dropdown is a landing surface too, and must say it there.
    options = graph_page.locator('[name="anchor"] option')
    texts = [options.nth(i).text_content() for i in range(options.count())]
    assert "Shadow check — LOCAL DRAFT" in texts
    assert "Plan the slice" in texts
    # And the sentence-length draft chip wraps: composing and selecting a
    # draft at 360 must not widen the page.
    graph_page.set_viewport_size({"width": 360, "height": 1400})
    assert graph_page.evaluate(
        "document.documentElement.scrollWidth"
        " <= document.documentElement.clientWidth")


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
