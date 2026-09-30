"""The canvas, drawn from a flow (spec 5.6.3, 7.4, 7.7).

`studio-canvas.js` draws two lists and keeps drawing what it is given; the flow's projection
(`desk-flow-graph.js`) hands it steps and roads, and the canvas grows only the hooks the flow needs:
a step's branch number and the note of a branch that waits, a mark at a step or a road that a
diagnostic row addressed, the word of a road, a palette the caller chooses, and no banner (the banner
speaks of a `GraphTemplate` draft). Every hook is inert without its key, which is what keeps the
Studio's own screen as it was, and is proved first.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from playwright.sync_api import Browser, Page

from browser_tests.desk_wizard_bench import desk_url  # noqa: F401
from tests.desk_wizard_node import fixture

PALETTE = [{"key": "doer", "text": "+ Doer", "title": "Add a doer",
            "edit": {"type": "add", "kind": "agent", "roleKind": "doer"}},
           {"key": "decision", "text": "+ You", "title": "Add a decision",
            "edit": {"type": "add", "kind": "human"}}]

SETUP = """
async ({flow, rows, canvas, selection}) => {
  const view = await import("/panel/studio-canvas.js");
  const graph = await import("/panel/desk-flow-graph.js");
  const edits = await import("/panel/desk-flow-edits.js");
  document.getElementById("flowMount")?.remove();
  const mount = document.createElement("div");
  mount.id = "flowMount";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  document.body.append(mount);
  let shown = flow;
  if (canvas.fork) {
    const put = (one, edit) => edits.applyEdit(one, edit).flow;
    shown = put(put(put(flow, {type: "add", kind: "agent", roleKind: "reviewer", afterId: "analyst"}),
      {type: "add", kind: "agent", roleKind: "designer", afterId: "reviewer"}), {type: "move",
      nodeId: "analyst", x: 0, y: 0});
  }
  const words = {title: (step) => step.title ?? step.step_id, when: (when) => `~${when}`,
    waiting: "waits its turn", severity: {error: "Error", warning: "Warning"}};
  const drawn = canvas.plain ? {nodes: shown.steps.map((step) => ({node_id: step.step_id,
    kind: step.type === "human" ? "gate" : step.type === "loop" ? "loop" : "task",
    title: step.step_id, ...(step.type === "loop" ? {loop: {bound: step.bound,
      back_to: step.back_to}} : {})})), edges: shown.links.map((link) => ({from_node: link.from,
    to_node: link.to}))} : graph.flowGraph(shown, words, rows);
  const emitted = [];
  const state = {locale: "en", workflows: {draft: {nodes: drawn.nodes, edges: drawn.edges},
    phase: "ready", diagnostics: []}, canvas: {...canvas.hooks, selection}};
  view.mountCanvas(mount, svg, state, {onEdit: (edit) => emitted.push(edit),
    onSelect: () => {}, onView: () => {}, onStatus: () => {}});
  window.flowCanvas = {emitted, mount, drawn};
}
"""

FACTS = """
() => {
  const mount = window.flowCanvas.mount;
  const text = (node) => node.textContent.trim();
  return {
    banner: mount.querySelectorAll(".studio-canvas__banner").length,
    palette: [...mount.querySelectorAll("[data-add-kind]")].map((node) => node.dataset.addKind),
    badges: Object.fromEntries([...mount.querySelectorAll("[data-node-id]")].map((node) =>
      [node.dataset.nodeId, [node.getAttribute("data-branch"), node.getAttribute("data-diag"),
        [...node.querySelectorAll(".studio-node__waits")].map(text),
        [...node.querySelectorAll(".studio-node__branch")].map(text),
        [...node.querySelectorAll(".studio-node__diag")].map(text)]])),
    edges: [...mount.querySelectorAll("[data-edge]")].map((node) => [node.dataset.edge,
      node.getAttribute("data-diag")]),
    labels: [...mount.querySelectorAll("[data-edge-label]")].map((node) =>
      [node.dataset.edgeLabel, text(node)]),
  };
}
"""


@pytest.fixture
def page(chromium: Browser, desk_url: str) -> Iterator[Page]:  # noqa: F811
    context = chromium.new_context(viewport={"width": 1100, "height": 900})
    try:
        page = context.new_page()
        page.set_default_timeout(8000)
        problems: list[str] = []
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.goto(f"{desk_url}/panel/desk.html", wait_until="load")
        yield page
        assert problems == []
    finally:
        context.close()


def draw(page: Page, **over: Any) -> dict[str, Any]:
    flow = fixture("flow", "desk-standard.flow-state.json")["flow"]
    page.evaluate(SETUP, {"flow": flow, "rows": [], "selection": None,
                          "canvas": {"hooks": {}, **over}})
    return page.evaluate(FACTS)


def test_without_its_keys_no_hook_draws_anything_and_the_studios_palette_and_banner_stand(page):
    facts = draw(page, plain=True)
    assert facts["banner"] == 1, "the Studio's banner stands when nothing says otherwise"
    assert facts["palette"] == ["task", "gate", "loop"]
    assert all(row[0] is None and row[1] is None and row[2:] == [[], [], []]
               for row in facts["badges"].values())
    assert facts["labels"] == [] and all(diag is None for _, diag in facts["edges"])


def test_a_step_says_its_branch_and_that_it_waits_and_a_road_says_its_word_and_its_mark(page):
    rows = [{"code": "timeout_clamped", "severity": "warning", "at": {"step_id": "do"},
             "params": {}},
            {"code": "link_outside_desk", "severity": "warning",
             "at": {"link": ["do", "do-fix", "failed"]}, "params": {}},
            {"code": "loop_body_empty", "severity": "error", "at": {"step_id": "do-fix"},
             "params": {}}]
    flow = fixture("flow", "desk-standard.flow-state.json")["flow"]
    page.evaluate(SETUP, {"flow": flow, "rows": rows, "selection": None,
                          "canvas": {"hooks": {}, "fork": True}})
    facts = page.evaluate(FACTS)
    assert facts["badges"]["do"] == ["1", "warning", [], ["1"], ["Warning"]]
    assert facts["badges"]["reviewer"] == ["2", None, ["waits its turn"], ["2"], []]
    assert facts["badges"]["designer"][:1] == ["2"] and facts["badges"]["analyst"][0] is None
    assert facts["badges"]["do-fix"] == [None, "error", [], [], ["Error"]]
    assert ["do do-fix", "warning"] in facts["edges"]
    assert facts["labels"] == [["do do-fix", "~failed · Warning"]], (
        "the road says its word and its mark; success is the road nobody needs told")


def test_the_caller_chooses_the_palette_and_a_press_adds_after_the_selected_step(page):
    facts = draw(page, hooks={"palette": PALETTE, "banner": False}, plain=False)
    assert facts["banner"] == 0 and facts["palette"] == ["doer", "decision"]
    flow = fixture("flow", "desk-standard.flow-state.json")["flow"]
    page.evaluate(SETUP, {"flow": flow, "rows": [], "selection": {"kind": "node", "id": "do"},
                          "canvas": {"hooks": {"palette": PALETTE, "banner": False}}})
    page.locator('[data-add-kind="doer"]').click()
    page.locator('[data-add-kind="decision"]').click()
    assert page.evaluate("() => window.flowCanvas.emitted") == [
        {"type": "add", "kind": "agent", "roleKind": "doer", "afterId": "do"},
        {"type": "add", "kind": "human", "afterId": "do"}]
