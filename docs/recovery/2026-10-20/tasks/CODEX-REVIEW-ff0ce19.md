# Codex: R3.1 и состояние приёмки на ff0ce19

Дата проверки: 20 октября 2026, 23:13 МСК.
Проверенный commit: `ff0ce19fc2ead13040886367100f3159d62bb69d`, ветка `recovery/2026-10-20`.
Рабочая копия перед проверкой и после тестов чистая. Этот новый отчёт добавлен после проверки.
Код продукта, тесты и настройки ОС в ходе ревью не менялись.

## Решение по R3.1

В рамках diff R3.1 новых блокирующих замечаний не найдено. Старые замечания по историческому
запуску, мастеру, скрытой вкладке и приоритету устаревшего события учтены. Это независимое
ревью данной части, не приёмка всей V1 и не закрытие остальных задач R1–R4.

По коду проверены привязка эффекта к runId показанной сцены, фильтрация событий по актуальному
состоянию до выбора приоритета, очистка уже показанных эффектов и ожидающих событий под
мастером, подавление ожиданий в скрытой вкладке и одно одновременное ожидание кадров.

Рекомендация Codex по R3.1-Q3: для V1 допустим один план по актуальному состоянию при
возврате прокрученного за экран iframe. Это рекомендация по открытой UX-настройке.
Строго ограничены число ожиданий и удерживаемых view; массив pending всё ещё может расти
от реальных переходов, пока кадры не приходят. Не называть всю память модуля ограниченной.

## Независимые проверки

1. Три файла `tests/test_desk_motion_model.py`, `tests/test_desk_motion_source.py`,
   `tests/test_desk_motion_wiring.py`: 128 passed, 1 setup error, 19.30 s.
   Setup error — невозможность создать каталог pytest в sandbox TEMP.
   Только этот тест повторён с новым доступным basetemp:
   `test_a_comment_that_names_the_wire_is_not_the_wire` — 1 passed, 0.46 s.
   Итого все 129 выбранных проверок пройдены. Логи этих двух запусков на диск не сохранялись;
   результаты записаны в выводах инструментов данной сессии.

2. `browser_tests/test_desk_motion.py`: **35 passed, 120.05 s**, Windows/Chromium.
   Команда после загрузки `December-Command-Environment.ps1 -Quiet`:
   `python -m pytest -q -p no:cacheprovider --basetemp C:\Users\Пользователь\Documents\Codex\work\r31codex --junitxml=<outputs>/R3.1-Codex-browser.xml browser_tests/test_desk_motion.py`.
   Тестируется настоящий Desk с фикстурами данных. Скрытие вкладки и задержка кадров в
   соответствующих тестах управляются стендом; отдельную настоящую cross-origin iframe-пробу
   из отчёта Opus Codex не повторял. Полный core suite и весь browser gate не запускались.

## CI: установленные факты вместо гипотезы о пробелах

[№40](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39451610001),
commit `57fe629`: полностью зелёный, обе последовательности browser gate на трёх ОС.
Этот commit предшествует большинству новых исправлений.

[№41](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39465863068),
commit `c07f447`: прочитаны логи всех шести core-job и Windows browser-job.

- Во всех шести core-job падает `test_file_endings` на trailing whitespace в
  `R1.2b-REPORT.md`. Исправление находится в `395cecc`.
- Дополнительно Ubuntu/Python 3.11:
  `test_server_drain.py::test_the_drain_harness_delivers_a_real_ctrl_c_that_closes_the_idle_project`
  ожидал exit 0, получил -2. Итог job: 2 failed, 17147 passed, 546 skipped.
  [Лог job](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39465863068/job/118776966884).
  Остальные пять core-job имеют ровно один failure — проверку пробелов.
- Windows, обратный browser gate:
  `test_studio_runs_fold.py::test_both_lenses_and_the_inspector_start_inside_the_first_screen_at_1280x900[trassa-ru]`
  не дождался появления детей у `#studioPrimary` за 30000 ms.
  Captured stderr содержит `net/socket/tcp_socket_win.cc:1148 connect failed: 10055`.
  Это отдельная сигнатура, не следствие markdown whitespace. Первопричина здесь не установлена.
  [Лог job](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39465863068/job/118776966913).
  Архив `browser-gate-windows-latest`, artifact 12291495337, скачан и SHA256 совпал:
  `9ef6540de6f9a3beece9dcc728bbc13ce621ff9a118bc972beefa769612fd19f`.

[№42](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/39485630011),
commit `ff0ce19`, срез на 23:13 МСК: ещё выполняется. Зелёные обе core-job Ubuntu,
сборка одного wheel, installed-wheel road Ubuntu и macOS. Остальные core-job и три browser gate
ещё выполняются. Успех Ubuntu 3.11 в №42 показывает, что отказ Ctrl+C из №41 не воспроизвёлся
в этом прогоне; это не доказывает его устранение.

Логи CI доступны Codex через GitHub connector; дополнительный вход в браузере для этого не нужен.

## N1 и условия перехода к приёмке V1

N1 `0463759` проверен по diff и отчётам: изменения ограничены tests/docs. BOM исправляет
содержимое тестового PowerShell-скрипта; строгое декодирование UTF-8 и проверки изоляции
сохранены. Новые нативные прогоны в рамках этого ревью не выполнялись.
Доказательства исходного ParserError и вторичного UnicodeDecodeError разделены корректно.

Подготовку R5 можно продолжать, но общий зелёный CI не закрывает следующие решения:

- **R1.2c:** terminal stalled удерживает слот; pause/revoke дают 422. В текущем
  `policy_driver.py:260` освобождение по-прежнему только для reason complete.
  Отчёт `R1.2b-SLOT-AFTER-END.md`, раздел 4, явно оставляет этот случай открытым.
  Нужна отдельная правка освобождения вместе с честным отображением остановленного запуска:
  интерфейс не должен обещать resume, который backend отвергает.
- **H5:** предложение оставить V1 без подписочного входа внутри изоляции — открытое решение
  о составе продукта. Не считать его принятым владельцем только из-за зелёного CI.
- **R4:** решения об авторстве requested_by, неизвестном исходе после внешнего действия
  и соответствующие G4/G8 остаются открытыми. Полное независимое ревью R4 здесь не проводилось.
- Разделы «Ревью Codex» других задач не закрыты данным отчётом.
- Локальный full core на `395cecc` не включает R3.1; его результат нельзя подписывать
  как проверку `ff0ce19`. Релизные доказательства должны указывать точный commit и wheel.

Не повторять старое задание R3.1. Следующие действия: учесть отдельные сбои №41, получить итог
№42, разобрать R1.2c и оставшиеся решения H5/R4, затем завершить проверки и приёмку кандидата.

## Локальные материалы

В папке outputs чата:
- `R3.1-Codex-browser.xml` — JUnit моего браузерного запуска;
- `Codex-review-ff0ce19/ci41-unit-failures.json` — выдержки сбоев всех шести core-job;
- `Codex-review-ff0ce19/ci41-windows-browser-failure.txt` — stdout упавшего browser-модуля;
- `Codex-review-ff0ce19/ci42-snapshot.json` — срез статусов №42.
