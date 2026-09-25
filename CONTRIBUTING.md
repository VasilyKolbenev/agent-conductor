# Contributing to December Command

[Русский](CONTRIBUTING.ru.md) · [README](README.md) · [Documentation](docs/index.md) · [Architecture](docs/architecture.md)

You can help with a clearer sentence, a reproducible bug report, a focused fix or a small feature. You do not need to understand the whole codebase first. Describe what a person should be able to do, then find the smallest coherent change that enables it.

## Set up a development copy

You need Git and Python 3.11 or newer. Fork the repository on GitHub if you need somewhere to push your work, then clone your fork and enter its root directory. Use the exact branch or commit agreed for your task; the default branch is not evidence of a tested release candidate.

Create a virtual environment to keep project dependencies together. These commands use its executables directly, so activation is optional.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,browser]"
.\.venv\Scripts\conduct.exe demo
```

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,browser]"
.venv/bin/conduct demo
```

Open the URL printed by `conduct demo`; stop the server with `Ctrl+C`. This demo uses bundled fixtures in a temporary directory and makes no paid model calls. You need no vendor login or API key for the demo or routine tests. The real-project setup is a separate walkthrough in the [first-run guide](docs/first-run-v1.en.md).

The editable install makes source edits available without reinstalling. Install both extras: `dev` supplies pytest, while `browser` also supplies Playwright and Pillow. Even the `tests/` suite imports Playwright through `tests/test_browser_gate.py` → `browser_tests/conftest.py`. Chromium itself is needed when you run browser checks, not merely to collect that suite. Shell commands for macOS do not establish that a particular release has been verified on macOS; see the first-run guide for recorded platform checks.

## Find the right place

Start with the [architecture guide](docs/architecture.md), then read nearby code and tests together.

- `src/conductor/schema.py`, `store.py`, `merge.py` and `report.py` handle lane data and the derived project report.
- `src/conductor/command/` contains workflows, runs, execution and provider adapters.
- `src/conductor/panel/` contains the browser UI, including the Workflow Studio.
- `tests/` checks Python behavior and source contracts; `browser_tests/` checks the rendered application in Chromium.

Keep existing boundaries. For Studio, `studio-model.js` transforms payloads without DOM or network access; `studio.js` owns transport. The allowed imports and file limits are checked in [test_studio_source.py](tests/test_studio_source.py). Adapter import cycles and public interfaces are checked in [test_adapter_module_graph.py](tests/test_adapter_module_graph.py). Read the relevant guard before splitting or moving a module.

The UI should read provider capabilities from the owning backend contract, not invent a hardcoded list. A successful child-process exit does not prove that its work was verified. Preserve those distinctions in behavior, labels and documentation.

## Check the change you made

For ordinary contributions, choose tests that exercise the changed behavior. For example, a change to the bundled lane demo belongs with `tests/test_demo.py`, which checks schema validity, blockers, disagreement and the human queue.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_demo.py
```

macOS / Linux:

```sh
.venv/bin/python -m pytest -q tests/test_demo.py
```

Replace that path with the relevant file or pytest test ID for your change. For UI changes, inspect the affected screen and choose its matching `browser_tests/test_*.py` checks too; source checks alone do not verify rendering. Install Chromium with the virtual environment's Python and `-m playwright install chromium` before running them. Linux may also need Playwright's system dependencies (`-m playwright install --with-deps chromium`).

Full checks belong in CI, release preparation, or changes whose impact warrants them. From the repository root:

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe browser_tests/gate.py
.\.venv\Scripts\python.exe browser_tests/gate.py --reverse
```

macOS / Linux:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m playwright install chromium
.venv/bin/python browser_tests/gate.py
.venv/bin/python browser_tests/gate.py --reverse
```

The default pytest command collects `tests/`. The browser gate runs each browser module in a fresh process and writes evidence to a temporary directory; both normal and reverse order matter for a release. A plain `pytest browser_tests` run is not the release gate. See the [CI workflow](.github/workflows/ci.yml) and [release smoke guide](docs/release-smoke.md) for the wider checks, including the `scripts/mutate_merge.py` helper. Read failures and collected-test counts; do not describe an unrun check or a successful process exit as verified behavior.

## Work with an AI coding assistant

Give the assistant a concrete result, an area to inspect and a boundary for the change. Review its diff as you would any contribution.

- Ask it to inspect the affected code, contracts and tests, then explain the intended behavior before editing.
- Preserve existing user edits. Avoid blanket rewrites, unrelated cleanup, and weakening or deleting checks just to obtain a pass.
- If behavior changes a specification, keep the real implementation, relevant checks and documentation consistent. Editing a spec alone does not implement a feature.
- Keep API keys and tokens out of chat, repository files, screenshots and logs. Use the documented environment-variable setup for an explicitly authorized live-provider task.
- Ask for the exact checks run, their results and anything still unverified. Routine development should use fixtures and fake providers.

Copy and adapt this brief:

```text
Goal: [observable user behavior and a concrete example].
Inspect: [relevant files] and their nearby contracts/tests first.
Scope: make the smallest coherent change; preserve existing user edits.
Explain the intended behavior, then implement it without weakening checks.
Use fixtures; do not call live providers or handle credentials.
Verify with [relevant test file/ID] and describe what remains unverified.
```

## Send your first pull request

1. Choose one problem and describe the current and expected behavior. For a substantial feature, discuss the scope in an issue first.
2. Create a branch in your clone. Make the focused change and keep the English and Russian versions of any paired documentation aligned.
3. Run the relevant checks, read `git diff` and `git status`, and stage only the intended files. Leave generated output and secrets out of the commit.
4. Commit with a clear description, push the branch to your fork and open a pull request. State the problem, resulting behavior, checks actually run and any remaining limits. A draft PR is useful when you want early feedback.

If you get stuck, include the command, operating system, Python version and a minimal example with private data removed. A precise question or reproducible report is already a useful contribution.
