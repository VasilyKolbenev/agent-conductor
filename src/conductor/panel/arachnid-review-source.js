"use strict";
import {path} from "./desk-transport.js";
import {isDigest, isId} from "./studio-model.js";
import {matchesAtlasAttempt} from "./studio-atlas-inspector.js";
import {manualReviewSource} from "./arachnid-manual-review.js";

const rows = items => Array.isArray(items) ? items : [];
const only = items => items.length === 1 ? items[0] : null;
const patch = item => item?.capability === "dispatch"
  && item.arguments?.profile === "implement-patch-v1";

function checkedSnapshot(journal, request, result, node) {
  const q = request.record, evidence = journal.filter(r => r.record_type === "evidence");
  const seal = only(evidence.filter(r => r.record.kind === "attempt_seal"
    && (r.record.action_id === q.action_id || r.record.attempt_id === q.attempt_id)));
  const s = seal?.record;
  if (!s || s.action_id !== q.action_id || s.attempt_id !== q.attempt_id || s.node_id !== q.node_id
      || s.instance_id !== q.instance_id || s.checker_instance_id !== node.verifier_instance_id
      || !isId(s.checker_adapter_id) || s.authorization_id !== q.run_authorization_id
      || s.authorization_digest !== q.run_authorization_digest
      || ![s.digest, s.test_report_digest, s.snapshot_digest].every(isDigest)) return null;
  const proof = only(evidence.filter(r => r.record.kind === "verification"
    && rows(result.record.evidence_refs).includes(r.record.evidence_id)));
  const v = proof?.record;
  if (!v || v.attempt_seal_digest !== s.digest || v.accept_manifest_digest !== s.snapshot_digest
      || v.verification !== "verified" || v.verifier_instance_id !== s.checker_instance_id
      || v.verified_by !== s.checker_adapter_id || journal.indexOf(request) >= journal.indexOf(seal)
      || journal.indexOf(seal) >= journal.indexOf(proof)
      || journal.indexOf(proof) >= journal.indexOf(result)) return null;
  return {snapshot: s.snapshot_digest, checkerAdapter: s.checker_adapter_id,
    testReportDigest: s.test_report_digest};
}

// The last dispatch for the accepted node must be the exact action that succeeded.
function acceptedAction(journal, gate, node) {
  const before = journal.slice(0, journal.indexOf(gate));
  const request = journal.filter(r => r.record_type === "action_request"
    && r.record.node_id === node.node_id).at(-1);
  const q = request?.record;
  if (!patch(q) || !isId(q.action_id) || !isId(q.attempt_id)
      || q.instance_id !== node.instance_id || !isId(q.run_authorization_id)
      || !isDigest(q.run_authorization_digest)) return null;
  const same = journal.filter(r => r.record_type === "action_request"
    && (r.record.action_id === q.action_id || r.record.attempt_id === q.attempt_id));
  const result = only(journal.filter(r => r.record_type === "action_result"
    && (r.record.action_id === q.action_id || r.record.attempt_id === q.attempt_id)));
  if (only(same) !== request || !before.includes(request) || !result
      || before.indexOf(result) <= before.indexOf(request)
      || result.record.attempt_id !== q.attempt_id || result.record.action_id !== q.action_id
      || result.record.instance_id !== q.instance_id || result.record.outcome !== "succeeded") {
    return null;
  }
  const seal = checkedSnapshot(before, request, result, node);
  return seal && {q, seal};
}

function acceptedPatch(detail, runId) {
  const taskId = detail?.task?.id, journal = rows(detail?.records);
  if (!isId(taskId) || detail.task.unreadable !== false || detail.config?.task?.id !== taskId
      || detail.run?.run_id !== runId || !isDigest(detail.run.config_digest)
      || !Array.isArray(detail.warnings) || detail.warnings.length
      || journal.some(r => r?.record?.run_id !== runId)) return null;
  const terminal = only(journal.filter(r => r.record_type === "run_terminal"));
  if (!terminal || terminal !== journal.at(-1) || terminal.record.state !== "complete"
      || !isId(terminal.record.terminal_id)) return null;
  const graph = detail.graph?.definition, settled = rows(terminal.record.settled_nodes);
  const nodes = rows(graph?.nodes), gate = journal.filter(r => r.record_type === "decision").at(-1);
  const decision = gate?.record;
  if (decision?.action !== "approve" || !isId(decision.receipt_id)
      || decision.config_digest !== detail.run.config_digest) return null;
  const end = only(nodes.filter(n => n?.kind === "gate" && n.gate_id === decision.gate_id));
  const edges = rows(graph?.edges);
  if (!isId(end?.node_id) || !settled.includes(end.node_id)
      || edges.some(e => e?.from_node === end.node_id && e.condition === "on_approved")) {
    return null;
  }
  const incoming = edges.filter(e => e?.condition === "on_succeeded"
    && e.to_node === end.node_id).map(e => e.from_node);
  const node = only(nodes.filter(n => n?.kind === "task" && patch(n) && incoming.includes(n.node_id)
    && settled.includes(n.node_id)));
  if (!node || ![node.node_id, node.instance_id, node.verifier_instance_id].every(isId)
      || node.instance_id === node.verifier_instance_id) return null;
  const instance = id => only(rows(detail.config.instances).filter(v => v?.id === id))?.adapter;
  const doer = {instanceId: node.instance_id, adapter: instance(node.instance_id)};
  const checker = {instanceId: node.verifier_instance_id,
    adapter: instance(node.verifier_instance_id)};
  if (!isId(doer.adapter) || !isId(checker.adapter)) return null;
  const action = acceptedAction(journal, gate, node);
  if (!action || action.seal.checkerAdapter !== checker.adapter) return null;
  const request = action.q;
  return {taskId, runId, nodeId: node.node_id, actionId: request.action_id,
    attemptId: request.attempt_id, receiptId: decision.receipt_id,
    terminalId: terminal.record.terminal_id, doer, checker, snapshot: action.seal.snapshot,
    testReportDigest: action.seal.testReportDigest, grant: request.run_authorization_id,
    grantDigest: request.run_authorization_digest};
}

function projectSource(projectId, ref, attempt) {
  const {grant, grantDigest, ...citation} = ref;
  const selection = {action_id: ref.actionId, attempt_id: ref.attemptId};
  const step = {nodeId: ref.nodeId, ownerId: ref.doer.instanceId,
    verifierId: ref.checker.instanceId};
  if (!matchesAtlasAttempt(attempt, selection, step, ref.runId) || attempt.outcome !== "succeeded"
      || attempt.manifest_digest !== ref.snapshot || !(attempt.files_total > 0)
      || attempt.verdict?.status !== "verified"
      || attempt.verdict.adapter_id !== ref.checker.adapter
      || attempt.tests.source !== "native" || attempt.tests.protocol.status !== "passed") {
    return null;
  }
  const {policy, binding, counts} = attempt.tests.protocol;
  if (binding.grant !== grant || binding.grant_digest !== grantDigest
      || policy.runner !== "python-unittest-v1") return null;
  return {...citation, projectId, tests: {
    runner: policy.runner, total: counts.total, failures: counts.failures,
    errors: counts.errors, skipped: counts.skipped},
  steps: ["apply_patch", "run_tests", "independent_check", "result_gate"]};
}

// Catalog ordering belongs to the caller. A network/refusal error propagates instead of
// silently substituting another source. The caller's guard pins this conversation and connection.
export async function findReviewSource({readJson, projectId, runIds, taskForRun, valid}) {
  if (!valid() || !Array.isArray(runIds) || typeof taskForRun !== "function"
      || !(projectId === null || /^[a-f0-9]{32}$/.test(projectId))) return null;
  const project = await readJson(path.project());
  if (!valid() || project?.project_id !== projectId || !["view", "active"].includes(project.mode)
      || (projectId === null && project.mode !== "view")) return null;
  for (const id of new Set(runIds)) {
    if (!isId(id)) continue;
    const taskId = taskForRun(id);
    if (!isId(taskId)) continue;
    const detail = await readJson(path.run(id));
    if (!valid()) return null;
    const manual = await manualReviewSource(detail, id, taskId, projectId);
    if (!valid()) return null;
    let source = manual, ref;
    if (!source) {
      ref = acceptedPatch(detail, id);
      if (!ref || ref.taskId !== taskId) continue;
      const attempt = await readJson(path.atlasAttempt(id, ref.nodeId, ref.actionId));
      if (!valid()) return null;
      source = projectSource(projectId, ref, attempt);
      if (!source) continue;
    }
    if (projectId === null) {
      const raw = await readJson(path.run(id));
      const reread = manual ? await manualReviewSource(raw, id, taskId, projectId)
        : acceptedPatch(raw, id);
      if (!valid() || JSON.stringify(manual || ref) !== JSON.stringify(reread)) return null;
    }
    const end = await readJson(path.project());
    return valid() && end?.project_id === projectId && end.mode === project.mode
      && end.hub_origin === project.hub_origin && end.demo === project.demo ? source : null;
  }
  return null;
}
