# agent-conductor — Design Specification

- **Status:** Draft for review
- **Date:** 2026-07-29
- **Package:** `agent-conductor` (PyPI, verified free) · **CLI:** `conduct` · **Brand:** Conduct
- **License:** MIT · **Language:** Python ≥ 3.11, zero runtime dependencies
- **Repository:** https://github.com/VasilyKolbenev/agent-conductor

> 2026-08-02: examples and §10 re-aligned with the de-voiced protocol and
> fictional demo (owner direction); row removed per ADR 0001.

## 1. Overview

Conduct is a local, decision-centric control plane for heterogeneous AI coding
agents. Several agents (Claude Code, Codex CLI, Cursor, a LangGraph graph, …)
work on one project; each writes its own **lane** — a small JSON file in an
agreed contract. A local panel merges the lanes and computes what no single
agent can see alone:

- **disagreements** — two lanes issuing conflicting verdicts on the same finding;
- **the human queue** — everything blocked on a human decision or action;
- **unreviewed claims** — findings the responsible reviewer never verdicted
  (*silence is never consent*);
- **project invariants** — statements that must stay true, checked per lane;
- **the live map** — the project's own roadmap/architecture nodes, lit by
  lane status.

Positioning in one line: *tracing tools (LangSmith, Langfuse, AgentOps) record
calls; Conduct tracks decisions.* It runs on `127.0.0.1`, reads files, and
needs no cloud, no account, and no API keys.

**Any popular vibe-coding tool can join, and they coordinate with each other
through Conduct while working on the same project.** Anything that reads and
writes project files — Claude Code, OpenAI Codex, Cursor, Windsurf, Cline,
aider, Devin — speaks the protocol directly via the universal prompt
contract (§9). Cloud builders that own their own sandbox (Lovable, Bolt,
v0) participate through the repository itself: `conductor/` is committed,
so their lane updates travel as ordinary commits and appear on the panel
after a pull. Conduct is the one place where heterogeneous tools *see each
other*: one tool's finding, another tool's verdict, the human's queue.

Tagline: **Your agents write lanes. You conduct.**

## 2. Goals and non-goals

### Goals (v0.1)

1. A published, versioned **protocol** (`spec/PROTOCOL.md`): map + lanes +
   events, with merge semantics defined normatively.
2. A **panel** served locally: map graph, cycle ring, KPI rail, human queue,
   computed disagreements, event feed. Live via SSE.
3. A **CLI** (`conduct`) with five commands: `init`, `up`, `demo`, `prompt`,
   `validate`.
4. The **universal adapter**: a state-aware prompt contract any file-writing
   agent can follow — no SDK required.
5. A **Claude Code adapter** (instructions + a mechanical heartbeat hook) and
   an **experimental LangGraph example**.
6. A **demo** (`conduct demo`) replaying a real multi-agent release-gate case.

### Non-goals (v0.1)

- Spawning or scheduling harness processes (Conduct never executes agents).
- Calling any LLM from Conduct itself, ever.
- Cloud sync, auth, multi-user, multi-project aggregation.
- History analytics / burn-down charts (the append-only event log accumulates
  the data from day one; rendering it is v0.2).
- Editing lanes or the map from the panel (the panel is read-only).

## 3. Core principles

1. **Files are the API.** Conduct only reads the `conductor/` directory. All
   intelligence lives in the user's agents; all integration lives in the
   protocol.
2. **Conduct never calls an LLM and never spawns processes.** Bootstrap and
   adapters work by *vending prompts* that the user pastes into their own
   tools.
3. **Computed, not authored.** Disagreements, staleness, the human queue and
   contested map nodes are derived by the merger from raw lanes. No author can
   bury a conflict by declining to write it down.
4. **Silence ≠ consent.** A finding without the responsible reviewer's verdict
   is surfaced as *unreviewed*, never treated as agreed.
5. **Tolerant reader, strict writer.** Agents SHOULD write atomically and
   validly; the panel MUST survive torn/malformed files by showing a "broken
   lane" state instead of crashing.
6. **Local trust model.** The server binds to `127.0.0.1` only. Anyone who can
   read the project's files can read the panel; no additional secrets exist.

## 4. The protocol

All state lives under `conductor/` in the **user's** project:

```
conductor/
  map.toml            the project map — source of truth (human- or agent-edited)
  lanes/<author>.json one file per participant; whole-file rewrite by its author only
  events.jsonl        append-only event log; any author; one JSON object per line
```

### 4.1 Why TOML (deviation from the approved sketch)

The design discussion said `map.yaml`. The Python standard library cannot
parse YAML, and zero runtime dependencies is a core principle, so the map is
**TOML** (`tomllib` is stdlib since Python 3.11 — hence the ≥ 3.11 floor).
TOML remains hand-editable and agent-writable. This is the only deviation
from the approved design.

### 4.2 `map.toml`

```toml
schema_version = 1
project = "web-app"

[[nodes]]
id = "schemas"
label = "shared contracts"
kind = "artifact"

[[nodes]]
id = "api"              # unique, referenced by lanes
label = "api build"
kind = "artifact"       # free-form: artifact | gate | component | doc | …
depends_on = ["schemas"]

[[cycle.roles]]
id = "implementer"
harness = "claude-code"  # informational
reviews = []             # role ids whose findings this role must verdict

[[cycle.roles]]
id = "reviewer"
harness = "codex"
reviews = ["implementer"]

[cycle]
phases = ["plan", "implement", "review", "human-gate"]
# Phases are labels; a "human gate" is simply a phase name. Dedicated
# human-gate objects were considered and cut (YAGNI): the human queue is
# built from lanes' waits_on_human, not from the map.

[[invariants]]
id = "main-untouched"
text = "main branch is never committed to directly"
```

Validation rules: `schema_version == 1`; node ids unique; `depends_on` and
`reviews` reference existing ids; at least one node. Everything else is
optional — a map with only nodes is valid.

### 4.3 Lane files — `conductor/lanes/<author>.json`

One author per file; the author rewrites the whole file each update (write to
a temp file, then rename, when the harness allows it).

```jsonc
{
  "schema_version": 1,
  "author": "claude",            // must equal the filename stem
  "role": "implementer",         // a cycle.roles id, or absent for observers
  "updated": "2026-07-29T21:20:00+03:00",
  "staleness_after_minutes": 360,   // optional; default 360
  "now": { "task": "fixing gate D", "since": "2026-07-29T20:00:00+03:00",
           "phase": "implement" },   // optional; must be a cycle.phases value
  "map_status": { "api": "pass", "smoke": "fail" },
  "findings": [
    {
      "id": "D-2",               // globally unique across lanes
      "title": "payment gateway config missing from the release image",
      "severity": "blocker",     // blocker | major | minor | note
      "claim": "defect",         // the author's own assessment (free-form label)
      "detail": "…",
      "evidence": "path/to/log or a reproduced command",
      "refs": ["smoke"]          // map node ids this finding touches
    }
  ],
  "verdicts": {
    "D-1": { "disposition": "confirmed", "note": "reproduced at …" }
  },
  "waits_on_human": [
    { "id": "w-config", "kind": "decision",
      "title": "Bake the payment config into the image or provision at deploy time?",
      "why": "Determines what D-2's fix looks like.", "blocks": ["D-2"] }
  ],
  "invariants": [ { "id": "main-untouched", "ok": true } ]
}
```

Closed vocabularies: `verdicts.*.disposition` ∈ `confirmed | refuted |
partial`; `map_status` values ∈ `pass | fail | blocked | running | idle`;
`waits_on_human.kind` ∈ `decision | action | review`. `blocks` and event
`ref` hold finding ids or map node ids.

**Finding lifecycle.** A finding is *open* while it is present in its
author's lane; the author resolves it by removing it (and SHOULD append an
`events.jsonl` entry, `kind: "ok"`, `ref: <finding id>`, saying why). A
verdict whose finding id no longer exists in any lane is a *stale verdict*:
surfaced in `warnings`, excluded from every computation.

### 4.4 `events.jsonl`

Append-only; one JSON object per line:

```json
{"ts":"2026-07-29T21:05:00+03:00","author":"claude","kind":"fail","text":"smoke failed on /live","ref":"D-1"}
```

`kind` ∈ `ok | fail | warn | stop | info`. Readers skip malformed lines and
report the skip count. The panel renders the most recent 500. Event lines
carry **no** `schema_version`: the log is versioned implicitly by the
protocol version of the `conductor/` directory it lives in.

### 4.5 Versioning

`map.toml` and every lane file carry `schema_version` (`events.jsonl` is
exempt — see §4.4). Version 1 is defined by `spec/PROTOCOL.md` in this
repository. The merger accepts version 1 and surfaces a per-file warning for
anything else (it does not guess).

## 5. Merge semantics (normative)

Input: parsed map + all lanes + events. Output: one `state.json`. All rules
are pure functions of the inputs (unit-testable without I/O):

| Computed | Rule |
|---|---|
| **Disagreement** | finding F (lane A) has a verdict from **any** other lane with disposition `refuted` or `partial` — observers included: a role-less lane can dispute, it just carries no review *obligation*. |
| **Unreviewed** | role R has `reviews` containing A's role, some lane holds role R, and **no** lane holding role R has a verdict for F (several lanes may hold the same role; any one of them verdicting satisfies the obligation). Distinct from agreement — rendered as "not reviewed". |
| **Uncovered** | role R with `reviews` ∋ A's role exists in the map but **no lane** holds role R — F is "review role absent", also never agreement. |
| **Review state (per finding)** | one value with precedence `suspended > disagreement > unreviewed > uncovered > agreed`: `suspended` for id-collided findings; `agreed` only when every reviewing role's obligation is met and every verdict on F is `confirmed`. Self-verdicts (a lane verdicting its own finding) are ignored in **all** review-state computation. A finding whose author's role is reviewed by nobody lands on `agreed` vacuously — this is intended, and the panel renders such rows as "no reviewer assigned" so the silence-≠-consent story stays visible. Per-author detail always remains visible in the finding's `verdicts`. |
| **Contested node** | two or more lanes report different `map_status` for the same node → state `contested`, listed with **all** disagreeing authors. No last-write-wins. |
| **Node status** | otherwise: the status from the most recently `updated` lane that mentions the node (future-dated lanes are excluded from this race — the clock-skew warning stands); nodes nobody mentions are `idle`. A node whose only voters are future-dated stays `idle`: the exclusion is total — a skewed clock never sets status unilaterally (mirroring the Current-phase rule; owner decision 2026-07-31). |
| **Current phase** | the `now.phase` of the most recently updated non-stale, non-future-dated lane that declares one; if no lane declares a phase, there is no current phase and the cycle renders statically. A `now.phase` naming no `cycle.phases` value (or any phase when the map declares none) is treated as undeclared, with a warning. |
| **Unknown referenced ids** | `map_status` keys, finding `refs`, and lane `invariants` ids that exist in no map are ignored for computation and reported in `warnings`. The invariant universe is the map-declared ids only. |
| **Human queue** | union of `waits_on_human` across lanes, keyed by id (same id in two lanes = one item, all sources listed). |
| **Invariant state** | per invariant id: `ok` only if every lane mentioning it says ok; a lane reporting `ok: false` marks it broken globally. |
| **Staleness** | `now - lane.updated > staleness_after_minutes` → lane flagged stale; its contributions render dimmed but still count. Clock skew (updated in the future) → warning, not an error. |
| **Broken lane** | unreadable/invalid JSON or author≠filename → lane listed as `broken` with the parse error; nothing else inferred from it. |
| **Unknown role** | a lane whose `role` names no `cycle.roles` id is treated as an observer (no review obligations attach to or from it) and produces a warning. |
| **Id collision** | the same finding id authored by two lanes → both surfaced, flagged `id-collision` in `warnings`; verdict attribution and disagreement computation are suspended for that id (they would be ambiguous) until the collision is fixed. |

KPIs derive from the above: nodes passed/total, open blockers (findings with
`severity: "blocker"` present in any lane), human-queue length, disagreement
count, broken lanes, stale lanes.

### 5.1 `state.json` shape (normative core)

The merger's output — the contract between `merge.py`, the panel, and any
third-party consumer of `/state.json`. Field list is normative; consumers
must tolerate additional fields:

```jsonc
{
  "schema_version": 1,
  "generated_at": "ISO8601",
  "project": "web-app",
  "map": { "nodes": [ { "id", "label", "kind", "depends_on": [],
                        "status": "pass|fail|blocked|running|idle|contested",
                        "contested_by": [] } ] },
  "cycle": { "phases": [], "roles": [ { "id", "harness", "reviews": [] } ],
             "current_phase": "implement" },        // absent if undeclared
  "lanes": [ { "author", "role", "updated", "stale": false,
               "broken": false, "error": null, "now": {} } ],
  "findings": [ { "id", "title", "severity", "claim", "author", "refs": [],
                  "verdicts": { "<author>": { "disposition", "note",
                                              "role": "reviewer or null" } },
                  "review_state":
                    "agreed|disagreement|unreviewed|uncovered|suspended" } ],
  "disagreements": [],      // the findings subset with review_state=disagreement
  "human_queue": [ { "id", "kind", "title", "why", "blocks": [], "sources": [] } ],
  "invariants": [ { "id", "ok", "broken_by": [] } ],
  "events_tail": [],        // newest-first, capped at 500
  "kpi": { "nodes_pass", "nodes_total", "blockers", "queue", 
           "disagreements", "broken_lanes", "stale_lanes" },
  "warnings": []            // id collisions, stale verdicts, skipped event lines, schema warnings
}
```

## 6. CLI

`conduct` is the single entry point (`[project.scripts]` → `conductor.__main__:main`).

| Command | Behavior | Exit codes |
|---|---|---|
| `conduct init` | Creates `conductor/` (refuses if it exists), writes a commented `map.toml` stub and an empty `lanes/`, then **prints the bootstrap prompt**: instructions for the user's own agent to read the project's roadmap/plan/architecture docs and generate a real `map.toml`. | 0 created · 1 already exists |
| `conduct up [--port 7777] [--dir PATH]` | `--dir` is the **project root** (the directory containing `conductor/`; default: cwd). Validates the map (refuses to start on a broken map with a clear error), then serves the panel on `127.0.0.1`. Watches `conductor/` by polling mtimes (0.5 s) and pushes SSE updates. If the map becomes invalid *while running*, keeps serving the last good map with a visible banner. | 0 on clean shutdown · 1 startup failure (port busy, invalid map) |
| `conduct demo [--port 7777]` | Copies the bundled demo fixture (via `importlib.resources`) into a temp directory and serves it read-only — the full experience with zero setup. | as `up` |
| `conduct prompt <role-id>` | Renders the **state-aware** prompt contract for that role from `map.toml` *and current lanes*: mission, lane file path, exact JSON schema template, the list of finding ids currently awaiting this role's verdict, valid map node ids. Deterministic template rendering — no LLM. Output to stdout for piping. | 0 · 1 unknown role or missing/invalid map |
| `conduct validate` | Schema-checks `map.toml` + all lanes + `events.jsonl`, then runs cross-file referential checks matching the merger's warning set (§5), including: verdict ids vs findings, `refs`/`map_status` keys vs map nodes, `now.phase` vs phases, lane `role` vs `cycle.roles`, lane invariant ids vs map invariants. Schema violations are **errors**; referential mismatches are **warnings** (they are legal runtime drift the merger tolerates, §5). CI-friendly. | 0 schema-valid (warnings allowed) · 1 schema errors |

## 7. Server

- stdlib `ThreadingHTTPServer`, bound to `127.0.0.1` only, `Cache-Control:
  no-store` everywhere.
- Routes: `/` (panel HTML), `/state.json` (merged state), `/lane/<author>.json`
  (raw lane passthrough, for "who wrote what"), `/events` (SSE stream;
  `EventSource` auto-reconnect), anything else → 404. No directory listing,
  no path traversal (author names validated against `[A-Za-z0-9_-]+`).
- SSE: the watcher thread stats `conductor/` files; on any mtime/size change
  it re-merges and broadcasts one `state` event to connected clients.
- **Periodic tick:** the watcher also re-merges every 60 s regardless of file
  changes — staleness is time-driven, and a lane that goes silent never
  touches a file, so a change-only watcher would never flip its stale flag.
  A tick broadcasts only if the merged state actually differs (the
  comparison excludes `generated_at`, which changes on every merge).

## 8. Panel

A single `panel/index.html` (vanilla JS, no CDN, no build step), packaged via
`importlib.resources`. English UI. Views, reusing the proven seed layout:

1. **Map graph** — SVG nodes/edges from the map, colored by computed status
   (`contested` gets a distinct treatment), click → detail card.
2. **Cycle ring** — roles/phases; the current phase (when lanes declare one,
   §5) pulses, otherwise the ring renders statically.
3. **KPI rail** — nodes passed, blockers, human queue, disagreements, broken
   lanes, stale lanes (mirrors `state.json.kpi`, §5.1).
4. **Human queue** — the owner's to-do; each item names what it blocks.
5. **Disagreements** — computed table: finding, claim, all verdicts with
   their notes. Includes *unreviewed* and *uncovered* rows so silence stays
   visible.
6. **Feed** — last events, newest first.

When `state.json.warnings` is non-empty, a warning banner with a count and a
click-through list renders above the views. `suspended` findings appear in
view 5 alongside the other non-agreed states.

Accessibility: status is never color-alone (glyph + text label), reduced
motion respected, keyboard focus visible. Dark/light via
`prefers-color-scheme`. Title shows the human-queue count.

## 9. Adapters

- **Universal (the default):** `conduct prompt <role>` output pasted into any
  harness's instructions. Works today for Codex CLI, Cursor, Windsurf, Cline,
  aider, Devin — anything that can write a file. Cloud builders without local
  filesystem access (Lovable, Bolt, v0) follow the same contract through the
  repository: `conductor/` is committed, lanes arrive as commits, and the
  panel picks them up on pull. Documented in `spec/PROTOCOL.md`.
- **Claude Code** (`adapters/claude-code/`): a skill/CLAUDE.md snippet
  carrying the same contract, plus an optional **Stop-hook heartbeat** — a
  shell one-liner appending a mechanical `{"kind":"info","text":"session
  active"}` event, so lane freshness works even between semantic updates.
  Honest split: hooks provide liveness; lane *content* comes from the model
  following the contract.
- **LangGraph** (`examples/langgraph/`, experimental): a callback handler
  mapping graph node transitions to `map_status` mechanically. An example,
  not a supported adapter.

## 10. Demo content

A fictional release-gate scenario: a gates pipeline with one smoke gate
failing, three blocker findings, a reviewer lane moving from silence
(rendered as *unreviewed*) to verdicts, one computed disagreement, and a
human queue with a genuine product decision. The structure is modeled on
real multi-agent coordination patterns; every project name, path, and
finding in the fixture is fictional.

## 11. Repository layout

```
agent-conductor/
  pyproject.toml            # zero deps; [dev] extra: pytest
  LICENSE                   # MIT
  README.md                 # EN; 60-second quickstart; GIF
  spec/PROTOCOL.md          # normative protocol v1
  src/conductor/
    __init__.py __main__.py # CLI dispatch (argparse)
    schema.py               # map/lane/event validation (pure)
    merge.py                # merge semantics (pure)
    prompts.py              # bootstrap + role prompt rendering (pure)
    server.py               # HTTP + SSE + file watcher
    demo.py                 # fixture copy + launch
  panel/index.html
  adapters/claude-code/
  examples/langgraph/
  demo/                     # fixture: map.toml + lanes/ + events.jsonl
  tests/
  docs/specs/               # this document
```

`schema.py`, `merge.py`, `prompts.py` are pure (no I/O) — the testable core.
`server.py` is the only I/O surface besides the CLI.

## 12. Testing

- **TDD throughout;** pytest is the only dev dependency.
- `merge.py`: golden tests for every rule in §5, including edge cases
  (broken lane, contested node, uncovered role, clock skew, duplicate
  human-queue ids).
- `schema.py`: a negative test per required field; unknown `schema_version`.
- `prompts.py`: golden output for a fixture map+lanes (state-awareness:
  pending verdict ids appear).
- `server.py`: loopback smoke — routes, 404s, author-name validation, SSE
  event on file change.
- `conduct validate` runs against `demo/` fixtures in CI (the demo can never
  drift from the schema).
- A mutation harness (dev script) flips each merge rule and asserts the
  golden tests go red — the KALI discipline carried over.

## 13. Milestones

1. **M1 — core:** `spec/PROTOCOL.md` + `schema.py` + `merge.py` green.
2. **M2 — CLI:** `validate`, `init`, `prompt` (state-aware).
3. **M3 — live:** `server.py` + panel generalized to map.toml, EN, SSE.
4. **M4 — demo:** fixtures + `conduct demo`.
5. **M5 — adapters:** Claude Code docs+hook; LangGraph example.
6. **M6 — launch:** README + GIF + PyPI publish (`0.1.0`) + announcement post.

Each milestone lands as reviewed commits; the panel is usable from M3.
M1–M4 form the single implementation plan; M5 and M6 are separable
follow-ups planned after M4 ships.

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Concurrent lane writes tear a file | whole-file rewrite + rename convention; reader tolerates and reports broken lanes |
| PyPI name squatted before launch | name verified free today; publish at M6, keep `openconductor` as checked fallback |
| Agents drift from the schema | `conduct validate` + state-aware prompts always restate the contract |
| Windows/Unix path differences | pathlib + tests run on both (CI matrix: windows-latest, ubuntu-latest) |
| SSE through odd proxies | loopback only — proxies aren't in the path |

## 15. Open questions

None blocking. Two owner sign-offs are scheduled inside milestones: demo
anonymization review (M4) and the announcement text (M6).
