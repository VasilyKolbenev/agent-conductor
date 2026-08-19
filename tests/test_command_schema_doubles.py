"""The adapter doubles that DECLARE how they read a capability's arguments.

`FakeAdapter` declares no `argument_schemas` at all, so the registry's per-pair
validation is a no-op for it -- which is exactly how a door consulting only the
global argument table passed every test while it let a plan no adapter could
execute become durable. These doubles exist to make a PAIR say something, and
they are split out of `test_command_adapters.py` before that module reaches its
line cap rather than after.

Each is registered through the real `AdapterRegistry`, so what any of them
claims in a class body is only true here if the registry recorded it.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.base import AdapterRegistry
from conductor.command.adapters.deep_adapters import DEEP_ARGUMENT_SCHEMA

from tests.test_command_adapters import FakeAdapter


class DeepDispatchAdapter(FakeAdapter):
    """A fake that DECLARES the argument family real deep adapters declare.

    `FakeAdapter` declares no `argument_schemas` at all, which makes the
    registry's per-pair validation a no-op for it. That is precisely how a door
    consulting only the GLOBAL schema table looked correct under test while it
    let a plan no adapter could execute become durable, so the doubles below
    exist to make the pair say something.
    """

    argument_schemas = {"dispatch": DEEP_ARGUMENT_SCHEMA}

    def __init__(self, adapter_id="claude-code"):
        super().__init__(adapter_id=adapter_id, capabilities=("observe", "dispatch"))


class DeepPlanAdapter(FakeAdapter):
    """Deep-schema for both capabilities a PLAN can carry: dispatch and review."""

    argument_schemas = {
        "dispatch": DEEP_ARGUMENT_SCHEMA, "review": DEEP_ARGUMENT_SCHEMA}

    def __init__(self, adapter_id="claude-code"):
        super().__init__(
            adapter_id=adapter_id, capabilities=("observe", "dispatch", "review"))


class ProcessDispatchAdapter(FakeAdapter):
    """Same capability NAME, another payload family behind it."""

    argument_schemas = {"dispatch": "structured-process-v1"}

    def __init__(self, adapter_id="claude-code"):
        super().__init__(adapter_id=adapter_id, capabilities=("observe", "dispatch"))


class MixedSchemaAdapter(FakeAdapter):
    """One adapter, one family per capability -- the pair is what decides.

    It serves `review` under the family this API speaks and `dispatch` under
    another. An adapter-level answer would have to call it servable or not; only
    a per-PAIR answer can say yes to one of its capabilities and no to the
    other, which is exactly what a plan naming both needs.
    """

    argument_schemas = {
        "dispatch": "structured-process-v1", "review": DEEP_ARGUMENT_SCHEMA}

    def __init__(self, adapter_id="claude-code"):
        super().__init__(
            adapter_id=adapter_id, capabilities=("observe", "dispatch", "review"))


class RetiredCapabilityAdapter(FakeAdapter):
    """Declares a capability the frozen command API carries no schema for.

    An adapter may serve work this surface has no shape for -- a capability
    retired from the API, or one that was never in it. Declaring the family
    this API speaks does not make it writable here, and the two roads have to
    say so with the same word.
    """

    argument_schemas = {"message": DEEP_ARGUMENT_SCHEMA}

    def __init__(self, adapter_id="claude-code"):
        super().__init__(
            adapter_id=adapter_id, capabilities=("observe", "message"))


@pytest.mark.parametrize("adapter,expected", [
    (DeepDispatchAdapter, {"dispatch": DEEP_ARGUMENT_SCHEMA}),
    (DeepPlanAdapter, {"dispatch": DEEP_ARGUMENT_SCHEMA,
                       "review": DEEP_ARGUMENT_SCHEMA}),
    (ProcessDispatchAdapter, {"dispatch": "structured-process-v1"}),
    (MixedSchemaAdapter, {"dispatch": "structured-process-v1",
                          "review": DEEP_ARGUMENT_SCHEMA}),
    (RetiredCapabilityAdapter, {"message": DEEP_ARGUMENT_SCHEMA}),
    (FakeAdapter, {}),
])
def test_the_registry_records_the_family_each_double_declares(adapter, expected):
    """These doubles exist to make a PAIR say something; read back what it says.

    `FakeAdapter` declares nothing, which makes the registry's per-pair
    validation a no-op for it -- that is how a door consulting only the global
    argument table passed every test while it let a plan no adapter could
    execute become durable. The rest declare a family per capability, and what
    the REGISTRY recorded is asserted here rather than read off the class.
    """
    registry = AdapterRegistry([adapter()])
    recorded = {
        capability: registry.argument_schema("claude-code", capability)
        for capability in registry.controls("claude-code")}
    assert {name: value for name, value in recorded.items()
            if value is not None} == expected
    assert registry.argument_schema("claude-code", "observe") is None
