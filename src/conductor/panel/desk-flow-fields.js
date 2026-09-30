"use strict";
// What the inspector of the «Схема» asks of a step, and how a typed text becomes one edit
// (spec 5.6.3, 7.2.1).
//
// The inspector draws ROWS: each names one field of the edit vocabulary (`desk-flow-edits.js`), the
// control it is drawn with and the text that control shows. `fieldEdit` is the way back: a text typed
// into a row becomes the one `set-field` edit the flow's edits take, or says why it cannot (a word
// where a number is wanted, a JSON that does not parse). The two are held to each other by
// `tests/test_desk_flow_fields.py`: the text a row shows, typed back, changes nothing.
//
// Nothing here is a rule about what a good cycle is: a row offers what the flow's own shape has and
// the server's diagnostics say the rest. The raw fields of the old Studio are the «Расширенные поля»
// rows: a key a step holds is shown and can be given back to the compiler, and a key it does not hold
// is written only when the person applies a value, so nothing half-written ever reaches the flow.
//
// Pure functions of a flow and a step; nothing is changed, nothing is read from a clock or a store.
import {BOUND_EXT_FIELDS, EXT_FIELDS, REVIEW_PROFILES, isDispatch, isLoop, loopOf,
  stepOf} from "./desk-flow-shape.js";

//: The control each field is drawn with. An extension field is always `json`.
const CONTROL = Object.freeze({title: "text", purpose: "area", timeout_seconds: "int",
  role_id: "text", capability: "select", verifier_role_id: "text", review_profile: "select",
  reads: "ids", instruction_from: "select", back_to: "select", bound: "int", passes: "int",
  rework: "int", flow_title: "text", execution_contract: "select"});
//: Every field name this module can write: its own table and the extension keys.
export const WRITTEN_FIELDS = Object.freeze([...new Set([...Object.keys(CONTROL), ...EXT_FIELDS,
  ...BOUND_EXT_FIELDS])].sort());
//: The two contracts a cycle can carry: the one the compiler writes, and none (older cycles).
export const CONTRACTS = Object.freeze(["bounded-run-v1", "none"]);
const CAPABILITIES = Object.freeze(["review", "dispatch"]);
//: The extension keys a step of each type is offered; a key it already holds is shown besides.
const OFFERED = Object.freeze({
  agent: EXT_FIELDS.filter((name) => name !== "gate_id" && name !== "success_requires"),
  human: EXT_FIELDS, route: EXT_FIELDS.filter((name) => name !== "gate_id"
    && name !== "success_requires"), loop: []});

const asText = (value) => (value === null || value === undefined ? "" : String(value));
const row = (section, field, control, text, extra = {}) => ({section, field, control, text,
  ...extra});
const withCurrent = (options, current) => (current === "" || options.includes(current) ? options
  : [...options, current]);

function generalRows(step) {
  return [row("general", "title", "text", asText(step.title)),
    row("general", "purpose", "area", asText(step.purpose))];
}

function roleRows(step) {
  const rows = [row("role", "role_id", "text", asText(step.role_id)),
    row("role", "capability", "select", asText(step.capability),
      {options: withCurrent([...CAPABILITIES], step.capability)}),
    row("role", "verifier_role_id", "text", asText(step.verifier_role_id))];
  if (step.capability === "review") {
    rows.push(row("role", "review_profile", "select", asText(step.review_profile),
      {options: ["", ...REVIEW_PROFILES]}));
  }
  return rows;
}

function limitRows(flow, step) {
  const rows = [row("limits", "timeout_seconds", "int", asText(step.timeout_seconds))];
  if (isDispatch(step)) {
    rows.push(row("limits", "passes", "int", asText(loopOf(flow, step.step_id, "passes")?.bound
      ?? 1)));
  }
  return rows;
}

function inputRows(flow, step) {
  const rows = [];
  if (isDispatch(step)) {
    const others = flow.steps.filter((one) => one.step_id !== step.step_id && isDispatch(one)
      && one.instruction_from === null).map((one) => one.step_id);
    rows.push(row("inputs", "instruction_from", "select", asText(step.instruction_from),
      {options: withCurrent(["", ...others], asText(step.instruction_from))}));
  }
  rows.push(row("inputs", "reads", "ids", step.reads.join(", ")));
  return rows;
}

function loopRows(flow, step) {
  const homes = flow.steps.filter((one) => !isLoop(one)).map((one) => one.step_id);
  return [row("loop", "back_to", "select", asText(step.back_to),
    {options: withCurrent(homes, step.back_to)}),
  row("loop", "bound", "int", asText(step.bound))];
}

//: The extension rows: the keys the type is offered, then any key it holds, in the order of the
//: schema's own list. A key a step holds is `set`, and its text is the JSON it holds.
function extRows(step) {
  const agent = step.type === "agent";
  const order = [...EXT_FIELDS, ...(agent ? [] : BOUND_EXT_FIELDS)];
  return order.filter((name) => (OFFERED[step.type] ?? []).includes(name)
    || Object.hasOwn(step.ext, name)).map((name) => {
    const set = Object.hasOwn(step.ext, name);
    return row("ext", name, "json", set ? JSON.stringify(step.ext[name], null, 2) : "", {set});
  });
}

/**
 * The rows of one step, by section, in the order they are drawn: `{section, field, control, text,
 * options?, set?}`. An agent has its role, limits and inputs; a gate its rework; a loop its return
 * and bound; every step its name, its purpose and its extension rows.
 */
export function stepRows(flow, step) {
  const reworked = step.type === "human"
    ? [row("rework", "rework", "int", asText(loopOf(flow, step.step_id, "rework")?.bound))] : [];
  const typed = {
    agent: () => [...roleRows(step), ...limitRows(flow, step), ...inputRows(flow, step)],
    human: () => reworked, loop: () => loopRows(flow, step)}[step.type];
  return [...generalRows(step), ...(typed === undefined ? [] : typed()), ...extRows(step)];
}

/** The rows of the cycle itself: its name and its execution contract. */
export function flowRows(flow) {
  const contract = Object.hasOwn(flow.ext, "execution_contract") && flow.ext.execution_contract
    === null ? "none" : CONTRACTS[0];
  return [row("flow", "flow_title", "text", asText(flow.title)),
    row("flow", "execution_contract", "select", contract, {options: [...CONTRACTS]})];
}

/** How many extension keys a step holds: the number its «Расширенные поля» heading carries. */
export function extCount(step) {
  return Object.keys(step.ext).length;
}

/** Give a key back to the compiler: the edit that removes it from the step's extension. */
export function clearEdit(nodeId, field) {
  return {type: "set-field", nodeId, field, clear: true};
}

const WHOLE = /^[0-9]+$/;

function whole(text) {
  const held = text.trim();
  return WHOLE.test(held) ? Number(held) : undefined;
}

//: The value a text means for a control, or `{reason}`. A blank number is nothing where nothing is
//: allowed (a time limit, a rework) and is refused where a number is owed (passes, a loop's bound).
function valueOf(control, field, text) {
  if (control === "int") {
    if (text.trim() === "" && (field === "timeout_seconds" || field === "rework")) {
      return {value: null};
    }
    const number = whole(text);
    return number === undefined ? {reason: "int"} : {value: number};
  }
  if (control === "ids") return {value: text.split(/[\s,]+/).filter((part) => part !== "")};
  if (control === "json") {
    if (text.trim() === "") return {reason: "empty"};
    try {
      return {value: JSON.parse(text)};
    } catch (_error) {
      return {reason: "json"};
    }
  }
  if (field === "execution_contract") return {value: text === "none" ? null : text};
  if (control === "select" && (field === "review_profile" || field === "instruction_from")) {
    return {value: text === "" ? null : text};
  }
  return {value: text};
}

function controlOf(flow, nodeId, field) {
  const step = nodeId === null ? undefined : stepOf(flow, nodeId);
  const bound = step !== undefined && step.type !== "agent" && BOUND_EXT_FIELDS.includes(field);
  if (EXT_FIELDS.includes(field) || bound) return "json";
  return Object.hasOwn(CONTROL, field) ? CONTROL[field] : null;
}

/**
 * The edit a text typed into a row means: `{edit}` with one `set-field` for the step (or for the
 * cycle when `nodeId` is null), or `{reason}` with why it means none: `text` (not a string),
 * `field` (no such row), `int` (not a whole number), `json` (does not parse) or `empty` (nothing
 * to apply to an extension row).
 */
export function fieldEdit(flow, nodeId, field, text) {
  if (typeof text !== "string") return {reason: "text"};
  const control = controlOf(flow, nodeId, field);
  if (control === null) return {reason: "field"};
  const made = valueOf(control, field, text);
  if (made.reason !== undefined) return {reason: made.reason};
  return {edit: {type: "set-field", nodeId, field, value: made.value}};
}
