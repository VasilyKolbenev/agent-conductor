# Отчёт по задаче: S-R4-2. Закрыть пробелы G1–G3, G5–G7 (только тесты)

- Исполнитель: Claude Code / Sonnet 5.5. Код продукта не менялся.
- Исходный commit и ветка: `57fe629`, `recovery/2026-10-20`. Основа задания: отчёт R4
  (`R4-PUSH-PR-RECONCILIATION.md`, раздел 9, S-R4-2; сверка велась на `4d0e3af`).
- Состояние рабочей копии до изменений: на старте были `M src/conductor/command/adapters/process.py`,
  `M tests/test_execution_boundary.py` (R1.1) и `?? docs/recovery/2026-10-20/tasks/` (отчёты). Эти
  файлы я не трогал; к концу работы они уже лежат в коммитах `63daddb` и `57fe629` другого
  исполнителя, а в рабочей копии, кроме моих файлов, осталось только
  `?? docs/recovery/2026-10-20/tasks/R3-DESK-MOTION-BRIEF.md`.
- Цель и наблюдаемое ожидаемое поведение: характеризационные тесты на пробелы G1, G2, G3, G5, G6,
  G7 из раздела 8 отчёта R4. Все новые тесты зелёные на текущем коде. G4 (ждёт В1) и G8 (ждёт
  В4) не делались.

## Изменения

Только тесты, четыре файла, 117 добавленных строк и одна изменённая (импорт). Существующие assert'ы
не ослаблялись, фикстуры не дублировались: везде использованы `accepted_with_gh`, `confirm`,
`digest_of`, `terms`, `verbs`, `stands`, `pushed`, `press`, `move_branch`, `made`, `keys`, `row_of`
и `rig`, `opened`, `live`, `statuses`, `said`.

| ID | Файл | Тест | Что проверяет |
| --- | --- | --- | --- |
| G1 | `tests/test_accept_push_reconcile.py` | `test_a_press_that_only_checks_finds_another_commit_there_and_rejects_with_no_push` | `check:true`, на remote другой коммит: 409 `push_rejected`, `verbs == ["ls-remote"]`, ref остался прежним, `push.json` нет |
| G2 | там же | `test_a_press_that_only_checks_and_gets_no_answer_from_its_look_asks_no_push[no_answer, cannot_sign_in]` | `check:true`, look молчит: `push_unconfirmed`; look не смог войти: `push_auth_failed`. В обоих `verbs == ["ls-remote"]`, на remote ничего нет, записи нет |
| G3 | `tests/test_accept_push_guard.py` | `test_a_press_that_only_checks_is_refused_as_changed_terms_before_any_look` | Имя guard занято после показа условий: `check:true` со старым digest даёт `push_terms_changed`, ни одного `ls-remote` и `push`, bare пуст. С обновлённым digest та же проверка делает ровно один `ls-remote` и отвечает 200 `{"push": null}` (отказ был из-за условий, а не из-за самой проверки) |
| G5 | `tests/test_desk_accept_publish.py` (Node), EN и RU | `test_a_pull_request_that_differs_in_base_or_repository_is_said_to_differ_and_not_to_move` | Запись PR с mismatch при совпадающем `head_oid` (другая base; форк): единственный status-текст это `desk.accept.pr.differs`, текста `desk.accept.pr.moved` нет, `live()` пусто, номер показан, запросов нет |
| G6 | `tests/test_accept_pull_request.py` | `test_a_deleted_branch_with_only_another_pull_request_listed_records_that_one_as_it_is[2 строки x check/plain]` | Ref удалён (`remote_oid is None`), в списке только чужой PR (другая base или другой head): 200, mismatch равен `{head_oid, base, cross_repository:false}` из строки списка, `record.base` берётся из нажатия, `gh pr create` не вызывался, запись видна в `GET /accept`, повтор не читает список |
| G7 | там же | `test_a_create_whose_number_the_list_does_not_show_records_nothing_and_is_not_repeated` | `gh pr create` вернул номер 7, которого в списке ещё нет: 409 `pr_create_failed`, `pr.json` нет, `GET` показывает `null`. Следующее нажатие находит PR 7 в списке и записывает (200, `mismatch: null`); всего `gh pr create` один раз |

Побочная правка: в `test_accept_pull_request.py` в импорт из `tests.accept_remote` добавлен
`remote_oid`; строка разбита по лимиту 100 символов.

Размеры файлов после правки: reconcile 351, guard 261, pull_request 470, desk_accept_publish 756
строк. Предел 800 не достигнут, новых модулей не создавалось. Самая длинная строка: 100 символов.

## Проверки

Каждая команда выполнялась после `. ...\December-Command-Environment.ps1 -Quiet`. Среда: Windows 11,
Python 3.12.14, git 2.53.0.windows.3. Сети нет: remote это bare-репозиторий на диске, gh это
скриптовая фальшивка.

| Команда | Результат | Что доказывает |
| --- | --- | --- |
| `python -m pytest -q --tb=short -p no:cacheprovider --basetemp ...\work\pt-s5a tests/test_accept_push.py tests/test_accept_push_guard.py tests/test_accept_push_reconcile.py tests/test_accept_pull_request.py` | **165 passed**, 0 failed, 0 skipped, 417.82 s (было 156; +9 = G1 1, G2 2, G3 1, G6 4, G7 1) | Серверные контракты push/PR на настоящем git, новые тесты зелёные |
| `... --basetemp ...\work\pt-s5b tests/test_desk_accept_publish.py tests/test_desk_transport_accept_publish.py tests/test_desk_accept_terminal.py` | **54 passed**, 9.60 s (было 52; +2 = G5 EN и RU) | Карточка под Node |
| `... --basetemp ...\work\pt-s5c tests/test_command_line_cap.py -k accept` | **11 passed**, 133 deselected | Лимит 100 символов для файлов reconcile, guard, pull_request |
| `git diff --stat` | 4 файла, 117 insertions(+), 1 deletion(-): pull_request 50, guard 19, reconcile 24, desk_accept_publish 25 | Diff ограничен названными файлами |
| `git status --short` | `M` на четырёх файлах из задания, `?? docs/recovery/2026-10-20/tasks/R3-DESK-MOTION-BRIEF.md` (чужой), плюс этот отчёт | Чужих файлов не затронуто |

Файл `tests/test_desk_accept_publish.py` в списке `CAPPED` у `test_command_line_cap.py` не значится,
поэтому проверка (c) его не охватывает. Длина строк в нём проверена отдельно скриптом: максимум 100,
превышений нет. Включить файл в `CAPPED` я не стал: задание ограничивало набор файлов.

### Проверка, что тесты краснеют при нарушении свойства

Копия `src` и `tests` лежала вне репозитория (`work\mut-s5`, `PYTHONPATH` на её `src`, подтверждено
печатью `conductor.__file__`); после прогонов копия удалена. Продукт в репозитории не менялся.

M4 и M5 применялись вместе в одном прогоне `tests/test_accept_pull_request.py` (они меняют разные
функции, `_moved` и `_create`); остальные мутации по одной.

| Мутация (в копии) | Что красное | Что осталось зелёным |
| --- | --- | --- |
| M1. `_send`: `if seen is not None and not request.check:` (проверка не замечает чужой коммит) | G1: получен 200 `{"push": null}` вместо 409 | существующий тест на обычное нажатие (`reconcile:113-119`) зелёный, то есть G1 закрывает именно проверку |
| M2. `_send`: первый `_look` при `check` глотает `PublishRefused` и считает ref отсутствующим | оба варианта G2: 200 вместо 409 | G1, обычное нажатие с молчащим look (`reconcile:105-110`): зелёные |
| M3. `_answer`: digest не сверяется при `check` | G3: 200 `{"push": null}` вместо 409 `push_terms_changed` | существующие `taken_after` и `freed_after` (обычное нажатие) зелёные |
| M4. `_moved`: без собственного PR в списке отказывает `remote_head_moved` вместо записи строки списка | все 4 варианта G6 (409 вместо 200); заодно 5 существующих тестов с чужой строкой | G6 здесь не единственный страж, но единственный для удалённого ref |
| M5. `_create`: если номер от gh известен, а списка в нём нет, строится синтетическая запись | G7: 201 вместо 409 | **все существующие тесты выбранного набора зелёные** (в них gh падает с `exit=1`, номер неизвестен, ветка не достигается), то есть G7 закрывает реальный пробел |
| M6. `desk-accept-host.js` `prRecord`: условие `moved` всегда истинно | G5 EN и RU: текст «moved» вместо «differs», `moved: true` | существующие тесты записи с перемещённой головой зелёные |

## Не проверено

- Не запускались: полный suite, `browser_tests/`, нативные AppContainer-тесты (по заданию). Из
  раздела 2 R4 это `browser_tests/test_desk_accept_publish.py` (8 passed в R4); моими изменениями
  он не затрагивается (изменены только Python- и Node-тесты, страница и продукт не менялись).
- Git 2.56 (эффект guard name на tracking ref), настоящие GitHub и gh, Linux и macOS: как и в R4,
  не проверялись. Тест G3 проверяет условие и команду, эффект на tracking ref он по-прежнему не
  показывает.
- G4 (смена actor в фазе `unknown`, ждёт В1) и G8 (500 `store_error`, ждёт В4/O2) намеренно не
  сделаны. Браузерный сценарий с перемещённой головой по-прежнему отсутствует (приоритет низкий).
- Новых расхождений с продуктом не найдено: все 11 новых тестов зелёные на текущем коде.

## Ревью Codex

Статус: ожидает. Заполняется после независимого чтения diff и необходимых проверок.

## Передача

- Итоговый commit: нет, коммит не создавался.
- `git status --short`: `M tests/test_accept_pull_request.py`, `M tests/test_accept_push_guard.py`,
  `M tests/test_accept_push_reconcile.py`, `M tests/test_desk_accept_publish.py`,
  `?? docs/recovery/2026-10-20/tasks/R4-S2-REPORT.md`, а также чужие
  `M tests/test_command_flow_driver.py` (R1.2, появилось в конце моей работы; мой `git diff --stat`
  из 4 файлов и 117 строк снят до этого) и `?? docs/recovery/2026-10-20/tasks/R3-DESK-MOTION-BRIEF.md`.
- Обновлённые документы: этот отчёт. Отчёт R4 и спецификация не менялись.
- Следующий конкретный шаг: Codex читает diff четырёх тестовых файлов и принимает или возвращает
  замечания; G4 и G8 выдавать после решений по В1 и В4. По желанию Codex: включить
  `tests/test_desk_accept_publish.py` в `CAPPED` в `tests/test_command_line_cap.py`.
- Временные файлы вне репозитория: каталог `work\pt-s5a` (можно удалить); копия `work\mut-s5` и
  остальные `pt-s5*` удалены.
