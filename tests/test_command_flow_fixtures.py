"""FlowState and Budget fixtures of the five cycles of spec 7.8, held to the spec and to themselves.

The desk draws from these files before the routes exist (spec 7.12 item 1). Two independent checks
keep them honest without `plan_budget`: the totals equal the five rows of the 7.8 table typed in
below from the spec, and every derived number follows from the `steps` rows and the flow by the
7.8 formulas. On day 5 `plan_budget` has to reproduce the files from the flows.
"""
import json
from pathlib import Path

import pytest

from conductor.command.workflow_flow import LINK_WHEN, settled_flow

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "flow"
CYCLES = ["desk-standard", "desk-short", "desk-starter-docs", "desk-standard-tester", "dalio-v5"]
#: spec 7.8 table: clean (actions, seconds), worst (actions, seconds), terms_draft (actions, seconds, window)
TABLE = {
    "desk-standard": ((2, 5400), (4, 12600), (4, 12600, 16200)),
    "desk-short": ((1, 3600), (2, 7200), (2, 7200, 10800)),
    "desk-starter-docs": ((3, 5400), (3, 5400), (3, 5400, 9000)),
    "desk-standard-tester": ((3, 9000), (6, 19800), (6, 19800, 23400)),
    "dalio-v5": ((5, 10800), (14, 32400), (8, 28800, 36000)),
}
STATE_KEYS = ["workflow_id", "source", "draft_digest", "flow", "revision_flow", "diagnostics",
              "publishable", "budget", "latest_revision", "next_revision", "published"]
BUDGET_KEYS = ["limits", "clean", "worst", "steps", "terms_draft", "spent", "exhausted", "inputs"]
LIMITS = {"max_actions": 8, "max_action_seconds": 3600, "max_total_task_seconds": 28800}
ROAD_OF_SUCCESS = {"success", "approved", "always"}


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def state(cycle):
    return load(f"{cycle}.flow-state.json")


def reserves(flow, budget):
    """(step_id, attempts, reserve) per counted step; the reserve is recomputed from the flow."""
    agents = {row["step_id"]: row for row in flow["steps"] if row["type"] == "agent"}
    rows = []
    for row in budget["steps"]:
        checked = agents[row["step_id"]]["verifier_role_id"] is not None
        assert row["reserve_seconds"] == row["timeout_seconds"] * (2 if checked else 1)
        rows.append((row["step_id"], row["attempts"], row["reserve_seconds"]))
    return rows


def clean_pass(flow):
    """Steps reached from the start by success, approved and always roads, never entering a loop."""
    kinds = {row["step_id"]: row["type"] for row in flow["steps"]}
    targets = {link["to"] for link in flow["links"]}
    frontier = [step_id for step_id in kinds if step_id not in targets and kinds[step_id] != "loop"]
    reached = []
    while frontier:
        step_id = frontier.pop(0)
        if step_id in reached:
            continue
        reached.append(step_id)
        frontier.extend(link["to"] for link in flow["links"] if link["from"] == step_id
                        and link["when"] in ROAD_OF_SUCCESS and kinds[link["to"]] != "loop")
    return reached, kinds


def humans_on_clean_pass(flow):
    reached, kinds = clean_pass(flow)
    return sum(kinds[step_id] == "human" for step_id in reached)


@pytest.mark.parametrize("cycle", CYCLES)
def test_every_flow_fixture_is_a_closed_flow_state_whose_flow_settles_unchanged(cycle):
    value = state(cycle)
    assert list(value) == STATE_KEYS and list(value["budget"]) == BUDGET_KEYS
    assert value["source"] in {"draft", "published"} and value["published"] is None
    assert value["budget"]["limits"] == LIMITS and value["budget"]["spent"] is None
    assert value["budget"]["exhausted"] is False
    assert settled_flow(value["flow"]) == value["flow"]
    if value["revision_flow"] is not None:
        assert settled_flow(value["revision_flow"]) == value["revision_flow"]
    flow = value["flow"]
    ids = [row["step_id"] for row in flow["steps"]]
    assert len(set(ids)) == len(ids)
    assert all(link["from"] in ids and link["to"] in ids and link["when"] in LINK_WHEN for link in flow["links"])
    assert all(row["back_to"] in ids for row in flow["steps"] if row["type"] == "loop")
    for row in value["diagnostics"]:
        assert list(row) == ["code", "severity", "at", "params"] and row["severity"] in {"error", "warning"}
        at = row["at"]
        assert at is None or at.get("step_id") in ids or (
            list(at) == ["link"] and dict(zip(("from", "to", "when"), at["link"])) in flow["links"])


@pytest.mark.parametrize("cycle", CYCLES)
def test_budget_of_each_fixture_cycle_matches_the_section_7_8_table(cycle):
    budget = state(cycle)["budget"]
    clean, worst, terms = TABLE[cycle]
    assert (budget["clean"]["actions"], budget["clean"]["seconds"]) == clean
    assert (budget["worst"]["actions"], budget["worst"]["seconds"]) == worst
    draft = budget["terms_draft"]
    assert (draft["max_actions"], draft["max_total_task_seconds"], draft["duration_seconds"]) == terms


@pytest.mark.parametrize("cycle", CYCLES)
def test_terms_draft_follows_from_the_budget_steps_and_the_human_steps_on_the_clean_pass(cycle):
    value = state(cycle)
    flow, budget = value["flow"], value["budget"]
    rows = reserves(flow, budget)
    reached, kinds = clean_pass(flow)
    counted = [step_id for step_id in reached if kinds[step_id] == "agent"]
    seconds = {step_id: reserve for step_id, _, reserve in rows}
    assert [step_id for step_id, _, _ in rows] == [row["step_id"] for row in flow["steps"] if row["type"] == "agent"]
    assert budget["clean"] == {"actions": len(counted), "seconds": sum(seconds[step_id] for step_id in counted)}
    worst = sum(attempts for _, attempts, _ in rows), sum(attempts * reserve for _, attempts, reserve in rows)
    assert (budget["worst"]["actions"], budget["worst"]["seconds"]) == worst
    total = min(28800, worst[1])
    assert budget["terms_draft"] == {
        "node_limits": [{"node_id": row["step_id"], "timeout_seconds": row["timeout_seconds"],
                         "max_attempts": row["attempts"]} for row in budget["steps"]],
        "max_actions": min(8, worst[0]), "max_action_seconds": max(seconds.values()),
        "max_total_task_seconds": total,
        "duration_seconds": min(86400, max(3600, total + 3600 * humans_on_clean_pass(flow)))}
    assert all(row["clamped"] is False for row in budget["steps"])


@pytest.mark.parametrize("cycle", CYCLES)
def test_publishable_is_true_exactly_when_no_diagnostic_row_is_an_error(cycle):
    value = state(cycle)
    assert value["publishable"] is (not any(row["severity"] == "error" for row in value["diagnostics"]))


def replacement(fresh, spent, humans):
    """The 7.8 terms of a replacement grant, from the fresh budget's rows and what the run spent."""
    used = {row["step_id"]: row["attempts"] for row in spent["attempts"]}
    steps = fresh["steps"]
    remaining = {row["step_id"]: max(0, row["attempts"] - used.get(row["step_id"], 0)) for row in steps}
    left = sum(remaining[row["step_id"]] * row["reserve_seconds"] for row in steps)
    return {
        "node_limits": [{"node_id": row["step_id"], "timeout_seconds": row["timeout_seconds"],
                         "max_attempts": max(row["attempts"], used.get(row["step_id"], 0))} for row in steps],
        "max_actions": min(8, spent["actions"] + sum(remaining.values())),
        "max_action_seconds": max(row["reserve_seconds"] for row in steps),
        "max_total_task_seconds": min(28800, spent["seconds"] + left),
        "duration_seconds": min(86400, max(3600, left + 3600 * humans))}, sum(remaining.values()) == 0


def test_replacing_budget_adds_the_spent_totals_and_keeps_the_window_to_the_remaining_work():
    fresh = state("desk-standard")
    budget = load("desk-standard.budget-replacing.json")
    assert list(budget) == BUDGET_KEYS
    for key in ("limits", "clean", "worst", "steps", "inputs"):
        assert budget[key] == fresh["budget"][key], "only spent, the terms and exhausted differ from a fresh plan"
    assert budget["spent"] == {"actions": 2, "seconds": 5400, "attempts": [
        {"step_id": "analyst", "attempts": 1}, {"step_id": "do", "attempts": 1}]}
    terms, exhausted = replacement(fresh["budget"], budget["spent"], humans_on_clean_pass(fresh["flow"]))
    assert budget["terms_draft"] == terms and budget["exhausted"] is exhausted is False
    assert terms["max_total_task_seconds"] == 12600 and terms["duration_seconds"] == 10800


def test_replacing_budget_with_no_admissible_action_is_exhausted():
    fresh = state("desk-short")
    budget = load("desk-short.budget-exhausted.json")
    assert list(budget) == BUDGET_KEYS
    assert budget["spent"] == {"actions": 2, "seconds": 7200, "attempts": [{"step_id": "do", "attempts": 2}]}
    terms, exhausted = replacement(fresh["budget"], budget["spent"], humans_on_clean_pass(fresh["flow"]))
    assert budget["terms_draft"] == terms and budget["exhausted"] is exhausted is True
