Итог: локально проверено | d7334d6 | 20587 passed, 0 failed/codec | C1 учтён | CI с отказами.

# ALPHA-CORE-REPAIR

## Основание и изменения

Владелец поручил исправить два architecture и 17 fixture/snapshot failures,
новый кандидат/full core UTF-8/CP1251 и CI только при зелёном. Без моделей/циклов,
стоп при12% остатка. Старт HEAD2d21ce7 чистый; TASKd6b4397, DESIGNv2 94b41ab.
WORKING-STANDARD/CONTRIBUTING/scope прочитаны. Чужих правок нет.

I1: pure subscription_account.py перемещён из command в adapters, два отложенных
product imports, два test imports и CAPPED path обновлены. Raw byte SHA сохранён:
`b97d7573a94c02dcaf035a26be4c64e25cfb35b9f0a71e668a5e635a95fa3502`.
Нет shim/re-export, изменений proof/hash/freeze или waiver архитектурных guards.

I2: partial Checker doubles используют реальные LoginRoad reset/account hooks,
verifier имеет instance_id. Evidence census сохраняет весь ordered kind list,
строгие seal/verification expectations, отдельно ровно два Q6 unverified provenance
с точными actor/role/request/action/attempt bindings и literal proof. Ни один
production read-back default/отказ или checker integrity guard не изменён.

I3: plain fake primary credentials создаются во всех method/config cases, включая
negative, и в subscription positives. Homes — действительные tmp fixtures.
Golden меняет только два Claude facts:20 schema names/types, omitted
ccOnboardingFlags, ровно12 forbidden env. Strict snapshot equality сохранена;
остальные snapshot facts не менялись. test_harness_subscription_login:779строк.

## Доказательства до кандидата

RED: исходный full core exact6d4bf97,19failed в обоих modes, raw предыдущего TASK
сохранён; подробности ALPHA-CANDIDATE-CORE-REPORT.md. Новых моделей/vendor CLI нет.

| Набор целых модулей | UTF-8 | CP1251 |
| --- | --- | --- |
| I1: account, provider breadth, SDK, module graph, CAPPED | 731 passed | 731 passed |
| I2: четыре исправленных + account/read-back | 77 passed,1 skipped | 77 passed,1 skipped |
| I3: оба login + core snapshot, native filesystem access | 108 passed | 108 passed |
| Root final CAPPED/file endings | 317 passed | 317 passed |

Во всех финальных targets failed/errors0. I2 skip: Windows не выводит Git mode
из chmod. Наборы пересекаются, их counts не суммировать. Import/codec witnesses
сохранены. I3 первый sandbox-run:98passed/8failed/2skipped в каждом mode,
os.link WinError5; native run с новыми temps устранил ограничение среды без кода
и ослабления tests. Оба исхода сохранены, sandbox не считается зелёным.

## Мутанты и ревью

I1 mutants не применимы: helper побайтно прежний, asserts guards не менялись.
I2 external copy: M0=5passed; remove-account, wrong-binding, runtime-integrity
bypass — каждый2failed/3passed,0errors/skips. Все source hashes восстановлены.
I3 external copy: M0=20passed; method admit-all4failed/2passed, config bypass
6failed/1passed; Q8 schema/type, omitted и env omission — каждый2failed/2passed.
Все восемь смысловых мутантов пойманы; copies удалены после plain scan.

Две design-линзы A/B дали GO, уточнения приняты v2 коммитом. Cross-review:
I2 проверил I1 bytes/boundaries, I1 проверил I3 deny AST/точный golden delta,
I3 проверил I2 hooks/census/bindings. Root прочитал source/test diff, guards
не ослаблены; staged diff чистый. Код/CAPPED сохранены7368dc0, C1 test-only сохранёнd7334d6.

## C1: новый blocker и дополнительный срез

В полном7368dc0 UTF8 зелёный, CP interruption[with_input-CancelWait] дал TypeError
None>int в observer. Writer уже atomic os.replace; причина OS-read неизвестна.
TASK/DESIGNv3 0f7cd06, независимый C1 review принят0930f72. Четыре гипотезы
различены: потеря initial baseline, None-as-progress, финальный reread, нет роста.
Детерминированный RED через реальный InterruptedRun.spawn/owned.proc.wait:
3failed/0passed. Изменены только observer и его test seam в существующем файле:
baseline берётся из wait_for_int, один sample на итерацию, valid >baseline
сохраняется без последнего перечитывания. Прежние deadline5/sleep.01 сохранены.
Постоянный None/нет роста дают прежний именованный отказ, не synthetic interruption.
Ни product code, ни _fakeproc, ни тела четырёх native cases не менялись.

Полный interruption-модуль:7passed в каждой кодировке, failed/errors/skipped0.
M0=3passed; baseline, None-progress, reread, no-op accept, deadline mutants дали
3/2/3/2/2failed,0errors/skips. Source hashes восстановлены, copy удалена.
Независимое review и root дали GO. Evidence: kit/interruption, девять plain temps
удалены после проверки точных путей. Полный7368 результат не переигрывать/не стирать;
после C1 новый кандидат должен пройти полный core заново.

## Полный core и CI

Финальный кандидат: `d7334d6c2d123a8e5949d12122faa6cb44eda68e`.
Чистый detached source до/после, imports/flags/codec witnesses сохранены.

| Кандидат | Кодировка | pytest passed | subtests | failed | errors | skipped |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 7368dc0 | UTF-8 | 20584 | 4 | 0 | 0 | 441 |
| 7368dc0 | CP1251 | 20583 | 4 | 1 | 0 | 441 |
| d7334d6 | UTF-8 | 20587 | 4 | 0 | 0 | 441 |
| d7334d6 | CP1251 | 20587 | 4 | 0 | 0 | 441 |

Первый полный7368 результат красный и сохранён, CI для него не запускался.
Его отдельный observer failure устранён C1 с детерминированным RED/мутантами.
Финальный d7334d6:56/56 групп,42 single-file native +14 ordinary, max4ordinary;
оба режима по20591 JUnit passed/21032 total (включая четыре subtests),4warnings.
Старые результаты не переигрывались, один и тот же SHA вслепую не повторялся.

Exact testcase delta от7368:только три новых observer cases,0removed в обоих modes.
От исходного6d4 после нормализации CAPPED rename ровно два GateG command-file
parameters покинули request-path enumeration вместе с перенесённым helper.
Сам helper проверяется неизменённым SDK rglob value guard, без нового exemption.
Его raw byte SHA прежний; все18 оставшихся исходных failing IDs прошли.
Пропущенные case IDs не изменились;96 точных skip reasons сохранены. Основные
группы:170oldGit,138macOS/POSIX,71symlink privileges,52native/vendor/archive,
2hatchling,8other explicit scenarios. Skips не есть passed или live harness proof.

## Артефакты и сохранность

Первый kit: `C:/Users/Пользователь/Documents/Codex/work/alpha-core-repair-1111`.
Его run-20261111T200853204052Z содержит красный7368 full result, все JUnit/logs,
aggregate и testcase deltas, actual session31590 exit1 и отсутствие59PID.
Results SHA: `9894e0b802988c65af2e726c59df39194d5d5485da8882c2007da9844be676fb`.
Aggregate SHA: `4fe135f4766c70075210ac4982fb8bd95b6011257c645e1e80839111d2c861f1`.
Target/mutant evidence находятся в architecture/,checker/,login/,interruption/.
Наборы пересекаются: targets и два режима не суммировать как unique test methods.

Финальный kit: `C:/Users/Пользователь/Documents/Codex/work/alpha-core-repair-c1-1111`.
Run-20261111T210026748326Z: полный green, все56JUnit/log/job receipts, aggregate,
оба testcase-delta, session18348 observedexit0 (toolchunk033472),59PID отсутствуют.
Results SHA: `026b21673ce324fa7bb031a7e441dc6b7e61dd0a54bec46c8a2ce89f0c4acd9f`.
Aggregate SHA: `de6fd201994482257dc498d7c9ff3beaae823810a73bd6987d603c31dd41c64e`.
Final runner SHA: `5cacc58d7f3509e25c2bcf39b4285e77e5f54feed69d5a9e8fb07d01e3d52652`.
Ровно два z->x prefix bytes отличаются от прочитанного прежнего runner; STOP,
PID ownership/single-native/clean state/opt-in guards прежние. Все56temps до него
отсутствовали. Неиспользованный y prefix имел34unknown roots и не запускался.

Root независимо проверил all56 passed/zero failed/errors и exact clean SHA,
прежний принятый counter-src-19956c8-r1:46records, SHA
`60f2621862e977456552be6d58044cb603808cd66c4173a6c09a1e0b99825ad6`.
Живых моделей/CLI vendor calls/нового продуктового цикла0; сервер99419/7830 и
защищённая Studio19956c8 не изменялись. Исходный проект владельца не менялся.

Финальный cleanup helper967a5370 проверен root, его actual exit receipt совпал.
Apply temp-audit-20261111T2152344282125Z.json:30plain roots удалены,6отсутствовали,
20reparse roots сохранены целиком без обхода targets. Остальные точные roots и
отклонения cleanup хранятся в per-slice temp-cleanup receipts; не удалять по маске.
I3 sandbox os.link отказы и последующий native outcome сохранены раздельно.
Cleanup старого7368 сначала отказал из-за несовпадения exit schema, затем live
recorded PID во время следующего run; ничего не удалял до успешного нового аудита.
Явный UTF-8, closed actual receipts/PID/path/reparse guards сохранены.

## CI: запущен, новые выпускные блокеры

После зелёного core проверена пустая remote ref и выполнен один no-force push
exact d7334d6 в `candidate/alpha-2026-11-11-d7334d6`. main/recovery не переписаны.
Remote ref и CI head_sha независимо подтверждены через GitHub connector.
[CI run43106716036](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43106716036),
event push, attempt1. Это выполнение разрешённого conditional CI, не release/tag.

Снимок ci-run-latest.json:12jobs,1success(build one wheel),6failure,5in_progress;
run в целом ещё in_progress. Локальный green не объявлен удалённым green.
Четыре POSIX core jobs и два installed-wheel road уже красные. Root и отдельный
reviewer прочитали representative logs; это два разных дефекта проверок:

1. Collection: tests/os_boundary_box.py:23 импортирует Windows-only probe до
   существующего platform gate; пять Kimi modules ломаются на POSIX. Ещё один
   top-level import adapters._winlaunch в test_patch_do_native.py:9. Ubuntu3.12
   имеет6collection errors/exit2 до выполнения тестов; macOS3.11 подтверждает тот же путь.
   Следующий срез: отложить Windows-only imports до уже защищённого использования,
   сохранить native refusals/существующие условия и POSIX pure coverage, без waiver.
2. Installed road: wheel стартует0.4s, затем SHA mismatch route `/`/exit1.
   installed_probe.py:27 ожидает studio.html; server.py:275–276 отдаёт ENTRY_PAGE,
   server_assets.py:43 задаёт arachnid.html, это закреплено server asset test:677.
   Следующий срез: provenance корня из owning ENTRY_PAGE; пять Studio screen
   assertions проверять на /panel/studio.html и добавить witness Arachnid root.
   Сохранить все SHA/content-type/asset census проверки, не принимать любой body.

CI/source edits или повторных запусков CI после этих новых находок не было.
Exact logs/status/source proof: finalkit/ci-diagnosis/diagnosis.json, SHA
`6c998cbfa57ee40e0684e10abdb0d5c1e5ff3e95face1f9de2ccd1f52264ed33`.
Другие jobs продолжаются; их полный итог ещё не засчитан. Сборка wheel success
не закрывает installed road и не разрешает выдачу пользователям.

## Отклонения и открытые вопросы

Root технически утвердил новый C1 blocker по измеренному факту, TASK/DESIGNv3
закоммичены до I4. Причина конкретного OS-read остаётся неизвестной; исправлена
доказанная логика наблюдения int|None. Deadline/retirement assertions сохранены.
Ни skip/retry/waiver, ни ослабления продукта для зелёного не вводились.
Новых сторонних инструментов не ставили. Рабочая копия до задачи без чужих правок.
Ревью code/test slices root и cross-reviews:GO; CAPPED сохранён в source commits.
Мутанты:13семей из I2/I3/I4 пойманы; чистое I1 перемещение не меняло assertions.

Локальные проверки не закрывают remote Linux/macOS/browser/installed roads,
чистые четыре подключения, четыре пользовательских UX-прохода и owner acceptance.
Новая защищённая установка и release этим TASK не выполнялись.

## Ревью Codex и передача

Root принял scoped repairs после независимых reviews, проверил полные локальные
данные, сохранность и actual CI checkout. Статус: локально проверено; CI имеет
отказы, не готово к выпуску. Документы — отдельный local docs commit после кода,
он не подменяет проверяемый/pushed d7334d6.

Последний доказанный: исходные19 исправлены; C1 детерминированно исправлен;
новый immutable d7334d6 прошёл56/56 в UTF-8/CP1251; CI запущен на exactSHA.
Первый несделанный: закрыть POSIX collection и installed-root provenance с
сохранением guards, проверить оставшиеся jobs; новый кандидат/core/CI до выпуска.
Не повторять красные6d4/7368 или текущий CI без изменения доказанной причины,
не повторять принятый модельный цикл. Порог12%, последний замер15%.

Остановка12.11 по прямой просьбе владельца до завтра. После checkpoint новых
тестов/исправлений не выполняли; финальная проверка новых docs ожидает продолжения.
CI уже запущен и остаётся на GitHub, новых CI runs не создавали.
