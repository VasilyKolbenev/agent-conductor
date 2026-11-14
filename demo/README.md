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

For the Windows download that lets a colleague supply two tasks and reuse a review
procedure in Kolos chat, see the [two-task pilot](../distribution/windows-two-task/README.md).
