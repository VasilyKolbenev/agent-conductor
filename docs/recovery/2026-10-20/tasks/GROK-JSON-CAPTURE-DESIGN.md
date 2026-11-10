# GROK-JSON-CAPTURE: разделение границ, v3

## Факты и гипотезы

Измерено: failed receipt от 10.11.2026 сообщает stdout overflow, не timeout;
оригинальный ответ не сохранён. Локальная проверка должна установить механизм,
но не угадывать содержимое утраченного ответа.

По коду: 49 152 байта применяются до JSON-разбора ко всему stdout; столько же
разрешено готовому UTF-8 артефакту. Это разные данные. JSON escaping способен
расширить один байт ASCII в шесть байтов `\uXXXX`. В JSON есть отдельный thought.
Подтверждение pinned 1.0.13 без исполнения: встроенная документация в PE
sha256 `bf43dc75f5478a106eab1e86d422c963e4dbe9666cf14dab363733d27bf1e672`,
смещение 123556105; text/stopReason/sessionId/requestId и optional thought/usage.
Большой thought при коротком text — легитимная синтетическая регрессия.

## Два варианта

A. Обычный JSON сохраняется, но wire и decoded artifact имеют разные бюджеты.
Все захваченные байты проходят прежние проверки JSON/секретов; только text
публикуется. Небольшая правка и совместимость с текущим frozen graph.

B. Инкрементальный collector отбрасывает thought/progress по мере чтения и
сохраняет bounded final text. Полезно для длительных сессий, но требует новой
границы ProcessRunner, проверки целого потока, duplicate keys и сканирования
секретов через границы чанков. Имеющийся diagnostic stream всё ещё целиком
ограничен 48 КиБ и склеивает тексты сообщений: простой switch не решает сбой.

Выбран A. Причина исправления — смешение типов данных и отсутствие отдельной
проверки decoded text; число само по себе не считается доказательством.
Это bounded JSON road, не обещание неограниченной потоковой истории.

## Контракт A

- `GROK_JSON_WIRE_LIMIT = 6 * ARTIFACT_CONTENT_LIMIT + 256 * 1024` = 557 056 байт.
  Первая часть математически покрывает escaping допустимого text; 256 КиБ —
  явно выбранный защитный бюджет служебных полей, не измерение утраченного ответа.
  Он ограничивает память до разбора. При его превышении — отказ, без частичного успеха.
- После полного строгого JSON и успешного end_turn: `len(text.encode('utf-8'))`
  не больше прежних 49 152. Пробелы, Unicode и повторы сохраняются без сокращений.
  Превышение даёт отдельный fixed failure, не unknown и не усечённый артефакт.
- Grok profile ceiling отражает новый wire budget и автоматически меняет
  `ProviderAuthority` digest через существующий asdict(profile).
- `_review_output_limit(request)` — чистый hook ArtifactAwareTransport,
  default None для прежнего поведения прочих harness. Grok возвращает wire
  для обычного JSON и прежние 49 152 для marked diagnostic stream.
- Grok `_attempt` сохраняет прежние 49 152 для non-review и отсутствующего
  явного лимита; меньший asked сохраняется через min, а не поднимается до default.
  Preflight/auth/quota/дормантный dispatch не получают большего
  бюджета. Нет mutable флагов на общем экземпляре адаптера.
- Секреты, error/exit, stopReason, отсутствие полного EOF JSON, duplicate keys,
  workspace readonly, leases и cleanup проверяются прежней дорогой.
  Новый предел не применяется к историческому run задним числом.
- Превышение decoded text имеет фиксированный detail
  `the review result exceeded the artifact byte limit`, явно допущенный
  в `failure_reasons.py`; ledger не скрывает его за общей фразой failed.

## Итерации и свидетели

I1: `_fakegrok.py`, новый `test_grok_json_budget.py`, regression red на базе:
малый и большой thought при одном literal text дают один и тот же полный artifact;
сырой размер конверта явно больше 49 152. Ни адаптер, ни runner не подменяются.

I2: hook, Grok caps/validation, обновление прежнего ожидания truncated-final.
Границы wire budget / +1, Unicode escaping при 49 152 decoded UTF-8 / +1,
malformed/duplicate/trailing JSON, error и synthetic secret в большом thought.
Успех проверяется по artifact content/input IDs, один child, auth не изменён,
дом удалён. Большой stderr не становится ни артефактом, ни причиной overflow.

I3: provider digest меняется с wire budget; прочие transport facts/лимиты и
marked diagnostic stream не меняются. UTF-8/CP1251, целевые соседние проверки,
mutants no-op/обрезка/потеря final bound/потеря wire bound/секрет.
Fake доказывает продуктовую дорогу, не поведение живого Grok после исправления.

Линза Спека/безопасность: отдельный read-only Codex (do_backend).
Линза Доказательства: отдельный Codex (do_evidence).
Opus недоступен; используется ранее согласованная замена ревью на Codex.
Ревью v1 и подтверждённые находки фиксируются перед реализацией.

## Независимое ревью v1

S1 (Спека): non-review override обязан сохранять меньший asked; подтверждено,
правило min добавлено выше. S2 (Доказательность): новая причина должна пройти
санитайзер failure_reasons, иначе UI/ledger её потеряют; подтверждено, fixed
detail добавлен. Блокеров варианта A нет. Линза Доказательства подтвердила
ordinary JSON форму по документации внутри pinned PE без исполнения CLI,
публичный шов runtime и различение wire 49 152 / 49 153 при одинаковом text.
Изменённый wire cap автоматически меняет digest только Grok profile.

## Уточнение до коммита реализации

S3 (Спека/архитектура): generic failure_reasons не имеет права знать бренд
провайдера. Подтверждено штатным gate G: 1 failed / 1 passed на failure_reasons.
Фиксированная причина выше сделана нейтральной. Allowlist и сам guard не меняются;
в adapter/runtime/tests ожидается одна и та же нейтральная фраза.
