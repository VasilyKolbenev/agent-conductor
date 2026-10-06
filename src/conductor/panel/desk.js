"use strict";
// Project-bound desk: shared transport, explicit writes through hosts, and live read refreshes.
import {LATE, createTransport, path} from "./desk-transport.js";
import {message} from "./studio-i18n.js";
import {deskHash, foreignProject, navigationChange, preferenceHash, readDeskHash,
  readPreferences} from "./desk-hash.js";
import {announceLocation, claimMode, claimNamesAnotherProject, embedTarget,
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
import {flagBody, flagLine, initialMarks, resumableRuns, runVerdicts} from "./desk-flag-model.js";
import {createFlagDoor} from "./desk-flag.js";
import {createQueueDoor} from "./desk-queue.js";
import {NO_PULT, createPultFlow} from "./desk-pult-flow.js";
import {createWizardHost} from "./desk-wizard-host.js";
import {connectDeskStream} from "./desk-stream.js";
import {createFlowHost} from "./desk-flow-host.js";
import {createPeopleHost} from "./desk-people-host.js";
import {createRunHost} from "./desk-run-host.js";
import {createRunPanelBindings} from "./desk-run-binding.js";
import {createDeskPanels} from "./desk-panels.js";
import {createToggles} from "./desk-toggles.js";
//: Route names come only from the shared transport.
const READS = Object.freeze({
  tasks: () => path.tasks(),
  runs: () => path.runs(),
  automation: (runId) => path.automation(runId),
  run: (runId) => path.run(runId),
  controls: (runId) => path.controls(runId),
  project: () => path.project(),
});
//: The five required desk mounts, in reading order.
const MOUNTS = Object.freeze(["deskRail", "deskScene", "deskFeed", "deskSummary", "deskPult"]);
//: List phases before and after a read.
const NONE = Object.freeze([]);
const NOT_READ = Object.freeze({phase: "empty", list: NONE});
const READING = Object.freeze({phase: "loading", list: NONE});
const UNUSABLE = Object.freeze({phase: "failed", list: NONE});
//: The chosen run's phases; `absent` explains a task with no run.
const NO_RUN = Object.freeze({phase: "empty", detail: null, absent: null});
const READING_RUN = Object.freeze({phase: "loading", detail: null, absent: null});
const UNUSABLE_RUN = Object.freeze({phase: "failed", detail: null, absent: null});
//: These are missing wire answers, unlike a server refusal.
const UNANSWERED = Object.freeze([LATE, "store_error"]);
//: The refusal that says this server serves another project (spec 4.5.1).
const MISMATCH = "project_mismatch";

// State belongs to this page; choice and loading epochs fence late answers.
let state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
  taskId: null, run: NO_RUN, foreign: false, actor: null, editing: false, draft: null,
  refused: false, mode: null, queue: null, flag: null, closing: null, pult: NO_PULT});
let choice = 0;
let door = null;
let flagDoor = null;
let queueDoor = null;
let pultFlow = null;
let wizardHost = null;
let stream = null, connection = "closed", loading = 0;
let selectionRead = Promise.resolve(true);
let panels = null;
// The bound project comes from the first hash or claim; only the hash's own identity is written
// back. Embedded origin and announced location belong to this page, never browser storage.
let bound = null;
let hashProject = null;
let lastWritten = readDeskHash("");
let seen = "";
let shown = Object.freeze({task: null, run: null});
let booted = Promise.resolve();
let embedded = null;
let announced = null;
//: The toggles of the top bar: a press while the boot still reads is a choice the boot keeps.
let toggles = null;
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
//: it already holds, what the controls say now (a person's change, else the flag the server holds),
//: the line the record reads as, and what became of the runs a consumed flag listed.
function flagView() {
  const {flag} = state;
  if (flag === null) return null;
  const rows = resumableRuns({tasks: state.tasks, runs: state.runs, automation: state.automation});
  const {record} = flag;
  const form = flag.draft ?? Object.freeze({enabled: record.enabled,
    marked: initialMarks(record, rows), queue: record.enabled && record.start_task_queue});
  return Object.freeze({...flag, rows, form, line: flagLine(flag.record),
    verdicts: runVerdicts(record, [...state.automation.values()])});
}

function render() {
  const held = focusTarget();
  const said = words();
  const view = {locale: locale(), listed: said.rail === "ready", tasks: state.tasks,
    runs: state.runs, automation: state.automation, taskId: state.taskId, run: state.run,
    connection, task: state.tasks.list.find((row) => row.task_id === state.taskId) ?? null,
    foreign: state.foreign, actor: state.actor, editing: state.editing, draft: state.draft,
    refused: state.refused, mode: state.mode, queue: state.queue, flag: flagView(),
    closing: state.closing, pult: state.pult};
  mountRail(byId("deskRail"), view, handlers);
  mountScene(byId("deskScene"), view, handlers);
  mountFeed(byId("deskFeed"), view);
  mountSummary(byId("deskSummary"), view);
  mountPult(byId("deskPult"), view, handlers);
  panels?.render(state, connection);
  wizardHost?.render();
  byId("deskPlate").hidden = state.mode !== "view" || state.foreign;
  mark(byId("deskRail"), said.rail);
  mark(byId("deskScene"), said.scene);
  mark(byId("deskFeed"), said.scene);
  mark(byId("deskPult"), state.foreign ? "empty" : "ready");
  mark(byId("deskSummary"), said.summary);
  mark(byId("deskShell"), said.shell);
  byId("deskShell").dataset.connection = connection;
  byId("deskConnection").textContent = message(locale(), `desk.connection.${connection}`);
  toggles?.draw(state.foreign);
  byId("deskPeople").hidden = !panels?.isOpen("people");
  byId("deskRun").hidden = !panels?.isOpen("run");
  for (const id of ["deskScene", "deskFeed", "deskSummary"])
    byId(id).hidden = Boolean(panels?.current());
  say(said.shell);
  restoreFocus(byId("deskShell"), held);
}

//: Where the desk stands: the task chosen and the run drawn for it. The run is what is on
//: the scene, so an address never names a run the desk has not drawn.
function where() {
  return Object.freeze({task: state.taskId, run: state.run.detail?.run.run_id ?? null});
}

//: What the desk's address says of what it draws, in the canonical order of `deskHash`.
function addressOf(wizardKeys) {
  const at = where();
  const embed = embedded === null ? null : "hub";
  const panel = panels?.current() ?? (state.flag !== null && state.flag.open ? "continue" : null);
  const extra = wizardKeys === undefined ? wizardHost?.hash() : wizardKeys;
  // Preparation names the wizard's task. Until its run link has landed, a previously
  // selected run in the scene must not be paired with that new task in the address.
  const run = extra?.prepare === "1" ? null : at.run;
  return preferenceHash(
    deskHash({project: hashProject, embed, task: at.task, run, panel, ...extra}),
    {locale: locale(), theme: document.documentElement.getAttribute("data-theme")});
}

//: The one place the desk moves its own address (spec 4.5.3, point 4): the selection it
//: draws, then the appearance, in the canonical order of `deskHash`. A terminal desk writes
//: nothing. `replaceState` adds no history entry and fires no `hashchange`, so this can
//: never start a loop, and the address it leaves is the one a new hash is compared with.
//: A hash the router has not read yet is a request, and is not overwritten: the router
//: that reads it normalises it.
function remember(wizardKeys) {
  if (state.foreign || location.hash !== seen) return;
  const address = addressOf(wizardKeys);
  history.replaceState(null, "", address);
  seen = location.hash;
  lastWritten = readDeskHash(address);
  shown = where();
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

//: The reads that say which tasks were closed (`desk-closing.js`) are one run read per finished
//: task in every `load` (the boot's, each full refresh the stream asks for, the run panel's
//: refresh, the wizard's exit) and may take as long as a read may (`READ_DEADLINE`). Only the
//: summary needs their answer, so nothing waits for them: not the scene of the task an address
//: names, not the hash that comes next. The answer is kept when it lands, unless the desk has
//: ended by then (`move` keeps nothing for one that has).
function learnClosing(reads, current) {
  reads.then((found) => { if (current()) move({closing: found}); });
}

//: The lists and the automation of each task's newest run, which the rail's words are made of, so
//: the desk is settled when they have landed. The reads that say which tasks were closed are
//: started beside them and are not waited for (`learnClosing`): the summary is drawn when its
//: numbers are known.
async function load(fresh = () => true, background = false) {
  const epoch = ++loading;
  const current = () => !state.foreign && epoch === loading && fresh();
  if (!background) move({tasks: READING, runs: READING});
  const [tasks, runs, queue] = await Promise.all([readTasks(), readRuns(), queueDoor.read()]);
  if (!current()) return false;
  const automation = await readAutomation(tasks, runs);
  if (!current()) return false;
  learnClosing(readClosing({read: (runId) => readJson(READS.run(runId)), tasks, runs,
    stopped: () => !current()}), current);
  move({tasks, runs, queue, automation});
  return tasks.phase === "ready" && runs.phase === "ready";
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
function chooseTask(...args) {
  selectionRead = readChoice(...args);
  return selectionRead;
}

async function readChoice(taskId, runId = null, fresh = () => true) {
  if (state.foreign || !fresh()) return false;
  const asked = ++choice;
  const newest = newestRun(state.runs, taskId);
  const absent = absence(state.tasks.list.find((row) => row.task_id === taskId), newest,
    runId !== null);
  if (absent !== null) {
    move({taskId, run: Object.freeze({phase: "empty", detail: null, absent})});
    return true;
  }
  move({taskId, run: whileReading(taskId)});
  const landed = await readRun(runId ?? newest.row.run_id, taskId);
  if (asked !== choice || state.foreign || !fresh()) return false;
  move({run: landed});
  return landed.phase === "ready";
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
  wizardHost?.actor(name);
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
//: `panel=continue`); nothing is drawn now, because a person opening it has done that. While the
//: boot reads, opening or closing it is the person's last choice (`desk-toggles.js`).
function openFlag(open) {
  if (state.foreign || state.flag === null || state.flag.open === open) return;
  if (open) panels?.open(null);
  state = Object.freeze({...state, flag: Object.freeze({...state.flag, open})});
  toggles.choose(open ? "continue" : null);
  remember();
}

//: The address says `panel=continue` (spec 4.5.3, 5.8): open the block and put the keyboard in it
//: -- at once if it stands, and when the read of the flag lands if it does not. This only
//: selects and focuses: nothing is written. A block the person opened themselves is not a request
//: of the address, so the keyboard is left where it is (`focus` false).
function showContinue(focus) {
  panels?.open(null);
  wantContinue = true;
  if (state.flag === null) return;
  move({flag: Object.freeze({...state.flag, open: true})});
  if (focus) focusOn("flag:summary");
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

//: The presses of the queue block go to the console's hands (`desk-pult-flow.js`), made at boot.
const press = (name) => (...args) => pultFlow[name](...args);

const handlers = Object.freeze({chooseTask, editActor, cancelActor, typeActor, setActor, reload,
  draftFlag, openFlag, saveFlag, clearFlag, orderEntry: press("order"),
  withdrawEntry: press("withdraw"), openRelease: press("openRelease"),
  closeDialog: press("closeDialog"), release: press("release"),
  openSkip: press("openSkip"), skip: press("skip"),
  openConfirm: press("openConfirm"), confirm: press("confirm")});

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
  panels?.refresh();
  render();
  return language;
}

//: The terminal state of a desk open for another project (spec 4.5.1): everything it holds is
//: dropped, the door is sealed (the token is forgotten, the stream closed, no read or write is
//: made again), a plate says so with the one way out, and `move` keeps nothing from then on.
function enterForeign() {
  if (state.foreign) return;
  loading += 1;
  choice += 1;
  stream?.dispose();
  panels?.dispose();
  connection = "closed";
  door.seal();
  state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
    taskId: null, run: NO_RUN, foreign: true, actor: null, editing: false, draft: null,
    refused: false, mode: null, queue: null, flag: null, closing: null, pult: NO_PULT});
  wizardHost?.dispose();
  render();
}

async function wizardExited({taskId, runId}) {
  await load();
  if (!state.foreign) await chooseTask(taskId, runId);
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

//: Show the panel a hash or a press chose: the continue-after block, a centre panel, or neither.
//: `focus` is whether the address asked for it, and not the person's own choice.
function showPanel(panel, focus) {
  if (panel === "continue") showContinue(focus);
  else closeContinue();
  if (toggles.names.includes(panel)) panels?.open(panel);
}

//: Apply the task/run selection before its panel and wizard (spec 4.5.3). `panelOf` gives the panel
//: to show once the selection has been read: the address's, and for the first hash the person's
//: last choice while the desk booted (a toggle or the continue-after block), if they chose. A
//: centre panel is closed for a hash that names another one or moves the task and names none, and
//: for no other: a hash that moves only the language or the run leaves what the person opened.
async function navigate(change, address, panelOf = (named) => named) {
  const keys = change.steps.map((step) => step.key);
  const reset = change.reset.includes("panel");
  if (reset) closeContinue();
  if ((reset || keys.includes("panel")) && address.panel !== panels?.current()) panels?.open(null);
  const opened = await navigateSelection(keys, address);
  const panel = panelOf(address.panel);
  if (keys.includes("panel") || panel !== address.panel) showPanel(panel, panel === address.panel);
  await wizardHost?.navigate(change, address);
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
//: alone. It selects, reads and sets the appearance, and writes nothing. A hash that arrives while
//: the desk boots is ordered with the person's presses by `toggles.hear`, and applied after it.
async function onHashChange() {
  const ticket = toggles.hear(readDeskHash(location.hash));
  await booted;
  if (state.foreign) return;
  seen = location.hash;
  const address = readDeskHash(seen);
  if (foreignProject(bound, address)) {
    enterForeign();
    return;
  }
  const language = setAppearance(readPreferences(seen, locale()));
  const change = toggles.after(ticket, navigationChange(lastWritten, address));
  const opened = await navigate(change, address);
  if (language && !opened) await reread();
  remember();
}

//: The first hash is applied like any other, against a desk that has written none -- which has
//: nothing to reset, so a block a person opened while the lists were read is not the hash's to
//: close. A hash that arrived meanwhile is not overwritten: it is compared with what is drawn.
async function start(address) {
  const first = navigationChange(readDeskHash(""), address);
  await navigate(Object.freeze({...first, reset: NONE}), address, toggles.resolve);
  lastWritten = readDeskHash(addressOf());
  remember();
}

//: Read the project claim first; a mismatch has already ended the desk.
async function readClaim() {
  try {
    return await readJson(READS.project());
  } catch (_error) {
    return null;
  }
}

//: Bind an unnamed address to the claim; refuse a conflicting named address.
function bindToClaim(address, claim) {
  if (address.project !== null) return !claimNamesAnotherProject(bound, claim);
  const named = projectOf(claim);
  if (typeof named === "string") bound = named;
  return true;
}

//: Embed only when the frame, address and claim agree (spec 4.5.5).
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
  toggles.finish();
  render();
  startStream();
}

async function refreshStream({current}) {
  if (!await load(current, true) || !current()) return false;
  while (current()) {
    const pending = selectionRead;
    await pending;
    if (!current()) return false;
    if (pending !== selectionRead) continue;
    if (state.taskId === null) return true;
    const fresh = chooseTask(state.taskId, where().run, current);
    const confirmed = await fresh;
    if (fresh !== selectionRead) continue;
    return confirmed && current();
  }
  return false;
}

function startStream() {
  if (state.foreign || stream !== null) return;
  stream = connectDeskStream({door, refresh: refreshStream, onForeign: enterForeign,
    onConnection: (value) => { connection = value; panels?.connection(value === "open");
      render(); }});
}

function stopStream() {
  panels?.suspend();
  stream?.dispose();
  stream = null;
  loading += 1;
  choice += 1;
  connection = "closed";
}

function boot() {
  seen = location.hash;
  const address = readDeskHash(seen);
  paintAppearance(readPreferences(seen, document.documentElement.lang));
  bound = hashProject = address.project;
  door = createTransport(locale, () => bound);
  flagDoor = createFlagDoor(door, enterForeign);
  queueDoor = createQueueDoor(door, enterForeign);
  pultFlow = createPultFlow({door: queueDoor,
    host: {state: () => state, move, nonce: () => crypto.randomUUID()}});
  const people = createPeopleHost({mount: byId("deskPeople"), pult: byId("deskPult"), door,
    locale, onForeign: enterForeign});
  const runBinding = createRunPanelBindings({state: () => state,
    connection: () => connection, choice: () => choice, where, load, chooseTask});
  const run = createRunHost({mount: byId("deskRun"), pult: byId("deskPult"), locale, door,
    ...runBinding, onChange: render, onForeign: enterForeign,
    openRun: () => panels?.open("run")});
  panels = createDeskPanels({flowMount: byId("deskFlow"), people, run,
    createFlow: () => createFlowHost({mount: byId("deskFlow"), door, locale,
      nonce: crypto.randomUUID().replaceAll("-", ""), onForeign: enterForeign}),
    allowed: () => !state.foreign, onChange: render});
  toggles = createToggles({byId, panels, closeContinue, remember, render, first: address,
    moves: navigationChange});
  wizardHost = createWizardHost({mount: byId("deskWizard"), trigger: byId("deskNewTask"),
    door, locale, nonce: () => crypto.randomUUID(), onForeign: enterForeign,
    onState: () => { render(); remember(); }, onHash: remember, onExit: wizardExited});
  wizardHost.bind({actor: () => state.actor, mode: () => state.mode,
    tasks: () => state.tasks.list, foreign: () => state.foreign, applied: toggles.applied});
  wizardHost.render();
  window.addEventListener("pagehide", stopStream);
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) { panels?.resume(); startStream(); }
  });
  window.addEventListener("hashchange", onHashChange);
  if (address.projectRepeated) {
    enterForeign();
    return;
  }
  booted = settle(address);
}

if (byId("deskShell") && MOUNTS.every((id) => byId(id))) boot();
