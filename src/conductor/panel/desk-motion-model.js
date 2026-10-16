"use strict";
// When the desk may play a transition (spec 5.5, D11), as values: the view the boot module
// draws from goes in, the moments it shows come out. Nothing here touches the page or the
// clock; `desk-motion.js` draws what this module decides.
//
// There are four moments: a task accepted (`accepted`), a task that now waits for the
// person (`to_you`), a task finished (`finished`) and a new task entering the list
// (`entered`). A moment is a CHANGE watched live: the detector compares each reading with
// the reading before it, and a reading is compared only while the stream is `open`. Every
// other connection word ends the comparison, so the first reading after a load, a drop, a
// reconnect or a page restored from the cache is a baseline and says nothing. That one rule
// is what keeps a transition from being played again after a reconnect or a reload.
import {taskStatus} from "./desk-status.js";
import {newestRun} from "./studio-taskruns.js";

//: The longest any one movement may last, its delay included (spec 5.5: «не больше 1,2 с»).
export const FX_MAX_MS = 1200;

const timing = (duration, delay = 0) => Object.freeze({duration, delay});
//: Every movement of the desk, by name. `desk-motion.js` plays no other; a test holds each
//: one finite and inside the cap.
export const TIMINGS = Object.freeze({
  comet: timing(700),
  landing: timing(500, 600),
  ring: timing(600),
  ring_late: timing(600, 220),
  wave: timing(700),
  wave_late: timing(700, 260),
  count: timing(700, 300),
  spark: timing(650, 120),
  halo: timing(900),
});

const NONE = Object.freeze([]);
//: A newest run this window cannot read: which run is newest cannot be said (the rail's rule).
const HIDDEN_RUN = Object.freeze({unreadable: true});
//: A run that is alive: the only places a finish can be watched from.
const ALIVE = Object.freeze(["running", "waiting_you"]);
//: The moments in the order a plaque prefers them, and the three the scene plays.
const URGENCY = Object.freeze(["to_you", "finished", "accepted", "entered"]);
const SCENE_KINDS = Object.freeze(["to_you", "finished", "accepted"]);
//: At most this many new tasks enter at once; the rest are in the list all the same.
const ENTRY_CAP = 3;

const moment = (kind, taskId) => Object.freeze({kind, taskId});

//: The newest run of the task: `null` when it has none, the hidden row when the list cannot say.
function newestOf(view, task) {
  if (task.unreadable) return null;
  const newest = newestRun(view.runs, task.task_id);
  if (newest.state === "known") return newest.row;
  return newest.state === "none" ? null : HIDDEN_RUN;
}

//: The record of the project queue that stands for this run, or null.
function entryOf(view, run) {
  if (run === null || run.unreadable || view.queue === null) return null;
  return view.queue.entries.find((one) => one.run_id === run.run_id) ?? null;
}

//: One task of a reading: its id, the key the rail would say for it, and whether that key can
//: be vouched for. A task whose run could not be read, or whose automation could not, has a key
//: that is a guess: it is not a row to compare, so a read that failed never looks like a task
//: that started or finished.
function rowOf(view, task) {
  const run = newestOf(view, task);
  const read = run !== null && !run.unreadable;
  const automation = read ? view.automation.get(task.task_id) ?? null : null;
  const {key} = taskStatus({task, run, automation, entry: entryOf(view, run)});
  const vouched = !task.unreadable && (run === null || (read && automation !== null));
  return Object.freeze({taskId: task.task_id, key, vouched});
}

//: The tasks of a view as a reading, or null while the lists are not both read (a render in
//: which they are out is not a reading) and in the terminal state.
export function readingOf(view) {
  if (view.foreign || view.tasks.phase !== "ready" || view.runs.phase !== "ready") return null;
  return view.tasks.list.map((task) => rowOf(view, task));
}

//: Whether a view is a live one: the desk is not in its terminal state and the stream is open.
export const isLive = (view) => !view.foreign && view.connection === "open";

//: The moment a task's change of key says, or null. Only a change INTO a key counts, and only
//: from the keys that make sense of it: a resume, an answered gate and a new run are not
//: moments, and neither is a failure.
function kindOf(before, after) {
  if (after === before) return null;
  if (after === "waiting_you") return "to_you";
  if (after === "outcome_succeeded" && ALIVE.includes(before)) return "finished";
  return after === "running" && before === "not_started" ? "accepted" : null;
}

//: The moments of one row against what the last live reading held. A task the last reading did
//: not hold enters, and is compared as a task that was not started.
function momentsOf(row, previous) {
  const known = previous.has(row.taskId);
  const entered = known ? NONE : [moment("entered", row.taskId)];
  const before = known ? previous.get(row.taskId) : "not_started";
  const kind = row.vouched && before !== null ? kindOf(before, row.key) : null;
  return kind === null ? entered : [...entered, moment(kind, row.taskId)];
}

//: What the next reading is compared with: the keys of this one, and for a row that cannot be
//: vouched for the key the last reading had (`null` when it had none). Tasks gone are forgotten.
function remembered(previous, reading) {
  return new Map(reading.map((row) => [row.taskId,
    row.vouched ? row.key : previous?.get(row.taskId) ?? null]));
}

//: The detector of one page: it holds the last live reading and nothing else.
export function createDetector() {
  let previous = null;
  function observe(view) {
    if (!isLive(view)) {
      previous = null;
      return NONE;
    }
    const reading = readingOf(view);
    if (reading === null || view.queue === null) return NONE;
    const found = previous === null ? NONE : reading.flatMap((row) => momentsOf(row, previous));
    previous = remembered(previous, reading);
    return Object.freeze(found);
  }
  return Object.freeze({observe});
}

//: What the moments of one render play: ONE plaque (the most urgent moment), the scene's moment
//: for the task the scene draws, and the tasks that enter (the first three, in list order).
export function planOf(moments, chosen) {
  const first = (kinds, accepts) => kinds.map((kind) => moments.find((one) =>
    one.kind === kind && accepts(one))).find((one) => one !== undefined) ?? null;
  return Object.freeze({
    plaque: first(URGENCY, () => true),
    scene: chosen === null ? null : first(SCENE_KINDS, (one) => one.taskId === chosen),
    entered: Object.freeze(moments.filter((one) => one.kind === "entered").slice(0, ENTRY_CAP)
      .map((one) => one.taskId)),
  });
}
