Итог: локально проверено | 19956c8 | 3 unittest passed, 0 failed/errors/skipped | финальный gate.

# DO-UNITTEST-RUN1: Do и независимая проверка прошли

Основание: TASK 8e8468d, DO-UNITTEST-ALIGN 85284cf. Ветка recovery/2026-10-20.
Продукт/CAPPED 19956c8 не менялись; чужих правок нет. Финальная приёмка не записана.
Kit: `C:/Users/Пользователь/Documents/Codex/work/do-unittest-run1-1111/`.

## Владелец, старт и границы

Первое сообщение о нажатии не сопровождалось записью: 36 records, decisions/Do 0.
Форма и console не показывали ошибку; причина первого незаписанного нажатия не установлена.
После уточнения кнопки владелец нажал «Записать решение», и в 17:27:07.893 МСК записан
approve gate-confirm-do от vasily, receipt-gate-confirm-do-0-vasily.
Это первая и единственная попытка Do; повторов моделей или цикла не было.

Do action: action-05654503d343d826abd98a1b6a969694.
Attempt: attempt-e57ab78075d3949d0a245aceaa01c9ca418a7520ec2074f692516cb444439972.
Старт 17:27:08.024 МСК, implementer instance-role-implementer / codex,
profile implement-patch-v1, лимит 1200 секунд, уточнённый human plan закреплён.
Одно действие включает patch, офлайн-применение, тесты и отдельного checker.

## Изменение и реальные тесты

В копии задачи изменены только runstats/counts.py и tests/test_counts.py.
Вместо len(rows) считается число dict с outcome == "succeeded"; другие типы,
отсутствующий ключ и неточные значения пропускаются. Устаревшая docstring исправлена.
Сохранён пустой тест; добавлены смешанные четыре словаря с результатом 2 и набор
не-словарей/неточных outcome с результатом 1. Все три метода — unittest.TestCase.

Настоящий pinned python-unittest-v1 выполнил эти три теста после патча до checker:
total 3, failures 0, errors 0, skipped 0; exit 0, completed, без truncation.
Вывод: Ran 3 tests in 0.000s; OK. Это протокол приложения, не заявление doer.
Raw protocol в unittest.txt, полный diff в changes.diff, API projection в attempt.json.
UTF-8/base64/output SHA-256 сверены независимо, сохранённые 525 байт совпали:
ee11aee39b4930c6c1526f68dbbc68e494eb88fe7336ea6a7325fb85ebbd21fe.

## Независимый checker и порядок

Отдельный instance-role-checker / codex дал verified для той же попытки.
Outcome Do succeeded; manifest snapshot:
sha256:3733fec2f676a7605213038641984f69dbb546cdfb3bb82e4d67d96cf8b184ef.
Сохранённый report/seal anchor — запись 42 в 17:27:26.853 МСК;
checker verified proof — запись 43 в 17:27:40.475 МСК с тем же seal.
В протоколе нет отдельного wall-clock поля времени тестов; порядок подтверждён
durable anchor и обязательным включением bound report в checker frame до его запуска.

Независимый аудит установленными read_bound_protocol/patch_verifier/read_snapshot
перехешировал blobs и сверил attempt/grant/policy/toolpin/tree/modes/input IDs,
включая human-unittest-counter-src-19956c8-r1. Без новых тестов/CLI провайдеров/моделей.
Автор результата и checker — разные instance IDs. Приёмку владельца это не заменяет.

## Сохранность и очистка

Все три оригинальных файла проекта и старый counter-src-385d035-r1/accept неизменны.
В новой копии задачи ровно три файла, два изменённых соответствуют snapshot.
Внутри одной action было четыре process-profile: doer с relay, offline patcher,
unittest и checker с отдельным relay. Это четыре подпроцесса, не четыре попытки модели.
Все 12 profile/ACL/loan records retired, mappings и временные папки отсутствуют,
две relay homes удалены; container-attempts пуст.
Evidence cleanup-audit.json SHA-256:
a5623db377feb3eea13f85a87fb62d65efd0cae6d21597c6ad3913d5aa01dfa4.
В process journals нет action_id: связь проверена по exact work scope, окну Do,
install/home и отдельно по точному unittest argv. Это ограничение корреляции сохранено.

## UI и открытая находка UI-NATIVE-SUMMARY-1

В Arachnid выбран Do и ровно эта попытка 1/1. Проверены оба diff, native unittest
с argv/cwd/output/exit и отдельная вкладка verified checker. Скриншоты в kit:
counts-diff.png, do-unittest.png, do-verdict.png; полный diff сохранён отдельно.
Результат доступен в этих вкладках; финальный Result Gate ждёт владельца.

Измерена ошибка верхней сводки: там написано «нет отчёта», хотя вкладка «Тесты»
правильно показывает native report и 3 passed. По коду причина подтверждена:
arachnid-conversation.js:212 учитывает только source == external и относит native
к test_absent. Корректный renderer вкладки есть в studio-atlas-inspector.js.
До передачи альфы исправить сводку с red native witness без повторения живого цикла.
В этом наблюдении код/сборка не менялись; ошибочное сообщение не считается истиной.

## Ревью, проверки и мутанты

Ведущий проверил API, diff, hash raw output и UI; отдельные агенты независимо проверили
spec/manifest/test bindings и cleanup/preservation. В backend evidence blocker/major нет.
UI finding выше открыт отдельно. Новый продуктовый код/guard tests не добавлялись,
поэтому новые мутанты и полный core не применимы. Тесты задачи вручную не повторялись.
Финальные документы проверяются test_file_endings в UTF-8 и штатной CP1251.

## Передача

Журнал 44 записи, SHA d00a402104d56445cde408e803907ce6545557ab351bd068a74ce15ab3437297.
Все пять task nodes settled, spent 5/4500, остаток 0/0; это резерв, не время по часам.
waiting/plan_waiting, Result Gate runnable/answerable first. Только одна decision — Do;
финальной приёмки нет. Один server 99419 работает на 7830, код/CAPPED 19956c8.
Последний доказанный шаг — Do succeeded + реальные 3 теста + отдельный checker verified.
Первый несделанный — владелец рассматривает diff/протокол и решает gate-result в Studio.
Не повторять Do, весь цикл или тесты задачи; не принимать финальный результат за владельца.
Порог 20%; на последней проверке осталось 22%. Публичный выпуск этим не объявляется.
