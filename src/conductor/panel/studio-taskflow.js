"use strict";
// Task orchestration uses the boot module's existing read/write doors. URL
// navigation carries only identifiers, never credentials or authority.
import {canOpenTask, isTaskId, taskTitle} from "./studio-tasks-model.js";
import {newestRun} from "./studio-taskruns.js";

const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SCREENS = ["overview", "workflow", "runs", "decisions", "agents"];

export function navigation(hash) {
  const fields = new URLSearchParams(hash.replace(/^#/, ""));
  const named = (key) => ID.test(fields.get(key) || "") ? fields.get(key) : null;
  const taskId = named("task");
  return {taskId: isTaskId(taskId) ? taskId : null, runId: named("run"),
    workflowId: named("workflow"), screen: SCREENS.includes(fields.get("screen"))
      ? fields.get("screen") : "overview"};
}

export function navigationHash(state) {
  const fields = new URLSearchParams();
  fields.set("screen", state.screen);
  if (state.tasks.selectedId) fields.set("task", state.tasks.selectedId);
  if (state.workflows.selectedId) fields.set("workflow", state.workflows.selectedId);
  if (state.runs.selectedId) fields.set("run", state.runs.selectedId);
  return `#${fields}`;
}

// The drafts a person types into on the chosen run. Every edit replaces its draft
// with a new frozen object, and a read of the same run keeps the very same ones,
// so an unchanged reference means nothing was typed while an answer was away.
const typedDrafts = (state) => [state.runs.step, state.runs.document, state.decisions.draft];
const untouched = (typed, state) => typedDrafts(state).every((draft, at) => draft === typed[at]);

class TaskFlow {
  constructor(door) { this.door = door; this.reads = 0; this.landed = 0; this.selection = 0; }
  editTask(patch) {
    const held = this.door.state().tasks.draft;
    if (patch.title === held.title) return;
    // A submitted payload is immutable even when its reply was lost. Editing
    // it starts the next task; an unchanged retry keeps the exact old payload.
    const taskId = !held.taskId || held.sent ? `task-${crypto.randomUUID()}` : held.taskId;
    this.door.dispatch({type: "task-edit", patch: {title: patch.title, taskId, sent: false}}, false);
  }
  async refreshTasks() {
    const asked = ++this.reads;
    this.door.dispatch({type: "tasks-phase", phase: "loading"});
    let heard;
    try {
      heard = {type: "tasks-loaded", payload: await this.door.read("/command/tasks")};
    } catch (_error) {
      heard = {type: "tasks-phase", phase: "failed",
        notice: {key: "notice.tasks_retry"}};
    }
    if (asked < this.landed) return;
    this.landed = asked;
    this.door.dispatch(heard);
  }

  async chooseTask(taskId, openNewest = true) {
    if (taskId !== null && !isTaskId(taskId)) return;
    const asked = ++this.selection;
    this.door.clearRun();
    this.door.dispatch({type: "task-chosen", taskId});
    if (!taskId || !openNewest) return;
    const navigation = this.door.runSelection();
    await this.door.loadRuns();
    if (asked !== this.selection || navigation !== this.door.runSelection()
        || this.door.state().tasks.selectedId !== taskId) return;
    const newest = newestRun(this.door.state().runs, taskId);
    if (newest.state === "unknown") {
      this.door.dispatch({type: "screen", screen: "runs"});
      this.door.dispatch({type: "task-notice", notice: {key: "notice.newest_run_unknown"}});
    } else if (newest.state === "none") this.door.dispatch({type: "screen", screen: "workflow"});
    else {
      this.door.dispatch({type: "screen", screen: "runs"});
      this.door.refreshRun(newest.row.run_id, true);
    }
  }

  async createTask() {
    const {draft, creating} = this.door.state().tasks;
    if (creating || !isTaskId(draft.taskId) || !taskTitle(draft.title)) {
      this.door.dispatch({type: "task-notice", notice: {key: "notice.task_name_invalid"}});
      return;
    }
    const asked = this.selection, navigation = this.door.runSelection();
    const typed = typedDrafts(this.door.state()); // words typed into the chosen run meanwhile
    const outcome = (status) => this.door.dispatch({type: "task-outcome",
      taskId: draft.taskId, title: draft.title, status});
    let answered = false;
    this.door.dispatch({type: "task-sent", generation: draft.generation});
    this.door.dispatch({type: "task-creating", value: true});
    outcome("writing");
    try {
      await this.door.write("tasks", null, {task_id: draft.taskId, title: draft.title}, () => {
        answered = true;
        const unchanged = this.door.state().tasks.draft.generation === draft.generation;
        outcome("accepted");
        this.door.dispatch({type: "status", notice: {key: "notice.task_created", params: {title: draft.title}}});
        this.door.dispatch({type: "task-spent", generation: draft.generation});
        this.refreshTasks();
        if (unchanged && asked === this.selection && navigation === this.door.runSelection()
            && untouched(typed, this.door.state())) {
          this.chooseTask(draft.taskId);
        }
      }, (result) => {
        answered = true;
        outcome(result.status === "refused" ? "refused" : "unknown");
      });
    } finally {
      if (!answered) outcome("unknown");
      this.door.dispatch({type: "task-creating", value: false});
    }
  }

  openRun(request) {
    const state = this.door.state(), taskId = state.tasks.selectedId;
    if (![request.runId, request.cycleId, state.workflows.selectedId]
      .every((value) => typeof value === "string" && ID.test(value))
        || !Number.isInteger(request.revision)
        || !canOpenTask(state)) return;
    const asked = this.selection, navigation = this.door.runSelection();
    const typed = typedDrafts(this.door.state()); // words typed into the chosen run meanwhile
    const opening = state.workflows.opening;
    const body = {run_id: request.runId, cycle_id: request.cycleId,
      mode: request.mode, participants: request.participants,
      workflow_id: state.workflows.selectedId, revision: request.revision,
      assignments: request.assignments, task_id: taskId,
      ...(request.mode === "policy" ? {automation_contract: "bounded-run-v1"} : {})};
    this.door.write("runs", null, body, () => {
      this.door.loadRuns();
      const sameWorkflow = state.workflows.selectedId === this.door.state().workflows.selectedId;
      const notice = {key: "notice.run_opened", params: {run: request.runId}};
      this.door.dispatch(sameWorkflow ? {type: "save", phase: "saved", notice}
        : {type: "status", notice});
      if (asked !== this.selection || taskId !== this.door.state().tasks.selectedId
          || navigation !== this.door.runSelection()
          || opening !== this.door.state().workflows.opening
          || !untouched(typed, this.door.state()) || !sameWorkflow) return;
      this.door.dispatch({type: "opening-cleared"});
      this.door.refreshRun(request.runId);
    });
  }
}

export function taskFlow(door) {
  const flow = new TaskFlow(door);
  return Object.fromEntries(["refreshTasks", "chooseTask", "createTask", "openRun", "editTask"]
    .map((name) => [name, flow[name].bind(flow)]));
}
