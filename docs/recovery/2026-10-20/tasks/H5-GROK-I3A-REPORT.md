Итог: локально проверено | `baeb40e` | 128 passed в UTF-8 и cp1251 | Grok не активирован.

# H5-GROK-I3A — 30.10.2026

TASK `7eaa0a0`; дизайн `183904f`, §4. Codex продолжает по запросу владельца в общем бюджете.
Чужие правки: отсутствовали; исполнитель работал только в трёх выделенных файлах.

## Изменение

AttemptLaunch.task_modes по умолчанию сохраняет dispatch/review. Запрет известного режима
проверяется в объявлении boundary, до preflight и повторно до claim при непосредственном
запуске. Metadata mode=None и прежняя валидация неизвестного режима сохранены.
serves_checks=False отключает verify_for/verification_started без отключения обычного review.
Включение обратно в подклассе поддержано. Profile dataclass и текущие providers не менялись.
artifact_transport — 798 строк, ниже лимита 800.

## Доказательства

Логи, команды и SHA: `Documents/Codex/work/grok-i3a/`; финальные прогоны — `final-*`.
Исходная красная фаза: 7 failed / 1 passed. Обычный запрещённый dispatch на обеих auth-дорогах
и с/без confinement возвращает failed без версии, claim, новых файлов и дочернего процесса.
После сужения mode во время version preflight доказан BoundaryUnavailable до claim;
это исход transport API, не утверждение о failed receipt верхнего runtime.
Положительный review запускает настоящий fake child в review-boundary и сохраняет evidence.

| Проверка | Результат |
| --- | --- |
| Финальный scoped UTF-8 | 128 passed, 0 failed, 0 skipped; 26.77 с |
| Финальный scoped cp1251 | 128 passed, 0 failed, 0 skipped; 27.71 с |
| Claude/Codex snapshots | 16 в каждом наборе; fixture не менялся |
| CAPPED и file endings | 226 passed |
| Финальный M0 | 8 passed |
| Без раннего отказа | 2 failed |
| Без spawn recheck | 1 failed |
| Без checker restriction | 2 failed |

Scoped: test_harness_task_modes, test_adapter_boundary_launch, test_adapter_boundary_roads,
test_harness_core_snapshot. Мутанты проверены в копиях с восстановлением SHA; две копии
и 14 собственных временных папок удалены. Ведущий сверил три финальных SHA с main.

## Отклонения и ревью

Первый scoped обнаружил настоящую регрессию: неизвестный mode=plan получил BoundaryUnavailable
вместо прежнего ValueError. Оба результата 127 passed / 1 failed сохранены. Guard сужен до
ATTEMPT_MODES; затем scoped и мутанты повторены на исправленном коде. Сбоев не пропускали.
Независимое ревью Codex: замечаний нет; уточнение для неизвестного режима отдельно перепроверено.
Новые тесты внесены в CAPPED. CI/full core, установок, серверов, живых CLI и push не было.

## Передача

Последний доказанный: режим только чтения и запрет checker работают на синтетическом harness.
Первый несделанный: I3B review_only projection/UI, затем активация Grok review/file/relay.
Не повторять старые live/once-пробы; G2/P/G6 и свежий owner grant остаются впереди.
Этот срез не означает, что Grok уже выполняет diagnose в приложении.
