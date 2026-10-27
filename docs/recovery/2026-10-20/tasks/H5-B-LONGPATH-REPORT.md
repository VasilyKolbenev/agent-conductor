Итог: локально проверено и принято ведущим (раздел «Приёмка ведущего»), ревью Codex ожидает |
код, тесты и `CAPPED` — `52f3d50`; полный core на нём: 18 708 passed, 409 skipped, 0 failed и
native 101 passed в каждой кодировке (из них `test_long_path_native` 10) | новые тесты 79 passed
в UTF-8 и cp1251; красная фаза: на `src` HEAD 53 failed, 8 passed (61 тест), на коде итерации 2
8/71, до правки ревью итерации 2 24/55; мутанты: 58 исполнителя и OWN2 ведущего — все убиты |
отклонения: семь, все приняты ведущим; стоп-условий нет | следующий шаг: новая защищённая
установка продукта на `52f3d50`, затем список уборки остатка B1 владельцу, перезагрузка и
штатное восстановление (условия B2 3–4 решения Codex `c0b438d`).

# Отчёт по задаче: H5-B-LONGPATH — уборка на путях длиннее 260 символов

- Исполнитель: Sonnet 5.5 (по заданию ведущего Opus); не коммитил, `CAPPED` не трогал.
- Прочитано: `tasks/H5-B-LONGPATH-TASK.md` по `d861e8b` + `e16ee8d` + `c0b438d` (последний добавил
  тест восстановления остатка старого формата), стандарт §10 по `0125e15`,
  `H5-B-RUN2-DECISION-REPORT.md` (`c0b438d`). Вторая итерация: две линзы ревью Opus (правильность
  и безопасность уборки; доказательность и стандарт), разобраны в разделе «Ревью Opus». Третья
  итерация: независимая проверка второй (Opus, 8 находок), разобрана в разделе «Проверка второй
  итерации (Opus)».
- Исходный commit и ветка: `recovery/2026-10-20`, старт на `e16ee8d`; в ходе работы HEAD ушёл на
  `fc9b118` чужими документальными коммитами (см. «Чужие правки»). Код `src` на HEAD равен коду
  `bc61db8` (`git diff bc61db8 HEAD -- src` пуст), поэтому красная фаза на `src` HEAD — красная
  фаза на `bc61db8`.
- Состояние рабочей копии до изменений: чисто. Вторая итерация началась с рабочей копии первой
  (6 `M` в `adapters/`, `M` `tests/test_login_relay_leaf.py`, 7 `??`), она сохранена и правится.
  Третья итерация началась с рабочей копии второй плюс одна правка ведущего (`M`
  `tests/test_command_line_cap.py`: шесть новых файлов в `CAPPED`); эту правку не трогал.
- Цель: уборка папки попытки, домиков, relay-home и чтение рабочей копии работают на путях
  длиннее 260 символов при `LongPathsEnabled = 0`; проверки уборки прежние.

## Причина и исправление (§10.2)

**Воспроизведение.** `repro_longpath.py` (Opus) и свой замер `work\lp\measure1.py`: на Windows с
`LongPathsEnabled = 0` имя из 362 символов в обычной форме даёт `FileNotFoundError`
(`WinError 3`) у `os.lstat`, `os.scandir`, `Path.iterdir`, `os.rmdir`, а `Path.exists()`,
`Path.is_dir()`, `os.path.lexists` отвечают `False` **молча**. Через `\\?\` + абсолютный путь те
же вызовы работают (`iterdir`, `relative_to`, `rmdir`, `link`, `CreateJunction` проверены).

**Подтверждённая гипотеза.** Причина — имя, которое продукт передаёт ОС, а не права и не лимит
записей: тот же процесс читает тот же путь в форме `\\?\` (замер выше). Воспроизведение идёт без
ребёнка и без ACL (обычная папка в tmp), значит ни гонка с ребёнком, ни права к причине не
относятся. Другие гипотезы отдельными экспериментами не проверялись, эта объяснила все наблюдения.

**Следствия по местам (измерено красной фазой на `src` HEAD).**

| Место | Что давала обычная форма |
| --- | --- |
| `process_acl._walk_plain` | `ProfileRefused("owned attempt is unreadable")` после работы ребёнка (симптом B1) |
| `harness_workspace._leaf` | `None`, то есть «нет такой записи» (ложь, не ошибка) |
| `harness_workspace._remove_tree` | глубокие записи приняты за отсутствующие, затем `rmdir` → `OSError WinError 145` |
| `harness_workspace.sweep_homes` (листинг корня) | на HEAD `OSError WinError 145`; после правок итераций 1–2 имя из листинга чистилось ещё раз: `...`/`.. `/` ` — стёрт весь корень; `h.`/`h ` — молча оставлена; junction `h `/`h.` — не названа (итерация 3) |
| `work_seed` (4 обхода) | `FileNotFoundError` из `iterdir` (измерено); по коду, файл на границе (каталог короче 260, имя файла переводит путь за 260) `iterdir` видит, а `_leaf` отвечал «нет», и дайджест молча его пропускал (отдельным тестом не воспроизводилось) |
| `login_home._walk` / `_take_one` | измерение `None` («неизвестно», отказ прогона) / файл не убран, «остался» |
| `login_relay.read_leaf` | `Refused("leaf_absent")` для существующего файла |
| `relay_home.leaf_kind` | `other` / `absent` для существующего листа |

**Правка (одно решение в одном месте).** Новый модуль `src/conductor/command/long_path.py`,
`extended(path) -> str`: абсолютный путь в форме `\\?\` (`\\?\UNC\` для сетевого). Это перенос
`login_relay._long`; каждый обход дерева, доступного ребёнку, начинает с него, а дальше дети
наследуют форму от `os.scandir`. Проверки уборки не менялись ни в одной строке (портал, reparse,
`nlink`, предел записей, «изменилось во время уборки», identity четырёх корней).

**Вторая причина, найдена ревью Opus и подтверждена (итерация 2).** `login_relay._long` (а за ним
и моя первая `extended`) вызывал `os.path.abspath` **до** проверки префикса. `abspath`
(`GetFullPathNameW`) чистит имя и в форме `\\?\`: срезает хвостовые точки и пробелы (`foo ` и
`foo.` → `foo`, `...` и `.. ` → родитель, `a.\b` → `a\b`; `a \b` и `a..\b` сохраняются; замер
`tests/test_long_path.py`). Имя, которое отдал листинг (`os.scandir` на расширенной базе возвращает
имена как они стоят), превращалось в имя другой записи. Следствия: `take_back` убирал запись
оператора и докладывал успех; junction `foo ` рядом с папкой `foo` проходила проверку портала как
эта папка; папка `...` читалась как родитель. Правка наименьшая и в той же причине (имя, которое
продукт передаёт ОС): (а) `extended` возвращает имя с префиксом как есть, **до** очистки; очищается
и получает префикс один раз имя без префикса от вызывающего; (б) `login_home.take_back` называет
**home** в расширенной форме и присоединяет к нему измеренное имя как есть (`_take_one(home, name)`;
вызов внутри прежнего `try`, поэтому «не бросает» сохранено).

**Третья причина того же класса, найдена проверкой Opus и подтверждена (итерация 3).**
`harness_workspace.sweep_homes` перечислял корень домиков в обычной форме
(`sorted(homes.iterdir())`), а каждое имя из листинга потом шло через `_leaf` и `_remove_tree`, то
есть через `extended` → `abspath`: имя без префикса чистится. Папка ребёнка `...`, `.. ` или ` `
читалась как сам корень домиков, и `_remove_tree` стирал весь корень `.claude-home` вместе с
записью-не-домом (её продукт обещал назвать и оставить) и junction, а возврат был `()`. Папка
`h.`/`h ` читалась как `h`, которой нет, и молча оставалась. Junction `attempt-1 `/`attempt-1.`
рядом с настоящим домом читалась как этот дом и не называлась (старый дефект с той же причиной,
на HEAD так же: проба проверяющего `sweep_junction_*-head.log`; для `...`, `.. ` и ` ` на HEAD
`OSError WinError 145` и ничего не удалено, `sweep_dd-head.log`). Правка наименьшая, в той же
причине: корень перечисляется как `Path(extended(homes))`, имена приходят с префиксом и уходят в
`_leaf` и `_remove_tree` как есть. Проверки (`portal_violation`, «не папка» → назвать и оставить)
не менялись. Остальные листинги `src` просмотрены поиском: больше нигде листинг в обычной форме не
кормит `_leaf`, `_remove_tree` и `extended` именами из папки, куда пишет ребёнок (раздел «Обходы
деревьев»).

**Мелкое в том же месте (итерация 3).** `extended` принимал форму устройства `\\.\X` за сетевую
(`\\?\UNC\.\X`, то есть «шара `.`»). Форма устройства возвращается без префикса, как её даёт
`abspath` (чистое имя — без изменений; ветка `//./` тоже).

Что **не** делалось (§10.2): ни перехвата `OSError` с продолжением, ни skip, ни повтора, ни
ослабления проверок, ни смены `LongPathsEnabled`, TEMP ребёнка или раскладки папок.

## Изменения

| Файл | Что | Связь с целью |
| --- | --- | --- |
| `src/conductor/command/long_path.py` (**новый**, 37 строк) | `extended`: имя с префиксом возвращается как есть, форма устройства `\\.\X` — без префикса, остальное очищается и получает префикс | одно решение для всех обходов; ревью К1–К3, проверка П2 |
| `adapters/process_acl.py` (+2/−1) | `os.scandir(extended(here))` в `_walk_plain` | п.1 и п.3: `_empty_owned`, `retire`, `recover` (`conduct ownership recover-containers`) идут через неё |
| `adapters/harness_workspace.py` (+6/−3, 794 строки) | `_remove_tree` начинает с `Path(extended(root))`; `_leaf` → `os.lstat(extended(path))`; `sweep_homes` перечисляет `Path(extended(homes))` | п.3: `discard_home`, `sweep_homes`, `login_home.take_back`; evidence больше не слышит «нет» про глубокий файл; проверка П1 |
| `adapters/work_seed.py` (+9/−1) | четыре обхода начинают с `Path(extended(base))` | п.4: `digest_work_tree`, `read_work_tree`, `capture_work_tree`, `work_modes` |
| `adapters/login_home.py` (+10/−4) | `_walk`; `take_back` → `_take_one(home, name)`: home в расширенной форме, имя присоединено как есть | п.5: каталог входа, куда пишет запуск вендора (`measure`, `take_back`); ревью К1 |
| `adapters/login_relay.py` (+5/−12) | `_long` убран, `discard`/`sweep` зовут `extended`; `read_leaf` — тоже | п.2 |
| `adapters/relay_home.py` (+3/−2) | `leaf_kind` | п.2 («чтение листа») |
| `tests/test_login_relay_leaf.py` (+2/−1, **существующий**) | заглушка `os.lstat` в `as_the_os_words_it` сравнивает имя без префикса `\\?\` | `read_leaf` теперь называет файл в расширенной форме; три теста (симлинк, reparse, подмена между lstat и open) иначе не получали подменённого ответа ОС. Проверка продукта не менялась, меняется только шов теста; шов сохранил силу (мутант D14 на этом файле: 2 failed) |
| `tests/_deep_tree.py` (**новый**, 140) | дерево глубже 260 через `\\?\`, junction, hard link, предусловие длины; `odd_name` (имя с хвостовой точкой/пробелом как оно написано), `without_long_paths` (любая машина отвечает «нет» обычному имени от N символов), `reads_as_another`; `named`/`standing` не чистят имя, уже имеющее префикс (проверка П3) | общий помощник тестов |
| `tests/test_long_path.py` (**новый**, 123) | 18 тестов: `extended` (в том числе имя с префиксом не чистится повторно; форма устройства), самопроверка помощников `without_long_paths` и `named`/`standing`, охрана уборщика тестов | помощник; К1, Д3, П2, П3 |
| `tests/test_long_path_attempt.py` (**новый**, 401) | 23 теста папки попытки и восстановления (в том числе два, перенесённые из тестов проверяющего: имена `...`/`.. `/`foo.`/` ` и junction `foo ` в глубоком остатке старого формата) | п.1, п.3; К3, Д2, Д3, П1 |
| `tests/test_long_path_homes.py` (**новый**, 517) | 38 тестов домиков, входа, рабочей копии, relay (в том числе семь на `sweep_homes`: пять имён в корне и junction `attempt-1 `/`attempt-1.`) | п.2–п.4; К1, К2, Д3, П1 |
| `tests/test_long_path_native.py` (**новый**, 241) | 10 нативных тестов в настоящем AppContainer (не менялся) | п.3 |

`process.py` не менялся (800 строк). Лимиты: файлы ≤ 800 (`harness_workspace.py` 794), строки ≤ 100
во всех новых и изменённых строках, хвостовых пробелов, CR, BOM нет, ровно один `\n` в конце
(проверено скриптом `work\lp3\limits.py`; отчёт — `work\lp3\mdlimits.py`). Строки > 100 в
`process_acl.py` (65, 70, 182, 211, 265, 312, 322, 328, 340) и `login_home.py` (564; в итерации 2
здесь стояло 561, номер сдвинулся от правок итерации 1) были до задачи и не тронуты: каждая из
этих десяти строк есть на HEAD с тем же текстом (`work\lp3\longlines.py`, сверка с
`git show HEAD:`), новых длинных строк в файлах `src` нет.

### Решение по п.4 (рабочая копия): обработать, не отказывать

Глубокий путь в `work/<item>` читается через `extended`, закрытый отказ не вводился. Основания:
(а) путь допустим для ОС и для ребёнка, это не нарушение; (б) отказ потерял бы результат шага из-за
одного служебного файла вендора; (в) `_leaf` отвечал «нет» про существующий глубокий файл
(измерено красной фазой: `absent_result_paths` не отвергал сообщённое удаление файла, который
стоит), то есть доказательство могло врать в сторону «файла нет»; (г) отказ потребовал бы нового
кода отказа в API без пользы. Поведение закреплено тестами: дайджест, листинг, захват и режимы
содержат глубокие файлы; портал и вторая жёсткая ссылка на глубине отмечены своим видом и не
читаются; захват с ними — `CaptureRefused("irregular_result")`; сообщённое удаление файла, который
глубоко ещё стоит, отвергается (`absent_result_paths`). Граница: путь длиннее предела Windows
(32 767) по-прежнему даёт `OSError`, как и раньше. `containment` не менялся: он классифицирует
результаты `lstat` и ходит по маршрутам, выбранным продуктом (см. п.5).

## Обходы деревьев, в которые пишет ребёнок (п.5)

Исправлено (ребёнок пишет, глубина достижима): `process_acl` (parent/runtime/work/login попытки),
`harness_workspace` (homes: `discard_home` и листинг корня в `sweep_homes`), `login_home`
(`measure`, `take_back` — каталог входа вендора), `work_seed` (рабочая копия), `login_relay`
(relay-home: `discard`, `sweep` уже были на `\\?\`).

**Поиск листингов в обычной форме, которые кормят имя ОС (итерация 3, проверка П1).** Вопрос:
есть ли, кроме `sweep_homes`, место, где имя из листинга без префикса идёт в `_leaf`,
`_remove_tree` или `extended` (где `abspath` почистил бы его как другое имя). Поиск по `src`:
`\.iterdir\(|os\.scandir\(|os\.listdir\(|os\.walk\(|\.glob\(|\.rglob\(` — **51 вхождение в 30
файлах**, каждое прочитано. Результат: **такое место одно — `sweep_homes`** (исправлено; проверяющий
утверждал то же). Остальное:

- обходы, которые начинаются с имени в расширенной форме, а дальше берут имена из листинга как
  есть (`entry.path`, `row.path`, `Path(row.path)`): `harness_workspace._remove_tree`, `work_seed`
  ×4, `login_home._walk`/`_children`/`_descend`, `process_acl._walk_plain`, `login_relay`
  `_remove_tree`/`discard`/`sweep` (в `sweep` имена ещё и фильтруются `kind-16hex`);
- листинги, у которых имя не уходит в ОС: `process_acl._empty_owned` (`os.scandir(parent)`: имя
  только сравнивается с `{work, runtime, login}`), `login_home.entries` (только множество имён),
  `login_relay._relay_refusal` (только «не пусто»);
- листинги с именами по шаблону, который делает продукт (`.relay.<hex>.tmp`, `acl-<attempt>.json`,
  `kind-<16 hex>`, имена хуков из `HOOK_NAMES`): `relay_home._sweep`, `process_acl._records`/
  журнал, `process_loans`/`process_profile` журналы, `process_loans._refuse_hooks` — имя с
  точкой или пробелом в конце такой шаблон не пропускает;
- обход, где имя из листинга уходит в ОС в обычной форме, но пишет туда только продукт или
  оператор: `relay_home._entries_refusal` (`home / name` → чтение DACL настоящего входа; один класс
  с `sweep_homes`, но чтение и вход не пишет ребёнок), `containment.unowned_paths`/
  `owned_file_violations` (папка запуска `RunStore`);
- обход, где то же верно и в другом виде: `ownership_transition._inventory` (открытый вопрос 6);
- хранилища и службы продукта (`accept_*`, `studio_routes`, `task_store`, `template_store`,
  `run_store`, `ownership*`, `boot_prepared`, `hub/*`, `server`/`store`/`supervisor`, `seed_stage`,
  `git_setup_*`, `workflow_draft`): имена делает продукт, ребёнок в эти папки не пишет.

Названо и **не менялось**, с причиной:

| Место | Почему не менялось |
| --- | --- |
| `relay_home._sweep` (папки `.relay.*.tmp`) | пустые папки продукта в `DecemberCommand`; длину задаёт раскладка продукта, не ребёнок |
| `relay_home._entries_refusal`, `login_side_refusal` | читают DACL верхних записей настоящего входа; ребёнок туда не пишет (`LOGIN_LOAN_OPEN` закрыт) |
| `login_relay._relay_refusal`, `copy_in`, `_write_exclusively` | пустой relay-home до старта ребёнка, имена фиксированной длины |
| `containment` (`_walk_directory_route`, `first_directory_violation`, `lstat_or_none`, `unowned_paths`) | маршруты выбирает продукт; `unowned_paths` ходит по папке запуска `RunStore`, где пишет только продукт; обход рабочей копии — в `work_seed` |
| `seed_stage._remove_entry`, `_hold_free` | промежуточная копия seed (файлы под git), создаётся продуктом до ребёнка |
| `ownership_transition._inventory` | maintenance-инвентарь `activate`/`rollback` при остановленных писателях. **Уточнено по ревью (К6, подтверждено замером):** `os.walk` с `onerror` по умолчанию молча ничего не перечисляет для папки с обычным путём 256–259 символов (`lstat` проходит, `scandir` падает), то есть содержимое такой папки **выпадает из инвентаря без отказа**, а не отвергается; ниже 256 и от 260 (там `lstat` падает) картина иная. Дефект старый, путь обслуживания; в задачу не входил. Открытый вопрос 6 |
| `hub/clone_cleanup`, `projects_add._walk`, `process_loans` (`os.listdir(login)`) | клоны git и обзор проекта до запуска; верхний уровень каталога входа |

## Проверки

Окружение: `. …\December-Command-Environment.ps1 -Quiet`, Windows 11, Python 3.12.14, venv
репозитория; `--basetemp` — несуществующий `C:\Users\Пользователь\<ровно 4 символа>`, свой на
каждый прогон, после прогона удалён через `\\?\`. Логи и скрипты вне репозитория:
`Documents\Codex\work\lp\` (итерация 1), `lp2\` (итерация 2) и **`lp3\` (итерация 3, итоговые
числа ниже)**. Итоговое дерево: 8 `M` и 7 `??` (как в начале итерации, новых файлов в репозитории
нет), `git diff --check` чисто, лимиты строк и файлов — `work\lp3\limits.py`.

| Команда | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| `pytest tests/test_long_path.py tests/test_long_path_attempt.py tests/test_long_path_homes.py` | UTF-8 (`PYTHONUTF8=1`, `utf8_mode=1`) | **79 passed** (18 + 23 + 38) | новые обычные тесты на итоговом коде; лог `work\lp3\final-new-utf8.log` |
| то же | cp1251 (`Remove-Item Env:PYTHONUTF8, Env:PYTHONIOENCODING`, `utf8_mode=0`) | **79 passed** | то же в кодировке владельца; лог `final-new-cp1251.log` |
| `pytest tests/test_long_path_native.py` (один процесс; итоговое дерево итерации 3) | UTF-8 / cp1251 | **10 passed** / **10 passed** | настоящий AppContainer, глубокие деревья, выход, восстановление; логи `native-utf8.log`, `native-cp1251.log` |
| native соседние файлы, по одному на процесс, последовательно (UTF-8 / cp1251): `test_login_relay_native` 2/2, `test_process_acl_mutex_native` 5/5, `test_process_acl_native` 1/1, `test_process_loans_native` 8/8, `test_process_login_config_native` 4/4, `test_process_login_native` 15/15, `test_process_login_native_overlap` 10/10, `test_process_native_boundary` 6/6, `test_relay_home_native` 32/32, `test_policy_native_feedback` 4/4 | оба | **все passed**, 0 failed, 0 skipped | десять соседних native-файлов не сломаны; `test_relay_claude_native` и `*_real_smoke` **не запускались** (живой Claude/Codex, запрещено); `HKCU\…\AppContainer\Mappings` и `%LOCALAPPDATA%\Packages` до и после — те же три `conduct-*` (B1 и два остатка итерации 1), новых нет (`work\lp3\profiles.ps1`) |
| затронутые обычные наборы итерации 3: 104 файла (3 178 тестов) (`work\lp3\affected.txt`: тесты, где встречаются `sweep_homes`, `harness_workspace`/`HarnessWorkspace`, их вызывающие `independent_transport`, `relay_attempt`, `subscription_quota`, `kimi_code`, `long_path`, `login_relay`, `login_home`, `relay_home`, `work_seed`, `process_acl`, плюс `test_command_line_cap`, `test_command_adapters`, `test_command_package_doors`, `test_command_import_hygiene`, `test_login_relay_leaf`, `test_login_relay_discard`; без native-файлов), один процесс | UTF-8 | **3 156 passed, 22 skipped**, 0 failed (21 мин 47 с; лог `work\lp3\affected-utf8.log`) | регрессии в harness, work_seed, login, relay, process_acl, door-guard, `CAPPED`, охрана импортов адаптеров, лимиты строк |
| то же | cp1251 | **3 156 passed, 22 skipped**, 0 failed (21 мин 58 с; лог `affected-cp1251.log`) | то же в кодировке владельца |
| 22 skipped, одинаково в обеих кодировках: 16 × `WinError 1314` (нет права на симлинк) в `sabotage_fixtures`; по одному в `test_seed_move` ×2 (симлинк, ссылка), `test_projects_add` (симлинк каталога), `test_command_product_names` (симлинк); «Windows не выводит режим Git из chmod» (`test_accept_capture:287`); `test_execution_boundary:114` | UTF-8 и cp1251 (`-rs`) | не зависят от изменения | вариант с симлинками на этой машине не исполнялся; junction/hard link исполнялись |
| `pytest tests/test_login_relay_leaf.py tests/test_login_relay_discard.py` | UTF-8 / cp1251 | входят в набор выше; 54 passed / 54 passed в итерации 1 | шов `as_the_os_words_it` подаёт подменённый ответ ОС и после правки |

Набор итерации 3 уже, чем 160 файлов итерации 2 (`work\lp\affected-all.txt`, 4 814 тестов, там
4 856 passed, 25 skipped в UTF-8 и 4 857 passed, 25 skipped в cp1251): в итерации 3 код менялся
в двух местах (`sweep_homes` и ветка формы устройства в `extended`) и в помощнике тестов, поэтому
набор — файлы, которые зовут `HarnessWorkspace`, его вызывающих и `long_path`, плюс перечисленные
в задании охранные тесты; остальные файлы из 160 этих мест не вызывают и в итерации 3 не
прогонялись. Полный core **не запускался** (его делает ведущий на финальном коммите).

## Красная фаза (§3)

**На неизменённом `src` HEAD** (равен `bc61db8`). Копия `git archive HEAD src` в
`Documents\Codex\work\lp3\red` (после работы удалена); `PYTHONPATH` и `conductor.__file__` — из
копии (первая строка логов `red-head-ah-utf8.log`, `red-head-ah-cp1251.log`); итоговые тесты —
поверх неё; `--basetemp` из 4 символов.

| Набор | Результат | На чём падает |
| --- | --- | --- |
| `test_long_path_attempt.py` + `test_long_path_homes.py` (61 = 23 + 38) | **53 failed, 8 passed**, в обеих кодировках | см. разбор ниже; те же 8 зелёных, что в итерации 2, а 44 красных итерации 2 — среди 53 (сверка списков `FAILED`: пусто в обе стороны), плюс девять новых тестов итерации 3 |
| `test_long_path.py` (18) | ошибка сбора: `ModuleNotFoundError: conductor.command.long_path` | не на сравнении; ожидаемо (помощник — перенос `login_relay._long`, на HEAD его нет) |
| `test_long_path_native.py` (10) | **5 failed, 5 passed** (UTF-8; итерация 1, **не пересчитывалась**: файл и `src` HEAD не менялись, а `named`/`standing` в нём зовутся с именами без префикса и без `...`/хвостовых точек) | выход из boundary: `ProfileRefused … unreadable` (тот же отказ, что в B1); папка попытки осталась; профиль в ОС остался; журнал `acl=applied`, `profile=created`; recover после рестарта не убирает |

**Разбор 53 падений** (`--tb=line`, `work\lp3\classify.py` и `pair.py`; тот же счёт в UTF-8 и
cp1251). Итоговые тесты итерации 3: **31 падает исключением-симптомом, 22 — сравнением**:

- исключение-симптом (31): 10 × `OSError WinError 145`, 9 × `ProfileRefused: owned attempt is
  unreadable` (симптом B1), 7 × `FileNotFoundError WinError 3` и 4 × `WinError 2` (глубокие записи
  для ОС «нет», затем `rmdir`/`lstat`/`iterdir` падают), 1 × `KeyError` (junction `foo ` не
  записан в доказательства). Это сам дефект: B1 и п.4 задания — исключение, теряющее результат. Тест
  не оборачивается в `try/except`, чтобы получить «сравнение»: это было бы прикрытием (§10.2).
  Стандарт §3 («падает на сравнении») здесь выполнен там, где у дефекта есть значение для
  сравнения, и не выполнен там, где дефект — исключение; **это названо отклонением от буквы §3,
  не скрыто**;
- сравнение (22): 7 × `Regex pattern did not match` (ожидаемый отказ не совпал: вместо
  `portal or irregular entry`, `changed during cleanup`, `exceeds cleanup bound` приходит
  `unreadable`), 14 × `AssertionError` с названием (измерение потеряло глубокие имена, имя
  оператора и спавна смешаны, `what is not a home was named as ()`, `a portal in the homes root was
  named as ()`, виды листа и т.п.), 1 × `DID NOT RAISE WorkspaceNotContained`.

**Поправка к итерации 2 (находка П4, подтверждена скриптом).** Итерация 2 писала «27 исключений / 17
сравнений» на 44 теста, проверка Opus — 24/20. Скрипт `classify.py` на логе итерации 2
(`work\lp2\red-utf8.log`) и на логе проверяющего (`work\lp-v3-op55\red-ah-utf8.log`) даёт
**24 исключения (8 `ProfileRefused`, 7 `OSError 145`, 4 `FileNotFoundError WinError 2`, 1 `WinError
3`, 3 `KeyError`, 1 `CaptureRefused`) и 20 сравнений (6 `Regex`, 13 `AssertionError`, 1 `DID NOT
RAISE`)**: проверка права, счёт итерации 2 был неверен для того лога. **Но и 27/17 не выдумка:**
вид падения шести тестов рабочей копии (дайджест, листинг, захват, junction, второе имя,
«машина с длинными путями» для дайджеста) зависит от длины basetemp. Лог итерации 2 получен с
basetemp из 5 символов (`lq5ru`), у проверяющего тоже 5 (`vqr1u`); при 4 символах (как требует
стандарт) путь папки 7-го уровня дерева — 259 символов (длина по расчёту, не замером), `lstat` его
проходит, листинг нет, и те же шесть тестов падают `FileNotFoundError WinError 3` (все шесть —
исключения), а при 5 символах тот же уровень — 260, `lstat` отвечает «нет», обход молча
пропускает папку и тесты падают на сравнении или `KeyError`/`CaptureRefused` (измерено сверкой
по тестам, `pair.py`: из 44 тестов различается вид у этих шести, у остальных 38 он тот же). Для
тех же 44 тестов при 4 символах счёт 27/17 (31 − 4 и 22 − 5: девять новых тестов дают 4
исключения и 5 сравнений, измерено построчно), при 5 символах — 24/20. Итоговый счёт для сдачи —
**31/22 на 53 теста при basetemp из 4 символов**; зависимость вида падения от длины пути отмечена
здесь, чтобы следующий пересчёт не принимали за расхождение.

Зелёные на старом коде (8 + 5) названы честно:

- обычные: `sweep` (два теста) и `discard` с junction в relay-home на глубине (их `\\?\` уже стоял
  в `login_relay`; мутанты B11, B12, C7, C8 их красят); контроль «несуществующее имя остаётся
  absent»; контроль «удаление уже удалённого глубокого файла принято»;
  `test_the_bound_counts_the_folder_the_walk_begins_at` (свойство предела, не длины);
  `test_a_folder_that_is_not_the_one_the_record_names…` (проверка identity стоит до обхода и не
  менялась; мутант D16 её красит); **`test_a_folder_the_system_will_not_list_refuses_the_cleanup…`**
  (новый страж уже существующего отказа «owned attempt is unreadable»; он нужен против прикрытия,
  мутант R2 его красит);
- native: ребёнок сделал дерево (предусловие), DACL как были, relay-home убирает `discard`,
  `a_cut_short_exit…` (предусловие остатка), `without_a_restart…` (отказ без доказательства
  сохраняется).

**На коде до правки ревью итерации 2** (`extended` чистит и имя с префиксом, `_take_one` называет
склеенный путь; остальной `src` итоговый, в том числе листинг `sweep_homes`;
`work\lp3\make-prefix-copy.py`, копия `work\lp3\prefix` после работы удалена): итоговые 79 тестов,
**24 failed, 55 passed** в обеих кодировках (`red-prefix-utf8.log`, `red-prefix-cp1251.log`; в
итерации 2 на 68 тестах было 15/53). Красные — тесты находок К1–К3 и П1–П2: 5 из 7 проверок
`extended` (`foo `, `foo.`, `...`, `.. `, `a.\b`; `a \b` и `a..\b` зелёные, как в замере ревьюера) и
проверка формы устройства (в этой копии ветки `\\.\` нет), 3 уборки попытки с `...`/`foo.`/`foo `
и глубокий остаток старого формата с такими именами, `discard_home`/`sweep_homes` с junction `foo `
(удалён файл за junction), семь тестов `sweep_homes` итерации 3 (в этой копии `_leaf` чистит имя с
префиксом, и листинг в расширенной форме не помогает), 3 `take_back` (`a `, `a.`, `...`: файла
оператора нет), рабочая копия с junction `foo ` (`KeyError`), измерение входа с junction `foo `
(прошло насквозь). Зелёные на этом коде: оба других параметра `extended`, самопроверка помощников,
три теста «машина с длинными путями» (глубокая уборка на этом коде уже работает, только имена с
точкой/пробелом читаются не так), страж «unreadable», junction `foo ` в уборке попытки и в
остатке старого формата (после первой итерации `_walk_plain` уже смотрел литеральный `entry.path`;
на HEAD этот тест красный).

**На коде итерации 2 до правок итерации 3** (`work\lp3\make-copies.py`, копия `work\lp3\iter2`,
после работы удалена:
`sweep_homes` листает корень в обычной форме, ветки `\\.\` в `extended` нет; тесты итоговые, в том
числе итоговый `_deep_tree.py`): 79 тестов, **8 failed, 71 passed** в обеих кодировках
(`red-iter2-utf8.log`, `red-iter2-cp1251.log`): форма устройства, пять случаев имён в корне домиков,
два случая junction `attempt-1 `/`attempt-1.`. Девятый красный итерации 3 — тест помощников
`named`/`standing` — красен только на помощнике итерации 2: первый прогон новых тестов на рабочей
копии до правок (`work\lp3\red-cur-utf8.log`, `test_long_path.py` + `test_long_path_homes.py`) дал
**9 failed, 47 passed** (форма устройства, помощник, пять имён, два junction), все девять на
сравнении (`AssertionError`). Два перенесённых теста остатка старого формата зелёны и на коде
итерации 2 (они страхуют путь восстановления от возврата к ошибкам К1–К3); на HEAD оба красные.

## Нативный свидетель

`tests/test_long_path_native.py` (сценарий `test_relay_home_native.py`, PowerShell из System32,
`RelaySite`): ребёнок в настоящем AppContainer создаёт дерево глубже 260 символов через `\\?\`
в своём TEMP и в relay-home и сам сообщает длину (в отладочном прогоне вне pytest: TEMP — 496,
relay — 402 символа; тест требует > 260). Выход из boundary проходит; папка попытки убрана;
`inspect_profile(sid)` → `None`; журнал `{profile, acl, loan}` = `retired`; DACL всех мест как
были; relay-home с глубоким деревом убирает `login_relay.discard`. Живая модель и вендор не
участвуют. Файл в итерациях 2 и 3 не менялся; прогоны повторены на итоговом дереве итерации 3
(10 passed в UTF-8 и в cp1251, один файл на процесс; лог `work\lp3\native-utf8.log`,
`native-cp1251.log`).

Факт, который изменил тест: **TEMP ребёнка не равен переданному `TEMP`** — система кладёт его в
`runtime\Packages\<имя>\AC\Temp`, как и в B1 (проверено списком `runtime`); поэтому тест ищет
`log.txt` под `runtime`, а не по переданному пути.

Восстановление (`tests/test_long_path_native.py`, второй сценарий): выход обрезан (`retire`
поднимает исключение, как при сбое) — папка попытки с глубоким TEMP и профиль стоят, запись `acl`
`applied`; `recover_containers(--dir)` **без** перезапуска → код 1, `profile_acl_unproven`, папка на
месте; с «следующим запуском ОС» (`later_boot`) → код 0, папка и профиль убраны, записи `retired`,
DACL как были. Остаток старого формата (запись до счётчика загрузки, схема 1) — обычный тест
`test_a_leftover_of_the_old_format_with_a_deep_tree_is_recovered_only_on_the_proofs`: не в своей
загрузке, не после рестарта без подготовки, не после подготовки без рестарта — отказ и ничего не
тронуто; после подготовки и рестарта глубокая папка убрана. Тот же сценарий с глубоким остатком,
где рядом лежат имена `...`, `.. `, `foo.`, ` `, `foo` (каждое убирается как оно стоит), и со
вторым остатком, где рядом с папкой `foo` стоит junction `foo ` (после всех доказательств
восстановление отказывает «portal or irregular entry» и ничего не трогает), добавлен в итерации 3
(два теста проверяющего, перенесённых в `test_long_path_attempt.py`). Настоящий остаток B1 в
тестах не использовался.

## Мутанты (§3, §10.3)

Копия `src`, `tests`, `pyproject.toml` в `Documents\Codex\work\lp3\mut` (после работы удалена),
`PYTHONPATH` на её `src`, `conductor.__file__` — из копии (первая строка лога `mutants-utf8.log`);
копия сверена с рабочей по SHA-256 каждого файла (0 расхождений); M0 без изменений: **79 passed**.
`--basetemp` каждого прогона — своя папка из 4 символов (`m001`…), стёрта после прогона. Мутанты
пересчитаны **заново, все 58**, на итоговых тестах (79): 52 прежних, пять новых (E1–E5) и один
новый для помощника тестов (T2). **Мутант, переживший новые тесты в файле, который был до задачи,
прогоняется ещё на существующих наборах, которые этот файл покрывают** (ревью К5/Д1): M0 этих
наборов — `harness_workspace` 124 passed, 13 skipped (4 файла); `login_home` 123 passed (3 файла);
`login_relay` 133 passed (3); `process_acl` 63 passed (3); `relay_home` 129 passed (3);
`work_seed` 138 passed, 14 skipped (5); `long_path` 146 passed, 1 skipped (4). После каждого
мутанта файл возвращён и его SHA-256 сверен с исходным (**58 из 58 — `restored: True`**; скрипт
останавливается при расхождении). Скрипты и результаты вне репозитория: `work\lp3\mutate3.py`,
`mutants-utf8.json`, `mutants-utf8.log`, `table3.py`. Native-мутанты (A1, A2, B1, C1, C2 из
итерации 2) **не пересчитывались**: `test_long_path_native.py` и мутируемые ими места в итерации 3
не менялись, а новые мутанты native не затрагивают (6 / 6 / 5 / 5 / 5 failed при M0 10 passed —
результат итерации 2). Внешние `crapper`/`dryer`/`mutator` (§10.9) не использовались: свой скрипт
замен текста.

**SHA-256 восстановления.** Скрипт сверяет файл с исходным после каждого мутанта (58 из 58 —
`restored: True`). Сверх этого после всех мутантов копия `work\lp3\mut` сверена с рабочей копией
репозитория по SHA-256 каждого из 1 327 файлов `src` и `tests`: **0 расхождений**. Восемь
мутируемых файлов (первые 16 знаков SHA-256; в копии и в репозитории одни и те же):

| Файл | SHA-256 (начало) | Мутанты |
| --- | --- | --- |
| `src/conductor/command/long_path.py` | `AB468E0B7E906D57` | A1–A4, E3 |
| `src/conductor/command/adapters/process_acl.py` | `93E04A846C93098B` | B1, C1, C2, D1–D6, D16, R2 |
| `src/conductor/command/adapters/harness_workspace.py` | `2C195E0C1F430FE0` | B2, B3, C3, C4, D7, E1, E2, E4, E5 |
| `src/conductor/command/adapters/work_seed.py` | `3B3C69016EC917CF` | B4–B7, C9–C12, D8–D11 |
| `src/conductor/command/adapters/login_home.py` | `BB0A3EE276091D99` | B8, B9, B9b, C5, C6, D12 |
| `src/conductor/command/adapters/login_relay.py` | `7557381BDF951BD7` | B10–B12, C7, C8, C13, D13, D14, D17 |
| `src/conductor/command/adapters/relay_home.py` | `D4983FBA71B20A60` | B13, B14, C14, D15 |
| `tests/_deep_tree.py` | `82047359F87C7DC2` | T1, T2 |

| Мутант | Результат | Что красное |
| --- | --- | --- |
| A1 `extended` возвращает путь как есть (пустая реализация) | 63 failed, 16 passed | почти все тесты глубины и имён, unit-тесты помощника |
| A2 `extended` ничего не возвращает | 74 failed, 5 passed | то же |
| A3 `extended` без `abspath` | 3 failed | unit: `..`/`/`, относительный путь, форма устройства `//./` |
| **A4** `extended` чистит и имя с префиксом (причина К1) | **23 failed**, 56 passed | 15 тестов К1–К3 и 8 новых: имена в корне домиков (пять), junction `attempt-1 `/`attempt-1.` (два), глубокий остаток старого формата с такими именами |
| B1 `\\?\` снят в обходе папки попытки | 20 failed | retire×3, walk, recover, legacy, портал/hard link, changed×2, bound×3, `...`/`foo.`/`foo `, junction `foo `, два остатка старого формата с именами |
| B2 снят в `_remove_tree` | 5 failed | discard_home ×2, junction, второе имя, junction `foo ` (в `discard_home`); `sweep_homes` теперь отдаёт `_remove_tree` имя с префиксом, и этот мутант его не задевает: его красят E1–E5 |
| B3 снят в `_leaf` | 1 failed | сообщённое удаление, где глубокий файл ещё стоит |
| B4 / B5 / B6 / B7 снят в work_seed: capture / modes / digest / listing | 4 / 2 / 5 / 3 failed | capture, modes, digest, listing, портал, второе имя, junction `foo ` |
| B8 снят в `login_home._walk` | 5 failed | измерение, добавленный файл, `take_back` с `a.`, junction глубоко и junction `foo ` |
| B9 снят в `take_back` (home без префикса) | 4 failed | файл, добавленный в глубокую папку, не убран; `take_back` с `a `, `a.`, `...` |
| **B9b** `take_back` называет склеенный путь (причина К1, место вызова) | **3 failed** | `take_back` с `a `, `a.`, `...`: файл оператора убран |
| B10 снят в `read_leaf` | 2 failed | глубокий лист, второе имя |
| B11 / B12 снят в `login_relay.discard` / `sweep` | 1 / 1 failed | junction на глубине; relay-корень глубже 260 |
| B13 / B14 снят в `leaf_kind` (дом / лист) | 1 / 1 failed | глубокий relay-home |
| C1 `_empty_owned` ничего не делает | 20 failed | retire, recover, legacy, портал, bound, changed, имена, страж «unreadable», два остатка с именами |
| C2 `_walk_plain` возвращает `[]` | 22 failed | то же + walk, предел |
| C3 `_remove_tree` ничего не делает | 19 failed | discard_home, junction, второе имя, sweep_homes (старые три и семь новых), `take_back`, junction `foo ` ×2 |
| C4 `_leaf` отвечает «нет» всегда (пустое чтение; бывший R1 ревью) | 30 failed | уборка, домики, `sweep_homes`, обходы work_seed, измерение, `take_back` |
| C5 / C6 `login_home._walk` и `take_back` ничего не делают | 7 / 5 failed | measure, take_back, имена с точкой/пробелом |
| C7 / C8 `discard` / `sweep` ничего не делают | 3 / 2 failed | sweep, junction, relay-корень |
| C9 / C10 / C11 / C12 work_seed ничего не возвращает | 5 / 3 / 4 / 2 failed | digest, listing, capture, modes |
| C13 / C14 `read_leaf` / `leaf_kind` ничего не делают | 2 / 1 failed | лист, виды листа |
| D1 / D2 проверка reparse / `nlink` в `_walk_plain` снята | 3 / 1 failed | портал/hard link на глубине (D1 ещё junction `foo ` и junction в остатке старого формата) |
| D3 / D4 проверки предела снята (по списку / при чтении) | 1 / 1 failed | «предел считает начальную папку»; «предел останавливает чтение широкой глубокой папки» |
| D5 / D6 проверка «изменилось во время уборки» (`nlink` / reparse) снята | 1 / 1 failed | changed[second name], changed[junction] |
| D7 портал в `_remove_tree` снят | 3 failed | junction в домике (иначе удалён `kept.txt` за порталом), junction `foo ` ×2 |
| D8 / D9 / D10 / D11 портал / второе имя в work_seed снято | 2 / 1 / 2 / 2 failed | digest, capture, listing |
| D12 портал в `login_home._descend` снят | 2 failed | junction под объявленной папкой; junction `foo ` |
| D13 `_is_link` в `login_relay._remove_tree` снят | 1 failed | junction в relay-home |
| **D14** `_plain(before)` в `read_leaf` снят | **79 passed на новых тестах — пережил; на существующих `test_login_relay_leaf` и др.: 2 failed** | `test_a_symlink_standing_where_the_file_should_be_is_refused`, `test_a_file_behind_a_reparse_point_is_refused` |
| D15 `nlink` в `leaf_kind` снят | 1 failed | вид листа |
| D16 проверка identity папки (`identity(path)` против записи) в `_verified_holds` снята | 1 failed | папка подменена другой с тем же именем: отказ «identity changed» до обхода |
| **D17** проверка «файл, который держим, — тот, который видели» в `read_leaf` снята | 79 passed на новых — пережил; на существующих `test_login_relay_leaf` и др.: **1 failed** | `test_a_file_swapped_between_the_look_and_the_open_is_refused` |
| **T1** `without_long_paths` (помощник тестов) ничего не делает | 1 failed | самопроверка помощника; три теста «машина с длинными путями» зелены и под T1 (на этой машине подмена совпадает с системой; проба проверяющего показывает помощник отдельно, см. «Не проверено») |
| **E1** (итерация 3) `sweep_homes` листает корень в обычной форме (причина П1) | **7 failed**, 72 passed | ровно семь тестов `sweep_homes` итерации 3: пять имён в корне, junction `attempt-1 `/`attempt-1.` |
| **E2** (итерация 3) `sweep_homes` ничего не делает (no-op) | **10 failed** | семь новых и три старых положительных свидетеля: глубокие домики убраны, запись-не-дом названа и оставлена, junction `foo ` в `sweep_homes` |
| **E3** (итерация 3) в `extended` нет ветки формы устройства | **1 failed** | `test_a_device_name_is_not_taken_for_a_network_path_and_is_left_in_its_own_form` |
| **E4** (итерация 3) проверка портала в `sweep_homes` снята | **7 failed** | junction `door` в корне (иначе `_remove_tree` идёт через неё), junction `attempt-1 `/`attempt-1.`: не названа, не оставлена |
| **E5** (итерация 3) проверка «не папка» в `sweep_homes` снята | **6 failed** | запись-не-дом (файл) не названа и не оставлена: старый тест и пять новых |
| **T2** (итерация 3) `named` чистит и имя с префиксом (прежний помощник) | **1 failed** | `test_the_helpers_ask_about_the_name_they_are_given_not_the_folder_it_is_read_as` |
| **R2** прикрытие вместо исправления: `except OSError: continue` в `_walk_plain` | 1 failed | `test_a_folder_the_system_will_not_list_refuses_the_cleanup_and_leaves_everything`; **без этого теста R2 переживает** новые тесты и `test_process_acl*` (130 passed, 1 deselected; итерация 2, `r2-without.py`), с ним — 1 failed |
| Native: A1 / A2 / B1 / C1 / C2 (M0: 10 passed; итерация 2, не пересчитывались) | 6 / 6 / 5 / 5 / 5 failed | выход из boundary, папка, профиль, журнал, recover; новых остатков профилей нет |

**Выживших нет: 58 мутантов, все убиты** (56 — новыми тестами; D14 и D17 — существующими
`test_login_relay_leaf`, где они были убиты и в итерации 2). **D14 больше не называется
эквивалентным** (ревью К5/Д1, подтверждено): его убивают существующие тесты. Вывод итерации 1
«второй барьер даёт тот же результат» был сделан по мутанту, прогнанному только на 45 новых
тестах, и неверен. Заодно закрыт пропуск «изменённый тест-страж не прошёл через мутанты»: шов
`as_the_os_words_it` после правки по-прежнему подаёт подменённый ответ ОС (D14: 2 failed, D17:
1 failed на `test_login_relay_leaf.py`), то есть правка шва страж не ослабила.

**Пустая реализация (§10.3).** Под no-op каждой уборки (C1, C2, C3, C5–C14, E2) красны её
положительные свидетели («убрано полностью», `retired`, измерение, дайджест, вид листа, домик
убран, запись-не-дом названа) и тесты запрета, идущие через ту же функцию (портал, второе имя,
предел, «изменилось во время уборки», страж «unreadable», junction в корне домиков): ни один тест
запрета не пережил no-op своей уборки, удалять нечего. Не красны под no-op только тесты, которые
эту функцию не вызывают, и **три контроля**, которые доказывают не уборку, а границу (проверено
по спискам красных в `mutants-utf8.json`: зелёные под своим no-op C13, C4 и C1): «имя, которого
нет, остаётся absent» (`test_a_name_that_is_not_there_is_absent_at_a_deep_path_too`),
«сообщённое удаление уже удалённого глубокого файла принято», «предел считает начальную папку».
Они сохранены рядом с положительными сценариями.

## Не проверено

- Живой Claude Code и настоящие `%USERPROFILE%\DecemberCommand\…`, `DecemberRehearsal` не
  запускались и не трогались; поведение настоящего Claude на глубоком TEMP — только B2.
- Git на глубоком пути результата (`accept`, checkout, `core.longpaths`): код продукта читает
  файл, но принятие результата с путём > 260 в чужой репозиторий не проверялось (`accept_preview`
  предупреждает `long_path_checkout`). Открытый вопрос.
- Windows не закрывает Linux и macOS: на POSIX тесты глубины идут без префикса и проверяют
  поведение, не ошибку ОС; тесты имён с хвостовой точкой/пробелом на POSIX пропускаются
  (`reads_as_another`: такого чтения имени там нет).
- **Различающая сила тестов глубины зависит от машины (ревью Д3), сужено проверкой П7.** Красная
  фаза получена на машине с `LongPathsEnabled = 0` (прочитано: 0). На машине с включёнными длинными
  путями (гипотеза: Windows-раннеры CI) глубокие тесты зелёные и на старом коде. Три теста «машина с
  длинными путями» (уборка попытки, `discard_home`, дайджест рабочей копии; имена начинаются с
  `test_a_machine_that_allows_long_names_`) подменяют границу: `os.lstat`, `stat`, `scandir`,
  `listdir`, `rmdir`, `unlink` отвечают `FileNotFoundError` на обычное имя от 260 символов, и отказ
  есть на любой машине. **Измерено (проба проверяющего, повторена):** помощник сам, без
  `LongPathsEnabled`, отличает старый код от нового. Проба
  `work\lp-v3-op55\test_probe_helper.py` (SHA-256 `41C8153A…AA03`) строит дерево короче 250
  символов, которое система обслуживает в обеих формах, и понижает предел помощника под его
  глубину; три теста, каждый с помощником и без. `src` HEAD: с помощником **3 failed**
  (`ProfileRefused`, `OSError WinError 145`, `AssertionError: []`), без — **3 passed**; текущий код:
  **6 passed** (`work\lp3\probe-helper-red.log`, `probe-helper-cur.log`). Не измерено осталось одно:
  **сами** три теста (дерево глубже 260, предел 260) на машине с `LongPathsEnabled = 1`; включать
  параметр и менять настройки Windows нельзя, а на этой машине подмена совпадает с самой системой
  (три теста красны на HEAD и без неё, зелёны на коде до правки ревью — как и должны). Остальные
  тесты глубины, native и `open`/чтение файла под подмену не подведены.
- Может ли ребёнок внутри AppContainer создать junction с именем `foo ` (ограничение mount point
  песочницы): не проверено. Дорога без контейнера (домики, рабочая копия, вход) его создать может,
  и тесты К2 её закрывают.
- Полный core, CI на SHA и ревью — ведущему и Codex.

## Чужие правки

- За время работы в ветке появились документальные коммиты ведущего/Codex: `0bc240c`
  (RUN1-REPORT), `0125e15` (стандарт §10 уточнён), `c0b438d` (решение Codex о B2; дополнение
  к TASK), `fc9b118` (UX-FIRST-RUN-TASK). Код `src` не менялся.
- В рабочей копии при старте первой итерации чисто; чужие незакоммиченные документы в ходе работы
  (`OPEN-DECISIONS.md`, `H5-B-LONGPATH-TASK.md`, `H5-B-RUN1-REPORT.md`,
  `H5-B-RUN2-DECISION-REPORT.md`, `UX-FIRST-RUN-TASK.md`) к концу работы закоммичены ведущим;
  я их не правил. Во второй итерации чужих правок нет. В третьей: `tests/test_command_line_cap.py`
  (шесть новых файлов в `CAPPED`, правка ведущего) — не трогал, прогонялся в наборе.
- Чужие каталоги `work\lp-rev`, `work\lp-rev-cs5`, `C:\Users\Пользователь\rvq7` (ревьюеры) не
  трогал. Пробу и тесты проверяющего третьей итерации (`work\lp-v3-op55`, каталог `lp-v3` в
  scratchpad сессии) только читал и копировал (проба помощника прогнана в копиях `work\lp3\red` и
  `work\lp3\cur`, после работы удалены).

## Отклонения

| Что | Почему | Кто утвердил |
| --- | --- | --- |
| Помощник в `src/conductor/command/long_path.py`, не в `adapters/long_path.py` | задание говорит «например»; модуль в `adapters/` с `import os` провалил бы охрану импортов `test_command_adapters` (нужна правка списка `SDK_WORKSPACE_DOOR`), а `containment` и будущие читатели его импортировать не смогут | ведущий Opus, 27.10: принято (см. «Приёмка ведущего») |
| Правки шире п.1–3: `login_home` (п.5), `_leaf`, `read_leaf`, `leaf_kind` (п.2) | п.5 велит исправить найденные обходы; `read_leaf`/`leaf_kind` названы в п.2; `_leaf` убирает тихое «нет» для глубокого файла в доказательствах | ведущий Opus, 27.10: принято (см. «Приёмка ведущего») |
| Изменён существующий тест-шов `tests/test_login_relay_leaf.py::as_the_os_words_it` (сравнение имени без `\\?\`) | следствие `read_leaf` через `extended` (п.2 задания); альтернатива — не трогать `read_leaf` и убрать мои два теста на глубокий лист: выгода теоретическая (путь листа достигает 260 символов только при профиле владельца длиннее ~170 символов, ребёнок его не удлиняет), риск — новый шов в чтении входа; решает ведущий. Шов сохранил силу: D14 на этом файле даёт 2 failed | ведущий Opus, 27.10: принято (см. «Приёмка ведущего») |
| Native-фикстура ловит любое исключение выхода из boundary | чтобы красная фаза падала утверждением, а не ошибкой фикстуры, и профиль, оставленный выходом, убирался; исключение проверяется тестом `exit_error is None` | ведущий Opus, 27.10: принято (см. «Приёмка ведущего») |
| Часть красных падений (31 из 53 на HEAD при basetemp из 4 символов; по логу итерации 2, 5 символов, — 24 из 44) — исключение-симптом, а не сравнение (§3 требует «падает на сравнении»). Итерация 2 писала «27 из 44»; проверка Opus поправила на 24/20 по тому логу, подтверждено скриптом: счёт 27/17 относится к basetemp из 4 символов, а не к тому логу (см. «Красная фаза») | дефект и есть исключение (B1: отказ после работы ребёнка; п.4: исключение, теряющее результат); обернуть вызов в `try/except`, чтобы получить «сравнение», значит прикрыть причину (§10.2); у дефектов со значением (виды листа, измерение, отказ не тот) падение идёт на сравнении | ведущий Opus, 27.10: принято (см. «Приёмка ведущего») |
| Два теста проверяющего про остаток старого формата перенесены в `test_long_path_attempt.py` в моей форме (на общих помощниках `an_old_leftover`, `refused_until_proven`); его два теста про `sweep_homes` (пять случаев) переписаны своими (семь случаев: пять имён в корне, включая `attempt-2.`/`attempt-2 `, с записью-не-домом и junction в том же корне, и junction `attempt-1 `/`attempt-1.`; буквальный `os.path.lexists`) | свои тесты строятся на общих помощниках файла, а не на копии `fixture` проверяющего; смысл и проверяемое то же, красные на тех же кодах | ведущий Opus, 27.10: принято (см. «Приёмка ведущего») |
| Часть тестов `test_long_path_attempt.py` идёт не через публичный шов: вызывают приватную `process_acl._walk_plain` (`test_the_walk_names_every_entry…`, `test_the_bound_counts_the_folder…`) и подменяют её (`walk_then_change`) и константу `process_acl._LIMIT` (три теста предела) (ревью Д4, подтверждено) | гонку «обход увидел обычный файл — до удаления у него второе имя / он стал junction» через границу ФС не воспроизвести без привязки к числу вызовов `os.lstat` (обход зовёт `lstat` дважды на запись, затем удаление; различать вызовы можно только по типу аргумента, это хрупко); предел записей `_LIMIT` — модульная константа без публичного шва; тест предела на длинной папке старого кода зелёный (названо в красной фазе). Новые тесты второй итерации идут через `retire` и `measure`/`take_back`/`discard_home`, без приватного | ведущий Opus, 27.10: принято (см. «Приёмка ведущего») |

Статус не выше «локально проверено» до утверждения.

## Открытые вопросы

1. **Остаток двух тестовых профилей AppContainer.** Первый прогон нативных мутантов C1 и C2 (до
   исправления фикстуры, итерация 1) оставил в `HKCU\…\AppContainer\Mappings` два **тестовых**
   профиля: `conduct-a063f59a2186-9c2f7a17e4e41226a03b320be7f996dd` и
   `conduct-ed227e354676-5bf93bdc64b752c447238b0bd8d557fe` (оба из моих временных проектов, не
   B1). Прямое удаление классификатор разрешений отклонил; я не обходил. Профиль B1
   `conduct-5c89a2d82d23-2a718e4b075c1d207f972fdfec4d8901` не тронут. Убрать (ведущему, из venv
   репозитория, только эти два имени):

   ```powershell
   $names = 'conduct-a063f59a2186-9c2f7a17e4e41226a03b320be7f996dd',
            'conduct-ed227e354676-5bf93bdc64b752c447238b0bd8d557fe'
   $code = 'import sys',
           'from conductor.command.adapters import _winlaunch as w',
           '[w.delete_profile(name) for name in sys.argv[1:]]'
   python -c ($code -join "`n") @names
   ```

   (Команда не запускалась: удалять профили запрещено заданием. Проверена только передача: с
   `print` вместо вызова оба имени дошли до `sys.argv`, а `_winlaunch.delete_profile`
   импортируется и вызываем; сам вызов не делался.)

   Исправленная фикстура больше не оставляет профиль (вторая итерация: native-прогоны и
   native-мутанты оставили те же три записи `Mappings`, новых нет). **По ревью Д6 (подтверждено,
   прочитано):** для тех же двух имён стоят и папки профилей в `%LOCALAPPDATA%\Packages`:
   `conduct-a063f59a2186-9c2f7a17e4e41226a03b320be7f996dd` и
   `conduct-ed227e354676-5bf93bdc64b752c447238b0bd8d557fe` (рядом папка профиля B1
   `conduct-5c89a2d82d23-…`, её не трогать). После `_winlaunch.delete_profile` ведущий проверяет
   исчезновение **и записей `Mappings`, и этих двух папок**; если папка остаётся — это не продукт
   (удаление профиля в ОС папку `Packages` может не убирать), решать отдельно.
2. **Только-чтение файл ребёнка в `process_acl._empty_owned`.** Замер (`work\lp\measure3.py`): файл,
   помеченный read-only, даёт `PermissionError WinError 5` из `child.unlink()` (не
   `ProfileRefused`), уборка попытки не завершается. Это отдельная причина (не длина пути),
   была до задачи; `login_relay` ведёт такой файл через `_force`. Не правилось (наименьшая
   правка); рекомендация: отдельный срез, если Claude Code создаёт read-only файлы.
3. Корень длиннее 260 (глубокий профиль владельца): `NativeHold`, `holds`, `_sweep`,
   `_entries_refusal` берут путь в обычной форме; здесь не менялось (ребёнок путь корня не
   удлиняет). Рекомендация: отдельная задача, если профиль владельца когда-либо станет глубоким.
4. Принятие результата с глубоким путём в git (см. «Не проверено»).
5. В красной фазе `harness_workspace._remove_tree` пропускал глубокие записи как отсутствующие
   и падал на `rmdir`; значит прежние `discard_home`/`sweep_homes` на глубоком дереве давали
   `OSError`, а не `ProfileRefused`. Кто это ловит выше, не проверялось.
6. **`ownership_transition._inventory` молча теряет содержимое папок с обычным путём 256–259
   символов** (ревью К6, подтверждено замером `work\lp2\probe_walk_window.py`: 250–255 — `os.walk`
   видит файл; 256–259 — `lstat` проходит, `os.walk` ничего не видит и молчит; от 260 — `lstat`
   падает). Рекомендация: отдельный срез — `onerror`, который поднимает ошибку, либо обход через
   расширенное имя; тест — папка с путём 256–259. Дефект старый, к уборке попытки не относится.
7. **`harness_workspace.absent_result_paths` называет сообщённое ребёнком имя без префикса**
   (проверка П8, старое, закрыто отказом, **не регрессия**). Сообщённое удаление `item/keep.txt `
   или `item/keep.txt.` при стоящем `keep.txt` читается как удаление `keep.txt` и отвергается
   (`WorkspaceNotContained: a reported deletion still has a file`): ложный отказ, в сторону
   «не принять», тот же ответ на HEAD и на текущем коде (измерено: `work\lp3\probe_absent.py` на
   обоих). Причина та же, что в `sweep_homes` (`_file_route` → `_leaf` → `extended` чистит имя без
   префикса); здесь не менялось: сообщённые имена приходят от ребёнка текстом, и правка меняет
   контракт (какое имя считать буквальным), а не только форму для ОС. Рекомендация: отдельный срез.

## Ревью Opus

Две линзы Opus; каждая находка перепроверена мной отдельно (воспроизведение — тест, красный на коде
до правки, и/или замер), затем правка. Статус: подтверждена / частично / нет. Нет находок,
отвергнутых как неверные. Числа в этом разделе — итерации 2 (68 тестов, 52 мутанта); итоговые числа
итерации 3 — в разделах «Проверка второй итерации», «Проверки», «Красная фаза» и «Мутанты».

**Линза 1. Правильность и безопасность уборки (К).**

| № | Находка | Статус | Доказательство | Что сделано |
| --- | --- | --- | --- | --- |
| К1 | **blocker.** `extended` вызывает `os.path.abspath` до проверки префикса, переписывает имя из листинга; `take_back` убирает запись оператора и докладывает успех | **подтверждена** | 3 теста `test_taking_back_a_name_the_spawn_made_never_takes_the_operators_…` (`a `/`a`, `a.`/`a`, `...`/`other`) красные на коде до правки: файла оператора нет (для `...` — файла соседней папки `other`: имя читалось как папка выше); 5 из 7 проверок `extended` красные. Мутанты A4 (15 failed) и B9b (3 failed) | (а) `extended` возвращает имя с префиксом как есть, до очистки; (б) `take_back`: home в расширенной форме, измеренное имя присоединяется как есть (`_take_one(home, name)`, вызов внутри прежнего `try`: «не бросает» сохранено). Docstring `extended` исправлен |
| К2 | **major.** `_leaf → extended` и обходы `_remove_tree`/work_seed смотрят на другой объект, чем читают/удаляют: junction `foo ` рядом с `foo` проходит проверку портала | **подтверждена; дыра старая** (на HEAD та же) | `discard_home`/`sweep_homes` с junction `foo `: красные на HEAD (`FileNotFoundError` в самой уборке) и на коде до правки (файл за junction удалён: `outside\kept.txt` не читается); `digest`/`read`/`capture`/`modes`: junction не записан как дверь (`KeyError`), чужие байты читались как файлы задачи | та же правка К1(а): `_leaf` теперь смотрит на `foo ` буквально, видит портал, `_remove_portal` убирает саму запись; тесты на `discard_home`, `sweep_homes` и все четыре обхода work_seed (`login_home._descend`/`measure` — отдельный тест). Отчёт итерации 1 утверждал, что проверки портала работают; верно для имён без хвостовой точки/пробела. Не проверено: создаст ли такую junction ребёнок внутри AppContainer (ограничение mount point песочницы) |
| К3 | minor. `_walk_plain`: `...` читается как родитель (цикл, «exceeds cleanup bound»), `foo.` как соседняя `foo` (дубликаты, `FileNotFoundError`), junction `foo ` | **подтверждена** | `test_the_cleanup_goes_by_the_name_a_child_gave_a_folder_not_the_one_the_system_reads_it_as` ×3 красные на коде до правки (`exceeds cleanup bound`, `FileNotFoundError`) и на HEAD; `test_a_junction_spelled_like_a_folder_beside_it_is_a_door_and_the_cleanup_stops` красный на HEAD (обход шёл через junction), зелёный на коде до правки | та же К1(а); тесты через `retire` (публичный шов) |
| К4 | minor. Тесты не различают буквальное имя и повторную очистку (45 одинаково зелёные) | **подтверждена** | 23 новых теста; на коде до правки **15 failed, 53 passed** в обеих кодировках (`work\lp2\prefix-*.log`) | добавлены тесты `extended` (имя с префиксом: `foo `, `foo.`, `...`, `.. `, `a.\b`, `a \b`, `a..\b`, UNC), три уборки, два junction в домиках, три `take_back`, junction в измерении и в четырёх обходах work_seed; различающая сила и на мутантах A4, B9b |
| К5 | minor. D14 объявлен эквивалентным, но его убивает существующий тест; мутанты гоняли только на 45 новых | **подтверждена** | D14 на `test_login_relay_leaf.py`: 2 failed (`…symlink_standing_where_the_file_should_be…`, `…file_behind_a_reparse_point…`) — повторено на итоговом коде | строка отчёта исправлена; в мутантах — второй этап на существующих наборах для каждого мутанта, пережившего новые тесты |
| К6 | minor. `ownership_transition._inventory`: основание «такой переход отвергнет» неточно — `os.walk` молча теряет содержимое папок с обычным путём 256–259 | **подтверждена (основание неточно)** | `work\lp2\probe_walk_window.py`: 250–255 — `os.walk` видит файл; 256–259 — `lstat` проходит, `os.walk` ничего не видит; от 260 — `lstat` падает; basetemp `lq10` удалён | текст п.5 исправлен; **код не менялся** (старый дефект пути обслуживания, в задачу не входил); открытый вопрос 6 |

**Линза 2. Доказательность и стандарт (Д).**

| № | Находка | Статус | Доказательство | Что сделано |
| --- | --- | --- | --- | --- |
| Д1 | **major.** «D14 эквивалентен» неверен; изменённый тест-страж не прошёл через мутанты | **подтверждена** | то же, что К5; D17 (проверка `held` против `before` в `read_leaf`) на `test_login_relay_leaf.py`: 1 failed | отчёт исправлен; мутанты D14 и D17 на существующем файле; M0 существующих наборов в таблице мутантов |
| Д2 | minor. Ни один тест не стережёт отказ «owned attempt is unreadable»; замена на `except OSError: continue` зелёная | **подтверждена** | мой мутант R2: **без** нового теста 130 passed, 1 deselected (новые тесты + `test_process_acl*`); **с** ним 1 failed (`r2-without.py`) | добавлен `test_a_folder_the_system_will_not_list_refuses_the_cleanup_and_leaves_everything`: `os.scandir` глубокой папки даёт `PermissionError` на границе, ждётся `ProfileRefused("owned attempt is unreadable")`, дерево и ACL не тронуты, запись не `retired` |
| Д3 | minor. Различие старого и нового кода только на машине с `LongPathsEnabled = 0` | **подтверждена** | `LongPathsEnabled = 0` прочитано; красная фаза получена только здесь | помощник `without_long_paths` (любая машина отвечает «нет» обычному имени от N символов) и три теста: уборка попытки, `discard_home`, дайджест; его самопроверка на коротком файле с заниженным пределом; мутант T1. Ограничение названо в «Не проверено» |
| Д4 | minor. Часть тестов идёт через приватные `_walk_plain` и `_LIMIT`; в «Отклонениях» не названо | **подтверждена** | `test_the_walk_names…` (прямой вызов `_walk_plain`), `walk_then_change` (подмена `_walk_plain`), три теста с `_LIMIT`, `test_the_bound_counts…` (прямые вызовы и `_LIMIT`) | **не менялось**; внесено в «Отклонения» с причиной (гонку «обход → удаление» через границу ФС не воспроизвести без привязки к числу вызовов `lstat`; `_LIMIT` — модульная константа без публичного шва); новые тесты идут через публичные швы |
| Д5 | minor. «5 раз ожидаемый отказ не тот» на деле 6; 17 из 30 падений — исключение, не сравнение | **подтверждена; счёт исправлен проверкой П4** | `classify.py` по `--tb=line` красной фазы: 6 × regex не совпал; исключений в итерации 2 **24 из 44** (не 27; 27 — при basetemp из 4 символов, см. «Красная фаза»), на итоговых тестах итерации 3 — **31 из 53** | разбор красной фазы пересчитан, добавлено названное отклонение от буквы §3 (дефект и есть исключение; оборачивать в `try/except` ради «сравнения» значит прикрывать) |
| Д6 | minor. Названы два тестовых профиля в `Mappings`, но не их папки в `%LOCALAPPDATA%\Packages` | **подтверждена** | прочитано: `Packages\conduct-a063f59a2186-…` и `conduct-ed227e354676-…` стоят рядом с профилем B1; до и после моих native-прогонов список тот же | открытый вопрос 1 дополнен: проверять и записи `Mappings`, и эти две папки; профиль B1 не трогать |

Повторено после правок (итерация 2): новые тесты — 68 passed в UTF-8 и cp1251; native-файл
`test_long_path_native` 10 + 10 passed, соседние native 10 файлов по одному на процесс — все
passed в обеих кодировках; затронутые наборы — см. «Проверки»; мутанты — полный список заново
(52) и native (A1, A2, B1, C1, C2). Красная фаза пересчитана на итоговых тестах (HEAD src: 44/8;
код до правки ревью: 15/53).

## Проверка второй итерации (Opus)

Независимая проверка итерации 2 (проба и тесты проверяющего: `work\lp-v3-op55`, scratchpad
сессии `lp-v3`; я их читал и копировал, не менял). Восемь находок; каждая перепроверена мной
отдельно (воспроизведение тестом, красным на коде итерации 2, и/или замер), затем правка. Нет
находок, отвергнутых как неверные. Статус: подтверждена / частично / нет.

| № | Находка | Статус | Доказательство | Что сделано |
| --- | --- | --- | --- | --- |
| П1 | **major, регрессия этой задачи.** `sweep_homes` перечисляет корень домиков в обычной форме; `...`, `.. ` и ` ` в корне читаются как сам корень: `_remove_tree` стирает весь `.claude-home` с записью-не-домом и junction, возврат `()`; на HEAD `OSError 145`, ничего не удалено. Junction `attempt-1 `/`attempt-1.` рядом с домом не называется (старый дефект, та же причина) | **подтверждена** | пробы проверяющего: `sweep_dd/ddd/sp-cur.log` (корень и всё в нём стёрто, `()`), `-head.log` (`OSError 145`), `sweep_junction_sp/dot-cur.log` и `-head.log` (`()` на обоих). Мои тесты через публичный `sweep_homes` (7 случаев): на коде итерации 2 **7 failed**, все на `AssertionError` (`what is not a home was named as ()`, `the folder the child made is still there`, `a portal in the homes root was named as ()`); на HEAD красные все. Мутанты: E1 (листинг в обычной форме) 7 failed, E2 (no-op) 10, E4 (портал снят) 7, E5 («не папка» снято) 6 | `sorted(Path(extended(homes)).iterdir())`: имена из листинга приходят с префиксом и идут в `_leaf`/`_remove_tree` как есть. Тесты: пять имён в корне (`...`, `.. `, ` `, `attempt-2.`, `attempt-2 `) рядом с файлом-не-домом и junction — названы и целы, странная папка удалена буквально (`os.path.lexists` на `\\?\`-имени, не `standing`); junction `attempt-1 `/`attempt-1.` названа, дом убран, `kept.txt` цел. Поиск других мест: «Обходы деревьев» (51 вхождение в 30 файлах; место одно, как утверждал проверяющий) |
| П2 | minor. `extended` принимает форму устройства `\\.\X` за UNC (`\\?\UNC\.\X`) | **подтверждена** | `extended("\\.\C:\x")` на коде итерации 2: `\\?\UNC\.\C:\x` (`red-cur-utf8.log`); `abspath` форму устройства не портит (замер `work\lp3\abs.py` по десяти именам) | `absolute.startswith(("\\\\?\\", "\\\\.\\"))`: форма устройства возвращается как даёт `abspath` (чистая — без изменений; `//./C:/x` приводится к `\\.\C:\x`); docstring; unit-тест (`\\.\C:\x`, `Path`, `//./`); мутант E3 1 failed |
| П3 | minor. `tests/_deep_tree.py` `named`/`standing` заново чистят имя (`abspath`): для `...`/`.. `/` ` спрашивают о содержащей папке | **подтверждена** | первый прогон новых тестов до правки: `named(\\?\…\...)` даёт путь папки выше (`red-cur-utf8.log`, 9 failed из них этот) | `named` возвращает имя с префиксом как есть (как `extended`); `odd_name` сведён к `os.path.join(named(parent), name)`; тест помощников (`named`, `standing` отвечают про саму запись, до и после её удаления); мутант T2 1 failed. **Смысл существующих тестов не изменился (измерено):** копия с `named`, пишущим в лог каждый вызов, где новый ответ отличается от прежнего, на 79 тестах: различаются только 4 вызова, все в новом тесте помощников (`work\lp3\named-differs.log`); `test_long_path_native.py` зовёт `named`/`standing` с именами без префикса и без `...` (прочитано, не инструментировалось) |
| П4 | Отчёт: разбор красной фазы на HEAD неверен: 24 исключения / 20 сравнений, не 27/17 | **подтверждена; уточнена** | `classify.py` на `work\lp2\red-utf8.log` и на логе проверяющего даёт 24/20 (8 `ProfileRefused`, 7 `OSError 145`, 4+1 `FileNotFoundError`, 3 `KeyError`, 1 `CaptureRefused`; 6 `Regex`, 13 `AssertionError`, 1 `DID NOT RAISE`). Оба лога — basetemp из 5 символов; при 4 символах (стандарт) те же 44 теста дают 27/17: вид падения шести тестов рабочей копии зависит от длины пути (`pair.py`) | разбор, «Отклонения» и строка Д5 исправлены; на итоговых тестах итерации 3: **53 failed, 8 passed; 31 исключение / 22 сравнения** (10 `OSError 145`, 9 `ProfileRefused`, 7+4 `FileNotFoundError`, 1 `KeyError`; 7 `Regex`, 14 `AssertionError`, 1 `DID NOT RAISE`), в UTF-8 и cp1251 одинаково |
| П5 | Итог: «test_long_path_native и 10 соседних native-файлов»; native-файл прогнать заново на итоговом дереве в обеих кодировках | **подтверждена** | native-файл на итоговом дереве итерации 3: **10 passed** (UTF-8) и **10 passed** (cp1251), один процесс; десять соседних файлов по одному на процесс — все passed в обеих кодировках (см. «Проверки»); `Mappings` и `Packages` до и после — те же три `conduct-*` | строка «Итог» переписана («`test_long_path_native` и 10 соседних native-файлов») со ссылкой на этот прогон |
| П6 | Строка с командой в блоке кода (215 символов) длиннее 100; номер длинной строки `login_home` указан неверно (564, не 561) | **подтверждена** | `work\lp3\longlines.py`: в `login_home.py` длинная строка — 564 (та же на HEAD); в `process_acl.py` девять (те же, на HEAD) | команда разбита на строки ≤ 100 (`$names`, `$code`, `python -c`), передача проверена на безвредной замене; номер исправлен; все десять строк сверены с `git show HEAD:` |
| П7 | «Не проверено» про `without_long_paths` слишком широко: проба проверяющего показала, что три теста «машина с длинными путями» отличают HEAD от нового кода помощником, без `LongPathsEnabled` | **подтверждена; повторено** | `work\lp-v3-op55\test_probe_helper.py` (SHA-256 `41C8153A…AA03`), копии `work\lp3\red` и `work\lp3\cur`: HEAD с помощником **3 failed** (`ProfileRefused`, `OSError WinError 145`, `AssertionError: []`), HEAD без помощника **3 passed**, текущий код **6 passed** | пункт «Не проверено» сужен: осталось не измеренным только то, что сами три теста дают на машине с `LongPathsEnabled = 1` |
| П8 | Открытый вопрос (старое, закрыто отказом, не регрессия): `absent_result_paths` называет сообщённые ребёнком имена без префикса; сообщённое удаление `item/keep.txt ` рядом со стоящим `keep.txt` отвергается ложно | **подтверждена; не регрессия** | `work\lp3\probe_absent.py`: `keep.txt ` и `keep.txt.` при стоящем `keep.txt` — `WorkspaceNotContained: a reported deletion still has a file` и на HEAD, и на текущем коде; `other.txt` принимается | код не менялся (правка меняет контракт имени, а не форму для ОС); открытый вопрос 7 с рекомендацией |

Повторено после правок: новые тесты — 79 passed в UTF-8 и cp1251; `test_long_path_native` 10 + 10
passed и десять соседних native-файлов — все passed в обеих кодировках; затронутые наборы — см.
«Проверки»; мутанты — полный список заново (58); красная фаза пересчитана на итоговых тестах (HEAD
`src`: 53 failed, 8 passed на 61 тесте; код итерации 2: 8/71 на 79; код до правки ревью итерации
2: 24/55 на 79).

## Приёмка ведущего (Opus, 27.10)

**Проверка третьей итерации (независимый Opus).** Вердикт `approve_with_notes`: дефектов в `src`
нет; красная фаза, мутанты исполнителя и свои мутанты проверяющего (OWN1, OWN3 убиты), пробы
`probe_v3` (24 сценария), поиск листингов по всему `src` (51 вхождение в 30 файлах) подтверждают
вывод исполнителя. Две находки minor, обе закрыты ведущим:

1. Три строки отчёта вне таблиц длиннее 100 (скрипт `mdlimits.py` пропускал строки, начинающиеся
   с обратной кавычки). Переписаны; проверка без этого исключения: строк > 100 вне таблиц нет.
2. Ветка `//?/` в `extended` без теста: мутант OWN2 (в кортеже только `\\.\`) переживал все наборы,
   и `extended("//?/C:/a/b")` давал сетевой путь `\\?\UNC\?\C:\a\b`. Вызывающих с такой формой
   нет. Добавлен случай `extended("//?/C:/x") == "\\?\C:\x"` в тест формы устройства; OWN2 теперь
   1 failed (UTF-8), файл восстановлен, SHA-256 совпал.

После правок: `test_long_path*.py` (кроме native) и `test_command_line_cap.py` — 276 passed в
UTF-8 и 276 passed в cp1251 (basetemp 4 символа, удалён; логи `work\lead-check3`);
`git diff --check` чист. Diff `sweep_homes`, `extended` и `_deep_tree.named`/`standing` прочитан
ведущим.

**Решения по «Отклонениям» (все семь приняты).**

1. `long_path.py` в `command/`, не в `adapters/`: помощник нужен и вне адаптеров, а в `adapters/`
   он провалил бы охрану импортов.
2. Правки шире п.1–3 (`login_home`, `_leaf`, `read_leaf`, `leaf_kind`): п.5 велит исправить
   найденные обходы, п.2 называет чтение листа; `_leaf` убирает ложное «файла нет» в
   доказательствах.
3. Шов `as_the_os_words_it`: проверка продукта не менялась, сила шва доказана мутантами D14
   (2 failed) и D17 (1 failed) на существующем файле. `read_leaf` через `extended` оставлен.
4. Native-фикстура ловит исключение выхода: оно проверяется утверждением `exit_error is None`, и
   профиль, оставленный выходом, не остаётся в системе.
5. Часть красных падений — исключение-симптом: дефект и есть исключение (отказ уборки после
   работы ребёнка); обёртка ради «сравнения» прикрыла бы причину (§10.2).
6. Тесты проверяющего итерации 2 в форме исполнителя: проверяемое то же, случаев больше, красные на
   тех же кодах.
7. Приватные швы `_walk_plain` и `_LIMIT`: гонку «обход → удаление» через ФС не воспроизвести без
   привязки к числу вызовов `lstat`; новые тесты второй и третьей итераций идут через публичные
   швы.

**Принятый риск для B2 (открытый вопрос 2 остаётся).** Read-only файл ребёнка в `_empty_owned`
даёт `PermissionError WinError 5` и останавливает уборку. Для B2 риск принят как низкий: остаток
B1 прочитан полностью через `\\?\` сканером только для чтения (0 ошибок обхода, 9 папок, 0 файлов,
0 read-only, 0 reparse, глубина 336 символов), а в режиме займа запись ACL держит только parent и
runtime, рабочую копию `_empty_owned` не очищает. Если B2 всё же даст `WinError 5` при уборке —
стоп по стандарту, отдельный срез, без повтора.

**Лимиты.** `harness_workspace.py` 794 строки (≤ 800, +2 строки комментария в `sweep_homes`);
`process.py` не менялся (800). Шесть новых файлов внесены в `CAPPED` ведущим в коммите кода.

**Коммиты.** Код, тесты и `CAPPED` — `52f3d50`. Этот отчёт — следующий коммит документов.

**Итоговый полный core на `52f3d50`** (detached worktree `work\wtf2`, `conductor` из него, статус
до и после пуст; 662 файла в 7 параллельных частях, затем 12 native-файлов по одному на процесс;
логи `Documents\Codex\work\lead-final2`, 17:41–18:42):

| Кодировка | Обычные тесты | Native |
| --- | --- | --- |
| UTF-8 (`utf8_mode=1`) | **18 708 passed, 409 skipped, 0 failed** | **101 passed**, 20 skipped |
| cp1251 (`utf8_mode=0`) | **18 708 passed, 409 skipped, 0 failed** | **101 passed**, 20 skipped |

Native: 11 прежних файлов (91 passed) и `test_long_path_native` (10 passed). 20 skipped — файл
A2 `test_relay_claude_native.py` без `CONDUCT_A2_CLAUDE_EXE`: живой CLI не запускался, прежний A2 не
повторялся (решение Codex, условие 2). Скрипт прогона не удалил 14 своих basetemp (`gu0–6`,
`gc0–6`): в них только файлы с атрибутом read-only (объекты git), reparse 0, ошибок обхода 0
(сканер только для чтения); `shutil.rmtree` атрибут не снимает. Это дефект скрипта, не продукта:
помощник `rmbase.py` (только папка ≤ 4 символов прямо в профиле, read-only снимается, reparse не
трогается) убрал все 14, worktree `wtf2` удалён.

## Ревью Codex: ожидает

Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit: нет (не коммитил). Предлагаемые коммиты: (1) `fix(command): name deep paths
  in the extended-length form in every cleanup of a child's tree (H5-B-LONGPATH)` — `src` (6
  изменённых и 1 новый файл) вместе с пятью новыми файлами тестов и правкой шва
  `tests/test_login_relay_leaf.py`; в сообщении: зачем (выход из boundary после работы ребёнка
  отказывал при пути > 260, B1), что (имя ОС в форме `\\?\` во всех обходах дерева ребёнка; имя
  из листинга не чистится повторно, листинг корня домиков тоже в этой форме), чем доказано
  (красная фаза 53 failed / 8 passed на HEAD, 8/71 на коде итерации 2, 24/55 на коде до правки
  ревью итерации 2, мутанты 58/58 убиты, native); (2) документ — этот отчёт.
- **Новые файлы для `CAPPED` (`tests/test_command_line_cap.py`):**
  `src/conductor/command/long_path.py`, `tests/_deep_tree.py`, `tests/test_long_path.py`,
  `tests/test_long_path_attempt.py`, `tests/test_long_path_homes.py`,
  `tests/test_long_path_native.py` — **ведущий их уже внёс** (`M tests/test_command_line_cap.py`
  в рабочей копии, +6 строк), я эту правку не трогал. Новых файлов в итерациях 2 и 3 нет (тесты
  добавлены в эти же).
- `git status` (мой, итерация 3): `M` `harness_workspace.py`, `login_home.py`, `login_relay.py`,
  `process_acl.py`, `relay_home.py`, `work_seed.py` (все в `src/conductor/command/adapters/`),
  `tests/test_command_line_cap.py` (ведущий), `tests/test_login_relay_leaf.py`; `??`
  `src/conductor/command/long_path.py`, `tests/_deep_tree.py`, `tests/test_long_path.py`,
  `tests/test_long_path_attempt.py`, `tests/test_long_path_homes.py`,
  `tests/test_long_path_native.py`, этот отчёт.
- **Команда восстановления остатка B1 для ведущего** (исправленная защищённая сборка, сервер
  остановлен Ctrl+C, согласие владельца получено, без `--abandon-loans`):
  `conduct ownership recover-containers --dir "%USERPROFILE%\DecemberRehearsal"`. Если команда
  откажет `profile_acl_unproven` и назовёт `--prepare-restart` (запись старого формата или другая
  среда загрузки) — выполнить `… --prepare-restart`, затем **полный Restart Windows** (не
  выключение, не перезапуск приложения), затем обычную команду ещё раз. Проверить факты, не
  только код выхода: папки попытки с путём 336 символов нет, профиль
  `conduct-5c89a2d82d23-2a718e4b075c1d207f972fdfec4d8901` не известен системе (`inspect_profile`),
  записи `profile/acl/loan` — `retired`, владение и lease берутся обычным путём, три исходных файла
  по seed-manifest целы. Обработает **все** записи журнала проекта (параметра выбора нет).
- Следующий конкретный шаг: ведущий читает «Проверка второй итерации (Opus)» (статусы П1–П8) и
  «Ревью Opus», затем коммиты, полный core на финальном коммите в detached worktree и новая
  защищённая установка продукта.
