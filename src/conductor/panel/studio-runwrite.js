"use strict";
// The two writes that drive one step of a planned run, and the two edits that
// fill in what they carry.
//
// Lifted out of `studio.js` when that module reached the project's line cap,
// along a seam the boot module's own head already draws: transport is one
// thing and what a Human's press MEANS is another. What moved here is the
// meaning -- which draft is spent when, which refusals buy a re-read, what each
// write announces afterwards. What did NOT move is the wire: every `fetch(`,
// the one stream and the one `method: "POST"` are still the boot module's, are
// still counted there, and are unreachable from this file. It is handed a
// `write` and calls it, exactly as a control is handed a handler and calls it.
//
// It composes no body either. The CONTROL builds those, out of the plan node
// the schedule chose and the two facts a person typed; everything here is
// about what happens AROUND the request.
import {PROPOSED_NOTE, READ_AGAIN, REQUESTED_NOTE, STEP_MOVED}
  from "./studio-runstep.js";

/**
 * The four callbacks the Runs screen's step controls are handed.
 *
 * @param {object} door What this module may use and the whole of it:
 *   `write(target, subject, body, carry, recover)` -- the boot module's one
 *   mutation door; `refreshRun(runId)`; `dispatch(event)`; `said(code)`, the
 *   refusal vocabulary; `isId(value)`; and `chosenRun()`, which is a GETTER
 *   because the answer moves -- a value copied here would answer for whichever
 *   run was chosen when this was built.
 * @returns {object} `chooseStep`, `editStep`, `proposeStep`, `confirmStep`.
 */
export function stepWriters(door) {
  //: Both halves of driving one step, which are one shape. The draft is MARKED
  //: before the request goes out and never destroyed: a proposal's identity is
  //: minted by the server, so a second press is a second proposal -- and a
  //: refusal that brings no read must still give the person their words back.
  //: The accepted road SPENDS it, because that is the one road that knows they
  //: are finished with.
  function onStepWrite(target, row, notice) {
    if (!row || !door.isId(row.runId) || !row.body) return;
    const asked = row.runId;
    door.dispatch({type: "step-writing", writing: true});
    door.write(target, asked, row.body, () => {
      if (asked !== door.chosenRun()) return;
      door.dispatch({type: "status", notice});
      door.dispatch({type: "step-chosen", nodeId: null});
      door.refreshRun(asked);
    }, (result) => {
      if (!STEP_MOVED.includes(result.code)
          || asked !== door.chosenRun()) return;
      door.dispatch({type: "status",
        notice: `${door.said(result.code)} ${READ_AGAIN}`});
      door.refreshRun(asked);
    // Whatever became of it -- accepted, refused, retired by another write, or
    // never sent because the line was down -- this write is over and the
    // control comes back. `write` resolves on every one of those roads, so
    // this is the one exit all of them share.
    }).finally(() => door.dispatch({type: "step-writing", writing: false}));
  }

  return Object.freeze({
    chooseStep: (nodeId) => door.dispatch({type: "step-chosen", nodeId}),
    editStep: (patch) => door.dispatch({type: "step-edit", patch}),
    proposeStep: (row) => onStepWrite("proposals", row, PROPOSED_NOTE),
    confirmStep: (row) => onStepWrite("actions", row, REQUESTED_NOTE),
  });
}
