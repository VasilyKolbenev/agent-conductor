"""Structured evidence values for future deep adapters; never raw output."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .deep_contracts import (
    DeepContractError,
    _closed_digest,
    _closed_id,
    _closed_timestamp,
    _enum,
    _exact,
)


EVIDENCE_KINDS = frozenset({"result", "diff", "tests", "status"})
EVIDENCE_VERIFICATIONS = frozenset({
    "verified", "unavailable", "mismatch", "error"})


@dataclass(frozen=True)
class AdapterEvidence:
    evidence_id: str
    run_id: str
    action_id: str
    attempt_id: str
    instance_id: str
    adapter_id: str
    kind: str
    artifact_ref: str
    digest: str
    observed_at: str
    verification: str
    verified_at: str | None
    _FIELDS: ClassVar[frozenset[str]] = frozenset({
        "evidence_id", "run_id", "action_id", "attempt_id", "instance_id",
        "adapter_id", "kind", "artifact_ref", "digest", "observed_at", "verification",
        "verified_at"})

    def __post_init__(self) -> None:
        for name in (
                "evidence_id", "run_id", "action_id", "attempt_id", "instance_id",
                "adapter_id", "artifact_ref"):
            object.__setattr__(self, name, _closed_id(name, getattr(self, name)))
        object.__setattr__(self, "kind", _enum(
            "kind", self.kind, EVIDENCE_KINDS))
        object.__setattr__(
            self, "digest", _closed_digest("evidence digest", self.digest))
        object.__setattr__(
            self, "observed_at", _closed_timestamp("observed_at", self.observed_at))
        object.__setattr__(self, "verification", _enum(
            "verification", self.verification, EVIDENCE_VERIFICATIONS))
        if self.verification == "verified":
            object.__setattr__(self, "verified_at", _closed_timestamp(
                "verified_at", self.verified_at))
        elif self.verified_at is not None:
            raise DeepContractError("only verified evidence may carry verified_at")

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in sorted(self._FIELDS)}

    @classmethod
    def from_dict(cls, value: object) -> "AdapterEvidence":
        return AdapterEvidence(**_exact(
            value, AdapterEvidence._FIELDS, "adapter evidence"))
