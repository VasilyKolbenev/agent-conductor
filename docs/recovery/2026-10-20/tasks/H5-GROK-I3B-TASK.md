Итог: review_only projection/UI принят Codex в оставшемся бюджете; Grok пока не активировать.

# H5-GROK-I3B: a read-only harness remains visible and owner-selectable

Authority: owner continuation 30.10.2026 and H5-GROK-DIAGNOSE-DESIGN §4 (`183904f`).
I2 and I3A are implemented separately. This slice prepares the remaining UI contract on fakes.
Account usage is 57% at this decision; original allowance began at 47% used. Stop and report
if this bounded slice cannot finish within the overall 20-25% of that original remaining 53%.

## Contract

Provider subscription task_road: dispatch is exactly True -> boundary; dispatch is exactly
False and review is exactly True -> review_only; otherwise refused. Exceptions and non-bools
must not gain permission. Keep existing non-subscription/unsupported projection behavior.
Alternative rejected: call a read-only provider boundary. That would falsely advertise do.

Studio parser preserves the new road and its quota row. People use a wait tone with explicit
RU/EN meaning: only a read-only task in isolation on an access-only login copy, no editing tasks.
The wizard carries taskRoad into its roster, excludes review_only from dispatch and checker
roles, and permits only an eligible owner-fixed selection. Previous/suggestion/quota ranking
must never auto-select it. Preserve existing behavior for boundary/refused rows.
No Grok capability/profile/argv change, live probes, browser server or product installation.

## Scope and proof

Implementer owns adapters/provider.py; panel/studio-model.js, studio-people.js,
studio-agents-copy.js and desk-wizard-roles.js; new tests/test_review_only_road.py;
directly affected census expectations in test_provider_task_road.py,
test_studio_provider_arms.py and test_studio_runs.py. No other files without telling the lead.
Lead owns CAPPED, report, handoff and commits. studio-model remains at 800 lines.

Red comparisons before behavior, then minimal implementation. Test public provider projection
and execute real JS parser/people/wizard code through the existing Node seam. Prove preserved
quota data, readable RU/EN status, owner choice, automatic rejection, do/checker exclusion and
strict boolean/error handling. Existing ordinary provider choices remain positive witnesses.
Scoped UTF-8 and cp1251, relevant existing modules, meaningful mutants for lost road parsing,
false boundary claim and automatic/forbidden role selection. M0 first; copies restored/removed.
Independent review, local code/report commits; no push, full core or live acceptance claim.

Next after this slice: activate Grok review/file/relay atomically, update its fake transport
witnesses, then G2/P, protected build and G6 before any owner-authorized Dalio run.
