"use strict";
// The Studio's reducer: one frozen state value, moved only by `reduce`.
//
// It touches no DOM and opens no socket, and it holds the boundary call: the
// module table gives it `studio-model.js` and gives transport no reason to know
// what a payload means.
//
// TWO SPELLINGS, ONE VALUE. `studio-model.js` answers in camelCase and the five
// mounting modules read the wire's own snake_case. The boundary JUDGES here and
// what is stored is the WIRE value it admitted -- rebuilt from the settled
// projection where the boundary DROPS rows (roster, starters, controls), and
// carried verbatim where it refuses the whole payload instead (workflows, runs,
// one run read). Nothing reaches the state the boundary did not admit.
//
// The draft rules below are this product's most expensive invariants, measured
// on `graph-store.js:186-267` and carried here unchanged.
import {projectControls, projectProviders, projectRunRead, projectRuns,
  projectStarters, projectWorkflow, projectWorkflows} from "./studio-model.js";

//: The seven words a screen container may stand in; the plain sentence beside
//: each is the view's.
export const PHASES = Object.freeze(["empty", "loading", "ready", "stale",
  "refused", "failed", "disconnected"]);
//: The five screens, in the product's own order.
export const SCREENS = Object.freeze(
  ["overview", "workflow", "runs", "decisions", "agents"]);
//: The closed edit vocabulary, spelled the same in `studio-canvas.js` and
//: `studio-inspector.js`. The module table forbids importing either, so
//: tests/test_studio_wiring.py holds the three copies equal. `EDIT_FIELDS` is
//: every field name a `set-field` edit may carry, held the same way.
export const EDIT_TYPES = Object.freeze(["add", "connect", "delete-edge",
  "delete-node", "duplicate", "reorder", "set-field"]);
export const EDIT_FIELDS = Object.freeze(["capability", "gate_id", "kind",
  "loop_back_to", "loop_bound", "resources", "role_id", "stage", "title"]);
//: `graph_definition.NODE_KINDS`, its loop and resource bounds, and
//: `workflow_draft.MAX_DRAFT_NODES` / `MAX_DRAFT_EDGES`.
export const NODE_KINDS = Object.freeze(["task", "gate", "loop"]);
export const LOOP_BOUND = Object.freeze({min: 1, max: 99});
export const MAX_RESOURCES = 16;
export const MAX_NODES = 256;
export const MAX_EDGES = 1024;
//: `graph_template.SCHEMA_VERSION`, the one a draft document must claim.
export const WORKFLOW_SCHEMA = 1;
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ZOOM = Object.freeze({min: 0.4, max: 2});

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }
function text(value) { return typeof value === "string" ? value : ""; }

// A frozen copy built key by key -- the transport module still holds the
// parsed payload. Every key is DEFINED rather than assigned, so a document
// carrying `__proto__` gets an own property, never the prototype setter.
function frozenCopy(value) {
  if (Array.isArray(value)) return Object.freeze(value.map(frozenCopy));
  if (!isObject(value)) return value;
  const out = {};
  for (const key of Object.keys(value)) {
    Object.defineProperty(out, key, {configurable: false, enumerable: true,
      value: frozenCopy(value[key]), writable: false});
  }
  return Object.freeze(out);
}
const NO_DRAFT = Object.freeze({key: null, action: "approve", actor: "",
  reason: ""});
const WORKFLOWS = Object.freeze({
  phase: "empty",
  list: Object.freeze([]),
  starters: Object.freeze([]),
  selectedId: null,
  //: The last landed read of the chosen workflow, verbatim; and the DRAWING,
  //: which is the document this window is editing, saved or not.
  detail: null,
  draft: null,
  //: The one mark that tells a composed step from a durable one. It lives
  //: BESIDE the document because a draft document is a closed key set: a mark
  //: written into a node would make the drawing FOREIGN, and an unsavable
  //: drawing is not a drawing.
  localIds: Object.freeze([]),
  //: `durable` is a stored draft adopted unchanged; `local` is anything this
  //: window composed or edited on top of it.
  provenance: "none",
  //: The server's answer about the SAVED draft, and what this window already
  //: sees would be refused about the UNSAVED one. Two documents, two lists.
  diagnostics: Object.freeze([]),
  problems: Object.freeze([]),
  publishable: false,
  nextRevision: null,
  savedAt: null,
  //: Whether this window may WRITE. Not "is the socket up": between choosing a
  //: workflow and its read landing the drawing is still the previous
  //: workflow's, and a save taken from it would write one workflow's document
  //: to another's draft. Readiness names one answer about one workflow, is
  //: taken away the moment another is chosen, and is given back only by a
  //: landed read of the chosen one. A refused or failed read grants nothing.
  writeReady: false,
  savePhase: "idle",   // idle | submitting | refused | outcome-unknown | saved
  saveNotice: "",
});

export const EMPTY = Object.freeze({
  screen: "overview",
  connection: "connecting",   // connecting | open | closed
  notice: "Nothing has been read yet.",
  //: `project.name` is null and stays null: no durable record carries one.
  project: Object.freeze({name: null, warnings: Object.freeze([])}),
  providers: Object.freeze([]),
  workflows: WORKFLOWS,
  canvas: Object.freeze({pan: Object.freeze({x: 0, y: 0}), zoom: 1,
    selection: Object.freeze({kind: null, id: null})}),
  runs: Object.freeze({phase: "empty", list: Object.freeze([]),
    selectedId: null, detail: null}),
  decisions: Object.freeze({phase: "empty", list: Object.freeze([]),
    draft: NO_DRAFT}),
  agents: Object.freeze({phase: "empty", participants: Object.freeze([])}),
});

// -- what the boundary admitted, in the wire's own words ------------------
function wireProviders(value) {
  return Object.freeze(projectProviders(value).map((row) => Object.freeze({
    provider_id: row.providerId, display_name: row.displayName,
    availability: row.availability, implementation: row.implementation,
    controls: row.controls,
  })));
}

function wireStarters(value) {
  return Object.freeze(projectStarters(value).map((row) => Object.freeze({
    starter_id: row.starterId, title: row.title, document: row.document,
  })));
}

function wireInstances(settled) {
  return Object.freeze(settled.instances.map((row) => Object.freeze({
    instance_id: row.instanceId, adapter_id: row.adapterId,
    model: row.model, controls: row.controls,
  })));
}

// -- the drawing ----------------------------------------------------------
//: A draft document is exactly `{schema_version, title, nodes, edges}`, and
//: the two `workflow_draft.NOT_YET_FIELDS` names -- `template_id`, `revision`
//: -- are carried by every starter and every published revision. So it is
//: REBUILT from a draft's four keys rather than copied and pruned: neither word
//: can ride in and make the drawing something the save route refuses.
export function draftFrom(value) {
  if (!isObject(value)) return null;
  return frozenCopy({schema_version: WORKFLOW_SCHEMA,
    title: text(value.title) || "Untitled workflow",
    nodes: rows(value.nodes).filter(isObject),
    edges: rows(value.edges).filter(isObject)});
}

function nodeIds(held) {
  return rows(held && held.nodes).filter(isObject).map((node) => node.node_id);
}

// What an authoritative read REPLACES, and what it may not. The DURABLE arm
// and only that: the read really does bring a stored draft, so that document
// wins and exactly the COMPOSED steps ride on top of it, told apart by
// `localIds`. Three things it will not do: cross a workflow change, because
// one workflow's unsaved step offered on another's screen is that workflow's;
// keep an id the stored draft now carries, because the server is then the
// authority on that step; or draw an edge with an end the merged drawing does
// not hold, which is a line from nothing.
function heldDraft(state, durable, workflowId) {
  const held = state.workflows;
  const local = new Set(held.localIds);
  const adopted = {draft: durable, localIds: Object.freeze([]),
    provenance: "durable"};
  if (!local.size || held.selectedId !== workflowId || held.draft === null) {
    return adopted;
  }
  const arrived = new Set(nodeIds(durable));
  const kept = rows(held.draft.nodes).filter(
    (node) => local.has(node.node_id) && !arrived.has(node.node_id));
  if (!kept.length) return adopted;
  const keptIds = new Set(kept.map((node) => node.node_id));
  const nodes = [...rows(durable.nodes), ...kept];
  const known = new Set(nodes.map((node) => node.node_id));
  const carried = rows(held.draft.edges).filter((edge) =>
    (keptIds.has(edge.from_node) || keptIds.has(edge.to_node))
    && known.has(edge.from_node) && known.has(edge.to_node));
  return {
    draft: frozenCopy({...durable, nodes, edges: [...rows(durable.edges), ...carried]}),
    localIds: Object.freeze([...keptIds]),
    provenance: "local",
  };
}

// A read that brings NOTHING keeps the WHOLE drawing, not just the composed
// part. Measured on the Graph window before that fix: nine steps on screen,
// zero after the socket came back, because a reconnect always ends in a re-read
// and the empty arm reset to EMPTY. A plan missing eight of its nine steps is
// not a plan.
//
// A DURABLE drawing is never held across an answer: it belongs to the workflow
// that answered with it, and carrying it into another's "has no draft" would
// show one workflow's stored document as another's unsaved one -- the mixing
// this seam refuses, in its worst direction. Crossing a workflow change is
// refused at the door the Human's own action opens, not here.
function localPlan(state) {
  const held = state.workflows;
  if (held.draft === null || held.provenance === "durable") return null;
  return {draft: held.draft, localIds: held.localIds, provenance: "local"};
}

// -- what this window can already see would be refused --------------------
//: The rules the DRAFT route refuses outright -- a document that is FOREIGN
//: rather than merely incomplete -- asked here so a save refuses beside the
//: control that asked for it instead of posting a body the server rejects with
//: no diagnostics. What a draft is ALLOWED to be missing is absent from this
//: list on purpose: that is what `diagnostics` reports.
function nodeProblems(node, found) {
  const named = ID_RE.test(text(node.node_id)) ? node.node_id : "a step";
  if (!ID_RE.test(text(node.node_id))) {
    found.push("A step id must be letters, digits, dot, underscore or hyphen, "
      + "up to 128 characters.");
  }
  if (!text(node.title).trim()) found.push(`Step ${named} needs a display name.`);
  if (!NODE_KINDS.includes(node.kind)) {
    found.push(`Step ${named} names a step type this build cannot store.`);
  }
  if (Object.hasOwn(node, "role_id") !== Object.hasOwn(node, "capability")) {
    found.push(`Step ${named} names half a binding. A role and a capability are `
      + "stored together or neither, so this draft cannot be saved until the "
      + "other half is chosen.");
  }
  if (rows(node.resources).length > MAX_RESOURCES) {
    found.push(`Step ${named} attaches more than ${MAX_RESOURCES} resources.`);
  }
}

export function saveProblems(draft) {
  if (!isObject(draft)) return Object.freeze([]);
  const found = [];
  if (!text(draft.title).trim()) found.push("This workflow needs a name.");
  if (rows(draft.nodes).length > MAX_NODES) {
    found.push(`A workflow draft carries at most ${MAX_NODES} steps.`);
  }
  if (rows(draft.edges).length > MAX_EDGES) {
    found.push(`A workflow draft carries at most ${MAX_EDGES} connections.`);
  }
  for (const node of rows(draft.nodes)) nodeProblems(node, found);
  return Object.freeze(found);
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
  reorder,
  "set-field": (draft, edit) => EDIT_FIELDS.includes(edit.field)
    ? replaceNode(draft, edit.nodeId,
      (node) => withField(node, edit.field, edit.value))
    : {draft: null, notice: "That field is not one this build stores."},
});

function edited(state, edit) {
  const held = state.workflows;
  if (!EDIT_TYPES.includes(edit && edit.type)
      || !Object.hasOwn(EDITS, edit.type)) return state;
  if (held.draft === null) {
    return spoken(state, "There is no editable draft on screen. A published "
      + "revision is immutable; start a draft to change this workflow.");
  }
  const answer = EDITS[edit.type](held.draft, edit);
  if (answer.draft === null) {
    return answer.notice ? spoken(state, answer.notice) : state;
  }
  const draft = frozenCopy(answer.draft);
  const localIds = answer.added
    ? Object.freeze([...held.localIds, answer.added]) : held.localIds;
  return Object.freeze({...state,
    notice: answer.notice || state.notice,
    workflows: Object.freeze({...held, draft, localIds, provenance: "local",
      problems: saveProblems(draft), savePhase: "idle", saveNotice: ""}),
  });
}

// -- derivations off one run read -----------------------------------------
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
function participantsOf(detail) {
  const controls = isObject(detail) ? detail.controls : null;
  if (!isObject(controls)) return Object.freeze([]);
  const runId = isObject(detail.run) ? detail.run.run_id : undefined;
  return Object.freeze(rows(controls.instances).map((row) => Object.freeze(
    runId === undefined ? row : {...row, run_id: runId})));
}

// -- the arms -------------------------------------------------------------
function spoken(state, notice) {
  return Object.freeze({...state, notice});
}

// A save outcome is carried THROUGH the authoritative answer that follows it;
// an answer carrying none leaves the one on screen alone. It is cleared where
// it becomes wrong: when the chosen workflow changes.
function carried(held, event) {
  return Object.hasOwn(event, "savePhase")
    ? {savePhase: event.savePhase, saveNotice: event.saveNotice}
    : {savePhase: held.savePhase, saveNotice: held.saveNotice};
}

function workflowsLoaded(state, event) {
  const settled = projectWorkflows(event.payload);
  if (settled === null) {
    return Object.freeze({...state,
      workflows: Object.freeze({...state.workflows, phase: "failed"}),
      notice: "The workflow list could not be read as this build speaks it. "
        + "Nothing on screen was replaced by a payload nobody can read."});
  }
  return Object.freeze({...state,
    providers: wireProviders(event.payload.providers),
    workflows: Object.freeze({...state.workflows, phase: "ready",
      list: frozenCopy(event.payload.workflows),
      starters: wireStarters(event.payload.starters)}),
    agents: Object.freeze({...state.agents, phase: "ready"}),
    notice: "",
  });
}

function workflowLoaded(state, event) {
  const settled = projectWorkflow(event.payload);
  if (settled === null) return workflowUnread(state, event, "failed",
    "This workflow answered with a payload this build cannot read. Nothing "
    + "about it is inferred from a document nobody can read.");
  const payload = frozenCopy(event.payload);
  const stored = payload.draft === null ? null : payload.draft.document;
  const brought = stored === null ? null : draftFrom(stored);
  const merged = brought === null
    ? localPlan(state)
    : heldDraft(state, brought, payload.workflow_id);
  const draft = merged === null ? null : merged.draft;
  return Object.freeze({...state,
    workflows: Object.freeze({...state.workflows, phase: "ready",
      selectedId: payload.workflow_id, detail: payload,
      draft, localIds: merged === null ? Object.freeze([]) : merged.localIds,
      provenance: merged === null ? "none" : merged.provenance,
      diagnostics: payload.diagnostics, problems: saveProblems(draft),
      publishable: payload.publishable, nextRevision: payload.next_revision,
      savedAt: payload.draft === null ? null : payload.draft.saved_at,
      writeReady: event.ready === true, ...carried(state.workflows, event)}),
    notice: "",
  });
}

// A refused or failed READ brings no durable fact and is not the Human doing
// anything, so it may not destroy the drawing this window holds. The state word
// carries the refusal, the write door stays shut, and the notice says who holds
// what is on screen.
function workflowUnread(state, event, phase, notice) {
  const kept = localPlan(state);
  const held = state.workflows;
  return Object.freeze({...state,
    workflows: Object.freeze({...held, phase,
      draft: kept === null ? held.draft : kept.draft,
      localIds: kept === null ? held.localIds : kept.localIds,
      provenance: kept === null ? held.provenance : kept.provenance,
      writeReady: false, ...carried(held, event)}),
    notice: kept === null ? notice : notice + " The drawing on screen is still "
      + "held in this window and has not been saved; nothing may be written "
      + "until this workflow has been read again.",
  });
}

// The one door a held drawing is let go through, and it is the Human's own
// action rather than a transport event: choosing another workflow. A drawing
// made against one workflow is not a draft of another's, and the save door
// beside it writes to whichever is chosen -- so it goes HERE, before the new
// read goes out.
function workflowChosen(state, workflowId) {
  if (state.workflows.selectedId === workflowId) return state;
  return Object.freeze({...state,
    workflows: Object.freeze({...WORKFLOWS, phase: "loading",
      list: state.workflows.list, starters: state.workflows.starters,
      selectedId: workflowId}),
    canvas: Object.freeze({...state.canvas,
      selection: Object.freeze({kind: null, id: null})}),
    notice: "",
  });
}

function runsLoaded(state, event) {
  const settled = projectRuns(event.payload);
  if (settled === null) {
    return Object.freeze({...state,
      runs: Object.freeze({...state.runs, phase: "failed"}),
      notice: "The run list could not be read as this build speaks it, so it "
        + "is not shown at all: a run you cannot see is worse than one you "
        + "cannot read."});
  }
  return Object.freeze({...state,
    providers: wireProviders(event.payload.providers),
    runs: Object.freeze({...state.runs, phase: "ready",
      list: frozenCopy(event.payload.runs)}),
    notice: "",
  });
}

//: The run read, the decisions waiting in it and the participants it froze
//: move together: all three come out of the SAME answer, and leaving one
//: standing while the others move would put two runs on one screen.
function runMoved(state, phase, detail, notice) {
  return Object.freeze({...state,
    project: Object.freeze({name: null,
      warnings: detail === null ? Object.freeze([]) : detail.warnings}),
    runs: Object.freeze({...state.runs, phase, detail,
      selectedId: detail === null ? state.runs.selectedId : detail.run.run_id}),
    decisions: Object.freeze({...state.decisions, phase, draft: NO_DRAFT,
      list: detail === null ? Object.freeze([]) : decisionRows(detail)}),
    agents: Object.freeze({...state.agents, phase,
      participants: detail === null
        ? Object.freeze([]) : participantsOf(detail)}),
    notice,
  });
}

function runLoaded(state, event) {
  if (projectRunRead(event.read) === null) {
    return runMoved(state, "failed", null,
      "This run answered with a payload this build cannot read. Nothing about "
      + "it is inferred from a document nobody can read.");
  }
  const controls = isObject(event.controls)
    ? projectControls(event.controls) : null;
  const detail = frozenCopy({...event.read,
    controls: controls === null ? null : {instances: wireInstances(controls)}});
  const moved = runMoved(state, "ready", detail, "");
  return controls === null ? moved : Object.freeze({...moved,
    providers: wireProviders(event.controls.providers)});
}

function runChosen(state, runId) {
  if (state.runs.selectedId === runId) return state;
  return Object.freeze({...runMoved(state, "loading", null, state.notice),
    runs: Object.freeze({...state.runs, phase: "loading", selectedId: runId,
      detail: null})});
}

function seeded(state, event) {
  const draft = draftFrom(event.document);
  if (draft === null) {
    return spoken(state, "That starting document is not one this build can "
      + "read as a workflow.");
  }
  return Object.freeze({...state,
    // Every step of a seeded drawing is this window's until it is saved, so
    // every id is a local one and a later read may take none of them.
    workflows: Object.freeze({...state.workflows, draft,
      localIds: Object.freeze(nodeIds(draft)), provenance: "local",
      problems: saveProblems(draft), savePhase: "idle", saveNotice: ""}),
    notice: "This drawing is held in this window and has been saved nowhere. "
      + "Save the draft to put it on the server.",
  });
}

function connectionMoved(state, value) {
  const open = value === "open";
  return Object.freeze({...state, connection: value,
    workflows: Object.freeze({...state.workflows,
      // A reconnect does not by itself make this window current again: what it
      // missed while it was down is unknown, so readiness is granted by the
      // READ that follows and by nothing else.
      writeReady: open ? state.workflows.writeReady : false}),
    notice: open ? state.notice
      : "Connection lost. The last read facts are still on screen, and nothing "
        + "may be written until the stream is back and this workflow has been "
        + "read again.",
  });
}

function canvasMoved(state, event) {
  const zoom = Number(event.zoom);
  const pan = isObject(event.pan) ? event.pan : {};
  return Object.freeze({...state, canvas: Object.freeze({...state.canvas,
    pan: Object.freeze({
      x: Number.isFinite(Number(pan.x)) ? Number(pan.x) : state.canvas.pan.x,
      y: Number.isFinite(Number(pan.y)) ? Number(pan.y) : state.canvas.pan.y}),
    zoom: Number.isFinite(zoom)
      ? Math.min(ZOOM.max, Math.max(ZOOM.min, zoom)) : state.canvas.zoom})});
}

function selected(state, selection) {
  const kind = isObject(selection)
    && (selection.kind === "node" || selection.kind === "edge")
    ? selection.kind : null;
  return Object.freeze({...state, canvas: Object.freeze({...state.canvas,
    selection: Object.freeze({kind,
      id: kind === null ? null : String(selection.id)})})});
}

function decisionDrafted(state, patch) {
  const draft = state.decisions.draft;
  const next = {...draft};
  for (const key of ["action", "actor", "reason"]) {
    if (isObject(patch) && Object.hasOwn(patch, key)) next[key] = patch[key];
  }
  return Object.freeze({...state, decisions: Object.freeze({...state.decisions,
    draft: Object.freeze(next)})});
}

function phaseMoved(state, screen, event) {
  if (!PHASES.includes(event.phase)) return state;
  return Object.freeze({...state, [screen]: Object.freeze({
    ...state[screen], phase: event.phase}),
  notice: typeof event.notice === "string" ? event.notice : state.notice});
}

// -- the one way to move --------------------------------------------------
function decisionChosen(state, event) {
  return Object.freeze({...state, decisions: Object.freeze({...state.decisions,
    draft: Object.freeze({...NO_DRAFT,
      key: typeof event.key === "string" ? event.key : null})})});
}

// The save door answers in every phase: a refusal that arrived after the
// drawing changed still has a Human waiting for it, and dropping it would leave
// a submitted document with no reported outcome at all.
function saveMoved(state, event) {
  return Object.freeze({...state, workflows: Object.freeze({...state.workflows,
    savePhase: ["idle", "submitting", "refused", "outcome-unknown", "saved"]
      .includes(event.phase) ? event.phase : "outcome-unknown",
    saveNotice: text(event.notice)})});
}

const ARMS = Object.freeze({
  "agents-phase": (state, event) => phaseMoved(state, "agents", event),
  "canvas-select": (state, event) => selected(state, event.selection),
  "canvas-view": canvasMoved,
  connection: (state, event) => ["connecting", "open", "closed"]
    .includes(event.state) ? connectionMoved(state, event.state) : state,
  "decision-chosen": decisionChosen,
  "decision-edit": (state, event) => decisionDrafted(state, event.patch),
  "decisions-phase": (state, event) => phaseMoved(state, "decisions", event),
  edit: (state, event) => edited(state, event.edit || {}),
  "run-chosen": (state, event) => runChosen(state, event.runId),
  "run-loaded": runLoaded,
  "runs-loaded": runsLoaded,
  "runs-phase": (state, event) => phaseMoved(state, "runs", event),
  save: saveMoved,
  screen: (state, event) => SCREENS.includes(event.screen)
    ? Object.freeze({...state, screen: event.screen}) : state,
  seed: seeded,
  status: (state, event) => spoken(state, text(event.notice)),
  "workflow-chosen": (state, event) => workflowChosen(state, event.workflowId),
  "workflow-loaded": workflowLoaded,
  "workflow-unread": (state, event) => workflowUnread(state, event,
    event.phase === "refused" ? "refused" : "failed", text(event.notice)),
  "workflows-loaded": workflowsLoaded,
  "workflows-phase": (state, event) => phaseMoved(state, "workflows", event),
});

// An own-key check, not a lookup: an event type is data and "constructor" is a
// spelling of it, so an inherited member is never reached as an arm.
export function reduce(state, event) {
  if (!event || typeof event.type !== "string") return state;
  return Object.hasOwn(ARMS, event.type)
    ? ARMS[event.type](state, event) : state;
}
