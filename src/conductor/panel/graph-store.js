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
  // Which product drives each instance this run's plan names, and which
  // model that instance pins. Empty until a read supplies it; a drawing
  // with no deployment rows says nothing about a deployment rather than
  // saying there is none.
  deployment: Object.freeze([]),
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

const DRAFT_HELD = "Durable graph loaded from the authoritative run read, and "
  + "the steps composed in this window are still held beside it as a LOCAL "
  + "DRAFT. The plan the run follows is immutable; nothing composed here has "
  + "been written to it.";
const DRAFT_DISPLACED = "Durable graph loaded from the authoritative run read. "
  + "The steps composed in this window could not be placed on the plan it "
  + "carries, so they are no longer drawn — and nothing was written to the run.";

// An authoritative read REPLACES the drawing, and for everything this window
// merely DREW that is right: a fixture is not a fact about a run, and the
// reconnect that proves it has its own test. It is wrong for what a Human
// COMPOSED and has not written. Unwritten work is not a fact about the run
// either, and losing it to a transport event -- a dropped socket, a reconnect,
// a state greeting -- is not a decision anybody made.
//
// So exactly the composed nodes are carried across, by the one mark that tells
// them apart: `compose` sets `draft: true`, and every projected node, fixture
// or durable, carries `draft: false`. Nothing else is kept, which is why the
// ruling for a seeded drawing stands untouched.
//
// Three things it will NOT do. It never crosses a run change, because carrying
// one run's unwritten step onto another run's screen would offer it as that
// run's. It never keeps an id the durable plan now carries -- once the run
// follows a plan naming that step, the run is the authority on it. And it
// never draws an edge with an end the merged drawing does not hold, which
// would be a line from nothing.
function heldDraft(state, facts) {
  const drafts = state.nodes.filter((node) => node.draft);
  if (!drafts.length || state.run.runId !== facts.run.runId) {
    return {facts: null, notice: ""};
  }
  const arrived = new Set(facts.nodes.map((node) => node.node_id));
  const kept = drafts.filter((node) => !arrived.has(node.node_id));
  if (!kept.length) return {facts: null, notice: ""};
  const keptIds = new Set(kept.map((node) => node.node_id));
  const nodes = Object.freeze([...facts.nodes, ...kept]);
  const known = new Set(nodes.map((node) => node.node_id));
  const local = state.edges.filter((edge) =>
    (keptIds.has(edge.from) || keptIds.has(edge.to))
    && known.has(edge.from) && known.has(edge.to));
  const edges = Object.freeze([...facts.edges, ...local]);
  const layout = computeLayout(nodes, edges);
  // A composed step whose anchor the run's plan does not have cannot be drawn
  // on it. That is said out loud rather than drawn wrongly or dropped quietly.
  if (!layout) return {facts: null, notice: DRAFT_DISPLACED};
  return {facts: {nodes, edges, layout}, notice: DRAFT_HELD};
}

const LOCAL_HELD = "This run follows no graph yet, and the plan on screen is "
  + "held in this window rather than by the run. Nothing here has been written; "
  + "the save door is what writes it.";

// A run that follows NO graph contributes no durable fact, so a drawing this
// window holds is hiding nothing -- and it is the only copy of work a Human has
// not written yet. Resetting to EMPTY here erased the entire writable road,
// `empty -> start from the default -> compose -> save`, on every reconnect,
// because a dropped socket always ends in a re-read. Measured before the fix:
// nine steps on screen, zero after the socket came back.
//
// Held WHOLE rather than by the draft mark. An earlier fix kept only the nodes
// `compose` had added, which protected the one road nothing can be saved on --
// a durable run's plan is immutable -- and left the road that matters broken. A
// plan missing eight of its nine steps is not a plan.
//
// It never crosses a run change: choosing another run discards it at that door,
// where the Human's own action is, rather than by a comparison here.
function localPlan(state) {
  // A DURABLE drawing is never held across an answer. It belongs to the run
  // that answered with it, and carrying it into a different run's "follows no
  // graph" would show one run's written plan as another run's unwritten one --
  // the mixing this whole seam exists to refuse, in its worst direction.
  if (state.phase !== "loaded" || !state.nodes.length
      || state.provenance.source === "durable") return {};
  return {phase: "loaded", nodes: state.nodes, edges: state.edges,
          layout: state.layout, provenance: state.provenance,
          registry: state.registry, deployment: state.deployment,
          run: state.run, selection: state.selection};
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
    const held = heldDraft(state, event.facts);
    return Object.freeze({...EMPTY, ...event.facts, ...held.facts,
      phase: "loaded", ...carried(state, event), ...ready,
      notice: held.notice || LOADED_NOTICE[event.facts.provenance.source]});
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
  const local = localPlan(state);
  return Object.freeze({...EMPTY, phase: "empty", ...local,
    ...carried(state, event), ...ready,
    notice: local.nodes ? LOCAL_HELD : spoken(event, EMPTY.notice)});
}

export function reduce(state, event) {
  if (!event || typeof event.type !== "string") return state;
  // The one door a held local plan is let go through, and it is the Human's own
  // action rather than a transport event: choosing another run. A plan drawn
  // against one run is not a draft of another's, and the save door beside it
  // writes to whichever run is selected -- so it is dropped HERE, before the
  // new run's read goes out, and never carried across on the strength of a
  // comparison made later.
  if (event.type === "discard") {
    // Only what this window HOLDS is let go. A DURABLE drawing already on
    // screen is the previous run's own answer, and it stays until the new
    // run's read lands -- a separate promise, kept deliberately, with the
    // write door shut in the meantime so nothing can be built from it. Blanking
    // it here would break that and tell the Human nothing in exchange.
    return state.provenance.source === "durable" ? state : EMPTY;
  }
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
