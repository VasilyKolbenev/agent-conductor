Итог: локально проверено (UTF-8 и cp1251) | код `bc61db8`, тест hub `d59cd70` | итоговый полный
core на `bc61db8`: UTF-8 18620 passed, 1 failed (hub, причина установлена, исправлено `d59cd70`),
cp1251 18621 passed, 0 failed, нативные 91 × 2; A2 на настоящем `claude.exe`: 20 passed × 2, 4
запуска | 8 отклонений ждут Codex | Р7/Р8 выполнены, раздел ведущего в конце | свежий вход и B.

Исполнитель (до коммита): основа HEAD `6cc2f45` (затем `05ded5d`, только документы) | целевые Q13 +
Q11 (12 файлов и `test_login_ownership.py`): 571 passed, 0 failed в UTF-8 и 571 passed, 0 failed в
cp1251 | A2 только на подставном exe: 20 passed, 0 failed в обеих кодировках, 2 запуска на процесс;
настоящий `claude.exe` НЕ запускался и A2 на нём НЕ выполнен | красная фаза Q13 3 failed, 3 passed |
мутанты: 22 красных, 0 выжили (плюс 4 контроля нагрузки проверок) | ревью Opus: 15 находок, 9 тем,
8 исправлены (одна частично), 1 вынесена ведущему | отклонения: 7 (1 утверждено Codex, 6 ждут
ведущего) | следующий шаг: commit ведущего (новый тест в `CAPPED`), Р7/Р8, затем A2 на настоящем
exe по «Передаче».

# Отчёт по задаче: H5-SUB-R5-I2B-CLOSE (Q13, Q11, D13 A2)

- Исполнитель: Claude Code / Sonnet 5.5 (`claude-sonnet-5-5`) по заданию ведущего, вторая итерация
  (исправление находок двух ревью Opus). Не коммитил, `CAPPED` не трогал, ничего не пушил, живых CLI
  и сеть не запускал. Настоящие `%USERPROFILE%\DecemberCommand\{logins,h5-a}` не читал. Настоящий
  `claude.exe` не запускал и не хешировал; у его папки установки читал метаданные DACL (`Get-Acl`:
  корень `harnesses`, папка версии, файл). Одно нарушение «не читать содержимое»: в проверочном
  скрипте переменная цикла `$p` перекрыла путь отчёта, и `Get-Content` один раз прочитал байты
  настоящего `claude.exe` как текст; выведены только длины строк (числа), ничего не сохранено, не
  запущено и не изменено. Переменная в командах ниже переименована в `$path`.
- Исходный commit и ветка: `recovery/2026-10-20`, HEAD `6cc2f45` (I3). К концу работы HEAD `05ded5d`
  (docs-коммит другого исполнителя); `git diff 6cc2f45 05ded5d -- src tests pyproject.toml` пуст.
  Задание — `H5-SUB-R5-I2B-CLOSE-TASK.md` §2 (Q13), §3 (Q11), §5 (D13 A2); решения — разделы Q11,
  Q13, D13 в `H5-SUB-R5-I2B-DECISION-REPORT.md` (commit `f6dbd65`, прочитаны целиком). §4 (Р7/Р8)
  и §6 делает ведущий.
- Состояние рабочей копии до этой итерации: 7 файлов ` M` и 2 `??` (список в «Передаче»), все мои.
- Цель: (Q13) checker, которому не удалось взять claim и у которого нет marker, говорит об этом
  правду, а не «marker уже есть»; (Q11) тест общей lease проверяет отношение владения, а не время
  старта процесса; (D13) один native-файл A2: запуск и освобождение ресурсов настоящего защищённого
  `claude.exe --version` в режимах boundary dispatch и review на синтетическом входе.

## Чужие правки

В этой итерации новых чужих правок нет. В первой итерации появились правки другого исполнителя:
`README.md`, `README.ru.md`, `docs/first-run-v1.md`, `docs/first-run-v1.en.md`,
`docs/owner-acceptance.md`, `docs/owner-acceptance.ru.md`,
`docs/recovery/2026-10-20/R5-CLAUDE-B-RUNBOOK.md`, `tasks/H5-SUB-R5-I3-REPORT.md` (не
отслеживался). Я их не читал для правки, не менял и не откатывал; они закоммичены в `05ded5d`
(«docs(h5): owner path after I3 …», автор Vasily Darsky, 26.10 16:59); `docs/release-smoke.md` не
менялся. Мои изменения — только список «Изменения».

## Изменения

| Файл | Что |
| --- | --- |
| `src/conductor/command/adapters/independent_check.py` | `claim_refused` в закрытом `REASONS` |
| `src/conductor/command/adapters/independent_transport.py` | `RelayNotStarted`: `claim` → `claim_refused`, `claim_standing` → `marker_standing`, остальное по-прежнему `login_not_ready`; комментарий |
| `src/conductor/command/verify_holds.py` | `CHECKER_CLAIM_REFUSED` = «the checker could not reserve its check, so nothing was started» |
| `src/conductor/command/verify_road.py` | `("error", "claim_refused")` в `CHECK_REASONS` |
| `tests/test_relay_road_refusals.py` | тест checker-claim с четырьмя случаями (782 строки); ждёт `CAPPED`-предел |
| `tests/test_relay_road_words.py` | два теста: слова двух причин и закрытое множество причин checker |
| `tests/test_login_ownership.py` | handshake и watchdog в `test_two_real_projects_share_one_resource_through_post_spawn_cleanup` |
| `tests/test_relay_claude_native.py` | НОВЫЙ: A2 (309 строк), opt-in `CONDUCT_A2_CLAUDE_EXE` |
| `docs/recovery/2026-10-20/tasks/H5-SUB-R5-I2B-CLOSE-REPORT.md` | НОВЫЙ: этот отчёт |

Новые файлы: `tests/test_relay_claude_native.py`, этот отчёт. `process.py` не менял (800 строк).
Продуктовый код во второй итерации не менялся: правки ревью — только тесты и отчёт.

### Q13

- Случаи теста (`CLAIM_NOT_TAKEN`, слова квитанции): `no-marker` → «the checker could not reserve
  its check, so nothing was started» (ключ `claim_refused`); `marker-before` (настоящий marker
  проверки стоит до checker), `marker-written` (claim упал после записи marker),
  `marker-unreadable` (marker нельзя прочитать) → «this action already claimed its independent
  checker; no second check was started» (ключ `marker_standing`).
- Для каждого: дословное предложение квитанции (у каждого ключа свои слова, различие держит
  `test_relay_road_words`, поэтому предложение определяет ключ транспорта), ровно один task-spawn
  (doer), нет evidence, lease свободна, relay-home не осталось, `verification_started` истинно для
  настоящего marker (`marker-before`, `marker-written`) и ложно для остальных.
- Закрытое множество: `CHECKER_REASONS` (23 причины) в `test_relay_road_words.py` равно
  `independent_check.REASONS`; каждая причина `CHECK_REASONS` входит в него; слова различны; обе
  причины Q13 присутствуют. Новая причина теперь требует правки теста вручную.
- Повтора и нового владения нет: `NotStarted` по-прежнему возвращается значением под lease.

### Q11

Тест остался один, имя и смысл прежние; продуктовый код не менялся.
`SETUP_DEADLINE = 60`, `RELEASE_WATCHDOG = 90` (отклонение 1). Handshake — событие `held`, которое
ставит удерживаемый `_take_back_login` внутри lease; `reached_the_held_cleanup` ждёт его до 60 с или
пока жив worker. Падение worker до handshake и недостигнутый handshake — отдельные `assert` с
текстом «precondition not met, …» (при завершённом worker без ошибки текст теперь «ended without
reaching its held post-spawn cleanup», а не «within 60 s»): не skip, не retry. Удержание до
`release.set()` родителя в `finally`. Четыре факта отдельными `assert` с сообщениями: предусловие
достигнуто; второй отказан до снятия удержания (`login_owner_busy`); его spawn не было
(`second_log` нет); второй после освобождения завершился и spawn был.

## Проверки

Окружение: `December-Command-Environment.ps1 -Quiet`, `--basetemp` —
`C:\Users\Пользователь\<4 знака>`, несуществующий, удалён после; cp1251 — после
`Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING` (в процессе `utf8_mode 0`, `locale cp1251`).
Логи — `Documents\Codex\work\close-iter2\logs\`, инструменты — `…\close-iter2\tools\`.

| Команда | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| Красная фаза Q13: `pytest test_relay_road_refusals.py test_relay_road_words.py -k "claim_cannot_be_taken or reserve_its_check or closed_set"`, байты 4 файлов `src` из `HEAD` и ИТОГОВЫЕ тесты (копия вне репозитория) | UTF-8 | 3 failed, 3 passed, 106 deselected (`[no-marker]`: `'this action ...k was started' == 'the checker ...g was started'`; слова: `'default'` вместо новых; `claim_refused` нет в `REASONS`) | падение на сравнении нового reason; три passed (`marker-*`) — поведение marker сохранено |
| Целевой пакет Q13 + Q11: `test_relay_road_refusals`, `test_relay_road_words`, `test_checker_lease_refusal`, `test_login_lease_refusal_words`, `test_command_independent_runtime`, `test_command_runtime_verify`, `test_independent_check_frame`, `test_threat_matrix`, `test_command_line_cap`, `test_adapter_boundary_roads`, `test_relay_road_leaving`, `test_independent_checker_transport`, `test_login_ownership` | UTF-8 | 571 passed, 0 failed, 0 skipped, 339 с | Q13, Q11 и соседние закрытые причины (после правок ревью) |
| то же | cp1251 | 571 passed, 0 failed, 0 skipped, 319 с | то же |
| Q11 отдельно: `pytest tests/test_login_ownership.py --durations=3` | UTF-8 / cp1251 | 9 passed (20,4 с) / 9 passed (20,8 с); тест Q11 4,30 с / 4,71 с | время теста Q11 и пакета `test_login_ownership` |
| A2 на подставном exe (сам тест без изменений): `claude.exe` — собранный `csc` заменитель, печатает `2.1.239 (Claude Code)` и свой argv, без сети и файлов; лежит в `…\close-iter2\fakeprofile\DecemberCommand\harnesses\claude-code\2.1.239\`, `USERPROFILE` процесса указывает на `fakeprofile`; после прогонов папки заменителей удалены (собираются `csc` из `tools\stub.cs` и `tools\slow.cs`) | UTF-8 / cp1251, по процессу | 20 passed / 20 passed (2 режима × 10 наблюдений), 1,07 с / 1,10 с; счётчик `CreateProcessW` (плагин вне репозитория): ровно 2 запуска exe на процесс; профилей `conduct-*` до и после 0 | механика теста: настоящие lease, relay, AppContainer, ProcessRunner; настоящий Claude не запускался |
| A2 без `CONDUCT_A2_CLAUDE_EXE` | UTF-8 | 20 skipped (не засчитано как A2) | opt-in для CI |
| A2 с `other.exe` в папке 2.1.239 / с настоящим `USERPROFILE` и exe вне него / с `test_relay_road_words.py` в том же процессе | UTF-8 | 20 failed / 20 failed / 20 failed + 45 passed чужого файла; запусков exe 0 во всех трёх | предусловие «точный pinned exe» и «один native-файл на процесс» держатся именованным отказом, не пропуском |
| A2 с зависшим заменителем (`slow.cs`, печатает версию и спит 150 с) | UTF-8 | 13 failed, 7 passed, 61,8 с; запусков 1 | при таймауте три наблюдения ребёнка красные с именем «the child did not complete (timed_out)», семь фактов освобождения dispatch остались отдельными зелёными (вход, relay-home, DACL, журнал, профиль в системе, токены, lease); review не стартовал |
| Предусловия команд A2 (`check-a2.ps1`, только `Get-Acl`) | — | настоящая цепочка `harnesses` → 2.1.239 → `claude.exe`: `protected chain OK`; заменитель в `Documents\Codex\work`: стоп «S-1-5-21-…-1002 may write»; чужой sha256: стоп; нет файла: стоп; `Documents` как корень: стоп «not protected» | команды ведущего ловят незащищённую установку до запуска |
| `hygiene.py` по 9 изменённым файлам | — | строки ≤ 100 (в добавленных), файл ≤ 800 (refusals 782, native 309), без хвостовых пробелов, CR, BOM, один `\n` в конце | лимиты задания |

Первая итерация: первый UTF-8 прогон пакета Q13 дал 545 passed, 1 failed: моя строка 101 знак в
`CAPPED`-файле `test_relay_road_refusals.py` (`test_command_line_cap`); исправлена.
Полный core не запускался (делает ведущий). Linux и macOS не проверялись.

## Красная фаза Q11 (старый красный и новый результат)

- Старый красный (I2b): cp1251, `assert entered.wait(8), errors`, `errors == []`; повторы в I2b —
  4 красных из 30, причина разброса не установлена. Тот красный я не воспроизводил самопроизвольно.
- Контролируемое подтверждение окна на копии (замер первой итерации): первый spawn замедлен на 10 с
  (`time.sleep(10)` в `_owned_attempt`). Старый тест (`HEAD`): 1 failed, `AssertionError: []`
  на `entered.wait(8)`, 13,7 с. Новый тест: 1 passed, 34 с. Это показывает дефект предусловия, а не
  причину задержки ОС; гипотезу об антивирусе не выдвигаю.
- Красная фаза A2: не применимо, потому что продукт этим заданием не менялся, а A2 новый файл.
  Доказательство, что наблюдения не пустые, — мутанты A2-a…A2-m ниже.

## Мутанты

Копия `src`, `tests`, `pyproject.toml` в `Documents\Codex\work\close-mut`, `PYTHONPATH` на её `src`,
`conductor.__file__` из копии; M0 без правок зелёные (Q13 7 passed, Q11 1 passed, A2 20 passed при
2 запусках); после каждого мутанта файл возвращён и SHA-256 совпал (`restored=True` во всех
строках). A2-мутанты идут на заменителе в `fakeprofile`; «запусков» — число `CreateProcessW` с
`claude.exe`; оставленные мутантом профили AppContainer удалены `DeleteAppContainerProfile` через
`_winlaunch.delete_profile` (до прогонов их было 0, после 0). Скрипты и журналы —
`Documents\Codex\work\close-iter2\{tools,logs}`; копия `close-mut` удалена в конце.

| Мутант | Результат | Что красное |
| --- | --- | --- |
| Q13-a снова смешивает `claim` и `claim_standing` в `marker_standing` | 1 failed, 6 passed | refusals `[no-marker]`: предложение квитанции |
| Q13-b меняет причины местами | 3 failed | refusals `[no-marker]`, `[marker-written]`, `[marker-unreadable]` |
| Q13-c `CHECKER_CLAIM_REFUSED` говорит слова marker | 3 failed | refusals `[no-marker]`, words: слова и закрытое множество (дубль слов) |
| Q13-d runtime сопоставляет `claim_refused` словам marker | 3 failed | те же три |
| Q13-e нечитаемый marker считается отсутствующим (`Claim.stands`) | 2 failed | refusals `[marker-unreadable]` и прежний тест doer про нечитаемый marker |
| Q13-f `claim_refused` убран из `REASONS` | 2 failed | words: `ValueError: unknown independent-check reason`, равенство `REASONS` |
| Q13-g у `claim_refused` нет слов в `CHECK_REASONS` | 3 failed | refusals `[no-marker]` (общее «adapter verification was error»), words ×2 |
| Q13-h marker, стоящий до checker, назван `claim_refused` | 1 failed | refusals `[marker-before]` (теперь с настоящим marker) |
| Q11-a lease отпускается до попытки (`owned_login_attempt`) | 1 failed | «the second was not refused while held» |
| Q11-b тест сам отпускает удержание сразу после handshake | 1 failed | «the second was not refused while held» |
| Q11-c handshake не ставится | 1 failed, 62 с | «precondition not met, the first attempt did not reach its held post-spawn cleanup within 60 s» |
| Q11-d первая попытка падает до cleanup | 1 failed, 2 с | «precondition not met, the first attempt failed before its cleanup» (`OwnershipError login_recovery_required`) |
| A2-a relay home не удаляется | 11 failed, 9 passed; запусков 1 | «the relay home is there» (dispatch); review не стартовал: 10 отказов «earlier observation is red» |
| A2-b `CLAUDE_CONFIG_DIR` = login-home | 12 failed; запусков 1 | «was told the new relay home», «relay home is gone»; review не стартовал |
| A2-c1 токен остаётся активным, защита продукта включена | 17 failed, 3 passed; запусков 1; профиль остался (удалён) | «the launch is lost or unknown, not repeated: ClaudeCodeError (ProfileRefused: profile_acl_unproven …)» и отдельные факты: DACL install, журнал, профиль в системе, токен |
| A2-c2 токен остаётся, защита продукта убрана | 11 failed; запусков 1 | `test_the_runner_holds_no_child_token` (`active_tokens()` не пуст) |
| A2-d DACL не возвращаются (`loans.restore()` пропущен) | 12 failed; запусков 1 | «the DACL of install changed» и журнал не `retired` |
| A2-e синтетический вход меняется | 11 failed; запусков 1 | «byte for byte»: digests до и после различаются |
| A2-f профиль не удаляется из ОС, журнал пишет `retired` (мутант R3 ревью) | 11 failed; запусков 1; профиль остался (удалён) | «the profile mapping is still there» (новое наблюдение); все прежние наблюдения dispatch зелёные |
| A2-g профиль просит `--version -p review-mutant` (мутант R1 ревью) | 19 failed, 1 passed; запусков 0 | «A2 STOP, the pin and the version print are not what A2 starts»: до lease и профиля |
| A2-h spec, переданный runner, получает `-p` в последний момент | 14 failed, 6 passed; запусков 0 | «A2 STOP, the spec is not the bare version print: its child is not started»; lease синтетического входа после этого «uncertain», тест называет это и не чистит |
| A2-m префикс argv boundary получает `-p` | 19 failed, 1 passed; запусков 0 | предварительная проверка префиксов до lease |
| Контроль A2-i: DACL не возвращаются И остановка внутри процесса убрана | 4 failed, 16 passed; запусков 2 | красные только 4 наблюдения; второй запуск произошёл: остановка нагрузочная |
| Контроль A2-j: то же, остановка на месте | 12 failed; запусков 1 | dispatch красный → review не стартовал |
| Контроль A2-k: spec получает `-p` И последняя проверка убрана | 11 failed, 9 passed; запусков 1 | красно только после запуска ребёнка с `-p`: проверка перед запуском нагрузочная |
| Контроль A2-l: профиль не удаляется И проверка «профиль неизвестен ОС» убрана | 20 passed; запусков 2; 2 профиля остались (удалены) | выживает: до этой итерации такой мутант не ловился |
| Контраст (первая итерация): первый spawn +10 с, новый тест | 1 passed | — |
| Контраст (первая итерация): первый spawn +10 с, старый тест `HEAD` | 1 failed | `entered.wait(8)` (см. выше) |

Контроль «нет spawn» у Q13 держит `len(site.tasks()) == 1`; отдельного мутанта «checker спавнится
при `claim_refused`» не делал: он потребовал бы переписать цикл попытки.
Наблюдение без изменения: при Q13-f (`claim_refused` убран из `REASONS`) интеграционный случай
`[no-marker]` может остаться зелёным, потому что runtime не сверяет причину транспорта с `REASONS`;
закрытое множество держат тесты слов (они красные). Так было и до этих правок.

## A2: что и как

- Файл `tests/test_relay_claude_native.py`, один процесс — один файл; без `CONDUCT_A2_CLAUDE_EXE`
  весь модуль skip (пропуск не засчитывается). Переменная обязана быть ТОЧНЫМ путём
  `%USERPROFILE%\DecemberCommand\harnesses\claude-code\2.1.239\claude.exe` (имя файла и каталог
  сравниваются целиком), файл существует, в процессе нет другого тестового файла и все прежние
  наблюдения зелёные; иначе наблюдение failed с именем «A2 STOP …», spawn нет. Что точный путь
  защищён и что это тот exe, тест не доказывает: это проверяют команды ведущего (sha256 против
  manifest Р7 и DACL цепочки, см. «Передачу»).
- Установка и вход: настоящий путь из переменной; синтетический login-home
  `<tmp>\DecemberCommand\logins\x` (`tests/relay_credentials.py`, срок жизни токена от
  настоящих часов + 4 ч); активированный проект в `<tmp>`; транспорт строится настоящей дверью
  `resolve_providers(..., confine_platform="win32")` с `auth="subscription"`, настоящим
  `ProcessRunner`. Конфигурация: `env_allow = ("SystemRoot", "windir")`; runner видит ещё
  `USERPROFILE` (для проверки установки внутри профиля), ребёнок его не получает.
- Ход (на каждый режим): до lease проверяется, что `profile.version_argv == ("--version",)` и оба
  префикса argv равны `(<claude.exe>,)`; затем `adapter._relay_start(mode)`,
  `adapter._relay_preflight(request)`, `adapter._attempt(profile.version_argv,
  work_route("work-001"), mode=…, claim=_claim_of(request), timeout=60, separate_stderr=True)`. Это
  настоящие lease, mint, copy-in, ready, boundary entry, claim, run, read-back, discard; логика
  окружения и spec не переписана (`attempt_spec`, `confined_spec`). Обёртка `runner.run` в последний
  момент отказывает любому spec, у которого argv не ровно `(<claude.exe>, "--version")` или есть
  stdin: ребёнок не стартует. Второй режим стартует, только если всё до него зелёное. Версию и
  статус входа (два дополнительных spawn) A2 не спрашивает: бюджет 4 запуска — это ровно
  `claude.exe --version` × 2 режима × 2 кодировки.
- Наблюдения (десять тестов на режим, по отдельности): завершён, exit 0, stdout содержит
  `2.1.239 (Claude Code)`, stdin не передавался, значений окружения в выводе нет; argv ровно
  `(<claude.exe>, "--version")`, boundary — `WindowsContainer` с тем же SID, нет stdin и prompt,
  timeout 60, boundary введён для этого режима; `CLAUDE_CONFIG_DIR` — новый relay-home
  (`c-<16 hex>` в папке ключа проекта, не login-home), `TEMP`/`TMP`/`LOCALAPPDATA` — runtime
  попытки; синтетический вход побайтно прежний; relay-home удалён (проверяется и по папке ключа, а
  не только по spec), `_retained == _login_residue == 0`; DACL relay, login, logins, install, work
  как были и профиль не назван (`icacls`); профиль, ACL-запись и loan в журнале `retired`; профиль
  отсутствует в ОС (`_winlaunch.inspect_profile(sid) is None`, точное сопоставление SID);
  `runner.active_tokens()` пуст; owner и login lease берутся снова, `active.json` нет и есть
  `closed-*.json`. Факты освобождения (вход, relay-home, DACL, журнал, профиль, токены) не требуют,
  чтобы ребёнок завершился: при таймауте или потерянном запуске они остаются отдельными
  наблюдениями. Таймаут, неизвестный исход, `RelayNotStarted`, потерянный запуск — failed с именем
  «A2 STOP …» и без повтора; lease вручную не чистится.
- Что A2 не показывает: что CLI читал credential (spec говорит, что ему сказали, а не что он
  сделал), подписку, отсутствие refresh во время задачи, модель, prompt, checker, публичную дорогу
  транспорта. Это первый B.

## Отклонения

| Что | Почему | Кто утвердил |
| --- | --- | --- |
| 1. Q11: ограничители 60 с (setup) и 90 с (release) вместо 8 с и 15 с | замер I2b: время старта fake-ребёнка 1–17 с, причина не установлена; это hang-guard, не SLA и не retry | Codex, `H5-SUB-R5-I2B-DECISION-REPORT.md` Q11, 26.10.2026 |
| 2. A2 вызывает приватные швы транспорта (`_relay_start`, `_relay_preflight`, `_claim_of`, `_attempt`, `_argv_prefix`, `_boundary_prefix`), а не публичную дорогу | у публичных dispatch и review в argv inference; CLOSE-TASK §5 требует существующие функции и один `--version` | ждёт ведущего |
| 3. Сверх задания: случай `marker-before` у Q13; у A2 наблюдения «профиль, ACL и loan `retired` в журнале» и «профиль неизвестен ОС» | первый закрывает «защита от повтора при marker прежняя»; два других — «временные разрешения и профиль сняты» независимо от записи самого продукта | ждёт ведущего |
| 4. A2 строит свой `Site` вместо существующего `RelaySite` (`tests/test_relay_home_native.py:54`) и подменяет `process_loans.configured_login_homes` | `RelaySite` готовит relay-home руками, тогда mint, copy-in и discard продукта не проверялись бы; A2 берёт из существующего `snapshot_of`, `entries_naming`, `same_acl`, `relay_credentials` и тот же патч `configured_login_homes`, что `run_child`; CLOSE-TASK §5 велит «использовать существующий native relay fixture» | ждёт ведущего |
| 5. A2 оборачивает `runner.container_profile` (запись входа, SID, путей) и `runner.run` (запись spec и отказ любому spec, кроме `--version` без stdin) | запись нужна для наблюдений и для причин остановки; отказ — защита бюджета «ноль inference»; для допустимого spec поведение не заменено | ждёт ведущего |
| 6. Q13: подмены на границе рабочей папки: `HarnessWorkspace.claim_verification` заменён отказывающей функцией (OSError «диск полон» иначе не вызвать), `is_verification_claimed` бросает (нечитаемый marker), `HarnessWorkspace.claim` обёрнут для `marker-before`: он дополнительно пишет настоящий marker проверки настоящим `claim_verification` | граница — файловые операции workspace, как у соседних тестов этого файла (`_raising`, `monkeypatch` `HarnessWorkspace`); приватный шпион на `IndependentCheckTransport._checker_answer` убран: он не нёс нагрузки | ждёт ведущего |
| 7. Сужение: переменная A2 — только точный путь под настоящим `USERPROFILE`, прежде допускалась любая папка с именами `harnesses/claude-code/2.1.239` | находки ревью: форма пути не доказывает «protected CLI»; точность и защита дополнительно проверяются командами ведущего | ждёт ведущего |

| 8. Q11: принятая вторая попытка (новый интерпретатор и настоящий spawn) — предел 60 с вместо 20 с `child()` (правка ведущего) | тот же замер I2b: spawn 1–17 с; ревью подтвердили риск по коду; это hang-guard, не SLA | ждёт Codex |

До утверждения статус не выше «локально проверено».

## Ревью Opus

Два ревью (контракт и нативный запуск; доказательность и стандарт), 15 находок (3 major, 12 minor);
многие совпадают между ревью, итого 9 тем. Каждую проверил сам (код и измерение на заменителе).
Ссылки: Р1/Р2 — ревью, номер — порядок находки.

| Тема (находки) | Статус | Проверка и действие |
| --- | --- | --- |
| 1. Остановка A2 внутри процесса: review стартовал при красном dispatch (Р1-1, major) | подтверждена, исправлена | по коду фикстура не смотрела результаты; в фикстуру `observed` до `Site(...)` добавлено: красное наблюдение раньше (`request.session.testsfailed`) → «A2 STOP … not started», запуска нет. Порядок сбора: 10 наблюдений dispatch, затем 10 review (`--collect-only`). Мутанты: A2-j (остановка на месте) запусков 1, контроль A2-i (остановка убрана) запусков 2 |
| 2. Факты освобождения привязаны к завершению ребёнка (Р1-2) | подтверждена, исправлена | по коду `completed()` требовала завершения; введено `attempted(seen)` (сайт и снимок «до» есть); relay-home проверяется по папке ключа; `naming` и журнал читаются без падения при отсутствии профиля. Измерено на зависшем заменителе: 13 failed, 7 passed, запуск 1: три наблюдения ребёнка красные, семь фактов освобождения dispatch зелёные по отдельности |
| 3. argv и stdin проверялись только после запуска (Р1-3, Р2-2 major) | подтверждена, исправлена | по коду сверка `spec.argv` шла после `real_run`; ревью измерило запуск с `-p`. Теперь: до lease проверяются `version_argv` и оба префикса; в обёртке `runner.run` spec с другим argv или с stdin отвергается до запуска. Мутанты: A2-g, A2-m (до lease) и A2-h (в последний момент) — запусков 0; контроль A2-k (последняя проверка убрана) — ребёнок запущен с `-p`, красное только после |
| 4. «Точный protected CLI» проверялся по форме пути (Р1-4, Р2-3) | подтверждена, исправлена частично | воспроизвёл: `other.exe` и exe вне защищённого корня проходили. Теперь точный путь `%USERPROFILE%\DecemberCommand\harnesses\claude-code\2.1.239\claude.exe`; контроли `other.exe`, чужой `USERPROFILE`: 20 failed, запусков 0. Защищённость и sha256 тест не может установить; команды ведущего проверяют их до pytest (`check-a2.ps1` проверен: настоящая цепочка `OK`, незащищённая и с чужим sha256 — стоп). Утвердить сужение (отклонение 7) |
| 5. `CONDUCT_A2_CLAUDE_EXE` остаётся в оболочке; полный core мог бы запустить A2 ещё дважды; вывод не сохраняется (Р1-5, Р2-6) | подтверждена, исправлена | по коду модуль включается только переменной, `testpaths = ["tests"]`. В тест добавлен отказ, если в процессе больше одного тестового файла (контроль с `test_relay_road_words.py`: 20 failed, запусков 0); команды ведущего завершаются `finally` (переменная и basetemp), пишут лог в `work\close-a2` и идут отдельным процессом после core |
| 6. Снятие профиля доказано только фазой в журнале продукта (Р1-6, Р2-1 major) | подтверждена, исправлена | свой мутант A2-l (профиль не удаляется, проверки нет): 20 passed, 2 профиля остались в реестре. Добавлено наблюдение `inspect_profile(sid) is None` (точное сопоставление SID). Мутант A2-f (без удаления): красный, «the profile mapping is still there»; остальные факты dispatch зелёные |
| 7. Таймаут `child()` 20 с в `test_login_ownership.py` ограничивает второй процесс с настоящим spawn (Р1-7, Р2-7) | подтверждена как риск, НЕ исправлена; вопрос ведущему | вне разрешённых Q11 пределов 60/90; красного не наблюдалось: Q11 зелёный в обеих кодировках (тест Q11 4,3 с в UTF-8 и 4,7 с в cp1251; весь файл 9 passed в обеих). Решение ведущего или Codex: поднять `child()` до 60 с с тем же основанием (spawn 1–17 с) или оставить с записью риска. Сделано только мелкое: сообщение предусловия различает «worker жив, 60 с» и «worker завершился без handshake» |
| 8. Не записаны отклонения: свой `Site` вместо `RelaySite`; подмены не на границе; marker-before подменой (Р1-8, Р2-4) | подтверждена, исправлена | отклонения 4, 5, 6 в таблице. Шпион на приватном `_checker_answer` убран (мутанты Q13-a…d остались красными по предложению квитанции). `marker-before` построен настоящим marker (`claim_verification` из `claim` doer): `verification_started` для него истинно, а не ложно |
| 9. Красная фаза записана на более ранней версии теста; для A2 нет строки «не применимо» (Р2-5) | подтверждена, исправлена | на байтах `HEAD` четырёх файлов `src` и итоговых тестах: 3 failed, 3 passed (раньше 3 failed, 2 passed); строка про A2 добавлена в «Красная фаза Q11» |

Не менялось: наблюдение Р2 про Q13-f (описано под таблицей мутантов), Q11 и Q13 по существу ревьюеры
подтвердили. Повторены: Q13/Q11 мутанты, A2 мутанты, целевой пакет и A2 в обеих кодировках.

## Не проверено

- Настоящий `claude.exe`: ни разу не запущен. Что он делает при `--version` внутри AppContainer с
  этим окружением (время старта, что пишет в `CLAUDE_CONFIG_DIR`, `TEMP`), неизвестно; механика
  проверена только на заменителях (`tar.exe` в первой итерации, собранный заменитель во второй).
  Заменитель — крошечная программа .NET: время старта и права у настоящего Claude Code могут
  отличаться.
- Подписка, чтение токена CLI, отсутствие refresh, модель, checker, цикл — первый B.
- Полный core на финальном коммите и CI — ведущий. Linux и macOS не проверялись.
- Не закрыты (из DECISION-REPORT, этим заданием не выполнялись): Q10 (`_login_echo` на всех
  дорогах, свидетель с испорченным credential), Q6 (сохранение `Ready.account` в доказательствах
  продукта), Q8 (закреплённый набор ключей `oauthAccount` и общий контракт окружения F10),
  H5-INSTALL-PREFLIGHT, Р9 и Р10 (A-I1), Q12 (остаётся fail-closed). Все они — до передачи альфы
  другим пользователям.

## Открытые вопросы

1. `child()` в `test_login_ownership.py` ограничен 20 с и охватывает старт второго процесса и его
   spawn после освобождения (тема 7 ревью): оставить с записью риска или поднять до 60 с.
2. `env_allow` A2 (`SystemRoot`, `windir`) — минимум для запуска контейнера на заменителе; для
   настоящего exe он не измерен. Он не обязан совпадать с `env_allow` и forced-env конфигурации B
   (Q8): их ведущий фиксирует отдельно.
3. Старый тест переименован (`…_and_says_a_marker_stands` → `…_names_what_is_true`): ссылки в
   документах ведущий обновляет сам.
4. Статус A2 в документах: «выполнен» — только после запуска на настоящем exe; прогоны на
   заменителях в «Проверках» A2 не считать.
5. После отказа `runner.run` до запуска (мутант A2-h) lease синтетического входа остаётся
   «uncertain» (продукт считает, что запуск мог состояться): для A2 это синтетический вход во
   временной папке, для B такой отказ означал бы восстановление по runbook.

## Ревью Codex: ожидает

## Передача

- Итоговый commit: не создан. Ведущему: код и тесты одним коммитом (`src`: 4 файла; `tests`: 3
  изменённых и 1 новый), документы — отдельным.
- Файлы для `CAPPED` (`tests/test_command_line_cap.py`), не внесено; новый файл один:
  `    "tests/test_relay_claude_native.py",`
- `git status --short` на конец работы: ` M` четыре файла `src/conductor/command/…`
  (`adapters/independent_check.py`, `adapters/independent_transport.py`, `verify_holds.py`,
  `verify_road.py`), ` M tests/test_login_ownership.py`, ` M tests/test_relay_road_refusals.py`,
  ` M tests/test_relay_road_words.py`, `?? tests/test_relay_claude_native.py` и этот отчёт.
- Обновлённые документы: только этот отчёт; `OPEN-DECISIONS.md` и общие документы не менялись.
- Команды A2 для ведущего: два процесса PowerShell (UTF-8, затем cp1251), не в том окне, где идёт
  полный core, и после него. В каждом ровно один запуск pytest по одному файлу: 2 запуска claude.exe
  (dispatch, review); всего 4. Повторов нет; при красном — стоп, записать «A2 STOP» и
  восстановление, второй процесс не запускать, B не начинать. Предусловия (путь, sha256, DACL)
  проверяются до pytest и ничего не запускают:

```powershell
# процесс 1: UTF-8 ($Tag = 'u8'). Процесс 2: новое окно, те же строки с $Tag = 'c1', и сразу
# после окружения: Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING
. (Join-Path $env:USERPROFILE 'Documents\Codex\2026-10-20\new-chat\outputs\December-Command-Environment.ps1') -Quiet
$WT  = '<корень проверяемого дерева: финальный коммит>'
$Tag = 'u8'
$Sha = '<sha256 claude.exe из защищённого manifest Р7>'
$Root = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses'
$Exe  = Join-Path $Root 'claude-code\2.1.239\claude.exe'
$Out  = Join-Path $env:USERPROFILE 'Documents\Codex\work\close-a2'
New-Item -ItemType Directory -Force $Out | Out-Null

# 1. Предусловия: файл, sha256, защищённая цепочка (Get-Acl, Get-FileHash; exe не запускается).
$sid = [Security.Principal.SecurityIdentifier]
$me = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$ok = @($me, 'S-1-5-18', 'S-1-5-32-544')
$w = 0x2 -bor 0x4 -bor 0x10 -bor 0x40 -bor 0x100 -bor 0x10000 -bor 0x40000 -bor 0x80000
$w = $w -bor 0x10000000 -bor 0x40000000
if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) { throw 'A2 STOP: claude.exe is not there' }
$hash = (Get-FileHash -LiteralPath $Exe -Algorithm SHA256).Hash
if ($hash -ne $Sha) { throw 'A2 STOP: sha256 differs from the manifest' }
foreach ($path in @($Root, (Split-Path $Exe -Parent), $Exe)) {
    $acl = Get-Acl -LiteralPath $path
    if ($acl.GetOwner($sid).Value -notin $ok) { throw "A2 STOP: owner of $path" }
    foreach ($r in $acl.Access) {
        $who = $r.IdentityReference.Translate($sid).Value
        $writes = [int]$r.FileSystemRights -band $w
        if ($r.AccessControlType -eq 'Allow' -and $who -notin $ok -and $writes) {
            throw "A2 STOP: $who may write $path"
        }
    }
}
if (-not (Get-Acl -LiteralPath $Root).AreAccessRulesProtected) {
    throw 'A2 STOP: harnesses root DACL is not protected'
}

# 2. Единственный запуск: переменная живёт только внутри try, basetemp не существует и удаляется.
Set-Location $WT
$env:PYTHONPATH = Join-Path $WT 'src'
python -c "import conductor; print(conductor.__file__)"   # должно быть в $WT\src
$bt = Join-Path $env:USERPROFILE "a2$Tag"
if (Test-Path $bt) { throw 'basetemp exists' }
$env:CONDUCT_A2_CLAUDE_EXE = $Exe
try {
    python -m pytest tests/test_relay_claude_native.py --basetemp=$bt -q -p no:cacheprovider -rs |
        Tee-Object -FilePath (Join-Path $Out "a2-$Tag.log")
} finally {
    Remove-Item Env:CONDUCT_A2_CLAUDE_EXE -ErrorAction SilentlyContinue
    if (Test-Path $bt) { Remove-Item -Recurse -Force $bt }
}
```

  Ожидаемо в каждом процессе: `20 passed`, 0 skipped (пропуск — не пройденный A2). Не запускать
  параллельно другие native-файлы, не использовать `-k`. Проверка кода предусловий (тот же
  контроль в `close-iter2\tools\check-a2.ps1`): настоящая цепочка `harnesses` проходит (только
  метаданные DACL), заменитель в `Documents\Codex\work` — стоп.
- Следующий конкретный шаг: ведущий коммитит код, делает Р7/Р8 и запускает A2 на настоящем exe по
  командам выше; затем заполняет раздел ниже.

## Р7/Р8, A2 факт, run-ready

Ведущий Opus, 26.10.2026. Настоящие входы владельца не читались, модель не вызывалась, push нет.

- **Коммиты.** Код и тесты — `bc61db8` (четыре файла `src`, тесты Q13/Q11, новый A2-файл в
  `CAPPED`). Вопрос 1 решён ведущим: принятая вторая попытка теста Q11 (новый интерпретатор и
  настоящий spawn) получила тот же предел 60 с (`child(..., timeout=SETUP_DEADLINE)`), остальные
  вызовы `child()` — прежние 20 с; основание — тот же замер 1–17 с. Это **отклонение 8**, ждёт
  Codex.
  Исправление теста hub — `d59cd70` (ниже). Этот отчёт — docs.
- **Итоговый полный набор** (CLOSE-TASK §3) на `bc61db8` в чистом `git worktree add --detach`
  (`Documents\Codex\work\wtf`), `PYTHONPATH` = его `src`, `conductor` импортирован из worktree,
  `git status` до и после пуст; 659 файлов в 7 процессах, AppContainer-файлы по одному на процесс;
  логи `Documents\Codex\work\lead-final\`. UTF-8: 18620 passed, **1 failed**, 409 skipped; cp1251:
  18621 passed, 0 failed, 409 skipped; нативные 91 passed в каждой; A2-файл без переменной — skip.
- **Красный UTF-8** — `test_hub_operations.py::test_an_add_row_of_the_same_project_does_not_count_
  against_its_own_operation` (`project_id` None). Причина установлена: строка add показывает шаг
  `start`, как только прочитана последняя строка шага ребёнка (`hub/operations.py:377`), а проект
  записывается только с результатом (`:249`); помощник теста ждал один шаг. Задержка, вставленная
  ровно в это окно (`Documents\Codex\work\hub-race\test_repro_hub_race.py`), даёт тот же красный
  каждый раз; с исправленным помощником (ждёт шаг и `project_id`) — зелёный; файл 216 passed в обеих
  кодировках. Код hub не менялся с `2043847`, к H5 отношения нет. Полный core после `d59cd70` не
  повторялся: изменён один тестовый файл, прогон адресный.
- **Р7.** `%USERPROFILE%\DecemberCommand\product\` с защищённым DACL (SYSTEM, Administrators,
  владелец). Базовый Python — защищённая копия рантайма Codex 3.12.14 без сторонних пакетов
  (`python-3.12.14`, 782 файла, каждый сверен с источником; 45 PE Valid: OpenAI, Microsoft, PSF; в
  источнике нет чужих ACE записи). Сборка — защищённый build-venv от этой копии, hatchling 1.32.4 и
  5 зависимостей с PyPI по разрешению владельца 26.10 (sha256 сверены, `Documents\Codex\work\
  b-prep\build-backend.json`), экспорт `git archive bc61db8`, `SOURCE_DATE_EPOCH` = время коммита.
  Wheel `agent_conductor-0.1.0-py3-none-any.whl`, sha256
  `3096bb04172963c56b6305802b6f8bb61afd482f20c7227064d0cf73307bd455`; повторная сборка из того же
  экспорта дала тот же sha256. Venv `product\bc61db88995c\venv` от защищённой копии, wheel
  установлен `--no-index --no-deps`, `conductor` импортируется из его site-packages,
  `conduct --help` отвечает. Manifest `product\bc61db88995c.manifest.json`, sha256
  `815caafcebd55ae3917b57dff86ba702c9b234272c68e95b559ea852b31fcd90` (commit, wheel, build backend,
  опись базового Python и venv). `h5-a\tools\preflight.ps1 -Mode check -Product bc61db88995c`:
  0 problems (18:42 и 19:48). Случай на пробной сборке: wheel унаследовал ACE песочницы из TEMP
  скрипта окружения — TEMP всех процессов сборки и установки перенесён в защищённый
  `product\build\tmp`, пересборка дала тот же хеш; это поймал сам preflight.
- **Р8.** Защищённый `product\bc61db88995c\scratch`; runbook B ставит его в TEMP/TMP окон B для
  процессов вне boundary; task-TEMP внутри boundary по-прежнему задаёт `confined_spec`.
- **Q8 (B).** Строка `claude-code`: `env_allow` = `SYSTEMROOT WINDIR PATH TEMP TMP`; forced-env
  профиля `DISABLE_AUTOUPDATER=1`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`; ни одного из 15
  имён решения Codex в выбранном окружении нет. Digest гранта — при оформлении конфигурации B.
- **A2 (факт).** Перед запуском preflight 0 problems, посторонних процессов Python нет; скрипт
  `h5-a\tools\a2-run.ps1` (предусловия CLOSE-отчёта: путь, sha256
  `0bc1304c…0a2b`, ACL цепочки, без запуска exe), один pytest на процесс, логи
  `Documents\Codex\work\close-a2\`. Процесс 1 (UTF-8): **20 passed, 0 skipped**, 2 запуска
  `claude.exe --version` (dispatch, review). Процесс 2 (cp1251): первая попытка остановилась на
  предусловии моего скрипта — локатор `conductor.__file__` в cp1251 вернул кириллический путь
  искажённым, сравнение с worktree не прошло; pytest не запускался, запусков `claude.exe` не было,
  лог сохранён (`a2-c1-precondition-stop.log`); локатор переведён на `-X utf8` (сам pytest остался
  в cp1251), затем процесс 2: **20 passed, 0 skipped**, 2 запуска. Всего 4 запуска, повторов A2
  нет. После: профилей `conduct-*` в реестре 0, папки `DecemberCommand\relay` нет. Ограничения A2
  прежние: запуск и освобождение ресурсов, а не подписка, токен, refresh, модель, checker или цикл.
- **run-ready.** `$KIT\run-ready.json` заполняется после коммита этого отчёта: указатели и копии
  SHA; основание доверия — защищённый manifest (runbook B сверяет и останавливается).
- **Следующий шаг.** Свежий вход владельца в `%USERPROFILE%\DecemberCommand\logins\claude-code`
  (блок «Свежий вход» runbook B), затем один B Claude → Claude: 6 действий + 2 проверки, gates —
  владелец.
