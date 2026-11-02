# Distinguish a slow status check from a signed-out subscription

In the Windows core run on 0241f44 the short timeout meant to exercise the
Claude prompt expired during login preflight instead. The receipt then told
the owner to sign in although the CLI had never answered the status question.

Give a timed-out status check a fixed, secret-free failure receipt before
claiming the action or dispatching a task. Reproduce that path at the runner
boundary. Separately prove the real sleeping test child entered the prompt and
timed out there, with its action claimed, login intact, relay removed and lease
available. Give the preflights sufficient time to start on a busy Windows host.
Keep the existing completed signed-out and API-key refusals covered.
