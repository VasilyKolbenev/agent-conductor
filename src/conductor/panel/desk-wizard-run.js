"use strict";
// The `run` slice as the wizard's model sees it: the chain of step 5 applied to the wizard's
// state, and the same chain after a reload.
//
// `desk-wizard-prep.js` knows nothing of the wizard's state and `desk-wizard-input.js` reads it
// once; this module is the seam the model calls: the gate of the step, the asks the slice calls
// for, an answer folded into the state (with what a reloaded page learns about its task), the
// owner's moves as functions of the state, and what a reloaded page says. The judgement of the
// four filling steps is the model's (`gateOf`), so it is handed in; the model is not imported.
import {FILL_STEPS, LIMITS, evolve, isLanguage, utf8Bytes} from "./desk-wizard-base.js";
import {resumeInput, runInput} from "./desk-wizard-input.js";
import {adoptRun, bumpRun, chainAsks, followingRunNumber, hashNow, initialRun, landChain,
  linkStates, openResume, resumeAsks, resumeFields, resumeSituation, retryChain, startChain}
  from "./desk-wizard-prep.js";

//: The plain facts the chain is built from, in the language the owner pressed the button in.
export function chainInput(state, lang = state.run.lang) {
  return state.run.resume === null ? runInput(state, lang) : resumeInput(state, lang);
}

function withRun(state, run) {
  return run === state.run ? state : evolve(state, {run});
}

const stop = (reason) => Object.freeze({ok: false, reason, step: "prepare"});
const go = Object.freeze({ok: true, reason: null, step: null});

//: Whether the chain may begin: the four steps are complete, and a cycle whose steps work in a
//: folder has a repository to seed it from (the ways out for a project without one are later
//: slices, so the reason is said, not skipped).
export function prepareGate(state, gateOf) {
  for (const step of FILL_STEPS) {
    const reason = gateOf(state, step);
    if (reason !== null) return Object.freeze({ok: false, reason, step});
  }
  const input = chainInput(state);
  return input.dispatch && input.seed.blocked !== null ? stop(input.seed.blocked) : go;
}

/** One row per link of the chain, with where it stands. */
export function chainLinks(state) {
  return Object.freeze(linkStates(state.run, chainInput(state)));
}

/** The ask the chain, or the read of a reloaded page, calls for now. */
export function runWanted(state) {
  const {run} = state;
  return run.pressed ? chainAsks(run, chainInput(state)) : resumeAsks(run, chainInput(state));
}

//: A wizard that has learned the server has no such task starts over at step 1 with nothing
//: written; its reads (git, cycles, roster) are still true.
function startOver(state) {
  return evolve(state, {step: "task", run: initialRun(), task: {...state.task, title: "",
    written: false}});
}

/**
 * Fold one answer of the chain in. A reloaded page takes the task's title from its first read
 * (a record, not a default) and starts over when the server has no such task.
 */
export function landRun(state, ask, result) {
  const run = landChain(state.run, chainInput(state), ask, result);
  if (run === state.run) return state;
  const next = evolve(state, {run});
  if (run.resume !== null && run.resume.lost) return startOver(next);
  if (state.task.written) return next;
  if (run.resume === null) {
    //: The title is fixed once the task is written: the same id with another title would clash.
    return run.done.some((key) => key.startsWith("task:"))
      ? evolve(next, {task: {...next.task, written: true}}) : next;
  }
  if (run.prep === null) return next;
  return evolve(next, {task: {...next.task, title: run.prep.task.title, written: true}});
}

// -- the owner's moves -------------------------------------------------------------------

/** «Подготовить запуск» / «Продолжить подготовку». */
export function runStart(state, event, gateOf) {
  if (!isLanguage(event.lang)) return state;
  const gate = state.run.resume === null ? prepareGate(state, gateOf) : resumeGate(state, gateOf);
  if (!gate.ok) return state;
  return withRun(state, startChain(state.run, chainInput(state, event.lang), event.lang));
}

export const runRetry = (state) => withRun(state, retryChain(state.run));
export const runAdopt = (state) => withRun(state, adoptRun(state.run));
export const runBump = (state) => withRun(state, bumpRun(state.run));

/** A reloaded page whose task stands with nothing after it: fill it in again, its title kept. */
export function resumeRestart(state) {
  return resumeSituation(state.run)?.kind === "no_run"
    ? evolve(state, {step: "task", run: initialRun()}) : state;
}

// -- what a reloaded page says -----------------------------------------------------------

function valueOf(state, name) {
  return name === "brief" || name === "hint" || name === "idea" ? state.task[name]
    : state.run.resume.texts[name] ?? "";
}

/**
 * What stands after a reload (`desk-wizard-prep.js` names the kinds); when documents are missing,
 * each field to type again with its value, and whether it is required.
 */
export function resumeView(state) {
  const situation = resumeSituation(state.run);
  if (situation === null || situation.kind !== "documents") return situation;
  const starter = state.mode.starterId !== null;
  return {...situation, fields: resumeFields(situation.missing, starter).map((field) => ({
    ...field, value: valueOf(state, field.name)}))};
}

/** Whether a reloaded page may go on: the fields the read asks for are filled in. */
export function resumeGate(state, gateOf) {
  const view = resumeView(state);
  if (view === null || !["documents", "preview"].includes(view.kind)) return stop("resume_pending");
  const fields = view.fields ?? [];
  if (fields.some((field) => field.kept === "task" && field.required)) {
    const reason = gateOf(state, "task");
    if (reason !== null) return stop(reason);
  }
  for (const field of fields.filter((one) => one.kept === "resume")) {
    const text = field.value;
    if (field.required && text.trim() === "") return stop("instruction_empty");
    if (utf8Bytes(text) > LIMITS.documentBytes) {
      return stop(field.name === "materials" ? "materials_over_bytes" : "instruction_too_large");
    }
  }
  return go;
}

/** Text typed again for a missing document that is not the task's (an instruction, the materials). */
export function resumeEdit(state, event) {
  const view = state.run.resume === null ? null : resumeView(state);
  const field = view?.fields?.find((one) => one.name === event.name && one.kept === "resume");
  if (!field || typeof event.value !== "string" || field.value === event.value) return state;
  const texts = {...state.run.resume.texts, [event.name]: event.value};
  return withRun(state, {...state.run, resume: {...state.run.resume, texts}});
}

/**
 * What step 5 draws: where each link stands, what may be pressed (`gate`), what a reloaded page
 * found (`resume`), a refusal or a failed read, the two run numbers a `record_conflict` offers,
 * and whether the run is prepared (the preview made and nothing written since).
 */
export function prepareFacts(state, gateOf) {
  const {run} = state, links = chainLinks(state);
  const gate = run.resume === null ? prepareGate(state, gateOf) : resumeGate(state, gateOf);
  const settled = links.every((row) => row.status === "done" || row.status === "skipped");
  return Object.freeze({phase: run.phase, pressed: run.pressed, links, gate,
    resume: resumeView(state), refusal: run.refusal, readFailed: run.readFailed,
    prepared: run.phase === "review" && settled, following: followingRunNumber(run)});
}

/** When a reloaded page finds its run past preparation: the run to open, and where it stands. */
export function wizardExit(state) {
  const situation = resumeSituation(state.run);
  return situation !== null && situation.kind === "exit"
    ? {runId: situation.runId, stage: situation.stage} : null;
}

/** The wizard's keys of the desk's hash as they stand now, or null when it wants none. */
export function wizardHash(state) {
  return hashNow(state.run, chainInput(state));
}

/** A reloaded page opens on the preparation step with the task the hash names and its read due. */
export function resumeOpening(opening) {
  return openResume(initialRun(), opening.resume);
}
