# H5-GROK-DIAGNOSE — задание исполнителю (Sonnet), часть 1: I0–I1, 30.10.2026

Ведущий — Opus 5.5 (PROC-NO-CODEX). Дизайн — `H5-GROK-DIAGNOSE-DESIGN.md` с дополнением 1;
прочитать целиком до кода. Ветка `recovery/2026-10-20`, основная рабочая копия. Исполнитель не
коммитит. Часть 2 (I2 relay, I3 review-дорога и закрытия, I4 `review_only` и UI, I5 seed) — после
пробы P владельцем; её задание выйдет отдельным дополнением.

## I0 — снимки ядра до правок

На текущем HEAD (до любых правок `src/`) — тест-свидетель, фиксирующий для Claude и Codex
(подписка через relay и API-ключ; dispatch, review, checker) поля `CommandSpec` (argv, env,
stdin_bytes, separate_stderr, sensitive_extra) и `ProviderAuthority.facts` (дизайн §5). После
каждой итерации свидетель совпадает побайтно. Новый тестовый файл — в `CAPPED`.

## I1 — канал задачи `file`

По дизайну §1: константы `TASK_CHANNEL_FILE`, `TASK_CHANNELS`, `OFF_ARGV_CHANNELS`,
`TASK_FILE_NAME` и проверка имён профиля (`harness_profile.py`); замены `== STDIN` на
`in OFF_ARGV_CHANNELS` (`headless_cli.py:173, :503`, `artifact_transport.py:19, :124` — строка в
строку, файл 797/800); новый `adapters/task_file.py` (`path_in`, `place`, `TaskFileRefused`;
O_EXCL, read-back, `st_nlink == 1`, пределы и UTF-8, отказ вне дома попытки или relay-дома,
обёртка всех ошибок); одна точка записи в `headless_spec.attempt_spec`; имя файла в первых
именах `discard`/`sweep` relay; факт канала для гранта (`policy_providers.py`); панель знает
`file` (`CHANNELS`, копии RU/EN) — JS-тесты панели зелёные.

На I1 ни один провайдер ещё не использует канал `file`: свидетели — на тестовом профиле с
`task_channel=file` (фейк читает задачу из файла). Мутанты дизайна §8 для I1.

## Можно трогать

`src/conductor/command/adapters/{harness_profile.py, headless_cli.py, artifact_transport.py,
headless_spec.py, relay_attempt.py, task_file.py (новый)}`, `src/conductor/command/
policy_providers.py`, `src/conductor/panel/{studio-automation-providers.js,
studio-automation-copy.js, studio-run-docs-copy.js, studio-controls.js}` (только знание
`file`), тесты (новые — в `CAPPED`), JS-тесты панели. Остальное — стоп и вопрос ведущему.

## Стандарт

Каждый новый страж — красный на сравнении до правки; мутанты — в копии
`Documents\Codex\work\grok-mut` (M0, SHA-256 до и после, копия удалена); строки ≤ 100;
`artifact_transport.py` ≤ 800 строк. Прогон: `run-scoped.ps1 -Pattern` по затронутым модулям в
UTF-8 и cp1251, метки — новые, до 2 знаков. Существующие тесты Claude, Codex и checker — без
правок ожиданий (дизайн §5); нужна правка — стоп.
