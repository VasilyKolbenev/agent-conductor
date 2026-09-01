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
// above already named. Then INPUTS AND OUTPUTS left, whole, for the same
// reason: it is the one of the six that grows, and the artifact trio would have
// pushed this file through the cap in a single slice. It is
// `studio-artifacts.js`, and the frame appends it in the same fourth place.
//
// The dependency still runs one way and it now runs through four files -- the
// frame knows about the sections and about the artifacts, both of those know
// about the primitives, and the primitives know nothing about any of them.
//
// The completeness rule is this module's to keep. A field is finished when it
// is validated in the primitive it is built from, written through
// `handlers.onEdit`, stored by the draft route and read back by the real
// product -- or it says, in place, that this harness does not support it.
// Nothing here writes inert data and nothing silently disappears; every
// unsupported line carries `data-unsupported`.
import {element, field} from "./command-view.js";
//: The REVIEWED argument schemas, projected. The Cockpit's proposal composer is
//: built from this same table, so a choice this inspector offers is a choice
//: that door already admits -- and there is no second vocabulary to keep equal.
import {CAPABILITY_FIELDS} from "./command-projection.js";
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
  withArgument,
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
//: `graph_definition.MIN_LOOP_BOUND` / `MAX_LOOP_BOUND` moved to
//: `studio-transitions.js` with the one control that spends it. Left here it
//: would be a second copy of a bound nobody in this file reads.
//: `graph_definition.MAX_RESOURCES`.
export const MAX_RESOURCES = 16;
//: `graph_values.REQUIRED_EVIDENCE` -- what a plan may require of a step's
//: verification BEYOND the fact that one happened. A closed vocabulary this
//: window mirrors rather than invents, held to its Python owner by
//: `tests/test_studio_canvas.py`, and closed in one direction only: every word
//: in it asks for MORE proof, and there is none for less.
export const REQUIRED_EVIDENCE = Object.freeze(["digest"]);
//: `graph_values.FAILURE_POLICIES` -- what a plan may do to the REST of a
//: run when one step fails. Held to the Python owner by
//: tests/test_studio_canvas.py rather than trusted here.
export const FAILURE_POLICIES = Object.freeze(["halt_run"]);
//: The same closed edit vocabulary `studio-canvas.EDIT_TYPES` names, so both
//: surfaces reach the draft through one callback and one word list.
export const EDIT_TYPES = Object.freeze([
  "add", "connect", "delete-edge", "delete-node", "duplicate", "move",
  "reorder", "set-edge-condition", "set-field",
]);
//: Every field name an inspector edit may carry. `loop_bound` and `loop_back_to`
//: are spelled flat because an edit names ONE field, and a nested path would be
//: a second grammar for slice D to parse.
export const EDIT_FIELDS = Object.freeze([
  "arguments", "attempt_bound", "capability", "failure_policy", "gate_id",
  "kind", "loop_back_to", "loop_bound", "purpose", "required_evidence",
  "resources", "role_id", "stage", "timeout_seconds", "title",
  "verifier_role_id",
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

//: The one capability argument this window WRITES, named once so the control,
//: the lookup and the edit cannot drift apart.
const OUTPUT_LIMIT_FIELD = "output_limit_profile";

//: What the REVIEWED schema declares one enum field of one capability may be.
//:
//: Read out of `CAPABILITY_FIELDS` -- the same projection the Cockpit's own
//: proposal composer is built from -- so this window offers exactly the words
//: that schema admits and can never grow a second vocabulary beside it. That is
//: the whole reason this is a lookup and not a list: a capability is a word the
//: roster supplies at run time, so a control that named one would be a second,
//: silent copy of a schema somebody else reviews.
//:
//: A capability this build carries no row for, or a row that does not declare
//: this field as an enum, answers null -- and the control then says the step
//: cannot name one rather than inventing choices for it.
function enumChoices(capability, field) {
  if (typeof capability !== "string"
      || !Object.hasOwn(CAPABILITY_FIELDS, capability)) return null;
  const row = CAPABILITY_FIELDS[capability].find(
    (entry) => entry[0] === field && entry[1] === "enum");
  return row === undefined ? null : row[2];
}

//: One profile said the way a person can act on it. A word the projection
//: admits and this build has no byte count for is NAMED as that, never shown as
//: `undefined bytes`: the two tables are held equal by a test, and this is what
//: the screen does on the day they are not.
function budgetLabel(word) {
  return Object.hasOwn(OUTPUT_LIMIT_BYTES, word)
    ? `${word} · ${OUTPUT_LIMIT_BYTES[word]} bytes`
    : `${word} · this build knows no byte count for it`;
}

//: The select that writes it. Empty is offered beside the profiles, and it is
//: not decoration: a step that names no profile is the state every dispatch
//: step this window draws starts in, so a control that could not return one
//: there would be the one-way door `unplaceNode` exists to refuse. What it
//: costs is stated beside it rather than met at a run that will not start.
function budgetSelect(box, form, choices, named) {
  const control = element("select", {"data-edit-field": OUTPUT_LIMIT_FIELD,
    "data-focus": `edit-${OUTPUT_LIMIT_FIELD}`, name: OUTPUT_LIMIT_FIELD},
  [option("", "no profile")].concat(
    choices.map((word) => option(word, budgetLabel(word)))));
  control.value = choices.includes(named) ? named : "";
  control.addEventListener("change", () => commit(form, "arguments",
    withArgument(form.node, OUTPUT_LIMIT_FIELD, control.value)));
  const wrapper = field("Output budget", editable(control, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper);
}

//: What this step's output budget IS, said in bytes, and the control that sets
//: it.
//:
//: It said "not supported by this harness" until the spawn actually read the
//: profile, and then stated it read-only. Both were the release verdict's own
//: example of the shape to avoid: a field declared, validated, stored, shipped
//: in both starters, and reachable from nowhere a person could change it.
function outputBudget(box, form) {
  const {node} = form;
  const held = isObject(node.arguments) ? node.arguments : {};
  const named = held[OUTPUT_LIMIT_FIELD];
  const choices = enumChoices(node.capability, OUTPUT_LIMIT_FIELD);
  if (choices === null) {
    context(box, "Output budget", "none — the reviewed schema for this step's "
      + "capability declares no output limit profile, so there is none to name",
    "the step's capability arguments");
    return;
  }
  budgetSelect(box, form, choices, named);
  context(box, "Output budget", choices.includes(named) ? budgetLabel(named)
    : "none — this step names no output limit profile, so the provider's own "
      + "reviewed ceiling is what bounds it",
  "the step's capability arguments, spent at the spawn");
  note(box, "A CEILING, like the timeout above: the smaller of this and the "
    + "provider's own reviewed limit is what the child may write. The choices "
    + "are the reviewed schema's own, and every other argument of this step is "
    + "carried across untouched when this one changes. Leaving it at no profile "
    + "is a real answer and it has a plain cost: this schema REQUIRES the "
    + "field, so while a dispatching step names none, no run of this workflow "
    + "can be opened at all — the open-run route refuses it, by the contract "
    + "rather than by this window.");
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
  outputBudget(box, form);
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

// -- 4. Inputs and outputs is `studio-artifacts.js` -------------------------
//
// It left when this module neared the cap, whole rather than in pieces: the
// frame imports `artifactSection` from there and appends it in the same place.
// Nothing of it stayed behind, so there is no half of that section here to
// drift away from the other.

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

//: What each word of the vocabulary ASKS FOR, said the way somebody choosing it
//: has to read it. A word the contract carries and this build has no sentence
//: for is NAMED as that rather than offered as a bare token -- `budgetLabel`'s
//: shape next door, and it is what the screen does on the day the two move
//: apart rather than showing `undefined`.
const EVIDENCE_DEMANDS = Object.freeze({
  digest: "the verification must name what it checked",
});

function evidenceLabel(word) {
  return Object.hasOwn(EVIDENCE_DEMANDS, word) ? EVIDENCE_DEMANDS[word]
    : `${word} — this build has no sentence for what it requires`;
}

//: WHAT this step's verification must name, beyond having happened.
//:
//: The pairing rule is the contract's, met here rather than only at the save:
//: `TemplateNode.__post_init__` refuses a requirement on a step that binds no
//: role of its own, because a step that carries nothing out is verified by
//: nobody and there is no verification to require anything of. So that step
//: gets the reason and no control, which is the shape `outputBudget` already
//: has for a capability whose schema declares no profile. Clearing the role
//: clears this with it, over in `studio-edits`.
function evidenceRequirement(box, form) {
  const {node} = form;
  const named = typeof node.required_evidence === "string"
    ? node.required_evidence : "";
  if (node.role_id === null || node.role_id === undefined) {
    context(box, "Evidence requirements", "none — this step binds no role, so "
      + "nobody verifies it and there is no verification to require anything "
      + "of", "the workflow contract");
    return;
  }
  selectField(box, form, "Evidence requirements", "required_evidence",
    [{value: "", label: "no requirement — the verification is held to the "
      + "runtime's own rule"}].concat(REQUIRED_EVIDENCE.map(
      (word) => ({value: word, label: evidenceLabel(word)}))),
    named);
  context(box, "Evidence requirements",
    REQUIRED_EVIDENCE.includes(named) ? evidenceLabel(named)
      : "none — this step is held to the runtime's own rule and to nothing "
        + "more", "the workflow document");
  note(box, "A TIGHTENING, and only ever a tightening. Every step already needs "
    + "a verification signed by the one adapter this plan makes authoritative "
    + "for it, recorded after the work was observed. What a requirement adds is "
    + "that the verification NAME what it checked. A run whose step asks for "
    + "this and whose harness writes no digest records verification_failed "
    + "instead of succeeded — and the same refusal is made again when the "
    + "journal is replayed from disk, so a hand-written record cannot buy the "
    + "success either.");
}

//: The one word a plan may say about what a FAILURE does to the rest of the run.
//:
//: A tightening and never routing, and the sentences below have to keep the two
//: apart or the control is worse than none: an `on_failed` road says where the
//: plan goes next, and this says nothing further may be authorized at all --
//: including branches no road from this step could reach. A person choosing it
//: is entitled to know it is the second thing and not the first.
//:
//: The pairing rule is the contract's, met here rather than only at the save:
//: a step binding no role of its own carries nothing out and cannot fail, so it
//: gets the reason and no control -- the shape `evidenceRequirement` next door
//: already has. Clearing the role clears this with it, over in `studio-edits`.
function failurePolicy(box, form) {
  const {node} = form;
  const named = typeof node.failure_policy === "string"
    ? node.failure_policy : "";
  if (node.role_id === null || node.role_id === undefined) {
    context(box, "Failure policy", "none — this step binds no role, so it "
      + "carries nothing out and cannot fail", "the workflow contract");
    return;
  }
  selectField(box, form, "Failure policy", "failure_policy",
    [{value: "", label: "no policy — a failure here stops nothing else"},
      {value: "halt_run",
        label: "halt the run — authorize nothing further, anywhere in it"}],
    named);
  context(box, "Failure policy",
    named === "halt_run"
      ? "the whole run stops when this step fails"
      : "none — a failure here ends this step and no more",
    "the workflow document");
  note(box, "This is NOT routing. A connection out of this step may open on "
    + "its failure and send the run somewhere; a policy says the run goes "
    + "nowhere at all. It fires on every failed outcome this build records — "
    + "failed, cancelled, rejected and verification_failed — and never on "
    + "unknown, because unknown means the journal supports no answer and an "
    + "unanswered question stays askable. What it does is make every step that "
    + "could still run blocked, so the run reads stalled and records that "
    + "ending.");
}

//: What the OPEN RUN's own frozen plan demands of this step, which is not
//: necessarily what the draft on screen says: a run materialized before this
//: field was edited follows the plan it was given, and that difference is
//: exactly what somebody looking at both needs told.
//:
//: Read off `run.planned` -- the run's `graph_definition` node -- and never off
//: `run.position`, which is the runtime PROJECTION: an outcome and a phase, and
//: no plan fact at all. A demand is a durable intention, so reading one out of
//: the record of what happened would be reading the wrong document.
function runEvidenceRow(box, form) {
  const {run} = form;
  if (!run) return;
  if (!run.planned) {
    context(box, "Required by the open run", "none — the open run's plan does "
      + "not name this step", `run ${run.runId}`);
    return;
  }
  const demanded = run.planned.required_evidence;
  context(box, "Required by the open run",
    typeof demanded === "string" && demanded !== ""
      ? evidenceLabel(demanded)
      : "nothing beyond the runtime's own rule",
    `the plan of run ${run.runId}`);
  // The POLICY the open run froze, read off the same document and never off
  // the draft: a run materialized before this field was edited follows the
  // plan it was given, and that difference is what somebody looking at both
  // needs told.
  context(box, "If this step fails in the open run",
    run.planned.failure_policy === "halt_run"
      ? "the whole run stops — nothing further may be authorized in it"
      : "this step ends and the rest of the run carries on",
    `the plan of run ${run.runId}`);
}

export function verificationSection(form) {
  const {run} = form;
  const box = sectionOf("verification", "Verification");
  verifierControl(box, form);
  evidenceRequirement(box, form);
  unsupported(box, "Success criteria", "Every criterion a plan could state, "
    + "this build already demands of every step: a success is verified, by the "
    + "one adapter the plan makes authoritative for it, over evidence recorded "
    + "after the work was observed — and, where the step asks for it, naming "
    + "what was checked. Anything a plan could add beside that would be weaker "
    + "than what it is already held to.");
  failurePolicy(box, form);
  runEvidenceRow(box, form);
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
