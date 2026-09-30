"use strict";
// The words of the console's queue controls, English first and Russian second, like every other
// copy module of the panel: `studio-i18n.js` spreads this catalogue into the one table. They are
// the names of the buttons a person presses on the queue block, the sentences of the dialogs a
// press opens, the reason a slot gives for being stopped or unavailable, and the sentence a press
// leaves under the block; the block's own lines are `desk-copy.js` and the status words
// `desk-status-copy.js`. A refusal is said in the words of the refusal vocabulary (`error.<code>`),
// never here, and a message carries a name or a number as a named parameter, never a joined string.
export const DESK_PULT_COPY = Object.freeze({
  // -- the controls of an entry -----------------------------------------------------------
  "desk_pult.up": ["Move up", "Выше"],
  "desk_pult.down": ["Move down", "Ниже"],
  "desk_pult.withdraw": ["Remove from the queue", "Убрать из очереди"],
  "desk_pult.cancel": ["Cancel", "Отмена"],
  // -- what a write that could not be confirmed leaves under the block ----------------------
  "desk_pult.unconfirmed": [
    "The change could not be confirmed. This is the queue the server holds.",
    "Изменение не удалось подтвердить. Здесь — очередь, как её хранит сервер."],
  // -- freeing the slot of a holder that stopped (spec 4.4.8) -----------------------------
  "desk_pult.release": ["Free the slot", "Освободить слот"],
  "desk_pult.release_need_name": ["Give your name above to free the slot.",
    "Укажите имя выше, чтобы освободить слот."],
  "desk_pult.release_text": [
    "{task} is stopped and holds the slot. Choose what to do with its permission: nothing is "
      + "chosen for you.",
    "{task} остановился и держит слот. Выберите, что сделать с его разрешением: за вас ничего "
      + "не выбрано."],
  "desk_pult.release_pause": ["Pause", "Приостановить"],
  "desk_pult.release_pause_note": ["It can be continued while the permission has not expired.",
    "Продолжить можно, пока разрешение не истекло."],
  "desk_pult.release_revoke": ["Revoke the permission", "Отозвать разрешение"],
  "desk_pult.release_revoke_note": [
    "It cannot be undone; next comes a new permission or “Rework”.",
    "Необратимо; дальше — новое разрешение или «Доработать»."],
  "desk_pult.release_feedback": [
    "Nothing to correct here: continuing would bring back the same stop.",
    "Исправлять нечем — продолжение вернёт ту же остановку."],
  "desk_pult.skip": ["Skip ahead", "Пропустить вперёд"],
  "desk_pult.skip_need_name": ["Give your name above to skip ahead.",
    "Укажите имя выше, чтобы пропустить вперёд."],
  "desk_pult.skip_text": [
    "{task} waits for a decision and holds the slot. Skip ahead pauses it, queues its continuation last and lets the first entry start.",
    "{task} ждёт решения и держит слот. «Пропустить вперёд» приостановит его, поставит продолжение в конец очереди и даст стартовать первой записи."],
  "desk_pult.skip_window": ["Its permission window keeps running: it ends at {time}.",
    "Окно его разрешения продолжает идти: оно кончается в {time}."],
  "desk_pult.skip_confirm": ["Pause it and queue its continuation",
    "Приостановить и поставить продолжение в очередь"],
  "desk_pult.skip_partial": ["{task} is paused, but its continuation was not queued. {reason}",
    "{task} приостановлен, но его продолжение не поставлено в очередь. {reason}"],
  "desk_pult.confirm": ["Confirm", "Подтвердить"],
  "desk_pult.confirm_need_name": ["Give your name above to confirm this entry.",
    "Укажите имя выше, чтобы подтвердить эту запись."],
  "desk_pult.confirm_text": ["Review the new terms for {task} before confirming its place in the queue.",
    "Проверьте новые условия для {task}, прежде чем подтвердить его место в очереди."],
  "desk_pult.confirm_actions": ["At most {count} actions", "Не более {count} действий"],
  "desk_pult.confirm_time": ["At most {seconds} seconds of task work",
    "Не более {seconds} секунд работы над задачей"],
  "desk_pult.confirm_window": ["Permission lasts {seconds} seconds",
    "Разрешение действует {seconds} секунд"],
  "desk_pult.confirm_press": ["Confirm these terms", "Подтвердить эти условия"],
  // -- why a slot is stopped or unavailable, after the state (spec 4.4.6) -------------------
  "desk_pult.why_expired": ["the permission expired", "разрешение истекло"],
  "desk_pult.why_feedback_required": ["a rejected check needs your review",
    "отклонённая проверка ждёт вашего просмотра"],
  "desk_pult.why_unknown_action": ["an action has an unknown result",
    "результат действия неизвестен"],
  "desk_pult.why_ambiguous_actions": ["several actions are unsettled",
    "несколько действий не завершены"],
  "desk_pult.why_admission_refused": ["the next action did not pass the checks",
    "следующее действие не прошло проверки допуска"],
  "desk_pult.why_stalled": ["the run needs attention", "запуск требует внимания"],
  "desk_pult.why_plan_stalled": ["the plan has no eligible next step",
    "в плане нет допустимого шага"],
  "desk_pult.why_seed_blocked": ["the working folder could not be seeded",
    "рабочую папку не удалось засеять"],
  "desk_pult.why_owner_required": ["the project has no owner", "у проекта нет владельца"],
  "desk_pult.why_server_stopping": ["the server is stopping", "сервер останавливается"],
  "desk_pult.why_project_not_active": ["the project is not active", "проект не активен"],
});
