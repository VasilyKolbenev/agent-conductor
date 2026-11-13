"use strict";
import {path} from "./desk-transport.js";
import {planningSession} from "./arachnid-advisor.js";
import {documentId} from "./desk-wizard-digest.js";
import {observeAdvice, suggestionFrom} from "./desk-advice-run.js";
import {compileDalio, need, recordedDalio, same, targetIds} from "./arachnid-plan-model.js";

const DIGEST = /^sha256:[0-9a-f]{64}$/;
const held = new WeakMap();
const records = (run, kind) => run.records.filter(r => r.record_type === kind).map(r => r.record);
const freeze = value => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
};

function session(door, projectId) {
  const check = () => need(door.valid(), "session_changed");
  async function read(url) {
    check();
    const value = await door.read(url);
    check();
    return value;
  }
  async function owner() {
    const id = await read(path.project());
    need(id?.mode === "active" && id.project_id === projectId, "project_changed");
  }
  async function write(name, subject, body) {
    await owner();
    check();
    return door.submit(name, subject, body);
  }
  return {read, owner, write, check};
}

// A transport failure may mean that the write landed. Only the canonical read can settle it.
async function ensure(readState, write) {
  if (await readState()) return;
  let failure;
  try {
    const answer = await write();
    if (answer?.status !== "accepted") failure = new Error(answer?.code || "write_unknown");
  } catch (error) { failure = error; }
  if (!await readState()) throw failure || new Error("write_unconfirmed");
}

async function approvedAdvice(road, request) {
  const run = await road.read(path.run(request.advisorId));
  need(Array.isArray(run?.records) && run.run?.run_id === request.advisorId, "proposal_invalid");
  const source = planningSession(run, request.projectId);
  need(source && (!request.sessionId || source === request.sessionId), "proposal_invalid");
  const rows = records(run, "artifact").filter(r => r.artifact_ref === "artifact-brief");
  need(rows.length === 1 && typeof rows[0].content === "string", "proposal_invalid");
  const input = JSON.parse(rows[0].content);
  need(input.task === request.brief && input.current_cycle === "dalio-v6", "proposal_invalid");
  const advice = await observeAdvice({readJson: road.read}, {
    id: request.advisorId, content: rows[0].content, provider: "codex", model: "gpt-6.1-sol",
  });
  need(advice.phase === "result" && advice.choice === "approve"
    && same(suggestionFrom(advice.content, input), request.proposal), "proposal_invalid");
  need(["en", "ru"].includes(input.language), "proposal_invalid");
  return input.language;
}

async function workflow(road, p) {
  async function published() {
    const state = await road.read(path.workflow(p.workflowId));
    need(Array.isArray(state?.revisions) && !state.unreadable_revisions?.length, "workflow_conflict");
    if (!state.revisions.length) return false;
    need(same(state.revisions, [1]), "workflow_conflict");
    const rev = await road.read(path.revision(p.workflowId, 1));
    need(same(rev?.document, {...p.document, template_id: p.workflowId, revision: 1}), "workflow_conflict");
    return true;
  }
  if (await published()) return;
  let digest;
  await ensure(async () => {
    const state = await road.read(path.workflow(p.workflowId));
    if (!state.draft) return false;
    need(same(state.draft.document, p.document) && DIGEST.test(state.draft.digest)
      && state.publishable && !state.diagnostics?.length, "workflow_conflict");
    digest = state.draft.digest;
    return true;
  }, () => road.write("draft", p.workflowId, {expected_absent: true, document: p.document}));
  await ensure(published, () => road.write("revisions", p.workflowId, {reviewed_digest: digest, revision: 1}));
}

function reviewSourceMode(document) {
  need(Array.isArray(document?.nodes), "workflow_conflict");
  const nodes = document.nodes.filter(node => node.node_id === "diagnose");
  need(nodes.length === 1 && Array.isArray(nodes[0].arguments?.target_artifact_refs),
    "workflow_conflict");
  return nodes[0].arguments.target_artifact_refs.includes("source-context");
}

function correctionMode(document) {
  need(Array.isArray(document?.nodes), "workflow_conflict");
  const nodes = document.nodes.filter(n => n.node_id === "do");
  need(nodes.length === 1 && [1, 2].includes(nodes[0].attempt_bound), "workflow_conflict");
  return nodes[0].attempt_bound === 2;
}

async function frozenDocument(road, workflowId) {
  const state = await road.read(path.workflow(workflowId));
  need(Array.isArray(state?.revisions) && !state.unreadable_revisions?.length, "workflow_conflict");
  if (state.revisions.length) {
    need(same(state.revisions, [1]), "workflow_conflict");
    const revision = await road.read(path.revision(workflowId, 1));
    need(revision?.document, "workflow_conflict");
    return revision.document;
  }
  if (!state.draft) return null;
  need(state.draft.document, "workflow_conflict");
  return state.draft.document;
}

// A persisted draft already binds the choice, even before the run or grant exists.
export async function readDalioChoice(door, request) {
  const road = session(door, request.projectId);
  await road.owner();
  const document = await frozenDocument(road, targetIds(request).workflowId);
  return document ? correctionMode(document) : null;
}

async function task(road, p) {
  await ensure(async () => {
    const facts = await road.read(path.tasks());
    need(Array.isArray(facts?.tasks), "task_conflict");
    const found = facts.tasks.filter(t => t.task_id === p.taskId);
    if (!found.length) return false;
    need(found.length === 1 && found[0].title === p.title, "task_conflict");
    return true;
  }, () => road.write("tasks", null, {task_id: p.taskId, title: p.title}));
}

async function seed(road, p, readOnly = false) {
  async function pinned() {
    const found = await road.read(path.preparation(p.taskId));
    need(found?.task?.task_id === p.taskId, "seed_conflict");
    const s = found.seed;
    if (!s) return false;
    need(s.task_id === p.taskId && s.work_item_id === "work-001" && s.source === "git"
      && s.base_commit === p.baseCommit && s.include_agent_instructions === false
      && s.work_scope === p.taskId && ["staged", "seeded"].includes(s.state), "seed_conflict");
    return s.state === "seeded";
  }
  if (readOnly) return need(await pinned(), "seed_conflict");
  await ensure(pinned, () => road.write("seed", p.taskId, {work_item_id: "work-001", source: "git",
    expect_commit: p.baseCommit, include_agent_instructions: false}));
}

function bindings(p) {
  const participants = p.roles.map(r => ({instance_id: r.instance, provider_id: r.provider, model: r.model}));
  const assignments = Object.fromEntries(p.roles.map(r => [r.role, r.instance]));
  return {participants, assignments};
}

function verifyGraph(detail, p) {
  const instances = p.roles.map(r => ({id:r.instance, adapter:r.provider, ...(r.model ? {model:r.model} : {})}));
  const incoming = detail?.config?.instances;
  need(Array.isArray(incoming) && incoming.length === instances.length
    && instances.every(row => incoming.some(item => same(item, row)))
    && detail.run?.run_id === p.runId && detail.run.mode === "policy" && detail.run.cycle_id === p.runId
    && detail.config?.automation_contract === "bounded-run-v1"
    && same(detail.config.task, {id:p.taskId, work_scope:p.taskId})
    && same(detail.config.workflow, {id:p.workflowId, revision:1}) && Array.isArray(detail.records)
    && Array.isArray(detail.warnings) && !detail.warnings.length, "run_conflict");
  const graphs = records(detail, "graph_definition"), graph = graphs[0];
  need(graphs.length === 1 && graph.run_id === p.runId && graph.execution_contract === "bounded-run-v1"
    && same(graph.edges, p.document.edges) && graph.nodes.length === p.document.nodes.length, "run_conflict");
  const {assignments} = bindings(p);
  for (const node of p.document.nodes) {
    const {role_id, verifier_role_id, ...expected} = node;
    if (role_id) {
      expected.instance_id = assignments[role_id];
      expected.arguments = {...node.arguments, work_scope:p.taskId};
      if (node.purpose) expected.arguments.step_purpose = node.purpose;
    }
    if (verifier_role_id) expected.verifier_instance_id = assignments[verifier_role_id];
    need(graph.nodes.some(n => same(n, expected)), "run_conflict");
  }
}

async function run(road, p) {
  await ensure(async () => {
    const index = await road.read(path.runs());
    need(Array.isArray(index?.runs), "run_conflict");
    if (!index.runs.some(r => r.run_id === p.runId)) return false;
    verifyGraph(await road.read(path.run(p.runId)), p);
    return true;
  }, () => road.write("runs", null, {run_id:p.runId, cycle_id:p.runId, mode:"policy", task_id:p.taskId,
    automation_contract:"bounded-run-v1", workflow_id:p.workflowId, revision:1, ...bindings(p)}));
}

async function inputs(road, p, readOnly = false, restoreLegacy = false) {
  for (const [ref, content] of Object.entries(p.inputs)) {
    const id = documentId(p.runId, ref, "text/plain", content);
    async function present() {
      const detail = await road.read(path.run(p.runId));
      verifyGraph(detail, p);
      const matches = records(detail, "artifact").filter(r => r.artifact_ref === ref);
      if (!matches.length) return false;
      const [file] = matches;
      // Restore an older instruction exactly as recorded, including its lack of source inputs.
      if (restoreLegacy && ref === "instruction-plan" && p.sourcePaths.length && matches.length === 1
        && file.run_id === p.runId && !file.source_action_id && file.media_type === "text/plain"
        && file.content === p.instruction
        && file.artifact_id === documentId(p.runId, ref, "text/plain", p.instruction)) {
        p.inputs[ref] = p.instruction;
        p.sourcePaths = [];
        return true;
      }
      need(matches.length === 1 && file.run_id === p.runId && file.artifact_id === id
        && !file.source_action_id && file.media_type === "text/plain" && file.content === content, "input_conflict");
      return true;
    }
    if (readOnly) need(await present(), "input_conflict");
    else await ensure(present, () => road.write("artifacts", p.runId, {
      artifact_id:id, artifact_ref:ref, media_type:"text/plain", content}));
  }
}

async function authorized(road, p, actor, preview = null) {
  const state = await road.read(path.automation(p.runId));
  need(state?.run_id === p.runId && Object.hasOwn(state,"authorization"), "run_conflict");
  const grant = state.authorization;
  if (!grant) {
    need(state.spent_actions === 0 && !state.active_action_id, "run_conflict");
    return null;
  }
  const detail = await road.read(path.run(p.runId));
  verifyGraph(detail, p);
  need(grant.run_id === p.runId && grant.authorization_id === "grant-" + p.runId
    && grant.config_digest === detail.run.config_digest && grant.authorized_by === actor
    && Object.entries(p.limits).every(([k,v]) => same(grant[k], v)
      || k === "duration_seconds" && Date.parse(grant.expires_at) - Date.parse(grant.authorized_at) === v * 1000)
    && (!preview || Object.entries(preview.terms).every(([k,v]) => k === "duration_seconds" || same(grant[k], v))),
  "authorization_conflict");
  return grant;
}

function validatePreview(preview, p, detail) {
  const t = preview?.terms;
  need(DIGEST.test(preview?.preview_digest) && t?.run_id === p.runId
    && DIGEST.test(t.graph_digest) && t.config_digest === detail.run.config_digest
    && DIGEST.test(t.source_prefix_digest) && DIGEST.test(t.provider_config_digest)
    && same(preview.patch_steps, ["do"]) && !preview.grok_diagnostic_steps?.length
    && Object.entries(p.limits).every(([k,v]) => same(t[k],v))
    && Date.parse(preview.valid_until) > Date.now(), "preview_invalid");
}

export async function prepareDalio(door, request) {
  const road = session(door, request.projectId);
  await road.owner();
  const locale = await approvedAdvice(road, request);
  const catalog = await road.read(path.workflows());
  const document = await frozenDocument(road, targetIds(request).workflowId);
  const reviewSources = document ? reviewSourceMode(document) : true;
  const allowCorrection = document ? correctionMode(document) : request.allowCorrection;
  need(request.allowCorrection === undefined || request.allowCorrection === allowCorrection,
    "correction_conflict");
  const p = compileDalio({...request,locale,allowCorrection}, catalog,
    await road.read(path.git()), {reviewSources});
  await workflow(road, p);
  await task(road, p);
  await seed(road, p);
  await run(road, p);
  const grant = await authorized(road, p, request.actor);
  await inputs(road, p, Boolean(grant), true);
  let preview = null;
  if (!grant) {
    const detail = await road.read(path.run(p.runId));
    verifyGraph(detail, p);
    need(detail.records.every(row => row.record_type === "graph_definition"
      || row.record_type === "artifact" && Object.hasOwn(p.inputs, row.record.artifact_ref)), "run_conflict");
    const answer = await road.write("automationPreview", p.runId, p.limits);
    need(answer?.status === "accepted", answer?.code || "preview_failed");
    preview = answer.payload;
    validatePreview(preview, p, detail);
  }
  road.check();
  return resultOf(p, request.actor, preview, grant);
}

function resultOf(p, actor, preview, grant) {
  const result = freeze(JSON.parse(JSON.stringify({phase:grant ? "authorized" : "preview", projectId:p.projectId,
    advisorId:p.advisorId, taskId:p.taskId, workflowId:p.workflowId, runId:p.runId, baseCommit:p.baseCommit,
    preview, terms:preview?.terms ?? null, limits:p.limits, roles:p.roles, proposal:p.proposal, brief:p.brief,
    sourcePaths:p.sourcePaths, authorization:grant})));
  held.set(result, {p, actor, attempted:Boolean(grant)});
  return result;
}

export async function restoreDalio(door, request) {
  const road = session(door, request.projectId);
  await road.owner();
  const {taskId,runId,workflowId} = targetIds(request);
  const runs = await road.read(path.runs());
  need(Array.isArray(runs?.runs), "run_conflict");
  if (!runs.runs.some(r => r.run_id === runId)) return null;
  const state = await road.read(path.automation(runId));
  need(state?.run_id === runId && Object.hasOwn(state, "authorization"), "run_conflict");
  if (!state.authorization) return null;
  const locale = await approvedAdvice(road, request);
  const preparation = await road.read(path.preparation(taskId));
  const revision = await road.read(path.revision(workflowId, 1));
  const reviewSources = reviewSourceMode(revision?.document);
  const allowCorrection = correctionMode(revision?.document);
  const p = recordedDalio({...request,locale,allowCorrection}, await road.read(path.workflows()),
    preparation?.seed?.base_commit, {reviewSources});
  need(same(revision?.document, {...p.document, template_id:workflowId, revision:1}), "workflow_conflict");
  await seed(road, p, true);
  await inputs(road, p, true, true);
  const grant = await authorized(road, p, request.actor);
  need(grant, "authorization_conflict");
  road.check();
  return resultOf(p, request.actor, null, grant);
}

export async function observeDalio(door, prepared, actor) {
  const entry = held.get(prepared);
  need(entry && entry.actor === actor, "preview_changed");
  const road = session(door, entry.p.projectId);
  await road.owner();
  return authorized(road, entry.p, actor, prepared.preview);
}

export async function authorizeDalio(door, prepared, actor) {
  const entry = held.get(prepared);
  need(entry && entry.actor === actor && typeof actor === "string" && actor.trim(), "preview_changed");
  const {p} = entry, road = session(door, p.projectId);
  await road.owner();
  const previous = await authorized(road, p, actor, prepared.preview);
  if (previous) return {phase:"authorized", runId:p.runId, authorization:previous};
  need(!entry.attempted && prepared.preview && Date.parse(prepared.preview.valid_until) > Date.now(), "preview_changed");
  need((await road.read(path.git()))?.git?.head?.commit === p.baseCommit, "source_changed");
  await seed(road, p, true);
  await inputs(road, p, true);
  // No new preview here. The server must accept exactly the one the operator just read.
  need(!entry.attempted && Date.parse(prepared.preview.valid_until) > Date.now(), "preview_changed");
  entry.attempted = true;
  let failure;
  try {
    const answer = await road.write("automationAuthorize", p.runId, {authorization_id:"grant-" + p.runId,
      authorized_by:actor, preview_digest:prepared.preview.preview_digest, terms:prepared.terms, supersedes:null});
    if (answer?.status !== "accepted") failure = new Error(answer?.code || "authorization_unknown");
  } catch (err) { failure = err; }
  const grant = await authorized(road, p, actor, prepared.preview);
  if (!grant) throw failure || new Error("authorization_unknown");
  return {phase:"authorized", runId:p.runId, authorization:grant};
}
