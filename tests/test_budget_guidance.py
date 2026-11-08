"""Task-aware recommendations go through the existing bounded preview and owner gate."""
import json

import pytest

from conductor.command.contract_values import ContractError, _content_digest
from conductor.command.policy_preview import PREVIEW_FIELDS
from tests.test_preview_draft import project
from tests.test_task_preparation import STANDARD_ASK


def ask(depth):
    return {"recommendation": {"depth": depth}}


def test_recognizes_plan_scope_checker_and_depth_without_issuing_a_grant(project):
    run = project.ready_run(1)
    before = project.store.read(run).records
    default = project.policy.preview(run, {})
    quick, thorough = (project.policy.preview(run, ask(choice)) for choice in ("quick", "thorough"))
    assert "recommendation" not in default
    assert quick["recommendation"]["step_count"] == 2
    assert quick["recommendation"]["checker_steps"] == 1
    assert quick["recommendation"]["input_bytes"] > 0
    assert quick["recommendation"]["history_samples"] == 0
    assert quick["recommendation"]["status"] == "preliminary"
    assert quick["terms"]["max_total_task_seconds"] < thorough["terms"]["max_total_task_seconds"]
    assert thorough["terms"]["max_total_task_seconds"] <= default["terms"]["max_total_task_seconds"]
    for reply in (quick, thorough):
        assert reply["preview_digest"] == _content_digest(reply["terms"])
        assert reply["budget"]["terms_draft"] == {k: reply["terms"][k] for k in PREVIEW_FIELDS}
        assert reply["budget"]["steps"][-1]["reserve_seconds"] == (
            reply["terms"]["node_limits"][-1]["timeout_seconds"] * 2)
        assert reply["terms"]["max_actions"] == default["terms"]["max_actions"]
    assert project.store.read(run).records == before
    assert json.dumps(quick["recommendation"]).find("artifact-brief") == -1


def test_recommendation_never_changes_an_existing_authorization(project):
    run = project.ready_run(1)
    first = project.policy.preview(run, ask("balanced"))
    project.grant(run, STANDARD_ASK)
    before = project.store.read(run).records
    with pytest.raises(ContractError, match="before the first authorization"):
        project.policy.preview(run, ask("thorough"))
    assert first["terms"]["max_actions"] > 0 and project.store.read(run).records == before


def test_new_published_materials_raise_the_suggested_room_but_not_the_plan_ceiling(project):
    from conductor.command.artifacts import ArtifactDocument
    from tests.test_preview_draft import NOW

    run = project.ready_run(1)
    small = project.policy.preview(run, ask("balanced"))
    project.store.append(ArtifactDocument(artifact_id="updated-materials", run_id=run,
        artifact_ref="artifact-materials", created_at=NOW, media_type="text/plain",
        content="данные для учебной проверки\n" * 600))
    large = project.policy.preview(run, ask("balanced"))
    ceiling = project.policy.preview(run, {})
    assert small["recommendation"]["input_bytes"] < large["recommendation"]["input_bytes"]
    assert small["budget"]["clean"]["seconds"] < large["budget"]["clean"]["seconds"]
    assert large["budget"]["worst"]["seconds"] <= ceiling["budget"]["worst"]["seconds"]
    assert small["terms"]["graph_digest"] == large["terms"]["graph_digest"]
    assert "учебной проверки" not in json.dumps(large["recommendation"], ensure_ascii=False)


@pytest.mark.parametrize("body", [
    {"recommendation": {}}, {"recommendation": {"depth": "max"}},
    {"recommendation": {"depth": "quick", "seconds": 1}},
    {"recommendation": {"depth": "quick"}, "max_actions": 20},
])
def test_guidance_accepts_only_its_named_user_choice(project, body):
    run = project.ready_run(1)
    before = project.store.read(run).records
    with pytest.raises(ContractError):
        project.policy.preview(run, body)
    assert project.store.read(run).records == before


def test_only_a_successful_matched_lease_and_receipt_contribute_a_timing(project):
    from dataclasses import replace
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    from conductor.command.attempts import AttemptEvent, action_request_digest
    from conductor.command.budget_guidance import _observations
    from conductor.command.contracts import ActionResultReceipt
    from tests.test_preview_draft import NOW, PD, spending

    run = project.ready_run(1)
    grant = project.grant(run, STANDARD_ASK)
    records = project.store.read(run).records
    graph = next(row.value for row in records if row.kind == "graph_definition")
    request_row, = spending(run, grant, ("analyst", "review", 1800))
    req = request_row.value
    ended = (datetime.fromisoformat(NOW) + timedelta(seconds=457)).isoformat()
    start = AttemptEvent("evt-start", run, req.action_id, req.attempt_id, req.instance_id,
                         "claude-code", "effect_lease", NOW, action_request_digest(req),
                         "recovery", None, None, 2)
    finish = replace(start, event_id="evt-finish", phase="execution_observed", recorded_at=ended,
                     outcome="succeeded", exit_code=0)
    receipt = ActionResultReceipt("receipt", req.action_id, run, req.attempt_id,
                                  req.instance_id, "succeeded", ended)

    def timings(events, digest=PD):
        rows = (*records, request_row, *(SimpleNamespace(kind="observation", value=e)
                                         for e in events))
        return list(_observations(rows, graph, digest))

    assert timings([start, finish, receipt]) == [("analyst", 457)]
    assert timings([start, finish, receipt], "different-install") == []
    assert timings([start, replace(finish, outcome="failed", exit_code=1), receipt]) == []
    assert timings([start, finish, replace(receipt, outcome="failed", detail="timeout")]) == []
    assert timings([start, finish]) == []


def test_only_earlier_runs_with_the_same_task_assignment_and_initial_inputs_are_read(project):
    from conductor.command.artifacts import ArtifactDocument
    from conductor.command.budget_guidance import _matching_runs
    from tests.test_preview_draft import NOW

    first = project.ready_run(1)
    second = project.ready_run(2)
    third = project.ready_run(3)
    project.store.append(ArtifactDocument(artifact_id="changed-brief", run_id=second,
        artifact_ref="artifact-brief", created_at=NOW, media_type="text/plain",
        content="other task"))
    matches = _matching_runs(project.store, project.store.read(third))
    assert [run.envelope.run_id for run in matches] == [first]


def test_two_comparable_observations_can_raise_an_unchecked_steps_reserve(project, monkeypatch):
    from conductor.command import budget_guidance

    monkeypatch.setattr(budget_guidance, "_observations", lambda rows, graph, digest: [
        ("analyst", 780)])
    project.ready_run(1)
    second = project.ready_run(2)
    one = project.policy.preview(second, ask("balanced"))
    third = project.ready_run(3)
    before = project.store.read(third).records
    two = project.policy.preview(third, ask("balanced"))
    assert one["recommendation"]["history_samples"] == 1
    assert one["terms"]["node_limits"][0]["timeout_seconds"] < 780
    assert two["terms"]["node_limits"][0]["timeout_seconds"] == 1170
    assert two["recommendation"]["history"] == [
        {"step_id": "analyst", "samples": 2, "min_seconds": 780, "max_seconds": 780}]
    assert project.store.read(third).records == before
