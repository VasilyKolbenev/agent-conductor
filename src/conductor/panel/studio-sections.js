"use strict";
// The inspector's CONTROLS: the six sections, in one order, and the field
// primitives every one of them is built from.
//
// Split out of `studio-inspector.js` when that module reached the project's
// line cap, at the seam the two halves already had. What stayed there is the
// FRAME: which document is open, which node is selected, what a run bound to
// this step, and where the sections go. What is here is the controls for one
// step -- and that is where the work is, because every field this product
// learns to store is a control in one of these six sections.
//
// The primitives came with them and then left again, when this file reached
// the cap in its turn: they are `studio-fields.js` now, at the seam the header
// above already named. The dependency still runs one way and it now runs
// through three files -- the frame knows about the sections, the sections know
// about the primitives, and the primitives know nothing about either.
//
// The completeness rule is this module's to keep. A field is finished when it
// is validated in the primitive it is built from, written through
// `handlers.onEdit`, stored by the draft route and read back by the real
// product -- or it says, in place, that this harness does not support it.
// Nothing here writes inert data and nothing silently disappears; every
// unsupported line carries `data-unsupported`.
import {element, field} from "./command-view.js";
import {
  ID_PATTERN,
  MAX_PURPOSE,
  actionButton,
  call,
  commit,
  context,
  editable,
  note,
  option,
  panelOf,
  sectionOf,
  selectField,
  suggestedField,
  textField,
  unsupported,
} from "./studio-fields.js";
import {CEILINGS} from "./studio-model.js";

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
//: The same closed edit vocabulary `studio-canvas.EDIT_TYPES` names, so both
//: surfaces reach the draft through one callback and one word list.
export const EDIT_TYPES = Object.freeze([
  "add", "connect", "delete-edge", "delete-node", "duplicate", "move",
  "reorder", "set-field",
]);
//: Every field name an inspector edit may carry. `loop_bound` and `loop_back_to`
//: are spelled flat because an edit names ONE field, and a nested path would be
//: a second grammar for slice D to parse.
export const EDIT_FIELDS = Object.freeze([
  "attempt_bound", "capability", "gate_id", "kind", "loop_back_to",
  "loop_bound", "purpose", "resources", "role_id", "stage",
  "timeout_seconds", "title", "verifier_role_id",
]);
//: The six sections, in the one order the design fixes them in.
export const SECTIONS = Object.freeze([
  "general", "assignment", "execution", "artifacts", "verification",
  "transitions",
]);

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }

// -- the sections ----------------------------------------------------------

//: Every role THIS document names, of either kind. A role a step carries out
//: and a role that verifies one are both roles a run binds, so an offer list
//: that read only the first would hide exactly the reviewer this control exists
//: to name. `roleNames` in `studio-runform.js` reads the same union one screen
//: over, and for the same reason.
function roleOffers(form) {
  const found = new Set();
  for (const node of rows(form.nodes)) {
    if (!isObject(node)) continue;
    for (const role of [node.role_id, node.verifier_role_id]) {
      if (typeof role === "string" && role !== "") found.add(role);
    }
  }
  return [...found].sort();
}

//: The furthest from the origin a step may be put. `graph_template`'s
//: `POSITION_LIMIT` and `studio-edits` hold the same number; this one bounds
//: the SPINNER, so the browser refuses out of range before a keystroke becomes
//: an edit the reducer would have to talk somebody out of.
const POSITION_LIMIT = 100000;

//: Where a step sits, editable by typing as well as by dragging.
//:
//: The mandate asks for every canvas operation to be reachable through the
//: inspector, and a position was the one that was not: a step could be placed
//: by pointer and by Alt+arrow and by nothing a person could TYPE. It emits the
//: same `move` edit the drag emits -- one operation, two surfaces, not two
//: implementations of one idea.
//:
//: Both axes are committed together, from the pair's current values, because
//: `NodePosition` refuses a half-placed step: an x with no y would be drawn at
//: a coordinate this window invented and nobody could tell it from one they
//: chose.
function positionControls(box, form) {
  const at = isObject(form.node.position) ? form.node.position : null;
  const axes = {};
  const send = () => call(form.handlers, "onEdit", {
    type: "move", nodeId: form.node.node_id,
    x: axes.x.value === "" ? 0 : Number(axes.x.value),
    y: axes.y.value === "" ? 0 : Number(axes.y.value)});
  for (const name of ["x", "y"]) {
    const input = element("input", {"data-edit-field": `position_${name}`,
      "data-focus": `edit-position-${name}`, max: String(POSITION_LIMIT),
      min: String(-POSITION_LIMIT), name: `position_${name}`,
      placeholder: "laid out", step: "1", type: "number"});
    input.value = at === null ? "" : String(at[name]);
    input.addEventListener("change", send);
    const wrapper = field(`Canvas ${name}`, editable(input, form));
    wrapper.classList.add("studio-field");
    box.append(wrapper);
    axes[name] = input;
  }
  if (at !== null) {
    actionButton(box, form, "Let the canvas place it", "unplace",
      {type: "move", nodeId: form.node.node_id, clear: true});
  }
  note(box, at === null
    ? "Nobody has placed this step, so the canvas lays it out: its column "
      + "comes from the connections and its row from the document's order. "
      + "Type a pair here, or drag it, and it stays where you put it."
    : "This step was placed. Where it sits is stored in the workflow document "
      + "and comes back on reload — and it is not execution semantics: a run's "
      + "frozen plan carries no coordinate, so moving a box can never change "
      + "what the run does.");
}

// -- 1. General ------------------------------------------------------------

export function generalSection(form) {
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
  positionControls(box, form);
  textField(box, form, "Purpose / description", "purpose", node.purpose || "",
    node.capability === null || node.capability === undefined
      ? "Stored on the step and frozen into every run's plan, where the "
        + "Decisions and Runs screens read it. A step that carries nothing out "
        + "reaches no harness, so this is written for the people who do."
      : "Stored on the step, frozen into the plan, and carried into the frame "
        + "the harness is handed — labelled there as the workflow's own words, "
        + "never as an instruction. One line, at most "
        + `${MAX_PURPOSE} characters.`);
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

export function assignmentSection(form) {
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

//: One control for both plan-side ceilings, because they are one idea: a whole
//: number in the contract's range, or empty for "the plan does not constrain
//: this". The range comes from `CEILINGS`, whose numbers are the Python
//: contract's own, so the field cannot offer what the store would refuse.
function ceilingField(box, form, label, name) {
  const rule = CEILINGS[name];
  const input = element("input", {"data-edit-field": name,
    "data-focus": `edit-${name}`, max: String(rule.max), min: String(rule.min),
    name, placeholder: "no limit", step: "1", type: "number"});
  const held = form.node[name];
  input.value = held === undefined || held === null ? "" : String(held);
  input.addEventListener("change", () => commit(form, name, input.value));
  const wrapper = field(label, editable(input, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper);
}

//: How many bytes each output-limit profile is worth. The Python table
//: `deep_commands.OUTPUT_LIMIT_BYTES` owns the same two numbers, and
//: `tests/test_studio_canvas.py` holds the two copies equal -- a window that
//: showed a budget the spawn does not use would be worse than showing none.
const OUTPUT_LIMIT_BYTES = Object.freeze({small: 4096, normal: 16384});

//: What this step's output budget IS, said in bytes.
//:
//: It said "not supported by this harness" until the spawn actually read the
//: profile. That was true and it was the release verdict's own example of the
//: shape to avoid: a field declared, validated, stored, shipped in both
//: starters and read by nothing. It is read now, so the honest line is the
//: number, where it comes from, and the fact that the provider's own reviewed
//: ceiling still binds -- a plan may ask for less and never for more.
function outputBudget(box, node) {
  const named = (node.arguments || {}).output_limit_profile;
  const bytes = OUTPUT_LIMIT_BYTES[named];
  if (bytes === undefined) {
    context(box, "Output budget",
      "none — this step names no output limit profile, so the provider's own "
      + "reviewed ceiling is what bounds it",
      "the step's capability arguments");
    return;
  }
  context(box, "Output budget", `${named} · ${bytes} bytes`,
    "the step's capability arguments, spent at the spawn");
  note(box, "A CEILING, like the timeout above: the smaller of this and the "
    + "provider's own reviewed limit is what the child may write. Set with the "
    + "capability arguments below, which are composed where a proposal is, "
    + "against the closed schema registered for this capability.");
}

export function executionSection(form) {
  const {node, run} = form;
  const box = sectionOf("execution", "Execution");
  context(box, "Confirmation mode", run && run.mode ? run.mode
    : "none — no run is open", run ? `the envelope of run ${run.runId}`
    : "the run read");
  note(box, "A mode is a RUN's authority ladder, not a step's: the same "
    + "workflow can be run under any of them.");
  ceilingField(box, form, "Timeout (seconds)", "timeout_seconds");
  note(box, "A CEILING, not a default. The action a Human confirms may ask for "
    + "less and never more, and a step that names none is unlimited by the "
    + "plan. Empty means no limit.");
  ceilingField(box, form, "Attempt bound", "attempt_bound");
  note(box, "How many attempts this step may have. Counted the way a loop "
    + "counts its passes -- distinct attempts naming this step -- and spent "
    + "before an action is authorized, so the bound is never exceeded once.");
  outputBudget(box, node);
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

export function artifactSection(form) {
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

//: WHO must confirm this step, as a ROLE and never as a participant: a template
//: may not name an instance, so which person or product fills the role is the
//: RUN's fact, settled by its binding and frozen into the plan as
//: `verifier_instance_id`.
//:
//: The pairing rule is the contract's, stated here rather than only met at the
//: save: `TemplateNode.__post_init__` refuses a verifier on a step that binds no
//: role of its own, because a step that carries nothing out has nothing to
//: verify. Clearing the role clears this with it, over in `studio-edits`.
function verifierControl(box, form) {
  const {node} = form;
  const bound = node.role_id !== null && node.role_id !== undefined;
  suggestedField(box, form, "Verifier role", "verifier_role_id",
    node.verifier_role_id,
    "A role, not a person: a run binds it to a participant like any other. "
    + "Type any name — a reviewer role no step carries out is exactly the "
    + "shape a separate reviewer takes — or pick one this document already "
    + "names.", roleOffers(form));
  note(box, bound
    ? "Naming a verifier here makes this step's confirmation somebody's job in "
      + "every run of this workflow, and Open a run will ask who fills it."
    : "This step binds no role of its own, so it may not name a verifier: a "
      + "step that carries nothing out has nothing to verify. Give it a role "
      + "and a capability under Assignment first.");
}

export function verificationSection(form) {
  const {run} = form;
  const box = sectionOf("verification", "Verification");
  verifierControl(box, form);
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

export function transitionSection(form) {
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

export function stepActions(form) {
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
  note(box, "Order is stored in the document, and it is what the canvas reads "
    + "for the row of a step NOBODY HAS PLACED — a step with a canvas position "
    + "sits where it was put and takes no row. Columns come from the "
    + "connections either way, so moving a step earlier or later never changes "
    + "what depends on what.");
  return box;
}
