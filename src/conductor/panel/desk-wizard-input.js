"use strict";
// What the preparation chain needs from the wizard's state, as plain values.
//
// The chain (`desk-wizard-prep.js`) is generic over these facts and imports nothing of the
// wizard's state: this module reads the state once, through the same functions the steps use, and
// hands the chain its task, the seed conditions, the flow write of link 3, who runs each role, and
// the documents it publishes. It keeps nothing and writes nothing. The flow write is built by the
// model (`flowWriteRequest`), which alone knows the digest of the draft that stands; this module
// only adds the shared instructions a saved cycle asks for (`instruction_from`, spec 7.2.3).
import {briefDocument} from "./desk-wizard-base.js";
import {bodyOf, instructionsRow} from "./desk-wizard-materials.js";
import {assignedTo, heldFlow, instructionFields} from "./desk-wizard-team.js";

//: The flow write with each step that shares another step's instruction saying so. Only a saved
//: cycle carries its flow in the write: a ready cycle is named by its id, and the product's own
//: cycles are never offered a shared instruction.
function withLikes(body, fields) {
  const likes = Object.fromEntries(fields.filter((field) => field.source === "like")
    .map((field) => [field.step_id, field.like]));
  if (Object.keys(likes).length === 0 || !body.source.flow) return body;
  const steps = body.source.flow.steps.map((step) => (Object.hasOwn(likes, step.step_id)
    ? {...step, instruction_from: likes[step.step_id]} : step));
  return {...body, source: {flow: {...body.source.flow, steps}}};
}

//: Where the agents get their code, from the one git read: the commit the desk showed (spec
//: 9.1.1), or none in view, where the seed is only a request (9.1.6). Any other state cannot be
//: seeded from, and says so instead of guessing a source.
function seedFacts(state) {
  const read = state.reads.git;
  const git = read && read.status === "ok" ? read.payload?.git : null;
  const row = instructionsRow(read, state.materials.includeInstructions);
  const include = row === null ? false : row.include;
  if (git?.state === "repo" && typeof git.head?.commit === "string") {
    return {blocked: null, commit: git.head.commit, include};
  }
  if (git?.state === "not_active") return {blocked: null, commit: null, include};
  return {blocked: "seed_needs_git", commit: null, include};
}

//: The instance a role runs on is named for the role, so the same assignment is always the same
//: request (the run's id is the only thing that makes a second run a second run).
function bindings(state) {
  const given = assignedTo(state) ?? {};
  const roles = Object.keys(given);
  return {participants: roles.map((role) => ({instance_id: `instance-${role}`,
    provider_id: given[role], model: null})),
  assignments: Object.fromEntries(roles.map((role) => [role, `instance-${role}`]))};
}

/**
 * The facts the chain is built from, for one language.
 *
 * @param {object} state The wizard's slice.
 * @param {string} lang The language the documents are written in.
 * @param {object|null} flowRequest The flow write that publishes the next revision, or null while
 *   no draft is known to stand.
 * @returns {object} Plain values only.
 */
export function runInput(state, lang, flowRequest) {
  const fields = instructionFields(state, lang);
  const body = flowRequest === null ? null : withLikes(flowRequest.body, fields);
  const held = heldFlow(state);
  const own = fields.filter((field) => field.source !== "like").map((field) => ({
    ref: `instruction-${field.step_id}`, content: field.text}));
  return {taskId: state.task.taskId, title: state.task.title, taskWritten: state.task.written,
    starterId: state.mode.starterId, view: state.mode.view, lang,
    workflowId: state.cycle.choice?.workflowId ?? null, dispatch: fields.length > 0,
    seed: seedFacts(state), flowBody: body, flowDoc: body?.source.flow ?? held?.flow ?? null,
    ...bindings(state),
    documents: [{ref: "artifact-brief", content: briefDocument(state, lang)}, ...own],
    materials: bodyOf(state.materials.items, lang)};
}
