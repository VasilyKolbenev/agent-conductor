# H5-CODEX-TEST-LAUNCH — Windows test PE

Codex 28.10.2026: узкое техническое решение в рамках подключения Codex, чтобы завершить core
без отключения Windows App Control. База — текущий A-I1 worktree, не продукт B3.

Факт: CodeIntegrity 3033/3077 блокирует synthetic PE+ZIP, созданные `_fakeexe.build`.
Успешный и блокированный экземпляры NotSigned, body одинаков, различаются ZIP timestamp.
Конкретная причина решения доверия Windows не доказана. Это не дефект настоящего Codex.

Вариант A — фиксированный ZIP timestamp: воспроизводимые байты, но не обещание допуска Windows.
Выбран B — явный test-only запуск только зарегистрированных fixtures через текущий Python.
Это меняет способ исполнения тестового двойника; нативный single-binary путь подтверждают
отдельные реальные CLI/native проверки. Нельзя заявлять, что Python-double доказывает PE startup.

## Названные файлы

Исполнитель только: `tests/_fakeexe.py`, новый `tests/_fakeprocess.py`, новый
`tests/conftest.py`, `tests/_fakeboundary.py` (только регистрация перемещённой копии), новый
`tests/test_fake_process_runner.py`, `tests/test_command_line_cap.py` (внести новые файлы).
`src/`, остальные fixtures, политика Windows, protected installs и реальные pins не меняются.

## Контракт

- `_fakeexe.build` регистрирует точный созданный fake-путь, его модуль и digest. После изменения
  bytes отказывать, а не переходить к native попытке. Копия регистрируется явно после сверки.
- Scoped pytest Popen seam только Windows и только такой registry entry. Прочие процессы,
  реальный Codex/Claude/Grok и native `_winlaunch` не перехватываются. Нет fallback после ошибки.
- Запуск через известный текущий Python сохраняет logical argv, cwd, env, stdin/EOF/stdout/stderr,
  таймаут и обычную уборку ProcessRunner. Не использовать shell и не подменять готовым outcome.
- Прямой subprocess.run в fakegh покрывает тот же seam. Не пропускать тесты ради допуска ОС.
- Red/green и различающие проверки: argv+stdin/EOF, timeout/termination, tampered fake refusal,
  незарегистрированный pin идёт исходным путём; положительный настоящий Python subprocess.
  Нативные fake PE не запускать в расследовании; subprocess граница в red — recording stub.
- Код с тестами отдельным коммитом после ревью; отчёт фиксирует, что именно доказано Python
  double, а что остаётся реальным native свидетельством. Один раунд реализации и ревью.

## Уточнение наблюдаемости P8 (A-I1)

No-auth exec в S164 допускает UnauthenticatedAuthProvider и сетевые повторы; быстрый локальный
auth-отказ не гарантирован. Кроме того, production dispatch отдельный stderr отправляет в
DEVNULL; прежний capture не видел stderr. Codex разрешает только в no-auth P8 scoped observer
заменить `separate_stderr` на false, сохранив original spec, argv, env names, timeout и bounded
output. Ни paid smoke, ни продуктовый запуск не меняются. После первого плохого clean исхода
сразу стоп, poison не запускать. Один новый clean диагностический замер, 60 с, полный bounded
вывод вне Git; неизвестный исход не разрешает дальнейших повторов. Если clean доказал ожидаемый
auth-отказ, завершить уже назначенный poison/control P8 без повторения clean. Исходный timeout
сохранён. Уточнение Codex дано до результата диагностического запуска.

## Различающее наблюдение P8

Диагностика 28.10 сохранила Windows error 11003 при DNS, затем waiting for network. Отдельный
`codex-dns-env-witness.py` выполнил два DNS-only child через подписанный Python: env={} дал 11003,
тот же env плюс SystemRoot разрешил адрес (2 записи). Код/endpoint одинаковы. Это измеренная
причина отсутствия DNS в окружении свидетеля, не доказательство дефекта подписки или адаптера.

Codex разрешает минимальную правку test `_real_harness` и trusted control: на Windows передавать
SystemRoot из системного окружения, остальные невыбранные env не копировать. Offline guard
должен различать потерю этого параметра и появление лишних имён. После него полный P8 один раз
на новом temp с тем же timeout 60 с. Если и этот исход не пройдёт — сохранить причину и стоп.
