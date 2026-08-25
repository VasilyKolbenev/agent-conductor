"use strict";
// The payload boundary, and nothing else: every closed vocabulary this window
// speaks, and the one function that turns an external payload into the facts
// graph-store.js reduces. It validates and REFUSES; it never repairs, never
// reaches the DOM, and never learns a wire spelling — the mapping into this
// shape is graph-adapter.js's and the socket is graph.js's.
//
// Its own rule, the one the December Command bought with a whole review
// round: a node's position comes from a fixture word or from a runtime
// document, never both and never neither. `projectNode` refuses rather than
// choosing, which is what keeps a plan's ceiling from being read as a run's
// position.
//
// Split out of graph-store.js when that file reached its line cap. The
// reducer kept the STATE; this file keeps the BOUNDARY, which is the seam
// they always had.
import {isId, isIdList, safeMode} from "./command-projection.js";

// Closed vocabularies, copied case-for-case from the contract layer
// (command/contracts.py, command-projection.js). None of these is invented
// here; tests/test_graph_source.py holds each copy to its source.
// A loop is a first-class step: the one way a cycle may appear on this field
// is an explicit bounded loop node ("repeat what feeds me, at most ×bound"),
// so the geometry stays a DAG while orchestration loops stay representable.
// The execution semantics of a pass belong to the runtime side; this window
// renders the declared bound and nothing more.
export const NODE_KINDS = Object.freeze(["task", "gate", "loop"]);
//: What a step may attach as configuration: the December Command's own six
//: resource words. Closed rows of {kind, name} — a name obeys the id grammar,
//: so no path, URI or free JSON can ride in as a resource.
export const RESOURCE_KINDS = Object.freeze(
  ["model", "tool", "skill", "session", "sandbox", "filesystem"]);
//: The five semantic stages of the default process, in their one order —
//: Dalio's five steps, fixed by the December Command as the product's
//: default graph. A stage is NOT the runtime phase: phase says what the
//: records prove happened; stage says which step of the process a task is.
//: The durable plan spells this attribute `stage` too, and holds the same
//: five words — graph_definition owns that vocabulary and this is a copy of
//: it, held to its source by tests/test_graph_source.py.
export const STAGE_NAMES = Object.freeze(
  ["goal", "identify", "diagnose", "design", "do"]);
export const HEALTH_STATES = Object.freeze(
  ["ready", "busy", "offline", "degraded", "unknown"]);
// Harness-level availability, distinct from a node's health: whether the
// product itself is offered as stable, offered behind a flag, or not offered.
// A fixture-interface vocabulary (the wording is the December Command's, not
// this module's invention); a registry row that omits it claims nothing and
// gets no chip.
export const AVAILABILITY_STATES = Object.freeze(
  ["available", "experimental", "unavailable"]);
export const CAPABILITY_NAMES = Object.freeze(
  ["dispatch", "review", "evidence", "stop", "retry", "switch"]);
export const EVIDENCE_KINDS = Object.freeze(["result", "diff", "tests", "status"]);
export const VERIFICATION_STATES = Object.freeze(
  ["unverified", "verified", "unavailable", "mismatch", "error"]);
// A node's phase is what the durable records could prove about it: no record
// (idle), a proposal, an accepted request, how far the current action was
// carried, or a result outcome — the position words are
// graph_projection.NODE_PHASES and the outcome words are contracts.py
// _RESULT_OUTCOMES, both verbatim.
//
// `observed` is the one that must never be read as a result: it says an
// execution boundary was REACHED, which is not success (safety law 9). It
// therefore lights the waiting channel, and the outcome — if any record
// states one — is a separate word on a separate line.
export const NODE_PHASES = Object.freeze(["idle", "proposed", "requested",
  "running", "observed",
  "succeeded", "failed", "cancelled", "rejected", "verification_failed",
  "unknown"]);
// `unknown` is the projection's refusal to choose, not a decision: a run
// holding two standing receipts for one gate supports two answers and
// therefore neither. It is NOT satisfied and must never draw as one.
export const GATE_STATES = Object.freeze(
  ["pending", "satisfied", "failed", "changes_requested", "waived", "unknown"]);
export const DECISION_ACTIONS = Object.freeze({
  approve: "satisfied",
  reject: "failed",
  request_changes: "changes_requested",
  waive: "waived",
});
// Status is a channel of its own (never the harness accent): which of the
// three semantic colours — or none — a phase may light.
export const PHASE_CHANNEL = Object.freeze({
  idle: "none", proposed: "wait", requested: "wait", running: "wait",
  observed: "wait", succeeded: "pass",
  failed: "fail", cancelled: "none", rejected: "fail",
  verification_failed: "fail", unknown: "none",
});
export const GATE_CHANNEL = Object.freeze({
  pending: "wait", satisfied: "pass", failed: "fail",
  changes_requested: "wait", waived: "none", unknown: "wait",
});
// The outcome of the CURRENT action, on its own channel because it is its own
// fact: a node can be `observed` with no outcome at all, and that pair says
// "the boundary was reached and nothing has reported a result" — which is the
// one reading a Cockpit owes and the one an inference would destroy.
export const OUTCOME_CHANNEL = Object.freeze({
  succeeded: "pass", failed: "fail", cancelled: "none", rejected: "fail",
  verification_failed: "fail", unknown: "none",
});
export const TITLE_LIMIT = 80;

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

// A closed shape: every level of the payload may carry exactly its own keys.
// Object.keys sees "__proto__" and "constructor" arriving as JSON own
// properties, so a prototype name is refused as any other unknown key is.
function ownKeysOnly(row, allowed) {
  return Object.keys(row).every((key) => allowed.includes(key));
}

// Registry rows are presentational: an ill-formed row is dropped and its
// harness draws the neutral badge, exactly as index.html loadRegistry decides.
// The graph structure below is not presentational, so there the same finding
// refuses the whole payload instead.
const HEX_RE = /^#[0-9a-f]{6}$/i;
const REGISTRY_KEYS = ["id", "display_name", "monogram", "accent_dark",
  "accent_light", "docs", "availability"];
// Registered monograms are two graphemes by the registry's own rule; eight
// code units leave unicode headroom without letting one unbroken mono token
// widen the rail. Names and ids share the node-title cap.
const MONOGRAM_LIMIT = 8;
export function projectRegistry(rows) {
  if (!Array.isArray(rows)) return [];
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== "object" || Array.isArray(row)) continue;
    if (!ownKeysOnly(row, REGISTRY_KEYS)) continue;
    const texts = [row.id, row.display_name, row.monogram];
    if (!texts.every((value) => typeof value === "string" && value)) continue;
    if (row.id.length > TITLE_LIMIT || row.display_name.length > TITLE_LIMIT
        || row.monogram.length > MONOGRAM_LIMIT) continue;
    // One row per id, first row wins — the same row every badge lookup
    // (registry.find) already answers with, so palette and badges agree.
    if (seen.has(row.id)) continue;
    if (!HEX_RE.test(row.accent_dark) || !HEX_RE.test(row.accent_light)) continue;
    if ("availability" in row
        && !AVAILABILITY_STATES.includes(row.availability)) continue;
    seen.add(row.id);
    out.push(Object.freeze({
      id: row.id, name: row.display_name, monogram: row.monogram,
      dark: row.accent_dark, light: row.accent_light,
      // The one field that becomes an href. Anything but https is dropped —
      // the same gate index.html applies before drawing its docs link — so a
      // javascript: or data: string arriving as registry data never renders.
      docs: typeof row.docs === "string" && row.docs.startsWith("https://")
        ? row.docs : "",
      availability: row.availability || "",
    }));
  }
  return out;
}

//: One deployment row: which product drives an instance, and which model that
//: instance PINS. Both are the run's frozen configuration's words and neither
//: appears in a graph document, where a plan names roles and never a machine.
const DEPLOYMENT_KEYS = ["instance_id", "adapter_id", "model"];

export function projectDeployment(rows) {
  // `model` is nullable and the null is load-bearing: it says the
  // configuration pinned none, so what runs is whatever the provider's own
  // configuration decides. A row that OMITTED the key would be a server too
  // old to answer the question, and this window must be able to tell the two
  // apart — so the key is required and its value may be null.
  if (!Array.isArray(rows)) return [];
  const out = [];
  const conflicted = new Set();
  for (const row of rows) {
    if (!row || typeof row !== "object" || Array.isArray(row)) continue;
    if (!ownKeysOnly(row, DEPLOYMENT_KEYS)) continue;
    if (!DEPLOYMENT_KEYS.every((key) => key in row)) continue;
    if (!isId(row.instance_id) || !isId(row.adapter_id)) continue;
    if (row.model !== null && !isId(row.model)) continue;
    // A second row for one instance is two answers to one question, and NEITHER
    // survives. "First wins" — the registry's rule, copied here at first — is
    // not a fact about the deployment: it hands whichever row arrived first the
    // authority to name a product and a model, and arrival order is the one
    // thing nobody controls. A Human would be shown a provider that may be
    // neither, with nothing on the screen saying so.
    //
    // Identical rows are dropped too. What is wrong is that the server ANSWERED
    // TWICE about one instance; two rows that happen to agree today are not
    // evidence about the pair that does not, and an exception for them would be
    // a comparison a reader has to trust instead of a rule they can state.
    //
    // Dropping the instance rather than refusing the whole projection is the
    // narrower answer: the graph stays readable, and the affected step falls
    // back to the state this window already has for a configuration it could
    // not read. A plan does not depend on this fact and must not vanish over it.
    if (out.some((kept) => kept.instanceId === row.instance_id)) {
      conflicted.add(row.instance_id);
      continue;
    }
    out.push(Object.freeze({
      instanceId: row.instance_id, adapterId: row.adapter_id,
      model: row.model,
    }));
  }
  return out.filter((row) => !conflicted.has(row.instanceId));
}

function projectEvidence(rows) {
  if (!Array.isArray(rows)) return null;
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== "object"
        || !ownKeysOnly(row, ["evidence_id", "kind", "verification"])
        || !isId(row.evidence_id)
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

// Sixteen rows bound the DOM the way the monogram cap bounds the rail; a
// fixture attaching more configuration than that is asking for a viewer,
// not a card.
const RESOURCE_LIMIT = 16;
function projectResources(rows) {
  if (rows === undefined) return Object.freeze([]);
  if (!Array.isArray(rows) || rows.length > RESOURCE_LIMIT) return null;
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== "object"
        || !ownKeysOnly(row, ["kind", "name"])
        || !RESOURCE_KINDS.includes(row.kind) || !isId(row.name)) return null;
    const key = `${row.kind} ${row.name}`;
    if (seen.has(key)) return null;
    seen.add(key);
    out.push(Object.freeze({kind: row.kind, name: row.name}));
  }
  return Object.freeze(out);
}

// The facts a loop node declares: how many passes it is allowed, which pass
// it is on, and which step a pass reopens. A pass REOPENS work — it executes
// nothing and counts as no effect; every effect still walks its own Human
// gate. The durable plan carries only two of the three: `bound` and `back_to`
// are a CEILING and a target, both written before the run starts. `pass` is
// the run's position and arrives in the runtime document, so it is refused
// here whenever that document states this node. back_to is display data
// validated at the payload level; it adds no edge and closes no cycle.
function projectLoop(row, stated) {
  if (row.kind !== "loop") {
    if (row.loop === null || row.loop === undefined) return null;
    return false;
  }
  if (!row.loop || typeof row.loop !== "object"
      || !ownKeysOnly(row.loop, ["bound", "pass", "back_to"])
      || !Number.isInteger(row.loop.bound)
      || row.loop.bound < 1 || row.loop.bound > 99) return false;
  const pass = "pass" in row.loop ? row.loop.pass : null;
  // A run's position may not ride in beside the plan's ceiling: when a
  // runtime document states this node, `pass` is ITS word and this key must
  // be empty. Otherwise one node would carry two passes and a reader would
  // have to guess which of them the run is on.
  if (!stated && pass !== null) return false;
  if (pass !== null && (!Number.isInteger(pass)
      || pass < 1 || pass > row.loop.bound)) return false;
  const backTo = "back_to" in row.loop ? row.loop.back_to : null;
  if (backTo !== null && !isId(backTo)) return false;
  return Object.freeze({bound: row.loop.bound, pass, backTo});
}

//: What one node's CURRENT action is observed to be doing. Every name here is
//: a name graph_definition.RUNTIME_ONLY_FIELDS refuses inside a plan, which is
//: what keeps a ceiling and a position from ever being read as each other.
//: The wire spellings are the adapter's to translate; by the time a row
//: arrives here it is already this window's own closed shape.
const RUNTIME_KEYS = ["phase", "outcome", "attempt_ids", "observed_at",
  "evidence_refs", "decision", "pass", "bound_reached"];
//: A bound on the join keys one node may carry: they are what a reader uses
//: to find an earlier attempt, and a longer list wants a viewer, not a card.
const RUNTIME_ID_LIMIT = 64;
function runtimeIds(value) {
  if (!Array.isArray(value) || value.length > RUNTIME_ID_LIMIT) return null;
  if (!isIdList(value)) return null;
  if (new Set(value).size !== value.length) return null;
  return Object.freeze([...value]);
}

function projectRuntime(row) {
  if (row.runtime === undefined || row.runtime === null) return null;
  const values = row.runtime;
  if (typeof values !== "object" || Array.isArray(values)
      || !ownKeysOnly(values, RUNTIME_KEYS)
      || !NODE_PHASES.includes(values.phase)) return false;
  const outcome = "outcome" in values ? values.outcome : null;
  if (outcome !== null && !Object.hasOwn(OUTCOME_CHANNEL, outcome)) return false;
  const observedAt = "observed_at" in values ? values.observed_at : null;
  if (observedAt !== null && !instantIsValid(observedAt)) return false;
  const attempts = runtimeIds(values.attempt_ids);
  const evidenceRefs = runtimeIds(values.evidence_refs);
  if (!attempts || !evidenceRefs) return false;
  // A decision is a gate's word and a pass is a loop's. A runtime row that
  // carries the other layer's word is refused rather than trimmed: this
  // projection attaches nothing at random, so a word out of place says the
  // join that produced the row was wrong about which node it described.
  const isGate = row.kind === "gate", isLoop = row.kind === "loop";
  if (("decision" in values) !== isGate) return false;
  if (("pass" in values) !== isLoop) return false;
  if (("bound_reached" in values) !== isLoop) return false;
  if (isGate && !GATE_STATES.includes(values.decision)) return false;
  if (isLoop) {
    if (!Number.isInteger(values.pass) || values.pass < 0
        || typeof values.bound_reached !== "boolean") return false;
    // The run counted its passes against a ceiling; if the two documents
    // disagree about whether that ceiling was reached, they are not
    // describing one loop and no arithmetic here may reconcile them.
    const bound = row.loop && row.loop.bound;
    if (values.bound_reached !== (values.pass >= bound)) return false;
  }
  return Object.freeze({
    phase: values.phase, outcome, observedAt, attempts, evidenceRefs,
    decision: isGate ? values.decision : null,
    pass: isLoop ? values.pass : null,
    boundReached: isLoop ? values.bound_reached : null,
  });
}

//: What the PLAN binds this step to: an instance the run's frozen
//: configuration declares, the one capability the step will ask for, and the
//: payload that capability's schema admitted. Which adapter serves that
//: instance is the configuration's fact and appears nowhere here — a
//: provider is data the registry may name, never a branch this window takes.
const BINDING_KEYS = ["instance_id", "capability", "arguments"];
const ARGUMENT_LIMIT = 16;
const ARGUMENT_TEXT_LIMIT = 200;
function argumentValue(value) {
  if (typeof value === "string") return value.length <= ARGUMENT_TEXT_LIMIT;
  return Array.isArray(value) && value.length <= ARGUMENT_LIMIT
    && value.every((item) => typeof item === "string"
      && item.length <= ARGUMENT_TEXT_LIMIT);
}

function projectBinding(row) {
  if (row.binding === undefined || row.binding === null) return null;
  const values = row.binding;
  if (typeof values !== "object" || Array.isArray(values)
      || !ownKeysOnly(values, BINDING_KEYS)
      || !isId(values.instance_id)
      || !CAPABILITY_NAMES.includes(values.capability)) return false;
  const payload = values.arguments;
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return false;
  }
  const names = Object.keys(payload);
  if (names.length > ARGUMENT_LIMIT) return false;
  // Every argument field is a closed id or a closed vocabulary word on the
  // wire, so a nested object or a number here is a shape this window was
  // never handed — displayed, it would be a claim about a payload nobody
  // validated in this form.
  for (const name of names) {
    if (!isId(name) || !argumentValue(payload[name])) return false;
  }
  return Object.freeze({
    instanceId: values.instance_id, capability: values.capability,
    // The payload as it was READ, frozen: the plan a Human asks a run to
    // follow is rebuilt from this, so it must be the admitted value and not
    // a rendering of it. `argumentRows` beside it is for the screen alone.
    arguments: Object.freeze(Object.fromEntries(names.map((name) =>
      [name, Array.isArray(payload[name])
        ? Object.freeze([...payload[name]]) : payload[name]]))),
    argumentRows: Object.freeze([...names].sort().map((name) => Object.freeze({
      name, value: Array.isArray(payload[name])
        ? payload[name].join(", ") : payload[name]}))),
  });
}

// A stage is optional, task-only, and unique: two nodes claiming one stage
// would let a later step absorb an earlier one — exactly the collapse the
// five-step process forbids (Diagnose is not a part of Identify).
function stageIsValid(row) {
  if (!("stage" in row) || row.stage === null) return true;
  return row.kind === "task" && STAGE_NAMES.includes(row.stage);
}

// ONE source per fact, made structural. A node's position — health and phase
// here, gate state, pass and evidence at their own arms — is stated by a
// fixture word or by the runtime document, never both and never neither.
// Splicing the layers into one key is how a plan's ceiling came to be read as
// a run's position, so this relation keeps them disjoint rather than the
// callers' good manners.
function positionIsSingleSourced(row, stated) {
  if (stated) {
    return HEALTH_STATES.includes(row.health) && NODE_PHASES.includes(row.phase);
  }
  return row.health === null && row.phase === null;
}

const NODE_KEYS = ["node_id", "kind", "title", "harness", "health", "phase",
  "capabilities", "evidence", "gate", "loop", "resources", "stage",
  "binding", "runtime"];
function projectNode(row) {
  if (!row || typeof row !== "object" || !isId(row.node_id)) return null;
  if (!ownKeysOnly(row, NODE_KEYS)) return null;
  if (!NODE_KINDS.includes(row.kind)) return null;
  if (typeof row.title !== "string" || !row.title.trim()
      || row.title.length > TITLE_LIMIT) return null;
  if (row.harness !== null
      && (typeof row.harness !== "string" || !row.harness)) return null;
  const runtime = projectRuntime(row);
  const binding = projectBinding(row);
  if (runtime === false || binding === false) return null;
  const stated = runtime === null;
  if (!positionIsSingleSourced(row, stated)) return null;
  const capabilities = projectCapabilities(row.capabilities);
  const evidence = projectEvidence(row.evidence);
  const resources = projectResources(row.resources);
  const loop = projectLoop(row, stated);
  if (!capabilities || !evidence || !resources || loop === false) return null;
  // Runtime evidence arrives as identifiers alone — no kind, no verification
  // — so a runtime-stated node carries no evidence ROW at all. A row here
  // would be a verification claim the projection never made.
  if (!stated && evidence.length) return null;
  if (!stageIsValid(row)) return null;
  const stage = "stage" in row && row.stage !== null ? row.stage : null;
  let gate = null;
  if (row.kind === "gate") {
    if (!row.gate || typeof row.gate !== "object"
        || !ownKeysOnly(row.gate, ["gate_id", "state"])
        || !isId(row.gate.gate_id)) return null;
    if (stated ? !GATE_STATES.includes(row.gate.state)
      : row.gate.state !== null) return null;
    gate = Object.freeze({gate_id: row.gate.gate_id, state: row.gate.state});
  } else if (row.gate !== null && row.gate !== undefined) {
    return null;
  }
  return Object.freeze({node_id: row.node_id, kind: row.kind,
    title: row.title.trim(), harness: row.harness,
    health: stated ? row.health : null, phase: stated ? row.phase : null,
    capabilities, evidence, gate, loop, resources, stage, binding, runtime,
    draft: false});
}

function projectEdges(rows, ids) {
  if (!Array.isArray(rows)) return null;
  const seen = new Set();
  const out = [];
  for (const row of rows) {
    if (!row || typeof row !== "object"
        || !ownKeysOnly(row, ["from", "to"])
        || !isId(row.from) || !isId(row.to)) return null;
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
    if (!row || typeof row !== "object"
        || !ownKeysOnly(row, ["event_id", "at", "node_id", "phase"])
        || !isId(row.event_id) || seen.has(row.event_id)) return null;
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

//: Where this graph came from, said in the value rather than left to the
//: reader. `fixture` is this window's own demonstration data and reaches no
//: server; `durable` is a plan the run's journal already holds, and it is the
//: only source that may carry a digest. The two never share a spelling, so a
//: LOCAL DRAFT can never be rendered with a durable graph's words.
export const GRAPH_SOURCES = Object.freeze(["fixture", "durable"]);
const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;
export const FIXTURE_SOURCE = Object.freeze(
  {source: "fixture", graphId: null, digest: null});

function projectProvenance(value) {
  if (value === undefined || value === null) return FIXTURE_SOURCE;
  if (typeof value !== "object" || Array.isArray(value)
      || !ownKeysOnly(value, ["source", "graphId", "digest"])
      || !GRAPH_SOURCES.includes(value.source)) return null;
  const graphId = "graphId" in value ? value.graphId : null;
  const digest = "digest" in value ? value.digest : null;
  // A digest is what makes a durable plan checkable, and a fixture has none
  // to offer. Letting a fixture carry one would put this window's own
  // demonstration data behind the one mark a reader trusts.
  if (value.source === "fixture") {
    return graphId === null && digest === null ? FIXTURE_SOURCE : null;
  }
  if (!isId(graphId) || typeof digest !== "string"
      || !DIGEST_RE.test(digest)) return null;
  return Object.freeze({source: "durable", graphId, digest});
}

// Every identity is unique and every reference names a real other node. A
// node id, a gate id and a stage are each a KEY: two nodes sharing one let a
// single Human decision flip a gate nobody decided, or a later step absorb an
// earlier one. A loop's return target is display data, but a ghost or self
// target draws a promise the graph cannot keep.
function identitiesAreDistinct(nodes, ids) {
  if (ids.size !== nodes.length) return false;
  const gateIds = nodes.flatMap((node) => (node.gate ? [node.gate.gate_id] : []));
  if (new Set(gateIds).size !== gateIds.length) return false;
  const stages = nodes.flatMap((node) => (node.stage ? [node.stage] : []));
  if (new Set(stages).size !== stages.length) return false;
  return nodes.every((node) => !node.loop || node.loop.backTo === null
    || (ids.has(node.loop.backTo) && node.loop.backTo !== node.node_id));
}

// Two documents describe one durable graph, so either every node carries the
// run's position or none does — a partial join leaves some steps at the
// plan's word while their neighbours show the run's, one screen with two
// meanings for one chip. Provenance answers for the same fact: a digest names
// a durable plan, so carrying one while stating no position, or the reverse,
// is not one graph read once.
function sourcesAgreeAcrossNodes(nodes, provenance) {
  const positioned = nodes.filter((node) => node.runtime !== null).length;
  if (positioned && positioned !== nodes.length) return false;
  return (provenance.source === "durable") === (positioned === nodes.length);
}

export function projectPayload(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }
  // No fixture_schema here: the version pin is the adapter's fact alone,
  // stripped before the payload reaches this module.
  if (!ownKeysOnly(payload,
    ["run", "registry", "nodes", "edges", "timeline", "provenance",
      "deployment"])) {
    return null;
  }
  const provenance = projectProvenance(payload.provenance);
  if (!provenance) return null;
  if (!payload.run || typeof payload.run !== "object"
      || !ownKeysOnly(payload.run, ["run_id", "mode"])
      || !isId(payload.run.run_id)) return null;
  if (!Array.isArray(payload.nodes) || !payload.nodes.length) return null;
  const nodes = payload.nodes.map(projectNode);
  if (nodes.some((node) => node === null)) return null;
  const ids = new Set(nodes.map((node) => node.node_id));
  if (!identitiesAreDistinct(nodes, ids)) return null;
  if (!sourcesAgreeAcrossNodes(nodes, provenance)) return null;
  const edges = projectEdges(payload.edges, ids);
  const timeline = projectTimeline(payload.timeline, ids);
  if (!edges || !timeline) return null;
  const layout = computeLayout(nodes, edges);
  if (!layout) return null;
  return Object.freeze({
    run: Object.freeze({runId: payload.run.run_id, mode: safeMode(payload.run.mode)}),
    registry: Object.freeze(projectRegistry(payload.registry)),
    deployment: Object.freeze(projectDeployment(payload.deployment)),
    nodes: Object.freeze(nodes), edges, layout, timeline, provenance,
  });
}
