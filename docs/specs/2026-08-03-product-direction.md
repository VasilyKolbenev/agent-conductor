# Conduct — product direction and the Default Orbit

- **Status:** Product direction — not a specification
- **Date:** 2026-08-03
- **Contracts:** `spec/PROTOCOL.md` (Protocol v1, normative) and
  `docs/adr/0001-harness-control-plane-model.md` (accepted model) remain the
  only binding documents. Nothing here changes either of them.
- **Applies to:** the alpha and the direction after it

This document says what Conduct is for, which process it recommends, and what
it refuses to do. Where a rule is normative — file formats, merge semantics,
review state, the human queue — the authority is `spec/PROTOCOL.md`, and this
document links there instead of restating it. Everything called *current* is
true of the alpha today; everything else is marked **planned** or
**deferred**. That distinction is not a formality: Conduct's own law is that
nothing unknown or missing may look done.

## 1. The product

Conduct is a **local-first, self-hostable control plane for heterogeneous AI
coding harnesses**. Several harnesses — Claude Code, Codex, Cursor, a custom
script, a CI check — work on one project, each writing one small file, its
lane. Conduct reads the project directory and computes what no single
participant can see alone.

The unit of value is not a conversation or an individual agent run: it is a
**project decision made across independent participants, with visible
evidence and explicit responsibility**.

### 1.1 What it does

| Capability | Meaning | Status |
|---|---|---|
| **Observe** | Collect current state from independent harnesses and checks, each owning exactly one lane file. | current |
| **Explain** | Compute why something is ready, blocked, contested, stale, unreviewed, uncovered, or waiting on a person. | current |
| **Decide** | Surface the human queue, the single next action, and a copyable decision brief for each wait. | current |
| **Act** | Perform a scoped, explicit adapter action — dispatch, pause, resume, retry, stop. | deferred |
| **Verify** | Confirm the requested effect and attach evidence to it. | deferred |

Act and Verify stay off until an action can carry permission, idempotency,
confirmation, and a receipt. An accepted command is not a successful outcome,
and the product will not let one look like the other.

### 1.2 What it does not do

- **Not a chat** with your agents, and it contains no LLM: every state it
  shows is a deterministic projection of files on disk.
- **Not an orchestrator or scheduler** — it never starts, stops, or schedules
  a harness.
- **Not a trace warehouse** — it records decisions, not call logs, and does
  not want your model's private reasoning.
- **Not a cloud service** — no account, no network egress, no API keys; the
  panel binds to `127.0.0.1` and is read-only.

## 2. Product laws

Every feature and every screen follows these eight.

1. **Project truth beats chat history.** Important state is structured,
   portable, and reviewable next to the code.
2. **Heterogeneous by default.** No model vendor, harness brand, or agent
   framework is privileged by protocol semantics; branding is presentation.
3. **No silent success.** Missing evidence, absent reviewers, stale state,
   failed checks, and undecided human gates never render as green.
4. **Every status answers "why?"** The answer names the sources, the
   obligation, the evidence, and the next action — never hidden reasoning.
5. **Every action is explicit and scoped.** No observation becomes a mutation
   without a visible human decision.
6. **Design is committable; runtime is owned.** Configuration travels with
   the repository; runtime files have one writer and never hold secrets.
7. **Unknown is a first-class state.** Partial support and offline harnesses
   degrade honestly instead of pretending.
8. **Simple first, power on demand.** A newcomer sees familiar names, one
   next action, and safe presets; protocol vocabulary is disclosed on demand.

## 3. The Default Orbit

The Default Orbit is Conduct's **recommended process** — a five-stage loop a
project may adopt, edit, or ignore. It is a default, not a requirement, and
carries no special semantics in the protocol.

```
Goal → Detect → Diagnose → Design → Deliver → next Run
```

### 3.1 Why an orbit and not a ring

A ring returns to where it started; an orbit does not. Each completed Run
leaves the project somewhere it has not been: the output of one Run —
surviving findings, decisions taken, evidence gathered, constraints learned —
is the **input context of the next**. Drawn out, the five stages form one
turn, and each turn closes above the point where it opened, so the figure
rises rather than repeats — which is why the same five stages can run many
times without going in circles.

The five-stage improvement loop is *inspired by* the well-known
continuous-improvement cycle used in engineering practice. Conduct uses its
own stage names, its own contracts, and its own visual form.

### 3.2 The stages

Each stage asks one question and owes one contract — what the next stage is
entitled to receive.

| Stage | Guiding question | Contract owed |
|---|---|---|
| **Goal** *(human-owned)* | What are we trying to achieve, and who owns the decision? | Intended outcome, scope, explicit non-goals, constraints, acceptance criteria, known risks, the named decision owner, references to the architecture touched. A goal nobody owns is not a goal. |
| **Detect** | What is actually true right now? | Findings with severity, evidence, affected components, reproducibility, and an honest list of unknowns. A finding without evidence stays *unverified* (the Orbit's word, not a Protocol v1 review state) — confidence never promotes a claim to a fact. |
| **Diagnose** | Why is it happening? | Hypotheses marked confirmed or refuted, the root cause, symptoms kept separate from the cause, the evidence behind each verdict, independent verdicts from someone who did not produce the finding, and the questions still open. |
| **Design** | What do we intend to change, and how will we know it worked? | Implementation plan, architectural impact, affected files, test strategy, migration and rollback paths, risks with the alternatives considered and rejected, and the evidence delivery is expected to produce. |
| **Deliver** | What changed, what was checked, and is it safe to accept? | The changes, the checks that ran, test evidence, independent review, findings still open, an explanation of why the result is ready, and the human decision that accepts it. |

### 3.3 A Run may not end green on silence

A final green state is **forbidden** when any of the following is true:

- required evidence is missing;
- a required independent review is absent;
- a check failed, or its result is unknown;
- a human decision receipt is required and has not been recorded.

Today the merger enforces the review and human-queue half of this from lanes
alone: unreviewed, uncovered, contested, stale, and broken states are
computed, never authored, and no gate is inferred from silence
(`spec/PROTOCOL.md` §6, ADR 0001 §4). Structured evidence verification and
durable decision receipts are **planned**; until they exist, Conduct shows
evidence as authored and claims nothing about verification.

### 3.4 One Run is one finite pass

`Deliver → Goal` is a **narrative** edge, not a scheduler edge. A Run is a
single finite pass through the Orbit. Conduct does not restart it, queue the
next one, or keep run history: real restart, history, and resume all depend
on a run identity that does not exist yet and is **deferred** (ADR 0001 §2).
The arrow describes how a team carries context forward, not something the
product executes.

## 4. Orbit, Stage, Node, Harness, Gate, Run

Conflating these levels is the fastest way to build a confusing product.

| Level | What it is | Example |
|---|---|---|
| **Orbit** | The process a user assembles for their project. | The Default Orbit, or a two-stage variant |
| **Stage** | One of the five meaning-bearing steps. | `Diagnose` |
| **Node** | One concrete piece of work inside a Stage. | `security-review` |
| **Harness** | The product or environment executing a harness node. | Claude Code, Codex, Cursor, a custom adapter |
| **Gate** | A condition, or an explicit human decision. | `Owner approves release` |
| **Run** | One finite pass through the Orbit. | Tonight's pass over the payment bug |

One Stage commonly holds several Nodes. A realistic `Deliver`:

```
Deliver
  ├─ implement            harness node   (implementer instance)
  ├─ tests                check node     (test suite)
  ├─ security scan        check node     (lint / CI / scanner)
  ├─ independent review   harness node   (a different instance)
  └─ owner approval       human gate
```

The UI direction follows: **five stages by default, nodes expanded on
demand** — the first viewport shows the process, not the wiring. That is the
target shape. The alpha panel today renders the project's declared phases and
per-lane state; the staged view is **planned**.

### 4.1 Protocol v1 has no Stage entity — plainly

There is no normative Stage in Protocol v1, and this document does not create
one. In v1 a stage is an entry in `cycle.phases` — a list of labels — and a
lane reports which one it is in through `now.phase` (`spec/PROTOCOL.md` §2,
§3). The Default Orbit is therefore expressible today by writing its five
names into `cycle.phases`; nothing else is required.

An optional `cycle.roles[].stage` field **is part of Protocol v1** (spec §2,
§6.1). It assigns a role to a stage for **presentation and handoff only** — never
affecting readiness, review state, the human queue, gate semantics, or any
merge rule. A panel or adapter that starts treating a stage label as a
semantic gate is a bug, not a feature.

## 5. Support many, recommend few

Conduct supports any participant that can write a lane file, and still ships
one recommended preset, because an empty graph is not a starting point.

| Position | Who holds it | Why |
|---|---|---|
| Goal and final decision | A human owner | Intent and accountability are not delegable |
| Implementation / design | One or more harness instances | The work itself |
| Diagnosis / review | A **separate** harness instance | Two answers with the same failure mode are one answer |
| Checks | Test, lint, or CI nodes | Machine facts, no opinion |
| Final gate | A human gate | Acceptance is a decision, not a status |

- **The preset is a preset.** It uses the same protocol vocabulary as any
  hand-written configuration and receives no privileged semantics.
- **Separate participants are separate instances, not separate
  installations.** Two Codex participants are two configured instances of one
  installed product, distinguished by instance id, role, and prompt. A review
  is still stronger when the reviewer differs by more than an id.

## 6. No model marketplace, no inference routing

Conduct does not select, price, rank, proxy, or route models; there is no
model marketplace and no BYOK vault. A model is an **internal setting of a
harness adapter**. It may surface in that harness's drill-down as reported or
configured by the harness itself, purely as information — the same way a lane
reports its current task. Conduct never sends a token to a model provider and
never needs a credential to do its job; keys stay in the harness's own
environment.

## 7. Alpha boundaries

### 7.1 What the alpha does today

- Observe, explain, and decide, over a committed `conductor/` directory.
- A read-only panel on `127.0.0.1`, live-updating, with an attention list, an
  agents block, findings with evidence, and a copyable decision brief.
- Deterministic projections only — no LLM anywhere in the product.
- Python 3.11+, zero runtime dependencies, loopback-only, no account.
- CLI surface: `conduct validate`, `init`, `prompt`, `up`, `demo`.

### 7.2 Deliberately deferred

Adapter actions · harness start/stop · any scheduler or conditional-execution
engine · run identity, history, and resume · durable human decision receipts
· structured evidence with verification · policy enforcement · drag-and-drop
graph editing · a model marketplace · API-key storage · a public adapter
marketplace · hosting or cloud sync · multi-project analytics, teams, and
RBAC.

All deferred for one reason: shipping the control surface before the decision
semantics would produce a product that looks in control and is not.

## 8. Priorities

### P0 — alpha differentiation

1. Hold Protocol v1 correctness, including instance-specific prompts.
2. A guided `init` producing a valid recommended configuration.
3. An attention-first home: plain-language *why* and one *next action*.
4. A harness drill-down over current lane data, with fields that stay
   compatible with the capability model to come.
5. A deterministic handoff packet and a portable decision brief fit to attach
   to a pull request.
6. A readiness command — what is wrong and how to fix it — kept distinct from
   schema validation.

P0 may use v1-derived data only. It must not pretend that the richer graph,
receipts, structured evidence, or runtime actions already exist.

### P1 — the decision foundation (Protocol v2)

1. Implement the ADR 0001 entities and graph semantics.
2. Structured evidence, provenance, and configuration digests.
3. Immutable human decision receipts and real gate resolution.
4. Adapter health and required-capability negotiation.
5. Desired-versus-observed drift, explained and never silently repaired.
6. The first optional independent-review policy — warning by default.

### P2 — safe control, only after that foundation

1. Adapter action envelopes: dispatch, pause, resume, retry, stop, and
   configuration proposals.
2. Mandatory preview, permission, idempotency key, result receipt, timeout,
   and post-action verification.
3. Run identity, history, resume, and frozen configuration snapshots.
4. Optional time, token, and cost guardrails from adapter-reported data.
5. Local notifications for human gates and failed actions.

## 9. Non-goals

- No built-in chat, and no LLM call from Conduct — ever.
- No agent spawning, scheduling, or harness lifecycle management.
- No cloud sync, authentication, or multi-user installation.
- No lane or map editing from the panel; no drag-and-drop cycle builder.
- No conditional-execution engine.
- No trace warehouse, evaluation lab, or model leaderboard.

A control plane earns trust by being small enough to audit and honest enough
to say "unknown". Everything above is in service of that.
