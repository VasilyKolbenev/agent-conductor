"use strict";
// Step 4 as the model sees it: the roles of the chosen cycle, who is given each, what each
// dispatch step is told, and the binding that goes with the flow for diagnostics.
//
// The pure functions of `desk-wizard-roles.js` know nothing of the wizard's state; these read the
// slices they need from it (the held flow, the roster, the quotas, the last run, the owner's own
// picks) and hand back values or the next state. It imports the shared base and the step modules,
// never the model, so the model can import it.
import {BUILT_STEPS, LIMITS, evolve, inputChars, isLanguage, taskText, utf8Bytes}
  from "./desk-wizard-base.js";
import {factsOf} from "./desk-wizard-cycle.js";
import {BINDING_CODES, argvFit, assignmentFrom, fieldsOf, offersFor, previousRun, quotaOf,
  rolesOf, rosterOf, suggest} from "./desk-wizard-roles.js";

export function heldFlow(state) {
  const {choice, flow, flowFor} = state.cycle;
  return choice !== null && flow !== null && flowFor === choice.workflowId ? flow : null;
}

function providersOf(state) {
  const read = state.reads.workflows;
  return read && read.status === "ok" ? read.payload?.providers ?? [] : [];
}

//: Whether any harness is offered at all: with none, the step says so and cannot be left.
export function hasProviders(state) {
  return rosterOf(providersOf(state)).length > 0;
}

function quotasOf(state) {
  const read = state.reads.quotas;
  return read && read.status === "ok" ? read.payload : null;
}

function charsByRole(state) {
  const flow = heldFlow(state), chars = {};
  if (flow === null) return chars;
  const inputs = inputChars(state);
  for (const field of fieldsOf(flow.flow, state.roles.instructions, taskText(state, "ru"), false)) {
    chars[field.role_id] = Math.max(chars[field.role_id] ?? 0, field.text.length + inputs);
  }
  return chars;
}

//: The last run of this cycle as role to harness, or null while it is unread or unreadable.
export function previousAssignment(state) {
  const choice = state.cycle.choice;
  const row = choice === null ? null : previousRun(state.reads.runs, choice.workflowId);
  if (row === null) return null;
  const run = state.history.runs[row.run_id];
  const revision = state.history.revisions[`${row.workflow_id}@${row.revision}`];
  if (!run || !revision) return null;
  return assignmentFrom(revision.document?.nodes, run.graph?.definition?.nodes,
    run.config?.instances);
}

//: One row per role: who has it and why (the owner, the last run, a suggestion, or nobody),
//: and every harness the role may be given, each with what is left of its limit or that it is
//: not known.
export function assignmentView(state) {
  const flow = heldFlow(state);
  if (flow === null) return [];
  const roles = rolesOf(flow.flow), providers = providersOf(state), quotas = quotasOf(state);
  const previous = previousAssignment(state), roster = rosterOf(providers);
  const found = suggest(roles, providers, quotas, previous ?? {}, {fixed: state.roles.owner,
    chars: charsByRole(state), hasPrevious: previous !== null});
  return roles.map((role) => ({...role, provider: found.assignment[role.role_id],
    by: found.by[role.role_id], notes: found.notes[role.role_id],
    offers: offersFor(role, roster).map((row) => ({id: row.id, name: row.name,
      channel: row.channel, quota: quotaOf(quotas, row.id)}))}));
}

//: The harness for each assigned role, and only those.
export function assignedTo(state) {
  const rows = assignmentView(state).filter((row) => row.provider !== null);
  return rows.length === 0 ? null
    : Object.fromEntries(rows.map((row) => [row.role_id, row.provider]));
}

//: What is sent with the flow for diagnostics once the owner has reached the roles step, and
//: still after they step back: the roles they see are the roles the server judges.
export function bindingNow(state) {
  const reached = state.cycle.boundKey !== "null"
    || BUILT_STEPS.indexOf(state.step) >= BUILT_STEPS.indexOf("roles");
  return reached && state.cycle.choice !== null ? assignedTo(state) : null;
}

//: A change of the binding is a new generation of the flow write, so its answer is told apart
//: from the last and the step waits for it (`fresh`).
export function syncBinding(state) {
  const key = JSON.stringify(bindingNow(state));
  if (state.cycle.choice === null || state.cycle.boundKey === key) return state;
  return evolve(state, {cycle: {...state.cycle, boundKey: key,
    generation: state.cycle.generation + 1}});
}

export function instructionFields(state, lang) {
  const flow = heldFlow(state);
  if (flow === null) return [];
  const owned = !state.cycle.choice.workflowId.startsWith("desk-");
  const given = assignedTo(state) ?? {};
  const roster = rosterOf(providersOf(state));
  const argvFor = (field) => {
    const row = roster.find((one) => one.id === given[field.role_id]);
    return row?.channel === "argv" && field.source !== "like"
      ? argvFit(field.text, inputChars(state)) : null;
  };
  return fieldsOf(flow.flow, state.roles.instructions, taskText(state, lang), owned)
    .map((field) => ({...field, argv: argvFor(field)}));
}

export function rolesGate(state) {
  if (rosterOf(providersOf(state)).length === 0) return "no_providers";
  if (assignmentView(state).some((row) => row.provider === null)) return "roles_unassigned";
  const fields = instructionFields(state, "ru");
  const own = fields.filter((one) => one.source !== "like");
  if (own.some((one) => one.text.trim() === "")) return "instruction_empty";
  if (own.some((one) => utf8Bytes(one.text) > LIMITS.documentBytes)) return "instruction_too_large";
  if (fields.some((one) => one.argv !== null && !one.argv.fits)) return "instruction_argv_over";
  if (state.cycle.status !== "idle") return `flow_${state.cycle.status}`;
  const facts = factsOf(state.cycle);
  if (!facts.fresh) return "binding_pending";
  return facts.diagnostics.some((row) => BINDING_CODES.includes(row.code)) ? "binding_rows" : null;
}

export function rolesPublication(state, lang) {
  const fields = instructionFields(state, lang);
  const documents = fields.filter((field) => field.source !== "like").map((field) => ({link: 5,
    target: "artifacts", ref: `instruction-${field.step_id}`, media_type: "text/markdown",
    content: field.text}));
  const likes = Object.fromEntries(fields.filter((field) => field.source === "like")
    .map((field) => [field.step_id, field.like]));
  const shared = Object.keys(likes).length === 0 ? []
    : [{link: 3, target: "flow", instruction_from: likes}];
  return {step: "roles", writes: [...documents, ...shared,
    {link: 4, target: "runs", assignments: assignedTo(state) ?? {}}]};
}

// -- the last run of the chosen cycle ----------------------------------------------------

//: The run itself and the revision it followed, whose nodes name the roles (spec 7.10).
export function historyAsks(state) {
  const choice = state.cycle.choice;
  if (choice === null || BUILT_STEPS.indexOf(state.step) < BUILT_STEPS.indexOf("cycle")) return [];
  const row = previousRun(state.reads.runs, choice.workflowId);
  if (row === null) return [];
  return [{id: `read:run:${row.run_id}`, name: "previous_run", door: "read", target: "run",
    subject: row.run_id, body: null},
  {id: `read:revision:${row.workflow_id}:${row.revision}`, name: "previous_revision",
    door: "read", target: "revision", subject: row.workflow_id, body: {revision: row.revision}}];
}

//: The last run and the revision it followed, kept by what they are about, or `null` when the
//: read failed: the roles step then says it does not know, and suggests instead.
export function answerHistory(kind) {
  return (state, ask, result) => {
    const key = kind === "runs" ? ask.subject : `${ask.subject}@${ask.body.revision}`;
    const value = result.status === "accepted" ? structuredClone(result.payload ?? null) : null;
    return evolve(state, {history: {...state.history,
      [kind]: {...state.history[kind], [key]: value}}});
  };
}

// -- events on roles and instructions ----------------------------------------------------

export function assignRole(state, event) {
  const row = assignmentView(state).find((one) => one.role_id === event.role_id);
  if (!row) return state;
  const owner = {...state.roles.owner};
  if (event.provider_id === null) {
    if (!Object.hasOwn(owner, event.role_id)) return state;
    delete owner[event.role_id];
  } else if (owner[event.role_id] === event.provider_id
      || !row.offers.some((offer) => offer.id === event.provider_id)) {
    return state;
  } else owner[event.role_id] = event.provider_id;
  return evolve(state, {roles: {...state.roles, owner}});
}

function fieldFor(state, stepId) {
  return instructionFields(state, "ru").find((field) => field.step_id === stepId);
}

function setEntry(state, stepId, entry) {
  return evolve(state, {roles: {...state.roles,
    instructions: {...state.roles.instructions, [stepId]: entry}}});
}

export function editInstruction(state, event) {
  const field = fieldFor(state, event.step_id);
  if (!field || field.source !== "own" || typeof event.text !== "string"
      || event.text === field.text) return state;
  return setEntry(state, event.step_id, {source: "own", like: null, text: event.text});
}

//: "Write apart": the instruction becomes the owner's, starting from the text it showed.
export function ownInstruction(state, event) {
  const field = fieldFor(state, event.step_id);
  if (!field || field.source === "own" || !isLanguage(event.lang)) return state;
  const kept = state.roles.instructions[event.step_id]?.text ?? "";
  const text = field.source === "task" ? taskText(state, event.lang) : kept;
  return setEntry(state, event.step_id, {source: "own", like: null, text});
}

//: "As step X", or back from it: only to a step the field offers, and back to what it was.
export function likeInstruction(state, event) {
  const field = fieldFor(state, event.step_id);
  if (!field) return state;
  const held = state.roles.instructions[event.step_id];
  if (event.like === null) {
    if (field.source !== "like") return state;
    return setEntry(state, event.step_id, held?.back === "task"
      ? {source: "task", like: null, text: ""}
      : {source: "own", like: null, text: held?.text ?? ""});
  }
  if (!field.likeChoices.includes(event.like) || field.like === event.like) return state;
  const back = field.source === "like" ? held?.back ?? "own" : field.source;
  const text = field.source === "own" ? field.text : held?.text ?? "";
  return setEntry(state, event.step_id, {source: "like", like: event.like, text, back});
}
