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

const REF_GRAMMAR = "An artifact reference must match "
  + "[A-Za-z0-9][A-Za-z0-9._-]{0,127}";

// -- required input artifacts ----------------------------------------------

function inputRows(box, form, held, name) {
  if (!held.length) {
    note(box, "This step requires no input artifact.");
    return;
  }
  const list = element("ul", {className: "studio-refs"});
  held.forEach((ref, at) => {
    const item = element("li", {className: "mono studio-ref", "data-ref": ref},
      [element("span", {text: ref})]);
    const drop = element("button", {"aria-label": `Stop requiring ${ref}`,
      className: "studio-ref__drop", "data-focus": `ref-drop-${at}`,
      type: "button"}, [element("span", {text: "Remove"})]);
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
  [element("span", {text: "Require it"})]);
  add.addEventListener("click", () => {
    if (!ID_PATTERN.test(input.value)) {
      call(form.handlers, "onStatus", `${REF_GRAMMAR}.`);
      return;
    }
    if (held.includes(input.value)) {
      call(form.handlers, "onStatus", "This step already requires "
        + `${input.value}. A run resolves each reference once, so asking for `
        + "one twice is refused where the resolution happens.");
      return;
    }
    commit(form, "arguments",
      withArgument(form.node, name, held.concat([input.value])));
  });
  const wrapper = field("Require an artifact", editable(input, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper, editable(add, form));
}

function requiredInputs(box, form) {
  const {node} = form;
  const found = artifactField(node.capability, INPUT_KINDS);
  if (found === null) {
    context(box, "Required input artifacts", "none — the reviewed schema for "
      + "this step's capability declares no artifact input, so there is none "
      + "to name", "the step's capability arguments");
    return;
  }
  const held = refsOf(node, found.name);
  inputRows(box, form, held, found.name);
  inputAdder(box, form, held, found.name);
  context(box, "Required input artifacts", held.length ? held.join(", ")
    : "none — this step names no input artifact",
  "the step's capability arguments, resolved before the spawn");
  note(box, "A reference is a HANDOFF NAME and not a document: a run resolves "
    + "it to the latest artifact standing under that name at the moment this "
    + "step runs. Every other argument of this step is carried across "
    + "untouched when this list changes.");
  note(box, found.kind === NON_EMPTY
    ? "This schema REQUIRES at least one, and leaving the list empty has a "
      + "plain cost: no run of this workflow can be opened at all while it is, "
      + "because the open-run route judges every step's payload against the "
      + "same reviewed schema — by the contract rather than by this window."
    : "This schema admits an EMPTY list, so requiring nothing is a real "
      + "answer: the step is then spawned with its instruction and no durable "
      + "material beside it.");
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
    "data-focus": `edit-${name}`, name, placeholder: "publishes nothing",
    spellcheck: "false", type: "text"});
  control.value = named;
  const judge = () => {
    const said = control.value === "" || ID_PATTERN.test(control.value)
      ? "" : `${REF_GRAMMAR}, or be empty.`;
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
  const wrapper = field("Produced artifact", editable(control, form));
  wrapper.classList.add("studio-field");
  box.append(wrapper, error);
}

function producedArtifacts(box, form) {
  const {node} = form;
  const found = artifactField(node.capability, OUTPUT_KINDS);
  if (found === null) {
    context(box, "Produced artifacts", "none — the reviewed schema for this "
      + "step's capability declares no result artifact reference, so a step of "
      + "this kind publishes no document of its own",
    "the step's capability arguments");
    note(box, "What it leaves instead is a CHANGE. The bound adapter digests "
      + "what this step altered under its own work directory, folds in the "
      + "identifiers of the artifacts it was given, and records that digest as "
      + "the run's verification evidence. There is nothing to name here "
      + "because no document is written.");
    return;
  }
  const named = refOf(node, found.name);
  producedControl(box, form, found.name, named);
  context(box, "Produced artifacts", named
    || "none — this step names no result artifact",
  "the step's capability arguments, published after the spawn");
  note(box, "Clearing it is allowed and it has a plain cost, met at the run "
    + "rather than here: a step of this kind that names no result artifact is "
    + "REFUSED when it is reached — nothing it produced could be published, so "
    + "no task is spawned at all and the model call is never spent.");
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
    context(box, "Handoff mapping", "none — this step requires no artifact, so "
      + "there is nothing for another step to hand it", "this workflow document");
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
        ? ` — produced by ${producers.map((row) => row.title).join(", ")}`
        : " — no step in this workflow produces it. A run is handed it on "
          + "the Runs screen, under Publish a document, before this step "
          + "can run."}),
    ]));
  }
  box.append(list);
  context(box, "Handoff mapping",
    `${met} of ${held.length} met by a step in this workflow`,
    "this workflow document");
}

// -- what a run bound to this step actually produced -------------------------

function runProducts(box, form) {
  const {run} = form;
  if (!run) return;
  const products = rows(run.products);
  const source = `the durable records of run ${run.runId}`;
  if (!products.length) {
    context(box, "Produced in this run", "none — no artifact in this run's "
      + "journal was published by an action of this step", source);
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
    products.map((row) => row.artifactRef).join(", "), source);
  note(box, "The handoff name, the identity and the media type. The CONTENT is "
    + "deliberately not here: an artifact is durable material a run hands "
    + "between roles, and this window says what exists rather than reproducing "
    + "it — the Runs screen shows the same three facts and no more.");
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
      "none — this step is given no input artifacts, so there is none to be "
      + "missing", "the workflow contract");
    return;
  }
  selectField(box, form, "Missing-artifact behaviour",
    "missing_artifact_policy",
    [{value: "", label: "fail — reach the step, then refuse it (the default)"},
      {value: "fail", label: "fail — reach the step, then refuse it"},
      {value: "block",
        label: "block — do not offer the step until the artifact exists"}],
    named);
  note(box, "Both answers are fail-closed and nothing here skips the step or "
    + "substitutes another document. With FAIL — which is also what saying "
    + "nothing means — the step is offered, reached, and refused when the "
    + "input cannot be resolved: no task is spawned and no model call is "
    + "spent, and the run carries a durable failure. With BLOCK the step is "
    + "never offered at all while the artifact is absent, so nothing is "
    + "attempted and nothing fails — the plan waits, and this screen says "
    + "which document it is waiting for.");
  runWaiting(box, run, node);
}

//: What the OPEN run is doing about it, read off the schedule the server
//: computed rather than recomputed here. Absent for a step that is not waiting,
//: because a line saying "waiting for nothing" is a line about nothing.
function runWaiting(box, run, node) {
  const standing = run && run.schedule
    ? rows(run.schedule.nodes).find((row) => row.node_id === node.node_id)
    : null;
  const waiting = standing === null || standing === undefined
    ? [] : rows(standing.awaiting_artifacts);
  if (!waiting.length) return;
  context(box, "Waiting for", waiting.join(", "),
    `the plan run ${run.runId} froze`);
  note(box, "This step is not offered until every artifact named above "
    + "exists in this run. Publish them, or answer the step that produces "
    + "them, and it becomes available.");
}

// -- 4. Inputs and outputs -------------------------------------------------

export function artifactSection(form) {
  const {run} = form;
  const box = sectionOf("artifacts", "Inputs and outputs");
  requiredInputs(box, form);
  producedArtifacts(box, form);
  box.append(element("h4", {text: "Handoff mapping"}));
  handoffMapping(box, form);
  missingArtifactPolicy(box, form, run);
  box.append(element("h4", {text: "What this run produced"}));
  runProducts(box, form);
  const refs = run && run.position ? rows(run.position.evidence_refs) : [];
  if (run && run.position) {
    context(box, "Evidence references", refs.length ? refs.join(", ") : "none",
      `the durable records of run ${run.runId}`);
    note(box, "Identifiers only. Nothing here states that any of them "
      + "verified anything.");
  }
  return box;
}
