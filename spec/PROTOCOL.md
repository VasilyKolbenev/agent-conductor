# agent-conductor Protocol — v1

- **Status:** Normative
- **Version:** 1
- **Governs:** `conductor/map.toml`, `conductor/lanes/<author>.json`,
  `conductor/events.jsonl`, and the merger's `state.json` output.

This document is the complete, standalone specification of protocol version
1. A reader with only this document can implement a conforming lane writer
  (an agent adapter that produces `conductor/lanes/<author>.json`) or a
  conforming merger (a program that reads `conductor/` and produces
  `state.json`), without consulting any other document.

Two principles govern every rule below:

- **Silence ≠ consent.** A finding without the responsible reviewer's
  verdict is surfaced as *unreviewed*, never treated as agreed. No
  participant can bury a conflict by declining to write it down —
  disagreements, staleness, the human queue, and contested nodes are
  *computed* by the merger from raw lanes, never authored directly.
- **Tolerant reader, strict writer.** Writers (agents producing lanes)
  SHOULD write atomically and validly. Readers (the merger and any other
  consumer of `conductor/`) MUST survive torn or malformed files by
  reporting a "broken lane" instead of crashing.

This document defines the file formats under `conductor/` and the merge
semantics that produce `state.json`. It does not define any particular CLI,
server, or panel — those are reference-implementation concerns; a
conforming lane writer or merger only needs what is written here.

## 1. Directory layout

All state lives under `conductor/` in the **user's** project:

```
conductor/
  map.toml            the project map — source of truth (human- or agent-edited)
  lanes/<author>.json one file per participant; whole-file rewrite by its author only
  events.jsonl        append-only event log; any author; one JSON object per line
```

## 2. `map.toml`

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

## 3. Lane files — `conductor/lanes/<author>.json`

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

## 4. `events.jsonl`

Append-only; one JSON object per line:

```json
{"ts":"2026-07-29T21:05:00+03:00","author":"claude","kind":"fail","text":"smoke failed on /live","ref":"D-1"}
```

`kind` ∈ `ok | fail | warn | stop | info`. Readers skip malformed lines and
report the skip count. Consumers render the most recent 500. Event lines
carry **no** `schema_version`: the log is versioned implicitly by the
protocol version of the `conductor/` directory it lives in.

## 5. Versioning

`map.toml` and every lane file carry `schema_version` (`events.jsonl` is
exempt — see §4). Version 1 is defined by this document. The merger accepts
version 1 and surfaces a per-file warning for anything else (it does not
guess).

## 6. Merge semantics (normative)

Input: parsed map + all lanes + events. Output: one `state.json`. All rules
are pure functions of the inputs (unit-testable without I/O):

| Computed | Rule |
|---|---|
| **Disagreement** | finding F (lane A) has a verdict from **any** other lane with disposition `refuted` or `partial` — observers included: a role-less lane can dispute, it just carries no review *obligation*. |
| **Unreviewed** | role R has `reviews` containing A's role, some lane holds role R, and **no** lane holding role R has a verdict for F (several lanes may hold the same role; any one of them verdicting satisfies the obligation). Distinct from agreement — rendered as "not reviewed". |
| **Uncovered** | role R with `reviews` ∋ A's role exists in the map but **no lane** holds role R — F is "review role absent", also never agreement. |
| **Review state (per finding)** | one value with precedence `suspended > disagreement > unreviewed > uncovered > agreed`: `suspended` for id-collided findings; `agreed` only when every reviewing role's obligation is met and every verdict on F is `confirmed`. Self-verdicts (a lane verdicting its own finding) are ignored in **all** review-state computation. A finding whose author's role is reviewed by nobody lands on `agreed` vacuously — this is intended, and consumers should render such rows as "no reviewer assigned" so the silence-≠-consent story stays visible. Per-author detail always remains visible in the finding's `verdicts`. |
| **Contested node** | two or more lanes report different `map_status` for the same node → state `contested`, listed with **all** disagreeing authors. No last-write-wins. |
| **Node status** | otherwise: the status from the most recently `updated` lane that mentions the node (future-dated lanes are excluded from this race — the clock-skew warning stands); nodes nobody mentions are `idle`. A node whose only voters are future-dated stays `idle`: the exclusion is total — a skewed clock never sets status unilaterally (mirroring the Current-phase rule). |
| **Current phase** | the `now.phase` of the most recently updated non-stale, non-future-dated lane that declares one; if no lane declares a phase, there is no current phase and the cycle renders statically. A `now.phase` naming no `cycle.phases` value (or any phase when the map declares none) is treated as undeclared, with a warning. |
| **Unknown referenced ids** | `map_status` keys, finding `refs`, and lane `invariants` ids that exist in no map are ignored for computation and reported in `warnings`. The invariant universe is the map-declared ids only. |
| **Human queue** | union of `waits_on_human` across lanes, keyed by id (same id in two lanes = one item, all sources listed). |
| **Invariant state** | per invariant id: `ok` only if every lane mentioning it says ok; a lane reporting `ok: false` marks it broken globally. |
| **Staleness** | `now - lane.updated > staleness_after_minutes` → lane flagged stale; its contributions render dimmed but still count. Clock skew (updated in the future) → warning, not an error. |
| **Broken lane** | unreadable/invalid JSON or author≠filename → lane listed as `broken` with the parse error; nothing else inferred from it. |
| **Unknown role** | a lane whose `role` names no `cycle.roles` id is treated as an observer (no review obligations attach to or from it) and produces a warning. |
| **Id collision** | the same finding id authored by two lanes → both surfaced, flagged `id-collision` in `warnings`; verdict attribution and disagreement computation are suspended for that id (they would be ambiguous) until the collision is fixed. |

**Clarification.** On an id collision, foreign verdicts remain visible on
both collided rows while `review_state` stays `suspended` for each — a
visibility policy, consistent with self-verdicts (per-author verdict detail
is never hidden from a finding's row).

KPIs derive from the above: nodes passed/total, open blockers (findings with
`severity: "blocker"` present in any lane), human-queue length, disagreement
count, broken lanes, stale lanes.

### 6.1 `state.json` shape (normative core)

The merger's output — the contract between a merger and any consumer of
`state.json`. Field list is normative; consumers must tolerate additional
fields:

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
