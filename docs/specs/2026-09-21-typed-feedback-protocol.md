> Integration update: new explicitly authorized Policy dispatch now uses this protocol.
> See [bounded integration](2026-09-21-bounded-feedback-integration.md).
> Foundation-only status below describes the initial isolated parser slice.

# Typed checker feedback protocol foundation — 2026-09-21

This specification implements the payload/parser portion of the accepted
`CODEX-SECTION-8-RULING-2026-09-09.md` §1. It does not replace that ruling.
The parser is inactive: no runtime, store, existing verdict parser or shipped
workflow invokes it. It creates no authority and writes no durable record.

## Closed payload

The checker output begins with the existing `VERDICT: reject` first non-empty
line. The remaining output must be exactly one JSON object, with JSON whitespace
permitted around it. Markdown fences, trailing prose and multiple objects refuse.
The existing verdict parser and its treatment of older runs do not change.

```json
{
  "protocol": "conduct.feedback.v1",
  "findings": [
    {
      "kind": "defect",
      "summary": "The empty-input branch returns an incorrect count.",
      "path": "src/count.py",
      "line": 12
    }
  ]
}
```

Both objects have exact required fields. `kind` is exactly `defect`,
`missing_requirement` or `verification_gap`. `summary` is a non-blank string;
its original Unicode, spacing and case are preserved. It is a finding field,
not an untyped stdout tail or a place for a transcript.

`path` is null or a non-empty relative POSIX path: `/` separates non-empty
components; absolute paths, `.` and `..` components, backslashes and colons
refuse. The colon exclusion prevents drive/stream spellings from looking
portable. No normalization, filesystem access, path expansion or claim of
filesystem containment occurs. A path is only a location cited by a finding.
`line` is null or a JSON integer from **1 through 9 999 999**, never a boolean
or float. The ceiling keeps a cited location from becoming a number channel and
keeps the value exact for a JavaScript reader. A line requires a non-null path;
a path without a line is permitted. The durable `correction_feedback` record
(`feedback_payload.settled_payload`) and the Studio read door
(`studio-feedback-model.js`) hold the same ceiling, so a record the parser could
not have admitted is refused wherever it is read, not only where it is written.

Decoded string fields reject Unicode control characters (categories `Cc`) and
surrogates (`Cs`), including escaped controls. Duplicate keys at either object
level, unknown/missing fields, non-finite constants, invalid UTF-8 and malformed
JSON refuse. No field carries run, grant, action, checker or other authority.

## Bounds and scanning

There are **1 through 16 findings**. The **whole payload** above, including the
protocol discriminator, keys and delimiters, is at most **8192 UTF-8 bytes** when
canonically encoded: Unicode is emitted directly, object keys sorted, separators
`,` and `:`, no surrounding whitespace, no trailing newline, no Unicode
normalization. Finding order is preserved. These are named conservative protocol
caps, not settings or measured optima. Limits already imposed by the transport
and complete checker frame remain in force. Refusal never truncates content.

Before canonical encoding, every decoded string **and integer** field is checked
for the non-empty sensitive byte values supplied by the caller: digits can spell
a sampled value as well as letters can. JSON `\u` or quote escaping must not hide
a value. This is a screen against an accidental verbatim echo, not a proof of
absence: a value split across findings, re-cased, re-encoded, or reflowed over
lines (a control character already refuses the field) is not claimed detected.
The future caller must supply doer material secrets, permitted environment
values and the checker's credentials sampled before and after its spawn, while
those samples still exist. This module reads no environment or credential files.
A refusal exposes only a stable reason, not the rejected text or secret, and
carries no chained decoder error that still holds the child's output. The
reasons are a closed vocabulary: `not_opted_in`, `invalid_sensitive_values`,
`invalid_outcome`, `not_rejected`, `malformed_payload`, `duplicate_field`,
`nonfinite_value`, `invalid_payload`, `protocol_mismatch`, `finding_count`,
`invalid_finding`, `sensitive_material`, `payload_over_limit`. Parsed values are
immutable; exported objects are fresh copies and their representation does not
print finding text.

## Explicit admission and unfinished integration

`parse_feedback(outcome, *, opted_in_protocol, sensitive)` requires the caller
to supply both keyword arguments. Only the exact `str`
`opted_in_protocol="conduct.feedback.v1"` allows parsing; an object that merely
compares equal does not. An output discriminator alone cannot opt a run in. The
outcome must be completed, exit with integer zero, have delivered stdin, and
report neither truncation nor an environment-value echo. Only an exact first
non-empty reject line is accepted, with the same leading-whitespace convention
as the existing parser. An accept line cannot publish rejection findings.

This result is untrusted, validated material, not a verdict receipt, evidence,
authorization or correction proposal. The future integration must select opt-in
from a frozen plan and bind the record through runtime facts: run/grant,
source action/attempt/node/lap, actual checker instance and adapter, checked
result digest and the feedback record ID. Those fields never come from this
payload. No grant is invented for a legacy Confirm run.

Durable publication, terminal-negative-outcome checks, orphan crash handling,
`on_failed` frontier selection, frozen feedback IDs in the correction proposal,
and the end-to-end defective-file → typed rejection → permitted correction →
verified-file witness are **not implemented by this foundation**. Until those
requirements and genuine grant/frozen opt-in integration exist, this parser must
remain unconnected to execution and storage.
