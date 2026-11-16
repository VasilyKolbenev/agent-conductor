# Explore Arachnid Studio with `conduct demo`

Run `conduct demo` from an installed copy, open the printed loopback URL and select
`demo-run-001`. The bundled release-review workflow contains a recorded attempt, an
approved decision and a final decision still pending. The command prepares a temporary
project, so you can explore it without connecting a subscription or calling a model.
Stop the server with Ctrl+C.

The same temporary project also contains the classic release-gate example. Its two
lane reports describe three blockers, one disagreement and a decision about payment
configuration. The example reads those reports from the packaged fixture. The workflow
history above comes from the separate Studio demo builder.
[Packaged fixture](../src/conductor/_demo/conductor) ·
[Studio demo](../src/conductor/command/demo_scenario.py)

The Windows ZIP opens the Codex + Grok example on first launch. Run `.\START.cmd new` for a second walkthrough. You record the checks from
a finished task, then ask Colossus to recall them for the next one. You can inspect the
source and edit the proposed plan in chat. [Download Arachnid Studio](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.1) ·
[Two-task instructions](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.1/START-HERE.txt).
