# CI-PORTABLE-ROOT — дизайн v2

## I1: portable collection, Windows-only use

A выбран: убрать eager native imports из helper/test module. Box native dependency
получается в функции при использовании, прежний Windows backend остаётся владельцем
отказа на POSIX. Deferred annotations не вызывают backend при collection.
Fixture constants/layout и pure role tests импортируются на всех поддержанных OS.
Одиночный _winlaunch import в native patch test переносится к реально gated use.

B: разделить portable declarations и Windows Box implementation на два новых
модуля с re-export. Больше diff/API surface без необходимости менять функции;
вернуться к нему только если A не сохраняет явные unsupported-use refusals.
Не заменять native module на безопасный stub, не расширять список skips.

## I2: actual installed entry and legacy Studio

A выбран: installed_probe использует owning ENTRY_PAGE для root expected bytes.
Wheel road сохраняет exactSHA/content-type/no-redirect/exhaustive assets guards;
пять экранов Studio проверяются на explicit /panel/studio.html. Root получает
literal Arachnid structural witness, не просто любой HTTP200 или отражение body.

B: новый универсальный route-provenance interface поверх всего server registry.
Это отдельное API/больший diff; текущий owning constant достаточен для root.
Никаких обновлений expected hash из фактически полученного body/отмены SHA.

## Доказательность

Existing CI logs — measured RED, дополнить быстрым локальным regression caller.
Import guard: fresh subprocess, Windows native dependency недоступна; pure module
и collectors импортируются, unsupported native use честно отказывает. Фактический
POSIX collection подтвердит CI; наличие локальной POSIX среды проверить без установки.
HTTP/provenance guard: настоящий served entry или faithful IO double на клиентской
границе, ожидаемые assets из installed files, negative wrong bytes/legacy missing
screen/root missing anchor обязаны падать. Не зеркалить реализацию.

Две readonly design-линзы до реализации: native boundaries и byte/UI truthfulness.
V2 отвечает находкам; scoped implementations, mutants, cross-review, code commit,
полный core exactSHA, conditional CI. Дополнительные CI findings не скрывать:
root решает доказанные blockers, остальные в report/open questions.

## Ответы независимым линзам

A1 принят: direct function-local native imports во всех девяти use sites,
TYPE_CHECKING-only alias для deferred annotations. Нет proxy/cache/stub/accessor.
A2 принят: fresh subprocess импортирует helper и шесть реальных collectors,
Windows backend imports блокируются finder-границей; ноль попыток при collection,
явный прежний ImportError при native use. Это не выдаётся за настоящий Linux run.
A3 принят: _winlaunch import в теле native patch test после verified_exe fixture gate.
B1 принят: root literal chat witness и classic anchor на /panel/studio.html,
не Studio screen ids на root; strict byte/type/redirect/census guards прежние.
B2 принят: regression caller installed_probe запускается -I в настоящем временном
venv с только собственным copied package/minimal metadata. Отдельный owning
ENTRY_PAGE override в копии ловит duplicated literal; HTTP expectations независимы.
Обе линзы дали GO. Root утвердил варианты A, реализация только в named scope.
