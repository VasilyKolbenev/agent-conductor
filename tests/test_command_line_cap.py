"""New Python code stays within 100 characters a line (house rule for the desk lanes).

The files listed are the ones lane L created for the desk redesign. A file is added to the list in
the commit that creates it, so the rule holds from its first line; a listed file that is gone
fails too, so a rename cannot drop a file out of the rule unnoticed.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 100
CAPPED = (
    "src/conductor/command/adapters/agent_instructions.py",
    "src/conductor/command/flag_control_id.py",
    "src/conductor/command/flow_routes.py",
    "src/conductor/command/flow_rules.py",
    "src/conductor/command/git_setup.py",
    "src/conductor/command/git_setup_first_index.py",
    "src/conductor/command/git_setup_first_lock.py",
    "src/conductor/command/git_setup_first_pending.py",
    "src/conductor/command/git_setup_first_records.py",
    "src/conductor/command/git_setup_first_resume.py",
    "src/conductor/command/git_setup_modes.py",
    "src/conductor/command/git_setup_snapshot.py",
    "src/conductor/command/plan_budget.py",
    "src/conductor/command/preview_draft.py",
    "src/conductor/command/product_names.py",
    "src/conductor/command/project_cycle.py",
    "src/conductor/command/project_documents.py",
    "src/conductor/command/project_git.py",
    "src/conductor/command/queue_bodies.py",
    "src/conductor/command/queue_flag.py",
    "src/conductor/command/queue_pump.py",
    "src/conductor/command/queue_reading.py",
    "src/conductor/command/queue_routes.py",
    "src/conductor/command/queue_service.py",
    "src/conductor/command/queue_store.py",
    "src/conductor/command/seed_plan.py",
    "src/conductor/command/seed_record.py",
    "src/conductor/command/seed_routes.py",
    "src/conductor/command/seed_stage.py",
    "src/conductor/command/task_preparation.py",
    "src/conductor/command/workflow_flow.py",
    "tests/git_first_readers.py",
    "tests/git_first_scratch.py",
    "tests/git_index_bytes.py",
    "tests/git_repo_helpers.py",
    "tests/queue_fixtures.py",
    "tests/test_command_line_cap.py",
    "tests/flow_driver_bench.py",
    "tests/test_command_flow_driver.py",
    "tests/test_command_flow_fixtures.py",
    "tests/test_command_flow_import_corners.py",
    "tests/test_command_flow_routes.py",
    "tests/test_command_flow_rules.py",
    "tests/test_command_auto_continue_routes.py",
    "tests/test_command_import_hygiene.py",
    "tests/test_command_plan_budget.py",
    "tests/test_command_product_names.py",
    "tests/test_command_queue.py",
    "tests/test_command_queue_wire.py",
    "tests/test_command_project_cycle.py",
    "tests/test_command_project_git.py",
    "tests/test_command_project_route.py",
    "tests/test_command_quota_view.py",
    "tests/test_command_workflow_flow.py",
    "tests/test_flag_control_id.py",
    "tests/test_git_first_reader_account.py",
    "tests/test_git_first_readers.py",
    "tests/test_git_first_scratch.py",
    "tests/test_git_fsmonitor_callers.py",
    "tests/test_git_index_labels.py",
    "tests/test_git_index_marker_compat.py",
    "tests/test_git_setup_first_index.py",
    "tests/test_git_setup_first_lock.py",
    "tests/test_git_setup_first_pending.py",
    "tests/test_git_setup_first_records.py",
    "tests/test_git_setup_first_resume.py",
    "tests/test_git_setup_modes.py",
    "tests/test_materials_refused_refusal.py",
    "tests/test_policy_driver_queue.py",
    "tests/test_policy_driver_slot.py",
    "tests/test_policy_queue_hook.py",
    "tests/test_policy_view_door.py",
    "tests/test_policy_view_expired.py",
    "tests/test_policy_view_reasons.py",
    "tests/test_preview_draft.py",
    "tests/test_preview_stale_refusal.py",
    "tests/test_project_documents.py",
    "tests/test_project_git_reader_keywords.py",
    "tests/test_project_git_failure_reason.py",
    "tests/test_project_not_active_refusal.py",
    "tests/test_queue_pump.py",
    "tests/test_queue_pump_flag.py",
    "tests/test_queue_reading.py",
    "tests/test_queue_receipt_budget.py",
    "tests/test_queue_refusals.py",
    "tests/test_queue_routes.py",
    "tests/test_queue_store.py",
    "tests/test_seed_plan.py",
    "tests/test_root_turn.py",
    "tests/test_seed_driver.py",
    "tests/test_seed_move.py",
    "tests/test_seed_record.py",
    "tests/test_seed_stage.py",
    "tests/test_seed_writer.py",
    "tests/test_seed_refusals.py",
    "tests/test_seed_routes.py",
    "tests/test_slot_busy_refusal.py",
    "tests/test_task_preparation.py",
)


@pytest.mark.parametrize("relative", CAPPED)
def test_the_lines_of_every_file_this_lane_created_stay_within_100_characters(relative):
    path = ROOT / relative
    assert path.is_file(), f"{relative} is listed as capped and does not exist"
    lines = path.read_text(encoding="utf-8").splitlines()
    over = [f"line {number} has {len(line)}" for number, line in enumerate(lines, 1)
            if len(line) > LIMIT]
    assert not over, f"{relative}: {'; '.join(over)}"
