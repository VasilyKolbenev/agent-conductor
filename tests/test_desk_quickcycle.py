"""The quick straight-line mode (spec 5.6.3, 7.2.4): a list of role kinds becomes a cycle by the
same edits the canvas makes, and by nothing else.

The mode declares no vocabulary of its own (the desk keeps exactly three copies of the words of an
edit): it asks `applyEdit` for each step, one after the other, and closes the line with the step
that is the person's. So a flow built here and a flow built on the canvas are the same flow.
"""
from __future__ import annotations

from typing import Any

from conductor.command.workflow_flow import settled_flow
from tests.desk_wizard_node import PANEL, run_js

MODULES = {"quick": "desk-quickcycle.js", "edits": "desk-flow-edits.js"}
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const ids = (flow) => flow.steps.map((row) => row.step_id);
const roads = (flow) => flow.links.map((link) => `${link.from}>${link.to}:${link.when}`);
//: What the canvas makes, one edit at a time, for the same rows.
const byHand = (title, kinds) => {
  let flow = {flow_version: 1, title, steps: [], links: [], ext: {}}, last = null;
  for (const roleKind of kinds) {
    const out = edits.applyEdit(flow, {type: "add", kind: "agent", roleKind, afterId: last});
    flow = out.flow;
    last = out.added;
  }
  return edits.applyEdit(flow, {type: "add", kind: "human", afterId: last}).flow;
};
"""


def js(body: str) -> Any:
    return run_js(PRELUDE + body, None, modules=MODULES)


def test_the_quick_flow_is_what_the_same_edits_build_one_by_one():
    out = js("""
      const kinds = ["analyst", "doer", "tester"];
      const made = quick.quickFlow("My cycle", kinds);
      show({same: JSON.stringify(made.flow) === JSON.stringify(byHand("My cycle", kinds)),
        ids: ids(made.flow), roads: roads(made.flow), title: made.flow.title,
        notice: made.notice});
    """)
    assert out["same"] is True
    assert out["ids"] == ["analyst", "doer", "tester", "decision", "doer-fix", "tester-fix"]
    assert out["roads"] == ["analyst>doer:success", "doer>doer-fix:failed", "doer>tester:success",
                            "tester>tester-fix:failed", "tester>decision:success"]
    assert out["title"] == "My cycle" and out["notice"] == ""


def test_a_final_decision_closes_the_line_and_a_single_step_still_gets_one():
    out = js("""
      const one = quick.quickFlow("T", ["doer"]).flow;
      const two = quick.quickFlow("T", ["analyst", "analyst"]).flow;
      show({one: [ids(one), roads(one)], two: [ids(two), roads(two)],
        last: two.steps.filter((row) => row.type === "human").map((row) => row.step_id)});
    """)
    assert out["one"] == [["doer", "decision", "doer-fix"],
                          ["doer>doer-fix:failed", "doer>decision:success"]]
    assert out["two"][0] == ["analyst", "analyst-2", "decision"]
    assert out["two"][1] == ["analyst>analyst-2:success", "analyst-2>decision:success"]
    assert out["last"] == ["decision"]


def test_an_empty_list_a_name_that_is_no_kind_and_a_list_past_the_limit_are_refused():
    out = js("""
      const why = (result) => [result.flow, result.notice.key ?? result.notice];
      show({empty: why(quick.quickFlow("T", [])), unknown: why(quick.quickFlow("T", ["doer",
        "wizard"])), many: why(quick.quickFlow("T", Array(300).fill("analyst"))),
        text: why(quick.quickFlow("T", "doer")), kinds: quick.QUICK_KINDS,
        notices: quick.QUICK_NOTICES, custom: quick.quickFlow("T", ["custom"]).flow.steps[0].role_id});
    """)
    assert out["empty"] == [None, "schema.quick.empty"]
    assert out["unknown"] == [None, "schema.quick.kind_unknown"]
    assert out["many"][0] is None and out["many"][1] == "schema.notice.limit_steps"
    assert out["text"] == [None, "schema.quick.empty"]
    assert out["kinds"] == ["analyst", "designer", "diagnostician", "reviewer", "doer", "tester",
                            "custom"]
    assert out["notices"] == ["empty", "kind_unknown"] and out["custom"] == "role-custom"


def test_a_quick_flow_is_a_flow_the_form_of_the_server_accepts():
    out = js("""
      const lists = [["analyst"], ["doer"], ["analyst", "doer", "tester"],
        ["designer", "diagnostician", "reviewer", "custom", "doer"]];
      show(lists.map((kinds) => quick.quickFlow("Цикл", kinds).flow));
    """)
    assert len(out) == 4
    for flow in out:
        assert settled_flow(flow) == flow


def test_the_quick_mode_declares_no_vocabulary_of_its_own():
    source = (PANEL / "desk-quickcycle.js").read_text(encoding="utf-8")
    assert "EDIT_TYPES" not in source and "EDIT_FIELDS" not in source
    assert "applyEdit" in source
