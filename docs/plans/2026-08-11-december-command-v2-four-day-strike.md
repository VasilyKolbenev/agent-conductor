# December Command v2 — four-day strike

- **Status:** binding execution plan
- **Owner directive:** 2026-08-11
- **Recovery re-baseline:** 2026-08-13; release-candidate deadline 2026-08-16
- **Base:** `codex/integration-alpha` at `3a31b1f`
- **Target:** a releasable v2 technical preview in 3–4 calendar days
- **Supersedes:** the 14-day calendar in the competitive product direction; the product laws,
  safety boundaries, and wow-path acceptance remain binding

## 1. Outcome

December Command moves from a read-only Harness Control Plane to a safe local command layer.
The strike is complete only when one local project can run the complete path without fake
telemetry or decorative controls:

1. Create or open an Orbit, including a small parallel branch and a Human Gate.
2. Connect configured Claude Code and Codex instances without scanning the machine.
3. Start a run with a stable identity and a frozen configuration digest.
4. Preview and dispatch implementation through the first adapter.
5. Stream observable progress and evidence into the Cockpit.
6. Route a deterministic handoff and independent review to the second adapter.
7. Pause, resume, retry, stop, or switch only when the selected adapter declares support.
8. Stop at the Human Gate; approve, reject, request changes, or waive with an immutable receipt.
9. Replay every proposal, confirmation, attempt, failure, switch, receipt, and verified outcome.
10. Demonstrate the complete path in under ten minutes from a clean installation.

The product remains deterministic around LLMs: the merger never calls a model, an accepted
command is not success, and the Orbit advances only from an observed result receipt.

## 2. Scope that does not move

The four-day target includes:

- run identity, attempts, frozen configuration snapshots, history, restart recovery, and replay;
- structured evidence plus explicit verification state;
- immutable human-decision receipts and Human Gate lifecycle;
- adapter SDK plus deep Claude Code and Codex adapters;
- capability-limited Gemini CLI and OpenCode adapters when their public interfaces support it;
- Cockpit message, dispatch, review, pause/resume/retry/stop, switch, and handoff controls;
- Observe, Propose, Confirm, and narrow Policy modes;
- a minimal source-preserving Orbit editor with stages, edges, assignments, gates, and one
  parallel branch;
- bounded proactive proposals and policy-authorized non-destructive actions;
- browser-level command-path tests, threat model, package smoke, and replayable demo;
- a prepared public rename patch for December Command.

Public distribution/repository renaming is conditional on trademark, domain, GitHub, and PyPI
clearance. Until those external facts are confirmed, brand copy may say December Command while
the distribution remains `agent-conductor` and the CLI remains `conduct`.

## 3. Safety laws

1. No adapter command is an unrestricted shell string. Requests carry a declared capability,
   structured arguments, working-directory scope, timeout, and idempotency key.
2. December may stop only a process it started and recorded; it never kills an arbitrary PID.
3. The browser cannot write agent-owned lane, event, prompt, or source files. Its writable
   surface is validated Command requests, Human receipts, and explicitly confirmed design edits.
4. Every browser mutation requires same-origin validation and a per-process anti-CSRF token.
5. Observe is the default. Confirm requires a fresh explicit confirmation. Policy executes only
   allow-listed non-destructive action classes within declared concurrency, time, and scope.
6. Policy never authorizes permission expansion, gate weakening, arbitrary commands, destructive
   filesystem operations, model/harness switching, or Human decisions.
7. No machine probing. Adapter executable paths and connection details are user configuration.
8. Secrets may be referenced by environment-variable name but are never written to project state,
   receipts, events, reports, or browser responses.
9. Requests and results are separate append-only records. `accepted`, `started`, `succeeded`,
   `failed`, `cancelled`, `unknown`, and `verification_failed` never collapse into one boolean.
10. Unsupported capability means the control is absent. A disabled decorative control fails
    acceptance.

## 4. Architecture seams

New runtime code lives under `conductor.command`; Protocol v1 and its merger stay compatible.

```text
src/conductor/command/
  contracts.py       # validated v2 envelopes and tolerant readers
  run_store.py       # append-only runs, attempts, actions, receipts, recovery
  policy.py          # Observe/Propose/Confirm/Policy authorization
  runtime.py         # prepare -> authorize -> execute -> verify state machine
  adapters/
    base.py           # capability manifest and adapter protocol
    process.py        # safe owned-process runner
    claude_code.py
    codex.py
    gemini_cli.py
    opencode.py
```

Committed design remains under `conductor/cycles/` and `conductor/harnesses/`. Runtime state is
project-local and single-writer under `conductor/runs/`; every record carries `schema_version = 2`.
Writes use create-nearby, flush, fsync, and atomic replace where replacement is allowed. Append-only
receipts use exclusive creation and superseding references instead of overwrite.

The existing panel stays a single no-build HTML asset. Command endpoints are loopback-only and
live outside the pure merge path. `state.json` additions are additive; v1 consumers keep working.

## 5. Four delivery lanes

- **A — contracts/runtime:** ADRs, contracts, run store, recovery, authorization, receipts.
- **B — adapters:** SDK, owned-process runner, Claude Code, Codex, limited Gemini/OpenCode.
- **C — Cockpit:** controls, stream, history, Human Gate, Orbit editor, browser tests.
- **D — assurance/release:** threat model, sabotage, packaging, docs, demo, daily integration.

Each lane owns disjoint files and branches from the recorded integration SHA. Integration happens
at least twice daily. Every isolated test prints the imported source root; editable `.pth` is never
trusted as proof of provenance.

## 6. Calendar

### Day 1 — contracts before commands

- Accept the five architecture decisions: run identity/store, action protocol, narrow panel writes
  and Human receipts, evidence verification, and policy effects.
- Implement validated contract objects and tolerant JSON readers.
- Implement the adapter protocol and capability manifests.
- Implement append-only run/receipt storage with restart recovery tests.
- Land Observe and Propose without executing a process.
- Produce a CLI-only preview: create run -> propose dispatch -> inspect exact request.

**Day-1 gate:** no process starts, yet every later mutation already has an id, scope, permission,
idempotency key, frozen configuration digest, and place for a result receipt.

### Day 2 — two real adapters and Confirm

- Implement the owned-process runner and deep Claude Code/Codex adapters.
- Add dispatch, output streaming, status/evidence request, stop, retry, and supported pause/resume.
- Add Confirm authorization and post-action verification.
- Add attempts, restart recovery, and Harness switching as a superseding attempt.
- Add CLI end-to-end tests using deterministic fake executables plus opt-in real-adapter smoke.

**Day-2 gate:** both deep adapters complete prepare -> confirm -> execute -> verify -> receipt;
failure, timeout, duplicate request, restart, and stop are independently sabotaged.

### Day 3 — Cockpit, Human Gate, editor, Policy

- Add authenticated same-origin Command endpoints and SSE run events.
- Add capability-driven controls; unsupported actions are absent.
- Add run history/replay, verified evidence, immutable Human Gate receipts, and switch flow.
- Add the minimal Orbit editor with source preview, validation, diff, confirmation, and atomic write.
- Add a parallel branch executor with bounded concurrency.
- Add narrow Policy allow-lists for dispatch, review, retry, and notification only.
- Add bounded proactive proposals for ready work, independent review, stale retry, and Human Gates.

**Feature freeze at Day 3 end.** Anything missing after the freeze is either a wow-path blocker or
is cut visibly; no new capability enters on Day 4.

### Day 4 — hostile review and release

- Run command-injection, CSRF, path-escape, duplicate-idempotency, stale-confirmation, PID-ownership,
  receipt-tamper, restart, disconnect, and verification-failure sabotage.
- Run the complete browser wow path with two harness adapters and a parallel Orbit.
- Run Windows/Linux tests, mutation harness, browser suite, clean wheel, and release smoke on one
  frozen revision.
- Record the under-ten-minute demo, finish English quickstart and threat model.
- Prepare rename patch; apply it only if all external clearance checks are affirmative.
- Tag the technical preview only after every blocker gate is green.

## 7. Control modes

| Mode | December may do |
|---|---|
| Observe | Read state and adapter health; never prepare or execute. |
| Propose | Build an exact preview and explain why; never execute. |
| Confirm | Execute one unchanged preview after a fresh Human confirmation. |
| Policy | Execute an allow-listed non-destructive action inside explicit limits. |

A changed request invalidates confirmation. A retry receives a new action id and attempt id while
retaining the original causal link. A switch never moves a live process invisibly: the old attempt
is stopped or marked unresolved, then a new compatible instance receives a new handoff.

## 8. Cut order if the clock slips

Safety and truth are not cut. Breadth is cut in this order:

1. Gemini CLI and OpenCode execution narrow to capability manifests plus Observe.
2. Orbit editor loses drag-and-drop polish but keeps form/source preview, validation, and parallel
   graph support.
3. Policy ships with dispatch/review only; retry and notification remain Confirm.
4. Pause/resume disappear for adapters that cannot prove them; stop/retry remain.
5. Public rename waits for clearance while December Command brand copy remains.

Never cut receipts, verification, confirmation freshness, process ownership, restart recovery,
Human Gate truth, or the two-adapter wow path.

## 9. Release acceptance

- Complete wow path under ten minutes from a clean wheel.
- Claude Code and Codex complete real or explicitly opted-in adapter smoke on the release machine.
- Every action has request and result receipts; every Human Gate transition has a decision receipt.
- History explains failed, cancelled, retried, switched, superseded, and verified attempts.
- Policy sabotage cannot escape its capability, project root, concurrency, time, or action budget.
- Browser controls match capabilities and remain usable without reading Protocol documentation.
- No v1 fixture or command changes output unless an additive v2 field is explicitly requested.
- Frozen-HEAD CLI, browser, mutation, package, threat, and clean-tree gates are all green.

## 10. Immediate first slice

`CMD-1` implements the contract layer only: run envelope, evidence reference, action request,
action result receipt, Human decision receipt, control mode, validation, canonical serialization,
and forward-compatible reading. It starts no process, writes no file, and changes no v1 output.
Its tests must prove malformed ids/timestamps/scopes are rejected, unknown fields survive a
round-trip, accepted is distinct from succeeded, and a Human Gate cannot become satisfied without
a valid decision receipt.

## 11. Execution ledger

- **CMD-1 — Complete 2026-08-11.** Validated Run, Action, Result, Evidence and Human Decision
  contracts; canonical serialization; forward-compatible readers; no execution surface.
- **CMD-2 — Complete 2026-08-11.** Project-local Run Store with exclusive creation, a frozen
  configuration screened against a named list of secret-bearing key names (a screen, not a
  proof of absence), canonical append-only replay, idempotency conflicts, causal
  Action-to-Result validation, immutable Human Decision files published all-or-nothing, a
  non-mutating reader beside the writer's repair path, and crash-tail recovery. It starts
  no process and changes no Protocol v1 output.
- **CMD-3 — Complete 2026-08-11.** Explicit non-probing Adapter registry; immutable capability
  manifests; validated observations, preparations and verification results; four protocol seams;
  unsupported controls stay absent and no registry execution method exists.
- **CMD-4 — Complete 2026-08-13 at `63d261a`.** Persisted Proposals and the
  Observe/Propose service. All three Codex REQUEST-CHANGES MAJORs are closed: (1) the instance ->
  adapter binding is derived from the pinned frozen config, never trusted from the caller, so
  an unknown instance, an adapter mismatch, and capability laundering through a foreign
  manifest are all refused before any adapter seam and before any append, on observe and
  propose alike — the proposal's adapter is derived unambiguously and verifiably from the
  frozen config it already digests, so no new durable field and no Protocol change were
  needed; (2) a Day-1 CLI-only gate, `conduct preview`, drives the fixed service end to end
  (create/open a run with a frozen config, propose one dispatch, print the canonical preview
  with its preview_digest) and prepares, executes and spawns nothing; (3) the preview's run id
  is fixed, so it can find a run it never created — the existing run is now replayed read-only
  and held against the module's frozen envelope and configuration, and against the history the
  preview itself would have written, before any append; one that disagrees on any point is
  refused with exit 1, an empty stdout and its append-only history byte for byte untouched.
  That third is the same class as the first: check the state you found against the frozen
  identity, never work from it. Internal review of d25ea05 then closed four more: the refusal
  tests now pin which side of each difference is whose rather than that both words appear; a
  pair of unreachable, coupled envelope-equality lines the docstring called the authority are
  gone, leaving the sentinel walk as the authority it always was; `preview._shown` is renamed
  away from `doctor._shown`'s opposite guarantee; and the found run's recorded history — the
  journal and `decisions/` alike — is the check named above, which was the last piece of found
  state nothing held. A second internal review found that round's new authority well guarded
  from the outside but one of its two branches held by nothing: the empty history — the run
  this preview created and then died before appending into, which the store is built to
  survive — so deleting that branch turned a recoverable run into a permanent refusal at a
  fixed id with the whole suite still green. It is now a resumption test. Two minors came back
  with it as regressions: the refusal's differences stand one per line, on a boundary `repr`
  cannot produce, because a found field's value could otherwise synthesize a difference entry
  the preview never named for any structured reader of stderr; and a stored `absent` joins the
  values proved distinct from the bare word the refusal speaks for a field that is missing. A
  run carrying the preview's own proposal id over other facts is refused by the store's
  immutability, and now says so under test rather than by accident. The preview's tests live in
  `tests/test_command_preview.py`, split out whole when those regressions took test_cli.py past
  800 lines. Codex's re-review of 7f30176 then found a fourth MAJOR, MAJOR-B, in that very
  history check: `RunStore.read` replays read-only, so a journal ending mid-record leaves those
  bytes on disk and reports them as a WARNING rather than as a record — and a check reading only
  the replayed records saw a permitted, empty history in a run that still carried unjudged bytes.
  `propose` then appended through the repairing store, which truncated the tail away: exit 0, a
  proposal printed, and durable bytes the preview never wrote silently gone. Any warning from the
  read-only replay is now a disagreement in its own right, named before one byte is appended, so
  no incomplete tail is adopted as the preview's own — not even one that is a byte prefix of the
  record the preview would itself have written. The alternative, proving such a tail a prefix of
  that exact canonical record, was declined: the preview executes nothing, so surviving a crash
  inside its own append is not a requirement it has, and a tail is evidence of what some writer
  intended, never of which writer it was. The price is stated rather than hidden, in the module
  docstring and in the refusal itself: a run left with a ragged tail will never open in this
  preview again, and a human must move or delete its run directory by hand. Codex's re-review of
  that fix found the shipped refusal unbreakable and its evidence short in four places, all closed.
  The immutability guard every refusal leans on — widened from a digest of `records.jsonl` to a
  snapshot of every durable file — was inert: narrowing it back left the whole preview suite
  green, because no production path here leaks a `.tmp` or edits a receipt, and the one staging
  artifact this command can leak is minted at `conductor/runs/.preview-run.<rand>/`, one level
  ABOVE the run directory the snapshot was rooted at. It is now rooted at `conductor/runs`, and a
  test plants a file at each path its docstring names and requires the snapshot to report it. The
  same review's second door is closed in production rather than in prose: `RunStore.read` opens
  four names, so a `.records.jsonl.<rand>.tmp` — the residue of a writer that died inside its own
  publish — replayed as a flawless, warning-free history and was ADOPTED, exit 0 and the proposal
  appended. Any file under the run directory the store does not own now refuses it on the same
  ground a tail does. Two guards that broke silently under review are permanent tests: the
  refusal's remedy sentence, which is the whole mitigation for the price above and could be
  deleted or blurred off the run's full path with everything green, is now held by a test that
  takes the path from the store and carries the remedy out — delete that directory, rerun, and
  the journal comes back byte for byte a genuine one; and a replay reporting TWO warnings, which
  no fixture produced, so naming only the first was green. One false universal in the prose was
  narrowed: not every warning names bytes the replay left out of what it returned, because an
  orphan `decisions/` receipt is replayed into the records. Carried with them, a pre-existing
  durability defect the same argument rests on: `_append_bytes` opened the journal without
  `O_BINARY`, so on Windows the CRT turned every LF into CRLF and the durable line was one CR
  longer than the bytes the store composed, while `run.json`, `config.json` and every receipt,
  staged through `mkstemp`, were not — two durable spellings of one record, and a run directory
  not byte-identical between platforms. A third review then found the price itself misstated for
  half the runs that pay it. Docstring and refusal both said a ragged tail OR a file the store
  does not own can never be opened again, so delete the run directory — and for the second half
  that was false twice over: removing the one named file returned the run immediately, journal
  byte for byte, so the advice destroyed legitimate proposal records where lifting out one blob
  was enough. It is also the reachable half: an editor swap file, `Thumbs.db`, `.DS_Store`, an
  antivirus artifact, against a crash inside an append that writes one record. The refusal now
  ends in exactly one remedy chosen by the owner's taxonomy — name the object and offer to move
  or delete only it when the run beneath is whole; offer the whole preview run only when the
  replay itself disagrees, which is where a foreign envelope, a foreign frozen config, a foreign
  history and a ragged tail all sit, since this module repairs no journal — and neither branch
  promises a repair, because rerunning either untouched refuses again. Assembling that remedy in
  `_run_differences` closed a second gap in the same breath: it used to be printed out of the
  unjudged-bytes check, so a run refused purely on its envelope was told neither where it stood
  nor what to do. Moving is now offered beside deleting on both roads; a human is not asked to
  destroy bytes to get moving. `_unowned_files` filtered on `Path.is_file`, which answers False
  for a dangling link and for a link to a directory, so the taxonomy's "a stray file or a link"
  held only for files — the walk now skips real directories instead, and an empty directory is
  still adopted, having no bytes to judge. Held by regressions that execute both roads end to
  end and carry each remedy out. Three limits stay open and are stated, not hinted away: staging
  residue at `conductor/runs/.preview-run.<rand>/` lies outside the directory that is checked, an
  empty directory inside the run is adopted, and an NTFS alternate data stream is not detected —
  nor is it modified, since the preview's own path only appends to the journal and never runs the
  repairing replace. Carried with them, a compatibility guard that had none: journals written
  before `O_BINARY` end their records CR LF, and they replay today only because
  `bytes.splitlines()` eats the CR. Both halves are now held — such a journal replays to the same
  records without warnings, and appending the same record is recognised as the retry it is, so
  the old spelling is never half-rewritten. Execution remains disabled until the owned-process
  runner and Confirm authorization are green. Not marked Complete: external APPROVE from Codex is
  not yet given.
- **CMD-4 round 4 — owner decision 2026-08-12: the remediation contract is narrowed.** This
  supersedes the round-3 two-road remedy taxonomy recorded above, which stays as what WAS.
  Refusals no longer classify a run into locally-fixable and irresolvable, compute no minimal
  deletion set, and give no advice to move or delete a file, a receipt, or the whole run —
  accuracy over pseudo-actionability, because naming the wrong object to destroy is worse than
  naming none. Every refusal that declines a run directory the preview found or failed to read,
  and every store-level creation failure, now holds six points by execution: exit 1; an empty
  stdout; the run tree byte for byte and structurally unchanged, links included; stderr naming
  what was reliably detected, the exact preview-run path and the exact paths of foreign objects
  where they are reliably established, and stating in so many words that the preview changed
  nothing in the run directory; no remediation promise and no destructive command; and, where
  StoreError/CorruptRun prevents establishing what a local object is, the stated limit — no safe
  automatic remediation is defined; preserve the run and investigate it separately. Closed with
  it, each established by execution first: an NTFS junction inside the run answered `is_dir()`
  True and `is_symlink()` False and `rglob` recursed straight through it, so an empty-target
  junction was silently ADOPTED — exit 0, proposal appended — and a populated one was named by
  paths that lie outside the run; the walk now names a symlink or junction by its own exact path
  and never steps through one, on the junction's reparse tag, which needs no privilege to plant.
  A FILE standing at the run's own path was reported as "run 'preview-run' does not exist" — the
  exact opposite of the truth — and a FILE at `conductor/runs` was an uncaught traceback; both
  are contract refusals now, and StoreError/CorruptRun raised by `store.read` inside the
  RunExists branch no longer bypasses the contract facts through the module-level catch. The
  message circuit lives in `tests/test_command_preview_refusal_contract.py` — self-contained,
  its immutability snapshot a test-local walk over bytes, structure and link targets, its
  expected paths computed from the fixture root, never from the production function under test —
  and the old remedy-text tests were reworked into behavioral regressions of the system property
  the advice traded on: out-of-band removal of exactly the foreign object, or of the whole run,
  still reopens or recreates it with every surviving record intact. The service-level refusal
  road (unknown instance / adapter mismatch after a fresh creation) keeps its own words and
  carries no changed-nothing claim, which belongs only where it is byte-for-byte true. Status
  unchanged: external APPROVE from Codex is not yet given.
- **CMD-4 ownership-boundary round — owner request changes 2026-08-13.** The internal double
  APPROVE is withdrawn: the owner personally reproduced LIVE defects of found state on the
  exact committed SHA, behavioral, not prose — while confirming alongside that the v1 pin
  matched, the v1 core sat outside the diff, the mutation gate stood 15/15 at baseline 104,
  and e0ec984 was justified and minimal; the blocker was solely the preview's ownership
  boundary. MAJOR-1: `_points_elsewhere` was applied only to objects INSIDE the run and never
  to the route that reaches it, so a directory symlink or an NTFS junction standing AT
  `conductor/runs/preview-run` was followed, the valid run behind it adopted as the preview's
  own, and the proposal appended into the EXTERNAL journal — exit 0, stderr empty, the
  external records.jsonl grown 0 to 609 bytes, reproduced with both portal kinds. MAJOR-2:
  `records.jsonl` replaced by a hard link to an empty file outside the run laundered the
  append through the permitted name — samefile True, st_nlink 2, exit 0, the external file
  grown 0 to 609 bytes — falsifying the module's claim that a found run is checked before
  append and that foreign state is never modified. Same class one level up: with
  `conductor/runs` itself a portal, a fresh run was created and filled outside the project
  with exit 0. Closed with ONE containment mechanism rather than name-by-name exceptions, in
  `preview.py` alone — `run_store.py` stays outside the diff as in every previous round:
  before any durable action on either road, every component of the writable route is read
  with `os.lstat` alone, following nothing — `conductor`, `runs`, the run directory,
  `decisions`, and every store-owned file present (`run.json`, `config.json`,
  `records.jsonl`, each `decisions/*.json`). A component that is a symlink, junction or any
  other reparse point, and an owned file that is not a regular file with exactly one hard
  link, refuses the preview before `create_run` and before the found run is even replayed,
  under the same narrowed contract: exit 1, empty stdout, the detected fact and the exact
  paths on stderr, the changed-nothing statement scoped to the run directory, no advice.
  Every owner scenario was first reproduced as a born-red regression on the committed SHA —
  red precisely because the command exited 0 there — in
  `tests/test_command_preview_route_containment.py`, self-contained, asserting BOTH sides
  each time: the refusal, and byte-for-byte inertness of the found state AND of the external
  target, via test-local snapshots that record a portal by its own target and never step
  through it. The same door is proven one and two levels up (junction and symlink at
  `conductor` and at `conductor/runs`), across `run.json` and a `decisions/*.json` receipt
  hard-linked outward, and at a symlinked `decisions` directory — the gate now speaks before
  the store reads through any of them. The relational changed-nothing driver gained the
  run-boundary portal as its seventh road. Residual R1 closed in the same breath,
  coordinator-authorized: the module docstring's umbrella clause "exits 1 with an empty
  stdout and changes nothing" is narrowed to the run-directory scope every road is measured
  at, and the boundary paragraphs now state the mechanism instead of the claim MAJOR-2
  falsified. Three limits stay open and are stated in the module docstring, not hinted away:
  the gate is check-then-act, so a local process swapping a component between the check and
  the append is not stopped; an NTFS alternate data stream is not a component of any path the
  walk reads and goes undetected; and a failed creation may still leave parent directories or
  staging residue above the run directory. Merge, push, and the runner/Confirm surface stay
  blocked; the two review stages run again on the new SHA.
- **CMD-4 final gate — external APPROVE 2026-08-13 at `63d261a`.** The final tests-and-prose
  delta pins the generic reparse-tag detector and the irregular-owned-file route arm; both named
  removals fail their own permanent regression. Its only production-file edits are docstrings,
  and the docstring-stripped `preview.py` AST is identical to `f172bb6`; `merge.py` is the same
  blob. Two internal reviews and the external delta review approved the exact SHA. The external
  targeted gate passed 79 tests and the full gate passed 2044 with 4 platform skips. CMD-4 is
  Complete; runner/Confirm may now consume its frozen boundary.

## 12. Four-day recovery schedule — binding from 2026-08-13

This section supersedes the sequencing in section 6 where the dates conflict. It does not relax
the outcome, safety laws, cut order, or release acceptance above. The elapsed first two days were
spent hardening the Day-1 boundary; the recovery schedule earns that time back through parallel
work on disjoint files, smaller vertical slices, and one frozen integration decision per slice.
Correctness, security, receipts, verification, and release evidence are not schedule variables.

### 12.1 Scope freeze and completion accounting

At this re-baseline, CMD-1 through CMD-4 are Complete; the final external approval is `63d261a`.
The reusable v0.1.0 alpha already supplies the read-only panel, SSE foundation, report, doctor,
packaging baseline, rendered-browser job, mutation isolation, and release-smoke procedure. This is
roughly 30% of the v2 technical preview by acceptance surface: the safe read/propose foundation
exists, while the execution runtime, deep adapters, writable Cockpit, Human Gate, Policy, editor,
parallel wow path, and frozen release gates remain.

The following breadth reductions are applied now, using section 8's approved cut order. They are
scope choices, not quality waivers:

1. Gemini CLI and OpenCode ship as explicit manifests plus Observe only. They do not execute.
2. The Orbit editor is form/source based: preview, validation, diff, confirmation, atomic write,
   stages, edges, assignments, gates, and one parallel branch. Drag-and-drop polish is excluded.
3. Policy authorizes dispatch and independent review only. Retry and notification stay Confirm.
4. Pause/resume is present only where an adapter proves it. Stop and retry remain mandatory.
5. The public distribution/repository rename is not applied without all external clearances.

No further capability enters before the release candidate. Marketplace/gallery work, remote
multi-user operation, billing, mobile-specific polish, and broad adapter parity are post-preview.

### 12.2 Parallel lanes and dependency rule

The four lanes work in separate worktrees with disjoint primary ownership. A lane may branch and
commit against `f172bb6` immediately to save elapsed time, but no Day-2 code integrates until the
CMD-4 micro-delta has two approvals on one exact committed SHA.

- **A — runtime:** owns `policy.py`, `runtime.py`, authorization freshness, attempts, receipts,
  and recovery. Contracts and fake-adapter tests may start before CMD-4 integrates.
- **B — adapters:** owns `adapters/process.py`, Claude Code, Codex, and Observe-only
  Gemini/OpenCode. The owned runner and deterministic fake executables may start immediately.
- **C — Cockpit:** owns command HTTP endpoints, CSRF, run SSE/history, capability controls,
  Human Gate, and editor. Its API/UI shell may start now, but execution wiring waits for CMD-4.
- **D — assurance:** owns the threat matrix, sabotage fixtures, browser path, package, demo, and
  docs. Tests and fixtures against frozen interfaces may start immediately.

The hard dependency is deliberately short:

```text
CMD-4 approved
  -> Confirm freshness + owned runner
  -> execute/verify receipts + Claude/Codex adapters
  -> authenticated Cockpit + Human Gate/history
  -> Policy + parallel wow path
  -> frozen release candidate
```

Runner, Cockpit shell, threat fixtures, and adapter argument builders proceed in parallel around
that chain. They merge only when the upstream contract they consume is frozen and green.

### 12.3 Day 1 — close the boundary and reach one fake executable

Deadline: 2026-08-13 end of day.

- **CMD4-R8-CLOSE — Complete at `63d261a`:** the generic-reparse relation test, the
  irregular-owned-file planting test, and the two scoped prose corrections passed two internal
  reviews and the external gate. Production behavior is unchanged. The boundary is available to
  runner/Confirm after this plan-only recovery record is committed.
- **ALPHA-DEBT-1:** integrate the already double-approved REPORT-GUARD-1 branch at `5f69207`
  after a compact rebase/provenance gate. It changes report guards and plan history, not product
  behavior. The tracked HCP specification and completed DO-7 gates are reused, not reimplemented.
- **A/CONF-1:** authorize one unchanged proposal by its canonical preview digest, a fresh Human
  confirmation, mode, scope, capability, action/time budgets, and frozen config. Any changed or
  stale fact refuses before preparation. Record the confirmation separately from result.
- **A/RT-1:** implement the minimal `prepare -> authorize -> execute -> verify -> result receipt`
  state machine against a fake adapter. Accepted, started, succeeded, failed, cancelled, unknown,
  and verification_failed remain distinct.
- **B/RUN-1:** implement the owned-process runner with structured argv, explicit cwd beneath the
  project root, sanitized environment references, timeout, bounded capture/streaming, and an
  ownership token. It may stop only the exact child/process group it started and recorded.
- **C/API-0 and D/THREAT-0:** freeze endpoint schemas, same-origin/CSRF fixtures, and the attack
  matrix early so runtime and UI do not invent incompatible command shapes later.

Day-1 recovery gate: one deterministic fake executable completes propose -> confirm -> execute ->
verify -> immutable receipt from CLI; stale confirmation, changed digest, path escape, arbitrary
shell text, timeout, duplicate idempotency, and foreign PID are independently red under sabotage.
All existing v1 and CMD-1..4 regressions stay green.

- **A/CONF-1 + A/RT-1 — landed on `track/v2a-runtime` (lane A Day-1).** New
  `src/conductor/command/runtime.py` is the Confirm state machine over the frozen CMD-1..3
  surfaces: it edits none of them and adds no store record type — every durable fact is one of
  the six the store already knows. `ControlRuntime.authorize` holds a fresh Human `Confirmation`
  against the run's own durable proposal — canonical preview digest, scope, capability, frozen
  config — plus freshness and the action/time budgets, and refuses ANY changed or stale fact
  before preparation and before one byte is written; a clean confirmation mints and appends the
  `ActionRequest` that records the confirmation as its own store record (the confirming human,
  the freshness instant, the confirmed digest), separate from any result and guarded by the
  store's RecordConflict/idempotency (CMD-2). `ControlRuntime.execute` drives the authorized
  request prepare -> execute -> verify -> one immutable result receipt, keeping accepted,
  started, succeeded, failed, cancelled, unknown, and verification_failed distinct: a crashed,
  empty, or foreign result is unknown, never success; a reported success reaches succeeded only
  through an explicit `verified` verification, with mismatch/error -> verification_failed and
  unavailable -> success left explicitly unverified. The runtime is adapter-agnostic — it
  resolves the adapter from the frozen-config binding, never a caller's word — and its source
  imports no process or machine door. The four owned sabotage classes each ship a permanent
  regression born of an executed red (the guard was disabled, the test observed red, then
  reverted): stale confirmation refused, changed preview digest refused, duplicate idempotency
  refused with no second durable effect, and a crashed/lost attempt never read as success. Path
  escape, shell text, timeout and foreign PID were left to lane B. A deferred CLI verb
  `conduct confirm` (`src/conductor/command/control_loop.py`) runs the whole loop against an
  in-process fake adapter and prints the immutable result receipt; README and the release smoke
  name it and the exact usage-line guard matches; the machine-probing ban stays green because
  the import is deferred. Tests: `tests/test_command_runtime_authorize.py`,
  `tests/test_command_runtime_execute.py`, `tests/test_command_control_loop.py`. Targeted gate
  76 passed; full suite 2087 passed, 4 platform skips. Policy (Day-3), attempt persistence,
  restart recovery and switch (Day-2) are not built here.
- **A/CONF-1 + A/RT-1 fix batch (F1) — landed on `track/v2a-runtime`.** The combined
  spec+quality review found one blocking MAJOR, F1, a false-public-claim confined to the
  foreign-run refusal test in `tests/test_command_control_loop.py`: its comment claimed the
  gate "refuses it rather than appending into it," which execution disproves. Reproduced on
  the exact SHA, seeding a run at the fixed id `control-loop-run` under a different valid
  frozen config and running `conduct confirm` once grows the foreign
  `runs/control-loop-run/records.jsonl` from 0 to 634 bytes with one `action_proposal`:
  `propose` derives the proposal's `config_digest` from the FOUND run's envelope and the store
  accepts it, then `authorize` refuses at the config-digest check. The production contract was
  already honest -- `control_loop.py` discloses "an honest refusal, not preview's proven
  inertness" -- and `authorize` appends nothing itself, so the defect was the test's comment
  plus the before/after state assertion the evidence rule mandates for a refusing path. Fixed
  by correcting the comment to the module's honest contract and adding the assertion: before,
  the run holds no records; after the refusal, exactly one `action_proposal` stands -- no
  `action_request` (no confirmation recorded), no evidence, no `action_result`. That assertion
  is a real regression door: with the `authorize` config-digest guard neutered the loop
  confirms, executes, and appends all four records into the foreign run, and it goes red.
  Production code is byte-for-byte unchanged; only the one test file was edited. Targeted lane-A
  gate 43 passed; full suite green.
- **B/RUN-1 — owned-process runner and thin process adapter, committed.** New additive modules
  `adapters/process.py` (the `ProcessRunner`, its `CommandSpec`/`OwnedProcess`/`ProcessOutcome`
  value types, and the thin `ProcessAdapter`) and `adapters/_procgroup.py` (POSIX session /
  Windows kill-on-close Job Object group termination). No frozen surface changed; the adapters
  `__init__`/`base` are untouched and callers import from `conductor.command.adapters.process`.
  The runner enforces each safety rule as a relation the child witnesses: structured argv only
  (a shell string is refused; `shell=False`); cwd strictly beneath the resolved root, proven by an
  `os.lstat` route walk that follows nothing and refuses a symlink/junction/reparse-point/`..`/
  outside/root-itself/non-directory BEFORE spawn (the CMD-4 route-covers-the-container lesson,
  reusing preview's portal idiom); a sanitized environment built from an explicit allowlist plus
  literal extras, never the parent wholesale; bounded capture (merged stdout+stderr) truncated at a
  stated byte bound by a pump that keeps draining so the parent cannot be exhausted; timeout as its
  own `timed_out` fact, never `completed`/success/silent; and an ownership token minted per start
  where `stop` terminates only a live token's child/group and there is no PID-killing method at all.
  The thin `ProcessAdapter` implements the frozen CMD-3 seams over the runner: `dispatch` +
  `observe` are the only declared capabilities (pause/resume/stop/retry/switch/review/evidence/
  notify/message are absent, not stubbed); `observe` reports `unknown` without probing; `execute`
  maps completed-zero->succeeded, completed-nonzero->failed, timeout->failed (never succeeded),
  stopped->cancelled; `verify` returns `unavailable`, never `verified`, because watching a process
  exit is not evidence of the requested effect. Deterministic fake executables live in
  `tests/_fakeproc.py` (driven via `sys.executable` + script path with env knobs: output size, exit
  code, sleep, heartbeat, grandchild spawn, argv/env/cwd dumps; no installed tool relied on).
  The four owned sabotage classes each ship a permanent regression proven born-red by mutation on
  this tree: shell text/injection (a space-free `&`-chain reaches the child as one inert token and
  no file is created; `shell=True` reds both witnesses), cwd + argv-target path escape (a portal on
  the route refuses before spawn; neutering the portal detector reds all route cases), timeout
  (mislabelling it `completed` reds), and foreign PID (accepting an unminted or finished token
  reds). Each rule also carries positive, refusing, and before/after assertions; test helpers take
  their witness (the child's own pid/ppid, os.environ, heartbeat) independently of the runner.
  The execution surface the CMD-1..4 door guards forbade is now confined, not banned: those guards
  (`test_command_package_doors.py`, and the SDK import guard in `test_command_adapters.py`) are
  renamed to their true claim and exempt exactly the two runner modules, with a new
  `test_the_execution_door_is_confined_to_the_owned_process_runner` proving the door has not spread
  and the runner still holds it. Stated limits, not hidden: the containment gate is check-then-act
  (a local component swap between lstat and spawn is not stopped) and an NTFS alternate data stream
  is neither detected nor traversed; on this machine the venv `python.exe` is a re-exec launcher, so
  the recorded pid is the child or its launcher parent, both self-reported by the child. NOT in this
  slice and left to lane A / the coordinator: Confirm authorization and the CLI propose -> confirm ->
  execute -> verify -> receipt gate wiring (which the adapter is built to be wired into after lanes
  A and B merge); stale confirmation / changed digest / duplicate idempotency belong to lane A's
  store/confirm surface and are not faked here. Targeted process suite 88 passed; full suite
  2087 passed, 4 skipped (0:02:09) with the three former no-execution-door guards updated in
  lockstep and one confinement guard added.

- **Day-1 A+B integration and hardening — integrated on `codex/v2-day1-integration`.**
  Lane A and B meet at one explicitly synthetic CLI gate: `conduct integration-smoke` proposes
  a fixed structured no-op, records deterministic fixture authorization facts, executes through
  `ProcessAdapter`/`ProcessRunner`, reports verification honestly unavailable, and persists one
  immutable result. It is not a product Human Confirm surface; that explicit action and its
  server-owned time/identity arrive with C/API-1. A shared command-layer containment engine holds
  preview, direct `ControlRuntime` entry, and runner cwd routes before replay, prepare, every
  durable append, and spawn; it refuses symlink, junction, any reparse point, irregular owned
  files and hard-link aliases. A found control-loop run is checked read-only against
  contract-derived envelope/config/history prefixes before proposal append. Execution holds the
  complete durable
  `ActionRequest`, reconstructs private canonical values at each untrusted adapter seam, consumes
  a memory-only one-shot grant before prepare, suppresses an exact terminal replay, and treats a
  request-without-result as ambiguous instead of retrying it across a crash or restart. Returned
  requests execute only when the durable Run envelope itself remains in Confirm mode; authorize
  and execute hold that authority independently before append, replay, or any adapter seam.
  Returned observation/result/verification identities are reconstructed and held against the
  frozen binding; arbitrary adapter prose is never persisted. Day-1 cannot causally bind
  post-action evidence without a durable
  `execution_observed` fact, so every `verified` response remains `verification_failed` and every
  terminal receipt with evidence refs is refused on replay; verified success belongs to A/RT-2.
  Adapter failures persist only runtime-owned phase classifications; exception type names and
  messages are both untrusted and never durable. Public process dispatch
  persists only structured argv/cwd/output bound and environment variable names; literal env
  values refuse before proposal append. The Windows child starts suspended and is assigned to a
  configured kill-on-close Job before resume; every post-Popen construction failure uses bounded
  kill/wait/close cleanup, and descendant groups are retired before output-pipe join. Accepted
  limits stay explicit: structural checks are check-then-act rather than an OS sandbox, NTFS ADS
  is not inspected, and operator `--dir` defines a resolved authority root. Day-2 still owns
  crash-safe attempt persistence/reconciliation beyond the current fail-closed ambiguous state.

### 12.4 Day 2 — two deep adapters and the writable Cockpit

Deadline: 2026-08-14 end of day.

- **B/CC-1 and B/CX-1:** Claude Code and Codex each implement manifest, prepare, dispatch,
  observable progress, evidence/status request, stop, retry, and verify. Deterministic fake
  executables are mandatory; real-adapter smoke is opt-in and never replaces them.
- **B/BREADTH-1:** Gemini CLI and OpenCode receive honest manifests and Observe only. No command
  endpoint or control claims execution, pause, resume, stop, or verification for them.
- **A/RT-2:** persist attempts and output/evidence/result receipts; recover after restart without
  converting unknown execution into success; retry receives new action/attempt ids with causal
  links; switch supersedes an attempt only after the old process is stopped or marked unresolved.
- **C/API-1:** add authenticated same-origin command and Human-decision endpoints with a
  per-process anti-CSRF token. The browser writes only validated command requests, decision
  receipts, and explicitly confirmed design edits. Run events extend the existing SSE path.
- **C/UI-1:** render capability-derived controls and run history. Unsupported controls are absent,
  never decorative disabled buttons. Add dispatch/review/stop/retry and only proven pause/resume.
- **D/ASSURE-1:** run injection, path escape, duplicate, stale confirmation, PID ownership,
  disconnect, restart, receipt tamper, and verification-failure sabotage as each seam lands.

Day-2 gate: both deep adapters pass fake-executable CLI end-to-end through prepare -> confirm ->
execute -> verify -> receipt. Failure, timeout, duplicate, restart, stop, retry, switch, and
unsupported capability each have a permanent regression. At least one opt-in real smoke per
available adapter runs on the release machine; an unavailable product is reported, never faked.

### 12.5 Day 3 — complete the browser wow path and freeze features

Feature freeze: 2026-08-15 14:00 Europe/Moscow. After that time only a release blocker, installation
failure, or wow-path defect may change production code.

- **C/HG-1:** show the Human Gate as a real lifecycle backed by immutable approve, reject,
  request-changes, and waive receipts; absence is idle, never satisfied.
- **C/EDIT-1:** ship the source-preserving minimal editor from the cut scope: form/source preview,
  validation, diff, explicit confirmation, atomic write, and one parallel branch.
- **A/POL-1:** implement narrow Policy for dispatch and independent review only, with explicit
  capability, project-root, concurrency, action-count, and time budgets. It cannot expand
  permissions, weaken gates, switch harnesses, make Human decisions, or perform arbitrary or
  destructive actions.
- **A/PRO-1:** propose bounded ready work, independent review, stale retry, and Human-Gate
  attention. Policy may execute only dispatch/review; retry and every Human decision stay Confirm.
- **A/PAR-1:** execute one bounded parallel branch; deterministic handoff routes implementation to
  one adapter and independent review to the other; Orbit advances only from verified result state.
- **C/D/WOW-1:** automate the complete browser path: open Orbit, preview, confirm dispatch, observe
  real streamed progress/evidence, hand off, review, stop at Human Gate, decide, and replay all
  attempts/receipts. Then execute the same path manually and reduce it below ten minutes.
- **D/REL-0:** finish English quickstart, threat model, demo fixture/script, and clean-wheel smoke
  while the interfaces are still fresh. Prepare but do not apply the public rename patch unless
  every external clearance is affirmative. Documentation may describe only behavior held by a
  gate.

Day-3 gate: the complete wow path passes in Chromium from a clean installed wheel with two adapter
implementations, one parallel branch, a Human Gate, history/replay, and no fake telemetry. The
feature-freeze SHA is committed and clean. Missing optional breadth is cut according to section 8,
not left half-present.

### 12.6 Day 4 — frozen release candidate only

Deadline: 2026-08-16. No feature development is scheduled on this day.

1. Freeze one release-candidate SHA before the first gate. Every result names that exact SHA and
   proves its import path; any blocker fix creates a new SHA and restarts the affected gates.
2. Run the full suite on Windows and Linux, the mutation harness, browser suite, deterministic
   fake-adapter e2e, available opt-in real-adapter smokes, package build/install, release smoke,
   threat/sabotage suite, Protocol-v1 byte pin, and committed-clean check.
3. Run two independent release reviews in parallel: one against the product/safety contract and
   one against code quality, packaging, and evidence. Both review the same SHA.
4. Execute and time the manual wow path from the clean wheel. Archive exact commands, receipts,
   screenshots/logs, limitations, and the under-ten-minute result.
5. Tag the technical preview only after every required gate is green. A missed required gate is a
   delayed release, never an inferred pass or a quality waiver.

Day 4 deliberately holds roughly one third of the recovery window for integration defects and
hostile review. If a blocker consumes that reserve, cut optional breadth before moving the safety
boundary. The two-adapter wow path, confirmation freshness, owned-process rule, receipts,
verification, restart truth, Human Gate truth, v1 compatibility, browser path, and clean-package
evidence are never cut.

### 12.7 Review and integration rules for speed without weaker evidence

- A slice is a narrow vertical behavior with its tests and truthful documentation, not a layer of
  unintegrated scaffolding. Production, tests, and plan record land before review on one clean SHA.
- The specification and quality reviews start concurrently and independently on that SHA. Their
  findings are combined into one fix batch; both re-review the resulting exact SHA.
- A repeated finding of the same class triggers structural redesign, not another enumeration of
  examples. Live defects, safety-contract gaps, false public claims, and missing regression doors
  block. True internal prose/style observations with no behavioral or public-contract consequence
  are recorded for cleanup and do not manufacture another feature cycle.
- Every safety rule has a positive path, a refusing path, a before/after state assertion, and at
  least one named sabotage that becomes a permanent regression. Test helpers obtain their witness
  independently from the production function they judge.
- Integrate at 13:00 and 20:00 Europe/Moscow. Each integration runs impacted tests, v1 pin, and a
  clean-tree/import-provenance check; the full suite runs nightly. Day 4 alone produces release
  numbers from one frozen SHA.
- No approved implementation receives a later behavior or public-contract change disguised as
  bookkeeping. A ledger-only transition from pending review to Complete is allowed after APPROVE
  only when a whitelist diff proves that one status/approved-SHA record is the entire change and
  production, tests, specifications, and public docs are byte-identical. It receives a compact
  provenance/delta review rather than reopening the implementation cycle. Any broader change is
  a new reviewed SHA. In all cases, the final release gates run on the exact release-candidate SHA.
- Existing structural limits remain: Python/test files stay below 800 lines, functions below 50
  lines, and changed lines at or below 100 characters unless an explicit, recorded exception is
  reviewed. A self-contained test circuit is split before it reaches the ceiling.

### 12.8 Progress reporting and stop conditions

At each 13:00/20:00 integration, report only executed facts: exact SHA, completed slice ids,
passed/failed/skipped counts, sabotage score, changed files/stat, residuals, and the next critical
dependency. Percentages are derived from the day gates: foundation 30%, Day-1 recovery gate 45%,
Day-2 gate 70%, Day-3 feature-freeze gate 90%, frozen Day-4 release acceptance 100%.

Stop and escalate immediately for a safety-law conflict, an interface change that invalidates two
active lanes, a repeated class defect after structural redesign, unavailable evidence for either
deep adapter, or a release gate that cannot run on the frozen SHA. Do not silently consume Day 4
with feature work, and do not report 100% until section 9 is green in full.
