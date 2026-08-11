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
