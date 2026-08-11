"""Capability-driven Adapter SDK tests; unsupported controls do not exist."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conductor.command.adapters import base as adapter_base
from conductor.command.adapters.base import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterRegistry,
    AdapterVerification,
    PreparedAction,
    UnsupportedCapability,
)
from conductor.command.contracts import ActionRequest, ActionResultReceipt


NOW = "2026-08-11T10:00:00Z"
DIGEST = "sha256:" + "a" * 64


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
        "preview_digest": DIGEST,
        "mode": "confirm",
    }
    values.update(changes)
    return ActionRequest(**values)


class FakeAdapter:
    def __init__(self, adapter_id="claude-code", capabilities=("observe", "dispatch")):
        self.manifest = AdapterManifest(
            adapter_id=adapter_id,
            display_name="Claude Code" if adapter_id == "claude-code" else "Custom",
            vendor="Anthropic" if adapter_id == "claude-code" else "User provided",
            version="1",
            capabilities=capabilities,
            docs_url="https://docs.anthropic.com/en/docs/claude-code/overview",
        )
        self.observations = 0
        self.preparations = 0

    def observe(self, instance_id, run_id):
        self.observations += 1
        return AdapterObservation(
            adapter_id=self.manifest.adapter_id,
            instance_id=instance_id,
            run_id=run_id,
            observed_at=NOW,
            health="ready",
            available_capabilities=self.manifest.capabilities,
            detail="Connected through the configured test transport.",
        )

    def prepare(self, request):
        self.preparations += 1
        return PreparedAction(
            adapter_id=self.manifest.adapter_id,
            request=request,
            adapter_payload={"operation": "dispatch", "handoff": "packet-001"},
        )

    def execute(self, prepared):
        raise AssertionError("CMD-3 must never call execute")

    def verify(self, request, result):
        return AdapterVerification(
            adapter_id=self.manifest.adapter_id,
            action_id=request.action_id,
            state="unavailable",
            observed_at=NOW,
            detail="The fake adapter exposes no verifier.",
        )


@pytest.mark.parametrize("field,value", [
    ("adapter_id", "../adapter"),
    ("display_name", ""),
    ("vendor", ""),
    ("version", ""),
    ("capabilities", ("observe", "observe")),
    ("capabilities", ("observe", "arbitrary-shell")),
    ("docs_url", "javascript:alert(1)"),
])
def test_manifest_boundary_rejects_ambiguous_identity_or_unbounded_capability(field, value):
    values = {
        "adapter_id": "claude-code",
        "display_name": "Claude Code",
        "vendor": "Anthropic",
        "version": "1",
        "capabilities": ("observe", "dispatch"),
        "docs_url": "https://docs.anthropic.com/",
    }
    values[field] = value
    with pytest.raises(AdapterContractError, match=field):
        AdapterManifest(**values)


def test_manifest_payload_is_stable_immutable_and_names_only_real_controls():
    source = ["dispatch", "observe", "stop"]
    manifest = AdapterManifest(
        adapter_id="custom", display_name="Custom", vendor="User provided", version="1",
        capabilities=source, docs_url="")
    source.append("pause")
    assert manifest.capabilities == ("dispatch", "observe", "stop")
    assert manifest.as_payload() == {
        "adapter_id": "custom",
        "display_name": "Custom",
        "vendor": "User provided",
        "version": "1",
        "capabilities": ["dispatch", "observe", "stop"],
        "docs_url": "",
    }
    assert "executable_hints" not in manifest.as_payload()


@pytest.mark.parametrize("payload", [
    {"command": "claude --dangerously-skip-permissions"},
    {"transport": {"shell": "codex && erase project"}},
    {"cmd": "cursor-agent"},
])
def test_prepared_payload_cannot_smuggle_an_unrestricted_shell_string(payload):
    with pytest.raises(AdapterContractError, match="unrestricted command field"):
        PreparedAction(
            adapter_id="claude-code", request=an_action(), adapter_payload=payload)
    allowed = PreparedAction(
        adapter_id="claude-code", request=an_action(),
        adapter_payload={"argv": ["claude", "--print", "packet-001"]})
    assert allowed.adapter_payload["argv"] == ("claude", "--print", "packet-001")


def test_registry_is_explicit_deterministic_and_never_detects_the_machine():
    registry = AdapterRegistry()
    custom = FakeAdapter("custom", ("observe",))
    claude = FakeAdapter()
    registry.register(custom)
    registry.register(claude)
    assert [row.adapter_id for row in registry.manifests()] == ["claude-code", "custom"]
    assert registry.resolve("custom") is custom
    with pytest.raises(AdapterContractError, match="already registered"):
        registry.register(FakeAdapter("custom", ("observe",)))
    with pytest.raises(AdapterContractError, match="not registered"):
        registry.resolve("missing")


def test_registry_keeps_the_manifest_that_was_reviewed_at_registration():
    adapter = FakeAdapter(capabilities=("observe",))
    registry = AdapterRegistry([adapter])
    adapter.manifest = AdapterManifest(
        adapter_id="custom", display_name="Changed", vendor="Changed", version="2",
        capabilities=("observe", "pause"), docs_url="")
    assert registry.controls("claude-code") == ("observe",)
    with pytest.raises(UnsupportedCapability, match="pause"):
        registry.prepare("claude-code", an_action(capability="pause"))


def test_sdk_source_has_no_machine_probe_or_process_door():
    source_path = Path(adapter_base.__file__).resolve()
    assert source_path.name == "base.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not imports & {"os", "pathlib", "shutil", "subprocess"}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not calls & {"which", "exists", "is_file", "run", "Popen", "system"}


def test_observe_calls_only_an_explicit_adapter_and_validates_its_claims():
    adapter = FakeAdapter()
    registry = AdapterRegistry([adapter])
    observation = registry.observe("claude-code", "claude-dev", "run-001")
    assert observation.health == "ready"
    assert observation.available_capabilities == ("observe", "dispatch")
    assert adapter.observations == 1

    adapter.manifest = AdapterManifest(
        adapter_id="claude-code", display_name="Claude Code", vendor="Anthropic",
        version="1", capabilities=("observe",), docs_url="")
    adapter.observe = lambda instance_id, run_id: AdapterObservation(
        adapter_id="somebody-else", instance_id=instance_id, run_id=run_id,
        observed_at=NOW, health="ready", available_capabilities=("observe",))
    with pytest.raises(AdapterContractError, match="returned identity"):
        registry.observe("claude-code", "claude-dev", "run-001")


def test_unsupported_capability_is_absent_and_adapter_is_not_called():
    adapter = FakeAdapter(capabilities=("observe",))
    registry = AdapterRegistry([adapter])
    assert registry.controls("claude-code") == ("observe",)
    with pytest.raises(UnsupportedCapability, match="dispatch"):
        registry.prepare("claude-code", an_action())
    assert adapter.preparations == 0


def test_prepare_returns_a_validated_non_executing_adapter_plan():
    adapter = FakeAdapter()
    registry = AdapterRegistry([adapter])
    prepared = registry.prepare("claude-code", an_action())
    assert prepared.request == an_action()
    assert prepared.adapter_id == "claude-code"
    assert prepared.adapter_payload == {
        "operation": "dispatch", "handoff": "packet-001",
    }
    assert adapter.preparations == 1


def test_registry_rejects_a_prepared_plan_that_changes_identity_or_request():
    adapter = FakeAdapter()
    registry = AdapterRegistry([adapter])
    adapter.prepare = lambda request: PreparedAction(
        adapter_id="custom", request=request, adapter_payload={})
    with pytest.raises(AdapterContractError, match="adapter_id"):
        registry.prepare("claude-code", an_action())

    adapter.prepare = lambda request: PreparedAction(
        adapter_id="claude-code", request=an_action(action_id="action-other"),
        adapter_payload={})
    with pytest.raises(AdapterContractError, match="changed the ActionRequest"):
        registry.prepare("claude-code", an_action())


def test_observation_and_verification_never_infer_green_from_missing_evidence():
    observation = AdapterObservation(
        adapter_id="custom", instance_id="custom-1", run_id="run-001",
        observed_at=NOW, health="unknown", available_capabilities=(), detail="")
    assert observation.health == "unknown"
    verification = AdapterVerification(
        adapter_id="custom", action_id="action-001", state="unavailable",
        observed_at=NOW, detail="Adapter cannot verify this result.")
    assert verification.state == "unavailable"
    with pytest.raises(AdapterContractError, match="verified evidence"):
        AdapterVerification(
            adapter_id="custom", action_id="action-001", state="verified",
            observed_at=NOW, detail="Looks good", evidence_refs=())


def test_protocol_keeps_execution_separate_from_preparation():
    adapter = FakeAdapter()
    registry = AdapterRegistry([adapter])
    prepared = registry.prepare("claude-code", an_action())
    assert isinstance(prepared, PreparedAction)
    assert not hasattr(registry, "execute")
    with pytest.raises(AssertionError, match="must never call execute"):
        adapter.execute(prepared)


def test_result_type_stays_separate_from_adapter_verification():
    result = ActionResultReceipt(
        receipt_id="result-001", action_id="action-001", run_id="run-001",
        attempt_id="attempt-001", instance_id="claude-dev", outcome="succeeded",
        observed_at=NOW)
    verification = FakeAdapter().verify(an_action(), result)
    assert result.outcome == "succeeded"
    assert verification.state == "unavailable"
