# Plan — the P0 control loop and the December visual system

- **Status:** Plan — coordination document, not a specification
- **Date:** 2026-08-03
- **Branch:** `feature/p0-control-loop`
- **Contracts:** `spec/PROTOCOL.md` (Protocol v1, normative) and
  `docs/adr/0001-harness-control-plane-model.md` (accepted model) remain the only binding
  documents. Nothing here changes either of them.
- **Public direction:** `docs/specs/2026-08-03-product-direction.md`
- **Precedent:** `docs/plans/2026-07-30-m1-m4-implementation.md`

The M1–M4 chunk had a written plan, and every task in it could be picked up and executed
without asking anyone a question. This chunk — the P0 control loop plus the December visual
system — has been driven from conversation instead. This document closes that gap. It
records what has shipped, what is queued and in what order, what each queued slice owes, what
the owner has decided and when, and which questions are still the owner's to answer. It does not
specify implementations: where a rule is normative the authority is `spec/PROTOCOL.md`, and
where the model is at stake it is ADR 0001.

Every claim below about current behaviour was checked against the code on this branch. Where
the conversation and the code disagreed, the code won and the disagreement is written down.

## 1. Brand and vocabulary

The public brand is **December**. Tagline: *"Build your Orbit. Control the cycle."* December
is a self-hosted control plane for individually assembled AI-harness work cycles.

| Term | Meaning |
|---|---|
| **December** | The brand and the product. |
| **Orbit** | An individually assembled work cycle. |
| **Harness** | An execution environment (Claude Code, Codex, Cursor, a custom adapter). |
| **Node** | A role or a step inside a stage. |
| **Gate** | A transition condition, or a human decision. |
| **Run** | One pass through an Orbit. |

The Python package stays `agent-conductor` and the CLI stays `conduct`, deliberately, for now.
A rename touches `pyproject.toml`, the entry point, every doc and the demo output; folded into a
UI slice it would make both unreviewable. It is a separate atomic PR, and it lands **before** any
PyPI publish — the name is cheap to change while nobody depends on it, expensive afterwards.

The tagline belongs in the README, in onboarding, and in empty states — not on the working
dashboard, where a person is mid-task and a slogan above their queue is noise.

## 2. Status — what has shipped on this branch

Base for this chunk is `c2c79cd` (the M1–M4 tip).

| Slice | Commits | What landed |
|---|---|---|
| **S1** project status and next action | `125d9f7` `55da0fa` `8c62473` | `project_status` and `next_action` in `state.json` §6.1 — a strict precedence ladder, one imperative sentence, ordering pinned by tests. |
| **DO-1** public product direction | `ba3b736` | `docs/specs/2026-08-03-product-direction.md` — five stages, eight product laws, the Orbit/Stage/Node/Harness/Gate/Run levels. |
| **DO-1b** optional `role.stage` | `49c301f` `688878b` `9009d75` `57266ef` | `cycle.roles[].stage` in Protocol v1 as presentation metadata, projected only when declared; additivity proven on both branches. |
| **DO-2** Default Orbit template and stage-aware prompts | `b9ff514` `db88fdd` `df70fcb` | The `default-orbit` template (five phases, five staged roles), `prompts._STAGE_CONTRACTS`, and the vacuous `agreed` state disclosed. |
| **DO-3/S4** guided init | `2f4aabf` | `conduct init` wizard, three vended templates, deterministic `--template`, scaffold-then-validate, printed next steps. |

**DO-3/S4's spec review has since passed.** Eighteen shell probes ran with no hang; the
AST-based ban on probing the machine for installed harnesses was verified by sabotage and
confirmed at runtime with an audit hook; the input allowlist and the validate-before-write order
are pinned by tests. The slice is off the queue — the head is now DO-4, which carries the one
requirement the review left behind (§3).

### Gate numbers

Re-measured 2026-08-03 on an isolated export of `bf0ab3b` — docs-only above `2f4aabf`, so the
code under test is identical — which keeps the agents working in this tree undisturbed and their
uncommitted work out of the result. Both numbers are unchanged:

| Gate | Command | Result |
|---|---|---|
| Test suite | `.venv\Scripts\python -m pytest -q` | **495 passed** |
| Mutation harness | `.venv\Scripts\python scripts\mutate_merge.py` | **13/13 mutations killed** |

Never `uv run` — the lockfile is not the environment these gates are pinned against.

## 3. The queue

The owner's approved order, reconciled with the December UI slices. Two reconciliations matter,
because the two lists were written separately and overlap:

- **DEC-UI-2 supersedes what was previously listed as DO-5/S2** (Orbit presentation). One slice,
  not two; the DO-5/S2 label is retired.
- **DEC-UI-3 covers the panel half of DO-4's branding.** DO-4 ships the registry *data* and its
  Python surface; DEC-UI-3 renders it. Neither is run twice.

```
DO-4     harness registry
DEC-UI-1 brand foundation
DEC-UI-2 Orbit presentation     (owner checkpoint before implementation)
DEC-UI-3 harness identity
DEC-UI-4 motion and polish
S5       conduct report
S7       conduct doctor
DO-6/S3+S6 harness drawer and handoff
DO-7     verification and documentation
```

### DO-4 — harness registry

The bundled known-harness registry from ADR 0001 §6: harness type id, display name, monogram,
light/dark accent, documentation URL, adapter id, plus a deterministic fallback for unknown
types. Data only — no protocol key is added and no merge rule reads it.

- Files: a new module under `src/conductor/` (registry data + lookup), `tests/`.
- Starter set `CC` Claude Code, `CX` Codex, `CU` Cursor, `WS` Windsurf; no official logos
  without license verification.
- Precedence per ADR 0001 §6: project/user override → adapter manifest → bundled registry →
  deterministic custom fallback. Only the last two exist in this slice.
- **Carried from the DO-3/S4 review:** the AST ban on machine probing parses the source of
  `conductor.__main__` and `conductor.templates` only, while `__main__` imports
  `conductor.demo` (which imports `shutil`) and `conductor.server` (which imports `os`). A
  `shutil.which` planted in either of those and called from `init` would not be caught today.
  DO-4 must widen the ban to the modules the init path actually reaches, because DO-4 — a
  registry of known harnesses — is where the temptation to detect the installed ones is highest.
- Acceptance: `state.json` is byte-identical before and after for every existing fixture; an
  unknown harness string yields a stable monogram and accent from the string alone; the widened
  ban is verified by the same sabotage method as the original; the mutation harness and the
  suite stay green.

### DEC-UI-1 — brand foundation

The December palette, the mark, the wordmark and the brand shell, as one token layer the later
UI slices consume. No layout is redesigned here.

- Files: `src/conductor/panel/index.html`, `tests/test_panel_smoke.py`, `README.md` (tagline).
- Palette lives once in `:root` (§4). Today's accent is teal (`--accent:#33b3a4` dark,
  `#00857a` light); December Red replaces it in the reserved roles only.
- Today's `--fail` is `#e0645c`, close enough to December Red `#E44955` that the two would read
  alike at a glance. Moving failure away from red-adjacent, or separating the two by weight and
  glyph, is this slice's job — §4 forbids the current state and a failure from looking alike.
- The light theme stays (`@media (prefers-color-scheme:light)`), on the approved
  *winter-daylight* palette — decision §8.3, 2026-08-03. Its token values are **outstanding**:
  the table in §8.3 is the coordinator's proposal awaiting the owner's sign-off, and this slice
  may not ship it as though it were approved.
- A constraint on this slice, not an opinion: December Red at `#E44955` on a light background
  falls below the 4.5:1 contrast ratio required for normal text, so the light theme needs a
  darkened variant of the brand red for text and small elements.
- The document title already follows the target pattern — `document.title = "Conduct — N
  waiting on you"` — so `December — N waiting on you` is a one-word swap plus a test update.
- Acceptance: smoke tests pin the title pattern and the mark; every foreground/background pair
  the slice ships has a measured contrast ratio recorded as a number, not an assumption; no
  state is conveyed by colour alone; no invented identifier of any kind appears in the shell —
  no run id, no synthesised session or build label (§8.2); no `innerHTML` introduced.

### DEC-UI-2 — Orbit presentation *(owner checkpoint before implementation)*

Replaces the current cycle ring with the Orbit as the dominant spatial graph: five stages, the
travelled part of the trajectory, the current stage, and roles grouped under the stage they are
staged to. **Unblocked by §8.1 (2026-08-03):** the stages display as *Goal, Detect, Diagnose,
Design, Deliver* — the shipped protocol ids, capitalised — and no alternative label is
introduced.

- Files: `src/conductor/panel/index.html` (`drawRing`, `renderCycle`), `tests/test_panel_smoke.py`.
- The panel joins `lane.role → cycle.roles[].stage`. It does not do this today: `renderCycle`
  reads `id`, `harness` and `reviews` only, and the string `stage` does not appear anywhere in
  the panel. The join is new work, not existing behaviour.
- `stage` is never duplicated into lanes, and never used to relocate a lane (§6).
- A stage with no participant is a legitimate shape — the `default-orbit` template deliberately
  stages nobody to `goal`.
- Acceptance: every computed value in `state.json` is unchanged; the five stage labels are the
  capitalised protocol ids and nothing else; no invented identifier of any kind appears in the
  shell, and what would have been headed *This Run* is headed **Recent activity** (§8.2); drift
  between `stage` and `now.phase` renders as a non-blocking presentation warning; the narrow
  layout degrades to a vertical sequence of stages; smoke tests cover both layouts.

### DEC-UI-3 — harness identity

Renders the DO-4 registry: monogram badge and accent per harness in the agents block and the
detail card.

- Files: `src/conductor/panel/index.html`, `tests/test_panel_smoke.py`.
- Acceptance: an unknown harness gets the neutral badge and a minimal card, never a blank or a
  guessed brand; branding never changes an ordering, a status or a queue position; the badge is
  never the only carrier of a status.

### DEC-UI-4 — motion and polish

Functional motion only (§5), and the removal of what is decorative today.

- Files: `src/conductor/panel/index.html`.
- The current phase carries a **permanent** animation today (`.pulse rect{animation:glow 2s
  ease-in-out infinite}`), and the live dot blinks on a 2.4 s infinite loop. The permanent glow
  is exactly the perpetual motion §5 forbids and this slice removes it; the live dot is a
  connection indicator, not Orbit motion, and its fate is a judgement call for the slice.
- `@media (prefers-reduced-motion:reduce)` already disables both; the guard must keep covering
  every animation added here.
- Acceptance: no animation runs when nothing changed; every new animation is listed in the
  reduced-motion guard; a reviewer can state, per animation, which real event triggers it.

### S5 — `conduct report`

A deterministic report over `state.json`, fit to attach to a pull request: the decision brief,
the queue, findings with evidence as authored, and what is unknown.

- Files: a new module under `src/conductor/`, `src/conductor/__main__.py`, `tests/`.
- Acceptance: a pure function of `state.json` — same input, same bytes; no field invented and
  none inferred; nothing unverified rendered as verified; no network.

### S7 — `conduct doctor`

Readiness, kept strictly distinct from schema validation: what is wrong with this project's
setup and how to fix it, rather than whether the files parse.

- Files: a new module under `src/conductor/`, `src/conductor/__main__.py`, `tests/`.
- Acceptance: `validate` behaviour and exit codes unchanged; `doctor` never reports green on an
  unknown; each finding names a concrete next command.

### DO-6/S3+S6 — harness drawer and handoff

The per-harness drill-down over current lane data, plus the deterministic handoff packet.

- Files: `src/conductor/panel/index.html` (the detail card, `#det`), the S5 module, `tests/`.
- Acceptance: only fields that exist in the §6.1 output contract are shown; model, prompt and
  skills stay absent until the data exists (§6); the drawer's structure is extensible without
  placeholders that imply missing data is empty rather than unknown.

### DO-7 — verification and documentation

Close the chunk: README and docs reconciled with what shipped, cross-document consistency
checked, both gates green, and the mutation harness extended to cover any merge rule added
along the way.

## 4. The December visual system

The owner's specification, recorded as given.

### Palette

| Token | Value | Role |
|---|---|---|
| ground | `#07090D` | Page background |
| panel | `#10141B` | Card surface |
| sunk | `#0B0E14` | Recessed surface |
| line | `#262D38` | Borders and rules |
| ink | `#F3F6F8` | Primary text |
| muted | `#B9C2CC` | Secondary text |
| faint | `#7F8A98` | Tertiary text |
| **December Red** | `#E44955` | Reserved — see below |

Those are the dark values, approved. The light theme is retained on the *winter-daylight*
palette (decision §8.3) and its token values are still outstanding.

December Red is reserved for six things and nothing else: the current Orbit stage, the
travelled part of the trajectory, human-control points, the primary action, focus and
selection, and a small brand mark. It is never used as a large filled surface.

Operational statuses — pass, warning, fail — keep their own semantics, stay compact, and are
always **glyph + text**. The current state and a failure must never look alike.

A barely-perceptible coordinate or star texture is allowed. No planets, no rockets, no galaxy
illustrations, no permanent decorative animation.

### Brand shell

In the top area: a December mark built from a circle, trajectories crossing it and one red dot;
the wordmark; the project name and the active Orbit name; the live state and an honestly
labelled **last update**, computed from `state.json`'s `generated_at`. Document title:
`December — N waiting on you`.

**No run identity appears in the shell** (decision §8.2, 2026-08-03). Protocol v1 has none —
`state.json` carries `generated_at`, not a run identity — and run identity stays deferred
(ADR 0001 §2; product direction §3.4, §7.2). The shell may not display an invented or
synthesised identifier of any kind, and where an earlier draft would have said *This Run* it
says **Recent activity** until P1 ships run identity.

## 5. Motion, responsive, accessibility

**Motion.** Only functional motion is allowed:

- a short pulse movement on a *real* phase change;
- a soft refresh of the travelled trajectory;
- a brief accent on a new queue item.

No perpetual Orbit motion. `prefers-reduced-motion` is respected for every animation.

**Responsive.** On desktop the Orbit is the dominant spatial graph. On narrow and mobile
viewports it becomes a vertical sequence of stages — the same information, re-laid out, not a
reduced subset.

**Accessibility.** Full keyboard navigation with visible focus. No state conveyed by colour
alone — the glyph + text rule is what makes this hold. Existing XSS hygiene is preserved: every
state-derived string enters the DOM as a text node or a `setAttribute` value, never through
`innerHTML`, because lane authors are untrusted input. Contrast is checked, not assumed.

## 6. Semantic constraints

The part a redesign is most likely to erode. None of it is negotiable inside a UI slice.

- **`stage` stays presentation and handoff metadata.** It must not affect readiness,
  `review_state`, merge semantics, the human queue, gates, transitions, or `project_status`.
  Protocol v1 §2 and §6.1 say so normatively, and `merge._role` projects it only when the map
  declares it.
- **The join is one-way.** The panel joins `lane.role → cycle.roles[].stage`; `stage` is never
  duplicated into lanes.
- **Design-time `stage` and runtime `now.phase` never overwrite each other.** A mismatch is
  *drift*: a non-blocking, presentation-level warning. A consumer must not take `stage` as
  authoritative and relocate the lane to the staged phase (§6.1 note).
- **No first-class Human Gate node before the corresponding v2 decision.** The existing human
  queue — computed from `waits_on_human`, never authored — may be *presented* as a control
  point. The protocol may not be quietly changed to acquire a gate entity, and absence of a
  wait is still not approval.
- **Harness stays distinct from model.** ADR 0001 §1: a model is an internal setting of a
  harness adapter, not a level of the model.
- **Brand metadata must not influence merge or protocol semantics.** If branding needs a
  contract extension, that is a separate additive slice — never a rider on a visual commit.
- **Do not show model, prompt or skills until those data exist in the output contract.** An
  extensible detail-panel structure is fine; invented values are not.

## 7. Technical constraints

- **The panel stays single-file, no-build, no-dependency.** `conduct up` hands the browser one
  static asset; a bundler or an ES-module split would be a new toolchain in a stdlib-only
  project.
- **Read-only semantics.** The panel never writes; loopback only.
- **The 1600-line waiver** (owner, 2026-08-03) exempts `src/conductor/panel/index.html` from the
  800-line global cap, on four conditions, all recorded in the file itself: sections stay marked
  with their banners; the source is never minified or compressed to fit; every surface keeps a
  smoke test in `tests/test_panel_smoke.py`; and as the file approaches 1600 lines the
  architecture is re-reviewed rather than the ceiling raised again. (The M1–M4 closeout audit
  recorded this waiver as living only in session history; it is now written into the panel
  source, so that finding is closed.)
- **Protocol changes and visual redesign never share a commit.**
- **Internal protocol keys are not renamed without a separate decision.**

### Headroom arithmetic — the structural risk of this chunk

| Measure | Lines |
|---|---|
| `panel/index.html` at M1–M4 closeout | 829 |
| `panel/index.html` today (`2f4aabf`) | **844** |
| Ceiling under the waiver | 1600 |
| **Remaining** | **756** |

Four UI slices — DEC-UI-1 through DEC-UI-4 — share those 756 lines, roughly 189 each, and
DEC-UI-2 replaces the cycle ring with a full spatial graph plus a responsive fallback layout.
That is the main structural risk of this chunk. Two consequences follow. First, each UI slice
reports its line delta when it lands, so the budget is visible rather than discovered at the
cap. Second, if DEC-UI-2 alone approaches the remaining budget, the waiver's own condition
applies — stop and re-review the architecture, do not raise the ceiling and do not minify.

## 8. Resolved decisions

The owner answered all three of the chunk's open questions on **2026-08-03**. The reasoning is
kept rather than deleted: whoever reopens one of these is owed the argument that closed it.

### 8.1 Stage naming — resolved 2026-08-03, no rename

**Decision: keep the shipped ids, display them capitalised.** The canonical protocol ids stay
`goal, detect, diagnose, design, deliver`; the UI shows *Goal, Detect, Diagnose, Design,
Deliver* and introduces no alternative marketing labels. **No code change is required** — the
shipped values already match the decision, which is option (c) below. The earlier UI brief
wording, *Goals → Problems → Diagnosis → Design → Doing*, is **superseded**, and every place in
this document that carried it has been corrected. **DEC-UI-2 is unblocked by this.**

The reasoning, kept. The shipped values are three things at once: the `cycle.phases` of the
`default-orbit` template, the keys of `prompts._STAGE_CONTRACTS`, and the vocabulary documented
in the public product direction §3.2.

| Option | What it means |
|---|---|
| **(a)** Keep the ids, show different labels | Protocol untouched; the panel maps id → display label. Two vocabularies exist, and the public direction keeps the old one. |
| **(b)** Rename the protocol phase ids to the superseded brief | One vocabulary everywhere. Touches the template, `_STAGE_CONTRACTS`, the direction, the spec examples, the demo fixtures. |
| **(c) — chosen** Keep both aligned as they are | The superseded names are dropped; nothing changes. |

The asymmetry that made this urgent, and that (b) would have had to pay for: a role's `stage`
MUST name a declared phase (`spec/PROTOCOL.md` §2), so renaming the phases orphans every staged
role and the map stops validating until each `stage` is renamed in the same edit. The template
ships five staged roles. `_STAGE_CONTRACTS` is keyed by the same strings, and `prompts` returns
an empty stage block for a key it does not know — so a partial rename would silently drop the
stage contract out of every prompt. Today only vended files are affected and a rename is a
mechanical edit. Once users have committed their own maps, the same rename is a breaking change
with no migration written.

### 8.2 Run identity — resolved 2026-08-03, not introduced early

**Decision: no run identity in the shell.** `Run id` is removed from the brand-shell
specification in §4. Protocol v1 has no run identity — `state.json` carries `generated_at` — and
it stays ADR-deferred (ADR 0001 §2; product direction §3.4, §7.2). The header instead shows the
live state and an honestly labelled **last update** computed from that `generated_at`, and
wherever this document or a DEC-UI slice would have said *This Run* it says **Recent activity**
until P1 ships run identity.

No invented or synthesised identifier of any kind may appear in the shell — not a run id, not a
session number, not a build label. DEC-UI-1 and DEC-UI-2 carry that as acceptance.

### 8.3 Light theme — resolved 2026-08-03, kept; token values outstanding

**Decision: `prefers-color-scheme: light` support is retained**, on an approved palette named
*winter-daylight*. **The owner has not yet supplied the token values**, so they are outstanding
and DEC-UI-1 cannot ship the light theme until they arrive.

The table below is the **coordinator's proposal, awaiting the owner's sign-off**. The dark
column is the approved palette from §4; the light column is not approved and must not be treated
as though it were:

| token | dark (approved) | light (proposed) |
|---|---|---|
| ground | `#07090D` | `#F2F5F8` |
| panel | `#10141B` | `#FFFFFF` |
| sunk | `#0B0E14` | `#E8EDF2` |
| line | `#262D38` | `#D3DBE4` |
| ink | `#F3F6F8` | `#0D1319` |
| muted | `#B9C2CC` | `#4A5763` |
| faint | `#7F8A98` | `#77848F` |
| December Red | `#E44955` | `#C8323E` |

One measurable constraint travels with the decision to DEC-UI-1, and it is a constraint rather
than an opinion: December Red at `#E44955` on a light background falls below the 4.5:1 contrast
ratio required for normal text, so the light theme needs a darkened variant of the brand red for
text and small elements. DEC-UI-1 must measure every foreground/background pair it ships and
record the numbers.

## 9. Still open

These two are for the owner. Nothing in this section is decided.

### 9.1 December terminology in CLI strings

Should the panel and the CLI surface December terminology in user-facing strings — "Orbit",
"Run", the wordmark — before the package rename, while the command is still `conduct` and the
package still `agent-conductor`? Splitting the vocabulary between the docs and the terminal has
a cost; so does holding the brand back behind a rename that has not been scheduled.

### 9.2 Which deferred ADR decision does DEC-UI press against first?

ADR 0001 defers five: run identity, narrow panel writes for receipts, the action protocol,
evidence verification, and policy effects. §8.2 settles the run-identity half by designing
around the gap — the shell shows a last update, never an identity — so what remains open is the
receipts half: the human-control points in §4 are the visual half of decision receipts, and no
receipt exists. Is DEC-UI expected to design around that gap as well, or to open the decision?

## 10. Backlog

Four items queued, none attached to a slice.

- **Harden `scripts/mutate_merge.py`.** The restore is a `finally` block rewriting `merge.py`
  from a byte copy held in memory, verified by an `assert`. An interrupt or a crash between the
  mutation write and the restore leaves a mutated `merge.py` in the working tree, and the
  verification `assert` disappears under `python -O`. The script already needed one guard against
  `__pycache__` poisoning across the same round trip (`PYTHONDONTWRITEBYTECODE`) — the same
  failure class: a later run reads something the harness thought it had put back. A crash-safe
  restore, writing beside the target and renaming, or restoring from git, removes the class.
- **Validate `waits_on_human[].title` as a string.** `schema._validate_lane_waits` checks `id`,
  `kind` and `blocks`, and never touches `title`. Finding titles *are* validated
  (`finding {id} needs a non-empty title`), so the gap is asymmetric. `merge._next_action`
  renders the wait title straight into `next_action.text` via
  `f"{lead}: {w['title'] or w['id']}"`, so a non-string title reaches the first sentence on the
  panel as a Python repr.
- **The port-busy message does not mention `--port`.** `__main__._serve` prints
  `cannot serve on 127.0.0.1:{port}: {e}` and exits 1. The flag exists on both `up` and `demo`,
  and the README already tells people about it; the error is the one place a person actually
  needs it and it is the one place that does not say it.
- **The README does not document `--template` or the wizard.** `conduct init` appears there once,
  as a bare command annotated with what it scaffolds — and what it scaffolds changed in
  `2f4aabf`, so that annotation now describes the old default. A small docs slice: the three
  vended templates, the wizard, the non-TTY path, and what the default scaffold contains today.
