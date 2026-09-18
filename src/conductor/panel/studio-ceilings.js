"use strict";
// The two ceilings a workflow step may place on itself, and what a person may
// put in a ceiling field.
//
// Split out of `studio-model.js` when that module reached the project's line
// cap with the task binding owed, along the seam the two halves already had:
// everything else in the boundary judges a PAYLOAD the server sent, and these
// two judge a value a person TYPED. The edits and the inspector's sections
// read them from here now, and the boundary does not re-export them -- a
// re-export would make it import this module, and it imports nothing by
// contract.
//
// This module imports nothing for the boundary's own reason: a judge that
// could reach a neighbour could answer from something other than the value it
// was given.

//: The two ceilings a workflow step may place on itself, and the ranges
//: `graph_definition.settled_bounds` holds them to. A vocabulary rather than a
//: rule of this window's own: the numbers are the Python contract's, and
//: `tests/test_studio_canvas.py` pins them to it in both directions.
//:
//: The empty field means ABSENT and never zero. "This step has no limit" and
//: "this step may run for no time at all" are different sentences, and only
//: one of them is a plan.
export const CEILINGS = Object.freeze({
  timeout_seconds: Object.freeze({min: 1, max: 86400,
    what: "a timeout in seconds"}),
  attempt_bound: Object.freeze({min: 1, max: 99, what: "an attempt bound"}),
});

//: What a person may put in a ceiling field, judged by the vocabulary above.
//: Here rather than in the reducer because it moves no state: given a node and
//: a typed value it answers the same way forever, which is what everything in
//: the boundary it left does. The window refuses out of range at the FIELD so a
//: person is told there rather than at a publish.
export function withCeiling(node, name, value) {
  const rule = CEILINGS[name];
  const raw = typeof value === "string" ? value.trim() : "";
  if (raw === "") {
    const {[name]: _dropped, ...rest} = node;
    return {node: rest, notice: ""};
  }
  const number = Number(raw);
  if (!Number.isInteger(number) || number < rule.min || number > rule.max) {
    return {node, notice: `${rule.what} is a whole number from ${rule.min} `
      + `to ${rule.max}, or empty for no limit.`};
  }
  return {node: {...node, [name]: number}, notice: ""};
}
