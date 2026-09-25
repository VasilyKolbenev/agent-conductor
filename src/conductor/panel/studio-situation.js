"use strict";
import {feedbackReadValid} from "./studio-feedback-model.js";
// This boundary judges one server reading. It has no transport, local clock,
// permission, scheduler or state. A rejected reading never becomes "no need".
import {exactKeys, frozenJson, isId, isInstant, isPlainObject,
  projectRunRead as projectBaseRunRead} from "./studio-model.js";
import {ARTIFACT_CONTENT_LIMIT} from "./studio-runwords.js";

//: Two records carry text past the 4,096 characters the base model allows every other carried
//: string, and each is held to ITS OWN judge instead: an artifact's `content` to the server's 49,152
//: UTF-8 bytes, and a correction's `payload` to `feedbackReadValid` below, which judges the original
//: whole (8,192 canonical bytes; one checker finding may run past 4,096 characters). MEASURED on the
//: first live runs (23.09.2026): a real review wrote 10-30 KiB, and one such document made the whole
//: run, and the Runs screen with it, unreadable here. The long value is set aside while the base
//: model judges the rest of the record, then carried back; everything else is judged as before.
const ENCODER = new TextEncoder();
const OWN_BOUND = new Map([
  ["artifact", {field: "content", fits: (text) => typeof text === "string"
    && text.length <= ARTIFACT_CONTENT_LIMIT && ENCODER.encode(text).length <= ARTIFACT_CONTENT_LIMIT}],
  ["correction_feedback", {field: "payload", fits: isPlainObject}],
]);
function setAside(payload) {
  if (!isPlainObject(payload) || !Array.isArray(payload.records)) return {shell: payload, held: []};
  const held = [];
  const records = payload.records.map((row) => {
    const bound = isPlainObject(row) && isPlainObject(row.record)
      ? OWN_BOUND.get(row.record_type) : undefined;
    const kept = bound !== undefined && bound.fits(row.record[bound.field]);
    held.push(kept ? [bound.field, row.record[bound.field]] : undefined);
    return kept ? {...row, record: {...row.record, [bound.field]: ""}} : row;
  });
  return {shell: {...payload, records}, held};
}
function carryBack(records, held) {
  return Object.freeze(records.map((row, at) => held[at] === undefined ? row
    : Object.freeze({...row, record: Object.freeze({...row.record, [held[at][0]]: frozenJson(held[at][1])})})));
}

const SITUATION_KEYS = ["state", "computed_at", "gates", "checked",
  "unknown_because", "unknown_sources"];
const GATE_KEYS = ["node_id", "gate_id", "arrived", "decision", "answerable",
  "lap", "standing_receipt", "standing_belongs_to_current_lap",
  "needs_decision", "why_not"];
const LAP_KEYS = ["required_pass", "settled_laps"];
const REASON_KEYS = ["reason", "count", "sources"];
export const HUMAN_STATES = Object.freeze(["required", "not_required", "unknown"]);
export const CHECKED_REASONS = Object.freeze(["gate_decision", "confirmation",
  "input_document", "reconcile", "attempt_bound", "run_ended"]);
export const UNKNOWN_REASONS = Object.freeze(["contradictory_gate_receipts",
  "replay_warnings", "unobserved_request"]);
export const GATE_WHY_NOT = Object.freeze(["run_ended", "decision_unknown",
  "answered_current_lap", "branch_closed", "road_not_open"]);
const DECISIONS = ["idle", "satisfied", "failed", "changes_requested", "waived", "unknown"];
const ANSWERABLE = ["first", "supersede", "none"];

function keys(value, names) { return isPlainObject(value) && exactKeys(value, names); }
function count(value) { return Number.isSafeInteger(value) && value >= 0; }
function same(left, right) {
  return left.length === right.length && left.every((value, at) => value === right[at]);
}
function ids(value) {
  return Array.isArray(value) && value.every(isId) && new Set(value).size === value.length;
}

function validGate(row) {
  if (!keys(row, GATE_KEYS) || !isId(row.node_id) || !isId(row.gate_id)
      || typeof row.arrived !== "boolean" || typeof row.needs_decision !== "boolean"
      || !DECISIONS.includes(row.decision) || !ANSWERABLE.includes(row.answerable)
      || !keys(row.lap, LAP_KEYS) || !count(row.lap.required_pass)
      || row.lap.required_pass < 1 || !count(row.lap.settled_laps)) return false;
  if (row.standing_receipt === null) {
    if (row.standing_belongs_to_current_lap !== null) return false;
  } else if (!isId(row.standing_receipt)
      || typeof row.standing_belongs_to_current_lap !== "boolean") return false;
  if (row.needs_decision) {
    return row.arrived && row.decision !== "unknown" && row.why_not === null;
  }
  return GATE_WHY_NOT.includes(row.why_not);
}

function validReasons(rows, reasons, unknown) {
  if (!Array.isArray(rows) || rows.length !== reasons.length) return false;
  return rows.every((row, at) => keys(row, REASON_KEYS) && row.reason === reasons[at]
    && count(row.count) && ids(row.sources)
    && (unknown && row.reason === "replay_warnings"
      ? row.sources.length === 0 : row.count === row.sources.length));
}

function gateReasonAgrees(row, ended) {
  if (ended) return row.why_not === "run_ended";
  if (row.decision === "unknown") return row.why_not === "decision_unknown";
  if (row.needs_decision) return row.why_not === null;
  return ["answered_current_lap", "branch_closed", "road_not_open"].includes(row.why_not);
}

function validRelations(value) {
  const checked = new Map(value.checked.map((row) => [row.reason, row]));
  const unknown = new Map(value.unknown_sources.map((row) => [row.reason, row]));
  const ended = checked.get("run_ended").count > 0;
  if (value.gates.some((row) => row.needs_decision
      !== (row.arrived && row.decision !== "unknown" && !ended)
      || !gateReasonAgrees(row, ended))) return false;
  const neededGates = value.gates.filter((row) => row.needs_decision).map((row) => row.node_id);
  const unclearGates = value.gates.filter((row) => row.decision === "unknown").map((row) => row.gate_id);
  if (!same(neededGates, checked.get("gate_decision").sources)
      || !same(unclearGates, unknown.get("contradictory_gate_receipts").sources)
      || checked.get("reconcile").count !== 0) return false;
  if (ended && (value.checked.some((row) => row.reason !== "run_ended" && row.count > 0)
      || unknown.get("unobserved_request").count > 0
      || value.gates.some((row) => row.answerable !== "none" || row.why_not !== "run_ended"))) return false;
  const because = value.unknown_sources.filter((row) => row.count > 0).map((row) => row.reason);
  if (!Array.isArray(value.unknown_because) || !same(value.unknown_because, because)) return false;
  const needed = value.checked.some((row) => row.reason !== "run_ended" && row.count > 0);
  const expected = because.length > 0 ? "unknown" : needed ? "required" : "not_required";
  return value.state === expected;
}

export function projectSituation(value) {
  if (!keys(value, SITUATION_KEYS) || !HUMAN_STATES.includes(value.state)
      || !isInstant(value.computed_at) || !Array.isArray(value.gates)
      || !value.gates.every(validGate)
      || !ids(value.gates.map((row) => row.node_id))
      || !ids(value.gates.map((row) => row.gate_id))
      || !validReasons(value.checked, CHECKED_REASONS, false)
      || !validReasons(value.unknown_sources, UNKNOWN_REASONS, true)
      || !validRelations(value)) return null;
  return frozenJson(value);
}

function recordsOf(read, kind) {
  return read.records.filter((row) => row.recordType === kind
    && row.record.run_id === read.run.runId).map((row) => row.record);
}

function nodeIdentities(nodes) {
  if (!Array.isArray(nodes) || !nodes.every(isPlainObject)
      || !ids(nodes.map((row) => row.node_id))) return null;
  if (nodes.some((row) => !["task", "gate", "loop"].includes(row.kind)
      || row.kind === "gate" && !isId(row.gate_id))) return null;
  return nodes.map((row) => JSON.stringify([row.node_id, row.kind,
    row.kind === "gate" ? row.gate_id : null]));
}

function frozenNodes(read) {
  const definitions = recordsOf(read, "graph_definition"), drawn = read.graph.definition;
  if (drawn === null) return definitions.length === 0 ? [] : null;
  if (!isPlainObject(drawn) || definitions.length !== 1) return null;
  const definition = definitions[0], expected = nodeIdentities(definition.nodes);
  const actual = nodeIdentities(drawn.nodes);
  if (Object.hasOwn(drawn, "execution_contract") !== Object.hasOwn(definition, "execution_contract")
      || drawn.execution_contract !== definition.execution_contract
      || Object.hasOwn(definition, "execution_contract") && definition.execution_contract !== "bounded-run-v1") return null;
  if (expected === null || actual === null || !same(expected, actual)
      || drawn.graph_id !== definition.graph_id || drawn.run_id !== read.run.runId) return null;
  return definition.nodes;
}

function gatesBelong(read, value, nodes) {
  const expected = nodes.filter((row) => row.kind === "gate");
  if (expected.length !== value.gates.length) return false;
  const receipts = recordsOf(read, "decision");
  return value.gates.every((row, at) => row.node_id === expected[at].node_id
    && row.gate_id === expected[at].gate_id
    && (row.standing_receipt === null || receipts.some((receipt) =>
      receipt.receipt_id === row.standing_receipt && receipt.gate_id === row.gate_id)));
}

function contained(sources, rows, key) {
  const available = new Set(rows.map((row) => row[key]));
  return sources.every((source) => available.has(source));
}

function sourcesBelong(read, value, nodes) {
  const checked = new Map(value.checked.map((row) => [row.reason, row]));
  const unknown = new Map(value.unknown_sources.map((row) => [row.reason, row]));
  const work = nodes.filter((row) => row.capability !== null && row.capability !== undefined);
  const terminals = recordsOf(read, "run_terminal").map((row) => row.terminal_id);
  return contained(checked.get("confirmation").sources, recordsOf(read, "action_proposal"), "proposal_id")
    && contained(checked.get("input_document").sources, work, "node_id")
    && contained(checked.get("attempt_bound").sources, work, "node_id")
    && same(checked.get("run_ended").sources, terminals)
    && unknown.get("replay_warnings").count === read.warnings.length
    && contained(unknown.get("unobserved_request").sources, recordsOf(read, "action_request"), "action_id");
}

// The store's actual read door is the conjunction of its old structural read
// and this new closed reading. The base model keeps its no-import contract.
export function projectRunRead(payload) {
  const marker = isPlainObject(payload?.config) && Object.hasOwn(payload.config, "automation_contract");
  if (marker && (payload.config.automation_contract !== "bounded-run-v1" || payload.run?.mode !== "policy"
      || !isPlainObject(payload.config.workflow))) return null;
  const legacy = marker ? {...payload, config: {...payload.config}} : payload;
  if (marker) delete legacy.config.automation_contract;
  const definition = payload?.graph?.definition;
  if (isPlainObject(definition) && Object.hasOwn(definition, "execution_contract")
      && (definition.execution_contract !== "bounded-run-v1" || !marker)) return null;
  const {shell, held} = setAside(legacy);
  const judged = projectBaseRunRead(shell);
  const base = judged === null ? null : Object.freeze({...judged, records: carryBack(judged.records, held)});
  if (base === null || !isPlainObject(base.graph)
      || projectSituation(base.graph.situation) === null || !feedbackReadValid(payload)) return null;
  const nodes = frozenNodes(base), value = base.graph.situation;
  if (nodes === null || !gatesBelong(base, value, nodes)
      || !sourcesBelong(base, value, nodes)) return null;
  return marker ? Object.freeze({...base, config: Object.freeze({...base.config,
    automationContract: "bounded-run-v1"})}) : base;
}
