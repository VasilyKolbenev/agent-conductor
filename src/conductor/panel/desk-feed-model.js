"use strict";
// The rows of the feed "Ход работы" (spec 5.3): the journal of ONE frozen run read, drawn as the
// facts its records state -- proposed, started, result, verdict of a check, a person's decision,
// a document published -- and the typed findings a checker recorded, which are a document. It is
// a pure module: a run read in, frozen rows out, no language and no DOM; the words that say a
// row are `desk-feed-copy.js` and the drawing is `desk-feed.js`.
//
// A row exists only for a record that states its fact. Nothing is counted, named or worded by
// this module beyond what a record carries: a row reads identity fields and the typed ones
// (a result's outcome, an evidence's verification, a decision's action, a document's own text, a
// checker's findings), and never the body of an action (`arguments`) or the free text a result
// may carry. Who a row belongs to is the participant the plan gives the step -- the run's frozen
// `instances` name its harness -- or the person who decided; the records carry no role name, so
// the duty (performs, verifies) is the only role said. The time is the instant the record states
// in the field `studio-runwords.js` names for its kind, and is left null when there is none.
// Rows keep the journal's order: a record dated later is not moved down the feed.
//
// Kinds the feed does not draw are the run's grant and its controls, the requests, an adapter's
// health, the plan, the second boundary of an attempt and the ending: they are the journal of
// "Запуск подробно", not the course of the work.
import {ARTIFACT_CONTENT_LIMIT, INSTANT_FIELDS, RESULT_OUTCOMES,
  VERIFICATION_STATES} from "./studio-runwords.js";

//: Every kind a row can have, and the only ones: the copy holds a sentence for each.
export const FEED_KINDS = Object.freeze(["proposed", "started", "result", "verdict",
  "decision", "document", "findings"]);
//: The words of a check's verdict: every verification state but the one that says nobody
//: checked, which is a claim and not a verdict.
const VERDICTS = Object.freeze(VERIFICATION_STATES.filter((word) => word !== "unverified"));
//: `contract_values._DECISION_ACTIONS`, held equal to it by a test that reads both.
export const DECISION_WORDS = Object.freeze(["approve", "reject", "request_changes", "waive"]);
//: The words that owe the sentence that a finished process is not a verified result.
const OWES_NOTE = Object.freeze(["verification_failed", "mismatch"]);
const UNKNOWN = Object.freeze({kind: "unknown"});

const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const list = (value) => (Array.isArray(value) ? value : []);
const text = (value) => (typeof value === "string" && value !== "" ? value : null);
const freeze = (value) => Object.freeze(value);

//: What a row is told about the run it belongs to: the steps of the plan by id, the requests
//: (which say which step an action carried out), the actions that have a result, which evidence
//: a result rests on, the harness of each frozen participant, and the pass the plan's loop is on.
function context(detail, records) {
  const graph = isObject(detail) && isObject(detail.graph) ? detail.graph : {};
  const nodes = list(graph.definition?.nodes)
    .filter((node) => isObject(node) && text(node.node_id));
  const of = (type) => records.filter((row) => isObject(row) && row.record_type === type
    && isObject(row.record)).map((row) => row.record);
  const results = of("action_result");
  return {
    nodes: new Map(nodes.map((node) => [node.node_id, node])),
    gates: new Map(nodes.filter((node) => text(node.gate_id)).map((node) => [node.gate_id, node])),
    requests: new Map(of("action_request").filter((one) => text(one.action_id))
      .map((one) => [one.action_id, one])),
    answered: new Set(results.map((one) => one.action_id)),
    evidenceOf: new Map(results.flatMap((one) => list(one.evidence_refs)
      .filter((ref) => text(ref)).map((ref) => [ref, one.action_id]))),
    instances: new Map(list(detail?.config?.instances).filter((one) => isObject(one)
      && text(one.id)).map((one) => [one.id, one])),
    pass: runPass(detail),
  };
}

//: The pass the run's bounded return stands on, or null when the plan has no loop or the run
//: states no number: `{pass, bound}`. The feed and the summary both say it.
export function runPass(detail) {
  const graph = isObject(detail) && isObject(detail.graph) ? detail.graph : {};
  const runtime = list(graph.runtime?.nodes);
  for (const node of list(graph.definition?.nodes).filter(isObject)) {
    const bound = isObject(node.loop) ? node.loop.bound : null;
    const row = runtime.find((one) => isObject(one) && one.node_id === node.node_id);
    if (Number.isSafeInteger(bound) && Number.isSafeInteger(row?.pass) && row.pass >= 1) {
      return freeze({pass: row.pass, bound});
    }
  }
  return null;
}

//: The participant a record names by instance id (or, for a check, by the adapter that made it),
//: with the harness and model the run froze for that id. No id at all is `unknown`.
function participant(ctx, instance, duty, adapter = null) {
  const id = text(instance);
  if (id === null && text(adapter) === null) return UNKNOWN;
  const frozen = id === null ? undefined : ctx.instances.get(id);
  return freeze({kind: "participant", instance: id,
    harness: text(frozen?.adapter) ?? text(adapter), model: text(frozen?.model), duty});
}

//: A step of the plan by node id: the plan's own title, or the id when the plan names no such step.
function step(ctx, nodeId) {
  const id = text(nodeId);
  return id === null ? null : freeze({node_id: id, title: text(ctx.nodes.get(id)?.title) ?? id});
}

const stepOfAction = (ctx, actionId) => step(ctx, ctx.requests.get(actionId)?.node_id);
const at = (kind, record) => text(record[INSTANT_FIELDS[kind]]);

function proposed(ctx, record) {
  if (text(record.instance_id) === null) return null;
  return {kind: "proposed", at: at("action_proposal", record),
    who: participant(ctx, record.instance_id, "perform"), step: step(ctx, record.node_id)};
}

function started(ctx, record) {
  const action = text(record.action_id);
  if (record.phase !== "effect_lease" || action === null) return null;
  const live = !ctx.answered.has(action);
  return {kind: "started", at: at("attempt_event", record), live, pass: live ? ctx.pass : null,
    who: participant(ctx, record.instance_id, "perform", record.adapter_id),
    step: stepOfAction(ctx, action)};
}

function result(ctx, record) {
  if (text(record.action_id) === null || text(record.outcome) === null) return null;
  const word = RESULT_OUTCOMES.includes(record.outcome) ? record.outcome : "unknown";
  return {kind: "result", at: at("action_result", record), word,
    needsNote: OWES_NOTE.includes(word), who: participant(ctx, record.instance_id, "perform"),
    step: stepOfAction(ctx, record.action_id)};
}

//: The action a check was made of: the result that names the evidence, else the address the
//: evidence carries (`verification/<action id>`).
function checkedAction(ctx, record) {
  const named = ctx.evidenceOf.get(record.evidence_id);
  if (text(named) !== null) return named;
  const found = typeof record.uri === "string" ? /^verification\/(.+)$/.exec(record.uri) : null;
  return found === null ? null : found[1];
}

function verdict(ctx, record) {
  if (!VERDICTS.includes(record.verification)) return null;
  return {kind: "verdict", word: record.verification,
    needsNote: OWES_NOTE.includes(record.verification),
    at: text(record.verified_at) ?? at("evidence", record),
    who: participant(ctx, record.verifier_instance_id, "verify", record.verified_by),
    step: stepOfAction(ctx, checkedAction(ctx, record))};
}

function decision(ctx, record) {
  if (!DECISION_WORDS.includes(record.action) || text(record.gate_id) === null) return null;
  const gate = ctx.gates.get(record.gate_id);
  return {kind: "decision", at: at("decision", record), word: record.action,
    who: freeze({kind: "person", name: text(record.actor)}), reason: text(record.reason),
    step: gate === undefined ? null : step(ctx, gate.node_id)};
}

//: A document's text, when it is within what the feed shows (the store's own limit, in UTF-8
//: bytes): `{content, tooLarge}`.
function body(content) {
  if (typeof content !== "string") return {content: null, tooLarge: false};
  const fits = new TextEncoder().encode(content).length <= ARTIFACT_CONTENT_LIMIT;
  return fits ? {content, tooLarge: false} : {content: null, tooLarge: true};
}

function published(ctx, record) {
  const ref = text(record.artifact_ref);
  if (ref === null) return null;
  const source = text(record.source_action_id);
  const request = source === null ? null : ctx.requests.get(source);
  return {kind: "document", at: at("artifact", record),
    doc: freeze({ref, id: text(record.artifact_id), mediaType: text(record.media_type),
      ...body(record.content)}),
    who: source === null ? freeze({kind: "person", name: null})
      : participant(ctx, request?.instance_id, "perform"),
    step: source === null ? null : stepOfAction(ctx, source)};
}

//: The findings a checker recorded, each its typed kind, its summary and where it points.
function findings(ctx, record) {
  const kept = list(record.payload?.findings).filter((one) => isObject(one)
    && text(one.kind) && text(one.summary)).map((one) => freeze({kind: one.kind,
    summary: one.summary, path: text(one.path),
    line: Number.isSafeInteger(one.line) ? one.line : null}));
  if (kept.length === 0) return null;
  return {kind: "findings", at: at("correction_feedback", record), findings: freeze(kept),
    who: participant(ctx, record.checker_instance_id, "verify", record.checker_adapter_id),
    step: step(ctx, record.source_node_id)};
}

const BUILDERS = Object.freeze({action_proposal: proposed, attempt_event: started,
  action_result: result, evidence: verdict, decision, artifact: published,
  correction_feedback: findings});
//: What every row carries, whatever its kind: a fact it does not state is null or false.
const BLANK = Object.freeze({at: null, who: UNKNOWN, step: null, word: null, needsNote: false,
  live: false, pass: null, doc: null, findings: null, reason: null});

//: The rows of a run read, in the journal's order. A read that is not a run read, and a record
//: that does not state its fact, make no row and throw nothing.
export function feedRows(detail) {
  const records = isObject(detail) ? list(detail.records) : [];
  const ctx = context(detail, records);
  const made = [];
  records.forEach((wrapper, place) => {
    if (!isObject(wrapper) || !isObject(wrapper.record)) return;
    const kind = wrapper.record_type;
    const row = Object.hasOwn(BUILDERS, kind) ? BUILDERS[kind](ctx, wrapper.record) : null;
    if (row !== null) made.push(freeze({...BLANK, ...row, key: `${place}:${row.kind}`}));
  });
  return freeze(made);
}
