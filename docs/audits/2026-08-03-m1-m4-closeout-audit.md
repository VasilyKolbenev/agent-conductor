# M1–M4 Closeout Audit

- **Status:** Complete — findings recorded, nothing fixed here
- **Date:** 2026-08-03
- **Scope:** branch `feature/m1-m4`, HEAD `baffb92`
- **Method:** rule-by-rule read of `spec/PROTOCOL.md` §6/§6.1 against
  `src/conductor/merge.py` and `src/conductor/schema.py`, plus a named-test search across
  `tests/`. Gates re-run locally before publication.

This is an audit, not an implementation. Every gap below is recorded, not repaired. A row whose
verdict is *uncovered* or *partial* is a finding: the behaviour may well be correct, but no test
names it, so nothing stops a future edit from silently removing it.

---

## 1. Normative reconciliation — PROTOCOL §6 and §6.1 against `merge.py`

### 1.1 §6 merge semantics

| Rule (§6) | Implementation | Naming test(s) | Verdict |
|---|---|---|---|
| Disagreement: any *other* lane verdicts `refuted`/`partial`, observers included | `merge.py:215` (`_review_state`) | `test_merge_review.py::test_refuted_by_any_lane_is_disagreement`, `::test_observer_can_dispute_without_role` | covered |
| Unreviewed: reviewing role held by some lane, none of its holders verdicted | `merge.py:221-224` | `test_merge_review.py::test_silent_reviewing_role_is_unreviewed_never_agreed`, `::test_two_lanes_same_role_any_one_satisfies` | covered |
| Uncovered: reviewing role declared in map but held by no lane | `merge.py:219-220` | `test_merge_review.py::test_absent_reviewing_role_is_uncovered` | covered |
| Review-state precedence `suspended > disagreement > unreviewed > uncovered > agreed` | `merge.py:210-225` | `::test_id_collision_suspends_and_warns` (suspended > disagreement), `::test_unreviewed_beats_uncovered_on_the_same_finding` | **partial** — the `disagreement > unreviewed` and `disagreement > uncovered` edges have no test in which both conditions co-exist |
| `agreed` only when every obligation met and every verdict is `confirmed` | `merge.py:225`, `215` | `::test_confirmed_by_all_reviewing_roles_is_agreed` | covered |
| Self-verdicts ignored in **all** review-state computation, still visible | `merge.py:171`, `181` | `::test_self_verdict_visible_but_ignored_in_computation`; mutation *self-verdict exclusion dropped* | covered |
| Vacuously `agreed` when the author's role is reviewed by nobody | `merge.py:172`, `225` | `::test_finding_with_no_reviewing_roles_is_vacuously_agreed` | covered |
| Contested node: ≥2 differing `map_status`, all disagreeing authors listed, no LWW | `merge.py:127-128` | `test_merge_nodes.py::test_disagreeing_lanes_contest_the_node_with_all_authors`, `::test_agreeing_lanes_are_not_contested` | covered |
| Node status: most recently `updated` lane that mentions the node wins | `merge.py:130-131` | none — deliberately unobservable (recency only runs among agreeing voters; noted `merge.py:109-111`) | **uncovered by design** |
| Node status: future-dated voters excluded totally; sole-future voter stays `idle` | `merge.py:129`, `133` | `test_merge_nodes.py::test_future_dated_lane_excluded_from_race_but_counts_for_contested`, `::test_sole_future_voter_leaves_node_idle`; mutation *future-voter total exclusion dropped* | covered |
| Nodes nobody mentions are `idle` | `merge.py:133` | `test_merge_nodes.py::test_unmentioned_node_is_idle` | covered |
| Current phase: most recent non-stale, non-future lane declaring one | `merge.py:310-324` | `test_merge_queue_phase.py::test_current_phase_from_most_recent_declaring_lane`, `::test_stale_lane_does_not_set_current_phase`, `::test_future_dated_lane_does_not_set_current_phase`; mutation *future-exclusion dropped in `_cycle`* | covered |
| No lane declares a phase → field absent, cycle renders statically | `merge.py:322` | `test_merge_queue_phase.py::test_stale_lane_does_not_set_current_phase` (asserts key absence) | covered |
| `now.phase` naming no `cycle.phases` value → undeclared + warning | `merge.py:315-318` | `test_merge_queue_phase.py::test_unknown_phase_is_undeclared_plus_warning` | covered |
| Exact-`updated` tie breaks on phase-string order (documented, accepted) | `merge.py:321-323` | none — accepted as unspecified by §6 (see `f5da37b`) | **uncovered, documented** |
| Unknown referenced ids — `map_status` keys ignored + warned | `merge.py:117-120` | `test_merge_nodes.py::test_unknown_map_status_key_ignored_with_warning` | covered |
| Unknown referenced ids — finding `refs` dropped + warned | `merge.py:228-234` | `test_merge_review.py::test_unknown_finding_refs_dropped_with_warning` | covered |
| Unknown referenced ids — lane invariant ids ignored + warned | `merge.py:257-260` | `test_merge_queue_phase.py::test_unknown_invariant_id_ignored_with_warning` | covered |
| Human queue: union across lanes keyed by id, all sources listed | `merge.py:238-247` | `test_merge_queue_phase.py::test_queue_dedupes_by_id_and_lists_all_sources` | covered |
| Invariant state: `ok` only if every mentioning lane says ok; one `false` breaks it globally | `merge.py:251-264` | `test_merge_queue_phase.py::test_invariant_broken_by_one_lane_is_broken_globally` | covered |
| Staleness: `now - updated > staleness_after_minutes`, strict `>` | `merge.py:28` | `test_merge_lanes.py::test_stale_lane_flagged_by_default_threshold`, `::test_custom_staleness_threshold_respected`, `::test_staleness_boundary_exact_threshold_is_not_stale` | covered |
| Stale lanes render dimmed **but still count** | `merge.py:72` (`live` excludes broken only) | `test_merge_nodes.py::test_stale_lane_still_counts_for_node_status` | **partial** — only node voting is pinned; that stale lanes still contribute findings, verdicts, queue items and invariants is untested |
| Clock skew (future `updated`) → warning, not error | `merge.py:26-27` | `test_merge_lanes.py::test_future_dated_lane_warns` | covered |
| Broken lane: unreadable/invalid JSON or author≠filename → listed `broken`, nothing inferred | `merge.py:19-22` | `test_merge_lanes.py::test_broken_lane_is_listed_and_nothing_inferred`; `test_store.py::test_author_filename_mismatch_is_broken`, `::test_malformed_lane_becomes_broken_entry_not_crash` | covered |
| Unknown role → observer, no obligations either way, warning | `merge.py:147-151` | `test_merge_review.py::test_unknown_role_becomes_observer_with_warning` | covered |
| Id collision: both surfaced, `id-collision` warning, attribution + disagreement suspended | `merge.py:163-167`, `213-214` | `test_merge_review.py::test_id_collision_suspends_and_warns`; mutation *collision suspension dropped* | covered |
| Clarification: foreign verdicts stay visible on both collided rows | `merge.py:169`, `181` | `::test_id_collision_suspends_and_warns` (asserts `codex` present in both rows' verdicts) | covered |
| Stale verdict (finding id gone) → warning, excluded from every computation | `merge.py:198-200` | `test_merge_review.py::test_stale_verdict_warns_and_is_excluded` | covered |
| KPI `blockers` | `merge.py:86` | `test_demo.py::test_demo_state_tells_the_story` | covered |
| KPI `queue` | `merge.py:87` | `test_merge_queue_phase.py::test_queue_dedupes_by_id_and_lists_all_sources` | covered |
| KPI `disagreements` | `merge.py:88` | `test_merge_review.py::test_refuted_by_any_lane_is_disagreement`, `::test_id_collision_suspends_and_warns` | covered |
| KPI `broken_lanes` | `merge.py:89` | `test_merge_lanes.py::test_broken_lane_is_listed_and_nothing_inferred` | covered |
| KPI `stale_lanes` | `merge.py:90` | `test_merge_lanes.py::test_stale_lane_flagged_by_default_threshold` | covered |
| KPI `nodes_pass` / `nodes_total` | `merge.py:84-85` | **none** — no test names either field | **uncovered** |

### 1.2 §6.1 `state.json` shape

| Field | Implementation | Naming test(s) | Verdict |
|---|---|---|---|
| `schema_version` | `merge.py:93` | `test_merge_lanes.py::test_state_shape_minimum` (key presence only) | **partial** — the value `1` is not asserted |
| `generated_at` | `merge.py:94` | `test_merge_lanes.py::test_state_shape_minimum` (key presence only) | **partial** — neither the ISO format nor that it equals `now` is asserted |
| `project` | `merge.py:95` | `test_schema_hardening.py::test_every_optional_section_roundtrips_and_row_warns` | covered |
| `map.nodes[].status` incl. `contested` | `merge.py:134-136` | all of `tests/test_merge_nodes.py` | covered |
| `map.nodes[].contested_by` | `merge.py:128` | `test_merge_nodes.py::test_disagreeing_lanes_contest_the_node_with_all_authors` | **partial** — the test re-sorts the result, so the implementation's `sorted()` is not load-bearing |
| `map.nodes[].id/label/kind/depends_on` passthrough | `merge.py:134-136` | none naming `label`/`kind`/`depends_on` | **uncovered** |
| `cycle.phases`, `cycle.roles[].id/harness/reviews` | `merge.py:306-309` | none naming the roles passthrough shape | **uncovered** |
| `cycle.current_phase`, absent when undeclared | `merge.py:324`, `322` | `test_merge_queue_phase.py::test_current_phase_from_most_recent_declaring_lane`, `::test_stale_lane_does_not_set_current_phase` | covered |
| `lanes[].author/role/updated/stale/broken/error` | `merge.py:19-22`, `29-31`, `80-81` | `tests/test_merge_lanes.py` (all), `test_store.py` (broken paths) | covered |
| `lanes[].now` | `merge.py:31` | **none** | **uncovered + shape deviation** — §6.1 documents `"now": {}`, but `data.get("now", {})` returns `None` for a lane that writes `"now": null` (schema-legal, `schema.py:200-201` only rejects non-dict non-null). Verified by probe: `state["lanes"][0]["now"] is None`. Non-crashing — `_cycle` uses `(v["now"] or {})` and the panel uses `l.now \|\| {}` (`panel/index.html:646`) — but the emitted shape departs from the normative sketch and nothing pins it. |
| `findings[].id/title/severity/claim/author/refs` | `merge.py:174-181` | `tests/test_merge_review.py` (all) | covered |
| `findings[].detail` / `.evidence` | `merge.py:177-178` | `test_merge_review.py::test_finding_detail_and_evidence_carried_into_state`, `::test_finding_missing_detail_and_evidence_defaults_to_empty` | covered |
| `findings[].verdicts` keyed by author, `{disposition, note, role}` | `merge.py:202-206` | `test_merge_review.py::test_verdicts_keyed_by_author_with_role_inside` | covered |
| `findings[].review_state` five-value vocabulary incl. `suspended` | `merge.py:210-225` | the five state tests in `tests/test_merge_review.py`; `test_panel_smoke.py::test_panel_pins_review_vocabulary_tokens` for the consumer side | covered |
| `disagreements` (findings subset) | `merge.py:82` | `test_demo.py::test_demo_disagreement_is_d3_with_reviewer_partial` | covered |
| `human_queue[].id/kind/title/why/blocks/sources` | `merge.py:242-246` | `test_demo.py::test_demo_review_coverage_complete_and_queue_identity` | covered |
| `invariants[].id/ok/broken_by` | `merge.py:253`, `262-263` | `test_merge_queue_phase.py::test_invariant_broken_by_one_lane_is_broken_globally` | covered |
| `events_tail` newest-first | `merge.py:103` | **none** — `test_demo.py` asserts only the length | **uncovered** |
| `events_tail` capped at 500 | `merge.py:13`, `103` | **none** — no fixture exceeds 500 events | **uncovered** |
| `warnings` | `merge.py:64-69`, throughout | many, incl. `test_merge_lanes.py::test_extra_warnings_flow_into_state`, `::test_skipped_events_produce_a_warning` | covered |

**Section 1 tally:** 47 rows — 38 covered, 6 partial, 3 uncovered (one of those uncovered by
design and one accepted-and-documented).

---

## 2. Container-field audit rider

The four crash-shape defects fixed during M1 (`72c2d5a`, `cab5658`, `88c1188`, `7fa066f`) all had
the same root cause: a container-typed field iterated without a shape guard. This rider enumerates
every container field in the protocol and asks whether a wrong-shape value is pinned by a test.

| Field | Guard | Wrong-shape test | Verdict |
|---|---|---|---|
| map `nodes` (list, non-empty) | `schema.py:46-48` | `test_schema_map.py::test_empty_nodes_is_error` | **partial** — only the empty-list case; a scalar `nodes` shares the same message and is untested |
| map `nodes[]` element | implicit — `isinstance(n, dict)` at `schema.py:52`, `60-61` | none | **uncovered** |
| map `nodes[].depends_on` | `schema.py:70-72` (list), `74-77` (element) | `::test_depends_on_scalar_is_single_error`, `::test_depends_on_nested_list_element_is_clear_error_not_crash` | covered |
| map `cycle` (table) | `schema.py:84-86` | `::test_cycle_scalar_is_error` | covered |
| map `cycle.phases` | `schema.py:120-123` | `::test_phases_scalar_is_error`, `::test_phases_with_non_string_element_is_error` | covered |
| map `cycle.roles` | `schema.py:90-93` | `::test_roles_scalar_is_error` | covered |
| map `cycle.roles[]` element | implicit — `isinstance(r, dict)` at `schema.py:95`, `103-104` | none | **uncovered** |
| map `roles[].reviews` | `schema.py:109-112` (list), `113-116` (element) | `::test_reviews_scalar_is_single_error`, `::test_reviews_nested_list_element_is_clear_error_not_crash` | covered |
| map `invariants` | `schema.py:130-132` | `::test_invariants_scalar_is_error` | covered |
| map `invariants[]` element | implicit — `isinstance(inv, dict)` at `schema.py:135` | none | **uncovered** |
| map top level | `schema.py:167-168` | none at schema level (unreachable via `store`: `tomllib` always yields a table) | **uncovered, unreachable** |
| lane `now` | `schema.py:200-202` | `test_schema_lane.py::test_now_scalar_is_single_error` | **partial** — `now: null` is accepted and reaches state as `None`; see §1.2 |
| lane `map_status` | `schema.py:208-211` (dict), `_in_vocab` at `212-215` | `::test_map_status_scalar_is_single_error`, `::test_unhashable_map_status_value_does_not_crash` | covered |
| lane `findings` | `schema.py:221-224` | `::test_findings_scalar_is_single_error` | covered |
| lane `findings[]` element | implicit — `isinstance(f, dict)` at `schema.py:227` | none | **uncovered** |
| lane `findings[].refs` | `schema.py:244-253` | `::test_refs_scalar_is_single_error`, `::test_refs_null_is_error_not_crash_downstream`, `::test_refs_non_string_element_is_clear_error`, `::test_refs_absent_is_fine` | covered |
| lane `findings[].severity` (closed vocab) | `_in_vocab`, `schema.py:234` | `::test_bad_severity_is_error`, `::test_unhashable_finding_severity_does_not_crash` | covered |
| lane `verdicts` (object) | `schema.py:259-262` | `::test_verdicts_non_dict_is_single_error` | covered |
| lane `verdicts[<id>]` value | `schema.py:264` (`isinstance(v, dict)` fused with `_in_vocab`) | `::test_bad_disposition_is_error`, `::test_unhashable_verdict_disposition_does_not_crash` | **partial** — a scalar verdict value (e.g. `"confirmed"`) hits the same fused branch but no test names it |
| lane `waits_on_human` | `schema.py:272-275` | `::test_waits_scalar_is_single_error` | covered |
| lane `waits[]` element | implicit — `isinstance(w, dict)` at `schema.py:278` | none | **uncovered** |
| lane `waits[].blocks` | `schema.py:288-297` | `::test_wait_blocks_scalar_is_single_error`, `::test_wait_blocks_null_is_error`, `::test_wait_blocks_non_string_element_is_clear_error`, `::test_wait_blocks_absent_is_fine` | covered |
| lane `waits[].kind` (closed vocab) | `_in_vocab`, `schema.py:285` | `::test_bad_wait_kind_is_error`, `::test_unhashable_wait_kind_does_not_crash` | covered |
| lane `invariants` | `schema.py:303-306` | `::test_invariants_scalar_is_single_error` | covered |
| lane `invariants[]` element | `schema.py:307-310` (explicit dict + id + bool ok) | none | **uncovered** |
| lane top level | `schema.py:334-335` | `test_store.py::test_non_dict_lane_json_is_broken_not_crash` | covered |
| event object | `schema.py:359-360` | none — `test_schema_lane.py::test_event_line_valid_and_invalid` passes a dict with bad fields; `test_store.py::test_valid_json_but_invalid_event_is_counted_as_skipped` likewise | **uncovered** — a JSON line that parses to a list/scalar is tolerated by the guard but nothing pins it |
| event `kind` (closed vocab) | `_in_vocab`, `schema.py:365` | `::test_unhashable_event_kind_does_not_crash` | covered |

**Section 2 tally:** 28 fields — 18 covered, 3 partial, 7 uncovered (one of them unreachable in
practice). All seven uncovered guards exist in code; none is exercised by a wrong-shape test. Note
that every uncovered row is an *implicit* guard — a bare `isinstance(x, dict)` inside a loop — which
is precisely the shape of guard that the four earlier crash defects taught us to distrust.

---

## 3. Deviations from the approved plan

Plan of record: `docs/plans/2026-07-30-m1-m4-implementation.md`. Its three up-front
`[plan decisions]` (`store.py` added to the module list, demo fixtures inside the package,
panel inside the package) are the plan's own text and are not repeated as deviations.

| # | Deviation | Reason | Authorized by |
|---|---|---|---|
| 1 | `store.load()` split into `_load_map` / `_load_lanes` / `_load_events` | The reference block was one long function; the split matches the file-size and function-size guards | Plan's own Task 10 deviation note (lines 1351-1355) |
| 2 | All three store readers catch `UnicodeDecodeError`/`OSError`; unreadable `events.jsonl` warns instead of raising | The plan's reference block crashes on invalid UTF-8 — a tolerant-reader violation | Task 10 deviation note; commit `e681df6` |
| 3 | Store-produced lane errors carry the `lane <stem>:` prefix | Consistency with schema-produced errors so CLI output has one voice | Task 10 deviation note |
| 4 | `AUTHOR_RE` anchored (`^…$` verified under `.match` too) | Defense-in-depth for the `/lane/<author>.json` URL guard | Commit `a6da1a9` (review finding) |
| 5 | `_MAP_EXAMPLE` promoted to public `prompts.MAP_EXAMPLE` | `conduct init` scaffolds from the same constant the bootstrap prompt vends, so the two can never drift | Commit `e82434a`; pinned by `test_cli.py::test_init_then_validate_is_clean` |
| 6 | `_LANE_TEMPLATE` (the commented §3 JSONC excerpt) deleted; replaced by a `json.dumps` strict-JSON template | The commented excerpt had JSONC comments, a hardcoded `claude` author and fictional node ids — an agent copying it verbatim produced a broken lane | Commit `7c99347`; pinned by `test_prompts.py::test_role_prompt_template_is_copy_safe_strict_json`, `::test_role_prompt_has_no_commented_spec_template` |
| 7 | `conduct prompt <role>` positional → `--role` / `--author`; positional kept with a stderr deprecation warning | The positional is ambiguous once instances exist; ADR 0001 forbids silently redefining it | ADR 0001 "CLI prompt transition"; commit `7c99347` |
| 8 | `Watcher._stop` renamed to `_stop_event` | `threading.Thread.join()` calls the private `self._stop()` on Python ≤ 3.12; the attribute shadowed it and broke all four CI jobs | Commit `250e655` (CI failure, 14 tests) |
| 9 | `ThreadingHTTPServer.allow_reuse_address = os.name != "nt"` | On Windows `SO_REUSEADDR` permits double-binding the same port, hiding a port conflict | Commit `590f735`; pinned by `test_server.py::test_busy_port_raises_instead_of_double_binding` |
| 10 | `row` removed from the protocol; the parser accepts-and-ignores it with a warning | Layout is not semantics; v2 uses separate layout hints | ADR 0001 §2 + v1 checklist (owner decision, 2026-08-02); commits `b9a3bf5`, `e82434a` |
| 11 | Findings gained `detail` and `evidence` in `state.json` §6.1 (additive) | External review: state showed verdicts without the grounds behind them | Commit `6b3ee81`; type-checked at the boundary in `1e7c28a` |
| 12 | Demo re-themed from the real voice-app case to a fictional web project | Owner direction, 2026-08-02 — structure, counts, review pattern and the plan's mandated assertions unchanged | Plan's Task 15 deviation note (lines 1622-1624); commits `5637c5a`, `1e7189e` |
| 13 | Mutation harness grew from the planned 5 mutations to 8 | `pending_verdicts` needed its own self-verdict and suspended-skip mutants after `0dd5648` | Commits `eac7dbc`, `2929e8f`, `0dd5648` |
| 14 | Panel exempted from the 800-line file cap, ceiling raised to 1600 | Single-file vanilla-JS panel with no build step; owner-granted on conditions: clear sections, no minification, smoke tests, architecture re-review near 1600 | Owner decision in session — **not recorded in any committed artifact** (see §4) |
| 15 | `_findings` split into `_index_findings_and_verdicts` + `_review_state` + `_findings` | Quality review: radon E/37, C901 17>10, 5 nesting levels on the single-function shape | Recorded inline in the plan's Task 7 Step 3; refactor pin test `::test_unreviewed_beats_uncovered_on_the_same_finding` |

---

## 4. Known gaps and non-blockers carried into the next chunk

1. **ruff: 34 findings** (13 `I001` import sorting, 13 `UP017` `datetime.UTC` alias, 5 `ISC004`,
   1 `RUF059`, 1 `DTZ001`, 1 `PLW1510`). Only 3 are in `src/` (all `UP017`); the rest are in
   `tests/` and `scripts/`. Not blocking: `pyproject.toml` declares no `[tool.ruff]` section and CI
   runs no lint step, so this is ruff's default rule set applied to a project that never opted in.
   Left unfixed by design — this audit does not touch code.
2. **mypy absent.** No `[tool.mypy]` config, no CI type-check job. Not blocking: the codebase is
   annotated throughout and the runtime is stdlib-only; adding the gate is a separate chunk.
3. **Invariant `text` is not carried into `state.json`.** `_invariants` (`merge.py:253`) emits only
   `id`/`ok`/`broken_by`, which is exactly what §6.1 specifies — so this is a *spec* gap, not an
   implementation bug. Consequence: the panel's broken-invariant row shows the id plus the voting
   authors and cannot show the human-readable rule text. Not blocking: the id is meaningful and the
   text lives in the committed `map.toml`.
4. **`detail`/`evidence` type-checking — already fixed, not a gap.** Verified: `1e7c28a` added the
   guard at `schema.py:240-243`, pinned by
   `test_schema_lane.py::test_non_string_detail_and_evidence_are_errors`. Recorded here only
   because it appeared on the carry-forward list.
5. **`events.jsonl` per-author split deferred to v2.** The single shared log violates the
   single-writer rule. Not blocking: ADR 0001 §5 records it as a known v1 limitation with a
   dual-read migration path; nothing in v1 depends on the split.
6. **The five ADR 0001 follow-ups**, all explicitly deferred and none load-bearing for the alpha:
   run/assignment identity (ADR §2, "explicitly deferred, not v2.0"); narrow panel writes (the
   panel is strictly read-only today, ADR "Non-goals"); the action protocol / harness `start_stop`
   (a named future capability only, ADR §6); evidence verification (Conduct records the evidence
   pointer, it never verifies it); policy effects — role policy compiled into instance-level
   obligations (ADR §3, arrives with the v2 schema).
7. **Human decision receipts are not durable.** Removing a wait clears the queue but records no
   decision (ADR 0001 §4). Not blocking: v1 never claims a gate passed — absence is rendered as
   absence.
8. **Discovered in this audit:**
   - `lanes[].now` can be `null` in `state.json` where §6.1 sketches `{}` (see §1.2). Non-crashing;
     every current consumer defends with `or {}`. Not blocking, but the shape is unpinned.
   - `events_tail` ordering and the 500-cap are both unpinned (§1.2). The cap is a one-line slice;
     a regression would be silent until a project accumulates >500 events.
   - `kpi.nodes_pass` / `kpi.nodes_total` are unpinned (§1.1) — the only two KPI fields without a
     naming test.
   - Seven implicit container-element guards have no wrong-shape test (§2). This is the exact
     category that produced the four crash-shape defects earlier in M1.
   - The panel line-cap exception (800 → 1600) exists only in session history. Grepping the tracked
     tree for `1600` returns nothing outside `.venv/`. A future contributor reading the global
     800-line rule will see `panel/index.html` at 829 lines as a violation with no recorded waiver.
   - CI last ran on `250e655`; the five commits from `7c99347` to `baffb92` are unpushed and
     therefore have no CI evidence (see §5).

---

## 5. Gate results snapshot

| Gate | Result |
|---|---|
| Full suite (`.venv\Scripts\python -m pytest -q`) | **198 passed** in 13.40 s (local, Python 3.14 venv) |
| Mutation harness (`.venv\Scripts\python scripts\mutate_merge.py`) | **8/8 mutations killed** |
| Mutations killed | disagreement drops `partial`; self-verdict exclusion dropped; collision suspension dropped; stale lanes skipped in `_nodes`; future-exclusion dropped in `_cycle`; future-voter total exclusion dropped in `_nodes`; `pending_verdicts` self-verdict exclusion dropped; `pending_verdicts` suspended-skip inverted |
| CI run | https://github.com/VasilyKolbenev/agent-conductor/actions/runs/30758291260 — **success**, 52 s |
| CI jobs | `test (ubuntu-latest, 3.11)` ✓ 25 s · `test (ubuntu-latest, 3.12)` ✓ 26 s · `test (windows-latest, 3.11)` ✓ 48 s · `test (windows-latest, 3.12)` ✓ 49 s |
| CI commit | `250e655` — **five commits behind HEAD**; `7c99347`, `0796290`, `fe50e0f`, `3c693e8`, `b4dbee2`, `baffb92` are local-only. Push before merging so the PR carries CI evidence for the code it ships. |
| Matrix | `{ubuntu-latest, windows-latest}` × `{3.11, 3.12}`, `fail-fast: false` |
| CI steps beyond pytest | mutation harness, demo drift gate (`conduct validate` on a materialized demo), wheel smoke (build → reinstall from `dist/` → import all modules → `conduct validate`) |
| CI annotations | Node.js 20 deprecation notice on `actions/checkout@v4` and `actions/setup-python@v5` (informational; jobs forced to Node 24) |
| Panel line count | `src/conductor/panel/index.html` — **829 lines** (over the 800 global cap, under the owner-granted 1600 ceiling; the waiver itself is unrecorded — §4) |
| Largest file check | Panel 829 · `schema.py` 369 · `server.py` 356 · `merge.py` 325 · `prompts.py` 220 · `__main__.py` 200. Every Python module is comfortably under 800; the panel is the only file needing the exception. |
| Ruff | 34 findings, 3 of them in `src/` — see §4.1. Not run in CI. |
| Working tree | Clean apart from the untracked `docs/specs/2026-08-03-hcp-competitive-product-direction.md` (another session's file — deliberately not staged with this audit). |
