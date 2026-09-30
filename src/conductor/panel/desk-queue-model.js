"use strict";
// The task-queue read of the project (spec 4.4.6, `GET /command/queue`), judged against its
// shape. A body this module cannot vouch for is `null`, so the console draws no queue rather
// than one it cannot trust; a body it can is returned frozen and cut to the fields the desk
// reads, including the preauthorization digest needed to verify a confirmation.
//
// The judgement is the boundary's, as `studio-model.js` is for the runs list: it says only
// whether the answer is well formed and what the desk may read from it. The words a record
// earns, its times and its order on screen are `desk-pult.js`'s.
//
// Beside the judgement are the moves a person makes on a queue that was read: the bodies of the
// two writes that change its order (`order` takes the revision that was read and the FULL list of
// the visible entries, `withdraw` takes nothing), and the questions that say whether what was
// asked has come to stand. A write is never judged by its own answer: what stands is read off a
// queue, so a lost answer is settled by reading the queue again.
//
// It is values in and values out and imports nothing: the queue is read by the queue door
// and handed here, and no clock or page is reached.

const SLOT_STATES = Object.freeze(["free", "busy", "stuck", "unavailable"]);
const KINDS = Object.freeze(["start", "resume"]);
//: The reasons a record may give under each state (spec 4.4.6). A record may also give none.
const REASONS = Object.freeze({
  preauthorized: ["behind", "slot_busy", "slot_unavailable", "project_not_active"],
  confirmation_required: ["terms_changed", "grant_expired", "grant_changed", "preview_refused",
    "server_restarted"],
  blocked: ["run_unreadable", "receipt_conflict"],
});
//: A run or task id, the grammar the routes accept.
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
//: The 33rd record is refused by the server (`queue_full`), so no read holds more.
const MAX_ENTRIES = 32;

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const isText = (value) => typeof value === "string";
const isId = (value) => isText(value) && ID.test(value);
const orNull = (check) => (value) => value === null || check(value);

//: The slot: its state, the run that holds it and the policy's word for why. A free slot names
//: no run, and a slot somebody holds names one; an unavailable one may or may not.
function judgeSlot(slot) {
  if (!isObject(slot) || !SLOT_STATES.includes(slot.state)) return null;
  if (!orNull(isId)(slot.run_id) || !orNull(isText)(slot.reason_code)) return null;
  if (slot.state === "free" && slot.run_id !== null) return null;
  if ((slot.state === "busy" || slot.state === "stuck") && slot.run_id === null) return null;
  return Object.freeze({state: slot.state, run_id: slot.run_id, reason_code: slot.reason_code});
}

//: One record of the queue, at its place, or null.
function judgeEntry(entry, place) {
  if (!isObject(entry) || !Object.hasOwn(REASONS, entry.state)) return null;
  const fine = isId(entry.run_id) && isId(entry.task_id) && isText(entry.title)
    && entry.position === place && KINDS.includes(entry.kind)
    && isText(entry.enqueued_at) && isText(entry.enqueued_by)
    && (entry.reason_code === null || REASONS[entry.state].includes(entry.reason_code))
    && orNull(isText)(entry.state_since);
  if (!fine) return null;
  const pre = entry.preauthorization;
  if (pre !== null && (!isObject(pre) || !isText(pre.authorized_by)
      || !isText(pre.preauthorized_at) || !DIGEST.test(pre.digest))) return null;
  return Object.freeze({run_id: entry.run_id, task_id: entry.task_id, title: entry.title,
    position: entry.position, kind: entry.kind, enqueued_at: entry.enqueued_at,
    enqueued_by: entry.enqueued_by, state: entry.state, reason_code: entry.reason_code,
    state_since: entry.state_since,
    preauthorization: pre === null ? null : Object.freeze({authorized_by: pre.authorized_by,
      preauthorized_at: pre.preauthorized_at, digest: pre.digest})});
}

//: `GET /command/queue` as the desk may read it, or null. Positions are 1..n in order and a
//: run stands in the queue once.
export function projectQueue(payload) {
  if (!isObject(payload) || payload.schema_version !== 1) return null;
  if (!Number.isInteger(payload.revision) || payload.revision < 0) return null;
  const slot = judgeSlot(payload.slot);
  if (slot === null || !Array.isArray(payload.entries) || payload.entries.length > MAX_ENTRIES) {
    return null;
  }
  const entries = payload.entries.map((entry, index) => judgeEntry(entry, index + 1));
  if (entries.includes(null)) return null;
  if (new Set(entries.map((entry) => entry.run_id)).size !== entries.length) return null;
  return Object.freeze({revision: payload.revision, slot, entries: Object.freeze(entries)});
}

// -- the moves of a person on a queue that was read ---------------------------------------------

//: The run ids of the visible entries after one of them stepped one place: `step` is -1 (up, toward
//: the head) or 1 (down). An entry at the end it would step past, an entry the queue does not hold
//: and any other step lead nowhere: null, and the caller writes nothing.
export function movedOrder(queue, runId, step) {
  if (queue === null || (step !== -1 && step !== 1)) return null;
  const ids = queue.entries.map((entry) => entry.run_id);
  const from = ids.indexOf(runId);
  const to = from + step;
  if (from < 0 || to < 0 || to >= ids.length) return null;
  [ids[from], ids[to]] = [ids[to], ids[from]];
  return Object.freeze(ids);
}

//: The body of `POST /command/queue/order`: the revision that was read and every visible entry in
//: its new place, or null when the step leads nowhere.
export function orderBody(queue, runId, step) {
  const ids = movedOrder(queue, runId, step);
  return ids === null ? null
    : Object.freeze({expected_revision: queue.revision, run_ids: ids});
}

//: The body of `POST /command/queue/<run_id>/withdraw`: nothing. A fresh object each time.
export function withdrawBody() {
  return Object.freeze({});
}

//: Whether the queue holds exactly these run ids, in this order.
export function holdsOrder(queue, runIds) {
  if (queue === null || queue.entries.length !== runIds.length) return false;
  return queue.entries.every((entry, place) => entry.run_id === runIds[place]);
}

//: Whether the queue holds an entry of this run.
export function holdsRun(queue, runId) {
  return queue !== null && queue.entries.some((entry) => entry.run_id === runId);
}

// -- freeing the slot: the holder, the control that stops it, the offer --------------------------

//: What the desk writes to a holder: a pause (it can be continued while its grant lasts) and a
//: revoke (it cannot be undone). A resume is the Studio's and the queue's, never this door's.
const CONTROLS = Object.freeze(["pause", "revoke"]);

//: The holder of the slot as `GET /command/runs/<run_id>/automation` tells it, cut to what a
//: control needs: the state and its reason, the grant (null for a run that has none), the id of
//: the last control written to it and the instant its window ends (null for no grant). A read of
//: another run, or one that does not say these, is null: nothing is written to a grant the desk
//: could not read.
export function projectHolder(read, runId) {
  if (!isObject(read) || read.run_id !== runId || !isText(read.state)
      || !isText(read.reason_code) || !orNull(isText)(read.expires_at)) return null;
  const {authorization: grant, control} = read;
  const grantOk = grant === null || (isObject(grant) && isId(grant.authorization_id)
    && isText(grant.authorization_digest) && DIGEST.test(grant.authorization_digest));
  const controlOk = control === null || (isObject(control) && isId(control.control_id));
  if (!grantOk || !controlOk) return null;
  return Object.freeze({run_id: runId, state: read.state, reason_code: read.reason_code,
    grant: grant === null ? null : Object.freeze({authorization_id: grant.authorization_id,
      authorization_digest: grant.authorization_digest}),
    last_control_id: control === null ? null : control.control_id,
    expires_at: read.expires_at});
}

//: The body of `POST /command/runs/<run_id>/automation/control` for a pause or a revoke: the grant
//: the person was looking at, the control they saw last (the server refuses a body that has been
//: overtaken), the action and their name. Null without a grant, an action of the two, a name and
//: an id in the grammar.
export function controlBody(holder, {action, actor, controlId}) {
  if (holder === null || holder.grant === null || !CONTROLS.includes(action)) return null;
  if (!isText(actor) || actor === "" || !isId(controlId)) return null;
  return Object.freeze({control_id: controlId, authorization_id: holder.grant.authorization_id,
    authorization_digest: holder.grant.authorization_digest, action, actor,
    expected_control_id: holder.last_control_id});
}

//: Whether the holder read says this control is the last one written to its grant: a write that
//: was not answered is settled by asking, never by assuming.
export function controlRecorded(holder, controlId) {
  return holder !== null && isText(controlId) && holder.last_control_id === controlId;
}

//: What the console offers for a slot somebody holds and cannot go on with (`stuck`): the run that
//: holds it, the reason, and whether a person is named to write in. Nothing for a slot in any other
//: state, for a queue that was not read, and in a project opened for viewing, which has no slot.
export function releaseOffer(queue, {mode, actor}) {
  if (queue === null || mode === "view" || queue.slot.state !== "stuck") return null;
  return Object.freeze({run_id: queue.slot.run_id, reason: queue.slot.reason_code,
    named: actor !== null});
}

// -- skipping ahead: a holder that waits for a person steps aside for the queue -------------------

//: What the console offers for a holder that waits for a person (`busy` at its gate) while the
//: queue is not empty: the run that holds the slot, and whether a person is named to write in.
//: Nothing in a project opened for viewing (it has no slot), for any other slot, or for a queue
//: that was not read.
export function skipOffer(queue, {mode, actor}) {
  const waits = queue !== null && queue.slot.state === "busy"
    && queue.slot.reason_code === "plan_waiting";
  if (!waits || mode === "view" || queue.entries.length === 0) return null;
  return Object.freeze({run_id: queue.slot.run_id, named: actor !== null});
}

//: The body of `POST /command/queue` that puts a paused holder back in the queue to continue: the
//: run, the grant, the pause it follows (its `expected_control_id`, which the server checks
//: against the grant's last control) and the person. Null without a grant, a person, and ids in
//: the grammar -- a continuation with no pause to follow is not a continuation.
export function resumeBody(holder, {actor, controlId, expectedControlId}) {
  if (holder === null || holder.grant === null || !isText(actor) || actor === "") return null;
  if (!isId(controlId) || !isId(expectedControlId)) return null;
  return Object.freeze({run_id: holder.run_id, resume: Object.freeze({control_id: controlId,
    authorization_id: holder.grant.authorization_id,
    authorization_digest: holder.grant.authorization_digest,
    expected_control_id: expectedControlId, actor})});
}

//: What a skip has done so far, read and never remembered: the pause is done when the holder's
//: last control is the pause this press wrote (`pauseId`), and the continuation is done when the
//: queue holds a RESUME entry of the holder (a start entry is not one).
export function skipProgress({holder, queue, runId, pauseId}) {
  return Object.freeze({paused: controlRecorded(holder, pauseId),
    queued: queue !== null && queue.entries.some((entry) => entry.run_id === runId
      && entry.kind === "resume")});
}

//: The first step a skip has not done: `pause`, then `queue`, then none.
export function skipStep({paused, queued}) {
  if (!paused) return "pause";
  return queued ? null : "queue";
}

//: The server's reviewed terms are carried through unchanged. The desk reads their numbers for
//: display and does not reconstruct them from an earlier grant or a client's budget guess.
export function confirmPreview(read) {
  if (!isObject(read) || !isObject(read.terms) || !DIGEST.test(read.preview_digest)) return null;
  const {max_actions: actions, max_total_task_seconds: seconds,
    duration_seconds: duration} = read.terms;
  if (![actions, seconds, duration].every((n) => Number.isInteger(n) && n > 0)) return null;
  return Object.freeze({terms: read.terms, preview_digest: read.preview_digest,
    max_actions: actions, max_total_task_seconds: seconds, duration_seconds: duration});
}

export function confirmBody(entry, preview, holder, {actor, authorizationId}) {
  if (entry === null || !isText(actor) || actor === "" || !isId(authorizationId)) return null;
  if (entry.kind === "resume" && entry.reason_code !== "grant_expired") {
    return resumeBody(holder, {actor, controlId: authorizationId,
      expectedControlId: holder?.last_control_id});
  }
  if (preview === null) return null;
  return Object.freeze({run_id: entry.run_id, start: Object.freeze({
    authorization_id: authorizationId, preview_digest: preview.preview_digest,
    terms: preview.terms, authorized_by: actor,
    supersedes: holder?.grant?.authorization_id ?? null})});
}
