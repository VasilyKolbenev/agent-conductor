# Arachnid Studio documentation

[English](index.md) · [Русский](index.ru.md) · [Project home](../README.md)

## Try Studio

- **Try the example or bring two tasks on Windows.** Extract the ZIP and open `START.cmd` to explore the completed Codex + Grok example. Run `.\START.cmd new` to record the checks from a finished task, recall them in the next one and edit the plan in chat. Both walkthroughs work offline. [Download Arachnid Studio](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.1-windows.2) · [Installation guide](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.1-windows.2/START-HERE.txt).
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
