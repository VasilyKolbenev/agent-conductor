"""The map of the five tabs' functions, typed from spec 5.6 (not a test file).

Spec 5.6 lists every function of the Studio's five tabs (`overview, workflow, runs, decisions,
agents`) in six tables, 5.6.1 to 5.6.6, and says where each one lives on the desk. The owner asks
that a function be "mapped to the new workspace, not deleted silently". The desk is built in
slices by several lanes, so most rows are not on it yet; what the map promises is that each row
says which of four things is so, and that the source agrees:

- `on_desk`: a booted desk draws or does it (the proof is in `desk.js` and what it imports);
- `module_only`: a module and its tests exist but no boot module mounts it: the place is named and
  the mount is the desk's (D1's `desk.js`);
- `not_built`: nothing of it exists; the owner and what blocks it are named;
- `retired`: the spec's "У": the Studio's code stays until the slice that removes the five tabs
  (D2), and the row says where the function went.

A row carries PROOFS, small facts of the source: a token a file has (`in`, of a file the desk
imports), a file that exists and that `desk.js` does not reach (`module`), a token a file does not
have (`absent`), a placeholder that still stands (`present`), a piece of old code that is still
there (`kept`). The guard holds the state of each row to its proofs, so a row that says "not
built" stops being true the day somebody builds it and reds until it is moved, and a row that says
"on the desk" reds the day its code goes. A part of a row that is not done (`owed`) names its
owner too.

The rows are typed here as the spec's tables: the name in the first column is the spec's own.
"""
from __future__ import annotations

from typing import NamedTuple

OWNERS = ("D1", "D2", "H", "L")
STATES = ("on_desk", "module_only", "not_built", "retired")
PROOF_KINDS = ("in", "module", "token", "absent", "present", "kept")


class Row(NamedTuple):
    """One function of the five tabs and what is so of it today."""

    section: str
    name: str
    place: str
    state: str
    proofs: tuple[tuple[str, str, str], ...]
    owner: str | None = None
    owed: tuple[tuple[str, str], ...] = ()
    selector: str | None = None


def _in(file: str, token: str) -> tuple[str, str, str]:
    return ("in", file, token)


def _module(file: str) -> tuple[str, str, str]:
    return ("module", file, "")


def _absent(file: str, token: str) -> tuple[str, str, str]:
    return ("absent", file, token)


def _in_module(file: str, token: str) -> tuple[str, str, str]:
    """A token a module that is NOT mounted has: the function exists, only the mount does not."""
    return ("token", file, token)


#: Still standing: the boot module says the desk opens no stream.
NO_STREAM = ("present", "desk.js", "NO_STREAM")
#: A panel other than the flag's block: `desk.js` has no row for `cycle`, `run` or `people`.
NO_PANEL = _absent("desk.js", "\"people\"")
#: The mount of the wizard and of the cycle editor: no module of the desk imports them.
WIZARD = _module("desk-wizard.js")
FLOW = _module("desk-flow.js")

ROWS: tuple[Row, ...] = (
    # -- 5.6.1 the frame --------------------------------------------------------------------
    Row("5.6.1", "Имя проекта", "top: project › task", "not_built",
        (_absent("desk-copy.js", "\"desk.path"),), "D1"),
    Row("5.6.1", "Привязка к проекту", "desk.js: the claim read first, the terminal state",
        "on_desk", (_in("desk.js", "enterForeign"), _in("desk-transport.js", "X-Conduct-Project"))),
    Row("5.6.1", "Пометка демо-проекта", "top: «Демо-данные»", "not_built",
        (_absent("desk.js", "demo"),), "D1"),
    Row("5.6.1", "Соединение", "top: indicator", "not_built", (NO_STREAM,), "D1"),
    Row("5.6.1", "Главное действие", "centre: the button in the task heading", "not_built",
        (_absent("desk.js", "primary"),), "D1"),
    Row("5.6.1", "Вкладки и стрелки", "the rail, the pult and the panels replace them", "retired",
        (("kept", "studio.html", "role=\"tablist\""), _absent("desk.html", "tablist")), "D2"),
    Row("5.6.1", "Семь слов состояния", "data-state of every region", "on_desk",
        (_in("desk.html", "data-state=\"empty\""), _in("desk.js", "data-state")),
        selector="[data-region][data-state]"),
    Row("5.6.1", "Строка статуса aria-live", "one line for the whole desk", "on_desk",
        (_in("desk.html", "role=\"status\""), _in("desk.html", "aria-live=\"polite\"")),
        selector="#deskStatus[role=\"status\"][aria-live=\"polite\"]"),
    Row("5.6.1", "RU/EN и тема", "top: the segments (hidden in a frame)", "not_built",
        (_absent("desk.html", "desk-seg"), _in("desk-hash.js", "readPreferences")), "D1",
        owed=(("D1", "the standalone segments; a framed desk follows the hub's hash"),)),
    Row("5.6.1", "«Прежняя панель»", "top: the link", "on_desk",
        (_in("desk.html", "href=\"/panel/index.html\""),), selector="a[href=\"/panel/index.html\"]"),
    Row("5.6.1", "Навигация в hash", "desk-hash.js and the hashchange router", "on_desk",
        (_in("desk.js", "navigationChange"), _in("desk.js", "hashchange")),
        owed=(("D1", "the keys panel, new, prepare, starter and workflow: no surface takes them"),)),
    Row("5.6.1", "Кто действует (actor)", "pult: «Вы: <имя> · изменить»", "on_desk",
        (_in("desk-pult.js", "desk.pult.actor"), _in("desk.js", "setActor")),
        selector=".desk-pult__actor"),
    Row("5.6.1", "Перенос набранного текста и фокуса", "the whole desk", "on_desk",
        (_in("desk.js", "restoreFocus"),)),
    Row("5.6.1", "Поток SSE: кадры state и run вызывают перечитывание", "desk-transport.js",
        "not_built", (NO_STREAM, _in("desk-transport.js", "EventSource")), "D1"),
    # -- 5.6.2 overview ---------------------------------------------------------------------
    Row("5.6.2", "Последний запуск", "centre: the task heading; status in the rail", "retired",
        (("kept", "studio-view.js", "latestRunCard"),), "D2"),
    Row("5.6.2", "«Нужно ваше внимание»", "pult: «Ждут вас» of this project", "not_built",
        (_absent("desk-pult.js", "attention"),), "D1"),
    Row("5.6.2", "«Что мешает»", "pult: the block with up to 12 rows", "not_built",
        (_absent("desk-pult.js", "blockingRows"),), "D1"),
    Row("5.6.2", "Готовность к запуску", "wizard: the roles and preparation steps", "module_only",
        (_module("desk-wizard-roles.js"), _module("desk-wizard-prep.js")), "D1"),
    Row("5.6.2", "«Что это за проект»", "the head of «Схема»: cycle, revisions, draft",
        "module_only", (FLOW, _in_module("desk-flow.js", "sourceLine")), "D1"),
    # -- 5.6.3 process (the editor) -----------------------------------------------------------
    Row("5.6.3", "Выбор цикла", "«Схема»: the picker and «Сделать циклом проекта»",
        "module_only", (FLOW, _in_module("desk-flow.js", "function picker")), "D1"),
    Row("5.6.3", "Новый цикл", "«Схема»: the menu of ways to begin", "module_only",
        (FLOW, _in_module("desk-flow.js", "beginMenu")), "D1"),
    Row("5.6.3", "Проверить / сохранить / опубликовать / «править как копию»",
        "«Схема»: the toolbar", "module_only",
        (_module("desk-flowwrite.js"), _in_module("desk-flow.js", "publishControl")), "D1"),
    Row("5.6.3", "Подтверждение ревизии со списком изменений", "«Схема»: the review", "module_only",
        (FLOW, _in_module("desk-flow-graph.js", "changeSummary")), "D1"),
    Row("5.6.3", "Строка результата сохранения", "«Схема»: the save line", "module_only",
        (FLOW, _in_module("desk-flow.js", "SAVE_LINES")), "D1"),
    Row("5.6.3", "Холст: палитра, пан и зум, перетаскивание, соединение, клавиатура, помощь",
        "«Схема»: the canvas", "module_only",
        (FLOW, _in_module("desk-flow-graph.js", "flowGraph")), "D1"),
    Row("5.6.3", "Линзы «Трасса / Орбита» для определения цикла", "«Схема»", "module_only",
        (FLOW, _in_module("desk-flow.js", "mountCanvas")), "D1"),
    Row("5.6.3", "Инспектор: название, тип, позиция, назначение", "«Схема»: the step inspector",
        "module_only", (FLOW, _in_module("desk-flow-inspector.js", "inspector")), "D1"),
    Row("5.6.3", "Роль и проверяющий", "«Схема»: role and «проверяет»", "module_only",
        (FLOW, _in_module("desk-flow-shape.js", "ROLE_KINDS")), "D1"),
    Row("5.6.3", "Потолки шага, бюджет вывода, вложения, аргументы", "«Схема»: timeout; the rest in the extended fields",
        "module_only", (FLOW, _in_module("desk-flow-fields.js", "WRITTEN_FIELDS")), "D1"),
    Row("5.6.3", "Входы и выходы шага", "«Схема»: manual inputs in the extended fields",
        "module_only", (FLOW, _in_module("desk-flow-fields.js", "stepRows")), "D1",
        owed=(("L", "the chain of inputs from the compiler: `compiled` in FlowState"),)),
    Row("5.6.3", "Проверка", "«Схема»: «проверяет» and the server's criteria", "module_only",
        (FLOW, _in_module("desk-flow-inspector.js", "verifier")), "D1"),
    Row("5.6.3", "«Расширенные поля»", "«Схема»: the fold of the step, the road and the cycle",
        "module_only", (FLOW, _in_module("desk-flow-shape.js", "EXT_FIELDS")), "D1"),
    Row("5.6.3", "Переходы, решение гейта, петли", "«Схема»: links.when, loops, passes",
        "module_only", (FLOW, _in_module("desk-flow-loops.js", "withoutStep")), "D1"),
    Row("5.6.3", "Порядок, копия, удаление шага; условие и удаление ребра",
        "«Схема»: the step actions and «Сначала эта ветка»", "module_only",
        (FLOW, _in_module("desk-flow-edits.js", "EDIT_TYPES")), "D1"),
    Row("5.6.3", "Диагностика: локальные и серверные проблемы", "«Схема»: «Что мешает публикации»",
        "module_only", (FLOW, _in_module("desk-flow-diag.js", "diagnosticsView")), "D1"),
    Row("5.6.3", "Быстрый линейный ввод", "wizard «Цикл» → «＋ Собрать свой»", "module_only",
        (_module("desk-quickcycle.js"), _in_module("desk-quickcycle.js", "QUICK_KINDS")), "D1"),
    Row("5.6.3", "«Открыть запуск»: run_id, cycle_id, режим, роль → харнесс, модель",
        "wizard: «Роли и указания»", "module_only", (WIZARD, _module("desk-wizard-roles.js")),
        "D1", owed=(("D1", "the manual run with its modes: «Запуск подробно › Ручной запуск»"),)),
    # -- 5.6.4 runs ---------------------------------------------------------------------------
    Row("5.6.4", "Задачи проекта, строка «Все задачи», статус задачи", "the rail", "on_desk",
        (_in("desk-rail.js", "taskStatus"),), selector="#deskRail [data-task-id]"),
    Row("5.6.4", "Выбор задачи", "the rail or the hash: task=<id>", "on_desk",
        (_in("desk.js", "chooseTask"),),
        owed=(("D2", "«Подготовить запуск» for a task with no run: prepare=1, the wizard"),)),
    Row("5.6.4", "Создать задачу", "wizard: the «Задача» step", "module_only",
        (WIZARD, _in_module("desk-wizard.js", "mountWizard")), "D1"),
    Row("5.6.4", "Исход создания задачи", "the wizard's result; a line in the centre heading",
        "module_only", (WIZARD, _in_module("desk-wizard.js", "onWizardClose")), "D1"),
    Row("5.6.4", "Обновить задачи и запуски", "the «↻» of the rail and of the run panel",
        "not_built", (_absent("desk-rail.js", "refresh"),), "D1"),
    Row("5.6.4", "Карточка цикла", "centre, under the task heading: read only", "not_built",
        (_absent("desk.html", "cycle"),), "D1"),
    Row("5.6.4", "Список запусков задачи", "«Запуск подробно › Запуски»", "not_built",
        (NO_PANEL,), "D1"),
    Row("5.6.4", "Заголовок и положение запуска", "centre: the task heading", "on_desk",
        (_in("desk-scene.js", "subject"),)),
    Row("5.6.4", "Сцена: линзы, планеты, орбита, состав, легенда", "the scene", "on_desk",
        (_in("desk-scene.js", "participantDeck"),), selector="#deskScene [data-deck-run]"),
    Row("5.6.4", "Участник: шаг (вход → действие → результат), параметры, история",
        "the scene: the participant panel", "on_desk", (_in("desk-scene.js", "participantDeck"),)),
    Row("5.6.4", "Гейт и петля на сцене", "the scene; «Открыть решение» leads to the pult",
        "on_desk", (_in("desk-scene.js", "participantDeck"),),
        owed=(("D1", "«Открыть решение»: no decisions surface for it to open yet"),)),
    Row("5.6.4", "Паспорт запуска", "«Запуск подробно › Паспорт»", "not_built", (NO_PANEL,), "D1"),
    Row("5.6.4", "План и положение шагов", "«Запуск подробно › Шаги»", "not_built",
        (NO_PANEL,), "D1"),
    Row("5.6.4", "Ручные шаги и защита шага", "«Запуск подробно › Шаги»", "not_built",
        (NO_PANEL,), "D1"),
    Row("5.6.4", "Документы запуска", "«Запуск подробно › Документы»", "not_built",
        (NO_PANEL,), "D1"),
    Row("5.6.4", "Результат и доказательства", "the feed: the verdict row", "on_desk",
        (_in("desk-feed.js", "feedRows"),),
        owed=(("D1", "«Запуск подробно › Результат»"),)),
    Row("5.6.4", "Артефакты", "the feed: a document opens in its row", "on_desk",
        (_in("desk-feed.js", "desk-feed__doc"),),
        owed=(("D1", "«Запуск подробно › Документы»"),)),
    Row("5.6.4", "Журнал записей", "the feed «Ход работы»", "on_desk",
        (_in("desk-feed.js", "feedRows"),), selector="#deskFeed .desk-feed__log"),
    Row("5.6.4", "Нечитаемая запись запуска", "the status «Запись не читается»", "on_desk",
        (_in("desk-status.js", "run_unreadable"),),
        owed=(("D1", "the way to recover, in «Запуск подробно»"),)),
    Row("5.6.4", "Замечания проверяющего", "the feed (a finding is a document)", "on_desk",
        (_in("desk-feed.js", "desk-feed__finding"),),
        owed=(("D1", "the participant panel of the scene: findings beside the checker"),)),
    Row("5.6.4", "Bounded-запуск: лимиты, preview, условия, «Подтвердить»",
        "wizard «Подготовка» and «Запуск»; the pult for an opened run", "module_only",
        (WIZARD, _module("desk-wizard-launch.js")), "D1",
        owed=(("D1", "the pult's confirmation for a run that is already open"),)),
    Row("5.6.4", "Пауза / возобновить / отозвать", "pult: «Освободить слот» and the holder's card",
        "not_built", (_absent("desk-pult.js", "revoke"),), "D1"),
    Row("5.6.4", "Очередь запусков проекта", "pult: the block «Очередь проекта»", "not_built",
        (_in("desk-pult.js", "desk.pult.queue"), _absent("desk.js", "/command/queue")), "D1",
        owed=(("D1", "the read of the queue in load() and the writes: order, withdraw, confirm"),)),
    Row("5.6.4", "«Ваш пульт», «Очередь внимания», «Ресурсы сейчас»", "the pult", "on_desk",
        (_in("desk.html", "desk.pult.label"),), selector="#deskPult",
        owed=(("D1", "«Очередь внимания» and «Ресурсы сейчас»"),)),
    # -- 5.6.5 decisions ----------------------------------------------------------------------
    Row("5.6.5", "Гейты запуска и квитанции", "«Запуск подробно › Решения»", "not_built",
        (NO_PANEL,), "D1"),
    Row("5.6.5", "Ответ на гейт: зачем, что откроет, ответы, actor, причина", "pult: the gate card",
        "not_built", (_absent("desk-pult.js", "gate"),), "D1"),
    Row("5.6.5", "«Доработать» на финальном гейте", "pult: new, L36", "not_built",
        (_absent("desk-pult.js", "rework"),), "D1",
        owed=(("D2", "a rework mode of the wizard: the owner's remarks as a document"),)),
    Row("5.6.5", "Почему пока нельзя ответить", "pult: why-not-yet", "not_built",
        (_absent("desk-pult.js", "whyNotYet"),), "D1"),
    # -- 5.6.6 agents -------------------------------------------------------------------------
    Row("5.6.6", "Лимиты полностью", "«Участники»; briefly the pult", "not_built",
        (NO_PANEL, _absent("desk-pult.js", "quota")), "D1"),
    Row("5.6.6", "Обновление лимитов раз в 60 с", "the pult, whatever the view", "not_built",
        (_absent("desk.js", "quota"),), "D1"),
    Row("5.6.6", "Харнессы: доступность, сборка, вход, controls", "«Участники»", "not_built",
        (NO_PANEL,), "D1"),
    Row("5.6.6", "Нет провайдеров: `conduct providers`, файл, поля", "«Участники»; the wizard",
        "not_built", (NO_PANEL,), "D1"),
    Row("5.6.6", "Участники запуска", "«Участники» and the summary panel", "on_desk",
        (_in("desk-summary-model.js", "participantsOf"),),
        owed=(("D1", "the panel «Участники»"),)),
)

