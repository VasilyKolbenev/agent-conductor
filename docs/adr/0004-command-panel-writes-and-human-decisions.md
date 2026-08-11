# ADR 0004: Narrow panel writes and Human decision receipts

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

The v1 panel is read-only. V2 must confirm actions, resolve Human Gates, and edit Orbit design
without giving browser code write access to agent-owned runtime files or arbitrary project paths.
Loopback by itself is not a browser security boundary.

## Decision

The panel may submit only validated Command requests, append Human decision receipts, and apply an
Orbit edit that has passed preview, schema validation, diff display, and explicit confirmation.
It cannot write lanes, agent events, prompts, source files, or adapter secrets.

Mutation endpoints require loopback, an allowed `Origin`, JSON content type, and a per-process
anti-CSRF token delivered by the served page. Confirmations bind to a request digest and expire;
changing any request field invalidates them.

Human receipts are immutable exclusive-created records. Actions are `approve`, `reject`,
`request_changes`, and `waive`; waive and request-changes require a reason. Correction creates a
new receipt whose `supersedes` points to the prior id. A Human Gate is satisfied only by the latest
applicable valid receipt; deleting a wait or clicking a button is never satisfaction.

## Consequences

December gains useful interactivity without broad filesystem authority. Browser tests and threat
tests become release gates, and Orbit writes require a stricter path than ordinary commands.
