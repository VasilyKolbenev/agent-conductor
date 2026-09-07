"""Lifecycle tests for the two thin, fake-protocol deep adapters.

The runner below is a deterministic executable witness: it receives the exact
code-owned ``CommandSpec`` and returns one bounded byte frame.  It cannot see a
browser body and exposes no argv/env/cwd setter.  The production ProcessRunner
route refusal is exercised separately.
"""
from __future__ import annotations

import ast
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import conductor
from conductor.command.adapters import (
    AdapterContractError,
    AdapterRegistry,
    ClaudeCodeAdapter,
    CodexAdapter,
    PreparedAction,
    UnsupportedCapability,
)
from conductor.command.adapters.base import CAPABILITIES
from conductor.command.providers import PROVIDER_CATALOG
from conductor.command.adapters.deep_adapters import DEEP_CAPABILITIES, DEEP_CONTROLS
from conductor.command.adapters.deep_codecs import FakeClaudeCodec, FakeCodexCodec
from conductor.command.adapters.deep_commands import (
    DEEP_ARGUMENT_TYPES,
    DEEP_PROTOCOL_FLAGS,
    DeepDispatchArgs,
    DeepEvidenceArgs,
    DeepRetryArgs,
    DeepReviewArgs,
    DeepStopArgs,
    DeepSwitchArgs,
)
from conductor.command.adapters.deep_contracts import (
    DeepAdapterConfig,
    DeepProtocol,
    NormalizedResult,
)
from conductor.command.adapters.deep_evidence import AdapterEvidence
from conductor.command.adapters.process import (
    CommandSpec,
    ProcessOutcome,
    ProcessRunner,
)
from conductor.command.contracts import ActionRequest, EvidenceRef
from conductor.command.contracts import canonical_json
from conductor.command.runtime import AttemptState

from tests.test_command_runtime_authorize import a_budget, a_confirmation, a_proposal
from tests.test_command_runtime_execute import authorized, kinds
from tests.test_command_runtime_authorize import a_store


NOW = "2026-08-11T12:00:00Z"
DIGEST = "sha256:" + "d" * 64


ARGUMENTS = {
    "dispatch": DeepDispatchArgs(
        "work-001", "instruction-001", "implement", [], "small").as_dict(),
    "review": DeepReviewArgs(
        "work-001", ["artifact-001"], "artifact-review-001",
        "security").as_dict(),
    "evidence": DeepEvidenceArgs("action-001", ["result", "tests"]).as_dict(),
    "stop": DeepStopArgs("attempt-001", "user").as_dict(),
    "retry": DeepRetryArgs("action-001", "failed").as_dict(),
    "switch": DeepSwitchArgs(
        "action-001", "codex-review", "handoff-001").as_dict(),
}


class FakeExecutable:
    """One deterministic process result and the exact specs it was given."""

    def __init__(self, outcome: ProcessOutcome):
        self.outcome = outcome
        self.specs: list[CommandSpec] = []

    def run(self, spec):
        assert type(spec) is CommandSpec
        self.specs.append(spec)
        return self.outcome


def process_outcome(
        output: bytes, *, status="completed", exit_code=0,
        truncated=False, token="runner-secret-token"):
    return ProcessOutcome(
        status=status, exit_code=exit_code, output=output,
        output_truncated=truncated, output_limit=16 * 1024,
        pid=4242, token=token)


def result(adapter_id="claude-code", instance_id="claude-dev", **changes):
    values = {
        "run_id": "run-001", "action_id": "action-fixed",
        "attempt_id": "attempt-001", "instance_id": instance_id,
        "adapter_id": adapter_id, "outcome": "succeeded",
        "observed_at": NOW, "exit_code": 0, "failure": None,
    }
    values.update(changes)
    return NormalizedResult(**values)


def request(adapter_id="claude-code", capability="dispatch", **changes):
    instance = "claude-dev" if adapter_id == "claude-code" else "codex-review"
    values = {
        "action_id": "action-fixed", "run_id": "run-001",
        "attempt_id": "attempt-001", "instance_id": instance,
        "capability": capability,
        # An undeclared control has no closed deep body; give it a plain one so a
        # test can still ask the registry to refuse the capability itself.
        "arguments": ARGUMENTS.get(capability, {"handoff": "packet-001"}),
        "scope": ("src",), "requested_by": "release-owner",
        "requested_at": NOW, "idempotency_key": "dispatch-proposal-001",
        "timeout_seconds": 30, "preview_digest": "sha256:" + "a" * 64,
        "mode": "confirm",
    }
    values.update(changes)
    return ActionRequest(**values)


def configured(
        adapter_type, runner, tmp_path, *, evidence_source=None, env_allow=()):
    protocol = {
        ClaudeCodeAdapter: "fake-claude-jsonl-v1",
        CodexAdapter: "fake-codex-jsonl-v1",
    }[adapter_type]
    executable = str((tmp_path / f"{adapter_type.__name__}.exe").resolve())
    config = DeepAdapterConfig(executable, protocol, list(env_allow))
    return adapter_type(
        config, runner, clock=lambda: NOW, ids=lambda _purpose: "deep-result-001",
        evidence_source=evidence_source)


@pytest.mark.parametrize("adapter_type,codec,adapter_id", [
    (ClaudeCodeAdapter, FakeClaudeCodec, "claude-code"),
    (CodexAdapter, FakeCodexCodec, "codex"),
])
def test_both_adapters_run_only_the_code_owned_spec_and_discard_process_identity(
        tmp_path, adapter_type, codec, adapter_id):
    instance = "claude-dev" if adapter_id == "claude-code" else "codex-review"
    frame = codec.encode_result(result(adapter_id, instance))
    runner = FakeExecutable(process_outcome(frame, token="APIKEY_SECRET_TOKEN"))
    adapter = configured(adapter_type, runner, tmp_path, env_allow=("PATH",))

    prepared = adapter.prepare(request(adapter_id))
    receipt = adapter.execute(prepared)

    assert receipt.outcome == "succeeded" and receipt.exit_code == 0
    assert receipt.detail is None and receipt.evidence_refs == ()
    assert "APIKEY" not in repr(receipt.as_dict())
    assert len(runner.specs) == 1
    spec = runner.specs[0]
    expected_flag = {
        ClaudeCodeAdapter: "--fake-claude-jsonl-v1",
        CodexAdapter: "--fake-codex-jsonl-v1",
    }[adapter_type]
    assert spec.argv == (adapter._config.executable, expected_flag)
    assert spec.cwd == "work" and spec.env_allow == ("PATH",)
    assert spec.output_limit == 16 * 1024 and spec.timeout_seconds == 30
    assert not hasattr(receipt, "pid") and not hasattr(receipt, "token")


@pytest.mark.parametrize("adapter_type,adapter_id", [
    (ClaudeCodeAdapter, "claude-code"), (CodexAdapter, "codex")])
def test_manifests_expose_observe_plus_exact_six_closed_schemas(
        tmp_path, adapter_type, adapter_id):
    adapter = configured(
        adapter_type, FakeExecutable(process_outcome(b"ignored")), tmp_path)
    registry = AdapterRegistry([adapter])
    assert registry.controls(adapter_id) == ("observe", *DEEP_CAPABILITIES)
    assert tuple(DEEP_ARGUMENT_TYPES) == DEEP_CAPABILITIES
    for capability, arguments in ARGUMENTS.items():
        registry.validate_arguments(adapter_id, capability, arguments)
    observation = registry.observe(adapter_id, "instance-001", "run-001")
    assert observation.health == "unknown"
    assert observation.available_capabilities == ()


@pytest.mark.parametrize("capability", DEEP_CAPABILITIES)
@pytest.mark.parametrize("forbidden", ["argv", "cwd", "env", "path", "shell"])
def test_browser_command_authority_cannot_enter_any_deep_schema(
        tmp_path, capability, forbidden):
    adapter = configured(
        ClaudeCodeAdapter, FakeExecutable(process_outcome(b"ignored")), tmp_path)
    registry = AdapterRegistry([adapter])
    hostile = dict(ARGUMENTS[capability])
    hostile[forbidden] = ["sh", "-c", "APIKEY_SECRET"]
    with pytest.raises(AdapterContractError, match="closed deep schema") as stopped:
        registry.validate_arguments("claude-code", capability, hostile)
    assert "APIKEY" not in repr(stopped.value)


def test_prepare_is_pure_and_execute_rebinds_payload_to_the_request(tmp_path):
    runner = FakeExecutable(process_outcome(b"never used"))
    adapter = configured(ClaudeCodeAdapter, runner, tmp_path)
    approved = request()
    prepared = adapter.prepare(approved)
    assert runner.specs == []
    assert prepared.adapter_payload == {
        "capability": "dispatch",
        "arguments_json": canonical_json(ARGUMENTS["dispatch"])}
    changed = PreparedAction(
        adapter_id="claude-code", request=approved,
        adapter_payload={
            "capability": "dispatch",
            "arguments_json": canonical_json(
                dict(ARGUMENTS["dispatch"], profile="review"))})
    with pytest.raises(AdapterContractError, match="differs"):
        adapter.execute(changed)
    assert runner.specs == []


@pytest.mark.parametrize("adapter_type,own_codec,foreign_codec,adapter_id,instance", [
    (ClaudeCodeAdapter, FakeClaudeCodec, FakeCodexCodec,
     "claude-code", "claude-dev"),
    (CodexAdapter, FakeCodexCodec, FakeClaudeCodec,
     "codex", "codex-review"),
])
def test_wrong_vendor_and_foreign_identity_are_fixed_refusals_without_raw_prose(
        tmp_path, adapter_type, own_codec, foreign_codec, adapter_id, instance):
    cases = (
        foreign_codec.encode_result(result(adapter_id, instance)),
        own_codec.encode_result(result(
            adapter_id, instance, action_id="action-foreign")),
        b"APIKEY_SECRET_OUTPUT\n",
    )
    for frame in cases:
        adapter = configured(
            adapter_type, FakeExecutable(process_outcome(frame)), tmp_path)
        with pytest.raises(AdapterContractError) as stopped:
            adapter.execute(adapter.prepare(request(adapter_id)))
        graph = repr((stopped.value, stopped.value.__cause__, stopped.value.__context__))
        assert "APIKEY" not in graph
        assert stopped.value.__cause__ is None and stopped.value.__context__ is None


@pytest.mark.parametrize("outcome,expected,exit_code", [
    (process_outcome(b"APIKEY_SECRET", status="timed_out", exit_code=None),
     "failed", None),
    (process_outcome(b"APIKEY_SECRET", status="stopped", exit_code=None),
     "cancelled", None),
    (process_outcome(b"APIKEY_SECRET", truncated=True), "unknown", None),
    (process_outcome(b"APIKEY_SECRET", exit_code=9), "failed", 9),
])
def test_timeout_stop_output_bomb_and_nonzero_are_closed_secret_free_receipts(
        tmp_path, outcome, expected, exit_code):
    adapter = configured(ClaudeCodeAdapter, FakeExecutable(outcome), tmp_path)
    receipt = adapter.execute(adapter.prepare(request()))
    assert (receipt.outcome, receipt.exit_code) == (expected, exit_code)
    assert receipt.detail is None and "APIKEY" not in repr(receipt.as_dict())


def test_actual_process_runner_route_refusal_is_sanitized_before_spawn(tmp_path):
    config = DeepAdapterConfig(sys.executable, "fake-claude-jsonl-v1")
    runner = ProcessRunner(tmp_path, environ={})
    adapter = ClaudeCodeAdapter(
        config, runner, clock=lambda: NOW, ids=lambda _purpose: "result-001")
    with pytest.raises(AdapterContractError) as stopped:
        adapter.execute(adapter.prepare(request()))
    assert str(stopped.value) == "deep process execution failed"
    assert stopped.value.__cause__ is None and stopped.value.__context__ is None
    assert runner.active_tokens() == ()


def test_independent_evidence_is_identity_bound_and_result_is_not_an_input(tmp_path):
    looked_up: list[str] = []

    def source(action_id):
        looked_up.append(action_id)
        return AdapterEvidence(
            "evidence-001", "run-001", action_id, "attempt-001", "claude-dev",
            "claude-code", "result", "artifact-001", DIGEST, NOW,
            "verified", NOW)

    frame = FakeClaudeCodec.encode_result(result())
    adapter = configured(
        ClaudeCodeAdapter, FakeExecutable(process_outcome(frame)), tmp_path,
        evidence_source=source)
    approved = request()
    receipt = adapter.execute(adapter.prepare(approved))
    verification = adapter.verify(approved, receipt)
    assert looked_up == [approved.action_id]
    assert verification.state == "verified"
    assert verification.evidence_refs == ("evidence-001",)
    foreign = replace(receipt, action_id="action-foreign")
    assert adapter.verify(approved, foreign).state == "mismatch"
    assert looked_up == [approved.action_id]


@pytest.mark.parametrize("adapter_type,codec,adapter_id,instance", [
    (ClaudeCodeAdapter, FakeClaudeCodec, "claude-code", "claude-dev"),
    (CodexAdapter, FakeCodexCodec, "codex", "codex-review"),
])
def test_fake_end_to_end_reaches_only_post_observation_verified_evidence(
        tmp_path, adapter_type, codec, adapter_id, instance):
    store = a_store(tmp_path)

    def source(action_id):
        evidence_id = f"evidence-{adapter_id}"
        store.append(EvidenceRef(
            evidence_id=evidence_id, run_id="run-001", kind="verification",
            uri=f"verification/{action_id}", label="independent fake fact",
            created_by=adapter_id, observed_at=NOW, digest=DIGEST,
            verification="verified", verified_by=adapter_id, verified_at=NOW))
        return AdapterEvidence(
            evidence_id, "run-001", action_id, "attempt-001", instance,
            adapter_id, "result", "artifact-001", DIGEST, NOW, "verified", NOW)

    frame = codec.encode_result(result(adapter_id, instance))
    runner = FakeExecutable(process_outcome(frame))
    adapter = configured(
        adapter_type, runner, tmp_path, evidence_source=source)
    runtime, authorization = authorized(
        store, adapter,
        proposal_changes={
            "instance_id": instance, "arguments": ARGUMENTS["dispatch"],
            "input_binding": "proposal-v1",
            "rationale": "Run one closed fake deep dispatch."})

    attempt = runtime.execute(authorization)

    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.receipt.evidence_refs == (f"evidence-{adapter_id}",)
    assert [row.kind for row in store.read("run-001").records] == [
        "action_proposal", "action_request", "attempt_event", "attempt_event",
        "evidence", "action_result"]
    assert runner.specs and attempt.verification_evidence[0].verified_by == adapter_id


def test_failed_or_missing_independent_fact_never_becomes_verified(tmp_path):
    frame = FakeClaudeCodec.encode_result(result())
    approved = request()
    for source in (
            None,
            lambda _action: AdapterEvidence(
                "evidence-001", "run-001", "action-foreign", "attempt-001",
                "claude-dev", "claude-code", "result", "artifact-001", DIGEST,
                NOW, "verified", NOW)):
        adapter = configured(
            ClaudeCodeAdapter, FakeExecutable(process_outcome(frame)), tmp_path,
            evidence_source=source)
        receipt = adapter.execute(adapter.prepare(approved))
        assert adapter.verify(approved, receipt).state in {"unavailable", "mismatch"}


# -- The closed per-capability schema relation --

@pytest.mark.parametrize("capability", DEEP_CAPABILITIES)
def test_each_capability_accepts_only_its_own_closed_argument_type(tmp_path, capability):
    """The mapping is a relation: a sibling capability's body is refused, not coerced."""
    adapter = configured(
        ClaudeCodeAdapter, FakeExecutable(process_outcome(b"unused\n")), tmp_path)
    registry = AdapterRegistry([adapter])
    schemas = type(adapter).argument_schemas
    assert set(schemas) == set(DEEP_CAPABILITIES)
    assert schemas[capability] == "deep-arguments-v1"
    registry.validate_arguments("claude-code", capability, ARGUMENTS[capability])
    for other in DEEP_CAPABILITIES:
        if other == capability:
            continue
        assert ARGUMENTS[other] != ARGUMENTS[capability]
        with pytest.raises(AdapterContractError, match="closed deep schema"):
            registry.validate_arguments("claude-code", capability, ARGUMENTS[other])


def test_all_six_capability_bodies_execute_and_none_reaches_the_child_spec(tmp_path):
    """The pending real transport carries no body: the spec is config-derived only."""
    frame = FakeClaudeCodec.encode_result(result())
    specs, payloads = [], []
    for capability in DEEP_CAPABILITIES:
        runner = FakeExecutable(process_outcome(frame))
        adapter = configured(ClaudeCodeAdapter, runner, tmp_path)
        prepared = adapter.prepare(request(capability=capability))
        assert adapter.execute(prepared).outcome == "succeeded"
        specs.append(runner.specs[0])
        payloads.append(prepared.adapter_payload["arguments_json"])
    assert len(specs) == 6 and len(set(payloads)) == 6
    assert all(spec == specs[0] for spec in specs), "a capability body reached the child"
    spawned = repr(specs)
    for carried in ("work-001", "instruction-001", "artifact-001", "handoff-001",
                    "attempt-001", "security", "implement"):
        assert carried not in spawned


# -- Identity binding across all five bound ids --

@pytest.mark.parametrize("field,foreign", [
    ("run_id", "run-foreign"),
    ("action_id", "action-foreign"),
    ("attempt_id", "attempt-foreign"),
    ("instance_id", "instance-foreign"),
    ("adapter_id", "codex"),
])
def test_any_single_foreign_bound_id_refuses_the_result_the_matched_one_accepts(
        tmp_path, field, foreign):
    matched = result()
    assert getattr(matched, field) != foreign
    control = FakeExecutable(process_outcome(FakeClaudeCodec.encode_result(matched)))
    accepting = configured(ClaudeCodeAdapter, control, tmp_path)
    assert accepting.execute(accepting.prepare(request())).outcome == "succeeded"

    runner = FakeExecutable(process_outcome(
        FakeClaudeCodec.encode_result(result(**{field: foreign}))))
    adapter = configured(ClaudeCodeAdapter, runner, tmp_path)
    with pytest.raises(AdapterContractError, match="identity does not match"):
        adapter.execute(adapter.prepare(request()))


# -- Hostile subclasses and instance-attribute shadowing --

def test_a_subclass_of_a_reviewed_deep_adapter_cannot_be_constructed(tmp_path):
    config = DeepAdapterConfig(
        str((tmp_path / "claude.exe").resolve()), "fake-claude-jsonl-v1")
    runner = FakeExecutable(process_outcome(b"unused\n"))
    for base in (ClaudeCodeAdapter, CodexAdapter):
        hostile = type("Hostile", (base,), {})
        with pytest.raises(AdapterContractError, match="reviewed concrete type"):
            hostile(config, runner, clock=lambda: NOW, ids=lambda _purpose: "id-001")
    assert runner.specs == []


@pytest.mark.parametrize("attribute,value,frame", [
    ("ADAPTER_ID", "codex",
     lambda: FakeClaudeCodec.encode_result(result("codex", "claude-dev"))),
    ("CODEC", FakeCodexCodec,
     lambda: FakeCodexCodec.encode_result(result("claude-code", "claude-dev"))),
])
def test_shadowing_a_class_attribute_never_borrows_the_other_vendor(
        tmp_path, attribute, value, frame):
    """Identity is re-derived from the class, so an instance attribute buys nothing."""
    runner = FakeExecutable(process_outcome(frame()))
    adapter = configured(ClaudeCodeAdapter, runner, tmp_path)
    object.__setattr__(adapter, attribute, value)
    assert getattr(type(adapter), attribute) is not value
    prepared = adapter.prepare(request())
    assert prepared.adapter_id == "claude-code"
    with pytest.raises(AdapterContractError) as stopped:
        adapter.execute(prepared)
    assert stopped.value.__cause__ is None and stopped.value.__context__ is None


def test_a_swapped_config_refuses_before_it_can_spawn_the_other_vendor(tmp_path):
    runner = FakeExecutable(process_outcome(b"unused\n"))
    adapter = configured(ClaudeCodeAdapter, runner, tmp_path)
    codex_config = DeepAdapterConfig(
        str((tmp_path / "codex.exe").resolve()), "fake-codex-jsonl-v1")
    object.__setattr__(adapter, "_config", codex_config)
    object.__setattr__(adapter, "PROTOCOL", DeepProtocol.FAKE_CODEX_V1)
    with pytest.raises(AdapterContractError, match="protocol does not match"):
        adapter.execute(adapter.prepare(request()))
    assert runner.specs == []


# -- Unsupported controls are absent, never stubbed --

def test_undeclared_controls_are_absent_from_the_manifest_and_have_no_stub(tmp_path):
    adapter = configured(
        ClaudeCodeAdapter, FakeExecutable(process_outcome(b"unused\n")), tmp_path)
    registry = AdapterRegistry([adapter])
    assert adapter.manifest.capabilities == DEEP_CONTROLS
    absent = sorted(CAPABILITIES - set(DEEP_CONTROLS))
    assert absent == ["message", "notify", "pause", "resume"]
    for capability in absent:
        assert not hasattr(adapter, capability)
        with pytest.raises(UnsupportedCapability):
            registry.validate_arguments("claude-code", capability, {"handoff": "x"})
        with pytest.raises(UnsupportedCapability):
            registry.prepare("claude-code", request(capability=capability))
    # Even a widened manifest buys nothing: the adapter has no such body to bind.
    object.__setattr__(adapter.manifest, "capabilities", ("observe", "message"))
    with pytest.raises(UnsupportedCapability, match="message"):
        adapter.prepare(request(capability="message"))


# -- Fake-only naming: nothing claims the real Claude Code or Codex CLI --

def test_only_the_two_reviewed_fake_flags_exist_and_no_real_cli_is_claimed(tmp_path):
    """Facts first -- flags, version, vendor, absent docs -- then the stated pending."""
    assert set(DEEP_PROTOCOL_FLAGS.values()) == {
        "--fake-claude-jsonl-v1", "--fake-codex-jsonl-v1"}
    for adapter_type in (ClaudeCodeAdapter, CodexAdapter):
        manifest = configured(
            adapter_type, FakeExecutable(process_outcome(b"unused\n")),
            tmp_path).manifest
        assert manifest.version == "fake-protocol-v1"
        assert "fake protocol" in manifest.display_name.casefold()
        assert "fixture" in manifest.vendor.casefold()
        # No docs link, because there is no real integration to point at.
        assert manifest.docs_url == ""
        # The PENDING statement is owed by whichever provider is still a
        # FIXTURE, and that is read from the catalog rather than from a list
        # here. `claude-code` became a real transport and stopped owing it in
        # the same commit; `codex` still owes it. A fixed list would have had to
        # be edited by the same hand that made the row real, which is the edit
        # most likely to be forgotten -- and the sentence it drops is the one
        # telling an operator that the row runs no real CLI.
        entry = PROVIDER_CATALOG.get(adapter_type.ADAPTER_ID)
        still_a_fixture = entry is not None and entry.implementation == "fixture_only"
        declaring = Path(sys.modules[adapter_type.__module__].__file__)
        if still_a_fixture:
            assert "PENDING" in declaring.read_text(encoding="utf-8"), (
                f"{adapter_type.__name__} stopped stating that its real CLI "
                f"transport is unimplemented ({declaring.name})")


def test_no_shipped_module_constructs_a_fake_deep_adapter(tmp_path):
    """Nothing in the product wires these in: they enter only explicit configuration."""
    package = Path(conductor.__file__).resolve().parent
    offenders: dict[str, list[str]] = {}
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        built = sorted({
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"ClaudeCodeAdapter", "CodexAdapter"}})
        if built:
            offenders[path.relative_to(package).as_posix()] = built
    assert offenders == {}
    assert AdapterRegistry().manifests() == ()


def test_protocol_identity_and_real_mode_are_closed_at_construction(tmp_path):
    runner = FakeExecutable(process_outcome(b"unused"))
    codex_config = DeepAdapterConfig(
        str((tmp_path / "codex.exe").resolve()), "fake-codex-jsonl-v1")
    with pytest.raises(AdapterContractError, match="does not match"):
        ClaudeCodeAdapter(
            codex_config, runner, clock=lambda: NOW, ids=lambda _purpose: "id")
    with pytest.raises(Exception, match="real_mode"):
        DeepAdapterConfig(
            str((tmp_path / "claude.exe").resolve()),
            "fake-claude-jsonl-v1", real_mode="ready")
