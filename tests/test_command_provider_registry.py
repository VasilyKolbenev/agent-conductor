"""The one provider registration door: exact schemas, one identity, proven seams.

Every relation here is proven against a plugin written IN THIS FILE -- its
capabilities, its per-capability argument schemas, and its lifecycle methods are
declared here and never imported from the code under test -- so no assertion
reads both of its sides from one production value. Each refusal is followed by a
state assertion: a refused provider must leave the door's descriptors and its
spawn surface exactly as they were.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters import AdapterContractError, AdapterManifest
from conductor.command.adapters.provider import (
    ProviderCatalogEntry,
    ProviderConfigError,
    ProviderRegistry,
    provider_projection,
)

CONTROLS = ("dispatch", "stop")
CAPABILITIES = ("observe", *CONTROLS)
SCHEMA = "deep-arguments-v1"
LIFECYCLE = ("observe", "prepare", "execute", "verify")


class PluginAdapter:
    """A test-owned plugin: it binds one reviewed schema to each control it declares."""

    argument_schemas = {"dispatch": SCHEMA, "stop": SCHEMA}

    def __init__(self, adapter_id: str = "plugin") -> None:
        self.manifest = AdapterManifest(
            adapter_id=adapter_id, display_name="Plugin", vendor="Test",
            version="fake-claude-jsonl-v1", capabilities=CAPABILITIES)

    def observe(self, instance_id: str, run_id: str) -> None:
        raise NotImplementedError("no session-1 test drives a lifecycle seam")

    def prepare(self, request: object) -> None:
        raise NotImplementedError("no session-1 test drives a lifecycle seam")

    def execute(self, prepared: object) -> None:
        raise NotImplementedError("no session-1 test drives a lifecycle seam")

    def verify(self, request: object, result: object) -> None:
        raise NotImplementedError("no session-1 test drives a lifecycle seam")


class HalfSchemaAdapter(PluginAdapter):
    """The same plugin, binding a schema to only one of the two controls it declares."""

    argument_schemas = {"dispatch": SCHEMA}


def _entry(**changes) -> ProviderCatalogEntry:
    values = {
        "provider_id": "plugin", "display_name": "Plugin", "vendor": "Test",
        "protocol": "fake-claude-jsonl-v1", "capabilities": CAPABILITIES,
        "schema_pairs": [(control, SCHEMA) for control in CONTROLS],
        "lifecycle": LIFECYCLE, "adapter_class": PluginAdapter,
    }
    values.update(changes)
    return ProviderCatalogEntry(**values)


def test_the_door_admits_a_plugin_that_binds_a_schema_to_every_declared_control():
    door = ProviderRegistry()
    adapter = PluginAdapter()
    contract = door.register(_entry(), availability="available", adapter=adapter)
    assert contract.available is True
    assert [row.provider_id for row in door.contracts()] == ["plugin"]
    assert door.adapters.resolve("plugin") is adapter
    assert provider_projection(door.contracts()) == [
        {"provider_id": "plugin", "display_name": "Plugin",
         "availability": "available", "implementation": "unproven",
         "controls": ["dispatch", "stop"]}]


def test_a_plugin_missing_a_schema_for_a_declared_control_is_refused_at_registration():
    door = ProviderRegistry()
    with pytest.raises(ProviderConfigError, match="adapter's own exact argument schema"):
        door.register(
            _entry(adapter_class=HalfSchemaAdapter), availability="available",
            adapter=HalfSchemaAdapter())
    assert door.contracts() == ()
    assert door.adapters.manifests() == ()


def test_a_declared_schema_the_adapter_does_not_own_is_refused_at_registration():
    """The door reads the RELATION, not just a reviewed schema name."""
    door = ProviderRegistry()
    invented = [("dispatch", "structured-process-v1"), ("stop", SCHEMA)]
    with pytest.raises(ProviderConfigError, match="adapter's own exact argument schema"):
        door.register(
            _entry(schema_pairs=invented), availability="available",
            adapter=PluginAdapter())
    assert door.contracts() == ()


def test_a_second_provider_with_a_registered_identity_is_refused_and_changes_nothing():
    door = ProviderRegistry()
    first = PluginAdapter()
    door.register(_entry(), availability="available", adapter=first)
    with pytest.raises(ProviderConfigError, match="already registered"):
        door.register(
            _entry(display_name="Impostor"), availability="available",
            adapter=PluginAdapter())
    # The same refusal without an adapter, so only the door's own identity check
    # can produce it: the adapter registry is never reached on this path.
    with pytest.raises(ProviderConfigError, match="already registered"):
        door.register(_entry(display_name="Impostor"), availability="executable_absent")
    assert [row.display_name for row in door.contracts()] == ["Plugin"]
    assert door.adapters.resolve("plugin") is first


def test_a_repeated_capability_or_a_repeated_schema_row_never_survives_the_door():
    door = ProviderRegistry()
    repeated_capability = _entry()
    object.__setattr__(  # bypass the value gate the constructor already ran
        repeated_capability, "capabilities", ("observe", "dispatch", "dispatch", "stop"))
    with pytest.raises(ProviderConfigError, match="remain canonical"):
        door.register(repeated_capability, availability="executable_absent")
    repeated_row = _entry()
    object.__setattr__(
        repeated_row, "schema_pairs",
        (("dispatch", SCHEMA), ("dispatch", SCHEMA), ("stop", SCHEMA)))
    with pytest.raises(ProviderConfigError, match="remain canonical"):
        door.register(repeated_row, availability="executable_absent")
    assert door.contracts() == ()


def test_a_hostile_catalog_entry_subclass_is_refused_before_its_as_data_can_lie():
    class ForgedEntry(ProviderCatalogEntry):
        def as_data(self):
            raise AssertionError("the door must never read a subclass's own as_data")

    door = ProviderRegistry()
    forged = ForgedEntry(
        provider_id="plugin", display_name="Plugin", vendor="Test",
        protocol="fake-claude-jsonl-v1", capabilities=CAPABILITIES,
        schema_pairs=[(control, SCHEMA) for control in CONTROLS],
        lifecycle=LIFECYCLE, adapter_class=PluginAdapter)
    with pytest.raises(ProviderConfigError, match="exact ProviderCatalogEntry"):
        door.register(forged, availability="available", adapter=PluginAdapter())
    assert door.contracts() == ()


def test_a_lifecycle_seam_the_adapter_class_does_not_implement_is_refused():
    door = ProviderRegistry()
    with pytest.raises(ProviderConfigError, match="lifecycle seams"):
        door.register(
            _entry(lifecycle=(*LIFECYCLE, "recover")), availability="executable_absent")
    assert door.contracts() == ()
    admitted = door.register(_entry(), availability="executable_absent")
    assert admitted.lifecycle == ("execute", "observe", "prepare", "verify")


def test_an_unavailable_provider_owns_a_descriptor_and_no_spawnable_adapter():
    door = ProviderRegistry()
    contract = door.register(_entry(), availability="executable_absent")
    assert contract.available is False
    assert [row.provider_id for row in door.contracts()] == ["plugin"]
    assert door.adapters.manifests() == ()
    with pytest.raises(AdapterContractError, match="not registered"):
        door.adapters.resolve("plugin")


def test_an_adapter_offered_for_an_unavailable_provider_is_refused():
    door = ProviderRegistry()
    with pytest.raises(ProviderConfigError, match="no adapter to spawn"):
        door.register(
            _entry(), availability="executable_absent", adapter=PluginAdapter())
    assert door.contracts() == ()
    assert door.adapters.manifests() == ()


def test_an_available_provider_requires_an_instance_of_its_catalogued_adapter():
    door = ProviderRegistry()
    with pytest.raises(ProviderConfigError, match="catalogued adapter"):
        door.register(_entry(), availability="available")
    with pytest.raises(ProviderConfigError, match="catalogued adapter"):
        door.register(_entry(), availability="available", adapter=HalfSchemaAdapter())
    assert door.contracts() == ()
    assert door.adapters.manifests() == ()


def test_an_adapter_carrying_another_identity_is_refused():
    door = ProviderRegistry()
    with pytest.raises(ProviderConfigError, match="adapter identity"):
        door.register(
            _entry(), availability="available", adapter=PluginAdapter("someone-else"))
    assert door.contracts() == ()
    assert door.adapters.manifests() == ()


def test_an_unreviewed_availability_state_is_refused():
    door = ProviderRegistry()
    with pytest.raises(ProviderConfigError, match="reviewed state"):
        door.register(_entry(), availability="probably")
    assert door.contracts() == ()


def test_the_door_hands_out_rebuilt_descriptors_never_the_value_it_stores():
    door = ProviderRegistry()
    door.register(_entry(), availability="available", adapter=PluginAdapter())
    handed = door.contracts()[0]
    object.__setattr__(handed, "display_name", "Rewritten")
    assert [row.display_name for row in door.contracts()] == ["Plugin"]
