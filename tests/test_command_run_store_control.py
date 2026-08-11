"""Run-store append and replay for proposals and durable observations.

These records carry no execution. A proposal is bound to the frozen config of
its run; an observation never crosses a run boundary; an identical repeat is a
no-op and a reused id with new facts is a conflict; corruption is refused, never
skipped. Every relation is checked before a durable byte is written, and again
on replay from bytes another process could have written.
"""
from __future__ import annotations

import json
import re

import pytest

from conductor.command.contracts import ActionProposal, ObservationRecord
from conductor.command.run_store import (
    CorruptRun,
    RecordConflict,
    RunStore,
    StoreError,
    snapshot_digest,
)

from tests.test_command_run_store import CONFIG, a_run


NOW = "2026-08-11T09:00:00Z"


def a_proposal(**changes):
    values = {
        "proposal_id": "proposal-001",
        "run_id": "run-001",
        "attempt_id": "attempt-001",
        "instance_id": "claude-dev",
        "capability": "dispatch",
        "arguments": {"handoff": "packet-001"},
        "scope": ("src",),
        "proposed_by": "claude-dev",
        "proposed_at": NOW,
        "timeout_seconds": 900,
        "rationale": "The lane finished its handoff and asks to dispatch review.",
        "config_digest": snapshot_digest(CONFIG),
    }
    values.update(changes)
    return ActionProposal(**values)


def an_observation(**changes):
    values = {
        "observation_id": "observation-001",
        "run_id": "run-001",
        "adapter_id": "claude-code",
        "instance_id": "claude-dev",
        "observed_at": NOW,
        "health": "ready",
        "available_capabilities": ("observe", "dispatch"),
        "detail": "Connected through the configured transport.",
    }
    values.update(changes)
    return ObservationRecord(**values)


def canonical_line(wrapper):
    return json.dumps(
        wrapper, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def append_line(store, wrapper):
    with (store.run_path("run-001") / "records.jsonl").open("ab") as stream:
        stream.write(canonical_line(wrapper).encode("utf-8"))


def test_a_proposal_and_an_observation_append_and_replay_in_causal_order(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    assert store.append(an_observation()) is True
    assert store.append(a_proposal()) is True

    recovered = store.recover("run-001")
    assert [row.kind for row in recovered.records] == [
        "adapter_observation", "action_proposal"]
    assert recovered.records[0].value == an_observation()
    assert recovered.records[1].value == a_proposal()


def test_an_identical_proposal_repeat_is_a_no_op_and_a_reused_id_conflicts(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    assert store.append(a_proposal()) is True
    assert store.append(a_proposal()) is False
    with pytest.raises(RecordConflict, match="proposal-001"):
        store.append(a_proposal(arguments={"handoff": "packet-changed"}))
    assert len(store.recover("run-001").records) == 1


def test_an_identical_observation_repeat_is_a_no_op_and_a_reused_id_conflicts(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    assert store.append(an_observation()) is True
    assert store.append(an_observation()) is False
    with pytest.raises(RecordConflict, match="observation-001"):
        store.append(an_observation(health="offline"))
    assert len(store.recover("run-001").records) == 1


def test_a_proposal_must_bind_to_the_frozen_config_of_its_run(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    with pytest.raises(StoreError, match="config_digest"):
        store.append(a_proposal(config_digest="sha256:" + "f" * 64))
    assert store.recover("run-001").records == ()


def test_an_observation_never_falls_back_to_another_run_when_its_run_is_missing(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    with pytest.raises(StoreError, match="run 'run-other' does not exist"):
        store.append(an_observation(run_id="run-other"))


def test_an_observation_survives_a_fresh_store_process_with_its_unknown_intact(tmp_path):
    writer = RunStore(tmp_path)
    writer.create_run(a_run(), CONFIG)
    born = ObservationRecord.from_dict({
        **an_observation(health="unknown", available_capabilities=()).as_dict(),
        "future": {"probe": ["kept"]},
    })
    assert writer.append(born) is True

    reader = RunStore(tmp_path)  # a second process holds no in-memory state
    replayed = reader.read("run-001").records
    assert [row.value for row in replayed] == [born]
    assert replayed[0].value.health == "unknown"
    assert replayed[0].value.as_dict()["future"] == {"probe": ["kept"]}


def test_replay_refuses_a_proposal_bound_to_another_runs_config(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    stray = a_proposal(config_digest="sha256:" + "f" * 64)
    append_line(store, {"record": stray.as_dict(), "record_type": "action_proposal"})
    expected = re.escape("proposal config_digest does not match the frozen run")
    with pytest.raises(CorruptRun, match=expected):
        store.read("run-001")


def test_replay_refuses_an_observation_from_another_run(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    stray = an_observation(run_id="run-other")
    append_line(store, {"record": stray.as_dict(), "record_type": "adapter_observation"})
    with pytest.raises(CorruptRun, match="belongs to run 'run-other'"):
        store.read("run-001")


def test_replay_refuses_a_proposal_whose_field_was_edited_under_a_stale_digest(tmp_path):
    store = RunStore(tmp_path)
    store.create_run(a_run(), CONFIG)
    store.append(a_proposal())
    journal = store.run_path("run-001") / "records.jsonl"
    tampered = journal.read_bytes().replace(b"packet-001", b"packet-999")
    assert tampered != journal.read_bytes()
    journal.write_bytes(tampered)
    with pytest.raises(CorruptRun, match="records.jsonl line 1 is invalid"):
        store.read("run-001")
