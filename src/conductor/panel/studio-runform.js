"use strict";
// The form that OPENS A RUN, and the roles such a run has to bind.
//
// Split out of `studio-view.js` when that module reached the project's line
// cap, at the seam its toolbar already had. What stayed behind is about the
// DOCUMENT on screen -- which workflow, how to start one, the two write doors,
// what stops publishing. What is here is the one control in that toolbar that
// starts something RUNNING, and the only part of it that reads the provider
// roster at all.
//
// `reachable` came across rather than staying behind, and that is forced rather
// than chosen: the Overview's readiness card asks the same question, and a copy
// on each side of the seam would be two answers about which providers a run
// could bind. The dependency runs one way -- the shell view imports this module,
// this module knows nothing about the shell.
//
// It writes DOM and nothing else: no `fetch(`, no stream, no clock, no storage.
// The door it submits through is `handlers.onOpenRun`, which the transport
// module owns and hands in, so the button that WRITES is still built by the
// module that owns the door it writes through.
import {element, field} from "./command-view.js";
import {CONTROL_MODES} from "./studio-model.js";

//: What each authority word PERMITS, in the user's own language. Read off the
//: closed `CONTROL_MODES` vocabulary; a mode with no sentence here is named and
//: left unexplained rather than described by a guess.
export const MODE_MEANINGS = Object.freeze({
  observe: "Nothing is proposed and nothing runs. The run watches.",
  propose: "Steps may be proposed, and nothing can confirm one here. Nothing "
    + "is carried out.",
  confirm: "Every effecting step waits for a person before it is carried out.",
  policy: "Reserved: this build ships no policy executor. A policy run behaves "
    + "as a propose run: steps may be proposed and nothing is carried out.",
});
const NOT_STATED = "not stated";
const ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}";

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

function show(value) {
  if (value === null || value === undefined || value === "") return NOT_STATED;
  if (Array.isArray(value)) return value.length ? value.join(", ") : NOT_STATED;
  return String(value);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

function note(value) { return element("p", {className: "studio-hint", text: value}); }

function option(value, label) {
  return element("option", {text: label === undefined ? value : label, value});
}

//: Which providers this build resolved AND this machine can reach. Two
//: different questions and both are shown; only the first gates a run.
export function reachable(state) {
  return rows(state.providers).filter((row) => row.availability === "available");
}

//: Every role this revision names, of BOTH kinds. A step's own `role_id` says
//: who carries it out and its `verifier_role_id` says who confirms it, and
//: `GraphTemplate._roles_of` counts both -- so `RunBinding.covers` demands an
//: assignment for both and `open_run` refuses a binding that leaves either
//: unassigned. Reading only the first is what would make a revision whose
//: reviewer role no step carries out impossible to open a run of: the picker
//: would not exist, nothing would be assigned, and the refusal would arrive
//: from the server naming a role this form never offered.
function roleNames(held) {
  const found = new Set();
  for (const node of rows(held && held.nodes)) {
    if (!node) continue;
    for (const role of [node.role_id, node.verifier_role_id]) {
      if (typeof role === "string") found.add(role);
    }
  }
  return [...found].sort();
}

//: The roles of the revision a run would follow. They come from the PUBLISHED
//: document and never from the drawing: a run materializes a revision, so a
//: role only this window has drawn is a role no run could bind.
export function runForm(state, handlers) {
  const detail = object(state.workflows.detail);
  const published = detail === null ? null : object(detail.published);
  const box = element("form", {className: "studio-card"});
  box.append(element("h3", {text: "Open a run"}));
  if (published === null) {
    box.append(note("A run follows a PUBLISHED revision, and this workflow has "
      + "none yet. Publishing the draft is what makes one."));
    return box;
  }
  const runId = element("input", {autocomplete: "off", "data-focus": "run-id",
    maxlength: "128", name: "run-id", pattern: ID_PATTERN, required: "",
    spellcheck: "false", type: "text"});
  const cycleId = element("input", {autocomplete: "off",
    "data-focus": "cycle-id", maxlength: "128", name: "cycle-id",
    pattern: ID_PATTERN, required: "", spellcheck: "false", type: "text"});
  const mode = element("select", {"data-focus": "run-mode", name: "run-mode"},
    CONTROL_MODES.map((word) => option(word)));
  // The most restrictive mode that still lets a person proceed is what is
  // offered: authority is granted deliberately, never inherited from a default.
  mode.value = "observe";
  const meaning = element("p", {className: "studio-hint",
    text: MODE_MEANINGS.observe});
  mode.addEventListener("change", () => {
    meaning.textContent = MODE_MEANINGS[mode.value]
      || "This build does not describe that mode.";
  });
  box.append(field("Run id", runId), field("Cycle id", cycleId),
    field("Authority (mode)", mode), meaning);
  const roles = roleNames(published);
  const pickers = new Map();
  const available = reachable(state);
  for (const role of roles) {
    const pick = element("select", {"data-focus": `role-${role}`,
      name: `role-${role}`}, [option("", "no participant")].concat(
      available.map((row) => option(row.provider_id,
        `${row.display_name} (${row.provider_id})`))));
    pickers.set(role, pick);
    box.append(field(`Role ${role}`, pick));
  }
  if (!roles.length) {
    box.append(note("Revision " + show(published.revision) + " names no role, "
      + "so a run of it binds nobody."));
  }
  if (!available.length) {
    box.append(note("No provider on this machine is available, so no role can "
      + "be bound. The Agents screen names the file to write."));
  }
  box.append(note("A participant names one CONFIGURED provider. This window "
    + "never sends a path, an argv, a credential or an adapter binding: the "
    + "server builds the frozen configuration from the provider ids alone."));
  const open = handlerOf(handlers, "onOpenRun");
  const go = element("button", {className: "studio-btn",
    "data-focus": "action:onOpenRun", text: "Open the run", type: "submit"});
  if (open === null) {
    go.disabled = true;
    go.title = "This screen was mounted without an onOpenRun handler.";
  }
  box.append(go);
  box.addEventListener("submit", (event) => {
    event.preventDefault();
    if (open === null) return;
    const participants = [];
    const assignments = {};
    for (const [role, pick] of pickers) {
      if (!pick.value) continue;
      const instanceId = `instance-${role}`;
      participants.push({instance_id: instanceId, provider_id: pick.value,
        model: null});
      assignments[role] = instanceId;
    }
    open({runId: runId.value.trim(), cycleId: cycleId.value.trim(),
      mode: mode.value, participants, assignments,
      revision: published.revision});
  });
  return box;
}
