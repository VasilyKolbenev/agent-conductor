# Human situation read contract (S2)

Status: proposed integration, 2026-09-21. This is a derived read, not a durable
record, permission, decision, authorization, driver or new write route. Its
phrases and visible treatment belong to the later RU/EN Studio shell. This
slice does not display a new needs line or change the legacy undecided count.

`graph_payload(recovered, *, computed_at)` adds required key `situation` to the
existing graph block, including runs without a graph. The server supplies the
read clock; event timestamps do not stand in for the read instant. One run list
uses one supplied instant across its rows. Readable rows add `human_state` with
the same state as a detail read of those durable facts; unreadable rows carry
`human_state: null`, retaining the existing unreadable marker. Reads do not
repair, reconcile, append, execute, authorize or otherwise change the journal.

## Closed value

The exact top-level keys are `state`, `computed_at`, `gates`, `checked`,
`unknown_because`, `unknown_sources`. No title, provider prose, path, credential,
recovery reference or authorizing field is included. IDs use the existing
command ID grammar. The instant uses the existing validated UTC grammar.

`state` is one of `required`, `not_required`, `unknown`. Required means at least
one demonstrated present need among the checked reasons. Not required is
limited to those named checks; it does not claim that a worker is alive, that
the work succeeded or that nothing else could need attention. Unknown takes
precedence when the available durable reading cannot settle the question.

Every gate carries exactly:

| Field | Value |
|---|---|
| `node_id`, `gate_id` | Existing IDs from this frozen graph |
| `arrived` | Boolean from the shared gate-arrival predicate |
| `decision` | `idle`, `satisfied`, `failed`, `changes_requested`, `waived`, `unknown` |
| `answerable` | `first`, `supersede`, `none` from the existing decision door |
| `lap` | Exactly `required_pass` (positive integer), `settled_laps` (nonnegative integer) |
| `standing_receipt` | Receipt ID or null |
| `standing_belongs_to_current_lap` | Boolean when a receipt stands, otherwise null |
| `needs_decision` | Boolean; arrival, readable decision and no recorded ending |
| `why_not` | Null if needed; otherwise one of the five codes below |

`why_not` is `run_ended`, `decision_unknown`, `answered_current_lap`,
`branch_closed`, or `road_not_open`. A current-lap correction may be answerable
without being needed. A reopened gate can need a new answer while the prior
lap's receipt still stands. Gate arrival deliberately includes the scheduler's
halt rewrite; it must not be reduced to `state == runnable`.

## Checked reasons and unknown sources

Every checked row has exactly `reason`, `count`, `sources`. Count is a
nonnegative integer equal to the unique ID-list length. All six rows are
mandatory, exactly once and in this order, including zero rows:

| Reason | Sources and meaning |
|---|---|
| `gate_decision` | Node IDs of gates currently needing an answer |
| `confirmation` | Proposal IDs: newest per node, confirm/propose mode, unrequested, no unanswered attempt, current runnable lap |
| `input_document` | Node IDs actually waiting only for an input document, not behind pending/closed roads or a halt |
| `reconcile` | Empty: this slice has no evidence proving abandoned ownership |
| `attempt_bound` | Blocked, spent node IDs in a stalled run |
| `run_ended` | Terminal IDs; informational, never makes state required |

Unplanned proposals retain their own identities. The existing authorize/store
rule reserves an attempt ID for one action across the run, across instances and
after completion; an independent attempt remains visible while another runs.
No whole-run in-flight predicate suppresses unplanned fanout. Confirmation reads the
proposal/request relation; a runtime phase of `proposed` alone is insufficient.
Documents and attempt bounds spend the shared scheduler predicates, not copied
lap or road arithmetic. A recorded ending suppresses every present need and
unobserved-request uncertainty, without removing historical facts.

`unknown_sources` has the same row keys, always these three reasons in order:

| Reason | Sources |
|---|---|
| `contradictory_gate_receipts` | IDs of gates whose decision is unreadable |
| `replay_warnings` | Empty list and actual warning count; warning prose is not copied |
| `unobserved_request` | Action IDs with a durable request, no attempt event and no terminal result |

`unknown_because` contains exactly the positive-count unknown reasons in that
order. Warning counts may exceed source-list length by this explicit exception.
Contradictory receipts and replay warnings remain unknown after a recorded
ending. Checked and unknown lists are not optional decorations of the state.

## Explicit correction to the September 16 draft

A request with no attempt event or result is also an ordinary confirmed request
queued for the shared T5 resource. Those durable bytes do not distinguish the
live queue from the same request after its process was lost. Therefore S2 does
not turn `stuck_actions` membership into a reconcile need. It reports the action
IDs under `unobserved_request`, keeps reconcile count zero, and returns unknown.
This is an explicit epistemic correction, not a renamed diagnostic or new
authority. A later ownership contract could supply independently verified live
facts; this slice neither implements nor assumes them.

## Reader boundary and validation

`studio-model.js` retains its existing no-import boundary and validates the new
run-row word. New pure `studio-situation.js` imports only that model's value
helpers, validates the complete closed S2 value, and composes its strict run
read door with the base structural reader. `studio-store.js` uses this strict
door. No S2 read reaches stored UI state if its checked list is absent, empty,
duplicated, malformed or inconsistent with its declared state. The graph window
admits the sixth key as unused read data, just as it admits schedule; it derives
no attention or authorization claim from it.

The strict read door also joins the S2 gate pairs to every gate in this read's
frozen graph, including coverage and standing-receipt membership. Source IDs
must belong to this run's proposal/request/terminal records or work-bearing
nodes as appropriate. A foreign sample cannot turn an unrelated run into a
required or unknown reading. These are identity joins and relations among
served fields, not browser calculations of gate arrival, roads or laps.

The source/import permission table adds the single edge
`studio-store.js -> studio-situation.js -> studio-model.js`. The base model
remains import-free. The new module is served by an exact packaged GET asset;
query, traversal, case-fold, suffix and source-map near misses remain refused.

Witness obligations include H1–H5, full-list H7 positive/negative controls,
clock injection, actual route/list parity, unchanged durable bytes, and the
HTTP/T5 held queue with a fresh durable reader. Browser disconnect treatment
(H6) and user-visible RU/EN wording/absence of authority claims (H8) belong to the
later shell and are not asserted complete by server or value-module tests.
