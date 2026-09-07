"use strict";
// Which writes on the Runs screen are in flight, and until when.
//
// Split out of `studio-store.js` at the line cap, along the seam the step
// draft's own comment already drew: a write in flight is not a fact about the
// draft at all. It is a fact about ONE step -- or the document -- of ONE run,
// keyed by both in `runs.writes`, and membership there is what holds a control
// shut. What moved here is the whole of that map's rule: when an entry
// appears, what it says while it stands, and the two ends that take it away.
//
// TWO ENDS, because one was not enough (R07 of the review of `8dec0e4`, as
// the slice-3 review found it): the accepted write's entry left the map the
// moment the server answered, so the control was redrawn over the stale
// screen -- the step still runnable, the accepting read not yet landed -- and
// stayed shut only because the spent draft left a required field empty. A
// draft NOT spent, which is every draft with a word typed after the press,
// opened it to a second press and a second durable record. So an ACCEPTED
// write stays in the map, marked answered, until the run it wrote to has been
// read again; every other end -- refused, retired, unknown, never sent --
// removes it at once, which is what gives a person their words and the
// control back. The sentence beside the shut control has always said exactly
// this: "until the server answers and this run has been read again".
//
// It touches no DOM and imports nothing.

//: What an entry says: the request is on the wire, or the server accepted it
//: and this run has not been read since. The value is read by the two arms
//: below and nowhere else -- a control asks only whether the entry stands.
export const ON_THE_WIRE = "writing";
export const ANSWERED = "answered";

function named(event) {
  return typeof event.runId === "string" && typeof event.nodeId === "string";
}

function keyOf(event) {
  return `${event.runId}/${event.nodeId}`;
}

function moved(state, writes) {
  return Object.freeze({...state, runs: Object.freeze({...state.runs,
    writes: Object.freeze(writes)})});
}

/**
 * A write begins, or ends on any road but the accepted one.
 *
 * `writing: true` records the request under its run and step before it
 * leaves; `writing: false` is the write's own end and removes the entry --
 * unless the accepted road has already marked it answered, in which case the
 * entry is the next read's to remove. No read, no change of run and no change
 * of draft reaches this map.
 *
 * @param {object} state The reducer's frozen value.
 * @param {object} event `{runId, nodeId, writing}`.
 * @returns {object} The next state, or the same one when nothing moved.
 */
export function stepWriting(state, event) {
  if (!named(event)) return state;
  const writes = {...state.runs.writes};
  const held = keyOf(event);
  if (event.writing === true) writes[held] = ON_THE_WIRE;
  else if (writes[held] === ON_THE_WIRE) delete writes[held];
  else return state;
  return moved(state, writes);
}

/**
 * The accepted road: the server answered, and the control stays shut.
 *
 * The entry is marked answered rather than removed, so the control drawn
 * over the stale screen is still shut and still says why; the landed read of
 * this run is what removes it (`readWrites`). An entry that is not on the
 * wire -- already ended, never recorded -- is left alone.
 *
 * @param {object} state The reducer's frozen value.
 * @param {object} event `{runId, nodeId}`.
 * @returns {object} The next state, or the same one when nothing moved.
 */
export function stepAnswered(state, event) {
  if (!named(event)) return state;
  const held = keyOf(event);
  if (state.runs.writes[held] !== ON_THE_WIRE) return state;
  return moved(state, {...state.runs.writes, [held]: ANSWERED});
}

/**
 * A landed read of one run: every answered write of THAT run is over.
 *
 * A run id admits no `/` (`contract_values._id`), so the prefix names one
 * run and no other. Writes still on the wire, and every write of another
 * run, stay exactly where they are: a read says nothing about them.
 *
 * @param {object} writes The map as it stands.
 * @param {string} runId The run the read was of.
 * @returns {object} The map with that run's answered entries removed, frozen.
 */
export function readWrites(writes, runId) {
  const kept = {};
  for (const [held, value] of Object.entries(writes)) {
    if (value !== ANSWERED || !held.startsWith(`${runId}/`)) kept[held] = value;
  }
  return Object.freeze(kept);
}
