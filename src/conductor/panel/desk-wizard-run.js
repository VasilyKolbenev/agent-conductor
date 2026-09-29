"use strict";
// The `run` and `launch` slices as the wizard's model sees them: the chain of step 5 applied to
// the wizard's state, the same chain after a reload, and the terms card of step 6.
//
// `desk-wizard-prep.js` and `desk-wizard-launch.js` know nothing of the wizard's state and
// `desk-wizard-input.js` reads it once; this module is the seam the model calls: the gate of the
// step, the asks the slices call for, an answer folded into the state (with what a reloaded page
// learns about its task), the owner's moves as functions of the state, and what a reloaded page
// and the card say. The judgement of the four filling steps is the model's (`gateOf`), so it is
// handed in; the model is not imported.
import {FILL_STEPS, LIMITS, evolve, isLanguage, utf8Bytes} from "./desk-wizard-base.js";
import {resumeInput, runInput} from "./desk-wizard-input.js";
import {taskTitleOfRun} from "./desk-wizard-cycle.js";
import {adoptPreview, beginLaunch, cardFacts, controlsOf, editActor, initialLaunch, isActor,
  isViewing, landLaunch, launchAsks, refreshLaunch, remaining, repeatsSpent, rereadLaunch,
  seenLaunch, tickLaunch, toggleInfo, unreadUnknown} from "./desk-wizard-launch.js";
import {advanceSkip, beginSkip, cancelSkip, confirmSkip, landSkip, skipAsks, skipFacts}
  from "./desk-wizard-skip.js";
import {heldFlow} from "./desk-wizard-team.js";
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
  return evolve(state, {step: "task", run: initialRun(), launch: initialLaunch(state.launch.actor),
    task: {...state.task, title: "", written: false}});
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
  //: The preview of the chain is the first card of step 6 (a later one replaces or keeps it).
  const carded = ask.name === "preview" && run.phase === "review"
    ? evolve(next, {launch: adoptPreview(state.launch, run.preview, run.runId)}) : next;
  if (state.task.written) return carded;
  if (run.resume === null) {
    //: The title is fixed once the task is written: the same id with another title would clash.
    return run.done.some((key) => key.startsWith("task:"))
      ? evolve(carded, {task: {...carded.task, written: true}}) : carded;
  }
  if (run.prep === null) return carded;
  return evolve(carded, {task: {...carded.task, title: run.prep.task.title, written: true}});
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
  return Object.freeze({phase: run.phase, pressed: run.pressed, links, gate,
    resume: resumeView(state), refusal: run.refusal, readFailed: run.readFailed,
    prepared: preparedBy(run, links), following: followingRunNumber(run)});
}

//: A run is prepared when its preview is made and every link of the chain stands as written.
function preparedBy(run, links) {
  return run.phase === "review"
    && links.every((row) => row.status === "done" || row.status === "skipped");
}

/** Whether the run is prepared: the chain done, the preview made, nothing edited since. */
export function isPrepared(state) {
  return preparedBy(state.run, chainLinks(state));
}

/**
 * When the wizard has nothing more to do: a reloaded page finds its run past preparation, or the
 * owner started or queued it. The run for the desk to open, and where it stands. A queue entry in
 * a project that is only viewed is not an exit: the closing line and the way to the flag are on
 * the wizard's own screen, and the owner leaves from there.
 */
export function wizardExit(state) {
  if (state.launch.result !== null) {
    const viewed = state.launch.result.kind === "queued" && isViewing(state.launch);
    return viewed ? null : {runId: state.run.runId, stage: state.launch.result.kind};
  }
  const situation = resumeSituation(state.run);
  return situation !== null && situation.kind === "exit"
    ? {runId: situation.runId, stage: situation.stage} : null;
}

// -- step 6: the card --------------------------------------------------------------------

//: What a card ask or answer needs to know about the run around it.
const launchCtx = (state) => ({runId: state.run.runId, nonce: state.nonce,
  phase: state.run.phase});

function withLaunch(state, launch) {
  return launch === state.launch ? state : evolve(state, {launch});
}

/** The reads, the write and the repeated preview the card calls for now, and the press's own. */
export function launchWanted(state) {
  const ctx = launchCtx(state);
  return [...launchAsks(state.launch, ctx), ...skipAsks(state.launch, ctx)];
}

/** Fold one answer of the card in (a write of «Пропустить вперёд» is folded by its own step). */
export function landCard(state, ask, result) {
  const ctx = launchCtx(state);
  const launch = ask.name.startsWith("launch_skip_")
    ? landSkip(state.launch, ctx, ask, result)
    : advanceSkip(landLaunch(state.launch, ctx, ask, result), ctx);
  return withLaunch(state, launch);
}

export const cardTick = (state, event) => withLaunch(state,
  tickLaunch(state.launch, event.now));
export const cardActor = (state, event) => withLaunch(state,
  editActor(state.launch, event.value));
export const cardStart = (state) => withLaunch(state, beginLaunch(state.launch, "start"));
export const cardEnqueue = (state) => withLaunch(state, beginLaunch(state.launch, "enqueue"));
export const cardRefresh = (state) => withLaunch(state, refreshLaunch(state.launch));
export const cardReread = (state) => withLaunch(state, rereadLaunch(state.launch));
export const cardSeen = (state) => withLaunch(state, seenLaunch(state.launch));
export const cardInfo = (state, event) => withLaunch(state,
  toggleInfo(state.launch, event.name));
export const cardSkip = (state) => withLaunch(state, beginSkip(state.launch));
export const cardSkipConfirm = (state) => withLaunch(state, confirmSkip(state.launch));
export const cardSkipCancel = (state) => withLaunch(state, cancelSkip(state.launch));

//: The role of each step of the cycle the run follows, when this window holds it.
function rolesByStep(state) {
  const steps = heldFlow(state)?.flow.steps ?? [];
  return Object.fromEntries(steps.filter((step) => step.type === "agent")
    .map((step) => [step.step_id, step.role_id]));
}

//: The line about where the agents get their code, from the seed the chain wrote or the read holds.
function seedLine(run) {
  const seed = run.seed ?? run.prep?.seed ?? null;
  if (seed === null) return null;
  if (seed.state === "requested") return {kind: "request"};
  if (typeof seed.base_commit !== "string") return null;
  const ref = typeof seed.base_ref === "string" ? seed.base_ref.replace(/^refs\/heads\//, "")
    : null;
  return {kind: "copy", ref, commit: seed.base_commit.slice(0, 7)};
}

//: The note of the last answer; a taken slot also carries the title of the holder's task when the
//: lists the wizard read say it, and null when they do not.
function noteOf(state) {
  const {note} = state.launch;
  if (note === null || note.kind !== "slot_busy") return note;
  return {...note, holderTitle: note.holder === null ? null
    : taskTitleOfRun(state.reads, note.holder)};
}

/**
 * What step 6 draws: the card (every number the server's), the controls the slot allows, the
 * countdown, and what the last answer said. `lostUnread` is true while a lost answer waits on a
 * read that failed: nothing is known of the write, and reading again is what the owner may do.
 */
export function launchFacts(state) {
  const {launch} = state, seconds = remaining(launch);
  return Object.freeze({phase: launch.phase, error: launch.error, note: noteOf(state),
    lostUnread: unreadUnknown(launch),
    refusal: launch.refusal, result: launch.result, viewing: isViewing(launch),
    runId: state.run.runId, infos: launch.infos,
    skip: skipFacts(launch, launchCtx(state), (runId) => taskTitleOfRun(state.reads, runId)),
    actor: launch.actor,
    actorValid: isActor(launch.actor), changed: launch.changed, seen: launch.seen,
    repeatsSpent: repeatsSpent(launch), controls: controlsOf(launch),
    countdown: seconds === null ? null : {seconds, until: launch.preview.valid_until},
    card: cardFacts(launch, {roles: rolesByStep(state), seed: seedLine(state.run)})});
}

/** The wizard's keys of the desk's hash as they stand now, or null when it wants none. */
export function wizardHash(state) {
  return hashNow(state.run, chainInput(state));
}

/** A reloaded page opens on the preparation step with the task the hash names and its read due. */
export function resumeOpening(opening) {
  return openResume(initialRun(), opening.resume);
}
