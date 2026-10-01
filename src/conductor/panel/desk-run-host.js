"use strict";
// The Desk's selected task and run are already read and fenced by desk.js.
// Adapt those facts to Studio's run reader and its existing step/document doors.
import {mountRuns} from "./studio-runs.js";
import {mountDecisions, mountDecisionCard} from "./studio-people.js";
import {element} from "./command-view.js";
import {localize, noticeText} from "./studio-i18n.js";
import {createRunWriteHost} from "./desk-run-write-host.js";
import {createAcceptHost} from "./desk-accept-host.js";

export function createRunHost({mount, pult, locale, selectRun, refreshRuns, door,
    binding, refreshRun, onChange, onForeign, openRun}) {
  let open = false, disposed = false;
  const heading = element("h2"), note = element("p", {className: "desk-run__note"});
  const outcome = element("p", {className: "desk-run__note", role: "status"});
  const body = element("div"), decisions = element("div");
  const pultCard = element("div");
  const writer = createRunWriteHost({door, binding, refreshRun, onChange, onForeign});
  const accept = createAcceptHost({door, binding, locale, onChange, onForeign,
    openDetails: openRun});
  function show(value) {
    if (disposed || open === value) return;
    open = value;
    if (!open) mount.replaceChildren();
  }
  function render(desk, connection) {
    if (disposed) return;
    const drafted = writer.sync(desk);
    const blocked = desk.mode === "view" ? "desk.run.view_blocked"
      : desk.run.phase !== "ready" || desk.mode !== "active" ? "desk.run.not_ready"
        : writer.decisionPending() ? "desk.decision.writing" : null;
    const decisionState = {...drafted, locale: locale(), connection,
      decisionActor: desk.actor, decisionWriteBlocked: blocked};
    pult.append(pultCard);
    mountDecisionCard(pultCard, decisionState, writer.handlers);
    pult.append(accept.pult);
    accept.render(desk, open);
    if (!open) return;
    if (!mount.contains(body)) mount.replaceChildren(heading, note, outcome, body, decisions,
      accept.detail);
    heading.textContent = localize({locale: locale()}, "desk.run");
    note.textContent = localize({locale: locale()}, desk.mode === "view"
      ? "desk.run.view_blocked" : "desk.run.actions");
    const selectedId = desk.run.detail?.run?.run_id ?? null;
    const state = {...drafted, locale: locale(), connection, deskRun: true,
      runWriteBlocked: blocked,
      tasks: {selectedId: desk.taskId},
      runs: {phase: desk.runs.phase, list: desk.runs.list,
        selectedId, detail: desk.run.detail, step: drafted.runs.step,
        document: drafted.runs.document, writes: drafted.runs.writes}};
    outcome.textContent = drafted.noticeFrom === "human"
      ? noticeText(state, drafted.notice) : "";
    mountRuns(body, state, {
      selectRun: (runId) => selectRun(runId),
      refreshRuns: () => refreshRuns(),
      ...writer.handlers,
    });
    mountDecisions(decisions, {...decisionState, decisionListOnly: true,
      decisions: {...decisionState.decisions,
        draft: {...decisionState.decisions.draft,
          key: writer.historyKey() ?? decisionState.decisions.draft.key}}}, writer.handlers);
  }
  function dispose() {
    disposed = true;
    open = false;
    writer.dispose();
    accept.dispose();
    mount.replaceChildren();
    pultCard.remove();
  }
  return Object.freeze({show, render, isOpen: () => open, dispose});
}
