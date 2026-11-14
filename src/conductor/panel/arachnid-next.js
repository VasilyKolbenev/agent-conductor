"use strict";
import {element} from "./command-view.js";
import {isId} from "./studio-model.js";
import {decisionRows} from "./studio-runread.js";
import {decisionWriters} from "./studio-runwrite.js";
import {automationEligible} from "./studio-automation-model.js";
import {automationFlow} from "./studio-automation-flow.js";
import {mountAutomation} from "./studio-automation.js";
import {mountDecisionCard} from "./studio-people.js";
import {focusTarget, restoreFocus} from "./studio-focus.js";
import {nextOf, nextText} from "./arachnid-next-view.js";

const gateKey = row => JSON.stringify([row.run_id, row.node_id, row.gate_id,
  row.answers, row.standing, row.answerable]);
const freshDraft = () => ({key: null, action: "approve", actor: "", reason: ""});
function sameRefs(actual, expected) {
  return Array.isArray(actual) && actual.length === expected.length
    && actual.every((ref, index) => ref === expected[index]);
}
function recorded(detail, body) {
  return detail.records.some(({record_type, record}) => record_type === "decision"
    && record.run_id === detail.run.run_id && sameRefs(record.scope_refs, body.scope_refs)
    && sameRefs(record.evidence_refs, body.evidence_refs)
    && ["receipt_id", "gate_id", "actor", "action", "reason", "supersedes"]
      .every(key => record[key] === body[key]));
}

export function createNextAction(host, door) {
  const label = element("p", {className: "next-label"});
  const button = element("button", {type: "button", className: "next-action"});
  const surface = element("div", {id: "nextSurface", className: "next-surface", hidden: ""});
  const card = element("div");
  const dismiss = element("button", {type: "button", className: "next-close"});
  surface.append(dismiss, card);
  host.replaceChildren(element("div", {className: "next-summary"}, [label, button]), surface);
  const receipts = new Map();
  let ctx = null, selected = "", rows = [], opened = null, draft = freshDraft(), last = [];
  let flow = makeFlow(), flowProject = null, reading = null, disposed = false;
  let generation = 0, formIntent = null;
  function permitted() {
    return !disposed && ctx?.ready && ctx.detail?.run?.run_id === ctx.runId &&
      ctx.detail.task?.id === ctx.taskId && ctx.detail.config?.task?.id === ctx.taskId &&
      door.valid(ctx.projectId, ctx.runId, ctx.taskId);
  }
  function canWrite() { return permitted() && isId(ctx.projectId) && ctx.mode === "active"; }
  function refresh(run) {
    if (permitted() && ctx.runId === run) return door.refreshRun(run);
  }
  function makeFlow() {
    return automationFlow({selected: () => ctx?.runId, ready: canWrite, changed: render,
      read: door.readAutomation, stop: door.stop, id: door.id, refreshRun: refresh,
      write: async (target, run, body, accept, refuse) => {
        if (!canWrite() || ctx.runId !== run || formIntent !== selected ||
            !["automationPreview", "automationAuthorize"].includes(target)) {
          refuse({status: "refused", code: "read_late"}); return;
        }
        const key = selected;
        let result;
        try { result = await door.submit(target, run, body); }
        catch { result = {status: "unknown"}; }
        if (key !== selected || !canWrite()) return;
        if (result.status === "accepted") accept(result); else refuse(result);
      }});
  }
  function show() {
    if (!permitted()) return {kind: "unreadable"};
    const request = receipts.get(selected);
    if (request && !recorded(ctx.detail, request.body)) {
      return {kind: request.kind, button: request.kind === "applying" ? null : "refresh"};
    }
    return nextOf(ctx, rows, flow.snapshot());
  }
  function choose() {
    if (!ctx || !permitted()) return;
    const next = show();
    if (next.button === "refresh") {
      const request = receipts.get(selected);
      if (request?.kind === "refused") request.checked = ctx.detail;
      // Applying that new run read also refreshes its automation projection.
      refresh(ctx.runId);
      return;
    }
    if (next.button === "showResult") { door.openStep(next.nodeId); return; }
    if (!next.button || !canWrite()) return;
    if (opened !== null) { close(); return; }
    if (next.kind === "gate") {
      opened = gateKey(next.gate);
      draft = {...freshDraft(), key: next.gate.run_id + "/" + next.gate.gate_id};
    } else if (next.kind === "permission") opened = "permission";
    else return;
    render();
    const control = card.querySelector('input[name="actor"], [data-focus="automation:run:actor"]');
    (control || dismiss).focus({preventScroll: false});
  }
  function close() {
    if (opened === null) return;
    const focused = surface.contains(host.ownerDocument.activeElement);
    opened = null; draft = freshDraft(); render();
    if (focused && !button.hidden) button.focus({preventScroll: true});
  }

  function writeGate(row, version) {
    if (version !== generation || !canWrite() || receipts.has(selected) ||
        opened !== gateKey(row) || show().kind !== "gate") return;
    const current = rows.find(item => item.needs_answer && gateKey(item) === opened);
    if (!current) return;
    const run = ctx.runId, key = selected, offered = opened;
    const writer = decisionWriters({isId, draft: () => draft,
      chosenRun: () => key === selected && canWrite() ? run : null,
      dispatch() {}, refreshRun: refresh,
      write: async (target, subject, body, success) => {
        if (!canWrite() || key !== selected || offered !== opened || receipts.has(key)
            || target !== "decisions" || run !== subject || body.gate_id !== current.gate_id
            || body.supersedes !== current.standing) return;
        const request = {body, kind: "applying"};
        receipts.set(key, request); render();
        let answer;
        try { answer = await door.submit(target, subject, body); }
        catch { answer = {status: "unknown"}; }
        if (disposed || receipts.get(key) !== request) return;
        request.kind = answer.status === "refused" ? "refused" : "uncertain";
        if (key !== selected || !canWrite()) return;
        if (answer.status === "accepted") success(answer);
        else refresh(run);
        render();
      }});
    writer.submitDecision(current);
  }

  function drawCard(next, held) {
    generation++;
    const version = generation;
    const state = {locale: ctx.locale, connection: "open", runs: {
      selectedId: ctx.runId, phase: "ready", detail: ctx.detail},
      decisions: {list: rows, phase: "ready", draft}};
    if (next.kind === "gate") {
      mountDecisionCard(card, state, {
        editDecision: patch => {
          if (version !== generation || !canWrite() || opened !== gateKey(next.gate)) return;
          draft = {...draft, ...patch}; render();
        },
        submitDecision: row => writeGate(row, version),
      });
      return;
    }
    card.replaceChildren();
    const actions = {};
    for (const name of ["edit", "preview", "toggleLimits", "authorize", "refresh"]) {
      actions[name] = (...args) => {
        if (version !== generation || opened !== "permission" || !canWrite()) return;
        formIntent = selected;
        try { return flow[name](...args); }
        finally { formIntent = null; }
      };
    }
    // This surface only exists before a grant. Known and uncertain grants have read-only status.
    mountAutomation(card, state, held, actions, () => {});
  }
  function render() {
    if (disposed) return;
    host.hidden = !ctx?.runId;
    if (host.hidden) { surface.hidden = true; card.replaceChildren(); last = []; return; }
    const next = show(), held = flow.snapshot();
    const text = key => nextText(ctx.locale, key, next.name);
    const key = next.gate ? gateKey(next.gate) : next.kind;
    const previouslyInside = surface.contains(host.ownerDocument.activeElement);
    if (opened !== key) { opened = null; draft = freshDraft(); }
    const visible = Boolean(opened);
    host.dataset.nextKind = next.kind;
    label.textContent = next.why ? text(next.kind) + " · " + next.why : text(next.kind);
    button.hidden = !next.button;
    if (next.button) button.textContent = text(next.button);
    const expands = next.kind === "gate" || next.kind === "permission";
    if (expands) {
      button.setAttribute("aria-expanded", String(visible));
      button.setAttribute("aria-controls", surface.id);
    } else {
      button.removeAttribute("aria-expanded"); button.removeAttribute("aria-controls");
    }
    surface.hidden = !visible;
    if (!visible) {
      if (card.childElementCount) { generation++; card.replaceChildren(); }
      if (previouslyInside && !button.hidden) button.focus({preventScroll: true});
      last = []; return;
    }
    const signature = [key, ctx.detail, ctx.locale, draft, next.gate ? null : held];
    if (signature.every((value, index) => value === last[index])) return;
    last = signature;
    const focused = previouslyInside ? focusTarget() : null;
    surface.dataset.subject = selected + "/" + key;
    dismiss.textContent = text("close");
    drawCard(next, held);
    restoreFocus(surface, focused);
  }

  function sync(next) {
    if (disposed) return;
    const key = next?.runId ? JSON.stringify([next.projectId, next.taskId, next.runId]) : "";
    const changed = key !== selected, wasReady = ctx?.ready;
    if (changed) {
      flow.clear();
      if (next?.projectId && flowProject !== next.projectId) {
        flow = makeFlow(); flowProject = next.projectId;
      }
      selected = key; opened = null; draft = freshDraft(); last = []; reading = null;
    }
    ctx = next;
    rows = permitted() ? decisionRows(ctx.detail) : [];
    const request = receipts.get(key);
    if (request && permitted() && (recorded(ctx.detail, request.body)
        || request.checked && ctx.detail !== request.checked)) receipts.delete(key);
    if (!canWrite()) {
      if (wasReady && !changed) flow.disconnect();
      reading = null;
    } else if (reading !== ctx.detail) {
      reading = ctx.detail;
      if (automationEligible(reading)) flow.sync(reading);
    }
    render();
  }

  button.addEventListener("click", choose);
  dismiss.addEventListener("click", close);
  function dispose() {
    disposed = true; flow.clear(); receipts.clear(); host.replaceChildren(); ctx = null;
  }
  return {sync, close, dispose};
}
