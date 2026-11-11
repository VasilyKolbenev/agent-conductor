Итог: локально проверено | 19956c8 | dry run PASS, metadata PASS | Do 0 | подтвердить владельцу.

# DO-UNITTEST-ALIGN: план согласован, Do подготовлен

Основание: TASK 792c7f1, решение c9cfa35. Продукт и CAPPED 19956c8 не менялись.
Ветка recovery/2026-10-20. Чужих правок не было.
Kit: `C:/Users/Пользователь/Documents/Codex/work/do-unittest-align-1111/`.

## Изменения и происхождение

В том же counter-src-19956c8-r1 добавлен human-unittest-counter-src-19956c8-r1,
ref artifact-plan, source_action_id=null. Это редакция техлида по поручению владельца,
не подмена результата модели. Исходный artifact-1a3339b3d7ad24e1b77489d2f1d87475
сохранён побайтно. Новый текст указывает его ID и SHA-256.
Изменён только раздел независимой проверки; обратная literal replacement восстанавливает
весь прежний текст. Функциональные требования и два разрешённых файла сохранены.

Согласовано: discoverable unittest.TestCase; приложение после патча исполняет pinned
python-unittest-v1, discover tests/test_*.py, до 120 секунд внутри Do. После этого
отдельный Codex проверяет diff и фактический протокол. Pytest не требуется.
Zero tests, timeout, неполный или неуспешный протокол не считаются прохождением.
Instruction document и его test-plan/runtime digest не изменялись.

Human plan UTF-8 SHA-256:
a8d530032a00418b2ecaf7076bc9093b850e70dbd001a43cc762644608a2134d.
Текст: work/do-unittest-align-1111/human-plan-unittest.txt.
Контроллер align.py SHA-256:
9c45d3b5a01483575e59ecca1f726641c527483eb10f26032e62020c693d2a07.

## Разрешение и бюджет

Через публичные API отозван прежний grant, опубликована новая редакция, создан preview
и записан superseding grant authorization-unittest-counter-src-19956c8-r1.
Это три новые metadata-записи и четыре HTTP POST, включая read-only preview.
Нет decisions, новых action requests, вызовов моделей или CLI провайдеров.

Caps прежние: 5 действий / 2400 секунд на action / 4500 общего резерва;
node caps 300/300/900/600/1200, по одной попытке. Расход cumulative по всей истории:
4 действия / 2100 зарезервированных секунд; осталось 1 действие / 2400 секунд Do+checker.
Новый срок 19:37:51 МСК 11.11.2026 раньше прежнего 19:42:50 МСК.
Исходное разрешение не продлено; источники и полномочия не расширены.
Новый initial binding выбирает уточнённый план для Do и его независимой проверки.

## Доказательства

- Один dry run установленного SDK: hypothetical revoke/document/regrant прошли валидацию,
  0 POST и неизменный журнал. Receipt dry-run-20261111T141539697264Z.json.
- Apply прошёл один раз: apply-receipts/completed.json, отдельный intent/response каждого POST.
- До: 33 records, SHA 4f0c92a8e0d29457f3cfee3db4c93572b1be2666cd5fdb200a852fbc3edbd2e1.
- После: 36 records, SHA f81919e399e01584e361caa4182447639b97935f3e28ba6838323168c8a65aee.
- Все прежние 33 строки сохранены literal prefix. Graph/config, instruction bindings,
  старый 385 run/accept, исходники и новая копия задачи побайтно неизменны.
- После UI повторно прочитаны API: waiting/plan_waiting, active=null, 4 requests, Do 0,
  decisions 0. Evidence ready-after-ui.json.
- В Studio открыта карточка Do; vasily и ссылка на новую редакцию заполнены только
  в локальной форме. Причина 160 символов; кнопку записи решения ведущий не нажимал.
  Скриншот work/do-unittest-align-1111/do-ready.png.

## Ревью Codex

Ведущий прочитал контроллер целиком. Независимый агент проверил literal section change,
schema, closed POST allowlist, cumulative budget, deadline ceiling и запрет решения Do.
Blocker/major не найдено. Правильный scope metadata подтверждён реальным API.
Комментарий gate не передаётся Do/checker; поэтому исправление закреплено документом,
а не только текстом в поле причины решения.

## Отклонения, мутанты и открытые вопросы

В ревью контроллера до исполнения исправлены копирование schema_version в terms,
legacy URL и написание defaultTestLoader. Dry run после исправлений прошёл с первого раза.
Изменений продукта/новых guard tests нет: новые мутанты и повтор полного core не применимы.
Финальные документы проверяются test_file_endings в UTF-8 и CP1251;
receipts проверки сохраняются в kit. Живой Do и постпатчевые тесты ещё не выполнялись.

UX-ограничение: disclosure результата Design выбирает исторический artifact по action ID,
поэтому показывает прежний model plan. Новый human plan закреплён в фактических входах Do,
его ID указан в подготовленном решении; полный текст доступен отдельным файлом.
Будущая UI-правка должна показывать оператору effective plan и его происхождение рядом
с историческим результатом. Это ограничение не маскируется переписыванием старых данных.

## Передача

Последний доказанный шаг: новый human plan закреплён, бюджет сохранён, Do ждёт владельца.
Первый несделанный: владелец подтверждает gate-confirm-do в Studio.
Не повторять четыре review шага и apply controller. Не подтверждать Do/приёмку за владельца.
Один сервер 99419, Studio: http://127.0.0.1:7830/#session=counter-src-19956c8-r1&lang=ru.
Нижний порог 20%; на последней проверке остаток 22%.
