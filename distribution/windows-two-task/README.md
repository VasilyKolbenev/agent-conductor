# Windows Pilot 2 · Two tasks with Kolos

Choose a completed task and one that needs similar checks. Record the first task's checks
and observed results, review the summary and confirm it. In the second task, ask Kolos
to find that procedure. Open its source, change a step and choose a reviewer in chat.
The pilot runs on loopback with the wheel in the ZIP. Both tasks stay on the colleague's
computer. Draft edits last for the browser tab.

For Windows with Python 3.11 or 3.12, extract the ZIP and open `START.cmd`. Follow the
[colleague walkthrough in Russian](START-HERE.txt). The
[Releases list](https://github.com/VasilyKolbenev/agent-conductor/releases) shows which
pilots are public. The [first pilot](../windows-pilot/README.md) includes the Codex + Grok
walkthrough and separate utility exercises. Pilot 2 uses operator-confirmed checks.

## Rebuild a candidate archive

Use the packaging directory from the candidate source revision and the `candidate-wheel`
artifact from its CI run. The hash expected by the installed-wheel job identifies the wheel
inside the artifact. The digest on GitHub's artifact page identifies the surrounding ZIP.
Set `$wheel` to the extracted wheel path and `$expectedWheelSha` to the wheel SHA-256.
From the repository root:

```powershell
py -3.12 -I -B distribution/windows-two-task/build.py --wheel $wheel --wheel-sha256 $expectedWheelSha --output-dir dist
```

The builder writes `Arachnid-Windows-Pilot-2.zip` and its `.zip.sha256` sidecar.
After extraction, `START.cmd verify` checks the manifest. Running `START.cmd` again
opens the same task pair. Use `START.cmd new` to create another pair.
