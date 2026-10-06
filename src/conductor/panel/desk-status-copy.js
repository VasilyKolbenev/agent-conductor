"use strict";
// The strings that say each key of `desk-status.js`, English first and Russian second,
// like every other copy module of the panel: `studio-i18n.js` spreads this catalogue into
// the one table. Four closed families and no string besides: the status of a task's row
// (one per key of `STATUS_KEYS`), the word of each reason a person is asked to look
// (`attention_<reason>`, one per reason of `ATTENTION_REASONS`), the phrases of a time (a wait
// since a moment, a wait noticed at one, a snapshot from one), and the reason a queue record
// gives (`entry_<code>`, spec 4.4.6). The words the spec gives (5.2.1, 4.1.9) stand here as it
// gives them; the entry reasons the spec leaves to the desk are plain sentences.
//
// A message takes at most one named value: the queue position of a `queued` row, or the short
// text of a time (`desk-time.js` says it, so a caller never joins a string). No message uses
// a raw machine word.
export const DESK_STATUS_COPY = Object.freeze({
  // -- the word of a task's row ---------------------------------------------------------
  "desk_status.task_unreadable": ["Record cannot be read", "Запись не читается"],
  "desk_status.not_started": ["Not started", "Не запущена"],
  "desk_status.run_unreadable": ["Record cannot be read", "Запись не читается"],
  "desk_status.waiting_you": ["Waiting for your decision", "Ждёт вашего решения"],
  "desk_status.queue_confirmation": ["Waiting for your confirmation",
    "Ждёт вашего подтверждения"],
  "desk_status.queue_blocked": ["Queued · cannot start", "В очереди · не может начаться"],
  "desk_status.queued": ["Queued · #{position}", "В очереди · {position}-я"],
  "desk_status.queued_inactive": ["Queued · starts once the project is active",
    "В очереди · начнётся после активации"],
  "desk_status.state_unknown": ["State unknown", "Состояние неизвестно"],
  "desk_status.running": ["Running", "Идёт"],
  "desk_status.checkpoint_inactive": [
    "At a checkpoint · the run belongs to the active project",
    "На контрольной точке · запуск — у активного проекта"],
  "desk_status.checkpoint": ["At a checkpoint · needs to be continued",
    "На контрольной точке · нужно продолжить"],
  "desk_status.owner_missing": ["No project owner", "Нет владельца проекта"],
  "desk_status.stalled": ["Run stalled", "Запуск остановился"],
  "desk_status.expired": ["Permission expired", "Разрешение истекло"],
  "desk_status.paused": ["Paused", "На паузе"],
  "desk_status.revoked": ["Permission revoked", "Разрешение отозвано"],
  "desk_status.outcome_succeeded": ["Succeeded", "Успешно"],
  "desk_status.outcome_verification_failed": ["Verification failed", "Проверка не пройдена"],
  "desk_status.outcome_failed": ["Failed", "Ошибка"],
  "desk_status.outcome_unknown": ["Outcome unknown", "Исход неизвестен"],
  "desk_status.outcome_rejected": ["Rejected", "Отклонено"],
  "desk_status.outcome_cancelled": ["Cancelled", "Отменено"],
  "desk_status.ended": ["Ended without a result", "Завершён без результата"],
  "desk_status.no_outcome": ["No result yet", "Результата пока нет"],
  // -- the reasons a person is asked to look (spec 4.1.9) ---------------------------------
  "desk_status.attention_gate_decision": ["Gate decision", "Решение на гейте"],
  "desk_status.attention_confirmation": ["Confirm the step", "Подтвердите шаг"],
  "desk_status.attention_input_document": ["A document is needed", "Нужен документ"],
  "desk_status.attention_reconcile": ["State needs reconciling outside the window",
    "Нужна сверка состояния вне окна"],
  "desk_status.attention_attempt_bound": ["The step ran out of attempts",
    "Шаг исчерпал попытки"],
  "desk_status.attention_restart_required": ["Continue after the restart",
    "Продолжить после перезапуска"],
  "desk_status.attention_stalled": ["Run stalled", "Запуск остановился"],
  "desk_status.attention_expired": ["Permission expired", "Разрешение истекло"],
  "desk_status.attention_queue_confirmation": ["Waiting for your confirmation",
    "Ждёт вашего подтверждения"],
  "desk_status.attention_slot_stuck": ["Slot busy · free the slot in the desk",
    "Слот занят · Освободить слот в столе"],
  // The one word of this table that is not the spec's: a review ruling changed it, because a project
  // that needs recovery does not always need a restart of the OS.
  "desk_status.attention_recovery_required": ["Project needs recovery",
    "Проект требует восстановления"],
  "desk_status.attention_login_recovery_required": ["Login needs recovery",
    "Вход требует восстановления"],
  // -- the phrases of a time ---------------------------------------------------------------
  "desk_status.since_waiting": ["waiting since {time}", "ждёт с {time}"],
  "desk_status.since_observed": ["noticed at {time}", "замечено в {time}"],
  "desk_status.since_observed_unknown": ["noticed · time not given",
    "замечено · время не указано"],
  "desk_status.snapshot": ["snapshot from {time}", "снимок от {time}"],
  "desk_status.snapshot_unknown": ["snapshot · time not given", "снимок · время не указано"],
  // -- the reason a task-queue record gives (spec 4.4.6) -----------------------------------
  "desk_status.entry_behind": ["another entry is ahead", "впереди другая запись"],
  "desk_status.entry_slot_busy": ["the slot is busy", "слот занят"],
  "desk_status.entry_slot_unavailable": ["the slot is unavailable", "слот недоступен"],
  "desk_status.entry_project_not_active": ["the project is not active", "проект не активен"],
  "desk_status.entry_terms_changed": ["the terms changed", "условия изменились"],
  "desk_status.entry_grant_expired": ["the permission expired", "разрешение истекло"],
  "desk_status.entry_grant_changed": ["the permission changed", "разрешение изменилось"],
  "desk_status.entry_preview_refused": ["the preview was refused", "предпросмотр отклонён"],
  "desk_status.entry_server_restarted": ["the server restarted", "сервер перезапускался"],
  "desk_status.entry_run_unreadable": ["the run record cannot be read",
    "запись запуска не читается"],
  "desk_status.entry_receipt_conflict": [
    "the queue and the journal disagree · remove it from the queue",
    "записи очереди и журнала расходятся · уберите из очереди"],
});
