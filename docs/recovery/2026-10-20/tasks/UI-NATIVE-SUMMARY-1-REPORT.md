Итог: локально проверено и принято ревью | 77b8104 | 28 browser + 327 structure passed
в каждой кодировке, 0 failed | среды исправлены без ослабления тестов | следующий шаг:
pre-alpha security debts по ALPHA-NEXT-2-DAYS.md.

# UI-NATIVE-SUMMARY-1

- Исполнитель: Codex; независимые линзы do_rejected_inspector и alpha_readiness_now.
- База 8f98e14, ветка recovery/2026-10-20; рабочая копия до задачи чистая.
- TASK/DESIGN v1 b5a6045, DESIGN v2 5622cd3; код 77b8104, CAPPED без новых файлов.
- Защищённая рабочая Studio остаётся на 19956c8, server 99419, порт 7830.

## Изменения и причина

Верхняя сводка принимала recorded tests только с source external; native ошибочно
показывался как absent. Теперь сводка, вкладка Tests и ответ Атласа используют один
atlasTestSummary. Native timeout без counts больше не ломает badge summary.total.
Bindings, matchesAtlasAttempt, сервер и выполнение задач не менялись.

Fixture tests/fixtures/atlas-accepted-native.json основан на raw response принятого
counter-src-19956c8-r1. Реальные diff, test counts/output/hash и verified сохранены;
IDs, argv/cwd и policy (только runner) обезличены для локального test server.
Это UI-проекция сохранённых фактов, а не новый криптографический protocol witness.
Failed/timeout/zero/truncated/infra варианты синтетические, проверяют отображение;
их изменённые status/counts не доказывают backend-валидность исходного transcript.

## Проверки

Артефакты: Documents/Codex/work/ui-native-summary-1111, вне Git.

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| RED на старом коде, native passed EN | 1 failed, 0 errors/skipped | red-native-browser.xml: literal Tests passed против No test report |
| Финальный Chromium, UTF-8 | 28 passed, 0 failed/errors/skipped | final-utf8.xml |
| Финальный Chromium, native CP1251 | 28 passed, 0 failed/errors/skipped | final-native.xml; utf8_mode=0, preferred/stdout cp1251 |
| Module graph/source/cap/endings, UTF-8 | 327 passed | structure-utf8-fixed-environment.xml |
| Те же guards, CP1251 | 327 passed | structure-native.xml |
| M0, полная изолированная копия | 1 passed | mutations/M0.xml; imports/assets из копии |
| M1 external-only | 1 failed | Ложное отсутствие native report |
| M2 formatter no-op | 1 failed | Пустая сводка вместо literal native status |
| M3 убрать counts nullguard | 1 failed | Чтение total у null |

Мутанты: errors/skips 0, после каждого SHA восстановлен, полная копия удалена.
1612 файлов сверены побайтно; mutations/results.json SHA
6397d5ec7fd429e6b8b6a75e5761f2d7bc22c302bb7a56bd3c291f849083b55e.
EN/RU screenshots проверены визуально; сводка и вкладка одинаково показывают 3/0/0/0.
Чужие изменения отсутствуют, crapper/dryer/mutator не ставились.

## Отклонения и ограничения

Два запуска browser в ограниченной среде зависли до проверяемого результата,
остановлены через Ctrl+C, не засчитаны как RED или green. Native Chromium вне этой
границы воспроизвёл именно дефект сравнения; sandbox guards не снимались в продукте.
Первый structural run: 321 passed, 6 setup errors — WinError5 при создании короткого
basetemp вне writable root. В workspace basetemp обе кодировки дали 327 passed;
ошибка прав на каталог не скрыта повтором и не объявлена дефектом продукта.

Полная release matrix, новый CI-wheel и защищённая установка нового кода не выполнялись.
Предыдущие 26 browser passed/codec до двух новых unavailable кейсов сохранены;
финальными считаются 28/codec, не сумма повторов. Живые модели/циклы не вызывались.

## Сохранность

Принятый ledger остался побайтно прежним:
60f2621862e977456552be6d58044cb603808cd66c4173a6c09a1e0b99825ad6.
checks-and-preservation.json сохраняет JUnit hashes и cleanup: свои temp удалены,
прерванные sandbox temp отсутствовали. Рабочая Studio и её принятый результат целы.

## Ревью Codex

Принято: две независимые линзы до кода и независимое чтение финального diff.
Blocker/major нет. Два замечания закрыты: добавлен unavailable EN/RU и убран
оставшийся personal install path из policy fixture. Недоступный Opus не имитировался.
Окончательные 28/28 и mutants проверены ведущим по receipts после reviewer snapshot.

## Передача

Код 77b8104, новые source/tests модули не создавались, CAPPED прежний.
План на два дня: ALPHA-NEXT-2-DAYS.md; существующие release gates не отменены.
Последний доказанный шаг — локальная сводка native results и nullable status, без
повтора принятого цикла. Первый несделанный — адресная проверка pre-alpha долгов
H5-I2B-Q6/Q8/Q10 и H5-QUOTA-IDS-RS1, затем единый release candidate/CI/чистый onboarding.
Не повторять counter-src-19956c8-r1, завершённые checks и M0/M1/M2/M3.
Новый предел владельца 15%, последний замер 19% остатка; автоматической публикации нет.
