"""An independent checker is a participant, not just its harness name."""
import pytest

from conductor.command.contracts import ContractError, EvidenceRef
from conductor.command.graph_definition import GraphNode
from conductor.command.graph_template import RunBinding, TemplateNode, materialize
from tests.test_command_plan_verifier import a_template, CONFIG, DOER, CHECKER, NOW


def evidence(**changes):
    values = dict(evidence_id="proof", run_id="run-001", kind="verification",
                  uri="verification/action-1", label="Verified", created_by="codex",
                  observed_at=NOW, verification="verified", verified_by="codex",
                  verified_at=NOW)
    return EvidenceRef(**{**values, **changes})


@pytest.mark.parametrize("value", [None, "", "two participants", 1])
def test_a_present_checker_identity_must_be_one_valid_participant(value):
    payload = {**evidence().as_dict(), "verifier_instance_id": value}
    with pytest.raises(ContractError, match="verifier_instance_id"):
        EvidenceRef.from_dict(payload)


def test_unverified_evidence_cannot_claim_an_independent_checker():
    payload = evidence(verification="unverified", verified_by=None,
                       verified_at=None).as_dict()
    with pytest.raises(ContractError, match="unverified"):
        EvidenceRef.from_dict({**payload, "verifier_instance_id": CHECKER})


def test_absent_checker_keeps_legacy_bytes_and_present_checker_is_a_field():
    legacy = evidence().as_dict()
    assert "verifier_instance_id" not in legacy
    assert EvidenceRef.from_dict(legacy).as_dict() == legacy
    payload = {**legacy, "verifier_instance_id": CHECKER}
    parsed = EvidenceRef.from_dict(payload)
    assert getattr(parsed, "verifier_instance_id", None) == CHECKER
    assert "verifier_instance_id" not in parsed.extra
    assert parsed.as_dict() == payload


def test_a_step_cannot_nominate_its_doer_as_independent_checker():
    with pytest.raises(ContractError, match="another participant"):
        GraphNode(node_id="do", kind="task", title="Do", instance_id=DOER,
                  capability="dispatch", verifier_instance_id=DOER)


def test_a_template_cannot_nominate_the_same_role_as_independent_checker():
    with pytest.raises(ContractError, match="another participant"):
        TemplateNode(node_id="do", kind="task", title="Do", role_id="author",
                     capability="dispatch", verifier_role_id="author")


def test_distinct_template_roles_must_materialize_to_distinct_participants():
    template = a_template(verifier_role="role-checker")
    with pytest.raises(ContractError, match="another participant"):
        materialize(template, RunBinding(assignments={
            "role-implementer": DOER, "role-checker": DOER}), CONFIG,
            graph_id="graph", run_id="run-001", created_at=NOW)
    plan = materialize(template, RunBinding(assignments={
        "role-implementer": DOER, "role-checker": CHECKER}), CONFIG,
        graph_id="graph", run_id="run-001", created_at=NOW)
    node = next(node for node in plan.nodes if node.node_id == "do")
    assert node.verifier_instance_id == CHECKER and node.instance_id == DOER
