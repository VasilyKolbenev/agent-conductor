# ALPHA-AUTH-CLOSE: дизайн v2

## Q10: недостоверный read-back

A: отдельный sticky road факт недостоверного чтения, снятый под turn/lease;
обязательный bool в frozen _Attempt, заполненный dispatch и review. Publish
отказывает до manifest/material handoff; checker после собственного spawn отказывает
до verdict и feedback. Reset следующей road не меняет старый frozen snapshot.
После release факт живёт/удаляется вместе с attempt, не новая mutable таблица.

B: map отказов по attempt_relation рядом с _login_history. Меньше constructor changes,
но отдельный lifecycle и опасность пропустить передачу при пустом secret set.
Выбран A. Read-back недостоверен независимо от наличия известного secret в выводе.
Закрытая причина credential_readback_untrusted, синхронно в vocab/sentence guards;
не выдавать это за доказанный env echo или успешный результат.

Relay имеет ожидаемый ticket.leaf и spec.admit. Direct subscription reader должен
различать malformed/present unreadable и optional absent: Codex secondary credentials
могут отсутствовать. Required primary — credential из profile.login_relay, где он есть.
Не расширять этот вывод на Kimi native state или API env, если этот профиль не
объявляет файловых credential. Эти собственные границы требуют отдельного свидетельства.

## Q6: локальный аккаунт в продуктовых доказательствах

A: namespaced additive structured evidence в receipt/event extension, точный account
ID из Ready/Ticket под реальной lease превращается в domain-separated SHA256.
Vendor, источник source_relay и статус local_match/unknown сохранены по relation.
Только совпавшие Ready/Ticket считаются match; hashes token/account-profile не подходят.
Не серверное подтверждение, не криптографическая аттестация подписки.
B: отдельный журнал account evidence с собственной lifetime/route. Лишний store и
опасность не связать с ActionResult; предпочтён A при доказанном сохранении runtime.
Точный wire door уточнён независимым tracing ниже; receipt-only вариант A отклонён.

## Q8: закрытая схема и окружение

A: добавить 12 auth/route имён из I2B-DECISION в общий реестр, проверить все двери
ProviderConfig/wizard/direct transport + effective CommandSpec и code-owned forced env.
Схему oauthAccount закрепить только по измеренному roster, не по догадке или fake data.
B: запретить весь Claude до новой live авторизации/совместимости. Не выбран:
владелец поручил локальную проверку без модели, существующий account login недоступен.
Сохранённый профиль 30.10 может дать новый structural roster; это не M1 от 23.10
и не live proof. После разрешённого измерения имён/типов — финальный frozen allowlist,
unknown ключ отказом, ни одного observed поля не выкидывать вслепую.

## Две линзы и проверка

native_test_runner_v2: Q10 dataflow/cleanup, отличать direct optional files и relay.
do_rejected_inspector: Q6 actual runtime journal, security/spec/legacy compatibility.
alpha_readiness_now: Q8 provenance/env; fake fixtures не доказывают измеренный roster.
v2 фиксирует их замечания номерами до кода. Общие файлы — только один исполнитель
или последовательные срезы; независимый env-срез может идти параллельно.

Швы: fake-child пишет неизвестный новый S в result и портит credential; publish
не создаёт manifest/evidence и checker не зовётся. Checker ACCEPT/REJECT после порчи
не даёт verdict/feedback. Две attempts на одном adapter не заражают/не очищают друг
друга; release очищает samples/homes/caches. Q6 реальный fake runtime append/read
сохраняет лишь ожидаемый hash; receipt extra без journal не считается закрытием.
Q8 все 12 имён/lowercase отказаны до spawn, harmless/API-control сохранены.
Мутанты: убрать readback guard, snapshot binding, account proof persistence и env guard;
M0 и каждый изолированно с import/restore SHA. Targets UTF-8/CP1251, CI не заявлять.

## Замечания линз и окончательные интерфейсы

1.1 native_test_runner_v2: общий _login_echo не достаточен; обязательный frozen
credential_readback_untrusted в _Attempt, sticky внутри одной road, проверяется
publish и независимым checker до verdict/feedback. Два constructor обновить явно.
1.2: optional absent secondary не считать порчей; expected relay leaf обязателен.
Present malformed declared credential на direct subscription тоже недостоверен.
Старый permissive тест менять как новый контракт Q10, не замалчивать.
2.1 do_rejected_inspector: runtime намеренно отбрасывает receipt.extra, AttemptEvent
строгий. Выбран Q6 вариант B существующего EvidenceRef вместо нового журнала:
kind subscription_account_v1, verification unverified; фиксированные run/action/
attempt/instance/role binding в extras, безопасный URI/label, только account ID hash.
Это дополнительный provenance, не acceptance evidence_refs и не успех задачи.
Account proof вычислить из Ready.account/Ticket.account внутри lease, сохранить в
attempt snapshot; записать через существующий ArtifactHandoff/RunStore после выхода
из lease для doer и checker. Unknown — явно, без перечитывания текущего профиля.
2.2: нельзя использовать Ready.digest, нельзя обещать server identity/relay reread.
3.1 alpha_readiness_now: старый M1 не содержит полного roster, fake не измерение.
Разрешён отдельный helper только names/types под lease; тот же saved snapshot не
является доказательством актуальной live совместимости. Все observed поля сохраняются,
только unknown names/types отказываются. Новая схема — отдельный code-owned контракт.

Исполнение: native_test_runner_v2 — Q10 и shared relay/headless/snapshot glue Q6;
do_rejected_inspector — новый helper account evidence, ArtifactHandoff и Q6 tests;
alpha_readiness_now — relay_env/claude_relay и новые Q8 tests. Общие модули не делят;
root интегрирует CAPPED и module graph registrations, общие документы/коммиты.
Конкретные названия helper/API согласовать сообщениями перед shared integration.

## Измерение Q8 и уточнение до реализации схемы

Helper выполнен один раз под штатной lease; profile-roster.json содержит только
20 имён/типов и roster hash
821849d871fb70d6aaeac3fc38220a23c9a2bb18b23d2da918a7d9b51f931231.
ccOnboardingFlags — observed dict. Техническое решение Codex: известное поле явно
не копируется, как и до правки (старый relay исключал все nested значения).
Его содержимое не читается повторно, не переносится и не получает доверия.
Остальные observed plain поля сохраняются с точными типами; unknown/type change
отказ до copy. Schema/omit policy входят в relay digest. Live compatibility отдельно.

Cap: устаревший комментарий _review_attempt_carries обновить вместе с Q10.
base.py уже 816 строк в базе; допускается только точное сокращение комментария
_GUARD_SEAMS с сохранением ссылки на открытый doer-residue долг, без изменения guard.
Тесты не ужимать, cap не поднимать, целевые изменённые файлы остаются <=800 строк.

## Адресные находки интеграции

Q6 сохраняется только при existing named_proposal(request): file-only legacy
transport без durable binding остаётся notchecked, без выдуманного факта и без
перечитывания текущего login. Это не отключает frozen Q10 отказ. Новый реальный
runtime positive обязан содержать оба Q6 actor proof. Сам writer по-прежнему
закрыто проверяет request/actor/role/vendor и не принимает чужой запрос.
Два fake adapter использовали независимые счётчики ids, что заняло evidence-4
account record вместо последующего verification. Отдельный purpose namespace
subscription-account-role-actor устраняет эту коллизию, не перехват/игнор ошибки.
