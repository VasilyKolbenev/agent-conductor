"use strict";
// Step 3, "Цикл": which cycle the task runs, said from the reads the model hands over.
//
// Pure functions over plain values, importing nothing: the cards the owner may pick, the card
// that is picked beforehand and why, the body the flow write carries, and the facts of the
// server's answer. The wizard draws no budget and judges no flow of its own -- a number on this
// step is a number the server's answer carried, and `factsOf` hands that answer back unchanged.

//: The cycles the wizard offers as cards beside the project's saved ones (spec 7.9). The order
//: is the desk's own; it is never the order the server's `starters()` happens to give.
export const WIZARD_STARTERS = Object.freeze(["desk-standard", "desk-short"]);
const BUILD_CARD = Object.freeze({id: "build", kind: "build", workflowId: null, title: null,
  pinned: false, published: false, revision: null, locked: false, canPin: false,
  canUnpin: false});
const NO_SOURCE = Object.freeze({kind: "none", by: null, at: null, task: null, taskTitle: null,
  workflowId: null});

function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function rowsOf(read, key) {
  const rows = read && read.status === "ok" ? read.payload?.[key] : null;
  return Array.isArray(rows) ? rows.filter(record) : [];
}

//: The project's saved cycles: published, readable, and not the product's own (`desk-*`).
function savedRows(reads) {
  return rowsOf(reads.workflows, "workflows").filter((row) => typeof row.workflow_id === "string"
    && !row.workflow_id.startsWith("desk-") && Number.isSafeInteger(row.latest_revision)
    && row.unreadable !== true);
}

function pinnedOf(read) {
  const pinned = read && read.status === "ok" ? read.payload?.pinned : null;
  return record(pinned) && typeof pinned.workflow_id === "string" ? pinned : null;
}

function starterCard(reads, id, pinnedId, locked) {
  const row = rowsOf(reads.workflows, "workflows").find((one) => one.workflow_id === id);
  const published = Number.isSafeInteger(row?.latest_revision);
  const pinned = id === pinnedId;
  return {id, kind: "starter", workflowId: id, title: null, pinned, published,
    revision: published ? row.latest_revision : null, locked, canPin: published && !pinned
      && !locked, canUnpin: pinned && !locked};
}

function savedCard(row, pinnedId) {
  const pinned = row.workflow_id === pinnedId;
  return {id: row.workflow_id, kind: "saved", workflowId: row.workflow_id,
    title: typeof row.title === "string" ? row.title : row.workflow_id, pinned, published: true,
    revision: row.latest_revision, locked: false, canPin: !pinned, canUnpin: pinned};
}

//: The cards, in order: the pinned cycle first, the two ready cycles, the saved ones, and last
//: "build your own". A starter run shows one locked card and nothing else (spec 6.2).
export function cardsOf(reads, starterId) {
  if (starterId !== null) return [starterCard(reads, starterId, null, true)];
  const pinnedId = pinnedOf(reads.cycle_read)?.workflow_id ?? null;
  const cards = [...WIZARD_STARTERS.map((id) => starterCard(reads, id, pinnedId, false)),
    ...savedRows(reads).map((row) => savedCard(row, pinnedId))];
  return [...cards.filter((card) => card.pinned), ...cards.filter((card) => !card.pinned),
    BUILD_CARD];
}

// -- the card chosen beforehand ----------------------------------------------------------

//: The project's last run: its newest readable run that has a workflow, whether or not that
//: workflow is a card. An older run never stands in for it (spec 7.10).
function lastRun(reads) {
  const usable = rowsOf(reads.runs, "runs").filter((run) => run.unreadable !== true
    && typeof run.workflow_id === "string" && typeof run.created_at === "string");
  return usable.reduce((best, run) => (best === null || run.created_at > best.created_at
    ? run : best), null);
}

function titleOf(reads, taskId) {
  const task = rowsOf(reads.tasks, "tasks").find((row) => row.task_id === taskId);
  return task && task.unreadable !== true && typeof task.title === "string" ? task.title : null;
}

function choiceOf(card) {
  return {kind: card.kind, workflowId: card.workflowId};
}

//: The pinned cycle when it is a card, else the workflow of the project's last run when that is a
//: card (spec 7.10). It says where the choice came from, and says only what was read: a pinned
//: cycle that could not be read is reported as unread, never as absent, and a last run whose
//: workflow is not offered here (`last_run_uncarded`) chooses nothing and names that workflow,
//: instead of choosing an older run's cycle under the words "the last run". The pin and the last
//: run are looked up in the list of cycles, so when that list could not be read
//: (`workflowsUnread`) a cycle missing from it is unknown, not absent: nothing is chosen and no
//: source is claimed.
export function preselect(reads) {
  const cards = cardsOf(reads, null).filter((card) => card.kind !== "build");
  const cardFor = (id) => cards.find((card) => card.workflowId === id) ?? null;
  const base = {ready: ["workflows", "runs", "cycle_read"].every((name) => reads[name]),
    pinnedUnread: reads.cycle_read !== undefined && reads.cycle_read.status !== "ok",
    workflowsUnread: reads.workflows !== undefined && reads.workflows.status !== "ok"};
  //: Nothing is chosen while a read is out: the last run's cycle would be false if the pinned
  //: one has not been heard yet.
  if (!base.ready || base.workflowsUnread) return {...base, choice: null, source: NO_SOURCE};
  const pinned = pinnedOf(reads.cycle_read);
  const byPin = pinned === null ? null : cardFor(pinned.workflow_id);
  if (byPin !== null) {
    return {...base, choice: choiceOf(byPin), source: {kind: "pinned", by: pinned.set_by ?? null,
      at: pinned.set_at ?? null, task: null, taskTitle: null, workflowId: pinned.workflow_id}};
  }
  const run = lastRun(reads);
  if (run === null) return {...base, choice: null, source: NO_SOURCE};
  const card = cardFor(run.workflow_id);
  return {...base, choice: card === null ? null : choiceOf(card), source: {
    kind: card === null ? "last_run_uncarded" : "last_run", by: null, at: run.created_at,
    task: run.task_id ?? null, taskTitle: titleOf(reads, run.task_id),
    workflowId: run.workflow_id}};
}

// -- the flow write ----------------------------------------------------------------------

//: Whether an accepted answer is really the flow state of the workflow it was asked about. A ready
//: cycle nobody has written has neither a draft nor a revision, and the server answers `source:
//: "none"` with no flow: that is an answer (`allowNone`), not a refusal. A saved cycle always has
//: a flow, so for it the same answer is unreadable.
export function isFlowState(payload, workflowId, allowNone = false) {
  if (!record(payload) || payload.workflow_id !== workflowId) return false;
  const flowed = record(payload.flow)
    || (allowNone && payload.flow === null && payload.source === "none");
  return flowed && Array.isArray(payload.diagnostics) && typeof payload.publishable === "boolean";
}

//: `POST …/flow` (spec 7.1): the source is the ready cycle's own id, or the flow itself for a
//: saved one; exactly one of the two expectations, as the draft door has it, worded from the
//: digest of the draft that stands (`digest`, null when none does) as the last read or answer said;
//: and a publish revision only when the chain asks for one. Returns null while a saved cycle's
//: flow is unread.
export function flowBody(choice, flow, digest, publish, binding) {
  if (publish !== null && !Number.isSafeInteger(publish)) throw new Error("a revision is a number");
  let source = {starter_id: choice.workflowId};
  if (choice.kind !== "starter") {
    if (!flow) return null;
    source = {flow: flow.flow};
  }
  const expected = typeof digest === "string" ? {expected_digest: digest}
    : {expected_absent: true};
  return {source, ...expected, publish_revision: publish, binding};
}

//: The server's answer, unchanged. Nothing here adds, sums or corrects a number in it.
export function factsOf(cycle) {
  const flow = cycle.flow;
  return {workflowId: cycle.choice?.workflowId ?? null, status: cycle.status,
    refusal: cycle.refusal, fresh: flow !== null && cycle.flowGeneration === cycle.generation,
    source: flow?.source ?? null,
    revisions: flow === null ? null
      : {latest: flow.latest_revision ?? null, next: flow.next_revision ?? null},
    budget: flow?.budget ?? null, diagnostics: flow?.diagnostics ?? [],
    publishable: flow?.publishable === true};
}
