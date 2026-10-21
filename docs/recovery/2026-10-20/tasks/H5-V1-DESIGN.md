# H5-V1: вход по подписке внутри изоляции — честный отказ и один предикат. Дизайн и задание

- Исполнитель: Claude Code / Opus 5.5 (дизайн), 21 октября 2026. Тип работы: проверка кода,
  дизайн, задание для Sonnet. Код продукта в репозитории не менялся; в репозитории создан только
  этот файл.
- Основание: решение владельца **H5-V1** (`OPEN-DECISIONS.md`): в V1 настоящие задачи — только по
  API-ключу; вход по подписке внутри изоляции остаётся честным отказом; схема B (временный home с
  копией только credentials) — после V1. Анализ: `tasks/R2-H5-ANALYSIS.md`, вариант D, разделы
  1, 4–6.
- База: ветка `recovery/2026-10-20`, HEAD `edd79d1` на старте. Во время работы параллельный
  workflow закоммитил `a8e6baa` (только документация владельца: README*, CONTRIBUTING*,
  `docs/first-run-v1*`, `docs/owner-acceptance.md`, `docs/release-smoke.md`, R5-PLAN,
  R5-WINDOWS-WHEEL-ROAD). Код и тесты на `a8e6baa` те же, что на `edd79d1`.
- С момента R2 (`4d0e3af`) из затронутых файлов менялся только `process.py` (`63daddb`, R1.1:
  `container_profile` отказывает вне Windows до импорта `_winlaunch`). На H5 это не влияет.
- Диагностика лежит только в `C:\Users\Пользователь\Documents\Codex\work\h5v1-design\`:
  - `copy\` — копия `src`, `tests`, `browser_tests`, `pyproject.toml` с применённым дизайном;
  - `apply_to_copy.py` — точный текст правок кода (раздел 4), применённый к копии; каждая
    «старая» строка проверяется на единственность;
  - `task\tests\test_subscription_road_boundary.py` — новый тестовый файл задания (копировать
    файлом, sha256 начинается с `95AE30420C5817D9`);
  - `task\tests\desk_wizard_prepare_addition.py`,
    `task\browser_tests\desk_wizard_prepare_addition.py` — дописки к двум тестам desk;
  - `h5v1.diff` — полный diff копии против репозитория (16 файлов);
  - `mutants.py`, `mutants.log`, `mutants_old_only.log` — мутанты и их результаты.
- Среда: Windows 11, Python 3.12.14 (`.venv`), node и Chromium из окружения. macOS/Linux и CI не
  запускались. Настоящих провайдеров, аккаунтов, ключей и сети не было.

## 0. Итог

1. **Один предикат уже есть, и флаг ничего не открывает.** Двери плана, preview automation,
   authorize, отказ транспорта до claim, сам spawn и checker спрашивают одно и то же:
   `AttemptLaunch._road_covers`, а в нём клаузу `not self._signed_in_road()`. Runner спрашивает
   `login_loan_provided()` только для ключа `login`, а транспорт этот ключ передать не может:
   его `AttemptFolders` состоит из `work, home, install`. Значит, `LOGIN_LOAN_OPEN = True` в
   production не открывает ничего. Это подтверждено пробой на текущем коде для четырёх harness со
   входом по подписке при закрытом и открытом флаге (раздел 1.3).
2. **Слабые места.** Клауза подписки безымянна. Ни один тест не ловит её связывание с флагом
   (мутант M2 переживает все существующие тесты). Ни один тест не ловит, что дверь начала читать
   флаг (M9 тоже переживает). Docstring `login_loan_provided` утверждает, что это «факт, который
   спрашивает дверь», и это неправда.
3. **Честный текст без нового кода отказа, без нового поля API и без нарушения заморозки**
   (раздел 2). Причина называется в четырёх местах:
   - `conduct providers` — две строки сразу под выбором способа входа;
   - экран «Агенты» — текст строки «Подписка» (EN/RU);
   - мастер desk, звено «Запуск» — своя фраза (EN/RU) вместо `service_refused`. Ключ берётся из
     уже существующего поля отказа `detail.sandbox`;
   - квитанция транспорта — новая фраза о подписке, но только когда вход — единственная причина.
     Плюс слова runtime для неё в `failure_reasons`.

   Сообщение HTTP-отказа двери плана не меняется: оно привязано к набору полей reviewed fact.
   Назвать в нём причину можно только новым additive-полем `reason`. Это опция **S-H5-D2 для
   Codex** (раздел 2.4); для V1 она не обязательна.
4. **Код.** Клауза получает имя `_login_road_covered()` с решением H5-V1 в docstring. Остальная
   часть `_road_covers` становится `_launch_covers(mode)`. Исправляются docstrings
   `process_boundary` и `process_loans`. Значение `LOGIN_LOAN_OPEN` не меняется.
5. **Проверено на копии.** Новый файл: 36 тестов зелёные. Затронутые наборы: 675 passed и 1
   skipped, плюс `test_process_login_closed.py` (8 passed, отдельным процессом). Новый
   browser-тест: 2 passed. Красная фаза: 19 тестов красные ровно там, где ожидалось. Мутанты: 13
   из 13 ведут себя как ожидалось (раздел 3.2).

## 1. Где решается «subscription road внутри boundary не покрыт»

### 1.1 Путь вопроса (HEAD `a8e6baa`)

| Где | Что спрашивает | Источник |
| --- | --- | --- |
| Дверь плана (POST runs и graph) | `http_writes._judge_plan` → `http_holds._sandboxes_are_provided` → `containment.node_boundary` → `AdapterRegistry.execution_boundary` → `adapter.boundary_provided(mode)` | `http_writes.py:581-603`, `http_holds.py:150-183`, `containment.py:502-534`, `base.py:675-691` |
| Authorize (Confirm, policy) | `authorize_holds._hold_node_sandbox_is_provided`, тот же registry | `authorize_holds.py:151-193`, `241-242` |
| Preview automation | `policy_preview._hold_capabilities`, тот же registry | `policy_preview.py:90-103` |
| Транспорт | `boundary_provided` = confine ∧ платформа ∧ `_road_covers`; `_road_covers` = `not self._signed_in_road()` ∧ вход runner ∧ install-папка | `harness_attempt.py:142-166` |
| Отказ до claim | `_boundary_refusal`: dispatch (`headless_cli.py:406`), review (`artifact_transport.py:340`) | `harness_attempt.py:181-189` |
| Сам spawn | `_attempt` → `_hold_boundary` (тот же `_road_covers`) **до** `owned_login_attempt` (lease) | `harness_attempt.py:191-215`, `login_lifetime.py:43-50` |
| Checker | `_hold_checker_boundary` → `boundary_provided("review")` | `independent_transport.py:20-23`, `artifact_transport.py:771` |
| Launcher → runner | `_run_confined` строит `harness_attempt.AttemptFolders(work, home, install)`; `ProcessRunner._loaned` берёт `login` через `getattr(..., None)` | `harness_attempt.py:52-67`, `347-364`; `process.py:475-503` |
| Runner | `FolderLoans.targets` отказывает ключу `login`, пока `login_loan_provided()` ≠ True | `process_loans.py:376-378`, `process_boundary.py:36-52` |

- `process_boundary.AttemptFolders` с полем `login` в `src` не используется никем. Его строят
  только тесты аренды (`tests/login_gate.py`, `test_process_login_*`).
- Имена `LOGIN_LOAN_OPEN` и `login_loan_provided` читают в `src` только `process_boundary.py` и
  `process_loans.py`.

### 1.2 Вывод

- Двери, отказ до claim, spawn и checker отвечают **одним** предикатом (`_road_covers`).
  Расхождения «дверь пропустила, launcher отказал после claim» нет.
- Gate runner — **другой механизм** (аренда login-home), а не второй ответ на тот же вопрос. Из
  production он недостижим. После H5-V1 он остаётся вторым, независимым замком: даже если кто-то
  протянет `login`, runner откажет до profile и журнала.
- Путей, где `LOGIN_LOAN_OPEN = True` что-то открывает в production, нет. Флаг влияет только на
  тесты аренды, которые вызывают `FolderLoans` и `container_profile` напрямую с
  `process_boundary.AttemptFolders(login=...)`.

### 1.3 Проба на текущем коде (без правок)

Scratch-файл вне репозитория: четыре harness (Claude Code, Codex, Grok Build, Kimi Code)
переводятся на подписку через `replace(adapter._pin, auth="subscription", auth_home=...)`,
каждый при `LOGIN_LOAN_OPEN` False и True. Результат: **19 passed**. Для каждого случая:

- `boundary_provided` ложно в обоих режимах, registry тоже отвечает `False`;
- `run_once` даёт `failed` с `boundary_detail`;
- 0 spawn у фейка, `runner.entries == runner.runs == []`;
- `login_write_guard` не входил, claim-маркера нет, home не создан, login-каталог пуст.

API-key road у всех пяти harness покрыт в обоих режимах при обоих значениях флага. Мутант «без
клаузы входа» в памяти даёт `True`.

Базовые прогоны на HEAD: `test_adapter_boundary_launch`, `test_execution_boundary_refusal`,
`test_production_door_boundary`, `test_adapter_boundary_roads`, `test_failure_reasons`,
`test_provider_setup_login`, `test_execution_boundary` — 218 passed, 1 skipped.
`test_process_login_closed.py` отдельным процессом — 8 passed; его нативный тест здесь проходит.

## 2. Честный текст отказа (вопрос 6 R2)

### 2.1 Что пользователь видит сейчас (harness настроен на подписку, Windows)

| Поверхность | Сейчас |
| --- | --- |
| `conduct providers` | «How does X sign in? 1 its own subscription login…, 2 a credential…». Без оговорок; подписка — пункт 1 |
| «Агенты» (Studio) | «Подписка» · «Настроена собственная авторизация провайдера в отдельном каталоге.» / «Configured to use the vendor's own login, kept in its own directory.» |
| Мастер desk, шаг 5, звено «Запуск» (`POST runs`) | «Сервер отказал на этом звене: service_refused.» / «The server refused this link: service_refused.» и кнопка «Повторить» |
| HTTP API (`POST runs`, graph) | 409 `service_refused`, «step 'X' demands sandbox route 'execution-boundary' that this build does not provide», detail `{run_id, node_id, sandbox}` |
| Confirm (authorize) | `authorization_refused`, фиксированный текст (`api_contracts.py:483-484`) |
| Preview automation | `contract_invalid`, фиксированный текст (`api_contracts.py:492-493`) |
| Квитанция, если двери обойдены (например, run авторизован до перевода на подписку) | «the execution boundary is not provided for this Claude Code attempt on this build, so no task was spawned». У runtime для неё слов нет (`failure_reasons.REASONS`) |
| Checker | `verify_holds.CHECKER_BOUNDARY_UNAVAILABLE` (без причины) |
| Studio, страница run | «Командная служба отклонила запрос.» (только код) |

Слово «subscription» не появляется нигде на пути отказа. Документация (`first-run-v1*`, раздел
«Где задачи исполняются в этой сборке») цитирует HTTP-фразу, но в desk пользователь её не видит:
панель показывает только код.

### 2.2 Ограничения словаря

- Коды отказов (`api_refusals.ERROR_STATUS`) и конверт `{code, message, detail}` заморожены
  (`tests/test_cockpit_command_api_freeze.py`: `EXPECTED_ERROR_CODES`, `refusal_shape`). Новый
  код не нужен и не вводится.
- Сообщение с деталью допускается, только если оно совпадает с reviewed fact
  (`_reviewed_fact`: `message == sentence(detail)`), а набор полей задаёт строку таблицы
  `_REVIEWED_FACTS`. Поэтому HTTP-фразу двери нельзя дополнить причиной без нового набора полей.
- Строка двери плана в C/API-0 (`docs/specs/2026-08-13-cockpit-command-api.md`) не заморожена.
  Тесты закрепляют detail ровно из трёх полей (`test_execution_boundary_refusal.py:111-113`,
  `test_execution_boundary.py:78`). Docstring этого теста: «No new code enters the refusal
  vocabulary».
- Фразы квитанций — проза адаптера (`harness_profile`): «a refactor may move a promise, and may
  not reword one». **Новая** фраза — не переформулировка, а additive. Runtime узнаёт фрагменты по
  таблице, и тест держит каждый фрагмент против исходника транспорта.
- Копия панели (`desk-wizard-copy.js`, `studio-agents-copy.js`) — не контракт. Тесты требуют
  EN и RU с одинаковыми параметрами и запрещают имена вендоров в модулях мастера.

### 2.3 Решение: назвать причину там, где её можно знать, без нового кода и поля

Правило `docs/v1-v2-scope.md` («additive fields and explicit live refusals, not silent
reinterpretation») соблюдается так:

- отказ остаётся явным и живым, на тех же дверях и до любого побочного эффекта;
- коды, конверт и наборы полей не меняются; ничего не переосмысляется;
- добавляется только новое: ключ копии, фраза квитанции, строки CLI, строка таблицы слов
  runtime.

Точность по поверхностям:

| Поверхность | Что знает | Текст |
| --- | --- | --- |
| `conduct providers` | что выбран вход 1 | правило V1 до того, как выбор сделан |
| «Агенты» | `auth = subscription` у строки | правило V1 для этой строки |
| desk «Запуск» | только `sandbox = execution-boundary` | три условия V1 (Windows, API-ключ, папка `harnesses`) |
| Квитанция | точную причину | о подписке — **только** если вход единственный недостающий факт; на Linux/macOS и при сборке вне `harnesses\<имя>\<версия>` — прежняя фраза без причины |

Обоснование «только если единственный»: на Linux совет «используйте API-ключ» был бы ложным, а
при сборке вне дерева неполным.

Тексты (точные):

- Квитанция (EN, проза адаптера; RU нет, как у всех квитанций): «this {tool} connection signs
  in with a subscription, and in this version a task runs inside the execution boundary only with
  an API key, so no task was spawned».
- Слова runtime: «a subscription login does not run tasks inside the execution boundary in this
  version».
- `conduct providers` (CLI только EN), две строки под пунктами 1 и 2:
  «  In this version only 2 runs tasks inside the execution boundary (on Windows);» и
  «  with 1 the quotas are read and every task is refused before it starts.»
- «Агенты», `agents.auth_subscription`:
  - EN: «Configured to use the vendor's own login, kept in its own directory. In this version it
    only reads quotas: a task runs inside the execution boundary only with an API key.»
  - RU: «Настроена собственная авторизация провайдера в отдельном каталоге. В этой версии она
    служит только для чтения квот: задача исполняется в изоляции только с API-ключом.»
- Мастер desk, `wizard.chain.boundary`:
  - EN: «This step needs the isolation (execution boundary), and this computer cannot give it to
    the agent chosen, so nothing was started. In this version a task runs in the isolation only on
    Windows, only for an agent that signs in with an API key (not a subscription), and only from a
    build installed under ...\harnesses\<name>\<version>\.»
  - RU: «Этому шагу нужна изоляция (execution boundary), а выбранному агенту этот компьютер её
    дать не может, поэтому ничего не запускалось. В этой версии задача исполняется в изоляции
    только на Windows, только у агента со входом по API-ключу (не по подписке) и только из сборки,
    установленной в ...\harnesses\<имя>\<версия>\.»

### 2.4 S-H5-D2 (опция, **для Codex**): additive-поле `reason` в отказе двери плана

Нужна, только если owner hands-on покажет, что фразы desk из трёх условий мало.

- `api_refusals`: закрытый список `BOUNDARY_REASONS = ("subscription_login",)`.
  - Новая строка `_REVIEWED_FACTS`: `("service_refused", ("run_id", "node_id", "sandbox",
    "reason"), …)`, текст «step 'X' demands sandbox route 'execution-boundary' that this build
    does not provide: subscription_login».
  - Ветка проверки в `_reviewed_fact`: `sandbox == BOUNDARY_ROUTE`, `reason` из списка.
  - Параметр `reason=None` у `plan_sandbox_unprovidable`.
- Seam адаптера `boundary_refusal_reason(mode)`: «subscription_login» при том же условии
  `login_only`, что в разделе 4. Registry: `execution_boundary_reason(adapter_id, mode)`,
  fail-closed `None`. `containment`: причина для участников шага. `http_holds` / `http_writes`:
  передать seam.
- Desk ничего нового не делает: он уже рисует `detail.reason` («service_refused ·
  subscription_login»). По желанию — фраза `wizard.chain.boundary_subscription`.
- Заморозку это не нарушает: коды и конверт те же, добавляется строка reviewed facts. Но это
  изменение API-поверхности: дописать актуальный контракт API, разделить параметр
  `SUBSCRIPTION` в `test_execution_boundary_refusal.py`. Объём — около дня Sonnet.
- Рекомендация Opus: в V1 не делать. Причину пользователь получает из «Агентов», CLI и фразы
  desk; квитанция её называет.

## 3. Тесты и мутанты

### 3.1 Покрытие требований (а)–(г)

Все тесты, кроме отмеченных, — в новом `tests/test_subscription_road_boundary.py`.

| Требование | Тест |
| --- | --- |
| (а) флаг не открывает дорогу на двери и в транспорте | `test_every_door_refuses_the_subscription_road_whatever_the_runners_gate` (4 harness × флаг): `boundary_provided` и registry — `[False, False]`, `runner.entries == runs == []`, 0 spawn |
| (а) в runner | `test_the_transport_names_no_login_home_so_no_transport_reaches_the_runners_gate` (поля `AttemptFolders` и единственный вызов в `harness_attempt` по AST); `test_only_the_runners_loan_reads_its_gate_and_no_door_asks_it` (по AST: имена флага читают только `process_boundary` и `process_loans`) |
| (б) до любого побочного эффекта | `test_a_subscription_dispatch_is_refused_before_any_claim_home_lease_or_spawn` (4 × флаг): `failed`, 0 spawn, `entries`/`runs`/`events` пусты, lease не входил, нет claim, нет home, login-каталог пуст; `test_a_road_that_skips_the_question_still_cannot_spawn_on_the_subscription_road` (оба режима, `BoundaryUnavailable` до lease); `test_a_subscription_checker_is_refused_before_it_spawns` |
| (в) API-key road покрыт | `test_the_api_key_road_on_windows_stays_covered_whatever_the_runners_gate` (5 harness × флаг); `test_an_api_key_dispatch_with_the_runners_gate_open_names_no_login_home` |
| (г) причина названа | `test_the_subscription_sentence_names_the_login_mode_and_the_runtime_words_for_it`; `test_where_the_platform_has_no_boundary_the_login_is_not_named` (linux, darwin); `test_a_build_installed_outside_the_tree_is_not_blamed_on_the_login` |
| (г) EN/RU в панели и CLI | `tests/test_studio_agents_i18n.py` (+2 assert); `tests/test_desk_wizard_prepare.py` (модель, +1 тест); `browser_tests/test_desk_wizard_prepare.py` (+1 тест, ru и en); `tests/test_provider_setup_login.py` (+2 assert) |

Красная фаза проверена на чистой копии: добавлены функция `subscription_boundary_detail` и все
тесты, остальной код не тронут. Результат — **19 failed**, и все падения ожидаемые:

- 8 случаев (б) — фраза квитанции;
- тест фразы и слов runtime;
- `test_the_subscription_road_is_not_provided_and_is_refused_before_it_spawns`;
- 4 случая `test_provider_setup_login`;
- модельный тест desk;
- 2 случая «Агентов»;
- 2 browser-теста.

Остальные новые тесты зелёные с самого начала: они закрепляют текущее поведение и убивают
мутанты.

### 3.2 Мутанты (на копии, `mutants.py`)

| Мутант | Новые тесты | Только прежние тесты |
| --- | --- | --- |
| M1 `_login_road_covered` всегда True | убит | убит |
| M2 `_login_road_covered` = прежнее **или** `login_loan_provided()` | убит (параметр gate-open) | **выжил** |
| M3 `LOGIN_LOAN_OPEN = True` в исходнике | выжил — так и задумано: дорога от флага не зависит | — |
| M3b то же, тест `test_process_login_closed.py` | убит | убит |
| M4 `_hold_boundary` без вопроса о дороге | убит | убит (тесты install-папки) |
| M5 dispatch без `_boundary_refusal` | убит | убит |
| M6 квитанция никогда не называет вход | убит | — |
| M7 квитанция называет вход при любой причине | убит | — |
| M8 `AttemptFolders` транспорта получает `login` | убит | убит |
| M9 дверь (`base.py`) импортирует `login_loan_provided` | убит | **выжил** |
| M10 нет строки в `failure_reasons` | убит | — |
| M11 `conduct providers` молчит | убит | — |
| M12 desk теряет `detail.sandbox` | убит | — |

## 4. ЗАДАНИЕ ДЛЯ SONNET: S-H5-D

> Решение владельца H5-V1 принято. Реализация — вариант D: подписка внутри изоляции честно
> отказывает, дверь и launcher отвечают одним предикатом, текст называет причину. Аренду
> login-home **не открывать**.

### 4.1 Рамки

- Ветка `recovery/2026-10-20`. Сначала `git status` и `git log -1`. Сверь 16 файлов из
  `h5v1.diff` с HEAD: строки «до» в `apply_to_copy.py` должны найтись ровно по одному разу. Если
  что-то не совпало, остановись и сообщи; дизайн писан по `a8e6baa`.
- Каждая команда PowerShell начинается с
  `. "C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command-Environment.ps1" -Quiet`.
- pytest: `python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\pt-<≤4>`.
  Свои `pt-*` удаляй.
- Нативные AppContainer-тесты — по одному файлу на процесс. Полный suite и gate не запускать.
- Мутанты — только на копии в `C:\Users\Пользователь\Documents\Codex\work\<имя>\`.
- Лимиты: файл ≤ 800 строк; в файлах `CAPPED` строка ≤ 100 символов; один `\n` в конце; без
  хвостовых пробелов. В JS-модулях мастера функция ≤ 50 строк, имён вендоров нет.
- **Не делать:**
  - не менять значение `LOGIN_LOAN_OPEN` и логику `FolderLoans.targets`;
  - не добавлять `login` в `harness_attempt.AttemptFolders`;
  - не трогать `api_refusals.py`, коды, конверт и detail двери плана (S-H5-D2 — только по
    решению Codex);
  - не трогать документацию владельца (`docs/owner-acceptance*`, `docs/first-run-v1*.md`,
    `docs/release-smoke.md`, `CONTRIBUTING*.md`, `README*.md`, `R5-PLAN.md`,
    `tasks/R5-WINDOWS-WHEEL-ROAD.md`) и `tests/test_command_line_cap.py`;
  - без коммитов, push, stash, checkout, reset, git config;
  - без настоящих провайдеров, аккаунтов, ключей и сети.

### 4.2 Шаг 1 — тесты (красные первыми)

1. Скопируй файлом
   `C:\Users\Пользователь\Documents\Codex\work\h5v1-design\task\tests\test_subscription_road_boundary.py`
   в `tests/` (246 строк, все ≤ 100 символов). Его 36 тестов перечислены в разделе 3.1.
   - Приём `replace(adapter._pin, auth="subscription", auth_home=...)` работает у всех четырёх:
     их `_login()` читает `self._pin`.
   - Lease ловится подменой `ProcessRunner.login_write_guard`.
2. `tests/test_adapter_boundary_launch.py`:
   - импорт `from conductor.command.adapters.harness_profile import (boundary_detail,
     subscription_boundary_detail)` (две строки);
   - в `test_the_subscription_road_is_not_provided_and_is_refused_before_it_spawns` ожидать
     `subscription_boundary_detail(adapter.profile.tool_noun)`.
3. `tests/test_provider_setup_login.py`, тест
   `test_the_login_question_is_put_only_where_a_login_is_driven`:
   - в ветке `if`: `assert "only 2 runs tasks inside the execution boundary" in said, said`;
   - в ветке `else`: `assert "execution boundary" not in said, said`.
4. `tests/test_studio_agents_i18n.py`, после assert про «Платёжный аккаунт неизвестен»:

   ```python
       # H5-V1: a subscription row says it only reads quotas and tasks need an API key.
       reads = "только для чтения квот" if locale == "ru" else "it only reads quotas"
       key = "только с API-ключом" if locale == "ru" else "only with an API key"
       assert reads in result["text"] and key in result["text"]
   ```

5. Допиши в конец `tests/test_desk_wizard_prepare.py` содержимое
   `task\tests\desk_wizard_prepare_addition.py`. Это тест
   `test_a_plan_door_that_cannot_provide_the_boundary_stops_at_the_run_and_names_the_route`:
   отказ `prep_run` с detail `{run_id, node_id, sandbox: "execution-boundary"}` даёт refusal
   `{job: "run", link: "run", code: "service_refused", reason: "execution-boundary"}`, а отказ
   без detail оставляет `reason: null`.
6. Допиши в конец `browser_tests/test_desk_wizard_prepare.py` содержимое
   `task\browser_tests\desk_wizard_prepare_addition.py`. Это тест
   `test_a_step_the_boundary_cannot_carry_says_why_in_a_sentence_of_its_own[ru|en]`: текст
   `[data-refusal-link="run"]` равен `bench.say("wizard.chain.boundary")`, а
   `runs_written == 0`.
7. Добавь в `harness_profile.py` одну функцию из шага 2.2 и прогони пункты 1–6. Ожидается ровно
   19 красных (раздел 3.1). Остальные новые тесты зелёные. Сохрани вывод для отчёта.

### 4.3 Шаг 2 — код (точно как в `apply_to_copy.py` и `h5v1.diff`)

2.1. `src/conductor/command/adapters/harness_attempt.py` (в `CAPPED`, ≤ 100 символов).

Импорт: `from .harness_profile import boundary_detail, subscription_boundary_detail`.

В docstring `boundary_provided` первый абзац заменяется таким:

```text
        False for a transport never confined, false on the subscription road
        (``_login_road_covered``), false when the runner this transport holds has no entry that
        takes the call it would make (``boundary_entry``), and false when the pinned build's
        install folder cannot be named from its path (``find_install_folder``): such an attempt
        is refused, never run without the boundary and never sent on to fail after the attempt
        was claimed. Each of these is a fact the transport holds before any claim, so the doors
        and the transport answer alike.
```

`_road_covers` заменяется тремя методами:

```python
    def _road_covers(self, mode: str) -> bool:
        """Whether the road this transport holds can carry a confined attempt of this mode.

        Apart from the platform: the login it holds (``_login_road_covered``) and the launch
        (``_launch_covers``).
        """
        return self._login_road_covered() and self._launch_covers(mode)

    def _login_road_covered(self) -> bool:
        """Whether the login this transport holds may start a task inside the boundary.

        The API-key road may. The subscription road may not, in V1: the owner's decision H5-V1
        of 21.10.2026 (``docs/recovery/2026-10-20/OPEN-DECISIONS.md``). Its child would need
        rights on the operator's login home, where the vendor keeps executable configuration
        that runs again outside the boundary, and no attempt is given any.

        This is the ONE answer for that road: the doors (``boundary_provided``), the refusal
        before the claim (``_boundary_refusal``), the spawn (``_hold_boundary``) and the checker
        all reach it through ``_road_covers``. ``process_boundary.LOGIN_LOAN_OPEN`` is not part
        of it: that is the runner's own gate on a login home, and no transport names one
        (``AttemptFolders`` has no such field), so opening it opens nothing here.
        """
        return not self._signed_in_road()

    def _launch_covers(self, mode: str) -> bool:
        """A runner whose entry takes the call, and a pinned build whose install folder the
        boundary can be asked to grant."""
        return (entry_takes_the_call(self._runner, mode)
                and find_install_folder(self._argv_prefix()[-1]) is not None)
```

Хвост `_boundary_refusal` (docstring дополняется одной фразой):

```python
        refusal spawns nothing, borrows no login and creates no folder, home or marker. Where
        the login is the one fact missing (the platform has the boundary and the launch is
        covered), the receipt names it (H5-V1); otherwise it names no cause.
        """
        if not self._confine or self.boundary_provided(mode):
            return None
        tool = self.profile.tool_noun
        login_only = (not self._login_road_covered() and self._launch_covers(mode)
                      and boundary_provided(self._boundary_platform, mode))
        detail = subscription_boundary_detail(tool) if login_only else boundary_detail(tool)
        return self._receipt(request, "failed", None, detail)
```

`_hold_boundary` не меняется: он уже спрашивает `_road_covers`.

2.2. `src/conductor/command/adapters/harness_profile.py` — сразу после `boundary_detail`:

```python
def subscription_boundary_detail(tool: str) -> str:
    """A task attempt refused because this transport signs in by subscription (H5-V1).

    Said only where the login is the one fact missing: the platform has the boundary and the
    launch would be covered (``AttemptLaunch._boundary_refusal``). It names the login MODE, a
    word the operator's own configuration and the Agents screen already show, and no directory,
    account or vendor detail. In V1 a task runs inside the boundary only on the API-key road
    (the owner's decision H5-V1 of 21.10.2026).
    """
    return (f"this {tool} connection signs in with a subscription, and in this version a task "
            "runs inside the execution boundary only with an API key, so no task was spawned")
```

2.3. `src/conductor/command/failure_reasons.py` — после строки `"reports no subscription"`:

```python
    ("runs inside the execution boundary only with an API key",
     "a subscription login does not run tasks inside the execution boundary in this version"),
```

2.4. `src/conductor/command/adapters/process_boundary.py` — только комментарии и docstrings,
значения не трогать.

- Последнее предложение комментария `LOGIN_LOAN_OPEN` («A review ruling … nothing else does»)
  заменяется таким:

  ```text
  #: spawns that stand outside the boundary: a status read, a quota read, a sign-in. In V1 it stays
  #: closed (the owner's decision H5-V1 of 21.10.2026). It is the runner's own gate and opens no
  #: road: whether a transport may start a task on the subscription road is answered by the
  #: transport (`AttemptLaunch._login_road_covered`, False in V1), and no transport names a login
  #: home, so only the loan's own tests reach this gate (`tests/login_gate.py`).
  ```

- Docstring `login_loan_provided`:

  ```text
      """Whether the runner loans a leased login home: the runner's own gate, and no door's.

      Only the boolean True counts as open. The runner refuses a login home with this answer `False`
      (`ProfileRefused`, before any profile, journal record or change exists). No door asks it and
      no transport names a login home (`harness_attempt.AttemptFolders` has no `login`), so it is
      not a second answer about the subscription road: that answer is the transport's alone.
      """
  ```

- В docstring `AttemptFolders` фраза про `login`:

  ```text
      executable and what it loads. `login` is the ABSOLUTE login home the attempt holds under the
      shared login lease, and None otherwise; no transport names one (in V1 the subscription road
      is refused before any claim, H5-V1). Nothing here grants anything: the runner checks each
      folder, takes the login home only if the attempt's own lease names it, and its journal grants
      and returns it (`process_loans`). A `login` is refused while `login_loan_provided()` is
      False, and it is, as shipped.
  ```

2.5. `src/conductor/command/adapters/process_loans.py`, docstring модуля: фраза «A login home
is refused, before anything exists, until a review ruling says which objects of it the attempt
may write.» заменяется на «A login home is refused, before anything exists. In V1 it stays
closed (the owner's decision H5-V1 of 21.10.2026), and no transport names one: the subscription
road is refused by the transport before any claim.» Переносы — как в `h5v1.diff`.

2.6. `src/conductor/provider_setup.py`, `_ask_login`, сразу после строки пункта 2:

```python
    _say("  In this version only 2 runs tasks inside the execution boundary (on Windows);")
    _say("  with 1 the quotas are read and every task is refused before it starts.")
```

2.7. Панель.

- `desk-wizard-prep.js`, `landWrite`:

  ```js
    // The word that says why, or the sandbox route a plan door could not provide.
    const detail = result.payload?.error?.detail ?? result.payload?.detail;
    return refusedAt(base, jobName(ask), code, detail?.reason ?? detail?.sandbox ?? null);
  ```

  Форма refusal остаётся `{job, link, code, reason}`: существующий тест сравнивает её целиком.

- `desk-wizard-prepare-view.js`. После `SENTENCES`:

  ```js
  //: The route a plan door refuses that has a sentence of its own: the execution boundary, which
  //: in this version only a connection with an API key on Windows has (H5-V1).
  const ROUTES = Object.freeze({"execution-boundary": "wizard.chain.boundary"});
  ```

  В `refusalNote` выбор ключа:

  ```js
    const route = refusal.code === "service_refused" && typeof refusal.reason === "string"
      && Object.hasOwn(ROUTES, refusal.reason) ? ROUTES[refusal.reason] : null;
    const key = Object.hasOwn(SENTENCES, refusal.code) ? SENTENCES[refusal.code]
      : route ?? "wizard.chain.refused";
  ```

- `desk-wizard-copy.js`: ключ `wizard.chain.boundary` после `wizard.chain.refused`. Тексты EN и
  RU — из раздела 2.3, собраны через `+` по образцу соседних ключей. Обратные слэши в JS
  удваиваются (`...\\harnesses\\<name>\\<version>\\.`). Фигурных скобок нет: это не параметры.
- `studio-agents-copy.js`: `agents.auth_subscription` — тексты EN и RU из раздела 2.3, каждый
  одной строкой, как остальные строки файла.
- `studio-people.js`: `AUTH_MEANINGS.subscription` — тот же EN, через `+` в три строки. Ключи не
  меняются: `test_studio_runs` проверяет только их.

### 4.4 Шаг 3 — прогоны (после зелёного)

1. Не-нативные, одним процессом (около 5 минут на копии):

   ```text
   tests/test_subscription_road_boundary.py tests/test_adapter_boundary_launch.py
   tests/test_execution_boundary_refusal.py tests/test_production_door_boundary.py
   tests/test_adapter_boundary_roads.py tests/test_failure_reasons.py
   tests/test_provider_setup_login.py tests/test_provider_setup.py tests/test_execution_boundary.py
   tests/test_harness_profile.py tests/test_command_isolation_facts.py
   tests/test_harness_subscription_login.py tests/test_studio_runs.py
   tests/test_studio_agents_i18n.py tests/test_studio_i18n.py tests/test_studio_source.py
   tests/test_studio_module_graph.py tests/test_desk_wizard_prepare.py
   tests/test_desk_wizard_copy.py tests/test_desk_wizard_source.py tests/test_desk_wizard_resume.py tests/test_desk_function_map.py
   tests/test_desk_docs_map.py tests/test_server_panel_assets.py tests/test_command_line_cap.py
   ```

   На копии этот список без трёх последних desk/panel-файлов дал 675 passed и 1 skipped. Новый
   файл отдельно — 36 passed. `test_desk_function_map` и `test_server_panel_assets` — зелёные.
   `test_desk_docs_map` на копии не проверялся: у копии нет `docs/`. В репозитории он должен
   быть зелёным.
2. Не-нативные тесты аренды, одним процессом. Изменились только docstrings, это проверка на
   регрессию:

   ```text
   tests/test_process_loans.py tests/test_process_loans_scope.py
   tests/test_process_loans_recovery.py tests/test_process_loans_overlap.py
   tests/test_login_leased_home.py
   ```

3. С нативными частями — **по одному файлу на процесс**:
   - `tests/test_process_login_closed.py` (обязательно; на HEAD 8 passed);
   - по желанию `tests/test_process_login_refusals.py`, `tests/test_process_login_grant.py`.
4. Browser: `browser_tests/test_desk_wizard_prepare.py -k "boundary or refusal_stops"` (на
   копии 4 passed).
5. Проверь лимиты для всех изменённых файлов: строки ≤ 100 в `CAPPED` и в новом файле, один `\n`
   в конце, нет хвостовых пробелов. Число строк длиннее 100 в `desk-wizard-copy.js` (7) и
   `studio-people.js` (5) расти не должно.

### 4.5 Шаг 4 — мутанты (на копии вне репозитория)

Копия — `C:\Users\Пользователь\Documents\Codex\work\h5v1-s\` (`src`, `tests`, `pyproject.toml`
после твоих правок). Запускать с `PYTHONPATH=<копия>\src` из корня копии. Готовый образец —
`h5v1-design\mutants.py` (13 мутантов, восстанавливает файл после каждого). Ожидание:

- убиты M1, M2, M3b, M4–M12;
- M3 (`LOGIN_LOAN_OPEN = True` в исходнике) **выживает** на новых тестах. Это доказательство
  независимости дороги от флага, а не дыра: его убивает `test_process_login_closed.py`.

Дополнительно приложи M2 и M9 против одних прежних тестов: оба должны выжить. Это довод, зачем
нужен новый файл.

### 4.6 Отчёт Sonnet

`tasks/H5-V1-REPORT.md` (по `TASK-REPORT-TEMPLATE.md`):

- diff-stat;
- красная фаза (19) и зелёная;
- команды и результаты каждого прогона;
- таблица мутантов;
- что в `CAPPED`;
- список правок документации (раздел 5).

В `CAPPED` нужно добавить `"tests/test_subscription_road_boundary.py"` (сам файл
`test_command_line_cap.py` не редактировать, только указать). `harness_attempt.py` и
`test_adapter_boundary_launch.py` уже там.

## 5. Что указать для документации (правит другой workflow, не Sonnet)

- `docs/first-run-v1.md` и `.en.md`, раздел «Где задачи исполняются в этой сборке»:
  - «Можно ли сделать вход по подписке безопасным… пока не решено» заменить на: «Решение
    владельца H5-V1 (21.10.2026): в V1 задачи исполняются только по API-ключу; вход по подписке
    внутри изоляции — после V1; подписка в V1 нужна только для чтения квот».
  - В таблицу «Шаг отказывает» добавить фразу desk (`wizard.chain.boundary`, RU/EN) и фразу
    квитанции о подписке.
  - В таблице каталога (строки Claude Code/Codex/Kimi/Grok — «вход по подписке») оговорить:
    для задач в V1 нужен API-ключ (имя переменной в `env_allow`); на репетиции R5 проверяются
    Claude Code и Codex по API. Работу Grok/Kimi по API-ключу с настоящим вендором продукт не
    проверял.
  - В шагах `conduct providers` отразить две новые строки и рекомендовать пункт 2.
- `README.md` / `README.ru.md` (абзац 105–106): «does not yet run tasks» → «in V1 does not run
  tasks (decision H5-V1); after V1 …».
- `docs/owner-acceptance.md:231-232`: «the execution boundary does not yet carry that road» →
  ссылка на H5-V1; ожидаемая фраза в desk — `wizard.chain.boundary`.
- `docs/release-smoke.md` (около 465): рядом с HTTP-фразой двери — ожидаемая фраза desk и текст
  «Агентов» для подписки.
- `R5-PLAN.md` §3.3 п. 1: H5-V1 решено; реализация — S-H5-D (этот файл).
- `OPEN-DECISIONS.md`:
  - H5-C — вопрос 6 (текст отказа) закрыт этим дизайном без нового кода;
  - открыто: S-H5-D2 (поле `reason`), удалять ли аренду `login` после V1, где держать копию
    credentials в схеме B.
- `CONTRIBUTING*`: правок не требуется.

## 6. Для Codex

1. Утвердить: в квитанции появляется слово «subscription». Docstring `boundary_detail` говорит,
   что login road в квитанции не называется — так было задумано. Новая фраза — отдельная и
   additive, прежняя не переформулирована. Подписка называется только когда это единственная
   причина. Слово — режим входа из конфигурации, не путь и не аккаунт.
2. S-H5-D2 (раздел 2.4): делать ли в V1. Рекомендация — нет.
3. Побочная находка вне H5: `isolation_facts.no_operating_system_boundary` («This build … creates
   no container, no jail…», `isolation_facts.py:160-165`) после R5 на Windows неверна: задача
   идёт в AppContainer. Строка входит в замороженный контракт
   (`docs/specs/2026-09-09-controls-current-contract.md`). Нужна отдельная additive-правка
   (например, строка-факт о boundary по платформе) — решение Codex.
4. Остаточный пробел desk: если harness перевели на подписку уже **после** подготовки run,
   preview отказывает `contract_invalid`, а Confirm — `authorization_refused`. Мастер тогда
   говорит «The project has no owner present…» (`wizard.launch.refused.authorization_refused`),
   и это неверное объяснение. Пробел существовал и до H5. Чинить в V1 или нет — решение Codex.

## 7. Что проверено и что нет

- Прочитано:
  - `harness_attempt.py`, `process_boundary.py`, `process_loans.py` (`targets`), `process.py`
    (`container_profile`, `_loaned`);
  - `harness_profile.py`, `headless_login.py`, `login_lifetime.py`, `headless_cli.py`
    (`_dispatch`), `artifact_transport.py` (review, `verify_for`), `independent_transport.py`;
  - `execution_boundary.py`, `containment.py`, `http_holds.py`, `http_writes.py`,
    `authorize_holds.py`, `policy_preview.py`, `base.py` (`execution_boundary`),
    `api_refusals.py`, `api_contracts.py` (перевод исключений), `failure_reasons.py`,
    `isolation_facts.py`, `provider_setup.py`;
  - панель: `desk-wizard-prep.js`, `desk-wizard-prepare-view.js`, `desk-wizard-copy.js`,
    `desk-transport.js`, `studio-people.js`, `studio-agents-copy.js`, `studio-runstep.js`;
  - тесты из раздела 3 и `tests/_fakeboundary.py`, `tests/login_gate.py`.
- Запускалось: базовые прогоны на HEAD, проба (19), копия с дизайном (36 + 675 + 8 + 4 browser),
  красная фаза (19 failed, ожидаемые), мутанты (13). Прогон `test_desk_docs_map` на копии падает
  только из-за отсутствия `docs/` в копии.
- Не запускалось: полный suite и gate; нативные тесты аренды кроме
  `test_process_login_closed.py`; macOS/Linux; CI; настоящие vendor CLI.
