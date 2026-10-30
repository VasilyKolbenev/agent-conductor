Итог: H5-GROK-COMPAT локально проверен; код `3ecad10`. Установка и живой запуск не выполнялись.

# H5-GROK-COMPAT — 30.10.2026

TASK: `b6b656d`, `H5-GROK-COMPAT-TASK.md`; база `120730a`.
Дизайн: дополнение 1 `H5-GROK-DIAGNOSE-DESIGN.md`, `183904f`.
Codex продолжает по решению владельца PROC-CODEX-RETURN; Opus недоступен.

## Изменение

Grok принудительно получает двенадцать пар
`GROK_{CLAUDE,CURSOR}_{SKILLS,RULES,AGENTS,MCPS,HOOKS,SESSIONS}_ENABLED=false`.
Выбранные оператором значения `true` заменяются до запуска дочернего процесса.
Четыре прежних telemetry-переключателя, argv, версия 1.0.5 и capabilities сохранены.
Факты профиля и digest Grok меняются; прежний грант не описывает новый профиль.

Fake CLI записывает все двенадцать имён независимо от production-константы.
Три публичных сценария проверяют семь дочерних процессов: API dispatch (version, task),
subscription transport (version, status, task), quota (version, billing).
Последний использует тот же metadata RPC, но проверяет отдельную вызывающую цепочку.
Тесты запускают только поддельный CLI и создают собственный пустой auth.json.

## Доказательства

Логи, точные команды и SHA256 файлов: `Documents/Codex/work/grok-compat/`.
Ведущий сверил хеши обоих финальных логов и пяти изменённых файлов с записями прогонов.

| Проверка | Результат |
| --- | --- |
| Первая корректная красная фаза на прежних forced_env | 5 failed, сравнения env/digest |
| Финальный scoped UTF-8 | 244 passed, 0 failed, 0 skipped; 46.58 с |
| Финальный scoped cp1251 | 244 passed, 0 failed, 0 skipped; 46.31 с |
| Claude/Codex core snapshot | 16 тестов в каждом scoped; fixture и тест не изменялись |
| CAPPED и file endings перед усилением публичного свидетеля | 222 passed |
| Финальный новый тест в CAPPED и file endings с отчётом | 10 passed |
| M0, весь новый модуль без мутаций | 4 passed |
| M1: убрать одну compat-пару | 4 failed: три child-сценария и digest |
| M2: заменить false на true у одной пары | 4 failed: те же свидетели |
| M3: убрать все compat-пары | 4 failed: финальная красная фаза на прежнем forced_env |

Scoped: compat_isolation, command_grok_transport, command_grok_leak_surfaces,
command_grok_version, grok_quota, grok_service_echo, grok_dispatch_permissions,
harness_core_snapshot. В JSON записаны import origin и кодировка; cp1251 был проверен явно.
Мутанты работали в отдельной копии: 1345 файлов восстановлены и сверены по SHA256.
Копия и десять тестовых каталогов удалены после проверки путей; логи сохранены.
Все падения мутантов — сравнения; ошибок сбора или запуска за доказательство не принимали.

## Ревью и отклонения

Независимый Codex-ревьюер нашёл P2: исходный тест вызывал version/status внутренними методами.
Исполнитель подтвердил недостаток доказательства и заменил вызовы публичным run_once.
Прицельное повторное ревью: P2 закрыта, новых actionable findings нет.
Это ревью узкого diff по коду, не приёмка настоящего Grok.

Первый `red.log` имел неверный protocol в тестовой фикстуре и не засчитан;
исправленный `red-confirmed.log` красный на сравнениях. До усиления теста scoped имел
245 passed; после объединения четырёх дорог в три публичных сценария — 244 passed.
Старый результат сохранён отдельно, пропусков и ослабления assert не было.

## Последний доказанный / первый несделанный / не повторять

Последний доказанный: принудительное окружение Grok на реальных fake-child процессах.
Первый несделанный: отдельный контракт I2 для GrokRelay и операторских routing-переменных.
Нужен узкий допуск code-owned false-пар: текущий `_route_selected` иначе отвергнет их
как forbidden. Codex `access_only_switch` повторно использовать нельзя: у него другие функции.

`confine_platform=None` — существующий тестовый путь общего транспорта; он не доказывает
готовность Grok по подписке внутри production boundary. Relay, file-канал и review_only
здесь не включались; текущие production-отказы сохранены.

Не повторять: реальные login/quota/model-пробы, setup DecemberV1 и полный core старой сборки.
DecemberV1 остаётся закрытым на `14f94cf9f8f0`; новой установки, CI и push не было.
Снимок проекта и истории хранится локально в `work/takeover-20261030T130259Z`.
