"""`POST …/automation/preview` with the body `{}`: the server drafts the terms (spec 6.4.4, 7.8).

The desk sends no numbers. The server reads the run's frozen plan, asks `plan_budget` what it
needs, builds the preview from that draft and adds the `Budget` it computed to the answer. An
explicit body of the five `PREVIEW_FIELDS` is what it always was: the same five keys back, and
nothing of the `budget`. What the grant of a replacement adds (the spent totals) is read off the
run's journal, so the desk does no arithmetic.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conductor.command import preview_draft
from conductor.command.contract_values import ContractError, _content_digest
from conductor.command.contracts import ActionRequest
from conductor.command.graph_template import TEMPLATE_DIR, GraphTemplate, load_template
from conductor.command.http_api import CommandApi
from conductor.command.http_transport import CommandSession
from conductor.command.plan_budget import product_limits
from conductor.command.policy_preview import PREVIEW_FIELDS
from conductor.command.runtime import Budget
from tests.test_command_http_api import PORT, TOKEN, post
from tests.test_policy_driver import authorize as authorize_both_steps
from tests.test_policy_runtime import ASK, NOW, PD, propose, setup
from tests.test_slot_busy_refusal import TakenSlot, door
from tests.test_task_preparation import STANDARD_ASK, Project

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "flow"
OLD_KEYS = {"terms", "preview_digest", "previewed_at", "provider_facts", "valid_until"}
LIMITS = {"max_actions": 8, "max_action_seconds": 3600, "max_total_task_seconds": 28800}
#: The terms the short cycle is offered (spec 7.8): two actions, 7 200 s, a 3 600 s window.
SHORT_ASK = {"node_limits": [{"node_id": "do", "timeout_seconds": 1800, "max_attempts": 2}],
             "max_actions": 2, "max_action_seconds": 3600, "max_total_task_seconds": 7200,
             "duration_seconds": 3600}


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path / "project")


def drafted(project, run_id):
    return project.policy.preview(run_id, {})


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def spending(run_id, grant, *nodes):
    """Stored-looking rows for actions already requested under `grant`, one per node named."""
    rows = []
    for number, (node_id, capability, timeout) in enumerate(nodes):
        rows.append(SimpleNamespace(kind="action_request", value=ActionRequest(
            action_id=f"action-{number}", run_id=run_id, attempt_id=f"attempt-{number}",
            instance_id="doer", capability=capability, arguments={}, scope=("work/item",),
            requested_by="run-policy", requested_at=NOW, idempotency_key=f"key-{number}",
            timeout_seconds=timeout, preview_digest=PD, mode="policy", node_id=node_id,
            run_authorization_id=grant.authorization_id,
            run_authorization_digest=grant.authorization_digest)))
    return rows


def replacing_draft(project, run_id, *nodes, ask=STANDARD_ASK):
    grant = project.grant(run_id, ask)
    records = [*project.store.read(run_id).records, *spending(run_id, grant, *nodes)]
    return preview_draft.drafted_preview(records, LIMITS)


# --- the empty body -------------------------------------------------------------------------------


def test_empty_preview_body_uses_plan_budget_terms_draft_and_adds_budget(project):
    run_id = project.ready_run(1)
    answer = drafted(project, run_id)
    assert set(answer) == OLD_KEYS | {"budget"}
    assert {key: answer["terms"][key] for key in PREVIEW_FIELDS} == answer["budget"]["terms_draft"]
    assert answer["budget"]["limits"] == LIMITS
    assert answer["budget"]["spent"] is None and answer["budget"]["exhausted"] is False


def test_the_budget_is_in_neither_the_terms_nor_the_digest_nor_the_cached_preview(project):
    run_id = project.ready_run(1)
    answer = drafted(project, run_id)
    assert "budget" not in answer["terms"]
    assert answer["preview_digest"] == _content_digest(answer["terms"])
    cached = project.policy.previews.require(
        "session", run_id, answer["preview_digest"], answer["terms"], NOW)
    assert cached == {key: value for key, value in answer.items() if key != "budget"}


def test_explicit_preview_body_returns_exactly_the_five_old_keys(project):
    run_id = project.ready_run(1)
    answer = project.policy.preview(run_id, STANDARD_ASK)
    assert set(answer) == OLD_KEYS
    assert {key: answer["terms"][key] for key in PREVIEW_FIELDS} == STANDARD_ASK


@pytest.mark.parametrize("body", [{"max_actions": 4}, {**STANDARD_ASK, "extra": 1}, None, []])
def test_a_body_that_is_neither_empty_nor_the_five_fields_is_still_refused(project, body):
    run_id = project.ready_run(1)
    with pytest.raises(ContractError):
        project.policy.preview(run_id, body)


def test_standard_cycle_draft_is_4_actions_12600_seconds_and_16200_window(project):
    terms = drafted(project, project.ready_run(1))["terms"]
    assert (terms["max_actions"], terms["max_total_task_seconds"], terms["duration_seconds"]) == (
        4, 12600, 16200)
    assert {key: terms[key] for key in PREVIEW_FIELDS} == STANDARD_ASK


def test_the_draft_equals_the_fixture_budget_of_the_cycle_it_plans(project):
    run_id = project.ready_run(1)
    fixed = fixture("desk-standard.flow-state.json")["budget"]
    assert drafted(project, run_id)["budget"] == fixed


def test_checked_node_with_a_3600_timeout_is_clamped_to_1800(project):
    document = load_template("desk-standard").as_dict()
    slow = [{**node, "timeout_seconds": 3600} if node["node_id"] == "do" else node
            for node in document["nodes"]]
    template = GraphTemplate.from_dict({**document, "nodes": slow, "template_id": "cycle-slow"})
    run_id = project.open_run(1, workflow="cycle-slow", template=template)
    project.publish(run_id, "artifact-brief", "artifact-materials", "instruction-do")
    answer = drafted(project, run_id)
    limits = {row["node_id"]: row["timeout_seconds"] for row in answer["terms"]["node_limits"]}
    assert limits["do"] == 1800
    row = next(row for row in answer["budget"]["steps"] if row["step_id"] == "do")
    assert (row["clamped"], row["timeout_seconds"], row["reserve_seconds"]) == (True, 1800, 3600)


BUNDLED = sorted(path.stem for path in TEMPLATE_DIR.glob("*.json"))
#: The first Dalio cycle predates `result_artifact_ref`: its reviews name no result document, so
#: `bind_inputs` refuses it for a bounded run whatever body the preview is given.
NEVER_BOUND = {"dalio-v1"}


def ready_bundled_run(project, name):
    run_id = project.open_run(1, workflow=name)
    plan = next(row.value for row in project.store.read(run_id).records
                if row.kind == "graph_definition")
    project.publish(run_id, "artifact-brief", "artifact-materials", *sorted({
        node.arguments["instruction_ref"] for node in plan.nodes
        if node.capability == "dispatch"}))
    return run_id


@pytest.mark.parametrize("name", [name for name in BUNDLED if name not in NEVER_BOUND])
def test_every_bundled_template_but_the_first_dalio_cycle_has_a_draft_build_preview_passes(
        project, name):
    answer = drafted(project, ready_bundled_run(project, name))
    assert {key: answer["terms"][key] for key in PREVIEW_FIELDS} == answer["budget"]["terms_draft"]
    assert answer["terms"]["max_actions"] <= 8


def test_the_first_dalio_cycle_is_refused_for_bounded_binding_with_or_without_a_draft(project):
    run_id = ready_bundled_run(project, "dalio-v1")
    body, _ = preview_draft.drafted_preview(project.store.read(run_id).records, LIMITS)
    for asked in (body, {}):
        with pytest.raises(ContractError, match="result_artifact_ref"):
            project.policy.preview(run_id, asked)


def test_a_run_that_follows_no_plan_cannot_be_drafted():
    with pytest.raises(ContractError, match="one frozen graph"):
        preview_draft.drafted_preview([], LIMITS)


def test_the_products_budget_gives_limits_of_eight_actions_of_3600_seconds_and_28800_in_all(
        project):
    assert product_limits(project.policy.budget) == LIMITS


@pytest.mark.parametrize("actions,seconds", [(8, 3600), (3, 100), (1, 1)])
def test_the_limits_take_their_total_from_the_actions_times_the_longest_action(
        actions, seconds):
    assert product_limits(Budget(actions, seconds, 300)) == {
        "max_actions": actions, "max_action_seconds": seconds,
        "max_total_task_seconds": actions * seconds}


# --- the grant that replaces one ------------------------------------------------------------------


def test_empty_preview_of_a_run_with_a_prior_grant_adds_the_spent_actions_seconds_and_attempts(
        project):
    run_id = project.ready_run(1)
    body, budget = replacing_draft(
        project, run_id, ("analyst", "review", 1800), ("do", "dispatch", 1800))
    assert budget == fixture("desk-standard.budget-replacing.json")
    assert body == budget["terms_draft"]


def test_replacing_draft_window_counts_only_the_remaining_work(project):
    run_id = project.ready_run(1)
    first = drafted(project, run_id)["terms"]["duration_seconds"]
    _, budget = replacing_draft(
        project, run_id, ("analyst", "review", 1800), ("do", "dispatch", 1800))
    assert budget["terms_draft"]["duration_seconds"] == first - budget["spent"]["seconds"] == 10800
    assert budget["terms_draft"]["max_total_task_seconds"] == 12600, "the totals span the run"


def test_the_short_cycle_with_both_passes_spent_is_the_exhausted_fixture(project):
    run_id = project.open_run(1, workflow="desk-short")
    project.publish(run_id, "artifact-brief", "artifact-materials", "instruction-do")
    body, budget = replacing_draft(
        project, run_id, ("do", "dispatch", 1800), ("do", "dispatch", 1800), ask=SHORT_ASK)
    assert budget == fixture("desk-short.budget-exhausted.json") and budget["exhausted"] is True
    assert body["max_actions"] == budget["spent"]["actions"] == 2


def test_a_run_with_eight_spent_actions_drafts_terms_that_admit_no_action(project):
    run_id = project.ready_run(1)
    body, budget = replacing_draft(project, run_id, *[("do", "dispatch", 1800)] * 8)
    assert budget["spent"]["actions"] == 8 and budget["exhausted"] is True
    assert body["max_actions"] == 8, "the terms are totals of the run: none is left beyond eight"
    assert {row["node_id"]: row["max_attempts"] for row in body["node_limits"]}["do"] == 8


def test_a_run_with_no_grant_yet_has_no_spent_and_is_not_exhausted(project):
    run_id = project.ready_run(1)
    records = project.store.read(run_id).records
    _, budget = preview_draft.drafted_preview(records, LIMITS)
    assert budget["spent"] is None and budget["exhausted"] is False


# --- through the doors ----------------------------------------------------------------------------


def test_preview_stale_and_slot_busy_are_told_apart_from_contract_invalid(tmp_path):
    f = setup(tmp_path)
    api, path = door(f), "/command/runs/run/automation/authorize"
    preview = f.policy.preview("run", ASK)
    body = {"authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None}
    invalid = post(api, path, {**body, "extra": 1})
    f.policy.previews.discard("session", "run")
    stale = post(api, path, body)
    f.policy.driver = TakenSlot()
    busy = post(api, path, body)
    assert [(row.status, row.payload["error"]["code"]) for row in (invalid, stale, busy)] == [
        (422, "contract_invalid"), (409, "preview_stale"), (409, "slot_busy")]


def test_the_preview_after_a_revoked_grant_is_drafted_with_what_the_run_really_spent(tmp_path):
    f = setup(tmp_path, two_steps=True, checker=True)
    grant = authorize_both_steps(f)
    propose(f)
    f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
    f.policy.control("run", {
        "control_id": "revoke", "authorization_id": grant.authorization_id,
        "authorization_digest": grant.authorization_digest, "action": "revoke", "actor": "owner",
        "expected_control_id": None})
    answer = f.policy.preview("run", {})
    assert answer["budget"]["spent"] == {
        "actions": 1, "seconds": 60, "attempts": [{"step_id": "do", "attempts": 1}]}
    assert answer["budget"]["exhausted"] is False
    assert set(answer) == OLD_KEYS | {"budget"}


def test_an_empty_preview_body_reaches_the_server_through_the_http_door(tmp_path):
    f = setup(tmp_path)
    api = CommandApi(f.store, f.registry, session=CommandSession(PORT, TOKEN),
                     budget=f.policy.budget, clock=f.policy.clock, ids=f.runtime._ids,
                     publish_run=lambda run_id: None)
    api._policy = f.policy
    before = f.store.read("run").records
    answer = post(api, "/command/runs/run/automation/preview", {})
    assert answer.status == 200 and set(answer.payload) == OLD_KEYS | {"budget"}
    assert answer.payload["terms"]["node_limits"] == [
        {"node_id": "do", "timeout_seconds": 30, "max_attempts": 1}]
    assert f.store.read("run").records == before, "a preview writes nothing"
