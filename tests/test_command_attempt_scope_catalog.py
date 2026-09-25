"""Every catalogued production adapter takes its turn over ONE project gate.

The in-process T5 promise holds for a provider only if its adapter declared an
attempt scope at registration, and holds ACROSS providers only if those scopes
name the same gate. Today that is true by inheritance from the shared transport
constructor; this holds the relation, so a sixth profile that forgets the
constructor cannot fall out of the serialization silently.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from conductor.command import providers
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.base import AdapterContractError
from conductor.command.adapters.process import ProcessRunner
from tests.test_command_adapters import FakeAdapter


def _catalogued_registry(root):
    runner = ProcessRunner(root, environ={})
    registry = AdapterRegistry()
    for provider_id in sorted(providers.PROVIDER_CATALOG):
        entry = providers._catalogued(providers.PROVIDER_CATALOG, provider_id)
        config = SimpleNamespace(
            provider_id=provider_id, executable=sys.executable, entrypoint=sys.executable,
            env_allow=(), auth="api_key", auth_home="", protocol=entry.protocol)
        registry.register(providers._build_adapter(
            entry, config, runner, root=root, clock=lambda: "2026-09-21T00:00:00Z",
            ids=lambda kind: f"{kind}-1"))
    return registry


def test_every_catalogued_adapter_declares_a_scope_over_the_same_project_gate(tmp_path):
    registry = _catalogued_registry(tmp_path)
    scopes = {row.adapter_id: registry.attempt_scope(row.adapter_id)
              for row in registry.manifests()}
    assert len(scopes) == len(providers.PROVIDER_CATALOG) >= 5
    undeclared = sorted(name for name, scope in scopes.items() if scope is None)
    assert undeclared == [], f"outside the attempt serialization: {undeclared}"
    assert len({id(scope.resource) for scope in scopes.values()}) == 1, (
        "providers under one project root must serialize on one gate")


@pytest.mark.parametrize("value", [object(), "scope", lambda: None, False])
def test_a_refused_scope_leaves_no_half_registered_adapter_behind(value):
    registry = AdapterRegistry()
    adapter = FakeAdapter()
    adapter.attempt_scope = value
    with pytest.raises(AdapterContractError, match="attempt_scope"):
        registry.register(adapter)
    with pytest.raises(AdapterContractError, match="not registered"):
        registry.resolve(adapter.manifest.adapter_id)
