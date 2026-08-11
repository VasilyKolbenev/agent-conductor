"""Run-store tests: durable facts before December starts a Harness.

The store is intentionally exercised through public methods except where a
test damages bytes to reproduce a crash.  A partial final journal line is the
only damage recovery may discard; an invalid complete line is corruption.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from conductor.command import run_store
from conductor.command.contracts import (
    ActionRequest,
    ActionResultReceipt,
    DecisionReceipt,
    EvidenceRef,
    RunEnvelope,
)
from conductor.command.run_store import (
    CorruptRun,
    RecordConflict,
    RunExists,
    RunStore,
    StoreError,
    snapshot_digest,
)


NOW = "2026-08-11T09:00:00Z"
CONFIG = {
    "cycle": {"id": "default-orbit", "phases": ["goal", "detect", "design"]},
    "instances": [
        {"id": "claude-dev", "adapter": "claude-code", "token_env": "ANTHROPIC_API_KEY"},
        {"id": "codex-review", "adapter": "codex", "api_key_env": "OPENAI_API_KEY"},
    ],
}


def a_run(**changes):
    values = {
        "run_id": "run-001",
        "cycle_id": "default-orbit",
        "created_at": NOW,
        "config_digest": snapshot_digest(CONFIG),
    }
    values.update(changes)
    return RunEnvelope(**values)


def an_action(**changes):
    values = {
        "action_id": "action-001",
        "run_id": "run-001",
        "attempt_id": "attempt-001",
        "instance_id": "claude-dev",
        "capability": "dispatch",
        "arguments": {"handoff": "packet-001"},
        "scope": ("src",),
        "requested_by": "owner",
        "requested_at": NOW,
        "idempotency_key": "dispatch-001",
        "timeout_seconds": 900,
        "preview_digest": "sha256:" + "b" * 64,
        "mode": "confirm",
    }
    values.update(changes)
    return ActionRequest(**values)


def a_result(**changes):
    values = {
        "receipt_id": "result-001",
        "action_id": "action-001",
        "run_id": "run-001",
        "attempt_id": "attempt-001",
        "instance_id": "claude-dev",
        "outcome": "succeeded",
        "observed_at": "2026-08-11T09:01:00Z",
        "evidence_refs": ("evidence-001",),
    }
    values.update(changes)
    return ActionResultReceipt(**values)


def a_decision(**changes):
    values = {
        "receipt_id": "decision-001",
        "run_id": "run-001",
        "gate_id": "release",
        "action": "approve",
        "actor": "release-owner",
        "decided_at": "2026-08-11T09:02:00Z",
        "reason": "Reviewed the evidence.",
        "scope_refs": ("release",),
        "config_digest": snapshot_digest(CONFIG),
    }
    values.update(changes)
    return DecisionReceipt(**values)


def evidence(**changes):
    values = {
        "evidence_id": "evidence-001",
        "run_id": "run-001",
        "kind": "test",
        "uri": "artifacts/pytest.json",
        "label": "pytest result",
        "created_by": "claude-dev",
        "observed_at": "2026-08-11T09:01:00Z",
    }
    values.update(changes)
    return EvidenceRef(**values)


def canonical_line(wrapper):
    """The one JSON spelling the store accepts, written by hand in the test."""
    return json.dumps(
        wrapper, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def write_decision_file(store, decision, stem=None):
    """Put a durable, canonically spelled receipt file into a run from outside."""
    path = (store.run_path(decision.run_id) / "decisions"
            / f"{stem or decision.receipt_id}.json")
    wrapper = {"record": decision.as_dict(), "record_type": "decision"}
    path.write_bytes(canonical_line(wrapper).encode("utf-8"))
    return path


def test_create_run_persists_canonical_identity_and_a_frozen_unaliased_snapshot(tmp_path):
    source = json.loads(json.dumps(CONFIG))
    store = RunStore(tmp_path)
    stored = store.create_run(a_run(), source)
    source["cycle"]["phases"].append("tampered-after-create")

    assert stored == tmp_path / "conductor" / "runs" / "run-001"
    recovered = store.recover("run-001")
    assert recovered.envelope == a_run()
    assert recovered.config["cycle"]["phases"] == ("goal", "detect", "design")
    assert recovered.records == ()
    assert recovered.warnings == ()
    assert (stored / "run.json").read_text(encoding="utf-8").endswith("\n")
    assert (stored / "config.json").read_text(encoding="utf-8").endswith("\n")


def test_create_run_is_exclusive_and_a_digest_mismatch_leaves_no_run(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    with pytest.raises(RunExists, match="run-001"):
        store.create_run(a_run(), CONFIG)

    wrong = a_run(run_id="run-wrong", config_digest="sha256:" + "f" * 64)
    with pytest.raises(StoreError, match="config_digest"):
        store.create_run(wrong, CONFIG)
    assert not (tmp_path / "conductor" / "runs" / "run-wrong").exists()


@pytest.mark.parametrize("snapshot", [
    {"adapter": {"api_key": "written-secret"}},
    {"adapter": {"apiKey": "written-secret"}},
    {"adapter": {"password": "written-secret"}},
    {"nested": [{"authorization": "Bearer written-secret"}]},
    {"adapter": {"token_env": "sk-not-an-environment-name"}},
])
def test_frozen_snapshot_rejects_secret_values_but_allows_environment_references(
        tmp_path, snapshot):
    store = RunStore(tmp_path)
    run = a_run(run_id="run-secret", config_digest=snapshot_digest(snapshot))
    with pytest.raises(StoreError, match="secret-bearing field"):
        store.create_run(run, snapshot)
    assert not store.run_path("run-secret").exists()


def test_append_and_replay_preserve_causal_order_and_never_fold_acceptance_into_success(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    assert store.append(an_action()) is True
    assert store.append(evidence()) is True
    assert store.append(a_result()) is True

    recovered = store.recover("run-001")
    assert [row.kind for row in recovered.records] == [
        "action_request", "evidence", "action_result",
    ]
    assert recovered.records[0].value == an_action()
    assert recovered.records[1].value == evidence()
    assert recovered.records[2].value == a_result()
    assert recovered.records[2].value.outcome == "succeeded"


def test_result_must_follow_and_match_the_action_it_claims_to_finish(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    with pytest.raises(StoreError, match="unknown action 'action-001'"):
        store.append(a_result())
    store.append(an_action())
    with pytest.raises(StoreError, match="attempt_id"):
        store.append(a_result(attempt_id="attempt-other"))
    with pytest.raises(StoreError, match="instance_id"):
        store.append(a_result(instance_id="codex-review"))
    assert [row.kind for row in store.recover("run-001").records] == ["action_request"]


def test_identical_append_is_idempotent_but_ids_and_idempotency_keys_cannot_change_meaning(
        tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    assert store.append(an_action()) is True
    assert store.append(an_action()) is False
    assert len(store.recover("run-001").records) == 1

    with pytest.raises(RecordConflict, match="action-001"):
        store.append(an_action(scope=("tests",)))
    with pytest.raises(RecordConflict, match="idempotency_key"):
        store.append(an_action(action_id="action-002", scope=("tests",)))
    assert len(store.recover("run-001").records) == 1


def test_a_record_never_falls_back_to_another_run_when_its_run_is_missing(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    with pytest.raises(StoreError, match="run 'run-other' does not exist"):
        store.append(an_action(run_id="run-other"))


def test_human_decision_receipt_is_exclusive_and_tampering_is_corruption(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    assert store.append(a_decision()) is True
    assert store.append(a_decision()) is False

    decision_path = store.run_path("run-001") / "decisions" / "decision-001.json"
    raw = json.loads(decision_path.read_text(encoding="utf-8"))
    raw["action"] = "reject"
    decision_path.write_text(json.dumps(raw) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(CorruptRun, match="decision-001"):
        store.recover("run-001")


def test_a_crash_while_writing_a_decision_receipt_publishes_no_receipt_at_all(
        tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    decisions = store.run_path("run-001") / "decisions"

    def tear(fd, payload):
        os.write(fd, payload[:12])
        raise OSError("the machine lost power mid-write")

    monkeypatch.setattr(run_store, "_write_all", tear)
    with pytest.raises(StoreError, match="cannot create decision receipt"):
        store.append(a_decision())
    assert list(decisions.iterdir()) == []

    monkeypatch.undo()
    assert store.append(a_decision()) is True
    assert [row.value for row in store.recover("run-001").records] == [a_decision()]


def test_decision_must_bind_to_this_frozen_config_and_supersede_a_prior_same_gate(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    with pytest.raises(StoreError, match="config_digest"):
        store.append(a_decision(config_digest="sha256:" + "f" * 64))
    with pytest.raises(StoreError, match="supersedes unknown"):
        store.append(a_decision(receipt_id="decision-002", supersedes="decision-missing"))
    store.append(a_decision())
    with pytest.raises(StoreError, match="different gate"):
        store.append(a_decision(
            receipt_id="decision-002", gate_id="security", supersedes="decision-001"))


def test_recovery_rejoins_an_exclusive_decision_left_before_its_journal_append(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(a_decision())
    journal = store.run_path("run-001") / "records.jsonl"
    journal.write_bytes(b"")

    recovered = store.recover("run-001")
    assert [row.value for row in recovered.records] == [a_decision()]
    assert recovered.warnings == (
        "decision receipt 'decision-001' survived without its journal line; "
        "the line was recovered",
    )
    assert store.recover("run-001").warnings == ()


def test_a_decision_file_that_cannot_be_reconciled_leaves_the_journal_byte_identical(
        tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(an_action())
    journal = store.run_path("run-001") / "records.jsonl"
    before = journal.read_bytes()

    stray = write_decision_file(store, a_decision(
        receipt_id="decision-bogus", config_digest="sha256:" + "f" * 64))
    with pytest.raises(CorruptRun, match="config_digest does not match the frozen run"):
        store.recover("run-001")
    assert journal.read_bytes() == before

    stray.unlink()
    assert [row.value for row in store.recover("run-001").records] == [an_action()]
    assert store.append(evidence()) is True


def test_orphan_receipts_rejoin_when_they_were_decided_not_in_filename_order(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(a_decision(receipt_id="zzz-early", decided_at="2026-08-11T09:02:00Z"))
    store.append(a_decision(
        receipt_id="aaa-late", gate_id="security", decided_at="2026-08-11T09:03:00Z"))
    journal = store.run_path("run-001") / "records.jsonl"
    journal.write_bytes(b"")

    names = sorted(
        path.stem for path in (store.run_path("run-001") / "decisions").glob("*.json"))
    assert names == ["aaa-late", "zzz-early"]
    recovered = store.recover("run-001")
    assert [row.value.receipt_id for row in recovered.records] == ["zzz-early", "aaa-late"]
    assert [json.loads(line)["record"]["receipt_id"]
            for line in journal.read_text(encoding="utf-8").splitlines()] == [
        "zzz-early", "aaa-late"]


def test_a_superseding_receipt_rejoins_after_the_receipt_it_supersedes(tmp_path):
    """Two receipts decided in the same second; the id tie-break opposes causality."""
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(a_decision(receipt_id="zzz-first", decided_at="2026-08-11T09:02:00Z"))
    store.append(a_decision(
        receipt_id="aaa-second", decided_at="2026-08-11T09:02:00Z",
        supersedes="zzz-first"))
    journal = store.run_path("run-001") / "records.jsonl"
    journal.write_bytes(b"")

    recovered = store.recover("run-001")
    assert [row.value.receipt_id for row in recovered.records] == ["zzz-first", "aaa-second"]
    assert [json.loads(line)["record"]["receipt_id"]
            for line in journal.read_text(encoding="utf-8").splitlines()] == [
        "zzz-first", "aaa-second"]


def test_recovery_discards_only_an_incomplete_final_line_and_keeps_durable_records(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(an_action())
    journal = store.run_path("run-001") / "records.jsonl"
    with journal.open("ab") as stream:
        stream.write(b'{"record_type":"action_result"')

    recovered = store.recover("run-001")
    assert [row.value for row in recovered.records] == [an_action()]
    assert recovered.warnings == (
        "records.jsonl ended with an incomplete record; the incomplete tail was ignored",
    )
    assert journal.read_bytes().endswith(b"\n")


def test_recovery_refuses_a_complete_invalid_record_instead_of_skipping_history(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    journal = store.run_path("run-001") / "records.jsonl"
    with journal.open("ab") as stream:
        stream.write(b'{"record_type":"unknown"}\n')
    with pytest.raises(CorruptRun, match="records.jsonl line 1"):
        store.recover("run-001")


def test_recovery_refuses_noncanonical_but_parseable_journal_bytes(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(an_action())
    journal = store.run_path("run-001") / "records.jsonl"
    journal.write_bytes(journal.read_bytes().replace(b'{"record":', b'{ "record":'))
    with pytest.raises(CorruptRun, match="canonical JSON"):
        store.recover("run-001")


def test_recovery_detects_frozen_configuration_tampering(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    config_path = store.run_path("run-001") / "config.json"
    config_path.write_text('{"cycle":{"id":"different"}}\n', encoding="utf-8")
    with pytest.raises(CorruptRun, match="config digest"):
        store.recover("run-001")


def test_run_path_accepts_only_contract_ids(tmp_path):
    store = RunStore(tmp_path)
    with pytest.raises(StoreError, match="run_id"):
        store.run_path("../outside")
    assert not (Path(tmp_path).parent / "outside").exists()
