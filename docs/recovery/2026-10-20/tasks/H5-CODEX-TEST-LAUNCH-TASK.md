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

Первый fix сохранил 11003: diagnostic env_names доказал, что SystemRoot вообще не передан.
Причина по коду: Windows Python нормализует os.environ в SYSTEMROOT, runner делает dict snapshot
и точный allowlist lookup. Guard только декларации был недостаточен. Root заменил его реальным
resolve/runner capture без spawn: 1 failed на прежнем регистре; SYSTEMROOT даёт 2 passed.
Предпосылка теперь проверена на действительном выбранном окружении. Codex разрешает завершить P8
одним новым полным запуском с этим регистром, без изменения timeout. Предыдущий исход сохранён.

Теперь clean/poison оба completed exit 1 (15,859/18,469 с), без truncation/env echo/PROBE,
оба дошли до HTTP401 на Responses. Сравнение hash всей final-error строки отказало. S164
`protocol/src/error.rs:637-660` добавляет в неё cf-ray/request id; равенство целых строк —
неверный контракт. Утраченные terminal bodies восстановить нельзя, их полное равенство не доказано.

Codex: для конкретного config-poison достаточно уже измеренных invariants выше и ровно одного
trusted-control, который должен отказать с PROBE до сети. Clean/poison снова не запускать.
Будущий тест нормализует только два именованных trace-поля в metadata suffix после url;
status/body/url/auth error/code сохраняет. Offline guards различают содержательные изменения;
canonical digest сохраняется до редактирования диагностики. Это не объявляет старый тест зелёным.

Trusted-control также отказал своему старому критерию (17,8 с, без PROBE). Новое основание S164
`config/src/loader/mod.rs:89-104,1325-1341,1924-1934`: model_provider теперь безусловно удаляется
из project-local config даже у trusted проекта. Поэтому пара на этом ключе не проверяет trust.

Codex разрешает продолжить узко, заменив оба плеча на невалидный TOML
`[PROBE_INVALID_PROJECT_LAYER` с переводом строки. S164:1893-1912: trusted parse error отказывает,
untrusted превращается в пустой disabled слой. Trusted witness: nonzero, точная строка
`Error parsing project config file` и путь именно этого файла. Полный bounded combined output
контроля сохранять при ошибке; generic nonzero не принимать. Новый offline guard и один полный
P8 с новым poison, прежними production argv/доступом/60 с; это новый различающий эксперимент,
не retry старого control. До успеха P8 не закрыт. Старые результаты остаются в отчёте.

## Граница argv после полного прогона 8a4fe5f

UTF-8 ordinary core: 18970 passed, 409 skipped, один отказ WinError 206 в
`test_check_road_limits.py` на логических 32767 единицах. Python-backed fixture добавляет
путь интерпретатора, поэтому его физическая командная строка уже превышает границу ОС.
Это дефект тестового свидетельства после замены запуска, не основание менять продуктовый лимит.

Codex 28.10 разрешает один дополнительный названный файл: `tests/test_check_road_limits.py`.
Короткая реальная калибровка остаётся. Граничная пара записывает argv на Popen seam и завершает
его контрольным исключением до физического запуска: ровно 32767 достигает seam один раз с
marker, 32768 отказывает до seam и marker. Проверить точный logical argv и Python prefix.
Прежнее утверждение о физическом запуске fixture на границе заменить точным описанием.

Чтобы сохранить независимое свидетельство настоящего потолка Windows, в том же файле добавить
Windows-only тест подписанного текущего Python с `-c pass`: физические 32767 единиц завершаются,
32768 дают WinError 206. Без fake PE, сетевых запросов, запуска harness и подмены product кода.
Доказательства: исходный full-core failure; оба encoding целого файла; мутанты отсутствующего
gate, неверного предела и no-op реализации должны быть пойманы. Не снижать лимит, не skip
граничную пару, не менять ProcessRunner/_procgroup/_fakeprocess. Код отдельно от этого решения.
