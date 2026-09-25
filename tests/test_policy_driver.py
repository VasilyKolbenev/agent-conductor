"""One human grant drives two ordered steps through the independent-check road."""
from threading import Event
import time

from conductor.command.adapters import AdapterVerification
from conductor.command.contracts import EvidenceRef
from conductor.command.coordinator import ExecutionCoordinator
from conductor.command.policy_driver import PolicyDriver
from conductor.command.policy_service import PolicyService
from conductor.command.runtime import ControlRuntime
from tests.test_command_plan_verifier import _Signing
from tests.test_policy_runtime import ASK, NOW, PD, setup


class Signing(_Signing):
    argument_schemas = {"dispatch": "deep-arguments-v1"}

    def _sign(self, request, verifier_instance_id=None):
        adapter_id = self.manifest.adapter_id
        evidence_id = f"evidence-{request.action_id}-{adapter_id}"
        self._store.append(EvidenceRef(evidence_id=evidence_id, run_id=request.run_id,
            kind="verification", uri=f"verification/{request.action_id}", label="Checked result",
            created_by=adapter_id, observed_at=NOW, verification="verified", verified_by=adapter_id,
            verified_at=NOW, verifier_instance_id=verifier_instance_id))
        return AdapterVerification(adapter_id=adapter_id, action_id=request.action_id,
            state="verified", observed_at=NOW, detail="", evidence_refs=(evidence_id,))


def ask():
    return {**ASK, "node_limits": [{"node_id": node, "timeout_seconds": 30, "max_attempts": 2}
                                  for node in ("do", "next")],
            "max_action_seconds": 60, "max_total_task_seconds": 120}


def authorize(f):
    preview = f.policy.preview("run", ask())
    return f.policy.authorize("run", {"authorization_id": "grant",
        "preview_digest": preview["preview_digest"], "authorized_by": "owner",
        "terms": preview["terms"], "supersedes": None})[0]


def attach_driver(f):
    execution = ExecutionCoordinator(f.runtime, capacity=1)
    execution.start()
    driver = PolicyDriver(f.policy, f.runtime, execution, clock=f.policy.clock, ids=f.runtime._ids)
    f.policy.driver = driver
    f.runtime._notify = driver.wake
    driver.start()
    return driver, execution


def wait_terminal(f):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        recovered = f.store.read("run")
        if any(row.kind == "run_terminal" for row in recovered.records):
            return recovered
        Event().wait(.02)
    raise AssertionError(f"driver stalled: {f.policy.driver.reason('run')}")


def assert_two_steps(f, recovered):
    requests = [row.value for row in recovered.records if row.kind == "action_request"]
    results = [row.value for row in recovered.records if row.kind == "action_result"]
    assert [row.node_id for row in requests] == ["do", "next"]
    assert [row.requested_by for row in requests] == ["run-policy", "run-policy"]
    assert {row.run_authorization_id for row in requests} == {"grant"}
    assert [row.outcome for row in results] == ["succeeded", "succeeded"]
    assert f.adapter.execute_calls == f.adapter.publish_calls == f.adapter.release_calls == 2
    assert f.adapter.verify_calls == 0 and len(f.verifier.independent_calls) == 2
    assert sum(row.kind == "decision" for row in recovered.records) == 1
    assert sum(row.kind == "run_authorization" for row in recovered.records) == 1


def test_one_human_authorization_drives_two_steps_and_independent_checks(tmp_path):
    f = setup(tmp_path, two_steps=True, checker=True)
    driver, execution = attach_driver(f)
    try:
        authorize(f)
        assert_two_steps(f, wait_terminal(f))
    finally:
        driver.stop()
        execution.shutdown()


def test_restart_does_not_activate_until_explicit_human_resume(tmp_path):
    f = setup(tmp_path, two_steps=True, checker=True)
    grant = authorize(f)  # The initial test activation writes no requests.
    previous = f.store.read("run").records
    f.runtime = ControlRuntime(f.store, f.registry, clock=f.policy.clock, ids=f.runtime._ids)
    f.policy = PolicyService(f.store, f.registry, budget=f.policy.budget, clock=f.policy.clock,
        provider_digest=lambda config: PD, owner_check=lambda: None, session="new-session",
        notify=lambda run: None)
    f.runtime._policy = f.policy
    driver, execution = attach_driver(f)
    try:
        driver.wake("run")
        Event().wait(.05)
        assert f.store.read("run").records == previous and f.adapter.execute_calls == 0
        f.policy.control("run", {"control_id": "resume", "authorization_id": grant.authorization_id,
            "authorization_digest": grant.authorization_digest, "action": "resume", "actor": "owner",
            "expected_control_id": None})
        assert_two_steps(f, wait_terminal(f))
    finally:
        driver.stop()
        execution.shutdown()
