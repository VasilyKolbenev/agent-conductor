"""The provider factory/config seam: availability resolution and honest wiring.

The factory turns operator config into a runtime registry plus per-provider
descriptors. A provider that is absent or version-mismatched resolves UNAVAILABLE
and builds no adapter, so it can never spawn (spawn count 0); only an available
provider's adapter enters the registry. The default (no configs) stays empty, so
the production server never pretends a real provider is available. Availability is
a real filesystem relation here: the "present" executable is an actual file on
disk and the "absent" one is a path that was never created.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from conductor import server
from conductor.command import providers as provider_factory
from conductor.command.adapters import AdapterContractError, AdapterRegistry
from conductor.command.adapters.provider import ProviderConfig, provider_projection
from conductor.command.contracts import canonical_json
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers
from tests.test_store import good_lane, write_project

NOW = "2026-08-17T10:00:00Z"


def _ids():
    counts: dict[str, int] = {}

    def mint(kind: str) -> str:
        counts[kind] = counts.get(kind, 0) + 1
        return f"{kind}-{counts[kind]}"

    return mint


def _config(provider_id: str, executable: str, protocol: str) -> ProviderConfig:
    return ProviderConfig(
        provider_id=provider_id, executable=executable, protocol=protocol, env_allow=())


def _present(tmp_path: Path, name: str) -> str:
    executable = tmp_path / name
    executable.write_text("", encoding="utf-8")
    return str(executable)


def _counted_runner(monkeypatch) -> dict[str, int]:
    """Replace the owned runner with a counter, so spawns are counted, not assumed."""
    counts = {"constructed": 0, "spawned": 0}

    class CountingRunner:
        def __init__(self, root, environ=None) -> None:
            counts["constructed"] += 1

        def run(self, spec):
            counts["spawned"] += 1
            raise AssertionError("no provider may spawn while resolving availability")

    monkeypatch.setattr(provider_factory, "ProcessRunner", CountingRunner)
    return counts


def _resolved_availability(resolution) -> dict:
    """Every described provider's resolved state, keyed by identity, never by order."""
    return {row.provider_id: row.availability for row in resolution.contracts}


def test_an_available_provider_registers_its_adapter_and_is_spawn_capable(tmp_path):
    executable = _present(tmp_path, "claude.exe")
    resolution = resolve_providers(
        [_config("claude-code", executable, "fake-claude-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    resolved = _resolved_availability(resolution)
    assert set(resolved) == set(PROVIDER_CATALOG)
    assert resolved["claude-code"] == "available"
    # Only the provider the operator pinned was looked at on disk; the rest of
    # the reviewed roster is described without anything being probed for it.
    assert set(resolved.values()) - {"available"} == {"unconfigured"}
    assert resolution.registry.resolve("claude-code").manifest.adapter_id == "claude-code"
    assert resolution.spawn_capable("claude-code") is True


def test_a_provider_with_an_absent_executable_resolves_unavailable_and_never_registers(tmp_path):
    missing = str(tmp_path / "not-installed.exe")  # deliberately never created
    resolution = resolve_providers(
        [_config("claude-code", missing, "fake-claude-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    assert resolution.contracts[0].availability == "executable_absent"
    assert resolution.contracts[0].available is False
    assert resolution.registry.manifests() == ()
    assert resolution.spawn_capable("claude-code") is False
    with pytest.raises(AdapterContractError, match="not registered"):
        resolution.registry.resolve("claude-code")


def test_a_provider_pinned_to_the_wrong_protocol_resolves_version_mismatch(tmp_path):
    missing = str(tmp_path / "nope.exe")
    resolution = resolve_providers(
        [_config("claude-code", missing, "fake-codex-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    assert resolution.contracts[0].availability == "version_mismatch"
    assert resolution.contracts[0].available is False
    assert resolution.spawn_capable("claude-code") is False


def test_two_configs_for_one_provider_are_refused(tmp_path):
    missing = str(tmp_path / "nope.exe")
    with pytest.raises(Exception, match="more than once"):
        resolve_providers(
            [_config("claude-code", missing, "fake-claude-jsonl-v1"),
             _config("claude-code", missing, "fake-claude-jsonl-v1")],
            root=tmp_path, clock=lambda: NOW, ids=_ids())


def test_a_config_naming_an_uncatalogued_provider_is_refused(tmp_path):
    with pytest.raises(Exception, match="not in the reviewed catalog"):
        resolve_providers(
            [_config("cursor", "/opt/cursor/bin/cursor", "fake-claude-jsonl-v1")],
            root=tmp_path, clock=lambda: NOW, ids=_ids())


def test_the_default_resolution_spawns_nothing_and_calls_every_provider_unconfigured(
        tmp_path):
    """With no operator config the roster is describable and nothing is runnable."""
    resolution = resolve_providers([], root=tmp_path, clock=lambda: NOW, ids=_ids())
    assert _resolved_availability(resolution) == {
        provider_id: "unconfigured" for provider_id in PROVIDER_CATALOG}
    assert resolution.registry.manifests() == ()
    assert not any(
        resolution.spawn_capable(provider_id) for provider_id in PROVIDER_CATALOG)


def test_both_fake_adapters_register_through_the_factory(tmp_path):
    resolution = resolve_providers(
        [_config("claude-code", _present(tmp_path, "claude.exe"), "fake-claude-jsonl-v1"),
         _config("codex", _present(tmp_path, "codex.exe"), "fake-codex-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    assert [row.adapter_id for row in resolution.registry.manifests()] == ["claude-code", "codex"]
    rows = provider_projection(resolution.contracts)
    assert {row["provider_id"] for row in rows} == set(PROVIDER_CATALOG)
    configured = {row["provider_id"]: row for row in rows}
    assert [configured[name]["availability"] for name in ("claude-code", "codex")] == [
        "available", "available"]
    assert all("observe" not in row["controls"] for row in rows)


def test_an_unavailable_provider_reaches_no_runner_and_spawns_nothing(tmp_path, monkeypatch):
    counts = _counted_runner(monkeypatch)
    resolution = resolve_providers(
        [_config("claude-code", str(tmp_path / "missing.exe"), "fake-claude-jsonl-v1"),
         _config("codex", str(tmp_path / "also-missing.exe"), "fake-claude-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    resolved = _resolved_availability(resolution)
    assert (resolved["claude-code"], resolved["codex"]) == (
        "executable_absent", "version_mismatch")
    assert counts == {"constructed": 0, "spawned": 0}
    assert resolution.registry.manifests() == ()


def test_an_available_provider_builds_one_runner_and_still_spawns_nothing(
        tmp_path, monkeypatch):
    counts = _counted_runner(monkeypatch)
    resolution = resolve_providers(
        [_config("claude-code", _present(tmp_path, "claude.exe"), "fake-claude-jsonl-v1"),
         _config("codex", _present(tmp_path, "codex.exe"), "fake-codex-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    assert counts == {"constructed": 1, "spawned": 0}
    assert resolution.spawn_capable("claude-code") is True


def test_the_factory_admits_nothing_the_registration_door_would_refuse(tmp_path):
    """Only the door proves a lifecycle claim, so refusing here proves it was used."""
    unbacked = replace(
        PROVIDER_CATALOG["claude-code"],
        lifecycle=("observe", "prepare", "execute", "verify", "recover"))
    with pytest.raises(Exception, match="lifecycle seams"):
        resolve_providers(
            [_config("claude-code", _present(tmp_path, "claude.exe"), "fake-claude-jsonl-v1")],
            root=tmp_path, clock=lambda: NOW, ids=_ids(),
            catalog={"claude-code": unbacked})


def test_a_catalog_key_that_disagrees_with_its_entry_is_refused(tmp_path):
    forged = {"claude-code": PROVIDER_CATALOG["codex"]}
    with pytest.raises(Exception, match="does not match its catalog key"):
        resolve_providers(
            [_config("claude-code", _present(tmp_path, "claude.exe"), "fake-codex-jsonl-v1")],
            root=tmp_path, clock=lambda: NOW, ids=_ids(), catalog=forged)


def test_no_pinned_path_or_secret_name_reaches_a_provider_descriptor(tmp_path):
    executable = _present(tmp_path, "claude.exe")
    resolution = resolve_providers(
        [_config("claude-code", executable, "fake-claude-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    blob = (canonical_json([row.as_dict() for row in resolution.contracts])
            + canonical_json(provider_projection(resolution.contracts)))
    assert executable not in blob
    for banned in ("argv", "cwd", "shell", "token", "secret", "pid", "raw_output"):
        assert banned not in blob


def test_build_resolves_provider_config_into_the_command_registry(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    executable = _present(Path(root), "claude.exe")
    subject = server.build(
        root, 0, providers=[_config("claude-code", executable, "fake-claude-jsonl-v1")],
        clock=lambda: NOW, ids=_ids())
    try:
        adapter = subject.command_registry.resolve("claude-code")
        assert adapter.manifest.adapter_id == "claude-code"
        resolved = {row.provider_id: row.availability
                    for row in subject.command_providers}
        assert resolved["claude-code"] == "available"
        assert set(resolved) == set(PROVIDER_CATALOG)
    finally:
        subject.server_close()


def test_build_without_providers_keeps_the_command_registry_empty(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    subject = server.build(root, 0, clock=lambda: NOW, ids=_ids())
    try:
        assert subject.command_registry.manifests() == ()
        assert {row.availability for row in subject.command_providers} == {
            "unconfigured"}
    finally:
        subject.server_close()


def test_build_refuses_an_explicit_registry_beside_provider_config(tmp_path):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    executable = _present(Path(root), "claude.exe")
    with pytest.raises(Exception, match="not both"):
        server.build(
            root, 0, registry=AdapterRegistry(),
            providers=[_config("claude-code", executable, "fake-claude-jsonl-v1")],
            clock=lambda: NOW, ids=_ids())
