# December Command: working context

Read `CONTRIBUTING.md` (or `CONTRIBUTING.ru.md`) and the relevant code and tests before changing behavior.

The project was recovered on 2026-10-20 from `feature/v1-desk-integration` at
`4d0e3af669e783f248cf4c4230e805e76c19836a`. This is a historical baseline,
not a requirement that HEAD remain there. Inspect the current branch, HEAD,
diff and status; preserve existing work.

Start with `LOCAL-SETUP.md`, `BASELINE.md`, `CONTINUATION-PLAN.md`
and `CI-BASELINE-NOTES.md`, all under `docs/recovery/2026-10-20/`.
They distinguish recovered evidence, new plans and checks actually run.
Original local chats and several handoffs are still missing; do not invent
their contents or treat old pending comments as current without checking
later commits and current code.

The current delivery scope is V1, governed by `docs/v1-v2-scope.md`.
Codex is the technical lead and independent reviewer. Claude Code handles
senior investigation and scoped implementation as described in
`docs/recovery/2026-10-20/CLAUDE-CODE-HANDOFF.md`.
Execute routine reads, edits and tests within the
assigned task without repeatedly asking for permission.

Use the existing virtual environment and fixture/fake-provider tests.
Record exact commands, results and untested limits. Windows tests need a
short temporary path; the full core suite and both browser-gate orders
are separate, substantially longer checks.

H5 login-home writes remain closed in the recovered code. Opening the flag
is not a substitute for reviewing writable objects and execution boundaries.
Desk motion requires production integration; its instrumented bench alone
does not prove that integration. See the plan for acceptance criteria.

Keep task briefs, decisions, review findings and handoffs in versioned
documents alongside the plan. Preserve the distinction between implemented,
locally tested, CI tested, reviewed and accepted by the owner.
Do not put credentials or large diagnostic archives into repository commits.
