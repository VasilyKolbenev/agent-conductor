"use strict";
// The input adapter, and deliberately nothing else: the single place where an
// external payload becomes the panel-internal fixture shape graph-store.js
// validates. fixture_schema 1 is PANEL-INTERNAL — it is NOT the wire
// contract, and neither is the shape this file builds out of the wire's two
// documents. The mapping lives HERE and nowhere else, so the store, the
// reducer and the visual layer never learn a wire spelling.
//
// The wire hands over a PAIR: an immutable `definition` — the plan a run
// follows, which is written once and can never be edited — and a `runtime`
// projection computed from the durable records and stored nowhere. They share
// no word but the join, and this file is the only place they are ever spliced
// into one drawing. Which of the two a fact came from stays visible in the
// value it lands on: a runtime-stated node's fixture keys are all null, and
// the store refuses any node that answers from both sources at once.
//
// This adapter opens no socket. Reading and writing are transport, and
// transport is graph.js; what happens to a payload's SHAPE is here.

export const INTERNAL_SCHEMA = 1;
//: `GraphDefinition.schema_version`, the one durable graph form this adapter
//: can read. A definition announcing another version is refused out loud
//: rather than guessed at — a mapping nobody wrote is not a mapping.
export const WIRE_SCHEMA = 2;

export function adaptPayload(external) {
  if (!external || typeof external !== "object" || Array.isArray(external)) {
    return null;
  }
  if (external.fixture_schema !== INTERNAL_SCHEMA) return null;
  // The schema pin is this adapter's own fact and travels no further: the
  // store never sees the field, so a load that skipped this function would
  // hand the store a key it refuses — every fixture in the suite then pins
  // the call site behaviourally, not by a source grep.
  const {fixture_schema: _, ...internal} = external;
  return internal;
}

//: `graph_definition.RUNTIME_ONLY_FIELDS`, copied word for word. These are
//: the names a durable plan REFUSES, and the reason the copy lives here is
//: below in `graphRequestBody`: a plan this window submits is screened
//: against them before it is ever offered to the route, so a run's position
//: cannot ride into an immutable record on the back of a redrawn node.
export const RUNTIME_ONLY_FIELDS = Object.freeze([
  "attempt_id", "attempt_ids", "attempts", "availability", "bound_reached",
  "decided_at", "decision", "decisions", "evidence", "evidence_refs",
  "health", "observed_at", "outcome", "outcomes", "pass", "passes", "phase",
  "started_at", "state", "status", "timeline",
]);
//: The one node field whose value is a capability's own payload, exempt from
//: the walk for the same reason production exempts it: its keys belong to the
//: capability's schema, not to the graph's vocabulary. It is lifted out
//: before the walk runs, never excused by the walk itself.
const EXEMPT_FIELD = "arguments";

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function keysWithin(allowed, value) {
  return Object.keys(value).every((key) => allowed.includes(key));
}

//: The gate word the runtime projection answers with when no receipt stands.
//: This window's own word for that is `pending`, so the translation happens
//: here — the store never sees `idle` and the runtime never sees `pending`.
const GATE_IDLE = "idle";

const DEFINITION_KEYS = ["schema_version", "graph_id", "run_id", "created_at",
  "nodes", "edges"];
const RUNTIME_DOCUMENT_KEYS = ["run_id", "graph_id", "nodes"];
//: `GraphNode.as_dict` and its two nested shapes, spelled out. A mapping that
//: READS named fields drops everything else, and dropping is repair: a key
//: this window has no mapping for would vanish silently and the drawing would
//: claim to be the whole plan. So each level is screened before it is read.
const PLAN_NODE_KEYS = ["node_id", "kind", "title", "stage", "instance_id",
  "capability", EXEMPT_FIELD, "resources", "gate_id", "loop"];
const PLAN_LOOP_KEYS = ["bound", "back_to"];
const PLAN_RESOURCE_KEYS = ["kind", "name"];
//: The projection's row for one node. `decision` belongs to a gate and
//: `pass`/`bound_reached` to a loop — each MUST be there for its own kind and
//: must not be there for any other. Trimming a word out of place would hide
//: a join that described the wrong node.
const POSITION_KEYS = ["node_id", "phase", "outcome", "attempt_ids",
  "observed_at", "evidence_refs"];

function planNodeIsWellFormed(node) {
  if (!keysWithin(PLAN_NODE_KEYS, node)) return false;
  if ("loop" in node && (!isObject(node.loop)
      || !keysWithin(PLAN_LOOP_KEYS, node.loop))) return false;
  if (!Array.isArray(node.resources)) return false;
  return node.resources.every(
    (row) => isObject(row) && keysWithin(PLAN_RESOURCE_KEYS, row));
}

function positionIsWellPlaced(row, kind) {
  const allowed = [...POSITION_KEYS];
  if (kind === "gate") allowed.push("decision");
  if (kind === "loop") allowed.push("pass", "bound_reached");
  if (!keysWithin(allowed, row)) return false;
  if (("decision" in row) !== (kind === "gate")) return false;
  if (("pass" in row) !== (kind === "loop")) return false;
  return ("bound_reached" in row) === (kind === "loop");
}

function adaptNode(node, position) {
  const gate = node.kind === "gate"
    ? {gate_id: node.gate_id, state: null} : null;
  const loop = node.kind === "loop" && isObject(node.loop)
    ? {bound: node.loop.bound, pass: null, back_to: node.loop.back_to} : null;
  const bound = "instance_id" in node;
  return {
    node_id: node.node_id,
    kind: node.kind,
    title: node.title,
    // The plan names an INSTANCE, never a product: which adapter serves that
    // instance is the run's frozen configuration's fact and appears in no
    // graph document. The badge therefore draws the instance the plan named,
    // and a registry row — if one exists for that id — supplies the vendor
    // colours as data. No branch here reads a provider.
    harness: bound ? node.instance_id : null,
    // Health and phase are the run's words, and this node's run words are in
    // `runtime` below. Left null so the store's one-source rule holds.
    health: null,
    phase: null,
    // What a harness CAN do is a registry fact; what this step WILL ask for
    // is the plan's `capability`, and it travels in `binding` where it can
    // never be read as the former.
    capabilities: [],
    // Runtime evidence is identifiers alone — no kind, no verification — so
    // no evidence ROW is built here. Inventing one would be a verification
    // claim no record makes.
    evidence: [],
    gate,
    loop,
    resources: node.resources,
    stage: "stage" in node ? node.stage : null,
    binding: bound ? {instance_id: node.instance_id,
      capability: node.capability, arguments: node[EXEMPT_FIELD]} : null,
    runtime: position,
  };
}

function adaptRuntimeNode(row, kind) {
  const out = {
    phase: row.phase,
    outcome: row.outcome,
    attempt_ids: row.attempt_ids,
    observed_at: row.observed_at,
    evidence_refs: row.evidence_refs,
  };
  if (kind === "gate") {
    out.decision = row.decision === GATE_IDLE ? "pending" : row.decision;
  }
  if (kind === "loop") {
    out.pass = row.pass;
    out.bound_reached = row.bound_reached;
  }
  return out;
}

//: The three answers a run read can give about a graph, and no fourth. They
//: are separate words because they mean different things to a reader: a run
//: that follows no plan yet is not a run whose plan could not be read, and
//: showing one as the other is how an empty screen comes to look like a
//: healthy one.
export const GRAPH_ABSENT = "absent";
export const GRAPH_REFUSED = "refused";
export const GRAPH_LOADED = "loaded";

function refused() {
  return Object.freeze({state: GRAPH_REFUSED, payload: null});
}

//: Whether the read carries a PAIR this window can read at all: three keys
//: present or three absent, the announced version, and both documents
//: agreeing about which run and which graph they describe. If they disagree,
//: they are not a pair and no join between them means anything.
function pairState(read, graph) {
  const parts = [graph.definition, graph.definition_digest, graph.runtime];
  const missing = (part) => part === null || part === undefined;
  // All three or none: the read answers `null` for every key when a run
  // follows no graph, so a mixed answer is a document this window cannot
  // read rather than a run in some third condition.
  if (parts.every(missing)) return GRAPH_ABSENT;
  if (parts.some(missing)) return GRAPH_REFUSED;
  const definition = graph.definition, runtime = graph.runtime;
  if (!isObject(definition) || !isObject(runtime)
      || !keysWithin(DEFINITION_KEYS, definition)
      || !keysWithin(RUNTIME_DOCUMENT_KEYS, runtime)) return GRAPH_REFUSED;
  if (definition.schema_version !== WIRE_SCHEMA) return GRAPH_REFUSED;
  if (typeof graph.definition_digest !== "string") return GRAPH_REFUSED;
  if (definition.run_id !== read.run.run_id
      || runtime.run_id !== read.run.run_id
      || definition.graph_id !== runtime.graph_id) return GRAPH_REFUSED;
  if (!Array.isArray(definition.nodes) || !Array.isArray(definition.edges)
      || !Array.isArray(runtime.nodes)) return GRAPH_REFUSED;
  return GRAPH_LOADED;
}

export function adaptRunGraph(read, registry) {
  if (!isObject(read) || !isObject(read.run)) return refused();
  const graph = read.graph;
  if (!isObject(graph) || !keysWithin(
    ["definition", "definition_digest", "runtime"], graph)) return refused();
  const pair = pairState(read, graph);
  if (pair === GRAPH_ABSENT) {
    return Object.freeze({state: GRAPH_ABSENT, payload: null});
  }
  if (pair === GRAPH_REFUSED) return refused();
  const definition = graph.definition, runtime = graph.runtime;
  const positions = new Map();
  for (const row of runtime.nodes) {
    if (!isObject(row) || positions.has(row.node_id)) return refused();
    positions.set(row.node_id, row);
  }
  const nodes = [];
  for (const node of definition.nodes) {
    if (!isObject(node) || !planNodeIsWellFormed(node)) return refused();
    const position = positions.get(node.node_id);
    // The projection describes exactly the plan's nodes. A step with no
    // position, or a position for a step no plan declares, means the join
    // was partial — and a partial join renders some steps at the plan's
    // word while their neighbours show the run's.
    if (position === undefined) return refused();
    if (!positionIsWellPlaced(position, node.kind)) return refused();
    positions.delete(node.node_id);
    nodes.push(adaptNode(node, adaptRuntimeNode(position, node.kind)));
  }
  if (positions.size) return refused();
  return Object.freeze({state: GRAPH_LOADED, payload: {
    run: {run_id: read.run.run_id, mode: read.run.mode},
    registry: Array.isArray(registry) ? registry : [],
    nodes,
    edges: definition.edges.map((edge) => isObject(edge)
      ? {from: edge.from_node, to: edge.to_node} : edge),
    // The runtime projection carries positions, not a history of instants:
    // it names no event and no time but the current action's. A timeline
    // assembled from it would be this window's invention.
    timeline: [],
    provenance: {source: "durable", graphId: definition.graph_id,
      digest: graph.definition_digest},
  }});
}

//: Every key a submitted plan may carry, at each level, spelled out. The body
//: is BUILT from these names rather than copied from a node, so a field this
//: window later grows cannot reach an immutable record by accident.
const REQUEST_NODE_KEYS = ["node_id", "kind", "title", "stage", "instance_id",
  "capability", EXEMPT_FIELD, "resources", "gate_id", "loop"];

function requestNode(node) {
  const out = {node_id: node.node_id, kind: node.kind, title: node.title,
    resources: node.resources.map((row) => ({kind: row.kind, name: row.name}))};
  if (node.stage !== null) out.stage = node.stage;
  if (node.binding !== null) {
    out.instance_id = node.binding.instanceId;
    out.capability = node.binding.capability;
    out[EXEMPT_FIELD] = node.binding.arguments;
  }
  if (node.gate !== null) out.gate_id = node.gate.gate_id;
  if (node.loop !== null) {
    out.loop = {bound: node.loop.bound, back_to: node.loop.backTo};
  }
  return out;
}

//: Walk one built body and answer whether a run's word reached it. The
//: capability payload is lifted out FIRST, by its field name, exactly as
//: `GraphNode.from_dict` does — so the walk has no exception to make and
//: none to be fooled by.
function carriesRuntimeWord(value) {
  if (Array.isArray(value)) return value.some(carriesRuntimeWord);
  if (!isObject(value)) return false;
  const {[EXEMPT_FIELD]: _payload, ...rest} = value;
  if (Object.keys(rest).some((key) => RUNTIME_ONLY_FIELDS.includes(key))) {
    return true;
  }
  return Object.values(rest).some(carriesRuntimeWord);
}

//: The plan a Human asks a run to follow, built from the definition side of
//: the drawing alone. Nothing observed reaches it: not a phase, not an
//: outcome, not a pass, not a gate's answer. The last act before returning is
//: to READ the body back and refuse it if a run's word is in it — the record
//: this body becomes can never be edited, so the screen belongs before the
//: door and not in a test that describes it.
export function graphRequestBody(graphId, state) {
  if (!isObject(state) || !Array.isArray(state.nodes) || !state.nodes.length) {
    return null;
  }
  const body = {
    graph_id: graphId,
    nodes: state.nodes.map(requestNode),
    edges: state.edges.map((edge) => ({from_node: edge.from, to_node: edge.to})),
  };
  if (body.nodes.some((node) => !keysWithin(REQUEST_NODE_KEYS, node))) {
    return null;
  }
  return carriesRuntimeWord(body) ? null : body;
}
