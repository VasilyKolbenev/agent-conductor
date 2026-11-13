"use strict";
import {isDigest, isId} from "./studio-model.js";
import {sha256Hex} from "./desk-wizard-digest.js";

const rows = value => Array.isArray(value) ? value : [];
const contains = (ids, id) => Array.isArray(ids) && ids.includes(id);
const uniqueIds = ids => Array.isArray(ids) && ids.every(isId) && new Set(ids).size === ids.length;
const readable = doc => ["text/plain", "text/markdown"].includes(doc?.media_type)
  && typeof doc.content === "string" && !!doc.content.trim();

// A repeated key is ambiguous even when both rows carry the same display label.
function byId(items, field) {
  const found = new Map();
  for (const row of items) {
    const id = row?.[field];
    if (isId(id)) found.set(id, found.has(id) ? null : row);
  }
  return found;
}

export function handoffData(detail, from = "grok-build", to = "codex") {
  const runId = isId(detail?.run?.run_id) ? detail.run.run_id : null;
  const links = [], continuations = [], model = {runId, links, continuations};
  if (!runId || !Array.isArray(detail.warnings) || detail.warnings.length) return model;

  const types = new Map(), positions = new Map();
  for (const [index, row] of rows(detail.records).entries()) {
    const value = row?.record;
    if (value?.run_id !== runId) continue;
    if (!types.has(row.record_type)) types.set(row.record_type, []);
    types.get(row.record_type).push(value);
    positions.set(value, index);
  }
  const records = type => types.get(type) || [];
  const requests = byId(records("action_request"), "action_id");
  const attempts = byId(records("action_request"), "attempt_id");
  const results = byId(records("action_result"), "action_id");
  const grants = byId(records("run_authorization"), "authorization_id");
  const instances = byId(rows(detail.config?.instances), "id");
  const documents = byId(records("artifact"), "artifact_id");
  const produced = byId(records("artifact"), "source_action_id");
  const earlier = (a, b) => positions.get(a) < positions.get(b);

  function settled(request) {
    const result = results.get(request?.action_id);
    if (!request || !result || attempts.get(request.attempt_id) !== request
        || !isId(request.node_id) || !isId(instances.get(request.instance_id)?.adapter)
        || result.attempt_id !== request.attempt_id || result.instance_id !== request.instance_id
        || result.outcome !== "succeeded" || !earlier(request, result)) return null;
    return result;
  }
  function identity(request) {
    return {adapter: instances.get(request.instance_id).adapter, instanceId: request.instance_id,
      nodeId: request.node_id, actionId: request.action_id, attemptId: request.attempt_id};
  }
  const reviews = new Map();
  for (const doc of documents.values()) {
    if (!doc || !readable(doc) || !isId(doc.artifact_ref)) continue;
    const request = requests.get(doc.source_action_id);
    const result = settled(request);
    if (!result || request.capability !== "review" || produced.get(request.action_id) !== doc
        || request.arguments?.result_artifact_ref !== doc.artifact_ref
        || !earlier(request, doc) || !earlier(doc, result)) continue;
    const endpoint = {...identity(request), artifactId: doc.artifact_id,
      artifactRef: doc.artifact_ref, excerpt: doc.content.slice(0, 1200)};
    reviews.set(doc.artifact_id, {doc, request, result, endpoint});
  }
  const targets = new Map();
  for (const target of reviews.values()) {
    if (target.endpoint.adapter !== to || !uniqueIds(target.doc.input_artifact_ids)) continue;
    for (const id of target.doc.input_artifact_ids) {
      const source = reviews.get(id);
      if (!source || source.endpoint.adapter !== from || !earlier(source.result, target.request)
          || !contains(target.request.arguments.target_artifact_refs, source.doc.artifact_ref)) {
        continue;
      }
      links.push({source: source.endpoint, target: target.endpoint});
      targets.set(target.doc.artifact_id, target);
    }
  }
  for (const request of requests.values()) {
    if (!settled(request) || request.capability !== "dispatch"
        || request.arguments?.profile !== "implement-patch-v1"
        || instances.get(request.instance_id).adapter !== to) continue;
    const grant = grants.get(request.run_authorization_id);
    if (!grant || !earlier(grant, request) || !isDigest(request.run_authorization_digest)
        || grant.authorization_digest !== request.run_authorization_digest) continue;
    const bindings = byId(rows(grant.initial_input_bindings), "artifact_ref");
    for (const target of targets.values()) {
      const ref = target.doc.artifact_ref;
      if (!earlier(target.result, request) || !contains(request.arguments.artifact_refs, ref)) {
        continue;
      }
      const binding = bindings.get(ref), pinned = documents.get(binding?.artifact_id);
      if (!readable(pinned) || pinned.artifact_ref !== ref || !earlier(pinned, grant)
          || binding.content_digest !== "sha256:" + sha256Hex(pinned.content)) continue;
      continuations.push({fromArtifactId: target.doc.artifact_id, inputRef: ref,
        inputArtifactId: pinned.artifact_id, target: identity(request),
        kind: pinned === target.doc ? "same_revision" : "different_revision"});
    }
  }
  return model;
}
