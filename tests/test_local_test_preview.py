"""The reviewed preview discloses the exact initial test policy, without execution."""
import json
from types import SimpleNamespace

import pytest

from conductor.command.contract_values import ContractError
from conductor.command.policy_preview import build_preview
from tests.test_local_test_plan import policy
from tests.test_patch_do_sources import doc
from tests.test_policy_runtime import ASK, PD, setup
from tests.test_studio_automation import js, wire


def test_preview_exposes_only_bound_initial_policy(tmp_path):
    from conductor.command.local_test_preview import test_steps
    plan = policy(tmp_path)
    instruction = doc("brief", "Do.\n\nconduct.test-plan.v1\n" + json.dumps(plan))
    nodes = [SimpleNamespace(node_id="do", capability="dispatch", arguments={
        "profile": "implement-patch-v1"})]
    binding = SimpleNamespace(node_id="do", artifact_id=instruction.artifact_id)
    rows = test_steps(nodes, [instruction], [binding], ASK["node_limits"])
    assert len(rows) == 1 and rows[0]["node_id"] == "do"
    assert rows[0]["policy"] == plan
    assert rows[0]["policy_digest"].startswith("sha256:")
    assert rows[0]["toolpin_digest"].startswith("sha256:")
    with pytest.raises(ContractError):
        test_steps(nodes, [instruction], [binding], [{"node_id": "other", "timeout_seconds": 1}])


def test_server_preview_refuses_test_policy_on_a_nonpatch_road(tmp_path):
    from conductor.command.artifacts import ArtifactDocument
    f = setup(tmp_path)
    f.store.append(ArtifactDocument(artifact_id="new", run_id="run", artifact_ref="instructions",
        created_at="2026-08-11T12:00:01Z", media_type="text/plain",
        content="Do.\n\nconduct.test-plan.v1\n" + json.dumps(policy(tmp_path))))
    with pytest.raises(ContractError, match="test policy"):
        build_preview(f.store.read("run"), ASK, budget=f.policy.budget,
            provider_digest=lambda config: PD, registry=f.registry, clock=f.policy.clock)


def test_studio_admits_exact_policy_and_refuses_missing_or_foreign_rows(tmp_path):
    payload = wire(tmp_path)
    payload["testPlan"] = policy(tmp_path)
    result = js("""
      const detail = p.read, packet = p.preview;
      const node = detail.graph.definition.nodes.find(n => n.capability);
      node.arguments.profile = "implement-patch-v1";
      const bound = packet.terms.instruction_bindings[0];
      const document = detail.records.find(r => r.record_type === "artifact"
        && r.record.artifact_id === bound.artifact_id).record;
      document.content = "Do.\\n\\nconduct.test-plan.v1\\n" + JSON.stringify(p.testPlan);
      const row = {node_id: node.node_id, policy: p.testPlan,
        policy_digest: packet.preview_digest, toolpin_digest: packet.preview_digest};
      const reviewed = {...packet, patch_steps: [node.node_id], test_steps: [row]};
      const admitted = value => Boolean(model.projectAutomationPreview(value, detail));
      console.log(JSON.stringify([admitted(reviewed), admitted({...reviewed, test_steps: []}),
        admitted({...reviewed, test_steps: [{...row, node_id: "other"}]}),
        admitted({...reviewed, test_steps: [
          {...row, policy: {...row.policy, pattern: "other"}}]})]));
    """, payload)
    assert result == [True, False, False, False]
