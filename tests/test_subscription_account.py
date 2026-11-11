"""Local account provenance survives the real runtime without buying acceptance."""
from dataclasses import replace

import pytest

from conductor.command.artifact_handoff import ArtifactHandoff
from conductor.command.run_store import RecordConflict, RunStore, StoreError
from conductor.command.runtime import AttemptState

from tests.test_command_runtime_authorize import NOW, a_store, counting_ids
from tests.test_command_runtime_execute import VerifiedAdapter, a_runtime, authorized


ACCOUNT_HASH = "sha256:9402266c838d3879b7d2f3ea1c88563b6b6c62a1a396ca07cfd044499ba6acee"
PROOF = {"version": 1, "vendor": "anthropic", "source": "source_relay",
         "status": "local_match", "account_sha256": ACCOUNT_HASH}


def handoff(store):
    return ArtifactHandoff(store, clock=lambda: NOW, ids=counting_ids())


def write_account(writer, request, **changes):
    values = {"actor_instance_id": request.instance_id, "adapter_id": "claude-code",
              "role": "doer", "proof": PROOF}
    values.update(changes)
    return writer.record_subscription_account(request, **values)


def account_rows(store):
    return [row.value for row in store.read("run-001").records
            if row.kind == "evidence" and row.value.kind == "subscription_account_v1"]


def test_public_runtime_keeps_the_local_account_fact_in_its_real_journal(tmp_path):
    store = a_store(tmp_path)

    class Observing(VerifiedAdapter):
        def execute(self, prepared):
            write_account(handoff(store), prepared.request)
            return super().execute(prepared)

    runtime, authorization = authorized(store, Observing(store))
    result = runtime.execute(authorization)
    assert len(account_rows(RunStore(tmp_path))) == 1
    assert result.state is AttemptState.SUCCEEDED


def test_runtime_read_restart_preserves_only_exact_account_provenance(tmp_path, monkeypatch):
    store = a_store(tmp_path)
    writer = handoff(store)

    class Observing(VerifiedAdapter):
        def execute(self, prepared):
            write_account(writer, prepared.request)
            return super().execute(prepared)

    adapter = Observing(store)
    runtime, authorization = authorized(store, adapter)

    def crash_after_observation(*args, **kwargs):
        raise RuntimeError("simulated crash after observation")

    monkeypatch.setattr(runtime, "_resolve", crash_after_observation)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runtime.execute(authorization)
    rows = account_rows(RunStore(tmp_path))
    assert len(rows) == 1
    row = rows[0]
    assert dict(row.extra["proof"]) == PROOF
    assert (row.run_id, row.created_by, row.verification) == (
        "run-001", "claude-code", "unverified")
    request = authorization.request
    assert dict(row.extra["binding"]) == {
        "run_id": request.run_id, "action_id": request.action_id,
        "attempt_id": request.attempt_id, "instance_id": request.instance_id,
        "actor_instance_id": "claude-dev", "adapter_id": "claude-code", "role": "doer"}
    raw_before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    assert b"account-local-Q6" not in raw_before
    restarted = RunStore(tmp_path)
    fresh = VerifiedAdapter(restarted)
    settled = a_runtime(restarted, fresh).execute(authorization)
    assert settled.state is AttemptState.SUCCEEDED
    assert fresh.execute_calls == 0 and fresh.verify_calls == 1
    assert adapter.execute_calls == 1
    assert row.evidence_id not in settled.receipt.evidence_refs
    assert account_rows(restarted)[0].as_dict() == row.as_dict()
    assert write_account(handoff(restarted), request).as_dict() == row.as_dict()
    assert len(account_rows(restarted)) == 1


@pytest.mark.parametrize("change", [
    {"attempt_id": "another-attempt"}, {"instance_id": "codex-review"},
    {"arguments": {"handoff": "foreign"}}, {"action_id": "another-action"},
])
def test_foreign_request_is_refused_before_any_account_bytes(tmp_path, change):
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, VerifiedAdapter(store))
    runtime.execute(authorization)
    request = replace(authorization.request, **change)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    with pytest.raises(StoreError):
        write_account(handoff(store), request)
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before


@pytest.mark.parametrize("changes", [
    {"actor_instance_id": "codex-review"}, {"adapter_id": "codex"},
    {"role": "checker", "actor_instance_id": "codex-review", "adapter_id": "codex"},
    {"role": "checker"},
    {"role": "not-a-role"},
])
def test_foreign_actor_cannot_attach_a_proof(tmp_path, changes):
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, VerifiedAdapter(store))
    runtime.execute(authorization)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    with pytest.raises((StoreError, ValueError)):
        write_account(handoff(store), authorization.request, **changes)
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before


@pytest.mark.parametrize("changes", [
    {"account_sha256": "raw-secret-Q6"}, {"raw_account": "raw-secret-Q6"},
    {"status": "unknown"}, {"version": True}, {"vendor": "raw-secret-Q6"},
    {"source": "server_verified"},
])
def test_malformed_or_raw_proof_is_not_persisted(tmp_path, changes):
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, VerifiedAdapter(store))
    runtime.execute(authorization)
    proof = {**PROOF, **changes}
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    with pytest.raises(ValueError):
        write_account(handoff(store), authorization.request, proof=proof)
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before
    assert b"raw-secret-Q6" not in before


def test_conflicting_proof_cannot_replace_a_recorded_account(tmp_path):
    store = a_store(tmp_path)
    writer = handoff(store)

    class Observing(VerifiedAdapter):
        def execute(self, prepared):
            write_account(writer, prepared.request)
            return super().execute(prepared)

    runtime, authorization = authorized(store, Observing(store))
    runtime.execute(authorization)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    with pytest.raises(RecordConflict):
        write_account(writer, authorization.request,
                      proof={**PROOF, "account_sha256": "sha256:" + "a" * 64})
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before


def test_a_known_adapter_cannot_record_another_vendors_proof(tmp_path):
    store = a_store(tmp_path)
    runtime, authorization = authorized(store, VerifiedAdapter(store))
    runtime.execute(authorization)
    before = store.run_path("run-001").joinpath("records.jsonl").read_bytes()
    with pytest.raises(ValueError):
        write_account(handoff(store), authorization.request, proof={**PROOF, "vendor": "openai"})
    assert store.run_path("run-001").joinpath("records.jsonl").read_bytes() == before


@pytest.mark.parametrize("source,relay", [
    (None, None), ("one", "two"), ("", ""), ("x", None), ("\ud800", "\ud800"),
])
def test_unavailable_account_is_explicitly_unknown(source, relay):
    from conductor.command.subscription_account import make_proof, settled_proof
    assert settled_proof(make_proof("anthropic", source, relay)) == {
        "version": 1, "vendor": "anthropic", "source": "source_relay",
        "status": "unknown", "account_sha256": None}


def test_factory_hashes_only_the_native_id_and_fixed_vendor():
    from conductor.command.subscription_account import (
        make_proof, normalize_vendor, settled_proof)
    proof = make_proof(normalize_vendor("Anthropic"), "account-local-Q6", "account-local-Q6")
    assert settled_proof(proof) == PROOF
    assert "account-local-Q6" not in repr(proof)
    assert [normalize_vendor(name) for name in ("OpenAI", "xAI", "Moonshot AI")] == [
        "openai", "xai", "moonshot"]
    with pytest.raises(ValueError):
        normalize_vendor("raw-secret-Q6")


def test_checker_actor_is_the_frozen_independent_participant(tmp_path):
    from tests.test_command_independent_runtime import circuit
    from tests.test_command_runtime_authorize import a_budget, a_confirmation
    store, doer, checker, _, runtime, proposal = circuit(tmp_path)
    original = checker.verify_for
    original_execute = doer.execute

    def observing_doer(prepared):
        write_account(handoff(store), prepared.request)
        return original_execute(prepared)

    def observing(request, result, verifier, material):
        write_account(handoff(store), request, actor_instance_id=verifier.instance_id,
                      adapter_id=verifier.adapter_id, role="checker",
                      proof={**PROOF, "vendor": "openai"})
        return original(request, result, verifier, material)

    checker.verify_for = observing
    doer.execute = observing_doer
    # Registry freezes its callable boundary; rebuild it with this fake checker.
    from conductor.command.adapters import AdapterRegistry
    from conductor.command.runtime import ControlRuntime
    from tests.test_command_runtime_authorize import fixed_clock, fixed_ids
    runtime = ControlRuntime(store, AdapterRegistry([doer, checker]),
                             clock=fixed_clock(), ids=fixed_ids())
    result = runtime.execute(runtime.authorize(a_confirmation(proposal), budget=a_budget()))
    assert result.state is AttemptState.SUCCEEDED
    rows = account_rows(RunStore(tmp_path))
    assert len(rows) == 2
    actors = {row.extra["binding"]["role"]: row for row in rows}
    assert actors["checker"].extra["binding"]["actor_instance_id"] == "codex-review"
    assert actors["doer"].extra["binding"]["actor_instance_id"] == "claude-dev"
    assert all(row.evidence_id not in result.receipt.evidence_refs for row in rows)
