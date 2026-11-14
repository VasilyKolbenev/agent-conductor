Итог: локально проверено | 19956c8 | 640 passed/codec, 0 failed | без моделей | далее сборка.

# GROK-REVIEW-SOURCES: исходный контекст Diagnose

TASK fda7c5a, DESIGN v2 e390f25, код 19956c8. Порог владельца — 20% остатка.
Последний замер — 23%, usedPercent=77. Настоящих vendor/model calls в этой задаче нет.
Чужих правок на старте d5c15dd не было. Исполнители меняли только названные файлы;
ведущий свёл изменения, регистрацию CAPPED, проверки и отчёт.
Артефакты: Documents/Codex/work/grok-review-sources-1111/.

## Подтверждённый пробел и границы вывода

Purpose Diagnose не потерян: он записан в реальном request и включён в рамку.
Файлы есть в правильной task copy, cwd соответствует ей; реальный loan дал review RX,
Grok разрешены Read/Grep/Glob. Свидетельств access denied нет.
Но рамка Diagnose содержит только artifact-problems и artifact-brief, без исходных bytes.
Grok пересказал нехватку материалов; первичный _review_task просит анализировать входы.
Это подтверждённый пробел входного контракта. Внутренняя причина решения модели
не вызывать Read не доказана; её не выдаём за измеренный факт или дефект ACL.

## Что исправлено

Новые coding plans Atlas создают отдельный initial artifact source-context с marker
conduct.review-sources.v1 и JSON списка путей только из пользовательского brief.
Только Diagnose объявляет этот input и получает цель исследовать фактический код.
Модельный criterion не добавляет пути. При отсутствии human paths новый input и purpose
не создаются: non-code review сохраняется.

Backend принимает opt-in только из выбранного initial ref=source-context.
Marker в смешанном artifact-brief, generated или невыбранном документе не даёт чтения.
Malformed/duplicate policy отказывает. Существующий source_section переиспользует
validate_path/file_image, scoped tree, plain-file guards, UTF-8/NUL, secret scan и лимиты.
Тексты и SHA-256 выбранных файлов включаются в фактический task file Grok;
явно названный отсутствующий файл показан как absent. Никакого shell fallback нет.

Before tree фиксируется до материализации и переносится через version preflight.
Перед model attempt сверяется именно этот tree, а не новый произвольный snapshot.
Результат сохраняет input_artifact_ids исходного документа по прежнему handoff.
Review остаётся read-only, права и перечень инструментов не расширены.
Do marker и его test plan не переосмыслены.

При reopen режим определяется по frozen draft/revision до expected compile.
Legacy не получает новые файлы, purpose или inputs; полные equality и conflict guards
графа, документов и grant сохранены. Подготовка не выдаёт разрешение сама.
Три новых code/test файла внесены в CAPPED; artifact_transport — 797 строк.

## Проверки

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| Public Grok red на старом коде | 1 failed, 0 passed: 0 source rows вместо 3 | backend-red.log |
| Builder red на старом коде | 1 failed, 1 passed: null вместо literal policy | ui-red-comparison.log |
| Новый backend + прежние Do sources | 29 passed/codec | backend-green-{utf8,native}.log |
| Node builder/reconciliation | 13 passed/codec | ui-green-{utf8,native}.log |
| JS plan → настоящий Python contract | passed | GraphTemplate.from_dict + materialize в positive |
| Все затронутые соседние контракты | 640 passed/codec, 0 failed/errors/skips | neighbors-result.json |
| Chromium planning/subscription | 4 passed/codec, 0 failed/errors/skips | browser-checks/neighbors-result.json |

Числа пересекающихся целевых наборов не складываются как уникальные тесты.
Оба режима проверены фактически: UTF-8 mode=1 и preferred/stdout utf-8;
native mode=0 и preferred/stdout cp1251, без PYTHONUTF8/PYTHONIOENCODING и live opt-ins.

Публичный положительный свидетель читает настоящий conduct-task.txt на процессной
границе, сверяет literal contents/hashes обоих файлов, child task hash, scoped cwd,
прежние allow/deny flags и сохранённые input IDs. Sibling/unrequested canaries отсутствуют.
Негативы: неверный ref/selection, malformed/duplicate, outside/reserved paths, hardlink,
portal, binary/NUL, настоящий fake login secret, per-file/channel overflow и изменение
невыбранного файла в version preflight. Последнее не запускает модель.
Generated-origin/legacy byte identity проверены отдельно на typed helper с реальным
workspace; это не заявляется полным runtime witness происхождения model artifact.

## Мутанты

Изолированные копии src/tests/pyproject, импорт conductor из копии; после каждой
поломки восстановлены SHA. Реальные исходники и рабочий проект не менялись.

| Мутант | Результат | Что различает |
| --- | --- | --- |
| Backend M0 | 22 passed | Набор без поломки |
| Нет source rows | 1 failed, 21 passed | Доставка буквальных материалов |
| Brief разрешает чтение | 2 failed, 20 passed | Dedicated ref и mixed criterion |
| Model origin разрешает чтение | 1 failed, 21 passed | Initial origin |
| Подставной source hash | 1 failed, 21 passed | Хеш фактических bytes |
| UI M0 | 13 passed | Полная изолированная копия |
| Нет binding Diagnose | 3 failed, 10 passed | UI source contract |
| Нет code-purpose | 1 failed, 12 passed | Цель исследования кода |
| Всегда новый режим | 1 failed, 12 passed | Frozen legacy |

Backend restore/import/log hashes — backend-mutant-results.json.
UI provenance/restore/root equality — ui-mutant-results.json.
Первичные UI JS-only mutants пойманы, но не считаются достаточным §3 proof:
после замечания ведущего выполнен полный изолированный witness.

## Ревью Codex и отклонения

Независимые линзы DESIGN: «Спека» закрыла mixed-origin S1 и empty-source S2;
«Стандарты/границы» уточнила before binding E1. Ведущий перепроверил по source.
После реализации автор UI независимо проверил backend, автор backend — UI.
Blocker/major в проверенном diff не найдены; ведущий прочитал код и тесты отдельно.
Opus недоступен, использованы Codex-агенты по делегированию владельца.

Setup failures не выдаются за red: неверная fixture binding, JS redeclaration,
старый Set/повтор brief в legacy fixture и tuple/list contract comparison сохранены
в отдельных исходных логах. Исправлены предпосылки свидетелей, guards не ослаблены.
В preflight race версия идёт через ProcessRunner.run, не hook boundary run;
runtime публично нормализует причину в adapter reported failed. Тест проверяет
этот literal и отсутствие model prompt, не частный внутренний текст ошибки.

## Непроверено и передача

Полный core/CI, Linux/macOS, сборка/защищённая установка и новый живой Diagnose
в этом TASK не проводились. Локальная доставка bytes не доказывает качество будущего
ответа модели или успешный полный цикл. Новый контракт не меняет старое разрешение.

Рабочая Studio остаётся 385d035. Ledger counter-src-385d035-r1 по-прежнему
0fc70a8da4141f9954052ef671eee262e920d9d549747d7ee9a647597c5e62c3,
waiting/plan_waiting, Do не начат; real calls этой задачи=0. Receipt live-preserved.json.
Последний доказанный шаг — локальный source-contract fix с двойниками и review.
Первый несделанный — проверка кандидата перед новой сборкой/предпросмотром по решению
владельца. Не одобрять текущий Do автоматически и не повторять старый цикл.
