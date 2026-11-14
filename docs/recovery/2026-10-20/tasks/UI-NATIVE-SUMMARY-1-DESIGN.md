# UI-NATIVE-SUMMARY-1: дизайн v2

## Причина и варианты

evidenceSummary в arachnid-conversation.js принимает recorded только с source external.
Вкладка Tests уже использует summary(view, tests) из studio-atlas-inspector.js:
она учитывает native status, optional counts, external, absent и unavailable.

A: скопировать mapping native в evidenceSummary. Меньше межмодульных изменений,
но две независимые реализации тех же фактов уже привели к расхождению.
B: экспортировать существующий pure formatter и использовать его в сводке.
Выбран B: одна логика, нет нового импорта модуля или изменений API сервера/guards.

Две независимые линзы: do_rejected_inspector — контракт/отрицательные сценарии;
alpha_readiness_now — стандарт/доказательства и границы альфы. Замечания до кода
фиксируются в v2, исполнитель Codex; внешние недоступные Opus/Sonnet не имитируются.

Замечание 1.1 (обе линзы): оставить matchesAtlasAttempt единственной дверью к helper,
не подменять binding и не отображать повреждённый protocol как успех.
Замечание 1.2 (do_rejected_inspector): resultHere badge тоже читает summary.total
без nullguard; native timeout может иметь counts null. Badge требует реальных counts,
а сводка показывает статус без выдуманного нуля; browser ловит pageerror и неверный текст.
Замечание 2.1 (alpha_readiness_now): helper использовать напрямую в обоих местах,
legacy external и отказ при несовпадении попытки сохранить. Альфа не следует из UI fix.

## Швы и границы

Browser проходит корневой #session route, выбирает Do на орбите, читает верхний
data-atlas-fact=tests, затем другую попытку. Подмена только HTTP evidence boundary.
Обезличенный fixture основан на attempt-final.raw.json принятого run: сохраняет
diff, counts, вывод и статус; заменяет IDs/binding, пути runtime и cwd на fixture values.
Литералы ожидаемых EN/RU текста/счётчиков не вычисляются production formatter.
Дополнительно native failed, timed_out без counts, unavailable/not_recorded.
Существующие external и wrong binding tests сохраняются. Browser screenshot доказывает
отрисовку локального двойника; не установку нового wheel и не новый живой цикл.

Red на прежней external-only ветке; no-op/неверный status мутанты в полной копии
src/tests/pyproject.toml с проверкой import path и восстановления SHA. Только целевые
browser/структурные проверки в обеих кодировках; полный release CI остаётся отдельным gate.
