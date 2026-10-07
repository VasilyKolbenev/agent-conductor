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
from .policy_providers import task_channel_fact


def instance_controls(config: Mapping[str, Any],
                      registry: AdapterRegistry,
                      provider_facts: Mapping[str, Mapping[str, Any]] | None = None,
                      ) -> list[dict[str, object]]:
    """Project only declared capabilities, their schema names, and model pins.

    A null model is not a default: this run chose none. Schema absence also
    means unknown, never a shape inferred from a pending proposal's values.
    The browser can therefore distinguish an old deep-argument proposal from
    a native/process proposal without reinterpreting either one's arguments.

    ``isolation`` is the same read, and it is answered PER CONTROL. What
    protects a step is a fact about the transport bound to it and about the road
    that step takes -- a review and a dispatch on one binding do not run the same
    checks, and one list for both would have to be the union or the intersection,
    each of which is wrong for one of them.

    It is projected here rather than in the browser so one source answers. The
    provider facts arrive as an argument because they belong to the machine's
    provider configuration rather than to this run's frozen bindings; the guard
    declaration is asked of the registry, which reads it off the bound adapter's
    CLASS without constructing anything or probing a vendor. Absent either, every
    row that depends on one reads `unknown`, which is what an unasked question
    deserves -- and an adapter that declares no guards is one this build knows
    nothing about, never one it can report as unprotected.
    """
    provider_facts = dict(provider_facts or {})
    models = frozen_config_models(config)
    rows = []
    for instance_id, adapter_id in sorted(frozen_config_bindings(config).items()):
        controls, schemas, guards = _registered(registry, adapter_id)
        facts = provider_facts.get(adapter_id, {})
        rows.append({
            "instance_id": instance_id, "adapter_id": adapter_id,
            "model": models.get(instance_id), "controls": controls,
            "argument_schemas": schemas,
            "isolation": {
                capability: list(facts_for(
                    facts.get("auth"), facts.get("vendor_sandbox"), guards,
                    capability))
                for capability in controls},
            "task_channel": _task_channel(registry, adapter_id),
        })
    return rows


def _task_channel(registry: AdapterRegistry, adapter_id: str):
    """The bound this binding's whole task meets before its claim (review ruling R2), or None.

    The same fact a bounded grant freezes (``policy_providers.task_channel_fact``), read off the
    bound adapter's CLASS profile; an adapter the registry cannot resolve states none.
    """
    try:
        adapter = registry.resolve(adapter_id)
    except AdapterContractError:
        return None
    return task_channel_fact(getattr(type(adapter), "profile", None))


def _registered(registry: AdapterRegistry, adapter_id: str):
    """What the registry knows about one adapter, or nothing where it knows none.

    One `try`, because the three answers come from one registration: a binding
    the registry cannot resolve has no controls, no schemas and no declared
    guards, and answering two of the three from a half-read registration is how
    a screen comes to describe an adapter that is not there.
    """
    try:
        controls = sorted(set(registry.controls(adapter_id)) & set(ARGUMENT_SCHEMAS))
        schemas = {capability: schema for capability in controls
                   if (schema := registry.argument_schema(adapter_id, capability))
                   is not None}
        return controls, schemas, registry.isolation_guards(adapter_id)
    except AdapterContractError:
        return [], {}, None
