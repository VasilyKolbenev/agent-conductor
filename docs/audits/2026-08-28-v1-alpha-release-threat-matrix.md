# December Command v1 public alpha — release threat matrix

- **Recorded:** 2026-08-28
- **Extended:** 2026-09-07 — independent checker authority and material containment
- **Production base:** `ade6a7f`
- **Supersedes:** `docs/audits/2026-08-13-v2-threat-matrix.md` (a historical snapshot of `63d261a`)
- **Scope:** the eighteen early-matrix threats plus three independent-checker threats

This is the release posture. The v2 matrix asked a different question — which Day-1
and Day-2 seams had been built yet — and answered it correctly for its own base. It was
never updated as the slices landed, and its guard could not notice, so it went on
reporting four of eighteen threats held long after all eighteen were. It is kept as a
dated record of that base and is not the posture of this release.

A row here means three things at once, and a reader may check each of them:

- **Door** — the production symbol that refuses. Named as `<module path>::<definition>`,
  so it survives the line drift that makes `file:line` citations rot, and so a guard can
  resolve it in the syntax tree rather than trust the prose.
- **Fixture** — the hostile construction in `tests/sabotage_fixtures.py` that the threat
  is written against. Its construction claims are proved in `tests/test_sabotage_fixtures.py`.
- **Witness** — one permanent, collected, green test that drives the threat at the door.
  Named as `<test module>::<test function>`, one row to one witness. A fixture self-test,
  a skipped primitive, a manual observation and a reserved name are none of them a witness.

`Status` here admits only `HELD`. A threat that is not held does not become a softer word
in the release posture; it becomes a release blocker and leaves this document.

`tests/test_threat_matrix.py` holds every one of those claims structurally: it parses each
row, resolves each door and each witness in the syntax tree of the named file, refuses a
row that is malformed or that leans on a witness another row already claims, and shows
itself failing on synthetic rows before it is trusted on these.

<!-- THREAT-MATRIX:START -->

### CONF-STALE — expired confirmation

- Status: `HELD`
- Door: `src/conductor/command/runtime.py::ControlRuntime._hold_freshness`
- Fixture: `expired_confirmation`
- Expected invariant: Refuse before prepare when the confirmation is older than the budget.
- Witness:
  `tests/test_command_runtime_authorize.py::test_a_confirmation_older_than_the_freshness_budget_is_refused`

### CONF-DIGEST — changed preview after confirmation

- Status: `HELD`
- Door: `src/conductor/command/action_proposal.py::ActionProposal.__post_init__`
- Fixture: `changed_digest_confirmation`
- Expected invariant: A stored proposal edited without its digest fails reconstruction.
- Witness:
  `tests/test_command_proposals.py::test_a_durable_proposal_whose_field_was_edited_without_its_digest_is_refused`

### PATH-SCOPE — contract scope escapes the project

- Status: `HELD`
- Door: `src/conductor/command/contract_values.py::_scope`
- Fixture: `path_escape_scopes`
- Expected invariant: ActionRequest construction rejects every non-canonical scope component.
- Witness:
  `tests/test_sabotage_fixtures.py::test_path_escape_scopes_trip_the_contract_gate`

### PATH-CWD — runner cwd escapes the project

- Status: `HELD`
- Door: `src/conductor/command/containment.py::assess_cwd_route`
- Fixture: `path_escape_cwds`
- Expected invariant: Refuse before spawn unless the resolved cwd is beneath the frozen root.
- Witness:
  `tests/test_command_process_containment.py::test_a_cwd_outside_the_root_is_refused`

### SHELL-INJECT — argv element contains shell control text

- Status: `HELD`
- Door: `src/conductor/command/adapters/process.py::ProcessRunner._spawn`
- Fixture: `shell_injection_payloads`, `write_argv_probe`
- Expected invariant: Spawn without a shell and hand each payload to the child as one token.
- Witness:
  `tests/test_command_process_runner.py::test_shell_metacharacters_in_an_argument_reach_the_child_as_one_inert_token`

### TIMEOUT — child survives beyond its action budget

- Status: `HELD`
- Door: `src/conductor/command/adapters/process.py::ProcessRunner.run`
- Fixture: `write_blocking_executable`
- Expected invariant: Stop only the owned group; report the timed-out fact, not an exit code.
- Witness:
  `tests/test_command_process_runner.py::test_a_child_exceeding_its_timeout_is_terminated_and_reported_timed_out`

### OUTPUT-BOMB — child floods captured output

- Status: `HELD`
- Door: `src/conductor/command/adapters/process.py::_Owned._drain`
- Fixture: `write_output_bomb`
- Expected invariant: Capture stays bounded and flags truncation rather than dropping bytes.
- Witness:
  `tests/test_command_process_runner.py::test_output_beyond_the_bound_is_truncated_and_flagged_never_silently_dropped`

### DUPLICATE-IDEMPOTENCY — one key is reused with new meaning

- Status: `HELD`
- Door: `src/conductor/command/run_store.py::RunStore.append`
- Fixture: `conflicting_idempotency_requests`
- Expected invariant: The second meaning conflicts and nothing further is appended.
- Witness:
  `tests/test_command_run_store.py::test_identical_append_is_idempotent_but_ids_and_idempotency_keys_cannot_change_meaning`

### FOREIGN-PID — stop targets a process December never owned

- Status: `HELD`
- Door: `src/conductor/command/adapters/process.py::ProcessRunner.stop`
- Fixture: `recorded_owner`, `foreign_pid`, `recycled_pid`
- Expected invariant: Stop refuses a token this runner never minted and signals nothing.
- Witness:
  `tests/test_command_process_ownership.py::test_a_process_the_runner_did_not_start_is_never_touched`

### PORTAL-PREVIEW — the found preview route points elsewhere

- Status: `HELD`
- Door: `src/conductor/command/preview.py::render_dispatch_preview`
- Fixture: `plant_route_portal`
- Expected invariant: Preview refuses before replay or append and external bytes stay unchanged.
- Witness:
  `tests/test_sabotage_fixtures.py::test_portal_planter_trips_preview_route_gate`

### HARDLINK-PREVIEW — an owned preview file has an outward alias

- Status: `HELD`
- Door: `src/conductor/command/containment.py::owned_file_violations`
- Fixture: `plant_outward_hard_link`
- Expected invariant: Preview refuses before replay or append and both alias names stay unchanged.
- Witness:
  `tests/test_sabotage_fixtures.py::test_outward_hard_link_planter_trips_preview_route_gate`

### PORTAL-CONFIRM — the Confirm or runner route points elsewhere

- Status: `HELD`
- Door: `src/conductor/command/containment.py::run_route_violations`
- Fixture: `plant_route_portal`
- Expected invariant: Refuse before spawn; internal and external bytes both stay unchanged.
- Witness:
  `tests/test_command_control_loop.py::test_integration_smoke_refuses_route_portal_before_spawn_and_leaves_sides_inert`

### HARDLINK-CONFIRM — a writable runtime file has an outward alias

- Status: `HELD`
- Door: `src/conductor/command/containment.py::owned_file_violations`
- Fixture: `plant_outward_hard_link`
- Expected invariant: Refuse before spawn when a writable owned name carries a second link.
- Witness:
  `tests/test_command_control_loop.py::test_integration_smoke_refuses_hard_linked_journal_before_spawn_and_changes_no_alias`

### RECEIPT-TAMPER — published receipt bytes are replaced or rewritten

- Status: `HELD`
- Door: `src/conductor/command/run_store.py::RunStore._validate_records`
- Fixture: `tampered_receipt_bytes`, `uncontracted_receipt_bytes`
- Expected invariant: Replay refuses changed identity bytes and never projects them as a decision.
- Witness:
  `tests/test_sabotage_fixtures.py::test_receipt_damage_fixture_trips_real_run_store_replay`

### RESTART — coordinator restarts while a child may still be live

- Status: `HELD`
- Door: `src/conductor/command/runtime.py::ControlRuntime._replayed_attempt`
- Fixture: `write_blocking_executable`, `recorded_owner`
- Expected invariant: Recovery reports unknown and re-enters no adapter seam.
- Witness:
  `tests/test_command_runtime_restart.py::test_restart_after_lease_before_effect_records_unknown_without_execute`

### DISCONNECT — event consumer disappears during a live attempt

- Status: `HELD`
- Door: `src/conductor/command/coordinator.py::ExecutionCoordinator`
- Fixture: `write_blocking_executable`
- Expected invariant: A vanished client neither cancels nor repeats the effect it started.
- Witness:
  `tests/test_server_async_execution.py::test_a_client_that_vanishes_mid_effect_neither_cancels_nor_repeats_it`

### VERIFY-FAIL — process exits zero but evidence does not verify

- Status: `HELD`
- Door: `src/conductor/command/runtime.py::ControlRuntime._verify`
- Fixture: `mismatched_verification`
- Expected invariant: Record verification_failed, distinct from process success and acceptance.
- Witness:
  `tests/test_command_runtime_verify.py::test_a_verify_that_refutes_success_reaches_verification_failed`

### CSRF-ORIGIN — browser mutation lacks one authorization factor

- Status: `HELD`
- Door: `src/conductor/command/http_transport.py::validate_command_mutation`
- Fixture: `hostile_browser_mutations`
- Expected invariant: Host, exact Origin and the process token must all match before any write.
- Witness:
  `tests/test_command_http_transport.py::test_structured_csrf_fixtures_drive_the_real_transport`

### CHECKER-ONCE — recovery spends a second checker call

- Status: `HELD`
- Door: `src/conductor/command/verify_road.py::verify_independently`
- Fixture: `standing_verification_marker`
- Expected invariant: Without a live grant, reuse standing matching evidence or refuse; never start another checker, even if its start status is unknown.
- Witness:
  `tests/test_command_independent_runtime.py::test_restart_with_no_checker_evidence_never_spends_a_second_grant`

### CHECKER-WRITES — a checker changes the work and claims acceptance

- Status: `HELD`
- Door: `src/conductor/command/adapters/independent_transport.py::IndependentCheckTransport._check_owned`
- Fixture: `checker_that_writes`
- Expected invariant: A changed work tree defeats an accept verdict and produces no verified evidence.
- Witness:
  `tests/test_independent_checker_transport.py::test_checker_refusal_no_verdict_or_write_never_becomes_success`

### WORKTREE-CONTENT — a result path escapes through a directory portal

- Status: `HELD`
- Door: `src/conductor/command/adapters/harness_workspace.py::HarnessWorkspace.read_work_tree`
- Fixture: `portal_under_work_item`
- Expected invariant: List the portal's kind; never walk it or read target bytes into the checker material.
- Witness:
  `tests/test_sabotage_fixtures.py::test_work_item_portal_fixture_is_not_opened_by_the_checker`

<!-- THREAT-MATRIX:END -->

## What this document does not claim

A named door is where the refusal lives, not proof that the witness reaches it by that
path; the witness proves the behaviour, the door tells a reader where to look. The guard
resolves both in the syntax tree and pins the pair, so a door that is renamed or deleted
and a witness that is swapped for another both surface as a decision rather than a drift.

Coverage of a threat is not coverage of its neighbourhood. The 2026-08-27 audit's two
specific gaps are no longer accurate descriptions of this tree: Kimi and dsh now have
`test_command_kimi_leak_surfaces.py` / `test_command_dsh_leak_surfaces.py`, and
`harness_profile.reviewed_env_allow` plus the process environment contract reject reviewed
code-loading overrides. These do not imply an operating-system sandbox or an audit of
every possible provider input. The final candidate's actual gates remain separate from
this document's structural door/witness inventory.

## Exit rule

A row is added only with a door and a witness that resolve, and the witness must have been
seen green in the same delta. A row leaves this document only by the threat being retired
from the product or by an owner's recorded decision to ship without it — in which case it
belongs in the release blockers, never in this file under a softer status.
