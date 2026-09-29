"use strict";
// The address of the desk: what its hash may say, read and written by one grammar (spec
// 4.5.2). The hash is an untrusted input -- the hub sets it, a bookmark carries it, and any
// page that opened the window can change it -- so it holds identifiers and interface words
// only, never a token, a path or a line of a task's text, and everything below judges a value
// by the same table of checks whether it is being read or about to be written.
//
// This module is shared with the hub's page, which loads it without the Studio: it is values
// in and values out, imports nothing and reaches neither the page, the wire nor the platform.
// What a hash MEANS to the desk -- which task to open, which language to say -- is the boot
// module's; this module says only which keys a hash carries and which of them moved.

//: The grammars, each the one its source has: a project is the activation's 32 hex; a task id
//: is the task model's, and a run, gate, workflow or starter id the routes' (a name longer than
//: the store can address is a path no route names, so it is no name here either).
const PROJECT = /^[0-9a-f]{32}$/;
const TASK = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
//: The panels a hash may open: the cycle, a run in detail, the people, the continue-after block.
export const PANELS = Object.freeze(["cycle", "run", "people", "continue"]);

//: The keys of the desk's hash, in the order they are written; the interface keys `lang` and
//: `theme` follow them and are the preference functions' below.
export const HASH_KEYS = Object.freeze(["project", "embed", "task", "run", "gate", "workflow",
  "panel", "new", "prepare", "starter"]);
//: The keys that ask the desk to move its selection, in the order a change applies them, top
//: to bottom: the task, its run, the gate, the panel of the cycle, the wizard, the preparation.
const NAVIGATION = Object.freeze(["task", "run", "gate", "workflow", "panel", "new", "starter",
  "prepare"]);
//: What a changed task starts over: a key the same hash does not carry is reset.
const RESET_BY_TASK = Object.freeze(["run", "gate", "panel", "workflow", "prepare"]);

const CHECKS = Object.freeze({
  project: (value) => PROJECT.test(value),
  embed: (value) => value === "hub",
  task: (value) => TASK.test(value),
  run: (value) => ID.test(value),
  gate: (value) => ID.test(value),
  workflow: (value) => ID.test(value),
  panel: (value) => PANELS.includes(value),
  new: (value) => value === "task",
  prepare: (value) => value === "1",
  starter: (value) => ID.test(value),
});

//: A state judged: every key is a value that passes its check or `null`, and the three keys
//: that hang on another are `null` without it (a gate needs its run, a preparation its task,
//: a starter the wizard it opens).
function settle(raw) {
  const kept = Object.fromEntries(HASH_KEYS.map((key) => {
    const value = raw[key];
    return [key, typeof value === "string" && CHECKS[key](value) ? value : null];
  }));
  return Object.freeze({...kept,
    gate: kept.run === null ? null : kept.gate,
    prepare: kept.task === null ? null : kept.prepare,
    starter: kept.new === null ? null : kept.starter});
}

//: A hash read into the ten keys. A key met more than once is absent, as in `readPreferences`;
//: `project` is the exception the desk must hear about, so it also says it was repeated.
export function readDeskHash(hash) {
  const fields = new URLSearchParams(hash.replace(/^#/, ""));
  const once = (key) => (fields.getAll(key).length === 1 ? fields.get(key) : null);
  return Object.freeze({...settle(Object.fromEntries(HASH_KEYS.map((key) => [key, once(key)]))),
    projectRepeated: fields.getAll("project").length > 1});
}

//: A state written: the keys that pass, in the order of the spec. What the reader would refuse
//: is never written, so no address the desk makes holds a value another page could not read.
export function deskHash(state) {
  const settled = settle(state);
  const fields = new URLSearchParams();
  for (const key of HASH_KEYS) if (settled[key] !== null) fields.set(key, settled[key]);
  return `#${fields}`;
}

//: What `next` asks of a desk whose own last address said `last`. A step is a navigation key
//: that `next` carries and that differs from `last`; a key `next` does not carry never moves
//: anything, so the hub may send the language alone and the selection stays. A changed `task`
//: also resets the keys the same hash does not carry.
export function navigationChange(last, next) {
  const steps = NAVIGATION.filter((key) => next[key] !== null && next[key] !== last[key])
    .map((key) => Object.freeze({key, value: next[key]}));
  const taskMoved = steps.some((step) => step.key === "task");
  return Object.freeze({steps: Object.freeze(steps),
    reset: Object.freeze(taskMoved ? RESET_BY_TASK.filter((key) => next[key] === null) : [])});
}

//: The desk is open for another project when a hash claims a project twice, or claims one
//: that is not the project the desk bound to (including no bound project at all). A hash that
//: names no project, or names one that is not a project id, claims nothing.
export function foreignProject(bound, address) {
  return address.projectRepeated || (address.project !== null && address.project !== bound);
}

export function readPreferences(hash, language) {
  const fields = new URLSearchParams(hash.replace(/^#/, ""));
  const one = (key, allowed) => fields.getAll(key).length === 1
    && allowed.includes(fields.get(key)) ? fields.get(key) : null;
  return Object.freeze({locale: one("lang", ["en", "ru"])
    || (/^ru(?:-|$)/i.test(language || "") ? "ru" : "en"),
  theme: one("theme", ["dark", "light"])});
}

export function preferenceHash(hash, value) {
  const fields = new URLSearchParams(hash.replace(/^#/, ""));
  fields.set("lang", value.locale);
  if (value.theme === null) fields.delete("theme");
  else fields.set("theme", value.theme);
  return `#${fields}`;
}
