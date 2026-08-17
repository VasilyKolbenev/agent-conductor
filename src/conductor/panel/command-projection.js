"use strict";
// Closed projections of durable command facts: no DOM, no network, no state.

export const RUN_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const CONTROL_NAMES = new Set(
  ["dispatch", "review", "evidence", "stop", "retry", "switch"]);
export const CAPABILITY_FIELDS = Object.freeze({
  dispatch: Object.freeze([
    ["work_item_id", "id"], ["instruction_ref", "id"],
    ["profile", "enum", ["implement", "review"]],
    ["artifact_refs", "ids"],
    ["output_limit_profile", "enum", ["small", "normal"]],
  ]),
  review: Object.freeze([
    ["work_item_id", "id"], ["target_artifact_refs", "ids-required"],
    ["review_profile", "enum", ["quality", "security", "spec"]],
  ]),
  evidence: Object.freeze([["target_action_id", "id"],
    ["kinds", "enum-list", ["result", "diff", "tests", "status"]]]),
  stop: Object.freeze([["target_attempt_id", "id"],
    ["reason", "enum", ["user", "timeout", "switch"]]]),
  retry: Object.freeze([["prior_action_id", "id"],
    ["reason", "enum", ["failed", "unknown", "verification_failed", "user"]]]),
  switch: Object.freeze([
    ["prior_action_id", "id"], ["target_instance_id", "id"],
    ["handoff_ref", "id"],
  ]),
});
export const ERROR_LABELS = Object.freeze({
  authorization_refused: "Authorization refused.",
  capability_unsupported: "This capability is unavailable.",
  contract_invalid: "The request shape is invalid.",
  csrf_denied: "The local session expired. Submit again.",
  malformed_request: "The request could not be read.",
  method_not_allowed: "That operation is unavailable.",
  record_conflict: "The durable record conflicts with an existing fact.",
  route_not_found: "The run route was not found.",
  route_unsafe: "The run route is structurally unsafe.",
  run_corrupt: "The run history is corrupt.",
  same_origin_denied: "The local origin was refused.",
  service_refused: "The command service refused the request.",
  store_error: "The run store is unavailable.",
});
const RECORD_FIELDS = Object.freeze({
  action_proposal: ["proposal_id", "instance_id", "capability", "proposed_at"],
  action_request: ["action_id", "instance_id", "capability", "requested_at"],
  action_result: ["receipt_id", "outcome", "finished_at"],
  adapter_observation: ["observation_id", "instance_id", "health", "observed_at"],
  attempt_event: ["event_id", "phase", "outcome", "recorded_at"],
  decision: ["receipt_id", "gate_id", "action", "decided_at"],
  evidence: ["evidence_id", "kind", "verification", "observed_at"],
});
export const DECISION_STATES = Object.freeze({
  approve: "satisfied",
  reject: "failed",
  request_changes: "changes_requested",
  waive: "waived",
});
export function isId(value) {
  return typeof value === "string" && RUN_ID.test(value);
}
export function isIdList(value) { return Array.isArray(value) && value.every(isId); }
export function safeMode(value) {
  return ["observe", "propose", "confirm"].includes(value) ? value : "unknown";
}
export function projectRecords(wrappers) {
  if (!Array.isArray(wrappers)) return [];
  return wrappers.map((wrapper) => {
    const kind = wrapper && typeof wrapper.record_type === "string"
      ? wrapper.record_type : "";
    const source = wrapper && wrapper.record && typeof wrapper.record === "object"
      ? wrapper.record : {};
    const fields = RECORD_FIELDS[kind];
    if (!fields) return {kind: "unknown", facts: []};
    const facts = fields.flatMap((name) => {
      const value = source[name];
      if (typeof value !== "string" || !value) return [];
      return [`${name}: ${value}`];
    });
    return {kind, facts};
  });
}
export function projectControls(payload) {
  if (!payload || !Array.isArray(payload.instances)) return [];
  return payload.instances.flatMap((instance) => {
    if (!instance || !isId(instance.instance_id)
        || !Array.isArray(instance.controls)) return [];
    const names = [...new Set(instance.controls.filter((name) =>
      CONTROL_NAMES.has(name) && CAPABILITY_FIELDS[name]))].sort();
    return names.length ? [{instanceId: instance.instance_id, names}] : [];
  }).sort((left, right) => left.instanceId.localeCompare(right.instanceId));
}
function projectDecision(value) {
  if (!value || typeof value !== "object") return null;
  if (!Number.isInteger(value.schema_version) || value.schema_version < 2) return null;
  if (![value.receipt_id, value.run_id, value.gate_id, value.actor].every(isId)) {
    return null;
  }
  // decided_at is the instant a Human decided. Production refuses a receipt
  // whose instant never existed, so a shape-only check here would let the wire
  // show an approval the durable store would never hold.
  if (!DECISION_STATES[value.action] || typeof value.decided_at !== "string"
      || !instantIsValid(value.decided_at)) {
    return null;
  }
  if (typeof value.reason !== "string"
      || (["request_changes", "waive"].includes(value.action)
          && !value.reason.trim())) return null;
  if (!isIdList(value.scope_refs) || !isIdList(value.evidence_refs)) return null;
  if (typeof value.config_digest !== "string"
      || !/^sha256:[0-9a-f]{64}$/.test(value.config_digest)) return null;
  if (value.supersedes !== null && !isId(value.supersedes)) return null;
  if (value.supersedes === value.receipt_id) return null;
  return {
    action: value.action, gateId: value.gate_id, receiptId: value.receipt_id,
    runId: value.run_id, supersedes: value.supersedes,
  };
}
export function projectGates(wrappers, runId) {
  if (!Array.isArray(wrappers)) return {corrupt: true, rows: []};
  const receipts = [];
  for (const wrapper of wrappers) {
    if (!wrapper || wrapper.record_type !== "decision") continue;
    const receipt = projectDecision(wrapper.record);
    if (!receipt || receipt.runId !== runId) return {corrupt: true, rows: []};
    receipts.push(receipt);
  }
  const byId = new Map(receipts.map((receipt) => [receipt.receiptId, receipt]));
  if (byId.size !== receipts.length) return {corrupt: true, rows: []};
  const gateIds = [...new Set(receipts.map((receipt) => receipt.gateId))].sort();
  const rows = [];
  for (const gateId of gateIds) {
    const matching = receipts.filter((receipt) => receipt.gateId === gateId);
    for (const receipt of matching) {
      if (receipt.supersedes === null) continue;
      const prior = byId.get(receipt.supersedes);
      if (!prior || prior.runId !== runId || prior.gateId !== gateId) {
        return {corrupt: true, rows: []};
      }
    }
    const superseded = new Set(matching.flatMap((receipt) =>
      receipt.supersedes === null ? [] : [receipt.supersedes]));
    const current = matching.filter((receipt) => !superseded.has(receipt.receiptId));
    if (current.length !== 1) return {corrupt: true, rows: []};
    rows.push({gateId, state: DECISION_STATES[current[0].action]});
  }
  return {corrupt: false, rows};
}
export function refusalCode(payload) {
  const code = payload && payload.error && payload.error.code;
  return typeof code === "string" && ERROR_LABELS[code] ? code : "store_error";
}
export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    const facts = Object.keys(value).sort().map((name) =>
      `${JSON.stringify(name)}:${canonicalJson(value[name])}`);
    return `{${facts.join(",")}}`;
  }
  return JSON.stringify(value);
}
export function projectScope(value) {
  const rows = value.split(",").map((row) => row.trim()).filter(Boolean);
  if (!rows.length) return null;
  for (const row of rows) {
    const parts = row.split("/");
    if (row.startsWith("/") || row.includes("\\") || row.includes(":")
        || parts.some((part) => !part || part === "." || part === "..")) {
      return null;
    }
  }
  return rows;
}
export function exactArguments(capability, data) {
  const output = {};
  for (const [name, kind, choices] of CAPABILITY_FIELDS[capability] || []) {
    const raw = String(data.get(`argument:${name}`) || "").trim();
    if (kind === "id") {
      if (!isId(raw)) return null;
      output[name] = raw;
    } else if (kind === "ids" || kind === "ids-required") {
      const values = raw ? raw.split(",").map((value) => value.trim()) : [];
      if (!isIdList(values) || (kind === "ids-required" && !values.length)) {
        return null;
      }
      output[name] = values;
    } else if (kind === "enum") {
      if (!choices.includes(raw)) return null;
      output[name] = raw;
    } else {
      const values = [...data.getAll(`argument:${name}`)];
      if (!values.length || !values.every((value) => choices.includes(value))
          || new Set(values).size !== values.length) return null;
      output[name] = values;
    }
  }
  return output;
}
// The immutable facts the durable ActionRequest must echo back, frozen at the
// moment the proposal was created. `idempotency_key` is not read from any
// response: the runtime derives it as `dispatch-<proposal_id>`
// (ControlRuntime._mint_request), so the Cockpit recomputes it here.
function proposalBinding(payload) {
  return Object.freeze({
    attempt_id: payload.attempt_id,
    instance_id: payload.instance_id,
    capability: payload.capability,
    preview_digest: payload.preview_digest,
    timeout_seconds: payload.timeout_seconds,
    arguments: canonicalJson(payload.arguments),
    scope: canonicalJson(payload.scope),
    idempotency_key: `dispatch-${payload.proposal_id}`,
  });
}
export function projectProposal(payload, submitted, runId) {
  if (!payload || typeof payload !== "object" || payload.schema_version !== 2
      || payload.run_id !== runId || !isId(payload.proposal_id)
      || typeof payload.proposed_at !== "string"
      || !/^sha256:[0-9a-f]{64}$/.test(payload.preview_digest || "")
      || !/^sha256:[0-9a-f]{64}$/.test(payload.config_digest || "")) return null;
  for (const name of ["instance_id", "attempt_id", "capability", "proposed_by",
    "rationale", "timeout_seconds"]) {
    if (payload[name] !== submitted[name]) return null;
  }
  if (canonicalJson(payload.arguments) !== canonicalJson(submitted.arguments)
      || canonicalJson(payload.scope) !== canonicalJson(submitted.scope)) return null;
  const confirmation = Object.freeze({
    proposal_id: payload.proposal_id,
    preview_digest: payload.preview_digest,
    capability: payload.capability,
    scope: Object.freeze([...payload.scope]),
    config_digest: payload.config_digest,
  });
  const facts = Object.freeze({
    proposal_id: payload.proposal_id,
    preview_digest: payload.preview_digest,
    config_digest: payload.config_digest,
    instance: payload.instance_id,
    capability: payload.capability,
    arguments: canonicalJson(payload.arguments),
    scope: confirmation.scope.join(", "),
    timeout_seconds: String(payload.timeout_seconds),
    rationale: payload.rationale,
  });
  return Object.freeze({binding: proposalBinding(payload), confirmation, facts});
}
// The Human supplies one fact — who confirms. Every other field is copied from
// the frozen snapshot, so editing the composer afterwards cannot reach the wire.
export function confirmationBody(proposal, confirmedBy) {
  const actor = String(confirmedBy || "").trim();
  if (!proposal || !isId(actor)) return null;
  const snapshot = proposal.confirmation;
  return {
    proposal_id: snapshot.proposal_id,
    preview_digest: snapshot.preview_digest,
    capability: snapshot.capability,
    scope: [...snapshot.scope],
    config_digest: snapshot.config_digest,
    confirmed_by: actor,
  };
}
//: Every identifier the durable ActionRequest must carry. A missing or
//: malformed one is a fact the Cockpit does not have, never a default.
const ACTION_IDS = Object.freeze(["action_id", "run_id", "attempt_id",
  "instance_id", "capability", "requested_by", "idempotency_key"]);
const UTC_INSTANT =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(?:Z|\+00:00)$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
// A string that matched UTC_INSTANT is still only a shape. This decides whether
// it names a real UTC instant, agreeing case-for-case with the production
// contract (command/contracts.py _timestamp -> datetime.fromisoformat): an
// invalid month, day, calendar day (incl. a non-leap Feb 29), hour, minute or
// second is refused; the ISO end-of-day 24:00:00 that production accepts — only
// when minute, second and microsecond are zero — is accepted here too.
function instantIsValid(value) {
  const m = UTC_INSTANT.exec(value);
  if (!m) return false;
  const year = Number(m[1]), month = Number(m[2]), day = Number(m[3]);
  if (year < 1 || month < 1 || month > 12) return false;
  const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
  const maxDay = month === 2 && leap ? 29 : MONTH_LENGTHS[month - 1];
  if (day < 1 || day > maxDay) return false;
  const hour = Number(m[4]), minute = Number(m[5]), second = Number(m[6]);
  if (minute > 59 || second > 59) return false;
  if (hour === 24) {
    return minute === 0 && second === 0
      && Number(((m[7] || "") + "000000").slice(0, 6)) === 0;
  }
  return hour <= 23;
}
function actionFactsPresent(payload) {
  return ACTION_IDS.every((name) => isId(payload[name]))
    && typeof payload.requested_at === "string"
    && UTC_INSTANT.test(payload.requested_at)
    && instantIsValid(payload.requested_at)
    && DIGEST.test(payload.preview_digest || "")
    && Number.isInteger(payload.timeout_seconds);
}
function actionEchoesSnapshot(payload, binding) {
  if (!binding || typeof binding !== "object") return false;
  return payload.attempt_id === binding.attempt_id
    && payload.instance_id === binding.instance_id
    && payload.capability === binding.capability
    && payload.preview_digest === binding.preview_digest
    && payload.timeout_seconds === binding.timeout_seconds
    && canonicalJson(payload.arguments) === binding.arguments
    && canonicalJson(payload.scope) === binding.scope;
}
// An accepted authorization is one prepared request, never a result: only the
// request's own identity is projected, and no outcome field exists to show.
//
// The endpoint is Confirm-only. Policy is a separate authority seam that no
// Human click may stand in for, so a response claiming it — or naming an actor
// the Human did not type, or echoing facts the frozen snapshot never held — is
// an unknown, not an acceptance. Every arm below refuses; none defaults.
export function projectAction(payload, submitted, runId, binding) {
  if (!payload || typeof payload !== "object" || payload.schema_version !== 2
      || payload.run_id !== runId
      || payload.capability !== submitted.capability
      || payload.preview_digest !== submitted.preview_digest
      || canonicalJson(payload.scope) !== canonicalJson(submitted.scope)
      || !actionFactsPresent(payload)) return null;
  if (payload.mode !== "confirm") return null;
  if (payload.requested_by !== submitted.confirmed_by) return null;
  if (!actionEchoesSnapshot(payload, binding)) return null;
  if (!binding || payload.idempotency_key !== binding.idempotency_key) return null;
  return Object.freeze({
    action_id: payload.action_id,
    capability: payload.capability,
    mode: payload.mode,
  });
}
