# December Command — V1 alpha, release notes (candidate draft, updated 25 September 2026)

Russian version: [release-notes-v1-alpha.ru.md](release-notes-v1-alpha.ru.md).

**Status of this text.** A draft first written on 22 September and brought to the state of candidate frozen-17 on
25 September 2026, from the implementer's checkpoints and the independent review. Every claim below is either
"in the candidate and proven by a named check" or "in the candidate, not yet proven", and the difference is
written out. The owner's own acceptance, a CI run on this candidate and macOS are still outstanding (see Known
limitations); publishing this text as a release before them would be a claim the product has not earned.

## What this is

A local, self-hosted control plane for the AI coding harnesses already working on your code. You describe a
process as a workflow of steps, gates and bounded returns; a run freezes one revision of it against one task and
one team of participants; every action is proposed, confirmed and verified as separate durable facts; a human
decision is a receipt, never a click that vanishes. The distribution is `agent-conductor`, the CLI is `conduct`,
the front door is the Workflow Studio at `http://127.0.0.1:7777/`.

## What the candidate contains

- **Five harnesses** through one reviewed catalogue: Claude Code 2.1.239, Codex 0.112.0, Kimi Code 0.38.0,
  Grok Build 1.0.5 (subscription login in a dedicated native profile) and DeepSeek Harness 0.1.0-rc.7 (API key
  by environment name only). Only Claude Code has run live on this candidate (see *Live runs* below); Codex, Kimi,
  Grok and DSH have not yet run live — their roads were exercised with fake harnesses and, for DSH, a
  synthetic-key probe.
- **Workflow Studio**: five screens (Overview, Workflow, Runs, Decisions, Agents), Russian and English side by
  side with the theme switch, preferences in the URL, drafts that survive reloads and late answers. The scene of a
  run has two lenses, Trace and Orbit, sharing one inspector.
- **Tasks**: durable task identity, the task rail, the newest run per task, a frozen task binding on every run.
- **Five starter workflows** ship, `dalio-v1` … `dalio-v5`; the default is `dalio-v5`, titled *Стандартный цикл*
  (Standard cycle).
- **The standard cycle, revision 5**: goal → identify → diagnose → design → human confirmation → do (with an
  independent checker on a different participant, and, under a bounded Policy grant, one correction of a rejected
  result carrying the original instruction and the checker's exact feedback) → human result gate → bounded return. Older revisions stay
  readable; a plan is immutable once written.
- **Execution authority**: Confirm mode per step; a bounded automatic mode (Policy) with a human preview and a
  separate permission, a recorded authorization history with pause, resume and revoke, and an in-process
  serialization that holds a participant's working tree from its doer through its independent checker to the
  terminal receipt. Once the owner has reviewed the explicit limits and authorized a bounded run, routine steps
  start without per-action confirmation, while human gates still wait for a person. The negative control under
  *Live runs* ran live with Claude under a bounded grant, which carried its correction.
- **Project ownership**: explicit activation (`conduct ownership activate --legacy-writers-stopped`), status,
  rollback and recovery; one owner per project root per process; a second `conduct up` on the same project is
  refused with `owner_busy`.
- **Limits and balance** on the Agents screen: the Claude subscription quota (5-hour and 7-day windows) is read
  live by the product itself, and the observation time is the vendor cache's own. While a step of the project is
  running the reading is not refreshed: it shows *update deferred* with the previous data and its own time.
  Codex (native app-server read), Grok and Kimi report the state `not_authenticated` ("The source did not confirm
  a signed-in account.") in the product's dedicated login
  directories until the owner logs in there; Kimi's usage source is the vendor's own OAuth usage endpoint and
  needs that login. DeepSeek (DSH) shows no data until the owner sets `DEEPSEEK_API_KEY`; its balance road (exact
  decimal amounts, currency and availability as the source reports them) was measured with synthetic keys and a
  local stub only. Only Claude has been read live. An unknown billing account is shown separately and never
  merged; null is never zero.
- **Typed checker feedback and the correction road**: the closed payload format for findings and the durable
  "reject → permitted correction → accept" road are in the candidate, and the road was exercised live in the
  negative control below.
- **Live runs, Claude only.** Claude Code acted as the doer and, in a separate instance (same vendor, same login,
  separate processes), as the independent checker in three runs: the standard cycle (run live-v5-7,
  candidates frozen-12/13); a custom workflow built in the Studio editor (live-v5-10, frozen-15); and a labelled
  negative control on frozen-17 (live-nc-2), where the real checker rejected a known wrong result with typed
  findings, the product carried them into a second attempt under the same bounded grant (at most two attempts),
  and a fresh check accepted the corrected bytes. The gates in these runs were decided by an operator acting for
  the owner, which is not the owner's own acceptance.

## Known limitations of this candidate

Named here so nobody has to discover them. Each is recorded with its evidence in `handoff-v1-studio/`.

1. **Only Claude has run live.** Live runs and live quota readings for Codex, Grok, Kimi and DSH are not yet
   done; whether Kimi's usage source also needs a particular subscription is not yet confirmed live.
2. **No owner acceptance yet.** The gates of the live runs were decided by an operator acting for the owner; the
   owner's personal acceptance is still to come.
3. **Correction delivery is visible only indirectly.** The product keeps no record of a child's stdin by design,
   so the live delivery of the correction data into the second attempt shows only in its effect; the exact bytes
   are covered by native tests.
4. **Platforms.** Windows: a clean-venv install of the package bytes of frozen-17 (a locally rebuilt archive
   whose METADATA/WHEEL/RECORD differ from the candidate archive; the package files are byte-equal) passed
   `init`, `ownership activate`, two server lifetimes each stopped by Ctrl+C, and `closed` ownership. Linux (WSL
   Ubuntu): the same road on the candidate wheel `83dc8d85…` passed, non-root on ext4, two lifetimes stopped by
   SIGINT. Neither configured any vendor account. **macOS is not verified**: the owner has no Mac, and a CI job
   for Linux and macOS is prepared locally but has not run (push not authorized). The CI configuration also runs
   the suite and the browser gate on Linux, Windows and macOS; no CI run exists on the current candidate. The
   process-group cleanup on POSIX has a named gap in the review (a kill after the reap; a descendant that leaves
   the group survives).
5. **Recovery after a real reboot** has not been exercised.
6. **Size bounds.** An independent checker reads each changed file whole up to 32 KiB; its whole frame, the
   stdin channel and the instruction are each bounded at 256 KiB; an input document is at most 48 KiB. Claude
   and Codex receive the task on standard input (256 KiB of UTF-8). Kimi, Grok and DSH receive it on the command
   line: the whole command (pinned paths, flags, quoting, the task with instruction, documents and any
   correction) must fit in 32,767 UTF-16 code units with its NUL, on every platform. A larger task is refused
   before anything is spawned.
7. **A grant binds the provider facts.** The channel, bound, unit and scope above are part of the provider facts
   a bounded grant binds; a grant made before those facts changed is refused at its next action and needs a new
   preview and grant.
8. **Cross-process ownership** covers the doors the implementer listed; shared login-home lifetime, successor
   and descendant lifetime and old-writer transition remain open.
9. **Tests on frozen-17.** The full `tests/` passed (8449 passed, 24 skipped); the browser gates passed 55/55 in
   both module orders on the second run. The first run was red once for ERR_NO_BUFFER_SPACE (Windows 10055, cause
   not measured) and once for four zero-size Overview cards (a test race, since fixed).

## How to install and accept

- Install and first run: [first-run-v1.md](first-run-v1.md) (Russian) / [first-run-v1.en.md](first-run-v1.en.md).
- Owner acceptance of one task, seventeen steps: [owner-acceptance.md](owner-acceptance.md).
- Two tasks with one team, nothing mixed, ten steps: [acceptance-two-tasks.md](acceptance-two-tasks.md) /
  [acceptance-two-tasks.ru.md](acceptance-two-tasks.ru.md).
- Release smoke of the built artifact, twelve steps: [release-smoke.md](release-smoke.md); the scripted installed
  road on Linux and macOS is `scripts/wheel_road.py` (Windows uses the operator's local console-Ctrl+C runner,
  which is not part of the repository).

## What V1 deliberately does not do

More harnesses (Qwen and GLM are parked), an experience ledger or evidence-weighted harness graph,
recommendations among participants, marketplace or cloud work, a general sandbox platform, personal memory.
These are preserved for V2 in [v1-v2-scope.md](v1-v2-scope.md) and were not smuggled into this closeout.
