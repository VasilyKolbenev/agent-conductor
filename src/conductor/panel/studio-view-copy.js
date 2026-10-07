"use strict";
export const VIEW_COPY = Object.freeze({
  "view.m001": [
    "No workflow is chosen, so there is nothing to start.",
    "Процесс не выбран — запускать пока нечего."
  ],
  "view.m002": [
    "No configured provider is available on this machine, so nothing could carry a step out. The Agents screen says exactly what to write.",
    "На этом компьютере нет доступного настроенного провайдера для исполнения шагов. Инструкции по настройке приведены на экране участников."
  ],
  "view.m003": [
    "This project has no name yet: its conductor/map.toml carries none, or still carries the placeholder a template ships with. Set `project` there and restart to see it here.",
    "У проекта пока нет имени: в conductor/map.toml оно отсутствует или осталось шаблонным. Задайте там `project` и перезапустите сервер."
  ],
  "view.m004": [
    "No workflow is chosen. The Workflow screen lists every one this project holds and can start a new one.",
    "Процесс не выбран. На экране процессов можно выбрать существующий или создать новый."
  ],
  "view.m005": [
    "Choose a workflow",
    "Выбрать процесс"
  ],
  "view.m006": [
    "What this is",
    "О проекте"
  ],
  "view.m007": [
    "Workflow",
    "Процесс"
  ],
  "view.m008": [
    "Name",
    "Название"
  ],
  "view.m009": [
    "Published revisions",
    "Опубликованные версии"
  ],
  "view.m010": [
    "Latest revision",
    "Последняя версия"
  ],
  "view.m011": [
    "Unsaved draft on the server",
    "Черновик на сервере"
  ],
  "view.m012": [
    "Edit this workflow",
    "Изменить этот процесс"
  ],
  "view.m013": [
    "The drawing on screen has changes this window is holding and the server has not been given. Saving the draft is what stores them.",
    "На экране есть изменения, которые пока хранятся только в этом окне. Сохраните черновик, чтобы записать их на сервер."
  ],
  "view.m014": [
    "Ready to run?",
    "Готовность к запуску"
  ],
  "view.m015": [
    "ready to open a run",
    "можно открыть запуск"
  ],
  "view.m016": [
    "not yet",
    "пока не готов"
  ],
  "view.m017": [
    "What is blocked",
    "Что мешает работе"
  ],
  "view.m018": [
    "Nothing read so far is blocking. That is a statement about what has been read, not a promise about what has not.",
    "В прочитанных данных препятствий нет. Это относится только к уже прочитанным сведениям."
  ],
  "view.m019": [
    "Open it",
    "Открыть"
  ],
  "view.m020": [
    "The most recent run",
    "Последний запуск"
  ],
  "view.m021": [
    "Every run this project holds is one whose journal did not replay, so none of them can name a most recent.",
    "По имеющимся журналам нельзя достоверно определить последний запуск. Выберите запуск на экране запусков."
  ],
  "view.m022": [
    "This project holds no run yet. Opening one from the Workflow screen is what creates the first.",
    "В проекте пока нет запусков. Первый можно открыть на экране процесса."
  ],
  "view.m023": [
    "Open the Runs screen",
    "Открыть запуски"
  ],
  "view.m024": [
    "Run",
    "Запуск"
  ],
  "view.m025": [
    "Opened at",
    "Открыт"
  ],
  "view.m026": [
    "Authority (mode)",
    "Режим разрешений"
  ],
  "view.m027": [
    "Opened as",
    "Состояние при открытии"
  ],
  "view.m028": [
    "Opened as is what the run was CREATED as. A run envelope is immutable, so it never reports where the run now stands.",
    "Это состояние при создании запуска. Неизменяемая запись открытия не описывает его текущее положение."
  ],
  "view.m029": [
    "No action of this run has recorded a result yet, which is a different thing from a result that was bad.",
    "Ни одно действие этого запуска пока не записало результат. Это ещё не означает неудачу."
  ],
  "view.m030": [
    "Actions still open",
    "Незавершённые действия"
  ],
  "view.m031": [
    "Read this run",
    "Открыть этот запуск"
  ],
  "view.m032": [
    "choose a workflow",
    "выберите процесс"
  ],
  "view.m033": [
    "A blank start is an empty drawing.",
    "Новый процесс начнётся с пустого черновика."
  ],
  "view.m034": [
    "start blank",
    "пустой черновик"
  ],
  "view.m035": [
    "This screen was mounted without an editStarter handler.",
    "Изменение исходного шаблона в этом окне не подключено."
  ],
  "view.m036": [
    "Start a workflow",
    "Создать процесс"
  ],
  "view.m037": [
    "This screen was mounted without an onStartWorkflow handler.",
    "Создание процесса в этом окне не подключено."
  ],
  "view.m038": [
    "New workflow id",
    "ID нового процесса"
  ],
  "view.m039": [
    "Start from",
    "Начать с"
  ],
  "view.m040": [
    "Publish revision",
    "Опубликовать версию"
  ],
  "view.m041": [
    "Validate",
    "Проверить"
  ],
  "view.m042": [
    "There is already a drawing on screen; edit it and save the draft.",
    "На экране уже есть черновик. Измените и сохраните его."
  ],
  "view.m043": [
    "This workflow has no published revision to copy.",
    "У этого процесса нет опубликованной версии для копирования."
  ],
  "view.m044": [
    "This workflow has not been read since the connection came back.",
    "После восстановления связи процесс ещё не прочитан."
  ],
  "view.m045": [
    "This draft is the revision already published, word for word. Publishing it would record an edit that never happened.",
    "Черновик полностью совпадает с опубликованной версией. Изменений для новой публикации нет."
  ],
  "view.m046": [
    "Publishing needs a SAVED draft the server says would construct a revision. Save the drawing first, then read what stops it.",
    "Для публикации нужен сохранённый черновик, который сервер допускает как версию. Сохраните его и проверьте оставшиеся замечания."
  ],
  "view.m047": [
    "Steps added",
    "Добавлены шаги"
  ],
  "view.m048": [
    "Steps removed",
    "Удалены шаги"
  ],
  "view.m049": [
    "Steps changed",
    "Изменены шаги"
  ],
  "view.m050": [
    "Connections added",
    "Добавлены связи"
  ],
  "view.m051": [
    "Connections removed",
    "Удалены связи"
  ],
  "view.m052": [
    "A revision is immutable. Once written it stands, and later edits become further revisions rather than changing this one.",
    "Опубликованная версия неизменяема. Последующие изменения создадут новые версии."
  ],
  "view.m053": [
    "Validation: the server says this draft would construct a revision.",
    "Проверка: сервер допускает публикацию этого черновика."
  ],
  "view.m054": [
    "Validation: the server refuses this draft.",
    "Проверка: сервер отклоняет этот черновик."
  ],
  "view.m055": [
    "This is the first revision, so there is nothing to compare it against. What it creates is listed in full.",
    "Это первая версия, поэтому сравнивать её пока не с чем. Ниже перечислено всё, что будет создано."
  ],
  "view.m056": [
    "There is no drawing to review.",
    "Нет черновика для просмотра."
  ],
  "view.m057": [
    "No structural change was found between this drawing and the revision now standing.",
    "Структурных различий между черновиком и текущей версией не найдено."
  ],
  "view.m058": [
    "Cancel",
    "Отмена"
  ],
  "view.m059": [
    "Open a run — choose or start a workflow first",
    "Открыть запуск — сначала выберите или создайте процесс"
  ],
  "view.m060": [
    "Open a run — this workflow has not been read",
    "Открыть запуск — процесс ещё не прочитан"
  ],
  "view.m061": [
    "Open a run — publish a revision first",
    "Открыть запуск — сначала опубликуйте версию"
  ],
  "view.m062": [
    "Start a new workflow",
    "Создать новый процесс"
  ],
  "view.m063": [
    "Nothing here stops it.",
    "Здесь препятствий нет."
  ],
  "view.m064": [
    "What stops publishing",
    "Что мешает публикации"
  ],
  "view.m065": [
    "The drawing on screen",
    "Черновик на экране"
  ],
  "view.m066": [
    "What this window can already see the save route would refuse. It is about the UNSAVED drawing and nothing has been sent.",
    "Замечания этого окна к несохранённому черновику. Он ещё не отправлен на сервер."
  ],
  "view.m067": [
    "The draft on the server",
    "Черновик на сервере"
  ],
  "view.m068": [
    "No draft is stored for this workflow yet.",
    "Для этого процесса ещё не сохранён черновик."
  ],
  "view.m069": [
    "This screen was mounted without a {name} handler.",
    "В этом экране не подключено действие {name}."
  ],
  "view.m070": [
    "The saved draft does not yet construct a revision: {message}",
    "Сохранённый черновик пока нельзя опубликовать: {message}"
  ],
  "view.m071": [
    "Workflow {id} has a revision this build cannot read.",
    "Версию процесса {id} невозможно прочитать."
  ],
  "view.m072": [
    "Run {id} did not replay, so nothing derived from it can be shown. It is listed rather than hidden.",
    "Журнал запуска {id} не удалось восстановить. Запуск показан в списке, но выводы из его журнала недоступны."
  ],
  "view.m073": [
    "No available provider serves {capability}, and {count} step(s) of this workflow need it: {steps}.",
    "Нет доступного провайдера для {capability}. Эта возможность нужна шагам ({count}): {steps}."
  ],
  "view.m074": [
    "{id} has no published revision yet. A run follows a revision, so publish the draft first.",
    "У процесса {id} ещё нет опубликованной версии. Сначала опубликуйте черновик."
  ],
  "view.m075": [
    "Revision {revision} is published; available providers on this machine: {count}. Role bindings are settled when the run opens.",
    "Версия {revision} опубликована. Доступных провайдеров: {count}. Роли назначаются при создании запуска."
  ],
  "view.m076": [
    "This is {name}, the project this server was started in. The name comes from conductor/map.toml.",
    "Проект: {name}. Имя прочитано из conductor/map.toml проекта, в котором запущен сервер."
  ],
  "view.m077": [
    "{count} blocking",
    "Препятствий: {count}"
  ],
  "view.m078": [
    "{count} more are on the screens above.",
    "Ещё {count} показано на соответствующих экранах."
  ],
  "view.m079": [
    "last outcome: {outcome}",
    "Последний исход: {outcome}"
  ],
  "view.m080": [
    "{id} — new, not saved yet",
    "{id} — новый, ещё не сохранён"
  ],
  "view.m081": [
    "{title} · revision {revision}",
    "{title} · версия {revision}"
  ],
  "view.m082": [
    "{name} — ready to run",
    "{name} — готов к запуску"
  ],
  "view.m083": [
    "{name} — see the note",
    "{name} — см. примечание"
  ],
  "view.m084": [
    "{title} · revision {revision} is ready to run.",
    "{title} · версия {revision} готова к запуску."
  ],
  "view.m085": [
    "Publish revision {revision}",
    "Опубликовать версию {revision}"
  ],
  "view.m086": [
    "Publish revision {revision}?",
    "Опубликовать версию {revision}?"
  ],
  "view.m087": [
    "Confirm and publish revision {revision}",
    "Подтвердить и опубликовать версию {revision}"
  ],
  "view.m088": [
    "Creates the workflow \"{title}\"",
    "Создаёт процесс «{title}»"
  ],
  "view.m089": [
    "Title: \"{before}\" becomes \"{after}\"",
    "Название: «{before}» → «{after}»"
  ],
  "view.m090": [
    "Open a run — revision {revision} is published",
    "Открыть запуск — версия {revision} опубликована"
  ],
  "view.m091": [
    "The server's own answer about the draft it stored at {at}.",
    "Ответ сервера о черновике, сохранённом {at}."
  ],
  "view.m092": [
    "Nothing stops publishing revision {revision}.",
    "Препятствий для публикации версии {revision} нет."
  ],
  "view.m093": [
    "yes",
    "да"
  ],
  "view.m094": [
    "no",
    "нет"
  ],
  "view.not_stated": [
    "not stated",
    "не указано"
  ],
  "view.new_draft": [
    "Edit as new draft",
    "Изменить как новый черновик"
  ],
  "view.verification_note": [
    "Process exit 0 proves the process finished, not that the work was verified.",
    "Код завершения 0 подтверждает окончание процесса, но не независимую проверку результата."
  ]
});
