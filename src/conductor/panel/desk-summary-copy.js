"use strict";
// The words of the summary "Выжимка" and its panel "кто что делал и сделал", English first and
// Russian second, like every other copy module of the panel: `studio-i18n.js` spreads this
// catalogue into the one table. A counter is a label and a number that stand side by side, never a
// sentence with a plural in it, so no message depends on a plural form. The words of a task's
// status are `desk-status-copy.js`, of a duty `scene.duty_*`, of a pass `scene.pass`: not said
// again here.
export const SUMMARY_COPY = Object.freeze({
  // -- the four counters, and the fifth that appears only when a record cannot be read --------
  "summary.label_working": ["In progress", "В работе"],
  "summary.label_waiting": ["Waiting for you", "Ждут вас"],
  "summary.label_closed": ["Closed", "Закрыто"],
  "summary.label_left": ["Left", "Осталось"],
  "summary.label_unclear": ["Unclear", "Не установлено"],
  // -- what each counter counts, honestly (the hint of a counter and the panel's explanation) ---
  "summary.caption_working": [
    "A run has begun and is not over, and nothing in it asks you: it goes, or it is paused or "
      + "parked.",
    "Запуск начат и не окончен, и ничего в нём не ждёт вас: он идёт, стоит на паузе или ждёт "
      + "своей очереди."],
  "summary.caption_waiting": [
    "The task is in your “waiting for you” list: a step, a confirmation, a resume or a stopped "
      + "grant.",
    "Задача в списке «Ждут вас»: шаг, подтверждение, возобновление или остановившееся "
      + "разрешение."],
  "summary.caption_closed": ["The newest run was accepted at its final gate.",
    "Последний запуск принят на финальном гейте."],
  "summary.caption_left": [
    "Work remains: nothing began yet, the run waits in the queue, or its last result is not "
      + "accepted.",
    "Работа осталась: ничего не начато, запуск ждёт очереди или его последний результат не "
      + "принят."],
  "summary.caption_unclear": [
    "The records cannot say: a task or run cannot be read, or its state or outcome is unknown.",
    "Записи не позволяют сказать: задача или запуск не читаются, либо их состояние или исход "
      + "неизвестны."],
  // -- what is going on now, in the run on the scene ---------------------------------------------
  "summary.now": ["now in {run}: {what}", "сейчас в {run}: {what}"],
  "summary.now_idle": ["nothing is running and nothing asks you",
    "ничего не идёт и ничего не ждёт вас"],
  "summary.now_asking": ["waiting for your decision: {steps}", "ждёт вашего решения: {steps}"],
  // -- the bar's toggle and the panel --------------------------------------------------------------
  "summary.more": ["Details ▴", "Подробнее ▴"],
  "summary.less": ["Collapse ▾", "Свернуть ▾"],
  "summary.panel": ["Who did what, and what was done", "Кто что делал и сделал"],
  "summary.how": ["How it is counted", "Как это считается"],
  "summary.tasks": ["Project tasks", "Задачи проекта"],
  "summary.people": ["Participants · run {run}", "Участники · запуск {run}"],
  "summary.no_run": ["Choose a task to see who works on its run.",
    "Выберите задачу, чтобы увидеть участников её запуска."],
  // -- what the records say of a task and of a participant ---------------------------------------
  "summary.did": ["Did: {who}", "Сделал: {who}"],
  "summary.checked": ["Checked: {who}", "Проверил: {who}"],
  "summary.accepted": ["Accepted: {who}", "Принял: {who}"],
  "summary.actions": ["Actions: {count}", "Действий: {count}"],
  "summary.checks": ["Checks: {count}", "Проверок: {count}"],
  "summary.documents": ["Documents: {refs}", "Документы: {refs}"],
  "summary.last": ["Last:", "Последнее:"],
});
