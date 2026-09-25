"""Independent input-byte oracles and the still-closed bounded request door."""
from dataclasses import replace
import hashlib

import pytest

from conductor.command.artifacts import ArtifactDocument
from conductor.command.authorization_history import journal_prefix_digest
from conductor.command.authorization_terms import (
    InitialInputBinding, InstructionBinding, NodeLimit)
from conductor.command.contracts import ActionProposal, ActionRequest, RunEnvelope, _thaw_json
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_authorization import RunAuthorization
from conductor.command.run_store import CorruptRun, RunStore, StoreError, snapshot_digest
from tests.test_authorization_history import AT, EXPIRES, CONFIG, forged, grant, snapshot, tree


INSTRUCTIONS = "Исправь файл.\n"
BRIEF = "Проверить café и λ.\nВторая строка.\n"
SEED = "Исходные факты.\n"


def digest(text):
    # Independent exact-content oracle: no production content/binding resolver.
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def publish(store, reference, content):
    document = ArtifactDocument(artifact_id=reference + "-one", artifact_ref=reference,
        run_id="run-one", created_at=AT, media_type="text/plain", content=content)
    assert store.append(document)
    return document


def inputs_tree(root, *, producer=False, available=True):
    store = RunStore(root)
    store.create_run(RunEnvelope(run_id="run-one", cycle_id="cycle-one", created_at=AT,
        config_digest=snapshot_digest(CONFIG), mode="policy"), CONFIG)
    nodes = [GraphNode(node_id="approve", kind="gate", title="Approve", gate_id="gate-one")]
    if producer:
        nodes.append(GraphNode(node_id="research", kind="task", title="Research",
            instance_id="checker", capability="review", timeout_seconds=30, attempt_bound=2,
            arguments={"target_artifact_refs": ["seed"], "result_artifact_ref": "brief"}))
    nodes.append(GraphNode(node_id="do", kind="task", title="Do", instance_id="doer",
        capability="dispatch", verifier_instance_id="checker", timeout_seconds=30,
        attempt_bound=2, arguments={"instruction_ref": "instructions", "artifact_refs": ["brief"]}))
    definition = GraphDefinition(graph_id="graph-one", run_id="run-one", created_at=AT,
        nodes=tuple(nodes),
        edges=(GraphEdge(from_node="approve", to_node="do", condition="on_approved"),))
    assert store.append(definition)
    publish(store, "instructions", INSTRUCTIONS)
    if available:
        publish(store, "brief", BRIEF)
    if producer:
        publish(store, "seed", SEED)
    return store, definition


def independently_reviewed(store, definition, *, inputs, producer=False):
    limits = (NodeLimit("research", 30, 2),) if producer else ()
    return RunAuthorization(authorization_id="grant-one", run_id="run-one",
        config_digest=snapshot_digest(CONFIG), graph_digest=definition.digest(),
        provider_config_digest="sha256:" + "1" * 64,
        source_prefix_digest=journal_prefix_digest(store.read("run-one").records),
        authorized_by="Owner", authorized_at=AT, expires_at=EXPIRES, supersedes=None,
        node_limits=limits + (NodeLimit("do", 30, 2),),
        instruction_bindings=(InstructionBinding("do", "instructions-one", digest(INSTRUCTIONS)),),
        initial_input_bindings=inputs, max_actions=8, max_action_seconds=60,
        max_total_task_seconds=480)


def test_exact_unicode_and_lf_input_bytes_append_and_replay_without_resolving_expected(tmp_path):
    store, definition = inputs_tree(tmp_path)
    expected = InitialInputBinding("brief", "brief-one", digest(BRIEF))
    reviewed = independently_reviewed(store, definition, inputs=(expected,))
    assert store.append(reviewed)
    before = snapshot(store)
    fresh = RunStore(tmp_path).read("run-one").records[-1].value
    assert fresh.initial_input_bindings == (expected,)
    assert fresh.instruction_bindings == (
        InstructionBinding("do", "instructions-one", digest(INSTRUCTIONS)),)
    assert snapshot(store) == before


@pytest.mark.parametrize("change", ["artifact_id", "content_digest", "missing"])
def test_wrong_input_binding_refuses_append_and_independently_forged_replay(tmp_path, change):
    store, definition = inputs_tree(tmp_path)
    binding = InitialInputBinding("brief", "brief-one", digest(BRIEF))
    if change == "artifact_id":
        binding = replace(binding, artifact_id="foreign-document")
    elif change == "content_digest":
        binding = replace(binding, content_digest=digest(BRIEF.replace("\n", "\r\n")))
    inputs = () if change == "missing" else (binding,)
    bad = independently_reviewed(store, definition, inputs=inputs)
    before = snapshot(store)
    with pytest.raises(StoreError, match="inputs differ"):
        store.append(bad)
    assert snapshot(store) == before
    forged(store, "run_authorization", bad)
    damaged = snapshot(store)
    with pytest.raises(CorruptRun, match="inputs differ"):
        RunStore(tmp_path).read("run-one")
    assert snapshot(store) == damaged


def test_missing_input_without_a_declared_producer_refuses_both_history_doors(tmp_path):
    store, definition = inputs_tree(tmp_path, available=False)
    bad = independently_reviewed(store, definition, inputs=())
    before = snapshot(store)
    with pytest.raises(StoreError, match="missing and have no authorized producer"):
        store.append(bad)
    assert snapshot(store) == before
    forged(store, "run_authorization", bad)
    damaged = snapshot(store)
    with pytest.raises(CorruptRun, match="missing and have no authorized producer"):
        RunStore(tmp_path).read("run-one")
    assert snapshot(store) == damaged


def test_declared_review_producer_allows_a_future_input_without_inventing_its_bytes(tmp_path):
    store, definition = inputs_tree(tmp_path, producer=True, available=False)
    expected = InitialInputBinding("seed", "seed-one", digest(SEED))
    reviewed = independently_reviewed(store, definition, inputs=(expected,), producer=True)
    assert store.append(reviewed)
    before = snapshot(store)
    records = RunStore(tmp_path).read("run-one").records
    assert records[-1].value.initial_input_bindings == (expected,)
    assert not any(isinstance(row.value, ActionRequest) for row in records)
    assert not any(isinstance(row.value, ArtifactDocument)
                   and row.value.artifact_ref == "brief" for row in records)
    assert snapshot(store) == before


def proposal_and_request(store, definition, mode):
    node = next(node for node in definition.nodes if node.node_id == "do")
    proposal = ActionProposal(proposal_id="proposal-one", run_id="run-one",
        attempt_id="attempt-one", instance_id=node.instance_id, capability=node.capability,
        arguments=_thaw_json(node.arguments), scope=("work/one",), proposed_by="doer", proposed_at=AT,
        timeout_seconds=30, rationale="Reviewed task", node_id="do",
        config_digest=store.read("run-one").envelope.config_digest)
    assert store.append(proposal)
    return ActionRequest(action_id="action-one", run_id="run-one", attempt_id="attempt-one",
        instance_id=node.instance_id, capability=node.capability, arguments=_thaw_json(node.arguments),
        scope=proposal.scope, requested_by="owner", requested_at=AT,
        idempotency_key="dispatch-proposal-one", timeout_seconds=30,
        preview_digest=proposal.preview_digest, mode=mode, node_id="do")


@pytest.mark.parametrize("mode,marked,standing_grant", [
    ("policy", True, False), ("policy", True, True),
    ("policy", False, False), ("confirm", False, False), ("confirm", True, False),
])
def test_marked_policy_refuses_an_unlinked_request_even_with_a_durable_grant(
        tmp_path, mode, marked, standing_grant):
    config = dict(CONFIG)
    if not marked:
        config.pop("automation_contract")
    store, definition = tree(tmp_path, mode=mode, config=config)
    request = proposal_and_request(store, definition, mode)
    if standing_grant:
        assert store.append(grant(store, definition))
    records = RunStore(tmp_path).read("run-one").records
    assert not any(isinstance(row.value, ActionRequest) for row in records)
    before = snapshot(store)
    if mode == "policy" and marked:
        with pytest.raises(StoreError, match="bounded request requires its explicit authorization reference"):
            store.append(request)
        assert snapshot(store) == before
        forged(store, "action_request", request)
        damaged = snapshot(store)
        with pytest.raises(CorruptRun, match="bounded request requires its explicit authorization reference"):
            RunStore(tmp_path).read("run-one")
        assert snapshot(store) == damaged
    else:
        assert store.append(request)
        accepted = snapshot(store)
        fresh = RunStore(tmp_path).read("run-one").records
        assert fresh[-1].value == request
        assert not any(row.kind == "attempt_event" for row in fresh)
        assert snapshot(store) == accepted
