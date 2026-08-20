"use strict";
// The reducer the Graph window runs on: one frozen state value, one event at
// a time, and no other way to move. Validation is not here — a payload is
// admitted by graph-payload.js before any of this sees it — so what this file
// decides is only ever what the SCREEN should now say.
//
// Two of its rules are worth stating where they live. A save outcome belongs
// to the run it was asked about and to the read that announces it. And the
// write door is opened by nothing in this module: readiness arrives as an
// answer about one run, and is refused, never assumed.
import {computeLayout, DECISION_ACTIONS, FIXTURE_SOURCE, TITLE_LIMIT}
  from "./graph-payload.js";
import {isId} from "./command-projection.js";

// The boundary twin of the reason input's maxlength: the DOM cap is advice,
// this one is the rule.
const REASON_LIMIT = 200;

export const EMPTY = Object.freeze({
  phase: "empty",   // empty | loaded | refused
  notice: "No run graph loaded. Load a run, or start from the product's "
    + "default plan — nothing is written to a run until you write it.",
  run: Object.freeze({runId: "", mode: "unknown"}),
  registry: Object.freeze([]),
  nodes: Object.freeze([]),
  edges: Object.freeze([]),
  layout: Object.freeze({columns: 0, rows: 0, cells: Object.freeze({})}),
  timeline: Object.freeze([]),
  // Where the nodes above came from. It starts as a fixture and stays one
  // until a durable read replaces it: nothing this window does locally may
  // promote its own drawing to `durable`.
  provenance: FIXTURE_SOURCE,
  // The save door's own status, apart from every other notice for the reason
  // the composer's is: a refusal must land beside the control it answers.
  // `saved` is never set here — only an authoritative re-read may say a plan
  // is durable.
  savePhase: "idle",   // idle | submitting | refused | outcome-unknown
  saveNotice: "",
  // Whether this window may WRITE. Not "is the socket up": a live socket says
  // nothing about whether the facts on screen belong to the run now selected.
  // Between choosing a run and its read landing, the drawing is still the
  // PREVIOUS run's — and a write then would have built one run's plan and
  // sent it to another run's immutable route. So readiness names one answer
  // about one run, is taken away the moment another is chosen, and is given
  // back only by a landed read of the chosen one. A refused or failed read
  // grants nothing.
  writeReady: false,
  selection: null,
  // The local decision ledger: gate_id → what the Human drafted here. Alpha
  // records it in this window and nowhere else; the notice says so. A null
  // prototype, because gate ids are data and "constructor" is a valid id —
  // an inherited member must never read as a recorded decision.
  decisions: Object.freeze(Object.create(null)),
  decisionNotice: "",
  // The composer's own status line, rendered beside the composer form; the
  // shell notice above stays reserved for load-level facts.
  composeNotice: "",
});

function withGateState(nodes, gateId, state) {
  return Object.freeze(nodes.map((node) => {
    if (!node.gate || node.gate.gate_id !== gateId) return node;
    // A durable gate's state is the journal's answer, and a draft recorded
    // in this window is not an entry in it. Rewriting the chip would dress
    // a LOCAL DRAFT in the one word a reader trusts as recorded, so a
    // runtime-stated gate keeps the run's answer and the draft is shown
    // beside it, labelled, instead.
    if (node.runtime !== null) return node;
    return Object.freeze({...node,
      gate: Object.freeze({...node.gate, state})});
  }));
}

function decide(state, event) {
  // An own-key check, not a lookup: a plain object inherits "constructor"
  // and friends, and an inherited truthy value must not become a gate state.
  const nextState = Object.hasOwn(DECISION_ACTIONS, event.action)
    ? DECISION_ACTIONS[event.action] : null;
  const gateNode = state.nodes.find((node) =>
    node.gate && node.gate.gate_id === event.gateId);
  const reason = typeof event.reason === "string" ? event.reason.trim() : "";
  const needsReason = ["request_changes", "waive"].includes(event.action);
  if (!gateNode || !nextState || !isId(event.actor)
      || reason.length > REASON_LIMIT || (needsReason && !reason)) {
    return Object.freeze({...state, decisionNotice:
      "Name the deciding Human and give a reason where one is required."});
  }
  return Object.freeze({...state,
    nodes: withGateState(state.nodes, event.gateId, nextState),
    // Rebuilt on a null prototype, for the reason EMPTY.decisions states.
    decisions: Object.freeze(Object.assign(Object.create(null),
      state.decisions,
      {[event.gateId]: Object.freeze({action: event.action, actor: event.actor,
        reason, recorded: "window-only"})})),
    decisionNotice: "Decision recorded as a LOCAL DRAFT in this window — "
      + "nothing submitted, and the run's own gate is untouched. "
      + "Nothing was executed.",
  });
}

// Composition stays closed: a new step takes a validated title, a harness id
// from the loaded registry (or null for none), and a placement relative to an
// existing node — after it, or parallel to it (sharing its parents). No free
// JSON, no paths, no vendor branches.
function compose(state, event) {
  const anchor = state.nodes.find((node) => node.node_id === event.anchorId);
  const title = typeof event.title === "string" ? event.title.trim() : "";
  const harness = event.harness === null ? null : String(event.harness || "");
  const registered = harness === null
    || state.registry.some((row) => row.id === harness);
  const placed = ["after", "parallel"].includes(event.placement);
  if (!anchor || !title || title.length > TITLE_LIMIT || !registered || !placed
      || !isId(event.nodeId) || state.nodes.some((n) => n.node_id === event.nodeId)) {
    return Object.freeze({...state, composeNotice:
      "Composition refused: use a fresh id, a title and a registered harness."});
  }
  // A composed step is a LOCAL DRAFT: it exists in this window, is written to
  // no run until a Human writes it, and says so on its own card. It states
  // its own position and carries no runtime document — nothing has run it, so
  // nothing may report on it, and that is what keeps it visibly apart from
  // every durable node beside it.
  const node = Object.freeze({node_id: event.nodeId, kind: "task", title,
    harness, health: "unknown", phase: "idle",
    capabilities: Object.freeze([]), evidence: Object.freeze([]), gate: null,
    loop: null, resources: Object.freeze([]), stage: null, binding: null,
    runtime: null, draft: true});
  const nodes = Object.freeze([...state.nodes, node]);
  const added = event.placement === "after"
    ? [Object.freeze({from: anchor.node_id, to: event.nodeId})]
    : state.edges.filter((edge) => edge.to === anchor.node_id)
        .map((edge) => Object.freeze({from: edge.from, to: event.nodeId}));
  const edges = Object.freeze([...state.edges, ...added]);
  const layout = computeLayout(nodes, edges);
  if (!layout) {
    return Object.freeze({...state, composeNotice: "Composition refused: cycle."});
  }
  return Object.freeze({...state, nodes, edges, layout, composeNotice:
    `Step "${title}" added as a LOCAL DRAFT — held in this window, submitted `
    + "to no run. Nothing was executed."});
}

//: What the shell says about the facts on screen, chosen by where they came
//: from. A durable read has reached a server and says so; a fixture has not
//: and says that. One notice for both would let either be read as the other.
const LOADED_NOTICE = Object.freeze({
  durable: "Durable graph loaded from the authoritative run read. The plan is "
    + "immutable; the run position beside it is computed, never stored.",
  fixture: "Fixture graph loaded. Nothing here reaches a server.",
});

// A save outcome is carried THROUGH the authoritative answer that follows it,
// and an answer carrying none leaves the one on screen alone. Resetting here
// meant any later re-read — a run frame, a reconnect — erased the sentence
// saying the plan was written. It is cleared where it becomes wrong instead:
// when the selected run changes, and nowhere else.
function carried(state, event) {
  return Object.hasOwn(event, "savePhase")
    ? {savePhase: event.savePhase, saveNotice: event.saveNotice}
    : {savePhase: state.savePhase, saveNotice: state.saveNotice};
}

function spoken(event, fallback) {
  return typeof event.notice === "string" && event.notice
    ? event.notice : fallback;
}

// The three answers a source can give, each with its own phase. A run that
// follows no graph is not a graph that could not be read, and neither is
// ever drawn as the other: an empty run is a normal answer, a refusal is a
// fault, and a load is facts.
function sourceArm(state, event) {
  // Readiness travels with the answer that grants it, and only a LANDED read
  // of the chosen run grants any: a superseded read never reaches here, and a
  // refused one is handled at its own arm below. A payload silent about it —
  // a fixture through the public seam — leaves it alone, because drawing is
  // no fact about which run the screen belongs to.
  const ready = Object.hasOwn(event, "ready")
    ? {writeReady: Boolean(event.ready)} : {writeReady: state.writeReady};
  if (event.type === "loaded") {
    return Object.freeze({...EMPTY, ...event.facts, phase: "loaded",
      ...carried(state, event), ...ready,
      notice: LOADED_NOTICE[event.facts.provenance.source]});
  }
  // A refusal grants nothing and confirms nothing. It cannot say the screen
  // belongs to the chosen run, so the write door stays shut; and a save
  // outcome still waiting on a read has not been confirmed by this one, so
  // it is never announced here as though it had been.
  if (event.type === "refused") {
    return Object.freeze({...EMPTY, phase: "refused",
      ...carried(state, event), writeReady: false,
      notice: spoken(event,
        "The graph payload was refused: it does not name a valid graph.")});
  }
  return Object.freeze({...EMPTY, phase: "empty",
    ...carried(state, event), ...ready,
    notice: spoken(event, EMPTY.notice)});
}

export function reduce(state, event) {
  if (!event || typeof event.type !== "string") return state;
  if (["loaded", "refused", "absent"].includes(event.type)) {
    return sourceArm(state, event);
  }
  // The write door, shut or opened by an answer about ONE run. Shutting it
  // also drops any save phase in flight: whatever that write is doing, this
  // screen is no longer the one entitled to report it.
  if (event.type === "ready") {
    return Object.freeze({...state, writeReady: event.ready === true,
      saveNotice: typeof event.notice === "string"
        ? event.notice : state.saveNotice,
      savePhase: event.ready === true ? state.savePhase : "idle"});
  }
  // The save door answers in every phase. A refusal that arrived after the
  // graph fell back to empty still has a Human waiting for it, and dropping
  // it here would leave a submitted plan with no reported outcome at all.
  if (event.type === "save") {
    return Object.freeze({...state,
      savePhase: ["idle", "submitting", "refused", "outcome-unknown"]
        .includes(event.phase) ? event.phase : "outcome-unknown",
      saveNotice: typeof event.notice === "string" ? event.notice : ""});
  }
  if (state.phase !== "loaded") return state;
  if (event.type === "select") {
    const known = state.nodes.some((node) => node.node_id === event.nodeId);
    if (!known) return state;
    const selection = state.selection === event.nodeId ? null : event.nodeId;
    // A decision status names the gate that was on screen when it was made;
    // carrying it under a different selection would assert a recording that
    // never happened there, so a selection change dismisses it.
    return Object.freeze({...state, selection, decisionNotice: ""});
  }
  if (event.type === "deselect") {
    return Object.freeze({...state, selection: null, decisionNotice: ""});
  }
  if (event.type === "decide") return decide(state, event);
  if (event.type === "compose") return compose(state, event);
  return state;
}
