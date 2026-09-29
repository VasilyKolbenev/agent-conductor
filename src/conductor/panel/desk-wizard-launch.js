"use strict";
// Step 6, «Запуск», as pure functions (spec 6.4.4-6.4.5): the terms card, what the owner may
// press, the countdown, and what happens to each answer.
//
// The card is the server's answer drawn as it came: the preview `{}` with its `budget` (7.8) and
// the slot of the queue read (4.4.6) decide what is shown and which button there is. Nothing here
// works out a limit, a duration or a count: the one arithmetic is the difference of two instants
// for the countdown, and a check that a number is a number. It imports only the stable spelling of
// a value and keeps no clock: the host says what time it is (`tick`).
//
// The slice (`launch`) holds: the owner's name (`actor`), the card (`preview`, its `digest`, its
// ordinal `card`, what `changed` when another replaced it and whether the owner has `seen` that),
// the reads it is drawn from (`reads.queue`, `.automation`, `.run`), the phase (review | starting |
// enqueuing | unknown | started | queued), a `note` or a `refusal` from the last answer, and the
// counters that make every ask's id (`previews`, `seq`, `attempts`).
import {stableJson as stable} from "./desk-wizard-digest.js";

export const MAX_REPEATS = 6;
const COUNTDOWN_CAP = 300;
const ACTOR = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const INSTANT = new RegExp("^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
  + "(?:\\.[0-9]+)?(?:Z|\\+00:00)$");
const SLOT_STATES = Object.freeze(["free", "busy", "stuck", "unavailable"]);
//: The lines of the card, top to bottom.
const CARD_LINES = Object.freeze(["actions", "time", "window", "steps", "harnesses", "receives"]);
//: Which line of the card each field of the terms is drawn on: a replaced card marks these lines.
const LINE_OF = Object.freeze({max_actions: "actions", max_action_seconds: "time",
  max_total_task_seconds: "time", duration_seconds: "window", node_limits: "steps",
  instruction_bindings: "receives", initial_input_bindings: "receives",
  provider_config_digest: "harnesses"});

function record(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function keysAre(value, names) {
  return record(value) && Object.keys(value).sort().join(",") === [...names].sort().join(",");
}

const whole = (value) => Number.isSafeInteger(value) && value >= 0;
const positive = (value) => whole(value) && value > 0;

/** A UTC instant as seconds since 1970 (null when it is not one): the countdown's only sum. */
export function epochSeconds(iso) {
  const found = typeof iso === "string" ? INSTANT.exec(iso) : null;
  if (found === null) return null;
  const [year, month, day, hour, minute, second] = found.slice(1).map(Number);
  const shifted = month <= 2 ? year - 1 : year;
  const era = Math.floor(shifted / 400), inEra = shifted - era * 400;
  const inYear = Math.floor((153 * (month + (month > 2 ? -3 : 9)) + 2) / 5) + day - 1;
  const inDays = inEra * 365 + Math.floor(inEra / 4) - Math.floor(inEra / 100) + inYear;
  return (era * 146097 + inDays - 719468) * 86400 + hour * 3600 + minute * 60 + second;
}

/** Whether a name may stand as the owner (the grammar of the gate decisions' actor). */
export function isActor(value) {
  return typeof value === "string" && ACTOR.test(value);
}

export function initialLaunch(actor) {
  return {actor, card: 0, preview: null, digest: null, changed: [], seen: true, now: null,
    repeats: 0, previews: 0, refreshWanted: false, repeatFailed: false, error: null,
    reads: {queue: null, automation: null, run: null}, seq: 0, phase: "idle", sending: null,
    note: null, refusal: null, result: null, settled: [], attempts: {}};
}

// -- the preview -------------------------------------------------------------------------

const PREVIEW_KEYS = ["budget", "preview_digest", "previewed_at", "provider_facts", "terms",
  "valid_until"];
const TERMS_KEYS = ["run_id", "contract", "config_digest", "graph_digest",
  "provider_config_digest", "source_prefix_digest", "node_limits", "instruction_bindings",
  "initial_input_bindings", "max_actions", "max_action_seconds", "max_total_task_seconds",
  "concurrency", "failure_handling", "duration_seconds"];
const BUDGET_KEYS = ["limits", "clean", "worst", "steps", "terms_draft", "spent", "exhausted",
  "inputs"];

function validTerms(terms, runId) {
  const rows = (list, names) => Array.isArray(list) && list.every((row) => keysAre(row, names));
  return keysAre(terms, TERMS_KEYS) && terms.run_id === runId && terms.contract === "bounded-run-v1"
    && ["max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds"]
      .every((name) => positive(terms[name]))
    && rows(terms.node_limits, ["node_id", "timeout_seconds", "max_attempts"])
    && rows(terms.instruction_bindings, ["node_id", "artifact_id", "content_digest"])
    && rows(terms.initial_input_bindings, ["artifact_ref", "artifact_id", "content_digest"]);
}

function validBudget(budget) {
  const count = (row) => keysAre(row, ["actions", "seconds"]) && whole(row.actions)
    && whole(row.seconds);
  const steps = ["step_id", "attempts", "timeout_seconds", "reserve_seconds", "clamped"];
  return keysAre(budget, BUDGET_KEYS) && keysAre(budget.limits, ["max_actions",
    "max_action_seconds", "max_total_task_seconds"]) && positive(budget.limits.max_actions)
    && count(budget.clean) && count(budget.worst) && Array.isArray(budget.steps)
    && budget.steps.every((row) => keysAre(row, steps)) && record(budget.terms_draft)
    && (budget.spent === null || (record(budget.spent) && whole(budget.spent.actions)
      && whole(budget.spent.seconds))) && typeof budget.exhausted === "boolean"
    && record(budget.inputs);
}

function validFacts(facts) {
  return facts === null || (keysAre(facts, ["providers"]) && Array.isArray(facts.providers)
    && facts.providers.every((row) => record(row) && record(row.config)
      && typeof row.config.provider_id === "string" && record(row.contract)));
}

/**
 * The server's preview `{}` answer, or null when it is not exactly that: the old five keys and
 * `budget`, a well-formed digest, two instants, the terms of this run, and a `Budget` in the
 * shape of 7.8.
 */
export function projectPreview(payload, runId) {
  const good = keysAre(payload, PREVIEW_KEYS) && validTerms(payload.terms, runId)
    && validBudget(payload.budget) && validFacts(payload.provider_facts)
    && DIGEST.test(payload.preview_digest) && epochSeconds(payload.previewed_at) !== null
    && epochSeconds(payload.valid_until) !== null;
  return good ? structuredClone(payload) : null;
}

//: The lines of the card whose terms changed between two previews, in the order the card draws
//: them (never in the order the server happened to spell its keys).
function changedLines(before, after) {
  const hit = new Set(Object.keys(LINE_OF).filter(
    (name) => stable(before.terms[name]) !== stable(after.terms[name])).map((n) => LINE_OF[n]));
  return CARD_LINES.filter((line) => hit.has(line));
}

/**
 * A preview taken in. The same digest keeps the card and restarts its countdown (an automatic
 * repeat is counted); another digest replaces it, marks the lines that changed and waits until the
 * owner has looked (`seen`); an answer that is not the server's shape is said so and draws nothing.
 */
export function takePreview(launch, payload, runId, auto) {
  const preview = projectPreview(payload, runId);
  if (preview === null) return {...launch, phase: "review", error: "preview_unreadable"};
  const base = {...launch, phase: "review", error: null, preview};
  if (launch.digest === preview.preview_digest) {
    return {...base, repeats: auto ? launch.repeats + 1 : 0};
  }
  const changed = launch.preview === null ? [] : changedLines(launch.preview, preview);
  return {...base, digest: preview.preview_digest, card: launch.card + 1, changed,
    seen: launch.preview === null, repeats: 0};
}

/**
 * The preview of the chain becomes the card. After edits made past an earlier card the reads it
 * is drawn from are asked again, since the run has moved on.
 */
export function adoptPreview(launch, payload, runId) {
  const stale = launch.reads.queue !== null || launch.reads.automation !== null;
  const base = stale ? {...launch, reads: {...launch.reads, queue: null, automation: null},
    seq: launch.seq + 1} : launch;
  return takePreview(base, payload, runId, false);
}

/** Seconds until the preview stops being fresh (at most 300); null while the clock is unknown. */
export function remaining(launch) {
  if (launch.preview === null || launch.now === null) return null;
  const now = epochSeconds(launch.now), until = epochSeconds(launch.preview.valid_until);
  return now === null || until === null ? null
    : Math.max(0, Math.min(COUNTDOWN_CAP, until - now));
}

const previewDue = (launch) => launch.phase === "review" && launch.preview !== null
  && (launch.refreshWanted || (remaining(launch) === 0 && !launch.repeatFailed
    && launch.repeats < MAX_REPEATS));

/** True when six repeats in a row have been made and the owner alone may ask again. */
export const repeatsSpent = (launch) => launch.repeats >= MAX_REPEATS
  && remaining(launch) === 0;

// -- the slot and the buttons ------------------------------------------------------------

/** The slot of the queue read, or null while it is unread. */
export function slotOf(launch) {
  return launch.reads.queue !== null && launch.reads.queue.status === "ok"
    ? launch.reads.queue.payload.slot : null;
}

const NONE = Object.freeze({shown: false, blocked: null});

//: What the slot allows (6.4.5): the two buttons, the link to release the slot, and the reason
//: when there is nothing to press.
function slotRow(slot) {
  const start = {shown: true, blocked: null}, enqueue = {shown: true, blocked: null};
  if (slot.state === "free") return {start, enqueue: NONE, release: false, why: null};
  if (slot.state === "busy") return {start: NONE, enqueue, release: false, why: null};
  if (slot.state === "stuck") return {start: NONE, enqueue, release: true, why: null};
  if (slot.reason_code === "project_not_active") {
    return {start: {shown: true, blocked: "project_not_active"}, enqueue, release: false,
      why: null};
  }
  return {start: NONE, enqueue: NONE, release: false, why: slot.reason_code};
}

//: What holds both buttons whatever the slot says, in the order it matters.
function heldBy(launch) {
  if (launch.phase !== "review") return "busy";
  if (launch.preview.budget.exhausted) return "exhausted";
  if (!launch.seen) return "card_changed";
  return isActor(launch.actor) ? null : "actor_invalid";
}

/**
 * The controls of the card: `start` and `enqueue` (each `{shown, blocked}`), whether to point at
 * «Освободить слот», the reason when nothing can be pressed, and the caption under the queue
 * button.
 */
export function controlsOf(launch) {
  const closed = {start: NONE, enqueue: NONE, release: false, caption: null};
  if (launch.preview === null) return {...closed, why: null};
  const slot = slotOf(launch);
  if (slot === null) return {...closed, why: launch.reads.queue === null ? "slot_reading"
    : "slot_unread"};
  const row = slotRow(slot), held = heldBy(launch);
  const hold = (one) => (one.shown && one.blocked === null ? {...one, blocked: held} : one);
  const view = slot.reason_code === "project_not_active";
  return {start: hold(row.start), enqueue: hold(row.enqueue), release: row.release, why: row.why,
    caption: row.enqueue.shown ? (view ? "queue_view" : "queue") : null};
}

// -- the asks ----------------------------------------------------------------------------

const authId = (launch, nonce) => `auth-${nonce}-${launch.card}`;

function grantBody(launch, nonce) {
  const grant = launch.reads.automation !== null && launch.reads.automation.status === "ok"
    ? launch.reads.automation.payload.authorization : null;
  return {authorization_id: authId(launch, nonce), preview_digest: launch.preview.preview_digest,
    authorized_by: launch.actor, terms: launch.preview.terms,
    supersedes: grant === null || grant === undefined ? null : grant.authorization_id};
}

function writeAsk(launch, ctx, kind) {
  const id = authId(launch, ctx.nonce), sent = launch.attempts[`${kind}:${id}`] ?? 0;
  const body = grantBody(launch, ctx.nonce);
  if (kind === "start") {
    return {id: `write:launch:auth:${id}:${sent}`, name: "launch_authorize", door: "write",
      target: "automationAuthorize", subject: ctx.runId, body};
  }
  return {id: `write:launch:queue:${id}:${sent}`, name: "launch_enqueue", door: "write",
    target: "queue", subject: null, body: {run_id: ctx.runId, start: {
      authorization_id: body.authorization_id, preview_digest: body.preview_digest,
      terms: body.terms, authorized_by: body.authorized_by, supersedes: body.supersedes}}};
}

function readAsks(launch, ctx) {
  const read = (name, target, subject) => ({id: `read:launch:${name}:${launch.seq}`,
    name: `launch_${name}`, door: "read", target, subject, body: null});
  const asks = [];
  if (launch.reads.queue === null) asks.push(read("queue", "queue", null));
  if (launch.reads.automation === null) asks.push(read("automation", "automation", ctx.runId));
  if (launch.reads.run === null) asks.push(read("run", "run", ctx.runId));
  return asks;
}

/**
 * The asks the card calls for: the reads it is drawn from, the write the owner pressed, and the
 * preview again when its countdown ran out (or the owner asked). None until the chain's preview
 * has landed.
 */
export function launchAsks(launch, ctx) {
  if (ctx.phase !== "review" || launch.phase === "idle") return [];
  const asks = readAsks(launch, ctx);
  if (launch.phase === "starting") asks.push(writeAsk(launch, ctx, "start"));
  if (launch.phase === "enqueuing") asks.push(writeAsk(launch, ctx, "enqueue"));
  if (previewDue(launch)) {
    asks.push({id: `write:launch:preview:${launch.previews}`, name: "launch_preview",
      door: "write", target: "automationPreview", subject: ctx.runId, body: {}});
  }
  return asks;
}

// -- the owner's moves -------------------------------------------------------------------

export function tickLaunch(launch, now) {
  return epochSeconds(now) === null || launch.now === now ? launch : {...launch, now};
}

export function editActor(launch, value) {
  return typeof value !== "string" || value === launch.actor ? launch : {...launch, actor: value};
}

export function seenLaunch(launch) {
  return launch.seen ? launch : {...launch, seen: true};
}

/** «Обновить условия»: ask the preview again, and the six repeats begin anew. */
export function refreshLaunch(launch) {
  if (launch.phase !== "review" || (launch.preview === null && launch.error === null)) {
    return launch;
  }
  return {...launch, refreshWanted: true, repeatFailed: false, repeats: 0, error: null};
}

/** Read the queue and the automation again. */
export function rereadLaunch(launch) {
  if (launch.phase !== "review") return launch;
  return {...launch, reads: {...launch.reads, queue: null, automation: null}, seq: launch.seq + 1};
}

/** The owner pressed a button of the card: the write begins, if that button may be pressed. */
export function beginLaunch(launch, kind) {
  const one = controlsOf(launch)[kind === "start" ? "start" : "enqueue"];
  if (!one.shown || one.blocked !== null) return launch;
  return {...launch, phase: kind === "start" ? "starting" : "enqueuing", sending: kind,
    note: null, refusal: null, repeats: 0};
}

// -- the answers -------------------------------------------------------------------------

function readOf(result, valid) {
  const good = result.status === "accepted" && valid(result.payload);
  return good ? {status: "ok", code: null, payload: structuredClone(result.payload)}
    : {status: "failed", code: result.code ?? (result.status === "accepted" ? "answer_unreadable"
      : result.status), payload: null};
}

const READ_VALID = Object.freeze({
  launch_queue: (payload) => record(payload) && record(payload.slot)
    && SLOT_STATES.includes(payload.slot.state) && Array.isArray(payload.entries),
  launch_automation: (payload) => record(payload) && Object.hasOwn(payload, "authorization"),
  launch_run: record});

function grantStands(launch, ctx) {
  const read = launch.reads.automation;
  const grant = read.status === "ok" ? read.payload.authorization : null;
  if (!record(grant) || grant.authorization_id !== authId(launch, ctx.nonce)
      || grant.authorized_by !== launch.actor) return false;
  return Object.keys(launch.preview.terms).filter((name) => name !== "duration_seconds")
    .every((name) => stable(grant[name]) === stable(launch.preview.terms[name]));
}

function entryOf(launch, ctx) {
  const read = launch.reads.queue;
  const entry = read.status === "ok" ? read.payload.entries.find((row) => record(row)
    && row.run_id === ctx.runId) : undefined;
  const held = entry?.preauthorization;
  return record(held) && held.digest === launch.preview.preview_digest
    && held.authorized_by === launch.actor ? entry : null;
}

//: A lost answer is settled by the two reads alone, comparing the ids and the terms: the grant or
//: the queue entry is there and is this card's, or it is not written and the owner may press again.
function settleUnknown(launch, ctx) {
  const done = {...launch, sending: null};
  if (launch.sending === "start" && grantStands(launch, ctx)) {
    return {...done, phase: "started", result: {kind: "started"}};
  }
  const entry = launch.sending === "enqueue" ? entryOf(launch, ctx) : null;
  if (entry !== null) {
    return {...done, phase: "queued", result: {kind: "queued", position: entry.position}};
  }
  return {...done, phase: "review", note: {kind: "not_written"}};
}

function landRead(launch, ctx, ask, result) {
  const name = ask.name.replace("launch_", "");
  const reads = {...launch.reads, [name]: readOf(result, READ_VALID[ask.name])};
  const next = {...launch, reads};
  const both = reads.queue !== null && reads.automation !== null;
  return launch.phase === "unknown" && both ? settleUnknown(next, ctx) : next;
}

function landPreview(launch, ctx, result) {
  const base = {...launch, previews: launch.previews + 1, refreshWanted: false};
  if (result.status === "accepted") {
    const owned = launch.refreshWanted;
    return takePreview({...base, repeatFailed: false}, result.payload, ctx.runId, !owned);
  }
  return {...base, repeatFailed: true, error: result.code ?? result.status};
}

//: What each refusal of starting or of queueing means. None of them starts anything by itself: a
//: taken slot or a stale preview changes what the card says, and the owner presses again.
function refusalAnswer(launch, ctx, code, detail) {
  const reset = {...launch.reads, queue: null, automation: null};
  const reread = {reads: reset, seq: launch.seq + 1};
  if (code === "slot_busy") {
    return {...launch, ...reread, note: {kind: "slot_busy", holder: detail?.run_id ?? null}};
  }
  if (code === "project_not_active") return {...launch, ...reread, note: {kind: code}};
  if (code === "preview_stale") return {...launch, note: {kind: "stale"}, refreshWanted: true};
  const replacing = grantBody(launch, ctx.nonce).supersedes !== null;
  const again = code === "contract_invalid" && replacing ? {refreshWanted: true} : {};
  return {...launch, ...again, refusal: {code}};
}

function landWrite(launch, ctx, ask, result) {
  const kind = ask.name === "launch_authorize" ? "start" : "enqueue";
  const key = `${kind}:${authId(launch, ctx.nonce)}`;
  const attempts = {...launch.attempts, [key]: (launch.attempts[key] ?? 0) + 1};
  const base = {...launch, attempts, phase: "review", sending: null};
  if (result.status === "accepted") {
    if (kind === "start") return {...base, phase: "started", result: {kind: "started"}};
    const entries = record(result.payload) && Array.isArray(result.payload.entries)
      ? result.payload.entries : [];
    const mine = entries.find((row) => record(row) && row.run_id === ctx.runId);
    return {...base, phase: "queued", result: {kind: "queued", position: mine?.position ?? null}};
  }
  if (result.status === "unknown") {
    return {...launch, attempts, phase: "unknown", reads: {...launch.reads, queue: null,
      automation: null}, seq: launch.seq + 1};
  }
  const detail = result.payload?.error?.detail ?? result.payload?.detail;
  return refusalAnswer(base, ctx, result.code ?? "refused", detail);
}

/**
 * Fold one answer of the card in. An answer already settled changes nothing.
 *
 * @param {object} launch The `launch` slice.
 * @param {object} ctx `{runId, nonce, phase}`: the run, the page's nonce, the chain's phase.
 * @param {object} ask The ask that was performed.
 * @param {object} result `{status, code, payload}`.
 */
export function landLaunch(launch, ctx, ask, result) {
  if (launch.settled.includes(ask.id)) return launch;
  const marked = {...launch, settled: [...launch.settled, ask.id]};
  if (ask.name === "launch_preview") return landPreview(marked, ctx, result);
  if (ask.name === "launch_authorize" || ask.name === "launch_enqueue") {
    return landWrite(marked, ctx, ask, result);
  }
  return landRead(marked, ctx, ask, result);
}

// -- the card ----------------------------------------------------------------------------

function warningsOf(budget) {
  const limit = budget.limits.max_actions, found = [];
  if (budget.clean.actions > limit) {
    found.push({code: "clean_over_actions", actions: budget.clean.actions, limit});
  }
  if (budget.worst.actions > limit) {
    found.push({code: "worst_over_actions", actions: budget.worst.actions, limit});
  }
  return found;
}

//: The harness each step of the plan runs on: the plan's node, its instance, that instance's
//: provider, and the provider's name from the facts the preview carries.
function harnessByStep(launch) {
  const plan = launch.reads.run !== null && launch.reads.run.status === "ok"
    ? launch.reads.run.payload : null;
  const instances = new Map((plan?.config?.instances ?? []).map((row) => [row.id, row.adapter]));
  const names = new Map((launch.preview.provider_facts?.providers ?? []).map((row) => [
    row.config.provider_id, row.contract.display_name]));
  return new Map((plan?.graph?.definition?.nodes ?? []).map((node) => [node.node_id,
    names.get(instances.get(node.instance_id)) ?? null]));
}

/**
 * What the card says, from the preview and what the caller knows around it: `roles` (step to
 * role id) and `seed` (the line about the code). Every number is the server's.
 */
export function cardFacts(launch, around) {
  if (launch.preview === null) return null;
  const {terms, budget, provider_facts: facts} = launch.preview;
  const clamped = new Map(budget.steps.map((row) => [row.step_id, row.clamped === true]));
  const harness = harnessByStep(launch);
  return {actions: {max: terms.max_actions, of: budget.limits.max_actions},
    spent: budget.spent === null ? null : {actions: budget.spent.actions,
      seconds: budget.spent.seconds},
    clean: {...budget.clean}, worst: {...budget.worst}, warnings: warningsOf(budget),
    time: terms.max_total_task_seconds, window: terms.duration_seconds,
    exhausted: budget.exhausted,
    steps: terms.node_limits.map((row) => ({step: row.node_id,
      role: around.roles[row.node_id] ?? null, harness: harness.get(row.node_id) ?? null,
      timeout: row.timeout_seconds, attempts: row.max_attempts,
      clamped: clamped.get(row.node_id) === true})),
    harnesses: (facts?.providers ?? []).map((row) => ({id: row.config.provider_id,
      name: row.contract.display_name, version: row.contract.version ?? null})),
    receives: {instructions: terms.instruction_bindings.map((row) => ({step: row.node_id,
      digest: row.content_digest})),
    inputs: terms.initial_input_bindings.map((row) => ({ref: row.artifact_ref,
      digest: row.content_digest})), seed: around.seed}};
}
