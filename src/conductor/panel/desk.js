"use strict";
// Boot module of the desk: it stands the regions of spec 5.1 on the page, reads what
// feeds them, and says on each the phase of the read that fed it.
//
// The regions are the five mounts of `desk.html`. Each stands in a machine word, one of the
// seven a state may hold, and the top bar says the whole of it in one plain sentence. The
// rail is drawn from the project's task list and the runs list, and from the automation of
// the newest run of each task, because the word of a task is a fact of all three (spec
// 5.2.1). The scene is drawn from the newest run of the task a person chose: choosing is a
// press, and the run is a read. The feed, the summary's numbers and the pult still have no
// module: they stay `empty` until one is written.
//
// It reaches the wire only through `desk-transport.js`, the ONLY module of the Studio and
// the desk that touches the network (`graph.js` and the classic `command.js` keep doors of
// their own), and holds no door, no timer and no storage of its own. Facts enter through
// a READ and through nothing else, and this module writes nothing at all. It reads the
// routes that exist for it today; the project route and its header are lane H's and are
// not faked here.
import {LATE, createTransport, path} from "./desk-transport.js";
import {message} from "./studio-i18n.js";
import {readPreferences} from "./studio-preferences.js";
import {projectTasks} from "./studio-tasks-model.js";
import {projectRuns} from "./studio-model.js";
import {newestRun} from "./studio-taskruns.js";
import {frozenCopy} from "./studio-draft.js";
import {projectRunRead} from "./studio-situation.js";
import {projectControls, wireControls} from "./studio-controls.js";
import {focusTarget, restoreFocus} from "./studio-focus.js";
import {mountRail} from "./desk-rail.js";
import {mountScene} from "./desk-scene.js";

//: The reads the desk makes, each named for the route it asks. A route is only ever
//: `path.<name>` of the transport module.
const READS = Object.freeze({
  tasks: () => path.tasks(),
  runs: () => path.runs(),
  automation: (runId) => path.automation(runId),
  run: (runId) => path.run(runId),
  controls: (runId) => path.controls(runId),
});
//: The five mounts, in reading order: the desk boots only on a page that carries all of
//: them. A mount no module fills stays in the word `empty`.
const MOUNTS = Object.freeze(["deskRail", "deskScene", "deskFeed", "deskSummary", "deskPult"]);
//: What a list stands at before a read and while one is out, and after a read that brought
//: nothing usable: a phase and no rows.
const NONE = Object.freeze([]);
const NOT_READ = Object.freeze({phase: "empty", list: NONE});
const READING = Object.freeze({phase: "loading", list: NONE});
const UNUSABLE = Object.freeze({phase: "failed", list: NONE});
//: The chosen task's run: nothing chosen yet, one being read, and one that could not be
//: used. `absent` says why a chosen task has no run to show, and is null otherwise.
const NO_RUN = Object.freeze({phase: "empty", detail: null, absent: null});
const READING_RUN = Object.freeze({phase: "loading", detail: null, absent: null});
const UNUSABLE_RUN = Object.freeze({phase: "failed", detail: null, absent: null});
//: The word of the live connection the scene is drawn under. The desk opens no stream yet,
//: so nothing it draws is confirmed live and the word is the Studio's own `closed`: the
//: deck then says a gate as an attention it cannot confirm and marks no active step, as it
//: does in the Studio once its stream has dropped. The stream slice turns this into state.
const NO_STREAM = "closed";
//: What the transport answers when the wire gave no answer at all: the read was
//: abandoned at its deadline, or the request could not be made. Any other answer
//: is the server's own refusal.
const UNANSWERED = Object.freeze([LATE, "store_error"]);

//: What a landed read is kept in: the two lists, the automation read for the newest run of
//: each task (a map that is built once and never changed), the task chosen, and the newest
//: run of that task. `choice` counts the choices made, so an answer that lands for a task a
//: person has since left is dropped. `door` is this window's transport, made at boot.
let state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
  taskId: null, run: NO_RUN});
let choice = 0;
let door = null;

const byId = (id) => document.getElementById(id);
//: The page's own language is the language of record: `<html lang>` says it, and anything
//: but Russian is read as English.
const locale = () => (document.documentElement.lang === "ru" ? "ru" : "en");
const readJson = (target) => door.readJson(target);

//: The phase a failed read puts its region in.
function phaseOf(error) {
  const code = error instanceof Error ? error.message : "store_error";
  return UNANSWERED.includes(code) ? "failed" : "refused";
}

//: The one word for a set of phases: the worst of them, and `ready` when none is worse.
function worst(phases) {
  for (const word of ["failed", "refused", "loading", "stale", "empty"]) {
    if (phases.includes(word)) return word;
  }
  return "ready";
}

function mark(node, phase) {
  node.setAttribute("data-state", phase);
}

//: Every word the page itself carries is a catalogue key: `data-i18n` is the text of a node
//: and `data-i18n-label` its accessible name.
function translate() {
  for (const node of document.querySelectorAll("[data-i18n]")) {
    node.textContent = message(locale(), node.dataset.i18n);
  }
  for (const node of document.querySelectorAll("[data-i18n-label]")) {
    node.setAttribute("aria-label", message(locale(), node.dataset.i18nLabel));
  }
  document.title = message(locale(), "desk.title");
}

function say(phase) {
  byId("deskStatus").textContent = message(locale(), `phase.${phase}`);
}

//: The word of each region a read feeds, and the shell's, which is the worst of them. The
//: rail needs both lists, the summary needs the runs, and the scene needs the run of the
//: chosen task -- and counts toward the shell only once a read of it has been asked.
function words() {
  const rail = worst([state.tasks.phase, state.runs.phase]);
  const scene = state.run.phase;
  const fed = scene === "empty" ? [] : [scene];
  return {rail, scene, summary: state.runs.phase,
    shell: worst([rail, state.runs.phase, ...fed])};
}

function render() {
  const held = focusTarget();
  const said = words();
  const view = {locale: locale(), listed: said.rail === "ready", tasks: state.tasks,
    runs: state.runs, automation: state.automation, taskId: state.taskId, run: state.run,
    connection: NO_STREAM, task: state.tasks.list.find((row) => row.task_id === state.taskId) ?? null};
  mountRail(byId("deskRail"), view, handlers);
  mountScene(byId("deskScene"), view, handlers);
  mark(byId("deskRail"), said.rail);
  mark(byId("deskScene"), said.scene);
  mark(byId("deskSummary"), said.summary);
  mark(byId("deskShell"), said.shell);
  say(said.shell);
  restoreFocus(byId("deskShell"), held);
}

function move(patch) {
  state = Object.freeze({...state, ...patch});
  render();
}

//: One list read, judged by the boundary that owns the list's shape. A body the boundary
//: cannot read is a read that FAILED, however healthy the answer looked.
async function readTasks() {
  try {
    const list = projectTasks(await readJson(READS.tasks()));
    return list === null ? UNUSABLE : Object.freeze({phase: "ready", list});
  } catch (error) {
    return Object.freeze({phase: phaseOf(error), list: NONE});
  }
}

async function readRuns() {
  try {
    const payload = await readJson(READS.runs());
    return projectRuns(payload) === null ? UNUSABLE
      : Object.freeze({phase: "ready", list: frozenCopy(payload.runs)});
  } catch (error) {
    return Object.freeze({phase: phaseOf(error), list: NONE});
  }
}

//: One task's automation, as the hub reads it, so a task is never named two ways. A read
//: that fails is `null`, which the rules take as "not read" and skip the rows that need it,
//: and so is an answer that names a run other than the one asked about: it is not this
//: run's automation, whatever it says.
async function readOneAutomation(found, taskId, latest) {
  const runId = latest.row.run_id;
  try {
    const answer = await readJson(READS.automation(runId));
    found.set(taskId, answer?.run_id === runId ? answer : null);
  } catch (_error) {
    found.set(taskId, null);
  }
}

//: The automation of the newest run of each readable task.
async function readAutomation(tasks, runs) {
  const found = new Map();
  if (tasks.phase !== "ready" || runs.phase !== "ready") return found;
  const newest = tasks.list.filter((task) => !task.unreadable)
    .map((task) => [task.task_id, newestRun(runs, task.task_id)])
    .filter(([, latest]) => latest.state === "known");
  await Promise.all(newest.map(([taskId, latest]) => readOneAutomation(found, taskId, latest)));
  return found;
}

async function load() {
  move({tasks: READING, runs: READING});
  const [tasks, runs] = await Promise.all([readTasks(), readRuns()]);
  move({tasks, runs, automation: await readAutomation(tasks, runs)});
}

//: The newest run of one task, read whole: the run and, beside it, what protects it. A run
//: read that names another task, or that the boundary cannot read, is a read that FAILED; a
//: controls read that is lost only leaves the run without them.
async function readRun(runId, taskId) {
  try {
    const [read, controls] = await Promise.all([
      readJson(READS.run(runId)),
      readJson(READS.controls(runId)).catch(() => null),
    ]);
    if (projectRunRead(read) === null || read.config?.task?.id !== taskId) return UNUSABLE_RUN;
    const settled = projectControls(controls);
    return Object.freeze({phase: "ready", absent: null, detail: frozenCopy({...read,
      controls: settled === null ? null : wireControls(settled)})});
  } catch (error) {
    return Object.freeze({phase: phaseOf(error), detail: null, absent: null});
  }
}

//: Why a chosen task has no run to show, or null when it has one to read.
function absence(task, newest) {
  if (!task || task.unreadable) return "unreadable";
  return newest.state === "known" ? null : newest.state;
}

//: What stands on the scene while the newest run of a task is read: the run already drawn,
//: if it is this task's, kept and said to be from an earlier read; else nothing.
function whileReading(taskId) {
  const shown = state.taskId === taskId ? state.run.detail : null;
  return shown === null ? READING_RUN
    : Object.freeze({phase: "stale", detail: shown, absent: null});
}

//: What a press MEANS. Choosing a task remembers which one and reads its newest run; it
//: writes nothing. Only the answer to the current choice is kept.
async function chooseTask(taskId) {
  const asked = ++choice;
  const newest = newestRun(state.runs, taskId);
  const absent = absence(state.tasks.list.find((row) => row.task_id === taskId), newest);
  if (absent !== null) {
    move({taskId, run: Object.freeze({phase: "empty", detail: null, absent})});
    return;
  }
  move({taskId, run: whileReading(taskId)});
  const landed = await readRun(newest.row.run_id, taskId);
  if (asked === choice) move({run: landed});
}

const handlers = Object.freeze({chooseTask});

//: The page's language is the address's (`#lang=ru`), and without a choice the page's own
//: `lang` stands; the browser's language as a default arrives with the hash module, which
//: is the one place allowed to ask the platform for it.
function boot() {
  document.documentElement.lang = readPreferences(location.hash,
    document.documentElement.lang).locale;
  door = createTransport(locale);
  translate();
  load();
}

if (byId("deskShell") && MOUNTS.every((id) => byId(id))) boot();
