Итог: RS1 локально закрыт и принят ревью | код 1147b86 | 200 passed + 4 subtests
на кодировку Python3.12, 5 stdlib tests/codec Python3.11 | ограничения ниже |
следующий шаг — единый release candidate, полный core/CI и чистый onboarding.

# RS1-CREDENTIAL-DEPTH

Ведущий Codex, исполнитель native_test_runner_v2, независимые линзы
do_rejected_inspector и alpha_readiness_now. База 0aeb943, repo чистый;
TASK c2db53f, DESIGN v2 e65c32b. Чужих правок нет; root отдельно поправил
два устаревших Q8 fixture по TASK fb50aa4/a3421b6, test-only код f9df475.

## Причина и изменение

Decoder JSON и рекурсивный Python обход имеют разные пределы. Небольшой файл,
который decoder уже принял, мог упасть в _strings или _cells с RecursionError.
Перехват с пустым/частичным списком потерял бы значения защитного сканирования.
Оба обхода заменены итеративным DFS с обратным добавлением children, сохраняя
порядок, exact tuple paths, threshold12, дедуп и surrogatepass. every_text уже
итеративен, не менялся. File size/parser/path guards и Q10 не ослаблены.

## Реальные локальные интерпретаторы и RED/green

| Измерение | Python 3.11.9 | Python 3.12.14 |
| --- | --- | --- |
| Старый код, 44 real fake JSON, recursionlimit1000 без изменений | 22 приняты decoder, 18 из них RecursionError; первый проверенный сбой depth500 | Все44 приняты,20 RecursionError; первый проверенный сбой depth1000 |
| После исправления, тот же набор | Все22 принятых сохраняют exact values,22 parser refusals не обходятся | Все44 сохраняют exact values |
| Финальный тот же stdlib unittest набор | 5 tests OK UTF8,5 OK native CP1251 | 5 tests OK UTF8,5 OK native CP1251 |

JSON dict/list fixtures меньше64KiB, parser acceptance проверяется до public reader.
Depth600 на3.12 действительно проходил и до правки; прежний отрицательный вывод
из одного такого probe не переносился на другие глубины или Python3.11.
Подтверждение 3.11 получено до production patch. Sys recursionlimit не менялся.

Системный3.11 в bounded inventory не найден. В kit изолированно размещён официальный
PSF embed3.11.9: https://www.python.org/downloads/release/python-3119/ .
SHA256 009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b
сверен с published messageDigest .sigstore, MD5 с release page. Это сверка published
hash по HTTPS, не криптографическая проверка Sigstore. PATH/system install не менялись.
Старый patch взят только как доступный официальный offline test binary; latest patch,
другие ОС и все версии >=3.11 этим не объявляются проверенными: остаётся release CI.

## Дополнительные проверки и мутанты

Kit вне Git: Documents/Codex/work/credential-depth-1111.
Python3.12 targets (195 соседних+5 новых методов): 200 passed +4 passed subtests
в UTF8 и CP1251, errors/skips0. XML204 cases включает subtests, не 204 разных метода.
RED pytest9.1: 3 failed/4 passed +2 passed subtests; XML9 cases включает дочерние.
Raw counts сохранены, отдельно stdlib runner подтверждает ровно5 методов.
323 source/CAPPED/module graph/file ending guards passed в каждой кодировке.

Полная src/tests/pyproject copy, проверенные imports/restore SHA, M0 без ошибок;
recursive_strings mutant ловят deep subtests, empty-loss — literal tuple,
wrong metadata path — literal account mapping. Три мутанта пойманы, копия удалена.
results.json SHA ccad35e09c6c44e6651a2fcdd63e70b6ed3ac40022658dbb3e51e007c9c84ebf.
mutants.json SHA cf2b61771863e98931f3350f1f5641bbc68a90bfaa49c952d04bda042858608f.
crapper/dryer/mutator не ставились. Новый test_credential_depth.py внесён в CAPPED.

## Сохранность, ограничения и передача

Никаких моделей/vendor CLI/повторного цикла/настоящих profiles. Принятый ledger:
46 records, SHA60f2621862e977456552be6d58044cb603808cd66c4173a6c09a1e0b99825ad6 прежний.
Fake homes удалены; guard temps очищены. Relay fixture temp links/junction entries
сняты только по своим именам без обхода целей, затем plain temp tree удалены;
closure-audit.json. Официальный test runtime+ZIP+published checksum оставлены в kit.
Рабочая Studio остаётся на19956c8, server99419/7830; не переустанавливалась.
Полный core/CI/installed road/OS lease recovery и новые аккаунты не проверялись.

RS1 вместе с surrogate fix919fed1 и Q10 fail-closed7742eaa локально выполнен.
Code review: blockers/major нет; порядок/path/полнота прочитаны независимо от автора.
Статус только локально проверено, не выпускная готовность. Не повторять законченные
probes/targets/mutants и принятый цикл. Следующий шаг — release candidate/core/CI,
четыре собственные подписки/чистый пользователь/UX/owner acceptance. Порог15%, остаток16%.
