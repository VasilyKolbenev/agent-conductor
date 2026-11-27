# Arachnid Studio

Arachnid Studio is a local workspace for developers who delegate code changes to AI agents
and maintainers who decide whether to ship them. Give Colossus, your chosen lead agent, a task
in chat. Agree on who investigates, who edits, who checks the patch and when to pause for you.
When you return, open the diff, test results and review for the same attempt.

- [See a completed run on GitHub](docs/run-example.en.md) — follow a bug from diagnosis to
  acceptance. You can read the example in your browser without installing anything.
- [Open Studio on your computer](#run-arachnid) — explore the local demo without a subscription.
- [Run your own task on Windows](docs/first-run-v1.en.md#1-install-the-identified-build) —
  set up a project and connect Codex and Grok with your subscriptions.

[Русский](README.ru.md)

**Inside the accepted Codex + Grok run**

![The orbit in Arachnid Studio with Do selected and the attempt’s evidence open on the right.](docs/assets/studio-orbit-en.png)

On a real Windows run, Grok read the counter and its tests to diagnose why failed runs were counted as successes. Codex fixed `count_succeeded`. Three unit tests passed before a separate Codex instance reviewed the patch. The operator approved implementation and accepted the result. [Run record](https://github.com/VasilyKolbenev/agent-conductor/blob/3304810f645b0e515b95934328009f1456139c58/docs/recovery/2026-10-20/tasks/DALIO-FIRST-COMPLETE-REPORT.md).

## Run Arachnid

The local demos use **Python 3.11 or 3.12** with `venv` and `pip`. They run without a vendor
login or model calls. [Release downloads][release].

| Windows | Linux (tested on Ubuntu) | macOS |
| --- | --- | --- |
| Windows ZIP with a reconstruction of the Codex + Grok run. Live tasks on Windows x64 use your personal subscriptions. | Python wheel with a local release-review demo. | The same wheel and local release-review demo. |

**Windows ZIP**

1. Download the [Studio ZIP][zip] and its [SHA-256 checksum][checksum].
2. Verify the download, then choose **Extract All**. The [ZIP guide][zip-guide] shows the
   PowerShell command.
3. Double-click **`START.cmd`** in the extracted folder and leave its window open.
   If Python is missing, press **I** when offered to install Python 3.12, or **O** to open
   the [official installer][python]. Press **R** to check again.
   The first launch opens the example. Select **Do** to see the patch, three tests and checker
   verdict. Stop Studio with Ctrl+C in the launcher window. If Studio opened a saved task pair,
   return to the example with `.\START.cmd demo`.

**Optional memory exercise.** After closing the demo, run `.\START.cmd new` in PowerShell from
the extracted folder. It asks you about two tasks so Colossus can recall the first task's checks
for the second. For a live agent task, follow the [project setup guide](docs/first-run-v1.en.md).

**Linux or macOS · explore Studio.** Download the [Python wheel][wheel]. In the folder containing that file, run the following with Python 3.12 (substitute `python3.11` if needed).

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index ./agent_conductor-0.1.1-py3-none-any.whl
.venv/bin/conduct demo
```

On Windows, the same wheel also runs the CLI demo from PowerShell. For Python 3.11, use `py -3.11` on the first line.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index .\agent_conductor-0.1.1-py3-none-any.whl
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
| Claude Code | A subscription Goal produced a saved result in isolation. Identify timed out. The setup guide covers manual handoff to the official CLI. [Run record](https://github.com/VasilyKolbenev/agent-conductor/blob/3304810f645b0e515b95934328009f1456139c58/docs/recovery/2026-10-20/tasks/H5-B-RUN2-REPORT.md). |
| Kimi Code CLI | An offline session opened. A live subscription task is pending. |
| DeepSeek Harness | An API-key adapter passed local tests. The provider uses an API balance. |
| Your own CLI | Manual handoff, or two-way text exchange through a compatible local bridge. Autonomous roles and subscription support depend on the adapter. |

You can add GitHub Copilot CLI or Cursor Agent for manual handoff. [Connect your own tool](docs/first-run-v1.en.md).

## Explore the project

[Architecture](docs/architecture.md) · [Documentation](docs/index.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)

The Python package is `agent-conductor` and the command is `conduct`. For local reading, see `docs/index.md`. [Documentation](docs/index.md).

[release]: https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.1-windows.2
[zip]: https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.1-windows.2/Arachnid-Studio-Windows.zip
[checksum]: https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.1-windows.2/Arachnid-Studio-Windows.zip.sha256
[zip-guide]: https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.1-windows.2/START-HERE.txt
[python]: https://www.python.org/downloads/windows/
[wheel]: https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.1/agent_conductor-0.1.1-py3-none-any.whl

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
