Итог: Q6/Q8/Q10 локально проверены и приняты ревью | 7742eaa | 534 passed/codec,
0 failed/errors/skipped в финальном combined | отклонения сохранены ниже |
дальше остаток RS1, затем единый release candidate/core/CI/чистый onboarding.

# ALPHA-AUTH-CLOSE

Ведущий Codex; исполнители native_test_runner_v2, do_rejected_inspector,
alpha_readiness_now. База b946ff7, чистая recovery/2026-10-20. TASK c6d8a27,
DESIGN v1 0c9433e, v2 d6832bb, уточнения 8840660/0cd6300/518f8ec/763ac21.
Чужих правок не было; исполнители меняли только назначенные файлы, root — интеграцию.

## Q6: аккаунт относится к попытке

Из Ready.account и Ticket.account под lease получается frozen proof совпадения
source/copy: domain-separated hash native account ID, canonical vendor и статус
local_match/unknown. Ready.digest/token fingerprint не используется. Это локальный
источник/копия, не серверная аттестация и не независимое чтение аккаунта relay.

ArtifactHandoff сохраняет отдельный EvidenceRef subscription_account_v1 с точными
run/action/attempt/actor/role/request-digest bindings. Он всегда unverified, отдельно
от acceptance evidence_refs; live/restart и повтор записи сохраняют ровно один факт.
Writer отвергает чужой запрос/actor/vendor, self-checker без frozen verifier,
дубли и замену факта. Account purpose ID не сталкивается с verification ID.
Doer использует frozen snapshot, checker — собственный свежий proof после lease.
Ledgerless legacy без named proposal остаётся notchecked, не читает текущий профиль
и не получает выдуманного подтверждения. Q10 guard на legacy по-прежнему действует.
Kimi без Ready/Ticket не получает ложного local_match; его собственный live proof отдельно.

## Q8: измеренная схема и точное окружение

Добавлены 12 Claude/Anthropic auth/route имён из решения Q8 в общий реестр отказа.
Проверены config/wizard/direct selected/forced-env, lowercase, отказ до vendor spawn,
положительный effective CommandSpec и неизменённый API control.

Единственный разрешённый helper под LoginScopes lease прочитал только структуру
oauthAccount сохранённого dedicated .claude.json. В receipt только имена/типы,
значений и credential-файла нет. Новый snapshot от 30.10, не M1 от 23.10.
20 полей, roster hash 821849d871fb70d6aaeac3fc38220a23c9a2bb18b23d2da918a7d9b51f931231.
19 plain-полей копируются, два UUID обязательны, прочие optional; неизвестный ключ
или изменение измеренного типа — отказ. ccOnboardingFlags явно исключён как
известное вложенное поле, которое и раньше не копировалось. Содержимое не измерялось.
Schema/omit входят в dataclass profile и frozen grant digest, старые grants не обновлялись.
Иная версия/схема аккаунта требует отдельного измерения; live совместимость с новым
пользователем этим структурным чтением не доказана.

## Q10: неизвестный новый секрет не публикуется

Sticky факт недостоверного read-back фиксируется в двух обязательных конструкторах
frozen attempt. Relay проверяет ticket.leaf; direct объявленные JSON files проверяются
с различением required primary, optional отсутствия и unreadable/stat failure.
Только FileNotFoundError означает отсутствие; OSError optional не считается безопасным.
Обычный verify, independent publish, ACCEPT и REJECT отказывают до work evidence,
manifest, artifact или correction feedback. Account provenance не есть work verification.
Новая road не очищает отказ старого snapshot; release/finally освобождают его и samples.
Строгая проверка файлов не расширяет пустой файловый контракт Kimi/API на их собственные
каналы состояния. Их отдельная приёмка сохраняется, как и полный остаток RS1.

## Проверки и мутанты

| Набор | UTF-8 | Native CP1251 | Артефакт вне Git |
| --- | --- | --- | --- |
| Финальный combined, 9 модулей | 534 passed | 534 passed | work/alpha-auth-close-1111/final-{utf8,native}.xml |
| Q10 и 7 соседних модулей | 249 passed | 249 passed | work/alpha-auth-close-q10-1111/targets-{utf8,native}.xml |
| Q8, 3 модуля | 448 passed | 448 passed | work/h5-q8-roster-1111/green-final-*.log |
| Q6 runtime/RunStore/restart | 26 passed | 26 passed | work/alpha-auth-close-1111/q6/final-*.log |

Финальные ошибки/пропуски 0. Наборы пересекаются, итоги не суммируются.
Mode witnesses: UTF8 [1,utf-8,utf-8], native [0,cp1251,cp1251]. Source fingerprints
до/после combined совпали. Новые source/tests в CAPPED, все изменённые файлы <=800,
новые строки <=100, diff-check чистый. Устаревшие comments уточнены по дизайну без
ослабления assertions; base.py до задачи был 816 строк, теперь 797.

Полные изолированные src/tests/pyproject copies, проверенные imports и восстановление SHA:
Q6 M0 26 passed; persistence/match/request mutants пойманы (4/1/2 failed).
Q8 M0 90 passed; env omission/schema bypass/nested passthrough (5/24/1 failed).
Q10 M0 13 passed; publish/checker/snapshot mutants по 1 failed.
Дополнительная common-verify дверь: M0 2 passed, удаление guard — 1 failed.
Optional stat failure: M0 1 passed, M5 OSError->continue — 1 failed на False/True;
optional-mutants.json SHA d86921ee650e9f5d37042509af2478385ed90f4cb3baf520b98fbbe88640bece.
Мутанты не смешаны с финальными passed; copies/temp очищены собственными исполнителями.
crapper/dryer/mutator не ставились; meaningful mutations выполнены вручную.

## Найдено, исправлено и не скрыто

- Q6: receipt.extra терялся runtime; выбран durable EvidenceRef вместо arbitrary-extra passthrough.
- Q6: self-checker, vendor mismatch и ID collision подтверждены, закрыты адресными witnesses.
- Q10: ordinary verify обходил publish; major закрыт общим frozen guard и новым RED/green.
- Первые Q10 3 failed, ordinary 1 failed/1 passed; initial ordinary fixture binding error
  сохранён отдельно и не засчитан как симптом продукта.
- Старые соседние targets: 241 passed/4 failed на codec — обязательные snapshot fields
  и новое unverified account evidence. Обновлены явный healthy fixture и точный выбор
  work evidence с проверкой, что provenance unverified и не входит в acceptance.
- Q8: первый RED 74 failed/4 passed включал ошибку cwd; исправленный 73 failed/5 passed.
  Первый green 424 passed/24 failed — неверный literal test sentence; исправлен тестовый
  literal на существующую фразу без изменения продукта. Оба исхода сохранены.
- Root restricted run: 375 passed/18 failed до поведения в os.link (WinError5).
  Итоговый вне этой границы использует те же проверки, защиты продукта не снимались.
  Первое имя short temp оказалось занято другой живой проверкой; assert остановил
  controller до pytest, существующая папка не удалялась. Затем взяты свободные q8u0/1.

## Сохранность и границы

closure-audit.json: старый ledger 46 records, SHA
60f2621862e977456552be6d58044cb603808cd66c4173a6c09a1e0b99825ad6 неизменен.
Новых моделей/vendor CLI/циклов — 0; structural profile inspection — ровно один.
Root temp q8u0/1 и guards-u удалены после plain/absolute checks; чужие temp не тронуты.
Рабочая Studio остаётся на 19956c8, server 99419 на 7830. Новый wheel/установка,
полный core/remote CI, AppContainer OS lease recovery и новые аккаунты не проверялись.
Принятый bounded Codex+Grok run не повторялся и не превращён в correction loop.

## Ревью и передача

Две независимые design lenses и code review по стандартам/спеке; root перепроверил
каждую подтверждённую находку. Major обычной verify закрыт финальным ревьюером.
Код/CAPPED 7742eaa, документы отдельным commit; статус только локально проверено,
не выпускная готовность. До альфы остаются полный RS1 depth/runtime audit,
единый release candidate/core/CI/installed road, четыре собственных подписки,
четыре пользовательских UX-прохода и owner acceptance. ALPHA-FOUR не отменён.
Не повторять принятый run и завершённые targets/mutants. Порог владельца 15%.
