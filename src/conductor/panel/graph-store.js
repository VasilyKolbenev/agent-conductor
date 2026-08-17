"use strict";
// Provider-neutral facts for the ALPHA-2 Graph window: no DOM, no network, and
// no vendor branch anywhere. Every difference between harness products arrives
// as data — registry rows, capability lists, health states — so an unsupported
// action is simply absent from the data and therefore absent from the screen.
//
// This module is the single reducer the Graph window runs on. It validates the
// fixture payload at the boundary (refuse, never repair), computes the branch
// layout once per load, and answers every render from one frozen state value.
// The wire is deliberately not here: until the frozen API fixtures arrive from
// the runtime side, the only source is the `conductGraph.load` seam graph.js
// exposes, and this file cannot tell the difference — that seam is the point.
import {isId, safeMode} from "./command-projection.js";

// Closed vocabularies, copied case-for-case from the contract layer
// (command/contracts.py, command-projection.js). None of these is invented
// here; tests/test_graph_source.py holds each copy to its source.
export const NODE_KINDS = Object.freeze(["task", "gate"]);
export const HEALTH_STATES = Object.freeze(
  ["ready", "busy", "offline", "degraded", "unknown"]);
export const CAPABILITY_NAMES = Object.freeze(
  ["dispatch", "review", "evidence", "stop", "retry", "switch"]);
export const EVIDENCE_KINDS = Object.freeze(["result", "diff", "tests", "status"]);
export const VERIFICATION_STATES = Object.freeze(
  ["unverified", "verified", "unavailable", "mismatch", "error"]);
// A node's phase is what the durable records could prove about it: no record
// (idle), a proposal, an accepted request, or a result outcome — the outcome
// vocabulary is contracts.py _RESULT_OUTCOMES verbatim.
export const NODE_PHASES = Object.freeze(["idle", "proposed", "requested",
  "succeeded", "failed", "cancelled", "rejected", "verification_failed",
  "unknown"]);
export const GATE_STATES = Object.freeze(
  ["pending", "satisfied", "failed", "changes_requested", "waived"]);
export const DECISION_ACTIONS = Object.freeze({
  approve: "satisfied",
  reject: "failed",
  request_changes: "changes_requested",
  waive: "waived",
});
// Status is a channel of its own (never the harness accent): which of the
// three semantic colours — or none — a phase may light.
export const PHASE_CHANNEL = Object.freeze({
  idle: "none", proposed: "wait", requested: "wait", succeeded: "pass",
  failed: "fail", cancelled: "none", rejected: "fail",
  verification_failed: "fail", unknown: "none",
});
export const GATE_CHANNEL = Object.freeze({
  pending: "wait", satisfied: "pass", failed: "fail",
  changes_requested: "wait", waived: "none",
});
const TITLE_LIMIT = 80;
// The boundary twin of the reason input's maxlength: the DOM cap is advice,
// this one is the rule.
const REASON_LIMIT = 200;

// The frozen UTC-instant grammar (command-projection.js instantIsValid states
// the same rule beside the production contract). Both copies answer the one
// corpus tests/fixtures/utc_instant_parity_corpus.json; the browser suite runs
// it against this function so the copies cannot drift apart silently.
const UTC_INSTANT =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:Z|\+00:00)$/;
const MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
export function instantIsValid(value) {
  if (typeof value !== "string") return false;
  const m = UTC_INSTANT.exec(value);
  if (!m) return false;
  const year = Number(m[1]), month = Number(m[2]), day = Number(m[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const maxDay = month === 2 && leap ? 29 : MONTH_LENGTHS[month - 1];
  if (day < 1 || day > maxDay) return false;
  const hour = Number(m[4]), minute = Number(m[5]), second = Number(m[6]);
  return hour <= 23 && minute <= 59 && second <= 59;
}

// Registry rows are presentational: an ill-formed row is dropped and its
// harness draws the neutral badge, exactly as index.html loadRegistry decides.
// The graph structure below is not presentational, so there the same finding
// refuses the whole payload instead.
const HEX_RE = /^#[0-9a-f]{6}$/i;
export function projectRegistry(rows) {
  if (!Array.isArray(rows)) return [];
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    const texts = [row.id, row.display_name, row.monogram];
    if (!texts.every((value) => typeof value === "string" && value)) continue;
    if (!HEX_RE.test(row.accent_dark) || !HEX_RE.test(row.accent_light)) continue;
    out.push(Object.freeze({
      id: row.id, name: row.display_name, monogram: row.monogram,
      dark: row.accent_dark, light: row.accent_light,
      // The one field that becomes an href. Anything but https is dropped —
      // the same gate index.html applies before drawing its docs link — so a
      // javascript: or data: string arriving as registry data never renders.
      docs: typeof row.docs === "string" && row.docs.startsWith("https://")
        ? row.docs : "",
    }));
  }
  return out;
}

function projectEvidence(rows) {
  if (!Array.isArray(rows)) return null;
  const out = [];
  for (const row of rows) {
    if (!row || !isId(row.evidence_id)
        || !EVIDENCE_KINDS.includes(row.kind)
        || !VERIFICATION_STATES.includes(row.verification)) return null;
    out.push(Object.freeze({evidence_id: row.evidence_id, kind: row.kind,
      verification: row.verification}));
  }
  return Object.freeze(out);
}

function projectCapabilities(names) {
  if (!Array.isArray(names)) return null;
  if (!names.every((name) => CAPABILITY_NAMES.includes(name))) return null;
  if (new Set(names).size !== names.length) return null;
  return Object.freeze([...names].sort());
}

function projectNode(row) {
  if (!row || typeof row !== "object" || !isId(row.node_id)) return null;
  if (!NODE_KINDS.includes(row.kind)) return null;
  if (typeof row.title !== "string" || !row.title.trim()
      || row.title.length > TITLE_LIMIT) return null;
  if (row.harness !== null
      && (typeof row.harness !== "string" || !row.harness)) return null;
  if (!HEALTH_STATES.includes(row.health)) return null;
  if (!NODE_PHASES.includes(row.phase)) return null;
  const capabilities = projectCapabilities(row.capabilities);
  const evidence = projectEvidence(row.evidence);
  if (!capabilities || !evidence) return null;
  let gate = null;
  if (row.kind === "gate") {
    if (!row.gate || !isId(row.gate.gate_id)
        || !GATE_STATES.includes(row.gate.state)) return null;
    gate = Object.freeze({gate_id: row.gate.gate_id, state: row.gate.state});
  } else if (row.gate !== null && row.gate !== undefined) {
    return null;
  }
  return Object.freeze({node_id: row.node_id, kind: row.kind,
    title: row.title.trim(), harness: row.harness, health: row.health,
    phase: row.phase, capabilities, evidence, gate});
}

function projectEdges(rows, ids) {
  if (!Array.isArray(rows)) return null;
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    if (!row || !isId(row.from) || !isId(row.to)) return null;
    if (!ids.has(row.from) || !ids.has(row.to) || row.from === row.to) return null;
    const key = `${row.from} ${row.to}`;
    if (seen.has(key)) return null;
    seen.add(key);
    out.push(Object.freeze({from: row.from, to: row.to}));
  }
  return Object.freeze(out);
}

function projectTimeline(rows, ids) {
  if (!Array.isArray(rows)) return null;
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    if (!row || !isId(row.event_id) || seen.has(row.event_id)) return null;
    if (!instantIsValid(row.at) || !ids.has(row.node_id)
        || !NODE_PHASES.includes(row.phase)) return null;
    seen.add(row.event_id);
    out.push(Object.freeze({event_id: row.event_id, at: row.at,
      node_id: row.node_id, phase: row.phase}));
  }
  // Raw string order is NOT time order: the grammar admits a variable-width
  // fraction and two UTC spellings, and "…00Z" sorts after "…00.900Z". The
  // key is the genuinely fixed-width 19-character prefix plus the fraction
  // padded to nine digits, which collapses Z against +00:00 and makes plain
  // code-unit comparison the time comparison. The index keeps ties stable.
  const keyOf = (at) =>
    `${at.slice(0, 19)}.${(UTC_INSTANT.exec(at)[7] || "").padEnd(9, "0")}`;
  return Object.freeze(out.map((row, index) => [keyOf(row.at), index, row])
    .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] - b[1]))
    .map((entry) => entry[2]));
}

// Layered layout, computed once per load. Depth is the longest path from a
// root, so a join sits one column after its slowest branch; the row is the
// order nodes were declared in, which keeps the fixture author in charge of
// vertical reading order. A cycle has no layer, so it refuses the payload.
export function computeLayout(nodes, edges) {
  const parents = new Map(nodes.map((node) => [node.node_id, []]));
  for (const edge of edges) parents.get(edge.to).push(edge.from);
  const depth = new Map();
  const visiting = new Set();
  function resolve(id) {
    if (depth.has(id)) return depth.get(id);
    if (visiting.has(id)) return null;
    visiting.add(id);
    let level = 0;
    for (const parent of parents.get(id)) {
      const above = resolve(parent);
      if (above === null) return null;
      level = Math.max(level, above + 1);
    }
    visiting.delete(id);
    depth.set(id, level);
    return level;
  }
  const cells = {};
  const rowsUsed = [];
  for (const node of nodes) {
    const column = resolve(node.node_id);
    if (column === null) return null;
    rowsUsed[column] = (rowsUsed[column] || 0);
    cells[node.node_id] = Object.freeze({column, row: rowsUsed[column]});
    rowsUsed[column] += 1;
  }
  return Object.freeze({
    columns: rowsUsed.length,
    rows: Math.max(0, ...rowsUsed),
    cells: Object.freeze(cells),
  });
}

export function projectPayload(payload) {
  if (!payload || typeof payload !== "object") return null;
  if (payload.fixture_schema !== 1) return null;
  if (!payload.run || !isId(payload.run.run_id)) return null;
  if (!Array.isArray(payload.nodes) || !payload.nodes.length) return null;
  const nodes = payload.nodes.map(projectNode);
  if (nodes.some((node) => node === null)) return null;
  const ids = new Set(nodes.map((node) => node.node_id));
  if (ids.size !== nodes.length) return null;
  // A gate id is a decision key — the ledger and every state rewrite go
  // through it — so two gates sharing one would let a single Human decision
  // flip a gate nobody decided. The same ambiguity node ids are refused for.
  const gateIds = nodes.flatMap((node) => (node.gate ? [node.gate.gate_id] : []));
  if (new Set(gateIds).size !== gateIds.length) return null;
  const edges = projectEdges(payload.edges, ids);
  const timeline = projectTimeline(payload.timeline, ids);
  if (!edges || !timeline) return null;
  const layout = computeLayout(nodes, edges);
  if (!layout) return null;
  return Object.freeze({
    run: Object.freeze({runId: payload.run.run_id, mode: safeMode(payload.run.mode)}),
    registry: Object.freeze(projectRegistry(payload.registry)),
    nodes: Object.freeze(nodes), edges, layout, timeline,
  });
}

export const EMPTY = Object.freeze({
  phase: "empty",   // empty | loaded | refused
  notice: "No run graph loaded. This window renders fixture data only.",
  run: Object.freeze({runId: "", mode: "unknown"}),
  registry: Object.freeze([]),
  nodes: Object.freeze([]),
  edges: Object.freeze([]),
  layout: Object.freeze({columns: 0, rows: 0, cells: Object.freeze({})}),
  timeline: Object.freeze([]),
  selection: null,
  // The local decision ledger: gate_id → what the Human drafted here. Alpha
  // records it in this window and nowhere else; the notice says so.
  decisions: Object.freeze({}),
  decisionNotice: "",
});

function withGateState(nodes, gateId, state) {
  return Object.freeze(nodes.map((node) => {
    if (!node.gate || node.gate.gate_id !== gateId) return node;
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
    decisions: Object.freeze({...state.decisions,
      [event.gateId]: Object.freeze({action: event.action, actor: event.actor,
        reason, recorded: "fixture-only"})}),
    decisionNotice:
      "Decision recorded in this window's fixture only. Nothing was executed.",
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
    return Object.freeze({...state, notice:
      "Composition refused: use a fresh id, a title and a registered harness."});
  }
  const node = Object.freeze({node_id: event.nodeId, kind: "task", title,
    harness, health: "unknown", phase: "idle",
    capabilities: Object.freeze([]), evidence: Object.freeze([]), gate: null});
  const nodes = Object.freeze([...state.nodes, node]);
  const added = event.placement === "after"
    ? [Object.freeze({from: anchor.node_id, to: event.nodeId})]
    : state.edges.filter((edge) => edge.to === anchor.node_id)
        .map((edge) => Object.freeze({from: edge.from, to: event.nodeId}));
  const edges = Object.freeze([...state.edges, ...added]);
  const layout = computeLayout(nodes, edges);
  if (!layout) {
    return Object.freeze({...state, notice: "Composition refused: cycle."});
  }
  return Object.freeze({...state, nodes, edges, layout,
    notice: `Step "${title}" added to the fixture graph. Nothing was executed.`});
}

export function reduce(state, event) {
  if (!event || typeof event.type !== "string") return state;
  if (event.type === "loaded") {
    return Object.freeze({...EMPTY, ...event.facts, phase: "loaded",
      notice: "Fixture graph loaded. Nothing here reaches a server."});
  }
  if (event.type === "refused") {
    return Object.freeze({...EMPTY, phase: "refused",
      notice: "The fixture payload was refused: it does not name a valid graph."});
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
