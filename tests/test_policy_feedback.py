"""A definite independent rejection follows only its pinned correction road."""
from dataclasses import replace
import pytest

from conductor.command.adapters import AdapterVerification
from conductor.command.artifact_handoff import ArtifactHandoff
from conductor.command.contracts import ABSENT, ContractError, ActionProposal
from conductor.command.feedback_payload import payload_bytes
from conductor.command.feedback_history import validate_feedback_history
from conductor.command.graph_definition import GraphEdge, GraphNode, GraphLoop
from conductor.command.policy_driver import _next_node
from conductor.command.run_store import StoreError
from tests import test_policy_driver as drivers
from tests import test_policy_runtime as runtime_tests
from tests.test_policy_runtime import NOW, ARGS, propose

PAYLOAD = {"protocol": "conduct.feedback.v1", "findings": [{"kind": "defect",
    "summary": "answer() must return 1 instead of 2", "path": "answer.py", "line": 2}]}


class RejectOnce(drivers.Signing):
    typed = True

    def publish(self, request, result):
        published = super().publish(request, result)
        return replace(published, result_manifest={"action_id": request.action_id,
            "attempt_id": request.attempt_id, "input_artifact_ids": ["instruction-1"], "files": []})

    def execute(self, prepared):
        request = prepared.request
        handoff = ArtifactHandoff(self._store, clock=lambda: NOW, ids=lambda kind: kind)
        self.corrections = getattr(self, "corrections", []) + [handoff.feedback(request)]
        return super().execute(prepared)

    def verify_for(self, request, result, verifier, material):
        if not self.independent_calls:
            self.independent_calls.append((verifier, material))
            self.started = True
            return AdapterVerification(adapter_id=self.manifest.adapter_id, action_id=request.action_id,
                state="mismatch", observed_at=NOW, detail="rejected",
                feedback=payload_bytes(PAYLOAD) if self.typed else None,
                result_manifest=material.result_manifest if self.typed else None)
        return super().verify_for(request, result, verifier, material)


def fixture(tmp_path, monkeypatch, *, typed=True, loop=False):
    class Checker(RejectOnce):
        pass
    Checker.typed = typed
    original = runtime_tests.GraphDefinition
    def definition(*args, **kwargs):
        kwargs["edges"] = tuple(replace(edge, condition="on_failed")
            if edge.from_node == "do" else edge for edge in kwargs["edges"])
        if loop:
            kwargs["nodes"] = tuple(n for n in kwargs["nodes"] if n.node_id != "next") + (
                GraphNode("again", "loop", "Correct", loop=GraphLoop(bound=2, back_to="do")),)
            kwargs["edges"] = (kwargs["edges"][0], GraphEdge("do", "again", condition="on_failed"))
        return original(*args, **kwargs)
    with monkeypatch.context() as local:
        local.setattr(runtime_tests, "GraphDefinition", definition)
        local.setattr(drivers, "Signing", Checker)
        return runtime_tests.setup(tmp_path, two_steps=True, checker=True)


def first_rejection(f):
    grant = drivers.authorize(f)
    propose(f)
    f.runtime.execute(f.runtime.authorize_policy("run", "proposal", grant.authorization_id))
    return grant, f.store.read("run")


def test_one_grant_delivers_exact_feedback_then_independently_checks_correction(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    driver, execution = drivers.attach_driver(f)
    try:
        drivers.authorize(f)
        recovered = drivers.wait_terminal(f)
        feedback = [r.value for r in recovered.records if r.kind == "correction_feedback"]
        results = [r.value for r in recovered.records if r.kind == "action_result"]
        requests = [r.value for r in recovered.records if r.kind == "action_request"]
        proposals = [r.value for r in recovered.records if r.kind == "action_proposal"]
        assert [r.outcome for r in results] == ["verification_failed", "succeeded"]
        assert [r.node_id for r in requests] == ["do", "next"]
        assert len(feedback) == 1 and feedback[0].as_dict()["payload"] == PAYLOAD
        assert proposals[0].feedback_ids is ABSENT
        assert proposals[1].feedback_ids == (feedback[0].feedback_id,)
        assert f.adapter.corrections == [(), (feedback[0].as_dict(),)]
        assert requests[0].as_dict()["arguments"] == requests[1].as_dict()["arguments"] == ARGS
        assert feedback[0].source_action_id == requests[0].action_id
        assert feedback[0].checker_instance_id == "checker"
        assert sum(r.kind == "run_authorization" for r in recovered.records) == 1
    finally:
        driver.stop()
        execution.shutdown()


def test_plain_reject_stops_without_inventing_correction_data(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch, typed=False)
    grant, recovered = first_rejection(f)
    assert not any(r.kind == "correction_feedback" for r in recovered.records)
    assert _next_node(recovered, grant) == (None, "feedback_required")
    assert f.adapter.execute_calls == 1


def test_feedback_crosses_the_permitted_next_lap_without_replacing_instructions(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch, loop=True)
    driver, execution = drivers.attach_driver(f)
    try:
        ask = drivers.ask()
        ask["node_limits"] = [ask["node_limits"][0]]
        preview = f.policy.preview("run", ask)
        f.policy.authorize("run", {"authorization_id": "grant", "authorized_by": "owner",
            "preview_digest": preview["preview_digest"], "terms": preview["terms"], "supersedes": None})
        recovered = drivers.wait_terminal(f)
        requests = [r.value for r in recovered.records if r.kind == "action_request"]
        assert len(requests) == 2 and [r.node_id for r in requests] == ["do", "do"]
        assert requests[0].attempt_id != requests[1].attempt_id
        assert requests[0].as_dict()["arguments"] == requests[1].as_dict()["arguments"] == ARGS
        assert len(f.adapter.corrections[1]) == 1
        assert f.adapter.corrections[1][0]["source_lap"] == 1
        assert [r.value.outcome for r in recovered.records if r.kind == "action_result"] == [
            "verification_failed", "succeeded"]
    finally:
        driver.stop()
        execution.shutdown()


@pytest.mark.parametrize("field,value", [("source_attempt_id", "foreign"),
    ("checker_instance_id", "doer"), ("checker_adapter_id", "claude-code"),
    ("source_lap", 2), ("authorization_id", "foreign")])
def test_replay_refuses_wrong_runtime_provenance(tmp_path, monkeypatch, field, value):
    f = fixture(tmp_path, monkeypatch)
    grant, recovered = first_rejection(f)
    position = next(i for i, r in enumerate(recovered.records) if r.kind == "correction_feedback")
    prefix = replace(recovered, records=recovered.records[:position])
    feedback = recovered.records[position].value
    with pytest.raises(ContractError):
        validate_feedback_history(prefix, replace(feedback, **{field: value}))


def test_missing_or_foreign_feedback_cannot_start_corrective_action(tmp_path, monkeypatch):
    f = fixture(tmp_path, monkeypatch)
    grant, recovered = first_rejection(f)
    fields = dict(run_id="run", attempt_id="correction", instance_id="doer", capability="dispatch",
        arguments=ARGS, scope=("work/item",), proposed_by="owner", rationale="Fix finding",
        timeout_seconds=30, node_id="next", proposal_id="fix")
    before = f.store.read("run").records
    with pytest.raises(StoreError):
        f.service.propose(**fields, feedback_ids=("foreign",))
    assert f.store.read("run").records == before
    f.service.propose(**fields)
    with pytest.raises(ContractError):
        f.runtime.authorize_policy("run", "fix", grant.authorization_id)
    assert f.adapter.execute_calls == 1
