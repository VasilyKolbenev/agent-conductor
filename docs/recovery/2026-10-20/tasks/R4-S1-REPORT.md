# Отчёт по задаче: S-R4-1. D1, вариант A (после push сервер всегда смотрит на ref)

- Исполнитель: Claude Code / Sonnet 5.5. Код продукта изменён: одна функция, `_send`.
- Статус решения: вариант A выбран **Opus (старшим разработчиком) как предварительное решение по В3,
  до подтверждения Codex**. Codex решение ещё не подтвердил; если он выберет вариант B, эта правка
  откатывается, а спецификация и docstring правятся по-другому (см. R4, раздел 6).
- Исходный commit и ветка: `4ddb1fd`, `recovery/2026-10-20`. Основа задания: отчёт R4
  (`R4-PUSH-PR-RECONCILIATION.md`, разделы 6–9, S-R4-1).
- Состояние рабочей копии до изменений: чужие незакоммиченные файлы (R3 motion: `browser_tests/
  desk_motion_bench.py`, `test_desk_motion.py`, `test_desk_shell.py`, `src/conductor/panel/desk-scene.js`,
  `tests/test_desk_motion_wiring.py`; R1.2: `tests/test_command_flow_driver.py`; R1.2-REPORT.md) я не
  трогал. Результаты S-R4-2 (`M tests/test_accept_pull_request.py`, `test_accept_push_guard.py`,
  `test_desk_accept_publish.py`, а также 24 добавленные строки в `tests/test_accept_push_reconcile.py`
  и `R4-S2-REPORT.md`) тоже лежат в рабочей копии без коммита. Файл `reconcile` общий с S-R4-2:
  правил я его только точечными `Edit`, строки S-R4-2 остались как были.
- Цель и наблюдаемое поведение: после каждого `git push` сервер смотрит на ref. `push_auth_failed`,
  полученный от самого push, возвращается только тогда, когда look после push не нашёл ref. Push,
  который дошёл до remote, но сообщил об ошибке входа, теперь даёт 201 по look после push (раньше 409).

## Изменения

| Файл | Что |
| --- | --- |
| `src/conductor/command/accept_push.py` | `_send`: ветка `if kind == "auth": raise PublishRefused("push_auth_failed")` перенесена из позиции до второго `_look` в позицию после него: после «тот же коммит → 201» и «другой коммит или `rejected` → `push_rejected`», перед итоговым `raise`. Диф: +2 −2. `_kind`, lease, `push_words`, `guard_name`, `_look`, docstring `_kind` не тронуты (docstring `_kind` уже говорит «what to call the failure when the look finds the ref absent», изменений не потребовал; docstring модуля («only that look decides») теперь верен буквально) |
| `tests/test_accept_push_reconcile.py` | Мои правки: +41 −3 (шаги 1–3 ниже) |
| `docs/specs/2026-08-13-cockpit-command-api.md` | Шаг 5: в перечне исходов «no ref» (строки 1453–1458) добавлено «`push_auth_failed` when git said it could not sign in»; три строки перенесены по ширине, смысл остального текста не менялся. Диф: +4 −3. Парного перевода нет: `grep` по `docs/` на «AFTER every push» и `push_auth_failed` нашёл только спецификацию и отчёты |

Тесты (шаги 1–3 задания):

| Шаг | Тест | Что проверяет |
| --- | --- | --- |
| 1 | `test_a_push_that_landed_and_said_it_could_not_sign_in_is_recorded_by_the_look_after_it` (новый) | `on_push` выполняет `run()` и отвечает `GitAnswer(128, AUTH_WORDS)`: 201, `payload.push.remote_oid == commit`, `remote_oid(bare) == record["commit"]`, `stands(root)`, `verbs == ["ls-remote","push","ls-remote"]`, `remote.verbs().count("push") == 1` |
| 2 | бывший `test_a_git_that_cannot_sign_in_is_push_auth_failed_and_no_look_follows_the_failed_push`, теперь `test_a_git_that_cannot_sign_in_is_push_auth_failed_after_the_look_finds_no_ref` | push не дошёл, look после него пуст: `push_auth_failed`, `verbs == ["ls-remote","push","ls-remote"]`, `not stands(root)`, `remote_oid(bare) is None` |
| 3 | `test_a_push_that_could_not_sign_in_and_a_look_that_is_silent_write_nothing_and_push_once[look_cannot_sign_in, look_no_answer]` (новый, 2 варианта) | push сообщил об ошибке входа, второй look: не смог войти → `push_auth_failed`; не ответил (таймаут) → `push_unconfirmed`. В обоих `verbs == ["ls-remote","push","ls-remote"]`, `push` ровно один, `push.json` нет, ref на remote нет |

Строки не длиннее 100 символов (reconcile: 100, `accept_push.py`: 98). Размер reconcile: 313 строк.

## Красный на текущем коде (до правки продукта)

Тест шага 1 добавлен первым, до любых правок `accept_push.py`:
`pytest ... --basetemp ...\work\pt-s4r1 tests/test_accept_push_reconcile.py -k landed_and_said_it_could_not_sign_in`
дал **1 failed**: `assert 409 == 201`, payload `accept_refused / push_auth_failed`. Это то же поведение, что
показала проба R4 (раздел 6). После добавления шагов 2 и 3 (до правки кода) красными были все четыре
затронутых теста: шаг 1, шаг 2 (`['ls-remote','push'] == [..., 'ls-remote']`), оба варианта шага 3
(получены 409 `push_auth_failed` и `verbs` без второго look). Остальные 2 теста, подошедшие под `-k`
(look не смог войти, обычное нажатие и проверка), оставались зелёными.

## Проверки

Каждая команда выполнялась после `. ...\December-Command-Environment.ps1 -Quiet`. Среда: Windows 11,
Python 3.12.14, git 2.53.0.windows.3. Сети нет: remote это bare-репозиторий на диске, gh это скриптовая
фальшивка.

| Команда | Результат | Что доказывает |
| --- | --- | --- |
| `python -m pytest -q --tb=short -p no:cacheprovider --basetemp ...\work\pt-s4a tests/test_accept_push.py tests/test_accept_push_guard.py tests/test_accept_push_reconcile.py tests/test_accept_pull_request.py` | **168 passed**, 539.95 s (было 156 в R4 и 165 после S-R4-2; +3 = шаг 1 и два варианта шага 3; шаг 2 это переименование) | Серверные контракты push/PR; ни в одном существующем сценарии число `push` не выросло (все проверки `count("push") == 1` и `verbs` зелёные) |
| `... --basetemp ...\work\pt-s4b tests/test_desk_accept_publish.py tests/test_desk_transport_accept_publish.py tests/test_desk_accept_terminal.py` | **54 passed**, 16.45 s | Карточка и мутационная дверь под Node. Число 54, а не 52 из задания: S-R4-2 добавил G5 (EN и RU) в `test_desk_accept_publish.py`, этот файл лежит в рабочей копии; мои изменения Node-тестов не касаются |
| `... --basetemp ...\work\pt-s4c browser_tests/test_desk_accept_publish.py` (один модуль) | **8 passed**, 162.82 s | Настоящий стол в Chromium, EN и RU; UI и тексты не менялись |
| `... --basetemp ...\work\pt-s4d tests/test_command_line_cap.py -k accept` | **11 passed**, 133 deselected | Строки не длиннее 100 |
| `git diff --stat` (мои файлы) | `accept_push.py` 2+/2−; спецификация 4+/3−; `test_accept_push_reconcile.py` 65+/3− в сумме с 24 строками S-R4-2 | Дифф ограничен перечисленными файлами |
| `git status --short` | см. «Передача» | Чужих файлов не затронуто |

Критерии приёмки:
- за каждым `push` в новых тестах ровно один `ls-remote` (в шаге 3 второй look сам бросает отказ, и он
  по-прежнему один);
- число `push` ни в одном существующем сценарии не растёт;
- UI и тексты не менялись: `push_auth_failed` по-прежнему в `PUSH_UNKNOWN`, доступна только «Проверить
  снова»;
- `_kind`, lease, `push_words`, `guard_name`, `_look`, `desk-accept-host.js`, `PUSH_UNKNOWN`,
  `PUSH_ABSENT` не тронуты, ретраев нет.

## Не проверено

- Полный suite, нативные AppContainer-тесты, Linux и macOS, git ≥ 2.56, настоящие GitHub и gh: не
  запускались (по заданию и как в R4).
- Случай «push сообщил об ошибке входа, а look после него нашёл другой коммит» теперь ведёт к
  `push_rejected` по общему порядку `_send`; отдельного теста на него я не добавлял (задание не
  требовало, и порядок веток прямо следует из шага 4).
- Мутационной проверки красноты не делал: красный вид доказан запуском тестов до правки кода.

## Ревью Opus и правка после него

Ревью Opus 5.5 (workflow `r4-implement-review`) — `approve_with_notes`, blocker нет.

- **Перебраны все ветви `_send`.** Push выполняется не больше одного раза на нажатие. 201
  возможен только при `seen == commit`, где `seen` получен из успешного `ls-remote`.
  Неизвестный исход не превращается ни в 201, ни в повтор. Новая ветка `auth` может лишь
  превратить прежний 409 в 201 по look (G9).
- **Повторные прогоны совпали с отчётом:** 168 / 54 / 8 / 11 passed.
- **Мутант M1** (старый порядок: `auth` до второго look) — 4 теста красные.
- **Мутант M2** (`auth` между «→ 201» и «→ `push_rejected`») выжил. Порядок «другой коммит
  важнее `auth`» тестом не был закреплён. Это тот самый пункт 2 из «Не проверено» выше.

Правка Opus. В `tests/test_accept_push_reconcile.py` добавлен
`test_another_commit_the_look_finds_after_a_push_that_could_not_sign_in_is_rejected`:
push сообщил об ошибке входа, а на remote за это время появился чужой коммит. Ожидается
`push_rejected`, verbs `ls-remote, push, ls-remote`, push один, ref остаётся чужим.

- На текущем коде: 1 passed.
- На копии `src` с мутантом M2 (`PYTHONPATH` на копию, путь импорта проверен):
  `1 failed`. Копия удалена.

## Ревью Codex

Статус: ожидает. Нужно подтвердить или отклонить вариант A по В3 (предварительное решение Opus).

## Передача

- Итоговый commit: нет, коммит не создавался.
- `git status --short` в конце работы: `M browser_tests/desk_motion_bench.py`,
  `M browser_tests/test_desk_motion.py`, `M browser_tests/test_desk_shell.py`,
  `M docs/specs/2026-08-13-cockpit-command-api.md`, `M src/conductor/command/accept_push.py`,
  `M src/conductor/panel/desk-scene.js`, `M tests/test_accept_pull_request.py`,
  `M tests/test_accept_push_guard.py`, `M tests/test_accept_push_reconcile.py`,
  `M tests/test_command_flow_driver.py`, `M tests/test_desk_accept_publish.py`,
  `?? docs/recovery/2026-10-20/tasks/R1.2-REPORT.md`, `?? docs/recovery/2026-10-20/tasks/R4-S2-REPORT.md`,
  `?? tests/test_desk_motion_wiring.py`; плюс этот отчёт (`?? docs/recovery/2026-10-20/tasks/R4-S1-REPORT.md`).
  Мои: `accept_push.py`, спецификация, `test_accept_push_reconcile.py` (совместно с S-R4-2) и этот отчёт.
- Обновлённые документы: спецификация (одна фраза) и этот отчёт. Отчёт R4 не менялся.
- Следующий шаг: Codex подтверждает вариант A по В3 и читает дифф трёх файлов. Если выбран вариант B,
  правка `_send` откатывается, тесты шагов 1–3 заменяются.
- Временные файлы вне репозитория: каталоги `work\pt-s4a` … `pt-s4d` (можно удалить); `pt-s4r1` и
  `pt-s4r2` удалены.
