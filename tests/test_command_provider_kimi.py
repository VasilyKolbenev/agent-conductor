"""Kimi Code is described, not driven -- and every catalogued id names a graph node.

Two relations live here. The first is the honest-unavailable one: this build
catalogues Kimi Code so the Cockpit can see it, and proves that no pin an
operator can make -- not even an executable that really exists on disk, pinned
to the exact catalogued protocol -- turns it into something that spawns. The
proof is behavioural: the resolved registry is asked to resolve the provider,
the projection is read for its controls, and the adapter class is asked for an
instance. Not one of the three yields anything a task could run through.

The second relation is the binding one: a provider id is the string a map's
role carries as its ``harness``, and the panel draws that role's badge by
resolving it through ``conductor.harnesses``. An id with no registry entry
resolves to a neutral fallback that names no product -- a provider the Cockpit
would show as an unbranded slug. So every id in the catalog is checked against
the registry itself, not against a list repeated here.
"""
from __future__ import annotations

import os

import pytest

from conductor import harnesses
from conductor.command.adapters.kimi_code import (
    KIMI_CAPABILITIES,
    KIMI_PROTOCOL,
    KIMI_PROVIDER_ID,
    KimiCodeContractAdapter,
    KimiTransportUnproven,
)
from conductor.command.adapters.provider import (
    ProviderCatalogEntry,
    ProviderConfig,
    ProviderConfigError,
    ProviderRegistry,
    provider_projection,
)
from conductor.command.providers import PROVIDER_CATALOG, resolve_providers

NOW = "2026-08-18T12:00:00Z"


class _Ids:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count}"


def _real_file(tmp_path, name: str) -> str:
    """An executable pin that REALLY exists, so availability cannot blame the disk."""
    path = tmp_path / name
    path.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    return str(path.resolve())


def _resolved(tmp_path, config: ProviderConfig):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    return resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ={})


def _contract(resolution, provider_id: str):
    """One described provider, read by identity rather than by list position."""
    return next(row for row in resolution.contracts if row.provider_id == provider_id)


def _kimi_config(tmp_path, *, protocol: str = KIMI_PROTOCOL) -> ProviderConfig:
    return ProviderConfig(
        provider_id=KIMI_PROVIDER_ID, executable=_real_file(tmp_path, "kimi.exe"),
        protocol=protocol)


# --- the provider is seen, and it is seen as offering nothing ---


def test_kimi_is_graph_visible_with_no_control_at_all(tmp_path):
    resolution = _resolved(tmp_path, _kimi_config(tmp_path))
    rows = {row["provider_id"]: row for row in provider_projection(resolution.contracts)}
    assert KIMI_PROVIDER_ID in rows
    row = rows[KIMI_PROVIDER_ID]
    assert row["availability"] == "version_mismatch"
    assert row["implementation"] == "unproven"
    assert row["controls"] == [], "an unproven transport may declare no control"
    assert "experimental" in row["display_name"].lower()


def test_an_executable_that_really_exists_still_buys_kimi_no_spawn(tmp_path):
    """Availability is not a fact about the disk here; it is a fact about proof."""
    config = _kimi_config(tmp_path)
    assert os.path.isfile(config.executable), "the pin must really be on disk"
    resolution = _resolved(tmp_path, config)
    kimi = _contract(resolution, KIMI_PROVIDER_ID)
    assert resolution.spawn_capable(KIMI_PROVIDER_ID) is False
    assert kimi.available is False
    assert kimi.availability != "available"
    assert resolution.registry.manifests() == ()


def test_no_kimi_adapter_can_be_constructed_or_driven():
    with pytest.raises(KimiTransportUnproven, match="dispatches nothing"):
        KimiCodeContractAdapter()
    # Even past the constructor -- which no caller can get past -- every seam
    # the registration door required of this class refuses on its own.
    unbuilt = KimiCodeContractAdapter.__new__(KimiCodeContractAdapter)
    with pytest.raises(KimiTransportUnproven):
        unbuilt.observe("inst-1", "run-1")
    with pytest.raises(KimiTransportUnproven):
        unbuilt.prepare(object())
    with pytest.raises(KimiTransportUnproven):
        unbuilt.execute(object())
    with pytest.raises(KimiTransportUnproven):
        unbuilt.verify(object(), object())


def test_the_door_refuses_a_control_kimi_cannot_back():
    """Closing the class: a smuggled control fails against the adapter's own schemas."""
    smuggled = ProviderCatalogEntry(
        provider_id=KIMI_PROVIDER_ID, display_name="Kimi Code",
        vendor="Moonshot AI", protocol=KIMI_PROTOCOL,
        capabilities=("observe", "dispatch"),
        schema_pairs=(("dispatch", "deep-arguments-v1"),),
        lifecycle=("execute", "observe", "prepare", "verify"),
        adapter_class=KimiCodeContractAdapter)
    with pytest.raises(ProviderConfigError, match="exact argument schema"):
        ProviderRegistry().register(smuggled, availability="executable_absent")


def test_only_a_provider_with_a_control_can_ever_resolve_available(tmp_path):
    """The relation is the control set, not the provider's name."""
    for provider_id, entry in PROVIDER_CATALOG.items():
        controls = set(entry.capabilities) - {"observe"}
        config = ProviderConfig(
            provider_id=provider_id, executable=_real_file(tmp_path, f"{provider_id}.bin"),
            protocol=entry.protocol,
            entrypoint=_real_file(tmp_path, f"{provider_id}.entry"))
        available = _contract(_resolved(tmp_path, config), provider_id).available
        assert available is bool(controls), (
            f"{provider_id}: available={available} with controls {sorted(controls)}")


def test_kimi_declares_observation_and_nothing_else():
    entry = PROVIDER_CATALOG[KIMI_PROVIDER_ID]
    assert entry.capabilities == KIMI_CAPABILITIES == ("observe",)
    assert entry.schema_pairs == ()
    assert KimiCodeContractAdapter.argument_schemas == {}


# --- every catalogued id is a graph node the panel can draw ---


def test_every_catalogued_provider_id_binds_a_registered_graph_node():
    """A role's `harness` string is the binding; an unregistered one draws no product.

    ``harnesses.resolve`` answers for ANY string, so resolving proves nothing.
    The relation is that the registry itself holds the id: ``get`` returns an
    entry, and that entry is the very object ``resolve`` hands the panel.
    """
    for provider_id in PROVIDER_CATALOG:
        registered = harnesses.get(provider_id)
        assert registered is not None, (
            f"provider id {provider_id!r} names no harness the panel can draw")
        assert harnesses.resolve(provider_id) is registered
        assert registered.monogram, "a registered harness carries its own badge"


def test_the_payload_the_panel_loads_carries_every_catalogued_provider():
    """The badge route is built from the registry, so the ids must be in its payload."""
    payload_ids = {row["id"] for row in harnesses.as_payload()}
    assert set(PROVIDER_CATALOG) <= payload_ids


def test_an_id_the_registry_never_registered_falls_back_and_names_no_product():
    """The negative half: this is what a bad provider id would get the Cockpit."""
    assert harnesses.get("kimi-code-unregistered") is None
    fallback = harnesses.resolve("kimi-code-unregistered")
    assert fallback.display_name == "kimi-code-unregistered"
    assert fallback.docs == "" and fallback.adapter == ""
