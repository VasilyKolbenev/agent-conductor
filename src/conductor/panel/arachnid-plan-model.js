"use strict";
import {sha256Hex, stableJson} from "./desk-wizard-digest.js";

const MODEL = "gpt-6.1-sol";
const STAGE_ROLES = {
  goal: "role-thinker", identify: "role-thinker", diagnose: "role-diagnostician",
  design: "role-designer", do: "role-implementer",
};
const STAGES = Object.keys(STAGE_ROLES);
const BINDINGS = {
  "role-thinker": "codex", "role-designer": "codex", "role-diagnostician": "grok-build",
  "role-implementer": "codex", "role-checker": "codex",
};
export const same = (a, b) => stableJson(a) === stableJson(b);
export function need(condition, code) {
  if (!condition) throw new Error(code);
}
const shortText = value => typeof value === "string" && value.trim() && value.length <= 1200;
const usableBrief = value => typeof value === "string" && value.trim() && !value.includes("\0");

function verifyProposal(proposal) {
  need(proposal && shortText(proposal.criterion) && (proposal.question === null || shortText(proposal.question))
    && [null, "dalio-v6"].includes(proposal.cycle_id) && proposal.roles
    && typeof proposal.roles === "object" && !Array.isArray(proposal.roles)
    && Object.keys(proposal).every(k => ["criterion", "question", "roles", "cycle_id", "depth"].includes(k))
    && (proposal.depth == null || ["quick", "balanced", "thorough"].includes(proposal.depth))
    && Object.entries(proposal.roles).every(([role, provider]) =>
      Object.hasOwn(BINDINGS, role) && BINDINGS[role] === provider), "proposal_invalid");
}

export function dalioOutline() {
  const roles = Object.entries(BINDINGS).map(([role, provider]) => ({
    role, provider, instance: "instance-" + role, model: provider === "codex" ? MODEL : null,
  }));
  const node_limits = STAGES.map(node_id => ({node_id, timeout_seconds: 600, max_attempts: 1}));
  const limits = {max_actions: 5, max_action_seconds: 1200, max_total_task_seconds: 3600,
    duration_seconds: 7200, node_limits};
  return {roles, steps: [...STAGES], stageRoles: {...STAGE_ROLES}, limits};
}

function admitProviders(catalog) {
  for (const [id, required, road] of [["codex", ["review", "dispatch"], "boundary"],
    ["grok-build", ["review"], "review_only"]]) {
    const rows = catalog.providers?.filter(v => v.provider_id === id);
    const row = rows?.[0];
    need(rows?.length === 1 && row.offered === true && row.availability === "available"
      && row.auth === "subscription" && row.task_road === road && Array.isArray(row.controls)
      && required.every(c => row.controls.includes(c))
      && (id !== "codex" || row.model_pin_supported === true), "provider_unavailable");
  }
}

function dalioDocument(catalog, locale) {
  const starters = catalog.starters?.filter(s => s.starter_id === "dalio-v6" && s.revision === 6);
  const source = starters?.[0]?.document;
  need(starters?.length === 1 && source?.template_id === "template-dalio" && source.revision === 6
    && Array.isArray(source.nodes) && same(source.nodes.filter(n => n.kind === "task").map(n => n.node_id), STAGES)
    && source.nodes.some(n => n.gate_id === "gate-confirm-do")
    && source.nodes.some(n => n.gate_id === "gate-result"), "starter_unavailable");
  const nodes = source.nodes.map(n => {
    if (n.kind !== "task") return n;
    const args = {...n.arguments};
    need(n.role_id === STAGE_ROLES[n.node_id] && args.work_item_id === "work-001", "starter_unavailable");
    if (n.node_id === "do") {
      need(n.capability === "dispatch" && n.role_id === "role-implementer" && n.verifier_role_id === "role-checker"
        && args.profile === "implement" && args.instruction_ref === "instruction-plan"
        && args.artifact_refs.includes("artifact-plan"), "starter_unavailable");
      args.profile = "implement-patch-v1";
      args.artifact_refs = [...new Set([...args.artifact_refs, "artifact-brief"])];
    } else {
      need(n.capability === "review" && Array.isArray(args.target_artifact_refs), "starter_unavailable");
      args.target_artifact_refs = [...new Set([...args.target_artifact_refs, "artifact-brief"])];
    }
    return {...n, arguments: args, timeout_seconds: 600, attempt_bound: 1};
  });
  return {schema_version: source.schema_version, title: locale === "ru" ? "Далио · Codex и Grok" : "Dalio · Codex and Grok",
    execution_contract: "bounded-run-v1", nodes, edges: source.edges};
}

export function targetIds({advisorId, projectId}) {
  need(/^advice-[0-9a-f]{20}$/.test(advisorId) && /^[0-9a-f]{32}$/.test(projectId), "proposal_invalid");
  const id = sha256Hex(stableJson([projectId, advisorId])).slice(0,24);
  const taskId = "atlas-" + id;
  return {taskId, runId:taskId + "-r1", workflowId:"dalio-" + id};
}

export function recordedDalio(request, catalog, baseCommit) {
  const {advisorId, projectId, proposal, brief, locale} = request;
  need(usableBrief(brief), "proposal_invalid");
  verifyProposal(proposal);
  need(typeof baseCommit === "string" && /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/.test(baseCommit), "source_required");
  const {roles, limits} = dalioOutline();
  const document = dalioDocument(catalog, locale);
  const {taskId, runId, workflowId} = targetIds(request);
  const inputs = {"artifact-brief": brief + "\n\n" + proposal.criterion,
    "instruction-plan": locale === "ru"
      ? "Подготовь ограниченную правку в рамках принятого плана и брифа. Изменяй только файлы задачи."
      : "Prepare a bounded patch for the accepted plan and brief. Modify only files in the task."};
  const title = [...brief.trim().replace(/[\u0000-\u001f\u007f-\u009f]+/g, " ")].slice(0, 160).join("");
  return {projectId, advisorId, brief, proposal, locale, baseCommit, taskId, title, runId, workflowId,
    roles, inputs, document, limits};
}

export function compileDalio(request, catalog, git) {
  need(git?.git?.state === "repo", "source_required");
  admitProviders(catalog);
  return recordedDalio(request, catalog, git.git.head?.commit);
}
