# December Command v2 early threat matrix

- **Recorded:** 2026-08-13
- **Slice:** D/THREAT-0
- **Production base:** `63d261a` plus REPORT-GUARD-1
- **Scope:** Day-1 and Day-2 command seams

This matrix separates a hostile fixture from a production protection. `HELD` means the named
production door exists and the fixture is driven against it by the permanent regression named
below. `PENDING` means only the hostile fixture and its independent witness exist. A pending row
is not a passing security test and cannot satisfy a day gate or release gate.

All fixture names resolve in `tests/sabotage_fixtures.py`; their construction claims are proved in
`tests/test_sabotage_fixtures.py`. The pending regression name is a reservation, not a skipped or
green test. It is written only when its production slice lands, born red against the prior SHA.

<!-- THREAT-MATRIX:START -->

### CONF-STALE — expired confirmation

- Status: `PENDING`
- Slice: `A/CONF-1`
- Fixture: `expired_confirmation`
- Expected invariant: Refuse before prepare when authorization time is at or after expiry.
- Regression: `PENDING: test_confirm_refuses_an_expired_confirmation_before_prepare`

### CONF-DIGEST — changed preview after confirmation

- Status: `PENDING`
- Slice: `A/CONF-1`
- Fixture: `changed_digest_confirmation`
- Expected invariant: Refuse before prepare unless the confirmed and current digests are equal.
- Regression: `PENDING: test_confirm_refuses_a_request_changed_after_confirmation`

### PATH-SCOPE — contract scope escapes the project

- Status: `HELD`
- Slice: `CMD-1`
- Fixture: `path_escape_scopes`
- Expected invariant: ActionRequest construction rejects every non-canonical scope component.
- Regression:
  `tests/test_sabotage_fixtures.py::test_path_escape_scopes_trip_the_contract_gate`

### PATH-CWD — runner cwd escapes the project

- Status: `PENDING`
- Slice: `B/RUN-1`
- Fixture: `path_escape_cwds`
- Expected invariant: Refuse before spawn unless resolved cwd is beneath the frozen project root.
- Regression: `PENDING: test_runner_refuses_every_cwd_escape_before_spawn`

### SHELL-INJECT — argv element contains shell control text

- Status: `PENDING`
- Slice: `B/RUN-1`
- Fixture: `shell_injection_payloads`, `write_argv_probe`
- Expected invariant: Spawn without a shell and preserve each payload as one unchanged argv item.
- Regression: `PENDING: test_runner_never_interprets_an_argv_element_as_shell_text`

### TIMEOUT — child survives beyond its action budget

- Status: `PENDING`
- Slice: `B/RUN-1`, `A/RT-1`
- Fixture: `write_blocking_executable`
- Expected invariant: Stop only the owned group; record outcome failed plus the timed-out fact.
- Regression: `PENDING: test_timeout_stops_the_owned_group_and_records_failed_with_timeout`

### OUTPUT-BOMB — child floods captured output

- Status: `PENDING`
- Slice: `B/RUN-1`
- Fixture: `write_output_bomb`
- Expected invariant: Combined capture stays bounded and reports truncation without hiding outcome.
- Regression: `PENDING: test_runner_bounds_combined_output_and_records_truncation`

### DUPLICATE-IDEMPOTENCY — one key is reused with new meaning

- Status: `PENDING`
- Slice: `A/RT-1`
- Fixture: `conflicting_idempotency_requests`
- Expected invariant: The second meaning refuses and neither prepares nor starts another action.
- Regression: `PENDING: test_runtime_refuses_an_idempotency_key_reused_for_another_action`

### FOREIGN-PID — stop targets a process December never owned

- Status: `PENDING`
- Slice: `B/RUN-1`
- Fixture: `recorded_owner`, `foreign_pid`, `recycled_pid`
- Expected invariant: Stop requires both recorded PID and start token; mismatch sends no signal.
- Regression: `PENDING: test_stop_never_signals_a_foreign_or_recycled_pid`

### PORTAL-PREVIEW — the found preview route points elsewhere

- Status: `HELD`
- Slice: `CMD-4`
- Fixture: `plant_route_portal`
- Expected invariant: Preview refuses before replay or append and external bytes remain unchanged.
- Regression:
  `tests/test_sabotage_fixtures.py::test_portal_planter_trips_preview_route_gate`

### HARDLINK-PREVIEW — an owned preview file has an outward alias

- Status: `HELD`
- Slice: `CMD-4`
- Fixture: `plant_outward_hard_link`
- Expected invariant: Preview refuses before replay or append and both alias names remain unchanged.
- Regression:
  `tests/test_sabotage_fixtures.py::test_outward_hard_link_planter_trips_preview_route_gate`

### PORTAL-CONFIRM — Confirm or runner route points elsewhere

- Status: `PENDING`
- Slice: `A/CONF-1`, `B/RUN-1`
- Fixture: `plant_route_portal`
- Expected invariant: Refuse before mutation or spawn; internal and external bytes stay unchanged.
- Regression: `PENDING: test_confirm_and_runner_refuse_every_route_portal_before_mutation`

### HARDLINK-CONFIRM — a writable runtime file has an outward alias

- Status: `PENDING`
- Slice: `A/CONF-1`, `B/RUN-1`
- Fixture: `plant_outward_hard_link`
- Expected invariant: Refuse before durable mutation or spawn when any writable name is aliased.
- Regression: `PENDING: test_confirm_and_runner_refuse_every_writable_hardlink_alias`

### RECEIPT-TAMPER — published receipt bytes are replaced or rewritten

- Status: `HELD`
- Slice: `CMD-2`
- Fixture: `tampered_receipt_bytes`, `uncontracted_receipt_bytes`
- Expected invariant: Replay refuses changed identity bytes and never projects them as a decision.
- Regression:
  `tests/test_sabotage_fixtures.py::test_receipt_damage_fixture_trips_real_run_store_replay`

### RESTART — coordinator restarts while a child may still be live

- Status: `PENDING`
- Slice: `A/RT-2`
- Fixture: `write_blocking_executable`, `recorded_owner`
- Expected invariant: Recovery reports unknown until exact ownership and outcome are reconciled.
- Regression: `PENDING: test_restart_never_converts_an_unreconciled_attempt_to_success`

### DISCONNECT — event consumer disappears during a live attempt

- Status: `PENDING`
- Slice: `A/RT-2`
- Fixture: `write_blocking_executable`
- Expected invariant: Disconnect changes no outcome; replay stays started until a terminal receipt.
- Regression: `PENDING: test_disconnect_does_not_cancel_or_complete_a_live_attempt`

### VERIFY-FAIL — process exits zero but evidence does not verify

- Status: `PENDING`
- Slice: `A/RT-1`
- Fixture: `mismatched_verification`
- Expected invariant: Record verification_failed, distinct from process success and acceptance.
- Regression: `PENDING: test_zero_exit_with_mismatched_evidence_is_verification_failed`

### CSRF-ORIGIN — browser mutation lacks one authorization factor

- Status: `PENDING`
- Slice: `C/API-1`
- Fixture: `hostile_browser_mutations`
- Expected invariant: Host, exact Origin, and process token must all match before any write.
- Regression: `PENDING: test_browser_mutation_requires_host_origin_and_process_csrf_token`

<!-- THREAT-MATRIX:END -->

## Exit rule

A slice owner changes a row from `PENDING` to `HELD` only in the same committed delta that adds
the named permanent regression and proves it was born red on the slice base. A fixture self-test,
a skipped platform primitive, prose, or a manual observation never changes status by itself.
