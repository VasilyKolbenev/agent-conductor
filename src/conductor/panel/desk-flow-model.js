"use strict";
// The state and the closed table of events of the «Схема» panel (spec 5.6.3, 7.1, 7.7).
//
// The panel is the write chain (`desk-flowwrite.js`: what is read, what is written, one write at a
// time) plus what only a panel keeps: the list of cycles and the starters to begin from, which step or
// road is selected, the text typed into rows and not yet committed, the open sections, the quick form
// and the canvas's pan and zoom. A pure function of its state and one event, in the shape of the
// wizard's model: an event goes in, a state and the asks that are due come out, and the host that owns
// the doors performs each ask and answers it (`answered`). It reads no clock and no store, and it
// holds no rule about what a good cycle is: every row, every number and every refusal it shows is the
// server's; the only arithmetic of its own is the order of a fork's branches (7.7) and the edits.
//
// `flowView` is what the drawing reads: the state turned into facts, each already settled here (which
// rows, which counter and whether it is stale, what a publication would change), so the drawing
// decides nothing.
import {applyEdit} from "./desk-flow-edits.js";
import {fieldEdit} from "./desk-flow-fields.js";
import {forksOf} from "./desk-flow-branches.js";
import {changeSummary} from "./desk-flow-graph.js";
import {QUICK_KINDS, quickFlow} from "./desk-quickcycle.js";
import {WRITE_EVENTS, initialWrite, isFlowState, isReadyId, stepWrite} from "./desk-flowwrite.js";
import {notice, stepOf} from "./desk-flow-shape.js";

//: Every notice this model gives, each with a message in both languages (`schema.model.<name>`).
export const MODEL_NOTICES = Object.freeze(["switch_wait", "field_int", "field_json",
  "field_empty", "field_unknown", "field_text", "quick_kind"]);
//: The folds the panel keeps open or shut: the extension rows of a step, and of the cycle.
export const SECTION_KEYS = Object.freeze(["ext", "flow"]);
const say = (name) => ({key: `schema.model.${name}`});
const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

/** The state of a panel that has opened nothing. `nonce` is 32 hex digits the page made. */
export function initialFlow({nonce}) {
  return {write: initialWrite({nonce}), list: null, listing: null, listError: null, listSeq: 0,
    selection: null, canvas: {pan: {x: 0, y: 0}, zoom: 1}, sections: {}, drafts: {}, quick: null,
    status: null, notice: null};
}

// -- the list of cycles ------------------------------------------------------------------

function listAsk(state) {
  if (state.listing !== null) return {state, asks: []};
  const id = `read:cycles:${state.listSeq + 1}`;
  const ask = {id, name: "schema_workflows", door: "read", target: "workflows", subject: null,
    body: null};
  return {state: {...state, listSeq: state.listSeq + 1, listing: {id}}, asks: [ask]};
}

function landList(state, ask, result) {
  if (state.listing?.id !== ask.id) return {state, asks: []};
  const base = {...state, listing: null}, payload = result.payload;
  if (result.status !== "accepted") {
    const code = result.code ?? (result.status === "unknown" ? "unknown" : "refused");
    return {state: {...base, listError: code}, asks: []};
  }
  if (!record(payload) || !Array.isArray(payload.workflows)) {
    return {state: {...base, listError: "answer_unreadable"}, asks: []};
  }
  const rows = (list) => (Array.isArray(list) ? list.filter(record) : []);
  return {state: {...base, listError: null,
    list: {workflows: rows(payload.workflows), starters: rows(payload.starters)}}, asks: []};
}

// -- selection and typed text ------------------------------------------------------------

//: Whether a selection still names a step or a road of the flow held.
function stands(flow, selection) {
  if (flow === null || selection === null) return false;
  if (selection.kind === "node") return stepOf(flow, selection.id) !== undefined;
  const [from, to, ...rest] = selection.id.split(" ");
  return rest.length === 0 && flow.links.some((link) => link.from === from && link.to === to);
}

//: The step a flow gained that is not a loop (a step and its loop come together), else any.
function gained(before, after) {
  const was = new Set((before?.steps ?? []).map((step) => step.step_id));
  const fresh = (after?.steps ?? []).filter((step) => !was.has(step.step_id));
  return fresh.find((step) => step.type !== "loop") ?? fresh[0];
}

//: What the state keeps once the write chain has moved: a selection and typed texts that name
//: nothing any more are dropped, and an edit that added a step selects it.
function settled(state, write, adding) {
  const added = adding ? gained(state.write.held, write.held) : undefined;
  const held = write.held;
  const selection = added === undefined ? (stands(held, state.selection) ? state.selection : null)
    : {kind: "node", id: added.step_id};
  const drafts = Object.fromEntries(Object.entries(state.drafts).filter(([, draft]) =>
    draft.nodeId === null || (held !== null && stepOf(held, draft.nodeId) !== undefined)));
  return {...state, write, selection, drafts};
}

function viaWrite(state, event, adding = false) {
  const out = stepWrite(state.write, event);
  return {state: settled(state, out.state, adding), asks: out.asks};
}

/** The key a typed text is kept under: the step (or none, for the cycle) and the field. */
export const draftKey = (nodeId, field) => `${nodeId ?? ""}\u0000${field}`;

function fieldInput(state, event) {
  const {field, text} = event, nodeId = event.nodeId ?? null, held = state.write.held;
  const known = held !== null && typeof field === "string" && typeof text === "string"
    && (nodeId === null || stepOf(held, nodeId) !== undefined);
  if (!known) return {state, asks: []};
  return {state: {...state, drafts: {...state.drafts, [draftKey(nodeId, field)]:
    {nodeId, field, text}}}, asks: []};
}

function withoutDraft(state, key) {
  const {[key]: _spent, ...kept} = state.drafts;
  return {...state, drafts: kept};
}

//: A typed text is one edit. A text that means none stays typed and says why; one that would change
//: nothing is let go without a word; one the flow refuses stays typed with the edit's own reason.
function commit(state, nodeId, field, text) {
  const held = state.write.held, key = draftKey(nodeId, field);
  if (held === null) return {state, asks: []};
  const made = fieldEdit(held, nodeId, field, text);
  if (made.edit === undefined) {
    const name = {field: "unknown"}[made.reason] ?? made.reason;
    return {state: {...state, notice: say(`field_${name}`)}, asks: []};
  }
  const tried = applyEdit(held, made.edit);
  if (tried.flow === null) {
    const quiet = tried.notice?.key === notice("unchanged").key;
    const base = quiet ? withoutDraft(state, key) : state;
    return {state: {...base, notice: quiet ? null : tried.notice}, asks: []};
  }
  return viaWrite(withoutDraft(state, key), {type: "edit", edit: made.edit});
}

function fieldCommit(state, event) {
  return commit(state, event.nodeId ?? null, event.field, event.text);
}

//: «Сохранить»: every text still typed is committed first, then what stands is written.
function save(state) {
  let now = state, asks = [];
  for (const draft of Object.values(state.drafts)) {
    const out = commit(now, draft.nodeId, draft.field, draft.text);
    now = out.state;
    asks = [...asks, ...out.asks];
  }
  const end = viaWrite(now, {type: "save"});
  return {state: end.state, asks: [...asks, ...end.asks]};
}

// -- opening, beginning, answering -------------------------------------------------------

//: An edit not yet written, in flight, or lost and unsettled is never left behind by a switch.
const unsaved = (write) => write.dirty || write.inflight !== null || write.lost !== null;

function switching(state, event, withList) {
  if (unsaved(state.write)) return {state: {...state, notice: say("switch_wait")}, asks: []};
  const out = stepWrite(state.write, event);
  if (out.state.workflowId === state.write.workflowId && event.type !== "open") {
    return {state: {...state, write: out.state}, asks: out.asks};
  }
  const base = {...state, write: out.state, selection: null, drafts: {}, quick: null,
    status: null};
  const list = withList && base.list === null ? listAsk(base) : {state: base, asks: []};
  return {state: list.state, asks: [...out.asks, ...list.asks]};
}

function answered(state, event) {
  const {ask, result} = event;
  if (!record(ask) || !record(result)) return {state, asks: []};
  if (ask.name === "schema_workflows") return landList(state, ask, result);
  const sent = state.write.inflight?.id === ask.id && ask.name === "schema_write";
  const out = stepWrite(state.write, event);
  const base = settled(state, out.state, false);
  const wrote = sent && result.status === "accepted" && isFlowState(result.payload, ask.subject,
    false);
  const list = wrote ? listAsk(base) : {state: base, asks: []};
  return {state: list.state, asks: [...out.asks, ...list.asks]};
}

// -- the quick form ----------------------------------------------------------------------

const quickOpen = (state) => ({state: {...state, quick: state.quick ?? {title: "", rows: []}},
  asks: []});

function withQuick(state, change) {
  return state.quick === null ? {state, asks: []}
    : {state: {...state, ...change(state.quick)}, asks: []};
}

function quickAdd(state, event) {
  if (state.quick !== null && !QUICK_KINDS.includes(event.kind)) {
    return {state: {...state, notice: say("quick_kind")}, asks: []};
  }
  return withQuick(state, (form) => ({quick: {...form, rows: [...form.rows, event.kind]}}));
}

function quickRemove(state, event) {
  return withQuick(state, (form) => ({quick: {...form, rows: form.rows.filter(
    (_kind, at) => at !== event.index)}}));
}

function quickBuild(state) {
  const form = state.quick;
  if (form === null) return {state, asks: []};
  const built = quickFlow(form.title.trim(), form.rows);
  if (built.flow === null) return {state: {...state, notice: built.notice}, asks: []};
  if (form.title.trim() === "") return {state: {...state, notice: notice("title_required")},
    asks: []};
  return switching(state, {type: "new", from: "flow", flow: built.flow}, false);
}

// -- the table ---------------------------------------------------------------------------

const passes = (type) => (state, event) => viaWrite(state, {...event, type}, type === "edit");
const clearsStatus = (handler) => (state, event) => handler({...state, status: null}, event);

const HANDLERS = Object.freeze({
  open: clearsStatus((state, event) => switching(state, event, true)), answered,
  edit: clearsStatus(passes("edit")), new: (state, event) => switching(state, event, false),
  save, check: passes("check"), "publish-request": passes("publish-request"),
  "publish-confirm": passes("publish-confirm"), "publish-cancel": passes("publish-cancel"),
  select: (state, event) => {
    const one = event.selection, ok = record(one) && typeof one.id === "string"
      && (one.kind === "node" || one.kind === "edge");
    return {state: {...state, status: null, selection: ok ? {kind: one.kind, id: one.id} : null},
      asks: []};
  },
  view: (state, event) => {
    const at = (value, held) => (Number.isFinite(value) ? value : held);
    const pan = record(event.pan) ? {x: at(event.pan.x, state.canvas.pan.x),
      y: at(event.pan.y, state.canvas.pan.y)} : state.canvas.pan;
    return {state: {...state, canvas: {pan, zoom: at(event.zoom, state.canvas.zoom)}}, asks: []};
  },
  status: (state, event) => ({state: {...state, status: record(event.notice) ? event.notice
    : null}, asks: []}),
  section: (state, event) => (SECTION_KEYS.includes(event.key)
    ? {state: {...state, sections: {...state.sections, [event.key]: event.open === true}},
      asks: []} : {state, asks: []}),
  "field-input": fieldInput, "field-commit": fieldCommit, cycles: (state) => listAsk(state),
  "quick-open": quickOpen, "quick-close": (state) => ({state: {...state, quick: null}, asks: []}),
  "quick-title": (state, event) => withQuick(state, (form) => ({quick: {...form,
    title: typeof event.value === "string" ? event.value : form.title}})),
  "quick-add": quickAdd, "quick-remove": quickRemove, "quick-build": quickBuild,
});

export const FLOW_EVENTS = Object.freeze([...WRITE_EVENTS, "select", "view", "status", "section",
  "field-input", "field-commit", "cycles", "quick-open", "quick-close", "quick-title", "quick-add",
  "quick-remove", "quick-build"]);

//: A panel notice lives until the person's next move, like a message on a line. An answer landing is
//: not their move, and neither are `view`, a typed letter or a fold: none of them wipes it.
const KEEPS_NOTICE = Object.freeze(["view", "field-input", "section", "status", "answered"]);

/** One event in; the new state and the asks that are due out. An event not in the table is nothing. */
export function stepFlow(state, event) {
  if (!Object.hasOwn(HANDLERS, event?.type)) return {state, asks: []};
  const base = KEEPS_NOTICE.includes(event.type) ? state : {...state, notice: null};
  return HANDLERS[event.type](base, event);
}

// -- what the drawing reads --------------------------------------------------------------

function resolved(flow, selection) {
  if (!stands(flow, selection)) return null;
  if (selection.kind === "node") return {kind: "step", step: stepOf(flow, selection.id)};
  const [from, to] = selection.id.split(" ");
  return {kind: "road", link: {...flow.links.find((link) => link.from === from
    && link.to === to)}};
}

function counterOf(budget, stale) {
  if (!record(budget) || !record(budget.clean) || !record(budget.worst)) return null;
  const pair = (one) => ({actions: one.actions, seconds: one.seconds});
  return {clean: pair(budget.clean), worst: pair(budget.worst),
    limit: budget.limits?.max_actions ?? null, stale};
}

//: Why «Опубликовать» is not open now: an unsaved or unanswered edit, errors, or an open review.
function publishWhy(write, server) {
  if (write.publishing !== null) return "open";
  if (write.dirty || write.inflight !== null || write.reading !== null || write.lost !== null) {
    return "wait";
  }
  return server?.publishable === true ? null : "blocked";
}

/** The state as facts: settled here, so the drawing decides nothing. */
export function flowView(state) {
  const write = state.write, server = write.server, flow = write.held;
  const stale = write.dirty || write.inflight !== null || write.refusal !== null
    || write.lost !== null;
  const why = publishWhy(write, server);
  return {phase: write.phase, error: write.error, workflowId: write.workflowId, flow,
    title: flow?.title ?? write.title, ready: isReadyId(write.workflowId),
    source: server?.source ?? null, latest: server?.latest_revision ?? null,
    next: server?.next_revision ?? null, save: write.save, notice: state.notice ?? write.notice,
    refused: write.refusal?.code ?? null,
    rows: write.refusal !== null ? write.refusal.diagnostics : server?.diagnostics ?? [],
    counter: counterOf(server?.budget, stale), stale, publishWhy: why,
    publishing: write.publishing, published: write.published,
    review: write.publishing !== null && flow !== null
      ? changeSummary(flow, server?.revision_flow ?? null) : [],
    selection: resolved(flow, state.selection), forks: flow === null ? [] : forksOf(flow),
    copyable: Number.isInteger(server?.latest_revision), busy: write.inflight !== null
      || write.reading !== null, cycles: state.list?.workflows ?? [],
    starters: state.list?.starters ?? [], listError: state.listError, quick: state.quick,
    sections: state.sections, drafts: state.drafts, canvas: state.canvas, status: state.status};
}
