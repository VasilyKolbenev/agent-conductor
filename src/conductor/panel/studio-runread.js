//: What ONE run read says about its gates and its participants.
//:
//: Moved out of `studio-store.js` when that module reached the project's
//: 800-line cap. The seam is real rather than convenient: nothing here moves
//: state. Every function below is a PROJECTION over a single run read --
//: given the payload it computes the same answer forever, with no previous
//: state, no event and no arm. The reducer next door answers a different
//: question, "what does this event do to what is on screen", and it calls
//: these the way it calls any other pure helper.
//:
//: They read the plan and the projection the run read already carries, and
//: they invent nothing: a gate this graph does not name is not a row here, and
//: a run that froze no participants states none rather than defaulting to an
//: empty capability list, which would read as "this instance may do nothing".
//:
//: The two predicates below are this module's own, as `studio-runs.js` keeps
//: its own. They are shape tests and not a vocabulary: a second copy of a
//: closed word list would drift, and a second copy of `Array.isArray` cannot.

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }

function receiptsOf(detail) {
  const found = new Map();
  for (const wrapper of rows(detail.records)) {
    if (wrapper.record_type === "decision" && isObject(wrapper.record)) {
      found.set(wrapper.record.gate_id, wrapper.record);
    }
  }
  return found;
}

//: Every gate this run's plan names, and where it stands. Read off the plan and
//: the projection the run read already carries; nothing here is stored twice
//: and no step is invented that the plan does not hold.
export function decisionRows(detail) {
  const graph = isObject(detail) ? detail.graph : null;
  const definition = isObject(graph) ? graph.definition : null;
  const runtime = isObject(graph) ? graph.runtime : null;
  if (!isObject(definition) || !isObject(runtime)) return Object.freeze([]);
  const run = isObject(detail.run) ? detail.run : {};
  const position = new Map(rows(runtime.nodes).filter(isObject)
    .map((row) => [row.node_id, row]));
  const titles = new Map(rows(definition.nodes).filter(isObject)
    .map((node) => [node.node_id, node.title]));
  const receipts = receiptsOf(detail);
  const found = [];
  for (const node of rows(definition.nodes).filter(isObject)) {
    if (typeof node.gate_id !== "string") continue;
    const standing = position.get(node.node_id);
    found.push(Object.freeze({
      run_id: run.run_id, gate_id: node.gate_id, node_id: node.node_id,
      title: node.title, mode: run.mode,
      decision: standing && typeof standing.decision === "string"
        ? standing.decision : "unknown",
      unblocks: Object.freeze(rows(definition.edges).filter(isObject)
        .filter((edge) => edge.from_node === node.node_id)
        .map((edge) => Object.freeze({node_id: edge.to_node,
          title: titles.has(edge.to_node) ? titles.get(edge.to_node) : null}))),
      receipt: receipts.has(node.gate_id) ? receipts.get(node.gate_id) : null,
    }));
  }
  return Object.freeze(found);
}

//: Who this run froze, joined to what this build says those bindings may be
//: asked for. The controls read is the source; a run with none states nothing
//: rather than defaulting a capability list to empty.
export function participantsOf(detail) {
  const controls = isObject(detail) ? detail.controls : null;
  if (!isObject(controls)) return Object.freeze([]);
  const runId = isObject(detail.run) ? detail.run.run_id : undefined;
  return Object.freeze(rows(controls.instances).map((row) => Object.freeze(
    runId === undefined ? row : {...row, run_id: runId})));
}
