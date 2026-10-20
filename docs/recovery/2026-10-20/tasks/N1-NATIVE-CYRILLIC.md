# Нативные тесты December Command на ноутбуке с профилем `C:\Users\Пользователь`: точные причины падений

## 0. Итог

- Прогнал **66** нативных и Windows-boundary файлов, по одному на процесс: **1478 passed, 17 failed, 19 errors, 98 skipped**, 794 с. Падают **6 файлов, 36 id**. Набор совпадает с R1.1 (11F/21P/10E на 5 файлах) и с R2 (3 + 8 + 4 + 10E).
- Причин две. **Дефекта продукта среди них нет.**
  - **RC1, дефект теста (27 id, 5 файлов).** Тесты пишут скрипт PowerShell для ребёнка в UTF-8 **без BOM**, и внутри скрипта есть абсолютные пути из basetemp. Windows PowerShell 5.1 читает такой `.ps1` в ANSI cp1251. Кириллица пути превращается в мусор. Байт `0x82` из «т» становится `U+201A`, а PowerShell считает его одинарной кавычкой. Литерал рвётся, получается **ParserError**, скрипт не выполняет ни одной строки, exit 1. Текст ошибки разбора по-русски и начинается с пути к скрипту. Он уходит в объединённый stdout в **OEM cp866**. Тестовый `facts()` декодирует строго как UTF-8 и падает на `0x8F` (= «П») в позиции 9. AppContainer, профиль пользователя, переменные окружения ребёнка и расположение python/.venv не участвуют: тот же сбой воспроизводится **без контейнера**.
  - **RC2, окружение (9 id, 1 файл).** Слишком длинный basetemp. Правило продукта: projects home не длиннее 60 единиц UTF-16. CI обходит это коротким basetemp. Кириллица ни при чём.
- R2 написал «окружение, не продукт». Для продукта вывод верен, но механизм назван неверно. Дело не в том, что «PowerShell в AppContainer печатает ошибку с путём профиля»: PowerShell 5.1 просто не может разобрать BOM-less UTF-8 скрипт с кириллицей.
- **Граница R5 на кириллическом профиле работает.** С BOM-фиксом на кириллическом basetemp проходят все 118 тестов пяти упавших PS-файлов. Нативная характеристика `b9fc4c3` и нативные свидетели аренды (`login_config_native`, `login_native_overlap`, `loans_native`, `login_native`) на этом ноутбуке теперь **переподтверждены**.

## 1. Окружение

| Параметр | Значение |
| --- | --- |
| ОС | Windows 11 Pro 10.0.26300, ANSI CP 1251, OEM CP 866 |
| Профиль | `C:\Users\Пользователь` |
| Python | 3.12.14, `.venv` → base `C:\Users\Пользователь\.cache\codex-runtimes\codex-primary-runtime\dependencies\python` |
| PowerShell в ребёнке | 5.1.26100.9444 (`System32\WindowsPowerShell\v1.0\powershell.exe`) |
| Консоль агента | CP 65001; `December-Command-Environment.ps1` ставит `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `TEMP=...\work\dc-temp` |
| Репозиторий | ветка `recovery/2026-10-20`. За время сессии другие агенты сделали коммиты `4ddb1fd` и `a622316`, только docs; `src` и `tests` не менялись |

## 2. Шаг 1: последовательный прогон

Команда (раннер `C:\Users\Пользователь\Documents\Codex\work\nat-diag\run_seq.py`). Для каждого файла отдельный процесс:

```
. "...\December-Command-Environment.ps1" -Quiet
python -m pytest -q -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\nat-a<n> --tb=long -rA --junitxml=<logsA>\<file>.xml tests/<file>
```

Список файлов: объединение `grep -l "os.name != .nt.|skipif.*nt|_winlaunch"` и `grep -l "_winlaunch|container_profile|WindowsContainer|AppContainer"` (55 файлов), плюс оставшиеся `test_process_*`, `test_process_identity` и `test_project_ownership_process`.

| n | файл | passed | failed | errors | skipped | с |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | test_process_login_native.py | 7 | **8** | 0 | 0 | 4.2 |
| 2 | test_process_loans_native.py | 5 | **3** | 0 | 0 | 8.8 |
| 3 | test_process_login_config_native.py | 0 | **4** | 0 | 0 | 2.1 |
| 4 | test_process_login_native_overlap.py | 0 | 0 | **10** | 0 | 3.7 |
| 5 | test_process_acl_native.py | 1 | 0 | 0 | 0 | 2.1 |
| 6 | test_process_login_closed.py | 8 | 0 | 0 | 0 | 1.1 |
| 7 | test_process_acl_mutex_native.py | 5 | 0 | 0 | 0 | 3.2 |
| 8 | test_process_native_boundary.py | 6 | 0 | 0 | 0 | 4.2 |
| 9 | test_process_launch_refusal.py | 6 | 0 | 0 | 0 | 0.8 |
| 10 | test_process_identity.py | 18 | 0 | 0 | 0 | 0.8 |
| 11 | test_process_profile.py | 6 | 0 | 0 | 0 | 0.7 |
| 12 | test_process_profile_folders.py | 8 | 0 | 0 | 0 | 0.8 |
| 13 | test_os_boundary_windows.py | 79 | **2** | 0 | 0 | 107.4 |
| 14 | test_os_boundary_windows_protected.py | 21 | 0 | 0 | 0 | 28.8 |
| 15 | test_os_boundary_windows_runner.py | 8 | 0 | 0 | 0 | 37.6 |
| 16 | test_os_boundary_windows_vendor.py | 10 | 0 | 0 | 0 | 32.1 |
| 17 | test_os_boundary_host.py | 18 | 0 | 0 | 0 | 6.6 |
| 18 | test_os_boundary_layout.py | 10 | 0 | 0 | 20 | 0.5 |
| 19 | test_project_ownership_process.py | 9 | 0 | 0 | 0 | 12.9 |
| 20 | test_process_acl.py | 4 | 0 | 0 | 0 | 0.5 |
| 21 | test_process_acl_folders.py | 6 | 0 | 0 | 0 | 0.6 |
| 22 | test_process_acl_restart.py | 53 | 0 | 0 | 0 | 1.4 |
| 23 | test_process_loans.py | 35 | 0 | 0 | 0 | 0.8 |
| 24 | test_process_loans_mutex.py | 5 | 0 | 0 | 0 | 0.6 |
| 25 | test_process_loans_overlap.py | 4 | 0 | 0 | 0 | 0.6 |
| 26 | test_process_loans_recovery.py | 6 | 0 | 0 | 0 | 0.6 |
| 27 | test_process_loans_scope.py | 39 | 0 | 0 | 0 | 0.9 |
| 28 | test_process_login_grant.py | 18 | 0 | 0 | 0 | 0.9 |
| 29 | test_process_login_hooks.py | 9 | 0 | 0 | 0 | 0.7 |
| 30 | test_process_login_overlap.py | 5 | 0 | 0 | 0 | 0.7 |
| 31 | test_process_login_refusals.py | 39 | 0 | 0 | 0 | 1.8 |
| 32 | test_process_login_return_order.py | 3 | 0 | 0 | 0 | 0.7 |
| 33 | test_process_rpc.py | 15 | 0 | 0 | 0 | 1.6 |
| 34 | test_adapter_boundary_launch.py | 89 | 0 | 0 | 0 | 33.2 |
| 35 | test_execution_boundary.py | 35 | 0 | 0 | 1 | 0.5 |
| 36 | test_container_view_mode.py | 6 | 0 | 0 | 0 | 1.9 |
| 37 | test_production_door_boundary.py | 11 | 0 | 0 | 0 | 3.5 |
| 38 | test_ownership_journals_cli.py | 19 | 0 | **9** | 0 | 10.0 |
| 39 | test_ownership_unavailable_reason.py | 10 | 0 | 0 | 0 | 10.5 |
| 40 | test_login_receipt_holds.py | 10 | 0 | 0 | 0 | 0.8 |
| 41 | test_windows_path_admission.py | 74 | 0 | 0 | 0 | 1.1 |
| 42 | test_windows_path_http.py | 51 | 0 | 0 | 0 | 1.5 |
| 43 | test_adapter_module_graph.py | 6 | 0 | 0 | 0 | 0.7 |
| 44 | test_command_adapters.py | 50 | 0 | 0 | 0 | 0.9 |
| 45 | test_command_package_doors.py | 4 | 0 | 0 | 0 | 2.0 |
| 46 | test_os_boundary_seatbelt_box.py | 0 | 0 | 0 | 25 | 0.5 |
| 47 | test_accept_commit.py | 20 | 0 | 0 | 0 | 41.2 |
| 48 | test_boot_prepared.py | 54 | 0 | 0 | 0 | 0.5 |
| 49 | test_command_project_git.py | 29 | 0 | 0 | 0 | 1.4 |
| 50 | test_conduct_home.py | 25 | 0 | 0 | 1 | 0.5 |
| 51 | test_fakeproc_publication.py | 3 | 0 | 0 | 0 | 1.5 |
| 52 | test_git_setup_facts.py | 8 | 0 | 0 | 1 | 6.7 |
| 53 | test_git_setup_first_commit.py | 25 | 0 | 0 | 13 | 137.0 |
| 54 | test_git_setup_first_lock.py | 72 | 0 | 0 | 5 | 4.1 |
| 55 | test_git_setup_first_prepare.py | 50 | 0 | 0 | 27 | 143.7 |
| 56 | test_git_setup_modes.py | 25 | 0 | 0 | 2 | 23.7 |
| 57 | test_hub_instance.py | 14 | 0 | 0 | 1 | 1.1 |
| 58 | test_hub_job.py | 18 | 0 | 0 | 1 | 3.1 |
| 59 | test_hub_owner_ops_real.py | 7 | 0 | 0 | 0 | 12.1 |
| 60 | test_hub_registry.py | 82 | 0 | 0 | 0 | 2.1 |
| 61 | test_hub_spawn.py | 31 | 0 | 0 | 1 | 7.1 |
| 62 | test_queue_pump_flag.py | 20 | 0 | 0 | 0 | 7.4 |
| 63 | test_queue_receipt_budget.py | 9 | 0 | 0 | 0 | 2.8 |
| 64 | test_server_bind_no_dns.py | 1 | 0 | 0 | 0 | 2.6 |
| 65 | test_up_hub_flags.py | 106 | 0 | 0 | 0 | 55.8 |
| 66 | test_up_status.py | 48 | 0 | 0 | 0 | 1.8 |
| | **итого** | **1478** | **17** | **19** | **98** | 794 |

Пропуски: почти все — POSIX-only, Seatbelt и gate `CONDUCT_OLD_GIT`. Несколько связаны с окружением: `[WinError 1314] Клиент не обладает требуемыми правами` при создании symlink (`test_git_setup_facts`, `test_git_setup_first_commit` ×2) и «this account cannot make symbolic links» (`test_git_setup_first_lock`). У учётной записи нет SeCreateSymbolicLinkPrivilege. Это пробел покрытия относительно CI (runneradmin), а не сбой. Пропусков `require_child_shell` нет.

## 3. Сигнатуры сбоев

| # | Сигнатура | Где (id) | Кол-во | Причина |
| --- | --- | --- | --- | --- |
| S1 | `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x8f in position 9` в `facts()` | login_native ×7, login_config_native ×2 | 9 F | RC1 |
| S2 | `assert ... exit_code == 0`, где `exit_code=1` | login_native ×1, loans_native ×1, login_config_native ×1 | 3 F | RC1 |
| S3 | `assert b'C:\\Users\\...Call\r\n \r\n' == b'work=denied;...'` | loans_native (review) | 1 F | RC1 |
| S4 | следы ребёнка отсутствуют: `'seed' == 'changed'`, `FileNotFoundError ...\claude-code\CLAUDE.md` | loans_native ×1, login_config_native ×1 | 2 F | RC1 |
| S5 | setup: `OwnershipError('login_recovery_required: shared resource lease is uncertain')` в обоих потоках | login_native_overlap | 10 E | RC1 (маскировано) |
| S6 | `the descendant never ran` [confined] / `the nested script is not a probe` [unconfined-control] | os_boundary_windows | 2 F | RC1 |
| S7 | setup: `HubRefusal: windows_path_too_long` | ownership_journals_cli | 9 E | RC2 |

## 4. Шаг 2: механизм

### 4.1 Кто запускается и кто декодирует

| Файл | Ребёнок | Как передан скрипт | Кто декодирует вывод |
| --- | --- | --- | --- |
| login_native, login_config_native | `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <install>\entry.ps1` внутри AppContainer, через продуктовый `ProcessRunner.run` | `entry.write_text(..., encoding="utf-8")`, **без BOM** (`tests/test_process_login_native.py:200`, `:209-211`) | тест: `facts()` = `outcome.output.decode()`, строгий UTF-8 (`:231`) |
| loans_native | то же | `tests/test_process_loans_native.py:108`, `:113-116` | тест: сравнение байтов (`:131-133`) |
| login_native_overlap | то же, в двух потоках | `write_text(..., "utf-8")` (`tests/test_process_login_native_overlap.py:55`) | тест: `child()` проверяет exit 0, затем `.decode()` (`:93-99`) |
| os_boundary_windows (nested) | `powershell -Command ...` запускает вложенный `powershell -File inner.ps1` | `write_bytes(script.encode("utf-8"))` (`tests/os_boundary_box.py:186-188`), `_INNER` (`tests/test_os_boundary_windows.py:82-88`) | тест смотрит на файлы. Сам helper `read_output` декодирует `"oem", errors="replace"` (`tests/os_boundary_windows.py:299-307`), поэтому без UnicodeDecodeError |
| Продукт | — | — | **Ничего не декодирует.** `_Owned._drain` и `finish` хранят байты (`src/conductor/command/adapters/process.py:388-440`) |

Кодировку симптома определяют флаги запуска в продукте. `_winlaunch.launch` вызывает CreateProcessW с `0x80000 | 0x08000000 (CREATE_NO_WINDOW) | 0x400 | CREATE_SUSPENDED`, а `hStdError = output`, если `separate_stderr=False` (`_winlaunch.py:444-453`). Без границы флаги те же: `_procgroup.popen_kwargs` (`_procgroup.py:119-122`). С CREATE_NO_WINDOW ребёнок получает новую скрытую консоль с OEM CP системы, то есть 866.

### 4.2 Сырые байты вывода ребёнка (продуктовый путь, кириллический basetemp, `dx_login.py ... cyr_test`)

`status=completed, exit_code=1, 3479 байт`. Первые 96 байт:

```
43 3a 5c 55 73 65 72 73 5c 8f ae ab ec a7 ae a2 a0 e2 a5 ab ec 5c 44 6f 63 75 6d 65 6e 74 73 5c 43 6f 64 65 78 5c 77 6f 72 6b
5c 6e 61 74 2d 64 78 31 5c 68 61 72 6e 65 73 73 65 73 5c 6b 69 74 5c 31 2e 30 5c 65 6e 74 72 79 2e 70 73 31 3a 31 20 a7 ad a0 aa
3a 36 39 39 0d 0a 2b 20 2e 2e 2e
```

- **cp866** (правильная):
```
C:\Users\Пользователь\Documents\Codex\work\nat-dx1\harnesses\kit\1.0\entry.ps1:1 знак:699
+ ... ); try { [IO.File]::WriteAllText('C:\Users\Р?Р?Р>С?Р·Р?Р?Р°С'РчР>С?\D ...
+                                                                  ~
Отсутствует ")" в вызове метода.
... Непредвиденная лексема "РчР>С?\Documents\Codex\work\nat-dx1\DecemberCommand\logins\claude-code\auth.json','token=refreshed'); $o += 'inplace=ok" в выражении или операторе.
... В операторе Try отсутствует блок Catch или блок Finally.
Выданы сообщения не обо всех ошибках синтаксического анализа. ...
    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException
    + FullyQualifiedErrorId : MissingEndParenthesisInMethodCall
```
- **cp1251**: `C:\Users\Џ®«м§®ў вҐ«м\...entry.ps1:1 §­ Є:699 ...` (мусор).
- **utf-8**: `UnicodeDecodeError: ... byte 0x8f in position 9`. Это ровно сигнатура S1. `8f ae ab ec a7 ae a2 a0 e2 a5 ab ec` = «Пользователь» в cp866.

### 4.3 Почему скрипт не разбирается

1. Файл `entry.ps1` начинается с `24 50 53 4d ...` (`$PSM...`), BOM нет. Windows PowerShell 5.1 читает такой файл в ANSI-кодировке системы, cp1251.
2. «Пользователь» в UTF-8 — это `D0 9F D0 BE D0 BB D1 8C D0 B7 D0 BE D0 B2 D0 B0 D1 82 D0 B5 D0 BB D1 8C`. В cp1251 это читается как `РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ`.
3. «т» = `D1 82`, а `0x82` в cp1251 — это `U+201A` (‚). Токенизатор PowerShell считает U+2018…U+201B одинарными кавычками. Литерал `'C:\Users\РџРѕР»СЊР·РѕРІР°С‚` закрывается на `‚`. Каретка «знак:699» указывает ровно на это место (`...Р°С'` в cp866-выводе), дальше идут каскадные ошибки разбора.
4. ParserError возникает до выполнения, поэтому ни одна строка скрипта не исполняется. Отсюда S2 (exit 1), S3 (в выводе текст ошибки вместо `work=...`) и S4 (ребёнок ничего не записал).

### 4.4 Почему вывод в cp866

Проба (`dx_ps.py`, без контейнера, флаги как у продукта) печатает `out_cp=866;oem=866;ansi=1251;text=` и затем байты `8f e0 a8 ac a5 e0` («Пример» в cp866). Если ребёнок наследует консоль родителя (без CREATE_NO_WINDOW): `out_cp=65001`, `d0 9f d1 80 ...`. `PYTHONUTF8`/`PYTHONIOENCODING` в окружении ребёнка ничего не меняют, а родитель с `chcp 866` и без PYTHONUTF8 даёт те же байты. Кодовая страница влияет только на вид симптома. При выводе в UTF-8 тест всё равно упал бы: exit 1 и разбор `facts()` по тексту ошибки.

### 4.5 Overlap: `login_recovery_required` — следствие, маскированное (`dx_overlap.py`)

Цепочка исключения в каждом потоке:

```
OwnershipError('login_recovery_required: shared resource lease is uncertain')
  context: OwnerRefused: login_recovery_required: shared resource lease is uncertain
  context: AssertionError: ProcessOutcome(status='completed', exit_code=1, ...)
```

Как это происходит. `child()` проверяет exit 0, получает AssertionError. В `LoginScopes.borrow` срабатывает `except`: `lease.uncertain = True`. Затем в `finally` вызывается `lease.close()` → `check()` → `OwnerRefused` (`src/conductor/ownership_login.py:217-223`, `:225-233`, `:241-259`). Оно заменяет исходную ошибку, и та остаётся только в `__context__`. R2 предполагал это без проверки; теперь цепочка получена.

### 4.6 os_boundary_windows (S6)

Механизм тот же: `inner.ps1` записан без BOM и содержит `@TMPD@` и `@SRC@` с кириллицей. Решающий факт — падает и вариант `[unconfined-control]` без контейнера.

### 4.7 ownership_journals_cli (S7)

`admit_home` отказывает, если `len(path) > 60` единиц UTF-16 (`src/conductor/hub/project_targets.py:52-53`). Путь `C:\Users\Пользователь\Documents\Codex\work\nat-a38\hclone0\personal\ConductProjects` — 83 символа. Fixture `bound` находится в `tests/test_hub_clone.py:44-53`. CI документирует обход коротким basetemp (`.github/workflows/ci.yml:61-69`).

## 5. Шаг 3: эксперименты (один фактор за раз)

| Эксперимент | Что изменено | Результат |
| --- | --- | --- |
| a) 6 упавших файлов, `--basetemp C:\Users\Public\dc-nat\pt1..pt6` | только путь временных данных (ASCII, короткий) | **всё зелёное:** 15, 8, 4, 10, 81 (203.6 с), 28 passed |
| a′) 5 PS-файлов, кириллический `...\work\nat-b1..b5`, `-p bomps1` (диагностический плагин: BOM к `.ps1`) | только байты `.ps1` | **всё зелёное:** 15, 8, 4, 10, 81 passed |
| a″) `test_ownership_journals_cli`, ASCII-basetemp той же длины 50 (`C:\Users\Public\dc-nat\long-ascii-basetemp-xxxxxx1`) | ASCII вместо кириллицы при равной длине | 19 passed, **9 errors** (тот же HubRefusal), то есть дело в длине |
| dx_login, продуктовый путь, ASCII-база `C:\Users\Public\dc-nat\dx-ascii` | путь | exit 0, все 28 фактов (`inplace=ok; ... git=denied;`) |
| dx_login, кириллица + BOM | BOM | exit 0, те же 28 фактов, байт в байт |
| dx_login, кириллица, скрипт только из ASCII | содержимое скрипта | exit 0, `alive=ok;` |
| dx_ps без контейнера, кириллица | контейнер убран | без BOM: exit 1, те же первые байты (`...file_utf8_nobom.ps1:1 знак:273 Отсутствует ")"...`). С BOM: exit 0. `-Command`: exit 0 |
| b) проба PowerShell внутри границы (только ASCII) | — | `USERPROFILE` не задан. `LOCALAPPDATA` перенаправлен в `<runtime>\Packages\conduct-…\AC`. `MyDocuments` пуст. `UserProfile=C:\Users\Пользователь`, листинг запрещён. `PSModulePath` пользователя относительный. StartupProfileData не создаётся. С `-NoProfile` профиль не читается и не нужен |
| b) env ребёнка: `USERPROFILE/APPDATA` → `C:\Users\Public\dc-nat\env\…` (и вариант с `LOCALAPPDATA/TEMP` туда же, грант `S-1-15-2-1` только на этот диагностический каталог) | окружение | тот же ParserError `знак:699`, exit 1. Окружение не фактор |
| c) кодовая страница | CREATE_NO_WINDOW, PYTHON* в env, chcp родителя | ребёнок без окна всегда пишет в 866. PYTHON* не влияют. Наследование консоли даёт 65001. Родитель с chcp 866 — те же байты |
| d) CPython (копия base runtime) в `<base>\harnesses\py\3.12`, запуск внутри границы через `container_profile(mode="dispatch", folders=AttemptFolders(...))` | кириллический путь install против ASCII | **оба работают:** `alive=1`, `work_write=ok`, `prefix` под кириллицей корректен. stdout в pipe по умолчанию `cp1251` (`cf f0 e8 ec e5 f0`). С `PYTHONUTF8=1` или `PYTHONIOENCODING=utf-8` — UTF-8 (`d0 9f d1 80 …`). Первый прогон с `-I` env игнорировал (методическая поправка), повторён с `-s` |

Расположение `python.exe` и `.venv` под кириллицей к сбоям не относится. Ни один нативный тест не запускает Python внутри контейнера: внутри границы выполняется только `powershell.exe`. Сам pytest работает вне границы. Python внутри границы с install-папкой под кириллическим путём работает.

## 6. Шаг 4: классификация

| Причина | Класс | Затрагивает реального пользователя | Обоснование |
| --- | --- | --- | --- |
| RC1: BOM-less UTF-8 `.ps1` + Windows PowerShell 5.1, строгий `.decode()` в тесте | **дефект теста** (хрупкий helper); проявляется из-за окружения: не-ASCII путь и CP 1251/866 | **нет** | продукт не пишет `.ps1` (grep `src` по `powershell|.ps1|-File` пуст), не декодирует вывод в runner, граница на кириллице доказана |
| RC2: basetemp длиннее лимита 60 | **окружение** (параметры запуска тестов) | нет | projects home по умолчанию — `C:\Users\Пользователь\ConductProjects`, 32 символа, это ≤ 60 |

Продуктовые места декодирования вывода ребёнка. Все при чужих байтах отказывают безопасно и не падают:

| Место | Режим | Что при не-UTF-8 |
| --- | --- | --- |
| `process.py:388-440` (`_drain`, `finish`) | байты | — |
| `independent_check.py:204-217` | strict | `no_verdict` |
| `feedback_protocol.py:93-101` | strict | `malformed_payload` |
| `artifact_transport.py:552-560`, `:742-750` | strict | evidence None / `uncontained` |
| `claude_code.py:508-511` | strict JSON | вход не допущен |
| `codex_cli.py:587`, `headless_values.py:75` | `replace` | — |
| `deep_codecs.py:64-71` | strict, `except Exception` | None |

Дороги review и verifier используют `separate_stderr=True` (`artifact_transport.py:386`, `independent_transport.py:58`). Локализованные OEM-сообщения stderr туда не попадают. Дефекта продукта по критерию «падает на чужих байтах» **нет**.

**Остаточный риск, не подтверждён.** Ребёнок с CREATE_NO_WINDOW получает консоль 866, а Python без UTF-8 mode пишет cp1251 (измерено, п. 5d). Если какой-то harness выводит текст не в UTF-8, строгие декодеры откажут: вердикта или публикации review не будет. По документации продукта пять harness V1 — нативные бинарники (`claude_code.py:103`, `codex_cli.py:8`, `grok_build.py:88`, `kimi_code.py:27,175`) или Node (`dsh_harness.py:7-9`) и пишут UTF-8. На этой машине это не измерено.

## 7. Шаг 5: влияние на владельца

- **Граница на кириллическом профиле не мешает.** Работают выдача и возврат прав на work/install/login/runtime, отказы, mutex, возврат DACL и перенаправление LOCALAPPDATA в AC. Доказательства: 118 нативных тестов пяти PS-файлов на кириллическом basetemp с BOM-фиксом; зелёные `test_process_native_boundary`, `os_boundary_windows_runner/vendor/protected/host`, `acl_native`, `acl_mutex_native`, `project_ownership_process` уже в основном прогоне; продуктовые пробы с дочерними PowerShell и Python.
- **Настоящая confined-задача** упирается в условия, которые не зависят от ноутбука:
  1. Дорога через подписку confined не предоставляется: `LOGIN_LOAN_OPEN = False` (`process_boundary.py:42`), `boundary_provided` равно false на подписке (`harness_attempt.py:142-166`). Claude Code, Codex, Grok и Kimi через вход по подписке будут отклонены до spawn. Нужна дорога с API-ключом (например, DSH).
  2. Закреплённая сборка должна лежать в `<любой>/harnesses/<name>/<version>`, и всё, что она загружает, — внутри этой папки (`harness_attempt.py:75-106`, `process_loans.py:219-236`, `:298-311`, `process.py:573-574`). Runtime вне системной папки тоже должен быть там, например node из `%USERPROFILE%\.cache\…`. Проба (b) показала, что контейнер не может читать профиль.
  3. Нужен живой owner. Корень проекта не длиннее 100 символов, projects home не длиннее 60; на этом профиле по умолчанию лимиты выполняются.
- Сквозной запуск реального vendor-harness через provider door в этой сессии **не выполнялся**: нет закреплённой установки и ключа. `test_adapter_boundary_launch.py:19-20` прямо не претендует на нативного свидетеля. Вывод: на уровне границы owner acceptance на этом ноутбуке возможна по дороге с API-ключом; дорога через подписку закрыта by design.

## 8. Рекомендации

1. **Тесты** (отдельная задача владельцу файлов; репозиторий я не трогал). Писать `.ps1` с BOM: `encoding="utf-8-sig"` в `tests/test_process_login_native.py:200`, `tests/test_process_loans_native.py:108`, `tests/test_process_login_native_overlap.py:55`; `script.encode("utf-8-sig")` в `tests/os_boundary_box.py:188`. Другой вариант — передавать тело через `-EncodedCommand`. В `facts()` и `child()` включать в сообщение assert вывод, декодированный с `errors="replace"` (oem), чтобы ParserError был виден вместо UnicodeDecodeError.
2. **CI.** Добавить не-ASCII компонент в короткий basetemp Windows-job, например `${{ runner.temp }}/пт`. Тогда этот класс сбоев будет ловиться в CI, а не на ноутбуке.
3. **Локальный прогон до исправления.** Короткий ASCII-basetemp (как в CI) или диагностический плагин `bomps1` (`C:\Users\Пользователь\Documents\Codex\work\nat-diag\plug\bomps1.py`, `PYTHONPATH=...\plug`, `-p bomps1`). Для hub-тестов basetemp должен быть коротким в любом случае.
4. **Документы.** Уточнить `tasks/R1.1-REPORT.md:75-76,97-99` и `tasks/R2-H5-ANALYSIS.md:160-172`. Механизм — RC1, дефект теста. Нативная характеристика `b9fc4c3` и свидетели аренды на этом ноутбуке переподтверждены (37 тестов четырёх login- и loans-native файлов зелёные при ASCII-basetemp и при BOM-фиксе).
5. **Продукт, необязательно.**
   - Диагностика `ownership_login.borrow` (`:241-259`): в отказ `login_recovery_required` стоит добавить класс исходного исключения, чтобы причина не терялась в `__context__`.
   - Явно описать, в какой кодировке пишут дети: при CREATE_NO_WINDOW это OEM. При появлении Python-harness стоит рассмотреть `PYTHONUTF8=1` в его env или отдельную причину «вывод не UTF-8» в квитанции.

## 9. Артефакты и уборка

- Диагностика: `C:\Users\Пользователь\Documents\Codex\work\nat-diag\`:
  - раннер `run_seq.py` и списки `files_*.txt`;
  - логи и junit-xml: `logsA` (основной прогон, `results.json`), `logsB` (ASCII), `logsC` (BOM), `logsD` (длина);
  - `dx_login.py` и `dx_login_*.json/.bin` (сырые байты);
  - `dx_ps.py` и `dx_ps_cyr.json`;
  - `dx_py.py` и `dx_py_{cyr,cyr2,ascii2}.json`;
  - `dx_overlap.py` и `dx_overlap.txt`;
  - `plug\bomps1.py`.
- Basetemp: `...\work\nat-a1..nat-a66`, `nat-b1..b5`, `nat-dx1`, `nat-dx3..dx9`, `nat-py1`, `nat-py2`.
- После прогонов в `HKCU\...\AppContainer\Mappings` нет записей `conduct*` (проверено только чтением, 0).
- **`C:\Users\Public\dc-nat\` удалён:** 34,4 МБ, 3854 элемента, `Test-Path` = False. В нём были `pt1..pt6`, `dx-ascii`, `dx-cp866`, `env` (единственный грант `S-1-15-2-1` был на этом каталоге), `py-ascii` и `long-ascii-basetemp-xxxxxx1`.
- Репозиторий не менялся: ни коммитов, ни stash, ни checkout. Чужие незакоммиченные изменения не тронуты. Отдельный файл отчёта не создавался.

## Проверка выводов (workflow `native-cyrillic-investigation`)

Оба скептика вывод не опровергли.

- **Скептик 1 (код, без прогонов).** Места записи `.ps1` без BOM и строгого `.decode()`
  в тестах подтверждены: `tests/test_process_login_native.py:199-211, 231`,
  `tests/test_process_loans_native.py:107-116`, `tests/test_process_login_native_overlap.py:55, 92-99`,
  `tests/os_boundary_box.py:52, 186-188`. Число и состав упавших тестов совпадают с картиной
  «скрипт-проба не выполнился», а не с «AppContainer/ACL не работает на кириллическом пути».
  Продукт `.ps1` не создаёт и не запускает. `_winlaunch.launch` использует `CreateProcessW` и
  `CREATE_UNICODE_ENVIRONMENT`. Вывод ребёнка продукт хранит байтами (`process.py:433-440`).
- **Скептик 2 (независимый повтор).** Результаты воспроизведены:
  - на кириллическом basetemp — 8F/7P, 3F/5P, 4F и 10E, как было;
  - на ASCII-пути `C:\Users\Public\dc-nat2` — 15P, 8P, 4P и 10P (каталог удалён);
  - на кириллическом пути с BOM — те же числа, и проходят оба теста `test_os_boundary_windows`;
  - микро-скрипты: «т» (D1 82) без BOM ломает разбор, «П» (D0 9F) без BOM выполняется,
    но читается как cp1251.

## Дополнительные наблюдения скептиков (вне причины сбоя)

- **O-N1. `ownership_login.borrow` и fail-closed.** Любое исключение внутри borrow
  (`src/conductor/ownership_login.py:249-255`) помечает аренду как uncertain. Дальше
  `close()` бросает уже в `check()` (`:220-223`), а `active.json` не перезаписывается (`:231`).
  Настоящий login-home после этого требует «recover explicitly after OS restart» (`:143-145`).
  Этот путь используется в продукте: `owned_login_attempt`, `login_lifetime.py:43-46`.
  Поведение задумано как fail-closed. Но одна сбойная попытка с арендой login-home
  оставляет login-home закрытым до явного восстановления после перезапуска ОС.
  Вопрос для Codex и владельца, связан с H5 (R2).
- **R-N1. Кодировка вывода настоящих vendor CLI на русской Windows.** Строгий UTF-8
  разбор в продукте отказывает безопасно: `independent_check.py:210-213`,
  `feedback_protocol.py:96-101`, `artifact_transport.py:552-560, 742-748`,
  `claude_code.py:508-511`, `jsonl_completion.py:55`, `hub/github.py:58-61`. Но если
  какой-то harness V1 (например, Kimi — «binary installs by script», `kimi_code.py:27`)
  пишет в pipe в ANSI/OEM, на машине с русской локалью это даст функциональную
  деградацию, а не нарушение границы. С настоящими harness не проверялось. Это относится
  к developer rehearsal в R5.

## Решение Opus

RC1 — дефект тестовых helper-ов. Исправляется только в тестах: `.ps1` пишется с BOM
через один общий helper; нужен регрессионный тест, который запускает скрипт с
не-ASCII литералом из каталога с не-ASCII именем и поэтому работает и в CI. RC2 —
параметр запуска: документировать короткий basetemp для этой машины. Задание
выполняется отдельно (N1-REPORT.md).