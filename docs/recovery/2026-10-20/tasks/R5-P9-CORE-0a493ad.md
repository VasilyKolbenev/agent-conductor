# Отчёт по задаче: R5 п. 9 — полный core на кириллическом профиле, commit 0a493ad

- Исполнитель: Claude Code / Opus 5.5. Дата: 21.10.2026, 21:35–23:13 МСК.
- Что: `R5-PLAN.md` п. 9 — полный core-suite на этом ноутбуке, точный SHA, чистая копия.
- Копия: `git worktree add --detach C:\Users\Пользователь\dc46 0a493ad`; `git rev-parse HEAD` =
  `0a493ad8a9962cc6e442b9d9e3c8ca104c5a1096`; `git status --porcelain --untracked-files=all`
  пуст до и после прогона.
- Среда: Windows 11 Pro 10.0.26300, dev `.venv` (Python 3.12.14), git 2.53.0.windows.3 из набора
  Codex; профиль `C:\Users\Пользователь`, ANSI cp1251, OEM 866. Скрипт окружения подключён, затем
  `PYTHONUTF8` и `PYTHONIOENCODING` сняты (в CI их нет, у пользователя тоже);
  `PYTHONPATH=<копия>\src`, `conductor.__file__` — из копии. Процесс — дочерний приложения
  Claude (MSIX), каталоги прогона вне `%LOCALAPPDATA%`.
- Команда (как шаг `Tests` в `ci.yml`): `python -m pytest -q --basetemp C:\Users\Пользователь\pt-9
  --junitxml <out>\junit.xml`; basetemp 26 символов. Первый запуск с `pt-46` (27 символов, сверх
  предела) остановлен через 10 с до первого теста и не засчитан.
- Доказательства: `C:\Users\Пользователь\Documents\Codex\work\p9-0a493ad\` (`facts.txt`,
  `pytest.out`, `pytest.err` пуст, `junit.xml`).

## Итог

**3 failed, 17 564 passed, 409 skipped, 4 warnings за 5881 с (1:38:01); exit 1.**

Все три падения — `tests/test_tool_env.py`:

- `test_git_runs_no_hook_under_the_built_environment_and_runs_it_without[absent]`;
- `test_git_runs_no_hook_under_the_built_environment_and_runs_it_without[empty]`;
- `test_the_built_environment_silences_a_hook_of_a_repository_local_hooks_path`.

Падает контрольная половина («control: nothing silences the hook»): `git commit` с хуком в
обычной среде возвращает 1.

## Причина — дефект теста, класс N1

`_repo_with_hook` пишет `pre-commit` через `write_text` без кодировки. Без UTF-8-режима Python
пишет в cp1251, `sh` из git читает скрипт как UTF-8, кириллический путь маркера приходит в `sh`
другим путём, хук падает, коммит тоже. Продукт хуков не пишет; проверяемое им глушение хуков
не затронуто.

| Проверка | Результат |
| --- | --- |
| ручное воспроизведение (`git init`, тот же хук, обычная среда), путь с кириллицей | exit 1, stderr `.git/hooks/pre-commit: line 2: C:/Users/<мусор>/pt-hk/the-hook-ran: No such file or directory` |
| то же в ASCII-пути (8.3 `C:\Users\73B5~1\...`) | exit 0, маркер есть |
| `tests/test_tool_env.py` в копии без `PYTHONUTF8` | 3 failed, 20 passed |
| то же с `PYTHONUTF8=1` | 23 passed |
| после правки (`encoding="utf-8"`), без `PYTHONUTF8` | 23 passed |
| после правки, с `PYTHONUTF8=1`, вместе с `test_command_line_cap.py`, `test_file_endings.py` | 189 passed |

CI этого не ловит: профиль runner в ASCII. В прежнем локальном прогоне на `395cecc` этих трёх
падений нет; вероятная причина — `PYTHONUTF8=1` из скрипта окружения, но среда того прогона
в документах не записана, так что это не доказано.

## Правка

`tests/test_tool_env.py`: хук пишется в UTF-8 (`encoding="utf-8"`), с комментарием о причине.
Отдельный локальный коммит, без push. Код продукта не менялся.

## Не проверено

- Полный suite после правки не повторялся: изменён один тестовый файл, его прогон — в таблице.
- Python 3.11 локально недоступен; 3.11 подтверждается только core-job CI.
- Падение CI №46 `tests windows-latest py3.12` (шаг `Tests`, строка лога 286) к этим трём не
  относится: в CI профиль ASCII. Его лог ждём от Codex.

## Ревью Codex

Статус: ожидает.
