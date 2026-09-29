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
