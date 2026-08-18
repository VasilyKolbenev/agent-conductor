"""The Graph window's closed fixture boundary, attacked in a real Chromium.

Split from test_graph_rendered.py when that module crossed the 800-line cap:
this file is the self-contained boundary circuit — every way a payload can be
refused, and the proof that a refusal neither leaks a string into the DOM nor
leaves a partial state behind. The rendering circuit (geometry, cards,
forms, providers) stays in test_graph_rendered.py, which also owns the
static server and page fixtures this module imports.
"""
from __future__ import annotations

import json

from playwright.sync_api import Page

from browser_tests.test_graph_rendered import (  # noqa: F401 — fixtures register
    _FIXTURES, _load, _registry_payload, graph_page, graph_url)


def test_a_refused_payload_reports_refusal_and_loads_nothing(
        graph_page: Page) -> None:
    """The boundary refuses rather than repairs, and says so out loud."""
    accepted = graph_page.evaluate(
        "window.conductGraph.load({fixture_schema: 1, run: {run_id: 'r-1'},"
        " nodes: [{node_id: 'a'}], edges: [], timeline: []})")
    assert accepted is False
    assert "refused" in graph_page.locator("#notice").inner_text()
    assert graph_page.locator(".g-node").count() == 0


def test_the_seam_is_load_and_state_and_nothing_else(graph_page: Page) -> None:
    """No public door may commit facts that skipped the boundary."""
    assert graph_page.evaluate(
        "Object.keys(window.conductGraph).sort()") == ["load", "state"]


def test_a_refused_load_clears_the_previous_canvas(graph_page: Page) -> None:
    """The last graph's SVG must not outlive the state that drew it."""
    _load(graph_page, "parallel_review")
    assert graph_page.locator("#edges").get_attribute("width") is not None
    assert not graph_page.evaluate("window.conductGraph.load({})")
    assert graph_page.locator("#edges").get_attribute("width") is None
    assert graph_page.locator(".g-edge").count() == 0
    assert graph_page.locator(".g-node").count() == 0


#: One structural fault per case, applied to a fresh copy of parallel_review.
#: The last block closes the boundary by key, level by level: an unknown field
#: is schema drift and is refused, never carried, at every depth — including
#: keys that are prototype names on an honest object.
_ONE_FAULT_CASES = [
    ("wrong-schema", lambda p: p.update(fixture_schema=2)),
    ("bad-run-id", lambda p: p["run"].update(run_id="bad id!")),
    ("health-out-of-vocab", lambda p: p["nodes"][0].update(health="excellent")),
    ("phase-out-of-vocab", lambda p: p["nodes"][0].update(phase="running")),
    ("kind-out-of-vocab", lambda p: p["nodes"][0].update(kind="step")),
    ("title-over-limit", lambda p: p["nodes"][0].update(title="x" * 81)),
    ("title-blank", lambda p: p["nodes"][0].update(title="   ")),
    ("capability-duplicate",
     lambda p: p["nodes"][1].update(capabilities=["dispatch", "dispatch"])),
    ("capability-out-of-vocab",
     lambda p: p["nodes"][1].update(capabilities=["deploy"])),
    ("evidence-kind", lambda p: p["nodes"][1]["evidence"][0].update(kind="log")),
    ("evidence-verification",
     lambda p: p["nodes"][1]["evidence"][0].update(verification="maybe")),
    ("gate-on-task",
     lambda p: p["nodes"][0].update(gate={"gate_id": "g-x", "state": "pending"})),
    ("gate-missing-on-gate", lambda p: p["nodes"][5].update(gate=None)),
    ("gate-state-out-of-vocab",
     lambda p: p["nodes"][5]["gate"].update(state="open")),
    ("duplicate-node-id", lambda p: p["nodes"][1].update(node_id="plan")),
    ("duplicate-gate-id", lambda p: p["nodes"].append(
        {**p["nodes"][5], "node_id": "ship-gate-2"})),
    ("dangling-edge", lambda p: p["edges"].append(
        {"from": "ghost", "to": "review"})),
    ("duplicate-edge", lambda p: p["edges"].append(dict(p["edges"][0]))),
    ("self-loop", lambda p: p["edges"].append({"from": "plan", "to": "plan"})),
    ("cycle", lambda p: p["edges"].append({"from": "ship-gate", "to": "plan"})),
    ("bad-instant", lambda p: p["timeline"][0].update(at="2026-02-30T09:00:00Z")),
    ("timeline-ghost-node", lambda p: p["timeline"][0].update(node_id="ghost")),
    ("duplicate-event-id", lambda p: p["timeline"][1].update(
        event_id=p["timeline"][0]["event_id"])),
    ("timeline-phase-out-of-vocab",
     lambda p: p["timeline"][0].update(phase="warming")),
    ("unknown-top-level-key", lambda p: p.update(queue="fifo")),
    ("unknown-run-key", lambda p: p["run"].update(endpoint="http://x")),
    ("unknown-node-key", lambda p: p["nodes"][0].update(argv=["--x"])),
    ("unknown-gate-key",
     lambda p: p["nodes"][5]["gate"].update(webhook="https://x")),
    ("unknown-evidence-key",
     lambda p: p["nodes"][1]["evidence"][0].update(path="C:/x")),
    ("unknown-edge-key", lambda p: p["edges"][0].update(weight=2)),
    ("unknown-timeline-key",
     lambda p: p["timeline"][0].update(detail="raw")),
    ("prototype-key-on-node",
     lambda p: p["nodes"][0].update(__proto__={"kind": "task"})),
    ("prototype-key-top-level", lambda p: p.update(constructor="x")),
    ("run-id-missing", lambda p: p["run"].pop("run_id")),
    ("loop-on-task", lambda p: p["nodes"][0].update(loop={"bound": 3})),
    ("loop-kind-without-bound", lambda p: p["nodes"][4].update(kind="loop")),
    ("loop-bound-zero",
     lambda p: p["nodes"][4].update(kind="loop", loop={"bound": 0})),
    ("loop-bound-unbounded",
     lambda p: p["nodes"][4].update(kind="loop", loop={"bound": 100})),
    ("loop-bound-fractional",
     lambda p: p["nodes"][4].update(kind="loop", loop={"bound": 2.5})),
    ("loop-unknown-key", lambda p: p["nodes"][4].update(
        kind="loop", loop={"bound": 2, "body": ["impl-a"]})),
    ("resource-kind-out-of-vocab",
     lambda p: p["nodes"][0].update(resources=[{"kind": "gpu", "name": "a100"}])),
    ("resource-name-with-a-path", lambda p: p["nodes"][0].update(
        resources=[{"kind": "filesystem", "name": "C:/secrets"}])),
    ("resource-unknown-key", lambda p: p["nodes"][0].update(
        resources=[{"kind": "model", "name": "m", "uri": "https://x"}])),
    ("resource-duplicate-row", lambda p: p["nodes"][0].update(
        resources=[{"kind": "tool", "name": "pytest"},
                   {"kind": "tool", "name": "pytest"}])),
    ("resources-not-a-list",
     lambda p: p["nodes"][0].update(resources="model")),
]


def test_each_boundary_arm_refuses_its_own_single_fault(
        graph_page: Page) -> None:
    """One fault per payload, so no refusal can hide behind a neighbour's."""
    registry = _registry_payload()
    for name, apply in _ONE_FAULT_CASES:
        payload = json.loads(json.dumps(_FIXTURES["parallel_review"]))
        payload["registry"] = registry
        apply(payload)
        # Through JSON.parse in the page, so a "__proto__" key arrives as an
        # own property the way a fixture file would deliver it — a structured
        # clone would quietly turn it into a prototype assignment instead.
        accepted = graph_page.evaluate(
            "text => window.conductGraph.load(JSON.parse(text))",
            json.dumps(payload))
        assert accepted is False, f"{name}: the boundary accepted the fault"
        assert graph_page.locator(".g-node").count() == 0, name
    # The unfaulted copy still loads, so every refusal above was the fault's.
    payload = json.loads(json.dumps(_FIXTURES["parallel_review"]))
    payload["registry"] = registry
    assert graph_page.evaluate(
        "text => window.conductGraph.load(JSON.parse(text))",
        json.dumps(payload))


_STORE_UNIT = """([payload, event]) => import("./graph-store.js").then(store => {
  const facts = store.projectPayload(payload);
  if (!facts) return {loaded: false};
  const loaded = store.reduce(store.EMPTY, {type: "loaded", facts});
  const next = store.reduce(loaded, event);
  return {
    loaded: true,
    notice: next.notice,
    composeNotice: next.composeNotice,
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
        assert "Composition refused" in result["composeNotice"], why
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


def test_an_unreadable_payload_is_refused_whole(graph_page: Page) -> None:
    """null, a list, a string, a number: refused, not coerced."""
    for hostile in (None, [], "graph", 7, True):
        accepted = graph_page.evaluate(
            "payload => window.conductGraph.load(payload)", hostile)
        assert accepted is False, repr(hostile)
        assert graph_page.locator(".g-node").count() == 0, repr(hostile)


_HOSTILE_MARKERS = (
    "sk-live-4f9a2b7c1d",
    "C:/secrets/.env",
    "https://exfil.example/collect",
    "--argv-inject",
    "Traceback (most recent call last)",
)


def test_a_hostile_refusal_leaks_nothing_and_leaves_no_partial_state(
        graph_page: Page) -> None:
    """A refused payload's strings never reach the DOM, and the state that
    was on screen is replaced whole, not patched."""
    _load(graph_page, "parallel_review")
    graph_page.locator('[data-node-id="ship-gate"]').click()
    form = graph_page.locator("#detailCard .g-decide")
    form.locator('[name="actor"]').fill("reviewer-1")
    form.locator('button[type="submit"]').click()
    assert graph_page.evaluate(
        "Object.keys(window.conductGraph.state().decisions)") == ["gate-release"]

    hostile = json.loads(json.dumps(_FIXTURES["parallel_review"]))
    hostile["registry"] = _registry_payload()
    hostile["token"] = _HOSTILE_MARKERS[0]
    hostile["run"]["env"] = _HOSTILE_MARKERS[1]
    hostile["nodes"][0]["uri"] = _HOSTILE_MARKERS[2]
    hostile["nodes"][1]["argv"] = _HOSTILE_MARKERS[3]
    hostile["timeline"][0]["detail"] = _HOSTILE_MARKERS[4]
    assert graph_page.evaluate(
        "payload => window.conductGraph.load(payload)", hostile) is False

    body = graph_page.locator("body").inner_text()
    for marker in _HOSTILE_MARKERS:
        assert marker not in body, marker
    state = graph_page.evaluate(
        """() => { const s = window.conductGraph.state();
             return {phase: s.phase, nodes: s.nodes.length,
                     selection: s.selection,
                     decisions: Object.keys(s.decisions),
                     notice: s.notice}; }""")
    assert state == {"phase": "refused", "nodes": 0, "selection": None,
                     "decisions": [],
                     "notice": "The fixture payload was refused: it does not "
                               "name a valid graph."}


def test_a_prototype_named_gate_id_earns_no_phantom_attribution(
        graph_page: Page) -> None:
    """"constructor" is a valid id; an inherited member is not a decision."""
    payload = json.loads(json.dumps(_FIXTURES["gate_satisfied"]))
    payload["registry"] = _registry_payload()
    for hostile in ("constructor", "toString", "hasOwnProperty"):
        payload["nodes"][1]["gate"] = {"gate_id": hostile, "state": "pending"}
        assert graph_page.evaluate(
            "text => window.conductGraph.load(JSON.parse(text))",
            json.dumps(payload))
        gates = graph_page.locator("#gatesCard")
        assert "LOCAL DRAFT" not in gates.inner_text(), hostile
        assert "undefined" not in gates.inner_text(), hostile
    # And the ledger still works for such an id when a Human really decides.
    graph_page.locator('[data-node-id="ship-gate"]').click()
    form = graph_page.locator("#detailCard .g-decide")
    form.locator('[name="actor"]').fill("reviewer-1")
    form.locator('button[type="submit"]').click()
    assert "LOCAL DRAFT by reviewer-1 — not submitted" in graph_page.locator(
        "#gatesCard").inner_text()


def test_an_ill_shaped_registry_row_is_dropped_alone_not_carried(
        graph_page: Page) -> None:
    """Unknown keys, prototype keys, over-cap text and duplicate ids each
    drop their row; the payload and every other row still load."""
    payload = json.loads(json.dumps(_FIXTURES["gate_satisfied"]))
    good = len(_registry_payload())
    payload["registry"] = _registry_payload() + [
        {"id": "extra-key", "display_name": "Extra", "monogram": "EK",
         "accent_dark": "#6ea8ff", "accent_light": "#2258c9",
         "endpoint": "https://exfil.example"},
        {"id": "proto-key", "display_name": "Proto", "monogram": "PK",
         "accent_dark": "#6ea8ff", "accent_light": "#2258c9",
         "__proto__": {"docs": "https://x"}},
        {"id": "long-monogram", "display_name": "Long", "monogram": "M" * 4000,
         "accent_dark": "#6ea8ff", "accent_light": "#2258c9"},
        {"id": "claude-code", "display_name": "Impostor", "monogram": "IM",
         "accent_dark": "#000000", "accent_light": "#ffffff",
         "availability": "unavailable"},
    ]
    assert graph_page.evaluate(
        "text => window.conductGraph.load(JSON.parse(text))",
        json.dumps(payload))
    palette = graph_page.locator("#paletteCard")
    assert palette.locator(".g-palette__row").count() == good
    assert "Impostor" not in palette.inner_text()
    assert "exfil" not in graph_page.locator("body").inner_text()
    # No sideways scroll survives the attempt either.
    for width in (360, 768, 1440):
        graph_page.set_viewport_size({"width": width, "height": 1200})
        assert graph_page.evaluate(
            "document.documentElement.scrollWidth"
            " <= document.documentElement.clientWidth"), width


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
