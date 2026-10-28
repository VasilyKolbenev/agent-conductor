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

## Отчёт исполнителя

По итерациям: изменённые файлы, красные тесты до и зелёные после, команды и числа
passed/failed/skipped в обеих кодировках, отклонения.
