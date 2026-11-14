# Arachnid Studio documentation

[English](index.md) · [Русский](index.ru.md) · [Back to the project](../README.md)

You do not need to read every specification before trying the product.
Pick the path that matches what you want to do.

## I want to use it

1. [Try two of your own tasks in Windows Pilot 2](../distribution/windows-two-task/START-HERE.txt). Record the checks you performed on the first task. In the second, ask Kolos for the order, open its source and edit the plan in chat. Both pilots work offline. Download published ZIPs from [GitHub Releases](https://github.com/VasilyKolbenev/agent-conductor/releases).
2. [Explore the Codex + Grok example in Windows Pilot 1](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.1). Select Do to inspect the patch, tests and independent verdict in the packaged sample.
3. [Set up a real project](first-run-v1.en.md): install, connect tools, open Studio, and understand the first run.
4. [Read the V1 candidate notes](release-notes-v1-alpha.md): implemented features and actual acceptance evidence are separate.
5. [Run the task isolation acceptance check](acceptance-two-tasks.md): a guided check that work from two tasks stays separate.

## I want to understand or change it

1. [Architecture](architecture.md): one end-to-end example, the main folders, and terms explained.
2. [Contributing](../CONTRIBUTING.md): local setup, a focused change, useful checks, and a first PR.
3. [V1 / V2 scope](v1-v2-scope.md): what must ship now and what is a future direction.

## I need the exact contract

| Question | Reference |
| --- | --- |
| What can an agent write in its reporting lane? | [Protocol](../spec/PROTOCOL.md) |
| What do the command API endpoints mean? | [Cockpit API](specs/2026-08-13-cockpit-command-api.md) and [current controls fields](specs/2026-09-09-controls-current-contract.md) |
| How does bounded automatic execution get permission? | [Authorization values](specs/2026-09-21-bounded-authorization-values.md) |
| How does a rejection become a permitted correction? | [Feedback integration](specs/2026-09-21-bounded-feedback-integration.md) and [typed findings](specs/2026-09-21-typed-feedback-protocol.md) |
| What does a quota reading establish? | [Quota observations](specs/2026-09-21-quota-observations.md) and [native subscription sources](specs/2026-09-21-native-subscription-quota.md) |
| Why is a component designed this way? | [Architecture decisions](adr/) |

December Command was the earlier product name. The package is still `agent-conductor` and the CLI is `conduct`.

Some older decisions use “V2” for the command layer that is now in the V1 product candidate.
Use the [current architecture](architecture.md) and [scope](v1-v2-scope.md) to orient yourself;
a date-stamped design document is not a claim that a release has passed acceptance.

## I am preparing a release

- [Release smoke](release-smoke.md): checks for the built artifact.
- [Owner acceptance](owner-acceptance.md): the user's own end-to-end acceptance.
- [Two-task acceptance](acceptance-two-tasks.md): the shared team and isolation scenario.
- [Candidate notes](release-notes-v1-alpha.md): the record to update with actual evidence.

The first-run guide is a tutorial. The acceptance documents are more detailed procedures;
you do not have to execute a release checklist to explore the demo or make a small contribution.
