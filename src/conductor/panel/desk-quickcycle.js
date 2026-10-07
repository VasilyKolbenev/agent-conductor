"use strict";
// The quick straight-line mode of the «Схема» (spec 5.6.3, 7.2.4): a list of role kinds becomes a
// cycle, one step after the other, closed by the step that is the person's.
//
// It writes with the edits of `desk-flow-edits.js` and with nothing else: it declares no vocabulary
// of its own (the desk keeps exactly three copies of the words of an edit) and holds no rule about
// what a good cycle is (the server's diagnostics say that). So the flow built here is the flow the
// canvas builds by the same adds, and the two can be compared step by step.
//
// A pure function of its two arguments; the list given is never touched.
import {applyEdit} from "./desk-flow-edits.js";
import {emptyFlow} from "./desk-flow-shape.js";

//: The kinds a row may name: the six of spec 7.2.2 and a custom role.
export const QUICK_KINDS = Object.freeze(["analyst", "designer", "diagnostician", "reviewer",
  "doer", "tester", "custom"]);
//: What the mode says when it builds nothing, each with a message in both languages
//: (`schema.quick.<name>`); a refusal of an edit keeps that edit's own notice.
export const QUICK_NOTICES = Object.freeze(["empty", "kind_unknown"]);

function refused(name) {
  return {flow: null, notice: {key: `schema.quick.${name}`}};
}

/**
 * The flow of a straight line of steps, each after the one before, and a decision step at the end.
 * Answers `{flow, notice}`; `flow` is null (and `notice` says why) for a list that is empty or is
 * not a list, a row that is no kind, or an edit the flow refuses (its step limit).
 */
export function quickFlow(title, kinds) {
  if (!Array.isArray(kinds) || kinds.length === 0) return refused("empty");
  if (!kinds.every((kind) => QUICK_KINDS.includes(kind))) return refused("kind_unknown");
  let flow = emptyFlow(title), last = null;
  for (const roleKind of kinds) {
    const out = applyEdit(flow, {type: "add", kind: "agent", roleKind, afterId: last});
    if (out.flow === null) return {flow: null, notice: out.notice};
    flow = out.flow;
    last = out.added;
  }
  const done = applyEdit(flow, {type: "add", kind: "human", afterId: last});
  return done.flow === null ? {flow: null, notice: done.notice} : {flow: done.flow, notice: ""};
}
