# CI baseline для продолжения December Command

Проверено 20 октября 2026 года. Это чтение сохранённых артефактов и логов GitHub, без повторного запуска тестов и без изменений продукта.

Основной снимок: `4d0e3af669e783f248cf4c4230e805e76c19836a`, [run 39149580847 от 18 октября](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39149580847). Источники ZIP лежат в наборе `recovery-2026-10-20`; ниже указаны пути внутри ZIP.

## Сводка

| Проверка | Подтверждённый результат |
| --- | --- |
| Windows unit, Python 3.11 / 3.12 | Оба job успешны по сохранённым метаданным GitHub |
| Ubuntu unit, Python 3.11 / 3.12 | В каждом один и тот же failure: неподхваченный `ImportError` Windows launcher |
| macOS unit, Python 3.12 | Тот же один failure |
| macOS unit, Python 3.11 | Тот же failure плюс незавершённое освобождение holder в flow-driver test |
| Ubuntu browser | Normal и reverse green: в каждом завершены все 113 модулей |
| macOS browser | Normal green; reverse: один setup error, все 113 модулей завершены |
| Windows browser | Normal: два упавших модуля; reverse: один. В каждом порядке завершены все 113 модулей |
| Build wheel | Успешно по метаданным GitHub |
| Installed-wheel road Ubuntu / macOS | `success: true` в обоих `report.json` |

«Завершены все модули» не означает, что все тесты прошли. Browser gate работал с `keep_going: true`; `progress: complete` и `result: red` совместимы.

## Unit: воспроизводимые точки для первого задания

Во всех четырёх красных POSIX jobs падает:

```text
tests/test_adapter_boundary_launch.py::test_a_confined_adapter_over_the_shipped_runner_starts_no_task_child
ImportError: Windows process creation is unavailable on this platform
src/conductor/command/adapters/_winlaunch.py:17
```

В исходном тесте, строки 383–399, намеренно вызывается `adapter.confine("win32")`. Его docstring ожидает отказ на не-Windows до запуска задачи; `except adapter.error` должен обработать отказ. Реально наружу вышел `ImportError`. Поэтому это кандидат на дефект перевода платформенной недоступности в штатный отказ; просто пропустить тест на POSIX означало бы не проверить заявленный контракт. Полную цепочку вызовов и правильную границу преобразования исключения ещё нужно разобрать.

Источники:

- [Ubuntu Python 3.11, job 117740282152](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39149580847/job/117740282152): **1 failed, 17094 passed, 544 skipped**, 1140,75 с.
- [Ubuntu Python 3.12, job 117740282218](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39149580847/job/117740282218): **1 failed, 17094 passed, 544 skipped**, 1216,48 с.
- [macOS Python 3.12, job 117740282091](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39149580847/job/117740282091): **1 failed, 17162 passed, 476 skipped**, 1947,96 с.
- [macOS Python 3.11, job 117740282142](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39149580847/job/117740282142): **2 failed, 17161 passed, 476 skipped**, 1824,92 с.

В macOS Python 3.11 дополнительно:

```text
tests/test_command_flow_driver.py::test_rejected_review_completes_the_run[the human rejects the result]
tests/test_command_flow_driver.py:131
assert run.holder() is None and run.automation()[0] == "complete"
AssertionError: assert ('run' is None)
```

Перед assert ожидание `run.plan_state() == "complete"` уже завершилось. Это указывает на рассогласование наблюдаемого завершения плана и освобождения holder в данном запуске. Причина и допустимая модель согласованности пока не доказаны: нельзя исправлять одним увеличением sleep или удалением assert.

Полные четыре лога дополнительно сохранены в соседней с репозиторием папке
`December-Command-evidence/ci-logs/job-<ID>.log`.

## Browser: Windows

`browser-gate-windows-latest.zip`:

1. `bg/gate.json`, модуль `test_desk_status.py`:
   `test_every_rule_of_the_table_says_its_word_in_the_page_and_no_machine_word_reaches_the_text[en]`.
   В `bg/test_desk_status.stdout.txt`: `Page.wait_for_function: Timeout 30000ms exceeded`; рядом Chromium `tcp_socket_win.cc:1148 connect failed: 10055`. Итог **1 failed, 17 passed**.
2. `bg/gate.json`, модуль `test_studio_step_races.py`:
   `test_an_answered_write_stays_its_runs_own_across_navigation`.
   В `bg/test_studio_step_races.stdout.txt`: тот же 30-секундный timeout и `connect failed: 10055`. Итог **1 failed, 11 passed**.
3. `bgr/gate.json`, модуль `test_desk_summary.py`:
   `test_no_region_of_the_desk_carries_a_machine_word_with_every_panel_and_document_open[task-waiting-en]`.
   В `bgr/test_desk_summary.stdout.txt`: прямой `Page.goto: net::ERR_NO_BUFFER_SPACE` при переходе на `http://127.0.0.1:<port>/panel/desk.html#lang=en&task=task-waiting`, плюс `connect failed: 10055`. Итог **1 failed, 45 passed**.

Подтверждено совпадение трёх failures с ошибкой соединения Chromium/Windows. Это ещё не доказательство причины нехватки буферов: утечка, особенности runner, Chromium и нагрузка должны различаться экспериментом. По этим логам нельзя объявить, что нарушена именно бизнес-логика статусов, навигации или локализации.

## Browser: macOS

`browser-gate-macos-latest.zip`:

- `bg/gate.json`: normal green, 113/113 модулей.
- `bgr/gate.json`: reverse red только на `test_studio_rendered.py`.
- Узел: `test_choosing_each_tab_shows_that_screen_and_only_that_screen`.
- `bgr/test_studio_rendered.stdout.txt`: **14 passed, 1 error**, ошибка setup — `Page.wait_for_function: Timeout 30000ms exceeded`.
- В stderr присутствуют `CVDisplayLinkCreateWithCGDisplay failed`, код `-6670`, и предупреждения чтения DNS config. Их причинная связь с timeout не установлена.

Не объединять этот случай с Windows 10055 без отдельного подтверждения.

## AFD-попытка от 13 октября: результат уже известен

Архив `browser-gate-windows-afd-2026-10-13.zip`, commit `cd215778d07c5806399474c2141ef97312a2cee5`, [run 38381468164](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/38381468164).

- В `bg/gate.json` и `bgr/gate.json` оба порядка **green**, в каждом 108/108 модулей, `failures: []`.
- `bg/afd/trace-config.json`: AFD trace действительно стартовал (`start_exit: 0`, `available: true`), круговой файл ограничен 64 МБ.
- `bg/afd/afd-extract.json`: `decoded: true`, 514571 событий, из них 514490 AFD, `eventslost: 0`, `bufferslost: 0`, `parse_error: null`.
- Но **`failures_total: 0`, `failures_read: 0`, `failures: []`**. В этой попытке не произошло целевого падения.
- Временной диапазон декодированных событий — 10:41:40–10:44:55 UTC. Из нулевого счётчика eventslost нельзя заключать, что круговой файл сохранил весь запуск, начавшийся раньше.

Следовательно, трассировка состоялась, но **причину 10055 не поймала**. Не надо снова искать в этом архиве доказанный root cause или называть попытку незапущенной. Разрешение на одну историческую попытку из commit messages не является бессрочным разрешением на новые трассировки; новый эксперимент нужно спроектировать отдельно.

## Как использовать для продолжения

1. Для восстановления окружения достаточно targeted smoke с точно записанными результатами: полный unit suite в CI занимал 19–32 минуты и содержит около 17,6 тысяч тестов.
2. Первое компактное исправление для Claude Code: штатный платформенный отказ у confined adapter на POSIX. Codex проверяет исключения, отсутствие запуска task child, cleanup и сохранение защиты на Windows.
3. Отдельным заданием исследовать согласованность plan completion / holder release. Не смешивать с POSIX import failure.
4. Browser failures вести двумя направлениями: Windows socket 10055 и macOS setup timeout. Сначала использовать сохранённые stdout, host/finish records и минимальное воспроизведение; полный gate normal+reverse нужен на этапе подтверждения широкой исправности.
5. H5 и Desk motion — другие задачи проекта. Устранение перечисленных CI failures само по себе не открывает login-home loan и не подключает motion к production.

Эти результаты характеризуют старый CI commit. Свежий локальный результат на
новом ноутбуке записан отдельно в [BASELINE.md](BASELINE.md).
