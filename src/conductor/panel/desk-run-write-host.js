"use strict";
// The Desk owns selection and the project-bound transport. Studio owns the
// run's drafts, write locks, bodies and acceptance rules.
import {EMPTY, reduce} from "./studio-store.js";
import {readWrites} from "./studio-runwrites.js";
import {stepWriters, documentWriters, decisionWriters} from "./studio-runwrite.js";
import {decisionRows} from "./studio-runread.js";
import {ERROR_LABELS} from "./command-projection.js";

const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const errorNotice = (code) => ({key: `error.${Object.hasOwn(ERROR_LABELS, code) ? code : "store_error"}`});

export function createRunWriteHost({door, binding, refreshRun, onChange, onForeign}) {
  let state = EMPTY, selected = null, detail = null, disposed = false;
  let actor = null, decisionRevision = 0, decisionAnswer = null, historyKey = null;
  // The run held is read again (the desk draws it as stale): its decisions are kept, writes wait.
  let updating = false;
  const drafts = new Map();
  const pendingDecisions = new Set();
  function dispatch(event) {
    if (disposed) return;
    if (event.type === "decision-chosen" && event.key === null && decisionAnswer
        && (decisionAnswer.runId !== selected
          || decisionAnswer.revision !== decisionRevision)) return;
    state = reduce(state, event);
    if (event.type === "decision-chosen" || event.type === "decision-edit") {
      if (event.type === "decision-chosen" && actor !== null) {
        state = reduce(state, {type: "decision-edit", patch: {actor}});
      }
      decisionRevision += 1;
      if (selected !== null) drafts.set(selected, state.decisions.draft);
    }
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
      if (selected !== null) drafts.set(selected, state.decisions.draft);
      selected = id;
      historyKey = null;
      state = reduce(state, {type: "run-chosen", runId: id});
      state = reduce(state, {type: "decision-chosen", key: null});
      state = Object.freeze({...state, decisions: Object.freeze({
        ...state.decisions, phase: "loading", list: Object.freeze([])})});
      const draft = id === null ? null : drafts.get(id);
      if (draft) state = Object.freeze({...state, decisions: Object.freeze({
        ...state.decisions, draft})});
      decisionRevision += 1;
      detail = null;
    }
    updating = desk.run.phase === "stale" && id !== null;
    if (id !== null && read !== detail && !updating) {
      detail = read;
      state = Object.freeze({...state, runs: Object.freeze({...state.runs,
        writes: readWrites(state.runs.writes, id)}),
        decisions: Object.freeze({...state.decisions, phase: "ready",
          list: decisionRows(read)})});
      if (!state.decisions.list.some((row) =>
          `${row.run_id}/${row.gate_id}` === historyKey)) historyKey = null;
    }
    actor = desk.actor;
    const selectedRow = state.decisions.list.find((row) =>
      `${row.run_id}/${row.gate_id}` === state.decisions.draft.key);
    const actionable = state.decisions.list.find((row) =>
      !row.ended && row.decision !== "unknown"
        && (row.answerable === "first" || row.answerable === "supersede"));
    if (id !== null && state.decisions.list.length
        && (!selectedRow || (actionable && selectedRow !== actionable
          && (selectedRow.ended || selectedRow.decision === "unknown"
            || (selectedRow.answerable !== "first"
              && selectedRow.answerable !== "supersede"))))) {
      const row = actionable ?? state.decisions.list[0];
      state = reduce(state, {type: "decision-chosen", key: `${row.run_id}/${row.gate_id}`});
      decisionRevision += 1;
    }
    if (id !== null && state.decisions.draft.actor !== (actor ?? "")) {
      state = reduce(state, {type: "decision-edit", patch: {actor: actor ?? ""}});
      drafts.set(id, state.decisions.draft);
      decisionRevision += 1;
    }
    return state;
  }
  async function write(target, runId, body, carry, recover) {
    if (!current() || runId !== selected || !ID.test(runId)) {
      recover?.({status: "refused", code: "read_late"});
      return;
    }
    if (target === "decisions" && (state.decisions.draft.key !== `${runId}/${body.gate_id}`
        || !state.decisions.list.some((row) => row.run_id === runId
          && row.gate_id === body.gate_id
          && (row.answerable === "first" || row.answerable === "supersede")))) {
      recover?.({status: "refused", code: "gate_unreached"});
      return;
    }
    const decisionKey = target === "decisions" ? `${runId}/${body.gate_id}` : null;
    if (decisionKey !== null && pendingDecisions.has(decisionKey)) return;
    if (decisionKey !== null) pendingDecisions.add(decisionKey);
    const answering = target === "decisions"
      ? {runId, revision: decisionRevision} : null;
    try {
      dispatch({type: "status", notice: {key: "notice.writing"}});
      if (!current() || runId !== selected) return;
      let result;
      try { result = await door.submit(target, runId, body); }
      catch (_error) { result = {status: "unknown"}; }
      if (disposed) return;
      if (result.code === "project_mismatch") { onForeign(); return; }
      if (result.status === "accepted") {
        decisionAnswer = answering;
        try { carry(result); } finally { decisionAnswer = null; }
        return;
      }
      // A late answer for another selection may unlock its own write, but must
      // never put its refusal on the newly selected run.
      if (runId === selected && binding().taskId === detail?.config?.task?.id) {
        dispatch({type: "status", notice: result.status === "unknown"
          ? {key: "notice.outcome_unknown"} : errorNotice(result.code)});
      }
      decisionAnswer = answering;
      try { recover?.(result); } finally { decisionAnswer = null; }
    } finally {
      if (decisionKey !== null) {
        pendingDecisions.delete(decisionKey);
        if (!disposed) onChange();
      }
    }
  }
  const adapter = {chosenRun: () => current() ? selected : null,
    dispatch, isId: (value) => typeof value === "string" && ID.test(value),
    said: errorNotice, state: () => state, write,
    refreshRun: (runId) => refreshRun(runId)};
  const decisions = decisionWriters({...adapter, draft: () => state.decisions.draft});
  return Object.freeze({sync, state: () => state, updating: () => updating,
    decisionPending: () => pendingDecisions.has(state.decisions.draft.key),
    historyKey: () => historyKey,
    handlers: Object.freeze({...stepWriters(adapter), ...documentWriters(adapter),
      selectDecision: (key) => {
        if (disposed || !state.decisions.list.some((row) =>
            `${row.run_id}/${row.gate_id}` === key)) return;
        historyKey = key;
        onChange();
      },
      editDecision: (patch) => dispatch({type: "decision-edit", patch}),
      ...decisions}),
    dispose: () => { disposed = true; selected = null; detail = null;
      drafts.clear(); pendingDecisions.clear(); }});
}
