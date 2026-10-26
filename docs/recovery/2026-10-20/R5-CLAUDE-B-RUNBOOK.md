# Первый цикл Далио Claude → Claude по подписке

Действующая инструкция B, подготовлена Codex 23.10.2026 на `2a5bcdd` по поручению владельца.
Она заменяет API-подготовку, старый wheel и negative control прежнего R5-REHEARSAL-RUNBOOK.
Сам цикл ещё не выполнен. B — промежуточный результат; Claude → Codex, R5 и V1 не закрывает.
Основа: H5-SUB-R5-TASK, решения `61a629f` и `2a5bcdd`; нужны завершённые I2b/I3.

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

1. Закоммиченные I2b/I3, целевые проверки и ревью, нативный свидетель подписочной дороги
   Claude для planning/review, do и checker. Подмена boundary или один login status недостаточны.
2. Claude 2.1.239 в защищённом
   `%USERPROFILE%\DecemberCommand\harnesses\claude-code\2.1.239\claude.exe`;
   sha256 и ACL по Р1 `2a5bcdd`. Установку копирует поток A, этот runbook её не дублирует.
3. Новый wheel из названного commit, sha256, отдельный venv вне `%LOCALAPPDATA%` и исходника;
   импорт из установленного wheel. Старый `rh-0a493ad` не использовать;
   editable не выдавать за установленный wheel.
4. Заполнить `$KIT\run-ready.json` из заготовки: реальные пути, SHA и ссылки на доказательства,
   `ready: true` только после выполнения этих условий. Полный релизный CI остаётся отдельным
   требованием; предварительный B допустим после целевых проверок и ревью по H5 TASK.
5. Проверить подписочный вход в отдельном home продукта, свежесть для ближайшей попытки
   (timeout + 10 минут). При необходимости подготовить владельцу штатный повторный вход.
   Не читать/выводить секреты; не использовать личный профиль рабочего Claude.

Дождаться A целиком или Codex 0.164.0 для B не требуется. Если I3 ещё не убрал надписи
«subscription только квоты / задачи только API», закончить уже назначенную правку I3.

## Подготовка приложения, без запуска модели

Два обычных окна PowerShell из «Пуска»: А — подготовка, Б — сервер. После готовности сборки:

```powershell
$KIT = Join-Path $env:USERPROFILE 'Documents\Codex\work\dalio-claude-preliminary'
$P = Join-Path $env:USERPROFILE 'DecemberRehearsal'
$readyText = Get-Content -LiteralPath (Join-Path $KIT 'run-ready.json') -Raw -Encoding UTF8
$ready = $readyText | ConvertFrom-Json
if (-not $ready.ready) { throw 'I2b/I3 and installed wheel are not ready' }
$PY = $ready.venv_python
$CONDUCT = $ready.conduct_exe
$CLAUDE = Join-Path $env:USERPROFILE 'DecemberCommand\harnesses\claude-code\2.1.239\claude.exe'
$LOGIN = Join-Path $env:USERPROFILE 'DecemberCommand\logins\claude-code'
$env:PYTHONPATH = ''
```

Перед стартом выполнить `preflight.ps1` из отчёта П0–П5 A (защищённый корень, хеши, ACL,
`tasks/H5-CODEX-COMPAT-A-P0-P5-REPORT.md`). Любая проблема в его выводе — стоп, приложение не
запускать. Он не проверяет установленный продукт (wheel, venv, базовый Python): «0 problems» это
не покрывает; проверка защищённой установки `product\<sha>` — отдельный шаг подготовки B (Р7,
`tasks/H5-SUB-R5-I2B-DECISION-REPORT.md`):

```powershell
& (Join-Path $env:USERPROFILE 'DecemberCommand\h5-a\tools\preflight.ps1') -Mode check
```

Перед инициализацией сохранить исходные sha256; сверить с `seed-manifest.json`.
Исходный пакет повторно не создавать и не сбрасывать. Затем один раз, при остановленном сервере:

```powershell
& $CONDUCT init --template default-orbit --dir $P
& $CONDUCT ownership activate --legacy-writers-stopped --dir $P
& $CONDUCT ownership status --dir $P
& $CONDUCT providers --dir $P
```

Ожидается ownership `active`. В мастере настроить **одну** строку `claude-code`:

| Поле | Значение |
| --- | --- |
| Provider | Claude Code (`claude-code`) |
| Executable | `$CLAUDE` из защищённого корня |
| How does it sign in? | `1`, собственный подписочный вход |
| Login directory | `$LOGIN`, уже существующий отдельный home продукта |
| Environment variable NAMES | `SYSTEMROOT WINDIR PATH TEMP TMP` |
| Write it? | `y` после проверки сводки `login subscription` |

Ключи не создавать, второй provider или второй вход для checker не нужны.
`availability available` подтверждает доступность установки, а не успех модельной задачи.
На время репетиции не работать параллельно с этим login-home; source читается под lease.

Окно Б: прочитать те же `$ready`, `$CONDUCT`, `$P` и очистить `PYTHONPATH`, затем:

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
8. До `gate-result` прочитать рабочие файлы, проверить тесты и неизменность исходника ниже.
   **Владелец:** `gate-result` → `approve` → «Записать решение», только если результат принят.
   «План завершён» не заменяет проверку. `request_changes` запускает внешнюю петлю перепланирования;
   продолжение этой петли не входит в бюджет B — остановиться и определить следующий шаг.

## Если запуск остановился

При ошибке `could not start the pinned build` или состоянии `recovery_required` — стоп. Действие,
возможно, уже выполнялось: не повторять его и не начинать новых попыток. Закрыть сервер (Ctrl+C),
перезагрузить ОС (**Перезагрузка**, не завершение работы), затем в новом окне PowerShell, с теми же
`$CONDUCT`, `$P` и `$LOGIN`:

```powershell
& $CONDUCT ownership recover --dir $P
& $CONDUCT ownership recover-login --auth-home $LOGIN
```

Если команда просит подготовленной перезагрузки (запись старой сборки на Windows), следовать её
выводу. Пока обе команды не завершились успехом, приложение не запускать. В журнал записать факт и
код отказа, без токенов и содержимого login-home.

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
