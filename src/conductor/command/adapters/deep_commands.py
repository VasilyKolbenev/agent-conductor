"""Closed deep-adapter arguments and code-owned process specifications."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from ..contracts import _id
from .deep_contracts import (
    DeepAdapterConfig,
    DeepContractError,
    _enum,
    _exact,
    _ids,
)


class _StrictArguments:
    _FIELDS: ClassVar[frozenset[str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            name: list(value) if isinstance(value, tuple) else value
            for name in self._FIELDS if (value := getattr(self, name)) is not None
        }

    @classmethod
    def from_dict(cls, value: object):
        return cls(**_exact(value, cls._FIELDS, cls.__name__))


@dataclass(frozen=True)
class DeepDispatchArgs(_StrictArguments):
    work_item_id: str
    instruction_ref: str
    profile: str
    artifact_refs: tuple[str, ...] | list[str]
    output_limit_profile: str
    _FIELDS = frozenset({
        "work_item_id", "instruction_ref", "profile", "artifact_refs",
        "output_limit_profile"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_item_id", _id("work_item_id", self.work_item_id))
        object.__setattr__(self, "instruction_ref", _id(
            "instruction_ref", self.instruction_ref))
        object.__setattr__(self, "profile", _enum(
            "profile", self.profile, frozenset({"implement", "review"})))
        object.__setattr__(self, "artifact_refs", _ids(
            "artifact_refs", self.artifact_refs, empty=True))
        object.__setattr__(self, "output_limit_profile", _enum(
            "output_limit_profile", self.output_limit_profile,
            frozenset({"small", "normal"})))


@dataclass(frozen=True)
class DeepReviewArgs(_StrictArguments):
    work_item_id: str
    target_artifact_refs: tuple[str, ...] | list[str]
    review_profile: str
    _FIELDS = frozenset({"work_item_id", "target_artifact_refs", "review_profile"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_item_id", _id("work_item_id", self.work_item_id))
        object.__setattr__(self, "target_artifact_refs", _ids(
            "target_artifact_refs", self.target_artifact_refs))
        object.__setattr__(self, "review_profile", _enum(
            "review_profile", self.review_profile,
            frozenset({"quality", "security", "spec"})))


@dataclass(frozen=True)
class DeepEvidenceArgs(_StrictArguments):
    target_action_id: str
    kinds: tuple[str, ...] | list[str]
    _FIELDS = frozenset({"target_action_id", "kinds"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_action_id", _id(
            "target_action_id", self.target_action_id))
        if isinstance(self.kinds, (str, bytes)) or not isinstance(self.kinds, (list, tuple)):
            raise DeepContractError("kinds must be a list")
        kinds = tuple(self.kinds)
        allowed = frozenset({"result", "diff", "tests", "status"})
        if not kinds or any(not isinstance(row, str) or row not in allowed for row in kinds):
            raise DeepContractError("kinds contains an unsupported evidence kind")
        if len(kinds) != len(set(kinds)):
            raise DeepContractError("kinds must not repeat a value")
        object.__setattr__(self, "kinds", kinds)


@dataclass(frozen=True)
class DeepStopArgs(_StrictArguments):
    target_attempt_id: str
    reason: str
    _FIELDS = frozenset({"target_attempt_id", "reason"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_attempt_id", _id(
            "target_attempt_id", self.target_attempt_id))
        object.__setattr__(self, "reason", _enum(
            "reason", self.reason, frozenset({"user", "timeout", "switch"})))


@dataclass(frozen=True)
class DeepRetryArgs(_StrictArguments):
    prior_action_id: str
    reason: str
    _FIELDS = frozenset({"prior_action_id", "reason"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "prior_action_id", _id(
            "prior_action_id", self.prior_action_id))
        object.__setattr__(self, "reason", _enum(
            "reason", self.reason,
            frozenset({"failed", "unknown", "verification_failed", "user"})))


@dataclass(frozen=True)
class DeepSwitchArgs(_StrictArguments):
    prior_action_id: str
    target_instance_id: str
    handoff_ref: str
    _FIELDS = frozenset({"prior_action_id", "target_instance_id", "handoff_ref"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "prior_action_id", _id(
            "prior_action_id", self.prior_action_id))
        object.__setattr__(self, "target_instance_id", _id(
            "target_instance_id", self.target_instance_id))
        object.__setattr__(self, "handoff_ref", _id("handoff_ref", self.handoff_ref))


_SPEC_AUTHORITY = object()
_PROTOCOL_FLAG = {
    "fake-claude-jsonl-v1": "--fake-claude-jsonl-v1",
    "fake-codex-jsonl-v1": "--fake-codex-jsonl-v1",
}


@dataclass(frozen=True, init=False)
class DeepCommandSpec:
    """An invocation assembled by code; no caller command/path suffix exists."""

    argv: tuple[str, ...]
    cwd: str
    env_allow: tuple[str, ...]
    output_profile: str
    timeout_seconds: int

    def __init__(
            self, argv: tuple[str, ...], cwd: str, env_allow: tuple[str, ...],
            output_profile: str, timeout_seconds: int, *, _authority=None) -> None:
        if _authority is not _SPEC_AUTHORITY:
            raise DeepContractError("DeepCommandSpec is code-owned; use from_config")
        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "env_allow", env_allow)
        object.__setattr__(self, "output_profile", output_profile)
        object.__setattr__(self, "timeout_seconds", timeout_seconds)

    @classmethod
    def from_config(
            cls, config: DeepAdapterConfig, *, timeout_seconds: int) -> "DeepCommandSpec":
        if not isinstance(config, DeepAdapterConfig):
            raise DeepContractError("from_config requires a DeepAdapterConfig")
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int)
                or timeout_seconds < 1):
            raise DeepContractError("timeout_seconds must be a positive integer")
        return cls(
            (config.executable, _PROTOCOL_FLAG[config.protocol.value]), ".",
            config.env_allow, "bounded-jsonl-v1", timeout_seconds,
            _authority=_SPEC_AUTHORITY)
