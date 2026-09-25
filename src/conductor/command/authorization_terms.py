"""Pure bounded-run terms. These values confer no execution or write authority.

The frozen graph determines node order and legal capabilities later, at the
preview/replay relation. This module validates closed values without consulting
today's graph, clock, provider configuration or owner handle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .contract_values import ContractError, _digest, _id, _text, _timestamp


AUTOMATION_CONTRACT = "bounded-run-v1"
FAILURE_HANDLING = "explicit-failure-route-only"
MAX_AUTHORIZATION_SECONDS = 24 * 60 * 60


def closed_fields(value, fields, name):
    if type(value) is not dict or set(value) != fields or any(type(key) is not str for key in value):
        raise ContractError(f"{name} requires exactly its declared fields")
    return dict(value)


def positive_integer(name, value):
    if type(value) is not int or value < 1:
        raise ContractError(f"{name} must be a positive integer")
    return value


def exact_schema(value):
    if type(value) is not int or value != 2:
        raise ContractError("bounded authorization requires schema_version 2")


def optional_id(name, value):
    return None if value is None else _id(name, value)


def human_identity(name, value):
    _text(name, value)
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ContractError(f"{name} must be valid UTF-8 text") from None
    return value


def _time_parts(name, value):
    _timestamp(name, value)
    whole = datetime.fromisoformat(value[:19])
    remainder = value[19:].removesuffix("Z").removesuffix("+00:00")
    # Comparing normalized decimal fractions as strings is exact even beyond
    # datetime's microsecond precision. No clock or float rounding is involved.
    fraction = remainder.removeprefix(".").rstrip("0")
    return whole, fraction


def authorization_interval(start, end):
    first, first_fraction = _time_parts("authorized_at", start)
    last, last_fraction = _time_parts("expires_at", end)
    seconds = (last - first).total_seconds()
    if seconds < 0 or seconds == 0 and last_fraction <= first_fraction:
        raise ContractError("authorization expiry must be strictly later")
    if seconds > MAX_AUTHORIZATION_SECONDS or (seconds == MAX_AUTHORIZATION_SECONDS
            and last_fraction > first_fraction):
        raise ContractError("authorization expiry exceeds 24 hours")


@dataclass(frozen=True)
class NodeLimit:
    node_id: str
    timeout_seconds: int
    max_attempts: int

    _FIELDS = frozenset({"node_id", "timeout_seconds", "max_attempts"})

    def __post_init__(self):
        _id("node_id", self.node_id)
        positive_integer("timeout_seconds", self.timeout_seconds)
        positive_integer("max_attempts", self.max_attempts)

    def as_dict(self):
        return {"node_id": self.node_id, "timeout_seconds": self.timeout_seconds,
                "max_attempts": self.max_attempts}

    @classmethod
    def from_dict(cls, value):
        return cls(**closed_fields(value, cls._FIELDS, "node limit"))


@dataclass(frozen=True)
class InstructionBinding:
    node_id: str
    artifact_id: str
    content_digest: str

    _FIELDS = frozenset({"node_id", "artifact_id", "content_digest"})

    def __post_init__(self):
        _id("node_id", self.node_id)
        _id("artifact_id", self.artifact_id)
        _digest("content_digest", self.content_digest)

    def as_dict(self):
        return {"node_id": self.node_id, "artifact_id": self.artifact_id,
                "content_digest": self.content_digest}

    @classmethod
    def from_dict(cls, value):
        return cls(**closed_fields(value, cls._FIELDS, "instruction binding"))


@dataclass(frozen=True)
class InitialInputBinding:
    artifact_ref: str
    artifact_id: str
    content_digest: str

    _FIELDS = frozenset({"artifact_ref", "artifact_id", "content_digest"})

    def __post_init__(self):
        _id("artifact_ref", self.artifact_ref)
        _id("artifact_id", self.artifact_id)
        _digest("content_digest", self.content_digest)

    def as_dict(self):
        return {"artifact_ref": self.artifact_ref, "artifact_id": self.artifact_id,
                "content_digest": self.content_digest}

    @classmethod
    def from_dict(cls, value):
        return cls(**closed_fields(value, cls._FIELDS, "initial input binding"))


def rows(value, row_type, key):
    """Detach mutable inputs and re-prove even a tampered frozen nested value."""
    if type(value) not in (list, tuple):
        raise ContractError("authorization rows must be an array")
    result = []
    for row in value:
        if type(row) is row_type:
            row = row.as_dict()
        result.append(row_type.from_dict(row))
    names = [getattr(row, key) for row in result]
    if len(names) != len(set(names)):
        raise ContractError("authorization rows must have unique identities")
    return tuple(result)


def instruction_order(node_limits, instruction_bindings):
    names = [row.node_id for row in node_limits]
    instructions = [row.node_id for row in instruction_bindings]
    if instructions != [name for name in names if name in set(instructions)]:
        raise ContractError("instruction bindings must follow authorized node order")


def initial_input_order(initial_input_bindings):
    names = [row.artifact_ref for row in initial_input_bindings]
    if names != sorted(names):
        raise ContractError("initial input bindings must use canonical reference order")
