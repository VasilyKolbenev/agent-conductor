"use strict";
// The run panel speaks only for the task/run currently selected by the Desk.
export function createRunPanelBindings({state, connection, choice, where, load, chooseTask}) {
  async function selectRun(runId) {
    const desk = state(), task = desk.taskId;
    if (task === null || !desk.runs.list.some((row) =>
      row.task_id === task && row.run_id === runId)) return;
    await chooseTask(task, runId);
  }
  async function refreshRuns() {
    const desk = state(), task = desk.taskId, run = where().run, asked = choice();
    if (!await load() || state().foreign || task !== state().taskId || asked !== choice()
        || task === null) return;
    await chooseTask(task, run);
  }
  async function refreshRun(runId) {
    const desk = state(), task = desk.taskId, asked = choice();
    if (task === null || desk.foreign || desk.run.detail?.run?.run_id !== runId
        || desk.run.detail?.config?.task?.id !== task) return false;
    if (asked !== choice()) return false;
    return chooseTask(task, runId, () => !state().foreign && state().taskId === task);
  }
  function binding() {
    const desk = state(), detail = desk.run.detail;
    return {taskId: desk.taskId, runId: detail?.run?.run_id ?? null,
      foreign: desk.foreign, mode: desk.mode, connection: connection(),
      ready: desk.run.phase === "ready" && detail?.config?.task?.id === desk.taskId};
  }
  return Object.freeze({selectRun, refreshRuns, refreshRun, binding});
}
