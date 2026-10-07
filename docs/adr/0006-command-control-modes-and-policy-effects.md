# ADR 0006: Control modes and bounded policy effects

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

Proactivity is valuable only when its authority is visible. A hidden autonomous mode or a broad
policy language would make a four-day implementation unsafe and incomprehensible.

## Decision

Each Orbit selects exactly one mode: `observe`, `propose`, `confirm`, or `policy`; `observe` is the
default. Observe reads. Propose creates an immutable preview. Confirm executes one unchanged
preview after a fresh Human confirmation. Policy executes only explicitly allow-listed
non-destructive capabilities within project root, concurrency, time, and action-count budgets.

For this preview Policy may allow dispatch, review, retry, and local notification. It cannot allow
Human decisions, permission expansion, destructive filesystem actions, arbitrary commands,
unconfirmed Harness/model switching, gate weakening, or edits outside validated Orbit design.
Every policy decision records the rule id and explanation in the action request and receipt.

A user can pause the Command Runtime and revoke future policy authority. Revocation does not alter
history or cancel an already verified result; in-flight cancellation follows adapter capability.

## Consequences

December can proactively prepare useful work while retaining a visible ceiling. A general scheduler
and policy language remain out of scope.
