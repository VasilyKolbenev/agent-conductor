"use strict";
// The summary at the foot of the desk (spec 5.1 and 5.4): four counters, a strip of tasks and
// what is going on now, and, on a press, who did what. This module is the pure half of it: values
// in, frozen values out, no language and no DOM; the drawing is `desk-summary.js` and the words
// are `desk-summary-copy.js`.
//
// Every task of the project stands in exactly one place, and the place is decided by the word the
// rail already gives the task's newest run (`taskStatus`, called with the same inputs), so a task
// is never named one way in the rail and another here. `BUCKETS` is that decision written once,
// a word at a time, and a test holds its keys equal to `STATUS_KEYS`:
//
//   waiting  the words that put the task in the project's "waiting for you" list (spec 4.1.9): a
//            step for a person, a confirmation in the queue, a checkpoint that needs a resume, a
//            stalled or expired grant;
//   working  a run has begun and is not over, and nothing there asks for a person: it goes, or a
//            person paused or revoked it, or it is parked for the owner or another project;
//   left     work remains: nothing began, the run waits in the queue, or its last word is a
//            result that nobody has accepted;
//   unclear  the records cannot say (an unreadable task or run, a state or an outcome unknown).
//
// A fifth place, `closed`, is not a word of the rail but a fact of a run read: the newest run
// ended `complete` AND its final gate -- a gate with no road out on "always" or "if approved" --
// stands approved for the lap the plan is on (spec 5.4, 9.4 rules 3-4). `complete` alone is not
// acceptance: a rejected run and an approved one both reach it. The fact is `digestOf(...).closed`;
// `mayBeClosed` is the necessary condition on a run's ROW, so a caller reads a run only when it
// could have been accepted (nothing open, nothing asks a person, some action reached a result).
// It does not ask for a success: a person may accept at the final gate a result that failed, and
// that run is closed all the same, as the caption says.
//
// Nothing here reads a clock; an instant is compared as the time it names and left as the string
// the record carried. No number is invented: a count is a count of records, and what a record
// does not say is null, an empty list or absent.
import {taskStatus} from "./desk-status.js";
import {newestRun} from "./studio-taskruns.js";
import {sceneOf} from "./studio-scene-model.js";
import {decisionRows} from "./studio-runread.js";
import {runPass} from "./desk-feed-model.js";

//: The place of each word a task can have. `closed` is missing on purpose: it is a fact.
export const BUCKETS = Object.freeze({
  waiting_you: "waiting", queue_confirmation: "waiting", checkpoint: "waiting",
  stalled: "waiting", expired: "waiting",
  running: "working", paused: "working", revoked: "working", checkpoint_inactive: "working",
  owner_missing: "working",
  not_started: "left", queue_blocked: "left", queued: "left", queued_inactive: "left",
  outcome_succeeded: "left", outcome_verification_failed: "left", outcome_failed: "left",
  outcome_rejected: "left", outcome_cancelled: "left", ended: "left", no_outcome: "left",
  task_unreadable: "unclear", run_unreadable: "unclear", state_unknown: "unclear",
  outcome_unknown: "unclear",
});
//: The places, in the order the bar says them.
export const PLACES = Object.freeze(["working", "waiting", "closed", "left", "unclear"]);

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const list = (value) => (Array.isArray(value) ? value : []);
const text = (value) => (typeof value === "string" && value !== "" ? value : null);
const freeze = (value) => Object.freeze(value);
//: A run row the list cannot read: the newest run of every task is then not established.
const HIDDEN_RUN = freeze({unreadable: true});

// -- the tasks --------------------------------------------------------------------------------

//: The newest run of a task as the rail reads it: its row, null when it has none, or the hidden
//: row when the list holds a record this window cannot read.
function newestOf(runs, task) {
  if (task.unreadable) return null;
  const newest = newestRun(runs, task.task_id);
  if (newest.state === "known") return newest.row;
  return newest.state === "none" ? null : HIDDEN_RUN;
}

//: Whether a run could have been accepted, judged on its row alone: nothing is open, no step
//: asks a person, and some action reached a result. A run that fails any of the three cannot be
//: closed, so it is never read to find out.
export function mayBeClosed(row) {
  return isObject(row) && row.unreadable !== true && row.human_state === "not_required"
    && row.open_actions === 0 && text(row.last_outcome) !== null;
}

function taskRow(task, runs, automation, closing) {
  const run = newestOf(runs, task);
  const readable = run !== null && run.unreadable !== true;
  const word = taskStatus({task, run, entry: null,
    automation: readable ? automation.get(task.task_id) ?? null : null});
  const held = closing.get(task.task_id);
  const digest = readable && isObject(held) && held.run_id === run.run_id ? held : null;
  const place = digest !== null && digest.closed ? "closed" : BUCKETS[word.key] ?? "unclear";
  return freeze({task_id: task.task_id, title: text(task.title), key: word.key,
    params: word.params, place, run_id: readable ? run.run_id : null, digest});
}

//: Every task in one place: `{rows, counts, total}`, the rows in the order of the list.
export function summaryOf(input) {
  const {tasks, runs, automation, closing} = isObject(input) ? input : {};
  const rows = list(tasks?.list).filter((task) => isObject(task) && text(task.task_id))
    .map((task) => taskRow(task, runs, automation ?? new Map(), closing ?? new Map()));
  const counts = Object.fromEntries(PLACES.map((place) => [place,
    rows.filter((row) => row.place === place).length]));
  return freeze({rows: freeze(rows), counts: freeze(counts), total: rows.length});
}

// -- a run: acceptance, who did what, and what is going on ----------------------------------

const records = (detail) => list(detail.records).filter((row) => isObject(row)
  && isObject(row.record));
const of = (detail, type) => records(detail).filter((row) => row.record_type === type)
  .map((row) => row.record);

function instancesOf(detail) {
  return new Map(list(detail.config?.instances).filter((one) => isObject(one) && text(one.id))
    .map((one) => [one.id, one]));
}

//: A participant as the summary names one: its instance and the harness the run froze for it.
function named(instances, instance, adapter = null) {
  const id = text(instance);
  return freeze({instance: id, harness: text(instances.get(id)?.adapter) ?? text(adapter)});
}

//: Each participant once, in the order the records first name them.
function distinct(people) {
  const seen = new Set();
  return people.filter((one) => {
    const key = one.instance ?? one.harness;
    return key !== null && !seen.has(key) && seen.add(key);
  });
}

//: The gates of the plan no road leaves on "always" or "if approved": approving one opens
//: nothing, so it is where the work is accepted.
function finalGates(detail) {
  const definition = detail.graph?.definition;
  const edges = list(definition?.edges).filter(isObject);
  return list(definition?.nodes).filter((node) => isObject(node) && node.kind === "gate"
    && !edges.some((edge) => edge.from_node === node.node_id
      && (edge.condition === undefined || edge.condition === null
        || edge.condition === "on_approved")));
}

//: Who approved the final gates that stand approved for the lap the plan is on: a gate reads
//: `satisfied` only when the standing answer is an approval, and that answer is the last receipt.
function acceptedBy(detail) {
  const finals = new Set(finalGates(detail).map((node) => node.node_id));
  const laps = new Map(list(detail.graph?.situation?.gates).filter(isObject)
    .map((gate) => [gate.node_id, gate.standing_belongs_to_current_lap]));
  const actors = decisionRows(detail).filter((row) => finals.has(row.node_id)
    && row.decision === "satisfied" && laps.get(row.node_id) !== false)
    .map((row) => text(row.receipt?.actor));
  return freeze([...new Set(actors.filter((actor) => actor !== null))]);
}

//: What a run read says of who did, who checked and who accepted, and whether it was accepted at
//: its final gate. Null for a value that is not a run read. Who checked is an independent
//: checker: the evidence names the participant that made the check (`verifier_instance_id`). A
//: step with no verifier is checked by its own adapter over its own evidence, which names no such
//: participant (the read leaves the field out), and that is nobody's check of the work but the
//: doer's own, so it is not listed here.
export function digestOf(detail) {
  const run = isObject(detail) && isObject(detail.run) ? text(detail.run.run_id) : null;
  if (run === null) return null;
  const instances = instancesOf(detail);
  const ended = of(detail, "run_terminal").some((one) => one.state === "complete");
  const accepted = acceptedBy(detail);
  return freeze({run_id: run, closed: ended && accepted.length > 0, pass: runPass(detail),
    did: freeze(distinct(of(detail, "action_result")
      .map((one) => named(instances, one.instance_id)))),
    verified: freeze(distinct(of(detail, "evidence")
      .filter((one) => one.verification === "verified" && text(one.verifier_instance_id) !== null)
      .map((one) => named(instances, one.verifier_instance_id, one.verified_by)))),
    accepted});
}

const moment = (iso) => (typeof iso === "string" ? Date.parse(iso) : Number.NaN);

//: When each participant last did something a record dates: the latest instant among the
//: records that name it.
function lastInstants(detail) {
  const actions = new Map(of(detail, "action_request").map((one) => [one.action_id, one]));
  const seen = [];
  const note = (instance, iso) => { if (text(instance) && text(iso)) seen.push([instance, iso]); };
  for (const one of of(detail, "action_proposal")) note(one.instance_id, one.proposed_at);
  for (const one of of(detail, "action_request")) note(one.instance_id, one.requested_at);
  for (const one of of(detail, "attempt_event")) note(one.instance_id, one.recorded_at);
  for (const one of of(detail, "action_result")) note(one.instance_id, one.observed_at);
  for (const one of of(detail, "artifact")) {
    note(actions.get(one.source_action_id)?.instance_id, one.created_at);
  }
  for (const one of of(detail, "evidence")) note(one.verifier_instance_id, one.verified_at);
  for (const one of of(detail, "correction_feedback")) {
    note(one.checker_instance_id, one.recorded_at);
  }
  const last = new Map();
  for (const [instance, iso] of seen) {
    const held = last.get(instance);
    if (!Number.isNaN(moment(iso)) && (held === undefined || moment(iso) > moment(held))) {
      last.set(instance, iso);
    }
  }
  return last;
}

//: The participants of a run in the order the run froze them, each with what the records say it
//: did: its duty in the plan, the actions authorized for it, the checks it made, the documents its
//: actions published and the instant it was last named. What no record says is 0, empty or null.
export function participantsOf(detail) {
  if (!isObject(detail) || !isObject(detail.run)) return freeze([]);
  const duties = new Map(list(sceneOf(detail)?.participants)
    .map((one) => [one.instanceId, one.duty]));
  const requests = of(detail, "action_request");
  const artifacts = of(detail, "artifact");
  const last = lastInstants(detail);
  return freeze([...instancesOf(detail).values()].map((one) => freeze({
    instance: one.id, harness: text(one.adapter), model: text(one.model),
    duty: duties.get(one.id) ?? "none",
    actions: requests.filter((request) => request.instance_id === one.id).length,
    checks: of(detail, "evidence").filter((proof) => proof.verifier_instance_id === one.id).length,
    documents: freeze([...new Set(artifacts.filter((doc) => requests.some((request) =>
      request.action_id === doc.source_action_id && request.instance_id === one.id))
      .map((doc) => text(doc.artifact_ref)).filter((ref) => ref !== null))]),
    last: last.get(one.id) ?? null})));
}

const NOTHING = freeze({doing: freeze([]), asking: freeze([])});

//: What is going on now in a run: the steps with an attempt in flight, each with the participant
//: that owns it, and the titles of the steps that ask a person.
export function nowOf(detail) {
  const scene = isObject(detail) && isObject(detail.run) ? sceneOf(detail) : null;
  if (scene === null) return NOTHING;
  const instances = instancesOf(detail);
  const doing = scene.steps.filter((step) => step.word === "awaiting_result")
    .map((step) => freeze({instance: step.ownerId,
      harness: text(instances.get(step.ownerId)?.adapter), step: step.title}));
  const asking = scene.steps.filter((step) => step.word === "needs_decision")
    .map((step) => step.title);
  return freeze({doing: freeze(doing), asking: freeze(asking)});
}
