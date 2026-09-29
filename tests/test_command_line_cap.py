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
    "src/conductor/command/flow_routes.py",
    "src/conductor/command/flow_rules.py",
    "src/conductor/command/plan_budget.py",
    "src/conductor/command/preview_draft.py",
    "src/conductor/command/product_names.py",
    "src/conductor/command/project_cycle.py",
    "src/conductor/command/project_git.py",
    "src/conductor/command/task_preparation.py",
    "src/conductor/command/workflow_flow.py",
    "tests/test_command_line_cap.py",
    "tests/test_command_flow_fixtures.py",
    "tests/test_command_flow_import_corners.py",
    "tests/test_command_flow_routes.py",
    "tests/test_command_flow_rules.py",
    "tests/test_command_import_hygiene.py",
    "tests/test_command_plan_budget.py",
    "tests/test_command_product_names.py",
    "tests/test_command_project_cycle.py",
    "tests/test_command_project_git.py",
    "tests/test_command_project_route.py",
    "tests/test_command_workflow_flow.py",
    "tests/test_policy_driver_slot.py",
    "tests/test_preview_draft.py",
    "tests/test_preview_stale_refusal.py",
    "tests/test_project_not_active_refusal.py",
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
