Итог: дизайн принят ведущим (владелец 30.10: «Делаем полностью») | кода нет | следующий шаг: G0b
(чтение строк бинаря и коммита 5115b46bc9), затем G2 и проба P с владельцем, затем TASK I0–I5.

Источники: workflow `wf_e2a79c47-89f` (два черновика, два скептика, синтез); G0 — `wf_d9412b0c-d14`.

# H5-GROK-DIAGNOSE: итоговый дизайн (синтез двух черновиков и двух разборов)

Обозначения: A = `src/conductor/command/adapters`, C = `src/conductor/command`, P =
`src/conductor/panel`, T = `tests`,
DC = `%USERPROFILE%\DecemberCommand`. G0 — последний (проверенный) результат grok-g0.txt. HEAD
14f94cf.
Пометки: [код] — по коду; [вендор] — по источнику vendor (дерево 19d42e35 = 1.0.6, бинарь 1.0.5,
поэтому бинарь
должен подтвердить); [гип] — гипотеза; [док] — по документу.

## 0. Решение и порядок
- V1-GROK-ROLE: Grok исполняет только role-diagnostician, то есть один read-only шаг `diagnose`
  (review,
  artifact-problems → artifact-causes) (docs/v1-v2-scope.md:42-46) [док].
  - Dispatch и роль проверяющего у Grok закрыты в коде на обеих дорогах: подписка и API-ключ.
  - Запасной путь — claude-code на diagnose.
- Что блокирует сегодня [код]:
  - у Grok нет review (A/grok_build.py:167-168);
  - канал задачи — argv `--single` (:331-334), а review требует stdin
    (A/artifact_transport.py:123-125);
  - у подписки нет relay (A/harness_attempt.py:183-201);
  - пин лежит вне `harnesses` (A/harness_attempt.py:88-106).
- Headless-режим не читает stdin ни в какой форме. Единственный канал не через argv — `--prompt-file
  <path>`:
  расширение любое, кроме ровно `json`; текст UTF-8, обрезается по краям; пустой текст — отказ
  [вендор, G0 Q1].
- Порядок gates, от дешёвых к дорогим. Любой красный gate: diagnose берёт claude-code, Grok идёт в
  следующий прогон.
  1. G0b — чтение без запуска.
  2. G2 — форма входа (выводятся только имена и числа).
  3. Решения ведущего.
  4. P — одна проба вне изоляции.
  5. I0–I5 — код.
  6. M — машина.
  7. Y — сборка и stage A.
  8. G6 — мини-прогон внутри изоляции.
  9. Точка заморозки, затем B.
- Принцип: в B Grok не встречает ничего, чего не было в G6. P стоит раньше кода, потому что может
  закрыть дорогу ценой
  одного запуска, а не 1,5–3 дней кода [гип].

## 1. Канал задачи `file`
**Интерфейс** (A/harness_profile.py:304-306, 522-525) [код]:
- Константы:
  - `TASK_CHANNEL_FILE = "file"`;
  - `TASK_CHANNELS = (argv, stdin, file)`;
  - `OFF_ARGV_CHANNELS = (stdin, file)`;
  - `TASK_FILE_NAME = "conduct-task.txt"` — ASCII, задаётся кодом, никогда не `.json`.
- Профиль отвергает совпадение этого имени с login_scratch, login_expected, login_credentials,
  login_forbidden и
  `login_relay.files`.
- Seams те же, что у stdin:
  - `_stdin_argv(home, model)` — параметра задачи нет;
  - `_task_stdin(task) -> bytes`.
- Замены `== STDIN` на `in OFF_ARGV_CHANNELS` в четырёх местах:
  - A/headless_cli.py:173 и :503;
  - A/artifact_transport.py:19 и :124. Правка строка в строку, модуль занимает 797 из 800 строк.
- Новый A/task_file.py, около 60 строк: `path_in(home)`, `place(home, payload)`,
  `TaskFileRefused(ProcessRunnerError)`.

**Одна точка записи — `attempt_spec`** (A/headless_spec.py:21-55):
- Условие: канал `file`, `mode ∈ ATTEMPT_MODES` и `stdin_bytes is not None`.
- Тогда `place(home, stdin_bytes)`, а в CommandSpec уходит `stdin_bytes = None` (DEVNULL).
- Версия, статус входа и чтения квоты (`mode = None`) не затронуты.
- Параметр `task_file`, протянутый через `_attempt → _owned_attempt → _spawn`, отвергнут: он менял
  бы сигнатуры
  общего кода Claude и Codex.

**Где лежит файл** — `<home>\conduct-task.txt`, где home — дом попытки:
- Relay-дорога. Дом — `DC\relay\<key>\g-<16hex>`, он же GROK_HOME ребёнка. Порядок [код]:
  copy_in (пустой дом) → `_relay_spec` → **place** → вход в boundary → claim → run
  (A/relay_attempt.py:354-371, 373-387).
- Дом проекта `.grok-home/<id>` (API-ключ, фейки):
  - путь `_spawn → attempt_spec` (A/harness_attempt.py:438) идёт после claim (:299-303);
  - отказ place там даёт `unknown` с маркером. Это принимается и закрепляется тестом: Grok в V1 эту
    дорогу не
    использует, API-ключа у владельца нет.
- `place` отказывает, если home не прямой ребёнок `homes_root()` проекта и не relay-дом `g-<16hex>`
  (`relay_home.HOME_NAME`). Так файл задачи не попадёт в `logins\grok-build` или в work.

**Создание** [код]:
- Проверки: `0 < len ≤ STDIN_LIMIT` (256 КиБ, A/process.py:95); нет NUL; строгий UTF-8; текст не из
  одних пробелов.
- Запись:
  - `os.open(O_RDWR|O_CREAT|O_EXCL|O_BINARY, 0o600)`;
  - запись целиком, `lseek(0)`, чтение назад;
  - нужно: sha совпадает и `st_nlink == 1`.
- Любая ошибка `OSError`, `ValueError` или `UnicodeError` (open, write, read-back, unlink) →
  best-effort unlink и
  `TaskFileRefused`. Сырое исключение под lease отравило бы вход Grok до перезагрузки
  (A/relay_attempt.py:10-17).
- На relay-дороге отказ ловит `_relay_spec` (:386) и возвращает `NotStarted("spec")`. Это
  существующая фраза:
  claim нет, ребёнка нет.

**Удаление** [код]:
- `login_relay.discard` удаляет всё дерево дома (A/login_relay.py:672-701).
- `TASK_FILE_NAME` добавить к первым именам в `discard` и `sweep` (A/relay_attempt.py:231, 351):
  задача уходит
  вместе с копией входа даже тогда, когда дерево целиком удалить не удалось.

**argv** — постоянные токены плюс один абсолютный путь:
- Путь — функция дома: ключ проекта и случайный токен. В нём нет run, action и текста задачи.
- Прецедент — `-o <home>\last-message.txt` у Codex (A/codex_cli.py:619-651) [код].

**ACL только на чтение для файла не делаем:**
- Для него нужен SID профиля контейнера и пятый вид loan, а закон loan-ов запрещает расширение
  (A/process_loans.py:45-50) [код].
- Читатель один — ребёнок, и он читает файл один раз при старте [вендор].
- Права у файла те же, что у копии auth.json.

**Факт для гранта и панели:**
- `task_channel_fact(file) = {"channel": "file", "limit": STDIN_LIMIT, "unit": "utf8_bytes",
  "scope": "task"}`
  (C/policy_providers.py:48-62).
- Без поддержки в панели preview и controls любого прогона с Grok становятся null
  (P/studio-automation-providers.js:15-26; P/studio-controls.js:155) [код]. Нужно:
  - `CHANNELS.file`;
  - `automation.task_channel_file` (P/studio-automation-copy.js:15-16) и `run_docs.channel_file`
    (P/studio-run-docs-copy.js:36), каждый RU/EN.
- В квитанции нет ни пути, ни размера, ни digest файла. Набор значений для скана не меняется.

## 2. GrokRelay (новый A/grok_relay.py)
```
GROK_SCOPE = "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828"  # [вендор] issuer + публичный client id
GROK_RELAY = GrokRelay(kind="g", credential="auth.json", files=("auth.json",),
    secret_fields=("key", "refresh_token"), refresh_fields=("refresh_token",),
    section=GROK_SCOPE, form=(("refresh_token", None),), forbidden_env=GROK_FORBIDDEN_ENV)
```
**Почему `section = GROK_SCOPE`:**
- базовый strip работает без изменений (A/login_relay.py:260-270);
- у RelaySpec не появляется новых полей, поэтому digest Claude и Codex не меняется
  (C/policy_providers.py:31-34).

**Почему `form = None`, то есть поле удаляется:**
- `""` (образец Codex, A/codex_relay.py:58-59) даёт цепочку Some("") → OidcSession → invalid_grant →
  write_scope_removal. Сама цепочка — [вендор], ответ IdP — [гип].
- Без поля запись становится LegacySession и работает до `expires_at − 300 с` [вендор].

**admit, по порядку:**
1. Ровно одна запись, и ключ равен `GROK_SCOPE`, иначе `unknown_shape`.
2. Поля ⊆ GROK_AUTH_FIELDS, иначе `unknown_shape`.
3. auth_mode: `api_key` → `api_key`; любое значение, кроме `oidc`, → `foreign_credentials`.
4. key — непустая строка, иначе `no_access_token`.
5. refresh_token отсутствует, None или строка; expires_at и oidc_* — строки, если есть.
6. Если есть oidc_issuer и oidc_client_id, то `issuer.rstrip('/') + '::' + client_id` равно ключу,
   иначе `unknown_shape` [вендор Q2].
7. user_id непустой, иначе `account_unknown`.

**Остальные методы:**
- expires_at читается через `login_relay.clock_instant` (A/login_relay.py:493-506). Python ≥ 3.11
  принимает `Z` и
  дробь до 9 цифр (pyproject.toml:10). Время без зоны или отсутствие поля → `expiry_unknown`.
- account = user_id.
- bootstrap = {}: config.toml несёт marketplace, это исполняемая конфигурация, она не копируется.
- credman_refusal = None.
- oidc_* и expires_at сохраняются — это поправка G0 к карте.

**Буква `g`:** A/relay_home.py:52 `[cxg]` и текст :254-255; текст A/login_relay.py:184; копия в
T/test_relay_road_success.py:58.

**Цикл импорта** [код]:
- grok_build → artifact_transport → relay_env (A/grok_build.py:146; A/artifact_transport.py:25).
- Поэтому `GROK_AUTH_FIELDS` и `GROK_AUTH_CREDENTIALS` переезжают в grok_relay, а
  `GROK_LOGIN_OVERRIDES` — в
  relay_env как `GROK_ROUTE_ENV`. grok_build реэкспортирует их.

**GROK_FORBIDDEN_ENV** складывается из:
- GROK_ROUTE_ENV (6 имён, A/grok_build.py:462-463);
- GROK_AUTH, _PATH, _EARLY_INVALIDATION_SECS, _TOKEN_TTL, _PROVIDER_LABEL; GROK_LOCAL_AUTH;
- GROK_OAUTH2_{ISSUER, CLIENT_ID, PRINCIPAL_TYPE, PRINCIPAL_ID, SCOPES, REFERRER};
- GROK_OIDC_{SCOPES, AUDIENCE}; GROK_FORCE_LOGIN_TEAM_ID; GROK_DISABLE_API_KEY_AUTH;
- GROK_FOLDER_TRUST, GROK_TRACK_HEADLESS, GROK_WS_URL, GROK_WS_ORIGIN;
- GROK_TELEMETRY_{EVENTS_URL, EVENTS_API_KEY, MIXPANEL_TOKEN};
- COMMON_ROUTE_ENV [вендор Q2, Q8].

Вне списка остаются:
- четыре принудительных выключателя `0` (A/grok_build.py:181-186);
- RUST_LOG и GROK_DEBUG_LOG — они не меняют маршрут;
- GROK_CLAUDE_SKILLS_ENABLED и GROK_CURSOR_SKILLS_ENABLED: их принудительное `false` в V2 останется
  возможным без
  исключения в `_route_selected` (A/relay_attempt.py:270-277).

**Что ещё меняется [код]:**
- Объединение `SUBSCRIPTION_ROUTE_ENV` (A/relay_env.py:73) растёт. Это дверь конфигурации для всех
  подписочных строк
  (A/provider.py:338-343). Перед Y владелец печатает только ИМЕНА env_allow каждой строки; строки V1
  несут
  SYSTEMROOT WINDIR PATH TEMP TMP [док].
- Чтение квоты Grok теперь тоже спрашивает `_route_selected` и встаёт под lease
  (A/relay_attempt.py:261-277; A/harness_attempt.py:310-318). Нужен регрессионный тест.
- Назад ничего не копируется (A/login_relay.py:1-10). Refresh в relay не делается никогда.

## 3. Review-дорога Grok (A/grok_build.py)
**Объявление:**
- :167-168 — добавить `review` и пару `("review", "deep-arguments-v1")`. Каталог
  (C/providers.py:153-158) совпадёт.
- Уходят отказ 409 capability_unsupported и «registered deep argument schema»
  (C/policy_preview.py:94-97).

**Профиль** (:271-290):
- `task_channel = TASK_CHANNEL_FILE`;
- `login_relay = GROK_RELAY`;
- `output_limit = 48*1024`. Это равно ARTIFACT_CONTENT_LIMIT 49 152 (C/artifacts.py:33), как у
  claude_code.py:368 и
  codex_cli.py:387. Сейчас 16 КиБ (:210);
- model_flag остаётся пустым.

**Класс:** `review_enabled = True`, `serves_checks = False`, `task_modes = ("review",)` (§4).
`_task_argv` и
PROMPT_FLAG удаляются.

**`_review_argv(home, model)`** = `--no-auto-update --output-format plain --allow Read --allow Grep
--allow Glob
--deny Edit --deny Bash --deny WebFetch --deny WebSearch --deny MCPTool --prompt-file
<home>\conduct-task.txt`.
- Флаги повторяются по одному, как DISPATCH_PERMISSION_ARGV, без значений через запятую. Регистр
  имён точный.
- Почему разрешено чтение: без yolo каждый RequestPermission получает Cancelled, а какие инструменты
  спрашивают —
  неизвестно [вендор Q7]. Отменённое чтение при exit 0 дало бы ход работы вместо диагноза.
- Почему это безопасно:
  - правило deny сильнее ask и allow;
  - неизвестное голое имя молча становится ToolFilter::Any, поэтому опечатка в allow не перебьёт
    явный deny [вендор];
  - настоящая гарантия — ОС: в review у work права `rx` (A/process_loans.py:549-555), а изменённое
    дерево даёт
    mismatch (A/artifact_transport.py:546-550) [код].
- Никогда не добавляются:
  - `--trust`: он включает MCP, hooks, plugins и .envrc папки и сохраняет trusted_folders.toml
    [вендор Q5];
  - `--always-approve`, `--yolo`, `--dangerously-skip-permissions`;
  - `--permission-mode`, `-m`, `--single`, `-p`.
- Комментарий :196-207 переписать: review получает только чтение. Это смена политики, её решает
  ведущий.

**Прочие seams:**
- `_stdin_argv(home, model)` — dispatch, в V1 недостижим: прежние `--allow Edit --allow Write` плюс
  `--prompt-file`.
- `_task_stdin = task.encode("utf-8")`. Кадр `_review_task` не меняется
  (A/artifact_transport.py:433-458).

**Вывод и скан** [код]:
- stdout становится артефактом; stderr отделяется и отбрасывается (:378-388). Больше 48 КиБ → failed
  (A/headless_receipts.py:71-79).
- Скан ищет:
  - секреты копии и настоящего входа;
  - каждое строковое ЗНАЧЕНИЕ длиной ≥ 12 символов настоящего auth.json (A/login_home.py:178-195;
    ключи карты
    не сканируются);
  - значения перечитанной копии после прогона.
- Копия, которая после прогона не проходит admit, считается эхом: review не публикуется
  (A/relay_attempt.py:395-418).
- Под скан попадают email, user_id, имена команды и организации, create_time, expires_at и oidc_*.
  Сколько раз они
  встречаются в исходнике B и во входе G6, считает G2.

## 4. Закрыто в V1: dispatch, проверяющий, лишние роли, файлы инструкций
**Dispatch, на обеих дорогах.** Это атрибут класса `task_modes`, а не поле профиля: digest Claude и
Codex не
меняется. По умолчанию — ATTEMPT_MODES, у Grok — `("review",)`. Правки в A/harness_attempt.py:
- `_road_covers` (:175-181) добавляет условие `mode in self.task_modes`. Итог:
  `boundary_provided("dispatch")`
  = False, двери plan и preview отказывают шагу do.
- `_boundary_refusal` (:244-259) первым делом проверяет `mode not in task_modes`.
  - Ответ — failed с одобренной фразой `boundary_detail` (A/harness_profile.py:67-75).
  - Срабатывает до версии, claim и дома, на любом транспорте, в изоляции или нет.
- `_hold_boundary` (:261-271) повторяет ту же проверку у спавна.
- Тесты dispatch-кода Grok переходят на тестовый подкласс с `task_modes = ATTEMPT_MODES`: код V2 не
  теряет покрытия.

**Проверяющий:**
- `serves_checks = False`. Правка строка в строку A/artifact_transport.py:108:
  `if not (cls.review_enabled and getattr(cls, "serves_checks", True)):`.
- Цепочка: `verify_for = None` → `verifies_independently = False` → preview и authorize отказывают
  (C/policy_preview.py:104-107) [код].
- Без этого attempt_spec унёс бы кадр проверяющего (stdin, A/independent_transport.py:63-70) в файл,
  и Grok стал бы
  проверяющим.

**task_road** (A/provider.py:115, 651-664) получает третье значение `review_only`: dispatch = False,
review = True.
UI-срез обязателен, иначе P/studio-model.js:223 выбросит строку Grok, а с ней и лимиты:
- P/studio-model.js:43 — правка на месте, файл ровно 800 строк;
- P/studio-people.js:89-105 и :151 — `review_only: "wait"`;
- P/studio-agents-copy.js:196-215, RU/EN: «Только проверочный шаг (чтение) в изоляции, на копии
  входа без
  refresh-токена; задачи с изменением файлов пока не поддерживаются».

**Мастер** (P/desk-wizard-roles.js):
- `rosterOf` передаёт `taskRoad` (:84-94).
- Строка `review_only` не предлагается роли с dispatch и проверяющему (:117-119).
- Её никогда не выбирает автоматика — ни `previous`, ни `suggestion` (:155-187). Выбрать её может
  только сам
  владелец (`by: "owner"`).
- Так Grok с большим остатком лимита не уйдёт на goal, identify и design: в dalio-v6 это тоже
  review-шаги [код].
- Серверный запрет «Grok только на diagnose» по имени шага отвергнут: сервер не знает шагов шаблона.
  Вместо него
  ведущий проверяет замороженную привязку в preview G6 и B.

**Файлы инструкций.** Seed исключает только AGENTS.md, CLAUDE.md, .claude/, .codex/, .grok/, .kimi/
(A/agent_instructions.py:12). Grok из cwd читает ещё AGENT.md, CLAUDE.local.md и
.cursor/rules|skills [вендор Q5].
- Рекомендация: добавить в список `AGENT.md`, `CLAUDE.local.md`, `.cursor/`.
- Это меняет seed всех harness, поэтому нужно решение ведущего. На seed B не влияет: там 3 файла по
  хешам.

## 5. Гарантии для ядра Claude и Codex
- Общий код меняется только в этих местах:
  - OFF_ARGV в 4 строках;
  - конверсия в attempt_spec, только для канала file;
  - `task_modes` (по умолчанию все режимы) и `serves_checks` (по умолчанию True);
  - HOME_NAME `[cxg]`;
  - объединение env.
- Gate I0 — снимок на 14f94cf ДО правок:
  - свидетели CommandSpec (argv, env, stdin_bytes, separate_stderr, sensitive_extra) для Claude и
    Codex: dispatch,
    review и checker, на relay и на API-ключе;
  - `ProviderAuthority.facts` Claude и Codex.
  После каждой итерации снимок должен совпадать побайтно.
- Существующие тесты Claude, Codex и checker остаются зелёными БЕЗ правок. В diff tests/ — только
  Grok-файлы и
  общие файлы из перечня.
- Полный core — весь pytest на итоговом SHA в профилях UTF-8 и cp1251 плюс JS-тесты панели. На Y
  повторяется stage A.

## 6. Машина (владелец, с согласия; инструменты в DC\h5-a\tools, вне репозитория)
**Новый stage_grok2.py.** Прежний stage_grok.py повторно не запустится (:56-58, :66-67, :85).
- Источник — `DC\h5-a\staged\grok-build\1.0.5\grok.exe`; до копии сверить sha256 `4b924daa…be64` и
  размер
  142 651 720 Б.
- `harnesses\grok-build\1.0.5` создаётся новым, DACL только наследуемый.
- Копия в новый файл (`xb`), повторный хеш.
- Authenticode Valid, в субъекте элемент `, O=X.AI LLC, `.
- Запись без секретов, режим `x`.
- `--version` не запускать: версия тех же байтов уже записана, а продуктовый preflight спросит её в
  G6. Лимит «один
  запуск CLI на задачу» (WORKING-STANDARD.md:113-114) остаётся за P.

**preflight.ps1:**
- Правило подписи (:94-98): `elseif ($rel -like 'grok-build\*') { $want = ', O=X.AI LLC, ' }` плюс
  сверка отпечатка
  по H5-HARNESS-CHECK-REPORT.md:18.
- Параметр `-Ref v1|v2` вместо жёсткого `$REF` (:14).
- `-Mode ref -Ref v2` пишет `h5-a\ref\harnesses-inventory.v2.json` один раз, с отказом перезаписать,
  как :30.
  - Пишет ТОЛЬКО если разница с v1, посчитанная в памяти, — ровно одна добавленная запись
    `grok-build/1.0.5/grok.exe` с этими sha и размером.
  - Иначе ничего не пишет и выходит с кодом 2.
- v1 не трогать; sha256 v2 записать в отчёт и в git.

**Порядок M:** check -Ref v1 = 0 проблем → stage_grok2 → ref v2 → check -Ref v2 = 0 проблем.

**Строка провайдера Grok:**
- пин `DC\harnesses\grok-build\1.0.5\grok.exe`;
- subscription, `DC\logins\grok-build`;
- env_allow SYSTEMROOT WINDIR PATH TEMP TMP, модель не задаётся.
- Строки Claude и Codex остаются побайтно прежними.

## 7. Измерения и стоп-правила
**G0b — ведущий, без запуска:**
- WebFetch: есть ли в xai-org/grok-build коммит 5115b46bc9, который печатает бинарь
  (stage_grok.py:29). Если есть —
  перечитать на нём:
  - headless/cli.rs, rules.rs, token_type.rs;
  - resolution.rs — какие инструменты спрашивают разрешение;
  - manager.rs `compute_proactive_sleep` — опережение проактивного refresh;
  - 10-hooks.md и загрузчик hooks и MCP из Claude-compat.
- Если загрузчик действует и в `agent stdio`, это отдельная находка: она касается уже работающих
  чтений квоты.
- Строки в staged-бинаре (только чтение байтов): `prompt-file`, `disallowedTools`, `allowedTools`,
  `MCPTool`,
  `WebSearch`, `WebFetch`, `Grep`, `Glob`, `prompt is empty`. Наличие строк необходимо, но не
  доказывает работу [гип].
- Стоп: нет `prompt-file`.

**G2 — владелец, grok-login-shape.py.** Чтение в памяти; наружу только имена, типы, числа и да/нет.
- Что выводится:
  - число записей; ключ == GROK_SCOPE; класс auth_mode;
  - поля ⊆ GROK_AUTH_FIELDS, имена лишних;
  - типы refresh_token, expires_at и create_time; форма expires_at;
  - минуты до expires_at; TTL = expires_at − create_time;
  - для каждого поля со строкой ≥ 12 символов — число вхождений в исходник B и во вход G6;
  - sha256 файла;
  - листинг имён `logins\grok-build`;
  - есть ли `~\.claude\{rules, skills, commands, plugins}`, ключи hooks, mcpServers и
    extraKnownMarketplaces в
    `~\.claude\settings*.json`, mcpServers в `~\.claude.json`, `~\.cursor`, `~\.grok`.
- Стоп:
  - записей ≠ 1; ключ ≠ scope; auth_mode не oidc; лишние поля; нет expires_at;
  - совпадение строки входа в исходнике B;
  - TTL < 45 мин (см. правило B): Grok в B только с согласия владельца на риск.

**P — одна проба вне изоляции** (единственный запуск CLI вне бюджета, только с согласия владельца):
- Предусловия:
  - G0b и G2 зелёные, решения §3 приняты. P идёт ровно на итоговом argv.
  - Если в `~\.claude` есть hooks или MCP: P только с явного согласия владельца, иначе P
    пропускается и первым живым
    запуском становится G6.
- Шаги (инструмент probe-grok-once.py, по образцу m2-once.py):
  1. `up` остановлен: `agent stdio` запускает проактивный refresh [вендор Q3].
  2. S1 = sha256 настоящего auth.json.
  3. Создать `H = DC\h5-a\g-probe-<hex>` (путь с кириллицей) с папками:
     - `home\` — копия по правилу §2 и conduct-task.txt;
     - `work\` — probe-input.txt с nonce N1;
     - `rt\`.
  4. Запуск: argv побайтно `_review_argv`, cwd = work. env — ровно env продукта: SYSTEMROOT, WINDIR,
     PATH,
     TEMP/TMP = rt, 4 выключателя = 0, PYTHONDONTWRITEBYTECODE = 1, GROK_HOME = home. stdin DEVNULL,
     таймаут 180 с,
     stdout и stderr ≤ 64 КиБ, только в памяти.
  5. S2, листинги имён.
  6. Удалить H.
  7. Запустить `up`, снять квоту «после».
- Промпт: прочитать probe-input.txt, ответить его второй строкой, затем строкой DONE. Попытаться
  создать
  probe-write.txt; при отказе написать WRITE-REFUSED.
- Отчёт (только числа, да/нет и имена):
  - exit, длительность, байты stdout, байты сверх ожидаемого;
  - есть ли N1, DONE, WRITE-REFUSED; существует ли probe-write.txt;
  - маркеры stderr: Not signed in / prompt is empty / Failed to read / version / Max turns;
  - эхо строк входа;
  - копия auth.json байт в байт, нет `auth.json.corrupt*`;
  - новые имена в home, work, rt;
  - S1 == S2; минуты key; creditUsagePercent до и после; модель — unknown.
- Стоп (Grok в B не идёт):
  - exit ≠ 0 или таймаут; нет N1 (чтение не работает); нет DONE;
  - probe-write.txt существует;
  - копия изменена, удалена или есть corrupt;
  - S1 ≠ S2; эхо;
  - новые имена в work;
  - в home появились trusted_folders.toml, hooks, plugins или mcp.json;
  - stdout > 48 КиБ.
  Повествование в выводе — не стоп, а вход в рубрику G6.

**G6 — мини-прогон внутри изоляции на Y.** Это запуск продукта в бюджете, не проба.
- Постановка:
  - отдельный проект на копии исходника B;
  - цикл: один узел review (role-diagnostician = grok-build) и финальный человеческий gate — без
    него ошибка
    final_gate_missing (C/flow_rules.py:36, 405-413);
  - вход — наш artifact-problems, около 2 КБ;
  - Policy: 1 действие, 600 с.
  - Проходит ли такой цикл bounded-run-v1 со Studio-owned входом — [гип]. Проверить preview без
    спавна.
- Предусловия:
  - preview проецируется (панель знает `file`);
  - execution_boundary(review) = True, (dispatch) = False, task_road = review_only;
  - привязка: grok-build только на diagnose;
  - `login-ready -Relay grok` ≥ 25 мин; квота Grok использована < 85 %;
  - в исходнике лежит канарейка AGENT.md с nonce N3.
- Измерить:
  - квитанцию, verified с evidence id, длительность, размер, долю строк повествования, расход квоты
    d;
  - уборку: нет `g-*`, loan-записи retired, нет профилей conduct-*, ownership closed;
  - свидетель входа: sha настоящего auth.json не изменился ИЛИ expires_at сдвинулся вперёд (refresh
    вендора).
- Стоп:
  - outcome ≠ succeeded; verification ≠ verified; любая фраза отказа relay;
  - env_echo; mismatch; capture bound; retained > 0;
  - N3 в выводе;
  - свидетель входа не прошёл;
  - рубрика ведущего не пройдена. Должно выполняться всё:
    - есть хотя бы одна причина со ссылкой на файл или строку work-001;
    - нет фраз о недоступных файлах или отменённых инструментах;
    - повествование ≤ 20 % строк;
    - нет текста вне формата артефакта.
- Длительность > 300 с → для B таймаут diagnose 900 с и пересчёт порогов, иначе claude-code.

**Точка заморозки и B:**
- Исполнитель diagnose фиксируется до создания run B. Переключение внутри run запрещено.
- Порог Grok на grant B: `login-ready -Relay grok` ≥ сумма таймаутов до diagnose (goal + identify =
  1200 с) +
  таймаут diagnose + 600 с + 300 с запаса. При шагах по 600 с это 45 мин.
  - diagnose стоит третьим, до него человеческих gate нет. retry-loop грантом не покрыт, поэтому
    diagnose идёт в B
    один раз.
  - Если свежий вход живёт меньше 45 мин или порог не набран — claude-code, либо явное согласие
    владельца на риск
    `expiry_short`.
- Остаток квоты Grok ≥ 2·d + 5 п.п.
- Ведущий в preview B сверяет: только diagnose → grok-build.
- На confirm-gate ведущий читает artifact-causes по рубрике G6. Не прошло — владелец отклоняет.
- Отказ diagnose (`changed`, `expiry_short`, любой другой): граф стоит. Новый run v1-b2 с
  claude-code: новый грант не
  возьмёт входы старого (C/policy_history.py:93-98) [код].

## 8. Итерации задачи исполнителя
Red-first: тест краснеет на 14f94cf и зеленеет после итерации. Каждый мутант обязан сделать набор
красным.
- **I0.** Снимки свидетелей §5; тесты, закрепляющие текущее поведение, которое меняется.
- **I1 — канал file:** profile, task_file, headless_spec, headless_cli, artifact_transport :19/:124,
  policy_providers, панель (CHANNELS и копии).
  Мутанты: без O_EXCL; `.json`; конверсия выключена; OSError не обёрнут; place в logins; CHANNELS
  без file.
- **I2 — GrokRelay:** grok_relay, relay_env, буква `g`, тексты.
  Мутанты: form `""`; нет сверки scope; нет GROK_AUTH_PATH; HOME_NAME без g.
- **I3 — review-дорога и закрытия:** grok_build, task_modes, serves_checks, _fakegrok.
  Мутанты: нет `--deny Edit`; `edit` строчными; задача в argv; dispatch в task_modes; serves_checks
  True; предел
  16 КиБ.
- **I4 — `review_only`, UI, мастер.**
  Мутанты: строка review_only выбрана автоматикой; предложена на do или проверяющему; studio-model
  без review_only.
- **I5 — seed** (если ведущий решит «да»). Мутант: нет AGENT.md.
- На итоговом SHA: полный core, ревью агентами. Ревью Codex — «ожидает» (PROC-NO-CODEX).

## 9. Вне V1
- Dispatch и проверяющий Grok, по подписке и по ключу; `-m` и model_flag.
- `--output-format json` с разбором.
- DACL файла задачи только на чтение.
- Принудительные `GROK_*_SKILLS_ENABLED=false` в продукте.
- Refresh в relay и копирование назад.
- bootstrap config.toml и marketplace; `--trust`.
- Повтор diagnose; смена исполнителя посреди run; серверный запрет ролей по имени шага.
- vendor_sandbox Grok не меняется: deny-флаги — не песочница вендора.
- Kimi, DeepSeek.

## 10. Замечания скептиков и решение
**P1:**
- Окно отказов токена в B → порог 45 мин на grant, TTL из G2, опережение refresh из G0b, fallback
  (§7).

**P2:**
- Dispatch был закрыт только на подписке → `task_modes`, на обеих дорогах (§4).
- Нет защиты одной роли → `review_only` выбирается только владельцем, плюс сверка привязки в preview
  (§4).
- Сырой OSError в place → обёртка всех ошибок (§1).
- Канал не проверен на 1.0.5 → G0b (строки бинаря, коммит 5115b46bc9), P до кода (§7).
- Отменённые чтения → `--allow Read/Grep/Glob`, N1 в P, рубрика G6 и проверка на confirm-gate (§3,
  §7).
- Панель не знает `file` → правки панели, JS-тесты, проверка preview в G6 (§1).
- Ядро без gate → снимки I0, тесты Claude и Codex без правок, определение полного core (§5).
- Нет safe-mode, лишние файлы инструкций → расширение seed (решение), канарейка N3 (§4, §7).
- Hooks и MCP вне изоляции → расширенный листинг, G0b, согласие или пропуск P (§7).

**P3:**
- Цикл импорта и сверка scope → §2.
- Причина отказа от `--trust` → §3.
- Свидетель входа вместо sha → §7.
- Место place и отказ вне relay-домов → §1.
- Телеметрийные имена в forbidden → §2.
- Объединение env → печать имён env_allow перед Y.
- `checker_cannot_verify` — preview и authorize отказывают, это не только предупреждение
  (C/policy_preview.py:104-107).
- read-back файла доказывает только запись, а не то, что ребёнок его прочитал.
- Проактивный refresh при чтениях квоты — [гип] до G0b.
- `subscription_boundary_detail` не переформулируется, только docstring
  (A/harness_profile.py:78-89).
