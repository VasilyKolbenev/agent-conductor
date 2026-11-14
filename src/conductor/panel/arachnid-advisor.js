"use strict";
// A separate one-action review. This module never receives authority over a target cycle.
import {path} from "./desk-transport.js";
import {quotaOf} from "./desk-wizard-roles.js";
import {documentId} from "./desk-wizard-digest.js";
import {ADVICE_WORKFLOW} from "./desk-wizard-cycle.js";
import {grantAdvice, observeAdvice, prepareAdvice, recordAdviceChoice, requestFor,
  suggestionFrom} from "./desk-advice-run.js";

const MODEL = "gpt-6.1-sol";
const FLOW = "dalio-v6";
const ROLES = {"role-thinker": ["codex", "review"], "role-designer": ["codex", "review"],
  "role-diagnostician": ["grok-build", "review"], "role-implementer": ["codex", "dispatch"],
  "role-checker": ["codex", "review"]};
const RUN = /^advice-[0-9a-f]{20}$/;
const ACTOR = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const initial = () => ({phase: "idle", issue: null, advicePreview: null, proposal: null,
  runId: null, brief: "", sessionId: null, projectId: null, provider: null, model: null,
  actor: null, input: null, quota: quotaOf(null, "codex")});
const terminalErrors = ["answer_invalid", "run_conflict", "decision_conflict",
  "advice_unsuccessful", "advice_stopped", "advice_login_unavailable", "workflow_conflict"];

function check(value, reason) { if (!value) throw Error(reason); }
function code(error) {
  return /^[a-z_]{1,64}$/.test(error?.message) ? error.message : "store_error";
}
function scope(args) {
  check(args && /^[a-f0-9]{32}$/.test(args.projectId)
    && /^new\/[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(args.sessionId), "advice_unavailable");
  return {sessionId: args.sessionId, projectId: args.projectId};
}
function scopeKey(ref) {
  // Salt the durable identity without sending the project's activation nonce to the CLI.
  return JSON.stringify([ref.projectId, ref.sessionId]);
}
function admits(row, capability) {
  return row?.auth === "subscription" && row.offered === true && row.availability === "available"
    && ["boundary", "review_only"].includes(row.task_road) && row.controls?.includes(capability)
    && (capability !== "dispatch" || row.task_road === "boundary");
}
function material(sessionId, text, language, role_options) {
  const current_roles = Object.fromEntries(Object.entries(role_options)
    .map(([role, ids]) => [role, ids[0] || null]));
  return {source_session: sessionId, language, task: text, current_criterion: "", question: "",
    cycles: [FLOW],
    current_cycle: FLOW, current_revision: 6, depth: "balanced", current_roles, role_options};
}
function inputFor(args) {
  const {providers, language} = args.input || {};
  check(Array.isArray(providers) && ["en", "ru"].includes(language), "advice_unavailable");
  const codex = providers.find(row => row.provider_id === "codex");
  check(args.provider === "codex" && args.model === MODEL && admits(codex, "review")
    && codex.model_pin_supported === true, "advice_unavailable");
  check(typeof args.text === "string" && args.text.trim(), "advice_empty");
  const role_options = {};
  for (const [role, [id, capability]] of Object.entries(ROLES)) {
    const available = admits(providers.find(row => row.provider_id === id), capability);
    role_options[role] = available ? [id] : [];
  }
  return material(args.sessionId, args.text, language, role_options);
}

function originalMaterial(run) {
  const input = run?.records?.filter(r => r.record_type === "artifact"
    && r.record?.artifact_ref === "artifact-brief").map(r => r.record);
  check(RUN.test(run?.run?.run_id) && input?.length === 1 && !input[0].source_action_id
    && typeof input[0].content === "string"
    && input[0].content.length <= 32768 && input[0].run_id === run.run.run_id
    && input[0].media_type === "text/plain" && input[0].artifact_id ===
      documentId(run.run.run_id, "artifact-brief", "text/plain", input[0].content), "run_conflict");
  let stored;
  try { stored = JSON.parse(input[0].content); } catch { throw Error("run_conflict"); }
  check(JSON.stringify(stored) === input[0].content, "run_conflict");
  return stored;
}

function requestFrom(run, ref, stored = originalMaterial(run)) {
  const instances = run?.config?.instances;
  check(run?.run?.run_id === ref.runId && run.run.mode === "policy" && !run.warnings?.length
    && run.config?.workflow?.id === ADVICE_WORKFLOW && run.config.workflow.revision === 1
    && run.config.task?.id === ref.runId && run.config.task.work_scope === ref.runId
    && Array.isArray(instances) && instances.length === 1 && instances[0].adapter === "codex"
    && instances[0].id === "instance-advisor" && instances[0].model === MODEL, "run_conflict");
  check(stored && typeof stored.task === "string" && stored.task.trim()
    && stored.source_session === ref.sessionId && ["en", "ru"].includes(stored.language)
    && Object.keys(stored.role_options || {}).length === Object.keys(ROLES).length
    && Object.entries(ROLES).every(([role, [id]]) => {
      const ids = stored.role_options[role];
      return Array.isArray(ids) && (ids.length === 0 || (ids.length === 1 && ids[0] === id));
    }), "run_conflict");
  const safe = material(ref.sessionId, stored.task, stored.language, stored.role_options);
  const request = requestFor(scopeKey(ref), "codex", MODEL, safe);
  check(request.id === ref.runId && request.content === JSON.stringify(stored), "run_conflict");
  return request;
}

export function planningSession(run, projectId) {
  try {
    const stored = originalMaterial(run);
    const ref = {...scope({projectId, sessionId: stored.source_session}), runId: run.run.run_id};
    requestFrom(run, ref, stored);
    return ref.sessionId;
  } catch { return null; }
}

export function createArachnidAdvisor(door) {
  let current = initial(), request = null, content = null, epoch = 0, reading = false;
  function valid(at) {
    return at === epoch && door.valid(current.projectId, current.sessionId);
  }
  function change(values) {
    current = {...current, ...values};
    door.refresh();
  }
  function state() { return structuredClone(current); }
  function close() { epoch++; reading = false; request = content = null; current = initial(); }
  function guarded(at, ref) {
    const need = () => check(valid(at), "preview_changed");
    return {readJson: url => { need(); return door.readJson(url); },
      write: (target, subject, body) => {
        need();
        const operation = {flow: subject === ADVICE_WORKFLOW, tasks: body.task_id === ref.runId,
          runs: body.run_id === ref.runId, artifacts: subject === ref.runId,
          automationPreview: subject === ref.runId,
          automationAuthorize: subject === ref.runId && current.phase === "authorizing",
          decisions: subject === ref.runId && current.phase === "deciding"};
        check(operation[target] === true, "advice_unavailable");
        return door.write(target, subject, body);
      }};
  }
  function reference() {
    const {runId, projectId, sessionId} = current;
    return {runId, projectId, sessionId};
  }
  function show(af, at) {
    if (!valid(at)) return;
    const actor = af.actor || current.actor;
    if (af.phase === "result") {
      const proposal = suggestionFrom(af.content, JSON.parse(request.content));
      check([null, "approve", "reject"].includes(af.choice), "decision_conflict");
      content = af.content;
      const phase = {approve: "accepted", reject: "declined"}[af.choice] || "result";
      change({phase, proposal, actor, issue: null, advicePreview: null});
    } else if (af.phase === "preview") {
      change({phase: "preview", advicePreview: af.preview, issue: null});
    } else if (af.phase === "ready") {
      change({phase: "draft", issue: null, advicePreview: null});
    } else change({phase: "running", issue: null, advicePreview: null});
  }
  function failed(error, at) {
    if (!valid(at)) return;
    const issue = code(error);
    change({phase: terminalErrors.includes(issue) ? "failed" : "recover", issue,
      advicePreview: null});
  }
  function open(args) {
    try {
      const ref = scope(args);
      check(door.valid(ref.projectId, ref.sessionId), "advice_unavailable");
      const req = requestFor(scopeKey(ref), "codex", MODEL, inputFor(args));
      check(new TextEncoder().encode(req.content).length <= 32768, "input_too_large");
      if (request?.id === req.id) return state();
      close(); request = req;
      change({...ref, phase: "draft", runId: req.id, brief: args.text, provider: "codex",
        model: MODEL, input: JSON.parse(req.content)});
    } catch (error) { close(); change({phase: "failed", issue: code(error)}); }
    return state();
  }
  async function restore(ref) {
    if (ref?.runId === current.runId && ref?.sessionId === current.sessionId
        && ref?.projectId === current.projectId && (reading || request)) return state();
    close();
    const at = epoch;
    try {
      const ids = scope(ref);
      check(door.valid(ids.projectId, ids.sessionId) && RUN.test(ref.runId), "run_conflict");
      reading = true;
      change({...ids, phase: "recover", runId: ref.runId, provider: "codex", model: MODEL});
      const bound = guarded(at, ref);
      const run = await bound.readJson(path.run(ref.runId));
      if (!valid(at)) return state();
      request = requestFrom(run, ref);
      const input = JSON.parse(request.content);
      change({brief: input.task, input});
      show(await observeAdvice(bound, request), at);
    } catch (error) {
      if (at === epoch && !current.projectId) change({phase: "failed", issue: code(error)});
      else failed(error, at);
    } finally { if (at === epoch) reading = false; }
    return state();
  }
  async function quota(bound) {
    try { return quotaOf(await bound.readJson(path.quotas()), "codex"); }
    catch { return quotaOf(null, "codex"); }
  }
  async function prepare() {
    if (!valid(epoch) || !request
        || !["draft", "preview", "recover"].includes(current.phase)) return state();
    const at = ++epoch, ref = reference(), bound = guarded(at, ref), req = request;
    change({phase: "preparing", issue: null, advicePreview: null});
    try {
      const q = await quota(bound);
      const ru = JSON.parse(req.content).language === "ru";
      const result = await prepareAdvice(bound, req,
        ru ? "План Колоса" : "Kolos plan", ru ? "План Атласа" : "Atlas plan");
      if (!valid(at)) return state();
      door.saveReference(ref);
      if (!valid(at)) return state();
      change({quota: q}); show(result, at);
    } catch (error) { failed(error, at); }
    return state();
  }
  async function grant(actor) {
    if (!valid(epoch) || current.phase !== "preview" || !request) return state();
    if (!ACTOR.test(actor) || typeof actor !== "string") {
      change({issue: "actor_invalid"}); return state();
    }
    const at = ++epoch, ref = reference(), bound = guarded(at, ref), req = request;
    const preview = current.advicePreview;
    change({phase: "authorizing", actor, issue: null});
    try {
      const q = await quota(bound);
      if (!valid(at)) return state();
      if (q.kind === "percent" && q.remaining <= 0) {
        change({phase: "preview", issue: "quota_exhausted", quota: q}); return state();
      }
      change({quota: q});
      show(await grantAdvice(bound, req, preview, actor, () => valid(at)), at);
    } catch (error) { failed(error, at); }
    return state();
  }
  async function tick() {
    if (reading || !valid(epoch) || !["recover", "running"].includes(current.phase)) return state();
    if (!request) return restore(reference());
    const at = epoch, req = request, bound = guarded(at, reference());
    reading = true;
    try { show(await observeAdvice(bound, req), at); }
    catch (error) { failed(error, at); }
    finally { if (at === epoch) reading = false; }
    return state();
  }
  async function decide(action, actor = current.actor) {
    if (!valid(epoch) || current.phase !== "result" || !request) return state();
    if (!["approve", "reject"].includes(action) || typeof actor !== "string"
        || !ACTOR.test(actor)) {
      change({issue: "actor_invalid"}); return state();
    }
    const at = ++epoch, req = request, bound = guarded(at, reference());
    change({phase: "deciding", actor});
    try {
      await recordAdviceChoice(bound, req, content, actor, action, "", () => valid(at));
      show(await observeAdvice(bound, req), at);
    } catch (error) { failed(error, at); }
    return state();
  }
  return {state, open, restore, prepare, grant, tick, decide, close};
}
