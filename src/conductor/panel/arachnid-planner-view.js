"use strict";
import {element} from "./command-view.js";

const labels = {
  idle: ["Plan with Codex", "Подготовить план с Codex"],
  description: ["Describe your task. Codex can plan the Dalio cycle with Grok for diagnosis.",
    "Опишите задачу. Codex может подготовить цикл Далио с Grok на этапе диагностики."],
  preparing: ["Preparing the advisor request…", "Готовится запрос к советнику…"],
  "advice-preview": ["Review the request to Codex", "Запрос к Codex"],
  advising: ["Waiting for the Codex review", "Ожидается ответ Codex"],
  proposal: ["Codex proposal", "Предложение Codex"],
  building: ["Preparing the Dalio run…", "Готовится запуск Далио…"],
  "main-preview": ["Review the Dalio run", "Условия запуска Далио"],
  authorized: ["Authorization recorded", "Разрешение записано"],
  blocked: ["Planning needs attention", "Для подготовки плана нужна проверка"],
  actor: ["Operator", "Кто разрешает"],
  subscription: ["Subscription", "Подписка"],
  reviewAdvice: ["Review advisor request", "Посмотреть запрос советнику"],
  authorizeAdvice: ["Authorize one Codex review", "Разрешить один запрос к Codex"],
  prepareMain: ["Accept plan and review run", "Принять план и посмотреть запуск"],
  authorizeMain: ["Authorize this Dalio run", "Разрешить этот запуск Далио"],
  refresh: ["Read current state", "Перечитать состояние"],
  openRun: ["Open run", "Открыть запуск"],
  expire: ["This preview has expired.", "Срок просмотра истёк."],
  renew: ["Refresh preview", "Обновить просмотр"],
  missing: ["No matching preview is available.", "Нет подтверждённого просмотра для этого запуска."],
  terms: ["Exact reviewed terms", "Точные просмотренные условия"],
  max_actions: ["Actions", "Действия"],
  max_action_seconds: ["Seconds per action", "Секунд на действие"],
  max_total_task_seconds: ["Total reserved seconds", "Общий резерв, секунд"],
  duration_seconds: ["Grant duration, seconds", "Срок разрешения, секунд"],
  valid: ["Preview valid until", "Просмотр действует до"],
  criterion: ["Success criterion", "Критерий успеха"],
  question: ["Clarification from Codex", "Уточнение от Codex"],
  depth: ["Review depth", "Глубина проверки"],
  steps: ["Steps and harnesses", "Шаги и харнессы"],
  role: ["Role", "Роль"],
  checker: ["Independent checker", "Независимый проверяющий"],
  seconds: ["seconds", "секунд"],
  attempts: ["attempts", "попыток"],
  evidence: ["Advisor run", "Запуск советника"],
  proposed: ["Proposed limits", "Предлагаемые пределы"],
  quota: ["Subscription allowance", "Остаток подписки"],
  balance: ["Balance reported; percentage unavailable", "Доступен баланс, процент неизвестен"],
  material: ["Material sent to Codex", "Материал для Codex"],
  adviseScope: ["One read-only review of the supplied text. The Dalio cycle has its own authorization.",
    "Одна проверка переданного текста в режиме чтения. Для цикла Далио потребуется отдельное разрешение."],
  git: ["Base Git commit", "Исходный Git-коммит"],
  sourcePaths: ["Task files to share with Codex during Do", "Файлы задачи для Codex на шаге Do"],
  answer: ["Reply in this chat to clarify the task.", "Ответьте в этом чате, чтобы уточнить задачу."],
  plan_busy: ["An operation is already in progress. Read its state before changing the task.",
    "Операция уже выполняется. Перечитайте её состояние, прежде чем менять задачу."],
  advice_unavailable: ["The selected subscription Codex is unavailable in this project.",
    "Выбранный Codex по подписке недоступен в этом проекте."],
  provider_unavailable: ["A required harness or role is unavailable.", "Нужный харнесс или роль недоступны."],
  preview_stale: ["The reviewed terms have changed.", "Просмотренные условия изменились."],
  preview_changed: ["The project or preview changed.", "Проект или предпросмотр изменился."],
  actor_invalid: ["Enter an operator name to authorize.", "Для разрешения укажите имя оператора."],
  answer_invalid: ["Codex returned an invalid plan.", "Ответ Codex не прошёл проверку плана."],
  advice_unsuccessful: ["Codex did not complete the review.", "Codex не завершил проверку."],
  advice_login_unavailable: ["Codex subscription login is unavailable. Sign in to its project profile.",
    "Вход Codex по подписке недоступен. Войдите в профиль харнесса для проекта."],
  advice_stopped: ["The advisor run stopped.", "Запуск советника остановился."],
  store_error: ["The project state could not be confirmed.", "Не удалось подтвердить состояние проекта."],
  git_unavailable: ["The project Git revision is unavailable.", "Ревизия Git проекта недоступна."],
  project_mismatch: ["The open project has changed.", "Изменился открытый проект."],
  disconnected: ["Connection lost. Read the recorded state before proceeding.",
    "Связь с сервером потеряна. Перечитайте состояние перед продолжением."],
  view: ["Open an active project to request a subscription plan.",
    "Откройте активный проект, чтобы запросить план по подписке."],
  subscription_unavailable: ["The subscription harness is unavailable.", "Харнесс по подписке недоступен."],
  not_authenticated: ["Subscription sign-in is required.", "Требуется вход по подписке."],
  quota_unknown: ["Subscription quota is unknown.", "Остаток по подписке неизвестен."],
  quota_exhausted: ["Subscription quota is exhausted.", "Лимит подписки исчерпан."],
  unknown: ["The outcome is not confirmed. Read the existing run.", "Исход не подтверждён. Перечитайте существующий запуск."],
};
const copy = (view, key) => labels[key]?.[view.locale === "ru" ? 1 : 0] || key;
const txt = value => typeof value === "string" && value.trim().length > 0;
const pos = value => Number.isSafeInteger(value) && value > 0;
const budgets = ["max_actions", "max_action_seconds", "max_total_task_seconds", "duration_seconds"];
const phases = new Set(["idle", "preparing", "advice-preview", "advising", "proposal",
  "building", "main-preview", "authorized", "blocked"]);
const handles = new WeakMap();

function frame(host, view) {
  let ui = handles.get(host);
  if (ui?.sessionId === view.sessionId && ui.title.parentElement === host) return ui;
  const title = element("h2");
  const body = element("div", {className: "planner-body"});
  const input = element("input", {type: "text", autocomplete: "off"});
  const name = element("span");
  const actor = element("label", {className: "planner-actor"}, [name, input]);
  const actions = element("div", {className: "planner-actions"});
  host.replaceChildren(title, body, actor, actions);
  ui = {sessionId: view.sessionId, title, body, name, input, actor, actions, handlers: null};
  input.addEventListener("input", () => ui.handlers.actorChanged(input.value));
  handles.set(host, ui);
  return ui;
}
function action(ui, view, name, label = name, grant = false, preview = null) {
  const b = element("button", {type: "button", "data-planner-action": name, text: copy(view, label)});
  b.disabled = grant && !ui.input.value.trim();
  b.addEventListener("click", () => {
    if (!b.isConnected || b.disabled) return;
    if (preview && Date.parse(preview.valid_until) <= Date.now()) {
      renderPlanner(ui.title.parentElement, view, ui.handlers);
      return;
    }
    ui.handlers[name]();
  });
  ui.actions.append(b);
}
function line(body, label, value) {
  if (value == null || value === "") return;
  body.append(element("div", {className: "planner-line"}, [
    element("span", {text: label}), element("strong", {text: String(value)}),
  ]));
}
function timing(view, limit) {
  const parts = [];
  if (pos(limit.timeout_seconds)) parts.push(limit.timeout_seconds + " " + copy(view, "seconds"));
  if (pos(limit.max_attempts)) parts.push(limit.max_attempts + " " + copy(view, "attempts"));
  return parts.join(" · ");
}
function plan(body, view) {
  const p = view.plan;
  if (!p) return;
  for (const key of ["criterion", "depth", "question"]) line(body, copy(view, key), p[key]);
  if (p.question) body.append(element("p", {text: copy(view, "answer")}));
  if (p.adviceRunId) line(body, copy(view, "evidence"), p.adviceRunId);
  if (Array.isArray(p.steps) && p.steps.length) {
    const list = element("ol", {className: "planner-steps", "aria-label": copy(view, "steps")});
    for (const step of p.steps) {
      const row = element("li", {}, [element("strong", {text: step.node_id}),
        element("span", {text: [step.role, step.provider, timing(view, step)].filter(Boolean).join(" · ")})]);
      if (txt(step.checker)) row.append(element("small", {text: copy(view, "checker") + " · " + step.checker}));
      list.append(row);
    }
    body.append(list);
  }
  const roles = view.roles || p.roles;
  if (Array.isArray(roles)) {
    for (const row of roles) line(body, row.role, [row.instance, row.provider, row.model].filter(Boolean).join(" · "));
  } else if (roles && typeof roles === "object") {
    for (const [role, provider] of Object.entries(roles)) if (txt(provider)) line(body, role, provider);
  }
}
function bounds(body, view, terms) {
  const box = element("div", {className: "planner-bounds"});
  for (const name of budgets) line(box, copy(view, name), terms[name]);
  body.append(box);
}
function issue(ui, view) {
  const value = view.issue;
  const code = typeof value === "string" ? value : value?.code;
  if (!code) return;
  const text = txt(value?.text) ? value.text : labels[code] ? copy(view, code)
    : copy(view, "store_error") + " (" + code + ")";
  ui.body.append(element("p", {className: "planner-issue", role: "status", text}));
}
function advisorInput(ui, view) {
  line(ui.body, copy(view, "subscription"), [view.lead, view.model].filter(Boolean).join(" · "));
  ui.body.append(element("p", {text: copy(view, "adviseScope")}));
  if (view.brief) ui.body.append(element("blockquote", {text: view.brief}));
  const q = view.quota;
  const reading = q?.known && Number.isFinite(q.remaining) ? q.remaining + "%"
    : copy(view, q?.known && q.kind === "balance" ? "balance" : "quota_unknown");
  line(ui.body, copy(view, "quota"), reading);
  if (view.input) ui.body.append(element("details", {className: "planner-exact"}, [
    element("summary", {text: copy(view, "material")}),
    element("pre", {text: txt(view.input) ? view.input : JSON.stringify(view.input, null, 2)}),
  ]));
}
function preview(ui, view, main) {
  const value = main ? view.mainPreview : view.advicePreview;
  const terms = value?.terms;
  const expectedRun = main ? view.runId : view.advisorId;
  const valid = terms && budgets.every(key => pos(terms[key])) && Array.isArray(terms.node_limits)
    && /^sha256:[0-9a-f]{64}$/.test(value.preview_digest) && Number.isFinite(Date.parse(value.valid_until))
    && !(expectedRun && terms.run_id && terms.run_id !== expectedRun);
  if (!valid) {
    ui.body.append(element("p", {text: copy(view, "missing")}));
    action(ui, view, main ? "prepareMain" : "reviewAdvice", "renew"); return;
  }
  if (!main) advisorInput(ui, view);
  else {
    line(ui.body, copy(view, "git"), view.baseCommit || view.plan?.baseCommit);
    if (view.sourcePaths?.length) line(ui.body, copy(view, "sourcePaths"), view.sourcePaths.join(", "));
  }
  if (terms.run_id) line(ui.body, main ? copy(view, "openRun") : copy(view, "evidence"), terms.run_id);
  bounds(ui.body, view, terms);
  for (const row of terms.node_limits) line(ui.body, row.node_id, timing(view, row));
  line(ui.body, copy(view, "valid"), value.valid_until);
  ui.body.append(element("details", {className: "planner-exact", "data-preview-digest": value.preview_digest}, [
    element("summary", {text: copy(view, "terms")}),
    element("code", {text: value.preview_digest}),
    element("pre", {text: JSON.stringify(terms, null, 2)}),
  ]));
  if (Date.parse(value.valid_until) <= Date.now()) {
    ui.body.append(element("p", {text: copy(view, "expire")}));
    action(ui, view, main ? "prepareMain" : "reviewAdvice", "renew"); return;
  }
  if (!main && (view.issue === "quota_exhausted" || view.quota?.known && view.quota.remaining === 0)) {
    action(ui, view, "reviewAdvice", "renew"); return;
  }
  ui.actor.hidden = false;
  action(ui, view, main ? "authorizeMain" : "authorizeAdvice",
    main ? "authorizeMain" : "authorizeAdvice", true, value);
}

export function renderPlanner(host, view, handlers) {
  if (!view?.sessionId || !phases.has(view.phase)) {
    host.hidden = true; host.replaceChildren(); handles.delete(host); return;
  }
  host.hidden = false;
  const ui = frame(host, view);
  const expanded = ui.body.querySelector("details[data-preview-digest][open]")?.dataset.previewDigest;
  const focus = host.ownerDocument.activeElement?.dataset.plannerAction;
  ui.handlers = handlers;
  ui.title.textContent = copy(view, view.phase);
  ui.body.replaceChildren(); ui.actions.replaceChildren();
  ui.actor.hidden = true;
  ui.input.readOnly = view.phase === "main-preview";
  ui.name.textContent = copy(view, "actor");
  const actor = typeof view.actor === "string" ? view.actor : "";
  if (ui.input.value !== actor) ui.input.value = actor;
  host.dataset.plannerPhase = view.phase;
  issue(ui, view);
  if (view.phase === "idle") {
    ui.body.append(element("p", {text: copy(view, "description")}));
    if (view.brief) action(ui, view, "reviewAdvice");
  } else if (view.phase === "advice-preview") {
    preview(ui, view, false);
  } else if (view.phase === "advising") {
    action(ui, view, "refresh");
  } else if (view.phase === "proposal") {
    plan(ui.body, view);
    if (view.terms && budgets.every(key => pos(view.terms[key]))) {
      ui.body.append(element("h3", {text: copy(view, "proposed")}));
      bounds(ui.body, view, view.terms);
    }
    if (view.plan && !view.plan.question) action(ui, view, "prepareMain");
  } else if (view.phase === "main-preview") {
    plan(ui.body, view); preview(ui, view, true);
  } else if (view.phase === "authorized") {
    line(ui.body, copy(view, "openRun"), view.runId);
    if (view.runId) action(ui, view, "openRun");
  } else if (view.phase === "blocked") {
    action(ui, view, "refresh");
    if (view.runId || view.advisorId) action(ui, view, "openRun");
  }
  const details = ui.body.querySelector("details[data-preview-digest]");
  if (expanded && details?.dataset.previewDigest === expanded) details.open = true;
  if (focus) [...ui.actions.children].find(b => b.dataset.plannerAction === focus)?.focus({preventScroll: true});
}
