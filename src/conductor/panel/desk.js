"use strict";
// Boot module of the desk: it stands the regions of spec 5.1 on the page, reads what
// feeds them, and says on each the phase of the read that fed it.
//
// The regions are the five mounts of `desk.html`. Each stands in a machine word, one of the
// seven a state may hold, and the top bar says the whole of it in one plain sentence. The
// rail is drawn from the project's task list and the runs list, and from the automation of
// the newest run of each task, because the word of a task is a fact of all three (spec
// 5.2.1). The scene, the feed, the summary's numbers and the pult still have no module:
// they stay `empty` until one is written.
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
import {focusTarget, restoreFocus} from "./studio-focus.js";
import {mountRail} from "./desk-rail.js";

//: The reads the desk makes, each named for the route it asks. A route is only ever
//: `path.<name>` of the transport module.
const READS = Object.freeze({
  tasks: () => path.tasks(),
  runs: () => path.runs(),
  automation: (runId) => path.automation(runId),
});
//: The five mounts, in reading order. A mount no module fills stays in the word `empty`.
const MOUNTS = Object.freeze(["deskRail", "deskScene", "deskFeed", "deskSummary", "deskPult"]);
//: What a list stands at before a read and while one is out, and after a read that brought
//: nothing usable: a phase and no rows.
const NONE = Object.freeze([]);
const NOT_READ = Object.freeze({phase: "empty", list: NONE});
const READING = Object.freeze({phase: "loading", list: NONE});
const UNUSABLE = Object.freeze({phase: "failed", list: NONE});
//: What the transport answers when the wire gave no answer at all: the read was
//: abandoned at its deadline, or the request could not be made. Any other answer
//: is the server's own refusal.
const UNANSWERED = Object.freeze([LATE, "store_error"]);

//: The phase a failed read puts its region in.
function phaseOf(error) {
  const code = error instanceof Error ? error.message : "store_error";
  return UNANSWERED.includes(code) ? "failed" : "refused";
}

//: The one word for a set of phases: the worst of them, and `ready` when none is worse.
function worst(phases) {
  for (const word of ["failed", "refused", "loading", "empty"]) {
    if (phases.includes(word)) return word;
  }
  return "ready";
}

(() => {
  const shell = document.getElementById("deskShell");
  if (!shell) return;
  const byId = (id) => document.getElementById(id);
  //: The page's own language is the language of record: `<html lang>` says it,
  //: and anything but Russian is read as English. The address may choose one
  //: (`#lang=ru`), and without a choice the page's own `lang` stands; the
  //: browser's language as a default arrives with the hash module, which is the
  //: one place allowed to ask the platform for it.
  document.documentElement.lang = readPreferences(location.hash,
    document.documentElement.lang).locale;
  const locale = () => (document.documentElement.lang === "ru" ? "ru" : "en");
  const {readJson} = createTransport(locale);
  //: What a landed read is kept in: the two lists, the automation read for the newest run
  //: of each task (a map that is built once and never changed), and the task chosen.
  let state = Object.freeze({tasks: NOT_READ, runs: NOT_READ, automation: new Map(),
    taskId: null});

  function mark(node, phase) {
    node.setAttribute("data-state", phase);
  }

  //: Every word the page itself carries is a catalogue key: `data-i18n` is the
  //: text of a node and `data-i18n-label` its accessible name.
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

  //: The word of each region a read feeds, and the shell's, which is the worst of them.
  //: The rail needs both lists and the summary needs the runs.
  function words() {
    const rail = worst([state.tasks.phase, state.runs.phase]);
    return {rail, summary: state.runs.phase, shell: worst([rail, state.runs.phase])};
  }

  function render() {
    const held = focusTarget();
    const said = words();
    mountRail(byId("deskRail"), {locale: locale(), phase: said.rail, tasks: state.tasks,
      runs: state.runs, automation: state.automation, taskId: state.taskId}, handlers);
    mark(byId("deskRail"), said.rail);
    mark(byId("deskSummary"), said.summary);
    mark(shell, said.shell);
    say(said.shell);
    restoreFocus(shell, held);
  }

  function move(patch) {
    state = Object.freeze({...state, ...patch});
    render();
  }

  //: One list read, judged by the boundary that owns the list's shape. A body the
  //: boundary cannot read is a read that FAILED, however healthy the answer looked.
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

  //: The automation of the newest run of each readable task, as the hub reads it, so one
  //: task is never named two ways. A read that fails is `null`, which the rules take as
  //: "not read" and skip the rows that need it.
  async function readAutomation(tasks, runs) {
    const found = new Map();
    if (tasks.phase !== "ready" || runs.phase !== "ready") return found;
    const newest = tasks.list.filter((task) => !task.unreadable)
      .map((task) => [task.task_id, newestRun(runs, task.task_id)])
      .filter(([, latest]) => latest.state === "known");
    async function readOne(taskId, latest) {
      try {
        found.set(taskId, await readJson(READS.automation(latest.row.run_id)));
      } catch (_error) {
        found.set(taskId, null);
      }
    }
    await Promise.all(newest.map(([taskId, latest]) => readOne(taskId, latest)));
    return found;
  }

  async function load() {
    move({tasks: READING, runs: READING});
    const [tasks, runs] = await Promise.all([readTasks(), readRuns()]);
    move({tasks, runs, automation: await readAutomation(tasks, runs)});
  }

  //: What a press MEANS. Choosing a task is remembering which one; it reads nothing and
  //: writes nothing.
  const handlers = Object.freeze({
    chooseTask: (taskId) => move({taskId}),
  });

  translate();
  load();
})();
