"use strict";
// Every Cockpit node is built from text: no markup string is ever parsed here.
import {CAPABILITY_FIELDS} from "./command-projection.js";

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
  for (const [name, kind, choices = []] of CAPABILITY_FIELDS[draft.capability]) {
    argumentFields.append(field(name, argumentControl(draft, name, kind, choices)));
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
export function renderComposer(composer, proposalStatus, state, draft, onSubmit) {
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
  const disabled = state.phase !== "ready"
    || ["submitting", "outcome-unknown"].includes(state.proposalPhase);
  for (const control of proposalForm.elements) control.disabled = disabled;
}
export function renderProposalReview(review, proposal) {
  review.replaceChildren();
  if (!proposal) return;
  review.append(element("h3", {
    id: "commandReviewTitle", text: "Proposal created — review only",
  }));
  for (const [label, value] of Object.entries(proposal)) {
    review.append(element("p", {className: "command-review-fact"}, [
      element("strong", {text: label}), element("span", {text: value}),
    ]));
  }
}
