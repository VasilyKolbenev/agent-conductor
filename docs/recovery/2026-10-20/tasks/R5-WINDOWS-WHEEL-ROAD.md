# Отчёт по задаче: R5 — installed-wheel road на Windows, commit 04641ca

- Исполнитель: Sonnet 5.5 (Claude Code), подзадача workflow-скрипта.
- Исходный commit и ветка: `04641ca32ac30b853277a2f41093167b2b0da964`,
  `recovery/2026-10-20` (запушен, `origin/recovery/2026-10-20` совпадает).
- Состояние рабочей копии до работы: чистая (`git status --short` пуст).
- Цель: один wheel из чистой выгрузки этого commit, чистый venv, шаги
  `docs/release-smoke.md` без аккаунтов и сети, честная остановка Ctrl+C.
- Правка 21.10.2026 (Sonnet 5.5, по ревью `R5-PLAN.md`; результат прогона не менялся): варианты А/Б
  (кто переносит wheel, прецедент, условие SHA), план шагов после разблокировки приведён к
  `release-smoke.md`, ручные пункты записаны как «проходит человек».
- **Итог: дорога НЕ пройдена. Остановка на шаге 1 (сборка wheel): backend сборки
  `hatchling` отсутствует на машине, а получить его можно только из PyPI. По заданию сеть не
  использовалась. Wheel не собран, venv `r5v`/`r5d` не создавались, ни один процесс продукта не
  запускался. Ни один шаг release smoke не засчитан.**

## Изменения

Единственный файл репозитория — этот отчёт. Код продукта, тесты, настройки Git и ОС не
менялись. Вне репозитория (каталог `C:\Users\Пользователь\Documents\Codex\work\r5w\`):

- `src-04641ca.tar` — `git archive` commit, 20 869 120 байт, SHA256
  `05f3eebe4d9508cac3ebe6f3daa3d2354cdc68ee68792361ab9680b9c6e6bd28`;
- `src-04641ca\` — его распаковка, 1516 файлов, тот же commit;
- `dist\` — пуст (wheel не собран);
- `logs\01-build-no-isolation.log` — вывод единственной сборочной попытки.

## Проверки

| Команда | Среда | Результат | Что доказывает |
| --- | --- | --- | --- |
| `git archive --format=tar --output=...\src-04641ca.tar 04641ca` | Git 2.53.0.windows.3, репозиторий | exit 0 | выгрузка без обращения к рабочей копии |
| `cmd /c "git get-tar-commit-id < ...\src-04641ca.tar"` | то же | `04641ca32ac30b853277a2f41093167b2b0da964` | архив сделан ровно от кандидата |
| `tar -xf` в `src-04641ca` | Windows tar | exit 0, 1516 файлов | чистая выгрузка есть |
| `python -m build --wheel --no-isolation --outdir ...\dist ...\src-04641ca` | `.venv` (Python 3.12.14, build 1.6.1) | **exit 1**, `BackendUnavailable: Cannot import 'hatchling.build'` | backend из `[build-system]` недоступен локально |
| поиск `hatchling*` в `.cache`, `AppData\Local`, `AppData\Roaming`, `Documents\Codex`, `Program Files*`, `ProgramData`, pip-кэше | профиль пользователя | ничего не найдено | оффлайн-источника нет; в `.venv` есть только `packaging`, `pluggy` |

Изолированную сборку (`python -m build --wheel` без `--no-isolation`) намеренно не запускали:
она скачала бы `hatchling` из PyPI. После запуска `--no-isolation` проверено, что репозиторий и
выгрузка не изменились (`git status` пуст, 1516 файлов).

## Что освобождает дорогу

Сборочная зависимость в `pyproject.toml`: `requires = ["hatchling"]`. Во время работы пакета
зависимостей нет, так что установка готового wheel `--no-index --no-deps` сети не потребует.
Нужен один из вариантов, решение за владельцем (скачивание требует явного разрешения в чате):

- **Вариант А (ближе к release-smoke).** Взять wheel, который собрал CI, — artifact
  `candidate-wheel` job `wheel` на commit `04641ca`, и его `sha256` из outputs этого job.
  `docs/release-smoke.md`, шаг 1, требует установить wheel, собранный от точного SHA, а не
  «отдельно пересобранную ревизию, чьи байты отличаются». Минус: скачивание artifact требует входа
  в GitHub; агент этого не делает. Кто и с чьего разрешения: владелец своим входом в GitHub либо
  Codex через GitHub-коннектор по поручению владельца. Этот путь уже работал:
  `outputs\recovery-2026-10-20\candidate-wheel.zip` (artifact 12145016129, 1 937 657 байт) — wheel
  от `4d0e3af`; для `04641ca` он не годится. SHA256 сверять у самого `.whl` с `sha256` из output
  job `wheel`, а не у zip.
- **Вариант Б.** Разрешить один раз скачать из PyPI `hatchling` и его зависимости (по метаданным
  hatchling это `pathspec` и `trove-classifiers`; `packaging` и `pluggy` уже есть; не проверено
  оффлайн) в каталог `...\work\r5w\wheelhouse`. Затем собрать как в CI. Версию hatchling записать и
  сверить с логом job `wheel`: CI ставит его без пина, и локальный wheel годится как кандидат,
  только если его SHA256 совпадёт с `sha256` из CI. Иначе единственным wheel остаётся CI-вариант.
  Документы здесь не противоречат друг другу, если читать условие SHA: возражение `release-smoke`
  относится к wheel с другими байтами, а совпадение SHA256 означает, что байты те же. Что байты
  разошлись бы, не доказано (R5-PLAN 5.1).
- Отдельно от выбора А/Б: на ноутбуке нет системного Python (нет `py`, `python` — заглушка
  `WindowsApps`), поэтому пункт 2 плана ниже использует Python набора Codex. Для владельца нужна
  установка Python 3.11+ или полный путь к `python.exe` (R5-PLAN 3.3 п. 6).

## План после разблокировки (не выполнялся)

1. `python -m build --wheel --outdir ...\r5w\dist ...\r5w\src-04641ca`; ровно один `.whl`; имя,
   размер, SHA256 в отчёт.
2. Базовый Python (`home` из `.venv\pyvenv.cfg`):
   `C:\Users\Пользователь\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m venv C:\Users\Пользователь\r5v`;
   `r5v\Scripts\python.exe -I -m pip --isolated install --no-index --no-deps --no-compile
   --disable-pip-version-check <wheel>` (как `scripts/wheel_road.py::install`).
3. Происхождение: `r5v\Scripts\python.exe -I src-04641ca\scripts\installed_probe.py` — отказывает,
   если `conductor` не из venv; сверить хеши файлов пакета с содержимым wheel; отдельно
   `conductor.__file__`.
4. Шаги 2–12 `docs/release-smoke.md` в его порядке и с его ожиданиями. `/panel/desk.html` в нём
   нет: `GET /` отдаёт оболочку Studio, classic panel — `/panel/index.html`.
   - Шаг 2: `--help`, exit 0. Сравнивать **набор** из 15 подкоманд, не текст: usage печатается в
     другом порядке и с переносом строки.
   - Шаг 3: `conductor.__version__` = `0.1.0`; совпадение с `pyproject.toml` глазами (у CLI нет
     `--version`).
   - Шаг 4: `demo --port 7801`; stdout — один URL, stderr — три строки (fixture, `demo workflow
     demo-orbit revision 1, run run-demo-001, gate gate-confirm-do is waiting`, `serving … — Ctrl+C
     to stop`).
   - Шаг 5: `GET /` — 200, `text/html; charset=utf-8`, `December` в `<title>`; `GET /state.json` —
     `project=web-app state=blocked reason=human_decision`, `findings=3 queue=1`;
     **`GET /handoff/claude.md`** — `200 text/markdown; charset=utf-8`, первая строка
     `# Conduct handoff — claude`.
   - Шаг 6: ровно один слушающий сокет, `127.0.0.1`; отказ при обращении к LAN-адресу машины.
   - Шаг 7: сканирование всего каталога `panel` установленного wheel (десятки файлов; единственный
     абсолютный URL — `http://www.w3.org/2000/svg`; все сетевые вызовы и ресурсы same-origin);
     `GET /harnesses.json` — каждый непустой `docs` начинается с `https://`, пустой только у
     `custom`; остановить demo.
   - Шаг 8: `init --template default-orbit` (exit 0, bootstrap prompt на stdout, `conduct
     validate: clean`), повтор — отказ, exit 1; **`ownership status`** — состояние свежего legacy,
     exit 0, без активации.
   - Шаг 9: `validate` (молчит, exit 0), `doctor` (exit 1, последняя строка `not ready: 3
     finding(s), 0 unknown, 2 ok.`, у каждой находки команда `next: conduct ...`), `report`,
     `prompt --role scout --author claude`.
   - Шаг 10: `up --port 7802` (URL на stdout, `/state.json` → `ready`) и второй `up` на занятом
     порту: exit 1, `bind_failed` и подсказка про `--port`.
   - Шаг 11: `preview` (одна JSON-строка, `preview_digest`, повтор побайтно тот же), с `--instance
     ghost` и `--adapter codex` — exit 1; `integration-smoke` — exit 0, исход
     `verification_failed` ожидаем; `reconcile` — exit 0 и `no action in this project is waiting
     for reconcile` на stderr.
   - Шаг 12: `providers` без терминала — exit 1, пустой stdout, строка `conduct providers needs a
     terminal: …`. Интерактивную часть шага проходит человек (см. таблицу ниже).
   `Stop-Process -Force`, которым smoke останавливает demo (шаг 7) и `up` (шаг 10), допустим здесь
   только для demo и неактивированного scaffold: на активированном проекте он оставляет `opened`
   (R5-PLAN 4.2 п. 4). Штатная остановка проверяется пунктом 5.
5. Остановка Ctrl+C: приём из `tests/_drain_harness.py` — сервер в скрытой `CREATE_NEW_CONSOLE`,
   помощник делает `AttachConsole(pid)` и `GenerateConsoleCtrlEvent(0, 0)` при
   `SetConsoleCtrlHandler(None, True)`; сначала доказать доставку на простом sleeper. Ожидать exit 0,
   `ownership status` = `closed` и повторный запуск без recovery (как `serve_once` в
   `wheel_road.py`). По замеру Opus (T1) такой приём на `04641ca` даёт exit 0 за 0,4 с, `closed` и
   рабочий повторный `up`. Это имитация Ctrl+C в консоли сервера; Ctrl+C рукой в видимом окне
   (`owner-acceptance.md` шаги 3 и 16) всё равно проходит человек.
6. `doctor` в каталоге с кириллицей и пробелом (например `C:\Users\Пользователь\r5d\Проект проверки`):
   напечатанные `next:` команды выполнить в cmd и в Windows PowerShell 5.1.
7. Удалить `r5v` и `r5d` после записи результатов; `dist` и `logs` оставить.

## Что из release smoke пройдено / не пройдено

| Шаг | Статус | Причина |
| --- | --- | --- |
| 1–12, Teardown | не пройдены | нет wheel |
| Ручные пункты (шаг 12 и «What this procedure does not check»): мастер `conduct init` с настоящим терминалом, интерактивный `conduct providers` (три отказа ввода, хотя бы один harness каждого вида), Ctrl+C рукой в видимом окне, classic panel и Studio в браузере | не пройдены; **их проходит человек** (разработчик или владелец; Studio — `owner-acceptance.md`) | скрипт и помощник их не заменяют: нужны живой терминал, окно и браузер человека; аккаунты не нужны |
| `/command/*`, `conduct tools`, `conduct hub`, `conduct projects add`, умолчание `init` без терминала | вне этой дороги | по самому документу их держат тесты (`test_tool_pins.py`, `test_hub_command.py`, `test_hub_live.py`, `test_projects_add.py`, `test_hub_operations.py`, `test_init.py`); их результат — core-job CI на том же SHA |
| Дополнительные gates (реальный checker, push/CI трёх ОС, owner exercise) | вне этого прогона | нужны аккаунты, платные вызовы или решения владельца |

Расхождение с CI: `scripts/wheel_road.py` завершается `SystemExit` при `os.name != "posix"`, а
матрица `wheel-road` в `.github/workflows/ci.yml` — только `ubuntu-latest` и `macos-latest`.
Windows-раннера дороги с Ctrl+C в репозитории нет. Прежняя фраза `docs/release-smoke.md`, что
дорога «walked locally on Windows», заменена в рабочей копии 21.10: дорога на Windows идёт вручную,
вывод хранится с кандидатом. Этот отчёт не заменяет такую запись: для commit 04641ca такой
записи пока нет.

## Не проверено

Всё, что требует установленного wheel (см. таблицу выше). Полный core suite, оба порядка browser gate
и результаты CI на `04641ca` здесь не рассматривались и не заявляются.

## Ревью Codex

Не заполнено.

## Передача

- Итоговый commit: не создан (по заданию).
- `git status`: до работы чистый; после — один новый файл, этот отчёт.
- Оставлено запущенным: ничего. Порты 7700, 7777, 7801, 7802 до работы свободны.
- Следующий конкретный шаг: решение владельца между вариантом А и Б и выбор Python 3.11+
  (`R5-PLAN.md` 3.3 п. 5–6); затем пункты 1–7 плана.
