"use strict";
// The write chain of the «Схема» (spec 7.1, 7.10, 5.6.3): a cycle is read and written through
// `GET/POST /command/workflows/<id>/flow` and no other door, one write at a time.
//
// A pure function of its state and one event, in the shape of the wizard's model: an event goes in,
// a state and the asks that are due come out, and the host that owns the doors performs each ask and
// answers it (`answered`). Nothing is remembered outside the state, and nothing here reads a clock,
// a random source or a store: the ids of a new cycle come from the page's nonce.
//
// What it keeps: the flow the person sees and edits (`held`), the last `FlowState` the server said
// (`server`: the diagnostics, the counter, the last revision's flow, the next revision number), and
// the digest of the draft that stands (`digest`), which the next write must name (`expected_digest`,
// or `expected_absent` when no draft stands). Every completed edit is written; the next one waits
// for the answer of the one in flight. A lost answer is never repeated blind (the digest would refuse
// it): the flow is read and compared. A `draft_conflict` on a draft that stands is read again and said
// so, and on the first write of an id this desk made, the next id is taken. A ready cycle (`desk-*`)
// is never written by an edit: the first edit makes a copy under a new `cycle-<8 hex>`.
import {applyEdit} from "./desk-flow-edits.js";
import {canonical, emptyFlow} from "./desk-flow-shape.js";

//: Every notice this chain gives, each with a message in both languages (`schema.write.<name>`).
export const WRITE_NOTICES = Object.freeze(["conflict", "copy_needs_revision", "publish_wait",
  "publish_blocked", "publish_open", "publish_not_written", "edit_wait", "check_failed"]);
const NONCE = /^[0-9a-f]{32}$/;
const CONFLICTS = 4;
const RESERVED = "desk-";

const say = (name) => ({key: `schema.write.${name}`});
const record = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const noted = (notice) => (notice === "" ? null : notice);

/** The state of a chain that has opened nothing. `nonce` is 32 hex digits the page made. */
export function initialWrite({nonce}) {
  if (typeof nonce !== "string" || !NONCE.test(nonce)) {
    throw new Error("the editor needs a page nonce of 32 hex digits");
  }
  return {nonce, minted: 0, conflicts: 0, workflowId: null, title: "", phase: "idle", error: null,
    held: null, server: null, digest: null, fresh: false, origin: null, seed: null, inflight: null,
    reading: null, dirty: false, blocked: false, checkLater: false, seq: 0, save: "idle",
    notice: null, refusal: null, publishing: null, published: null, lost: null};
}

//: The id of the n-th cycle this page names: eight hex digits of the nonce, a window at a time,
//: the nonce turned a place further after four.
function cycleId(nonce, minted) {
  const turn = Math.floor(minted / 4) % 32, rotated = nonce.slice(turn) + nonce.slice(0, turn);
  const at = (minted % 4) * 8;
  return `cycle-${rotated.slice(at, at + 8)}`;
}

//: The next id this page names, never the one the chain stands on (a host may have opened it).
function minted(state) {
  let count = state.minted;
  while (cycleId(state.nonce, count) === state.workflowId) count += 1;
  return {...state, minted: count + 1, workflowId: cycleId(state.nonce, count)};
}

/** Whether an answer is the `FlowState` of the workflow asked about (`none` only when allowed). */
export function isFlowState(payload, workflowId, allowNone) {
  if (!record(payload) || payload.workflow_id !== workflowId) return false;
  const flowed = record(payload.flow)
    || (allowNone && payload.flow === null && payload.source === "none");
  return flowed && Array.isArray(payload.diagnostics) && typeof payload.publishable === "boolean";
}

// -- asks --------------------------------------------------------------------------------

function readAsk(state, purpose) {
  const id = `read:schema:${state.seq + 1}`;
  const ask = {id, name: "schema_read", door: "read", target: "flowRead",
    subject: state.workflowId, body: null};
  return {state: {...state, seq: state.seq + 1, reading: {id, purpose}}, asks: [ask]};
}

//: The write of what stands to be written: a new cycle's seed (a starter or a copy) or the held
//: flow, and a publication when `publish` names a revision.
function writeAsk(state, publish) {
  const source = publish === null && state.seed !== null ? structuredClone(state.seed)
    : {flow: structuredClone(state.held)};
  const expected = state.digest === null ? {expected_absent: true}
    : {expected_digest: state.digest};
  const id = `write:schema:${state.seq + 1}`;
  const ask = {id, name: "schema_write", door: "write", target: "flow",
    subject: state.workflowId, body: {source, ...expected, publish_revision: publish, binding: null}};
  const inflight = {id, flow: source.flow ?? null, seed: state.seed, digest: state.digest, publish};
  return {state: {...state, seq: state.seq + 1, inflight, save: "saving", blocked: false,
    dirty: publish === null ? false : state.dirty}, asks: [ask]};
}

//: What is due when nothing is out: the write of what is unsaved, else a check that was waiting.
function flush(state) {
  const quiet = state.inflight === null && state.reading === null && state.phase === "ready";
  if (quiet && state.dirty && !state.blocked) return writeAsk(state, null);
  if (quiet && state.checkLater && (!state.dirty || state.blocked)) {
    return readAsk({...state, checkLater: false}, null);
  }
  return {state, asks: []};
}

// -- what a landed read does -------------------------------------------------------------

function unreadable(result, payload, id, allowNone) {
  return result.status !== "accepted" || !isFlowState(payload, id, allowNone);
}

function failedWith(result) {
  return result.status === "accepted" ? "answer_unreadable"
    : result.code ?? (result.status === "unknown" ? "unknown" : "refused");
}

function landOpen(state, payload) {
  const none = payload.flow === null;
  const reserved = state.workflowId.startsWith(RESERVED);
  const held = none ? (reserved ? null : emptyFlow(state.title)) : structuredClone(payload.flow);
  return {state: {...state, phase: "ready", error: null, server: payload, held,
    digest: payload.draft_digest ?? null, fresh: none && !reserved, save: "idle"}, asks: []};
}

function landCheck(state, payload) {
  const idle = !state.dirty && state.inflight === null && payload.flow !== null;
  return flush({...state, server: payload, held: idle ? structuredClone(payload.flow) : state.held,
    digest: idle ? payload.draft_digest ?? null : state.digest});
}

//: Another window's draft stands where ours was to go: it is shown, ours is not written over it.
function landConflict(state, payload) {
  const held = payload.flow === null ? state.held : structuredClone(payload.flow);
  return {state: {...state, server: payload, held, digest: payload.draft_digest ?? null,
    dirty: false, blocked: false, save: "conflict", notice: say("conflict"), lost: null,
    publishing: null}, asks: []};
}

//: A lost answer, settled by what the server holds now: it holds our flow (landed), it holds what it
//: held before (not landed: write again under the digest the read gave), or it holds another's.
function landSettle(state, payload) {
  const lost = state.lost, base = {...state, lost: null, server: payload};
  const published = lost.publish !== null && payload.source === "published"
    && payload.latest_revision === lost.publish;
  const draft = payload.source === "draft" && (lost.flow === null
    || canonical(payload.flow) === canonical(lost.flow));
  if (lost.publish !== null ? published : draft) return settledAs(base, payload, lost);
  if ((payload.draft_digest ?? null) !== lost.digest) return landConflict(base, payload);
  const again = lost.publish === null;
  return flush({...base, digest: payload.draft_digest ?? null, dirty: again || base.dirty,
    publishing: null, notice: again ? base.notice : say("publish_not_written"), save: "pending"});
}

function settledAs(state, payload, lost) {
  const ahead = state.dirty;
  const made = lost.publish === null ? null : {revision: lost.publish, created: null};
  return flush({...state, digest: payload.draft_digest ?? null, held: ahead ? state.held
    : structuredClone(payload.flow), seed: null, fresh: false, published: made,
  publishing: null, save: ahead ? "pending" : "saved"});
}

const LANDINGS = Object.freeze({open: landOpen, check: landCheck, conflict: landConflict,
  settle: landSettle});

function landRead(state, ask, result) {
  if (state.reading?.id !== ask.id) return {state, asks: []};
  const purpose = state.reading.purpose ?? "check";
  const base = {...state, reading: null};
  const allowNone = purpose === "open" || purpose === "check" || purpose === "settle";
  if (unreadable(result, result.payload, ask.subject, allowNone)) {
    if (purpose === "open") {
      return {state: {...base, phase: "failed", error: failedWith(result)}, asks: []};
    }
    return {state: {...base, notice: say("check_failed"), checkLater: false}, asks: []};
  }
  return LANDINGS[purpose](base, result.payload);
}

// -- what a landed write does ------------------------------------------------------------

function landAccepted(state, payload) {
  const ahead = state.dirty, made = payload.published ?? null;
  return flush({...state, server: payload, digest: payload.draft_digest ?? null, fresh: false,
    conflicts: 0, seed: null, phase: "ready", refusal: null, published: made ?? state.published,
    publishing: made === null ? state.publishing : null,
    held: ahead ? state.held : structuredClone(payload.flow),
    save: ahead ? "pending" : "saved"});
}

function landRefused(state, sent, result) {
  const rows = result.payload?.diagnostics;
  const refusal = {code: result.code ?? "refused",
    diagnostics: Array.isArray(rows) ? structuredClone(rows) : []};
  const published = sent.publish !== null;
  return {state: {...state, save: "refused", refusal, blocked: !published || state.blocked,
    dirty: published ? state.dirty : true, publishing: null}, asks: []};
}

//: A conflict on an id this desk made and never wrote takes the next id; on a draft that stands, it
//: reads the draft again and says the cycle was changed in another window.
function landConflictWrite(state, sent) {
  if (state.fresh) {
    if (state.conflicts + 1 >= CONFLICTS) {
      return landRefused({...state, dirty: true}, sent, {code: "draft_conflict"});
    }
    return flush({...minted({...state, conflicts: state.conflicts + 1}), dirty: true});
  }
  return readAsk({...state, save: "conflict", notice: say("conflict")}, "conflict");
}

function landLost(state, sent) {
  const lost = {flow: sent.flow, digest: sent.digest, publish: sent.publish};
  return readAsk({...state, lost: sent.seed === null ? lost : {...lost, flow: null},
    save: "unknown"}, "settle");
}

function landWrite(state, ask, result) {
  const sent = state.inflight;
  if (sent === null || sent.id !== ask.id) return {state, asks: []};
  const base = {...state, inflight: null};
  if (result.status === "unknown") return landLost(base, sent);
  if (result.status === "refused") {
    return result.code === "draft_conflict" ? landConflictWrite(base, sent)
      : landRefused(base, sent, result);
  }
  if (!isFlowState(result.payload, ask.subject, false)) {
    return landRefused(base, sent, {code: "answer_unreadable"});
  }
  return landAccepted(base, result.payload);
}

// -- the events --------------------------------------------------------------------------

function open(state, event) {
  const base = {...initialWrite({nonce: state.nonce}), minted: state.minted,
    workflowId: event.workflowId, title: typeof event.title === "string" ? event.title : "",
    phase: "reading"};
  return readAsk(base, "open");
}

function answered(state, event) {
  const {ask, result} = event;
  if (!record(ask) || !record(result)) return {state, asks: []};
  if (ask.name === "schema_read") return landRead(state, ask, result);
  return ask.name === "schema_write" ? landWrite(state, ask, result) : {state, asks: []};
}

//: The first edit of a ready cycle makes a copy: the held flow is written under a new id, the
//: ready cycle is never written to.
function copyOnEdit(state) {
  if (!state.workflowId.startsWith(RESERVED)) return state;
  return {...minted(state), origin: {workflowId: state.workflowId,
    revision: state.server?.latest_revision ?? null}, digest: null, fresh: true, conflicts: 0};
}

function edit(state, event) {
  if (state.phase !== "ready" || state.held === null) return {state: {...state,
    notice: say("edit_wait")}, asks: []};
  if (state.publishing !== null) return {state: {...state, notice: say("publish_open")}, asks: []};
  const out = applyEdit(state.held, event.edit);
  if (out.flow === null) return {state: {...state, notice: noted(out.notice)}, asks: []};
  return flush({...copyOnEdit(state), held: out.flow, dirty: true, blocked: false,
    save: state.inflight === null ? "pending" : "saving", notice: noted(out.notice),
    refusal: null, published: null});
}

//: A new cycle begins from nothing, a starter, or a copy of the revision that stands. A starter or
//: a copy is written at once (its seed is what the write carries); nothing is written for nothing.
function begin(state, event) {
  const base = {...initialWrite({nonce: state.nonce}), minted: state.minted, phase: "ready"};
  if (event.from === "empty") {
    return {state: {...minted(base), held: emptyFlow(event.title ?? ""), fresh: true}, asks: []};
  }
  if (event.from === "flow") {
    if (!record(event.flow)) return {state, asks: []};
    return flush({...minted(base), held: structuredClone(event.flow), fresh: true, dirty: true,
      save: "pending"});
  }
  if (event.from === "starter") {
    const seed = {starter_id: event.id};
    const own = event.same === true ? {workflowId: event.id} : {...minted(base), fresh: true};
    return flush({...base, ...own, seed, dirty: true, save: "pending"});
  }
  return copyOf(state, base);
}

function copyOf(state, base) {
  const revision = state.server?.latest_revision;
  if (!Number.isInteger(revision)) return {state: {...state, notice: say("copy_needs_revision")},
    asks: []};
  const seed = {copy_of: {workflow_id: state.workflowId, revision}};
  return flush({...minted(base), seed, dirty: true, fresh: true, save: "pending",
    origin: {workflowId: state.workflowId, revision}});
}

function save(state) {
  return flush({...state, blocked: false});
}

function check(state) {
  if (state.workflowId === null || state.phase === "reading" || state.reading !== null) {
    return {state, asks: []};
  }
  if (state.lost !== null && state.inflight === null) return readAsk(state, "settle");
  if (state.inflight !== null || (state.dirty && !state.blocked)) {
    return {state: {...state, checkLater: true}, asks: []};
  }
  return readAsk(state, "check");
}

function request(state) {
  if (state.publishing !== null) return {state, asks: []};
  if (state.server === null || state.held === null) {
    return {state: {...state, notice: say("publish_blocked")}, asks: []};
  }
  if (state.dirty || state.inflight !== null || state.reading !== null) {
    return {state: {...state, notice: say("publish_wait")}, asks: []};
  }
  if (!state.server.publishable) return {state: {...state, notice: say("publish_blocked")}, asks: []};
  return {state: {...state, publishing: {revision: state.server.next_revision}, notice: null},
    asks: []};
}

function confirm(state) {
  if (state.publishing === null || state.dirty || state.inflight !== null) {
    return {state, asks: []};
  }
  return writeAsk(state, state.publishing.revision);
}

const HANDLERS = {open, answered, edit, new: begin, save, check,
  "publish-request": request, "publish-confirm": confirm,
  "publish-cancel": (state) => ({state: {...state, publishing: null}, asks: []})};

export const WRITE_EVENTS = Object.freeze(Object.keys(HANDLERS));

/** One event in; the new state and the asks that are due out. An event not in the table is nothing. */
export function stepWrite(state, event) {
  if (!Object.hasOwn(HANDLERS, event?.type)) return {state, asks: []};
  return HANDLERS[event.type](state, event);
}
