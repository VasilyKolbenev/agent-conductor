# GROK-REVIEW-SOURCES DESIGN v1

База d5c15dd. Операционный сбой — DO-TEST-STUDIO-RUN1-REPORT.md.
Никаких изменений текущего run, grant, ACL, разрешённых инструментов или бюджета.

## Выбор

A: только уточнить purpose «прочитай файлы». Это меньше diff, но двойник докажет
лишь передачу просьбы, а не попадание исходных материалов к харнессу.
B: явно объявленный initial-human source context с фактическими bytes/hashes.
Выбран B: source data уже доступны в рамке независимо от решения модели о Read.
Purpose уточняется только в новых планах с таким контекстом.

## Контракт

Новый opt-in в initial artifact, выбранном среди target_artifact_refs Diagnose:
два перевода строки, conduct.review-sources.v1, перевод строки и JSON списка путей.
Ровно один selected initial документ; malformed/duplicate marker отказывает.
Model-produced документ не разрешает чтение; невыбранный initial документ тоже.
Legacy review без нового marker получает прежний frame. Do marker не переосмысляется.

Список берётся только из пользовательского brief через нынешний namedSources.
Новый initial ref source-context включается только в Diagnose; Goal и прочие
стадии не получают новые права автоматически. Модельный criterion не добавляет пути.
Новая цель Diagnose: исследовать переданный код и объяснить фактическую причину,
отделять уже существующие материалы от будущих результатов Do/checker.

source_section получает optional marker, default прежний patch marker.
Закрытый parser путей, file_image, full-tree digest, UTF-8/NUL, secret scan и лимиты
переиспользуются. Отсутствующий явно названный файл остаётся строкой state=absent,
как в Do; это не доказательство отсутствия иных материалов или успешной диагностики.
Пути вне task scope, порталы и hardlinks не становятся источниками.

Материализация — до version/model preflight. Frame содержит JSON rows с literal
path/content/sha256, затем проверяется весь task channel. До spawn снова сверяется
полный before tree. Дерево после действия проверяется прежним review contract.
Source input ID сохраняется стандартной связью consumed input artifacts.
Ни raw credentials, ни произвольного shell/нового SDK execution door нет.

## Новые планы и сохранённые планы

compile/recordedDalio получают явный режим source context. Для нового плана — новый
режим. При повторном открытии существующего draft/revision режим выводится из
замороженного документа: наличие source-context среди входов Diagnose.
Старый опубликованный граф и старые initial inputs не дополняются автоматически.
Проверки полного equality графа/inputs/grant сохраняются; «снять equality» не решение.
Do patch-source instruction и его restore-совместимость остаются прежними.

## Проверки

- Red public Grok process seam: точные текущие bytes/hashes обоих файлов и cwd;
  sibling/unrequested canaries отсутствуют; raw source data дошли в conduct-task.txt.
- Initial-origin/selected input, malformed/duplicate, outside/portal/link, binary,
  NUL/secret/overflow и changed-tree отказывают до vendor spawn.
- Legacy без нового marker byte-identical; generated marker не даёт чтения.
- Builder добавляет source-context с user-only paths в Diagnose; purpose конкретен.
- Reopen старого/нового плана, lost-write reconciliation и human-only grant прежние.
- No-op materialization и source-origin/hash mutants; UTF-8 и native CP1251.

Тест не доказывает качество будущего ответа модели или полный живой цикл.
После этой задачи новый wheel/реальная попытка требуют отдельного решения владельца.
