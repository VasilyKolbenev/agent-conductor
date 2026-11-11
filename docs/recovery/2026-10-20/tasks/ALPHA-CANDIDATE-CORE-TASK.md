# ALPHA-CANDIDATE-CORE

Владелец 11.11.2026 поручил единый кандидат из текущего HEAD, полный Windows core
в UTF-8 и CP1251, при зелёном результате CI. Без моделей и нового цикла.
Позднее в том же задании новый стоп изменён с15% на12%; стартовый остаток16%.
WORKING-STANDARD обязателен, до/после полного прогона чистый detached worktree.

Кандидат зафиксирован до служебного TASK commit:
6d4bf97228529a7def649f912c1b8227830ac19c (6d4bf97).
Служебные документы задания/результата не меняют этот проверяемый SHA.
Source исходной recovery/2026-10-20 чистый; origin
https://github.com/VasilyKolbenev/agent-conductor.git.

Переиспользовать проверенный full-core.py из do-test-protocol-1111/core-ready,
после чтения и проверки покрытия новых модулей, с новым kit/worktree/output/temp
prefix. Все CONDUCT_ opt-ins и наследуемые PYTHON/GIT override очищены; модельные
native opt-ins не включать. Реальные vendor CLI не вызывать.
Каждый native файл отдельным процессом, затем ordinary shards; UTF-8 полностью
до CP1251. Никаких retry/skip/timeout ослаблений и исправлений кандидата по ходу.
Сохранить полный inventory, mode/import witnesses, PID, stdout/JUnit, skip reasons,
точные passed/failed/errors/skipped и clean HEAD/status до/после.

Только если обе кодировки без failed/errors: разрешён push точного candidate SHA
в новую candidate/alpha-2026-11-11-6d4bf97 на origin для запуска ci.yml.
Не force-push, не переписывать recovery или чужие ветки; сначала remote ref check.
Не публиковать release/tag. Проверить CI run/checks именно этого SHA; local green
не объявлять remote green. Если core красный — CI не запускать и не менять SHA
скрытно: сохранить весь результат/причины и первый несделанный шаг.

Kit вне Git: work/alpha-candidate-1111. На пороге12% штатно остановить controller
и уже запущенные дочерние проверки по записанным PID, сохранить незавершённый статус;
не называть его зелёным. Перед остановкой handoff, отчёт и отдельный docs commit.
