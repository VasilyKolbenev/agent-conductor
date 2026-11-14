# Отчёт по задаче: N2 — helper разбора напечатанной команды в `tests/test_doctor.py`

- Исполнитель: Claude Code (Sonnet 5.5).
- Исходный commit и ветка: `79cd652`, `recovery/2026-10-20`. Это docs-коммит поверх `ff0ce19`:
  `git diff --name-only ff0ce19 HEAD` даёт три файла в `docs/recovery/2026-10-20/` и ни одного
  в `src/` или `tests/`, так что код и тесты те же, что в `ff0ce19`.
- Состояние рабочей копии до изменений: чистая (`git status --short` пуст).
- Цель и наблюдаемое ожидаемое поведение: `tests/test_doctor.py` проходит целиком на
  кириллическом профиле (`C:\Users\Пользователь`) так же, как в Windows CI с ASCII-путями.
  Раньше на ноутбуке было 14 failed. Код продукта (`src/`) не менялся.

## Находка

Полный core-suite Opus 20.10: 17284 passed, 16 failed. Из 16 два — артефакт запуска
`tests/test_file_endings.py` вне git: тест читает список файлов из `git ls-files`. В репозитории
он проходит (см. «Проверки»). Остальные 14 — `tests/test_doctor.py`, список в задании.

Причина 14 падений: helper `commands()` разбирал напечатанную команду через `.split(" ")` и не
снимал кавычки. Продукт по контракту (`doctor._spelled`, `_BARE_CHARS`) берёт в двойные кавычки
любой токен с символом вне allowlist, а кириллица в пути к allowlist не относится. На ASCII-пути
токен остаётся голым, поэтому в CI тесты зелёные. На кириллическом профиле helper отдавал
`'"C:\\Users\\Пользователь\\pt-f\\..."'` с буквальными кавычками. Отсюда `argv[4] == '"..."'`
вместо пути и `OSError: [WinError 123]`, когда `main(argv)` получал этот путь.

## Изменения

Состояние после правок по ревью Opus (первая версия этой задачи держала всё в `test_doctor.py`,
см. «Правки после ревью Opus»):

| Файл | Что и зачем |
| --- | --- |
| `tests/doctor_printed.py` (новый, 47 строк) | Helper без тестов. Регулярное выражение `_PRINTED_TOKEN = "([^"]*)"\|([^ "]+)` и функция `printed_argv(line)`: токен в двойных кавычках даёт один аргумент без кавычек (пробелы и обратные слеши сохраняются), токен без кавычек идёт до пробела, `conduct` отбрасывается. После разбора проверяется `doctor.spell(argv) == line`, иначе `AssertionError` с обеими строками. Разбираются только строки с `COMMAND_PREFIX`; detail и остальные строки отчёта helper не читает. |
| `tests/test_doctor.py` (+7, −2 к HEAD, 788 строк) | `commands(out)` вызывает `printed_argv` из `tests/doctor_printed.py` вместо `.split(" ")[1:]`. Импорт `re` не нужен и не добавлен. |
| `tests/test_doctor_printed.py` (новый, 75 строк, 13 тестов) | Регрессионный `test_a_quoted_root_is_read_back_out_of_the_printed_line_as_the_path_it_is`: проект в `tmp_path / "Пользователь dir"` (не-ASCII и пробел заставляют `doctor` взять путь в кавычки на любой ОС и при любом временном корне раннера); строка содержит `--dir "<root>"`, `argv == ["init", "--template", templates.DEFAULT, "--dir", str(root)]`, в токенах нет `"`, `main(argv) == 0` и `conductor/map.toml` создан. Контракт против писателя `doctor.spell` (5 параметров): голый путь, кириллица с пробелом, Windows-путь с обратными слешами и пробелом, `Program Files (x86)\p&q`, пустой токен; обратные слеши не съедаются, то есть `shlex.split(posix=True)` не подошёл бы. Новое: 7 строк, которые `doctor.spell` не пишет, helper обязан отвергнуть. |
| `docs/recovery/2026-10-20/tasks/N2-REPORT.md` | Этот отчёт. |

`src/` не менялся (`git diff --stat -- src` пуст). Хвостовые пробелы, строки длиннее 100
символов и окончания файлов в трёх файлах `tests/` выше проверены отдельно: нет замечаний.

## Проверки

Окружение: `December-Command-Environment.ps1 -Quiet`, Windows 11, Python 3.12.14,
`python -m pytest -q -p no:cacheprovider --basetemp <путь>`. Все свои `pt-n2*` каталоги удалены.

| Команда | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| `tests/test_doctor.py`, старый helper (до правки), `C:\Users\Пользователь\pt-n2a` | кириллический профиль | 14 failed, 44 passed | падения воспроизведены, набор совпадает с заданием |
| `tests/test_doctor.py`, новый helper, `C:\Users\Пользователь\pt-n2b` | кириллический профиль | 64 passed | 14 падений сняты; 58 прежних плюс 6 новых тестов |
| `tests/test_doctor.py`, новый helper, `C:\Users\Public\pt-n2` | ASCII basetemp | 64 passed | на ASCII-пути ничего не сломано |
| копия с возвращённым `.split(" ")[1:]`, `C:\Users\Public\pt-n2` | ASCII basetemp | 1 failed, 63 passed | регрессионный тест КРАСНЫЙ со старым helper-ом даже на ASCII-пути: argv `[..., '"C:\\...\\Пользователь', 'dir"']` вместо одного пути |
| та же копия, `C:\Users\Пользователь\pt-n2c` | кириллический профиль | 15 failed, 49 passed | прежние 14 плюс регрессионный |
| `tests/test_command_line_cap.py tests/test_file_endings.py`, `C:\Users\Пользователь\pt-n2d` | кириллический профиль, в git | 154 passed | `test_file_endings` в репозитории зелёный; 2 падения полного прогона были артефактом запуска вне git |
| `tests/test_doctor_claims.py tests/test_doctor_argv_doors.py`, `C:\Users\Пользователь\pt-n2e` | кириллический профиль | 27 passed | соседние файлы, которые импортируют другие helper-ы из `test_doctor.py`, не задеты |

Красный результат получен на копии `tests/test_doctor.py`, лежащей вне репозитория:
`C:\Users\Пользователь\Documents\Codex\work\n2-old\test_doctor_oldhelper.py`. В ней единственное
отличие от рабочего файла — одна строка в `commands()`. Файл в репозитории не правился и не
возвращался. Запускается из корня репозитория: `python -m pytest` добавляет cwd в `sys.path`,
и `from tests.test_store import ...` находится.

Прогон копии на `C:\Users\Public\pt-n2` показывает, что регрессионный тест краснеет и без
кириллического профиля, то есть он ловит этот класс сбоя в ASCII-среде вроде CI.

Таблица выше относится к первой версии правки (все тесты внутри `test_doctor.py`). Числа после
ревью Opus и вынесения — в следующем разделе.

## Правки после ревью Opus

Ревью нашло блокер: `tests/test_doctor.py` вырос с 783 до 840 физических строк при лимите 800.
Первая версия (+58, −1) складывала helper и два теста в этот файл. Сделано:

1. **Вынос.** `printed_argv` вместе с `_PRINTED_TOKEN` лежит в `tests/doctor_printed.py` (файл без
   тестов, как `queue_fixtures.py` и `git_repo_helpers.py`). Регрессионный тест на каталоге
   `Пользователь dir` и тест разбора против `doctor.spell` переехали в
   `tests/test_doctor_printed.py` по образцу `test_doctor_claims.py`: docstring модуля, фикстуры
   `report` и `commands` из `tests.test_doctor`. Проект тест-модуль из тест-модуля импортирует
   (`test_doctor_claims.py` берёт фикстуры из `test_doctor.py`), но здесь это дало бы цикл: новому
   файлу нужны `report` и `commands` из `test_doctor.py`, а `test_doctor.py` нужен `printed_argv`.
   Поэтому helper отдельным модулем, а `test_doctor.py` импортирует его оттуда: строка
   `from tests.doctor_printed import printed_argv`. Результат: `test_doctor.py` 788 строк
   (было 840, лимит 800), diff к HEAD +7 −2.
2. **Локальный артефакт убран из данных теста.** Параметр `C:\Users\Пользователь\pt-n2a\a b`
   заменён на `C:\Users\Пользователь\project\a b`. Литерала `pt-n2a` в `tests/` больше нет
   (поиск по `tests/`). В этом отчёте он остался только в таблице «Проверки» как имя каталога
   прошлого прогона.
3. **Строгий helper.** После разбора `printed_argv` вычисляет `doctor.spell(tuple(argv))` и, если
   результат не равен исходной строке, поднимает `AssertionError`: `printed line '...' is not what
   doctor.spell writes for the argv read off it, [...]: spell gives '...'`. Так команда
   восстанавливается тем же контрактом, что её напечатал; строка, которую `spell` не пишет
   (голый токен, который `spell` взял бы в кавычки, кавычки на токене, который `spell` пишет голым,
   двойной пробел, нет `conduct`, пустая строка), не читается молча как какой-то argv. Новые
   проверки: параметризованный `test_a_line_that_doctor_spell_would_not_write_is_refused_not_read`
   на 7 строках; в параметризованный тест разбора добавлена обратная сверка
   `doctor.spell(printed_argv(line)) == line`. Мутация: с условием `if spelled != line` заменённым
   на `if False` (копия кода в scratch, файл в репозитории не менялся) ни одна из 7 строк не
   вызывает ошибку, то есть новые случаи без проверки красные.
4. **`tests/test_command_line_cap.py` не менялся.** В `CAPPED` нет ни `test_doctor.py`, ни
   `test_doctor_claims.py`, ни `test_doctor_argv_doors.py` (поиск «doctor» по файлу пуст), а
   его docstring говорит о файлах, созданных lane L для desk-редизайна. Соседние doctor-тесты не
   перечислены. Строки новых файлов при этом проверены вручную: 0 строк длиннее 100. Что
   добавить в `CAPPED`, см. следующий подраздел.

### Доведение после остановки (Sonnet 5.5, 21.10, HEAD `5bb09f6`)

Работа была остановлена после выноса; состояние проверено заново, а не принято на веру.

- **Состояние до проверок:** изменены `tests/test_doctor.py` (+7 −2 к HEAD) и три
  неотслеживаемых файла; правок в коде тестов не потребовалось, делалась только проверка.
- **Физические строки** (`\n` в файле): `tests/test_doctor.py` 788 (лимит 800, запас 12),
  `tests/doctor_printed.py` 47, `tests/test_doctor_printed.py` 75. В каждом один `\n` в конце,
  хвостовых пробелов, `\r` и строк длиннее 100 нет. (`Measure-Object -Line` считает без пустых
  строк и даёт 664; как физические строки его число не использовать.)
- **Строгий helper:** `printed_argv` сверяет `doctor.spell(tuple(argv)) == line` и иначе поднимает
  `AssertionError` с обеими строками и словами «is not what doctor.spell writes». Литерала
  `pt-n2` в `tests/` нет (поиск по `tests/*.py` пуст).
- **Мутант A, красный.** Копия вне репозитория,
  `C:\Users\Пользователь\Documents\Codex\work\n2-q\`: `mut_split_doctor.py` (копия
  `test_doctor.py`, где `commands()` снова `.split(" ")[1:]`) и `test_mut_split.py` (копия
  `test_doctor_printed.py`, которая берёт `commands` оттуда). Регрессионный тест на
  `Пользователь dir` краснеет: argv `[..., '"…\\Пользователь', 'dir"']` вместо одного пути.
  Остальные 12 тестов копии зелёные.
- **Мутант B, красный.** `mut_lax_printed.py` (`if spelled != line` заменён на `if False`) и
  `test_mut_lax.py`: все 7 случаев отказа дают `DID NOT RAISE AssertionError`; 6 остальных
  зелёные.

| Команда | Среда | Результат |
| --- | --- | --- |
| 4 файла doctor, `C:\Users\Пользователь\pt-q1` | кириллический basetemp | 98 passed |
| те же 4 файла, `C:\Users\Public\pt-q2` | ASCII basetemp | 98 passed |
| мутант A, `C:\Users\Пользователь\pt-q3` | кириллический | 1 failed, 12 passed |
| мутант A, `C:\Users\Public\pt-q4` | ASCII | 1 failed, 12 passed |
| мутант B, `C:\Users\Public\pt-q5` | ASCII | 7 failed, 6 passed |

Четыре файла: `test_doctor.py` 58, `test_doctor_printed.py` 13, `test_doctor_claims.py` 19,
`test_doctor_argv_doors.py` 8. Все `pt-q*` каталоги удалены, `git status` после прогонов тот же.

**Для оркестратора: что добавить в `CAPPED`** (`tests/test_command_line_cap.py`; правило из
его docstring: файл вносится в коммите, который его создаёт; мной файл не правился):

- `"tests/doctor_printed.py"`
- `"tests/test_doctor_printed.py"`

`tests/test_doctor.py` не создавался этой задачей, но тоже без строк длиннее 100 и его можно
добавить тем же коммитом по желанию. Лимит 800 строк на `test_doctor.py` отдельным тестом не
держится: следить вручную (запас 12).

Проверки (все свои каталоги `pt-r*` удалены; чужие `pt-f` и `pt-c2` в `C:\Users\Пользователь`
не тронуты):

| Команда | Среда | Результат |
| --- | --- | --- |
| `tests/test_doctor.py tests/test_doctor_printed.py tests/test_doctor_claims.py tests/test_doctor_argv_doors.py`, `C:\Users\Пользователь\pt-r1` | кириллический профиль | 98 passed (58 + 13 + 19 + 8) |
| те же четыре файла, `C:\Users\Public\pt-r2` | ASCII basetemp | 98 passed |
| `tests/test_command_line_cap.py tests/test_file_endings.py`, `C:\Users\Пользователь\pt-r3` | кириллический профиль | 154 passed |

Физические строки и окончания: `tests/test_doctor.py` 788, `tests/test_doctor_printed.py` 75,
`tests/doctor_printed.py` 47; во всех трёх один перевод строки в конце, хвостовых пробелов нет,
строк длиннее 100 нет. `test_file_endings.py` читает только то, что даёт `git ls-files`, а три
файла (два новых и этот отчёт) пока не отслеживаются, поэтому окончания я проверил отдельно, а не
по зелёному `test_file_endings.py`. Было 64 теста в `test_doctor.py` (58 прежних и 6 новых),
стало 58 в нём и 13 в новом файле; соседние 19 и 8 прежние.

## Вывод скептика о реальных оболочках

Скептик (метод: заглушка `conduct.exe` через distlib ScriptMaker, тот же лаунчер, что у
`.venv\Scripts\conduct.exe`, печатает `json.dumps(sys.argv[1:])`; проекты строил `corpus()` из
`test_doctor.py`; строки `next:` из `python -m conductor doctor --dir`; ожидаемый argv из
`doctor.inspect(root)`; argv сверялся как Unicode) подтвердил, что напечатанные команды в PowerShell
и cmd дают правильный argv. Вердикт скептика: для 14 падений гипотеза не опровергнута, дефект в
тестовом helper-е, продукт печатает правильную команду.

| Оболочка | Способ запуска | Базы | Результат |
| --- | --- | --- | --- |
| PowerShell 5.1 | `-EncodedCommand` (UTF-16, как вставка в консоль) | «Пользователь», «My Dir», «a&b» | argv правильный |
| PowerShell 5.1 | `.ps1` с BOM | те же | argv правильный |
| cmd | `cmd /d /c <строка>` (сырая командная строка в CreateProcessW) | те же | argv правильный |
| cmd | `.cmd` с `chcp 65001` | те же | argv правильный |
| `sh.exe` из Git | `run_sh.py`, по одной команде на файл | те же | 18 из 18 строк основного набора правильный argv (по `run_sh.txt`; колонка `sh-file` в `run.txt` — сбой стенда) |

Всего скептик выполнил 30 напечатанных команд на трёх базах. Цифры по ячейкам таблицы
в мой текст не дошли (сообщение оборвано на этом месте), поэтому ячейки выше отражают только
сформулированный вывод: «правильный argv» для PowerShell и cmd. Позже я прочитал файлы стенда
`run.txt` и `run_sh.txt`: на основном наборе (3 базы, 6 проектов на каждую, 18 строк) расхождений
нет ни в PowerShell, ни в cmd, ни в `sh`. Это согласуется с выводом скептика. Сам я оболочки не
запускал.

Скептик также сообщает, что общая посылка гипотезы («двойные кавычки корректны для POSIX sh,
PowerShell и cmd») неверна: он нашёл отдельные дефекты продукта. К 14 падениям они отношения не
имеют. Этим отчётом они не закрываются. Комментарий к `_spelled` в `doctor.py` сам оговаривает,
что в POSIX sh двойные кавычки не нейтрализуют `$`, обратную кавычку, обратный слеш и `"`.

## Найдено скептиком вне N2: дефекты продукта N3

Это не часть N2 и не исправлялось: задача N2 только про тесты, `src/` не менялся. Скептик
прогнал напечатанные команды через PowerShell 5.1, cmd и `sh.exe` из Git на корнях, которых нет в
корпусе `test_doctor.py`. Я прочитал файлы стенда (`results.json`, `run.txt`, `run_sh.txt`,
`e2e.txt` в `C:\Users\Пользователь\Documents\Codex\work\n2-sk\`), оболочки сам не запускал. По
ним: на шести проектах и трёх основных базах («Пользователь», «My Dir», «a&b», 18 строк) PowerShell,
cmd и `sh` дают правильный argv. Расхождения только на дополнительных корнях и ролях:

- корень с `\` на конце: `\"` читается как буква кавычки в cmd (во всех трёх строках), в PowerShell
  (там, где в пути есть пробел) и в `sh` (кавычка не закрыта); вставленная строка из `e2e.txt`
  падает с `cannot inspect ...": not a directory`;
- корни с `$` и обратной кавычкой: расхождения в PowerShell и `sh`;
- `%OS%` в корне: расхождение в cmd;
- роль `@scout`: PowerShell не отдаёт её как значение (`expected one argument` в `e2e.txt`);
- относительные и короткие (8.3) корни без пробелов: голый `\` в `sh` съедается (5 из 6 строк).

Сводка по 53 дополнительным строкам основного набора: расхождения в PowerShell на 14, в cmd на 9,
в `sh` на 15. Колонка `sh-file` в `run.txt` — сбой самого стенда, её заменяет `run_sh.txt`.
Описание, воспроизведение и решение по продукту — в
[`tasks/N3-DOCTOR-QUOTING.md`](N3-DOCTOR-QUOTING.md).

## Не проверено

- Windows CI (ASCII-профиль) и Linux/macOS не запускались. Что регрессионный тест с каталогом
  `Пользователь dir` проходит на POSIX, выведено из того, что `tmp_path` там принимает любое
  имя из Unicode. Не измерено.
- Полный core-suite не перезапускался: прогнаны `tests/test_doctor.py`,
  `tests/test_doctor_printed.py`, `tests/test_command_line_cap.py`, `tests/test_file_endings.py` и
  два соседних файла doctor. `printed_argv()` теперь импортируют `tests/test_doctor.py` и
  `tests/test_doctor_printed.py`, `commands()` — `tests/test_doctor_printed.py`; больше никто
  (поиск по `tests/`).
- Реальные оболочки я не запускал. Таблица выше и раздел про N3 передают файлы стенда скептика, а
  не мои измерения.
- Дефекты продукта N3 не воспроизводились мной и не исправлялись. Задача N2 — только тесты.
- Новые файлы `tests/doctor_printed.py` и `tests/test_doctor_printed.py` не отслеживаются git, так
  что `test_file_endings.py` их не читает (окончания проверены вручную, см. выше).
- В `C:\Users\Пользователь` остались каталоги `pt-f` (прогон Opus) и `pt-c2` (не мой). Я их не
  трогал.

## Ревью Codex

Ожидает. Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit, если создан: нет (без коммитов, push, stash, checkout, reset).
- `git status`: ` M tests/test_doctor.py` и не отслеживаемые `tests/doctor_printed.py`,
  `tests/test_doctor_printed.py`, `docs/recovery/2026-10-20/tasks/N2-REPORT.md`. Ничего не в
  индексе.
- Обновлённые документы: этот отчёт.
- Следующий конкретный шаг: ревью Codex и коммит `tests/test_doctor.py`,
  `tests/doctor_printed.py`, `tests/test_doctor_printed.py` вместе с отчётом одной правкой.
  Вместе с ним внести два модуля в `CAPPED` (см. «Доведение после остановки»). Дефекты
  продукта из раздела про N3 ведутся в `tasks/N3-DOCTOR-QUOTING.md`.
