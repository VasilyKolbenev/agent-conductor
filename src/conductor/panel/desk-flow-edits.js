"use strict";
// What one EDIT does to a cycle, and nothing else (spec 5.6.3, 7.2, 7.2.4).
//
// The closed vocabulary of the old `studio-edits.js`, over flow v1 instead of a workflow document:
// the nine words are the ones the canvas speaks (`studio-canvas.js`), and the names a `set-field`
// may carry are the flow's own fields plus the extension fields («Расширенные поля»), so nothing the
// server's schema has is out of reach and nothing it does not have can be written. Three copies of
// the words are held equal to each other and to the schema by `tests/test_desk_flow_guards.py`.
//
// Every edit is a transform: a flow in, `{flow, notice, added?}` out. `flow` is null when nothing
// changed (a word not known, a step not in the flow, a value the schema refuses, an edit that would
// change nothing) and `notice` then says why; the flow given is never touched. The desk has no rule
// of its own about what a good cycle is: an edit keeps the flow in the closed shape the server takes,
// and whether it is a good cycle is the server's diagnostics.
import {BOUND_EXT_FIELDS, DEFAULT_TIMEOUT, EXT_FIELDS, LIMITS, LINK_WHENS, REVIEW_PROFILES,
  ROLE_KINDS, blockEnd, canonical, defaultWhen, freshId, isLoop, loopOf, notice, refused,
  stepOf} from "./desk-flow-shape.js";
import {putReworkFirst, reworkIndex, withPasses, withRework, withoutStep} from "./desk-flow-loops.js";
import {branchFirst} from "./desk-flow-branches.js";

//: The words the canvas and the inspector speak; spelled the same in both, and here.
export const EDIT_TYPES = Object.freeze(["add", "connect", "delete-edge", "delete-node",
  "duplicate", "move", "reorder", "set-edge-condition", "set-field"]);
//: Every name a `set-field` may carry: a step's typed fields, its nine extension fields, the two
//: forms of loops (`passes`, `rework`) and the two fields of the flow itself.
export const EDIT_FIELDS = Object.freeze(["arguments", "attempt_bound", "back_to", "bound",
  "capability", "execution_contract", "failure_policy", "flow_title", "gate_id",
  "instruction_from", "missing_artifact_policy", "passes", "purpose", "reads",
  "required_evidence", "resources", "review_profile", "rework", "role_id", "stage",
  "success_requires", "timeout_seconds", "title", "verifier_role_id"]);
//: What the two fields of the flow itself are called and the two loop forms.
export const FLOW_FIELDS = Object.freeze(["flow_title", "execution_contract"]);
export const SUGAR_FIELDS = Object.freeze(["passes", "rework"]);
//: The kinds `add` takes (`task` and `gate` are the canvas's own words for the first two).
const ADD_TYPES = Object.freeze({agent: "agent", task: "agent", human: "human", gate: "human",
  route: "route", loop: "loop"});
const STEM = Object.freeze({human: "decision", route: "route", loop: "loop", custom: "step"});
const DEFAULT_CONTRACT = "bounded-run-v1";

const rows = (value) => (Array.isArray(value) ? value : []);
const blankNull = (value) => {
  if (value === null || (typeof value === "string" && value.trim() === "")) return null;
  return typeof value === "string" ? value : undefined;
};
const required = (value) => (typeof value === "string" && value.trim() !== "" ? value : undefined);
const whole = (value, range) => (Number.isInteger(value) && value >= range.min
  && value <= range.max ? value : undefined);

// -- adding ----------------------------------------------------------------------------------

function baseStep(id, type) {
  return {step_id: id, type, title: null, purpose: null, position: null, timeout_seconds: null,
    ext: {}};
}

//: A step of a role kind with what 7.2.2 gives it; a name that is none of the six is a custom role
//: that reviews (its author chooses the capability in the inspector).
function agentStep(flow, edit) {
  const named = edit.roleKind ?? "doer";
  const kind = Object.hasOwn(ROLE_KINDS, named) ? named : "custom";
  const spec = kind === "custom" ? null : ROLE_KINDS[kind];
  return {...baseStep(freshId(flow, kind === "custom" ? STEM.custom : kind), "agent"),
    timeout_seconds: DEFAULT_TIMEOUT, role_id: `role-${kind}`,
    capability: spec === null ? "review" : spec.capability,
    verifier_role_id: spec === null ? null : spec.checker,
    review_profile: spec === null ? null : spec.profile, reads: [], instruction_from: null,
    passes: spec === null ? 1 : spec.passes};
}

function madeStep(flow, edit, type, after) {
  if (type === "agent") return agentStep(flow, edit);
  const step = baseStep(freshId(flow, STEM[type]), type);
  return type === "loop" ? {...step, back_to: after.step_id, bound: 2} : step;
}

function inserted(flow, step, after) {
  const at = isLoop(step) ? reworkIndex(flow) : blockEnd(flow);
  const link = after === undefined ? [] : [{from: after.step_id, to: step.step_id,
    when: defaultWhen(after)}];
  return {...flow, steps: [...flow.steps.slice(0, at), step, ...flow.steps.slice(at)],
    links: [...flow.links, ...link]};
}

function addStep(flow, edit) {
  const type = Object.hasOwn(ADD_TYPES, edit.kind) ? ADD_TYPES[edit.kind] : null;
  if (type === null) return refused("kind_unknown");
  if (flow.steps.length >= LIMITS.steps) return refused("limit_steps");
  const after = typeof edit.afterId === "string" ? stepOf(flow, edit.afterId) : undefined;
  if (typeof edit.afterId === "string" && after === undefined) return refused("step_missing");
  if (type === "loop" && after === undefined) return refused("loop_needs_step");
  const {passes = 1, ...step} = madeStep(flow, edit, type, after);
  const placed = inserted(flow, step, after);
  const built = passes > 1 ? withPasses(placed, step.step_id, passes).flow : placed;
  return {flow: built, added: step.step_id, notice: notice("added", {step: step.step_id})};
}

// -- roads -----------------------------------------------------------------------------------

function connect(flow, edit) {
  const from = stepOf(flow, edit.fromId), to = stepOf(flow, edit.toId);
  if (from === undefined || to === undefined || from === to) return refused("connection_invalid");
  if (edit.when !== undefined && !LINK_WHENS.includes(edit.when)) return refused("word_unknown");
  if (flow.links.some((link) => link.from === edit.fromId && link.to === edit.toId)) {
    return refused("connection_exists");
  }
  if (flow.links.length >= LIMITS.links) return refused("limit_links");
  const link = {from: edit.fromId, to: edit.toId, when: edit.when ?? defaultWhen(from)};
  return {flow: {...flow, links: [...flow.links, link]}, notice: ""};
}

function dropLink(flow, edit) {
  const kept = flow.links.filter((link) => !(link.from === edit.fromId && link.to === edit.toId));
  return kept.length === flow.links.length ? refused("link_missing")
    : {flow: {...flow, links: kept}, notice: ""};
}

function setWord(flow, edit) {
  if (!LINK_WHENS.includes(edit.value)) return refused("word_unknown");
  const own = (link) => link.from === edit.fromId && link.to === edit.toId;
  const held = flow.links.find(own);
  if (held === undefined) return refused("link_missing");
  if (held.when === edit.value) return refused("word_same");
  return {flow: {...flow, links: flow.links.map((link) => (own(link)
    ? {...link, when: edit.value} : link))}, notice: ""};
}

// -- removing and copying --------------------------------------------------------------------

//: A step's own loops go with it, and so does every loop that returned to it.
function goneWith(flow, id) {
  const gone = new Set([id]);
  for (const kind of ["passes", "rework"]) {
    const held = loopOf(flow, id, kind);
    if (held !== undefined) gone.add(held.step_id);
  }
  for (const step of flow.steps) if (isLoop(step) && step.back_to === id) gone.add(step.step_id);
  return gone;
}

function withoutReferences(step, gone) {
  if (step.type !== "agent") return step;
  const reads = step.reads.filter((name) => !gone.has(name));
  const borrowed = gone.has(step.instruction_from) ? null : step.instruction_from;
  return reads.length === step.reads.length && borrowed === step.instruction_from ? step
    : {...step, reads, instruction_from: borrowed};
}

function dropStep(flow, edit) {
  if (stepOf(flow, edit.nodeId) === undefined) return refused("step_missing");
  const gone = goneWith(flow, edit.nodeId);
  let next = flow;
  for (const id of gone) next = withoutStep(next, id);
  return {flow: {...next, steps: next.steps.map((step) => withoutReferences(step, gone))},
    notice: notice("removed", {step: edit.nodeId})};
}

//: `do-2` copies under the stem `do`, not `do-2-2`.
function stemOf(id) {
  return id.replace(/-[0-9]+$/, "");
}

function duplicate(flow, edit) {
  const step = stepOf(flow, edit.nodeId);
  if (step === undefined) return refused("step_missing");
  if (flow.steps.length >= LIMITS.steps) return refused("limit_steps");
  const id = freshId(flow, stemOf(step.step_id));
  const {gate_id: _one, ...ext} = structuredClone(step.ext);
  const at = step.position === null ? null : {x: step.position.x + 32, y: step.position.y + 32};
  const copy = {...structuredClone(step), step_id: id, position: at, ext};
  return {flow: inserted(flow, copy), added: id, notice: notice("duplicated", {step: id})};
}

// -- placing ---------------------------------------------------------------------------------

function moveStep(flow, edit) {
  const step = stepOf(flow, edit.nodeId);
  if (step === undefined) return refused("step_missing");
  if (edit.clear === true) return step.position === null ? refused("unchanged")
    : replaceStep(flow, step, {position: null});
  const x = Math.round(Number(edit.x)), y = Math.round(Number(edit.y));
  const limit = LIMITS.position;
  if (!Number.isInteger(x) || !Number.isInteger(y) || Math.abs(x) > limit || Math.abs(y) > limit) {
    return refused("position_range");
  }
  if (step.position?.x === x && step.position?.y === y) return refused("unchanged");
  return replaceStep(flow, step, {position: {x, y}});
}

function replaceStep(flow, step, change) {
  const steps = flow.steps.map((one) => (one === step ? {...one, ...change} : one));
  return {flow: {...flow, steps}, notice: ""};
}

//: A step moves among the steps of its own band (loops among loops, the rest among the rest), so a
//: loop never leaves the loops' place and a step never leaves the steps'.
function reorder(flow, edit) {
  if (edit.reworkFirst === true) return putReworkFirst(flow);
  if (edit.branchFirst === true) return branchFirst(flow, edit.nodeId);
  const step = stepOf(flow, edit.nodeId);
  if (step === undefined) return refused("step_missing");
  const band = flow.steps.filter((one) => isLoop(one) === isLoop(step));
  const target = band[Math.max(0, Math.min(band.length - 1, Number(edit.index)))];
  if (!Number.isInteger(Number(edit.index)) || target === undefined || target === step) {
    return refused("unchanged");
  }
  const rest = flow.steps.filter((one) => one !== step);
  const before = flow.steps.indexOf(step) < flow.steps.indexOf(target) ? 1 : 0;
  const at = rest.indexOf(target) + before;
  return {flow: {...flow, steps: [...rest.slice(0, at), step, ...rest.slice(at)]}, notice: ""};
}

// -- fields ----------------------------------------------------------------------------------

const ANY = Object.freeze(["agent", "human", "route", "loop"]);
const idList = (value) => {
  const list = rows(value);
  const good = Array.isArray(value) && list.every((name) => required(name) !== undefined)
    && new Set(list).size === list.length;
  return good && list.length <= LIMITS.reads ? [...list] : undefined;
};
//: The typed fields of a step: where each may be written and what it takes (`undefined` refuses).
const TYPED = Object.freeze({
  title: {types: ANY, make: blankNull},
  purpose: {types: ANY, make: blankNull},
  timeout_seconds: {types: ANY, make: (value) => (value === null ? null
    : whole(value, LIMITS.timeout))},
  role_id: {types: ["agent"], make: required},
  capability: {types: ["agent"], make: required},
  verifier_role_id: {types: ["agent"], make: blankNull},
  review_profile: {types: ["agent"], make: (value) => (value === null
    || REVIEW_PROFILES.includes(value) ? value : undefined)},
  reads: {types: ["agent"], make: idList},
  instruction_from: {types: ["agent"], make: blankNull},
  back_to: {types: ["loop"], make: required},
  bound: {types: ["loop"], make: (value) => whole(value, LIMITS.bound)},
});

function plain(value) {
  try {
    return JSON.parse(JSON.stringify(value)) ?? null;
  } catch (_error) {
    return undefined;
  }
}

//: One key of a step's `ext`: a value writes it, `clear` removes it (the computed value stands).
function withExt(flow, step, name, edit) {
  const held = {...step.ext};
  if (edit.clear === true) {
    if (!Object.hasOwn(held, name)) return refused("unchanged");
    delete held[name];
  } else {
    const value = plain(edit.value);
    if (value === undefined) return refused("field_invalid");
    if (Object.hasOwn(held, name) && canonical(held[name]) === canonical(value)) {
      return refused("unchanged");
    }
    held[name] = value;
  }
  return replaceStep(flow, step, {ext: held});
}

function typedField(flow, step, edit) {
  const rule = TYPED[edit.field];
  if (!rule.types.includes(step.type)) return refused("field_invalid");
  if (edit.field === "reads" && rows(edit.value).length > LIMITS.reads) {
    return refused("reads_limit", {max: String(LIMITS.reads)});
  }
  const value = rule.make(edit.value);
  if (value === undefined) return refused("field_invalid");
  if (JSON.stringify(step[edit.field]) === JSON.stringify(value)) return refused("unchanged");
  return replaceStep(flow, step, {[edit.field]: value});
}

function flowField(flow, edit) {
  if (edit.field === "flow_title") {
    if (required(edit.value) === undefined) return refused("title_required");
    return edit.value === flow.title ? refused("unchanged")
      : {flow: {...flow, title: edit.value}, notice: ""};
  }
  const ext = {...flow.ext};
  if (edit.value === null && edit.clear !== true) ext.execution_contract = null;
  else if (edit.value === DEFAULT_CONTRACT || edit.clear === true) delete ext.execution_contract;
  else return refused("field_invalid");
  return JSON.stringify(ext) === JSON.stringify(flow.ext) ? refused("unchanged")
    : {flow: {...flow, ext}, notice: ""};
}

function setField(flow, edit) {
  if (!EDIT_FIELDS.includes(edit.field)) return refused("field_unknown");
  if (FLOW_FIELDS.includes(edit.field)) return flowField(flow, edit);
  const step = stepOf(flow, edit.nodeId);
  if (step === undefined) return refused("step_missing");
  if (edit.field === "passes") return withPasses(flow, edit.nodeId, edit.value);
  if (edit.field === "rework") return withRework(flow, edit.nodeId, edit.value);
  const bound = BOUND_EXT_FIELDS.includes(edit.field) && step.type !== "agent";
  if (EXT_FIELDS.includes(edit.field) || bound) return withExt(flow, step, edit.field, edit);
  return typedField(flow, step, edit);
}

//: One arm per edit word: a type not named here reaches no flow at all.
const EDITS = Object.freeze({add: addStep, connect, "delete-edge": dropLink,
  "delete-node": dropStep, duplicate, move: moveStep, reorder, "set-edge-condition": setWord,
  "set-field": setField});

/**
 * The one door an edit knocks on. Answers `{flow, notice, added?}`; `flow` is null when nothing
 * moved, and `notice` (a `{key, params}` message or an empty string) says why.
 */
export function applyEdit(flow, edit) {
  const known = EDIT_TYPES.includes(edit?.type) && Object.hasOwn(EDITS, edit.type);
  if (!known || flow === null || typeof flow !== "object") return {flow: null, notice: ""};
  return EDITS[edit.type](flow, edit);
}
