# Первый цикл Далио Claude → Claude по подписке

Действующая инструкция B, подготовлена Codex 23.10.2026 на `2a5bcdd` по поручению владельца.
Она заменяет API-подготовку, старый wheel и negative control прежнего R5-REHEARSAL-RUNBOOK.
Сам цикл ещё не выполнен. B — промежуточный результат; Claude → Codex, R5 и V1 не закрывает.
Основа: H5-SUB-R5-TASK, решения `61a629f` и `2a5bcdd`; нужны завершённые I2b/I3. Условия
старта приведены к решениям Codex от 26.10 (`tasks/H5-SUB-R5-I2B-DECISION-REPORT.md`,
`tasks/H5-SUB-R5-I2B-CLOSE-TASK.md`).

## Уже подготовлено

- Исходный проект `%USERPROFILE%\DecemberRehearsal`: три файла, исходный дефект `return len(rows)`.
- Три файла в Git-индексе; коммита и настройки identity нет. Это снимок перед работой harness.
- Один начальный unittest проходит только на пустом списке. На success + failed получено 2
  вместо требуемого 1: дефект сохранён. Это не успешная проверка будущего результата.
- Пакет `%USERPROFILE%\Documents\Codex\work\dalio-claude-preliminary` (далее `$KIT`):
  `artifact-brief.txt`, `instruction-plan.txt`, `seed/`, `seed-manifest.json`,
  `source-prepared.json`, `evidence-template.json`, `run-ready.template.json`.
  Тексты готовы к вставке. JSON-заготовки — журнал подготовки, не импортируемый конфиг приложения.

## Что завершает Opus до старта

Порядок и границы — `tasks/H5-SUB-R5-I2B-CLOSE-TASK.md` §1.

1. Закоммиченный I3, Q13 (`claim_refused`) и Q11 (удержание login в тесте) на сохранённой базе,
   целевые проверки в обеих кодировках и ревью; итоговый полный набор тестов на окончательном
   коммите в чистом detached worktree (CLOSE-TASK §3).
2. Claude 2.1.239 в защищённом
   `%USERPROFILE%\DecemberCommand\harnesses\claude-code\2.1.239\claude.exe`;
   sha256 и ACL по Р1 `2a5bcdd`. Установку копирует поток A, этот runbook её не дублирует.
3. Продукт по Р7 в защищённом `%USERPROFILE%\DecemberCommand\product\<sha12>\` (venv, wheel,
   `scratch`) и manifest `%USERPROFILE%\DecemberCommand\product\<sha12>.manifest.json`: wheel из
   названного commit окончательного кода, sha256, установка из wheel (не editable), импорт из
   установленного wheel. Старый `rh-0a493ad` не использовать. Проверка —
   `preflight.ps1 -Mode check -Product <sha12>` без проблем (команда в «Подготовке»). Этот wheel
   локальный для B, не финальный CI-кандидат R5.
4. A2 по D13: только нативный `claude.exe --version` в режимах boundary dispatch и review, в UTF-8
   и cp1251, на синтетическом входе, без prompt и без входа владельца; не больше четырёх запусков,
   платных запросов нет. A2 показывает запуск и освобождение ресурсов, но не подписку, не чтение
   токена, не отсутствие refresh, не модель, не checker и не цикл.
5. Заполнить `$KIT\run-ready.json` из заготовки: реальные пути, SHA и ссылки на доказательства,
   `ready: true` только после выполнения пунктов 1–4 и отчёта подготовки
   `tasks/H5-SUB-R5-I2B-CLOSE-REPORT.md` (CLOSE-TASK §1 п. 4, §6). Это указатель и копия сведений,
   не основание доверия: основание — защищённый manifest. Полный релизный CI остаётся отдельным
   требованием; предварительный B допустим после целевых проверок, итогового полного набора (п. 1)
   и ревью по H5 TASK.
6. Свежий вход владельца в `$LOGIN` (блок «Свежий вход» ниже) — после пунктов 1–5, прямо перед B;
   токен должен пережить ближайшую попытку (timeout + 10 минут). Не читать и не выводить секреты;
   не использовать личный профиль рабочего Claude.

Свидетельства. У Claude один настоящий ответ, на копии входа вне изоляции. Dispatch, review и
checker внутри изоляции впервые проходят в B: это первый прогон, не повтор проверенного.

Дождаться A целиком или Codex 0.164.0 для B не требуется: из A нужен только A2 (пункт 4). Если I3
ещё не убрал надписи «subscription только квоты / задачи только API», закончить уже назначенную
правку I3.

## Подготовка приложения, без запуска модели

Два обычных окна PowerShell из «Пуска»: А — подготовка, Б — сервер. После готовности сборки
в обоих окнах выполнить два блока: имена, затем (после `preflight.ps1`, окно А) пути.
`<sha12>` подставляет ведущий при установке продукта:

```powershell
$SHA12 = '<sha12>'
$DC = Join-Path $env:USERPROFILE 'DecemberCommand'
$KIT = Join-Path $env:USERPROFILE 'Documents\Codex\work\dalio-claude-preliminary'
$P = Join-Path $env:USERPROFILE 'DecemberRehearsal'
```

Перед стартом, в окне А, выполнить `preflight.ps1` из отчёта П0–П5 A (защищённый корень, хеши,
ACL, `tasks/H5-CODEX-COMPAT-A-P0-P5-REPORT.md`) вместе с проверкой установленного продукта (wheel,
venv, базовый Python, Р7, `tasks/H5-SUB-R5-I2B-DECISION-REPORT.md`):

```powershell
& (Join-Path $DC 'h5-a\tools\preflight.ps1') -Mode check -Product $SHA12
```

Любая проблема в его выводе или код выхода 2 — стоп, приложение не запускать. Без `-Product`
«0 problems» установленный продукт не покрывает. Пути `$PY`, `$CONDUCT` и `$SCRATCH` берутся из
защищённого manifest (Р7), а не из изменяемого `run-ready.json`; несовпадение с ним (пути, SHA
wheel, `source_commit` против `commit` manifest, `commit` против `$SHA12`) — стоп:

```powershell
$manifestPath = Join-Path $DC "product\$SHA12.manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$readyText = Get-Content -LiteralPath (Join-Path $KIT 'run-ready.json') -Raw -Encoding UTF8
$ready = $readyText | ConvertFrom-Json
if (-not $ready.ready) { throw 'I2b/I3, the A2 smoke and the installed product are not ready' }
if ($ready.venv_python -ne $manifest.venv_python) { throw 'run-ready.json differs from manifest' }
if ($ready.conduct_exe -ne $manifest.conduct_exe) { throw 'run-ready.json differs from manifest' }
if ($ready.wheel_sha256 -ne $manifest.wheel.sha256) { throw 'run-ready.json differs from manifest' }
if ($ready.source_commit -ne $manifest.commit) { throw 'run-ready.json differs from manifest' }
if (-not ([string]$manifest.commit).StartsWith($SHA12)) { throw 'manifest is not of this build' }
$PY = $manifest.venv_python
$CONDUCT = $manifest.conduct_exe
$SCRATCH = $manifest.scratch
$CLAUDE = Join-Path $DC 'harnesses\claude-code\2.1.239\claude.exe'
$LOGIN = Join-Path $DC 'logins\claude-code'
$env:TEMP = $SCRATCH
$env:TMP = $SCRATCH
$env:PYTHONPATH = ''
```

`TEMP` и `TMP` окна — защищённый `scratch` продукта (Р8): процессы вне boundary (версия, статус
входа, квоты) не пишут в общий TEMP. Task-TEMP внутри boundary по-прежнему задаёт сама попытка.

Перед инициализацией сохранить исходные sha256; сверить с `seed-manifest.json`.
Исходный пакет повторно не создавать и не сбрасывать. Затем один раз, при остановленном сервере:

```powershell
& $CONDUCT init --template default-orbit --dir $P
& $CONDUCT ownership activate --legacy-writers-stopped --dir $P
& $CONDUCT ownership status --dir $P
```

Ожидается ownership `active`.

**Свежий вход** делает владелец, в окне А, перед мастером (CLOSE-TASK §6). Папку входа создать
заранее: мастер её не создаёт. Вход идёт в браузере аккаунтом подписки; ассистент входа не
выполняет и login-home не читает. Без переменной инструмент войдёт в личный профиль, а папка
продукта останется пустой:

```powershell
New-Item -ItemType Directory -Force -Path $LOGIN | Out-Null
$env:CLAUDE_CONFIG_DIR = $LOGIN
& $CLAUDE auth login --claudeai
Remove-Item Env:CLAUDE_CONFIG_DIR
```

Мастер задаёт вопросы Python, а не PowerShell: переменная в ответе не раскрывается, и `$CLAUDE`
будет отвергнут как неабсолютный путь. Напечатать значения и вставить в мастер их, а не имена:

```powershell
$CLAUDE
$LOGIN
& $CONDUCT providers --dir $P
```

В мастере настроить **одну** строку `claude-code`:

| Поле | Значение |
| --- | --- |
| Provider | Claude Code (`claude-code`) |
| Executable | значение `$CLAUDE`, напечатанное выше (полный путь) |
| How does it sign in? | `1`, собственный подписочный вход |
| Login directory | значение `$LOGIN`, напечатанное выше; папка уже создана и содержит свежий вход |
| Environment variable NAMES | `SYSTEMROOT WINDIR PATH TEMP TMP` |
| Write it? | `y` после проверки сводки `login subscription` |

После вопроса о папке входа мастер печатает две строки входа («Paste these two lines»): не выполнять
их. Свежий вход уже сделан выше, а повторный заменил бы его.

Ключи не создавать, второй provider или второй вход для checker не нужны.
`availability available` подтверждает доступность установки, а не успех модельной задачи.
На время репетиции не работать параллельно с этим login-home; source читается под lease.

Окно Б: выполнить те же два блока (имена; manifest, `run-ready.json`, `TEMP`/`TMP` из `$SCRATCH`,
чистый `PYTHONPATH`); `CLAUDE_CONFIG_DIR` в нём не задавать. Затем:

```powershell
& $CONDUCT up --dir $P --port 7801
```

Дождаться `serving … — Ctrl+C to stop`, открыть `http://127.0.0.1:7801/` (Studio).
Если порт занят, разобраться с владельцем процесса; чужой сервер не завершать.
До модели снять квоту Claude в «Участниках»: источник, время, известные окна и сбросы.
Неизвестное оставить неизвестным; две роли не означают две квоты.

## Один цикл в Studio

1. **«Процесс» → «Создать новый процесс».** ID `r5-claude-dalio`; начать со «Стандартного
   цикла» `dalio-v5`; исполнение — «Ограниченный автоматический процесс». «Создать процесс» →
   «Сохранить черновик» → «Проверить» → «Опубликовать версию 1».
   Ревизия стартового шаблона 5 и версия нового процесса 1 — разные числа.
2. **«Запуски» → «Новая задача».** Название `R5 Claude — count_succeeded`, «Создать задачу».
   Выбрать опубликованный процесс и «Создать новый запуск».
3. ID запуска и ID цикла — `r5-claude-preliminary`; версия процесса 1;
   «Автоматически в заданных пределах». Во всех пяти ролях выбрать `claude-code`.
   Модели оставить пустыми: это default CLI, не обещание конкретного Sonnet/Opus.
   Фактически наблюдённую модель записать, неизвестную не угадывать. «Создать запуск».
4. **«Опубликовать документ».** Имя материала `artifact-brief` → содержимое одноимённого TXT
   из `$KIT`; затем `instruction-plan` → его TXT с исходными тремя файлами. Не публиковать
   заранее готовое решение или выдуманные результаты стадий.

| Роль | Экземпляр, который создаёт Studio | Задача |
| --- | --- | --- |
| role-thinker | instance-role-thinker | goal, identify |
| role-diagnostician | instance-role-diagnostician | diagnose |
| role-designer | instance-role-designer | design |
| role-implementer | instance-role-implementer | do |
| role-checker | instance-role-checker | отдельная проверка точного результата do |

Один provider допустим; `instance-role-implementer` и `instance-role-checker` различны.
Не создавать вторую строку provider с тем же ID. Публичный контракт поддерживает это:
`tests/test_standard_cycle_checker.py`, тест двух экземпляров одного harness.

5. **«Просмотреть границы запуска».** Проверить путь Claude, подписку, роли, материалы,
   `execution-boundary` и checker. Лимит — **6 действий и максимум 2 проверки**.
   По текущему коду defaults: goal/identify/diagnose/design по 300 секунд × 1;
   do — 300 секунд × 2, включая возможную коррекцию. Проверка do резервирует ещё его timeout:
   `max_action_seconds=600`, `max_total_task_seconds=2400`, срок гранта 3600 секунд.
   Сверить фактический preview установленного wheel, не повышать лимиты по старому runbook.
   **Владелец:** имя `vasily` → «Разрешить ограниченный запуск».
6. Дождаться **goal → identify → diagnose → design**. Проверить цепочку
   `artifact-goal → artifact-problems → artifact-causes → artifact-plan`.
   **Владелец:** «Решения», `gate-confirm-do`, прочитать план, `approve`, автор `vasily`,
   «Записать решение». Автор решения — латинский ID.
7. Дождаться **do + отдельный checker**. Требуется настоящий `accept`, instance ID проверяющего,
   новая попытка и digest потреблённых материалов. На первый reject с пригодными замечаниями
   допускается одна коррекция do и повторная проверка в том же цикле; второй reject — стоп.
   Unknown, проблемы входа или потерю дерева не превращать в разрешение повторить вызов.
   Отказ входа посреди цикла (например `the pinned login expires before the attempt would end;
   sign in again`) — стоп и запись слов. Повторный вход и новое предложение шага решает Codex;
   в бюджете 6+2 их нет.
8. До `gate-result` прочитать рабочие файлы, проверить тесты и неизменность исходника ниже.
   **Владелец:** `gate-result` → `approve` → «Записать решение», только если результат принят.
   «План завершён» не заменяет проверку. `request_changes` запускает внешнюю петлю перепланирования;
   продолжение этой петли не входит в бюджет B — остановиться и определить следующий шаг.

## Если запуск остановился

Ключ — то, что видно на экране и в отказе. Действие, возможно, уже выполнялось: не повторять его и
не начинать новых попыток, а сервер закрыть (Ctrl+C). Повторного вызова в бюджете B нет;
продолжение — решение Codex. Два признака:

1. Исход `unknown` со словами `adapter execute lost its result`. Результат шага потерян, а владение
   проектом цело: одни эти слова перезагрузки не требуют. Причину они не называют; фраза
   `could not start the pinned build` на экран не выводится.
2. Шаг остаётся начатым без результата, а Studio на каждое действие, которое пишет, отвечает
   «The run store is unavailable.» (в русском интерфейсе «Хранилище запусков недоступно.»). Это
   случай Q12: закреплённая сборка не запустилась внутри runner, владение проектом и аренда входа
   стали неопределёнными, квитанцию записать нельзя. Ctrl+C печатает `stop uncertain`, а следующий
   `up` откажет с `recovery_required`.

Если `up` или следующее действие откажет с `recovery_required` либо `login_recovery_required`
(после признака 2 `up` откажет наверняка) — перезагрузить ОС (**Перезагрузка**, не завершение
работы). Затем в новом окне PowerShell из «Пуска» заново выполнить оба блока «Подготовки» (имена;
manifest и `TEMP`/`TMP` из `$SCRATCH`): прежних `$CONDUCT`, `$P` и `$LOGIN` там нет. Затем команда
для названного кода; после признака 2 — обе, потому что аренда входа осталась открытой вместе с
записью проекта:

```powershell
& $CONDUCT ownership recover --dir $P                       # recovery_required
& $CONDUCT ownership recover-login --auth-home $LOGIN       # login_recovery_required
```

Если команда просит подготовленной перезагрузки (запись старой сборки на Windows), следовать её
выводу. Отказ команды, которой нечего восстанавливать, — не препятствие: `recover` говорит
`recovery_refused: there is no abandoned owner session to recover`, а `recover-login` при
остановленном сервере и чистой аренде — `login_owner_busy: shared login recovery cannot hold its
resource`. Эти слова значат «нечего восстанавливать» только для точного абсолютного пути
существующей папки входа (`$LOGIN`): опечатка в пути или несуществующая папка дают тот же ответ.
Приложение не запускать и действий не начинать, пока `up` отказывает с `recovery_required`; после
`login_recovery_required` или признака 2 — и пока `recover-login` не ответил `recovered` либо
отказом `login_owner_busy` при точном `$LOGIN`. После восстановления шаг без результата может
закрыться `unknown` со словами `effect lease has no durable observation; execution was not
repeated`: продукт его не повторил, не повторять и вручную. В журнал записать факт и код отказа,
без токенов и содержимого login-home.

## Проверка полезного результата и принятие

Рабочая копия — `$P\work\_tasks\<фактический task_id>\work-001`. Сначала посмотреть её файлы.
Ожидаются три исходных файла; `__init__.py` побайтно исходный. Не выполнять неизвестные
команды из ответа harness; после чтения кода и тестов запускать известный локальный Python.

```powershell
$W = Join-Path $P 'work\_tasks\<actual-task-id>\work-001'
Get-Content -LiteralPath (Join-Path $W 'runstats\counts.py')
Get-Content -LiteralPath (Join-Path $W 'tests\test_counts.py')
Push-Location -LiteralPath $W
& $PY -B -m unittest discover -s tests -v
Pop-Location
```

Тесты должны проверять смешанные результаты, не-словари, отсутствие outcome, регистр/пробелы,
пустой список и неизменность входа. Пример из brief должен давать 2; success + failed — 1.
Одного прежнего зелёного теста недостаточно. Сохранить реальные passed/failed и SHA256 результата.
До принятия три файла исходника сверить с `seed-manifest.json`, проверить новые файлы в
`runstats/` и `tests/`: один `git diff` не ловит неотслеживаемые файлы.

После **явного принятия владельцем** скопировать только `runstats/counts.py` и
`tests/test_counts.py` из проверенной рабочей копии в исходник, повторить unittest в `$P`.
Не применять весь каталог, не выполнять push/PR. Снимок результата должен совпасть с проверенным.

Обновить страницу. Ctrl+C в окне Б; `ownership status` должен стать `closed`; снова `up`.
Версия процесса, конфигурация, документы, артефакты, human gates и checker evidence сохраняются
без нового вызова harness. Снять квоту Claude после; её дельта не доказывает расход этой задачи,
если тот же аккаунт использовали где-либо ещё. В конце штатно закрыть сервер.

## Доказательства и передача

Заполнить копию `evidence-template.json` фактическими ID, SHA, путями, числом действий,
вердиктами, решениями владельца, квотами и проверкой перезапуска. Пустое поле — не доказанный факт.
Обычно это 5 действий + 1 checker, максимум 6 + 2; login/status/quota записываются отдельно.
Модельные probes, negative control и второй цикл этим runbook не назначаются.
Не копировать auth.json, credentials, сырые OAuth-ответы или токены в журнал/скриншоты.

Последний доказанный шаг | первый несделанный: исходный проект и тексты подготовлены |
новый проверенный wheel, защищённая установка и запуск UI ещё впереди.
Не повторять создание seed и старые M2; подписочный цикл пока не запускался.
Следующий шаг: Opus завершает I2b/I3 и заполняет `run-ready.json`;
затем один проход по этой странице.
