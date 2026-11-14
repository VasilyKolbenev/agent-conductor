"use strict";
import {element} from "./command-view.js";
import {isDigest, isId} from "./studio-model.js";

const text = (s, limit) => typeof s === "string" && s.trim().length > 0 && s.length <= limit;
const one = rows => rows.length === 1 ? rows[0] : null;
const singleton = (arr, value) => Array.isArray(arr) && arr.length === 1 && arr[0] === value;

async function approvedBytes(doc, receipt) {
  if (!globalThis.crypto?.subtle) return false;
  // This protocol's document is flat. Its content is itself a UTF-8 JSON string.
  const bytes = new TextEncoder().encode(JSON.stringify(doc, Object.keys(doc).sort()));
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const hex = Array.from(hash, value => value.toString(16).padStart(2, "0")).join("");
  return receipt.reason === "Принята запись выполненных проверок. sha256:" + hex;
}

export async function manualReviewSource(detail, runId, taskId, projectId) {
  const rows = detail?.records, graph = detail?.graph?.definition;
  if (!isId(runId) || !isId(taskId) || detail?.task?.id !== taskId
      || detail.task.unreadable !== false || detail.config?.task?.id !== taskId
      || detail.run?.run_id !== runId || !isDigest(detail.run.config_digest)
      || !Array.isArray(detail.warnings) || detail.warnings.length
      || !Array.isArray(rows) || rows.some(r => r?.record?.run_id !== runId)
      || !Array.isArray(graph?.nodes) || !Array.isArray(graph.edges) || graph.edges.length)
    return null;
  const node = one(graph.nodes);
  if (node?.kind !== "gate" || node.node_id !== "operator-review"
      || node.gate_id !== "gate-operator-review") return null;
  const record = type => one(rows.filter(row => row.record_type === type));
  const artifact = record("artifact"), decision = record("decision"), end = record("run_terminal");
  const doc = artifact?.record, receipt = decision?.record, terminal = end?.record;
  if (!isId(doc?.artifact_id) || doc.artifact_ref !== "operator-review-procedure-v1"
      || doc.media_type !== "text/plain" || doc.source_action_id != null
      || !text(doc.content, 49152) || receipt?.action !== "approve"
      || receipt.gate_id !== node.gate_id || !isId(receipt.receipt_id) || !isId(receipt.actor)
      || receipt.config_digest !== detail.run.config_digest
      || !singleton(receipt.scope_refs, doc.artifact_id)
      || rows.indexOf(artifact) >= rows.indexOf(decision) || end !== rows.at(-1)
      || terminal?.state !== "complete" || !isId(terminal.terminal_id)
      || !singleton(terminal.settled_nodes, node.node_id) || !await approvedBytes(doc, receipt))
    return null;
  let value;
  try { value = JSON.parse(doc.content); } catch { return null; }
  if (value?.schema_version !== 1 || value.run_id !== runId || value.task_id !== taskId
      || value.actor_id !== receipt.actor || !text(value.reviewer, 160)
      || !Array.isArray(value.checks) || !value.checks.length || value.checks.length > 20
      || value.checks.some(v => !text(v?.step, 320) || !text(v.result, 2048))) return null;
  return {kind: "operator", taskTitle: detail.task.title || taskId, taskId, projectId, runId,
    documentId: doc.artifact_id, receiptId: receipt.receipt_id, author: value.reviewer,
    outcome: typeof value.outcome === "string" ? value.outcome : "",
    steps: value.checks.map(({step, result}) => ({label: step, result}))};
}

export async function manualReviewEvidence(detail, runId, taskId, projectId, docId, locale) {
  const source = await manualReviewSource(detail, runId, taskId, projectId);
  if (!source || source.documentId !== docId) return null;
  const ru = locale === "ru";
  return element("section", {className: "review-proposal"}, [
    element("h3", {text: source.taskTitle}),
    element("p", {text: (ru ? "Проверку подтвердил(а) " : "Checks confirmed by ") + source.author}),
    element("ol", {}, source.steps.map(step => element("li", {}, [
      element("strong", {text: step.label}), element("p", {text: step.result})]))),
    ...(source.outcome ? [element("p", {text: source.outcome})] : []),
    element("small", {text: [source.runId, source.documentId, source.receiptId].join(" · ")}),
  ]);
}
