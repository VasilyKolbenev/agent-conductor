# Отчёт по задаче: R3. Подключить Desk motion к настоящему Desk

- Исполнитель: Claude Code / Sonnet 5.5.
- Исходный commit и ветка: ветка `recovery/2026-10-20`. HEAD в начале работы `57fe629`, к концу `f2d6833`.
  Коммиты `4ddb1fd`, `a622316` и `f2d6833` добавили только документы recovery. По `git diff --stat 4d0e3af HEAD`
  файлы панели, motion-тестов, bench, `test_studio_module_graph.py` и `test_studio_source.py` не менялись.
- Состояние рабочей копии до изменений: чужие незакоммиченные правки в `tests/test_accept_pull_request.py`,
  `test_accept_push_guard.py`, `test_accept_push_reconcile.py`, `test_command_flow_driver.py`,
  `test_desk_accept_publish.py`, а также неотслеживаемые `R3-DESK-MOTION-BRIEF.md` и `R4-S2-REPORT.md`.
  Во время работы другие агенты добавили свои правки (`accept_push.py`, `policy_driver.py`, `seed_routes.py`,
  native-тесты, отчёты R1.2/R4). Я их не трогал и не включал в изменения R3.
- Цель и наблюдаемое ожидаемое поведение: настоящий `desk.html` на упакованных байтах передаёт каждый `view`
  из `render()` в `watchMotion`. Четыре момента отображаются; при `prefers-reduced-motion: reduce` движения нет,
  плашка есть; reload и reconnect ничего не повторяют; поздний render и смена задачи не рисуют метки на сцене;
  запросов кроме GET нет; слой пропускает нажатия.

## Изменения

Файлы R3 (`git diff --stat`: `desk-scene.js` +5; `test_desk_shell.py` +3; `desk_motion_bench.py` и
`test_desk_motion.py` переписаны; `tests/test_desk_motion_wiring.py` новый, 282 строки).

1. `src/conductor/panel/desk-scene.js` (+5 строк): `import {watchMotion} from "./desk-motion.js";` после импорта
   `studio-participants.js`, вызов `watchMotion(view);` первой инструкцией `mountScene` (до ветки foreign),
   два предложения в шапке. Новых `export` нет. `desk.js` не менялся: 800 строк из 800. `desk-motion*.js`, CSS,
   `desk.html`, граф и реестры motion-guard не менялись.
2. `browser_tests/test_desk_shell.py` (+3): `desk-motion.js` и `desk-motion-model.js` в `DESK_BOOT_ASSETS`.
   Census лежит в `browser_tests/test_desk_shell.py`; файла `tests/test_desk_shell.py` в репозитории нет.
3. `browser_tests/desk_motion_bench.py`: удалена подстановка (`SCENE_IMPORT`, `SCENE_HEAD`, `WIRING_IMPORT`,
   `WIRING_CALL`, `wiring()`, `answering()`, `JS`, цикл `page.route`, лишние импорты). Страница получает
   продуктовые модули как есть. Добавлено:
   - `Desk.panel` и `Desk.take`: последний ответ на каждый файл `/panel/`;
   - `Desk.listen()`: запись запросов (метод, путь);
   - счётчик `fetch` по путям в `INSTRUMENT` (`window.__asked`) и барьер `BOOTED` в `open_desk` (см. «Отличия»).
4. `browser_tests/test_desk_motion.py`: тест подстановки заменён; добавлено 7 тестов (с параметрами 8 прогонов).
5. `tests/test_desk_motion_wiring.py` (новый): 26 тестов source-контракта.

### Новые browser-тесты (настоящий desk, без `page.route` на `/panel/*`)

| Тест | Что доказывает |
| --- | --- |
| `test_the_desk_loads_the_packaged_scene_and_motion_modules_as_they_are` | `desk-scene.js`, `desk-motion.js`, `desk-motion-model.js` получены с 200 и побайтно равны файлам пакета; `#deskMotion` создан |
| `test_a_moment_waits_while_the_scene_is_read_again_and_then_plays_once_on_the_fresh_scene` | пока чтение запуска удержано (сцена `stale`), `calls == []`, плашки нет; после `land` плашка и метки у gate новой сцены; следующий refresh ничего не добавляет |
| `test_a_moment_of_the_task_left_marks_no_scene_now_drawn_even_when_its_read_lands_late` | после смены задачи нет `comet/ring/spark`, `calls == []`; плашка называет прежнюю задачу (правило `planOf`, записано в тесте); поздний ответ и refresh ничего не добавляют |
| `test_a_panel_over_the_scene_keeps_the_plaque_and_draws_no_scene_mark` | при открытой панели плашка есть, меток сцены нет |
| `test_the_motion_layer_writes_nothing_and_asks_for_no_module_after_boot[motion/reduced]` | после `open` только GET; ни одного `/panel/`; пути `/events` или `/command/*`; нет `/command/session` |
| `test_the_motion_layer_lets_a_press_through_where_it_draws_the_plaque` | `pointer-events: none` у слоя и плашки; 9 точек над плашкой попадают не в слой; настоящий клик доходит до элемента под плашкой (не control), записей нет |
| `test_the_motion_layer_lets_a_press_through_where_it_draws_each_mark` | в колбэке `MutationObserver`, без ожидания по времени, центр каждой метки лежит над элементом вне слоя |

Существующие тесты (4 момента в normal, reduced EN/RU, геометрия, счётчик, reload, reconnect, язык, слой) не менялись
и теперь идут на настоящем Desk.

### Source-контракт `tests/test_desk_motion_wiring.py`

Читает код без комментариев (`tests.test_graph_source._code`). Проверяет:
- ровно один импорт `watchMotion` и ровно два упоминания в сцене; вызов первой инструкцией `mountScene`;
- `desk.js` импортирует `mountScene`; `render()` содержит один вызов `mountScene(byId("deskScene"), view, handlers)`;
  `view` содержит ключи `connection`, `foreign`, `tasks`, `runs`, `automation`, `queue`, `taskId`, `run` (разбор ключей,
  а не поиск слова);
- `./desk-motion.js` импортирует только сцена, `./desk-motion-model.js` только `desk-motion.js`; `createDetector()`
  вызывается только в `desk-motion.js`, `watchMotion()` только в сцене;
- файлы bench и `test_desk_motion.py` не вызывают `route(...)` на `/panel/`.

Калибровка: 19 дефектов подсаживаются в настоящий текст (импорт удалён, вызов удалён, вызов после ветки foreign,
вызов под `if`, вызов дважды, второй detector, модель импортирует сцена, `desk.js` импортирует motion, `desk.js`
вызывает watcher, `render` без `mountScene`, `mountScene` дважды, `desk.js` без импорта сцены, `view` без `connection`,
`foreign`, `queue`, `run`, три варианта `route` на `/panel/`); каждый должен покраснеть со своим словом. Дефекты
подсаживаются при запуске теста, а не при импорте модуля: если в рабочей копии вызова нет, тесты краснеют по имени.

## Проверки

Все команды из `C:\...\December-Command` после `. ...December-Command-Environment.ps1 -Quiet`; pytest с
`-q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-s3<суффикс>`.
Полный suite, `browser_tests/gate.py` и native AppContainer-тесты не запускались.

| Команда | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| `tests/test_desk_motion_wiring.py tests/test_desk_motion_model.py tests/test_desk_motion_source.py tests/test_studio_module_graph.py tests/test_studio_source.py tests/test_desk_source.py tests/test_desk_style.py` | Windows, .venv | 274 passed (база Opus 248 + 26 новых) | граф импортов, лимиты размера, motion-guard, новый контракт |
| `tests/test_desk_function_map.py tests/test_desk_address_source.py tests/test_studio_scope.py tests/test_server_panel_assets.py tests/test_desk_docs_map.py tests/test_file_endings.py` | то же | 243 passed, 1 skipped, **1 failed**: `test_file_endings` на чужом файле (см. «Не проверено»). Тот же набор раньше в этой сессии дал 244 passed, 1 skipped, как база (пропуск: нет `hatchling`) | соседние source-проверки |
| `browser_tests/test_desk_motion.py` | Chromium Playwright | 25 passed (база 18: минус 1 замена плюс 8 новых прогонов) | четыре момента, reduced, reload, reconnect, поздний render, сеть, клики на настоящем Desk |
| `browser_tests/test_desk_shell.py` | то же | 12 passed | census с двумя новыми файлами |
| остальные 43 `browser_tests/test_desk_*.py`, каждый отдельным процессом (скрипт `work\r3probe\sweep.ps1`, логи `work\r3run\`) | то же | 907 passed, 0 failed, 0 skipped | подключение не ломает другие Desk-модули |

Итого browser: 45 модулей, 944 passed, 0 failed, 0 skipped. Совпадает с ориентиром Opus (907 + 12 + 18 -> 907 + 12 + 25).

Сводка по модулям (passed, failed везде 0): accept 9, accept_publish 8, binding 7, boot_presses 68, bound_project 23,
closing 11, decision_reread 4, decisions 2, embed 21, feed 34, flow 50, flow_canvas 3, flow_host 1, hash 22, hold 6,
live_selection 1, live_stream 2, map 10, motion 25, people 4, pult 50, queue 9, queue_confirm 3, queue_moves 13,
queue_release 22, queue_skip 15, rail_scene 30, run 2, run_write 1, settled 12, shell 12, status 18, summary 46,
view_mode 44, wizard 16, wizard_cycle 40, wizard_git 44, wizard_git_fresh 9, wizard_git_pending 36,
wizard_git_starter 30, wizard_host 1, wizard_launch 90, wizard_materials 26, wizard_prepare 42, wizard_roles 22.

### Красные без подключения (временные правки, затем возврат)

`desk-scene.js` сохранён копией, правка откатывалась копированием обратно; после каждого возврата SHA-256 файла
`B6CB5871…0830AAA`, `git diff -- desk-scene.js` равен +5 строк.

| Правка | Что покраснело |
| --- | --- |
| закомментирован только вызов `// watchMotion(view);` (импорт остался) | `browser_tests/test_desk_motion.py`: **24 failed, 1 passed** (прошёл только `test_a_language_change_...`: он утверждает лишь «ничего не играет», поэтому зелёный и без подключения). Все 8 новых прогонов красные, в том числе тест упакованных байтов (нет `#deskMotion`). `tests/test_desk_motion_wiring.py`: 6 failed, 20 passed (3 контрольных теста и 3 строки таблицы, где дефект уже в тексте) |
| удалены импорт и вызов | `test_desk_shell.py` census: 1 failed (в ответах нет `desk-motion*.js`); `test_the_desk_loads_the_packaged_...`: 1 failed (`desk-motion.js was never fetched`) |

### Стабильность

Тесты с удержанием чтения (`waits_while...`, `task_left...`) и остальные 5 новых прогонов запущены подряд 6 раз:
6 × 7 passed. Модуль целиком проходил дважды (25 passed в обоих).

## Отличия от задания

1. Отчёт назван `R3-REPORT.md` (по заданию воркфлоу), а не `R3-DESK-MOTION-REPORT.md` из брифа.
2. Census находится в `browser_tests/test_desk_shell.py`, не в `tests/`.
3. В bench добавлены счётчик `fetch` и барьер `BOOTED`, которых нет в брифе. Причина: в первом прогоне
   `test_a_moment_waits_while_...` упал (`Running` вместо `Waiting for your decision`). Слово `open` появляется
   после первого refresh, но первый кадр сервера (`state`) вызывает ещё один полный refresh. Если `hold()`
   поставлен до его конца, он держит чтение этого refresh, а ожидаемое изменение читает уже следующий. Барьер ждёт
   второго чтения `/command/quotas`: desk читает лимиты один раз на каждый завершённый refresh. Это связь с
   поведением people-хоста: если оно изменится, `BOOTED` истечёт по таймауту громко, а не пропустит гонку молча.
4. Имя теста про смену задачи сокращено до `test_a_moment_of_the_task_left_marks_no_scene_now_drawn_even_when_its_read_lands_late`
   (строка длиннее 100 символов).
5. В тесте клика для motion проверяются все метки колбэка, а не только первое кольцо. В reduce вместо слушателя на
   найденном элементе стоит одноразовый capture-слушатель на `document`: он не теряется при перерисовке сцены.
6. Сверх брифа: проверка единственности detector и watcher, запрет `route(...)` на `/panel/` в файлах bench и
   motion-теста, тест панели над сценой (пункт 7 брифа, «по желанию»).

## Не проверено

- POSIX и macOS; прогоны только на Windows. bfcache (`pageshow`), скрытая вкладка и мастер поверх Desk в браузере не
  воспроизводились (как и в анализе).
- Полный core suite и `browser_tests/gate.py`: это R5. Нативные AppContainer-тесты не запускались.
- `tests/test_file_endings.py::test_no_file_this_repository_ships_ends_badly_or_trails_whitespace` сейчас красный
  не из-за R3: `docs/recovery/2026-10-20/tasks/N1-NATIVE-CYRILLIC.md:306: no newline at end of file`. Файл добавлен
  другим агентом в коммите `f2d6833`. Мои файлы проверены тем же правилом (`whitespace_faults`) и чисты.
- Счётчик `[data-attention-count]` в production не рисуется (только в тесте), волна на нём пока неактивна.
- `browser_tests/test_desk_wizard_git_fresh.py` подменяет `desk-transport.js` в сценарии «без двери» через
  `page.route`. К R3 это не относится (motion-тесты `/panel/` не подменяют), но критерий «ни один browser-тест не
  подменяет `/panel/*`» верен для motion-файлов, а не для всего набора.

## Открытые вопросы

Вопросы 6.1 (момент сцены для не самого нового запуска), 6.2 (мастер поверх Desk) и 6.3 (скрытая вкладка) из брифа
решены как решения в `R3.1-DECISIONS.md` (коммит `a622316`), реализация там помечена как отдельный шаг после R3.
Здесь они не реализованы: `desk-motion*.js` по заданию не менялись.

## Ревью Opus и правка после него

Ревью Opus 5.5 — workflow `r3-desk-motion`, ракурсы «жизненный цикл» и «браузерные
доказательства». Каждую находку выше уровня note пытался опровергнуть отдельный скептик.
Оба ракурса дали `approve_with_notes`, blocker нет.

- **Жизненный цикл.**
  - Вызовов `watchMotion` столько же, сколько отрисовок: 50 смен темы дали 50 вызовов,
    50 SSE-кадров — 230 вызовов на 230 отрисовок.
  - В видимой вкладке нет утечек и новых слушателей.
  - Reduced motion корректно переключается на лету.
  - После загрузки — только GET.
  - Слой не перехватывает фокус и нажатия.
- **Доказательства.**
  - Из 12 мутантов 11 краснеют на своём утверждении.
  - Census сверяется на точное равенство.
  - Модуль motion три раза подряд дал 25 passed.
- **Подтверждено, minor — закрыто здесь.** Сброс ожидающих моментов при не-live отрисовке
  (`desk-motion.js:250`) не держался ни одним тестом: мутант `pending = [...pending, ...found]`
  проходил весь модуль, хотя после reconnect повторяет старое событие. Opus добавил
  `test_a_moment_waiting_on_a_stale_scene_when_the_stream_drops_is_not_shown_after_it`
  (по пробе ревьюера, плюс проверка, что следующее изменение играет).
  - Текущий код: 3 из 3 passed.
  - Мутант на копии `src`/`browser_tests`/`tests` вне репозитория: 2 из 2 failed,
    «a moment from before the drop played».
  - Повторные прогоны: `browser_tests/test_desk_motion.py` — 26 passed;
    `browser_tests/test_desk_shell.py` — 12 passed; source-группа (wiring, source, model,
    module graph, studio source, desk style, file endings) — 168 passed.
- **Подтверждён механизм, серьёзность снижена с major — передано в R3.1.** В скрытой вкладке
  каждая устойчивая live-отрисовка при непустом `pending` ставит ещё один rAF-колбэк с
  замыканием на свой `view`. Chromium не вызывает rAF у скрытого документа, поэтому колбэки
  копятся (в пробе — 70 после 20 кадров) и сбрасываются при возврате. Исправление относится к
  `desk-motion.js`, который задание R3 менять запрещало. R3.1 должен проверять `document.hidden`
  до постановки ожидания или держать не больше одного ожидания, а тест скрытой вкладки — считать
  невыполненные rAF.
- **Опровергнуто:** «тест упакованных байтов сверяет только три файла» — заявленный сценарий
  не проходит незамеченным.

## Ревью Codex

Ожидает. Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit, если создан: нет (коммит по указанию Codex).
- `git status` (только файлы R3; остальное в рабочей копии принадлежит другим агентам):
  `M src/conductor/panel/desk-scene.js`, `M browser_tests/desk_motion_bench.py`, `M browser_tests/test_desk_motion.py`,
  `M browser_tests/test_desk_shell.py`, `?? tests/test_desk_motion_wiring.py`, `?? docs/recovery/2026-10-20/tasks/R3-REPORT.md`.
- Обновлённые документы: этот отчёт.
- Следующий конкретный шаг: ревью Codex diff R3 и повторный прогон `browser_tests/test_desk_motion.py` с настоящим
  Chromium; затем R3.1 (решения по старому запуску, мастеру и скрытой вкладке).
