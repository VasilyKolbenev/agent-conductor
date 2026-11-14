# R4-V1. Чьё имя проверка пишет в `requested_by`: проект изменения и задание для Sonnet

- Исполнитель: Claude Code / Opus 5.5. Режим только чтения. Единственный изменённый файл в
  репозитории — этот документ.
- Дата: 21 октября 2026. Ветка `recovery/2026-10-20`, HEAD `6932cfd`, рабочая копия чистая.
  Номера строк ниже указаны по `6932cfd`.
- Основание — решение владельца R4-V1 от 21.10.2026 (`OPEN-DECISIONS.md`, строка 15): в
  `requested_by` записывается тот, кто подтвердил исходное нажатие (`state.signer`), а не тот, кто
  нажал «Проверить снова». Контекст: `tasks/R4-PUSH-PR-RECONCILIATION.md`, В1 (раздел 10) и G4
  (раздел 8).

## 0. Выжимка

1. Сервер берёт `requested_by` **из тела запроса**, из поля `actor`, и при проверке (`check:true`)
   тоже (`accept_push.py:278`, `accept_pull_request.py:283`). Своей памяти о том, кто подтвердил
   нажатие, у сервера нет: для push и PR не пишется ни intent, ни журнал, а до `push.json` или
   `pr.json` на диске о нажатии ничего не хранится. Сессия и заголовки имя не подменяют.
2. UI хранит подписавшего в `push.signer` и `pr.signer`. Его ставит `confirmed()`
   (`desk-accept-host.js:355-356`) при нажатии, которое действует; проверка его не трогает
   (`:360-361`). Но тело проверки строится от **текущего** `actor` (`:358`). Поэтому, если в фазе
   `unknown` за стол сел другой человек, проверка уходит от его имени и найденная запись называет
   его.
3. У PR ситуация та же: тот же `send` и та же строка `:358`. Разница одна: `_repeat` у PR не
   сверяет actor (`accept_pull_request.py:148-152`), поэтому 409 `acceptance_exists` у PR не
   бывает.
4. **Минимальное изменение — одна строка UI:** проверка отправляет `state.signer`, обычное нажатие
   — текущего `actor`. Сервер, схемы записей, digest и словарь отказов не меняются. Прототип на
   копии: G4 красный на HEAD и зелёный с правкой. Ломаются ровно два assert'а,
   `tests/test_desk_accept_publish_signer.py:42` и `:96`: они закрепляют старое поведение. Все
   остальные Node-тесты и проверки исходников зелёные, мутанты убиты (раздел 7).
5. После перезагрузки страницы фазы `unknown` и `signer` нет, и восстановить их не из чего. Но и
   проверки после перезагрузки нет: следующее действие — новое полное нажатие с review, и запись
   называет того, кто его подтвердил; его имя стоит в тексте подтверждения. Это граница решения,
   а не нарушение. Серверный pending-signer отвергнут как не минимальный (раздел 4).
   **Поправка после скептика:** это верно для одной вкладки. Если же в другой вкладке (или после
   перезагрузки) исходное нажатие уже повторил другой человек, проверка из первой вкладки
   называет прежнего подписанта, а запись называет другого: см. O-V1-1 (push) и O-V1-3 (PR) в
   разделе 5.
6. В спецификацию нужна одна фраза (раздел 6). Задание для Sonnet — в разделе 8.

## 1. Откуда берётся `requested_by`

### 1.1 Сервер

| Место | Что там |
| --- | --- |
| `accept_push.py:66-85` | Тело подтверждения: ровно `acceptance_id, remote, push_digest, actor` и необязательный `check:true`. `actor` проверяется только как `human_identity` (`authorization_terms.py:41-47`): непустой текст в UTF-8. Ни с сессией, ни с чем-либо ещё он не сверяется |
| `accept_push.py:107-114` | Под `publish_lock`: если `push.json` уже есть — `_repeat`; иначе пересчёт условий, сверка digest и `_send` |
| `accept_push.py:117-123` | `_repeat`: другой digest → `push_terms_changed`, **другой actor → `acceptance_exists`**, иначе стоящая запись |
| `accept_push.py:140-144` | Digest считается от `acceptance_id, commit, remote, push_url, repo, ref, command`. **`actor` в digest не входит** |
| `accept_push.py:224-232` | `_send`: первый look. Тот же коммит → `_record` и 201, в том числе для проверки; другой коммит → `push_rejected`; ref нет и `check` → 200 `{"push": null}` без push |
| `accept_push.py:273-279` | `_record`: `"requested_by": request.actor`, то есть имя из тела |
| `accept_pull_request.py:109-122` | Тело PR; `actor` тоже проверяется только как `human_identity` |
| `accept_pull_request.py:141-145, 148-152` | Стоящая запись отдаётся любому нажатию с той же `base`; **actor не сверяется** |
| `accept_pull_request.py:155-166` | Проверка до создания: найденный собственный PR записывается (200); `check` без PR → 200 `null` |
| `accept_pull_request.py:187-202` | `_moved`: при сдвинутой голове найденный PR записывается любым нажатием, проверкой тоже |
| `accept_pull_request.py:273-284` | `_record`: `"requested_by": request.actor` |
| `accept_records.py:18-26, 51-58` | Схемы `push.json` и `pr.json`: `requested_by` — любое `human_identity`. Поля «кто подтвердил исходное нажатие» нет |
| `accept_store.py`, `accept_commit.py:71-100` | Intent (`intent-<digest>.json`) есть только у commit; у push и PR его нет |

Вывод: сервер служит проводником и записывает то имя, которое пришло в `actor`. Проба R4
`work\r4probe\test_r4_probe.py::test_probe_a_check_by_another_person_writes_that_person_as_requested_by`
это показала: Other нажал проверку → `requested_by: "Other"`; точный повтор от Owner → 409
`acceptance_exists`.

### 1.2 UI (`src/conductor/panel/desk-accept-host.js`)

| Место | Что там |
| --- | --- |
| `:46-52` | `newPush()` и `newPr()` начинают с `signer: null`; у PR есть ещё `fields` |
| `:107-116` | `reviewAgain` и `unconfirm`: при смене actor (`sync`, `:189-190`) фаза `absent` уходит на review, **фаза `unknown` остаётся** (меняется только `confirming`) |
| `:249` | `writable`: нажимать можно только тогда, когда за столом названный человек (`Boolean(actor)`) |
| `:319-335` | `stepBody(step, signer, check)`: тело — то, что показано и подтверждено (`push.terms` или `pr.fields`), с `actor: signer` и, для проверки, `check:true` |
| `:340-345` | `mayPress`: проверка возможна только в фазе `unknown` |
| `:354-356` | `confirmed(step)`: `{signer: actor}`, у PR ещё `fields` |
| **`:358`** | **`body = stepBody(step, actor, check)`: для проверки тоже берётся текущий `actor`** |
| `:360-361` | Проверка не перезаписывает `signer` (`...(check ? {} : confirmed(step))`) |
| `:384-389` | `settleAbsent`: «снова» предлагается только тому же `signer`, другому человеку — review |
| `:390-406` | `settle`: подходящая запись попадает в `facts[key]`, фаза становится `idle` |
| `:633-635, 675-677` | В фазе `unknown` единственная кнопка — `desk.accept.check` |

Значит, `state.signer` у UI есть и живёт ровно столько, сколько фаза `unknown` в этой вкладке. В
фазе `unknown` он никогда не равен `null`: туда попадают только через `send` без `check`, а он
ставит `signer`; проверки его не меняют.

Старое поведение закрепляют существующие тесты:
`tests/test_desk_accept_publish_signer.py:42` (PR, `actors == ["Owner", "Other", "Other"]`) и `:96`
(push, `[None, "Owner", "Other", "Other"]`). Средний элемент — тело проверки.

### 1.3 Спецификация (`docs/specs/2026-08-13-cockpit-command-api.md`)

- 1403–1409: тела запросов. `check:true` — единственный необязательный ключ; `actor` следует
  «the identity of the commit route». Чьё имя несёт проверка, не сказано.
- 1435, 1458–1461: проверка останавливается после первого look и push не делает. «An exact repeat
  of a press that recorded the push answers 200 … another actor `acceptance_exists`».
- 1482–1491: проверка PR; «The standing record answers 200 to a press that names its base».
- Подписывает тот, кто назван в `actor` тела. Чьим именем должен быть `requested_by` у push и PR,
  спецификация не говорит. Раздела 9.7 desk redesign в репозитории нет.

## 2. PR: та же ситуация

Да. Проверка PR идёт через тот же `send` (`:357-370`) с тем же `stepBody(step, actor, check)`,
`pr.signer` хранится так же, а найденный PR (обычный путь `:161-163` или `_moved`) записывается с
`request.actor`. Отличается только повтор: `_repeat` у PR actor не сверяет. Поэтому после чужой
проверки исходный автор получает 200 и запись (с чужим именем), а не 409. Одна строка UI
исправляет оба шага.

## 3. Перезагрузка страницы

- Хост создаётся заново: `push = newPush()`, `pr = newPr()`, фаза `idle`, `signer: null`. Панель
  не пользуется ни `localStorage`, ни `sessionStorage`; `SEALED` в `tests/test_studio_source.py`
  их запрещает. На сервере до записи `push.json` или `pr.json` о нажатии ничего не хранится (раздел
  1.1). Поэтому `state.signer` после перезагрузки потерян, и восстановить его не из чего.
- Кнопки «Проверить снова» после перезагрузки тоже нет. Push: карточка предлагает «Показать
  условия отправки», затем review, где текст подтверждения называет текущего человека, затем
  нажатие. Сервер сначала смотрит на remote (`accept_push.py:226-228`) и, если находит коммит,
  пишет запись с именем **того, кто подтвердил это новое нажатие**. PR: поля по умолчанию, review,
  нажатие; сервер сначала читает список (`:161-163` или `_moved`) и записывает найденный PR с
  именем подтвердившего.
- Для одной вкладки решение не нарушено: проверки здесь нет, а в записи стоит имя того, кто
  подтвердил записавшее её нажатие и видел своё имя в тексте подтверждения. **После скептика:**
  утверждение «Решения это не нарушает» снято для случая двух вкладок и перезагрузки. Там запись
  может назвать не подписанта той проверки, которая её нашла: вкладка A (Owner, исход `unknown`)
  и вкладка B или перезагрузка, где Other сделал полное нажатие и сервер записал его имя (O-V1-1
  для push и O-V1-3 для PR, раздел 5). Если владельцу нужно имя исходного автора и там, это
  отдельное серверное решение (вариант В в разделе 4), а не R4-V1.

## 4. Варианты

| Вариант | Суть | Цена | Решение |
| --- | --- | --- | --- |
| **А. UI отправляет `state.signer` в проверке** | `:358`: при `check` подписант — `push.signer` или `pr.signer`, при остальных нажатиях — текущий `actor` | Одна строка кода и комментарий. Сервер, схемы, digest и тексты не трогаются | **Выбран** |
| Б. Сервер берёт имя из commit или из другой записи | `requested_by` = `commit.requested_by` или имя push | Неверно по смыслу: commit мог подтверждать другой человек, а у push до look записи нет | Отвергнут |
| В. Сервер хранит pending-signer | Перед push или `gh pr create` писать intent `{acceptance_id, digest или fields, actor}`, проверка берёт имя оттуда | Новый файл и схема в `accept_records`/`read_records`, семантика при сбое, правка спецификации, тесты повреждений. Кроме того, новое подтверждённое нажатие после перезагрузки получит чужое имя | Отвергнут для V1; если владелец захочет — отдельное решение |
| Г. Проверка без `actor` | Тело `check` без `actor`; имя брать неоткуда | Ломает закрытое тело и спецификацию, упирается в ту же проблему, что В | Отвергнут |

Почему вариант А ничего не ломает:

- **Digest и условия.** `push_digest` не включает actor (`accept_push.py:140-144`). Тело проверки
  берёт `push.terms` или `pr.fields`, зафиксированные при подтверждении. С правкой тело проверки
  точно равно телу подтверждённого нажатия плюс `check:true`, даже если за столом другой человек.
  Именно это и закрепляет G4.
- **Проверка ничего не делает вовне.** Серверный путь `check` не меняется (`accept_push.py:231-232`,
  `accept_pull_request.py:164-165`). В UI не появляется новых кнопок и автоповторов; `mayPress`,
  `PUSH_UNKNOWN` и `PR_UNKNOWN` остаются прежними.
- **Повтор исходного автора.** Запись, найденная чужой проверкой, теперь записана на исходного
  автора. Его точный повтор, с проверкой или без, получает 200 и стоящую запись вместо 409
  `acceptance_exists`. Повтор от другого имени по-прежнему получает 409 (spec 1460–1461). У PR
  ничего не меняется: повтор с той же `base` получает 200 при любом actor.
- **«Снова» после отсутствия.** Без изменений. Если проверка (теперь от имени Owner) ничего не
  нашла, а за столом Other, `settleAbsent` (`:384-389`) возвращает шаг к review, и новое
  действующее нажатие подписывает уже Other. От имени человека, которого нет за столом, уходит
  только проверка, а она ничего не делает вовне.
- **Без человека за столом** проверка по-прежнему недоступна (`writable`, `:249`). Это оставлено
  намеренно: проверка может создать запись, а это запись в проект.

## 5. Что остаётся вне задания

- **O-V1-1.** Пусть запись push создало новое подтверждённое нажатие другого человека, например
  после перезагрузки в другой вкладке. Тогда проверка в старой вкладке от имени Owner получит 409
  `acceptance_exists`. Карточка считает это окончательным отказом (`:404`): сбрасывает условия и
  предлагает «Показать условия отправки». Если за столом не тот, кто записал push, следующее
  нажатие снова получит 409; кнопки «Обновить» при стоящем commit нет (`:467-472`), поэтому
  запись станет видна только после перезагрузки или смены запуска. Если за столом сам записавший,
  его полный повтор получит 200 (поправка ниже). Вопрос классификации отказов (рядом с R4-V4)
  решают Codex или владелец.
  **Поправка после ревью Opus.** Формулировки «так было и до R4-V1» и «после правки этот случай
  реже» были неверны, граница стала шире. Вкладка A: Owner, исход `unknown`. Во вкладке B Other
  записал `push.json`; за столом вкладки A сел Other. На HEAD проверка шла от Other и получала 200
  («Sent to GitHub»). С правкой она идёт от Owner и получает 409 `acceptance_exists`: карточка
  уходит в `idle` с текстом «This run already has another confirmed acceptance.», а полный повтор
  (review и подтверждение) от Other получает 200. До правки 409 был только если за столом A сидел
  не тот, кто записал push; теперь он при любом человеке за столом. Правка R4-V1 выбрала имя
  исходного подтверждения и поэтому сместила этот случай: это граница решения владельца, а не
  дефект кода, и код здесь не менялся.
- **O-V1-2.** В фазе `unknown` карточка не говорит, чьё имя запишет проверка. Строку «Проверка
  записывается на имя …» (EN/RU) добавить можно, но это новый текст, а не R4-V1. Без решения не
  делать.
- **O-V1-3 (добавлено после скептика).** Аналог O-V1-1 для PR. Вкладка A: Owner подтвердил
  создание, исход `unknown`. Вкладка B или перезагрузка: Other сделал полное нажатие (review и
  подтверждение), и сервер записал PR с `requested_by` Other. Проверка из вкладки A несёт Owner
  (после правки R4-V1) и получает 200 со стоящей записью, где назван Other: `_repeat` у PR
  actor не сверяет (`accept_pull_request.py:148-152`, spec 1490-1491), а `recordFits` в UI
  `requested_by` не сверяет и сверять не должен. У push тот же сценарий даёт 409
  `acceptance_exists` (O-V1-1). Без серверного pending-signer (вариант В) это не чинится. Правка
  R4-V1 этого не ухудшает: старая проверка из вкладки A тоже получила бы стоящую запись с тем же
  именем. Поэтому формулировка в разделе 6 говорит только о теле запроса и о записи, которую пишет
  сама проверка, и не обещает, что любая запись, найденная проверкой, называет подписанта.
- **CAPPED.** Файла `tests/test_desk_accept_publish_signer.py` (123 строки, после задания около
  171) нет в `CAPPED`. Включать ли его — тот же вопрос, что R4-G. `tests/test_command_line_cap.py` в
  этой задаче не правится.

## 6. Спецификация: одна фраза

Фраза нужна: по букве спецификации проверка несёт какой-то `actor`, и нигде не сказано, что это
подписавший исходное нажатие. Место — абзац о телах запросов, общий для двух маршрутов, строка
1409.

Было (1409):

```
boolean. Any other key or value is `contract_invalid`. After the body, the push answers
```

Стало (три строки вместо одной, остальной абзац не переносится). **После скептика:** прежняя
формулировка («запись, которую она находит, называет подтвердившего то нажатие») обещала лишнее.
Найденная запись может назвать другого (O-V1-1, O-V1-3, раздел 5), а проверка гарантирует только
то, что уходит в теле, и то, что пишет она сама. Рабочий текст:

```
boolean. Any other key or value is `contract_invalid`. A press with `"check":true` carries the
body of the press it looks for, `actor` included, whoever asks to look; a record that the look
writes names that actor in `requested_by`. After the body, the push answers
```

Длины строк — 94, 94 и 75 символов (проверено на файле спецификации).

## 7. Прототип на копии

Копия: `C:\Users\Пользователь\Documents\Codex\work\r4v1`, сделана через
`git archive HEAD src tests pyproject.toml`. Запуск с `$env:PYTHONPATH = "<копия>\src;<копия>"` и
`--rootdir <копия>`. Репозиторий не менялся.

| Прогон | Результат |
| --- | --- |
| Базовая линия в репозитории: `tests/test_desk_accept_publish.py tests/test_desk_transport_accept_publish.py tests/test_desk_accept_terminal.py tests/test_desk_accept_publish_signer.py` | 58 passed |
| Базовая линия: `tests/test_command_line_cap.py -k accept` | 11 passed, 141 deselected |
| Базовая линия: `tests/test_file_endings.py` | 9 passed |
| Копия, хост как в HEAD, прототипы G4 (push и PR) | 2 failed: в теле проверки `actor: "Other"` вместо `"Owner"` |
| Копия с правкой: signer, прототипы G4, publish, transport, terminal, `test_desk_accept_host.py` | 70 passed, 2 failed — ровно `signer.py:42` и `:96`, где теперь ожидаются `["Owner", "Owner", "Other"]` и `[None, "Owner", "Owner", "Other"]` |
| Копия с правкой и обновлёнными assert'ами: signer и прототипы G4 | 6 passed |
| Копия с правкой: `test_studio_source.py test_desk_copy.py test_desk_flag_door_source.py test_studio_module_graph.py test_desk_accept_host.py` | 40 passed (лимит 800 строк, запрещённые слова, граф модулей) |
| Копия, серверные характеризационные тесты (push и PR) на неизменённом сервере | 2 passed |

Мутанты на копии; модуль signer с обновлёнными assert'ами плюс два теста G4, всего 6 тестов:

| Мутант | Результат |
| --- | --- |
| M0 = HEAD: `const signer = actor;` | 4 failed: оба G4 и `signer.py:42`, `:96` |
| M1: проверка перезаписывает signer (`...confirmed(step)` всегда) | 4 failed: оба G4 (вторая проверка уходит от Other) и `:42`, `:96` («снова» достаётся Other без review) |
| M2: подписант исходного нажатия только у push | 2 failed: G4 PR и `:42` |
| M3: только у PR | 2 failed: G4 push и `:96` |
| S1: `accept_push._record` пишет `commit["requested_by"]` | серверный тест push красный |
| S2: `accept_pull_request._record` пишет `push["requested_by"]` | серверный тест PR красный |
| S3: `accept_push._repeat` не сверяет actor | серверный тест push красный (и существующий `reconcile:312-321`) |
| S4: `accept_pull_request._repeat` переписывает запись на actor повтора | серверный тест PR красный |

Мутант `state.signer ?? actor` эквивалентен и не считается: в фазе `unknown` `signer` всегда
задан.

## 8. Задание для Sonnet: S-R4-V1

### Цель

Проверка («Проверить снова», `check:true`) push и PR отправляет `actor` того, кто подтвердил
проверяемое нажатие (`push.signer` / `pr.signer`), кто бы ни сидел за столом. Обычные нажатия
по-прежнему отправляют текущего `actor`. Сервер не меняется. Основание — решение владельца R4-V1
(21.10.2026), проект — этот документ, разделы 0–7.

### Перед началом

- `git status --short` пуст; HEAD — `6932cfd` или потомок, в котором файлы ниже не менялись.
  Если менялись, остановиться и сообщить.
- Каждая команда PowerShell начинается с
  `. "C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command-Environment.ps1" -Quiet`.
- pytest запускать так:
  `python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\pt-<суффикс ≤ 4>`.
  Свои `pt-*` удалять. Browser-модули — по одному на процесс.
- Никаких коммитов, push, stash, checkout, reset и git config. Настоящих push и gh нет: только
  фальшивый gh и bare-remote из тестов.

### Файлы (только эти)

1. `src/conductor/panel/desk-accept-host.js`: комментарий 46–48 и начало `send` (357–358).
2. `tests/test_desk_accept_publish_signer.py`: docstring, assert'ы в строках 42 и 96, два новых
   теста G4.
3. `tests/test_accept_push_reconcile.py`: один характеризационный тест.
4. `tests/test_accept_pull_request.py`: один характеризационный тест.
5. `docs/specs/2026-08-13-cockpit-command-api.md`: строка 1409 заменяется тремя (раздел 6).

`tests/test_desk_accept_publish.py` (756 строк) **не трогать**: G4 идёт в модуль signer, который
уже вынесен из него по образцу проекта и импортирует оттуда `_js`, `PREFIX`, `PR_PREFIX` и
`PUSH_CLICK`.

### Шаг 1. Сначала красное (Node)

В `tests/test_desk_accept_publish_signer.py`:

a. Строку 42 заменить на `assert out["actors"] == ["Owner", "Owner", "Other"]`.

b. Строку 96 заменить на `assert out["actors"] == [None, "Owner", "Owner", "Other"]`.

c. В docstring модуля после первого абзаца добавить, например:

```
A check is not such a press: it acts on nothing outside and looks for the press that was
confirmed, so it carries that press's signer whoever presses it, and the record it finds names
that person (the owner's decision R4-V1, 21 October 2026).
```

d. В конец модуля добавить два теста G4 (основа ниже, проверена на копии; имена можно уточнить,
   строки не длиннее 100 символов):

```python
def test_a_check_pressed_by_another_person_names_the_signer_of_the_push_it_looks_for():
    out = _js("""
      const r = rig({push: [ok('push_terms', TERMS), refused('push_unconfirmed'), unknown,
        ok('push', PUSHED)]});
      await opened(r);
      for (const key of d) await press(r, key);
      signer = 'Other'; shown(r);
      const otherAtDesk = live(r.host.detail);
      await press(r, 'accept:push:desk.accept.check');
      const stillUnknown = live(r.host.detail);
      await press(r, 'accept:push:desk.accept.check');
      console.log(JSON.stringify({otherAtDesk, stillUnknown, kinds: kinds(r),
        bodies: r.sent.map(({body}) => body), sent: hasText(r.host.detail, 'Sent to GitHub'),
        after: live(r.host.detail)}));
    """, list(PUSH_CLICK))
    assert out["otherAtDesk"] == out["stillUnknown"] == [PREFIX + "check"]
    assert out["kinds"] == ["terms", "send", "check", "check"]
    first, checked, again = out["bodies"][1:]
    assert first["actor"] == "Owner"
    assert checked == again == {**first, "check": True}
    assert out["sent"] and out["after"] == [PR_PREFIX + "review"]


def test_a_check_pressed_by_another_person_names_the_signer_of_the_pull_request_it_looks_for():
    out = _js("""
      const r = rig({facts: {push: PUSHED}, pull: [unknown, unknown,
        ok('pull_request', PULL)]});
      await opened(r);
      for (const key of ['review', 'pr.action']) await press(r, 'accept:pr:desk.accept.' + key);
      signer = 'Other'; shown(r);
      const otherAtDesk = live(r.host.detail);
      await press(r, 'accept:pr:desk.accept.check');
      const stillUnknown = live(r.host.detail);
      await press(r, 'accept:pr:desk.accept.check');
      console.log(JSON.stringify({otherAtDesk, stillUnknown, kinds: kinds(r),
        bodies: r.sent.map(({body}) => body), number: hasText(r.host.detail, '#7'),
        after: live(r.host.detail)}));
    """)
    assert out["otherAtDesk"] == out["stillUnknown"] == [PR_PREFIX + "check"]
    assert out["kinds"] == ["send", "check", "check"]
    first, checked, again = out["bodies"]
    assert first["actor"] == "Owner"
    assert checked == again == {**first, "check": True}
    assert out["number"] and out["after"] == []
```

Две проверки подряд (первая возвращает unknown) закрепляют, что `signer` не перезаписывается
проверкой (мутант M1). `PUSHED` и `PULL` из фикстуры уже несут `requested_by: 'Owner'`.

Прогнать только этот модуль на текущем коде: ожидается **4 failed, 2 passed** (два обновлённых
assert'а и два новых теста; во всех причина — `actor: "Other"` в теле проверки). Без этого красного
дальше не идти.

### Шаг 2. Серверная характеризация (зелёная и до правки, и после)

Сервер не меняется. Тесты фиксируют серверную половину договора, на которую опирается UI: запись,
найденная проверкой, называет `actor` из тела проверки, и повтор от этого имени получает стоящую
запись. Имя `"Signer"` нарочно отличается от `"Owner"` в commit и push: так видно, что имя берётся
из тела, а не из другой записи (мутанты S1 и S2). Все импорты в обоих модулях уже есть.

a. `tests/test_accept_push_reconcile.py`, сразу после
   `test_when_neither_the_push_nor_the_look_answers_nothing_is_written_and_a_check_records_it`
   (строки 52–74):

```python
@needs_git
def test_a_check_writes_the_signer_its_body_names_and_the_signers_repeat_gets_that_record(
        tmp_path):
    api, root, record, remote, bare, gh = accepted_with_gh(tmp_path)
    digest = digest_of(api, record)
    looks = []

    def second_look_is_silent(run):
        looks.append(1)
        return TIMED_OUT if len(looks) == 2 else run()

    remote.on_look = second_look_is_silent
    assert reason_of(confirm(api, record, digest, actor="Signer")) == "push_unconfirmed"
    checked = confirm(api, record, digest, actor="Signer", check=True)
    assert checked.status == 201 and checked.payload["push"]["requested_by"] == "Signer"
    for again in (confirm(api, record, digest, actor="Signer"),
                  confirm(api, record, digest, actor="Signer", check=True)):
        assert (again.status, again.payload) == (200, checked.payload)
    other = confirm(api, record, digest, actor="Other", check=True)
    assert reason_of(other) == "acceptance_exists"
    assert remote.verbs().count("push") == 1
```

b. `tests/test_accept_pull_request.py`, сразу после
   `test_an_uncertain_pr_create_that_the_list_does_not_show_may_be_created_again_after_a_check`
   (строки 210–223):

```python
@needs_git
def test_a_check_after_an_unknown_creation_writes_the_signer_its_body_names(tmp_path):
    api, root, push, remote, bare, gh = pushed(tmp_path)
    _fakegh.script(gh.dir, {
        LISTED: [_fakegh.pr_list(), _fakegh.pr_list(), _fakegh.pr_list(row_of(push, 11))],
        CREATED: [_fakegh.said("", exit=1)]})
    assert reason_of(press(api, push, actor="Signer")) == "pr_create_failed"
    checked = press(api, push, actor="Signer", check=True)
    assert checked.status == 200, checked.payload
    assert checked.payload["pull_request"]["requested_by"] == "Signer"
    again = press(api, push, actor="Other")
    assert (again.status, again.payload) == (200, checked.payload)
    assert len(made(gh, CREATED)) == 1
```

Оба теста должны быть зелёными на текущем коде. Если хоть один красный — остановиться и сообщить:
это новое расхождение, продукт не править.

### Шаг 3. Правка UI

В `src/conductor/panel/desk-accept-host.js`:

a. Комментарий 46–48 заменить на:

```js
// `signer` is who confirmed the press that acted, and for the pull request `fields` freezes what
// that person saw: a repeat after a look that found nothing may use neither another name nor
// another text. A check looks for that press, so it carries that name too, whoever presses it.
```

b. Начало `send` (357–358) заменить на:

```js
  async function send(step, check) {
    // A check names the signer of the press it looks for, never the person at the desk now.
    const signer = check ? (step === "push" ? push : pr).signer : actor;
    const ticket = epoch, runId = selected, body = stepBody(step, signer, check);
```

Больше в файле ничего не менять: `stepBody`, `mayPress`, `writable`, `confirmed`, `settle`,
`settleAbsent`, `recordFits`, `PUSH_UNKNOWN`, `PUSH_ABSENT` и `PR_UNKNOWN` остаются как есть.
`recordFits` не должен сверять `requested_by`: стоящая запись PR законно отдаётся любому actor.

После правки модуль signer должен дать 6 passed.

### Шаг 4. Спецификация

Строку 1409 в `docs/specs/2026-08-13-cockpit-command-api.md` заменить тремя строками из раздела 6,
дословно. Остальной абзац не переносить.

### Шаг 5. Мутанты (на копии вне репозитория)

Сделать копию рабочего дерева (с правками), например в
`C:\Users\Пользователь\Documents\Codex\work\r4v1-s\`:
`Copy-Item -Recurse -Force <repo>\src, <repo>\tests <копия>` и `Copy-Item <repo>\pyproject.toml
<копия>`. Запускать с `$env:PYTHONPATH = "<копия>\src;<копия>"`, `Set-Location <копия>` и
`--rootdir <копия>`. Каждый мутант — замена одной строки, прогон, возврат исходного текста.

| Мутант | Замена | Прогон | Ожидается |
| --- | --- | --- | --- |
| M0 | `const signer = check ? (step === "push" ? push : pr).signer : actor;` → `const signer = actor;` | signer | 4 failed |
| M1 | `login: false, ...(check ? {} : confirmed(step))}` → `login: false, ...confirmed(step)}` | signer | 4 failed |
| M2 | строка `signer` → `const signer = check && step === "push" ? push.signer : actor;` | signer | 2 failed (G4 PR, тест PR из шага 1a) |
| M3 | строка `signer` → `const signer = check && step === "pr" ? pr.signer : actor;` | signer | 2 failed (G4 push, тест push из шага 1b) |
| S1 | `accept_push.py`: `"requested_by": request.actor, "pushed_at"` → `"requested_by": commit["requested_by"], "pushed_at"` | новый тест push | failed |
| S2 | `accept_pull_request.py`: `"requested_by": request.actor, "created_at"` → `"requested_by": push["requested_by"], "created_at"` | новый тест PR | failed |
| S3 | `accept_push.py`: `if record["requested_by"] != request.actor:` → `if False:` | новый тест push | failed |
| S4 | `accept_pull_request.py`, `_repeat`: последняя строка `return record` → `return {**record, "requested_by": request.actor}` | новый тест PR | failed |

Серверные мутанты прогонять только по двум новым тестам (`-k "writes_the_signer"`), а не по
полному набору.

### Шаг 6. Прогоны в репозитории (после правки)

| Команда (`python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\pt-…` + …) | Ожидается |
| --- | --- |
| `tests/test_desk_accept_publish.py tests/test_desk_transport_accept_publish.py tests/test_desk_accept_terminal.py tests/test_desk_accept_publish_signer.py` | **60 passed** (было 58, плюс 2 G4) |
| `tests/test_studio_source.py tests/test_desk_copy.py tests/test_desk_flag_door_source.py tests/test_studio_module_graph.py tests/test_desk_accept_host.py` | все passed (на копии было 40) |
| `tests/test_accept_push.py tests/test_accept_push_guard.py tests/test_accept_push_reconcile.py tests/test_accept_pull_request.py` | **170 passed** (было 168 после S-R4-1, плюс 2). Идёт около 9 минут |
| `browser_tests/test_desk_accept_publish.py` (отдельным процессом) | **8 passed**, без изменений. Сценарии там с тем же подписантом, тело проверки не меняется |
| `tests/test_command_line_cap.py -k accept` | **11 passed**, 141 deselected (reconcile и pull_request в `CAPPED`) |
| `tests/test_file_endings.py` | 9 passed |

Файлы `desk-accept-host.js`, `test_desk_accept_publish_signer.py` и строки спецификации тест длины
строк не покрывает. Проверить их вручную: ни одной строки длиннее 100 символов, без хвостовых
пробелов, ровно один `\n` в конце. Например:

```powershell
foreach ($f in 'src/conductor/panel/desk-accept-host.js',
               'tests/test_desk_accept_publish_signer.py') {
  $n = 0; foreach ($l in [IO.File]::ReadAllLines((Resolve-Path $f))) { $n++
    if ($l.Length -gt 100 -or $l -match '\s$') { "$f`:$n" } } }
```

`desk-accept-host.js` после правки — около 715 строк, лимит 800 (`test_studio_source.py`).

### Критерии приёмки

- На текущем коде модуль signer красный ровно в четырёх местах (шаг 1); после правки он зелёный.
- Тело проверки равно телу подтверждённого нажатия плюс `check:true`, в том числе когда за столом
  другой человек; обычное нажатие («снова» после review) по-прежнему подписывает текущий человек.
- Число `push` и `gh pr create` ни в одном сценарии не растёт; серверный код не изменён.
- Все мутанты из шага 5 убиты.
- `git diff --stat` показывает только пять файлов из списка.

### Чего не делать

- Не менять `accept_push.py`, `accept_pull_request.py`, `accept_records.py` и схемы записей; не
  добавлять серверный intent или pending-signer (вариант В отвергнут).
- Не менять тексты EN/RU (`desk-copy.js`, `studio-notice-copy.js`) и не добавлять строку про то,
  чьё имя запишет проверка (это O-V1-2).
- Не трогать `tests/test_desk_accept_publish.py`, `tests/test_command_line_cap.py` и browser-тесты.
  Если нужно что-то в `CAPPED`, написать об этом в отчёте.
- Не ослаблять существующие assert'ы. Меняются только два списка `actors` (шаг 1a, 1b).
- Не разрешать проверку без человека за столом (`writable` не трогать).
- Не чинить O-V1-1 (409 `acceptance_exists` в старой вкладке).
- Без коммитов, push, stash, checkout, reset и git config; без настоящих push и gh.

### Отчёт

По образцу `tasks/R4-S1-REPORT.md`, если оркестратор не назначил другого места: команды, числа,
красное до правки, таблица мутантов, `git status`, список временных каталогов.

## 9. Не проверено в этом анализе

- Полные серверные прогоны push/PR и browser-модуль на копии не запускались. Числа 168 и 8 взяты из
  `tasks/R4-S1-REPORT.md`; файлы этих наборов с тех пор не менялись (последний коммит по ним —
  `9c8fa7c`).
- Настоящий GitHub и gh, Linux и macOS.
- Ревью Codex по R4-V1 ещё не проводилось.

## 10. Передача

- Коммит не создавался. Изменён только этот файл (новый, не отслеживается).
- Временные файлы вне репозитория: `C:\Users\Пользователь\Documents\Codex\work\r4v1` — копия HEAD с
  прототипом правки (`src/conductor/panel/desk-accept-host.js`, `fixed-host.js.txt`), обновлёнными
  assert'ами в `tests/test_desk_accept_publish_signer.py` и пробами `tests/test_r4v1_probe.py`,
  `tests/test_r4v1_server_probe.py`. Её можно удалить. Каталоги `C:\Users\Пользователь\pt-v1*`
  удалены.
