"use strict";
// The five-screen shell is presentation only; handlers own every action.
import {element} from "./command-view.js";
import {localize, noticeText} from "./studio-i18n.js";
import {runPrimary} from "./studio-runhead.js";

export const PHASE_SENTENCES = Object.freeze({
  empty: "Nothing has been read yet.",
  loading: "Reading.",
  ready: "Read.",
  stale: "Shown from an earlier read; a newer one has not landed.",
  refused: "This read was refused. Nothing below is newer than the refusal.",
  failed: "This read failed. Nothing below is newer than the failure.",
  disconnected: "The live connection is down, so nothing here updates.",
});
const PHASE_ORDER = ["failed", "refused", "loading", "stale", "empty", "ready"];
const PRIMARY = Object.freeze({
  overview: ["onScreen", "workflow"], workflow: ["onSaveDraft", null],
  runs: ["onRefreshRuns", null], decisions: ["onRefreshRun", null],
  agents: ["onRefreshAgents", null],
});

export function screenPhase(state, screen) {
  if (state.connection === "closed") return "disconnected";
  if (screen === "overview") {
    const seen = [state.workflows.phase, state.runs.phase];
    return PHASE_ORDER.find((word) => seen.includes(word)) || "empty";
  }
  const held = state[screen === "workflow" ? "workflows" : screen];
  const word = held && typeof held === "object" ? held.phase : "empty";
  return Object.hasOwn(PHASE_SENTENCES, word) ? word : "failed";
}

export function saveRefusal(held, state) {
  if (held.draft === null) return localize(state,
    held.detail?.published ? "save.copy_first" : "save.no_draft");
  if (!held.writeReady) return localize(state, "save.unread");
  return held.savePhase === "submitting" ? localize(state, "save.pending") : null;
}

function primaryAction(state, handlers) {
  // A chosen run's main action is the one its own read calls for; with no run chosen, the list is read again.
  const detail = state.runs.detail;
  if (state.screen === "runs" && detail?.run?.run_id && detail.run.run_id === state.runs.selectedId) {
    return runPrimary(state, handlers, detail);
  }
  const screen = Object.hasOwn(PRIMARY, state.screen) ? state.screen : "overview";
  const [name, argument] = PRIMARY[screen];
  const call = handlers[name];
  const control = element("button", {className: "studio-btn", type: "button",
    "data-focus": `action:${name}`, text: localize(state, `primary.${screen}`)});
  if (typeof call === "function") control.addEventListener("click", () => call(argument));
  else control.disabled = true;
  const refusal = screen === "workflow" ? saveRefusal(state.workflows, state) : null;
  if (refusal !== null) {
    control.disabled = true;
    control.title = refusal;
  }
  return control;
}

function tab(node, state, handlers) {
  const screen = node.getAttribute("data-screen"), current = screen === state.screen;
  node.textContent = localize(state, `nav.${screen}`);
  node.setAttribute("aria-selected", String(current));
  node.tabIndex = current ? 0 : -1;
  if (node.dataset.wired === "yes") return;
  node.dataset.wired = "yes";
  if (typeof handlers.onScreen !== "function") node.disabled = true;
  else node.addEventListener("click", () => handlers.onScreen(screen));
}

export function mountShell(mounts, state, handlers) {
  mounts.main.dataset.screen = state.screen;
  const workflow = state.workflows.list.find((row) => row.workflow_id === state.workflows.selectedId);
  mounts.project.textContent = state.project.name !== null ? state.project.name
    : workflow ? (workflow.title || workflow.workflow_id) : localize(state, "app.name");
  const connection = ["open", "connecting"].includes(state.connection) ? state.connection : "closed";
  mounts.connection.textContent = localize(state, `connection.${connection}`);
  mounts.connection.setAttribute("data-connection", state.connection);
  mounts.primary.replaceChildren(primaryAction(state, handlers));
  for (const node of mounts.tabs) tab(node, state, handlers);
  for (const [screen, node] of Object.entries(mounts.screens)) {
    const phase = screenPhase(state, screen);
    node.setAttribute("data-state", phase);
    node.hidden = screen !== state.screen;
    mounts.states[screen].textContent = localize(state, `phase.${phase}`);
  }
  for (const node of mounts.translatedText) node.textContent = localize(state, node.dataset.i18n);
  for (const node of mounts.translatedLabels) node.setAttribute("aria-label", localize(state, node.dataset.i18nLabel));
  mounts.title.textContent = localize(state, "app.title");
  mounts.status.textContent = noticeText(state, state.notice);
}

export function wireScreenKeys(tabs, handlers) {
  tabs.forEach((node, at) => node.addEventListener("keydown", (event) => {
    const step = {ArrowRight: 1, ArrowLeft: -1}[event.key];
    if (!step) return;
    event.preventDefault();
    const next = tabs[(at + step + tabs.length) % tabs.length];
    handlers.onScreen(next.getAttribute("data-screen"));
    next.focus();
  }));
}
