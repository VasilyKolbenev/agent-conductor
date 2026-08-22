"""Provider factory: resolve operator config to availability, register the available.

This is the one provider seam that touches the filesystem, and it touches it in
exactly one way: it asks ``os`` whether each operator-pinned ABSOLUTE path is
present -- the executable, and for a provider whose executable is an interpreter,
the entrypoint it runs. It never searches ``PATH``, scans a home directory,
resolves ``npx`` or ``latest``, installs anything, or spawns a process to probe;
an interpreter-backed provider with no entrypoint pinned resolves UNAVAILABLE
rather than having its missing half guessed. A provider that is absent or whose
pinned protocol does not match the catalogued provider resolves UNAVAILABLE, and
no adapter is built for it -- so it can never spawn a process (spawn count 0). A
provider this build catalogues but proved no transport for declares no control,
and a provider with nothing to dispatch is refused availability before its pins
are even read. Only an available provider's adapter enters the returned
``AdapterRegistry``; with no configs the registry stays honestly empty, so the
default production server never pretends a real provider is available. The
descriptors are the other half of that honesty: every CATALOGUED provider is
described, and one no operator config named is ``unconfigured`` -- this build
knows it, nothing was looked at for it, and nothing can be dispatched through it.
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
from .adapters.grok_build import (
    GROK_CAPABILITIES,
    GROK_DISPLAY_NAME,
    GROK_LIFECYCLE,
    GROK_PROTOCOL,
    GROK_PROVIDER_ID,
    GROK_SCHEMA_PAIRS,
    GrokBuildAdapter,
)
from .adapters.kimi_code import (
    KIMI_CAPABILITIES,
    KIMI_DISPLAY_NAME,
    KIMI_LIFECYCLE,
    KIMI_PROTOCOL,
    KIMI_PROVIDER_ID,
    KIMI_SCHEMA_PAIRS,
    KimiCodeAdapter,
)
from .adapters.process import ProcessRunner
from .adapters.headless_cli import ExecutablePin
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
#: Protocols whose executable is the WHOLE pin: one native binary, no second
#: half. Keyed by PROTOCOL rather than by provider id on purpose -- a protocol is
#: not an identity, so this stays a fact about pin SHAPE and the identity gate
#: has nothing to permit here. Two products sharing a shape share this row.
_SINGLE_EXECUTABLE_PROTOCOLS = frozenset({KIMI_PROTOCOL, GROK_PROTOCOL})
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
        lifecycle=_DEEP_LIFECYCLE, adapter_class=ClaudeCodeAdapter,
        implementation="fixture_only"),
    "codex": ProviderCatalogEntry(
        provider_id="codex", display_name="Codex (fake protocol)",
        vendor="OpenAI-compatible test fixture", protocol="fake-codex-jsonl-v1",
        capabilities=DEEP_CONTROLS, schema_pairs=_DEEP_SCHEMA_PAIRS,
        lifecycle=_DEEP_LIFECYCLE, adapter_class=CodexAdapter,
        implementation="fixture_only"),
    "deepseek-harness": ProviderCatalogEntry(
        provider_id="deepseek-harness", display_name="DeepSeek Harness (dsh, headless)",
        vendor="DeepSeek", protocol=DSH_PROTOCOL,
        capabilities=_DSH_CAPABILITIES, schema_pairs=_DSH_SCHEMA_PAIRS,
        lifecycle=_DEEP_LIFECYCLE, adapter_class=DshHarnessAdapter,
        implementation="real_experimental"),
    KIMI_PROVIDER_ID: ProviderCatalogEntry(
        provider_id=KIMI_PROVIDER_ID, display_name=KIMI_DISPLAY_NAME,
        vendor="Moonshot AI", protocol=KIMI_PROTOCOL,
        capabilities=KIMI_CAPABILITIES, schema_pairs=KIMI_SCHEMA_PAIRS,
        lifecycle=KIMI_LIFECYCLE, adapter_class=KimiCodeAdapter,
        implementation="real_experimental"),
    GROK_PROVIDER_ID: ProviderCatalogEntry(
        provider_id=GROK_PROVIDER_ID, display_name=GROK_DISPLAY_NAME,
        vendor="xAI", protocol=GROK_PROTOCOL,
        capabilities=GROK_CAPABILITIES, schema_pairs=GROK_SCHEMA_PAIRS,
        lifecycle=GROK_LIFECYCLE, adapter_class=GrokBuildAdapter,
        implementation="real_experimental"),
})


@dataclass(frozen=True)
class ProviderResolution:
    """The factory's result: the runtime registry and every provider's descriptor.

    ``registry`` holds only the adapters of AVAILABLE providers, so the runtime
    can resolve and later spawn exactly those. ``contracts`` describes every
    CATALOGUED provider -- configured or not, available or not -- for the Cockpit
    projection, so the roster a person can see is the roster this build knows.
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
    if entry.protocol in _SINGLE_EXECUTABLE_PROTOCOLS and config.entrypoint:
        # The mirror image: this provider runs ONE binary, so an entrypoint
        # pinned beside it is a config this build cannot honour -- the operator
        # believes a second file is run and nothing here would run it.
        #
        # It is answered HERE, as unavailability, and not by raising from the
        # adapter factory. Raising took down the whole roster: `conduct up` does
        # not catch ProviderConfigError, so one operator typo ended the server
        # with a traceback and no descriptor for ANY provider. It also fired only
        # when the pinned entrypoint really existed -- an absent one was reported
        # as `executable_absent` first -- so it was loudest in the case that
        # needed it least. Read as a fact about the CONFIG's shape, it needs no
        # disk at all and it costs one provider its availability, which is what
        # every other unhonourable pin costs.
        return "version_mismatch"
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
    if entry.protocol in _SINGLE_EXECUTABLE_PROTOCOLS:
        # No adapter is ever built for a config carrying an entrypoint here:
        # `_resolve_availability` refuses it, and only an AVAILABLE provider
        # reaches this function. The refusal type comes from the adapter class
        # that will hold the pin, so a second single-binary provider refuses as
        # ITSELF -- hardcoding one provider's factory here gave every future one
        # Kimi Code's error.
        return entry.adapter_class(
            ExecutablePin(
                executable=config.executable, env_allow=config.env_allow,
                error=entry.adapter_class.error),
            runner, root=root, clock=clock, ids=ids,
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

    Every CATALOGUED provider is registered, configured or not. One the operator
    never named resolves ``unconfigured``: nothing on the machine was looked at
    for it, it owns no adapter, and it is spawn-capable through nothing -- but the
    Cockpit can still see that this build knows it exists and can say what would
    have to be configured. That is the honest answer to "what could I run here?",
    and it is a different answer from "the pinned file is missing".
    """
    reviewed = _reviewed_configs(configs)
    providers = ProviderRegistry()
    runner: ProcessRunner | None = None
    configured = {config.provider_id: config for config in reviewed}
    for provider_id in _catalogued_ids(catalog, configured):
        entry = _catalogued(catalog, provider_id)
        config = configured.get(provider_id)
        if config is None:
            providers.register(entry, availability="unconfigured", adapter=None)
            continue
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


def _catalogued_ids(
        catalog: object, configured: Mapping[str, ProviderConfig]) -> tuple[str, ...]:
    """Every reviewed provider id, in a stable order, with the configured held first.

    A configured provider is resolved first so a config naming a provider this
    build does not catalogue is refused before an unrelated provider is described.
    """
    if not isinstance(catalog, Mapping):
        raise ProviderConfigError("provider catalog must be a mapping of reviewed entries")
    if any(type(key) is not str for key in catalog):
        raise ProviderConfigError("provider catalog keys must be provider id strings")
    known = tuple(sorted(catalog))
    return tuple(sorted(configured)) + tuple(
        provider_id for provider_id in known if provider_id not in configured)
