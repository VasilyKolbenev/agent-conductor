"use strict";
// What the preparation chain needs from the wizard's state, as plain values.
//
// The chain (`desk-wizard-prep.js`) is generic over these facts and imports nothing of the
// wizard's state: this module reads the state once, through the same functions the steps use, and
// hands the chain its task, the seed conditions, the flow write of link 3, who runs each role, and
// the documents it publishes. It keeps nothing and writes nothing. It also holds the flow write
// itself (`flowWriteRequest`): the one place that knows the digest of the draft that stands.
import {briefDocument} from "./desk-wizard-base.js";
import {flowBody} from "./desk-wizard-cycle.js";
import {bodyOf, instructionsRow, textCard} from "./desk-wizard-materials.js";
import {assignedTo, heldFlow, instructionFields} from "./desk-wizard-team.js";
import {resumeRow} from "./desk-wizard-prep.js";

//: What the materials note is called when the owner types them again after a reload, in the
//: language of the document.
const MATERIALS_TITLE = Object.freeze({ru: "Материалы", en: "Materials"});

//: `POST …/flow` for the chosen cycle. Its id carries the generation of the choice, so an
//: answer for a card the owner has left is told apart from the card they are on. There is no
//: request until a read or an answer has said what draft stands for this cycle: the write's
//: expectation is that fact, never a guess (spec 7.1).
export function flowWriteRequest(state, {publish = null, binding = null} = {}) {
  const {choice, flow, flowFor, draft, generation} = state.cycle;
  if (choice === null || draft === null || draft.for !== choice.workflowId) return null;
  const held = flow !== null && flowFor === choice.workflowId ? flow : null;
  const body = flowBody(choice, held, draft.digest, publish, binding);
  return body === null ? null : {id: `write:flow:${generation}`, name: "flow", door: "write",
    target: "flow", subject: choice.workflowId, body};
}

//: The flow write that publishes the next revision, or null while none is known to stand.
function publishRequest(state) {
  const flow = state.cycle.flow;
  const next = flow !== null && Number.isSafeInteger(flow.next_revision) ? flow.next_revision
    : null;
  return next === null ? null : flowWriteRequest(state, {publish: next, binding: null});
}

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
    return {blocked: null, source: "git", commit: git.head.commit, include};
  }
  if (git?.state === "not_active") {
    return {blocked: null, source: "git", commit: null, include};
  }
  if (git?.state === "not_git" && state.mode.starterId === null
      && state.materials.withoutGit === true) {
    return {blocked: null, source: "empty", commit: null, include};
  }
  return {blocked: "seed_needs_git", source: null, commit: null, include};
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
 * @returns {object} Plain values only.
 */
export function runInput(state, lang) {
  const fields = instructionFields(state, lang);
  const request = publishRequest(state);
  const body = request === null ? null : withLikes(request.body, fields);
  const held = heldFlow(state);
  const own = fields.filter((field) => field.source !== "like").map((field) => ({
    ref: `instruction-${field.step_id}`, content: field.text}));
  return {taskId: state.task.taskId, title: state.task.title, taskWritten: state.task.written,
    starterId: state.mode.starterId, view: state.mode.view, lang, resumed: false,
    workflowId: state.cycle.choice?.workflowId ?? null, dispatch: fields.length > 0,
    seed: seedFacts(state), flowBody: body, flowDoc: body?.source.flow ?? held?.flow ?? null,
    ...bindings(state),
    documents: [{ref: "artifact-brief", content: briefDocument(state, lang)}, ...own],
    materials: bodyOf(state.materials.items, lang)};
}

/**
 * The same facts for a reloaded page: nothing but the documents the read says are missing, from
 * the text the owner typed again. The task, the seed, the cycle and the run stand already.
 *
 * @param {object} state The wizard's slice, with a `run.resume`.
 * @param {string} lang The language the documents are written in.
 * @returns {object} Plain values only; `documents` and `materials` name only what is missing.
 */
export function resumeInput(state, lang) {
  const row = resumeRow(state.run);
  const missing = row === null ? {instructions: [], inputs: []} : row.missing;
  const texts = state.run.resume.texts;
  const documents = [];
  if (missing.inputs.includes("artifact-brief")) {
    documents.push({ref: "artifact-brief", content: briefDocument(state, lang)});
  }
  for (const wanted of missing.instructions) {
    documents.push({ref: wanted.instruction_ref,
      content: texts[`instruction:${wanted.node_id}`] ?? ""});
  }
  const note = (texts.materials ?? "").trim() === "" ? []
    : [textCard("m1", {kind: "note", title: MATERIALS_TITLE[lang], content: texts.materials})];
  return {taskId: state.task.taskId, title: state.task.title, taskWritten: true,
    starterId: state.mode.starterId, view: state.mode.view, lang, resumed: true,
    workflowId: state.run.resume.workflowId, dispatch: false, seed: null, flowBody: null,
    flowDoc: null, participants: [], assignments: {}, documents,
    materials: missing.inputs.includes("artifact-materials") ? bodyOf(note, lang) : null};
}
