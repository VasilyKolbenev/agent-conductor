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

The flow answers (`FlowState` and `Budget` of the five cycles) are lane L's, in
`tests/fixtures/flow/`; the wizard reads those unchanged.
