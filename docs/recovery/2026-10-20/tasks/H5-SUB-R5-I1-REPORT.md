# Отчёт по задаче: H5-SUB-R5 / I1. Слой runner для relay-home

- Исполнитель: Claude Code / Sonnet 5.5. Дизайн `H5-SUB-R5-DESIGN.md` v2 (Opus 5.5), только слой
  runner: раздел 2 (размещение, relay-корень, защищённый DACL), 3.1 (общая функция формы и разбор
  ACE), 3.2 (runner), нативный свидетель и тесты runner/`FolderLoans` из раздела 4. Транспорт
  (`login_relay`, спецификации, `_owned_attempt`, claim, тексты), `harness_attempt.py`,
  `headless_*.py`, `artifact_transport.py`, `independent_transport.py`, адаптеры вендоров, панель
  и документы владельца не менялись. Итерация 1 — реализация; итерация 2 — разбор ревью двух линз
  Opus (раздел «Ревью Opus»).
- Исходный commit и ветка: `0b763dc` в итерации 1; в итерации 2 HEAD `b7d959c` (docs, коммит
  ведущего), ветка `recovery/2026-10-20`. Мои изменения не закоммичены, ничего не запушено.
- Состояние рабочей копии до изменений: в итерации 1 `git status` чистый; в итерации 2 на входе были
  изменения итерации 1 (6 `M`, 8 `??`), поверх которых я работал.
- Чужие правки (не мои, не трогал): `AGENTS.md`, `docs/recovery/2026-10-20/OPEN-DECISIONS.md`,
  `docs/recovery/2026-10-20/CONTINUATION-PLAN.md`, `tasks/H5-SUB-R5-DESIGN.md`,
  `tasks/H5-SUB-R5-TASK.md` (все M), `tasks/PROC-STD-REPORT.md` и
  `tasks/H5-SUB-R5-V2-REVIEW-REPORT.md` (??). Дизайн я читал в версии на начало итерации 2; его
  правки во время работы не учтены. `CLAUDE.md` и `WORKING-STANDARD.md` во время итерации 1
  появлялись как чужие правки и теперь внесены в `b7d959c`.
- Цель и наблюдаемое ожидаемое поведение: runner одолжит AppContainer абсолютную папку
  `<relay>/<key>/<name>` рядом с `logins` как обычный home (права `modify`, тот же журнал и
  recovery), и только её. Абсолютная форма home означает relay-home и ничего другого: папка
  проекта пишется маршрутом. Любой другой абсолютный home, чужой key, link в маршруте, пересечение
  с проектом, work, install или login-home, незащищённый relay-корень, запись для `AC`, пакета или
  capability на relay-корне, key, relay-home, на настоящем login-home, его родителе и записях его
  верха отказываются до создания профиля. `LOGIN_LOAN_OPEN` остаётся `False`.

## Изменения

| Файл | Что |
| --- | --- |
| `adapters/relay_home.py` (новый, 460 строк) | форма, ключ, `absolute_home`, разбор ACE, DACL relay-корня (staging и rename), чтение login-home с записями его верха |
| `adapters/process_loans.py` (+46, -5; 708 строк) | `FolderLoans._refuse_relay_home` (форма по написанному, сверка реального места, relay-сторона, login-стороны), ветка в `targets` |
| `adapters/process.py` (+21, -5; 797 строк) | `RELAY_HOME_LOANS`, `_loaned` (абсолютный home через `absolute_home`), `ensure_relay_root` |
| `adapters/process_boundary.py` (+19, -8) | `AttemptFolders.home` принимает абсолютный путь |
| `command/boundary_entry.py` (+12) | `entry_lends_relay_homes(runner)` |
| `tests/_fakeboundary.py` (+29, -4) | абсолютный home судит та же `relay_home_shape` |
| `tests/test_command_adapters.py` (+4, -1) | `relay_home.py` в `SDK_WORKSPACE_DOOR` (страж импортов) |
| `tests/relay_fixtures.py` (новый, 116) | раскладки в tmp, fake native (DACL идёт за папкой при переименовании), hold папки и файла, `link` |
| `tests/test_relay_home_shape.py` | 59 тестов формы |
| `tests/test_relay_home_acl.py` | 85 тестов разбора ACE, login-home, DACL, `ensure_relay_root` |
| `tests/test_relay_home_loans.py` | 53 теста `FolderLoans`, `_loaned`, `AttemptFolders` |
| `tests/test_relay_home_boundary.py` | 17 тестов fake boundary, шва runner и `RELAY_HOME_LOANS` |
| `tests/test_relay_home_native.py` | 30 нативных тестов |

Пути `adapters/` это `src/conductor/command/adapters/`. Что в `relay_home.py`: `relay_root_for`,
`relay_key`, `relay_home_shape`, `absolute_home`, `relay_root_sddl`, `ace_refusal`,
`relay_root_refusal`, `relay_side_refusal`, `login_side_refusal`, `logins_refusal`,
`relay_acl_refusal`, `ensure_relay_root`. Транспорта и `_winlaunch` модуль не импортирует.

Как устроено и что отличается от текста задания (для ревью):

1. `relay_home_shape(auth_homes, root, root_identity, path, work, install)` проверяет путь как он
   написан: абсолютный, без `.` и `..`; имя `^[cx]-[0-9a-f]{16}$`; родитель точно равен
   `relay_key(root_identity)` (16 hex от `sha256("{vol}:{fileid}")`, запись как в
   `_winlaunch.acl_mutex_name`; без учёта регистра сравнения нет); `relay` и `DecemberCommand` по
   именам без учёта регистра; `normcase(realpath)` относительно `relay_root_for` одного из
   login-home; затем lstat-обход четырёх имён (`containment.contained_directory`: `_required_lstat`
   + `portal_violation`); затем непересечение по realpath с проектом, work, install и каждым
   login-home. Все четыре компонента должны существовать в момент вызова. Для `ready()` до создания
   relay-home есть `relay_acl_refusal(native, auth_home)` без relay-home.
2. Абсолютный home означает relay-home. `ProcessRunner._loaned` для абсолютного home зовёт
   `relay_home.absolute_home(path, root)`: путь, который лежит в проекте как написан или по
   `realpath` (junction снаружи внутрь), отказывается (`profile_acl_invalid: the relay home is
   refused: an absolute home is a relay home ...`); остальное идёт в loan как написано, без
   `_resolve_cwd`. `FolderLoans.targets` получает реальные папки: home вне проекта это relay-home,
   его судит `relay_home_shape` по написанному пути (в `realpath` нет link, обход их не увидел бы),
   home внутри проекта это результат пройденного маршрута, правила проектного home не изменились.
   Поэтому защита от «абсолютного home в проекте» стоит на шве runner (`_loaned`), а не в классе
   `FolderLoans`: по типу `Path` он не отличает абсолютную запись от пройденного маршрута
   (см. Л1-1).
3. `relay_side_refusal` до профиля читает три DACL: relay-корень ровно
   `O:<owner>D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;<owner>)` и protected (`native.acl_equal`), key-папку
   и relay-home только с унаследованными записями и без `AC`, `S-1-15-2-*`, `S-1-15-3-*` в A/OA
   (`ace_refusal` через `process_loans._split/_fields`; условная запись и непонятный DACL это
   отказ). `login_side_refusal` то же для настоящего login-home, `logins` и каждой записи верха
   login-home (файлы и папки, не больше 512; запись, которую нельзя открыть для чтения, отказ): их
   читает и `ready()` в I2, и runner на каждом grant (`logins_refusal`: все существующие login-home
   рядом с relay-корнем, потому что runner не знает, от какого логина работает попытка).
4. `ensure_relay_root(auth_home, *, native, hold_factory)` берёт `native` параметром, а вызывается
   через `ProcessRunner.ensure_relay_root(auth_home)`. Причина: страж `test_command_package_doors`
   допускает `import _winlaunch` только в `process.py`. Под
   `acl_exclusive(NativeHold(DecemberCommand))`: существующая папка только проверяется, чужой DACL
   не чинится; несуществующая делается рядом под именем `.relay.<16 hex>.tmp`, получает protected
   DACL, перечитывается и сравнивается, и только потом `os.rename` в `relay` (Windows не
   заменяет), затем ещё одно чтение. `relay` не появляется без своего DACL при любой остановке
   процесса; пустые остатки stage подметаются следующим вызовом.
   Отказ это `ProfileRefused("profile_acl_invalid")`, текст называет папку (`DecemberCommand/relay`)
   и действие (удалить, когда попытки нет; продукт сделает снова). Внутри lease такое исключение
   сделало бы lease uncertain (F3), поэтому I2 должен звать её до входа в lease.
5. Владелец relay-корня: DACL строится по владельцу самой папки (как `process_acl._grant`). Папка
   другого владельца с DACL (SY, этот владелец) проходит как «точная», но пользователю продукта она
   не даёт доступа, первая папка key откажется ОС; привязка к SID токена не делалась (см. Л1-5 и
   «Открытые вопросы»).
6. Удаление и перенос relay-home ребёнком показаны попыткой: профиль без DELETE получает от ОС
   access denied (`IOException/80070005` для переноса, `IOException/80131620` для
   `Directory.Delete`, это ветка access denied .NET Framework), а профиль с DELETE на home получил
   бы sharing violation
   `IOException/80070020` от собственного handle runner (измерено мутантом N1). Прежний пункт 6
   этого отчёта («попыткой не показать») был неверен и снят (Л2-1). Дополнительно тест читает DACL,
   который сообщает ОС: запись профиля на сам home `0x1201BF`, наследуемая `0x1301BF`.

## Проверки

Каждая команда после `. ...\December-Command-Environment.ps1 -Quiet` (`PYTHONUTF8=1`, где не
сказано иное), basetemp `C:\Users\Пользователь\pt-<1 символ>` (26 символов), Windows 11, Python
3.12.14, git 2.53.0. Сети нет. Итерация 2, финальный код.

| Команда | Результат | Что доказывает |
| --- | --- | --- |
| 4 юнит-файла `tests/test_relay_home_*` | **214 passed**, 4 с | слой без ОС |
| `tests/test_relay_home_native.py`, один процесс | **30 passed**, 3.5 с | свидетель, см. ниже |
| то же, ASCII basetemp `C:\Users\Public\pt-r` | **30 passed**, 3.3 с | basetemp как на CI (путь без кириллицы) |
| без `PYTHONUTF8` (cp1251): 4 юнит-файла / native | **214 / 30 passed** | кодировка не влияет |
| смежные без нативных, 26 файлов (а) | **707 passed**, 35 с | прежнее цело, страж `_winlaunch` зелёный |
| 5 файлов дверей и транспортов (б) | **185 passed, 1 skipped**, 181 с | fake boundary прежний; skip тот же, что в I1 |
| `test_process_loans_native` / `_login_closed` | 8 / 8 passed | аренда home, gate login-home закрыт |
| `test_process_login_native` / `_native_overlap` / `_config_native` | 15 / 10 / 4 passed | refresh-шаблоны, конфиг login |
| `test_process_native_boundary` / `_acl_native` / `_acl_mutex_native` | 6 / 1 / 5 passed | нативная граница, журнал ACL, мьютекс |
| все 9 нативных файлов в ОДНОМ процессе | **87 passed**, 19 с | свидетель не требует отдельного процесса |
| скрипт лимитов (13 файлов: добавленные строки) | OK | см. ниже |

(а) `test_process_acl`, `_acl_folders`, `_acl_restart`, `test_process_identity`,
`test_process_launch_refusal`, `test_process_loans`, `_loans_mutex`, `_loans_overlap`,
`_loans_recovery`, `_loans_scope`, `test_process_login_grant`, `_hooks`, `_overlap`, `_refusals`,
`_return_order`, `test_process_profile`, `_profile_folders`, `test_process_rpc`,
`test_command_adapters`, `test_command_line_cap`, `test_command_import_hygiene`,
`test_command_package_doors` (22) и четыре новых юнит-файла (26 файлов).
(б) `test_adapter_boundary_launch`, `test_production_door_boundary`, `test_execution_boundary`,
`test_subscription_road_boundary`, `test_container_view_mode`.

Нативные файлы из таблицы по одному прогонялись и каждым своим процессом pytest (по одному файлу),
и вместе в одном процессе (порядок: login-файлы первыми, `test_relay_home_native` последним).

Юнит-файлы: форма (имя, key точно, `..`, link, пересечения), ACE (`AC`, `S-1-15-2-*`,
`S-1-15-3-*`, `OA`, условная запись, норма), записи верха login-home (имена, ссылка, два имени,
граница 512), `FolderLoans` с fake native (relay-home допущен, остальные отказаны, незащищённый
relay-корень отказан, login-home рядом с записью для контейнера отказан, отказ до профиля),
`ensure_relay_root` (stage, rename, остановка, остатки), `_loaned` с абсолютным путём (в проекте
отказ), `AttemptFolders`, fake boundary и шов runner отказывают одним и тем же абсолютным home,
`RELAY_HOME_LOANS`.

Нативный свидетель, ребёнок в реальном AppContainer с `internet_client=True` на relay-home; каждая
проба пишет тип исключения и HRESULT (`_probe`), а «отказано» значит ровно
`UnauthorizedAccessException/80070005`:

- может: обновить лист на месте (тот же file id), `MoveFileEx` поверх (`True`), delete+move,
  создать файл и вложенную папку;
- capability измерена: файл с одной записью `S-1-15-3-1` читается, соседний без неё нет;
- не может: переместить (`IOException/80070005`) и удалить (`IOException/80131620`) relay-home,
  менять ACL, писать и создавать в key-папке, relay-корне и чужом relay-home, читать чужой
  relay-home, читать, писать, создавать и листать настоящий login-home, писать в `logins` и в box
  `active.json`, писать в install, источник и `.git`; work записан;
- после выхода DACL всех 9 папок прежние, `icacls /T` не называет профиль нигде,
  `LOGIN_LOAN_OPEN is False`, реальные DACL проходят `relay_acl_refusal`;
- `ProcessRunner.ensure_relay_root` делает protected SYSTEM+owner, повторный вызов только проверяет.

Нативные отказы, матрица «объект, мутация, кто отказал» (ровно то, что в тестах):

| Объект | Мутация (icacls) | Кто отказал нативно |
| --- | --- | --- |
| relay-корень | `/inheritance:e`, Everyone, `S-1-15-2-1`, `S-1-15-3-1` | `ensure_relay_root` (DACL не тронут) и runner до профиля (журнал пуст, DACL не тронуты) |
| key-папка, relay-home | `S-1-15-2-1`, `S-1-15-3-1` (правило контейнера); Everyone (правило «только унаследованное») | runner до профиля (журнал пуст, DACL не тронуты) |
| login-home, `logins` | `S-1-15-2-1`, `S-1-15-3-1` | `relay_acl_refusal` и runner до профиля |
| лист login-home | `S-1-15-2-1`, `S-1-15-3-1` | `relay_acl_refusal` (с relay-home и без) и runner до профиля |
| чужой relay-home, home вне relay | | runner до профиля |

Нативно НЕ проверено: `relay_acl_refusal` на relay-корне, key и relay-home с этими записями (это
держат юнит-тесты). Runner не читает DACL login-home для проектного home (не его loan).

Лимиты: строк длиннее 100 в добавленных строках кода нет, хвостовых пробелов нет, один `\n` в конце,
CR и BOM нет, файлы ≤ 800 (`process.py` 797, у него длинная строка 709 была и раньше). `ruff` в
окружении не установлен, не запускался; неиспользуемые импорты в новых и изменённых файлах проверены
разбором AST в I1 (новых нет); в итерации 2 новые импорты (`itertools`, `secrets`, `os`, `re`,
`Path`, `link`, `NativeOwnershipError`) используются.

### Мутанты

Копия `src`, `tests`, `pyproject.toml` лежала в `C:\Users\Пользователь\Documents\Codex\work\i1-mut\`
(`PYTHONPATH` на её `src`, проверено: `conductor` импортируется из копии). M0 без изменений: 214
passed и 30 passed. После каждого мутанта файл возвращён, SHA-256 сверен: совпал во всех 27 случаях.
Копия и `pt-*` удалены; драйвер, журналы и пробы в `Documents\Codex\work\i1-iter2\`.

| Мутант (в копии) | Результат | Что красное |
| --- | --- | --- |
| M1 `relay_home_shape` принимает чужой key | unit 5; native 1 | shape, key точно, fake, native «чужой home» |
| M2 `relay_side_refusal` не читает DACL relay-корня | unit 7; native 4 | `FolderLoans` на корень, readiness, native |
| M3 `ace_refusal` пропускает `S-1-15-3-` | unit 18; native 4 | все `S-1-15-3-*`, key/home и лист login-home нативно |
| M4 `_loaned` ведёт абсолютный home через `_resolve_cwd` | unit 9; native 15 + 14 err | `_loaned`, шов runner, весь свидетель |
| M5 fake без `relay_home_shape` | unit 13 | отказы fake, паритет, «спрашивает общую функцию» |
| M6 без lstat-обхода маршрута | unit 7 | link в `relay`, `key`, `home`; нет компонента |
| M7 loan судит форму по realpath | unit 3 | link в `relay` и `key` в `FolderLoans`, сверка реального места |
| M8 явные записи на key и home разрешены | unit 3; native 2 | acl и loans на явную запись; нативно (раньше зелёный) |
| M9 relay-корень создаётся без protected | unit 5; native 16 + 14 err | порядок и DACL `ensure_relay_root`, свидетель |
| A1 `absolute_home` ничего не отказывает | unit 8 | 4 случая шва runner и 4 паритета |
| A2 `absolute_home` судит только написанный путь | unit 2 | junction снаружи внутрь (шов и паритет) |
| A3 `_loaned` не зовёт `absolute_home` | unit 8 | шов runner и паритет |
| B1 `login_side_refusal` не читает записи верха | unit 20; native 2 | записи login-home, `FolderLoans`, нативный отказ листа |
| B2 скан записей пропускает папки | unit 4 | папка с записью, ссылка |
| B3 скан без границы 512 | unit 1 | граница |
| C1 нет сверки реального места с обходом | unit 1 | подмена `_plain_directory` |
| D1 loan не спрашивает login-home | unit 10; native 3 | login-home, `logins`, лист через `FolderLoans`, нативно через runner |
| D2 несуществующий login-home читается как существующий | unit 2 | не блокирует loan |
| E1 relay создаётся на месте, как раньше | unit 2 | порядок, `relay` без DACL |
| E2 нет уборки остатков stage | unit 1 | подметание |
| E3 нет чтения после rename | unit 1 | дрейф после rename |
| E4 отказ без папки и действия | unit 5 | текст отказа |
| E5 неудачный stage остаётся | unit 5 | остановка, дрейф, не удалось задать |
| F1 key без учёта регистра | unit 1 | key точно |
| N1 профилю дан DELETE на relay-home | native 2 | перенос/удаление (теперь `80070020`), маска; прежний свидетель краснел только по маскам |
| N2 ребёнок в свидетеле без `internet_client` | native 1 | capability; в I1 выживал (23 passed по ревью) |
| N3 runner не передаёт capability в запуск | native 1 | capability; в I1 выживал |

Числа: красные тесты (failed) и ошибки фикстуры (err). Под N1 ребёнок сообщает
`home_move=IOException/80070020`, `home_delete=IOException/80070020` (штатно `80070005` и
`80131620`).

Сохранено вне репозитория (`Documents\Codex\work\i1-iter2\`): `mutate.py` (драйвер и список
мутантов), `mutants.json` и `mutants-final.log` (итоговые числа), `limits.py`, `probe_dump.py` и
`n1_facts.py` (факты ребёнка). Статус по шкале: реализовано, локально проверено.

## Отклонения

| Что | Почему | Кто утвердил |
| --- | --- | --- |
| `ensure_relay_root` берёт `native` параметром и вызывается через `ProcessRunner.ensure_relay_root` | страж `test_command_package_doors` допускает `import _winlaunch` только в `process.py` (красный на первой версии) | ожидает ведущего (с I1) |
| Отказ абсолютного home в проекте стоит на шве `ProcessRunner._loaned`, а не внутри `FolderLoans.targets` | по типу `Path` `targets` не отличает абсолютную запись от пройденного маршрута; прямой вызов `targets` с проектным home остаётся контрактом loan (`test_process_loans_scope`) | ожидает ведущего (Л1-1) |
| Владелец relay-корня не привязан к SID токена процесса | утечки нет; нужен нативный вызов и повышенный процесс даёт ложный отказ | ожидает ведущего (Л1-5б) |
| Дизайн §3.1 называет только папки login-home; runner и readiness читают ещё записи его верха | лист с записью для AC читается ребёнком при закрытых папках (измерено) | ожидает ведущего (правка текста дизайна) |

## Не проверено

- CI-прогон нативного свидетеля: локально зелёный на кириллическом и ASCII basetemp, один и в одном
  процессе со всеми нативными файлами; на CI не запускался, пункт открыт до зелёного прогона.
- Живые CLI Claude Code и Codex на relay-home, refresh-вызовы вендора, M1-M3 из раздела 5 дизайна:
  это транспорт и измерения, не слой runner.
- Не-Windows: `ProcessRunner.ensure_relay_root` отказывает `CommandSpecError` по `os.name`;
  отказ не прогонялся (хост Windows). Юнит-тесты слоя платформенно нейтральны, кроме проверки имени
  мьютекса (Windows) и link (junction на Windows, symlink иначе); `os.rename` без замены на POSIX не
  проверялся (продукт там не запускается).
- Гонка двух процессов над `ensure_relay_root` не воспроизводилась: мьютекс `acl_exclusive` взят, и
  при существующей `relay` rename не заменит папку, но проверено только на одном процессе.
  Убийство процесса между шагами не воспроизводилось, инвариант «`relay` без DACL не появляется»
  проверен по порядку вызовов и остановкой внутри `acl_set`.
- Rename папки при открытом чужом handle (антивирус, индексатор): не воспроизводилось; тогда
  `ensure_relay_root` откажет (`PermissionError`), stage уберёт, без retry.
- Записи глубже верха login-home (вложенные файлы) не читаются: учётные листы лежат наверху.
- Константы `IOException/80070005` и `IOException/80131620` измерены на .NET Framework Windows
  PowerShell 5.1 этой машины.
- Владелец relay-корня: DACL строится по владельцу самой папки (как `process_acl._grant`); процесс с
  повышением, создавший папку под владельцем Administrators, даст отказ в доступе, а не расширенные
  права. Привязка к SID токена не делалась.
- Страж «под `Path.home()` ничего не создано» (раздел 4 дизайна, 3.5) не добавлен, это I2. Руками:
  `~/DecemberCommand` и `~/.december-command` после всех прогонов не существуют, все пути тестов
  в `tmp_path`.

## Открытые вопросы

1. Привязать владельца relay-корня к SID токена процесса (Л1-5б)? Нужен нативный вызов в
   `_winlaunch` (TokenUser); для повышенного процесса папка принадлежит Administrators, и проверка
   откажет. Сейчас не делается, утечки нет. Рекомендация: оставить как есть до I2.
2. Глубина чтения login-home: верх (до 512 записей). Нужна ли вложенность, решает ведущий
   вместе с дизайном §3.1 (там названы только папки: добавить «и записи верха login-home»).
3. Маркер на уровне типов вместо защиты на шве `_loaned` (обёртка `RelayHome` в `targets`) дал бы
   то же самое внутри `FolderLoans`, но потребовал бы правки `process_profile` и тестов loan;
   не делал. Рекомендация: не нужно, пока единственный источник `folders` это `_loaned`.
4. Цена: runner теперь читает DACL login-home, `logins` и записей его верха на каждом grant
   relay-home. `ready()` в I2 это же читает заранее; повтор нужен против гонки между ready()
   и grant.
5. Необязательная сверка identity hold с identity, прочитанной при обходе (Л1-3), не сделана:
   гонка возможна только процессом того же пользователя, relay-корень закрыт для остальных.

## Новые файлы для `CAPPED` (вносит ведущий)

```
src/conductor/command/adapters/relay_home.py
tests/relay_fixtures.py
tests/test_relay_home_shape.py
tests/test_relay_home_acl.py
tests/test_relay_home_loans.py
tests/test_relay_home_boundary.py
tests/test_relay_home_native.py
```

`tests/test_command_line_cap.py` не менялся. `boundary_entry.py` и `_fakeboundary.py` уже в списке,
их добавленные строки в пределе 100.

## Ревью Opus

Две линзы (безопасность и корректность runner; доказательность), 13 находок, из них одна общая
(Л1-1 и Л2-2). Каждую проверил сам: подтверждены все 13 по существу, одна (Л1-5б) без правки кода
по причине ниже, одна (Л2-6) частично. Пробы ревью (`probe_i1_review.py`, `_order.py`,
`_leaf_native.py`) перепрогнаны мной до правок и подтвердили Л1-1, Л1-2, Л1-3, Л1-6, Л1-5б.

| № | Статус | Доказательство | Что сделано, что держит |
| --- | --- | --- | --- |
| Л1-1 + Л2-2 (major) абсолютный home вне семантики relay | подтверждена | P1: `FolderLoans.targets` принял `<root>\jl\a` и `<tmp>\outside-link\a` как `<root>\.claude-home\a`; `_loaned` отдал `<root>\jl\a` без обхода (маршрут `jl/a` даёт `ContainmentError`); fake отказывал | `absolute_home` в `_loaned`: абсолютный home в проекте (написан или реально) отказ. Отличие от формулировки ревью: сам `FolderLoans.targets` по `Path` не отличает абсолютную запись от пройденного маршрута (`test_process_loans_scope` передаёт ему проектные home как `Path`), поэтому защита на шве runner; тест `..._still_judged_by_the_rules_of_a_project_home` не заменён отказом, а переименован и описывает контракт loan (реальное место пройденного маршрута); отказ абсолютной формы в двух новых тестах шва (по 4 случая) и 3 новых случаях паритета fake/runner. Мутанты A1-A3, M4 |
| Л1-2 (major) login_side_refusal не видит лист | подтверждена нативно | перепрогон P8: readiness `None`, ребёнок `leaf_read=ok;list=denied` при `*S-1-15-2-1:R` на `.credentials.json` | `login_side_refusal` читает ещё каждую запись верха login-home (файлы и папки, до 512); нативные отказы листа (`S-1-15-2-1`, `S-1-15-3-1`) в readiness и в runner; контроль: ребёнок читает лист с записью, добавленной после проверки runner. Мутанты B1-B3, D1 |
| Л1-3 (minor) порядок realpath и обхода | подтверждена | P7: `targets` вернул `<tmp>\elsewhere\anything` | в `_refuse_relay_home` сверка `realpath(spelled) == real["home"]`, иначе отказ; тест с подменой `_plain_directory`. Необязательную сверку identity не делал. Мутанты C1, M7 |
| Л1-4 (minor) runner не перепроверяет login-side | подтверждена (отклонение от §3.1: «это держат юнит-тесты FolderLoans») | `_refuse_relay_home` звал только `relay_side_refusal` | `logins_refusal` для всех существующих login-home рядом с relay-корнем; несуществующий не блокирует; нативно login-home, `logins` и лист отказывает runner (`refused_before_a_profile`), не только прямой вызов. Мутанты D1, D2 |
| Л1-5а (minor) `relay` без DACL после остановки | подтверждена по коду | `root.mkdir()`, затем отдельный `acl_set`; существующий тест `(INHERITED, False)` подтверждает вечный отказ | stage `.relay.<hex>.tmp`, DACL, чтение, rename, чтение; остатки подметаются; текст отказа с папкой и действием. Тесты: `relay` не существует в момент `acl_set`, остановка (OSError, KeyboardInterrupt), остатки. Мутанты E1-E5, M9 |
| Л1-5б (minor) владелец не привязан к пользователю | подтверждена как наблюдение (P5: `ensure_relay_root` вернул папку с владельцем `S-1-5-21-9`), код не менял | утечки нет: DACL называет только SY и этого владельца, пользователь продукта не получит доступа, первая папка key откажется ОС; SID токена нужен нативно и для повышенного процесса даёт ложный отказ; владелец `DecemberCommand` как эталон даёт ложный отказ для папки, созданной другим процессом | docstring `relay_root_refusal` фиксирует; текст отказа называет папку и действие. Решение за ведущим (вопрос 1) |
| Л1-6 (minor) key через `normcase` | подтверждена (P4: верхний регистр принят) | `normcase(key.name) != normcase(wanted)` | `key.name != wanted`; тест (ключ с буквой, оба написания). Мутант F1 |
| Л2-1 (major) `_tries` сводит всё к «denied» | подтверждена моими измерениями | все 21 отказ свидетеля `UnauthorizedAccessException/80070005`; перенос home `IOException/80070005`, `Directory.Delete` `IOException/80131620`; с DELETE на home оба `80070020`. Пункт 6 прежнего отчёта неверен | `_probe` пишет тип и HRESULT; тесты требуют точных значений; добавлена проба удаления home; пункт 6 переписан. Мутант N1 красит 2 теста (раньше только маски) |
| Л2-3 (minor) `internet_client=True` не измерен | подтверждена: в свидетеле не было пробы capability; мутанты ревью R3/R3b выживали (23 passed) | | файл с записью `S-1-15-3-1` и соседний без неё; N2 и N3 красные |
| Л2-4 (minor) regex «has an entry» слишком широк | подтверждена по коду (совпадает с «has an entry of its own») | по ревью M3 нативно краснил только readiness | regex сужен до фразы правила контейнера; нативный тест правила «только унаследованное» (Everyone); M3 красит нативно key/home/лист, M8 теперь красен и нативно |
| Л2-5 (minor) отчёт шире прогонов | подтверждена | S-1-15-3-1 на relay-корне нативно не ставился; runner на login-home не проверялся; «журнал пуст» только в случаях runner | `S-1-15-3-1` на relay-корне добавлен нативно; отчёт переписан матрицей «объект, мутация, кто отказал» (выше) |
| Л2-6 (minor) «run alone» и CI | подтверждена частично: условие в docstring ничем не обосновано, прочие нативные файлы его не требуют | CI = один процесс с ASCII basetemp | строка из docstring убрана; проверено локально: 9 нативных файлов в одном процессе 87 passed, relay native на ASCII basetemp 30 passed. CI не запускался: пункт открыт |
| Л2-7 (minor) учёт | подтверждена: `pt-b1`, `pt-i1..9`, `pt-n1..9` по 27 символов (> 26); 25 вместо 26 файлов | | basetemp `pt-<1 символ>` (26 символов), имена сверены с существующими до запуска, чужие не тронуты, свои удалены; число файлов исправлено на 26 (22 + 4) |

## Ревью Codex

Статус: ожидает. Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit кода и тестов: `74e4b30` (ведущий Opus, 23.10.2026), не запушен. Перед коммитом
  ведущий повторил: юнит и стражи 444 passed; нативный свидетель отдельным процессом 30 passed; без
  `PYTHONUTF8` юнит вместе с `test_subscription_road_boundary` и `test_production_door_boundary`
  269 passed. Этот отчёт — отдельный docs-коммит.
- `CAPPED`: семь новых файлов внесены ведущим в том же коммите `74e4b30`.
- Состояние ниже — на момент конца итерации 2, до коммита.
- `git status --short` в конце итерации 2: `M` у `process.py`, `process_boundary.py`,
  `process_loans.py`, `boundary_entry.py`, `tests/_fakeboundary.py`,
  `tests/test_command_adapters.py` (мои) и у пяти чужих документов (см. «Чужие правки»);
  `??` у `relay_home.py`,
  `tests/relay_fixtures.py`, четырёх юнит-файлов `tests/test_relay_home_*.py`,
  `tests/test_relay_home_native.py` и этого отчёта (мои), `PROC-STD-REPORT.md` и
  `H5-SUB-R5-V2-REVIEW-REPORT.md` (чужие).
- Для I2 (транспорт): `entry_lends_relay_homes(runner)` для `_launch_covers`;
  `ProcessRunner.ensure_relay_root(auth_home)` звать до lease; ключ `relay_key(identity(root))`
  равен ключу журнала (`profiles.root_identity`); relay-home создавать `mkdir(exist_ok=False)` до
  вызова `relay_acl_refusal(native, auth_home, relay_home)`; `AttemptFolders.home` абсолютной
  строкой и только для relay-home (абсолютный home в проекте runner отказывает; проектный home
  пишется маршрутом); настоящий login-home перед claim проверять `relay_acl_refusal`
  (теперь включает записи верха login-home), runner повторит это на grant.
- Обновлённые документы: только этот отчёт.
- Следующий конкретный шаг: ревью Codex diff `74e4b30`; I2 (транспорт) по решению Codex (DESIGN §8).
- Временные файлы вне репозитория: мои `pt-a`...`pt-n` (одна буква), `C:\Users\Public\pt-r` и копия
  `work\i1-mut` удалены; чужие `pt-*` не тронуты; `work\i1-iter2\` (драйвер мутантов, лимиты, пробы,
  журнал) оставлен.
