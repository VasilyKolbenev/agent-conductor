"""Immutable, value-only contracts shared by future deep adapters.

Nothing here probes an executable, reads an environment value, starts a process,
or claims a real Claude/Codex integration.  The Claude and Codex protocols are
deterministic fake protocols and their real modes remain explicitly unavailable
until separately proven.  ``DSH_HEADLESS_V1`` is the one token naming a protocol
published by a real vendor; naming it here buys no availability and no claim that
the tool is installed -- the harness adapter still spawns nothing until an
operator pins both absolute paths and an exact version preflight agrees.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, ClassVar

from ..contracts import ContractError, _digest, _id, _timestamp


class DeepContractError(ContractError):
    """A deep-adapter value is open-ended, secret-bearing, or contradictory."""


class DeepProtocol(str, Enum):
    FAKE_CLAUDE_V1 = "fake-claude-jsonl-v1"
    FAKE_CODEX_V1 = "fake-codex-jsonl-v1"
    DSH_HEADLESS_V1 = "dsh-headless-v1"
    #: Catalogued so Kimi Code can be SEEN, and unproven on purpose: no
    #: adapter in this build implements it, so it binds no argv flag and
    #: resolves no spawnable provider. See adapters/kimi_code.py.
    KIMI_UNPROVEN_V0 = "kimi-code-unproven-v0"


_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
OBSERVED_OUTCOMES = frozenset({
    "succeeded", "failed", "cancelled", "rejected", "unknown"})
ADAPTER_FAILURE_CODES = frozenset({
    "invalid_arguments", "executable_unavailable", "spawn_refused", "timeout",
    "stopped", "protocol_error", "output_limit", "lost_result",
    "recovery_unavailable", "identity_mismatch", "evidence_unavailable",
    "evidence_mismatch", "ownership_lost", "unsupported",
})
ADAPTER_FAILURE_PHASES = frozenset({
    "prepare", "execute", "observe", "verify", "recover", "stop",
})
RECOVERY_STATES = frozenset({
    "running", "succeeded", "failed", "cancelled", "unknown"})
RECOVERY_OUTCOMES = MappingProxyType({
    "succeeded": frozenset({"succeeded"}),
    "failed": frozenset({"failed", "rejected"}),
    "cancelled": frozenset({"cancelled"}),
    "unknown": frozenset({"unknown"}),
})


def _exact(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise DeepContractError(f"{name} must be an object with string keys")
    if set(value) != fields:
        raise DeepContractError(
            f"{name} fields must be exact; missing or extra fields are refused")
    return dict(value)


def _enum(name: str, value: object, allowed: frozenset[str]) -> str:
    if type(value) is not str or value not in allowed:
        raise DeepContractError(f"{name} must be one of {sorted(allowed)}")
    return value


def _ids(name: str, value: object, *, empty: bool = False) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise DeepContractError(f"{name} must be a list of ids")
    rows = tuple(value)
    if any(type(item) is not str for item in rows):
        raise DeepContractError(f"{name} must contain only contract ids")
    try:
        rows = tuple(_id(name, item) for item in rows)
    except ContractError:
        raise DeepContractError(f"{name} must contain only contract ids") from None
    if not empty and not rows:
        raise DeepContractError(f"{name} must not be empty")
    if len(rows) != len(set(rows)):
        raise DeepContractError(f"{name} must not repeat an id")
    return rows


def _closed_id(name: str, value: object) -> str:
    if type(value) is not str:
        raise DeepContractError(f"{name} must be a contract id")
    failed = False
    try:
        result = _id(name, value)
    except ContractError:
        failed = True
        result = ""
    if failed:
        raise DeepContractError(f"{name} must be a contract id") from None
    return result


def _closed_digest(name: str, value: object) -> str:
    if type(value) is not str:
        raise DeepContractError(f"{name} must be a sha256 digest")
    failed = False
    try:
        result = _digest(name, value)
    except ContractError:
        failed = True
        result = ""
    if failed:
        raise DeepContractError(f"{name} must be a sha256 digest") from None
    return result


def _closed_timestamp(name: str, value: object) -> str:
    if type(value) is not str:
        raise DeepContractError(f"{name} must be an RFC 3339 UTC timestamp")
    failed = False
    try:
        result = _timestamp(name, value)
    except (ContractError, OverflowError, ValueError):
        failed = True
        result = ""
    if failed:
        raise DeepContractError(
            f"{name} must be an RFC 3339 UTC timestamp") from None
    return result


def _env_names(value: object) -> tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise DeepContractError("env_allow must contain unique environment names")
    names = tuple(value)
    if (any(type(row) is not str or _ENV_NAME.fullmatch(row) is None
            for row in names) or len(names) != len(set(names))):
        raise DeepContractError("env_allow must contain unique environment names")
    return names


def _exit_relation(outcome: str, exit_code: object) -> int | None:
    if exit_code is not None and type(exit_code) is not int:
        raise DeepContractError("exit_code must be an integer or null")
    if outcome == "succeeded" and exit_code not in (None, 0):
        raise DeepContractError("succeeded exit_code must be zero or null")
    if outcome == "failed" and exit_code == 0:
        raise DeepContractError("failed exit_code must be nonzero or null")
    if outcome in {"cancelled", "rejected", "unknown"} and exit_code is not None:
        raise DeepContractError(f"{outcome} exit_code must be null")
    return exit_code


@dataclass(frozen=True)
class DeepAdapterConfig:
    executable: str
    protocol: DeepProtocol | str
    env_allow: tuple[str, ...] | list[str] = ()
    real_mode: str = "unavailable"
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "executable", "protocol", "env_allow", "real_mode"})

    def __post_init__(self) -> None:
        if type(self.executable) is not str or "\x00" in self.executable:
            raise DeepContractError("executable must be a NUL-free absolute path string")
        if not (PurePosixPath(self.executable).is_absolute()
                or PureWindowsPath(self.executable).is_absolute()):
            raise DeepContractError("executable must be an absolute configured path")
        failed = False
        if isinstance(self.protocol, DeepProtocol):
            protocol = self.protocol
        elif type(self.protocol) is not str:
            failed = True
            protocol = DeepProtocol.FAKE_CLAUDE_V1
        else:
            try:
                protocol = DeepProtocol(self.protocol)
            except (TypeError, ValueError):
                failed = True
                protocol = DeepProtocol.FAKE_CLAUDE_V1
        if failed:
            raise DeepContractError(
                "protocol must name one reviewed fake protocol") from None
        names = _env_names(self.env_allow)
        if type(self.real_mode) is not str or self.real_mode != "unavailable":
            raise DeepContractError("real_mode remains 'unavailable' until opt-in proof lands")
        object.__setattr__(self, "protocol", protocol)
        object.__setattr__(self, "env_allow", names)

    def as_dict(self) -> dict[str, Any]:
        if type(self) is not DeepAdapterConfig:
            raise DeepContractError("deep adapter config must remain canonical")
        failed = False
        try:
            canonical = DeepAdapterConfig(
                self.executable, self.protocol, self.env_allow, self.real_mode)
        except Exception:  # noqa: BLE001 -- a mutated value remains untrusted
            failed = True
            canonical = None
        if failed:
            raise DeepContractError(
                "deep adapter config must remain canonical") from None
        assert canonical is not None
        return {
            "executable": canonical.executable, "protocol": canonical.protocol.value,
            "env_allow": list(canonical.env_allow), "real_mode": canonical.real_mode}

    @classmethod
    def from_dict(cls, value: object) -> "DeepAdapterConfig":
        data = _exact(value, DeepAdapterConfig._FIELDS, "deep adapter config")
        if type(data["env_allow"]) is not list:
            raise DeepContractError("env_allow must be a JSON array")
        return DeepAdapterConfig(**data)


@dataclass(frozen=True)
class RecoveryRef:
    scheme: str
    adapter_id: str
    action_id: str
    digest: str
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "scheme", "adapter_id", "action_id", "digest"})

    def __post_init__(self) -> None:
        if type(self.scheme) is not str or self.scheme != "fake-ledger-v1":
            raise DeepContractError("recovery scheme must be 'fake-ledger-v1'")
        object.__setattr__(self, "adapter_id", _closed_id("adapter_id", self.adapter_id))
        object.__setattr__(self, "action_id", _closed_id("action_id", self.action_id))
        object.__setattr__(self, "digest", _closed_digest("recovery digest", self.digest))

    def as_dict(self) -> dict[str, str]:
        return {"scheme": self.scheme, "adapter_id": self.adapter_id,
                "action_id": self.action_id, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: object) -> "RecoveryRef":
        return RecoveryRef(**_exact(value, RecoveryRef._FIELDS, "recovery ref"))


@dataclass(frozen=True)
class AdapterFailure:
    code: str
    phase: str
    retryable: bool
    _FIELDS: ClassVar[frozenset[str]] = frozenset({"code", "phase", "retryable"})

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "code", _enum("code", self.code, ADAPTER_FAILURE_CODES))
        object.__setattr__(
            self, "phase", _enum("phase", self.phase, ADAPTER_FAILURE_PHASES))
        if not isinstance(self.retryable, bool):
            raise DeepContractError("retryable must be a boolean")

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "phase": self.phase, "retryable": self.retryable}

    @classmethod
    def from_dict(cls, value: object) -> "AdapterFailure":
        return AdapterFailure(**_exact(value, AdapterFailure._FIELDS, "adapter failure"))


@dataclass(frozen=True)
class NormalizedResult:
    run_id: str
    action_id: str
    attempt_id: str
    instance_id: str
    adapter_id: str
    outcome: str
    observed_at: str
    exit_code: int | None
    failure: AdapterFailure | None = None
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "run_id", "action_id", "attempt_id", "instance_id", "adapter_id",
        "outcome", "observed_at", "exit_code", "failure"})

    def __post_init__(self) -> None:
        for name in ("run_id", "action_id", "attempt_id", "instance_id", "adapter_id"):
            object.__setattr__(self, name, _closed_id(name, getattr(self, name)))
        object.__setattr__(
            self, "outcome", _enum("outcome", self.outcome, OBSERVED_OUTCOMES))
        object.__setattr__(
            self, "observed_at", _closed_timestamp("observed_at", self.observed_at))
        object.__setattr__(self, "exit_code", _exit_relation(self.outcome, self.exit_code))
        if self.outcome == "succeeded" and self.failure is not None:
            raise DeepContractError("succeeded result cannot carry a failure")
        if self.outcome != "succeeded" and type(self.failure) is not AdapterFailure:
            raise DeepContractError("non-success result requires a closed AdapterFailure")

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "action_id": self.action_id,
                "attempt_id": self.attempt_id, "instance_id": self.instance_id,
                "adapter_id": self.adapter_id, "outcome": self.outcome,
                "observed_at": self.observed_at, "exit_code": self.exit_code,
                "failure": None if self.failure is None else self.failure.as_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "NormalizedResult":
        data = _exact(value, NormalizedResult._FIELDS, "normalized result")
        failure = data["failure"]
        data["failure"] = None if failure is None else AdapterFailure.from_dict(failure)
        return NormalizedResult(**data)


@dataclass(frozen=True)
class AdapterRecovery:
    run_id: str
    action_id: str
    attempt_id: str
    instance_id: str
    adapter_id: str
    recovery_ref: RecoveryRef
    state: str
    result: NormalizedResult | None
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "run_id", "action_id", "attempt_id", "instance_id", "adapter_id",
        "recovery_ref", "state", "result"})

    def __post_init__(self) -> None:
        for name in ("run_id", "action_id", "attempt_id", "instance_id", "adapter_id"):
            object.__setattr__(self, name, _closed_id(name, getattr(self, name)))
        if type(self.recovery_ref) is not RecoveryRef:
            raise DeepContractError("recovery_ref must be a RecoveryRef")
        if (self.recovery_ref.action_id != self.action_id
                or self.recovery_ref.adapter_id != self.adapter_id):
            raise DeepContractError("recovery_ref must bind the action and adapter")
        object.__setattr__(self, "state", _enum(
            "state", self.state, RECOVERY_STATES))
        if self.state == "running":
            if self.result is not None:
                raise DeepContractError("running recovery cannot claim a result")
            return
        if type(self.result) is not NormalizedResult:
            raise DeepContractError("terminal recovery requires a normalized result")
        for name in ("run_id", "action_id", "attempt_id", "instance_id", "adapter_id"):
            if getattr(self, name) != getattr(self.result, name):
                raise DeepContractError(f"recovered result {name} must match recovery")
        if self.result.outcome not in RECOVERY_OUTCOMES[self.state]:
            raise DeepContractError("recovery state contradicts its normalized result")

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "action_id": self.action_id,
                "attempt_id": self.attempt_id, "instance_id": self.instance_id,
                "adapter_id": self.adapter_id, "recovery_ref": self.recovery_ref.as_dict(),
                "state": self.state,
                "result": None if self.result is None else self.result.as_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "AdapterRecovery":
        data = _exact(value, AdapterRecovery._FIELDS, "adapter recovery")
        data["recovery_ref"] = RecoveryRef.from_dict(data["recovery_ref"])
        data["result"] = None if data["result"] is None else NormalizedResult.from_dict(
            data["result"])
        return AdapterRecovery(**data)
