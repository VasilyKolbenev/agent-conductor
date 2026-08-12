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
  and held against the module's frozen envelope and configuration before any append, and one
  that disagrees on any field is refused with exit 1, an empty stdout and its append-only
  history byte for byte untouched. That third is the same class as the first: check the state
  you found against the frozen identity, never work from it. Execution remains disabled until
  the owned-process runner and Confirm authorization are green. Not marked Complete: external
  APPROVE from Codex is not yet given.
