# ALPHA-CORE-REPAIR

Владелец 11.11.2026 поручил исправить два architecture и 17 fixture/snapshot
failures exact6d4bf97 без ослабления защит, новый кандидат и полный Windows core
в UTF-8/CP1251; CI только если зелёный. Без моделей/нового цикла, стоп при12%.
Стартовый HEAD 2d21ce7, recovery/2026-10-20, status чистый, остаток16%.
WORKING-STANDARD/CONTRIBUTING/scope обязательны. Старый красный run и принятый
counter-src-19956c8-r1 не менять/не повторять; protected Studio/server99419 не трогать.

## Объём и разделение

I1: перенести неизменённый pure subscription_account.py из command в adapters,
обновить два product imports, test_subscription_account imports и CAPPED path.
Без provider-neutral/SDK waiver, старого compatibility shim или безопасных defaults.
Исполнитель владеет только этими файлами; при другом требуемом source diff — к root.

I2: tests/test_accept_capture.py, test_local_test_checker.py, test_patch_do_policy.py,
test_attempt_rejected_protocol.py. Partial doubles соблюдают LoginRoad contract,
Q6 account facts проверяются отдельно/точно, verification/seal guards сохранены.

I3: tests/test_harness_login_method.py, test_harness_subscription_login.py,
tests/fixtures/h5_core_snapshot.json. Создать fake primary credentials для всех
method/config cases, включая negative. Golden изменить только в двух Claude facts:
20 schema types, omitted field и ровно12 env guards по утверждённому Q8.

Три исполнителя могут писать только в перечисленные непересекающиеся файлы.
Root единолично пишет общие docs/решения, интегрирует и коммитит. Остальное readonly.
TASK/DESIGN и уточнения вступают в работу отдельными docs commits до реализации.

## Доказательства и закрытие

RED уже измерен полным core в обоих modes:19failed, raw kit alpha-candidate-1111.
Сверить каждый симптом с source, не выдавать вывод по коду за runtime measurement.
Целевые полные модули и соседние Q6/Q8/Q10/SDK guards в обеих кодировках; новые
guard assertions проверить смысловыми мутантами в source/test copy, M0 до них,
каждый исходник восстановить с проверкой hash. Отдельное cross-review до коммита.
Без retry/skip/waiver/timeout или assertion ослаблений. Если новый доказанный blocker,
сначала причина/дизайн, не наращивать похожие исправления вслепую.

После code+tests commit зафиксировать новый SHA и чистый detached worktree.
Внешний runner предыдущего TASK переиспользовать после чтения, новый kit/temps,
21 native(single-file)+7ordinary на mode, max4 ordinary, UTF8 до CP1251.
Убрать CONDUCT_ opt-ins/наследуемые overrides, exact SHA/import/codec witnesses,
PID/stdout/JUnit/counts/skips и clean before/after. Native запуск с нужным доступом,
короткие новые basetemp<=26; без реальных vendor CLI или модели.

Если оба modes зелёные: проверить отсутствие remote ref и push exactSHA в новую
candidate/alpha-2026-11-11-<shortSHA> на origin для ci.yml; no force/main/recovery
rewrite/release/tag. Подтвердить CI run/checks exactSHA, не называть running зелёным.
Если красный — сохранить полный результат и причину, CI не запускать.
При12% остановить через STOP marker новые jobs и только own recorded child PID;
сохранить interrupted, отчёт/handoff и первый несделанный шаг, не засчитывать green.

Kit: C:/Users/Пользователь/Documents/Codex/work/alpha-core-repair-1111.
Старые reparse temps не удалять по маске. Cleanup только exact own roots после
подтверждённого выхода процессов, plain scan; сомнительные roots сохранить.
