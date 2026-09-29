"""The wizard model's step 5 after a reload (spec 6.4.3): resume from the preparation read alone.

Nothing is stored in the browser, so a reloaded page knows only what the hash names (the task,
`prepare=1`, and the workflow, run and starter once the chain reached them) and what the
preparation read says. The model reads first, says what stands, asks again only for the text of
the documents the read says are missing, and never sends a recorded document again. What a
reload cannot bring back (typed text, the roles) is said, not guessed.
"""
from __future__ import annotations

import re

from tests.desk_wizard_node import PRELUDE, fixture, run_js

MODULES = {"wiz": "desk-wizard-model.js", "dig": "desk-wizard-digest.js"}
DATA = {name: fixture("wizard", f"preparation_{name}.json") for name in (
    "new", "seeded", "run_created", "documents_missing", "ready", "queued", "authorized",
    "ended")}
DATA["preview"] = fixture("wizard", "preview_standard.json")
RESUME = PRELUDE + """
const ok = (payload) => ({status: "accepted", payload});
const lost = {status: "unknown"};
const refused = (code, payload = null) => ({status: "refused", code, payload});
const moved = (value) => JSON.parse(JSON.stringify(value).replaceAll("task-bench", "task-t1"));
const resumed = (over = {}, resume = {runId: "task-t1-r1", workflowId: "desk-standard"}) =>
  wiz.initialWizard({starterId: null, viewMode: false, newTaskId: "task-t1", resume, ...over});
const begin = (state) => wiz.stepWizard(state, {type: "open"});
const answer = (step, result) => wiz.stepWizard(step.state, {type: "answered",
  ask: step.asks.find((ask) => ask.name === "prep_read") ?? step.asks[0], result});
const readAsk = (step) => step.asks.find((ask) => ask.name === "prep_read");
const landed = (name, over = {}) => {
  const first = begin(resumed(over));
  return wiz.stepWizard(first.state, {type: "answered", ask: readAsk(first),
    result: ok(moved(d[name]))});
};
const drive = (first, over = {}) => {
  const table = {prep_doc: () => ok({}), prep_materials: () => ok({}),
    preview: () => ok(moved(d.preview)), ...over}, log = [];
  let step = first;
  for (let at = 0; at < 20 && step.asks.length > 0; at += 1) {
    const [ask] = step.asks;
    log.push(ask);
    step = wiz.stepWizard(step.state, {type: "answered", ask, result: table[ask.name](ask)});
  }
  return {state: step.state, log};
};
const links = (state) => wiz.chainLinks(state).map((row) => row.status);
"""


def test_the_hash_of_a_preparation_opens_a_resume_only_with_a_valid_task_and_prepare_one():
    out = run_js(RESUME + """
      const of = (keys, starters = ["desk-starter-docs"]) => wiz.resumeFrom(keys, starters);
      show({plain: of({task: "task-a", prepare: "1"}),
        full: of({task: "task-a", prepare: "1", run: "task-a-r1", workflow: "desk-standard",
          new: "task", starter: "desk-starter-docs"}),
        no_task: of({prepare: "1"}), bad_task: of({task: "../x", prepare: "1"}),
        not_one: of({task: "task-a", prepare: "2"}), none: of({task: "task-a"}),
        unknown_starter: of({task: "task-a", prepare: "1", new: "task", starter: "desk-short"}),
        starter_unread: of({task: "task-a", prepare: "1", new: "task",
          starter: "desk-starter-docs"}, null),
        bad_run: of({task: "task-a", prepare: "1", run: "a b"}), nothing: of(null)});
    """, DATA, modules=MODULES)
    assert out["plain"] == {"taskId": "task-a", "runId": None, "workflowId": None,
                            "starterId": None}
    assert out["full"] == {"taskId": "task-a", "runId": "task-a-r1", "workflowId": "desk-standard",
                           "starterId": "desk-starter-docs"}
    assert out["no_task"] is None and out["bad_task"] is None and out["not_one"] is None
    assert out["none"] is None and out["nothing"] is None
    assert out["unknown_starter"]["starterId"] is None
    assert out["starter_unread"]["starterId"] is None, "the list of starters is not yet read"
    assert out["bad_run"]["runId"] is None


def test_a_resumed_wizard_opens_on_the_preparation_step_and_reads_before_anything_else():
    out = run_js(RESUME + """
      const state = resumed();
      const step = begin(state);
      show({step: state.step, resume: state.run.resume, written: state.task.written,
        asks: step.asks.map((ask) => [ask.id, ask.name, ask.door, ask.target, ask.subject,
          ask.hash]),
        wanted: wiz.wantedAsks(step.state).map((ask) => ask.name).filter((name) =>
          ["flow_read", "flow", "previous_run", "previous_revision", "document"].includes(name)),
        hash: wiz.wizardHash(state), fresh_hash: wiz.wizardHash(open())});
    """, DATA, modules=MODULES)
    assert out["step"] == "prepare" and out["written"] is False
    assert out["resume"] == {"runId": "task-t1-r1", "workflowId": "desk-standard", "texts": {},
                             "lost": False}
    names = [row[1] for row in out["asks"]]
    assert names.count("prep_read") == 1
    read = next(row for row in out["asks"] if row[1] == "prep_read")
    assert read == ["read:prep:0", "prep_read", "read", "preparation", "task-t1",
                    {"task": "task-t1", "prepare": "1", "workflow": "desk-standard",
                     "run": "task-t1-r1"}]
    assert out["wanted"] == [], "a resumed wizard fills in nothing, so it reads no cycle or history"
    assert out["hash"] == read[5] and out["fresh_hash"] is None


def test_a_task_the_server_does_not_know_starts_the_wizard_over_at_step_one():
    out = run_js(RESUME + """
      const first = begin(resumed());
      const over = answer(first, refused("service_refused", {error: {code: "service_refused",
        detail: {task_id: "task-t1"}}}));
      show({step: over.state.step, resume: over.state.run.resume, written: over.state.task.written,
        hash: wiz.wizardHash(over.state), asks: over.asks.map((ask) => ask.name),
        title: over.state.task.title});
    """, DATA, modules=MODULES)
    assert out["step"] == "task" and out["resume"] is None and out["written"] is False
    assert out["hash"] is None and out["title"] == ""
    assert "prep_read" not in out["asks"]


def test_a_task_with_no_run_says_the_texts_and_roles_were_lost_and_can_be_filled_in_again():
    out = run_js(RESUME + """
      const step = landed("seeded");
      const view = wiz.resumeView(step.state);
      const again = wiz.stepWizard(step.state, {type: "resume-restart"});
      const fresh = again.state;
      show({view, title: step.state.task.title, written: step.state.task.written,
        gate: wiz.resumeGate(step.state), step: fresh.step, resume: fresh.run.resume,
        fresh_title: fresh.task.title, fresh_written: fresh.task.written,
        locked: wiz.stepWizard(fresh, {type: "edit-title", value: "Other"}).state === fresh,
        hash: wiz.wizardHash(fresh), ignored: wiz.stepWizard(begin(resumed()).state,
          {type: "resume-restart"}).asks.length});
    """, DATA, modules=MODULES)
    assert out["view"] == {"kind": "no_run", "title": "Fix login"}
    assert out["title"] == "Fix login" and out["written"] is True
    assert out["gate"] == {"ok": False, "reason": "resume_pending", "step": "prepare"}
    assert out["step"] == "task" and out["resume"] is None
    assert out["fresh_title"] == "Fix login" and out["fresh_written"] is True
    assert out["locked"] is True and out["hash"] is None


def test_a_run_with_documents_missing_asks_only_for_those_fields_in_the_order_of_the_read():
    out = run_js(RESUME + """
      const all = landed("run_created").state, some = landed("documents_missing").state;
      const fields = (state) => wiz.resumeView(state).fields;
      show({all: fields(all), some: fields(some), view: wiz.resumeView(some),
        gate_empty: wiz.resumeGate(some)});
    """, DATA, modules=MODULES)
    assert [row["name"] for row in out["all"]] == [
        "brief", "hint", "materials", "instruction:do"]
    assert [row["name"] for row in out["some"]] == ["materials", "instruction:do"]
    assert [row["required"] for row in out["some"]] == [False, True]
    assert out["view"]["kind"] == "documents" and out["view"]["runId"] == "task-t1-r1"
    assert out["gate_empty"] == {"ok": False, "reason": "instruction_empty", "step": "prepare"}


def test_only_the_missing_documents_are_written_from_the_retyped_text_and_never_the_others():
    out = run_js(RESUME + """
      const base = landed("documents_missing").state;
      const filled = [{type: "resume-edit", name: "instruction:do", value: "Do the login form."},
        {type: "resume-edit", name: "materials", value: "See the spec."}]
        .reduce((now, event) => wiz.reduceWizard(now, event), base);
      const bad = wiz.reduceWizard(base, {type: "resume-edit", name: "instruction:nope",
        value: "x"});
      const step = wiz.stepWizard(filled, {type: "prepare-start", lang: "en"});
      const done = drive(step);
      show({gate: wiz.resumeGate(filled), bad_ignored: bad === base,
        log: done.log.map((ask) => [ask.name, ask.target, ask.subject, ask.body, ask.hash]),
        id: dig.documentId("task-t1-r1", "instruction-do", "text/markdown", "Do the login form."),
        phase: done.state.run.phase, links: links(done.state)});
    """, DATA, modules=MODULES)
    assert out["gate"] == {"ok": True, "reason": None, "step": None}
    assert out["bad_ignored"] is True
    assert [row[0] for row in out["log"]] == ["prep_doc", "prep_materials", "preview"], (
        "no task, seed, cycle or run is written, and the brief the read does not miss stays")
    doc, materials, preview = out["log"]
    assert doc[1:4] == ["artifacts", "task-t1-r1", {
        "artifact_id": out["id"], "artifact_ref": "instruction-do", "media_type": "text/markdown",
        "content": "Do the login form."}]
    assert materials[1:3] == ["materials", "task-t1-r1"]
    assert materials[3] == {"lang": "en", "items": [
        {"kind": "note", "title": "Materials", "content": "See the spec."}]}
    assert preview[1:4] == ["automationPreview", "task-t1-r1", {}]
    keys = {"task": "task-t1", "prepare": "1", "workflow": "desk-standard", "run": "task-t1-r1"}
    assert doc[4] == materials[4] == preview[4] == keys
    assert out["phase"] == "review"
    assert out["links"] == ["done", "skipped", "done", "done", "done", "done"], (
        "the seed of this read is null and is not this chain's to write")


def test_an_empty_materials_field_writes_the_no_materials_document_and_the_brief_is_retyped():
    out = run_js(RESUME + """
      const base = landed("run_created").state;
      const filled = [{type: "edit-brief", value: "Fix it."},
        {type: "resume-edit", name: "instruction:do", value: "Do it."}]
        .reduce((now, event) => wiz.reduceWizard(now, event), base);
      const done = drive(wiz.stepWizard(filled, {type: "prepare-start", lang: "ru"}));
      show({names: done.log.map((ask) => ask.name), gate_before: wiz.resumeGate(base).reason,
        brief: done.log[0].body.content, materials: done.log.find((ask) =>
          ask.name === "prep_materials").body});
    """, DATA, modules=MODULES)
    assert out["gate_before"] == "brief_empty"
    assert out["names"] == ["prep_doc", "prep_doc", "prep_materials", "preview"]
    assert out["brief"] == "# Fix login\n\n## Что нужно сделать\nFix it.\n\n" \
        "## Как понять, что готово (подсказка)\n—\n"
    assert out["materials"] == {"lang": "ru", "items": []}


def test_a_run_that_is_ready_goes_straight_to_the_preview():
    out = run_js(RESUME + """
      const state = landed("ready").state;
      const done = drive(wiz.stepWizard(state, {type: "prepare-start", lang: "en"}));
      show({view: wiz.resumeView(state), gate: wiz.resumeGate(state),
        names: done.log.map((ask) => ask.name), phase: done.state.run.phase});
    """, DATA, modules=MODULES)
    assert out["view"]["kind"] == "preview" and out["gate"]["ok"] is True
    assert out["names"] == ["preview"] and out["phase"] == "review"


def test_a_run_past_the_preparation_is_an_exit_that_names_the_run_and_the_stage():
    out = run_js(RESUME + """
      const exits = Object.fromEntries(["queued", "authorized", "ended", "ready",
        "documents_missing", "seeded"].map((name) => [name,
        wiz.wizardExit(landed(name).state)]));
      show({exits, before_the_read: wiz.wizardExit(begin(resumed()).state),
        fresh: wiz.wizardExit(open()), gate: wiz.resumeGate(landed("queued").state)});
    """, DATA, modules=MODULES)
    assert out["exits"]["queued"] == {"runId": "task-t1-r1", "stage": "queued"}
    assert out["exits"]["authorized"] == {"runId": "task-t1-r1", "stage": "authorized"}
    assert out["exits"]["ended"] == {"runId": "task-t1-r1", "stage": "ended"}
    assert out["exits"]["ready"] is None and out["exits"]["documents_missing"] is None
    assert out["exits"]["seeded"] is None
    assert out["before_the_read"] is None and out["fresh"] is None
    assert out["gate"]["ok"] is False


def test_a_run_that_is_not_the_one_the_hash_names_is_no_run_and_an_older_run_never_stands_in():
    out = run_js(RESUME + """
      const other = landed("ended", {resume: {runId: "task-t1-r2", workflowId: null}});
      const none = landed("ended", {resume: {runId: null, workflowId: null}});
      show({named: wiz.resumeView(other.state).kind, unnamed: wiz.resumeView(none.state).kind,
        exit: wiz.wizardExit(other.state)});
    """, DATA, modules=MODULES)
    assert out == {"named": "no_run", "unnamed": "no_run", "exit": None}


def test_a_read_that_fails_is_said_and_asked_again_by_the_owner_and_never_guessed():
    out = run_js(RESUME + """
      const first = begin(resumed());
      const failed = answer(first, refused("store_error"));
      const lostRead = answer(first, lost);
      const again = wiz.stepWizard(failed.state, {type: "prepare-retry"});
      show({view: wiz.resumeView(failed.state), lost: wiz.resumeView(lostRead.state).kind,
        after_fail_asks: failed.asks.map((ask) => ask.name),
        retry: again.asks.map((ask) => [ask.id, ask.name]),
        reading: wiz.resumeView(first.state).kind, fresh: wiz.resumeView(open())});
    """, DATA, modules=MODULES)
    assert out["view"] == {"kind": "failed", "code": "store_error"}
    assert out["lost"] == "failed"
    assert "prep_read" not in out["after_fail_asks"]
    assert out["retry"] == [["read:prep:1", "prep_read"]]
    assert out["reading"] == "reading" and out["fresh"] is None


def test_a_starter_resume_keeps_its_key_in_the_hash_until_the_run_stands():
    out = run_js(RESUME + """
      const state = resumed({starterId: "desk-starter-docs"},
        {runId: null, workflowId: "desk-starter-docs"});
      const step = begin(state);
      show({hash: wiz.wizardHash(state), mode: state.mode,
        read: readAsk(step).hash});
    """, DATA, modules=MODULES)
    keys = {"task": "task-t1", "prepare": "1", "workflow": "desk-starter-docs",
            "starter": "desk-starter-docs"}
    assert out["hash"] == keys and out["read"] == keys
    assert out["mode"]["starterId"] == "desk-starter-docs"


def test_the_resume_text_events_are_taken_only_in_a_resumed_wizard_and_name_a_known_field():
    out = run_js(RESUME + """
      const fresh = open();
      const base = landed("documents_missing").state;
      const edits = (state, name, value) => wiz.stepWizard(state, {type: "resume-edit",
        name, value});
      show({fresh_ignored: edits(fresh, "materials", "x").state === fresh,
        not_a_string: edits(base, "materials", 7).state === base,
        same: edits(wiz.reduceWizard(base, {type: "resume-edit", name: "materials", value: "a"}),
          "materials", "a").state.run.resume.texts,
        brief_when_not_missing: edits(base, "brief", "x").state === base});
    """, DATA, modules=MODULES)
    assert out["fresh_ignored"] is True and out["not_a_string"] is True
    assert out["same"] == {"materials": "a"}
    assert out["brief_when_not_missing"] is True
