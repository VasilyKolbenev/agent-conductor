"""A legacy pending proposal is a recoverable review task, not a malformed request."""
from conductor.command.api_contracts import refusal_from_exception
from conductor.command.runtime_values import ProposalNeedsRebinding


def test_legacy_material_binding_refusal_has_its_own_sanitized_wire_road():
    refused = refusal_from_exception(ProposalNeedsRebinding("PRIVATE_PATH_AND_KEY"))
    assert refused.code == "proposal_rebind_required"
    payload = refused.as_dict()
    assert "PRIVATE_PATH_AND_KEY" not in str(payload)
    assert "new proposal" in str(payload)
    assert "review" in str(payload)
