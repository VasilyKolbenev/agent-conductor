"""Closed data contracts for explicitly opted-in bounded-run history.

RunStore checks these records with authorization_history on append and replay.
They confer no live grant or scheduler activation. Fresh provider/capability,
budget and project-owner checks still belong to the execution admission door.
Existing Confirm records and unmarked Policy runs keep their current meaning.
"""
from __future__ import annotations

from dataclasses import dataclass

from .authorization_terms import (
    AUTOMATION_CONTRACT, FAILURE_HANDLING, InitialInputBinding, InstructionBinding,
    NodeLimit, authorization_interval, closed_fields, exact_schema, initial_input_order,
    human_identity, instruction_order, optional_id, positive_integer, rows,
)
from .contract_values import ContractError, _content_digest, _digest, _id, _timestamp


@dataclass(frozen=True)
class RunAuthorization:
    authorization_id: str
    run_id: str
    config_digest: str
    graph_digest: str
    provider_config_digest: str
    source_prefix_digest: str
    authorized_by: str
    authorized_at: str
    expires_at: str
    supersedes: str | None
    node_limits: tuple[NodeLimit, ...]
    instruction_bindings: tuple[InstructionBinding, ...]
    initial_input_bindings: tuple[InitialInputBinding, ...]
    max_actions: int
    max_action_seconds: int
    max_total_task_seconds: int
    contract: str = AUTOMATION_CONTRACT
    concurrency: int = 1
    failure_handling: str = FAILURE_HANDLING
    schema_version: int = 2
    authorization_digest: str = ""

    _FIELDS = frozenset({"schema_version", "authorization_id", "run_id", "contract",
        "config_digest", "graph_digest", "provider_config_digest", "source_prefix_digest",
        "authorized_by", "authorized_at", "expires_at", "supersedes", "node_limits",
        "instruction_bindings", "initial_input_bindings", "max_actions", "max_action_seconds",
        "max_total_task_seconds", "concurrency", "failure_handling", "authorization_digest"})

    def __post_init__(self):
        exact_schema(self.schema_version)
        for name in ("authorization_id", "run_id"):
            _id(name, getattr(self, name))
        for name in ("config_digest", "graph_digest", "provider_config_digest", "source_prefix_digest"):
            _digest(name, getattr(self, name))
        human_identity("authorized_by", self.authorized_by)
        authorization_interval(self.authorized_at, self.expires_at)
        optional_id("supersedes", self.supersedes)
        if self.supersedes == self.authorization_id:
            raise ContractError("an authorization cannot supersede itself")
        if type(self.contract) is not str or self.contract != AUTOMATION_CONTRACT:
            raise ContractError("unknown automation contract")
        if type(self.concurrency) is not int or self.concurrency != 1:
            raise ContractError("bounded authorization requires concurrency 1")
        if type(self.failure_handling) is not str or self.failure_handling != FAILURE_HANDLING:
            raise ContractError("bounded authorization requires explicit failure routes")
        for name in ("max_actions", "max_action_seconds", "max_total_task_seconds"):
            positive_integer(name, getattr(self, name))
        self._copy_bindings()
        computed = _content_digest(self._terms())
        if self.authorization_digest != "":
            _digest("authorization_digest", self.authorization_digest)
            if self.authorization_digest != computed:
                raise ContractError("authorization digest does not match its terms")
        object.__setattr__(self, "authorization_digest", computed)

    def _copy_bindings(self):
        for name, row_type, key in (("node_limits", NodeLimit, "node_id"),
                ("instruction_bindings", InstructionBinding, "node_id"),
                ("initial_input_bindings", InitialInputBinding, "artifact_ref")):
            object.__setattr__(self, name, rows(getattr(self, name), row_type, key))
        instruction_order(self.node_limits, self.instruction_bindings)
        initial_input_order(self.initial_input_bindings)

    def _terms(self):
        out = {name: getattr(self, name) for name in self._FIELDS
               if name not in {"authorization_digest", "node_limits", "instruction_bindings",
                               "initial_input_bindings"}}
        out.update(node_limits=[row.as_dict() for row in self.node_limits],
            instruction_bindings=[row.as_dict() for row in self.instruction_bindings],
            initial_input_bindings=[row.as_dict() for row in self.initial_input_bindings])
        return out

    def as_dict(self):
        return {**self._terms(), "authorization_digest": self.authorization_digest}

    @classmethod
    def from_dict(cls, value):
        data = closed_fields(value, cls._FIELDS, "run authorization")
        # Constructor-only empty digest requests derivation. Persisted/wire data
        # must carry the actual digest, never an empty value that is filled in.
        _digest("authorization_digest", data["authorization_digest"])
        return cls(**data)


@dataclass(frozen=True)
class RunAuthorizationControl:
    control_id: str
    run_id: str
    authorization_id: str
    authorization_digest: str
    action: str
    actor: str
    recorded_at: str
    expected_control_id: str | None
    schema_version: int = 2

    _FIELDS = frozenset({"schema_version", "control_id", "run_id", "authorization_id",
        "authorization_digest", "action", "actor", "recorded_at", "expected_control_id"})

    def __post_init__(self):
        exact_schema(self.schema_version)
        for name in ("control_id", "run_id", "authorization_id"):
            _id(name, getattr(self, name))
        _digest("authorization_digest", self.authorization_digest)
        human_identity("actor", self.actor)
        _timestamp("recorded_at", self.recorded_at)
        optional_id("expected_control_id", self.expected_control_id)
        if self.expected_control_id == self.control_id:
            raise ContractError("a control cannot name itself as its predecessor")
        if type(self.action) is not str or self.action not in {"pause", "resume", "revoke"}:
            raise ContractError("unknown bounded authorization control")

    def as_dict(self):
        return {name: getattr(self, name) for name in self._FIELDS}

    @classmethod
    def from_dict(cls, value):
        return cls(**closed_fields(value, cls._FIELDS, "run authorization control"))
