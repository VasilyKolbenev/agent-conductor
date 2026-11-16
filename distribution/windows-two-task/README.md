# Arachnid Studio for Windows

Download `Arachnid-Studio-Windows.zip` and its SHA-256 from the current release.
Extract the whole ZIP and open `START.cmd` with Python 3.11 or 3.12 installed.
The launcher verifies the packaged files and installs its wheel offline.
[Release downloads](https://github.com/VasilyKolbenev/agent-conductor/releases)
· [English and Russian walkthrough](START-HERE.txt)

The first launch opens a read-only reconstruction of a completed Codex + Grok run.
Select **Do** to inspect the changes, the three tests and the independent review.

| Command | What opens |
| --- | --- |
| `START.cmd` | The latest saved task pair, or the Codex + Grok example on first launch. |
| `START.cmd demo` | The Codex + Grok example. |
| `START.cmd new` | Two personal tasks. Record accepted checks from the first, then recall and edit the plan in the second. |
| `START.cmd verify` | File integrity verification. |

New task pairs are stored in `%USERPROFILE%\ArachnidStudio`. Studio can read the
previous launcher's last pair from `%USERPROFILE%\ArachnidPilot2`. The example uses
a temporary workspace. To connect your own subscriptions, create an active project
using the [first-run guide](../../docs/first-run-v1.en.md).

## Build the Windows ZIP

Use the source and the CI wheel from the same commit. Supply the wheel digest
reported by the CI build job.

```powershell
py -3.12 -I -B distribution/windows-two-task/build.py --wheel $wheel --wheel-sha256 $expectedWheelSha --output-dir dist
```

The builder writes `Arachnid-Studio-Windows.zip` and its `.zip.sha256` file.
It checks the packaged example against the approved fixture digest.
