"""The automation model and its words know every reason the server can give (spec 4.4.1).

`GET /command/runs/<run_id>/automation` gives a `(state, reason_code)` pair, and the Studio's model
judges the read against a closed list of reasons: a reason it does not know makes the whole read
`null`, and the desk's slot and rail then lose the run's automation. Lane L added two values in
`policy_view.py` (`project_not_active` under `restart_required` in a process opened for viewing,
`seed_blocked` under `stalled`), so this holds the model to what the server says, in BOTH
directions, and holds each reason to a message in both languages.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.desk_node import run_js

ROOT = Path(__file__).resolve().parents[1]
POLICY_VIEW = ROOT / "src" / "conductor" / "command" / "policy_view.py"
MODULES = {"model": "studio-automation-model.js", "copy": "studio-automation-copy.js"}


def _server_reasons() -> set[str]:
    """Every literal reason `automation_view` can give, read off the source of `policy_view`.

    The returns of `_state` are `(state, reason)` pairs; the one that returns a name (`reason`)
    takes it from the driver, whose closed set is `_STALLS`.
    """
    tree = ast.parse(POLICY_VIEW.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_state":
            for inner in ast.walk(node):
                if isinstance(inner, ast.Return) and isinstance(inner.value, ast.Tuple):
                    reason = inner.value.elts[1]
                    if isinstance(reason, ast.Constant):
                        found.add(reason.value)
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "_STALLS"
                for target in node.targets):
            found |= {item.value for item in ast.walk(node.value)
                      if isinstance(item, ast.Constant) and isinstance(item.value, str)}
    return found


def _model_reasons() -> list[str]:
    return run_js("console.log(JSON.stringify([...model.AUTOMATION_REASONS]));", MODULES)


def test_the_source_reader_finds_the_reasons_the_server_is_known_to_give():
    """The instrument is calibrated: a reader that found nothing would turn the next test green."""
    found = _server_reasons()
    assert {"authorization_required", "ready", "plan_waiting", "feedback_required"} <= found
    assert len(found) >= 16


def test_the_models_reasons_are_exactly_the_reasons_the_server_can_give():
    model, server = set(_model_reasons()), _server_reasons()
    never_given, refused = model - server, server - model
    assert never_given == set(), f"the model names reasons the server never gives: {never_given}"
    assert refused == set(), f"the server gives reasons the model refuses: {refused}"


@pytest.mark.parametrize("reason", ["project_not_active", "seed_blocked"])
def test_a_read_that_carries_a_reason_lane_l_added_is_judged_and_not_refused(reason):
    """The read a `view` process gives for a run that holds a grant is not `null`."""
    verdicts = run_js("""
      const detail = {run: {run_id: "run-1", mode: "policy"},
        config: {automation_contract: "bounded-run-v1"}, graph: {definition: {nodes: []}}};
      const read = {run_id: "run-1", authorization: null, control: null, state: "unconfigured",
        reason_code: d, active_action_id: null, next_node_id: null, spent_actions: 0,
        remaining_actions: 0, spent_task_seconds: 0, remaining_task_seconds: 0, expires_at: null,
        owner_present: true};
      console.log(JSON.stringify(model.projectAutomation(read, detail) !== null));
    """, MODULES, reason)
    assert verdicts is True


def test_every_reason_the_server_gives_has_a_message_in_both_languages():
    messages = run_js("console.log(JSON.stringify(copy.AUTOMATION_COPY));", MODULES)
    missing = [reason for reason in sorted(_server_reasons())
               if not (isinstance(messages.get(f"automation.{reason}"), list)
                       and len(messages[f"automation.{reason}"]) == 2
                       and all(text.strip() for text in messages[f"automation.{reason}"]))]
    assert missing == []
