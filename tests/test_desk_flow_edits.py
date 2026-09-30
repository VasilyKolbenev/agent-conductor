"""The desk's edits of a cycle over flow v1 (spec 5.6.3, 7.2, 7.2.4, 7.7).

Every test runs the packaged modules under Node on plain values: a flow goes in, an edit goes in,
a flow (or a refusal with its reason) comes out. The expectations are the spec's, written by hand
from its lines, so a change of the module cannot quietly move them. The last two tests are the
witnesses that hold the edits to the server's shape and to immutability.
"""
from __future__ import annotations

from typing import Any

from conductor.command.workflow_flow import settled_flow
from tests.desk_wizard_node import fixture, run_js

MODULES = {"edits": "desk-flow-edits.js", "shape": "desk-flow-shape.js",
           "loops": "desk-flow-loops.js", "branches": "desk-flow-branches.js"}
FLOWS = {"standard": "desk-standard", "short": "desk-short", "docs": "desk-starter-docs",
         "tester": "desk-standard-tester", "dalio": "dalio-v5"}
DATA: dict[str, Any] = {"flows": {name: fixture("flow", f"{file}.flow-state.json")["flow"]
                                  for name, file in FLOWS.items()}}
PRELUDE = """
const empty = () => ({flow_version: 1, title: "Cycle", steps: [], links: [], ext: {}});
const put = (flow, edit) => {
  const out = edits.applyEdit(flow, edit);
  if (out.flow === null) throw new Error("refused: " + JSON.stringify([edit, out.notice]));
  return out.flow;
};
const why = (flow, edit) => {
  const out = edits.applyEdit(flow, edit);
  return out.flow === null ? (out.notice === "" ? "" : out.notice.key.replace("schema.notice.", ""))
    : "applied";
};
const ids = (flow) => flow.steps.map((row) => row.step_id);
const roads = (flow) => flow.links.map((link) => `${link.from}>${link.to}:${link.when}`);
const step = (flow, id) => flow.steps.find((row) => row.step_id === id);
const show = (value) => console.log(JSON.stringify(value));
const agent = (id, role, capability, over = {}) => ({step_id: id, type: "agent", title: null,
  purpose: null, position: null, timeout_seconds: 1800, role_id: role, capability,
  verifier_role_id: capability === "dispatch" ? "role-checker" : null, review_profile: null,
  reads: [], instruction_from: null, ext: {}, ...over});
const human = (id) => ({step_id: id, type: "human", title: null, purpose: null, position: null,
  timeout_seconds: null, ext: {}});
const build = (steps, links) => ({...empty(), steps, links});
"""


def js(body: str) -> Any:
    return run_js(PRELUDE + body, DATA, modules=MODULES)


def test_the_edit_words_are_the_canvas_nine_and_the_fields_are_the_flows_and_the_extensions():
    out = js("show({types: edits.EDIT_TYPES, fields: edits.EDIT_FIELDS});")
    assert out["types"] == ["add", "connect", "delete-edge", "delete-node", "duplicate", "move",
                            "reorder", "set-edge-condition", "set-field"]
    assert out["fields"] == sorted(out["fields"]) and len(out["fields"]) == 24
    typed = {"title", "purpose", "timeout_seconds", "role_id", "capability", "verifier_role_id",
             "review_profile", "reads", "instruction_from", "back_to", "bound"}
    extended = {"stage", "arguments", "resources", "attempt_bound", "required_evidence",
                "failure_policy", "missing_artifact_policy", "gate_id", "success_requires"}
    assert set(out["fields"]) == typed | extended | {
        "passes", "rework", "flow_title", "execution_contract"}


def test_a_word_or_a_flow_that_is_not_one_changes_nothing_and_says_nothing():
    out = js("""
      const flow = d.flows.standard;
      show({word: edits.applyEdit(flow, {type: "erase"}),
        none: edits.applyEdit(null, {type: "move"}), bare: edits.applyEdit(flow, null)});
    """)
    assert out == {"word": {"flow": None, "notice": ""}, "none": {"flow": None, "notice": ""},
                   "bare": {"flow": None, "notice": ""}}


def test_adding_a_doer_after_a_step_gives_a_checker_1800_seconds_a_road_and_a_pass_loop_of_three():
    out = js("""
      const first = put(empty(), {type: "add", kind: "agent", roleKind: "analyst"});
      const both = put(first, {type: "add", kind: "agent", roleKind: "doer", afterId: "analyst"});
      show({ids: ids(both), roads: roads(both), doer: step(both, "doer"),
        loop: step(both, "doer-fix"), first: ids(first)});
    """)
    assert out["ids"] == ["analyst", "doer", "doer-fix"] and out["first"] == ["analyst"]
    assert out["roads"] == ["analyst>doer:success", "doer>doer-fix:failed"]
    doer = out["doer"]
    assert (doer["role_id"], doer["capability"], doer["verifier_role_id"]) == (
        "role-doer", "dispatch", "role-checker")
    assert doer["timeout_seconds"] == 1800 and doer["review_profile"] is None
    assert doer["title"] is None and doer["ext"] == {} and doer["reads"] == []
    loop = out["loop"]
    assert (loop["type"], loop["back_to"], loop["bound"]) == ("loop", "doer", 3)


def test_each_role_kind_is_added_with_its_capability_its_profile_and_its_checker():
    out = js("""
      const kinds = ["analyst", "designer", "diagnostician", "reviewer", "doer", "tester",
        "custom"];
      show(Object.fromEntries(kinds.map((kind) => {
        const flow = put(empty(), {type: "add", kind: "agent", roleKind: kind});
        const row = flow.steps[0];
        return [kind, [row.step_id, row.role_id, row.capability, row.review_profile,
          row.verifier_role_id, row.timeout_seconds, flow.steps.length]];
      })));
    """)
    assert out == {
        "analyst": ["analyst", "role-analyst", "review", "spec", None, 1800, 1],
        "designer": ["designer", "role-designer", "review", "spec", None, 1800, 1],
        "diagnostician": ["diagnostician", "role-diagnostician", "review", "quality", None,
                          1800, 1],
        "reviewer": ["reviewer", "role-reviewer", "review", "quality", None, 1800, 1],
        "doer": ["doer", "role-doer", "dispatch", None, "role-checker", 1800, 2],
        "tester": ["tester", "role-tester", "dispatch", None, "role-checker", 1800, 2],
        "custom": ["step", "role-custom", "review", None, None, 1800, 1]}


def test_a_new_step_id_is_never_taken_never_reserved_and_the_step_stands_before_the_loops():
    out = js("""
      const more = put(d.flows.standard, {type: "add", kind: "agent", roleKind: "analyst"});
      const again = put(more, {type: "add", kind: "agent", roleKind: "analyst"});
      show({more: ids(more), again: ids(again), brief: shape.freshId({steps: []}, "brief"),
        materials: shape.freshId({steps: []}, "materials"), plain: shape.freshId({steps: []}, "a"),
        aliases: ["task", "gate", "route"].map((kind) => step(put(empty(),
          {type: "add", kind}), kind === "task" ? "doer" : kind === "gate" ? "decision"
          : "route")?.type ?? null)});
    """)
    assert out["more"] == ["analyst", "do", "result", "analyst-2", "do-fix"]
    assert out["again"] == ["analyst", "do", "result", "analyst-2", "analyst-3", "do-fix"]
    assert (out["brief"], out["materials"], out["plain"]) == ("brief-2", "materials-2", "a")
    assert out["aliases"] == ["agent", "human", "route"], "task and gate are the canvas's words"


def test_the_road_an_added_step_gets_is_the_word_its_source_can_say():
    out = js("""
      const flow = d.flows.standard;
      const road = (source, kind, id) => roads(put(flow, {type: "add", kind, afterId: source}))
        .find((one) => one.includes(`>${id}:`));
      show({agent: road("analyst", "human", "decision"), gate: road("result", "agent", "doer"),
        loop: road("do-fix", "human", "decision"),
        none: roads(put(flow, {type: "add", kind: "human"})).length});
    """)
    assert out["agent"] == "analyst>decision:success"
    assert out["gate"] == "result>doer:approved"
    assert out["loop"] == "do-fix>decision:always"
    assert out["none"] == 3, "a step added after nothing draws no road"


def test_a_loop_can_only_be_added_after_a_step_it_returns_to():
    out = js("""
      const flow = d.flows.standard;
      const raw = put(flow, {type: "add", kind: "loop", afterId: "analyst"});
      show({none: why(flow, {type: "add", kind: "loop"}), raw: step(raw, "loop"),
        placed: ids(raw), road: roads(raw).at(-1), kind: why(flow, {type: "add", kind: "wat"}),
        unknown: why(flow, {type: "add", kind: "agent", afterId: "ghost"})});
    """)
    assert out["none"] == "loop_needs_step" and out["kind"] == "kind_unknown"
    assert out["unknown"] == "step_missing"
    assert (out["raw"]["back_to"], out["raw"]["bound"]) == ("analyst", 2)
    assert out["placed"] == ["analyst", "do", "result", "loop", "do-fix"]
    assert out["road"] == "analyst>loop:success"


def test_connect_draws_the_word_of_its_source_and_refuses_a_self_a_repeat_and_an_unknown_step():
    out = js("""
      const flow = d.flows.standard;
      const joined = put(flow, {type: "connect", fromId: "analyst", toId: "result"});
      const said = put(flow, {type: "connect", fromId: "analyst", toId: "result",
        when: "rejected"});
      show({joined: roads(joined).at(-1), said: roads(said).at(-1),
        self: why(flow, {type: "connect", fromId: "do", toId: "do"}),
        repeat: why(flow, {type: "connect", fromId: "analyst", toId: "do"}),
        ghost: why(flow, {type: "connect", fromId: "analyst", toId: "ghost"}),
        word: why(flow, {type: "connect", fromId: "analyst", toId: "result", when: "soon"}),
        from_gate: roads(put(flow, {type: "connect", fromId: "result", toId: "analyst"})).at(-1)});
    """)
    assert out["joined"] == "analyst>result:success" and out["said"] == "analyst>result:rejected"
    assert out["self"] == out["ghost"] == "connection_invalid"
    assert out["repeat"] == "connection_exists" and out["word"] == "word_unknown"
    assert out["from_gate"] == "result>analyst:approved"


def test_deleting_a_road_takes_only_that_road():
    out = js("""
      const flow = d.flows.standard;
      show({kept: roads(put(flow, {type: "delete-edge", fromId: "analyst", toId: "do"})),
        steps: ids(put(flow, {type: "delete-edge", fromId: "analyst", toId: "do"})),
        missing: why(flow, {type: "delete-edge", fromId: "do", toId: "analyst"})});
    """)
    assert out["kept"] == ["do>result:success", "do>do-fix:failed"]
    assert out["steps"] == ["analyst", "do", "result", "do-fix"]
    assert out["missing"] == "link_missing"


def test_deleting_a_step_takes_its_roads_its_loops_and_the_references_to_it():
    out = js("""
      const std = put(d.flows.standard, {type: "delete-node", nodeId: "do"});
      const docs = put(d.flows.docs, {type: "delete-node", nodeId: "plan"});
      const shared = put(put(put(empty(), {type: "add", kind: "agent", roleKind: "doer"}),
        {type: "add", kind: "agent", roleKind: "doer", afterId: "doer"}),
        {type: "set-field", nodeId: "doer-2", field: "instruction_from", value: "doer"});
      const without = put(shared, {type: "delete-node", nodeId: "doer"});
      const loop = put(d.flows.standard, {type: "delete-node", nodeId: "do-fix"});
      const returning = put(build([agent("a", "role-doer", "dispatch"), agent("b", "role-doer-2",
        "dispatch"), {step_id: "back", type: "loop", title: null, purpose: null, position: null,
        timeout_seconds: null, back_to: "a", bound: 2, ext: {}}], []),
        {type: "delete-node", nodeId: "a"});
      show({std: [ids(std), roads(std)], scheme: step(d.flows.docs, "scheme").reads,
        docs: step(docs, "scheme").reads, shared: step(shared, "doer-2").instruction_from,
        without: [ids(without), step(without, "doer-2").instruction_from],
        loop: [ids(loop), roads(loop)], returning: ids(returning),
        ghost: why(d.flows.standard, {type: "delete-node", nodeId: "ghost"})});
    """)
    assert out["std"] == [["analyst", "result"], []]
    assert out["scheme"] == ["plan"] and out["docs"] == []
    assert out["shared"] == "doer"
    assert out["without"] == [["doer-2", "doer-2-fix"], None]
    assert out["loop"] == [["analyst", "do", "result"], ["analyst>do:success", "do>result:success"]]
    assert out["returning"] == ["b"], "a loop that returned to the deleted step goes with it"
    assert out["ghost"] == "step_missing"


def test_duplicate_copies_the_step_under_a_new_id_without_its_gate_id_and_a_little_aside():
    out = js("""
      const set = put(put(d.flows.standard, {type: "set-field", nodeId: "result", field: "gate_id",
        value: "gate-final"}), {type: "move", nodeId: "result", x: 40, y: 80});
      const copy = put(set, {type: "duplicate", nodeId: "result"});
      const twice = put(copy, {type: "duplicate", nodeId: "result-2"});
      show({ids: ids(copy), copy: step(copy, "result-2"), original: step(copy, "result"),
        again: ids(twice), ghost: why(set, {type: "duplicate", nodeId: "ghost"}),
        added: edits.applyEdit(set, {type: "duplicate", nodeId: "result"}).added});
    """)
    assert out["ids"] == ["analyst", "do", "result", "result-2", "do-fix"]
    assert out["copy"]["ext"] == {} and out["original"]["ext"] == {"gate_id": "gate-final"}
    assert out["copy"]["position"] == {"x": 72, "y": 112}
    assert out["again"][3:5] == ["result-2", "result-3"] and out["added"] == "result-2"
    assert out["ghost"] == "step_missing"


def test_move_sets_the_position_clear_removes_it_and_a_move_out_of_range_is_refused():
    out = js("""
      const flow = d.flows.standard;
      const moved = put(flow, {type: "move", nodeId: "do", x: 8.4, y: -16});
      show({at: step(moved, "do").position, clear: step(put(moved, {type: "move", nodeId: "do",
        clear: true}), "do").position, same: why(moved, {type: "move", nodeId: "do", x: 8, y: -16}),
        far: why(flow, {type: "move", nodeId: "do", x: 1e9, y: 0}),
        nan: why(flow, {type: "move", nodeId: "do", x: "left", y: 0}),
        ghost: why(flow, {type: "move", nodeId: "ghost", x: 0, y: 0}),
        unplaced: why(flow, {type: "move", nodeId: "do", clear: true})});
    """)
    assert out["at"] == {"x": 8, "y": -16} and out["clear"] is None
    assert out["same"] == "unchanged" and out["far"] == "position_range"
    assert out["nan"] == "position_range" and out["ghost"] == "step_missing"
    assert out["unplaced"] == "unchanged"


def test_reorder_moves_a_step_among_the_steps_of_its_own_band_and_never_out_of_it():
    out = js("""
      const flow = d.flows.standard;
      const of = (edit) => ids(put(flow, {type: "reorder", ...edit}));
      show({up: of({nodeId: "result", index: 0}), far: of({nodeId: "analyst", index: 99}),
        loop: why(flow, {type: "reorder", nodeId: "do-fix", index: 0}),
        same: why(flow, {type: "reorder", nodeId: "analyst", index: 0}),
        bad: why(flow, {type: "reorder", nodeId: "analyst", index: "x"}),
        ghost: why(flow, {type: "reorder", nodeId: "ghost", index: 0})});
    """)
    assert out["up"] == ["result", "analyst", "do", "do-fix"]
    assert out["far"] == ["do", "result", "analyst", "do-fix"]
    assert out["loop"] == out["same"] == out["bad"] == "unchanged"
    assert out["ghost"] == "step_missing"


FORK = """
const fork = () => {
  let flow = put(empty(), {type: "add", kind: "agent", roleKind: "analyst"});
  flow = put(flow, {type: "add", kind: "agent", roleKind: "doer", afterId: "analyst"});
  flow = put(flow, {type: "add", kind: "agent", roleKind: "reviewer", afterId: "analyst"});
  flow = put(flow, {type: "add", kind: "agent", roleKind: "designer", afterId: "reviewer"});
  flow = put(flow, {type: "add", kind: "human", afterId: "doer"});
  return put(flow, {type: "connect", fromId: "designer", toId: "decision"});
};
const marks = (flow) => Object.fromEntries([...branches.branchMarks(flow)]
  .map(([id, mark]) => [id, [mark.branch, mark.waiting, mark.fork]]));
"""


def test_the_branches_of_a_fork_are_numbered_in_step_order_and_the_later_ones_wait():
    out = js(FORK + """
      const flow = fork();
      show({ids: ids(flow), marks: marks(flow), forks: branches.forksOf(flow)
        .map((one) => [one.fork, one.when, one.branches.map((row) => [row.number, row.steps])]),
        line: marks(put(empty(), {type: "add", kind: "agent", roleKind: "doer"}))});
    """)
    assert out["ids"] == ["analyst", "doer", "reviewer", "designer", "decision", "doer-fix"]
    assert out["forks"] == [["analyst", "success", [[1, ["doer"]], [2, ["reviewer", "designer"]]]]]
    assert out["marks"] == {"doer": [1, False, "analyst"], "reviewer": [2, True, "analyst"],
                            "designer": [2, True, "analyst"]}
    assert out["line"] == {}, "a straight line has no branch to number"


def test_first_branch_moves_the_steps_of_a_branch_before_the_first_and_leaves_the_roads_alone():
    out = js(FORK + """
      const flow = fork();
      const moved = put(flow, {type: "reorder", nodeId: "designer", branchFirst: true});
      show({ids: ids(moved), same_roads: JSON.stringify(roads(moved).sort())
          === JSON.stringify(roads(flow).sort()), marks: marks(moved),
        again: why(moved, {type: "reorder", nodeId: "designer", branchFirst: true}),
        none: why(flow, {type: "reorder", nodeId: "analyst", branchFirst: true}),
        back: ids(put(moved, {type: "reorder", nodeId: "doer", branchFirst: true}))});
    """)
    assert out["ids"] == ["analyst", "reviewer", "designer", "doer", "decision", "doer-fix"]
    assert out["same_roads"] is True
    assert out["marks"] == {"reviewer": [1, False, "analyst"], "designer": [1, False, "analyst"],
                            "doer": [2, True, "analyst"]}
    assert out["again"] == "unchanged" and out["none"] == "step_missing"
    assert out["back"] == ["analyst", "doer", "reviewer", "designer", "decision", "doer-fix"]


def test_the_word_of_a_road_can_be_any_of_the_nine_and_no_other():
    out = js("""
      const flow = d.flows.standard;
      const words = ["success", "failed", "approved", "rejected", "changes_requested", "waived",
        "bound_reached", "bound_remaining", "always"];
      show({words: words.map((word) => why(flow, {type: "set-edge-condition", fromId: "analyst",
        toId: "do", value: word})), set: roads(put(flow, {type: "set-edge-condition",
        fromId: "analyst", toId: "do", value: "rejected"}))[0],
        other: why(flow, {type: "set-edge-condition", fromId: "analyst", toId: "do",
          value: "on_failed"}),
        ghost: why(flow, {type: "set-edge-condition", fromId: "do", toId: "analyst",
          value: "always"})});
    """)
    assert out["words"] == ["word_same"] + ["applied"] * 8
    assert out["set"] == "analyst>do:rejected" and out["other"] == "word_unknown"
    assert out["ghost"] == "link_missing"


def test_the_always_road_of_an_agent_becomes_success_by_one_edit_and_nothing_else_moves():
    out = js("""
      const flow = d.flows.dalio;
      const fixed = put(flow, {type: "set-edge-condition", fromId: "goal", toId: "identify",
        value: "success"});
      show({before: roads(flow)[0], after: roads(fixed)[0],
        rest: JSON.stringify(roads(fixed).slice(1)) === JSON.stringify(roads(flow).slice(1)),
        steps: JSON.stringify(fixed.steps) === JSON.stringify(flow.steps)});
    """)
    assert out["before"] == "goal>identify:always" and out["after"] == "goal>identify:success"
    assert out["rest"] is True and out["steps"] is True


def test_typed_fields_are_written_as_the_schema_wants_them_and_a_bad_value_is_refused():
    out = js("""
      const flow = d.flows.standard;
      const set = (id, field, value) => why(flow, {type: "set-field", nodeId: id, field, value});
      const val = (id, field, value) => step(put(flow, {type: "set-field", nodeId: id, field,
        value}), id)[field];
      const named = put(flow, {type: "set-field", nodeId: "do", field: "title", value: "Build"});
      show({title: [step(put(named, {type: "set-field", nodeId: "do", field: "title", value: "  "}),
        "do").title, val("do", "title", "Build"), set("do", "title", "  ")],
        purpose: [val("do", "purpose", ""), val("do", "purpose", "Why")],
        timeout: [val("do", "timeout_seconds", 60), val("do", "timeout_seconds", null),
          set("do", "timeout_seconds", 90000), set("do", "timeout_seconds", 1.5),
          set("do", "timeout_seconds", "60"), set("do", "timeout_seconds", 0)],
        role: [set("do", "role_id", ""), set("do", "capability", 7),
          val("do", "role_id", "role-x")],
        checker: [val("do", "verifier_role_id", ""), val("do", "verifier_role_id", "role-y")],
        profile: [val("analyst", "review_profile", "security"),
          val("analyst", "review_profile", null), set("analyst", "review_profile", "deep")],
        reads: [val("do", "reads", ["analyst"]), set("do", "reads", Array(9).fill("a")
          .map((_, at) => `s${at}`)), set("do", "reads", ["a", "a"]), set("do", "reads", "a")],
        from: [set("do", "instruction_from", ""), val("do", "instruction_from", "analyst")],
        loop: [val("do-fix", "back_to", "analyst"), val("do-fix", "bound", 5),
          set("do-fix", "bound", 100), set("do-fix", "bound", 0), set("do", "bound", 3),
          set("do", "back_to", "analyst"), set("result", "role_id", "role-x")],
        same: set("do", "timeout_seconds", 1800), unknown: set("do", "colour", "red"),
        ghost: set("ghost", "title", "x")});
    """)
    assert out["title"] == [None, "Build", "unchanged"], "blank is null: the kind's name shows"
    assert out["purpose"] == [None, "Why"]
    assert out["timeout"] == [60, None, "field_invalid", "field_invalid", "field_invalid",
                              "field_invalid"]
    assert out["role"] == ["field_invalid", "field_invalid", "role-x"]
    assert out["checker"] == [None, "role-y"]
    assert out["profile"] == ["security", None, "field_invalid"]
    assert out["reads"] == [["analyst"], "reads_limit", "field_invalid", "field_invalid"]
    assert out["from"] == ["unchanged", "analyst"]
    assert out["loop"] == ["analyst", 5, "field_invalid", "field_invalid", "field_invalid",
                           "field_invalid", "applied"]
    assert out["same"] == "unchanged" and out["unknown"] == "field_unknown"
    assert out["ghost"] == "step_missing"


def test_an_extension_field_is_set_by_its_value_and_removed_by_clear():
    out = js("""
      const flow = d.flows.standard;
      const stage = put(flow, {type: "set-field", nodeId: "do", field: "stage", value: "do"});
      const args = put(stage, {type: "set-field", nodeId: "do", field: "arguments",
        value: {profile: "implement"}});
      const cleared = put(args, {type: "set-field", nodeId: "do", field: "stage", clear: true});
      const nulled = put(flow, {type: "set-field", nodeId: "result", field: "success_requires",
        value: null});
      const shared = {profile: "implement"};
      const held = put(flow, {type: "set-field", nodeId: "do", field: "arguments", value: shared});
      shared.profile = "changed";
      show({stage: step(stage, "do").ext, args: step(args, "do").ext,
        cleared: step(cleared, "do").ext,
        nulled: step(nulled, "result").ext, absent: why(flow, {type: "set-field", nodeId: "do",
        field: "stage", clear: true}), held: step(held, "do").ext,
        fn: why(flow, {type: "set-field", nodeId: "do", field: "resources", value: () => 1})});
    """)
    assert out["stage"] == {"stage": "do"}
    assert out["args"] == {"stage": "do", "arguments": {"profile": "implement"}}
    assert out["cleared"] == {"arguments": {"profile": "implement"}}
    assert out["nulled"] == {"success_requires": None}, "null is a value, not a removal"
    assert out["absent"] == "unchanged"
    assert out["held"] == {"arguments": {"profile": "implement"}}, "the value is copied, not held"
    assert out["fn"] == "field_invalid"


def test_writing_the_value_a_field_already_holds_changes_nothing_and_a_new_value_does():
    out = js("""
      const flow = put(d.flows.standard, {type: "set-field", nodeId: "do", field: "arguments",
        value: {b: 2, a: {c: [1]}}});
      const write = (value, field = "arguments", node = "do") => why(flow, {type: "set-field",
        nodeId: node, field, value});
      show({same: write({b: 2, a: {c: [1]}}), reordered: write({a: {c: [1]}, b: 2}),
        other: write({b: 3}), absentNull: write(null, "success_requires", "result"),
        title: why(flow, {type: "set-field", nodeId: null, field: "flow_title",
          value: flow.title}),
        renamed: why(flow, {type: "set-field", nodeId: null, field: "flow_title", value: "New"})});
    """)
    assert out["same"] == "unchanged" and out["reordered"] == "unchanged"
    assert out["other"] == "applied", "a different value is a change"
    assert out["absentNull"] == "applied", "a null on a missing key adds the key"
    assert out["title"] == "unchanged" and out["renamed"] == "applied"


def test_the_role_a_gate_or_a_loop_is_bound_to_lives_in_its_extension_and_an_agents_in_the_step():
    out = js("""
      const flow = d.flows.standard;
      const gate = put(flow, {type: "set-field", nodeId: "result", field: "role_id",
        value: "role-boss"});
      const loop = put(gate, {type: "set-field", nodeId: "do-fix", field: "verifier_role_id",
        value: "role-checker"});
      show({gate: [step(gate, "result").ext, "role_id" in step(gate, "result")],
        loop: step(loop, "do-fix").ext, agent: [step(put(flow, {type: "set-field", nodeId: "do",
        field: "role_id", value: "role-z"}), "do").role_id, step(flow, "do").ext]});
    """)
    assert out["gate"] == [{"role_id": "role-boss"}, False]
    assert out["loop"] == {"verifier_role_id": "role-checker"}
    assert out["agent"] == ["role-z", {}]


def test_the_title_and_the_contract_of_the_flow_itself_are_set_by_the_same_door():
    out = js("""
      const flow = d.flows.standard;
      const of = (field, value, over = {}) => edits.applyEdit(flow, {type: "set-field",
        nodeId: null, field, value, ...over});
      show({title: of("flow_title", "Мой цикл").flow.title,
        blank: why(flow, {type: "set-field",
        nodeId: null, field: "flow_title", value: " "}), dropped: of("execution_contract", null)
        .flow.ext, kept: why(flow, {type: "set-field", nodeId: null, field: "execution_contract",
        value: "bounded-run-v1"}),
        back: put(of("execution_contract", null).flow, {type: "set-field", nodeId: null,
        field: "execution_contract", value: "bounded-run-v1"}).ext,
        cleared: put(of("execution_contract", null).flow, {type: "set-field", nodeId: null,
        field: "execution_contract", clear: true}).ext,
        other: why(flow, {type: "set-field", nodeId: null, field: "execution_contract",
          value: "x"})});
    """)
    assert out["title"] == "Мой цикл" and out["blank"] == "title_required"
    assert out["dropped"] == {"execution_contract": None}
    assert out["kept"] == "unchanged", "the default contract is what a flow without the key has"
    assert out["back"] == {} and out["cleared"] == {} and out["other"] == "field_invalid"


def test_passes_of_two_or_more_build_a_fix_loop_and_a_failed_road_and_one_removes_the_pair():
    out = js("""
      const flow = d.flows.short;
      const set = (base, id, value) => put(base, {type: "set-field", nodeId: id,
        field: "passes", value});
      const five = set(flow, "do", 5);
      const none = set(flow, "do", 1);
      const back = set(none, "do", 4);
      show({five: [ids(five), step(five, "do-fix").bound], none: [ids(none), roads(none)],
        back: [ids(back), roads(back), step(back, "do-fix").back_to, step(back, "do-fix").bound],
        same: why(flow, {type: "set-field", nodeId: "do", field: "passes", value: 2}),
        gone: why(none, {type: "set-field", nodeId: "do", field: "passes", value: 1}),
        review: why(d.flows.standard, {type: "set-field", nodeId: "analyst", field: "passes",
          value: 2}),
        range: ["0", "100", "1.5"].map((text) => why(flow, {type: "set-field", nodeId: "do",
          field: "passes", value: Number(text)}))});
    """)
    assert out["five"] == [["do", "result", "do-fix"], 5]
    assert out["none"] == [["do", "result"], ["do>result:success"]]
    assert out["back"] == [["do", "result", "do-fix"], ["do>result:success", "do>do-fix:failed"],
                           "do", 4]
    assert out["same"] == "unchanged" and out["gone"] == "unchanged"
    assert out["review"] == "passes_not_dispatch"
    assert out["range"] == ["passes_range"] * 3


def test_a_taken_fix_name_gets_the_next_number_and_a_testers_loop_returns_to_the_doer_above():
    out = js("""
      const taken = build([agent("do", "role-doer", "dispatch"), human("do-fix"), human("end")],
        [{from: "do", to: "end", when: "success"}]);
      const numbered = put(taken, {type: "set-field", nodeId: "do", field: "passes", value: 2});
      const tester = put(d.flows.standard, {type: "add", kind: "agent", roleKind: "tester",
        afterId: "do"});
      const alone = put(empty(), {type: "add", kind: "agent", roleKind: "tester"});
      show({numbered: ids(numbered).at(-1), road: roads(numbered).at(-1),
        tester: [step(tester, "tester-fix").back_to, step(tester, "tester-fix").bound],
        alone: step(alone, "tester-fix").back_to,
        doer: step(put(tester, {type: "add", kind: "agent", roleKind: "doer", afterId: "tester"}),
          "doer-fix").back_to});
    """)
    assert out["numbered"] == "do-fix-2" and out["road"] == "do>do-fix-2:failed"
    assert out["tester"] == ["do", 2] and out["alone"] == "tester"
    assert out["doer"] == "doer"


def test_rework_builds_a_loop_on_changes_requested_before_the_pass_loops_and_null_removes_it():
    out = js("""
      const flow = d.flows.standard;
      const set = (base, id, value) => put(base, {type: "set-field", nodeId: id,
        field: "rework", value});
      const three = set(flow, "result", 3);
      const off = set(three, "result", null);
      const resized = set(three, "result", 5);
      show({ids: ids(three), road: roads(three).at(-1), loop: step(three, "result-rework"),
        off: [ids(off), roads(off)], resized: step(resized, "result-rework").bound,
        agent: why(flow, {type: "set-field", nodeId: "do", field: "rework", value: 3}),
        range: [1, 9, 2.5].map((value) => why(flow, {type: "set-field", nodeId: "result",
          field: "rework", value})),
        same: why(three, {type: "set-field", nodeId: "result", field: "rework", value: 3}),
        idle: why(flow, {type: "set-field", nodeId: "result", field: "rework", value: null}),
        lonely: why(put(empty(), {type: "add", kind: "human"}), {type: "set-field",
          nodeId: "decision", field: "rework", value: 3})});
    """)
    assert out["ids"] == ["analyst", "do", "result", "result-rework", "do-fix"]
    assert out["road"] == "result>result-rework:changes_requested"
    assert (out["loop"]["back_to"], out["loop"]["bound"], out["loop"]["type"]) == (
        "do", 3, "loop")
    assert out["off"] == [["analyst", "do", "result", "do-fix"],
                          ["analyst>do:success", "do>result:success", "do>do-fix:failed"]]
    assert out["resized"] == 5 and out["agent"] == "rework_not_human"
    assert out["range"] == ["rework_range"] * 3
    assert out["same"] == out["idle"] == "unchanged" and out["lonely"] == "rework_no_step"


def test_a_pass_loop_added_later_stands_after_the_rework_loops():
    out = js("""
      let flow = put(d.flows.short, {type: "set-field", nodeId: "do", field: "passes", value: 1});
      flow = put(flow, {type: "set-field", nodeId: "result", field: "rework", value: 2});
      flow = put(flow, {type: "set-field", nodeId: "do", field: "passes", value: 3});
      show(ids(flow));
    """)
    assert out == ["do", "result", "result-rework", "do-fix"]


def test_putting_rework_first_orders_the_loops_and_touches_nothing_else():
    out = js("""
      const flow = d.flows.dalio;
      const moved = put(flow, {type: "reorder", nodeId: "correct", reworkFirst: true});
      const loopIds = (one) => ids(one).filter((id) => step(one, id).type === "loop");
      show({before: ids(flow), after: ids(moved), loops: [loopIds(flow), loopIds(moved)],
        roads: JSON.stringify(moved.links) === JSON.stringify(flow.links),
        again: why(moved, {type: "reorder", nodeId: "correct", reworkFirst: true}),
        clean: why(d.flows.standard, {type: "reorder", nodeId: "do-fix", reworkFirst: true})});
    """)
    assert out["loops"] == [["correct", "retry-loop"], ["retry-loop", "correct"]]
    assert out["after"] == ["goal", "identify", "diagnose", "design", "confirm-gate", "do",
                            "retry-loop", "result-gate", "correct"]
    assert out["roads"] is True and out["again"] == out["clean"] == "unchanged"


SERIES = """
//: One flow put through every kind of edit, each time from the same start.
const series = (flow) => {
  const first = flow.steps.find((row) => row.type !== "loop")?.step_id;
  const last = [...flow.steps].reverse().find((row) => row.type !== "loop")?.step_id;
  const each = (type) => flow.steps.filter((row) => row.type === type).map((row) => row.step_id);
  const list = [
    ...["analyst", "designer", "diagnostician", "reviewer", "doer", "tester", "custom"]
      .map((roleKind) => ({type: "add", kind: "agent", roleKind, afterId: first})),
    {type: "add", kind: "human", afterId: last}, {type: "add", kind: "route", afterId: first},
    {type: "add", kind: "loop", afterId: first},
    {type: "connect", fromId: first, toId: last}, {type: "duplicate", nodeId: first},
    {type: "move", nodeId: first, x: 16, y: 24}, {type: "delete-node", nodeId: last},
    {type: "set-field", nodeId: first, field: "title", value: "T"},
    {type: "set-field", nodeId: first, field: "timeout_seconds", value: 90},
    {type: "set-field", nodeId: null, field: "execution_contract", value: null},
    {type: "set-field", nodeId: null, field: "flow_title", value: "Другой"},
    {type: "reorder", nodeId: first, index: 1}, {type: "reorder", nodeId: first, reworkFirst: true},
    {type: "reorder", nodeId: last, branchFirst: true},
    ...flow.links.slice(0, 1).map((link) => ({type: "set-edge-condition", fromId: link.from,
      toId: link.to, value: "rejected"})),
    ...flow.links.slice(0, 1).map((link) => ({type: "delete-edge", fromId: link.from,
      toId: link.to})),
    ...each("agent").flatMap((id) => [{type: "set-field", nodeId: id, field: "passes", value: 4},
      {type: "set-field", nodeId: id, field: "arguments", value: {a: [1, {b: null}]}},
      {type: "set-field", nodeId: id, field: "reads", value: []}]),
    ...each("human").map((id) => ({type: "set-field", nodeId: id, field: "rework", value: 3})),
    ...each("loop").map((id) => ({type: "set-field", nodeId: id, field: "bound", value: 7})),
  ];
  return list.map((edit) => edits.applyEdit(flow, edit)).filter((out) => out.flow !== null)
    .map((out) => out.flow);
};
"""


def test_every_edit_of_every_kind_leaves_a_flow_the_form_of_the_server_accepts():
    out = js(SERIES + """
      show(Object.fromEntries(Object.entries(d.flows).map(([name, flow]) => [name, series(flow)])));
    """)
    assert set(out) == set(FLOWS)
    for name, results in out.items():
        assert len(results) >= 20, f"{name}: the edits of the series mostly applied"
        for flow in results:
            assert settled_flow(flow) == flow, name


def test_an_edit_never_changes_the_flow_it_was_given():
    out = js(SERIES + """
      const freeze = (value) => {
        if (value !== null && typeof value === "object") {
          Object.values(value).forEach(freeze);
          Object.freeze(value);
        }
        return value;
      };
      const before = Object.fromEntries(Object.entries(d.flows)
        .map(([name, flow]) => [name, JSON.stringify(flow)]));
      Object.values(d.flows).forEach(freeze);
      const counts = Object.fromEntries(Object.entries(d.flows)
        .map(([name, flow]) => [name, series(flow).length]));
      show({same: Object.entries(d.flows).every(([name, flow]) => JSON.stringify(flow)
        === before[name]), counts});
    """)
    assert out["same"] is True and all(count >= 20 for count in out["counts"].values())
