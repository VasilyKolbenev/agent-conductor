Итог: локально проверено (затронутые тесты; полный core — на итоговой версии) | код `6f77c46` |
3203 passed, 0 failed, 32 skipped в UTF-8 и cp1251 | отклонения: 6, утверждены ведущим |
следующий шаг: полный core итоговой версии и новая защищённая сборка.

# Отчёт по задаче: H5-BRANCH-LEFTOVERS — пункты 4–9 ревью ветки Codex

- Исполнитель: Sonnet (workflow), ведущий и ревью — Opus 5.5 (PROC-NO-CODEX).
- Исходный commit и ветка: `c3c0e0c` (задание), `recovery/2026-10-20`; код — как `064ddb1`.
- Состояние рабочей копии до изменений: чистое, кроме файла задания.
- Цель: закрыть открытые пункты 4–9 `H5-CODEX-BRANCH-REVIEW-OPUS.md` до живого прогона V1; главное
  — постоянный prompt ревью Claude (Claude исполняет шаги Dalio v6).

## Изменения

- `claude_code.py` — `REVIEW_PROMPT`: «Read the task supplied on standard input and produce the
  complete output document it asks for. Your final reply is that document: write the whole
  document in it, not a summary of it or a pointer to a file or plan.» Согласование с рамкой
  `fd6b1bb` («not an input to find or review»); не воспроизведённый сбой: на `52f3d50` шаг goal
  Claude со старым текстом дал около 22 КБ (B2/B3). Живой Goal v6 измерит рамку и argv вместе.
- `codex_cli.py` — `LOGIN_CONFIG_KEYS` += `chatgpt_base_url`, `openai_base_url` (поля
  `ConfigToml` 0.164.0 по исходнику vendor `6aaac69`: маршрут запросов с bearer входа);
  комментарии `LOGIN_SCRATCH`, телеметрии (шесть пар), формы версии (18 байт) — по факту.
- `artifact_transport.py` — скан публикации берёт forced-пары, которые получает попытка задачи
  (`relayed = self._confine and self._relay_road()`), а не литерал кода на каждой дороге.
- `login_home.py` — `take_back`: спутник SQLite (`-wal`, `-shm`) рядом со стоявшей до спавна
  базой остаётся и не остаток; рядом с неудалённой или неизмеренной — остаётся и засчитывается;
  сирота удаляется, как раньше. `headless_login.py` — только докстринг.
- Тесты: `test_command_claude_review.py` (argv буквально — ожидание изменено по п. 1),
  `test_dalio_analysis_prompt.py`, `test_harness_login_method.py`, `test_relay_road_refusals.py`,
  `test_codex_relay_environment.py`, `test_codex_compatibility.py`; докстринги фейков Codex,
  Claude и общих (`_fakecodex`, `_fakeclaude`, `relay_roads`, `_fakeboundary`,
  `test_adapter_boundary_launch`, `test_command_codex_transport`, `test_command_claude_transport`).

## Проверки

| Команда | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| `run-scoped.ps1 -Tag a1` | копия: старый src + новые тесты, UTF-8 | 19 failed, 205 passed, все на сравнении | красный до правок |
| `-Tag c4`, `-Pattern` задания (108 файлов) | основная копия | 3201 passed, 32 skipped (обе) | первый проход |
| `-Tag d1` | копия: старый `take_back` + мутант `_confine` | 2 failed, 80 passed | красный до для дополнения 1 |
| `-Tag j2`, тот же набор | основная копия | 3203 passed, 32 skipped (обе) | дополнение 1 |
| `-Tag j3`, 3 файла | после правки двух докстрингов ведущим | 289 passed (обе) | слова, без поведения |

Прогон `c4` в cp1251 пережил сон ноутбука (длительность в логе ложная), результат зелёный; итог
задачи — `j2` после пробуждения. 32 пропуска — прежние (opt-in нативные и настоящие CLI).

## Мутанты

В свежей копии итогового дерева `Documents\Codex\work\leftovers-mut` (M0 226 passed, SHA-256
каждого мутированного файла до и после — в журнале workflow `wf_1c530b31-c1a`), копия удалена.

| Мутант | Результат | Что красное |
| --- | --- | --- |
| a3: старый текст `REVIEW_PROMPT` | убит, 5 failed | argv буквально, Dalio claude ×4 |
| a4: «review» назад | убит, 5 failed | то же |
| a5: без хвоста | убит, 2 failed | argv, «final reply / pointer» |
| a6 / a7: без `chatgpt_base_url` / `openai_base_url` | убит, 5 / 5 failed | ряды parametrize, набор грантов, квота `not_supported` |
| a8: литерал всегда | убит, 3 failed | API-дорога [False/True], неограниченная relay-дорога |
| a9: пара никогда | убит, 1 failed | relayed-страж (держится прямым pin) |
| n1: без `_confine` | убит, 1 failed | неограниченная relay-дорога |
| c1: спутник всегда удаляется | убит, 4 failed | `[database_stood]`, неудалённая и неизмеренная база |
| c2: без «base in left» | убит, 1 failed | неудалённая база |
| c3: без проверки существования базы | убит, 2 failed | сирота, неизмеренная база |
| n2 / n3: неизмеренная база = «стояла» / «нет» | убит, 1 / 1 failed | неизмеренная база |

Не применимо: п. 5–6 и правки слов (комментарии, докстринги) — поведения нет.

## Отклонения (что | почему | кто утвердил)

1. `profile` не добавлен в `LOGIN_CONFIG_KEYS` | vendor 0.164.0: legacy `profile` — жёсткая
   ошибка загрузки конфига (fail closed), селектором не служит; файлы профилей — только по
   `--profile`, которого продукт не передаёт | ведущий, дополнение 1.
2. Тесты п. 3 в `test_codex_relay_environment.py` (не назван в задании) | там уже стоят соседние
   тесты пары и boundary | ведущий.
3. Проверка «route.invalid» не в detail добавлена в существующий параметризованный тест | верна и
   для старых строк, ожидания не ослабляет | ведущий.
4. Хвост `REVIEW_PROMPT` — «that document» вместо «that artifact» | иначе ссылка не на «output
   document» | ведущий (текст задания).
5. Юнит-тесты `take_back` в `test_codex_compatibility.py`, а не в
   `test_harness_subscription_login.py` | предел 800 строк | ведущий.
6. Две фразы докстрингов (R1, R2 финального ревью) и одна фраза об ограничении (R3) правлены
   ведущим без исполнителя | только слова; прогон `j3` | ведущий.

## Чужие правки

Нет. `codex_cli.py` — 799 строк (предел 800), `test_relay_road_refusals.py` — 799.

## Ревью

Ревью Codex: ожидает (PROC-NO-CODEX).

- `wf_d8d4158a-91d` — read-only дизайн с четырьмя скептиками.
- `wf_3627f30a-5d6` — сверка vendor (исходник `openai/codex` `6aaac69` на GitHub, только чтение),
  исполнитель, три линзы: P1 нет; E1 (P2, опровергнут скептиком), T1 (P2 → P3); P3 — закрыты
  дополнением 1.
- `wf_1c530b31-c1a` — дополнение 1 и весь дифф: P1–P2 нет; R1–R3 (P3) — слова, правлены ведущим.

## Не проверено

- Живое поведение Claude 2.1.239 с новым prompt и рамкой `fd6b1bb` — первый живой Goal v6.
- Linux и macOS — CI после push.

## Открытые вопросы

1. R3: спутник рядом со стоявшей базой не осматривается — точку повторного разбора на его месте
   могла бы оставить только сама vendor CLI (SQLite пишет файлы); записано в докстринге.
2. Ключи маршрута, найденные сверкой, но недостижимые из `config.toml` дома входа:
   `model_providers` (инертен без `model_provider`), `experimental_realtime_*_base_url`,
   прокси-переключатели; файлы слоя `<name>.config.toml` (только `--profile`) и вне `CODEX_HOME`
   (`%ProgramData%\OpenAI\Codex`, проверяет preflight).
3. `CHILD_ENV` и `RUNTIME_ENV` не воспроизводятся в скане публикации (было и до задачи).
4. Докстринги фейков Grok, Kimi, gh — прежние «REAL executable».
5. Измерено владельцем 30.10: `config.toml` в доме входа Codex нет — новые ключи этот дом не
   отклоняют.

## Передача

- Итоговый commit кода: `6f77c46`; документов — этот.
- `CAPPED`: без изменений (новых файлов нет).
- Обновлённые документы: этот отчёт, задание (дополнение 1), закрытие пунктов в
  `H5-CODEX-BRANCH-REVIEW-OPUS.md`, исправленный хеш в `H5-CODEX-OPUS-HANDOFF.md` и
  `H5-DALIO-ANALYSIS-PURPOSE-TASK.md` (п. 2), решения P8 в `H5-CODEX-A-I1-REPORT.md` (п. 10).
- Следующий конкретный шаг: полный core итоговой версии в `git worktree add --detach`.
