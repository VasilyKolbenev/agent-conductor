Итог: локально проверено | 19956c8 | 640+4 passed/codec; live 4/4 | Do 0 | решение владельца.

# GROK-SOURCE-ROLLOUT: установка и новый запуск до Do

Исполнитель: Codex. Независимое чтение live evidence: делегированный агент Codex.
Код продукта: 19956c85ae82eade3ce63fd6483941c8be54c0ce, ветка recovery/2026-10-20.
TASK с делегированием запуска: 7889c7f. Нового продуктового поведения задача не добавляет.
Kit: `C:/Users/Пользователь/Documents/Codex/work/grok-source-rollout-1111/`.

Измерено на snapshot `20261111T134624119308Z`: Studio нового продукта работает,
новый run разрешён codex-test по делегированию владельца и выполнил четыре review шага.
Состояние `waiting / plan_waiting`, active action отсутствует, spent actions 4,
remaining actions 1. Do requests 0; решений gate и финальной приёмки нет.

## Изменения

Из точного Git commit собран wheel версии 0.1.0 без скачивания зависимостей.
В чистом окружении проверены RECORD, entrypoint/direct_url, CLI help и 541 package files.
Установлен тот же проверенный wheel в `DecemberCommand/product/19956c85ae82`.
Защищённый helper не менялся; wrapper заменяет только build-wheel шаг копированием
проверенных байтов. Receipt явно фиксирует `backend_process_executed=false`,
`completed=true`, пустой `cleanup_error` и неизменённую схему manifest.

Измеренные pins:

- Wheel: `574d91a4fd218c7ce6b691ab5878ecddb9710895f803070e48954961f8379452`.
- Manifest: `d5a63eb8cf78dc9e05f762599cdadf69f4d12d0ce3cd52c76fe87e77115a163a`.
- Install receipt: `40e140ede9d1c8a8e013b8f1578abf3ae41f8fa245c1ffe733074a04805e62fd`.
- Исправленный launcher: `2370ec1f2c06b8979ca1f6da8f2b16d100d44edc1102b19d76716470b173f4d1`.

Helper создал новые ID `counter-src-19956c8`,
`counter-src-19956c8-r1`, `dalio-count-19956c8-r1`. Отдельный initial `source-context`
содержит ровно runstats/counts.py и tests/test_counts.py и выбран только Diagnose.
Snapshot подтверждает initial `source_action_id=null`, точные два пути,
Diagnose target refs и consumed input ID `doc-counter-src-19956c8-r1-input-2`.
Purpose совпадает с новым compiler. Do-инструкция сохраняет прежние байты,
один test-plan перед patch-sources и доверенный runtime digest.
Бюджет: пять действий, одна попытка; 300/300/900/600/1200 секунд,
checker до 1200, action cap 2400, total 4500, grant duration 10800.
Helper не вызывает authorize/enqueue. Завершённые receipts допускают только сверку;
частичная подготовка отказывает без автоматического повтора.

## Проверки

| Проверка | Среда | Измеренный результат | Evidence |
| --- | --- | --- | --- |
| Ранее выполненные affected guards | UTF8 и native cp1251 | По 640 passed, 0 failed/skipped | `ready-result.json`, ссылки на neighbors metadata/JUnit |
| Ранее выполненные Chromium guards | UTF8 и native cp1251 | По 4 passed, 0 failed/skipped | `ready-result.json`, browser-checks metadata/JUnit |
| Wheel/install byte comparison и CLI help | Чистый local venv | 541 package files, RECORD/import OK | `package-result.json` |
| Installed contract smoke | Тот же local venv | Source bytes/hashes, absent/scope/origin guards OK; 0 model/vendor calls | `installed-smoke.json`, `installed-smoke-final.log` |
| Preflight до установки | Native, прежний продукт 385d035 | 63 files, 0 problems, 0 notes | `preflight-before-install.json` |
| Защищённая установка | Protected Python, unchanged helper | completed, exact wheel, cleanup OK | `install-verified-result.json` |
| Preflight нового launcher | Native, продукт 19956c8 | 63 files, 0 problems, 0 notes; manifest/wheel pins совпали | `preflight-launch-do-tests-20261111T1339405297279Z.json` |
| Launcher parsing/checks | PowerShell 5.1.26100.9818 | AST без исполнения; read-only guards PASS | `probe-launch-ast-native.log`, `probe-launch-checks-native.log` |
| Helper syntax/static bindings | Compile AST без исполнения helper | Purpose, runtime/ledger pins и marker order совпали | `prepare.py`; tool output ведущего |
| Подготовка и preview | Protected installed product | Три initial inputs, test_steps только Do, затем один grant | `receipts/`, финальный snapshot |
| Живые review действия | Codex + Grok subscriptions | 4 succeeded, exit 0; 4 proposals/requests/results, без повторов | `snapshot-20261111T134624119308Z.json` |

640+4 на кодировку — сохранённые проверки затронутых контрактов и браузера,
а не новый полный core. Установка не закрывает CI или платформы Linux/macOS.

## Чужие правки

Продуктовый код в этом rollout не менялся. Контроллеры и helper находятся вне repo,
в указанном kit. Агент редактировал только названный REPORT; ведущий ведёт соседние
документы передачи и решения владельца.

## Живой результат и смысл артефактов

Grant один: `authorized_by=codex-test`, `2026-11-11T13:42:50.978925Z`, с прежними
пределами 5/2400/4500 и одной попыткой каждого шага. Goal, Identify и Design выполнил
Codex, Diagnose — Grok. Все четыре action_result имеют succeeded и exit_code 0.
В snapshot нет correction/decision records, Do requests и активного действия.

Grok создал `artifact-causes` размером 7932 UTF-8 bytes. Он цитирует фактический
`return len(rows)`, объясняет отсутствие фильтра dict/outcome и почему имеющийся
тест пустого входа не различает дефектную и требуемую реализации. Оба source SHA
совпадают с сохранёнными исходниками:
counts.py — `79fd0a46778eaa2ce0f2308a05052204be4c85e8760043fcbe08fd7de09cf6b1`,
test_counts.py — `471f75c74c82ce8a0cf91f67233bd91419a1f790edcf3635f9a70481eee67997`.
Артефакт отдельно помечает вывод по тексту и отсутствие исполнения тестов/патча.
Это подтверждает содержательный разбор переданного кода в этой попытке;
внутренний способ рассуждения модели и вызовы её инструментов этим не доказываются.

Design получил `artifact-causes` и brief, создал `artifact-plan` размером 4985 bytes.
План опирается на найденную причину, ограничивает правку двумя файлами и предлагает
регрессии для смешанных исходов, пустого списка и неподходящих типов/значений.
Но в разделе независимой проверки он предписывает `python -m pytest tests/test_counts.py`.
Это расходится с закреплённым протоколом: trusted `python-unittest-v1`, discover `tests`,
pattern `test_*.py`, до 120 секунд внутри Do, затем checker по сохранённому протоколу.
Текст плана не изменяет frozen policy. Расхождение открыто перед решением владельца;
отчёт не подтверждает Do и не утверждает прохождение будущих тестов.

## Сохранение состояния и очистка

Финальный snapshot подтверждает побайтную неизменность ALL старых run/accept files
относительно `receipts/preparation-started.json`, а также трёх исходных файлов
и их копий нового task. OLD385 ledger остаётся:
`0fc70a8da4141f9954052ef671eee262e920d9d549747d7ee9a647597c5e62c3`.
Новый ledger на срезе: `4f0c92a8e0d29457f3cfee3db4c93572b1be2666cd5fdb200a852fbc3edbd2e1`.
`attempt_directory_count=0`.

Независимо прочитаны journal metadata четырёх попыток, выбранных по точному loan work path
`work/_tasks/counter-src-19956c8/work-001`. Для каждой согласованы attempt, owner nonce,
root/data identity и SID; profile/ACL/loan phase равны retired, attempt directory отсутствует:

| Profile file | ACL file | Loan file |
| --- | --- | --- |
| `profile-508eb5c6eef915c2c11e1d686b50ad48.json` | `acl-508eb5c6eef915c2c11e1d686b50ad48.json` | `loan-508eb5c6eef915c2c11e1d686b50ad48.json` |
| `profile-73fdb4a2cffa7fff87c00bfcdd18085c.json` | `acl-73fdb4a2cffa7fff87c00bfcdd18085c.json` | `loan-73fdb4a2cffa7fff87c00bfcdd18085c.json` |
| `profile-b8d966c38b89de04b68682066baa3e54.json` | `acl-b8d966c38b89de04b68682066baa3e54.json` | `loan-b8d966c38b89de04b68682066baa3e54.json` |
| `profile-c73ade84bdce0689c75747433f8b3054.json` | `acl-c73ade84bdce0689c75747433f8b3054.json` | `loan-c73ade84bdce0689c75747433f8b3054.json` |

Evidence: `DecemberAtlasLive/conductor.v3/process-profiles/` с соответствующими
`profile-`, `acl-`, `loan-` JSON. Это проверка четырёх journal triplets и отсутствия
их runtime directories; отдельная native OS-перепроверка удаления SID не выполнялась.
Credential files при независимом чтении не открывались.

## Отклонения

Первый launcher остановился до старта сервера из-за обёртки JSON array в PS 5.1:
`@(Read-Json ...)` давал один вложенный `System.Object[]` вместо двух строк codecs.
`probe-json-array-native.log` различает counts 1/2 и подтверждает сохранение режимов.
Исправлено присваивание результата перед нормализацией массива; checks/asserts не сняты.
Native AST и read-only checks прошли. Product source/wheel этим исправлением не менялись.
Это диагностический повтор launcher после установленной причины, не повтор модели.

`controller-hashes.json` хранит исходный launcher SHA; актуальный SHA указан выше.
Старую запись нельзя выдавать за hash исправленного файла.

## Мутанты

В rollout новый product guard не вводится: переиспользованы доказательства задачи
GROK-REVIEW-SOURCES. Её authoritative full-copy mutation results сохранены отдельно
в `work/grok-review-sources-1111/ui-mutant-results.json` и backend results.
Текущий отчёт не выдаёт installed smoke за новый mutation/full-core прогон.

## Не проверено и открытые вопросы

- Разрешение запуска выполнено codex-test по делегированию владельца; повтор не разрешён.
- Перед Do владелец должен рассмотреть расхождение Design pytest и pinned unittest protocol.
- Gate-confirm-do и финальная приёмка остаются за владельцем.
- Do, патч и постпатчевые тесты не исполнялись; их результат ещё не проверен.
- UI наблюдал ведущий; semantic review основан на saved snapshot и journal metadata.

## Проверка интерфейса ведущим

В Arachnid открыт новый session, legacy route не использовался. В preview явно видны
source-context с двумя путями, оба файла Do и unittest до checker.
Оператор codex-test указан только для делегированного запуска. Срок 10800 секунд
совпадает с сохранёнными terms; рекомендация UI 11700 заменена до просмотра/разрешения.
Grant записан один раз в самом приложении; затем наблюдались Identify и Diagnose.
Скриншот старта: work/grok-source-rollout-1111/launched.png.
После четырёх результатов UI показал 4/5 и Human Gate - Confirm Do.
Карточка открыта для владельца: имя решения пустое, запись решения недоступна.
Скриншот: work/grok-source-rollout-1111/confirm-do.png. Сервер 99419 оставлен работающим.

## Ревью Codex

Независимо прочитаны финальный snapshot, источники/consumed IDs Diagnose, actual causes/plan
и четыре cleanup triplets. Передача source context и остановка до Do подтверждены.
Открытое замечание: неверная команда/порядок тестирования в Design, как описано выше.
Решение о Do и финальная приёмка этим ревью не делегируются.

## Передача

Последний доказанный шаг: четыре review действия нового запуска succeeded;
Grok дал разбор фактических исходников; run остановлен до Do, старое состояние сохранено.
Первый несделанный шаг: решение владельца на gate-confirm-do с учётом замечания к Design.
Не повторять: первую launcher-попытку без исправления array wrapping;
модельные действия, старый run и Do не повторять и не подтверждать.
Следующий шаг: ведущему передать владельцу живую Studio и артефакты на gate-confirm-do.
Код/CAPPED 19956c8 не менялись. Ведущий фиксирует REPORT, handoff и решение отдельным
docs-коммитом после проверки файлов; публичный выпуск этим не объявляется.
