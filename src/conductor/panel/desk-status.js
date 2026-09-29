"use strict";
// The word of a task's row on the desk, from the raw fields the routes give and by
// the rules of spec 5.2.1, top to bottom: the first rule that fits decides.
//
// It is a pure module: values in, a key and its parameters out. The strings that say
// a key in a language are `desk-status-copy.js`; this module never says a word, so the
// desk's rail and, later, the hub's column can show the same task in the same words.
// The fields are read as the routes spell them, with no renaming -- `task` is a row of
// `GET /command/tasks`, `run` the newest run's row of `GET /command/runs` (or null),
// `automation` the answer of `GET /command/runs/<id>/automation` for that run (null when
// it was not read, which skips the rules that need it), and `entry` a record of the task
// queue with the same run (null until the queue is read).
//
// Only what the rail needs is built: `taskStatus` and the closed list of its keys. The
// other exports of the spec (attention items, the waiting-since rule, the journal
// projection) arrive with the slices that need them.

//: Every key `taskStatus` can answer, and the only ones: the copy holds a string in each
//: language for each of these and for nothing else.
export const STATUS_KEYS = Object.freeze([
  "task_unreadable", "not_started", "run_unreadable", "waiting_you",
  "queue_confirmation", "queue_blocked", "queued", "queued_inactive",
  "state_unknown", "running",
  "checkpoint_inactive", "checkpoint", "owner_missing", "stalled", "expired", "paused",
  "revoked",
  "outcome_succeeded", "outcome_verification_failed", "outcome_failed", "outcome_unknown",
  "outcome_rejected", "outcome_cancelled",
  "ended", "no_outcome",
]);

const say = (key, params = {}) => Object.freeze({key, params: Object.freeze(params)});

//: Rules 1-4: what the task and its newest run say before anything else can.
function first(task, run) {
  if (task?.unreadable) return say("task_unreadable");
  if (!run) return say("not_started");
  if (run.unreadable) return say("run_unreadable");
  return run.human_state === "required" ? say("waiting_you") : null;
}

//: Rules 5-7: a record of the task queue for this run.
function queued(entry) {
  if (entry?.state === "confirmation_required") return say("queue_confirmation");
  if (entry?.state === "blocked") return say("queue_blocked");
  if (entry?.state !== "preauthorized") return null;
  return entry.reason_code === "project_not_active" ? say("queued_inactive")
    : say("queued", {position: String(entry.position)});
}

//: Rules 8-9: what the run itself says it is doing.
function doing(run) {
  if (run.human_state === "unknown") return say("state_unknown");
  return run.open_actions > 0 ? say("running") : null;
}

const RESTART = Object.freeze({project_not_active: "checkpoint_inactive",
  explicit_resume_required: "checkpoint", owner_required: "owner_missing"});
const GRANTED = Object.freeze({expired: "expired", paused: "paused", revoked: "revoked",
  running: "running", waiting: "running", ready: "running"});

//: Rules 10-17: what the run's automation says. Skipped whole when it was not read.
function granted(automation) {
  if (!automation) return null;
  const {state, reason_code: reason} = automation;
  if (state === "restart_required") {
    return Object.hasOwn(RESTART, reason) ? say(RESTART[reason]) : null;
  }
  if (state === "stalled") return say("stalled", {reason_code: String(reason)});
  return Object.hasOwn(GRANTED, state) ? say(GRANTED[state]) : null;
}

//: Rule 18: the last outcome the run's own records carry. An outcome this build has no
//: word for is not "no result": it is a state it cannot name.
function outcome(run) {
  if (run.last_outcome === null || run.last_outcome === undefined) return null;
  const key = `outcome_${run.last_outcome}`;
  return STATUS_KEYS.includes(key) ? say(key) : say("state_unknown");
}

//: Rules 19-20: a plan that ended with no outcome, and a run nobody has authorized.
function settled(automation, entry) {
  if (automation?.state === "complete") return say("ended");
  return automation?.state === "unconfigured" && !entry ? say("not_started") : null;
}

export function taskStatus(input) {
  const {task, run, automation = null, entry = null} = input;
  return first(task, run) || queued(entry) || doing(run) || granted(automation)
    || outcome(run) || settled(automation, entry) || say("no_outcome");
}
