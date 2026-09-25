"use strict";
// Closed presentation boundary. The server owns admission, time and execution.
import {exactKeys, isDigest, isId, isInstant, isPlainObject} from "./studio-model.js";
import {compareInstants} from "./studio-taskruns.js";
import {validProviderFacts} from "./studio-automation-providers.js";
import {canonicalJson} from "./command-projection.js";

export const AUTOMATION_STATES = Object.freeze(["unconfigured", "ready", "running", "waiting",
  "paused", "revoked", "expired", "complete", "stalled", "restart_required"]);
export const AUTOMATION_REASONS = Object.freeze(["authorization_required", "plan_ended", "paused", "revoked",
  "expired", "owner_required", "explicit_resume_required", "ambiguous_actions", "action_in_flight",
  "unknown_action", "feedback_required", "admission_refused", "stalled", "plan_stalled", "plan_waiting", "ready"]);
const TERMS = ["run_id", "contract", "config_digest", "graph_digest", "provider_config_digest",
  "source_prefix_digest", "node_limits", "instruction_bindings", "initial_input_bindings",
  "max_actions", "max_action_seconds", "max_total_task_seconds", "concurrency", "failure_handling"];
const GRANT = [...TERMS, "schema_version", "authorization_id", "authorized_by", "authorized_at",
  "expires_at", "supersedes", "authorization_digest"];
const CONTROL = ["schema_version", "control_id", "run_id", "authorization_id", "authorization_digest",
  "action", "actor", "recorded_at", "expected_control_id"];
const VIEW = ["run_id", "authorization", "control", "state", "reason_code", "active_action_id",
  "next_node_id", "spent_actions", "remaining_actions", "spent_task_seconds", "remaining_task_seconds",
  "expires_at", "owner_present"];
const object = (row, keys) => isPlainObject(row) && exactKeys(row, keys);
const count = (value) => Number.isSafeInteger(value) && value >= 0;
const positive = (value) => count(value) && value > 0;
const optionalId = (value) => value === null || isId(value);
const human = (value) => typeof value === "string" && value.trim().length > 0 && value.length <= 4096;
const copy = (value) => JSON.parse(JSON.stringify(value));

function validRows(rows, key, valid) {
  return Array.isArray(rows) && rows.every(valid)
    && new Set(rows.map((row) => row[key])).size === rows.length;
}
function validNode(row) {
  return object(row, ["node_id", "timeout_seconds", "max_attempts"]) && isId(row.node_id)
    && positive(row.timeout_seconds) && positive(row.max_attempts);
}
function validBinding(row, name) {
  return object(row, [name, "artifact_id", "content_digest"]) && isId(row[name])
    && isId(row.artifact_id) && isDigest(row.content_digest);
}
function validTerms(terms, detail) {
  if (!terms || terms.run_id !== detail.run.run_id || terms.contract !== "bounded-run-v1"
      || terms.config_digest !== detail.run.config_digest || terms.concurrency !== 1
      || terms.failure_handling !== "explicit-failure-route-only") return false;
  if (!["config_digest", "graph_digest", "provider_config_digest", "source_prefix_digest"]
    .every((name) => isDigest(terms[name]))) return false;
  if (![terms.max_actions, terms.max_action_seconds, terms.max_total_task_seconds].every(positive)
      || !validRows(terms.node_limits, "node_id", validNode)
      || !validRows(terms.instruction_bindings, "node_id", (row) => validBinding(row, "node_id"))
      || !validRows(terms.initial_input_bindings, "artifact_ref", (row) => validBinding(row, "artifact_ref"))) return false;
  const nodes = (detail.graph?.definition?.nodes || []).filter((node) => node.capability);
  if (nodes.length !== terms.node_limits.length || !nodes.every((node, i) => node.node_id === terms.node_limits[i].node_id)) return false;
  const instructions = terms.instruction_bindings.map((row) => row.node_id);
  if (instructions.join("\0") !== terms.node_limits.filter((row) => instructions.includes(row.node_id))
    .map((row) => row.node_id).join("\0")) return false;
  const refs = terms.initial_input_bindings.map((row) => row.artifact_ref);
  return refs.join("\0") === [...refs].sort().join("\0");
}

export function automationEligible(detail) {
  return detail?.run.mode === "policy" && detail.config?.automation_contract === "bounded-run-v1";
}
export function projectAutomationPreview(value, detail) {
  if (!automationEligible(detail) || !object(value, ["terms", "preview_digest", "previewed_at", "valid_until", "provider_facts"])
      || !validProviderFacts(value.provider_facts, detail)
      || !object(value.terms, [...TERMS, "duration_seconds"]) || !validTerms(value.terms, detail)
      || !positive(value.terms.duration_seconds) || value.terms.duration_seconds > 86400
      || !isDigest(value.preview_digest) || !isInstant(value.previewed_at) || !isInstant(value.valid_until)
      || compareInstants(value.previewed_at, value.valid_until) >= 0) return null;
  return copy(value);
}
function validGrant(grant, detail) {
  return object(grant, GRANT) && validTerms(grant, detail) && grant.schema_version === 2
    && isId(grant.authorization_id) && human(grant.authorized_by) && optionalId(grant.supersedes)
    && isDigest(grant.authorization_digest) && isInstant(grant.authorized_at)
    && isInstant(grant.expires_at) && compareInstants(grant.authorized_at, grant.expires_at) < 0;
}
function validControl(control, grant) {
  return object(control, CONTROL) && grant !== null && control.schema_version === 2
    && isId(control.control_id) && control.run_id === grant.run_id
    && control.authorization_id === grant.authorization_id && control.authorization_digest === grant.authorization_digest
    && ["pause", "resume", "revoke"].includes(control.action) && human(control.actor)
    && isInstant(control.recorded_at) && optionalId(control.expected_control_id);
}
export function projectAutomation(value, detail) {
  if (!automationEligible(detail) || !object(value, VIEW) || value.run_id !== detail.run.run_id
      || !AUTOMATION_STATES.includes(value.state) || !AUTOMATION_REASONS.includes(value.reason_code)
      || typeof value.owner_present !== "boolean" || !optionalId(value.active_action_id)
      || !optionalId(value.next_node_id)) return null;
  if (![value.spent_actions, value.remaining_actions, value.spent_task_seconds, value.remaining_task_seconds].every(count)) return null;
  if (value.authorization === null) {
    if (value.control !== null || value.expires_at !== null || value.state !== "unconfigured") return null;
  } else {
    if (!validGrant(value.authorization, detail) || value.expires_at !== value.authorization.expires_at
        || value.control !== null && !validControl(value.control, value.authorization)) return null;
    if (value.remaining_actions !== Math.max(0, value.authorization.max_actions - value.spent_actions)
        || value.remaining_task_seconds !== Math.max(0, value.authorization.max_total_task_seconds - value.spent_task_seconds)) return null;
  }
  const nodes = detail.graph?.definition?.nodes || [];
  if (value.next_node_id !== null && !nodes.some((node) => node.node_id === value.next_node_id && node.capability)) return null;
  return copy(value);
}

//: The limits a person starts from, made to fit together and to fit the frozen plan. A step an
//: independent checker judges reserves the checker's time as well (2x, as the server holds it); a
//: step whose own failure road loops back to it is budgeted for that planned correction up front,
//: so the preview shows every attempt it would authorize. A frozen timeout or attempt bound is never
//: exceeded. Only a starting draft: nothing here authorizes or runs anything, and a person's own
//: edits are kept by the flow, never recomputed over.
export function automationDraft(detail) {
  const definition = detail.graph?.definition || {};
  const loops = new Map((definition.nodes || []).filter((node) => node.loop).map((node) => [node.node_id, node.loop]));
  const rows = (definition.nodes || []).filter((node) => node.capability).map((node) => {
    const timeout = Math.min(node.timeout_seconds || 300, 300);
    const checked = Boolean(node.verifier_instance_id) && node.verifier_instance_id !== node.instance_id;
    const correction = (definition.edges || []).find((edge) => edge.from_node === node.node_id
      && edge.condition === "on_failed" && loops.get(edge.to_node)?.back_to === node.node_id);
    const planned = correction ? loops.get(correction.to_node).bound : 1;
    return {node_id: node.node_id, timeout, reserved: timeout * (checked ? 2 : 1),
      attempts: Math.max(1, Math.min(planned, node.attempt_bound || planned))};
  });
  const total = rows.reduce((sum, row) => sum + row.reserved * row.attempts, 0);
  return {actor: "", max_actions: String(Math.max(1, rows.reduce((sum, row) => sum + row.attempts, 0))),
    max_action_seconds: String(Math.max(1, ...rows.map((row) => row.reserved))),
    max_total_task_seconds: String(Math.max(1, total)),
    duration_seconds: String(Math.min(86400, Math.max(3600, total))),
    node_limits: rows.map((row) => ({node_id: row.node_id, timeout_seconds: String(row.timeout),
      max_attempts: String(row.attempts)}))};
}
export function previewRequest(draft) {
  const integer = (text) => typeof text === "string" && /^[1-9][0-9]*$/.test(text) && positive(Number(text));
  const names = ["max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds"];
  if (!names.every((key) => integer(draft[key])) || !draft.node_limits.every((row) =>
    isId(row.node_id) && integer(row.timeout_seconds) && integer(row.max_attempts))) return null;
  return {...Object.fromEntries(names.map((key) => [key, Number(draft[key])])), node_limits:
    draft.node_limits.map((row) => ({node_id: row.node_id, timeout_seconds: Number(row.timeout_seconds), max_attempts: Number(row.max_attempts)}))};
}

export function automationWriteReadBack(request, view, detail) {
  const body = request.body, authorization = request.target === "automationAuthorize";
  const kind = authorization ? "run_authorization" : "run_authorization_control";
  const rows = (detail.records || []).filter((row) => row.record_type === kind).map((row) => row.record);
  rows.push(authorization ? view.authorization : view.control);
  return rows.some((row) => {
    if (authorization) return row && validGrant(row, detail)
      && row.authorization_id === body.authorization_id && row.authorized_by === body.authorized_by
      && row.supersedes === body.supersedes
      && TERMS.every((key) => canonicalJson(row[key]) === canonicalJson(body.terms[key]));
    return row && validControl(row, view.authorization)
      && Object.keys(body).every((key) => canonicalJson(row[key]) === canonicalJson(body[key]));
  });
}
