Итог: P1 нет; P2 — три (одна уже снята правкой Dalio), P3 — тринадцать | ветка
`codex/subscription-0164`, `d6e4331..141a26d` и незакоммиченная правка Dalio | только чтение,
тесты и CLI не запускались | следующий шаг: Codex решает по открытым пунктам 1–3.

# Ревью Opus ветки codex/subscription-0164, 28.10.2026

Ревьюер — Opus 5.5 по просьбе владельца («проверь ветку как ревьюер»). Пять независимых
направлений (адаптер Codex 0.164; изоляция и учётные данные; целостность тестов; отчёты против
кода; незакоммиченный diff Dalio), каждую находку затем пытался опровергнуть отдельный
скептик. Ниже — только выжившие находки, с его итоговой серьёзностью. Ревьюеры читали код в
`work\cdx164`; ревьюер адаптера дополнительно читал исходник vendor на закреплённом коммите
`6aaac69` (github.com/openai/codex), без загрузок и запусков.

## Подтверждено: открыто

| # | Серьёзность | Где | Что |
| --- | --- | --- | --- |
| 1 | P2 | `codex_quota.py:37`; `login_home.py:189-193`; `subscription_quota.py:103-107` | Ответ `account/rateLimits/read` 0.164 несёт `accountId` (`v2/account.rs`, `GetAccountRateLimitsResponse.account_id`); sampler считает `tokens.account_id` секретом → каждый живой read — `source_error`. Фикстуры квоты — только форма 0.112 (`tests/test_subscription_quota.py:18-26`), без `rateLimitsByLimitId`/`accountId`. Совпадает с измерением `H5-CODEX-QUOTA-ECHO-CLASSIFY-REPORT.md`. |
| 2 | P2 | `H5-CODEX-OPUS-HANDOFF.md:40`, `H5-DALIO-ANALYSIS-PURPOSE-TASK.md:11` (закоммичены) | SHA-256 `first-goal-api.json` записан 63 знаками: пропущено `e` в `…aeabdb·e3c5…`. Настоящий: `15e2eb19d49a1a137bcd710a01a5fd987535316bae81370aeabdbe3c521f2855` (сверено ведущим). В незакоммиченном FIRST-GOAL исправлено; закоммиченные не переписаны. |
| 3 | P3 | `codex_quota.py:18-23`; `quota.py:401-406` | Декодер не читает `ordinaryUsageAllowed`, `spendControlReached`, `rateLimitReachedType`, `individualLimit`; заблокированный аккаунт будет `observed` с «остатком». Скрыт, пока read отклоняется (п. 1); решать вместе. |
| 4 | P3 | `codex_cli.py:367-368, 557-560` | В реальном доме входа `config.toml` проверяется только на `projects`/`model_provider`; `chatgpt_base_url`/`openai_base_url` (есть в `ConfigToml` `6aaac69`) проходят и уводят bearer quota-read. Env-двойник `OPENAI_BASE_URL` отклоняется (`relay_env.py:24`). Предусловие — конфиг самого оператора. |
| 5 | P3 | `claude_code.py:249-251, 617` | argv Claude: «Produce the complete review artifact supplied on standard input…» — рядом с новой рамкой («not an input to find or review») читается как «ревью поданного документа». Задание говорит, что Claude наследует ту же рамку; живой дефект был на Codex. Решить до живого Goal Claude на v6. |
| 6 | P3 | `artifact_transport.py:663` | Сканер публикации подставляет литерал кода вместо значения оператора `CODEX_REFRESH_TOKEN_URL_OVERRIDE` на дорогах, где принудительной пары больше нет (API-ключ, preflight). |
| 7 | P3 | `codex_cli.py:332-339`; `login_home.py:476-478` | Take-back удаляет новые `-wal`/`-shm` по отдельности рядом с прежней базой оператора; скептик: риск лишь при убийстве во время checkpoint. |
| 8 | P3 | `codex_cli.py:437-438, 291` | Устаревшие комментарии: «19 bytes» (замерено 18), «five published config keys» над шестью парами. |
| 9 | P3 | `tests/_fakecodex.py:1-6, 231`; `tests/test_command_codex_transport.py:1, 28-31` | Докстринги фейков всё ещё обещают «REAL executable» и пустое окружение; на Windows после `522bbf0` это Python-двойник. |
| 10 | P3 | `H5-CODEX-A-I1-REPORT.md:14` | Не названы решения `f25172a`, `6c3a757`, `7561cfd`, на которых стоят описанные в `:82-87` изменения SystemRoot/P8. |
| 11 | P3 (второй читатель — P2) | `src/conductor/panel/desk-flow.js:73-76` | Метка «Цикл Далио» привязана к `dalio-v5` (шаги без целей); v6 показан под общим «Стандартный цикл», как и v4. Рядом — затравка `graph-default.js:70-107` без целей. UI — к UX-FIRST-RUN. |

## Подтверждено и уже исправлено (незакоммиченная правка Dalio)

| # | Серьёзность | Что | Исправление ведущего |
| --- | --- | --- | --- |
| 12 | P2 | Рамка всегда говорила «Carry out the stated purpose», и шаги без цели (ревью-узлы v1–v5, шаги конструктора с `purpose: null`, `reviewer`) не просили ревью | одна фраза для обоих случаев; контракт «с целью и без отличаются только фразой цели» (`test_command_step_purpose.py:358`) сохранён |
| 13 | P3 | Двойная точка после цели v6, закреплённая тестом | у четырёх целей v6 убрана конечная точка |
| 14 | P3 | Докстринг `purpose_clause` («рамка та же, что до поля») стал ложным | исправлен текст |
| 15 | P3 | `templates/README.md` называл текущим `dalio-v5` | добавлен абзац о v6 |
| 16 | P3 | (чтение итогового diff) «Create the new output document» без запрета файла зовёт агента только-чтения писать файл | «do not create or modify any file for it» в обеих рамках |

Подробности и доказательства — `H5-DALIO-ANALYSIS-PURPOSE-REPORT.md`.

## Опровергнуто скептиком

Тест `test_standard_cycle_correction.py:238` (уже исправлен ведущим до ревью); формулировка
«узкое исправление» в передаче; `-B` в argv продукта (зафиксирован открыто, консервативен);
файл последнего сообщения в фейке Codex (до квитанции не доходит); `tests/conftest.py`
(разрешён `H5-CODEX-TEST-LAUNCH-TASK.md:17-18`).

## Проверено и в порядке (по словам ревьюеров)

Версия 0.164.0 закрыта точным сравнением, 0.112.0 отклоняется; override refresh доходит
только до relay-задач, не до version/status/quota/API; route/credential env отклоняются без
учёта регистра и в конфиге, и в pin; схема relay `auth.json` и вырезание `oauth_provenance`;
декодер JSON-RPC отклоняет нотификации, дубликаты и ошибки.

## Открытые вопросы (для Codex)

1. Пункты 1 и 3 — одно решение по квоте Codex (с вопросом 2 Grok из `H5-HARNESS-CHECK-REPORT.md`).
2. Пункт 4 — дополнить `LOGIN_CONFIG_KEYS` или иначе закрыть base URL в доме входа.
3. Пункт 5 — менять ли постоянный argv Claude до живого Goal Claude на v6.

## Закрытие (Opus, PROC-NO-CODEX, 30.10.2026)

| # | Итог |
| --- | --- |
| 1 | исправлено H5-QUOTA-IDS (`54bdc9e`): id аккаунта допускается только на двух своих местах ответа |
| 2 | хеш исправлен в обоих закоммиченных документах (коммит документов H5-BRANCH-LEFTOVERS) |
| 3 | открыто: поля доступности декодера — после живого чтения исчерпанного аккаунта |
| 4–9 | исправлено H5-BRANCH-LEFTOVERS (`6f77c46`, `tasks/H5-BRANCH-LEFTOVERS-REPORT.md`); п. 4 — два ключа, `profile` не нужен (0.164.0 сам отказывает) |
| 10 | решения `f25172a`, `6c3a757`, `7561cfd` дописаны в `H5-CODEX-A-I1-REPORT.md` |
| 11 | UI — в UX-FIRST-RUN |

## Ревью Codex: ожидает
