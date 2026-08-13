"""Immutable, value-only contracts shared by future deep adapters.

Nothing here probes an executable, reads an environment value, starts a process,
or claims a real Claude/Codex integration.  The only protocols are deterministic
fake protocols; real modes remain explicitly unavailable until separately proven.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, ClassVar

from ..contracts import ContractError, _digest, _id, _timestamp


class DeepContractError(ContractError):
    """A deep-adapter value is open-ended, secret-bearing, or contradictory."""


class DeepProtocol(str, Enum):
    FAKE_CLAUDE_V1 = "fake-claude-jsonl-v1"
    FAKE_CODEX_V1 = "fake-codex-jsonl-v1"


_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_OBSERVED = frozenset({"succeeded", "failed", "cancelled", "rejected", "unknown"})
_FAILURE_CODES = frozenset({
    "invalid_arguments", "executable_unavailable", "spawn_refused", "timeout",
    "stopped", "protocol_error", "output_limit", "lost_result",
    "recovery_unavailable", "identity_mismatch", "evidence_unavailable",
    "evidence_mismatch", "ownership_lost", "unsupported",
})
_FAILURE_PHASES = frozenset({
    "prepare", "execute", "observe", "verify", "recover", "stop",
})


def _exact(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise DeepContractError(f"{name} must be an object with string keys")
    missing, extra = sorted(fields - set(value)), sorted(set(value) - fields)
    if missing or extra:
        raise DeepContractError(f"{name} fields must be exact; missing={missing}, extra={extra}")
    return dict(value)


def _enum(name: str, value: object, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise DeepContractError(f"{name} must be one of {sorted(allowed)}")
    return value


def _ids(name: str, value: object, *, empty: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DeepContractError(f"{name} must be a list of ids")
    rows = tuple(_id(name, item) for item in value)
    if not empty and not rows:
        raise DeepContractError(f"{name} must not be empty")
    if len(rows) != len(set(rows)):
        raise DeepContractError(f"{name} must not repeat an id")
    return rows


def _exit_relation(outcome: str, exit_code: object) -> int | None:
    if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
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
        if not isinstance(self.executable, str) or "\x00" in self.executable:
            raise DeepContractError("executable must be a NUL-free absolute path string")
        if not (PurePosixPath(self.executable).is_absolute()
                or PureWindowsPath(self.executable).is_absolute()):
            raise DeepContractError("executable must be an absolute configured path")
        try:
            protocol = (self.protocol if isinstance(self.protocol, DeepProtocol)
                        else DeepProtocol(self.protocol))
        except (TypeError, ValueError):
            raise DeepContractError("protocol must name one reviewed fake protocol") from None
        if isinstance(self.env_allow, (str, bytes)) or not isinstance(
                self.env_allow, (list, tuple)):
            raise DeepContractError("env_allow must contain unique environment names")
        names = tuple(self.env_allow)
        if (any(not isinstance(row, str) or _ENV_NAME.fullmatch(row) is None
                for row in names) or len(names) != len(set(names))):
            raise DeepContractError("env_allow must contain unique environment names")
        if self.real_mode != "unavailable":
            raise DeepContractError("real_mode remains 'unavailable' until opt-in proof lands")
        object.__setattr__(self, "protocol", protocol)
        object.__setattr__(self, "env_allow", names)

    def as_dict(self) -> dict[str, Any]:
        return {"executable": self.executable, "protocol": self.protocol.value,
                "env_allow": list(self.env_allow), "real_mode": self.real_mode}

    @classmethod
    def from_dict(cls, value: object) -> "DeepAdapterConfig":
        return cls(**_exact(value, cls._FIELDS, "deep adapter config"))


@dataclass(frozen=True)
class RecoveryRef:
    scheme: str
    adapter_id: str
    action_id: str
    digest: str
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "scheme", "adapter_id", "action_id", "digest"})

    def __post_init__(self) -> None:
        if self.scheme != "fake-ledger-v1":
            raise DeepContractError("recovery scheme must be 'fake-ledger-v1'")
        object.__setattr__(self, "adapter_id", _id("adapter_id", self.adapter_id))
        object.__setattr__(self, "action_id", _id("action_id", self.action_id))
        object.__setattr__(self, "digest", _digest("recovery digest", self.digest))

    def as_dict(self) -> dict[str, str]:
        return {"scheme": self.scheme, "adapter_id": self.adapter_id,
                "action_id": self.action_id, "digest": self.digest}

    @classmethod
    def from_dict(cls, value: object) -> "RecoveryRef":
        return cls(**_exact(value, cls._FIELDS, "recovery ref"))


@dataclass(frozen=True)
class AdapterFailure:
    code: str
    phase: str
    retryable: bool
    _FIELDS: ClassVar[frozenset[str]] = frozenset({"code", "phase", "retryable"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _enum("code", self.code, _FAILURE_CODES))
        object.__setattr__(self, "phase", _enum("phase", self.phase, _FAILURE_PHASES))
        if not isinstance(self.retryable, bool):
            raise DeepContractError("retryable must be a boolean")

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "phase": self.phase, "retryable": self.retryable}

    @classmethod
    def from_dict(cls, value: object) -> "AdapterFailure":
        return cls(**_exact(value, cls._FIELDS, "adapter failure"))


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
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "outcome", _enum("outcome", self.outcome, _OBSERVED))
        object.__setattr__(self, "observed_at", _timestamp("observed_at", self.observed_at))
        object.__setattr__(self, "exit_code", _exit_relation(self.outcome, self.exit_code))
        if self.outcome == "succeeded" and self.failure is not None:
            raise DeepContractError("succeeded result cannot carry a failure")
        if self.outcome != "succeeded" and not isinstance(self.failure, AdapterFailure):
            raise DeepContractError("non-success result requires a closed AdapterFailure")

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "action_id": self.action_id,
                "attempt_id": self.attempt_id, "instance_id": self.instance_id,
                "adapter_id": self.adapter_id, "outcome": self.outcome,
                "observed_at": self.observed_at, "exit_code": self.exit_code,
                "failure": None if self.failure is None else self.failure.as_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "NormalizedResult":
        data = _exact(value, cls._FIELDS, "normalized result")
        failure = data["failure"]
        data["failure"] = None if failure is None else AdapterFailure.from_dict(failure)
        return cls(**data)


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
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        if not isinstance(self.recovery_ref, RecoveryRef):
            raise DeepContractError("recovery_ref must be a RecoveryRef")
        if (self.recovery_ref.action_id != self.action_id
                or self.recovery_ref.adapter_id != self.adapter_id):
            raise DeepContractError("recovery_ref must bind the action and adapter")
        object.__setattr__(self, "state", _enum(
            "state", self.state,
            frozenset({"running", "succeeded", "failed", "cancelled", "unknown"})))
        expected = {
            "succeeded": frozenset({"succeeded"}),
            "failed": frozenset({"failed", "rejected"}),
            "cancelled": frozenset({"cancelled"}),
            "unknown": frozenset({"unknown"}),
        }
        if self.state == "running":
            if self.result is not None:
                raise DeepContractError("running recovery cannot claim a result")
            return
        if not isinstance(self.result, NormalizedResult):
            raise DeepContractError("terminal recovery requires a normalized result")
        for name in ("run_id", "action_id", "attempt_id", "instance_id", "adapter_id"):
            if getattr(self, name) != getattr(self.result, name):
                raise DeepContractError(f"recovered result {name} must match recovery")
        if self.result.outcome not in expected[self.state]:
            raise DeepContractError("recovery state contradicts its normalized result")

    def as_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "action_id": self.action_id,
                "attempt_id": self.attempt_id, "instance_id": self.instance_id,
                "adapter_id": self.adapter_id, "recovery_ref": self.recovery_ref.as_dict(),
                "state": self.state,
                "result": None if self.result is None else self.result.as_dict()}

    @classmethod
    def from_dict(cls, value: object) -> "AdapterRecovery":
        data = _exact(value, cls._FIELDS, "adapter recovery")
        data["recovery_ref"] = RecoveryRef.from_dict(data["recovery_ref"])
        data["result"] = None if data["result"] is None else NormalizedResult.from_dict(
            data["result"])
        return cls(**data)
