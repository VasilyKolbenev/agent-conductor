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
import {localize} from "./studio-i18n.js";
import {CONTROL_MODES} from "./studio-model.js";

//: What each authority word PERMITS, in the user's own language. Read off the
//: closed `CONTROL_MODES` vocabulary; a mode with no sentence here is named and
//: left unexplained rather than described by a guess.
export const MODE_MEANINGS = Object.freeze({
  observe: "Nothing is proposed and nothing runs. The run watches.",
  propose: "Steps may be proposed, and nothing can confirm one here. Nothing "
    + "is carried out.",
  confirm: "Every effecting step waits for a person before it is carried out.",
  policy: "Bounded automatic work requires a separate human preview and permission. "
    + "Opening the run grants no execution permission.",
});
const NOT_STATED = "not stated";
const ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}";

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

function show(state, value) {
  if (value === null || value === undefined || value === "") return localize(state, "runform.not_stated");
  if (Array.isArray(value)) return value.length ? value.join(", ") : localize(state, "runform.not_stated");
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

//: Text commits on input without rendering, so an in-flight open reply can
//: distinguish the next draft even before blur. The focus net carries its
//: caret; state owns the text. Missing edit doors shut every field.
function wireTheEdits(state, edit, controls) {
  const {runId, cycleId, mode, meaning, pickers, models} = controls;
  const typed = [runId, cycleId, mode, ...pickers.values(), ...models.values()];
  if (edit === null) {
    for (const control of typed) {
      control.disabled = true;
      control.title = localize(state, "runform.m1");
    }
    return;
  }
  runId.addEventListener("input", () => edit({runId: runId.value}));
  cycleId.addEventListener("input", () => edit({cycleId: cycleId.value}));
  mode.addEventListener("change", () => {
    meaning.textContent = localize(state, `runform.mode_${mode.value}`)
      || localize(state, "runform.m2");
    edit({mode: mode.value});
  });
  for (const pick of pickers.values()) {
    pick.addEventListener("change", () => edit({roles: Object.fromEntries(
      [...pickers].map(([role, each]) => [role, each.value]))}));
  }
  for (const model of models.values()) {
    model.addEventListener("input", () => edit({models: Object.fromEntries(
      [...models].map(([role, each]) => [role, each.value]))}));
  }
}

//: The roles of the revision a run would follow. They come from the PUBLISHED
//: document and never from the drawing: a run materializes a revision, so a
//: role only this window has drawn is a role no run could bind.
export function runForm(state, handlers) {
  const detail = object(state.workflows.detail);
  const published = detail === null ? null : object(detail.published);
  const box = element("form", {className: "studio-card studio-runform"});
  box.append(element("h3", {text: localize(state, "runform.m3")}));
  const chosenTask = state.tasks?.list.find((row) => row.task_id === state.tasks.selectedId);
  const taskReady = state.tasks?.phase === "ready" && chosenTask && !chosenTask.unreadable;
  if (published === null) {
    box.append(note(localize(state, "runform.m4")));
    return box;
  }
  //: What this form already holds, from the reducer's own copy
  //: (`studio-toolbardraft.js`), and the door every committed change goes back
  //: through. Drawn from nothing, the fields emptied on every frame.
  const opening = object(state.workflows.opening) || {};
  const edit = handlerOf(handlers, "editOpening");
  const runId = element("input", {autocomplete: "off", "data-focus": "run-id",
    "data-focus-value": "state",
    maxlength: "128", name: "run-id", pattern: ID_PATTERN, required: "",
    spellcheck: "false", type: "text"});
  runId.value = typeof opening.runId === "string" ? opening.runId : "";
  const cycleId = element("input", {autocomplete: "off",
    "data-focus-value": "state",
    "data-focus": "cycle-id", maxlength: "128", name: "cycle-id",
    pattern: ID_PATTERN, required: "", spellcheck: "false", type: "text"});
  cycleId.value = typeof opening.cycleId === "string" ? opening.cycleId : "";
  const mode = element("select", {"data-focus": "run-mode", name: "run-mode"},
    CONTROL_MODES.map((word) => option(word, localize(state, `runform.label_${word}`))));
  // The most restrictive mode that still lets a person proceed is what is
  // first offered: authority is granted deliberately, never inherited from a
  // default -- and once chosen it is kept, like every other typed fact here.
  mode.value = CONTROL_MODES.includes(opening.mode) ? opening.mode : "observe";
  if (published.execution_contract === "bounded-run-v1") {
    for (const choice of mode.options) choice.disabled = choice.value !== "policy";
    mode.value = "policy";
  }
  const meaning = element("p", {className: "studio-hint",
    text: localize(state, `runform.mode_${mode.value}`)});
  box.append(field(localize(state, "runform.m5"), runId), field(localize(state, "runform.m6"), cycleId),
    field(localize(state, "runform.m7"), mode), meaning);
  const roles = roleNames(published);
  const pickers = new Map();
  const models = new Map();
  const available = reachable(state);
  const bound = object(opening.roles) || {};
  const pinned = object(opening.models) || {};
  for (const role of roles) {
    const pick = element("select", {"data-focus": `role-${role}`,
      name: `role-${role}`}, [option("", localize(state, "runform.m8"))].concat(
      available.map((row) => option(row.provider_id,
        `${row.display_name} (${row.provider_id})`))));
    pick.value = typeof bound[role] === "string" ? bound[role] : "";
    pickers.set(role, pick);
    const model = element("input", {autocomplete: "off",
      "data-focus-value": "state",
      "data-focus": `model-${role}`, maxlength: "128", name: `model-${role}`,
      pattern: ID_PATTERN, placeholder: localize(state, "runform.m9"),
      spellcheck: "false", type: "text"});
    model.disabled = !pick.value;
    model.value = pick.value && typeof pinned[role] === "string" ? pinned[role] : "";
    model.title = localize(state, "runform.m10");
    models.set(role, model);
    box.append(field(localize(state, "runform.m16", {role: String(role)}), pick), field(localize(state, "runform.m17", {role: String(role)}), model));
  }
  wireTheEdits(state, edit, {runId, cycleId, mode, meaning, pickers, models});
  if (!roles.length) {
    box.append(note(localize(state, "runform.m18", {revision: show(state, published.revision)})));
  }
  if (!available.length) {
    box.append(note(localize(state, "runform.m11")));
  }
  box.append(note(localize(state, "runform.m12")));
  const open = handlerOf(handlers, "onOpenRun");
  const go = element("button", {className: "studio-btn",
    "data-focus": "action:onOpenRun", text: localize(state, "runform.m13"), type: "submit"});
  if (open === null) {
    go.disabled = true;
    go.title = localize(state, "runform.m14");
  }
  if (!taskReady) {
    go.disabled = true;
    go.title = localize(state, "runform.m15");
  }
  box.append(go);
  box.addEventListener("submit", (event) => {
    event.preventDefault();
    if (open === null || !taskReady || !box.reportValidity()) return;
    const participants = [];
    const assignments = {};
    for (const [role, pick] of pickers) {
      if (!pick.value) continue;
      const instanceId = `instance-${role}`;
      participants.push({instance_id: instanceId, provider_id: pick.value,
        model: models.get(role).value.trim() || null});
      assignments[role] = instanceId;
    }
    open({runId: runId.value.trim(), cycleId: cycleId.value.trim(),
      mode: mode.value, participants, assignments,
      revision: published.revision});
  });
  return box;
}
