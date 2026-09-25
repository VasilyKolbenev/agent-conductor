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
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

from .adapters import AdapterContractError, AdapterRegistry
from .quota_plans import ProviderQuotaPlan, quota_plan_for
from .adapters.claude_code import (
    CLAUDE_CAPABILITIES,
    CLAUDE_DISPLAY_NAME,
    CLAUDE_HOME_ENV,
    CLAUDE_LIFECYCLE,
    CLAUDE_PROTOCOL,
    CLAUDE_PROVIDER_ID,
    CLAUDE_SCHEMA_PAIRS,
    ClaudeCodeTransport,
)
from .adapters.claude_code import LOGIN_ARGV as CLAUDE_LOGIN_ARGV
from .adapters.codex_cli import (
    CODEX_CAPABILITIES,
    CODEX_DISPLAY_NAME,
    CODEX_HOME_ENV,
    CODEX_LIFECYCLE,
    CODEX_PROTOCOL,
    CODEX_PROVIDER_ID,
    CODEX_SCHEMA_PAIRS,
    CodexCliTransport,
)
from .adapters.codex_cli import LOGIN_ARGV as CODEX_LOGIN_ARGV
from .adapters.deep_contracts import DeepAdapterConfig
from .adapters.dsh_harness import DSH_PROTOCOL, DshHarnessAdapter, DshPin
from .adapters.grok_build import (
    GROK_CAPABILITIES,
    GROK_DISPLAY_NAME,
    GROK_HOME_ENV,
    GROK_LOGIN_ARGV,
    GROK_LIFECYCLE,
    GROK_PROTOCOL,
    GROK_PROVIDER_ID,
    GROK_SCHEMA_PAIRS,
    GrokBuildAdapter,
)
from .adapters.kimi_code import (
    KIMI_CAPABILITIES,
    KIMI_DISPLAY_NAME,
    KIMI_HOME_ENV,
    KIMI_LOGIN_ARGV,
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
    UNPINNED_AUTH,
    ProviderCatalogEntry,
    ProviderConfig,
    ProviderConfigError,
    ProviderContract,
    ProviderRegistry,
    reconstruct_config,
    reconstruct_entry,
)

#: The seams the dsh harness really implements. Recovery is absent on purpose:
#: no adapter in this build carries a ``recover`` seam, and the door refuses a
#: lifecycle claim its adapter class cannot back.
#:
#: The deep control set and its schema pairs stood beside this until the Codex
#: transport landed. They described the fake-protocol row, and with every
#: catalogued provider now real there is no such row to describe -- the fakes
#: remain in their own modules as the ``_DeepAdapter`` lifecycle fixtures, and
#: the catalog no longer serves one.
_DEEP_LIFECYCLE = ("observe", "prepare", "execute", "verify")
#: Protocols whose executable is an INTERPRETER: the operator must pin a second
#: absolute path, the entrypoint it runs, and both files must really be present
#: before the provider is available. Nothing is derived, searched, or guessed.
_ENTRYPOINT_PROTOCOLS = frozenset({DSH_PROTOCOL})
#: Protocols whose executable is the WHOLE pin: one native binary, no second
#: half. Keyed by PROTOCOL rather than by provider id on purpose -- a protocol is
#: not an identity, so this stays a fact about pin SHAPE and the identity gate
#: has nothing to permit here. Two products sharing a shape share this row.
_SINGLE_EXECUTABLE_PROTOCOLS = frozenset(
    {KIMI_PROTOCOL, GROK_PROTOCOL, CLAUDE_PROTOCOL, CODEX_PROTOCOL})
#: What a pin for one protocol must LOOK like, in the three words a surface that
#: asks an operator for one needs. A closed vocabulary rather than two booleans,
#: so a caller cannot spell "both" or "neither" and get an answer.
ENTRYPOINT_REQUIRED = "required"
ENTRYPOINT_FORBIDDEN = "forbidden"
ENTRYPOINT_OPTIONAL = "optional"
ENTRYPOINT_RULES = frozenset(
    {ENTRYPOINT_REQUIRED, ENTRYPOINT_FORBIDDEN, ENTRYPOINT_OPTIONAL})
#: The dsh harness carries one control and says so; stop, retry and switch are
#: absent from the manifest, so the door cannot admit them.
_DSH_CAPABILITIES = ("observe", "dispatch")
_DSH_SCHEMA_PAIRS = (("dispatch", "deep-arguments-v1"),)

#: The closed catalog of providers this build knows how to describe and construct.
#: A ProviderConfig naming a provider absent from this catalog is refused; it is
#: never silently discovered or invented.
PROVIDER_CATALOG = MappingProxyType({
    CLAUDE_PROVIDER_ID: ProviderCatalogEntry(
        provider_id=CLAUDE_PROVIDER_ID, display_name=CLAUDE_DISPLAY_NAME,
        vendor="Anthropic", protocol=CLAUDE_PROTOCOL,
        capabilities=CLAUDE_CAPABILITIES, schema_pairs=CLAUDE_SCHEMA_PAIRS,
        lifecycle=CLAUDE_LIFECYCLE, adapter_class=ClaudeCodeTransport,
        implementation="real_experimental"),
    CODEX_PROVIDER_ID: ProviderCatalogEntry(
        provider_id=CODEX_PROVIDER_ID, display_name=CODEX_DISPLAY_NAME,
        vendor="OpenAI", protocol=CODEX_PROTOCOL,
        capabilities=CODEX_CAPABILITIES, schema_pairs=CODEX_SCHEMA_PAIRS,
        lifecycle=CODEX_LIFECYCLE, adapter_class=CodexCliTransport,
        implementation="real_experimental"),
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
    quota_plans: tuple[ProviderQuotaPlan, ...] = field(default=(), repr=False)

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


def entrypoint_rule(protocol: str) -> str:
    """Whether a pin for this protocol must name an entrypoint, may not, or neither.

    The pin SHAPE, said out loud, because two surfaces need it and only one of
    them was reading it. `_resolve_availability` below judges a finished config
    against these same two sets; `conduct providers` ASKS an operator to build
    one. While the asking surface carried its own idea -- it offered an optional
    entrypoint to every provider -- an operator could answer every question,
    be told the file was written, and get `executable_absent` from the server for
    the interpreter-backed row and `version_mismatch` for the single-executable
    ones. Neither answer named the question that produced it.

    So the rule is read from one place by both, and a protocol that changes shape
    moves the dialogue with it. A protocol in neither set constrains the pin
    NEITHER way, and `optional` is the honest word for that -- it is what
    availability below then requires, not a gap in this function.

    Args:
        protocol: A reviewed protocol token, as carried by a catalogue entry.

    Returns:
        One of `ENTRYPOINT_REQUIRED`, `ENTRYPOINT_FORBIDDEN`, `ENTRYPOINT_OPTIONAL`.
    """
    if protocol in _ENTRYPOINT_PROTOCOLS:
        return ENTRYPOINT_REQUIRED
    if protocol in _SINGLE_EXECUTABLE_PROTOCOLS:
        return ENTRYPOINT_FORBIDDEN
    return ENTRYPOINT_OPTIONAL


def login_hint(protocol: str) -> tuple[str, tuple[str, ...]] | None:
    """How a PERSON signs this protocol's harness in, or None if none is driven.

    The two halves are vendor facts and are read from the transport module that
    owns them rather than retyped here: the environment variable that names a
    login directory, and the vendor's own login command. This build never runs
    that command -- a login is an account-holding act, and a product performing
    one would be handling somebody's credentials -- so the only thing done with
    this pair is printing it beside the directory the operator pinned.

    Args:
        protocol: A reviewed protocol token, as carried by a catalogue entry.

    Returns:
        `(home_env, login_argv)` for a protocol whose transport drives a vendor
        login, and None for every other, which is the same set the config door
        admits `subscription` for.
    """
    if protocol == CLAUDE_PROTOCOL:
        return CLAUDE_HOME_ENV, CLAUDE_LOGIN_ARGV
    if protocol == CODEX_PROTOCOL:
        return CODEX_HOME_ENV, CODEX_LOGIN_ARGV
    if protocol == GROK_PROTOCOL:
        return GROK_HOME_ENV, GROK_LOGIN_ARGV
    if protocol == KIMI_PROTOCOL:
        return KIMI_HOME_ENV, KIMI_LOGIN_ARGV
    return None


def availability_of(config: ProviderConfig, *,
                    catalog: object = PROVIDER_CATALOG) -> str:
    """What `resolve_providers` will call this config, without building anything.

    The same judgement, asked without a project root, a clock or an id source,
    so a surface that has just collected a pin can say what the server will say
    about it instead of reporting that a file was written and leaving the
    operator to discover the rest from a screen that names no cause.
    """
    return _resolve_availability(
        reconstruct_config(config), _catalogued(catalog, config.provider_id))


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
    rule = entrypoint_rule(entry.protocol)
    if rule == ENTRYPOINT_REQUIRED and not config.entrypoint:
        # An interpreter with nothing to run is not a usable provider, and
        # inventing the missing half is exactly what this factory refuses to do.
        return "executable_absent"
    if rule == ENTRYPOINT_FORBIDDEN and config.entrypoint:
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
                error=entry.adapter_class.error, auth=config.auth,
                auth_home=config.auth_home),
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
    quota_plans: list[ProviderQuotaPlan] = []
    configured = {config.provider_id: config for config in reviewed}
    for provider_id in _catalogued_ids(catalog, configured):
        entry = _catalogued(catalog, provider_id)
        config = configured.get(provider_id)
        if config is None:
            # No row named it, so it carries no login at all -- not the login
            # that a row leaving the field out would have meant. Said out loud
            # rather than left to the parameter's default: this is the one road
            # that means it, and a default is not a decision.
            providers.register(
                entry, availability="unconfigured", auth=UNPINNED_AUTH,
                adapter=None)
            continue
        availability = _resolve_availability(config, entry)
        adapter: object = None
        if availability == "available":
            if runner is None:
                runner = ProcessRunner(Path(root), environ=environ)
            adapter = _build_adapter(
                entry, config, runner, root=root, clock=clock, ids=ids)
            quota_plan = quota_plan_for(provider_id, adapter)
            if quota_plan is not None:
                quota_plans.append(quota_plan)
        providers.register(
            entry, availability=availability, auth=config.auth, adapter=adapter)
    return ProviderResolution(
        registry=providers.adapters, contracts=providers.contracts(),
        quota_plans=tuple(quota_plans))


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
