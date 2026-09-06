//: What ONE run read says about its gates and its participants.
//:
//: Moved out of `studio-store.js` when that module reached the project's
//: 800-line cap. The seam is real rather than convenient: nothing here moves
//: state. Every function below is a PROJECTION over a single run read --
//: given the payload it computes the same answer forever, with no previous
//: state, no event and no arm. The reducer next door answers a different
//: question, "what does this event do to what is on screen", and it calls
//: these the way it calls any other pure helper.
//:
//: They read the plan and the projection the run read already carries, and
//: they invent nothing: a gate this graph does not name is not a row here, and
//: a run that froze no participants states none rather than defaulting to an
//: empty capability list, which would read as "this instance may do nothing".
//:
//: The two predicates below are this module's own, as `studio-runs.js` keeps
//: its own. They are shape tests and not a vocabulary: a second copy of a
//: closed word list would drift, and a second copy of `Array.isArray` cannot.

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }

function receiptsOf(detail) {
  const found = new Map();
  for (const wrapper of rows(detail.records)) {
    if (wrapper.record_type === "decision" && isObject(wrapper.record)) {
      found.set(wrapper.record.gate_id, wrapper.record);
    }
  }
  return found;
}

//: One step's row in the server's own schedule, or null when this build was
//: answered no schedule at all. The ONE lookup: where a step stands, what it
//: waits on and where it goes next are three fields of one row, and three
//: separate finds would be three chances to read them off different rows.
function scheduleRow(schedule, nodeId) {
  if (!isObject(schedule)) return null;
  const row = rows(schedule.nodes).filter(isObject)
    .find((node) => node.node_id === nodeId);
  return isObject(row) ? row : null;
}

//: The roads out of one step, as the server's own schedule states them.
//
// A run read from a build that answers no schedule states NO successors rather
// than falling back to the edge list. Guessing here is exactly the failure this
// key exists to remove, and an empty list is a reading a person can see is
// empty; a wrong one is not.
function opensOf(row) {
  return row === null ? [] : rows(row.opens).filter(isObject);
}

//: Every receipt this run has written for one gate, in journal order.
//
// Two different questions are answered off this one list -- which receipt
// stands, and how many answers the gate has had -- and reading the journal
// twice would be two chances to disagree about one run.
function receiptsFor(detail, runId, gateId) {
  return rows(detail.records)
    .filter((wrapper) => wrapper.record_type === "decision"
      && isObject(wrapper.record) && wrapper.record.run_id === runId
      && wrapper.record.gate_id === gateId)
    .map((wrapper) => wrapper.record);
}

//: WHICH receipt stands for one gate right now, or null.
//
// The same reading `contracts.gate_decision` takes and no other: of this run's
// receipts for this gate, the ones nothing supersedes -- and when that is not
// exactly one, null. A journal holding two of them is one the projection
// itself calls `unknown`, and there is no current answer in it for a person to
// replace. Answering with either would be this window picking a current answer
// the server says it cannot pick.
function standingOf(mine) {
  const superseded = new Set(mine
    .map((receipt) => receipt.supersedes)
    .filter((value) => typeof value === "string"));
  const current = mine.filter(
    (receipt) => !superseded.has(receipt.receipt_id));
  return current.length === 1 && typeof current[0].receipt_id === "string"
    ? current[0].receipt_id : null;
}

//: What the PLAN says about one gate, and what the run has already answered
//: it. Six fields, computed together because they are one question -- may this
//: gate be answered now, and by replacing what -- and because the Decisions
//: screen must ask it the way the write door asks it.
//
// `reachable` is the server's own reading of ARRIVED, spelled the same way on
// both sides: no road in still pending, none closed by a branch not taken, and
// the lap it owes not already answered. It is deliberately not the word
// `runnable`: a HALT rewrites every runnable row to blocked so that nothing
// more is offered as WORK, and a decision is not work -- a screen reading
// `runnable` printed "ALL incoming roads must open" about a gate whose roads
// were all open, and said "cannot be answered yet" forever on a run that had
// stopped.
function planWords(planned, answered) {
  const blocked = Object.freeze(planned === null ? []
    : rows(planned.blocked_by).filter((row) => typeof row === "string"));
  const closed = Object.freeze(planned === null ? []
    : rows(planned.closed_by).filter((row) => typeof row === "string"));
  const state = planned === null || typeof planned.state !== "string"
    ? null : planned.state;
  return {
    state, blocked_by: blocked, closed_by: closed,
    reachable: state !== null && state !== "settled"
      && blocked.length === 0 && closed.length === 0,
    // The receipt a second answer would REPLACE, read the way the server
    // reads it. A reopened lap is answered again by superseding what stands,
    // and a window that posted `null` there would write a second standing
    // answer -- which is the journal the projection cannot read.
    standing: standingOf(answered),
    // How many answers this gate has already had in this run. It is the
    // window's half of a receipt IDENTITY: an id minted from the gate and the
    // person alone can be minted once, so a second answer on a reopened lap
    // collided with the first and was refused as a conflict. Counting durable
    // records keeps the identity derivable -- a lost reply re-sent before the
    // write lands counts the same answers and re-sends the same id.
    answers: answered.length,
    // The decision DOOR's own verdict for a receipt offered now, served on the
    // read: `first`, `supersede` or `none` on a gate, null elsewhere -- and
    // null from a build that answers no such word, which offers nothing. The
    // form is gated on THIS and not on the two words above, because one of the
    // door's arms is a fact this window cannot compute without a second copy of
    // the lap arithmetic: whether the standing answer belongs to the lap the
    // gate is on now. A copy here offered a supersede of lap one's approval on
    // a gate lap two had not reached, and the door refused every one of them.
    answerable: planned !== null && typeof planned.answerable === "string"
      ? planned.answerable : null,
  };
}

//: What the DRAWING says about one gate: the author's own sentence about why
//: it exists, what it demands of an answer, and where each answer sends the
//: run. All three are carried through and none is interpreted here.
//
// `purpose` is the workflow author's own words, frozen into the plan the run
// followed, and this is the only place that sentence exists after the drawing
// was published. `success_requires` is the plan's word about what the gate
// demands: the server refuses a waiver and the store refuses one written
// around the server, so this window decides nothing beyond which control to
// stop offering. `unblocks` is read off the SCHEDULE the server computed --
// this window used to walk the edge list and call every out-edge an
// unblocking, which was true only while no road could carry a condition, and
// afterwards would have promised a person that approving opens a step their
// approval actually closes.
function drawnFacts(node, titles, planned) {
  return {
    purpose: typeof node.purpose === "string" ? node.purpose : null,
    success_requires: typeof node.success_requires === "string"
      ? node.success_requires : null,
    unblocks: Object.freeze(opensOf(planned)
      .map((row) => Object.freeze({node_id: row.to_node,
        condition: typeof row.condition === "string" ? row.condition : null,
        title: titles.has(row.to_node) ? titles.get(row.to_node) : null}))),
  };
}

//: Whether an authorized attempt on ONE step has not been answered.
//
// `graph_schedule.attempt_in_flight`, spelled the same way on this side of the
// wire: an `action_request` naming this step whose `action_id` no
// `action_result` closes. Records, and nothing else.
//
// It was the runtime PHASE first, and twice over that was the wrong document.
// The phase reports how far the node's CURRENT action got, and
// `graph_projection._current_action` is the LAST proposal or request naming it
// -- so a phase of `observed` is answered for an attempt whose result has
// already landed, and a proposal appended OVER an unanswered request (a stale
// second window; the propose door holds no schedule check) pushes the phase
// back to `proposed` while a worker is still executing. The screen then told a
// person the run had been halted while its worker ran.
//
// Judged by `action_id` and never by "some request, some result", for the same
// reason the Python does: two attempts on one step are two identities, and a
// rule that asked only whether ANY answer had arrived would call the second
// one finished the moment the first reported.
export function attemptInFlight(detail, nodeId) {
  if (typeof nodeId !== "string") return false;
  const records = rows(isObject(detail) ? detail.records : null);
  const answered = new Set(records
    .filter((row) => row.record_type === "action_result" && isObject(row.record))
    .map((row) => row.record.action_id));
  return records.some((row) => row.record_type === "action_request"
    && isObject(row.record) && row.record.node_id === nodeId
    && !answered.has(row.record.action_id));
}

//: The document a reference resolves to, as the transport resolves it
//: (`ArtifactHandoff.instruction`, `.bound`): the latest artifact under the
//: ref among the records standing BEFORE the named proposal -- or, for a
//: proposal a person is about to write, among all of them. Null when none
//: stands, which is the file road's answer and not a refusal; and null when
//: the proposal is not in these records, because what a proposal the journal
//: does not hold bound is not a question this read can answer.
export function latestDocument(records, artifactRef) {
  let found = null;
  for (const wrapper of rows(records)) {
    if (wrapper.record_type === "artifact" && isObject(wrapper.record)
        && wrapper.record.artifact_ref === artifactRef) {
      found = wrapper.record;
    }
  }
  return found;
}

export function boundDocument(records, proposalId, artifactRef) {
  let found = null;
  for (const wrapper of rows(records)) {
    if (wrapper.record_type === "action_proposal" && isObject(wrapper.record)
        && wrapper.record.proposal_id === proposalId) {
      return found;
    }
    if (wrapper.record_type === "artifact" && isObject(wrapper.record)
        && wrapper.record.artifact_ref === artifactRef) {
      found = wrapper.record;
    }
  }
  return null;
}

//: Whether this run is OVER, by either of the two facts that say so.
//
// The plan's own word for a run nothing can be added to, or the durable
// terminal it recorded. Asked once per read and carried onto every gate row,
// because it is a fact about the RUN and not about any one gate -- and because
// a screen that did not say it would go on offering an answer the door is
// bound to refuse, or explain a gate as though its turn were still coming.
function endingOf(detail, schedule) {
  const word = isObject(schedule) && typeof schedule.run_state === "string"
    ? schedule.run_state : null;
  const recorded = rows(detail.records)
    .some((wrapper) => wrapper.record_type === "run_terminal");
  return {
    ended: recorded || word === "stalled" || word === "complete",
    plan_word: word,
  };
}

//: Every gate this run's plan names, and where it stands. Read off the plan and
//: the projection the run read already carries; nothing here is stored twice
//: and no step is invented that the plan does not hold.
export function decisionRows(detail) {
  const graph = isObject(detail) ? detail.graph : null;
  const definition = isObject(graph) ? graph.definition : null;
  const runtime = isObject(graph) ? graph.runtime : null;
  const schedule = isObject(graph) ? graph.schedule : null;
  if (!isObject(definition) || !isObject(runtime)) return Object.freeze([]);
  const run = isObject(detail.run) ? detail.run : {};
  const position = new Map(rows(runtime.nodes).filter(isObject)
    .map((row) => [row.node_id, row]));
  const titles = new Map(rows(definition.nodes).filter(isObject)
    .map((node) => [node.node_id, node.title]));
  const receipts = receiptsOf(detail);
  const ending = endingOf(detail, schedule);
  const found = [];
  for (const node of rows(definition.nodes).filter(isObject)) {
    if (typeof node.gate_id !== "string") continue;
    const standing = position.get(node.node_id);
    const planned = scheduleRow(schedule, node.node_id);
    const answered = receiptsFor(detail, run.run_id, node.gate_id);
    found.push(Object.freeze({
      run_id: run.run_id, gate_id: node.gate_id, node_id: node.node_id,
      title: node.title, mode: run.mode,
      ...drawnFacts(node, titles, planned),
      decision: standing && typeof standing.decision === "string"
        ? standing.decision : "unknown",
      // What the plan says about THIS gate, and what already answers it.
      // `null` state is a build that answered no schedule, which is the one
      // case the screen falls back to its older idle rule for.
      ...planWords(planned, answered),
      // …and whether the RUN is over, which is a fact about neither.
      ...ending,
      receipt: receipts.has(node.gate_id) ? receipts.get(node.gate_id) : null,
    }));
  }
  return Object.freeze(found);
}

//: Who this run froze, joined to what this build says those bindings may be
//: asked for. The controls read is the source; a run with none states nothing
//: rather than defaulting a capability list to empty.
export function participantsOf(detail) {
  const controls = isObject(detail) ? detail.controls : null;
  if (!isObject(controls)) return Object.freeze([]);
  const runId = isObject(detail.run) ? detail.run.run_id : undefined;
  return Object.freeze(rows(controls.instances).map((row) => Object.freeze(
    runId === undefined ? row : {...row, run_id: runId})));
}
