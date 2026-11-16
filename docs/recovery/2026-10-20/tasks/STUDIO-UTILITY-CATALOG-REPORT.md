# Studio subscription setup catalogue

Result: locally verified | code `6127f40d` | 597 checks covered per encoding,
0 failures after correction | no scope change | integrate and run candidate CI.

**Scope.** TASK and DESIGN `a6f69d34`. Baseline `305003d8`. The new worktree
started clean. No changes to the candidate worktree, providers, personal accounts,
dependency installations or release state.

**Reproduction.** The routing-label test for conditions initially failed with
`JSONDecodeError` at character 106. All 29 tests in the two matrix modules
failed through the same catalogue collector. The cause was JavaScript string
concatenation inside `utility.setup_paths`, which the browser evaluated, but the
strict bilingual data reader could not decode. Splitting the two instructions
into two JSON-compatible translation rows preserves the complete information in
the alternate-terminal disclosure. The edited text lines measure 100, 96, 72
and 90 UTF-8 bytes.

**Verification on Windows.** The same reader decoded 1,546 distinct keys in 15
catalogues. Both original matrix modules passed all 29 tests. All ten direct
source-reader consumer modules, Studio i18n, module/wiring/source guards, docs,
assets and provider-card Chromium tests gave 596 passed and one optional wheel
test skipped per encoding. The developer venv lacks Hatchling. Re-running that
specific wheel test with the local verified builder's site-packages added for
that invocation passed in each encoding. Python reported UTF-8 and CP1251.

**Mutants.** Fresh source copy, original files restored and hashes compared:
M0 4 passed. M1 reintroduced a plus operator inside English copy, 1 routing
failure. M2 removed the Python hint from the rendered card, 3 browser failures
in English and Russian across the two Studio entries.

**Handoff.** No unrelated changes or deviations. Source and browser guards
remain in force. No full candidate or CI claim from this branch. Next step:
integrate into the release candidate. Technical lead review pending.
