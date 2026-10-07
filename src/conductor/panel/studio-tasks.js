"use strict";
// The project task picker and creation form. No record or scope is inferred
// from a displayed title; two equal titles remain two separate choices.
import {element} from "./command-view.js";
import {TASK_TITLE_LIMIT, selectedTask} from "./studio-tasks-model.js";
import {localize, noticeText} from "./studio-i18n.js";
import {newestRun} from "./studio-taskruns.js";
import {cycleCard} from "./studio-runhead.js";

function field(label, control, extra = "") {
  return element("label", {className: `command-field ${extra}`}, [
    element("span", {text: label}), control]);
}

export function mountTasks(mount, state, handlers) {
  const held = state.tasks, selected = selectedTask(state);
  const expanded = mount.querySelector("details[data-task-create]")?.open || false;
  const pick = element("select", {"aria-label": localize(state, "task.label"), "data-focus": "task-picker"}, [
    element("option", {value: "", text: localize(state, "task.all")})]);
  for (const row of held.list) {
    const repeated = held.list.filter((other) => other.title === row.title).length > 1;
    pick.append(element("option", {value: row.task_id,
      text: `${row.title || localize(state, "task.unreadable")}${repeated || row.unreadable
        ? ` · ${row.task_id.slice(-8)}` : ""}`}));
  }
  if (held.selectedId && !selected) pick.append(element("option", {
    value: held.selectedId, text: localize(state, "task.unavailable", {id: held.selectedId})}));
  pick.value = held.selectedId || "";
  pick.addEventListener("change", () => handlers.chooseTask(pick.value || null));
  const refresh = element("button", {type: "button", text: localize(state, "task.refresh"),
    "data-focus": "task-refresh"});
  refresh.addEventListener("click", handlers.refreshTasks);
  const disclosure = creation(state, handlers, expanded);
  const notice = noticeText(state, held.notice) || (selected?.unreadable
    ? localize(state, "task.unreadable_notice") : "");
  const history = held.outcomes.length ? [element("details", {
    "data-task-outcomes": ""}, [element("summary", {text: localize(state, "task.history")}),
    element("ul", {}, held.outcomes.map((row) => element("li", {
      "data-task-outcome": row.taskId, text: `${row.title} · ${localize(state, `task.${row.status}`)}`})))])] : [];
  if (history.length) history[0].open = mount.querySelector("[data-task-outcomes]")?.open || false;
  // The chosen run's cycle sits under the tasks on the run screen, as the agreed shell draws it.
  const detail = state.runs.detail, chosen = detail?.run && detail.run.run_id === state.runs.selectedId;
  const cycle = state.screen === "runs" && chosen
    ? [cycleCard(state, detail, mount.querySelector("[data-cycle-crew]")?.open || false)] : [];
  mount.replaceChildren(element("div", {className: "studio-task-bar"}, [
    ...(state.screen === "runs" ? [taskRail(state, handlers)]
      : [field(localize(state, "task.label"), pick, "studio-task-choice")]), refresh, disclosure, ...history,
    element("p", {className: "studio-hint", "data-task-notice": "",
      ...(notice ? {} : {hidden: ""}), text: notice}), ...cycle]));
}

function creation(state, handlers, expanded) {
  const held = state.tasks;
  const title = element("input", {name: "task-title", "data-focus": "task-title",
    "data-focus-value": "state",
    autocomplete: "off", maxlength: String(TASK_TITLE_LIMIT), required: ""});
  title.value = held.draft.title;
  title.addEventListener("input", () => handlers.editTask({title: title.value}));
  const create = element("button", {type: "submit", text: localize(state, held.creating ? "task.creating" : "task.create"), "data-focus": "task-create"});
  create.disabled = held.creating || state.connection !== "open";
  const form = element("form", {className: "studio-task-create"}, [
    field(localize(state, "task.name"), title), create]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!create.disabled && form.reportValidity()) handlers.createTask();
  });
  const disclosure = element("details", {"data-task-create": ""}, [element("summary", {
    text: localize(state, "task.new"), "data-focus": "task-new"}), form]);
  disclosure.open = expanded;
  return disclosure;
}

function taskWord(state, task) {
  if (task.unreadable) return localize(state, "task.unreadable");
  if (state.connection !== "open") return localize(state, "scene.disconnected");
  const newest = newestRun(state.runs, task.task_id);
  if (newest.state !== "known") return localize(state,
    newest.state === "none" ? "bridge.no_runs" : "bridge.catalog_unknown");
  const row = newest.row;
  if (row.human_state !== "not_required") return localize(state,
    row.human_state === "required" ? "bridge.required" : "bridge.unknown");
  if (row.open_actions > 0) return localize(state, "scene.awaiting_result");
  return row.last_outcome ? localize(state, `scene.outcome_${row.last_outcome}`)
    : localize(state, "bridge.no_outcome");
}

function taskRail(state, handlers) {
  const nav = element("nav", {className: "studio-task-rail", "aria-label": localize(state, "task.section")}, [
    element("h2", {text: localize(state, "task.section")})]);
  const row = (id, title, word) => {
    const button = element("button", {type: "button", className: "studio-task-row",
      "data-task-id": id || "", "data-focus": `task-row:${id || "all"}`,
      "aria-pressed": String(state.tasks.selectedId === id)}, [
      element("strong", {text: title}), element("span", {text: word})]);
    button.addEventListener("click", () => handlers.chooseTask(id));
    return button;
  };
  nav.append(row(null, localize(state, "bridge.task_all"), ""));
  for (const task of state.tasks.list) {
    const repeated = state.tasks.list.filter((other) => other.title === task.title).length > 1;
    const title = (task.title || localize(state, "task.unreadable"))
      + (repeated || task.unreadable ? ` · ${task.task_id.slice(-8)}` : "");
    nav.append(row(task.task_id, title, taskWord(state, task)));
  }
  if (state.tasks.selectedId && !selectedTask(state)) nav.append(row(state.tasks.selectedId,
    localize(state, "task.unavailable", {id: state.tasks.selectedId}), localize(state, "bridge.unknown")));
  return nav;
}
