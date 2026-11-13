# Rebuild Arachnid Studio Windows Pilot 1

While Pilot 1 is a draft, the repository owner can download **Arachnid-Windows-Pilot-7f6b825.zip**
from GitHub Releases while signed in. The public release and asset links on this page work after
publication. Extract the ZIP and follow [START-HERE.txt](START-HERE.txt) for the offline
Codex + Grok walkthrough and the manual utility or local echo example.
[Owner's releases page](https://github.com/VasilyKolbenev/agent-conductor/releases)
· [Windows Pilot 1 release](https://github.com/VasilyKolbenev/agent-conductor/releases/tag/v0.1.0-pilot.1)

## Reproduce the release asset

Use this directory from a checkout or source archive containing the packaging recipe.
The wheel comes from product commit `7f6b8254d2d621af4b636aa9eef1997f17f68ad6`.
Extract `agent_conductor-0.1.0-py3-none-any.whl` from the original `candidate-wheel` CI artifact
while available, or get the same file from the draft as the owner. After publication the release
wheel link serves it directly.
[Release wheel](https://github.com/VasilyKolbenev/agent-conductor/releases/download/v0.1.0-pilot.1/agent_conductor-0.1.0-py3-none-any.whl)
· [CI run](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43454184474)
· [Original artifact](https://github.com/VasilyKolbenev/agent-conductor/actions/runs/43454184474/artifacts/14051753924)

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
