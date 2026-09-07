"""A live extension does not buy permission to rewrite the ALPHA-1 journal."""
from conductor.command.attempts import AttemptEvent
from conductor.command.contracts import ActionProposal, ActionRequest, ActionResultReceipt, EvidenceRef
from tests.alpha1_artifacts import load
from tests.alpha1_providers import a_store


def test_frozen_terminal_rows_still_append_and_replay_without_binding_fields(tmp_path):
    factories = {"action_proposal": ActionProposal, "action_request": ActionRequest,
                 "attempt_event": AttemptEvent, "evidence": EvidenceRef,
                 "action_result": ActionResultReceipt}
    terminal = next(row for row in load("alpha1_record_states")["states"]
                    if row["state"] == "terminal")
    store = a_store(tmp_path)
    expected = terminal["durable_records"]
    for row in expected:
        record = factories[row["record_type"]].from_dict(row["record"])
        assert record.as_dict() == row["record"]
        store.append(record)
    recovered = store.read("run-001")
    assert not recovered.warnings
    assert [{"record_type": row.kind, "record": row.value.as_dict()}
            for row in recovered.records] == expected
