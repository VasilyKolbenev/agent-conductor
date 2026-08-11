# ADR 0003: Command action and adapter protocol

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

An interactive Harness Control Plane must not become a generic shell. Different Harnesses expose
different public contracts, and process start is not proof that the requested result occurred.

## Decision

Every adapter implements four steps: `prepare`, `execute`, `observe`, and `verify`. Its manifest
declares exact capabilities. Unsupported controls are absent.

An action request contains a stable id, run and attempt ids, target instance, declared capability,
structured arguments, project-root-relative scope, requested time, requester, idempotency key,
timeout, and the digest of the preview that was authorized. It never contains a shell command
string. The local process adapter invokes an argv vector with `shell=False`, a validated working
directory, and an explicit environment allow-list.

Execution produces a separate result receipt with an outcome from `succeeded`, `failed`,
`cancelled`, `rejected`, `unknown`, or `verification_failed`, plus observations and evidence refs.
`accepted` and `started` are events, not successful outcomes. Repeating an idempotency key returns
the recorded result or in-flight identity and never launches a second process.

December stops only a process created by this runtime and matched to its recorded ownership token.

## Consequences

Claude Code and Codex can be deep adapters without privileged protocol semantics. Terminal-only
Harnesses remain usable, but no adapter may smuggle an unrestricted command surface into the UI.

