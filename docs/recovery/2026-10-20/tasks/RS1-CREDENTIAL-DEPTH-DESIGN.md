# RS1-CREDENTIAL-DEPTH: дизайн v2

## Измерение и варианты

Две независимые линзы до кода: native_test_runner_v2 и do_rejected_inspector
подтвердили natural RED на Python 3.12.14 с неизменённым recursionlimit1000.
Настоящие bounded JSON глубиной 1000–1600 принимаются parser, затем credential_values
бросает RecursionError; codex_quota._cells тоже рекурсивен и падает на глубине1100.
Прежняя глубина600 остаётся честным положительным контролем 3.12.

A: итеративный DFS в login_home._strings и codex_quota._cells, children в обратном
порядке для прежнего обхода; точные path tuples, значения, дедуп/порог/encoding прежние.
JSON size/parser/path guards и Q10 остаются прежними; все decoded значения сохраняются.
B: заранее отказывать по глубине через typed Q10. Это требует новой политики полного
отказа и не может возвращать частичный список/пустой успех. Не выбран: существующий
bounded декодированный документ можно прочитать без рекурсивного Python стека.

## Замечания и их учёт

1.1 native: не приписывать сбой depth600 или недоступной 3.11; фиксировать version,
recursion limit, byte bound и parser acceptance до проверки публичного результата.
2.1 do_rejected: _cells тоже реально падает; его metadata fail-closed сохраняется,
но нормальный bounded credential не должен ломать штатное account admission.
2.2 every_text уже iterative, sorted distinct bytes — не менять его.
3.1 alpha_readiness_now: reversed DFS сохраняет порядок; no-op/recursive/depth cutoff
должны быть обнаружены позитивным literal witness; не менять sys recursionlimit.

## Среды и швы

CI minor versions 3.11/3.12. Локально 3.11 не найден в bounded inventory.
Для проверки изолированно staging официального PSF Windows embed Python 3.11.9
(последний опубликованный bugfix binary, не заявление о latest security patch).
URL проверен на Python.org release page; sha256 сверяется с опубликованным
messageDigest .sigstore sidecar, дополнительно MD5 release page. Sidecar checksum
используется как published hash по HTTPS; криптографическая проверка Sigstore не заявляется.
Системная установка/PATH/ассоциации не меняются; исполнять только после hash checks,
только fake JSON/offline tests. Latest patch и другие ОС остаются выпускной CI-проверкой.

Новый tests/test_credential_depth.py допускает stdlib unittest для embed runner:
public credential_values и reply_metadata на настоящем fake auth.json, literal
ожидания, shallow order/duplicates/Unicode и over-parser/size fail-closed controls.
Выбранная глубина проверяется parser прежде вызова; supported-version cases называют
точный интерпретатор. Не обходить parser mock или менять глобальный recursionlimit.
Existing tests/кодировки на 3.12 отдельно, 3.11 запускает тот же stdlib набор.
Мутанты: recursive walker, no-op/loss и неправильный metadata path; полные copies,
M0/import path/restore SHA/cleanup. Новые файлы в CAPPED, никаких моделей/CLI/циклов.

Production files: login_home.py, codex_quota.py. Test file новый credential_depth,
root CAPPED/документы. Дополнительные прежние Q8 fixture изменения допускаются только
при доказанном RED и отдельном названном решении; не смешивать их молча с RS1.
