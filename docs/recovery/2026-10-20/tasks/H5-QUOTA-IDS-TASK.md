# H5-QUOTA-IDS — задание исполнителю (Sonnet), 28.10.2026

Ведущий — Opus 5.5 (PROC-NO-CODEX). Дизайн — `H5-QUOTA-IDS-DESIGN.md` v2 (тот же коммит, что это
задание); прочитать целиком до кода. Ветка `recovery/2026-10-20`, основная рабочая копия.
Исполнитель не коммитит; коммитит ведущий после ревью.

## Можно трогать

- новый `src/conductor/command/adapters/service_metadata.py`;
- `src/conductor/command/adapters/grok_build.py`, `codex_quota.py`;
- `src/conductor/command/adapters/codex_cli.py` — только список баз `CodexCliTransport` и не
  больше трёх однострочных делегатов к функциям `codex_quota.py` (файл 773 строки, предел 800);
- новые `tests/test_service_metadata.py`, `tests/test_codex_quota_echo.py`;
- `tests/test_grok_service_echo.py` — только новые тесты, ожидания существующих не менять;
- `tests/test_harness_login_leaks.py` — буквальная фиксация `login_scratch`/`login_expected` Grok
  рядом с Claude и Codex (`:670-705`);
- `tests/test_command_line_cap.py` — новые файлы в `CAPPED`.

Остальное — не трогать. Нужен другой файл — стоп и вопрос ведущему.

## Итерации (по порядку, каждая — зелёные затронутые тесты перед следующей)

1. **I1 — вынос без изменения поведения.** `ServiceMetadata` — первая база `GrokBuildAdapter`;
   переносятся `_attempt`, `_remember_login_values`, `_login_secrets`, `_echoed_login` и атрибуты
   `_service*` с прежними именами; у Grok остаются крючки `_service_for`, `_reply_metadata`,
   `_masked_reply` (его нынешние функции). Строки до 100 знаков. Существующие
   `test_grok_service_echo.py` и `test_grok_quota.py` — без единой правки и зелёные. Новый
   структурный тест: четыре метода `GrokBuildAdapter` разрешаются в `ServiceMetadata`.
2. **I2 — тотальность и поток** (дизайн, «Тотальность», «Поток»). Свидетели в
   `test_service_metadata.py`: крючок `_reply_metadata` бросает → `_login_secrets` даёт полный
   набор, `_attempt` не бросает; `_masked_reply` бросает → `_login_echo` True, чтение — отказ;
   ответ с одиночным суррогатом (`\ud800` в строке JSON) → отказ без исключения из `_attempt`;
   `_login_secrets` из другого потока во время обмена (синхронизация событием внутри фейкового
   runner) содержит допущенное значение, а `_service_values` после чтения пусты.
3. **I3 — Codex.** `codex_quota.py`: `_service_for` (точные argv и stdin `QUOTA_RPC`),
   `_reply_metadata` (оба файла, ключи по месту, допуск `tokens.account_id`), `_masked_reply`
   (декодер; id 3 `accountId`; id 2 `workspaceRouting.chatgptAccountId`, только объект; точное
   равенство; `ensure_ascii=True`). `CodexCliTransport`: `ServiceMetadata` первой базой. Тесты —
   `test_codex_quota_echo.py`, все строки «Codex» таблицы швов дизайна; фейк повторяет скан runner
   (`allowed_environment_values(...) + spec.sensitive_extra`, как `EchoRunner`), `auth.json`
   формы 0.164 (образец — `tests/relay_credentials.py` `codex_leaf` + `auth_mode`,
   `login_owner_id`, `oauth_provenance`), положительный тест проходит сборщик и HTTP-строку
   (образец — `test_grok_service_echo.py:80-93`). Структурный тест — для Codex тоже.
4. **I4 — Grok.** Правило места (в `ServiceMetadata._echoed_login`: значение судится в полях,
   чьи допустимые образцы равны ему или содержат его; маскируются эти образцы); сквозные поля
   `handle_info` в `GROK_REPLY_METADATA` по списку дизайна; `login_scratch` += `models_cache.json`,
   `worktrees.db`. Тесты — строки «Grok» таблицы швов; форма адреса — `grok-asset:///` +
   идентификатор и https-идентификатор.

Каждый новый охранный тест сначала красный на коде до итерации (записать имя и причину красноты).

## Проверка

`powershell -NoProfile -ExecutionPolicy Bypass -File %USERPROFILE%\Documents\Codex\work\quota-ids\run-scoped.ps1 -Tag <новый>`
— затронутые тесты в UTF-8 и cp1251 (без `-Only` — все тесты, импортирующие затронутые модули).
Для быстрой итерации — `-Mode utf8 -Only tests/a.py,tests/b.py`. Метка каждый раз новая (скрипт
отказывается повторять). Контроль до правок — метка `b0`, ведущий.

## Стоп-условия

- нужно изменить ожидание существующего теста;
- нужен файл вне списка;
- `codex_cli.py` выходит за 800 строк;
- поведение vendor расходится с дизайном (форма ответа, поля) — не угадывать.

## Дополнение 1 (ведущий, после стопа I2)

Стоп I2 верен: `threading` в модуле-значении запрещает
`test_command_adapters.py::test_every_value_module_of_the_sdk_package_imports_only_the_allowed_value_modules`.
Решение ведущего — роли вместо потоков (дизайн, «Роли, не потоки»):

- список файлов дополняется: `src/conductor/command/adapters/headless_login.py` — новый метод
  `LoginRoad._spawn_secrets()` (по умолчанию `return self._login_secrets()`, докстринг о том,
  что это набор для скана одного спавна); `src/conductor/command/adapters/headless_spec.py:55` —
  `sensitive_extra` из `adapter._spawn_secrets()`;
- `ServiceMetadata`: без `threading`, `_service_thread`, `_in_exchange`; переопределяет
  `_spawn_secrets` (нынешнее тело `_login_secrets` с тотальностью) и `_echoed_login` (в обмене
  сверяет с `_spawn_secrets()`); `_login_secrets` и `_remember_login_values` не переопределяет;
- структурные тесты I1 (новый файл) правятся под это: в `ServiceMetadata` разрешаются `_attempt`,
  `_spawn_secrets`, `_echoed_login`; свидетель потока — `_login_secrets()` и
  `_sensitive_values(...)` из другого потока во время обмена дают полный набор и не меняют
  `_service_values`;
- `ensure_ascii=False` и у Codex (отклонение исполнителя по Grok принято).

Метки прогонов — не длиннее 2 знаков (`rmbase.py` отказывает длиннее 4 с префиксом `qu`/`qc`).
Несколько файлов в `-Only` — через `powershell -Command "& <script> -Tag X -Only 'a','b'"`.

## Дополнение 2 (ведущий, после ревью I2–I4, workflow `wf_98e5bde8-bc9`)

Находки ревью и решения. Файлы: `service_metadata.py`, `codex_quota.py`, `grok_build.py` (только
комментарий), `tests/test_service_metadata.py`, `tests/test_codex_quota_echo.py`,
`tests/test_grok_service_echo.py` (только новые тесты). Остальное — стоп.

1. **RP-1 / RT-3 (P3) — отказ крючка до конца обмена.** В ветке `except` `_spawn_secrets`:
   `self._service = None` и вернуть весь `values`; остаток спавна судится как любой другой
   (`LoginRoad`, весь набор). Строки `_service_metadata = {}` / `_service_protected = ...` там
   становятся лишними — убрать. Докстринги (`:26-29`, `:99-104`) — по факту. Свидетели: крючок
   бросает при первом вызове и отвечает потом; Codex — `runner.after` меняет `tokens.account_id`,
   ответ несёт новый id на обоих местах → `_login_echo` True, чтение — отказ; нейтральный — в
   `test_service_metadata.py`.
2. **RS-2 (P3) — ключи крючка покрывают скан.** `codex_quota.reply_metadata`: после сбора —
   `if not set(login_home.credential_values(home, names)) <= {*keys, raw}: return {}`
   (крючок читает файлы через `credential_document`, скан — через `_read_json`; точка повторного
   разбора, которую видит только скан, иначе теряет «ключ побеждает» на равенстве). Свидетель:
   `credential_document` подменён так, что `.credentials.json` для крючка None, а файл держит
   значение, равное id → допуска нет, чтение — отказ. Тест `:411-417` (файл отсутствует / не JSON →
   допуск) должен остаться зелёным.
3. **RT-1 (P2) — соседи `result`.** Новые случаи: id как соседний член `result` в ответе 2 и в
   ответе 3 (сырой транскрипт, который декодер принимает) → отказ как эхо. То же для строки
   auth/info Grok (значение, допущенное в своём поле, ещё и соседом `result`) → отказ.
4. **RT-2 (P2) — массивы в файлах входа.** Коллизии: `.credentials.json` `scopes: ['read', id]` и
   ячейка-массив в `auth.json`, равная id, — в поведенческой и в «крючок отдельно»
   параметризациях → допуска нет.
5. **RT-7, спец-наблюдение 3 — слова.** `service_metadata.py:10` — без «unchanged» (вынесен в I1,
   затем тотальность, роли, правило места). `grok_build.py:492-494`: измерено — `principal_id`
   внутри `profileImageUrl` (28.10); что он внутри идентификатора картинки — вывод из исходника
   (`handle_info`), подтвердит живое чтение. `service_metadata.py:26-29`: тотальность — над тремя
   крючками; чтение самого файла входа (`login_home`) — вне этой задачи (RS-1, долг ведущего).
6. **RT-4, RT-6 — мутанты по стандарту.** В копии (`WORKING-STANDARD.md` §3): `src`, `tests`,
   `pyproject.toml` в `%USERPROFILE%\Documents\Codex\work\quota-ids-mut`; прогон —
   `run-scoped.ps1 -Tree <копия> ...`; M0 без изменений; после каждого мутанта SHA-256 файла
   равен исходному; копию удалить. Мутанты: на каждый новый страж п. 1–4; повтор n6 (без
   декодера) и n7 (без «ключ побеждает») на итоговом коде; без порога id (`:99`); без проверки
   `name == CREDENTIAL` (`:95`); `_spawn_secrets` без перечитывания после спавна (тесты
   обновления `:423`, `:449`); `service_for` без argv (`[other-argv]`). Для теста, которому
   мутант не подобрать, — «не применимо, причина». Таблица «Мутант | Результат | Что красное».

Проверка: `run-scoped.ps1` без `-Only` в обеих кодировках, новая метка (свободны `s1`…).
Полный core — ведущий, после коммита.

## Дополнение 3 (ведущий, после ревью дополнения 2, workflow `wf_6c240258-2cd`)

Отклонения исполнителя по дополнению 2 приняты: возврат `_service_values`, страж в
`_echoed_login`, проверка покрытия по каждому файлу. Файлы: `service_metadata.py` и
`codex_quota.py` (только докстринги), `tests/test_service_metadata.py`,
`tests/test_codex_quota_echo.py`. Остальное — стоп.

1. **X1-1 (P2) — свидетель значения, записанного спавном.** Grok в `test_service_metadata.py`
   и Codex в `test_codex_quota_echo.py`: крючок отвечает до спавна и бросает после
   (`scripted(..., lambda call: call > 1)`); `runner.after` обновляет `key` / `access_token`;
   ответ несёт свежее значение в чужом поле и ни одного допущенного → `_login_echo` True, чтение —
   отказ, свежего значения нет в `runner.specs[-1].sensitive_extra`. Мутанты в копии (как в
   дополнении 2, M0, SHA-256, удаление копии): ветка `except` возвращает `self._login_seen`;
   слияние в `_service_values` только после ответа крючка (проба ревью z7). Строки — в таблицу.
2. **Y-1 / X1-2 (P3) — слова о тотальности.** `service_metadata.py:27-33`: под арендой входа
   работают два крючка (`_reply_metadata`, `_masked_reply`); `_service_for` вызывается в
   `_attempt` до аренды (её берёт `harness_attempt._owned_attempt`), поэтому его исключение вход не
   отравляет, и он не обёрнут. Вместо «only compares an argv and a stdin».
3. **Y-2 (P3) — докстринг `reply_metadata`** по файлам: `auth.json`, который не документ или без
   ячейки `tokens.account_id` от 12 знаков, не допускает ничего; файл, который читает скан, но не
   этот читатель, не допускает ничего, если скан нашёл в нём значение, не являющееся ключом этой
   функции (для `auth.json` — кроме ячейки самого id); файл, который не читает никто, ничего не
   меняет.

Проверка: `run-scoped.ps1` без `-Only` в обеих кодировках, новая метка (свободны `u7`-`u9`,
`v1`…`v9`).

## Дополнение 4 (ведущий, после финального ревью, workflow `wf_ee660cf8-27e`)

W1-1 (скептик: P3, до задачи, но таблица Grok выросла с 4 до 13 имён): маска Grok снимает
значения только в строке auth/info (`grok_build.py:561`, `row.get("id") == _RPC_INFO_ID`), и
этого не держит ни один тест. Файлы: `tests/test_grok_service_echo.py` (только новый тест) и
`src/conductor/command/adapters/service_metadata.py` (только докстринг, W1-2: аренду берут
`_owned_attempt` и, для relay, `_relay_attempt`; `_service_for` — до обоих).

1. Свидетель: допущенное значение в именованном поле `result` строки initialize (id 1) и строки
   billing (id 3); параметры — как `carrying()` пробы ревью (`email`, `teamId`, `principalId`,
   по одному сквозному полю) → чтение — отказ, `_login_echo` True, значения нет в
   `runner.specs[-1].sensitive_extra`.
2. Мутант G1 в копии (M0, SHA-256, удаление копии): `result = row.get("result")` без проверки id.
   Строка — в таблицу.

Проверка: `run-scoped.ps1` без `-Only` в обеих кодировках, метки `v3`…`v9`.

## Отчёт исполнителя

По итерациям: изменённые файлы, красные тесты до и зелёные после, команды и числа
passed/failed/skipped в обеих кодировках, отклонения.
