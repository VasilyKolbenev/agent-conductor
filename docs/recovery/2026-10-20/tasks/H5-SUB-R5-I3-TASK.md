# H5-SUB-R5 I3: тексты, UI, документы владельца и доводка I2b

Opus (ведущий) → исполнитель Sonnet, 23.10.2026. Основа: H5-SUB-R5-TASK (I3 — тексты и UI после
транспорта), отчёт I2b `tasks/H5-SUB-R5-I2B-REPORT.md` («Передача», «Открытые вопросы», раздел
ведущего), runbook B `R5-CLAUDE-B-RUNBOOK.md` (`80f3370`), стандарт. База — код I2b `2ec3bca`.
Одна задача и один коммит кода с тестами: тексты дорог и доводка relay-транспорта затрагивают одни
и те же файлы (`relay_attempt.py`, `harness_attempt.py`), поэтому идут вместе.

## Цель

После I3 владелец, следуя документам и подсказкам продукта, ставит строку `claude-code` или `codex`
с подписочным входом в правильную папку, видит в Studio и Desk, что задача идёт внутри изоляции на
relay, получает отказ до запуска, если папка входа неверна, и понимает каждый отказ без чтения кода.
Grok и Kimi по-прежнему отказывают подписочной задаче — с честным текстом.

## Что сделать

1. **Тексты H5-V1** для профилей с `login_relay` (Claude Code, Codex) заменить на поведение I2b,
   для Grok/Kimi оставить «вход по подписке для этого harness внутри изоляции пока не поддержан».
   Места — «Передача» отчёта I2b: `harness_attempt.py` (docstring дорог),
   `harness_profile.py:77-88`, `failure_reasons.py`, `process_boundary.py:36-44,48-56,90-97`,
   `process_loans.py:29-33`, `codex_cli.py` (`_login`, `_read_attempt_home`),
   `provider_setup.py:357-361`, `desk-wizard-copy.js:420-428`, `desk-wizard-prepare-view.js:16-18`,
   `studio-agents-copy.js:196-199`, `studio-people.js:82-88`, `isolation_facts.py:143-148`.
   Перепроверить поиском по всему `src`, нет ли других мест.
2. **UI:** закрытый факт `task_road` в строке провайдера (`registry.execution_boundary(id,
   "dispatch")`); тексты Agents и Desk — по паре (`auth`, `task_road`).
3. **Дверь и мастер о папке входа** (вопрос 2 I2b): на relay-дороге `_launch_covers` требует
   `relay_home.relay_root_for(<login-home>) is not None` — чистая функция пути, без ФС; отказ на
   plan/preview/authorize тем же закрытым словом, тест через двери. Мастер `conduct providers` для
   профиля с `login_relay` проверяет форму `…\DecemberCommand\logins\<id>` и подсказывает
   `%USERPROFILE%\DecemberCommand\logins\<id>`; вход — с `CLAUDE_CONFIG_DIR`/`CODEX_HOME` на неё.
4. **Слова отказов не по входу** (разбор ведущего, 4): коды `mint`, `spec`, `enter`, `claim`,
   `claim_standing` получают префикс «the <tool> attempt could not start in isolation: …» вместо
   «login is not ready»; отказы входа (срок, env, папки, lease) — прежний префикс. Таблица
   `failure_reasons` и words-тесты — по таблице продукта.
5. **Доводка I2b** (проверка ведущего, находки f1, f2, f5):
   - f1: `_run_relayed` при отказе выхода после внутреннего `NotStarted` (`claim`, `claim_standing`,
     `spec`) возвращает внутренний отказ, а не `enter`; два теста через hook `exit` (claim бросает
     `OwnerRefused` и выход отказывает → слова claim; marker записан и выход отказывает →
     `claim_standing`).
   - f2: тест «все тексты листа вне схемы» кладёт значение под ключ вне схемы и вне `secret_fields`;
     мутант `every_text → secret_values` должен быть красным.
   - f5: relay-попытка без `claim` невозможна: `_attempt` для `_relayed(mode)` с `claim is None` —
     программная ошибка до lease; тест lifecycle передаёт настоящий claim.
6. **Документы владельца, EN и RU синхронно:** `README*.md`, `docs/first-run-v1*.md`,
   `owner-acceptance*.md`, `release-smoke.md` — подписочный вход без API-ключей, папки
   `%USERPROFILE%\DecemberCommand\{harnesses,logins}`, `conduct providers` при остановленном
   сервере, новая сборка, точные действия в UI; убрать отменённые API-only указания.
   `R5-REHEARSAL-RUNBOOK.md` пометить заменённым `R5-CLAUDE-B-RUNBOOK.md` (строки 16, 74 и `$H` из
   `%LOCALAPPDATA%` устарели).
7. **Runbook B** (вопрос 12): при «could not start the pinned build» или `recovery_required` — стоп,
   не повторять, перезагрузка ОС, затем `conduct ownership recover --dir $P` и
   `conduct ownership recover-login --auth-home $LOGIN`; перед стартом — `preflight.ps1` (отчёт
   П0–П5 A). Остальной текст runbook Codex не менять.

## Не делать

Codex A-I1, override Р3, паритет `_login_echo` (вопрос 10), новый ключ checker (вопрос 13), хеш
аккаунта в evidence (вопрос 6), тест `test_login_ownership` (вопрос 11), runner `retire` (вопрос 12,
кроме текста), нативный свидетель транспорта (решение Codex по D13), push, живые CLI.

## Проверка и сдача

Красная фаза на базе для новых и изменённых тестов; мутанты для новых стражей; целевые и затронутые
тесты в UTF-8 и cp1251; нативные — по файлу на процесс, если затронуты; новые файлы — в `CAPPED` тем
же коммитом (вносит ведущий); строка ≤ 100, файл ≤ 800. Отчёт `tasks/H5-SUB-R5-I3-REPORT.md` по
шаблону стандарта. Коммитит ведущий. Стоп и вопрос ведущему, если правка требует сменить закрытый
контракт (ключи checker, коды квитанций) сверх п. 4.
