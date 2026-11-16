# Rebuild Arachnid Studio Windows Pilot 1

For the current Windows download, use the [Arachnid Studio release](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.1).
Its [two-task walkthrough](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.1/START-HERE.txt)
shows how to recall checks from a previous task and edit the plan in Colossus chat.

This directory reproduces the **archived first Windows pilot**. To explore that
recorded Codex + Grok task, download `Arachnid-Windows-Pilot-7f6b825.zip` from the
[original release](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.1),
extract it and follow [START-HERE.txt](START-HERE.txt).

## What the utility exercises demonstrate

In Pilot 1, `Start.cmd utilities` opens an empty project. GitHub Copilot CLI and Cursor
Agent were registered there for manual exchanges. The operator transfers the prompt and
records the reply. `Start.cmd echo` demonstrates automatic exchange with a local executable
that speaks `arachnid.utility.v1`. A separate adapter is needed to run a utility as an
autonomous worker or checker with quota reporting. [Walkthrough in Russian](HARNESSES.txt)

For the CLI versions, subscription sign-in and isolation used in an active project,
see the [setup guide](../../docs/first-run-v1.en.md). The original build and
installation checks are recorded in the [Windows pilot report](https://github.com/VasilyKolbenev/agent-conductor/blob/a755627cc242c5edd35935ba49f89246c0933c9b/docs/recovery/2026-10-20/tasks/COLLEAGUE-WINDOWS-PACK-REPORT.md).

## Reproduce the release asset

Use this directory from a checkout or source archive containing the packaging recipe.
The wheel comes from product commit `7f6b8254d2d621af4b636aa9eef1997f17f68ad6`.
Download `agent_conductor-0.1.0-py3-none-any.whl` from the public release or extract it from
the original `candidate-wheel` CI artifact while available.
[Release wheel](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.1/agent_conductor-0.1.0-py3-none-any.whl)
· [CI run](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43454184474)

The original CI artifact ID was `14051753924`. The release wheel above is the public download.

Place the wheel in the repository root. From that directory, run these commands in PowerShell
with Python 3.12. The builder uses the Python standard library.

```powershell
python -I -B distribution/windows-pilot/build.py `
  --wheel ./agent_conductor-0.1.0-py3-none-any.whl --output-dir ./dist
Get-FileHash ./dist/Arachnid-Windows-Pilot-7f6b825.zip -Algorithm SHA256
```

| File | SHA-256 |
| --- | --- |
| Wheel | `214bf5e5beb0822f4616ded0dce44161e76e1f9d557d9c5507ec40939acd40fe` |
| Pilot ZIP | `7bff7440611c009782885d7eb47d1e4aef48efa42a56f6aa2ac40005dc468dd2` |

The builder checks all ten entries, including the 19-file synthetic demo fixture. It reproduces
the release order, timestamps, ZIP attributes and Windows text encoding from LF sources.
It writes the ZIP only when the complete archive matches the published SHA-256.
CPython 3.12.14 with zlib 1.3.2 reproduced the release on Windows.
