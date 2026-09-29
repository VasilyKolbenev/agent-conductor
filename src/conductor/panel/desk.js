"use strict";
// Boot module of the desk: it stands the regions of spec 5.1 on the page, reads what
// feeds them, and says on each the phase of the read that fed it.
//
// The regions are the five mounts of `desk.html`. Each stands in a machine word, one of the
// seven a state may hold, and the top bar says the whole of it in one plain sentence. The
// rail is drawn from the project's task list and the runs list, and from the automation of
// the newest run of each task, because the word of a task is a fact of all three (spec
// 5.2.1). The scene is drawn from the newest run of the task a person chose, or from the run
// the address names: choosing is a press or a hash, and the run is a read. The feed, the
// summary's numbers and the pult still have no module: they stay `empty` until one is written.
//
// The address (spec 4.5.2 and 4.5.3) is read by `desk-hash.js` and moved by one function here,
// `remember`, which writes the canonical hash by `replaceState` and so fires no `hashchange`.
// A hash the desk did not write is read by ONE listener, the router, which selects, reads and
// sets the appearance and nothing else. A hash, or a project claim, that names another project
// than the one the desk bound to puts it in a terminal state, and it then reads and applies
// nothing.
//
// It reaches the wire only through `desk-transport.js`, the ONLY module of the Studio and
// the desk that touches the network (`graph.js` and the classic `command.js` keep doors of
// their own), and holds no door, no timer and no storage of its own. Facts enter through
// a READ and through nothing else, and this module writes nothing at all. It reads the
// routes that exist for it today, and the project claim only when a framed window asks for
// embed mode (spec 4.5.5): the claim's header, `X-Conduct-Project`, is lane H's and is not
// faked here. In embed mode it says its location to the hub, in one message, and listens to
// nothing the hub posts.
import {LATE, createTransport, path} from "./desk-transport.js";
import {message} from "./studio-i18n.js";
import {deskHash, foreignProject, navigationChange, preferenceHash, readDeskHash,
  readPreferences} from "./desk-hash.js";
import {announceLocation, claimNamesAnotherProject, embedAsked,
  embedTarget} from "./desk-embed.js";
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
  project: () => path.project(),
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
//: each task (a map that is built once and never changed), the task chosen, and the run drawn
//: for it; `foreign` is the terminal state of a desk open for another project. `choice`
//: counts the choices made, so an answer that lands for a task a person has since left is
//: dropped. `door` is this window's transport, made at boot.
let state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
  taskId: null, run: NO_RUN, foreign: false});
let choice = 0;
let door = null;
//: The project this desk bound to, from its first hash (null when that named none); the last
//: address the desk wrote, which a new hash is compared with; the hash it last wrote or read;
//: what was last remembered; and the promise that the lists have landed and the first hash
//: has been applied. `embedded` is the hub origin when embed mode is in force (null when it is
//: not), and `announced` is the location the hub was last told.
let bound = null;
let lastWritten = readDeskHash("");
let seen = "";
let shown = Object.freeze({task: null, run: null});
let booted = Promise.resolve();
let embedded = null;
let announced = null;

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

//: The one sentence of the top bar: the phase of the shell, or, in the terminal state, the
//: sentence that says the desk is open for another project.
function say(phase) {
  const key = state.foreign ? "desk.foreign" : `phase.${phase}`;
  byId("deskStatus").textContent = message(locale(), key);
}

//: The word of each region a read feeds, and the shell's, which is the worst of them. The
//: rail needs both lists, the summary needs the runs, and the scene needs the run of the
//: chosen task -- and counts toward the shell only once a read of it has been asked. A desk
//: open for another project draws no region and refuses as a whole.
function words() {
  if (state.foreign) return {rail: "empty", scene: "empty", summary: "empty", shell: "refused"};
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

//: Where the desk stands: the task chosen and the run drawn for it. The run is what is on
//: the scene, so an address never names a run the desk has not drawn.
function where() {
  return Object.freeze({task: state.taskId, run: state.run.detail?.run.run_id ?? null});
}

//: The one place the desk moves its own address (spec 4.5.3, point 4): the selection it
//: draws, then the appearance, in the canonical order of `deskHash`. A terminal desk writes
//: nothing. `replaceState` adds no history entry and fires no `hashchange`, so this can
//: never start a loop, and the address it leaves is the one a new hash is compared with.
//: A hash the router has not read yet is a request, and is not overwritten: the router
//: that reads it normalises it.
function remember() {
  if (state.foreign || location.hash !== seen) return;
  const at = where();
  const embed = embedded === null ? null : "hub";
  const address = preferenceHash(deskHash({project: bound, embed, task: at.task, run: at.run}),
    {locale: locale(), theme: document.documentElement.getAttribute("data-theme")});
  history.replaceState(null, "", address);
  seen = location.hash;
  lastWritten = readDeskHash(address);
  shown = at;
}

//: Say where the desk is to the hub that framed it (spec 4.5.5), when embed mode is in force
//: and this is not what the hub was last told. The message is the location and nothing else.
function announce() {
  if (embedded === null || state.foreign) return;
  const at = where();
  if (announced !== null && announced.task === at.task && announced.run === at.run) return;
  announced = at;
  announceLocation(window.parent, embedded.origin,
    {project_id: bound, task_id: at.task, run_id: at.run});
}

//: A change of what is drawn is remembered in the address and told to the hub; a redraw of
//: the same is not.
function follow() {
  const at = where();
  if (at.task !== shown.task || at.run !== shown.run) remember();
  announce();
}

//: A terminal desk keeps nothing a late answer brings.
function move(patch) {
  if (state.foreign) return;
  state = Object.freeze({...state, ...patch});
  render();
  follow();
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

//: The automation of the newest run of each readable task. A desk that went foreign while its
//: lists were out asks for none: there is nothing left for the answers to be kept in.
async function readAutomation(tasks, runs) {
  const found = new Map();
  if (state.foreign || tasks.phase !== "ready" || runs.phase !== "ready") return found;
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

//: Why a chosen task has no run to show, or null when it has one to read. A run the address
//: names is judged by its own read, so the newest run need not be known for it.
function absence(task, newest, named) {
  if (!task || task.unreadable) return "unreadable";
  if (named) return null;
  return newest.state === "known" ? null : newest.state;
}

//: What stands on the scene while the newest run of a task is read: the run already drawn,
//: if it is this task's, kept and said to be from an earlier read; else nothing.
function whileReading(taskId) {
  const shown = state.taskId === taskId ? state.run.detail : null;
  return shown === null ? READING_RUN
    : Object.freeze({phase: "stale", detail: shown, absent: null});
}

//: What a press or a hash MEANS. Choosing a task remembers which one and reads its newest
//: run, or the run named with it; it writes nothing. Only the answer to the current choice
//: is kept.
async function chooseTask(taskId, runId = null) {
  if (state.foreign) return;
  const asked = ++choice;
  const newest = newestRun(state.runs, taskId);
  const absent = absence(state.tasks.list.find((row) => row.task_id === taskId), newest,
    runId !== null);
  if (absent !== null) {
    move({taskId, run: Object.freeze({phase: "empty", detail: null, absent})});
    return;
  }
  move({taskId, run: whileReading(taskId)});
  const landed = await readRun(runId ?? newest.row.run_id, taskId);
  if (asked === choice) move({run: landed});
}

const handlers = Object.freeze({chooseTask});

// -- the address ------------------------------------------------------------------------

//: The page's language and theme, written on the document and said in words: the language
//: is `<html lang>`, the theme is the root's `data-theme` (none is the system's).
function paintAppearance(next) {
  const root = document.documentElement;
  root.lang = next.locale;
  if (next.theme === null) root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", next.theme);
  translate();
}

//: A language or theme a new hash asks for. Nothing is done when it is the one already set;
//: otherwise the page is repainted and drawn again. Says whether the language changed.
function setAppearance(next) {
  const root = document.documentElement;
  const language = locale() !== next.locale;
  if (!language && (root.getAttribute("data-theme") ?? null) === next.theme) return false;
  paintAppearance(next);
  render();
  return language;
}

//: The terminal state of a desk open for another project (spec 4.5.1): everything it holds is
//: dropped, one sentence says so, and `move` keeps nothing from then on.
function enterForeign() {
  state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
    taskId: null, run: NO_RUN, foreign: true});
  render();
}

//: Apply the steps of a hash the desk did not write, top to bottom. The task and its run are
//: the only navigation the desk has a surface for today (the pult, the panels and the wizard
//: come with their modules), so no other step has a row here. A task the lists do not hold,
//: or a run with no task to belong to, is dropped. Says whether it opened a run.
async function navigate(change, address) {
  const keys = change.steps.map((step) => step.key);
  if (!keys.includes("task") && !keys.includes("run")) return false;
  const taskId = keys.includes("task") ? address.task : state.taskId;
  if (taskId === null || !state.tasks.list.some((row) => row.task_id === taskId)) return false;
  await chooseTask(taskId, keys.includes("run") ? address.run : null);
  return true;
}

//: The run on the scene, read again -- for a language that changed under it.
async function reread() {
  const run = where().run;
  if (state.taskId !== null && run !== null) await chooseTask(state.taskId, run);
}

//: The one listener (spec 4.5.3). A new hash is read against the last one the desk wrote: a
//: project that is not the bound one ends the desk; a language or theme is set; a navigation
//: key that moved is applied; a hash with none moves nothing, so the hub can send the language
//: alone. It selects, reads and sets the appearance, and writes nothing.
async function onHashChange() {
  await booted;
  if (state.foreign) return;
  seen = location.hash;
  const address = readDeskHash(seen);
  if (foreignProject(bound, address)) {
    enterForeign();
    return;
  }
  const language = setAppearance(readPreferences(seen, locale()));
  const opened = await navigate(navigationChange(lastWritten, address), address);
  if (language && !opened) await reread();
  remember();
}

//: The first hash is applied like any other, against a desk that has written none.
async function start(address) {
  await navigate(navigationChange(readDeskHash(""), address), address);
  remember();
}

//: Embed mode (spec 4.5.5), decided once, at load. Only a framed window whose hash asks for it
//: reads the project claim. A claim that names another project than the one the desk bound to
//: ends the desk (spec 4.5.1): it is open for another project, and says so. The desk embeds
//: only if the claim repeats the hash's project and names a hub origin of the exact grammar.
//: Any other answer, a refusal, or no route at all leaves it off, and the hash the desk keeps
//: then says no `embed`. The hub is told where the desk stands at once, and again at each change.
async function enterEmbed(address) {
  const framed = window.parent !== window;
  if (!embedAsked({framed, address})) return;
  let claim = null;
  try {
    claim = await readJson(READS.project());
  } catch (_error) {
    claim = null;
  }
  if (state.foreign) return;
  if (claimNamesAnotherProject(bound, claim)) {
    enterForeign();
    return;
  }
  const origin = embedTarget({framed, address, claim});
  if (origin === null) return;
  embedded = Object.freeze({origin});
  remember();
  announce();
}

//: The page's language is the address's (`#lang=ru`), and without a choice the page's own
//: `lang` stands. The platform's language is not asked for here or in the hash module: the
//: source guards keep that question in the transport and the Studio's boot module, and the
//: hub always says `lang` when it mounts a desk.
function boot() {
  seen = location.hash;
  const address = readDeskHash(seen);
  paintAppearance(readPreferences(seen, document.documentElement.lang));
  door = createTransport(locale);
  bound = address.project;
  window.addEventListener("hashchange", onHashChange);
  if (address.projectRepeated) {
    enterForeign();
    return;
  }
  booted = load().then(() => start(address));
  enterEmbed(address);
}

if (byId("deskShell") && MOUNTS.every((id) => byId(id))) boot();
