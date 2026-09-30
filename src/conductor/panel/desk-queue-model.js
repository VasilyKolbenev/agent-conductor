"use strict";
// The task-queue read of the project (spec 4.4.6, `GET /command/queue`), judged against its
// shape. A body this module cannot vouch for is `null`, so the console draws no queue rather
// than one it cannot trust; a body it can is returned frozen and cut to the fields the desk
// reads -- the preauthorization's digest and every field a later server may add stay out.
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
  return Object.freeze({run_id: entry.run_id, task_id: entry.task_id, title: entry.title,
    position: entry.position, kind: entry.kind, enqueued_at: entry.enqueued_at,
    enqueued_by: entry.enqueued_by, state: entry.state, reason_code: entry.reason_code,
    state_since: entry.state_since});
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
