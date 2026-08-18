"use strict";
// The Cockpit's default demonstration: the product's default graph, which the
// December Command fixed as Dalio's five-step process — Goal, Identify
// Problems, Diagnose Root Causes, Design the Plan, Do — with a Human gate
// before the one effect-capable step, a result gate after it, and a bounded
// loop that turns problems into progress by REOPENING work, never by
// executing it. Completion is only ever a verified result: the result gate
// ships pending, and no unknown or unverified outcome may satisfy it.
//
// Panel-internal fixture data through the one adapter seam — not a wire
// contract. The registry stays empty on purpose: vendor rows arrive as data
// from the one registry when a source exists, never as a second copy here;
// until then every badge draws neutrally from its harness string. Harness
// ids on steps are data references showing different products holding
// different steps of one process — no vendor branch renders any of them.
export const DALIO_DEFAULT = Object.freeze({
  fixture_schema: 1,
  run: {run_id: "run-dalio-default", mode: "confirm"},
  registry: [],
  nodes: [
    {node_id: "goal", kind: "task", title: "Goal",
      harness: "claude-code", health: "ready", phase: "succeeded",
      capabilities: ["evidence"], stage: "goal",
      evidence: [{evidence_id: "ev-goal-brief", kind: "result",
        verification: "verified"}],
      gate: null},
    {node_id: "identify", kind: "task", title: "Identify Problems",
      harness: "codex", health: "ready", phase: "succeeded",
      capabilities: ["evidence", "review"], stage: "identify",
      evidence: [{evidence_id: "ev-identify-list", kind: "result",
        verification: "verified"}],
      gate: null},
    {node_id: "diagnose", kind: "task", title: "Diagnose Root Causes",
      harness: "deepseek-harness", health: "busy", phase: "requested",
      capabilities: ["evidence", "review"], stage: "diagnose",
      evidence: [],
      gate: null},
    {node_id: "design", kind: "task", title: "Design the Plan",
      harness: "claude-code", health: "ready", phase: "idle",
      capabilities: ["evidence"], stage: "design",
      evidence: [],
      gate: null},
    {node_id: "confirm-gate", kind: "gate", title: "Human Gate — Confirm Do",
      harness: null, health: "unknown", phase: "idle",
      capabilities: [],
      evidence: [],
      gate: {gate_id: "gate-confirm-do", state: "pending"}},
    {node_id: "do", kind: "task", title: "Do",
      harness: "kimi-code", health: "ready", phase: "idle",
      capabilities: ["dispatch", "evidence", "stop"], stage: "do",
      evidence: [],
      gate: null},
    {node_id: "result-gate", kind: "gate", title: "Result Gate",
      harness: null, health: "unknown", phase: "idle",
      capabilities: [],
      evidence: [],
      gate: {gate_id: "gate-result", state: "pending"}},
    {node_id: "retry-loop", kind: "loop", title: "Turn problems into progress",
      harness: null, health: "unknown", phase: "idle",
      capabilities: [],
      evidence: [],
      gate: null,
      loop: {bound: 3, pass: 1, back_to: "identify"}},
  ],
  edges: [
    {from: "goal", to: "identify"},
    {from: "identify", to: "diagnose"},
    {from: "diagnose", to: "design"},
    {from: "design", to: "confirm-gate"},
    {from: "confirm-gate", to: "do"},
    {from: "do", to: "result-gate"},
    {from: "result-gate", to: "retry-loop"},
  ],
  timeline: [
    {event_id: "t-goal-succeeded", at: "2026-08-18T08:00:10Z",
      node_id: "goal", phase: "succeeded"},
    {event_id: "t-identify-succeeded", at: "2026-08-18T08:12:41Z",
      node_id: "identify", phase: "succeeded"},
    {event_id: "t-diagnose-requested", at: "2026-08-18T08:13:02Z",
      node_id: "diagnose", phase: "requested"},
  ],
});
