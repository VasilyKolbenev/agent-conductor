# ADR 0005: Evidence claims and verification

- **Status:** Accepted
- **Date:** 2026-08-11

## Context

Paths, URLs, test names, and adapter messages are claims. Treating their presence as proof would
violate the product law that missing evidence never becomes green.

## Decision

Structured evidence records identity, kind, label, URI/path, creator, observed time, optional
digest and Git/config/run/node/instance refs. Verification is explicit: `unverified`, `verified`,
`unavailable`, `mismatch`, or `error`. A verifier records its identity, time, observation, and
computed digest when applicable.

Core stores claims and canonical digests but does not infer availability. Local readers may verify
files inside approved roots; adapters verify Harness-native results. A later missing artifact does
not erase the last receipt: the UI shows the observation time and current freshness separately.
Private reasoning and secret content are never evidence payloads.

## Consequences

Action success can depend on observable evidence instead of process exit alone. Offline and partial
adapters degrade to honest unverified states.
