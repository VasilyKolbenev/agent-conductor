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
// Beside the word of a row it holds the rule of the time a human step has waited
// (`waitingSince`, spec 4.5.6) and the projection of a run's journal that rule reads
// (`journalIndex`): the hub builds the same index server-side and the two are held equal
// by a shared fixture. The module reads no clock -- an instant is a string a server wrote --
// and imports nothing, because the hub's page takes it whole with the other shared modules.

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

// -- the journal and the time a human step has waited (spec 4.5.6) --------------------------

//: Which field of a record says when it happened. A kind absent here states no instant this
//: build knows, and its row carries none: it is never stamped with a guess. The table is the
//: Studio's own (`studio-runwords.js`), spelled again because this module imports nothing;
//: a test holds the two equal, kind by kind.
const INSTANT_FIELDS = Object.freeze({
  action_proposal: "proposed_at", action_request: "requested_at",
  action_result: "observed_at", adapter_observation: "observed_at",
  artifact: "created_at", attempt_event: "recorded_at",
  correction_feedback: "recorded_at", decision: "decided_at", evidence: "observed_at",
  graph_definition: "created_at", run_authorization: "authorized_at",
  run_authorization_control: "recorded_at", run_terminal: "recorded_at",
});
//: The hub keeps the last 256 rows of a journal and the desk keeps the same number, so a
//: record older than the window is not found by either.
const JOURNAL_ROWS = 256;

const text = (value) => (typeof value === "string" ? value : null);
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

//: One row of the index, or null for a row that is not a typed record.
function indexRow(row) {
  if (!isObject(row) || typeof row.record_type !== "string" || !isObject(row.record)) return null;
  const {record_type: kind, record} = row;
  const field = Object.hasOwn(INSTANT_FIELDS, kind) ? INSTANT_FIELDS[kind] : null;
  return Object.freeze({record_type: kind, instant: field === null ? null : text(record[field]),
    action_id: text(record.action_id), node_id: text(record.node_id),
    proposal_id: text(record.proposal_id)});
}

//: The projection of a run's journal (the `records` of a run read) that `waitingSince` reads:
//: the last 256 typed rows, each cut to what finding a wait needs and none of the payload.
export function journalIndex(records) {
  const rows = Array.isArray(records) ? records.map(indexRow).filter((row) => row !== null) : [];
  return Object.freeze(rows.slice(-JOURNAL_ROWS));
}

const instantMs = (instant) => (typeof instant === "string" ? Date.parse(instant) : Number.NaN);

//: Of some instants the earliest, or the latest when `later`, compared as times and not as
//: text; a value that is not an instant is not found. Null when none is.
function pick(instants, later) {
  const sorted = instants.filter((instant) => !Number.isNaN(instantMs(instant)))
    .sort((left, right) => instantMs(left) - instantMs(right));
  return sorted.length === 0 ? null : sorted[later ? sorted.length - 1 : 0];
}

//: The last result the journal holds for a step, in journal order. A result names no step,
//: so it is joined to one through the requests the step made (`action_id`).
function lastResult(journal, nodeId) {
  const requested = new Set(journal.filter((row) => row.record_type === "action_request"
    && row.node_id === nodeId && row.action_id !== null).map((row) => row.action_id));
  const results = journal.filter((row) => row.record_type === "action_result"
    && requested.has(row.action_id));
  return results.length === 0 ? null : results.at(-1).instant;
}

//: When a step was opened: the latest last-result among the steps that opened it, and for a
//: step nothing opened (an input step) the moment the graph was defined.
function openedAt(journal, runtime, nodeId) {
  const node = runtime.find((row) => row.node_id === nodeId);
  if (!node || !Array.isArray(node.opened_by)) return null;
  if (node.opened_by.length === 0) {
    return journal.find((row) => row.record_type === "graph_definition")?.instant ?? null;
  }
  return pick(node.opened_by.map((step) => lastResult(journal, step)), true);
}

const proposedAt = (journal, _runtime, proposal) => journal.find(
  (row) => row.record_type === "action_proposal" && row.proposal_id === proposal)?.instant ?? null;

//: The record each reason of a human step is dated by. `reconcile` has none: the server names
//: no source for it, so it is always "not found".
const OPENERS = Object.freeze({
  confirmation: proposedAt,
  attempt_bound: (journal, _runtime, node) => lastResult(journal, node),
  gate_decision: openedAt,
  input_document: openedAt,
});

//: When the step a person is asked about began to wait, as an instant string of the journal, or
//: null when the record that opened it is not there: the step closed without an action, the
//: record is older than the 256 the projection keeps, the journal cannot be read, or the
//: reason has no source. Several sources give the earliest that is found.
export function waitingSince(input) {
  const {reason, sources, journal, runtime} = isObject(input) ? input : {};
  if (!Object.hasOwn(OPENERS, reason)) return null;
  const rows = Array.isArray(journal) ? journal.filter(isObject) : [];
  const nodes = Array.isArray(runtime) ? runtime.filter(isObject) : [];
  const named = (Array.isArray(sources) ? sources : []).filter((one) => typeof one === "string");
  return pick(named.map((source) => OPENERS[reason](rows, nodes, source)), false);
}
