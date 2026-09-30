"use strict";
// The continue-after flag as the desk judges and uses it (spec 4.3.4 and 5.8): the record a
// read of it answers, the runs a person may mark, and the body a save sends. Values in and
// values out: this module imports nothing and reaches neither the page, the wire nor the clock.
//
// The record is the one the flag file holds and its two routes answer, exactly nine keys. A body
// with another key, a missing one, a value of another type or a contradiction (a standing flag
// with no owner, a consumed flag still enabled) is not a record this module can vouch for, and
// the desk then draws no block rather than one that might say what the server did not.
//
// What the desk cannot know is left unsaid here. That a flag was handed to a transition and its
// project died before consuming it, and that a run changed after the flag so the flag did not
// apply, are facts of the hub and of the queue pump; the flag file carries neither, so no
// function below infers them.

const RECORD_KEYS = Object.freeze(["schema_version", "flag_id", "revision", "enabled", "actor",
  "set_at", "resume_runs", "start_task_queue", "consumed"]);
const RUN_KEYS = Object.freeze(["run_id", "authorization_id", "authorization_digest",
  "last_control_id"]);
const CONSUMED_KEYS = Object.freeze(["at", "transition_id", "activation_nonce"]);
//: The automation read's reasons for which a run that waits for a person can still be continued
//: by the flag, besides a pause (spec 5.8).
const RESUMABLE_REASONS = Object.freeze(["explicit_resume_required", "project_not_active"]);

const isText = (value) => typeof value === "string" && value !== "";
const textOrNull = (value) => value === null || isText(value);
const isPlain = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const hasKeys = (value, keys) => isPlain(value)
  && Object.keys(value).sort().join(",") === [...keys].sort().join(",");

function goodRun(row) {
  return hasKeys(row, RUN_KEYS) && isText(row.run_id) && isText(row.authorization_id)
    && isText(row.authorization_digest) && textOrNull(row.last_control_id);
}

function goodConsumed(value) {
  return value === null || (hasKeys(value, CONSUMED_KEYS) && CONSUMED_KEYS.every(
    (key) => isText(value[key])));
}

function coherent(record) {
  const owned = isText(record.flag_id) && isText(record.actor) && isText(record.set_at);
  return (!record.enabled || owned) && (record.consumed === null || !record.enabled);
}

//: A read of the flag judged against the record of spec 4.3.4: a frozen copy of it, or `null`.
export function projectFlag(payload) {
  if (!hasKeys(payload, RECORD_KEYS) || payload.schema_version !== 2) return null;
  const sound = Number.isInteger(payload.revision) && payload.revision >= 0
    && typeof payload.enabled === "boolean" && typeof payload.start_task_queue === "boolean"
    && textOrNull(payload.flag_id) && textOrNull(payload.actor) && textOrNull(payload.set_at)
    && Array.isArray(payload.resume_runs) && payload.resume_runs.every(goodRun)
    && goodConsumed(payload.consumed) && coherent(payload);
  if (!sound) return null;
  return Object.freeze({...payload,
    resume_runs: Object.freeze(payload.resume_runs.map((row) => Object.freeze({...row}))),
    consumed: payload.consumed === null ? null : Object.freeze({...payload.consumed})});
}

//: Which line of spec 5.8 the record reads as: a flag that stands (`set_at` and who set it), one
//: that was consumed by an activation (`consumed.at` and who set it), and none -- no file, or one
//: the owner took off, which the block says by its switch being off and nothing more.
export function flagLine(flag) {
  if (flag.consumed !== null) return Object.freeze({kind: "consumed", at: flag.consumed.at,
    actor: flag.actor});
  if (flag.enabled) return Object.freeze({kind: "standing", at: flag.set_at, actor: flag.actor});
  return Object.freeze({kind: "none", at: null, actor: null});
}

//: Whether a run's automation read says its grant can be continued: paused, or waiting for an
//: explicit resume because the project started again or is not active. An expired grant is told
//: apart, not folded into "no": it has no mark and says why (spec 5.8).
function continuable(answer) {
  if (answer.state === "expired") return "expired";
  const waits = answer.state === "restart_required"
    && RESUMABLE_REASONS.includes(answer.reason_code);
  return answer.state === "paused" || waits ? "resumable" : null;
}

//: The runs the block may list, from what the desk already holds: the automation read of the
//: newest run of each readable task. Each row is `{run_id, task_id, title, created_at, expired}`;
//: a run that cannot be continued at all has no row. Oldest run first, as the flag resumes them
//: (spec 5.8), and the order of two runs made together is their ids'.
export function resumableRuns({tasks, runs, automation}) {
  if (runs.phase !== "ready") return Object.freeze([]);
  const rows = [];
  for (const task of tasks.list) {
    const answer = task.unreadable ? null : automation.get(task.task_id) ?? null;
    const run = answer === null ? undefined : runs.list.find((row) => row.run_id === answer.run_id);
    const kind = answer === null || run === undefined ? null : continuable(answer);
    if (kind !== null) {
      rows.push(Object.freeze({run_id: run.run_id, task_id: task.task_id, expired: kind === "expired",
        title: task.title || task.task_id, created_at: run.created_at}));
    }
  }
  const order = (a, b) => (a.created_at === b.created_at ? (a.run_id < b.run_id ? -1 : 1)
    : (a.created_at < b.created_at ? -1 : 1));
  return Object.freeze(rows.sort(order));
}

//: The runs the block opens with marked: those a standing flag already lists, that can still be
//: continued. Nothing is marked on a flag that is off or was consumed: a new decision is a new
//: flag (spec 4.3.4).
export function initialMarks(flag, rows) {
  if (!flag.enabled) return Object.freeze([]);
  const listed = flag.resume_runs.map((row) => row.run_id);
  return Object.freeze(rows.filter((row) => !row.expired && listed.includes(row.run_id))
    .map((row) => row.run_id));
}

//: The body of a save: exactly four keys. A flag taken off names no run and no queue start,
//: whatever was marked when it was taken off (spec 4.3.4).
export function flagBody({enabled, actor, runIds, startQueue}) {
  return Object.freeze(enabled
    ? {enabled: true, actor, resume_runs: Object.freeze([...runIds]),
      start_task_queue: startQueue === true}
    : {enabled: false, actor, resume_runs: Object.freeze([]), start_task_queue: false});
}
