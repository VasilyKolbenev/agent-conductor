# December Command v2 — four-day strike

- **Status:** binding execution plan
- **Owner directive:** 2026-08-11
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
- **CMD-4 — fixed, pending external re-review 2026-08-11.** Persisted Proposals and the
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
