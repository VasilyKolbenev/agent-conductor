Итог: локально проверено, CI запущен | 6f4d947 | core20621 passed+4subtests,
0 failed/errors,441 skipped в каждом codec | remote пока не green | следующий шаг: CI43388477627.

# CI-PORTABLE-ROOT

Исполнители: Codex root, portable_collection, wheel_entry; независимый CI-аудит ci_final_audit.
База b887cff, recovery/2026-10-20, status чистый. TASK/DESIGN записаны до реализации:
dfe99c1, 3969015, 8fa93f7, 75c414a. Владелец разрешил conditional CI, без моделей/нового цикла,
стоп10% остатка; старт14%.

## Изменения

- tests/os_boundary_box.py: Windows backend импортируется при native use; аннотации через
  TYPE_CHECKING. Все существующие gates, отказы, assertions сохранены.
- tests/test_patch_do_native.py: native import после fixture gate, внутри теста.
- tests/test_native_probe_imports.py: fresh subprocess проверяет семь реальных collectors
  при недоступном Windows backend и явный отказ при native use.
- scripts/installed_probe.py: root provenance из owning server.ENTRY_PAGE.
- scripts/wheel_road.py: SHA/type/status/no-redirect/census прежние; root Arachnid witnesses,
  пять экранов и nav на explicit Studio route; обе document routes обязательны.
- tests/test_wheel_root_contract.py: настоящий isolated no-pip venv с own copied package,
  смена owning ENTRY_PAGE, HTTP IO double с независимыми file hashes, негативные guards.
- Оба новых теста внесены root в CAPPED тем же коммитом кода.

## Проверки

Все артефакты вне Git: Documents/Codex/work/ci-portable-root-1113.

| Проверка | UTF-8 | CP1251 | Доказательство |
| --- | --- | --- | --- |
| I1 guard и шесть collector модулей singly | 13 passed, 9 skipped | 13 passed, 9 skipped | collection/targets-elevated.json |
| I2 root contract и release matrix с B3 | 36 passed | 36 passed | wheel/b3-*.log |
| CAPPED и окончания файлов | 319 passed | 319 passed | meta-*.xml |

I1 RED:8 failed. I2 meaningful RED:3 failed,18 passed; B3 RED:2 failed,22 deselected.
Пропуски I1 относятся к прежним native/opt-in gates, новых skips нет.
Поддержанные POSIX здесь не запускались: WSL inventory пуст; import simulation не Linux run.
Полный core exact6f4d947 завершён:58/58 групп, UTF8 полностью до CP1251,744 файла
ровно один раз на codec. В каждом:20621 pytest passed+4subtests,441 skipped,4 warnings,
0failed/errors. JUnit attributes:21066total/20625passed/441skipped; testcase nodes:
21062total/20621passed/441skipped. Разность4 — измеренные subtests, не двойной счёт.
Каждый native файл singly, ordinary max4, mode/import witnesses и пустые opt-ins сохранены.
Detached source чистый до/после; session44329 exit0, chunk a4f281, все58 финальных receipts.
Проверенные scripts не вызывают vendor-модели. Новых моделей/CLI/живых циклов0.

Full run: kit/run-20261113T065710197551Z. Results SHA256:
75f6b0678a34b3b492f6f86ff073e329a24fc936d421db70b22c8eccc5f10da7.
Независимый aggregate.json SHA256:
4fe603e7260b55fc4e942e4d7c209fb41e38cd4802e436c9b4198cbf2bae4d20.
Первый aggregate equality guard выявил разность suite attrs/testcase nodes; это ошибка
предположения агрегатора, не тестов. Исправлен явный учёт4subtests, итоговые guards true.

После allgreen выполнен один no-force push в ранее отсутствовавшую ветку
candidate/alpha-2026-11-13-6f4d947. API подтвердил точный6f4d9479ab1f75e9a7c5b1ada8dfba260a13c8ca.
[CI43388477627](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43388477627)
создан событием push на этом SHA, первый snapshot queued/conclusion null.
Следующий snapshot:12jobs,3success/9in_progress. Build и оба настоящих installed
wheel roads (Ubuntu/macOS, jobs131762539806/131762539432) зелёные. I2 подтверждён
на POSIX; итоги core и browser ещё ожидаются. Raw snapshot: kit/ci-jobs-snapshot.json.
Main/recovery remote, tags/releases и protected Studio не менялись. Remote proof/push receipt в kit.

## Мутанты

| Группа | M0 | Мутант | Результат |
| --- | --- | --- | --- |
| I1 | 8 passed | eager helper / eager patch / native no-op | 7 / 1 / 1 failed |
| I2 | 22 passed | stale root / duplicated root | 2 / 1 failed |
| I2 | 22 passed | SHA/type/redirect/status/chat/classic/classic href/census | каждый 1 failed |
| I2 | 22 passed | missing Studio screen guard | 10 failed |
| I2 B3 | 2 passed,22 deselected | missing required document routes | 2 failed |

Итого15 обнаруженных мутаций. Копии src/tests/scripts/pyproject, import witnesses,
SHA восстановления и cleanup сохранены в collection/mutants.json, wheel/mutants.json,
wheel/b3-mutants.json. Сторонние crapper/dryer/mutator не ставились; мутации вручную.

## Чужие правки

Нет. Scoped параллельные изменения перечислены выше; общие документы/CAPPED/commits у root.
Принятый counter-src-19956c8-r1, protected Studio и личные профили не изменялись.

## Отклонения

Первый sandbox I1 запуск:8 passed и2 setup errors WinError5; сохранён. После доказанного
ограничения доступа native fake проверки выполнены elevated с новыми temps.
Первый I1 M0 без scripts package:5 failed,3 passed; исправлена только mutation copy,
повтор M0:8 passed. Исходники не менялись ради этого результата.
Первый I2 harness run:1 failed,18 passed,2 setup errors из-за cp1251 stdout пути;
JSON ASCII query устранил причину. Этот запуск не засчитан как provenance RED.
B3 cleanup diagnostic сохранён: выбранные HTTP guards не создают temp, проверяется lexists.
Root B3 review добавил required routes до финальной реализации. Утилиты/таймауты/защиты
продукта не ослаблены, новых retries или waivers нет.

## Открытые вопросы / не проверено

CI d7334d6, run43106716036 завершён failure:2 success,10 failure. Все12 logs и
проверенные browser artifacts сохранены в ci-audit/AUDIT.md. I1/I2 исправляют причины
четырёх POSIX core и двух installed roads; это не закрывает остальные job:

- Windows3.11: test_long_path.py fixture считает, что Path не меняет device spelling.
  Offline3.11/3.12 свидетель доказал slash уже в os.fspath до production helper.
- Browser: устаревший census verifier IDs после Q6; iframe focus policy; macOS response
  body после navigation; POSIX subscription-advice unavailable; Ubuntu layout/participant
  failures. Для последних причины полностью не доказаны. Не выдавать их за root defect.

Эти независимые blockers сохранены, исправления вне текущего scoped TASK. Новый CI может
оставаться красным; local green не означает remote green, owner acceptance или alpha release.

## Ревью Codex

Root прочитал непустой diff на существующей базе и оба новых regression модуля.
Две design-линзы GO; независимые I1/I2 cross-reviews GO. Root finding B3 исправлен с RED
и killed mutant. Реализация, целевые доказательства и полный core приняты в scope;
результат нового CI ожидается. Приёмка владельца/выпуск не засчитаны.

## Передача

- Кодовый SHA: 6f4d9479ab1f75e9a7c5b1ada8dfba260a13c8ca; CAPPED обе записи в этом commit.
- Полный runner: 692b006f788c14e6a8e74f8429ec8ee63f60db02511469e64946fccd46be3b21,
  только2 байта z→r; свежие512 bases, старые roots не тронуты. STOP/retained Popen/native
  singly/max4/codec/clean-SHA guards сохранены.
- Последний доказанный: full58/58 green, independent aggregate, exact remote ref и новый CI.
- Первый несделанный: итог CI43388477627, затем оставшиеся Win3.11/browser blockers.
- Финальные документы и CAPPED:319passed в каждом codec, final-meta-*.xml.
- Cleanup: первый audit-only отказал CIM в sandbox,0PID proofs/0root scans; после
  изменения доступа elevated audit подтвердил60PID absent/58exact paths. Apply exit0
  удалил30plain roots (отсутствие проверено отдельно),20reparse сохранены,8уже отсутствовали.
  Ошибок0, unknown targets не обходились; оба helper реально завершились, процессов не убивали.
  Receipt temp-audit-20261113T0755413957708Z.json SHA256:
  4c52c6953bfda3f7b83a58d79b26be759461fe30708303f494b2e41037afd159.
- Последний остаток12%, порог10%; никаких новых моделей или повторного цикла.
- Не повторять: старый CI run/модели/живой цикл; сохранённые красные диагностические запуски
  не закрывать одним зелёным повтором. Полный core green разрешает новый candidate CI.
