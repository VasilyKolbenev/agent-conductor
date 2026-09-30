"use strict";
// Boot module of the desk: it stands the regions of spec 5.1 on the page, reads what
// feeds them, and says on each the phase of the read that fed it.
//
// The regions are the five mounts of `desk.html`. Each stands in a machine word, one of the
// seven a state may hold, and the top bar says the whole of it in one plain sentence. The
// rail is drawn from the project's task list and the runs list, and from the automation of
// the newest run of each task, because the word of a task is a fact of all three (spec
// 5.2.1). The scene is drawn from the newest run of the task a person chose, or from the run
// the address names: choosing is a press or a hash, and the run is a read. The pult draws the
// name of the person at this page (held here, in the page's memory), the project queue once a
// read of it is wired (none is yet) and, in a project the claim says is in `view`, the lines
// that say so. The feed is drawn from the run the scene is drawn from and stands in the word the
// scene stands in. The summary is drawn from the lists, the automation of each task's newest run
// and the reads that say which tasks were closed, and from the run on the scene; it stands in the
// word of the runs read and is drawn when its numbers are known.
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
// a READ and through nothing else, and this module writes nothing at all.
//
// The desk binds to its project before it reads anything else (spec 4.5.1): the first read
// of every window is the project claim, with the project of the hash when there is one, and
// the lists are read only after it has answered. The project the doors claim from then on is
// the hash's, or else the one the server named; the header itself is the transport's, which
// this module never names. A claim that names another project than the bound one, and a
// refusal `project_mismatch` from any read, end the desk in its terminal state, which seals
// the transport. A claim read that fails any other way binds nothing new: the desk runs on
// what its hash said, and the header it then sends is what guards each request. The mode the
// claim names is the desk's mode in every window. In embed mode (spec 4.5.5), decided from
// that same claim, it says its location to the hub, in one message, and listens to nothing
// the hub posts.
import {LATE, createTransport, path} from "./desk-transport.js";
import {message} from "./studio-i18n.js";
import {deskHash, foreignProject, navigationChange, preferenceHash, readDeskHash,
  readPreferences} from "./desk-hash.js";
import {announceLocation, claimNamesAnotherProject, embedTarget,
  projectOf} from "./desk-embed.js";
import {projectTasks} from "./studio-tasks-model.js";
import {projectRuns} from "./studio-model.js";
import {newestRun} from "./studio-taskruns.js";
import {frozenCopy} from "./studio-draft.js";
import {projectRunRead} from "./studio-situation.js";
import {projectControls, wireControls} from "./studio-controls.js";
import {focusTarget, restoreFocus} from "./studio-focus.js";
import {mountRail} from "./desk-rail.js";
import {mountScene} from "./desk-scene.js";
import {mountFeed} from "./desk-feed.js";
import {mountSummary} from "./desk-summary.js";
import {mountPult} from "./desk-pult.js";
import {readClosing} from "./desk-closing.js";
import {flagBody, flagLine, initialMarks, resumableRuns} from "./desk-flag-model.js";
import {createFlagDoor} from "./desk-flag.js";

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
//: them. Each has a module that fills it; one whose read gave nothing to draw stays in the word
//: `empty`.
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
//: The refusal that says this server serves another project (spec 4.5.1).
const MISMATCH = "project_mismatch";

//: What a landed read is kept in: the two lists, the automation read for the newest run of
//: each task (a map that is built once and never changed), the task chosen, and the run drawn
//: for it; `foreign` is the terminal state of a desk open for another project. `choice`
//: counts the choices made, so an answer that lands for a task a person has since left is
//: dropped. `door` is this window's transport, made at boot.
//:
//: The console's facts: `actor` is the name of the person at this page (null until given),
//: `editing` says the form that asks for it is open, and `draft` is what was typed into that
//: form and not saved (null: nothing typed since it opened) -- all three live in this page's
//: memory only, and the draft is what a redraw draws back into the field; `mode` is what the
//: project claim said (`active`, `view`, or null when no claim was read or it named no mode
//: this build knows); `queue` is the task-queue read once one is wired (null: not read);
//: `closing` is the digest of the newest finished run of each task that could have been
//: accepted, by task id (null until those reads have landed).
//:
//: The continue-after block's memory is `flag` (spec 5.8): null where there is no block (a desk
//: nobody framed, or one whose read of the flag gave no record this desk can vouch for);
//: otherwise `record` is the flag the server holds, `draft` what a person changed and did not
//: save (null: nothing), `open` says the block is open, `saving` a write is out, and `refused`
//: is the code of the last refusal (or `unknown`).
let state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
  taskId: null, run: NO_RUN, foreign: false, actor: null, editing: false, draft: null,
  refused: false, mode: null, queue: null, flag: null, closing: null});
let choice = 0;
let door = null;
let flagDoor = null;
//: The project this desk is bound to: the one its first hash named, or else the one the claim
//: named (null when neither named one), and what the doors claim from then on. `hashProject`
//: is only what the first hash named: it is what the address the desk writes says, so a project
//: learned from the server is never written into an address the hub did not write. The last
//: address the desk wrote, which a new hash is compared with; the hash it last wrote or read;
//: what was last remembered; and the promise that the claim has answered, the lists have landed
//: and the first hash has been applied. `embedded` is the hub origin when embed mode is in force
//: (null when it is not), and `announced` is the location the hub was last told.
let bound = null;
let hashProject = null;
let lastWritten = readDeskHash("");
let seen = "";
let shown = Object.freeze({task: null, run: null});
let booted = Promise.resolve();
let embedded = null;
let announced = null;
//: Whether the address has asked for the continue-after block (`panel=continue`), which a read of
//: the flag still to land must then open.
let wantContinue = false;

const byId = (id) => document.getElementById(id);
//: The page's own language is the language of record: `<html lang>` says it, and anything
//: but Russian is read as English.
const locale = () => (document.documentElement.lang === "ru" ? "ru" : "en");
//: The one read of this module. A refusal `project_mismatch` from any answer ends the desk
//: (spec 4.5.1) before the caller hears of it; the caller then finds a terminal desk, which
//: keeps nothing a late answer brings.
async function readJson(target) {
  try {
    return await door.readJson(target);
  } catch (error) {
    if (error instanceof Error && error.message === MISMATCH) enterForeign();
    throw error;
  }
}

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

//: What the console draws of the block: the memory above, the runs the desk may offer from what
//: it already holds, what the controls say now (a person's change, else the flag the server holds)
//: and the line the record reads as.
function flagView() {
  const {flag} = state;
  if (flag === null) return null;
  const rows = resumableRuns({tasks: state.tasks, runs: state.runs, automation: state.automation});
  const {record} = flag;
  const form = flag.draft ?? Object.freeze({enabled: record.enabled,
    marked: initialMarks(record, rows), queue: record.enabled && record.start_task_queue});
  return Object.freeze({...flag, rows, form, line: flagLine(flag.record)});
}

function render() {
  const held = focusTarget();
  const said = words();
  const view = {locale: locale(), listed: said.rail === "ready", tasks: state.tasks,
    runs: state.runs, automation: state.automation, taskId: state.taskId, run: state.run,
    connection: NO_STREAM, task: state.tasks.list.find((row) => row.task_id === state.taskId) ?? null,
    foreign: state.foreign, actor: state.actor, editing: state.editing, draft: state.draft,
    refused: state.refused, mode: state.mode, queue: state.queue, flag: flagView(),
    closing: state.closing};
  mountRail(byId("deskRail"), view, handlers);
  mountScene(byId("deskScene"), view, handlers);
  mountFeed(byId("deskFeed"), view);
  mountSummary(byId("deskSummary"), view);
  mountPult(byId("deskPult"), view, handlers);
  byId("deskPlate").hidden = state.mode !== "view" || state.foreign;
  mark(byId("deskRail"), said.rail);
  mark(byId("deskScene"), said.scene);
  mark(byId("deskFeed"), said.scene);
  mark(byId("deskPult"), state.foreign ? "empty" : "ready");
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
  const panel = state.flag !== null && state.flag.open ? "continue" : null;
  const address = preferenceHash(
    deskHash({project: hashProject, embed, task: at.task, run: at.run, panel}),
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

//: The lists, the automation of each task's newest run, and, beside them, the reads that say
//: which tasks were closed (`desk-closing.js`): the rail is drawn when its words are known and
//: the summary when its numbers are.
async function load() {
  move({tasks: READING, runs: READING});
  const [tasks, runs] = await Promise.all([readTasks(), readRuns()]);
  const closing = readClosing({read: (runId) => readJson(READS.run(runId)), tasks, runs,
    stopped: () => state.foreign});
  move({tasks, runs, automation: await readAutomation(tasks, runs)});
  move({closing: await closing});
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

//: The name of a person, in the grammar every id of the routes has: it is what the routes will
//: take as an actor, so the desk refuses here what they would refuse there.
const ACTOR = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

//: Put the keyboard where a press that replaced its own control means it to be.
function focusOn(key) {
  byId("deskPult").querySelector(`[data-focus-key="${key}"]`)?.focus();
}

function editActor() {
  if (state.foreign) return;
  move({editing: true});
  focusOn("pult:actor-name");
}

function cancelActor() {
  if (state.foreign) return;
  move({editing: false, draft: null, refused: false});
  focusOn("pult:actor-change");
}

//: Hold the words typed into the form so far. A redraw of the page -- a task chosen, a language
//: set, a read landing -- rebuilds the form from the state, and the state is what holds them.
//: Nothing is drawn: the field already shows what was typed. A keystroke also ends the refusal
//: the form may be saying: the words are new. Page memory only, like the name.
function typeActor(text) {
  if (state.foreign || !state.editing || typeof text !== "string") return;
  state = Object.freeze({...state, draft: text, refused: false});
}

//: Keep the name of the person at this page, or say it was refused. It is held in this page's
//: memory and nowhere else: no storage, no address, no request. A refused name leaves the words
//: typed where they are, and the refusal is remembered (the form says it again after every
//: redraw, until a keystroke or a cancel ends it); a kept one, like a cancel, ends them, so the
//: form always opens on the name that stands.
function setActor(name) {
  if (state.foreign || typeof name !== "string") return false;
  if (!ACTOR.test(name)) {
    state = Object.freeze({...state, refused: true});
    return false;
  }
  move({actor: name, editing: false, draft: null, refused: false});
  focusOn("pult:actor-change");
  return true;
}

// -- the continue-after block -----------------------------------------------------------

function patchFlag(changes) {
  if (state.foreign || state.flag === null) return;
  move({flag: Object.freeze({...state.flag, ...changes})});
}

//: A change a person made to one control of the block. It is kept, and drawn from the next
//: redraw on; nothing is drawn now, because the control already shows it.
function draftFlag(change) {
  if (state.foreign || state.flag === null) return;
  const {form} = flagView();
  let marked = form.marked;
  if ("run" in change) {
    const others = marked.filter((id) => id !== change.run);
    marked = change.on ? [...others, change.run] : others;
  }
  const draft = Object.freeze({enabled: "enabled" in change ? change.enabled : form.enabled,
    marked: Object.freeze(marked), queue: "queue" in change ? change.queue : form.queue});
  state = Object.freeze({...state, flag: Object.freeze({...state.flag, draft, refused: null})});
}

//: Whether the block is open is kept for the next redraw, and said in the address (spec 4.5.2:
//: `panel=continue`); nothing is drawn now, because a person opening it has done that.
function openFlag(open) {
  if (state.foreign || state.flag === null || state.flag.open === open) return;
  state = Object.freeze({...state, flag: Object.freeze({...state.flag, open})});
  remember();
}

//: The address says `panel=continue` (spec 4.5.3, 5.8): open the block and put the keyboard in it
//: -- at once if it stands, and when the read of the flag lands if it does not. This only
//: selects and focuses: nothing is written.
function showContinue() {
  wantContinue = true;
  if (state.flag === null) return;
  move({flag: Object.freeze({...state.flag, open: true})});
  focusOn("flag:summary");
  remember();
}

//: A save that is not a record to keep. A refusal is said in place with its code. A save this
//: desk cannot vouch for is said so, and the flag is read again: what the server holds is what
//: the line of the block says.
async function unconfirmed(done) {
  if (done.status === "refused") {
    patchFlag({saving: false, refused: done.code});
    return;
  }
  const record = await flagDoor.read();
  patchFlag(record === null ? {saving: false, refused: "unknown"}
    : {record, saving: false, refused: "unknown"});
}

//: The one write of the block, in the name of the person at this page: the runs marked, in the
//: order of the list, and the queue start. It waits for a name and for the save before it.
async function writeFlag(enabled) {
  const view = flagView();
  if (view === null || state.foreign || state.actor === null || view.saving) return;
  const runIds = view.rows.filter((row) => view.form.marked.includes(row.run_id))
    .map((row) => row.run_id);
  patchFlag({saving: true});
  const done = await flagDoor.save(
    flagBody({enabled, actor: state.actor, runIds, startQueue: view.form.queue}));
  if (state.foreign) return;
  if (done.status === "saved" && done.flag !== null) {
    patchFlag({record: done.flag, draft: null, saving: false, refused: null});
  } else await unconfirmed(done);
}

const saveFlag = () => writeFlag(flagView()?.form.enabled ?? false);
const clearFlag = () => writeFlag(false);

//: The read of the flag, made once by a desk a hub frames: a record it can vouch for makes the
//: block; anything else leaves the console without one.
async function loadFlag() {
  const record = await flagDoor.read();
  if (record === null || state.foreign) return;
  move({flag: Object.freeze({record, draft: null, open: wantContinue, saving: false,
    refused: null})});
  if (wantContinue) {
    focusOn("flag:summary");
    remember();
  }
}

//: The one way out of the terminal state: the page is loaded again and binds afresh.
function reload() {
  location.reload();
}

const handlers = Object.freeze({chooseTask, editActor, cancelActor, typeActor, setActor, reload,
  draftFlag, openFlag, saveFlag, clearFlag});

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
//: dropped, the door is sealed (the token is forgotten, the stream closed, no read or write is
//: made again), a plate says so with the one way out, and `move` keeps nothing from then on.
function enterForeign() {
  if (state.foreign) return;
  door.seal();
  state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
    taskId: null, run: NO_RUN, foreign: true, actor: null, editing: false, draft: null,
    refused: false, mode: null, queue: null, flag: null, closing: null});
  render();
}

//: The selection steps: the task and its run. A task the lists do not hold, or a run with no
//: task to belong to, is dropped. Says whether it opened a run.
async function navigateSelection(keys, address) {
  if (!keys.includes("task") && !keys.includes("run")) return false;
  const taskId = keys.includes("task") ? address.task : state.taskId;
  if (taskId === null || !state.tasks.list.some((row) => row.task_id === taskId)) return false;
  await chooseTask(taskId, keys.includes("run") ? address.run : null);
  return true;
}

//: The address no longer asks for the block: a task changed and the same hash carries no panel
//: (spec 4.5.3, step 2.1), or it names a panel other than `continue`. The block closes, and a read
//: of the flag still to land opens nothing, so `remember` has no `panel` left to write back.
function closeContinue() {
  wantContinue = false;
  if (state.flag === null || !state.flag.open) return;
  move({flag: Object.freeze({...state.flag, open: false})});
}

//: Apply the steps of a hash the desk did not write, top to bottom. The task and its run, and
//: the one panel the desk has a surface for, `continue`, are the only navigation it has today
//: (the wizard and the other panels come with their modules), so no other step has a row here;
//: a panel step that names another panel closes the block, since one panel is open at a time. A
//: changed task resets the panel with it, before its run is read (spec 4.5.3, step 2.1). The
//: panel step follows the selection, as in spec 4.5.3. Says whether it opened a run.
async function navigate(change, address) {
  const keys = change.steps.map((step) => step.key);
  if (change.reset.includes("panel")) closeContinue();
  const opened = await navigateSelection(keys, address);
  if (!keys.includes("panel")) return opened;
  if (address.panel === "continue") showContinue();
  else closeContinue();
  return opened;
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

//: The mode the server's claim names: the only source of it (spec 4.5.1). A claim that names
//: none this build knows, or no claim at all, is no mode -- never a guess of `active`.
function claimMode(claim) {
  const mode = claim !== null && typeof claim === "object" ? claim.mode : null;
  return mode === "active" || mode === "view" ? mode : null;
}

//: The first read of every window (spec 4.5.1): the project claim. The claim, or null when
//: the read gave none (a refusal, a route that is not there, no answer). A `project_mismatch`
//: has ended the desk by now, in `readJson`.
async function readClaim() {
  try {
    return await readJson(READS.project());
  } catch (_error) {
    return null;
  }
}

//: Whether the claim ends the desk: the hash named a project and the claim names another
//: (an id that differs, or none), which is the claim being wrong for this window. A window
//: whose hash named none binds to what the claim names, `null` included; a claim that names
//: nothing usable binds nothing and ends nothing.
function bindToClaim(address, claim) {
  if (address.project !== null) return !claimNamesAnotherProject(bound, claim);
  const named = projectOf(claim);
  if (typeof named === "string") bound = named;
  return true;
}

//: Embed mode (spec 4.5.5), decided once, from the claim the window already read. The desk
//: embeds only if the window is framed, its hash asks for it and names a project, and the claim
//: repeats that project and names a hub origin of the exact grammar. Any other answer leaves it
//: off, and the hash the desk keeps then says no `embed`. The hub is told where the desk stands
//: at once, and again at each change.
function enterEmbed(address, claim) {
  const origin = embedTarget({framed: window.parent !== window, address, claim});
  if (origin === null) return;
  embedded = Object.freeze({origin});
  remember();
  announce();
}

//: The boot of the data (spec 4.5.1): the claim first, and everything else only after it has
//: answered. A desk the claim ended reads nothing more.
async function settle(address) {
  const claim = await readClaim();
  if (state.foreign) return;
  if (!bindToClaim(address, claim)) {
    enterForeign();
    return;
  }
  const mode = claimMode(claim);
  if (mode !== null) move({mode});
  enterEmbed(address, claim);
  if (embedded !== null) loadFlag();
  await load();
  await start(address);
}

//: The page's language is the address's (`#lang=ru`), and without a choice the page's own
//: `lang` stands. The platform's language is not asked for here or in the hash module: the
//: source guards keep that question in the transport and the Studio's boot module, and the
//: hub always says `lang` when it mounts a desk.
function boot() {
  seen = location.hash;
  const address = readDeskHash(seen);
  paintAppearance(readPreferences(seen, document.documentElement.lang));
  bound = hashProject = address.project;
  door = createTransport(locale, () => bound);
  flagDoor = createFlagDoor(door, enterForeign);
  window.addEventListener("hashchange", onHashChange);
  if (address.projectRepeated) {
    enterForeign();
    return;
  }
  booted = settle(address);
}

if (byId("deskShell") && MOUNTS.every((id) => byId(id))) boot();
