# Owner acceptance — can a person operate this without a developer?

`docs/release-smoke.md` asks whether the artifact installs and answers. This asks a different
question, and it is the one that decides an alpha: **can somebody who did not build this open it
and get work done?**

Seventeen steps. Every one names what you must be able to see or do **without opening a terminal
log, reading source, or asking the person who wrote it**. A step you cannot complete from the
screen alone is a finding, and the finding is the product's, not yours.

**You do not open a text editor at any point in this script.** There is no exception: step 7
used to send you to `conductor/providers.json` and called that deliberate, which was an honest
description of a gap rather than a design. If you find yourself reaching for an editor, stop and
write down which step sent you there — that is the finding this line exists to catch.

**Where this script types at a shell, it is running a `conduct` command or calling the product's
own HTTP API** — never editing a file, never reading a log to find out what happened. Step 12 is
the one place it calls the API directly, and it says why that is itself a finding.

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

**You must see** the eleven subcommands and no traceback. Nothing on `PYTHONPATH`: an editable
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

## 4. Create a workflow, from blank or from a starting point

Go to **Workflow**. Create one, either empty or from a bundled starting point (the Dalio
five-step cycle ships with the product and needs no network).

**Three starters ship, and they must not look alike.** Each row names its revision and says
either *ready to run* or *see the note*; the note itself is the readable text under the control,
for the starter you have chosen, and it changes with your choice. One note says that four of
that starter's review steps name no result artifact, so those steps cannot succeed. One starter
draws the routed cycle: its connections carry conditions, so approving the confirm gate opens
the effecting step and asking for changes at the result gate sends the run round again. If the
rows read identically you cannot choose between them, and that is a finding — they are not
equal choices.

**The screen fits an ordinary window.** At 1280 px wide nothing scrolls sideways — not even with
a workflow id of 128 characters chosen — and the canvas begins within the first screen. *Start
a new workflow* and *Open a run* each sit behind a fold whose heading says what it holds and
where that stands (*Open a run — choose or start a workflow first*, *— publish a revision first*,
*— revision 1 is published*); the start box is open while no workflow is chosen, the run box
while a revision is published and you are not editing a draft, and either opens with a click or
with Tab and Enter. The open run box costs height (the canvas begins lower while it is open; fold
it to get the height back), and a fold you opened or closed by hand stays that way through the
frames that arrive, as does anything typed into it. A page that scrolls sideways, a fold whose
heading does not say what is inside, or a fold that closes by itself, is a finding.

**The workflow you just named must be the one the picker says is chosen**, immediately, without
a save and without a reload. A picker that falls back to "choose a workflow" while you are
looking at that workflow's drawing is a finding.

**You must be able to tell**, from the screen: which workflow you are editing, whether what you
are looking at is the published revision or your unsaved draft, and what stops it being
publishable right now.

## 5. Add and connect steps

Add at least two steps and connect them. Then do the same thing **without the pointer** — the
canvas must be operable from the keyboard, and every operation must also exist in the inspector.

**You must be able to** pan, zoom, select a step, select a connection, move a step, delete one,
and duplicate one. A step you cannot reach with the Tab key is a finding.

**Place a step three ways, and satisfy yourself they are one operation.** Drag one. Move another
with Alt and an arrow. Type a coordinate pair into the inspector's **General** section for a
third — a position the canvas alone can set is exactly the pointer-only affordance this step is
looking for. Then use **Let the canvas place it** to hand one back to the automatic layout: if
placing a step is a door that only opens one way, that is a finding.

Where you put a step is stored in the workflow document, and step 16 asks you to confirm it came
back. It is **not** execution semantics: a run's frozen plan carries no coordinate at all, so
rearranging a drawing can never change what a run does.

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
you exactly what to do about it, and what it must name is a COMMAND:

```powershell
& $CONDUCT providers --dir $PROJ
```

It asks which harness you have, where it is on this disk, and which environment variables it
may read. Whether it asks a fourth question — the entrypoint — depends on the harness, and it
must not ask you to choose: `deepseek-harness` runs through an interpreter, so it asks for the
script that interpreter runs and will not take an empty answer; the others are a single
executable, so no entrypoint is asked for and the screen says why.

Then it shows you what it will write, **including the availability that pin will resolve to**,
and asks before writing it. If it says `availability available`, restarting `conduct up` must
show that provider as available. If it says anything else, it names the file that is missing.
A wizard that reported only "wrote providers.json" is what this replaced.

**Three things you must try, because they are the reason this is a command and not an editor:**

- at the environment question, type a credential the way somebody in a hurry would paste one:
  `ANTHROPIC_API_KEY=sk-something`. It must refuse, name the VARIABLE, and say the value is
  read from your environment when a step runs. **No credential value may reach that file.**
- then type a bare key-shaped token on its own — `sk-live-anything`, with no `NAME=` in front,
  which is what a paste into the wrong question actually looks like. It must refuse **and the
  token must not appear in the refusal**. Your terminal will have drawn what you typed, and
  the command says so up front; what it controls is whether it repeats it.
- type `PYTHONPATH`, or `LD_PRELOAD`. It must refuse with the reason, while you are typing it.
  A name like that chooses code to load into the harness before its own first instruction, and
  a refusal that arrived later would arrive as a harness that simply would not start.

It never asks for the protocol. That is a fact about the provider this build already holds, and
retyping it could only introduce an error.

The browser writes none of this: a provider pins an absolute path on your machine, and the
reviewed position is that no browser should be able to write one. The command is how that
position stops costing you a text editor.

Restart `conduct up`, and the same Agents screen must now show that provider as **available** —
providers are read once at startup, and the command says so when it finishes.

If you have no harness installed, stop here and record that. Steps 8-15 need one.

## 8. Walk every field of the inspector

Back in **Workflow**, walk the inspector's six sections for a step: General, Assignment,
Execution, Inputs and outputs, Verification, Transitions.

**The rule for this step is absolute: every field either writes something the product reads
back and acts on, or states a fact with the document it was read from named beside it. There is
no third kind.** Nothing in this release says "not supported by this harness". If you find such
a row, that is a finding — the register of unsupported labels reached zero, and a new one may
only appear as a deliberate report.

For each field below: **edit it, save the draft, reload the page, and see it come back.** Where
the third column names a consumption, that is what you must also be able to see happen.

| Field | Section | What you must see |
| --- | --- | --- |
| **Purpose** | General | Free text, saved and read back. It travels INSIDE the step's payload when the step runs, so a harness is told why the plan says this step exists. |
| **Position** | General | A coordinate pair you can type, and **Let the canvas place it** to hand it back. Step 16 checks it survived. |
| **Timeout** | Execution | Seconds, refused outside the contract's bounds with the bound named. It becomes the attempt's own ceiling. |
| **Attempt bound** | Execution | A count. When a step has spent it, the Runs screen says so in words — *Every attempt this plan allows the step has been authorized, so it can never settle again.* — and offers no button the runtime would refuse. While an attempt is executing the same screen says the attempt is in flight and offers the step no second control: a bound of two never means two at once. |
| **Output budget** | Execution | A chosen profile, with the byte ceiling it resolves to stated beside it. The window states the number rather than implying one. |
| **Route and policy attachments** | Execution | `sandbox: project-root` is a demand on the machine that runs the step, and the screen says exactly what it buys: the route a child will run on is walked from the project root and refused if it leaves — a symlink, a junction, a reparse point, a hard link, a `..` segment, or anything not strictly beneath the root. **It must also say what it is not:** not operating-system isolation, no privilege drop, no filesystem jail, and the check reads the route at the instant it walks it. A step demanding any other route is refused before anything is spawned — **when the run is opened, and again when an attempt is authorized**, and the screen must say both. That refusal is new in this release: a workflow drawn against an earlier build that names another route still publishes, and no longer opens a run, until you change this row. The other five kinds — model, tool, skill, session, filesystem — are recorded and the screen says this build does nothing else with them. |
| **Required input artifacts** | Inputs and outputs | Add and remove references. The control writes the argument the reviewed schema marks, and refuses a malformed reference rather than posting it. |
| **Produced artifacts** | Inputs and outputs | The reference this step publishes, editable where the schema declares one, and the cost of clearing it stated. |
| **Handoff mapping** | Inputs and outputs | Derived from the document: for each required reference, which step produces it — or that nobody does. Both arms must appear on one document. |
| **Missing-artifact behaviour** | Inputs and outputs | A choice of two, both fail-closed. **fail** (which is also what saying nothing means): the step is offered, reached, and refused when the input cannot be resolved — no task spawned. **block**: the step is never offered while the artifact is absent. Step 12 makes you watch a `block` wait and end it. |
| **Verifier** | Verification | A role. Naming one means evidence from the doer is refused; naming none means the doer answers. |
| **Evidence requirements** | Verification | `digest`, and only ever a tightening — the control offers no word that would ask for less. |
| **Success criteria** | Verification | **Read-only, and there is no field to edit.** Sentences the server derived from the rules that really operate, each beside the layer that enforces it: the result must be verified; who may answer for it, named out of the plan; for a review, the result artifact that must stand and answer its request; and the digest when the step demands one. **No sentence may say "signed" or "signature"** — there is no cryptographic signature anywhere in this product, and a screen implying one is a finding. |
| **Verification failure policy** | Verification | `halt the run`. It is a tightening and not routing: it says nothing further may be authorized in this run at all, including branches no road from the failing step could reach. |
| **Human decision** | Transitions | A gate id, and — on a gate — **Require explicit human approval — waiver disabled**. Step 14 makes you meet what it removes. |
| **Decision routing** | Transitions | Read-only: where each answer sends the run, derived from the roads already drawn. A gate whose every answer opens the same step says so; a step that is not a gate says so. |
| **Edge conditions** | Transitions | On each road out of a step, the words that step's own kind can produce — and none at all for a step that carries out no work, because the contract refuses a condition there. |
| **Loop target and bound** | Transitions | A loop names where it reopens and how many passes at most. |

**Two consumptions you must provoke here, not merely read about.**

- Give an effecting step an **attempt bound lower than the bound of a loop that contains it**,
  then publish. **You must see** the warning, in these words: *Attempt bound may be exhausted
  before the loop's final pass.* It must **not** refuse the publish — the document is legal and
  the judgement is yours. A refusal here is a finding, and so is silence.
- Put **`on_waived`** on a road out of a gate that requires explicit human approval. **You must
  see** the publish refused, because that gate can never produce that word: the road is one no
  run could travel.

## 9. Validate and publish a revision

Use **Validate**, then **Publish**.

**You must see**, before you confirm: what changed, and which revision number you are about to
create. A refusal must say what is wrong in words you can act on, and must leave the published
revisions untouched.

Publish a second time with no changes. **You must see** that nothing new was created, rather than
a silent second revision.

## 10. Start a run against that exact revision

Start a run from the workflow you just published, choosing the authority **confirm** and
binding each role to a participant. The form starts at *observe*, which proposes nothing and
runs nothing; every step of this script from 13 on needs *confirm*, and a run opened at the
default meets the sentence *This run's authority is observe* on every row instead of a control.

**You must be able to see** which revision the run is following. A run freezes the plan it
starts with: editing the workflow afterwards must not change what that run is doing.

**If you are opening a run against a workflow drawn on an earlier build, this is where it can
be refused.** A step attaching a `sandbox` route other than `project-root` is refused here,
naming the step and the route. That is the intended answer, not a defect: the earlier build
accepted such a demand and then ignored it. Go back to that step's **Route and policy
attachments** (step 8), remove or change the row, publish a new revision, and open the run
against that one. **You must see the refusal name the step and the route** — a refusal that
does not tell you which row to change is itself a finding.

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

## 12. Watch a step wait for a document, and end the wait

Give a step **`block`** as its missing-artifact behaviour, requiring a reference nothing in the
run has published — `artifact-brief` — then publish and start a run.

**You must see**, on the Runs screen, that step held back with a **Waiting for artifact** row
naming `artifact-brief`, and a sentence saying it is not offered until that artifact exists.
It must **not** say it is waiting on a predecessor step, and it must not show an empty "Waiting
on" line. Nothing has been attempted for it, and nothing has failed.

Now publish the artifact, from the same screen. Under **Publish a document**, below the
positions, choose `artifact-brief` as the reference — the list offers only the references this
run's plan reads, and nothing there is typed but the document itself. **You must see** the
document id minted from the reference (`artifact-brief-0`, then `-1` for the next one), the kind
of text as a closed choice, and the size counted in bytes as you type, against the bound the
server holds it to. Write a brief and press **Publish this document**.

**You must then see**, without reloading anything by hand, the waiting sentence disappear, the
step become available, and the document listed under **Artifacts**. If you have to reload to see
it, record that. A document is immutable: publishing another under the same reference stands it
beside the first, and whatever is proposed afterwards binds the newest one standing.

## 13. Drive the cycle and read the plan's own word

Use the routed starter (`dalio-v3`) for this step, because its roads carry conditions.

**First pass, approve.** Answer the confirm gate `approve`. Then go to **Runs** and open the
run: the `do` row now reads `plan: runnable` and offers **Propose this step**. Before you press
it, publish the instruction this step runs: under **Publish a document**, choose
`instruction-plan` — the starter's own reference, for which `conduct init` writes no file — and
write what the step is to do. **You must see** the Propose form say which instruction a proposal
made now would bind: *durable document `instruction-plan-0`*, its size and when it was written;
before you published it, the same row must have said *no durable document* and named the file
the machine would read instead. Press **Propose this step**. **You must see** the facts the
proposal will carry — instance, capability, arguments, timeout, attempt id — drawn from the
frozen plan and not from anything you can type; the only fields you fill are who proposes and
why. Send it, and **you must see** the row read `proposed` and offer **Confirm this proposal**,
with the proposal's own id and digest beside it — and the instruction it bound, *the one
standing when this proposal was written*. Publish a second `instruction-plan` now: **you must
see** the Confirm form keep naming `instruction-plan-0`, because a source is bound when it is
confirmed and never chosen again at execution; a Confirm form that switched to the newer
document is a finding. Give your name and confirm. **You must then see**, without reloading, the timeline grow on its own —
`action_request → effect_lease → execution_observed → action_result` — and, while the attempt
runs, the row say *An attempt on this step is still in flight; the plan offers it again only
after that attempt answers.* with no second control. Nothing runs by itself: a step that is
never proposed and confirmed never runs, and a run that starts work without those two clicks
is a finding. When the result lands, answer the result gate `approve`. **You must see** the
run reach **Plan: complete** — and beside it the two facts that tell you what "complete"
means: the last gate answer and the last outcome.

**"Complete" must never be drawn as a success.** It is the neutral chip, the same one a run that
exhausted every retry reaches, and the screen must say so. A green tick on that word is a
finding.

**Second pass, send it back.** Start another run and answer the result gate `request_changes`
three times, driving the body round between answers the same way. **You must see** the loop
reopen twice and the third answer end it, with the loop's position and its ceiling both on
screen. From the second answer on, the Decisions screen must say that answering again
supersedes the receipt standing on that gate, and name it — a second answer that is written
beside the first rather than in its place leaves the gate reading `unknown`, and that is a
finding. A run that reopens forever, or a screen that shows a position without its ceiling,
is a finding.

## 14. Submit a human decision, and meet a gate that refuses one

Go to **Decisions**.

**You must see**, for each waiting decision: why a human is needed, which step and run it affects,
what your choices are, and what each choice causes. Submit one.

**A gate the plan has not reached offers no form.** Choose the confirm gate of a run whose
earlier steps have not settled. **You must see** no submit control at all, the sentence *This
gate cannot be answered yet. ALL incoming roads must open before this step may run.*, and
*Waiting on:* followed by the names of the steps it is waiting on. A form offered there is a finding: its only possible
outcome is a refusal, and a build that accepted the answer would let the step behind the gate
run before the steps in front of it.

**You must then see** a durable receipt, and what became runnable as a result. A decision that
vanishes without a receipt is a finding. **Read the receipt again after the screen has re-read
the run** — choose the gate a second time, and the receipt's own id, the actor and the immutability
sentence must all still be there. A receipt that survives only until the next refresh is a
finding.

Now open a gate whose plan says **Require explicit human approval**. **You must see** that
`waive` is not offered at all, with the reason on screen — and that `approve`, `reject` and
`request_changes` are all still offered. This makes a gate harder to pass and never harder to
fail; if the other answers disappeared too, that is a finding.

## 15. Modify the workflow and publish another immutable revision

Go back to **Workflow**. **Use Edit to start a new draft from the published revision** — a
published revision is immutable and its controls are shut, so the way to change it is to draw a
new draft on top of it. Change something and publish again.

**You must see** revision 2 created, revision 1 unchanged, the diff before you confirm, and the
run from step 10 still following the revision it started with.

## 16. Reload and reconnect

Reload the page. Then stop `conduct up`, watch the screen, and start it again.

**You must see**: the same published revision and the same draft after a reload — the draft is
stored on the server, not in your browser; **every step you moved still where you left it**, for
the same reason; an honest disconnected state while the server is down, with write controls
disabled rather than failing silently; and everything back after it returns, without losing work
you had not saved.

**While it is down, put your cursor in a text field and leave it there.** When the connection
returns, the controls must come back without throwing you out of the field you were typing in,
and without moving your cursor to the end of what you had typed.

```powershell
Get-Process conduct -ErrorAction SilentlyContinue | Stop-Process -Force
```

## 17. Understand every failure without opening a terminal log

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
