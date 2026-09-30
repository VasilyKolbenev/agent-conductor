"""The flow as the canvas draws it, and the summary of what a publication changes (spec 5.6.3, 7.4,
7.7).

The projection turns a flow into the two lists the canvas already draws (steps and roads), and adds
only what the flow's own facts say: the word of a road, the branch a step belongs to, the mark a
diagnostic row leaves at its address. It computes no rule of the server's and no number. The summary
compares the flow being edited with the last revision's, so the confirmation before a revision says
what will change in a revision that can never be changed.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"g": "desk-flow-graph.js", "edits": "desk-flow-edits.js"}
FLOWS = {"standard": "desk-standard", "short": "desk-short", "docs": "desk-starter-docs",
         "tester": "desk-standard-tester", "dalio": "dalio-v5"}
DATA: dict[str, Any] = {"flows": {name: fixture("flow", f"{file}.flow-state.json")["flow"]
                                  for name, file in FLOWS.items()}}
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const put = (flow, edit) => {
  const out = edits.applyEdit(flow, edit);
  if (out.flow === null) throw new Error("refused: " + JSON.stringify([edit, out.notice]));
  return out.flow;
};
const words = {title: (step) => step.title ?? `<${step.step_id}>`, when: (when) => `~${when}`,
  waiting: "waits", severity: {error: "Error", warning: "Warning"}};
const empty = () => ({flow_version: 1, title: "T", steps: [], links: [], ext: {}});
const fork = () => {
  let flow = put(empty(), {type: "add", kind: "agent", roleKind: "analyst"});
  flow = put(flow, {type: "add", kind: "agent", roleKind: "doer", afterId: "analyst"});
  flow = put(flow, {type: "add", kind: "agent", roleKind: "reviewer", afterId: "analyst"});
  flow = put(flow, {type: "add", kind: "agent", roleKind: "designer", afterId: "reviewer"});
  return put(flow, {type: "add", kind: "human", afterId: "doer"});
};
const ids = (list) => list.map((row) => row.node_id);
"""


def js(body: str) -> Any:
    return run_js(PRELUDE + body, DATA, modules=MODULES)


def test_the_projection_keeps_the_steps_in_order_with_their_kinds_their_roles_and_their_loops():
    out = js("""
      const flow = put(put(d.flows.standard, {type: "move", nodeId: "do", x: 40, y: 8}),
        {type: "set-field", nodeId: "analyst", field: "title", value: "Read"});
      const drawn = g.flowGraph(flow, words);
      const of = (id) => drawn.nodes.find((row) => row.node_id === id);
      show({ids: ids(drawn.nodes), kinds: drawn.nodes.map((row) => row.kind),
        analyst: [of("analyst").title, of("analyst").role_id, of("analyst").capability],
        titled: of("do").title, moved: of("do").position, unplaced: "position" in of("analyst"),
        loop: of("do-fix").loop, gate: [of("result").kind, "capability" in of("result")]});
    """)
    assert out["ids"] == ["analyst", "do", "result", "do-fix"]
    assert out["kinds"] == ["task", "task", "gate", "loop"]
    assert out["analyst"] == ["Read", "role-analyst", "review"]
    assert out["titled"] == "<do>" and out["moved"] == {"x": 40, "y": 8}
    assert out["unplaced"] is False and out["loop"] == {"bound": 3, "back_to": "do"}
    assert out["gate"] == ["gate", False]


def test_a_road_is_drawn_with_its_word_except_success_and_a_step_may_be_a_route_without_a_role():
    out = js("""
      const drawn = g.flowGraph(d.flows.tester, words);
      const route = g.flowGraph({...d.flows.tester, steps: [...d.flows.tester.steps,
        {step_id: "via", type: "route", title: null, purpose: null, position: null,
        timeout_seconds: null, ext: {}}]}, words).nodes.at(-1);
      show({edges: drawn.edges.map((row) => [row.from_node, row.to_node, row.label]),
        route: [route.kind, "capability" in route, "role_id" in route]});
    """)
    assert out["edges"] == [["analyst", "do", None], ["do", "tester", None],
                            ["tester", "result", None], ["do", "do-fix", "~failed"],
                            ["tester", "tester-fix", "~failed"]]
    assert out["route"] == ["task", False, False]


def test_a_row_at_a_step_a_road_or_a_loop_marks_it_and_an_error_beats_a_warning():
    out = js("""
      const rows = [
        {code: "timeout_clamped", severity: "warning", at: {step_id: "do"}, params: {}},
        {code: "dispatch_without_checker", severity: "error", at: {step_id: "do"}, params: {}},
        {code: "link_outside_desk", severity: "warning", at: {link: ["do", "do-fix", "failed"]},
          params: {}},
        {code: "loop_body_empty", severity: "error", at: {step_id: "do-fix"}, params: {}},
        {code: "final_gate_missing", severity: "error", at: null, params: {}},
        {code: "ref_unknown", severity: "error", at: {step_id: "ghost"}, params: {}},
        {code: "when_invalid", severity: "error", at: {link: ["ghost", "do", "success"]},
          params: {}}];
      const marks = g.diagnosticMarks(rows);
      const drawn = g.flowGraph(d.flows.standard, words, rows);
      const node = (id) => drawn.nodes.find((row) => row.node_id === id);
      show({steps: [...marks.steps], links: [...marks.links],
        do: node("do").mark, loop: node("do-fix").mark, plain: "mark" in node("analyst"),
        edge: drawn.edges.map((row) => [row.from_node, row.to_node, row.mark ?? null])});
    """)
    assert out["steps"] == [["do", "error"], ["do-fix", "error"], ["ghost", "error"]]
    assert out["links"] == [["do do-fix", "warning"], ["ghost do", "error"]]
    assert out["do"] == {"severity": "error", "text": "Error"}
    assert out["loop"] == {"severity": "error", "text": "Error"} and out["plain"] is False
    assert out["edge"] == [["analyst", "do", None], ["do", "result", None],
                           ["do", "do-fix", {"severity": "warning", "text": "Warning"}]]


def test_branches_are_numbered_on_the_steps_and_the_later_ones_say_they_wait():
    out = js("""
      const drawn = g.flowGraph(fork(), words);
      const node = (id) => drawn.nodes.find((row) => row.node_id === id);
      show(Object.fromEntries(["analyst", "doer", "reviewer", "designer", "decision"]
        .map((id) => [id, [node(id).badge ?? null, node(id).note ?? null]])));
    """)
    assert out == {"analyst": [None, None], "doer": ["1", None], "reviewer": ["2", "waits"],
                   "designer": ["2", "waits"], "decision": ["1", None]}, (
        "the decision follows only the first branch here, so it belongs to it")


def test_the_summary_names_added_removed_and_changed_steps_and_roads_extension_keys_included():
    out = js("""
      const before = d.flows.standard;
      let flow = put(before, {type: "add", kind: "agent", roleKind: "reviewer", afterId: "analyst"});
      flow = put(flow, {type: "set-field", nodeId: "do", field: "title", value: "Build"});
      flow = put(flow, {type: "set-field", nodeId: "do", field: "stage", value: "do"});
      flow = put(flow, {type: "delete-edge", fromId: "do", toId: "result"});
      flow = put(flow, {type: "set-edge-condition", fromId: "analyst", toId: "do", value: "rejected"});
      flow = put(flow, {type: "delete-node", nodeId: "do-fix"});
      flow = put(flow, {type: "set-field", nodeId: null, field: "flow_title", value: "Other"});
      flow = put(flow, {type: "set-field", nodeId: null, field: "execution_contract", value: null});
      show({rows: g.changeSummary(flow, before),
        same: g.changeSummary(before, before),
        first: g.changeSummary(before, null).map((row) => [row.kind, row.id ?? null]),
        order: g.changeSummary(put(before, {type: "reorder", nodeId: "result", index: 0}),
          before)});
    """)
    kinds = [row["kind"] for row in out["rows"]]
    assert kinds == ["flow_title", "flow_contract", "step_removed", "step_added", "step_changed",
                     "link_removed", "link_removed", "link_added", "link_changed"]
    rows = out["rows"]
    assert rows[0]["after"] == "Other" and rows[2]["id"] == "do-fix" and rows[3]["id"] == "reviewer"
    assert rows[4] == {"kind": "step_changed", "id": "do", "fields": ["title", "ext.stage"]}
    assert [(row["from"], row["to"]) for row in rows[5:7]] == [("do", "result"), ("do", "do-fix")]
    assert (rows[7]["from"], rows[7]["to"], rows[7]["when"]) == ("analyst", "reviewer", "success")
    assert rows[8] == {"kind": "link_changed", "from": "analyst", "to": "do", "before": "success",
                       "after": "rejected"}
    assert out["same"] == []
    assert out["first"] == [["step_added", "analyst"], ["step_added", "do"], ["step_added", "result"],
                            ["step_added", "do-fix"], ["link_added", None], ["link_added", None],
                            ["link_added", None]]
    assert out["order"] == [{"kind": "order"}]


def test_the_projection_and_the_summary_never_change_the_flow_they_are_given():
    out = js("""
      const freeze = (value) => {
        if (value !== null && typeof value === "object") {
          Object.values(value).forEach(freeze);
          Object.freeze(value);
        }
        return value;
      };
      const before = JSON.stringify(d.flows);
      Object.values(d.flows).forEach(freeze);
      const rows = [{code: "x", severity: "error", at: {step_id: "do"}, params: {}}];
      const counts = Object.entries(d.flows).map(([name, flow]) => [name,
        g.flowGraph(flow, words, rows).nodes.length === flow.steps.length,
        g.flowGraph(flow, words, rows).edges.length === flow.links.length,
        g.changeSummary(flow, d.flows.standard).length >= 0]);
      show({same: JSON.stringify(d.flows) === before, counts});
    """)
    assert out["same"] is True
    assert all(row[1] and row[2] and row[3] for row in out["counts"]), out["counts"]
