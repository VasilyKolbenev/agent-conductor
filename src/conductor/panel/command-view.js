"use strict";
// Every Cockpit node is built from text: no markup string is ever parsed here.
import {CAPABILITY_FIELDS, baseKind} from "./command-projection.js";

export function element(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (name === "className") node.className = value;
    else if (name === "text") node.textContent = value;
    else if (value === null) continue;
    else node.setAttribute(name, value);
  }
  node.append(...children);
  return node;
}
export function field(label, control) {
  return element("label", {className: "command-field"}, [
    element("span", {text: label}), control,
  ]);
}
function option(value) { return element("option", {text: value, value}); }
export function gateLabel(value) {
  return {
    changes_requested: "■ changes requested",
    failed: "✕ rejected",
    satisfied: "✓ approved",
    waived: "◇ waived",
  }[value] || "✕ corrupt";
}
export function gateRow(gateState, text) {
  return element("li", {className: "command-gate",
    "data-gate-state": gateState, text});
}
// `kind` arrives already normalized by `fillArguments`: whether an id refers to
// a durable artifact changes nothing about the control that collects it, so
// this function never sees the `artifact-` prefix and cannot grow a branch on
// one.
function argumentControl(draft, name, kind, choices) {
  const saved = (draft.arguments[draft.capability] || {})[name];
  if (kind === "enum") {
    const control = element(
      "select", {name: `argument:${name}`}, choices.map(option));
    if (choices.includes(saved)) control.value = saved;
    return control;
  }
  if (kind === "enum-list") {
    const control = element("select", {
      multiple: "", name: `argument:${name}`, size: String(choices.length),
    }, choices.map(option));
    for (const row of control.options) {
      row.selected = Array.isArray(saved) && saved.includes(row.value);
    }
    return control;
  }
  const control = element("input", {
    autocomplete: "off", name: `argument:${name}`,
    placeholder: kind.startsWith("ids") ? "id-1, id-2" : "stable-id",
    required: kind === "ids" ? null : "", spellcheck: "false", type: "text",
  });
  control.value = Array.isArray(saved) ? saved.join(", ") : saved || "";
  return control;
}
function fillArguments(argumentFields, draft) {
  argumentFields.replaceChildren(element("legend", {
    text: "Closed capability arguments",
  }));
  for (const [name, declared, choices = []] of CAPABILITY_FIELDS[draft.capability]) {
    argumentFields.append(field(name, argumentControl(
      draft, name, baseKind(declared), choices)));
  }
}
function proposalInput(draft, name, fallback, type = "text") {
  const key = {
    attempt_id: "attemptId", proposed_by: "proposedBy",
    timeout_seconds: "timeout",
  }[name] || name;
  if (!draft[key]) draft[key] = fallback;
  const control = element("input", {
    autocomplete: "off", name, required: "", spellcheck: "false", type,
    value: draft[key],
  });
  control.addEventListener("input", () => { draft[key] = control.value; });
  return control;
}
//: The phases in which a person may still work the controls. A BACKGROUND
//: refresh is on this list and that is the whole of a measured defect: it is
//: not the person's action, it re-reads facts the form under their hands does
//: not depend on, and disabling a form blurs whatever is focused in it. So a
//: signal arriving while somebody typed took the keyboard away from them --
//: for the length of an authoritative read, which under load is long enough to
//: swallow keystrokes and to throw a screen reader to the top of the document.
//:
//: `stale` and `refused` are NOT on it: the connection is down or the read
//: failed, and nothing may be written on either. `loading` is not, because an
//: explicit load is the person's own request for different facts. What still
//: guards a write during a background read is what always did -- the frozen
//: `preview_digest` the server compares, and the submitting arm below.
const WORKABLE_PHASES = Object.freeze(["ready", "refreshing"]);

//: Whether a person may work these controls at all. The LINE first, because a
//: phase is what the last read did and a read that starts after the stream
//: drops overwrites `stale` with `refreshing` -- which, once a background
//: refresh stopped disabling the forms, re-opened the write door on a dead
//: connection. Measured: dispatch a disconnect while a refresh is queued
//: behind it, and the confirm control came back enabled.
function workable(state) {
  return state.connected !== false && WORKABLE_PHASES.includes(state.phase);
}

//: WHERE a person is working, answered BEFORE the form is replaced: which
//: control by name, and where their caret stands inside it. The node itself is
//: about to stop existing, so nothing about it can be read afterwards.
//:
//: The caret is not a refinement of the focus, it is the other half of the same
//: fact. Giving somebody the field back with the caret at the END moves them
//: mid-word: the owner's own acceptance walk has them typing an actor name and
//: a reason, and a signal landing while they correct a letter would silently
//: append the rest of the word to the end of the value.
//:
//: A form nobody was working in answers null, and no focus is taken from
//: wherever it really is.
function focusedPlace(mount) {
  const active = document.activeElement;
  if (!mount.contains(active) || active === mount) return null;
  return {
    name: active.getAttribute("name") || active.id || null,
    caret: caretOf(active),
  };
}

//: A control's selection, or null for one that carries none.
//:
//: MEASURED in the browser this ships against, because the guard depends on
//: which half of the pair misbehaves. READING `selectionStart` does not throw:
//: a `number` input answers null and a `<select>` answers undefined. WRITING
//: does -- `setSelectionRange` raises `InvalidStateError` on the number input
//: and `TypeError` on the select, and it would raise inside a render, leaving
//: the form half-built and the person with far less than a caret.
//:
//: So the type test is the whole guard and it is on the READ, where the answer
//: is already honest. A `try` around either call would be a guard nothing in
//: this panel can make fail -- the composer's `timeout_seconds` and its two
//: selects are the only controls of those kinds, and both are covered by this
//: one line. An earlier version wrapped both and survived its own mutation for
//: exactly that reason.
function caretOf(control) {
  return typeof control.selectionStart === "number"
    ? {start: control.selectionStart, end: control.selectionEnd} : null;
}

//: Give the place back, to the control of that name in the rebuilt form.
//: Silent when the name is gone -- a field that no longer exists cannot be
//: refocused, and guessing a neighbour would put a person somewhere they never
//: chose. A caret is written only where one was read, which by `caretOf` above
//: means a control whose type really carries one.
function restoreFocus(form, place) {
  if (!place || !place.name) return;
  const control = form.querySelector(
    `[name="${place.name}"], #${place.name}`);
  if (!control || control.disabled) return;
  control.focus();
  if (place.caret) {
    control.setSelectionRange(place.caret.start, place.caret.end);
  }
}

export function renderComposer(composer, proposalStatus, state, draft, onSubmit) {
  // Asked before the replacement, for `focusedName`'s reason.
  const keepFocus = focusedPlace(composer);
  composer.replaceChildren();
  proposalStatus.textContent = state.proposalNotice;
  proposalStatus.dataset.proposalState = state.proposalPhase;
  if (!state.controls.length) return;
  const instances = state.controls.map((row) => row.instanceId);
  if (!instances.includes(draft.instanceId)) draft.instanceId = instances[0];
  const selected = state.controls.find((row) => row.instanceId === draft.instanceId);
  if (!selected.names.includes(draft.capability)) draft.capability = selected.names[0];
  const proposalForm = element("form", {className: "command-proposal-form"});
  const instance = element("select", {name: "instance_id"}, instances.map(option));
  instance.value = draft.instanceId;
  const capability = element(
    "select", {name: "capability"}, selected.names.map(option));
  capability.value = draft.capability;
  const argumentFields = element("fieldset", {className: "command-arguments"}, [
    element("legend", {text: "Closed capability arguments"}),
  ]);
  instance.addEventListener("change", () => {
    draft.instanceId = instance.value;
    const row = state.controls.find((item) => item.instanceId === draft.instanceId);
    capability.replaceChildren(...row.names.map(option));
    draft.capability = row.names[0];
    fillArguments(argumentFields, draft);
  });
  capability.addEventListener("change", () => {
    draft.capability = capability.value;
    fillArguments(argumentFields, draft);
  });
  fillArguments(argumentFields, draft);
  proposalForm.append(
    element("h3", {id: "commandComposerTitle", text: "Create proposal"}),
    field("Instance", instance), field("Capability", capability),
    field("Attempt id", proposalInput(draft, "attempt_id", "attempt-001")),
    field("Project scope", proposalInput(draft, "scope", "src, tests")),
    field("Proposed by", proposalInput(draft, "proposed_by", "operator")),
    field("Rationale", proposalInput(draft, "rationale", "Describe the reviewed work.")),
    field("Timeout seconds", proposalInput(draft, "timeout_seconds", "900", "number")),
    argumentFields,
    element("button", {text: "Create proposal", type: "submit"}),
  );
  proposalForm.addEventListener("submit", onSubmit);
  composer.append(proposalForm);
  const disabled = !workable(state)
    || ["submitting", "outcome-unknown"].includes(state.proposalPhase);
  for (const control of proposalForm.elements) control.disabled = disabled;
  restoreFocus(proposalForm, keepFocus);
}
export function renderProposalReview(review, proposal) {
  review.replaceChildren();
  if (!proposal) return;
  review.append(element("h3", {
    id: "commandReviewTitle", text: "Proposal created — review only",
  }));
  for (const [label, value] of Object.entries(proposal.facts)) {
    review.append(element("p", {className: "command-review-fact"}, [
      element("strong", {text: label}), element("span", {text: value}),
    ]));
  }
}
export const CONFIRM_NOTE = "This sends only the frozen snapshot above plus the "
  + "name you type. Acceptance records one authorized request; nothing is executed.";
export function renderConfirm(confirm, confirmStatus, state, draft, onConfirm) {
  // Focus intent outlives the disabled in-flight render, so a keyboard Human is
  // never dropped to the top of the document by their own confirmation.
  // The place is read before the replacement and kept on the draft, because a
  // render that leaves the form disabled has to hand it to the NEXT one -- the
  // same reason the typed value has lived there since this form existed.
  const place = focusedPlace(confirm);
  if (place) draft.confirmPlace = place;
  const keepFocus = place !== null || draft.confirmFocus;
  confirm.replaceChildren();
  confirmStatus.textContent = state.confirmNotice;
  confirmStatus.dataset.confirmState = state.confirmPhase;
  if (!state.proposal) return;
  // The escaped hyphen is load-bearing: a browser compiles `pattern` with the
  // RegExp `v` flag first, where a bare trailing `-` in a class is a syntax
  // error — and a pattern that fails to compile is IGNORED, not enforced.
  const actor = element("input", {
    "aria-describedby": "commandConfirmNote", autocomplete: "off",
    id: "commandConfirmedBy", maxlength: "128", name: "confirmed_by",
    pattern: "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}", required: "",
    spellcheck: "false", type: "text", value: draft.confirmedBy,
  });
  draft.confirmFocus = keepFocus;
  actor.addEventListener("blur", () => { draft.confirmFocus = false; });
  actor.addEventListener("input", () => { draft.confirmedBy = actor.value; });
  const form = element("form", {className: "command-confirm-form"}, [
    element("h3", {id: "commandConfirmTitle", text: "Confirm unchanged proposal"}),
    element("p", {className: "command-confirm-note", id: "commandConfirmNote",
      text: CONFIRM_NOTE}),
    field("Confirmed by", actor),
    element("button", {className: "command-confirm-submit", type: "submit",
      text: "Confirm unchanged proposal"}),
  ]);
  form.addEventListener("submit", onConfirm);
  confirm.append(form);
  for (const [label, value] of Object.entries(state.action || {})) {
    confirm.append(element("p", {className: "command-action-fact"}, [
      element("strong", {text: label}), element("span", {text: value}),
    ]));
  }
  const disabled = !workable(state)
    || ["submitting", "outcome-unknown"].includes(state.confirmPhase);
  for (const control of form.elements) control.disabled = disabled;
  if (keepFocus && !disabled) {
    restoreFocus(form, {name: "confirmed_by",
                        caret: (draft.confirmPlace || {}).caret || null});
  }
}
