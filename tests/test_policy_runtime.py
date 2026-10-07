"""Bounded authority reaches the real runtime without fabricated confirmations."""
from dataclasses import replace
from itertools import count
from types import SimpleNamespace
import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import ActionRequest, DecisionReceipt, RunEnvelope, ContractError, ABSENT
from conductor.command.graph_definition import GraphDefinition, GraphNode, GraphEdge
from conductor.command.policy_preview import build_preview
from conductor.command.policy_service import PolicyService
from conductor.command.run_authorization import RunAuthorizationControl
from conductor.command.run_store import RunStore, snapshot_digest, StoreError
from conductor.command.runtime import ControlRuntime, Budget
from conductor.command.service import CommandService
from tests.test_command_runtime_execute import ScriptedAdapter


NOW = "2026-08-11T12:00:00Z"
PD = "sha256:" + "a" * 64
ARGS = {"work_item_id": "item", "instruction_ref": "instructions", "profile": "implement",
        "artifact_refs": [], "output_limit_profile": "small"}
ASK = {"node_limits": [{"node_id": "do", "timeout_seconds": 30, "max_attempts": 2}],
       "max_actions": 2, "max_action_seconds": 30, "max_total_task_seconds": 60,
       "duration_seconds": 300}


class DeepScripted(ScriptedAdapter):
    argument_schemas = {"dispatch": "deep-arguments-v1"}


class Activation:
    def __init__(self):
        self.active = None
        self.calls = 0

    def hold_activation(self, run_id):
        pass

    def activate(self, run_id, grant_id):
        self.calls += 1
        self.active = (run_id, grant_id)

    def is_active(self, run_id, grant_id):
        return self.active == (run_id, grant_id)

    def deactivate(self, run_id):
        self.active = None


def setup(root, *, two_steps=False, checker=False):
    config = {"cycle": {"id": "cycle"}, "instances": [{"id": "doer", "adapter": "claude-code"}],
              "workflow": {"id": "custom", "revision": 1}, "automation_contract": "bounded-run-v1"}
    if checker:
        config["instances"].append({"id": "checker", "adapter": "codex-cli"})
    store = RunStore(root)
    store.create_run(RunEnvelope("run", "cycle", NOW, snapshot_digest(config), mode="policy"), config)
    nodes = [GraphNode("gate", "gate", "Approve", gate_id="gate-id")]
    edges = []
    for index, node_id in enumerate(("do", "next") if two_steps else ("do",)):
        nodes.append(GraphNode(node_id, "task", node_id, instance_id="doer", capability="dispatch",
            arguments=ARGS, timeout_seconds=30, attempt_bound=2,
            verifier_instance_id="checker" if checker else None))
        edges.append(GraphEdge("gate" if index == 0 else "do", node_id,
                               condition="on_approved" if index == 0 else "on_succeeded"))
    graph = GraphDefinition("graph", "run", NOW, nodes=tuple(nodes), edges=tuple(edges),
        execution_contract="bounded-run-v1" if two_steps else ABSENT)
    store.append(graph)
    store.append(ArtifactDocument(artifact_id="instruction-1", run_id="run", artifact_ref="instructions", created_at=NOW, media_type="text/plain", content="Keep my task.\n"))
    store.append(DecisionReceipt("decision", "run", "gate-id", "approve", "owner", NOW,
                                "Reviewed", ("gate-id",), snapshot_digest(config)))
    if checker:
        from tests.test_policy_driver import Signing
        adapter, verifier = Signing(store), Signing(store, adapter_id="codex-cli")
        registry = AdapterRegistry([adapter, verifier])
    else:
        adapter = DeepScripted(execute_outcome="failed")
        verifier = None
        registry = AdapterRegistry([adapter])
    ticks, seq = [NOW], count()
    clock, ids = lambda: ticks[0], lambda kind: f"{kind}-{next(seq)}"
    budget = Budget(8, 3600, 300)
    policy = PolicyService(store, registry, budget=budget, clock=clock,
        provider_digest=lambda config: PD, owner_check=lambda: None, session="session", notify=lambda run: None)
    policy.driver = Activation()
    runtime = ControlRuntime(store, registry, clock=clock, ids=ids)
    runtime._policy = policy
    return SimpleNamespace(store=store, graph=graph, adapter=adapter, registry=registry, ticks=ticks,
        policy=policy, runtime=runtime, verifier=verifier, service=CommandService(store, registry, clock=clock, ids=ids))


def approve(f):
    preview = f.policy.preview("run", ASK)
    body = {"authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None}
    grant, created = f.policy.authorize("run", body)
    assert created
    return grant, body


def propose(f):
    return f.service.propose(run_id="run", attempt_id="attempt", instance_id="doer", capability="dispatch",
        arguments=ARGS, scope=("work/item",), proposed_by="run-driver", rationale="Approved work",
        timeout_seconds=30, node_id="do", proposal_id="proposal")


def pause(f, grant):
    f.policy.control("run", {"control_id": "pause", "authorization_id": grant.authorization_id,
        "authorization_digest": grant.authorization_digest, "action": "pause", "actor": "owner",
        "expected_control_id": None})


def test_preview_is_read_only_and_exact_retry_does_not_reactivate(tmp_path):
    f = setup(tmp_path)
    before = f.store.read("run").records
    f.policy.preview("run", ASK)
    assert f.store.read("run").records == before and f.adapter.prepare_calls == 0
    grant, body = approve(f)
    f.ticks[0] = "2026-08-11T13:00:00Z"
    f.policy.owner_check = lambda: (_ for _ in ()).throw(AssertionError("retry asked for live owner"))
    assert f.policy.authorize("run", body) == (grant, False)
    assert f.policy.driver.calls == 1


def test_changed_source_invalidates_preview_before_grant(tmp_path):
    f = setup(tmp_path)
    preview = f.policy.preview("run", ASK)
    f.store.append(ArtifactDocument(artifact_id="instruction-2", run_id="run", artifact_ref="instructions", created_at=NOW, media_type="text/plain", content="Changed"))
    before = f.store.read("run").records
    with pytest.raises(ContractError, match="changed"):
        f.policy.authorize("run", {"authorization_id": "grant", "preview_digest": preview["preview_digest"],
            "authorized_by": "owner", "terms": preview["terms"], "supersedes": None})
    assert f.store.read("run").records == before and f.adapter.prepare_calls == 0


def test_real_policy_request_executes_once_and_retry_never_spends_again(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    propose(f)
    authority = f.runtime.authorize_policy("run", "proposal", grant.authorization_id)
    request = authority.request
    assert request.requested_by == "run-policy" and request.run_authorization_digest == grant.authorization_digest
    result = f.runtime.execute(authority)
    assert result.receipt.outcome == "failed" and f.adapter.execute_calls == 1
    retry = f.runtime.authorize_policy("run", "proposal", grant.authorization_id)
    assert not retry.record_created and retry.request == request
    assert f.runtime.execute(retry).receipt == result.receipt and f.adapter.execute_calls == 1
    assert sum(row.kind == "action_request" for row in f.store.read("run").records) == 1


@pytest.mark.parametrize("when", ["queued", "prepared", "expired"])
def test_pause_or_expiry_before_lease_cancels_without_execute(tmp_path, when):
    f = setup(tmp_path)
    grant, _ = approve(f)
    propose(f)
    authority = f.runtime.authorize_policy("run", "proposal", grant.authorization_id)
    if when == "queued":
        pause(f, grant)
    elif when == "expired":
        f.ticks[0] = "2026-08-11T12:05:00Z"
    else:
        original = f.adapter.prepare
        def prepared(request):
            value = original(request)
            pause(f, grant)
            return value
        f.adapter.prepare = prepared
    result = f.runtime.execute(authority)
    assert result.receipt.outcome == "cancelled" and f.adapter.execute_calls == 0
    assert f.adapter.prepare_calls == (1 if when == "prepared" else 0)
    assert not any(row.kind == "attempt_event" for row in f.store.read("run").records)


def test_foreign_reference_and_missing_reference_refuse_on_direct_append(tmp_path):
    f = setup(tmp_path)
    grant, _ = approve(f)
    proposal = propose(f)
    from conductor.command.policy_runtime import mint_request
    request = mint_request(proposal, grant, action_id="action", at=NOW)
    before = f.store.read("run").records
    with pytest.raises(StoreError, match="another authorization"):
        f.store.append(replace(request, run_authorization_id="foreign"))
    assert f.store.read("run").records == before
    assert f.store.append(request)
    assert not f.store.append(request)
