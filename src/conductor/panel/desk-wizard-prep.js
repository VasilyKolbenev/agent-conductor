"use strict";
// Step 5, «Подготовка»: the chain «Подготовить запуск» as pure functions (spec 6.4.1-6.4.3).
//
// The chain is six links -- the task, the seed, the cycle, the run, its documents and the preview
// -- written strictly in order, each only after the 200 or 201 of the one before. It is a value:
// `chainAsks` gives the ONE ask the state calls for (the same ask, with the same id, until an
// answer changes the state, so nothing is sent twice and nothing is sent in parallel), and
// `landChain` folds an answer in. A lost answer is `unknown` and is never repeated blindly: the
// preparation read comes first, and only what the read does not prove is sent again, with the
// same bytes (every id is a function of them). Every write says which keys of the desk's hash
// must stand before it is sent (`ask.hash`: the wizard's own keys `task`, `prepare`, `workflow`,
// `run`, `starter`, the whole set at that moment, an absent key meaning "not there"); the host
// writes them with `history.replaceState` and nothing else here touches the page, a clock, a
// random source or storage.
//
// It knows the wizard only through `input`, the plain facts `desk-wizard-input.js` reads off the
// state, and the `run` slice it folds answers into:
//   phase: idle | preparing | unknown | refused | review, pressed, lang, settled [ask ids],
//   done [job keys], attempts {job key: sends that did not settle}, seq (reads made), prep (the
//   last preparation read), readFailed, flowCheck, runId, revision, adopted, refusal, preview.
import {documentId, sha256Hex} from "./desk-wizard-digest.js";

export const LINKS = Object.freeze(["task", "seed", "flow", "run", "documents", "preview"]);
const MEDIA = "text/markdown";
const WORK_ITEM = "work-001";
const STARTS = Object.freeze(["idle", "review"]);

export function initialRun() {
  return {phase: "idle", pressed: false, lang: "en", settled: [], done: [], attempts: {}, seq: 0,
    prep: null, readFailed: null, flowCheck: false, runId: null, revision: null, adopted: null,
    refusal: null, preview: null, resume: null};
}

// -- after a reload ----------------------------------------------------------------------

/**
 * A reloaded page: the hash names the task, and maybe the run and the cycle; nothing else is
 * known until the preparation read answers. `texts` holds what the owner types again for the
 * documents the read says are missing, and `lost` is set when the server has no such task.
 */
export function openResume(run, resume) {
  return {...run, resume: {runId: resume.runId ?? null, workflowId: resume.workflowId ?? null,
    texts: {}, lost: false}};
}

/** The run of the task the hash names, as the read lists it, or null. */
export function resumeRow(run) {
  if (run.resume === null || run.prep === null || run.resume.runId === null) return null;
  return run.prep.runs.find((row) => row.run_id === run.resume.runId) ?? null;
}

const EXITS = Object.freeze(["queued", "authorized", "ended"]);

/**
 * What stands after a reload, from the read alone: `reading`, `failed`, `no_run` (the task stands
 * and nothing after it: what was typed and chosen is gone), `exit` (the run is past preparation),
 * `documents` (some are missing) or `preview` (nothing is). An older run of the task never stands
 * in for the one the hash names.
 */
export function resumeSituation(run) {
  if (run.resume === null) return null;
  if (run.readFailed !== null) return {kind: "failed", code: run.readFailed.code};
  if (run.prep === null) return {kind: "reading"};
  const row = resumeRow(run);
  if (row === null) return {kind: "no_run", title: run.prep.task.title};
  if (EXITS.includes(row.stage)) return {kind: "exit", runId: row.run_id, stage: row.stage};
  return {kind: row.stage === "documents_missing" ? "documents" : "preview", runId: row.run_id,
    revision: row.revision, workflowId: row.workflow_id, missing: row.missing};
}

/** The fields the missing documents need typed again, in the order of the read. */
export function resumeFields(missing, starter) {
  const fields = [];
  if (missing.inputs.includes("artifact-brief")) {
    fields.push(...(starter ? [{name: "idea", required: true, kept: "task"}]
      : [{name: "brief", required: true, kept: "task"}, {name: "hint", required: false,
        kept: "task"}]));
  }
  if (missing.inputs.includes("artifact-materials")) {
    fields.push({name: "materials", required: false, kept: "resume"});
  }
  return [...fields, ...missing.instructions.map((row) => ({name: `instruction:${row.node_id}`,
    required: true, kept: "resume"}))];
}

/** The one read a reloaded page makes before it says anything. */
export function resumeAsks(run, input) {
  if (run.resume === null || run.pressed || run.prep !== null || run.readFailed !== null
      || run.resume.lost) return [];
  return [{id: `read:prep:${run.seq}`, name: "prep_read", door: "read", target: "preparation",
    subject: input.taskId, body: null, job: null, hash: hashResumed(run, input)}];
}

function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

//: A value spelled the same whatever the order its keys were made in.
function stable(value) {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (record(value)) {
    const facts = Object.keys(value).sort()
      .map((key) => `${JSON.stringify(key)}:${stable(value[key])}`);
    return `{${facts.join(",")}}`;
  }
  return JSON.stringify(value);
}

// -- the links as jobs -------------------------------------------------------------------

//: One write of the chain: what it is called, the ask it makes, and the key that says it is done.
//: The key holds the bytes, so a text edited after its write landed is a different job.
function job(link, name, ask, target, subject, key, body) {
  return {link, name, ask, target, subject, key, body};
}

function taskSpec(input) {
  return job("task", "task", "prep_task", "tasks", null, `task:${input.taskId}:${input.title}`,
    {task_id: input.taskId, title: input.title});
}

function seedSpec(input) {
  const body = {work_item_id: WORK_ITEM, source: "git", expect_commit: input.seed.commit,
    include_agent_instructions: input.seed.include};
  return job("seed", "seed", "prep_seed", "seed", input.taskId, `seed:${stable(body)}`, body);
}

function flowSpec(input) {
  return job("flow", "flow", "prep_flow", "flow", input.workflowId,
    `flow:${stable(input.flowBody)}`, input.flowBody);
}

function runSpec(input, run) {
  const body = {run_id: run.runId, cycle_id: run.runId, mode: "policy",
    automation_contract: "bounded-run-v1", participants: input.participants,
    workflow_id: input.workflowId, revision: run.revision, assignments: input.assignments,
    task_id: input.taskId};
  return job("run", "run", "prep_run", "runs", null, `run:${stable(body)}`, body);
}

function documentSpec(run, paper) {
  const id = documentId(run.runId, paper.ref, MEDIA, paper.content);
  return job("documents", `doc-${paper.ref}`, "prep_doc", "artifacts", run.runId, `doc:${id}`,
    {artifact_id: id, artifact_ref: paper.ref, media_type: MEDIA, content: paper.content});
}

function materialsSpec(input, run) {
  return job("documents", "materials", "prep_materials", "materials", run.runId,
    `materials:${run.runId}:${stable(input.materials)}`, input.materials);
}

//: Every write since the last preview changes what the preview says (spec 6.4.1: any record in the
//: journal changes the digest the grant is checked against), so the preview is owed again whenever
//: another write landed after it.
function previewSpec(run) {
  const writes = run.done.filter((key) => !key.startsWith("preview:")).length;
  return job("preview", "preview", "preview", "automationPreview", run.runId,
    `preview:${run.runId}:${writes}`, {});
}

//: After a reload the task, the seed, the cycle and the run stand; what is left is the documents
//: the read says are missing, from the text typed again, and the preview.
function resumedSpecs(run, input) {
  const list = input.documents.map((paper) => documentSpec(run, paper));
  if (input.materials !== null) list.push(materialsSpec(input, run));
  return [...list, previewSpec(run)];
}

//: The writes still to make, in the order of the chain. The run and what follows it can be
//: spelled only once the cycle is published and the run's number is fixed.
function pendingSpecs(run, input) {
  if (input.resumed) return resumedSpecs(run, input).filter((spec) => !run.done.includes(spec.key));
  if (input.flowBody === null || run.prep === null) return [];
  const list = [];
  if (input.dispatch && run.prep.seed === null) list.push(seedSpec(input));
  list.push(flowSpec(input));
  if (run.runId !== null && run.revision !== null) {
    if (run.adopted !== run.runId) list.push(runSpec(input, run));
    list.push(...input.documents.map((paper) => documentSpec(run, paper)));
    list.push(materialsSpec(input, run), previewSpec(run));
  }
  return list.filter((spec) => !run.done.includes(spec.key));
}

// -- the asks ----------------------------------------------------------------------------

//: The whole set of the wizard's hash keys at a link (spec 6.4.3): the task and `prepare` before
//: the first write, the cycle before link 3, the run before link 4, and the starter until link 4.
function hashAt(link, input, run) {
  const at = LINKS.indexOf(link);
  const keys = {task: input.taskId, prepare: "1"};
  if (at >= LINKS.indexOf("flow") && input.workflowId !== null) keys.workflow = input.workflowId;
  if (at >= LINKS.indexOf("run") && run.runId !== null) keys.run = run.runId;
  if (input.starterId !== null && at <= LINKS.indexOf("run")) keys.starter = input.starterId;
  return keys;
}

//: The keys a reloaded page opened with, which stand until the owner presses the button.
function hashResumed(run, input) {
  const keys = {task: input.taskId, prepare: "1"};
  if (run.resume.workflowId !== null) keys.workflow = run.resume.workflowId;
  if (run.resume.runId !== null) keys.run = run.resume.runId;
  if (input.starterId !== null) keys.starter = input.starterId;
  return keys;
}

/**
 * The wizard's keys of the desk's hash as they stand now, or null when it wants none: a wizard
 * that has not begun writing, or one that started over. Before a write the ask itself says them
 * (`ask.hash`); this is the same set for the moments no ask is made.
 */
export function hashNow(run, input) {
  if (run.resume !== null && !run.pressed) return hashResumed(run, input);
  if (!run.pressed) return null;
  const open = linkStates(run, input).find((row) => row.status !== "done"
    && row.status !== "skipped");
  return hashAt(open === undefined ? "preview" : open.link, input, run);
}

function writeAsk(run, input, spec) {
  const sent = run.attempts[spec.key] ?? 0;
  return {id: `write:prep:${spec.name}:${sha256Hex(spec.key).slice(0, 8)}:${sent}`, name: spec.ask,
    door: "write", target: spec.target, subject: spec.subject, body: spec.body, job: spec.key,
    hash: hashAt(spec.link, input, run)};
}

function readAsk(run, input, name, id, target, subject, link) {
  return {id, name, door: "read", target, subject, body: null, job: null,
    hash: hashAt(link, input, run)};
}

/**
 * The ask the chain calls for now: none, or exactly one.
 *
 * @param {object} run The `run` slice.
 * @param {object} input The plain facts of the wizard (`desk-wizard-input.js`).
 * @returns {object[]} At most one ask.
 */
export function chainAsks(run, input) {
  if (!run.pressed || (run.phase !== "preparing" && run.phase !== "unknown")) return [];
  const read = () => readAsk(run, input, "prep_read", `read:prep:${run.seq}`, "preparation",
    input.taskId, "task");
  if (run.phase === "unknown") return run.readFailed === null ? [read()] : [];
  const task = taskSpec(input);
  if (!input.resumed && !run.done.includes(task.key)) return [writeAsk(run, input, task)];
  if (run.prep === null) return [read()];
  if (run.flowCheck) {
    return [readAsk(run, input, "prep_flow_read", `read:prep:flow:${run.seq}`, "flowRead",
      input.workflowId, "flow")];
  }
  const next = pendingSpecs(run, input)[0];
  return next === undefined ? [] : [writeAsk(run, input, next)];
}

// -- the owner's four moves --------------------------------------------------------------

/**
 * «Подготовить запуск»: the chain begins, or begins again after edits made past a preview.
 * With nothing left to write it changes nothing.
 */
export function startChain(run, input, lang) {
  if (!STARTS.includes(run.phase)) return run;
  if (input.resumed) {
    const row = resumeRow(run);
    return row === null ? run : {...run, pressed: true, lang, phase: "preparing", refusal: null,
      runId: row.run_id, revision: row.revision, adopted: row.run_id};
  }
  const task = taskSpec(input);
  const done = input.taskWritten && !run.done.includes(task.key) ? [...run.done, task.key]
    : run.done;
  const next = {...run, pressed: true, lang, phase: "preparing", refusal: null, done};
  return run.phase === "review" && run.prep !== null && pendingSpecs(next, input).length === 0
    ? run : next;
}

/** «Повторить»: a refusal is tried again (its ask has a new id); a failed read is asked again. */
export function retryChain(run) {
  if (run.phase === "refused") return {...run, phase: "preparing", refusal: null};
  const reading = run.phase === "unknown" || (run.resume !== null && !run.pressed);
  if (reading && run.readFailed !== null) return {...run, readFailed: null};
  return run;
}

/** After a `record_conflict`: keep the run that stands, whatever its arrangement was. */
export function adoptRun(run) {
  if (run.phase !== "refused" || run.refusal?.code !== "record_conflict") return run;
  return {...run, phase: "preparing", refusal: null, adopted: run.runId};
}

/** After a `record_conflict`: open the next number, read from the server again. */
export function bumpRun(run) {
  if (run.phase !== "refused" || run.refusal?.code !== "record_conflict") return run;
  return {...run, phase: "preparing", refusal: null, runId: null, prep: null, adopted: null};
}

// -- the answers -------------------------------------------------------------------------

function isPreparation(payload, taskId) {
  return record(payload) && record(payload.task) && payload.task.task_id === taskId
    && (payload.seed === null || record(payload.seed)) && Array.isArray(payload.runs)
    && payload.runs.every((row) => record(row) && typeof row.run_id === "string")
    && Number.isSafeInteger(payload.next_run_number) && payload.next_run_number >= 1;
}

//: The run's id is the task's and the number the read gave when the cycle was published, fixed
//: from then on: a read made after a lost answer counts the run it did not see answered.
function fixRun(run, input) {
  if (run.runId !== null || run.revision === null || run.prep === null) return run;
  return {...run, runId: `${input.taskId}-r${run.prep.next_run_number}`};
}

//: What a fresh read proves: the task stands, the seed stands, and a run under our id with our
//: cycle means the cycle was published for it.
function reconcile(run, input) {
  const done = new Set([...run.done, taskSpec(input).key]);
  if (input.dispatch && run.prep.seed !== null) done.add(seedSpec(input).key);
  const row = run.runId === null ? null : run.prep.runs.find((one) => one.run_id === run.runId);
  let next = {...run};
  if (row && row.workflow_id === input.workflowId && Number.isSafeInteger(row.revision)) {
    next = {...next, revision: row.revision};
    done.add(flowSpec(input).key);
    done.add(runSpec(input, next).key);
  }
  return {...next, done: [...done]};
}

function landRead(run, input, result) {
  const seq = run.seq + 1, failed = {code: result.code ?? result.status};
  const accepted = result.status === "accepted" && isPreparation(result.payload, input.taskId);
  const unknownTask = result.status === "refused" && result.code === "service_refused";
  if (run.resume !== null && !run.pressed) {
    if (accepted) return {...run, seq, prep: result.payload, readFailed: null};
    if (unknownTask) return {...run, seq, readFailed: null, resume: {...run.resume, lost: true}};
    return {...run, seq, readFailed: failed};
  }
  if (accepted) {
    const read = {...run, seq, prep: result.payload, readFailed: null, phase: "preparing"};
    return input.resumed ? read : reconcile(fixRun(read, input), input);
  }
  if (unknownTask && input.resumed) {
    return refusedAt({...run, seq}, "task", "service_refused", null);
  }
  if (unknownTask) {
    return {...run, seq, prep: null, readFailed: null, phase: "preparing",
      done: run.done.filter((key) => !key.startsWith("task:"))};
  }
  return {...run, seq, phase: "unknown", readFailed: failed};
}

function refusedAt(run, name, code, reason) {
  const link = name.startsWith("doc-") || name === "materials" ? "documents" : name;
  return {...run, phase: "refused", refusal: {job: name, link, code, reason}};
}

//: A flow write that met another window's draft: the last revision may be exactly this cycle
//: (a lost answer landed), and then the link is closed by it; else the cycle changed elsewhere.
function landFlowRead(run, input, result) {
  const seq = run.seq + 1, page = input.flowDoc === null ? null : stable(input.flowDoc);
  const payload = result.payload;
  if (result.status === "accepted" && payload?.source === "published" && page !== null
      && stable(payload.flow) === page && Number.isSafeInteger(payload.latest_revision)) {
    const closed = {...run, seq, flowCheck: false, revision: payload.latest_revision,
      done: [...run.done, flowSpec(input).key]};
    return fixRun(closed, input);
  }
  const base = {...run, seq, flowCheck: false};
  return result.status === "unknown" ? {...base, phase: "unknown"}
    : refusedAt(base, "flow", "draft_conflict", null);
}

function acceptedWrite(run, input, ask, payload) {
  const done = [...run.done, ask.job];
  if (ask.name === "prep_flow") {
    const revision = payload?.published?.revision;
    if (!Number.isSafeInteger(revision)) return unreadable(run, ask);
    return fixRun({...run, done, revision, flowCheck: false}, input);
  }
  return ask.name === "preview" ? {...run, done, phase: "review", preview: payload}
    : {...run, done};
}

function jobName(ask) {
  return ask.id.split(":")[2];
}

function unreadable(run, ask) {
  const attempts = {...run.attempts, [ask.job]: (run.attempts[ask.job] ?? 0) + 1};
  return refusedAt({...run, attempts}, jobName(ask), "answer_unreadable", null);
}

function landWrite(run, input, ask, result) {
  if (result.status === "accepted") return acceptedWrite(run, input, ask, result.payload);
  const attempts = {...run.attempts, [ask.job]: (run.attempts[ask.job] ?? 0) + 1};
  const base = {...run, attempts};
  if (result.status === "unknown") return {...base, phase: "unknown"};
  const code = result.code ?? "refused";
  if (ask.name === "prep_flow" && code === "draft_conflict") return {...base, flowCheck: true};
  const detail = result.payload?.error?.detail ?? result.payload?.detail;
  return refusedAt(base, jobName(ask), code, detail?.reason ?? null);
}

/**
 * Fold one answer of the chain in. An answer already settled changes nothing.
 *
 * @param {object} run The `run` slice.
 * @param {object} input The plain facts of the wizard.
 * @param {object} ask The ask that was performed, as it was handed out.
 * @param {object} result `{status: "accepted" | "refused" | "unknown", code, payload}`.
 * @returns {object} The next `run` slice.
 */
export function landChain(run, input, ask, result) {
  if ((!run.pressed && run.resume === null) || run.settled.includes(ask.id)) return run;
  const base = {...run, settled: [...run.settled, ask.id]};
  if (ask.name === "prep_read") return landRead(base, input, result);
  if (ask.name === "prep_flow_read") return landFlowRead(base, input, result);
  return landWrite(base, input, ask, result);
}

// -- what the step says ------------------------------------------------------------------

//: After a reload the four first links stand, since a run stands; the documents are done when
//: everything the read said was missing has been written, and the preview when it was made.
function resumedDone(run, input, link) {
  if (link !== "documents" && link !== "preview") return true;
  const row = resumeRow(run);
  if (row === null) return false;
  const held = {...run, runId: row.run_id};
  const specs = input.documents.map((paper) => documentSpec(held, paper));
  if (input.materials !== null) specs.push(materialsSpec(input, held));
  return link === "documents" ? specs.every((spec) => run.done.includes(spec.key))
    : run.done.includes(previewSpec(held).key);
}

function linkDone(run, input, link) {
  if (input.resumed) return resumedDone(run, input, link);
  if (link === "task") return run.done.includes(taskSpec(input).key);
  if (link === "seed") {
    return !input.dispatch || run.done.includes(seedSpec(input).key)
      || (run.prep !== null && run.prep.seed !== null);
  }
  if (link === "flow") return input.flowBody !== null && run.done.includes(flowSpec(input).key);
  if (run.runId === null || run.revision === null) return false;
  if (link === "run") {
    return run.adopted === run.runId || run.done.includes(runSpec(input, run).key);
  }
  if (link === "documents") {
    return [...input.documents.map((paper) => documentSpec(run, paper)),
      materialsSpec(input, run)].every((spec) => run.done.includes(spec.key));
  }
  return run.done.includes(previewSpec(run).key);
}

/**
 * The state of each link, in order: `done`, `skipped` (a cycle with no step that works in a
 * folder has no seed), `running`, `unknown` (an answer was lost), `refused`, or `todo`.
 */
export function linkStates(run, input) {
  let current = null;
  return LINKS.map((link) => {
    const done = linkDone(run, input, link);
    const noSeed = input.resumed ? run.prep === null || run.prep.seed === null : !input.dispatch;
    if (done) return {link, status: link === "seed" && noSeed ? "skipped" : "done"};
    current = current ?? link;
    if (link !== current || !run.pressed) return {link, status: "todo"};
    if (run.phase === "refused") return {link, status: "refused"};
    return {link, status: run.phase === "unknown" ? "unknown" : "running"};
  });
}
