"""A rejected product is not an input, and a preview never silently rebinds.

These witnesses judge actual artifact/receipt contracts, the shared schedule
reader, and the store's direct causal relation. The latter is intentionally
called below the authorize door: a refusal higher up cannot guard replay.
"""
import pytest

from conductor.command.artifacts import (
    ArtifactDocument, latest_artifacts, settled_products,
    unresolved_input_refs, validate_artifact_source,
)
from conductor.command.contracts import ABSENT, ContractError
from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.graph_schedule import schedule
from tests.test_command_graph_projection import an_event
from tests.test_command_http_api import RUN_ID, api, post
from tests.test_command_run_store import NOW, a_result, an_action
from tests.test_command_runtime_authorize import a_proposal


REF = "artifact-candidate"
ARGUMENTS = {"target_artifact_refs": [REF],
             "result_artifact_ref": "artifact-reviewed"}


def document(identity, *, source=None):
    return ArtifactDocument(
        artifact_id=identity, artifact_ref=REF, run_id=RUN_ID,
        created_at=NOW, media_type="text/markdown", content=identity,
        source_action_id=source)


def terminal(source, outcome):
    return a_result(receipt_id=f"result-{source}", action_id=source,
                    outcome=outcome, evidence_refs=())


def consuming(prior, *, marked=True):
    proposal = a_proposal(
        capability="review", arguments=ARGUMENTS,
        input_binding="proposal-v1" if marked else ABSENT)
    request = an_action(
        action_id="action-consumer", capability="review", arguments=ARGUMENTS,
        idempotency_key=f"dispatch-{proposal.proposal_id}")
    observed = an_event(
        request, "execution_observed", outcome="succeeded", exit_code=0)
    return request, (*prior, proposal, request, observed)


def output(request, *inputs):
    return ArtifactDocument(
        artifact_id="artifact-result", artifact_ref="artifact-reviewed",
        run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
        content="Reviewed the candidate.", source_action_id=request.action_id,
        input_artifact_ids=inputs)


@pytest.mark.parametrize("outcome", [
    "failed", "unknown", "verification_failed", "cancelled", "rejected"])
def test_a_terminal_non_success_is_not_a_product(outcome):
    candidate = document("candidate-1", source="producer")
    assert settled_products((candidate,)) == (candidate,)
    assert settled_products((candidate, terminal("producer", outcome))) == ()
    assert unresolved_input_refs(
        (candidate, terminal("producer", outcome)), "review", ARGUMENTS) == (REF,)


def test_a_successful_older_revision_is_selected_when_the_latest_was_rejected():
    older = document("candidate-1", source="producer-1")
    rejected = document("candidate-2", source="producer-2")
    rows = (older, terminal("producer-1", "succeeded"), rejected,
            terminal("producer-2", "verification_failed"))
    assert latest_artifacts(settled_products(rows), (REF,)) == (older,)
    assert unresolved_input_refs(rows, "review", ARGUMENTS) == ()
    request, prior = consuming(rows)
    validate_artifact_source(output(request, older.artifact_id), prior)
    with pytest.raises(ContractError, match="input ids do not match"):
        validate_artifact_source(output(request, rejected.artifact_id), prior)


def test_block_waits_for_an_accepted_product_but_never_filters_a_human_document():
    plan = GraphDefinition(
        graph_id="graph-products", run_id=RUN_ID, created_at=NOW,
        nodes=(GraphNode(
            node_id="review", kind="task", title="Review", instance_id="reviewer",
            capability="review", arguments=ARGUMENTS,
            missing_artifact_policy="block"),), edges=())
    rejected = document("candidate-2", source="producer")
    rows = (rejected, terminal("producer", "verification_failed"))
    held = schedule(plan, rows)
    assert held.state_of("review") == "blocked"
    assert held.nodes[0].awaiting_artifacts == (REF,)
    assert held.run_state == "open"
    human = document("candidate-human")
    assert settled_products((*rows, human)) == (human,)
    assert schedule(plan, (*rows, human)).state_of("review") == "runnable"


def test_the_http_publication_road_creates_a_human_product(tmp_path):
    subject, store, _ = api(tmp_path)
    response = post(subject, f"/command/runs/{RUN_ID}/artifacts", {
        "artifact_id": "human-1", "artifact_ref": REF,
        "media_type": "text/plain", "content": "The owner's source."})
    assert response.status == 201
    rows = tuple(row.value for row in store.read(RUN_ID).records)
    assert settled_products(rows) == (rows[0],)
    assert rows[0].source_action_id is None


def test_a_failure_after_preview_refuses_the_exact_binding_without_falling_back():
    older = document("candidate-1", source="producer-1")
    selected = document("candidate-2", source="producer-2")
    request, prior = consuming((older, terminal("producer-1", "succeeded"), selected))
    validate_artifact_source(output(request, selected.artifact_id), prior)
    failed = (*prior, terminal("producer-2", "verification_failed"))
    for claimed in (selected, older):
        with pytest.raises(ContractError, match="failed after its proposal"):
            validate_artifact_source(output(request, claimed.artifact_id), failed)
    # Replay judges the prefix before this artifact, not a failure appended
    # afterwards. The original accepted relation remains accepted unchanged.
    validate_artifact_source(output(request, selected.artifact_id), prior)


def test_legacy_replay_keeps_the_pre_existing_unfiltered_input_rule():
    older = document("candidate-1")
    rejected = document("candidate-2", source="producer")
    rows = (older, rejected, terminal("producer", "verification_failed"))
    request, prior = consuming(rows, marked=False)
    validate_artifact_source(output(request, rejected.artifact_id), prior)
    with pytest.raises(ContractError, match="input ids do not match"):
        validate_artifact_source(output(request, older.artifact_id), prior)
