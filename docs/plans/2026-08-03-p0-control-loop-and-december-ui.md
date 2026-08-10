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
| **DO-3/S4** guided init | `2f4aabf` | `conduct init` wizard, four vended templates, deterministic `--template`, scaffold-then-validate, printed next steps. |

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

**How these numbers are maintained** (owner, 2026-08-03). Every intermediate measurement is
signed with the specific commit it was taken on, and parallel changes are never mixed into an
older result. The table above therefore still reads `bf0ab3b`, even though the branch has since
advanced to `a120cb0` and the suite there measures **498 passed** — that divergence is not a
defect of this document, it is the rule working. Until DO-7 the table need not be re-pinned for
every parallel commit; carrying the measurement's commit plus this explicit note that a final
re-pin is owed is sufficient. The final re-pin happens in DO-7, on a frozen HEAD, and only that
single run's results become the chunk's numbers.

One trap for whoever performs that re-pin: this `.venv` carries an editable-install `.pth`
pointing at the working tree, so an isolated `git archive` export does **not** isolate imports on
its own — `PYTHONPATH` must point at the export's `src`, or the mutation harness silently mutates
the export while the tests import the working tree and reports 0/13.

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
  unregistered harness takes its display name from the incoming string, a deterministic monogram
  from that same string, and the fixed neutral accent of the theme in force — no hash-derived
  colour, and `custom` and unrecognised harnesses alike stay neutral; the widened ban is verified
  by the same sabotage method as the original; the mutation harness and the suite stay green.

### DEC-UI-1 — brand foundation

The December palette, the mark, the wordmark and the brand shell, as one token layer the later
UI slices consume. No layout is redesigned here.

- Files: `src/conductor/panel/index.html`, `tests/test_panel_smoke.py`, `README.md` (tagline).
- Palette lives once in `:root` (§4). Today's accent is teal (`--accent:#33b3a4` dark,
  `#00857a` light); December Red replaces it in the reserved roles only.
- Today's `--fail` is `#e0645c`, close enough to December Red `#E44955` that the two would read
  alike at a glance. Both themes now settle this and this slice implements both. In the
  **light** theme, `--accent` `#c92f42` and `--fail` `#b42318` (§8.3). In the **dark** theme,
  `--fail` moves to `#e0703a` while December Red is retained at full strength as the accent
  (§8.4). No semantic value is invented by this slice; all of them are the owner's.
- The light theme stays (`@media (prefers-color-scheme:light)`), on the *Winter Daylight*
  palette — decision §8.3, 2026-08-03. **Its token values are approved** (§4, §8.3) and this
  slice implements them.
- The contrast constraint that travelled with the light-theme decision is **satisfied by the
  approved palette rather than outstanding**: December Red at `#E44955` on a light background
  falls below the 4.5:1 ratio required for normal text, and the approved light `--accent`
  `#c92f42` is that darkened variant. The obligation to *measure and record* remains.
- **Accent and fail are both reds in the light theme.** `--accent` `#c92f42` and `--fail`
  `#b42318` differ by roughly a 1.24:1 luminance ratio — the coordinator's estimate, which this
  slice must replace with a precise measurement. §4 forbids the current state and a failure from
  looking alike, and the mitigation the palette relies on is structural rather than chromatic:
  statuses always carry glyph, text and shape, and the accent is reserved for the current stage,
  human-control points, the primary action and focus — roles that rarely occupy the same
  position as a status chip.
- **`fail` and `wait` are both warm hues in the dark theme.** `#e0703a` (orange-coral) and
  `#c9971f` (gold) are adjacent on the wheel. Under red-green colour-vision deficiency — the
  common form — orange and gold converge, so the pair that separates *"this failed"* from
  *"this is waiting"* may not be separable by hue for a meaningful share of users. This is stated
  as a fact to measure, not an objection to the palette: the owner's glyph/text/shape rule is the
  mitigation, and this obligation is what proves the rule is load-bearing rather than decorative.
- The document title already follows the target pattern — `document.title = "Conduct — N
  waiting on you"` — so `December — N waiting on you` is a one-word swap plus a test update.
- Acceptance: smoke tests pin the title pattern and the mark; every foreground/background pair
  the slice ships has a measured contrast ratio recorded as a number, not an assumption;
  `fail` and `wait` are each measured against `panel` and `sunk` in both themes; every
  accent/`fail` pair is measured precisely rather than estimated, and the slice enumerates the
  places where an accent element and a `fail` element can appear within one field of view and
  shows that they stay distinguishable without relying on hue alone; the two common CVD types are
  simulated and the slice records whether `fail` and `wait` remain separable under each; the
  glyph-and-text differentiation is shown to be genuinely load-bearing — the states are still
  tellable apart with colour removed entirely, not merely accompanied by a glyph; no
  state is conveyed by colour alone; no invented identifier of any kind appears in the shell —
  no run id, no synthesised session or build label (§8.2); no `innerHTML` introduced.

### DEC-UI-2 — Orbit presentation *(owner checkpoint before implementation)*

Replaces the current cycle ring with the Orbit as the dominant spatial graph: five stages, the
trajectory that connects them and returns to the first, the current stage, and roles grouped
under the stage they are staged to. **Unblocked by §8.1 (2026-08-03):** the stages display as
*Goal, Detect, Diagnose, Design, Deliver* — the shipped protocol ids, capitalised — and no
alternative label is introduced.

The trajectory carries no history, and the slice ships none: every connection is the same
neutral contour, and the return to the first stage is told from a step by its dash and its
missing arrow head rather than by a colour. Displaying the travelled part is reserved (§8.6).

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
- The permanent glow on the current phase (`.pulse rect{animation:glow 2s ease-in-out
  infinite}`) is gone already: DEC-UI-2 deleted it with the old cycle ring in b8b80bf, and
  tests/test_panel_style.py holds that nothing references it. What is left for this slice is
  what the owner settled on 2026-08-09. The live dot becomes a **static** connection
  indicator — a blink with no event behind it is fake telemetry, which the Precision Cockpit
  direction forbids — so the panel is left with no perpetual motion at all. In its place the
  Orbit gets one short transition, on an **observed** change of the current phase: a first
  drawing exists, two consecutive state documents arrived over a live SSE connection, and they
  name different phases. A reload, a reconnect, the first frame after either, a new
  `generated_at` and a new queue each fail one of those and move nothing. Under
  `prefers-reduced-motion` the transition is instant.
- The **travelled trajectory** is not implemented in v1. Protocol v1 records no run history, so
  the third kind of movement §5 sketches has no subject; it is reserved with the accent role in
  §8.6 and stays reserved.
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

- **DO-7 owns the final gate re-pin** (§2). On a frozen HEAD, the test suite, the mutation
  harness and a clean-tree check are re-run *together*, in one run, and only that single run's
  results become the chunk's final numbers. Intermediate measurements taken along the way are
  signed with their own commit and are not merged into it.
- **Until crash-safe restore lands, DO-7 runs the mutation harness on a throwaway export only.**
  Crash-safe restore stays a separate task with its own review (§10, first backlog item). Until
  it is done, DO-7 runs `scripts/mutate_merge.py` against a one-shot export of the frozen HEAD:
  if a run dies between the mutation write and the restore, the export is discarded and the
  working tree is never the thing being restored. Point `--root` at the export — the trap in §2
  is why: the export isolates files, not imports.

## 4. The December visual system

The owner's specification, recorded as given.

### Direction — Precision Cockpit, decided 2026-08-05

**Decision: the December surface is a *Precision Cockpit*** — the minimal, premium
instrument panel of a car or a real spacecraft. Matte dark surfaces, thin cool contours,
local functional lighting, and one dominant instrument: the Orbit. The intensity of the
light reflects real activity and real need for attention. No fake telemetry, no decorative
HUD, no wall-to-wall neon, no perpetual animation.

The direction is a material-and-light layer **over** the palette below, not a replacement
for it. The owner's tokens are unchanged by it: `--ground` `#07090D`, `--panel` `#10141B`
and `--sunk` `#0B0E14` already *are* matte dark surfaces and `--line` `#262D38` already is
a cool contour. What the direction adds is that they become a named system rather than a
set of coincidences.

**Responsibility is split between two slices.** DEC-UI-1 lays down the material and light
system **without changing layout**; DEC-UI-2 turns the Orbit into the central instrument
cluster. Neither does the other's half.

Two constraints travel with the direction and bind every slice that touches the panel:

- **Light must be derived from data.** Every light level names a concrete field or
  computation from `state.json` that drives it. A level with no source behind it is fake
  telemetry, which is §8.2's ban on invented identifiers in its visual form. The absence of
  attention is itself a valid state: a panel with nothing waiting is meant to look calmly
  unlit, not uniformly glowing.
- **Light and accent are different channels.** Light intensity is carried by material and
  contour — surface lightness, contour weight and brightness, depth — and never by the
  accent hue. A lit card does not turn red; it gets lighter and its contour gets crisper.
  December Red stays on the five roles below. In the light theme the mechanism inverts:
  Winter Daylight is an instrument panel in daylight, so depth and contour carry the light
  level there, because a white card cannot be made lighter.

### Palette

Both themes are the owner's and both are approved: the dark surfaces and text ramp, the
*Winter Daylight* light set (decision §8.3), and the dark semantic triple (decision §8.4) — the
last two approved 2026-08-03. Values are recorded verbatim as supplied, hex case included.

| Token | Role | dark (approved) | light — Winter Daylight (approved) |
|---|---|---|---|
| ground | Page background | `#07090D` | `#f3f5f7` |
| panel | Card surface | `#10141B` | `#ffffff` |
| sunk | Recessed surface | `#0B0E14` | `#e9edf1` |
| line | Borders and rules | `#262D38` | `#d5dce4` |
| ink | Primary text | `#F3F6F8` | `#11161d` |
| muted | Secondary text | `#B9C2CC` | `#4e5965` |
| faint | Tertiary text | `#7F8A98` | `#697684` |
| **December Red** / accent | Reserved — see below | `#E44955` | `#c92f42` |
| pass | Operational status | `#3fa86a` (§8.4) | `#247a4b` |
| wait | Operational status | `#c9971f` (§8.4) | `#8a6500` |
| fail | Operational status | `#e0703a` (§8.4) | `#b42318` |

Both columns are now complete. December Red `#E44955` is retained as the full brand accent in
the dark theme; it is the failure colour that moved away from it, not the accent that gave up
colour (§8.4).

December Red is reserved for five things and nothing else: the current Orbit stage,
human-control points, the primary action, focus and selection, and a small brand mark. It is
never used as a large filled surface. A sixth role — the travelled part of the trajectory —
was reserved here until 2026-08-10, when the owner reserved the display itself until a
structural Run history exists (§8.6).

Operational statuses — pass, wait, fail — keep their own semantics, stay compact, and are
always distinguished by **glyph, text and shape as well as colour, never by colour alone**
(owner, 2026-08-03, §8.4). The current state and a failure must never look alike.

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
- a brief accent on a new queue item.

A soft refresh of the travelled trajectory was a third allowance. It goes with the display it
would have moved: §8.6 reserves that display until a structural Run history exists, so in v1
there is nothing for such a refresh to be a refresh *of*, and inventing one would be motion
with no event behind it.

No perpetual Orbit motion. `prefers-reduced-motion` is respected for every animation.

**Responsive.** On desktop the Orbit is the dominant spatial graph. On narrow and mobile
viewports it becomes a vertical sequence of stages — the same information, re-laid out, not a
reduced subset.

**Accessibility.** Full keyboard navigation with visible focus. No state conveyed by colour
alone — the glyph, text and shape rule (§4, §8.4) is what makes this hold, and both approved
palettes depend on it holding. Existing XSS hygiene is preserved: every
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
- **The single-file waiver** (owner, 2026-08-03; revised 2026-08-08 and 2026-08-10, §8.5) exempts
  `src/conductor/panel/index.html` from the 800-line global cap, on four conditions, all recorded
  in the file itself:
    - sections stay marked with their banners;
    - the source is never minified or compressed to fit;
    - Every new panel invariant is pinned in the matching `tests/test_panel_*.py` module.
      `test_panel_smoke.py` guards basic loading and the structural contract; it is not the
      mandatory home for every panel guard.
    - crossing 1600 lines triggers an architecture audit; 2000 lines is the alpha ceiling, and
      a forecast beyond it stops the slice for a split proposal rather than another increase.

  (The M1–M4 closeout audit recorded this waiver as living only in session history; it is now
  written into the panel source, so that finding is closed.)
- **Protocol changes and visual redesign never share a commit.**
- **Internal protocol keys are not renamed without a separate decision.**

### Headroom arithmetic — the structural risk of this chunk

| Measure | Lines |
|---|---|
| `panel/index.html` at M1–M4 closeout | 829 |
| `panel/index.html` before the UI chunk (`2f4aabf`) | **844** |
| `panel/index.html` after DO-6 (`9541746`) | **1657** |
| Mandatory architecture-audit trigger | 1600 |
| Alpha ceiling under the waiver | 2000 |
| **Remaining after DO-6** | **343** |

The trigger fired after DO-6 and the architecture review is recorded in
`docs/audits/2026-08-10-panel-1600-line-audit.md`. The alpha keeps the single-file constraint:
the source is still sectioned, unminified and below 2000, while the invariant circuits already
live in focused `tests/test_panel_*.py` modules. The remaining 343 lines are defect headroom,
not a feature budget. Any post-alpha interactive control work starts with a split proposal;
DO-7 may reconcile documentation and fix release blockers, but adds no new panel surface.

## 8. Resolved decisions

The owner answered all three of the chunk's open questions on **2026-08-03**, and closed a
fourth the same day — §8.4, a gap the light-theme approval exposed rather than one the chunk
started with. The reasoning is kept rather than deleted: whoever reopens one of these is owed
the argument that closed it.

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

### 8.3 Light theme — resolved 2026-08-03, kept; token values approved

**Decision: `prefers-color-scheme: light` support is retained, on the owner's *Winter Daylight*
palette, and the token values below are the owner's and are approved.** Nothing about the light
theme is outstanding, and **DEC-UI-1 may implement it**.

| token | light — Winter Daylight (approved) |
|---|---|
| `--ground` | `#f3f5f7` |
| `--panel` | `#ffffff` |
| `--sunk` | `#e9edf1` |
| `--line` | `#d5dce4` |
| `--ink` | `#11161d` |
| `--muted` | `#4e5965` |
| `--faint` | `#697684` |
| `--accent` | `#c92f42` |
| `--pass` | `#247a4b` |
| `--wait` | `#8a6500` |
| `--fail` | `#b42318` |

The reasoning, kept. An earlier revision of this entry carried a **coordinator's proposal**
awaiting sign-off — `#F2F5F8 / #FFFFFF / #E8EDF2 / #D3DBE4 / #0D1319 / #4A5763 / #77848F` with
December Red at `#C8323E`. That proposal is **superseded in full** by the table above. It is
recorded only so a future reader can tell the two apart: the values above are the owner's, they
are what ships, and the proposal never was. The approved set also goes further than the proposal
did — it supplies the semantic triple (`pass`, `wait`, `fail`), which the proposal did not
address at all.

The measurable constraint that travelled with the decision is now **satisfied rather than
outstanding**: December Red at `#E44955` on a light background falls below the 4.5:1 contrast
ratio required for normal text, and `--accent` `#c92f42` is the darkened variant that answers it.
The obligation it created survives the approval — DEC-UI-1 still measures every
foreground/background pair it ships and records the numbers, because approval of a value is not
a measurement of it.

The approval also exposed something the proposal had not: `--accent` `#c92f42` and `--fail`
`#b42318` are both reds, roughly 1.24:1 apart in luminance by the coordinator's estimate. That
is not a defect — the separation is meant to be structural, not chromatic — but it is a
measurement DEC-UI-1 owes, and it is written into that slice's acceptance in §3.

### 8.4 Dark semantic triple — resolved 2026-08-03, variant A approved

**Decision: the dark theme's `pass`/`wait`/`fail` are the owner's values below, approved.** The
owner's original dark palette (§4) supplied surfaces, the text ramp and December Red but no
semantic triple, and the panel had been shipping its own unapproved values. That gap is closed.

| token | dark (approved) |
|---|---|
| `--pass` | `#3fa86a` |
| `--wait` | `#c9971f` |
| `--fail` | `#e0703a` |

**These exact hex values were approved, not merely the direction.** Variant A was put to the
owner with these values and blessed as it stood; a future reader may treat them as literal, and
a change to any one of them is a new decision rather than an adjustment within an approved
direction.

The reasoning, kept, because it constrains future changes more than the values do. The problem
was that today's dark `--fail` `#e0645c` sits very close to December Red `#E44955` — the same
collision the light theme has between accent and fail, but more acute, because in a dark theme
both are light marks on a near-black field and cannot be separated by lightness the way the
light theme separates them. Two ways out existed: move the failure colour, or take the colour
away from the accent and let form and position carry it. **The owner chose to move the failure
colour and to retain December Red as the full brand accent** — the current state, focus and
human-action points must not lose the brand colour, and must not come to look like a failure.
So failure moves to orange-coral and the warning stays gold.

One standing rule travels with the decision, and it is a rule rather than a nicety precisely
because the palette leans on it: `pass`, `wait` and `fail` are always distinguished by **glyph,
text and shape as well as colour, never by colour alone**. §4 and §5 already carried the weaker
*glyph + text* form of this; it is now the stronger form and applies to both themes.

What the decision leaves for DEC-UI-1 to measure, not to reopen: `#e0703a` and `#c9971f` are
adjacent warm hues, and under the common form of red-green colour-vision deficiency orange and
gold converge. The mitigation is the standing rule above; the obligation to prove it holds is
written into DEC-UI-1's acceptance in §3.

### 8.5 Where a panel invariant is pinned — resolved 2026-08-10, the waiver's third condition widened

**Decision, as given:**

> Every new panel invariant is pinned in the matching tests/test_panel_*.py module.
> test_panel_smoke.py guards basic loading and the structural contract; it is not the
> mandatory home for every panel guard.

§7 and the copy of the four conditions inside `src/conductor/panel/index.html` both carry the
new wording. The condition has to read the same in both places or the panel's own record of the
waiver stops being the record.

The reasoning, kept. The condition was written when one module held everything the panel
promised. It no longer does: `tests/test_panel_cascade.py` owns the parsing and the cascade
model, `test_panel_colour.py` the colorimetry as a self-contained circuit, `test_panel_contrast.py`
the measured pairs, `test_panel_style.py` the stylesheet's structural relations,
`test_panel_orbit.py` the Orbit's geometry and stage vocabulary, `test_panel_harness.py` the
harness channel rule, and `test_panel_smoke.py` the served response and the id contract. Two
forces produced that split and both are the owner's: a guard belongs with the class it closes,
and a test file over 800 lines gives up the self-contained circuit inside it rather than growing
(the rule of 2026-08-04, which is what moved the colorimetry out of the contrast module).

Read literally, the old condition ordered the geometry, cascade, contrast and branding guards
back into `test_panel_smoke.py`. The 800-line cap on test files is not what the panel's waiver
suspends — the waiver names one HTML file — and the guards outside the smoke module already run
to 2927 lines against a smoke module of 270, so the literal reading is not merely undesirable
but unreachable. It would also put unrelated guards behind one module's fixtures and dissolve
the one thing a module name is good for: telling a reader which class of claim was closed where.

What the condition buys is unchanged, and it is the part worth keeping: no surface ships
unguarded. It is the module that moved, not the obligation. Specifically **not** implied by
this decision: gathering the Orbit's checks into `test_panel_smoke.py` for literal compliance
with the old wording. Geometry, cascade, contrast and branding stay in the modules that own them.

### 8.6 The travelled trajectory — resolved 2026-08-10, reserved rather than a v1 accent role

**Decision, as given:**

> Displaying the travelled trajectory is reserved until a structural Run history exists.
> It is not implemented in v1: the interface does not derive it from the current phase,
> does not accumulate it client-side, and does not simulate historical data.

December Red is therefore reserved for **five** roles, not six (§4); DEC-UI-1's accent list and
DEC-UI-2's description of what the Orbit shows (§3) drop it; and §5's soft refresh of the
travelled trajectory goes with it.

The reasoning, kept. Protocol v1 records no run history. `state.json`'s `cycle` carries the
declared phases, the roles, and at most the one phase a lane is reporting right now — there is
no field in it that could make a travelled path true, and run identity is ADR-deferred (§8.2,
ADR 0001 §2). Each of the three ways to draw one anyway is an invention of exactly the kind this
document bans elsewhere: deriving the path from `now.phase` asserts that every earlier phase was
completed, which the merger never says; accumulating it in the browser makes the picture depend
on how long a tab happened to stay open, so two people looking at the same project see different
histories; and simulated history is fake telemetry, which §4's rule that light must be derived
from data already forbids.

The role therefore had no subject, and the panel had already settled the question in the other
direction while the plan still listed it: no part of the trajectory may be painted with the
accent or with a status colour, and the return to the first stage is told from a step by its
dash and its missing arrow head. The DEC-UI-2 review found that contradiction and correctly
declined to fix it in the guards, because the guards were quoting §4 faithfully and the
contradiction was the plan's. This entry is that repair. Nothing in the panel is implemented to
satisfy it and nothing needs to be: reserving a display is a decision not to build one.

### 8.7 December Command — the 2026-08-10 owner directive, acknowledged

**Decision (owner, 2026-08-10; binding).** The product's full name is **December Command**;
the brand stays **December**; the market category is **Harness Control Plane**. The naming
discussion is closed and is not reopened here. The authoritative record is
`docs/specs/2026-08-03-hcp-competitive-product-direction.md` (§1.2, §4.9–§4.11, §8 P3, and
the "14-day December Command strike" section). That file becomes tracked at
integration/DO-7 **deliberately** — this supersedes the 2026-08-03 disclosure decision to
keep it untracked, and its historical evidence is not rewritten.

**What this changes for the alpha: the packaging course, nothing else.** v0.1.0 ships under
the distribution name `agent-conductor`, CLI `conduct`, Protocol v1, read-only panel
semantics. No broad rename happens during DO-7. This supersedes the 2026-08-08 packaging
decision that the first public release must ship as `december-orbit`, and it supersedes
§1's sentence that the rename lands before any PyPI publish: the public rename to December
Command happens post-alpha, only after trademark, domain, repository and package clearance.
The alpha scope stays frozen; no v2 execution or orchestration functionality enters it.

**What this changes after the alpha.** The post-alpha delivery contract is the 14-day
December Command strike as written in the spec: four parallel lanes, daily integration,
architecture frozen by day 2, features frozen after day 10, release candidate on day 13,
release on day 14. Phase order: A foundation (recorded alpha quality debt, browser-render
test job, crash-safe mutation restore, Protocol v2 ADRs, run identity / evidence /
receipts) → B safe control (adapter SDK, Claude Code and Codex adapters, Observe and
Propose modes, action previews, verified handoff and review dispatch) → C interactive
execution (Confirm mode, pause / resume / retry / stop, harness switching, run history and
replay, immutable Human Gate decisions) → D December Command v2 (Policy mode, visual Orbit
editor, parallel execution, the complete wow path, public launch). The nine ADRs the
directive lists precede implementation; none of these concepts enters through an
incidental UI commit or a silent Protocol v1 change. The product laws travel with it:
Orbit advances only from verified state — an accepted command is never a successful
result — and there is no hidden fully-autonomous mode.

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

Five items queued, none attached to a slice.

- **Give `scripts/mutate_merge.py` a crash-safe restore.** The restore is a `finally` block
  rewriting `merge.py` from a byte copy held in memory, and the rewrite is proved by content
  hash with retries: a restore that cannot be confirmed stops the run and names the file that
  may still carry a mutation. What no `finally` covers is the window between the mutation write
  and the restore — an interrupt or a hard kill there leaves a mutated `merge.py` in the working
  tree and says nothing at all, which is the one outcome the harness documents rather than
  prevents. The script already needed one guard against `__pycache__` poisoning across the same
  round trip (`PYTHONDONTWRITEBYTECODE`) — the same failure class: a later run reads something
  the harness thought it had put back. A crash-safe restore, writing beside the target and
  renaming, or restoring from git, removes the class.
- **Rendered-result browser testing.** The panel's guards read source text: the `<style>`
  block parsed into rules, the `<script>` block read as characters. Nothing renders. So they
  prove what the panel *declares* — its structure — and not what a browser produces from it,
  and the same behaviour written a different way goes straight through. That is not a
  hypothesis: two reviews executed fourteen sabotages of exactly this kind, among them
  `querySelector("html")` for `documentElement`, a class assembled as `"card li" + "t"`, a
  class reached through `style.boxShadow`, an attribute order the regex could not follow,
  `(st.glyph + " " + st.label) && ""` keeping every guarded substring while producing an empty
  string, `insertAdjacentHTML` for `innerHTML`, and `box-shadow: inset` and `filter:
  hue-rotate` as paints outside the closed list. Chasing each spelling is not the answer and
  the owner has closed that route; closing the class needs assertions on the **rendered
  result** rather than on the source. Post-alpha this becomes a **separate browser-test job**
  with Playwright driving Chromium, asserting computed styles and composited colours off a
  live page. It is a **dev/CI dependency only**, and it leaves the three product constraints
  intact: the runtime stays stdlib-only, the panel stays a single file, and there is still no
  build step.
- **Validate `waits_on_human[].title` as a string.** `schema._validate_lane_waits` checks `id`,
  `kind` and `blocks`, and never touches `title`. Finding titles *are* validated
  (`finding {id} needs a non-empty title`), so the gap is asymmetric. `merge._next_action`
  renders the wait title straight into `next_action.text` via
  `f"{lead}: {w['title'] or w['id']}"`, so a non-string title reaches the first sentence on the
  panel as a Python repr. It reaches the report's Decision brief the same way, and that half
  cannot be fixed downstream: by the time `conduct report` is handed the document, the repr *is*
  the string `next_action.text` holds — `Answer the decision: {'raw': 1}` — so the report's
  one door out of the document (`report._from_document`) gets text and renders text, exactly as
  it would for a sentence a person wrote. Pinned as current behaviour, not guarded against, by
  `test_a_non_string_wait_title_reaches_the_decision_brief_as_a_repr_the_merger_wrote`.
  The f-string is the merger's; so is the fix, and validating `title` closes both surfaces.
- **The port-busy message does not mention `--port`.** `__main__._serve` prints
  `cannot serve on 127.0.0.1:{port}: {e}` and exits 1. The flag exists on both `up` and `demo`,
  and the README already tells people about it; the error is the one place a person actually
  needs it and it is the one place that does not say it.
- **Six guards on `conduct report` hold their sentence by vocabulary, not by relation.** The
  report's behaviour is right in all six; the guards are what is thin, so only test-hardening is
  queued here — the live defects and the false prose the S5 reviews found are fixed on the slice
  itself, not carried into this item. Each diversion below is applied on its own to a clean tree
  and the full suite stays green (`971 passed, 4 skipped`), which is the whole complaint:
  1. **The empty-queue section can be rewritten into consent.**
     `test_the_empty_queue_section_itself_asserts_no_agreement_anywhere_in_it` reads the section
     for a ten-word list the test owns (`_AGREEMENT_WORDS`). Rewriting `report._queue`'s empty
     branch to say that every question the project put to a person *"came back yes"*, that
     *"the way is clear to merge"*, and that a reviewer may treat everything below as carrying
     *"the blessing of the people who own it"* stays green: not one of those phrases is in the
     list (`clear to merge` is not the listed `cleared`), and the rewrite leaves one denial
     sentence standing, which is all the guard's second assertion asks for.
  2. **A field §6.1 does not define is displayed, provided it carries no backticks.**
     `test_no_line_shows_a_value_that_no_field_of_the_document_can_move` sweeps sentinels only
     over lines matching a code span (`_value_lines`). Two invented header lines rendered as
     bare prose — `- Release readiness: cleared to merge` and
     `- Sign-off: all lanes have signed off` — never enter the swept set, so every report can
     assert a clearance no document records.
  3. **The vacuous-agreement sentence can be inverted with the guarded substring left in.**
     `test_agreed_with_nobody_assigned_to_review_it_is_not_rendered_as_checked` asks for
     `no reviewer assigned` in the vacuous half and its absence in the reviewed half. Rewriting
     `verify()`'s vacuous label to *"agreed and sound — the phrase no reviewer assigned does not
     apply here; this finding was reviewed and its agreement stands on a real check"* keeps the
     substring and leaves `verified` False, so the report calls a finding checked while the
     unknown section four sections later still lists it as vacuous. The counting guard cannot
     catch it: `_VERIFIED_LABEL` is derived from `verify()`, so both sides move together.
  4. **The `## Findings — none` sentence has no guard at all.** Replacing *"That is what the
     lanes say; it is not a record that anything was checked."* with *"Every lane has looked and
     every check has passed, so the work is clear to merge."* stays green. It is the same
     sentence, written for the same reason, as the empty queue's — and the empty queue has one.
  5. **Document order is claimed and unmeasured.** The module docstring says lists render in the
     order the merger built them; having `report._findings` iterate its findings sorted by
     `str(f.get("id"))` in reverse instead stays green. A re-sort is deterministic, so the
     determinism battery cannot see it, and no other guard looks at sequence.
  6. **Nothing ties the `Verification` line to the fields it names.** Shortening its
     parenthetical to ``(read from `review_state` alone)`` stays green, so what the line tells a
     reader the verdict rests on is held by no test. Both fields it names are live, which is the
     relation a guard here can reach rather than a vocabulary: with the rest of the document
     unchanged, taking the author's role out of `cycle.roles[].reviews` flips `verified` from
     True to False, and so does changing `review_state`.

  **Closed when** each of the six, applied one at a time to an otherwise clean tree and run as
  `pytest -q` with `PYTHONPATH` on that worktree's `src`, turns the suite red, and the tree with
  all six reverted is green. Those six runs are the acceptance evidence and belong in the closing
  report verbatim; a guard that reds only on the exact wording quoted above closes nothing. Three
  of them constrain the shape of the fix: (1) cannot be closed by lengthening `_AGREEMENT_WORDS`,
  because a vocabulary the test owns is still a vocabulary; (3) cannot be closed by a comparison
  whose two sides both derive from `verify()`; and (6) is not closed by a substring match on the
  parenthetical, but by moving each field it names and showing the rendered verdict move with it.
- ~~**The README does not document `--template` or the wizard.**~~ **Closed.** The README now
  carries a "What `conduct init` writes" section: the wizard's three questions, `--template`,
  the four vended maps — the item said three, and `templates.names()` returns four — and the
  path without a terminal, which writes `default-orbit` without waiting for an answer. The same
  slice added the `conduct report` the README had never mentioned, and `docs/release-smoke.md`,
  the procedure a person runs against a release candidate before publishing. What holds all of
  it is a relation rather than a rewrite: `tests/test_docs_commands.py` reads the subcommand
  list off the parser `__main__._build_parser()` builds and requires the README and the release
  smoke to name exactly that set, in both directions, so the next command added or renamed
  moves both documents or reds the suite.
