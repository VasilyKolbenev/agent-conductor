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
//   - after every other answer but the desk's own door turning the press away (nothing was sent)
//     the read is asked again too, a locked index included: the stored operation can have moved
//     before the lock was met, and a continue is always answered from the stored terms;
//   - the starter's «Создать репозиторий: 2 шага» is ONE press of two requests, never two at once:
//     `init`, then the read, then the empty first commit. The second request is handed out only
//     when the route gave its exact receipt for the first AND the read says the repository is
//     there with nothing pending; a first answer of any other kind ends the chain, even when the
//     next read shows the repository (a lost answer is read, never turned into a go-ahead). The
//     wait for the read between the two is as busy as a request: every event is a no-op in it.
import {evolve} from "./desk-wizard-base.js";
import {isActor} from "./desk-wizard-launch.js";
import {gitFacts} from "./desk-wizard-materials.js";
import {GIT_SETUP_CODES, GIT_SETUP_REASONS, KINDS, MANUAL_REASONS, MODES, REFUSAL_ACTIONS,
  UNSENT_CODES, WARNING_WORDS, classify, confirmBody, continueBody, pendingOf, previewBody,
  signCommands, stepBody} from "./desk-wizard-git.js";

//: Why a control is drawn disabled, in the order they are judged.
export const BLOCK_WORDS = Object.freeze(["door_missing", "confirm_door_closed",
  "project_not_active", "git_reading", "not_offered", "busy", "actor_invalid", "preview_missing"]);
//: A reason that asks for another line of what to do next when the press was made in a wait for
//: the person's signature: the shared notice says the repository has a first commit, and the
//: wait's own line says what the branch must hold instead.
const WAIT_NEXT = Object.freeze({head_exists: "head_exists_signing"});
//: How a link of the starter's chain stands, and why the second was never started: the first did
//: not come to a done answer (refused, lost, turned away), or the read after it did not allow it.
const CHAIN_STATUS = Object.freeze(["todo", "working", "done", "refused", "lost", "unsent",
  "skipped"]);
const CHAIN_SKIPPED = Object.freeze(["first_refused", "first_lost", "first_unsent", "read"]);

//: The closed words of the block, by family: each is `wizard.first.<family>.<word>` in the
//: catalogue (the other codes are `error.<code>` of the shared notices).
export const FIRST_WORDS = Object.freeze({why: BLOCK_WORDS,
  lost: Object.freeze(["head", "reading", "pending", "done", "none", "other", "nothing_written"]),
  busy: Object.freeze([...KINDS, "chain_read"]), chain_status: CHAIN_STATUS,
  chain_skipped: CHAIN_SKIPPED,
  done: Object.freeze(["init", "exclude", "confirm", "signature_present"]),
  unsent: UNSENT_CODES, next: Object.freeze([...GIT_SETUP_REASONS, ...Object.values(WAIT_NEXT)]),
  codes: GIT_SETUP_CODES, manual: MANUAL_REASONS,
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
//: Whether a request works: one is in flight, or the starter's chain waits for the read that lets
//: its second request go. Either way nothing else may be pressed.
const working = (git) => git.sending !== null || git.chain?.stage === "read";
const OFFERED = Object.freeze({
  init: (read) => read.state === "not_git",
  exclude: (read) => ["repo", "unborn"].includes(read.state) && read.exclude === "deferred",
  preview: (read, git) => firstPanel(read, git),
  confirm: (read, git) => firstPanel(read, git),
  continue: (read) => read.pending !== null && CONTINUABLE.includes(read.pending.state),
  chain: (read, _git, state) => state.mode.starterId !== null && read.state === "not_git"});
//: The presses that end in a confirm of the first commit: they wait behind its switch.
const CONFIRMS = Object.freeze(["confirm", "continue", "chain"]);

function blockOf(state, kind, read) {
  const git = state.git;
  if (!git.door) return "door_missing";
  if (CONFIRMS.includes(kind) && !git.open) return "confirm_door_closed";
  if (state.mode.view) return "project_not_active";
  if (read.state === "reading") return "git_reading";
  if (!OFFERED[kind](read, git, state)) return "not_offered";
  if (working(git)) return "busy";
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

//: The word of the line that says what to do next: the reason's own, or the wait's where the
//: press was made in a wait for a signature and the reason has one.
const nextWord = (result) => (result.waiting && Object.hasOwn(WAIT_NEXT, result.reason)
  ? WAIT_NEXT[result.reason] : result.reason);

function resultFacts(result, read) {
  if (result === null) return null;
  const facts = {...result, notice: null, next: null, action: null, verdict: null};
  if (result.status === "unsent") facts.notice = `wizard.first.unsent.${result.code}`;
  if (result.status === "lost") facts.verdict = verdictOf(result.kind, read);
  if (result.status !== "refused") return facts;
  const reason = result.reason;
  return {...facts, notice: reason === null ? `error.${result.code}` : `git_setup.reason.${reason}`,
    next: reason === null ? null : `wizard.first.next.${nextWord(result)}`,
    action: reason === null ? "none" : REFUSAL_ACTIONS[reason]};
}

// -- the starter's chain --------------------------------------------------------------------

//: How a link stands: its outcome's own word once it has one, else working while its request is
//: out, skipped once the chain is over without it, else not started yet.
function linkStatus(chain, key) {
  const said = chain[key];
  if (said !== null) return said.status;
  if (chain.stage === (key === "first" ? "init" : "commit")) return "working";
  return chain.stage === "over" ? "skipped" : "todo";
}

//: Why the second link was never started. It is only asked of a chain that is over, which has the
//: first link's outcome: that was not done, or it was and the read did not allow the second.
function skippedWhy(chain) {
  return chain.first.status === "done" ? "read" : `first_${chain.first.status}`;
}

function chainFacts(chain, read) {
  if (chain === null) return null;
  const link = (name, key) => {
    const status = linkStatus(chain, key);
    return {link: name, status, result: chain[key] === null ? null : resultFacts(chain[key], read),
      skipped: key === "second" && status === "skipped" ? skippedWhy(chain) : null};
  };
  //: The first commit by hand is the way on whenever the read now shows a repository with no
  //: commit and nothing pending, whatever stopped the chain.
  const byHand = chain.stage === "over" && chain.second?.status !== "done"
    && read.state === "unborn" && read.pending === null;
  return {stage: chain.stage, rows: [link("init", "first"), link("commit", "second")], byHand};
}

//: The word of the wait: the kind of the request in flight, or the read between the chain's links.
const busyWord = (git) => git.sending?.kind ?? (git.chain?.stage === "read" ? "chain_read" : null);

/** Everything the view draws, from the state alone (the read is the state's). */
export function firstFacts(state) {
  const git = state.git, read = readOf(state), view = state.mode.view;
  const waits = read.pending !== null && CONTINUABLE.includes(read.pending.state);
  const signing = read.pending?.state === "awaiting_signature" ? read.pending.signing : null;
  const deferred = OFFERED.exclude(read) && !view;
  const blocks = Object.fromEntries(Object.keys(OFFERED).map((kind) => [kind,
    blockOf(state, kind, read)]));
  return {phase: working(git) ? "busy" : "idle", busy: busyWord(git),
    starter: state.mode.starterId !== null, chain: chainFacts(git.chain, read),
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
  continue: (state) => continueBody(readOf(state).pending.terms, state.launch.actor),
  //: The chain's second link: an empty first commit, which needs no preview (the repository does
  //: not exist when the chain is pressed) and carries a null digest by the contract.
  empty: (state) => confirmBody("empty", null, state.launch.actor)});

//: The request of one press, numbered by its press so that no id is ever handed out twice: `kind`
//: names its ask and its answer, `body` the body it is made from, `link` the chain's link or null.
function sendingFor(state, kind, seq, body, link = null) {
  const id = `write:git:${kind}:${seq}`;
  const ask = {id, name: NAMES[kind], door: "write", target: "gitSetup", subject: null,
    body: BODIES[body](state)};
  // Whether the person pressed in a wait for a signature: the answer's words are judged by it.
  const waiting = readOf(state).pending?.state === "awaiting_signature";
  return {id, kind, mode: state.git.mode, ask, waiting, link};
}

function press(kind) {
  return (state) => {
    if (pressBlock(state, kind) !== null) return state;
    const git = state.git, seq = git.seq + 1;
    return evolve(state, {git: {...git, seq, result: null, chain: null,
      sending: sendingFor(state, kind, seq, kind)}});
  };
}

//: The starter's chain: the first link is `init`; the second goes when the read allows it.
function pressChain(state) {
  if (pressBlock(state, "chain") !== null) return state;
  const git = state.git, seq = git.seq + 1;
  return evolve(state, {git: {...git, seq, result: null,
    chain: {stage: "init", first: null, second: null},
    sending: sendingFor(state, "init", seq, "init", "first")}});
}

//: A change of the block's own view (not a press): nothing while a request works or in view.
function tidy(change) {
  return (state, event) => (working(state.git) || state.mode.view ? state
    : change(state, event));
}

function start(state) {
  const read = readOf(state);
  if (state.git.panel !== null || read.state !== "unborn" || read.pending !== null) return state;
  const mode = state.mode.starterId === null ? "snapshot" : "empty";
  return evolve(state, {git: {...state.git, panel: "first_commit", mode, preview: null,
    list: false, result: null, chain: null}});
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
  "git-continue": tidy(press("continue")), "git-chain": tidy(pressChain)});

/** The write ask of the press in flight (handed out once, by its id), or nothing. */
export function gitWanted(state) {
  return state.git.sending === null ? [] : [state.git.sending.ask];
}

/** Whether a request works, or the chain waits for its read: closing then asks first. */
export function closeBusy(state) {
  return working(state.git);
}

//: The chain's stages in which closing ends the press: the second request is only ever made from
//: an answer the open window receives, so it is never sent. In `commit` it has already gone.
const CHAIN_ENDS_ON_CLOSE = Object.freeze(["init", "read"]);

/** The key of the line the close dialog shows for a request that works (see `closeBusy`). */
export function closeBusyWord(state) {
  return CHAIN_ENDS_ON_CLOSE.includes(state.git.chain?.stage) ? "wizard.first.close_chain"
    : "wizard.first.close_busy";
}

// -- the answers ----------------------------------------------------------------------------

//: The git read is the only thing the desk asks again by itself: drop it and its ask id.
function dropGitRead(state) {
  const {git: _read, ...reads} = state.reads;
  return evolve(state, {reads, asked: state.asked.filter((id) => id !== "read:git")});
}

function outcome(found, waiting) {
  return {status: found.status, kind: found.kind, code: found.code ?? null,
    reason: found.reason ?? null, tool: found.tool ?? null, receipt: found.receipt ?? null,
    cause: found.cause ?? null, waiting};
}

//: A request that had the window waiting for it is over: a dialog that asked "close anyway?" for
//: no other reason has nothing left to ask.
const stillAsking = (state) => (state.closing === "confirm" && state.materials.items.length === 0
  ? null : state.closing);

//: A link of the starter's chain is over. Its outcome is kept in the chain (not in `result`), and
//: only the route's exact answer to the first link leaves the chain waiting for the read that lets
//: the second go; any other answer ends it. The read is asked again after every answer the
//: desk's own door did not turn away.
function settleLink(state, found) {
  const link = state.git.sending.link;
  const stage = link === "first" && found.status === "done" ? "read" : "over";
  const next = evolve(state, {closing: stillAsking(state), git: {...state.git, sending: null,
    result: null, chain: {...state.git.chain, stage, [link]: outcome(found, false)}}});
  return found.status === "unsent" ? next : dropGitRead(next);
}

function settle(state, found) {
  const sending = state.git.sending, closing = stillAsking(state);
  if (sending.link !== null) return settleLink(state, found);
  const git = {...state.git, sending: null};
  if (found.status === "done" && found.kind === "preview") {
    return evolve(state, {closing, git: {...git, preview: found.preview, result: null}});
  }
  const spent = found.status === "done" ? ["confirm", "continue"].includes(found.kind)
    : SPENDS_PREVIEW.includes(found.reason);
  const next = evolve(state, {closing, git: {...git, result: outcome(found, sending.waiting),
    preview: spent ? null : git.preview, list: spent ? false : git.list}});
  return found.status === "unsent" ? next : dropGitRead(next);
}

/** Fold the answer of the press in flight in; an answer to anything else changes nothing. */
export function landGit(state, ask, result) {
  const sending = state.git.sending;
  if (sending === null || !record(ask) || sending.ask.id !== ask.id) return state;
  return settle(state, classify(sending.kind, result, sending.mode));
}

/**
 * Called when the git read has landed. A starter's chain that waits for it goes on with its second
 * link when the read says the repository is there with nothing pending (and the press may still be
 * made: the switch, the door, the name), and ends otherwise; with no chain waiting, nothing
 * changes.
 */
export function chainNext(state) {
  const git = state.git;
  if (git.chain?.stage !== "read") return state;
  const read = readOf(state);
  if (read.state === "reading") return state;
  const may = read.state === "unborn" && read.pending === null && git.door && git.open
    && !state.mode.view && isActor(state.launch.actor);
  if (!may) return evolve(state, {git: {...git, chain: {...git.chain, stage: "over"}}});
  const seq = git.seq + 1;
  return evolve(state, {git: {...git, seq, chain: {...git.chain, stage: "commit"},
    sending: sendingFor(state, "confirm", seq, "empty", "second")}});
}
