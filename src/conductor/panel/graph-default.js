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
  // Which product drives each instance this plan names, and which model that
  // instance PINS. Both are the frozen configuration's words, and neither is
  // in the plan above — a template names roles, a run's binding names
  // instances, and only a deployment names a product and a model.
  //
  // This is the fact the default used to have nowhere to put, and it went
  // wrong three ways for want of it:
  //
  // - the Do step drew `kimi-code` while its binding said `claude-dev`;
  // - every OTHER step said `claude-dev` too, so one instance was drawn as
  //   four different products at once. That was the same defect, and it was
  //   the larger half: it is why the first one was easy to miss;
  // - the Do step carried a `model: sonnet` resource row. A resource row is a
  //   durable demand a plan makes of every machine that runs it, and the
  //   shipped cycle deliberately makes no such demand about a model.
  //
  // Every step now names an instance this deployment really declares, each
  // instance appears once here with the product that serves it, and the model
  // appears where a real read puts it. A `claude-dev` binding shows Claude Code
  // and Opus 5 because that is what this deployment says, not because anything
  // renders a vendor.
  //
  // TWO instances, and the number came DOWN from a first attempt at four. That
  // attempt named `deepseek-lane` and `kimi-lane`, which no ordinary
  // configuration declares — and the wire suite caught it at once: a Human who
  // presses "Start from the default" and saves gets `service_refused`, because
  // the route holds a plan to the run's frozen configuration. A default nobody
  // can save is worse than a default that shows fewer products, and the old
  // four-product picture was only reachable while every step claimed one
  // instance it did not run on. So the fixture names the two instances the
  // product's own canonical configuration declares.
  //
  // One pins a model and one does not, which is deliberate: `null` is the
  // state a reader is most likely to be shown something false about.
  deployment: [
    {instance_id: "claude-dev", adapter_id: "claude-code",
      model: "claude-opus-5"},
    {instance_id: "codex-review", adapter_id: "codex", model: null},
  ],
  nodes: [
    {node_id: "goal", kind: "task", title: "Goal",
      harness: "claude-code", health: "ready", phase: "succeeded",
      capabilities: ["evidence"], stage: "goal",
      evidence: [{evidence_id: "ev-goal-brief", kind: "result",
        verification: "verified"}],
      binding: {instance_id: "claude-dev", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "spec",
          target_artifact_refs: ["artifact-brief"],
          result_artifact_ref: "artifact-goal"}},
      gate: null},
    {node_id: "identify", kind: "task", title: "Identify Problems",
      harness: "codex", health: "ready", phase: "succeeded",
      capabilities: ["evidence", "review"], stage: "identify",
      evidence: [{evidence_id: "ev-identify-list", kind: "result",
        verification: "verified"}],
      binding: {instance_id: "codex-review", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "quality",
          target_artifact_refs: ["artifact-goal"],
          result_artifact_ref: "artifact-problems"}},
      gate: null},
    {node_id: "diagnose", kind: "task", title: "Diagnose Root Causes",
      harness: "codex", health: "busy", phase: "requested",
      capabilities: ["evidence", "review"], stage: "diagnose",
      evidence: [],
      binding: {instance_id: "codex-review", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "quality",
          target_artifact_refs: ["artifact-problems"],
          result_artifact_ref: "artifact-causes"}},
      gate: null},
    {node_id: "design", kind: "task", title: "Design the Plan",
      harness: "claude-code", health: "ready", phase: "idle",
      capabilities: ["evidence"], stage: "design",
      evidence: [],
      binding: {instance_id: "claude-dev", capability: "review",
        arguments: {work_item_id: "work-001", review_profile: "spec",
          target_artifact_refs: ["artifact-causes"],
          result_artifact_ref: "artifact-plan"}},
      gate: null},
    {node_id: "confirm-gate", kind: "gate", title: "Human Gate — Confirm Do",
      harness: null, health: "unknown", phase: "idle",
      capabilities: [],
      evidence: [],
      gate: {gate_id: "gate-confirm-do", state: "pending"}},
    {node_id: "do", kind: "task", title: "Do",
      harness: "claude-code", health: "ready", phase: "idle",
      capabilities: ["dispatch", "evidence", "stop"], stage: "do",
      evidence: [],
      // The sandbox row and NOTHING else. A resource row is a durable demand
      // the plan makes of whatever machine runs it, so `sandbox: project-root`
      // belongs here — it names what the work may touch — and a model does
      // not. Which model runs is the deployment's business, and this fixture
      // now shows it where a real read shows it: in `deployment` below.
      resources: [{kind: "sandbox", name: "project-root"}],
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
