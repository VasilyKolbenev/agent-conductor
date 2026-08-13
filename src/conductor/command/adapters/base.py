"""Adapter contracts and an explicit, non-probing registry.

This module has no process, filesystem, environment, or network door. It
validates what a configured adapter claims and exposes only declared
capabilities. The registry wraps prepare, execute, and verify so each untrusted
seam receives reconstructed contract values and each return crosses validation
again. `resolve` still hands back the configured adapter for internal binding;
the Confirm runtime performs effects only through the wrappers.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from ..contracts import (
    HEALTH_STATES,
    ActionRequest,
    ActionResultReceipt,
    ContractError,
    _id,
    _object,
    _text,
    _timestamp,
    canonical_json,
)
from ..dispatch import validate_dispatch_arguments


class AdapterContractError(ValueError):
    """An adapter claim is malformed or contradicts its registered identity."""


class UnsupportedCapability(AdapterContractError):
    """A caller requested a control the manifest does not declare."""


CAPABILITIES = frozenset({
    "observe",
    "message",
    "dispatch",
    "review",
    "evidence",
    "pause",
    "resume",
    "retry",
    "stop",
    "switch",
    "notify",
})
VERIFICATION_STATES = frozenset({"verified", "unavailable", "mismatch", "error"})
_UNRESTRICTED_COMMAND_FIELDS = frozenset({"cmd", "command", "script", "shell"})


def _contract(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except ContractError as e:
        raise AdapterContractError(str(e)) from e


def _capabilities(value: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise AdapterContractError("capabilities must be a list of declared capability ids")
    rows = tuple(value)
    if any(not isinstance(row, str) or row not in CAPABILITIES for row in rows):
        unknown = [row for row in rows if not isinstance(row, str) or row not in CAPABILITIES]
        raise AdapterContractError(
            f"capabilities contain unsupported values {unknown!r}; "
            f"allowed values are {sorted(CAPABILITIES)}")
    if len(set(rows)) != len(rows):
        raise AdapterContractError("capabilities must not contain duplicates")
    return rows


def _unrestricted_command_field(value: object, path: tuple[str, ...] = ()) -> str | None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normal = str(key).casefold().replace("-", "_")
            if normal in _UNRESTRICTED_COMMAND_FIELDS:
                return ".".join((*path, str(key)))
            found = _unrestricted_command_field(item, (*path, str(key)))
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _unrestricted_command_field(item, (*path, str(index)))
            if found is not None:
                return found
    return None


@dataclass(frozen=True)
class AdapterManifest:
    """Stable adapter identity and the complete set of controls it supports."""

    adapter_id: str
    display_name: str
    vendor: str
    version: str
    capabilities: tuple[str, ...] | list[str]
    docs_url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", _contract(_id, "adapter_id", self.adapter_id))
        for name in ("display_name", "vendor", "version"):
            object.__setattr__(self, name, _contract(_text, name, getattr(self, name)))
        object.__setattr__(self, "capabilities", _capabilities(self.capabilities))
        if not isinstance(self.docs_url, str):
            raise AdapterContractError("docs_url must be a string")
        if self.docs_url and not self.docs_url.startswith("https://"):
            raise AdapterContractError("docs_url must be empty or an https URL")

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def as_payload(self) -> dict[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "display_name": self.display_name,
            "vendor": self.vendor,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "docs_url": self.docs_url,
        }


@dataclass(frozen=True)
class AdapterObservation:
    """One adapter-reported observation; absence and unknown never become ready."""

    adapter_id: str
    instance_id: str
    run_id: str
    observed_at: str
    health: str
    available_capabilities: tuple[str, ...] | list[str] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        for name in ("adapter_id", "instance_id", "run_id"):
            object.__setattr__(self, name, _contract(_id, name, getattr(self, name)))
        object.__setattr__(
            self, "observed_at", _contract(_timestamp, "observed_at", self.observed_at))
        if self.health not in HEALTH_STATES:
            raise AdapterContractError(
                f"health must be one of {sorted(HEALTH_STATES)}, got {self.health!r}")
        object.__setattr__(
            self, "available_capabilities", _capabilities(self.available_capabilities))
        object.__setattr__(
            self, "detail", _contract(_text, "detail", self.detail, empty=True))


@dataclass(frozen=True)
class PreparedAction:
    """Adapter-specific preparation bound to one unchanged ActionRequest."""

    adapter_id: str
    request: ActionRequest
    adapter_payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "adapter_id", _contract(_id, "adapter_id", self.adapter_id))
        if not isinstance(self.request, ActionRequest):
            raise AdapterContractError("request must be a validated ActionRequest")
        unsafe = _unrestricted_command_field(self.adapter_payload)
        if unsafe is not None:
            raise AdapterContractError(
                f"adapter_payload contains unrestricted command field {unsafe!r}; "
                "use a capability-specific structure or an argv vector")
        object.__setattr__(
            self, "adapter_payload", _contract(_object, "adapter_payload", self.adapter_payload))


@dataclass(frozen=True)
class AdapterVerification:
    """An adapter's explicit verification result, separate from process outcome."""

    adapter_id: str
    action_id: str
    state: str
    observed_at: str
    detail: str
    evidence_refs: tuple[str, ...] | list[str] = ()

    def __post_init__(self) -> None:
        for name in ("adapter_id", "action_id"):
            object.__setattr__(self, name, _contract(_id, name, getattr(self, name)))
        if self.state not in VERIFICATION_STATES:
            raise AdapterContractError(
                f"state must be one of {sorted(VERIFICATION_STATES)}, got {self.state!r}")
        object.__setattr__(
            self, "observed_at", _contract(_timestamp, "observed_at", self.observed_at))
        object.__setattr__(
            self, "detail", _contract(_text, "detail", self.detail, empty=True))
        if isinstance(self.evidence_refs, (str, bytes)):
            raise AdapterContractError("evidence_refs must be a list of evidence ids")
        refs = tuple(_contract(_id, "evidence_refs", ref) for ref in self.evidence_refs)
        if len(set(refs)) != len(refs):
            raise AdapterContractError("evidence_refs must not contain duplicates")
        if self.state == "verified" and not refs:
            raise AdapterContractError("verified evidence requires at least one evidence_ref")
        object.__setattr__(self, "evidence_refs", refs)


class Adapter(Protocol):
    """The four adapter seams driven by the Confirm runtime after authorization."""

    manifest: AdapterManifest

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation: ...

    def prepare(self, request: ActionRequest) -> PreparedAction: ...

    def execute(self, prepared: PreparedAction) -> ActionResultReceipt: ...

    def verify(
            self, request: ActionRequest, result: ActionResultReceipt,
    ) -> AdapterVerification: ...


class AdapterRegistry:
    """Adapters explicitly supplied by configuration; no discovery or global state."""

    def __init__(self, adapters: Iterable[Adapter] = ()) -> None:
        self._adapters: dict[str, Adapter] = {}
        self._manifests: dict[str, AdapterManifest] = {}
        self._argument_schemas: dict[str, Mapping[str, str]] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: Adapter) -> None:
        manifest = getattr(adapter, "manifest", None)
        if not isinstance(manifest, AdapterManifest):
            raise AdapterContractError("adapter.manifest must be an AdapterManifest")
        missing = [name for name in ("observe", "prepare", "execute", "verify")
                   if not callable(getattr(adapter, name, None))]
        if missing:
            raise AdapterContractError(f"adapter is missing protocol methods {missing}")
        if manifest.adapter_id in self._adapters:
            raise AdapterContractError(
                f"adapter {manifest.adapter_id!r} is already registered")
        # Keep the reviewed VALUE, not a pointer the adapter can still rewrite.
        reviewed = AdapterManifest(**manifest.as_payload())
        schemas = getattr(type(adapter), "argument_schemas", {})
        if not isinstance(schemas, Mapping):
            raise AdapterContractError("adapter argument_schemas must be a capability mapping")
        reviewed_schemas: dict[str, str] = {}
        for capability, schema in schemas.items():
            if capability not in reviewed.capabilities:
                raise AdapterContractError(
                    f"argument schema names undeclared capability {capability!r}")
            if schema != "structured-process-v1":
                raise AdapterContractError(
                    f"adapter declares unknown argument schema {schema!r}")
            reviewed_schemas[capability] = schema
        # Publish the registration only after every supplied claim validated.
        self._adapters[reviewed.adapter_id] = adapter
        self._manifests[reviewed.adapter_id] = reviewed
        self._argument_schemas[reviewed.adapter_id] = MappingProxyType(reviewed_schemas)

    def resolve(self, adapter_id: str) -> Adapter:
        safe = _contract(_id, "adapter_id", adapter_id)
        try:
            return self._adapters[safe]
        except KeyError as e:
            raise AdapterContractError(f"adapter {safe!r} is not registered") from e

    def manifests(self) -> tuple[AdapterManifest, ...]:
        # Hand back freshly built values, never the stored objects: a caller that
        # rewrites a returned manifest through object.__setattr__ must not be able
        # to reach controls(), _require(), or observation-width behind our back.
        return tuple(
            AdapterManifest(**self._manifests[adapter_id].as_payload())
            for adapter_id in sorted(self._manifests))

    def controls(self, adapter_id: str) -> tuple[str, ...]:
        self.resolve(adapter_id)
        return self._registered_manifest(adapter_id).capabilities

    def observe(self, adapter_id: str, instance_id: str, run_id: str) -> AdapterObservation:
        adapter = self._require(adapter_id, "observe")
        observed = adapter.observe(instance_id, run_id)
        if not isinstance(observed, AdapterObservation):
            raise AdapterContractError("observe must return AdapterObservation")
        registered = self._registered_manifest(adapter_id)
        if (observed.adapter_id != registered.adapter_id
                or observed.instance_id != instance_id or observed.run_id != run_id):
            raise AdapterContractError(
                "adapter returned identity for another adapter, instance, or run")
        undeclared = set(observed.available_capabilities) - set(registered.capabilities)
        if undeclared:
            raise AdapterContractError(
                f"observation reports undeclared capabilities {sorted(undeclared)}")
        return observed

    def prepare(self, adapter_id: str, request: ActionRequest) -> PreparedAction:
        if not isinstance(request, ActionRequest):
            raise AdapterContractError("request must be a validated ActionRequest")
        adapter = self._require(adapter_id, request.capability)
        # Compare against a VALUE taken before the adapter sees the request, so an
        # adapter that rewrites the caller's object in place cannot satisfy the check
        # by returning the very object both sides would otherwise read.
        authorized = _contract(canonical_json, request)
        handed = ActionRequest.from_dict(request.as_dict())
        prepared = adapter.prepare(handed)
        if not isinstance(prepared, PreparedAction):
            raise AdapterContractError("prepare must return PreparedAction")
        if prepared.adapter_id != self._registered_manifest(adapter_id).adapter_id:
            raise AdapterContractError("prepared adapter_id does not match the registered adapter")
        if _contract(canonical_json, prepared.request) != authorized:
            raise AdapterContractError("adapter changed the ActionRequest while preparing it")
        return PreparedAction(
            adapter_id=prepared.adapter_id,
            request=ActionRequest.from_dict(request.as_dict()),
            adapter_payload=prepared.adapter_payload)

    def execute(
            self, adapter_id: str, prepared: PreparedAction) -> ActionResultReceipt:
        """Call execute with a reconstructed request and return a reconstructed receipt."""
        if not isinstance(prepared, PreparedAction):
            raise AdapterContractError("execute requires a validated PreparedAction")
        adapter = self._require(adapter_id, prepared.request.capability)
        handed = PreparedAction(
            adapter_id=prepared.adapter_id,
            request=ActionRequest.from_dict(prepared.request.as_dict()),
            adapter_payload=prepared.adapter_payload)
        reported = adapter.execute(handed)
        if not isinstance(reported, ActionResultReceipt):
            raise AdapterContractError("execute must return ActionResultReceipt")
        return ActionResultReceipt.from_dict(reported.as_dict())

    def verify(
            self, adapter_id: str, request: ActionRequest,
            result: ActionResultReceipt) -> AdapterVerification:
        """Call verify with reconstructed facts and return a reconstructed value."""
        adapter = self._require(adapter_id, request.capability)
        verification = adapter.verify(
            ActionRequest.from_dict(request.as_dict()),
            ActionResultReceipt.from_dict(result.as_dict()))
        if not isinstance(verification, AdapterVerification):
            raise AdapterContractError("verify must return AdapterVerification")
        return AdapterVerification(
            adapter_id=verification.adapter_id,
            action_id=verification.action_id,
            state=verification.state,
            observed_at=verification.observed_at,
            detail=verification.detail,
            evidence_refs=verification.evidence_refs)

    def validate_arguments(
            self, adapter_id: str, capability: str, arguments: Mapping[str, Any]) -> None:
        """Run one registry-owned pure schema; never call the mutable adapter."""
        safe = _contract(_id, "adapter_id", adapter_id)
        manifest = self._registered_manifest(safe)
        if not manifest.supports(capability):
            raise UnsupportedCapability(
                f"adapter {safe!r} does not declare capability {capability!r}")
        if self._argument_schemas[safe].get(capability) == "structured-process-v1":
            validate_dispatch_arguments(arguments)

    def _require(self, adapter_id: str, capability: str) -> Adapter:
        adapter = self.resolve(adapter_id)
        manifest = self._registered_manifest(adapter_id)
        if not manifest.supports(capability):
            raise UnsupportedCapability(
                f"adapter {manifest.adapter_id!r} does not declare capability "
                f"{capability!r}")
        return adapter

    def _registered_manifest(self, adapter_id: str) -> AdapterManifest:
        safe = _contract(_id, "adapter_id", adapter_id)
        try:
            return self._manifests[safe]
        except KeyError as e:
            raise AdapterContractError(f"adapter {safe!r} is not registered") from e
