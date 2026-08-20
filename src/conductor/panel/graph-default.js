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
// contract. The registry stays empty on purpose: vendor rows are DATA the
// server's own registry supplies to a loaded run, never a second copy here,
// so every badge in this default draws neutrally from its harness string.
// Harness ids on steps are data references showing different products
// holding different steps of one process — no vendor branch renders any of
// them, here or anywhere else in this window.
//
// The bindings ARE the wire's own words, and they are the reason only two
// capabilities appear here. Of the six, only `review` and `dispatch` can be
// written down in advance: the other four name a runtime document a plan has
// not got — `target_action_id`, `target_attempt_id`, `prior_action_id` — and
// a plan that named one would be naming a record that does not exist yet. So
// the four thinking steps each REVIEW the artifact the step before produced,
// and Do — the one effect-capable step, behind the one Human gate — is the
// only `dispatch` in the process.
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
      binding: {instance_id: "claude-dev", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "spec",
          target_artifact_refs: ["artifact-brief"]}},
      gate: null},
    {node_id: "identify", kind: "task", title: "Identify Problems",
      harness: "codex", health: "ready", phase: "succeeded",
      capabilities: ["evidence", "review"], stage: "identify",
      evidence: [{evidence_id: "ev-identify-list", kind: "result",
        verification: "verified"}],
      binding: {instance_id: "claude-dev", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "quality",
          target_artifact_refs: ["artifact-goal"]}},
      gate: null},
    {node_id: "diagnose", kind: "task", title: "Diagnose Root Causes",
      harness: "deepseek-harness", health: "busy", phase: "requested",
      capabilities: ["evidence", "review"], stage: "diagnose",
      evidence: [],
      binding: {instance_id: "claude-dev", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "quality",
          target_artifact_refs: ["artifact-problems"]}},
      gate: null},
    {node_id: "design", kind: "task", title: "Design the Plan",
      harness: "claude-code", health: "ready", phase: "idle",
      capabilities: ["evidence"], stage: "design",
      evidence: [],
      binding: {instance_id: "claude-dev", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "spec",
          target_artifact_refs: ["artifact-causes"]}},
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
      resources: [{kind: "model", name: "sonnet"},
        {kind: "sandbox", name: "project-root"}],
      binding: {instance_id: "claude-dev", capability: "dispatch",
        arguments: {work_item_id: "work-001",
          instruction_ref: "instruction-plan", profile: "implement",
          artifact_refs: ["artifact-plan"], output_limit_profile: "normal"}},
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
