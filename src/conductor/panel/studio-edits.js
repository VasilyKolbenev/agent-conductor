//: What one EDIT does to a drawing, and nothing else.
//:
//: Split out of `studio-store.js` when that module reached the project's line
//: cap, along the seam the two halves already had. The reducer next door is a
//: STATE machine: it lands payloads, moves phases, remembers which workflow is
//: chosen and which run is open. Everything here is a pure document transform
//: -- a draft in, a draft out, no state, no payload, no phase and no notice
//: about anything but the edit itself.
//:
//: That seam is also where the work is. `withField` is the one dispatcher every
//: new editable step field passes through, and the vocabulary it dispatches on
//: is the list this module owns. Adding a field grows this file and touches the
//: reducer not at all, which is the property the split was drawn for.
//:
//: It imports the payload boundary for the two ceiling helpers and nothing
//: else, so the dependency runs one way: the reducer knows about the edits, the
//: edits know nothing about the reducer.
import {CEILINGS, withCeiling} from "./studio-model.js";

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function rows(value) { return Array.isArray(value) ? value : []; }
function text(value) { return typeof value === "string" ? value : ""; }

//: The closed edit vocabulary, spelled the same in `studio-canvas.js` and
//: `studio-inspector.js`. The module table forbids importing either, so
//: tests/test_studio_wiring.py holds the three copies equal. `EDIT_FIELDS` is
//: every field name a `set-field` edit may carry, held the same way.
export const EDIT_TYPES = Object.freeze(["add", "connect", "delete-edge",
  "delete-node", "duplicate", "move", "reorder", "set-edge-condition",
  "set-field"]);
export const EDIT_FIELDS = Object.freeze(["arguments", "attempt_bound",
  "capability", "failure_policy", "gate_id", "kind", "loop_back_to",
  "loop_bound", "purpose", "required_evidence", "resources", "role_id",
  "stage", "timeout_seconds", "title", "verifier_role_id"]);
//: `graph_definition.NODE_KINDS`, its loop and resource bounds, and
//: `workflow_draft.MAX_DRAFT_NODES` / `MAX_DRAFT_EDGES`.
export const NODE_KINDS = Object.freeze(["task", "gate", "loop"]);
export const LOOP_BOUND = Object.freeze({min: 1, max: 99});
export const MAX_RESOURCES = 16;
export const MAX_NODES = 256;
export const MAX_EDGES = 1024;
//: `graph_conditions.EDGE_CONDITIONS` -- the eight words a road may open
//: on, and `_CONDITIONS_BY_KIND` beside it, so a select offers exactly the
//: family the step behind the road can produce. Copies of the layer that
//: owns them, held equal by tests/test_studio_wiring.py rather than trusted.
export const EDGE_CONDITIONS = Object.freeze([
  "on_approved", "on_rejected", "on_changes_requested", "on_waived",
  "on_succeeded", "on_failed",
  "on_bound_reached", "on_bound_remaining"]);
export const CONDITIONS_BY_KIND = Object.freeze({
  gate: Object.freeze([
    "on_approved", "on_rejected", "on_changes_requested", "on_waived"]),
  task: Object.freeze(["on_succeeded", "on_failed"]),
  loop: Object.freeze(["on_bound_reached", "on_bound_remaining"]),
});

export function nodeIds(held) {
  return rows(held && held.nodes).filter(isObject).map((node) => node.node_id);
}

// -- edits ----------------------------------------------------------------
function freshId(nodes, stem) {
  const taken = new Set(nodes.map((node) => node.node_id));
  let serial = nodes.length + 1;
  while (taken.has(`${stem}-${serial}`)) serial += 1;
  return `${stem}-${serial}`;
}

function newNode(kind, nodes) {
  return {node_id: freshId(nodes, "step"), kind,
    title: `New ${kind === "gate" ? "human gate" : kind}`, resources: []};
}

function withBinding(node, name, value) {
  const next = {...node};
  delete next.arguments;
  if (value === null || value === "") {
    // Clearing one half clears the other with it: the contract holds the two
    // as ONE fact, and half of one names a step nobody can carry out.
    delete next.role_id;
    delete next.capability;
    // And the VERIFIER goes with them. `TemplateNode.__post_init__` refuses a
    // verifier role on a step that binds no role of its own -- a step that
    // carries nothing out has nothing to verify -- so leaving one behind here
    // would make a draft unsavable by clearing a field, and the person would
    // meet it as a refusal about a control they did not touch.
    delete next.verifier_role_id;
    // And the EVIDENCE REQUIREMENT with them, for the same reason one field
    // over: a step that carries nothing out is verified by nobody, so
    // `TemplateNode.__post_init__` refuses a demand made of a verification
    // that will never exist.
    delete next.required_evidence;
    // And the FAILURE POLICY, for the same reason again: a step that
    // carries nothing out cannot fail, so there is no failure for a
    // policy to answer and the contract refuses one.
    delete next.failure_policy;
    return next;
  }
  next[name] = value;
  if (next.role_id === undefined || next.capability === undefined) return next;
  next.arguments = isObject(node.arguments) ? node.arguments : {};
  return next;
}

//: A loop is stored as the PAIR `{bound, back_to}` -- `GraphLoop.from_dict`
//: takes both or refuses -- so half of one is never written. Choosing the step
//: a loop reopens completes the pair at the contract's own floor and says so;
//: a bound with no target is refused, because there is no honest value to
//: invent for the other half.
function withLoop(node, name, value) {
  const loop = isObject(node.loop) ? node.loop : {};
  const next = {...node};
  if (name === "loop_back_to") {
    if (value === null || value === "") {
      delete next.loop;
      return {node: next, notice: "This step no longer reopens anything."};
    }
    const bound = Number.isInteger(loop.bound) ? loop.bound : LOOP_BOUND.min;
    next.loop = {bound, back_to: value};
    return {node: next, notice: Number.isInteger(loop.bound) ? ""
      : `A loop is stored as a pair, so its greatest pass was set to `
        + `${LOOP_BOUND.min}. Change it beside this.`};
  }
  if (!Number.isInteger(value) || value < LOOP_BOUND.min
      || value > LOOP_BOUND.max) {
    return {node, notice: `A loop bound is a whole number from `
      + `${LOOP_BOUND.min} to ${LOOP_BOUND.max}.`};
  }
  if (typeof loop.back_to !== "string") {
    return {node, notice: "Choose the step this loop reopens first: a loop is "
      + "stored as the pair (bound, back_to) and half of one cannot be saved."};
  }
  next.loop = {bound: value, back_to: loop.back_to};
  return {node: next, notice: ""};
}

//: A type change takes with it the attachments the new type may not carry.
function withKind(node, value) {
  const next = {...node, kind: value};
  if (value !== "gate") delete next.gate_id;
  if (value !== "loop") delete next.loop;
  if (value !== "task") delete next.stage;
  return next;
}

//: Unset means ABSENT, never null: `TemplateNode._document` writes it so.
function optional(node, name, value) {
  const next = {...node};
  if (value === null || value === "") delete next[name];
  else next[name] = value;
  return next;
}

function withResources(node, value) {
  return {...node, resources: rows(value).filter(isObject)
    .slice(0, MAX_RESOURCES)
    .map((row) => ({kind: String(row.kind), name: String(row.name)}))};
}

function withField(node, name, value) {
  if (name === "role_id" || name === "capability") {
    return {node: withBinding(node, name, value), notice: ""};
  }
  if (name === "loop_bound" || name === "loop_back_to") {
    return withLoop(node, name, value);
  }
  if (Object.hasOwn(CEILINGS, name)) return withCeiling(node, name, value);
  if (name === "kind") {
    return NODE_KINDS.includes(value)
      ? {node: withKind(node, value), notice: ""}
      : {node, notice: "That step type is not one this build can store."};
  }
  if (name === "resources") {
    return {node: withResources(node, value), notice: ""};
  }
  if (name === "title") {
    return text(value).trim() ? {node: {...node, title: value}, notice: ""}
      : {node, notice: "A step needs a display name."};
  }
  return {node: optional(node, name, value), notice: ""};
}

//: The furthest from the origin a step may be put, and the grammar of a
//: coordinate. `graph_template.POSITION_LIMIT` and `NodePosition` own the same
//: two rules one layer down; refusing here as well is what stops a drag
//: writing a draft the save route would then reject, which the person would
//: meet as a save that failed for a reason nothing on screen explains.
const POSITION_LIMIT = 100000;

//: Unplacing is the same operation as placing -- it writes the same one field
//: -- so it is a flag on `move` rather than a seventh word in a closed
//: vocabulary that three modules hold equal. Without it a placement is a
//: ONE-WAY door: the first drag takes a step out of the automatic layout for
//: good, and `NodePosition | None` was built to allow exactly the way back.
function unplaceNode(draft, edit) {
  return replaceNode(draft, edit.nodeId, (node) => {
    if (!isObject(node.position)) return {node, notice: ""};
    const next = {...node};
    delete next.position;
    return {node: next, notice: ""};
  });
}

function moveNode(draft, edit) {
  if (edit.clear === true) return unplaceNode(draft, edit);
  const x = Math.round(Number(edit.x));
  const y = Math.round(Number(edit.y));
  if (!Number.isInteger(x) || !Number.isInteger(y)
      || Math.abs(x) > POSITION_LIMIT || Math.abs(y) > POSITION_LIMIT) {
    return {draft: null,
      notice: "A step stays within the canvas this build can store."};
  }
  return replaceNode(draft, edit.nodeId, (node) => {
    const at = node.position;
    // A move to where the step already is changes nothing, and saying it did
    // would call a saved draft unsaved for a gesture that did not land.
    if (isObject(at) && at.x === x && at.y === y) {
      return {node, notice: ""};
    }
    return {node: {...node, position: {x, y}}, notice: ""};
  });
}

function replaceNode(draft, nodeId, make) {
  const at = rows(draft.nodes).findIndex((node) => node.node_id === nodeId);
  if (at < 0) return {draft: null, notice: "That step is not in this drawing."};
  const answer = make(draft.nodes[at]);
  if (answer.node === draft.nodes[at]) return {draft: null, notice: answer.notice};
  const nodes = draft.nodes.slice();
  nodes[at] = answer.node;
  return {draft: {...draft, nodes}, notice: answer.notice};
}

function connect(draft, edit) {
  const known = new Set(nodeIds(draft));
  if (!known.has(edit.fromId) || !known.has(edit.toId)
      || edit.fromId === edit.toId) {
    return {draft: null, notice: "A connection joins two different steps that "
      + "are both in this drawing."};
  }
  if (rows(draft.edges).some((edge) =>
    edge.from_node === edit.fromId && edge.to_node === edit.toId)) {
    return {draft: null, notice: "Those steps are already connected."};
  }
  return {draft: {...draft, edges: [...draft.edges,
    {from_node: edit.fromId, to_node: edit.toId}]}, notice: ""};
}

// A gate id names ONE decision, so a duplicated gate may not carry the
// original's: two steps answering to one receipt is a plan that cannot say
// which of them a Human decided.
function duplicate(draft, edit) {
  const node = rows(draft.nodes).find((row) => row.node_id === edit.nodeId);
  if (!node) return {draft: null, notice: "That step is not in this drawing."};
  const copy = {...node, node_id: freshId(draft.nodes, "step"),
    title: `${node.title} (copy)`};
  delete copy.gate_id;
  return {draft: {...draft, nodes: [...draft.nodes, copy]}, added: copy.node_id,
    notice: `Added ${copy.node_id} as a copy. It is connected to nothing and, `
      + "if it was a human gate, names no gate id yet."};
}

function reorder(draft, edit) {
  const at = rows(draft.nodes).findIndex((node) => node.node_id === edit.nodeId);
  const to = Math.max(0, Math.min(draft.nodes.length - 1, Number(edit.index)));
  if (at < 0 || !Number.isInteger(to) || to === at) {
    return {draft: null, notice: ""};
  }
  const nodes = draft.nodes.slice();
  nodes.splice(to, 0, nodes.splice(at, 1)[0]);
  return {draft: {...draft, nodes}, notice: ""};
}

function dropNode(draft, edit) {
  if (!nodeIds(draft).includes(edit.nodeId)) {
    return {draft: null, notice: "That step is not in this drawing."};
  }
  return {draft: {...draft,
    nodes: draft.nodes.filter((node) => node.node_id !== edit.nodeId),
    edges: draft.edges.filter((edge) =>
      edge.from_node !== edit.nodeId && edge.to_node !== edit.nodeId)},
  notice: `Removed ${edit.nodeId} and every connection naming it. A loop still `
    + "reopening it will say so in the diagnostics."};
}

function addNode(draft, edit) {
  if (!NODE_KINDS.includes(edit.kind)) {
    return {draft: null, notice: "That step type is not one this build stores."};
  }
  const node = newNode(edit.kind, draft.nodes);
  const edges = typeof edit.afterId === "string"
    && nodeIds(draft).includes(edit.afterId)
    ? [...draft.edges, {from_node: edit.afterId, to_node: node.node_id}]
    : draft.edges.slice();
  return {draft: {...draft, nodes: [...draft.nodes, node], edges},
    added: node.node_id, notice: `Added ${node.node_id}. It names no role yet, `
      + "so nothing would carry it out."};
}

//: One arm per edit word: a type not named here reaches no drawing at all. An
//: arm that removed nothing answers `null`, or it would call the draft unsaved.
const EDITS = Object.freeze({
  add: addNode,
  connect,
  "delete-edge": (draft, edit) => {
    const kept = draft.edges.filter((edge) =>
      !(edge.from_node === edit.fromId && edge.to_node === edit.toId));
    return kept.length === draft.edges.length
      ? {draft: null, notice: "That connection is not in this drawing."}
      : {draft: {...draft, edges: kept}, notice: ""};
  },
  "delete-node": dropNode,
  duplicate,
  move: moveNode,
  reorder,
  //: An empty value CLEARS, which is how a person says "unconditional"
  //: through a select. Absent and empty are one answer here, exactly as
  //: `settled_edge_condition` reads them, so the window cannot compose a
  //: document the contract would rewrite under it.
  "set-edge-condition": (draft, edit) => {
    if (edit.value !== "" && !EDGE_CONDITIONS.includes(edit.value)) {
      return {draft: null, notice: "That is not a word a connection can "
        + "open on."};
    }
    let moved = false;
    const edges = rows(draft.edges).map((edge) => {
      if (edge.from_node !== edit.fromId || edge.to_node !== edit.toId) {
        return edge;
      }
      const {condition, ...rest} = edge;
      const next = edit.value === "" ? rest : {...rest, condition: edit.value};
      moved = moved || (condition || "") !== edit.value;
      return next;
    });
    return moved
      ? {draft: {...draft, edges}, notice: ""}
      : {draft: null, notice: "That connection already opens on that."};
  },
  "set-field": (draft, edit) => EDIT_FIELDS.includes(edit.field)
    ? replaceNode(draft, edit.nodeId,
      (node) => withField(node, edit.field, edit.value))
    : {draft: null, notice: "That field is not one this build stores."},
});


//: The one door the reducer knocks on. It answers `{draft, notice, added?}`
//: with a NULL draft when nothing moved -- a word this build does not know, a
//: step that is not in the drawing, an edit that would change nothing -- so the
//: caller can tell "refused, and here is why" from "accepted" without knowing
//: what any arm does.
export function applyEdit(draft, edit) {
  if (!EDIT_TYPES.includes(edit && edit.type)
      || !Object.hasOwn(EDITS, edit.type)) {
    return {draft: null, notice: ""};
  }
  return EDITS[edit.type](draft, edit);
}
