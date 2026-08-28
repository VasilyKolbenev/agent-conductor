# Release smoke test

What a person runs against a release candidate before publishing it: install it clean, run
every command it ships, and look at the living panel. Nothing here is automated — the suite
already runs in CI, and this procedure exists to check the things a suite cannot: that the
built artifact installs, that the console script appears on PATH, that the panel answers a
real browser request on a real socket, and that it answers on loopback and nowhere else.

Eleven steps, in order. Every one of them names what you must see. A step whose output does not
match is a release blocker, not a note for later.

**Shell.** The commands below are Windows PowerShell, because that is the shell the procedure
was executed in when it was written. The `conduct` commands themselves are the same on every
platform; only the plumbing around them — fetching a URL, listing a listening socket, killing
a background process — is shell-specific, and each of those steps says what it is checking so
you can spell it your own way.

**Port.** `conduct up` and `conduct demo` bind 127.0.0.1:7777 by default. The steps below pass
`--port` explicitly, because on the machine this was executed on 7777 was already held by
another process — which is the case `--port` exists for, and step 10 checks what happens when
it is not passed.

---

## 1. Install the candidate into a throwaway environment

Never smoke-test in the environment you develop in: an editable install of the working tree
will answer every command and prove nothing about what you are about to publish.

```powershell
$SMOKE = "$env:TEMP\conduct-smoke"
Remove-Item -Recurse -Force $SMOKE -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $SMOKE | Out-Null
python -m venv "$SMOKE\venv"
$env:PYTHONPATH = ""          # nothing on the path but the installed package
$PY = "$SMOKE\venv\Scripts\python.exe"
$CONDUCT = "$SMOKE\venv\Scripts\conduct.exe"
& $PY -m pip install <the release candidate>
```

For a candidate already published, `<the release candidate>` is the install line from the
README's quickstart. For one that is not published yet, it is the path to the source tree you
are about to build from — the point of the step is that the artifact under test is installed,
not imported from a checkout.

Expect: the install succeeds, and `& $PY -m pip list` shows the distribution at the version
you are shipping.

## 2. The command exists and lists what it can do

```powershell
& $CONDUCT --help
```

Expect exit 0, and this list of subcommands — no more, no fewer:

```
usage: conduct [-h] {validate,init,doctor,prompt,report,preview,integration-smoke,up,demo} ...
```

If a subcommand you expected is missing, the wheel is not built from what you think it is.

## 3. The version is what you are shipping

```powershell
& $PY -c "import conductor; print(conductor.__version__)"
```

Expect the version string of this release: `0.1.0`.

Checked by eye, not by command: that this string and the version in `pyproject.toml` agree.
The CLI has no `--version` flag — `conduct --version` is an argparse usage error, exit 2 —
and nothing in the package compares the two, so the only thing standing between them is you,
here, before you publish.

## 4. The demo serves a panel

```powershell
$demo = Start-Process -FilePath $CONDUCT -ArgumentList "demo","--port","7801" `
    -PassThru -NoNewWindow `
    -RedirectStandardOutput "$SMOKE\demo-out.txt" -RedirectStandardError "$SMOKE\demo-err.txt"
Start-Sleep -Seconds 3
Get-Content "$SMOKE\demo-out.txt"
Get-Content "$SMOKE\demo-err.txt" -Encoding UTF8    # without it, PowerShell mangles the dash
```

Expect stdout to be the URL alone — it is the command's result and has to survive a pipe:

```
http://127.0.0.1:7801/
```

and stderr to carry the throwaway fixture path and the lifecycle line:

```
demo fixture materialized in ...\conduct-demo-rup_x8pc (throwaway copy)
serving ...\conduct-demo-rup_x8pc — Ctrl+C to stop
```

## 5. The panel and the state document answer

```powershell
$r = Invoke-WebRequest -Uri "http://127.0.0.1:7801/" -UseBasicParsing
"$($r.StatusCode) $($r.Headers['Content-Type']) $($r.RawContentLength) bytes"
[regex]::Match($r.Content, '<title>[^<]*</title>').Value
$j = (Invoke-WebRequest -Uri "http://127.0.0.1:7801/state.json" -UseBasicParsing).Content |
     ConvertFrom-Json
"project=$($j.project) state=$($j.project_status.state) reason=$($j.project_status.reason)"
"findings=$($j.findings.Count) queue=$($j.human_queue.Count)"
$handoff = Invoke-WebRequest -Uri "http://127.0.0.1:7801/handoff/claude.md" -UseBasicParsing
"$($handoff.StatusCode) $($handoff.Headers['Content-Type'])"
($handoff.Content -split "`n")[0]
```

Expect `200 text/html; charset=utf-8` and a page with `December` in its `<title>` — a served
page of only a few hundred bytes means the packaged panel did not make it into the wheel. `GET /`
answers the Workflow Studio shell; the classic panel is at `/panel/index.html` and is the tens-of-
kilobytes document. Expect the state document to describe the bundled scenario, which the README's
quickstart sets out:

```
project=web-app state=blocked reason=human_decision
findings=3 queue=1
200 text/markdown; charset=utf-8
# Conduct handoff — claude
```

The handoff response is generated from the same brokered `state.json`, not from the raw lane,
and is what the panel's **Copy handoff packet** button copies.

## 6. It listens on loopback and nowhere else

```powershell
Get-NetTCPConnection -LocalPort 7801 -State Listen | Select-Object LocalAddress,LocalPort
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.PrefixOrigin -ne 'WellKnown' } |
       Select-Object -First 1).IPAddress
try { Invoke-WebRequest -Uri "http://$ip`:7801/" -UseBasicParsing -TimeoutSec 5 | Out-Null;
      "REACHABLE OFF LOOPBACK - BLOCKER" } catch { "refused off loopback: OK" }
```

Expect exactly one listening row, `LocalAddress 127.0.0.1`, and the fetch at the machine's own
LAN address to fail to connect. Two separate facts: the first is what the socket was bound to,
the second is what a machine on the same network can actually reach.

## 7. The panel asks nothing of the network

```powershell
$html = (Invoke-WebRequest -Uri "http://127.0.0.1:7801/" -UseBasicParsing).Content
[regex]::Matches($html, 'https?://[^\s"''<>)]+') | ForEach-Object { $_.Value } | Sort-Object -Unique
[regex]::Matches($html, '(?:fetch|EventSource|XMLHttpRequest|WebSocket)\s*\(\s*[^)]{0,40}') |
    ForEach-Object { $_.Value.Trim() } | Sort-Object -Unique
$resource = '(?:\bsrc|\bhref|\bposter)\s*[:=]\s*["'']?[^"''\s>;)]{0,60}' +
            '|@import[^;]{0,60}|@font-face|url\(\s*[^)]{0,60}'
[regex]::Matches($html, $resource) | ForEach-Object { $_.Value.Trim() } | Sort-Object -Unique
```

Expect the only absolute URL in the served page to be `http://www.w3.org/2000/svg`, which is
an XML namespace name and not an address anything fetches, and the only two network calls to
be same-origin:

```
EventSource("/events"
fetch("/state.json", { cache: "no-store" }
```

The third scan exists because the first two cannot see the spellings this step's own verdict
names. A CDN script tag or a web font can be loaded without a scheme — `src="//cdn.example.com/x.js"`,
`@font-face { src: url(//cdn.example.com/x.woff2) }` — and neither the absolute-URL scan nor
the call scan reports one. Expect exactly two hits, both fragment references into the page's
own SVG:

```
url(#arw
url(#ctstFill
```

Every hit from the third scan must be same-origin or a bare `#fragment`. A hit naming a host,
with a scheme or without one, is a blocker, and so is any absolute URL beyond the namespace
above: the panel is offline software and a page that reaches out is not.

Stop the demo when you are done with it:

```powershell
Stop-Process -Id $demo.Id -Force
```

## 8. `conduct init --template` scaffolds a real project without asking anything

```powershell
$PROJ = "$SMOKE\proj"
New-Item -ItemType Directory -Force -Path $PROJ | Out-Null
& $CONDUCT init --template default-orbit --dir $PROJ
```

`--template` is the automation path: it asks nothing, so this step cannot hang waiting for an
answer nobody is there to give. Read it for exactly that and no more — the flag returns before
init ever asks whether it has a terminal, so running it from your own console proves nothing
about the no-terminal default, which is named below among what this procedure does not check.
Expect exit 0, the scaffold report and the verdict on stderr:

```
scaffolded ...\proj\conductor: map.toml (edit me), lanes/, events.jsonl
template: default-orbit

conduct validate: clean — no warnings.
```

and, on stdout alone, the bootstrap prompt, beginning:

```
You are setting up Conduct for this project. The map you must fill
in is:
```

Run it a second time and expect a refusal, exit 1 — a release that overwrites somebody's
`conductor/` is a release you do not publish:

```
...\proj\conductor already exists — refusing to touch it
```

## 9. `conduct validate`, `conduct doctor`, `conduct report` and `conduct prompt` read what init wrote

```powershell
& $CONDUCT validate --dir $PROJ; "validate exit=$LASTEXITCODE"
& $CONDUCT doctor --dir $PROJ; "doctor exit=$LASTEXITCODE"
& $CONDUCT report --dir $PROJ
& $CONDUCT prompt --role scout --author claude --dir $PROJ
```

Expect `conduct validate` to print nothing at all, on either stream, and exit 0. Silence is
the whole signal: a freshly scaffolded map that warns has a defect in the template it was
written from.

Expect `conduct doctor` to describe the scaffold honestly and exit 1: the map is still the
built-in `default-orbit`, no lane has reported, and no declared role is held. Its last line is:

```
not ready: 3 finding(s), 0 unknown, 2 ok.
```

Each finding must include a copyable `next: conduct ...` command. This is a successful smoke
result even though the process exits 1: a fresh scaffold is valid, but it is not yet a project
that agents have configured or worked in.

Expect `conduct report` to print a Markdown document beginning `# Conduct report —
your-project`, with a `## Decision brief` naming `no_lanes_yet` and a `## What this report
does not know` section. A scaffold nobody has worked in yet has nothing to report, and the
report has to say so rather than look healthy.

Expect `conduct prompt` to print the scout's working prompt, beginning:

```
You hold the "scout" role in this project's Conduct cycle; you review findings from: no other roles.
```

## 10. `conduct up` serves the project, and a busy port fails loudly

```powershell
$up = Start-Process -FilePath $CONDUCT -ArgumentList "up","--dir",$PROJ,"--port","7802" `
    -PassThru -NoNewWindow `
    -RedirectStandardOutput "$SMOKE\up-out.txt" -RedirectStandardError "$SMOKE\up-err.txt"
Start-Sleep -Seconds 3
Get-Content "$SMOKE\up-out.txt"
((Invoke-WebRequest -Uri "http://127.0.0.1:7802/state.json" -UseBasicParsing).Content |
 ConvertFrom-Json).project_status.state
& $CONDUCT up --dir $PROJ --port 7802; "busy exit=$LASTEXITCODE"
Stop-Process -Id $up.Id -Force
```

Expect the URL on stdout, `http://127.0.0.1:7802/`, and the scaffolded project's state
`ready` from its `/state.json` — the same document the panel renders.

Expect the second `up`, on the port the first one holds, to refuse and exit 1:

```
cannot serve on 127.0.0.1:7802: [WinError 10048] ... To try a different port, rerun with --port PORT.
```

The message names its own answer: rerun with `--port`. The operating system's half of the line
is whatever your platform says about a busy socket, and it is localized — read past it to the
sentence Conduct adds. If that sentence is missing, this build is older than it claims to be.

## 11. `conduct preview` proposes one dispatch and inspects it without executing

```powershell
& $CONDUCT preview --dir $PROJ; "preview exit=$LASTEXITCODE"
& $CONDUCT preview --dir $PROJ --instance ghost; "unknown exit=$LASTEXITCODE"
& $CONDUCT preview --dir $PROJ --adapter codex; "mismatch exit=$LASTEXITCODE"
& $CONDUCT integration-smoke --dir $PROJ; "integration-smoke exit=$LASTEXITCODE"
```

Expect the first `conduct preview` to print a single line of canonical JSON on stdout and
exit 0: one `dispatch` ActionProposal for the `claude-dev` instance, carrying a
`preview_digest` of the form `sha256:` followed by 64 hex digits. It creates a run under
`$PROJ\conductor\runs\preview-run` and proposes against it — and it prepares, executes and
spawns nothing. Run it twice and the line is byte-identical: the preview is deterministic.

Expect the second call to exit 1 with an empty stdout and a stderr line naming `ghost`: the
frozen config declares no such instance, and an unknown instance is refused before any
adapter is touched. Expect the third to exit 1 the same way, its stderr naming `claude-dev`
and `codex`: the caller's adapter is cross-checked against the binding the frozen config
declares, never trusted over it.

Expect `conduct integration-smoke` to complete the fixed synthetic Day-1 loop through the
owned-process adapter and exit 0. It is explicitly not a product Human Confirm surface: its
actor, time, ids and no-op effect are deterministic fixture facts. It opens a run under
`$PROJ\conductor\runs\control-loop-run`, executes and verifies one synthetic dispatch, and
prints a single line of canonical JSON on stdout —
one immutable `ActionResultReceipt` whose `outcome` is `verification_failed`, whose
`exit_code` is `0`, and whose empty evidence list says why: the owned-process adapter
watches a process and holds no independent check of the work, so it exposes no verifier,
and this product never turns an exit code into a success. **`verification_failed` is the
expected pass here.** The exit status to read is the command's own `exit=0`, and the proof
that the loop ran is the durable record it left, not a success token. Run it twice and the
line is byte-identical: the receipt is deterministic, and reopening the run appends nothing.

## Teardown

```powershell
Remove-Item -Recurse -Force $SMOKE
```

The demo's own fixture is a copy in the system temp directory, printed on stderr in step 4;
it is thrown away with the rest of the temp directory and nothing in the package is touched
by any of the above.

## What this procedure does not check

Named so that passing it is not read as more than it is.

- **The wizard.** `conduct init` in a terminal asks three questions, and no scripted procedure
  can answer them — driving a console prompt is not the same act as a person answering one.
  Run it once by hand, with a terminal genuinely attached, and see the three questions and the
  template line that follows your answers.
- **The panel in a browser.** Steps 5 to 7 check what the server sends. Nobody has looked at
  what a browser draws from it, and the live update is checked only as far as the page opening
  an `EventSource`. Open the demo URL, edit a lane file in the printed fixture directory, and
  watch the panel move.
- **The no-terminal default.** Step 8 passes `--template`, which short-circuits before
  `conduct init` consults the terminal at all, so nothing above exercises what init does
  when stdin is a pipe or a CI runner — the path that would hang every runner if it broke.
  It is held by
  `tests/test_init.py::test_init_non_tty_uses_the_default_template_and_never_reads_stdin`,
  and by nothing in this procedure.
- **Ctrl-C.** The steps above stop the servers with `Stop-Process`, which is not the interrupt
  a person sends. Stop one by hand once.
- **Any platform but this one.** Everything above ran on Windows. CI runs the suite and the
  browser gate on Linux, Windows and macOS — nine jobs — but this procedure has been executed
  on Windows only, so what is unchecked here is the procedure, not the suite.
- **A skip that does not name what it could not get.** The mutation-harness suites carry exactly
  two skips and each names its primitive: `tests/test_mutate_harness.py:676` skips under
  `os.geteuid() == 0` saying "root ignores the read-only bit" — the test makes a file read-only
  to prove an unwritable source is an invalid measurement rather than a score, and root defeats
  that premise — and `tests/test_mutate_harness_crash_safety.py:123` skips when directory
  symlinks are unavailable, naming the `OSError` it caught. Recorded here because an earlier
  known-issues entry cited `tests/test_mutate_harness.py:624` as an unnamed skip; line 624 is a
  comment, and the class that entry watched has no instance in these modules.
