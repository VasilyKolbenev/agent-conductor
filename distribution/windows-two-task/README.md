# Windows Pilot 3 · Two tasks with Colossus

Choose a completed task and one that needs similar checks. Record the first task's checks
and observed results, review the summary and confirm it. In the second task, ask Colossus
to find that procedure. Open its source, change a step and choose a reviewer in chat.
The pilot runs on loopback with the wheel in the ZIP. Both tasks stay on the colleague's
computer. Draft edits last for the browser tab.

For Windows with Python 3.11 or 3.12, extract the ZIP and open `START.cmd`. Follow the
[colleague walkthrough in Russian](START-HERE.txt). For the published [Pilot 3](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.3),
use the [download instructions](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.3/START-HERE.txt)
to verify the ZIP. The copy inside that archive still names the Pilot 2 ZIP.
The [first pilot](../windows-pilot/README.md) includes the recorded Codex + Grok
walkthrough and separate utility exercises. The two-task pilot uses operator-confirmed checks.
To connect your own CLI subscriptions, follow the first-run guide for your wheel to open
a separate active project. [First-run guide](../../docs/first-run-v1.en.md).

## Rebuild a candidate archive

Use the packaging directory from the candidate source revision and the `candidate-wheel`
artifact from its CI run. The hash expected by the installed-wheel job identifies the wheel
inside the artifact. The digest on GitHub's artifact page identifies the surrounding ZIP.
Set `$wheel` to the extracted wheel path and `$expectedWheelSha` to the wheel SHA-256.
From the repository root:

```powershell
py -3.12 -I -B distribution/windows-two-task/build.py --wheel $wheel --wheel-sha256 $expectedWheelSha --output-dir dist
```

On this branch the builder writes `Arachnid-Windows-Pilot-3.zip` and its `.zip.sha256` sidecar.
Changes to the packaged guide change the archive digest even with the same wheel.
To reproduce the published archives, use the matching release tag and its wheel.
The original Pilot 3 builder wrote the published ZIP bytes under the Pilot 2 filename.
After extraction, `START.cmd verify` checks the manifest. Running `START.cmd` again
opens the same task pair. Use `START.cmd new` to create another pair.
