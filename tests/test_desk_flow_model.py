"""The state and the closed table of events of the «Схема» panel (spec 5.6.3, 7.1, 7.7).

The model is the write chain plus what only a panel keeps: the list of cycles, which step or road is
selected, the text typed into rows and not yet committed, the open sections, the quick form and the
canvas view. It is a pure function of its state and one event, in the shape of the wizard's model:
an event goes in, a state and the asks that are due come out, and a host that owns the doors
performs each ask and answers it. The tests run the packaged modules under Node; the drawing is
proved in the browser (`browser_tests/test_desk_flow.py`).
"""
from __future__ import annotations

from typing import Any

from tests.desk_wizard_node import fixture, run_js

MODULES = {"model": "desk-flow-model.js", "write": "desk-flowwrite.js",
           "quick": "desk-quickcycle.js", "edits": "desk-flow-edits.js"}
DATA: dict[str, Any] = {
    "states": {"standard": fixture("flow", "desk-standard.flow-state.json"),
               "tester": fixture("flow", "desk-standard-tester.flow-state.json"),
               "dalio": fixture("flow", "dalio-v5.flow-state.json"),
               "none": fixture("wizard", "flow_state_none.json")},
    "list": fixture("wizard", "workflows.json")}
PRELUDE = """
const NONCE = "a1b2c3d4e5f60718293a4b5c6d7e8f90";
const D = (letter) => "sha256:" + letter.repeat(64);
const show = (value) => console.log(JSON.stringify(value));
const fresh = () => model.initialFlow({nonce: NONCE});
const send = (out, event) => model.stepFlow(out.state, event);
const fs = (name, id, over = {}) => ({...structuredClone(d.states[name]), workflow_id: id,
  ...over});
const reply = (out, ask, payload, over = {}) => send(out, {type: "answered", ask,
  result: {status: over.status ?? "accepted", code: over.code ?? null, payload}});
const named = (out, name) => out.asks.find((ask) => ask.name === name);
//: A panel that has opened a cycle and heard the list of cycles.
const opened = (id = "cycle-x1", name = "tester") => {
  const first = send({state: fresh()}, {type: "open", workflowId: id, title: "New cycle"});
  const read = reply(first, named(first, "schema_read"), fs(name, id));
  return reply(read, named(first, "schema_workflows"), d.list);
};
const landed = (ask, digest, over = {}) => fs("tester", ask.subject, {source: "draft",
  flow: ask.body.source.flow, draft_digest: digest, ...over});
const edit = (id, field, value) => ({type: "edit", edit: {type: "set-field", nodeId: id, field,
  value}});
const ids = (flow) => flow.steps.map((row) => row.step_id);
"""


def js(body: str) -> Any:
    return run_js(PRELUDE + body, DATA, modules=MODULES)


def test_the_events_are_the_write_chains_and_the_panels_own_in_one_closed_table():
    out = js("""
      const odd = model.stepFlow(fresh(), {type: "constructor"});
      const proto = model.stepFlow(fresh(), {type: "toString"});
      const none = model.stepFlow(fresh(), null);
      show({events: model.FLOW_EVENTS, write: write.WRITE_EVENTS,
        same: [odd.asks.length, proto.asks.length, none.asks.length]});
    """)
    own = ["select", "view", "status", "section", "field-input", "field-commit", "cycles",
           "quick-open", "quick-close", "quick-title", "quick-add", "quick-remove", "quick-build"]
    assert out["events"] == [*out["write"], *own]
    assert out["same"] == [0, 0, 0], "an inherited key or a null is no event"


def test_opening_a_cycle_asks_its_flow_and_the_list_of_cycles_once_and_keeps_the_list():
    out = js("""
      const first = send({state: fresh()}, {type: "open", workflowId: "cycle-x1", title: "T"});
      const both = reply(first, named(first, "schema_read"), fs("tester", "cycle-x1"));
      const listed = reply(both, named(first, "schema_workflows"), d.list);
      const again = send(listed, {type: "open", workflowId: "desk-standard", title: ""});
      const view = model.flowView(listed.state);
      show({asks: first.asks.map((ask) => [ask.id, ask.name, ask.door, ask.target, ask.subject]),
        again: again.asks.map((ask) => ask.name),
        cycles: view.cycles.map((row) => row.workflow_id), starters: view.starters.map(
          (row) => row.starter_id), phase: view.phase, listed: view.listError});
    """)
    assert out["asks"] == [["read:schema:1", "schema_read", "read", "flowRead", "cycle-x1"],
                           ["read:cycles:1", "schema_workflows", "read", "workflows", None]]
    assert out["again"] == ["schema_read"], "the list is asked once, not at every open"
    assert out["cycles"][0] == "cycle-7c1e5a90" and "desk-standard" in out["cycles"]
    assert out["starters"] == ["desk-standard", "desk-short", "desk-starter-docs", "dalio-v5"]
    assert out["phase"] == "ready" and out["listed"] is None


def test_the_answer_to_the_first_cycles_read_does_not_fill_the_panel_of_the_second_cycle():
    out = js("""
      const a = send({state: fresh()}, {type: "open", workflowId: "cycle-a1", title: "A"});
      const b = send(a, {type: "open", workflowId: "cycle-b2", title: "B"});
      const late = reply(b, named(a, "schema_read"), fs("tester", "cycle-a1"));
      const waiting = model.flowView(late.state);
      const right = reply(late, named(b, "schema_read"), fs("none", "cycle-b2"));
      const done = model.flowView(right.state);
      show({ids: [named(a, "schema_read").id, named(b, "schema_read").id],
        late: [waiting.workflowId, waiting.phase, waiting.flow, late.asks.length],
        right: [done.workflowId, done.phase, done.flow.steps.length]});
    """)
    assert out["ids"][0] != out["ids"][1], "the second open asks under an id of its own"
    assert out["late"] == ["cycle-b2", "reading", None, 0], "B shows nothing of A while it waits"
    assert out["right"] == ["cycle-b2", "ready", 0]


def test_a_list_that_cannot_be_read_is_said_and_a_stale_answer_changes_nothing():
    out = js("""
      const first = send({state: fresh()}, {type: "open", workflowId: "cycle-x1", title: "T"});
      const ask = named(first, "schema_workflows");
      const refused = reply(first, ask, null, {status: "refused", code: "project_mismatch"});
      const lost = reply(first, ask, null, {status: "unknown"});
      const wrong = reply(first, ask, {workflows: "x"});
      const stale = reply(first, {...ask, id: "read:cycles:9"}, d.list);
      const again = send(refused, {type: "cycles"});
      show({refused: model.flowView(refused.state).listError,
        lost: model.flowView(lost.state).listError, wrong: model.flowView(wrong.state).listError,
        stale: [stale.state.list, stale.state.listing.id], again: again.asks.map((one) => one.id),
        none: model.flowView(first.state).cycles});
    """)
    assert out["refused"] == "project_mismatch" and out["lost"] == "unknown"
    assert out["wrong"] == "answer_unreadable"
    assert out["stale"] == [None, "read:cycles:1"]
    assert out["again"] == ["read:cycles:2"] and out["none"] == []


def test_a_write_that_landed_asks_the_list_again_so_the_new_cycle_is_in_it():
    out = js("""
      const ready = opened();
      const one = send(ready, edit("do", "title", "Build"));
      const done = reply(one, named(one, "schema_write"), landed(named(one, "schema_write"),
        D("1")));
      show({asks: done.asks.map((ask) => ask.name), save: model.flowView(done.state).save,
        quiet: ready.asks.length, twice: reply(done, done.asks[0], d.list).asks.length});
    """)
    assert out["asks"] == ["schema_workflows"] and out["save"] == "saved"
    assert out["quiet"] == 0 and out["twice"] == 0


def test_a_step_or_a_road_is_selected_by_the_canvas_words_and_a_missing_one_selects_nothing():
    out = js("""
      const ready = opened();
      const pick = (selection) => model.flowView(send(ready, {type: "select",
        selection}).state).selection;
      show({step: pick({kind: "node", id: "do"}), road: pick({kind: "edge", id: "do tester"}),
        gone: pick({kind: "node", id: "nothing"}), goneRoad: pick({kind: "edge", id: "do result"}),
        cleared: pick(null), none: model.flowView(ready.state).selection,
        bad: pick({kind: "weird", id: "do"})});
    """)
    assert out["step"]["kind"] == "step" and out["step"]["step"]["step_id"] == "do"
    assert out["road"] == {"kind": "road", "link": {"from": "do", "to": "tester",
                                                     "when": "success"}}
    assert out["gone"] is None and out["goneRoad"] is None and out["cleared"] is None
    assert out["none"] is None and out["bad"] is None


def test_an_added_step_is_selected_and_a_deleted_step_leaves_the_selection():
    out = js("""
      const ready = opened();
      const picked = send(ready, {type: "select", selection: {kind: "node", id: "tester"}});
      const added = send(picked, {type: "edit", edit: {type: "add", kind: "agent",
        roleKind: "doer", afterId: "tester"}});
      const view = model.flowView(added.state);
      const dropped = send(picked, {type: "edit", edit: {type: "delete-node", nodeId: "tester"}});
      const refused = send(picked, {type: "edit", edit: {type: "add", kind: "nonsense"}});
      show({added: [view.selection.step.step_id, view.selection.step.type],
        dropped: [model.flowView(dropped.state).selection, dropped.state.selection],
        kept: model.flowView(refused.state).selection.step.step_id});
    """)
    assert out["added"] == ["doer", "agent"], "the step, not the pass loop that came with it"
    assert out["dropped"] == [None, None], (
        "the state forgets the step too: a later step of the same id must not be selected")
    assert out["kept"] == "tester"


def test_opening_another_cycle_clears_the_selection_the_typed_text_and_the_quick_form():
    out = js("""
      const ready = opened();
      const busy = send(send(send(ready, {type: "select", selection: {kind: "node", id: "do"}}),
        {type: "field-input", nodeId: "do", field: "title", text: "Bu"}), {type: "quick-open"});
      const save = send(busy, {type: "edit", edit: {type: "set-field", nodeId: "do",
        field: "title", value: "Z"}});
      const first = model.stepFlow({...busy.state, write: {...busy.state.write, dirty: false}},
        {type: "open", workflowId: "cycle-y2", title: "Y"});
      show({drafts: [Object.keys(first.state.drafts), first.state.quick, first.state.selection],
        waits: model.stepFlow(save.state, {type: "open", workflowId: "cycle-y2", title: "Y"})});
    """)
    assert out["drafts"] == [[], None, None]
    assert out["waits"]["asks"] == []
    assert out["waits"]["state"]["write"]["workflowId"] == "cycle-x1"


def test_a_cycle_is_not_switched_while_an_edit_is_unsaved_or_in_flight_and_it_says_so():
    out = js("""
      const ready = opened();
      const one = send(ready, edit("do", "title", "Build"));
      const tried = model.stepFlow(one.state, {type: "open", workflowId: "cycle-y2", title: "Y"});
      const fresh2 = model.stepFlow(one.state, {type: "new", from: "empty", title: "Z"});
      show({inflight: [one.state.write.inflight !== null, tried.asks.length,
        tried.state.write.workflowId, model.flowView(tried.state).notice],
        fresh: [fresh2.state.write.workflowId, model.flowView(fresh2.state).notice]});
    """)
    assert out["inflight"][:3] == [True, 0, "cycle-x1"]
    assert out["inflight"][3] == {"key": "schema.model.switch_wait"}
    assert out["fresh"] == ["cycle-x1", {"key": "schema.model.switch_wait"}]


def test_text_typed_into_a_row_is_kept_in_the_state_and_asks_nothing_until_it_is_committed():
    out = js("""
      const ready = opened();
      const one = send(ready, {type: "field-input", nodeId: "do", field: "title", text: "Bu"});
      const two = send(one, {type: "field-input", nodeId: "do", field: "title", text: "Build"});
      const other = send(two, {type: "field-input", nodeId: null, field: "flow_title", text: "T"});
      const gone = send(other, {type: "field-input", nodeId: "nothing", field: "title", text: "x"});
      const done = send(other, {type: "field-commit", nodeId: "do", field: "title", text: "Build"});
      show({keep: [one.asks.length, two.state.drafts], flow: other.state.drafts,
        ghost: Object.keys(gone.state.drafts).length,
        commit: [done.asks.map((ask) => ask.name), Object.keys(done.state.drafts),
          done.state.write.held.steps[1].title]});
    """)
    assert out["keep"][0] == 0
    assert out["keep"][1] == {"do\u0000title": {"nodeId": "do", "field": "title", "text": "Build"}}
    assert sorted(out["flow"]) == ["\u0000flow_title", "do\u0000title"]
    assert out["ghost"] == 2, "a row of a step that does not exist keeps no text"
    assert out["commit"] == [["schema_write"], ["\u0000flow_title"], "Build"]


def test_a_text_that_means_no_edit_stays_typed_and_says_why_and_a_same_text_leaves_no_draft():
    out = js("""
      const ready = opened();
      const typed = (field, text, id = "do") => send(ready, {type: "field-commit", nodeId: id,
        field, text});
      const word = typed("timeout_seconds", "ten"), json = typed("arguments", "{");
      const same = typed("title", "");
      show({word: [word.asks.length, model.flowView(word.state).notice],
        json: model.flowView(json.state).notice, same: [same.asks.length,
        Object.keys(same.state.drafts), model.flowView(same.state).notice]});
    """)
    assert out["word"] == [0, {"key": "schema.model.field_int"}]
    assert out["json"] == {"key": "schema.model.field_json"}
    assert out["same"][:2] == [0, []] and out["same"][2] is None


def test_an_answer_that_lands_later_does_not_wipe_a_notice_the_person_has_not_yet_read():
    out = js("""
      const ready = opened();
      const wrote = send(ready, edit("do", "title", "Build"));
      const noted = send(wrote, {type: "field-commit", nodeId: "do", field: "timeout_seconds",
        text: "ten"});
      const ask = named(wrote, "schema_write");
      const done = reply(noted, ask, fs("tester", "cycle-x1", {source: "draft",
        flow: ask.body.source.flow, draft_digest: D("1")}));
      const listed = reply(done, done.asks[0], d.list);
      const moved = send(listed, {type: "select", selection: null});
      show({before: model.flowView(noted.state).notice, written: model.flowView(done.state).notice,
        listed: model.flowView(listed.state).notice, moved: model.flowView(moved.state).notice});
    """)
    assert out["before"] == {"key": "schema.model.field_int"}
    assert out["written"] == out["before"] and out["listed"] == out["before"], (
        "a write's answer and the list's answer are not the person's next move")
    assert out["moved"] is None, "the next thing the person does is what clears it"


def test_saving_commits_every_typed_text_first_and_then_asks_one_write():
    out = js("""
      const ready = opened();
      const typed = send(send(ready, {type: "field-input", nodeId: "do", field: "title",
        text: "Build"}), {type: "field-input", nodeId: "tester", field: "purpose", text: "Test"});
      const saved = send(typed, {type: "save"});
      const body = saved.asks[0].body.source.flow, held = saved.state.write.held;
      const next = reply(saved, saved.asks[0], landed(saved.asks[0], D("1")));
      show({asks: saved.asks.map((ask) => ask.name), drafts: Object.keys(saved.state.drafts),
        sent: [body.steps[1].title, body.steps[2].purpose === held.steps[2].purpose],
        held: [held.steps[1].title, held.steps[2].purpose, saved.state.write.dirty],
        then: next.asks.map((ask) => [ask.name, ask.body?.source?.flow?.steps[2].purpose])});
    """)
    assert out["asks"] == ["schema_write"] and out["drafts"] == []
    assert out["sent"] == ["Build", False], "one write in flight: the second text waits its turn"
    assert out["held"] == ["Build", "Test", True]
    assert ["schema_write", "Test"] in out["then"], "and goes out when the first is answered"


def test_pressing_publish_with_a_text_still_typed_writes_the_text_first_and_opens_no_review():
    out = js("""
      const ready = opened();
      const title = (flow) => flow?.steps.find((step) => step.step_id === "do").title ?? null;
      const typed = send(ready, {type: "field-input", nodeId: "do", field: "title",
        text: "Build"});
      const asked = send(typed, {type: "publish-request"});
      const late = send(asked, {type: "field-commit", nodeId: "do", field: "title",
        text: "Build"});
      const sent = named(asked, "schema_write");
      const saved = sent === undefined ? late : reply(late, sent, landed(sent, D("1")));
      const again = send(saved, {type: "publish-request"});
      const confirmed = send(again, {type: "publish-confirm"});
      const view = model.flowView(asked.state), after = model.flowView(late.state);
      show({asked: [asked.asks.map((ask) => ask.name), view.publishing, view.notice,
          Object.keys(asked.state.drafts), title(sent?.body.source.flow)],
        late: [late.asks.length, title(late.state.write.held), Object.keys(late.state.drafts),
          after.notice, after.publishing],
        again: model.flowView(again.state).publishing !== null,
        body: [confirmed.asks[0]?.body.publish_revision !== undefined,
          title(confirmed.asks[0]?.body.source.flow)]});
    """)
    assert out["asked"] == [["schema_write"], None, {"key": "schema.write.publish_wait"}, [],
                            "Build"], "the typed text is written before any review opens"
    assert out["late"] == [0, "Build", [], {"key": "schema.write.publish_wait"}, None], (
        "the commit that leaving the field brings after the press finds the text already held")
    assert out["again"] is True, "the next press opens the review, nothing is unsaved by then"
    assert out["body"] == [True, "Build"], "what is published holds the typed text"


def test_a_text_that_cannot_be_committed_keeps_the_review_shut_and_stays_typed_with_its_reason():
    out = js("""
      const ready = opened();
      const typed = send(ready, {type: "field-input", nodeId: "do", field: "timeout_seconds",
        text: "ten"});
      const asked = send(typed, {type: "publish-request"});
      const view = model.flowView(asked.state);
      show({asks: asked.asks.length, publishing: view.publishing, notice: view.notice,
        drafts: Object.values(asked.state.drafts).map((draft) => draft.text)});
    """)
    assert out == {"asks": 0, "publishing": None, "notice": {"key": "schema.model.field_int"},
                   "drafts": ["ten"]}, "no review opens over a text the flow does not hold"


def test_a_text_committed_while_a_review_is_open_stays_typed_and_says_the_review_is_open():
    out = js("""
      const ready = opened();
      const title = (out) => out.state.write.held.steps.find((step) => step.step_id === "do").title;
      const review = send(ready, {type: "publish-request"});
      const typed = send(review, {type: "field-input", nodeId: "do", field: "title",
        text: "Build"});
      const shape = (out) => [out.asks.length,
        Object.values(out.state.drafts).map((one) => one.text),
        model.flowView(out.state).notice, title(out)];
      const left = send(typed, {type: "field-commit", nodeId: "do", field: "title",
        text: "Build"});
      const saved = send(typed, {type: "save"});
      const cancelled = send(left, {type: "publish-cancel"});
      const after = send(cancelled, {type: "field-commit", nodeId: "do", field: "title",
        text: "Build"});
      show({open: model.flowView(review.state).publishing !== null, left: shape(left),
        saved: shape(saved), after: [after.asks.map((ask) => ask.name),
          Object.keys(after.state.drafts), title(after)]});
    """)
    shut = {"key": "schema.write.publish_open"}
    assert out["open"] is True
    assert out["left"] == [0, ["Build"], shut, None], "leaving the field did not lose the text"
    assert out["saved"] == [0, ["Build"], shut, None], "nor did «Сохранить» under an open review"
    assert out["after"] == [["schema_write"], [], "Build"], "once it is closed the text is written"


def test_the_canvas_view_the_status_line_and_the_open_sections_are_kept_and_ask_nothing():
    out = js("""
      const ready = opened();
      const moved = send(ready, {type: "view", pan: {x: 12, y: -4}, zoom: 1.5});
      const bad = send(moved, {type: "view", pan: {x: "a"}, zoom: "z"});
      const said = send(ready, {type: "status", notice: {key: "workflow_detail.port_no_target"}});
      const open = send(ready, {type: "section", key: "ext", open: true});
      const shut = send(open, {type: "section", key: "ext", open: false});
      const view = model.flowView(moved.state);
      show({canvas: view.canvas, bad: model.flowView(bad.state).canvas,
        status: model.flowView(said.state).status, sections: [model.flowView(open.state).sections,
          model.flowView(shut.state).sections],
        asks: [moved, said, open].map((out) => out.asks.length)});
    """)
    assert out["canvas"] == {"pan": {"x": 12, "y": -4}, "zoom": 1.5}
    assert out["bad"] == {"pan": {"x": 12, "y": -4}, "zoom": 1.5}, "what is not a number is ignored"
    assert out["status"] == {"key": "workflow_detail.port_no_target"}
    assert out["sections"] == [{"ext": True}, {"ext": False}] and out["asks"] == [0, 0, 0]


def test_the_road_fold_is_kept_like_the_step_fold_and_a_fold_of_another_name_is_not():
    out = js("""
      const ready = opened();
      const open = send(ready, {type: "section", key: "road", open: true});
      const both = send(open, {type: "section", key: "ext", open: true});
      const other = send(both, {type: "section", key: "elsewhere", open: true});
      show({sections: model.flowView(other.state).sections, keys: model.SECTION_KEYS,
        asks: [open, both, other].map((out) => out.asks.length)});
    """)
    assert out["sections"] == {"road": True, "ext": True}
    assert out["keys"] == ["ext", "flow", "road"] and out["asks"] == [0, 0, 0]


def test_the_quick_form_collects_rows_and_builds_the_flow_the_same_edits_build():
    out = js("""
      const ready = opened();
      let form = send(ready, {type: "quick-open"});
      form = send(form, {type: "quick-title", value: "Mine"});
      for (const kind of ["analyst", "doer", "tester"]) {
        form = send(form, {type: "quick-add", kind});
      }
      const bad = send(form, {type: "quick-add", kind: "nonsense"});
      form = send(form, {type: "quick-remove", index: 0});
      const before = model.flowView(form.state).quick;
      const built = send(form, {type: "quick-build"});
      const reference = quick.quickFlow("Mine", ["doer", "tester"]).flow;
      const sent = built.asks[0].body.source.flow;
      show({before, asks: built.asks.map((ask) => [ask.name, ask.subject.startsWith("cycle-")]),
        equal: JSON.stringify(sent) === JSON.stringify(reference),
        after: [built.state.quick, built.state.write.fresh, ids(built.state.write.held)],
        notice: [model.flowView(bad.state).notice, bad.state.quick.rows.length]});
    """)
    assert out["before"] == {"title": "Mine", "rows": ["doer", "tester"]}
    assert out["asks"] == [["schema_write", True]] and out["equal"] is True
    assert out["after"][0] is None and out["after"][1] is True
    assert out["after"][2] == ["doer", "tester", "decision", "doer-fix", "tester-fix"]
    assert out["notice"] == [{"key": "schema.model.quick_kind"}, 3], "a row that is no kind is said"


def test_the_quick_form_builds_nothing_for_no_rows_or_no_name_and_closes_without_a_trace():
    out = js("""
      const ready = opened();
      const form = send(ready, {type: "quick-open"});
      const bare = send(form, {type: "quick-build"});
      const rows = send(send(form, {type: "quick-add", kind: "doer"}), {type: "quick-build"});
      const blank = send(send(send(form, {type: "quick-add", kind: "doer"}),
        {type: "quick-title", value: "  "}), {type: "quick-build"});
      const closed = send(form, {type: "quick-close"});
      const late = send({state: fresh()}, {type: "quick-add", kind: "doer"});
      show({bare: [bare.asks.length, model.flowView(bare.state).notice],
        rows: [rows.asks.length, model.flowView(rows.state).notice],
        blank: [blank.asks.length, model.flowView(blank.state).notice],
        closed: closed.state.quick, late: late.state.quick});
    """)
    assert out["bare"] == [0, {"key": "schema.quick.empty"}]
    assert out["rows"] == [0, {"key": "schema.notice.title_required"}]
    assert out["blank"] == [0, {"key": "schema.notice.title_required"}]
    assert out["closed"] is None and out["late"] is None, "no form is open, so no row is added"


def test_the_view_says_what_the_server_said_its_rows_its_counter_and_what_is_stale():
    out = js("""
      const ready = opened("cycle-d1", "dalio");
      const view = model.flowView(ready.state);
      const one = send(ready, edit("goal", "title", "G"));
      const dirty = model.flowView(one.state);
      const refused = reply(one, named(one, "schema_write"), {error: {code: "contract_invalid"},
        diagnostics: [{code: "dead_join", severity: "error", at: {step_id: "do"}, params: {}}]},
        {status: "refused", code: "contract_invalid"});
      const rv = model.flowView(refused.state);
      show({rows: view.rows.length, counter: view.counter, stale: [view.stale, dirty.stale],
        refused: [rv.refused, rv.rows.map((row) => row.code), rv.stale], source: view.source,
        ready: [model.flowView(send({state: fresh()}, {type: "open", workflowId: "desk-standard",
          title: ""}).state).ready, view.ready]});
    """)
    assert out["rows"] == 8
    assert out["counter"] == {"clean": {"actions": 5, "seconds": 10800},
                              "worst": {"actions": 14, "seconds": 32400}, "limit": 8,
                              "stale": False}
    assert out["stale"] == [False, True], "an edit not yet answered makes the count stale"
    assert out["refused"] == ["contract_invalid", ["dead_join"], True]
    assert out["source"] == "draft" and out["ready"] == [True, False]


def test_publishing_shows_what_changes_against_the_last_revision_before_it_writes():
    out = js("""
      const ready = opened("cycle-p1", "tester");
      const revision = structuredClone(d.states.tester.flow);
      revision.steps[1].title = "Old";
      const held = ready.state.write;
      const state = {...ready.state, write: {...held, server: {...held.server,
        revision_flow: revision, publishable: true, next_revision: 3}}};
      const asked = model.stepFlow(state, {type: "publish-request"});
      const view = model.flowView(asked.state);
      const confirmed = model.stepFlow(asked.state, {type: "publish-confirm"});
      show({publishing: view.publishing, review: view.review,
        body: confirmed.asks[0].body.publish_revision,
        idle: model.flowView(state).review});
    """)
    assert out["publishing"] == {"revision": 3}
    assert out["review"] == [{"kind": "step_changed", "id": "do", "fields": ["title"]}]
    assert out["body"] == 3 and out["idle"] == []
