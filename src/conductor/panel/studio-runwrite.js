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
import {DOCUMENT_KEY, PUBLISHED_NOTE} from "./studio-rundocs.js";
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
  //: Both halves of driving one step, which are one shape. The write is
  //: RECORDED before the request goes out, against the run and the step it
  //: is for, and the draft is never destroyed: a proposal's identity is
  //: minted by the server, so a second press is a second proposal -- and a
  //: refusal that brings no read must still give the person their words back.
  //: The accepted road SPENDS the draft, because that is the one road that
  //: knows they are finished with -- and only the draft this write was
  //: minted from, so another step's unsent words survive its answer.
  function onStepWrite(target, row, notice) {
    if (!row || !door.isId(row.runId) || !row.body) return;
    const asked = row.runId;
    //: What this write OWNS, fixed before the request leaves: the run, the
    //: step, and the generation of the draft it carries.
    const spent = {runId: asked, nodeId: row.nodeId,
      generation: row.generation};
    door.dispatch({type: "step-writing", ...spent, writing: true});
    door.write(target, asked, row.body, () => {
      // The run was written to whether or not the person is still looking at
      // it, and its next read is what gives the control back: an answered
      // write's control is shut until then, said first and unconditionally.
      door.dispatch({type: "step-answered", runId: asked, nodeId: row.nodeId});
      if (asked !== door.chosenRun()) return;
      door.dispatch({type: "status", notice});
      door.dispatch({type: "step-spent", ...spent});
      door.refreshRun(asked);
    }, (result) => {
      if (!STEP_MOVED.includes(result.code)
          || asked !== door.chosenRun()) return;
      door.dispatch({type: "status",
        notice: `${door.said(result.code)} ${READ_AGAIN}`});
      door.refreshRun(asked);
    // Whatever became of it -- accepted, refused, retired by a dropped stream,
    // or never sent because the line was down -- this write is over. `write`
    // resolves on every one of those roads, so this is the one exit all of
    // them share; on every road but the accepted one it is also what gives
    // the control back, and on that one the run's next read is.
    }).finally(() => door.dispatch({type: "step-writing", ...spent,
      writing: false}));
  }

  return Object.freeze({
    chooseStep: (nodeId) => door.dispatch({type: "step-chosen", nodeId}),
    editStep: (patch) => door.dispatch({type: "step-edit", patch}),
    proposeStep: (row) => onStepWrite("proposals", row, PROPOSED_NOTE),
    confirmStep: (row) => onStepWrite("actions", row, REQUESTED_NOTE),
  });
}

//: What an accepted decision MEANS, said by the window after it lands.
export const DECIDED = "The decision is a durable receipt in this run's journal. "
  + "Nothing was executed by answering.";

/**
 * The one callback the Decisions screen's form is handed.
 *
 * Lifted out of the boot module at its line cap, along the seam the step and
 * document roads were: a decision is a receipt, and its identity is the
 * caller's -- the window mints one from the gate and the deciding person so a
 * lost reply re-sends the same identity and the route answers idempotently
 * instead of writing a second receipt for one answer.
 *
 * @param {object} door What `stepWriters` is handed, plus `draft()`, a GETTER
 *   for the decision draft, for the reason `chosenRun` is one.
 * @returns {object} `submitDecision`.
 */
export function decisionWriters(door) {
  function onSubmitDecision(row) {
    const draft = door.draft();
    if (!row || !door.isId(row.run_id) || !door.isId(row.gate_id)
        || !door.isId(draft.actor)) {
      door.dispatch({type: "status",
        notice: "Name the deciding person before recording a decision."});
      return;
    }
    // WHICH receipt this answer replaces, or none. A gate askable again while
    // a receipt still stands is a reopened lap, and a window that always sent
    // `null` there wrote a SECOND standing answer: the projection then refuses
    // to choose between them and the gate reads `unknown` -- which is how the
    // result gate became unreadable the moment a person answered it twice.
    const supersedes = typeof row.standing === "string" ? row.standing : null;
    // The identity this answer carries. It must be DERIVABLE, so a lost reply
    // re-sends the same one and the route answers idempotently -- but the gate
    // and the person alone can be spelled once, so a second answer on a
    // reopened gate collided with the first and was refused as a conflict.
    //
    // The count of answers already durable is the third fact, and it is always
    // present and stands BEFORE the actor. A suffix would collide across
    // people: `bob-1` answering first writes the same id as `bob` answering
    // second. Nothing may follow the actor, because an actor is the one part
    // of this id a person chooses.
    const answered = Number.isInteger(row.answers) ? row.answers : 0;
    const body = {
      receipt_id: `receipt-${row.gate_id}-${answered}-${draft.actor}`,
      gate_id: row.gate_id, action: draft.action, actor: draft.actor,
      reason: typeof draft.reason === "string" ? draft.reason.trim() : "",
      scope_refs: [], evidence_refs: [], supersedes};
    const asked = row.run_id;
    // Both roads below SPEND the draft before the read they provoke. A landed
    // read of the same run keeps what is typed -- it has no way to know the
    // words are finished with -- so the two places that do know say so.
    door.write("decisions", asked, body, () => {
      if (asked !== door.chosenRun()) return;
      door.dispatch({type: "status", notice: DECIDED});
      door.dispatch({type: "decision-chosen", key: null});
      door.refreshRun(asked);
    }, (result) => {
      // The one refusal a decision can meet that this window acts on rather
      // than only reports, and the recovery is `draft_conflict`'s shape for
      // `draft_conflict`'s reason: the screen is offering an answer for a gate
      // the server says the run has not reached, so what is on screen is out
      // of date. The read is what makes it current again.
      if (result.code !== "gate_unreached" || asked !== door.chosenRun()) return;
      door.dispatch({type: "decision-chosen", key: null});
      door.refreshRun(asked);
    });
  }

  return Object.freeze({submitDecision: onSubmitDecision});
}

/**
 * The two callbacks the Runs screen's document form is handed.
 *
 * The same shape as a step write and the same door: the write is recorded
 * under the run and the document key before the request leaves, the accepted
 * road spends only the draft it was minted from and re-reads the run, a
 * refusal that says the screen is stale re-reads it too, and the write's own
 * end is the one thing that gives the control back.
 *
 * @param {object} door What `stepWriters` is handed, and the whole of it.
 * @returns {object} `editDocument`, `publishDocument`.
 */
export function documentWriters(door) {
  function onDocumentWrite(row) {
    if (!row || !door.isId(row.runId) || !row.body) return;
    const asked = row.runId;
    const spent = {runId: asked, nodeId: DOCUMENT_KEY,
      generation: row.generation};
    door.dispatch({type: "step-writing", ...spent, writing: true});
    door.write("artifacts", asked, row.body, () => {
      door.dispatch({type: "step-answered", runId: asked, nodeId: DOCUMENT_KEY});
      if (asked !== door.chosenRun()) return;
      door.dispatch({type: "status", notice: PUBLISHED_NOTE});
      door.dispatch({type: "document-spent", runId: asked,
        generation: row.generation});
      door.refreshRun(asked);
    }, (result) => {
      if (!STEP_MOVED.includes(result.code)
          || asked !== door.chosenRun()) return;
      door.dispatch({type: "status",
        notice: `${door.said(result.code)} ${READ_AGAIN}`});
      door.refreshRun(asked);
    }).finally(() => door.dispatch({type: "step-writing", ...spent,
      writing: false}));
  }

  return Object.freeze({
    editDocument: (patch) => door.dispatch({type: "document-edit", patch}),
    publishDocument: onDocumentWrite,
  });
}
