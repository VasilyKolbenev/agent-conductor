"use strict";
// The Desk owns selection and the project-bound transport. Studio owns the
// run's drafts, write locks, bodies and acceptance rules.
import {EMPTY, reduce} from "./studio-store.js";
import {readWrites} from "./studio-runwrites.js";
import {stepWriters, documentWriters} from "./studio-runwrite.js";
import {ERROR_LABELS} from "./command-projection.js";

const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const errorNotice = (code) => ({key: `error.${Object.hasOwn(ERROR_LABELS, code) ? code : "store_error"}`});

export function createRunWriteHost({door, binding, refreshRun, onChange, onForeign}) {
  let state = EMPTY, selected = null, detail = null, disposed = false;
  function dispatch(event) {
    if (disposed) return;
    state = reduce(state, event);
    onChange();
  }
  function current() {
    const now = binding();
    return !disposed && !now.foreign && now.mode === "active"
      && now.connection === "open" && now.runId === selected
      && now.taskId === detail?.config?.task?.id && now.ready;
  }
  function sync(desk) {
    if (disposed) return state;
    const visible = desk.run.detail;
    const read = desk.run.phase === "ready" ? visible : null;
    const id = visible?.config?.task?.id === desk.taskId ? visible?.run?.run_id ?? null : null;
    if (id !== selected) {
      selected = id;
      state = reduce(state, {type: "run-chosen", runId: id});
      detail = null;
    }
    if (id !== null && read !== detail) {
      detail = read;
      state = Object.freeze({...state, runs: Object.freeze({...state.runs,
        writes: readWrites(state.runs.writes, id)})});
    }
    return state;
  }
  async function write(target, runId, body, carry, recover) {
    if (!current() || runId !== selected || !ID.test(runId)) {
      recover?.({status: "refused", code: "read_late"});
      return;
    }
    dispatch({type: "status", notice: {key: "notice.writing"}});
    let result;
    try { result = await door.submit(target, runId, body); }
    catch (_error) { result = {status: "unknown"}; }
    if (disposed) return;
    if (result.code === "project_mismatch") { onForeign(); return; }
    if (result.status === "accepted") { carry(result); return; }
    // A late answer for another selection may unlock its own write, but must
    // never put its refusal on the newly selected run.
    if (runId === selected && binding().taskId === detail?.config?.task?.id) {
      dispatch({type: "status", notice: result.status === "unknown"
        ? {key: "notice.outcome_unknown"} : errorNotice(result.code)});
    }
    recover?.(result);
  }
  const adapter = {chosenRun: () => current() ? selected : null,
    dispatch, isId: (value) => typeof value === "string" && ID.test(value),
    said: errorNotice, state: () => state, write,
    refreshRun: (runId) => refreshRun(runId)};
  return Object.freeze({sync, state: () => state,
    handlers: Object.freeze({...stepWriters(adapter), ...documentWriters(adapter)}),
    dispose: () => { disposed = true; selected = null; detail = null; }});
}
