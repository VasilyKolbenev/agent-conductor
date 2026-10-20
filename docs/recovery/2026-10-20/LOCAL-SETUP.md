# Рабочая копия на новом ноутбуке

Восстановлено 20 октября 2026 года из `feature/v1-desk-integration`.
Полный Git clone содержит `.git`, удалённые ветки и историю. Исходная точка —
`4d0e3af669e783f248cf4c4230e805e76c19836a`.

## Где находится проект

Папка: `C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command`.
Для нового чата Codex или Claude Code выбирайте именно эту папку как корень проекта.
Файлы `AGENTS.md` и `CLAUDE.md` направляют обоих помощников к текущему плану.

Рядом с папкой находятся:

- `Open-December-Command.cmd` — открыть PowerShell с Git, Node.js и Python проекта в PATH.
- `Start-December-Command-Demo.cmd` — запустить демо; открыть адрес из терминала, остановить через Ctrl+C.
- `December-Command-Environment.ps1` — подготовка окружения только для текущего процесса.
- `Start-December-Command-Demo.ps1` — запуск демо с необязательным параметром `-Port`.

CMD-файлы задают `RemoteSigned` только для запускаемого PowerShell. Системная
политика исполнения и постоянный PATH не изменялись.

## Установленное окружение

Используются Python 3.12.14, Git 2.53.0.windows.3 и Node.js 24.19.0 из локального
набора инструментов Codex. В `.venv` установлен пакет `agent-conductor` в editable-режиме,
extras `dev,browser` и `build`. Правки `src/` доступны без переустановки.
Точные версии пакетов записаны в `baseline-dependencies.txt`.

Chromium Playwright установлен в `.venv/playwright-browsers`; путь задаёт
скрипт окружения. Временные файлы находятся вне Git-копии в
`Documents\Codex\work`; это также избегает недоступной временной папки sandbox.

Окружение зависит от базового Python и инструментов в
`%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies`.
Это проверенная установка на данном ноутбуке, а не переносимая `.venv`.
Если набор Codex будет удалён, установите Python 3.11+ и Git обычным способом,
пересоздайте `.venv` по `CONTRIBUTING.ru.md` и обновите пути в скрипте окружения.

## Команды в подготовленном терминале

```powershell
git status
python -m conductor --help
conduct demo
```

У `conduct` нет параметра `--version`. Версию можно прочитать так:

```powershell
python -c "import conductor; print(conductor.__version__)"
```

Демо работает на `127.0.0.1:7777`, использует временные fixture и не требует
аккаунтов или платных модельных вызовов. Если порт занят:

```powershell
conduct demo --port 7778
```

Управляемые продуктом настоящие проекты и профиль провайдеров ещё не
настраивались. Для них есть `docs/first-run-v1.md`. Восстановление исходников
не означает восстановление аккаунтов Claude Code или других провайдеров.

## Тесты и временные пути

Запускайте pytest с коротким `--basetemp`, не длиннее 26 символов: например
`C:\Users\Пользователь\pt-<n>` с одной цифрой вместо `<n>` (сам профиль занимает 21 символ).
Измерено: `tests/test_ownership_journals_cli.py` при 26 и 27 символах даёт 28 passed, при 28 —
9 ошибок. Предел задаёт `tests/test_hub_clone_restart.py`: он создаёт 53 каталога `hclone<k>`, и
при двузначном `k` суффикс на символ длиннее. При 27 символах — 43 ошибки, при 26 — 57 passed.

Корень проектов в тестах hub — это basetemp плюс `\hclone<k>\personal\ConductProjects`, то есть
ещё 33 символа (34, когда `<k>` двузначное). Продукт на Windows отказывает с
`windows_path_too_long`, если корень проектов длиннее 60 единиц UTF-16
(`src/conductor/hub/project_targets.py`, `admit_home`). Поэтому длинный basetemp, например внутри
`Documents\Codex\work\...`, даёт `windows_path_too_long` при подготовке тестов hub. Это контракт
продукта, а не дефект. CI обходит его коротким `--basetemp` (`.github/workflows/ci.yml`).

Кириллица в basetemp допустима: нативные тесты пишут `.ps1` с BOM (`tests/_ps1.py`).

## Куда смотреть дальше

1. `BASELINE.md` — что реально проверено на этом ноутбуке.
2. `CI-BASELINE-NOTES.md` — конкретные старые падения CI и первичные источники.
3. `CONTINUATION-PLAN.md` — очередь работ, ответственные и критерии готовности.
4. `CLAUDE-CODE-HANDOFF.md` — готовое стартовое задание Claude Code.
5. `RECOVERED-CONTEXT.txt` — восстановленные следы решений из сообщений коммитов.

Исходные большие архивы сохранены рядом в `recovery-2026-10-20` и общем
`December-Command-recovery-2026-10-20.zip`. В обычный Git-коммит их включать не нужно.
