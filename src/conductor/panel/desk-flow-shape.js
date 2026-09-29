"use strict";
// The facts of flow v1 the desk edits by (spec 7.2), and pure questions over a flow.
//
// Every constant here is a copy of what `command/workflow_flow.py` owns: the desk imports no Python,
// so `tests/test_desk_flow_guards.py` holds each copy equal to it (a step's keys, the road words, the
// extension fields, the bounds). The questions read a flow and nothing else: no wire, no clock, no
// store, and no rule of the server's -- whether a flow is right is the server's diagnostics. What is
// answered here is only what an edit needs to know to keep the flow's own shape: which roads leave a
// step, which loop is a step's pass loop, which name is free.
//
// It imports nothing, and it never changes a flow it is given.

export const FLOW_VERSION = 1;
export const STEP_TYPES = Object.freeze(["agent", "human", "route", "loop"]);
//: `graph_conditions.EDGE_CONDITIONS` without the `on_` prefix (`succeeded` is `success`), and the road
//: with no condition, `always`.
export const LINK_WHENS = Object.freeze(["success", "failed", "approved", "rejected",
  "changes_requested", "waived", "bound_reached", "bound_remaining", "always"]);
//: The words of a road the desk draws by default; the others live in a road's extended fields.
export const DESK_WORDS = Object.freeze(["success", "approved", "rejected"]);
export const EXT_FIELDS = Object.freeze(["stage", "arguments", "resources", "attempt_bound",
  "required_evidence", "failure_policy", "missing_artifact_policy", "gate_id", "success_requires"]);
//: What a gate or a loop may keep in `ext` besides: the role keys an import found on it.
export const BOUND_EXT_FIELDS = Object.freeze(["role_id", "capability", "verifier_role_id"]);
export const FLOW_EXT_FIELDS = Object.freeze(["execution_contract"]);
export const REVIEW_PROFILES = Object.freeze(["spec", "quality", "security"]);
//: The keys of each step type, as the server's shapes have them (`STEP_FIELDS`).
export const STEP_KEYS = Object.freeze({
  agent: Object.freeze(["step_id", "type", "title", "purpose", "position", "timeout_seconds",
    "role_id", "capability", "verifier_role_id", "review_profile", "reads", "instruction_from",
    "ext"]),
  human: Object.freeze(["step_id", "type", "title", "purpose", "position", "timeout_seconds", "ext"]),
  route: Object.freeze(["step_id", "type", "title", "purpose", "position", "timeout_seconds", "ext"]),
  loop: Object.freeze(["step_id", "type", "title", "purpose", "position", "timeout_seconds",
    "back_to", "bound", "ext"]),
});
export const LIMITS = Object.freeze({steps: 256, links: 1024, reads: 8, position: 100000,
  bound: Object.freeze({min: 1, max: 99}), rework: Object.freeze({min: 2, max: 8}),
  timeout: Object.freeze({min: 1, max: 86400})});
//: A step id whose `artifact-<id>` the run's own documents already hold.
export const RESERVED_IDS = Object.freeze(["brief", "materials"]);
export const DEFAULT_TIMEOUT = 1800;
export const CHECKER_ROLE = "role-checker";
//: The role kinds of 7.2.2. `passes` is what a new step of the kind gets, and 1 means none.
export const ROLE_KINDS = Object.freeze({
  analyst: Object.freeze({capability: "review", profile: "spec", checker: null, passes: 1}),
  designer: Object.freeze({capability: "review", profile: "spec", checker: null, passes: 1}),
  diagnostician: Object.freeze({capability: "review", profile: "quality", checker: null, passes: 1}),
  reviewer: Object.freeze({capability: "review", profile: "quality", checker: null, passes: 1}),
  doer: Object.freeze({capability: "dispatch", profile: null, checker: CHECKER_ROLE, passes: 3}),
  tester: Object.freeze({capability: "dispatch", profile: null, checker: CHECKER_ROLE, passes: 2}),
});
const ROLE_NAME = /^role-([a-z]+)(?:-[0-9]+)?$/;

/** The kind a role id names (`role-doer`, `role-doer-2`), or null when it names none of the six. */
export function kindOfRole(roleId) {
  const found = typeof roleId === "string" ? ROLE_NAME.exec(roleId) : null;
  return found !== null && Object.hasOwn(ROLE_KINDS, found[1]) ? found[1] : null;
}

const rows = (value) => (Array.isArray(value) ? value : []);

/** The step with this id, or undefined (the first one when an id is repeated). */
export function stepOf(flow, id) {
  return rows(flow?.steps).find((step) => step.step_id === id);
}

export const isDispatch = (step) => step?.type === "agent" && step.capability === "dispatch";
export const isReview = (step) => step?.type === "agent" && step.capability === "review";

export const roadsFrom = (flow, id) => rows(flow?.links).filter((link) => link.from === id);
export const roadsInto = (flow, id) => rows(flow?.links).filter((link) => link.to === id);

/** The word a road takes when the person draws it without choosing one, by the step it leaves. */
export function defaultWhen(step) {
  if (step?.type === "agent") return "success";
  return step?.type === "human" ? "approved" : "always";
}

/**
 * A loop's kind, told by the roads that lead into it and never by its name: a pass loop is entered
 * by `failed` from a dispatch step, a rework loop by `changes_requested` from a gate.
 * Returns `{kind: "passes" | "rework" | "other", owner}` (owner is the step that leads into it).
 */
export function loopKind(flow, loopId) {
  for (const link of roadsInto(flow, loopId)) {
    const source = stepOf(flow, link.from);
    if (link.when === "failed" && isDispatch(source)) return {kind: "passes", owner: source.step_id};
    if (link.when === "changes_requested" && source?.type === "human") {
      return {kind: "rework", owner: source.step_id};
    }
  }
  return {kind: "other", owner: null};
}

/** The loop step entered from `ownerId` by the road of `kind`, or undefined. */
export function loopOf(flow, ownerId, kind) {
  const word = kind === "passes" ? "failed" : "changes_requested";
  const link = roadsFrom(flow, ownerId).find((road) => road.when === word
    && stepOf(flow, road.to)?.type === "loop");
  return link === undefined ? undefined : stepOf(flow, link.to);
}

/** A free id: `stem`, else `stem-2`, `stem-3`... never a reserved one and never a taken one. */
export function freshId(flow, stem) {
  const taken = new Set([...rows(flow?.steps).map((step) => step.step_id), ...RESERVED_IDS]);
  let serial = 1, id = stem;
  while (taken.has(id)) {
    serial += 1;
    id = `${stem}-${serial}`;
  }
  return id;
}

/** The nearest step above `id` along the roads for which `wanted(step)` holds, by steps' order. */
export function nearestAbove(flow, id, wanted) {
  const order = new Map(rows(flow?.steps).map((step, at) => [step.step_id, at]));
  const seen = new Set([id]);
  let layer = [id];
  while (layer.length > 0) {
    const above = [];
    for (const name of layer) {
      for (const road of roadsInto(flow, name)) {
        if (!seen.has(road.from) && stepOf(flow, road.from)?.type !== "loop") {
          seen.add(road.from);
          above.push(road.from);
        }
      }
    }
    const found = above.filter((one) => wanted(stepOf(flow, one)))
      .sort((a, b) => order.get(a) - order.get(b));
    if (found.length > 0) return stepOf(flow, found[0]);
    layer = above;
  }
  return undefined;
}

export const isLoop = (step) => step?.type === "loop";

//: Every reason an edit gives for changing nothing, each with a message in both languages
//: (`schema.notice.<name>`); an edit answers `{flow: null, notice}` and never throws.
export const NOTICE_NAMES = Object.freeze(["step_missing", "link_missing", "connection_invalid",
  "connection_exists", "kind_unknown", "field_unknown", "field_invalid", "word_unknown",
  "word_same", "position_range", "passes_not_dispatch", "passes_range", "rework_not_human",
  "rework_range", "rework_no_step", "loop_needs_step", "title_required", "limit_steps",
  "limit_links", "reads_limit", "unchanged", "duplicated", "added", "removed"]);

/** A notice of the closed list, as an edit hands it back. */
export function notice(name, params) {
  if (!NOTICE_NAMES.includes(name)) throw new Error(`no such notice: ${name}`);
  return params === undefined ? {key: `schema.notice.${name}`}
    : {key: `schema.notice.${name}`, params};
}

/** The answer of an edit that changed nothing, and why. */
export const refused = (name, params) => ({flow: null, notice: notice(name, params)});

/** The index where a new step that is not a loop goes: after the last non-loop step's block. */
export function blockEnd(flow) {
  const at = rows(flow?.steps).findIndex((step) => isLoop(step));
  return at < 0 ? rows(flow?.steps).length : at;
}
