"use strict";
// «Пропустить вперёд» from the card (spec 6.4.5, 4.4.8), as pure functions over the `launch` slice.
//
// One press is the spec's three steps, each idempotent by an id made from the card, and the third
// is two writes: the new run is queued with this card's authorization, put first, its holder is
// paused, and the holder's own resume is queued behind (so the queue pump starts the head, the new
// run, when the slot frees).
// What is done is never remembered: after every answer, and after a lost one, the queue, this
// run's automation and the holder's automation are read again, and the next step is the first one
// those reads say is not done. A step that stays undone after three writes stops the press, and so
// does a refusal; a changed queue is read and ordered once more, and a second change shows the
// queue to the owner instead.
import {authId, controlsOf, grantBody, slotOf} from "./desk-wizard-launch.js";

/** The four writes of a press, in order. */
export const SKIP_STEPS = Object.freeze(["enqueue", "order", "pause", "resume"]);
/** Why a press can stop in words of its own; any other refusal is said by its code. */
export const SKIP_STOPS = Object.freeze(["not_written", "read_failed", "queue_changed",
  "preview_stale", "authorization_refused", "queue_full", "queue_not_ready", "server_stopping",
  "contract_invalid"]);
/** What the card says of a step: done, not done, being read, or not known. */
export const SKIP_STATUS = Object.freeze(["done", "todo", "reading", "unknown"]);
const STEPS = SKIP_STEPS;
//: The fact of the reads that says each step is done.
const DONE = Object.freeze({enqueue: "enqueued", order: "first", pause: "paused",
  resume: "queuedHolder"});
const TRIES = 3;

const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

/** The id of the pause this card writes, and of the resume it queues: the card's, so a repeat is
 *  the same request. */
export const pauseId = (launch, nonce) => `pause-${nonce}-${launch.card}`;
export const resumeId = (launch, nonce) => `resume-${nonce}-${launch.card}`;

// -- the owner's moves -------------------------------------------------------------------

/** The press on «Пропустить вперёд»: the dialog opens, holding what the holder's read said. */
export function beginSkip(launch) {
  const offer = controlsOf(launch).skip;
  if (launch.skip !== null || !offer.shown || offer.blocked !== null) return launch;
  const grant = launch.reads.holder.payload, {authorization} = grant;
  const holder = {run_id: grant.run_id, authorization_id: authorization.authorization_id,
    authorization_digest: authorization.authorization_digest,
    expires_at: authorization.expires_at ?? grant.expires_at ?? null,
    control_id: grant.control?.control_id ?? null};
  const tries = Object.fromEntries(STEPS.map((name) => [name, 0]));
  return {...launch, skip: {phase: "confirm", holder, tries, orderChanged: 0, stop: null}};
}

/** «Отмена» on the dialog, or the acknowledgement of a press that stopped. */
export function cancelSkip(launch) {
  const shown = launch.skip !== null && ["confirm", "stopped"].includes(launch.skip.phase);
  return shown ? {...launch, skip: null} : launch;
}

/** The dialog's confirmation: everything is read afresh; the steps are written from the reads. */
export function confirmSkip(launch) {
  if (launch.skip?.phase !== "confirm") return launch;
  const reads = {...launch.reads, queue: null, automation: null, holder: null};
  return {...launch, phase: "skipping", note: null, refusal: null, repeats: 0, reads,
    seq: launch.seq + 1, presses: launch.presses + 1, skip: {...launch.skip, phase: "running"}};
}

// -- the reads and the progress they show -----------------------------------------------

function holderRead(launch, runId) {
  return {id: `read:launch:holder:${launch.seq}`, name: "launch_holder", door: "read",
    target: "automation", subject: runId, body: null};
}

//: Before the press, the holder is read once when the slot says its plan waits for a human: that
//: read decides whether the button is offered and carries the grant the dialog names.
function offerRead(launch) {
  const slot = slotOf(launch);
  const wanted = launch.phase === "review" && launch.reads.holder === null && slot !== null
    && slot.state === "busy" && slot.reason_code === "plan_waiting"
    && typeof slot.run_id === "string";
  return wanted ? [holderRead(launch, slot.run_id)] : [];
}

/**
 * What the reads say is done, or null while one is still out, or `{unreadable: true}` when the
 * queue or the holder could not be read. A run whose grant is this card's has already been started
 * by the pump: its queue entry is gone, and both of its steps are done.
 */
function progressOf(launch, ctx) {
  const {queue, holder, automation} = launch.reads;
  if (queue === null || holder === null || automation === null) return null;
  if (queue.status !== "ok" || holder.status !== "ok") return {unreadable: true};
  const rows = queue.payload.entries.filter(record), held = launch.skip.holder.run_id;
  const mine = rows.find((row) => row.run_id === ctx.runId);
  const grant = automation.status === "ok" ? automation.payload.authorization : null;
  const started = record(grant) && grant.authorization_id === authId(launch, ctx.nonce);
  const enqueued = started || mine?.preauthorization?.digest === launch.preview.preview_digest;
  return {unreadable: false, started, enqueued,
    first: started || (enqueued && rows[0].run_id === ctx.runId),
    paused: holder.payload.control?.control_id === pauseId(launch, ctx.nonce),
    queuedHolder: rows.some((row) => row.run_id === held && row.kind === "resume")};
}

const nextStep = (seen) => STEPS.find((name) => !seen[DONE[name]]) ?? null;

// -- the asks ----------------------------------------------------------------------------

//: An ask is handed out once, by its id: the id names the press and the try, so a second press on
//: the same card asks again, while the request's own ids (made from the card) stay the same.
function writeAsk(launch, ctx, step) {
  const id = authId(launch, ctx.nonce), {holder, tries} = launch.skip;
  const base = {id: `write:launch:skip:${step}:${id}:${launch.presses}:${tries[step]}`,
    name: `launch_skip_${step}`, door: "write", subject: null};
  if (step === "enqueue") {
    const start = grantBody(launch, ctx.nonce);
    return {...base, target: "queue", body: {run_id: ctx.runId, start}};
  }
  if (step === "order") {
    const others = launch.reads.queue.payload.entries.filter((row) => row.run_id !== ctx.runId);
    return {...base, target: "queueOrder", body: {
      expected_revision: launch.reads.queue.payload.revision,
      run_ids: [ctx.runId, ...others.map((row) => row.run_id)]}};
  }
  const grant = {authorization_id: holder.authorization_id,
    authorization_digest: holder.authorization_digest};
  if (step === "pause") {
    return {...base, target: "automationControl", subject: holder.run_id, body: {
      control_id: pauseId(launch, ctx.nonce), ...grant, action: "pause", actor: launch.actor,
      expected_control_id: holder.control_id}};
  }
  return {...base, target: "queue", body: {run_id: holder.run_id, resume: {
    control_id: resumeId(launch, ctx.nonce), ...grant,
    expected_control_id: pauseId(launch, ctx.nonce), actor: launch.actor}}};
}

/**
 * The asks the press calls for: the holder's read before it (to offer it) and during it, and the
 * one write the reads say is next. None while a read is out, or once the press has ended.
 */
export function skipAsks(launch, ctx) {
  if (ctx.phase !== "review") return [];
  const skip = launch.skip;
  if (skip === null) return offerRead(launch);
  if (skip.phase !== "running") return [];
  const reads = launch.reads.holder === null ? [holderRead(launch, skip.holder.run_id)] : [];
  const seen = progressOf(launch, ctx), step = seen === null || seen.unreadable ? null
    : nextStep(seen);
  return step === null ? reads : [...reads, writeAsk(launch, ctx, step)];
}

// -- the answers -------------------------------------------------------------------------

//: Read everything again: what was written is judged by the reads, whatever the answer said.
function reread(launch, skip) {
  const reads = {...launch.reads, queue: null, automation: null, holder: null};
  return {...launch, skip, reads, seq: launch.seq + 1};
}

//: The steps the last consistent reads say are done, or null when they cannot say: what the card
//: tells the owner about a press that stopped, before it reads anything again.
function standingOf(launch, ctx) {
  const seen = progressOf(launch, ctx);
  return seen === null || seen.unreadable ? null : STEPS.filter((name) => seen[DONE[name]]);
}

function stopSkip(launch, ctx, skip, why) {
  const reads = {...launch.reads, queue: null, automation: null, holder: null};
  const stopped = {...skip, phase: "stopped", stop: why, standing: standingOf(launch, ctx)};
  return {...launch, phase: "review", skip: stopped, reads, seq: launch.seq + 1,
    refreshWanted: why.code === "preview_stale" || launch.refreshWanted};
}

/**
 * After every answer and every read: when the reads show the press done, it ends (the run started
 * if the pump already did, else queued first); when the next step has been written three times and
 * is still undone, or a read failed, it stops.
 */
export function advanceSkip(launch, ctx) {
  if (launch.skip?.phase !== "running") return launch;
  const seen = progressOf(launch, ctx);
  if (seen === null) return launch;
  if (seen.unreadable) {
    return stopSkip(launch, ctx, launch.skip, {code: "read_failed", step: null});
  }
  const step = nextStep(seen);
  if (step === null) {
    const result = seen.started ? {kind: "started"} : {kind: "queued", position: 1};
    return {...launch, phase: result.kind, result, skip: {...launch.skip, phase: "done"}};
  }
  return launch.skip.tries[step] >= TRIES
    ? stopSkip(launch, ctx, launch.skip, {code: "not_written", step}) : launch;
}

/** Fold in the answer of one write of the press. */
export function landSkip(launch, ctx, ask, result) {
  const skip = launch.skip;
  if (skip === null || skip.phase !== "running" || launch.settled.includes(ask.id)) return launch;
  const step = ask.name.replace("launch_skip_", "");
  const marked = {...launch, settled: [...launch.settled, ask.id]};
  const counted = {...skip, tries: {...skip.tries, [step]: skip.tries[step] + 1}};
  if (result.status !== "refused") return advanceSkip(reread(marked, counted), ctx);
  const code = result.code ?? "refused";
  if (step === "order" && code === "queue_changed" && counted.orderChanged < 1) {
    return advanceSkip(reread(marked, {...counted, orderChanged: 1}), ctx);
  }
  return stopSkip(marked, ctx, counted, {code, step});
}

// -- what the card says about it ---------------------------------------------------------

//: Each step and whether it is done: all once the press has ended, what the last consistent reads
//: said once it stopped, what the reads in hand say while it runs; null while nothing says.
function stepRows(launch, ctx) {
  const skip = launch.skip;
  const seen = skip.phase === "running" ? progressOf(launch, ctx) : null;
  const known = seen === null || seen.unreadable ? null : STEPS.filter((name) => seen[DONE[name]]);
  const done = skip.phase === "done" ? [...STEPS] : skip.phase === "stopped" ? skip.standing
    : known;
  return STEPS.map((name) => ({step: name, done: done === null ? null : done.includes(name)}));
}

/**
 * The dialog and the press as the card draws them: the holder (its run, its task's title, when its
 * grant ends), how far the steps are (`done` is null while nothing says), why it stopped, and,
 * when the queue changed twice, the queue as it stands.
 */
export function skipFacts(launch, ctx, titleOf) {
  const skip = launch.skip;
  if (skip === null) return null;
  const rows = launch.reads.queue?.status === "ok" ? launch.reads.queue.payload.entries : [];
  const shown = skip.stop?.code === "queue_changed" ? rows.filter(record).map((row) => ({
    runId: row.run_id, title: row.title ?? null, position: row.position})) : [];
  return {phase: skip.phase, stop: skip.stop, queue: shown, steps: stepRows(launch, ctx),
    holder: {runId: skip.holder.run_id, title: titleOf(skip.holder.run_id),
      expiresAt: skip.holder.expires_at}};
}
