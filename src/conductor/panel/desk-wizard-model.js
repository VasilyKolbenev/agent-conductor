"use strict";
// The new-task wizard's state and every way it can change, as pure functions.
//
// The model is a reducer over one frozen `wizard` slice. Every edit is one event
// from the closed table `HANDLERS` (EVENTS is its key list, so the two cannot
// disagree), and nothing here reaches a clock, a random source, a store or a wire:
// an id the wizard needs is handed in, and an answer it wants from the server is a
// value it returns. `stepWizard(state, event)` gives back the next state and the
// asks that event made due, each ask handed out ONCE (its id is recorded in
// `state.asked`), so the host neither polls nor de-duplicates:
//
//   ask = {id, name, door: "read" | "write", target, subject, body}
//
// The host performs an ask through the door its `target` names and hands the
// outcome back as `{type: "answered", ask, result}`, `result` shaped exactly like
// the one door's own answer (`{status: "accepted" | "refused" | "unknown", code,
// payload}`). Nothing in this slice writes to a server; what a step would publish
// is only described (`publications`).
//
// The step modules hold the pure rules of each step (`desk-wizard-materials.js`, `-cycle.js`,
// `-roles.js`); `desk-wizard-base.js` holds what they share and `desk-wizard-team.js` applies
// step 4's rules to this state. This module is the state, the table of events and the asks.
//
// State shape (all frozen):
//   step, mode {starterId, view}, task {taskId, title, brief, hint, idea, written},
//   reads {name: {status: "ok" | "failed", code, payload}}, asked [ask id], opened, closing,
//   materials {items, counter, picker, refusal, includeInstructions},
//   cycle {choice, chosenBy, generation, flow, flowFor, flowGeneration, status, refusal,
//          settled, boundKey},
//   roles {owner, instructions}, history {runs, revisions}.
import {taskTitle, isTaskId} from "./studio-tasks-model.js";
import {MATERIAL_KINDS, bodyOf, documentCard, estimateOf, gitFacts, instructionsRow,
  isComplete, isDocumentRow, isMaterialKind, isOid, pickerOf, textCard}
  from "./desk-wizard-materials.js";
import {WIZARD_STARTERS, cardsOf, factsOf, flowBody, isFlowState, preselect}
  from "./desk-wizard-cycle.js";
import {argvFit, offersFor, quotaOf, roleKind, rolesOf, rosterOf, suggest}
  from "./desk-wizard-roles.js";
import {BUILT_STEPS, LIMITS, STEPS, briefDocument, evolve, frozen, inputChars, taskText,
  utf8Bytes} from "./desk-wizard-base.js";
import {answerHistory, assignRole, assignmentView, bindingNow, editInstruction, heldFlow,
  historyAsks, instructionFields, likeInstruction, ownInstruction, previousAssignment,
  rolesGate, rolesPublication, syncBinding} from "./desk-wizard-team.js";

//: The one starter the hash may name (spec 4.5.2). The two ready cycles the wizard offers as
//: cards are the cycle module's, re-exported here as the wizard's one vocabulary.
export const HASH_STARTERS = Object.freeze(["desk-starter-docs"]);
export {STEPS, BUILT_STEPS, LIMITS, MATERIAL_KINDS, WIZARD_STARTERS, argvFit, briefDocument,
  inputChars, offersFor, quotaOf, roleKind, rolesOf, rosterOf, taskText, utf8Bytes,
  assignmentView, instructionFields, previousAssignment};
export const suggestAssignment = suggest;
//: The controls whose door a later slice opens. Each is drawn disabled with its reason and
//: never as a button that does nothing.
export const LATER = Object.freeze(["connect_git", "first_commit", "run_without_git",
  "from_starter_docs", "build_own", "make_project_cycle", "prepare"]);

export function isLater(control) {
  return LATER.includes(control);
}

//: The reads a wizard asks for once it opens: every later step draws on one of them.
const OPENING_READS = Object.freeze([["git", "git"], ["workflows", "workflows"],
  ["runs", "runs"], ["cycle_read", "projectCycle"], ["tasks", "tasks"], ["quotas", "quotas"]]);
const READ_NAMES = Object.freeze(OPENING_READS.map(([name]) => name));

// -- opening ---------------------------------------------------------------------------

//: `starter` counts only beside `new=task`, only when the hash grammar allows it, and only
//: when the workflows read really lists it (`starters`, ids; null while unread).
export function openingFrom(keys, starters) {
  const named = keys && keys.new === "task" ? keys.starter : null;
  const known = Array.isArray(starters) && starters.includes(named);
  return Object.freeze({starterId: HASH_STARTERS.includes(named) && known ? named : null});
}

//: Nothing is prefilled (spec 6): every text field starts empty. What arrives from outside is
//: the task id the page drew, and -- for a task that is already written and being resumed --
//: the title the server holds for it, which is a record and not a default.
export function initialWizard(opening) {
  if (!opening || !isTaskId(opening.newTaskId)) {
    throw new Error("the wizard needs a task id from its caller");
  }
  const starterId = HASH_STARTERS.includes(opening.starterId) ? opening.starterId : null;
  const written = opening.taskWritten === true;
  const title = written && typeof opening.title === "string" ? opening.title : "";
  return frozen({step: "task", opened: false, asked: [], closing: null,
    mode: {starterId, view: opening.viewMode === true},
    task: {taskId: opening.newTaskId, title, brief: "", hint: "", idea: "", written},
    reads: {},
    materials: {items: [], counter: 0, picker: false, refusal: null,
      includeInstructions: null},
    cycle: {choice: starterId === null ? null : {kind: "starter", workflowId: starterId},
      chosenBy: starterId === null ? null : "starter", generation: starterId === null ? 0 : 1,
      flow: null, flowFor: null, flowGeneration: -1, status: "idle", refusal: null,
      settled: [], boundKey: "null"},
    roles: {owner: {}, instructions: {}},
    history: {runs: {}, revisions: {}}});
}

// -- step 1: the task ------------------------------------------------------------------

export function taskFields(state) {
  return Object.freeze(state.mode.starterId === null
    ? ["title", "brief", "hint"] : ["title", "idea"]);
}

function taskGate(state) {
  if (!taskTitle(state.task.title)) return "title_invalid";
  const starter = state.mode.starterId !== null;
  if ((starter ? state.task.idea : state.task.brief).trim() === "") {
    return starter ? "idea_empty" : "brief_empty";
  }
  return utf8Bytes(briefDocument(state, "ru")) > LIMITS.documentBytes ? "brief_too_large" : null;
}

function taskPublication(state, lang) {
  return {step: "task", writes: [
    {link: 1, target: "tasks", body: {task_id: state.task.taskId, title: state.task.title}},
    {link: 5, target: "artifacts", ref: "artifact-brief", media_type: "text/markdown",
      content: briefDocument(state, lang)}]};
}

// -- step 2: the materials --------------------------------------------------------------

//: Where the agents get their code, said from the one git read and the mode.
export function gitReading(state) {
  return gitFacts(state.reads.git, state.mode);
}

export function availableKinds(state) {
  return MATERIAL_KINDS.filter((kind) => kind !== "project_doc" || !state.mode.view);
}

export function materialsBody(state, lang) {
  return bodyOf(state.materials.items, lang);
}

//: The approximate size of what the cards compose ("≈": the server alone knows the exact one).
export function materialsEstimate(state) {
  return estimateOf(state.materials.items);
}

export function agentInstructionsRow(state) {
  return instructionsRow(state.reads.git, state.materials.includeInstructions);
}

export function documentPicker(state) {
  return pickerOf(state.materials.picker && !state.mode.view, state.reads.documents,
    state.materials.items);
}

//: Closing with cards that no server holds yet loses them, so it asks first (spec 6.2.2).
export function closeNeedsWarning(state) {
  return state.materials.items.length > 0;
}

function materialsGate(state) {
  const stop = gitReading(state).stop;
  if (stop !== null) return stop;
  const estimate = materialsEstimate(state);
  if (estimate.overCount) return "materials_over_count";
  if (!state.materials.items.every(isComplete)) return "material_incomplete";
  return estimate.overBytes ? "materials_over_bytes" : null;
}

function materialsPublication(state, lang) {
  return {step: "materials", writes: [
    {link: 2, target: "seed", later: true},
    {link: 5, target: "materials", ref: "artifact-materials", body: materialsBody(state, lang)}]};
}

// -- step 3: the cycle -------------------------------------------------------------------

export function cycleCards(state) {
  return cardsOf(state.reads, state.mode.starterId);
}

//: The card picked beforehand, and where the choice came from (spec 7.10).
export function preselection(reads) {
  return preselect(reads);
}

export function cycleFacts(state) {
  return factsOf(state.cycle);
}

//: `POST …/flow` for the chosen cycle. Its id carries the generation of the choice, so an
//: answer for a card the owner has left is told apart from the card they are on.
export function flowWriteRequest(state, {publish = null, binding = null} = {}) {
  const {choice, flow, flowFor, generation} = state.cycle;
  if (choice === null) return null;
  const held = flow !== null && flowFor === choice.workflowId ? flow : null;
  const body = flowBody(choice, held, publish, binding);
  return body === null ? null : {id: `write:flow:${generation}`, name: "flow", door: "write",
    target: "flow", subject: choice.workflowId, body};
}

function cycleGate(state) {
  const cycle = state.cycle;
  if (cycle.choice === null) return "cycle_none";
  if (cycle.status !== "idle") return `flow_${cycle.status}`;
  if (cycle.flow === null || cycle.flowFor !== cycle.choice.workflowId) return "flow_pending";
  return cycle.flow.publishable === true ? null : "flow_unpublishable";
}

function cyclePublication(state) {
  const {choice, flow} = state.cycle;
  const next = Number.isSafeInteger(flow.next_revision) ? flow.next_revision : null;
  return {step: "cycle", writes: [{link: 3, target: "flow", workflow_id: choice.workflowId,
    body: flowWriteRequest(state, {publish: next, binding: null}).body}]};
}

//: The preselection is applied once, when the three reads it needs have landed and the owner
//: has not chosen: after that the owner's card, and only theirs, moves the choice.
function applyPreselection(state) {
  const cycle = state.cycle;
  if (cycle.choice !== null || state.mode.starterId !== null) return state;
  const found = preselect(state.reads);
  if (!found.ready || found.choice === null) return state;
  return evolve(state, {cycle: {...cycle, choice: found.choice, chosenBy: "preselection",
    generation: cycle.generation + 1}});
}

function chooseCycle(state, event) {
  if (state.mode.starterId !== null) return state;
  const card = cycleCards(state).find((one) => one.id === event.id && one.kind !== "build");
  if (!card) return state;
  const cycle = state.cycle;
  const same = cycle.choice?.workflowId === card.workflowId;
  const left = same ? {} : {flow: null, flowFor: null, flowGeneration: -1, boundKey: "null"};
  return evolve(state, {cycle: {...cycle, ...left, choice: {kind: card.kind,
    workflowId: card.workflowId}, chosenBy: "owner", generation: cycle.generation + 1,
    status: "idle", refusal: null}});
}

// -- the steps and their gates ---------------------------------------------------------

//: Why a step is not complete yet, as a closed code (null when it is). One entry per built
//: step; a step with no entry has nothing to refuse.
const GATES = {task: taskGate, materials: materialsGate, cycle: cycleGate, roles: rolesGate};
const PUBLISHERS = {task: taskPublication, materials: materialsPublication,
  cycle: cyclePublication, roles: rolesPublication};

function gateOf(state, step) {
  return Object.hasOwn(GATES, step) ? GATES[step](state) : null;
}

export function nextStep(state) {
  return BUILT_STEPS[BUILT_STEPS.indexOf(state.step) + 1] ?? null;
}

//: Whether the current step is complete, and if not, the code that says why. It does not say
//: whether a step follows: the last built step is complete and still has nowhere to go.
export function canAdvance(state) {
  const reason = gateOf(state, state.step);
  return Object.freeze({ok: reason === null, reason});
}

export function stepStates(state) {
  const at = STEPS.indexOf(state.step);
  let blocker = null;
  return Object.freeze(STEPS.map((step, index) => {
    const built = BUILT_STEPS.includes(step);
    const failing = built ? gateOf(state, step) : null;
    let status = "later";
    if (built) {
      if (index === at) status = "current";
      else status = index < at ? "done" : blocker === null ? "ready" : "blocked";
    }
    const reason = status === "blocked" ? blocker : status === "current" ? failing : null;
    if (built && blocker === null && failing !== null) blocker = failing;
    return frozen({step, status, reason});
  }));
}

//: Forward only over steps whose gates pass; back is always allowed.
function moveTo(state, step) {
  const to = BUILT_STEPS.indexOf(step), at = BUILT_STEPS.indexOf(state.step);
  if (to < 0 || to === at) return state;
  const held = BUILT_STEPS.slice(0, to).some((prior) => gateOf(state, prior) !== null);
  return to > at && held ? state : evolve(state, {step});
}

//: What each step would publish once the chain of later slices sends it. The chain runs in
//: order, so a step publishes only when it and every step before it is complete, and no
//: descriptor carries an id the chain has yet to make.
export function publications(state, lang) {
  const rows = [];
  for (const step of BUILT_STEPS) {
    if (gateOf(state, step) !== null) break;
    if (Object.hasOwn(PUBLISHERS, step)) rows.push(frozen(PUBLISHERS[step](state, lang)));
  }
  return Object.freeze(rows);
}

// -- asks --------------------------------------------------------------------------------

function readAsk(name, target) {
  return {id: `read:${name}`, name, door: "read", target, subject: null, body: null};
}

function documentAsk(docId) {
  return {id: `read:document:${docId}`, name: "document", door: "read", target: "document",
    subject: docId, body: null};
}

//: The reads step 2 makes due: the list once the picker opens, and the text of each document
//: taken as a copy that has not been read yet. None of them exists in view (spec 9.1.6).
function materialAsks(state) {
  if (state.mode.view) return [];
  const asks = state.materials.picker ? [readAsk("documents", "documents")] : [];
  for (const card of state.materials.items) {
    if (card.kind === "project_doc" && card.mode === "copy" && !card.fetched) {
      asks.push(documentAsk(card.docId));
    }
  }
  return asks;
}

function flowReadAsk(id, workflowId) {
  return {id, name: "flow_read", door: "read", target: "flowRead", subject: workflowId,
    body: null};
}

//: The flow asks step 3 makes due, and only once the owner stands on that step: a conflict is
//: read again; a saved cycle is read before anything is written for it; a write goes only when
//: no other write is in flight, so it carries the digest the last answer left.
function cycleAsks(state) {
  const cycle = state.cycle;
  if (cycle.choice === null || BUILT_STEPS.indexOf(state.step) < BUILT_STEPS.indexOf("cycle")) {
    return [];
  }
  const id = cycle.choice.workflowId;
  if (cycle.status === "conflict") {
    return [flowReadAsk(`read:flow:${cycle.generation}:reread`, id)];
  }
  if (cycle.choice.kind === "saved" && heldFlow(state) === null) {
    return [flowReadAsk(`read:flow:${cycle.generation}`, id)];
  }
  const binding = bindingNow(state);
  if (cycle.choice.kind === "saved" && binding === null) return [];
  const ask = flowWriteRequest(state, {publish: null, binding});
  const busy = state.asked.some((sent) => sent.startsWith("write:flow:") && sent !== ask.id
    && !cycle.settled.includes(sent));
  return busy ? [] : [ask];
}

//: Every ask the state calls for, whether or not it went out already; `stepWizard` hands out
//: only those whose id is not yet in `asked`.
export function wantedAsks(state) {
  if (!state.opened) return [];
  return [...OPENING_READS.map(([name, target]) => readAsk(name, target)),
    ...materialAsks(state), ...cycleAsks(state), ...historyAsks(state)];
}

function readOf(result) {
  return result.status === "accepted"
    ? {status: "ok", code: null, payload: structuredClone(result.payload ?? null)}
    : {status: "failed", code: result.code ?? result.status, payload: null};
}

//: The three reads a preselection is made from; when one lands the choice may be made.
const PRESELECTING = Object.freeze(["workflows", "runs", "cycle_read"]);

function answerRead(name) {
  return (state, _ask, result) => {
    const next = evolve(state, {reads: {...state.reads, [name]: readOf(result)}});
    return PRESELECTING.includes(name) ? applyPreselection(next) : next;
  };
}

function generationOf(id) {
  return Number(id.split(":")[2]);
}

//: A flow answer, for a write or for the read that follows a conflict. It lands only on the
//: card the owner is still on and only if it is not older than the one already held; either
//: way its ask is settled, which frees the next write. A conflict is read again and told to the
//: owner, and only their next choice of the card writes again.
function landFlow(state, ask, result, wasWrite) {
  const cycle = state.cycle, settled = [...cycle.settled, ask.id];
  const onIt = cycle.choice !== null && cycle.choice.workflowId === ask.subject;
  if (!onIt || generationOf(ask.id) < cycle.flowGeneration) {
    return evolve(state, {cycle: {...cycle, settled}});
  }
  if (result.status === "accepted" && isFlowState(result.payload, ask.subject)) {
    const status = !wasWrite && cycle.status === "conflict" ? "changed_elsewhere" : "idle";
    return evolve(state, {cycle: {...cycle, settled, flow: structuredClone(result.payload),
      flowFor: ask.subject, flowGeneration: generationOf(ask.id), status, refusal: null}});
  }
  const code = result.status === "accepted" ? "answer_unreadable" : result.code ?? result.status;
  const status = code === "draft_conflict" ? "conflict"
    : result.status === "unknown" ? "unknown" : "refused";
  const rows = result.payload?.diagnostics ?? result.payload?.detail?.diagnostics ?? [];
  return evolve(state, {cycle: {...cycle, settled, status,
    refusal: {code, diagnostics: Array.isArray(rows) ? structuredClone(rows) : []}}});
}

//: A document read for a card taken as a copy. A refusal sends the card back to a link; only
//: "not text" is final, because it is a fact about the file and not about this attempt.
function answerDocument(state, ask, result) {
  const card = state.materials.items.find((one) => one.docId === ask.subject);
  if (!card) return state;
  const payload = result.payload;
  if (result.status === "accepted" && typeof payload?.content === "string") {
    return replaceCard(state, card, {content: payload.content, fetched: true,
      gitOid: isOid(payload.git_oid) ? payload.git_oid : card.gitOid, blocked: null});
  }
  const reason = payload?.detail?.reason ?? result.code ?? result.status;
  const final = reason === "document_not_text";
  return replaceCard(state, card, {mode: "link", blocked: final ? reason : "read_failed"},
    final ? reason : "read_failed");
}

const ANSWERS = {...Object.fromEntries([...READ_NAMES, "documents"]
  .map((name) => [name, answerRead(name)])), document: answerDocument,
  previous_run: answerHistory("runs"), previous_revision: answerHistory("revisions"),
  flow: (state, ask, result) => landFlow(state, ask, result, true),
  flow_read: (state, ask, result) => landFlow(state, ask, result, false)};

function validResult(result) {
  return result !== null && typeof result === "object"
    && ["accepted", "refused", "unknown"].includes(result.status);
}

function answered(state, event) {
  const {ask, result} = event;
  if (!ask || !state.asked.includes(ask.id) || !validResult(result)) return state;
  return Object.hasOwn(ANSWERS, ask.name) ? ANSWERS[ask.name](state, ask, result) : state;
}

function reread(state, event) {
  if (!READ_NAMES.includes(event.name) && event.name !== "documents") return state;
  const {[event.name]: _dropped, ...reads} = state.reads;
  return evolve(state, {reads, asked: state.asked.filter((id) => id !== `read:${event.name}`)});
}

// -- events on the cards -----------------------------------------------------------------

//: Every change to the cards clears the last refusal: a reason is about the last thing tried.
function withMaterials(state, patch, extra = {}) {
  return evolve(state, {...extra, materials: {...state.materials, refusal: null, ...patch}});
}

function refuse(state, code) {
  return state.materials.refusal === code ? state
    : evolve(state, {materials: {...state.materials, refusal: code}});
}

function replaceCard(state, card, patch, refusal = null, extra = {}) {
  const items = state.materials.items.map((one) => (one === card ? {...one, ...patch} : one));
  return evolve(state, {...extra, materials: {...state.materials, items, refusal}});
}

function listedRows(state) {
  const read = state.reads.documents;
  const rows = read && read.status === "ok" ? read.payload?.documents : null;
  return Array.isArray(rows) ? rows.filter(isDocumentRow) : [];
}

function nextCard(state, make) {
  const {counter, items} = state.materials;
  return withMaterials(state, {items: [...items, make(`m${counter + 1}`)], counter: counter + 1,
    picker: false});
}

function addDocument(state, event) {
  if (state.mode.view) return state;
  if (event.docId === undefined) {
    return state.materials.picker ? state : withMaterials(state, {picker: true});
  }
  if (state.materials.items.length >= LIMITS.materials) return refuse(state, "too_many_materials");
  if (state.materials.items.some((card) => card.docId === event.docId)) {
    return refuse(state, "already_added");
  }
  const row = listedRows(state).find((one) => one.doc_id === event.docId);
  return row ? nextCard(state, (key) => documentCard(key, row)) : refuse(state, "doc_unknown");
}

function addMaterial(state, event) {
  if (!isMaterialKind(event.kind)) return state;
  if (event.kind === "project_doc") return addDocument(state, event);
  if (state.materials.items.length >= LIMITS.materials) return refuse(state, "too_many_materials");
  return nextCard(state, (key) => textCard(key, event));
}

function cardOf(state, key) {
  return state.materials.items.find((card) => card.key === key);
}

//: A card's title is its own only when it is text; a copied document's text is editable, a
//: link has none. Anything else is a field the card does not have.
function editable(card, field) {
  if (field === "title") return card.kind !== "project_doc";
  return field === "content" && (card.kind !== "project_doc" || card.mode === "copy");
}

function editMaterial(state, event) {
  const card = cardOf(state, event.key);
  if (!card || typeof event.value !== "string" || !editable(card, event.field)
      || card[event.field] === event.value) return state;
  return replaceCard(state, card, {[event.field]: event.value});
}

function removeMaterial(state, event) {
  if (!cardOf(state, event.key)) return state;
  return withMaterials(state, {items: state.materials.items.filter((c) => c.key !== event.key)});
}

//: Link or copy for a project document. Asking for the text again is allowed while it has not
//: been read; a file the server called "not text" is refused before an ask is made.
function setMode(state, event) {
  const card = cardOf(state, event.key);
  if (!card || card.kind !== "project_doc" || card.mode === event.mode
      || !["link", "copy"].includes(event.mode)) return state;
  if (event.mode === "copy" && card.blocked === "document_not_text") {
    return refuse(state, "document_not_text");
  }
  const again = event.mode === "copy" && !card.fetched;
  const asked = again ? state.asked.filter((id) => id !== `read:document:${card.docId}`)
    : state.asked;
  return replaceCard(state, card, {mode: event.mode, blocked: null}, null, {asked});
}

// -- events ------------------------------------------------------------------------------

function editTask(field, allowed) {
  return (state, event) => {
    if (typeof event.value !== "string" || state.task[field] === event.value) return state;
    if (!allowed(state) || (field === "title" && state.task.written)) return state;
    return evolve(state, {task: {...state.task, [field]: event.value}});
  };
}

const HANDLERS = {
  open: (state) => (state.opened ? state : evolve(state, {opened: true})),
  goto: (state, event) => moveTo(state, event.step),
  next: (state) => (canAdvance(state).ok && nextStep(state) !== null
    ? moveTo(state, nextStep(state)) : state),
  back: (state) => {
    const at = BUILT_STEPS.indexOf(state.step);
    return at > 0 ? evolve(state, {step: BUILT_STEPS[at - 1]}) : state;
  },
  "edit-title": editTask("title", () => true),
  "edit-brief": editTask("brief", (state) => state.mode.starterId === null),
  "edit-hint": editTask("hint", (state) => state.mode.starterId === null),
  "edit-idea": editTask("idea", (state) => state.mode.starterId !== null),
  "material-add": addMaterial,
  "material-edit": editMaterial,
  "material-remove": removeMaterial,
  "material-mode": setMode,
  "cycle-choose": chooseCycle,
  "role-assign": assignRole,
  "instruction-edit": editInstruction,
  "instruction-own": ownInstruction,
  "instruction-like": likeInstruction,
  "include-instructions": (state, event) => (typeof event.value === "boolean"
    && state.materials.includeInstructions !== event.value
    ? evolve(state, {materials: {...state.materials, includeInstructions: event.value}})
    : state),
  "close-request": (state) => (closeNeedsWarning(state) && state.closing === null
    ? evolve(state, {closing: "confirm"}) : state),
  "close-cancel": (state) => (state.closing === null ? state : evolve(state, {closing: null})),
  reread,
  answered,
};

export const EVENTS = Object.freeze(Object.keys(HANDLERS));

//: One event in, the next state and the asks it made due out. An event the table does not
//: name, or one that changes nothing, hands back the very same state object and no asks.
export function stepWizard(state, event) {
  if (!event || !Object.hasOwn(HANDLERS, event.type)) return {state, asks: []};
  const changed = HANDLERS[event.type](state, event);
  if (changed === state) return {state, asks: []};
  const next = syncBinding(changed);
  const asks = wantedAsks(next).filter((ask) => !next.asked.includes(ask.id));
  if (asks.length === 0) return {state: next, asks};
  return {state: evolve(next, {asked: [...next.asked, ...asks.map((ask) => ask.id)]}), asks};
}

export function reduceWizard(state, event) {
  return stepWizard(state, event).state;
}
