"use strict";
// Branches of a fork (spec 7.7): what can be drawn is several roads of one outcome leaving one
// step, and they run ONE AT A TIME, in the order of the steps (the driver takes the first ready
// step of the plan, and a grant allows one open action). This module says which steps belong to
// which branch, numbers the branches by that order, and moves a branch to the front.
//
// A fork is a step with two or more roads of the same word to steps that are not loops. A branch is
// what one such road reaches and no other road of that fork reaches: a step that two branches meet
// in (the «И» join) belongs to neither. Loops are not counted, so moving a branch never moves a loop
// out of the loops' place (spec 7.2.4). It is a walk over the flow's own roads and no rule of the
// server's: whether the flow is right is the diagnostics' business.
//
// Pure functions of a flow; the flow given is never touched.
import {isLoop, refused, roadsFrom, stepOf} from "./desk-flow-shape.js";

function reachFrom(flow, start) {
  const seen = new Set(), pending = [start];
  while (pending.length > 0) {
    const id = pending.pop();
    if (!seen.has(id)) {
      seen.add(id);
      for (const road of roadsFrom(flow, id)) pending.push(road.to);
    }
  }
  return seen;
}

function forkAt(flow, source, roads, order) {
  const reach = roads.map((road) => reachFrom(flow, road.to));
  const branches = roads.map((road, at) => {
    const others = reach.filter((_one, held) => held !== at);
    const steps = flow.steps.map((step) => step.step_id).filter((id) => reach[at].has(id)
      && !others.some((set) => set.has(id)) && !isLoop(stepOf(flow, id)));
    return {first: road.to, steps};
  }).sort((a, b) => order.get(a.first) - order.get(b.first));
  if (branches.some((branch) => !branch.steps.includes(branch.first))) return null;
  return {fork: source, when: roads[0].when,
    branches: branches.map((branch, at) => ({...branch, number: at + 1}))};
}

/**
 * The forks of a flow, in the order of their steps: `{fork, when, branches: [{number, first,
 * steps}]}` with the branches in the order they will run. A fork whose branches do not each own the
 * step their road enters is not numbered (its shape is not one the desk draws).
 */
export function forksOf(flow) {
  const order = new Map(flow.steps.map((step, at) => [step.step_id, at]));
  const found = [];
  for (const step of flow.steps.filter((one) => !isLoop(one))) {
    const byWord = new Map();
    for (const road of roadsFrom(flow, step.step_id)) {
      if (!isLoop(stepOf(flow, road.to)) && order.has(road.to)) {
        byWord.set(road.when, [...(byWord.get(road.when) ?? []), road]);
      }
    }
    for (const roads of byWord.values()) {
      const fork = roads.length > 1 ? forkAt(flow, step.step_id, roads, order) : null;
      if (fork !== null) found.push(fork);
    }
  }
  return found;
}

/**
 * What each step of a branch is called on the schema: `{branch, waiting, fork}` by step id, for the
 * outermost fork a step belongs to. `waiting` is true for every branch but the first.
 */
export function branchMarks(flow) {
  const marks = new Map();
  for (const fork of forksOf(flow)) {
    for (const branch of fork.branches) {
      for (const id of branch.steps) {
        if (!marks.has(id)) {
          marks.set(id, {branch: branch.number, waiting: branch.number > 1, fork: fork.fork});
        }
      }
    }
  }
  return marks;
}

/**
 * The branch a step stands in, for the outermost fork it belongs to (the one `branchMarks` marks):
 * `{fork, number, of, waiting}`, or null for a step in no branch.
 */
export function branchOf(flow, id) {
  for (const fork of forksOf(flow)) {
    const branch = fork.branches.find((one) => one.steps.includes(id));
    if (branch !== undefined) {
      return {fork: fork.fork, number: branch.number, of: fork.branches.length,
        waiting: branch.number > 1};
    }
  }
  return null;
}

/** «Сначала эта ветка»: the steps of the branch `id` stands in move before the first branch's. */
export function branchFirst(flow, id) {
  const forks = forksOf(flow);
  const fork = forks.find((one) => one.branches.some((branch) => branch.steps.includes(id)));
  if (fork === undefined) return refused("step_missing");
  const branch = fork.branches.find((one) => one.steps.includes(id));
  if (branch.number === 1) return refused("unchanged");
  const moved = flow.steps.filter((step) => branch.steps.includes(step.step_id));
  const rest = flow.steps.filter((step) => !branch.steps.includes(step.step_id));
  const head = fork.branches[0].steps;
  const start = rest.findIndex((step) => head.includes(step.step_id));
  return {flow: {...flow, steps: [...rest.slice(0, start), ...moved, ...rest.slice(start)]},
    notice: ""};
}
