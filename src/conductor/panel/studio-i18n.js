"use strict";
import {RUN_STEP_COPY} from "./studio-runstep-copy.js";
import {PARTICIPANT_COPY} from "./studio-participant-copy.js";
import {RUN_DOCS_COPY} from "./studio-run-docs-copy.js";
import {RUNS_COPY} from "./studio-runs-copy.js";
import {RUNFORM_COPY} from "./studio-runform-copy.js";
import {VIEW_COPY} from "./studio-view-copy.js";
import {WORKFLOW_DETAIL_COPY} from "./studio-workflow-detail-copy.js";
import {WORKFLOW_COPY} from "./studio-workflow-copy.js";
import {FEEDBACK_COPY} from "./studio-feedback-copy.js";
import {AGENTS_COPY} from "./studio-agents-copy.js";
import {AUTOMATION_COPY} from "./studio-automation-copy.js";
import {NOTICE_COPY} from "./studio-notice-copy.js";
// Interface messages only. User text, identifiers and durable records are data.
// Each entry carries both locales; parameters are exact named string values.
const TEXT = {
  "bridge.no_outcome": ["No outcome recorded", "Исход ещё не записан"],
  "scene.attention_unconfirmed": ["Attention unconfirmed", "Участие не подтверждено"],
  "scene.trace": ["Trace", "Трасса"],
  "scene.orbit": ["Orbit", "Орбита"],
  "scene.lenses": ["Run view", "Представление запуска"],
  "scene.scroll_team": ["All {count} participants. Select a name to locate it; scroll inside the Trace for the full plan.", "Все участники: {count}. Выберите имя, чтобы найти его; прокручивайте Трассу для просмотра всего плана."],
  "scene.team": ["Run team", "Команда запуска"],
  "scene.closed": ["Route closed", "Ветка закрыта"],
  "scene.awaiting_result": ["Awaiting result", "Ждёт результата"],
  "scene.settled": ["Settled", "Завершён"],
  "scene.runnable": ["Ready in the plan", "Готов по плану"],
  "scene.spent": ["Attempts exhausted", "Попытки исчерпаны"],
  "scene.blocked": ["Waiting", "Ожидание"],
  "scene.unassigned": ["In this run; no steps", "В запуске без шагов"],
  "scene.needs_decision": ["Decision needed", "Нужно решение"],
  "scene.decision_unknown": ["Decision unknown", "Решение неизвестно"],
  "scene.decision_satisfied": ["Approved", "Одобрено"],
  "scene.decision_failed": ["Rejected", "Отклонено"],
  "scene.decision_changes_requested": ["Changes requested", "Нужны изменения"],
  "scene.decision_waived": ["Waived", "Пропущено по решению"],
  "scene.run_ended": ["Run ended", "Запуск окончен"],
  "scene.answered_current_lap": ["This pass is answered", "На этот проход дан ответ"],
  "scene.branch_closed": ["Branch closed", "Ветка закрыта"],
  "scene.road_not_open": ["Road not open yet", "Дорога ещё не открыта"],
  "scene.outcome_cancelled": ["Cancelled", "Отменено"],
  "scene.outcome_failed": ["Failed", "Ошибка"],
  "scene.outcome_rejected": ["Rejected", "Отклонено"],
  "scene.outcome_succeeded": ["Succeeded", "Успешно"],
  "scene.outcome_unknown": ["Outcome unknown", "Исход неизвестен"],
  "scene.outcome_verification_failed": ["Verification failed", "Проверка не пройдена"],
  "scene.duty_both": ["Performs and verifies", "Выполняет и проверяет"],
  "scene.duty_perform": ["Performs", "Выполняет"],
  "scene.duty_verify": ["Verifies", "Проверяет"],
  "scene.duty_none": ["Participant", "Участник"],
  "scene.bound_reached": ["Pass limit reached", "Предел проходов исчерпан"],
  "scene.pass": ["Pass {pass} of {bound}", "Проход {pass} из {bound}"],
  "scene.select": ["Inspect", "Подробнее"],
  "scene.selected": ["Selected", "Выбрано"],
  "scene.gate": ["Human decision", "Решение человека"],
  "scene.loop": ["Bounded return", "Ограниченный возврат"],
  "scene.back_to": ["Returns to {step}", "Возврат к шагу {step}"],
  "scene.previous_answer": ["The standing answer belongs to an earlier pass.", "Действующий ответ относится к прежнему проходу."],
  "scene.open_decisions": ["Open decisions", "Открыть решения"],
  "scene.no_plan": ["This run has no frozen plan.", "У этого запуска нет замороженного плана."],
  "scene.no_instances": ["This run binds no participants.", "В этом запуске нет привязанных участников."],
  "scene.evidence_count": ["{count} evidence references", "Ссылок на доказательства: {count}"],
  "scene.legend": ["Plan routes · filled mark means settled, not verified", "Связи плана · заполненный знак означает завершение, а не проверку"],
  "scene.disconnected": ["Connection lost; human attention is unconfirmed.", "Связь прервана; необходимость участия человека не подтверждена."],
  "condition.on_approved": ["if approved", "если одобрено"],
  "condition.on_rejected": ["if rejected", "если отклонено"],
  "condition.on_changes_requested": ["if changes requested", "если нужны изменения"],
  "condition.on_waived": ["if waived", "если пропущено"],
  "condition.on_succeeded": ["if succeeded", "при успехе"],
  "condition.on_failed": ["if failed", "при неудаче"],
  "condition.on_bound_reached": ["if limit reached", "если достигнут предел"],
  "condition.on_bound_remaining": ["while passes remain", "пока остались проходы"],
  "bridge.title": ["Your controls", "Ваш пульт"],
  "bridge.attention": ["Human attention", "Участие человека"],
  "bridge.required": ["You are needed", "Нужно ваше участие"],
  "bridge.not_required": ["No action is needed", "Ваше действие не требуется"],
  "bridge.unknown": ["Needs are not established", "Необходимость участия неизвестна"],
  "bridge.as_of": ["As of {at}", "По состоянию на {at}"],
  "bridge.checked": ["What was checked", "Что проверено"],
  "bridge.gate_decision": ["Decisions needed: {count}", "Нужны решения: {count}"],
  "bridge.confirmation": ["Steps awaiting confirmation: {count}", "Шаги ждут подтверждения: {count}"],
  "bridge.input_document": ["Steps awaiting input documents: {count}", "Шаги ждут входные документы: {count}"],
  "bridge.reconcile": ["Reconcile outside this window: {count}", "Сверка состояния вне окна: {count}"],
  "bridge.attempt_bound": ["Steps with exhausted attempts: {count}", "Шаги с исчерпанными попытками: {count}"],
  "bridge.run_ended": ["The run is ended.", "Запуск окончен."],
  "bridge.queue": ["Attention queue", "Очередь внимания"],
  "bridge.queue_empty": ["No confirmed requests for your attention.", "Подтверждённых запросов на ваше участие нет."],
  "bridge.more": ["{count} more runs", "Ещё запусков: {count}"],
  "bridge.open_agents": ["Open usage and agents", "Открыть лимиты и участников"],
  "bridge.usage": ["Usage now", "Ресурсы сейчас"],
  "bridge.region": ["Run controls and usage", "Пульт запуска и ресурсы"],
  "bridge.usage_missing": ["No current readings.", "Текущих показаний нет."],
  "bridge.usage_stale": ["Stale reading", "Устаревшие данные"],
  "bridge.usage_deferred": ["Update deferred: a step is running (last try {at})", "Обновление отложено: идёт шаг (последняя попытка {at})"],
  "bridge.deferred_short": ["update deferred", "обновление отложено"],
  "bridge.window_reset": ["Window reset since this reading", "Окно сброшено после этого показания"],
  "bridge.usage_error": ["Source unavailable", "Источник недоступен"],
  "bridge.usage_unknown": ["Account unknown; shown separately", "Аккаунт неизвестен; показано отдельно"],
  "bridge.balance": ["Balance {amount} {currency}", "Баланс {amount} {currency}"],
  "bridge.remaining": ["Remaining {value}%", "Осталось {value}%"],
  "bridge.reset": ["Reset {at}", "Сброс {at}"],
  "bridge.no_reset": ["Reset not applicable", "Сброс не применяется"],
  "bridge.no_runs": ["No runs yet", "Запусков ещё нет"],
  "bridge.catalog_unknown": ["Newest run cannot be established", "Новейший запуск не установлен"],
  "bridge.task_all": ["All tasks", "Все задачи"],
  "bridge.details": ["Run details", "Подробности запуска"],
  "bridge.choose_run": ["Choose a run explicitly; the catalog is incomplete.", "Выберите запуск явно: каталог прочитан не полностью."],
  "bridge.new_run": ["Create a new run", "Создать новый запуск"],

  "app.title": ["December — Workflow Studio", "December — Студия процессов"],
  "app.name": ["Workflow Studio", "Студия процессов"],
  "nav.label": ["Studio screens", "Экраны студии"],
  "nav.overview": ["Overview", "Обзор"],
  "nav.workflow": ["Workflow", "Процесс"],
  "nav.runs": ["Runs", "Запуски"],
  "nav.decisions": ["Decisions", "Решения"],
  "nav.agents": ["Agents", "Участники"],
  "settings.label": ["Appearance and language", "Тема и язык"],
  "settings.language": ["Language", "Язык"],
  "settings.theme": ["Theme", "Тема"],
  "settings.light": ["Light", "Светлая"],
  "settings.dark": ["Dark", "Тёмная"],
  "shell.classic": ["Map, findings, feed and handoffs — classic panel", "Карта, замечания, события и передачи работы — прежняя панель"],
  "shell.overview": ["This screen answers what the project is, whether it is ready to run, what is blocked, and what needs you.", "Здесь видно, что представляет собой проект, готов ли он к запуску, что заблокировано и где нужно ваше участие."],
  "shell.workflow": ["A workflow names roles and steps. It never names a provider, a model or a run — a run binds those when it starts.", "Процесс задаёт роли и шаги. Провайдеры и модели связываются с ними при создании запуска."],
  "shell.runs": ["About runs", "О запусках"],
  "shell.verification": ["A process that exits 0 has finished, which is not the same as having been verified. Both words are shown.", "Код выхода 0 означает завершение процесса. Проверка результата — отдельный факт. Здесь показаны оба."],
  "shell.decisions": ["A decision is a durable receipt. This screen says why one is needed, what each choice causes, and what it unblocks.", "Решение сохраняется в журнале. Здесь видно, зачем оно нужно, что означает каждый выбор и какие шаги он открывает."],
  "shell.agents": ["A participant binds one instance to one configured provider. Providers are operator-written and read at startup.", "Каждый участник связан с одним настроенным провайдером. Настройки провайдеров задаются оператором и читаются при запуске."],
  "connection.open": ["Connected. Live changes reach this window.", "Подключено. Изменения поступают в это окно."],
  "connection.connecting": ["Connecting to this project's live stream.", "Подключение к событиям проекта."],
  "connection.closed": ["Connection lost. What is on screen is the last thing that was read; nothing here updates and nothing may be written until it is back.", "Связь потеряна. На экране последние прочитанные данные. Обновление и запись недоступны до восстановления связи."],
  "phase.empty": ["Nothing has been read yet.", "Данные ещё не прочитаны."],
  "phase.loading": ["Reading.", "Чтение данных."],
  "phase.ready": ["Read.", "Данные прочитаны."],
  "phase.stale": ["Shown from an earlier read; a newer one has not landed.", "Показаны прежние данные; новое чтение ещё не завершено."],
  "phase.refused": ["This read was refused. Nothing below is newer than the refusal.", "В чтении отказано. Данные ниже не обновлялись после отказа."],
  "phase.failed": ["This read failed. Nothing below is newer than the failure.", "Чтение не удалось. Данные ниже не обновлялись после ошибки."],
  "phase.disconnected": ["The live connection is down, so nothing here updates.", "Связь прервана; данные не обновляются."],
  "primary.overview": ["Edit the workflow", "Изменить процесс"],
  "primary.workflow": ["Save draft", "Сохранить черновик"],
  "primary.runs": ["Read runs again", "Обновить запуски"],
  "primary.decisions": ["Read this run again", "Обновить запуск"],
  "primary.agents": ["Read the roster again", "Обновить участников"],
  "save.no_draft": ["There is no drawing to save.", "Нет черновика для сохранения."],
  "save.copy_first": ["There is no drawing to save. Edit as new draft copies the published revision into one you can change.", "Нет черновика для сохранения. Создайте новый черновик из опубликованной версии, чтобы изменить её."],
  "save.unread": ["This workflow has not been read since the connection came back, so nothing may be written to it yet.", "После восстановления связи процесс ещё не прочитан. Запись пока недоступна."],
  "save.pending": ["This draft is being saved. Wait for its answer before saving again.", "Черновик сохраняется. Дождитесь ответа, прежде чем сохранять снова."],
  "task.label": ["Task", "Задача"],
  "task.section": ["Project tasks", "Задачи проекта"],
  "task.all": ["All tasks · choose one for a new run", "Все задачи · выберите задачу для нового запуска"],
  "task.unreadable": ["Unreadable task", "Задача не читается"],
  "task.unavailable": ["{id} · not available", "{id} · недоступна"],
  "task.refresh": ["Read tasks again", "Обновить задачи"],
  "task.name": ["Task name", "Название задачи"],
  "task.new": ["New task", "Новая задача"],
  "task.create": ["Create task", "Создать задачу"],
  "task.creating": ["Creating task…", "Создание задачи…"],
  "task.history": ["Task creation history", "История создания задач"],
  "task.unreadable_notice": ["This task cannot be read; opening a run is unavailable.", "Задача не читается; создание запуска недоступно."],
  "task.writing": ["Sending creation request…", "Отправка запроса на создание…"],
  "task.accepted": ["Created; stored record has not yet been read.", "Создана; сохранённая запись ещё не прочитана."],
  "task.read": ["Stored task read back.", "Сохранённая задача прочитана."],
  "task.refused": ["Creation request was refused.", "В создании задачи отказано."],
  "task.unknown": ["Outcome unknown. Read tasks again; an unchanged retry uses the same request.", "Результат неизвестен. Обновите задачи; повтор без изменений использует тот же запрос."],
};

export const LOCALES = Object.freeze(["en", "ru"]);
export const MESSAGES = Object.freeze(Object.fromEntries(Object.entries({...TEXT, ...AUTOMATION_COPY, ...AGENTS_COPY, ...WORKFLOW_COPY, ...WORKFLOW_DETAIL_COPY, ...VIEW_COPY, ...RUNFORM_COPY, ...RUNS_COPY, ...RUN_DOCS_COPY, ...PARTICIPANT_COPY, ...RUN_STEP_COPY, ...FEEDBACK_COPY, ...NOTICE_COPY})
  .map(([key, values]) => [key, Object.freeze({en: values[0], ru: values[1]})])));

function parameters(text) {
  return [...new Set([...text.matchAll(/\{([a-z_]+)\}/g)].map((row) => row[1]))].sort();
}

export function validateMessages(catalog) {
  return catalog !== null && typeof catalog === "object" && Object.keys(catalog).length > 0
    && Object.values(catalog).every((row) => row && typeof row === "object"
    && Object.keys(row).sort().join(",") === "en,ru"
    && LOCALES.every((locale) => typeof row[locale] === "string" && row[locale].length > 0)
    && parameters(row.en).join(",") === parameters(row.ru).join(","));
}

export function message(locale, key, params = {}) {
  if (!LOCALES.includes(locale) || !Object.hasOwn(MESSAGES, key)) {
    throw new Error("Unknown interface locale or message key");
  }
  const text = MESSAGES[key][locale], expected = parameters(text);
  if (!params || Object.getPrototypeOf(params) !== Object.prototype
      || Object.keys(params).sort().join(",") !== expected.join(",")
      || expected.some((name) => typeof params[name] !== "string")) {
    throw new Error("Interface message parameters do not match their key");
  }
  return text.replace(/\{([a-z_]+)\}/g, (_match, name) => params[name]);
}

export function localize(state, key, params) {
  return message(state.locale || "en", key, params);
}

//: A stored notice, drawn in the reader's language when it is drawn: a string is data and
//: stands as written, `{key, params}` is a message, and a list is its parts joined by a space.
//: A parameter may itself be a notice, so a word inside a sentence switches with it.
export function noticeText(state, notice) {
  if (typeof notice === "string") return notice;
  if (Array.isArray(notice)) return notice.map((part) => noticeText(state, part)).filter(Boolean).join(" ");
  if (!notice || typeof notice.key !== "string") return "";
  const params = Object.fromEntries(Object.entries(notice.params || {}).map(([name, value]) =>
    [name, typeof value === "string" ? value : noticeText(state, value)]));
  return localize(state, notice.key, params);
}

//: Whether a stored notice says this message, alone or as one of its parts.
export function noticeHas(notice, key) {
  return Array.isArray(notice) ? notice.some((part) => noticeHas(part, key)) : notice?.key === key;
}
