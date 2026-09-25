# Bounded authorization values — 21 September 2026

## Implemented history extension

RunStore now registers both records and applies `authorization_history` on
append and prefix replay. Explicit frozen `automation_contract=bounded-run-v1`,
Policy mode and a published workflow reference are required. Legacy unmarked
Policy and Confirm runs do not acquire these semantics. Marked Policy action
requests remain refused until their separate admission path is implemented.

The history relation checks the exact ordered journal-wrapper prefix, frozen
config/graph, executable node order and tightened bounds, immutable instruction
and resolved-input identities with SHA-256 of exact UTF-8 content. Missing
instructions never use the filesystem fallback. Missing future inputs must have
a declared authorized review producer; same-grant consumption remains a driver
obligation. Replacements require the immediate preceding authorization to be
revoked/expired and no unsettled requests. Controls bind the current grant and
latest control; revoke is irreversible and expired grants cannot resume.

This extension records facts only. Provider digest provenance, supported native
capability/schema and deployment caps belong to the still-unimplemented fresh
preview/admission boundary; historical replay must not ask today's provider or
clock. Live grant, routes, cumulative request reservations and driver remain
disabled. The project ownership prerequisite is unchanged. The original pure
value checkpoint below is retained as historical context.

This is the pure data part of BOUNDED-RUN-AUTH-DESIGN-2026-09-07, with the
Section 8 ruling of 9 September. It does not activate a Policy run, issue a live
grant, add a route, register journal records or change Confirm history.

`command/run_authorization.py` defines closed `RunAuthorization` and
`RunAuthorizationControl` records. The former includes the exact frozen config,
graph, provider configuration and preceding journal-prefix digests; node bounds;
instruction and initial-document identities/content digests; human attribution;
expiry and finite action/time ceilings. Concurrency remains exactly one and
failure handling remains `explicit-failure-route-only`.

Every wire field is required. Unknown keys and explicit nulls refuse, except the
specified nullable predecessor IDs. These new records accept exactly schema 2;
the older schema grammar is unchanged. Constructor-only digest derivation is
available to a future trusted builder. Persisted/wire records must carry their
correct digest, covering every other field and every nested binding.

Nested inputs are reconstructed and frozen. Duplicate node/reference identities
refuse. Node order is preserved for later comparison to frozen graph order;
instruction bindings follow that order, and initial input references use lexical
canonical order. The expiry is strictly later than authorization and no more
than 24 hours later. Fractions beyond microsecond precision are compared exactly,
without asking the current clock. Human names must encode as UTF-8.

These are necessary shape checks, not sufficient authority checks. Remaining
implementation must verify graph eligibility/order/capabilities, exact raw input
bytes and immutable sources, provider facts, predecessor/control history,
cumulative reservations, old-request compatibility and replay. Deployment limits
belong to that relation and preview; this value type does not increase the
server's default budget. Pause/resume/revoke values alone do not pause, restart
or revoke execution. Replacements and controls require their full historical
relations before append becomes legal.

RunStore currently rejects both record types before creating durable bytes.
The owner lifetime across all writers and subprocesses must be completed before
the bounded driver can be enabled. Tests in `test_run_authorization.py` establish
only this data boundary and continued lack of store activation.
