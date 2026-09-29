"""The budget of a cycle, computed on the server (spec 7.8, L18).

`plan_budget` reads a template's nodes or a frozen plan's nodes alike and answers the `Budget` of
the spec. The numbers are held to the five rows of the 7.8 table (typed in below from the spec) and
to the five fixture budgets the desk draws from; the formulas are held case by case.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command.flow_rules import flow_rules
from conductor.command.graph_template_document import GraphTemplate, _build
from conductor.command.plan_budget import plan_budget
from conductor.command.workflow_flow import compile_flow
from tests.test_command_workflow_flow import CYCLES, chain, fixture_flow, review, step

LIMITS = {"max_actions": 8, "max_action_seconds": 3600, "max_total_task_seconds": 28800}
#: Spec 7.8: (clean actions, clean seconds), (worst actions, worst seconds), then terms_draft as
#: (actions, seconds, window).
TABLE = {
    "desk-standard": ((2, 5400), (4, 12600), (4, 12600, 16200)),
    "desk-short": ((1, 3600), (2, 7200), (2, 7200, 10800)),
    "desk-starter-docs": ((3, 5400), (3, 5400), (3, 5400, 9000)),
    "desk-standard-tester": ((3, 9000), (6, 19800), (6, 19800, 23400)),
    "dalio-v5": ((5, 10800), (14, 32400), (8, 28800, 36000)),
}


def template_of(flow):
    document = {**compile_flow(flow), "template_id": "cycle-test", "revision": 1}
    return GraphTemplate.from_dict(document)


def plan_of(flow, limits=LIMITS, spent=None):
    nodes, edges = template_of(flow).settled()
    return plan_budget(nodes, edges, limits, spent)


def budget_fixture(name):
    root = Path(__file__).resolve().parent / "fixtures" / "flow"
    return json.loads((root / name).read_text(encoding="utf-8"))


def attempts_of(budget):
    return {row["step_id"]: row["attempts"] for row in budget["steps"]}


@pytest.mark.parametrize("cycle", CYCLES)
def test_budget_of_each_cycle_matches_the_section_7_8_table(cycle):
    clean, worst, terms = TABLE[cycle]
    budget = plan_of(fixture_flow(cycle))
    assert (budget["clean"]["actions"], budget["clean"]["seconds"]) == clean
    assert (budget["worst"]["actions"], budget["worst"]["seconds"]) == worst
    draft = budget["terms_draft"]
    assert (draft["max_actions"], draft["max_total_task_seconds"],
            draft["duration_seconds"]) == terms
    assert budget == budget_fixture(f"{cycle}.flow-state.json")["budget"]


def test_the_budget_has_the_form_of_the_spec_and_is_plain_json():
    budget = plan_of(fixture_flow("desk-standard"))
    assert list(budget) == ["limits", "clean", "worst", "steps", "terms_draft", "spent",
                            "exhausted", "inputs"]
    assert budget["spent"] is None and budget["exhausted"] is False
    assert json.loads(json.dumps(budget)) == budget
    assert budget["limits"] == LIMITS


def dispatch(step_id, **own):
    return step(step_id, "agent", verifier_role_id="role-checker", timeout_seconds=1800, **own)


def with_loops(flow, *loops):
    """Add pass loops as `(source, back_to, bound)`: a loop step and its `failed` road."""
    for source, back_to, bound in loops:
        name = f"{source}-fix-{back_to}-{bound}"
        flow["steps"].append(step(name, "loop", back_to=back_to, bound=bound))
        flow["links"].append({"from": source, "to": name, "when": "failed"})
    return flow


def test_loops_sharing_a_back_to_count_their_largest_bound_once():
    flow = with_loops(chain(dispatch("do"), step("result", "human")),
                      ("do", "do", 3), ("do", "do", 2))
    assert attempts_of(plan_of(flow)) == {"do": 3}


def test_frames_of_different_back_to_add_one_less_than_each_bound():
    flow = chain(review("plan"), dispatch("do"), step("result", "human"))
    flow["steps"].append(step("rework", "loop", back_to="plan", bound=3))
    flow["links"].append({"from": "result", "to": "rework", "when": "changes_requested"})
    with_loops(flow, ("do", "do", 2))
    assert attempts_of(plan_of(flow)) == {"plan": 3, "do": 1 + 2 + 1}


def test_the_clean_pass_leaves_out_steps_only_a_failure_or_a_rejection_reaches():
    flow = chain(review("plan"), step("decide", "human"))
    flow["steps"] += [dispatch("do"), review("other", role_id="role-reviewer"),
                      dispatch("patch"), step("result", "human")]
    flow["links"] += [{"from": "decide", "to": "do", "when": "approved"},
                      {"from": "decide", "to": "other", "when": "rejected"},
                      {"from": "do", "to": "result", "when": "success"},
                      {"from": "do", "to": "patch", "when": "failed"}]
    budget = plan_of(flow)
    assert (budget["clean"]["actions"], budget["worst"]["actions"]) == (2, 4)
    assert [row["step_id"] for row in budget["steps"]] == ["plan", "do", "other", "patch"]
    assert budget["worst"]["seconds"] == 1800 + 3600 + 1800 + 3600
    assert budget["terms_draft"]["duration_seconds"] == 10800 + 3600 * 2, (
        "the window adds an hour for each human answer of the clean pass: decide and result")


def test_a_tester_return_and_a_doer_pass_loop_count_one_frame_and_take_the_larger_bound():
    flow = chain(dispatch("do"), dispatch("tester", role_id="role-tester"),
                 step("result", "human"))
    with_loops(flow, ("do", "do", 3), ("tester", "do", 2))
    assert attempts_of(plan_of(flow)) == {"do": 3, "tester": 2}


def test_attempt_bound_caps_the_attempts():
    flow = with_loops(chain(dispatch("do", ext={"attempt_bound": 2}), step("result", "human")),
                      ("do", "do", 3))
    budget = plan_of(flow)
    assert attempts_of(budget) == {"do": 2}
    assert budget["terms_draft"]["node_limits"][0]["max_attempts"] == 2


@pytest.mark.parametrize("checked,seconds,expected", [
    (True, 3000, (1800, 3600, True)),
    (True, 1800, (1800, 3600, False)),
    (False, 3000, (3000, 3000, False)),
    (False, 5000, (3600, 3600, True)),
    (False, None, (1800, 1800, False))])
def test_checked_step_over_1800_seconds_is_clamped_and_marked(checked, seconds, expected):
    do = step("do", "agent", timeout_seconds=seconds,
              verifier_role_id="role-checker" if checked else None)
    row = plan_of(chain(do, step("result", "human")))["steps"][0]
    assert (row["timeout_seconds"], row["reserve_seconds"], row["clamped"]) == expected


def test_a_step_that_reserves_more_than_the_action_ceiling_is_clamped_to_it():
    do = step("do", "agent", timeout_seconds=1800, verifier_role_id="role-checker")
    limits = {**LIMITS, "max_action_seconds": 1000}
    row = plan_of(chain(do, step("result", "human")), limits)["steps"][0]
    assert (row["timeout_seconds"], row["reserve_seconds"], row["clamped"]) == (500, 1000, True)


@pytest.mark.parametrize("cycle", CYCLES)
def test_budget_reads_a_frozen_plan_and_its_template_alike(cycle):
    template = template_of(fixture_flow(cycle))
    roles = {role: f"instance-{number}" for number, role in enumerate(template.roles)}
    plan = _build(template, roles, graph_id="graph-1", run_id="run-1",
                  created_at="2026-09-29T10:00:00Z")
    nodes, edges = template.settled()
    assert plan_budget(plan.nodes, plan.edges, LIMITS) == plan_budget(nodes, edges, LIMITS)


def test_the_limits_are_the_callers_and_the_module_keeps_none_of_its_own():
    limits = {"max_actions": 2, "max_action_seconds": 1000, "max_total_task_seconds": 2000}
    budget = plan_of(fixture_flow("desk-standard"), limits)
    assert budget["limits"] == limits
    assert [(row["timeout_seconds"], row["clamped"]) for row in budget["steps"]] == [
        (1000, True), (500, True)]
    draft = budget["terms_draft"]
    assert (draft["max_actions"], draft["max_action_seconds"]) == (2, 1000)
    assert draft["max_total_task_seconds"] == 2000


def test_a_budget_of_no_agent_step_is_empty_and_does_not_fail():
    budget = plan_of(chain(step("only", "human")))
    assert budget["clean"] == {"actions": 0, "seconds": 0} and budget["steps"] == []
    assert budget["terms_draft"]["max_actions"] == 0
    assert budget["terms_draft"]["max_action_seconds"] == 0
    assert budget["terms_draft"]["duration_seconds"] == 3600


def node(node_id, **own):
    values = {"node_id": node_id, "kind": "task", "capability": None, "timeout_seconds": None,
              "attempt_bound": None, "loop": None, "verifier_role_id": None,
              "payload": lambda: {}}
    return SimpleNamespace(**{**values, **own})


def test_a_loop_that_reopens_a_step_the_plan_does_not_carry_is_ignored_not_fatal():
    do = node("do", capability="dispatch", payload=lambda: {"instruction_ref": "instruction-do"})
    loop = node("fix", kind="loop", loop=SimpleNamespace(bound=5, back_to="ghost"))
    edges = [SimpleNamespace(from_node="do", to_node="fix", condition="on_failed")]
    assert plan_budget([do, loop], edges, LIMITS)["worst"]["actions"] == 1


def test_inputs_list_the_instruction_of_each_dispatch_node_in_node_order():
    flow = chain(dispatch("second"), dispatch("first", role_id="role-tester"),
                 step("result", "human"))
    flow["steps"][0]["instruction_from"] = "first"
    flow["steps"][0], flow["steps"][1] = flow["steps"][1], flow["steps"][0]
    budget = plan_of(flow)
    assert budget["inputs"] == {
        "instructions": [{"step_id": "first", "instruction_ref": "instruction-first"},
                         {"step_id": "second", "instruction_ref": "instruction-first"}],
        "documents": ["artifact-brief", "artifact-materials"]}


def test_replacing_draft_adds_the_spent_totals_and_keeps_the_window_to_the_remaining_work():
    fixture = budget_fixture("desk-standard.budget-replacing.json")
    spent = fixture["spent"]
    budget = plan_of(fixture_flow("desk-standard"), spent=spent)
    assert budget == fixture
    assert budget["terms_draft"]["max_total_task_seconds"] == 12600
    assert budget["terms_draft"]["duration_seconds"] == 10800


def test_replacing_draft_with_no_admissible_action_is_exhausted():
    fixture = budget_fixture("desk-short.budget-exhausted.json")
    budget = plan_of(fixture_flow("desk-short"), spent=fixture["spent"])
    assert budget == fixture and budget["exhausted"] is True


def test_a_draft_is_exhausted_when_attempts_remain_but_the_run_has_no_action_left():
    flow = with_loops(chain(dispatch("do"), step("result", "human")), ("do", "do", 3))
    spent = {"actions": 8, "seconds": 3600, "attempts": [{"step_id": "do", "attempts": 1}]}
    assert plan_of(flow, spent=spent)["exhausted"] is True
    assert plan_of(flow, spent={**spent, "actions": 7})["exhausted"] is False


def test_a_draft_is_exhausted_when_the_remaining_time_cannot_hold_one_more_action():
    flow = with_loops(chain(dispatch("do"), step("result", "human")), ("do", "do", 3))
    spent = {"actions": 2, "seconds": 28800 - 3599,
             "attempts": [{"step_id": "do", "attempts": 2}]}
    assert plan_of(flow, spent=spent)["exhausted"] is True


def test_spent_is_echoed_as_a_copy_and_attempts_of_unknown_steps_change_nothing():
    flow = chain(dispatch("do"), step("result", "human"))
    spent = {"actions": 1, "seconds": 3600,
             "attempts": [{"step_id": "ghost", "attempts": 4}, {"step_id": "do", "attempts": 1}]}
    budget = plan_of(flow, spent=spent)
    assert budget["spent"] == spent and budget["spent"] is not spent
    assert budget["exhausted"] is True


def test_clean_pass_over_eight_actions_is_an_error_and_worst_case_over_eight_a_warning():
    long = chain(*[review(f"r{number}") for number in range(9)], step("result", "human"))
    rows = flow_rules(long, budget=plan_of(long))
    assert {row["code"]: row["severity"] for row in rows}["clean_over_actions"] == "error"
    dalio = fixture_flow("dalio-v5")
    rows = flow_rules(dalio, budget=plan_of(dalio))
    severities = {row["code"]: row["severity"] for row in rows}
    assert severities["worst_over_actions"] == severities["worst_over_time"] == "warning"
    assert "error" not in severities.values(), "over the worst case a cycle still publishes"
