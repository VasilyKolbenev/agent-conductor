"""Closed browser inputs and typed sanitized refusals for C/API-1.

The value mappers construct no durable response and call no service, store,
runtime, adapter, filesystem, process, or server seam.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any

from .adapters import UnsupportedCapability
from .contracts import ActionProposal, ContractError, DecisionReceipt
from .run_store import CorruptRun, RecordConflict, StoreError
from .runtime import AuthorizationError, Confirmation
from .service import ServiceError
from .http_transport import HttpRefusal


ERROR_STATUS = MappingProxyType({
    "same_origin_denied": 403,
    "csrf_denied": 403,
    "method_not_allowed": 405,
    "route_not_found": 404,
    "malformed_request": 400,
    "contract_invalid": 422,
    "run_corrupt": 409,
    "store_error": 500,
    "route_unsafe": 409,
    "service_refused": 409,
    "capability_unsupported": 409,
    "authorization_refused": 409,
    "record_conflict": 409,
})

_FIXED_MESSAGES = MappingProxyType({
    "same_origin_denied": "request origin is not allowed",
    "csrf_denied": "request CSRF token is not current",
    "method_not_allowed": "request method is not allowed for this route",
    "route_not_found": "command route does not exist",
    "malformed_request": "request transport or JSON shape is malformed",
    "contract_invalid": "request values do not satisfy the contract",
    "run_corrupt": "stored run is corrupt",
    "store_error": "run store could not complete the request",
    "route_unsafe": "run route is not structurally contained",
    "service_refused": "command service refused the request",
    "capability_unsupported": "adapter does not support this capability",
    "authorization_refused": "confirmation did not authorize the request",
    "record_conflict": "durable record identity conflicts",
})

ARGUMENT_SCHEMAS = MappingProxyType({
    "message": ("message",),
    "dispatch": ("handoff",),
    "review": ("handoff",),
    "evidence": ("action_id",),
    "pause": ("action_id",),
    "resume": ("action_id",),
    "retry": ("action_id",),
    "stop": ("action_id",),
    "switch": ("action_id", "instance_id"),
    "notify": ("message",),
})

_PROPOSAL_REQUIRED = frozenset({
    "instance_id", "attempt_id", "capability", "arguments", "scope",
    "proposed_by", "rationale", "timeout_seconds",
})
_PROPOSAL_FIELDS = _PROPOSAL_REQUIRED | {"adapter_id"}
_CONFIRM_FIELDS = frozenset({
    "proposal_id", "preview_digest", "capability", "scope", "config_digest",
    "confirmed_by",
})
_DECISION_FIELDS = frozenset({
    "receipt_id", "gate_id", "action", "actor", "reason", "scope_refs",
    "evidence_refs", "supersedes",
})
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_REFUSAL_BUILD = object()
_PHASE_MESSAGES = MappingProxyType({
    "same_origin_denied": frozenset({
        "request Host is not allowed", "request origin is not allowed"}),
    "malformed_request": frozenset({
        "request transport or JSON shape is malformed",
        "request Content-Type is not supported",
        "request body is not one JSON object",
    }),
})


def _safe_id(value: object) -> bool:
    return isinstance(value, str) and _ID_RE.fullmatch(value) is not None


@dataclass(frozen=True, init=False)
class ApiRefusal(Exception):
    """One closed browser-safe refusal; no exception prose is carried through."""

    code: str
    message: str
    detail: Mapping[str, str]

    def __init__(
            self, build: object, code: str, message: str,
            detail: Mapping[str, str]) -> None:
        if build is not _REFUSAL_BUILD:
            raise ValueError("API refusals require a reviewed factory")
        if code not in ERROR_STATUS:
            raise ValueError("unknown API refusal code")
        copied = dict(detail)
        if copied:
            expected = {"run_id", "instance_id"}
            if (code != "service_refused" or set(copied) != expected
                    or any(not _safe_id(copied[key]) for key in expected)
                    or message != (
                        f"frozen config declares no instance '{copied['instance_id']}'")):
                raise ValueError("API refusal detail must match a reviewed fact")
        else:
            messages = _PHASE_MESSAGES.get(code, frozenset()) | {
                _FIXED_MESSAGES[code]}
            if message not in messages:
                raise ValueError("API refusal message must match a reviewed template")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "detail", MappingProxyType(copied))
        Exception.__init__(self, message)

    @property
    def status(self) -> int:
        return ERROR_STATUS[self.code]

    def as_dict(self) -> dict[str, object]:
        """Return exactly the frozen refusal envelope."""
        return {"error": {
            "code": self.code, "message": self.message, "detail": dict(self.detail)}}

    @classmethod
    def fixed(cls, code: str) -> "ApiRefusal":
        """Build one vocabulary-complete refusal with no submitted detail."""
        if code not in _FIXED_MESSAGES:
            raise ValueError("unknown API refusal code") from None
        return cls(_REFUSAL_BUILD, code, _FIXED_MESSAGES[code], {})

    @classmethod
    def from_http(cls, refusal: HttpRefusal) -> "ApiRefusal":
        """Preserve the transport's reviewed phase-specific safe message."""
        if not isinstance(refusal, HttpRefusal):
            raise ValueError("HTTP refusal must be typed")
        return cls(_REFUSAL_BUILD, refusal.code, refusal.message, {})

    @classmethod
    def service_missing_instance(
            cls, run_id: str, instance_id: str) -> "ApiRefusal":
        """Name one validated frozen-config relation without exception prose."""
        if not _safe_id(run_id) or not _safe_id(instance_id):
            raise ValueError("service refusal identifiers must be safe IDs") from None
        detail = {"run_id": run_id, "instance_id": instance_id}
        message = f"frozen config declares no instance '{instance_id}'"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)


@dataclass(frozen=True)
class ProposalInput:
    """Validated browser facts ready for CommandService.propose on a later slice."""

    instance_id: str
    attempt_id: str
    capability: str
    arguments: Mapping[str, Any]
    scope: tuple[str, ...]
    proposed_by: str
    rationale: str
    timeout_seconds: int
    adapter_id: str | None


@dataclass(frozen=True)
class ConfirmInput:
    """Closed Human confirmation facts; ids and time are injected later."""

    proposal_id: str
    preview_digest: str
    capability: str
    scope: tuple[str, ...]
    config_digest: str
    confirmed_by: str

    def build(
            self, *, confirmation_id: str, run_id: str,
            confirmed_at: str) -> Confirmation:
        return Confirmation(
            confirmation_id=confirmation_id, run_id=run_id,
            proposal_id=self.proposal_id, preview_digest=self.preview_digest,
            capability=self.capability, scope=self.scope,
            config_digest=self.config_digest, confirmed_by=self.confirmed_by,
            confirmed_at=confirmed_at)


@dataclass(frozen=True)
class DecisionInput:
    """Closed Human decision facts; run/config/time are injected later."""

    receipt_id: str
    gate_id: str
    action: str
    actor: str
    reason: str
    scope_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    supersedes: str | None

    def build(
            self, *, run_id: str, decided_at: str,
            config_digest: str) -> DecisionReceipt:
        return DecisionReceipt(
            receipt_id=self.receipt_id, run_id=run_id, gate_id=self.gate_id,
            action=self.action, actor=self.actor, decided_at=decided_at,
            reason=self.reason, scope_refs=self.scope_refs,
            config_digest=config_digest, evidence_refs=self.evidence_refs,
            supersedes=self.supersedes)


def _closed(body: object, fields: frozenset[str]) -> dict[str, Any]:
    if not isinstance(body, Mapping) or any(not isinstance(key, str) for key in body):
        raise ApiRefusal.fixed("contract_invalid")
    supplied = set(body)
    if supplied != fields:
        raise ApiRefusal.fixed("contract_invalid")
    return dict(body)


def _proposal_body(body: object) -> dict[str, Any]:
    if not isinstance(body, Mapping) or any(not isinstance(key, str) for key in body):
        raise ApiRefusal.fixed("contract_invalid")
    supplied = set(body)
    if not _PROPOSAL_REQUIRED <= supplied <= _PROPOSAL_FIELDS:
        raise ApiRefusal.fixed("contract_invalid")
    return dict(body)


def _contract(call, *args, **kwargs):
    invalid = False
    try:
        result = call(*args, **kwargs)
    except (ContractError, TypeError):
        invalid = True
        result = None
    if invalid:
        raise ApiRefusal.fixed("contract_invalid") from None
    return result


def _capabilities(values: Iterable[str]) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise ApiRefusal.fixed("capability_unsupported") from None
    invalid = False
    try:
        rows = frozenset(values)
    except Exception:  # noqa: BLE001 -- adapter iterable prose is discarded
        invalid = True
        rows = frozenset()
    if invalid:
        raise ApiRefusal.fixed("capability_unsupported") from None
    if any(not isinstance(row, str) for row in rows):
        raise ApiRefusal.fixed("capability_unsupported") from None
    return rows


def _argument_values(capability: str, arguments: Mapping[str, Any]) -> None:
    for name, value in arguments.items():
        if name == "message":
            valid = isinstance(value, str) and bool(value.strip()) and "\x00" not in value
        else:
            valid = isinstance(value, str) and _ID_RE.fullmatch(value) is not None
        if not valid:
            raise ApiRefusal.fixed("contract_invalid")


def _json_array(values: dict[str, Any], name: str) -> list[Any]:
    value = values[name]
    if not isinstance(value, list):
        raise ApiRefusal.fixed("contract_invalid")
    return value


def parse_proposal(
        body: object, *, adapter_capabilities: Iterable[str]) -> ProposalInput:
    """Validate the closed capability request without proposing or appending."""
    values = _proposal_body(body)
    capability = values["capability"]
    capabilities = _capabilities(adapter_capabilities)
    if not _safe_id(capability):
        raise ApiRefusal.fixed("contract_invalid") from None
    if (capability == "observe" or capability not in ARGUMENT_SCHEMAS
            or capability not in capabilities):
        raise ApiRefusal.fixed("capability_unsupported")
    arguments = values["arguments"]
    if not isinstance(arguments, Mapping) or set(arguments) != set(
            ARGUMENT_SCHEMAS[capability]):
        raise ApiRefusal.fixed("contract_invalid")
    _argument_values(capability, arguments)
    scope = _json_array(values, "scope")
    probe = _contract(
        ActionProposal,
        proposal_id="api-proposal-validation", run_id="api-run-validation",
        attempt_id=values["attempt_id"], instance_id=values["instance_id"],
        capability=capability, arguments=arguments, scope=scope,
        proposed_by=values["proposed_by"], proposed_at="2000-01-01T00:00:00Z",
        timeout_seconds=values["timeout_seconds"], rationale=values["rationale"],
        config_digest="sha256:" + "0" * 64)
    adapter_id = values.get("adapter_id")
    if "adapter_id" in values and not _safe_id(adapter_id):
        raise ApiRefusal.fixed("contract_invalid") from None
    return ProposalInput(
        instance_id=probe.instance_id, attempt_id=probe.attempt_id,
        capability=probe.capability, arguments=probe.arguments, scope=probe.scope,
        proposed_by=probe.proposed_by, rationale=probe.rationale,
        timeout_seconds=probe.timeout_seconds, adapter_id=adapter_id)


def parse_confirmation(body: object) -> ConfirmInput:
    """Validate exactly the six caller-owned Human confirmation facts."""
    values = _closed(body, _CONFIRM_FIELDS)
    scope = _json_array(values, "scope")
    confirmation = _contract(
        Confirmation,
        confirmation_id="api-confirmation-validation", run_id="api-run-validation",
        proposal_id=values["proposal_id"], preview_digest=values["preview_digest"],
        capability=values["capability"], scope=scope,
        config_digest=values["config_digest"], confirmed_by=values["confirmed_by"],
        confirmed_at="2000-01-01T00:00:00Z")
    return ConfirmInput(
        proposal_id=confirmation.proposal_id,
        preview_digest=confirmation.preview_digest,
        capability=confirmation.capability, scope=confirmation.scope,
        config_digest=confirmation.config_digest,
        confirmed_by=confirmation.confirmed_by)


def parse_decision(body: object) -> DecisionInput:
    """Validate exactly the eight caller-owned Human decision facts."""
    values = _closed(body, _DECISION_FIELDS)
    scope_refs = _json_array(values, "scope_refs")
    evidence_refs = _json_array(values, "evidence_refs")
    decision = _contract(
        DecisionReceipt,
        receipt_id=values["receipt_id"], run_id="api-run-validation",
        gate_id=values["gate_id"], action=values["action"], actor=values["actor"],
        decided_at="2000-01-01T00:00:00Z", reason=values["reason"],
        scope_refs=scope_refs, config_digest="sha256:" + "0" * 64,
        evidence_refs=evidence_refs, supersedes=values["supersedes"])
    return DecisionInput(
        receipt_id=decision.receipt_id, gate_id=decision.gate_id,
        action=decision.action, actor=decision.actor, reason=decision.reason,
        scope_refs=decision.scope_refs, evidence_refs=decision.evidence_refs,
        supersedes=decision.supersedes)


def refusal_from_exception(error: Exception) -> ApiRefusal:
    """Translate only exception types; submitted/OS/adapter prose is discarded."""
    if isinstance(error, HttpRefusal):
        return ApiRefusal.from_http(error)
    if isinstance(error, CorruptRun):
        return ApiRefusal.fixed("run_corrupt")
    if isinstance(error, RecordConflict):
        return ApiRefusal.fixed("record_conflict")
    if isinstance(error, StoreError):
        return ApiRefusal.fixed("store_error")
    if isinstance(error, UnsupportedCapability):
        return ApiRefusal.fixed("capability_unsupported")
    if isinstance(error, ServiceError):
        return ApiRefusal.fixed("service_refused")
    if isinstance(error, AuthorizationError):
        return ApiRefusal.fixed("authorization_refused")
    if isinstance(error, ContractError):
        return ApiRefusal.fixed("contract_invalid")
    raise TypeError("exception type has no frozen API translation")
