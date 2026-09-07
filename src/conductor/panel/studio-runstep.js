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
// capability, the run's frozen authority must permit the write, and this run's
// controls read must say the bound instance's adapter serves it. A build that
// serves none still draws the control, DISABLED, naming the pair it cannot
// serve -- a control that vanishes teaches a person the product cannot do the
// thing, when what happened is that this machine has no provider for it.
//
// It builds fragments and mounts nothing. `studio-runs.js` owns the screen and
// calls this once per position row. The split is the line cap's, but the seam
// is real: a control that writes is the one part of that screen a reader has to
// audit, and it is now the whole of one file.
import {canonicalJson} from "./command-projection.js";
import {element} from "./command-view.js";
//: Which of a step's arguments name the documents it READS, as the reviewed
//: schema marks them: the one rule, declared beside the form that publishes
//: under those references.
import {inputRefs, needsMaterialReproposal} from "./studio-rundocs.js";
import {boundDocument, latestDocument} from "./studio-runread.js";
import {MATERIAL_BINDING, REBIND_MATERIALS, STREAM_DOWN_REASON,
  SAME_ADAPTER_VERIFICATION, UNVERSIONED_MATERIALS, VERIFICATION_FRAME_NOTE,
  VERIFICATION_MATERIALS, VERIFICATION_OUTPUT_NOTE, WRITING_NOTE}
  from "./studio-runwords.js";

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
// sentence blaming a plan that had not moved. This cap fits the shipped budget
// even when doubled for a checker; a custom lower budget may still refuse it.
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
  ["authorization_refused", "service_refused", "run_terminal",
    "proposal_rebind_required"]);
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
//: What a control says while its own write is in flight is `WRITING_NOTE`,
//: declared with the other sentences two fragments say. The draft is NOT
//: destroyed at the door: a refusal that does not re-read must give the
//: control back with what was typed still in it, so the shut state is a fact
//: about the WRITE (`writingOf`), recorded before the request goes out and
//: taken away only by the write's own end.
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

// -- the run's authority ------------------------------------------------------

//: What each rung of the authority ladder PERMITS on this screen, read off the
//: run's frozen envelope (`contract_values.ControlMode`) before any control is
//: drawn. Two server refusals are the source: `service.propose` refuses every
//: proposal in `observe`, and `runtime.authorize` refuses every confirmation
//: unless the run's mode is `confirm`. `policy` is a word the vocabulary
//: carries and nothing serves -- this build ships no policy executor -- so a
//: policy run permits what a propose run permits, and says so rather than
//: offering a Confirm the server is bound to refuse.
//
// R06 of the review of `8dec0e4`: the controls read the schedule and never the
// mode, so an observe run offered a Propose that answered 409 and a propose run
// offered a Confirm that answered 409, each under a sentence sending a person
// to a plan that had not moved. A word this table does not carry permits
// nothing: a write this window cannot describe is not offered.
const PERMITS = Object.freeze({
  observe: "nothing", propose: "proposals", policy: "proposals",
  confirm: "confirmations",
});
//: Where a person gets the authority this run withholds. Named in every
//: sentence that withholds it: a shut door without the open one beside it
//: teaches that the product cannot do the thing. It names what that form
//: really opens -- a run of the workflow's PUBLISHED revision -- and not
//: "this revision", which the form offers no way to choose once a newer one
//: is published, and which a run that follows no workflow does not have.
const CONFIRM_ROAD = "To carry a step out, open a new run of this workflow's "
  + "published revision with authority confirm: "
  + "the Open a run form on the Workflow screen grants it explicitly.";
//: …and for a run that follows no workflow (the API admits one), the road
//: that exists for it: there is no revision of "this workflow" to reopen.
const NO_WORKFLOW_ROAD = "This run follows no workflow. To carry a step out, "
  + "publish a workflow and open a run of it with authority confirm: "
  + "the Open a run form on the Workflow screen grants it explicitly.";

function authorityOf(detail) {
  const run = object(detail.run) || {};
  return {mode: show(run.mode), permits: PERMITS[run.mode] || "nothing",
    road: typeof run.workflow_id === "string" ? CONFIRM_ROAD : NO_WORKFLOW_ROAD};
}

function nothingPermitted(authority) {
  return note(`This run's authority is ${authority.mode}: nothing may be `
    + `proposed on it and nothing runs. ${authority.road}`);
}

function proposalsOnly(authority) {
  return note(`A proposal stands on this step and this run's authority is `
    + `${authority.mode}: nothing can confirm it here. ${authority.road}`);
}

function proposedUnder(mode) {
  return note(`In a ${mode} run a proposal is a durable record and nothing `
    + "carries it out here.");
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

//: The id budget the contract grants (`contract_values._id`), and the two
//: spellings an attempt of one step may take within it. Every NAMED id begins
//: `attempt-` and every DIGEST id begins `attempt.`: the character after the
//: word is the namespace, so no string of one form equals any string of the
//: other, by construction. A step literally named as another step's digest --
//: the collision the first design of this fallback admitted -- therefore mints
//: `attempt-<hex>-0` while the long step mints `attempt.<hex>-0`.
const ID_LIMIT = 128;
const NAMED = "attempt-";
const DIGESTED = "attempt.";

//: FNV-1a, 64 bits, over the UTF-8 bytes of a name. A fixed, documented
//: function rather than a platform digest, because the id must be derivable on
//: every read of every window, synchronously: `crypto.subtle` answers a promise
//: and this render does not wait. Sixteen hex digits, zero-padded, so two names
//: never differ only in a dropped leading digit. `browser_tests` holds a Python
//: spelling of the same function against this one.
function fnv64(text) {
  let hash = 0xcbf29ce484222325n;
  for (const byte of new TextEncoder().encode(text)) {
    hash ^= BigInt(byte);
    hash = (hash * 0x100000001b3n) & 0xffffffffffffffffn;
  }
  return hash.toString(16).padStart(16, "0");
}

//: The two prefixes under which THIS step's attempts may already stand.
function attemptForms(nodeId) {
  return Object.freeze({
    named: `${NAMED}${nodeId}-`,
    digested: `${DIGESTED}${fnv64(nodeId)}-`,
  });
}

//: Every counter already spelled under one prefix. A foreign id in another
//: grammar is skipped rather than counted.
function countersUnder(prefix, ids) {
  return ids
    .filter((id) => typeof id === "string" && id.startsWith(prefix))
    .map((id) => id.slice(prefix.length))
    .filter((tail) => /^[0-9]+$/.test(tail))
    .map((tail) => Number(tail));
}

//: This attempt's identity, minted from the step and the attempts already
//: AUTHORIZED on it. It must be derivable, so a lost reply re-sends the same
//: one, and it must not collide with an id this run already holds --
//: `_hold_attempt_is_not_taken` refuses a repeat, and a refusal there is
//: permanent, because the same journal mints the same id every time.
//
// So it is the greatest number already spelled under EITHER of this step's two
// forms plus one, never the count of the set. Counting is wrong the moment a
// number is skipped: one `attempt-goal-1` in a journal of one attempt made the
// next mint `attempt-goal-1` as well, and that step could never be proposed
// again.
//
// BOUNDED, whatever the step is called (R09 of the review of `8dec0e4`). The
// named form spends the step's own name, so a name of 119 characters minted
// an id the contract refuses and the boundary answered `contract_invalid`
// without naming the length -- although `GraphNode` and the plan both admit
// the name. The form is chosen per counter: the named spelling while it fits
// the budget, the digest spelling once it does not. No plan id is truncated;
// the digest is a projection of the name and never an edit of it. Last, the
// minted id is checked against the run's WHOLE set and bumped until free --
// the server's refusal stays the authority for what one window cannot see.
function attemptId(node, runtime) {
  const forms = attemptForms(node.node_id);
  const ids = rows(runtime.attempt_ids);
  const taken = [...countersUnder(forms.named, ids),
    ...countersUnder(forms.digested, ids)];
  const spell = (counter) => {
    const named = `${forms.named}${counter}`;
    return named.length <= ID_LIMIT ? named : `${forms.digested}${counter}`;
  };
  let counter = taken.length ? Math.max(...taken) + 1 : 0;
  let minted = spell(counter);
  while (ids.includes(minted)) minted = spell(++counter);
  return minted;
}

//: WHICH DOCUMENT A DISPATCH RUNS, said where the person decides (R04 of the
//: review of `8dec0e4`, under the owner's correction: a source is bound when
//: it is confirmed, never chosen again at execution). The Propose form states
//: what a proposal written NOW would bind -- the latest document under the
//: step's instruction reference -- and the Confirm form states what the
//: STANDING proposal bound: the document standing when it was written, which
//: nothing published since can replace. No document means the file road, and
//: that is named too.
const INSTRUCTION_FIELD = "instruction_ref";

function instructionRef(held) {
  const found = (object(held) || {})[INSTRUCTION_FIELD];
  return typeof found === "string" ? found : null;
}

function byteLength(value) {
  return new TextEncoder().encode(value).length;
}

function instructionFacts(ref, bound, standing) {
  if (ref === null) return [];
  const label = `Instruction ${ref}`;
  if (bound === null) {
    return [fact(label, "no durable document"), note(standing
      ? `No document stood under ${ref} when this proposal was written, so `
        + `the machine's instructions/${ref}.md is read if it exists and the `
        + "attempt is refused before anything is spawned if not."
      : `No document stands under ${ref} in this run, so a proposal made now `
        + `binds the machine's instructions/${ref}.md if it exists -- or is `
        + "refused before anything is spawned. Publish a document under "
        + `${ref} below, and a proposal made after that binds it.`)];
  }
  return [fact(label, `durable document ${show(bound.artifact_id)} · `
    + `${byteLength(text(bound.content))} bytes · written `
    + `${show(bound.created_at)}`), note(standing
    ? "The one standing when this proposal was written: confirming this "
      + "proposal runs it. A document published since is durable and is not "
      + "what runs; the newest one standing is bound by the next proposal "
      + "made on this step, once this attempt has answered."
    : "The one standing now: a proposal made now binds it, and a document "
      + "published after that proposal is not what runs.")];
}

//: WHICH DOCUMENTS A STEP READS, one fact per input reference, bound at the
//: same journal position as the instruction (`ArtifactHandoff.bound`): the
//: Propose form names the newest under each reference now, the Confirm form
//: the one standing when the proposal was written. A reference under which
//: nothing stands is said so: the attempt is refused before anything is
//: spawned rather than run on nothing.
function inputFacts(refs, lookup, standing) {
  if (!refs.length) return [];
  return [...refs.map((ref) => {
    const bound = lookup(ref);
    return fact(`Input ${ref}`, bound === null
      ? "no durable document -- the attempt is refused before anything is spawned"
      : `durable document ${show(bound.artifact_id)} · `
        + `${byteLength(text(bound.content))} bytes · written `
        + `${show(bound.created_at)}`);
  }), note(standing
    ? "Each input is the document standing when this proposal was written; "
      + "the child reads exactly these, whatever is published since."
    : "Each input is the newest document standing under its reference now: "
      + "a proposal made now binds these, and one published after it is not "
      + "what the child reads.")];
}

//: What the PLAN decided about this step, drawn read-only. Every one of these
//: travels into the body exactly as it is shown: there is no control here that
//: could make the screen and the wire disagree.
function planFacts(node, runtime, detail) {
  const ref = instructionRef(node.arguments);
  return [
    fact("Step", `${show(node.title)} · ${show(node.node_id)}`),
    fact("Instance", node.instance_id),
    fact("Capability", node.capability),
    fact("Arguments", canonicalJson(node.arguments)),
    note("The arguments are the plan's own bytes. The server refuses a "
      + "proposal that does not repeat them, so they are shown rather than "
      + "offered."),
    ...instructionFacts(ref, ref === null ? null
      : latestDocument(rows(detail.records), ref), false),
    ...inputFacts(inputRefs(node.capability, node.arguments),
      (input) => latestDocument(rows(detail.records), input), false),
    fact("Longest this may run", `${timeoutOf(node)}s`),
    note(TIMEOUT_NOTE),
    ...verificationFacts(node, detail, timeoutOf(node)),
    fact("Attempt id", attemptId(node, runtime)),
    fact("Scope", SCOPE),
    note(SCOPE_NOTE),
  ];
}

// Identity and frozen model come from this run's controls, never the roster
// of another workflow. Both Propose and Confirm state the extra paid action.
function verificationFacts(node, detail, ceiling) {
  if (typeof node.verifier_instance_id !== "string") {
    return [note(SAME_ADAPTER_VERIFICATION)];
  }
  const controls = object(detail.controls) || {};
  const binding = rows(controls.instances).find(
    (row) => row.instance_id === node.verifier_instance_id);
  const who = binding ? `${binding.instance_id} · ${binding.adapter_id} · `
    + (binding.model === null ? "provider default" : show(binding.model))
    : `${node.verifier_instance_id} · binding not available in this read`;
  return [fact("Independent verifier", who),
    fact("Verification materials", VERIFICATION_MATERIALS[node.capability]),
    note(VERIFICATION_FRAME_NOTE),
    fact("Task time ceilings", `${ceiling}s for the attempt + ${ceiling}s `
      + `for one check (2 × ${ceiling}s = ${2 * ceiling}s combined task time). `
      + "Bounded version preflights and setup add wall-clock time. "
      + "This run's budget must cover both task ceilings."),
    note(VERIFICATION_OUTPUT_NOTE)];
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

//: Whether a write for THIS step of THIS run is in flight: membership in the
//: run screen's `writes`, keyed by run and step. No read, no change of run and
//: no change of draft alters that record -- only the write's own end does --
//: so a second press is impossible whatever else happened (R07A of the review
//: of `8dec0e4`; the owner's control across navigation), and a press on
//: ANOTHER step is not shut by it: one press must not grey every step.
function writingOf(state, detail, node) {
  const writes = object((object(state.runs) || {}).writes) || {};
  return Object.hasOwn(writes, `${runOf(detail)}/${node.node_id}`);
}

//: What the person SEES in the control being replaced, carried into the one
//: drawn in its place. A render lands whenever a frame does, and a frame can
//: land in the middle of a word: the draft holds only what `change` has
//: committed, so a control drawn from the draft alone dropped the letters
//: typed since the last blur -- measured on the propose road, `release-owner`
//: reached the wire as `er`, `r` and `ner`. The predecessor is the focused
//: control of the SAME form, found while it is still on the page.
function liveValue(step, name, fallback) {
  const active = document.activeElement;
  if (!active || !active.getAttribute
      || active.getAttribute("name") !== name
      || typeof active.value !== "string") {
    return fallback;
  }
  const form = active.closest("[data-step]");
  return form !== null && form.getAttribute("data-step") === step
    ? active.value : fallback;
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

function proposeForm(node, runtime, detail, state, handlers, authority) {
  const draft = draftFor(state, node);
  const step = `propose:${show(node.node_id)}`;
  const submit = handlerOf(handlers, "proposeStep");
  const wire = wireFor("proposeStep", `propose:${node.node_id}`,
    editorFor(node, draft !== null, handlers), submit,
    state.connection === "open", writingOf(state, detail, node));
  const shut = whyNoAdapter(detail, node);
  const stops = shut === null ? whyNotProposable(draft) : shut;
  const form = element("form", {className: "studio-step", "data-step": step},
    [element("h4", {text: "Propose this step"}), note(PROPOSED_NOTE),
      ...(authority.permits === "proposals"
        ? [proposedUnder(authority.mode)] : []),
      ...planFacts(node, runtime, detail),
      textControl("proposed_by", "proposedBy", liveValue(step, "proposed_by",
        draft === null ? "" : text(draft.proposedBy)), wire.edit,
      "Proposed by", {maxlength: "128", pattern: ID_PATTERN, required: ""}),
      textControl("rationale", "rationale", liveValue(step, "rationale",
        draft === null ? "" : text(draft.rationale)), wire.edit,
      `Why (up to ${RATIONALE_LIMIT} characters)`,
      {maxlength: String(RATIONALE_LIMIT)}),
      ...submitControl("Propose this step", stops, wire)]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (stops !== null || submit === null || wire.shut) return;
    submit({runId: runOf(detail), nodeId: node.node_id,
      generation: draft.generation, body: proposalBody(node, runtime, draft)});
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
// Age alone does not stale a proposal: freshness judges the confirmation.
// Material binding is separate, explicitly revisioned, and cannot be claimed
// for an older record. `Proposed at` stays as history, not an expiry verdict.
function proposalFacts(proposal, detail) {
  const ref = instructionRef(proposal.arguments);
  const bound = proposal.input_binding === MATERIAL_BINDING;
  return [
    fact("Proposal", proposal.proposal_id),
    fact("Proposed at", proposal.proposed_at),
    fact("Proposed by", proposal.proposed_by),
    fact("Why", proposal.rationale),
    fact("Capability", proposal.capability),
    fact("Arguments", canonicalJson(proposal.arguments)),
    ...(bound ? instructionFacts(ref, ref === null ? null : boundDocument(
      rows(detail.records), proposal.proposal_id, ref), true) : []),
    ...(bound ? inputFacts(inputRefs(proposal.capability, proposal.arguments),
      (input) => boundDocument(rows(detail.records), proposal.proposal_id,
        input), true) : [note(UNVERSIONED_MATERIALS)]),
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
  const step = `confirm:${show(node.node_id)}`;
  const submit = handlerOf(handlers, "confirmStep");
  const wire = wireFor("confirmStep", `confirm:${node.node_id}`,
    editorFor(node, draft !== null, handlers), submit,
    state.connection === "open", writingOf(state, detail, node));
  const shut = whyNoAdapter(detail, node);
  const stops = shut === null ? whyNotConfirmable(draft) : shut;
  const form = element("form", {className: "studio-step", "data-step": step},
    [element("h4", {text: "Confirm this proposal"}), note(REQUESTED_NOTE),
      ...proposalFacts(proposal, detail),
      ...verificationFacts(node, detail, proposal.timeout_seconds),
      textControl("confirmed_by", "confirmedBy", liveValue(step, "confirmed_by",
        draft === null ? "" : text(draft.confirmedBy)), wire.edit,
      "Confirmed by", {maxlength: "128", pattern: ID_PATTERN, required: ""}),
      ...submitControl("Confirm and authorize", stops, wire)]);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (stops !== null || submit === null || wire.shut) return;
    submit({runId: runOf(detail), nodeId: node.node_id,
      generation: draft.generation, body: confirmBody(proposal, draft)});
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
 * standing on it is confirmed, and every other phase proposes -- within what
 * the run's frozen authority permits (`PERMITS`): an observe run is offered
 * neither and told where authority is granted; a propose or policy run is
 * offered the proposal and, once one stands, told that nothing here confirms
 * it; a confirm run is offered both.
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
  const authority = authorityOf(detail);
  if (authority.permits === "nothing") {
    return [nothingPermitted(authority)];
  }
  if (runtime.phase === "proposed") {
    if (needsMaterialReproposal(standingProposal(detail, node.node_id), detail)) {
      return [note(REBIND_MATERIALS),
        ...proposeForm(node, runtime, detail, state, handlers, authority)];
    }
    return authority.permits === "confirmations"
      ? confirmForm(node, detail, state, handlers)
      : [proposalsOnly(authority)];
  }
  return proposeForm(node, runtime, detail, state, handlers, authority);
}
