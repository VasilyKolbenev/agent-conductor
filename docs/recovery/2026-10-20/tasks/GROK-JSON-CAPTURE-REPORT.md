Итог: локально проверено | `4deb571` | 195 target + 26 guard/Chromium passed, 0 failed |
без моделей | финальный локальный core выполняется, затем решение об установке.

# Отчёт: GROK-JSON-CAPTURE

- Ведущий: Codex; независимые линзы: do_backend, do_evidence, do_studio.
- База: `52e7244`, ветка `recovery/2026-10-20`, исходный status чистый.
- TASK/DESIGN `f3aff6a`, уточнения `8aeeae6` / `4d7f669` / `9b34570`, scope `5102325` / `0f8ed4c`.
- Цель: большой JSON-конверт не должен лишать runtime полного допустимого ответа Grok.
  Потерянный live stdout не восстановлен; состав исходного переполнения неизвестен.

## Воспроизведение и гипотезы

| Гипотеза | Различающая проверка | Итог |
| --- | --- | --- |
| Один предел ошибочно применяется к конверту и результату | Один literal `  Да 🚀\n`, JSON с thought 49 152 / 49 153 байта | На базе 1 passed / 1 failed: второй получил capture refusal |
| Escaping уменьшает допустимый UTF-8 результат | 49 152 UTF-8 байта с emoji и JSON escapes, затем +1 | Первый полностью сохраняется после исправления; второй явно refused |
| stderr съедает stdout budget | 720 000 байт stderr при коротком stdout | Успех без публикации stderr; отдельный канал в NUL |
| Достаточно увеличить любое число | Финальный text 49 153, wire 557 057, invalid/error/secret | Ни один не превращается в успешный частичный артефакт |

Первый прогон двух новых тестов в sandbox упал раньше эффекта на os.link с WinError 5;
он не засчитан как red продукта. Обычный host, короткий свежий gj11:
`wire-public-red.xml` — 1 passed / 1 failed именно на сравнении ожидаемого успеха.
Гипотезы о большом thought или слишком длинном final в историческом пакете
по этим синтетическим тестам не становятся установленными фактами live запуска.

## Изменения

- `grok_build.py`: только обычный JSON review получает wire budget 557 056 байт:
  `6 * ARTIFACT_CONTENT_LIMIT + 256 * 1024`. Шесть покрывает worst-case escaping;
  служебный запас 256 КиБ — выбранный bounded бюджет, не замер утраченного пакета.
- После строгого разбора JSON итоговый text отдельно ограничен прежними 49 152
  байтами UTF-8. Ничего не сокращается: пробелы, переводы строк и повторы сохранены.
- Диагностический stream, version/login/quota и меньший asked сохраняют прежние
  пределы. ServiceMetadata, секреты, lease и cleanup остаются на штатной дороге.
- `artifact_transport.py`: чистый provider hook, default None; прочие harness не
  получают нового kwarg. Сжаты два docstring для сохранения лимита 799 строк.
- V4 (`b113fff`): лимит результата импортируется через разрешённый durability seam;
  ServiceMetadata сохраняет владение `_attempt`, Grok выбирает только числовой
  предел через чистый scalar hook. Default identity не меняет прочие provider roads.
- Companion `4deb571`: один UI test helper закрывает fetching routes через
  существующий close_context, а не raw context.close. Product assets не менялись.
- Profile ceiling входит в существующий `ProviderAuthority` digest. Старый grant
  с выбранным Grok не разрешает изменившийся transport; Codex-only digest неизменен.
- `failure_reasons.py`: нейтральная фиксированная причина превышения размера
  результата, отдельно от capture refusal. Никакой сырой текст CLI не копируется.
- Добавлены два CAPPED тестовых файла; старый truncated-final fixture теперь
  ожидает ранний осмысленный отказ результата вместо переполнения всего конверта.

## Проверки

Все CLI в этих проверках — локальные дочерние двойники, credentials синтетические.
Не запускался настоящий Grok/Codex и не изменялись входы владельца.

| Проверка | Среда | passed / failed / skipped | Доказательство |
| --- | --- | --- | --- |
| Новый wire regression на базе | Windows | 1 / 1 / 0 | `wire-public-red.xml` |
| Authority на базе | Windows | 3 / 1 / 0 | `authority-final-red.xml` |
| 21 связанный модуль до v4 | UTF-8, clean `9164bed` | 1139 / 0 / 0 | `final-utf8.xml`, flags utf8=1 |
| Тот же набор до v4 | Native CP1251, `9164bed` | 1139 / 0 / 0 | `final-native.xml`, flags utf8=0 |
| Публичная дорога старого wheel до v4 | Windows UTF-8 | 56 / 0 / 0 | `installed-fake.xml`, импорт из wheel-env |
| Полный core старого SHA, UTF-8 | Windows, clean `9164bed` | 20277 / 3 / 441 | Старые архитектурные и teardown guards выявили S4/S5/S6 |
| Native CP1251 старого SHA | Windows, clean `9164bed` | 162 / 0 / 31 | Остальные CP-группы прерваны, не засчитаны |
| V4 SDK/MRO, metadata, wire и authority | Windows UTF-8 | 195 / 0 / 0 | `v4-targets.xml`, оба прежних guard без правок |
| Teardown guard и реальный Chromium UI-модуль | Windows | 26 / 0 / 0 | `v4-ui.xml` |
| Финальный core: 728 файлов, обе кодировки | Windows, clean `4deb571` | выполняется | `core-final/run-20261110T183845718955Z/results.json` |

Промежуточные 39/441/723 проверки не суммируются с финальными 1139: наборы пересекаются.
Предварительная попытка core-adjacent temp gc11 остановилась до pytest: путь уже
существовал, его не удаляли. Финальные temp были новыми и короткими.

Старый wheel 9164bed из clean checkout, SHA-256
`9790c012e7b9bfc019c7c8e55dd28000304b5edc203360c8dce5355bc8c1ecfc`.
Финальный wheel 4deb571: `agent_conductor-0.1.0-py3-none-any.whl`, SHA-256
`9d4391e92a54c71a237ec3e28404bbd67085b052b9d396d6f2c7ab50fc27caf2`.
Все 533 файла пакета побайтно совпали с Git и чистой установкой без system-site-packages.
Build первый раз не стартовал из dev venv: отсутствовал hatchling. Без скачиваний
использован уже подготовленный pinned build venv; `build-pinned.log` и `wheel-verified.json`.
Это локальный wheel для проверки, не защищённая установленная Studio и не release.

## Мутанты

Копии src/tests/pyproject вне repo, подтверждён conductor.__file__; M0 до/после,
SHA восстановлен после каждого опыта, копии удалены после проверки абсолютных путей.

| Мутант | Итог | Что различил тест |
| --- | --- | --- |
| M1 вернуть ordinary capture 48 КиБ | killed | Короткий ответ в 49 153-byte wire снова failed |
| M2 убрать decoded-final bound | killed | Поздний VERIFICATION_FAILED вместо раннего FAILED с причиной |
| M3 strip текста | killed | Потеря пробелов и перевода строки |
| M4 увеличить hard wire bound на 1 | killed | 557 057-byte wire ошибочно опубликовал артефакт |
| M5 отключить raw-sensitive response guard | killed | Поздняя защита дала VERIFICATION_FAILED; утечки не было |
| M6 дать diagnostic stream большой бюджет | killed | Фактический CommandSpec 557 056 вместо 49 152 |
| A1 не включать новый cap в digest | killed | Старый и новый grant digest ошибочно совпали |
| A2 поднимать меньший asked до default | killed | Реальный spec 49 152 вместо 2048 |

Логи старого SHA: `wire-mutations.json`, `authority-mutants-20261110175307/summary.json`.
V4: `wire-mutations-v4/wire-mutations.json`, M0 15/15 в UTF-8 и CP1251, M1–M6
все killed на тех же assertions. Проверенная копия совпала с b113fff поблобно.
M0 wire 15/15 до и после; authority 4/4 до и после. Mutator/crapper/dryer не ставились.

## Ревью Codex

Спека/безопасность: do_backend; Стандарты: do_studio; Доказательства: do_evidence.
S1 меньший asked, S2 видимость fixed failure учтены в DESIGN v2.
S3 бренд в generic runtime подтверждён штатным gate G (1 failed / 1 passed),
заменён нейтральной фразой в DESIGN v3 и коде. Сам guard/allowlist не ослаблялись.
После перепроверки открытых blocker/major у линз нет. Это локальное ревью;
полный core ещё не завершён, удалённый CI и приёмка владельцем не заявлены.
Полный core 9164bed затем нашёл S4/S5: SDK import и владение metadata circuit.
Они исправлены по v4 без изменения обоих guard. S6 — один helper старого UI-теста,
неправильно закрывавший окно; штатный helper устранил оба диагностических hits.
V4 фактический diff прошёл повторное независимое ревью Спека/Стандарты; findings закрыты.

## Чужие правки и отклонения

Чужих правок не было. Параллельные агенты работали в назначенных тестовых файлах,
коммитил ведущий. Opus недоступен; применяется ранее согласованная замена Codex.
Нет увеличения времени шага, попыток, artifact limit, новых прав или вызовов моделей.
Выбор bounded JSON вместо нового incremental collector обоснован в DESIGN.

## Не проверено и открытые вопросы

- Поведение нового транспорта на живом Grok после исправления не измерено.
- Полный локальный core выполняется; удалённый CI / Linux / macOS и полный browser
  release gate не выполнялись. Прежний UI не менялся этим backend-срезом.
- Wire budget конечен. Многочасовая автономная сессия, renew access-only входов,
  восстановление/checkpoints и потоковая история требуют отдельных доказательств.
  Репетиционные 5 действий/600 секунд не объявлены универсальным пределом продукта.

Дополнительный read-only аудит долгих задач, код 9164bed:

| Текущая граница | По коду | Последствие |
| --- | --- | --- |
| Atlas жёстко планирует пять шагов по 600 с, depth=thorough их не меняет | `arachnid-plan-model.js:35,74` | Адаптивный подбор бюджета пока не реализован |
| Штатный server: max_actions=8, max_action_seconds=3600, total=28800 | `http_api.py:92`, `server.py:547,660` | Для Do с checker до 1800 с каждому; расход считается за весь run |
| Формальный timeout до 86400 с, grant до 24 ч | `contracts.py:143`, `authorization_terms.py:17,66` | Возможности движка не равны доступным настройкам штатного server |
| Instruction 256 КиБ, artifact 49152 UTF-8 байта | `harness_workspace.py:110,688`, `artifacts.py:33,70` | Нельзя выдавать новый wire bound за снятие предела handoff |
| Access-only token покрывает попытку с запасом | `login_relay.py:467,487`, `relay_attempt.py:90` | Более долгий grant не продлевает подписочный вход |
| Resume между завершёнными действиями; unknown и expiry отказывают | `policy_service.py:160`, `policy_view.py:58,72` | Resume не возобновляет внутреннее вычисление CLI с прерванного места |

Пути в таблице: JS под `src/conductor/panel/`, Python под command/ или adapters/.
Бюджет восьми действий накопительный даже при новом grant того же run
(`policy_history.py:46–63`). Эти ограничения — долг приёмки длительных задач;
следующий срез должен выбирать видимый бюджет по сложности и квоте, предусмотреть
продление/контрольные точки, без ослабления человеческих gates и границ workspace.
Этот аудит не меняет текущие полномочия или таймауты и не создаёт новых вызовов.

## Передача

Первый код: `9164bed3de964a855ab59ecf482f606e90228571`, CAPPED обновлён там же.
Коррекция кода `b113fff`, отдельный companion `4deb57129049d370decf3166211a3d18c642ddb8`.
Матрица 9164bed прервана после 47 завершённых jobs; исходный results.json не
переписан, `interrupted.json` фиксирует причину и отсутствие живых recorded PID.
Незавершённые четыре CP-процесса и три не запущенные группы не считаются пройденными.
У первого старта финального runner preflight отказал до pytest из-за существовавшего
q-temp. Чужой путь не удаляли; выбран префикс u, все 54 пути проверены отсутствующими.
Рабочая Studio всё ещё `22267058fbf8`, порт 7830. Run `counter-src-ff2fbce-r1`
остаётся stalled: 23 записи, 3 прежних действия, ledger hash не изменился.
В 17:56:40 UTC подтверждены неизменность исходников/work-copy и 9 retired receipts.
Последний доказанный шаг: исправленный wheel прошёл offline installed road.
Первый несделанный шаг: дождаться полного core на 4deb571, проверить каждый job.
Не повторять старый Diagnose, не принимать failed результат и не запускать модели
под видом диагностики. Новый живой цикл и gates подтверждает владелец.
Артефакты: `Documents/Codex/work/grok-json-capture-1110/`; стоп при 30% остатка.
