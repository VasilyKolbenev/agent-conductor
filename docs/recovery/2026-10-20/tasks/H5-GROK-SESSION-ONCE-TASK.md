# Observe session creation after authentication without inference

Run pinned Grok 1.0.5 once in a fresh Windows review AppContainer on the verified
product a9044e1. Use a disposable access-only login, an empty working directory and
no network capability. Do not start a task or send a prompt. Check whether the CLI
returns a nonempty sessionId, and distinguish a session refusal from an authentication
failure, timeout or malformed response. Report fixed labels only. Do not repeat the
live attempt. Stop at 45% remaining Codex quota.
