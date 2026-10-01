"use strict";
// The words of the hub's page, English first and Russian second, like every other copy module of
// the panel. The hub imports neither `studio-i18n.js` nor `command-view.js` (spec 4.1.10), so this is
// its own catalogue and its own `hubText`; it also says the keys of `desk-status-copy.js`, the shared
// module whose words the hub's column and the desk's rail both use, so one task is told in one set of
// words in both places.
//
// Five families and no string besides: the frame of the page, the project's line (the working state
// and the lifecycle state of spec 4.1.10), the actions and their confirmations, the banners, and one
// clause for every code of the three closed lists of the hub (`hub.code.<code>`: the refusals of a
// route, the codes of a failed step and the codes of a start that did not happen, spec 4.6.5 and
// 4.1.5). A condition that is checked before a route answers and again inside a long step has one name
// and one clause. A code is always a clause (lower case, no full stop) that a sentence can carry after
// its colon; no message shows a raw code, and a code the page has no word for is said by
// `hub.code_unknown`, never by itself. A message takes named string values and nothing else.
import {DESK_STATUS_COPY} from "./desk-status-copy.js";

export const HUB_COPY = Object.freeze({
  "hub.add.home": ["Folder for new projects", "Папка новых проектов"],
  "hub.add.change_home": ["Change folder…", "Изменить папку…"],
  // -- the frame -----------------------------------------------------------------------
  "hub.page_title": ["December Command — Hub", "December Command — Hub"],
  "hub.top.label": ["Top bar", "Верхняя панель"],
  "hub.banners.label": ["Notices", "Уведомления"],
  "hub.confirm.label": ["Confirmation", "Подтверждение"],
  "hub.rail.label": ["Projects and tasks", "Проекты и задачи"],
  "hub.center.label": ["The chosen project", "Выбранный проект"],
  "hub.side.label": ["Queue of projects and limits", "Очередь проектов и лимиты"],
  "hub.new_task": ["＋ New task", "＋ Новая задача"],
  "hub.new_task.blocked": ["The project has no running desk.", "У проекта нет работающего стола."],
  "hub.add_project": ["＋ Add a project", "＋ Добавить проект"],
  "hub.add.heading": ["Add a project", "Добавить проект"],
  "hub.add.source_folder": ["Existing folder", "Папка на компьютере"],
  "hub.add.source_scratch": ["Start from scratch", "С нуля"],
  "hub.add.source_github": ["GitHub repository", "Репозиторий GitHub"],
  "hub.add.github_intro": ["Choose a repository to clone into your projects folder.",
    "Выберите репозиторий для клонирования в папку проектов."],
  "hub.add.github_owner": ["Owner or organisation (empty: my repositories)", "Владелец или организация (пусто: мои репозитории)"],
  "hub.add.github_list": ["Show repositories", "Показать репозитории"],
  "hub.add.github_repo": ["Repository: owner/name", "Репозиторий: владелец/имя"],
  "hub.add.github_truncated": ["Showing the first 200. Enter owner/name to select another repository.", "Показаны первые 200. Другой репозиторий можно указать как владелец/имя."],
  "hub.add.github_loading": ["Checking GitHub sign-in…", "Проверяем вход в GitHub…"],
  "hub.add.github_ok": ["GitHub is connected", "GitHub подключён"],
  "hub.add.github_not_logged_in": ["Sign in to GitHub in your terminal", "Войдите в GitHub через терминал"],
  "hub.add.github_not_pinned": ["Pin GitHub CLI before continuing", "Сначала закрепите GitHub CLI"],
  "hub.add.github_changed": ["The pinned GitHub CLI has changed", "Закреплённый GitHub CLI изменился"],
  "hub.add.github_unreachable": ["GitHub did not respond", "GitHub не ответил"],
  "hub.add.github_failed": ["GitHub sign-in could not be checked", "Не удалось проверить вход в GitHub"],
  "hub.add.github_refresh": ["Check again", "Проверить снова"],
  "hub.add.github_pinned_login": ["Use the GitHub CLI executable pinned for December Command.", "Используйте GitHub CLI, закреплённый для December Command."],
  "hub.add.github_cancel": ["Cancel cloning", "Отменить клонирование"],
  "hub.add.cancelled": ["Cloning cancelled.", "Клонирование отменено."],
  "hub.add.cloned_not_added": ["Repository saved in {folder}, but the project was not added. Its files were kept.",
    "Репозиторий сохранён в {folder}, но проект не добавлен. Его файлы оставлены на месте."],
  "hub.add.scratch_intro": ["Create a project folder, then prepare its idea and materials in the task wizard.",
    "Создайте папку проекта, затем подготовьте идею и материалы в мастере задачи."],
  "hub.add.close": ["Close", "Закрыть"],
  "hub.add.intro": ["Choose an existing folder on this computer. Its path stays in the hub.",
    "Выберите существующую папку на этом компьютере. Её путь остаётся в hub."],
  "hub.add.choose": ["Choose folder…", "Выбрать папку…"],
  "hub.add.window": ["The folder window is open on this computer; it may be behind the browser.",
    "Окно выбора папки открыто на этом компьютере; оно может быть за браузером."],
  "hub.add.cancel": ["Cancel choice", "Отменить выбор"],
  "hub.add.folder": ["Folder", "Папка"],
  "hub.add.name": ["Project name", "Имя проекта"],
  "hub.add.writers": ["No other conduct up or agents are working in this folder now",
    "Других conduct up и агентов в этой папке сейчас нет"],
  "hub.add.ownership": ["Adding creates project data and enables ownership where needed.",
    "Добавление создаст данные проекта и при необходимости включит владение."],
  "hub.add.submit": ["Add", "Добавить"],
  "hub.add.progress": ["Step", "Шаг"],
  "hub.add.result": ["Added", "Добавлено"],
  "hub.add.serving": ["The project desk is ready.", "Стол проекта готов."],
  "hub.add.error": ["Could not complete", "Не удалось завершить"],
  "hub.add.step.admit": ["Check folder", "Проверка папки"],
  "hub.add.step.clone": ["Clone repository", "Клонирование репозитория"],
  "hub.add.step.git": ["Check git", "Проверка git"],
  "hub.add.step.init": ["Create project data", "Создание данных проекта"],
  "hub.add.step.activate": ["Enable ownership", "Включение владения"],
  "hub.add.step.providers": ["Apply profile", "Применение профиля"],
  "hub.add.step.exclude": ["Set git exclusions", "Настройка исключений git"],
  "hub.add.step.instructions": ["Find agent instructions", "Поиск инструкций агентов"],
  "hub.add.step.register": ["Register project", "Регистрация проекта"],
  "hub.add.step.start": ["Open project desk", "Открытие стола проекта"],
  "hub.first.heading": ["Add an existing folder", "Добавить существующую папку"],
  "hub.first.explain": ["Run these commands in a terminal, in order. Replace <absolute-folder> with your folder's absolute path. The project will appear here automatically. No harness is started by adding it.",
    "Выполните эти команды в терминале по порядку. Замените <absolute-folder> абсолютным путём к своей папке. Проект появится здесь автоматически. Добавление не запускает харнесс."],
  "hub.first.step.1": ["1. Set up the shared harness profile once:",
    "1. Один раз настройте общий профиль харнессов:"],
  "hub.first.step.2": ["2. Stop other writers in that folder, then explicitly activate and add it:",
    "2. Остановите других писателей в папке, затем явно включите владение и добавьте её:"],
  "hub.lang.label": ["Language", "Язык"],
  "hub.theme.label": ["Theme", "Тема"],
  "hub.theme.dark": ["Dark", "Тёмная"],
  "hub.theme.light": ["Light", "Светлая"],
  "hub.theme.system": ["System", "Системная"],
  "hub.path.label": ["Where you are", "Где вы"],
  "hub.path.none": ["No project chosen", "Проект не выбран"],
  "hub.status.loading": ["Reading the hub…", "Читаем hub…"],
  "hub.status.ready": ["Read.", "Прочитано."],
  "hub.status.failed": ["The hub could not be read.", "Hub не удалось прочитать."],
  "hub.status.stream_lost": ["Live updates were lost; trying again.",
    "Живые обновления прерваны; пробуем снова."],
  // -- the column of projects --------------------------------------------------------------
  "hub.rail.heading": ["Projects · {count}", "Проекты · {count}"],
  "hub.rail.waiting": ["◆ waiting for you: {count}", "◆ ждут вас: {count}"],
  "hub.rail.none": ["There are no projects yet.", "Проектов пока нет."],
  "hub.rail.badge": ["{count} waiting for you", "Ждут вас: {count}"],
  "hub.rail.tasks_none": ["The hub holds no tasks of this project.", "В данных hub задач проекта нет."],
  "hub.rail.no_data": ["No data yet", "Данных пока нет"],
  "hub.rail.menu": ["More about {name}", "Ещё о проекте {name}"],
  "hub.waiting.heading": ["Waiting for you", "Ждут вас"],
  "hub.waiting.none": ["Nothing waits for you.", "Вас ничто не ждёт."],
  "hub.waiting.row_task": ["{project} · {task} · {reason} · {since}",
    "{project} · {task} · {reason} · {since}"],
  "hub.waiting.row_project": ["{project} · {reason} · {since}", "{project} · {reason} · {since}"],
  // -- the line of a project: the working state, then the state of its process ---------------
  "hub.working.active": ["In progress", "В работе"],
  "hub.working.queued": ["Queued · #{position}", "В очереди · {position}-й"],
  "hub.working.stopped": ["Stopped", "Остановлен"],
  "hub.working.stopped_since": ["Stopped · since {time}", "Остановлен · с {time}"],
  "hub.working.view": ["View", "Просмотр"],
  "hub.working.view_queued": ["View · queued #{position}", "Просмотр · в очереди {position}-й"],
  "hub.state.starting_active": ["Starting…", "Запускается…"],
  "hub.state.starting_view": ["Opening…", "Открывается…"],
  "hub.state.stopping": ["Stopping, until {time}", "Останавливается, до {time}"],
  "hub.state.stopping_open": ["Stopping…", "Останавливается…"],
  "hub.state.stop_overdue": ["The stop is taking long: the step did not finish by {time}",
    "Остановка затянулась: шаг не закончился к {time}"],
  "hub.state.stop_overdue_open": ["The stop is taking long: the step has not finished",
    "Остановка затянулась: шаг не закончился"],
  "hub.state.stop_overdue_hint": ["Ending the process would mean recovering after a restart of the OS.",
    "Убить процесс — значит восстанавливать после перезагрузки ОС."],
  "hub.state.stop_uncertain": ["Stop not confirmed · the OS needs a restart",
    "Остановка не подтверждена · нужна перезагрузка ОС"],
  "hub.state.failed": ["Did not start: {reason}", "Не запустился: {reason}"],
  "hub.state.busy_elsewhere": ["Open in another conduct up", "Открыт другим conduct up"],
  "hub.state.recovery_required": ["The OS needs a restart", "Нужна перезагрузка ОС"],
  "hub.state.identity_mismatch": ["A different project is in the folder now",
    "В папке теперь другой проект"],
  "hub.state.missing": ["The folder was not found or was replaced", "Папка не найдена или заменена"],
  "hub.state.status_unreadable": ["The status file cannot be read, so no other project starts",
    "Файл состояния не читается, другой проект не запустится"],
  "hub.line.becomes_active": ["Will become active after {name} stops",
    "Станет активным после остановки {name}"],
  "hub.line.not_active": ["Did not become active: {name} is not closed · the OS needs a restart",
    "Не стал активным: {name} не закрыт · нужна перезагрузка ОС"],
  // -- actions and what asks before it is done ------------------------------------------------
  "hub.act.stop": ["Stop at a checkpoint", "Остановить на контрольной точке"],
  "hub.act.activate": ["Make active", "Сделать активным"],
  "hub.act.resume": ["Continue", "Продолжить"],
  "hub.act.view_open": ["Open for viewing", "Открыть на просмотр"],
  "hub.act.view_close": ["Close the view", "Закрыть просмотр"],
  "hub.act.restart": ["Start again", "Запустить снова"],
  "hub.act.recheck": ["Check again", "Проверить снова"],
  "hub.act.recover": ["Recover", "Восстановить"],
  "hub.act.forget": ["Remove from the list", "Убрать из списка"],
  "hub.act.raise": ["Raise", "Поднять"],
  "hub.act.lower": ["Lower", "Опустить"],
  "hub.act.clear_flag": ["Clear the flag", "Снять флаг"],
  "hub.act.recover_login": ["Recover the login", "Восстановить вход"],
  "hub.act.menu": ["⋯", "⋯"],
  "hub.confirm.switch": ["{name} is in progress now: it will stop at a checkpoint — its current step "
    + "will finish on its own.", "Сейчас в работе {name}: он остановится на контрольной точке — "
    + "текущий шаг закончится сам."],
  "hub.confirm.stop": ["The current step will finish on its own, no new step will begin. The stop "
    + "cannot be cancelled.", "Текущий шаг закончится сам, новые шаги не начнутся. Отменить остановку "
    + "нельзя."],
  "hub.confirm.stop_next": ["{name} will become active next.", "Следом станет активным {name}."],
  "hub.confirm.cancel": ["Cancel", "Отмена"],
  "hub.notice.refused": ["The hub refused: {reason}.", "Hub отказал: {reason}."],
  "hub.notice.accepted": ["The hub took it and is doing it.", "Hub принял и выполняет."],
  "hub.notice.not_built": ["The hub does not have this action in this build yet.",
    "В этой сборке hub этого действия пока нет."],
  "hub.notice.unknown": ["The hub did not answer. Read the state again before pressing twice.",
    "Hub не ответил. Прочитайте состояние ещё раз, прежде чем нажимать повторно."],
  // -- banners ---------------------------------------------------------------------------------
  "hub.banner.profile_absent": ["The harnesses are not set up", "Харнессы не настроены"],
  "hub.banner.profile_how": ["Run conduct providers --profile once in a terminal.",
    "Один раз выполните в терминале conduct providers --profile."],
  "hub.banner.profile_invalid": ["The harness profile cannot be read",
    "Профиль харнессов не читается"],
  "hub.banner.tools": ["git / gh are not pinned or have changed", "git / gh не закреплены или изменились"],
  "hub.banner.login": ["The login of {harness} is not closed", "Вход {harness} не закрыт"],
  "hub.banner.home_invalid": ["The folder for new projects cannot be used",
    "Папку для новых проектов нельзя использовать"],
  "hub.banner.registry": ["The project registry cannot be read", "Реестр не читается"],
  "hub.unlisted.note": ["A project taken off the list is not closed yet (since {time}): no other "
    + "project starts until it is.", "Проект, убранный из списка, ещё не закрыт (с {time}): другой "
    + "проект не запустится, пока он не будет закрыт."],
  "hub.unlisted.note_open": ["A project taken off the list is not closed yet: no other project "
    + "starts until it is.", "Проект, убранный из списка, ещё не закрыт: другой проект не "
    + "запустится, пока он не будет закрыт."],
  "hub.unlisted.relist_blocked": ["Putting it back needs the add-project dialog, which is not in "
    + "this build yet.", "Чтобы вернуть проект, нужно окно добавления проекта, его в этой сборке "
    + "пока нет."],
  "hub.act.relist": ["Put back on the list", "Вернуть в список"],
  "hub.banner.job": ["Projects do not start from this hub: it runs inside a Windows job",
    "Проекты из этого hub не запускаются: он внутри задания Windows"],
  "hub.banner.job_how": ["Stop the hub (Ctrl+C) and start conduct hub from a separate terminal "
    + "window, not from another application's built-in terminal", "Остановите hub (Ctrl+C) и "
    + "запустите conduct hub из отдельного окна терминала, а не из встроенного терминала другого "
    + "приложения"],
  // -- the bar over the desk, and the centre -------------------------------------------------
  "hub.view.with_active": ["View · {name} is in progress", "Просмотр · в работе {name}"],
  "hub.view.no_active": ["View · there is no active project", "Просмотр · активного проекта нет"],
  "hub.center.choose": ["Choose a project on the left.", "Выберите проект слева."],
  "hub.frame.title": ["Desk of {name}", "Стол проекта {name}"],
  "hub.center.stub": ["This project has no running desk.", "У этого проекта нет работающего стола."],
  "hub.center.drain": ["Stopping: {time} left", "Остановка: осталось {time}"],
  // -- the queue of projects and the limits of the active one ----------------------------------
  "hub.queue.heading": ["Queue of projects", "Очередь проектов"],
  "hub.queue.now": ["In progress: {name}", "В работе: {name}"],
  "hub.queue.none_active": ["There is no active project", "Активного проекта нет"],
  "hub.queue.entry": ["{position}. {name} · will continue by itself · flag since {time}",
    "{position}. {name} · продолжит сам · флаг с {time}"],
  "hub.queue.entry_open": ["{position}. {name} · will continue by itself",
    "{position}. {name} · продолжит сам"],
  "hub.queue.empty": ["No project waits in the queue.", "В очереди проектов никого нет."],
  "hub.limits.heading": ["Limits of the active project", "Лимиты активного проекта"],
  "hub.limits.live": ["limits are read by the active project", "лимиты читает активный проект"],
  "hub.limits.snapshot": ["limits are read by the active project · snapshot from {time}",
    "лимиты читает активный проект · снимок {time}"],
  "hub.limits.none": ["no data · limits are read by the active project",
    "нет данных · лимиты читает активный проект"],
  "hub.limits.unverified": ["the account is not confirmed", "аккаунт не подтверждён"],
  "hub.limits.window": ["{label}: {value}% left · resets {time}",
    "{label}: осталось {value}% · сброс {time}"],
  "hub.limits.window_open": ["{label}: {value}% left", "{label}: осталось {value}%"],
  "hub.limits.minutes": ["{count} min", "{count} мин"],
  "hub.limits.hours": ["{count} h", "{count} ч"],
  "hub.limits.balance": ["Balance {amount} {currency}", "Баланс {amount} {currency}"],
  "hub.limits.no_reset": ["reset does not apply", "сброс не применяется"],
  "hub.limits.missing": ["no data", "нет данных"],
  "hub.limits.error": ["the source is unavailable", "источник недоступен"],
  "hub.limits.unavailable": ["not available", "недоступно"],
  "hub.limits.stale": ["out of date", "устарело"],
  // -- one clause for each code of the closed lists (spec 4.6.5, 4.1.5) -------------------------
  "hub.code_unknown": ["a reason this page has no word for", "причина, для которой у страницы нет слов"],
  "hub.code.same_origin_denied": ["this page is not allowed to ask the hub",
    "этой странице нельзя обращаться к hub"],
  "hub.code.csrf_denied": ["the page's write token was not accepted: reload the page",
    "токен записи страницы не принят: перезагрузите страницу"],
  "hub.code.malformed_request": ["the request was not understood", "запрос не понят"],
  "hub.code.route_not_found": ["the hub has no such address", "у hub нет такого адреса"],
  "hub.code.method_not_allowed": ["the hub does not take this kind of request here",
    "hub не принимает здесь такой запрос"],
  "hub.code.contract_invalid": ["the request does not have the form the hub takes",
    "запрос не той формы, какую принимает hub"],
  "hub.code.windows_name_unsafe": ["Windows does not allow this name", "Windows не допускает такое имя"],
  "hub.code.windows_path_too_long": ["the path is too long for Windows",
    "путь слишком длинный для Windows"],
  "hub.code.name_invalid": ["the name is not allowed", "такое имя недопустимо"],
  "hub.code.folder_invalid": ["the folder name is not allowed", "такое имя папки недопустимо"],
  "hub.code.repo_invalid": ["the repository name is not allowed", "такое имя репозитория недопустимо"],
  "hub.code.project_not_found": ["the hub has no such project", "такого проекта у hub нет"],
  "hub.code.operation_not_found": ["the hub does not remember this operation",
    "hub не помнит эту операцию"],
  "hub.code.pick_not_found": ["the hub does not remember this folder choice",
    "hub не помнит этот выбор папки"],
  "hub.code.login_not_found": ["the hub does not know this login", "hub не знает этот вход"],
  "hub.code.candidate_not_found": ["that version is no longer on offer",
    "этой версии больше нет в предложении"],
  "hub.code.pick_invalid": ["the chosen folder cannot be used", "выбранную папку нельзя использовать"],
  "hub.code.legacy_writers_unconfirmed": ["confirm that no other conduct up or agent works in this "
    + "folder", "подтвердите, что в этой папке не работают другие conduct up и агенты"],
  "hub.code.folder_exists": ["a folder with this name already exists", "папка с таким именем уже есть"],
  "hub.code.projects_home_invalid": ["the folder for new projects cannot be used",
    "папку для новых проектов нельзя использовать"],
  "hub.code.review_harness_missing": ["no harness is set up to review a project started from scratch",
    "не настроен харнесс, который проверяет проект «с нуля»"],
  "hub.code.operation_busy": ["another operation is running", "идёт другая операция"],
  "hub.code.registry_busy": ["the project registry is busy", "реестр проектов занят"],
  "hub.code.registry_invalid": ["the project registry cannot be read", "реестр проектов не читается"],
  "hub.code.dialog_busy": ["a folder dialog is already open", "окно выбора папки уже открыто"],
  "hub.code.dialog_unavailable": ["the folder dialog cannot be opened here",
    "окно выбора папки здесь открыть нельзя"],
  "hub.code.profile_absent": ["the harness profile is not set", "профиль харнессов не задан"],
  "hub.code.profile_invalid": ["the harness profile cannot be read", "профиль харнессов не читается"],
  "hub.code.git_not_pinned": ["git is not pinned", "git не закреплён"],
  "hub.code.gh_not_pinned": ["gh is not pinned", "gh не закреплён"],
  "hub.code.git_changed": ["git has changed since it was pinned", "git изменился после закрепления"],
  "hub.code.gh_changed": ["gh has changed since it was pinned", "gh изменился после закрепления"],
  "hub.code.git_too_old": ["the pinned git is too old", "закреплённый git слишком старый"],
  "hub.code.tool_version_unreadable": ["the version of the tool cannot be read",
    "версию инструмента не удаётся прочитать"],
  "hub.code.gh_not_logged_in": ["gh is not logged in to GitHub", "gh не вошёл в GitHub"],
  "hub.code.gh_unreachable": ["GitHub cannot be reached", "GitHub недоступен"],
  "hub.code.gh_failed": ["gh failed", "gh завершился с ошибкой"],
  "hub.code.project_busy": ["the project is busy with another change", "проект занят другим изменением"],
  "hub.code.project_running": ["the project already has a running process",
    "у проекта уже работает процесс"],
  "hub.code.project_not_running": ["the project has no running process",
    "у проекта нет работающего процесса"],
  "hub.code.project_unavailable": ["the project cannot be used until it is removed from the list "
    + "and added again", "проект нельзя использовать, пока его не уберут из списка и не добавят "
    + "заново"],
  "hub.code.already_active": ["the project is already the active one", "проект уже активный"],
  "hub.code.active_not_closed": ["the previous active project is not closed",
    "прежний активный проект не закрыт"],
  "hub.code.recovery_required": ["the OS needs a restart", "нужна перезагрузка ОС"],
  "hub.code.recover_not_needed": ["there is nothing to recover", "восстанавливать нечего"],
  "hub.code.operation_not_cancellable": ["this step cannot be cancelled", "этот шаг отменить нельзя"],
  "hub.code.project_queue_changed": ["the queue of projects changed while you were choosing",
    "очередь проектов изменилась, пока вы выбирали"],
  "hub.code.hub_in_kill_on_close_job": ["hub runs inside a Windows job", "hub внутри задания Windows"],
  "hub.code.hub_flags_incomplete": ["startup error", "ошибка запуска"],
  "hub.code.project_id_invalid": ["startup error", "ошибка запуска"],
  "hub.code.hub_origin_invalid": ["startup error", "ошибка запуска"],
  "hub.code.status_file_invalid": ["startup error", "ошибка запуска"],
  "hub.code.stdin_is_terminal": ["startup error", "ошибка запуска"],
  "hub.code.mode_invalid": ["startup error", "ошибка запуска"],
  "hub.code.project_identity_changed": ["another project is in the folder now",
    "в папке теперь другой проект"],
  "hub.code.owner_busy": ["another conduct up holds the project", "проект держит другой conduct up"],
  "hub.code.ownership_lost": ["the folder was replaced or moved", "папка заменена или перенесена"],
  "hub.code.transition_conflict": ["the ownership state cannot be read",
    "состояние владения не читается"],
  "hub.code.ownership_unavailable": ["the ownership state cannot be read",
    "состояние владения не читается"],
  "hub.code.store_error": ["the project map cannot be read", "карта проекта не читается"],
  "hub.code.providers_invalid": ["the project's providers.json was not accepted",
    "providers.json проекта не принят"],
  "hub.code.bind_failed": ["the port is taken", "порт занят"],
  "hub.code.start_failed": ["the process did not start", "процесс не запустился"],
  "hub.code.start_timeout": ["it did not answer in time", "не ответил вовремя"],
  "hub.code.status_unreadable": ["the status file of a project cannot be read; no other project "
    + "starts until it is", "файл состояния проекта не читается; пока он не исправлен, другой "
    + "проект не запустится"],
  "hub.code.clone_timeout": ["cloning took too long", "клонирование заняло слишком много времени"],
  "hub.code.clone_failed": ["cloning failed", "клонирование не удалось"],
  "hub.code.clone_cleanup_incomplete": ["cloning failed and its folder could not be removed "
    + "completely", "клонирование не удалось, папку не удалось убрать полностью"],
  "hub.code.root_invalid": ["the folder cannot be a project", "эта папка не может быть проектом"],
  "hub.code.root_too_broad": ["the folder is too broad to be a project",
    "папка слишком широкая для проекта"],
  "hub.code.root_nested": ["the folder is inside another project or holds one",
    "папка лежит внутри другого проекта или содержит его"],
  "hub.code.root_in_login_home": ["the folder is inside a harness's login home",
    "папка лежит в домашней папке входа харнесса"],
  "hub.code.root_already_registered": ["the folder is already in the list", "эта папка уже в списке"],
  "hub.code.root_path_too_long": ["the folder's path is too long", "путь к папке слишком длинный"],
  "hub.code.conduct_home_invalid": ["the hub's own folder is inside a project",
    "собственная папка hub лежит внутри проекта"],
  "hub.code.project_not_repo_root": ["the folder is inside a git repository but is not its root",
    "папка внутри git-репозитория, но не его корень"],
  "hub.code.tracks_product_dir": ["git tracks a folder the product keeps its own files in",
    "git отслеживает папку, где продукт хранит свои файлы"],
  "hub.code.legacy_writers_must_stop": ["stop the other conduct up and agents that work in this folder",
    "остановите другие conduct up и агентов, которые работают в этой папке"],
  "hub.code.unsettled_action": ["an action in this folder has not settled",
    "в папке есть незавершённое действие"],
  "hub.code.activation_present": ["the project is already activated", "проект уже активирован"],
  "hub.code.inventory_bound": ["the folder holds too many files to take over",
    "в папке слишком много файлов, чтобы принять её"],
  "hub.code.git_exclude_failed": ["the ignore block of git could not be written",
    "не удалось записать блок исключений git"],
  "hub.code.ports_exhausted": ["no free port is left for a project",
    "свободных портов для проекта не осталось"],
  "hub.code.stop_uncertain": ["the stop is not confirmed", "остановка не подтверждена"],
  "hub.code.recovery_refused": ["the recovery was refused", "восстановление отклонено"],
  "hub.code.login_recovery_required": ["the login needs recovery", "вход требует восстановления"],
  "hub.code.login_owner_busy": ["the login is held by a running project",
    "вход держит работающий проект"],
  "hub.code.login_ownership_invalid": ["the login's ownership record is damaged",
    "запись владения входом повреждена"],
  "hub.code.login_context_required": ["the recovery needs the context of the harness login",
    "для восстановления нужен контекст входа харнесса"],
  "hub.code.subprocess_failed": ["a helper process ended without saying why",
    "вспомогательный процесс завершился без объяснения"],
});

export const HUB_LOCALES = Object.freeze(["en", "ru"]);
const TABLE = Object.freeze({...DESK_STATUS_COPY, ...HUB_COPY});

function parameters(text) {
  return [...new Set([...text.matchAll(/\{([a-z_]+)\}/g)].map((row) => row[1]))].sort();
}

/** The names of the values the message `key` takes, sorted (none for a key it does not have). */
export function paramsOf(key) {
  return Object.hasOwn(TABLE, key) ? parameters(TABLE[key][0]) : [];
}

/**
 * The message `key` in `locale`. A locale or a key the catalogue does not have, a value the message
 * does not take, a value it needs and did not get, or a value that is not a string, is an error:
 * a wrong call fails where it is made and never paints a bare key.
 */
export function hubText(locale, key, params = {}) {
  const index = HUB_LOCALES.indexOf(locale);
  if (index < 0 || !Object.hasOwn(TABLE, key)) throw new Error("Unknown hub locale or message key");
  const text = TABLE[key][index], expected = parameters(text);
  const plain = params !== null && typeof params === "object"
    && Object.getPrototypeOf(params) === Object.prototype;
  if (!plain || Object.keys(params).sort().join(",") !== expected.join(",")
      || expected.some((name) => typeof params[name] !== "string")) {
    throw new Error("Hub message parameters do not match their key");
  }
  return text.replace(/\{([a-z_]+)\}/g, (_match, name) => params[name]);
}

/** The clause for a code of the hub's closed lists; a code it has no word for says so, never itself. */
export function codeWords(locale, code) {
  const key = typeof code === "string" ? `hub.code.${code}` : "";
  return hubText(locale, Object.hasOwn(HUB_COPY, key) ? key : "hub.code_unknown");
}
