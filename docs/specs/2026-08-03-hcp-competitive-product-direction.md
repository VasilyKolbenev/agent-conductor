# HCP competitive product direction — from dashboard to control loop

- **Status:** proposed product direction for implementation planning
- **Date:** 2026-08-03
- **Builds on:** `docs/adr/0001-harness-control-plane-model.md`
- **Does not modify:** Protocol v1 semantics

## 1. Product decision

HCP is a **local-first, self-hostable control plane for heterogeneous AI
coding harnesses**. It helps a person design how Claude Code, Codex, Cursor,
Zo, custom harnesses, checks, and human gates work together on one project;
then shows what is happening, why it is happening, what needs attention, and
whether the result is safe to accept.

HCP is not a personal AI computer, an LLM chat, a hosting platform, or a
framework-specific trace collector. Its unit of value is not a conversation
or an individual agent run. Its unit of value is a **project decision made
across multiple independent participants with visible evidence and explicit
responsibility**.

The category statement is:

> Zo is an AI computer. LangSmith is an agent application platform. HCP is the
> lightweight control tower for the harnesses already working on your code.

The primary job to be done is:

> Given several AI coding harnesses working on the same project, tell me what
> is happening, why, what needs me, and safely carry the resulting decision
> forward without hiding uncertainty.

### 1.1 Competitive evidence snapshot (non-normative)

This direction is based on public product information available on
2026-08-03:

- Zo packages an always-on personal cloud, models, files, hosting, and broad
  tools behind a conversational interface: <https://www.zo.computer/>.
- Zo already combines model selection/BYOK, scoped personas, open Agent
  Skills, and scheduled automations with run history:
  <https://www.zo.computer/models>,
  <https://www.zo.computer/docs/personas>,
  <https://www.zo.computer/docs/skills>, and
  <https://www.zo.computer/docs/automations>.
- LangSmith's full self-hosted product combines observability, evaluation,
  deployment, and a UI/API for multiple agents and graphs, but its complete
  control plane is an enterprise, Kubernetes-based installation:
  <https://docs.langchain.com/langsmith/self-hosted>.

Product inference: HCP cannot win by offering another model picker, generic
automation list, or trace warehouse. It can win by being lighter,
framework-neutral, project-owned, and substantially better at cross-harness
responsibility, evidence, review, and human decision semantics.

### 1.2 International name and category — owner decision 2026-08-10

The product name after alpha is **December Command**. The
brand remains **December**; *Command* names the product's move from a read-only
cockpit to a safe command layer over heterogeneous coding harnesses. The public
category remains descriptive rather than proprietary:

> **December Command — the self-hosted Harness Control Plane.**
>
> Build your Orbit. Control the cycle.

The terms have separate jobs:

- **December** is the brand and visual language;
- **Command** is the interactive product surface;
- **Harness Control Plane** is the searchable market category;
- **Orbit** is the user-designed development cycle;
- **Cockpit** is the minimal panel that shows and controls one Orbit;
- **Command Runtime** is the optional execution layer introduced after the
  v2 action and receipt contracts exist.

This is the owner's product decision, subject only to trademark, domain,
repository, and package clearance before the public rename. Public metadata
should use `December Command` or `December Harness Control Plane`, never the
unqualified word `December` alone, because the brand word by itself is not a
discoverable software category. The alpha distribution and CLI are not renamed
by this direction.

## 2. The complete HCP control loop

The current alpha is strongest in the middle of the loop. The product must
eventually close all five steps while keeping the deterministic core small:

1. **Observe** — collect current state from independent harnesses and checks.
2. **Explain** — compute why something is ready, blocked, contested, stale,
   uncovered, or awaiting a person.
3. **Decide** — obtain agent verdicts and explicit human receipts; silence is
   never consent.
4. **Act** — through an adapter, perform only an explicit, scoped action such
   as dispatch, pause, resume, retry, or stop.
5. **Verify** — confirm the requested effect and attach evidence; an accepted
   command is not the same as a successful outcome.

Alpha implements Observe, Explain, and Decide. Act and Verify are designed
now but remain disabled until adapter actions have idempotency, permission,
confirmation, and receipt semantics. The merger remains pure and never calls
an LLM.

## 3. Product laws

Every feature and screen follows these laws:

1. **Project truth beats chat history.** Important state is structured,
   portable, and reviewable next to the code.
2. **Heterogeneous by default.** No model vendor, harness brand, or agent
   framework is privileged by protocol semantics.
3. **No silent success.** Missing evidence, missing reviewers, stale state,
   adapter failure, and absent human decisions can never render as green.
4. **Every status can answer “Why?”** The answer identifies the sources,
   obligation, evidence, and exact next action; it does not expose hidden
   chain-of-thought.
5. **Every action is explicit, scoped, and receipted.** HCP never turns an
   observation into a mutation without a visible user decision or policy.
6. **Design is committable; runtime is owned.** Cycle, harness, policy, and
   prompt configuration travels with the repository. Runtime files have one
   writer and never contain secrets.
7. **Unknown is a first-class state.** Partial adapter support and offline
   harnesses degrade honestly instead of crashing or pretending success.
8. **Simple first, power on demand.** A junior sees familiar names, one next
   action, and safe presets. Protocol vocabulary and advanced controls are
   progressively disclosed.

## 4. Defensible feature core

These features distinguish HCP from a single-agent workspace and from a
generic workflow builder.

### 4.1 Decision graph, not merely workflow graph

The cycle DAG from ADR 0001 remains the visual backbone, but each node also
participates in a decision graph:

```
task/artifact -> finding -> evidence -> review obligation -> verdict
              -> human gate -> decision receipt -> verified outcome
```

The UI must let a user follow this chain in either direction. A red status
must not be a decorative color; it must link to its cause and the action that
can resolve it.

### 4.2 Deterministic handoff packets

HCP should remove cross-harness copy-paste errors without becoming a chat.
For a cycle node it deterministically produces a handoff packet containing:

- task and node identity;
- relevant architecture refs and invariants;
- predecessor outputs and unresolved findings;
- required review obligations and expected evidence;
- selected instance, model label, prompt reference, and capabilities;
- exact lane/event contract and destination paths.

Proposed CLI:

```text
conduct handoff --cycle main --node review
conduct handoff --cycle main --node review --format json
```

The default text output is designed to paste into any harness. Adapters may
deliver the same packet mechanically later. No LLM is involved.

### 4.3 Evidence and provenance as product primitives

Free-form evidence remains readable, but Protocol v2 should support a
structured form with at least:

```text
kind, uri/path, label, digest?, created_by, observed_at,
git_ref?, cycle_id?, node_id?, instance_id?, run_id?
```

Examples include a diff, test result, CI URL, screenshot, log excerpt,
artifact, benchmark, or manual observation. HCP displays availability and
freshness; it does not claim a referenced artifact exists unless verified by
an adapter or local reader.

A decision brief must be able to prove which project revision and which
configuration were reviewed:

- Git commit/worktree identity when available;
- cycle and harness configuration digests;
- prompt and skill digests;
- adapter and model identifiers as reported by the harness;
- findings, evidence, verdicts, exceptions, and human receipts.

This is provenance, not chain-of-thought capture. HCP should not require or
encourage storage of private model reasoning.

### 4.4 Explicit human decision receipts

Human gates become useful only when a person can resolve them. The panel may
remain read-only for maps, lanes, prompts, and harness configuration, while
making one narrow exception: it may append immutable human decision receipts
after confirmation.

Minimum actions:

- approve;
- reject;
- request changes;
- acknowledge/waive with a required reason and visible exception state.

Minimum receipt fields:

```text
id, gate/wait id, action, actor label, timestamp, reason,
scope refs, cycle/node ids, config digest, evidence refs
```

A receipt is append-only. Corrections create a superseding receipt; history
is never rewritten. Removing a wait without a receipt only clears the wait
and never satisfies a gate.

### 4.5 Review independence policies

Counting two answers is not enough when both answers have the same failure
mode. HCP should optionally express how independent a review must be:

```text
independence: instance | harness_type | provider | model_family
```

Examples:

- Claude Code implementation plus Codex review satisfies provider diversity;
- two Codex instances satisfy instance diversity but not provider diversity;
- a human gate may be required for blocker findings regardless of consensus.

Alpha ships one understandable built-in warning: **Independent review
recommended**. Custom policies and enforcement arrive after the base
obligation model. A policy can warn or block, but its effect is always shown.

### 4.6 Desired-versus-observed drift

Committed configuration expresses desired state. Adapters report observed
state. HCP compares them without owning credentials:

- configured model versus reported model;
- configured prompt/skill digest versus loaded digest;
- declared permissions versus effective capabilities;
- cycle assignment versus active lane;
- expected adapter version versus connected version.

Drift is never silently repaired in alpha. The panel explains the mismatch
and offers a copyable remediation command or file location. Later an adapter
with `configuration_write` may propose a scoped fix.

### 4.7 Capability negotiation and adapter health

An adapter manifest describes capabilities; runtime health says which of
them are currently available. A cycle can declare requirements such as
`review`, `runtime_events`, or `structured_evidence`.

Before work begins, HCP computes readiness:

- **ready** — all required instances and capabilities are available;
- **degraded** — work may proceed but optional visibility is missing;
- **blocked** — a required instance/capability is unavailable;
- **unknown** — the adapter cannot report enough information.

Proposed CLI:

```text
conduct doctor
conduct doctor --cycle main
conduct adapter check path/to/manifest.toml
```

`doctor` answers what is wrong and how to fix it. `validate` remains the
schema/protocol command; the two must not be conflated.

### 4.8 Portable decision bundle

HCP exports a compact, redacted report that can be attached to a pull request
or release without running the panel:

```text
conduct report --cycle main --format markdown
conduct report --cycle main --format json
```

The bundle includes status, open findings, evidence references, obligations,
verdicts, decision receipts, warnings, configuration digests, and timestamps.
Secrets, full prompts, and hidden reasoning are excluded by default.

### 4.9 Interactive harness command surface

December Command must let a person work with a connected harness from the
Cockpit without turning the panel into a generic shell or another IDE. A
selected harness instance may expose only the controls its adapter declares:

- deliver a deterministic handoff or follow-up instruction;
- dispatch a prepared node assignment;
- stream structured progress and user-visible output;
- request status or evidence;
- pause, resume, retry, cancel, or stop a supported run;
- redirect unfinished work to another compatible harness instance;
- request review and resolve a human gate through a decision receipt.

The first implementation is a structured message and action surface, not an
unrestricted browser terminal. Terminal-only harnesses are mediated by a local
runner; native integrations may use their supported API, hooks, plugins, or
headless mode. The panel never invents a control for a capability the adapter
does not report. Unsupported controls are absent rather than decorative.

Adapters have four distinct responsibilities:

1. **Observe** — report health, session state, progress, evidence, and output.
2. **Prepare** — validate a handoff and preview the exact requested action.
3. **Execute** — perform one capability-scoped action with an idempotency key.
4. **Verify** — report the observed result and attach a result receipt.

An accepted command is not a successful result. The Orbit advances only from
verified state, never from a button click or a process-start event.

### 4.10 Bounded proactive orchestration

Proactive behavior is useful only when its authority is visible. Each project
or Orbit selects one control mode, with the safest mode as the default:

1. **Observe** — read-only, today's alpha behavior.
2. **Propose** — December computes and previews the next action; a person runs
   it.
3. **Confirm** — December may execute a prepared action after explicit human
   confirmation.
4. **Policy** — December may execute only pre-authorized action classes inside
   declared scope, budget, concurrency, and time limits.

There is no hidden fifth "fully autonomous" mode. A policy is explicit,
committable, inspectable, and reversible. A user can always see why an action
was proposed, which permission allows it, which files or instance it may
touch, and which receipt proves the outcome.

Useful proactive behaviors include:

- proposing the next ready node and the best compatible harness instance;
- preparing an independent review as soon as implementation evidence exists;
- noticing a stale, failed, or disconnected instance and proposing a retry or
  handoff;
- pausing before a human gate, destructive action, permission expansion, or
  budget boundary;
- notifying the owner when the Orbit genuinely needs a decision;
- verifying that a requested state change actually occurred.

Proactivity never means probing the machine without consent, selecting a
different model or harness silently, expanding filesystem scope, weakening a
gate, treating silence as approval, or inferring success from missing state.

### 4.11 The v2 wow path

The first-run v2 demonstration must show real value in one continuous path:

1. Start from Default Orbit or create a small custom Orbit.
2. Connect two existing harnesses explicitly, with no machine scan.
3. Dispatch implementation to the first harness from the Cockpit.
4. Watch the active node update from adapter events, not fake telemetry.
5. Receive artifacts and a structured handoff packet.
6. Route independent review to the second harness.
7. Stop at a human decision with the evidence and disagreement visible.
8. Approve or request changes and leave an immutable decision receipt.
9. Replay why every transition occurred and which configuration produced it.

If this path cannot be completed in under ten minutes on a local project, v2
has accumulated features without becoming a coherent product.

## 5. Minimal alpha experience

The alpha should expose only six primary surfaces. Features may be powerful
underneath, but the first screen remains immediately understandable.

### Surface 1 — Setup

`conduct init` becomes a guided, deterministic wizard with three choices:

1. **Claude Code → Codex Review → Human approval** (recommended);
2. **Single harness + human approval**;
3. **Empty/custom project**.

The wizard asks for display names and paths, validates the result, prints the
next command, and never asks for an API key. Advanced users may pass flags or
edit TOML directly.

### Surface 2 — Home / Attention

The first viewport answers only:

1. Is the project ready, active, blocked, or complete?
2. What needs my attention now?
3. What happens next?

It contains one project state, one prioritized `Needs you` list, and one
cycle preview. Counts and raw terminology are secondary.

### Surface 3 — Cycle

The graph shows simple sequences without pan/zoom and expands naturally for
parallel branches. Node status uses icon + label + color. Selecting a node
opens details; the graph itself is not edited in alpha.

### Surface 4 — Harness instance

One drawer uses progressive disclosure:

```text
Overview | Instructions | Capabilities | Activity
```

Overview shows name, harness type, role, current task/phase, freshness, and
readiness. Instructions groups model, prompt, and skills. Capabilities groups
tools and permissions. Activity shows causal events, not an unfiltered log.

### Surface 5 — Finding / decision

A finding card shows title and severity first. Expanding it reveals claim,
detail, evidence, reviewers, verdicts, `Why this state?`, and the next action.
Human gate actions use an explicit confirmation and create receipts.

### Surface 6 — Project health

Warnings, broken files, stale lanes, missing adapters, unsupported
capabilities, and configuration drift live in one health drawer. Health
problems link to a file, command, or owning instance.

## 6. Language for junior-friendly UI

Protocol terms stay precise in files and developer docs. Primary UI copy is
plain language:

| Protocol term | Primary UI copy |
|---|---|
| harness instance | Agent / participant, followed by its product name |
| lane | Current report |
| obligation | Required review |
| uncovered | No reviewer available |
| unreviewed | Waiting for review |
| disagreement | Reviewers disagree |
| stale | Has not reported recently |
| human gate | Your approval / decision |
| decision receipt | Decision record |

Technical terms may appear in tooltips and Advanced views. Brand accents help
orientation but never replace text, icons, or status semantics.

## 7. Alpha acceptance tests

### Five-minute junior test

A developer unfamiliar with HCP must be able to:

1. install or run the project;
2. select the recommended template;
3. open the panel;
4. identify which agent is working and what it is doing;
5. understand one finding and who must review it;
6. see the exact next action;

within five minutes, without reading the protocol specification.

### Honesty test

- No missing, stale, unsupported, or unknown state appears green.
- Every warning links to a cause and remediation.
- A human gate cannot pass without a receipt.
- A review cannot count as independent when the selected policy says it is
  not independent.
- Adapter failure does not erase the last known state; the UI marks its age.

### Portability test

- The recommended cycle works without a Conduct account or network access.
- Replacing Codex with a custom or Zo adapter requires no merger changes.
- Design configuration and prompts can be committed without secrets.
- A decision bundle is understandable without opening the live panel.

### Simplicity test

- No more than three top-level navigation destinations in alpha.
- The recommended cycle fits in the initial viewport.
- Advanced configuration is hidden until requested.
- Every visible control either works or is absent; no decorative disabled
  orchestration controls.

## 8. Priorities

### P0 — alpha differentiation

1. Preserve and finish current v1 correctness and author-specific prompts.
2. Guided `init` with a valid recommended template and first-run instructions.
3. Attention-first home with plain-language `why` and `next action`.
4. Harness instance drawer backed by current lane data and future-compatible
   capability fields.
5. Deterministic handoff packet and portable decision brief/report.
6. `conduct doctor` with actionable project and adapter readiness.

P0 is allowed to use v1-derived data. It must not pretend the v2 graph,
receipts, structured evidence, or runtime actions already exist.

### P1 — Protocol v2 decision foundation

1. Implement ADR 0001 entities and graph semantics.
2. Add structured evidence/provenance and configuration digests.
3. Add immutable human decision receipts and gate resolution.
4. Add adapter health and required-capability negotiation.
5. Add desired-versus-observed drift.
6. Add the first optional independent-review policy.

### P2 — safe control, after the decision foundation

1. Define adapter action envelopes for dispatch, pause, resume, retry, stop,
   and configuration proposals.
2. Require action preview, explicit permission, idempotency key, result
   receipt, timeout, and post-action verification.
3. Introduce cycle-run identity, history, resume/retry semantics, and frozen
   configuration snapshots.
4. Add optional time, token, and cost guardrails from adapter-reported data.
5. Add local notifications for human gates and failed actions.

### P3 — December Command v2

1. Ship the local Command Runtime and adapter SDK with capability manifests,
   health, action preview, idempotency, receipts, and post-action verification.
2. Deeply support two harnesses end-to-end first (Claude Code and Codex), then
   add Gemini CLI and OpenCode; add Cursor, Windsurf, Kimi Code, and Qwen Code
   only where a stable public integration contract exists.
3. Add the Cockpit command surface: message, dispatch, pause/resume/retry/stop,
   review request, harness switch, and verified handoff.
4. Add the four control modes from §4.10. New projects default to Observe;
   capability-scoped confirmation is the first writable mode.
5. Add run identity, frozen configuration snapshots, attempts, history,
   replay, and recovery after a local restart.
6. Add a visual Orbit editor for branches, parallel nodes, return edges, and
   human gates while preserving source view and committable configuration.
7. Pass the complete wow path in §4.11 with two real harness products on a
   clean local installation.

### Four-day December Command strike — owner directive 2026-08-11

The owner supersedes the 2026-08-10 calendar and requires a releasable,
high-quality December Command v2 technical preview within **3–4 calendar
days**. The functional target and product laws do not shrink: the result must
complete the wow path in §4.11. Speed comes from parallel delivery, a narrow
Policy mode, two deep adapters before breadth, and cutting polish before
safety. It is not permission to replace verified behavior with decorative
controls, fake integrations, or unreviewed autonomy. The binding execution
plan is `docs/plans/2026-08-11-december-command-v2-four-day-strike.md`.

The strike is successful only if it ships one end-to-end system containing:

1. Minimal reviewed v2 contracts for run identity, frozen configuration,
   adapter capabilities, action request/result receipts, human decisions, and
   observable verification.
2. A local Command Runtime with restart recovery, scoped process ownership,
   output streaming, cancellation, idempotency, and no secret material in
   project state.
3. Deep Claude Code and Codex adapters that complete dispatch, progress,
   handoff, review, stop/retry, and result receipt flows on real installations.
4. Capability-limited Gemini CLI and OpenCode adapters where their public
   interfaces support the same operations; an unsupported operation remains
   absent and does not block the two-adapter wow path.
5. Cockpit controls for message/follow-up, dispatch, pause/resume where the
   harness supports it, retry, stop, harness switch, review request, and Human
   Gate resolution.
6. Observe, Propose, and Confirm modes end-to-end. Policy mode ships narrowly:
   explicit per-Orbit allow-lists for non-destructive dispatch, review, retry,
   and notification actions only. It is not a general policy language.
7. Run history and causal replay sufficient to explain every transition in
   the wow path, including failed and superseded attempts.
8. A minimal visual Orbit editor for stages, edges, Harness assignments, and
   Human Gates. It supports the default linear cycle and a small parallel
   branch without becoming a general workflow programming environment.
9. Browser-level end-to-end tests for the command path, action authorization,
   no-motion-first-frame rule, failure recovery, and the complete two-harness
   demonstration.
10. English quickstart, threat model, clean-environment package smoke, and a
    recorded demonstration that finishes the §4.11 path in under ten minutes.

#### Parallel delivery lanes

- **Lane A — protocol/runtime:** v2 envelopes, receipts, run store, recovery,
  action authorization, and migration/tolerant reading.
- **Lane B — adapters:** adapter SDK plus Claude Code, Codex, Gemini CLI, and
  OpenCode capability implementations.
- **Lane C — Cockpit:** command surface, streaming, run history/replay, Orbit
  editor, and browser tests.
- **Lane D — integration/assurance:** threat model, sabotage/e2e tests,
  packaging, docs, demo fixtures, and daily integration.

All lanes branch from one recorded integration SHA and integrate at least
once per day. Editable-install provenance is printed in every isolated test
run. A lane never edits another lane's files in place.

#### Calendar

- **Day 1:** accept the five runtime ADR decisions; land v2 contracts, adapter
  SDK, run/receipt store, recovery, Observe, and Propose.
- **Day 2:** deep Claude Code and Codex prepare/execute/verify flows; Confirm,
  streaming, stop/retry, supported pause/resume, and Harness switching.
- **Day 3:** authenticated Cockpit commands, Human Gate receipts, history and
  replay, parallel execution, minimal Orbit editor, bounded proactivity, and
  narrow Policy mode. Feature freeze at the end of the day.
- **Day 4:** hostile review, cross-platform and browser wow-path tests, clean
  package, threat model, under-ten-minute demo, rename decision, tag/release.

After the Day-3 freeze, only a security, data-loss, protocol-integrity,
installation, or wow-path blocker can change the release candidate.
Guard-strength debt without a demonstrated product failure is recorded and
does not restart the strike.

### Later, deliberately not alpha

- drag-and-drop graph editing;
- conditional execution and a general scheduler;
- built-in chat or direct LLM calls from the merger;
- hosting, cloud storage, or broad SaaS integrations;
- multi-project analytics, teams, auth, and RBAC;
- adapter marketplace and public template gallery;
- trace warehouses, evaluation labs, and model leaderboards.

## 9. Follow-up architecture decisions

These topics must receive a separate ADR before P1/P2 implementation; they
must not be introduced by silently changing ADR 0001 or Protocol v1.

1. **Run identity.** ADR 0001 defers the assignment/run entity. Repeated cycle
   execution and reproducible reports eventually require a stable `run_id`.
   Recommended resolution: keep scheduling/assignment deferred, but reserve a
   run envelope for events and receipts before history ships.
2. **Narrow panel writes.** Recommended resolution: the panel remains
   read-only for agent-owned and design files, but may append human decision
   receipts through a validated local endpoint.
3. **Action protocol.** Recommended resolution: deterministic core stays pure;
   adapter actions are optional capability-gated commands with immutable
   request/result receipts.
4. **Evidence verification.** Recommended resolution: core records claims and
   digests; adapters/local readers report verification. Missing verification
   renders `unverified`, never `verified` by inference.
5. **Policy effects.** Recommended resolution: policies default to warnings;
   a policy blocks only when the project explicitly marks it `enforce`.

## 10. Implementation guardrails for Fable 5

- Treat ADR 0001 and Protocol v1 as compatibility contracts.
- Implement vertical slices in P0 order; do not start P2 execution work while
  the decision foundation is absent.
- Keep zero runtime dependencies and loopback-only operation for alpha.
- Do not add an LLM dependency for setup, summaries, explanations, handoffs,
  or reports; all are deterministic projections of project state.
- Reuse the existing merger as the only place for computed state.
- Add every new computed state to tests before panel rendering.
- Preserve unknown fields and tolerant-reader behavior.
- Every new empty/error/degraded state needs user-facing copy and a next step.
- Do not expose secrets, full private prompts, or chain-of-thought in reports.
- Do not add a UI control until its end-to-end action and failure state exist.

## 11. Competitive success condition

HCP does not win by matching Zo's number of tools or LangSmith's number of
traces. It wins when a user can connect the harnesses they already trust and,
in under five minutes, answer questions those products do not answer together:

- Who is responsible for this step?
- What exactly was reviewed, by whom, and with what evidence?
- Is the review independent enough for this risk?
- Why is the cycle blocked or contested?
- What does the human need to decide now?
- What configuration and project revision produced this decision?
- Can I carry the same control model to another harness or self-hosted
  environment without rebuilding the workflow?

That is the moat: **portable, explainable control over heterogeneous harness
systems, with project-owned truth and no silent consent.**
