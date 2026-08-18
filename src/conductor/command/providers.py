"""Provider factory: resolve operator config to availability, register the available.

This is the one provider seam that touches the filesystem, and it touches it in
exactly one way: it asks ``os`` whether each operator-pinned ABSOLUTE path is
present -- the executable, and for a provider whose executable is an interpreter,
the entrypoint it runs. It never searches ``PATH``, scans a home directory,
resolves ``npx`` or ``latest``, installs anything, or spawns a process to probe;
an interpreter-backed provider with no entrypoint pinned resolves UNAVAILABLE
rather than having its missing half guessed. A provider that
is absent or whose pinned protocol does not match the catalogued provider
resolves UNAVAILABLE, and no adapter is built for it -- so it can never spawn a
process (spawn count 0). A provider this build catalogues but proved no
transport for declares no control, and a provider with nothing to dispatch is
refused availability before its pins are even read. Only an available provider's adapter enters the returned
``AdapterRegistry``; with no configs the registry stays honestly empty, so the
default production server never pretends a real provider is available.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from .adapters import AdapterContractError, AdapterRegistry
from .adapters.deep_adapters import (
    DEEP_CAPABILITIES,
    DEEP_CONTROLS,
    ClaudeCodeAdapter,
    CodexAdapter,
)
from .adapters.deep_contracts import DeepAdapterConfig
from .adapters.dsh_harness import DSH_PROTOCOL, DshHarnessAdapter, DshPin
from .adapters.kimi_code import (
    KIMI_CAPABILITIES,
    KIMI_DISPLAY_NAME,
    KIMI_LIFECYCLE,
    KIMI_PROTOCOL,
    KIMI_PROVIDER_ID,
    KIMI_SCHEMA_PAIRS,
    KimiCodeContractAdapter,
)
from .adapters.process import ProcessRunner
from .adapters.provider import (
    SCHEMALESS_CAPABILITIES,
    ProviderCatalogEntry,
    ProviderConfig,
    ProviderConfigError,
    ProviderContract,
    ProviderRegistry,
    reconstruct_config,
    reconstruct_entry,
)

#: Each deep control capability binds the one reviewed deep argument schema.
_DEEP_SCHEMA_PAIRS = tuple(sorted(
    (capability, "deep-arguments-v1") for capability in DEEP_CAPABILITIES))
#: The seams the fake-protocol adapters really implement. Recovery is absent on
#: purpose: no adapter in this build carries a ``recover`` seam, and the door
#: refuses a lifecycle claim its adapter class cannot back.
_DEEP_LIFECYCLE = ("observe", "prepare", "execute", "verify")
#: Protocols whose executable is an INTERPRETER: the operator must pin a second
#: absolute path, the entrypoint it runs, and both files must really be present
#: before the provider is available. Nothing is derived, searched, or guessed.
_ENTRYPOINT_PROTOCOLS = frozenset({DSH_PROTOCOL})
#: The dsh harness carries one control and says so; stop, retry and switch are
#: absent from the manifest, so the door cannot admit them.
_DSH_CAPABILITIES = ("observe", "dispatch")
_DSH_SCHEMA_PAIRS = (("dispatch", "deep-arguments-v1"),)

#: The closed catalog of providers this build knows how to describe and construct.
#: A ProviderConfig naming a provider absent from this catalog is refused; it is
#: never silently discovered or invented.
PROVIDER_CATALOG = MappingProxyType({
    "claude-code": ProviderCatalogEntry(
        provider_id="claude-code", display_name="Claude Code (fake protocol)",
        vendor="Anthropic-compatible test fixture", protocol="fake-claude-jsonl-v1",
        capabilities=DEEP_CONTROLS, schema_pairs=_DEEP_SCHEMA_PAIRS,
        lifecycle=_DEEP_LIFECYCLE, adapter_class=ClaudeCodeAdapter),
    "codex": ProviderCatalogEntry(
        provider_id="codex", display_name="Codex (fake protocol)",
        vendor="OpenAI-compatible test fixture", protocol="fake-codex-jsonl-v1",
        capabilities=DEEP_CONTROLS, schema_pairs=_DEEP_SCHEMA_PAIRS,
        lifecycle=_DEEP_LIFECYCLE, adapter_class=CodexAdapter),
    "deepseek-harness": ProviderCatalogEntry(
        provider_id="deepseek-harness", display_name="DeepSeek Harness (dsh, headless)",
        vendor="DeepSeek", protocol=DSH_PROTOCOL,
        capabilities=_DSH_CAPABILITIES, schema_pairs=_DSH_SCHEMA_PAIRS,
        lifecycle=_DEEP_LIFECYCLE, adapter_class=DshHarnessAdapter),
    KIMI_PROVIDER_ID: ProviderCatalogEntry(
        provider_id=KIMI_PROVIDER_ID, display_name=KIMI_DISPLAY_NAME,
        vendor="Moonshot AI", protocol=KIMI_PROTOCOL,
        capabilities=KIMI_CAPABILITIES, schema_pairs=KIMI_SCHEMA_PAIRS,
        lifecycle=KIMI_LIFECYCLE, adapter_class=KimiCodeContractAdapter),
})


@dataclass(frozen=True)
class ProviderResolution:
    """The factory's result: the runtime registry and every provider's descriptor.

    ``registry`` holds only the adapters of AVAILABLE providers, so the runtime
    can resolve and later spawn exactly those. ``contracts`` describes every
    configured provider, available or not, for the Cockpit projection.
    """

    registry: AdapterRegistry
    contracts: tuple[ProviderContract, ...]

    def spawn_capable(self, provider_id: str) -> bool:
        """True only when an available provider's adapter can be spawned at all."""
        try:
            self.registry.resolve(provider_id)
        except AdapterContractError:
            return False
        return True


def _reviewed_configs(configs: object) -> tuple[ProviderConfig, ...]:
    if isinstance(configs, (str, bytes)):
        raise ProviderConfigError("provider configs must be a sequence of ProviderConfig")
    reviewed: list[ProviderConfig] = []
    seen: set[str] = set()
    for config in configs:
        canonical = reconstruct_config(config)
        if canonical.provider_id in seen:
            raise ProviderConfigError(
                f"provider {canonical.provider_id!r} is configured more than once")
        seen.add(canonical.provider_id)
        reviewed.append(canonical)
    return tuple(reviewed)


def _executable_present(path: str) -> bool:
    """One exact stat of the operator's pin; never a search, scan, or spawn."""
    try:
        return os.path.isfile(path)
    except OSError:
        return False


def _dispatchable_controls(entry: ProviderCatalogEntry) -> frozenset[str]:
    """The controls a provider offers the runtime. An observation is not one."""
    return frozenset(entry.capabilities) - SCHEMALESS_CAPABILITIES


def _resolve_availability(config: ProviderConfig, entry: ProviderCatalogEntry) -> str:
    """Availability is a fact about pinned FILES, never about a name or a hope."""
    if not _dispatchable_controls(entry):
        # A provider this build proved no transport for declares no control at
        # all, so there is nothing the runtime could dispatch through it and no
        # pin on the machine can change that. Calling it available would tell the
        # Cockpit a usable provider is there while the projection handed it an
        # empty control list; the protocol it carries is not one this build
        # implements, which is exactly what version_mismatch says.
        return "version_mismatch"
    if config.protocol != entry.protocol:
        return "version_mismatch"
    if entry.protocol in _ENTRYPOINT_PROTOCOLS and not config.entrypoint:
        # An interpreter with nothing to run is not a usable provider, and
        # inventing the missing half is exactly what this factory refuses to do.
        return "executable_absent"
    if not _executable_present(config.executable):
        return "executable_absent"
    if config.entrypoint and not _executable_present(config.entrypoint):
        return "executable_absent"
    return "available"


def _catalogued(catalog: object, provider_id: str) -> ProviderCatalogEntry:
    """Read one reviewed entry from an untrusted catalog and rebuild it before use."""
    if not isinstance(catalog, Mapping):
        raise ProviderConfigError("provider catalog must be a mapping of reviewed entries")
    entry = catalog.get(provider_id)
    if entry is None:
        raise ProviderConfigError(
            f"provider {provider_id!r} is not in the reviewed catalog")
    canonical = reconstruct_entry(entry)
    if canonical.provider_id != provider_id:
        raise ProviderConfigError("catalogued provider id does not match its catalog key")
    return canonical


def _build_adapter(
        entry: ProviderCatalogEntry, config: ProviderConfig, runner: ProcessRunner, *,
        root: str | os.PathLike[str], clock: Callable[[], str],
        ids: Callable[[str], str]) -> object:
    if entry.protocol in _ENTRYPOINT_PROTOCOLS:
        pin = DshPin(
            node_executable=config.executable, entrypoint=config.entrypoint,
            env_allow=config.env_allow)
        return entry.adapter_class(
            pin, runner, root=root, clock=clock, ids=ids,
            adapter_id=entry.provider_id)
    deep_config = DeepAdapterConfig(
        executable=config.executable, protocol=config.protocol,
        env_allow=config.env_allow, real_mode="unavailable")
    return entry.adapter_class(deep_config, runner, clock=clock, ids=ids)


def resolve_providers(
        configs: Iterable[ProviderConfig], *, root: str | os.PathLike[str],
        clock: Callable[[], str], ids: Callable[[str], str],
        environ: dict[str, str] | None = None,
        catalog: object = PROVIDER_CATALOG) -> ProviderResolution:
    """Resolve each operator config to a descriptor and register it through the door.

    An adapter -- and with it the owned process runner it would spawn through --
    is built only for a provider that resolved AVAILABLE, so an absent or
    version-mismatched provider reaches no runner at all.
    """
    reviewed = _reviewed_configs(configs)
    providers = ProviderRegistry()
    runner: ProcessRunner | None = None
    for config in reviewed:
        entry = _catalogued(catalog, config.provider_id)
        availability = _resolve_availability(config, entry)
        adapter: object = None
        if availability == "available":
            if runner is None:
                runner = ProcessRunner(Path(root), environ=environ)
            adapter = _build_adapter(
                entry, config, runner, root=root, clock=clock, ids=ids)
        providers.register(entry, availability=availability, adapter=adapter)
    return ProviderResolution(
        registry=providers.adapters, contracts=providers.contracts())
