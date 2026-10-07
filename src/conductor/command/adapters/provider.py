"""Immutable provider contract, the one registration door, and the projection.

This value module probes nothing: it opens no process, filesystem, environment,
or network door. It holds the two halves of a configured provider and keeps them
apart on purpose:

- ``ProviderConfig`` is the operator's durable input. It stores a provider id, one
  ABSOLUTE operator-pinned executable path, a reviewed protocol token, allowlisted
  environment NAMES, and -- for a provider whose executable is an interpreter --
  one further ABSOLUTE operator-pinned entrypoint path under the same gate. It
  stores no secret value, no argv, no cwd, no token, and no raw output; a secret
  is referenced by name and read from the live environment at spawn time, never
  written here. An empty ``entrypoint`` means the operator pinned none, which is
  the whole shape for a provider that is its own executable.
- ``ProviderContract`` is the public descriptor the Cockpit may see. It carries
  identity, resolved availability, the declared implementation of this build's
  transport, declared capabilities, the CLOSED per-capability argument-schema
  relation, and the lifecycle seams the provider really implements -- and it
  never carries the executable, a path, an env value, a token, a PID, or raw
  output. Availability and implementation are separate questions in separate
  closed vocabularies and are never mixed: the machine's state cannot be read off
  the build's, or the other way round.

``ProviderRegistry`` is the one door between the two. The factory admits every
provider through it, so a descriptor the Cockpit can see and an adapter the
runtime can spawn exist only for a provider that passed. It refuses -- at
registration -- a partial schema relation, a duplicate identity, a lifecycle
claim the adapter class does not implement, and an adapter offered for a
provider that is not available.

Every supplied value is reconstructed to its exact base type before one field of
it is read, so a hostile subclass, an ``object.__setattr__`` mutation, or a
mutated frozen value is refused rather than trusted. Availability resolution and
adapter construction -- the only seams that touch the filesystem or build a
spawning adapter -- live in ``conductor.command.providers``, never in this
module.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, ClassVar

from ..contracts import ContractError, _id, _text, canonical_json
from .base import CAPABILITIES, _ARGUMENT_SCHEMAS, AdapterContractError, AdapterRegistry
from .deep_contracts import DeepProtocol, _env_names

#: Every reviewed provider protocol/version token an operator may pin.
KNOWN_PROTOCOLS = frozenset(protocol.value for protocol in DeepProtocol)
#: The reviewed argument-schema names any capability may bind to.
KNOWN_SCHEMAS = frozenset(_ARGUMENT_SCHEMAS)
#: The four resolved states of the OPERATOR'S MACHINE; ``available`` is the only
#: spawn-capable one and ``unconfigured`` means no operator config named this
#: provider at all, so nothing about its files has been looked at.
AVAILABILITY_STATES = frozenset({
    "available", "executable_absent", "version_mismatch", "unconfigured"})
#: The three states of THIS BUILD's transport for a provider. It is a different
#: question from availability and shares no value with it, so neither can be
#: read as the other: a provider can be available and only a fixture, or carry a
#: real transport and be unconfigured.
IMPLEMENTATION_STATES = frozenset({"real_experimental", "fixture_only", "unproven"})
#: What a provider that declares no implementation claims: the weakest of the
#: three. A stronger claim has to be written down to be made.
WEAKEST_IMPLEMENTATION = "unproven"
#: The two logins a provider row may be pinned to. ``api_key`` is the road that
#: shipped -- the harness reads a credential out of the environment by a name the
#: row allows -- and ``subscription`` is the vendor's own login, kept in a
#: directory the row names. A row that says neither means ``api_key``, so every
#: configuration written before this field existed still means what it meant.
#: Both are spelled like the availability and implementation words beside them,
#: so one screen never mixes two token styles for three parallel facts.
AUTH_MODES = frozenset({"api_key", "subscription"})
#: What an unsaid mode is. Named rather than spelled inline, because two places
#: (this door and the operator file's row writer) have to agree on it.
DEFAULT_AUTH_MODE = "api_key"
SUBSCRIPTION_AUTH = "subscription"
#: Environment NAMES that buy model access billed to an API account. In
#: subscription mode a row may not forward one: the reviewed Claude build was
#: measured going straight to ``POST /v1/messages`` with an ``x-api-key`` header
#: when ``ANTHROPIC_API_KEY`` stood in its environment, under the very flag the
#: subscription road needs. A row that pinned both would bill an API account
#: while its operator believed a subscription was in use, and no later refusal
#: could see that it had happened.
#:
#: Like :data:`INJECTING_ENV` in the process door, this is a NAMED defence and
#: not a proof: a credential forwarded under some other name is not caught here,
#: and nothing in this build can see the value.
API_BILLING_ENV = frozenset({
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY"})
#: The reviewed protocols whose transport really drives a vendor login. A mode is
#: not a label: pinning ``subscription`` where no transport implements it would
#: leave an operator reading a login this build never performs, so it is refused
#: at this door -- in the same breath as an unreviewed protocol token, and for
#: the same reason.
SUBSCRIPTION_PROTOCOLS = frozenset({
    "claude-code-headless-v1", "codex-headless-v1", "grok-build-headless-v1", "kimi-code-headless-v1"})
#: What a provider carries on the wire when NO operator row names it at all. It is
#: a third word rather than the default mode, because "nobody pinned a login" and
#: "a row pinned the login that shipped" are different facts, and a screen that
#: showed the second for the first would be reporting a configuration that does
#: not exist. It shares no value with the availability or implementation
#: vocabularies, so no consumer can read one answer as another.
UNPINNED_AUTH = "unpinned"
#: Every value the wire may carry for the login question.
CONTRACT_AUTH_STATES = frozenset(AUTH_MODES | {UNPINNED_AUTH})
#: The one lifecycle capability that carries no argument schema: an observation is
#: an adapter-authored fact, never a browser-submitted argument body.
SCHEMALESS_CAPABILITIES = frozenset({"observe"})
#: Every adapter lifecycle seam a provider may claim it implements.
LIFECYCLE_SEAMS = frozenset({"observe", "prepare", "execute", "verify", "recover"})
#: The seams no provider may omit. ``recover`` is optional and must be declared
#: to be claimed, because no adapter in this build implements recovery yet.
REQUIRED_SEAMS = frozenset({"observe", "prepare", "execute", "verify"})


class ProviderConfigError(ContractError):
    """A provider config or contract value is open-ended, secret-bearing, or partial."""


def _provider_id(value: object) -> str:
    try:
        return _id("provider_id", value)
    except ContractError as error:
        raise ProviderConfigError(str(error)) from None


def _reviewed_text(name: str, value: object) -> str:
    try:
        return _text(name, value)
    except ContractError as error:
        raise ProviderConfigError(str(error)) from None


def _reviewed_env_names(value: object) -> tuple[str, ...]:
    try:
        return _env_names(value)
    except ContractError:
        raise ProviderConfigError(
            "env_allow must contain unique environment NAMES, never values") from None


def _is_absolute(path: str) -> bool:
    return PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()


def _exact_fields(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise ProviderConfigError(f"{name} must be an object with string keys")
    if set(value) != fields:
        raise ProviderConfigError(f"{name} fields must be exact; nothing missing or extra")
    return dict(value)


def _plain(value: object) -> Any:
    """Re-read one value as exact JSON data, dropping every supplied identity."""
    return json.loads(canonical_json(value))


def _closed(build: Callable[[], Any], message: str) -> Any:
    """Run one rebuild; every failure becomes the same closed refusal.

    A value mutated past its constructor can fail the rebuild in many ways -- an
    unreadable field, an unserializable field, a broken invariant. All of them
    mean the same thing here, and none of them may report the hostile detail on.
    """
    failed = False
    try:
        result = build()
    except Exception:  # noqa: BLE001 -- a mutated value keeps no hostile graph
        failed = True
        result = None
    if failed:
        raise ProviderConfigError(message) from None
    return result


def _reviewed_capabilities(value: object) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise ProviderConfigError("capabilities must be a list of declared capability ids")
    rows = tuple(value)
    if any(type(row) is not str or row not in CAPABILITIES for row in rows):
        raise ProviderConfigError("capabilities contain an unsupported value")
    if len(set(rows)) != len(rows):
        raise ProviderConfigError("capabilities must not repeat a value")
    return rows


def _reviewed_vendor_sandbox(
        pairs: object) -> tuple[tuple[str, str], ...] | None:
    """Close the vendor's own sandbox declaration, keeping its three answers.

    ``None`` survives as ``None``: it says this integration declares nothing,
    which is not the same claim as ``()`` -- "we looked and this vendor ships
    none" -- and a normalizer that folded either into the other would hand a
    screen an absence nobody measured. A road named twice is two answers to one
    question and is refused, because a reader would have to pick one.
    """
    if pairs is None:
        return None
    if type(pairs) not in (list, tuple):
        raise ProviderConfigError(
            "vendor sandbox is a list of road/tokens pairs, or is not declared")
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pair in pairs:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            raise ProviderConfigError(
                "each vendor sandbox row must be one road/tokens pair")
        road, tokens = pair
        if type(road) is not str or type(tokens) is not str:
            raise ProviderConfigError("a vendor sandbox row is two strings")
        if not road.strip() or not tokens.strip():
            raise ProviderConfigError(
                "a vendor sandbox row names a road and the tokens it pins")
        if road in seen:
            raise ProviderConfigError(
                f"vendor sandbox names road {road!r} twice")
        seen.add(road)
        rows.append((road, tokens))
    return tuple(rows)


def _reviewed_schema_relation(
        capabilities: tuple[str, ...],
        pairs: object) -> tuple[tuple[str, str], ...]:
    """Close the per-capability schema relation: total over controls, injective, exact.

    The relation is supplied as DATA (capability/schema pairs), so a repeated
    capability, a schema for an undeclared or schemaless capability, and a control
    left without a schema are each visible and each refused here.
    """
    if type(pairs) not in (list, tuple):
        raise ProviderConfigError("schema relation must be a list of capability/schema pairs")
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pair in pairs:
        if type(pair) not in (list, tuple) or len(pair) != 2:
            raise ProviderConfigError(
                "each schema relation row must be one capability/schema pair")
        capability, schema = pair
        if type(capability) is not str or capability not in capabilities:
            raise ProviderConfigError("schema relation names an undeclared capability")
        if type(schema) is not str or schema not in KNOWN_SCHEMAS:
            raise ProviderConfigError("schema relation names an unreviewed schema")
        if capability in seen:
            raise ProviderConfigError("schema relation must not repeat a capability")
        seen.add(capability)
        rows.append((capability, schema))
    controls = set(capabilities) - SCHEMALESS_CAPABILITIES
    if seen != controls:
        raise ProviderConfigError(
            "every control capability requires exactly one argument schema")
    return tuple(sorted(rows))


def _reviewed_lifecycle(value: object) -> tuple[str, ...]:
    """Close the lifecycle claim: reviewed seam names, no repeat, nothing required missing."""
    if type(value) not in (list, tuple):
        raise ProviderConfigError("lifecycle must be a list of reviewed seam names")
    rows = tuple(value)
    if any(type(row) is not str or row not in LIFECYCLE_SEAMS for row in rows):
        raise ProviderConfigError("lifecycle names an unreviewed seam")
    if len(set(rows)) != len(rows):
        raise ProviderConfigError("lifecycle must not repeat a seam")
    if not REQUIRED_SEAMS.issubset(rows):
        raise ProviderConfigError(
            "lifecycle must declare observe, prepare, execute and verify")
    return tuple(sorted(rows))


@dataclass(frozen=True)
class ProviderConfig:
    """Operator-pinned provider configuration: the only durable provider input."""

    provider_id: str
    executable: str
    protocol: str
    env_allow: tuple[str, ...] | list[str] = ()
    entrypoint: str = ""
    auth: str = DEFAULT_AUTH_MODE
    auth_home: str = ""
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "provider_id", "executable", "protocol", "env_allow", "entrypoint",
        "auth", "auth_home"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _provider_id(self.provider_id))
        if type(self.executable) is not str or "\x00" in self.executable:
            raise ProviderConfigError("executable must be a NUL-free absolute path string")
        if not _is_absolute(self.executable):
            raise ProviderConfigError("executable must be an absolute operator-pinned path")
        if type(self.protocol) is not str or self.protocol not in KNOWN_PROTOCOLS:
            raise ProviderConfigError("protocol must name a reviewed provider protocol")
        object.__setattr__(self, "env_allow", _reviewed_env_names(self.env_allow))
        if type(self.entrypoint) is not str or "\x00" in self.entrypoint:
            raise ProviderConfigError("entrypoint must be a NUL-free absolute path string")
        if self.entrypoint and not _is_absolute(self.entrypoint):
            raise ProviderConfigError("entrypoint must be an absolute operator-pinned path")
        self._reviewed_login()

    def _reviewed_login(self) -> None:
        """Close the login half: a named mode, a directory only where one is read.

        The directory is refused unless the mode reads it, and required where the
        mode does. A path a build would never open is not a harmless spare
        field: an operator who wrote one would believe a login was configured.
        """
        if type(self.auth) is not str or self.auth not in AUTH_MODES:
            raise ProviderConfigError(
                f"auth must name a reviewed authentication mode: {sorted(AUTH_MODES)}")
        if type(self.auth_home) is not str or "\x00" in self.auth_home:
            raise ProviderConfigError("auth_home must be a NUL-free absolute path string")
        if self.auth == SUBSCRIPTION_AUTH:
            if self.protocol not in SUBSCRIPTION_PROTOCOLS:
                raise ProviderConfigError(
                    f"protocol {self.protocol!r} has no transport that drives a "
                    f"vendor login; {SUBSCRIPTION_AUTH} is implemented for "
                    f"{sorted(SUBSCRIPTION_PROTOCOLS)}")
            if not self.auth_home:
                raise ProviderConfigError(
                    "subscription authentication needs auth_home, "
                    "the directory this provider's login is kept in")
            forwarded = sorted(set(self.env_allow) & API_BILLING_ENV)
            if forwarded:
                raise ProviderConfigError(
                    f"subscription authentication may not forward {forwarded}: "
                    "the harness would bill an API account instead of the subscription")
        elif self.auth_home:
            raise ProviderConfigError(
                f"auth_home is read only in {SUBSCRIPTION_AUTH} authentication")
        if self.auth_home and not _is_absolute(self.auth_home):
            raise ProviderConfigError("auth_home must be an absolute operator-pinned path")

    def as_dict(self) -> dict[str, Any]:
        if type(self) is not ProviderConfig:
            raise ProviderConfigError("provider config must remain canonical")
        canonical = _rebuilt_config(self)
        return {
            "provider_id": canonical.provider_id, "executable": canonical.executable,
            "protocol": canonical.protocol, "env_allow": list(canonical.env_allow),
            "entrypoint": canonical.entrypoint, "auth": canonical.auth,
            "auth_home": canonical.auth_home}

    @classmethod
    def from_dict(cls, value: object) -> "ProviderConfig":
        data = _exact_fields(value, ProviderConfig._FIELDS, "provider config")
        if type(data["env_allow"]) is not list:
            raise ProviderConfigError("env_allow must be a JSON array of names")
        return ProviderConfig(**data)


def _rebuilt_config(config: ProviderConfig) -> ProviderConfig:
    failed = False
    try:
        rebuilt = ProviderConfig(
            config.provider_id, config.executable, config.protocol, config.env_allow,
            config.entrypoint, config.auth, config.auth_home)
    except Exception:  # noqa: BLE001 -- a mutated value retains no hostile graph
        failed = True
        rebuilt = None
    if failed:
        raise ProviderConfigError("provider config must remain canonical") from None
    assert rebuilt is not None
    return rebuilt


def reconstruct_config(value: object) -> ProviderConfig:
    """Rebuild the exact base ProviderConfig before one field of it is read."""
    if type(value) is not ProviderConfig:
        raise ProviderConfigError("provider config must be an exact ProviderConfig")
    return ProviderConfig.from_dict(_plain(value.as_dict()))


@dataclass(frozen=True)
class ProviderCatalogEntry:
    """A code-owned, reviewed provider template the factory resolves against."""

    provider_id: str
    display_name: str
    vendor: str
    protocol: str
    capabilities: tuple[str, ...]
    schema_pairs: tuple[tuple[str, str], ...]
    lifecycle: tuple[str, ...]
    adapter_class: type
    implementation: str = WEAKEST_IMPLEMENTATION
    _DATA: ClassVar[frozenset[str]] = frozenset({
        "provider_id", "display_name", "vendor", "protocol", "capabilities",
        "schema_pairs", "lifecycle", "implementation"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _provider_id(self.provider_id))
        object.__setattr__(self, "display_name", _reviewed_text("display_name", self.display_name))
        object.__setattr__(self, "vendor", _reviewed_text("vendor", self.vendor))
        if type(self.protocol) is not str or self.protocol not in KNOWN_PROTOCOLS:
            raise ProviderConfigError("protocol must name a reviewed provider protocol")
        object.__setattr__(self, "capabilities", _reviewed_capabilities(self.capabilities))
        object.__setattr__(self, "schema_pairs", _reviewed_schema_relation(
            self.capabilities, self.schema_pairs))
        object.__setattr__(self, "lifecycle", _reviewed_lifecycle(self.lifecycle))
        if not isinstance(self.adapter_class, type):
            raise ProviderConfigError("adapter_class must be an adapter type")
        if self.implementation not in IMPLEMENTATION_STATES:
            raise ProviderConfigError("implementation must name a reviewed state")

    def as_data(self) -> dict[str, Any]:
        """Every JSON-able field of this entry; the adapter class is carried apart."""
        if type(self) is not ProviderCatalogEntry:
            raise ProviderConfigError("provider catalog entry must remain canonical")
        return {
            "provider_id": self.provider_id, "display_name": self.display_name,
            "vendor": self.vendor, "protocol": self.protocol,
            "capabilities": list(self.capabilities),
            "schema_pairs": [list(pair) for pair in self.schema_pairs],
            "lifecycle": list(self.lifecycle), "implementation": self.implementation}


def reconstruct_entry(value: object) -> ProviderCatalogEntry:
    """Rebuild the exact base catalog entry before one field of it is read.

    A subclass is refused outright, so a lying ``as_data`` never runs; every other
    field is re-read as plain JSON data and re-validated, so a value mutated past
    its constructor with ``object.__setattr__`` cannot reach the door intact.
    """
    if type(value) is not ProviderCatalogEntry:
        raise ProviderConfigError("catalog entry must be an exact ProviderCatalogEntry")
    adapter_class = value.adapter_class
    if not isinstance(adapter_class, type):
        raise ProviderConfigError("adapter_class must be an adapter type")
    return _closed(
        lambda: ProviderCatalogEntry(
            adapter_class=adapter_class,
            **_exact_fields(_plain(value.as_data()), ProviderCatalogEntry._DATA, "entry")),
        "catalog entry must remain canonical")


@dataclass(frozen=True)
class ProviderContract:
    """One immutable provider descriptor: identity, availability, and controls.

    It carries no executable, no argv, no cwd, no env value, no token, no PID, and
    no raw output -- only what the Cockpit may see. ``available`` is derived from
    ``availability`` and is true only in the ``available`` state. ``lifecycle``
    names the adapter seams the provider implements; ``ProviderRegistry`` refuses
    a seam the adapter class does not really carry.
    """

    provider_id: str
    display_name: str
    vendor: str
    version: str
    capabilities: tuple[str, ...]
    schema_pairs: tuple[tuple[str, str], ...]
    lifecycle: tuple[str, ...]
    availability: str
    available: bool
    implementation: str = WEAKEST_IMPLEMENTATION
    auth: str = UNPINNED_AUTH
    #: The VENDOR's own sandbox, per road, read off this provider's profile:
    #: ``None`` where the integration declares nothing, ``()`` where it declares
    #: the vendor ships none, pairs where it names the tokens each road pins.
    #: A fact about somebody else's product, and never a claim about what THIS
    #: build protects -- the isolation table answers that separately.
    vendor_sandbox: tuple[tuple[str, str], ...] | None = None
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "provider_id", "display_name", "vendor", "version", "capabilities",
        "schema_pairs", "lifecycle", "availability", "available", "implementation",
        "auth", "vendor_sandbox"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_id", _provider_id(self.provider_id))
        for name in ("display_name", "vendor", "version"):
            object.__setattr__(self, name, _reviewed_text(name, getattr(self, name)))
        object.__setattr__(self, "capabilities", _reviewed_capabilities(self.capabilities))
        object.__setattr__(self, "schema_pairs", _reviewed_schema_relation(
            self.capabilities, self.schema_pairs))
        object.__setattr__(self, "lifecycle", _reviewed_lifecycle(self.lifecycle))
        if self.availability not in AVAILABILITY_STATES:
            raise ProviderConfigError("availability must name a reviewed state")
        if self.implementation not in IMPLEMENTATION_STATES:
            raise ProviderConfigError("implementation must name a reviewed state")
        if type(self.available) is not bool:
            raise ProviderConfigError("available must be a boolean")
        if self.available is not (self.availability == "available"):
            raise ProviderConfigError("available must equal the resolved availability state")
        if self.auth not in CONTRACT_AUTH_STATES:
            raise ProviderConfigError("auth must name a reviewed login state")
        if self.availability == "unconfigured" and self.auth != UNPINNED_AUTH:
            # The dangerous direction, and the only one refused here: a provider
            # NO row named cannot carry a login somebody pinned. The mirror case
            # under-claims -- it says no login was pinned when one was -- and the
            # resolver that reads the config is where that is proved, because it
            # is the only place that holds both facts.
            raise ProviderConfigError(
                "a provider no row configured carries an unpinned login")
        object.__setattr__(self, "vendor_sandbox", _reviewed_vendor_sandbox(
            self.vendor_sandbox))

    def as_dict(self) -> dict[str, Any]:
        if type(self) is not ProviderContract:
            raise ProviderConfigError("provider contract must remain canonical")
        return {
            "provider_id": self.provider_id, "display_name": self.display_name,
            "vendor": self.vendor, "version": self.version,
            "capabilities": list(self.capabilities),
            "schema_pairs": [list(pair) for pair in self.schema_pairs],
            "lifecycle": list(self.lifecycle),
            "availability": self.availability, "available": self.available,
            "implementation": self.implementation, "auth": self.auth,
            "vendor_sandbox": (None if self.vendor_sandbox is None
                               else [list(pair) for pair in self.vendor_sandbox])}


def reconstruct_contract(value: object) -> ProviderContract:
    """Rebuild the exact base ProviderContract before one field of it is read."""
    if type(value) is not ProviderContract:
        raise ProviderConfigError("provider contract must be an exact ProviderContract")
    return _closed(
        lambda: ProviderContract(
            **_exact_fields(_plain(value.as_dict()), ProviderContract._FIELDS, "contract")),
        "provider contract must remain canonical")


def _prove_schema_relation(entry: ProviderCatalogEntry) -> None:
    """Prove the declared relation IS the adapter class's own schema mapping.

    The class's mapping is re-read as plain pairs and compared as a WHOLE, so a
    declared control the class binds no schema to, a schema the entry invented,
    and a schema bound under another name are each refused here, at registration.
    """
    schemas = getattr(entry.adapter_class, "argument_schemas", None)
    if not isinstance(schemas, Mapping):
        raise ProviderConfigError("adapter class must declare an argument schema mapping")
    declared: list[tuple[str, str]] = []
    for capability, schema in dict(schemas).items():
        if type(capability) is not str or type(schema) is not str:
            raise ProviderConfigError("adapter argument schemas must be name/schema strings")
        declared.append((capability, schema))
    if tuple(sorted(declared)) != entry.schema_pairs:
        raise ProviderConfigError(
            "every declared capability requires the adapter's own exact argument schema")


def _prove_lifecycle(entry: ProviderCatalogEntry) -> None:
    """Prove every declared lifecycle seam is a real callable on the adapter class."""
    missing = sorted(
        seam for seam in entry.lifecycle
        if not callable(getattr(entry.adapter_class, seam, None)))
    if missing:
        raise ProviderConfigError(
            f"adapter class does not implement declared lifecycle seams {missing}")


class ProviderRegistry:
    """The one door a provider passes before it can be described or spawned.

    Registration is refused unless the supplied catalog entry reconstructs to its
    exact base value, binds exactly the adapter class's own argument schema to
    each declared control, declares only lifecycle seams that class really
    implements, and carries an identity no registered provider already holds. An
    AVAILABLE provider must hand over an instance of its catalogued adapter; an
    unavailable one must hand over none, so an unavailable provider owns no
    adapter and no spawn is reachable through it. Every refusal happens before
    anything is stored, so a refused provider leaves no trace. This door opens no
    process, filesystem, environment, or network door of its own.
    """

    def __init__(self) -> None:
        self._adapters = AdapterRegistry()
        self._contracts: dict[str, ProviderContract] = {}

    @property
    def adapters(self) -> AdapterRegistry:
        """The adapters of AVAILABLE providers only: the runtime's whole spawn surface."""
        return self._adapters

    def contracts(self) -> tuple[ProviderContract, ...]:
        """Every registered provider's descriptor, rebuilt before it is handed out."""
        return tuple(
            reconstruct_contract(self._contracts[key]) for key in sorted(self._contracts))

    def register(
            self, entry: object, *, availability: str, auth: str = UNPINNED_AUTH,
            adapter: object = None) -> ProviderContract:
        """Admit one provider, or refuse it and change nothing."""
        canonical = reconstruct_entry(entry)
        if type(availability) is not str or availability not in AVAILABILITY_STATES:
            raise ProviderConfigError("availability must name a reviewed state")
        if type(auth) is not str or auth not in CONTRACT_AUTH_STATES:
            raise ProviderConfigError("auth must name a reviewed login state")
        if canonical.provider_id in self._contracts:
            raise ProviderConfigError(
                f"provider {canonical.provider_id!r} is already registered")
        _prove_schema_relation(canonical)
        _prove_lifecycle(canonical)
        contract = ProviderContract(
            provider_id=canonical.provider_id, display_name=canonical.display_name,
            vendor=canonical.vendor, version=canonical.protocol,
            capabilities=canonical.capabilities, schema_pairs=canonical.schema_pairs,
            lifecycle=canonical.lifecycle, availability=availability,
            available=(availability == "available"),
            implementation=canonical.implementation, auth=auth,
            # Read off the adapter CLASS's profile: no instance is built, no
            # version probe runs and no login is asked, because a person opening
            # Confirm may not set a vendor process going. An adapter with no
            # profile -- every plugin in the test roster -- declares nothing,
            # and nothing is not an absence.
            vendor_sandbox=getattr(
                getattr(canonical.adapter_class, "profile", None),
                "vendor_sandbox", None))
        self._admit_adapter(canonical, adapter, contract.available)
        self._contracts[canonical.provider_id] = contract
        return contract

    def _admit_adapter(
            self, entry: ProviderCatalogEntry, adapter: object, available: bool) -> None:
        if not available:
            if adapter is not None:
                raise ProviderConfigError(
                    "an unavailable provider must be given no adapter to spawn")
            return
        if type(adapter) is not entry.adapter_class:
            raise ProviderConfigError(
                "an available provider requires an instance of its catalogued adapter")
        manifest = getattr(adapter, "manifest", None)
        if getattr(manifest, "adapter_id", None) != entry.provider_id:
            raise ProviderConfigError(
                "adapter identity does not match the provider identity")
        try:
            self._adapters.register(adapter)
        except AdapterContractError as error:
            raise ProviderConfigError(str(error)) from None


def provider_projection(contracts: Iterable[ProviderContract]) -> list[dict[str, Any]]:
    """Project reviewed provider contracts onto the closed Cockpit surface.

    Each row carries exactly the six names the UI may see -- provider id,
    display name, availability, implementation, the pinned login, and the PROVEN
    controls -- and nothing a provider did not declare. ``auth`` is the mode an
    operator WROTE, never a proof that the login works: what a machine can start,
    which build answers, which login was pinned, and whether a real authenticated
    run ever happened are four different claims, and this row carries the first
    three of them side by side. A control is proven when the contract
    binds it to an argument schema, which ``ProviderRegistry.register`` admits
    only after matching the whole relation against the adapter class's own
    schemas. No executable, argv, cwd, env value, protocol token, secret, PID,
    lifecycle seam, or raw output ever reaches this projection.

    ``availability`` and ``implementation`` answer two different questions and
    are carried side by side, each in its own closed vocabulary
    (:data:`AVAILABILITY_STATES` and :data:`IMPLEMENTATION_STATES`, which share no
    value). Neither is derived from the other and neither is derived from the
    display name: a consumer joins these rows by ``provider_id``, and a display
    name is a label to show, never a fact to parse.
    """
    if isinstance(contracts, (str, bytes)):
        raise ProviderConfigError("provider contracts must be an iterable of contracts")
    return [
        {
            "provider_id": contract.provider_id,
            "display_name": contract.display_name,
            "availability": contract.availability,
            "implementation": contract.implementation,
            "auth": contract.auth,
            "controls": sorted(capability for capability, _ in contract.schema_pairs),
            # The vendor's own mechanism, per road, carried rather than derived:
            # the request path may not know which provider has what. `null` is
            # an integration that declares nothing and is not an absence.
            "vendor_sandbox": (
                None if contract.vendor_sandbox is None
                else [list(pair) for pair in contract.vendor_sandbox]),
        }
        for contract in (reconstruct_contract(row) for row in contracts)
    ]
