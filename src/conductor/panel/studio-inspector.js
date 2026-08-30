"use strict";
// The node inspector's FRAME: which document is open, which node is selected,
// what a run bound to it, and where the six sections go. The sections
// themselves and the primitives they are built from live in
// `studio-sections.js`, which this module reached the line cap without.
//
// Every string enters as a text node; this module reaches no network and no
// clock, and it writes nothing but DOM.
//
// The separation this file exists to hold: a WORKFLOW document names roles and
// never a provider, a model, an adapter or a run -- the partition
// `graph_template` and `graph_definition.RUNTIME_ONLY_FIELDS` already enforce.
// So Assignment EDITS the role and the capability, and SHOWS the participant,
// the harness and the model a run bound to that role as read-only context with
// the run named beside it. There is no control here that could put a provider
// or a model into a workflow document.
//
// The second rule is the completeness rule. A field is finished when it is
// validated here, written through `handlers.onEdit`, stored by the draft route
// and read back by the real product -- or it says, in place, that this harness
// does not support it. Nothing on this screen writes inert data, and nothing
// silently disappears. Every unsupported line carries `data-unsupported`.
import {element} from "./command-view.js";
//: The fourth section is a module of its own -- what a step consumes and what
//: it produces is the one of the six that grows, so it left `studio-sections`
//: before that file reached the cap. It is appended in the same place it always
//: was; only the file it is read from changed.
import {artifactSection} from "./studio-artifacts.js";
//: The primitives come from the toolkit and the sections from the sections:
//: this frame reaches past `studio-sections.js` for `note` and `panelOf` the
//: way that module does, because both build controls out of one toolkit and a
//: re-export would be a second name for one thing.
import {
  call,
  context,
  editable,
  note,
  panelOf,
  unsupported,
} from "./studio-fields.js";
import {
  assignmentSection,
  executionSection,
  generalSection,
  stepActions,
  transitionSection,
  verificationSection,
} from "./studio-sections.js";

//: The two shapes this frame asks of a payload before handing it to a control.
//: Kept here rather than imported: they are three lines each, and a boundary
//: module that reached for them would be importing a neighbour to answer a
//: question about its own argument.
function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function rows(value) { return Array.isArray(value) ? value : []; }

// -- what is on screen -----------------------------------------------------

//: The same reading `studio-canvas.canvasDocument` makes, and it must stay the
//: same reading: two surfaces showing two different documents at once is the
//: confusion this whole screen is built to refuse. The module table forbids
//: importing it, so the test holds the two functions to one another instead.
export function inspectedDocument(state) {
  const workflows = isObject(state) && isObject(state.workflows)
    ? state.workflows : {};
  const draft = workflows.draft;
  const held = isObject(draft) && !Array.isArray(draft.nodes)
    && isObject(draft.document) ? draft.document : draft;
  if (isObject(held) && Array.isArray(held.nodes)) {
    return {kind: "draft", document: held, revision: null};
  }
  const detail = isObject(workflows.detail) ? workflows.detail : {};
  const published = detail.published;
  if (isObject(published) && Array.isArray(published.nodes)) {
    return {kind: "published", document: published,
      revision: published.revision === undefined ? null : published.revision};
  }
  return {kind: "none", document: null, revision: null};
}

function selectionOf(state) {
  const canvas = isObject(state) && isObject(state.canvas) ? state.canvas : {};
  const selection = isObject(canvas.selection) ? canvas.selection : {};
  const kind = selection.kind === "node" || selection.kind === "edge"
    ? selection.kind : null;
  return {kind, id: kind === null ? null : String(selection.id)};
}

//: Every durable artifact THIS step's actions published in the open run.
//:
//: A two-hop join, and both hops are the journal's own. An `ArtifactDocument`
//: names the action that produced it (`source_action_id`); an `ActionRequest`
//: names the step that action was bound to (`node_id`). Neither record carries
//: the other half, so no step's outputs can be read off one row -- and an
//: artifact whose source action this journal does not hold, or whose request
//: was bound to no step, is attributed to NOTHING rather than to the step
//: whoever is looking happens to have selected.
//:
//: Three facts are carried and the content is not one of them. An artifact is
//: durable material a run hands between roles; this window says which exist.
function producedBy(detail, nodeId) {
  const boundTo = new Map();
  for (const row of rows(detail.records)) {
    if (!isObject(row) || row.record_type !== "action_request") continue;
    const record = isObject(row.record) ? row.record : {};
    if (typeof record.action_id !== "string") continue;
    boundTo.set(record.action_id, record.node_id);
  }
  const found = [];
  for (const row of rows(detail.records)) {
    if (!isObject(row) || row.record_type !== "artifact") continue;
    const record = isObject(row.record) ? row.record : {};
    if (boundTo.get(record.source_action_id) !== nodeId) continue;
    found.push({
      artifactId: String(record.artifact_id),
      artifactRef: String(record.artifact_ref),
      mediaType: String(record.media_type),
    });
  }
  return found;
}

//: What a RUN says about this step, and the run it says it about. Every field
//: is optional and nothing is defaulted: a step no run named answers `null`,
//: which is a different thing from a step a run named with nothing to report.
export function runContext(state, nodeId) {
  const detail = isObject(state) && isObject(state.runs) ? state.runs.detail : null;
  if (!isObject(detail)) return null;
  const run = isObject(detail.run) ? detail.run : {};
  const graph = isObject(detail.graph) ? detail.graph : {};
  const definition = isObject(graph.definition) ? graph.definition : null;
  const runtime = isObject(graph.runtime) ? graph.runtime : null;
  const planned = definition
    ? rows(definition.nodes).find((row) => isObject(row) && row.node_id === nodeId)
    : null;
  const config = isObject(detail.config) ? detail.config : {};
  const instanceId = planned ? planned.instance_id : null;
  return {
    runId: run.run_id === undefined ? null : String(run.run_id),
    mode: run.mode === undefined ? null : String(run.mode),
    planned: planned || null,
    instance: rows(config.instances).find(
      (row) => isObject(row) && row.id === instanceId) || null,
    position: runtime
      ? rows(runtime.nodes).find((row) => isObject(row) && row.node_id === nodeId)
        || null
      : null,
    //: A PROJECTION of the journal rather than the journal itself: the
    //: sections are handed the three facts about this step's own artifacts and
    //: no road to the records the join was made from, so no control can grow a
    //: second reading of them -- or reach an artifact's content.
    products: producedBy(detail, nodeId),
  };
}

//: Which capabilities this BUILD can actually serve, and who serves them --
//: read off the provider roster's PROVEN controls and off nothing else. There
//: is no hardcoded list here and no branch on a provider id: a provider that
//: declares a control appears, and one that does not, does not.
export function capabilityRoster(state) {
  const roster = rows(isObject(state) ? state.providers : null).filter(isObject);
  const byCapability = new Map();
  for (const row of roster) {
    for (const control of rows(row.controls)) {
      if (typeof control !== "string") continue;
      if (!byCapability.has(control)) byCapability.set(control, []);
      byCapability.get(control).push(row);
    }
  }
  return {roster, byCapability, names: [...byCapability.keys()].sort()};
}

// -- an edge, when an edge is what is selected -----------------------------

function edgePanel(mount, form, id) {
  const parts = String(id).split(" ");
  const box = panelOf("edge", "Connection");
  if (parts.length !== 2) {
    note(box, "This selection does not name two steps.");
    mount.append(box);
    return;
  }
  context(box, "From", parts[0], "the workflow document");
  context(box, "To", parts[1], "the workflow document");
  unsupported(box, "Condition", "A connection carries exactly the two steps "
    + "it joins; there is no condition field for one to be stored in.");
  const drop = element("button", {className: "studio-action",
    "data-action": "delete-edge", "data-focus": "action-delete-edge",
    type: "button"}, [element("span", {text: "Disconnect"})]);
  drop.addEventListener("click", () => call(form.handlers, "onEdit", {
    type: "delete-edge", fromId: parts[0], toId: parts[1]}));
  box.append(editable(drop, form));
  mount.append(box);
}

// -- focus, kept across an idempotent re-render ----------------------------

function focusKey(mount) {
  const active = document.activeElement;
  if (!active || !mount.contains(active)) return null;
  return active.getAttribute ? active.getAttribute("data-focus") : null;
}

function restoreFocus(mount, key) {
  if (!key) return;
  const successor = mount.querySelector(`[data-focus="${key}"]`);
  if (successor) successor.focus();
}

function documentHeader(shown) {
  const head = element("div", {className: "studio-inspector__head",
    "data-document": shown.kind});
  head.append(element("p", {className: "studio-inspector__document",
    text: shown.kind === "draft"
      ? "Editing the DRAFT. Every change below is written to this workflow's "
        + "draft document, which is stored on the server."
      : shown.kind === "published"
        ? `Showing published revision${shown.revision === null ? ""
          : ` ${shown.revision}`}. A published revision is immutable, so every `
          + "control here is disabled. Edit as new draft copies it into a "
          + "draft you can change; this revision stays exactly as it is."
        : "No workflow document is open."}));
  return head;
}

/**
 * Draw the six sections for the selected step, or say what is selected instead.
 *
 * @param {Element} mount the inspector container (`#workflowInspector`)
 * @param {object} state the reducer's frozen value
 * @param {object} handlers `onSelect`, `onEdit`, `onStatus`
 */
export function mountInspector(mount, state, handlers) {
  const key = focusKey(mount);
  const shown = inspectedDocument(state);
  const selection = selectionOf(state);
  const nodes = rows(shown.document && shown.document.nodes).filter(
    (row) => isObject(row) && typeof row.node_id === "string");
  const edges = rows(shown.document && shown.document.edges).filter(
    (row) => isObject(row) && typeof row.from_node === "string"
      && typeof row.to_node === "string");
  const base = {capabilities: capabilityRoster(state), edges,
    editable: shown.kind === "draft", handlers, nodes};
  mount.replaceChildren(documentHeader(shown));
  if (selection.kind === "edge") {
    edgePanel(mount, base, selection.id);
    restoreFocus(mount, key);
    return;
  }
  const node = nodes.find((row) => row.node_id === selection.id);
  if (!node) {
    mount.append(element("p", {className: "studio-inspector__empty", text:
      "No step is selected. Choose one on the canvas, or press an arrow key "
      + "with the canvas focused."}));
    restoreFocus(mount, key);
    return;
  }
  const form = {...base, node, run: runContext(state, node.node_id)};
  mount.append(generalSection(form), assignmentSection(form),
    executionSection(form), artifactSection(form), verificationSection(form),
    transitionSection(form), stepActions(form));
  restoreFocus(mount, key);
}
