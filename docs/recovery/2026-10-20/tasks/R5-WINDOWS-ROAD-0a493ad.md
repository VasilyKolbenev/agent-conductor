# Отчёт по задаче: R5 — Windows installed-wheel road, wheel 0a493ad

- Исполнитель: Claude Code / Sonnet 5.5 в workflow, ведущий Opus 5.5.
- Кандидат: commit `0a493ad8a9962cc6e442b9d9e3c8ca104c5a1096`, CI №46 (run 39645262035),
  artifact `candidate-wheel` 12367660793. По `ci-snapshot.json` (срез Codex, 17:56 UTC) CI ещё
  шёл: зелёными были `build one wheel` и два `installed wheel road`. Финальная приёмка
  кандидата возможна только после полностью зелёного CI.
- HEAD рабочей копии: `8f081b4ebe7f3f071590892decec4a14584b66c9`, ветка `recovery/2026-10-20`.
  Это кандидат и два docs-коммита (`48fdde3`, `8f081b4`). Команда `git diff 0a493ad HEAD --
  src tests browser_tests scripts pyproject.toml .github` дала пустой вывод, exit 0.
- Состояние рабочей копии до и после работы: ` M docs/recovery/2026-10-20/R5-REHEARSAL-RUNBOOK.md`
  (правка Codex, не трогал). Единственный новый файл репозитория — этот отчёт. Коммитов нет.
- Wheel: `agent_conductor-0.1.0-py3-none-any.whl`, 1 985 026 байт, SHA256
  `90c0da18af8e254d5b455faebcd27e26aebe75a01e1bec16ef306ed4891ec3f8`.
- Среда: Windows 11 Pro 10.0.26300, Windows PowerShell 5.1.26100.9444, базовый Python 3.12.14,
  в venv pip 25.0.1. Прогон 21.10.2026, 21:05–21:16 МСК, затем отчёт. Ни ключей, ни
  провайдеров; из сети — только loopback и собственный LAN-адрес машины (шаг 6).
- Цель: пройти шаги 2–12 `docs/release-smoke.md` и Windows installed road (два срока
  `conduct up`, Ctrl+C, `closed`) на CI-wheel кандидата, в частичной имитации чистой
  оболочки (границы имитации — в разделе «Проверки»).
- **Итог: дорога пройдена. Wheel кандидата (его скачал Codex как artifact CI) ставится
  оффлайн; установленные байты равны wheel; оба срока `conduct up` останавливает доставленный
  Ctrl+C (exit 0, `opened` → `closed`); напечатанные doctor команды работают в cmd и
  PowerShell 5.1 в пути с кириллицей и пробелом. Три независимых проверяющих Opus
  подтвердили результат дороги (раздел «Ревью Opus»); по их замечаниям отчёт исправлен.
  Расхождений с `release-smoke.md` пять (находки 1-5): три — устаревший текст документа,
  одно — ловушка кириллического профиля в шаге 7, одно — поведение продукта (`conduct
  providers` при stdin = NUL). Какие из них блокируют выпуск по правилу документа («шаг не
  совпал — блокер»), а какие закрывает правка документа, решает Codex.**

## Изменения

- Единственный файл репозитория — этот отчёт. Код продукта, тесты, документы, Git и
  настройки ОС не менялись.
- Вне репозитория — каталог доказательств EV, `C:\Users\Пользователь\Documents\Codex\work\r5w46\`
  (состав в разделе «Передача»).
- В профиле пользователя новое: два каталога `conduct-demo-*` в TEMP (их создаёт сам
  `conduct demo`) и basetemp `C:\Users\Пользователь\pt-rw1` от pytest. Каталог
  `.december-command` в профиле не появился (проверено до и после).

## Проверки

Оболочка: Windows PowerShell 5.1, каждый вызов — новый процесс, переменные в `EV\vars.ps1`.
`vars.ps1` убирает только четыре переменные: `PYTHONPATH`, `PYTHONHOME`, `PYTHONUTF8`,
`PYTHONIOENCODING`. Исходно были пусты первые три; `PYTHONIOENCODING` была
`utf-8:surrogateescape` (запись в `logs/00-preflight.txt`). Dev `.venv` в PATH не стоял,
`December-Command-Environment.ps1` для дороги не подключался. Логи — `EV\logs\NN-*.txt`, сырые
байты — `EV\raw\`.

«Чистая оболочка» здесь частичная. Что осталось от среды запуска:

- `PYTHONDONTWRITEBYTECODE=1` унаследована всеми процессами (`logs/00`, строки 2-3). `python
  -I` её игнорирует, поэтому в venv появились `.pyc` (см. ниже).
- Около 33 переменных среды агента (`CLAUDECODE`, `CLAUDE_CODE_*`, `ANTHROPIC_BASE_URL` и
  др.; только имена) унаследованы всеми процессами `conduct`. Это замер ревью: в EV список не
  записан, `logs/00` хранит только семь переменных.
- Продукт напрямую по имени читает из среды лишь `DISPLAY`, `WAYLAND_DISPLAY`
  (`hub/dialogs.py:28`, `hub/pick_folder.py:48`), `USERPROFILE`
  (`command/adapters/process_loans.py:229`) и `CONDUCT_HOME` (`hub/home.py:45`; не задана,
  `logs/00`); allowlist-ы (`tool_env`, `env_allow`) выбирают свои имена из снимка. Снимок
  всего `os.environ` берут `hub/spawn.py:141` (и отдаёт его дочерним серверам хаба, :165) и
  `command/adapters/process.py:470`; второй агентам передаёт только переменные из allowlist
  (`select_environment`, docstring :17-22). В дороге агенты и хаб не запускались, влияния нет.
- Дорога шла дочерними процессами приложения Claude (пакет MSIX). Ведущий 21.10 измерил, что
  запись в `%LOCALAPPDATA%` из этого контекста перенаправляется в
  `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\…` (в EV не записано). EV
  лежит в Documents, `%TEMP%` и `%USERPROFILE%` не перенаправляются, так что на дорогу это
  не влияет.

| № | Команда | Результат | Что доказывает |
| --- | --- | --- | --- |
| 1 | `Get-FileHash` wheel и его копии | оба = ожидаемому | копия — тот же wheel |
| 2 | SHA256SUMS, provenance, build-output, snapshot | commit и sha совпали | данные согласованы |
| 3 | zip `ci46-12367660793.zip` под `python -I` | один wheel, байты = копии | в zip этот wheel |
| 4 | `python -I -m venv`; `pip install --no-index --no-deps` | exit 0 | оффлайн, один wheel |
| 5 | `pip list`; `pip show -f agent-conductor` | 0.1.0; Editable нет | установка не editable |
| 6 | `python -I -c "import conductor ..."` | из `venv\Lib\site-packages`, 0.1.0 | импорт из venv |
| 7 | `installed_probe.py` под `-I` | exit 0; 478 файлов, 159 маршрутов | как в CI-дороге |
| 8 | `tools/record_verify.py` | RECORD 487 строк; 482 файла zip = диск | совпали; скрипт менялся |
| 9 | `wheel_road.http_checks` на demo | 166 проверок; 159 маршрутов = zip | отдаётся байты wheel |
| 10 | Контроль Ctrl+C на sleeper | код `0xC000013A` за 0,3 с | доставка Ctrl+C работает |
| 11 | Два срока `up --port 7853` | exit 0 за 0,30 и 0,66 с; `closed` | дорога Windows держится |
| 12 | Printed doctor-команды в cmd и PS 5.1 | exit 1/0/0, вывод = прямому argv | путь не разрезан |
| 13 | Процессы, порты, профиль, git в конце | пусто; HEAD и status прежние | остатков нет |
| 14 | `pytest -q --basetemp pt-rw1 tests/test_file_endings.py` | 9 passed, exit 0 | концы строк |

Подробности: п. 1-3 — `logs/01`, п. 4-8 — `logs/02`, п. 9 — `logs/09`, п. 10-11 — `logs/16`
и `logs/16-road-report.json`, п. 12 — `logs/17`, п. 13 — `logs/18`. П. 14 выполнен после
`. December-Command-Environment.ps1 -Quiet`. Этот тест читает только отслеживаемые файлы, а
отчёт ещё не в Git, поэтому его хвосты, табы, длину строк (не больше 100 символов) и единый
`\n` в конце проверил отдельный скрипт: чисто. Каталог `C:\Users\Пользователь\pt-rw1`
(basetemp pytest) оставлен.

Происхождение wheel (п. 2-3): что доказано офлайн и что взято из данных Codex.

- Доказано офлайн (`logs/01`): zip с именем `ci46-12367660793.zip` содержит ровно один wheel,
  и он побайтно равен копии (`testzip` — None, sha256 `90c0…`).
- Взято из данных, скачанных Codex, без сетевой сверки: что это artifact 12367660793 run
  39645262035 и что sha256 output job `wheel` равен `90c0…` (`provenance.json`,
  `build-output-evidence.json`). Формулировка «это artifact CI» этим не доказана.
- Ревью A проверило код кандидата: `needs.wheel.outputs.sha256` передаётся в `wheel_road
  --sha256` (`ci.yml:260-261`, 280, 332); все 478 файлов `conductor/` в wheel равны blob-ам
  `src/conductor` коммита `0a493ad`, `METADATA` = `README.md@0a493ad`.

Что именно сверялось в п. 7-8:

- В wheel 483 файла: `RECORD` и 482 других. В установленном `RECORD` 487 строк: pip добавил
  `conduct.exe`, `INSTALLER`, `REQUESTED`, `direct_url.json`. 486 строк совпали с байтами на
  диске по хешу и размеру; 487-я — сам `RECORD`, у него хеша нет.
- Все 482 файла zip побайтно равны установленным; файлов `conductor/`, dist-info и
  `Scripts/conduct.exe`, которых нет в `RECORD`, нет — не считая `.pyc` (см. ниже).
- В `conductor/` 478 файлов, как в отчётах POSIX-дорог CI (`installed_files: 478`).
- После `python -I` импортов в venv появились 189 файлов `__pycache__/*.pyc`: `-I` игнорирует
  `PYTHONDONTWRITEBYTECODE`. В `RECORD` их нет; финальная версия проверки их не считает
  нарушением, а печатает счётчиком.
- **`record_verify.py` менялся между первым и финальным прогоном.** Первый прогон — `logs/02`
  (21:06; stdout в `raw/record-verify.out`, 21:06:43), финальный — `logs/18` (21:16:11); файл
  скрипта записан в 21:16:01. Между ними ослаблено исключение `.pyc` из «файлов вне `RECORD`».
  Первая версия не сохранена, её текст неизвестен. По `logs/02` (строки 541-554) в момент
  первого прогона `.pyc` ещё не было (`*.pyc under conductor/: 0`) и все проверки держались:
  чистая установка до импортов совпала с `RECORD` без исключений.
- Независимо проверено ревью и перепроверено по диску EV при правке отчёта: все 189 `.pyc` —
  `cpython-312`, у каждого есть `.py`, все записаны 21:06:51.2-21:06:51.9, во время `-I`
  импортов (`import-conductor` и `installed_probe`).

## Release smoke: шаги 1-12

Порты 7851 и 7852 вместо 7801 и 7802, `$SMOKE` = `EV\smoke`. Подробный вывод каждого шага —
в `EV\logs`. «Буква» — дословный текст «Expect» документа.

| Шаг | Статус | Что наблюдалось |
| --- | --- | --- |
| 1 Установка | пройден | `pip list`: agent-conductor 0.1.0; wheel один, копия с тем же sha |
| 2 `--help` | пройден | exit 0; 15 подкоманд, набор равен документу (сравнён как набор) |
| 3 Версия | пройден | `0.1.0`; `pyproject.toml` тоже `0.1.0`; `--version` — exit 2 |
| 4 demo | пройден | stdout только URL; stderr три строки; id demo свои (находка 6) |
| 5 Studio, state | пройден | 200 `text/html`, 9145 байт; `web-app blocked`; 3 и 1; handoff |
| 6 Loopback | пройден | один сокет `127.0.0.1`; 192.168.0.32 отказ за 2,1 с |
| 7 Сеть панели | не пройден (буква) | 171 файл; два «абсолютных URL»; находки 1 и 2 |
| 8 init | пройден | exit 0; повтор exit 1; `ownership status` = `legacy` |
| 9 validate, doctor, report, prompt | не пройден (буква) | заголовок report другой, находка 4 |
| 10 `up` и занятый порт | пройден | `ready`; второй `up` exit 1 `bind_failed`; legacy |
| 11 preview и далее | пройден | digest, повтор побайтно тот же, ghost и codex — exit 1 |
| 12 providers | не пройден (буква) | при stdin = NUL нет нужной строки; находка 5 |
| 12 интерактивная часть | проходит человек | нужен живой терминал |

Что стоит за строками, чтобы их не пришлось искать в логах:

- Шаг 4: stderr — `demo fixture materialized in ...conduct-demo-94x_quv0 (throwaway copy)`,
  `demo workflow release-review revision 1, run demo-run-001, gate gate-result is waiting`,
  `serving ... — Ctrl+C to stop`. Запуск `conduct.exe` порождает дерево conduct.exe (launcher)
  → venv `python.exe` → базовый `python.exe` и `conhost.exe`; слушает самый внутренний.
  Оговорка по байтам: проверка во время работы сервера (`logs/05`, строки 12-14) дала `stdout
  bytes: 0  stderr bytes: 0` и `strict UTF-8: NO`, что противоречит выводу выше (строки 5-10
  того же лога). Причина в логе не записана; вероятно, нарушение совместного доступа, пока
  сервер держал файлы (предположение). Вывод шага держится на позднем замере после остановки:
  `logs/08`, строки 119-125 (`demo-out.txt` 24 байта, `demo-err.txt` 277 байт, строгий UTF-8),
  и на замере ревью B: demo-out 24 байта, один CRLF; demo-err 277 байт, ровно три CRLF.
- Шаг 5: `project=web-app state=blocked reason=human_decision`, `findings=3 queue=1`,
  handoff `200 text/markdown; charset=utf-8`, первая строка `# Conduct handoff — claude`;
  `/panel/index.html` — 200, 91 210 байт.
- Шаг 6: `Get-NetTCPConnection` — одна строка `127.0.0.1 7851`; и 192.168.0.32, и второй
  адрес машины 10.72.71.99 отвечают «Невозможно соединиться с удаленным сервером» (не таймаут).
- Шаг 7, harnesses: 12 строк, у 11 `docs` начинается с `https://`, пустой только у `custom`
  (`logs/08`, строки 92-106). Вторая половина ожидания документа — что каждое непустое
  значение называет документацию самого вендора — в прогоне не оценивалась. Оценка по виду
  URL, без сетевой сверки и без проверки владельцев доменов: девять значений похожи на сайты
  документации (`docs.*`, `/docs`, `developers.*`); `qwen-code` →
  `https://github.com/QwenLM/qwen-code` и `deepseek-harness` →
  `https://github.com/deepseek-ai/deepseek-harness` (`src/conductor/harnesses.py:135`, :181) —
  репозитории в организациях самих вендоров. Считать ли README репозитория документацией
  вендора — решает Codex.
  Все вызовы `fetch` и `EventSource` в панели идут на пути, начинающиеся с `/` (проверено по
  исходникам `hub.js` и `desk-transport.js`).
- Шаг 8: bootstrap prompt на stdout начинается с `You are setting up Conduct for this project.`;
  stderr (`raw/step08-init-1.err`, 1408 байт) — не три строки, а три строки и блок после них.
  Первые три: `scaffolded ...`, `template: default-orbit`, `conduct validate: clean — no
  warnings.`. Далее около 20 строк (`logs/10`, строки 47-75): «The map is valid but
  generic…», «Your first action», «Next command» (`conduct validate`) и «Then …» с командами
  `conduct prompt`, `conduct ownership activate`, `conduct providers`, `conduct up`. Документ
  не говорит «только эти строки», расхождения нет; перечень в три строки был неполным.
  Второй запуск — `...\proj\conductor already exists — refusing to touch it`, stdout пуст.
- Шаг 9: `validate` — 0 байт на обоих потоках, exit 0; `doctor` — exit 1, последняя строка
  `not ready: 3 finding(s), 0 unknown, 2 ok.`, у трёх находок `next: conduct ...`; `report`
  содержит `no_lanes_yet`, `## Decision brief`, `## What this report does not know`;
  `prompt` начинается `You hold the "scout" role in this project's Conduct cycle`.
- Шаг 10: `http://127.0.0.1:7852/`, `state` = `ready`, второй `up` — exit 1 за 0,49 с,
  `conduct up: refused bind_failed: cannot serve on 127.0.0.1:7852: [WinError 10048] ...
  To try a different port, rerun with --port PORT.` После `Stop-Process -Force` лаунчера
  процессов проекта нет, порт свободен, `ownership status` по-прежнему `legacy`.
- Шаг 11: `preview` — одна строка JSON, `capability` `dispatch`, `instance_id` `claude-dev`,
  `preview_digest` `sha256:faafda6d...1d445c`, второй запуск байт в байт тот же; `ghost` и
  `--adapter codex` — exit 1, stdout пуст, stderr называет `ghost`, `claude-dev` и `codex`;
  `integration-smoke` — exit 0, `outcome` `verification_failed`, `exit_code` 0, `evidence_refs`
  пуст, повтор побайтно тот же; `reconcile` — exit 0, stderr `no action in this project is
  waiting for reconcile`. После шага 11 `ownership status $PROJ` всё ещё `legacy`.
  Оговорка: документ добавляет, что повторное открытие run ничего не дописывает. Побайтное
  равенство двух выводов доказано (`logs/13`, строки 19 и 57). Что второй запуск ничего не
  дописал, согласуется с mtime `runs/*/records.jsonl` (`preview-run` 21:11:29.107,
  `control-loop-run` 21:11:39.110): они раньше создания raw-файлов вторых запусков
  (21:11:29.226 и 21:11:39.249). Но это не доказано: время старта вторых запусков в логах не
  записано, а время создания raw-файлов — лишь косвенная граница.
- Шаг 12: см. находку 5; `providers.json` нигде не создан.

Дополнительно к шагам, по образцу `wheel_road.http_checks`, на втором экземпляре demo (порт
7851): 166 проверок (159 маршрутов и 7 read-эндпоинтов), пять экранов Studio
(Overview, Workflow, Runs, Decisions, Agents) на месте, а байты каждого из 159 маршрутов
равны и установленному файлу, и записи в zip wheel (`logs/09-demo-http-checks.txt`).

## Дорога Ctrl+C на Windows

Помощник `EV\tools\road_ctrlc.py` повторяет приём `tests/_drain_harness.py`: сервер в скрытой
консоли (`CREATE_NEW_CONSOLE`, `SW_HIDE`), stdin — NUL, stdout и stderr — в файлы; Ctrl+C
доставляет отдельный процесс (`FreeConsole`, `AttachConsole(pid)`,
`SetConsoleCtrlHandler(None, True)`, `GenerateConsoleCtrlEvent(0, 0)`). Проект `EV\road`:
`init --template default-orbit`, `ownership activate --legacy-writers-stopped`, статус
`active`. Порт 7853 до и после каждого срока свободен.

| Что | Срок 1 | Срок 2 |
| --- | --- | --- |
| PID лаунчера `conduct.exe` | 5020 | 25764 |
| `ownership status` до старта | `active` | `closed` |
| URL на stdout | 0,50 с | 0,47 с |
| «serving ... — Ctrl+C to stop» на stderr | 0,52 с | 0,47 с |
| `GET /` | 200, `text/html`, 9145 | 200, `text/html`, 9145 |
| `GET /state.json` | `ready`, `no_lanes_yet` | то же |
| http_checks; равенство zip | 166; 159 | 166; 159 |
| `ownership status` на ходу | `opened` | `opened` |
| от Ctrl+C до выхода | 0,30 с | 0,66 с |
| код выхода | 0 | 0 |
| `ownership status` после | `closed` | `closed` |
| `recovery_required` в выводе | нет | нет |
| оставшиеся процессы; порт | нет; свободен | нет; свободен |

- Контроль: sleeper в своей скрытой консоли (PID 21908) умер от доставленного Ctrl+C с кодом
  `3221225786` = `0xC000013A` за 0,3 с. Без этого контроля остановку нельзя было бы считать.
- Дерево каждого срока по `ParentProcessId`: `conduct.exe` (лаунчер, он же владелец консоли) →
  venv `python.exe` → базовый `python.exe`, рядом `conhost.exe`. Слушает внутренний
  `python.exe`. Ctrl+C доходит до всех и завершает дерево без принудительной остановки
  (`forced_cleanup` не потребовался).
- stdout срока — `http://127.0.0.1:7853/`, stderr — `serving ...\road — Ctrl+C to stop`
  (94 байта); `recovery_required` во втором сроке не было.
- Для сравнения: в отчётах POSIX-дорог CI то же число проверок (166) и выход за 0,56-0,63 с.
- Это имитация Ctrl+C в консоли сервера. Ctrl+C рукой в видимом окне не делался.
- На активированном проекте `Stop-Process`/`taskkill` не применялся ни разу.

## doctor в пути с кириллицей и пробелом

Проект `EV\Проект проверки` (`init --template default-orbit`), PATH: первой записью
`EV\venv\Scripts`, `Get-Command conduct` → `...\venv\Scripts\conduct.exe`.

- `conduct doctor --dir <путь>` — exit 1, `not ready: 3 finding(s), 0 unknown, 2 ok.`
- Печатается голый `conduct`, не путь к exe. Путь в `--dir` печатается в двойных кавычках,
  с кириллицей и пробелом, без закрывающего разделителя. Команд три: `conduct doctor --dir
  "..."` и два раза `conduct prompt --role scout --dir "..."`.
- Каждая команда выполнена дословно в `cmd.exe /d /s /c "<строка>"` и в `powershell.exe
  -NoProfile -NonInteractive -EncodedCommand` (UTF-16LE base64). Результат одинаков:

| Команда | cmd: exit, stdout | PS 5.1: exit, stdout | Сверка |
| --- | --- | --- | --- |
| doctor | 1, 1228 байт | 1, 1228 байт | = вызову с тем же argv без оболочки |
| prompt (1) | 0, 4463 байта | 0, 4463 байта | то же |
| prompt (2) | 0, 4463 байта | 0, 4463 байта | то же |

- Скрипта, которым гонялись напечатанные команды в cmd и PowerShell, в EV нет: точные
  командные строки не записаны, в `logs/17` только итоги (поиск по EV на `EncodedCommand` и
  `cmd.exe` пуст; в `tools\` его нет). Форма запуска из пункта о дословном выполнении выше
  записью не подтверждена. Ревью C воспроизвело независимо: `cmd.exe /d /s /c "<строка>"` и
  `powershell.exe -NoProfile -EncodedCommand` с телом «<строка>\r\nexit $LASTEXITCODE», через
  каналы и в настоящей скрытой консоли (кодовая страница 866): exit 1, байты равны прямому
  вызову.
- Вывод cmd и вывод PowerShell побайтно равны прямому вызову, без нормализации CRLF. У doctor
  это одно и то же sha256 `a225d3016c3a0835af4796d5a35871236e0f1c4dff383075d62f1f15a973931d`
  у `raw/doctor-run.out`, `doctor-cmd-1.out`, `doctor-ps-1.out` (1228 байт, CR=27, LF=27). У
  prompt — `a0cd932fd4d66b21aeaa35f28fd14b157eff43d735036abc25d0d71bd43bc75a` у
  `doctor-base-prompt.out`, `doctor-cmd-2.out`, `doctor-cmd-3.out`, `doctor-ps-2.out`,
  `doctor-ps-3.out` (4463 байта). Заголовок `conduct doctor — C:\...\Проект проверки`
  целый: путь не разрезан, «не распознано» нет.
- В stderr PowerShell только служебный `#< CLIXML ... Preparing modules for first use`,
  от `conduct` в нём ничего нет. Все три команды только читают: проект не изменился.
- Дополнительно: корень, набранный с закрывающим `\`, печатается в командах без него.

## Отклонения от документа

1. Порты 7851 и 7852 вместо 7801 и 7802; `$SMOKE` = `EV\smoke`, не случайный каталог в TEMP.
2. Шаг 1: нет `python` в PATH, venv создан `python.exe -I -m venv` из базового Python;
   установка `--isolated --no-index --no-deps --no-compile` (как `wheel_road.install`),
   а не `pip install <кандидат>`; вместо `$env:PYTHONPATH = ""` убраны четыре переменные.
3. Команды `conduct` запускались через `Start-Process -RedirectStandardOutput/-Error` и
   `WaitForExit` (хелпер `Invoke-Logged`), а не через `&`: так stdout, stderr и exit
   сохраняются раздельно и побайтно. Фрагменты шагов 4, 5, 6, 7 и 10 с `Start-Process`,
   `Invoke-WebRequest`, `Get-NetTCPConnection`, `Stop-Process` выполнены дословно.
4. Шаг 7: первая команда (`$panel = & $PY -c ...`) на этой машине не работает (находка 1);
   вторая попытка с `PYTHONIOENCODING=utf-8` только для этой строки. Записаны обе. Вторая
   сработала лишь потому, что у инструмента `[Console]::OutputEncoding` = 65001 (находка 1).
5. Шаг 12: кроме дословного запуска, добавлены запуски со stdin из пустого файла и из канала
   (находка 5).
6. Второй экземпляр demo для `http_checks` (первый уже остановлен по шагу 7).
7. `PYTHONDONTWRITEBYTECODE=1` осталась от инструмента: в списке из четырёх её нет. Так же
   унаследованы около 33 переменных среды агента (см. «Проверки»).
8. В PowerShell-запуске doctor-команд добавлены `[Console]::OutputEncoding = UTF-8` перед и
   `exit $LASTEXITCODE` после напечатанной строки — только чтобы прочесть вывод и код.
9. Ctrl+C доставлялся помощником, не рукой: так задано заданием.
10. `tools\record_verify.py` изменён между первым (`logs/02`) и финальным (`logs/18`)
    прогоном: ослаблено исключение `.pyc`; первая версия не сохранена (см. «Проверки»).
11. Скрипт запуска напечатанных doctor-команд в cmd и PowerShell в EV не сохранён.

## Находки

Каждое расхождение с «Expect» документа записано как есть; смягчения нет.

1. **Шаг 7, первая команда ломается на кириллическом профиле.** `$panel = & $PY -c
   "import conductor, pathlib; print(pathlib.Path(conductor.__file__).parent / 'panel')"`
   при пустых `PYTHONUTF8` и `PYTHONIOENCODING` печатает путь в канал в ANSI (cp1251):
   `43 3a 5c 55 73 65 72 73 5c cf ee eb fc e7 ...`. PowerShell читает его как UTF-8 (в этом
   инструменте) и получает `C:\Users\������������\...`. Дословно: `Get-ChildItem : Cannot find
   path 'C:\Users������������\Documents\Codex\work\r5w46\venv\Lib\site-packages\conductor\pane
   l' because it does not exist.` и `scanned: 0 files in C:\Users\������������\...\panel`; три
   сканирования пусты. В обычной консоли с OEM 866 те же байты читаются как
   `C:\Users\╧юы№чютрЄхы№\...` (расчёт по байтам, в видимой консоли не воспроизводилось).
   Документ сам предупреждает о малом числе файлов, так что провал не молчит. С
   `PYTHONIOENCODING=utf-8` на первой строке: `scanned: 171 files`, но лишь потому, что у
   инструмента `[Console]::OutputEncoding` = 65001 (`logs/08`, строка 31) и PowerShell прочёл
   UTF-8-байты как UTF-8. В обычной ru-RU консоли владельца (OEM 866) PowerShell прочёл бы те
   же UTF-8-байты как cp866, и путь снова был бы неверным (расчёт, не наблюдение). Значит,
   обхода для владельца эта попытка не показывает. Правка документа должна получать путь
   `panel` без передачи через кодировку консоли. Это дефект текста `release-smoke.md`, он
   бьёт ровно по кириллическому профилю владельца.
2. **Шаг 7, «ровно один абсолютный URL» не держится по букве.** Кроме
   `http://www.w3.org/2000/svg` скан печатает вторую строку
   `https://github\\.com/[A-Za-z0-9][A-Za-z0-9-]{0,38}/`. Это не адрес: это шаблон
   `new RegExp(...)` `PULL_URL` в `desk-accept-host.js:49`, проверяющий URL pull request; ничто
   его не запрашивает. Документ называет любой второй абсолютный URL блокером; по свойству
   («ничего не просит у сети») шаг держится. Остальное: все сетевые вызовы — на пути с `/`;
   `href: h.docs`, `href: row.docs`, `href: row.url` — переменные, не загрузка; в `graph.html`
   `href="graph.css"` и `src="graph.js"` без ведущего `/` (относительные, тот же origin);
   `href="/hub/hub.css"` и `src="/hub/hub.js"` ведут на `/hub/`, не на `/panel/`. Решение —
   блокер это или правка текста документа — за ведущим.
3. **Шаг 5, регулярка из документа печатает пустую строку.** `[regex]::Match($r.Content,
   '<title>[^<]*</title>').Value` ничего не нашла: тег
   `<title id="studioTitle">December — Workflow Studio</title>` несёт атрибут. Свойство
   документа («`December` в `<title>`») верно; устарела регулярка. Классическая панель:
   `<title>December</title>`.
4. **Шаг 9, заголовок report.** Документ: `# Conduct report — your-project`. Факт:
   `# Conduct report — proj`. `init` пишет в `map.toml` имя папки (`project = "proj"`), а не
   шаблонное `your-project` (`project_identity.py`, `templates.UNNAMED`). Остальные
   ожидания шага (`no_lanes_yet`, `## Decision brief`, `## What this report does not know`)
   выполнены. Устарел пример в документе.
5. **Шаг 12, `conduct providers` при stdin = NUL.** Инструмент отдаёт ребёнку NUL
   (`GetFileType` = CHAR, не консоль, Python 3.12 `isatty()` = True). Результат: exit 1, stdout
   пуст, `providers.json` не создан, но stderr — не одна строка, а вступление, список из пяти
   провайдеров, `choice [1]:` и последняя строка: `the input ended before the questions did,
   so nothing was written. Run this again in a terminal you can type into.` Строки `conduct
   providers needs a terminal: ...` нет. Со stdin из пустого файла и из канала (`'' | conduct
   providers`) строка есть: exit 1, stdout пуст, одна строка stderr, как в документе.
   `conduct init` случай NUL разбирает явно (`init.py:399-405`: «`conduct init < NUL`», «no
   input available»), `provider_setup._interactive()` (`provider_setup.py:85-91`) — нет.
   Исход безопасный (ничего не записано), но сообщение не то, которое обещает документ.
   Объём находки (по коду, `provider_setup.py:85-91`): `_interactive()` возвращает `True` и
   для настоящей консоли, поэтому человек, набравший команду шага 12 в своей PowerShell,
   получит мастер — это и задумано абзацем «Run it once by hand». Однострочный отказ «needs a
   terminal» появляется только при stdin из файла или канала. Значит, «Expect» шага 12 верен
   лишь для перенаправленного stdin: это и правка документа, и мелкая несогласованность
   продукта. Вывод по коду, в видимой консоли не запускалось.
6. **Шаг 4, id demo.** Документ приводит `demo-orbit`, `run-demo-001`, `gate-confirm-do`;
   demo печатает `release-review`, `demo-run-001`, `gate-result`. Документ оговаривает, что id
   «свои», поэтому находка только как пометка: пример в документе устарел.
7. **Остатки demo.** После `Stop-Process -Force` лаунчера процессов и порта нет (дерево гибнет
   целиком), но каталоги фикстур остаются: `conduct-demo-94x_quv0` и `conduct-demo-xa8r8h0i` в
   `C:\Users\Пользователь\AppData\Local\Temp`. Документ говорит, что их уничтожит TEMP; сам
   demo при `Stop-Process` их не убирает. Не удалял.
8. **TIME_WAIT.** 166 запросов `http_checks` на сервер оставляют сотни сокетов `TIME_WAIT`:
   321 на 7851 после demo (`logs/09`) и 647 на 7853 после дороги (`logs/16`, 21:14:26).
   Слушателей нет; к финальному снимку (`logs/18`, 21:16:11) `TIME_WAIT` уже не осталось. Для
   справки к разделу «Known gaps» (`ERR_NO_BUFFER_SPACE`): диагнозом это не является.

## Не проверено

- Мастер `conduct init` с настоящим терминалом (три вопроса и строка `template:`).
- `conduct providers` интерактивно: три отказа ввода (`ANTHROPIC_API_KEY=...`, голый токен
  `sk-live-...`, `PYTHONPATH`/`LD_PRELOAD`), по одному harness каждого вида, строка
  `availability available`.
- Ctrl+C рукой в видимом окне (имитация помощником проверена, см. выше).
- Браузер: classic panel и живое обновление, Workflow Studio, `docs/owner-acceptance.md`.
- Настоящие провайдеры, ключи, платные вызовы; opt-in checker probe.
- П. 9 плана (полный core на кириллическом профиле) — не в этой задаче; pytest ядра не
  запускался. Исключение: `tests/test_file_endings.py` (п. 14 таблицы «Проверки»).
- Все `/command/*` кроме read-эндпоинтов из `http_checks`; `conduct tools`, `conduct hub`,
  `conduct projects add`; `ownership recover` и перезагрузка ОС.
- Python 3.11 и CI-job других ОС; финальный зелёный CI №46 (на 17:56 UTC шёл).
- Находка 1 в видимой консоли с OEM 866: расчёт по байтам, не наблюдение.
- Шаг 6: только два адреса машины (192.168.0.32, 10.72.71.99); IPv6 не смотрел.

## Ревью Opus (три линзы, 21.10.2026)

Три независимых проверяющих Opus перепроверили результат дороги: у всех трёх вердикт
`confirmed`. Они нашли места, где отчёт писал не то, что показывают логи; отчёт исправлен, и
каждое исправление сверено с логами EV (замеры самих ревью и ведущего помечены как их замеры).

- **A — происхождение: confirmed.** Wheel = `0a493ad` по blob-ам, нет `.pth` и editable
  установки, лаунчер `conduct.exe` с shebang на venv, `sys.path` только из venv. Внесено по A:
  раскрыто изменение `record_verify.py` между прогонами и перепроверены 189 `.pyc`
  (раздел «Проверки»); строка про zip разделена на доказанное офлайн и взятое из данных Codex,
  добавлена сверка с `ci.yml` и blob-ами; «чистая оболочка» названа частичной (среда агента,
  `PYTHONDONTWRITEBYTECODE`, пакет MSIX).
- **B — ожидания smoke: confirmed.** Вердикты fail шагов 7, 9 и 12 верны по букве документа;
  http-сверка покрыла 159 маршрутов по 159 файлам `panel` и 16 hub-файлов, то есть все 171.
  Внесено по B: шаг 4 — оговорка про нулевую байтовую проверку во время работы сервера и опора
  на поздний замер; шаг 7 — оценка `harnesses.json` (`qwen-code` и `deepseek-harness` ведут на
  репозитории GitHub, решение за Codex); находка 5 — уточнён объём (настоящая консоль даёт
  мастер, отказ только при stdin из файла или канала); находка 1 — обход с
  `PYTHONIOENCODING` держится лишь на кодировке 65001 инструмента, в консоли 866 путь снова
  неверен; шаг 8 — полный состав stderr; шаг 11 — оговорка про «повторное открытие».
- **C — Ctrl+C и doctor: confirmed**, с независимым воспроизведением своим инструментом:
  проект `EV\verify-c`, порт 7859, exit 0 через 0,29 с после Ctrl+C, на диске gen-3 `opened`
  → gen-4 `closed`, кириллица в консоли 866 целая. Записи владения `EV\road` gen-3..gen-6
  подтверждают два срока без recovery (перепроверено по диску: gen-3 `opened` → gen-4
  `closed`, gen-5 `opened` → gen-6 `closed`, `recovered_session` = null, сессии разные).
  Внесено по C: финальный снимок — `TIME_WAIT` только в `logs/16`, в `logs/18` «(none)»;
  doctor — скрипта запуска команд в EV нет, независимое воспроизведение ревью C описано;
  вывод PowerShell побайтно равен прямому вызову (не «после нормализации CRLF»).

## Ревью Codex

Статус: ожидает. Заполняется после независимого чтения отчёта и перепроверки `EV`.

## Передача

- Итоговый commit: нет, по заданию. `git status` до и после: только ` M docs/recovery/
  2026-10-20/R5-REHEARSAL-RUNBOOK.md` (Codex) и этот новый файл отчёта.
- EV: `C:\Users\Пользователь\Documents\Codex\work\r5w46\`. Внутри:
  - `vars.ps1` и `tools\` (`lib.ps1`, `record_verify.py`, `http_checks.py`, `road_ctrlc.py`,
    `zip_peek.py`, `stdin_probe.py`) — почти всё, чем прогонялось. Нет скрипта запуска
    doctor-команд в cmd и PowerShell, а `record_verify.py` лежит в финальной версии (первая
    не сохранена);
  - `logs\00`-`18` и `16-road-report.json` — вывод каждого шага (stdout, stderr, exit);
  - `raw\` — сырые байты stdout и stderr каждой команды (128 файлов);
  - `wheel\` — копия wheel (sha256 сверен); `venv\` — установка, не удалена;
  - `smoke\` — `$SMOKE`: `proj`, `demo-*`, `up-*`; `road\` — активированный проект, `closed`;
  - `Проект проверки\` — проект для doctor; `roadrun\` — логи серверов дороги;
  - `verify-c\` — проект независимого воспроизведения ревью C (порт 7859);
  - `scratch\` — служебные pid и пустой файл stdin.
- Оставлено: `venv` и все проекты, чтобы их перепроверили независимые проверяющие. Процессов
  нет (в списке `python*`/`conduct*` только чужой `-m laboratory`). В финальном снимке
  (`logs/18`, 21:16:11) на 7851-7853 и 7859 нет ни слушателей, ни `TIME_WAIT` («(none)»);
  `TIME_WAIT` был раньше, ×321 в `logs/09` и ×647 в `logs/16`. `%USERPROFILE%\.december-command`
  отсутствует, `%LOCALAPPDATA%\DecemberCommand` и `%USERPROFILE%\DecemberRehearsal` не
  трогал и не смотрел. В TEMP остались два каталога `conduct-demo-*` (находка 7), в профиле —
  `pt-rw1`.
- Для перепроверки: `. EV\vars.ps1`, затем `& $PY -I EV\tools\record_verify.py $VENV $WHEEL`
  (в `venv` лежат `__pycache__` от `-I` импортов, их надо игнорировать). Дорогу можно
  повторить на `road` (состояние `closed`), указав новые `--work` и `--report`.
- Следующий конкретный шаг: ведущий решает по находкам 2 и 5 (блокер или правка документа и
  продукта) и по находкам 1, 3, 4, 6 (правка `release-smoke.md`); ручные пункты из раздела
  «Не проверено» проходит человек.
