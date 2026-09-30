"""What the inspector asks of a step, and how a typed text becomes one edit (spec 5.6.3, 7.2.1).

The inspector draws rows; each row names one field of the edit vocabulary, the control it is drawn
with and the text that control shows. `fieldEdit` is the other direction: a text typed into a row
becomes the one `set-field` edit the flow's edits take, or says why it cannot. The two are held to
each other here: the text a row shows, typed back, changes nothing, for every row of every step of
the real flows, so no control can write what it did not show. The tests run the packaged modules
under Node.
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"fields": "desk-flow-fields.js", "edits": "desk-flow-edits.js",
           "shape": "desk-flow-shape.js"}
DATA: dict[str, Any] = {
    "tester": fixture("flow", "desk-standard-tester.flow-state.json")["flow"],
    "dalio": fixture("flow", "dalio-v5.flow-state.json")["flow"]}
PRELUDE = """
const show = (value) => console.log(JSON.stringify(value));
const rowsOf = (flow, id) => fields.stepRows(flow, flow.steps.find((row) => row.step_id === id));
const by = (rows, name) => rows.find((row) => row.field === name);
const names = (rows, section) => rows.filter((row) => row.section === section)
  .map((row) => row.field);
"""


def js(body: str) -> Any:
    return run_js(PRELUDE + body, DATA, modules=MODULES)


def test_a_dispatch_step_offers_its_typed_rows_by_section_and_then_its_seven_extension_rows():
    out = js("""
      const rows = rowsOf(d.tester, "do");
      show({sections: [...new Set(rows.map((row) => row.section))],
        general: names(rows, "general"), role: names(rows, "role"), limits: names(rows, "limits"),
        inputs: names(rows, "inputs"), ext: names(rows, "ext"),
        text: Object.fromEntries(rows.filter((row) => row.section !== "ext")
          .map((row) => [row.field, row.text])),
        controls: Object.fromEntries(rows.map((row) => [row.field, row.control])),
        set: rows.filter((row) => row.section === "ext").some((row) => row.set)});
    """)
    assert out["sections"] == ["general", "role", "limits", "inputs", "ext"]
    assert out["general"] == ["title", "purpose"]
    assert out["role"] == ["role_id", "capability", "verifier_role_id"]
    assert out["limits"] == ["timeout_seconds", "passes"]
    assert out["inputs"] == ["instruction_from", "reads"]
    assert out["ext"] == ["stage", "arguments", "resources", "attempt_bound", "required_evidence",
                          "failure_policy", "missing_artifact_policy"]
    doer = DATA["tester"]["steps"][1]
    assert doer["step_id"] == "do" and doer["purpose"], "the fixture's doer says what it does"
    assert out["text"] == {"title": "", "purpose": doer["purpose"], "role_id": "role-doer",
                           "capability": "dispatch", "verifier_role_id": "role-checker",
                           "timeout_seconds": "1800", "passes": "3", "instruction_from": "",
                           "reads": ""}
    assert out["controls"]["title"] == "text" and out["controls"]["purpose"] == "area"
    assert out["controls"]["timeout_seconds"] == "int" and out["controls"]["reads"] == "ids"
    assert out["controls"]["capability"] == "select" and out["controls"]["stage"] == "json"
    assert out["set"] is False, "a step with no extension key shows every extension row unset"


def test_a_review_step_adds_its_profile_and_a_tester_reads_its_own_passes():
    out = js("""
      const review = rowsOf(d.tester, "analyst"), tester = rowsOf(d.tester, "tester");
      show({profile: [names(review, "role"), by(review, "review_profile").options,
          by(review, "review_profile").text], passes: [names(review, "limits"),
          by(tester, "passes").text], like: by(tester, "instruction_from").options});
    """)
    assert out["profile"] == [["role_id", "capability", "verifier_role_id", "review_profile"],
                              ["", "spec", "quality", "security"], "spec"]
    assert out["passes"] == [["timeout_seconds"], "2"], "a review has no passes; the pair is read"
    assert out["like"] == ["", "do"], "as-step-X offers the other dispatch steps only"


def test_a_gate_reads_its_rework_and_its_extension_keys_and_a_loop_its_return_and_bound():
    out = js("""
      const gate = rowsOf(d.dalio, "result-gate"), home = rowsOf(d.dalio, "confirm-gate");
      const loop = rowsOf(d.tester, "do-fix");
      show({gate: [names(gate, "rework"), by(gate, "rework").text, names(gate, "ext").slice(-2)],
        null: [by(home, "success_requires").text, by(home, "success_requires").set,
          by(home, "gate_id").set, by(home, "stage").set],
        loop: [names(loop, "loop"), by(loop, "back_to").text, by(loop, "bound").text,
          by(loop, "back_to").options, names(loop, "ext")],
        none: by(rowsOf(d.tester, "result"), "rework").text});
    """)
    assert out["gate"] == [["rework"], "3", ["gate_id", "success_requires"]]
    assert out["null"] == ["null", True, True, False]
    assert out["loop"] == [["back_to", "bound"], "do", "3",
                           ["analyst", "do", "tester", "result"], []]
    assert out["none"] == "", "a gate with no rework loop shows an empty row"


def test_an_extension_key_a_step_already_holds_is_shown_even_where_its_type_offers_none():
    out = js("""
      const flow = structuredClone(d.tester);
      const loop = flow.steps.find((row) => row.step_id === "do-fix");
      loop.ext = {role_id: "role-x", stage: "do"};
      const rows = fields.stepRows(flow, loop);
      show({ext: names(rows, "ext"), text: by(rows, "stage").text, count: fields.extCount(loop),
        none: fields.extCount(flow.steps[0])});
    """)
    assert out["ext"] == ["stage", "role_id"], "a key the type offers, then a role key it holds"
    assert out["text"] == '"do"' and out["count"] == 2 and out["none"] == 0


def test_the_cycles_own_rows_are_its_name_and_its_execution_contract():
    out = js("""
      const plain = fields.flowRows(d.tester), old = fields.flowRows(d.dalio);
      show({plain: plain.map((row) => [row.field, row.text, row.control]),
        old: old.map((row) => [row.field, row.text]), options: plain[1].options});
    """)
    assert out["plain"] == [["flow_title", "Standard with a tester", "text"],
                            ["execution_contract", "bounded-run-v1", "select"]]
    assert out["old"] == [["flow_title", "Стандартный цикл"], ["execution_contract", "none"]]
    assert out["options"] == ["bounded-run-v1", "none"]


def test_a_typed_text_becomes_the_one_edit_the_field_takes_or_says_why_not():
    out = js("""
      const edit = (id, field, text) => fields.fieldEdit(d.tester, id, field, text);
      show({text: edit("do", "title", "Build"), area: edit("do", "purpose", "  "),
        int: edit("do", "timeout_seconds", " 600 "), blank: edit("do", "timeout_seconds", ""),
        word: edit("do", "timeout_seconds", "ten"), passes: edit("do", "passes", "4"),
        passesBlank: edit("do", "passes", ""), rework: edit("result", "rework", ""),
        reworkSet: edit("result", "rework", "3"), ids: edit("do", "reads", " a, b  c,"),
        profile: edit("analyst", "review_profile", ""), json: edit("do", "arguments", '{"a": 1}'),
        badJson: edit("do", "arguments", "{"), emptyJson: edit("do", "arguments", "  "),
        title: fields.fieldEdit(d.tester, null, "flow_title", "Mine"),
        contract: [fields.fieldEdit(d.tester, null, "execution_contract", "none"),
          fields.fieldEdit(d.tester, null, "execution_contract", "bounded-run-v1")],
        unknown: edit("do", "nonsense", "x"), notText: edit("do", "title", 5),
        clear: fields.clearEdit("do", "stage")});
    """)
    def one(node: str, field: str, value: Any) -> dict[str, Any]:
        return {"edit": {"type": "set-field", "nodeId": node, "field": field, "value": value}}

    assert out["text"] == one("do", "title", "Build")
    assert out["area"] == one("do", "purpose", "  ")
    assert out["int"] == one("do", "timeout_seconds", 600)
    assert out["blank"] == one("do", "timeout_seconds", None)
    assert out["word"] == {"reason": "int"}
    assert out["passes"] == one("do", "passes", 4) and out["passesBlank"] == {"reason": "int"}
    assert out["rework"] == one("result", "rework", None)
    assert out["reworkSet"] == one("result", "rework", 3)
    assert out["ids"] == one("do", "reads", ["a", "b", "c"])
    assert out["profile"] == one("analyst", "review_profile", None)
    assert out["json"] == one("do", "arguments", {"a": 1})
    assert out["badJson"] == {"reason": "json"} and out["emptyJson"] == {"reason": "empty"}
    assert out["title"] == one(None, "flow_title", "Mine"), "the cycle's own field has no step"
    assert out["contract"][0]["edit"]["value"] is None
    assert out["contract"][1]["edit"]["value"] == "bounded-run-v1"
    assert out["unknown"] == {"reason": "field"} and out["notText"] == {"reason": "text"}
    assert out["clear"] == {"type": "set-field", "nodeId": "do", "field": "stage", "clear": True}


def test_the_text_every_row_shows_typed_back_changes_nothing_on_every_step_of_the_real_flows():
    out = js("""
      const seen = [], moved = [];
      for (const flow of [d.tester, d.dalio]) {
        const all = [...flow.steps.flatMap((step) => fields.stepRows(flow, step)
          .map((row) => [step.step_id, row])), ...fields.flowRows(flow).map((row) => [null, row])];
        for (const [id, row] of all) {
          if (row.section === "ext" && row.text === "") continue;
          const made = fields.fieldEdit(flow, id, row.field, row.text);
          const done = made.edit ? edits.applyEdit(flow, made.edit) : {flow: "none"};
          seen.push(`${id}:${row.field}`);
          if (done.flow !== null) moved.push([id, row.field, made.reason ?? made.edit.value]);
        }
      }
      show({count: seen.length, moved});
    """)
    assert out["count"] > 60, "both flows, every row of every step"
    assert out["moved"] == []


def test_every_field_a_row_writes_is_a_word_of_the_edit_vocabulary():
    out = js("""
      const named = new Set(edits.EDIT_FIELDS), bad = [];
      for (const flow of [d.tester, d.dalio]) {
        for (const step of flow.steps) {
          for (const row of fields.stepRows(flow, step)) {
            if (!named.has(row.field)) bad.push(row.field);
          }
        }
        for (const row of fields.flowRows(flow)) if (!named.has(row.field)) bad.push(row.field);
      }
      show({bad, written: fields.WRITTEN_FIELDS.filter((name) => !named.has(name))});
    """)
    assert out == {"bad": [], "written": []}


# -- the road's own extended words (spec 7.2.1, 5.6.3) -----------------------------------------

ROAD_WORDS = ("success", "failed", "approved", "rejected", "changes_requested", "waived",
              "bound_reached", "bound_remaining", "always")
DESK_THREE = ["success", "approved", "rejected"]
#: A step of each kind a road may leave or enter, with a home for a loop to return to.
ROAD_STEPS: dict[str, dict[str, Any]] = {
    "agent": {"type": "agent", "role_id": "role-doer", "capability": "dispatch",
              "verifier_role_id": "role-checker", "review_profile": None, "reads": [],
              "instruction_from": None},
    "human": {"type": "human"},
    "loop": {"type": "loop", "back_to": "home", "bound": 2},
}


def _road_step(step_id: str, kind: str) -> dict[str, Any]:
    return {"step_id": step_id, "title": None, "purpose": None, "position": None,
            "timeout_seconds": 1800 if kind == "agent" else None, "ext": {},
            **ROAD_STEPS[kind]}


def _road_flow(source: str, target: str, word: str) -> dict[str, Any]:
    """A flow with one road `a -> b` of `word`, `a` of kind `source` and `b` of kind `target`."""
    steps = [_road_step("home", "agent"), _road_step("a", source), _road_step("b", target)]
    return {"flow_version": 1, "title": "Road", "steps": steps, "ext": {},
            "links": [{"from": "a", "to": "b", "when": word}]}


def test_a_road_offers_the_desks_three_words_and_a_loops_entry_words_and_the_rest_is_extended():
    out = js("""
      const words = (flow, link) => fields.roadWords(flow, link);
      const find = (flow, from, to) => flow.links.find((l) => l.from === from && l.to === to);
      show({
        plain: words(d.tester, find(d.tester, "analyst", "do")),
        always: words(d.dalio, find(d.dalio, "goal", "identify")),
        entry: words(d.tester, find(d.tester, "do", "do-fix")),
        rework: words(d.dalio, find(d.dalio, "result-gate", "retry-loop")),
        waived: words(d.dalio, {from: "result-gate", to: "do", when: "waived"}),
        failedOnward: words(d.tester, {from: "do", to: "tester", when: "failed"}),
        fromLoop: words(d.tester, {from: "do-fix", to: "result", when: "bound_reached"}),
        fromGate: words(d.dalio, find(d.dalio, "confirm-gate", "do")),
      });
    """)
    extra = [word for word in ROAD_WORDS if word not in DESK_THREE]
    assert out["plain"] == {"main": DESK_THREE, "extra": extra, "outside": False,
                            "home": "success"}
    assert out["always"] == {"main": DESK_THREE, "extra": extra, "outside": True,
                             "home": "success"}
    loops = DESK_THREE + ["failed", "changes_requested"]
    rest = ["waived", "bound_reached", "bound_remaining", "always"]
    assert out["entry"] == {"main": loops, "extra": rest, "outside": False, "home": "success"}
    assert out["rework"] == {"main": loops, "extra": rest, "outside": False, "home": "approved"}
    assert out["waived"]["outside"] is True and out["waived"]["home"] == "approved"
    assert out["failedOnward"]["outside"] is True, "failed is the loop's word only into a loop"
    assert out["fromLoop"]["outside"] is True and out["fromLoop"]["home"] is None
    assert out["fromGate"]["outside"] is False and out["fromGate"]["home"] == "approved"


def test_the_desks_road_words_agree_with_the_servers_link_outside_desk_rule_in_every_case():
    from conductor.command.flow_rules import flow_rules

    cases = [(source, target, word) for source in ("agent", "human", "loop")
             for target in ("agent", "loop") for word in ROAD_WORDS
             if not (source == "loop" and target == "loop")]
    flows = [_road_flow(*case) for case in cases]
    out = run_js("const show = (value) => console.log(JSON.stringify(value));\n"
                 "show(d.map((flow) => fields.roadWords(flow, flow.links[0]).outside));",
                 flows, modules={"fields": "desk-flow-fields.js"})
    assert len(out) == len(cases) == 6 * 9 - 9
    for case, flow, desk_says in zip(cases, flows, out):
        server_says = any(row["code"] == "link_outside_desk" for row in flow_rules(flow))
        assert desk_says == server_says, case


# -- which loop is which, and which branch a step is in (spec 7.5, 7.7) -------------------------

def _fork_flow() -> dict[str, Any]:
    """`a` leads to `b` and to `c` by the same word: a fork of two branches."""
    steps = [_road_step(name, "agent") for name in ("a", "b", "c")]
    return {"flow_version": 1, "title": "Fork", "steps": steps, "ext": {},
            "links": [{"from": "a", "to": "b", "when": "success"},
                      {"from": "a", "to": "c", "when": "success"}]}


def test_a_loop_says_its_kind_and_owner_and_a_step_lists_the_loops_that_return_to_it():
    out = js("""
      const facts = (flow, id) => fields.stepFacts(flow,
        flow.steps.find((row) => row.step_id === id));
      const orphan = {...d.tester, links: d.tester.links.filter((link) => link.to !== "do-fix")};
      show({passes: facts(d.tester, "tester-fix"), rework: facts(d.dalio, "retry-loop"),
        other: facts(orphan, "do-fix"), doer: facts(d.tester, "do"),
        inputs: facts(d.dalio, "identify"), alone: facts(d.tester, "result")});
    """)
    assert out["passes"] == {"loop": {"kind": "passes", "owner": "tester", "back_to": "do",
                                      "bound": 2}, "returning": [], "branch": None}
    assert out["rework"]["loop"] == {"kind": "rework", "owner": "result-gate",
                                     "back_to": "identify", "bound": 3}
    assert out["other"]["loop"] == {"kind": "other", "owner": None, "back_to": "do", "bound": 3}
    assert out["doer"] == {"loop": None, "branch": None, "returning": [
        {"id": "do-fix", "kind": "passes", "owner": "do", "bound": 3},
        {"id": "tester-fix", "kind": "passes", "owner": "tester", "bound": 2}]}, (
        "both loops that return to the doer, in the order of the steps")
    assert out["inputs"]["returning"] == [{"id": "retry-loop", "kind": "rework",
                                           "owner": "result-gate", "bound": 3}]
    assert out["alone"] == {"loop": None, "returning": [], "branch": None}


def test_a_step_of_a_fork_says_which_branch_it_is_in_and_whether_it_waits_its_turn():
    out = run_js("const show = (value) => console.log(JSON.stringify(value));\n"
                 "const facts = (id) => fields.stepFacts(d, d.steps.find((row) => "
                 "row.step_id === id));\n"
                 "show({a: facts('a').branch, b: facts('b').branch, c: facts('c').branch});",
                 _fork_flow(), modules={"fields": "desk-flow-fields.js"})
    assert out == {"a": None, "b": {"fork": "a", "number": 1, "of": 2, "waiting": False},
                   "c": {"fork": "a", "number": 2, "of": 2, "waiting": True}}
