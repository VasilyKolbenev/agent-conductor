# Owner acceptance — can a person operate this without a developer?

`docs/release-smoke.md` asks whether the artifact installs and answers. This asks a different
question, and it is the one that decides an alpha: **can somebody who did not build this open it
and get work done?**

Fifteen steps. Every one names what you must be able to see or do **without opening a terminal
log, reading source, or asking the person who wrote it**. A step you cannot complete from the
screen alone is a finding, and the finding is the product's, not yours.

You do not edit a file by hand at any point after step 2. If you find yourself reaching for an
editor, stop and write down which step sent you there.

**Shell.** Windows PowerShell below, because that is where this was written. The `conduct`
commands are identical on every platform.

---

## 1. Install a clean wheel

```powershell
$ACC = "$env:TEMP\conduct-acceptance"
Remove-Item -Recurse -Force $ACC -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $ACC | Out-Null
python -m venv "$ACC\venv"
$env:PYTHONPATH = ""
$PY = "$ACC\venv\Scripts\python.exe"
$CONDUCT = "$ACC\venv\Scripts\conduct.exe"
& $PY -m pip install <the release candidate>
& $CONDUCT --help
```

**You must see** the ten subcommands and no traceback. Nothing on `PYTHONPATH`: an editable
working tree would answer every command below and prove nothing.

## 2. Create a project

```powershell
$PROJ = "$ACC\project"
New-Item -ItemType Directory -Force -Path $PROJ | Out-Null
& $CONDUCT init --template default-orbit --dir $PROJ
```

**You must see** the bootstrap prompt on stdout and a new `conductor/` directory. This is the
only step that writes a file for you, and the last time you touch the filesystem by hand.

## 3. Open the application

```powershell
Start-Process -FilePath $CONDUCT -ArgumentList @("up","--dir",$PROJ,"--port","7801")
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:7801/"
```

**You must see** the Workflow Studio: a project name, a connection state, and five screens —
Overview, Workflow, Runs, Decisions, Agents. **Overview must answer, without you clicking
anything:** what this project is, whether it is ready to run, what is blocked, what needs you,
the most recent run, and a route to the thing that is blocking.

On a brand-new project most of those answers are "nothing yet". That is a legitimate answer and
the screen must say it in words. A blank area is a finding. A spinner with no exit is a finding.

## 4. Create a workflow, from blank or from a template

Go to **Workflow**. Create one, either empty or from a bundled starting point (the Dalio
five-step cycle ships with the product and needs no network).

**You must be able to tell**, from the screen: which workflow you are editing, whether what you
are looking at is the published revision or your unsaved draft, and what stops it being
publishable right now.

## 5. Add and connect steps

Add at least two steps and connect them. Then do the same thing **without the pointer** — the
canvas must be operable from the keyboard, and every operation must also exist in the inspector.

**You must be able to** pan, zoom, select a step, select a connection, move a step, delete one,
and duplicate one. A step you cannot reach with the Tab key is a finding.

## 6. Assign an implementer and a reviewer

Select a step and use the inspector's **Assignment** section to give it a role, and give a second
step a reviewing role.

**Note what a workflow may and may not say.** A workflow names *roles*. It never names a
provider, a model or a run — those are bound when a run starts, which is what lets the same
workflow run against different harnesses. The inspector shows the deployment facts as read-only
context and says where each one comes from.

## 7. Choose the harness, provider and model

Go to **Agents**.

On a fresh machine you will see the providers this build knows about, each marked
**unconfigured** — the product ships no credentials and discovers nothing. The screen must tell
you exactly what to do about that: which file to write (`conductor/providers.json`), which keys
it takes, and that it is read at startup.

**This is the one place the script sends you back to a file**, and it is deliberate: a provider
pins an absolute executable path on your machine, and no browser should be able to write one.
Write it, restart `conduct up`, and the same screen must now show that provider as available.

If you have no harness installed, stop here and record that. Steps 8-13 need one.

## 8. Configure execution, artifacts and verification

Back in **Workflow**, walk the inspector's six sections for a step: General, Assignment,
Execution, Inputs and outputs, Verification, Transitions.

**Every field must do one of two things**: be validated, saved, read back and used by the
product — or say plainly that this harness does not support it. A control that looks editable
and changes nothing is a finding. A field that disappears without explanation is a finding.
Several fields in this release honestly say they are unsupported, and each says where the fact
actually lives instead. That is the intended behaviour; a silent one is not.

## 9. Validate and publish a revision

Use **Validate**, then **Publish**.

**You must see**, before you confirm: what changed, and which revision number you are about to
create. A refusal must say what is wrong in words you can act on, and must leave the published
revisions untouched.

Publish a second time with no changes. **You must see** that nothing new was created, rather than
a silent second revision.

## 10. Start a run against that exact revision

Start a run from the workflow you just published, binding each role to a participant.

**You must be able to see** which revision the run is following. A run freezes the plan it
starts with: editing the workflow afterwards must not change what that run is doing.

## 11. Inspect the run's real durable timeline

Go to **Runs** and open it.

**You must see** the run id and its revision, the mode, the assigned harness/provider/model,
where it is now, the outcome, the verification result, any artifacts and evidence, and a
chronological timeline of what actually happened:

```
action_proposal -> action_request -> effect_lease -> execution_observed -> action_result
```

Each row names the durable record it came from. **If you see `verification_failed`, read what the
screen says about it**: a process that exits 0 has finished, which is not the same as having been
verified. If that sentence is not on the screen, that is a finding — it is the single most
confusing thing this product can show you.

## 12. Submit a human decision

Go to **Decisions**.

**You must see**, for each waiting decision: why a human is needed, which step and run it affects,
what your choices are, and what each choice causes. Submit one.

**You must then see** a durable receipt, and what became runnable as a result. A decision that
vanishes without a receipt is a finding.

## 13. Modify the workflow and publish another immutable revision

Go back to **Workflow**, change something, and publish again.

**You must see** revision 2 (or 3) created, revision 1 unchanged, and the run from step 10 still
following the revision it started with.

## 14. Reload and reconnect

Reload the page. Then stop `conduct up`, watch the screen, and start it again.

**You must see**: the same published revision and the same draft after a reload — the draft is
stored on the server, not in your browser; an honest disconnected state while the server is
down, with write controls disabled rather than failing silently; and everything back after it
returns, without losing work you had not saved.

```powershell
Get-Process conduct -ErrorAction SilentlyContinue | Stop-Process -Force
```

## 15. Understand every failure without opening a terminal log

Cause a failure on purpose — name a provider that is not configured, publish an invalid
workflow, or point a step at a step you deleted.

**You must be able to say, from the screen alone**: what was refused, why, and what to do next.

---

## The verdict

You are answering one question: **could you have done all of this without the person who wrote
it?** Write down every step where the answer was no, and what you had to do instead. Those are
the alpha's real findings; everything else is polish.

## What this script deliberately does not cover

- Anything a credential would be needed for beyond step 7 — that is the operator's own machine.
- Cross-platform behaviour. This is one machine; CI covers Linux, Windows and macOS.
- Whether a real harness does good work. This checks that you can *drive* it, see what it did,
  and decide — not that the model was any good.
