# Отчёт по задаче: N1 — BOM для `.ps1` нативных тестов, читаемые отказы, короткий basetemp

- Исполнитель: Claude Code (Sonnet 5.5).
- Исходный commit и ветка: `f2d6833`, `recovery/2026-10-20`.
- Состояние рабочей копии до изменений: много чужих незакоммиченных изменений. R1.2/R1.2b:
  `policy_driver.py`, `seed_routes.py`, `tests/test_command_flow_driver.py`,
  `tests/test_policy_driver_ended.py`, `tests/test_command_line_cap.py`. R3: `desk-scene.js`,
  `browser_tests/*`, `tests/test_desk_motion_wiring.py`. R4: `accept_push.py`, `docs/specs`,
  `tests/test_accept_*.py`, `tests/test_desk_accept_publish.py`. Плюс отчёты в
  `docs/recovery/2026-10-20/tasks/`. Я их не менял, не добавлял в индекс и не коммитил.
- Цель и наблюдаемое ожидаемое поведение: исправить RC1 и RC2 из `N1-NATIVE-CYRILLIC.md` только
  в тестах и документации. Нативные тесты проходят на кириллическом профиле. Если скрипт ребёнка
  не выполнился, тест показывает его вывод читаемо, а не `UnicodeDecodeError`. Код продукта
  (`src/`) не менялся.

## Изменения

| Файл | Что и зачем |
| --- | --- |
| `tests/_ps1.py` (новый, 59 строк) | Один helper `write_ps1(path, text)`: UTF-8 с BOM (`utf-8-sig`), без перевода строк. В docstring объяснено, почему BOM. Рядом читатели вывода ребёнка: `strict_text` (строгий UTF-8, при неудаче `AssertionError` с выводом ребёнка в `oem`), `child_text` (`oem`, `errors="replace"`, только для текста сообщения) и `describe` (статус, код выхода и вывод для assert). Модуль не импортирует ничего Windows-специфичного, поэтому нативные тесты подключают его на верхнем уровне. |
| `tests/os_boundary_box.py` | `write_inner_script` пишет `inner.ps1` через `write_ps1` (было `write_bytes(... .encode("utf-8"))`). |
| `tests/test_process_login_native.py` | `entry.ps1` через `write_ps1`. `facts()` декодирует через `strict_text`: факты по-прежнему строгие. В assert на exit code добавлен `describe(outcome)`. |
| `tests/test_process_loans_native.py` | `entry.ps1` через `write_ps1`. К assert на exit code добавлен `describe`, к сравнению байтов вывода — `child_text`. Само сравнение осталось точным. |
| `tests/test_process_login_native_overlap.py` | Четыре скрипта `.ps1` через `write_ps1`. `child()` использует `describe` в assert и `strict_text` для разбора. |
| `tests/test_process_login_config_native.py` | В assert на exit code добавлен `describe` (его `facts` и `run_child` берутся из `test_process_login_native`). |
| `tests/test_os_boundary_windows.py` | В сообщения двух assert вложенного теста добавлен вывод внешней оболочки (раньше было «the descendant never ran» без причины). Проверки не менялись. |
| `tests/test_ps1_script_encoding.py` (новый, 94 строки) | 4 теста. Два работают везде: BOM и байты текста в `write_ps1`; `strict_text` и `child_text`. Два только на Windows: регрессионный и свидетель (см. ниже). |
| `docs/recovery/2026-10-20/LOCAL-SETUP.md` | Раздел «Тесты и временные пути» (RC2): короткий basetemp, расчёт длины, `windows_path_too_long` — контракт продукта, а не дефект. |

Регрессионный тест `test_windows_powershell_runs_a_script_with_a_cyrillic_literal_from_a_cyrillic_directory`
делает в `tmp_path` каталог `Пользователь-т`, пишет туда через `write_ps1` скрипт с литералом `'т-ль'`
и путём этого каталога, запускает `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`
(без контейнера: он не фактор). Требует exit 0 и ровно `D1-82-2D-D0-BB-D1-8C;True`: вывод только
ASCII, поэтому он не зависит от кодовой страницы консоли. От имени профиля машины тест не зависит.
Свидетель `test_the_same_script_without_the_mark_is_not_read_as_written` пишет тот же скрипт без
BOM и требует, чтобы он не выполнился как написано. Он пропускается, если ANSI-страница системы
UTF-8 (`GetACP() == 65001`): там BOM-less файл читается верно.

Отклонение от задания: в задании basetemp `C:\Users\Пользователь\pt-<n>` назван 24-символьным, а
корень проектов hub равным basetemp + ~33. Измерено: `C:\Users\Пользователь` занимает 21 символ,
`pt-1` даёт 26, `pt-n1a` даёт 28, суффикс `\hclone<k>\personal\ConductProjects` — 33 символа
(34 при двузначном `<k>`). Поэтому basetemp вида `pt-n1<буква>` (28) для
`test_ownership_journals_cli` слишком длинный. Файл прогнан на `C:\Users\Пользователь\n1h2` (26), в
LOCAL-SETUP записан предел 26 символов.

## Проверки

Все прогоны: `python -m pytest -q -p no:cacheprovider --basetemp <путь> <файл>`, окружение
`December-Command-Environment.ps1 -Quiet`, Windows 11 (ANSI 1251, OEM 866), Python 3.12.14,
по одному файлу на процесс. Basetemp кириллический, короткий (`C:\Users\Пользователь\pt-n1<буква>`).

| Команда | Результат | Что доказывает |
| --- | --- | --- |
| `tests/test_process_login_native.py` | 15 passed | RC1 снят: `.ps1` с BOM, факты разбираются строго |
| `tests/test_process_loans_native.py` | 8 passed | то же, байты вывода сравниваются точно |
| `tests/test_process_login_config_native.py` | 4 passed | то же |
| `tests/test_process_login_native_overlap.py` | 10 passed | то же в двух потоках |
| `tests/test_os_boundary_windows.py` | 81 passed (98.9 с) | `inner.ps1` с BOM: вложенный потомок запускается |
| `tests/test_ownership_journals_cli.py`, basetemp `C:\Users\Пользователь\n1h2` (26) | 28 passed | RC2: короткий basetemp достаточен |
| то же, basetemp `...\pt-n1f` (28) | 19 passed, 9 errors | предел реален: 28 символов дают `windows_path_too_long` |
| `tests/test_ps1_script_encoding.py` | 4 passed | регрессионный тест и свидетель зелёные с BOM |
| остальные импортёры изменённых helper-ов, по файлу на процесс: `test_process_login_closed` 8, `test_os_boundary_windows_vendor` 10, `test_os_boundary_windows_runner` 8, `test_os_boundary_windows_protected` 21, `test_os_boundary_host` 18, `test_process_acl_native` 1, `test_process_native_boundary` 6 | все passed | helper-ы не сломали соседей |
| `tests/test_file_endings.py` | 8 passed, 1 failed | см. ниже: падение не из моих файлов |

Красный без BOM (одноразовый плагин `-p nobomps1` в рабочей папке вне репозитория, `SCRIPT_ENCODING = "utf-8"`):
`test_ps1_script_encoding.py` даёт 2 failed (проверка BOM и регрессионный тест) и 2 passed. Регрессионный
тест падает с `ParserError`, прочитанным как cp866: «Отсутствует ")" в вызове метода». Без плагина (с BOM)
те же 4 теста зелёные. Тот же плагин на `test_process_login_native.py` даёт первый отказ уже
с читаемым выводом ребёнка в assert на exit code, а не `UnicodeDecodeError`. Плагин и все
каталоги `pt-n1*` и `n1h2` удалены (17 + 1; `HKCU\...\AppContainer\Mappings`: 0 записей `conduct*`).

`git diff --stat` моих файлов (в рабочей копии одновременно чужие правки):

```
 docs/recovery/2026-10-20/LOCAL-SETUP.md    | 15 +++++++++++++++
 tests/os_boundary_box.py                   |  3 ++-
 tests/test_os_boundary_windows.py          |  8 +++++---
 tests/test_process_loans_native.py         | 17 ++++++++++-------
 tests/test_process_login_config_native.py  |  4 +++-
 tests/test_process_login_native.py         |  9 +++++----
 tests/test_process_login_native_overlap.py |  7 ++++---
 7 files changed, 44 insertions(+), 19 deletions(-)
```

Новые файлы: `tests/_ps1.py`, `tests/test_ps1_script_encoding.py`, этот отчёт.

## Не проверено

- Реальный Windows-раннер CI (ASCII-профиль, ANSI cp1252) не запускался. Что байт 0x82 в cp1252 тоже
  кавычка U+201A, выведено из таблицы кодировки, а не измерено. Измерено на cp1251.
- Свидетель пропускается на системе с UTF-8 как ANSI-страницей, там он ничего не проверяет.
- Полный suite и browser gate не запускались. Прогнаны все импортёры изменённых helper-ов.
- Рекомендация расследования про не-ASCII компонент в basetemp CI не выполнялась: `ci.yml` вне
  этого задания. Регрессионный тест уже ловит класс сбоя в CI независимо от basetemp.
- `strict_text` теперь бросает `AssertionError` вместо `UnicodeDecodeError`: тест по-прежнему
  падает на не-UTF-8 выводе, факты не ослаблены.
- `tests/test_file_endings.py` падает на уже закоммиченном
  `docs/recovery/2026-10-20/tasks/N1-NATIVE-CYRILLIC.md:306`: нет перевода строки в конце файла.
  Файл не мой и не менялся. Все файлы, которые я создал или правил, проверены отдельно
  (хвостовые пробелы, пустая строка в конце, длина строки не больше 100).

## Ревью Opus и правки после него

Ревью Opus 5.5 (workflow `n1-native-ps1-bom`) — `approve_with_notes`, blocker нет.
Повторный прогон по одному файлу на процесс совпал с отчётом:
- 15, 8, 4, 10, 81 и 4 passed;
- `test_ownership_journals_cli`: 28 passed при 27 символах, 9 errors при 28.

Без BOM (одноразовый плагин) регрессионный тест краснеет, `login_native` даёт 8 failed с
читаемым cp866-ParserError в сообщении вместо голого `UnicodeDecodeError`.

Правки Opus:
- Свидетель `test_the_same_script_without_the_mark_is_not_read_as_written`: убрано утверждение
  `returncode != 0`. Оно было строже docstring и на системах с многобайтовой ANSI-страницей
  (cp932/936/949/950) могло дать ложный красный. Осталось `stdout != EXPECTED`.
- `describe` в `tests/_ps1.py` теперь сообщает и `output_truncated`.
- В `LOCAL-SETUP.md` предел 26 символов обоснован решающим случаем: `test_hub_clone_restart`
  (53 каталога `hclone<k>`) при 27 символах даёт 43 ошибки, при 26 — 57 passed.
- Размеры новых файлов исправлены на фактические: 59 и 94 строки.
- В закоммиченном `N1-NATIVE-CYRILLIC.md` добавлен перевод строки в конце: из-за его
  отсутствия падал `tests/test_file_endings.py`. Ошибка Opus при коммите отчёта.

## Ревью Codex

Ожидает. Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit, если создан: нет (без коммитов, push, stash, checkout, reset, `git config`).
- `git status`: мои изменения — 7 изменённых файлов из списка выше и 3 новых
  (`tests/_ps1.py`, `tests/test_ps1_script_encoding.py`, этот отчёт), всё не в индексе. Остальное
  в `git status` (R1.2/R1.2b, R3, R4, их отчёты) принадлежит другим задачам.
- Обновлённые документы: `docs/recovery/2026-10-20/LOCAL-SETUP.md`.
- Следующий конкретный шаг: ревью Codex и коммит тестов и документации одной правкой. Отдельно
  владельцу: добавить перевод строки в конец `N1-NATIVE-CYRILLIC.md`; по желанию добавить не-ASCII
  компонент в короткий basetemp Windows-job в `ci.yml`.
