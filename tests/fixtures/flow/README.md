# Flow fixtures (spec 7.8, 7.12 item 1)

Answers of `GET /command/workflows/<workflow_id>/flow` for the five cycles of the 7.8 table, so the
desk can draw the editor, the diagnostics and the counter before the routes exist. Each
`<cycle>.flow-state.json` is a `FlowState` with its `Budget` inside.

| File | Cycle | Source in the answer |
|---|---|---|
| `desk-standard.flow-state.json` | Standard | published, revision 1 |
| `desk-short.flow-state.json` | Short | published, revision 1 |
| `desk-starter-docs.flow-state.json` | Starter documents | published, revision 1 |
| `desk-standard-tester.flow-state.json` | Standard with a tester | draft of a new `cycle-<8 hex>` |
| `dalio-v5.flow-state.json` | "Start from: Dalio cycle" | draft of a new `cycle-<8 hex>` |
| `desk-standard.budget-replacing.json` | `Budget` of a replacement grant after two spent actions | `spent` set |
| `desk-short.budget-exhausted.json` | `Budget` of a replacement grant with nothing left | `exhausted` true |

## What is checked, and what is only derived

- The totals of every `budget` equal the 7.8 table, and every derived number follows from the rows
  and the flow by the 7.8 formulas (`tests/test_command_flow_fixtures.py`).
- Every `flow` settles unchanged through `workflow_flow.settled_flow`.
- Derived, not yet produced by code: the flows of the four `desk-*` and tester cycles come from 7.9
  and 7.6; the `dalio-v5` flow applies the 7.3 import rules by hand (every review and `do` carries
  its whole `arguments` and its `stage` in `ext`, both gates carry `gate_id` and a null
  `success_requires`, the cycle carries a null `execution_contract`). `diagnostics` rows carry the
  codes and addresses of 7.4 with empty `params`; the spec fixes no `params` shape yet.
- `draft_digest` is the sha256 of the canonical flow JSON, a stand-in: the real one digests the
  compiled document. Treat it as an opaque `expected_digest` to send back.
- When `import_template`, `flow_rules` and `plan_budget` land (days 3-5) they must reproduce these
  files from the flows; a difference is settled in the fixture or in the module, on the record.
