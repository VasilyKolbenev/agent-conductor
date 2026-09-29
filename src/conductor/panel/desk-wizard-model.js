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
// State shape (all frozen):
//   step, mode {starterId, view}, task {taskId, title, brief, hint, idea, written},
//   reads {name: {status: "ok" | "failed", code, payload}}, asked [ask id], opened.
import {taskTitle, TASK_TITLE_LIMIT, isTaskId} from "./studio-tasks-model.js";

export const STEPS = Object.freeze(["task", "materials", "cycle", "roles", "prepare", "run"]);
export const BUILT_STEPS = Object.freeze(["task", "materials", "cycle", "roles"]);
//: The one starter the hash may name (spec 4.5.2), and the two cycles the wizard offers as
//: cards. The set of cards is the desk's own, never the order `starters()` happens to give.
export const HASH_STARTERS = Object.freeze(["desk-starter-docs"]);
export const WIZARD_STARTERS = Object.freeze(["desk-standard", "desk-short"]);
export const LIMITS = Object.freeze({materials: 12, documentBytes: 49152, argvChars: 32767,
  title: TASK_TITLE_LIMIT});

//: What the documents this wizard composes say, in the language of the interface. A document
//: is data for agents, not interface text, so its headings live here and not in the catalogue.
const WORDS = Object.freeze({
  ru: Object.freeze({todo: "Что нужно сделать", idea: "Идея проекта",
    hint: "Как понять, что готово (подсказка)", none: "—"}),
  en: Object.freeze({todo: "What needs to be done", idea: "Project idea",
    hint: "How to tell it is done (hint)", none: "—"}),
});
//: The reads a wizard asks for once it opens: every later step draws on one of them.
const OPENING_READS = Object.freeze([["git", "git"], ["workflows", "workflows"],
  ["runs", "runs"], ["cycle_read", "projectCycle"], ["tasks", "tasks"], ["quotas", "quotas"]]);
const READ_NAMES = Object.freeze(OPENING_READS.map(([name]) => name));
const encoder = new TextEncoder();

export function utf8Bytes(text) {
  return encoder.encode(text).length;
}

function frozen(value) {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const item of Object.values(value)) frozen(item);
  return Object.freeze(value);
}

function evolve(state, patch) {
  return frozen({...state, ...patch});
}

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
  return frozen({step: "task", opened: false, asked: [],
    mode: {starterId, view: opening.viewMode === true},
    task: {taskId: opening.newTaskId, title, brief: "", hint: "", idea: "", written},
    reads: {}});
}

// -- step 1: the task ------------------------------------------------------------------

export function taskFields(state) {
  return Object.freeze(state.mode.starterId === null
    ? ["title", "brief", "hint"] : ["title", "idea"]);
}

//: The `artifact-brief` document (spec 6.2.3, n. 1), byte for byte: the same template the
//: server-side readers expect, a starter's idea under its own heading, a dash for no hint.
export function briefDocument(state, lang) {
  const words = WORDS[lang];
  if (!words) throw new Error("unknown document language");
  const starter = state.mode.starterId !== null;
  const text = starter ? state.task.idea : state.task.brief;
  const hint = starter || state.task.hint.trim() === "" ? words.none : state.task.hint;
  return `# ${state.task.title}\n\n## ${starter ? words.idea : words.todo}\n${text}\n\n`
    + `## ${words.hint}\n${hint}\n`;
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

// -- the steps and their gates ---------------------------------------------------------

//: Why a step is not complete yet, as a closed code (null when it is). One entry per built
//: step; a step with no entry has nothing to refuse.
const GATES = {task: taskGate};
const PUBLISHERS = {task: taskPublication};

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

//: What each step would publish once the chain of later slices sends it. Only a complete
//: step publishes anything, and no descriptor carries an id the chain has yet to make.
export function publications(state, lang) {
  return Object.freeze(BUILT_STEPS.filter((step) => gateOf(state, step) === null
    && Object.hasOwn(PUBLISHERS, step)).map((step) => frozen(PUBLISHERS[step](state, lang))));
}

// -- asks --------------------------------------------------------------------------------

function readAsk(name, target) {
  return {id: `read:${name}`, name, door: "read", target, subject: null, body: null};
}

//: Every ask the state calls for, whether or not it went out already; `stepWizard` hands out
//: only those whose id is not yet in `asked`.
export function wantedAsks(state) {
  return state.opened ? OPENING_READS.map(([name, target]) => readAsk(name, target)) : [];
}

function readOf(result) {
  return result.status === "accepted"
    ? {status: "ok", code: null, payload: structuredClone(result.payload ?? null)}
    : {status: "failed", code: result.code ?? result.status, payload: null};
}

function answerRead(name) {
  return (state, _ask, result) => evolve(state, {reads: {...state.reads, [name]: readOf(result)}});
}

const ANSWERS = Object.fromEntries(READ_NAMES.map((name) => [name, answerRead(name)]));

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
  if (!READ_NAMES.includes(event.name)) return state;
  const {[event.name]: _dropped, ...reads} = state.reads;
  return evolve(state, {reads, asked: state.asked.filter((id) => id !== `read:${event.name}`)});
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
  reread,
  answered,
};

export const EVENTS = Object.freeze(Object.keys(HANDLERS));

//: One event in, the next state and the asks it made due out. An event the table does not
//: name, or one that changes nothing, hands back the very same state object and no asks.
export function stepWizard(state, event) {
  if (!event || !Object.hasOwn(HANDLERS, event.type)) return {state, asks: []};
  const next = HANDLERS[event.type](state, event);
  if (next === state) return {state, asks: []};
  const asks = wantedAsks(next).filter((ask) => !next.asked.includes(ask.id));
  if (asks.length === 0) return {state: next, asks};
  return {state: evolve(next, {asked: [...next.asked, ...asks.map((ask) => ask.id)]}), asks};
}

export function reduceWizard(state, event) {
  return stepWizard(state, event).state;
}
