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
- `inputs.instructions` is one row per dispatch step, read off the flow: the `instruction_ref` in the
  step's `ext.arguments` when it has one, otherwise `instruction-<instruction_from or step_id>`. An
  `ext` replaces the computed arguments whole (7.2.1), so the `dalio-v5` copy names
  `instruction-plan`, not the default `instruction-do`. Both replacement budgets are held to the flow
  of the cycle they replace.
- `inputs.documents` is not read off the flow: it is the pair the wizard publishes for every run
  (6.2.3, 6.4.1 link 5), so the `dalio-v5` copy keeps both although its `goal` reads only
  `artifact-brief`. What the flow does read from outside stays inside that pair.
- The `dalio-v5` flow is what `import_template` makes of the shipped template
  (`test_import_of_dalio_v5_equals_the_fixture_flow`): every review and `do` carries its whole
  `arguments` and its `stage` in `ext`, while the typed `review_profile` still says what those
  arguments spell; both gates carry `gate_id` and a null `success_requires`; the cycle carries a
  null `execution_contract`. The first hand-made copy left the four profiles null, and the module
  won: an inspector should show the profile the arguments name, not an empty control.
- The flows of the four `desk-*` and tester cycles come from 7.9 and 7.6, and each compiles to a
  template that builds (`test_every_compiled_fixture_cycle_builds_a_template`). `diagnostics` rows
  carry the codes and addresses of 7.4 with empty `params`; the spec fixes no `params` shape yet.
- `draft_digest` is the sha256 of the canonical flow JSON, a stand-in: the real one digests the
  compiled document. Treat it as an opaque `expected_digest` to send back.
- The modules now reproduce these files from the flows, and a difference is settled in the fixture
  or in the module, on the record. `plan_budget` gives every `budget` and both replacement budgets
  (`tests/test_command_plan_budget.py`), `flow_rules` gives every `diagnostics` and `publishable`
  (`tests/test_command_flow_rules.py`), and `import_template` gives the `dalio-v5` flow. What is
  still only derived from the spec is the `draft_digest` stand-in and the flows of the four
  `desk-*` and tester cycles, which wait for the shipped `desk-*` files.
