"use strict";
//: The Runs screen's closed vocabularies, each a copy of exactly one Python
//: owner, and the one sentence the outcome word may never appear without.
//:
//: Split out of `studio-runs.js` when that module crossed the project's line
//: cap, along the seam that module's own section header already drew: a
//: vocabulary is a self-contained circuit and the rendering that spends it is
//: not. The same seam `graph_values` and `graph_schedule_values` were taken
//: along one layer down, for the same reason.
//:
//: It imports nothing, and cannot: every name here is a word this build must
//: hold equal to a Python owner, and a module that could reach a neighbour
//: could answer from something other than the list it was given. The parity
//: guards read THIS file and the Python module side by side, so a word added on
//: either side and not the other still reds.
//:
//: `studio-runs.js` imports every name back under its old spelling.

// -- closed vocabularies, each a copy of exactly one Python owner ------------
//
// Held equal to their owners by tests/test_studio_runs.py, which reads this
// source and the Python module side by side. A word added on either side and
// not the other reds that module.

//: graph_projection.NODE_PHASES -- how far a node's CURRENT action got. Read
//: `observed` as "a boundary was reached", never as success: the outcome is a
//: separate word from a separate record (safety law 9).
export const NODE_PHASES = Object.freeze(
  ["idle", "proposed", "requested", "running", "observed"]);
//: graph_projection.GATE_STATES. `unknown` is the projection refusing to
//: choose between two standing receipts, not a soft pending.
export const GATE_STATES = Object.freeze(
  ["idle", "satisfied", "failed", "changes_requested", "waived", "unknown"]);
//: contract_values._RESULT_OUTCOMES -- what an ActionResultReceipt may say.
export const RESULT_OUTCOMES = Object.freeze(
  ["cancelled", "failed", "rejected", "succeeded", "unknown",
    "verification_failed"]);
//: contract_values._VERIFICATION_STATES -- what an EvidenceRef may say.
export const VERIFICATION_STATES = Object.freeze(
  ["error", "mismatch", "unavailable", "unverified", "verified"]);
//: contract_values._RUN_STATES -- the words a RunEnvelope's status may hold.
export const RUN_STATES = Object.freeze(
  ["active", "blocked", "cancelled", "complete", "created", "failed",
    "paused", "unknown"]);
//: attempts.ATTEMPT_PHASES -- the two durable boundaries of one attempt.
export const ATTEMPT_PHASES = Object.freeze(
  ["effect_lease", "execution_observed"]);
//: run_store._RECORDS -- every record kind a run directory may hold, with the
//: plain-language name this screen puts beside the protocol word. The keys are
//: the contract; the values are prose and are never parsed.
export const RECORD_KINDS = Object.freeze({
  action_proposal: "A lane proposed an action",
  action_request: "A Human authorized one request",
  action_result: "A result was observed",
  adapter_observation: "An adapter reported its health",
  artifact: "An artifact was written",
  attempt_event: "An attempt crossed a durable boundary",
  decision: "A Human answered a gate",
  evidence: "Evidence was claimed",
  graph_definition: "The run was given its plan",
  run_terminal: "The plan has nothing left to open",
});
//: `artifacts.ARTIFACT_MEDIA_TYPES` and `artifacts.ARTIFACT_CONTENT_LIMIT`:
//: the two closed facts a document a person publishes is held to at the
//: boundary, copied here so the form can refuse beside the person.
export const ARTIFACT_MEDIA_TYPES = Object.freeze(["text/markdown", "text/plain"]);
export const ARTIFACT_CONTENT_LIMIT = 49152;
//: What a control says while its own write is in flight. Said by two
//: fragments -- the step controls and the document form -- so it is declared
//: once here, as every sentence two files say is.
//
// The draft is NOT destroyed at the door. A refusal that does not re-read --
// the line down, a body the boundary refuses, a session that rotated -- must
// give the control back with what was typed still in it. So the shut state is
// a fact about the WRITE, and it is what makes a second press impossible.
export const WRITING_NOTE = "Writing… this control is shut until the server "
  + "answers and this run has been read again. What you have typed here is "
  + "kept.";
//: contract_values.ControlMode -- the whole authority ladder, and what each
//: rung PERMITS. There is no hidden autonomous rung.
export const CONTROL_MODES = Object.freeze({
  observe: "Reads and reports. Nothing is proposed and nothing runs.",
  propose: "May propose work. Nothing can be authorized in this run, so "
    + "nothing runs.",
  confirm: "A Human confirms each proposal, and only then may it run.",
  policy: "Reserved: this build ships no policy executor. A policy run behaves "
    + "as a propose run: nothing can be authorized in it, so nothing runs.",
});
//: The five steps of the real progression, in the one order they can happen.
//: The first, second and fifth are record kinds; the third and fourth are the
//: two phases of an `attempt_event`. Nothing here decides that a step is
//: MISSING -- a step is named only when a record carries it.
export const TIMELINE_STEPS = Object.freeze([
  "action_proposal", "action_request", "effect_lease", "execution_observed",
  "action_result"]);
//: Which field carries a record's instant. A kind absent from this map states
//: no instant this build knows, and is said so rather than stamped with one.
export const INSTANT_FIELDS = Object.freeze({
  action_proposal: "proposed_at", action_request: "requested_at",
  action_result: "observed_at", adapter_observation: "observed_at",
  artifact: "created_at", attempt_event: "recorded_at",
  decision: "decided_at", evidence: "observed_at",
  graph_definition: "created_at", run_terminal: "recorded_at",
});
//: The identity fields each kind is summarised by, in reading order. Payload
//: bodies (`arguments`, `content`) are deliberately absent: a timeline row is
//: an index into the journal, never a second copy of it.
export const ROW_FACTS = Object.freeze({
  action_proposal: ["proposal_id", "attempt_id", "node_id", "instance_id",
    "capability", "proposed_by"],
  action_request: ["action_id", "attempt_id", "node_id", "instance_id",
    "capability", "mode", "requested_by"],
  action_result: ["receipt_id", "action_id", "attempt_id", "instance_id",
    "outcome", "exit_code", "detail", "evidence_refs"],
  adapter_observation: ["observation_id", "adapter_id", "instance_id",
    "health", "available_capabilities", "detail"],
  artifact: ["artifact_id", "artifact_ref", "media_type", "source_action_id",
    "input_artifact_ids"],
  attempt_event: ["event_id", "action_id", "attempt_id", "instance_id",
    "adapter_id", "phase", "outcome", "exit_code"],
  decision: ["receipt_id", "gate_id", "action", "actor", "reason",
    "supersedes"],
  evidence: ["evidence_id", "kind", "label", "uri", "verification",
    "verified_by", "verified_at"],
  graph_definition: ["graph_id", "schema_version"],
  run_terminal: ["terminal_id", "graph_id", "state", "settled_nodes",
    "unreachable_nodes"],
});
//: Status is its own channel and never the only carrier: every chip below
//: draws a glyph and a word as well.
export const OUTCOME_CHANNEL = Object.freeze({
  succeeded: "pass", failed: "fail", cancelled: "none", rejected: "fail",
  verification_failed: "fail", unknown: "none",
});
export const PHASE_CHANNEL = Object.freeze({
  idle: "none", proposed: "wait", requested: "wait", running: "wait",
  observed: "wait",
});
export const GATE_CHANNEL = Object.freeze({
  idle: "wait", satisfied: "pass", failed: "fail",
  changes_requested: "wait", waived: "none", unknown: "wait",
});
export const VERIFICATION_CHANNEL = Object.freeze({
  verified: "pass", unverified: "wait", unavailable: "none",
  mismatch: "fail", error: "fail",
});
export const CHANNEL_GLYPHS = Object.freeze({
  pass: "✓", wait: "●", fail: "✕", none: "·",
});
//: The one sentence `verification_failed` must never appear without. The
//: protocol word travels beside it, never instead of it.
export const VERIFICATION_FAILED_NOTE = "Process exit 0 proves the process "
  + "finished, not that the work was verified. This run reached the end of an "
  + "action and its verification did not pass, so nothing here says the work "
  + "is done.";
//: The ONE sentence this product uses for a step waiting at a join.
//
// "Waiting for a predecessor" reads as ANY, and joins are AND-only: every
// road into a step must open before it may run. A person told the weaker
// thing would expect the step to start as soon as one branch arrived, and
// would read the plan as doing something it never does.
//
// It lives HERE rather than beside either screen because two screens say it
// now: the Runs screen about a step that is not offered, and the Decisions
// screen about a gate that cannot be answered yet. Two copies of one rule are
// two chances to say it differently about one run.
export const ALL_ROADS = "ALL incoming roads must open before this step may "
  + "run.";
//: The ONE sentence a write control says while the socket is down.
//
// Every write control on this window's run screens is gated on the STREAM
// being open -- not on any workflow's readiness, because neither a decision
// nor a step is about a workflow -- so a control that stayed pressable while
// it is down would invite a press the door has already decided to refuse. The
// reason is SAID rather than left to a grey button: a control that greys with
// no sentence teaches a person the product cannot do the thing, when what
// happened is that the line went down.
//
// It lives HERE for `ALL_ROADS`'s reason: two files say it now -- the
// Decisions screen about recording an answer, the step control about proposing
// and confirming -- and one rule written out twice is one rule that can be
// said two ways.
export const STREAM_DOWN_REASON = "The live connection is down, so nothing can "
  + "be recorded until it is back. What you have typed here is kept.";
