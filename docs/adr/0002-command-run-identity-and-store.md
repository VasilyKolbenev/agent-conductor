# ADR 0002: Command run identity and append-only store

- **Status:** Accepted
- **Date:** 2026-08-11
- **Supersedes:** ADR 0001's deferral of run identity for December Command v2 only

## Context

Protocol v1 intentionally has no run identity. December Command cannot retry, recover, switch
Harnesses, or explain history without distinguishing a design-time Orbit from one execution and
its attempts. Adding mutable run fields to v1 lanes would break their single-writer contract.

## Decision

V2 introduces an immutable run envelope with `schema_version`, `run_id`, `cycle_id`, UTC
`created_at`, control `mode`, frozen `config_digest`, and initial status. A run owns ordered
attempts and append-only action, evidence, event, and decision records. A retry or Harness switch
creates a new attempt; it never rewrites the earlier attempt.

Runtime lives under `conductor/runs/<run_id>/`. The Command Runtime is the single writer. Initial
documents are created exclusively; append records are newline-delimited canonical JSON; mutable
indexes are derived and may be atomically replaced. Restart recovery replays records and marks an
owned process whose identity cannot be re-established as `unknown`, never `succeeded`.

The frozen configuration snapshot contains design digests and non-secret adapter configuration.
Secret values are excluded. Protocol v1 files and merge semantics are unchanged.

## Consequences

History becomes replayable and causal. Storage grows append-only and needs compaction later, but
truth is never recovered from a mutable status flag alone.

Two states a crash can leave behind are recoverable, and neither is recovered by guessing. Both
procedures are written out below because an operator who cannot find them has, in practice, only
one move left: deleting the run.

### Recovering a run whose journal was cut off mid-write

A crash, a `SIGKILL`, a full disk or a power loss during an append can leave
`conductor/runs/<run_id>/records.jsonl` ending in a partial line — bytes with no closing newline.
Every complete record before it is intact and is still read; only the fragment is in question,
and the store never guesses what it was going to say.

Reading is non-destructive, always. `RunStore.read` ignores the fragment, leaves it on disk byte
for byte, and reports one warning: `records.jsonl ends with an incomplete record; the incomplete
tail was ignored and left in place`. A reader — the panel, `conduct report`, a replay — therefore
shows the same run it would have shown before the crash, and says that something was interrupted
rather than pretending nothing was.

Repair belongs to the run's single writer and to nobody else. `RunStore.recover(run_id)` truncates
the fragment back to the last complete record and says so with its own warning: `records.jsonl
ended with an incomplete record; the incomplete tail was ignored`. Running it from a second
process while the writer is live is the one thing that turns a recoverable crash into a corrupted
one.

`conduct integration-smoke` repairs its own fixed run before it proposes anything, because for
that one run id the gate is that single writer. A crash mid-append therefore costs the
interrupted line and nothing else: run the command again.

Only an interrupted final line is repairable this way. A *complete* record that contradicts its
contract or its neighbours is `CorruptRun`, raised with the store's own line number; recovery
never reaches it and never rewrites it. Deleting the run directory is always available and always
loses that run's history — reach for it last, not first.

### Closing an action that was interrupted before it could start

If the process dies between the moment an action request is written down and the moment the
effect lease is taken, the action is left in the one state that is neither resumable nor
finished: a durable request with no lease. The runtime will not execute it — a restarted process
holds no fresh authority to spend, and inventing one would be the product deciding on its own
that a human had confirmed something. So it refuses, and names the way out.

Because no lease was ever appended, no effect was ever authorized to start: `execute` writes the
lease before it calls the adapter, so an action that never reached a lease never reached a spawn.
Reconciling therefore closes the action honestly rather than guessing:

    from conductor.command.run_store import RunStore
    from conductor.command.runtime import ControlRuntime
    ControlRuntime(RunStore(project_root)).reconcile(run_id, action_id)

It resolves no adapter, prepares, executes and verifies nothing, and appends one terminal
`unknown` result — the only honest terminal for an effect nobody observed, and one this runtime
never promotes to a success. It refuses a run that is not in `confirm` mode, a run whose replay
left unjudged durable bytes, an action that already carries an attempt event (that recovery
belongs to `execute`, which never repeats an effect), and an action that already has a terminal
result. There is no `conduct reconcile` subcommand in this release; the runtime API above is the
whole operation.
