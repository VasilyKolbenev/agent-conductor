"use strict";
// The node inspector: six sections, in one order, for the step the canvas has
// selected. Every string enters as a text node; this module reaches no network
// and no clock, and it writes nothing but DOM.
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
import {element, field} from "./command-view.js";

// -- vocabularies this module consumes -------------------------------------
//
// Copies of the layers that own them. `tests/test_studio_canvas.py` holds each
// against the PYTHON owner and against `studio-canvas.js`'s copy, which the
// module table forbids importing from here.

//: `graph_definition.NODE_KINDS`.
export const NODE_KINDS = Object.freeze(["task", "gate", "loop"]);
//: `graph_definition.RESOURCE_KINDS` -- the closed attachment vocabulary.
export const RESOURCE_KINDS = Object.freeze([
  "model", "tool", "skill", "session", "sandbox", "filesystem"]);
//: `graph_definition.DALIO_STAGES`, in the ONE order the product numbers them.
export const STAGE_NAMES = Object.freeze([
  "goal", "identify", "diagnose", "design", "do"]);
//: `graph_definition.MIN_LOOP_BOUND` / `MAX_LOOP_BOUND`.
export const LOOP_BOUND = Object.freeze({min: 1, max: 99});
//: `graph_definition.MAX_RESOURCES`.
export const MAX_RESOURCES = 16;
//: `contract_values._ID_RE`, character for character, and the same grammar
//: `command-projection.RUN_ID` already holds on the Cockpit side.
export const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
//: The same closed edit vocabulary `studio-canvas.EDIT_TYPES` names, so both
//: surfaces reach the draft through one callback and one word list.
export const EDIT_TYPES = Object.freeze([
  "add", "connect", "delete-edge", "delete-node", "duplicate", "reorder",
  "set-field",
]);
//: Every field name an inspector edit may carry. `loop_bound` and `loop_back_to`
//: are spelled flat because an edit names ONE field, and a nested path would be
//: a second grammar for slice D to parse.
export const EDIT_FIELDS = Object.freeze([
  "capability", "gate_id", "kind", "loop_back_to", "loop_bound", "resources",
  "role_id", "stage", "title",
]);
//: The six sections, in the one order the design fixes them in.
export const SECTIONS = Object.freeze([
  "general", "assignment", "execution", "artifacts", "verification",
  "transitions",
]);

function call(handlers, name, value) {
  const handler = handlers && handlers[name];
  if (typeof handler === "function") handler(value);
}

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
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

// -- the writers -----------------------------------------------------------

function sectionOf(name, title) {
  return element("section", {className: "studio-section",
    "data-section": name}, [element("h3", {text: title})]);
}

//: Anything that is NOT one of the six. `data-section` names exactly the six
//: the design fixes, so a reader — and a browser test — can count them.
function panelOf(name, title) {
  return element("section", {className: "studio-panel",
    "data-panel": name}, [element("h3", {text: title})]);
}

//: One machine word for a label a human reads, so a test can address a row
//: without matching prose that is allowed to be rewritten.
function slug(label) {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

//: The one shape an unsupported field takes. It NAMES the field, says this
//: harness does not support it, and gives the reason -- so a reader learns
//: what the product does not do rather than finding a gap where a control
//: should be. `data-unsupported` is the machine word beside the sentence.
function unsupported(mount, label, reason) {
  mount.append(element("p", {className: "studio-unsupported",
    "data-unsupported": slug(label)}, [
    element("strong", {text: label}),
    element("span", {text: ` — not supported by this harness. ${reason}`}),
  ]));
}

//: A fact this screen READS and cannot write, with the document it came from
//: named beside it. A value with no named source is a claim nobody can check.
function context(mount, label, value, source) {
  mount.append(element("p", {className: "studio-context",
    "data-context": slug(label)}, [
    element("strong", {text: label}),
    element("span", {className: "mono", text: `: ${value}`}),
    element("i", {className: "mono studio-context__source", text: ` (${source})`}),
  ]));
}

function note(mount, text) {
  mount.append(element("p", {className: "studio-note", text}));
}

function option(value, label) {
  return element("option", {text: label === undefined ? value : label, value});
}

//: Every control this module writes is disabled together when the document on
//: screen cannot be edited, and the reason is on screen rather than implied by
//: a grey box: a published revision is immutable, by design and forever.
function editable(control, form) {
  if (!form.editable) control.disabled = true;
  return control;
}

function commit(form, name, value) {
  call(form.handlers, "onEdit", {
    type: "set-field", nodeId: form.node.node_id, field: name, value});
}

//: What each edited word must be, in the grammar its Python contract already
//: holds it to. A field says what is wrong beside itself and refuses to write,
//: which is the difference between a control that validates and a control that
//: posts a body for the server to reject.
const CHECKS = Object.freeze({
  title: (value) => value.trim() && !value.includes("\0") ? null
    : "A display name must be a non-empty string and must not contain NUL.",
  role_id: (value) => value === "" || ID_PATTERN.test(value) ? null
    : "A role must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}, or be empty.",
  gate_id: (value) => value === "" || ID_PATTERN.test(value) ? null
    : "A gate id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}, or be empty.",
});

//: The error sits beside the control from the first render, `hidden` until it
//: has something to say, so a keyboard reader hears it through
//: `aria-describedby` without this module holding a second copy of the state.
function textField(mount, form, label, name, value, help) {
  const check = CHECKS[name] || (() => null);
  const errorId = `studio-invalid-${name}`;
  const error = element("p", {className: "studio-invalid", hidden: "",
    id: errorId, role: "note"});
  const control = element("input", {
    "aria-describedby": errorId, autocomplete: "off",
    "data-edit-field": name, "data-focus": `edit-${name}`, name,
    spellcheck: "false", type: "text"});
  control.value = value === null || value === undefined ? "" : String(value);
  const judge = () => {
    const said = check(control.value);
    error.textContent = said || "";
    error.hidden = !said;
    control.setAttribute("aria-invalid", said ? "true" : "false");
    return said;
  };
  control.addEventListener("input", judge);
  control.addEventListener("change", () => {
    if (judge()) return;
    commit(form, name, name.endsWith("_id") && control.value === ""
      ? null : control.value);
  });
  const wrapper = field(label, editable(control, form));
  wrapper.classList.add("studio-field");
  mount.append(wrapper, error);
  if (help) note(mount, help);
  return control;
}

function selectField(mount, form, label, name, values, value) {
  const control = element("select", {"data-edit-field": name,
    "data-focus": `edit-${name}`, name}, values.map((row) => option(row.value,
      row.label)));
  control.value = value === null || value === undefined ? "" : String(value);
  control.addEventListener("change", () => commit(form, name,
    control.value === "" ? null : control.value));
  const wrapper = field(label, editable(control, form));
  wrapper.classList.add("studio-field");
  mount.append(wrapper);
  return control;
}

function actionButton(mount, form, label, key, edit) {
  const button = element("button", {className: "studio-action",
    "data-action": key, "data-focus": `action-${key}`, type: "button"},
  [element("span", {text: label})]);
  button.addEventListener("click", () => call(form.handlers, "onEdit", edit));
  mount.append(editable(button, form));
  return button;
}

// -- 1. General ------------------------------------------------------------

function generalSection(form) {
  const {node} = form;
  const box = sectionOf("general", "General");
  context(box, "Stable id", node.node_id, "the workflow document");
  note(box, "A step's id is what its connections, a loop's back_to and every "
    + "run's journal name it by. This build does not rename one: add a step "
    + "and connect it instead.");
  textField(box, form, "Display name", "title", node.title,
    "Stored on the step and materialized into every run's plan as its title.");
  selectField(box, form, "Step type", "kind",
    NODE_KINDS.map((kind) => ({value: kind})), node.kind);
  note(box, "A human gate must name a gate id; a loop must name a bound and "
    + "the step it reopens. Change the type and this draft will say what it "
    + "still needs — a draft is allowed to be incomplete.");
  if (node.kind === "task") {
    selectField(box, form, "Stage (five-step cycle)", "stage",
      [{value: "", label: "no stage"}].concat(STAGE_NAMES.map(
        (name, at) => ({value: name, label: `${at + 1}/5 · ${name}`}))),
      node.stage || "");
  } else {
    context(box, "Stage", "none — a gate or a loop names no stage",
      "the workflow contract");
  }
  unsupported(box, "Purpose / description",
    "A workflow step carries a title and no description field, so a "
    + "paragraph typed here would be stored nowhere and read by nothing.");
  return box;
}

// -- 2. Assignment ---------------------------------------------------------

function compatibilityLine(box, form, capability) {
  if (!capability) {
    note(box, "This step names no capability, so there is nothing to check a "
      + "provider against.");
    return;
  }
  const serving = form.capabilities.byCapability.get(capability) || [];
  if (!serving.length) {
    note(box, `No configured provider declares "${capability}". A run bound `
      + "to this role would have nothing able to carry the step out.");
    return;
  }
  for (const row of serving) {
    context(box, "Can serve it", `${row.provider_id} · ${row.availability}`
      + ` · ${row.implementation}`, "the provider roster this build resolved");
  }
}

function boundProviderLine(box, run, capability, form) {
  if (!run || !run.instance || !capability) return;
  const provider = form.capabilities.roster.find(
    (row) => row.provider_id === run.instance.adapter);
  if (!provider) {
    note(box, "The run's configuration names an adapter this build's provider "
      + "roster does not carry, so nothing can be said about its controls.");
    return;
  }
  const declares = rows(provider.controls).includes(capability);
  context(box, "Bound provider declares this capability", declares ? "yes" : "no",
    `the provider roster, joined to run ${run.runId} by adapter id`);
}

function assignmentSection(form) {
  const {node, run} = form;
  const box = sectionOf("assignment", "Assignment");
  note(box, "A workflow names ROLES. A run binds a role to a participant, and "
    + "a participant names a provider and at most a model. So the two fields "
    + "below are the workflow's; everything under them is a run's, read-only.");
  textField(box, form, "Role", "role_id", node.role_id,
    "A role and a capability are set together or neither: half a binding "
    + "names a step nobody can carry out.");
  selectField(box, form, "Capability", "capability",
    [{value: "", label: "no capability"}].concat(
      form.capabilities.names.map((name) => ({value: name}))),
    node.capability || "");
  note(box, "Every choice above comes from the PROVEN controls the provider "
    + "roster reports for this build. Nothing here is a written-down list.");
  if (!run) {
    note(box, "No run is open, so no participant, provider or model is bound "
      + "to this role yet. Start a run to bind one.");
  } else if (!run.planned) {
    context(box, "Participant", "none — the open run's plan does not name this "
      + "step", `run ${run.runId}`);
  } else {
    context(box, "Participant", String(run.planned.instance_id),
      `the plan of run ${run.runId}`);
    context(box, "Harness / provider", run.instance
      ? String(run.instance.adapter)
      : "unreadable — the run's frozen configuration names no such instance",
    `the frozen configuration of run ${run.runId}`);
    context(box, "Model", modelWord(run.instance),
      `the frozen configuration of run ${run.runId}`);
  }
  compatibilityLine(box, form, node.capability);
  boundProviderLine(box, run, node.capability, form);
  return box;
}

//: Three states and they are three, exactly as `graph-view.appendDeployment`
//: keeps them apart: a pinned model, a configuration that pinned none, and a
//: configuration this window could not read.
function modelWord(instance) {
  if (!instance) return "unreadable — no row for this instance";
  if (instance.model === null || instance.model === undefined) {
    return "none pinned — the provider's own configuration decides";
  }
  return String(instance.model);
}

// -- 3. Execution ----------------------------------------------------------

function resourceRows(box, form) {
  const held = rows(form.node.resources).filter(isObject);
  if (!held.length) note(box, "This step attaches nothing.");
  const list = element("ul", {className: "studio-resources"});
  held.forEach((row, at) => {
    const item = element("li", {className: "mono studio-resource"}, [
      element("span", {text: `${row.kind}: ${row.name}`})]);
    const drop = element("button", {"aria-label": `Remove ${row.kind} `
      + `${row.name}`, className: "studio-resource__drop",
    "data-focus": `resource-drop-${at}`, type: "button"},
    [element("span", {text: "Remove"})]);
    drop.addEventListener("click", () => commit(form, "resources",
      held.filter((_, index) => index !== at)));
    item.append(editable(drop, form));
    list.append(item);
  });
  box.append(list);
  return held;
}

function resourceAdder(box, form, held) {
  const kind = element("select", {"data-focus": "resource-kind",
    name: "resource_kind"}, RESOURCE_KINDS.map((row) => option(row)));
  const name = element("input", {autocomplete: "off",
    "data-focus": "resource-name", name: "resource_name", spellcheck: "false",
    type: "text"});
  const add = element("button", {className: "studio-resource__add",
    "data-focus": "resource-add", type: "button"},
  [element("span", {text: "Attach"})]);
  add.addEventListener("click", () => {
    if (!ID_PATTERN.test(name.value)) {
      call(form.handlers, "onStatus", "An attachment name must match "
        + "[A-Za-z0-9][A-Za-z0-9._-]{0,127}.");
      return;
    }
    if (held.length >= MAX_RESOURCES) {
      call(form.handlers, "onStatus",
        `A step attaches at most ${MAX_RESOURCES} resources.`);
      return;
    }
    commit(form, "resources", held.concat([{kind: kind.value, name: name.value}]));
  });
  const kindField = field("Attachment kind", editable(kind, form));
  const nameField = field("Attachment name", editable(name, form));
  for (const wrapper of [kindField, nameField]) wrapper.classList.add("studio-field");
  box.append(kindField, nameField, editable(add, form));
}

function argumentRows(box, node) {
  const payload = isObject(node.arguments) ? node.arguments : {};
  const names = Object.keys(payload).sort();
  if (!names.length) {
    note(box, "This step carries no capability arguments.");
    return;
  }
  box.append(element("ul", {className: "studio-arguments"}, names.map(
    (name) => element("li", {className: "mono", text: `${name}: `
      + (isObject(payload[name]) || Array.isArray(payload[name])
        ? "(a structured value)" : String(payload[name]))}))));
}

function executionSection(form) {
  const {node, run} = form;
  const box = sectionOf("execution", "Execution");
  context(box, "Confirmation mode", run && run.mode ? run.mode
    : "none — no run is open", run ? `the envelope of run ${run.runId}`
    : "the run read");
  note(box, "A mode is a RUN's authority ladder, not a step's: the same "
    + "workflow can be run under any of them.");
  unsupported(box, "Timeout", "A timeout is a per-action field carried on a "
    + "proposal, not on a workflow step; a number typed here would reach no "
    + "run.");
  unsupported(box, "Retry / attempt bound", "The only bound a workflow "
    + "document carries is a loop's, and it is edited under Transitions.");
  unsupported(box, "Output budget", "This build carries no output budget on a "
    + "workflow step. The reviewed dispatch arguments carry an output limit "
    + "profile, and those are set where a proposal is composed.");
  box.append(element("h4", {text: "Sandbox and policy attachments"}));
  note(box, "The closed attachment vocabulary a step may declare. `sandbox` "
    + "and `filesystem` are the policy-bearing kinds; every one of them is "
    + "stored on the step and materialized into a run's plan.");
  resourceAdder(box, form, resourceRows(box, form));
  box.append(element("h4", {text: "Provider-specific options"}));
  argumentRows(box, node);
  note(box, "Read-only here. Capability arguments are judged by the reviewed "
    + "closed schema registered for that capability, and they are composed at "
    + "the Cockpit's proposal door where that schema is enforced. This "
    + "inspector will not write a free-form payload past it.");
  return box;
}

// -- 4. Inputs and outputs -------------------------------------------------

function artifactSection(form) {
  const {run} = form;
  const box = sectionOf("artifacts", "Inputs and outputs");
  unsupported(box, "Required input artifacts", "A workflow step declares "
    + "resources — model, tool, skill, session, sandbox, filesystem — and no "
    + "artifact requirement, so nothing would read one.");
  unsupported(box, "Produced artifacts", "A workflow step declares no output "
    + "contract. What a run actually produced is durable, and it is shown "
    + "below as the run's own fact.");
  unsupported(box, "Handoff mapping", "This build carries no step-to-step "
    + "artifact mapping in a workflow document.");
  unsupported(box, "Missing-artifact behaviour", "With no declared artifact "
    + "requirement there is no missing-artifact case for a policy to answer.");
  const refs = run && run.position ? rows(run.position.evidence_refs) : [];
  if (run && run.position) {
    context(box, "Evidence references", refs.length ? refs.join(", ") : "none",
      `the durable records of run ${run.runId}`);
    note(box, "Identifiers only. Nothing here states that any of them "
      + "verified anything.");
  }
  return box;
}

// -- 5. Verification -------------------------------------------------------

function verificationSection(form) {
  const {run} = form;
  const box = sectionOf("verification", "Verification");
  unsupported(box, "Verifier", "A workflow step names no verifier. "
    + "Verification is recorded on the evidence a run produces, by the "
    + "contract that validated it.");
  unsupported(box, "Evidence requirements", "This build carries no per-step "
    + "evidence requirement in a workflow document.");
  unsupported(box, "Success criteria", "A workflow step states no success "
    + "criteria; an outcome is reported by the immutable result record of a "
    + "run and by nothing a plan could assert in advance.");
  unsupported(box, "Verification failure policy", "With no declared criteria "
    + "there is no failure policy for a plan to carry.");
  note(box, "Process exit 0 proves the process finished, not that the work "
    + "was verified. A run that reports verification_failed reached its "
    + "boundary and did not prove its work.");
  if (run && run.position) {
    context(box, "Outcome recorded", run.position.outcome === null
      || run.position.outcome === undefined
      ? "none — no result record for the current action"
      : String(run.position.outcome), `the durable records of run ${run.runId}`);
    context(box, "Position", String(run.position.phase),
      `the projection of run ${run.runId}, computed and stored nowhere`);
  }
  return box;
}

// -- 6. Transitions --------------------------------------------------------

function outgoingRows(box, form) {
  const outgoing = form.edges.filter((edge) => edge.from_node === form.node.node_id);
  if (!outgoing.length) {
    note(box, "No outgoing connection: this step ends the plan as drawn.");
    return;
  }
  const list = element("ul", {className: "studio-edges"});
  for (const edge of outgoing) {
    const id = `${edge.from_node} ${edge.to_node}`;
    const item = element("li", {className: "studio-edge-row", "data-edge": id});
    const open = element("button", {className: "studio-edge-row__select",
      "data-focus": `edge-select-${id}`, type: "button"},
    [element("span", {className: "mono", text: `→ ${edge.to_node}`})]);
    open.addEventListener("click", () => call(form.handlers, "onSelect",
      {kind: "edge", id}));
    const drop = element("button", {"aria-label": `Disconnect `
      + `${edge.from_node} from ${edge.to_node}`,
    className: "studio-edge-row__drop", "data-focus": `edge-drop-${id}`,
    type: "button"}, [element("span", {text: "Disconnect"})]);
    drop.addEventListener("click", () => call(form.handlers, "onEdit", {
      type: "delete-edge", fromId: edge.from_node, toId: edge.to_node}));
    item.append(open, editable(drop, form));
    list.append(item);
  }
  box.append(list);
}

function connectControl(box, form) {
  const others = form.nodes.filter((row) => row.node_id !== form.node.node_id);
  if (!others.length) {
    note(box, "There is no other step to connect this one to.");
    return;
  }
  const target = element("select", {"data-focus": "connect-target",
    name: "connect_to"}, others.map((row) => option(row.node_id,
      `${row.node_id} — ${row.title}`)));
  const go = element("button", {className: "studio-connect",
    "data-focus": "connect-go", type: "button"},
  [element("span", {text: "Connect"})]);
  go.addEventListener("click", () => call(form.handlers, "onEdit", {
    type: "connect", fromId: form.node.node_id, toId: target.value}));
  const wrapper = field("Connect to", editable(target, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper, editable(go, form));
}

function gateControls(box, form) {
  if (form.node.kind === "gate") {
    textField(box, form, "Gate id", "gate_id", form.node.gate_id,
      "The id a Human's decision receipt names. A run's gate state is read "
      + "through it, and through nothing else.");
  } else {
    context(box, "Human decision", "none — only a gate step carries one",
      "the workflow contract");
  }
  unsupported(box, "Decision routing", "This build runs one plan: a decision "
    + "records approval, rejection, changes requested or a waiver, and it "
    + "does not choose between two different onward paths.");
}

function loopControls(box, form) {
  if (form.node.kind !== "loop") {
    context(box, "Loop", "none — only a loop step reopens work",
      "the workflow contract");
    return;
  }
  const loop = isObject(form.node.loop) ? form.node.loop : {};
  const targets = form.nodes.filter((row) => row.node_id !== form.node.node_id);
  selectField(box, form, "Reopens (back_to)", "loop_back_to",
    targets.map((row) => ({value: row.node_id,
      label: `${row.node_id} — ${row.title}`})), loop.back_to || "");
  const bound = element("input", {"data-edit-field": "loop_bound",
    "data-focus": "edit-loop_bound", max: String(LOOP_BOUND.max),
    min: String(LOOP_BOUND.min), name: "loop_bound", step: "1", type: "number"});
  bound.value = loop.bound === undefined ? "" : String(loop.bound);
  bound.addEventListener("change", () => {
    const value = Number(bound.value);
    if (!Number.isInteger(value) || value < LOOP_BOUND.min
        || value > LOOP_BOUND.max) {
      call(form.handlers, "onStatus", `A loop bound is a whole number from `
        + `${LOOP_BOUND.min} to ${LOOP_BOUND.max}.`);
      return;
    }
    commit(form, "loop_bound", value);
  });
  const wrapper = field("Loop bound (greatest pass)", editable(bound, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper);
  note(box, "A bound is a ceiling on the POSITION — the greatest pass this "
    + "work may reach — never a count of reopenings beside it. Which pass a "
    + "run is on is the run's own fact and is shown under Assignment's run "
    + "context, never here.");
}

function transitionSection(form) {
  const box = sectionOf("transitions", "Transitions");
  box.append(element("h4", {text: "Outgoing connections"}));
  outgoingRows(box, form);
  connectControl(box, form);
  unsupported(box, "Edge conditions", "A connection carries exactly the two "
    + "steps it joins. There is no condition field for one to be stored in.");
  box.append(element("h4", {text: "Human decision routing"}));
  gateControls(box, form);
  box.append(element("h4", {text: "Loop"}));
  loopControls(box, form);
  return box;
}

// -- the step's own actions ------------------------------------------------

function stepActions(form) {
  const box = panelOf("actions", "This step");
  const at = form.nodes.findIndex((row) => row.node_id === form.node.node_id);
  actionButton(box, form, "Move earlier", "earlier",
    {type: "reorder", nodeId: form.node.node_id, index: at - 1});
  actionButton(box, form, "Move later", "later",
    {type: "reorder", nodeId: form.node.node_id, index: at + 1});
  actionButton(box, form, "Duplicate", "duplicate",
    {type: "duplicate", nodeId: form.node.node_id});
  actionButton(box, form, "Delete step", "delete",
    {type: "delete-node", nodeId: form.node.node_id});
  note(box, "Order is what the canvas rows read, and it is stored in the "
    + "document. Columns come from the connections, so moving a step earlier "
    + "or later never changes what depends on what.");
  return box;
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
          + "control here is disabled."
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
