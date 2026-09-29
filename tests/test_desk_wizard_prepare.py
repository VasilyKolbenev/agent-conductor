"""The wizard model's step 5 ("Подготовка"): the chain «Подготовить запуск» (spec 6.4.1-6.4.3).

The chain is a value: the model hands out one ask at a time, each write only after the 200/201 of
the one before, and every write says which hash keys must stand before it is sent. The answers
here are the stand-in fixtures of `tests/fixtures/wizard/` (the preparation read, the preview) and
lane L's flow fixtures; the run and the documents are answered by a small table, so what is judged
is only what the wizard sends and what it does with each kind of answer.
"""
from __future__ import annotations

import re

from tests.desk_wizard_node import PRELUDE, fixture, run_js

MODULES = {"wiz": "desk-wizard-model.js", "dig": "desk-wizard-digest.js"}
FLOWS = {"standard": fixture("flow", "desk-standard.flow-state.json"),
         "short": fixture("flow", "desk-short.flow-state.json"),
         "starter": fixture("flow", "desk-starter-docs.flow-state.json"),
         "tester": fixture("flow", "desk-standard-tester.flow-state.json")}
DATA = {"flows": FLOWS, "workflows": fixture("wizard", "workflows.json"),
        "git": fixture("wizard", "git_repo.json"),
        "git_view": fixture("wizard", "git_not_active.json"),
        "git_not_git": fixture("wizard", "git_not_git.json"),
        "runs": fixture("wizard", "runs.json"), "tasks": fixture("wizard", "tasks.json"),
        "unpinned": fixture("wizard", "project_cycle_none.json"),
        "quotas": fixture("wizard", "quotas.json"),
        "prep_new": fixture("wizard", "preparation_new.json"),
        "prep_seeded": fixture("wizard", "preparation_seeded.json"),
        "prep_created": fixture("wizard", "preparation_run_created.json"),
        "preview": fixture("wizard", "preview_standard.json")}
#: A wizard whose four steps are complete (`ready`, `readyStarter`), the chain's own answers
#: (`table`), and `drive`, which presses «Подготовить запуск» and answers each ask in turn from
#: the table with the overrides a test hands it, until the model asks for nothing more.
CHAIN = PRELUDE + """
const digest = "sha256:" + "b".repeat(64);
const ok = (payload) => ({status: "accepted", payload});
const lost = {status: "unknown"};
const refused = (code, payload = null) => ({status: "refused", code, payload});
const moved = (value) => JSON.parse(JSON.stringify(value).replaceAll("task-bench", "task-t1"));
const flowOf = (base, over = {}) => ({...structuredClone(base), draft_digest: digest,
  source: "draft", published: null, ...over});
const reads = (state, over = {}) => Object.entries({workflows: d.workflows, runs: d.runs,
  cycle_read: d.unpinned, tasks: d.tasks, quotas: d.quotas, ...over})
  .reduce((now, [name, payload]) => reply(now, name, payload), state);
const atCycle = (over = {}, git = d.git, opening = {}) => reads(run(reply(opened(
  started(opening)), "git", git), {type: "next"}), over);
const atRoles = (over = {}, flow = d.flows.standard, git = d.git, opening = {}) =>
  wiz.reduceWizard(land(atCycle(over, git, opening), flowOf(flow)), {type: "next"});
const ready = (over = {}, flow = d.flows.standard, git = d.git, opening = {}) =>
  land(atRoles(over, flow, git, opening), flowOf(flow));
const readyStarter = () => {
  const state = run(open({starterId: "desk-starter-docs"}),
    {type: "edit-title", value: "Notes"}, {type: "edit-idea", value: "An app."}, {type: "next"});
  const cycle = reads(run(reply(opened(state), "git", d.git), {type: "next"}));
  return land(wiz.reduceWizard(land(cycle, flowOf(d.flows.starter)), {type: "next"}),
    flowOf(d.flows.starter));
};
const published = (revision = 2) => ({...flowOf(d.flows.standard), source: "published",
  draft_digest: null, published: {revision, created: true}});
const table = {
  prep_task: () => ok({schema_version: 1, task_id: "task-t1"}),
  prep_read: () => ok(moved(d.prep_new)),
  prep_seed: () => ok(moved(d.prep_seeded).seed),
  prep_flow: () => ok(published()),
  prep_flow_read: () => ok({...structuredClone(d.flows.standard), source: "published",
    draft_digest: null, latest_revision: 2}),
  prep_run: () => ok({run: {run_id: "task-t1-r1"}}),
  prep_doc: () => ok({}), prep_materials: () => ok({}),
  preview: () => ok(moved(d.preview))};
const press = (state, lang = "en") => wiz.stepWizard(state, {type: "prepare-start", lang});
const answer = (step, result) => wiz.stepWizard(step.state, {type: "answered",
  ask: step.asks[0], result});
const drive = (first, over = {}, cap = 40) => {
  const plan = {...table, ...over}, log = [];
  let step = first;
  for (let at = 0; at < cap && step.asks.length > 0; at += 1) {
    const [ask] = step.asks;
    log.push(ask);
    step = answer(step, plan[ask.name](ask, step.state, log));
  }
  return {state: step.state, log, last: step};
};
const shape = (ask) => [ask.id, ask.name, ask.target, ask.subject];
const names = (log) => log.map((ask) => ask.name);
const links = (state) => wiz.chainLinks(state).map((row) => row.status);
"""


def test_the_step_may_be_left_only_when_every_step_before_it_is_complete_and_a_repo_can_seed():
    out = run_js(CHAIN + """
      show({stopped: wiz.prepareGate(open()), ready: wiz.prepareGate(ready()),
        view: wiz.prepareGate(ready({}, d.flows.standard, d.git_view, {viewMode: true})),
        no_git: wiz.prepareGate(ready({}, d.flows.standard, d.git_not_git))});
    """, DATA, modules=MODULES)
    assert out["stopped"]["ok"] is False and out["stopped"]["reason"] == "title_invalid"
    assert out["ready"] == {"ok": True, "reason": None, "step": None}
    assert out["view"]["ok"] is True, "in view the seed is a request and needs no commit"
    assert out["no_git"] == {"ok": False, "reason": "seed_needs_git", "step": "prepare"}


def test_nothing_is_asked_before_the_button_and_the_first_ask_is_the_task_with_its_hash():
    out = run_js(CHAIN + """
      const before = ready();
      const step = press(before);
      show({before: wiz.wantedAsks(before).filter((ask) => /:prep:/.test(ask.id)).length,
        run_before: before.run.phase, asks: step.asks, phase: step.state.run.phase,
        again: wiz.stepWizard(step.state, {type: "prepare-start", lang: "en"}).asks.length,
        bad_lang: wiz.stepWizard(before, {type: "prepare-start", lang: "de"}).asks.length,
        unready: wiz.stepWizard(open(), {type: "prepare-start", lang: "en"}).asks.length});
    """, DATA, modules=MODULES)
    assert out["before"] == 0 and out["run_before"] == "idle" and out["phase"] == "preparing"
    (ask,) = out["asks"]
    assert re.fullmatch(r"write:prep:task:[0-9a-f]{8}:0", ask["id"])
    assert {key: value for key, value in ask.items() if key != "id"} == {
        "name": "prep_task", "door": "write", "target": "tasks", "subject": None,
        "body": {"task_id": "task-t1", "title": "Fix login"},
        "job": "task:task-t1:Fix login", "hash": {"task": "task-t1", "prepare": "1"}}
    assert out["again"] == 0 and out["bad_lang"] == 0 and out["unready"] == 0


def test_the_links_go_in_order_each_after_the_answer_of_the_one_before_and_read_between():
    out = run_js(CHAIN + """
      const done = drive(press(ready()));
      const first = press(ready());
      const held = answer(first, ok({}));
      show({order: done.log.map(shape), phase: done.state.run.phase,
        while_one_is_out: wiz.wantedAsks(first.state).filter((ask) => /:prep:/.test(ask.id))
          .map(shape), next_after_task: held.asks.map(shape)});
    """, DATA, modules=MODULES)
    assert [row[1] for row in out["order"]] == [
        "prep_task", "prep_read", "prep_seed", "prep_flow", "prep_run", "prep_doc", "prep_doc",
        "prep_materials", "preview"]
    assert out["order"][1] == ["read:prep:0", "prep_read", "preparation", "task-t1"]
    assert [row[1] for row in out["while_one_is_out"]] == ["prep_task"]
    assert out["next_after_task"] == [["read:prep:0", "prep_read", "preparation", "task-t1"]]
    assert out["phase"] == "review"


def test_each_write_has_the_body_of_the_spec_and_the_hash_keys_that_stand_before_it():
    out = run_js(CHAIN + """
      const state = ready();
      const done = drive(press(state));
      const view = wiz.assignmentView(state).map((row) => [row.role_id, row.provider]);
      show({log: done.log.map((ask) => [ask.name, ask.target, ask.subject, ask.body, ask.hash]),
        view});
    """, DATA, modules=MODULES)
    task, read, seed, flow, run, brief, instruction, materials, preview = out["log"]
    ids = {"task": "task-t1", "prepare": "1"}
    assert task[4] == read[4] == seed[4] == ids
    assert seed[1:4] == ["seed", "task-t1", {
        "work_item_id": "work-001", "source": "git",
        "expect_commit": "abc1234def5678abc1234def5678abc1234def56",
        "include_agent_instructions": False}]
    assert flow[1:3] == ["flow", "desk-standard"]
    assert flow[4] == {**ids, "workflow": "desk-standard"}
    assert flow[3] == {"source": {"starter_id": "desk-standard"},
                       "expected_digest": "sha256:" + "b" * 64, "publish_revision": 2,
                       "binding": None}
    roles = out["view"]
    assert run[1:3] == ["runs", None]
    assert run[3] == {
        "run_id": "task-t1-r1", "cycle_id": "task-t1-r1", "mode": "policy",
        "automation_contract": "bounded-run-v1",
        "participants": [{"instance_id": f"instance-{role}", "provider_id": provider,
                          "model": None} for role, provider in roles],
        "workflow_id": "desk-standard", "revision": 2,
        "assignments": {role: f"instance-{role}" for role, _ in roles}, "task_id": "task-t1"}
    for row in (run, brief, instruction, materials, preview):
        assert row[4] == {**ids, "workflow": "desk-standard", "run": "task-t1-r1"}, row[0]
    assert [row[1:3] for row in (brief, instruction, materials, preview)] == [
        ["artifacts", "task-t1-r1"], ["artifacts", "task-t1-r1"], ["materials", "task-t1-r1"],
        ["automationPreview", "task-t1-r1"]]
    assert preview[3] == {}


def test_the_documents_are_the_brief_then_the_instructions_then_the_materials_by_their_bytes():
    out = run_js(CHAIN + """
      const state = ready();
      const done = drive(press(state, "ru"));
      const docs = done.log.filter((ask) => ask.name === "prep_doc").map((ask) => ask.body);
      const brief = wiz.briefDocument(state, "ru"), text = wiz.taskText(state, "ru");
      show({docs, brief, text,
        materials: done.log.find((ask) => ask.name === "prep_materials").body,
        ids: [dig.documentId("task-t1-r1", "artifact-brief", "text/markdown", brief),
          dig.documentId("task-t1-r1", "instruction-do", "text/markdown", text)]});
    """, DATA, modules=MODULES)
    brief, instruction = out["docs"]
    assert brief == {"artifact_id": out["ids"][0], "artifact_ref": "artifact-brief",
                     "media_type": "text/markdown", "content": out["brief"]}
    assert instruction == {"artifact_id": out["ids"][1], "artifact_ref": "instruction-do",
                           "media_type": "text/markdown", "content": out["text"]}
    assert out["brief"].startswith("# Fix login\n\n## Что нужно сделать\n")
    assert out["materials"] == {"lang": "ru", "items": []}


def test_the_seed_is_sent_for_a_dispatch_cycle_and_skipped_when_it_stands_or_has_no_dispatch():
    out = run_js(CHAIN + """
      const names_of = (over, state = ready()) => names(drive(press(state), over).log);
      const view = drive(press(ready({}, d.flows.standard, d.git_view, {viewMode: true})));
      const shared = run(ready(), {type: "include-instructions", value: true});
      show({sent: names_of({}), standing: names_of({prep_read: () => ok(moved(d.prep_seeded))}),
        starter: names(drive(press(readyStarter())).log),
        view_body: view.log.find((ask) => ask.name === "prep_seed").body,
        agent_files: drive(press(shared)).log.find((ask) => ask.name === "prep_seed")
          .body.include_agent_instructions});
    """, DATA, modules=MODULES)
    assert "prep_seed" in out["sent"] and "prep_seed" not in out["standing"]
    assert "prep_seed" not in out["starter"], "no step of the starter cycle works in a folder"
    assert out["view_body"] == {"work_item_id": "work-001", "source": "git",
                                "expect_commit": None, "include_agent_instructions": False}
    assert out["agent_files"] is True


def test_a_saved_cycle_with_a_shared_instruction_is_written_with_instruction_from():
    out = run_js(CHAIN + """
      const base = structuredClone(d.flows.tester);
      const pin = {pinned: {workflow_id: "cycle-7c1e5a90", latest_revision: 2,
        set_by: "Вы: Василий", set_at: "2026-09-28T13:50:00Z"}};
      const state = land(run(ready({cycle_read: pin}, base),
        {type: "instruction-like", step_id: "tester", like: "do"}), flowOf(base));
      const done = drive(press(state), {prep_flow: () => ok({...flowOf(base),
        source: "published", draft_digest: null, published: {revision: 3, created: true}})});
      const flow = done.log.find((ask) => ask.name === "prep_flow");
      show({source: Object.keys(flow.body.source), steps: flow.body.source.flow.steps
          .filter((step) => step.type === "agent").map((step) => [step.step_id,
            step.instruction_from]),
        docs: done.log.filter((ask) => ask.name === "prep_doc")
          .map((ask) => ask.body.artifact_ref)});
    """, DATA, modules=MODULES)
    assert out["source"] == ["flow"]
    assert [row for row in out["steps"] if row[0] in ("do", "tester")] == [
        ["do", None], ["tester", "do"]]
    assert out["docs"] == ["artifact-brief", "instruction-do"]


def test_an_edited_text_after_the_write_landed_is_a_new_document_sent_again_with_a_new_preview():
    out = run_js(CHAIN + """
      const first = drive(press(ready()));
      const edited = run(first.state, {type: "instruction-own", step_id: "do", lang: "en"},
        {type: "instruction-edit", step_id: "do", text: "Do it differently."});
      const held = wiz.wantedAsks(edited).filter((ask) => /:prep:/.test(ask.id)).length;
      const second = drive(wiz.stepWizard(edited, {type: "prepare-start", lang: "en"}));
      show({held, second: second.log.map((ask) => [ask.name, ask.body?.artifact_ref ?? null]),
        ids: second.log.map((ask) => ask.id), phase: second.state.run.phase,
        first_ids: first.log.map((ask) => ask.id)});
    """, DATA, modules=MODULES)
    assert out["held"] == 0, "nothing is written until the owner presses the button again"
    assert out["second"] == [["prep_doc", "instruction-do"], ["preview", None]]
    assert not set(out["ids"]) & set(out["first_ids"]), "a new document is a new ask"
    assert out["phase"] == "review"


def test_a_lost_answer_asks_the_read_first_and_never_repeats_a_write_blindly():
    out = run_js(CHAIN + """
      const first = press(ready());
      const gone = answer(first, lost);
      const again = answer(gone, refused("service_refused", {detail: {task_id: "task-t1"}}));
      show({phase: gone.state.run.phase, after_loss: gone.asks.map(shape),
        first: first.asks[0].body, repeat: again.asks.map((ask) => [ask.name, ask.body]),
        repeat_ids: [first.asks[0].id, again.asks[0].id],
        links: [links(first.state), links(gone.state)]});
    """, DATA, modules=MODULES)
    assert out["phase"] == "unknown"
    assert out["after_loss"] == [["read:prep:0", "prep_read", "preparation", "task-t1"]]
    assert out["repeat"] == [["prep_task", out["first"]]], "the same bytes"
    assert out["repeat_ids"][0] != out["repeat_ids"][1]
    assert out["links"][0][0] == "running" and out["links"][1][0] == "unknown"


def test_a_lost_run_answer_is_settled_by_the_read_and_the_run_id_never_moves():
    out = run_js(CHAIN + """
      const upTo = (over) => drive(press(ready()), over);
      const seen = upTo({prep_run: () => lost, prep_read: (ask, _s, log) =>
        ok(log.length > 3 ? moved(d.prep_created) : moved(d.prep_new))});
      const notSeen = upTo({prep_run: (ask, _s, log) => (log.filter((one) =>
          one.name === "prep_run").length === 1 ? lost : ok({})),
        prep_read: (ask, _s, log) => ok({...moved(d.prep_new), next_run_number:
          log.filter((one) => one.name === "prep_read").length === 1 ? 1 : 2})});
      show({seen: names(seen.log), not_seen: notSeen.log.map((ask) => [ask.name,
        ask.name === "prep_run" ? ask.body.run_id : null])});
    """, DATA, modules=MODULES)
    assert out["seen"][3:8] == ["prep_flow", "prep_run", "prep_read", "prep_doc", "prep_doc"]
    assert "prep_run" not in out["seen"][5:], "the read shows the run: it is not written twice"
    runs = [row[1] for row in out["not_seen"] if row[0] == "prep_run"]
    assert runs == ["task-t1-r1", "task-t1-r1"], "the number the read now says does not move it"


def test_a_draft_conflict_on_the_flow_reads_it_and_closes_the_link_by_the_last_revision():
    out = run_js(CHAIN + """
      const conflict = {prep_flow: (ask, _s, log) => (log.filter((one) => one.name === "prep_flow")
        .length === 1 ? refused("draft_conflict") : ok(published()))};
      const equal = drive(press(ready()), conflict);
      const other = structuredClone(d.flows.standard);
      other.flow.title = "Changed elsewhere";
      const differs = drive(press(ready()), {...conflict, prep_flow_read: () => ok({...other,
        source: "published", draft_digest: null, latest_revision: 2})});
      show({equal: equal.log.map(shape).slice(3, 6), run_revision: equal.log.find((ask) =>
          ask.name === "prep_run").body.revision, phase: equal.state.run.phase,
        differs: differs.state.run.phase, refusal: differs.state.run.refusal,
        stops_at: names(differs.log).at(-1), links: links(differs.state)});
    """, DATA, modules=MODULES)
    assert [row[1:] for row in out["equal"]] == [
        ["prep_flow", "flow", "desk-standard"], ["prep_flow_read", "flowRead", "desk-standard"],
        ["prep_run", "runs", None]]
    assert out["run_revision"] == 2 and out["phase"] == "review"
    assert out["differs"] == "refused" and out["stops_at"] == "prep_flow_read"
    assert out["refusal"]["code"] == "draft_conflict" and out["refusal"]["link"] == "flow"
    assert out["links"][2] == "refused"


def test_a_record_conflict_on_the_run_offers_the_recorded_arrangement_or_the_next_number():
    out = run_js(CHAIN + """
      const clash = {prep_run: (ask, _s, log) => (log.filter((one) => one.name === "prep_run")
        .length === 1 ? refused("record_conflict") : ok({}))};
      const stopped = drive(press(ready()), clash);
      const adopted = drive(wiz.stepWizard(stopped.state, {type: "prepare-adopt"}), clash);
      const bumped = drive(wiz.stepWizard(stopped.state, {type: "prepare-bump"}), {
        prep_run: () => ok({}), prep_read: () => ok({...moved(d.prep_created),
          runs: moved(d.prep_created).runs.map((row) => ({...row, workflow_id: "cycle-old"}))})});
      const idle = wiz.stepWizard(ready(), {type: "prepare-adopt"});
      show({phase: stopped.state.run.phase, code: stopped.state.run.refusal.code,
        asks_left: stopped.last.asks.length, adopted: names(adopted.log),
        adopted_docs: adopted.log.filter((ask) => ask.name === "prep_doc").map((ask) => ask.subject),
        bumped: bumped.log.map((ask) => [ask.name, ask.name === "prep_run" ? ask.body.run_id : null]),
        idle_ignored: idle.asks.length === 0 && idle.state.run.phase === "idle"});
    """, DATA, modules=MODULES)
    assert out["phase"] == "refused" and out["code"] == "record_conflict"
    assert out["asks_left"] == 0
    assert out["adopted"][:2] == ["prep_doc", "prep_doc"] and set(out["adopted_docs"]) == {
        "task-t1-r1"}, "the run that stands is kept and its documents are written to it"
    assert out["bumped"][0][0] == "prep_read"
    assert ["prep_run", "task-t1-r2"] in out["bumped"]
    assert out["idle_ignored"] is True


def test_any_other_refusal_stops_at_its_link_and_a_retry_sends_the_same_bytes_under_a_new_id():
    out = run_js(CHAIN + """
      const wire = {error: {code: "seed_refused", message: "the base moved",
        detail: {reason: "base_moved"}}};
      const bad = {prep_seed: (ask, _s, log) => (log.filter((one) => one.name === "prep_seed")
        .length === 1 ? refused("seed_refused", wire) : ok({}))};
      const stopped = drive(press(ready()), bad);
      const retried = wiz.stepWizard(stopped.state, {type: "prepare-retry"});
      const asked = stopped.log.find((ask) => ask.name === "prep_seed");
      show({phase: stopped.state.run.phase, refusal: stopped.state.run.refusal,
        stopped: stopped.last.asks.length, links: links(stopped.state),
        retry: retried.asks.map((ask) => [ask.name, ask.body]),
        ids: [asked.id, retried.asks[0].id], body: asked.body,
        idle: wiz.stepWizard(ready(), {type: "prepare-retry"}).asks.length});
    """, DATA, modules=MODULES)
    assert out["phase"] == "refused" and out["stopped"] == 0
    assert out["refusal"] == {"job": "seed", "link": "seed", "code": "seed_refused",
                              "reason": "base_moved"}
    assert out["links"][:3] == ["done", "refused", "todo"]
    assert out["retry"] == [["prep_seed", out["body"]]] and out["ids"][0] != out["ids"][1]
    assert out["idle"] == 0


def test_an_answer_for_a_settled_or_a_foreign_ask_changes_nothing():
    out = run_js(CHAIN + """
      const first = press(ready());
      const landed = answer(first, ok({}));
      const twice = wiz.stepWizard(landed.state, {type: "answered", ask: first.asks[0],
        result: ok({})});
      const foreign = wiz.stepWizard(first.state, {type: "answered",
        ask: {...first.asks[0], id: "write:prep:task:deadbeef:0"}, result: ok({})});
      const malformed = wiz.stepWizard(first.state, {type: "answered", ask: first.asks[0],
        result: {status: "maybe"}});
      show({twice: twice.state === landed.state && twice.asks.length === 0,
        foreign: foreign.state === first.state, malformed: malformed.state === first.state});
    """, DATA, modules=MODULES)
    assert out == {"twice": True, "foreign": True, "malformed": True}


def test_the_hash_keeps_the_starter_key_until_the_run_is_written_and_names_no_document_or_text():
    out = run_js(CHAIN + """
      const done = drive(press(readyStarter()));
      show(done.log.map((ask) => [ask.name, ask.hash]));
    """, DATA, modules=MODULES)
    hashes = dict((row[0], row[1]) for row in out)
    start = {"task": "task-t1", "prepare": "1", "starter": "desk-starter-docs"}
    assert hashes["prep_task"] == start
    assert hashes["prep_flow"] == {**start, "workflow": "desk-starter-docs"}
    assert hashes["prep_run"] == {**start, "workflow": "desk-starter-docs", "run": "task-t1-r1"}
    assert hashes["prep_doc"] == {"task": "task-t1", "prepare": "1",
                                  "workflow": "desk-starter-docs", "run": "task-t1-r1"}
    assert all(set(hash_) <= {"task", "prepare", "workflow", "run", "starter"}
               for _, hash_ in out)


def test_the_links_are_said_done_running_todo_skipped_unknown_or_refused_as_they_stand():
    out = run_js(CHAIN + """
      const start = press(ready());
      const seeded = drive(start, {prep_flow: () => lost, prep_read: (ask, _s, log) =>
        (log.filter((one) => one.name === "prep_read").length === 1
          ? ok(moved(d.prep_new)) : refused("store_error"))});
      const skipped = drive(press(readyStarter()));
      show({idle: links(ready()), first: links(start.state), seeded: links(seeded.state),
        starter: links(skipped.state), review: links(drive(press(ready())).state)});
    """, DATA, modules=MODULES)
    assert out["idle"] == ["todo"] * 6
    assert out["first"] == ["running", "todo", "todo", "todo", "todo", "todo"]
    assert out["seeded"] == ["done", "done", "unknown", "todo", "todo", "todo"]
    assert out["starter"][1] == "skipped" and out["starter"] == [
        "done", "skipped", "done", "done", "done", "done"]
    assert out["review"] == ["done"] * 6
