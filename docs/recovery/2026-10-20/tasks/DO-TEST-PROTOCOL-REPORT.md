Итог: локально проверено | 385d035 | 20362 passed/codec, 0 failed | skips 441 | установка.

# DO-TEST-PROTOCOL: тесты до checker и материалы отказа

Исполнитель: Codex и независимые Codex-исполнители/ревьюеры.
Ветка recovery/2026-10-20. Сохранённая база 53cc60b, чужих правок не было.
TASK e009342, уточнение бюджета/runner 1adde93; DESIGN v3 6d4043d, решение 4d938e8.
Порог владельца теперь 20% остатка; прежняя остановка на 30% заменена.
Основной код: db4d408cfb0fbd342d1b592a7d7315e15e6c14df.
Исправленный кандидат: 5e2d1ebe1ad09e27c9db4a8fb79469bdb76752d7.
Окончательный кандидат: 385d0354722fb620214d0d5e27d98a340e713bf1.
Последняя фиксация — только тесты, все исходники продукта как в 5e2d1eb.

## Чужие правки

На старте рабочая копия была чистой. Параллельные исполнители работали в отдельных
worktree и названных файлах; их изменения сведены ведущим. Чужих незакоммиченных
правок не затрагивали. Живой проект, его terminal run и решения владельца сохранены.

## Изменения

Do выполняет объявленные тесты после применения патча и до checker.
План берётся только из initial human instruction, связанной с грантом.
Модель не задаёт произвольный executable, shell или дополнительный бюджет.
Первый поддержанный runner — python-unittest-v1, не универсальный toolchain.
Legacy без marker сохраняется; malformed marker отказывает.

local_test_plan/run/receipt/frame проверяют закрытую политику и полный runtime pin.
Исполнение — через существующий offline ProcessRunner, home=None, read-only задача
и install, writable scratch, без credentials и host fallback. unittest импортируется
до добавления project path. Время тестов входит в остаток Do deadline.
Сохраняются merged stdout+stderr, argv/cwd/exit/status/counts и exact-attempt binding.
Вывод ограничен 64 KiB. Zero/all skipped, timeout и truncation не дают passed.
Claim записывается до spawn; даже незавершённый marker запрещает повтор.

codex_patch_dispatch передаёт report через frozen Published.
independent_check/transport сверяют tree, modes, policy и runtime вокруг проверки.
Failed tests доступны checker для feedback; ACCEPT не делает их successful.
Неполный протокол не запускает checker. Sensitive scans действуют до записи/frame.

artifact_handoff/attempt_protocol сохраняют prepared seal и outcome.
До checker журналируется отдельный attempt_seal EvidenceRef, всегда unverified:
это якорь полного seal, не verification и не acceptance.
Accumulated snapshot, current manifest, whole workspace и modes не подменяют друг друга.
Пересчёт файловых seal/outcome при подмене snapshot не меняет ledger anchor.
Успешный proof также ссылается на seal; условия acceptance не ослаблены.

attempt_detail/test_evidence и Atlas показывают exact-attempt diff, native protocol,
checker и typed findings отказа. Позднее изменение work не меняет эти материалы.
Чужая попытка или повреждение дают unavailable, legacy не получает backfill.
Studio и Desk раскрывают порядок, effective timeout и pin до разрешения.
Новый JS зарегистрирован в server_assets/module graph; Desk проверяет source binding.

## Проверки

Артефакты: Documents/Codex/work/do-test-protocol-1111/.
Продуктовых вызовов моделей и настоящих vendor CLI — 0, нового живого цикла — 0.
Процессная граница подменяется в integration; native witness использует настоящий Python.

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| Public runner red | 1 failed, 0 passed | runner-red.log: нет tests между apply/checker |
| Preview red | 2 failed, 0 passed | preview-red.log: поля скрыты, неверная дорога допущена |
| Rejected projection red | 1 failed, 0 passed | Публичный API не показывал verdict |
| Anchor red | 2 failed, 0 passed | runner-anchor-red.log: extra row и mode substitution |
| Runner seam UTF-8/native | 48 passed в каждом | runner-green-{utf8,native}.log |
| Archive/checker UTF-8/native | 16 passed в каждом | runner-anchor-green-{utf8,native}.log |
| Соседние backend contracts | 287 passed | targeted-utf8.log |
| Public failure gates + структура | 306 passed | failure-gates.log |
| Studio/Desk projection UTF-8/native | 86 passed в каждом | Closed metadata, source binding |
| Final Chromium 5e2d1eb UTF-8/native | 27 passed в каждом | browser-5e2d1eb-{utf8,native}.log |
| Native Python v2 | 1 test, 0 failures/errors/skips, exit 0 | native-witness-v2/evidence/result.json |
| Core db4d408, неполный красный | 31 failures в двух группах | Каталог/census; stopped-after-failure.json |
| Исправление каталога/census | 359 passed, 1 skipped | catalog-assets-fixed.log |
| Windows core 5e2d1eb UTF-8 | 20354 passed, 3 failed, 441 skipped | Core run ниже |
| Windows core 5e2d1eb CP1251 | 20354 passed, 3 failed, 441 skipped | Те же три inventory failure |
| Окончательный core 385d035 UTF-8 | 20362 passed, 0 failed, 441 skipped | Чистый detached worktree |
| Окончательный core 385d035 CP1251 | 20362 passed, 0 failed, 441 skipped | Тот же exact SHA |
| Полные JS/module/boot/asset guard-файлы | 69 passed, 1 skipped/codec | guard-inventory-{utf8,native}.log |
| Closed checker words | 49 passed/codec | reason-proof-results.json, old source 5 failed |
| Wheel 385d035, exact artifact linkage | passed, 540 файлов совпали | package-ready/ready-result.json |
| Окончания итоговых документов UTF-8/CP1251 | 9 passed/codec, diff-check чист | docs-final-checks.json |

Окончательный core: 54/54 групп passed, failures=0 и errors=0 в обеих кодировках.
До и после прогона HEAD 385d035, detached worktree чистый.
Результат: core-ready/run-20261111T110716316359Z/results.json.
Mode witnesses подтвердили UTF-8 и CP1251, импорт из candidate-ready и пустые opt-ins.
441 skipped/codec не считаются passed: среди причин платформа, выключенные native/live
opt-ins, symlink privilege, старый Git, hatchling и четыре прежних contrast-свидетеля
ниже threshold. Полные причины сохранены в логах; opt-ins ради зелёного не включались.

Native v2 подтвердил stdlib из копии доверенного Python 3.12.14, project unittest.py
не загружен. Четыре записи work/install запрещены PermissionError errno=13,
scratch literal-42 работает. Исходные bytes/ACL, runtime copy, задача и оригинал целы;
loan ACL возвращены, tokens=0, profile/attempt удалены, три journal records retired.
SHA result.json: ac08442039137f4a62b1bdc1d5125bc8fc0d133ef66bd09c8f5ee0c625a1efdb.

Wheel: package-ready/dist/agent_conductor-0.1.0-py3-none-any.whl, 2 240 220 байт.
SHA-256: bfc9f05293f933e7638bc14f563a126d98daef3ea9be6120ff6cacb53bce77f6.
Проверены шесть новых Python-модулей, preview, report roundtrip, zero-test refusal,
JS allowlist/package и conduct --help. Импорт — только из чистого venv.
Source archive 385d035:
9d57c25ee938765d2335a7403ea72f0d2decf17a022d4d55bdcf5ed1769da634.
С предыдущим wheel db4d408 совпали 539 файлов; изменён только studio-atlas-copy.js,
все 78 значений которого доказанно прежние. Оба wheel и receipts сохранены.
Wheel 385d035 целиком идентичен wheel 5e2d1eb, все 540 файлов совпали также
с финальными исходниками и чистым installed env. Поэтому точная прежняя
установка/smoke использована повторно без нового bootstrap/install/run.

## Мутанты

M0 запускается из отдельной src/tests/pyproject копии, conductor.__file__ проверен.
После каждого мутанта SHA восстановлен; копии и собственные short temp удалены.
Counts разных наборов не складываются как число уникальных тестов.

| Мутант | Результат | Что красное |
| --- | --- | --- |
| Нет исполнения tests | 1 failed | Public apply/tests/checker order |
| M0 общей копии | 10 passed | root-mutant-M0.log |
| M1: failed tests можно принять | 1 failed, 9 passed | Public failed + checker ACCEPT |
| M2: неполный протокол допускает checker | 3 failed, 7 passed | Zero/timeout/truncation |
| M3: нет preview-проверки policy | 1 failed, 9 passed | Policy на неверном профиле |
| M4: нет ledger anchor | 2 failed, 8 passed | Валидные snapshot extra/mode substitutions |
| No-op rejected projection | 7 failed, 3 passed | Exact verdict/protocol |
| No-op Inspector renderer | killed | Literal argv/output в Chromium |
| Desk: нет source binding | 1 failed, 1 passed | Чужая инструкция |
| Desk: нет closed rows guard | 1 failed, 1 passed | Неверные metadata |
| Desk: нет отрисовки policy | 1 failed | Actual DOM order/runtime |
| Нет четырёх checker reason mappings | 4 failed, 45 passed | Literal reason words; M0 49 passed |

Общая таблица и restore SHA: root-mutant-results.json.
Отдельные projection/renderer наборы имеют собственные M0 и cleanup receipts.

## Ревью Codex

Независимые линзы «Стандарты» и «Спека», затем чтение ведущим.
Opus недоступен; работу выполняли Codex-агенты по делегированию владельца.
Исправлены frozen Mapping parser, legacy seal guard, controlled infrastructure refusal,
pin до/после checker, asset registration и Desk compatibility.
P1 snapshot substitution воспроизведён двумя assertion failures и закрыт E3 в DESIGN v3.
После исправлений blocker/major в проверенных контрактах не найдено.
Все 16 новых code/test файлов в CAPPED; общий process/network execution door прежний.

## Отклонения и неудачные проверки

- Native v1 остановился на неверных критериях свидетеля: winerror=5 вместо фактического
  errno=13 и неверные имена journal. Сохранены первый исход и read-only аудит:
  реальные запреты и cleanup были целы. Один согласованный v2 исправил только
  эти критерии; v1 не выдан за положительную проверку.
- В sandbox некоторые pytest setup получили os.link denied. Это не product red.
  Штатные проверки перенесены на host с новыми short temp; assertions не ослаблялись.
- Browser сначала: 25 passed / 1 failed в Save→Publish. Чистая база воспроизвела
  гонку confirming GET: закрытие review либо draft_changed. При задержке 250 ms
  baseline failed, исправленный тест passed. Изменено только ожидание saved,
  не продукт, timeout или проверки опубликованного документа.
- Core preflight отказал до тестов на старых занятых short temp. Старые папки
  не удалялись; выделены 54 проверенно новые папки длиной не более 26 символов.
- После остановки db4d408 удалены 17 plain temp, три уже отсутствовали;
  шесть каталогов с reparse сохранены. Их пути перечислены в core cleanup.json;
  переходы не удалялись рекурсивно. Это остатки тестовых negative fixtures,
  не рабочая задача или профиль приложения.
- После завершённого 5e2d1eb удалены 28 plain temp, шесть отсутствовали;
  двадцать с reparse сохранены, пути в core-final cleanup.json.
- После зелёного 385d035 удалены 28 plain temp, шесть отсутствовали;
  двадцать с reparse сохранены без обхода переходов. Точные пути и результаты —
  core-ready/run-20261111T110716316359Z/cleanup.json.
- db4d408: 30 проверок literal source messages не принимали добавленную склейку
  строк каталога; ещё один census не перечислял новый JS. После красного прогона
  5e2d1eb возвращает буквальный формат и точный census. Node подтвердил равенство
  всех 78 значений каталога. Старый неполный прогон не выдан за зелёный;
  controller и все записанные PID завершены перед новой полной матрицей.
- Полный 5e2d1eb выявил ровно три inventory failure в каждой кодировке.
  Независимый аудит дополнительно обнаружил два browser boot census до установки.
  385d035 исправляет пять точных списков; equality/closed guards сохранены.
  Продукт не меняется. Третий раунд по новым фактам разрешён в c7b284c.
- В main venv отсутствовал hatchling: сборка выполнена существующим доверенным
  hatchling 1.32.4. Ошибка декодирования cp1251 ensurepip output исправлена только
  в helper, с сохранением raw log и без повторного build/bootstrap. Downloads=0.

## Не проверено

Нет remote CI, Linux/macOS, защищённой установки и нового модельного Do.
Рабочая Studio остаётся на 4deb571; старый terminal run не переписан.
Legacy без seal не получает материалы задним числом. Для infrastructure/прочих
неподтверждённых отказов вне typed checker REJECT представление пока unavailable.
Первый runner ограничен unittest и bounded output; другие toolchains требуют политики.

## Открытые вопросы

Постоянные correction loops, adaptive renewal и новые основные UI-тексты сохранены
как следующий срез. Старый no-retry grant не превращён в повтор; внешние 4 passed
не подменяют отказ checker в counter-src-4deb571-r2.
Для сокращения повторных полных прогонов нужен предварительный запуск всех
static import/module/boot/reason census вместе; текущие assertions не ослаблялись.

## Передача

Код 385d035, полный core завершён в отдельном чистом detached worktree: 54/54 passed.
Все 16 новых code/test файлов зарегистрированы в CAPPED; проверки структуры зелёные.
Документы: этот отчёт, HANDOFF-2026-11-11, OPEN-DECISIONS.
Последний доказанный шаг: core в двух кодировках, native/browser, мутанты и exact wheel.
Первый несделанный шаг — подготовить защищённую установку
проверенного wheel и новый initial test plan для count_succeeded.
Модель/новый цикл остаются на новом разрешении владельца.
Не повторять counter-src-4deb571-r2, G6 или native witness ради ещё одного зелёного.
