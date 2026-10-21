# R5: проверки выпуска и приёмка V1 — план

- Дата: 21 октября 2026. Автор: Claude Code / Opus 5.5, режим только чтения (кроме этого файла).
- База: ветка `recovery/2026-10-20`, HEAD `04641ca32ac30b853277a2f41093167b2b0da964` (запушен,
  CI на нём идёт). Код продукта, тесты, Git и CI не менялись; сеть и аккаунты не использовались.
- Прочитано целиком: `docs/release-smoke.md`, `docs/owner-acceptance.md`,
  `docs/acceptance-two-tasks.md` и `.ru.md`, `docs/first-run-v1.md`, `docs/v1-v2-scope.md`,
  `.github/workflows/ci.yml`, `browser_tests/gate.py`, `scripts/wheel_road.py`,
  `scripts/installed_probe.py`, начало `scripts/mutate_merge.py`; документы восстановления
  (`CONTINUATION-PLAN.md` R5, `HANDOFF-2026-10-21.md`, `OPEN-DECISIONS.md`,
  `tasks/CODEX-REVIEW-ff0ce19.md`) и отчёты N1–N3, R1.2c, R1.3-E1, R1.5, R2-H5.
- Это план, а не результат. Пометка «по коду» значит: выведено чтением кода и не измерено.
  Пометка «предложение Opus» значит: такого шага в документах нет.
- Правка 21.10.2026 (Claude Code / Sonnet 5.5, не закоммичена): по ревью плана (Opus,
  `approve_with_notes`) и замерам Opus T1–T3. Пометка «измерено» значит: замер на этом ноутбуке на
  `04641ca`, dev `.venv`, временный `CONDUCT_HOME`; временные каталоги удалены, процессов не
  осталось, `git status` не изменился. Затронуты разделы 0, 3.3, 4.1, 4.2, 5.1–5.4; те же поправки
  внесены в документы владельца (5.2) и в `tasks/R5-WINDOWS-WHEEL-ROAD.md`.

## 0. Коротко

1. На `04641ca` не подтверждено ничего из выпускных проверок. Между `ff0ce19` (CI №42) и
   `04641ca` изменено 22 файла в `src/`, `tests/`, `browser_tests/` (R1.2c, R1.5, N2, N3,
   R1.3-E1). Итог №42 в репозитории не записан: есть только срез на 23:13 20.10.
2. CI проверяет ядро на трёх ОС и двух Python, browser gate в двух порядках на трёх ОС (только
   3.12), один wheel и installed road **только на Ubuntu и macOS**. Windows installed road,
   release smoke, кириллический профиль, интерактивные мастера, Ctrl+C человеком, настоящие
   harness и приёмка владельца в CI не входят.
3. Настоящее исполнение на этой сборке возможно только на Windows и только по дороге API-ключа:
   подписка внутри execution boundary отказывает до запуска (H5), на Linux и macOS boundary не
   предоставляется вовсе. До правки 21.10 `docs/first-run-v1.md` этого не говорил; теперь это
   подраздел «Где задачи исполняются в этой сборке» в обоих языках (рабочая копия, 5.2). Поэтому
   решение владельца **H5-V1** стоит первым: от него зависят аккаунты и установки для rehearsal и
   приёмки.
4. Найдены три ловушки для владельца на этом ноутбуке, все три измерены на `04641ca` (T1–T3,
   раздел 4.2):
   - `Stop-Process` в шаге 16 `owner-acceptance.md` убивает дерево процессов без drain, владение
     остаётся `opened`, нужна полная перезагрузка ОС;
   - путь проекта из шага 1 (в `TEMP`) занимает 100 символов, а id процесса в 128 символов из
     шага 4 допускает корень не длиннее 82: сохранение черновика отказывает с
     `windows_path_too_long`;
   - шаг 3 запускал сервер скрыто (`-WindowStyle Hidden`): Ctrl+C из окна владельца до него не
     доходит, остановить его человек может только через `Stop-Process`, то есть через п. 1.
5. Кандидат — один SHA и один wheel из job `build one wheel` этого SHA. Локальная сборка wheel
   без сети невозможна (`hatchling` отсутствует, параллельный отчёт
   `tasks/R5-WINDOWS-WHEEL-ROAD.md`). Wheel берётся из CI (вариант А) либо собирается локально
   после разового скачивания `hatchling` и принимается только при совпадении его sha256 с sha256
   из CI (вариант Б). Оба варианта требуют решения и действия владельца: 3.3 п. 5, условие в 5.1.
6. Release notes от 25.09 (`frozen-19`, `d4d2580`) описывают другую сборку и устарели целиком.

## 1. Все проверки выпуска и приёмки

Где: **CI** — GitHub Actions на точном commit; **Win** — локально на Windows этого ноутбука
(разработчик); **Вл** — вручную владельцем; **Акк** — нужен аккаунт или API-ключ провайдера и
платные вызовы.

История CI: №39 — commit в документах не записан; по `HANDOFF` подтвердил R1.1 на Ubuntu/macOS.
№40 `57fe629` (run 39451610001) — полностью зелёный. №41 `c07f447` (run 39465863068) — красный:
guard пробелов во всех шести core-job (исправлен `395cecc`), Ubuntu 3.11 drain Ctrl+C exit -2
(R1.5, исправлен `ce3b7bd`), Windows reverse gate 10055 в `test_studio_runs_fold` (R1.3).
№42 `ff0ce19` (run 39485630011) — на 23:13 зелёные core Ubuntu 3.11/3.12, wheel, road Ubuntu и
macOS; остальное шло. Ни один из этих прогонов не проверяет `04641ca`.

| № | Проверка | Источник | Где | Статус на `04641ca` | Что сохранить |
| --- | --- | --- | --- | --- | --- |
| 1 | Полный core `pytest -q --basetemp pt`, 3 ОС × Python 3.11/3.12 (6 job). Внутри — структурные лимиты, frozen bytes, payload parity, `test_file_endings`, `CAPPED` | `ci.yml` job `test`, шаг Tests; `release-smoke.md` «Additional release gates» | CI | Не подтверждено, CI идёт. Важно для POSIX/3.11: свидетели R1.2c (гонка `HeldTick`), R1.5, N3 тест 7 (sh/zsh) локально не запускались | URL run, id job, хвост `passed/failed/skipped`, exit; выдержки падений |
| 2 | Mutation harness `scripts/mutate_merge.py` | `ci.yml` шаг Mutation harness | CI, в каждом из 6 job | Не подтверждено | Строка счёта и exit (0 = все мутанты убиты; 2 = измерение недействительно) |
| 3 | Demo drift gate (`validate` материализованного demo) | `ci.yml` | CI, 6 job | Не подтверждено | Exit шага |
| 4 | Wheel smoke в каждом job: свой wheel, установка, импорт, `validate` | `ci.yml` шаг Wheel smoke | CI, 6 job | Не подтверждено. Это **не** кандидатный wheel: каждый job собирает свой | Exit шага |
| 5 | Чистая рабочая копия после job | `ci.yml` (все job) | CI | Не подтверждено | Exit шага |
| 6 | Browser gate: `gate.py --keep-going`, затем `--reverse`, отдельный процесс на модуль, без retry и waiver; Python 3.12 | `ci.yml` job `browser`; `browser_tests/gate.py`; `CONTINUATION-PLAN.md` R5 | CI, Ubuntu/Windows/macOS | Не подтверждено. На Windows пара зелёных порядков ожидается примерно в 37 % прогонов (λ ≈ 0,5 события 10055 на порядок, `tasks/R1.3-WIN-10055-CI41.md` §3) | Artifact `browser-gate-<os>`: `bg/gate.json` и `bgr/gate.json` (`result: green`, `complete: true`, `failures: []`), `versions.json`, на Windows `netfail/*.jsonl` (R1.3-E1); SHA256 архива. Хранение 14 дней |
| 7 | Один wheel (`build one wheel`, Ubuntu, 3.12) и его sha256 | `ci.yml` job `wheel` | CI | Не подтверждено | Имя файла, sha256 из output job, artifact `candidate-wheel` (14 дней) |
| 8 | Installed road из этого wheel: venv, offline-установка, provenance, init → activate → два `up`, SIGINT, `closed` | `scripts/wheel_road.py`, `ci.yml` job `wheel-road` | CI, Ubuntu и macOS | Не подтверждено | Artifact `wheel-road-<os>`: `report.json` (`success`, `wheel.sha256` = п. 7, `graceful_stop`, `status_after: closed`) и логи |
| 9 | Полный core на кириллическом профиле, точный SHA, чистая копия | `HANDOFF-2026-10-21.md` план п. 6; `LOCAL-SETUP.md` (basetemp ≤ 26 символов) | Win | Не подтверждено. Прежний прогон на `395cecc` (17 284 passed, 408 skipped, 16 failed: 2 — запуск вне git, 14 — N2, исправлено) к кандидату не относится. CI этот класс не ловит: рекомендация N1 о не-ASCII basetemp в CI не внесена | `git rev-parse HEAD`, пустой `git status`, команда, junit-xml, лог, числа, exit |
| 10 | Release smoke, шаги 1–12, с кандидатным wheel | `release-smoke.md` 1–12 | Win (PowerShell) | Не пройден. Попытка 21.10 остановлена на сборке wheel (`tasks/R5-WINDOWS-WHEEL-ROAD.md`, не закоммичен) | Имя и SHA256 wheel, `pip list`, вывод каждого шага, сохранённый `$SMOKE` |
| 11 | Installed road на Windows: два срока `up`, Ctrl+C, `closed` | `wheel_road.py` docstring; комментарий `ci.yml` к `wheel-road`; release notes 25.09 п. 4 | Win, вручную | Не пройден. Windows-раннера в репозитории нет (`wheel_road.py` выходит при `os.name != "posix"`; release notes: раннер оператора «not part of the repository») | Вывод `ownership status` после каждой остановки, коды выхода |
| 12 | Ручные пункты smoke: `conduct init` с терминалом, `conduct providers` интерактивно (три отказа ввода, хотя бы один харнесс каждого вида), Ctrl+C рукой, живое обновление classic panel | `release-smoke.md` шаг 12 и «What this procedure does not check» | Win или Вл | Не пройдены | Записи наблюдений; никаких значений ключей |
| 13 | Opt-in probe настоящего checker: 2 вызова на провайдера, 60 с каждый | `release-smoke.md` «Opt-in real checker probe»; `tests/test_command_independent_real_smoke.py` | Акк | Не запускался после восстановления (живые прогоны были только с Claude на `frozen-12…17`) | Слово вердикта, версия harness, SHA кандидата |
| 14 | Developer rehearsal: real-result (`count_succeeded`), независимый checker другого участника, отрицательный контроль | `owner-acceptance.md` «Required real-result acceptance»; `release-smoke.md` «Additional release gates» | Акк + Win | Не проводился | SHA и wheel, версии harness, участники и модели, бюджеты, run id, вердикты, digest артефактов; без ключей и сырого вывода checker |
| 15 | Owner acceptance, 17 шагов | `owner-acceptance.md` 1–17 | Вл | Не проводилась никогда | Список «где без разработчика не вышло» по шагам |
| 16 | Две задачи, 10 шагов | `acceptance-two-tasks.md` / `.ru.md` | Вл (шаги 7, 9 — Акк) | Не проводилась | Находки против run и шага |
| 17 | Повтор real-result владельцем | `owner-acceptance.md`; `v1-v2-scope.md` | Вл + Акк | Не проводился | Как в п. 14, отдельной записью |
| 18 | Ревью Codex: R1.1 `63daddb`, R1.2 `4267f6b`, R1.2b `c07f447`, R3 `ba09148`, R4 `f7ba4a3`/`9c8fa7c`, N2 `117b1da`, R1.3-E1 `ea3fbf3`, R1.2c `f8f562b`, R1.5 `ce3b7bd`, N3 `04641ca` | `OPEN-DECISIONS.md` «Ревью Codex»; отчёты задач | Codex | Не проведены (проведены только R3.1 и N1) | Раздел «Ревью Codex» в каждом отчёте |
| 19 | Решения владельца и Codex | `OPEN-DECISIONS.md` | Вл, Codex | Открыты, см. раздел 4.3 | Запись решения с датой |

## 2. Что CI закрывает и чего нет

**Закрывает (после зелёного прогона на точном SHA):** core на Ubuntu, Windows и macOS для
Python 3.11 и 3.12, включая нативные Windows-тесты на runner; mutation harness merge; дрейф
demo; сборку и импорт wheel в каждом job; browser gate в двух порядках на трёх ОС; один wheel с
sha256; установленную дорогу этого wheel на Ubuntu и macOS; чистоту checkout.

**Не закрывает:**

- Windows installed road из **одного** wheel. Windows-job ставят собственный wheel, а job
  `wheel-road` есть только для Ubuntu и macOS. Нужно сделать вручную (п. 10–11).
- Python 3.11 вне ядра: browser gate, wheel и road идут только на 3.12. На ноутбуке есть только
  3.12.14, поэтому 3.11 подтверждается только core-job CI.
- Кириллический профиль, ANSI 1251 и OEM 866: на runner ASCII-профиль и cp1252. Классы N1 и N2
  находились только на ноутбуке (п. 9).
- Release smoke целиком: он ручной по замыслу. Интерактивные `init` и `providers`, Ctrl+C
  человеком, отрисовку в браузере владельца.
- Настоящие harness, аккаунты, real-result и независимую проверку настоящим checker.
- Исполнение на Linux и macOS: boundary есть только для `win32`
  (`src/conductor/command/execution_boundary.py:27-28`). Продукт ограничивает адаптеры платформой
  хоста по умолчанию (`src/conductor/command/providers.py:369-394`), поэтому настоящая задача на
  POSIX отказывает до запуска. Зелёный CI на POSIX доказывает тесты и platform road, а не
  исполнение.
- Owner acceptance и приёмку двух задач.
- AFD-трассу: условие в `ci.yml:120` привязано к ветке `feature/v1-desk-integration` и на
  `recovery/2026-10-20` не включится. Это следствие конфигурации, не дефект; новые трассировки
  требуют отдельного решения (R1.3-next).

## 3. Developer rehearsal

### 3.1 Без аккаунтов

- `conduct demo` и `conduct integration-smoke` (smoke шаги 4–7 и 11). Это синтетика и не
  заполняет rehearsal (`owner-acceptance.md`, последний абзац «Required real-result»).
- `owner-acceptance.md` шаги 1–9 и 15–17: установка, проект, Studio, редактор, inspector,
  публикация ревизий, перезагрузка, понятные отказы.
- Шаги 10–14 и `acceptance-two-tasks.md` шаги 4–6, 8 требуют назначить роли настроенным
  провайдерам. Без проверенной установки и разрешённых credentials документ велит продолжать
  редакторские проверки, а шаги исполнения записывать как blocked (`owner-acceptance.md` шаг 7).
- Fake-провайдеры есть только в тестах (`tests/_fakeexe.py` и т. п.). Пути для Studio в
  документах нет; core и browser suite уже проверяют дороги на fixture и fake.

### 3.2 Только с настоящим harness и аккаунтом

- Probe п. 13.
- Real-result п. 14: `dalio-v5`, проверяющий — другой участник (можно тот же harness).
  Если первый результат чистый, отдельный помеченный отрицательный контроль с настоящим
  checker. Чистый проход `dalio-v5` стоит 5 действий, с одной коррекцией 6, лимит Policy по
  умолчанию 8 (`src/conductor/command/templates/README.md:113-115`).
- `acceptance-two-tasks.md` шаги 7 и 9 (исполнение до первых ворот) и показания «Usage now».
- R-N1: записать, в какой кодировке настоящий vendor CLI пишет в pipe на русской Windows.

### 3.3 Что нужно от владельца

1. Решение **H5-V1** до всего остального. Сейчас (по коду) подписка внутри boundary
   отказывает до claim: `harness_attempt.py:159-166`; на экране отказ шага
   `sandbox route 'execution-boundary'` (`tasks/R2-H5-ANALYSIS.md` §0, §1.2). Если V1 = «только
   API-ключ» (рекомендация Opus), нужен хотя бы один ключ: `ANTHROPIC_API_KEY` для Claude Code
   2.1.239, `OPENAI_API_KEY` для Codex 0.112.0 или `DEEPSEEK_API_KEY` с балансом для DSH
   0.1.0-rc.7. Подписочный вход в V1 на Windows не исполняет задачи; он нужен только для
   показаний квот.
2. Закреплённые версии, штатный исполняемый файл (не `.cmd`), установленный под
   `<любой путь>\harnesses\<name>\<version>\` (`harness_attempt.py:70-93`). Иначе boundary не
   предоставляется и шаг отказывает. Скачивание установщиков — действие владельца в сети.
3. Явный бюджет. Оценка Opus по документам, не измерение: probe — 2 вызова на провайдера;
   rehearsal — 5–6 действий на прогон плюс отрицательный контроль; две задачи — первые шаги до
   ворот; повтор владельца — столько же. Итого порядка 20–30 действий за оба прохода.
4. Время владельца (оценка Opus, в документах её нет): 3–5 часов на 17 + 10 шагов и
   real-result.
5. **Перенос candidate-wheel на ноутбук.** Wheel собирает CI. На ноутбуке нет входа в GitHub и
   нет `hatchling`, а агент сеть не использует. Скачивание — действие владельца или происходит с
   его явного разрешения в чате. Два варианта (подробности в `tasks/R5-WINDOWS-WHEEL-ROAD.md`):
   - **А (по `release-smoke.md` шаг 1).** Скачать artifact `candidate-wheel` job `wheel` на точном
     SHA кандидата. Кто: владелец своим входом в GitHub либо Codex через GitHub-коннектор по его
     поручению; Claude Code входа не выполняет. Рядом записать sha256 из output job `wheel` и
     сверить `Get-FileHash` распакованного `.whl`: дайджест самого zip — другая величина.
     Прецедент: `outputs\recovery-2026-10-20\candidate-wheel.zip` (artifact 12145016129,
     1 937 657 байт) получен этим путём для `4d0e3af`; для `04641ca` он не годится.
   - **Б.** Разово скачать из PyPI `hatchling` (по метаданным — ещё `pathspec` и
     `trove-classifiers`; оффлайн не проверено) в `...\work\r5w\wheelhouse` и собрать wheel из
     `git archive` SHA. Разрешает владелец. Такой wheel становится кандидатом, только если его
     sha256 совпал с sha256 из CI (5.1).
6. **Python 3.11+.** У владельца нет системного Python (измерено: нет `C:\Windows\py.exe`;
   `python` — заглушка `WindowsApps`); есть только набор Codex (3.12.14). Поэтому `py -3 -m venv`
   из `first-run-v1.md` и `python -m venv` из `owner-acceptance.md` шаг 1 на ноутбуке не
   сработают. Варианты: (а) владелец устанавливает Python 3.11+ обычным способом, скачивание
   установщика — его действие; (б) в команды подставляется полный путь к `python.exe` набора
   Codex (`...\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`): без
   установки, но окружение принадлежит Codex и может исчезнуть (`LOCAL-SETUP.md`). Выбор и его
   запись — за владельцем. `first-run-v1` (оба языка) и `owner-acceptance` шаг 1 теперь
   говорят: если `py`/`python` не найден, подставьте полный путь к `python.exe` версии 3.11+.

## 4. Owner acceptance на этом ноутбуке

### 4.1 Подготовка (разработчик)

- Кандидат по разделу 5.1: SHA, имя wheel и SHA256 владельцу; wheel на ноутбуке и Python 3.11+
  по 3.3 п. 5–6.
- Решения раздела 4.3 приняты или явно отложены с записью.
- Пункты 1–12 таблицы зелёные; провайдер установлен по 3.3.
- Документы владельца исправлены по T1–T3 (5.2) и закоммичены; пока нет, владелец идёт по
  разделу 4.2, а не по шагам 1, 3, 16 прежней редакции `owner-acceptance.md`.

### 4.2 Сценарий

Короткий `--basetemp` нужен только pytest; владельцу он не нужен. Длина пути проекта при этом
важна (шаг 2 ниже).

1. **Оболочка.** Обычная Windows PowerShell, не `Open-December-Command.cmd`. Скрипт окружения
   ставит первым в `PATH` dev-`.venv` (editable `conduct`), задаёт `PYTHONUTF8=1`,
   `PYTHONIOENCODING` и `TEMP=...\Documents\Codex\work\dc-temp`. Так окружение владельца
   отличалось бы от настоящего. На ноутбуке нет `py` и системного Python (измерено: нет
   `C:\Windows\py.exe`, есть только заглушка `WindowsApps\python.exe`). Шаг `py -3 -m venv` из
   `first-run-v1.md` здесь не сработает. Варианты: явный путь к базовому
   `...\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` (3.12.14) или
   установка Python 3.11+ владельцем (3.3 п. 6).
2. **Установка и проект — пути `first-run-v1.md` §1–2**: `%LOCALAPPDATA%\DecemberCommand\app-v1`
   и `%USERPROFILE%\DecemberTrial` (35 символов). Не `$ACC` из прежней редакции
   `owner-acceptance.md` шаг 1 (`GetTempPath`): `$ACC\project` занимает 100 символов, со
   скриптом окружения 110 (измерено). Черновик процесса с id в 128 символов (шаг 4) пишется в
   `<root>\conductor.v3\templates\<id>\draft.json` со staging-именем
   `.draft.json.xxxxxxxx.tmp`. Условие `root + 49 + id ≤ 259`, то есть `root + 177` при id в 128
   символов (`template_store.py:248-259`, `path_admission.py:54-58`).
   **Измерено (T2, `04641ca`):** `init`, `ownership activate` и `up` проходят при любой длине
   корня. Отказ только при сохранении черновика в шаге 4: HTTP 422, `windows_path_too_long`
   («shorten the identifier or move the project to a shorter path; the Windows path budget is
   exceeded»). Корень 82 + id 128 — 201, путь staging ровно 259; корень 83 — 422; корень 100: id
   в 110 символов проходит, в 111 нет; корень 35 (длина `%USERPROFILE%\DecemberTrial`) — 201. Экран
   отказа в браузере не смотрели. Пределы 60 и 100 (`project_targets.py:52,88`,
   `projects_add.py:83`) действуют только для hub и `projects add`, на `init` и `up` не влияют.
   Сверить `Get-FileHash` wheel с выданным SHA256. В пути не использовать `$`, обратную кавычку и
   `%` (N3-D3). Кириллица в пути допустима (N1, N3).
3. **Провайдер.** `conduct providers --dir <project>` по выбранной в H5-V1 дороге: только имена
   переменных, ключ в окружении запущенного сервера. Три отказа ввода из шага 7.
4. **Запуск и остановка `conduct up`** — как в `first-run-v1.md` §4: в видимом окне, остановка
   Ctrl+C **после** появления URL. R1.5 (`ce3b7bd`) закрыл окно, в котором Ctrl+C после URL
   уходил мимо drain. Остался зазор около 1 мс до печати URL (`tasks/R1.5-REPORT.md`). После
   остановки `conduct ownership status` должен ответить `closed`.
   **Шаг 3 `owner-acceptance.md` в прежней редакции (скрытый `Start-Process … -PassThru
   -WindowStyle Hidden`) делал Ctrl+C невозможным, а шаг 16 завершал процесс через
   `Stop-Process`.** Оба шага исправлены в рабочей копии: сервер запускается во втором видимом
   окне PowerShell, остановка — Ctrl+C в этом окне. Замеры на `04641ca` (T1, T3):
   - **`Stop-Process` (T1).** Шаг 3 буквально, HTTP 200 через 0,6 с, затем `Stop-Process -Id
     $APP.Id`: убито всё дерево `conduct.exe→python→python`, код выхода -1. `ownership status`
     показывает `opened` и при живом, и при убитом сервере. Повтор шага 3 молча завершается с
     кодом 1: текст отказа виден только при перенаправлении вывода. `doctor` про владение молчит.
     Следующий `up` получает `recovery_required` (`ownership.py:115-116`), а `ownership recover`
     требует полной перезагрузки ОС (`ownership_transition.py:267-296`). Тексты отказов:
     `conduct up: refused recovery_required: previous owner did not close; recover explicitly
     after OS restart`; `ownership recover`: `recovery_required: restart the OS before recovering
     an uncertain writer session (do a full Restart, not a shutdown)`; `ownership recover
     --prepare-restart`: `recovery_refused: no preparation is needed: … do a full Restart (not a
     shutdown), then run ownership recover`. Восстановление: полная перезагрузка ОС, затем
     `ownership recover`. Саму перезагрузку не выполняли: путь называют сами отказы.
   - **Ctrl+C (T1).** `CTRL_C_EVENT` в собственную скрытую консоль процесса, как в
     `_drain_harness`: выход 0 за 0,4 с, `closed`; повторный `up` работает (проверено дважды).
   - **Ctrl+C из окна владельца после скрытого запуска (T3).** PowerShell выходит с кодом 1,
     сервер продолжает отвечать HTTP 200, `opened`. Остановить его смог только помощник,
     подключившийся к скрытой консоли сервера; человеку это недоступно.
   Не измерено: закрытие окна консоли с сервером; экран браузера при отказе черновика.
   Не выполнять шаг 16 через `Stop-Process`. Остановить Ctrl+C и запустить снова той же командой.
5. Пройти `owner-acceptance.md` 3–17, затем `acceptance-two-tasks.ru.md` 1–10, затем real-result
   на отдельном свежем проекте.
6. **Что владелец увидит и должен оценить как решение, а не как находку.**
   - R1.2c, вариант A1: запуск с планом `stalled` читается «Завершён · Ваше действие не
     требуется»; отличие видно только по токену `stalled`. Строка desk бывает «Исход неизвестен»
     и даже «Успешно».
   - R1.2-W: один тик слот показан занятым.
   - R3.1-Q1–Q3: появление задачи после мастера, сцена без автоперехода на новый запуск,
     прокрученный iframe хаба.
   - Разовый 10055 у пользователя даёт пустую оболочку Studio/Desk до перезагрузки страницы
     (`tasks/R1.3-WIN-10055-CI41.md` §8, вопрос UX).
7. **Запись.** Вердикт по каждому шагу, SHA и wheel, версии harness, участники и модели, бюджеты.
   Ключи, сырой вывод checker и закрытое содержимое проекта не записывать.

### 4.3 Решения, без которых приёмка не закрывается

По `HANDOFF-2026-10-21.md` п. 7 и `tasks/CODEX-REVIEW-ff0ce19.md`:

- Владелец: **H5-V1** (первым); **R1.2c-В1** (A1/A2/A3, лучше после того, как владелец увидит
  экран); **R4-V1** (`requested_by`); **R3.1-Q1, Q2, Q3**; **R1.2-W**.
- Codex: **R4-V3** (D1, вариант A уже в коде), **R4-V2**, **R4-V4**, **R4-G**; **H5-C** и
  **O-N1** (связаны с H5); **R1.2c-В2…В4**; **N3-D3** (документировано в docstring).
- Решаются по данным и приёмку не блокируют: **R1.5-B**; **R1.3-next** (по `netfail` из CI
  `04641ca`); **R-N1** (наблюдение на rehearsal).
- Новые вопросы этого плана, раздел 5.4.

## 5. Выпуск

### 5.1 Что такое кандидат

- Один полный SHA. На нём CI-run, где зелены все 12 job: 6 core, 3 browser (оба порядка), wheel,
  2 road. Повтор CI после красного допустим только с записью сбоя
  (`release-smoke.md` «Known gaps», 10055): команда, состояние сокетов, таймаут. Зелёный повтор
  не объясняет первый сбой.
- Один wheel `agent_conductor-0.1.0-py3-none-any.whl` из artifact `candidate-wheel` этого run.
  Его sha256 из output job `wheel` равен `wheel.sha256` в обоих `report.json` road и
  `Get-FileHash` файла, который ставится на Windows. Версии в `pyproject.toml` и
  `conductor.__version__` обе `0.1.0` (проверено чтением).
- Условие кандидата по wheel — **совпадение SHA**: sha256 файла, который ставится на Windows,
  равен sha256 из output job `wheel`. Для локальной пересборки (вариант Б, 3.3 п. 5) нужен
  `hatchling` из сети; её wheel годится, только если это условие выполнено. Что байты разошлись бы, не
  доказано: CI ставит `hatchling` без закрепления версии (`ci.yml`, `python -m pip install
  build`), и совпадение зависит от его версии и входных файлов; версию сверить по логу job.
  Документы расходятся: `release-smoke.md` шаг 1 не принимает «отдельно пересобранную ревизию,
  чьи байты отличаются», отчёт `tasks/R5-WINDOWS-WHEEL-ROAD.md` (вариант Б) принимает локальную
  сборку при совпадении SHA. Они согласуются через это условие: совпал SHA — байты не
  отличаются; не совпал — единственным wheel остаётся CI-вариант. Скачать artifact (вариант А)
  можно только со входом в GitHub: вход владельца либо коннектор Codex. Агент сеть не
  использовал.
- К кандидату приложены: п. 9 на этом SHA, п. 10–12, ревью п. 18, решения п. 19.

### 5.2 Документы, которые надо обновить

- `docs/release-notes-v1-alpha.md` и `.ru.md`: всё привязано к `frozen-19`, `d4d2580`, wheel
  `47b5dc64…`, 8459 тестам и «Only Claude has run live». Нужны: SHA и wheel кандидата, run CI,
  платформы (Windows road вручную, POSIX без исполнения), H5 (подписка не исполняет), новые
  известные ограничения (10055 с частотой, A1, R3.1-Q1–Q3, остаток R1.5, N3-D3, `Stop-Process`),
  реальные live-прогоны кандидата. Обновить оба файла или заменить новым снимком — решает Codex.
  Release notes в правке 21.10 **не тронуты**: их обновление — отдельный шаг после выбора
  кандидата.
- Устарело относительно кода, исправить до приёмки. Состояние на 21.10: правки сделаны в рабочей
  копии, не закоммичены. Пары EN/RU: `first-run-v1` (`.md` ru, `.en.md`), `CONTRIBUTING.md` и
  `.ru.md`, `README.md` и `.ru.md`; у `owner-acceptance.md` и `release-smoke.md` пар нет (5.4, Р-6).
  - `docs/first-run-v1.md` и `.en.md`. Сделано: подраздел §3 «Где задачи исполняются в этой
    сборке» (Windows — только дорога API-ключа и установка в `harnesses\<name>\<version>`;
    подписка внутри изоляции отказывает до запуска, квоты читаются; macOS и Linux — изоляции нет,
    любой шаг с задачей отказывает до запуска, разделы macOS / Linux годятся для настройки и
    осмотра, а не для исполнения), сформулированный как поведение текущей сборки, а не
    окончательное решение по H5; запасной путь вместо `py -3`; короткий путь проекта (≤ 82
    символов) и причина; остановка только Ctrl+C и что бывает после принудительного завершения;
    строки таблицы «Если что-то мешает». Не сделано: ссылки «результаты приёмки в заметках к
    кандидату» — они ждут release notes.
  - `docs/owner-acceptance.md`. Сделано: шаг 1 (`$ACC` в `%LOCALAPPDATA%`, объяснение лимита пути)
    и шаг 2 (`%USERPROFILE%\DecemberTrial`); шаг 3 (второе видимое окно PowerShell, без
    `-WindowStyle Hidden`, ожидание URL); шаг 7 (оба «restart `conduct up`» — как в шаге 16; текущее
    поведение подписки и POSIX); шаг 16 (Ctrl+C, проверка `closed`, предупреждение о
    принудительном завершении, перезагрузка ОС и `ownership recover`); «Reload and restart» в
    real-result.
  - `docs/release-smoke.md`. Сделано: шаг 2 — сравнивать набор из 15 команд, не текст usage
    (в нём другой порядок и перенос); шаг 10 и «Known gaps» — `Stop-Process -Force` на
    активированном проекте оставляет `opened`; запись о 10055 дополнена частотой (около 1 на 1900
    контекстов, λ ≈ 0,5 на порядок, около 37 % зелёных пар) и счётчиком `netfail` (R1.3-E1);
    «Any platform but this one»: «no CI run exists» и «walked locally on Windows» заменены
    (Windows-раннера нет, дорога вручную); «Ctrl-C» — видимое окно.
  - `CONTRIBUTING.md` и `CONTRIBUTING.ru.md` «Проверьте своё изменение»: полные команды для
    Windows теперь с `--basetemp C:\pt`, `--artifacts C:\bg` и `C:\bgr` и пояснением (≤ 26
    символов целиком, ссылка на `LOCAL-SETUP.md`). Раньше с путями по умолчанию на этом профиле
    получалось `windows_path_too_long`.
  - `README.md` и `.ru.md`: одно предложение под таблицей harness о том, где исполняются задачи.
  - `CONTINUATION-PLAN.md` R0 и R1: рабочая ветка теперь `recovery/2026-10-20`. Не тронуто.

### 5.3 Порядок на 1–2 дня

День 1 (21.10):

1. Codex через GitHub: итог №42 и CI на `04641ca` по job. Скачать и захешировать `bg`/`bgr`,
   `wheel-road-*`, `candidate-wheel`. Свести `netfail` по правилам R1.3 §8. Красное без объяснения
   — стоп и разбор. Красный Windows gate по 10055 — запись и повтор job.
2. Владелец: H5-V1. Затем R1.2c-В1 (можно после 4.2 п. 6), R4-V1, R3.1-Q1–Q3, R1.2-W.
3. Codex: ревью п. 18, в первую очередь коммиты со `src/`: `f8f562b`, `ce3b7bd`, `04641ca`,
   `9c8fa7c`, `c07f447`, `63daddb`, `ba09148`.
4. Правка документов 5.2, кроме release notes с итогами (сделана в рабочей копии 21.10; остаются
   проверка Codex и пункты «Не сделано»). Коммит, push, CI. Этот SHA — кандидат.
   Без правок кандидатом остаётся `04641ca`, а владелец пользуется разделом 4.
5. Параллельно с CI: п. 9 на кандидате (кириллический basetemp ≤ 26 символов, например
   `C:\Users\Пользователь\pt-1`, из чистой копии в git).

День 2 (22.10):

6. После зелёного CI кандидата: п. 10–12 на Windows с CI-wheel в обычной оболочке.
7. При наличии ключа и установок: п. 13, затем п. 14 и шаги исполнения п. 16 (разработчик).
8. Владелец: п. 15–17 по разделу 4.
9. Release notes по фактам, статусы раздельно: реализовано / локально проверено / проверено CI /
   принято ревью / принято владельцем. Публикация и тег — отдельное решение.

Критический путь: H5-V1 → ключ и установка → rehearsal → приёмка владельца. Параллельно идут
CI (6 core-job по 19–32 мин) с возможными повторами Windows gate. Время browser-job на этом SHA
не измерено: цифра 44 мин в документах относится к другим измерениям (позиция модуля на Windows
runner в `tasks/R1.3-WIN-10055-CI41.md`, macOS на `frozen-19` в release notes 25.09) и не служит
прогнозом. Без ключа к концу дня 2 закрываются только шаги без исполнения. Real-result
записывается как blocked; выпуск не объявляется.

### 5.4 Новые вопросы

- **Р-1 (Codex).** Docs-коммит с итогами приёмки после кандидата меняет SHA. Считать ли кандидатом
  прежний SHA, если `git diff <кандидат> <итог> -- src tests browser_tests scripts .github
  pyproject.toml` пуст, или требовать CI на итоговом SHA (`release-smoke.md`: «green jobs … on the
  final candidate»)?
- **Р-2 (Codex).** Нужен ли воспроизводимый Windows-раннер road в репозитории вместо ручного
  прохода. Подход к Ctrl+C на Windows описан в `tests/_drain_harness.py` и в
  `tasks/R5-WINDOWS-WHEEL-ROAD.md`. Предложение Opus, не шаг документов.
- **Р-3 (Codex).** Pre-existing: на Python 3.11 `conduct doctor --dir=--` падает трассировкой
  (`tasks/N3-REPORT.md`, по скептику, не измерено). Вне V1-блокеров или исправлять?
- **Р-4 (Codex).** `conduct doctor` не показывает владение `opened` и о владении молчит (T1).
  Человек узнаёт о застрявшем владении только из отказа следующего `up`. Должен ли `doctor`
  сообщать состояние владения и выдавать находку `recovery_required` с командой `next:`? Продукт
  не менялся.
- **Р-5 (Codex).** `conduct ownership status` отвечает `opened` и при живом сервере, и при убитом
  (T1): живой сервер от убитого он не отличает. Нужна ли ему такая проверка или это сознательное
  свойство контракта? Не решено.
- **Р-6 (Codex, владелец; предложение Sonnet).** `docs/owner-acceptance.md` и
  `docs/release-smoke.md` есть только по-английски, пар `.ru` нет. У `first-run-v1`,
  `acceptance-two-tasks`, `CONTRIBUTING` и `README` пары есть. Нужен ли владельцу русский
  `owner-acceptance.md` до приёмки (около 500 строк)? Перевод не делался.
