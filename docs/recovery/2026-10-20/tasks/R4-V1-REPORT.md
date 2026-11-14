# Отчёт по задаче: S-R4-V1. Проверка исхода называет подписанта исходного нажатия

- Исполнитель: Claude Code / Sonnet 5.5. Код продукта изменён: одна строка логики в
  `src/conductor/panel/desk-accept-host.js` (функция `send`) и комментарий к ней. Сервер, схемы
  записей и тексты EN/RU не менялись.
- Основание: решение владельца R4-V1 от 21.10.2026 (`OPEN-DECISIONS.md`, строка 15): в
  `requested_by` записывается тот, кто подтвердил исходное нажатие (`state.signer`), а не тот, кто
  нажал «Проверить снова». Проект: `tasks/R4-V1-DESIGN.md`, раздел 8, с поправками скептика
  (см. ниже).
- Ветка `recovery/2026-10-20`. Работа начата на `6932cfd`; во время работы HEAD стал `3a64fbe`
  (чужой docs-коммит: `OPEN-DECISIONS.md`, `H5-V1-REPORT.md`, `CODEX-REVIEW-H5-6932cfd.md`). Файлы
  этой задачи он не менял. Коммит не создавался.
- Наблюдаемое поведение. Проверка (`check:true`) шлёт `actor` из `push.signer` или `pr.signer`, кто
  бы ни сидел за столом; обычное нажатие по-прежнему шлёт текущего `actor`. Тело проверки равно
  телу подтверждённого нажатия плюс `check:true`. Без человека за столом проверка по-прежнему
  недоступна (`writable` не тронут).

## Изменения

| Файл | Что |
| --- | --- |
| `src/conductor/panel/desk-accept-host.js` | `send`: `const signer = check ? (step === "push" ? push : pr).signer : actor;`, затем `stepBody(step, signer, check)`; комментарий у `newPush`/`newPr` и у `send`. Диф: +4 −2, файл 714 строк (лимит 800) |
| `tests/test_desk_accept_publish_signer.py` | Два assert'а, закреплявшие старое поведение (`actors` в строках 42 и 96), теперь `["Owner", "Owner", "Other"]` и `[None, "Owner", "Owner", "Other"]`; абзац в docstring; 10 новых Node-тестов (с тестом на мутант M6 после ревью). Было 123 строки, стало 314, строки не длиннее 100 |
| `docs/specs/2026-08-13-cockpit-command-api.md` | Строка 1409 заменена тремя (длины 94, 94, 75), см. ниже. Диф: +3 −1 |
| `tasks/R4-V1-DESIGN.md` | Правки «после скептика»: раздел 0 (п. 5), раздел 3, раздел 5 (новый O-V1-3), раздел 6 (формулировка) |

Фраза в спецификации (после скептика: только тело запроса и запись, которую пишет сама проверка):

```
A press with `"check":true` carries the body of the press it looks for, `actor` included,
whoever asks to look; a record that the look writes names that actor in `requested_by`.
```

(в файле она перенесена по ширине и стоит перед «After the body, the push answers»). Прежняя
формулировка из проекта («запись, которую она находит, называет подтвердившего то нажатие»)
обещала лишнее: найденная запись может назвать другого (O-V1-1, O-V1-3).

## Тесты (Node, настоящий хост с фальшивой дверью)

Новые 9 тестов в `tests/test_desk_accept_publish_signer.py`. Два теста G4 (push и PR) взяты из
проекта дословно, остальные — из проб скептика
`work\sk-r4v1\tests\test_sk_r4v1_probe.py` (11 Node-проб), с именами по образцу модуля:

| Тест | Что закрепляет |
| --- | --- |
| G4 push, G4 PR | Other за столом нажимает проверку дважды: тело = тело подтверждения + `check:true`, `actor: Owner` оба раза (второй раз закрепляет, что проверка не перезаписывает `signer`) |
| every_check_names_the_signer… | Owner → Other → никого → Owner → Third: каждая проверка несёт Owner; при пустом столе проверки нет |
| check_after_send_again… | «Снова» нажал Owner, проверку нажал Other: Owner |
| check_names_the_new_signer… | Other подтвердил новое нажатие после «absent», проверку нажал Owner: Other |
| final_refusal_to_a_check… | Окончательный отказ на проверку возвращает к review; следующее нажатие называет Other |
| pull_request_that_follows_a_push… | Push найден проверкой Other; следующий шаг (PR) подписывает человек за столом |
| standing_pull_request_naming_someone_else… | Стоящая запись PR с `requested_by: Other` остаётся записью, которую искала проверка Owner (UI `requested_by` не сверяет; это граница O-V1-3, а не защита) |
| check_after_a_change_of_language… | Смена языка и человека за столом: тело проверки то же, что у подтверждённого нажатия |

## Красный на текущем коде (до правки продукта)

Сначала изменены два assert'а и дописаны все 9 тестов, продукт не тронут:
`python -m pytest ... tests/test_desk_accept_publish_signer.py` дал **10 failed, 3 passed**.
Красные: оба изменённых старых теста (`actor: "Other"` в теле проверки вместо `"Owner"`) и 8 новых.
Зелёными остались два нетронутых старых теста и тест про стоящий PR (он описывает поведение,
которое не меняется). После правки: **13 passed**.

## Мутанты (на копии `C:\Users\Пользователь\Documents\Codex\work\r4v1-s\`, не в репозитории)

Копия: `src`, `tests`, `pyproject.toml`; `PYTHONPATH` на копию; после каждого мутанта файл
возвращён (хэш до и после совпал). Прогон: модуль signer, 13 тестов.

| Мутант | Замена | Результат |
| --- | --- | --- |
| M0 (= поведение до правки) | `const signer = actor;` | 10 failed, 3 passed |
| M1 | проверка перезаписывает `signer`: `...confirmed(step)` всегда | 5 failed (оба G4, `every_check…`, два старых теста про «Other» по review) |
| M2 | подписант проверки только у push | 4 failed (G4 PR, старый PR-тест, `final_refusal`, `language`) |
| M3 | подписант проверки только у PR | 6 failed (G4 push, старый push-тест, `every_check`, `send_again`, `new_signer`, `pull_request_that_follows`) |
| Проверка проверки «снова от текущего actor» | = M0 | G4 красный (см. M0) |

Мутант `state.signer ?? actor` эквивалентен и не считался: в фазе `unknown` `signer` всегда задан.

## Серверная половина договора: не добавлена в репозиторий

(Устарело после ревью Opus: оба теста добавлены в `tests/test_accept_push.py` и
`tests/test_accept_pull_request.py`, см. «Правки после ревью Opus» ниже.)

Проект (раздел 8, шаг 2) предлагал два характеризационных теста на сервер
(`tests/test_accept_push_reconcile.py` и `tests/test_accept_pull_request.py`): «проверка пишет
`requested_by` из своего тела, повтор от этого имени получает стоящую запись». В список файлов этой
задачи они не входят, поэтому в репозитории я их **не добавлял**. На копии
`work\r4v1-s\` я проверил их текст из проекта:

| Проверка | Результат |
| --- | --- |
| Оба теста на неизменённом сервере | 2 passed |
| S1 (`accept_push._record` пишет `commit["requested_by"]`) | тест push красный |
| S2 (`accept_pull_request._record` пишет `push["requested_by"]`) | тест PR красный |
| S3 (`accept_push._repeat` не сверяет actor) | тест push красный |
| S4 (`accept_pull_request._repeat` переписывает запись на actor повтора) | тест PR красный |

Тем самым фраза спецификации («a record that the look writes names that actor») сейчас
закреплена только таким прогоном на копии; в репозитории её держит серверный код. Добавить оба
теста можно по решению оркестратора, это ещё два файла (CAPPED уже включает оба).

## Проверки в репозитории

Каждая команда выполнялась после `. ...\December-Command-Environment.ps1 -Quiet`, pytest с
`-p no:cacheprovider --basetemp C:\Users\Пользователь\pt-<суффикс>`. Среда: Windows 11, git 2.53.0.
Сети нет: remote — bare-репозиторий на диске, gh — скриптовая фальшивка.

| Команда | Результат |
| --- | --- |
| `tests/test_desk_accept_publish.py tests/test_desk_transport_accept_publish.py tests/test_desk_accept_terminal.py tests/test_desk_accept_publish_signer.py tests/test_desk_accept_host.py` | **79 passed**, 12.9 с |
| `tests/test_studio_source.py tests/test_desk_copy.py tests/test_desk_flag_door_source.py tests/test_studio_module_graph.py` | **28 passed** (лимит 800 строк, запрещённые слова, граф модулей) |
| `tests/test_accept_push.py tests/test_accept_push_guard.py tests/test_accept_push_reconcile.py tests/test_accept_pull_request.py` | **169 passed**, 724.7 с (без новых серверных тестов; по отчётам это 168 после S-R4-1 плюс тест Opus из ревью). Число `push` и `gh pr create` ни в одном сценарии не выросло |
| `browser_tests/test_desk_accept_publish.py` (отдельный процесс) | первый прогон (параллельно шёл серверный набор и чужие прогоны): **2 failed, 6 passed**, оба красных — RU-варианты `…whose_answer_is_not_known_is_checked_and_created_only_once[ru]` и `…not_github_gets_the_terminal_command_and_no_step[ru]`, в снимке «Ждём ответ сервера…». Повтор тех трёх RU-тестов: 3 passed. Два полных повтора модуля после окончания серверного набора: **8 passed** (122 с) и **8 passed** (99 с) |
| `tests/test_command_line_cap.py -k accept` | **11 passed**, 141 deselected |
| `tests/test_file_endings.py` | **9 passed** |
| Ручная проверка `desk-accept-host.js`, signer-модуля, спецификации: строки ≤ 100, без хвостовых пробелов, один `\n` в конце | все чисты; в спецификации диф ≤ 100 |

Про два красных в первом прогоне браузера. Причина не установлена, и объяснять её «нестабильностью»
я не стал. Известно: в тех же сценариях проверку нажимает тот же человек, что подтверждал
нажатие, поэтому тело проверки правкой не меняется; прогон шёл параллельно с двенадцатиминутным
серверным набором (и, возможно, с чужими прогонами на той же машине); те же тесты затем прошли
отдельно и в полном модуле. Если красные вернутся на тихой машине, это расхождение для разбора, а не шум.

## Критерии приёмки

- На текущем коде модуль signer красный (10 failed: 2 изменённых assert'а и 8 новых), после правки
  зелёный (13 passed). Выполнено.
- Тело проверки равно телу подтверждённого нажатия плюс `check:true`, в том числе при другом
  человеке за столом; «снова» после review подписывает текущий человек (старые тесты про
  `Other` на review зелёные). Выполнено.
- Число `push` и `gh pr create` не растёт (серверный набор 169 passed, сервер не менялся);
  серверный код не изменён. Выполнено.
- Мутанты M0–M3 убиты. Серверные S1–S4 убиты на копии, в репозитории тестов для них нет.
- `git diff --stat`: три файла (спецификация, `desk-accept-host.js`, signer-тест) и новый
  неотслеживаемый `R4-V1-DESIGN.md`. Не пять файлов из проекта: два серверных теста не добавлены.
  (После ревью Opus добавлены ещё `tests/test_accept_push.py` и `tests/test_accept_pull_request.py`;
  S1 и S2 теперь убиты тестами репозитория.)

## Что решение не покрывает

Решение владельца 21.10 («в `requested_by` пишется подтвердивший исходное нажатие») выполнено в
пределах того, что один клиент знает сам. Остаётся за границей:

- **Две вкладки или перезагрузка (O-V1-1, push).** Вкладка A: Owner, исход `unknown`. Вкладка B
  или перезагрузка: Other сделал полное нажатие, сервер записал push с `requested_by: Other`.
  Проверка из A несёт Owner и получает 409 `acceptance_exists`; карточка считает это
  окончательным отказом, кнопки «Обновить» при стоящем commit нет. Если за столом A сел Other,
  на HEAD проверка шла от Other и получала 200 («Sent to GitHub»); с правкой она идёт от Owner и
  получает 409, карточка уходит в `idle` с «This run already has another confirmed acceptance.»,
  и только полный повтор от Other получает 200. До правки 409 был лишь тогда, когда за столом A
  сидел не тот, кто записал push; теперь он при любом человеке. Это граница решения владельца
  (код не менялся); формулировки «так было и до правки» и «после правки реже» сняты.
- **То же для PR (O-V1-3, добавлено после скептика).** Проверка из A несёт Owner, `_repeat` у PR
  actor не сверяет (`accept_pull_request.py:148-152`, spec 1490-1491), ответ 200 со стоящей записью,
  где назван Other; UI принимает её (`recordFits` `requested_by` не сверяет). Запись называет не
  подписанта проверки. Правка этого не ухудшает: старая проверка из вкладки A при Owner за столом
  дала бы то же самое.
- Без серверного pending-signer (вариант В проекта, отвергнут для V1) это не чинится. Утверждение
  «Решения это не нарушает» из раздела 3 проекта снято для двух вкладок и перезагрузки.
- **O-V1-2.** Карточка в фазе `unknown` не говорит, чьё имя запишет проверка; текст не добавлялся
  (по заданию, тексты EN/RU не менялись).
- После перезагрузки фазы `unknown` и `signer` нет; проверки тоже нет, следующее действие — новое
  полное нажатие, и запись называет его подтвердившего.

## Не проверено

- Полный suite, нативные AppContainer-тесты, Linux и macOS, настоящие GitHub и gh: не запускались.
- Два вкладки и перезагрузка с настоящим сервером в Chromium: не воспроизводились, только
  разбор кода и Node-тест на границу O-V1-3 (стоящая запись с другим именем).
- Причина двух красных RU-прогонов браузера при параллельной нагрузке (см. выше).
- Серверные тесты и мутанты S1–S4 были на копии вне репозитория; после ревью Opus тесты в
  репозитории, а S1 и S2 повторены на новой копии (S3 и S4 не повторялись).

## Правки после ревью Opus

Диагностика ревьюера, каталог `C:\Users\Пользователь\Documents\Codex\work\rv-r4v1b\`: файлы
`copy\tests\test_rv_probe.py`, `mutants.py`, `server_tests.py`. Код продукта не менялся, кроме
текста комментария.

1. **Граница O-V1-1 описана точно** (`R4-V1-DESIGN.md` раздел 5, этот отчёт, раздел «Что решение
   не покрывает»). Формулировки «так было и до правки» и «после правки этот случай реже» сняты:
   на деле граница шире. Вкладка A: Owner, исход `unknown`; во вкладке B Other записал
   `push.json`; за столом A сел Other. На HEAD проверка шла от Other и получала 200 («Sent to
   GitHub»); с правкой идёт от Owner и получает 409 `acceptance_exists`, карточка уходит в `idle`
   с «This run already has another confirmed acceptance.», затем полный повтор от Other получает
   200. До правки 409 был только если за столом A сидел не тот, кто записал push; теперь при
   любом человеке. Это граница решения владельца; код не менялся.
2. **Проба ревьюера в `tests/test_desk_accept_publish_signer.py`:**
   `test_a_pr_check_names_the_pr_signer_even_when_another_person_signed_the_push` (Owner сделал push,
   Other создаёт PR с исходом `unknown`, Owner жмёт проверку: `actor` проверки PR = Other).
   Docstring модуля: вместо «the record it finds names that person» стоит «a record it writes
   names that person», как в спецификации.
3. **Серверные характеризационные тесты** (проект, раздел 8, шаг 2). Проверка `check:true` с
   `actor` (Signer), отличным от `requested_by` коммита и push (Owner), пишет запись с
   `requested_by` = Signer. Тексты взяты из `server_tests.py` ревьюера; добавлены docstring и
   assert, что `requested_by` коммита (push) в самом деле Owner.
   - `tests/test_accept_push.py`:
     `test_a_check_writes_the_signer_its_body_names_and_the_signers_repeat_gets_that_record`.
     Повтор Signer, с проверкой и без, получает ту же запись (200); проверка Other получает 409
     `acceptance_exists`; `push` ушёл один раз.
   - `tests/test_accept_pull_request.py`:
     `test_a_check_after_an_unknown_creation_writes_the_signer_its_body_names`.
     Повтор получает ту же запись (200; у PR `_repeat` actor не сверяет); `gh pr create` один.
4. **Комментарий в `desk-accept-host.js` (`send`):** «never the person at the desk now» заменено
   на «not whoever sits at the desk now». Логика не тронута.

Красное и зелёное. Копия вне репозитория (`git archive HEAD` плюс четыре изменённых файла):
`C:\Users\Пользователь\Documents\Codex\work\r4v1-rv2\copy`. Скрипт мутантов лежит в scratchpad
сессии. После каждого мутанта файл возвращён и сверен (host restored: True, server restored: True).

| Вариант | Проба ревьюера | Модуль signer (14 тестов) |
| --- | --- | --- |
| Хост с правкой | 1 passed | **14 passed** |
| M6 (`push.signer ?? pr.signer`) | **1 failed** | 1 failed, 13 passed |
| Хост как в HEAD | **1 failed** | 11 failed, 3 passed |
| M0 (`signer = actor`) | 1 failed | 11 failed, 3 passed |

| Серверный вариант | `-k writes_the_signer` (2 теста) |
| --- | --- |
| Без мутанта | 2 passed |
| S1 (`accept_push` пишет `commit["requested_by"]`) | тест push **красный**, тест PR зелёный |
| S2 (`accept_pull_request` пишет `push["requested_by"]`) | тест PR **красный**, тест push зелёный |

Прогоны в репозитории (после `Environment.ps1 -Quiet`, `-p no:cacheprovider`, свой `--basetemp`
`pt-r?`; каталоги удалены):

| Команда | Результат |
| --- | --- |
| Четыре Node-модуля: signer, publish, transport, terminal | **68 passed**, 12.9 с |
| `test_accept_push.py`, `test_accept_push_guard.py` | **63 passed**, 157 с |
| `test_accept_push_reconcile.py` | **32 passed**, 236 с |
| `test_accept_pull_request.py` | **76 passed**, 313 с |
| `test_command_line_cap.py -k accept` | **11 passed**, 141 deselected |
| `test_file_endings.py` | **9 passed** |

Три серверные группы шли параллельно в отдельных процессах: 63 + 32 + 76 = 171 = 169 прежних
плюс два новых. Сервер не менялся.

Ошибка по ходу. Первая вставка серверного теста в `tests/test_accept_push.py` попала внутрь
последнего старого теста: чтение файла по диапазону не показало его настоящую последнюю строку
(320), и новый тест встал перед ней. Первый же прогон дал 409 вместо 200 в чужой строке. Строка
возвращена на место, `git diff --numstat` по двум серверным файлам: 30 и 21 добавленная строка,
удалений нет.

## Ревью Codex

Статус: ожидает. Нужно прочитать дифф (`desk-accept-host.js`, signer-тест, спецификация и после
ревью Opus два серверных теста в `tests/test_accept_push.py` и `tests/test_accept_pull_request.py`)
и оценить O-V1-1/O-V1-3 как оставшуюся границу решения (O-V1-1 шире, чем писалось сначала).

## Передача

- Итоговый commit: нет, коммит не создавался. Push, stash, checkout, reset не выполнялись.
- Файлы линии R4-V1 в `git status --short`: `M docs/specs/2026-08-13-cockpit-command-api.md`,
  `M src/conductor/panel/desk-accept-host.js`, `M tests/test_desk_accept_publish_signer.py`,
  `M tests/test_accept_push.py`, `M tests/test_accept_pull_request.py` (последние два после
  ревью Opus), `?? docs/recovery/2026-10-20/tasks/R4-V1-DESIGN.md` и этот отчёт
  (`R4-V1-REPORT.md`); файлы линии R1.6 стоят в статусе отдельно.
- Модули для CAPPED: `tests/test_desk_accept_publish_signer.py` (314 строк, строки ≤ 100) не в
  `CAPPED`; `tests/test_command_line_cap.py` в этой задаче не правился. Решает оркестратор (тот же
  вопрос, что R4-G).
- Временные файлы вне репозитория: `C:\Users\Пользователь\Documents\Codex\work\r4v1-s\` и
  `...\work\r4v1-rv2\` (копии для мутантов; можно удалить). Мои каталоги `pt-r1` … `pt-rc`, а
  после ревью Opus `pt-s1`, `pt-s2`, `pt-ra` … `pt-re`, `pt-mh`, `pt-ms` удалены.
