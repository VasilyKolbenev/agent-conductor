"""The explicit topology marker survives editing without migrating old drafts."""
import pytest
from conductor.command.contracts import ContractError
from conductor.command.workflow_draft import parse_document, publish_candidate
from tests.test_command_workflow_draft import a_document


def test_optional_execution_contract_survives_draft_and_publication():
    old = parse_document(a_document())
    assert "execution_contract" not in old
    marked = parse_document({**old, "execution_contract": "bounded-run-v1"})
    assert marked == {**old, "execution_contract": "bounded-run-v1"}
    published = publish_candidate(marked, workflow_id="routine", revision=1)
    assert published.as_dict()["execution_contract"] == "bounded-run-v1"
    from conductor.command.api_contracts import parse_template
    assert parse_template(published.as_dict()) == published
    historical = {key: value for key, value in published.as_dict().items()
                  if key != "execution_contract"}
    assert parse_template(historical).as_dict() == historical


@pytest.mark.parametrize("marker", [None, False, "unknown"])
def test_unknown_or_null_execution_contract_is_refused(marker):
    with pytest.raises(ContractError):
        parse_document({**a_document(), "execution_contract": marker})
