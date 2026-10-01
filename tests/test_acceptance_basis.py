"""Acceptance's journal foundation refuses missing final snapshots; it is not a preview."""
from dataclasses import replace

import pytest

from conductor.command.acceptance_basis import AcceptanceRun, acceptance_basis
from conductor.command.artifacts import ArtifactDocument, REVIEW_CAPABILITY
from conductor.command.contract_values import ContractError
from conductor.command.graph_definition import GraphDefinition, GraphEdge, GraphNode
from conductor.command.run_terminal import RunTerminal
from conductor.command.seed_record import SeedRecord
from conductor.command.task_contracts import TaskBinding
from tests.test_command_run_store import NOW, a_decision, an_action, evidence
from tests.test_seed_record import a_git_seed

RUN = "run-001"
TASK = TaskBinding("task-one", "task-one")
TREE, MANIFEST = "sha256:" + "a" * 64, "sha256:" + "b" * 64


def facts(**changes):
    return AcceptanceRun(**{"run_id": RUN, "task": TASK, "created_at": NOW,
                            "has_action_requests": True, "active": False, "queued": False,
                            **changes})


def journal(capability="dispatch"):
    plan = GraphDefinition("graph-one", RUN, NOW, (
        GraphNode("do", "task", "Work", instance_id="claude-dev", capability=capability),
        GraphNode("finish", "gate", "Accept", gate_id="release")),
        execution_contract="bounded-run-v1")
    action = an_action(node_id="do", capability=capability)
    proof = evidence(kind="verification", uri=f"verification/{action.action_id}", digest=TREE,
                     verification="verified", verified_by="checker", verified_at=NOW,
                     verifier_instance_id="independent-checker", extra={
                         "work_tree_digest": TREE, "accept_manifest_digest": MANIFEST})
    terminal = RunTerminal("ended", RUN, plan.graph_id, "complete", ("do", "finish"), (), NOW)
    return plan, [action, proof, a_decision(), terminal]


def seed():
    return SeedRecord.from_dict(a_git_seed(task_id=TASK.task_id, work_scope=TASK.work_scope))


def basis(plan=None, rows=None, *, runs=None, stored_seed=True):
    default_plan, default_rows = journal()
    return acceptance_basis(plan or default_plan, default_rows if rows is None else rows,
                            [facts()] if runs is None else runs, seed() if stored_seed else None)


def test_files_basis_confirms_only_journal_and_requires_both_preview_checks():
    plan, rows = journal()
    before = tuple(row.as_dict() for row in rows)
    result = basis(plan, rows)
    assert result.refused is None
    assert (result.kind, result.final_gate, result.decision_id, result.verified_action) == (
        "files", "release", "decision-001", "action-001")
    assert (result.work_tree_digest, result.accept_manifest_digest) == (TREE, MANIFEST)
    assert result.pending_checks == ("snapshot_integrity", "current_work_tree")
    assert not hasattr(result, "accept_digest")
    assert tuple(row.as_dict() for row in rows) == before


@pytest.mark.parametrize("extra", [{}, {"work_tree_digest": TREE},
                                  {"accept_manifest_digest": MANIFEST},
                                  {"work_tree_digest": TREE, "accept_manifest_digest": "broken"}])
def test_legacy_or_incomplete_snapshot_evidence_is_never_an_acceptance_basis(extra):
    plan, rows = journal()
    rows[1] = replace(rows[1], extra=extra)
    assert basis(plan, rows).refused == "final_check_missing"


def test_task_seed_and_complete_terminal_are_required_for_files():
    plan, rows = journal()
    assert basis(runs=[facts(task=None)]).refused == "run_has_no_task"
    assert basis(stored_seed=False).refused == "seed_missing"
    assert basis(plan, rows[:-1]).refused == "run_not_complete"
    rows[-1] = replace(rows[-1], state="stalled")
    assert basis(plan, rows).refused == "run_not_complete"


@pytest.mark.parametrize("field,value", [("task_id", "other"), ("work_scope", "other"),
                                         ("work_item_id", "work-002")])
def test_seed_must_match_the_frozen_task_and_work_item(field, value):
    plan, rows = journal()
    with pytest.raises(ContractError, match="seed does not match"):
        acceptance_basis(plan, rows, [facts()], replace(seed(), **{field: value}))


@pytest.mark.parametrize("action", ["waive", "reject", "request_changes"])
def test_only_current_approval_counts_not_a_superseded_approval(action):
    plan, rows = journal()
    rows.insert(-1, a_decision(receipt_id="correction", action=action,
                               supersedes="decision-001", reason="Changed decision"))
    assert basis(plan, rows).refused == "final_gate_not_approved"


@pytest.mark.parametrize("condition,accepted", [(None, False), ("on_approved", False),
                                               ("on_rejected", True)])
def test_a_final_gate_has_no_road_opened_by_approval(condition, accepted):
    plan, rows = journal()
    plan = replace(plan, nodes=(*plan.nodes, GraphNode("after", "task", "After")),
                   edges=(GraphEdge("finish", "after", condition),))
    rows[-1] = replace(rows[-1], settled_nodes=("do", "finish") if accepted else
                       ("do", "finish", "after"), unreachable_nodes=("after",) if accepted else ())
    assert (basis(plan, rows).refused is None) is accepted


def test_latest_current_final_approval_is_selected_by_journal_order_not_timestamp():
    plan, rows = journal()
    plan = replace(plan, nodes=(*plan.nodes, GraphNode("also", "gate", "Also", gate_id="other")))
    rows.insert(-1, a_decision(receipt_id="other-decision", gate_id="other", decided_at=NOW))
    rows[-1] = replace(rows[-1], settled_nodes=("do", "finish", "also"))
    result = basis(plan, rows)
    assert result.refused is None
    assert (result.final_gate, result.decision_id) == ("other", "other-decision")


@pytest.mark.parametrize("changes", [{"verifier_instance_id": None},
                                     {"verifier_instance_id": "claude-dev"},
                                     {"digest": None}, {"verification": "mismatch"},
                                     {"uri": "verification/other"}])
def test_each_latest_dispatch_needs_its_own_independently_verified_evidence(changes):
    plan, rows = journal()
    rows[1] = replace(rows[1], **changes)
    assert basis(plan, rows).refused == "result_not_verified"


def test_a_new_attempt_cannot_borrow_the_old_attempts_verification():
    plan, rows = journal()
    rows.insert(2, an_action(action_id="action-two", attempt_id="attempt-two", node_id="do"))
    assert basis(plan, rows).refused == "result_not_verified"


def test_a_late_proof_of_an_old_attempt_is_not_the_final_snapshot_of_the_latest_attempt():
    plan, rows = journal()
    older = an_action(action_id="action-old", attempt_id="attempt-old", node_id="do")
    proof = replace(rows[1], evidence_id="evidence-old", uri="verification/action-old", extra={})
    rows.insert(0, older)
    rows.insert(3, proof)
    assert basis(plan, rows).refused == "final_check_missing"


def test_approval_must_follow_the_result_in_the_journal():
    plan, rows = journal()
    rows[1], rows[2] = rows[2], rows[1]
    assert basis(plan, rows).refused == "decision_precedes_result"


def test_later_work_and_any_active_or_queued_run_of_this_task_block_files():
    later = facts(run_id="run-two", created_at="2026-08-11T09:00:00.1Z")
    assert basis(runs=[facts(), later]).refused == "superseded_by_later_run"
    assert basis(runs=[facts(), replace(later, has_action_requests=False)]).refused is None
    for flag in ("active", "queued"):
        assert basis(runs=[replace(facts(), **{flag: True})]).refused == "task_run_active"
    other_task = replace(later, task=TaskBinding("other", "other"), active=True, queued=True)
    assert basis(runs=[facts(), other_task]).refused is None


def test_missing_or_ambiguous_inventory_is_an_input_error_not_no_later_work():
    for runs in ([], [facts(), facts()]):
        with pytest.raises(ContractError):
            basis(runs=runs)
    with pytest.raises(ContractError, match="cannot be ordered"):
        basis(runs=[facts(), facts(run_id="run-two", created_at="2026-08-11T09:00:00.000+00:00")])
    with pytest.raises(ContractError, match="disagree"):
        basis(runs=[facts(has_action_requests=False)])
    with pytest.raises(ContractError, match="known booleans"):
        facts(active=None)


def test_documents_use_verified_immutable_artifact_bytes_without_a_seed_or_tree_claim():
    plan, rows = journal(REVIEW_CAPABILITY)
    artifact = ArtifactDocument("artifact-one", "artifact-plan", RUN, NOW, "text/markdown",
                                "A checked plan", "action-001")
    rows[1] = replace(rows[1], digest=artifact.digest(), extra={})
    rows.insert(1, artifact)
    result = basis(plan, rows, stored_seed=False)
    assert result.refused is None and result.kind == "documents"
    assert result.accept_manifest_digest is None and result.pending_checks == ()
    rows[2] = replace(rows[2], digest=TREE)
    assert basis(plan, rows, stored_seed=False).refused == "result_not_verified"
