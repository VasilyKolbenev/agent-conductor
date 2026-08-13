"""Strict common value contracts for future deep adapters."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from conductor.command.adapters.deep_commands import (
    DeepCommandSpec,
    DeepDispatchArgs,
    DeepEvidenceArgs,
    DeepReviewArgs,
    DeepRetryArgs,
    DeepStopArgs,
    DeepSwitchArgs,
)
from conductor.command.adapters.deep_contracts import (
    AdapterFailure,
    AdapterRecovery,
    DeepAdapterConfig,
    DeepContractError,
    DeepProtocol,
    NormalizedResult,
    RecoveryRef,
)
from conductor.command.adapters.deep_evidence import AdapterEvidence


NOW = "2026-08-13T20:00:00Z"
DIGEST = "sha256:" + "a" * 64


def failure(**changes):
    values = {"code": "lost_result", "phase": "execute", "retryable": True}
    values.update(changes)
    return AdapterFailure(**values)


def result(**changes):
    values = {
        "run_id": "run-001", "action_id": "action-001",
        "attempt_id": "attempt-001", "instance_id": "claude-dev",
        "adapter_id": "deep-claude", "outcome": "succeeded",
        "observed_at": NOW, "exit_code": 0, "failure": None,
    }
    values.update(changes)
    return NormalizedResult(**values)


def recovery_ref(**changes):
    values = {"scheme": "fake-ledger-v1", "adapter_id": "deep-claude",
              "action_id": "action-001", "digest": DIGEST}
    values.update(changes)
    return RecoveryRef(**values)


@pytest.mark.parametrize("value", [
    DeepAdapterConfig("C:/fake/claude.exe", DeepProtocol.FAKE_CLAUDE_V1, ["PATH"]),
    recovery_ref(), failure(), result(),
    AdapterRecovery(
        "run-001", "action-001", "attempt-001", "claude-dev", "deep-claude",
        recovery_ref(), "succeeded", result()),
    AdapterEvidence(
        "evidence-001", "run-001", "action-001", "attempt-001", "claude-dev",
        "deep-claude", "diff", "artifact-001", DIGEST, NOW, "verified", NOW),
])
def test_values_are_frozen_and_exact_roundtrip(value):
    assert type(value).from_dict(value.as_dict()) == value
    with pytest.raises(FrozenInstanceError):
        value.anything = "changed"
    with pytest.raises(DeepContractError, match="extra"):
        type(value).from_dict({**value.as_dict(), "secret": "APIKEY"})


@pytest.mark.parametrize("field", ["pid", "path", "token", "credential", "secret"])
def test_recovery_ref_is_digest_only_authority_without_machine_or_secret_fields(field):
    with pytest.raises(DeepContractError, match="extra"):
        RecoveryRef.from_dict({**recovery_ref().as_dict(), field: "APIKEY-secret"})


@pytest.mark.parametrize("code", [
    "invalid_arguments", "executable_unavailable", "spawn_refused", "timeout",
    "stopped", "protocol_error", "output_limit", "lost_result",
    "recovery_unavailable", "identity_mismatch", "evidence_unavailable",
    "evidence_mismatch", "ownership_lost", "unsupported",
])
def test_adapter_failure_exact_reviewed_code_vocabulary(code):
    assert failure(code=code).code == code


@pytest.mark.parametrize("bad", ["unavailable", "cancelled", "effect_unknown", "APIKEY"])
def test_adapter_failure_has_no_free_text_or_unreviewed_code(bad):
    with pytest.raises(DeepContractError):
        failure(code=bad)


@pytest.mark.parametrize("field", [
    "run_id", "action_id", "attempt_id", "instance_id", "adapter_id",
])
def test_recovery_result_must_keep_every_identity(field):
    recovered = {
        "run_id": "run-001", "action_id": "action-001",
        "attempt_id": "attempt-001", "instance_id": "claude-dev",
        "adapter_id": "deep-claude", "recovery_ref": recovery_ref(),
        "state": "succeeded", "result": result(),
    }
    recovered[field] = f"foreign-{field}"
    with pytest.raises(DeepContractError):
        AdapterRecovery(**recovered)


@pytest.mark.parametrize("state,outcome", [
    ("succeeded", "succeeded"), ("failed", "failed"),
    ("failed", "rejected"), ("cancelled", "cancelled"),
    ("unknown", "unknown"),
])
def test_terminal_recovery_state_is_exactly_bound_to_normalized_result(state, outcome):
    normalized = result(
        outcome=outcome, exit_code=None,
        failure=None if outcome == "succeeded" else failure())
    recovered = AdapterRecovery(
        "run-001", "action-001", "attempt-001", "claude-dev", "deep-claude",
        recovery_ref(), state, normalized)
    assert AdapterRecovery.from_dict(recovered.as_dict()) == recovered


def test_running_recovery_claims_no_result_and_real_mode_is_unavailable():
    recovered = AdapterRecovery(
        "run-001", "action-001", "attempt-001", "claude-dev", "deep-claude",
        recovery_ref(), "running", None)
    assert recovered.result is None
    with pytest.raises(DeepContractError, match="real_mode"):
        DeepAdapterConfig("/fake/claude", "fake-claude-jsonl-v1", real_mode="ready")


@pytest.mark.parametrize("executable", ["claude", "bin/claude", "", 3])
def test_config_requires_absolute_configured_executable_without_touching_fs(executable):
    with pytest.raises(DeepContractError):
        DeepAdapterConfig(executable, "fake-claude-jsonl-v1")


def test_config_does_not_probe_the_absolute_executable(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda path: (_ for _ in ()).throw(
        AssertionError("config probed filesystem")))
    assert DeepAdapterConfig("/definitely/absent", "fake-codex-jsonl-v1").executable


@pytest.mark.parametrize("changes", [
    {"protocol": "APIKEY-secret"},
    {"env_allow": 7},
    {"env_allow": ["PATH", "PATH"]},
])
def test_config_normalizes_invalid_protocol_and_env_shapes(changes):
    values = {"executable": "/fake/claude", "protocol": "fake-claude-jsonl-v1"}
    values.update(changes)
    with pytest.raises(DeepContractError) as stopped:
        DeepAdapterConfig(**values)
    assert "APIKEY" not in repr(stopped.value)
    assert stopped.value.__cause__ is None


def test_evidence_is_structured_and_carries_no_raw_label_or_output_field():
    evidence = AdapterEvidence(
        "evidence-001", "run-001", "action-001", "attempt-001", "claude-dev",
        "deep-claude", "status", "artifact-001", DIGEST, NOW, "unavailable", None)
    assert set(evidence.as_dict()) == AdapterEvidence._FIELDS
    for field in ("label", "output", "stdout", "stderr", "detail"):
        with pytest.raises(DeepContractError):
            AdapterEvidence.from_dict({**evidence.as_dict(), field: "APIKEY-secret"})


@pytest.mark.parametrize("value", [
    DeepDispatchArgs("work-001", "instruction-001", "implement", (), "small"),
    DeepReviewArgs("work-001", ("artifact-001",), "security"),
    DeepEvidenceArgs("action-001", ("result", "tests")),
    DeepStopArgs("attempt-001", "switch"),
    DeepRetryArgs("action-001", "verification_failed"),
    DeepSwitchArgs("action-001", "codex-review", "handoff-001"),
])
def test_each_capability_argument_is_closed_and_roundtrips(value):
    assert type(value).from_dict(value.as_dict()) == value
    for forbidden in ("argv", "cwd", "path", "env", "executable", "pid", "token"):
        with pytest.raises(DeepContractError):
            type(value).from_dict({**value.as_dict(), forbidden: "APIKEY-secret"})


def test_command_spec_is_code_owned_argv_with_fixed_cwd_and_no_shell_suffix():
    config = DeepAdapterConfig(
        "C:/fake/codex.exe", "fake-codex-jsonl-v1", ["PATH", "OPENAI_API_KEY"])
    spec = DeepCommandSpec.from_config(config, timeout_seconds=90)
    assert spec.argv == ("C:/fake/codex.exe", "--fake-codex-jsonl-v1")
    assert spec.cwd == "." and spec.env_allow == ("PATH", "OPENAI_API_KEY")
    assert spec.output_profile == "bounded-jsonl-v1" and spec.timeout_seconds == 90
    with pytest.raises(DeepContractError, match="code-owned"):
        DeepCommandSpec(("sh", "-c", "APIKEY"), ".", (), "whole", 1)
