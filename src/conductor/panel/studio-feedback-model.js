"use strict";
// Closed historical findings. No accepted row grants execution or proves success.
import {exactKeys, isDigest, isId, isInstant, isPlainObject} from "./studio-model.js";
import {canonicalJson} from "./command-projection.js";
const KEYS = ["schema_version", "feedback_id", "run_id", "authorization_id", "authorization_digest",
  "source_action_id", "source_attempt_id", "source_node_id", "source_lap", "checker_instance_id",
  "checker_adapter_id", "result_manifest", "result_manifest_digest", "payload", "recorded_at"];
const object = (value, keys) => isPlainObject(value) && exactKeys(value, keys);
const positive = (value) => Number.isSafeInteger(value) && value > 0;
const MAX_LINE = 9999999; // the parser's ceiling (command/adapters/feedback_protocol.py MAX_LINE)
const characters = (value) => typeof value === "string" && value.length > 0
  && !/[\u0000-\u001f\u007f-\u009f\ud800-\udfff]/u.test(value);
const text = (value) => characters(value)
  && value.replace(/[\u0020\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/gu, "").length > 0;
const ids = (value) => Array.isArray(value) && value.every(isId);
function path(value, named = true) {
  return (named ? text(value) : characters(value)) && !value.includes("\\") && !value.includes(":")
    && value.split("/").every((part) => part !== "" && part !== "." && part !== "..");
}
function finding(value) {
  return object(value, ["kind", "summary", "path", "line"])
    && ["defect", "missing_requirement", "verification_gap"].includes(value.kind) && text(value.summary)
    && (value.path === null ? value.line === null : path(value.path)
      && (value.line === null || (positive(value.line) && value.line <= MAX_LINE)));
}
function payload(value) {
  return object(value, ["protocol", "findings"]) && value.protocol === "conduct.feedback.v1"
    && Array.isArray(value.findings) && value.findings.length >= 1 && value.findings.length <= 16
    && value.findings.every(finding) && new TextEncoder().encode(canonicalJson(value)).length <= 8192;
}
function file(value) {
  return object(value, ["path", "state", "length", "sha256"]) && path(value.path, false)
    && Number.isSafeInteger(value.length) && value.length >= 0
    && (value.state === "deleted" ? value.length === 0 && value.sha256 === null
      : value.state === "present" && isDigest(value.sha256));
}
function codePointOrder(a, b) {
  const left = Array.from(a, (char) => char.codePointAt(0)), right = Array.from(b, (char) => char.codePointAt(0));
  for (let i = 0; i < Math.min(left.length, right.length); i++) {
    if (left[i] !== right[i]) return left[i] - right[i];
  }
  return left.length - right.length;
}
function manifest(value, row) {
  if (!object(value, ["action_id", "attempt_id", "input_artifact_ids", "files"])
      || value.action_id !== row.source_action_id || value.attempt_id !== row.source_attempt_id
      || !ids(value.input_artifact_ids) || !Array.isArray(value.files) || !value.files.every(file)) return false;
  const paths = value.files.map((item) => item.path);
  return new Set(paths).size === paths.length
    && paths.every((name, at) => at === 0 || codePointOrder(paths[at - 1], name) < 0);
}
export function validFeedback(row) {
  return object(row, KEYS) && row.schema_version === 2
    && ["feedback_id", "run_id", "authorization_id", "source_action_id", "source_attempt_id",
      "source_node_id", "checker_instance_id", "checker_adapter_id"].every((key) => isId(row[key]))
    && isDigest(row.authorization_digest) && isDigest(row.result_manifest_digest)
    && positive(row.source_lap) && isInstant(row.recorded_at) && manifest(row.result_manifest, row) && payload(row.payload);
}
function belongs(row, read) {
  const request = read.records.find((wrapper) => wrapper.record_type === "action_request"
    && wrapper.record.action_id === row.source_action_id)?.record;
  const grant = read.records.find((wrapper) => wrapper.record_type === "run_authorization"
    && wrapper.record.authorization_id === row.authorization_id)?.record;
  const checker = read.config.instances.find((value) => value.id === row.checker_instance_id);
  const node = read.graph.definition?.nodes.find((value) => value.node_id === row.source_node_id);
  return row.run_id === read.run.run_id && request?.attempt_id === row.source_attempt_id
    && request.node_id === row.source_node_id && request.run_authorization_id === row.authorization_id
    && request.run_authorization_digest === row.authorization_digest
    && grant?.authorization_digest === row.authorization_digest && checker?.adapter === row.checker_adapter_id
    && node?.verifier_instance_id === row.checker_instance_id;
}
export function feedbackReadValid(read) {
  const feedback = read.records.filter((row) => row.record_type === "correction_feedback").map((row) => row.record);
  if (!feedback.every((row) => validFeedback(row) && belongs(row, read))) return false;
  const named = new Set(feedback.map((row) => row.feedback_id));
  if (named.size !== feedback.length) return false;
  return read.records.filter((row) => row.record_type === "action_proposal").every(({record}) => {
    if (!Object.hasOwn(record, "feedback_ids")) return true;
    const refs = record.feedback_ids;
    return ids(refs) && refs.length >= 1 && refs.length <= 16 && new Set(refs).size === refs.length
      && refs.every((id) => named.has(id));
  });
}
