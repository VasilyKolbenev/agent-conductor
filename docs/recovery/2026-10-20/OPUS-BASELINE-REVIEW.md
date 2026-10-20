# Opus: стартовый разбор восстановленной рабочей копии

- Дата: 20 октября 2026.
- Исполнитель: Claude Code (вкладка Code приложения Claude Desktop), модель Opus 5.5
  (`claude-opus-5-5`). Реализация ограниченных задач — субагенты с моделью `sonnet`
  (Sonnet 5.5); анализ R1.2, R2, R3, R4 — субагенты с моделью `opus`.
- Задание: `CLAUDE-CODE-HANDOFF.md`, стартовое задание Opus.
- Код продукта в рамках этого разбора не менялся. Исправление R1.1 выполняется
  отдельной задачей Sonnet, отчёт — `tasks/R1.1-REPORT.md`.

## Исходное состояние

| Что | Значение |
| --- | --- |
| Каталог | `C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command` |
| HEAD | `4d0e3af669e783f248cf4c4230e805e76c19836a` («style(desk): the motion bench ends with one newline») |
| Ветка | `feature/v1-desk-integration`, совпадает с `origin/feature/v1-desk-integration` |
| Remote | `origin https://github.com/VasilyKolbenev/agent-conductor.git` (fetch/push) |
| `git status --short` | `?? AGENTS.md`, `?? CLAUDE.md`, `?? docs/recovery/` — только документы восстановления; отслеживаемые файлы не изменены |
| `git stash list` | пусто |
| Git identity | `user.name` и `user.email` в репозитории и глобально **не заданы**. Последние коммиты подписаны `Vasily Darsky`. Коммиты не создаются до решения владельца, какую identity использовать; придумывать её нельзя (`CONTINUATION-PLAN.md`, R0.1) |
| Окружение | `December-Command-Environment.ps1 -Quiet`: Python 3.12.14 (`.venv`), Git 2.53.0.windows.3, Node.js 24.19.0 — совпадает с `BASELINE.md` |
| Linux-окружение | WSL не установлен, Docker отсутствует. Проверка на POSIX локально невозможна |

Прочитаны: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.ru.md`, `docs/v1-v2-scope.md`,
`LOCAL-SETUP.md`, `BASELINE.md`, `CI-BASELINE-NOTES.md`, `CONTINUATION-PLAN.md`,
`TASK-REPORT-TEMPLATE.md`. `README.ru.md` и `docs/architecture.ru.md` — в той части,
которая нужна задачам; области R2/R3 читают агенты-аналитики.

## Что не повторялось и почему

Core baseline Codex (13 модулей, 309 passed / 35 skipped), browser smoke (15 + 4 passed)
и demo smoke выполнены на этом же ноутбуке, в этом же `.venv`, на том же HEAD.
С тех пор не менялись ни код, ни окружение, поэтому они не повторялись.
Старые CI-результаты не считаются проверкой этого окружения.

## Выполненные команды

Во всех командах сначала выполнялось
`. ...\December-Command-Environment.ps1 -Quiet`.

| # | Команда | Результат | Зачем |
| --- | --- | --- | --- |
| 1 | `git rev-parse HEAD; git branch --show-current; git remote -v; git status --short --branch; git log --oneline -8; git stash list` | см. таблицу выше | исходное состояние |
| 2 | `python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-r11a tests/test_adapter_boundary_launch.py tests/test_execution_boundary.py` | **124 passed**, 29,44 с, exit 0 | база до правки на Windows: `test_adapter_boundary_launch.py` не входил в baseline Codex |
| 3 | то же с `-p posix_sim` (плагин `C:\Users\Пользователь\Documents\Codex\work\r11sim\posix_sim.py`, `PYTHONPATH` на этот каталог) для `tests/test_adapter_boundary_launch.py::test_a_confined_adapter_over_the_shipped_runner_starts_no_task_child` | **1 failed**: `ModuleNotFoundError: import of conductor.command.adapters._winlaunch halted; None in sys.modules`, `process.py:485`, стек `harness_attempt.py:360 → process.py:485` | воспроизведение механизма CI-падения на Windows |
| 4 | `wsl.exe --list --verbose`; `Get-Command docker` | WSL не установлен; docker нет | можно ли проверить на POSIX локально |

Плагин имитации (вне репозитория) делает две вещи: подставляет `None` вместо
`conductor.command.adapters._winlaunch` в `sys.modules`, чтобы импорт не удавался,
как вне Windows, и заменяет `os` только в модуле `process` объектом с
`name == "posix"`. Это **имитация механизма**, а не доказательство поведения на POSIX.

## R1.1: разбор

### Цепочка вызовов

1. Тест `tests/test_adapter_boundary_launch.py:383-399` создаёт fake Grok Build
   поверх штатного `ProcessRunner` и вызывает `adapter.confine("win32")` на любой ОС.
   Docstring: раннер, вход которого принимает вызов, «вне Windows или без live owner»
   отказывает на входе, после печати версии; `except adapter.error` ожидает этот отказ.
2. `harness_attempt.py:203-215` `_attempt` → `_hold_boundary` (`:191-201`): платформа
   передана явно как `"win32"`, `require_boundary` проходит; `_road_covers` (`:159-166`)
   истинно, потому что `ProcessRunner.container_profile` принимает вызов
   (`boundary_entry.entry_takes_the_call`), а у fake-сборки есть каталог установки.
   Это ожидаемо: платформу предиката задаёт тест.
3. `_owned_attempt` (`:217-261`) создаёт home → `_spawn` (`:302-345`) →
   `_run_confined` (`:347-364`) → `self._runner.container_profile(**entry_call(mode, folders))`.
4. `process.py:473-489` `ProcessRunner.container_profile`: после проверки режима
   просмотра сразу `from . import _winlaunch` (`:485`).
5. `_winlaunch.py:16-17`: вне Windows модуль сам бросает
   `ImportError("Windows process creation is unavailable on this platform")`.
   Этот guard обязателен: его фиксирует `tests/test_adapter_module_graph.py:169-187`
   (`WINDOWS_ONLY`).
6. `_run_confined` ловит только `LAUNCH_REFUSALS = (ProcessRunnerError, OSError,
   OwnerRefused, ProfileRefused)` (`harness_attempt.py:49`). `ImportError` в этот
   набор не входит, поэтому проходит мимо `_spawn` (который превращает
   `ProcessRunnerError` в фиксированное `self.error`) и выходит из `execute`.

На Windows тот же тест доходит до `ProfileJournal.for_project` (`process_profile.py:103-107`):
без открытого owner — `ProfileRefused("profile_owner_required")`, это входит
в `LAUNCH_REFUSALS`, и тест получает `adapter.error`. Поэтому Windows CI зелёный,
а все четыре POSIX job красные.

Тест и docstring с обещанием «off Windows … refuses at the entry» добавлены в
`9162fdf` (14 октября) — «the provider door confines every harness for the host, and a
harness answers yes only to a runner whose entry can take the call». Импорт
`_winlaunch` в `container_profile` существует с `6ce0a1c`/`f6675ad` (1 октября).
Что POSIX CI падал на этом тесте с 14 октября, по более ранним запускам не проверялось.

### Где граница преобразования

Прецедент уже есть в том же классе: `ProcessRunner._launch` (`process.py:612-616`)
вне Windows отказывает `CommandSpecError("Windows boundary is unavailable on this
platform")` **до** импорта `_winlaunch`. Его фиксирует
`tests/test_execution_boundary.py:87-94`. У второго входа в нативный помощник,
`container_profile`, такой проверки нет — это и есть дефект.

| Вариант | Решение | Причина |
| --- | --- | --- |
| A. В `ProcessRunner.container_profile` после отказа режима просмотра и до импорта `_winlaunch`: `if os.name != "nt": raise CommandSpecError(<то же предложение>)` | **выбран** | Хост знает раннер, а не транспорт. Повторяет существующий отказ `_launch`. `CommandSpecError` ⊂ `ProcessRunnerError` ⊂ `LAUNCH_REFUSALS`, поэтому `_run_confined` → `_spawn` дают фиксированное `adapter.error`. До `container_profile` ничего не выдаётся, home удаляет `finally` в `_owned_attempt`. На Windows путь не меняется |
| B. Добавить `ImportError` в `LAUNCH_REFUSALS` | отклонён | Слишком широко: настоящая поломка импорта на Windows превратилась бы в обычный отказ «could not start» и спряталась |
| C. Ловить `ImportError` вокруг `from . import _winlaunch` | отклонён | Та же маскировка, плюс расхождение с явной проверкой платформы в `_launch` |
| D. Судить платформу в транспорте (`confine`/`_hold_boundary`) по реальному хосту | отклонён | Нарушает контракт `confine`: платформа «passed in, never read here, so a test names the platform it asks about» (`harness_attempt.py:130-136`) |
| E. Пропустить тест на POSIX | запрещён | Оставляет заявленный контракт непроверенным (`CONTINUATION-PLAN.md`, R1.1) |

Неохваченные соседние пути: `ProcessRunner.recover_container_profiles`
(`process.py:499-501`) тоже импортирует `_winlaunch` без проверки, но в `src/`
у него нет вызовов. `ownership_journals_cli.py:97-100` сам обрабатывает `ImportError`
своим отказом. `_policy_check` (`process.py:600-606`) вызывается только после
`_launch`, который вне Windows отказывает раньше. В R1.1 эти пути не меняются.

### Первое задание Sonnet (выдано)

- Вариант A в `process.py`; предложение отказа — одна модульная константа для
  `_launch` и `container_profile`; одна фраза в docstring `container_profile`.
- Не менять: `_winlaunch.py`, `LAUNCH_REFUSALS`, существующий тест.
- Новый свидетельский тест в `tests/test_execution_boundary.py` рядом с
  `test_the_predicate_agrees_with_the_runner_on_the_platform_the_test_runs_on`:
  вне Windows вход раннера отказывает `CommandSpecError`, в корне проекта ничего
  не создано, `_winlaunch` не загружен.
- Проверки: затронутые модули на Windows; имитация POSIX для целевого и нового
  теста; `git diff --stat`, `git status`.
- Что должен проверить Codex: отказ до запуска task child (`prompt_spawns == []`),
  cleanup (`_no_home_left`), сохранение Windows-защиты (guard `_winlaunch`,
  `WINDOWS_ONLY`, путь `ProfileRefused` на Windows), отсутствие ослабленных проверок.
- Окончательное подтверждение — POSIX jobs CI (Ubuntu 3.11/3.12, macOS 3.11/3.12).
  Для этого нужен push ветки, а это решение владельца.

## Параллельные аналитические задачи

Запущены одновременно с R1.1. Код продукта они не меняют; каждая пишет свой отчёт
в `docs/recovery/2026-10-20/tasks/`:

| ID | Отчёт | Содержание |
| --- | --- | --- |
| R1.2 | `R1.2-HOLDER-ANALYSIS.md` | порядок plan completion / holder release, контракт, попытка детерминированного воспроизведения |
| R2 | `R2-H5-ANALYSIS.md` | матрица login-home по harness, варианты, рекомендация; реализация только после решения Codex/владельца |
| R3 | `R3-DESK-MOTION-BRIEF.md` | жизненный цикл production render и готовое задание Sonnet |
| R4 | `R4-PUSH-PR-RECONCILIATION.md` | сверка spec/код/UI/тесты по трём вопросам Push/PR |

R1.3 (Windows 10055) и R1.4 (macOS setup timeout) не начаты: для них нужен новый
CI-прогон и отдельно спроектированный эксперимент.

## Пробелы

- POSIX: нет WSL/Docker, поэтому R1.1 подтверждает только CI после push.
- Полный core suite, browser gate в обоих порядках и матрица ОС на этой копии
  не запускались (это R5).
- Git identity не настроена, поэтому коммиты отложены.
- Ревью Codex по R1.1 и решения по R2/R4 ещё не получены.
