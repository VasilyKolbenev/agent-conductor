"use strict";
import {sceneOf} from "./studio-scene-model.js";
import {digestOf} from "./desk-summary-model.js";
import {patchStep} from "./arachnid-orbit.js";
import {localize, MESSAGES} from "./studio-i18n.js";

const words = {
  unreadable: ["Run information is unavailable", "Данные запуска недоступны"],
  unknown: ["The outcome is unclear", "Исход пока неизвестен"],
  waiting: ["Waiting for {name}", "Ожидается результат от {name}"],
  gate: ["Your decision is needed", "Требуется ваше решение"],
  review: ["Review {name}", "Рассмотреть: {name}"],
  viewGate: ["Waiting for a decision on {name}", "Ожидается решение: {name}"],
  stalled: ["The run has stopped", "Запуск остановлен"],
  checkerRejected: ["The checker rejected the result.", "Проверяющий отклонил результат."],
  permission: ["Waiting for your permission", "Ожидается ваше разрешение"],
  limits: ["Review run limits", "Посмотреть условия запуска"],
  applying: ["Recording your decision…", "Записывается ваше решение…"],
  uncertain: ["Your decision has no matching receipt yet", "Запись вашего решения не подтверждена"],
  refused: ["The decision was refused", "Запрос на запись решения отклонён"],
  refresh: ["Check the run", "Проверить состояние запуска"],
  result: ["Result accepted", "Результат принят"],
  complete: ["Run complete", "Запуск завершён"],
  showResult: ["View Do result", "Посмотреть результат Do"],
  ready: ["Next in the plan: {name}", "Следующий шаг по плану: {name}"],
  recorded: ["Permission recorded", "Разрешение записано"],
  expired: ["Permission expired", "Срок разрешения истёк"],
  revoked: ["Permission revoked", "Разрешение отозвано"],
  exhausted: ["The run budget is exhausted", "Бюджет запуска исчерпан"],
  paused: ["The run is paused", "Запуск приостановлен"],
  restart_required: ["The run needs an explicit restart", "Нужен явный перезапуск"],
  preparing: ["Reading run limits…", "Читаются условия запуска…"],
  blocked: ["Waiting for the next step", "Ожидается следующий шаг"],
  close: ["Close review", "Закрыть карточку"],
};

export function nextText(locale, key, name = "") {
  return words[key][locale === "ru" ? 1 : 0].replace("{name}", () => name);
}

// The runtime records both of these verdicts even when no actionable findings were saved.
// Other verification failures, including an unavailable checker, do not establish a rejection.
const checkerRejections = new Set([
  "the independent checker rejected the doer's result",
  "the independent checker rejected the doer's result, but the typed feedback protocol refused " +
    "its findings, so no correction can carry them",
]);

function feedbackReason(ctx, scene, grant) {
  const records = ctx.detail.records;
  const request = records.findLast(row => row.record_type === "action_request")?.record;
  if (!request || !grant || request.run_id !== ctx.runId
      || request.run_authorization_id !== grant.authorization_id
      || request.run_authorization_digest !== grant.authorization_digest) return null;
  const result = records.find(row => row.record_type === "action_result"
    && row.record.action_id === request.action_id && row.record.attempt_id === request.attempt_id
    && row.record.run_id === ctx.runId && row.record.instance_id === request.instance_id)?.record;
  const step = scene.steps.find(s => s.nodeId === request.node_id);
  if (!result || !step || step.outcome !== result.outcome || result.outcome === "succeeded")
    return null;
  const why = step.verifierId && result.outcome === "verification_failed"
    && checkerRejections.has(result.detail) ? nextText(ctx.locale, "checkerRejected")
    : localize(ctx, "scene.outcome_" + result.outcome);
  return step.title + " · " + why;
}

function stopped(ctx, scene, held) {
  if (held?.runId === ctx.runId && held.phase === "ready" && held.view?.state === "stalled") {
    const reason = "automation." + held.view.reason_code;
    if (held.view.reason_code === "feedback_required") return {kind: "stalled",
      why: feedbackReason(ctx, scene, held.view.authorization) || localize(ctx, reason)};
    if (Object.hasOwn(MESSAGES, reason)) return {kind: "stalled", why: localize(ctx, reason)};
  }
  const failed = scene.steps.find(s => s.kind === "task" && (s.word === "spent" ||
    s.outcome && s.outcome !== "succeeded"));
  const reason = "scene." + failed?.word;
  const why = failed && Object.hasOwn(MESSAGES, reason)
    ? failed.title + " · " + localize(ctx, reason) : localize(ctx, "automation.plan_stalled");
  return {kind: "stalled", why};
}

// Run facts are taken from the same admitted read as the orbit. Permission is a separate read.
export function nextOf(ctx, gates, held) {
  const scene = sceneOf(ctx.detail);
  if (!scene) return {kind: "unreadable"};
  if (held?.request && held.runId === ctx.runId) return {kind: "unknown", button: "refresh"};
  const member = scene.steps.find(step => step.word === "awaiting_result");
  if (!scene.ending.ended && member) {
    const owner = scene.participants.find(p => p.instanceId === member.ownerId);
    return {kind: "waiting", name: [owner?.adapter || member.ownerId, member.title]
      .filter(Boolean).join(" · ")};
  }
  if (ctx.detail.graph.situation?.state === "unknown") return {kind: "unknown"};
  const gate = gates.find(row => row.needs_answer && !row.ended && row.decision !== "unknown"
    && ["first", "supersede"].includes(row.answerable));
  if (gate) return ctx.mode === "active"
    ? {kind: "gate", button: "review", gate, name: gate.title || gate.node_id}
    : {kind: "viewGate", name: gate.title || gate.node_id};
  const digest = digestOf(ctx.detail);
  if (digest?.closed || scene.ending.plan_word === "complete") {
    const patches = scene.steps.filter(patchStep), stages = scene.steps.filter(s =>
      s.kind === "task" && s.node.stage === "do");
    const result = patches.length === 1 ? patches[0] : stages.length === 1 ? stages[0] : null;
    return {kind: digest?.closed ? "result" : "complete",
      button: result ? "showResult" : null, nodeId: result?.nodeId};
  }
  if (scene.ending.ended) return stopped(ctx, scene, held);
  if (held?.runId === ctx.runId && ctx.mode === "active") {
    if (held.phase === "failed") return {kind: "unreadable", button: "refresh"};
    if (held.phase !== "ready") return {kind: "preparing"};
    const view = held.view;
    if (view?.authorization) {
      if (view.state === "stalled") return stopped(ctx, scene, held);
      if (["expired", "revoked", "paused", "restart_required"].includes(view.state))
        return {kind: view.state};
      if (!view.remaining_actions || !view.remaining_task_seconds) return {kind: "exhausted"};
      return {kind: "recorded"};
    }
    if (held.view?.owner_present && held.view.reason_code === "authorization_required")
      return {kind: "permission", button: "limits"};
  }
  const runnable = scene.steps.find(s => s.kind === "task" && s.word === "runnable");
  return runnable ? {kind: "ready", name: runnable.title} : {kind: "blocked"};
}
