"""Value-only causal attempt facts for December Command v2.

Attempt events describe durable lease and observed boundaries.  They grant no
authority, touch no store, and infer no success from time or mere presence.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .contracts import (
    ActionRequest,
    ContractError,
    _digest,
    _id,
    _timestamp,
    canonical_json,
)


ATTEMPT_PHASES = frozenset({"effect_lease", "execution_observed"})
OBSERVED_OUTCOMES = frozenset({
    "succeeded", "failed", "cancelled", "rejected", "unknown",
})


def action_request_digest(request: ActionRequest) -> str:
    """Digest every canonical ActionRequest field, including future extras."""
    if not isinstance(request, ActionRequest):
        raise ContractError("action_request_digest requires a validated ActionRequest")
    payload = canonical_json(request.as_dict()).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class AttemptEvent:
    """One strict durable boundary for an authorized action attempt."""

    event_id: str
    run_id: str
    action_id: str
    attempt_id: str
    instance_id: str
    adapter_id: str
    phase: str
    recorded_at: str
    request_digest: str
    recovery_ref: str
    outcome: str | None
    exit_code: int | None
    schema_version: int

    _FIELDS = frozenset({
        "event_id", "run_id", "action_id", "attempt_id", "instance_id",
        "adapter_id", "phase", "recorded_at", "request_digest", "recovery_ref",
        "outcome", "exit_code", "schema_version",
    })

    def __post_init__(self) -> None:
        for name in (
                "event_id", "run_id", "action_id", "attempt_id", "instance_id",
                "adapter_id", "recovery_ref"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        if not isinstance(self.phase, str) or self.phase not in ATTEMPT_PHASES:
            raise ContractError(
                f"phase must be one of {sorted(ATTEMPT_PHASES)}, got {self.phase!r}")
        object.__setattr__(self, "recorded_at", _timestamp("recorded_at", self.recorded_at))
        object.__setattr__(
            self, "request_digest", _digest("request_digest", self.request_digest))
        if self.exit_code is not None and (
                isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)):
            raise ContractError("exit_code must be an integer or null")
        if self.phase == "effect_lease":
            if self.outcome is not None or self.exit_code is not None:
                raise ContractError("an effect_lease event must have null outcome and exit_code")
        elif not isinstance(self.outcome, str) or self.outcome not in OBSERVED_OUTCOMES:
            raise ContractError(
                "an observed event outcome must be succeeded, failed, cancelled, "
                "rejected, or unknown")
        elif self.outcome == "succeeded" and self.exit_code not in (None, 0):
            raise ContractError("a succeeded observed event exit_code must be zero or null")
        elif self.outcome == "failed" and self.exit_code == 0:
            raise ContractError("a failed observed event exit_code must be nonzero or null")
        elif self.outcome in {"cancelled", "rejected", "unknown"}:
            if self.exit_code is not None:
                raise ContractError(
                    f"a {self.outcome} observed event exit_code must be null")
        if isinstance(self.schema_version, bool) or self.schema_version != 2:
            raise ContractError("AttemptEvent schema_version must be exactly 2")

    def as_dict(self) -> dict[str, Any]:
        """Return exactly the thirteen contracted fields, including nulls."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "action_id": self.action_id,
            "attempt_id": self.attempt_id,
            "instance_id": self.instance_id,
            "adapter_id": self.adapter_id,
            "phase": self.phase,
            "recorded_at": self.recorded_at,
            "request_digest": self.request_digest,
            "recovery_ref": self.recovery_ref,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AttemptEvent":
        """Reconstruct only an exact thirteen-field AttemptEvent object."""
        if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
            raise ContractError("attempt event must be a JSON object with string keys")
        supplied = set(value)
        missing = sorted(cls._FIELDS - supplied)
        extra = sorted(supplied - cls._FIELDS)
        if missing or extra:
            raise ContractError(
                f"attempt event fields must be exact; missing={missing}, extra={extra}")
        return cls(**{name: value[name] for name in cls._FIELDS})
