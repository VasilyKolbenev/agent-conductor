"""One grant, real native defect, typed rejection, correction and separate check."""
import json
import hashlib
from dataclasses import replace
from itertools import count
from types import SimpleNamespace
import time
import pytest

from conductor import ownership
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.codex_cli import CODEX_PROVIDER_ID, CODEX_PROTOCOL
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contracts import DecisionReceipt, RunEnvelope, _thaw_json
from conductor.command.graph_definition import GraphDefinition, GraphNode, GraphEdge
from conductor.command.policy_service import PolicyService
from conductor.command.providers import resolve_providers
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import ControlRuntime, Budget
from conductor.command.service import CommandService
from tests import _fakeexe, _fakecodex, _fakepolicy
from tests.test_policy_driver import attach_driver, authorize
from tests.test_policy_runtime import NOW, PD, ARGS, Activation, propose
from tests.test_project_ownership import activated


def native_registry(root, tmp_path, **knobs):
    executable = _fakeexe.build(tmp_path / "bin", "policy", "_fakepolicy")
    assert executable is not None, "this native witness must run, not silently skip"
    log = tmp_path / "spawns.log"
    environment = {_fakecodex.SPAWN_LOG: str(log), **knobs}
    config = ProviderConfig(provider_id=CODEX_PROVIDER_ID, protocol=CODEX_PROTOCOL,
        executable=str(executable), env_allow=tuple(environment))
    seq = count()
    ids = lambda kind: f"{kind}-{next(seq)}"
    resolution = resolve_providers([config], root=root, clock=lambda: NOW, ids=ids,
                                   environ=environment)
    return resolution.registry, ids, log


def run_state(root, registry, ids, plan=None):
    store = RunStore(root)
    config = {"cycle": {"id": "cycle"}, "instances": [
        {"id": role, "adapter": CODEX_PROVIDER_ID} for role in ("doer", "checker")],
        "workflow": {"id": "custom", "revision": 1}, "automation_contract": "bounded-run-v1"}
    digest = snapshot_digest(config)
    store.create_run(RunEnvelope("run", "cycle", NOW, digest, mode="policy"), config)
    args = ARGS if plan is None else {**ARGS, "artifact_refs": ["artifact-plan"]}
    nodes = (GraphNode("gate", "gate", "Approve", gate_id="gate-id"), *(
        GraphNode(node, "task", node, instance_id="doer", capability="dispatch", arguments=args,
            timeout_seconds=30, attempt_bound=2, verifier_instance_id="checker") for node in ("do", "next")))
    store.append(GraphDefinition("graph", "run", NOW, nodes=nodes, edges=(
        GraphEdge("gate", "do", condition="on_approved"), GraphEdge("do", "next", condition="on_failed")),
        execution_contract="bounded-run-v1"))
    store.append(ArtifactDocument("instruction-1", "instructions", "run", NOW,
        "text/plain", _fakepolicy.INSTRUCTION))
    if plan is not None:
        store.append(ArtifactDocument("plan-1", "artifact-plan", "run", NOW, "text/markdown", plan))
    store.append(DecisionReceipt("decision", "run", "gate-id", "approve", "owner", NOW,
        "Reviewed", ("gate-id",), digest))
    policy = PolicyService(store, registry, budget=Budget(8, 3600, 300), clock=lambda: NOW,
        provider_digest=lambda _: PD, owner_check=lambda: ownership.require_owner(root),
        session="native-session", notify=lambda run: None)
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=ids)
    runtime._policy = policy
    return SimpleNamespace(store=store, policy=policy, runtime=runtime)


def terminal(f):
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        read = f.store.read("run")
        if any(row.kind == "run_terminal" for row in read.records):
            return read
        time.sleep(.02)
    raise AssertionError(f"native driver stalled: {f.policy.driver.reason('run')}")


def assert_rejection_material(feedback, request):
    expected = {"action_id": request.action_id, "attempt_id": request.attempt_id,
        "input_artifact_ids": ["instruction-1"], "files": [{"path": "item/answer.py",
            "state": "present", "length": len(_fakepolicy.BAD),
            "sha256": "sha256:" + hashlib.sha256(_fakepolicy.BAD).hexdigest()}]}
    assert _thaw_json(feedback.result_manifest) == expected
    canonical = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    assert feedback.result_manifest_digest == "sha256:" + hashlib.sha256(canonical).hexdigest()
    assert feedback.source_action_id == request.action_id
    assert feedback.source_attempt_id == request.attempt_id


def test_native_children_correct_only_the_exact_bound_task_after_typed_rejection(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    registry, ids, log = native_registry(root, tmp_path)
    with ownership.acquire_owner(root):
        f = run_state(root, registry, ids)
        driver, execution = attach_driver(f)
        try:
            authorize(f)
            settled = terminal(f)
        finally:
            driver.stop()
            execution.shutdown()
    results = [row.value for row in settled.records if row.kind == "action_result"]
    assert [row.outcome for row in results] == ["verification_failed", "succeeded"]
    requests = [row.value for row in settled.records if row.kind == "action_request"]
    assert len(requests) == 2 and requests[0].arguments == requests[1].arguments
    assert _thaw_json(requests[0].arguments) == ARGS
    assert requests[0].instance_id == requests[1].instance_id == "doer"
    assert {row.run_authorization_id for row in requests} == {"grant"}
    feedback = [row.value for row in settled.records if row.kind == "correction_feedback"]
    assert len(feedback) == 1 and feedback[0].as_dict()["payload"] == _fakepolicy.PAYLOAD
    assert feedback[0].checker_instance_id == "checker"
    assert_rejection_material(feedback[0], requests[0])
    assert sum(row.kind == "run_authorization" for row in settled.records) == 1
    assert (root / "work/item/answer.py").read_bytes() == _fakepolicy.GOOD
    semantic = [json.loads(line) for line in log.with_suffix(".semantic.jsonl").read_text().splitlines()]
    assert semantic == [
        {"role": "doer", "correction_received": False, "instruction_preserved": True, "written": 2},
        {"role": "checker", "manifest_matches": True, "accepted": False},
        {"role": "doer", "correction_received": True, "instruction_preserved": True, "written": 1},
        {"role": "checker", "manifest_matches": True, "accepted": True}]
    assert len(_fakecodex.task_spawns(log)) == 4
    evidence = [row.value for row in settled.records if row.kind == "evidence"]
    assert len(evidence) == 1 and evidence[0].verifier_instance_id == "checker"


@pytest.mark.parametrize("tamper", ["absent", "wrong_length"])
def test_missing_or_tampered_manifest_refuses_before_native_checker_spawn(tmp_path, monkeypatch, tamper):
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    registry, ids, log = native_registry(root, tmp_path)
    adapter = registry.resolve(CODEX_PROVIDER_ID)
    original = adapter.publish

    def publish(request, result):
        material = original(request, result)
        assert material.refusal is None and material.result_manifest is not None
        manifest = _thaw_json(material.result_manifest)
        manifest["files"][0]["length"] += 1
        return replace(material, result_manifest=None if tamper == "absent" else manifest)

    monkeypatch.setattr(adapter, "publish", publish)
    with ownership.acquire_owner(root):
        f = run_state(root, AdapterRegistry([adapter]), ids)
        f.policy.driver = Activation()
        f.service = CommandService(f.store, f.runtime._registry, clock=lambda: NOW, ids=ids)
        grant = authorize(f)
        propose(f)
        result = f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
        assert result.receipt.outcome == "verification_failed"
        assert not adapter.verification_started(result.request)
        assert not any(row.kind in {"evidence", "correction_feedback"} for row in f.store.read("run").records)
    assert len(_fakecodex.task_spawns(log)) == 1
    rows = [json.loads(line) for line in log.with_suffix(".semantic.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["role"] == "doer"


def test_a_changed_file_past_the_read_budget_is_named_and_never_reaches_a_checker(tmp_path):
    """MEASURED live (live-v5-8): a 19,538-byte test file was reported as an uncontained work tree."""
    from conductor.command import verify_holds as words
    from conductor.command.adapters.harness_workspace import FILE_BUDGET
    root = tmp_path / "root"
    root.mkdir()
    activated(root)
    pad = FILE_BUDGET + 1 - len(_fakepolicy.BAD)  # the answer is exactly one byte past the budget
    registry, ids, log = native_registry(root, tmp_path, **{_fakepolicy.PAD: str(pad)})
    with ownership.acquire_owner(root):
        f = run_state(root, registry, ids)
        f.policy.driver = Activation()
        f.service = CommandService(f.store, f.runtime._registry, clock=lambda: NOW, ids=ids)
        grant = authorize(f)
        propose(f)
        result = f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
    assert result.receipt.outcome == "verification_failed"
    assert result.receipt.detail == words.DOER_OVER_READ_BUDGET
    assert len(_fakecodex.task_spawns(log)) == 1
