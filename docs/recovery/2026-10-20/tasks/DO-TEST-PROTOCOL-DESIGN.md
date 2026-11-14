# DO-TEST-PROTOCOL — DESIGN v3

База `e009342`, TASK в этом коммите. Код продукта ещё не изменён.
Причины подтверждены live-отказом и чтением source, не догадкой о лимитах.

## Два варианта

A. В одном Do: prepare patch → apply → bounded local tests → capture/seal →
independent checker. Сохраняется один action claim и deadline; feedback относится
к точным изменённым файлам и тестам. Рекомендуется как минимальный вертикальный срез.

B. Отдельный graph test-step между изменением и checker. Он видим оператору,
но меняет число действий и связь отдельного verifier с исходным Do. Для текущего
контракта потребует больше изменений и новых правил планирования. Отложить.

Выбран A после source-линз; wiring блокируется до native witness доверенного runner.
Нельзя скрыто считать имеющийся import внешних counters полноценным исполнением.

## Test plan и runner

Тестовая политика задаётся проектом/пользователем и входит в просмотренные
инструкции и digest гранта. Модель не выбирает новый исполняемый файл или shell.
Первый runner может поддерживать Python unittest, но сам протокол не фиксирует
test_counts.py, язык или один CLI навсегда. Неизвестный toolchain требует явной
настройки; не притворяться, что любое произвольное приложение уже поддержано.

Runner использует существующие ProcessRunner и offline container_profile,
home=None, без vendor _attempt/login relay. Доверенный executable/install pin
проверяется до эффекта и виден в preview. Read-only дерево, writable scratch,
пустой env allowlist с необходимым штатным OS environment. Нет host fallback.
Native witness: pinned Python действительно стартует в такой границе, импортирует
unittest из своей stdlib и читает точную копию проекта. До этого wiring не готов.

Точный argv строит продукт из ограниченной политики. Python bootstrap импортирует
доверенный unittest до добавления project path: проектный unittest.py не становится
runner. Timeout ограничен остатком Do deadline; отдельные бесконтрольные 60 секунд
не добавляются к разрешению. Не терять stderr: unittest пишет туда протокол.
Ноль тестов, timeout, ошибка или усечение вывода не дают passed.

## Сохранение протокола

Результат содержит argv, cwd, status, exit code, stdout/stderr, признак усечения,
счётчики и run/action/attempt, digest политики и инструментов, tree/snapshot digest.
Входные и итоговые байты сверяются вокруг теста и вокруг checker. Секреты и
чувствительные файлы проходят имеющиеся guards перед записью и показом.
Checker получает этот документ до своего запуска, а не поздний внешний отчёт.
Обычные test failures передаются как реальные failures для feedback; ошибка
инфраструктуры или неизвестный исход останавливает выполнение, не маскируется.
Точное правило повторной проверки/восстановления фиксируется до реализации:
один тестовый прогон на attempt; незавершённый marker не разрешает новый spawn.

## Отклонённый результат

Снимок сейчас записывается accept_capture до checker. Его digest становится
доступен UI только через успешный record_dispatch. CorrectionFeedback имеет
хеши изменённых файлов, но не полную связь с накопленным sealed snapshot.
Простого снятия условия succeeded в attempt_detail недостаточно.

Нужна явная неизменяемая связь attempt → tree/snapshot/test evidence, сохранённая
до checker и привязанная к результату отказа. Представление читает именно её;
не ищет похожий snapshot и не читает нынешний live workspace. Доступность снимка
не приравнивается к принятию. Existing acceptance требует verified как прежде.
Inspector отображает rejected, checker, findings, diff и тестовый протокол;
нет протокола/снимка — отдельное честное состояние, не пустой успешный результат.

## Доказательства

- Публичная fake-process дорога: checker не стартует до завершения тестов и видит
  literal transcript точного post-patch дерева; базовый код красный на этом месте.
- Test failure, ноль тестов, timeout, truncation, неверный pin/срок/путь/связь:
  каждый отличается от success; никаких vendor calls и host execution fallback.
- Отказ checker: UI показывает exact-attempt snapshot/findings/tests, в том числе
  после изменений live workspace; чужая попытка и повреждённая связь отказывают.
- No-op/result substitution mutants и UTF-8/native, короткие свежие temp dirs.

## За рамками текущего исправления

Постоянная работа по feedback до достижения цели — новое направление владельца,
не повод поменять старый terminal run или автоматически повторить модельный вызов.
Отдельный следующий срез: ограниченные correction loops, адаптивные бюджеты,
renewal/resume и новые тексты основного UI. Далио остаётся доступным процессом.

## Уточнения после линз S1/S2 и E1/E2

S1: install admission принимает только harnesses/name/version. Не ослаблять его.
Допускается полная побайтная копия уже установленного доверенного Python 3.12.14
в такую отдельную папку. Без download/dependencies; оригинальные bytes/ACL неизменны.
Native witness дополнительно проверяет stdlib origin, project unittest.py trap,
запреты записи work/install, scratch positive и полное возвращение ACL/profiles.

S2: TestPlan размещается перед последним conduct.patch-sources.v1, который
по-прежнему завершает instruction. Новый conduct.test-plan.v1 содержит один JSON;
дубли, trailing/malformed data отказывают до модели/патча. Поля закрыты:
runner=python-unittest-v1, toolchain={install, entry, runtime_digest}, start,
pattern, timeout_seconds. entry=python.exe, install — plain pinned harness dir,
runtime_digest — полный ограниченный инвентарь. Plan берётся только из initial
bound instruction и виден в preview с pin; runtime сверяется до и после теста.
start — task-relative directory, pattern — basename glob без separators;
timeout положительный и не превосходит остатка Do deadline. Отсутствие marker
сохраняет legacy; malformed marker не считается его отсутствием.

E1: Неизменяемый prepared seal под accept/run/actions/action хранит version,
run/node/action/attempt/instance, grant id/digest, input ids, result manifest digest,
seed base/object format, snapshot digest, полный workspace digest, переносимый
subtree digest, report/policy/toolpin digests, checker instance/adapter.
Digest seal добавляется в checker frame. После checker сохраняется отдельная
неизменяемая outcome-связь: seal digest, status/reason/checker и hash typed findings.
Inspector допускает rejected только при совпадении с реальным ActionResultReceipt
и CorrectionFeedback (attempt, inputs, manifest, checker, findings digest).
Отсутствие legacy seal — not_recorded; повреждённый — unavailable. Никакого backfill.

E2: workspace digest и subtree digest имеют разную область и не подменяют друг друга.
Снимок и test report связываются с одними post-patch bytes; whole tree/modes/pins
сверяются вокруг test и checker. Reporter хранит argv/cwd/status/exit и bounded
merged stdout+stderr (явно merged), counts и immutable binding. Подмена, ноль тестов,
таймаут, truncation и незавершённый marker не дают passed и не повторяются.
Обычные tests failed доступны checker для feedback; ACCEPT не может превратить
failed tests в verified. Инфраструктурная ошибка не запускает checker модель.
Существующая acceptance-дорога по-прежнему требует independently verified EvidenceRef.

Новые чистые test policy/runner модули — адаптерный SDK; хранение seals — handoff.
Published получает optional frozen test_report, отсутствующий у legacy.
Нельзя публиковать raw output, содержащий секрет; действуют прежние semantic scans.

## Уточнение E3 после ревью общей реализации

E3: файловые seal/outcome сами не якорят полный accumulated snapshot в журнале.
До checker handoff добавляет отдельный EvidenceRef kind=attempt_seal,
verification=unverified, uri=attempt-seal/action, digest prepared seal и точные
action/attempt/grant links. Это свидетельство сохранения, не проверка и не приёмка.
Projection требует единственную такую запись до результата/feedback и сверяет digest.
Подмена snapshot вместе с пересчётом файловых seal/outcome не меняет журнал и отказывает.
Регрессия меняет mode или добавляет accumulated row при прежних current-file hashes.
