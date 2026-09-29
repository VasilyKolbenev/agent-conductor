"use strict";
// The two forms the editor builds and keeps for loops (spec 7.2.4), and the order of the steps.
//
// Passes of a dispatch step `S`, `p >= 2`: a loop step `<S>-fix {back_to, bound: p}` and a road
// `S -> <S>-fix` by `failed`; `back_to` is `S` itself, or, for a tester, the nearest dispatch step
// above it. `p = 1` removes the pair. Rework of a gate `G`: a loop step `{back_to: a step above G,
// bound: 2..8}` and a road `G -> loop` by `changes_requested`. The steps stand in this order: the
// steps of agents, gates and routes, then the rework loops, then the pass loops (the reason is the
// arithmetic of spec 7.5: a step in two loops lives by the one that demands more laps, and a tie
// goes to the one that stands earlier).
//
// Pure functions of a flow: a flow in, `{flow, notice}` out (`flow` is null when nothing changed),
// and the flow given is never touched.
import {LIMITS, freshId, isDispatch, isLoop, kindOfRole, loopKind, loopOf, nearestAbove, notice,
  refused, stepOf} from "./desk-flow-shape.js";

//: An edit that would change nothing says so, and says nothing more.
const NOTHING = Object.freeze({flow: null, notice: notice("unchanged")});

function whole(value, range) {
  return Number.isInteger(value) && value >= range.min && value <= range.max;
}

//: The flow without one step and every road that touches it.
export function withoutStep(flow, id) {
  return {...flow, steps: flow.steps.filter((step) => step.step_id !== id),
    links: flow.links.filter((link) => link.from !== id && link.to !== id)};
}

function withBound(flow, id, bound) {
  return {...flow, steps: flow.steps.map((step) => (step.step_id === id ? {...step, bound}
    : step))};
}

//: Where a rework loop goes: before the first pass loop, so the rework loops come first.
export function reworkIndex(flow) {
  const at = flow.steps.findIndex((step) => isLoop(step)
    && loopKind(flow, step.step_id).kind === "passes");
  return at < 0 ? flow.steps.length : at;
}

function loopStep(id, backTo, bound) {
  return {step_id: id, type: "loop", title: null, purpose: null, position: null,
    timeout_seconds: null, back_to: backTo, bound, ext: {}};
}

//: A new loop of `kind` entered from `ownerId`; `at` is where in `steps` it stands.
function withLoop(flow, ownerId, kind, backTo, bound) {
  const id = freshId(flow, `${ownerId}-${kind === "passes" ? "fix" : "rework"}`);
  const at = kind === "passes" ? flow.steps.length : reworkIndex(flow);
  const link = {from: ownerId, to: id, when: kind === "passes" ? "failed" : "changes_requested"};
  return {...flow, steps: [...flow.steps.slice(0, at), loopStep(id, backTo, bound),
    ...flow.steps.slice(at)], links: [...flow.links, link]};
}

/** Where the passes of a dispatch step return to (spec 7.2.4, 7.6). */
export function homeOfPasses(flow, id) {
  if (kindOfRole(stepOf(flow, id)?.role_id) !== "tester") return id;
  return nearestAbove(flow, id, isDispatch)?.step_id ?? id;
}

//: The step a gate's rework returns to: the nearest dispatch step above it, else the nearest agent.
function reworkHome(flow, gateId) {
  return (nearestAbove(flow, gateId, isDispatch) ?? nearestAbove(flow, gateId,
    (step) => step?.type === "agent"))?.step_id;
}

/** Set the passes of a dispatch step: 2 or more build (or resize) the pair, 1 removes it. */
export function withPasses(flow, id, value) {
  if (!isDispatch(stepOf(flow, id))) return refused("passes_not_dispatch");
  if (!whole(value, LIMITS.bound)) {
    return refused("passes_range", {min: String(LIMITS.bound.min), max: String(LIMITS.bound.max)});
  }
  const held = loopOf(flow, id, "passes");
  if (value === 1) return held === undefined ? NOTHING
    : {flow: withoutStep(flow, held.step_id), notice: ""};
  if (held !== undefined) {
    return held.bound === value ? NOTHING : {flow: withBound(flow, held.step_id, value), notice: ""};
  }
  return {flow: withLoop(flow, id, "passes", homeOfPasses(flow, id), value), notice: ""};
}

/** Set the rework of a gate: 2..8 build (or resize) the loop, null removes it. */
export function withRework(flow, id, value) {
  if (stepOf(flow, id)?.type !== "human") return refused("rework_not_human");
  const held = loopOf(flow, id, "rework");
  if (value === null || value === 0) return held === undefined ? NOTHING
    : {flow: withoutStep(flow, held.step_id), notice: ""};
  if (!whole(value, LIMITS.rework)) {
    return refused("rework_range", {min: String(LIMITS.rework.min), max: String(LIMITS.rework.max)});
  }
  if (held !== undefined) {
    return held.bound === value ? NOTHING : {flow: withBound(flow, held.step_id, value), notice: ""};
  }
  const home = reworkHome(flow, id);
  if (home === undefined) return refused("rework_no_step");
  return {flow: withLoop(flow, id, "rework", home, value), notice: ""};
}

const RANK = Object.freeze({rework: 0, other: 1, passes: 2});

/**
 * The fix of `loop_order`: every rework loop stands before every pass loop. Only loops move, and
 * only among the places loops already stand in, so no other step changes its place.
 */
export function putReworkFirst(flow) {
  const places = [];
  flow.steps.forEach((step, at) => { if (isLoop(step)) places.push(at); });
  const rank = (step) => RANK[loopKind(flow, step.step_id).kind];
  const sorted = places.map((at) => flow.steps[at])
    .map((step, held) => [step, held]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1])
    .map(([step]) => step);
  const steps = [...flow.steps];
  places.forEach((at, held) => { steps[at] = sorted[held]; });
  const moved = steps.some((step, at) => step !== flow.steps[at]);
  return moved ? {flow: {...flow, steps}, notice: ""} : NOTHING;
}
