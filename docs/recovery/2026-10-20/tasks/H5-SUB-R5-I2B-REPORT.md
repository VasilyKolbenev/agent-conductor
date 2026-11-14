Итог: локально проверено (UTF-8 и cp1251) | код `2ec3bca` | полный core ведущего 18420 passed,
409 skipped, 0 failed в обеих кодировках, нативные 91 passed в обеих | решения Codex по 22
отклонениям приняты 26.10 с условиями; D13 — ограниченный A2 | следующий шаг: завершить I3,
затем `H5-SUB-R5-I2B-CLOSE-TASK.md`; живой B и готовность выпуска не подтверждены.

Исполнитель (до коммита): целевые 5 файлов 150 passed, 1 skipped; затронутый набор 254 файла 7094
passed, 214 skipped, 0 failed в обеих кодировках; красная фаза на старом `src` 154 failed, 214
passed; 69 мутантов красные. Один красный в промежуточном прогоне (`test_login_ownership`, окно 8 с;
измерено: старт fake-ребёнка 1–17 с на старом и новом дереве; причина разброса не установлена;
код I2b в окне — порядка 1 мс по трассировке) не закрыт повтором — вопрос 11. Ревью Opus: 18
находок, 16 исправлены, 2 частично; проверка исправлений ведущим — раздел «Проверка ведущего».

# Отчёт по задаче: H5-SUB-R5 / I2b. Подключение relay к транспорту

- Исполнитель: Claude Code / Sonnet 5.5 (`claude-sonnet-5-5`), две итерации: первая — реализация,
  вторая — исправления по трём линзам ревью Opus (раздел «Ревью Opus»). Не коммитил, `CAPPED` не
  трогал, ничего не пушил, живых CLI не запускал.
- Исходный commit и ветка: `recovery/2026-10-20`, работа начата над `6d5ad7c` (I2a: код `13be63a`).
  Ко второй итерации HEAD — `2deece6`: четыре docs-коммита ведущего и Codex (`69c2a7d`, `2a5bcdd`,
  `80f3370`, `2deece6`), `git diff --name-only 6d5ad7c HEAD` называет только `docs/`, `git diff
  --stat 6d5ad7c HEAD -- src tests pyproject.toml` пуст. Прочитанные TASK/DESIGN — те, что названы в
  задании (v2, §8, §8.1, решения `01d4d85`, `f4b31c8`, `8bc2d64`, `61a629f`); решения H5-A-Р1–Р6 из
  `2a5bcdd` прочитаны после работы, влияние — в «Открытых вопросах».
- Цель и наблюдаемое ожидаемое поведение. Подписочная задача Claude Code и Codex (dispatch, review,
  независимый checker) на confined-транспорте идёт в relay-home вне проекта: `HOME` ребёнка —
  relay-home с копией входа без refresh token; version и login status перед задачей остаются на
  настоящем login-home; порядок lease → copy-in → вход в boundary → claim → run; всё, что можно
  отказать до claim, отказывается значением до claim, без маркера и ребёнка, с закрытой lease;
  relay-home убирается на любой дороге; значения копий и значения, которые ребёнок мог переписать в
  relay-home, входят в сканы утечек; Grok, Kimi и профили без relay отказываются как раньше (H5-V1).

## Чужие правки

- Старт первой итерации: один неотслеживаемый чужой файл
  `docs/recovery/2026-10-20/tasks/H5-CODEX-COMPAT-A-DESIGN.md` (не трогал; ведущий закоммитил его в
  `69c2a7d` во время работы).
- Старт второй итерации: `git status --short` — 23 `M` и 8 `??` (31 запись), все они — моя
  неотслеживаемая работа первой итерации (список в «Передаче»). Чужих правок в `src/`, `tests/` и
  `pyproject.toml` нет ни в рабочей копии, ни в коммитах над `6d5ad7c` (там только `docs/`).
- Конец второй итерации: 32 записи (24 `M`, 8 `??`), новых файлов нет; в сравнении с первой
  итерацией добавилась одна `M` — `adapters/subscription_quota.py`. Документы параллельной задачи
  H5-CODEX-COMPAT A (`docs/recovery/2026-10-20/tasks/H5-CODEX-COMPAT-*`) я не менял.

## Изменения

Пути `adapters/` — `src/conductor/command/adapters/`.

| Файл | Что |
| --- | --- |
| `adapters/relay_attempt.py` (новый, 410 строк) | миксин `RelayAttempt`: старт дороги (`_relay_start`, `_homes_refusal`, `_claim_of`), окружение (`_route_selected`), готовность как последний шаг preflight (`_relay_preflight`), попытка под lease (`_relay_attempt`, `_relay_in`, `_relay_spec`), чтение relay-home до удаления (`_read_relay_home`, `_home_leaf_kind`); значения `NotStarted`, `LaunchLost`, `CarriedError`, `Claim` (вызываемое + `stands()`), исключение `RelayNotStarted` (поднимает только `_attempt`, вне lease); `CLAIM_REFUSALS`; закрытая таблица фраз `OWN_PHRASES` (10, с `claim_standing`), `refusal_sentence(.., home_env)` |
| `adapters/harness_attempt.py` (+177, 536 строк) | предикат: `_login_road_covered()` = не подписка ИЛИ есть relay; `_relay_road`, `_relayed(mode)`, `_asks_the_real_login(mode)`; `_launch_covers` на relay-дороге требует `entry_lends_relay_homes`; `_attempt(..., claim=)` (не-relay берёт claim первым, relay — после входа; обе ветки идут через `_relay_outcome`); `_owned_attempt` и `_spawn`: вопрос к настоящему login, который нельзя начать, — значение (`CarriedError`, `LaunchLost`); `_attempt_folders` (единственный вызов `AttemptFolders`), `_run_relayed` (вход, `_ready_to_run`, run, выход; отказ до claim — значение), `_ready_to_run` (spec, затем claim) |
| `adapters/headless_cli.py` | `RelayAttempt` в базах; `execute` ловит `RelayNotStarted` как `LoginLeaseRefused`; `_dispatch`: `_homes_refusal`, `claim=self._claim_of(request)`; последний шаг `_preflight` — `_relay_preflight` |
| `adapters/artifact_transport.py` (787 строк) | то же для review: `_homes_refusal`, `claim=self._claim_of(request)`, `RelayNotStarted` в `_review_owned` |
| `adapters/independent_transport.py` | checker: `_relay_start` рядом с `sweep_homes` (`homes_refused` / `login_not_ready`), `_preflight` с различением `login_not_ready`, `claim=self._claim_of(request, verification=True)`, `RelayNotStarted` → `login_not_ready` (`marker_standing` для `claim` и `claim_standing`) |
| `adapters/headless_login.py`, `headless_spec.py` | `_home_value(home, mode=None)`: relay-home для relay-попытки, иначе прежнее; `attempt_spec(mode=, extra=)`: `sensitive_extra` = секреты настоящего листа и копии; `_forget_login_sample` сбрасывает и `_relay_ready`; `_login_home_refusal` первым делом судит окружение (`_route_selected`) |
| `adapters/subscription_quota.py` (1 строка) | чтение квот на relay-дороге отказывает `not_supported`, если выбранное окружение несёт запрещённое имя (`_route_selected`) |
| `adapters/login_relay.py` (+50) | `clock_instant`, `ready_for` (срок = таймаут ЭТОЙ попытки + `MARGIN_SECONDS` 600), `every_text` (все тексты документа длиной ≥ 12, для листа, вышедшего из схемы); I2a без изменения |
| `adapters/relay_home.py` (+86) | `project_key`, `mint_home` (`mkdir` без `exist_ok`, корень relay не создаётся), `lease_names` (lease называет этот login по identity; закрывает отклонение 1.6 I2a), `leaf_kind` (вид имени в relay-home) |
| `adapters/process.py` (800 строк) | `ProcessRunner.relay_acl_refusal(auth_home, relay_home=None)` (+6 строк); три блока текста переписаны, чтобы уложиться в 800 строк, смысл прежний: комментарий `RELAY_HOME_LOANS` (две строки → одна, ссылка сокращена до `entry_lends_relay_homes`, без `boundary_entry.`), docstring `container_profile` (перенос слов, один абзац стал короче на строку) и комментарий в `ProcessAdapter.execute` (четыре строки → три: «the same defect» → «the defect», «on the harness road» → «on this road», дата 23.09.2026 сохранена) |
| `adapters/codex_cli.py` | одна строка: `_read_attempt_home` читает вид `-o`-файла через `_home_leaf_kind` |
| `adapters/independent_check.py`, `verify_road.py`, `verify_holds.py` | закрытый ключ `login_not_ready` и предложение `CHECKER_LOGIN_NOT_READY` |
| `failure_reasons.py` (+62) | 30 строк слов (по одной на код `REFUSALS` и на код дороги, включая `claim_standing`) — после «exceeded its timeout» и «exit non-zero» |
| `tests/relay_roads.py`, `tests/_fakehome.py` (новые) | стенд: активированный tmp-проект с живым `ProjectOwner`, настоящая `LoginLease` на `<tmp>\DecemberCommand\logins\x`, fake claude/codex с полной синтетической схемой; отчёт ребёнка о своём home |
| `tests/_fakeboundary.py`, `_fakeclaude.py`, `_fakecodex.py` | дублёр boundary: `ensure_relay_root`/`relay_acl_refusal`, hooks, `outcome`; fake: `HOME_REPORT`, `ROTATE_ACCESS` (без изменения прежнего поведения) |
| `tests/test_relay_road_success.py` (21), `..._refusals.py` (65), `..._lifecycle.py` (15), `..._words.py` (35) | поведенческие тесты пп. 7–8 задания (136; 117 после первой итерации) |
| `tests/test_relay_home_native.py` (30 → 32) | два нативных теста вопроса runner (`ProcessRunner.relay_acl_refusal` с домом и без) |
| `tests/test_subscription_road_boundary.py` (15 → 66), `test_adapter_boundary_launch.py`, `test_execution_boundary_refusal.py`, `test_production_door_boundary.py` | H5-V1 переписан честно (см. ниже) |
| `tests/test_accept_capture.py` | дублёр `Checker` получил три метода-заглушки новых швов дороги (`_relay_start`, `_relay_refused`, `_claim_of`) |

Как это устроено, и чем отличается от текста задания (подробности — «Отклонения»):

1. **Одна дорога, три двери.** `_login_road_covered()` — единственный ответ; `boundary_provided`,
   `_boundary_refusal`, `_hold_boundary` и checker приходят к нему через `_road_covers`. Для Grok и
   Kimi (нет `login_relay`) ответ прежний и отказ прежней фразой H5-V1. `_relayed(mode)` требует
   confine, режим из `ATTEMPT_MODES` и relay-дорогу; неconfined транспорт фейков не меняется (`HOME`
   — настоящий login-home, docstring).
2. **Исключения под lease.** Всё ожидаемое под lease — значения (`NotStarted`, `LaunchLost`,
   `CarriedError`); `_attempt` стоит вне lease и превращает `NotStarted` в `RelayNotStarted`
   (квитанция «не запускалось», до claim), а `LaunchLost` — в прежнюю фиксированную ошибку `could
   not start the pinned build` (runtime пишет `unknown`); `CarriedError` поднимает прежнее
   исключение (`WorkspaceNotContained` → прежняя квитанция «uncontained»). Так же ведут себя вопросы
   к настоящему login (version, login status, чтение квот) на relay-дороге: отказ runner'а до
   ребёнка или невозможность создать домик проекта больше не отравляют lease. Неожиданное (баг,
   прерывание, `retire(False)`, в том числе собственный сигнал runner'а об исчезнувшем pinned-файле)
   по-прежнему поднимается и оставляет lease uncertain.
3. **Порядок.** Старт дороги (`ensure_relay_root` вне lease, sweep) → preflight (окружение, затем
   version, login status, затем `relay_acl_refusal`, окружение ещё раз, `ready`) → под lease: lease
   называет login, mint, `relay_acl_refusal(home)`, `copy_in(digest из ready)` → вход → spec → claim
   → run → чтение relay-листа → `discard`. Claim, не взятый до конца, но оставивший marker, — отказ
   `claim_standing` (повтор действия будет `unknown`). `ready` не кешируется: `Ready` потребляется
   попыткой и сбрасывается `_forget_login_sample`.
4. **Окружение** судится по фактически выбранному (`capture_environment(env_allow, forced_env)`), а
   не по именам строки конфигурации; первым делом (до version и login status, которые идут на
   настоящий login-home с тем же окружением) и в чтении квот (`not_supported`); на readiness — ещё
   раз.
5. **Refresh вне boundary не делается**: малый или неизвестный срок — отказ «войдите заново» с
   командой входа профиля и именем переменной login-папки (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`), без
   пути.

## Проверки

Каждая команда — после `. ...\December-Command-Environment.ps1 -Quiet`, Windows 11, Python 3.12.14,
`--basetemp C:\Users\Пользователь\<4 символа>` (26 символов), свой на прогон, `Test-Path` = False
до, удалён после; для cp1251 — `Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING` (в логе `utf8_mode
0`, `preferred cp1251`; для UTF-8 — `utf8_mode 1`, `preferred utf-8`). Скрипты и логи второй
итерации: `Documents\Codex\work\i2b2\` (`run_chunk.ps1`, `run_red.ps1`, `run_native.ps1`,
`red-r3.log`, `run-v1…v7.log` и `run-vt.log` (UTF-8), `run-w1…w7.log` и `run-wt.log` (cp1251),
`native-n1.log` (UTF-8), `native-n2.log` (cp1251), `mutate4.py`, `mutants4*.json`,
`final-tree.log`); первой — `Documents\Codex\work\i2b\`. Итоговые прогоны сняты на одном дереве: хеш
`src` и `tests` (`treehash.py`, 31 файл) 90c2489bc8c56e2e до прогонов UTF-8 и после всех, правок в
промежутке нет. Параллельно шли до восьми процессов pytest (8 логических ядер).

| Что | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| Красная фаза, заново на итоговых тестах: 8 файлов (4 новых, 4 изменённых H5-V1) на `src` из `git archive HEAD` (`2deece6`; `src` как в `6d5ad7c`); `conductor.__file__` из копии, тесты побайтно равны рабочей копии | UTF-8 | **154 failed, 214 passed**, 223 с (`red-r3.log`). Падения: 96 сравнений (80 `AssertionError` и 16 `assert`: прежняя фраза H5-V1 вместо успеха или закрытого relay-предложения, двери отвечают `False` там, где должны `True`, `failed` вместо `succeeded`/`cancelled`, прочее); 36 — новый модуль `relay_attempt` не импортируется (35 `ModuleNotFoundError`, 1 `ImportError`: тесты слов и свидетели пропуска preflight; это не сравнение); 14 — двери и runtime отказывают дорогу, которую обязаны допустить (10 `AuthorizationError`, 2 `ApiRefusal`, 2 `CheckFrameError`); 5 `Failed` (`DID NOT RAISE` и подобные); по одному `TypeError` (`_home_value(home, mode)`), `AttributeError`, `ValueError` (фраза отсутствует в `REASONS`). По файлам красных: success 21 из 21, refusals 65 из 65, lifecycle 15 из 15, words 33 из 35, boundary 12 из 66, adapter_boundary_launch 2 из 94, execution_boundary_refusal 2 из 53, production_door 4 из 19 | новые поведения красные на старом коде. 214 прошедших: 212 в четырёх файлах H5-V1 — прежнее поведение (API-key, закрытые Grok/Kimi, профили без relay); 2 в `test_relay_road_words.py` — стражи, зелёные на старом коде по причине (см. ниже) |
| Целевые, итоговые тесты: четыре новых файла и `test_accept_capture.py` (5 файлов; success 21, refusals 65, lifecycle 15, words 35, accept_capture 15 тестов) | UTF-8 / cp1251 | **150 passed, 1 skipped / 150 passed, 1 skipped** (`run-vt.log` 316 с, `run-wt.log` 366 с; skip — `test_accept_capture.py:287`, Windows не выводит Git mode из chmod, был в `HEAD`) | новые поведенческие тесты (136 против 117 в первой итерации) и дублёр |
| Затронутый набор: 254 файла (250 первой итерации — по имени и по использованию транспортов, fake-ов, `failure_reasons`, `verify_*`, `login_relay`, `relay_home`, `ProcessRunner` — и 4, которые ревью нашло пропущенными: `test_alpha4_template_server_smoke`, `test_command_input_binding_version`, `test_command_run_routes`, `test_desk_wizard_roster`), без нативных и без новых, семь процессов | UTF-8 | v1 1239 passed, 11 skipped; v2 1152 / 30; v3 1190 / 10; v4 1440 / 30; v5 938 / 128; v6 1062 / 5; v7 (4 файла) 73 / 0; итого **7094 passed, 214 skipped, 0 failed** (вместе с целевыми 7244 passed, 215 skipped) | прежнее цело |
| то же | cp1251 | w1 1239 / 11; w2 1152 / 30; w3 1190 / 10; w4 1440 / 30; w5 938 / 128; w6 1062 / 5; w7 73 / 0; итого **7094 passed, 214 skipped, 0 failed** (вместе с целевыми 7244 / 215) | кодировка не влияет |
| Нативные, **один файл на процесс**, десять файлов: `test_relay_home_native`, `test_login_relay_native`, `test_process_login_closed`, `test_process_native_boundary`, `test_process_acl_native`, `test_process_acl_mutex_native`, `test_process_loans_native`, `test_process_login_native`, `test_process_login_native_overlap`, `test_process_login_config_native` | UTF-8 / cp1251 | **32 / 2 / 8 / 6 / 1 / 5 / 8 / 15 / 10 / 4 passed, 0 failed** в обеих кодировках (`native-n1.log`, `native-n2.log`) | свидетели runner и gate login-home закрыты (`LOGIN_LOAN_OPEN is False`); `ProcessRunner.relay_acl_refusal` проверен настоящим helper; `process.py` цел |
| Лимиты: `limits.py` (новые файлы целиком, изменённые — добавленные строки), строки ≤ 100, файлы ≤ 800, без хвостовых пробелов, CR и BOM, один `\n` | — | LIMITS OK (32 файла, включая этот отчёт; `process.py` ровно 800, `artifact_transport.py` 787) | форма |
| Неиспользуемые импорты (AST, `unused.py`; `ruff` не установлен) | — | 0 | — |

**Стражи, зелёные на старом коде.** Первая версия красной фазы (на ранних версиях тестов) пропускала
на старом `src` пять новых тестов: контроль review
`test_a_review_that_prints_the_access_token_of_its_copy_is_not_published`,
`test_the_login_of_every_refused_attempt_is_byte_for_byte_what_it_was` и три теста слов, один из
которых сверял только литералы набора. Теперь красные на старом коде первые два (контроль проверяет,
что ребёнок запускался, `len(site.tasks()) == 1`, и что вывод узнан как несущий токен, `_login_echo
is True`, мутант CTRL; второй проверяет, что дорога дошла до boundary, `len(site.runner.entries) ==
1`, мутант G2) и `test_no_two_refusals_share_their_words_…` (сверяет и таблицу продукта, мутанты W5,
W3). Зелёными остались два теста, и это стражи, а не пропуск проверки:
`test_the_phrases_this_suite_spells_are_the_ones_the_product_writes_for_every_login_refusal` держит
таблицу `login_relay.REFUSALS` (код I2a, в старом `src` она уже есть) против литералов набора,
убивающий мутант G3 (другая фраза в `REFUSALS`);
`test_a_sentence_of_what_a_child_did_is_never_taken_for_a_refusal` держит порядок строк `REASONS`
для двух строк «что сделал ребёнок» (они в старом `src` есть), убивающий мутант W6 (чужая строка
перед ними).

**Причины skipped** (по `-rs` итоговых логов, 215 в каждой кодировке: 214 затронутого набора и 1 в
целевых). Платформенных 133: macOS Seatbelt и POSIX-пути профиля Seatbelt 106 (68 + 38,
`test_os_boundary_darwin*`, `test_os_boundary_seatbelt_*`); POSIX 27 (`/bin/sh` 20, POSIX-раннер 2,
POSIX-сессия 1, бит режима и execute bit 2, `chmod` на Windows 2). Условий среды 82: нет права на
символьные ссылки 26 (`WinError 1314` у учётной записи, «this account cannot make a link»);
`CONDUCT_OLD_GIT` не задан 35 (ворота G-old, `git_first_readers`); живые CLI и платные проверки не
включены 20 (`CONDUCT_*_EXECUTABLE`, `CONDUCT_*_REAL_PROMPT`, `CONDUCT_*_REAL_CHECKER`,
`CONDUCT_DSH_*`); вход идёт через журнал 1 (`test_execution_boundary.py`, ссылка на
`test_container_view_mode`). Первая версия отчёта называла все skip платформенными, глядя на один
лог; это было неверно для 82 из 215.

**Красный, не закрытый повтором:**
`test_login_ownership.py::test_two_real_projects_share_one_resource_through_post_spawn_cleanup`
(файл `tests/`). В промежуточном прогоне cp1251 (`run-c4.log`, пока на машине шли ещё три pytest и
мутанты) — 1 failed: `assert entered.wait(8)`, `errors == []`; в итоговых
прогонах (`run-v4.log`, `run-w4.log`) тест зелёный в обеих кодировках. Тест и его окно я не менял; в
окне ожидания код один и тот же (lease, mint, один spawn fake-ребёнка, `_take_back_login` до
`entered.set()`), мои правки добавили только `_relay_outcome` после возврата. **Измерено:**
окно 8 с ограничивает время `ProcessRunner.run` fake-ребёнка, а оно на этой машине менялось
от 1 до 17 с на обоих деревьях; причина разброса не установлена. Проба вне репозитория
(`probe_phases.py`, воспроизводит
работу worker'а с отметками времени, cp1251, шесть прогонов на каждую сторону): новый код — `run`
1.2, 1.2, 1.2, 3.7, 9.7, 11.7 с; старый (`src` из `HEAD`) — 1.5, 1.7, 2.4, 9.2, 9.5, 16.5 с; три из
шести прогонов старого кода превышают 8 с. Фон машины: Telegram, Claude, ChatGPT, Chrome (~28% CPU
без моих процессов). Повторы самого теста, простой машины, cp1251: новое дерево в репозитории — 3
красных из 15 (12.6, 11.4, 11.1 с); копия нового дерева в `work\i2b2\newcopy` рядом со старым — 1 из
15 (12.2 с); старый код (`work\i2b2\red`) — 0 из 15 (но 14.98 и 22.07 с прошли: их окно ожидания не
пересеклось). Различие по частоте красных (4 из 30 против 0 из 15) не значимо (точный критерий
Фишера, p ≈ 0.18) и не объяснено кодом. Зелёный повтор красный не закрывает: предусловие «ребёнок
стартует быстрее 8 с» тест сам не создаёт и не проверяет (стандарт §2.4); решение за ведущим или
Codex (открытый вопрос 11).

Первая итерация (для истории, её числа заменены итоговыми выше): красная фаза на ранних версиях
тестов 125 failed / 215 passed; затронутый набор 250 файлов UTF-8 7016 passed, 214 skipped, 2 failed
(дублёр `Checker` в `test_accept_capture.py` не знал новых швов; причина установлена, правка
дублёра, перепрогон зелёный), cp1251 7018 passed, 0 failed.

В затронутые наборы входят тесты H5-V1 с границей: старые 184 (три файла) заменены 213
(`test_subscription_road_boundary` 66, `test_adapter_boundary_launch` 94,
`test_execution_boundary_refusal` 53), плюс `test_production_door_boundary` 19.

### Что именно держит тестовая часть

- **H5-V1 переписан, не ослаблен.** Отрицательные свидетели дверей, отказа до claim, пропуска
  вопроса (`_attempt` напрямую), review через runtime и checker через runtime — на Claude и Codex с
  `replace(profile, login_relay=None)` и на Grok и Kimi (дверям и dispatch; у них нет review и
  checker). Положительные — Claude и Codex допускаются при закрытых и открытых `LOGIN_LOAN_OPEN`.
  Production door с подписочными пинами на win32: claude/codex `True`, grok/kimi `False` (и над
  настоящим `ProcessRunner`: ответ следует его entry и `RELAY_HOME_LOANS`). Свидетель «платформа без
  boundary называет не вход, а платформу» (его имя — в таблице мутантов, G1b) идёт на Claude и без
  relay, и с relay (Linux и macOS). Стражи сохранены:
  `AttemptFolders` без `login` и один вызов, `LOGIN_LOAN_OPEN` читают только
  `process_boundary`/`process_loans`, `mode=None` по умолчанию у `_home_value`.
- **Успех** (`test_relay_road_success`, 21): `HOME` = relay-home, version и status на настоящем
  login-home; в relay-home в момент запуска ровно копия без refresh (литералы JSON, спелленные в
  тесте), настоящий login-home побайтно прежний, relay-home удалён; порядок событий; claim после
  входа и lease стоит в обоих моментах; Codex пишет и читает `-o` в relay-home (`ANSWER_WRITTEN`);
  review публикуется; Claude → Claude (другой instance, реальный verdict accept/reject из fake) и
  Codex checker после Claude doer; значение, которое ребёнок переписал в relay-лист, попадает в
  `_sensitive_values(relation)` и режет публикацию review; значения обеих копий в `sensitive_extra`
  даже при нечитаемом настоящем файле; relay-лист, испорченный ребёнком, — review не публикуется
  (`_login_echo`), а лист, вышедший из схемы, отдаёт сканам все свои тексты. **Для dispatch и
  checker флаг `_login_echo` не читается ни на одной дороге** (так было и до I2b); их защита от
  этого случая — значения в сканах.
- **Отказы до claim** (`test_relay_road_refusals`, 65). Общий `assert_refused_before_the_claim`
  (`failed`, закрытое предложение, слова runtime, нет задачи, число входов в boundary, нет маркера,
  нет relay-home, lease берётся снова) применён к отказам: 13 видов Claude и 4 Codex (лист,
  bootstrap, срок, plan, credman), срок на границе (60 + 600 с: 660 проходит, 659 нет; 3000 + 600:
  3600/3599), `relay_root`, `acl` на preflight и после mint, окружение по значениям
  (`ANTHROPIC_BASE_URL`, `https_proxy`, `CLAUDE_CODE_OAUTH_TOKEN`, `NODE_EXTRA_CA_CERTS`), лист,
  который status-вопрос переписал, `changed`, `refresh_leak`, `not_empty`, `relay_unusable`, `mint`,
  нет lease (проект без owner), lease другой папки, отказ входа, отказ claim (четыре вида
  исключений), spec до и после входа. **Остальные тесты файла проверяют меньше или другое и названы
  по своему делу:** готовность не кешируется (второй action, checker после doer) — по состоянию и
  числу задач; имя в `env_allow` без значения в окружении не судится — по успеху; sweep (убирает
  остаток; не убирает — `residue_detail` и lease; для checker `homes_refused`) — по своим
  предложениям; `claim_standing` — маркер стоит, так что помощник не годится (задачи нет, lease
  свободна, повтор `unknown`); чтение квот в запрещённом окружении —
  `NativeQuotaReadError('not_supported')` и ни одного spawn; review (2 теста, через runtime:
  состояние попытки, слова runtime, нет задачи и claim; lease свободна проверена во втором); checker
  (5 тестов: состояние, закрытая фраза, нет evidence, `verification_started`, нет relay-home,
  lease); login побайтно прежний после отказа входа.
- **Жизненный цикл** (`test_relay_road_lifecycle`, 15): `exit_error` → ошибка `could not start the
  pinned build`, маркер стоит, lease чистая, повтор — `unknown`; `retire(False)` → lease остаётся
  uncertain и следующая попытка отказана; timed_out и stopped — квитанция и relay удалён; отказ
  `discard` → `_retained`, `retained_detail` в квитанции, `publish` → `home_retained`, следующая
  дорога остановлена sweep до снятия отказа; второй проект на том же login → `login_owner_busy` до
  всякого вопроса; quota-чтение во время relay-попытки → `NativeQuotaDeferred`; `Ready` потребляется
  попыткой и сбрасывается вместе с выборкой дороги; **вопрос к настоящему login (version print,
  login status), который runner отказывается начинать, и домик проекта, который нельзя создать, не
  оставляют lease uncertain**.
- **Слова** (`test_relay_road_words`, 35): таблица `REASONS` — 30 строк, по одной на каждый код,
  фрагмент есть в источнике транспорта, слова не повторяются ни в наборе, ни в таблице продукта,
  строки после двух строк «что сделал ребёнок», слово о переменной login-папки только у отказов по
  сроку, закрытый ключ `login_not_ready` и его предложение.

## Мутанты

Копия `src`, `tests`, `pyproject.toml` вне репозитория (`Documents\Codex\work\i2b2-mut`, `-mut2`…
`-mut6`; несколько драйверов шли параллельно по непересекающимся спискам, у каждого своя копия и
свой `--basetemp` `im4<тег>`), `PYTHONPATH` на её `src`, проверено: `conductor.__file__` из копии.
M0 без изменений: **368 passed** (четыре relay-файла и четыре файла H5-V1; `mutants4.json`). После
каждого мутанта файл возвращён, SHA-256 сверён: у всех 69 «restored». Каждый мутант идёт с `-x`
(первый красный тест заканчивает прогон), поэтому число красных тестов на мутант не считалось;
**выживших нет**. Копии удалены. Драйвер, журналы и сборщик таблицы: `Documents\Codex\work\i2b2\`
(`mutate4.py`, `mutants4*.json`, `mutant_table2.py`). Дерево `src` и `tests` с момента запуска
драйверов не менялось: хеш `treehash.py` (90c2489bc8c56e2e, 31 файл) снят до запуска и перед
итоговыми прогонами, одинаковый.

Первая итерация: 42 мутанта; в первом прогоне выжил T3 (готовность не потребляется попыткой), тест
был усилен (две попытки одной дороги после одного preflight) и T3 стал красным. Во второй итерации
42 мутанта первой итерации прогнаны заново на итоговом коде (якоря сдвинулись вместе с кодом: C2,
R1, W1, W2, N3, N4, N5), все красные; добавлено 27 мутантов: по одному на каждое исправление и на
каждый новый или усиленный тест-страж (X1–X4, B1–B7, S2–S4, Y1–Y2, Z2, H2–H3, W4–W6, CTRL, G1, G1b,
G2, G3). Первый красный тест у W3 теперь `test_no_two_refusals…`: тест усилен, он сравнивает ещё и
таблицу продукта.

| Мутант | Что делает | Результат | Первый красный тест |
| --- | --- | --- | --- |
| P1 | the predicate covers every profile | красный: 1 failed | `test_subscription_road_boundary.py::test_every_door_refuses_a_subscription_road_with_no_relay_whatever_the_runners_gate[claude-code-without-relay-gate-closed]` |
| P2 | a runner that lends no relay home is asked nothing | красный: 1 failed, 12 passed | `test_subscription_road_boundary.py::test_a_relay_road_over_a_runner_that_lends_no_relay_home_is_refused_before_a_spawn[claude-code]` |
| P3 | a transport never confined is relayed | красный: 1 failed, 2 passed | `test_relay_road_success.py::test_the_home_a_spawn_is_told_about_is_the_relay_home_only_for_a_confined_task_attempt` |
| P4 | a spawn that is no task attempt is relayed | красный: 1 failed | `test_relay_road_success.py::test_a_claude_dispatch_runs_on_a_relay_home_and_leaves_the_real_login_as_it_was` |
| C1 | the claim is taken before the boundary is entered | красный: 1 failed, 5 passed | `test_relay_road_success.py::test_the_action_is_claimed_only_after_the_boundary_is_entered_and_the_lease_stands_at_both[claude-code]` |
| C2 | a claim that cannot be taken is an exception inside the lease | красный: 1 failed, 49 passed | `test_relay_road_refusals.py::test_a_claim_that_cannot_be_taken_inside_the_boundary_starts_nothing[not-contained]` |
| E1 | a refused entry is an exception inside the lease | красный: 1 failed, 48 passed | `test_relay_road_refusals.py::test_an_entry_of_the_boundary_that_is_refused_starts_nothing_and_leaves_no_marker` |
| E2 | a refusal to leave is a launch that did not start | красный: 1 failed | `test_relay_road_lifecycle.py::test_a_boundary_that_refuses_to_be_left_is_an_unknown_outcome_and_the_lease_stays_clean[claude-code]` |
| E3 | a lost launch is no error | красный: 1 failed | `test_relay_road_lifecycle.py::test_a_boundary_that_refuses_to_be_left_is_an_unknown_outcome_and_the_lease_stays_clean[claude-code]` |
| H1 | the child's home is the real login home | красный: 1 failed | `test_relay_road_success.py::test_a_claude_dispatch_runs_on_a_relay_home_and_leaves_the_real_login_as_it_was` |
| V1 | a refused copy is an exception inside the lease | красный: 1 failed, 41 passed | `test_relay_road_refusals.py::test_a_login_that_changed_between_its_proof_and_its_copy_is_refused_and_the_lease_is_clean` |
| R1 | the relay credential is not read back | красный: 1 failed, 12 passed | `test_relay_road_success.py::test_a_token_the_vendor_renewed_in_the_relay_home_joins_what_is_scanned_for[claude-code]` |
| R2 | an unreadable relay credential is not taken as echoed | красный: 1 failed, 16 passed | `test_relay_road_success.py::test_a_credential_the_child_spoilt_in_its_relay_home_is_taken_as_echoed` |
| R3 | the values of the copies are not remembered | красный: 1 failed, 12 passed | `test_relay_road_success.py::test_a_token_the_vendor_renewed_in_the_relay_home_joins_what_is_scanned_for[claude-code]` |
| R4 | the runner is not handed the values of the copies | красный: 1 failed, 14 passed | `test_relay_road_success.py::test_the_runner_and_the_road_hold_both_copies_of_the_login_even_if_the_file_cannot_be_read[claude-code]` |
| D1 | the relay home is not removed | красный: 1 failed | `test_relay_road_success.py::test_a_claude_dispatch_runs_on_a_relay_home_and_leaves_the_real_login_as_it_was` |
| D2 | a relay home that stays is not counted | красный: 1 failed, 10 passed | `test_relay_road_lifecycle.py::test_a_relay_home_that_cannot_be_removed_is_counted_and_nothing_of_it_is_published` |
| S1 | the readiness is proved before the login status | красный: 1 failed, 3 passed | `test_relay_road_success.py::test_the_road_asks_for_the_relay_folder_first_and_proves_the_login_after_its_last_question[claude-code]` |
| L1 | no check that the lease names this login | красный: 1 failed, 46 passed | `test_relay_road_refusals.py::test_a_project_without_a_live_owner_holds_no_lease_and_the_attempt_is_refused` |
| L2 | the lease is judged by no identity | красный: 1 failed, 47 passed | `test_relay_road_refusals.py::test_a_lease_that_names_another_folder_than_the_login_is_refused` |
| T1 | the margin of ten minutes is none | красный: 1 failed, 17 passed | `test_relay_road_refusals.py::test_a_login_that_ends_before_the_attempt_is_refused_and_a_new_sign_in_is_asked_for[claude-code]` |
| T2 | the timeout of the attempt is not in the horizon | красный: 1 failed, 20 passed | `test_relay_road_refusals.py::test_the_login_must_outlast_the_timeout_of_this_attempt_by_ten_minutes[60-659-False]` |
| T3 | the readiness is kept after the attempt | красный: 1 failed, 3 passed | `test_relay_road_lifecycle.py::test_the_readiness_is_spent_by_the_attempt_it_was_proved_for` |
| W1 | the environment is judged by the names a row lists | красный: 1 failed, 36 passed | `test_relay_road_refusals.py::test_the_same_name_allowed_but_not_present_in_the_environment_is_not_selected` |
| W2 | the environment is not judged | красный: 1 failed, 30 passed | `test_relay_road_refusals.py::test_a_name_that_replaces_the_login_or_reroutes_it_is_refused_where_it_is_really_selected[ANTHROPIC_BASE_URL]` |
| A1 | the folders are not read at the readiness | красный: 1 failed, 27 passed | `test_relay_road_refusals.py::test_a_folder_that_could_open_the_login_to_a_container_is_refused_before_the_claim[claude-code]` |
| A2 | the folders are not read again with the relay home | красный: 1 failed, 29 passed | `test_relay_road_refusals.py::test_a_folder_found_open_after_the_relay_home_was_made_is_refused_and_the_home_goes` |
| K1 | the relay homes of earlier attempts are not swept | красный: 1 failed, 37 passed | `test_relay_road_refusals.py::test_a_relay_home_an_earlier_attempt_left_is_removed_by_the_sweep_and_the_run_goes_on` |
| K2 | a relay folder that cannot be proved is let through | красный: 1 failed, 26 passed | `test_relay_road_refusals.py::test_a_relay_folder_that_cannot_be_proved_is_refused_before_any_question_is_asked` |
| Q1 | a login not ready is a build that failed its preflight | красный: 1 failed, 24 passed | `test_relay_road_refusals.py::test_the_independent_check_asks_for_the_login_again_after_the_doer_has_finished` |
| Q2 | a relay folder refusal of the checker is a leftover | красный: 1 failed, 40 passed | `test_relay_road_refusals.py::test_a_relay_folder_that_cannot_be_proved_for_the_checker_is_a_login_not_ready` |
| Z1 | a relay home is read as a home of the project | красный: 1 failed, 1 passed | `test_relay_road_success.py::test_a_codex_dispatch_runs_on_a_relay_home_and_reads_its_final_message_from_it` |
| F1 | a readiness the road did not spend outlives the road | красный: 1 failed, 4 passed | `test_relay_road_lifecycle.py::test_a_readiness_the_road_did_not_spend_is_dropped_with_the_sample_of_that_road` |
| W3 | the relay refusal words stand before the words of what a child did | красный: 1 failed, 31 passed | `test_relay_road_words.py::test_no_two_refusals_share_their_words_and_none_names_a_path_or_a_vendor_value` |
| N1 | a review road does not turn a refusal before the claim into a receipt | красный: 1 failed, 59 passed | `test_relay_road_refusals.py::test_a_review_whose_boundary_entry_is_refused_fails_before_its_claim` |
| N2 | a dispatch road does not turn a refusal before the claim into a receipt | красный: 1 failed, 29 passed | `test_relay_road_refusals.py::test_a_folder_found_open_after_the_relay_home_was_made_is_refused_and_the_home_goes` |
| N3 | a review attempt is never claimed | красный: 1 failed, 8 passed | `test_relay_road_success.py::test_a_claude_review_runs_on_a_relay_home_and_its_text_is_published` |
| N4 | a checker attempt is never claimed | красный: 1 failed, 9 passed | `test_relay_road_success.py::test_claude_is_checked_by_another_claude_instance_each_on_its_own_relay_home` |
| N5 | a dispatch attempt is never claimed | красный: 1 failed | `test_relay_road_success.py::test_a_claude_dispatch_runs_on_a_relay_home_and_leaves_the_real_login_as_it_was` |
| N6 | the runner's relay question ignores the relay home | красный: 1 failed, 28 passed | `test_relay_home_native.py::test_the_runners_own_question_reads_the_relay_home_only_when_it_is_given_one` |
| N7 | the runner's relay question never reads the login side | красный: 1 failed, 27 passed | `test_relay_home_native.py::test_the_runners_own_question_is_the_one_the_transport_asks_before_and_after_the_home` |
| K3 | the checker has no closed key for a login not ready | красный: 1 failed, 24 passed | `test_relay_road_refusals.py::test_the_independent_check_asks_for_the_login_again_after_the_doer_has_finished` |
| X1 | a question to the real login the runner cannot start is an exception under the lease | красный: 1 failed, 5 passed | `test_relay_road_lifecycle.py::test_a_question_to_the_real_login_that_the_runner_refuses_to_start_leaves_the_lease_clean[version-print]` |
| X2 | a project home that cannot be made for a question is an exception under the lease | красный: 1 failed, 7 passed | `test_relay_road_lifecycle.py::test_a_project_home_that_cannot_be_made_for_a_question_is_a_receipt_and_the_lease_is_clean` |
| X3 | no spawn is a question to the real login | красный: 1 failed, 5 passed | `test_relay_road_lifecycle.py::test_a_question_to_the_real_login_that_the_runner_refuses_to_start_leaves_the_lease_clean[version-print]` |
| X4 | a carried error is not raised again | красный: 1 failed, 7 passed | `test_relay_road_lifecycle.py::test_a_project_home_that_cannot_be_made_for_a_question_is_a_receipt_and_the_lease_is_clean` |
| B1 | a claim refused by the owner or the runner is not a claim refusal | красный: 1 failed, 51 passed | `test_relay_road_refusals.py::test_a_claim_that_cannot_be_taken_inside_the_boundary_starts_nothing[owner-refused]` |
| B2 | a claim that left its marker is not told so | красный: 1 failed, 53 passed | `test_relay_road_refusals.py::test_a_marker_that_cannot_be_looked_at_after_a_failed_claim_is_taken_as_standing` |
| B3 | every failed claim is told to leave its marker | красный: 1 failed, 49 passed | `test_relay_road_refusals.py::test_a_claim_that_cannot_be_taken_inside_the_boundary_starts_nothing[not-contained]` |
| B4 | a marker that cannot be looked at is taken as absent | красный: 1 failed, 53 passed | `test_relay_road_refusals.py::test_a_marker_that_cannot_be_looked_at_after_a_failed_claim_is_taken_as_standing` |
| B5 | a checker claim that left its marker is not a marker standing | красный: 1 failed, 64 passed | `test_relay_road_refusals.py::test_a_checker_whose_claim_cannot_be_taken_starts_nothing_and_says_a_marker_stands[marker-written]` |
| B6 | a checker claim that fails is a login not ready | красный: 1 failed, 63 passed | `test_relay_road_refusals.py::test_a_checker_whose_claim_cannot_be_taken_starts_nothing_and_says_a_marker_stands[no-marker]` |
| B7 | the checker claims its check before its attempt, not inside the boundary | красный: 1 failed, 61 passed | `test_relay_road_refusals.py::test_a_checker_whose_entry_is_refused_claims_nothing_and_leaves_the_lease_clean` |
| S2 | the command is built after the claim | красный: 1 failed, 56 passed | `test_relay_road_refusals.py::test_a_command_that_cannot_be_made_for_the_boundary_is_refused_before_the_claim` |
| S3 | a command that cannot be built before the boundary is an exception under the lease | красный: 1 failed, 55 passed | `test_relay_road_refusals.py::test_a_command_that_cannot_be_built_for_the_relay_home_is_refused_before_the_boundary` |
| S4 | a command that cannot be made for the boundary is a refused entry | красный: 1 failed, 56 passed | `test_relay_road_refusals.py::test_a_command_that_cannot_be_made_for_the_boundary_is_refused_before_the_claim` |
| Y1 | the environment is judged only after the questions to the real login | красный: 1 failed, 30 passed | `test_relay_road_refusals.py::test_a_name_that_replaces_the_login_or_reroutes_it_is_refused_where_it_is_really_selected[ANTHROPIC_BASE_URL]` |
| Y2 | a quota read does not judge the environment | красный: 1 failed, 34 passed | `test_relay_road_refusals.py::test_a_quota_read_in_an_environment_that_reroutes_the_login_is_not_supported[claude-code]` |
| Z2 | the texts of a credential out of its shape are not scanned for | красный: 1 failed, 17 passed | `test_relay_road_success.py::test_every_text_of_a_relay_credential_that_left_its_shape_joins_what_is_scanned_for` |
| H2 | a new sign-in is asked for without the login variable | красный: 1 failed, 12 passed | `test_relay_road_refusals.py::test_a_claude_login_that_cannot_be_copied_is_refused_before_the_claim[expiry_unknown]` |
| H3 | a refusal sentence is never told the login variable | красный: 1 failed, 12 passed | `test_relay_road_refusals.py::test_a_claude_login_that_cannot_be_copied_is_refused_before_the_claim[expiry_unknown]` |
| W4 | a claim whose marker stands has no words of the runtime | красный: 1 failed, 54 passed | `test_relay_road_refusals.py::test_a_claim_that_fails_after_its_marker_was_written_says_that_the_marker_stands` |
| CTRL | a subscription review of a relay road is refused (the control proves a review ran) | красный: 1 failed | `test_relay_road_success.py::test_a_review_that_prints_the_access_token_of_its_copy_is_not_published` |
| G2 | a refused entry rewrites the real login (a write-back) | красный: 1 failed, 60 passed | `test_relay_road_refusals.py::test_the_login_of_every_refused_attempt_is_byte_for_byte_what_it_was` |
| G3 | the phrase of a login refusal is another than the table of the suite | красный: 1 failed | `test_relay_road_words.py::test_the_phrases_this_suite_spells_are_the_ones_the_product_writes_for_every_login_refusal` |
| W5 | two refusals of the runtime table share their words | красный: 1 failed, 6 passed | `test_relay_road_words.py::test_every_refusal_sentence_earns_the_words_the_runtime_owns[claim_standing]` |
| W6 | a row of the runtime table stands before the rows of what a child did | красный: 1 failed, 33 passed | `test_relay_road_words.py::test_a_sentence_of_what_a_child_did_is_never_taken_for_a_refusal` |
| G1 | a platform with no boundary does not refuse a relay road | красный: 1 failed, 12 passed | `test_subscription_road_boundary.py::test_a_relay_road_over_a_runner_that_lends_no_relay_home_is_refused_before_a_spawn[claude-code]` |
| G1b | the same, asked of the one test that names the platform without a boundary | красный: 1 failed, 2 passed | `test_subscription_road_boundary.py::test_where_the_platform_has_no_boundary_the_login_is_not_named[relay-linux]` |

## Отклонения

Строки 1–14 — первой итерации (обновлены там, где вторая их изменила); 15–22 — второй. До
утверждения статус не выше «локально проверено».

| Что | Почему | Кто утвердил |
| --- | --- | --- |
| 1. `ProcessRunner.relay_acl_refusal` — статический метод в `process.py` без проверки платформы; `process.py` ровно 800 строк: три блока текста переписаны (комментарий `RELAY_HOME_LOANS`, docstring `container_profile`, комментарий в `ProcessAdapter.execute`), смысл прежний, ссылка `entry_lends_relay_homes` и дата 23.09.2026 сохранены | страж `test_native_creation_helper_has_only_the_owned_runner_as_a_caller` допускает `_winlaunch` только в `process.py`, а запас файла был три строки; проверка `os.name`, как у `ensure_relay_root`, не поместилась. Вне Windows `_winlaunch` не импортируется (`ImportError`), а транспорт до этого не дойдёт: `boundary_provided` ложно. Первая итерация написала «два блока» и убрала из двух ссылку и дату (Л3.8); точное описание — в таблице «Изменения» | Codex 26.10: DECISION-REPORT, п. 1 |
| 2. Отказ до claim поднимает `_attempt` исключением `RelayNotStarted` (вне lease), а не квитанцией | `_attempt` возвращает `ProcessOutcome`; тот же механизм, что `LoginLeaseRefused` (его ловят те же три места). Под lease — только значения, как требует C3 | Codex 26.10: DECISION-REPORT, п. 2 |
| 3. `claim` — `Claim` (вызываемое со вторым методом `stands()`), аргумент `_attempt` на всех дорогах: не-relay берёт его первым (прежний порядок), relay — после входа и после построения spec | C2: для relay claim стоит после входа; одно место вместо трёх разных вызовов у dispatch, review и checker; `stands()` нужен, чтобы квитанция не расходилась с маркером (Л1.3) | Codex 26.10: DECISION-REPORT, п. 3 |
| 4. `Ready` лежит в `RelayAttempt._relay_ready` между preflight и попыткой одной дороги; попытка его потребляет, `_forget_login_sample` сбрасывает | `_preflight` возвращает только квитанцию. Первая версия добавляла `_preflight(request, mode)` и сломала два дублёра тестов с одним аргументом (`test_independent_review_evidence_commit`, `test_command_input_binding`) — сигнатуру вернул: режим релевантен только как «confine и relay-дорога», оба режима попытки relay-ятся одинаково | Codex 26.10: DECISION-REPORT, п. 4 |
| 5. Отказ `claim` внутри boundary (`WorkspaceNotContained`, `OSError`, `OwnerRefused`, `ProcessRunnerError`) — значение: `NotStarted("claim")` или, если marker после отказа стоит (или не читается), `NotStarted("claim_standing")` с отдельной фразой и словами runtime; у checker оба кода — `marker_standing`. **Неточность, которую я несу:** у checker отказ claim, не оставивший marker, всё равно отвечает «this action already claimed its independent checker» — закрытого ключа «claim не взят» нет | в задании названы отказы sweep/copy-in/enter; исключение из claim под lease сделало бы lease uncertain из-за пути. Первая версия не различала marker (Л1.3) и не знала `OwnerRefused` (Л1.2). Новый закрытый ключ checker — решение ведущего (открытый вопрос 13) | Codex 26.10: DECISION-REPORT, п. 5 |
| 6. Готовность считается по `self._clock()` (строка часов продукта), а не по wall time | детерминизм тестов (`clock` — граница, которую подменяют); в production часы — настоящее UTC (`server.py:99`). Часы без зоны или не время — `expiry_unknown`, не «свежо» | Codex 26.10: DECISION-REPORT, п. 6 |
| 7. `leaf_kind` (вид имени в relay-home) вынесен в `relay_home.py`, а не в `HarnessWorkspace` | `harness_workspace.py` — 791 строка; `home_leaf_kind` ждёт home проекта. `codex_cli._read_attempt_home` зовёт `_home_leaf_kind`, который выбирает по родителю home | Codex 26.10: DECISION-REPORT, п. 7 |
| 8. `relay_home.py` (в `SDK_WORKSPACE_DOOR`) получил импорты `ownership`, `ownership_native.identity`, `containment.portal_violation`; `harness_workspace` импортируется внутри `leaf_kind` | `lease_names` читает владельца и identity; верхний импорт `harness_workspace` даёт цикл `process` → `relay_home` → `harness_workspace` → `process` | Codex 26.10: DECISION-REPORT, п. 8 |
| 9. `relay_attempt.py` не внесён в `SDK_WORKSPACE_DOOR` | модуль value-only: файловую и временную работу делают `login_relay` и `relay_home` (уже двери), `.run` в нём нет; тип `WorkspaceNotContained` импортируется только для `CLAIM_REFUSALS` | Codex 26.10: DECISION-REPORT, п. 9 |
| 10. `tests/test_accept_capture.py`: дублёр `Checker` получил `_relay_start`, `_relay_refused` и `_claim_of` | общая дорога проверки читает три новых шва; поведение теста и его утверждения не менялись | Codex 26.10: DECISION-REPORT, п. 10 |
| 11. Красная фаза: 36 из 154 падений — не сравнение, а отсутствие нового модуля (`ModuleNotFoundError`, `ImportError`) | модуль `relay_attempt` импортируется внутри теста слов и теста пропуска preflight (модульный импорт ломал бы сбор файла целиком, что хуже для учёта); 96 падений — сравнения, 14 — отказ дорог, которые обязаны допускаться | Codex 26.10: DECISION-REPORT, п. 11 |
| 12. `retire(False)` в тесте задан на уровне lease (`hold()(False)` после работы ребёнка), а не отказом завершения настоящего дерева | настоящий отказ завершения дерева на этой машине не воспроизвести детерминированно. Ревью Opus независимо показало на настоящей `LoginLease` подменой `_procgroup._JobGroup.retired` → `False` то же (owner `recovery_required`, lease uncertain, relay-home удалён); сам отказ runner'а проверяют его нативные тесты | Codex 26.10: DECISION-REPORT, п. 12 |
| 13. Нет нативного свидетеля «транспорт + настоящий `ProcessRunner` + AppContainer + fake CLI» | задание требует свидетеля runner'а (существующие нативные файлы зелёные; к ним добавлены два теста вопроса `ProcessRunner.relay_acl_refusal`) и поведенческие тесты на дублёре boundary; fake-бинарь не запустить внутри AppContainer (он читает репозиторий по запечённым путям); полный сквозной нативный проход — живой цикл | Codex 26.10: DECISION-REPORT, п. 13 |
| 14. Данные тестовых швов: `_fakeboundary` (hooks, `outcome`, дубли `ensure_relay_root`/`relay_acl_refusal`, `auth_homes`), `_fakeclaude`/`_fakecodex` (`HOME_REPORT`, `ROTATE_ACCESS`), `_fakehome.py` | швы нужны, чтобы увидеть home ребёнка и момент входа/запуска; прежние тесты (затронутый набор) зелёные | Codex 26.10: DECISION-REPORT, п. 14 |
| 15. Вопросы к настоящему login на relay-дороге (version print, login status, чтение квот): отказ runner'а до ребёнка — значение `LaunchLost`, домик проекта, который нельзя создать, — значение `CarriedError`; `_attempt` вне lease поднимает ту же ошибку или то же исключение (`_asks_the_real_login`) | Л1.1: исключение внутри lease делало lease uncertain до перезагрузки, а на `HEAD` подписочную дорогу отказывал `_boundary_refusal` ещё до preflight (H5-V1), так что в production этот путь стал достижим только с I2b. Видимое поведение прежнее (та же ошибка `could not start the pinned build`, та же квитанция «uncontained»). Собственный сигнал runner'а `retire(False)` не очищается (проба: исчезнувший pinned-файл → `OwnerRefused recovery_required`) — вариант «Б» ревью; решение ведущего о варианте «А» (записать ограничение) не понадобилось | Codex 26.10: DECISION-REPORT, п. 15 |
| 16. `_route_selected()` судит окружение первым делом в `_login_home_refusal` (до version print) и в `subscription_quota._read` (`not_supported`); на readiness повторено | Л2.1: дизайн §3.9 ставил проверку в `_login_home_refusal` и в quota; первая итерация поставила её последним шагом, после двух вопросов к настоящему login в том же окружении | Codex 26.10: DECISION-REPORT, п. 16 |
| 17. `confined_spec` строится после входа в boundary и до claim, а не до входа | Л1.4: ему нужны `boundary` и `paths`, которые выдаёт вход; отказы `runner.run` (cwd, `holds_entry`) остаются `LaunchLost`, как просил ревьюер | Codex 26.10: DECISION-REPORT, п. 17 |
| 18. Relay-лист, вышедший из схемы, отдаёт сканам все свои тексты длиной ≥ 12 (`login_relay.every_text`); флаг `_login_echo` по-прежнему читает только review | Л2.2: какой из текстов — токен, сказать нельзя; чтение флага dispatch и checker — не свойство relay (на старых дорогах его тоже нет), решение ведущего (открытый вопрос 10) | Codex 26.10: DECISION-REPORT, п. 18 |
| 19. Тесты подменяют внутренности продукта, а не только границы (стандарт §2.4): `adapter._login_secrets` (файл «нечитаем в момент spawn»: между copy-in и spec нет границы ФС, в которую можно вмешаться); `ProjectOwner.leased_login` (гард всегда берёт lease того login, что назвал транспорт, lease другой папки публично недостижима, `lease_names` — защита в глубину); `HarnessWorkspace.claim`, `claim_verification`, `is_claimed`, `Path.write_text` для `*.marker` (отказ записи marker и потеря owner между входом и claim на ФС этой машины не воспроизводятся; попытка вынести на границу ФС — файл на месте папки run — отказала раньше claim, в `is_claimed`, как «uncontained»); `HarnessWorkspace.mint_home`; `relay_attempt.attempt_spec` и `harness_attempt.confined_spec` (argv, который нельзя собрать, из проверенного пина не получить); обёртка `site.runner.run` (отказ runner'а до ребёнка воспроизводится только ею); `site.runner._environ` (окружение процесса runner'а); дублёр boundary с hooks — по заданию | Л3.6: это инъекции отказа, недостижимого через публичный шов; где граница ФС или времени доступна, она использована (часы продукта, файлы входа, остаток relay-home, права на удаление) | Codex 26.10: DECISION-REPORT, п. 19 |
| 20. Прямые вызовы внутренних методов в трёх тестах: `adapter._attempt`, `_relay_start`, `_preflight`, `_relay_ready`, `_forget_login_sample`, `_home_value` (`test_the_readiness_is_spent_by_the_attempt_it_was_proved_for`, `test_a_readiness_the_road_did_not_spend_is_dropped_with_the_sample_of_that_road`, `test_the_home_a_spawn_is_told_about_is_the_relay_home_only_for_a_confined_task_attempt`) | инвариант «одна готовность — одна попытка» публичной дорогой не нарушить (она всегда делает preflight перед попыткой); публичный эффект проверен отдельно (второй action и checker после doer: `…readiness_is_asked_again_for_every_attempt…`, `…independent_check_asks_for_the_login_again…`) | Codex 26.10: DECISION-REPORT, п. 20 |
| 21. Слова отказа по сроку называют переменную login-папки (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) и команду входа без пути | Л2.3: команда без переменной вела бы владельца в глобальный профиль вендора, что запрещает TASK п. 1; формулировка `_login_preflight` | Codex 26.10: DECISION-REPORT, п. 21 |
| 22. Тест `test_where_the_platform_has_no_boundary_the_login_is_not_named` теперь идёт и без relay, и с relay | Л3.5: без relay-варианта свидетеля «Linux и macOS с relay» в наборе не было | Codex 26.10: DECISION-REPORT, п. 22 |

## Не проверено

- Живые CLI (M2 Codex, M2 Claude на продуктовом пути) и весь цикл: ни один вендорский CLI не
  запускался. Работает ли Claude на копии без `refreshToken` и с `{oauthAccount}` и Codex на пустом
  `refresh_token`, из этих тестов не следует.
- Сквозной запуск транспорта в настоящем AppContainer (см. отклонение 13): `FolderLoans`,
  `relay_acl_refusal` по настоящим DACL и транспорт проверены раздельно (нативные файлы runner'а;
  поведение транспорта — на дублёре boundary).
- Linux и macOS, CI, полный core и кириллический полный прогон (R5-PLAN п. 9), browser gate, wheel.
  Windows не закрывает Linux и macOS; тесты relay-дороги не используют ничего специфичного для
  Windows, кроме нативных файлов, но на POSIX не прогонялись.
- `write_failed` сквозным путём (запись в relay-home, которая не удалась): код есть в таблице и
  слов, поведение держит `test_login_relay_flow` (I2a).
- Часы: ни один тест не проверяет срок против настоящего времени — только против часов продукта.
- Конкуренция двух процессов над одним relay-корнем и потеря процесса между mint и discard не
  воспроизводились (остаток убирает sweep следующей дороги — этот путь проверен).
- Ветка `server_read is not None` в `RelayAttempt._relay_spec` (код `spec`): из транспортов
  недостижима, тестом не покрыта.
- `claim_standing` для review проверен только общим кодом с dispatch и тестом checker; отдельного
  теста review с половинной записью marker нет. Чтение квот, у которого version print или запрос не
  стартовал (`LaunchLost` общего `_attempt`), отдельным тестом не проверено: проверены version print
  и login status перед dispatch.
- Не проверено, что вся документация владельца ещё называет H5-V1: это I3.

## Открытые вопросы

1. **Окружение и H5-A-Р3.** Решение Р3 из `2a5bcdd` допускает «точный code-owned refresh override
   только для access-only процессов». Моя проверка (`forbidden_env` по выбранному окружению,
   `forced_env` включён) откажет такое имя, если оно попадёт в `forced_env` профиля или в
   `env_allow`. Исключение должно быть code-owned и точным (имя и значение), решение для задачи A.
   Рекомендация: не ослаблять `forbids`, а передавать override мимо выбора оператора (константа
   спецификации), и проверять, что в окружении именно оно.
2. **Место login-home.** Транспорт требует `…\DecemberCommand\logins\<name>`; иной путь — «relay
   folder is not usable» (`root`) до первого вопроса. Мастер, runbook и тексты I3 обязаны сказать
   это владельцу; сейчас он увидит только закрытую фразу.
3. **`process.py` на лимите.** 800 строк, запас нулевой. Следующая правка runner'а начнётся с выноса
   (`container_profile`/relay-статики в отдельный модуль); `harness_workspace.py` — 791 строка.
4. **Поведение при выходе relay-листа из схемы.** Любой лист, не проходящий `spec.admit` после
   попытки (например, живой Claude допишет поле), делает `_login_echo = True`, и review не
   публикуется; все его тексты ≥ 12 символов входят в сканы (dispatch, checker). Это fail-closed;
   ослаблять только по измеренному M2.
5. **Один ключ `login_not_ready` у checker.** Журнал не различает код отказа (срок, окружение,
   папки, spec); если нужен разбор для человека, нужны отдельные ключи. Рекомендация: пока оставить,
   причину того же login видно по отказу его dispatch.
6. **Нет учёта аккаунта в доказательствах.** `Ready.account`/`Ticket.account` доступны, но в
   evidence цикла не попадают (в задании: «фиксировать доступную идентичность в доказательствах»).
   Решение за I3/циклом; рекомендация: хеш `account` в доказательствах.
7. **Закрыт во второй итерации:** quota при запрещённом окружении (`not_supported`) — Л2.1.
8. **Закрытый набор ключей `oauthAccount`** (вопрос 2 I2a) и перечень F10 (вопрос 7 I2a) остаются
   как были.
9. **Claim.** При отказе записи marker после его создания квитанция теперь `failed` с фразой
   `claim_standing` («marker стоит, повтор `unknown`»). Ведущий подтверждает выбор: альтернатива —
   считать такой отказ `unknown` сразу (как `LaunchLost`), что согласуется с повтором, но называет
   «не запускалось» неточно.
10. **Флаг `_login_echo` у dispatch и checker.** Ни на одной дороге dispatch и checker его не читают
    (читают review, чтение квот, Kimi). Для relay риск малый (без refresh token ребёнок не получит
    нового токена), поэтому не расширял. Если нужно: записывать флаг в факт попытки (как `retained`
    в `_Attempt`/`AttemptEvidence`), отказывать `publish` dispatch кодом `env_echo`, у checker
    считать `no_verdict`. Решение ведущего.
11. **Окно 8 с в `tests/test_login_ownership.py`.** `entered.wait(8)` короче худшего времени запуска
    fake-ребёнка на этой машине (1–17 с, измерено, не зависит от моего кода; раздел «Проверки»).
    Красный в промежуточном прогоне не закрыт повтором. Решение Codex или ведущего: предусловие по
    стандарту §2.4 (замер времени запуска до проверки поведения) или другое окно.
12. **Исчезнувший pinned-файл.** Между проверкой и запуском pinned-сборка исчезла — runner сам пишет
    `retire(False)` («a process loan did not prove retirement»), project owner и lease требуют
    recovery. Это fail-closed по C3 и не менялось; runbook (I3) должен сказать владельцу, что это
    значит и как восстановить.
13. **Закрытый ключ checker для «claim не взят».** Сейчас отказ claim без marker отвечает
    `marker_standing` («this action already claimed its independent checker») — неточно.
    Рекомендация: ключ `claim_refused` и слова «the checker could not claim its check, so nothing
    was started».

## Ревью Opus

Три линзы: **Л1** «lease, claim, исключения» (C2, C3; approve_with_notes, 5 minor), **Л2**
«credentials и утечки» (approve_with_notes, 3 minor), **Л3** «доказательность и стандарт»
(request_changes: 1 major, 9 minor). Всего 18 находок. Каждую я проверил сам: воспроизвёл тестом,
который красен на коде, возвращённом к старому поведению (мутант — раздел «Мутанты»), затем
исправил или записал, почему нет. Итог: **16 подтверждены и исправлены, 2 подтверждены частично
(Л1.4, Л2.2), отвергнутых нет.** Все имена тестов — в `tests/`, мутанты — в таблице раздела
«Мутанты».

| № | Серьёзность | Статус | Что сделано и чем доказано |
| --- | --- | --- | --- |
| Л1.1 | minor | подтверждена, исправлена (вариант «Б») | Вопрос к настоящему login (version print, login status), который runner отказывается начинать, поднимал исключение внутри lease, и lease оставалась uncertain до перезагрузки; на `HEAD` подписочную дорогу отказывал `_boundary_refusal` ещё до preflight (H5-V1), так что в production этот путь стал достижим только с I2b. Теперь `_asks_the_real_login(mode)` (mode `None` на relay-дороге): отказ `_spawn` — значение `LaunchLost`, невозможность создать домик проекта — `CarriedError`; `_attempt` вне lease поднимает ту же ошибку (`could not start the pinned build`) или то же исключение (`WorkspaceNotContained` → прежняя квитанция «uncontained»). Тесты: `test_a_question_to_the_real_login_that_the_runner_refuses_to_start_leaves_the_lease_clean[version-print\|login-status]` (после отказа lease свободна, следующий action успешен), `test_a_project_home_that_cannot_be_made_for_a_question_is_a_receipt_and_the_lease_is_clean`; мутанты X1–X4 красные. **Не очищено, как требует C3:** проба вне репозитория (pinned-файл исчез между проверкой и запуском) даёт `OwnerRefused recovery_required: a process loan did not prove retirement` — собственный `retire(False)` runner'а; открытый вопрос 12 |
| Л1.2 | minor | подтверждена, исправлена | Отказ claim через `OwnerRefused` (`ownership_lost`) или `ProcessRunnerError` не был в списке и уходил во внешний `except`, давая `NotStarted("enter")` и квитанцию «boundary отказал relay-home». Теперь `CLAIM_REFUSALS = (WorkspaceNotContained, OSError, OwnerRefused, ProcessRunnerError)` → `NotStarted("claim")`. Тест `test_a_claim_that_cannot_be_taken_inside_the_boundary_starts_nothing[not-contained\|os-error\|owner-refused\|runner-error]` (общий помощник: failed, закрытое предложение, слова runtime, нет задачи, нет маркера, lease свободна); B1 красный на `[owner-refused]` |
| Л1.3 | minor | подтверждена, исправлена | Квитанция «не взято, задачи нет» при стоящем marker расходилась с состоянием: повтор давал `unknown` без объяснения. Теперь после отказа claim смотрит `Claim.stands()`: marker стоит (или не читается — считается стоящим) → закрытый код `claim_standing`: «the claim of the action could not be completed but its marker stands, and a repeat of the action is unknown» (+ слова runtime, 30-я строка); иначе `claim`. Тесты `test_a_claim_that_fails_after_its_marker_was_written_says_that_the_marker_stands` (повтор действия — `unknown`), `test_a_marker_that_cannot_be_looked_at_after_a_failed_claim_is_taken_as_standing`; мутанты B2, B3, B4, W4. У checker оба кода — `marker_standing` (B5) |
| Л1.4 | minor | подтверждена частично | «Готовить spec до claim» исполнено, «до входа» нельзя: `confined_spec` берёт `boundary` и `paths` из входа в boundary. Теперь порядок: вход → spec → claim; ошибка построения — `NotStarted("spec")` (маркера нет, lease чистая); отказы `runner.run` (cwd, `holds_entry`) остаются `LaunchLost`, как предложил ревьюер. Тест `test_a_command_that_cannot_be_made_for_the_boundary_is_refused_before_the_claim`; мутанты S2 (spec после claim), S4 |
| Л1.5 | minor | подтверждена (пробел в тестах) | Тесты checker: `test_a_checker_whose_entry_is_refused_claims_nothing_and_leaves_the_lease_clean` (B7), `test_a_checker_that_cannot_leave_the_boundary_has_claimed_its_check_and_is_not_repeated` (check claimed, evidence нет, lease свободна; ключ `material_unavailable`, а не `VERIFY_RAISED`: дорога checker отвечает им на любое исключение попытки, моё наблюдение отличается от пробы ревью, поведение прежнее), `test_a_checker_whose_claim_cannot_be_taken_starts_nothing_and_says_a_marker_stands[no-marker\|marker-written]` (B5, B6) |
| Л2.1 | minor | подтверждена, исправлена | Воспроизведено: с `ANTHROPIC_BASE_URL` в выбранном окружении ушли version и login status на настоящий login-home (`site.rows()` 2). Теперь `_route_selected()` — первым делом в `_login_home_refusal` (до version print) и в `subscription_quota._read` (`not_supported`); на readiness проверка повторена. Тесты: усилен `test_a_name_that_replaces_the_login_or_reroutes_it_is_refused_where_it_is_really_selected` (`site.rows() == []`, события `["relay-root"]`; Y1), новый `test_a_quota_read_in_an_environment_that_reroutes_the_login_is_not_supported[claude-code\|codex]` (Y2) |
| Л2.2 | minor | подтверждена частично | (а) Значения relay-листа, вышедшего из схемы, не попадали в сканы — подтверждено, исправлено: `login_relay.every_text` собирает все тексты ≥ 12 символов такого документа (`test_every_text_of_a_relay_credential_that_left_its_shape_joins_what_is_scanned_for`, Z2). (б) Флаг `_login_echo` читает только review — подтверждено, но это не свойство relay: `grep` по `src` находит читателей только в `artifact_transport.py` (review), `subscription_quota.py` (чтение квот) и `kimi_code.py`; dispatch и checker не читают его на старых дорогах тоже. Расширять — решение ведущего; docstring `_read_relay_home` и текст отчёта сужены до «review не публикуется, для dispatch и checker защита — значения»; открытый вопрос 10 |
| Л2.3 | minor | подтверждена, исправлена | Отказ по сроку предлагал `auth login --claudeai` без переменной login-папки, и человек вошёл бы в глобальный профиль вендора. Теперь `…; sign in again with CLAUDE_CONFIG_DIR\|CODEX_HOME set to the login directory this provider pins and run <команда>` (имя из `profile.home_env`, пути нет). Тесты: `SIGN_IN` в refusals и words, `test_the_login_directory_of_a_new_sign_in_is_named_by_its_variable_and_never_by_its_path`; H2, H3 |
| Л3.1 | **major** | подтверждена, исправлена | Порядок C2 «вход → claim» и «отказ входа → нет маркера, чистая lease» для checker держится тестом (см. Л1.5); мутант MY4 ревьюера (checker берёт claim до `_attempt`) — B7 красный |
| Л3.2 | minor | подтверждена, исправлена | Тест на отказ claim у checker добавлен (Л1.5); MY1 ревьюера (всегда `login_not_ready`) — B6 красный. Остаток — отклонение 5: checker при отказе claim без marker всё равно отвечает `marker_standing` |
| Л3.3 | minor | подтверждена, исправлена | Путь `spec` проверен двумя тестами: до входа (`relay_attempt._relay_spec`, `test_a_command_that_cannot_be_built_for_the_relay_home_is_refused_before_the_boundary`, S3 — MY3 ревьюера) и после входа (`confined_spec`, S4). Ветка `server_read is not None` недостижима из транспортов — в «Не проверено» |
| Л3.4 | minor | подтверждена, исправлена | Красная фаза снята заново на итоговых тестах (154 / 214, раздел «Проверки»); именованы стражи, зелёные на старом коде, с причиной и мутантом; контроль усилен (`len(site.tasks()) == 1` и `_login_echo is True`, CTRL); `test_no_two_refusals_share_their_words…` теперь сверяет и таблицу продукта (W5, W3); `test_the_login_of_every_refused_attempt…` проверяет, что дорога дошла до boundary (G2) |
| Л3.5 | minor | подтверждена, исправлена | `test_where_the_platform_has_no_boundary_the_login_is_not_named` параметризован `strip` [True, False] × Linux/macOS, проверяет и `runner.events == []`; G1b красный на `[relay-linux]` |
| Л3.6 | minor | подтверждена, исправлена | Подмены внутренностей продукта и прямые вызовы внесены в «Отклонения» (19, 20) с причиной каждой. Одну (отказ записи marker) пробовал заменить границей ФС (файл на месте папки run): путь отказывает раньше claim, в `is_claimed`, как «uncontained», и до claim не доходит |
| Л3.7 | minor | подтверждена, исправлена | Формулировки сужены: «Что именно держит тестовая часть» называет, какие тесты проверяют всё (общий помощник), а какие меньше; тесты «lease другой папки» и «claim» доведены до `assert_refused_before_the_claim`; причины skip перечислены по итоговым логам (133 платформенных, 82 условия среды) |
| Л3.8 | minor | подтверждена, исправлена | Правка `process.py` описана точно (три блока); ссылка `entry_lends_relay_homes` и дата 23.09.2026 возвращены в комментарии, файл по-прежнему 800 строк |
| Л3.9 | minor | подтверждена, исправлена | Раздел «Чужие правки» добавлен; подпись кодировок исправлена: UTF-8 — `utf8_mode 1`, `preferred utf-8`; cp1251 — `utf8_mode 0`, `preferred cp1251` |
| Л3.10 | minor | подтверждена, исправлена | Четыре файла (`test_alpha4_template_server_smoke`, `test_command_input_binding_version`, `test_command_run_routes`, `test_desk_wizard_roster`) включены в затронутый набор: 73 passed в обеих кодировках, итоговые числа пересчитаны |

## Проверка ведущего

Opus (ведущий), 23.10.2026 22:47–23:40 МСК, на рабочей копии, затем закоммиченной как `2ec3bca`.

- **Правка ведущего:** 7 новых файлов внесены в `CAPPED` (`tests/test_command_line_cap.py`, 187
  passed); других правок кода нет.
- **Полный core** (656 файлов в 7 параллельных процессах; 10 AppContainer-файлов отдельно, по файлу
  на процесс; basetemp `l[uc]N` не существовали и удалены; скрипт и логи —
  `Documents\Codex\work\lead-i2b\`): UTF-8 (`utf8_mode 1`) — 18420 passed, 409 skipped, 0 failed;
  cp1251 (`utf8_mode 0`, preferred cp1251) — 18420 passed, 409 skipped, 0 failed; нативные 91 passed
  в каждой кодировке. `test_login_ownership` зелёный в обоих прогонах; красный исполнителя этим не
  закрыт (вопрос 11). `git status` по `src` и `tests` до и после прогона одинаков (за время прогона
  добавлен только документ `H5-SUB-R5-I3-TASK.md`).
- **Независимая сверка исправлений** (Opus, только чтение, workflow `wf_ed8fae5e-a15`): approve with
  notes; C2 соблюдён на dispatch, review и checker, C3 — для всех ожидаемых отказов, H5-V1-свидетели
  не ослаблены. Семь minor: f1 — при отказе выхода из boundary после внутреннего `NotStarted`
  (`claim`, `claim_standing`, `spec`) квитанция говорит `enter` (настоящий `container` снова
  проверяет владельца на выходе, дублёр — нет), то есть Л1.2/Л1.3 закрыты не до конца; f2 — тест
  Л2.2(а) не отличает «все тексты» от именованных полей; f3 — параметр `[no-marker]` закрепляет
  `marker_standing` без маркера (вопрос 13); f4 — шов Р3 задачи A переехал в `_route_selected`
  (`relay_attempt.py:250-263`, вызовы `headless_login.py:177`, `subscription_quota.py:137`,
  `relay_attempt.py:283`): override A должен входить только в env relay-попытки, не в `forced_env`;
  f5 — relay-попытка с `claim=None` запускается без маркера (в production все три дороги claim
  передают); f6 — отклонение 20 не перечисляет прямые `adapter._attempt`,
  `_hold_checker_boundary()` и чтения `_sensitive_values`/`_login_echo`; f7 — правка `CAPPED` ведущим (выше). f1, f2, f5 — в I3
  (`tasks/H5-SUB-R5-I3-TASK.md`, п. 5); f3 — вопрос 13; f4 — к задаче A.
- **Разбор отклонений и вопросов** (тот же workflow): 14 отклонений — принять, 8 (1, 5, 11, 13,
  18, 19, 20) — с условиями; вопросы 6, 8, 11, 12, 13 — решение Codex. Для B: **D13 — препятствие**:
  runbook B (п. 1) требует нативного свидетеля подписочной дороги Claude для planning/review, do и
  checker, а транспорт доказан только на дублёре boundary; первый сбой запуска в настоящем
  AppContainer снимет loan как недоказанный (вопрос 12) — owner и login lease до перезагрузки ОС.
  Варианты на решение Codex: **A2 (рекомендация)** — нативный файл, один на процесс, обе кодировки:
  настоящий `claude.exe` 2.1.239 из защищённого корня, поддельный вход в tmp
  `…\DecemberCommand\logins\x`, без inference, через публичные dispatch/review/checker; проверяет
  запуск в AppContainer, HOME = relay, отсутствие refresh, discard, чистую lease; **A1** —
  самодостаточный fake внутри install-папки (дороже); **Б** — первая попытка B как свидетель, шаги
  восстановления в runbook (I3 их добавит в любом случае).
- **Поправка формулировки вопроса 11:** «причина измерена и от кода не зависит» заменено (в «Итоге»)
  на измеренное: разброс старта 1–17 с на обоих деревьях, причина не установлена.

## Ревью Codex: решения приняты с условиями, 26.10.2026

Независимое чтение кода `2ec3bca`, отчёта `aa23a03` и задания I3 `758a159`:
`H5-SUB-R5-I2B-DECISION-REPORT.md`. Там решения по всем 22 отклонениям, Q6/Q8/Q11–Q13,
D13 и Р7–Р10; они заменяют ожидание решения выше. Подробные условия не сокращать до «approved».
I2b принят как основа продолжения, не как доказанный живой путь. f1/f2/f5 остаются в I3;
Q11/Q13 — в CLOSE-TASK после сохранения текущего I3. A2 проверяет native launch/lifecycle,
первый B — подписочную дорогу целиком. Q10 и дополнительные alpha-ограничения названы отдельно.
Тесты, CLI вендоров и настоящие auth-файлы Codex при этом ревью не запускал/не читал.

## Передача

- Итоговый commit кода и тестов: `2ec3bca` (ведущий). Статус по шкале: локально проверено в обеих
  кодировках, полный core ведущего зелёный. Не проверено CI; решения ревью Codex условные, живой цикл не
  выполнялся. Ревью Opus учтено: 16 находок исправлены, 2 частично; остаток — в I3.
- `CAPPED`: 7 новых файлов внесены ведущим тем же коммитом `2ec3bca`:

```
src/conductor/command/adapters/relay_attempt.py
tests/relay_roads.py
tests/_fakehome.py
tests/test_relay_road_success.py
tests/test_relay_road_refusals.py
tests/test_relay_road_lifecycle.py
tests/test_relay_road_words.py
```

  Изменённые файлы из `CAPPED` (`harness_attempt.py`, `_fakeboundary.py`,
  `test_adapter_boundary_launch.py`, `test_execution_boundary_refusal.py`,
  `test_production_door_boundary.py`, `test_subscription_road_boundary.py`,
  `test_relay_home_native.py`) проходят предел строки в добавленных строках (`limits.py`). Размеры:
  `relay_attempt.py` 410, `harness_attempt.py` 536, `headless_cli.py` 663, `artifact_transport.py`
  787, `login_relay.py` 751, `process.py` 800 строк, самый длинный тест —
  `test_relay_road_refusals.py` 748.
- `git status --short` в конце: 24 `M` (15 файлов `src`, 9 файлов `tests`; в сравнении с первой
  итерацией добавился `subscription_quota.py`) и 8 `??` (`relay_attempt.py`, `tests/relay_roads.py`,
  `tests/_fakehome.py`, четыре `tests/test_relay_road_*.py` и этот отчёт). Чужих правок нет.
- Что осталось для I3 (я этого не делал и не менял):
  - тексты H5-V1: `harness_attempt.py` (docstring дорог), `harness_profile.py`
    (`subscription_boundary_detail`, строки 77–88), `failure_reasons.py` (слова «a subscription
    login does not run tasks inside the execution boundary in this version»), `process_boundary.py`
    (36–44, 48–56, 90–97), `process_loans.py` (29–33), `codex_cli.py` (`_login` и
    `_read_attempt_home`: «the attempt home is still minted»), `provider_setup.py` (357–361),
    `desk-wizard-copy.js` (420–428), `desk-wizard-prepare-view.js` (16–18), `studio-agents-copy.js`
    (196–199), `studio-people.js` (82–88), `isolation_facts.py` (143–148, строка про relay); для
    Grok и Kimi: «вход по подписке для этого harness внутри изоляции пока не поддержан»;
  - UI: закрытый факт `task_road` в строке провайдера (`registry.execution_boundary(id,
    "dispatch")`), тексты Agents и Desk по паре (`auth`, `task_road`); мастер `conduct providers` по
    `profile.login_relay is not None`; текст про расположение login-home (вопрос 2); текст про
    исчезнувший pinned-файл (вопрос 12);
  - документы владельца: `first-run-v1*.md`, `README*.md`, `owner-acceptance*.md`,
    `release-smoke.md`, `R5-REHEARSAL-RUNBOOK.md` (реальные пути, подписочный вход, `conduct
    providers` при остановленном сервере, новая сборка, точные действия в UI);
  - живое: M2 Claude и Codex на продуктовом пути с relay (по решению H5-A — Codex 0.164.0), нативный
    сквозной свидетель транспорта, свежий CI;
  - решение по вопросам 1, 5, 6, 9, 10, 11, 12, 13 выше.
- Временные файлы вне репозитория: `Documents\Codex\work\i2b2\` (скрипты, логи, `mutants4*.json`,
  `red\` — копия старого `src` с итоговыми тестами для красной фазы) и `Documents\Codex\work\i2b\`
  первой итерации оставлены; копии мутантов `i2b2-mut*`, `i2b2\newcopy` и мои basetemp в
  `C:\Users\Пользователь` удалены. Пробы ревью и мои пробы — в scratchpad сессии
  (`probe_missing.py`, `probe_spawn_time.py`, `probe_phases.py`), в репозиторий не входят. Под
  `Path.home()` ничего не создавалось: пути тестов в `tmp_path`; проверено после прогонов:
  `~\DecemberCommand\relay` и `~\.december-command` нет, `~\DecemberCommand\logins` — настоящие
  входы владельца, времена изменения прежние (23.10, 13:12, 13:18, 13:36), содержимое не читал.
- Следующий конкретный шаг: I3 по `tasks/H5-SUB-R5-I3-TASK.md`; Codex — ревью `2ec3bca`, 22
  отклонения, вопросы 6, 8, 11–13 и вариант нативного свидетеля для B (D13).
