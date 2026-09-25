"use strict";
import {localize, MESSAGES} from "./studio-i18n.js";
// The inspector's FIELD PRIMITIVES: the shapes every control on this screen is
// built from, and the two grammars they judge against.
//
// Split out of `studio-sections.js` when that module reached the project's line
// cap, at the seam its own header already named: that file was "the six
// sections, in one order, and the field primitives every one of them is built
// from", which is two things. The sections stayed there. What is here is the
// toolkit -- a section box, a panel box, a read-only fact, a note, an
// unsupported line, and the four controls that WRITE (text, suggested text,
// select, action button).
//
// The dependency runs one way and it now runs through three files: the frame
// knows about the sections, the sections know about these primitives, and these
// know nothing about either. A toolkit that reached back would close the ring
// the last split was drawn to avoid.
//
// The completeness rule lives with the sections that state it, but its ONE
// VOICE lives here: `unsupported` is the only place the sentence "not supported
// by this harness" is written, and `context` the only place a read-only fact is
// given its source. A second spelling of either is a second product.
import {element, field} from "./command-view.js";

//: `contract_values._ID_RE`, character for character, and the same grammar
//: `command-projection.RUN_ID` already holds on the Cockpit side.
export const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
//: `graph_definition.MAX_PURPOSE`, held equal to it by a test rather than
//: guessed: a window that let somebody type past the contract's bound would
//: send a save the server refuses, for a reason nothing on screen explains.
export const MAX_PURPOSE = 500;

export function call(handlers, name, value) {
  const handler = handlers && handlers[name];
  if (typeof handler === "function") handler(value);
}

// -- the writers -----------------------------------------------------------

export function sectionOf(name, title, state = {}) {
  return element("section", {className: "studio-section",
    "data-section": name}, [element("h3", {text: workflowLabel(state, title)})]);
}

//: Anything that is NOT one of the six. `data-section` names exactly the six
//: the design fixes, so a reader — and a browser test — can count them.
export function panelOf(name, title, state = {}) {
  return element("section", {className: "studio-panel",
    "data-panel": name}, [element("h3", {text: workflowLabel(state, title)})]);
}

//: One machine word for a label a human reads, so a test can address a row
//: without matching prose that is allowed to be rewritten.
function slug(label) {
  const original = Object.entries(MESSAGES).find(([key, row]) => key.startsWith("workflow.") && row.ru === label)?.[1].en || label;
  return original.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

//: The one shape an unsupported field takes. It NAMES the field, says this
//: harness does not support it, and gives the reason -- so a reader learns
//: what the product does not do rather than finding a gap where a control
//: should be. `data-unsupported` is the machine word beside the sentence.
export function unsupported(mount, label, reason, state = {}) {
  mount.append(element("p", {className: "studio-unsupported",
    "data-unsupported": slug(label)}, [
    element("strong", {text: workflowLabel(state, label)}),
    element("span", {text: localize(state, "workflow.unsupported", {reason: String(reason)})}),
  ]));
}

//: A fact this screen READS and cannot write, with the document it came from
//: named beside it. A value with no named source is a claim nobody can check.
export function context(mount, label, value, source, state = {}) {
  mount.append(element("p", {className: "studio-context",
    "data-context": slug(label)}, [
    element("strong", {text: workflowLabel(state, label)}),
    element("span", {className: "mono", text: `: ${value}`}),
    element("i", {className: "mono studio-context__source", text: ` (${source})`}),
  ]));
}

export function note(mount, text) {
  mount.append(element("p", {className: "studio-note", text}));
}

export function option(value, label, state = {}) {
  return element("option", {text: label === undefined ? value : workflowLabel(state, label), value});
}

//: Every control this module writes is disabled together when the document on
//: screen cannot be edited, and the reason is on screen rather than implied by
//: a grey box: a published revision is immutable, by design and forever.
export function editable(control, form) {
  if (!form.editable) control.disabled = true;
  return control;
}

export function commit(form, name, value) {
  call(form.handlers, "onEdit", {
    type: "set-field", nodeId: form.node.node_id, field: name, value});
}

//: This step's argument map with ONE key set or removed and every other key
//: carried across untouched.
//:
//: The spread is the whole point. A reviewed dispatch payload carries four
//: other fields, and an edit that rebuilt the map out of this one value would
//: delete them -- silently, into a draft that saves, surfacing later as a run
//: that cannot open. `set-field` carries one field; `arguments` IS one field,
//: so the value it carries is the whole map.
//:
//: It sits in the toolkit rather than beside any one control because two
//: sections write arguments now -- the output budget and the artifact pair --
//: and two copies of this spread would be two chances to lose a sibling. What
//: REMOVES a key is the empty string, and only that: an empty ARRAY is a real
//: and different answer, because a step that requires no input artifact
//: honestly carries `[]` and its schema admits one.
export function withArgument(node, field, chosen) {
  const held = node.arguments !== null && typeof node.arguments === "object"
    && !Array.isArray(node.arguments) ? node.arguments : {};
  const next = {...held};
  if (chosen === "") delete next[field];
  else next[field] = chosen;
  return next;
}

//: What each edited word must be, in the grammar its Python contract already
//: holds it to. A field says what is wrong beside itself and refuses to write,
//: which is the difference between a control that validates and a control that
//: posts a body for the server to reject.
const CHECKS = Object.freeze({
  title: (value) => value.trim() && !value.includes("\0") ? null
    : "workflow.copy_2",
  //: Empty is a real answer -- it means the step names no purpose -- so this
  //: judges only what a NON-empty one may be, and it judges the same three
  //: things `settled_purpose` does one layer down.
  purpose: (value) => !value.trim() || (
    value.length <= MAX_PURPOSE && !/[\0\r\n]/.test(value)) ? null
    : "workflow.invalid_purpose",
  role_id: (value) => value === "" || ID_PATTERN.test(value) ? null
    : "workflow.copy_4",
  gate_id: (value) => value === "" || ID_PATTERN.test(value) ? null
    : "workflow.copy_5",
  //: The same grammar `role_id` is held to, because it IS a role -- the one a
  //: run binds to whoever confirms this step. Empty is a real answer: it means
  //: nobody is named as the verifier of this step.
  verifier_role_id: (value) => value === "" || ID_PATTERN.test(value) ? null
    : "workflow.copy_6",
});

//: The error sits beside the control from the first render, `hidden` until it
//: has something to say, so a keyboard reader hears it through
//: `aria-describedby` without this module holding a second copy of the state.
export function textField(mount, form, label, name, value, help) {
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
    error.textContent = said ? localize(form.state || {}, said, said === "workflow.invalid_purpose" ? {max: String(MAX_PURPOSE)} : {}) : "";
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
  const wrapper = field(workflowLabel(form.state || {}, label), editable(control, form));
  wrapper.classList.add("studio-field");
  mount.append(wrapper, error);
  if (help) note(mount, help);
  return control;
}

//: A text field whose value stays FREE, with names already in this document
//: offered beside it. A datalist and never a `<select>`: what is offered is a
//: convenience, and typing a name no step carries is first-class -- which is
//: the whole point where a separate reviewer is concerned, because a picker
//: limited to names already in use would force somebody to invent a fictitious
//: step before they could name the person who checks the real one.
export function suggestedField(mount, form, label, name, value, help, offers) {
  const control = textField(mount, form, label, name, value, help);
  const listId = `studio-offers-${name}`;
  control.setAttribute("list", listId);
  mount.append(element("datalist", {id: listId},
    offers.map((offer) => option(offer))));
  return control;
}

export function selectField(mount, form, label, name, values, value) {
  const control = element("select", {"data-edit-field": name,
    "data-focus": `edit-${name}`, name}, values.map((row) => option(row.value,
      row.label, form.state || {})));
  control.value = value === null || value === undefined ? "" : String(value);
  control.addEventListener("change", () => commit(form, name,
    control.value === "" ? null : control.value));
  const wrapper = field(workflowLabel(form.state || {}, label), editable(control, form));
  wrapper.classList.add("studio-field");
  mount.append(wrapper);
  return control;
}

export function actionButton(mount, form, label, key, edit) {
  const button = element("button", {className: "studio-action",
    "data-action": key, "data-focus": `action-${key}`, type: "button"},
  [element("span", {text: workflowLabel(form.state || {}, label)})]);
  button.addEventListener("click", () => call(form.handlers, "onEdit", edit));
  mount.append(editable(button, form));
  return button;
}


// Only controlled field labels enter this lookup; user values never do.
function workflowLabel(state, label) {
  const entry = Object.entries(MESSAGES).find(([key, row]) =>
    key.startsWith("workflow.") && row.en === label);
  return entry ? localize(state, entry[0]) : label;
}
