# G6-WIRE

Two actual Grok reviews failed after their process started. The second attempt created a
session, prompt history and session updates. Neither run retained the reason. The product
intentionally discards stderr. An offline control on the pinned binary demonstrated a JSON
error on stdout for an unsigned profile.

Change Grok review only to its JSON output format. Keep the original output bound, task file,
read-only rights and stderr discard. Bind this wire format into Grok's provider facts so a
grant from the previous build cannot silently authorize the new format. Other providers and
dormant Grok dispatch retain their formats. Historical journals remain readable.

After the original byte and credential checks, extract only the documented terminal text
from a successful result. Recheck decoded bytes against sensitive values. Never publish the
envelope, thought, usage, session ID or raw error. A malformed, truncated or ambiguous result
must not yield a verified artifact. A nonzero exit may supply one product-owned reason for a
known CLI error category. Unknown errors stay generic. Predicted alternatives were intercepting
stderr for every provider or adding more external probes. The Grok-only format keeps the
existing boundary for private stderr and exercises the installed application path.

Verify through the real runtime with a fake binary: clean success publishes only its text,
an error records a fixed reason with no other bytes, invalid/oversized output and escaped
login values cannot be published. Run relevant browser and transport suites in both Windows
encodings. A future live test needs a green protected build and an owner grant for a fresh run.
