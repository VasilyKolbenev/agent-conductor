# Grok terminal error evidence

Baseline 5d5e5f5. The last G6 receipt contains a failed action and an unclassified
service error. Its raw vendor message was intentionally not stored. The historical
cause cannot be reconstructed from that receipt.

At xai-org/grok-build source tree 9fabade, headless.rs on_error writes type and
message and optionally attaches frozen usage. There is no independent HTTP status
in this JSON contract. 14-headless-mode.md documents usage.total_tokens and the
incomplete-only form. A missing value gives no verdict about calls or cost.

Keep the existing classifications. For otherwise unclassified terminal failures,
distinguish positive integer total_tokens from incomplete usage and from an
absence of evidence. Emit only fixed descriptions, never counts, opaque data or
messages. An unsuccessful attempt never produces a verified result. Compare
matched cases at the adapter's public execution door, including a fake secret,
malformed counts, and unchanged success. This task authorizes local tests only.
