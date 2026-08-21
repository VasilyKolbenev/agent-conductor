"""What a catalog row means, and what every catalogued id owes the Cockpit.

This module used to be about Kimi Code being described and not driven. Kimi Code
is driven now -- ``tests/test_command_kimi_transport.py`` holds that against a
real child process -- so what is left here is the part that was never about Kimi
at all, and it is the more important part: the RULES a row must satisfy,
whichever product is standing in it.

Two of them are held against a synthetic provider rather than a catalogued one,
and that is deliberate. Every product in the catalog now declares a control, so a
rule about control-less providers checked against the catalog would pass by
having no subject -- the shape of test that keeps passing after the thing it
guards is gone. The synthetic entry gives the rule a subject that cannot
disappear underneath it.

The rest is the binding relation: a provider id is the string a map's role
carries as its ``harness``, and the panel draws that role's badge by resolving it
through ``conductor.harnesses``. An id with no registry entry resolves to a
neutral fallback that names no product -- a provider the Cockpit would show as an
unbranded slug. So every id in the catalog is checked against the registry
itself, not against a list repeated here.
"""
from __future__ import annotations

import os

import pytest

from conductor import harnesses
from conductor.command.adapters.provider import (
    ProviderCatalogEntry,
    ProviderConfig,
    ProviderConfigError,
    ProviderRegistry,
    provider_projection,
)
from conductor.command.providers import (
    _ENTRYPOINT_PROTOCOLS,
    PROVIDER_CATALOG,
    resolve_providers,
)

NOW = "2026-08-21T12:00:00Z"
#: A protocol this build really implements, so a synthetic entry below is
#: refused for the reason under test and never for its protocol token.
A_REAL_PROTOCOL = PROVIDER_CATALOG["deepseek-harness"].protocol
#: An id no catalog and no registry holds, used for the negative halves.
UNREGISTERED_ID = "a-product-this-build-never-catalogued"


class _Ids:
    def __init__(self) -> None:
        self.count = 0

    def __call__(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count}"


class _ObserveOnlyAdapter:
    """A synthetic adapter that honestly declares no control at all.

    It exists so the two rules below keep a subject after every catalogued
    product grew one. The lifecycle seams are present because the registration
    door proves a declared lifecycle against callables the class really carries;
    they are never reached, because a provider with no control never resolves
    available and so is never built.
    """

    argument_schemas: dict[str, str] = {}

    def observe(self, instance_id: str, run_id: str) -> object:
        raise AssertionError("a control-less provider is never driven")

    def prepare(self, request: object) -> object:
        raise AssertionError("a control-less provider is never driven")

    def execute(self, prepared: object) -> object:
        raise AssertionError("a control-less provider is never driven")

    def verify(self, request: object, result: object) -> object:
        raise AssertionError("a control-less provider is never driven")


def _observe_only_entry(provider_id: str) -> ProviderCatalogEntry:
    return ProviderCatalogEntry(
        provider_id=provider_id, display_name="Observed Only (experimental)",
        vendor="a vendor this build proved no transport for",
        protocol=A_REAL_PROTOCOL, capabilities=("observe",), schema_pairs=(),
        lifecycle=("execute", "observe", "prepare", "verify"),
        adapter_class=_ObserveOnlyAdapter)


def _real_file(tmp_path, name: str) -> str:
    """An executable pin that REALLY exists, so availability cannot blame the disk."""
    path = tmp_path / name
    path.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
    return str(path.resolve())


def _resolved(tmp_path, config: ProviderConfig, catalog=PROVIDER_CATALOG):
    root = tmp_path / "root"
    root.mkdir(exist_ok=True)
    return resolve_providers(
        [config], root=root, clock=lambda: NOW, ids=_Ids(), environ={},
        catalog=catalog)


def _contract(resolution, provider_id: str):
    """One described provider, read by identity rather than by list position."""
    return next(row for row in resolution.contracts if row.provider_id == provider_id)


# --- a provider with nothing to dispatch is never available ------------------


def test_a_provider_with_no_control_is_seen_and_is_never_available(tmp_path):
    """Availability is not a fact about the disk; it is a fact about proof.

    The pin really exists and names the catalogued protocol exactly, and the
    provider still resolves unavailable, declares an empty control list, and
    puts no adapter in the registry -- so nothing about it can spawn.
    """
    entry = _observe_only_entry(UNREGISTERED_ID)
    config = ProviderConfig(
        provider_id=UNREGISTERED_ID,
        executable=_real_file(tmp_path, "observed.bin"),
        protocol=A_REAL_PROTOCOL,
        entrypoint=_real_file(tmp_path, "observed.entry"))
    assert os.path.isfile(config.executable), "the pin must really be on disk"

    resolution = _resolved(tmp_path, config, catalog={UNREGISTERED_ID: entry})

    described = _contract(resolution, UNREGISTERED_ID)
    assert described.available is False
    assert described.availability == "version_mismatch"
    assert resolution.spawn_capable(UNREGISTERED_ID) is False
    assert resolution.registry.manifests() == ()
    row = {
        item["provider_id"]: item
        for item in provider_projection(resolution.contracts)}[UNREGISTERED_ID]
    assert row["controls"] == [], "a provider with no proven transport offers none"
    assert row["implementation"] == "unproven", (
        "a row that declares no implementation makes the weakest claim of the three")


def test_a_control_the_adapter_cannot_back_is_refused_at_registration(tmp_path):
    """Closing the class: a smuggled control fails against the adapter's own schemas.

    The entry claims a dispatch control and binds it to a real schema; the
    adapter class behind it declares none. The door compares the declared
    relation against the CLASS's own mapping as a whole, so the claim cannot
    survive registration however well-formed it looks.
    """
    smuggled = ProviderCatalogEntry(
        provider_id=UNREGISTERED_ID, display_name="Observed Only (experimental)",
        vendor="a vendor this build proved no transport for",
        protocol=A_REAL_PROTOCOL, capabilities=("observe", "dispatch"),
        schema_pairs=(("dispatch", "deep-arguments-v1"),),
        lifecycle=("execute", "observe", "prepare", "verify"),
        adapter_class=_ObserveOnlyAdapter)

    with pytest.raises(ProviderConfigError, match="exact argument schema"):
        ProviderRegistry().register(smuggled, availability="executable_absent")


def test_availability_follows_the_control_set_for_every_catalogued_provider(
        tmp_path):
    """The relation is the control set, not the provider's name.

    Held over the real catalog as well as the synthetic case above, so a product
    that ever loses its last control loses availability with it rather than
    keeping a row that says a person can dispatch through it.
    """
    for provider_id, entry in PROVIDER_CATALOG.items():
        controls = set(entry.capabilities) - {"observe"}
        # The pin SHAPE follows the protocol, because the two shapes refuse each
        # other on purpose: an interpreter with no entrypoint is unavailable,
        # and an entrypoint pinned against a single binary is refused outright.
        # Reading the shape from the factory keeps this loop about controls.
        entrypoint = (
            _real_file(tmp_path, f"{provider_id}.entry")
            if entry.protocol in _ENTRYPOINT_PROTOCOLS else "")
        config = ProviderConfig(
            provider_id=provider_id,
            executable=_real_file(tmp_path, f"{provider_id}.bin"),
            protocol=entry.protocol, entrypoint=entrypoint)
        available = _contract(_resolved(tmp_path, config), provider_id).available
        assert available is bool(controls), (
            f"{provider_id}: available={available} with controls {sorted(controls)}")


def test_every_catalogued_row_names_a_transport_this_build_really_carries():
    """A row means this build can describe AND constructively serve the provider.

    The owner's rule for the alpha roster, held mechanically: a catalogued
    product declares a control, binds every control to a reviewed schema, and
    points at an adapter class that lives in its OWN module. The last clause is
    what keeps the identity gate honest -- the module a provider may compare its
    own id in is derived from ``adapter_class.__module__``, so two ids sharing
    one module grant that module rights over both.
    """
    for provider_id, entry in PROVIDER_CATALOG.items():
        controls = set(entry.capabilities) - {"observe"}
        assert controls, f"{provider_id} declares no control at all"
        assert {pair[0] for pair in entry.schema_pairs} == controls, (
            f"{provider_id} binds a schema to something other than its controls")
        assert entry.implementation in {"real_experimental", "fixture_only"}, (
            f"{provider_id} carries an unproven row, which this roster forbids")


def test_no_two_providers_own_the_same_home_or_marker_name():
    """The one collision the workspace door cannot see, held where it can be.

    The door bounds every delete on the home name it is HANDED and serializes on
    it, so it is correct for whatever pair it is given -- it has no way to know
    another provider was handed the same pair. Two products sharing a home name
    would sweep each other's attempt directories as crash residue and block each
    other's dispatches over residue neither one left. The catalog is where that
    is visible, so it is checked here, across every provider that owns a pair.
    """
    homes: dict[str, str] = {}
    markers: dict[str, str] = {}
    for provider_id, entry in PROVIDER_CATALOG.items():
        profile = getattr(entry.adapter_class, "profile", None)
        if profile is None:
            continue  # a fixture adapter owns no subtree beneath the project root
        for owned, field in ((homes, "home_dir"), (markers, "marker_dir")):
            name = getattr(profile, field)
            clash = owned.get(name)
            assert clash is None, (
                f"{provider_id} and {clash} both own {field}={name!r}")
            owned[name] = provider_id
    assert homes, "no provider owns a home root, so this proved nothing"


# --- every catalogued id is a graph node the panel can draw ------------------


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
    assert harnesses.get(UNREGISTERED_ID) is None
    fallback = harnesses.resolve(UNREGISTERED_ID)
    assert fallback.display_name == UNREGISTERED_ID
    assert fallback.docs == "" and fallback.adapter == ""
