"use strict";
// The flow as the canvas draws it, and the summary of what a publication changes (spec 5.6.3, 7.4,
// 7.7).
//
// The canvas draws two lists, steps and roads (`studio-canvas.js`). `flowGraph` turns a flow into
// them: an agent is a task, a gate of the person is a gate, a loop is a loop, and each road carries its
// word. It adds only what the flow's own facts say: the branch a step belongs to and whether it waits
// its turn (7.7), the word of a road (except `success`, the road nobody needs told), and the mark a
// diagnostic row leaves at its address (7.4): a step, a road or a loop. Nothing here is a rule of the
// server's or a number of its own; the words to say come from the caller.
//
// `changeSummary` compares the flow being edited with the last revision's, so the confirmation before
// a revision names what will change in something that can never be changed.
//
// Pure functions; a flow given is never touched.
import {branchMarks} from "./desk-flow-branches.js";
import {canonical} from "./desk-flow-shape.js";

const KIND = Object.freeze({agent: "task", route: "task", human: "gate", loop: "loop"});
const WORSE = Object.freeze({error: 2, warning: 1});
const roadKey = (from, to) => `${from} ${to}`;

function raise(map, id, severity) {
  const held = map.get(id);
  if (held === undefined || WORSE[severity] > WORSE[held]) map.set(id, severity);
}

/**
 * Where the rows of the diagnostics land: `steps` (by step id; a loop is a step) and `links` (by
 * `"<from> <to>"`, the name the canvas gives a road), each with the worse severity of its rows.
 * A row with no address, or an address the flow does not have, marks nothing here.
 */
export function diagnosticMarks(rows) {
  const steps = new Map(), links = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const at = row?.at;
    if (!Object.hasOwn(WORSE, row?.severity)) continue;
    if (typeof at?.step_id === "string") raise(steps, at.step_id, row.severity);
    else if (Array.isArray(at?.link) && at.link.length === 3) {
      raise(links, roadKey(at.link[0], at.link[1]), row.severity);
    }
  }
  return {steps, links};
}

const markOf = (severity, words) => ({severity, text: words.severity?.[severity] ?? severity});

function nodeOf(step, words, marks, branches) {
  const node = {node_id: step.step_id, kind: KIND[step.type],
    title: words.title === undefined ? step.title ?? step.step_id : words.title(step)};
  if (step.type === "agent") {
    node.role_id = step.role_id;
    node.capability = step.capability;
  }
  if (step.type === "loop") node.loop = {bound: step.bound, back_to: step.back_to};
  if (step.position !== null) node.position = {...step.position};
  const branch = branches.get(step.step_id);
  if (branch !== undefined) {
    node.badge = String(branch.branch);
    if (branch.waiting) node.note = words.waiting ?? "";
  }
  const severity = marks.steps.get(step.step_id);
  if (severity !== undefined) node.mark = markOf(severity, words);
  return node;
}

function edgeOf(link, words, marks) {
  const edge = {from_node: link.from, to_node: link.to, when: link.when,
    label: link.when === "success" ? null : words.when?.(link.when) ?? link.when};
  const severity = marks.links.get(roadKey(link.from, link.to));
  if (severity !== undefined) edge.mark = markOf(severity, words);
  return edge;
}

/**
 * The two lists the canvas draws. `words` says the desk's words: `title(step)` (the name of a step),
 * `when(word)` (the name of a road's word), `waiting` (the note of a branch that waits its turn) and
 * `severity` (the name of each severity). `rows` are the server's diagnostics.
 */
export function flowGraph(flow, words = {}, rows = []) {
  const marks = diagnosticMarks(rows), branches = branchMarks(flow);
  return {nodes: flow.steps.map((step) => nodeOf(step, words, marks, branches)),
    edges: flow.links.map((link) => edgeOf(link, words, marks))};
}

// -- what a publication changes ----------------------------------------------------------

//: The names of the fields in which two steps differ; a key of `ext` is named `ext.<key>`.
function differing(before, after) {
  const names = [];
  for (const name of Object.keys({...before, ...after})) {
    if (name === "ext") {
      const keys = Object.keys({...before.ext, ...after.ext});
      names.push(...keys.filter((key) => canonical(before.ext[key]) !== canonical(after.ext[key])
        || Object.hasOwn(before.ext, key) !== Object.hasOwn(after.ext, key))
        .map((key) => `ext.${key}`));
    } else if (canonical(before[name]) !== canonical(after[name])) names.push(name);
  }
  return names;
}

function stepRows(before, after) {
  const held = new Map(before.steps.map((step) => [step.step_id, step]));
  const now = new Map(after.steps.map((step) => [step.step_id, step]));
  const rows = [...held.keys()].filter((id) => !now.has(id)).map((id) => ({kind: "step_removed", id}));
  rows.push(...[...now.keys()].filter((id) => !held.has(id)).map((id) => ({kind: "step_added", id})));
  for (const [id, step] of now) {
    const fields = held.has(id) ? differing(held.get(id), step) : [];
    if (fields.length > 0) rows.push({kind: "step_changed", id, fields});
  }
  return rows;
}

function linkRows(before, after) {
  const held = new Map(before.links.map((link) => [roadKey(link.from, link.to), link]));
  const now = new Map(after.links.map((link) => [roadKey(link.from, link.to), link]));
  const at = (link) => ({from: link.from, to: link.to});
  const rows = [...held].filter(([key]) => !now.has(key))
    .map(([, link]) => ({kind: "link_removed", ...at(link), when: link.when}));
  rows.push(...[...now].filter(([key]) => !held.has(key))
    .map(([, link]) => ({kind: "link_added", ...at(link), when: link.when})));
  for (const [key, link] of now) {
    if (held.has(key) && held.get(key).when !== link.when) {
      rows.push({kind: "link_changed", ...at(link), before: held.get(key).when, after: link.when});
    }
  }
  return rows;
}

//: The steps both flows have, in the order each has them.
function reordered(before, after) {
  const common = new Set(before.steps.map((step) => step.step_id));
  const shared = (flow) => flow.steps.map((step) => step.step_id)
    .filter((id) => new Set(after.steps.map((row) => row.step_id)).has(id) && common.has(id));
  return canonical(shared(before)) !== canonical(shared(after));
}

/**
 * What differs between the flow being edited and the last revision's (null: there is none, and
 * every step and road is new). Rows: `flow_title`, `flow_contract`, `step_removed`, `step_added`,
 * `step_changed` (with the names of the fields), `link_removed`, `link_added`, `link_changed` and
 * `order` (the steps stand in another order, which decides which branch runs first).
 */
export function changeSummary(flow, revisionFlow) {
  const before = revisionFlow ?? {title: flow.title, steps: [], links: [], ext: flow.ext};
  const rows = [];
  if (before.title !== flow.title) {
    rows.push({kind: "flow_title", before: before.title, after: flow.title});
  }
  if (canonical(before.ext) !== canonical(flow.ext)) rows.push({kind: "flow_contract"});
  rows.push(...stepRows(before, flow), ...linkRows(before, flow));
  if (reordered(before, flow)) rows.push({kind: "order"});
  return rows;
}
