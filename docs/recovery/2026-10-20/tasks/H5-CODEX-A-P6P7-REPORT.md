# H5-CODEX-A-P6P7 — квоты и измеренные служебные файлы Codex

Итог: локально проверено, исправленный P6 пройден | продукт `9788eb9`, тесты `4528a6c` |
R4: 222 passed; P7: 236 passed; guard: 239 passed, 0 failed в каждом наборе и кодировке |
полный `9788eb9` остановлен с 1 failed; новый core выполняется | M2 ещё не запускался.

Промежуточный отчёт, 28.10.2026. Полный green, CI, inference и цикл с Codex не заявлены.
Числа R4/P7/guard не суммируются: все три набора включают одни и те же 203 проверки caps.

## Основание и объём

- Исполнители: отдельные Codex-агенты R4 и P7; ведущий независимо прочитал оба diff.
- Worktree: `Documents\Codex\work\cdx164`; перед началом R4/P7 рабочая копия чистая.
- TASK: `91a7d2d`; классификация P7: `bc7f538`; уточнение гранта: `d8f0887`.
- DESIGN: `69c2a7d`; родительская реализация A-I1: `8a4fe5f`.
- Код и тесты: `9788eb9289bb61d5055061e7fdf3309dcc78de92`.
- Решение о завершении защищённой установки через Python: `b7366da`.
- TASK дополнен `896fef8` после находки полного core; только тест исправлен коммитом
  `4528a6cea2de7329dc9078bf3225e8ad2e2d9fe5`, продуктовый код прежний.

Цель: прочитать квоту Codex 0.164.0 по подписке через строгий продуктовый протокол и учесть
именно измеренные служебные файлы. Обратная запись входа, расширение декодера, wildcard-допуски,
новые полномочия конфигурации и вызовы модели в эту правку не входят.

## Исходное измерение P6

Измерено на защищённом продукте `8a4fe5f`: две access-only сессии завершились exit 0;
quota — 1,046 с, catalog — 0,766 с. В обеих пришли ровно `account/updated` и
`remoteControl/status/changed`. Строгий продуктовый декодер квоты их отверг:
`strict_product_decode=false`. Успешный exit этого отказа не отменяет.

Свежий `models_cache.json` имел client_version 0.164.0 и `gpt-6.1-sol` с visibility `list`;
в каталоге сервера десять моделей. Это доказательство свежего каталога, не работа модели.
Источник и access-only копии не изменились; refresh пуст, provenance не скопирован;
secret echo и диагностик refresh нет. Деревья процессов завершены, relay и временный корень
удалены. Inference не выполнялся.

Запись: `Documents/Codex/work/cdx164-live-prep/evidence/20261028T114205982864Z-p6.json`.
SHA-256: `42b8cf9279eb70db1b3640d103878fd3aa281544bfeaf7ff3e6a8358ac0062d1`.

## Изменения

R4: `codex_quota.py` передаёт в `initialize.params.capabilities.optOutNotificationMethods`
только два измеренных метода. `experimentalApi` не включён. `SubscriptionRpc.decode` не менялся:
пришедшая нотификация, включая любую из двух подавляемых, всё ещё вызывает отказ.
`test_subscription_quota.py` проверяет фактический stdin через публичный quota-read и границу CLI,
а не только значение константы. Закреплённая upstream-схема 0.164.0 задаёт вложенные capabilities,
точные имена методов и false по умолчанию для experimental API.

P7: `codex_cli.py` объявляет scratch ровно `tmp`, `log`, `.sandbox` и пятнадцать имён SQLite:
`goals_1`, `logs_2`, `memories_1`, `queue_1`, `state_5`, каждое с суффиксами `.sqlite`,
`.sqlite-shm`, `.sqlite-wal`. В expected добавлены только `models_cache.json` и `installation_id`.
Общий sanitizer не менялся: новые scratch-файлы удаляются, прежние файлы владельца сохраняются,
неизвестное новое имя отказывает. `test_codex_compatibility.py` проверяет это через quota-read
с буквальным результатом, записью в выбранный CODEX_HOME и сохранностью старых sentinel-файлов.

Уточнение `d8f0887`: payload quota RPC сам по себе не входит в `ProviderAuthority.facts`.
Изменённые login-name поля профиля P7 входят через `asdict(profile)`. Первый продуктовый запуск
получает новый грант владельца; старый грант не переиспользуется.

## Целевые проверки

Все пути доказательств ниже — внутри `Documents/Codex/work`, вне Git.

| Набор | Красная фаза на старом коде | UTF-8 | cp1251 | Доказательства |
| --- | --- | --- | --- | --- |
| R4 quota + caps | 1 failed, 18 passed: malformed_payload вместо квоты | 222 passed | 222 passed | `e164-r4-checks/red.log`, `green.log`, `cp.log` |
| P7 compatibility + caps | 2 failed, 1 passed: residue refusal | 236 passed | 236 passed | `cdx-p7-census/red.log`, `green-utf8.log`, `green-cp1251.log` |
| Независимый census guard + caps | full UTF-8 shard4: 1 failed, 3057 passed, 8 skipped | 239 passed | 239 passed | `cdx-p7-census/guard-update/green-utf8.log`, `green-cp1251.log` |

Для cp1251 проверены `utf8_mode=0` и реальная preferred encoding; для UTF-8 — mode 1.
R4 содержит 19 тестовых случаев, P7 compatibility — 33, harness login leaks — 36, caps — 203.
В зелёных целевых наборах пропусков нет. Новых файлов `src/` или `tests/` нет:
`CAPPED` не требовал дополнений.
Scoped diff-check чистый. Эти проверки не заменяют полный core.

Полный прогон обнаружил пропущенный первым scoped-набором независимый literal guard:
`test_harness_login_leaks.py::test_the_two_declared_lists_are_the_measured_ones`, строка 691
до правки, ещё ожидал старый Codex census. По TASK `896fef8` обновлены только два литерала Codex,
Claude assertions сохранены. `4528a6c` меняет только этот тестовый файл (+10/−2), без product diff.

Первый запуск внешнего R4 mutant-runner дал 4 setup errors: не был создан родитель basetemp.
Причина исправлена в runner; исходные `M0-setup-error.log` и `mutants-setup-error.json` сохранены.
Этот исход не считается ни красной фазой продукта, ни успешным уничтожением мутанта.

## Мутанты

Копии `src/tests/pyproject.toml`, проверенный импорт из копии, восстановление и сверка хешей
после каждой мутации. Копии и собственные basetemp удалены после проверки точных путей и reparse.

| Набор и мутант | Результат | Что различил свидетель |
| --- | --- | --- |
| R4 M0 | 4 passed | исправленная передача квоты и строгий отказ |
| R4: убрать account/updated из opt-out | 1 failed, 3 passed | нотификация мешает чтению квоты |
| R4: убрать remoteControl/status/changed | 1 failed, 3 passed | то же для второго метода |
| R4: пустой decoder | 4 failed | пустая реализация не выдаёт квоту и не соблюдает отказы |
| R4: разрешить нотификации в decoder | 3 failed, 1 passed | недопустимые сообщения приняты |
| R4: добавить experimentalApi=true | 1 failed, 3 passed | фактический запрос вышел за контракт |
| P7 M0 | 3 passed | поддержанный census и неизвестный остаток |
| P7: убрать models_cache.json | 2 failed, 1 passed | измеренный expected-файл ошибочно отвергнут |
| P7: пустой _take_back_login | 3 failed | уборка исчезла, неизвестное имя принято |
| P7: unexpected всегда пуст | 1 failed, 2 passed | неизвестная база принята |
| P7 восстановленный M0 | 3 passed | восстановление подтверждено |
| Guard M0 и восстановленный M0 | по 1 passed | независимый literal соответствует измерению |
| Guard: убрать log из Codex scratch | 1 failed | потеря нового объявленного имени обнаружена |

Доказательства: `e164-r4-checks/mutants.json` и отдельные M0–M5 логи;
`cdx-p7-census/mutants/RESULT.json`. Подробный P7 отчёт: `cdx-p7-census/REPORT.md`.
Дополнение guard: `cdx-p7-census/guard-update/REPORT.md` и `RESULT.json`, хеши восстановлены.

## Защищённая сборка и принятое отклонение

Исходная установка `9788eb9` собрала wheel, venv и проверила импорт, но остановилась на
`product_install.py:149`: Windows отверг сгенерированный `conduct.exe --help`, WinError 4551.
Исходный отказ сохранён в `codex-r4-product-build.log`. У venv Python подпись Valid;
сгенерированный pip launcher NotSigned. Защиты Windows не отключались, исключений не добавляли.

Решение `b7366da` разрешило завершить именно эту установку внешним bounded finalizer после
сверки архива, wheel members с установленными файлами, базовой описи и происхождения модуля.
Smoke через подписанный Python и `-m conductor` выполнен; wrapper остаётся в описи.
Это местный способ запуска, не подтверждение готовности unsigned installer к распространению.

Доказательство завершения: `codex-r4-product-finalize.log`.
Продукт: `%USERPROFILE%\DecemberCommand\product\9788eb9289bb`.
Фактический launch argv: `[<product>\venv\Scripts\python.exe, -I, -B, -m, conductor]`.

- Wheel SHA-256: `e252458077985ecdfe0dedddaf264e8b73655d91155fc198bf39f286ac2b9e5b`.
- Manifest: `%USERPROFILE%\DecemberCommand\product\9788eb9289bb.manifest.json`.
- Manifest SHA-256: `2c590f604b415bd7c91ebf814308fe0c17ac07d2bd0bf92ad004806e5283c4b3`.

## Исправленный P6: один quota-only запуск

Измерено 28.10.2026 на защищённом `9788eb9`: одна разрешённая metadata-сессия, actual revised
QUOTA_RPC, timeout 15 с. Completed, exit 0, 1,14 с; нотификаций нет,
`strict_product_decode=true`, `needs_r4_review=false`. Model/list и inference не запускались.
Источник и копия неизменны; refresh пуст, provenance отсутствует, owner ID сохранён;
нет secret echo и диагностик refresh/decode. Процесс retired, relay и временный корень удалены.

Вендор вернул одно окно: limit_id `codex`, window_id `primary`, 10 080 минут,
used_percent 64, resets_at 1793779089 (04.11.2026, 10:58:09 МСК).
Это снимок общей квоты аккаунта, не расход данной сессии; других окон измерение не показало.

Запись: `cdx164-live-prep/evidence/20261028T120420297921Z-p6-r4.json`.
SHA-256: `418f97672ad42095ff927966a8ac9add73abb295036c8ed7c520581815336ff6`.

## Полный core и ещё не проверенное

Полный core `9788eb9289bb61d5055061e7fdf3309dcc78de92` в чистом detached worktree
`Documents\Codex\work\cdx164-check` остановился после UTF-8 ordinary batch:
шесть shards passed, shard4 — 1 failed, 3057 passed, 8 skipped. Причина — старый literal guard,
описанный выше. Снимок `stopped_failed_batch`, 28.10.2026 12:13:00 UTC.
Запись: `cdx-full-164/run-20261028T115421406728Z/results.json`; исходное падение сохранено
в `utf8-shard4.log`. Native и cp1251 в этом прогоне не начинались; он не считается зелёным.

После тестовой правки начат новый полный прогон точного
`4528a6cea2de7329dc9078bf3225e8ad2e2d9fe5` в отдельном чистом detached worktree
`Documents\Codex\work\cdx164-finalcheck`.
Запись: `cdx-full-164/run-20261028T121338649620Z/results.json`.
Порядок нового прогона: native по одному файлу на процесс, затем семь ordinary shards,
сначала UTF-8, затем cp1251. На снимке 12:14:19 UTC все 14 native UTF-8 jobs завершены exit 0,
семь ordinary shards выполняются. Vendor opt-ins удалены; browser gates принудительно
не включались. Полного итога и чистого status после него пока нет: full green не заявлен.

Установленный продукт и wheel остаются `9788eb9`: новой сборки `4528a6c` не было.
Ведущий и автор отчёта сверили Git identities у обоих коммитов:

- `src/conductor` tree: `2bc965da674828624f13b18208c8b4926dd9621e`.
- `pyproject.toml` blob: `7fe28b2bcc36093350fd897ceb8062cfac67e152`.

Таким образом, новый полный прогон проверяет те же продуктовые исходники и package metadata,
из которых построен установленный wheel; соответствие wheel установленным файлам отдельно
подтверждено finalizer выше. Изменились только доказательства в тестах, не production bytes.

Единичный M2 0.164.0 / gpt-6.1-sol ещё не выполнялся. Его внешний helper прошёл отдельное
read-only ревью без блокеров; это не результат inference. До M2 нужны оставшиеся предусловия
DESIGN §6, включая законченный полный core. Работа Codex в продукте и первый цикл — отдельно.
CI/другие ОС, owner acceptance и готовность к выпуску этим отчётом не подтверждены.

## Чужие правки

R4 и P7 выполнялись параллельно только в четырёх назначенных файлах; чужие изменения сохранены.
Решения, общий TASK, коммит кода, защищённая установка и live P6 выполнялись ведущим.
Этот отчёт подготовлен отдельно без правок исходников, других документов и без коммита.

## Отклонения

Изменение запуска защищённого продукта: WinError 4551 у wrapper → подписанный Python module
launch; утверждено Codex в `b7366da`, исходный отказ сохранён.
Продуктовый код ради этого не менялся.
Ошибка подготовки basetemp в R4 mutant-runner описана выше; исправление не меняло тестовых
ожиданий и не засчитывается как доказательство поведения продукта.
Пропущенный независимый census guard добавлен в scope решением `896fef8`; исходный полный
неуспех сохранён, выполнена test-only правка `4528a6c` и начат новый полный прогон.

## Ревью Codex

Ведущий независимо прочитал оба implementation diff и принял их без находок до `9788eb9`.
Это принятие узкой правки, не зелёный CI и не завершённая приёмка. Итоговый отчёт и оставшиеся
интеграционные доказательства ожидают проверки ведущим.

## Открытые вопросы

Полный core ещё выполняется; M2, первый продуктовый запуск и приёмка не пройдены.
Блокировка unsigned console launcher остаётся ограничением распространения этой установки.
Недостающие quota windows нельзя придумывать из локального бюджета действий.

## Передача

- Последний доказанный шаг: код `9788eb9`, целевые оба режима и мутанты, независимое ревью diff,
  защищённая установка, исправленный P6 и test-only guard `4528a6c` с двумя зелёными режимами.
- Первый несделанный: получить полный итог core `4528a6c` и чистый status после него.
- Следующий шаг: ведущий проверяет результат полного core; при выполненных предусловиях —
  отдельно разрешённый единственный M2, 60 с, без смены модели, ключа и повторов.
- Не повторять: исходный P6 показал две нотификации, исправленный P6 успешно прочитал квоту;
  обе записи сохранены выше. Не повторять model/list, P11, P8/P9 или metadata без нового решения.
  Старый full `9788eb9` имеет сохранённое падение; новый exact `4528a6c` уже выполняется.
- Product commit: `9788eb9289bb61d5055061e7fdf3309dcc78de92`; test-only follow-up:
  `4528a6cea2de7329dc9078bf3225e8ad2e2d9fe5`; `CAPPED` не менялся.
- Документ: только этот REPORT; при начале подготовки HEAD `b7366da`, status чистый.
  Отчёт оставлен незакоммиченным для ведущего.
