# N3 — кавычение напечатанных команд `conduct doctor`: разбор D1–D4, решение и задание

- Автор: Opus 5.5 (старший разработчик). Режим только чтения для репозитория; этот файл — единственная
  правка в нём.
- Исходный commit и ветка: `79cd652`, `recovery/2026-10-20`.
- Рабочая копия: незакоммиченный N2 (`tests/test_doctor.py`, `tests/doctor_printed.py`,
  `tests/test_doctor_printed.py`, `tasks/N2-REPORT.md`) — база задачи. Параллельный workflow держит
  неотслеживаемые `tasks/R1.3-WIN-10055-CI41.md`, `tasks/R1.5-DRAIN-CTRL-C.md` и правит
  policy_driver/queue/Desk — не тронуто.
- `src/` и `tests/` не менялись. Все эксперименты — в копии вне репозитория
  `C:\Users\Пользователь\Documents\Codex\work\n3-op\tc` (см. раздел 9).

## 0. Итог

Все четыре дефекта скептика подтверждены по коду и повторным прогоном в настоящих оболочках. Сверх
них найдены три дефекта того же класса (D5–D7). Решение — четыре правки в `src/conductor/doctor.py`
(две константы, три строки `_spelled`, одна строка `inspect`) плюс docstring-и; D3 документируется.

| Дефект | Подтверждено | Решение |
| --- | --- | --- |
| D1 корень с хвостовым `\` | cmd всегда; PowerShell 5.1 при пробеле; sh всегда | нормализовать корень в `inspect` (`str(Path(root))`, якорь `C:\` остаётся) **и** удваивать хвостовые `\` закавыченного токена (правило CRT) |
| D2 роль `@scout` | PowerShell: splatting, токен исчезает; `@` один — ошибка разбора | кавычить: `@` вне `_BARE_CHARS`; `_AUTHORED_CHARS` по содержимому не меняется |
| D3 `$`, обратная кавычка, `%VAR%` в корне | PS и sh раскрывают `$` и `` ` ``; cmd раскрывает `%VAR%` в кавычках | документировать; измерено, что ни одна форма кавычек не обслуживает одновременно PS и cmd |
| D4 голый `\` в sh | `C:\Users\x` → `C:Usersx`, 8.3, относительные пути | `\` вне `_BARE_CHARS`: Windows-путь всегда в кавычках |
| D5 (новый) запятая | PowerShell: `scout,07` → `scout,7`, `a,1kb` → `a,1024`, `,x` → `x`; `x,`, `a,,b`, `,` — ошибка разбора | `,` вне `_BARE_CHARS` (кавычить) |
| D6 (новый) ведущая `~` | sh: `--dir ~` → `$HOME` | `~` вне `_BARE_CHARS` |
| D7 (новый) пустой корень | `--dir ""`: PowerShell 5.1 выбрасывает пустой аргумент → argparse exit 2 | снимается нормализацией (`""` → `.` → без `--dir`) |

Итоговое правило:

```text
_BARE_CHARS     = A-Z a-z 0-9 и  - _ . : / + =          (было ещё , @ ~ \)
_AUTHORED_CHARS = A-Z a-z 0-9 и  - _ . , : / @ + =      (как сегодня, но явным множеством)
_spelled(t)     = t, если t непуст и все символы из _BARE_CHARS;
                  иначе '"' + t + (хвостовые '\' t ещё раз) + '"'
inspect(root)   : text_root = str(Path(root))
```

Остаётся и документируется: D3; Windows PowerShell 5.1 передаёт закавыченный токен без пробела
голым, поэтому токен, оканчивающийся на `\`, приходит программе с одним лишним `\` — после
нормализации это только якорь: `C:\` → `C:\\` (тот же каталог, проверено настоящим `conduct.exe`),
`\` → `\\` (уже не каталог); в Git sh UNC-префикс `\\srv` внутри `"..."` становится `\srv`, и
MSYS-конверсия переписывает аргумент с ведущим `/` (это не вопрос кавычек).

## 1. Метод и стенд

- Заглушка скептика `n2-sk\bin\conduct.exe` (distlib-лаунчер, как у `.venv\Scripts\conduct.exe`,
  печатает `ARGV:<json>`), `PYTHONPATH=n2-sk\stub`.
- Шесть исполнителей (`n3-op\probe.py`): `ps-i` — PowerShell 5.1 `-EncodedCommand` (как вставка в
  консоль); `ps-f` — отдельный `.ps1` с BOM на каждую строку; `cmd-i` — `cmd.exe /d /c <строка>`;
  `cmd-b` — отдельный `.cmd` с `chcp 65001`; `sh` — Git `usr\bin\sh.exe` из
  `codex-primary-runtime` с `MSYS_NO_PATHCONV=1` (как у скептика); `sh-conv` — тот же sh без него
  (как настоящий Git Bash). По одной строке на процесс/файл: каскада между случаями нет.
- `n3-op\stand3.py` — стенд скептика целиком (корпус `corpus()` под базами «Пользователь», «My Dir»,
  «a&b», «Мой проект», «x,07» и др., хвостовые `\` и `\\`, относительные, 8.3, пустой корень, `C:\`;
  роли `@scout`, `a,b`, `scout,07`, `x~y`): напечатанные `next:` из `python -m conductor doctor`,
  ожидаемый argv из `doctor.inspect`, прогон во всех шести исполнителях. Запускался на исходном
  `src` и на копии с правкой.
- `n3-op\e2e3.py` — настоящий `conduct.exe` (только `doctor` и `prompt`), исходный и исправленный код.
- `n3-op\probe2.py` — запятые и числа в PowerShell; `n3-op\probe3.py` — альтернативные кавычки для D3;
  `n3-op\posix_sim.py` — механика будущего POSIX-теста через Git sh.

## 2. Подтверждение D1–D4

### D1. Хвостовой `\` внутри кавычек

Код: `_spelled` (стр. 540) — `return token if ... else f'"{token}"'`. По правилам CRT/MSVCRT
(`CommandLineToArgvW`) `\"` — буквальная кавычка, а `2n` обратных слешей перед `"` — это `n`
слешей и закрывающая кавычка. Хвостовой `\` корня поэтому съедает закрывающую кавычку.

Стенд скептика (`run.txt`, `e2e.txt`), повторено мной (`probe1.txt`, `stand3-old.txt`, `e2e3-old.txt`):

```text
[extra] My Dir (trailing \) | ps-interactive=DIFF ps1-file=DIFF cmd-interactive=DIFF cmd-batch=DIFF
    cmd-interactive: got [..., "--dir", "C:\\...\\My Dir\\unheld\""]
--- cmd: pasted conduct doctor --dir "C:\...\Пользователь-tpl\": exit 1
    cannot inspect C:\...\Пользователь-tpl": not a directory
sh: line 1: unexpected EOF while looking for matching `"'
```

PowerShell 5.1 без пробела в пути — OK (он передаёт значение голым), с пробелом — `...My Dir"`:
5.1 сам заворачивает аргумент с пробелом в кавычки и хвостовые `\` не удваивает (известное
поведение 5.1). Проба ревьюера `n2-rv\tail.py`: `C:\Мой\` → argv `C:\Мой"`.

### D2. Роль с ведущим `@`

Код: `_spellable` (стр. 196–197) отвергает только ведущий `-`; `@` входит в `_AUTHORED_CHARS`
через `_BARE_CHARS` (стр. 121, 126), поэтому `@scout` печатается голым.

```text
[extra] ascii | at role | ps-interactive=DIFF ps1-file=DIFF cmd-interactive=OK cmd-batch=OK sh-file=OK
    ps-interactive: got ["prompt", "--role", "--dir", "C:\\...\\atrole"]
--- powershell: pasted conduct prompt --role @scout --dir "...\atrole": exit 1
    conduct prompt: error: argument --role: expected one argument
```

Мои пробы: `@` один и `@x,y` — ошибка разбора PowerShell; `a@b` в середине — OK. Закавыченные
`"@scout"`, `"@"`, `"@x,y"` — OK во всех шести исполнителях. `fromfile_prefix_chars` у парсера нет:
`--role @scout` из cmd доходит до `prompt` (exit 0).

### D3. `$`, обратная кавычка, `%VAR%` в корне

Код: docstring `_spelled` (стр. 505–508, 532–538) говорит о раскрытии только для POSIX sh.

```text
x$y : PS  got "...\\x\\unheld" (cmd OK)       sh got "...\\x\\unheld"
t`k : PS  got "...\\tk\\unheld" (cmd OK)       sh: unexpected EOF while looking for matching ``'
%OS%: cmd got "...\\pWindows_NTq\\unheld" (PS OK, sh OK)
```

Сверх стенда: `C:\$Recycle.Bin` → PS `C:\.Bin`, sh `C:$Recycle.Bin`; корень с типографской
кавычкой U+201C → ошибка разбора PowerShell (он читает `“ ” „` как `"`); `\\srv\c$\proj` — PS и
cmd OK (`$\` не переменная).

### D4. Голый `\` в sh

Код: `_BARE_CHARS` (стр. 121) включает `\`; комментарий стр. 119–120 объясняет это корнем.
`run_sh.txt`: `ascii\unheld` → `asciiunheld`; 8.3 → `C:Users73B5~1DOCUME~1...`. Мои пробы:
`C:\Users\Public\proj\` → `C:UsersPublicproj`; `C:\` → `C:`; `\\srv\share\dir` → `\srvsharedir`.
Для cmd и PowerShell голый `\` безопасен (все такие строки OK).

## 3. Новые находки

- **D5, запятая (PowerShell 5.1).** Голый токен с `,` — выражение-массив: элементы после запятой
  разбираются как значения, числа преобразуются, элементы склеиваются через `,` (`probe2.txt`):
  `a,07` → `a,7`, `a,0x10` → `a,16`, `a,1kb` → `a,1024`, `a,1e3` → `a,1000`, `a,.5` → `a,0.5`,
  `01,2` → `1,2`, `scout,07` → `scout,7`; `,x` → `x`; `x,`, `,`, `a,,b`, `a,b,`, `a,@b` — ошибка
  разбора. `a,b` и `c,d\unheld` случайно проходят. Задевает и роли (`,` в `_AUTHORED_CHARS`), и
  корни: `C:\Users\Public\x,07` голым → `...\x,7` (другой каталог). В кавычках — OK везде.
- **D6, ведущая `~` (sh).** `--dir ~` → `/c/Users/...` (`posix_sim-old.txt`). В середине (`DOCUME~1`)
  безвредна.
- **D7, пустой корень.** `conduct doctor --dir ""` из cmd работает (корень — cwd), а напечатанное
  `--dir ""` в PowerShell 5.1 теряет пустой аргумент: `["prompt", "--role", "reviewer", "--dir"]`.
- Мелкие ограничения, которые остаются (раздел 0): `\` как корень в PS 5.1; UNC в sh; MSYS-конверсия
  в Git Bash (`sh-conv`: `/x` → `X:/`, `/` → каталог установки Git) — и в кавычках тоже.
- Наблюдение вне задачи: `docs/first-run-v1.md` и `docs/release-smoke.md` вызывают `& $conduct`, а не
  `conduct` из PATH, так что вставленная строка `conduct ...` в такой установке не найдётся.

## 4. Варианты и измерения

### 4.1 D1: удвоение, нормализация или оба

A — только удвоение хвостовых `\`; B — только нормализация; C — оба (вместе с правилами D2/D4/D5/D6).
`+\` — программа получила один лишний `\` (тот же каталог). Источник: `probe1.txt`.

| Корень | Сегодня | A | C |
| --- | --- | --- | --- |
| `C:\Users\Пользователь\proj\` | PS OK; cmd `proj"`; sh EOF | PS `+\`; cmd, sh OK | `"...proj"`: все OK |
| `C:\Users\Пользователь\My Dir\` | все сломаны | все OK | все OK |
| `C:\Users\Public\proj\` (голый) | PS, cmd OK; sh `C:UsersPublicproj` | как сегодня | все OK |
| `C:\` | PS, cmd OK; sh `C:` | как сегодня | `"C:\\"`: cmd, sh OK; PS `+\` |
| `\\srv\общий\` | PS OK; cmd `общий"`; sh EOF | cmd OK; PS `+\`; sh `\srv\...` | как A |
| `\\srv\my share\` | все сломаны | PS, cmd OK; sh `\srv\...` | как A |
| `C:\Users\Public\a b\\` | везде `a b\` (на один меньше) | все OK | `"...\a b"`: все OK |
| `""` | PS: `--dir` без значения | как сегодня | `conduct doctor`: все OK |

Выбран C. Только A: в PowerShell без пробела каждый корень с хвостом получает лишний `\`, а
следующий отчёт печатает уже `"...\\\\"` — строка растёт с каждым кругом; голые ASCII-корни в sh
не чинятся. Только B: якоря (`C:\`, корень UNC-шары) остаются с хвостом, а `"C:\"` после D4
сломан в cmd и PowerShell. Нормализация — `str(Path(root))`: `C:\x\` → `C:\x`, `C:\x\\` → `C:\x`,
`C:/x/` → `C:\x`, `""` → `.`; якорь не трогается (`C:\` остаётся `C:\`: `C:` означал бы текущий
каталог диска). `..` не схлопывается.

Место — `inspect` (`text_root`), а не `_dir_args`: `tests/test_doctor_argv_doors.py` держит
`_dir_args` в форме «один return из литералов и параметра», вызов внутри него — «дверь». Не
`os.path.normpath`: `os` в `PROBING_MODULES` (`tests/test_init_probing_ban.py`, doctor в `FLOOR`), и
normpath схлопывает `..`.

### 4.2 D2: кавычить или отвергать

Кавычки проверены во всех шести исполнителях — OK. Отказ (как для `-`) убрал бы рабочую команду для
законного id и не помог бы корню: относительный корень `@dir` ломается в PowerShell так же
(`["doctor", "--dir"]`), а корень отвергнуть нельзя. Поэтому одно место — `_spelled`. `@` убран из
`_BARE_CHARS` целиком, без позиционного правила: `a@b` кавычится без нужды, но безвредно (измерено).

### 4.3 D3: документировать (`probe3.txt`)

| Форма | PowerShell 5.1 | cmd | sh |
| --- | --- | --- | --- |
| `"C:\x$y\p"` | `C:\x\p` | OK | `C:\x\p` |
| `'C:\x$y\p'` | OK | кавычки в имени | OK |
| ``"C:\x`$y\p"`` | OK | обратная кавычка в имени | EOF |
| `"C:\x\$y\p"` | `C:\x\\p` | `\$` в имени | OK |
| ``"C:\t`k\p"`` | `C:\tk\p` | OK | EOF |
| ``'C:\t`k\p'`` | OK | кавычки в имени | OK |
| `"C:\p%OS%q"` | OK | `C:\pWindows_NTq` | OK |
| `"C:\p"%^OS%"q"` | два аргумента | OK | `C:\p%^OS%q` |
| `'C:\p%OS%q'` | OK | `'C:\pWindows_NTq'` | OK |

Ни одна форма не обслуживает PowerShell и cmd одновременно, а владелец работает в обоих. Корень —
путь, который читатель набрал сам; значение из карты проекта сюда не попадает (`_AUTHORED_CHARS` не
содержит ни одного из этих символов), так что вектора инъекции нет. Вторая форма кавычек удвоила бы
контракт (чтение в `tests/doctor_printed.py`, docstring-и, тесты) и всё равно ломала бы одну из двух
оболочек. Решение: документировать. Худший случай записать в docstring: `conduct init ... --dir
"C:\x$y\proj"`, вставленная в PowerShell, создаёт каркас в `C:\x\proj` (`init._scaffold` делает
`mkdir(parents=True)`); остальные команды падают громко («cannot inspect ...: not a directory»).

### 4.4 D4: убрать `\` или объявить Git sh неподдерживаемым

Обещаны (`docs/first-run-v1.md`) «Windows · PowerShell» и «macOS / Linux · терминал»; Git sh на
Windows не обещан. Убрать `\` всё же стоит: (1) каталог POSIX с буквальным `\` в имени ломается тем
же правилом в обещанной оболочке (`posix_sim-old.txt`: `a\b` → `ab`); (2) Claude Code на Windows
исполняет команды через Git Bash — агент, вставивший `next:`, попадает в D4 (вывод, не измерен на
самом Claude Code); (3) цена на Windows косметическая: закавыченный Windows-путь в PowerShell 5.1 и
cmd ведёт себя так же (все основные строки `stand3-new.txt` OK), а на кириллическом профиле владельца
кавычки и так стоят всегда.

Влияние на тесты и CI (копия с правкой, тесты без изменений): ASCII basetemp
`C:\Users\Public\pt-o2` — **8 failed**, 93 passed: `test_a_root_is_quoted_exactly_when_bare_would_not_carry_it`
×7 и `test_the_only_shell_syntax_a_printed_command_carries_is_the_readers_own_path`, потому что
собственные копии `BARE_ENOUGH` в `tests/test_doctor.py` и `tests/test_doctor_argv_doors.py`
содержат `\`. Кириллический basetemp — 101 passed: **ноутбук владельца этот класс сбоев не
видит**, там закавычено всё. После сужения копий — 132 passed, 1 skipped (ASCII) и 277 passed,
1 skipped вместе с `test_command_line_cap.py` (кириллица). На CI windows-latest все Windows-пути в
`next:` станут закавыченными; на Linux/macOS меняются только пути с `, @ ~`. Строки `NEEDING_NONE`
на Windows теряют различающую силу (в каждом корне есть `\`), на Linux/macOS CI сохраняют; набор
голых символов независимо от ОС держит новый контрактный тест `spell`.

## 5. Решение (контракт для docstring)

1. `_BARE_CHARS` — только символы, которые cmd, Windows PowerShell 5.1 и POSIX sh читают буквально в
   **любом** месте голого слова. Против сегодняшнего убраны: `\` (escape в sh), `,` (оператор
   массива PowerShell), `@` (splatting PowerShell в начале слова), `~` (tilde в начале слова в sh).
2. `_AUTHORED_CHARS` по содержимому не меняется (буквы, цифры, `-_.,:/@+=`), но задаётся явно и
   больше не подмножество `_BARE_CHARS`. Инвариант: в нём нет ничего, на что любая из трёх оболочек
   реагирует внутри `"..."` (PS: `$`, `` ` ``, `"`, `“ ” „`; sh: `$`, `` ` ``, `\`, `"`; cmd: `%`,
   `"`), поэтому авторский токен печатается голым или в двойных кавычках и везде значит себя.
3. Закавыченный токен: `"` + токен + его хвостовые `\` ещё раз + `"`. Внутренние `\` не трогаются.
4. Корень нормализуется в `inspect`: `str(Path(root))`; после этого разделитель на конце остаётся
   только у якоря.
5. Ограничения (раздел 0 и 4.3) перечислены в docstring `_spelled` честно, с оболочкой и примером.

## 6. Проверка прототипа

Прототип правки — `n3-op\tc` (diff `n3-op\proto-doctor.diff`: doctor.py +7 −4 без docstring-ов).

`stand3` (99 уникальных строк; OK / `+\` / DIFF):

| Исполнитель | Исходный код | С правкой |
| --- | --- | --- |
| ps-i, ps-f | 80 / 2 / 17 | 86 / 1 / 12 |
| cmd-i, cmd-b | 85 / 4 / 10 | 93 / 0 / 6 |
| sh, sh-conv | 72 / 5 / 22 | 87 / 0 / 12 |

С правкой остались только D3 (`x$y`, `` t`k `` ×6 в PS и sh; `%OS%` ×6 в cmd) и `C:\` в PS (`+\`).
В исходном `+\` — хвост `\\`, ставший одним `\`, и `C:\` → `C:` в sh (это уже другой путь).

`e2e3` с настоящим `conduct.exe`: исходный код — вставка в cmd «cannot inspect ...Пользователь-tpl":
not a directory», в PowerShell с пробелом то же, `@scout` в PowerShell — «expected one argument».
С правкой все вставленные строки работают в cmd и PowerShell (`doctor` — отчёт и exit 1, `prompt`
`"@scout"` — exit 0); `conduct doctor --dir "C:\\"` в PowerShell печатает заголовок `C:\\`, а
следующий `next:` снова `"C:\\"` — неподвижная точка.

Тесты-черновик `n3-op\tc\tests\test_doctor_quoting.py` (147 строк, все ≤ 100 символов): на исходном
коде 14 failed, 14 passed, 1 skipped; с правкой зелёные. Тест настоящих оболочек: 1,9–2,3 с
(три прогона), на исходном коде красный со списком всех расхождений. Мутанты (`mutants.txt`, прогон
`test_doctor_quoting.py`, `test_doctor_printed.py`, `test_doctor.py`): все девять красные — см. 7.6.

## 7. Задание для Sonnet: N3 — кавычение напечатанных команд `conduct doctor`

### 7.1 Контекст и рамки

- Репозиторий `C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command`,
  ветка `recovery/2026-10-20`, HEAD `79cd652`. В каждой команде PowerShell сначала
  `. "C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command-Environment.ps1" -Quiet`.
- Прочитать этот документ целиком, `src/conductor/doctor.py`, `tests/doctor_printed.py`,
  `tests/test_doctor_printed.py`, `tests/test_doctor.py` (стр. 160–180, 597–743),
  `tests/test_doctor_argv_doors.py` (стр. 1–110, 340–375), `tests/test_init_probing_ban.py` (стр. 28–62).
- Проверенный черновик тестов и правки: `C:\Users\Пользователь\Documents\Codex\work\n3-op\tc`
  (`src/conductor/doctor.py`, `tests/test_doctor_quoting.py`, `tests/doctor_printed.py`). Им можно
  пользоваться, но docstring-и, комментарии и красный прогон — твоя работа.
- Шаг 0: `git status --short`. Если N2 (`tests/test_doctor.py`, `tests/doctor_printed.py`,
  `tests/test_doctor_printed.py`) ещё не закоммичен, твои правки в этих трёх файлах ложатся поверх
  него: в отчёте перечисли свои ханки по каждому из них отдельно, чтобы их можно было отделить от N2.
  Чужие файлы (`R1.*`, policy_driver/queue/Desk, `N2-REPORT.md`) не трогать.

### 7.2 Красные тесты сначала: новый модуль `tests/test_doctor_quoting.py`

Docstring модуля: что он держит (кавычение напечатанной команды против cmd, Windows PowerShell 5.1 и
POSIX sh), почему отдельно от `test_doctor.py` (лимит 800 строк), откуда фикстуры
(`from tests.test_doctor import commands, lane, ran, report, role_map, write_project`, как в
`test_doctor_claims.py`; цикла нет). Тесты:

1. `test_spell_quotes_what_a_shell_would_change_and_doubles_a_closing_backslash` — параметры
   `(argv, line)`, ожидание `doctor.spell(argv) == line` (Python-литералы):
   - `("doctor", "--dir", "C:\\Мой проект\\")` → `'conduct doctor --dir "C:\\Мой проект\\\\"'`
   - `("doctor", "--dir", "C:\\")` → `'conduct doctor --dir "C:\\\\"'`
   - `("doctor", "--dir", "C:\\a\\\\")` → `'conduct doctor --dir "C:\\a\\\\\\\\"'`
   - `("doctor", "--dir", "C:\\a b")` → `'conduct doctor --dir "C:\\a b"'` (внутренние `\` не удваиваются)
   - `("doctor", "--dir", "ascii\\unheld")` → `'conduct doctor --dir "ascii\\unheld"'` (D4)
   - `("prompt", "--role", "@scout")`, `("prompt", "--role", "a@b")`, `("prompt", "--role", "scout,07")`,
     `("doctor", "--dir", "~")` → тот же токен в двойных кавычках (D2, D5, D6)
   - `("prompt", "--role", "a.b:c/d+e=f_g-h")` → голым (весь новый `_BARE_CHARS` без кавычек)
2. `test_a_crt_program_reads_the_printed_token_back_as_itself` — только Windows:
   `shell32.CommandLineToArgvW(doctor.spell(("--dir", token)))` == `["conduct", "--dir", token]`
   для `C:\Мой проект\`, `C:\`, `C:\a\\`, `\\srv\s p\`, `C:\a b`, `@scout`, `scout,07`
   (`restype = POINTER(c_wchar_p)`, `LocalFree` в `finally`). Это оракул правила CRT без процессов.
3. `test_a_root_typed_with_trailing_separators_is_printed_without_them[1|2]` — пустой каталог
   `tmp_path / "Мой проект"`, `report(capsys, str(root) + os.sep * n, 1)`, единственная команда из
   `commands(out)` оканчивается на `["--dir", str(root)]`, и `main(argv) == 0` (D1 через CLI).
4. `test_an_empty_root_names_no_dir_rather_than_an_empty_one` — `monkeypatch.chdir(tmp_path)`, ни
   одна `check.command` из `doctor.inspect("")` не содержит `--dir` (D7).
5. Охранный (зелёный до и после): `test_an_authored_id_a_shell_can_carry_quoted_still_gets_its_prompt`
   для `@scout`, `a,b`, `scout,07`, `x.y`, `a:b`, `a=b`, `a+b` — печатается `prompt --role <id>`,
   `ran(argv) == 0`. Держит, что `_AUTHORED_CHARS` не сузили вслед за `_BARE_CHARS`.
6. Настоящие оболочки, Windows (`skipif` не win32; ещё `skipif` при
   `shutil.which("powershell.exe") is None`): `test_printed_lines_reach_a_program_from_cmd_and_powershell_as_their_argv`.
   Заглушка — `tmp_path / "argv.py"`, печатает `"ARGV:" + json.dumps(sys.argv[1:])`; программа
   `conduct` подменяется на `"<sys.executable>" "<argv.py>"`, хвост строки после `conduct ` — дословно
   из `doctor.spell`. Случаи: команды `doctor.inspect(str(tmp_path / "Мой проект") + "\\")`,
   `("doctor", "--dir", Path(tmp_path).anchor)`, `("prompt", "--role", "@scout", "--dir", "C:\\p q")`,
   `("prompt", "--role", "scout,07")`, `("doctor", "--dir", "x,07\\unheld")`,
   `("doctor", "--dir", "C:\\Program Files (x86)\\p&q")`.
   cmd — по процессу на строку: `subprocess.run(f'cmd.exe /d /s /c ""{python}" "{stub}" {tail}"')`
   (`/s` снимает именно добавленные внешние кавычки). PowerShell — один процесс
   `powershell.exe -NoProfile -NonInteractive -EncodedCommand <driver>`, где driver читает строки
   `& "<python>" "<stub>" <tail>` из UTF-8 файла и выполняет каждую
   `try { Invoke-Expression $l } catch { 'ERR:' + $_ }`. Без `-File` и без `-ExecutionPolicy`.
   Ожидание: cmd — ровно argv; PowerShell — ровно argv, кроме последнего токена без пробела,
   оканчивающегося на `\`: у него один лишний `\` (документированное поведение 5.1; комментарий в
   тесте). Собирать все расхождения в список и падать одним `assert not wrong, wrong`.
7. Настоящий sh, POSIX (`skipif` win32): `test_printed_lines_reach_a_program_from_posix_sh_as_their_argv`
   — `subprocess.run(["/bin/sh", "-c", f'"$0" "$1" {tail}', sys.executable, str(stub)])` для команд
   `doctor.inspect(str(tmp_path / "Мой проект") + "/")` и `("doctor", "--dir", "a\\b")`,
   `("doctor", "--dir", "rel\\dir\\")`, `("doctor", "--dir", "~")`, `("prompt", "--role", "@scout")`,
   `("prompt", "--role", "a,b")`; ожидание — ровно argv. Здесь он только skipped; механика проверена
   через Git sh (`n3-op\posix_sim.py`), на исходном коде `a\b`, `rel\dir\`, `~` красные.

Прогнать модуль на текущем продукте и сохранить вывод. Ожидаемо на Windows (ASCII basetemp):
**14 failed, 14 passed, 1 skipped** — красные: 8 строк теста 1 (кроме `C:\a b` и голой строки), 2
строки теста 2 (`C:\Мой проект\`, `\\srv\s p\`), тест 3 ×2, тест 4, тест 6. Если красных меньше —
остановиться и разобраться, а не подгонять.

### 7.3 Продукт: `src/conductor/doctor.py`

```python
_BARE_CHARS = frozenset(string.ascii_letters + string.digits + "-_.:/+=")
_AUTHORED_CHARS = frozenset(string.ascii_letters + string.digits + "-_.,:/@+=")
```

```python
    if token and not set(token) - _BARE_CHARS:
        return token
    tail = len(token) - len(token.rstrip("\\"))
    return '"' + token + "\\" * tail + '"'
```

В `inspect`: `text_root = str(Path(root))`. Новых импортов нет (`os` запрещён
`test_init_probing_ban.py`). `spell`, `_spellable`, `_dir_args`, `_FLAG_MARK`, `render`, `run` — без
изменений. Docstring-и и комментарии (английский, как в модуле):

- комментарий `_BARE_CHARS`: пункт 1 раздела 5 с причиной для каждого убранного символа; убрать
  фразу «The backslash and the tilde are here for the one token that is a path»;
- комментарий `_AUTHORED_CHARS`: пункт 2 раздела 5 — содержимое прежнее, не подмножество
  `_BARE_CHARS`, `,` и `@` уходят в кавычках, а не отвергаются, и почему это безопасно;
- `_spellable`: одна фраза — id с `,` или `@` спеллируем и печатается в кавычках;
- `_spelled`: абзац «Double quotes and not single ...» и последний абзац про корень переписать:
  правило CRT для закрывающей кавычки; поведение PowerShell 5.1 (перекавычивает только токен с
  пробелом, поэтому без пробела приходит лишний `\` — после нормализации только у якоря: `C:\` → тот
  же каталог, `\` → `\\` не каталог); что двойные кавычки НЕ нейтрализуют в каждой из трёх оболочек
  (PS: `$`, обратная кавычка, `"`, `“ ” „`; sh: `$`, обратная кавычка, `"` и `\` перед любым из
  них или перед `\`, отсюда UNC `\\srv` → `\srv`; cmd: `%VAR%`, при delayed expansion `!VAR!`); что ни одна форма не обслуживает PS и cmd сразу
  (таблица 4.3 одной фразой); худший случай с `init`; что Git sh не обещан
  (`docs/first-run-v1.md`), но обычные Windows-пути в нём теперь доходят, а MSYS-конверсия ведущего
  `/` — не вопрос кавычек. Сохранить абзацы про два авторских токена и `test_doctor_argv_doors.py`;
- `inspect`: почему корень нормализуется здесь (хвостовой `\` в кавычках — единственное место, где
  CRT и PowerShell 5.1 расходятся; `""` → `.`; якорь сохраняется; не в `_dir_args` — его форму держит
  `test_doctor_argv_doors.py`).

### 7.4 Тестовые копии правила и чтение строки

- `tests/test_doctor.py`: `BARE_ENOUGH = set(string.ascii_letters + string.digits + "-_.:/+=")`;
  `"p,q"` перенести из `NEEDING_NONE` в `NEEDING_QUOTES` и поправить комментарий над ними («other
  six» → «other seven»; отметить, что на Windows каждый корень держит `\` и закавычен). Число строк не
  растёт (788 → 788).
- `tests/test_doctor_argv_doors.py`: тот же `BARE_ENOUGH` (поведения не меняет, держит копии в ногу).
- `tests/doctor_printed.py`: значение закавыченного токена — с хвостовыми `\`, уменьшенными вдвое
  (`_unquoted(inside)`: `tail = len(inside) - len(inside.rstrip("\\"))`, вернуть
  `inside[:len(inside) - tail // 2]`); в docstring `printed_argv` назвать правило CRT. Сверка
  `spell(argv) == line` остаётся и отвергает нечётный хвост.
- `tests/test_doctor_printed.py`: в `test_a_printed_line_reads_back_as_the_argv_it_was_spelled_from`
  добавить строки `("doctor", "--dir", "C:\\Мой проект\\")`, `("doctor", "--dir", "C:\\")`,
  `("prompt", "--role", "@scout")`.

### 7.5 Прогоны

```powershell
$doc = "tests/test_doctor_quoting.py", "tests/test_doctor.py", "tests/test_doctor_printed.py",
       "tests/test_doctor_claims.py", "tests/test_doctor_argv_doors.py",
       "tests/test_init_probing_ban.py"
New-Item -ItemType Directory -Force C:\Users\Public\pt-n3a | Out-Null
python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Public\pt-n3a @doc
python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\pt-n3b @doc `
  tests/test_command_line_cap.py tests/test_file_endings.py
Remove-Item -Recurse -Force C:\Users\Public\pt-n3a, C:\Users\Пользователь\pt-n3b
```

**ASCII basetemp обязателен**: на кириллическом профиле закавычено всё, и сломанные копии
`BARE_ENOUGH` там зелёные. У прототипа было 132 passed, 1 skipped (ASCII) и 277 passed, 1 skipped
(кириллица, с `test_command_line_cap.py`); числа у тебя могут отличаться на число своих строк.
`test_file_endings.py` читает только `git ls-files`: для неотслеживаемых новых файлов окончания,
хвостовые пробелы и длину строк проверить отдельно.
Других потребителей `doctor` в `src/` и `tests/` нет (поиск `doctor.` и `"doctor"`), полный
core-suite не обязателен.

### 7.6 Мутанты (каждый в копии вне репозитория; должен покраснеть)

| Мутант | Ожидаемо красные (прототип, `mutants.txt`) |
| --- | --- |
| M1 убрать удвоение в `_spelled` | тест 1 (3 строки), тест 2 (4), тест 6 — 8 failed |
| M2 вернуть `\` в `_BARE_CHARS` | тест 1 (3), тест 6, 7 тестов `test_doctor.py` — 11 failed |
| M3 вернуть `,` | тест 1 (`scout,07`), тест 6 — 2 failed |
| M4 вернуть `@` | тест 1 (`@scout`, `a@b`), тест 6 — 3 failed |
| M5 вернуть `~` | тест 1 (`~`) — 1 failed (на POSIX CI ещё тест 7) |
| M6 `text_root = str(root)` | тест 3 ×2, тест 4 — 3 failed |
| M7 `_AUTHORED_CHARS = _BARE_CHARS` | тест 5 (`@scout`, `a,b`, `scout,07`) — 3 failed |
| M8 удваивать все `\` в кавычках | 56 failed |
| M9 `_unquoted` без деления хвоста | `test_doctor_printed.py` (2 новые строки) — 2 failed |

Скрипт-образец: `n3-op\mutate.py` (копирует `src`/`tests` во временный каталог, меняет одну
строку, гоняет три файла с `--basetemp C:\Users\Public\pt-om`, убирает за собой).

### 7.7 Ручная проверка в настоящих оболочках

Автотест 6 покрывает cmd и PowerShell 5.1 на CI windows-latest; Git sh на Windows и PowerShell 7 —
только вручную. После правки прогнать на стенде (исправленный `src` репозитория):

```powershell
$w = "C:\Users\Пользователь\Documents\Codex\work\n3-op"
$src = "C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command\src"
$env:PYTHONIOENCODING = "utf-8"
python "$w\stand3.py" $src "$w\s3fix" | Out-File -Encoding utf8 "$w\stand3-fix.txt"
python "$w\e2e3.py" $src "$w\e2e-fix" | Out-File -Encoding utf8 "$w\e2e3-fix.txt"
```

Оба скрипта берут хелперы корпуса из `n3-op\tc\tests` и запускают `conduct` из `.venv` с
`PYTHONPATH=<src>`; работают около минуты.

Критерий: в `stand3` DIFF только у строк `x$y`, `` t`k `` (PS, sh) и `p%OS%q` (cmd), `+\` только у
`C:\` в PS; в `e2e3` все вставленные строки выполняются (`cannot inspect` и `expected one argument`
отсутствуют). Каталоги `s3fix`, `e2e-fix` после сверки удалить.

### 7.8 Критерии приёмки

- Все тесты 7.5 зелёные в обоих basetemp; новый модуль красный на исходном коде ровно в
  перечисленных местах (вывод сохранён в отчёте); все мутанты M1–M9 красные.
- `_AUTHORED_CHARS` по содержимому равен прежнему; ни один id, который сегодня получает `prompt`,
  не теряет его (тест 5).
- Ни одна строка `next:` не печатает закавыченный токен с нечётным хвостом `\`; на стенде остаются
  только ограничения из раздела 0.
- `tests/test_doctor.py` ≤ 800 строк (ожидаемо 788), строки ≤ 100 символов во всех тронутых и новых
  файлах, один перевод строки в конце, без хвостовых пробелов.
- Docstring `_spelled` называет каждое оставшееся ограничение с оболочкой.

### 7.9 Чего не делать

- Не отвергать `@`/`,` в `_spellable` и не сужать `_AUTHORED_CHARS`: это смена поведения, а не
  исправление.
- Не вводить вторую форму кавычек (одинарные, `` ` ``-escape, `^`) и не пытаться «чинить» D3.
- Не нормализовать в `_dir_args` и не импортировать `os` в `doctor.py`; не использовать
  `os.path.normpath`/`resolve()` (меняют смысл пути или лезут в файловую систему).
- Не удваивать внутренние `\` и не трогать `spell`, `render`, заголовок отчёта (там остаётся корень
  как набран).
- Не добавлять Git sh/PowerShell 7 в автотесты и не ставить `-ExecutionPolicy`; не трогать
  `tests/test_command_line_cap.py` (doctor-тестов в `CAPPED` нет, как решено в N2).
- Не раздувать `tests/test_doctor.py`; не править `N2-REPORT.md` и чужие R1.x-файлы.
- Без коммитов, push, stash, checkout, reset, git config.

### 7.10 Отчёт

`docs/recovery/2026-10-20/tasks/N3-REPORT.md` по `TASK-REPORT-TEMPLATE.md`: ханки по файлам (с
пометкой, какие ложатся поверх незакоммиченного N2), красный прогон до правки, зелёные после, мутанты,
ручной стенд, «Не проверено» (PowerShell 7, Git sh в CI, POSIX-тест локально только skipped).

## 8. Не проверено

- PowerShell 7 (`$PSNativeCommandArgumentPassing`) на машине нет. По документации 7.3+ передаёт
  аргументы по правилам CRT; ожидаемо `"C:\\"` → `C:\\` (тот же каталог), остальное как в 5.1. Не
  измерено.
- Интерактивное автодополнение Tab (что PowerShell 5.1 дописывает `\` к каталогу) в
  `-NonInteractive` не воспроизводится; на стенде корни с хвостом подавались argv напрямую.
- POSIX-тест 7 запускался только через Git sh на Windows (механика); на Linux/macOS не запускался.
- Claude Code + Git Bash как путь к D4 — вывод, не измерение.
- Windows CI не запускался; поведение на ASCII-путях смоделировано basetemp `C:\Users\Public\pt-*`.

## 9. Артефакты и уборка

`C:\Users\Пользователь\Documents\Codex\work\n3-op\` (вне репозитория, оставлено для Sonnet и ревью):
`probe.py`/`probe1.txt` (D1–D4 и токены), `probe2.py`/`probe2.txt` (запятые), `probe3.py`/`probe3.txt`
(D3), `stand3.py`/`stand3-old.txt`/`stand3-new.txt`, `e2e3.py`/`e2e3-old.txt`/`e2e3-new.txt`,
`posix_sim.py`/`posix_sim-old.txt`/`posix_sim-new.txt`, `mutate.py`/`mutants.txt`,
`proto-doctor.diff`, копия с правкой `tc\`, рабочие каталоги `p1`–`p3`, `s3old`, `s3new`,
`e2e-old`, `e2e-new`. Свои `pt-o*` в `C:\Users\Public` и `C:\Users\Пользователь` удалены; чужие
`pt-f`, `pt-m3` не тронуты. Стенд `n2-sk` не изменялся.
