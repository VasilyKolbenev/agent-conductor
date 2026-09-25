# Release smoke test

What a person runs against a release candidate before publishing it: install it clean, run
every command it ships, and fetch what it serves. Nothing here is automated — the suite
already runs in CI, and this procedure exists to check the things a suite cannot: that the
built artifact installs, that the console script appears on PATH, that the server answers a
real browser request on a real socket, and that it answers on loopback and nowhere else.

**This procedure is a server check, not a product check.** It fetches documents and reads
what came back; it never operates the Workflow Studio, because nothing scriptable can. What a
person must do by hand — open the Studio, publish a workflow, confirm a gate, watch a run — is
`docs/owner-acceptance.md`, and a release needs both, including its real-result exercise.
The current scope and the deferred next-version work are in [V1/V2 scope](v1-v2-scope.md).

Twelve steps, in order. Every one of them names what you must see. A step whose output does not
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
$SMOKE = Join-Path ([System.IO.Path]::GetTempPath()) ("conduct-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $SMOKE | Out-Null
python -m venv "$SMOKE\venv"
$env:PYTHONPATH = ""          # nothing on the path but the installed package
$PY = "$SMOKE\venv\Scripts\python.exe"
$CONDUCT = "$SMOKE\venv\Scripts\conduct.exe"
& $PY -m pip install <the release candidate>
```

For a candidate already published, `<the release candidate>` is the install line from the
README's quickstart. For one that is not published yet, use the wheel built from the exact
candidate SHA, record its filename and hash, and install that wheel — not an editable source
tree or a separately rebuilt revision whose bytes differ from the proposed release.

Expect: the install succeeds, and `& $PY -m pip list` shows the distribution at the version
you are shipping.

## 2. The command exists and lists what it can do

```powershell
& $CONDUCT --help
```

Expect exit 0, and this list of subcommands — no more, no fewer:

```
usage: conduct [-h] {validate,init,doctor,prompt,report,preview,integration-smoke,reconcile,providers,ownership,up,demo} ...
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

## 4. The demo serves, and says what it built

```powershell
$demo = Start-Process -FilePath $CONDUCT -ArgumentList "demo","--port","7801" `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput "$SMOKE\demo-out.txt" -RedirectStandardError "$SMOKE\demo-err.txt"
Start-Sleep -Seconds 3
Get-Content "$SMOKE\demo-out.txt"
Get-Content "$SMOKE\demo-err.txt" -Encoding UTF8    # without it, PowerShell mangles the dash
```

Expect stdout to be the URL alone — it is the command's result and has to survive a pipe:

```
http://127.0.0.1:7801/
```

and stderr to carry **three** lines: the throwaway fixture path, what the demo built on the
command surface, and the lifecycle line. The middle line is the one that says the front door has
something to show — `conduct demo` publishes a workflow revision and opens a run against it, and
a demo that served an empty Studio was the finding that added it:

```
demo fixture materialized in ...\conduct-demo-rup_x8pc (throwaway copy)
demo workflow demo-orbit revision 1, run run-demo-001, gate gate-confirm-do is waiting
serving ...\conduct-demo-rup_x8pc — Ctrl+C to stop
```

The ids are the demo's own and will match what `conduct demo` prints; what must be there is the
line, with a workflow, a revision, a run and a waiting gate named.

## 5. The Studio, the panel and the state document answer

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

## 7. Nothing it serves asks anything of the network

`/` serves the Workflow Studio, which is a shell that loads a directory of ES modules. Fetching
`/` would therefore scan a document with almost no code in it, and fetching a hand-typed list of
module URLs would go stale the first time a module is added — a scan that silently misses a file
is worse than no scan. So scan **the whole panel directory of the installed wheel**, which is
complete by construction and is exactly the bytes the server will hand a browser:

```powershell
$panel = & $PY -c "import conductor, pathlib; print(pathlib.Path(conductor.__file__).parent / 'panel')"
$text = (Get-ChildItem -File $panel | Get-Content -Raw) -join "`n"
"scanned: $((Get-ChildItem -File $panel).Count) files in $panel"
[regex]::Matches($text, 'https?://[^\s"''<>)]+') | ForEach-Object { $_.Value } | Sort-Object -Unique
[regex]::Matches($text, '(?:fetch|EventSource|XMLHttpRequest|WebSocket)\s*\(\s*[^)]{0,40}') |
    ForEach-Object { $_.Value.Trim() } | Sort-Object -Unique
$resource = '(?:\bsrc|\bhref|\bposter)\s*[:=]\s*["'']?[^"''\s>;)]{0,60}' +
            '|@import[^;]{0,60}|@font-face|url\(\s*[^)]{0,60}'
[regex]::Matches($text, $resource) | ForEach-Object { $_.Value.Trim() } | Sort-Object -Unique
```

**Judge the property, not the transcript.** The exact strings move as the Studio grows, so what
you are checking is:

- **the only absolute URL is an XML namespace.** Expect exactly one line,
  `http://www.w3.org/2000/svg` — a namespace is an identifier, not an address, and nothing
  fetches it. Any second absolute URL is a blocker.
- **every network call is same-origin.** Every hit must open with `/`, or with a backtick
  template that does. You will see `EventSource("/events"`, `fetch("/state.json"`,
  `fetch("/harnesses.json"`, `fetch("/command/session"` and several `fetch(path`/`fetch(target`
  calls whose argument is built one line above from a `/command/...` path. A call naming a host
  is a blocker. Hits with no argument at all are prose — these files carry `//:` comment blocks,
  and a sentence about `fetch(` is not a call.
- **every resource is same-origin or a bare `#fragment`.** Expect `/panel/...` paths from the
  Studio shell and `url(#...)` references into the classic panel's own SVG.

The third scan exists because the first two cannot see the spellings this step's own verdict
names. A CDN script tag or a web font can be loaded without a scheme —
`src="//cdn.example.com/x.js"`, `@font-face { src: url(//cdn.example.com/x.woff2) }` — and
neither the absolute-URL scan nor the call scan reports one. A hit naming a host, with a scheme
or without one, is a blocker: this is offline software and a page that reaches out is not.

**If the file count is small, you scanned the wrong directory.** The panel ships tens of files.
A scan that reports three or four has found something other than the installed package, and its
silence means nothing.

This step reads the wheel rather than the socket, deliberately: the server hands a browser these
same bytes, and step 5 has already confirmed the wheel is what is being served. Reading the
directory is the only form of this check that cannot quietly skip a file.

**The one place absolute URLs are legitimate, and the scan above cannot see it.** The panel draws
a "docs" link for each harness in the bundled registry, and those URLs live in
`harnesses.py`, not in `panel/` — the scan shows only `href: h.docs`, a variable. Check them
where they are served:

```powershell
$h = (Invoke-WebRequest -Uri "http://127.0.0.1:7801/harnesses.json" -UseBasicParsing).Content |
     ConvertFrom-Json          # a bare JSON array, one object per harness
$h | ForEach-Object { "$($_.id)  $($_.docs)" }
```

Expect one row per registered harness, and every non-empty `docs` value to begin `https://` and
name that harness's own vendor documentation — `https://docs.claude.com/en/docs/claude-code`,
`https://developers.openai.com/codex/`, and so on. Exactly one row, `custom`, has an empty
`docs`: it stands for a harness this registry has never heard of, and it links to no vendor
because there is none to link to. **Nothing fetches any of them.** They are rendered
as `target="_blank" rel="noreferrer noopener"` anchors, the page drops any value that is not
`https://` before drawing one, and a person clicking one is a person choosing to leave. A value
that is not `https://`, or one pointing somewhere other than that harness's documentation, is a
blocker — this is the only route by which a bundled string becomes something a person can click.

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

Check the ownership state without migrating the release fixture:

```powershell
& $CONDUCT ownership status --dir $PROJ
```

`conduct ownership status` must report the fresh legacy state and exit 0.
Activation for new Studio work is covered by the first-run instructions.

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
    -PassThru -WindowStyle Hidden `
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
& $CONDUCT reconcile --dir $PROJ; "reconcile exit=$LASTEXITCODE"
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

Expect `conduct reconcile` to exit 0 with an empty stdout and one stderr line: `no action
in this project is waiting for reconcile`. That is the answer on a healthy project, and it is
the one you want here — a listed action would mean a run in this fixture was interrupted between
writing an action request and taking its effect lease. When there is one, the command prints
`<run> <action>` on stdout, one line each, and `conduct reconcile --run <RUN> --action <ACTION>`
closes exactly one of them with a terminal `unknown` receipt. It resolves no adapter, starts
nothing, and never reports success; ADR 0002 records why `unknown` is the only honest terminal
for an effect nobody observed.

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

## 12. `conduct providers` refuses to be scripted, and never takes a value

```powershell
& $CONDUCT providers --dir $PROJ; "providers exit=$LASTEXITCODE"
```

Expect exit 1, an empty stdout, and one stderr line: `conduct providers needs a terminal:
every answer is a fact about this machine and none of them has a default.` That refusal IS
the check at this step. Every answer the wizard wants — which harness, where it is on this
disk, which environment variables it may read — is a fact about one machine, and a command
that guessed any of them would write a provider configuration nobody chose.

Run it once by hand in a real terminal to see the rest, because a release nobody has driven
interactively has not been driven. It writes `$PROJ\conductor\providers.json` and, before
writing, prints the availability that pin will resolve to — `availability available` when
both pinned files are there. **A run that ends `available` is the check.** The command used
to report only that it had written the file, which was true and told nobody whether the
result was usable.

How many questions it asks depends on the harness, and that is the point: an
interpreter-backed provider (`deepseek-harness`) is asked for the script its interpreter
runs and will not accept an empty answer, while a single-executable one (`claude-code`,
`codex`, `grok-build`, `kimi-code`) is never asked for an entrypoint at all. **Drive at
least one of each.** Offering the same optional entrypoint to both wrote a config the
server then refused — `executable_absent` for the first shape, `version_mismatch` for the
second — under a message that said the file had been written.

Three things to watch for at the environment question, because they are the reason this
command exists rather than an instruction to open an editor:

- type `ANTHROPIC_API_KEY=sk-something`. It must be refused, naming the VARIABLE and saying
  the value is read from your environment. **No credential value may ever reach that file**,
  and there is nowhere in the dialogue one fits;
- type a bare key-shaped token — `sk-live-anything` — as somebody who misread the question
  would paste one. It must be refused **without repeating the token back**: the refusal says
  which entry it means, never what was in it;
- type `PYTHONPATH` or `LD_PRELOAD`. It must be refused with the reason, at the moment you
  type it — not later, from a harness that would not start.

The protocol is never asked for: it is a fact about the provider that this build already
holds, and a person retyping it could only get it wrong.

## Teardown

Retain the uniquely named `$SMOKE` directory until the evidence has been reviewed. Stop only
the process ids returned above. Then inspect and delete that exact temporary directory with
the file manager if it is no longer needed; never remove another acceptance project or a
repository directory by matching a broad name.

The demo's own fixture is a copy in the system temp directory, printed on stderr in step 4;
it is thrown away with the rest of the temp directory and nothing in the package is touched
by any of the above.

## Known gaps in this release

Product gaps rather than gaps in this procedure, each with what it costs a person. A gap named
here is one somebody will meet; a gap nobody named is one they meet alone.

- **A run cannot name the roles it was opened with.** Materialization substitutes instances for
  roles and only the result becomes durable; the run envelope carries no assignments. **What it
  costs:** on the Agents screen a participant shows its instance, provider and availability, and
  the "Roles it carries" row says the run's plan does not carry roles — which is true. The
  mapping is recoverable by joining the plan's step→instance to the workflow revision's
  step→role, because the frozen configuration names the workflow and revision; this build does
  not perform that join.
- **Four of the six declared capabilities have no provider.** `evidence`, `stop`, `retry` and
  `switch` are part of the deep protocol, but no current catalogue transport supplies them.
  Some transports supply dispatch only; compatible Claude Code/Codex transports also supply
  review and independent verification. **What it costs:** a workflow cannot use those capabilities
  at all, and their argument vocabularies are exercised only by the contract tests and the fake
  harness. `adapters/deep_commands.py` says so at the vocabularies themselves.
- **A plan naming a sandbox route this build cannot provide no longer opens a run.** This is the
  deliberate live-authority tightening. `project-root` is the
  only route this build provides; a step attaching any other `sandbox` row is now refused twice —
  when a run is opened, naming the step and the route (*step 'X' demands sandbox route 'Y' that
  this build does not provide*), and again when an attempt is authorized, for runs that were
  opened before the rule existed. **What it costs:** a workflow drawn against an earlier build
  that named such a route must be edited before a run will open against it — remove or change
  that attachment in the inspector's **Route and policy attachments** and publish a new revision.
  Nothing about the stored document changes: publishing one is still allowed, every shipped
  revision digest is untouched, and a journal already carrying such a route still replays — it
  simply authorizes nothing. **Why it is a gain and not a regression:** the earlier build accepted
  the demand and then ignored it, which told a person their step was contained when it was not.
  Refusing out loud is the point. A person meets this at `docs/owner-acceptance.md` step 10,
  where a run is started; step 8's **Route and policy attachments** row is where the screen
  states the rule before you can trip over it.
- **A run waiting only for a document never ends by itself.** A step whose missing-artifact
  behaviour is `block` keeps its run `open` until the document is published, a standing
  decision is superseded, or a halt lands; this build has no cancel or abandon door. **What it
  costs:** a run seeded against a document nobody will ever publish stays open in the Runs
  list, saying what it waits for, until somebody publishes it on the Runs screen under
  **Publish a document** or removes the project by hand.
- **An attempt that dies unreconciled keeps its run open and its step blocked.** An
  `action_request` with no `action_result` is an attempt in flight: the run stays `open`, the
  step is not offered again, and the Runs screen says so beside the attempt's phase. **What it
  costs:** nothing on screen prompts the operator; `conduct reconcile` is the road that ends it,
  and the run's word moves only after the `unknown` result it writes.
- **A gate whose recorded answers contradict each other accepts nothing through the live
  road.** Two unsuperseded receipts on one gate — which only bytes written around the product
  can produce now — read as `unknown`; the Decisions screen offers no form and the route refuses
  every receipt, because a correction supersedes one receipt and there are two. **What it
  costs:** such a journal is repaired only outside the product.
- **A receipt appended by hand onto a gate the plan has not reached still settles it.** The
  live route refuses that decision; the scheduler, by design, settles a gate from its receipts
  alone, so a journal written around the route keeps its meaning — the shipped demo journal is
  one. **What it costs:** nothing through the screens; a forged journal is a forged journal.
- **Legacy deep proposals need a new preview before a new execution.** Older proposals lack
  the digest-covered `input_binding: "proposal-v1"` marker. Completed journals retain their
  original replay semantics, and exact confirmation retries remain idempotent, but a pending
  unbound proposal cannot start another task. **What it costs:** use Studio's re-propose road,
  inspect the current instruction/input bindings, then explicitly confirm the new proposal.
  Native/process proposals are not reclassified by their argument spelling.
- **Independent verification is bounded, not a hidden unlimited second agent.** Its exact
  first non-empty answer must be `VERDICT: accept` or `VERDICT: reject`; malformed output,
  rejection, timeout or changed work cannot yield success. The frame limit is 256 KiB; changed
  file content is inlined whole up to 32 KiB per file; under confirmation a larger file is
  listed by digest, and a bounded run refuses it before any check. A review
  whose combined input/result does not fit is refused rather than truncated. **What it costs:**
  divide oversized work deliberately, and preserve the failed attempt instead of treating a
  human decision as verification. Each task child gets its own timeout N; 2 × N is the combined
  task allowance, not a total wall-clock deadline including preflights and setup. Restart
  reuses matching evidence if it exists but never spends another checker call automatically.
- **A task's own channel is bounded before its claim.** Claude and Codex read the task on standard
  input: at most 256 KiB of UTF-8. Kimi, Grok and DSH receive it on the command line: the whole
  command — pinned paths, flags, quoting and the task, instruction, input documents and any
  correction included — must fit in 32,767 UTF-16 code units with its terminating NUL, the bound
  Windows measured (one more unit fails with WinError 206). The same rule applies on every
  platform. An input document is at most 48 KiB, so one large document can already fill a
  command-line task. The channel, bound, unit and scope are part of the provider facts a bounded
  grant binds. **What it costs:** a larger task is refused with "the materialized task exceeds the
  bounded task channel" and nothing is spawned; split the input or pick a standard-input doer. A
  grant made before these facts changed is refused at its next action and needs a new preview.
- **The browser gate has failed on this Windows host for two unexplained reasons.** One is
  `ERR_NO_BUFFER_SPACE` (WSAENOBUFS, 10055) while a module loads; which resource runs out is
  not measured, and `TIME_WAIT` counts are an observation, not an established cause. The other,
  separate, was an Overview geometry check reading four zero-size cards: a test race, now fixed,
  in which a re-render landed between finding the cards and measuring them. **What it costs:**
  record the failed command, socket state and exact timeout before any repeat. A green repeat
  alone proves neither a host diagnosis nor that the original failure was harmless; final
  normal and reverse gates must still pass.

## Additional release gates — not filled by the twelve checks above

- Record one exact candidate SHA for complete fast, complete Python 3.11 floor, browser normal
  and reverse, applicable mutation batteries, structural limits, frozen bytes and payload parity.
  Keep full output and exit codes outside the deliverable; a prior SHA's pass is not this SHA's pass.
- Rehearse the real-result exercise in [owner acceptance](owner-acceptance.md), then have the
  owner repeat it. Include a real checker rejecting a known wrong result and accepting the
  corrected one. Record the bounded verdict and artifact/digest, never credentials or raw
  private checker prose. Fake executables and the synthetic `integration-smoke` do not prove
  vendor behavior or useful work.
- Use only explicitly authorized credentials and reviewed installation versions. Missing
  credentials, an installation version mismatch, and an unrun paid check stay separate named
  blockers. Do not extract an unrelated CLI login, weaken a version pin, or substitute a
  final-message file for the required working-tree result.
- After authorized integration/push, require actual green jobs for Linux, Windows and macOS
  on the final candidate. Local workflow structure and a previous run are not remote evidence.
  Publication/tagging and the owner's acceptance remain separate decisions.

### Opt-in real checker probe — a narrower developer gate

`tests/test_command_independent_real_smoke.py` can check a real Claude Code or Codex
installation against both a correct and an incorrect one-file result. Run it from the exact
candidate checkout with that candidate's prepared test interpreter. It creates a synthetic
doer observation and calls the real checker; **it does not run a real doer or the complete
Studio workflow**, and cannot replace the real-result owner exercise.

Only after explicitly authorizing the two checker calls, configure one provider. This example
names an already-set credential; it neither sets nor prints the secret value:

```powershell
$env:CONDUCT_CLAUDE_EXECUTABLE = "C:\absolute\path\to\reviewed\claude.exe"
$env:CONDUCT_CLAUDE_KEY_NAME = "ANTHROPIC_API_KEY"
$env:CONDUCT_CLAUDE_REAL_CHECKER = "1"
try {
    python -m pytest tests/test_command_independent_real_smoke.py -k CLAUDE -q
} finally {
    Remove-Item Env:CONDUCT_CLAUDE_REAL_CHECKER
}
```

For Codex, use `CONDUCT_CODEX_EXECUTABLE`, `CONDUCT_CODEX_KEY_NAME` (normally naming
`OPENAI_API_KEY`), `CONDUCT_CODEX_REAL_CHECKER`, and `-k CODEX`. The executable is the
reviewed native binary, not a shell shim. `CONDUCT_CHECKER_MODEL` optionally selects the
configured model; `CONDUCT_CHECKER_ENV_NAMES` optionally lists additional allowed environment
**names**, comma-separated, such as a deployment endpoint or required Windows bootstrap name.
Do not discover credentials from another CLI login or weaken a failed version pin.

Each selected provider has two cases, each allowing one checker task with a 60-second task
ceiling and 4 KiB capture profile; version preflights and setup add wall time. Expect literal
`VERDICT: accept` for the correct file and `VERDICT: reject` for the wrong one, with the work
tree unchanged and no retained attempt home. Missing opt-in, installation or credential is an
explicit skip, not evidence of vendor behavior. Reports retain only the allowed verdict word,
not arbitrary checker output. Clear the opt-in flag after the probe as above so a later test
run cannot silently repeat these calls.

## What this procedure does not check

Named so that passing it is not read as more than it is.

- **The wizard.** `conduct init` in a terminal asks three questions, and no scripted procedure
  can answer them — driving a console prompt is not the same act as a person answering one.
  Run it once by hand, with a terminal genuinely attached, and see the three questions and the
  template line that follows your answers.
- **Anything in a browser.** Steps 5 to 7 check what the server sends. Nobody has looked at
  what a browser draws from it, and the live update is checked only as far as the page opening
  an `EventSource`. For the classic panel: open `/panel/index.html`, edit a lane file in the
  printed fixture directory, and watch it move. For the Workflow Studio, which is what `/`
  serves and where every write in this product is made, this procedure checks nothing at all —
  no step here opens a screen, publishes a revision, confirms a gate or reads a receipt. That
  is `docs/owner-acceptance.md`, seventeen steps, done by a person.
- **Every `/command/*` route.** The Studio's whole API — proposals, action requests, decisions,
  drafts, revisions, the run journal, the scheduler's readings — is untouched above. Steps 5
  to 7 fetch `/`, `/state.json`, `/handoff/claude.md` and the panel's static files, and nothing
  else. A release candidate that served those four perfectly and refused every write would pass
  this procedure.
- **The no-terminal default.** Step 8 passes `--template`, which short-circuits before
  `conduct init` consults the terminal at all, so nothing above exercises what init does
  when stdin is a pipe or a CI runner — the path that would hang every runner if it broke.
  It is held by
  `tests/test_init.py::test_init_non_tty_uses_the_default_template_and_never_reads_stdin`,
  and by nothing in this procedure.
- **Ctrl-C.** The steps above stop the servers with `Stop-Process`, which is not the interrupt
  a person sends. Stop one by hand once.
- **Any platform but this one.** Everything above ran on Windows. The CI configuration runs the
  suite and the browser gate on Linux, Windows and macOS (nine jobs), builds one wheel, and walks
  the installed-wheel road (`scripts/wheel_road.py`: a clean venv, init, ownership activate, two
  `conduct up` lifetimes stopped by SIGINT, `closed`) on Linux and macOS. A configuration is not
  evidence: no CI run exists on the current candidate. The installed road has been walked locally
  on Windows and on Linux (WSL); macOS has not been walked at all yet.
- **A skip that does not name what it could not get.** The mutation-harness suites carry exactly
  two skips and each names its primitive: `tests/test_mutate_harness.py:676` skips under
  `os.geteuid() == 0` saying "root ignores the read-only bit" — the test makes a file read-only
  to prove an unwritable source is an invalid measurement rather than a score, and root defeats
  that premise — and `tests/test_mutate_harness_crash_safety.py:123` skips when directory
  symlinks are unavailable, naming the `OSError` it caught. Recorded here because an earlier
  known-issues entry cited `tests/test_mutate_harness.py:624` as an unnamed skip; line 624 is a
  comment, and the class that entry watched has no instance in these modules.
