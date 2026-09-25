"use strict";
// The inspector's INPUTS AND OUTPUTS: what a step requires before it can run,
// what it publishes, where each requirement is met, and what a run bound to it
// actually produced.
//
// Split out of `studio-sections.js` before that module reached the project's
// line cap, at the seam its own header already named. That file is "the six
// sections, in one order", and this is the one of them that grows.
//
// THE DESIGN, because it is the thing most likely to be undone by someone
// trying to help. None of these three facts is a field on a workflow step, and
// none of them may become one. They are already durable, already validated,
// already materialized into a run's plan and already replay-guarded -- as the
// capability's own reviewed ARGUMENTS:
//
//   required inputs   `artifact_refs` / `target_artifact_refs`, resolved by
//                     `artifact_handoff.resolve` through `latest_artifacts`,
//                     and refused WITHOUT spawning when one is unavailable;
//   produced          `result_artifact_ref`, which is where a step's own output
//                     is published; the store holds the artifact to it at
//                     append and again at replay
//                     (`artifacts._artifact_answers_its_request`).
//
// So every control here is a VIEW over the reviewed schema, driven by
// `CAPABILITY_FIELDS` -- the same projection the Cockpit's proposal composer is
// built from -- and every one of them writes through `set-field` `arguments`
// with the whole map rebuilt around one key. Promoting any of it to a
// `TemplateNode` field would be a second authority over a capability payload,
// which `graph_template` forbids in four places.
//
// WHICH field is which is a LOOKUP and never a capability name. A capability is
// a word the provider roster supplies at run time; a control that named one
// would be a second, silent copy of a schema somebody else reviews, and the
// inspector's source guard bans those literals for exactly that reason.
//
// The dependency runs one way: this module reaches the toolkit and the
// projection, and neither the sections nor the frame. Two halves of one
// inspector that could import each other would close the ring the split was
// drawn to open.
import {localize} from "./studio-i18n.js";
import {element, field} from "./command-view.js";
//: The REVIEWED argument schemas, projected. Read for the `artifact-` kinds it
//: marks, which is how this section finds its two controls without naming a
//: capability to find them.
import {CAPABILITY_FIELDS} from "./command-projection.js";
import {
  ID_PATTERN,
  call,
  commit,
  context,
  editable,
  note,
  sectionOf,
  selectField,
  withArgument,
} from "./studio-fields.js";

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }

// -- which argument field carries which artifact role -----------------------

//: The kinds the reviewed projection marks a step's REQUIRED INPUTS with, and
//: the one it marks a step's OWN OUTPUT with. Two words for the inputs because
//: the two schemas differ on one real rule and this window must not flatten it:
//: a dispatching step's list may be empty, a reviewing step's may not.
const INPUT_KINDS = Object.freeze(["artifact-ids", "artifact-ids-required"]);
const OUTPUT_KINDS = Object.freeze(["artifact-id"]);
//: The one of `INPUT_KINDS` whose list the schema refuses to leave empty.
const NON_EMPTY = "artifact-ids-required";

//: Which argument field of ONE capability plays ONE artifact role, or null.
//:
//: A capability this build carries no row for, or a row that marks no field
//: with one of these kinds, answers null -- and the control then SAYS the step
//: has no such field rather than inventing one for it. That is the whole reason
//: this is a lookup: `result_artifact_ref` exists on one schema and not on the
//: other, and the difference is a real product fact -- a step that carries work
//: out publishes no document, only a digest of what it changed.
function artifactField(capability, kinds) {
  if (typeof capability !== "string"
      || !Object.hasOwn(CAPABILITY_FIELDS, capability)) return null;
  const row = CAPABILITY_FIELDS[capability].find(
    (entry) => kinds.includes(entry[1]));
  return row === undefined ? null : {name: row[0], kind: row[1]};
}

//: What this step's argument map holds under one name, read defensively: a
//: draft is allowed to be incomplete, so an absent key and a key holding
//: something that is not a list are both "no references", never an error.
function refsOf(node, name) {
  const held = isObject(node.arguments) ? node.arguments : {};
  return rows(held[name]).filter((row) => typeof row === "string");
}

function refOf(node, name) {
  const held = isObject(node.arguments) ? node.arguments : {};
  return typeof held[name] === "string" ? held[name] : "";
}


// -- required input artifacts ----------------------------------------------

function inputRows(box, form, held, name) {
  if (!held.length) {
    note(box, localize(form.state || {}, "workflow_detail.input_none"));
    return;
  }
  const list = element("ul", {className: "studio-refs"});
  held.forEach((ref, at) => {
    const item = element("li", {className: "mono studio-ref", "data-ref": ref},
      [element("span", {text: ref})]);
    const drop = element("button", {"aria-label": localize(form.state || {}, "workflow_detail.drop_ref", {ref: String(ref)}),
      className: "studio-ref__drop", "data-focus": `ref-drop-${at}`,
      type: "button"}, [element("span", {text: localize(form.state || {}, "workflow_detail.remove")})]);
    drop.addEventListener("click", () => commit(form, "arguments",
      withArgument(form.node, name,
        held.filter((_, index) => index !== at))));
    item.append(editable(drop, form));
    list.append(item);
  });
  box.append(list);
}

//: Two refusals, and each is one this window can honestly make on its own.
//:
//: The grammar is `contract_values._ID_RE`, which every reference is held to
//: wherever it is finally read. The duplicate is `latest_artifacts`' own rule:
//: it resolves through `_unique_ids`, so a list asking for one name twice is
//: refused at the spawn -- and a control that let one be typed would be writing
//: a draft that saves and a run that will not resolve.
//:
//: What this window does NOT refuse is a name no artifact stands under. It
//: cannot: which documents exist is a RUN's fact and a draft is written before
//: any run of it exists, so a control that only admitted names it could see
//: today would refuse every honest workflow that receives its first input from
//: outside. That case is stated under the handoff mapping instead.
function inputAdder(box, form, held, name) {
  //: `data-edit-field` names the argument this control really writes, the way
  //: every other writer on this screen names its field. It is the lookup's
  //: answer rather than a word written here, so a browser can hold the
  //: rendered control against the reviewed projection and catch a section that
  //: had grown its own idea of which argument carries a step's inputs.
  const input = element("input", {autocomplete: "off",
    "data-edit-field": name, "data-focus": "ref-name", name: "artifact_ref",
    spellcheck: "false", type: "text"});
  const add = element("button", {className: "studio-ref__add",
    "data-focus": "ref-add", type: "button"},
  [element("span", {text: localize(form.state || {}, "workflow_detail.require")})]);
  add.addEventListener("click", () => {
    if (!ID_PATTERN.test(input.value)) {
      call(form.handlers, "onStatus", {key: "workflow_detail.ref_grammar"});
      return;
    }
    if (held.includes(input.value)) {
      call(form.handlers, "onStatus", {key: "workflow_detail.ref_duplicate", params: {ref: String(input.value)}});
      return;
    }
    commit(form, "arguments",
      withArgument(form.node, name, held.concat([input.value])));
  });
  const wrapper = field(localize(form.state || {}, "workflow_detail.require_label"), editable(input, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper, editable(add, form));
}

function requiredInputs(box, form) {
  const {node} = form;
  const found = artifactField(node.capability, INPUT_KINDS);
  if (found === null) {
    context(box, "Required input artifacts", localize(form.state || {}, "workflow_detail.input_schema_none"), localize(form.state || {}, "workflow_detail.arguments_source"), form.state);
    return;
  }
  const held = refsOf(node, found.name);
  inputRows(box, form, held, found.name);
  inputAdder(box, form, held, found.name);
  context(box, "Required input artifacts", held.length ? held.join(", ")
    : localize(form.state || {}, "workflow_detail.input_unnamed"),
  localize(form.state || {}, "workflow_detail.input_source"), form.state);
  note(box, localize(form.state || {}, "workflow_detail.ref_note"));
  note(box, found.kind === NON_EMPTY
    ? localize(form.state || {}, "workflow_detail.input_required")
    : localize(form.state || {}, "workflow_detail.input_optional"));
}

// -- produced artifacts ------------------------------------------------------

//: The control that names where this step's own output is published. Written
//: here rather than through `textField` because what it commits is one key of
//: the argument MAP, not a field of the step -- but it is judged before it
//: writes exactly as every other control is, and it says what is wrong beside
//: itself instead of posting a body for somebody else to reject.
function producedControl(box, form, name, named) {
  const errorId = `studio-invalid-${name}`;
  const error = element("p", {className: "studio-invalid", hidden: "",
    id: errorId, role: "note"});
  const control = element("input", {"aria-describedby": errorId,
    autocomplete: "off", "data-edit-field": name,
    "data-focus": `edit-${name}`, name, placeholder: localize(form.state || {}, "workflow_detail.publishes_nothing"),
    spellcheck: "false", type: "text"});
  control.value = named;
  const judge = () => {
    const said = control.value === "" || ID_PATTERN.test(control.value)
      ? "" : localize(form.state || {}, "workflow_detail.ref_optional_grammar");
    error.textContent = said;
    error.hidden = !said;
    control.setAttribute("aria-invalid", said ? "true" : "false");
    return said;
  };
  control.addEventListener("input", judge);
  control.addEventListener("change", () => {
    if (judge()) return;
    commit(form, "arguments",
      withArgument(form.node, name, control.value));
  });
  const wrapper = field(localize(form.state || {}, "workflow_detail.produced_label"), editable(control, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper, error);
}

function producedArtifacts(box, form) {
  const {node} = form;
  const found = artifactField(node.capability, OUTPUT_KINDS);
  if (found === null) {
    context(box, "Produced artifacts", localize(form.state || {}, "workflow_detail.output_schema_none"),
    localize(form.state || {}, "workflow_detail.arguments_source"), form.state);
    note(box, localize(form.state || {}, "workflow_detail.output_changes"));
    return;
  }
  const named = refOf(node, found.name);
  producedControl(box, form, found.name, named);
  context(box, "Produced artifacts", named
    || localize(form.state || {}, "workflow_detail.output_unnamed"),
  localize(form.state || {}, "workflow_detail.output_source"), form.state);
  note(box, localize(form.state || {}, "workflow_detail.output_empty_note"));
}

// -- handoff mapping ---------------------------------------------------------

//: Every step of THIS document that publishes one reference.
//:
//: The comparison is reference against reference, and the producing FIELD is
//: looked up per node from that node's own capability -- a document may mix
//: kinds of step, and a walk that assumed one field name would silently find
//: no producer on the ones that use the other.
function producersOf(nodes, ref) {
  const found = [];
  for (const node of nodes) {
    const declared = artifactField(node.capability, OUTPUT_KINDS);
    if (declared === null) continue;
    if (refOf(node, declared.name) === ref) found.push(node);
  }
  return found;
}

//: Where each of this step's requirements is met, derived from the document on
//: screen and stored nowhere. It updates as references and producers change,
//: because it is computed on every render out of `form.nodes` -- the same way
//: `roleOffers` derives the roles this document names.
//:
//: The absent case is a real answer and it is the shipped starters' own: the
//: first step of the Dalio cycle requires `artifact-brief`, which no step
//: produces, so a run receives it from outside before that step can run.
function handoffMapping(box, form) {
  const found = artifactField(form.node.capability, INPUT_KINDS);
  const held = found === null ? [] : refsOf(form.node, found.name);
  if (!held.length) {
    context(box, "Handoff mapping", localize(form.state || {}, "workflow_detail.handoff_none"), localize(form.state || {}, "workflow_detail.workflow_source"), form.state);
    return;
  }
  const list = element("ul", {className: "studio-handoffs"});
  let met = 0;
  for (const ref of held) {
    const producers = producersOf(form.nodes, ref);
    if (producers.length) met += 1;
    list.append(element("li", {className: "studio-handoff",
      "data-handoff": ref}, [
      element("span", {className: "mono", text: ref}),
      element("span", {text: producers.length
        ? localize(form.state || {}, "workflow_detail.produced_by", {steps: producers.map((row) => row.title).join(", ")})
        : localize(form.state || {}, "workflow_detail.external_input")}),
    ]));
  }
  box.append(list);
  context(box, "Handoff mapping",
    localize(form.state || {}, "workflow_detail.handoff_count", {met: String(met), total: String(held.length)}),
    localize(form.state || {}, "workflow_detail.workflow_source"), form.state);
}

// -- what a run bound to this step actually produced -------------------------

function runProducts(box, form) {
  const {run} = form;
  if (!run) return;
  const products = rows(run.products);
  const source = localize(form.state || {}, "workflow_detail.run_source", {run: String(run.runId)});
  if (!products.length) {
    context(box, "Produced in this run", localize(form.state || {}, "workflow_detail.run_products_none"), source, form.state);
    return;
  }
  const list = element("ul", {className: "studio-artifacts"});
  for (const row of products) {
    list.append(element("li", {className: "mono studio-artifact",
      "data-artifact": row.artifactId}, [element("span", {
      text: `${row.artifactRef} · ${row.artifactId} · ${row.mediaType}`})]));
  }
  box.append(list);
  context(box, "Produced in this run",
    products.map((row) => row.artifactRef).join(", "), source, form.state);
  note(box, localize(form.state || {}, "workflow_detail.run_products_note"));
}

// -- 3b. what happens when a required input is not there --------------------

//: `graph_values.MISSING_ARTIFACT_POLICIES` -- the two fail-closed words a plan
//: may say. Held to the Python owner by a source test rather than trusted here,
//: the way every other closed vocabulary on this surface is.
export const MISSING_ARTIFACT_POLICIES = Object.freeze(["fail", "block"]);

//: The label the register carried while this had no durable home. It keeps the
//: label, so a person who read the old sentence finds the control where the
//: explanation used to be.
function missingArtifactPolicy(box, form, run) {
  const {node} = form;
  const named = typeof node.missing_artifact_policy === "string"
    ? node.missing_artifact_policy : "";
  // The pairing rule both Python contracts hold, said here in the vocabulary a
  // person drew in: a step nothing hands a document to has no input to be
  // missing, and the reason names the CAPABILITY because that is the half they
  // can change.
  if (artifactField(node.capability, INPUT_KINDS) === null) {
    context(box, "Missing-artifact behaviour",
      localize(form.state || {}, "workflow_detail.missing_inapplicable"), localize(form.state || {}, "workflow_detail.contract_source"), form.state);
    return;
  }
  selectField(box, form, "Missing-artifact behaviour",
    "missing_artifact_policy",
    [{value: "", label: localize(form.state || {}, "workflow_detail.missing_default")},
      {value: "fail", label: localize(form.state || {}, "workflow_detail.missing_fail")},
      {value: "block",
        label: localize(form.state || {}, "workflow_detail.missing_block")}],
    named);
  note(box, localize(form.state || {}, "workflow_detail.missing_note"));
  runWaiting(box, run, node, form);
}

//: What the OPEN run is doing about it, read off the schedule the server
//: computed rather than recomputed here. Absent for a step that is not waiting,
//: because a line saying "waiting for nothing" is a line about nothing.
function runWaiting(box, run, node, form) {
  const standing = run && run.schedule
    ? rows(run.schedule.nodes).find((row) => row.node_id === node.node_id)
    : null;
  const waiting = standing === null || standing === undefined
    ? [] : rows(standing.awaiting_artifacts);
  if (!waiting.length) return;
  context(box, "Waiting for", waiting.join(", "),
    localize(form.state || {}, "workflow_detail.frozen_source", {run: String(run.runId)}), form.state);
  note(box, localize(form.state || {}, "workflow_detail.waiting_note"));
}

// -- 4. Inputs and outputs -------------------------------------------------

export function artifactSection(form) {
  const {run} = form;
  const box = sectionOf("artifacts", "Inputs and outputs", form.state);
  requiredInputs(box, form);
  producedArtifacts(box, form);
  box.append(element("h4", {text: localize(form.state || {}, "workflow_detail.handoff_heading")}));
  handoffMapping(box, form);
  missingArtifactPolicy(box, form, run);
  box.append(element("h4", {text: localize(form.state || {}, "workflow_detail.products_heading")}));
  runProducts(box, form);
  const refs = run && run.position ? rows(run.position.evidence_refs) : [];
  if (run && run.position) {
    context(box, "Evidence references", refs.length ? refs.join(", ") : localize(form.state || {}, "workflow_detail.none"),
      localize(form.state || {}, "workflow_detail.run_source", {run: String(run.runId)}), form.state);
    note(box, localize(form.state || {}, "workflow_detail.evidence_ids_note"));
  }
  return box;
}
