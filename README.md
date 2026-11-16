# Arachnid Studio

**Give Colossus one goal and put a team of coding harnesses to work on it.** In Arachnid Studio, one tool can investigate a problem, another can change the code, and a separate instance can review the result. Agree on roles, a budget and approval points in the local Studio. Once you start the workflow, the team passes results between steps until it reaches a decision or a limit.

[**Download Arachnid Studio**][release] · [Connect your tools](docs/first-run-v1.en.md) · [Русский](README.ru.md)

| Windows | Linux (tested on Ubuntu) | macOS |
| --- | --- | --- |
| Two-task ZIP, Studio and CLI. Live Codex + Grok on personal subscriptions. | Studio and CLI from the Python wheel. Local demo. | Studio and CLI from the same wheel. Local demo. |

![A completed five-step orbit: Grok diagnosed the problem, Codex implemented the fix, and the inspector links the two changed files, three tests and independent verdict.](docs/assets/colossus-pilot3-recap.png)

On a real Windows run, Grok read the counter and its tests to diagnose why failed runs were counted as successes. Codex fixed `count_succeeded`. Three unit tests passed before a separate Codex instance reviewed the patch. The operator approved implementation and accepted the result. [Run record](docs/recovery/2026-10-20/tasks/DALIO-FIRST-COMPLETE-REPORT.md).

## Run Arachnid

Use **Python 3.11 or 3.12** with `venv` and `pip`. Both walkthroughs below run locally without signing in or calling a model.

**Windows · try two of your own tasks.** Download the [Windows ZIP][zip] and its [SHA-256 checksum][checksum]. Extract the entire ZIP and double-click **`START.cmd`**. Record the checks you performed on a finished task. In the second task, ask Colossus to find that procedure, open the source and edit the proposed review plan in chat. The two tasks and accepted observations stay on your machine. Copy the edited draft before you close the tab. [Walkthrough](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.3/START-HERE.txt).

**Linux or macOS · explore Studio.** Download the [Python wheel][wheel]. In the folder containing that file, run the following with Python 3.12 (substitute `python3.11` if needed).

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index ./agent_conductor-0.1.0-py3-none-any.whl
.venv/bin/conduct demo
```

On Windows, the same wheel also runs the CLI demo from PowerShell. For Python 3.11, use `py -3.11` on the first line.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index .\agent_conductor-0.1.0-py3-none-any.whl
.\.venv\Scripts\python.exe -m conductor demo
```

Open the local URL printed in the terminal. Press Ctrl+C there to stop the demo. For a real project, the setup guide covers supported CLI versions, account sign-in, isolation and the preview you approve before execution. [First real project](docs/first-run-v1.en.md).

## Work with a team of harnesses

| Ask Colossus or choose a step | What Studio shows |
| --- | --- |
| “What did Grok hand to Codex?” | The diagnosis and its supporting material from the run. |
| Select **Do**, then an attempt | The actual diff, test results and independent verdict for that attempt. |
| “What changed while I was away?” | The latest recorded outcome, any decision waiting for you, and links to the evidence. |
| “Find the review procedure from the previous task.” | A proposed sequence and reviewer, linked to the accepted record you can inspect. |

Start with Ray Dalio’s five steps: set a goal, identify problems, diagnose the cause, design a plan and carry it out. You can also build and publish your own cycle. Use **Connect a harness** in the sidebar to add tools, then assign roles in the workflow. [Workflow setup](docs/first-run-v1.en.md) · [Evidence behind a recalled procedure](docs/assets/kolos-task-evidence.png).

| Harness | What has been verified |
| --- | --- |
| **Codex CLI + Grok Build** | A complete five-step run on Windows with the owner's subscriptions, without API keys. Codex implemented and reviewed in separate instances. |
| Claude Code | A subscription Goal produced a saved result in isolation. Identify timed out. The setup guide covers manual handoff to the official CLI. [Run record](docs/recovery/2026-10-20/tasks/H5-B-RUN2-REPORT.md). |
| Kimi Code CLI | An offline session opened. A live subscription task is pending. |
| DeepSeek Harness | An API-key adapter passed local tests. The provider uses an API balance. |
| Your own CLI | Manual handoff, or two-way text exchange through a compatible local bridge. Autonomous roles and subscription support depend on the adapter. |

For example, Pilot 1 registered GitHub Copilot CLI and Cursor Agent for manual handoff. Its local echo utility demonstrates the bridge protocol. [Try a custom utility](distribution/windows-pilot/README.md#what-the-utility-exercises-demonstrate).

## Explore the project

**Orbit design preview.** The screenshot above shows the current Arachnid Studio release. The next design gives Colossus four visible states and the harness roles distinct planets. The artwork is available for review ahead of implementation. [View the proposed orbit and its four states](docs/assets/colossus-orbit/README.md).

[Architecture](docs/architecture.md) · [V2 roadmap](docs/plans/2026-11-13-v2-alpha-review.ru.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)

Arachnid grew out of **December Command v0.1.0 alpha**. The Python package is `agent-conductor` and its command is `conduct`. For local reading, the documentation index is `docs/index.md`. [Release evidence](docs/release-notes-v1-alpha.md) · [Build checks](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43869073662).

Earlier releases include the [offline Codex + Grok example in Pilot 1](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.1) and the [original two-task pilot](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.2).

[release]: https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.3
[zip]: https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.3/Arachnid-Windows-Pilot-3.zip
[checksum]: https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.3/Arachnid-Windows-Pilot-3.zip.sha256
[wheel]: https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.3/agent_conductor-0.1.0-py3-none-any.whl

<details>
<summary><strong>CLI reference · useful once you leave the demo</strong></summary>

Run `conduct --help`, or add `--help` to a command, for its flags.
Use the executable inside your virtual environment if it is not activated.

| Command | Purpose |
| --- | --- |
| `conduct demo` | Open the bundled sample in a temporary directory. |
| `conduct init` | Create project data; interactive terminals ask setup questions. |
| `conduct validate` | Check the map and lane files. |
| `conduct doctor` | Explain readiness problems and the next action. |
| `conduct providers` | Configure executable paths and allowed environment-variable names. |
| `conduct ownership` | Activate, inspect, or explicitly recover project ownership. |
| `conduct up` | Start local Studio for the project. |
| `conduct utility-bridge` | Deliver an attached `stdio-v1` utility's pending text to a local executable and record its reply in Studio. |
| `conduct prompt` | Print working instructions for an agent's reporting role. |
| `conduct report` | Print the merged lane state as Markdown. |
| `conduct preview` | Prepare a synthetic dispatch preview without executing it. |
| `conduct integration-smoke` | Exercise the synthetic execution road; not a live provider task. |
| `conduct reconcile` | Inspect actions left uncertain after interruption. |
| `conduct tools` | Pin the `git` and `gh` this product may run (`conduct tools pin git --path <absolute path>`). |
| `conduct hub` | Serve the hub page on one loopback port (default 7700); it runs one server per project. |
| `conduct projects add` | Check and register a local project folder using the shared harness profile. |

Project-map templates are different from Studio's workflow starters:

- **`--template NAME`** skips the `conduct init` questions and chooses a project map:
  - `default-orbit` — the default five-stage map.
  - `single-harness` — one implementing role and a human decision, without a reviewer.
  - `empty` — a minimal placeholder map.
  - `minimal` — the protocol's example map.

The bootstrap prompt follows the map: where nodes are placeholders, it tells the agent to replace them with your real components;
where nodes already name components, it tells the agent to check each one against your project instead.
`conduct init` does not overwrite existing project data. Follow [first run](docs/first-run-v1.en.md) for ownership activation.

</details>
