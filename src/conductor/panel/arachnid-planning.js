"use strict";
import {path} from "./desk-transport.js";
import {createArachnidAdvisor, planningSession} from "./arachnid-advisor.js";
import {authorizeDalio, observeDalio, prepareDalio, restoreDalio} from "./arachnid-plan.js";
import {dalioOutline} from "./arachnid-plan-model.js";
import {renderPlanner} from "./arachnid-planner-view.js";

const phases = {idle: "idle", draft: "idle", preparing: "preparing", preview: "advice-preview",
  authorizing: "advising", running: "advising", recover: "blocked", result: "proposal",
  accepted: "proposal", deciding: "building", declined: "blocked", failed: "blocked"};
const model = "gpt-6.1-sol";

export function atlasPlanning(host, door) {
  let active = null;
  const actors = new Map();
  function valid(entry) {
    return active === entry && door.valid(entry.projectId, entry.sessionId, entry.reference);
  }
  function snapshot() {
    if (!active) { host.hidden = true; host.replaceChildren(); return; }
    const e = active, a = e.advisor.state(), p = e.prepared;
    const outline = a.proposal ? dalioOutline() : null;
    const roles = p?.roles || outline?.roles;
    const limits = p?.limits || outline?.limits;
    const plan = a.proposal ? {...a.proposal, adviceRunId: a.runId, roles,
      steps: limits.node_limits.map(step => {
        const role = roles.find(row => row.role === outline.stageRoles[step.node_id]);
        return {...step, role: role?.role, provider: role?.provider, checker: step.node_id === "do"
          ? roles.find(row => row.role === "role-checker")?.instance : null};
      })} : null;
    host.hidden = false;
    const view = {sessionId: e.sessionId, locale: e.locale, phase: e.phase || phases[a.phase],
      actor: e.actor, lead: "codex", model, brief: a.brief || e.brief, plan,
      advicePreview: a.advicePreview, mainPreview: p?.preview, terms: p?.terms || limits,
      quota: a.quota, input: a.input, advisorId: a.runId, baseCommit: p?.baseCommit,
      authorization: e.authorization, runId: p?.runId || a.runId, issue: e.issue || a.issue};
    const signature = JSON.stringify(view);
    if (signature === e.signature) return;
    e.signature = signature;
    renderPlanner(host, view, {
      actorChanged: value => { if (!e.working && valid(e)) {
        e.actor = value; actors.set(e.projectId, value); snapshot();
      } },
      authorizeAdvice: () => action(e, () => e.advisor.grant(e.actor)),
      reviewAdvice: () => action(e, () => e.advisor.state().runId ? e.advisor.prepare() :
        beginAdvice(e, e.brief)),
      prepareMain: () => action(e, () => materialize(e)),
      authorizeMain: () => action(e, () => launch(e)),
      refresh: () => action(e, () => observe(e)),
      openRun: () => {
        if (valid(e) && view.runId) door.openRun(view.runId, p?.taskId || a.runId);
      },
    });
  }
  async function observe(e) {
    if (e.prepared) {
      const grant = await observeDalio(mainDoor(e), e.prepared, e.actor);
      if (!valid(e)) return;
      e.authorization = grant;
      e.phase = grant ? "authorized" : e.launchAttempted ? "proposal" : "main-preview";
      return;
    }
    e.phase = null;
    await e.advisor.tick();
  }
  async function action(e, work) {
    if (!valid(e) || e.working) return;
    e.working = true; e.issue = null;
    try { await work(); }
    catch (error) {
      if (valid(e)) { e.issue = error.message || "store_error"; e.phase = "blocked"; }
    } finally { e.working = false; if (valid(e)) snapshot(); }
  }
  function mainDoor(e) {
    return {read: route => door.readJson(route),
      valid: () => valid(e),
      submit: (target, subject, body) => valid(e) ? door.write(target, subject, body) :
        Promise.resolve({status: "refused", code: "project_mismatch"})};
  }
  function mainRequest(e, a) {
    return {projectId: e.projectId, advisorId: a.runId, sessionId: e.sessionId,
      proposal: a.proposal, brief: a.brief, actor: e.actor, locale: a.input?.language || e.locale};
  }
  async function materialize(e) {
    const advisor = e.advisor;
    if (!["result","accepted"].includes(advisor.state().phase)) return;
    e.phase = "building"; snapshot();
    if (advisor.state().phase === "result") await advisor.decide("approve", e.actor);
    const a = advisor.state();
    if (!valid(e) || a.phase !== "accepted") { e.phase = null; return; }
    const p = await prepareDalio(mainDoor(e), mainRequest(e, a));
    if (!valid(e)) return;
    e.prepared = p; e.launchAttempted = false;
    e.phase = p.phase === "authorized" ? "authorized" : "main-preview";
    e.authorization = p.authorization || null;
  }
  async function launch(e) {
    if (!e.prepared || e.phase !== "main-preview") return;
    e.launchAttempted = true;
    const result = await authorizeDalio(mainDoor(e), e.prepared, e.actor);
    if (!valid(e)) return;
    e.authorization = result.authorization; e.phase = "authorized";
  }
  function make(ctx) {
    const e = {...ctx, prepared: null, authorization: null, working: false,
      actor: actors.get(ctx.projectId) ?? "local-operator", phase: null, issue: null};
    e.advisor = createArachnidAdvisor({
      readJson: door.readJson, write: mainDoor(e).submit,
      valid: (id, session) => valid(e) && id === e.projectId && session === e.sessionId,
      saveReference: ref => {
        if (valid(e)) { door.saveReference(ref); e.reference = ref?.runId || null; }
      },
      refresh: () => { if (valid(e)) snapshot(); },
    });
    return e;
  }
  function sync(ctx) {
    if (!ctx || !active || active.projectId !== ctx.projectId || active.sessionId !== ctx.sessionId
        || active.reference !== ctx.reference) {
      const old = active; active = null; old?.advisor.close();
      if (ctx) {
        active = make(ctx);
        const e = active;
        if (ctx.reference) void action(e, async () => {
          const a = await e.advisor.restore({projectId: e.projectId,
            sessionId: e.sessionId, runId: ctx.reference});
          if (!valid(e)) return;
          if (a.actor) e.actor = a.actor;
          if (a.phase === "accepted") {
            e.phase = "building"; snapshot();
            const recorded = await restoreDalio(mainDoor(e), mainRequest(e, a));
            if (!valid(e)) return;
            e.prepared = recorded; e.authorization = recorded?.authorization || null;
            e.phase = recorded ? "authorized" : null;
          }
        });
      }
    }
    if (active) active.locale = ctx.locale;
    snapshot();
  }
  async function beginAdvice(e, brief) {
    const catalog = await door.readJson(path.workflows());
    if (!valid(e)) return;
    e.phase = null;
    await e.advisor.open({projectId: e.projectId, sessionId: e.sessionId, text: brief,
      provider: "codex", model, input: {language: e.locale, providers: catalog.providers}});
    if (e.advisor.state().phase === "draft") await e.advisor.prepare();
  }
  function message(sessionId, text) {
    const e = active;
    if (!e || !valid(e) || e.sessionId !== sessionId) return false;
    if (e.working || ["authorizing","running","recover"].includes(e.advisor.state().phase)
        || e.phase === "authorized") {
      e.issue = "plan_busy"; snapshot(); return true;
    }
    const a = e.advisor.state();
    const brief = a.proposal?.question && ["result","accepted"].includes(a.phase) ?
      [a.brief, a.proposal.question, text].join("\n\n") : text;
    e.brief = brief; e.prepared = null; e.authorization = null; e.phase = "preparing";
    e.advisor.close();
    door.saveReference(null); e.reference = null; snapshot();
    void action(e, () => beginAdvice(e, brief));
    return true;
  }
  function tick() {
    const e = active;
    if (e && !e.working && valid(e) && ["running","recover"].includes(e.advisor.state().phase)) {
      void action(e, () => e.advisor.tick());
    }
  }
  return {sync, message, tick, planningSession};
}
