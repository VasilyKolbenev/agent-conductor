"""RT-2 restart safety: durable boundaries never grant a second effect."""
from __future__ import annotations

import pytest

from conductor.command.attempts import AttemptEvent, action_request_digest
from conductor.command.contracts import canonical_json
from conductor.command.run_store import CorruptRun, RunStore
from conductor.command.runtime import AttemptState

from tests.test_command_runtime_execute import (
    ScriptedAdapter,
    a_runtime,
    authorized,
)
from tests.test_command_runtime_authorize import NOW, a_store


def attempt_events(store):
    return [
        row.value for row in store.read("run-001").records
        if row.kind == "attempt_event"
    ]


def append_raw(store, event):
    journal = store.run_path("run-001") / "records.jsonl"
    wrapper = {"record_type": "attempt_event", "record": event.as_dict()}
    with journal.open("ab") as stream:
        stream.write(canonical_json(wrapper).encode("utf-8") + b"\n")


def an_event(request, phase="effect_lease", **changes):
    observed = phase == "execution_observed"
    values = {
        "event_id": "event-observed" if observed else "event-lease",
        "run_id": request.run_id, "action_id": request.action_id,
        "attempt_id": request.attempt_id, "instance_id": request.instance_id,
        "adapter_id": "claude-code", "phase": phase, "recorded_at": NOW,
        "request_digest": action_request_digest(request),
        "recovery_ref": "recovery-restart", "schema_version": 2,
        "outcome": "succeeded" if observed else None,
        "exit_code": 0 if observed else None,
    }
    values.update(changes)
    return AttemptEvent(**values)


def test_effect_lease_is_durable_before_the_adapter_effect(tmp_path):
    store = a_store(tmp_path)

    class Witness(ScriptedAdapter):
        def execute(self, prepared):
            self.lease_visible = [
                row.phase for row in attempt_events(store)] == ["effect_lease"]
            return super().execute(prepared)

    adapter = Witness()
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.SUCCEEDED
    assert adapter.lease_visible is True
    assert [row.phase for row in attempt_events(store)] == [
        "effect_lease", "execution_observed"]
    assert adapter.execute_calls == 1


def test_restart_after_lease_before_effect_records_unknown_without_execute(
        tmp_path, monkeypatch):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    monkeypatch.setattr(
        runtime, "_observe_execute",
        lambda *args: (_ for _ in ()).throw(RuntimeError("crash after lease")))
    with pytest.raises(RuntimeError, match="crash after lease"):
        runtime.execute(authorization)
    assert adapter.execute_calls == 0
    assert [row.phase for row in attempt_events(store)] == ["effect_lease"]

    fresh = ScriptedAdapter()
    attempt = a_runtime(RunStore(tmp_path), fresh).execute(authorization)
    assert attempt.state is AttemptState.UNKNOWN
    assert fresh.prepare_calls == fresh.execute_calls == fresh.verify_calls == 0
    assert [row.phase for row in attempt_events(store)] == ["effect_lease"]


def test_restart_after_effect_before_observation_never_repeats_marker(
        tmp_path, monkeypatch):
    marker = tmp_path / "effect-marker"

    class MarkingAdapter(ScriptedAdapter):
        def execute(self, prepared):
            marker.write_text(marker.read_text() + "x" if marker.exists() else "x")
            return super().execute(prepared)

    store = a_store(tmp_path)
    adapter = MarkingAdapter()
    runtime, authorization = authorized(store, adapter)
    append_event = runtime._append_event

    def crash_on_observed(*args, **kwargs):
        if kwargs.get("phase") == "execution_observed":
            raise RuntimeError("crash after effect")
        return append_event(*args, **kwargs)

    monkeypatch.setattr(runtime, "_append_event", crash_on_observed)
    with pytest.raises(RuntimeError, match="crash after effect"):
        runtime.execute(authorization)
    assert marker.read_text() == "x"
    assert [row.phase for row in attempt_events(store)] == ["effect_lease"]

    fresh = ScriptedAdapter()
    attempt = a_runtime(RunStore(tmp_path), fresh).execute(authorization)
    assert attempt.state is AttemptState.UNKNOWN
    assert marker.read_text() == "x"
    assert fresh.prepare_calls == fresh.execute_calls == fresh.verify_calls == 0


def test_observed_restart_is_verify_only_and_events_are_exactly_once(
        tmp_path, monkeypatch):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter()
    runtime, authorization = authorized(store, adapter)
    monkeypatch.setattr(
        runtime, "_resolve",
        lambda *args: (_ for _ in ()).throw(RuntimeError("crash after observed")))
    with pytest.raises(RuntimeError, match="crash after observed"):
        runtime.execute(authorization)
    assert adapter.execute_calls == 1
    assert [row.phase for row in attempt_events(store)] == [
        "effect_lease", "execution_observed"]

    fresh = ScriptedAdapter()
    recovered = a_runtime(RunStore(tmp_path), fresh).execute(authorization)
    assert recovered.state is AttemptState.SUCCEEDED
    assert fresh.prepare_calls == fresh.execute_calls == 0
    assert fresh.verify_calls == 1
    before = (store.run_path("run-001") / "records.jsonl").read_bytes()
    replay_adapter = ScriptedAdapter()
    replayed = a_runtime(RunStore(tmp_path), replay_adapter).execute(authorization)
    assert replayed.receipt == recovered.receipt
    assert replay_adapter.prepare_calls == replay_adapter.execute_calls == 0
    assert replay_adapter.verify_calls == 0
    assert (store.run_path("run-001") / "records.jsonl").read_bytes() == before
    assert [row.phase for row in attempt_events(store)] == [
        "effect_lease", "execution_observed"]


@pytest.mark.parametrize("field,foreign", [
    ("run_id", "run-foreign"),
    ("action_id", "action-foreign"),
    ("attempt_id", "attempt-foreign"),
    ("adapter_id", "adapter-foreign"),
    ("request_digest", "sha256:" + "0" * 64),
])
def test_tampered_lease_identity_refuses_before_every_adapter_seam(
        tmp_path, field, foreign):
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, ScriptedAdapter())
    append_raw(store, an_event(authorization.request, **{field: foreign}))
    journal = store.run_path("run-001") / "records.jsonl"
    before = journal.read_bytes()
    adapter = ScriptedAdapter()
    with pytest.raises(CorruptRun):
        a_runtime(RunStore(tmp_path), adapter).execute(authorization)
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    assert journal.read_bytes() == before


def test_tampered_observed_recovery_ref_refuses_before_every_adapter_seam(tmp_path):
    store = a_store(tmp_path)
    _, authorization = authorized(store, ScriptedAdapter())
    store.append(an_event(authorization.request))
    append_raw(store, an_event(
        authorization.request, "execution_observed",
        recovery_ref="recovery-foreign"))
    journal = store.run_path("run-001") / "records.jsonl"
    before = journal.read_bytes()
    adapter = ScriptedAdapter()
    with pytest.raises(CorruptRun):
        a_runtime(RunStore(tmp_path), adapter).execute(authorization)
    assert adapter.prepare_calls == adapter.execute_calls == adapter.verify_calls == 0
    assert journal.read_bytes() == before


def test_adapter_reconciliation_outcome_is_observed_as_unknown(tmp_path):
    store = a_store(tmp_path)
    adapter = ScriptedAdapter(execute_outcome="verification_failed")
    runtime, authorization = authorized(store, adapter)
    attempt = runtime.execute(authorization)
    assert attempt.state is AttemptState.UNKNOWN
    observed = attempt_events(store)[1]
    assert observed.outcome == "unknown" and observed.exit_code is None
    assert adapter.verify_calls == 0
