"""Input binding is a versioned proposal fact, not a new reading of old bytes."""
from dataclasses import replace

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.artifact_handoff import ArtifactHandoff, UnboundProposal
from conductor.command.contracts import (
    ABSENT, ActionProposal, ContractError, canonical_json,
)
from conductor.command.runtime import ControlRuntime
from conductor.command.runtime_values import ProposalNeedsRebinding
from conductor.command.service import CommandService
from tests.test_command_input_binding import (
    _a_review_run_with_a_later_candidate, _proposal_for,
)
from tests.test_command_artifact_dispatch import ARGUMENTS, _Ids
from tests.test_command_claude_review import _confirmation
from tests.test_command_claude_transport import NOW
from conductor.command.runtime import Budget


def test_the_binding_marker_is_optional_but_never_null_or_unknown():
    marked = _proposal_for(ARGUMENTS)
    legacy = replace(marked, input_binding=ABSENT, preview_digest="")
    legacy_bytes = canonical_json(legacy.as_dict())
    assert "input_binding" not in legacy.as_dict()
    assert canonical_json(ActionProposal.from_dict(legacy.as_dict()).as_dict()) == legacy_bytes
    assert marked.as_dict()["input_binding"] == "proposal-v1"
    assert marked.preview_digest != legacy.preview_digest
    for malformed in (None, "", "proposal-v2", [], True):
        with pytest.raises(ContractError, match="input_binding"):
            ActionProposal.from_dict({**legacy.as_dict(), "input_binding": malformed})
        with pytest.raises(ContractError, match="input_binding"):
            replace(legacy, input_binding=malformed)


def test_removing_or_adding_binding_cannot_keep_the_confirmed_digest():
    marked = _proposal_for(ARGUMENTS)
    removed = {key: value for key, value in marked.as_dict().items()
               if key != "input_binding"}
    with pytest.raises(ContractError, match="preview_digest"):
        ActionProposal.from_dict(removed)
    legacy = replace(marked, input_binding=ABSENT, preview_digest="")
    with pytest.raises(ContractError, match="preview_digest"):
        ActionProposal.from_dict({**legacy.as_dict(), "input_binding": "proposal-v1"})


def _legacy(tmp_path):
    adapter, root, store, proposal = _a_review_run_with_a_later_candidate(tmp_path)
    registry = AdapterRegistry([adapter])
    runtime = ControlRuntime(store, registry, clock=lambda: NOW, ids=_Ids())
    budget = Budget(max_actions=8, max_action_seconds=3600,
                    max_confirmation_age_seconds=3600)
    return root, store, proposal, registry, runtime, budget


def test_pending_legacy_proposal_must_be_reproposed_before_new_authority(tmp_path):
    root, store, proposal, registry, runtime, budget = _legacy(tmp_path)
    journal = store.run_path(proposal.run_id) / "records.jsonl"
    before = journal.read_bytes()
    admitted = []
    with pytest.raises(ProposalNeedsRebinding, match="Create a new proposal"):
        runtime.authorize(_confirmation(proposal), budget=budget,
                          admit=lambda: admitted.append(True))
    assert admitted == [] and runtime._grants == set()
    assert journal.read_bytes() == before
    handoff = ArtifactHandoff(store, clock=lambda: NOW, ids=_Ids())
    with pytest.raises(UnboundProposal, match="create a new proposal"):
        handoff.bound(proposal.run_id, proposal.proposal_id, ("artifact-candidate",))


def test_an_exact_historical_confirmation_retry_is_not_a_new_grant(tmp_path):
    _, store, proposal, _, runtime, budget = _legacy(tmp_path)
    confirmation = _confirmation(proposal)
    request = runtime._mint_request(confirmation, proposal)
    store.append(request)  # The request an older runtime already authorized.
    journal = store.run_path(proposal.run_id) / "records.jsonl"
    before = journal.read_bytes()
    admitted = []
    retry = runtime.authorize(confirmation, budget=budget,
                              admit=lambda: admitted.append(True))
    assert retry.request == request and retry.record_created is False
    assert admitted == [] and runtime._grants == set()
    assert journal.read_bytes() == before


def test_service_marks_new_deep_proposals_and_the_new_preview_can_be_confirmed(tmp_path):
    _, store, legacy, registry, runtime, budget = _legacy(tmp_path)
    service = CommandService(store, registry, clock=lambda: NOW, ids=_Ids())
    proposal = service.propose(
        run_id=legacy.run_id, instance_id=legacy.instance_id,
        attempt_id="fresh-attempt", capability=legacy.capability,
        arguments=legacy.arguments, scope=legacy.scope,
        proposed_by=legacy.proposed_by, rationale=legacy.rationale,
        timeout_seconds=legacy.timeout_seconds, proposal_id="fresh-proposal")
    assert proposal.input_binding == "proposal-v1"
    assert store.read(legacy.run_id).records[-1].value == proposal
    authorization = runtime.authorize(_confirmation(proposal), budget=budget)
    assert authorization.record_created is True
    assert authorization.request.preview_digest == proposal.preview_digest


def test_non_deep_proposals_keep_the_legacy_wire_shape(tmp_path):
    from tests.test_command_service import a_service, propose_kwargs

    service, store = a_service(tmp_path)
    proposal = service.propose(**propose_kwargs())
    assert proposal.input_binding is ABSENT
    assert "input_binding" not in proposal.as_dict()
    assert store.read(proposal.run_id).records[-1].value == proposal
