Итог: локально проверено (UTF-8 и cp1251) | код, тесты и документы I3 — `6cc2f45`, правки
документов по проходу владельца — следующий docs-коммит ведущего | целевые 25 файлов у ведущего:
1095 passed, 0 failed в обеих кодировках; полный core — один раз на финальном коммите CLOSE-TASK |
ниже — отчёт исполнителя; рабочая копия начата над `c092dfb` (код I2b `2ec3bca`, задание I3
`758a159`; к концу работы HEAD — `f6dbd65`, docs-коммит Codex, `src` и `tests` не менял) | полный
core UTF-8 18612 passed, 1 failed, 409 skipped (красный — моя строка в 101 знак в
`test_subscription_road_boundary.py`, исправлена, повтор 345 passed); cp1251 18613 passed, 0
failed, 409 skipped (красный cp1251 первой итерации `test_view_mode…full_prepare_flow` здесь
зелёный, причина не установлена); нативные 91 passed в обеих; browser gate 12 + 8 UI-файлов 218 +
115 passed в обеих; красная фаза правок ревью 22 failed, 52 passed; мутанты ревью 9 красные, четыре
из них выживают на старых тестах (первая итерация: 136 failed, 718 passed, 37 красные) | ревью
Opus: 23 находки, 20 исправлены, 1 частично (Л1.2), 2 вопроса ведущему (Л1.11, Л2.3) | 16
отклонений (15 ждут ведущего), 13 открытых вопросов | следующий шаг: commit ведущего (три новых
теста в `CAPPED`), затем `H5-SUB-R5-I2B-CLOSE-TASK` (Q13, Q11, wheel и защищённая установка, A2,
`run-ready.json`).

# Отчёт по задаче: H5-SUB-R5 / I3. Тексты, UI, документы владельца и доводка I2b

- Исполнитель: Claude Code / Sonnet 5.5 (`claude-sonnet-5-5`), вторая сессия I3: продолжение с
  незакоммиченных правок исполнителя, остановленного владельцем 24.10 около 01:00. Не коммитил,
  `CAPPED` не трогал, ничего не пушил, живых CLI не запускал, настоящие
  `%USERPROFILE%\DecemberCommand\{logins,harnesses,h5-a}` не читал и не менял.
- Исходный commit и ветка: `recovery/2026-10-20`, HEAD `c092dfb`. По `src`, `tests` и
  `pyproject.toml` он равен `758a159`: `git diff 758a159 HEAD --stat -- src tests pyproject.toml`
  пуст, `git diff --name-only 758a159 HEAD` называет только
  `docs/recovery/2026-10-20/HANDOFF-2026-10-23.md`. В ходе работы появился docs-коммит `f6dbd65`
  (26.10 10:35: решения Codex по I2b, D13, Р7–Р10 и `H5-SUB-R5-I2B-CLOSE-TASK`; `src`, `tests` и
  мои файлы не менял, runbook B не трогал); его решения прочитаны перед сдачей и учтены в вопросах
  и «Передаче». Задание I3 — `758a159`, прочитано целиком;
  прочитаны также отчёт I2b (раздел «Передача», вопросы 2 и 12, «Проверка ведущего»: f1, f2, f5),
  раздел I3 задания H5-SUB-R5, `docs/v1-v2-scope.md`, `R5-CLAUDE-B-RUNBOOK.md`, отчёт П0–П5 A,
  `WORKING-STANDARD.md`.
- Состояние рабочей копии до изменений: `git status --short` — 60 записей (57 `M`, 3 `??`),
  `git diff HEAD --stat` — 57 файлов, +1235/−320. Это правки остановленного исполнителя: `src`
  (14 файлов Python, 9 JS), `tests` (24 изменённых файла: 20 тестов, помощник
  `alpha1_live_extensions.py`, три файла фикстур; 3 новых теста), документы (README,
  `first-run-v1`, `owner-acceptance`, `release-smoke`, спецификация контракта, два runbook; всего
  10). Снимок вне
  репозитория: `Documents\Codex\work\i3-partial\` (diff, status, три новых теста; новые тесты
  побайтно равны файлам рабочей копии на старте).
- Цель и наблюдаемое ожидаемое поведение: владелец по документам и подсказкам продукта ставит
  строку `claude-code` или `codex` с подписочным входом в `…\DecemberCommand\logins\<id>`, видит в
  Studio (Agents) и в Desk (шаг подготовки), что задача идёт внутри изоляции на relay-копии входа,
  получает отказ до запуска при неверной папке входа и понимает каждый отказ по тексту. Grok Build и
  Kimi Code по-прежнему отказывают подписочной задаче с честным текстом «вход по подписке для этого
  harness внутри изоляции пока не поддержан».

## Чужие правки

- Исходное состояние: правки остановленного исполнителя (60 записей, выше). Их скрипты и логи
  (`Documents\Codex\work\i3\`: `limits.py`, `mutate_i3.py`, `run_chunk.ps1`, `run_red.ps1`, логи
  прогонов `run-u*`, `run-d*`, `red-q*`) прочитаны как образец и не приняты как доказательство: ни
  один его результат в этом отчёте не используется, все прогоны сняты заново (скрипты и логи —
  `Documents\Codex\work\i3c\`). Его красная фаза не была закончена (копия базы без `docs`, сбор
  тестов падал).
- Судьба: все 60 записей оставлены как исходное состояние, ничего не откатывалось целиком. Мои
  правки поверх них перечислены в разделе «Изменения» (1 файл `src`, 3 файла `tests`, 2 файла
  `browser_tests`, 1 документ); сверка каждого пункта задания — ниже. Правок других агентов в `src`,
  `tests`, `pyproject.toml` нет ни в рабочей копии, ни в коммитах над `758a159`.

## Сверка: рабочая копия остановленного исполнителя и задание

Строки — по пунктам задания; «верно ли» — по чтению кода и по результатам прогонов этого отчёта.

| Пункт | Что уже сделано в рабочей копии (файл:строки) | Верно ли | Что не хватало / что сделано мной |
| --- | --- | --- | --- |
| п. 1 тексты H5-V1 | `adapters/harness_attempt.py:23-32,163-166,184-195,248-252`; `harness_profile.py:78-89`; `failure_reasons.py:91-92`; `process_boundary.py:36-45,52-56,105-108`; `process_loans.py:29-34`; `codex_cli.py:596-606,696-704`; `provider_setup.py:339-353,415-433`; `desk-wizard-copy.js:418-445`; `desk-wizard-prepare-view.js:14-20`; `studio-agents-copy.js:196-215`; `studio-people.js:82-108`; `isolation_facts.py:143-150` | Да, прочитано каждое место. Claude/Codex: поведение I2b (копия access-токена без refresh-токена в relay-home, каталог входа не выдаётся); Grok/Kimi: «not supported inside the execution boundary for this harness yet» (`harness_profile.py:88`, слова runtime `failure_reasons.py:92`) | Поиск по `src`, `tests`, `docs`, `browser_tests` (кроме `docs/recovery/**` — история) по фразам «only with an API key», «only reads quotas», «API key (not a subscription)», «in this version a task», «only 2 runs tasks», «не исполняет», «временной копией»: для Claude/Codex старых текстов не осталось, для Grok/Kimi честный текст на месте (`provider_setup.py:350-353`, `first-run-v1*.md`, `owner-acceptance*.md`, `README*.md`). Найдены два устаревших docstring тестов («H5-V1 … an API key»): `tests/test_desk_wizard_prepare.py:472-477`, `browser_tests/test_desk_wizard_prepare.py:337-341` — исправлены |
| п. 2 UI: факт `task_road` | `provider.py:110-113,649-702` (`TASK_ROADS`, `task_road`, `provider_projection(…, boundary=)`); `http_api.py:376-377`; `http_reads.py:45-48`; `studio_routes.py:121-122,617-629`; спецификация `docs/specs/2026-09-09-controls-current-contract.md:38,54,247,521,533`; фикстуры `tests/fixtures/wizard/*.json`, `alpha1_live_extensions.py` | Да для трёх маршрутов с массивом (workflows, runs, controls): ответ `registry.execution_boundary(id, "dispatch")`, закрытые слова `boundary`/`refused`, отказ по умолчанию `refused` | Маршрут `quotas` (`quota_views.py:41`, `quota_snapshot_view.py:110`) строит строки без registry и всегда говорит `refused`; шов `payload(contracts, now)` закреплён `tests/test_command_quota_view.py:26-34` — не менял, вопрос 1. Браузерный gate показал строки, собранные вручную без поля: `browser_tests/test_studio_isolation.py:247-251` — добавил `task_road` |
| п. 2 UI: окно и тексты по паре (`auth`, `task_road`) | `studio-model.js:43,180,223,240`; `studio-store.js:181`; `studio-people.js:87-108,151,661-683`; `studio-agents-copy.js:196-215`; Desk: `desk-wizard-roles.js:111-115` (`boundaryCause`), `desk-wizard-team.js:88-90` (`boundaryOf`), `desk-wizard-prepare-view.js:19-31`, `desk-wizard-copy.js:420-445` (`wizard.chain.boundary`, `wizard.chain.boundary_login`) | Да: строка Agents показывает слова пары для подписки и фразу дороги для каждой строки; Desk выбирает предложение по выбранным агентам, не по имени | Настоящего рендера предложения Desk про вход не было (только заглушка DOM): добавил два браузерных теста (`browser_tests/test_desk_wizard_prepare.py:355-379`). Сжатие комментария `projectVendorDetail` в `studio-model.js:182-193` оставлено: без него файл 804 строки при пределе 800 (отклонение 2) |
| п. 3 дверь | `harness_attempt.py:216-229` (`_launch_covers`: `relay_home.relay_root_for(<login-home>) is not None`, чистая функция пути); тесты через двери: `test_subscription_road_boundary.py:272-366`, `test_execution_boundary_refusal.py:63-137` (план, готовность, авторизация), `test_production_door_boundary.py:140-153` | Да: отказ на plan/preview/authorize тем же закрытым словом `service_refused`/`execution-boundary`; Grok/Kimi и API-ключ формой не затронуты | Ничего |
| п. 3 мастер | `provider_setup.py:339-385,413-433`, `providers.py:272-282` (`has_login_relay`); `test_provider_setup_login.py:73-134` | Да: форма `<что-то>\DecemberCommand\logins\<имя>` — тем же `relay_root_for`, подсказка `%USERPROFILE%\DecemberCommand\logins\<id>`, строка входа с `CLAUDE_CONFIG_DIR`/`CODEX_HOME` на папку | Мастер отвергает литерал `%USERPROFILE%` как не абсолютный путь: добавил строку «Type the whole path: …» (`provider_setup.py:376`) и проверку в `test_provider_setup_login.py:103`. Форма требуется на всех платформах — вопрос 4 |
| п. 4 слова отказов не по входу | `relay_attempt.py:90-129` (`NOT_THE_LOGIN`: `mint`, `spec`, `enter`, `claim`, `claim_standing`; `refusal_prefix(tool, code)`); `failure_reasons.py` слова не менялись: они ищутся по фразе, не по префиксу; тесты `test_relay_road_words.py:44-95`, `test_relay_road_refusals.py:121-133` | Да | Тест «ровно пять кодов» (`test_relay_road_words.py:89-100`) сверял два литерала самого набора и продукта не касался; усилен: сверка с `relay_attempt.NOT_THE_LOGIN`, `OWN_PHRASES`, `login_relay.REFUSALS` |
| п. 5 f1 | `harness_attempt.py:491-522` (`_run_relayed`: внутренний отказ побеждает отказ выхода); `tests/test_relay_road_leaving.py:33-95` (claim бросает `OwnerRefused` и выход отказывает → слова claim; marker записан и выход отказывает → `claim_standing`; `spec`; контроль: отказ выхода после запуска остаётся `unknown`) | Да, через hook `exit`; мутанты F1 и F1-CTRL красные | Ничего |
| п. 5 f2 | `test_relay_road_success.py:354-376`: значение под ключом вне схемы и вне `secret_fields` | Да; мутант F2 (`every_text` → `secret_values`) красный | Ничего |
| п. 5 f5 | `harness_attempt.py:299-308` (программная ошибка до lease); `test_subscription_road_boundary.py:436-452`; `test_relay_road_lifecycle.py:83-93` передаёт настоящий claim | Да; мутант F5 красный | Ничего |
| п. 6 документы EN/RU | `README.md:104`, `README.ru.md:105`; `first-run-v1.en.md:74,136,146,224,329,353`, `first-run-v1.md:73,134,144,221,325,331`; `owner-acceptance.md:198,240`, `owner-acceptance.ru.md:207,252`; `release-smoke.md:465-477`; `R5-REHEARSAL-RUNBOOK.md:3-9` | Да по содержанию (подписочный вход без API-ключей, папки `%USERPROFILE%\DecemberCommand\{harnesses,logins}`, `conduct providers` при остановленном сервере, новая сборка, точные действия в UI); EN и RU синхронны по разделам (README 7/7 строк; first-run 102/100 строк, 8/8 строк таблиц, 6/6 пунктов; owner-acceptance 34/36) | Баннер `R5-REHEARSAL-RUNBOOK.md` имел оборванную фразу про wheel и дату 24.10 — исправлено («старый wheel `0a493ad` не используется», дата замены 23.10 по runbook B) |
| п. 7 runbook B | `R5-CLAUDE-B-RUNBOOK.md` на `6cc2f45`: `preflight.ps1 -Mode check` и раздел восстановления; ключ восстановления после прохода владельца исправлен — видимые признаки и код отказа, см. «Проверка ведущего» | Да: остальной текст не менялся (24 добавленные строки); команды существуют (`ownership_cli.py:37-82`), `preflight.ps1 -Mode check` — по отчёту П0–П5 A | Ничего |
| три новых теста | `test_desk_wizard_boundary_words.py` (9), `test_provider_task_road.py` (22), `test_relay_road_leaving.py` (4) | Прочитаны целиком; ожидания — литералы и артефакты, подмена внутренностей — отклонение 13 | Все красные на базе, кроме двух контролей (раздел «Красная фаза») |

## Изменения

Пути `adapters/` — `src/conductor/command/adapters/`.

**Оставлено от первого исполнителя без изменений** (прочитано и проверено, п. 1–7 в таблице выше):
`adapters/{harness_attempt,harness_profile,relay_attempt,process_boundary,process_loans,codex_cli,
provider}.py`, `command/{failure_reasons,http_api,http_reads,isolation_facts,providers,
studio_routes}.py`, `provider_setup.py` (кроме одной строки), девять файлов панели
(`desk-wizard-{copy,model,prepare-view,roles,team}.js`,
`studio-{agents-copy,model,people,store}.js`), двадцать четыре изменённых файла `tests`
(двадцать тестов, помощник, фикстуры `tests/fixtures/wizard/`) и три новых теста, документы.

**Мои правки поверх:**

| Файл | Что |
| --- | --- |
| `src/conductor/provider_setup.py` | +1 строка в `_ask_login_home`: «Type the whole path: %USERPROFILE% is your user folder, e.g. C:\Users\you.» |
| `tests/test_provider_setup_login.py` | +1 проверка этой строки |
| `tests/test_relay_road_words.py` | тест «ровно пять кодов» сверяет `relay_attempt.NOT_THE_LOGIN`, `OWN_PHRASES`, `login_relay.REFUSALS` |
| `tests/test_desk_wizard_prepare.py` | docstring: убраны «H5-V1» и «an API key» |
| `browser_tests/test_desk_wizard_prepare.py` | docstring; два новых теста: настоящий рендер `wizard.chain.boundary_login` (ru, en) |
| `browser_tests/test_studio_isolation.py` | строки ростера, собранные вручную, получили `task_road` (иначе `projectProviders` отбрасывает их) |
| `docs/recovery/2026-10-20/R5-REHEARSAL-RUNBOOK.md` | баннер: «старый wheel `0a493ad` не используется, API-ключи не нужны», дата замены |

**Правки по ревью Opus (эта итерация):**

| Файл | Что (находка) |
| --- | --- |
| `src/conductor/command/http_api.py` | откат правки `_list_runs` к форме HEAD (Л3.8); diff файла — только `_controls` |
| `src/conductor/panel/studio-people.js` | дорога задачи и пара (`auth`, `task_road`) рисуются только для `availability === "available"` (Л1.6) |
| `src/conductor/panel/studio-agents-copy.js` | `agents.provider_explainer` — четыре факта (Л1.5); `agents.setup_explainer` — остановленный сервер и папка входа, без имён вендоров (Л1.10) |
| `src/conductor/panel/studio-model.js` | комментарий `PROVIDER_TASK_ROAD` сокращён до 93 знаков, файл по-прежнему 800 строк (Л3.3) |
| `src/conductor/panel/desk-wizard-prepare-view.js` | два перенесённых места длиной 101 знак, без смены поведения (Л3.3) |
| `tests/test_subscription_road_boundary.py` | `ANY_FOLDER` для шести свидетелей честного текста без relay (Л2.1); `UNCOVERED`: тест checker через runtime с вторым случаем «relay, login в другой папке» (Л3.4) |
| `tests/test_adapter_boundary_launch.py` | `PRODUCT_LOGIN` и папка входа параметром (Л2.1) |
| `tests/test_provider_setup_login.py` | шесть неверных форм папки (Л3.1); POSIX-форма на Windows (Л2.2); запись мастера проходит `relay_root_for` |
| `tests/test_studio_agents_i18n.py` | `agents_view`; чип дороги (Л3.2); строка, которую компьютер не может запустить (Л1.6); пояснение (Л1.5); пустой ростер (Л1.10) |
| `README.md`, `README.ru.md`, `docs/first-run-v1.en.md`, `docs/first-run-v1.md`, `docs/owner-acceptance.md`, `docs/owner-acceptance.ru.md` | оговорка о живых свидетельствах, раздел «What has been checked with the real vendor», `reconcile` и перезагрузка по случаям, таблица по словам экрана Runs, шаг 1, PowerShell из «Пуска», путь `codex.exe`, срок входа (Л1.1–Л1.4, Л1.6–Л1.9) |
| `docs/release-smoke.md`, `docs/specs/2026-09-09-controls-current-contract.md` | дорога рисуется для строки, которую компьютер может запустить (Л1.6) |
| `docs/recovery/2026-10-20/R5-CLAUDE-B-RUNBOOK.md`, `…/R5-REHEARSAL-RUNBOOK.md` | фраза о том, что `preflight` не проверяет продукт (Л1.12); перенос баннера до 100 знаков (Л3.3) |

Эта итерация новых файлов `src` и `tests` не добавила. Новых файлов `src` нет. Новые файлы `tests`
остались прежние (три): `tests/test_desk_wizard_boundary_words.py`,
`tests/test_provider_task_road.py`, `tests/test_relay_road_leaving.py` (список для `CAPPED` — в
«Передаче»). `process.py` (800 строк), `artifact_transport.py` (787), `harness_attempt.py` (563)
в пределах; `studio-model.js` ровно 800 строк.

## Проверки

Каждая команда — после `. ..\December-Command-Environment.ps1 -Quiet`, Windows 11, Python 3.12.14,
node v24.19.0, `--basetemp C:\Users\Пользователь\<≤4 символа>` (не существовал до прогона,
удалён после; проверено), для cp1251 — `Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING` (в логе
`utf8_mode 0`, `preferred cp1251`; для UTF-8 — `utf8_mode 1`, `preferred utf-8`). Скрипты и логи:
`Documents\Codex\work\i3c\` (`run_chunk.ps1`, `run_red.ps1`, `run_natives.ps1`, `run_mut.ps1`,
`mutate_i3.py`, `red_report.py`, `limits.py`, `run-*.log`, `red-*.log/.xml/.json`,
`mutants-*.json`, `mutant_table.md`). Параллельно шло до восьми процессов pytest (8 логических
ядер).

| Что | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| Целевые тесты, четыре набора (двери и граница 4 файла, дорога relay 5 файлов, мастер и факт дороги 7 файлов, UI, контракт и документы 16 файлов) до двух последних правок тестов | UTF-8 | 289 + 148 + 224 + 504 = **1165 passed** (`run-a1…a4.log`) | первичное подтверждение заготовки |
| Полный core: все 659 `tests/test_*.py`, кроме десяти нативных, семь процессов (сюда входят все тесты, импортирующие изменённые модули, тесты UI через node и тесты документов) | UTF-8 | **18543 passed, 409 skipped, 0 failed** (3038/12, 2594/39, 2737/53, 2426/57, 2542/86, 2613/31, 2593/131; `run-fu1…fu7.log`, 946–1479 с) | прежнее цело; кириллический профиль (путь basetemp `C:\Users\Пользователь\fuN`) |
| то же | cp1251 | **18542 passed, 1 failed, 409 skipped** (`run-fw1…fw7.log`): `tests/test_view_mode.py::test_view_mode_process_never_spawns_a_child_through_a_full_prepare_flow` — `POST /command/runs` ответил 500 `store_error` (`run-fw6.log`: 2612 passed, 1 failed, 31 skipped) | красный не закрыт, см. ниже |
| Диагностика красного cp1251 | cp1251 | тест один: 3 запуска на простаивающей машине — 3 passed (11,5–11,9 с); 6 запусков под нагрузкой — 6 passed (14,7–23,1 с); весь chunk 6 повторён под нагрузкой (мутанты, красная фаза): **2613 passed, 31 skipped, 0 failed** (`run-fx6.log`) | **причина не установлена**: 500 `store_error` не воспроизведён за 10 повторов; гипотеза «блокировка файла хранилища на Windows под нагрузкой» не проверена; зелёные повторы красный не закрывают. Файл и код дороги подписки тесту не касаются (вопрос 7) |
| Нативные, **один файл на процесс**, десять файлов (`test_relay_home_native`, `test_login_relay_native`, `test_process_login_closed`, `test_process_native_boundary`, `test_process_acl_native`, `test_process_acl_mutex_native`, `test_process_loans_native`, `test_process_login_native`, `test_process_login_native_overlap`, `test_process_login_config_native`) | UTF-8 / cp1251 | **32/2/8/6/1/5/8/15/10/4 = 91 passed / 91 passed**, 0 failed | runner и ворота `LOGIN_LOAN_OPEN` (`False`) целы; `process.py` не менялся |
| `test_relay_road_words.py` после усиления одного теста (правка после полного прогона) | UTF-8 / cp1251 | 43 passed / 43 passed | усиленный тест зелёный |
| Browser gate, весь `browser_tests/` (114 файлов, три процесса) | UTF-8 | bu1: 1 failed, 497 passed — `test_studio_isolation::test_the_roster_keeps_the_three_answers_…` (строки ростера без `task_road`: **реальное падение от этого diff**, исправлено); bu2: 1 failed, 614 passed — `test_studio_step::test_the_attempt_id_counts_past_the_one_this_run_already_holds` (клик по неактивной «Confirm and authorize», 30 с, под тремя Chromium); bu3: 780 passed | настоящий рендер Studio и Desk; красный `test_studio_step` не воспроизведён (ниже), причина не установлена |
| Browser gate, 12 UI-файлов (`test_studio_{screens_rendered,layout,isolation,demo,step}`, `test_desk_{wizard_roles,wizard_host,wizard_prepare,status,run_write}`, `test_hub_page{,_ops}`) на простаивающей машине, после исправления | UTF-8 / cp1251 | **218 passed / 218 passed** (`run-bw2.log`, `run-bw1.log`) | рендер Agents и Desk, ростер, пара (`auth`, `task_road`) |
| Browser: `test_desk_wizard_prepare.py` под нагрузкой, затем на простаивающей машине | UTF-8 | 1 failed, 43 passed (первый тест, клик по полю `wizard:title` до любой проверки поведения, параллельно шёл pytest дороги relay) / **46 passed** (44 + два новых) | оба исхода записаны; красный не закрыт, причина не установлена |
| `test_studio_isolation.py` + `test_studio_step.py` отдельно после исправления | UTF-8 | 16 passed | исправление строки ростера |
| Лимиты (`limits.py`: новые файлы целиком, изменённые — добавленные строки; строки ≤ 100, файлы ≤ 800, без хвостовых пробелов, CR и BOM, один `\n`) | — | 64 файла (с этим отчётом); `.js` не мерился (отклонение 16: `limits.py` первой итерации мерил `.py` и `.md`, исправлено во второй, строка ниже); в мерённых `.py` и `.md` ошибок нет; две строки JSON по 402 символа в `docs/specs/2026-09-09-controls-current-contract.md:303,584` — зеркало предложения из `isolation_facts.py` (JSON-строку не перенести; в этом файле строк > 100 было 27 и на HEAD) | форма |
| Под `Path.home()` | — | `~\DecemberCommand\relay` и `~\.december-command` не существуют; `logins` 23.10 13:35, `harnesses` 23.10 18:11, `h5-a` 23.10 18:41 — как до работы; содержимое не читал | безопасность |

### Проверки правок по ревью Opus

Среда и приёмы те же (скрипт окружения; basetemp `C:\Users\Пользователь\<≤4 символа>`, не
существовал до прогона, удалён после; для cp1251 —
`Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING`, в логе `utf8_mode 0`, `preferred cp1251`).
Скрипты и логи: `Documents\Codex\work\i3d\`
(`run_in.ps1`, `mutate_i3d.py`, `limits.py`, `docs_parity.py`, `treehash.py`, `run-*.log`,
`mutants-b.*`, `mutants-c.*`). Прогоны шли на рабочей копии (отклонение 12); семь процессов pytest.
Чанки полного core — те же `c1…c7` (659 файлов `tests/test_*.py` без десяти нативных; покрытие всех
669 файлов сверено с диском).

| Что | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| Промежуточные целевые наборы (четыре, 1231 тест) до последних правок | UTF-8 | `ua1` 317 passed; `ua2` 148 passed; `ua3` 2 failed, 234 passed; `ua4` 1 failed, 529 passed | два красных были моими: тест мастера (форма `…\logins` — начало верного пути, Л3.1) и текст пояснения с именем вендора (страж `test_no_screen_branches_on_a_provider_name`, Л1.10); оба исправлены, повтор `qa2` (мастер, Agents, `test_studio_runs`): 145 passed |
| Полный core: 659 файлов, семь процессов | UTF-8 | **18612 passed, 1 failed, 409 skipped** (`run-fu1…fu7.log`: 3070/2594/2737/2438/2567+1 failed/2613/2593 passed; 713–1223 с) | красный один — `test_command_line_cap` на моей новой строке 518 `test_subscription_road_boundary.py` (101 знак): исправлено (перенос комментария); повтор `qa3` — `test_command_line_cap`, `test_subscription_road_boundary`, `test_file_endings`, `test_docs_commands`: **345 passed** |
| Полный core, те же чанки, после исправления | cp1251 | **18613 passed, 0 failed, 409 skipped** (`run-fw1…fw7.log`: 3070/2594/2737/2438/2568/2613/2593 passed; 915–1610 с) | прежнее цело; красный `test_view_mode…full_prepare_flow` первой итерации в этом прогоне зелёный (чанк 6: 2613 passed, 31 skipped, как раньше); зелёный повтор красный первой итерации не закрывает (причина не установлена, вопрос 7) |
| Нативные, **один файл на процесс**, десять файлов, ни один не затронут (runner, `relay_home`, `login_relay`, `process*` не менялись), прогнаны для проверки | UTF-8 / cp1251 | 32/2/8/6/1/5/8/15/10/4 = **91 passed / 91 passed**, 0 failed (`natives-utf8.log`, `natives-cp1251.log`) | `LOGIN_LOAN_OPEN` остаётся `False`; `process.py` без изменений |
| Browser gate: 12 UI-файлов (`test_studio_{screens_rendered,layout,isolation,demo,step}`, `test_desk_{wizard_roles,wizard_host,wizard_prepare,status,run_write}`, `test_hub_page{,_ops}`), простаивающая машина, один процесс | UTF-8 / cp1251 | **218 passed / 218 passed** (`run-bu1.log`, `run-bw1.log`; 233 и 236 с) | настоящий рендер Agents и Desk после правок `studio-people.js`, копии и `desk-wizard-prepare-view.js` |
| Browser gate: ещё восемь файлов, где рисуется Agents (`test_studio_{rendered,read_queues,read_liveness,quotas,preferences,lifecycle}`, `test_desk_{view_mode,people}`) | UTF-8 / cp1251 | **115 passed / 115 passed** (`run-bu2.log`, `run-bw2.log`) | остальные места, где строка провайдера попадает на экран |
| Красная фаза, мутанты | UTF-8 | разделы «Красная фаза» и «Мутанты правок по ревью Opus»: 22 failed на базе; M0 379 passed; 9 мутантов красные | |
| Документные тесты после последней правки отчёта (`test_file_endings`, `test_docs_commands`, `test_command_line_cap`, `test_controls_current_contract`, `test_studio_source`, `test_studio_runs`, `test_release_metadata`) | UTF-8 / cp1251 | **300 passed / 300 passed** (`run-qd1.log`, `run-qd2.log`) | отчёт и документы без хвостовых пробелов, CR и BOM; команды и ссылки README сверены с парсером |
| Лимиты (`work\i3d\limits.py`: `.py`, `.js`, `.md`, добавленные строки, новые файлы целиком; строка ≤ 100 кроме таблиц и ограждений кода, файл ≤ 800, без хвостовых пробелов, CR, BOM, один `\n`) | — | 64 файла: **LIMITS OK**; `studio-model.js` 800 строк, `process.py` 800, `artifact_transport.py` 787, `harness_attempt.py` 563; длинные JS-строки — только девять строк копии `studio-agents-copy.js` (по языку на строку, стиль файла) | форма |
| EN/RU документов (`docs_parity.py`: заголовки, строки таблиц, пункты списков, ограждения кода, ссылки) | — | README 7/30/9/6/24 против 7/30/9/6/24; first-run 11/34/18/32/21 против 11/34/18/32/21; owner-acceptance 21/20/17/20/4 против 21/20/17/20/4 | синхронность |
| Состояние дерева до и после прогонов | — | `git status --short`: 64 записи до и после (`fc`: без различий, `status-cp1251-start/end.txt`); хеш `src`, `tests`, `browser_tests`, `docs`, `pyproject.toml` без отчёта `a9fba285685708d9`, 1579 файлов, до и после полного cp1251; начало итерации `00fb9990ba65cd50`; `git diff HEAD --shortstat`: 60 files, +1554/−345 | рабочая копия не менялась прогонами |
| Под `Path.home()` | — | `~\DecemberCommand\relay` и `~\.december-command` не существуют; `logins` 23.10 13:35, `harnesses` 23.10 18:11, `h5-a` 23.10 18:41 — как до работы; содержимое не читал; `DecemberCommand\product` (26.10 11:12) — подготовка B Codex, я его не открывал | безопасность |

## Красная фаза

Итоговые тесты (рабочая копия, 26 файлов с изменениями или потребители изменённых помощников и
фикстур) на `src` **неизменной базы `758a159`**: `git archive 758a159` в
`Documents\Codex\work\i3c\red\` (zip sha256 `4DD9C125…A2B84`; `docs` базы, не рабочей копии), поверх
неё — `tests\` и `browser_tests\` рабочей копии (побайтно равны, проверено); `PYTHONPATH` на
`red\src`, `conductor.__file__` из копии (в `red-rd2.log`). UTF-8. Первая версия красной фазы
(`rd1`) шла до усиления одного теста и дала 135 failed, 719 passed; итоговая (`rd2`) — после:

**136 failed, 718 passed** (854 теста; `red-rd2.log`, `.xml`, `.json`; 850 с). Причины 136
падений:

| Причина | Число | Что это |
| --- | --- | --- |
| сравнение (`AssertionError`, `assert`) | 88 | двери отвечают `True` там, где должны `False` (16: неверная папка входа), слова отказов с прежним префиксом, Desk и Agents без пары и строки дороги, мастер без заметок и без проверки формы, строки провайдера без `task_road` в ожиданиях (`vendor_sandbox`, фикстуры) |
| `TypeError` | 16 | `provider_projection()` не знает `boundary` (14) и прочее |
| `AttributeError` | 13 | нет `TASK_ROADS`, `boundaryOf`, `has_login_relay` и других новых имён |
| `DID NOT RAISE` | 12 | дверь checker не отказывает неверную папку (10, `CheckFrameError`), дверь плана (2, `ApiRefusal`) |
| прочее | 4 | `RelayNotStarted` вместо программной ошибки на `claim=None` (f5; 2 режима × 2 harness) |
| `KeyError` | 2 | нет ключа `wizard.chain.boundary_login` |
| `ImportError` | 1 | нет `relay_attempt.NOT_THE_LOGIN` (усиленный тест «ровно пять кодов») |

По файлам (всего тестов → красных): `test_subscription_road_boundary` 108 → 39,
`test_execution_boundary_refusal` 56 → 3, `test_production_door_boundary` 31 → 6,
`test_adapter_boundary_launch` 94 → 0, `test_relay_road_refusals` 65 → 10, `test_relay_road_words`
43 → 11, `test_relay_road_lifecycle` 15 → 0, `test_relay_road_success` 21 → 0,
`test_relay_road_leaving` 4 → 3, `test_provider_setup_login` 20 → 12, `test_codex_auth_store` 8 → 0,
`test_relay_env` 112 → 0, `test_provider_task_road` 22 → 21, `test_controls_provider_block` 17 → 2,
`test_desk_wizard_roster` 4 → 2, `test_studio_agents_i18n` 16 → 10, `test_studio_runs` 71 → 1,
`test_desk_wizard_boundary_words` 9 → 9, `test_command_isolation_facts` 16 → 1,
`test_command_provider_contract` 14 → 1, `test_command_provider_registry` 13 → 1,
`test_provider_auth_mode` 53 → 1, `test_studio_provider_arms` 3 → 2,
`test_alpha1_ui_lane_artifacts` 21 → 1 (потребитель `alpha1_live_extensions.py`),
`test_controls_current_contract` 4 → 0, `test_studio_payload_parity` 14 → 0.

Браузерные файлы на базе (`red-rb1.log`, `red-rb2.log`): `test_desk_wizard_prepare.py` 2 failed, 44
passed (два новых теста), `test_studio_isolation.py` 1 failed, 9 passed (исправленный тест ростера).

**Стражи, зелёные на базе** (15 функций из изменённых или новых; по причине):

- Контроли нового поведения, зелёные на базе по замыслу:
  `test_the_folder_of_the_login_is_judged_by_its_written_names_and_nothing_is_read` (правильное
  написание и регистр не отказывают, ФС не читается; убивает FORM-DOOR-READS),
  `test_a_refusal_about_the_login_or_its_folders_still_says_the_login_is_not_ready` (отказы входа
  сохранили прежний префикс; PREFIX-ALL),
  `test_a_boundary_that_refuses_to_be_left_after_a_run_is_still_an_unknown_outcome` (после запуска
  отказ выхода остаётся `unknown`; F1-CTRL),
  `test_a_login_without_a_relay_is_still_kept_in_any_absolute_folder` (Grok/Kimi держат любую папку;
  WIZ-RELAY-ALL),
  `test_the_fact_does_not_change_the_contract_a_grant_is_bound_by` (`task_road` не входит в
  контракт, который связывает grant; CONTRACT-LEAK),
  `test_a_row_that_says_no_road_states_no_task_road_and_no_pair` (строка без дороги ничего не
  утверждает; UI-NULLROAD),
  `test_the_machine_the_build_and_the_login_never_share_a_word` (словари не делят слов;
  VOCAB-SHARE).
- Исправление теста без нового поведения продукта:
  `test_every_text_of_a_relay_credential_that_left_its_shape_joins_what_is_scanned_for` (f2: на
  базе `every_text` уже есть, тест лишь теперь отличает «все тексты» от именованных полей; убивает
  F2).
- Правки совместимости (путь входа теперь в `DecemberCommand\logins\<id>`, claim передаётся
  настоящий), поведение прежнее, мутантов не имеют:
  `test_a_road_that_skips_the_preflight_cannot_spawn_on_a_relay_either`,
  `test_the_readiness_is_spent_by_the_attempt_it_was_proved_for`,
  `test_a_subscription_row_refuses_an_api_billing_name_while_it_is_typed`,
  `test_the_printed_login_command_survives_a_real_machine_path`,
  `test_the_vendor_login_writes_a_directory_and_prints_the_command_to_run`,
  `test_the_wizard_prints_the_sign_in_that_keeps_the_login_in_a_file`,
  `test_the_wizard_refuses_such_a_name_while_it_is_typed_and_writes_the_one_after`; зелёными на
  базе остаются и 94 теста `test_adapter_boundary_launch.py`, 112 `test_relay_env.py`, 53 из 56
  `test_execution_boundary_refusal.py` — прежние ветки (API-ключ, Grok/Kimi без relay, Linux).

### Красная фаза правок по ревью Opus

`Documents\Codex\work\i3d\red\`: копия дерева **до правок этой итерации** (`src` как в рабочей
копии при старте итерации; `conductor.__file__` из копии, в `run-rd1.log` … `run-rd3.log`), поверх
неё четыре изменённых файла тестов. UTF-8, по файлу на процесс.

| Файл тестов | На базе | Причина |
| --- | --- | --- |
| `test_studio_agents_i18n.py` | **22 failed, 20 passed** (42 теста; `run-rd3.log`) | все 22 — на сравнении (`AssertionError`): 18 строк, которые компьютер не может запустить, рисуют `[['studio-chip studio-chip--fail', '✕ refused']]` вместо `[]`; 2 пояснения (`'Four facts per row' in …`, `'дорога задачи' in …`); 2 пустых ростера (`'Stop the server first…' in …`, `'Сначала остановите сервер…' in …`) |
| `test_provider_setup_login.py` | 32 passed | страж, зелёный на базе: мастер (`provider_setup.py`) эта итерация не менялся, тесты держат мутанты WIZ-NAMED и WIZ-LOGINS-ONLY |
| `test_subscription_road_boundary.py` | 136 passed | страж: честный текст без relay и тест checker не менялись в `src`; держат мутанты FORM-ALL-ROADS и FORM-DOOR-CHECKER-RUNTIME |
| `test_adapter_boundary_launch.py` | 98 passed | страж: то же (FORM-ALL-ROADS) |

Четыре проверки чипа (`test_the_chip_of_a_road_is_drawn_as_the_fact_it_is`) зелёные на базе по той
же причине: канал чипа уже был верным, тест убивает мутант UI-CHIP-SWAP (стандарт §3: страж, красный
на мутанте, а не на старом коде).

## Мутанты

Копия дерева вне репозитория (`Documents\Codex\work\i3-mut`, `i3-mut2`, `i3-mut3`; три драйвера
шли параллельно по непересекающимся спискам, у каждого своя копия и свой `--basetemp` `ima`,
`imb`, `imc`), `PYTHONPATH` на её `src`, проверено: `conductor.__file__` из копии. В копии лежит
**всё дерево** (`src`, `tests`, `docs`, `browser_tests`, `pyproject.toml` и остальное, кроме
`.git` и `.venv`): тесты стражей читают `docs` (отклонение 6). M0 без изменений на копии A:
**669 passed** (18 файлов стражей целиком). После каждого мутанта файл возвращён и его SHA-256
сверен с исходным: у всех 37 «restored»; хеш дерева (`src`, `tests`, `browser_tests`, `docs`,
`pyproject.toml`, 1579 файлов) у трёх копий и рабочей копии одинаков
(`b2c566206906a218`) перед удалением копий. Каждый мутант идёт с `-x`, поэтому число красных
тестов на мутант не считалось. Копии удалены. Первый красный тест выбран по `-x`, а не по смыслу.

**Выживший один, и это набор, а не тест:** UI-MODEL («окно не читает дорогу строки») в первом
прогоне выжил (101 passed), потому что страж этой ветки —
`test_studio_provider_arms.py::test_the_third_arm_keeps_a_row_only_for_a_road_a_task_can_take` —
в набор драйвера не входил; с ним в наборе (103 passed в копии) мутант красный. Остальные 36 были
красными с первого прогона.

Обязательные мутанты задания: дверь без проверки формы login-home — FORM-DOOR (и FORM-DOOR-READS:
дверь читает ФС); мастер без проверки формы — FORM-WIZ; префиксы перепутаны — PREFIX-SWAP (и
PREFIX-NONE, PREFIX-ALL, PREFIX-STANDING, PREFIX-SPEC); f1 — F1 (и F1-CTRL); f2 — F2; f5 — F5;
строка UI `task_road` не выводится — UI-LINE.

Не мутировались (причина): три браузерных теста (нужен настоящий Chromium, код тех же ветвей
держат DESK-* и UI-* на заглушке DOM); правки совместимости (раздел «Красная фаза»); тест
«ровно пять кодов» убивают PREFIX-SPEC и PREFIX-STANDING (сверка с `NOT_THE_LOGIN` продукта).

| Мутант | Что делает | Результат | Первый красный тест |
| --- | --- | --- | --- |
| M0 | без изменения (все файлы стражей целиком) | 669 passed in 1046.39s (0:17:26) | - |
| FORM-DOOR | the door asks no form of the login home | красный: 1 failed, 16 passed | `test_subscription_road_boundary.py::test_every_door_refuses_a_relay_road_whose_login_is_not_kept_in_the_product_folder[claude-code-a-bare-folder]` |
| FORM-WIZ | the wizard asks no form of the login home | красный: 1 failed, 9 passed | `test_provider_setup_login.py::test_a_login_with_a_relay_is_asked_for_the_product_folder_and_another_is_asked_again[claude-code]` |
| WIZ-HINT | the wizard does not say to type the whole path | красный: 1 failed, 9 passed | `test_provider_setup_login.py::test_a_login_with_a_relay_is_asked_for_the_product_folder_and_another_is_asked_again[claude-code]` |
| WIZ-VARIABLE | the wizard does not name the variable that points at the folder | красный: 1 failed, 11 passed | `test_provider_setup_login.py::test_the_sign_in_lines_point_the_vendors_variable_at_the_product_folder[claude-code-CLAUDE_CONFIG_DIR]` |
| WIZ-RELAY-ALL | every harness is a harness with a relay for the wizard | красный: 1 failed, 7 passed | `test_provider_setup_login.py::test_the_menu_says_what_a_subscription_login_does_for_this_harness_and_not_for_another[grok-build]` |
| WIZ-RELAY-NONE | no harness has a relay for the wizard | красный: 1 failed, 5 passed | `test_provider_setup_login.py::test_the_menu_says_what_a_subscription_login_does_for_this_harness_and_not_for_another[claude-code]` |
| F5 | a relayed attempt may be given no claim | красный: 1 failed, 68 passed | `test_subscription_road_boundary.py::test_a_relay_attempt_given_no_claim_is_a_fault_of_the_code_and_starts_nothing[claude-code-dispatch]` |
| TEXT-OLD | a harness with no relay is told the old sentence | красный: 1 failed, 76 passed | `test_subscription_road_boundary.py::test_a_subscription_review_with_no_relay_is_refused_before_any_claim_home_lease_or_spawn[claude-code-without-relay-gate-closed]` |
| TEXT-WORDS | the runtime has no words for the new sentence | красный: 1 failed | `test_subscription_road_boundary.py::test_grok_and_kimi_are_refused_a_subscription_task_with_the_honest_words[grok-build]` |
| ISO-FACT | the isolation fact says nothing of a relay | красный: 1 failed, 11 passed | `test_command_isolation_facts.py::test_the_login_directory_row_says_a_relay_task_does_not_stand_on_it` |
| FORM-DOOR-READS | the door reads the folder of the login (it must judge the written names) | красный: 1 failed, 26 passed | `test_subscription_road_boundary.py::test_the_folder_of_the_login_is_judged_by_its_written_names_and_nothing_is_read[claude-code-the-product-spelling]` |
| PREFIX-SWAP | the prefix of a login refusal and of a start refusal are swapped | красный: 1 failed, 1 passed | `test_relay_road_words.py::test_every_refusal_sentence_earns_the_words_the_runtime_owns[account_unknown]` |
| PREFIX-NONE | a start refusal says the login is not ready | красный: 1 failed, 5 passed | `test_relay_road_words.py::test_every_refusal_sentence_earns_the_words_the_runtime_owns[claim]` |
| PREFIX-STANDING | a claim whose marker stands says the login is not ready | красный: 1 failed, 6 passed | `test_relay_road_words.py::test_every_refusal_sentence_earns_the_words_the_runtime_owns[claim_standing]` |
| PREFIX-SPEC | a refused command says the login is not ready | красный: 1 failed, 28 passed | `test_relay_road_words.py::test_every_refusal_sentence_earns_the_words_the_runtime_owns[spec]` |
| PREFIX-ALL | a login refusal says the attempt could not start | красный: 1 failed, 1 passed | `test_relay_road_words.py::test_every_refusal_sentence_earns_the_words_the_runtime_owns[account_unknown]` |
| F1 | the outer except gives enter again after a refusal from inside the block | красный: 1 failed | `test_relay_road_leaving.py::test_a_claim_that_cannot_be_taken_is_told_so_even_when_the_boundary_then_refuses_to_be_left` |
| F2 | every text of a credential out of its shape is only its secret fields | красный: 1 failed, 17 passed | `test_relay_road_success.py::test_every_text_of_a_relay_credential_that_left_its_shape_joins_what_is_scanned_for` |
| F1-CTRL | a refusal to leave after the run is no unknown outcome | красный: 1 failed, 3 passed | `test_relay_road_leaving.py::test_a_boundary_that_refuses_to_be_left_after_a_run_is_still_an_unknown_outcome` |
| ROAD-NONE | the projection never asks the registry | красный: 1 failed, 2 passed | `test_provider_task_road.py::test_only_a_plain_yes_of_the_registry_is_a_boundary[True-boundary]` |
| ROAD-LAX | any answer but no counts as a boundary | красный: 1 failed, 5 passed | `test_provider_task_road.py::test_only_a_plain_yes_of_the_registry_is_a_boundary[1-refused]` |
| ROAD-MODE | the road is asked for a review, not a dispatch | красный: 1 failed, 2 passed | `test_provider_task_road.py::test_only_a_plain_yes_of_the_registry_is_a_boundary[True-boundary]` |
| ROAD-CONTROLS | the controls route does not ask the registry | красный: 1 failed, 17 passed | `test_provider_task_road.py::test_every_route_that_carries_the_array_sends_the_answer_of_the_registry[/command/runs/run-001/controls]` |
| ROAD-RUNS | the runs route does not ask the registry | красный: 1 failed, 16 passed | `test_provider_task_road.py::test_every_route_that_carries_the_array_sends_the_answer_of_the_registry[/command/runs]` |
| ROAD-WORKFLOWS | the workflows route does not ask the registry | красный: 1 failed, 15 passed | `test_provider_task_road.py::test_every_route_that_carries_the_array_sends_the_answer_of_the_registry[/command/workflows]` |
| ROAD-OPEN | a registry that cannot answer is a boundary | красный: 1 failed, 7 passed | `test_provider_task_road.py::test_a_registry_that_cannot_answer_for_a_provider_refuses_it` |
| ROAD-NOREG | no registry asked is a boundary | красный: 1 failed, 1 passed | `test_provider_task_road.py::test_every_row_carries_the_fact_and_it_fails_closed_where_no_registry_was_asked` |
| CONTRACT-LEAK | the road of a task joins the contract a grant is bound by | красный: 1 failed | `test_provider_task_road.py::test_the_fact_does_not_change_the_contract_a_grant_is_bound_by` |
| VOCAB-SHARE | the login word `unpinned` is the road word `refused` | красный: 1 failed | `test_studio_runs.py::test_the_machine_the_build_and_the_login_never_share_a_word` |
| UI-LINE | the Agents row does not say the road of a task | красный: 1 failed, 2 passed | `test_studio_agents_i18n.py::test_a_subscription_row_says_what_a_task_does_by_its_road_and_why_it_is_refused[boundary-en]` |
| UI-PAIR | the login words of a subscription ignore the road | красный: 1 failed, 2 passed | `test_studio_agents_i18n.py::test_a_subscription_row_says_what_a_task_does_by_its_road_and_why_it_is_refused[boundary-en]` |
| UI-WIRE | the store forgets the road of a row | красный: 1 failed, 99 passed | `test_studio_payload_parity.py::test_the_store_hands_every_admitted_provider_key_back_to_the_screen` |
| UI-MODEL | the window does not read the road of a row | красный: 1 failed, 103 passed (первый прогон на наборе без `test_studio_provider_arms.py`: 101 passed, выжил; набор неполный, не тест) | `test_studio_provider_arms.py::test_the_third_arm_keeps_a_row_only_for_a_road_a_task_can_take` |
| UI-NULLROAD | a row that says no road is shown as a refused one | красный: 1 failed, 6 passed | `test_studio_agents_i18n.py::test_a_row_that_says_no_road_states_no_task_road_and_no_pair[en]` |
| DESK-PAIR | the desk cause ignores the road | красный: 1 failed | `test_desk_wizard_boundary_words.py::test_the_cause_is_read_from_the_pair_of_the_agents_chosen_and_from_no_name` |
| DESK-CHOSEN | the desk cause counts every row, not the chosen ones | красный: 1 failed | `test_desk_wizard_boundary_words.py::test_the_cause_is_read_from_the_pair_of_the_agents_chosen_and_from_no_name` |
| DESK-VIEW | the refusal note ignores the cause | красный: 1 failed, 1 passed | `test_desk_wizard_boundary_words.py::test_the_refusal_note_of_the_boundary_is_the_sentence_of_the_pair[subscription-refused-en]` |

### Мутанты правок по ревью Opus

Копия дерева `Documents\Codex\work\i3d\mut` (всё дерево, как в отклонении 6; хеш `src`, `tests`,
`browser_tests`, `docs` и `pyproject.toml` без отчёта у копии и рабочей копии одинаков до и после
каждой серии, по 1579 файлов: `dfb450213dcc10a6` у серии b, `a9fba285685708d9` у серии c;
`treehash.py`), `PYTHONPATH` на её `src`, проверено: `conductor.__file__` из копии. Каждый мутант
с `-x`; после каждого файл возвращён, SHA-256 сверен (у всех «restored»). Скрипт и результаты:
`work\i3d\mutate_i3d.py`; `mutants-b.*` (таблица ниже; дерево до переноса комментария строки 518 и
до правок формулировок документов) и `mutants-c.*` (итоговое дерево, копия пересинхронизирована):
те же вердикты, M0 379 passed in 151.57s, все девять красные.
Мутанты Л2.1, Л2.2, Л3.1, Л3.2 ревьюеры строили сами и они выживали; здесь они повторены и убиты.

| Мутант | Что делает | Результат | Первый красный тест |
| --- | --- | --- | --- |
| M0 | без изменения (четыре файла правок и `test_studio_runs.py`) | **379 passed** in 134.26s | - |
| FORM-ALL-ROADS | проверка формы папки входа на любой подписочной дороге, не только на relay (Л2.1) | красный: 1 failed, 61 passed | `test_subscription_road_boundary.py::test_a_subscription_dispatch_with_no_relay_is_refused_before_any_claim_home_lease_or_spawn[claude-code-without-relay-gate-closed-any-other-folder]` |
| FORM-DOOR | дверь не спрашивает форму папки (контроль) | красный: 1 failed, 24 passed | `…::test_every_door_refuses_a_relay_road_whose_login_is_not_kept_in_the_product_folder[claude-code-a-bare-folder]` |
| FORM-DOOR-CHECKER-RUNTIME | то же, спрошено только у нового случая checker через runtime (Л3.4) | красный: 1 failed, 1 passed | `…::test_a_subscription_checker_the_boundary_cannot_cover_is_refused_through_the_runtime[claude-code-gate-closed-relay-with-its-login-in-another-folder]` |
| WIZ-NAMED | мастер судит папку по написанным именам (`login_home_named`), а не `relay_root_for` (Л2.2) | красный: 1 failed, 21 passed | `test_provider_setup_login.py::test_a_path_that_names_the_product_folder_but_is_not_absolute_here_is_asked_again[claude-code]` |
| WIZ-LOGINS-ONLY | мастер требует только, чтобы родитель назывался `logins` (Л3.1) | красный: 1 failed, 11 passed | `…::test_a_login_with_a_relay_is_asked_for_the_product_folder_and_another_is_asked_again[claude-code-logins-without-the-product-folder]` |
| UI-CHIP-SWAP | чип дороги нарисован наоборот: `boundary` — `fail`, `refused` — `pass` (Л3.2) | красный: 1 failed, 12 passed | `test_studio_agents_i18n.py::test_the_chip_of_a_road_is_drawn_as_the_fact_it_is[boundary-studio-chip--pass-✓-en]` |
| UI-ROAD-ALWAYS | дорога рисуется и для строки, которую компьютер не может запустить (Л1.6) | красный: 1 failed, 16 passed | `…::test_a_row_this_machine_cannot_start_says_no_road_and_no_pair[subscription-unconfigured-en]` |
| COPY-THREE-FACTS | пояснение снова говорит «Three facts per row» (Л1.5) | красный: 1 failed, 34 passed | `…::test_the_explainer_under_the_list_counts_the_road_of_a_task_among_its_facts[en-Four facts per row-the road of a task]` |
| COPY-SETUP-NO-STOP | текст пустого ростера теряет «Stop the server first» (Л1.10) | красный: 1 failed, 36 passed | `…::test_the_empty_roster_names_the_wizard_the_stopped_server_and_the_login_folder[en-Stop the server first (Ctrl+C in its window)-owner_busy]` |

**Те же четыре мутанта на СТАРЫХ тестах** (копия `before`: дерево на старте итерации, хеш
`00fb9990ba65cd50` до и после; `mutants-d.json`) — выживают, то есть находки были настоящими:

| Мутант | Старые тесты | Результат |
| --- | --- | --- |
| FORM-ALL-ROADS | `test_subscription_road_boundary.py`, `test_adapter_boundary_launch.py` | **выжил**: 202 passed in 138.92s |
| WIZ-NAMED | `test_provider_setup_login.py` | **выжил**: 20 passed |
| WIZ-LOGINS-ONLY | `test_provider_setup_login.py` | **выжил**: 20 passed |
| UI-CHIP-SWAP | `test_studio_agents_i18n.py` | **выжил**: 16 passed |

Не мутировались (причина): документы (правки Л1.1–Л1.4, Л1.7–Л1.9, Л1.12 — проза, тест её не
читает, кроме сверок команд `test_docs_commands` и спецификации `test_controls_current_contract`);
откат `_list_runs` (мёртвый код, мутанта нет: достижимые места держат ROAD-* из первой таблицы).

## Отклонения

До утверждения статус не выше «локально проверено».

| Что | Почему | Кто утвердил |
| --- | --- | --- |
| 1. Работа продолжена с 60 записей остановленного исполнителя, а не начата от `758a159` | указание ведущего в задании; каждая правка прочитана, ничего не принято на веру, все прогоны сняты заново | ведущий (задание) |
| 2. `studio-model.js:182-193`: комментарий `projectVendorDetail` уплотнён (12 строк → 8, смысл прежний) | файл ровно 800 строк, `LINE_CAP = 800` (`test_studio_source`); моя попытка вернуть исходный комментарий дала 804 строки (`limits.py`), возвращено уплотнение | ожидает ведущего |
| 3. Маршрут `GET /command/quotas` не получил `task_road` от registry: его строки говорят `refused` | шов `payload(contracts, now)` закреплён тестом другой полосы (`test_command_quota_view.py:26-34`); смена шва — решение ведущего (вопрос 1) | ожидает ведущего |
| 4. Мастер проверяет форму папки входа на любой платформе (на macOS и Linux задача отказывает в любом случае) | то же правило, что у дверей (`relay_root_for`, по написанным именам); вопрос 4 | ожидает ведущего |
| 5. Мои дополнения вне буквы задания: строка подсказки мастера и её проверка; усиление теста «ровно пять кодов»; два браузерных теста Desk; строки ростера в `test_studio_isolation.py`; два docstring; баннер `R5-REHEARSAL-RUNBOOK.md` | каждое найдено сверкой или прогоном (литерал `%USERPROFILE%` мастер отвергает; тест не касался продукта; настоящего рендера не было; браузерный gate показал красный; docstring устарел; фраза оборвана) | ожидает ведущего |
| 6. Копия для мутантов содержит всё дерево, а не только `src`, `tests`, `pyproject.toml` | тесты стражей читают `docs/` (иначе сбор падает, как в первой красной фазе остановленного исполнителя); хеш дерева у копий равен рабочей копии | ожидает ведущего |
| 7. Красная фаза: 26 файлов, из них `test_controls_current_contract`, `test_studio_payload_parity`, `test_alpha1_ui_lane_artifacts` — потребители изменённых документов и помощников без изменения собственного текста; `docs` красной копии — базы | чтобы показать, что изменение контракта строки провайдера видно потребителям | ожидает ведущего |
| 8. В `docs/specs/2026-09-09-controls-current-contract.md` две строки JSON по 402 символа | зеркало предложения `isolation_facts.py`, проверяемое `test_controls_current_contract`; на HEAD в файле уже 27 строк > 100 | ожидает ведущего |
| 9. Полный core cp1251: 1 красный, не воспроизведён (вопрос 7) | причина не установлена; статус не выше «локально проверено» | ожидает ведущего |
| 10. Browser gate: красный `test_studio_isolation` (от этого diff, исправлен) и нестабильный `test_studio_step` под нагрузкой | итоговое подтверждение — 12 UI-файлов на простаивающей машине в обеих кодировках; полный gate — на CI | ожидает ведущего |
| 11. Мои прогоны шли с параллельной нагрузкой (до восьми процессов), как в I2b | время `test_login_ownership` (окно 8 с, вопрос 11 I2b): в обоих полных прогонах зелёный | ожидает ведущего |
| 12. Полный core и browser gate (обе итерации) шли в рабочей копии с незакоммиченными правками, не в `git worktree add --detach` с пустым `status` до и после (стандарт §3, Л3.7) | незакоммиченный diff в detached worktree не перенести; записаны `git status --short` и хеш дерева до и после прогонов (раздел «Проверки»); итоговый полный прогон — на коммите в `worktree --detach`, делает ведущий | ожидает ведущего |
| 13. Тесты подменяют внутренности продукта и вызывают частные методы (Л3.4): `HarnessWorkspace.claim`, `Path.write_text` для `*.marker`, `harness_attempt.confined_spec` (`test_relay_road_leaving.py:37,51-58,75-76`); `adapter._hold_checker_boundary()`, `adapter._claim_of`, `adapter._attempt` без claim (`test_subscription_road_boundary.py`, `test_relay_road_lifecycle.py`) | то же основание, что отклонения 19 и 20 I2b (приняты Codex 26.10: «не выдавать за общее разрешение подменять внутренности»): отказ claim, marker и сборки команды публично недостижим; `_attempt` без claim (f5) в production не бывает, потому что все три дороги передают claim; checker с неверной папкой теперь проходит и через runtime | ожидает ведущего |
| 14. Часть красных на базе падает не на сравнении (Л3.5): `TypeError` 16, `AttributeError` 13, `KeyError` 2, `ImportError` 1, неверное исключение 4 из 136 (раздел «Красная фаза»); два браузерных теста — на «Unknown interface locale or message key» | новых имён (`TASK_ROADS`, `boundary=`, `has_login_relay`, `boundaryOf`, `NOT_THE_LOGIN`, ключ `wizard.chain.boundary_login`) на базе нет, до сравнения тест не доходит | ожидает ведущего |
| 15. Дорога задачи не рисуется на экране Agents для строки, которую компьютер не может запустить (Л1.6) | закрытый ответ registry для провайдера без адаптера — `refused` (спека `controls-current-contract.md:40-41`), на проводе он остался; окно не выдаёт его за вердикт о компьютере; спека и документы это говорят | ожидает ведущего |
| 16. Измерение длины строки в первой итерации не охватывало `.js` (Л3.3) | `limits.py` первой итерации мерил `.py` и `.md` и освобождал markdown-строки с «](»; исправлено: `work\i3d\limits.py` | ожидает ведущего |

## Не проверено

- CI, Linux и macOS, полный browser gate на CI, wheel из итогового commit. Windows не закрывает
  Linux и macOS: новые тесты мастера и дверей строят пути через `tmp_path` и не используют ничего
  специфичного для Windows, но на POSIX не прогонялись; `relay_root_for` на POSIX-путях не измерен.
- Живые CLI и подписочный цикл (M2 Claude, Codex 0.164.0): не запускались. Работает ли Claude на
  копии без refresh-токена, из этих тестов не следует.
- Нативный сквозной свидетель транспорта: Codex 26.10 решил узкий A2 (`--version`, без входа и
  inference); он не доказывает ни подписку, ни отсутствие refresh на задаче — это первый B.
- Настоящий рендер Agents (цепь `boundary`/`refused`, метка дороги) проверен только существующими
  Studio-файлами browser gate (218 passed) и заглушкой DOM; отдельного браузерного теста строки
  Agents нет. Рендер предложения Desk про вход — два браузерных теста.
- Маршрут квот и снимок `limits.json` hub'а, записанный старой сборкой (вопросы 1, 2).
- Документы владельца прочитаны и сверены с кодом по пунктам таблицы, но по ним не прошёл человек с
  чистой машиной. Оговорка о живых свидетельствах (Л1.1) написана по документам `docs/recovery`
  (M1, M2, `HANDOFF-2026-10-26`, D13), новой пробы не было; слова таблицы «If something is blocked»
  сверены с `failure_reasons.REASONS` и `relay_attempt.OWN_PHRASES` по тексту, тестом не закреплены.
- Первое падение cp1251 (`test_view_mode`, первая итерация) и падение `test_studio_step` под
  нагрузкой: причины не установлены; в итоговых прогонах этой итерации оба теста зелёные, зелёный
  повтор красный не закрывает.
- Строка Agents для провайдера без запуска (Л1.6) проверена `js`-тестами на заглушке DOM и 12 + 8
  файлами browser gate на простаивающей машине; отдельного браузерного теста этой строки нет.
- POSIX: `test_a_path_that_names_the_product_folder_but_is_not_absolute_here_is_asked_again` на
  POSIX пропущен (`skipif`), остальное на POSIX не прогонялось.
- Полный прогон на коммите в `git worktree add --detach` (отклонение 12).

## Открытые вопросы

Рекомендуемый ответ — после тире.

1. **Маршрут квот и `task_road`.** `QuotaView.payload` и `HubLimitsView.payload` строят строки без
   registry, поэтому `GET /command/quotas` отвечает `task_road: "refused"` для всех, даже когда
   dispatch того же провайдера идёт в изоляции; окно эту строку не показывает (читает только
   `display_name`). — Расширить шов необязательным `boundary=` у обоих reader'ов и передавать
   `registry.execution_boundary` из `http_reads.py:39`, обновить заглушку `Reader` в
   `test_command_quota_view.py:26-34`; решение ведущего (шов другой полосы).
2. **Снимок `limits.json` старой сборки.** Его строки не несут `task_road`; `projectProviders`
   отбрасывает такую строку, и ответ квот в окне view-процесса читается как нечитаемый, пока hub не
   запишет свежий. — Принять (окно обновится при следующем ответе активного проекта) или
   достраивать поле при чтении снимка; решение ведущего.
3. **Закрытый ключ checker `login_not_ready`** (`independent_transport.py:72-75`) отвечает «the
   checker's login is not ready for an isolated attempt» и на `mint`, `spec`, `enter`, то есть на
   отказы не по входу (п. 4). — Решение Codex 26.10 (Q5) сохраняет `login_not_ready`; новый
   `claim_refused` для `NotStarted("claim")` разрешён отдельно (`CLOSE-TASK` §2). Расхождение слов
   для `mint`, `spec`, `enter` остаётся принятым; закрытый контракт, не менял.
4. **Форма папки входа в мастере на macOS и Linux.** Там задача отказывает в любом случае, но мастер
   тоже требует `<что-то>/DecemberCommand/logins/<имя>` для Claude Code и Codex. — Оставить (одно
   правило с дверями); при жалобах ограничить `os.name == "nt"`.
5. **Квитанция при неверной папке входа** говорит общее «isolation is not provided for this
   attempt» (закрытое слово двери); причину называют мастер, Agents (`refused`) и Desk. — Оставить;
   отдельная фраза — закрытый контракт.
6. **Вопросы I2b** 1 (Р3), 5, 6, 9, 10, 11, 12 (runner), 13 и D13 я не менял. Вопрос 2 закрыт
   (мастер, документы, Agents, Desk), вопрос 12 закрыт текстом runbook B (п. 7; Codex 26.10:
   достаточно). Решены Codex 26.10 (`I2B-DECISION-REPORT`): Q6, Q8 (для B ограниченно), Q11
   (правка теста — `CLOSE-TASK` §3), Q13 (`claim_refused`, §2), D13 (A2: `--version`, §5), Р7–Р10;
   Q10 — до альфы; Q1/Р3, Р9, Р10 — A-I1.
7. **Нестабильные тесты под нагрузкой.** `test_view_mode…full_prepare_flow` (cp1251, 1 красный из
   двух полных прогонов chunk 6 и 10 зелёных повторов; `POST /command/runs` → 500 `store_error`,
   причина не установлена) и `browser_tests/test_studio_step.py::test_the_attempt_id_counts_past_…`
   (30 с на неактивную кнопку, под тремя Chromium). — Решение Codex или ведущего: как вопрос 11
   I2b (замер и предусловие по стандарту §2.4). Связь с дорогой подписки не исключена (Л3.6):
   `tests/test_view_mode.py:57` импортирует изменённый помощник `alpha1_live_extensions.py`, сервер
   теста стоит на изменённом `http_api`; на базе под той же нагрузкой тест не снимался, а
   «блокировка файла хранилища под нагрузкой» — гипотеза, не проверенная.
8. **`R5-PLAN.md:150,328`** всё ещё описывает схему «с временной копией — после V1» (история плана
   H5-V1). — Правит ведущий (общий документ).
9. **Номер версии Codex в документах** (0.112.0 в `first-run-v1*.md`) остаётся прежним: кандидат
   0.164.0 — решение A, не I3. — После решения A. Оговорка о живых свидетельствах (Л1.1) говорит
   про 0.112.0 и придётся править вместе с номером.
10. **Префикс квитанции для трёх кодов copy-in** (Л1.11, Л2.3). `relay_unusable`, `not_empty`,
    `write_failed` — сбои relay-дома попытки, но квитанция начинается с «the <tool> login is not
    ready for an isolated attempt» (`NOT_THE_LOGIN` — пять кодов по п. 4). Слова runtime для экрана
    Runs верны (`failure_reasons.py:63-67`), владелец этого не видит. — Оставить; если расширять
    `NOT_THE_LOGIN` на три кода, это правка закрытой фразы квитанции (слова runtime и ключ checker
    сверить отдельно): решение ведущего, например в CLOSE-TASK.
11. **Путь установки в first-run** (Л1.8). Документ ставит продукт в
    `%LOCALAPPDATA%\DecemberCommand\app-v1`, Р7 (26.10) для B требует защищённого
    `%USERPROFILE%\DecemberCommand\product\<sha>`. Я добавил «PowerShell из «Пуска»» и абзац, что
    общая папка не меняется, а проверка сопровождающего ставит в защищённую. — Привести путь
    документа к Р7 или оставить оговорку: решение ведущего, после выбора раскладки.
12. **Перезагрузка и `LaunchLost`** (Л1.2) — исправлено проходом документов ведущего. Два вида:
    retire доказан (выход из boundary упал после работы ребёнка) — владение цело, runtime пишет
    `unknown` со словами `adapter execute lost its result`, перезагрузка не нужна; runner не смог
    запустить ребёнка — `retire(False)` делает владельца и аренду входа uncertain, RunStore
    отказывает в записи (`ownership.py:167-168`, `run_store.py:459`), квитанции нет, Studio
    отвечает «The run store is unavailable.»; тогда стоп, перезагрузка и `recover --dir` /
    `recover-login` по коду отказа. Слова «could not start the pinned build» на экран не попадают.
13. **Заметки к кандидату** (`release-notes-v1-alpha*.md`, frozen-19 от 25.09) не менялись:
    first-run теперь говорит, что собранный до изоляции кандидат исполняет задачу без изоляции
    (Л1.4). — Править при публикации кандидата с дорогой подписки (ведущий).

## Ревью Opus

Три линзы Opus (тексты и честность; двери, мастер, транспорт; доказательность и стандарт), 23
находки: 3 major, 20 minor; verdict линз — `request_changes`, `approve_with_notes`,
`approve_with_notes`. Исполнитель этой итерации — Claude Code / Sonnet 5.5, не коммитит. Каждая
находка проверена мной заново (по коду, документам `docs/recovery`, прогону на базе и мутантом на
копии); «подтверждена» — исправлено, «частично» и «нет» — доказательство ниже. Номер — линза и
порядок находки.

| № | Находка | Проверка | Статус | Что сделано |
| --- | --- | --- | --- | --- |
| Л1.1 | major: документы называют дорогу Claude Code и особенно Codex 0.112.0 работающей без оговорки о живых свидетельствах (у Kimi и Grok оговорка есть) | `M2-MODEL-REPORT.md:87-93` (M2b exit 1, сервер отказал модели; «Успех access-only задачи по-прежнему не получен»); `M1-DECISION-REPORT.md:16-18` (один ответ Claude OK вне AppContainer, «не весь путь продукта»); `HANDOFF-2026-10-26.md:22,38`; `I2B-DECISION-REPORT.md:143-145` (всё это «впервые проверяется в B»); до правки таблица и абзац first-run говорили «runs a task», «a full road» | подтверждена | `first-run-v1.en.md`, `first-run-v1.md`: оговорка в строках таблицы Claude Code (один настоящий ответ вне изоляции, задача внутри неё не выполнялась) и Codex (сервер отклонил обе пробы 0.112.0 по модели, задача может закончиться `the process exited non-zero`); «a full road» заменено описанием того, что делает сборка; новый раздел «What has been checked with the real vendor» / «Что проверено с настоящим вендором» и ссылки на него; `README.md`, `README.ru.md`, `owner-acceptance.md`, `owner-acceptance.ru.md`: «устроены так, чтобы исполнять», что не проверено, отказ записывать как заблокированное. Тексты UI (мастер, Agents) оставлены: они описывают факт сборки, а не работоспособность входа |
| Л1.2 | major: абзац отправляет перезагружать Windows и выполнять `ownership recover` при ЛЮБОМ `unknown`; штатная дорога неизвестного исхода — `conduct reconcile`, которой в first-run и owner-acceptance нет | Верно: прежний абзац требовал перезагрузки при любом «unknown»; `reconcile` в `first-run*` и `owner-acceptance*` нет (поиск по `docs` вне `recovery`: только `release-smoke.md`); экран Runs пишет «Outside this window: conduct reconcile» (`studio-runs-copy.js:163`). **Не верно:** что `reconcile` — дорога для квитанции `unknown`. `reconcile.stuck_actions` (`reconcile.py:61-70`) и `ControlRuntime.reconcile` (`runtime.py:737-751`, ADR 0002:65-85) закрывают только действие, у которого есть durable-запрос, но нет ни effect lease, ни терминала (сбой между записью запроса и lease). `LaunchLost` (`relay_attempt.py:317-319`) поднимает ошибку, и при доказанном retire runtime записывает терминальный `unknown` (`runtime.py:573-581`): такое действие `reconcile` не перечисляет (при недоказанном loan записать ничего нельзя — вопрос 12, «Проверка ведущего») | частично | first-run EN/RU, §5 и таблица: `unknown` не повторяется; перезагрузка и `ownership recover` / `recover-login` — только при `could not start the pinned build`, `recovery_required`, `login_recovery_required` (текст runbook B, п. 7); `conduct reconcile --dir <project>` (список, затем `--run … --action …`) — для действия, которое экран «Запуски» отправляет «вне окна»; в строке про `could not start the pinned build` сказано, что `unknown` без этих слов перезагрузки не требует. Что делать с `LaunchLost` — вопрос 12 |
| Л1.3 | major: строка «If something is blocked» привязана к тексту квитанции, которого владелец не видит; диагноз «missing, damaged» не относится к «sign in again» | `runtime.py:629-637`: экран показывает `adapter reported {outcome}: {words}`; `failure_reasons.py:1-13` («The runtime never forwards adapter prose»), `:55-58` («…; sign in again» только для срока), `:30-37` (нет файла и повреждённый файл — без этой фразы); `relay_attempt.py:89` (`SIGN_IN_AGAIN = {expiry_short, expiry_unknown}`) | подтверждена | вместо одной строки шесть, ключ — слова экрана «Запуски» (EN и RU): срок и `sign in again` (с переменной на папку входа); нет файла, повреждён, API-ключ, консольный план (с действием); имя в окружении; «attempt could not start in isolation» (вход ни при чём); `marker stands` (не повторять); `Outside this window: conduct reconcile`. Строка про квитанцию в «Where tasks run» теперь говорит, что экран показывает слова runtime |
| Л1.4 | шаг 1: не сказано, где взять сборку; метка «H5-SUB-R5» — жаргон; «older build refuses every task» неверно для frozen-19 | `release-notes-v1-alpha.md:5-6,30-34,67-73`: frozen-19 от 25 сентября, живые прогоны Claude на подписке; слов boundary, isolation, sandbox про исполнение в заметках нет (поиск) | подтверждена | first-run EN/RU, шаг 1: сборка до изоляции исполняет задачу без изоляции, после изоляции и до этой дороги — отказывает, опубликованного кандидата с дорогой подписки пока нет, сопровождающий назовёт сборку; проверка по заметке мастера сохранена; метка убрана |
| Л1.5 | пояснение под списком Agents говорит «Three facts per row», а фактов четыре | `studio-agents-copy.js:305` до правки; `studio-people.js:87` («A fourth question») | подтверждена | `agents.provider_explainer` EN/RU: четыре факта; дорога задачи — факт сборки, компьютера и вида папки входа, а не самого входа (срок проверяется перед каждой задачей), показана только для инструмента, который компьютер может запустить; тест `test_the_explainer_under_the_list_counts_the_road_of_a_task_among_its_facts`; мутант COPY-THREE-FACTS красный |
| Л1.6 | строка неназначенного или недоступного провайдера получает метку `refused` и фразу «cannot run inside the boundary here»: на свежей машине все пять строк красные | `provider.py:649-662` (нет адаптера — `refused`); спека `controls-current-contract.md:40-41` («a provider that is not available has no adapter and says refused»); на базе все 18 новых проверок такой строки красные: `[['studio-chip studio-chip--fail', '✕ refused']] == []` | подтверждена | провод не менял (закрытая спека: ответ registry); окно рисует метку и фразу дороги и пару (`auth`, `task_road`) только при `availability === "available"` (`studio-people.js:661-664`); строка без дороги ничего о ней не утверждает; спека, owner-acceptance EN/RU, release-smoke, first-run EN/RU это говорят; Desk не затронут (`offersFor` берёт только available); тест `test_a_row_this_machine_cannot_start_says_no_road_and_no_pair` (3 availability × 3 auth × 2 языка); мутант UI-ROAD-ALWAYS красный |
| Л1.7 | owner-acceptance: «кончается раньше шага (с запасом менее десяти минут)» читается неверно | `login_relay.py:86-87,508-519`: `MARGIN_SECONDS = 600`, токен должен пережить таймаут шага на десять минут; отказ получает и вход, кончающийся ПОСЛЕ шага с меньшим запасом | подтверждена | owner-acceptance EN/RU: «A login whose access token does not outlast the step's timeout by ten minutes is refused…» / «не переживает таймаут шага на десять минут» |
| Л1.8 | установка в `%LOCALAPPDATA%\DecemberCommand\app-v1`: окно PowerShell из приложения Claude или Codex попадает в виртуализацию MSIX; Р7 требует защищённого `product\<sha>` | `R5-REHEARSAL-RUNBOOK.md:57-65` (измерено 21.10: venv ушёл в `LocalCache` пакета); `WORKING-STANDARD.md` §5; `I2B-DECISION-REPORT.md:149-164` (Р7) | подтверждена | first-run EN/RU: «откройте PowerShell из меню «Пуск», не из терминала приложения Claude или Codex» и абзац, что папка установки общая, а проверка сопровождающего ставит сборку в защищённую `product\<build id>`; сам путь установки не менял: решение ведущего (вопрос 11) |
| Л1.9 | пример входа Codex: заглушка `'<the pinned codex.exe>'`, путь не дан | `H5-CODEX-COMPAT-A-INVENTORY.json:35` и `R5-REHEARSAL-RUNBOOK.md:27,84`: раскладка 0.112.0 `codex\0.112.0\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\codex\codex.exe` | подтверждена | first-run EN/RU: `$codex = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\codex\0.112.0\node_modules\…\codex.exe'` и фраза, что мастер печатает эти строки с вашими путями: копировать нужно их, а не примеры |
| Л1.10 | `agents.setup_explainer` не говорит про остановленный сервер и папку входа | `studio-agents-copy.js:300-303` до правки; `desk-wizard-copy.js:432` («while the server is stopped»); `owner-acceptance.md:196-197` (`owner_busy`) | подтверждена | EN/RU: «Stop the server first (Ctrl+C in its window)… owner_busy»; для входа по подписке, на котором может исполняться задача, — папка `…\DecemberCommand\logins\<id>` и две строки входа. Имён вендоров в тексте нет: страж `test_no_screen_branches_on_a_provider_name` читает отрисованный текст и был красным на первой версии, где стояло «Claude Code и Codex» (моё промежуточное падение, исправлено); тест `test_the_empty_roster_names_the_wizard_the_stopped_server_and_the_login_folder`; мутант COPY-SETUP-NO-STOP красный |
| Л1.11 | `relay_unusable`, `not_empty`, `write_failed` — сбои relay-дома попытки, но квитанция начинается с «login is not ready» | `login_relay.py:76-78`; `relay_attempt.py:93,96-104` (`NOT_THE_LOGIN` — пять кодов, префикс только для них); слова runtime для Runs верны (`failure_reasons.py:63-67`) | не дефект исполнения, вопрос ведущему | не менял: п. 4 задания выполнен буквально, расширение набора — вне буквы п. 4 и касается закрытой фразы квитанции (ключ checker `login_not_ready`); вопрос 10 |
| Л1.12 | runbook B: шаг `preflight.ps1` подан как достаточная проверка, а по Р7 он не проверяет установку продукта | `I2B-DECISION-REPORT.md:161-163`: «preflight.ps1 проверяет harnesses/downloads/h5-a, но не product: его прежние «0 problems» не покрывают новую установку» | подтверждена | `R5-CLAUDE-B-RUNBOOK.md`, в моём п. 7: «Он не проверяет установленный продукт (wheel, venv, базовый Python): «0 problems» это не покрывает; проверка защищённой установки `product\<sha>` — отдельный шаг подготовки B (Р7)»; остальной текст runbook не менял |
| Л2.1 | честный текст Grok, Kimi и дороги без relay нигде не проверен для папки входа вне `DecemberCommand/logins/x` | мутант FORM-ALL-ROADS (проверка формы папки на любой подписочной дороге) на старых `test_subscription_road_boundary` и `test_adapter_boundary_launch` (копия `before`): **202 passed, выжил** (ревьюер: 289 passed на четырёх файлах); до правки `_signed_in` и `_sign_in` клали вход только в продуктовую папку (`test_subscription_road_boundary.py:91`, `test_adapter_boundary_launch.py:223-230`) | подтверждена | `ANY_FOLDER` (продуктовая папка или `auth/x`): параметризованы `…no_relay_whatever_the_runners_gate`, `…dispatch_with_no_relay…`, `…review_with_no_relay…`, `…checker_with_no_relay_is_refused_before_it_spawns`, `…grok_and_kimi…honest_words` и `test_a_subscription_road_with_no_relay_is_not_provided…` (ABL); мутант FORM-ALL-ROADS красный |
| Л2.2 | тесты мастера не закрепляют, что форму судит `relay_root_for` с `is_absolute` хоста | мутант WIZ-NAMED (мастер судит `login_home_named`) на старых тестах: **20 passed, выжил**; на Windows `/Users/you/DecemberCommand/logins/claude-code` проходит `_ask_absolute` и `login_home_named`, но `relay_root_for` даёт None | подтверждена | `test_a_path_that_names_the_product_folder_but_is_not_absolute_here_is_asked_again` (Windows: POSIX-форма, мастер спрашивает снова; на POSIX пропущен); основной тест мастера проверяет, что записанная строка проходит `relay_root_for`; мутант WIZ-NAMED красный |
| Л2.3 | `NOT_THE_LOGIN` и три кода copy-in | то же, что Л1.11 | вопрос ведущему | вопрос 10 |
| Л3.1 | тест мастера держит только две неверные формы; мутант R1-WIZ-LOGINS-ONLY выжил | мутант повторил на старых тестах (копия `before`): **20 passed, выжил** | подтверждена | тест параметризован шестью неверными формами (пять форм `WRONG_FOLDERS` дверей и «папка с именем харнесса»); мутант WIZ-LOGINS-ONLY красный (первый красный: `…[claude-code-logins-without-the-product-folder]`). Попутно исправил свой тест: форма `…\DecemberCommand\logins` — начало верного пути, и проверка «введённый путь не повторён» по всему выводу была ложной; теперь проверяется строка отказа, а весь вывод — для форм, не являющихся началом верного пути |
| Л3.2 | канал чипа дороги (класс и глиф) не проверен; мутант R2-CHIP-SWAP выжил | мутант повторил на старых тестах (`{boundary: "fail", refused: "pass"}`): **16 passed, выжил** | подтверждена | `test_the_chip_of_a_road_is_drawn_as_the_fact_it_is`: `studio-chip--pass` и ✓ для `boundary`, `studio-chip--fail` и ✕ для `refused`, в обоих языках, один чип дороги на строку; мутант UI-CHIP-SWAP красный |
| Л3.3 | строки > 100 в JS и в баннере runbook; `limits.py` исполнителя мерил длину только `.py` и `.md` | `desk-wizard-prepare-view.js:16,31` (101), `studio-model.js:42` (107), `R5-REHEARSAL-RUNBOOK.md:3` (111, проза со ссылкой): строки добавлены этим diff; `work\i3c\limits.py:45` освобождал markdown-строку с «](» целиком | подтверждена | исправлены все четыре (комментарии перенесены; `studio-model.js` не вырос: 800 строк, комментарий сокращён до 93 знаков; в `refusalNote` выделена переменная `named`); новый `work\i3d\limits.py` мерит `.py`, `.js` и `.md` по всем добавленным строкам и освобождает только строки таблиц и ограждения кода; длинные JS-строки перечисляются отдельно: девять строк копии `studio-agents-copy.js` (одна строка на язык, стиль файла: на HEAD в нём 51 такая строка) |
| Л3.4 | отчёт: «подмена — граница runner и фейки»; новые тесты подменяют внутренности и зовут частные методы, отклонением не названо | `test_relay_road_leaving.py:37,51-58,75-76` (`HarnessWorkspace.claim`, `Path.write_text` для `.marker`, `harness_attempt.confined_spec`); `test_subscription_road_boundary.py` (`_hold_checker_boundary`, `_claim_of`, `_attempt` без claim); `test_relay_road_lifecycle.py` (`_claim_of`) | подтверждена | строка 13 в «Отклонения»: ссылка на отклонения 19 и 20 I2b (приняты Codex 26.10, «не выдавать за общее разрешение»), перечень мест; checker с неверной папкой теперь идёт и через runtime (`UNCOVERED`, второй случай); прямой `_hold_checker_boundary()` оставлен как узкая проверка двери, f5 — прямой `_attempt` без claim: публично недостижимо (все три дороги передают claim) |
| Л3.5 | 34 красных из 136 падают не на сравнении | таблица причин отчёта: `TypeError` 16, `AttributeError` 13, `KeyError` 2, `ImportError` 1, неверное исключение 4 (36 по моей классификации; ревьюер насчитал 34: расхождение в двух `TypeError` из «и прочее», не пересчитывал); два браузерных теста падают на «Unknown interface locale or message key» | подтверждена | строка 14 в «Отклонения»: новых имён (`TASK_ROADS`, `boundary=`, `has_login_relay`, `boundaryOf`, `NOT_THE_LOGIN`, ключ `wizard.chain.boundary_login`) на базе нет, поэтому часть тестов падает раньше сравнения |
| Л3.6 | статус «локально проверено (UTF-8 и cp1251)» при незакрытом красном cp1251; «к дороге подписки не относятся» шире доказанного | `tests/test_view_mode.py:57` импортирует `REFUSALS` из изменённого помощника `tests/alpha1_live_extensions.py`, а сервер теста стоит на изменённом `http_api`: пересечение по замыканию импортов есть; базу под той же нагрузкой не прогоняли; стандарт §2.6 и §3 | подтверждена | «Итог» переписан: UTF-8 — 0 failed; cp1251 — итог этой итерации и красный первой итерации, причина не установлена; «не относится к дороге подписки» — гипотеза по коду; вопрос 7 уточнён (решение Codex или ведущего по §2.6) |
| Л3.7 | полный core и browser gate шли в рабочей копии с незакоммиченными правками, не в `git worktree add --detach` | `work\i3c\run_chunk.ps1:6`: `Set-Location` в репозиторий; мои прогоны этой итерации — тоже в рабочей копии | подтверждена | строка 12 в «Отклонения»: незакоммиченный diff в detached worktree не перенести; записаны `git status --short` и хеш дерева до и после моих прогонов (раздел «Проверки»); итоговый полный прогон ведущему — на коммите в `worktree --detach` |
| Л3.8 | правка `CommandApi._list_runs` недостижима | `Grep`: `_list_runs` встречается только в определении `http_api.py:318` (и в имени несвязанного теста); `GET /command/runs` идёт через `http_reads.py:46-48`; метод мёртв и на HEAD | подтверждена | правка откатана к форме HEAD (мёртвый метод не тронут); diff `http_api.py` теперь — только `_controls`; достижимые места сверки п. 2: `http_reads.py:46-48`, `http_api.py:376-377`, `studio_routes.py:121-122` |

## Проверка ведущего

Opus (ведущий), 26.10.2026.

- **Коммит.** `6cc2f45`: код, тесты, `browser_tests`, документы владельца и runbook из итоговой
  итерации исполнителя; 3 новых теста внесены в `CAPPED` ведущим. Документы и тесты, читающие их
  (`test_docs_commands`, `test_boot_claims`, `test_provider_setup`,
  `test_controls_current_contract`), связаны, поэтому документы I3 вошли в тот же коммит; этот
  отчёт и правки прохода владельца — docs.
- **Целевой прогон** (25 изменённых или новых тестовых файлов I3 и `test_command_line_cap`,
  `Documents\Codex\work\lead-i3\`): UTF-8 1095 passed, 0 failed; cp1251 1095 passed, 0 failed.
  Полный core не дублировался: по CLOSE-TASK §3 он идёт один раз на финальном коммите в detached
  worktree.
- **Независимая сверка исправлений** (Opus, только чтение, `wf_98d96e66-8e5`): код — approve with
  notes, новых дефектов нет; 5 minor по документам. **Проход пути владельца** (Opus): 13 находок,
  5 major — восстановление привязано к невидимым словам, «обе команды recover» тупиковы, runbook B
  расходился с D13/Р7, папка входа Codex не создавалась, не сказано, откуда закреплённые сборки.
- **Проход документов** (`wf_d5fd45db-77d`: Sonnet → повторный проход Opus → Sonnet): F1–F5 и
  O1–O13 закрыты, кроме остатка O9 (подсказка desk-мастера `wizard.providers.none` про правку
  файла — оговорена в документах, UI не менялся); повторный проход нашёл ещё 8 (2 major: признак
  Q12 и имена npm-пакетов Codex) — исправлены, W7 (этот отчёт) исправил ведущий. Тесты документов:
  185 passed, 3 skipped (symlink, WinError 1314) в обеих кодировках.
- **Решения ведущего по вопросам исполнителя:** 1–2 (квоты и снимок hub без `task_road`) — открыто,
  не препятствует B; 3, 5 — оставить по Codex Q5; 4 — принять; 7 — красные `test_view_mode` и
  `test_studio_step` под нагрузкой: решение Codex по §2.6, итоговый полный прогон покажет; 8, 13 —
  при публикации кандидата; 9 — после A; 10 (`NOT_THE_LOGIN` и коды copy-in) — оставить, слова
  runtime уже верные; 11 — B ставится в защищённый `product\<sha>` по Р7, общий путь документа — к
  альфе; 12 — исправлено (выше).

## Ревью Codex: ожидает

Статус: ожидает. Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit кода и тестов: `6cc2f45` (ведущий). Исходное предложение разбивки по §4
  стандарта: код и тесты (включая `docs/specs/2026-09-09-controls-current-contract.md`, которую
  читает `test_controls_current_contract`) — один commit, документы (README, `docs/first-run-v1*`,
  `docs/owner-acceptance*`, `docs/release-smoke.md`, два runbook, этот отчёт) — другой. Статус по
  шкале: локально проверено в обеих кодировках (итоговая итерация: 0 failed в UTF-8 после
  исправления моей строки и в cp1251); не проверено CI, не принято ревью Codex, живой цикл не
  выполнялся.
- `CAPPED` (`tests/test_command_line_cap.py`): вносит ведущий тем же commit; **новых файлов
  `src` нет, новых тестов три**:

```
tests/test_desk_wizard_boundary_words.py
tests/test_provider_task_road.py
tests/test_relay_road_leaving.py
```

  Из `CAPPED` в этой итерации изменены `tests/test_subscription_road_boundary.py` (697 строк) и
  `tests/test_adapter_boundary_launch.py` (664): строка ≤ 100 (`limits.py` и
  `test_command_line_cap`, 345 passed в `qa3`). `browser_tests/` в `CAPPED` не входит.
- `git status --short` в конце: 63 записи — 60 `M` (src 23, tests 25 с `alpha1_live_extensions.py`
  и фикстурами, `browser_tests` 2, docs 10 с README) и 3 `??` (три новых теста); этот отчёт —
  64-я (до и после моих прогонов 64, `fc` без различий).
  `git diff HEAD --shortstat`: 60 файлов, +1554/−345 (без новых файлов).
- Что осталось до B (я этого не делал и не менял), по решениям Codex 26.10 и `CLOSE-TASK`: Q13
  (`claim_refused`) и Q11 (предусловие `test_login_ownership`) на сохранённой базе; wheel из
  итогового commit, защищённые venv и manifest (Р7/Р8) и `run-ready.json` (runbook B, п. 3–4);
  один узкий A2 (native launch, `claude.exe --version`, до четырёх запусков; это решение D13);
  свежий вход владельца и проверка срока (timeout + 10 минут); `preflight.ps1 -Mode check` перед
  стартом; CI; ревью Opus и Codex; правка `R5-PLAN.md` (вопрос 8). A-I1, override Р3, паритет
  `_login_echo`, ключ checker, хеш аккаунта, `retire` и `test_login_ownership` в I3 не входили.
- Временные файлы вне репозитория: `Documents\Codex\work\i3c\` (скрипты, логи, `red-*`,
  `mutants-*.json`, `mutant_table.md`) и `Documents\Codex\work\i3c\red\` (копия базы `758a159` с
  итоговыми тестами) оставлены; `Documents\Codex\work\i3-partial\` и `Documents\Codex\work\i3\`
  первого исполнителя не менялись; копии мутантов `i3-mut*` и все basetemp
  `C:\Users\Пользователь\<…>` удалены. Под `Path.home()` ничего не создавалось (проверено после
  прогонов). Эта итерация: `Documents\Codex\work\i3d\` (скрипты, логи, `mutants-b…d.*`) и копии
  `i3d\before` (дерево на старте итерации) и `i3d\red` (до правок, с итоговыми тестами) оставлены;
  копия мутантов `i3d\mut` удалена.
- Следующий конкретный шаг: commit кода и документов ведущим (три новых теста — в `CAPPED`), ответы
  на вопросы 10–12 и затем `H5-SUB-R5-I2B-CLOSE-TASK` (применяет ведущий). Codex — ревью I3,
  вопросы 1, 2, 7 и 10–12 выше.
