"use strict";
// The Desk's selected task and run are already read and fenced by desk.js.
// Adapt those facts to the existing Studio run reader without granting a new
// write door: its step, document and decision controls stay visibly disabled.
import {mountRuns} from "./studio-runs.js";
import {element} from "./command-view.js";
import {localize} from "./studio-i18n.js";

export function createRunHost({mount, locale, selectRun, refreshRuns}) {
  let open = false, disposed = false;
  const heading = element("h2"), note = element("p", {className: "desk-run__note"});
  const body = element("div");
  function show(value) {
    if (disposed || open === value) return;
    open = value;
    if (!open) mount.replaceChildren();
  }
  function render(desk, connection) {
    if (disposed || !open) return;
    if (!mount.contains(body)) mount.replaceChildren(heading, note, body);
    heading.textContent = localize({locale: locale()}, "desk.run");
    note.textContent = localize({locale: locale()}, "desk.run.read_only");
    const selectedId = desk.run.detail?.run?.run_id ?? null;
    const state = {locale: locale(), connection, readOnly: true,
      tasks: {selectedId: desk.taskId},
      runs: {phase: desk.runs.phase, list: desk.runs.list,
        selectedId, detail: desk.run.detail}};
    mountRuns(body, state, {
      selectRun: (runId) => selectRun(runId),
      refreshRuns: () => refreshRuns(),
    });
  }
  function dispose() {
    disposed = true;
    open = false;
    mount.replaceChildren();
  }
  return Object.freeze({show, render, isOpen: () => open, dispose});
}
