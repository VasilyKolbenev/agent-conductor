Итог: локально проверено, красный | 6d4bf97 | 20567 passed, 19 failed | без waiver | исправить.

# ALPHA-CANDIDATE-CORE: полный Windows core

## Основание и кандидат

- Владелец поручил полный core текущего HEAD в UTF-8 и CP1251, CI только при зелёном
  результате. Новых моделей и циклов нет. Последний порог владельца — 12% остатка.
- Прочитаны AGENTS.md и WORKING-STANDARD.md. TASK f0ade81, уточнение 04bf5cf.
- Кандидат: `6d4bf97228529a7def649f912c1b8227830ac19c`, ветка recovery/2026-10-20.
  Служебные TASK/REPORT commits не включены в проверяемый SHA и не подменяют его.
- Чистый detached worktree до и после:
  `C:/Users/Пользователь/Documents/Codex/work/alpha-candidate-1111/source`.
- Чужие правки: нет. В этом задании product source, тесты и CAPPED не менялись.

## Выполнение

Использован прочитанный прежний full-core.py с необходимыми изменениями внешнего
контроллера: свежие короткие zu/zc temps, явный single-file native partition для
test_process_profile.py и STOP marker с завершением только собственных Popen PID.
Уточнение зафиксировано 04bf5cf до запуска. Root и отдельный reviewer проверили
контроллер; AST/help/dry inventory прошли без запуска тестов.

Финальный controller SHA-256:
`eaa73ad48668ce0d1a008bc956b426f70c1bbd534f81fd1e4bb99083be5a3553`.
Inventory: 742 файла; на кодировку 21 native файл отдельными процессами и семь
обычных shards, не более четырёх параллельно. UTF-8 полностью до CP1251.
Все CONDUCT_ opt-ins и переопределения Python/Git очищены. Сохранены import/flags/
encoding witnesses. Нативный доступ Windows разрешён для fake/local core, без
включения vendor/model opt-ins. Test timeouts и assertions не ослаблялись.

Запуск 11.11.2026, 20:49:20–21:35:57 МСК. Session 61761 завершена с exit 1.
Все 56 групп завершены: 46 без падений, 10 с падениями. Все 42 native-группы
завершены без failed/errors; opt-in проверки внутри них имеют явные skips.
Контроллер 20912/28176 и все 56 записанных pytest PID завершены.

## Результат

| Среда | pytest passed | subtests passed | failed | errors | skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| Python 3.12.14, UTF-8 | 20567 | 4 | 19 | 0 | 441 |
| Python 3.12.14, native CP1251 | 20567 | 4 | 19 | 0 | 441 |

В JUnit по 20571 passed: это 20567 плюс четыре subtests, не дополнительные
независимые тестовые методы. По четыре warnings на кодировку. Все 19 failure IDs
между кодировками совпадают. Повторов и исправлений в ходе прогона не было.

Пропуски на кодировку: 170 требуют CONDUCT_OLD_GIT, 138 относятся к macOS/POSIX,
71 требует symlink privilege, 52 — vendor/native/live opt-in либо отсутствующий
архив, два — отсутствующий hatchling, восемь — другие явные platform/threshold
сценарии. Точные причины каждого skip сохранены в aggregate.json и JUnit/logs.
Skips не считаются passed и не доказывают работоспособность четырёх подписок.

## Причины падений: независимый разбор без изменения кандидата

| Модуль | Cases | Вывод и первый необходимый шаг |
| --- | ---: | --- |
| test_alpha1_gate_g_provider_breadth | 1 | Source defect: provider literals нового subscription_account.py находятся в request-path package. Перенести pure vendor helper на adapters boundary. |
| test_command_adapters | 1 | Source defect того же размещения: relay_attempt.py импортирует ..subscription_account вне разрешённых SDK imports. Sibling helper сохраняет архитектурный guard без waiver. |
| test_harness_core_snapshot | 2 | Старый golden inventory: различия только в утверждённых Q8 schema/omitted fields и 12 forbidden_env. Адресно обновить два Claude facts, сохранить строгую equality. |
| test_accept_capture | 2 | Partial Checker double оставляет _begin_road пустым; trace подтверждает отсутствие read-back state. Переиспользовать LoginRoad reset/account hooks. |
| test_local_test_checker | 3 | Такой же partial Checker double; сохранить runtime-substitution/event assertions, добавить действительный reset/account contract и verifier.instance_id. |
| test_harness_login_method | 3 | Fixtures не создают обязательный auth.json. Два trace явно показывают Q10 refusal, для третьего причина установлена по коду. Seed fake credential во всех cases, включая negative cases. |
| test_harness_subscription_login | 4 | По коду positive fixtures используют отсутствующие Claude credentials либо пустой Codex home. Trace показывает failed без подробного отказа; runtime-причину сверх этого не считать измеренной. Создать реальные локальные fake fixtures. |
| test_patch_do_policy | 2 | Общий census evidence не учитывает два Q6 provenance. Outcome/apply/check уже прошли; отдельно проверять verification и exact-bound unverified account facts. |
| test_attempt_rejected_protocol | 1 | Лог явно показывает два новых subscription_account_v1/unverified. Разделить точный census seal/verification и Q6 provenance, сохранив оба набора assertions. |

Архитектурные нарушения подтверждены source guards и строками
command/subscription_account.py:10–17,41 и adapters/relay_attempt.py:377.
Недостающий read-back state подтверждён trace independent_transport.py:74;
простая подстановка безопасного default в production исправлением не считается.
Для конкретных Q6 строк patch-policy тип не напечатан: происхождение установлено
по dataflow; дополнительные None измерены. В attempt-rejected типы напечатаны.
Разбор выполнен отдельным агентом и проверен root; новых тестовых запусков нет.

## Доказательства и сохранность

Kit: `C:/Users/Пользователь/Documents/Codex/work/alpha-candidate-1111`.
Run: `run-20261111T174920637867Z/`, содержит results.json, 56 JUnit/log/job receipts,
aggregate.json с failure IDs/skip reasons и owned-process-exit.json.
session-61761-exit.json подтверждает наблюдавшийся выход сессии.

- results.json SHA-256:
  `01e395c975f66a47fd06b3828dc8ba521cd41f6e0ede3f67f17c3904eeffae86`.
- aggregate.json SHA-256:
  `978fb07bd9ec998ba5af1de8cf44fcdf5307d4a149a322a722aefeb23a98eca0`.
- Принятый counter-src-19956c8-r1: прежние 46 записей, SHA-256
  `60f2621862e977456552be6d58044cb603808cd66c4173a6c09a1e0b99825ad6`.
  Root повторно сверил hash; цикл и его приёмка не повторялись.
- Защищённая Studio по-прежнему 19956c8, foreground server 99419 на порту 7830.
  Сервер и продуктовые файлы этим заданием не изменялись.

## Уборка внешних temps

Первый Apply helper отказал до удаления: PowerShell 5 прочитал UTF-8 launch receipt
как ANSI и не сопоставил кириллический путь. Отдельный encoding probe подтвердил
default_matches=false, utf8_matches=true. Изменены только три чтения receipt на
явный UTF-8; strict path/PID/reparse guards сохранены, независимо перепроверены.
Это исправление внешнего скрипта, не изменение кандидата или повтор core.

Финальный temp-audit.ps1 SHA-256:
`7b2b56c3fa4e3c6c4ee387fedd4319ea56a7c382077fbe817a49d06df8301bd8`.
Default audit и последующий Apply подтвердили выход 58 PID. Из 56 точных roots
30 plain удалены, шесть отсутствовали, 20 с reparse сохранены целиком без обхода
их targets. Ошибок удаления нет. Не удалять оставшиеся roots по маске.
Квитанции в kit: temp-audit-20261111T1837396636488Z.json (отказ),
temp-audit-20261111T1839503450917Z.json (audit),
temp-audit-20261111T1840577212868Z.json (Apply).

## Не проверено и отклонения

CI не запускался: условие зелёного локального core не выполнено. Push, candidate
branch, release/tag не создавались этим заданием. Новый wheel/installed road,
Linux/macOS, чистые подключения четырёх harness, UX-проходы и owner acceptance
этим результатом не закрыты. Старый зелёный core не заменяет этот красный SHA.

Отклонения: внешний runner получил обязательную коррекцию native partition и
ограниченную остановку, утверждённые 04bf5cf. Новый порог владельца 12% соблюдён.
Ни retry, skip, waiver, ни ослабления продукта для зелёного не было.

Мутанты: не применимо — это полный verification run, source/test assertions не
менялись. Внешний runner проверен dry inventory и двумя чтениями; исходный код
кандидата оставался неизменным.

## Проверка документов

test_file_endings: по девять passed в UTF-8 и CP1251. Первый отдельный запуск
получил 3 passed / 6 errors на кодировку: sandbox запретил mkdir короткого temp
в USERPROFILE (WinError 5). Оба исходных лога сохранены как docs-utf8/cp1251.log.
После подтверждения причины этот ненативный guard выполнен с новыми temps в
разрешённом workspace; финальные логи docs-final-utf8/cp1251.log и JUnit сохранены.
Это отдельная проверка документов, не повтор полного core. Оба её plain temp
удалены после проверки точных абсолютных путей и отсутствия reparse points;
receipt docs-temp-cleanup.json. Ошибки sandbox не включены в числа полного core.

## Ревью Codex

Root проверил exact SHA/clean states, сводные числа из results.json и сохранность
принятого ledger. Независимые controller/failure reviews выполнены. Кандидат
не одобрен для CI/выпуска из-за перечисленных 19 failures.

## Передача

Последний доказанный шаг: полный Windows core exact 6d4bf97 в обеих кодировках,
одинаковый красный результат и завершённые процессы.
Первый несделанный: минимально исправить размещение account-proof helper и
перечисленные fixtures/snapshots с сохранением положительных и отрицательных
стражей, затем зафиксировать новый кандидат и полностью проверить его до CI.

Не повторять: этот красный SHA без изменения доказанной причины, принятый
counter-src-19956c8-r1, vendor/model probes. Сырые доказательства сохранять.
Код и CAPPED этим заданием не изменены; TASK/REPORT — отдельные local docs commits.
Открытые вопросы: последующие release gates остаются в ALPHA-NEXT-2-DAYS.md.
