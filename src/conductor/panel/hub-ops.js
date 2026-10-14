"use strict";
// What the hub page says of an operation it follows after a press (spec 4.1.8, 4.6.4, 8.7): the
// recovery of a project, the recovery of a login, the copy of the shared profile. Each of them
// answers `202 {operation_id}`; the row at `GET /hub/operations/<id>` says how it ends.
//
// The first half is pure: a row to the sentence it is told in. A failed recovery that needs a
// restart or a preparation first carries one closed word in `detail.reason`, and the sentence of
// that word (`hub.reason.<kind>.<reason>`, the words lane H wrote) is the whole message: the bare
// words of the code say "restart", which is wrong for a record that needs a preparation first and
// for one whose boot environment changed. A reason the closed list does not know is the
// `not_proven` sentence, never advice to restart. A failed profile copy that met a project not
// closed properly carries `recovery_required` beside the code `subprocess_failed`, and the page
// says to recover it first. Nothing a command printed is ever said: the page reads one closed word
// and no text.
//
// The second half follows a row by its id through a door and a scheduler the page hands it (this
// module has no wire and no clock): a row is read at once, again when the hub says a step moved (a
// frame), and slowly while it runs as a net under the stream. One id is one row: the same operation
// answered again (a login recovery pressed twice) is not a second row.
import {codeWords, hubText} from "./hub-copy.js";

/** The kind of operation each write target of the page begins: the page follows these, no other. */
export const FOLLOWED = Object.freeze({projectRecover: "recover", loginRecover: "recover_login",
  projectProviders: "providers"});

//: The closed words of `detail.reason` for a recovery that needs a restart or a preparation: lane
//: H's list, held equal to its own by `tests/test_hub_ops.py`.
export const RECOVERY_REASONS = Object.freeze(["restart_needed", "prepare_needed",
  "other_environment", "not_proven"]);
//: The failed code, by kind, that carries one of those words.
const RESTART_CODE = Object.freeze({recover: "recovery_required",
  recover_login: "login_recovery_required"});
//: How long a running row waits before it is read again when no frame came: the stream is the main
//: road, this is the net under it.
const FOLLOW_MS = 5000;

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const say = (locale, key, params = {}) => ({key, text: hubText(locale, key, params)});

//: `running`, `done` or `failed` for a row of a followed kind in a state the page knows, else null.
function phaseOf(row) {
  if (!isObject(row) || !Object.values(FOLLOWED).includes(row.kind)) return null;
  return {running: "running", succeeded: "done", failed: "failed"}[row.state] ?? null;
}

//: A failure told by the clause of a code (a code the page has no word for has its own clause).
const refusedNote = (code, locale) => say(locale, "hub.op.failed",
  {reason: codeWords(locale, code)});

function failedNote(row, locale) {
  const reason = isObject(row.detail) && typeof row.detail.reason === "string"
    ? row.detail.reason : null;
  if (Object.hasOwn(RESTART_CODE, row.kind) && row.code === RESTART_CODE[row.kind]) {
    const word = RECOVERY_REASONS.includes(reason) ? reason : "not_proven";
    return say(locale, `hub.reason.${row.kind}.${word}`);
  }
  if (row.kind === "providers" && reason === "recovery_required") {
    return say(locale, "hub.reason.recovery_required");
  }
  return refusedNote(row.code, locale);
}

/**
 * What a row says: `{phase, key, text}`, or null for a row the page cannot read (not an object, a
 * kind it does not follow, a state it does not know). `key` is the catalogue key of the sentence.
 */
export function operationNote(row, locale) {
  const phase = phaseOf(row);
  if (phase === null) return null;
  if (phase === "running") return {phase, ...say(locale, "hub.op.running")};
  if (phase === "done") return {phase, ...say(locale, `hub.op.done.${row.kind}`)};
  return {phase, ...failedNote(row, locale)};
}

// -- following a row ---------------------------------------------------------------------------

//: The follower: the page's hooks and the rows it follows, by id. A row is read at once; while it
//: runs it is read again when a frame names it (`touch`) and, as a net under the stream, every
//: `FOLLOW_MS`. One read of a row is out at a time; a frame that comes during one asks for another.
function arm(follower, id, entry) {
  entry.timer = follower.ctx.schedule(() => poll(follower, id), FOLLOW_MS);
}

//: What an answer to a read of the row makes of it. A lost answer is read again and is never a
//: verdict. A read the hub refuses (it forgot the operation: a restart, or 50 later rows) ends the
//: row as `unreported`: how the operation ended is not known, so it is never said as failed. A row
//: the page cannot read ends it as failed.
function land(follower, id, entry, answer) {
  const {ctx, entries} = follower;
  if (entries.get(id) !== entry) return;
  if (answer.status === "unknown") {
    arm(follower, id, entry);
    return;
  }
  const known = phaseOf(answer.status === "accepted" ? answer.payload : null);
  const phase = known ?? (answer.status === "refused" ? "unreported" : "failed");
  Object.assign(entry, {phase, row: known === null ? null : answer.payload, code: answer.code});
  if (phase === "running") arm(follower, id, entry);
  if (phase === "done") entries.delete(id);
  if (phase !== "running") {
    ctx.settled({kind: entry.kind, phase,
      key: phase === "done" ? `hub.op.done.${entry.kind}` : null});
  }
  ctx.changed();
}

async function poll(follower, id) {
  const entry = follower.entries.get(id);
  if (entry === undefined || entry.phase !== "running") return;
  follower.ctx.cancel(entry.timer);
  if (entry.reading) {
    entry.again = true;
    return;
  }
  entry.reading = true;
  const answer = await follower.ctx.read("operation", {operation: id});
  entry.reading = false;
  land(follower, id, entry, answer);
  if (entry.again && entry.phase === "running" && follower.entries.get(id) === entry) {
    entry.again = false;
    poll(follower, id);
  }
}

function textOf(entry, locale) {
  if (entry.phase === "running") return say(locale, "hub.op.running").text;
  if (entry.phase === "unreported") return say(locale, "hub.op.unreported").text;
  return (entry.row === null ? refusedNote(entry.code, locale)
    : operationNote(entry.row, locale)).text;
}

/**
 * The follower of the operations a press began. `ctx` is `{read, schedule, cancel, changed,
 * settled}`: `read("operation", {operation})` is the page's door for the row, `schedule(call, ms)`
 * and `cancel(handle)` its timer, `changed()` asks the page to draw, and `settled({kind, phase,
 * key})` tells it a row ended (`done`: the key of the sentence; `failed` or `unreported`: null, and
 * the row stays until it is dismissed).
 */
export function createFollower(ctx) {
  const follower = {ctx, entries: new Map()};
  return Object.freeze({
    /** Follow `id`; false when it is already followed (the same operation answered again). */
    follow(kind, id, subject) {
      if (follower.entries.has(id)) return false;
      follower.entries.set(id, {kind, subject, phase: "running", row: null, code: null,
        timer: null, reading: false, again: false});
      ctx.changed();
      poll(follower, id);
      return true;
    },
    /** A frame named `id`: read it at once (nothing for an id nobody follows). */
    touch: (id) => poll(follower, id),
    /** Forget a row (a failed one the person has read). */
    dismiss(id) {
      const entry = follower.entries.get(id);
      if (entry === undefined) return;
      ctx.cancel(entry.timer);
      follower.entries.delete(id);
      ctx.changed();
    },
    /** The rows to draw: `{id, kind, subject, phase, text}` in the order they began. */
    rows: (locale) => [...follower.entries].map(([id, entry]) => ({id, kind: entry.kind,
      subject: entry.subject, phase: entry.phase, text: textOf(entry, locale)})),
  });
}
