"""An optional registered value, never an inferred fifth adapter method."""
import gc

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.base import AdapterContractError
from conductor.command.adapters.harness_workspace import HarnessWorkspace
from tests.test_command_adapters import FakeAdapter


def _scope(resource=None, calls=None):
    from conductor.command.adapters.attempt_scope import AttemptScope
    resource = object() if resource is None else resource
    calls = [] if calls is None else calls

    def acquire():
        calls.append("acquire")
        return True

    return AttemptScope(resource, acquire, lambda: calls.append("release"))


def test_scope_registration_copies_the_value_and_never_calls_its_callbacks():
    calls = []
    original = _scope(calls=calls)
    resource = original.resource
    adapter = FakeAdapter()
    adapter.attempt_scope = original
    registry = AdapterRegistry([adapter])
    object.__setattr__(original, "resource", object())
    adapter.attempt_scope = _scope()
    returned = registry.attempt_scope(adapter.manifest.adapter_id)
    assert returned.resource is resource
    object.__setattr__(returned, "acquire", lambda: calls.append("forged"))
    assert calls == []
    registered = registry.attempt_scope(adapter.manifest.adapter_id)
    registered.acquire()
    registered.release()
    assert calls == ["acquire", "release"]


def test_dynamic_unknown_attributes_do_not_opt_an_adapter_into_attempt_scope():
    calls = []

    class Dynamic(FakeAdapter):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return lambda *args, **kwargs: calls.append(name)

    adapter = Dynamic()
    registry = AdapterRegistry([adapter])
    assert registry.attempt_scope(adapter.manifest.adapter_id) is None
    assert calls == []


def test_property_getter_is_not_a_scope_discovery_door():
    calls = []

    class PropertyAdapter(FakeAdapter):
        @property
        def attempt_scope(self):
            calls.append("getter")
            raise RuntimeError("a registration must not execute this getter")

    with pytest.raises(AdapterContractError, match="attempt_scope"):
        AdapterRegistry([PropertyAdapter()])
    assert calls == []


@pytest.mark.parametrize("value", [object(), "scope", lambda: None, False])
def test_malformed_explicit_scope_refuses_before_registration_publication(value):
    registry = AdapterRegistry()
    adapter = FakeAdapter()
    adapter.attempt_scope = value
    with pytest.raises(AdapterContractError, match="attempt_scope"):
        registry.register(adapter)
    assert registry.manifests() == ()


def test_legacy_slotted_adapter_needs_only_the_existing_four_methods():
    class Slotted:
        __slots__ = ("manifest",)
        observe = FakeAdapter.observe
        prepare = FakeAdapter.prepare
        execute = FakeAdapter.execute
        verify = FakeAdapter.verify

        def __init__(self):
            self.manifest = FakeAdapter().manifest

    adapter = Slotted()
    registry = AdapterRegistry([adapter])
    assert registry.controls(adapter.manifest.adapter_id) == adapter.manifest.capabilities
    assert registry.attempt_scope(adapter.manifest.adapter_id) is None


def test_explicit_scope_slot_is_a_value_and_is_snapshotted():
    class Slotted:
        __slots__ = ("manifest", "attempt_scope")
        observe = FakeAdapter.observe
        prepare = FakeAdapter.prepare
        execute = FakeAdapter.execute
        verify = FakeAdapter.verify

    adapter = Slotted()
    adapter.manifest = FakeAdapter().manifest
    adapter.attempt_scope = _scope()
    resource = adapter.attempt_scope.resource
    registry = AdapterRegistry([adapter])
    adapter.attempt_scope = _scope()
    assert registry.attempt_scope(adapter.manifest.adapter_id).resource is resource


def test_workspace_scope_retains_the_actual_gate_across_gc_and_direct_entry(tmp_path):
    one = HarnessWorkspace.at(tmp_path, home_dir=".one-home", marker_dir=".one-markers")
    alias = HarnessWorkspace.at(tmp_path / ".", home_dir=".two-home", marker_dir=".two-markers")
    elsewhere = HarnessWorkspace.at(
        tmp_path / "other", home_dir=".one-home", marker_dir=".one-markers")
    scope = one.attempt_scope()
    resource = scope.resource
    del one
    gc.collect()
    assert alias.attempt_scope().resource is resource
    assert elsewhere.attempt_scope().resource is not resource
    scope.acquire()
    try:
        with alias.owned():
            made = alias.work_dir("own-item")
            (made / "proof.txt").write_text("owned", encoding="utf-8")
    finally:
        scope.release()
    assert (made / "proof.txt").read_text(encoding="utf-8") == "owned"
