# Arachnid Studio documentation

[English](index.md) · [Русский](index.ru.md) · [Project home](../README.md)

## Try Studio

- **Bring two tasks on Windows.** Record how you checked a finished task. In the second task, ask Colossus for the same procedure, inspect its source and edit the proposed plan in chat. Download the Windows ZIP, extract it and open `START.cmd`. This walkthrough works offline. [Arachnid Studio release](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.3) · [Walkthrough](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.3/START-HERE.txt).
- **Explore on Windows, Linux or macOS.** Install the release wheel and run `conduct demo` to open a local sample with a recorded attempt and a pending decision. No subscription is required. [Installation commands](../README.md#run-arachnid) · [What the demo contains](../demo/README.md).
- **Run a real project.** Connect your tools, assign the roles, inspect the limits and approve execution in Studio. Codex and Grok completed the live subscription workflow on Windows. [First real project](first-run-v1.en.md).

## Understand the project

- [Architecture](architecture.md) follows one task through Studio, the execution layer and the recorded result.
- [Reporting protocol](../spec/PROTOCOL.md) defines what a participant can record in its reporting lane.
- [Contributing](../CONTRIBUTING.md) covers local setup, checks and pull requests.

## Verify a build

- [Release smoke test](release-smoke.md) checks the installed artifact.
- [Owner acceptance](owner-acceptance.md) walks through the operator's decisions on a real project.
- [Two-task acceptance](acceptance-two-tasks.md) checks that two tasks can share a team while keeping their results separate.

December Command was the earlier product name. The Python package is `agent-conductor` and the command is `conduct`.
