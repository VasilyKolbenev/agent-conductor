"use strict";
// What the wizard's model and its step adapters share, so neither has to import the other:
// the order of the steps, the limits, how a frozen change is made, how a text is measured, and
// the words of the documents the wizard composes (an `artifact-brief` and the default
// instruction), which are data for agents and live here rather than in the interface catalogue.
import {TASK_TITLE_LIMIT} from "./studio-tasks-model.js";
import {MATERIAL_LIMITS, composeText} from "./desk-wizard-materials.js";
import {ARGV_LIMIT} from "./desk-wizard-roles.js";

export const STEPS = Object.freeze(["task", "materials", "cycle", "roles", "prepare", "run"]);
//: The four steps the owner fills in: what the chain of step 5 writes is what they said there.
export const FILL_STEPS = Object.freeze(["task", "materials", "cycle", "roles"]);
export const BUILT_STEPS = FILL_STEPS;
export const LIMITS = Object.freeze({materials: MATERIAL_LIMITS.count,
  documentBytes: MATERIAL_LIMITS.bytes, argvChars: ARGV_LIMIT, title: TASK_TITLE_LIMIT});

const WORDS = Object.freeze({
  ru: Object.freeze({todo: "Что нужно сделать", idea: "Идея проекта",
    hint: "Как понять, что готово (подсказка)", none: "—"}),
  en: Object.freeze({todo: "What needs to be done", idea: "Project idea",
    hint: "How to tell it is done (hint)", none: "—"}),
});
const encoder = new TextEncoder();

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
