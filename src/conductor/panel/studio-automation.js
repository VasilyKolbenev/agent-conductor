"use strict";
// A reviewed human permission is separate from per-action confirmation.
import {element, field} from "./command-view.js";
import {localize} from "./studio-i18n.js";
import {automationEligible} from "./studio-automation-model.js";

const note = (text) => element("p", {className: "studio-hint", text});
const word = (state, key, params) => localize(state, `automation.${key}`, params);
function button(state, key, enabled, invoke) {
  const control = element("button", {type: "button", className: "studio-btn",
    "data-focus": `automation:${key}`, text: word(state, key)});
  control.disabled = !enabled;
  control.addEventListener("click", invoke);
  return control;
}
function input(state, held, actions, key, node = null) {
  const value = node || held.draft;
  const control = element("input", {type: "text",
    "data-focus": `automation:${node?.node_id || "run"}:${key}`, "data-focus-value": "state",
    required: "", autocomplete: "off", ...(key === "actor" ? {maxlength: "4096"} : {inputmode: "numeric", pattern: "[1-9][0-9]*"})});
  control.value = value[key];
  control.disabled = held.pending || Boolean(held.request);
  control.addEventListener("input", (event) => actions.edit(key, control.value, node?.node_id || null, !event.isComposing));
  control.addEventListener("compositionend", () => actions.edit(key, control.value, node?.node_id || null));
  return field(word(state, key), control);
}
function boundsForm(state, held, actions) {
  const form = element("form", {className: "studio-automation__bounds"});
  for (const key of ["max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds"])
    form.append(input(state, held, actions, key));
  for (const row of held.draft.node_limits) {
    const node = state.runs.detail.graph.definition.nodes.find((item) => item.node_id === row.node_id);
    const group = element("fieldset", {}, [element("legend", {text: node.title || row.node_id})]);
    group.append(input(state, held, actions, "timeout_seconds", row), input(state, held, actions, "max_attempts", row));
    form.append(group);
  }
  const submit = button(state, "preview", !held.pending && !held.request && held.phase === "ready", () => {});
  submit.type = "submit"; form.append(submit);
  form.addEventListener("submit", (event) => { event.preventDefault(); if (form.reportValidity()) actions.preview(); });
  return form;
}
function participant(state, detail, id, duty) {
  const found = detail.config.instances.find((row) => row.id === id);
  if (!found) return note(word(state, "no_checker"));
  return note(word(state, duty, {instance: found.id, adapter: found.adapter,
    model: found.model || word(state, "unpinned")}));
}
function reviewedWork(state, terms) {
  const detail = state.runs.detail, box = element("section", {}, [element("h4", {text: word(state, "bounds")})]);
  for (const name of ["max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds"])
    box.append(note(`${word(state, name)}: ${terms[name]}`));
  for (const limit of terms.node_limits) {
    const node = detail.graph.definition.nodes.find((row) => row.node_id === limit.node_id);
    box.append(element("h4", {text: `${node.title || node.node_id} · ${node.node_id}`}),
      participant(state, detail, node.instance_id, "performs"),
      participant(state, detail, node.verifier_instance_id, "verifies"),
      note(`${word(state, "timeout_seconds")}: ${limit.timeout_seconds} · ${word(state, "max_attempts")}: ${limit.max_attempts}`));
    if (node.arguments?.work_item_id) box.append(note(`work/${node.arguments.work_item_id}`));
  }
  return box;
}
function boundDocument(state, binding, title) {
  const document = (state.runs.detail.records || []).find((row) => row.record_type === "artifact"
    && row.record.artifact_id === binding.artifact_id)?.record;
  const detail = element("details", {}, [element("summary", {text: title}), note(binding.content_digest)]);
  if (document) detail.append(element("pre", {text: document.content}));
  else detail.append(note(word(state, "document_missing")));
  return detail;
}
function documents(state, terms) {
  const box = element("section", {}, [element("h4", {text: word(state, "inputs")})]);
  for (const binding of terms.instruction_bindings) box.append(boundDocument(state, binding,
    word(state, "instruction", {node: binding.node_id, artifact: binding.artifact_id})));
  for (const binding of terms.initial_input_bindings) box.append(boundDocument(state, binding,
    word(state, "input", {reference: binding.artifact_ref, artifact: binding.artifact_id})));
  box.append(note(word(state, "generated")));
  return box;
}

function roads(state) {
  const definition = state.runs.detail.graph.definition;
  const box = element("section", {}, [element("h4", {text: word(state, "failure_routes")})]);
  for (const edge of definition.edges.filter((row) => row.condition)) box.append(note(
    `${edge.from_node} → ${edge.to_node} · ${localize(state, `condition.${edge.condition}`)}`));
  const loops = definition.nodes.filter((node) => node.kind === "loop");
  for (const node of loops) box.append(note(word(state, "loop", {node: node.node_id,
    bound: String(node.loop.bound), target: node.loop.back_to})));
  if (!loops.length) box.append(note(word(state, "no_loops")));
  return box;
}
function providerFacts(state, facts) {
  const box = element("section", {}, [element("h4", {text: word(state, "providers")})]);
  if (facts === null) { box.append(note(word(state, "providers_missing"))); return box; }
  for (const row of facts.providers) {
    box.append(element("h4", {text: `${row.config.provider_id} · ${row.contract.version}`}),
      note(`${word(state, "auth")}: ${word(state, `auth_${row.config.auth}`)}`),
      note(`${word(state, "executable")}: ${row.config.executable}`),
      note(`${word(state, "protocol")}: ${row.config.protocol}`));
    if (row.task_channel) box.append(note(word(state, `task_channel_${row.task_channel.channel}`,
      {limit: String(row.task_channel.limit)})));
    if (row.config.auth_home) box.append(note(`${word(state, "auth_home")}: ${row.config.auth_home}`));
    if (row.config.env_allow.length) box.append(note(`${word(state, "env_names")}: ${row.config.env_allow.join(", ")}`));
  }
  box.append(element("details", {}, [element("summary", {text: word(state, "provider_details")}),
    element("pre", {text: JSON.stringify(facts, null, 2)})]));
  return box;
}

function review(state, held, actions) {
  const preview = held.preview;
  const box = element("section", {className: "studio-automation__review", "data-automation-preview": "true"}, [
    note(word(state, "valid_until", {at: preview.valid_until})),
    reviewedWork(state, preview.terms), providerFacts(state, preview.provider_facts),
    documents(state, preview.terms), roads(state),
    note(word(state, "limit_note")), note(word(state, "stop_note")), note(word(state, "workspace")),
    element("details", {}, [element("summary", {text: word(state, "technical")}),
      element("pre", {text: JSON.stringify(preview.terms, null, 2)})]),
  ]);
  box.append(button(state, "authorize", held.phase === "ready" && Boolean(held.view?.owner_present)
    && Boolean(held.draft.actor.trim()) && !held.pending && !held.request, actions.authorize));
  return box;
}
function status(state, held, actions) {
  const view = held.view, box = element("section", {"data-automation-state": view.state}, [
    element("h4", {text: word(state, view.state)}), note(word(state, view.reason_code)),
    note(word(state, "actions_left", {spent: String(view.spent_actions), remaining: String(view.remaining_actions)})),
    note(word(state, "time_left", {spent: String(view.spent_task_seconds), remaining: String(view.remaining_task_seconds)})),
  ]);
  if (view.expires_at) box.append(note(word(state, "expires", {at: view.expires_at})));
  if (view.active_action_id) box.append(note(word(state, "current_action", {id: view.active_action_id})));
  if (view.next_node_id) box.append(note(word(state, "next_node", {id: view.next_node_id})));
  if (!view.owner_present) box.append(note(word(state, "owner_absent")));
  if (view.authorization && !["revoked", "expired", "complete"].includes(view.state)) {
    const ready = held.phase === "ready" && view.owner_present && !held.pending && !held.request && held.draft.actor.trim();
    const action = ["paused", "restart_required", "stalled"].includes(view.state) ? "resume" : "pause";
    box.append(button(state, action, ready, () => actions.control(action)),
      button(state, "revoke", ready, () => actions.control("revoke")));
  }
  return box;
}
export function mountAutomation(mount, state, held, actions) {
  if (!automationEligible(state.runs.detail) || !held.draft || held.runId !== state.runs.selectedId) return;
  const box = element("section", {className: "studio-section studio-automation", "data-automation": held.runId}, [
    element("h3", {text: word(state, "title")}), note(word(state, "explain")), input(state, held, actions, "actor"),
    button(state, "refresh", state.connection === "open" && !held.pending, actions.refresh),
  ]);
  if (["loading", "failed", "disconnected"].includes(held.phase)) box.append(note(word(state, held.phase)));
  if (held.notice) box.append(element("p", {"data-automation-notice": held.notice, text: word(state, held.notice)}));
  if (held.view) box.append(status(state, held, actions));
  if (held.request) box.append(button(state, "retry", !held.pending && state.connection === "open", actions.retry));
  else if (!held.view?.authorization || ["expired", "revoked"].includes(held.view.state)) box.append(boundsForm(state, held, actions));
  if (held.preview) box.append(review(state, held, actions));
  const deck = mount.querySelector(".studio-deck");
  if (deck) deck.after(box); else mount.append(box);
}
