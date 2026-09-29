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
| `workflows.json` | `GET /command/workflows`: rows, `starters`, `providers` | 7.9, 5.6.6 |
| `runs.json` | `GET /command/runs` (the keys the preselection reads) | 7.10 |
| `project_cycle.json`, `project_cycle_none.json` | `GET /command/project/cycle`, pinned and not | 7.10 |
| `tasks.json` | `GET /command/tasks` (the title in the preselection's label) | 7.10 |
| `quotas.json` | `GET /command/quotas` (the keys the roles step reads) | 5.6.6, 6.3 |
| `previous_run.json`, `previous_revision.json` | `GET /command/runs/<id>` and `GET /command/workflows/<id>/revisions/<n>` of the last run | 7.10 |
| `flow_state_none.json` | `GET /command/workflows/<id>/flow` of a workflow with neither a draft nor a revision: `source: "none"`, `flow: null`, `draft_digest: null` (the `workflow_id` is overwritten per cycle) | 7.1 |

The provider rows inside `workflows.json` carry three facts the server's roster does not carry
yet: `capabilities` (which roads a harness has), `task_channel` (how it is fed, in the shape
`studio-automation-providers.js` already judges) and `offered` (whether this version offers it).
The wizard treats a row without `offered: true` as not offered.

The flow answers (`FlowState` and `Budget` of the five cycles) are lane L's, in
`tests/fixtures/flow/`; the wizard reads those unchanged.
