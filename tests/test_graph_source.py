"""Source-level contract for the ALPHA-2 Graph window (fixture-fed, wire-free).

The Graph window is allowed to exist before any of its wire contracts do, and
these checks are what make that safe: the whole surface is proven to open no
network door, to parse no markup string, and to restate every closed vocabulary
as an exact copy of the layer that owns it. When the frozen API fixtures arrive
the wire will be added behind the one `load` seam — and the guards here will
have to be revised deliberately, not drift silently.
"""
from __future__ import annotations

import re
from pathlib import Path

from conductor.command import contracts

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src" / "conductor" / "panel"
HTML = PANEL / "graph.html"
STORE = PANEL / "graph-store.js"
VIEW = PANEL / "graph-view.js"
BOOT = PANEL / "graph.js"
STYLE = PANEL / "graph.css"
SCRIPTS = (STORE, VIEW, BOOT)
SOURCE = "\n".join(path.read_text(encoding="utf-8") for path in SCRIPTS)
IMPORTS = r'from "(\./[a-z-]+\.js)";'


def test_the_contract_module_resolves_inside_this_tree():
    """A silent import fallback to another checkout would void every claim."""
    module = Path(contracts.__file__).resolve()
    assert ROOT in module.parents, f"conductor resolved outside this tree: {module}"


def test_graph_window_files_sit_in_the_panel_under_the_line_cap():
    for path in (HTML, STORE, VIEW, BOOT, STYLE):
        assert path.is_file() and path.parent == PANEL
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 800


def test_the_graph_module_graph_is_acyclic_and_the_store_stays_pure():
    assert re.findall(IMPORTS, STORE.read_text(encoding="utf-8")) == [
        "./command-projection.js"]
    assert sorted(re.findall(IMPORTS, VIEW.read_text(encoding="utf-8"))) == [
        "./command-view.js", "./graph-store.js"]
    assert sorted(re.findall(IMPORTS, BOOT.read_text(encoding="utf-8"))) == [
        "./graph-store.js", "./graph-view.js"]
    store = STORE.read_text(encoding="utf-8")
    assert "document" not in store
    assert "window." not in store
    assert "getElementById" not in store


def test_the_graph_window_opens_no_wire_and_parses_no_markup():
    html = HTML.read_text(encoding="utf-8")
    lowered = (SOURCE + "\n" + html).lower()
    for forbidden in ("fetch(", "eventsource", "xmlhttprequest", "websocket",
                      "webtransport", "rtcpeerconnection", "sendbeacon",
                      "import(", "importscripts", "navigator.",
                      "innerhtml", "outerhtml", "insertadjacenthtml",
                      "localstorage", "sessionstorage", "document.cookie",
                      "settimeout", "setinterval", "console."):
        assert forbidden not in lowered, forbidden
    assert "from '" not in SOURCE  # imports stay double-quoted and countable
    assert '<link rel="stylesheet" href="graph.css">' in html
    assert '<script src="graph.js" type="module"></script>' in html
    assert html.count("<script") == 1
    assert "/panel/" not in html


def _tokens(css: str) -> list[dict[str, str]]:
    """Every `--name:value` map, one per `:root{...}` block, in order."""
    blocks = re.findall(r":root\{(.*?)\}", css, re.DOTALL)
    return [dict(re.findall(r"(--[a-z0-9-]+):([^;}]+)", block))
            for block in blocks]


def test_the_graph_palette_is_a_value_for_value_copy_of_the_december_palette():
    panel_blocks = _tokens((PANEL / "index.html").read_text("utf-8"))
    graph_blocks = _tokens(STYLE.read_text("utf-8"))
    # Exactly one dark and one light block each — a third override block
    # would drift the effective palette while the first-two check stays green.
    assert len(panel_blocks) == 2 and len(graph_blocks) == 2
    panel_dark, panel_light = panel_blocks
    graph_dark, graph_light = graph_blocks
    required = {"--ground", "--panel", "--sunk", "--line", "--ink", "--muted",
                "--faint", "--accent", "--pass", "--wait", "--fail"}
    assert required <= set(graph_dark) and required <= set(graph_light)
    for name, value in graph_dark.items():
        assert value == panel_dark[name], name
    for name, value in graph_light.items():
        assert value == panel_light[name], name


def _js_list(source: str, name: str) -> set[str]:
    body = re.search(
        rf"{name} = Object\.freeze\(\s*\[(.*?)\]\)", source, re.DOTALL)
    assert body, name
    return set(re.findall(r'"([a-z_]+)"', body.group(1)))


def test_the_store_vocabularies_are_copies_of_the_layers_that_own_them():
    store = STORE.read_text(encoding="utf-8")
    projection = (PANEL / "command-projection.js").read_text(encoding="utf-8")
    assert _js_list(store, "HEALTH_STATES") == contracts.HEALTH_STATES
    assert _js_list(store, "VERIFICATION_STATES") == contracts._VERIFICATION_STATES
    assert _js_list(store, "NODE_PHASES") == (
        {"idle", "proposed", "requested"} | contracts._RESULT_OUTCOMES)
    decisions = dict(re.findall(r'(\w+): "(\w+)",\n', re.search(
        r"DECISION_ACTIONS = Object\.freeze\(\{(.*?)\}\)", store,
        re.DOTALL).group(1)))
    assert set(decisions) == contracts._DECISION_ACTIONS
    projected = dict(re.findall(r'(\w+): "(\w+)",\n', re.search(
        r"DECISION_STATES = Object\.freeze\(\{(.*?)\}\)", projection,
        re.DOTALL).group(1)))
    assert decisions == projected
    capability_keys = set(re.findall(
        r"^  (\w+): Object\.freeze\(\[", re.search(
            r"CAPABILITY_FIELDS = Object\.freeze\(\{(.*?)\n\}\);", projection,
            re.DOTALL).group(1), re.MULTILINE))
    assert _js_list(store, "CAPABILITY_NAMES") == capability_keys
    kinds = re.search(r'\["kinds", "enum-list", \[(.*?)\]\]', projection).group(1)
    assert _js_list(store, "EVIDENCE_KINDS") == set(re.findall(r'"(\w+)"', kinds))
    assert _js_list(store, "GATE_STATES") == {"pending"} | set(decisions.values())
    # Harness-level availability: the December Command's own three words, and
    # no fourth invented beside them.
    assert _js_list(store, "AVAILABILITY_STATES") == {
        "available", "experimental", "unavailable"}


def test_local_only_actions_say_so_where_they_land():
    """The decision and composition arms carry their honesty in the notice."""
    store = STORE.read_text(encoding="utf-8")
    assert store.count("Nothing was executed") == 2
    assert store.count("Composition refused") == 2
    assert '"fixture-only"' in store
    view = VIEW.read_text(encoding="utf-8")
    assert "Nothing is executed or sent" in view


def test_the_docs_field_is_https_gated_at_both_boundary_and_anchor():
    """The one registry field that becomes an href keeps the index.html gate."""
    store = STORE.read_text(encoding="utf-8")
    assert 'row.docs.startsWith("https://")' in store
    view = VIEW.read_text(encoding="utf-8")
    assert 'row.docs.startsWith("https://")' in view
    anchor = re.search(r'element\("a", \{(.*?)\}\)', view, re.DOTALL).group(1)
    assert 'rel: "noreferrer noopener"' in anchor
    assert 'target: "_blank"' in anchor


def test_every_refusal_arm_of_the_store_is_pinned_by_count():
    """Deleting any boundary arm must red this file, not only the browser gate.

    The behavioural half lives in browser_tests/test_graph_rendered.py
    (one-fault payloads); this is the change-detection half, so an arm cannot
    vanish while the many-fault payload still refuses for another reason.
    """
    store = STORE.read_text(encoding="utf-8")
    assert store.count("return null;") == 35
    assert store.count("return false;") == 4
    # The registry's arms refuse by dropping a row, so they are pinned by
    # their own spelling: deleting one reds this line, not only the rendered
    # drop-row test in the browser suite.
    assert store.count("continue;") == 7
