# R5: предварительная developer rehearsal на ноутбуке владельца — runbook

21.10.2026, Claude Code / Opus 5.5; сверено с кодом на `24f9be0` (`e904910`, `0a493ad` процитированных
файлов не меняют). Передача Codex 21.10: выбранная сборка
`0a493ad8a9962cc6e442b9d9e3c8ca104c5a1096`, CI №46 (run `39645262035`), artifact
`candidate-wheel` `12367660793`. Wheel скачан; SHA256 совпал со значением build job,
переданным обоим POSIX road, и с их успешными отчётами. Полный CI на момент передачи ещё идёт.
Проход **предварительный** (решение владельца
21.10, `CONTINUATION-PLAN.md`); финальная приёмка — повтор §2–§5 на финальном CI-wheel. Проверено 21.10:
в чистой PowerShell 5.1 со старым wheel `4d0e3af` — venv, `pip --no-index`, путь `conductor`, пакет и
`unittest`, git без identity, ввод без эха; на dev-`.venv` — мастер `providers` на активированном проекте
(ответы подставлены скриптом). Настоящие CLI, ключи и `up` не запускались.

Ревью Codex 21.10: правка шага 7 EN/RU (`48fdde3`) и практические инструкции этого runbook
приняты, новых блокеров в проверенном объёме нет. Базовые правки R1.6 (`e904910`) и R4 O2/G8
(`0a493ad`) подтверждены чтением diff и отдельными целевыми прогонами: 13 тестов Node
(30 deselected) и 24 теста unknown/signer, всего **37 passed** на Windows/Python 3.12.14.
Это не полный gate и не настоящий запуск провайдеров. Полный CI-снимок и происхождение wheel —
в `outputs/R5-candidate-0a493ad/ci-snapshot.json` и `provenance.json`, рядом с рабочей копией.

## 0. Правила

1. Два окна **обычной** Windows PowerShell (не `Open-December-Command.cmd`, не скрипт окружения):
   **А** — команды, **Б** — только сервер. Ключи вводит владелец, только в окне Б (§1.3).
   Окна открывать из меню «Пуск», **не** из терминала внутри приложения Claude или Codex, и там же
   ставить harness (§1.2). Причина измерена 21.10: дочерние процессы приложения Claude пишут в
   `%LOCALAPPDATA%` через виртуализацию MSIX. `python -m venv` в `%LOCALAPPDATA%\DecemberCommand\rh-0a493ad`
   из него лёг в `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\DecemberCommand\…`
   (venv сам сообщил «Actual environment location may have moved»), и обычное окно его не видит.
   `%TEMP%` и `%USERPROFILE%` (проект, `.december-command`) не перенаправляются.
2. Сервер останавливать только Ctrl+C в окне Б после строки `serving … — Ctrl+C to stop`.
   `Stop-Process` запрещён: проект останется `opened` до полной перезагрузки ОС (T1).
3. Push/PR и публикации Desk не использовать; в исходный пакет — только ручное копирование (§4.6).
   Пути без `$`, обратной кавычки и `%` (N3-D3): все пути ниже собраны из `$env:`.

## 1. Что подготовить владельцу

**1.0. Переменные окна А** (повторять в каждом новом окне А). В PATH нет Python, `py`, git, node/npm
(проверено 21.10): `$BASEPY` (3.12.14) и `$GIT` — из набора Codex, он может исчезнуть (`LOCAL-SETUP.md`);
свой Python 3.11+ — `$BASEPY = '<путь к python.exe>'`.
```powershell
$env:PYTHONPATH = ''
$BASEPY = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$APP = Join-Path $env:LOCALAPPDATA 'DecemberCommand\rh-0a493ad'
$PY = Join-Path $APP 'Scripts\python.exe'
$CONDUCT = Join-Path $APP 'Scripts\conduct.exe'
$P = Join-Path $env:USERPROFILE 'DecemberRehearsal'
$H = Join-Path $env:LOCALAPPDATA 'DecemberCommand\harnesses'
$CLAUDE = Join-Path $H 'claude-code\2.1.239\claude.exe'
$CODEX = Join-Path $H 'codex\0.112.0\node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\codex\codex.exe'
$GIT = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe'
```

**1.2. Harness.** Штатный исполняемый файл (не `.cmd`/PowerShell-обёртка) ровно закреплённой версии в
`<путь>\harnesses\<имя>\<версия>\` (`harness_attempt.py:70-93`); не в `Program Files`/`Windows`, не в
проекте, не сам профиль (`process_loans.py:220-237`); иначе граница не предоставляется. Источник
установки в репозитории не записан — по официальной инструкции вендора.
- **Claude Code 2.1.239**: нативный бинарник, один файл (`claude_code.py:103-104`), прямо в папке версии
  (раскладка 14.10, `tests/_fakeboundary.py:37-48`); документация: https://docs.claude.com/en/docs/claude-code.
- **Codex 0.112.0**: нативный `codex.exe` npm-пакета `@openai/codex@0.112.0`, раскладка как `$CODEX`
  (`codex_cli.py:8-10`, `_fakeboundary.py:43-44`); допустим бинарник архива релиза той же версии прямо в
  `$H\codex\0.112.0\` (`codex_cli.py:517-522`; исправить `$CODEX`); https://developers.openai.com/codex/.
```powershell
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $CLAUDE), (Join-Path $H 'codex\0.112.0') | Out-Null
$env:DISABLE_AUTOUPDATER = '1'
& $CLAUDE --version
& $CODEX --version
```
Ожидается ровно `2.1.239 (Claude Code)` и `codex-cli 0.112.0` (`claude_code.py:384-385`,
`codex_cli.py:466`). Форма Claude описана вендором, локально не наблюдалась: иная печать — блокер,
записать дословно; пин не ослаблять.

**1.3. Ключи** `ANTHROPIC_API_KEY` (в `--bare` Claude Code читает только его) и `OPENAI_API_KEY`. В
конфигурацию идут только имена (`env_allow`); значения сервер копирует из своего окружения при старте
`up` (`process.py:470`). Поэтому в окне Б **до** `up`:
```powershell
$env:ANTHROPIC_API_KEY = (New-Object System.Net.NetworkCredential('', (Read-Host 'ANTHROPIC_API_KEY' -AsSecureString))).Password
$env:OPENAI_API_KEY = (New-Object System.Net.NetworkCredential('', (Read-Host 'OPENAI_API_KEY' -AsSecureString))).Password
'ANTHROPIC_API_KEY', 'OPENAI_API_KEY' | ForEach-Object { '{0}: {1}' -f $_, [bool][Environment]::GetEnvironmentVariable($_) }
```
Ввод без эха и вне истории; ожидается `True` дважды; ключи исчезают с окном Б. Альтернатива
(`first-run-v1.md`) — переменные пользователя в окне «Переменные среды»; после прохода удалить.

**1.4. Бюджет.** Действие — вызов исполнителя; проверка Codex — отдельный платный вызов, не действие.
`dalio-v5`: чистый проход 5 действий (4 шага планирования Claude + `do`), с коррекцией 6
(`templates/README.md:94-115`). Лимит Policy — **6** на запуск (сервер допускает 8, `http_api.py:91-95`).
Основной + контроль: ≤ **12 действий**, ≤ **16 платных вызовов** (≤ 12 Claude, ≤ 4 Codex). Денег продукт
не ограничивает. Бюджет подтверждён владельцем в чате 21.10.2026.

## 2. Wheel в чистый venv (окно А)

Codex уже распаковал wheel из artifact `12367660793` в `outputs\R5-candidate-0a493ad`.
Рядом лежат `SHA256SUMS.txt`, `provenance.json` и оба отчёта POSIX road. SHA256 ниже относится
к файлу `.whl`, не к zip. Его совпадение с build output проверено по аргументу `--sha256`,
который CI передал обоим road из `needs.wheel.outputs.sha256`.
```powershell
$wheel = Join-Path $env:USERPROFILE 'Documents\Codex\2026-10-20\new-chat\outputs\R5-candidate-0a493ad\agent_conductor-0.1.0-py3-none-any.whl'
$expected = '90c0da18af8e254d5b455faebcd27e26aebe75a01e1bec16ef306ed4891ec3f8'
(Get-FileHash -Algorithm SHA256 -LiteralPath $wheel).Hash.ToLower() -eq $expected.ToLower()
Test-Path -LiteralPath $APP
& $BASEPY -m venv $APP
& $PY -m pip install --no-index --disable-pip-version-check $wheel
& $PY -m pip show agent-conductor
& $PY -I -c "import conductor, sys; print(conductor.__file__); print(sys.prefix)"
& $CONDUCT --help
```
Ожидается: `True`; `False`; `Successfully installed agent-conductor-0.1.0`; `Location:
…\rh-0a493ad\Lib\site-packages` без `Editable project location`; `conductor\__init__.py` там же;
15 подкоманд, среди них `init`, `ownership`, `providers`, `up`.

## 3. Проект репетиции (окно А)

**3.1. Исходный пакет** в `%USERPROFILE%\DecemberRehearsal` (39 символов, предел 82; отдельно от
`DecemberTrial`): явно обозначенный дефект, снимок в git-индексе без коммита. Папка должна быть новой.
```powershell
Test-Path -LiteralPath $P
New-Item -ItemType Directory -Path (Join-Path $P 'runstats'), (Join-Path $P 'tests') | Out-Null
Set-Content -LiteralPath (Join-Path $P 'runstats\__init__.py') -Encoding ascii -Value @'
from .counts import count_succeeded
'@
Set-Content -LiteralPath (Join-Path $P 'runstats\counts.py') -Encoding ascii -Value @'
def count_succeeded(rows):
    """KNOWN DEFECT, fixed in the rehearsal: every row is counted."""
    return len(rows)
'@
Set-Content -LiteralPath (Join-Path $P 'tests\test_counts.py') -Encoding ascii -Value @'
import unittest
from runstats import count_succeeded

class CountSucceededTest(unittest.TestCase):
    def test_empty_input_is_zero(self):
        self.assertEqual(count_succeeded([]), 0)
'@
Push-Location -LiteralPath $P; & $PY -B -m unittest discover -s tests -v; Pop-Location
& $GIT -C $P init -q
& $GIT -C $P add runstats tests
& $GIT -C $P status --short
```
Ожидается: `False`; `Ran 1 test … OK`; три строки `A`. Предупреждения git о LF/CRLF — норма.

**3.2. init и активация:** `& $CONDUCT init --template default-orbit --dir $P`, затем
`& $CONDUCT ownership activate --legacy-writers-stopped --dir $P`,
`& $CONDUCT ownership status --dir $P` → `active`.

**3.3. Провайдеры — при остановленном сервере**: при работающем `up` мастер отказывает до вопросов с
`owner_busy` (измерено 21.10, `ownership_cli.py:9-26`). Напечатать пути: `$CLAUDE; $CODEX`. Затем
дважды `& $CONDUCT providers --dir $P`:

| Вопрос мастера | Claude Code | Codex |
| --- | --- | --- |
| `choice [1]:` | `1` | `2` |
| `Absolute path to the … executable:` | значение `$CLAUDE` | значение `$CODEX` |
| `How does … sign in?` | `2` | `2` |
| `Environment variable NAMES …` | `SYSTEMROOT WINDIR PATH TEMP TMP ANTHROPIC_API_KEY` | `SYSTEMROOT WINDIR PATH TEMP TMP OPENAI_API_KEY` |
| `Write it? [y/N]:` | `y` | `y` |

Сводка: `login api_key`, `availability available`; основа имён — `first-run-v1.md` §3. Имена только
**прописными**: имя ищется точно в `dict(os.environ)` (`environment_values.py:29-31`; измерено: `SYSTEMROOT` есть, `SystemRoot` нет).

**3.4. Сервер (окно Б):** `$env:PYTHONPATH = ''`, три строки ключей §1.3, затем
```powershell
$CONDUCT = Join-Path $env:LOCALAPPDATA 'DecemberCommand\rh-0a493ad\Scripts\conduct.exe'
$P = Join-Path $env:USERPROFILE 'DecemberRehearsal'
& $CONDUCT up --dir $P --port 7801
```
Дождаться `http://127.0.0.1:7801/` и `serving … — Ctrl+C to stop`. Окно А:
`Start-Process 'http://127.0.0.1:7801/'`; `& $CONDUCT ownership status --dir $P` → `opened`.

**3.5. Изоляция до первого платного вызова.** Граница есть только при трёх фактах: Windows, API-ключ,
файл под `harnesses\<имя>\<версия>`; положительного индикатора нет, смотреть на отсутствие отказов.
«Участники»: оба `available`, «Настроено чтение ключа из окружения.», текста о подписке нет (квот на
API-ключе нет — норма, `subscription_quota.py:159-160`). Открытие запуска — без `step '…' demands sandbox
route 'execution-boundary' that this build does not provide`; предпросмотр Policy — без `automation
cannot provide a required sandbox`; инспектор `do`: `sandbox: project-root`, проверяющий `role-checker`.

## 4. Задача `count_succeeded`: исполняет Claude, проверяет Codex

**4.1. Процесс и запуск.** «Процесс» → «Создать новый процесс» → «Стандартный цикл» (`dalio-v5`) →
«Проверить» → «Опубликовать версию». «Запуски» → «Новая задача» `R5 count_succeeded` → «Создать задачу»
→ «Создать новый запуск»: «ID запуска» и «ID цикла» `r5-main`; версия 1; «Автоматически в заданных
пределах» (Studio добавит `automation_contract`, `studio-taskflow.js:129`); `role-thinker`,
`role-diagnostician`, `role-designer`, `role-implementer` → `claude-code`; `role-checker` → `codex`;
модель пустая (по умолчанию harness) или полный ID по выбору владельца (алиасы `sonnet`/`opus`/`haiku`/
`fable` отклоняются, `claude_code.py:352`) → «Создать запуск».

**4.2. Документы** («Опубликовать документ», до предпросмотра). `artifact-brief`:
```text
R5. Исправить count_succeeded(rows) в пакете runstats и покрыть её тестами unittest.
Считать только словари, у которых значение ключа "outcome" в точности равно строке "succeeded".
Не считать: "failed", "unknown", "verification_failed", другие значения, отсутствие ключа "outcome",
запись {"plan": "complete"}, "Succeeded", "succeeded ". Пустой список даёт 0; rows не изменяется.
Текущий runstats/counts.py содержит явно обозначенный дефект: return len(rows).
Только стандартная библиотека Python, без сети и новых зависимостей.
```
`instruction-plan` — текст ниже, затем код из буфера (окно А):
`& { foreach ($f in 'runstats\__init__.py', 'runstats\counts.py', 'tests\test_counts.py') { "--- $f ---"; Get-Content -LiteralPath (Join-Path $P $f) } } | Set-Clipboard`
```text
Работай только в текущей рабочей папке. Создай ровно три файла: runstats/__init__.py (без изменений),
runstats/counts.py (исправленный), tests/test_counts.py (unittest). Других файлов не создавай,
пакеты не устанавливай, к сети не обращайся.
КРИТЕРИИ ПРИЁМКИ (по ним судит независимый проверяющий):
1. count_succeeded(rows) возвращает число словарей в rows, у которых "outcome" == "succeeded" в точности.
2. Не считаются: "failed", "unknown", "verification_failed", другие значения, отсутствие ключа,
   {"plan": "complete"}, "Succeeded", "succeeded ".
3. count_succeeded([]) == 0; rows не изменяется.
4. tests/test_counts.py проверяет пункты 1-3 и проходит: python -m unittest discover -s tests
5. runstats/__init__.py совпадает с текущим.
ТЕКУЩИЙ КОД:
```
**4.3. Разрешение Policy.** «Просмотреть границы запуска»: прочитать факты провайдеров (имена переменных,
модель, пределы); «Максимум действий за весь запуск» = `6`, остальное как предложено (шаг 1800 с, `do` с
проверяющим резервирует 2 × 1800 с, `plan_budget.py:75-82`); «Ваше имя» → «Разрешить ограниченный запуск».

**4.4. Ход.** `goal` → `identify` → `diagnose` → `design` идут сами. «Решения»: `gate-confirm-do` —
прочитать `artifact-plan`, `approve`. Затем `do` и проверка Codex. Отказ → одна коррекция в том же
разрешении и новая проверка; второй отказ останавливает запуск без `succeeded`.

**4.5. Ревью до ворот результата** (окно А; файлы читать до запуска тестов):
```powershell
Get-ChildItem -LiteralPath (Join-Path $P 'work') -Recurse -Filter counts.py | Select-Object -ExpandProperty FullName
$W = '<папка work-001 этого запуска: путь выше без \runstats\counts.py>'
Get-Content -LiteralPath (Join-Path $W 'runstats\counts.py')
Get-Content -LiteralPath (Join-Path $W 'tests\test_counts.py')
Push-Location -LiteralPath $W; & $PY -B -m unittest discover -s tests -v; Pop-Location
& $GIT -C $P diff --exit-code -- runstats tests; "original unchanged: exit=$LASTEXITCODE"
```
Копия — `$P\work\_tasks\<id задачи>\work-001` (`work_layout.py:19-28`); `-B` не пишет `__pycache__`.
Ожидается: тесты покрывают пункты 1–3 и проходят; `exit=0`. В «Запусках»: лента `action_request →
effect_lease → execution_observed → action_result`, вердикт Codex, доказательство с экземпляром
проверяющего и digest. Затем ворота результата `approve` → «План: завершён» (метка нейтральная).

**4.6. Явное принятие** — отдельное решение владельца после 4.5:
```powershell
Copy-Item -LiteralPath (Join-Path $W 'runstats\counts.py') -Destination (Join-Path $P 'runstats\counts.py')
Copy-Item -LiteralPath (Join-Path $W 'tests\test_counts.py') -Destination (Join-Path $P 'tests\test_counts.py')
Push-Location -LiteralPath $P; & $PY -B -m unittest discover -s tests -v; Pop-Location
& $GIT -C $P diff --stat -- runstats tests
```
Ожидается: тесты проходят; в diff только `counts.py` и `test_counts.py`.

**4.7. Перезапуск.** Перезагрузить страницу; Ctrl+C в окне Б; окно А: `ownership status` → `closed`;
окно Б: снова `up` (§3.4). Версия, решения, атрибуция проверяющего, доказательства на месте; новой проверки нет.

**4.8. Отрицательный контроль** — только если первая проверка основного запуска `accept` (`owner-acceptance.md`,
real-result); способ получить неверный результат документы не описывают, ниже — предложение Opus. Новая задача
`R5-NC заведомо неверный результат`, запуск `r5-nc` той же версии, те же роли, Policy, лимит 6; `artifact-brief`
тот же; `instruction-plan` — тот же с абзацем в начале:
```text
NEGATIVE CONTROL R5-NC (помеченный контрольный прогон; результат не применяется).
Если в задании НЕТ замечаний проверяющего (первая попытка): создай три файла ровно как в разделе
ТЕКУЩИЙ КОД, ничего не исправляя и не добавляя тестов. Если замечания ЕСТЬ (коррекция): выполни
задание по КРИТЕРИЯМ ПРИЁМКИ. Проверяющий судит только по КРИТЕРИЯМ ПРИЁМКИ.
```
Ожидается: первая проверка `reject` с типизированными замечаниями, коррекция, вторая проверка —
записать. Результат NC не копировать; `git diff --stat` как после 4.6. Если код исправлен сразу, NC не
получен — отклонение; запасной путь — opt-in probe настоящего checker (`release-smoke.md`, разработчик,
checkout `0a493ad`, 2 вызова Codex); NC в продукте он не заменяет.

**4.9. Завершение.** Ctrl+C в окне Б; окно А: `ownership status` → `closed`; закрыть окно Б.

## 5. Что записать (`tasks/R5-REHEARSAL-REPORT.md`; без ключей и сырого вывода проверяющего)

| Поле | Значение |
| --- | --- |
| Дата, время; кто вёл; кто отвечал на ворота | |
| SHA / CI run / artifact; имя wheel; sha256 измеренный = из job `wheel` | |
| `$BASEPY` и версия; `conductor.__file__`; пути и `--version` Claude Code и Codex | |
| `env_allow` (имена), `login`, `availability` обоих провайдеров | |
| Run id основного и NC; версия; роли → harness; модели | |
| Условия разрешения; израсходовано действий («Зарезервировано … осталось …») | |
| Проверки: №, экземпляр проверяющего, слово вердикта, digest, число замечаний | |
| Результат: путь `work-001`, sha256 файлов; `unittest` в копии и в исходнике | |
| `git diff --exit-code` до принятия; `git diff --stat` после | |
| R-N1: артефакты планирования с кириллицей читаются; вердикт не `no_verdict` | |
| Что видел владелец; где понадобился разработчик; отклонения, тексты отказов; итог `ownership status` | |

**Полезный результат принят**, если одновременно: Claude выполнил `do` в границе; Codex как другой
участник проверил именно этот результат (`accept`, digest); владелец прочитал файлы, тесты прошли в
копии; исходник до принятия не изменён (`exit=0`); принятие явное, тесты прошли в исходнике; перезапуск
сохранил состояние без второй проверки; при чистом проходе NC дал `reject` без `succeeded`; ≤ 6
действий на запуск; без `Stop-Process`; в конце `closed`. Приёмку V1 этот проход не закрывает.

## 6. Известные ограничения предварительного прохода

- **O2/G8 входит в этот wheel** (`0a493ad`): неоднозначный ответ оставляет push/PR в `unknown`
  с проверкой результата. Сам runbook push/PR не упражняет.
- **R1.2c-В4**: законченный запуск без разрешения читается `unconfigured/authorization_required`, Studio рисует
  форму границ, «Разрешить» → 422 (`tasks/R1.2c-V4-TASK.md`); не нажимать, записать.
- **R1.5, раннее окно**: Ctrl+C в ~1 мс до печати URL минует drain (`tasks/R1.5-REPORT.md`) — ждать `serving …`.
- **10055**: разовый `ERR_NO_BUFFER_SPACE` даёт пустую Studio до перезагрузки страницы (`R1.3-WIN-10055-CI41.md` §8).
- **macOS SSE** (CI №44) к Windows-проходу не относится. **N3-D3**: `$`, обратная кавычка, `%VAR%` — см. §0.
- **Первый живой проход через границу**: по документам Claude Code/Codex с API-ключом в границе не запускались
  (`release-notes-v1-alpha.ru.md`); вывод vendor CLI в квитанцию не попадает; `env_allow` не расширять без разработчика.
- **R1.6 P2** исправлен в `e904910` (тест); R1.2c-A1, R1.2-W, R3.1-Q1–Q3 — принятые решения, не находки.
