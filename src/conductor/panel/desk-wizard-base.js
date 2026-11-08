"use strict";
// What the wizard's model and its step adapters share, so neither has to import the other:
// the order of the steps, the limits, how a frozen change is made, how a text is measured, and
// the words of the documents the wizard composes (an `artifact-brief` and the default
// instruction), which are data for agents and live here rather than in the interface catalogue.
import {TASK_TITLE_LIMIT} from "./studio-tasks-model.js";
import {MATERIAL_LIMITS, composeText, documentCard, isDocumentRow, textCard} from "./desk-wizard-materials.js";
import {ARGV_LIMIT} from "./desk-wizard-roles.js";

export const STEPS = Object.freeze(["task", "materials", "cycle", "roles", "prepare", "run"]);
//: The four steps the owner fills in: what the chain of step 5 writes is what they said there.
export const FILL_STEPS = Object.freeze(["task", "materials", "cycle", "roles"]);
//: The steps this build draws: the four the owner fills in, the preparation that writes them and
//: the terms card the run starts or is queued from.
export const BUILT_STEPS = Object.freeze([...FILL_STEPS, "prepare", "run"]);
export const GUIDE_STAGES = Object.freeze([
  ["result", "task", "materials"], ["team", "cycle", "roles"], ["review", "prepare", "run"],
]);
export function guideStage(step) {
  return GUIDE_STAGES.find(([, first, last]) => step === first || step === last);
}
export function titleFromGoal(goal) {
  const line = goal.split(/\r?\n/).find((part) => part.trim()) || "";
  return [...line.replace(/[\x00-\x1f\x7f]/g, " ").trim()].slice(0, TASK_TITLE_LIMIT).join("");
}
export const LIMITS = Object.freeze({materials: MATERIAL_LIMITS.count,
  documentBytes: MATERIAL_LIMITS.bytes, argvChars: ARGV_LIMIT, title: TASK_TITLE_LIMIT});

const WORDS = Object.freeze({
  ru: Object.freeze({todo: "Что нужно сделать", idea: "Идея проекта",
    hint: "Как понять, что готово (подсказка)", none: "—"}),
  en: Object.freeze({todo: "What needs to be done", idea: "Project idea",
    hint: "How to tell it is done (hint)", none: "—"}),
});
const encoder = new TextEncoder();
const DRAFT_ID = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$/;
export const validModelText = (value) => typeof value === "string" && (value.trim() === "" || DRAFT_ID.test(value.trim()));

function draftMaterials(rows, documents) {
  if (!Array.isArray(rows)) return [];
  return rows.slice(0, MATERIAL_LIMITS.count).flatMap((row, i) => {
    if (!row) return [];
    const key = `m${i + 1}`;
    if (["plan", "ideas", "scheme", "note"].includes(row.kind)) return [textCard(key, row)];
    const doc = Array.isArray(documents) && documents.find((item) => isDocumentRow(item)
      && item.doc_id === row.docId && item.git_oid === row.gitOid);
    return doc ? [{...documentCard(key, doc), mode: row.mode === "copy" ? "copy" : "link",
      edits: Array.isArray(row.edits) ? row.edits : []}] : [];
  });
}

export function restoreAnswers(fresh, held, documents, offered) {
  const items = draftMaterials(held.items, documents).map((row, at) => ({...row, key: `m${at + 1}`}));
  const known = offered.find((row) => row.id === held.cycleId && row.kind !== "build");
  const restored = {guided: held.guided !== false, titleEdited: held.titleEdited === true,
    budgetDepth: ["quick", "thorough"].includes(held.budgetDepth) ? held.budgetDepth : "balanced",
    draftMaterialsMissing: Array.isArray(held.items) && items.length !== held.items.length,
    task: {...fresh.task, title: held.title, brief: held.brief, hint: held.hint},
    materials: {...fresh.materials, items, counter: items.length, withoutGit: held.withoutGit === true,
      includeInstructions: typeof held.includeInstructions === "boolean" ? held.includeInstructions : null}};
  if (!known) return evolve(fresh, restored);
  const revision = held.cycleRevision ?? (fresh.firstRunGuide ? known.revision : null);
  restored.cycle = {...fresh.cycle, choice: {kind: known.kind, workflowId: known.workflowId,
    ...(known.kind === "saved" && Number.isSafeInteger(revision) && revision > 0 ? {revision} : {})},
    chosenBy: "owner", generation: 1};
  const entries = (value) => value && typeof value === "object" && !Array.isArray(value)
    ? Object.entries(value).filter(([id]) => DRAFT_ID.test(id)) : [];
  const owner = entries(held.owner).filter(([, id]) => typeof id === "string" && DRAFT_ID.test(id));
  const instructions = [];
  for (const [id, item] of entries(held.instructions)) {
    if (!item || !["own", "task", "like"].includes(item.source) || typeof item.text !== "string") continue;
    if (item.source === "like" && (typeof item.like !== "string" || !DRAFT_ID.test(item.like))) continue;
    instructions.push([id, {source: item.source, like: item.source === "like" ? item.like : null,
      text: item.text, back: item.back === "task" ? "task" : "own"}]);
  }
  const models = entries(held.models).filter(([, pin]) => pin && typeof pin.provider === "string" && DRAFT_ID.test(pin.provider)
    && typeof pin.text === "string" && pin.text.length <= 128)
    .map(([role, pin]) => [role, {provider: pin.provider, text: pin.text}]);
  restored.roles = {owner: Object.fromEntries(owner), instructions: Object.fromEntries(instructions),
    models: Object.fromEntries(models)};
  return evolve(fresh, restored);
}

export function isLanguage(lang) {
  return Object.hasOwn(WORDS, lang);
}

export function utf8Bytes(text) {
  return encoder.encode(text).length;
}

export function frozen(value) {
  if (value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const item of Object.values(value)) frozen(item);
  return Object.freeze(value);
}

export function evolve(state, patch) {
  return frozen({...state, ...patch});
}

function wordsFor(lang) {
  if (!isLanguage(lang)) throw new Error("unknown document language");
  return WORDS[lang];
}

//: The `artifact-brief` document (spec 6.2.3, n. 1), byte for byte: the same template the
//: server-side readers expect, a starter's idea under its own heading, a dash for no hint.
export function briefDocument(state, lang) {
  const words = wordsFor(lang);
  const starter = state.mode.starterId !== null;
  const text = starter ? state.task.idea : state.task.brief;
  const hint = starter || state.task.hint.trim() === "" ? words.none : state.task.hint;
  return `# ${state.task.title}\n\n## ${starter ? words.idea : words.todo}\n${text}\n\n`
    + `## ${words.hint}\n${hint}\n`;
}

//: The instruction a doer gets by default is the task's own text, hint included (spec 6.1).
export function taskText(state, lang) {
  const words = wordsFor(lang);
  const {brief, hint} = state.task;
  return hint.trim() === "" ? brief : `${brief}\n\n## ${words.hint}\n${hint}`;
}

//: How many UTF-16 units the brief and the materials add to every instruction on a command
//: line, in the longer of the two languages (spec 6.3).
export function inputChars(state) {
  return briefDocument(state, "ru").length + composeText(state.materials.items, "ru").length;
}
