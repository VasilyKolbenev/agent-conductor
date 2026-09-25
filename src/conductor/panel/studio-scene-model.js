"use strict";
// One frozen run supplies both scene lenses. No clock, transport or scheduling.
import {attemptInFlight, decisionRows, endingOf} from "./studio-runread.js";

const rows = (value) => Array.isArray(value) ? value : [];
const mapBy = (values, key) => new Map(rows(values).map((row) => [row[key], row]));

function ordered(nodes, edges) {
  const waiting = new Set(nodes.map((node) => node.node_id)), result = [];
  while (waiting.size) {
    const ready = nodes.filter((node) => waiting.has(node.node_id)
      && !edges.some((edge) => edge.to_node === node.node_id && waiting.has(edge.from_node)));
    // Invalid cyclic drawings are never presented as an invented order.
    if (!ready.length) return null;
    for (const node of ready) { result.push(node); waiting.delete(node.node_id); }
  }
  return result;
}

function gateWord(runtime, gate) {
  if (runtime?.decision === "unknown") return "decision_unknown";
  if (gate?.needs_decision) return "needs_decision";
  if (["satisfied", "failed", "changes_requested", "waived"].includes(runtime?.decision)
      && gate?.standing_belongs_to_current_lap !== false) return `decision_${runtime.decision}`;
  return gate?.why_not || "road_not_open";
}

function stepWord(detail, node, runtime, scheduled, gate) {
  if (node.kind === "gate") return gateWord(runtime, gate);
  if (scheduled?.state === "unreachable") return "closed";
  if (attemptInFlight(detail, node.node_id)) return "awaiting_result";
  if (scheduled?.state === "settled") return runtime?.outcome ? `outcome_${runtime.outcome}` : "settled";
  if (scheduled?.state === "runnable") return "runnable";
  return scheduled?.attempts_spent ? "spent" : "blocked";
}

function stepsOf(detail, nodes) {
  const runtime = mapBy(detail.graph?.runtime?.nodes, "node_id");
  const schedule = mapBy(detail.graph?.schedule?.nodes, "node_id");
  const gates = mapBy(detail.graph?.situation?.gates, "node_id");
  return nodes.map((node, slot) => ({nodeId: node.node_id, title: node.title || node.node_id,
    kind: node.kind, slot, ownerId: node.instance_id || null,
    verifierId: node.verifier_instance_id || null, node,
    runtime: runtime.get(node.node_id) || null, scheduled: schedule.get(node.node_id) || null,
    gate: gates.get(node.node_id) || null,
    word: stepWord(detail, node, runtime.get(node.node_id), schedule.get(node.node_id), gates.get(node.node_id)),
    outcome: runtime.get(node.node_id)?.outcome || null}));
}

function participantWord(assigned) {
  if (!assigned.length) return "unassigned";
  if (assigned.some((step) => step.word === "awaiting_result")) return "awaiting_result";
  if (assigned.some((step) => step.word === "runnable")) return "runnable";
  if (assigned.every((step) => step.scheduled?.state === "settled")) {
    const failed = assigned.find((step) => step.outcome && step.outcome !== "succeeded");
    return failed ? `outcome_${failed.outcome}` : "settled";
  }
  return "blocked";
}

function participantsOf(detail, steps) {
  return rows(detail.config?.instances).map((instance) => {
    const performs = steps.filter((step) => step.ownerId === instance.id);
    const verifies = steps.filter((step) => step.verifierId === instance.id);
    const assigned = steps.filter((step) => performs.includes(step) || verifies.includes(step));
    return {instanceId: instance.id, adapter: instance.adapter, model: instance.model,
      performs: performs.map((step) => step.nodeId), verifies: verifies.map((step) => step.nodeId),
      duty: performs.length ? verifies.length ? "both" : "perform" : verifies.length ? "verify" : "none",
      word: participantWord(assigned)};
  });
}

function linksOf(edges, steps) {
  const indexed = mapBy(steps, "nodeId");
  return edges.map((edge) => ({from: edge.from_node, to: edge.to_node,
    kind: edge.condition ? "condition" : "next", condition: edge.condition || null,
    open: rows(indexed.get(edge.to_node)?.scheduled?.opened_by).includes(edge.from_node)}));
}

function loopReason(detail, step, edges, steps, decisions) {
  const incoming = edges.filter((edge) => edge.to_node === step.nodeId
    && rows(step.scheduled?.opened_by).includes(edge.from_node));
  const source = incoming.map((edge) => steps.find((row) => row.nodeId === edge.from_node))
    .find((row) => row?.kind === "gate" || row?.outcome);
  if (!source) return null;
  if (source.kind !== "gate") return {kind: "outcome", outcome: source.outcome};
  const standing = decisions.find((row) => row.node_id === source.nodeId)?.standing;
  const receipt = rows(detail.records).find((row) => row.record_type === "decision"
    && row.record.receipt_id === standing)?.record;
  return receipt ? {kind: "decision", text: receipt.reason,
    evidenceCount: rows(receipt.evidence_refs).length} : null;
}

function loopsOf(detail, steps, edges) {
  const decisions = decisionRows(detail);
  return steps.filter((step) => step.kind === "loop").map((step) => ({nodeId: step.nodeId,
    backTo: step.node.loop?.back_to, bound: step.node.loop?.bound,
    pass: step.runtime?.pass ?? null, boundReached: step.runtime?.bound_reached === true,
    reason: loopReason(detail, step, edges, steps, decisions)}));
}

export function sceneOf(detail) {
  const definition = detail?.graph?.definition;
  if (!definition) return null;
  const edges = rows(definition.edges), nodes = ordered(rows(definition.nodes), edges);
  if (nodes === null) return null;
  const steps = stepsOf(detail, nodes), ending = endingOf(detail, detail.graph?.schedule);
  const needs = steps.filter((step) => step.word === "needs_decision");
  const pending = steps.filter((step) => step.word === "awaiting_result");
  const positions = ending.ended ? [] : [...needs, ...(pending.length ? pending
    : steps.filter((step) => step.word === "runnable"))].map((step) => step.nodeId);
  return {runId: detail.run.run_id, steps, participants: participantsOf(detail, steps),
    links: linksOf(edges, steps), loops: loopsOf(detail, steps, edges), positions, ending};
}

// Variable-width slots and nonoverlapping planets. Only geometry is inferred.
export function traceLayout(scene, available) {
  const widths = scene.steps.map((step) => step.kind === "task" ? 104 : step.kind === "gate" ? 56 : 40);
  const tasks = scene.steps.filter((step) => step.kind === "task").length;
  const extra = Math.min(44, Math.max(0, available - 48 - widths.reduce((a, b) => a + b, 0)) / Math.max(1, tasks));
  let cursor = 24;
  const points = scene.steps.map((step, at) => {
    const width = widths[at] + (step.kind === "task" ? extra : 0);
    const point = {id: step.nodeId, x: cursor + width / 2}; cursor += width; return point;
  });
  const indexed = mapBy(points, "id");
  const preferred = scene.participants.map((participant, order) => {
    const ids = participant.performs.length ? participant.performs : participant.verifies;
    const positions = ids.map((id) => indexed.get(id)?.x).filter((x) => x !== undefined);
    return {id: participant.instanceId, order,
      x: positions.length ? positions.reduce((a, b) => a + b) / positions.length : cursor + order * 164};
  }).sort((a, b) => a.x - b.x || a.order - b.order);
  let right = -80;
  const planets = preferred.map((point) => {
    const x = Math.max(point.x, right + 164); right = x; return {id: point.id, x};
  });
  return {width: Math.max(available, cursor + 24, right + 84), points, planets};
}
