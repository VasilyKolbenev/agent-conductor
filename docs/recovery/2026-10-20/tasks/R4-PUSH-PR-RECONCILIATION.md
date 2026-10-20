# R4. Сверка Push / PR: спецификация, код, UI, тесты

- Исполнитель: Claude Code / Opus 5.5. Только анализ; код продукта, тесты и состояние Git не менялись.
- Дата: 20 октября 2026.
- Исходный commit и ветка: `4d0e3af`, `feature/v1-desk-integration`.
- Рабочая копия во время сверки: `M src/conductor/command/adapters/process.py` и
  `M tests/test_execution_boundary.py` (параллельный агент, не R4), `?? AGENTS.md`, `?? CLAUDE.md`,
  `?? docs/recovery/`. Все файлы R4 совпадают с HEAD, поэтому номера строк ниже указаны по HEAD.
  Тесты прогонялись на этой рабочей копии; push и gh идут через `ProcessRunner`, поэтому правка
  `process.py` другим агентом формально входила в прогон.
- Статус выводов: **новый вывод ревью от 20.10**, а не найденное историческое решение. В сообщениях
  `00f732b` и `c7a185c` (13.10), `ae6951e` и `7e51ef7` (14.10) варианты (a)(b)(c) и п. 1
  раздела 9.7 помечены «pending a ruling». Merge `a2277c4` (18.10, D1-S1) говорит «Reviewed and
  verified in the lane», но речь там о guard name и команде (`a338594`, `4392991`), а не об
  (a)(b)(c). Явного принятия не найдено. Откатывать что-либо из-за слова «pending» этот отчёт не
  предлагает.

## 0. Итог

| Вопрос | Вердикт |
| --- | --- |
| 1. `check:true` и неизвестный исход push | **Согласовано по существу.** Гарантии выполняются: потеря ответа не ведёт к повторному push, показанная команда совпадает с выполненной. Есть одно буквальное расхождение со спецификацией, **D1** (P3, безопасность не страдает), и пробелы в тестах G1–G4 |
| 2. `pr.json.mismatch` и `detail.mismatch` | **Согласовано.** Пробелы в тестах G5 и G6. Наблюдение O1 о нестрогости словаря отказов на поведение не влияет |
| 3. Перемещённый remote head | **Согласовано.** Список читается при каждом нажатии, найденный PR записывается, `gh pr create` на перемещённой голове не вызывается, изменившиеся условия требуют нового подтверждения. Пробел G7 и остаточный риск R-1 спецификация признаёт сама |

Новая рекомендация для Codex: считать (a)(b)(c) и п. 1 раздела 9.7 действующим контрактом в той
форме, в какой они уже записаны в спецификации и реализованы. Отдельно решить D1 (вариант A или B)
и ответить на открытые вопросы В1–В4.

## 1. Источники

- `docs/specs/2026-08-13-cockpit-command-api.md`: таблица маршрутов, строки 237–238; маршруты,
  строки 1399–1490 (тела 1399–1418, условия push 1420–1433, подтверждение 1435–1461,
  PR 1463–1490).
- Спецификация desk redesign, на которую ссылается API-спецификация (разделы 9.5–9.7, 9.12 R7/S3),
  **в репозитории отсутствует** (`docs/**/*redesign*` пусто). Поэтому UI сверялся с
  API-спецификацией, комментариями в коде и сообщениями коммитов.
- Код: `accept_push.py`, `accept_pull_request.py`, `accept_github.py`, `accept_gh.py`,
  `accept_records.py`, `api_refusals.py`, `project_git.py`, `tool_env.py`; UI:
  `panel/desk-accept-host.js`, `desk-transport.js`, `desk-copy.js`, `studio-notice-copy.js`.
- История: `0202a76`, `e2c4acd`, `00f732b`, `c7a185c` (13.10); `000c66e`, `8b1ad79`, `1903fe8`,
  `5a214fd`, `ac833f0`, `0fabe95`, `2cf7801`, `c098421`, `ae6951e`, merge `7e51ef7` (14.10);
  `a338594`, `f9d2392`, `4392991`, `53ec40d`, `aa364f4` (16.10), merge `a2277c4` (18.10).

## 2. Проверки

Перед каждой командой выполнялось
`. "C:\Users\Пользователь\Documents\Codex\2026-10-20\new-chat\outputs\December-Command-Environment.ps1" -Quiet`.
Среда: Windows 11, Python 3.12.14, git 2.53.0.windows.3. Сети не было: удалённым репозиторием
служил bare-репозиторий на диске, а gh был скриптовой фальшивкой.

| Команда (`python -m pytest -q --tb=short -p no:cacheprovider` + …) | Результат | Что доказывает |
| --- | --- | --- |
| `--basetemp C:\Users\Пользователь\Documents\Codex\work\pt-o4a tests/test_accept_push.py tests/test_accept_push_guard.py tests/test_accept_push_reconcile.py tests/test_accept_pull_request.py` | **156 passed**, 0 failed, 0 skipped, 323.39 s | Серверные контракты push/PR на настоящем git |
| `--basetemp …\pt-o4b tests/test_desk_accept_publish.py tests/test_desk_transport_accept_publish.py tests/test_desk_accept_terminal.py` | **52 passed**, 8.75 s | Карточка под Node и мутационная дверь |
| `--basetemp …\pt-o4c browser_tests/test_desk_accept_publish.py` | **8 passed**, 109.82 s | Настоящий стол в Chromium, EN и RU |
| `--basetemp …\pt-o4e tests/test_accept_github.py tests/test_accept_gh.py tests/test_fakegh.py` | **78 passed**, 5.40 s | Факты GitHub, читатель gh, фальшивый gh |
| `--basetemp …\pt-o4f tests/test_command_line_cap.py -k "accept or fakegh or gh_script"` | **14 passed**, 130 deselected | Лимит 100 символов в строке для файлов R4 |
| Проба (scratch, вне репозитория): `$env:PYTHONPATH=<repo>; python -m pytest -q -s --tb=short -p no:cacheprovider --rootdir . --basetemp …\pt-o4d C:\Users\Пользователь\Documents\Codex\work\r4probe\test_r4_probe.py` | **2 passed**, 9.81 s | Доказательства D1 и В1 (раздел 6) |

Git на хосте старше 2.56, поэтому эффект guard name на tracking ref здесь не виден. Тесты сами
об этом говорят: `test_accept_push_guard.py:11-15`.

## 3. Вопрос 1: `check:true` и неизвестный исход push

| Пункт | Спецификация | Код | UI | Тесты | Вердикт |
| --- | --- | --- | --- | --- | --- |
| 1.1 Тело проверки | 1403–1406: `"check":true` — единственный необязательный ключ подтверждения push и тела PR | `accept_push.py:66-85` (71–74: только `true`; вместе с телом terms это `contract_invalid`); `accept_pull_request.py:109-122` | `desk-accept-host.js:319-335`: то же тело, что показано и подтверждено, плюс `check:true`; цели двери в `desk-transport.js:95-100` | `test_accept_push.py:71-89`; `test_accept_pull_request.py:30-54`; `test_desk_transport_accept_publish.py:27-38, 100-123` | согласовано |
| 1.2 Проверка ничего не делает | 1457–1458: остановка после первого look, 200 `{"push":null}` при отсутствии ref, «never pushes»; тот же коммит даёт 201 (1437), другой даёт `push_rejected` (1438) | `accept_push.py:224-232`: look, затем 201, `push_rejected` или `{"push": None}`; всё это до вызова push | `settle` 390–393: `null` на проверку ведёт в `settleAbsent` (384–389); «Отправить снова» видит только тот же подписант | `test_accept_push_reconcile.py:52-74` (проверка записывает 201, push один), 77–82 (проверка делает только `ls-remote`); `test_desk_accept_publish.py:133-157`; browser `:171-193` | согласовано; пробелы G1–G3 |
| 1.3 Look до push и после каждого push; неизвестный ответ вслепую не повторяется | 1435–1440: «BEFORE any push and AFTER every push; only the look decides»; lease `--force-with-lease=<ref>:` | `accept_push.py:224-243`; слова push 149–158; lease 158 | — | `test_accept_push.py:252-276` (гонка: lease отклоняет, ветка не двигается), 306–320 (повтор даёт 200, push один); `reconcile:39-49, 246-258` (запись не удалась, следующее нажатие записывает без второго push), 303–327 | согласовано, кроме D1 |
| 1.4 Ответы после push | 1451–1457: тот же коммит → 201; другой → `push_rejected`; ref нет → `push_rejected`, `push_unconfirmed`, `push_timed_out` или `git_failed` по ответу push; look без ответа → `push_unconfirmed`, а если git не смог войти, `push_auth_failed` | `accept_push.py:233-243`, `_kind` 246–262. **Строки 235–236: при `kind == "auth"` второго look нет** | `PUSH_UNKNOWN` (39) включает `push_auth_failed`, поэтому доступна только «Проверить снова» | `reconcile:85-110`; **`reconcile:96-102` закрепляет «no look follows the failed push»** | **расхождение D1** (безопасность сохранена) |
| 1.5 UI при неизвестном исходе | API-спецификация UI не описывает (раздел 9.7 desk redesign недоступен) | — | Заголовок 5–8; 39–41; `outcome` 78–82; `mayPress` 340–345; `send` 357–370; `settle` 390–406. Сетевой сбой (`desk-transport.js:141-161`) или ротация сессии (225–226) дают `unknown`, после чего доступна только «Проверить снова». Условия и команда остаются на экране, поля PR заблокированы, автоповтора нет | `test_desk_accept_publish.py:133-157` («quiet»: три перерисовки без запросов), 160–192, 338–363; browser `:171-193, 196-218` | согласовано |
| 1.6 Повтор и смена условий | 1435, 1451, 1458–1460: другой digest → `push_terms_changed`; точный повтор → 200 и стоящая запись; другой actor → `acceptance_exists` | `accept_push.py:107-123` | Окончательный отказ сбрасывает условия, доступно «Показать условия отправки» (404). «Отправить снова» отправляет тот же digest от того же подписанта (336–345, 384–389). При смене actor шаг возвращается к review (109–116) | `reconcile:233-243`; `guard:187-220`; `test_desk_accept_publish.py:160-221, 402-423` | согласовано; см. В1 (проверка от другого actor) |
| 1.7 Показанная команда = выполненная | 1425–1426, 1447–1451 | `_current_terms` (126–146) строит `command` и `words` из одного списка. `_answer` (111–114) передаёт эти же `words` в `_send` (233). Digest покрывает `command` | `termsFacts` 602–612: `<pre>` дословно повторяет `terms.command`; на сервер уходит только `push_digest` (326–327) | `guard:166-173, 176-184, 187-206`; `test_accept_push.py:173-193, 279-303`; browser `:139-147` (`terms["command"] == "git " + words_of(pushed)`) | согласовано на уровне слов после `git -C <root>`; см. В2 |
| 1.8 Сеть вне транзакции, одно нажатие за раз | 1460–1461 | `accept_github.py:104-107`; `accept_push.py:107, 282-288` | — | `reconcile:261-282, 303-327` | согласовано |

Гарантия «потеря ответа не ведёт к повторному внешнему действию» для push держится на трёх
вещах. Сервер всегда смотрит на ref перед push (`accept_push.py:226-232`). Lease не даёт переписать
существующий ref (`:158`). Карточка никогда не повторяет запрос сама (`desk-accept-host.js:5-8,
340-345`). Доказательства: `test_accept_push.py:306-320`, `reconcile:52-74, 246-258`, browser
`:171-193`.

Гарантия «показанная команда = выполненная» выполняется на уровне слов, переданных git-ридеру.
`tests/accept_remote.py:44-47` отрезает `-C <root>`, а обёртка `Remote` записывает аргументы до
того, как ридер добавляет `GIT_FLAGS`. Фактический argv выглядит так:
`<pinned git> -c core.fsmonitor= -c gc.auto=0 -c maintenance.auto=false -C <root> <words>`
(`project_git.py:25, 105`), с окружением 8.9 (`tool_env.py:43-47`: `core.hooksPath` указывает на
пустой каталог, `GIT_TERMINAL_PROMPT=0`, `LC_ALL=C`). По разделам 9.3 и 8.9 так устроены все
git-вызовы продукта, так что противоречия со спецификацией нет. Но для фразы «the one for the
owner's terminal» (1449) это важно: см. В2.

## 4. Вопрос 2: `pr.json.mismatch` и `detail.mismatch`

| Пункт | Спецификация | Код | UI | Тесты | Вердикт |
| --- | --- | --- | --- | --- | --- |
| 2.1 Формат `pr.json.mismatch` | 1473–1474, 1490: `null` для собственного PR, иначе `{head_oid, base, cross_repository}` | `accept_pull_request.py:273-284` (mismatch 280–282); схема `accept_records.py:24-25, 87-96, 100-109`; согласованность с `push.json` 131–134 | `prRecord` 691–703: при `mismatch` показывается статус «moved» с OID, если `mismatch.head_oid !== head_oid`, иначе «differs». Ссылка выводится только для `github.com/.../pull/N` (44–45) | `test_accept_pull_request.py:127-140` (`null`), 160–192, 286–342, 407–422 (повреждённый mismatch → `run_corrupt`); `test_desk_accept_publish.py:563-589` | согласовано; пробел G5 (текст «differs» не покрыт) |
| 2.2 mismatch при перемещённой голове | 1485–1487: коммит, на котором ветка стоит сейчас, base и флаг форка; `null` только если ref нет и PR собственный | `_moved` 187–202 (сначала собственный PR, иначе `listed[0]`); `_record` 274 (`own = moved is None and is_own`), 281 (`moved or row.head_oid`) | — | `:286-312, 315-329, 332-342` | согласовано; пробел G6 (ref удалён, в списке только чужой PR) |
| 2.3 `detail.mismatch` | 1416–1418: только у `pr_mismatch`, одно из четырёх слов, «no other reason carries it» | `api_refusals.py:261, 283, 395-396, 417-433, 559-569`; `accept_github.py:45-53, 74-79`. Все три места, где отказывает PR (`accept_pull_request.py:151, 183, 200`), передают слово | `refusalText` 250–257: для нажатия слово берётся из `MISMATCH` (25–29), для проверки — из `CHECKED` (31–35); тексты EN/RU в `desk-copy.js:178-207` | `test_accept_push.py:108-124`; `test_accept_pull_request.py:110-124, 143-157, 392-404`; `test_desk_transport_accept_publish.py:126-138`; `test_desk_accept_publish.py:505-560` | согласовано; наблюдение O1 |

## 5. Вопрос 3: перемещённый remote head

| Пункт | Спецификация | Код | UI | Тесты | Вердикт |
| --- | --- | --- | --- | --- | --- |
| 3.1 Список читается при каждом нажатии, даже если голова сдвинулась | 1464–1465, 1482–1488 | `_publish` 158–160 вызывает `_moved` 187–202. Если gh не отдал список — `pr_create_failed` (205–213). Если remote не ответил до проверки — `pr_create_failed` или `push_auth_failed` (169–175) | Найденный PR (200) записывается с mismatch. На `remote_head_moved` для нажатия выводится «Это нажатие Pull Request не создало», для проверки — нейтральный текст (`desk-copy.js:178-207`) | `test_accept_pull_request.py:143-157, 286-312` (и проверка, и обычное нажатие), 315–367, 370–377; `test_desk_accept_publish.py:513-576` | согласовано |
| 3.2 `gh pr create` на перемещённой голове не вызывается | 1488–1489 | `_create` достижим только при `seen == push["commit"]`, при списке без собственного и без чужого PR и без `check` (158–166) | — | `made(gh, CREATED) == []` в `:143-157, 315-367`; в `:286-312` за весь сценарий ровно одно создание | согласовано |
| 3.3 После создания: снова проверка, запись найденного, без повторного создания | 1470–1478 | `_create` 228–240, `_moved_to` 243–253, `_number` 256–270 (exit 4 — единственный исход, при котором точно ничего не создано). Неизвестный ответ ведёт к чтению списка; если PR нет — `pr_create_failed` | `PR_UNKNOWN` (41) оставляет только «Проверить снова». `null` ведёт к «Создать снова» тем же подписантом с теми же полями (355–356, 384–389) | `test_accept_pull_request.py:160-234, 259-266`; `test_desk_accept_publish.py:338-363, 452-475`; browser `:196-218` (одно создание) | согласовано; остаточный риск R-1 |
| 3.4 Изменившиеся условия требуют нового подтверждения | 1435, 1451 (push); для PR проверка идёт перед каждым созданием (1464, 1478) | push: digest включает команду (`accept_push.py:111-113`) | Правка поля PR в «absent» возвращает к review (409–413). Смена actor тоже (109–116, 384–389). `pr_mismatch` и окончательные отказы возвращают к review (404–405). `push_terms_changed` требует заново прочитать условия | `test_desk_accept_publish.py:199-221, 366-449, 452-475, 513-534` | согласовано |

## 6. Расхождения

### D1. После `git push`, сообщившего об ошибке входа, сервер не смотрит на remote (P3)

- **Спецификация** (1435–1436, 1451–1457): «looks at the ref on the remote BEFORE any push and
  AFTER every push; only the look decides». После push `push_auth_failed` возникает только из look,
  который не смог войти. Docstring самого модуля говорит то же: `accept_push.py:14-16` («Whatever
  the push said, only that look decides»).
- **Код**: `accept_push.py:234-236`. При `kind == "auth"` сразу возвращается `push_auth_failed`,
  второго `ls-remote` нет. Так было с первого коммита `00f732b` (13.10). Тест
  `test_accept_push_reconcile.py:96-102` это закрепляет: `verbs == ["ls-remote", "push"]`.
- **Доказательство (новая проба)**: `work\r4probe\test_r4_probe.py::test_probe_a_landed_push_with_auth_words_is_not_looked_at_after_the_push`.
  Push дошёл до remote, но git вернул exit 128 со словами «could not read Username». Результат:
  409 `push_auth_failed`, verbs `['ls-remote', 'push']`, коммит на remote есть, `push.json` нет.
  Следующий `check:true` даёт 201, и push по-прежнему один.
- **Влияние**: повторного внешнего действия нет. UI считает `push_auth_failed` неизвестным
  исходом и предлагает только проверку; сервер смотрит перед любым push; lease защищает ref.
  Расходятся контракт ответа и принцип «only the look decides»: push, который фактически дошёл,
  сообщается как ошибка входа и требует лишней проверки. На практике нужна редкая комбинация —
  ненулевой exit и слова об ошибке входа без флага отправки.
- **Варианты (решает Codex, В3)**:
  - **A (рекомендую)**: код всегда смотрит после push, а `push_auth_failed` от самого push
    остаётся только для случая «ref нет». В спецификацию нужно добавить в перечень исходов «no
    ref» фразу «`push_auth_failed` when git said it could not sign in». Без неё по букве
    спецификации это `git_failed`, и UI потеряет подсказку о входе.
  - **B**: код оставить и исправить спецификацию и docstring, например так: «a push that git could
    not sign in for answers `push_auth_failed` without the second look».
- Готовое задание для варианта A — **S-R4-1** в разделе 9.

Других расхождений между спецификацией, кодом, UI и тестами по трём вопросам не найдено.

## 7. Наблюдения (не расхождения поведения)

- **O1. Словарь допускает `pr_mismatch` без `mismatch`.** `ApiRefusal.accept_refused`
  (`api_refusals.py:552-557`) принимает любое слово `ACCEPT_REASONS`, в том числе `pr_mismatch`.
  Строка `("accept_refused", ("reason",))` (389–390) признаёт `{reason:"pr_mismatch"}`. Три теста
  закрепляют такую форму: `test_accept_preview.py:213-220`, `test_accept_push.py:99-105` и
  `test_desk_transport_accept_publish.py:77-81, 126-130` («14 wires with only reason»). Живой код её
  не порождает: в разделе 4 все места передают слово. По тому же образцу устроен
  `signing_required`. UI обрабатывает и эту форму: показывается общий текст
  `accept.reason.pr_mismatch`. Ужесточать стоит вместе с `signing_required` и по решению Codex, вне
  R4.
- **O2. Как UI понимает `git_failed`, `git_timed_out` и 5xx после внешнего действия.** Комментарий
  `desk-accept-host.js:36-38` утверждает, что после `PUSH_ABSENT` «the look found it absent».
  Фактически `git_failed` бывает и до любого look: при пересчёте условий
  (`accept_push.py:134-138, 182-212`; `accept_github.py:139-175`). Бывает и после успешного push,
  если не удалось записать `push.json`: `OSError` превращается в `git_failed`
  (`accept_github.py:88, 92`). Ответ 500 `store_error` после push (`reconcile:246-258`) UI считает
  окончательным отказом (78–82, 404), тогда как другие хосты стола считают `store_error` потерянным
  ответом (`desk-flow-host.js:11`, `desk-wizard-git.js:290`). Безопасности это не вредит: следующее
  нажатие сначала смотрит на remote и записывает. Но тексты могут вводить в заблуждение, например
  «Git не смог прочитать факты для принятия» рядом с кнопкой «Отправить снова». Классификацию
  решают Codex или владелец (В4); характеризующий тест — G8.
- **O3 (вне трёх вопросов).** `_admitted` (`accept_github.py:157-161`) и `_GITHUB`
  (`project_git_state.py:19`) принимают адрес с завершающим `/`
  (`https://github.com/O/R/`, `….git/`). Спецификация (1422–1424) говорит «exactly … with an
  optional `.git`». Нужно сузить код или дописать спецификацию; сюда же относится В4.
- **R-1. Остаточный риск, признанный спецификацией** (1475–1478; docstring
  `accept_pull_request.py:18-24`). Если после неизвестного создания `gh pr list` ещё не показывает
  PR, то после двух пустых чтений и явного «Создать снова» будет вторая попытка `gh pr create`.
  Второй открытый PR с той же парой head/base GitHub обычно отклоняет, но это внешнее свойство:
  без настоящего GitHub его тестами не проверить.

## 8. Пробелы в тестах

| ID | Что не покрыто | Где добавить | Зависит от |
| --- | --- | --- | --- |
| G1 | `check:true`, на remote другой коммит → `push_rejected`, только `ls-remote` (сейчас покрыто лишь обычное нажатие, `reconcile:113-119`) | `tests/test_accept_push_reconcile.py` | — |
| G2 | `check:true`, look без ответа: таймаут → `push_unconfirmed`, нет входа → `push_auth_failed`; ни одного push (сейчас покрыто только обычное нажатие, `reconcile:105-110`) | там же | — |
| G3 | `check:true` при изменившихся условиях (guard name занят) → `push_terms_changed`, ни одного `ls-remote` (сейчас покрыто только обычное нажатие, `guard:187-206`) | `tests/test_accept_push_guard.py` | — |
| G4 | UI: смена actor в фазе `unknown` → чьё имя уходит в проверку и попадает в запись (сейчас текущий actor, `desk-accept-host.js:358`) | `tests/test_desk_accept_publish.py` | В1 |
| G5 | UI: запись PR с mismatch при совпадающем `head_oid` (другая base или форк) → текст «differs», кнопок нет | `tests/test_desk_accept_publish.py` | — |
| G6 | Сервер: ref удалён, в списке только чужой PR (другая base или другой head) → 200, mismatch из строки списка, `gh pr create` не вызывался | `tests/test_accept_pull_request.py` | — |
| G7 | Сервер: `gh pr create` вернул номер, которого ещё нет в списке → `pr_create_failed`, записи нет; следующее нажатие находит PR и создаёт ровно один | `tests/test_accept_pull_request.py` | — |
| G8 | UI: ответ 500 `store_error` на отправку → автоповтора нет, дальше идёт чтение условий (характеризация O2) | `tests/test_desk_accept_publish.py` | В4 / O2 |
| G9 | Push дошёл, но git сообщил об ошибке входа → 201 по look после push | входит в S-R4-1 | D1 |
| — | Браузерного сценария с перемещённой головой и показом mismatch на настоящем столе нет; Node-тесты и серверные тесты его покрывают, приоритет низкий | `browser_tests/test_desk_accept_publish.py` | — |

## 9. Задания для Sonnet

### S-R4-1. D1, вариант A. Запускать только после решения Codex по В3

**Цель.** После каждого `git push` сервер смотрит на ref. `push_auth_failed`, полученный от самого
push, возвращается только тогда, когда look после push не нашёл ref.

**Файлы (только эти):**
- `src/conductor/command/accept_push.py`: функция `_send` (224–243). Если нужно, одно предложение
  в docstring `_kind` (246–252).
- `tests/test_accept_push_reconcile.py`: тест на строках 96–102 и новые тесты рядом с ним.
- `docs/specs/2026-08-13-cockpit-command-api.md`: одна фраза в 1453–1457, если Codex утвердил
  текст. Иначе спецификацию правит Codex.

**Шаги:**
1. Сначала красный тест. Новый тест
   `test_a_push_that_landed_and_said_it_could_not_sign_in_is_recorded_by_the_look_after_it`:
   `remote.on_push` выполняет `run()` и возвращает `GitAnswer(128, AUTH_WORDS)`. Ожидается 201,
   `remote_oid(bare) == record["commit"]`, `stands(root)`,
   `verbs(remote) == ["ls-remote", "push", "ls-remote"]` и `remote.verbs().count("push") == 1`. На
   текущем коде тест красный (409 `push_auth_failed`), это видно и по пробе из раздела 6.
2. Изменить тест 96–102: переименовать в
   `test_a_git_that_cannot_sign_in_is_push_auth_failed_after_the_look_finds_no_ref`. Ожидается
   `push_auth_failed`, `verbs(remote) == ["ls-remote", "push", "ls-remote"]`, `not stands(root)`,
   `remote_oid(bare) is None`.
3. Добавить параметризованный тест: push сообщил об ошибке входа, а look после push (а) тоже не
   смог войти → `push_auth_failed`; (б) не ответил (таймаут) → `push_unconfirmed`. В обоих случаях
   push ровно один, `push.json` нет.
4. В коде `_send` перенести ветку `if kind == "auth": raise …("push_auth_failed")` после второго
   `_look`. Она должна стоять после «тот же коммит → 201» и «другой коммит или `rejected` →
   `push_rejected`», но перед итоговым `raise` (`push_unconfirmed` / `push_timed_out` /
   `git_failed`). Больше ничего не менять.
5. Спецификация, если текст утверждён: в перечне исходов «no ref» (1453–1456) добавить
   «`push_auth_failed` when git said it could not sign in».

**Проверки** (каждый раз с предварительным `. …December-Command-Environment.ps1 -Quiet`):
- `python -m pytest -q --tb=short -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\pt-s4a tests/test_accept_push.py tests/test_accept_push_guard.py tests/test_accept_push_reconcile.py tests/test_accept_pull_request.py`:
  всё зелёное. До изменения было 156 passed; после — 156 плюс новые.
- `python -m pytest -q --tb=short -p no:cacheprovider --basetemp …\pt-s4b tests/test_desk_accept_publish.py tests/test_desk_transport_accept_publish.py tests/test_desk_accept_terminal.py`:
  52 passed, без изменений.
- `python -m pytest -q --tb=short -p no:cacheprovider --basetemp …\pt-s4c browser_tests/test_desk_accept_publish.py`:
  8 passed.
- `python -m pytest -q --tb=short -p no:cacheprovider --basetemp …\pt-s4d tests/test_command_line_cap.py -k "accept"`:
  passed (строки не длиннее 100 символов).

**Критерии приёмки:**
- В новых тестах за каждым `push` следует ровно один `ls-remote`; исключение — когда сам look
  бросает отказ.
- Число `push` ни в одном существующем сценарии не растёт.
- UI и тексты не меняются: `push_auth_failed` по-прежнему считается неизвестным исходом, и
  доступна только «Проверить снова».
- Diff ограничен перечисленными файлами. `_kind`, lease, `push_words`, `guard_name` и `_look` не
  тронуты.

**Чего не делать:** не менять `desk-accept-host.js`, `PUSH_UNKNOWN` и `PUSH_ABSENT`; не добавлять
ретраи; не трогать `adapters/process.py` и `tests/test_execution_boundary.py` (это чужая задача);
не выполнять реальные push и gh; не делать коммит без указания.

### S-R4-2. Закрыть пробелы G1–G3, G5–G7 (только тесты, продукт не менять)

**Файлы:** `tests/test_accept_push_reconcile.py` (G1, G2), `tests/test_accept_push_guard.py` (G3),
`tests/test_accept_pull_request.py` (G6, G7), `tests/test_desk_accept_publish.py` (G5). G4 и G8
ждут решений по В1 и В4.

**Шаги:**
1. G1: `seed_remote_ref(root, bare, moved_commit(root, record))`, затем
   `confirm(..., check=True)`. Ожидается `push_rejected`, `verbs == ["ls-remote"]`, ref не сдвинут.
2. G2: два теста по образцу `reconcile:105-110`, но с `check=True`. Первый: `on_look` →
   `TIMED_OUT` → `push_unconfirmed`. Второй: `on_look` → `GitAnswer(128, b"fatal: Authentication failed …")`
   → `push_auth_failed`. В обоих `verbs == ["ls-remote"]`.
3. G3: по образцу `guard:187-206`, но вторым нажатием `confirm(..., check=True)`. Ожидается
   `push_terms_changed`, ни одного `ls-remote`, ни одного `push`.
4. G5 (Node): `rig({facts: {push: PUSHED, pull_request: {...PULL, mismatch: {head_oid: OID, base: 'dev', cross_repository: false}}}})`.
   Должен показываться текст `desk.accept.pr.differs`, текста `desk.accept.pr.moved` быть не
   должно, `live(...)` пусто. Проверить EN и RU.
5. G6: `move_branch(root, bare)` (удалить ref), затем
   `pr_list(row_of(push, 4, base="dev"))` и, вторым параметром, `pr_row(4, OTHER, head=BRANCH)`.
   Для `check=True` и обычного нажатия ожидается 200 и mismatch
   `{head_oid: <из строки>, base: <из строки>, cross_repository: False}`; `made(gh, CREATED) == []`.
6. G7: `LISTED: [pr_list(), pr_list()]`, `CREATED: [created(7)]`. Первое нажатие даёт
   `pr_create_failed`, `pr.json` нет. Затем `LISTED: [pr_list(row_of(push, 7))]`, второе нажатие
   даёт 200 и `number == 7`; `len(made(gh, CREATED)) == 1`.

**Проверки:** те же четыре команды, что в S-R4-1 (`--basetemp …\pt-s5a` … `pt-s5d`).
**Критерии:** все новые тесты зелёные на **текущем** коде, потому что это характеризация. Если
какой-то из них красный, остановиться и сообщить: это новое расхождение, а не повод править
продукт. Строки не длиннее 100 символов.
**Чего не делать:** не менять код продукта и тексты, не ослаблять существующие assert'ы, не
трогать файлы чужих задач.

## 10. Открытые вопросы для Codex и владельца

- **В1 (владельцу).** Чьё имя проверка записывает в `requested_by`? Сейчас проверка уходит от
  текущего actor (`desk-accept-host.js:358`), и найденная запись получает это имя
  (`accept_push.py:273-279`; `accept_pull_request.py:273-284`). Проба
  `test_probe_a_check_by_another_person_writes_that_person_as_requested_by`: Owner отправил push,
  исход неизвестен; Other нажал проверку → 201, `requested_by: "Other"`. После этого точный повтор
  от Owner получает 409 `acceptance_exists`. Варианты: (а) проверка несёт `state.signer`, то есть
  того, кто подтвердил проверяемое нажатие; (б) оставить как есть и записать в спецификации, что
  запись, найденная проверкой, называет того, кто нажал проверку. Повторного внешнего действия ни
  в одном варианте нет.
- **В2 (Codex).** Спецификация (1448–1449) называет показанную команду «the one for the owner's
  terminal». Продукт запускает её с окружением 8.9: hooks выключены, без запроса пароля. В
  терминале владельца те же слова запустят pre-push hooks и могут запросить вход. Нужна ли
  оговорка в карточке или в спецификации?
- **В3 (Codex).** D1: вариант A или B (раздел 6).
- **В4 (Codex или владельцу).** O2: считать ли в карточке `store_error` (и `git_failed` после
  внешнего действия) неизвестным исходом, как это делают другие хосты стола? И O3: сузить
  `_admitted` до форм спецификации или дописать в спецификацию завершающий `/`?

## 11. Не проверено

- Git ≥ 2.56: эффект guard name на tracking ref на хосте не виден (git 2.53). Это работа CI-job с
  Git 2.56 (`test_push_argv_sends_no_tags_and_no_submodules` печатает версию).
- Настоящий GitHub и настоящий gh: отставание `gh pr list`, отказ GitHub на второй PR той же пары
  head/base (R-1), формулировки ошибок входа от реального сервера.
- Linux и macOS: прогоны были только на Windows. Полный suite и release gate не запускались, как и
  требовало задание.
- Оригинал desk redesign 9.7 и 9.12 и утраченные отчёты
  `v1-lanes/reports/2026-10-14-D1-push-pr-backend.md`, `…-ui.md`, `2026-10-16-D1-S1.md`.

## 12. Ревью Codex

Заполняется после независимого чтения. Заранее не заполнять.

## 13. Передача

- Коммит не создавался.
- `git status` на момент сверки: `M src/conductor/command/adapters/process.py`,
  `M tests/test_execution_boundary.py` (параллельный агент), `?? AGENTS.md`, `?? CLAUDE.md`,
  `?? docs/recovery/`. Этот отчёт — новый файл в `docs/recovery/2026-10-20/tasks/`.
- Временные файлы вне репозитория: `C:\Users\Пользователь\Documents\Codex\work\r4probe\test_r4_probe.py`
  (проба D1 и В1) и каталоги `work\pt-o4a` … `pt-o4f`. Их можно удалить.
- Следующий шаг: Codex решает В3 (D1, A или B) и В1, после чего Sonnet получает S-R4-1. S-R4-2
  можно выдавать сразу, оно не зависит от решений.
