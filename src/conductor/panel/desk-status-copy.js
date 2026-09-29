"use strict";
// The strings that say each key of `desk-status.js`, English first and Russian second,
// like every other copy module of the panel: `studio-i18n.js` spreads this catalogue into
// the one table. One message per key and no message besides: the words the spec gives
// (5.2.1) stand here as it gives them. The only parameter is the queue position, a named
// value and never a joined string. No message uses a raw machine word.
export const DESK_STATUS_COPY = Object.freeze({
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
});
