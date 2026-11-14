# Проверки восстановленной рабочей копии

Дата: 20 октября 2026. Это фактический локальный результат на новом ноутбуке.
Старый CI разобран отдельно в [CI-BASELINE-NOTES.md](CI-BASELINE-NOTES.md).

## Git и окружение

- Полный clone `https://github.com/VasilyKolbenev/agent-conductor`.
- Ветка `feature/v1-desk-integration` отслеживает одноимённую ветку `origin`.
- HEAD: `4d0e3af669e783f248cf4c4230e805e76c19836a`.
- История не shallow: от HEAD достижимы 1470 коммитов; получены все пять удалённых веток.
- `git fsck --full` завершился успешно.
- `git diff --exit-code` подтвердил отсутствие изменений отслеживаемых файлов продукта.
- Новые `AGENTS.md`, `CLAUDE.md` и `docs/recovery/2026-10-20/` пока не закоммичены. Коммиты и push при восстановлении не выполнялись.
- Python 3.12.14, Git 2.53.0.windows.3, Node.js 24.19.0.
- `.venv`: editable `agent-conductor==0.1.0`, extras `dev,browser`, пакет `build`; `pip check` успешен.
- Chromium Playwright установлен: версия 156.0.8078.4, build 1248; также headless shell, ffmpeg и winldd.
- Версии Python-зависимостей записаны в [baseline-dependencies.txt](baseline-dependencies.txt).

Инструкции запуска и зависимость от локального набора инструментов Codex:
[LOCAL-SETUP.md](LOCAL-SETUP.md). Команда `claude` в подготовленном PATH не найдена;
установка Claude Code, вход в аккаунт и выбор модели ещё не проверены.

## Что прошло

| Проверка | Результат |
| --- | --- |
| Импорт пакета, версия и CLI help | Пакет загружается из этой рабочей копии, версия 0.1.0 |
| 13 выбранных core-модулей | **309 passed, 35 skipped**, 223,60 с, exit 0 |
| Весь `browser_tests/test_studio_rendered.py` | **15 passed**, 20,22 с |
| Три выбранные функции Desk shell, четыре случая с параметрами | **4 passed**, 2,12 с |
| Настоящий CLI demo + Chromium | HTTP 200, пять вкладок, Runs / Decisions / Overview отображаются, ошибок JavaScript нет |
| Полная резервная копия Git | `December-Command-history-2026-10-20.bundle`, 9 852 162 байта; `git bundle verify` успешен |

Core проверял demo, графы модулей adapters/Studio, модель и исходники Desk motion,
execution boundary и отказы, Desk accept/publish transport, Git wizard,
first-commit/first-replace, область process loans и production door boundary.

35 пропусков имеют конкретные причины:

- 31: не задан `CONDUCT_OLD_GIT`; проверка совместимости со старым Git остаётся открытой.
- 2: Windows не предоставляет используемую проверкой POSIX-семантику execute bit.
- 2: для создания symlink не хватило привилегии Windows, WinError 1314.

Первый запуск этих же core-модулей внутри sandbox дал 65 failures и 27 setup
errors: `os.link` получал WinError 5, `ssh-keygen` не мог сохранить публичный
ключ. Повторный запуск в обычном локальном окружении, без изменения продукта,
дал результат 309/35 выше. Это подтверждает зависимость этих сбоев от окружения
запуска, но не доказывает конкретный механизм ограничения доступа.

Browser smoke выполнялся отдельным процессом pytest для каждого модуля.
Точные имена трёх выбранных функций Desk и все аргументы сохранены в JSON
команд. Demo использовал временные fixture; реальные provider-задачи не
запускались. После проверки временный сервер остановлен.

## Где доказательства

В соседней с репозиторием папке `December-Command-evidence`:

- `local-baseline/core-native-command.json`, `core-native-result.json`,
  `core-native.log`, `core-native.xml` — успешный core baseline.
- `local-baseline/studio-browser-*` и `desk-browser-*` — браузерные проверки.
- `local-baseline/core-*` — первоначальный неуспешный запуск в sandbox.
- `local-sandbox-findings.txt` — группировка первоначальных ошибок.
- `demo-smoke.json`, `demo.png` и логи — настоящий запуск демо.
- `ci-logs/job-<ID>.log` — четыре исходных POSIX unit-лога старого CI.

Каждый `*-command.json` содержит executable, cwd и массив аргументов, каждый
`*-result.json` — код завершения. Повторять проверки следует только после
относящихся к ним изменений или для расследования конкретного вопроса.

## Что ещё не подтверждено

- Полный core suite, оба порядка полного browser gate и вся матрица ОС/Python
  на этой восстановленной копии не выполнялись.
- Новый release wheel, его установка в чистое окружение и release smoke
  не выполнялись; старый успешный CI wheel не заменяет эту проверку.
- H5 login-home, production-подключение Desk motion и старые CI failures
  остаются задачами плана. Локальный smoke не объявляет их исправленными.
- Нет проверки настоящей задачи Claude Code, аккаунтов провайдеров и owner acceptance.
- Не восстановлены недоступные старые локальные чаты и возможные незапушенные
  изменения с SSD. Основание рабочей копии — подтверждённая GitHub-ветка.

Рабочая среда восстановлена и проверена в указанном объёме. Следующая задача —
R1.1 из [CONTINUATION-PLAN.md](CONTINUATION-PLAN.md): штатный платформенный отказ
confined adapter на POSIX.
