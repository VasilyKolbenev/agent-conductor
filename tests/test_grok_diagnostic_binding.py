"""The diagnostic is a frozen review argument, visible in the grant for its own step."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.base import AdapterContractError, PreparedAction
from conductor.command.adapters.deep_commands import DeepReviewArgs
from conductor.command.adapters.deep_contracts import DeepContractError
from conductor.command.adapters.grok_build import GrokBuildError
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import RunEnvelope
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.policy_service import PolicyService
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import Budget
from conductor.command.workflow_flow import compile_flow, import_template
from conductor.command.workflow_draft import parse_document
from tests.test_command_grok_transport import a_request
from tests.test_command_runtime_execute import ScriptedAdapter
from tests.test_grok_activation import _site
from tests.test_grok_compat_isolation import _harness
from tests.test_policy_runtime import Activation, NOW, PD


ARGS = {"work_item_id": "work-001", "review_profile": "quality",
        "target_artifact_refs": ["input"], "result_artifact_ref": "answer"}
MODE = {"grok_diagnostic": "session-phase-v1"}


@pytest.mark.parametrize("other", [None, True, False, "json", "streaming-messages-json", {}])
def test_only_the_closed_versioned_mode_is_admitted(other):
    with pytest.raises(DeepContractError):
        DeepReviewArgs.from_dict({**ARGS, "grok_diagnostic": other})
    assert DeepReviewArgs.from_dict(ARGS).as_dict() == ARGS


def test_api_key_registry_refuses_before_work_or_provider_spawn(tmp_path):
    adapter, log, _authority = _harness(tmp_path)
    registry = AdapterRegistry([adapter])
    registry.validate_arguments("grok-build", "review", ARGS)
    with pytest.raises(AdapterContractError, match="Grok subscription"):
        registry.validate_arguments("grok-build", "review", {**ARGS, **MODE})
    with pytest.raises(GrokBuildError, match="authorized request and provider"):
        adapter.prepare(a_request(capability="review", arguments={**ARGS, **MODE}))
    assert not log.exists()


def test_unrelated_provider_cannot_opt_in():
    other = ScriptedAdapter(capabilities=("review",))
    registry = AdapterRegistry([other])
    with pytest.raises(AdapterContractError, match="Grok subscription"):
        registry.validate_arguments("claude-code", "review", {**ARGS, **MODE})
    assert (other.prepare_calls, other.execute_calls) == (0, 0)


@pytest.mark.parametrize("inject", [True, False])
def test_prepared_payload_cannot_add_or_remove_the_authorized_mode(tmp_path, inject):
    adapter, _root, log, _login, _bytes, _runner = _site(
        tmp_path, "subscription", "enabled-fixed-review")
    marked = {**ARGS, **MODE}
    request = a_request(capability="review", arguments=ARGS if inject else marked)
    forged = PreparedAction("grok-build", request, marked if inject else ARGS)
    with pytest.raises(GrokBuildError, match="authorized request and provider"):
        adapter.execute(forged)
    assert not log.exists()


def test_g6_diagnostic_document_survives_studio_round_trip():
    tasks = Path(__file__).resolve().parents[1] / "docs/recovery/2026-10-20/tasks"
    document = json.loads((tasks / "grok-g6-session-diagnostic.json").read_text(encoding="utf-8"))
    assert compile_flow(import_template(document)) == parse_document(document)
    diagnose, gate = document["nodes"]
    assert (diagnose["node_id"], diagnose["capability"]) == ("diagnose", "review")
    assert gate["kind"] == "gate"
    args = DeepReviewArgs.from_dict(diagnose["arguments"])
    assert args.grok_diagnostic == MODE["grok_diagnostic"]
    assert args.result_artifact_ref == "artifact-causes"


@pytest.mark.parametrize("marked", [False, True])
def test_owner_sees_only_selected_node_and_grant_binds_it(tmp_path, marked):
    adapter, _root, log, _login, _bytes, _runner = _site(
        tmp_path, "subscription", "enabled-fixed-review")
    registry = AdapterRegistry([adapter])
    config = {"cycle": {"id": "cycle"}, "instances": [{"id": "reviewer", "adapter": "grok-build"}],
              "workflow": {"id": "custom", "revision": 1}, "automation_contract": "bounded-run-v1"}
    store = RunStore(tmp_path / "journal")
    envelope = RunEnvelope("run", "cycle", NOW, snapshot_digest(config), mode="policy")
    store.create_run(envelope, config)
    first = GraphNode("a", "task", "First", instance_id="reviewer", capability="review",
                      arguments=ARGS, timeout_seconds=30, attempt_bound=1)
    plain = replace(first, node_id="b", title="Second",
                    arguments={**ARGS, "result_artifact_ref": "out"})
    selected = replace(plain, arguments={**dict(plain.arguments), **MODE}) if marked else plain
    graph = GraphDefinition("graph", "run", NOW, nodes=(first, selected),
                            edges=(GraphEdge("a", "b", condition="on_succeeded"),))
    store.append(graph)
    store.append(ArtifactDocument(artifact_id="seed", run_id="run", artifact_ref="input",
                                  created_at=NOW, media_type="text/plain", content="local input"))
    policy = PolicyService(store, registry, budget=Budget(8, 3600, 300), clock=lambda: NOW,
        provider_digest=lambda _config: PD,
        owner_check=lambda: None, session="session", notify=lambda run: None)
    policy.driver = Activation()
    preview = policy.preview("run", {})
    if marked:
        assert preview["grok_diagnostic_steps"] == ["b"]
        assert graph.digest() != replace(graph, nodes=(first, plain)).digest()
    else:
        assert "grok_diagnostic_steps" not in preview
    grant, created = policy.authorize("run", {
        "authorization_id": "grant", "authorized_by": "owner", "supersedes": None,
        "preview_digest": preview["preview_digest"], "terms": preview["terms"]})
    assert created and grant.graph_digest == graph.digest()
    assert not log.exists()
