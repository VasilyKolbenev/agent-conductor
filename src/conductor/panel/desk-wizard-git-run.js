"use strict";
// The git block of step 2 as the wizard's state holds it: one press is one request, the answer is
// folded back, a lost answer is read and never repeated, and everything the view draws is a
// function of the one git read and of the `git` slice (`initialGit` makes it).
//
// The rules (lane L's contract, sections 4 to 6):
//   - a press while a request is in flight changes nothing and asks nothing (one press, one
//     request), and the ask carries the number of its press, so a second press can never be handed
//     out under an old id;
//   - what a press may be is judged here, not in the view: `pressBlock` names the first thing in
//     its way (the desk has no door for the route, the confirm's switch is shut, the project is
//     only open for viewing, the read is out, the control is not offered, a request works, the
//     name is not a name, there is no preview) and the view writes that reason beside the control;
//   - an answer the desk did not read as the route's closed table is LOST: the body is never
//     resent, the git read is dropped and asked again (the one thing the desk repeats by itself),
//     the preview stays, and the read says whether the first commit is pending, done or not
//     recorded. A lost answer is not worded as a cancel or as a failure;
//   - after every other answer but a locked index (nothing changed) and the desk's own door turning
//     the press away (nothing was sent) the read is asked again too.
import {evolve} from "./desk-wizard-base.js";
import {isActor} from "./desk-wizard-launch.js";
import {gitFacts} from "./desk-wizard-materials.js";
import {GIT_SETUP_CODES, GIT_SETUP_REASONS, KINDS, MANUAL_REASONS, MODES, REFUSAL_ACTIONS,
  UNSENT_CODES, WARNING_WORDS, classify, confirmBody, continueBody, pendingOf, previewBody,
  signCommands, stepBody} from "./desk-wizard-git.js";

//: Why a control is drawn disabled, in the order they are judged.
export const BLOCK_WORDS = Object.freeze(["door_missing", "confirm_door_closed",
  "project_not_active", "git_reading", "not_offered", "busy", "actor_invalid", "preview_missing"]);
//: The closed words of the block, by family: each is `wizard.first.<family>.<word>` in the
//: catalogue (the other codes are `error.<code>` of the shared notices).
export const FIRST_WORDS = Object.freeze({why: BLOCK_WORDS,
  lost: Object.freeze(["head", "reading", "pending", "done", "none", "other", "nothing_written"]),
  busy: KINDS, done: Object.freeze(["init", "exclude", "confirm", "signature_present"]),
  unsent: UNSENT_CODES, next: GIT_SETUP_REASONS, codes: GIT_SETUP_CODES, manual: MANUAL_REASONS,
  warning: WARNING_WORDS,
  pending: Object.freeze(["unfinished", "awaiting_signature", "damaged", "unreadable"]),
  mode: Object.freeze([...MODES, "starter"])});

const CONTINUABLE = Object.freeze(["unfinished", "awaiting_signature"]);
//: An answer that makes the standing preview useless: the files or settings moved, the branch
//: cannot take the signed road, or the wait for a signature is stored and takes over.
const SPENDS_PREVIEW = Object.freeze(["paths_changed", "signing_ref_unsupported",
  "signing_required"]);

function record(value) {
  return value !== null && typeof value === "object";
}

//: What the one git read says, in the words the block needs: the state, the pending operation
//: (only in `unborn` and `repo`, where the server gives one) and the exclusion block's state.
function readOf(state) {
  const read = state.reads.git;
  const found = pendingOf(read);
  const facts = gitFacts(read, state.mode, found);
  const git = read && read.status === "ok" && record(read.payload?.git) ? read.payload.git : {};
  return {state: facts.state, pending: facts.pending === null ? null : found,
    exclude: typeof git.exclude === "string" ? git.exclude : null};
}

const previewNow = (git) => (git.preview !== null && git.preview.mode === git.mode
  ? git.preview : null);
const firstPanel = (read, git) => git.panel === "first_commit" && read.state === "unborn"
  && read.pending === null;
const OFFERED = Object.freeze({
  init: (read) => read.state === "not_git",
  exclude: (read) => ["repo", "unborn"].includes(read.state) && read.exclude === "deferred",
  preview: (read, git) => firstPanel(read, git),
  confirm: (read, git) => firstPanel(read, git),
  continue: (read) => read.pending !== null && CONTINUABLE.includes(read.pending.state)});

function blockOf(state, kind, read) {
  const git = state.git;
  if (!git.door) return "door_missing";
  if ((kind === "confirm" || kind === "continue") && !git.open) return "confirm_door_closed";
  if (state.mode.view) return "project_not_active";
  if (read.state === "reading") return "git_reading";
  if (!OFFERED[kind](read, git)) return "not_offered";
  if (git.sending !== null) return "busy";
  if (kind !== "preview" && !isActor(state.launch.actor)) return "actor_invalid";
  return kind === "confirm" && previewNow(git) === null ? "preview_missing" : null;
}

/** The first thing in the way of pressing `kind`, or null when the press may go. */
export function pressBlock(state, kind) {
  return Object.hasOwn(OFFERED, kind) ? blockOf(state, kind, readOf(state)) : "not_offered";
}

// -- what the view draws --------------------------------------------------------------------

function confirmVerdict(read) {
  if (read.pending !== null) return "pending";
  return read.state === "repo" ? "done" : (read.state === "unborn" ? "none" : "other");
}

function stepVerdict(kind) {
  return (read) => {
    if (!["repo", "unborn"].includes(read.state)) {
      return kind === "init" && read.state === "not_git" ? "none" : "other";
    }
    return kind === "init" || read.exclude !== "deferred" ? "done" : "none";
  };
}

const VERDICTS = Object.freeze({confirm: confirmVerdict, continue: confirmVerdict,
  init: stepVerdict("init"), exclude: stepVerdict("exclude")});

//: What the read says now about a press whose answer was lost. A preview wrote nothing, so it
//: needs no read to be told so.
function verdictOf(kind, read) {
  if (kind === "preview") return "wizard.first.lost.nothing_written";
  return `wizard.first.lost.${read.state === "reading" ? "reading" : VERDICTS[kind](read)}`;
}

function resultFacts(result, read) {
  if (result === null) return null;
  const facts = {...result, notice: null, next: null, action: null, verdict: null};
  if (result.status === "unsent") facts.notice = `wizard.first.unsent.${result.code}`;
  if (result.status === "lost") facts.verdict = verdictOf(result.kind, read);
  if (result.status !== "refused") return facts;
  const reason = result.reason;
  return {...facts, notice: reason === null ? `error.${result.code}` : `git_setup.reason.${reason}`,
    next: reason === null ? null : `wizard.first.next.${reason}`,
    action: reason === null ? "none" : REFUSAL_ACTIONS[reason]};
}

/** Everything the view draws, from the state alone (the read is the state's). */
export function firstFacts(state) {
  const git = state.git, read = readOf(state), view = state.mode.view;
  const waits = read.pending !== null && CONTINUABLE.includes(read.pending.state);
  const signing = read.pending?.state === "awaiting_signature" ? read.pending.signing : null;
  const deferred = OFFERED.exclude(read) && !view;
  const blocks = Object.fromEntries(Object.keys(OFFERED).map((kind) => [kind,
    blockOf(state, kind, read)]));
  return {phase: git.sending === null ? "idle" : "busy", busy: git.sending?.kind ?? null,
    state: read.state, mode: git.mode, modes: state.mode.starterId === null ? [...MODES]
      : ["empty"], pending: read.pending, commands: signing === null ? null : signCommands(signing),
    preview: previewNow(git), list: git.list, actor: state.launch.actor, blocks,
    result: resultFacts(git.result, read),
    shown: {panel: git.panel === "first_commit" && read.pending === null
      && ["unborn", "reading"].includes(read.state), connect: read.state === "not_git" && !view,
    exclude: deferred, pending: read.pending !== null, continue: waits}};
}

// -- the presses ----------------------------------------------------------------------------

const NAMES = Object.freeze({init: "git_init", exclude: "git_exclude", preview: "git_preview",
  confirm: "git_confirm", continue: "git_confirm"});
const BODIES = Object.freeze({
  init: (state) => stepBody("init", state.launch.actor),
  exclude: (state) => stepBody("exclude", state.launch.actor),
  preview: (state) => previewBody(state.git.mode),
  confirm: (state) => confirmBody(state.git.mode, previewNow(state.git), state.launch.actor),
  continue: (state) => continueBody(readOf(state).pending.terms, state.launch.actor)});

function press(kind) {
  return (state) => {
    if (pressBlock(state, kind) !== null) return state;
    const git = state.git, seq = git.seq + 1, id = `write:git:${kind}:${seq}`;
    const ask = {id, name: NAMES[kind], door: "write", target: "gitSetup", subject: null,
      body: BODIES[kind](state)};
    return evolve(state, {git: {...git, seq, result: null,
      sending: {id, kind, mode: git.mode, ask}}});
  };
}

//: A change of the block's own view (not a press): nothing while a request works or in view.
function tidy(change) {
  return (state, event) => (state.git.sending !== null || state.mode.view ? state
    : change(state, event));
}

function start(state) {
  const read = readOf(state);
  if (state.git.panel !== null || read.state !== "unborn" || read.pending !== null) return state;
  const mode = state.mode.starterId === null ? "snapshot" : "empty";
  return evolve(state, {git: {...state.git, panel: "first_commit", mode, preview: null,
    list: false, result: null}});
}

function chooseMode(state, event) {
  const git = state.git;
  const allowed = state.mode.starterId === null ? MODES : ["empty"];
  if (git.panel === null || !allowed.includes(event.mode) || git.mode === event.mode) return state;
  return evolve(state, {git: {...git, mode: event.mode, preview: null, list: false,
    result: null}});
}

function toggleList(state) {
  return previewNow(state.git) === null ? state
    : evolve(state, {git: {...state.git, list: !state.git.list}});
}

/** The events of the block, merged into the model's one closed table. */
export const GIT_HANDLERS = Object.freeze({
  "git-start": tidy(start), "git-mode": tidy(chooseMode), "git-list": tidy(toggleList),
  "git-preview": tidy(press("preview")), "git-init": tidy(press("init")),
  "git-exclude": tidy(press("exclude")), "git-confirm": tidy(press("confirm")),
  "git-continue": tidy(press("continue"))});

/** The write ask of the press in flight (handed out once, by its id), or nothing. */
export function gitWanted(state) {
  return state.git.sending === null ? [] : [state.git.sending.ask];
}

/** Whether a request works: closing the window then asks first. */
export function closeBusy(state) {
  return state.git.sending !== null;
}

// -- the answers ----------------------------------------------------------------------------

//: The git read is the only thing the desk asks again by itself: drop it and its ask id.
function dropGitRead(state) {
  const {git: _read, ...reads} = state.reads;
  return evolve(state, {reads, asked: state.asked.filter((id) => id !== "read:git")});
}

function outcome(found) {
  return {status: found.status, kind: found.kind, code: found.code ?? null,
    reason: found.reason ?? null, tool: found.tool ?? null, receipt: found.receipt ?? null,
    cause: found.cause ?? null};
}

//: A request that had the window waiting for it is over: a dialog that asked "close anyway?" for
//: no other reason has nothing left to ask.
const stillAsking = (state) => (state.closing === "confirm" && state.materials.items.length === 0
  ? null : state.closing);

function settle(state, found) {
  const git = {...state.git, sending: null}, closing = stillAsking(state);
  if (found.status === "done" && found.kind === "preview") {
    return evolve(state, {closing, git: {...git, preview: found.preview, result: null}});
  }
  const spent = found.status === "done" ? ["confirm", "continue"].includes(found.kind)
    : SPENDS_PREVIEW.includes(found.reason);
  const next = evolve(state, {closing, git: {...git, result: outcome(found),
    preview: spent ? null : git.preview, list: spent ? false : git.list}});
  const nothing = found.status === "unsent" || found.reason === "index_locked";
  return nothing ? next : dropGitRead(next);
}

/** Fold the answer of the press in flight in; an answer to anything else changes nothing. */
export function landGit(state, ask, result) {
  const sending = state.git.sending;
  if (sending === null || !record(ask) || sending.ask.id !== ask.id) return state;
  return settle(state, classify(sending.kind, result, sending.mode));
}
