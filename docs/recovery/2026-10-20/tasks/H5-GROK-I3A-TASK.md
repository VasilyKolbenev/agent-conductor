Итог: подготовка read-only контракта принята Codex; база I2 `7cdaae0`.

# H5-GROK-I3A: task mode and checker restrictions before provider activation

Authority: owner continuation 30.10.2026, H5-GROK-DIAGNOSE-DESIGN §4 (`183904f`).
This is the next bounded offline slice in the remaining allowance, not permission to spend
additional account limits or activate Grok. No new live calls, install, server or push.

## Contract

Add task_modes to AttemptLaunch, default ATTEMPT_MODES. A provider may narrow it to review.
_road_covers, _boundary_refusal and _hold_boundary must agree. A forbidden mode refuses before
preflight/claim on every road, including unconfined/API execution; the spawn guard rechecks it.
Use the existing boundary refusal sentence and outcome. Do not add profile dataclass fields.
ArtifactAwareTransport defaults to serving independent checks as before; serves_checks=False
prevents automatic verify_for/verification_started when review_enabled=True.

Alternative rejected: only hide dispatch in Studio. Direct runtime callers must refuse too.
Keep existing Claude/Codex/Grok defaults and profile snapshots unchanged. This commit introduces
the mechanism on a synthetic review-only fixture; activating Grok follows in a separate atomic
slice with review_only projection, wizard restrictions and file-channel argv.

## Scope and proof

Implementer owns adapters/harness_attempt.py, adapters/artifact_transport.py and one new
tests/test_harness_task_modes.py. Parent owns CAPPED, report and commits.
Artifact transport is 797 lines of 800: replace its existing checker guard in place.
No shared-file writes by other agents.

Red comparisons before implementation; public prepare/execute witness for denied dispatch with
zero preflight children, no claim and no files. Positive review still works on fake CLI/boundary.
Independent checker declaration is absent for serves_checks=False and unchanged by default.
Prove _hold_boundary protects a prepared request if task_modes narrows before spawn.
Mutants: no early mode check, no spawn recheck, no checker restriction; no-op must not make the
positive review pass. Scoped tests in UTF-8 and cp1251, plus unchanged Claude/Codex snapshots.
No full core for inactive-provider preparation. Independent review, code/report commits and
handoff include the first unimplemented activation step and the remaining live gates.
