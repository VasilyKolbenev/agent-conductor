"use strict";
// The desk's own strings, English first and Russian second, like every other copy module of
// the panel: `studio-i18n.js` spreads this catalogue into the one table. The words of the
// page itself (its title, its note, its link and the name of each region) live here and are
// written into `desk.html` by `data-i18n` and `data-i18n-label`; the page carries no other
// word than the product's own name. Where a message carries a number or a name it is a
// named parameter, never a joined string, and no message depends on a plural form.
export const DESK_COPY = Object.freeze({
  // -- the page ------------------------------------------------------------------------
  "desk.title": ["December Command — Desk", "December Command — Стол"],
  "desk.note": [
    "The desk is being built: the rail and the scene are live; the feed, the summary and the "
      + "console stay empty until their modules land.",
    "Стол в разработке: рельс и сцена работают; лента, выжимка и пульт остаются пустыми, "
      + "пока не появятся их модули."],
  "desk.classic": ["Classic panel", "Прежняя панель"],
  // -- the names of the five regions, as a screen reader hears them --------------------
  "desk.rail.label": ["Tasks", "Задачи"],
  "desk.scene.label": ["Scene", "Сцена"],
  "desk.feed.label": ["Progress", "Ход работы"],
  "desk.summary.label": ["Summary", "Выжимка"],
  "desk.pult.label": ["Your console", "Ваш пульт"],
  // -- the rail ------------------------------------------------------------------------
  "desk.rail.none": ["This project has no tasks yet.", "В проекте пока нет задач."],
  "desk.rail.unreadable": ["Unreadable task", "Задача не читается"],
  // -- the scene -----------------------------------------------------------------------
  "desk.scene.choose": ["Choose a task to see its newest run.",
    "Выберите задачу, чтобы увидеть её новейший запуск."],
  "desk.scene.no_run": ["This task has no run yet.", "У этой задачи ещё нет запусков."],
  "desk.scene.unknown_run": [
    "The newest run of this task cannot be established: a run record cannot be read.",
    "Новейший запуск задачи не установлен: одна из записей запусков не читается."],
  "desk.scene.task_unreadable": ["This task cannot be read, so there is no run to show.",
    "Задача не читается, показывать нечего."],
  "desk.scene.subject": ["{task} · run {run}", "{task} · запуск {run}"],
});
