# Public alpha scope — finish V1, then use it to build V2

**Owner decision, 2026-09-05:** close the nine findings from the `8dec0e4` review,
prove one useful independently checked result, and pass final review and owner
acceptance. This is the current delivery boundary, not another platform roadmap.
Nothing here declares a release, a green remote run, or completed manual acceptance.

## What remains non-negotiable in V1

The product is a local-first control plane for heterogeneous coding harnesses.
Its unit of value is a project decision across independent participants, supported
by evidence and explicit human responsibility — not a chat or a model leaderboard.
The principles in [product direction](specs/2026-08-03-product-direction.md) and
[HCP direction](specs/2026-08-03-hcp-competitive-product-direction.md) remain; their
dated capability labels and schedules are not today's completion report.

- A usable Workflow Studio: editable steps/connections, keyboard and pointer parity,
  clear participant/model choices, real parameter consumption, and an uncluttered
  first path. Drafts survive refreshes and concurrent request completions honestly.
- Bounded execution from immutable revisions: reached gates, conditions and loop
  bounds govern eligibility; no hidden authority escalation and no unbounded
  autonomous executor. A step starts only through a permitted road: a per-step
  confirmation, or a bounded automatic (Policy) run the owner authorized after
  reviewing its explicit limits. Under such a run routine steps start without
  per-action confirmation, human gates still wait for a person, and pause,
  resume and revoke are explicit controls.
- A real independent checker: a different participant, possibly on the same harness,
  judges the exact doer result and consumed materials under visible budgets. A
  process exit, a human approval and verified work remain three different facts.
- Studio-owned briefs, instructions and artifact inputs; exact preview binding;
  a contained working copy and an explicitly accepted result, never an automatic
  overwrite of the user's original repository.
- Historical journals and frozen revision bytes remain readable. New requirements
  use additive fields and explicit live refusals, not silent reinterpretation.

Completion is measured by [owner acceptance](owner-acceptance.md), including the
developer's real-result rehearsal and the owner's separate hands-on pass, plus
[release gates](release-smoke.md). A small V2 utility used in this acceptance
exercise is a test of V1's usefulness, not permission to start the V2 implementation.

## Preserve for V2 — do not reopen before alpha

- Additional harnesses, including the parked Qwen and GLM work; no new transport
  claim enters the alpha catalogue without its own reviewed real-install evidence.
- **Experience Ledger / evidence-weighted Harness Graph.** Preserve project-owned
  experience about immutable configurations, task classes, handoff edges, review
  complementarity and graph topology. Every inference must show sample size,
  supporting evidence, freshness and applicability. Unknown model versions remain
  unknown; changed configurations do not inherit unqualified trust. No private
  prompts, secrets, chain-of-thought, context-free ranking or silent model switch.
- Recommendations among configured participants, graph changes with preview and
  human authorization, marketplace/cloud work, and a general sandbox/worktree
  platform. None is smuggled into an alpha closeout fix.
- Export run brief is a useful next candidate, not a new condition of this release.

## Approved V2 directions: memory, measured improvement and human choice

These are planned directions, not shipped V1 features or promises of a particular savings percentage.

- **Qwen** is planned for V2; the V1 execution catalogue remains the five agreed harnesses.
- **Memory and portable handoffs:** keep the task goal, constraints, confirmed findings,
  open questions and references to original evidence available across participants and sessions.
- **Dream-RSI-inspired experiments:** use prior work to propose changes to the strategy
  around an existing harness. This does not require rewriting a vendor's agent.
- **SoL-Pi-inspired context handoffs:** first compare a full research handoff with a compact
  evidence-linked handoff on separate tasks. Preserve source access and initially keep
  the independent checker's inputs unchanged. Measure missed facts, result quality,
  corrections, time, resource use and human intervention, including the cost of summarizing.
  Batching actions, choosing compaction points and processing observations are additional
  experiments only where the harness exposes the necessary interface; installing one
  upstream extension does not optimize all five native harnesses automatically.
- **Human approval:** every strategy change is a proposal for the person to confirm.
  An experiment passing its checks does not grant permission to apply a new strategy.

Use V1 to help build V2. Establish reliable memory and measurable run history before
claiming self-improvement or moving a proposed optimization into ordinary work.

## Why the two older HCP editions disagree

The bundled edition was last updated by commit `47f5f9ffc44a4aab7bf1ebc866b6d508d2fb83b9`;
it retains the historical four-day strike. A later owner working copy, headed
**Updated 2026-08-24**, adds §4.12 Experience Ledger and a fourteen-day strike.
At this closeout that later file was untracked, not a committed revision; its
SHA-256 was `78f500d223f3c713748493c667d28bdb7a65603389db1cc18f466261389f3f1b`.
The ideas above preserve that later direction without rewriting either document
or pretending its calendar is a new deadline. The dated 2026-09-05 closeout decision
governs current delivery; the next-version ideas remain in this explicit queue.
