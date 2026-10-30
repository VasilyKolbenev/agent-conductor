Итог: Grok включён, полный core зелёный в двух кодировках, сборка установлена; G6 ждёт свежего входа.

# H5-GROK-ACTIVATE — evidence checkpoint

Authority: TASK a46edea, live-order decision a93a09b, budget extension fd1527c.
Owner stop is now 20% remaining. No push, real model call or owner grant performed here yet.
Code: seed 6a9e359, activation 6039eeb, shared-contract follow-up af799fb.
Shared census: 0d781e1; final wizard/login fixture migration: 48a787c.
Current exact candidate for the complete clean rerun is 48a787c.

## Proven code behavior

Grok 1.0.5 uses the file channel and access-only GrokRelay for subscription review.
Only Read/Grep/Glob are allowed; edit/shell/web/MCP tools are explicitly denied.
Production dispatch and independent checker remain closed, output bound is 48 KiB.
Seed excludes AGENT.md, CLAUDE.local.md and .cursor alongside existing instruction names.

- Activation red: five failed comparisons before implementation. Focused final: 362 passed,
  3 opt-in real-smoke skips in EACH UTF-8/cp1251 run; unchanged 16 core snapshots included.
- Activation M0: 5 passed. Six killed mutants: open dispatch (3 failures), open checker (3),
  stdin channel (3), missing deny Edit (2), missing relay (2), empty task payload (2).
- Seed red: 6 failed on actual staged files. Green: 216 passed, 4 platform skips in EACH
  encoding. M0 6 passed; each missing exclusion gives 2 failures; empty seed gives 6.
- Initial seed sandbox runs: 28 failed/189 passed/3 skipped per encoding, Windows hardlink
  access denied. Native reruns above use separate short temp roots; those failures are not
  product proof. The same sandbox restriction affected a later snapshot command (10 failures);
  native module-graph + snapshot proof is 22 passed in each encoding.
- Full-check follow-up: six stale Grok boundary/stderr witnesses reproduced as 4 failed/74
  passed and 2 failed/61 passed. Updated tests retain no-spawn refusal and exact stdout with
  stderr absent from artifact/journal. Final four modules: 161 passed EACH encoding.
  M0 3 passed; open dispatch mutant 2 failures, merge stderr mutant 1 failure.
- Import facade: one reproduced failure, same-object TASK_CHANNEL_FILE re-export fixes it;
  strict existing import-graph check remains unchanged. Seed/capability literal censuses:
  2 failed/4 passed and 1 failed before; 6 passed and 1 passed respectively in each encoding.

All changed code/fixtures above received independent review. No production guards were relaxed.
Proof copies restored by SHA and deleted by their authors; original logs retained.
Evidence: work/grok-activate and work/grok-activation (including resume-6039).

Final nine-module census: 391 passed in UTF-8 and 391 in cp1251 (utf8_mode=0).
Five changed test files preserve public server.build -> review -> real fake child -> durable
artifact. Production dispatch is refused before spawning on all three platforms. The no-op
review mutant fails with VERIFICATION_FAILED; M0 passes. Independent final review: no findings.
Evidence: work/grok-activation/resume-census. No product edits in this final census.

## Interrupted complete suite

Exact 6039eeb worktree: work/grok-live-check. Full runner started 18:21 MSK; all fourteen
UTF-8 native modules completed, seven ordinary shards were interrupted at about 18:29.
At reconnect 20:40 their recorded PIDs no longer existed and no ordinary JUnit existed.
Some earlier failures were stale expectations listed above. Two later Git-case failures
did not reproduce individually (1 passed in 4.29s; 1 passed in 0.69s); their old cause is
not established. The interrupted run is NOT green and cp1251 did not start.
Evidence: work/grok-activation/run-20261030T152106166187Z; do not overwrite logs or old temp roots.
Next complete run uses two ordinary workers and records/stops at the first failure per shard;
this changes scheduling, never assertions or test timeouts.

Second clean full run (0d781e1) stopped normally at the first failed batch, not by interruption.
UTF-8 native files passed; ordinary shards 0/1/3 passed with 2815/3253/2339 passed tests.
Shard 2: 1258 passed, one failure in test_desk_wizard_roster: its fixture still declared
Grok controls=[dispatch]. Remaining shards and cp1251 were not run. Evidence:
work/grok-activation/run-20261030T175939023227Z. This run is NOT green.
Connected wizard/browser and provider-login fixture migration is scoped by d911f3f/76deac0.
The next exact-commit full run may use four ordinary workers (native files remain serial),
with unchanged assertions/timeouts and fresh temp roots; it is not a retry of this failed SHA.

Wizard/login migration 48a787c: initial red 3 failures, dependent role expectations 5 failures,
browser role expectation 1 failure. All wizard core modules + provider_setup_login:
472 passed in each encoding; browser role scenarios: 22 passed (RU/EN).
Argv-size witnesses now use DeepSeek, Grok is review_only/file and excluded from do/checker;
relay-home witnesses include Grok, Kimi retains the no-relay witness. Independent review clean.
Six files only; non-Grok fixture rows unchanged. Evidence: work/grok-activation/wizard-migration.
Full exact 48a787c starts in work/grok-live-check3, records
work/grok-activation/run-20261030T182108700175Z; no result claimed while running.

## Protected machine

Grok copied from staging into DecemberCommand/harnesses/grok-build/1.0.5/grok.exe.
Size 142651720; SHA256 4b924daa801663ea20e96382408b1f2b5ba39efad62c14d20d88618a9eb0be64.
Authenticode Valid, X.AI LLC, thumbprint C4550B58C79C51C04390FAC323E600A1459186EB.
No Grok process was needed for the copy. DACL owner/SYSTEM/Administrators checked.
Old inventory v1 preserved; v2 adds exactly this file (62 total), SHA256
e8a3d174c84a24e3232ddc18baaed529f2617f5f372dedb6d0a6fad43422ae12.
Preflight v2 + accepted base/product 9788eb9289bb: zero problems, zero notes, 18:21 MSK.

Protected tools are NEW stage_grok2.py and preflight-v2.ps1; old preflight.ps1 unchanged.
Their SHA256: 598f04cd3f08af5cbf271c696737677d008930c4e2a2ac20e985d4fa5827eddb and
b1d5053f931d4ca8b1f5d694ab7392917ac7f36d1bab1d15fd1a49c89e831735.
The first copy sequence stopped when the latter draft's comment changed after review;
no Grok binary had been copied. The inspected comment-only hash was updated and copying
continued without overwriting existing files. Six synthetic inventory cases and overwrite
refusal were checked offline. Evidence: work/grok-activation/machine.

G2 at 18:17 MSK: one known OIDC scope, no unknown fields, 203.2 minutes remaining then,
360-minute token lifetime. All 55 credential-string/input collision counts were zero.
This TTL is historical, not readiness for a later launch. No credential values were logged.

## Final full checks and installed product

Exact 48a787cde881425abee17ff151413b5c29e04c03: all 42 jobs passed, 19,629 passed and
432 skipped in EACH encoding, zero failures/errors. Both mode witnesses and final clean Git
state recorded. results.json SHA256 f0c93a08fd8c55db08634c3d39533bfea1e2ae4a043df16073d43a098fa8a5ce.
These are local Windows checks, not green cross-platform CI or release acceptance.

Protected product installed at DecemberCommand/product/48a787cde881.
Archive SHA256 f3e01ce03dab6f0a73e173b91d58e0778fd8dcaeb7c6046b522c305c0ff1171f;
wheel SHA256 02b8c3212b9ddadb6bfcf1af4a8a33cbf0ff9a6cb66ab20550996f8bc1222a2c;
manifest SHA256 1b0633a51ee560703d416ae1239272c77639883a068b6f10c28b111614b074c9.
Preflight of the new product at 22:15 MSK: 62 harness files, zero problems/notes.
Old installed products preserved. No push.

## Prepared live G6; first missing step

setup-g6.py and prepare-g6.py executed successfully. Fresh DecemberGrokG6 on port7804;
source commit fab5f7558b273423873b420f7877f13d3739d17a; three seed file hashes verified,
AGENT.md canary excluded through public seed API. Run grok-g6-first has one diagnose,
600 seconds, one action; preview created, authorization absent, spent_actions=0.
No model task was launched. Only Codex/Grok configured; Claude is unconfigured and not polled.

Initial live quota: Codex observed/current, 23% remaining at that observation. Grok returned
source_error. Before server start its access token had expired 34.3 minutes earlier;
expiry is proven, but the precise cause of source_error is not established. Server stopped
with Ctrl+C, port7804 free, ownership status closed. Auth values never printed.
Owner asked to use work/grok-activation/login-grok.ps1 for fresh login (pending).
Do not repeat setup-g6.py or prepare-g6.py: the project/workflow/task/run already exist.
After login: inspect safe metadata/readiness, start existing launcher, check fresh quota,
refresh preview and present owner grant in the app. G6 has not passed; no Dalio run exists.
Only a clean successful G6 permits the separate fresh Dalio run. Optional P stays skipped.
The unexecuted prepare-dalio-codex-grok.py requires actual G6 proof and a fresh input check.
At that checkpoint the owner stop was 20%; it is superseded by the update below.

## Fresh login and one-run quota exception, 30 October evening

Owner completed fresh Grok login. Product readiness with a 25-minute horizon passed;
safe metadata showed about 359 minutes remaining. After login quota is observed/current,
but used/remaining percentages are null. One native metadata-only diagnostic at 22:47 MSK
confirmed the percentage field is absent upstream; no model calls. Missing usage stays unknown.

Owner decision committed as 8a1cc2d: permit one G6 despite unknown percentage, one action,
600 seconds, three read-only seed files, subscription, no repeat. This does not authorize
a full Dalio with unknown quota. The separate application grant remains an owner action.
Server restarted on 7804 (PTY 12291), protected preflight 62 files / 0 problems / 0 notes.
Latest public automation read: unconfigured, authorization=null, spent_actions=0.
First missing step is the owner's application grant; no G6 result is claimed.

Owner stop is now 10% remaining; latest Codex observation is 21% remaining.
Kimi Desktop 3.2.23.24 is installed, kimi command absent from PATH; integration is queued,
not established by the presence of Desktop. No Claude polling or model calls were performed.

## First G6 attempt: failed, no retry

Owner entered vasily and granted in the application. At 20:25:07 UTC on 30 October the
effect lease was recorded; execution_observed at 20:25:12.939 UTC recorded failed / exit 1.
Result at 20:25:13 says only: adapter reported failed: the process exited non-zero.
No evidence references or diagnosis artifact. Root cause is not established.

Actual owner grant used the form defaults: one action, 300 seconds per action/node and
300 total reserved seconds, rather than the planned 600. This is an observed deviation;
the failure after about six seconds is not a timeout. spent_task_seconds=300 accounts
for the reservation and is not the measured process duration. No additional attempt.

All three acl/loan/profile journal records are retired; container-attempts is empty.
The original three source file hashes match setup. Server stopped with Ctrl+C;
ownership status returned closed. Saved receipt: work/grok-activation/g6-first-failed-receipt.json.
The graph opened result-gate after the failed step; no human gate decision was made.
G6 is NOT passed and no full Dalio is admitted by this result.

Next: inspect existing evidence and failure handling without another model call.
UX findings to preserve: disabled grant when Your name is empty has no explanation;
the top status said running/no human action while authorization_required; planned bounds
prepared through API do not populate the browser's local form draft.
