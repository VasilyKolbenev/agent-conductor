# Native subscription quota collection (21 September 2026)

This addendum supersedes the earlier foundation-only statements for the paths
implemented below. No authenticated user account was queried during development.
Synthetic native protocol and boundary tests prove the code path, not the current
quota of an operator account. Setup still requires the operator's own native login.

All subscription readers use the configured executable, ProcessRunner constructor
environment, allowlist and dispatch auth_home. Native sources remain provider-owned;
HTTP GET only reads the existing cache. SessionContext keeps account unknown and
never deduplicates aliases or totals subscription capacity. Rebinding invalidates
old generations and an error replaces a previous successful sample.

- Codex: native app-server account/read plus account/rateLimits/read, existing
  ChatGPT method proof. Finite request framing and bounded output use ProcessRunner.
- Claude 2.1.239: native experimental control get_usage, no model/user prompt.
  Native initialize must identify a first-party subscription with no API-key or
  token-source override. Native get_usage may fall back to persisted utilization
  without disclosing age, so the reader requires the same shown windows as the bounded
  cachedUsageUtilization field (equal utilization, reset within 60 s) and retains
  fetchedAtMs. Missing or mismatched cache is unavailable. Repeated polling never makes
  the same native cache fresh. The control spawn alone runs without
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC, dropped from the forced switches and the
  allowlist alike: measured live on 23 September 2026, under that switch get_usage only
  echoes the vendor cache and never refreshes it. DISABLE_AUTOUPDATER, --safe-mode, the
  version preflight and every task spawn keep the full profile.
- Grok 1.0.5: ACP initialize, _x.ai/auth/info, _x.ai/billing. Only cached_token is
  admitted; no login or token-export method is invoked. A dedicated native login
  profile retains only the measured bootstrap config. Custom endpoint/auth config
  and actual selected override environment cause a closed refusal. Billing's
  creditUsagePercent and currentPeriod provide the real percent and reset.
- Kimi 0.38.0: a caller-owned ephemeral native web server on literal IPv4 loopback,
  same managed OAuth profile, reads /api/v1/auth then /api/v1/oauth/usage. The external
  helper selects an unused loopback port and supplies that explicit port to the
  owned child. Only that port and the native persistent server.token are used;
  no existing server is discovered. The token is never rotated or exposed.
  An owned stop must succeed after the read; an exited/bind-failed leader refuses
  the sample. The fixed-path transport has no proxy/redirect and bounds response
  size and whole-call duration. Every road retires the native group before cleaning
  per-attempt files. Windows registry polling was rejected after it provably made
  native atomic metadata publication fail with EPERM; no registry polling or Win32
  reader workaround is in the implementation.


Kimi's native ACP authenticate(methodId=login) is a readiness check in the pinned
source; it calls ensureAuthed and never performs a device login. Dispatch uses that
check only after the profile is established as the native managed OAuth provider.
Custom model/API-key/provider/environment replacements are refused. Both native
regional managed endpoints are supported by their exact native OAuth slot formula.
The old quota.usages parser is retained for the earlier schema's value fixtures;
the live 0.38.0 reader selects the separate summary/limits/counts parser. A zero
capacity is unknown, never 0% used. Native normalized counts are reported as such;
this reader cannot reconstruct fields the native server already normalized.

No source claims that cached telemetry equals verified billing-account identity.
No collector requests a login, model turn or paid inference. Native
vendors may refresh an existing credential while reading account metadata; that
stays inside the same native auth home and the existing retention/leak-scan road.
