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

21.10.2026: **правка `3f60f34` принята**, блокеров в проверенном объёме нет.
Меняется только кодировка тестового hook; его содержимое, LF и контроль реального исполнения
сохранены. Продуктовый `tool_env` не менялся. Исходные `facts.txt` и `pytest.out` согласуются
с SHA, чистотой копии и результатом полного прогона, указанными выше.

Независимая проверка на Windows/Python 3.12.14: `PYTHONUTF8=0`, `PYTHONIOENCODING` снят,
перед прогоном подтверждены `utf8_mode=0`, `encoding=cp1251`; git из набора Codex в PATH:

```text
.venv\Scripts\python.exe -m pytest -q tests/test_tool_env.py
  --basetemp C:\Users\Пользователь\Documents\Codex\work\hk-review-3f60 -p no:cacheprovider
23 passed in 1.44s
```

Полный suite после правки не повторялся; исторические ручные эксперименты Opus не повторялись.
Это одобрение узкой правки теста, не подтверждение зелёного CI.

### Передача по завершившемуся CI №46

Run `39645262035`, SHA `0a493ad8a9962cc6e442b9d9e3c8ca104c5a1096`: **10 job success,
2 failure**. Красные — Windows core py3.12 и Windows browser gate. Остальные core,
оба POSIX browser gate, сборка и обе POSIX wheel road зелёные.

Core job `119379019975`: единственное падение в `tests/test_boot_kuser.py` —
`test_a_read_that_runs_off_the_end_of_the_page_is_reported_as_partial_not_a_crash`,
строка 205, `Failed: DID NOT RAISE BootRefused`. Итог:
**1 failed, 17637 passed, 338 skipped, 2 warnings in 2137.28s**.
Это не Node timeout CI №43 и не три локальных encoding-падения.

Тест читает 64 байта от `0x7FFE0FF0`, предполагая недоступность соседней страницы,
но не создаёт и не проверяет такую границу. Успех `read_page` допускается только при
`done && got == size`; наиболее узкое объяснение — диапазон прочитался целиком.
Карта памяти runner не записана, причина доступности соседней страницы не доказана.
Обычный вызов читает `0x2C8` байт от начала KUSER и эту границу не пересекает.
Локальный целевой прогон `tests/test_boot_kuser.py -p no:cacheprovider` под `-X utf8`:
**23 passed, 1 skipped in 0.48s**; это не воспроизведение CI failure.

Задание Opus: заменить предположение о соседней странице контролируемой нативной границей;
отдельно детерминированно проверить `0 < got < size` со строгим `partial_read`.
Сохранить реальные проверки KUSER и отказ при неполном чтении. Оснований менять продукт
пока нет. Не добавлять retry, skip или увеличивать timeout. Достаточны целевые boot-тесты;
новый полный локальный suite перед R5 не нужен.

Windows browser job `119379019413`, artifact `12372154301`: оба порядка завершили
114/114 модулей, оба красные. Все три failed node сопоставлены по имени, ресурсу и времени
с `requestfailed` и Chromium `connect failed: 10055`:

- `bg`, `test_desk_wizard_git.py`, параметр `[en]`: не загружен
  `/panel/studio-tasks-model.js`; упал `bench.problems == []` (строка 318).
- `bg`, `test_studio_read_liveness.py`, `[error-same]`: не загружен `/panel/studio.js`;
  ожидание начальной загрузки истекло через 30000 ms.
- `bgr`, `test_desk_view_mode.py`, `[ru]`: `Page.goto` не загрузил `/host.html`
  с `ERR_NO_BUFFER_SPACE`, до проверки поведения флага.

Это повтор симптома R1.3; первопричина не установлена. Других зарегистрированных
`requestfailed` в этих артефактах нет. Ошибки не отменяются, gate остаётся красным.
По решению владельца глубокое расследование не останавливает предварительный R5.

Доказательства вне Git, рядом с рабочей копией:
`outputs/R5-candidate-0a493ad/CI46/`: полный `core-windows-py312.log`,
`browser-windows.log`, `jobs.json`, `browser-triage.json`, полный ZIP и извлечённые
`windows/bg/gate.json`, `windows/bgr/gate.json`, обе папки `netfail`, stdout/stderr падений.
SHA256 ZIP совпал с digest GitHub artifact:
`da6c5a9cef5cd20b5c96e486100ac5c82a89903044e70020a3a185e638eac21a`.

Следующий основной шаг — предварительная репетиция R5 на уже полученном wheel.
Тестовую правку границы памяти проверить отдельно; после согласованных правок нужен один
полный CI на новом SHA и его wheel для финальной приёмки. Провайдеры в этом ревью не запускались.
