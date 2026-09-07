"use strict";
// What a person has opened or typed in the Workflow toolbar, kept across
// every render: which fold they toggled, the next workflow's id and starter,
// and the facts of the run they are about to open.
//
// R08 of the review of `8dec0e4` put the start box and the run form behind a
// fold each, open or folded by the STATE -- and the slice-3 review measured
// what that cost: the fold was recomputed from state on every render, so the
// next frame from anywhere closed the box a person had just opened, and the
// id they had typed into it went with it (the run form's fields had always
// gone that way: they were drawn from nothing). A frame lands on every write
// of any run and on every state frame, so the loss was ordinary.
//
// So the toolbar's own facts live here, in the reducer's `workflows` slice,
// exactly as the Runs screen's drafts live in its: a fold a person touched is
// theirs until they touch it again (`null` is "as the state decides"), and a
// typed word is committed on change. The letters typed since the last change,
// and the caret, are carried across a render by the boot module's focus net
// -- the view surface may not read the DOM back, and committing on every
// keystroke re-rendered the toolbar under the caret, moving it to the end and
// doubling an IME's composition. Choosing another workflow clears all three,
// which is the one road the whole slice is rebuilt on.
//
// It touches no DOM and imports nothing.

//: A fold nobody has touched: the state decides. `true` and `false` are a
//: person's own.
export const NO_FOLDS = Object.freeze({start: null, run: null});
//: The start box, empty.
export const NO_STARTER = Object.freeze({workflowId: "", starterId: ""});
//: The run form, as it is first drawn: the most restrictive authority that
//: still lets a person proceed, granted deliberately and never by default.
export const NO_OPENING = Object.freeze({
  runId: "", cycleId: "", mode: "observe", roles: Object.freeze({}),
  models: Object.freeze({}),
});
const FOLDS = Object.freeze(["start", "run"]);
const STARTER_KEYS = Object.freeze(["workflowId", "starterId"]);
const OPENING_KEYS = Object.freeze(["runId", "cycleId", "mode"]);

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function workflowsMoved(state, patch) {
  return Object.freeze({...state, workflows: Object.freeze({
    ...state.workflows, ...patch})});
}

//: The typed keys of a patch, copied over a held value; null when none moved.
function typedInto(held, keys, patch) {
  if (!isObject(patch)) return null;
  const next = {...held};
  let moved = false;
  for (const key of keys) {
    if (Object.hasOwn(patch, key) && typeof patch[key] === "string") {
      next[key] = patch[key];
      moved = true;
    }
  }
  return moved ? next : null;
}

function typedMap(patch, key) {
  return isObject(patch) && isObject(patch[key]) ? Object.freeze(
    Object.fromEntries(Object.entries(patch[key]).filter(
      ([, value]) => typeof value === "string"))) : null;
}

/**
 * A person opened or closed one fold by hand.
 *
 * @param {object} state The reducer's frozen value.
 * @param {object} event `{name, open}`: one of the two folds, and a boolean.
 * @returns {object} The next state, or the same one for anything else.
 */
export function foldMoved(state, event) {
  if (!FOLDS.includes(event.name) || typeof event.open !== "boolean") {
    return state;
  }
  return workflowsMoved(state, {folds: Object.freeze({
    ...state.workflows.folds, [event.name]: event.open})});
}

/**
 * One typed field of the start box: the next workflow's id or its starter.
 *
 * @param {object} state The reducer's frozen value.
 * @param {object} patch `{workflowId}` or `{starterId}`, strings.
 * @returns {object} The next state, or the same one when nothing moved.
 */
export function starterEdited(state, patch) {
  const next = typedInto(state.workflows.starter, STARTER_KEYS, patch);
  return next === null ? state : workflowsMoved(state, {
    starter: Object.freeze(next)});
}

/**
 * One typed field of the run form, or its whole role binding.
 *
 * `roles` replaces the map rather than merging into it: the form sends every
 * picker's value at once, so a role unbound again is not left bound. A model
 * belongs to that harness binding: changing it clears the model, even when a
 * caller sends a model in the same patch. A later model edit belongs to the
 * new binding. Frames never edit either map.
 *
 * @param {object} state The reducer's frozen value.
 * @param {object} patch `{runId}`, `{cycleId}`, `{mode}`, `{roles}` or `{models}`.
 * @returns {object} The next state, or the same one when nothing moved.
 */
export function openingEdited(state, patch) {
  const held = state.workflows.opening;
  const typed = typedInto(held, OPENING_KEYS, patch);
  const roles = typedMap(patch, "roles");
  const models = typedMap(patch, "models");
  if (typed === null && roles === null && models === null) return state;
  const bindings = roles === null ? held.roles : roles;
  const pinned = Object.fromEntries(Object.entries(models || held.models).filter(
    ([role]) => bindings[role] && bindings[role] === held.roles[role]));
  return workflowsMoved(state, {opening: Object.freeze({
    ...(typed === null ? held : typed),
    roles: bindings, models: Object.freeze(pinned)})});
}

/**
 * The run form emptied: the run it described is open.
 *
 * @param {object} state The reducer's frozen value.
 * @returns {object} The next state.
 */
export function openingCleared(state) {
  return workflowsMoved(state, {opening: NO_OPENING});
}
