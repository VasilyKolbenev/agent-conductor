"""Read frozen run bindings and registered argument families without guessing.

Instance rows describe this run's deployment; the provider roster describes the
build and machine and stays a separate projection. A schema here is a registry
fact, not a deduction from argument keys or from the provider's display name.
Absent registrations have no controls and no argument families.
"""
from collections.abc import Mapping
from typing import Any

from .adapters import AdapterContractError, AdapterRegistry
from .api_contracts import ARGUMENT_SCHEMAS
from .contracts import frozen_config_bindings, frozen_config_models
from .isolation_facts import facts_for


def instance_controls(config: Mapping[str, Any],
                      registry: AdapterRegistry,
                      provider_facts: Mapping[str, Mapping[str, Any]] | None = None,
                      ) -> list[dict[str, object]]:
    """Project only declared capabilities, their schema names, and model pins.

    A null model is not a default: this run chose none. Schema absence also
    means unknown, never a shape inferred from a pending proposal's values.
    The browser can therefore distinguish an old deep-argument proposal from
    a native/process proposal without reinterpreting either one's arguments.

    ``isolation`` is the same read: what stands for THIS binding, not what this
    build can do somewhere. It is projected here rather than in the browser so
    one source answers, and the provider facts arrive as an argument because
    they belong to the machine's provider configuration rather than to this
    run's frozen bindings -- absent, every row that depends on one reads
    `unknown`, which is what an unasked question deserves.
    """
    provider_facts = dict(provider_facts or {})
    models = frozen_config_models(config)
    rows = []
    for instance_id, adapter_id in sorted(frozen_config_bindings(config).items()):
        try:
            controls = sorted(set(registry.controls(adapter_id)) & set(ARGUMENT_SCHEMAS))
            schemas = {capability: schema for capability in controls
                       if (schema := registry.argument_schema(adapter_id, capability))
                       is not None}
        except AdapterContractError:
            controls, schemas = [], {}
        facts = provider_facts.get(adapter_id, {})
        rows.append({
            "instance_id": instance_id, "adapter_id": adapter_id,
            "model": models.get(instance_id), "controls": controls,
            "argument_schemas": schemas,
            "isolation": list(facts_for(
                facts.get("auth"), facts.get("vendor_sandbox"))),
        })
    return rows
