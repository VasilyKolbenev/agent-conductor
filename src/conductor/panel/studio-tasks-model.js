"use strict";
// Project tasks are durable identities; names are display text only. This
// boundary owns the list contract and its local selection/creation draft.
import {isInstant} from "./studio-model.js";
export const TASK_ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._\\-]{0,63}";
export const TASK_TITLE_LIMIT = 200;
export const NO_TASKS = Object.freeze({phase: "empty", list: Object.freeze([]),
  selectedId: null, draft: Object.freeze({taskId: "", title: "", generation: 0, sent: false}),
  outcomes: Object.freeze([]),
  creating: false, notice: Object.freeze({key: "notice.tasks_not_read"})});

export function isTaskId(value) {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(value);
}

function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function keys(value, names) {
  return record(value) && Object.keys(value).sort().join(",") === names;
}

export function taskTitle(value) {
  return typeof value === "string" && value.trim().length > 0
    && [...value].length <= TASK_TITLE_LIMIT && !/[\x00-\x1f\x7f]/.test(value);
}

export function projectTasks(payload) {
  if (!keys(payload, "tasks") || !Array.isArray(payload.tasks)) return null;
  const seen = new Set(), list = [];
  for (const row of payload.tasks) {
    if (!keys(row, "created_at,schema_version,task_id,title,unreadable,work_scope")
        || !isTaskId(row.task_id) || seen.has(row.task_id)) return null;
    seen.add(row.task_id);
    if (row.unreadable === true) {
      if ([row.created_at, row.schema_version, row.title, row.work_scope]
        .some((value) => value !== null)) return null;
    } else if (row.unreadable !== false || row.schema_version !== 1
        || !taskTitle(row.title) || !isTaskId(row.work_scope)
        || !isInstant(row.created_at)) return null;
    list.push(Object.freeze({...row}));
  }
  return Object.freeze(list);
}

function moved(state, patch) {
  return Object.freeze({...state, tasks: Object.freeze({...state.tasks, ...patch})});
}

export function reduceTasks(state, event) {
  const held = state.tasks;
  if (event.type === "tasks-loaded") {
    const list = projectTasks(event.payload);
    return list === null ? moved(state, {phase: "failed",
      notice: {key: "notice.tasks_unreadable"}})
      : moved(state, {phase: "ready", list, notice: "",
        outcomes: Object.freeze(held.outcomes.map((row) => list.some((task) =>
          !task.unreadable && task.task_id === row.taskId && task.title === row.title)
          ? Object.freeze({...row, status: "read"}) : row))});
  }
  if (event.type === "tasks-phase") return moved(state, {phase: event.phase,
    notice: event.notice || {key: "notice.tasks_reading"}});
  if (event.type === "task-chosen") return moved(state,
    {selectedId: event.taskId === null || isTaskId(event.taskId) ? event.taskId : null});
  if (event.type === "task-edit") {
    const draft = {...held.draft, generation: held.draft.generation + 1};
    for (const key of ["taskId", "title"]) {
      if (typeof event.patch?.[key] === "string") draft[key] = event.patch[key];
    }
    if (typeof event.patch?.sent === "boolean") draft.sent = event.patch.sent;
    return moved(state, {draft: Object.freeze(draft)});
  }
  if (event.type === "task-sent" && held.draft.generation === event.generation) {
    return moved(state, {draft: Object.freeze({...held.draft, sent: true})});
  }
  if (event.type === "task-outcome") {
    const old = held.outcomes.find((row) => row.taskId === event.taskId);
    const row = Object.freeze({taskId: event.taskId, title: event.title,
      status: old?.status === "read" ? "read" : event.status});
    return moved(state, {outcomes: Object.freeze([
      ...held.outcomes.filter((item) => item.taskId !== row.taskId), row])});
  }
  if (event.type === "task-creating") return moved(state, {creating: event.value});
  if (event.type === "task-notice") return moved(state, {notice: event.notice});
  if (event.type === "task-spent" && held.draft.generation === event.generation) {
    return moved(state, {draft: Object.freeze({taskId: "", title: "",
      generation: held.draft.generation + 1, sent: false})});
  }
  return state;
}

export function selectedTask(state) {
  return state.tasks.list.find((row) => row.task_id === state.tasks.selectedId) || null;
}

export function canOpenTask(state) {
  if (state.tasks.selectedId === null) return false;
  const task = selectedTask(state);
  return state.tasks.phase === "ready" && task !== null && !task.unreadable;
}
