# Отчёт по задаче: S-H5-D (H5-V1). Вход по подписке внутри изоляции: честный отказ и один предикат

- Исполнитель: Claude Code / Sonnet 5.5. Решение владельца: H5-V1 от 21.10.2026
  (`OPEN-DECISIONS.md`: в V1 настоящие задачи только по API-ключу; схема B после V1). Задание:
  `tasks/H5-V1-DESIGN.md`, раздел 4 (вариант D из `tasks/R2-H5-ANALYSIS.md`). Ревью Codex: ожидает.
  Коммита нет.
- Исходный commit и ветка: `a8e6baa`, `recovery/2026-10-20`. Задание писалось по `edd79d1`/`a8e6baa`;
  между `edd79d1` и `a8e6baa` изменилась только документация владельца, код и тесты те же.
- Состояние рабочей копии до изменений: чисто, кроме `?? docs/recovery/2026-10-20/tasks/H5-V1-DESIGN.md`
  (файл задания). Все 19 «старых» строк правок из `apply_to_copy.py` перед работой найдены в
  репозитории ровно по одному разу (сухой прогон по `EDITS`, без записи), расхождений нет.
- Цель и наблюдаемое ожидаемое поведение: подписка внутри isolation честно отказывает. Двери плана,
  отказ до claim, spawn и checker отвечают одним предикатом `AttemptLaunch._login_road_covered()`;
  `LOGIN_LOAN_OPEN = True` не открывает ничего; квитанция называет причину (вход по подписке) только
  когда это единственная недостающая причина; те же слова есть в `conduct providers`, экране
  «Агенты» и мастере desk. Путь по API-ключу не менялся. Значение `LOGIN_LOAN_OPEN`, логика
  `FolderLoans.targets`, `api_refusals.py`, коды и конверт отказов не менялись.

## Изменения

Итого 16 изменённых файлов (+144 / −30) и 1 новый (`tests/test_subscription_road_boundary.py`,
246 строк). Правки кода применены точно по `apply_to_copy.py`; после применения все 16 файлов и новый
тест побайтно совпали (SHA-256) с `h5v1-design\copy\` из дизайна.

| Файл | Что изменено |
| --- | --- |
| `src/conductor/command/adapters/harness_attempt.py` | Клауза подписки получила имя `_login_road_covered()` с решением H5-V1 в docstring; остальное стало `_launch_covers(mode)`; `_road_covers` = оба. `_boundary_refusal` выбирает фразу квитанции: о подписке только если вход единственный недостающий факт. Правлен docstring `boundary_provided` |
| `src/conductor/command/adapters/harness_profile.py` | Новая функция `subscription_boundary_detail(tool)` (additive, прежняя `boundary_detail` не тронута) |
| `src/conductor/command/failure_reasons.py` | Строка слов runtime для новой фразы |
| `src/conductor/command/adapters/process_boundary.py` | Только комментарий `LOGIN_LOAN_OPEN` и docstrings `login_loan_provided`, `AttemptFolders` (значение флага не менялось) |
| `src/conductor/command/adapters/process_loans.py` | Только docstring модуля |
| `src/conductor/provider_setup.py` | Две строки в `_ask_login` под выбором способа входа |
| `src/conductor/panel/desk-wizard-prep.js`, `desk-wizard-prepare-view.js`, `desk-wizard-copy.js` | Причина отказа берётся из `detail.reason`, иначе из `detail.sandbox`; таблица `ROUTES`; фраза `wizard.chain.boundary` (EN, RU) |
| `src/conductor/panel/studio-agents-copy.js`, `studio-people.js` | Текст строки «Подписка»: в V1 служит только для чтения квот |
| `tests/test_subscription_road_boundary.py` (новый, 36 тестов) | Требования (а)–(г): флаг ничего не открывает, отказ до любого побочного эффекта, API-key road покрыт, причина названа |
| `tests/test_adapter_boundary_launch.py`, `tests/test_provider_setup_login.py`, `tests/test_studio_agents_i18n.py`, `tests/test_desk_wizard_prepare.py`, `browser_tests/test_desk_wizard_prepare.py` | Ожидание новой фразы квитанции, строки CLI, текст «Агентов», модельный и browser-тест desk |

Не тронуты: `api_refusals.py`, `tests/test_command_line_cap.py`, документация владельца, git-состояние
(коммитов, push, stash, checkout, reset, правок git config не было).

## Проверки

Каждая команда начиналась с `. ...\December-Command-Environment.ps1 -Quiet`. Среда: Windows 11,
Python 3.12.14 (`.venv`), node и Chromium из окружения. Никаких настоящих провайдеров, аккаунтов,
ключей и сети. Ограничение sandbox: нативные AppContainer-файлы запускались по одному на процесс.
Логи лежат в `C:\Users\Пользователь\Documents\Codex\work\h5v1-s\`.

| Команда | Результат | Что доказывает |
| --- | --- | --- |
| Красная фаза: новый файл + правки тестов + только функция `subscription_boundary_detail`; `tests/test_subscription_road_boundary.py test_adapter_boundary_launch.py test_provider_setup_login.py test_studio_agents_i18n.py test_desk_wizard_prepare.py` (`red-phase-python.log`) | **17 failed**, 144 passed, 279.93 s | Тесты красные до кода |
| Красная фаза, browser: `browser_tests/test_desk_wizard_prepare.py -k boundary` (`red-phase-browser.log`) | **2 failed** (`Unknown interface locale or message key`: ключа `wizard.chain.boundary` ещё нет), 42 deselected | Итого красных **19**, ровно по разделу 3.1 дизайна |
| Основной не-нативный прогон, один процесс (24 файла из раздела 4.4.1, включая новый, `test_desk_docs_map`, `test_server_panel_assets`, `test_command_line_cap`; `green-main.log`) | **756 passed, 2 skipped**, 304.23 s | Зелёная фаза; все 19 бывших красных зелёные, регрессий нет |
| Пропуски в нём (`-rs`, отдельным запуском двух тестов) | `test_execution_boundary.py:114` (запись входит в журнал на этой платформе, `test_container_view_mode`); `test_server_panel_assets.py:710` (в окружении нет `hatchling.builders.wheel`) | Оба пропуска окружения, не связаны с H5 |
| `tests/test_subscription_road_boundary.py tests/test_command_line_cap.py` | **187 passed** (из них новый файл 36) | Новый файл сам по себе; лимит 100 символов держится |
| Аренда login-home, один процесс: `test_process_loans*.py` (4 файла), `test_login_leased_home.py` (`green-loans.log`) | **92 passed**, 3.43 s | Docstrings не ломают аренду |
| Нативный, отдельным процессом: `tests/test_process_login_closed.py` | **8 passed** | Закрытый gate runner остаётся закрытым (его же убивает M3b) |
| Нативные, по одному на процесс: `test_process_login_refusals.py`, `test_process_login_grant.py` | **39 passed**; **18 passed** | Прочие нативные тесты аренды целы |
| Browser: `browser_tests/test_desk_wizard_prepare.py -k "boundary or refusal_stops"` | **4 passed** | Фраза desk, `runs_written == 0` |
| Browser: весь `browser_tests/test_desk_wizard_prepare.py` | **44 passed**, 30.09 s | Смена `refusalNote` не задела прочие отказы мастера |
| Дополнительно (смежные упоминания boundary/receipt/login): `test_studio_completeness`, `test_login_lease_refusal_words`, `test_login_lease_refusal_reason`, `test_correction_frame_integers`, `test_command_input_binding`, `test_command_artifact_flow`, `test_check_road_limits`, `test_command_provider_contract`, `test_command_adapters`, `test_harness_login_method`, `test_harness_login_lifetime`, `test_harness_login_leaks` | **376 passed**, 174.37 s | Другие потребители фраз и login-кода не затронуты |
| Скрипт лимитов (вне репозитория) по всем изменённым файлам | Файлы ≤ 800 строк (максимум `studio-people.js`, 749); в новом файле и в `harness_attempt.py` строк > 100 нет; один `\n` в конце, хвостовых пробелов и `\r` нет; строк > 100 в `desk-wizard-copy.js` 7 → 7, в `studio-people.js` 5 → 5 | Лимиты соблюдены |
| `git diff --stat` | 16 файлов, 144 insertions(+), 30 deletions(-), плюс новый файл | Правки только названные в задании |

Полный suite и gate не запускались (по условию). Свои каталоги `pt-*` удалены; `pt-f`, `pt-n3`, `pt-o2`
в `C:\Users\Пользователь\` чужие, не трогал.

### Мутанты (на копии вне репозитория)

Копия `C:\Users\Пользователь\Documents\Codex\work\h5v1-s\` (`src`, `tests`, `pyproject.toml` после
правок), `PYTHONPATH=<копия>\src` (импорт из копии подтверждён печатью `conductor.__file__`).
Перед мутантами в копии зелёные базовые прогоны всех пяти наборов (`mutants-baseline.log`). Файл
восстанавливается после каждого мутанта. Репозиторий не мутировался. Лог: `mutants-all.log`,
`mutants-old-only.log`.

| Мутант | Новые и прежние тесты | Ожидалось | Факт |
| --- | --- | --- | --- |
| M1 `_login_road_covered` всегда True | новый файл + прежние | убит | **убит** |
| M2 `_login_road_covered` = прежнее или `login_loan_provided()` | новый файл + прежние | убит | **убит** |
| M3 `LOGIN_LOAN_OPEN = True` в исходнике | новый файл | выживает (дорога от флага не зависит) | **выжил** |
| M3b то же | `test_process_login_closed.py` | убит | **убит** |
| M4 `_hold_boundary` без вопроса о дороге | новый файл | убит | **убит** |
| M5 dispatch без `_boundary_refusal` | новый файл | убит | **убит** |
| M6 квитанция никогда не называет вход | новый файл | убит | **убит** |
| M7 квитанция называет вход при любой причине | новый файл | убит | **убит** |
| M8 `AttemptFolders` транспорта получает `login` | новый файл | убит | **убит** |
| M9 дверь (`base.py`) импортирует `login_loan_provided` | новый файл | убит | **убит** |
| M10 нет строки в `failure_reasons` | новый файл | убит | **убит** |
| M11 `conduct providers` молчит | `test_provider_setup_login.py` | убит | **убит** |
| M12 desk теряет `detail.sandbox` | `test_desk_wizard_prepare.py` | убит | **убит** |

Только прежние тесты (`test_adapter_boundary_launch`, `test_execution_boundary_refusal`,
`test_production_door_boundary`, `test_adapter_boundary_roads`, `test_execution_boundary`,
`test_failure_reasons`, `test_login_leased_home`):

| Мутант | Факт |
| --- | --- |
| M2 | **выжил** |
| M9 | **выжил** |
| M4, M5, M8 | убиты (для сравнения) |

M2 и M9 выживают без нового файла: поэтому он нужен. M3 выживает на новых тестах намеренно:
это доказательство, что дорога не зависит от флага.

## Что в CAPPED

Для `tests/test_command_line_cap.py` (файл не редактировался; нужно добавить отдельно):
`"tests/test_subscription_road_boundary.py"`. Файл новый, 246 строк, самая длинная строка не больше
100 (проверено скриптом). `harness_attempt.py` и `tests/test_adapter_boundary_launch.py` уже в
`CAPPED`; после правок строк длиннее 100 в них нет. Остальные изменённые Python-файлы в `CAPPED` не
входят. Строк длиннее 100 в `studio-agents-copy.js` стало 51 вместо 49: две новые строки `agents.auth_subscription`
(EN, RU) написаны одной строкой, как предписано заданием и как остальные строки этого файла.

## Правки после ревью Opus

После ревью Opus в `tests/test_subscription_road_boundary.py` добавлены тесты review-дороги и дороги
независимого checker: каждая сама задаёт вопрос о дороге, и отказ проверен через runtime, а не
только вызовом помощника под ней.

- **Новые тесты.** Подписочный review через runtime отказывает до claim, home, login lease и spawn
  (`test_a_subscription_review_is_refused_before_any_claim_home_lease_or_spawn`, ×2 по GATE);
  подписочный checker через runtime даёт `VERIFICATION_FAILED` с `CHECKER_BOUNDARY_UNAVAILABLE` без
  claim, evidence и lease
  (`test_a_subscription_checker_is_refused_through_the_runtime_before_any_claim_home_or_lease`,
  ×2 по GATE). Контрольные тесты
  `test_an_api_key_{review,checker}_through_the_runtime_runs_inside_the_boundary_whatever_the_gate`:
  тот же шаг по API-ключу не отказывает. Вначале в них GATE был
  зафиксирован `True`, хотя имя обещало «whatever the gate»; теперь оба параметризованы по `GATE`
  (+2 теста), имя верно.
- **Размер файла.** Теперь 44 теста и 391 физическая строка (в таблице выше — состояние до ревью:
  36 тестов; число строк там посчитано без пустых);
  самая длинная строка 99.
- **Мутанты ревью** (на копии вне репозитория, номера этого раунда свои, не совпадают с таблицей
  выше; в этом проходе заново не гонялись, цифры по данным ревью):

  | Мутант | Красных |
  | --- | --- |
  | M1: review-дорога без вопроса о дороге (`artifact_transport.py:340-342`) | 2 |
  | M2: checker-дорога без `_hold_checker_boundary` (`artifact_transport.py:771`) | 2 |
  | M3, M4: вопрос о дороге стоит после preflight | красные |
  | M5: `LOGIN_LOAN_OPEN` открывает дорогу подписки | 14 |

- **Прогоны этого прохода** (`pt-*` удалён): `tests/test_subscription_road_boundary.py` отдельно
  **44 passed**; вместе с `tests/test_adapter_boundary_launch.py` и
  `tests/test_execution_boundary_refusal.py` **184 passed**, 152 s (по ревью до параметризации
  контрольных тестов было 182).
- **CAPPED.** `tests/test_subscription_road_boundary.py` в `CAPPED` вносит оркестратор:
  `tests/test_command_line_cap.py` я не редактировал. Строк длиннее 100 в файле нет, так что запись
  пройдёт.

## Правки документации владельца (делает другой workflow, я не трогал)

- `docs/first-run-v1.md` и `.en.md`, раздел «Где задачи исполняются в этой сборке»:
  - фразу «Можно ли сделать вход по подписке безопасным… пока не решено» заменить на: «Решение
    владельца H5-V1 (21.10.2026): в V1 задачи исполняются только по API-ключу; вход по подписке
    внутри изоляции после V1; подписка в V1 нужна только для чтения квот»;
  - в таблицу «Шаг отказывает» добавить фразу desk (`wizard.chain.boundary`, RU и EN) и фразу
    квитанции о подписке: «this {tool} connection signs in with a subscription, and in this
    version a task runs inside the execution boundary only with an API key, so no task was
    spawned»;
  - в таблице каталога (Claude Code, Codex, Kimi, Grok, «вход по подписке») оговорить: для задач в
    V1 нужен API-ключ (имя переменной в `env_allow`); работу Grok и Kimi по API-ключу с настоящим
    вендором продукт не проверял (R5 в пользовательском документе не упоминать);
  - в шагах `conduct providers` отразить две новые строки и рекомендовать пункт 2.
- `README.md` и `README.ru.md` (абзац около 105–106): «does not yet run tasks» заменить на «in V1
  does not run tasks (decision H5-V1); after V1 …».
- `docs/owner-acceptance.md:231-232`: «the execution boundary does not yet carry that road» заменить
  ссылкой на H5-V1; ожидаемая фраза в desk: `wizard.chain.boundary`.
- `docs/release-smoke.md` (около 465): рядом с HTTP-фразой двери добавить ожидаемую фразу desk и
  текст «Агентов» для подписки.
- `R5-PLAN.md` §3.3 п. 1: H5-V1 решено, реализация S-H5-D (этот отчёт).
- `OPEN-DECISIONS.md`: H5-C, вопрос 6 (текст отказа) закрыт реализацией H5-V1 — новые фразы
  `subscription_boundary_detail` и `wizard.chain.boundary`, без нового кода отказа и поля API —
  и ждёт утверждения Codex; открыто: S-H5-D2
  (поле `reason` в отказе двери плана), удалять ли аренду `login` после V1, где держать копию
  credentials в схеме B.
- `CONTRIBUTING*`: правок не требуется.

## Не проверено

- Полный suite и gate не запускались. Значение: общая регрессия вне перечисленных прогонов (около 1330 тестов
  суммарно) не исключена; перед коммитом нужен обычный gate.
- macOS, Linux и CI не запускались. Ветка «без boundary на платформе» проверена в тестах через
  `platform="linux"` и `"darwin"` на фальшивом runner на Windows.
- Настоящие vendor CLI и настоящий вход по подписке не запускались; весь трафик фальшивый. Нативная
  часть проверена только тестами аренды (закрытый gate).
- `test_server_panel_assets::test_the_built_wheel_...` пропущен: в окружении нет `hatchling`. Значение:
  состав wheel с изменёнными JS в этом прогоне не проверен (панельные файлы не добавлялись и не
  переименовывались).
- Текст desk из трёх условий (Windows, API-ключ, папка `harnesses`) не проверялся глазами владельца;
  решение о нужности S-H5-D2 зависит от hands-on.

## Для Codex (из раздела 6 задания, без изменений)

1. Утвердить слово «subscription» в квитанции: новая фраза отдельная и additive, называется режим
   входа из конфигурации (не путь и не аккаунт), только когда это единственная причина.
2. S-H5-D2 (поле `reason` в отказе двери плана): в V1 не делалось; рекомендация дизайна: не делать.
3. Побочная находка: `isolation_facts.no_operating_system_boundary` после R5 на Windows неверна
   (задача идёт в AppContainer); строка входит в замороженный контракт, нужна отдельная additive-правка.
4. Остаточный пробел desk: если harness перевели на подписку после подготовки run, preview отказывает
   `contract_invalid`, Confirm `authorization_refused`, мастер говорит про отсутствие владельца (неверное
   объяснение). Существовал до H5.

## Ревью Codex

Ожидает.

## Передача

- Итоговый commit, если создан: нет (по условию).
- `git status`: ветка `recovery/2026-10-20`, HEAD `a8e6baa`. `M` на 16 файлах из таблицы выше;
  `?? tests/test_subscription_road_boundary.py`; `?? docs/recovery/2026-10-20/tasks/H5-V1-DESIGN.md`
  (файл задания) и этот отчёт.
- Обновлённые документы: только этот отчёт. Документацию владельца не менял (список выше).
- Следующий конкретный шаг: Codex независимо читает diff; добавляет
  `tests/test_subscription_road_boundary.py` в `CAPPED`; прогоняет gate; коммитит код и тесты
  отдельным коммитом; другой workflow вносит правки документации из списка выше.
