# R3. Desk motion в production Desk: анализ и задание для Sonnet

- Автор анализа: Claude Code / Opus 5.5, 20 октября 2026.
- Исходная точка: ветка `feature/v1-desk-integration`, HEAD `4d0e3af`.
  В рабочей копии до анализа не отслеживались только `AGENTS.md`, `CLAUDE.md` и `docs/recovery/`.
- К концу анализа HEAD стал `57fe629`: другие агенты добавили коммиты `8117fe5`, `6a6d693`,
  `63daddb` и `57fe629` (recovery-документы и исправление boundary R1.1).
  - `git diff --stat 4d0e3af HEAD` по `src/conductor/panel`, motion-тестам, bench,
    `test_desk_shell.py`, `test_studio_module_graph.py` и `test_studio_source.py` пуст. Все ссылки
    ниже верны и для `57fe629`.
  - Незакоммиченные правки других агентов есть в `tests/test_accept_*.py`,
    `tests/test_command_flow_driver.py` и `tests/test_desk_accept_publish.py`. К R3 они не относятся.
- Код продукта и тесты не менялись. Изменён только этот файл. Пробные скрипты лежали вне
  репозитория, в `C:\Users\Пользователь\Documents\Codex\work\r3probe\`.
- Оригиналы redesign-spec, `v1-lanes/reports/2026-10-16-D2-S2.md` и
  `handoffs/D2-to-D1-desk-motion-wiring.md` утеряны. Их содержание здесь не восстанавливается.
  Ниже используются только код, тесты и сообщения коммитов `dc3235b`, `58c17bb`, `7f52237`,
  `4d0e3af` и merge `368a336`.

## 0. Главное

1. **Блокеров нет.** Для подключения в продукте достаточно двух строк в
   `src/conductor/panel/desk-scene.js`: `import {watchMotion} from "./desk-motion.js";` и
   вызова `watchMotion(view);` первой строкой `mountScene`. Именно такой вид D2-S2 заложил в bench
   (`browser_tests/desk_motion_bench.py:83-102`). Заголовок `desk-motion.js:6` тоже говорит, что
   модуль получает view от монтирования сцены. Граф импортов разрешает это ребро
   (`tests/test_studio_module_graph.py:121-127`).
2. **`desk.js` менять нельзя.** В нём ровно 800 строк, а `LINE_CAP = 800`
   (`tests/test_studio_source.py:137,166-170`). Кроме того, `render()` вызывает `mountScene` ровно
   один раз за каждую отрисовку с тем же `view` (`desk.js:171-178`). Поэтому вызов из сцены по
   смыслу равен вызову из `render()`.
3. **Без сопутствующих правок тестов подключение нельзя считать доказанным:**
   - `browser_tests/test_desk_shell.py::test_the_desk_boots_from_its_own_address_with_no_error_and_every_file_answering_200`
     после подключения краснеет. Это проверено: страница дополнительно загружает
     `desk-motion.js` и `desk-motion-model.js`. Перечень `DESK_BOOT_ASSETS` нужно дополнить двумя
     строками.
   - Bench сейчас сам подставляет подключение через `page.route`. Если его оставить, регресс
     «строки подключения удалены из продукта» не покраснеет ни в одном browser-тесте. Подстановку
     нужно удалить.
4. Поведенческие требования R3 уже держит связка detector + `latest` + `unsettled`. Я
   проверил это пробой в Chromium на подключённом через `route` Desk (раздел 7):
   - пока сцена `stale`, ничего не играет;
   - при переключении задачи не появляется ни одной метки на сцене;
   - поздний ответ ничего не запускает;
   - нет запросов кроме GET;
   - плашка пропускает клик.

## 1. Жизненный цикл production render

### 1.1 Загрузка и отрисовка

- `desk.js:800`: `boot()` запускается, если есть `#deskShell` и пять областей.
- `boot()` (`desk.js:759-798`):
  - читает hash;
  - создаёт транспорт (`764`), двери флага и очереди, хосты People/Run/Flow, панели, toggles и мастер (`765-787`);
  - вешает `pagehide → stopStream`, `pageshow(persisted) → panels.resume + startStream` и `hashchange` (`788-792`);
  - затем выполняет `booted = settle(address)` (`797`).
- `settle()` (`desk.js:709-725`): claim → проверка foreign → mode/embed → `load()` →
  `start(address)` (выбор задачи из адреса) → `toggles.finish()` → `render()` → `startStream()`.
- `render()` (`desk.js:168-200`) при каждом вызове собирает **новый объект `view`**
  (`171-176`). Его поля:
  - `locale`, `listed`, `tasks`, `runs`, `automation`;
  - `taskId`, `run`, `connection`, `task`, `foreign`;
  - `actor`, `editing`, `draft`, `refused`, `mode`;
  - `queue`, `flag`, `closing`, `pult`.

  `render()` монтирует `mountRail` (`177`), затем `mountScene(byId("deskScene"), view, handlers)` (`178`) и остальные области. После монтирования он ставит
  `data-connection` (`191`) и скрывает сцену, если открыта центральная панель (`196-197`).
- Состояние меняется только через `move(patch)` (`desk.js:257-262`): сначала новый замороженный
  `state`, затем `render()` и `follow()`. Терминальный (foreign) Desk ничего не принимает (`258`).
- `render()` вызывают очень часто:
  - каждый `move`;
  - каждая смена слова соединения (`746-747`);
  - смена языка (`571`), foreign (`590`), конец загрузки (`723`);
  - хост мастера (`784`), toggles и панели (`onChange: render`, `779`);
  - ответ чтений закрытия (`learnClosing`, `317-319`).

  Это важно для счётчика `latest` в motion.

### 1.2 Как приходят события

- Используется один SSE: `desk-transport.js:177-179` (`new EventSource("/events")`). Его
  открывает `desk-stream.js`, а `desk.js:743-748` (`startStream`) подписывает desk на смену слова
  соединения. Обработчик этой смены задаёт `connection = value`, вызывает `panels.connection(...)` и
  `render()`.
- Кадры SSE только запрашивают чтение (`desk-stream.js:46-54`). `state` требует полного
  перечитывания, `run` — тоже перечитывания, а `refreshStream` в любом случае делает полное.
  Слова соединения:
  - при создании — `connecting` (`88`);
  - на `open` — снова `connecting` и `request(null)` (`56-62`);
  - после каждого перечитывания — `open`, если оно подтвердилось, иначе `closed` (`36`);
  - на `error` — `closed` (`64-71`).
- Периодически списки не опрашиваются. Единственный периодический таймер Desk — минутное
  обновление лимитов в `desk-people-host.js` (реестр `TIMERS` в
  `tests/test_desk_motion_source.py:49-55`).
- `refreshStream` (`desk.js:727-741`):
  1. Выполняет `load(current, true)`. Это фоновая загрузка: области не переводятся в `loading`
     (`328`). Затем выполняется `move({tasks, runs, queue, automation})` (`335`).
  2. Ждёт текущий `selectionRead`.
  3. Заново читает запуск выбранной задачи: `chooseTask(state.taskId, where().run, current)`
     (`735`). Пока чтение идёт, сцена находится в `stale` (`whileReading`, `367-371`).
  4. Возвращает `confirmed && current()`. Обработчик `drain` по этому результату ставит `open` или `closed`.

### 1.3 Reconnect, pagehide/pageshow, reload

- **Обрыв.** `dropped()` (`desk-stream.js:64-71`) увеличивает `generation`, снимает `connected`,
  вызывает `door.dropSession()` и ставит `closed`. Это даёт `render()`.
- **Возврат.** `EventSource` переподключается сам. `opened()` ставит `connecting` и запускает
  полное перечитывание. Ответ, начатый до обрыва, не может стать текущим: `current()` проверяет
  `generation` (`desk-stream.js:31`), а `load` — эпоху `loading` (`desk.js:326-332`).
  После подтверждения ставится `open`.
- **`pagehide`.** `stopStream()` (`desk.js:750-757`):
  - вызывает `panels.suspend()` и `stream.dispose()`;
  - после `dispose` `onConnection` больше не вызывается (`desk-stream.js:11-13,75`);
  - увеличивает `loading` и `choice` и ставит `connection = "closed"`;
  - **`render()` при этом не вызывается.**
- **`pageshow` из bfcache.** Вызывается `startStream()`. Новый `connectDeskStream` сразу ставит
  `connecting` и вызывает `render()`.
- **Reload.** Это новый документ, и всё состояние модулей создаётся заново. Внутри Desk
  `location.reload()` вызывается только с плашки foreign (`desk.js:536-539`).

### 1.4 Переключение выбранной задачи

- Задачу выбирают:
  - кнопка в рельсе (`desk-rail.js:75`);
  - hash: `applyHash → navigate → navigateSelection → chooseTask`, `desk.js:600-606,658-669`;
  - панель запуска: `desk-run-binding.js:4-22`;
  - выход мастера: `desk.js:593-596`.
- `chooseTask` (`376-379`) сохраняет `selectionRead`. `readChoice` (`381-396`) выполняет
  `asked = ++choice`. Если запуска нет, задача сразу попадает в `move` с причиной. Иначе:
  1. `move({taskId, run: whileReading(taskId)})`: `loading` для другой задачи, `stale` для той же.
  2. `readRun` (`342-355`).
  3. Защита `asked !== choice || foreign || !fresh()` (`393`).
  4. `move({run: landed})`.

### 1.5 Защита от устаревшего render

| Защита | Где | Что отсекает |
| --- | --- | --- |
| Эпоха загрузки `loading` | `desk.js:326-332`; растёт в `enterForeign` `580` и `stopStream` `754` | ответ списков от прошлой загрузки |
| Эпоха выбора `choice` | `desk.js:383,393`; `581`, `755`; `desk-run-binding.js:11-12,17-20` | ответ запуска от прошлого выбора |
| Поколение потока `generation`/`current()` | `desk-stream.js:8,31,58,66,77` | перечитывание, начатое до обрыва |
| Цикл `selectionRead` | `desk.js:729-739` | подтверждение `open` до чтения текущего выбора |
| Терминальный `foreign` | `desk.js:258,578-591` | любые ответы после mismatch |
| Фазы сцены `loading` / `stale` | `desk.js:367-371` | сцена, которую вот-вот заменят |

Поздний ответ не доходит до `move`, поэтому не вызывает и `render()`. Но обычных `render()` много. Поэтому motion
должен сам переносить ожидание на следующую отрисовку. Это делает `latest` (раздел 2).

## 2. Контракт `watchMotion(view)`

- **Сигнатура:** `export function watchMotion(view)` (`desk-motion.js:245-258`).
  - **Возвращает** `undefined`: у вызова нет ни отписки, ни handle.
  - **Состояние** хранится на уровне модуля: один `detector` на страницу (`53`), `pending` и
    `latest` (`55-56`). На странице `desk.html` одна сцена, поэтому так и задумано. Если бы в том
    же документе появился второй источник вызовов, он делил бы с первым один detector и один
    `latest`, и оба потока данных смешались бы.
- **Поля view, которые читаются:**
  - `foreign` и `connection` (`isLive`);
  - `tasks.phase` / `tasks.list` и `runs.phase` / `runs.list`;
  - `automation` (`Map`);
  - `queue`: если `null`, это не чтение;
  - `taskId`, `run.phase`.

  Неполный view не роняет вызов: при неопределённом `connection` view считается не live.
- **Шаг одного вызова:**
  1. `layer()` гарантирует слой `#deskMotion` (`79-87`). Это `fixed`-элемент поверх
     `body` с `pointer-events: none`, `z-index: 50` и `aria-live="polite"`.
  2. `latest += 1`.
  3. `found = detector.observe(view)`.
  4. `pending = isLive(view) ? [...pending, ...found] : NONE` (`250`). Сцена с фазой
     `loading` или `stale` (`unsettled`, `233`) ничего не запускает (`251`).
  5. В остальных случаях модуль ждёт два кадра (`drawn`, `237-240`). Если за это время не было
     нового `render()` (`mine !== latest`, `253`), он вызывает `planOf(pending, view.taskId)`,
     очищает `pending` и вызывает `show(plan)` (`224-230`). Если новый `render()` был, ожидание
     пропадает, а `pending` остаётся до следующей устойчивой live-отрисовки.
- **Baseline** (`desk-motion-model.js:111-125`):
  - Любой не live view сбрасывает `previous`: `!foreign && connection === "open"`, `81`.
  - Первое live-чтение после сброса — это baseline, и `found` для него пустой (`120`).
  - Отрисовка без двух готовых списков или с `queue === null` не считается чтением и не сбрасывает
    baseline (`119`).
  - Строка без подтверждения (automation не прочитана, запуск нечитаем) хранит прежний ключ
    (`105-108`).

  Поэтому reconnect и reload не повторяют события. Перед первым `open` всегда идёт `closed` или
  `connecting`; reload создаёт новый detector.
- **Reduced motion:**
  - `motionAllowed()` (`59-61`) возвращает `!matchMedia("(prefers-reduced-motion: reduce)").matches`.
  - Значение спрашивается в `show` (`226`) и при каждом `play` (`70-71`), а не хранится.
  - Плашка показывается **всегда** (`225`). Её текст — `«<заголовок> · <слово>»`, скопированный
    из строки рельса (`207-220`). Она живёт 6 с (`29`, единственный таймер — `later`, `64-66`).
    Одновременно на экране одна плашка. Её объявляет `aria-live`.
  - Метки скрыты от чтения экрана атрибутом `aria-hidden` (`121`).
- **Четыре момента:** `kindOf` и `momentsOf` (`desk-motion-model.js:86-101`).

| Момент | Переход ключа | Что рисуется при разрешённом движении | Код |
| --- | --- | --- | --- |
| `accepted` | `not_started → running`, в том числе для новой задачи, которая уже идёт: `entered` + `accepted` | комета от первого участника к работающему и два кольца | `146-153` |
| `to_you` | любой ключ → `waiting_you` | комета к ожидающему gate, две янтарные волны и волна на `[data-attention-count]`, если счётчик есть | `156-172` |
| `finished` | `running` или `waiting_you` → `outcome_succeeded` | два кольца и 8 искр в конце плана | `175-184` |
| `entered` | задачи не было в прошлом чтении | ореол вокруг строки рельса, не больше 3 (`ENTRY_CAP`) | `195-203` |

  Не считаются моментами: resume, ответ на gate, failure, `outcome_succeeded → running`
  (`kindOf`). `planOf` (`129-138`) строит:
  - одну плашку для самого срочного момента: `to_you > finished > accepted > entered`;
  - момент сцены — только для `view.taskId`;
  - до трёх ореолов `entered`.

  Тайминги не превышают 1200 мс (`17,22-31`); это держит `tests/test_desk_motion_source.py`.
- **Что делает bench** (`browser_tests/desk_motion_bench.py`):
  - поднимает настоящий `server.build` над seed-проектом (`203-206`);
  - переписывает ответы `/command/runs` и `/command/tasks` (`Staged`, `115-132,218-219`);
  - отправляет настоящий SSE-кадр `publish_state` (`163-165`);
  - записывает вызовы `animate` и добавленные `[data-fx]` (`INSTRUMENT`, `62-79`);
  - **подставляет строки подключения**: `wiring()` (`89-102`) и
    `page.route("**/panel/desk-scene.js")` (`220-221`).
- **Почему bench не доказывает подключение:**
  - Страница исполняет изменённый в памяти `desk-scene.js`, а не упакованный.
  - `test_the_page_is_served_the_two_wiring_lines_only_while_the_product_lacks_them`
    (`browser_tests/test_desk_motion.py:77-91`) зелёный в обеих ветках.
  - Если строки исчезнут из продукта, bench вставит их снова, и все 18 тестов останутся
    зелёными. Цепочка `desk.html → desk.js → desk-scene.js → desk-motion.js` на упакованных
    байтах не проверяется нигде.

## 3. Точки подключения

### 3.1 Где вызывать

Первой инструкцией в `mountScene` (`desk-scene.js:54-55`) поставить `watchMotion(view);`, а
импорт добавить после импорта `studio-participants.js` (`13-16`).

- `mountScene` вызывается ровно один раз за `render()` (`desk.js:178`). Других вызовов нет:
  поиск `mountScene(` по `src/conductor/panel` это подтверждает. View тот же, что и у всех областей;
  состояние не дублируется.
- Первая строка нужна до ветки foreign (`57-60`). Тогда терминальный view тоже дойдёт до
  detector и сбросит его, и вызов останется безусловным для всех фаз.
- Отрисовка откладывается на два кадра. К этому моменту `render()` уже выставил `hidden` у сцены
  (`desk.js:196-197`), перерисовал рельс (`177`) и мастер. `stageOf()` при скрытой сцене
  возвращает `null` (`desk-motion.js:103`).
- `desk.js` не трогается: 800/800 строк. Импорт в `desk.js` разрешён графом (`test_studio_module_graph.py:87`), но
  потребовал бы рефакторинга ради места. В минимальный diff это не входит.

### 3.2 Baseline при reconnect/reload

Добавлять ничего не нужно. Нельзя добавлять собственную память, `sessionStorage`/`localStorage`
(запрещены `SEALED`, `tests/test_studio_source.py:107-110`) или ручной сброс из `desk.js`.
Последовательность reconnect в продукте:

1. `closed`: `render`, сброс.
2. `connecting`: `render`, сброс; фоновое перечитывание отрисовывается при `connecting`, снова сброс.
3. `open`: `render`, baseline.
4. Следующий кадр сравнивается с этим baseline.

bfcache (`pageshow`) сначала отрисовывает `connecting`, поэтому `previous` из прошлой жизни не
используется.

### 3.3 Поздний render и смена задачи

- Пока чтение запуска не пришло, сцена находится в `loading` или `stale`, и `watchMotion` не
  ставит ожидание (`251`).
- В `refreshStream` переход `move(списки)` → `move(run: stale)` проходит в микрозадачах
  (`await load`, `await selectionRead`). Поэтому `render(stale)` всегда успевает раньше двух
  кадров и отменяет ожидание, поставленное на старой сцене.
- После смены задачи `planOf` получает `view.taskId` новой сцены, и момент чужой задачи на сцене
  не играет. Плашка и ореолы относятся к рельсу и остаются; так задумано.
- Поздний ответ отсекает `choice` (`desk.js:393`). До `render` он не доходит.
- Всё это проверено пробой (раздел 7).

### 3.4 Сеть и клики

- Сеть:
  - `desk-motion.js` импортирует только `command-view.js` и модель
    (`test_studio_module_graph.py:102-103`);
  - `fetch`, `EventSource` и `navigator.` разрешены только транспорту
    (`test_studio_source.py:112,216-241`);
  - динамический `import(` запрещён (`SEALED`).
- Клики:
  - у слоя `pointer-events: none`, и это свойство наследуется плашкой и метками;
  - проба: `elementFromPoint` в центре плашки возвращает элемент сцены под ней.

### 3.5 Граф импортов и размеры

Новое ребро `desk-scene.js → desk-motion.js` цикла не образует. Замыкание `desk-motion.js` —
`command-view.js → command-projection.js`, модель `→ desk-status.js`,
`studio-taskruns.js → studio-model.js`; ни один из них не ведёт обратно к сцене.

| Файл | Строк | Лимит | Статус |
| --- | --- | --- | --- |
| `src/conductor/panel/desk.js` | **800** | 800 | заполнен, не менять |
| `src/conductor/panel/desk-scene.js` | 69 | 800 | +2 строки кода, комментарий |
| `src/conductor/panel/desk-motion.js` | 258 | 800 | не менять |
| `src/conductor/panel/desk-motion-model.js` | 138 | 800 | не менять |
| `src/conductor/panel/studio-participants.js` | 687 | 800 | ближе всех к лимиту из соседей; не трогать |
| `src/conductor/panel/desk-stream.js`, `desk-transport.js` | 99, 272 | 800 | не менять |
| `src/conductor/panel/desk.css` | 465 | 800 (`test_desk_style.py:38`) | не трогать |
| `browser_tests/desk_motion_bench.py` / `test_desk_motion.py` | 239 / 245 | нет | меняются |
| `tests/test_desk_motion_source.py` | 585 | нет | не менять |

У тестов лимита строк нет. Действуют правила дома:
- строки не длиннее 100 символов (`tests/test_command_line_cap.py`, для новых файлов не обязательно, но принято);
- файл заканчивается ровно одним переводом строки (`tests/test_file_endings.py`).

## 4. Ограничения и риски

### 4.1 Что гарантированно изменится в существующих тестах

- `test_desk_shell.py::test_the_desk_boots_..._answering_200` (`browser_tests/test_desk_shell.py:273-279`)
  краснеет. Проба показала: `extra = ['desk-motion-model.js', 'desk-motion.js']`, `missing = []`.
  Нужно добавить две строки в `DESK_BOOT_ASSETS` (`55-127`).
- `test_desk_motion.py::test_the_page_is_served_the_two_wiring_lines...` останется зелёным
  в ветке `carried`, но перестанет что-либо доказывать. Его нужно заменить вместе с удалением
  `wiring()` (раздел 5).

### 4.2 Прогон остальных Desk browser-модулей с подключением, подставленным через route

Пробный pytest-плагин вне репозитория подставлял подключённый `desk-scene.js` в каждый
browser context. Модули запускались по одному процессу pytest. Итог: 43 модуля, 907 passed,
0 failed. Кроме census, ни один существующий Desk browser-тест подключение не ломает.
Подробности — в разделе 7.4.

### 4.3 Поведение, которое стоит знать до ревью (не дефекты подключения)

- **Плашка момента другой задачи.** Если до показа человек переключился на другую задачу, плашка
  называет момент прежней задачи, а меток на сцене нет. Так задумано в `planOf`.
- **Счётчик `[data-attention-count]` в продукте не рисуется.** Поиск по `src/` находит его только
  в `desk-motion.js:46`. Волна на счётчике в production пока неактивна; тест подсаживает счётчик сам.
- **Отказ перечитывания гасит момент.** Если перечитывание запуска выбранной задачи завершилось
  неудачей, `refreshStream` вернёт `false` и `drain` поставит `closed`. Ожидающие моменты сбросятся,
  и момент не покажется. Это консервативно: Desk не говорит того, за что не может поручиться.

### 4.4 Что нельзя менять в R3

- `desk.js`: лимит, а также контракты эпох и потока.
- `desk-motion.js` и `desk-motion-model.js`: семантика моментов, тайминги, `play`/`later`/`motionAllowed`.
- Реестры `TIMERS`, `MEDIA`, `ANIMATORS` в `tests/test_desk_motion_source.py`.
- `desk-stream.js`, `desk-transport.js`, `server_assets.py`, CSS, `desk.html`.
- Таблица разрешений графа: нужное ребро уже есть.
- `tests/test_desk_motion_model.py`: семантика модели.
- `src/conductor/command/**` и `tests/test_execution_boundary.py`: там работают другие агенты.

## 5. ЗАДАНИЕ ДЛЯ SONNET

```text
Задача: R3 — подключить готовый Desk motion к production Desk.
Исходный commit: актуальный HEAD feature/v1-desk-integration по согласованию с Codex
(на конец анализа 57fe629; файлы R3 с 4d0e3af не менялись — перед началом проверить
`git diff --stat 4d0e3af HEAD -- src/conductor/panel browser_tests tests/test_desk_motion*.py`).
Работать в отдельной ветке/worktree, без push; commit — по указанию Codex. Чужие незакоммиченные
файлы (tests/test_accept_*.py, tests/test_command_flow_driver.py, tests/test_desk_accept_publish.py)
не трогать и не включать в diff.
Перед началом каждой команды PowerShell:
  . "C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command-Environment.ps1" -Quiet
Ничего не устанавливать. pytest всегда с коротким basetemp:
  python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-s3<буква> ...
Прочитать перед правкой: этот файл целиком; src/conductor/panel/desk.js (168-200, 325-396,
727-757), desk-scene.js, desk-motion.js, desk-motion-model.js, desk-stream.js;
browser_tests/desk_motion_bench.py, test_desk_motion.py, test_desk_shell.py (55-127, 273-279),
desk_hold.py (Hold, read_again, land_read, close_context).
```

### 5.1 Цель

Настоящий `desk.html` на упакованных байтах передаёт каждый `view` из `render()` в
`watchMotion`. Цепочка: `desk.js:178 → mountScene → watchMotion`. Четыре момента
отображаются; reduced motion, baseline, защита от поздней отрисовки, отсутствие сетевых записей
и пропуск кликов доказаны browser-тестами без подстановки модулей.

### 5.2 Файлы, которые можно менять (и только их)

1. `src/conductor/panel/desk-scene.js`:
   - добавить `import {watchMotion} from "./desk-motion.js";` сразу после импорта из
     `./studio-participants.js`;
   - добавить `watchMotion(view);` первой строкой тела `mountScene`, до `participantSelection` и до
     ветки foreign;
   - в шапке дописать одно-два предложения: каждый view сначала получает модуль переходов,
     он рисует на своём слое и не читает и не пишет ни одной двери;
   - новых `export` не добавлять: `tests/test_desk_source.py:570-575` требует только `mountScene`.
2. `browser_tests/desk_motion_bench.py`:
   - удалить подстановку: `SCENE_IMPORT`, `SCENE_HEAD`, `WIRING_IMPORT`, `WIRING_CALL`, `wiring()`,
     `answering()`, `JS`, цикл `page.route` в `open_desk` и ставшие лишними импорты;
   - переписать абзац docstring про подстановку: страница теперь получает продуктовые модули
     как есть;
   - допустимо добавить в `Desk` запись запросов (метод и путь) и маленькие помощники для
     новых тестов.
3. `browser_tests/test_desk_motion.py`:
   - заменить тест подстановки (`77-91`);
   - добавить новые тесты из 5.4;
   - существующие тесты не ослаблять.
4. `browser_tests/test_desk_shell.py`: в `DESK_BOOT_ASSETS` добавить `"desk-motion.js": 200`
   и `"desk-motion-model.js": 200` с комментарием о переходах сцены. Ничего другого не менять.
5. `tests/test_desk_motion_wiring.py` — новый source-контракт (5.4.A).
6. `docs/recovery/2026-10-20/tasks/R3-DESK-MOTION-REPORT.md` — отчёт по
   `TASK-REPORT-TEMPLATE.md`.

Если окажется, что нужен любой другой файл, остановиться и описать причину в отчёте.
Расширять область самостоятельно нельзя.

### 5.3 Ожидаемый жизненный цикл после правки

1. Загрузка. Первый `render()` создаёт `#deskMotion` в `body`: пустой, `pointer-events: none`.
   `connection` равен `closed` или `connecting`, движения нет.
2. Поток открыт. Отрисовка с `connection === "open"` берёт baseline. Ничего не играет и
   плашки нет.
3. Кадр SSE и перечитывание при `open`:
   1. `move(списки)` даёт момент.
   2. `move(run: stale)` откладывает показ.
   3. Ответ запуска (`ready`) через два кадра показывает план.
   4. Плашка появляется всегда. Метки — только без reduce и только если сцена видна.
4. Смена задачи до показа: момент сцены прежней задачи не играет. Плашка и ореолы возможны.
5. Обрыв или reconnect: `closed` и `connecting` сбрасывают, первое `open` — новый baseline,
   изменения за время обрыва не показываются. Reload — новый detector, то же поведение.
6. Foreign: view сбрасывает detector. Ничего не играет.

### 5.4 Тесты

**A. Source-контракт: `tests/test_desk_motion_wiring.py`.** Код читать без комментариев через
`tests.test_graph_source._code` или `tests.test_panel_cascade.strip_comments`. Каждая
проверка — функция над текстом, а таблица дефектов подаёт ей подсаженный дефект, как в
`test_desk_motion_source.py`.

1. `desk-scene.js` содержит ровно один `import {watchMotion} from "./desk-motion.js";`.
   `watchMotion` встречается ровно дважды: в импорте и в вызове.
2. Первая инструкция тела `export function mountScene(mount, view, handlers) {` — `watchMotion(view);`.
3. В `desk.js` есть `import {mountScene} from "./desk-scene.js";`. Внутри
   `function render()` ровно один вызов `mountScene(byId("deskScene"), view, handlers)`, и объект
   `view` в `render()` содержит поля `connection`, `foreign`, `tasks`, `runs`, `automation`,
   `queue`, `taskId`, `run`. Это и есть контракт цепочки, начинающейся в `desk.js`.
4. Во всём `src/conductor/panel/*.js` модуль `./desk-motion.js` импортирует только `desk-scene.js`,
   а `./desk-motion-model.js` — только `desk-motion.js`. Второго detector быть не должно.
5. Калибровка: каждая проверка краснеет на своём дефекте, подсаженном в настоящий текст:
   - импорт удалён;
   - вызов удалён;
   - вызов перенесён после ветки foreign;
   - вызов обёрнут в `if`;
   - `desk.js` тоже импортирует `desk-motion.js`;
   - `render()` больше не вызывает `mountScene`;
   - из `view` пропало `connection`.

**B. Browser: `browser_tests/test_desk_motion.py`.** Работать на настоящем `desk.html`, без
`page.route` на `/panel/*`.

1. Заменить тест подстановки на `test_the_desk_loads_the_packaged_scene_and_motion_modules_as_they_are`:
   - записать ответы `/panel/desk-scene.js`, `/panel/desk-motion.js`, `/panel/desk-motion-model.js`;
   - у каждого статус 200 и `response.body()` побайтно равен файлу из `src/conductor/panel`;
   - `#deskMotion` существует после загрузки.
2. Существующие тесты должны пройти без изменений смысла. Они становятся production-доказательством:
   - normal motion по `accepted`, `to_you`, `finished` (`113-131`) и `entered` (`134-146`);
   - reduced motion по трём моментам сцены в EN/RU (`94-110`) и `entered` (`149-157`);
   - геометрия (`160-178`) и счётчик (`181-189`);
   - reload (`192-204`), reconnect (`207-222`), язык (`225-232`), слой (`235-245`).
3. Новый `test_a_moment_waits_while_the_scene_is_read_again_and_then_plays_once_on_the_fresh_scene`:
   1. Motion разрешён. Поставить `Hold(desk.page, "**/command/runs/run-working/controls")`
      и выполнить `.hold()`.
   2. `desk.change("waiting_you")`. Ждать `#deskScene[data-state="stale"]` и `QUIET`.
   3. Проверить `desk.fx() == {"calls": [], "added": []}` и `desk.plaque()` count 0.
   4. `controls.land()`. Ждать `ready`, затем плашку `Fix lost text · Waiting for your decision`.
   5. Проверить, что вызовы есть, волны рядом с gate новой сцены (переиспользовать
      `CENTRES`/`near`), а после `refreshed()` число вызовов не выросло: показ однократный.
4. Новый `test_a_moment_of_the_task_left_plays_no_mark_on_the_scene_now_drawn_even_when_its_read_lands_late`:
   1. Как в п. 3: hold controls и `change("waiting_you")`, сцена `stale`.
   2. Нажать `#deskRail [data-task-id="task-closed"]`. Ждать `aria-pressed="true"`, сцену `ready` и `QUIET`.
   3. Проверить: в `added` нет `comet`, `ring`, `spark`; `calls == []`. Плашка равна тексту
      прежней задачи; это поведение `planOf` — записать в тест комментарием.
   4. `controls.land()`, `desk.refreshed()`, `QUIET`. По-прежнему нет вызовов и меток сцены.
5. Новый `test_the_motion_layer_writes_nothing_and_asks_for_no_module_after_boot` для обоих
   режимов (параметр `motion`):
   1. Записывать `page.on("request")` с момента после `open`.
   2. Выполнить один момент сцены и вход новой задачи.
   3. Проверить:
      - ни одного метода, кроме GET;
      - ни одного запроса `/panel/` после загрузки;
      - каждый путь равен `/events` или начинается с `/command/`;
      - нет `/command/session`: сессию запрашивает только запись.
6. Новый `test_the_motion_layer_lets_a_press_through_where_it_draws`.
   - **Reduce.** Плашка видна. `getComputedStyle` слоя и плашки дают `pointerEvents === "none"`.
     `elementFromPoint` в центре плашки возвращает элемент вне `#deskMotion`. Настоящий
     `page.mouse.click` в этой точке доходит до элемента под ней (проверить флаг одноразового
     слушателя, который тест вешает на `elementsFromPoint(...).find(не слой)`). В пробе под
     плашкой был `.studio-step-flow__body`. Если там окажется элемент управления, который пишет,
     сместить точку внутри плашки: тест не должен запускать запись.
   - **Motion.** Один `evaluate` с Promise. Первый добавленный `[data-fx="ring"]` обрабатывается в
     `MutationObserver`, и в том же колбэке `elementFromPoint` в его центре возвращает элемент вне
     слоя. Ожидание по времени не использовать.
7. По желанию, если укладывается без хрупкости, добавить
   `test_a_panel_over_the_scene_keeps_the_plaque_and_draws_no_scene_mark`: открыть
   `#deskRunToggle`, выполнить `change("waiting_you")`, проверить плашку и отсутствие
   `comet`/`ring`.

Правила для тестов bench сохраняются: ничего не ждать по времени (`wait_for_timeout` и sleep
запрещены). «Ничего не случилось» проверяется после `desk.refreshed()` и `QUIET`. Каждое окно
закрывается через `close_context`, а в конце проверяется `desk.problems == []`.

### 5.5 Какие проверки запустить (каждый browser-модуль — отдельным процессом)

Source:

```text
python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-s3a tests/test_desk_motion_wiring.py tests/test_desk_motion_model.py tests/test_desk_motion_source.py tests/test_studio_module_graph.py tests/test_studio_source.py tests/test_desk_source.py tests/test_desk_style.py tests/test_desk_function_map.py tests/test_desk_address_source.py tests/test_studio_scope.py tests/test_server_panel_assets.py tests/test_desk_docs_map.py tests/test_file_endings.py
```

Базовая линия Opus на `4d0e3af` для этого набора без нового файла: 248 + 244 passed и 1
skipped (`hatchling` не установлен).

Browser:
1. `browser_tests/test_desk_motion.py`. Базовая линия: 18 passed за 77 с.
2. `browser_tests/test_desk_shell.py`. Базовая линия: 12 passed.
3. Затем по одному все остальные `browser_tests/test_desk_*.py`, каждый своим процессом
   pytest. Список и ожидаемые числа — в разделе 7.4.

Полный suite и `browser_tests/gate.py` не запускать: это R5 и ревью Codex. В отчёте указать
точные команды и числа passed/failed/skipped по каждому модулю.

### 5.6 Критерии приёмки

1. `desk.js` не изменён и по-прежнему ≤ 800 строк. В `desk-scene.js` добавлены импорт,
   вызов первой строкой `mountScene` и поправлен комментарий. Изменения в `desk-motion*.js` нет.
2. Ни один browser-тест не подменяет `/panel/*`. Тест 5.4.B.1 доказывает, что исполняются упакованные байты.
3. Четыре момента играются на настоящем Desk; таймингов больше 1200 мс нет; метки уходят со слоя.
4. При reduce `calls == []`, меток нет, плашка с текстом на EN/RU есть и уходит.
5. Reload и reconnect поверх изменённого проекта ничего не играют и не показывают, а
   следующее изменение играет.
6. Поздняя отрисовка и смена задачи не дают меток на сцене (5.4.B.3–4).
7. Нет запросов кроме GET и запросов `/panel/` после загрузки (5.4.B.5). Слой пропускает
   клики (5.4.B.6).
8. Перечисленные source-тесты и все Desk browser-модули по одному зелёные. Каждое отличие от
   раздела 7.4 объяснено.
9. Отчёт `R3-DESK-MOTION-REPORT.md` заполнен по шаблону: команды, числа, непроверенное, `git status`.

### 5.7 Чего не делать

- Не менять `desk.js`, `desk-motion.js`, `desk-motion-model.js`, `desk-stream.js`,
  `desk-transport.js`, `server_assets.py`, CSS, `desk.html` и таблицу графа.
- Не ослаблять, не удалять и не скипать существующие проверки: реестры motion-guard,
  census в `test_desk_shell.py`, утверждения `test_desk_motion.py`.
- Не хранить состояние motion в `state` Desk, в storage или в адресе. Второй detector или
  второй вызов `watchMotion` не добавлять.
- Не добавлять `setTimeout`, `matchMedia`, `animate`, CSS-анимации и transition. Не ждать по
  времени в тестах.
- Не трогать `src/conductor/command/**` и `tests/test_execution_boundary.py`: там работают
  другие агенты.
- Не выдумывать визуальные требования «5.5» сверх уже реализованного модуля.
- Не выполнять `git push`, `git config`, `stash`, `reset` и `checkout` чужих файлов.

## 6. Открытые вопросы для Codex/владельца

1. **Сцена показывает не самый новый запуск задачи.** Такое возможно через `run=` в адресе или
   панель запуска (`desk-run-binding.js:4-9`). `planOf` сравнивает только `taskId`
   (`desk-motion-model.js:134`), а `stageOf` берёт якоря той сцены, что нарисована
   (`desk-motion.js:101-117`). Поэтому `to_you` или `finished` нового запуска проиграются на
   участниках и gate старого. Нужно решить:
   - принять как есть;
   - либо отдельным маленьким шагом после R3 (это правка модели и model-теста) показывать
     момент сцены только тогда, когда `view.run.detail.run.run_id` совпадает с самым новым
     запуском задачи.

   `accepted` это не затрагивает: у `not_started` прежнего запуска нет.
2. **Мастер (`.desk-wizard-shell`, `z-index: 20`) открыт поверх Desk.** Слой motion
   (`z-index: 50`) нарисует плашку, ореол и метки сцены поверх мастера. Под оверлеем сцена не
   `hidden`, поэтому `stageOf` её видит. Нужно решить, допустимо ли это или движение и плашку
   надо гасить, пока мастер открыт. Без правки модуля это не сделать, а `desk.js` заполнен.
3. **Скрытая вкладка.** `requestAnimationFrame` в фоне не вызывается, поэтому моменты копятся
   в `pending`, если поток оставался `open`. Сыграет одна плашка, момент сцены и до трёх ореолов
   при возврате к вкладке. Это не повтор после reconnect или reload, и критерии R3 не нарушает.
   Нужно подтвердить, что такой «догоняющий» показ желателен.

## 7. Что я запускал

Все команды выполнялись из корня репозитория после
`. "C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command-Environment.ps1" -Quiet`.

### 7.1 Source-тесты на `4d0e3af`

```text
python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-o3a tests/test_desk_motion_model.py tests/test_desk_motion_source.py tests/test_studio_module_graph.py tests/test_studio_source.py tests/test_desk_style.py tests/test_desk_source.py
→ 248 passed in 55.62s

python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-o3e tests/test_desk_function_map.py tests/test_desk_address_source.py tests/test_studio_scope.py tests/test_server_panel_assets.py tests/test_desk_docs_map.py tests/test_file_endings.py
→ 244 passed, 1 skipped in 11.44s   (skip: tests/test_server_panel_assets.py:710, нет модуля hatchling)
```

### 7.2 Browser-тесты на `4d0e3af` (без правок)

```text
python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-o3b browser_tests/test_desk_motion.py
→ 18 passed in 77.06s      (с подстановкой bench, как сейчас в репозитории)

python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-o3c browser_tests/test_desk_shell.py
→ 12 passed in 7.48s
```

### 7.3 Проба подключённого Desk (вне репозитория)

Скрипт `C:\Users\Пользователь\Documents\Codex\work\r3probe\r3_probe.py` использует
`wiring()` из bench, то есть подключённый `desk-scene.js`, настоящий сервер и настоящий SSE.

```text
python C:\Users\Пользователь\Documents\Codex\work\r3probe\r3_probe.py <repo> C:\Users\Пользователь\Documents\Codex\work\pt-o3d
CENSUS extra: ['desk-motion-model.js', 'desk-motion.js'] missing: []
LAYER (no tasks, stream closed): {parent: BODY, live: polite, pe: none, z: 50, kids: 0, overflow: 0} problems: []
WHILE STALE fx: {calls: [], added: []} plaques: 0 held: True
AFTER SWITCH fx: {calls: [], added: ['plaque']} plaque: ['Fix lost text · Waiting for your decision']
AFTER LATE LAND fx: {calls: [], added: ['plaque']}
NON-GET: []
PATHS: /command/queue, /command/quotas, /command/runs, /command/runs/run-closed, …/run-closed/accept,
       …/run-closed/automation, …/run-closed/controls, …/run-waiting/automation, /command/runs/run-working,
       …/run-working/automation, …/run-working/controls, /command/tasks
PLAQUE hit-test: {pe: none, hitInLayer: False, hit: studio-step-flow__body}
```

### 7.4 Остальные Desk browser-модули с подключением, подставленным через route

Плагин `C:\Users\Пользователь\Documents\Codex\work\r3probe\r3wire.py` подключался через
`-p r3wire` с `PYTHONPATH=<r3probe>;<repo>`. Каждый модуль запускался отдельным процессом:

```text
python -m pytest -q --tb=line -p no:cacheprovider -p r3wire --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-o3h browser_tests/<module>
```

Сначала отдельно: `test_desk_shell.py` → **1 failed, 11 passed**. Упал только тест census
(`Left contains 2 more items: {'desk-motion-model.js': 200, 'desk-motion.js': 200}`).

Остальные 43 модуля `browser_tests/test_desk_*.py`, без `test_desk_motion.py` и
`test_desk_shell.py`: **907 passed, 0 failed, 0 skipped**. Ни одного падения. Общее время —
около 29 минут; параллельно работали другие агенты, поэтому длительность завышена.

| Модуль | passed | Модуль | passed |
| --- | --- | --- | --- |
| test_desk_accept | 9 | test_desk_queue_moves | 13 |
| test_desk_accept_publish | 8 | test_desk_queue_release | 22 |
| test_desk_binding | 7 | test_desk_queue_skip | 15 |
| test_desk_boot_presses | 68 | test_desk_rail_scene | 30 |
| test_desk_bound_project | 23 | test_desk_run | 2 |
| test_desk_closing | 11 | test_desk_run_write | 1 |
| test_desk_decision_reread | 4 | test_desk_settled | 12 |
| test_desk_decisions | 2 | test_desk_status | 18 |
| test_desk_embed | 21 | test_desk_summary | 46 |
| test_desk_feed | 34 | test_desk_view_mode | 44 |
| test_desk_flow | 50 | test_desk_wizard | 16 |
| test_desk_flow_canvas | 3 | test_desk_wizard_cycle | 40 |
| test_desk_flow_host | 1 | test_desk_wizard_git | 44 |
| test_desk_hash | 22 | test_desk_wizard_git_fresh | 9 |
| test_desk_hold | 6 | test_desk_wizard_git_pending | 36 |
| test_desk_live_selection | 1 | test_desk_wizard_git_starter | 30 |
| test_desk_live_stream | 2 | test_desk_wizard_host | 1 |
| test_desk_map | 10 | test_desk_wizard_launch | 90 |
| test_desk_people | 4 | test_desk_wizard_materials | 26 |
| test_desk_pult | 50 | test_desk_wizard_prepare | 42 |
| test_desk_queue | 9 | test_desk_wizard_roles | 22 |
| test_desk_queue_confirm | 3 | | |

**Вывод для 4.1–4.2.** С подключённой сценой ломается только census в `test_desk_shell.py`.
Остальные существующие Desk browser-модули совместимы. Sonnet должен повторить эти прогоны на
настоящей правке, а не на подстановке: числа выше — ориентир, а не доказательство.

### 7.5 Что не проверялось

- POSIX и macOS. Все прогоны выполнены только в Windows.
- bfcache-переход (`pageshow` с `persisted`): в headless Chromium под Playwright он обычно не
  возникает. Вывод о сбросе baseline сделан по коду.
- Скрытая вкладка (вопрос 6.3) и мастер поверх Desk (вопрос 6.2) в браузере не воспроизводились.
- Полный core suite и `browser_tests/gate.py` в обоих порядках не запускались: это R5.
