# Wizard fixtures (stand-ins)

Answers of the reads the new-task wizard makes, written by lane D2 from the spec so the
wizard's model and its browser tests run before the routes exist. They are STAND-INS: a
route's own fixture, when its lane delivers one, replaces the file of the same read, and a
difference is settled in the fixture or in the route, on the record.

| File | Read | Spec |
|---|---|---|
| `git_<state>.json` (eight files) | `GET /command/project/git`, one per `state` | 6.2.1 |
| `documents.json`, `documents_truncated.json` | `GET /command/project/documents` | 6.2.2, 9.5 |
| `document.json` | `GET /command/project/documents/<doc_id>` | 9.5 |
| `workflows.json`, `workflows_served.json` | `GET /command/workflows`: rows, `starters`, `providers`; the second without the two owed provider facts (below) | 7.9, 5.6.6 |
| `runs.json` | `GET /command/runs` (the keys the preselection reads) | 7.10 |
| `project_cycle.json`, `project_cycle_none.json` | `GET /command/project/cycle`, pinned and not | 7.10 |
| `tasks.json` | `GET /command/tasks` (the title in the preselection's label) | 7.10 |
| `quotas.json` | `GET /command/quotas` (the keys the roles step reads) | 5.6.6, 6.3 |
| `previous_run.json`, `previous_revision.json` | `GET /command/runs/<id>` and `GET /command/workflows/<id>/revisions/<n>` of the last run | 7.10 |
| `flow_state_none.json` | `GET /command/workflows/<id>/flow` of a workflow with neither a draft nor a revision: `source: "none"`, `flow: null`, `draft_digest: null` (the `workflow_id` is overwritten per cycle) | 7.1 |

The provider rows of `workflows.json` are the server's own (`provider_projection`: `provider_id`,
`display_name`, `availability`, `implementation`, `auth`, `controls`, `vendor_sandbox`; the roads a
harness has are its `controls`) plus two facts that are still OWED by the server, lane L's to add:
`offered` (whether this version offers the harness, the owner's list) and `task_channel` (how it is
fed, in the shape `studio-automation-providers.js` already judges). `workflows_served.json` is the
same answer with exactly what the server serves today, without the two owed facts. The wizard treats
a row without `offered: true` as not offered, and a roster whose rows lack either fact as "not yet
served", which is not "no harness configured". `tests/test_desk_wizard_roster.py` holds both files
to the real projection: keys, and the roads of every harness this build has.

The flow answers (`FlowState` and `Budget` of the five cycles) are lane L's, in
`tests/fixtures/flow/`; the wizard reads those unchanged.

## Steps 5 and 6: the preparation read, the preview and the queue read

Lane L builds these three reads in parallel; the wizard (lane D2) is built on the shapes below,
taken literally from the spec (v3.1, `docs/specs/2026-09-28-v1-desk-redesign-design.md`; the line
numbers are that file's). The VALUES are invented (digests are patterned placeholders, times are
2026-09-29); the KEYS and the structure are the spec's. `tests/test_desk_wizard_fixtures.py` holds
every file to the closed key sets written by hand from the same lines, so a stand-in cannot drift;
when L's own fixture arrives it replaces the file of the same read, and a difference is settled in
the fixture or in the route, on the record.

| File | Read | Where each field comes from |
|---|---|---|
| `preparation_new.json`, `preparation_seeded.json`, `preparation_run_created.json`, `preparation_documents_missing.json`, `preparation_ready.json`, `preparation_queued.json`, `preparation_authorized.json`, `preparation_ended.json`, `preparation_two_runs.json` | `GET /command/tasks/<task_id>/preparation` | 6.4.2, lines 2984-2994 (the JSON: `task`, `seed`, `next_run_number`, `runs[]` with `run_id`, `created_at`, `workflow_id`, `revision`, `stage`, `missing {instructions [{node_id, instruction_ref}], inputs}`, `grant`, `queue`); lines 2996-3009 (`seed`: the seed record of 9.1.5, lines 4289-4301, plus `state`; `next_run_number` counts unreadable runs, line 2999; `stage`: the first of `ended`, `queued`, `authorized`, `documents_missing`, `ready_to_preview`, lines 3000-3005; `grant`: line 3007; `queue`: line 3008). `preparation_documents_missing.json` is the example of lines 2984-2994 as it stands. `preparation_two_runs.json` is a task whose third run is unreadable, so `next_run_number` is 4. |
| `preview_standard.json`, `preview_replacing.json`, `preview_exhausted.json` | `POST /command/runs/<run_id>/automation/preview` with body `{}` | 6.4.4, lines 3049-3051 (the answer is the old five keys, `terms`, `preview_digest`, `previewed_at`, `provider_facts`, `valid_until`, plus `budget`; `budget` is in neither `terms` nor the digest); 7.8, lines 3588-3602 (the `Budget` form: copied unchanged from `tests/fixtures/flow/`); `terms` = the fourteen fields the run terms hold (`command/policy_preview.py` `build_preview`) plus `duration_seconds`, its five preview numbers equal to `budget.terms_draft` (6.4.4, line 3050); `valid_until` is 300 s after `previewed_at` (6.4.5, line 3099). The replacing and exhausted files are the two `Budget`s of `tests/fixtures/flow/desk-standard.budget-replacing.json` and `desk-short.budget-exhausted.json` (6.4.4, lines 3075-3082). |
| `queue_free.json`, `queue_busy_waiting.json`, `queue_busy_running.json`, `queue_stuck.json`, `queue_view.json`, `queue_owner_required.json`, `queue_server_stopping.json`, `queue_with_entries.json` | `GET /command/queue` | 4.4.6, lines 1149-1157 (the JSON: `schema_version`, `revision`, `slot {state, run_id, reason_code}`, `entries[]`); the slot table, lines 1161-1171: one file per row the card acts on (`free`; `busy` holder `plan_waiting`, the holder that waits for a human; `busy` holder `action_in_flight`; `stuck`; `unavailable` / `project_not_active`, the view mode; `unavailable` / `owner_required`; `unavailable` / `server_stopping`); entry `state` and `reason_code`, lines 1174-1184. |
| `automation_holder_waiting.json`, `automation_unconfigured.json` | `GET /command/runs/<run_id>/automation` | The keys `automation_view` returns (`command/policy_view.py`) and the Studio's own validator lists (`panel/studio-automation-model.js`, `VIEW` and `GRANT`); read at 6.4.5, lines 3132 and 3147 (`unknown` is settled only by this read and the queue read). |
| `run_detail.json` | `GET /command/runs/<run_id>` | The keys the card's step rows read: the frozen plan's nodes and `config.instances` (6.4.5, line 3096: `node_limits` joined with the plan and `participants`); the same slice `previous_run.json` holds. |
