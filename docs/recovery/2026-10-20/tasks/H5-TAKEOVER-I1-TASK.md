# H5-TAKEOVER-I1: resume Opus's preserved offline slice, 2026-10-30

Owner request: preserve the current project and continue while the Claude account appeal
is pending. Budget: 20-25% of the currently available Codex allowance. Starting observation:
47% used, 53% remaining; reserve at most 11-13 percentage points, with a stopping margin.
Codex resumes the lead role under this explicit request; no change to V1 product scope.

## Preserved baseline and scope

- Main branch: `recovery/2026-10-20`, original HEAD `183904f19ea94f24190f4fe0e21ec2a65022d7a4`.
- Source snapshot: `Documents/Codex/work/takeover-20261030T130259Z`.
  Verified Git bundle, working source ZIP, binary patches and original index. All 19 dirty
  files are Opus's pre-existing work, including the previously untracked I0-I1 TASK.
- Adopt `H5-GROK-DIAGNOSE-TASK.md` I0-I1 and DESIGN commits `349bf1a`, `183904f` only.
  Recording the TASK now does not retroactively establish compliance of prior work.
- Installed product `14f94cf9f8f0` and the live `DecemberV1` project are preserved separately.
  Stop the existing server with Ctrl+C before taking a stable project snapshot.

## Work and evidence

1. Verify the inherited Claude/Codex snapshot against unchanged source, using fake providers.
2. Verify the new file channel, its failures, cleanup and UI contracts in both encodings.
3. Run the I1 mutants from DESIGN section 8 in an isolated source copy, including a no-op.
4. Correct only proven failures and the inaccurate stdin-only refusal text; preserve
   existing Claude/Codex behavior and all credential and boundary protections.
5. Independently review the final diff, commit the locally verified I0-I1 code separately
   from the report, and record the first unfinished step and evidence paths.

No live provider calls, new login, token handling, model selection, new product server,
release, push or deployment belongs to this task. No full core suite is required for this
local slice; CI, native Grok execution, I2-I5 and owner acceptance remain outstanding.
Grok's existing executor capabilities and the installed product are not expanded here.

## Stop rules

Preserve any failing result. If the budget margin is reached or the inherited slice needs
broader contract changes, stop with an exact handoff, not an accepted-release claim.
The absence of Opus changes the available reviewer, not the level of proof required.
