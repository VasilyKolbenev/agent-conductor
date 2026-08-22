"""Strict common value contracts for future deep adapters."""
from __future__ import annotations

import ast
import importlib
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from conductor.command.adapters.deep_commands import (
    DEEP_ARGUMENT_TYPES,
    DEEP_OUTPUT_LIMIT,
    DEEP_PROTOCOL_FLAGS,
    DISPATCH_PROFILES,
    OUTPUT_LIMIT_PROFILES,
    REQUESTED_EVIDENCE_KINDS,
    RETRY_REASONS,
    REVIEW_PROFILES,
    STOP_REASONS,
    DeepCommandSpec,
    DeepDispatchArgs,
    DeepEvidenceArgs,
    DeepRetryArgs,
    DeepReviewArgs,
    DeepStopArgs,
    DeepSwitchArgs,
)
from conductor.command.adapters.deep_contracts import (
    ADAPTER_FAILURE_CODES,
    ADAPTER_FAILURE_PHASES,
    OBSERVED_OUTCOMES,
    RECOVERY_OUTCOMES,
    RECOVERY_STATES,
    AdapterFailure,
    AdapterRecovery,
    DeepAdapterConfig,
    DeepContractError,
    DeepProtocol,
    NormalizedResult,
    RecoveryRef,
)
from conductor.command.adapters.deep_evidence import (
    EVIDENCE_KINDS,
    EVIDENCE_VERIFICATIONS,
    AdapterEvidence,
)
from conductor.command.adapters.process import ProcessRunner

NOW = "2026-08-13T20:00:00Z"
DIGEST = "sha256:" + "a" * 64


class _HostileList(list):
    iterated = compared = False

    def __iter__(self):
        type(self).iterated = True
        raise RuntimeError("APIKEY_SECRET_ITERATOR")

    def __eq__(self, _other):
        type(self).compared = True
        raise RuntimeError("APIKEY_SECRET_EQUALITY")


class _HostileTuple(tuple):
    iterated = compared = False

    def __iter__(self):
        type(self).iterated = True
        raise RuntimeError("APIKEY_SECRET_ITERATOR")

    def __eq__(self, _other):
        type(self).compared = True
        raise RuntimeError("APIKEY_SECRET_EQUALITY")


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
    assert spec.cwd == "work" and spec.env_allow == ("PATH", "OPENAI_API_KEY")
    assert spec.output_profile == "bounded-jsonl-v1" and spec.timeout_seconds == 90
    with pytest.raises(DeepContractError, match="two-value tuple"):
        DeepCommandSpec(("sh", "-c", "APIKEY"), ".", (), "whole", 1)


def test_all_deep_vocabularies_and_protocol_flags_are_exactly_pinned():
    assert set(DeepProtocol) == {
        DeepProtocol.FAKE_CLAUDE_V1, DeepProtocol.FAKE_CODEX_V1,
        DeepProtocol.DSH_HEADLESS_V1, DeepProtocol.KIMI_HEADLESS_V1,
        DeepProtocol.GROK_HEADLESS_V1, DeepProtocol.CLAUDE_HEADLESS_V1,
        DeepProtocol.CODEX_HEADLESS_V1}
    assert dict(DEEP_PROTOCOL_FLAGS) == {
        "fake-claude-jsonl-v1": "--fake-claude-jsonl-v1",
        "fake-codex-jsonl-v1": "--fake-codex-jsonl-v1",
    }
    # The five real tokens are reviewed vocabulary, not deep fake protocols:
    # none binds a deep argv flag, so the fake-protocol command builder can
    # never render any of them. `codex-headless-v1` joined this set when Codex
    # CLI became a real transport, and NEITHER fake token retired beside it --
    # both fake protocols are still the families the `_DeepAdapter` lifecycle
    # suites drive, and neither is catalogued any more.
    non_deep = {DeepProtocol.DSH_HEADLESS_V1, DeepProtocol.KIMI_HEADLESS_V1,
        DeepProtocol.GROK_HEADLESS_V1, DeepProtocol.CLAUDE_HEADLESS_V1,
        DeepProtocol.CODEX_HEADLESS_V1}
    for protocol in non_deep:
        assert protocol.value not in DEEP_PROTOCOL_FLAGS
    assert set(DEEP_PROTOCOL_FLAGS) == {
        protocol.value for protocol in DeepProtocol if protocol not in non_deep}
    assert OBSERVED_OUTCOMES == {
        "succeeded", "failed", "cancelled", "rejected", "unknown"}
    assert ADAPTER_FAILURE_CODES == {
        "invalid_arguments", "executable_unavailable", "spawn_refused", "timeout",
        "stopped", "protocol_error", "output_limit", "lost_result",
        "recovery_unavailable", "identity_mismatch", "evidence_unavailable",
        "evidence_mismatch", "ownership_lost", "unsupported"}
    assert ADAPTER_FAILURE_PHASES == {
        "prepare", "execute", "observe", "verify", "recover", "stop"}
    assert RECOVERY_STATES == {
        "running", "succeeded", "failed", "cancelled", "unknown"}
    assert dict(RECOVERY_OUTCOMES) == {
        "succeeded": {"succeeded"}, "failed": {"failed", "rejected"},
        "cancelled": {"cancelled"}, "unknown": {"unknown"}}
    assert EVIDENCE_KINDS == {"result", "diff", "tests", "status"}
    assert EVIDENCE_VERIFICATIONS == {
        "verified", "unavailable", "mismatch", "error"}
    assert DISPATCH_PROFILES == {"implement", "review"}
    assert OUTPUT_LIMIT_PROFILES == {"small", "normal"}
    assert REVIEW_PROFILES == {"quality", "security", "spec"}
    assert REQUESTED_EVIDENCE_KINDS == {"result", "diff", "tests", "status"}
    assert STOP_REASONS == {"user", "timeout", "switch"}
    assert RETRY_REASONS == {"failed", "unknown", "verification_failed", "user"}


def test_public_deep_schema_authority_names_each_exact_argument_base_type():
    expected_types = {
        "dispatch": DeepDispatchArgs, "review": DeepReviewArgs,
        "evidence": DeepEvidenceArgs, "stop": DeepStopArgs,
        "retry": DeepRetryArgs, "switch": DeepSwitchArgs,
    }
    assert dict(DEEP_ARGUMENT_TYPES) == expected_types
    assert {
        capability: value._FIELDS for capability, value in DEEP_ARGUMENT_TYPES.items()
    } == {
        "dispatch": {
            "work_item_id", "instruction_ref", "profile", "artifact_refs",
            "output_limit_profile"},
        "review": {"work_item_id", "target_artifact_refs", "review_profile"},
        "evidence": {"target_action_id", "kinds"},
        "stop": {"target_attempt_id", "reason"},
        "retry": {"prior_action_id", "reason"},
        "switch": {"prior_action_id", "target_instance_id", "handoff_ref"},
    }
    with pytest.raises(TypeError):
        DEEP_ARGUMENT_TYPES["future"] = DeepDispatchArgs


@pytest.mark.parametrize("value,array_field", [
    (DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1"), "env_allow"),
    (DeepDispatchArgs("work", "instruction", "review", (), "normal"),
     "artifact_refs"),
    (DeepReviewArgs("work", ("artifact",), "quality"), "target_artifact_refs"),
    (DeepEvidenceArgs("action", ("result",)), "kinds"),
])
def test_from_dict_requires_json_arrays_while_constructors_accept_immutable_tuples(
        value, array_field):
    data = value.as_dict()
    data[array_field] = tuple(data[array_field])
    with pytest.raises(DeepContractError, match="JSON array"):
        type(value).from_dict(data)


@pytest.mark.parametrize("value,array_field", [
    (DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1"), "env_allow"),
    (DeepDispatchArgs("work", "instruction", "review", (), "normal"),
     "artifact_refs"),
    (DeepReviewArgs("work", ("artifact",), "quality"), "target_artifact_refs"),
    (DeepEvidenceArgs("action", ("result",)), "kinds"),
])
def test_from_dict_rejects_hostile_json_array_subclasses_before_iteration(
        value, array_field):
    class HostileList(list):
        iterated = False

        def __iter__(self):
            type(self).iterated = True
            raise RuntimeError("APIKEY_SECRET_ITERATOR")

    data = value.as_dict()
    data[array_field] = HostileList(data[array_field])
    with pytest.raises(DeepContractError, match="JSON array") as stopped:
        type(value).from_dict(data)
    assert not HostileList.iterated
    assert stopped.value.__cause__ is None and stopped.value.__context__ is None


@pytest.mark.parametrize("base", [
    DeepDispatchArgs, DeepReviewArgs, DeepEvidenceArgs,
    DeepStopArgs, DeepRetryArgs, DeepSwitchArgs,
])
def test_argument_from_dict_reconstructs_only_the_exact_public_base_type(base):
    class Hostile(base):
        pass

    sample = {
        DeepDispatchArgs: DeepDispatchArgs("work", "instruction", "review", [], "small"),
        DeepReviewArgs: DeepReviewArgs("work", ["artifact"], "quality"),
        DeepEvidenceArgs: DeepEvidenceArgs("action", ["result"]),
        DeepStopArgs: DeepStopArgs("attempt", "user"),
        DeepRetryArgs: DeepRetryArgs("action", "failed"),
        DeepSwitchArgs: DeepSwitchArgs("action", "instance", "handoff"),
    }[base]
    assert type(base.from_dict(sample.as_dict())) is base
    with pytest.raises(DeepContractError, match="exact base type"):
        Hostile.from_dict(sample.as_dict())


def test_command_spec_revalidates_every_fact_and_rederives_config_before_runner_use(
        tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    config = DeepAdapterConfig(
        sys.executable, "fake-claude-jsonl-v1", ["PATH"])
    spec = DeepCommandSpec.from_config(config, timeout_seconds=10)
    runner_spec = spec.to_runner_spec(config)
    assert runner_spec.argv == (sys.executable, "--fake-claude-jsonl-v1")
    assert runner_spec.cwd == "work" and runner_spec.output_limit == DEEP_OUTPUT_LIMIT
    runner = ProcessRunner(tmp_path, environ={"PATH": "reviewed-path"})
    outcome = runner.run(runner_spec)
    assert outcome.status == "completed" and runner.active_tokens() == ()

    foreign = DeepAdapterConfig(sys.executable, "fake-codex-jsonl-v1", ["PATH"])
    with pytest.raises(DeepContractError, match="does not equal"):
        spec.to_runner_spec(foreign)
    object.__setattr__(spec, "cwd", ".")
    with pytest.raises(DeepContractError, match="does not equal"):
        spec.to_runner_spec(config)


def test_command_spec_from_config_reconstructs_exact_values_without_hostile_behavior():
    class EvilSpec(DeepCommandSpec):
        pass

    class HostileProtocol:
        @property
        def value(self):
            raise RuntimeError("APIKEY_SECRET_PROTOCOL")

    class HostileExecutable(str):
        def __fspath__(self):
            raise RuntimeError("APIKEY_SECRET_EXECUTABLE")

    config = DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1")
    assert type(DeepCommandSpec.from_config(config, timeout_seconds=10)) is DeepCommandSpec
    with pytest.raises(DeepContractError, match="exact spec base type") as stopped:
        EvilSpec.from_config(config, timeout_seconds=10)
    assert stopped.value.__cause__ is None and stopped.value.__context__ is None
    for field, hostile in (
            ("protocol", HostileProtocol()),
            ("executable", HostileExecutable("C:/fake/tool.exe")),
            ("env_allow", _HostileTuple(["PATH"]))):
        mutated = DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1")
        object.__setattr__(mutated, field, hostile)
        with pytest.raises(DeepContractError) as stopped:
            DeepCommandSpec.from_config(mutated, timeout_seconds=10)
        assert str(stopped.value) == "from_config requires a canonical DeepAdapterConfig"
        graph = repr((stopped.value, stopped.value.__cause__, stopped.value.__context__))
        assert "APIKEY_SECRET" not in graph
        assert stopped.value.__cause__ is None and stopped.value.__context__ is None
    assert not _HostileTuple.iterated and not _HostileTuple.compared


@pytest.mark.parametrize("changes", [
    {"argv": ("C:/fake/tool.exe", "--future-protocol")},
    {"cwd": "."}, {"cwd": "../work"}, {"env_allow": ("BAD-NAME",)},
    {"output_profile": "whole-output"}, {"timeout_seconds": True},
])
def test_public_command_spec_constructor_cannot_bypass_structural_invariants(changes):
    values = {
        "argv": ("C:/fake/tool.exe", "--fake-claude-jsonl-v1"),
        "cwd": "work", "env_allow": (), "output_profile": "bounded-jsonl-v1",
        "timeout_seconds": 10,
    }
    values.update(changes)
    with pytest.raises(DeepContractError):
        DeepCommandSpec(**values)


def test_command_spec_subclass_cannot_override_comparison_authority():
    class HostileSpec(DeepCommandSpec):
        def __eq__(self, _other):
            return True

    config = DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1")
    hostile = HostileSpec(
        ("C:/fake/tool.exe", "--fake-claude-jsonl-v1"), "work", (),
        "bounded-jsonl-v1", 10)
    with pytest.raises(DeepContractError, match="exact spec base type"):
        hostile.to_runner_spec(config)


def test_public_from_dict_rejects_mapping_subclasses_without_reading_hostile_values():
    class HostileDict(dict):
        def __iter__(self):
            raise RuntimeError("APIKEY_SECRET_ITERATOR")

    with pytest.raises(DeepContractError) as stopped:
        RecoveryRef.from_dict(HostileDict(recovery_ref().as_dict()))
    graph = repr((stopped.value, stopped.value.__cause__, stopped.value.__context__))
    assert "APIKEY" not in graph


def test_nested_value_subclasses_cannot_cross_exact_public_contract_boundaries():
    class HostileFailure(AdapterFailure):
        pass

    class HostileRef(RecoveryRef):
        pass

    hostile_failure = HostileFailure("lost_result", "execute", True)
    with pytest.raises(DeepContractError, match="closed AdapterFailure"):
        result(outcome="unknown", exit_code=None, failure=hostile_failure)
    hostile_ref = HostileRef(
        "fake-ledger-v1", "deep-claude", "action-001", DIGEST)
    with pytest.raises(DeepContractError, match="RecoveryRef"):
        AdapterRecovery(
            "run-001", "action-001", "attempt-001", "claude-dev", "deep-claude",
            hostile_ref, "running", None)


@pytest.mark.parametrize("value", [
    DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1", ["PATH"]),
    recovery_ref(), failure(), result(),
    AdapterRecovery(
        "run-001", "action-001", "attempt-001", "claude-dev", "deep-claude",
        recovery_ref(), "running", None),
    AdapterEvidence(
        "evidence", "run-001", "action-001", "attempt-001", "claude-dev",
        "deep-claude", "result", "artifact", DIGEST, NOW, "unavailable", None),
])
def test_every_public_from_dict_returns_the_exact_base_not_the_calling_subclass(value):
    hostile = type(f"Hostile{type(value).__name__}", (type(value),), {})
    reconstructed = hostile.from_dict(value.as_dict())
    assert type(reconstructed) is type(value)


@pytest.mark.parametrize("constructor,changes", [
    (RecoveryRef.from_dict, {"action_id": "APIKEY/SECRET"}),
    (NormalizedResult.from_dict, {"action_id": "APIKEY/SECRET"}),
    (DeepAdapterConfig.from_dict, {"protocol": "APIKEY_SECRET_PROTOCOL"}),
])
def test_untrusted_value_failures_retain_no_secret_cause_or_context(constructor, changes):
    if constructor == RecoveryRef.from_dict:
        body = recovery_ref().as_dict()
    elif constructor == NormalizedResult.from_dict:
        body = result().as_dict()
    else:
        body = DeepAdapterConfig(
            "C:/fake/tool.exe", "fake-claude-jsonl-v1").as_dict()
    body.update(changes)
    with pytest.raises(DeepContractError) as stopped:
        constructor(body)
    graph = repr((stopped.value, stopped.value.__cause__, stopped.value.__context__))
    assert "APIKEY" not in graph
    assert stopped.value.__cause__ is None and stopped.value.__context__ is None


def test_public_constructors_refuse_string_subclasses_before_using_their_behavior():
    class HostileString(str):
        def __eq__(self, _other):
            raise RuntimeError("APIKEY_SECRET_EQUALITY")

        def __hash__(self):
            return str.__hash__(self)

    cases = (
        lambda: DeepAdapterConfig(HostileString("C:/fake/tool.exe"),
                                  "fake-claude-jsonl-v1"),
        lambda: DeepAdapterConfig("C:/fake/tool.exe",
                                  HostileString("fake-claude-jsonl-v1")),
        lambda: RecoveryRef(
            "fake-ledger-v1", "deep-claude", HostileString("action-001"), DIGEST),
        lambda: AdapterFailure(HostileString("lost_result"), "execute", True),
        lambda: DeepAdapterConfig(
            "C:/fake/tool.exe", "fake-claude-jsonl-v1", [HostileString("PATH")]),
        lambda: DeepCommandSpec(
            ("C:/fake/tool.exe", HostileString("--fake-claude-jsonl-v1")),
            "work", (), "bounded-jsonl-v1", 10),
    )
    for build in cases:
        with pytest.raises(DeepContractError) as stopped:
            build()
        graph = repr((stopped.value, stopped.value.__cause__, stopped.value.__context__))
        assert "APIKEY_SECRET" not in graph


def test_public_collections_require_exact_list_or_tuple_before_iteration():
    cases = (
        (lambda rows: DeepAdapterConfig(
            "C:/fake/tool.exe", "fake-claude-jsonl-v1", rows), ["PATH"],
         "env_allow must contain unique environment names"),
        (lambda rows: DeepDispatchArgs(
            "work", "instruction", "review", rows, "normal"), ["artifact"],
         "artifact_refs must be a list of ids"),
        (lambda rows: DeepReviewArgs(
            "work", rows, "quality"), ["artifact"],
         "target_artifact_refs must be a list of ids"),
        (lambda rows: DeepEvidenceArgs("action", rows), ["result"],
         "kinds must be a list"),
        (lambda rows: DeepCommandSpec(
            rows, "work", (), "bounded-jsonl-v1", 10),
         ["C:/fake/tool.exe", "--fake-claude-jsonl-v1"],
         "argv must be the exact reviewed two-value tuple"),
        (lambda rows: DeepCommandSpec(
            ("C:/fake/tool.exe", "--fake-claude-jsonl-v1"), "work", rows,
            "bounded-jsonl-v1", 10), ["PATH"],
         "env_allow must contain unique environment names"),
    )
    for base in (list, tuple):
        class HostileRows(base):
            iterated = False

            def __iter__(self):
                type(self).iterated = True
                raise RuntimeError("APIKEY_SECRET_ITERATOR")

        for build, values, message in cases:
            HostileRows.iterated = False
            with pytest.raises(DeepContractError) as stopped:
                build(HostileRows(values))
            assert str(stopped.value) == message
            assert not HostileRows.iterated
            assert stopped.value.__cause__ is None
            assert stopped.value.__context__ is None


def test_consumers_revalidate_mutated_collections_before_iteration_or_equality():
    def config_call(rows):
        value = DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1")
        object.__setattr__(value, "env_allow", rows)
        return value.as_dict

    def spec_call(rows):
        config = DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1")
        value = DeepCommandSpec.from_config(config, timeout_seconds=10)
        object.__setattr__(value, "env_allow", rows)
        return lambda: value.to_runner_spec(config)

    def argument_call(value, field, rows):
        object.__setattr__(value, field, rows)
        return value.as_dict

    cases = (
        (config_call, ["PATH"], "deep adapter config must remain canonical"),
        (spec_call, ["PATH"], "command spec must remain canonical"),
        (lambda rows: argument_call(
            DeepDispatchArgs("work", "instruction", "review", [], "normal"),
            "artifact_refs", rows), ["artifact"],
         "deep arguments must remain canonical"),
        (lambda rows: argument_call(
            DeepReviewArgs("work", ["artifact"], "quality"),
            "target_artifact_refs", rows), ["artifact"],
         "deep arguments must remain canonical"),
        (lambda rows: argument_call(
            DeepEvidenceArgs("action", ["result"]), "kinds", rows), ["result"],
         "deep arguments must remain canonical"),
    )
    for hostile_type in (_HostileList, _HostileTuple):
        for make_call, rows, message in cases:
            hostile_type.iterated = hostile_type.compared = False
            call = make_call(hostile_type(rows))
            with pytest.raises(DeepContractError) as stopped:
                call()
            assert str(stopped.value) == message
            assert not hostile_type.iterated and not hostile_type.compared
            assert stopped.value.__cause__ is None
            assert stopped.value.__context__ is None


def test_consumers_reconstruct_mutated_exact_base_collections():
    config = DeepAdapterConfig("C:/fake/tool.exe", "fake-claude-jsonl-v1")
    object.__setattr__(config, "env_allow", ["PATH"])
    assert config.as_dict()["env_allow"] == ["PATH"]
    spec = DeepCommandSpec.from_config(config, timeout_seconds=10)
    object.__setattr__(spec, "env_allow", ["PATH"])
    assert spec.to_runner_spec(config).env_allow == ("PATH",)
    values = (
        (DeepDispatchArgs("work", "instruction", "review", [], "normal"),
         "artifact_refs", ["artifact"]),
        (DeepReviewArgs("work", ["artifact"], "quality"),
         "target_artifact_refs", ["artifact"]),
        (DeepEvidenceArgs("action", ["result"]), "kinds", ["result"]),
    )
    for value, field, rows in values:
        object.__setattr__(value, field, rows)
        assert value.as_dict()[field] == rows


def test_public_constructors_require_exact_integer_types_not_equal_subclasses():
    class HostileInt(int):
        pass

    with pytest.raises(DeepContractError, match="exit_code"):
        result(exit_code=HostileInt(0))
    with pytest.raises(DeepContractError, match="timeout_seconds"):
        DeepCommandSpec(
            ("C:/fake/tool.exe", "--fake-claude-jsonl-v1"), "work", (),
            "bounded-jsonl-v1", HostileInt(10))


def test_deep_value_modules_have_the_exact_reviewed_import_surface():
    expected = {
        "conductor.command.adapters.deep_contracts": {
            "__future__", "re", "dataclasses", "enum", "pathlib", "types",
            "typing", "..contracts"},
        "conductor.command.adapters.deep_commands": {
            "__future__", "dataclasses", "pathlib", "types", "typing",
            ".deep_contracts", ".process"},
        "conductor.command.adapters.deep_codecs": {
            "__future__", "json", "math", "collections.abc", "typing",
            "..contracts", ".deep_contracts"},
        "conductor.command.adapters.deep_evidence": {
            "__future__", "dataclasses", "typing", ".deep_contracts"},
    }
    for module_name, allowed in expected.items():
        module = importlib.import_module(module_name)
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported = {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names}
        imported.update(
            "." * node.level + (node.module or "")
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        assert imported == allowed
        dynamic_doors = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"__import__", "import_module"}}
        dynamic_doors.update(
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"__import__", "import_module"})
        dynamic_doors.update(
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and node.value in {"__import__", "import_module"})
        assert dynamic_doors == set()
