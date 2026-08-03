# ADR 0001 — Harness control-plane model

- **Status:** ACCEPTED — owner decisions 2026-08-02
- **Date:** 2026-08-02
- **Relates to:** `spec/PROTOCOL.md` (Protocol v1, normative),
  `docs/specs/2026-07-29-agent-conductor-design.md`
- **Scope:** model and vocabulary only; nothing is implemented now. Protocol
  v1 is never changed silently — the only v1 edit this ADR authorizes is the
  `row` deletion (§2). Fixtures and tests for the v2 schema come when the
  schema is implemented, not with this ADR.

## Context

Conduct v1 (alpha, M1–M4) is a decision dashboard: agents write lanes, a pure
merger computes disagreements, the human queue, and map status. The owner has
extended the vision: Conduct becomes a **self-hosted high-level control plane
for designing, operating, and observing harness systems** — users compose
their own agent work cycles (Claude Code, Codex, Cursor, custom harnesses),
build simple or complex workflow graphs, drill into each harness instance
(model, roles, prompts, skills, tools, permissions), tie workflows to the
architecture map, and control findings, reviews, decisions, runtime state.

Today's schema conflates the entities this future needs. `cycle.roles` welds a
process role to a harness brand (`id = "reviewer"`, `harness = "codex"`); the
cycle is a flat phase list with a single computed `current_phase`; all authors
share one `events.jsonl`; design and runtime live side by side in one
directory with one unified `map.toml`.

This ADR fixes the correct model now so nothing in the v1 alpha blocks it —
without implementing it now, and without changing Protocol v1 silently.

## Decision

Owner's explicit decisions (2026-08-02):

1. Role policies compile into canonical instance-level obligations.
2. v1 migration creates reviewer groups with `satisfaction = any`.
3. One runtime instance cannot occupy multiple cycle nodes in v2.0.
4. Branding is UI/adapter metadata, not normative protocol semantics.
5. A human-gate with no wait and no explicit decision is `idle` — absence of
   a record never means approval.

### 1. Vocabulary

Six terms, used consistently from now on in specs, code, and UI copy:

1. **Harness type** — a kind of integration/environment: `claude-code`,
   `codex`, `cursor`, `windsurf`, or `custom` (any adapter-provided type).
2. **Harness instance** (agent instance) — a concrete configured participant:
   instance id, display name, harness type, model, roles, prompt reference,
   skills, tools, permissions, adapter-specific settings. Examples:
   `claude-backend`, `codex-review`, `cursor-frontend`. The instance id is
   the lane author: v1's lane filename stem becomes the instance id verbatim.
3. **Role** — the instance's function in the process: `implementer`,
   `reviewer`, `security`, `planner`, `qa`, `release-owner`, or custom. A
   role is never welded to a harness brand; any type can hold any role, and
   an instance may hold several.
4. **Cycle** — an arbitrary workflow graph of harness instances, automated
   steps, and human gates. Not a ring, not a phase list.
5. **Lane** — the runtime state of one harness instance: current task, phase,
   findings, verdicts, waits, freshness, runtime events. Exactly one writer.
6. **Adapter** — the integration layer between Conduct and a harness type.
   It describes itself through a capability manifest (§6).

In these terms, v1's `cycle.roles` entry is a role and a harness type fused
into one object, with the lane author as the implicit instance.

### 2. Cycle model

The cycle becomes a directed graph. Minimal conceptual form:

```
cycle:       id, label, nodes
cycle node:  id, kind: harness | human-gate | check,
             harness_instance (optional; required for kind = harness),
             phase (label), depends_on, reviews, refs, metadata
```

Edges are expressed on nodes: `depends_on` entries are sequencing edges,
`reviews` entries are review edges; two edge kinds suffice today, so there
is no separate `edges` table, and `metadata` is the reserved extension
point. Optional `refs` ties a step to architecture-map node ids.

This supports sequential steps, parallel branches, review edges, human
gates, and many instances of one harness type. `kind = "check"` names an
automated non-harness step (CI job, script); its status source is
deliberately undesigned in v2.0. **No conditional-execution engine is
designed or implied** — conditional stages, when they come, will be node
metadata, not a scheduler. Conduct renders the graph read-only.

**Phase semantics.** Phase is a per-instance fact reported in each lane's
`now.phase`, matched against its cycle node's phase label. Intent for v2:

- Different instances being in different phases **simultaneously is normal**
  — it is the entire point of parallel branches.
- There may be **no global current phase at all**; multiple active phases are
  normal. v2 state has no `cycle.current_phase`.
- One instance's phase must **never silently overwrite another's by
  timestamp**. Recency never picks a winner across instances.
- The UI must be able to show parallelism and contested or ambiguous state
  (e.g. two lanes claiming one gate) — never collapse to a single value.

**Known v1 limitation.** Protocol v1 §6 defines exactly the rule being
deprecated: *current phase = the `now.phase` of the most recently updated
non-stale, non-future-dated lane* — a timestamp race between instances,
acceptable only while cycles are rings with one implicit token. Migration
note: v1 directories keep this rule unchanged; v2 state drops the field and
exposes per-instance phase only — which v1 `state.json` already carries in
`lanes[].now.phase`, so consumers can start reading the right thing today.
The in-flight alpha P0 work (Agents block showing per-lane phase,
author-specific prompts) are deliberate steps toward this model.

**Layout is not semantics (owner decision).** v1's `row` field is deleted
now — removed from the normative spec and examples; the legacy parser
accepts-and-ignores it **with a warning**. v2 uses separate layout hints:

```toml
[cycle.nodes.layout]
rank = 2
order = 1          # future: x / y / pinned
```

Graph semantics and visual placement are strictly separated; a cycle with no
layout block gets an automatic DAG layout.

**One node per instance (owner decision, v2.0).** Within a given cycle, one
runtime instance maps to exactly one cycle node. Allowing more creates
unresolvable ambiguity — which node owns `now.phase`, findings, verdicts,
staleness; two runs of one instance are indistinguishable. A harness *type*
may have unlimited instances; config reuse goes through profiles:

```toml
[[harness_profiles]]
id = "codex-review-default"
type = "codex"
model = "gpt-5"

[[harnesses]]
id = "codex-integration"
profile = "codex-review-default"

[[harnesses]]
id = "codex-security"
profile = "codex-review-default"
```

Explicitly deferred, not v2.0: an `assignment`/`run` entity (instance, cycle
node, assignment id, run id) making lanes assignment-keyed; likewise one
instance shared across *different* cycles with a single active assignment.

### 3. Review obligations — role policy compiled to instance semantics

Users author review policy at the role level; Conduct **normalizes** it into
canonical instance-level obligations. Declarative form:

```toml
[[roles]]
id = "reviewer"
reviews_roles = ["implementer"]
```

Canonical obligation form (computed, never authored):

```
obligation: id, finding-owner instance, reviewer group, group members,
            satisfaction: any | all | quorum,
            source: role-default | explicit-edge
```

- **v1 migration:** "role R reviews role A" compiles to — for each instance
  holding A — an obligation whose reviewer group is *all instances holding
  R*, with `satisfaction = any`. v1's "any lane holding role R satisfies the
  obligation" (§6) is preserved literally.
- **v2 explicit review edges** on cycle nodes create instance-level
  obligations directly (`source = explicit-edge`).
- **Review state is computed over obligations:** `uncovered` = reviewer
  group has no available instances; `unreviewed` = reviewers exist but the
  satisfaction policy is unmet; `agreed` = every obligation group satisfied
  by confirmed verdicts; `disagreement` = any foreign `partial`/`refuted`
  verdict exists. Observers can still dispute without holding an obligation.
- Runtime semantics no longer depends on implicit string-role matching.

### 4. Human gates — no pass from silence

A gate must **never** be inferred `pass` from the mere absence of an open
wait — that would make silence consent again. Gate lifecycle semantics:

| Condition | Gate state |
|---|---|
| no active wait and no decision receipt | `idle` (never pass) |
| open wait linked to the gate | `waiting` |
| upstream dependency blocked | `blocked` |
| explicit human decision/approval recorded | `satisfied` |
| explicit human rejection recorded | `failed/rejected` |

A durable decision receipt (e.g. `conductor/decisions/<decision-id>.json`)
will eventually be required: removing a wait clears the queue but does not
*record* the decision. v2.0 may keep gates visual-only; pass-from-silence is
forbidden.

### 5. File layout — design separated from runtime

Direction (names indicative, not final):

```
conductor/
  map.toml                    # architecture map (unchanged role: the project graph)
  cycles/release.toml         # workflow graphs — design-time, committed
  harnesses/claude-backend.toml   # harness instances — design-time, committed
  harnesses/codex-review.toml
  lanes/claude-backend.json       # runtime — one writer: that instance
  events/claude-backend.jsonl     # runtime — per-instance append-only log
  decisions/                      # human decision receipts (§4)
```

Rules the layout must satisfy:

- **Design/config is committable.** `map.toml`, `cycles/`, `harnesses/` are
  reviewed like code and travel through the repository.
- **Runtime state has a single unambiguous owner.** The filename stem is the
  instance id; only that instance writes its lane and its event log. One
  instance never edits another's lane — now structural for events too.
- **Secrets never appear in committed config.** Harness files carry model
  names, prompt paths, role labels — never API keys or tokens. Conduct never
  needs credentials; they stay in the harness's own environment.
- **A custom harness requires no core changes:** a harness file with
  `harness_type = "custom"` plus an adapter manifest (§6) is sufficient.
- **Existing v1 projects get a clear migration path** (next section); the
  single `events.jsonl` is not broken — dual-read is the mechanism.

`map.toml` keeps its v1 unified shape for now; v2 splits `[cycle]` into
`cycles/` and instance data into `harnesses/`, leaving the architecture map.

### 6. Capability-driven adapter manifest and branding

Each adapter describes itself; the panel renders only what the adapter
declares. Sketch:

```toml
id = "codex"
display_name = "OpenAI Codex"
harness_type = "codex"
docs = "https://..."
capabilities = ["model_selection", "roles", "prompts", "review",
                "runtime_events"]
# full vocabulary: model_selection, roles, prompts, skills, hooks, mcp_tools,
# permissions, runtime_events, review, start_stop, configuration_write

[branding]
monogram = "CX"
accent_light = "#10a37f"      # light/dark theme accents for the panel badge
accent_dark = "#1fc79a"

[runtime]
state_source = "lane"   # how runtime state is determined: lane file today;
                        # adapter-push / poll are future values

[config_fields]
model = { type = "string" }   # fields the drill-down may show/edit later
```

Custom adapters drop a manifest next to their harness files. The drill-down
UI shows only declared capabilities; unknown adapters get the neutral badge
and a minimal card. `start_stop` and `configuration_write` are **named
future capabilities only** — harness launching is not designed here.

**Branding precedence (owner decision — hybrid model):** project/user
override → adapter manifest branding → bundled known-harness registry →
deterministic custom fallback.

Conduct bundles a safe minimum only — harness type id, display name,
monogram, light/dark accent, documentation URL, adapter id — starter
registry: `CC` Claude Code, `CX` Codex, `CU` Cursor, `WS` Windsurf; no
official logos without license verification. Branding is UI/adapter
metadata, **never** normative merge semantics: the protocol stores only
`harness_type`, `adapter_id`, and an optional `branding_key`; the UI
enriches via the registry. Custom harnesses can always override display
name, monogram, and accent.

## Scenarios

Both mandatory validation scenarios, expressed in the proposed model with no
hardcoded special fields. Fixtures and tests follow with the implementation.

### Simple: Claude Code Dev → Codex Review → Human Gate

```toml
# conductor/harnesses/claude-dev.toml
schema_version = 2
id = "claude-dev"
harness_type = "claude-code"
model = "claude-opus-5"
roles = ["implementer"]
prompt = "prompts/dev.md"
```

```toml
# conductor/cycles/main.toml — inline node arrays; [[nodes]] is equivalent
schema_version = 2
id = "main"
label = "Dev → Review → Gate"
nodes = [
  { id = "dev", kind = "harness", harness_instance = "claude-dev", phase = "implement" },
  { id = "review", kind = "harness", harness_instance = "codex-review", phase = "review", depends_on = ["dev"], reviews = ["dev"] },
  { id = "ship", kind = "human-gate", label = "Owner approves release", depends_on = ["review"] },
]
```

### Complex: parallel branches, two instances of one type, security review

Cursor Frontend + Claude Backend in parallel → Codex Integration Review →
Human Release Gate; Claude Backend also feeds a Security Review held by a
**second claude-code instance** — two instances of one type in one cycle.

```toml
# conductor/cycles/release.toml   (refs tie steps to architecture-map nodes)
schema_version = 2
id = "release"
label = "Parallel build → integrated review → release"
nodes = [
  { id = "frontend", kind = "harness", harness_instance = "cursor-frontend", phase = "implement", refs = ["frontend"] },
  { id = "backend", kind = "harness", harness_instance = "claude-backend", phase = "implement", refs = ["api"] },
  { id = "integration-review", kind = "harness", harness_instance = "codex-integration", phase = "review", depends_on = ["frontend", "backend"], reviews = ["frontend", "backend"] },
  { id = "security-review", kind = "harness", harness_instance = "claude-security", phase = "review", depends_on = ["backend"], reviews = ["backend"] },
  { id = "release", kind = "human-gate", label = "Owner release decision", depends_on = ["integration-review", "security-review"] },
]
```

A custom harness slots into the same node with only a harness file:

```toml
# conductor/harnesses/sec-scan.toml — alternative security reviewer
schema_version = 2
id = "sec-scan"
harness_type = "custom"
adapter = "in-house-sast"
roles = ["security"]
```

While `frontend` and `backend` run, two lanes legitimately report different
phases at once; the panel renders both branches live and the gate `idle`
(§4 — never inferred pass) — read-only, with no orchestration engine.

## Migration & compatibility

**Protocol v1 is never changed silently.** Version 1 stays governed by
`spec/PROTOCOL.md` as written; v2 is a new schema read alongside it.

- v2 artifacts carry `schema_version = 2`. The v1 tolerant reader already
  accepts unknown versions with a per-file warning (spec §5), so v2 files
  next to v1 files degrade gracefully today instead of crashing anything.
- `state.json` §6.1 requires consumers to tolerate additional fields —
  additive v2 output (per-instance phases, cycle graph, manifest data) is
  legal without breaking v1 consumers.
- **Roles → instances.** Each v1 `cycle.roles` entry plus the lane holding
  it maps to one instance with a single role: instance id = lane author,
  harness type = the role's `harness` label, roles = `[role id]`. A declared
  role no lane holds maps to a placeholder instance named after the role.
  v1's role-level `reviews` DAG compiles into canonical obligations with
  `satisfaction = any`, per §3 — v1 semantics preserved literally.
- **Events dual-read.** The merger reads legacy `events.jsonl` and
  per-instance `events/*.jsonl` together, merged by timestamp; new writers
  append to their own file; the legacy file is retired when its authors stop.
- **CLI prompt transition (lands in the current P0, before v2).** The
  ambiguous positional is abandoned. Legacy/current form: `conduct prompt
  --role reviewer --author codex`; v2 form: `conduct prompt --instance
  codex-review` — the instance determines the author/lane path, harness
  type, roles, model, prompt, skills, review edges, pending obligations.
  The positional `conduct prompt reviewer` may be temporarily supported with
  a deprecation warning, but its meaning is **never silently re-defined**
  from role id to instance id.
- `conduct migrate` (one paragraph, future): reads a v1 `conductor/`, emits
  `cycles/default.toml` (v1 phases become a linear node chain over the
  migrated instances) and `harnesses/*.toml` with `schema_version = 2`,
  leaves every v1 file untouched, and prints what it inferred for owner
  review. Dual-read makes the transition incremental.

## v1 non-blocking checklist

Audit of the current alpha against this model:

| v1 decision (as shipped/in flight) | Verdict |
|---|---|
| `author` = lane filename stem, `[A-Za-z0-9_-]+` | **Forward-compatible.** Becomes the instance id verbatim; `lanes/claude-backend.json` is already the v2 naming. |
| `state.json` additivity + accept-with-warning versioning (§5, §6.1) | **Forward-compatible.** This is the mechanism that lets v2 artifacts and fields coexist with v1 readers. |
| Human queue computed from `waits_on_human`, never authored | **Forward-compatible.** v2 gate nodes are design-time markers; the queue stays lane-driven, so silence ≠ consent survives intact. |
| P0 in flight: author-specific prompts; Agents block with per-lane phase | **Steps toward this model.** Prompts keyed by instance rather than role, and per-instance phase in the UI, are exactly the v2 semantics. |
| `cycle.roles` (`id` + `harness` + `reviews`) | **Known v1 limitation.** Role and harness conflated; becomes sugar readable as instances-with-single-role; migration above unfuses it. |
| §6 current-phase timestamp rule | **Known v1 limitation.** Deprecated by §2 of this ADR; kept for v1 directories, absent from v2 state. |
| Single shared `events.jsonl` | **Known v1 limitation.** Violates single-writer; migrated via dual-read to per-instance logs. |
| Unified `map.toml` (nodes + cycle + invariants) | **v1 keeps it.** v2 splits cycle and instances out; `map.toml` remains the architecture map. |
| `row` layout field (spec sketch + `prompts.MAP_EXAMPLE`; unvalidated, unused by merge) | **Deleted (owner, 2026-08-02).** Removed from normative v1 and examples; the legacy parser accepts-and-ignores it with a warning. v2 uses separate non-semantic layout hints (§2). |

Nothing shipped in M1–M4 structurally blocks the v2 model.

## Non-goals now

The alpha stays a simple, functional product. Explicitly out of scope:

- No built-in chat or LLM calls from Conduct, ever.
- No agent spawning or scheduling; no harness start/stop implementation
  (`start_stop` is a named future capability only).
- No cloud sync, auth, or multi-user; no heavy analytics; no heavy UI
  frameworks.
- No lane or map editing from the panel; no drag-and-drop cycle builder.
- No conditional-execution engine.

## Consequences

- Every future feature names its entity precisely: drill-down targets an
  *instance*, badges come from an *adapter manifest*, graphs are *cycles*,
  runtime is a *lane*. Spec and UI copy stop saying "role" for three things.
- v1 keeps working unchanged; v2 lands as new files plus a merger that reads
  both. The cost is a dual-read window and a §6 rewrite (role-level review
  *policy* compiled into instance-level *obligations*, §3) — done openly in
  a Protocol v2 document, never as a silent edit.
- The panel gains obligations: render parallel phases, ambiguous instance
  states, gate lifecycle states, and capability-gated drill-downs, instead
  of one pulsing phase.
- The alpha needs no rework now; the P0 items in flight (per-lane phase in
  the Agents block, `--role`/`--author` prompt flags) already point the
  right way.
- Owner's closing principle: **v2 must remain an extension of "silence ≠
  consent", never its accidental weakening.** The obligation model (§3) and
  the gate lifecycle (§4) are the two places this ADR makes that guarantee
  structural rather than conventional.
