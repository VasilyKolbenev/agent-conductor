"use strict";
// The rail: the current project's tasks, one button each, and under each title the word
// the task's NEWEST run has earned (spec 5.1 and 5.2.1). It draws what the boot module
// hands it and reads nothing itself: a press is a call to `handlers.chooseTask`, and the
// only fact it derives is the row's word, through `taskStatus`, which is the one place the
// rules of that word are written.
//
// The word is said in the reader's language through the catalogue. A machine word never
// reaches the screen: `verification_failed` is drawn as its own words with its sentence in
// the same row, so the run's exit code is never read as a verified result.
import {element} from "./command-view.js";
import {MESSAGES, localize} from "./studio-i18n.js";
import {taskStatus} from "./desk-status.js";
import {newestRun} from "./studio-taskruns.js";

//: The words that ask for a person or say the run is going, and no other, carry a tone;
//: the word is always in the row as well, so the tone is never the only carrier.
const TONES = Object.freeze({waiting_you: "amber", queue_confirmation: "amber", running: "ion"});
//: The list holds a run row this window cannot read, so which task it belongs to, and
//: therefore which run is newest, cannot be established: the row reads as an unreadable
//: record rather than as "not started".
const HIDDEN_RUN = Object.freeze({unreadable: true});

//: Two tasks may share a title; a title names nothing, so a repeated or unreadable one
//: carries the tail of its id.
function titleOf(view, task) {
  const repeated = view.tasks.list.filter((other) => other.title === task.title).length > 1;
  const named = task.title || localize(view, "desk.rail.unreadable");
  return repeated || task.unreadable ? `${named} · ${task.task_id.slice(-8)}` : named;
}

//: The newest run of the task, `null` when it has none, and the hidden row when the list
//: cannot say.
function newestOf(view, task) {
  if (task.unreadable) return null;
  const newest = newestRun(view.runs, task.task_id);
  if (newest.state === "known") return newest.row;
  return newest.state === "none" ? null : HIDDEN_RUN;
}

function statusOf(view, task) {
  const run = newestOf(view, task);
  const automation = run && !run.unreadable ? view.automation.get(task.task_id) ?? null : null;
  return taskStatus({task, run, automation, entry: null});
}

//: A key's message takes the parameters its text names and no other: the status carries
//: facts (a queue position, the reason a run stalled) that a given wording may not use.
function wordsOf(view, {key, params}) {
  const id = `desk_status.${key}`;
  const wanted = [...MESSAGES[id][view.locale].matchAll(/\{([a-z_]+)\}/g)].map((found) => found[1]);
  return localize(view, id, Object.fromEntries(wanted.map((name) => [name, String(params[name])])));
}

function row(view, task, handlers) {
  const status = statusOf(view, task);
  const tone = Object.hasOwn(TONES, status.key) ? TONES[status.key] : null;
  const note = status.key === "outcome_verification_failed"
    ? [element("span", {className: "desk-task__note",
      text: localize(view, "view.verification_note")})] : [];
  const button = element("button", {type: "button", className: "desk-task",
    "data-task-id": task.task_id, "data-focus-key": `task:${task.task_id}`,
    "aria-pressed": String(view.taskId === task.task_id)}, [
    element("strong", {className: "desk-task__title", text: titleOf(view, task)}),
    element("span", {className: "desk-task__state", "data-tone": tone,
      text: wordsOf(view, status)}),
    ...note]);
  button.addEventListener("click", () => handlers.chooseTask(task.task_id));
  return button;
}

//: Nothing is drawn until the lists that feed the rail have both landed: a half-read
//: list would name a status the rules cannot yet earn.
export function mountRail(mount, view, handlers) {
  if (view.phase !== "ready") {
    mount.replaceChildren();
    return;
  }
  const tasks = view.tasks.list;
  mount.replaceChildren(
    element("h2", {className: "desk-rail__head", text: localize(view, "desk.rail.label")}),
    tasks.length
      ? element("div", {className: "desk-rail__list"},
        tasks.map((task) => row(view, task, handlers)))
      : element("p", {className: "desk-rail__none", text: localize(view, "desk.rail.none")}));
}
