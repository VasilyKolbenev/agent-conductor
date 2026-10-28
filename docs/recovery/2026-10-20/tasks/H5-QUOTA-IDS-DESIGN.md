Итог: дизайн v2 узкого допуска идентификаторов аккаунта в ответах лимитов Codex и Grok, после
четырёх скептиков (v1 `c50cc20`) | ветка `recovery/2026-10-20` | кода нет | следующий шаг: TASK
исполнителю, итерации I1–I3.

# H5-QUOTA-IDS — идентификатор аккаунта в ответе лимитов (Codex, Grok), DESIGN v2

Ведущий — Opus 5.5 (PROC-NO-CODEX, 28.10). Основание: V1-HARNESS требует видимых лимитов
Claude, Codex и Grok; сейчас каждое чтение Codex и Grok — `source_error`.

## Измеренные и найденные причины

| # | Harness | Что совпало | Где | Доказательство |
| --- | --- | --- | --- | --- |
| 1 | Codex 0.164.0 | `auth.json` `tokens.account_id` | `$.result.accountId` ответа id 3 | `H5-CODEX-QUOTA-ECHO-CLASSIFY-REPORT.md`; vendor `6aaac69` `v2/account.rs` `GetAccountRateLimitsResponse.account_id` (`Option<String>`) |
| 2 | Codex 0.164.0 | то же значение | `$.result.workspaceRouting.chatgptAccountId` ответа id 2 (`account/read`) | скептик VF-1: `GetAccountResponse.workspace_routing` (experimental, но не вырезается для клиента без `experimentalApi`), `workspace_routing.rs` `chatgpt_account_id: entry.id` при `entry.id == get_account_id()`; измерение класс `other` это не исключает |
| 3 | Grok 1.0.5 | `principal_id` (= `user_id`) | внутри `profileImageUrl` ответа id 2 | `H5-HARNESS-CHECK-REPORT.md`, причина 2; vendor `19d42e35` `extensions/auth.rs` `handle_info`: адрес — сам `profile_image_asset_id` (если http/https) или `grok-asset:///{asset_id}`, значит `principal_id` стоит внутри допустимого идентификатора картинки |
| 4 | Grok 1.0.5 | новые `models_cache.json`, `worktrees.db` в доме входа | `_login_residue` | там же, причина 1 |

Механизм отказа: `login_home.credential_values` берёт каждую строку от 12 знаков из объявленных
файлов входа; на квотной дороге это `sensitive_extra` runner (`headless_spec.py:55`) и
`_echoed_login` после запуска (`headless_login.py:301-315`); `_clean` отказывает
(`subscription_quota.py:102-107`). У Grok уже есть узкий допуск: значение допускается только в
своём поле проверенного ответа (`grok_build.py:361-430, 565-624`).

## Что меняется и что нет

Меняется только квотный обмен Codex и Grok (`SubscriptionRpc` по точному argv и stdin).
Не меняются: дороги задач, ревью и checker; `secret_fields` relay; история публикации; сырой
побайтовый поиск ключей (как во всём продукте; канонизация JSON-экранирования — отдельная
общая задача, скептик SEC-1, опровергнуто как дефект этого дизайна); декодер лимитов (поля
доступности — после живого чтения исчерпанного аккаунта); `LOGIN_CONFIG_KEYS`; preflight.

## Интерфейс

Рассмотрены A (копия логики Grok в Codex) и B (вынос в общий миксин). **Выбран B**: общая часть —
обновление входа посреди обмена, происхождение значения по полю, «ключ побеждает» между
выборками (`grok_build.py:382-423`); копия этой логики — худший долг. Свои у провайдера (и при A
тоже): чтение файла входа и маска ответа.

- `adapters/service_metadata.py`, класс `ServiceMetadata` — **первая база** `GrokBuildAdapter` и
  `CodexCliTransport` (иначе C3 ставит его после `LoginRoad` и он мёртв, скептик B-4). Переносятся
  `_attempt`, `_echoed_login` и (после дополнения 1 — как `_spawn_secrets`) `_login_secrets` с
  `_remember_login_values`, и состояние с теми же именами (`_service`, `_service_metadata`, `_service_values`, `_service_protected`; на них
  смотрит `test_grok_service_echo.py:142-143`).
- Крючки провайдера: `_service_for(argv, stdin_bytes) -> SubscriptionRpc | None`;
  `_reply_metadata() -> dict[str, frozenset[bytes]]` (поле входа → допустимые значения; «ключ
  побеждает» по одному документу — здесь); `_masked_reply(output, service, own_fields) -> bytes`.
- **Тотальность** (B-1): крючки работают под общей арендой входа, исключение отравляет вход до
  перезапуска ОС (`ownership_login.py:249-255`). Миксин: исключение `_reply_metadata` →
  полный набор значений до конца обмена; исключение `_masked_reply` → `_echoed_login` = True.
  Пересериализация маски — `ensure_ascii=False`, как у Grok сейчас (дополнение 1): `True`
  экранировал бы не-ASCII допущенное значение вне своего поля, и поиск его байтов промахнулся бы;
  одиночный суррогат роняет `encode`, тотальность превращает это в отказ.
- **Роли, не потоки** (SEC-3, дополнение 1): `publish()` читает `_login_secrets` без очереди
  рабочей папки, а квотное чтение идёт в потоке сборщика. `LoginRoad` получает
  `_spawn_secrets()` (по умолчанию — `_login_secrets()`), и `headless_spec.attempt_spec` берёт
  `sensitive_extra` из него. Миксин переопределяет только `_spawn_secrets` и `_echoed_login`:
  `_login_secrets` (публикация, история `_remember_login_values`) всегда полный и состояние
  `_service*` не трогает. `_spawn_secrets` и `_echoed_login` вызываются только внутри попытки,
  а попытки и квотное чтение идут по очереди рабочей папки. `threading` не нужен (его запрещает
  `test_command_adapters.py` для модулей-значений).
- **Правило места** (меняет и Grok): значение V судится в полях, чьи допустимые образцы **равны V
  или содержат V**, и маскируются эти образцы, а не только V. Так `principal_id` внутри
  идентификатора картинки проходит, а `principal_id` в адресе вне него — нет (сохраняет
  `test_an_image_url_cannot_hide_another_metadata_fields_value`). Таблица Grok не расширяется
  кортежами, `replace(..., 1)` остаётся.

## Codex (`codex_quota.py`; `codex_cli.py` — 773 строки, получает только базу и делегаты)

- Документы: `auth.json` и `.credentials.json`, по одному чтению каждого через
  `login_home.credential_document`.
- Ключи **по месту**: каждая строковая лист-ячейка обоих файлов от 12 знаков, кроме одной ячейки
  `auth.json` `tokens.account_id`.
- Допустимо: `tokens.account_id` — строка от 12 знаков, не равна ключу, не содержит его и не
  содержится в нём (включая значение `.credentials.json`, `login_owner_id`, `last_refresh`).
- Маска: только если `QUOTA_RPC.decode(output)` принял весь обмен; точное равенство в двух местах —
  `result.accountId` ответа id 3 и `result.workspaceRouting.chatgptAccountId` ответа id 2 (только
  если `workspaceRouting` — объект). Остальное — отказ. Пересериализация — `ensure_ascii=False`.
- Не ловит: `rateLimitUpsell` (произвольный JSON сервера, приходит исчерпанному аккаунту) может
  повторить идентификатор — тогда отказ, безопасно; покажет живое чтение.

## Grok

- Правило места выше; таблица полей ответа дополняется сквозными полями `handle_info` с точным
  равенством: `firstName`→`first_name`, `lastName`→`last_name`, `teamName`→`team_name`,
  `teamRole`→`team_role`, `organizationId`→`organization_id`, `organizationName`→
  `organization_name`, `organizationRole`→`organization_role`, `principalType`→`principal_type`,
  `userBlockedReason`→`user_blocked_reason` (VF-3; основание — исходник, не измерение).
- `login_scratch` += `models_cache.json`, `worktrees.db` (только измеренные имена; явное решение
  вместо запрета H5-GROK-M1). `-wal`/`-shm` не объявляются: появились — отказ.

## Итерации

- **I1 — вынос без изменения поведения.** Только `ServiceMetadata` + Grok на нём. Все 11 функций
  (20 случаев) `test_grok_service_echo.py` и `test_grok_quota.py` без правок ожиданий, UTF-8 и
  cp1251; структурный тест: четыре метода у Grok разрешаются в `ServiceMetadata`.
- **I2 — тотальность и поток.** Свидетели: исключение крючка не выходит из `_attempt`, итог —
  отказ; `_login_secrets` из другого потока во время обмена — полный набор.
- **I3 — Codex.** Крючки, база, свидетели ниже.
- **I4 — Grok.** Правило места, сквозные поля, scratch, буквальная фиксация списков профиля.

## Швы тестов

| Шов | Ловит | Не ловит |
| --- | --- | --- |
| Codex: фейк повторяет скан runner (как `EchoRunner`), `auth.json` реальной формы 0.164 (`auth_mode`, `login_owner_id`, `oauth_provenance`), id 3 — `rateLimitsByLimitId` + `accountId`, id 2 — `workspaceRouting`; путь сборщик → HTTP-строка: окна есть, `account_id` в строке нет | ложный отказ; утечку в строку | живой порядок полей |
| Codex: `accountId` в id 1, в `account`, в окне, вложенно, в неизвестном поле, внутри строки → отказ | допуск вне места | — |
| Codex: обмен, который отвергает декодер, с `accountId` → `source_error` и `_login_echo` | маску без проверки декодером | — |
| Codex: токен где угодно; `account_id`, равный значению `.credentials.json`, `login_owner_id`, токена или внутри них → отказ | «ключ побеждает» по обоим файлам | — |
| Codex: обновлённый посреди обмена токен в выводе → отказ | дыру обновления | — |
| Codex: задачи и ревью видят `account_id` как секрет; `_sensitive_values` во время обмена из другого потока содержит его | утечку допуска наружу | — |
| Grok: `profileImageUrl` = `grok-asset:///` + идентификатор с `principal_id` внутри, и форма https → чтение; `principal_id` в адресе вне идентификатора → отказ | правило места | серверную форму идентификатора |
| Grok: сквозные поля с значениями от 12 знаков в своём поле → чтение, в чужом → отказ | расширение таблицы | — |
| Grok: scratch появились → забраны, чтение; были до запуска → не тронуты; `worktrees.db-wal` появился → отказ | остаток | — |
| Структурный: методы у Grok и Codex разрешаются в `ServiceMetadata` | мёртвый миксин | — |

Мутанты: маска не применяется; маска на любом поле; маска без декодера; «ключ побеждает» убран;
ключи только из `auth.json`; правило места «только равенство» (как до v2); миксин второй базой.

## Правила

Новые файлы — в `CAPPED` (`tests/test_command_line_cap.py`), строки до 100 знаков (перенос строки
`grok_build.py:379` при выносе). Затронутые тесты в UTF-8 и cp1251, мутанты, затем полный core
объединённой версии. Живое чтение лимитов Codex и Grok — отдельным шагом на новой защищённой
сборке, с владельцем.

## Дополнение 2 (после ревью I2–I4)

- Отказ `_reply_metadata` — до конца обмена буквально: миксин снимает `_service`, и остаток спавна
  судится как любой другой спавн по всему набору (RP-1).
- Codex: ключи крючка обязаны покрывать то, что читает скан (`credential_values`); не покрывают
  (файл, который видит только скан) — допуска нет (RS-2).
- Тотальность — над двумя крючками, `_reply_metadata` и `_masked_reply`: аренду входа берут
  `_owned_attempt` (`harness_attempt.py:320`) и, для задачи через relay, `_relay_attempt`
  (`relay_attempt.py:328`); `_service_for` вызывается в `ServiceMetadata._attempt` до обоих, и его
  исключение вход не отравляет (дополнение 3, ревью Y-1, W1-2). Квотный обмен не идёт через relay.
  Чтение самого файла входа (`login_home`: одиночный суррогат, глубокая вложенность) бросает и под
  арендой — до этого изменения так же у всех провайдеров; отдельный долг (RS-1).
- После отказа крючка спавн судится по всему, что обмен видел, включая значения, записанные
  самим спавном (перечитанные после него); снимок до спавна (`_login_seen`) для этого мал (X1-1).

## Находки скептиков

Подтверждены и учтены: VF-1 (P2), B-1, B-3, T1, T2, T3 (P3 после проверки), SEC-2, SEC-3, B-4,
B-5, VF-2, VF-3, T4–T8 (P3). Опровергнуты: SEC-1 (сырой поиск ключей — свойство всего продукта),
B-2 (дизайн и так отдаёт крючки Codex). Записи — журнал workflow `wf_be628f87-772`.
