# H5-BRANCH-LEFTOVERS — задание исполнителю (Sonnet), 29.10.2026

Ведущий — Opus 5.5 (PROC-NO-CODEX). Основание: открытые пункты 4–9
`H5-CODEX-BRANCH-REVIEW-OPUS.md`; дизайн — read-only разведка со скептиками (workflow
`wf_d8d4158a-91d`, журнал в каталоге сессии). Ветка `recovery/2026-10-20`, основная рабочая
копия, от `56d0a22`. Исполнитель не коммитит. Пункты 2 и 10 ревью (документы) и 3 (декодер
лимитов после живого чтения), 11 (UI, UX-FIRST-RUN) — не здесь.

## Решения ведущего

1. **п. 5 — постоянный prompt ревью Claude** (`claude_code.py:249-251`). Первое предложение
   `REVIEW_PROMPT` — «Read the task supplied on standard input and produce the complete output
   document it asks for.»; хвост «Your final reply is that document: write the whole document in
   it, not a summary of it or a pointer to a file or plan.» — дословно прежний (live-v5-4).
   `VERDICT_PROMPT`, `CONSTANT_PROMPT` не трогать. Комментарий: согласование с рамкой `fd6b1bb`
   («not an input to find or review»), не воспроизведённый сбой — на `52f3d50` шаг goal Claude
   со старым текстом дал около 22 КБ (B2/B3); живой Goal v6 измерит рамку и argv вместе.
   Тесты: `test_command_claude_review.py:150-155` — буквальная запись argv, как
   `test_command_claude_transport.py:191-202`, плюс `REVIEW_PROMPT == argv[2]` и отсутствие
   «review» (ожидание этого теста меняется — разрешено); `test_dalio_analysis_prompt.py` — ветка
   claude: argv[2] содержит «output document» и не содержит «review» (файл в `CAPPED`).
2. **п. 4 — ключи маршрута в `config.toml` дома входа Codex** (`codex_cli.py:369`).
   `LOGIN_CONFIG_KEYS` += `chatgpt_base_url`, `openai_base_url`, `profile` — каждый ТОЛЬКО если
   сверка vendor (этап 0 workflow) не опровергла его; кортеж в несколько строк. Комментарий
   `:359-367` — ключи ищутся на любой глубине, base URL — config-двойник `OPENAI_BASE_URL`
   (`relay_env.py:24`); `login_home.py:21-23, 114-116` — «isolation or the login's route».
   Если сверка нашла ещё ключи маршрута или учётных данных — добавить с доказательством; файл
   слоя внутри `CODEX_HOME` (например `managed_config.toml`) — НЕ добавлять (это поле профиля и
   новый digest грантов), а записать как открытый вопрос. Тесты: строки parametrize
   `test_harness_login_method.py:197-201` (каждый ключ, `[profiles.x]` вариант, `profile`), проверка
   множеством рядом с `:225-243`, свидетель квоты в `test_relay_road_refusals.py` рядом с
   `:346-357` той же формой (`Site`, `site.login / 'config.toml'`, `not_supported`,
   `site.rows() == []`).
3. **п. 6 — сканер публикации** (`artifact_transport.py:661-666`): forced-пары — те, что получает
   попытка задачи этого транспорта: `relayed = self._confine and self._relay_road()` (предикат
   `relay_attempt.py:270, 292`), пара `access_only_switch` только при `relayed`; docstring `:641`.
   Тесты: API-дорога (boundary False/True) — значение оператора в `_sensitive_values()`, литерал
   кода нет (красный до); relayed-дорога — литерал остаётся (страж перекоррекции).
4. **п. 7 — спутники SQLite** (`login_home.take_back`, `:474-478`). Вариант B: спутник
   (`-wal`, `-shm` объявленной базы) рядом с базой, которая стояла до спавна, не удаляется и не
   считается остатком; рядом с базой, которую не удалось удалить, — остаётся и засчитывается;
   спутник без базы (сирота) удаляется, как сейчас. Форма — в журнале скептика п. 7
   (`_database_of`, `_COMPANIONS`, `_leaf_stands`). Докстринг — настоящая опасность (прерванный
   checkpoint, сеанс оператора в той же папке), не «потеря закоммиченных страниц»;
   `headless_login.py:349-353`, `codex_cli.py:329-332` — по факту. Тесты: база не удалилась →
   спутники стоят; `[database_stood]` в `test_codex_compatibility.py` (B: чтение проходит, база и
   спутники на месте); юнит «стоит база, added={wal}» → `()` и файл на месте; контроль «базы нет,
   added={wal}» → удалён.
5. **п. 8** — `codex_cli.py:292-293` (шесть пар: пять опубликованных ключей и R10) и `:439`
   (18 байт; лучше ссылкой на докстринг `:17` и тест `test_command_codex_version.py:205-212`).
6. **п. 9 — докстринги фейков** по факту (`522bbf0`: на Windows фикстура запускается текущим
   Python через `tests/_fakeprocess.py`; ссылаться на узкую формулировку `tests/_fakeexe.py:3-7`):
   `tests/_fakecodex.py:1-6, :231`, `tests/test_command_codex_transport.py:1, :28-31`,
   `tests/relay_roads.py:5-6`, `tests/_fakeboundary.py:13-14`,
   `tests/test_adapter_boundary_launch.py:4-5`, и Claude (V1): `tests/_fakeclaude.py:1-5, :293`,
   `tests/test_command_claude_transport.py:1`. Grok, Kimi, gh — не здесь (открытый вопрос).
   Переключатели Codex — «config keys (five published, one code-owned by R10)».

## Можно трогать

`claude_code.py`, `codex_cli.py`, `artifact_transport.py`, `login_home.py`, `headless_login.py`
(только докстринг/комментарий `:349-353`); тесты и фейки, названные выше. Остальное — стоп.

## Проверка и стандарт

- Каждый новый страж сначала красный на сравнении («N failed, M passed»); мутанты — в копии
  `Documents\Codex\work\leftovers-mut` (M0, SHA-256, копия удалена), таблица «Мутант | Результат |
  Что красное»: п. 1 — старый текст, «review» назад, без хвоста; п. 2 — убрать каждый ключ; п. 3 —
  литерал всегда, пара никогда; п. 4 — спутник всегда удаляется, `base in left` убран, проверка
  существования базы убрана; п. 5–6 — не применимо (текст).
- Прогон: `run-scoped.ps1 -Pattern 'claude_code|codex_cli|artifact_transport|login_home|
  headless_login|relay_attempt|_fakecodex|_fakeclaude|relay_roads|_fakeboundary'` (одной строкой)
  — все тесты, чей текст упоминает затронутые модули, в UTF-8 и cp1251; метки новые, до 2 знаков.
  Тесты не запускать, пока нет `%USERPROFILE%\Documents\Codex\work\lead-final3\done.txt`
  (идёт полный core ведущего).
- Строки ≤ 100; `codex_cli.py` ≤ 800 строк (сейчас 785).

## Стоп-условия

Файл вне списка; vendor опровергает ключ п. 2 или требует поля профиля; ожидание существующего
теста, кроме названного в п. 1, меняется.
