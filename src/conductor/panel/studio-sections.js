"use strict";
import {localize} from "./studio-i18n.js";
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
import {CEILINGS} from "./studio-ceilings.js";

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
  "kind", "loop_back_to", "loop_bound", "missing_artifact_policy",
  "purpose", "required_evidence", "resources", "role_id", "stage",
  "success_requires", "timeout_seconds", "title", "verifier_role_id",
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
      placeholder: localize(form.state || {}, "workflow.copy_8"), step: "1", type: "number"});
    input.value = at === null ? "" : String(at[name]);
    input.addEventListener("change", send);
    const wrapper = field(localize(form.state || {}, name === "x" ? "workflow.canvas_x" : "workflow.canvas_y"),
      editable(input, form));
    wrapper.classList.add("studio-field");
    box.append(wrapper);
    axes[name] = input;
  }
  if (at !== null) {
    actionButton(box, form, localize(form.state || {}, "workflow.copy_9"), "unplace",
      {type: "move", nodeId: form.node.node_id, clear: true});
  }
  note(box, at === null
    ? localize(form.state || {}, "workflow.copy_10")
    : localize(form.state || {}, "workflow.copy_11"));
}

// -- 1. General ------------------------------------------------------------

export function generalSection(form) {
  const {node} = form;
  const box = sectionOf("general", localize(form.state || {}, "workflow.copy_12"));
  context(box, localize(form.state || {}, "workflow.copy_13"), node.node_id, localize(form.state || {}, "workflow.copy_14"));
  note(box, localize(form.state || {}, "workflow.copy_15"));
  textField(box, form, localize(form.state || {}, "workflow.copy_16"), "title", node.title,
    localize(form.state || {}, "workflow.copy_17"));
  selectField(box, form, localize(form.state || {}, "workflow.copy_18"), "kind",
    NODE_KINDS.map((kind) => ({value: kind, label: localize(form.state || {}, `workflow.kind_${kind}`)})), node.kind);
  note(box, localize(form.state || {}, "workflow.copy_19"));
  if (node.kind === "task") {
    selectField(box, form, localize(form.state || {}, "workflow.copy_20"), "stage",
      [{value: "", label: localize(form.state || {}, "workflow.copy_21")}].concat(STAGE_NAMES.map(
        (name, at) => ({value: name, label: `${at + 1}/5 · ${localize(form.state || {}, `workflow.stage_${name}`)}`}))),
      node.stage || "");
  } else {
    context(box, localize(form.state || {}, "workflow.copy_22"), localize(form.state || {}, "workflow.copy_23"),
      localize(form.state || {}, "workflow.copy_24"));
  }
  positionControls(box, form);
  textField(box, form, localize(form.state || {}, "workflow.copy_25"), "purpose", node.purpose || "",
    node.capability === null || node.capability === undefined
      ? localize(form.state || {}, "workflow.copy_26")
      : localize(form.state || {}, "workflow.purpose_help", {max: String(MAX_PURPOSE)}));
  return box;
}

// -- 2. Assignment ---------------------------------------------------------

function compatibilityLine(box, form, capability) {
  if (!capability) {
    note(box, localize(form.state || {}, "workflow.copy_28"));
    return;
  }
  const serving = form.capabilities.byCapability.get(capability) || [];
  if (!serving.length) {
    note(box, localize(form.state || {}, "workflow.no_provider", {capability: String(capability)}));
    return;
  }
  for (const row of serving) {
    context(box, localize(form.state || {}, "workflow.copy_30"), `${row.provider_id} · ${row.availability}`
      + ` · ${row.implementation}`, localize(form.state || {}, "workflow.copy_31"));
  }
}

function boundProviderLine(box, run, capability, form) {
  if (!run || !run.instance || !capability) return;
  const provider = form.capabilities.roster.find(
    (row) => row.provider_id === run.instance.adapter);
  if (!provider) {
    note(box, localize(form.state || {}, "workflow.copy_32"));
    return;
  }
  const declares = rows(provider.controls).includes(capability);
  context(box, localize(form.state || {}, "workflow.copy_33"), localize(form.state || {}, "workflow.yes_no", {answer: localize(form.state || {}, declares ? "workflow.yes" : "workflow.no")}),
    localize(form.state || {}, "workflow.source_roster", {run: String(run.runId)}));
}

export function assignmentSection(form) {
  const {node, run} = form;
  const box = sectionOf("assignment", localize(form.state || {}, "workflow.copy_34"));
  note(box, localize(form.state || {}, "workflow.copy_35"));
  textField(box, form, localize(form.state || {}, "workflow.copy_36"), "role_id", node.role_id,
    localize(form.state || {}, "workflow.copy_37"));
  selectField(box, form, localize(form.state || {}, "workflow.copy_38"), "capability",
    [{value: "", label: localize(form.state || {}, "workflow.copy_39")}].concat(
      form.capabilities.names.map((name) => ({value: name}))),
    node.capability || "");
  note(box, localize(form.state || {}, "workflow.copy_40"));
  if (!run) {
    note(box, localize(form.state || {}, "workflow.copy_41"));
  } else if (!run.planned) {
    context(box, localize(form.state || {}, "workflow.copy_42"), localize(form.state || {}, "workflow.copy_43"), localize(form.state || {}, "workflow.source_run", {run: String(run.runId)}));
  } else {
    context(box, localize(form.state || {}, "workflow.copy_44"), String(run.planned.instance_id),
      localize(form.state || {}, "workflow.source_plan", {run: String(run.runId)}));
    context(box, localize(form.state || {}, "workflow.copy_45"), run.instance
      ? String(run.instance.adapter)
      : localize(form.state || {}, "workflow.copy_46"),
    localize(form.state || {}, "workflow.source_config", {run: String(run.runId)}));
    context(box, localize(form.state || {}, "workflow.copy_47"), modelWord(run.instance, form),
      localize(form.state || {}, "workflow.source_config", {run: String(run.runId)}));
  }
  compatibilityLine(box, form, node.capability);
  boundProviderLine(box, run, node.capability, form);
  return box;
}

//: Three states and they are three, exactly as `graph-view.appendDeployment`
//: keeps them apart: a pinned model, a configuration that pinned none, and a
//: configuration this window could not read.
function modelWord(instance, form) {
  if (!instance) return localize(form.state || {}, "workflow.copy_48");
  if (instance.model === null || instance.model === undefined) {
    return localize(form.state || {}, "workflow.copy_49");
  }
  return String(instance.model);
}

// -- 3. Execution ----------------------------------------------------------

//: `containment.SANDBOX_ROUTES` -- every route demand this build can actually
//: meet. Held to the Python owner by a source test rather than trusted here.
export const SANDBOX_ROUTES = Object.freeze(["project-root"]);
//: The one attachment kind this build spends. Named so the sentence below can
//: say which of the six does something without naming five of them twice.
const CONSUMED_KIND = "sandbox";

//: What the attachments mean, in the vocabulary of the module that enforces
//: them, and what they do NOT mean.
//:
//: The word "sandbox" is never left to stand on its own here. What a
//: `project-root` demand buys is ROUTE CONTAINMENT: before a child is started
//: its working route is walked from the project root with `os.lstat`, and the
//: walk refuses a symlink, a junction, a reparse point, a hard link, a `..`
//: segment, or anything not strictly beneath the root. That is a structural
//: door, not an operating-system one -- there is no privilege drop and no
//: filesystem jail anywhere in this build -- and the walk establishes its facts
//: at the instant it reads them, so a component swapped concurrently and an
//: NTFS alternate data stream are outside it. Saying otherwise on this screen
//: would be selling a promise the product does not keep.
function routeAttachments(box, form) {
  note(box, localize(form.state || {}, "workflow.copy_50"));
  note(box, localize(form.state || {}, "workflow.copy_51"));
  note(box, localize(form.state || {}, "workflow.copy_52"));
  resourceAdder(box, form, resourceRows(box, form));
}

function resourceRows(box, form) {
  const held = rows(form.node.resources).filter(isObject);
  if (!held.length) note(box, localize(form.state || {}, "workflow.copy_53"));
  const list = element("ul", {className: "studio-resources"});
  held.forEach((row, at) => {
    const item = element("li", {className: "mono studio-resource"}, [
      element("span", {text: `${row.kind}: ${row.name}`})]);
    const drop = element("button", {"aria-label": localize(form.state || {}, "workflow.remove_resource", {kind: String(row.kind), name: String(row.name)}), className: "studio-resource__drop",
    "data-focus": `resource-drop-${at}`, type: "button"},
    [element("span", {text: localize(form.state || {}, "workflow.copy_55")})]);
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
    name: "resource_kind"}, RESOURCE_KINDS.map((row) => option(row, localize(form.state || {}, `workflow.resource_${row}`))));
  const name = element("input", {autocomplete: "off",
    "data-focus": "resource-name", name: "resource_name", spellcheck: "false",
    type: "text"});
  const add = element("button", {className: "studio-resource__add",
    "data-focus": "resource-add", type: "button"},
  [element("span", {text: localize(form.state || {}, "workflow.copy_56")})]);
  add.addEventListener("click", () => {
    if (!ID_PATTERN.test(name.value)) {
      call(form.handlers, "onStatus", {key: "workflow.copy_57"});
      return;
    }
    if (held.length >= MAX_RESOURCES) {
      call(form.handlers, "onStatus", {key: "workflow.max_resources", params: {max: String(MAX_RESOURCES)}});
      return;
    }
    commit(form, "resources", held.concat([{kind: kind.value, name: name.value}]));
  });
  const kindField = field(localize(form.state || {}, "workflow.copy_58"), editable(kind, form));
  const nameField = field(localize(form.state || {}, "workflow.copy_59"), editable(name, form));
  for (const wrapper of [kindField, nameField]) wrapper.classList.add("studio-field");
  box.append(kindField, nameField, editable(add, form));
}

function argumentRows(box, node, form) {
  const payload = isObject(node.arguments) ? node.arguments : {};
  const names = Object.keys(payload).sort();
  if (!names.length) {
    note(box, localize(form.state || {}, "workflow.copy_60"));
    return;
  }
  box.append(element("ul", {className: "studio-arguments"}, names.map(
    (name) => element("li", {className: "mono", text: `${name}: `
      + (isObject(payload[name]) || Array.isArray(payload[name])
        ? localize(form.state || {}, "workflow.copy_61") : String(payload[name]))}))));
}

//: One control for both plan-side ceilings, because they are one idea: a whole
//: number in the contract's range, or empty for "the plan does not constrain
//: this". The range comes from `CEILINGS`, whose numbers are the Python
//: contract's own, so the field cannot offer what the store would refuse.
function ceilingField(box, form, label, name) {
  const rule = CEILINGS[name];
  const input = element("input", {"data-edit-field": name,
    "data-focus": `edit-${name}`, max: String(rule.max), min: String(rule.min),
    name, placeholder: localize(form.state || {}, "workflow.copy_62"), step: "1", type: "number"});
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
function budgetLabel(word, form) {
  return Object.hasOwn(OUTPUT_LIMIT_BYTES, word)
    ? localize(form.state || {}, "workflow.budget_bytes", {word: String(word), bytes: String(OUTPUT_LIMIT_BYTES[word])})
    : localize(form.state || {}, "workflow.budget_unknown", {word: String(word)});
}

//: The select that writes it. Empty is offered beside the profiles, and it is
//: not decoration: a step that names no profile is the state every dispatch
//: step this window draws starts in, so a control that could not return one
//: there would be the one-way door `unplaceNode` exists to refuse. What it
//: costs is stated beside it rather than met at a run that will not start.
function budgetSelect(box, form, choices, named) {
  const control = element("select", {"data-edit-field": OUTPUT_LIMIT_FIELD,
    "data-focus": `edit-${OUTPUT_LIMIT_FIELD}`, name: OUTPUT_LIMIT_FIELD},
  [option("", localize(form.state || {}, "workflow.copy_63"))].concat(
    choices.map((word) => option(word, budgetLabel(word, form)))));
  control.value = choices.includes(named) ? named : "";
  control.addEventListener("change", () => commit(form, "arguments",
    withArgument(form.node, OUTPUT_LIMIT_FIELD, control.value)));
  const wrapper = field(localize(form.state || {}, "workflow.copy_64"), editable(control, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper);
}

//: What this step's output budget IS, said in bytes, and the control that sets
//: it.
//:
//: It said "not supported by this harness" until the spawn actually read the
//: profile, and then stated it read-only. Both were the release verdict's own
//: example of the shape to avoid: a field declared, validated, stored, shipped
//: in every starter, and reachable from nowhere a person could change it.
function outputBudget(box, form) {
  const {node} = form;
  const held = isObject(node.arguments) ? node.arguments : {};
  const named = held[OUTPUT_LIMIT_FIELD];
  const choices = enumChoices(node.capability, OUTPUT_LIMIT_FIELD);
  if (choices === null) {
    context(box, localize(form.state || {}, "workflow.copy_65"), localize(form.state || {}, "workflow.copy_66"),
    localize(form.state || {}, "workflow.copy_67"));
    return;
  }
  budgetSelect(box, form, choices, named);
  context(box, localize(form.state || {}, "workflow.copy_68"), choices.includes(named) ? budgetLabel(named, form)
    : localize(form.state || {}, "workflow.copy_69"),
  localize(form.state || {}, "workflow.copy_70"));
  note(box, localize(form.state || {}, "workflow.copy_71"));
}

export function executionSection(form) {
  const {node, run} = form;
  const box = sectionOf("execution", localize(form.state || {}, "workflow.copy_72"));
  context(box, localize(form.state || {}, "workflow.copy_73"), run && run.mode ? run.mode
    : localize(form.state || {}, "workflow.copy_74"), run ? localize(form.state || {}, "workflow.source_envelope", {run: String(run.runId)})
    : localize(form.state || {}, "workflow.copy_75"));
  note(box, localize(form.state || {}, "workflow.copy_76"));
  ceilingField(box, form, localize(form.state || {}, "workflow.copy_77"), "timeout_seconds");
  note(box, localize(form.state || {}, "workflow.copy_78"));
  ceilingField(box, form, localize(form.state || {}, "workflow.copy_79"), "attempt_bound");
  note(box, localize(form.state || {}, "workflow.copy_80"));
  outputBudget(box, form);
  box.append(element("h4", {text: localize(form.state || {}, "workflow.copy_81")}));
  routeAttachments(box, form);
  box.append(element("h4", {text: localize(form.state || {}, "workflow.copy_82")}));
  argumentRows(box, node, form);
  note(box, localize(form.state || {}, "workflow.copy_83"));
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
  suggestedField(box, form, localize(form.state || {}, "workflow.copy_84"), "verifier_role_id",
    node.verifier_role_id,
    localize(form.state || {}, "workflow.copy_85"), roleOffers(form));
  note(box, bound
    ? localize(form.state || {}, "workflow.copy_86")
    : localize(form.state || {}, "workflow.copy_87"));
}

//: What each word of the vocabulary ASKS FOR, said the way somebody choosing it
//: has to read it. A word the contract carries and this build has no sentence
//: for is NAMED as that rather than offered as a bare token -- `budgetLabel`'s
//: shape next door, and it is what the screen does on the day the two move
//: apart rather than showing `undefined`.
const EVIDENCE_DEMANDS = Object.freeze({
  digest: "workflow.copy_88",
});

function evidenceLabel(word, form) {
  return Object.hasOwn(EVIDENCE_DEMANDS, word) ? localize(form.state || {}, EVIDENCE_DEMANDS[word])
    : localize(form.state || {}, "workflow.evidence_unknown", {word: String(word)});
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
    context(box, localize(form.state || {}, "workflow.copy_89"), localize(form.state || {}, "workflow.copy_90"), localize(form.state || {}, "workflow.copy_91"));
    return;
  }
  selectField(box, form, localize(form.state || {}, "workflow.copy_92"), "required_evidence",
    [{value: "", label: localize(form.state || {}, "workflow.copy_93")}].concat(REQUIRED_EVIDENCE.map(
      (word) => ({value: word, label: evidenceLabel(word, form)}))),
    named);
  context(box, localize(form.state || {}, "workflow.copy_94"),
    REQUIRED_EVIDENCE.includes(named) ? evidenceLabel(named, form)
      : localize(form.state || {}, "workflow.copy_95"), localize(form.state || {}, "workflow.copy_96"));
  note(box, localize(form.state || {}, "workflow.copy_97"));
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
    context(box, localize(form.state || {}, "workflow.copy_98"), localize(form.state || {}, "workflow.copy_99"), localize(form.state || {}, "workflow.copy_100"));
    return;
  }
  selectField(box, form, localize(form.state || {}, "workflow.copy_101"), "failure_policy",
    [{value: "", label: localize(form.state || {}, "workflow.copy_102")},
      {value: "halt_run",
        label: localize(form.state || {}, "workflow.copy_103")}],
    named);
  context(box, localize(form.state || {}, "workflow.copy_104"),
    named === "halt_run"
      ? localize(form.state || {}, "workflow.copy_105")
      : localize(form.state || {}, "workflow.copy_106"),
    localize(form.state || {}, "workflow.copy_107"));
  note(box, localize(form.state || {}, "workflow.copy_108"));
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
    context(box, localize(form.state || {}, "workflow.copy_109"), localize(form.state || {}, "workflow.copy_110"), localize(form.state || {}, "workflow.source_run", {run: String(run.runId)}));
    return;
  }
  const demanded = run.planned.required_evidence;
  context(box, localize(form.state || {}, "workflow.copy_111"),
    typeof demanded === "string" && demanded !== ""
      ? evidenceLabel(demanded, form)
      : localize(form.state || {}, "workflow.copy_112"),
    localize(form.state || {}, "workflow.source_plan", {run: String(run.runId)}));
  // The POLICY the open run froze, read off the same document and never off
  // the draft: a run materialized before this field was edited follows the
  // plan it was given, and that difference is what somebody looking at both
  // needs told.
  context(box, localize(form.state || {}, "workflow.copy_113"),
    run.planned.failure_policy === "halt_run"
      ? localize(form.state || {}, "workflow.copy_114")
      : localize(form.state || {}, "workflow.copy_115"),
    localize(form.state || {}, "workflow.source_plan", {run: String(run.runId)}));
}

//: What counts as success for this step, READ rather than set.
//:
//: There is no editable field here and there never was: success for a step is
//: already decided by rules this build enforces, so the honest control is no
//: control at all. Each clause arrives from the server with the layer that
//: enforces it, and this function prints the pair. It composes no sentence,
//: because a sentence composed here would be a second opinion about somebody
//: else's rule -- right until that rule moved.
function successCriteria(box, form) {
  const rows = Array.isArray(form.criteria) ? form.criteria : [];
  if (!rows.length) {
    context(box, localize(form.state || {}, "workflow.copy_116"),
      localize(form.state || {}, "workflow.copy_117"), localize(form.state || {}, "workflow.copy_118"));
    return;
  }
  for (const row of rows) {
    if (!row || typeof row.text !== "string") continue;
    context(box, localize(form.state || {}, "workflow.copy_119"), row.text,
      typeof row.source === "string" ? row.source : localize(form.state || {}, "workflow.copy_120"));
  }
}

export function verificationSection(form) {
  const {run} = form;
  const box = sectionOf("verification", localize(form.state || {}, "workflow.copy_121"));
  verifierControl(box, form);
  evidenceRequirement(box, form);
  successCriteria(box, form);
  failurePolicy(box, form);
  runEvidenceRow(box, form);
  note(box, localize(form.state || {}, "workflow.copy_122"));
  if (run && run.position) {
    context(box, localize(form.state || {}, "workflow.copy_123"), run.position.outcome === null
      || run.position.outcome === undefined
      ? localize(form.state || {}, "workflow.copy_124")
      : String(run.position.outcome), localize(form.state || {}, "workflow.source_records", {run: String(run.runId)}));
    context(box, localize(form.state || {}, "workflow.copy_125"), String(run.position.phase),
      localize(form.state || {}, "workflow.source_projection", {run: String(run.runId)}));
  }
  return box;
}

// -- the step's own actions ------------------------------------------------

export function stepActions(form) {
  const box = panelOf("actions", localize(form.state || {}, "workflow.copy_126"));
  const at = form.nodes.findIndex((row) => row.node_id === form.node.node_id);
  actionButton(box, form, localize(form.state || {}, "workflow.copy_127"), "earlier",
    {type: "reorder", nodeId: form.node.node_id, index: at - 1});
  actionButton(box, form, localize(form.state || {}, "workflow.copy_128"), "later",
    {type: "reorder", nodeId: form.node.node_id, index: at + 1});
  actionButton(box, form, localize(form.state || {}, "workflow.copy_129"), "duplicate",
    {type: "duplicate", nodeId: form.node.node_id});
  actionButton(box, form, localize(form.state || {}, "workflow.copy_130"), "delete",
    {type: "delete-node", nodeId: form.node.node_id});
  note(box, localize(form.state || {}, "workflow.copy_131"));
  return box;
}
