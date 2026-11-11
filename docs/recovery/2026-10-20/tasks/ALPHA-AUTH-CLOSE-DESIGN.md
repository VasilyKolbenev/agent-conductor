# ALPHA-AUTH-CLOSE: дизайн v1

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
Точный wire door уточняется по независимому tracing до реализации.

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
