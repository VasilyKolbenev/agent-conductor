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
    "The desk is being built: the rail, the scene and the console are live; the feed and the "
      + "summary stay empty until their modules land.",
    "Стол в разработке: рельс, сцена и пульт работают; лента и выжимка остаются пустыми, "
      + "пока не появятся их модули."],
  "desk.classic": ["Classic panel", "Прежняя панель"],
  // -- the terminal state: an address that claims another project ------------------------
  "desk.foreign": [
    "This desk is open for another project. Reload the page to continue.",
    "Стол открыт для другого проекта. Перезагрузите страницу, чтобы продолжить."],
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
  // -- the console: the name of the person at this page (spec 5.2, the actor) ---------------
  "desk.pult.actor": ["You: {name}", "Вы: {name}"],
  "desk.pult.actor_none": ["You: name not given", "Вы: имя не указано"],
  "desk.pult.actor_change": ["change", "изменить"],
  "desk.pult.actor_set": ["set", "указать"],
  "desk.pult.actor_label": ["Your name (it signs what is recorded in your name)",
    "Ваше имя (оно подписывает записи от вашего имени)"],
  "desk.pult.actor_save": ["Save", "Сохранить"],
  "desk.pult.actor_cancel": ["Cancel", "Отмена"],
  "desk.pult.actor_hint": [
    "Use letters and digits, then dots, hyphens or underscores; up to 128 characters.",
    "Латинские буквы и цифры, затем точки, дефисы или подчёркивания; до 128 знаков."],
  // -- the console: the project queue (spec 4.4.8) ---------------------------------------
  "desk.pult.queue": ["Project queue", "Очередь проекта"],
  "desk.pult.slot_free": ["Now: nothing is running · the slot is free",
    "Сейчас: ничего не идёт · слот свободен"],
  "desk.pult.slot_busy": ["Now: {task} · holds the slot", "Сейчас: {task} · держит слот"],
  "desk.pult.slot_stuck": ["Now: {task} · stopped and holds the slot",
    "Сейчас: {task} · остановился и держит слот"],
  "desk.pult.slot_unavailable": ["Now: the slot is unavailable", "Сейчас: слот недоступен"],
  "desk.pult.queue_empty": ["Nothing is queued.", "В очереди ничего нет."],
  "desk.pult.entry_start": ["{position}. {title} · starts on its own",
    "{position}. {title} · начнётся сама"],
  "desk.pult.entry_confirm": ["{position}. {title} · waits for your confirmation",
    "{position}. {title} · ждёт вашего подтверждения"],
  "desk.pult.entry_blocked": ["{position}. {title} · cannot start",
    "{position}. {title} · не может начаться"],
  "desk.pult.entry_queued": ["in the queue since {time}", "в очереди с {time}"],
  // -- the console: a project in view (spec 4.4.8, 5.8) ------------------------------------
  "desk.pult.inactive": [
    "Project not active · the queue starts when the project becomes active",
    "Проект не активен · очередь начнётся, когда проект станет активным"],
  "desk.pult.flag": [
    "Entries start by themselves after activation only if the project has “continue after” "
      + "set with the task queue. Otherwise we ask you again after activation.",
    "Записи начнутся сами после активации, только если у проекта стоит «продолжить после» "
      + "с очередью задач. Иначе после активации спросим вас снова."],
});
