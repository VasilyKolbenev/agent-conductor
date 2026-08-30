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
from conductor.command.adapters.claude_code import CLAUDE_PROTOCOL
from conductor.command.adapters.codex_cli import CODEX_PROTOCOL
from conductor.command.adapters.dsh_harness import DSH_PROTOCOL
from conductor.command.adapters.process import ProcessRunner
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

    class CountingRunner(ProcessRunner):
        """A real runner that counts, rather than a stand-in that resembles one.

        It SUBCLASSES `ProcessRunner` deliberately. A headless transport refuses
        anything else at construction -- "spawns only through an owned runner" --
        and that refusal is a relation this suite must not route around by
        handing the factory a duck-typed double. Counting is added; nothing is
        replaced but `run`, which asserts rather than spawning.
        """

        def __init__(self, root, environ=None) -> None:
            super().__init__(root, environ=environ)
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
        [_config("claude-code", executable, CLAUDE_PROTOCOL)],
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
        [_config("claude-code", missing, CLAUDE_PROTOCOL)],
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
            [_config("claude-code", missing, CLAUDE_PROTOCOL),
             _config("claude-code", missing, CLAUDE_PROTOCOL)],
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


def test_two_configured_providers_both_register_through_the_factory(tmp_path):
    """Two REAL transports, which is what the roster now holds -- all of it.

    It used to be "both fake adapters", then "one real transport and one
    fixture", and the rewording each time is the point: a test whose name or
    docstring promised a roster that no longer exists would keep passing while
    describing nothing. `codex` was the last fixture row, and it is gone.
    """
    resolution = resolve_providers(
        [_config("claude-code", _present(tmp_path, "claude.exe"), CLAUDE_PROTOCOL),
         _config("codex", _present(tmp_path, "codex.exe"), CODEX_PROTOCOL)],
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
        [_config("claude-code", str(tmp_path / "missing.exe"), CLAUDE_PROTOCOL),
         _config("codex", str(tmp_path / "also-missing.exe"), "fake-claude-jsonl-v1")],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    resolved = _resolved_availability(resolution)
    assert (resolved["claude-code"], resolved["codex"]) == (
        "executable_absent", "version_mismatch")
    assert counts == {"constructed": 0, "spawned": 0}
    assert resolution.registry.manifests() == ()


def test_an_available_provider_builds_one_runner_and_still_spawns_nothing(
        tmp_path, monkeypatch):
    """ONE runner for TWO available providers, and it starts nothing.

    Both configs must really resolve available or the count of one proves
    nothing: this passed for a while with the second provider version-mismatched,
    where one runner for one provider is all it could ever have been.
    """
    counts = _counted_runner(monkeypatch)
    resolution = resolve_providers(
        [_config("claude-code", _present(tmp_path, "claude.exe"), CLAUDE_PROTOCOL),
         _config("codex", _present(tmp_path, "codex.exe"), CODEX_PROTOCOL)],
        root=tmp_path, clock=lambda: NOW, ids=_ids())
    assert _resolved_availability(resolution)["codex"] == "available"
    assert counts == {"constructed": 1, "spawned": 0}
    assert resolution.spawn_capable("claude-code") is True
    assert resolution.spawn_capable("codex") is True


def test_the_factory_admits_nothing_the_registration_door_would_refuse(tmp_path):
    """Only the door proves a lifecycle claim, so refusing here proves it was used."""
    unbacked = replace(
        PROVIDER_CATALOG["claude-code"],
        lifecycle=("observe", "prepare", "execute", "verify", "recover"))
    with pytest.raises(Exception, match="lifecycle seams"):
        resolve_providers(
            [_config("claude-code", _present(tmp_path, "claude.exe"), CLAUDE_PROTOCOL)],
            root=tmp_path, clock=lambda: NOW, ids=_ids(),
            catalog={"claude-code": unbacked})


def test_a_catalog_key_that_disagrees_with_its_entry_is_refused(tmp_path):
    forged = {"claude-code": PROVIDER_CATALOG["codex"]}
    with pytest.raises(Exception, match="does not match its catalog key"):
        resolve_providers(
            [_config("claude-code", _present(tmp_path, "claude.exe"), CODEX_PROTOCOL)],
            root=tmp_path, clock=lambda: NOW, ids=_ids(), catalog=forged)


def test_no_pinned_path_or_secret_name_reaches_a_provider_descriptor(tmp_path):
    executable = _present(tmp_path, "claude.exe")
    resolution = resolve_providers(
        [_config("claude-code", executable, CLAUDE_PROTOCOL)],
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
        root, 0, providers=[_config("claude-code", executable, CLAUDE_PROTOCOL)],
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
            providers=[_config("claude-code", executable, CLAUDE_PROTOCOL)],
            clock=lambda: NOW, ids=_ids())


# -- the PIN SHAPE, which availability judges and nothing held ---------------
#
# Two arms of `_resolve_availability` decide whether the operator pinned the
# right NUMBER of files: an interpreter-backed provider must name a second
# absolute path, and a single-executable one may not. Deleting either arm left
# all 199 tests across every provider module green, which is how `conduct
# providers` came to offer the same "optional entrypoint" question to all five
# rows and write two kinds of config the server would then refuse. The wizard's
# own tests cannot cover this any more -- it can no longer express either
# mistake -- so the rule is held here, where it lives.


def _contract(resolution, provider_id: str):
    """The descriptor for one provider, found by identity rather than position.

    `_catalogued_ids` puts the configured rows first, so index 0 is the
    configured one for a single-config resolution -- but that is an ordering
    detail, and a test that reads it measures the ordering as well as the rule.
    """
    found = [row for row in resolution.contracts
             if row.provider_id == provider_id]
    assert len(found) == 1, [row.provider_id for row in resolution.contracts]
    return found[0]


def _pinned(tmp_path: Path, provider_id: str, protocol: str, *,
            entrypoint: str | None) -> ProviderConfig:
    """A config whose files all exist, so only the SHAPE can make it unavailable."""
    return ProviderConfig(
        provider_id=provider_id, executable=_present(tmp_path, "interpreter"),
        protocol=protocol, env_allow=(),
        entrypoint="" if entrypoint is None else entrypoint)


def test_an_interpreter_backed_provider_with_no_entrypoint_is_unavailable(tmp_path):
    """An interpreter with nothing to run is not a usable provider.

    Both files are present, so `executable_absent` here is a statement about the
    pin's SHAPE and not about the disk -- which is what makes it the right
    answer: there is a second file, and the operator named none.
    """
    resolution = resolve_providers(
        [_pinned(tmp_path, "deepseek-harness", DSH_PROTOCOL, entrypoint=None)],
        root=tmp_path, clock=lambda: NOW, ids=_ids())

    assert _contract(resolution, "deepseek-harness").availability == (
        "executable_absent")
    assert resolution.spawn_capable("deepseek-harness") is False


def test_an_interpreter_backed_provider_with_both_halves_is_available(tmp_path):
    """The over-correction control: the arm above must not refuse a good pin."""
    resolution = resolve_providers(
        [_pinned(tmp_path, "deepseek-harness", DSH_PROTOCOL,
                 entrypoint=_present(tmp_path, "agent.py"))],
        root=tmp_path, clock=lambda: NOW, ids=_ids())

    assert _contract(resolution, "deepseek-harness").availability == "available"
    assert resolution.spawn_capable("deepseek-harness") is True


def test_a_single_executable_provider_pinned_with_an_entrypoint_is_unavailable(
        tmp_path):
    """The mirror image, and it is answered as unavailability rather than raised.

    Raising from the adapter factory took down the whole roster: `conduct up`
    does not catch `ProviderConfigError`, so one operator typo ended the server
    with a traceback and no descriptor for any provider at all.
    """
    resolution = resolve_providers(
        [_pinned(tmp_path, "claude-code", CLAUDE_PROTOCOL,
                 entrypoint=_present(tmp_path, "extra.js"))],
        root=tmp_path, clock=lambda: NOW, ids=_ids())

    assert _contract(resolution, "claude-code").availability == "version_mismatch"
    assert resolution.spawn_capable("claude-code") is False


def test_a_single_executable_provider_with_one_file_is_available(tmp_path):
    """The over-correction control for the mirror arm."""
    resolution = resolve_providers(
        [_pinned(tmp_path, "claude-code", CLAUDE_PROTOCOL, entrypoint=None)],
        root=tmp_path, clock=lambda: NOW, ids=_ids())

    assert _contract(resolution, "claude-code").availability == "available"
    assert resolution.spawn_capable("claude-code") is True


def test_the_pin_shape_rule_covers_every_catalogued_protocol():
    """No catalogued provider may have an unstated pin shape.

    `optional` is honest for a protocol this build does not catalogue -- nothing
    constrains such a pin either way. It is NOT honest for one that ships: a
    catalogued row whose shape nobody has decided is a row an operator can pin
    two ways, one of which the server will refuse without saying so.
    """
    unstated = sorted(
        entry.protocol for entry in PROVIDER_CATALOG.values()
        if provider_factory.entrypoint_rule(entry.protocol)
        == provider_factory.ENTRYPOINT_OPTIONAL)

    assert unstated == []
