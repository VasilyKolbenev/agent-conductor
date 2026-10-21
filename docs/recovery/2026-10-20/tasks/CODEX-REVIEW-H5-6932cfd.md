# Codex: независимое ревью H5-V1 и разбор CI #43

Дата: 21 октября 2026, 15:30 МСК. Ветка `recovery/2026-10-20`.
Проверенный HEAD: `6932cfd01b839b89c31f0da81be674abc1553ffe`.
H5: код `cc69cd85d141780d86814427e98a0ccbcf0e456c`, документы `bd6e600`.
До и после проверок HEAD совпал. До записи этого отчёта единственный untracked-файл —
`R4-V1-DESIGN.md`, работа Claude; он не изменялся.

## Вердикт и границы

Новых блокирующих замечаний в изменении H5-V1 не найдено. Проверка относится к решению,
записанному в `OPEN-DECISIONS.md` и коммите `edd79d1`: в V1 задачи только по API-ключу,
подписочный режим внутри изоляции отказывает; схема B после V1. Прежняя рекомендация Codex
включить подписки в V1 не подменяет последующее записанное решение владельца.

Это ревью H5, а не приёмка V1 целиком. R4-V1 в работе, окончательный SHA и wheel ещё не
выбраны. Полный локальный suite, полный browser gate, настоящие vendor CLI и Windows road
из CI-wheel в этом ревью не запускались. Мутационные эксперименты Opus не повторялись.

## Что проверено чтением кода

- `_login_road_covered()` сохраняет закрытый подписочный путь и не зависит от
  `LOGIN_LOAN_OPEN`. Дверь плана и транспорт используют общий `_road_covers()`.
- Dispatch, review и checker отказывают до запуска; проверка перед `_attempt()` сохраняет
  отказ до создания home и получения login lease. Production `resolve_providers()` по
  умолчанию включает confinement для платформы хоста.
- Квитанция называет подписку только когда доступна платформенная граница и допустима
  установка harness. Иначе сохраняется общий отказ: подписка не выдаётся за единственную
  причину, если не выполнены и другие условия.
- Слово `subscription` в квитанции допустимо: это режим конфигурации, без пути, аккаунта
  или credential. H5-C, вопрос о тексте отказа: со стороны Codex замечаний нет.
- Отдельное поле `reason` для этого изменения не требуется. Существующий `detail.sandbox`
  позволяет мастеру показать пояснение; замороженный конверт API не меняется. S-H5-D2 можно
  оставить вне V1, если приёмка не выявит отдельной потребности.
- Новый тестовый модуль уже добавлен в `CAPPED`; указание в первоначальном отчёте добавить
  его не является оставшейся работой.

## Независимые проверки

Windows, Python 3.12.14 из `.venv`, bundled Node/Git, `PYTHONUTF8=1`,
`PYTHONIOENCODING=utf-8`. Никаких аккаунтов, ключей или платных вызовов.

1. `tests/test_subscription_road_boundary.py`: **44 passed**, 37.83 s.
   Команда: `.venv\Scripts\python.exe -m pytest -q tests/test_subscription_road_boundary.py`
   с отдельным `--basetemp` в `Documents\Codex\work\h5-codex-review-20261021`.
   Одно предупреждение о невозможности записи `.pytest_cache/nodeids`; тесты прошли.
   Вывод сохранён в истории инструментов ревью; отдельного JUnit у этого прогона нет.
2. Один прогон пяти файлов: **271 passed**, 4.16 s:
   `test_provider_setup_login.py`, `test_studio_agents_i18n.py`,
   `test_desk_wizard_prepare.py`, `test_command_line_cap.py`,
   `test_command_materials_compose.py` из `tests/`.
   Команда: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider` с этими файлами,
   отдельным `--basetemp` `Documents\Codex\work\ch5-model-1` и `--junitxml`.
3. Chromium: `browser_tests/test_desk_wizard_prepare.py`
   с `-k 'boundary or refusal_stops'`: **4 passed, 40 deselected**, 5.17 s.
   Те же `-q -p no:cacheprovider`, отдельный `--basetemp`
   `Documents\Codex\work\ch5-browser-1` и `--junitxml`.

Прогоны 2–3 запускались после dot-source `outputs/December-Command-Environment.ps1 -Quiet`.
Итого 319 успешных проверок. Это разные ограниченные наборы, а не полный gate.

Локальные свидетельства вне репозитория, рядом с рабочей копией:

- [JUnit моделей и CLI](../../../../../Codex-H5-review/model-tests.xml)
- [JUnit Chromium](../../../../../Codex-H5-review/browser-tests.xml)
- [Снимок CI](../../../../../Codex-H5-review/CI/ci43-ci44-snapshot.json)
- [Фрагмент падения CI #43](../../../../../Codex-H5-review/CI/ci43-windows-py312-failure.txt)

Эти относительные ссылки относятся к восстановленному workspace; сами XML и логи не входят
в Git. В репозитории остаётся этот отчёт с результатами и публичными ссылками на CI.

## CI: точные результаты вместо предположения о нестабильности

Данные получены через GitHub-коннектор, вход владельца в браузере не потребовался.
Снимок — 21.10.2026, 15:28:03 МСК.

- CI #42 на `ff0ce19fc2ead13040886367100f3159d62bb69d` завершён успешно:
  https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39485630011
- CI #43 на `04641ca32ac30b853277a2f41093167b2b0da964`: 11 из 12 job успешны.
  Единственное падение — Windows Python 3.12, job `119105185449`:
  https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39565042944/job/119105185449
- Тест: `tests/test_command_materials_compose.py` →
  `test_the_desks_line_for_a_link_is_the_composers_whatever_backticks_the_path_holds`,
  параметр ``docs/a`b.md``. Ошибка `subprocess.TimeoutExpired`:
  `node --input-type=module` не завершил обмен по pipe за 30 секунд.
  Место: `tests/desk_wizard_node.py:77–78`. Итог job:
  **1 failed, 17520 passed, 338 skipped, 1 warning**.
- Это не прежний Ctrl+C exit -2 и не Chromium 10055. Имя с обратной кавычкой само по себе
  не доказывает ошибку quoting: helper передаёт скрипт через stdin, данные через JSON,
  без shell. Первопричина таймаута по имеющимся данным не установлена.
- В нашем прогоне весь `test_command_materials_compose.py`, включая упавший случай,
  прошёл. Ни этот проход, ни пять проходов другого набора не объясняют падение CI.
- CI #44 на `bd6e60069c821e3c82217e9ab1732fe093edd86b` ещё идёт: 4 job успешны,
  8 работают. Успешны Ubuntu Python 3.11, сборка wheel, road Ubuntu и macOS:
  https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39597140707

Следующий шаг по #43: диагностировать точный Node-вызов и его завершение на Windows,
сохраняя длительность, stdout/stderr и сведения о процессе при таймауте. Не увеличивать
timeout вслепую и не объявлять ошибку объяснённой после зелёного повтора.

## Поправки к переданному статусу и продолжение

1. «API-ключ работает у всех пяти harness» сильнее доказательств. Корректно: адаптеры
   допускают API-режим всех пяти; тесты H5 используют recording fake, контрольные runtime
   проверки review/checker не заменяют vendor CLI в AppContainer. Документы прямо говорят,
   что настоящие API-запуски Kimi/Grok не проверены (`first-run-v1.md:134–135`).
2. Браузерный вход владельца не единственный путь к CI-wheel. Коннектор читает логи и
   metadata `candidate-wheel`; получение через Codex уже предусмотрено в R5-PLAN.
   В #44 существует artifact `12344486262` (не истёк). Он не скачивался и не устанавливался
   в этом ревью. Digest архива нельзя выдавать за SHA256 файла `.whl`.
3. В `H5-V1-REPORT.md`, `OPEN-DECISIONS.md` и R5-PLAN остаются исторические фразы
   «не закоммичено», «ревью ожидает», «добавить CAPPED». При синхронизации статусов нужно
   сослаться на `cc69cd8`, `bd6e600` и этот отчёт, сохранив историю отдельных прогонов.
4. Проверка команд перевода: 10/10 блоков `owner-acceptance` EN/RU совпадают;
   14/14 блоков `first-run` совпадают кроме перевода плейсхолдеров.
   Блокирующих расхождений в рассмотренных установочных шагах не найдено.
5. После завершения R4-V1 выбрать окончательный SHA и зелёный CI на нём. Скачать именно
   его `candidate-wheel`, сверить SHA256 файла с build job и обоими POSIX road; затем
   Windows smoke/installed road, developer rehearsal Claude/Codex и приёмка владельцем.
   Wheel #44 не доказывает ещё не вошедший в него R4-V1.

Код продукта, существующие отчёты и файлы Claude не менялись. Создан только этот отчёт;
коммит и push не выполнялись. Ревью остальных незакрытых задач этим документом не заменяется.
