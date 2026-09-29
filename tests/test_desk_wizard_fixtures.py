"""The stand-in fixtures of steps 5 and 6, held to the spec lines they are taken from.

Lane L builds the preparation read (6.4.2), the preview `{}` with `budget` (6.4.4, 7.8) and the
queue read with `slot` (4.4.6) in parallel; the wizard is built on these files. Every key set below
is written BY HAND from the spec lines named in `tests/fixtures/wizard/README.md`, never read off a
fixture, so a stand-in that drifts from the spec turns a test red instead of quietly moving the
wizard with it. What the wizard reads is a shape; the values are invented.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import pytest

from tests.desk_wizard_node import FIXTURES, fixture

WIZARD = FIXTURES / "wizard"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
#: 6.4.2, lines 2984-3008.
PREPARATION = {"task", "seed", "next_run_number", "runs"}
TASK = {"schema_version", "task_id", "title", "work_scope", "created_at"}
RUN = {"run_id", "created_at", "workflow_id", "revision", "stage", "missing", "grant", "queue"}
MISSING = {"instructions", "inputs"}
GRANT = {"authorization_id", "authorized_by", "authorized_at", "preauthorized_at"}
QUEUE_ROW = {"position", "state", "reason_code", "state_since"}
STAGES = ("ended", "queued", "authorized", "documents_missing", "ready_to_preview")
#: 9.1.5, lines 4289-4301: the record and, in the read, its `state`.
SEED = {"schema_version", "task_id", "work_scope", "work_item_id", "source", "base_commit",
        "base_tree", "object_format", "base_ref", "file_count", "total_bytes",
        "include_agent_instructions", "staging", "skipped", "agent_instructions_skipped",
        "warnings", "staged_at", "state"}
#: 6.4.4, lines 3049-3051, and the run terms of `command/policy_preview.py`.
PREVIEW = {"terms", "preview_digest", "previewed_at", "provider_facts", "valid_until", "budget"}
TERMS = {"run_id", "contract", "config_digest", "graph_digest", "provider_config_digest",
         "source_prefix_digest", "node_limits", "instruction_bindings", "initial_input_bindings",
         "max_actions", "max_action_seconds", "max_total_task_seconds", "concurrency",
         "failure_handling", "duration_seconds"}
#: 7.8, lines 3588-3602.
BUDGET = {"limits", "clean", "worst", "steps", "terms_draft", "spent", "exhausted", "inputs"}
#: 4.4.6, lines 1149-1157 and the slot table, lines 1161-1171.
QUEUE = {"schema_version", "revision", "slot", "entries"}
SLOT = {"state", "run_id", "reason_code"}
ENTRY = {"run_id", "task_id", "title", "position", "kind", "enqueued_at", "enqueued_by", "state",
         "reason_code", "state_since", "preauthorization"}
SLOT_ROWS = {("free", None), ("busy", "plan_waiting"), ("busy", "action_in_flight"),
             ("busy", "ready"), ("busy", "paused"), ("busy", "revoked"), ("busy", "plan_ended"),
             ("stuck", "expired"), ("stuck", "stalled"), ("stuck", "feedback_required"),
             ("stuck", "unknown_action"), ("stuck", "ambiguous_actions"),
             ("stuck", "admission_refused"), ("stuck", "plan_stalled"), ("stuck", "seed_blocked"),
             ("unavailable", "project_not_active"), ("unavailable", "owner_required"),
             ("unavailable", "server_stopping")}
ENTRY_STATES = {"preauthorized": {"behind", "slot_busy", "slot_unavailable", "project_not_active"},
                "confirmation_required": {"terms_changed", "grant_expired", "grant_changed",
                                          "preview_refused", "server_restarted"},
                "blocked": {"run_unreadable", "receipt_conflict"}}
#: The keys `automation_view` returns (`command/policy_view.py`).
AUTOMATION = {"run_id", "authorization", "control", "state", "reason_code", "active_action_id",
              "next_node_id", "spent_actions", "remaining_actions", "spent_task_seconds",
              "remaining_task_seconds", "expires_at", "owner_present"}


def keys(value: Any, expected: set[str], where: str) -> None:
    """The closed key set of one object: an extra key and a missing key are both a fault."""
    assert isinstance(value, dict), f"{where} is not an object"
    assert set(value) == expected, (
        f"{where}: extra {sorted(set(value) - expected)}, missing {sorted(expected - set(value))}")


def files(prefix: str) -> list[str]:
    return sorted(path.name for path in WIZARD.glob(f"{prefix}*.json"))


PREPARATIONS = files("preparation_")
PREVIEWS = files("preview_")
QUEUES = files("queue_")


def test_the_key_set_guard_names_an_extra_and_a_missing_key():
    with pytest.raises(AssertionError, match="extra \\['z'\\], missing \\['b'\\]"):
        keys({"a": 1, "z": 2}, {"a", "b"}, "sample")
    with pytest.raises(AssertionError, match="is not an object"):
        keys([], {"a"}, "sample")
    keys({"a": 1}, {"a"}, "sample")


@pytest.mark.parametrize("name", PREPARATIONS)
def test_a_preparation_fixture_has_exactly_the_keys_of_spec_6_4_2(name):
    read = fixture("wizard", name)
    keys(read, PREPARATION, name)
    keys(read["task"], TASK, f"{name} task")
    assert read["task"]["schema_version"] == 1
    if read["seed"] is not None:
        keys(read["seed"], SEED, f"{name} seed")
        assert read["seed"]["state"] in ("staged", "seeded", "seed_lost", "requested")
    assert isinstance(read["next_run_number"], int) and read["next_run_number"] >= 1
    for row in read["runs"]:
        keys(row, RUN, f"{name} run")
        keys(row["missing"], MISSING, f"{name} missing")
        assert row["stage"] in STAGES
        assert INSTANT.match(row["created_at"])
        for pair in row["missing"]["instructions"]:
            keys(pair, {"node_id", "instruction_ref"}, f"{name} instruction row")
        if row["grant"] is not None:
            keys(row["grant"], GRANT, f"{name} grant")
        if row["queue"] is not None:
            keys(row["queue"], QUEUE_ROW, f"{name} queue")


@pytest.mark.parametrize("name", PREPARATIONS)
def test_a_preparation_fixture_states_the_stage_its_own_facts_give(name):
    """Lines 3000-3005: the first matching value; `ended` needs the run's own end, which the row
    does not carry, so it is the one stage the row cannot contradict."""
    read = fixture("wizard", name)
    for row in read["runs"]:
        lists = row["missing"]
        if row["stage"] == "ended":
            continue
        if row["queue"] is not None:
            expected = "queued"
        elif row["grant"] is not None:
            expected = "authorized"
        elif lists["instructions"] or lists["inputs"]:
            expected = "documents_missing"
        else:
            expected = "ready_to_preview"
        assert row["stage"] == expected, (name, row["run_id"])


@pytest.mark.parametrize("name", PREPARATIONS)
def test_next_run_number_is_past_every_listed_run_of_the_task(name):
    read = fixture("wizard", name)
    task = read["task"]["task_id"]
    numbers = [int(re.fullmatch(rf"{re.escape(task)}-r([0-9]+)", row["run_id"]).group(1))
               for row in read["runs"]]
    assert read["next_run_number"] >= 1 + max(numbers, default=0)


def test_an_unreadable_run_is_counted_in_the_next_number_but_not_listed():
    read = fixture("wizard", "preparation_two_runs.json")
    listed = [row["run_id"] for row in read["runs"]]
    assert listed == ["task-bench-r1", "task-bench-r2"] and read["next_run_number"] == 4


@pytest.mark.parametrize("name", PREVIEWS)
def test_a_preview_fixture_has_exactly_the_keys_of_spec_6_4_4_and_a_budget_inside(name):
    preview = fixture("wizard", name)
    keys(preview, PREVIEW, name)
    keys(preview["terms"], TERMS, f"{name} terms")
    keys(preview["budget"], BUDGET, f"{name} budget")
    assert preview["terms"]["contract"] == "bounded-run-v1"
    assert preview["terms"]["concurrency"] == 1
    assert DIGEST.match(preview["preview_digest"])
    for key in ("config_digest", "graph_digest", "provider_config_digest", "source_prefix_digest"):
        assert DIGEST.match(preview["terms"][key]), key
    assert INSTANT.match(preview["previewed_at"]) and INSTANT.match(preview["valid_until"])
    assert "budget" not in preview["terms"], "the budget is in neither the terms nor the digest"


@pytest.mark.parametrize("name,flow_file,budget_key", [
    ("preview_standard.json", "desk-standard.flow-state.json", "budget"),
    ("preview_replacing.json", "desk-standard.budget-replacing.json", None),
    ("preview_exhausted.json", "desk-short.budget-exhausted.json", None)])
def test_the_preview_budget_is_the_flow_fixtures_budget_unchanged(name, flow_file, budget_key):
    expected = fixture("flow", flow_file)
    expected = expected[budget_key] if budget_key else expected
    assert fixture("wizard", name)["budget"] == expected


@pytest.mark.parametrize("name", PREVIEWS)
def test_the_preview_terms_are_the_budgets_draft_and_the_bindings_are_the_inputs(name):
    """6.4.4, line 3050: the server builds the preview from the plan's `terms_draft`."""
    preview = fixture("wizard", name)
    terms, budget = preview["terms"], preview["budget"]
    for key in ("node_limits", "max_actions", "max_action_seconds", "max_total_task_seconds",
                "duration_seconds"):
        assert terms[key] == budget["terms_draft"][key], key
    assert [row["node_id"] for row in terms["instruction_bindings"]] == [
        row["step_id"] for row in budget["inputs"]["instructions"]]
    refs = [row["artifact_ref"] for row in terms["initial_input_bindings"]]
    assert refs == sorted(refs) == sorted(budget["inputs"]["documents"])
    for row in (*terms["instruction_bindings"], *terms["initial_input_bindings"]):
        assert DIGEST.match(row["content_digest"]) and re.fullmatch(r"doc-[0-9a-f]{32}",
                                                                    row["artifact_id"])


@pytest.mark.parametrize("name", PREVIEWS)
def test_the_preview_is_valid_for_three_hundred_seconds_and_names_the_providers_it_read(name):
    preview = fixture("wizard", name)
    span = datetime.fromisoformat(preview["valid_until"].replace("Z", "+00:00")) \
        - datetime.fromisoformat(preview["previewed_at"].replace("Z", "+00:00"))
    assert span.total_seconds() == 300
    providers = preview["provider_facts"]["providers"]
    assert providers and all(row["config"]["provider_id"] == row["contract"]["provider_id"]
                             for row in providers)


@pytest.mark.parametrize("name", QUEUES)
def test_a_queue_fixture_has_exactly_the_keys_of_spec_4_4_6(name):
    read = fixture("wizard", name)
    keys(read, QUEUE, name)
    keys(read["slot"], SLOT, f"{name} slot")
    assert (read["slot"]["state"], read["slot"]["reason_code"]) in SLOT_ROWS
    for position, entry in enumerate(read["entries"], start=1):
        keys(entry, ENTRY, f"{name} entry")
        assert entry["position"] == position
        assert entry["reason_code"] in ENTRY_STATES[entry["state"]]


def test_the_queue_slot_fixtures_cover_every_row_of_the_slot_table_the_card_acts_on():
    """6.4.5, lines 3114-3120: free, busy (a holder that waits for a human, and one that does not),
    stuck, unavailable in view, and the two unavailable rows with no button."""
    slots = [fixture("wizard", name)["slot"] for name in QUEUES]
    seen = {(slot["state"], slot["reason_code"]) for slot in slots}
    assert {("free", None), ("busy", "plan_waiting"), ("busy", "action_in_flight"),
            ("stuck", "expired"), ("unavailable", "project_not_active"),
            ("unavailable", "owner_required"), ("unavailable", "server_stopping")} <= seen


def test_only_the_slot_with_a_holder_names_it_and_the_others_name_none():
    for name in QUEUES:
        slot = fixture("wizard", name)["slot"]
        assert (slot["run_id"] is not None) == (slot["state"] in ("busy", "stuck")), name


@pytest.mark.parametrize("name", ["automation_holder_waiting.json", "automation_unconfigured.json"])
def test_an_automation_fixture_has_exactly_the_keys_automation_view_returns(name):
    read = fixture("wizard", name)
    keys(read, AUTOMATION, name)
    if read["authorization"] is None:
        assert read["control"] is None and read["expires_at"] is None
    else:
        grant = read["authorization"]
        assert read["expires_at"] == grant["expires_at"]
        assert read["remaining_actions"] == grant["max_actions"] - read["spent_actions"]
        assert grant["schema_version"] == 2 and DIGEST.match(grant["authorization_digest"])


def test_the_run_detail_names_the_plans_nodes_and_the_instances_they_run_on():
    read = fixture("wizard", "run_detail.json")
    instances = {row["id"]: row["adapter"] for row in read["config"]["instances"]}
    for node in read["graph"]["definition"]["nodes"]:
        for name in ("instance_id", "verifier_instance_id"):
            assert node[name] is None or node[name] in instances, (node["node_id"], name)


def test_the_readme_names_every_fixture_of_the_three_reads():
    readme = (WIZARD / "README.md").read_text(encoding="utf-8")
    names = [*PREPARATIONS, *PREVIEWS, *QUEUES, "automation_holder_waiting.json",
             "automation_unconfigured.json", "run_detail.json"]
    assert [name for name in names if f"`{name}`" not in readme] == []
