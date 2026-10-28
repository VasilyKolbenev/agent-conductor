# H5-CODEX-A-I1: подключить установленный Codex 0.164.0

Владелец 28.10.2026 поручил Codex продолжить подключение Codex к продукту по подписке.
База `d6e4331`; отдельный worktree `Documents\Codex\work\cdx164`. Продукт B3 не заменять.
Основания: COMPAT-TASK, DESIGN `69c2a7d` с решениями A-REVIEW `2a5bcdd`, П0–П5 `2deece6`,
Р9/Р10 I2B-DECISION `f6dbd65`. Это исполнение принятого дизайна, не новый общий аудит.

## Результат

Кандидат адаптера принимает установленный 0.164.0, новую закрытую форму ChatGPT-входа,
запускает задачу/проверку на access-only копии и читает подписочные лимиты. Готовность живой
связки принимается после оставшихся измерений; одна смена pin её не доказывает.

1. Pin/argv, новая фраза API status, отсутствие `-o` на Failed/Interrupted, feedback disabled.
2. Новые tokens.login_owner_id и oauth_provenance: закрытые типы; owner ID сохраняется,
   provenance и настоящий refresh не копируются. Источник не меняется, старый shape допускается.
3. Перепись route/key env П5, включая запрет пользовательского refresh override даже при
   совпадении значения. Только code-owned loopback override на access-only процессе;
   вопросы настоящему home, вход/выход владельца его не получают.
4. `.env` и `environments.toml` в настоящем home отказывают до spawn без удаления файлов.
5. Нотификации quota менять только по П6а, закрытым списком; неизвестное не замалчивать.

## Файлы и параллельная работа

Все исполнители в отдельном worktree, только в перечисленных своих файлах; коммитит Codex.

- Relay: `src/conductor/command/adapters/codex_relay.py`, `tests/test_codex_relay.py`.
- Env/launch: `relay_env.py`, `relay_attempt.py`, `headless_spec.py` в том же каталоге
  adapters; `tests/test_relay_env.py`, новый `tests/test_codex_relay_environment.py`.
  Если действительный launch-шов лежит в другом файле, сначала сообщить ведущему.
- Ведущий: `codex_cli.py`, `provider.py`, при измеренном основании `codex_quota.py`;
  `tests/_fakecodex.py`, `_fakeboundary.py`, `test_command_codex_version.py`,
  `test_codex_auth_store.py`, `test_command_codex_transport.py`,
  `test_command_codex_real_smoke.py`, `test_harness_login_method.py`,
  `test_harness_login_leaks.py`, `test_subscription_quota.py`, `test_quota_deferral_studio.py`,
  `test_studio_quota_session_rows.py`, `test_relay_profiles.py`, `test_command_line_cap.py`;
  новый `tests/test_codex_compatibility.py`, документы A и отдельный отчёт.
- Нативный свидетель: новый opt-in `tests/test_codex_native_compat.py` на существующем шаблоне
  `test_relay_claude_native`; только fake auth и --version/login status/doctor без prompt.
  Старый test_adapter_boundary_launch использует recording boundary и сам П9 не доказывает.

Не раздувать codex_cli (790/800) и test_relay_road_refusals (782/800).
Не трогать защищённую сборку B3, личные профили, журнал/seed DecemberRehearsal.

## Доказательства и живые шаги

Красная фаза на новых закрытых формах/публичных швах, затем минимальная реализация; синтетические
credentials. Целевые проверки UTF-8 и cp1251; позитивный dispatch различает no-op, запреты —
снятие защиты. После итогового кода полный core в чистом worktree, два режима кодировки,
короткий новый basetemp. Нативные файлы по одному процессу. Повтор П0–П5 не назначается.

Оставшийся порядок A-REVIEW: П8/П9 без настоящих credentials и inference; проверка нового
feedback-ключа без inference; П11 — отдельный пустой защищённый home, вход владельца, имена/типы
полей, logout только тестового home. Затем П6: квота и свежий каталог на копии под общей lease,
без refresh/copy-out. Служебные записи измерений вне Git, секретные значения никогда не выводить.

Условный M2 уже разрешён: один 0.164.0/gpt-6.1-sol, 60 с, фиксированный минимальный stdin,
VERDICT: accept; только после применимой матрицы, свежего server cache с visibility list,
preflight и срока access token не меньше суммы timeout + 10 минут. Без перебора и retry.
Путь до живого запуска подготовить полностью до запроса действия владельца; его вход не
автоматизировать. Если понадобятся изменения вне установленного бюджета — сначала факты/решение.

После M2 — отдельный первый запуск Codex в приложении с явным grant владельца и проверкой
результата. Не выдавать M2 вне boundary за полный цикл или готовность R5.

Последний доказанный шаг: установка и П0–П5. Первый несделанный: A-I1 и оставшаяся матрица.
Следующий шаг: красные синтетические проверки и реализация в названных файлах.
