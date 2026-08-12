"""Run-store tests: durable facts before December starts a Harness.

The store is exercised through its public methods, with two deliberate
exceptions: a test damages durable bytes to reproduce a crash, or it drives the
private exclusive-receipt publisher `_ensure_decision_file` directly to stand in
for a second writer racing for the same receipt file.  A partial final journal
line is the only damage recovery may discard; an invalid complete line is
corruption.
"""
from __future__ import annotations

import json
import os
import re
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
    {"adapter": {"vendor_token": "written-secret"}},
    {"nested": [{"authorization": "Bearer written-secret"}]},
    {"adapter": {"token_env": "sk-not-an-environment-name"}},
])
def test_frozen_snapshot_rejects_the_known_secret_key_names_and_malformed_env_references(
        tmp_path, snapshot):
    store = RunStore(tmp_path)
    run = a_run(run_id="run-secret", config_digest=snapshot_digest(snapshot))
    with pytest.raises(StoreError, match="secret-bearing field"):
        store.create_run(run, snapshot)
    assert not store.run_path("run-secret").exists()


@pytest.mark.parametrize("snapshot", [
    {"adapter": {"private_key": "written-secret"}},
    {"adapter": {"password_hash": "written-secret"}},
    {"adapter": {"secret_value": "written-secret"}},
    {"adapter": {"token_value": "written-secret"}},
    {"adapter": {"apikeys": ["written-secret"]}},
    {"adapter": {"github_pat": "written-secret"}},
    {"adapter": {"authorization_header": "Bearer written-secret"}},
    {"adapter": {"url": "https://user:written-secret@example.com/x"}},
])
def test_the_frozen_snapshot_screen_reads_key_names_only_and_lets_these_through(
        tmp_path, snapshot):
    """The documented limit: the screen is not an absence-of-secrets guarantee."""
    store = RunStore(tmp_path)
    run = a_run(run_id="run-secret", config_digest=snapshot_digest(snapshot))
    store.create_run(run, snapshot)
    assert store.read("run-secret").envelope == run
    frozen = (store.run_path("run-secret") / "config.json").read_text(encoding="utf-8")
    assert "written-secret" in frozen


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


def test_repeating_a_decision_dedups_in_the_journal_before_the_receipt_file_is_touched(
        tmp_path, monkeypatch):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    reached = []
    ensure = RunStore._ensure_decision_file

    def counted(self, decision, wrapper):
        reached.append(decision.receipt_id)
        return ensure(self, decision, wrapper)

    monkeypatch.setattr(RunStore, "_ensure_decision_file", counted)
    assert store.append(a_decision()) is True
    assert store.append(a_decision()) is False
    assert reached == ["decision-001"]


def test_a_receipt_file_that_already_holds_different_facts_refuses_the_new_body(tmp_path):
    """Exclusive creation, not the journal, is what arbitrates two racing writers."""
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    path = store.run_path("run-001") / "decisions" / "decision-001.json"
    approve, reject = a_decision(), a_decision(action="reject")

    store._ensure_decision_file(
        approve, {"record": approve.as_dict(), "record_type": "decision"})
    published = path.read_bytes()
    with pytest.raises(RecordConflict, match="decision-001"):
        store._ensure_decision_file(
            reject, {"record": reject.as_dict(), "record_type": "decision"})
    assert path.read_bytes() == published

    store._ensure_decision_file(
        approve, {"record": approve.as_dict(), "record_type": "decision"})
    assert path.read_bytes() == published


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


def a_torn_run(root, **changes):
    """A run whose journal lost a decision line and then caught a writer mid-append."""
    store = RunStore(root, **changes)
    store.create_run(a_run(), CONFIG)
    store.append(a_decision())
    journal = store.run_path("run-001") / "records.jsonl"
    journal.write_bytes(b'{"record":{"partial')
    return store, journal


def snapshot_run_bytes(root):
    """Every durable file of a run directory as {relative posix path -> bytes}."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def test_reading_a_run_edits_no_durable_byte_and_repair_is_an_explicit_ask(tmp_path):
    store, journal = a_torn_run(tmp_path)
    root = store.run_path("run-001")
    before = snapshot_run_bytes(root)

    read = store.read("run-001")
    assert [row.value for row in read.records] == [a_decision()]
    # The whole directory, not one file: journal, run.json, config.json, every
    # receipt -- and the file SET, so a leaked staging .tmp would fail equality too.
    assert snapshot_run_bytes(root) == before

    recovered = store.recover("run-001")
    assert [row.value for row in recovered.records] == [a_decision()]
    assert snapshot_run_bytes(root) != before
    assert store.read("run-001").warnings == ()
    assert len(read.warnings) == len(recovered.warnings) == 2
    assert set(read.warnings).isdisjoint(recovered.warnings)


def test_append_hands_the_caller_the_repairs_recovery_made_underneath_it(tmp_path):
    observed = a_torn_run(tmp_path / "observed")[0].recover("run-001").warnings
    assert observed != ()

    seen = []
    writer = a_torn_run(tmp_path / "writer", on_warning=seen.append)[0]
    seen.clear()
    assert writer.append(evidence()) is True
    assert tuple(seen) == observed


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


def append_line(store, wrapper):
    with (store.run_path("run-001") / "records.jsonl").open("ab") as stream:
        stream.write(canonical_line(wrapper).encode("utf-8"))


def damage_line_from_another_run(store):
    append_line(store, {
        "record": an_action(
            run_id="run-other", action_id="action-002",
            idempotency_key="dispatch-002").as_dict(),
        "record_type": "action_request"})
    return "belongs to run 'run-other'"


def damage_duplicate_identity(store):
    append_line(store, {
        "record": an_action().as_dict(), "record_type": "action_request"})
    return "duplicates action_request identity 'action-001'"


def damage_duplicate_idempotency_key(store):
    append_line(store, {
        "record": an_action(action_id="action-002").as_dict(),
        "record_type": "action_request"})
    return "idempotency_key 'dispatch-001' belongs to both 'action-001' and 'action-002'"


def damage_result_without_its_action(store):
    append_line(store, {
        "record": a_result(receipt_id="result-002", action_id="action-999").as_dict(),
        "record_type": "action_result"})
    return "action result names unknown action 'action-999'"


def damage_envelope_naming_another_run(store):
    path = store.run_path("run-001") / "run.json"
    path.write_bytes(canonical_line(a_run(run_id="run-999").as_dict()).encode("utf-8"))
    return "run directory 'run-001' contains envelope 'run-999'"


def damage_secret_reintroduced_into_the_frozen_config(store):
    poisoned = {**CONFIG, "adapter": {"api_key": "written-secret"}}
    root = store.run_path("run-001")
    (root / "config.json").write_bytes(canonical_line(poisoned).encode("utf-8"))
    (root / "run.json").write_bytes(canonical_line(
        a_run(config_digest=snapshot_digest(poisoned)).as_dict()).encode("utf-8"))
    return "frozen config contains secret-bearing field 'adapter.api_key'"


def damage_journalled_decision_without_its_file(store):
    (store.run_path("run-001") / "decisions" / "decision-001.json").unlink()
    return "decision receipts missing exclusive files: ['decision-001']"


def damage_decision_file_owned_by_another_run(store):
    write_decision_file(store, a_decision(receipt_id="decision-002"))
    path = store.run_path("run-001") / "decisions" / "decision-002.json"
    stray = a_decision(receipt_id="decision-002", run_id="run-other")
    path.write_bytes(canonical_line(
        {"record": stray.as_dict(), "record_type": "decision"}).encode("utf-8"))
    return "decision receipt 'decision-002' belongs to another run"


def damage_decision_filename_disagreeing_with_its_receipt(store):
    write_decision_file(store, a_decision(receipt_id="decision-002"), stem="decision-other")
    return "decision filename 'decision-other' disagrees with 'decision-002'"


def damage_decision_file_edited_after_it_was_written(store):
    write_decision_file(store, a_decision(action="reject"))
    return "decision receipt 'decision-001' disagrees with records.jsonl"


def damage_decision_file_carrying_an_uncontracted_field(store):
    decision = a_decision()
    path = store.run_path("run-001") / "decisions" / "decision-001.json"
    path.write_bytes(canonical_line({
        "record": decision.as_dict(), "record_type": "decision",
        "action": "reject"}).encode("utf-8"))
    return "decision receipt 'decision-001' has non-canonical or uncontracted fields"


@pytest.mark.parametrize("damage", [
    damage_line_from_another_run,
    damage_duplicate_identity,
    damage_duplicate_idempotency_key,
    damage_result_without_its_action,
    damage_envelope_naming_another_run,
    damage_secret_reintroduced_into_the_frozen_config,
    damage_journalled_decision_without_its_file,
    damage_decision_file_owned_by_another_run,
    damage_decision_filename_disagreeing_with_its_receipt,
    damage_decision_file_edited_after_it_was_written,
    damage_decision_file_carrying_an_uncontracted_field,
], ids=lambda call: call.__name__.removeprefix("damage_"))
def test_replay_refuses_durable_bytes_that_break_a_relation_the_run_already_recorded(
        tmp_path, damage):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(an_action())
    store.append(evidence())
    store.append(a_result())
    store.append(a_decision())
    assert [row.kind for row in store.read("run-001").records] == [
        "action_request", "evidence", "action_result", "decision"]

    expected = re.escape(damage(store))
    with pytest.raises(CorruptRun, match=expected):
        store.read("run-001")
    with pytest.raises(CorruptRun, match=expected):
        store.recover("run-001")
    with pytest.raises(StoreError, match=expected):
        store.append(an_action(action_id="action-late", idempotency_key="dispatch-late"))


def test_the_journal_holds_the_exact_bytes_the_store_composed_for_each_record(tmp_path):
    """The durable journal is the canonical record, not the platform's spelling of it.

    `_append_bytes` opened the journal without `O_BINARY`, so on Windows the CRT
    translated every LF on the way out and each appended line landed one CR longer
    than the bytes the store composed. Nothing failed: `bytes.splitlines()` eats
    that CR before the canonicality check, so every replay stayed green while the
    same run directory was not byte-identical between platforms — and `run.json`,
    `config.json` and every `decisions/*.json`, all staged through `mkstemp`,
    which sets the flag, already carried the composed bytes. Two durable spellings
    of one record is one too many when the store's whole argument is durable bytes.

    Held against the canonical line this module spells out for itself rather than
    against a replay: a re-parse cannot tell the two spellings apart, which is
    exactly why this went unnoticed.
    """
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(an_action())
    store.append(evidence())
    journal = (store.run_path("run-001") / "records.jsonl").read_bytes()
    assert journal == (
        canonical_line({"record": an_action().as_dict(), "record_type": "action_request"})
        + canonical_line({"record": evidence().as_dict(), "record_type": "evidence"})
    ).encode("utf-8")
    assert b"\r" not in journal


def test_a_journal_whose_records_end_crlf_replays_and_re_appends_without_a_byte_moving(
        tmp_path):
    """The spelling this store itself left on Windows before it opened the journal binary.

    Until `_append_bytes` passed `O_BINARY`, the CRT translated every LF written
    through that descriptor, so a run recorded by an earlier build carries a
    journal whose every record ends CR LF. Those runs replay today for one reason:
    `bytes.splitlines()` treats CR LF as one terminator and hands the parser the
    same bytes the store composed. Nothing held that reason. Spelling the split as
    `split(b"\\n")` leaves a CR on the end of every line and an empty final element,
    which is corruption on the very first record -- and the whole suite stayed
    green, because every other run in it was written by this build.

    Both halves are held, because a reader that survives is only half of
    compatibility: such a journal must also be recognised as already holding the
    record, so appending it again writes nothing and the old spelling is never
    half-rewritten into the new one under a run nobody asked to convert.
    """
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(an_action())
    store.append(evidence())
    journal = store.run_path("run-001") / "records.jsonl"
    old = journal.read_bytes().replace(b"\n", b"\r\n")
    assert old.count(b"\r\n") == 2 and old != journal.read_bytes()
    journal.write_bytes(old)

    replayed = RunStore(tmp_path).read("run-001")
    assert [row.value for row in replayed.records] == [an_action(), evidence()]
    assert replayed.warnings == ()
    # The retry is recognised through the old spelling, so nothing is appended and
    # the durable bytes are the ones this test found there.
    assert RunStore(tmp_path).append(an_action()) is False
    assert journal.read_bytes() == old


def test_run_path_accepts_only_contract_ids(tmp_path):
    store = RunStore(tmp_path)
    with pytest.raises(StoreError, match="run_id"):
        store.run_path("../outside")
    assert not (Path(tmp_path).parent / "outside").exists()
