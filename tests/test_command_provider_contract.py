"""The immutable provider contract: closed schema relation and an honest projection.

These tests prove the value half of the hardened provider registry, with no
filesystem or process door. Each relation ships a positive path, a refusing path,
and a state assertion; the factory half (availability, registration, wiring) is
proven in ``test_command_provider_factory.py``. Control witnesses are written
here literally so no assertion reads both of its sides from one production value.
"""
from __future__ import annotations

import pytest

from conductor.command.contracts import canonical_json
from conductor.command.adapters.provider import (
    ProviderConfig,
    ProviderConfigError,
    ProviderContract,
    provider_projection,
    reconstruct_config,
    reconstruct_contract,
)

# An independent witness of the six deep control capabilities and their schema.
CONTROLS = ("dispatch", "review", "evidence", "stop", "retry", "switch")
CAPABILITIES = ("observe", *CONTROLS)
SCHEMA_PAIRS = [(capability, "deep-arguments-v1") for capability in CONTROLS]
LIFECYCLE = ("observe", "prepare", "execute", "verify")
ABS_EXECUTABLE = "/opt/claude/bin/claude"


def _contract(**changes) -> ProviderContract:
    values = {
        "provider_id": "claude-code", "display_name": "Claude Code",
        "vendor": "Anthropic", "version": "fake-claude-jsonl-v1",
        "capabilities": CAPABILITIES, "schema_pairs": SCHEMA_PAIRS,
        "lifecycle": LIFECYCLE, "availability": "available", "available": True,
    }
    values.update(changes)
    return ProviderContract(**values)


def test_provider_contract_binds_a_schema_to_every_control_and_refuses_a_partial_one():
    contract = _contract()
    assert [capability for capability, _ in contract.schema_pairs] == sorted(CONTROLS)
    with pytest.raises(ProviderConfigError, match="every control capability"):
        _contract(schema_pairs=[("review", "deep-arguments-v1")])


def test_provider_contract_refuses_a_repeated_capability_in_the_schema_relation():
    with pytest.raises(ProviderConfigError, match="repeat a capability"):
        _contract(
            capabilities=("observe", "dispatch"),
            schema_pairs=[
                ("dispatch", "deep-arguments-v1"),
                ("dispatch", "structured-process-v1")])


def test_provider_contract_refuses_a_schema_for_the_schemaless_observe_capability():
    with pytest.raises(ProviderConfigError, match="every control capability"):
        _contract(
            capabilities=("observe", "dispatch"),
            schema_pairs=[
                ("dispatch", "deep-arguments-v1"),
                ("observe", "deep-arguments-v1")])


def test_provider_contract_refuses_a_schema_for_an_undeclared_capability():
    with pytest.raises(ProviderConfigError, match="undeclared capability"):
        _contract(
            capabilities=("observe", "dispatch"),
            schema_pairs=[
                ("dispatch", "deep-arguments-v1"),
                ("stop", "deep-arguments-v1")])


def test_the_contract_carries_the_lifecycle_and_refuses_a_missing_or_invented_seam():
    assert _contract().lifecycle == tuple(sorted(LIFECYCLE))
    assert _contract(lifecycle=(*LIFECYCLE, "recover")).lifecycle == (
        "execute", "observe", "prepare", "recover", "verify")
    with pytest.raises(ProviderConfigError, match="must declare observe"):
        _contract(lifecycle=("observe", "prepare", "execute"))
    with pytest.raises(ProviderConfigError, match="unreviewed seam"):
        _contract(lifecycle=(*LIFECYCLE, "install"))
    with pytest.raises(ProviderConfigError, match="repeat a seam"):
        _contract(lifecycle=(*LIFECYCLE, "verify"))


def test_available_is_derived_from_the_resolved_state_never_supplied_freely():
    assert _contract(availability="executable_absent", available=False).available is False
    with pytest.raises(ProviderConfigError, match="available must equal"):
        _contract(availability="executable_absent", available=True)


def test_reconstruct_config_refuses_a_hostile_subclass_and_relays_a_canonical_value():
    honest = ProviderConfig(
        provider_id="claude-code", executable=ABS_EXECUTABLE,
        protocol="fake-claude-jsonl-v1", env_allow=("ANTHROPIC_API_KEY",))
    relayed = reconstruct_config(honest)
    assert relayed is not honest
    assert relayed.as_dict() == honest.as_dict()

    class ForgedConfig(ProviderConfig):
        def as_dict(self):
            return {
                "provider_id": "codex", "executable": ABS_EXECUTABLE,
                "protocol": "fake-codex-jsonl-v1", "env_allow": []}

    forged = ForgedConfig(
        provider_id="claude-code", executable=ABS_EXECUTABLE,
        protocol="fake-claude-jsonl-v1")
    with pytest.raises(ProviderConfigError, match="exact ProviderConfig"):
        reconstruct_config(forged)


def test_reconstruct_config_refuses_a_frozen_value_mutated_after_construction():
    config = ProviderConfig(
        provider_id="claude-code", executable=ABS_EXECUTABLE,
        protocol="fake-claude-jsonl-v1")
    object.__setattr__(config, "executable", "relative/claude")  # bypass the absolute gate
    with pytest.raises(ProviderConfigError, match="canonical"):
        reconstruct_config(config)


def test_reconstruct_contract_refuses_a_contract_mutated_after_construction():
    contract = _contract()
    relayed = reconstruct_contract(contract)
    assert relayed is not contract and relayed.as_dict() == contract.as_dict()
    object.__setattr__(contract, "available", False)  # bypass the derivation gate
    with pytest.raises(ProviderConfigError, match="remain canonical"):
        reconstruct_contract(contract)


def test_projection_exposes_only_names_availability_and_proven_controls():
    available = _contract()
    unavailable = _contract(
        provider_id="codex", display_name="Codex", vendor="OpenAI",
        version="fake-codex-jsonl-v1", availability="executable_absent", available=False)
    rows = provider_projection([available, unavailable])
    assert rows == [
        {"provider_id": "claude-code", "display_name": "Claude Code",
         "availability": "available", "implementation": "unproven",
         "controls": sorted(CONTROLS)},
        {"provider_id": "codex", "display_name": "Codex",
         "availability": "executable_absent", "implementation": "unproven",
         "controls": sorted(CONTROLS)},
    ]
    for row in rows:
        assert set(row) == {
            "provider_id", "display_name", "availability", "implementation",
            "controls"}
        assert "observe" not in row["controls"]


def test_no_forbidden_field_reaches_the_contract_or_its_projection():
    contract = _contract()
    blob = canonical_json(contract.as_dict()) + canonical_json(provider_projection([contract]))
    for banned in (
            "argv", "cmd", "command", "script", "shell", "cwd", "executable",
            "token", "api_key", "secret", "pid", "raw_output"):
        assert banned not in blob


def test_provider_config_stores_only_the_operator_pin_and_env_names():
    config = ProviderConfig(
        provider_id="claude-code", executable=ABS_EXECUTABLE,
        protocol="fake-claude-jsonl-v1", env_allow=("ANTHROPIC_API_KEY",))
    assert set(config.as_dict()) == {
        "provider_id", "executable", "protocol", "env_allow", "entrypoint"}
    assert config.as_dict()["env_allow"] == ["ANTHROPIC_API_KEY"]
    # An unpinned entrypoint is empty, never a guess: a provider that is its own
    # executable carries no second path at all.
    assert config.as_dict()["entrypoint"] == ""
    with pytest.raises(ProviderConfigError, match="env_allow"):
        ProviderConfig(
            provider_id="claude-code", executable=ABS_EXECUTABLE,
            protocol="fake-claude-jsonl-v1", env_allow=("ANTHROPIC_API_KEY=sk-live-secret",))
    blob = canonical_json(config.as_dict())
    for banned in ("argv", "cwd", "token", "secret", "pid", "raw_output"):
        assert banned not in blob


def test_the_second_pin_passes_the_same_absolute_gate_and_survives_a_round_trip():
    """The entrypoint is an operator pin under the executable's own gate."""
    pinned = ProviderConfig(
        provider_id="claude-code", executable=ABS_EXECUTABLE,
        protocol="fake-claude-jsonl-v1", entrypoint="C:/dsh/lib/bin.js")
    assert pinned.entrypoint == "C:/dsh/lib/bin.js"
    # The durable JSON carries it, and reading that JSON back rebuilds the value.
    assert ProviderConfig.from_dict(pinned.as_dict()) == pinned
    for relative in ("lib/bin.js", "./bin.js", "bin.js"):
        with pytest.raises(ProviderConfigError, match="entrypoint must be an absolute"):
            ProviderConfig(
                provider_id="claude-code", executable=ABS_EXECUTABLE,
                protocol="fake-claude-jsonl-v1", entrypoint=relative)
    with pytest.raises(ProviderConfigError, match="entrypoint must be a NUL-free"):
        ProviderConfig(
            provider_id="claude-code", executable=ABS_EXECUTABLE,
            protocol="fake-claude-jsonl-v1", entrypoint="C:/dsh/bin.js\x00evil")


def test_provider_config_refuses_a_relative_path_or_unreviewed_protocol():
    with pytest.raises(ProviderConfigError, match="absolute"):
        ProviderConfig(
            provider_id="claude-code", executable="claude",
            protocol="fake-claude-jsonl-v1")
    with pytest.raises(ProviderConfigError, match="protocol"):
        ProviderConfig(
            provider_id="claude-code", executable=ABS_EXECUTABLE, protocol="npx-latest")
