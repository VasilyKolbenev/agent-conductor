"use strict";
// The one place on the Runs screen that WRITES: a step the plan calls runnable
// is proposed here, and the proposal standing on it is confirmed here.
//
// Everything a proposal says about the WORK is read out of the frozen plan
// node -- the instance, the capability, the arguments and the ceiling -- and
// nothing here offers a control that could change one of them. That is not
// caution. `graph_causality._matches_its_node` refuses a proposal whose
// arguments are not the node's own bytes, and `authorize_holds`
// `_hold_node_is_eligible` refuses a node the schedule does not call runnable.
// A window that let a person type either would be composing a body the server
// is bound to refuse and calling it a form.
//
// What a person supplies is who is asking, why, and -- one road later -- who
// is confirming. Three typed facts; the rest belongs to the plan.
//
// THE OFFER RULE IS READ FROM DURABLE FACTS AND NEVER FROM A REFUSAL. The
// server's own schedule row must say `runnable`, the node must bind a
// capability, and this run's controls read must say the bound instance's
// adapter serves it. A build that serves none still draws the control,
// DISABLED, naming the pair it cannot serve -- a control that vanishes teaches
// a person the product cannot do the thing, when what happened is that this
// machine has no provider for it.
//
// It builds fragments and mounts nothing. `studio-runs.js` owns the screen and
// calls this once per position row. The split is the line cap's, but the seam
// is real: a control that writes is the one part of that screen a reader has to
// audit, and it is now the whole of one file.
import {canonicalJson} from "./command-projection.js";
import {element} from "./command-view.js";
import {STREAM_DOWN_REASON} from "./studio-runwords.js";

//: `contract_values._id`'s grammar, twice: once as a value this window judges
//: with, once as the pattern a control spells for the platform. Both are copies
//: of one rule, and `studio-people.js` carries the same pair for its own
//: control.
const ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9._\\-]{0,127}";
const ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const RATIONALE_LIMIT = 200;
//: The longest this window ever asks for: the default when a step names no
//: ceiling, and the CAP on the ceiling when it names one.
//
// Two ceilings apply and only one of them is the plan's.
// `graph_causality._within_the_planned_ceiling` refuses a document asking for
// more than its step allows -- and `runtime._hold_budget` refuses a proposal
// past the RUN's `max_action_seconds` at AUTHORIZE rather than at propose. So a
// plan naming 7200s proposed cleanly and made every Confirm 409, under a
// sentence blaming a plan that had not moved. This number is below every budget
// this product ships, so asking for at most this can never meet that refusal.
const DEFAULT_TIMEOUT = 900;
//: WHAT A PROPOSAL DECLARES IT MAY TOUCH, and why it is stated rather than
//: typed.
//
// `contract_values._scope` demands a non-empty list of canonical project-
// relative paths, so a proposal cannot omit it. What READS it afterwards is
// exactly one relation, said twice: `runtime._hold_facts` refuses a
// confirmation whose scope is not the stored proposal's, and `graph_causality`
// holds that same equality against bytes replayed from disk. No adapter, no
// execution path and no schedule rule consults it -- what a step may really
// touch is the sandbox the adapter runs under, which is a different mechanism
// with a different refusal.
//
// So a control here would write a value nothing narrows anything by, which is
// the one thing the completeness register forbids outright: a field with no
// consumer says so where it would have been rather than growing a control that
// looks like an authority. The value is this product's own -- the `_SCOPE`
// both `conduct preview` and the control loop send -- and the sentence beside
// it says what it is not.
const SCOPE = Object.freeze(["src"]);
const SCOPE_NOTE = "Scope is a declaration this run's records carry, not a "
  + "boundary this build enforces: nothing narrows what a step may touch by "
  + "it, and the sandbox the adapter runs under is what does. It is stated "
  + "here rather than typed, because a control over a value nothing reads "
  + "would be a promise this build does not keep.";
//: WHAT EACH WRITE MEANS, said by the control before it happens and by the
//: window after it lands. One sentence per road and one copy of each: a form
//: promising one thing above a status line reporting another would be two
//: answers about one durable record. `studio.js` reads both to announce the
//: write it made.
//
// The first is the half of the road that authorizes nothing: a proposal is a
// request FOR an attempt, and only a Human's confirmation makes one. The
// second is the half that does, and it says where the work actually happens --
// on the server's worker, never in this window.
export const PROPOSED_NOTE = "A proposal is a durable record and runs "
  + "nothing: it is a request for an attempt, and confirming it is what "
  + "authorizes one.";
export const REQUESTED_NOTE = "The request is a durable record. Whatever runs, "
  + "runs on the server's worker; this window only reads.";
//: The two refusals a step write can meet that say the SCREEN is stale rather
//: than the person wrong, and the sentence appended to them: a window that only
//: printed the refusal would leave the same row offering the same refused step.
//: The refusals a step write can meet that say the SCREEN is stale rather than
//: the person wrong, and are answered by reading the run again.
//
// `run_terminal` is here for `authorization_refused`'s own reason: a run that
// recorded its ending offers nothing further, so what is on screen is older
// than what the server holds and the read is what makes it current.
//
// `route_unsafe` is deliberately NOT here, and it is the sharper case. The
// sentence these codes carry ends "the run was read again" -- and for a route
// this build refuses to walk, that read is refused too, by the same
// `_hold_route` on the way in. Promising a read that cannot happen is worse
// than saying nothing, so the refusal is reported and nothing is reopened.
export const STEP_MOVED = Object.freeze(
  ["authorization_refused", "service_refused", "run_terminal"]);
//: …and the sentence appended to them. It names the plan AND the run's own
//: allowance, because one refusal class covers both: a step the plan no longer
//: calls runnable, and a request the run refuses on its budget, its changed
//: facts, its attempt identity or a sandbox it cannot provide. The wire carries
//: the code and discards the prose, so a sentence naming only the plan was
//: wrong for four of the five and sent a person looking at a plan that had not
//: moved.
export const READ_AGAIN = "Read again: this step is offered only while the "
  + "run's plan calls it runnable and the request fits what the run allows; "
  + "the run was read again.";
//: What a control says while its own write is in flight.
//
// The draft is NOT destroyed at the door. A refusal that does not re-read --
// the line down, a body the boundary refuses, a session that rotated -- must
// give the control back with what was typed still in it, which is what
// `STREAM_DOWN_REASON` has always promised. So the shut state here is a fact
// about the WRITE, and it is what makes a second press impossible: it is
// dispatched before the request goes out, and only the accepting read takes it
// away, along with the whole draft.
const WRITING_NOTE = "Writing… this control is shut until the server answers "
  + "and this run has been read again. What you have typed here is kept.";
//: What the window ASKS FOR, said beside the number so a reader can check it.
const TIMEOUT_NOTE = "The window asks for this step's own ceiling or "
  + `${DEFAULT_TIMEOUT}s, whichever is smaller. A plan may name a ceiling `
  + "above what a run's budget allows, and an attempt past that budget is "
  + "refused at the Confirm rather than here.";

const NOT_STATED = "not stated";

function show(value) {
  if (value === null || value === undefined || value === "") return NOT_STATED;
  if (Array.isArray(value)) return value.length ? value.join(", ") : NOT_STATED;
  return String(value);
}

function rows(value) { return Array.isArray(value) ? value : []; }

function object(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value : null;
}

function text(value) { return typeof value === "string" ? value : ""; }

function note(value) {
  return element("p", {className: "studio-note", text: value});
}

function fact(label, value) {
  return element("p", {className: "studio-fact"}, [
    element("span", {className: "studio-fact__k", text: label}),
    element("span", {className: "studio-fact__v", text: show(value)}),
  ]);
}

function handlerOf(handlers, name) {
  const found = handlers ? handlers[name] : null;
  return typeof found === "function" ? found : null;
}

//: The one sentence a control says when this screen was mounted without the
//: wire it needs, spelled the way `studio-runs.js` spells it: a person meeting
//: a shut control is owed the same explanation wherever it sits.
function mountedWithout(name) {
  return `This screen was mounted without a ${name} handler.`;
}

//: Which run this control writes to, off the read it was drawn from.
function runOf(detail) {
  return (object(detail.run) || {}).run_id;
}

// -- the offer rule -----------------------------------------------------------

//: Why this build cannot serve this step, or null when it can.
//
// The join is `assignmentSection`'s, by identity: the run's frozen binding
// names an instance, the controls read says which capabilities the adapter
// bound to it declares, and the plan node names the one this step needs. A read
// that never landed is a THIRD answer and says so -- "no adapter serves this"
// and "this window was not told" are different facts, and a person acting on
// the first while the second is true would go looking for a provider they have.
function whyNoAdapter(detail, node) {
  const controls = object(detail.controls);
  const pair = `${show(node.instance_id)}/${show(node.capability)}`;
  if (controls === null) {
    return "This run's controls read has not landed here, so this window "
      + `cannot say whether any adapter serves ${pair}.`;
  }
  const bound = rows(controls.instances)
    .find((row) => row.instance_id === node.instance_id) || null;
  if (bound === null || !rows(bound.controls).includes(node.capability)) {
    return `This build serves no adapter for ${pair}, so nothing here can `
      + "carry this step out. The step is offered and the control is shut.";
  }
  return null;
}

// -- the facts the plan already decided ---------------------------------------

//: The longest this attempt may run: the SMALLER of the step's own ceiling and
//: this window's own. Two ceilings really do apply -- see `DEFAULT_TIMEOUT` --
//: and a proposal that honoured only the plan's was accepted and then refused
//: at every Confirm.
function timeoutOf(node) {
  return Number.isInteger(node.timeout_seconds)
    ? Math.min(node.timeout_seconds, DEFAULT_TIMEOUT) : DEFAULT_TIMEOUT;
}

//: This attempt's identity, minted from the step and the attempts already
//: AUTHORIZED on it. It must be derivable, so a lost reply re-sends the same
//: one, and it must not collide with an id this run already holds --
//: `_hold_attempt_is_not_taken` refuses a repeat, and a refusal there is
//: permanent, because the same journal mints the same id every time.
//
// So it is the greatest number already spelled in THIS grammar plus one, never
// the count of the set. Counting is wrong the moment a number is skipped: one
// `attempt-goal-1` in a journal of one attempt made the next mint
// `attempt-goal-1` as well, and that step could never be proposed again.
//
// RESIDUAL, stated rather than guarded: `attempt-` and the counter spend ten
// characters of the 128 an id may have, so a node id past about 118 mints one
// the contract refuses, and the boundary answers `contract_invalid` without
// naming the length. A plan naming a step that long needs bytes written around
// this product before it needs a branch here.
function attemptId(node, runtime) {
  const prefix = `attempt-${node.node_id}-`;
  const taken = rows(runtime.attempt_ids)
    .filter((id) => typeof id === "string" && id.startsWith(prefix))
    .map((id) => id.slice(prefix.length))
    .filter((tail) => /^[0-9]+$/.test(tail))
    .map((tail) => Number(tail));
  return `${prefix}${taken.length ? Math.max(...taken) + 1 : 0}`;
}

//: What the PLAN decided about this step, drawn read-only. Every one of these
//: travels into the body exactly as it is shown: there is no control here that
//: could make the screen and the wire disagree.
function planFacts(node, runtime) {
  return [
    fact("Step", `${show(node.title)} · ${show(node.node_id)}`),
    fact("Instance", node.instance_id),
    fact("Capability", node.capability),
    fact("Arguments", canonicalJson(node.arguments)),
    note("The arguments are the plan's own bytes. The server refuses a "
      + "proposal that does not repeat them, so they are shown rather than "
      + "offered."),
    fact("Longest this may run", `${timeoutOf(node)}s`),
    note(TIMEOUT_NOTE),
    fact("Attempt id", attemptId(node, runtime)),
    fact("Scope", SCOPE),
    note(SCOPE_NOTE),
  ];
}

// -- the controls -------------------------------------------------------------

function textControl(name, key, value, edit, label, attributes) {
  const control = element("input", Object.assign({
    autocomplete: "off", "data-focus-key": `field:${name}`, name,
    spellcheck: "false", type: "text",
  }, attributes));
  control.value = value;
  if (edit === null) control.disabled = true;
  else control.addEventListener("change", () => edit(key, control.value));
  return element("label", {className: "studio-field"}, [
    element("span", {text: label}), control,
  ]);
}

//: The one submit control, and every reason it may be shut, in the order a
//: person can do something about them. A dropped stream is said first: it is
//: the reason no amount of typing here answers.
function submitControl(label, stops, wire) {
  const button = element("button", {
    "data-focus-key": wire.key, text: label, type: "submit",
  });
  button.disabled = stops !== null || wire.shut;
  if (wire.writing) button.title = WRITING_NOTE;
  else if (!wire.live) button.title = STREAM_DOWN_REASON;
  const said = [];
  // The write in flight is said FIRST: it is the only one of these a person
  // has already done something about, and it is about to end by itself.
  if (wire.writing) said.push(note(WRITING_NOTE));
  if (!wire.live) said.push(note(STREAM_DOWN_REASON));
  if (stops !== null) said.push(note(stops));
  if (wire.missing !== null) said.push(note(mountedWithout(wire.missing)));
  return [button, ...said];
}

//: Where a row's typed facts go, and whose they are. The draft addresses ONE
//: step at a time, exactly as the Decisions screen's draft addresses one gate:
//: a value typed against this row is this row's, and a row the draft is not
//: addressing shows empty controls rather than somebody else's answer.
function draftFor(state, node) {
  const runs = object(state.runs) || {};
  const step = object(runs.step) || {};
  return step.nodeId === node.node_id ? step : null;
}

//: One editor for a row's fields. Choosing comes FIRST and only when the draft
//: is addressing another row: `step-chosen` clears the draft, so calling it on
//: the row that already holds one would throw away the field just typed.
function editorFor(node, mine, handlers) {
  const choose = handlerOf(handlers, "chooseStep");
  const edit = handlerOf(handlers, "editStep");
  if (choose === null || edit === null) return null;
  return (key, value) => {
    if (!mine) choose(node.node_id);
    edit({[key]: value});
  };
}

//: What this form was mounted WITH, gathered once so the control, its title
//: and its sentences all read the same answers. `missing` names the one wire
//: that is absent, or null: a control shut for the want of a handler says which
//: one, and a control shut because the line is down says that instead.
function wireFor(name, key, edit, submit, live, writing) {
  const absent = submit === null ? name : (edit === null ? "editStep" : null);
  return {edit, key, live, missing: absent,
    shut: submit === null || edit === null || !live || writing, submit,
    writing};
}

//: Whether a write for THIS row's draft is in flight. A draft addressing
//: another row shuts nothing here: one press must not grey every step.
function writingOf(draft) {
  return draft !== null && draft.writing === true;
}

// -- propose ------------------------------------------------------------------

//: What stops this proposal being written, in the user's words, or null. The
//: rules are `ActionProposal`'s own -- `proposed_by` is an id, `rationale` is a
//: non-empty text -- asked here so the control refuses beside the person rather
//: than on the wire.
function whyNotProposable(draft) {
  if (draft === null) {
    return "Type who is proposing this step and why, and it can be written.";
  }
  if (!ID_RE.test(text(draft.proposedBy))) {
    return "Type who is proposing, as a plain id: letters, digits, dot, "
      + "underscore or hyphen, up to 128 characters.";
  }
  if (!text(draft.rationale).trim()) {
    return "Say why this step is being proposed. The reason becomes part of "
      + "the durable record.";
  }
  return null;
}

//: The nine keys a proposal carries, and where each one comes from.
//
// `node_id` is ALWAYS the step the SCHEDULE chose and never a typed value: it
// binds the action to the plan, it resolves the verifier, and it is what
// `_hold_node_is_eligible` judges. Four beside it are the plan node's own, two
// are stated above this file's controls, and two are the person's.
function proposalBody(node, runtime, draft) {
  return {
    instance_id: node.instance_id,
    attempt_id: attemptId(node, runtime),
    capability: node.capability,
    arguments: node.arguments,
    scope: SCOPE,
    proposed_by: draft === null ? "" : text(draft.proposedBy),
    rationale: draft === null ? "" : text(draft.rationale),
    timeout_seconds: timeoutOf(node),
    node_id: node.node_id,
  };
}

function proposeForm(node, runtime, detail, state, handlers) {
  const draft = draftFor(state, node);
  const submit = handlerOf(handlers, "proposeStep");
  const wire = wireFor("proposeStep", `propose:${node.node_id}`,
    editorFor(node, draft !== null, handlers), submit,
    state.connection === "open", writingOf(draft));
  const shut = whyNoAdapter(detail, node);
  const stops = shut === null ? whyNotProposable(draft) : shut;
  const form = element("form", {className: "studio-step",
    "data-step": `propose:${show(node.node_id)}`},
  [element("h4", {text: "Propose this step"}), note(PROPOSED_NOTE),
    ...planFacts(node, runtime),
    textControl("proposed_by", "proposedBy",
      draft === null ? "" : text(draft.proposedBy), wire.edit, "Proposed by",
      {maxlength: "128", pattern: ID_PATTERN, required: ""}),
    textControl("rationale", "rationale",
      draft === null ? "" : text(draft.rationale), wire.edit,
      `Why (up to ${RATIONALE_LIMIT} characters)`,
      {maxlength: String(RATIONALE_LIMIT)}),
    ...submitControl("Propose this step", stops, wire)]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (stops !== null || submit === null || wire.shut) return;
    submit({runId: runOf(detail), nodeId: node.node_id,
      body: proposalBody(node, runtime, draft)});
  });
  return [form];
}

// -- confirm ------------------------------------------------------------------

//: WHICH proposal stands on this step, read out of the run's own journal.
//
// The last `action_proposal` naming this node that no `action_request` has
// taken. The link between the two is `preview_digest`: a request repeats the
// stored proposal's, and `runtime._hold_facts` refuses a confirmation whose
// digest is not that same one -- so it is the identity the SERVER already holds
// the pair to, rather than a spelling this window invents.
//
// Read from the READ and never from the reply to the write that made it: what
// a person confirms must be what the journal appended.
function standingProposal(detail, nodeId) {
  const records = rows(detail.records);
  const taken = new Set(records
    .filter((row) => row.record_type === "action_request")
    .map((row) => (object(row.record) || {}).preview_digest));
  const open = records
    .filter((row) => row.record_type === "action_proposal")
    .map((row) => object(row.record))
    .filter((record) => record !== null && record.node_id === nodeId
      && !taken.has(record.preview_digest));
  return open.length ? open[open.length - 1] : null;
}

//: The six keys `api_contracts._CONFIRM_FIELDS` admits, and no seventh. Five
//: are the STORED proposal's, copied verbatim: a confirmation restates the
//: facts it is confirming and the runtime refuses every one that differs. A
//: confirm body may not name a node at all -- `node_id` is copied from the
//: stored proposal at authorize time, so a body that could name one could name
//: a different one.
function confirmBody(proposal, draft) {
  return {
    proposal_id: proposal.proposal_id,
    preview_digest: proposal.preview_digest,
    capability: proposal.capability,
    scope: proposal.scope,
    config_digest: proposal.config_digest,
    confirmed_by: draft === null ? "" : text(draft.confirmedBy),
  };
}

//: The stored proposal, drawn as the facts a person is confirming.
//
// There is deliberately NO sentence about a proposal going stale, and the
// missing sentence is the point. `runtime._hold_freshness` judges the
// CONFIRMATION, which the server mints at the moment of the press
// (`confirmed_at=self._clock()`), so a proposal standing since last year is
// confirmed exactly as one written a second ago. A sentence saying otherwise
// would have sent a person to propose again over a control that works.
// `Proposed at` stays: it is history, and history is what it is drawn as.
function proposalFacts(proposal) {
  return [
    fact("Proposal", proposal.proposal_id),
    fact("Proposed at", proposal.proposed_at),
    fact("Proposed by", proposal.proposed_by),
    fact("Why", proposal.rationale),
    fact("Capability", proposal.capability),
    fact("Arguments", canonicalJson(proposal.arguments)),
    fact("Scope", proposal.scope),
    fact("Preview digest", proposal.preview_digest),
    fact("Against configuration", proposal.config_digest),
  ];
}

function whyNotConfirmable(draft) {
  if (draft === null || !ID_RE.test(text(draft.confirmedBy))) {
    return "Type who is confirming, as a plain id: letters, digits, dot, "
      + "underscore or hyphen, up to 128 characters.";
  }
  return null;
}

function confirmForm(node, detail, state, handlers) {
  const proposal = standingProposal(detail, node.node_id);
  if (proposal === null) {
    return [note("This step reads as proposed and this window cannot find the "
      + "proposal standing on it. Read the run again: nothing is offered "
      + "against a record that is not there.")];
  }
  const draft = draftFor(state, node);
  const submit = handlerOf(handlers, "confirmStep");
  const wire = wireFor("confirmStep", `confirm:${node.node_id}`,
    editorFor(node, draft !== null, handlers), submit,
    state.connection === "open", writingOf(draft));
  const shut = whyNoAdapter(detail, node);
  const stops = shut === null ? whyNotConfirmable(draft) : shut;
  const form = element("form", {className: "studio-step",
    "data-step": `confirm:${show(node.node_id)}`},
  [element("h4", {text: "Confirm this proposal"}), note(REQUESTED_NOTE),
    ...proposalFacts(proposal),
    textControl("confirmed_by", "confirmedBy",
      draft === null ? "" : text(draft.confirmedBy), wire.edit, "Confirmed by",
      {maxlength: "128", pattern: ID_PATTERN, required: ""}),
    ...submitControl("Confirm and authorize", stops, wire)]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (stops !== null || submit === null || wire.shut) return;
    submit({runId: runOf(detail), nodeId: node.node_id,
      body: confirmBody(proposal, draft)});
  });
  return [form];
}

/**
 * The controls one position row is offered, which is usually none.
 *
 * A row is offered a control only while the server's own schedule calls the
 * step `runnable` AND the plan node binds an instance and a capability.
 * Everything else -- blocked, settled, unreachable, a gate, a loop -- is
 * offered nothing, and the row's own sentence next door says why. Which of the
 * two controls it is comes from the runtime phase: a step with a proposal
 * standing on it is confirmed, and every other phase proposes.
 *
 * @param {object} node The plan's frozen node, joined by `node_id`.
 * @param {object} runtime That node's row of the runtime projection.
 * @param {object} standing That node's row of the server's schedule, or null.
 * @param {object} detail The whole run read: its records, config and controls.
 * @param {object} state The reducer's frozen value, whole.
 * @param {object} handlers Callbacks this module invokes and never defines:
 *   `chooseStep(nodeId)`, `editStep(patch)`, `proposeStep(row)`,
 *   `confirmStep(row)`.
 * @returns {Array<Element>} Nodes to append to the row; empty when none.
 */
export function stepControls(node, runtime, standing, detail, state, handlers) {
  if (standing === null || standing.state !== "runnable") return [];
  if (typeof node.node_id !== "string"
      || typeof node.instance_id !== "string"
      || typeof node.capability !== "string") {
    return [];
  }
  return runtime.phase === "proposed"
    ? confirmForm(node, detail, state, handlers)
    : proposeForm(node, runtime, detail, state, handlers);
}
