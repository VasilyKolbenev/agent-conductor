Итог: TASK/DESIGN подготовлены, реализация не начата | `e009342` / `be27a53` |
новых тестовых прогонов и vendor calls 0 | остановка на пороге 30% остатка.

# DO-TEST-PROTOCOL — точка продолжения

База `3a113c2`, чужих правок не было. Рабочий стандарт прочитан.
TASK `e009342`; предварительный DESIGN v1 `be27a53`. Две независимые source-линзы:
do_tests_seam и do_rejected_inspector. Полное ревью DESIGN до реализации ещё требуется.

## Подтверждено по коду

- codex_patch_dispatch публикует патч, но не выполняет тесты до checker.
- Есть ProcessRunner и offline container_profile без home; vendor _attempt для
  тестов применять нельзя, поскольку он включает login/relay.
- separate_stderr=True теряет stderr; для unittest это теряет сам протокол.
- attempt_test_evidence импортирует только внешние counters, не argv/output;
  импорт отчёта не считается исполнением тестов.
- accept_capture сохраняет snapshot до checker; связь с ним доступна Inspector
  через успешный record_dispatch. CorrectionFeedback имеет изменённые files,
  но не полную связь с накопленным acceptance snapshot.
- attempt_detail:125–139 прекращает построение view без успешного proof;
  studio-atlas-inspector не отображает rejected findings.

DESIGN рекомендует одну дорогу apply → bounded tests → seal → checker,
с объявленным test plan и проверенным runner pin, без shell и host fallback.
Перед wiring нужно доказать штатный запуск полного доверенного Python runtime
в offline boundary. Для diff отказа нужна явная exact-attempt snapshot-связь;
снятие условия succeeded само по себе не является исправлением.

## Уточнения владельца

Будущие задания автоматически используют feedback отказа для следующего
исправления до достижения критериев цели, в согласованных scope и budgets.
При исчерпании сохраняется прогресс и запрашивается продление. Это не бесконтрольный
повтор неизвестного исхода. Текущий terminal run и его no-retry grant не меняются.
Arachnid — постоянная среда для харнессов; аналогия владельца — OpenClaw.
Далио — процесс внутри неё, не повторяющийся главный заголовок обычного UI.
Направление записано в v1-v2-scope и OPEN-DECISIONS; тексты продукта пока не менялись.

## Не сделано

Красное воспроизведение на публичном шве ещё не запускалось. Новых production/test
файлов нет, мутационные и полные проверки не выполнялись; мутанты пока неприменимы.
Нет установки новой сборки и нет заявленного исправления. Рабочая Studio — 4deb571.
Документы проверены git diff --check; remote CI не запускался.

Последний доказанный шаг: source-причины локализованы, TASK и DESIGN закоммичены.
Первый несделанный: публичная red-регрессия порядка apply/tests/checker и native
witness доверенного runner; затем ревью DESIGN и минимальная реализация.
Ревью Codex: source-факты проверены; DESIGN и реализация ожидают продолжения.
Не повторять counter-src-4deb571-r2, не менять его verdict и не подставлять
внешние 4 passed вместо протокола, отсутствовавшего у checker.

Остановка по прямому условию владельца: замер primary usedPercent 70,
остаток 30%. После замера только фиксация этого отчёта и handoff.
