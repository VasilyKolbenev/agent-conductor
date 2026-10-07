"""Immutable proposal content and optional correction data binding."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from .contract_values import (ABSENT, ContractError, _id, _object, _scope, _timestamp,
    _text, _digest, _schema, _extra, _content_digest, _DIGEST_RE, _thaw_json,
    _raw, _take, _bound_id, _unique_ids)

PROPOSAL_INPUT_BINDING = "proposal-v1"


@dataclass(frozen=True)
class ActionProposal:
    """One proposed action; it executes nothing and prepares nothing.

    A Proposal is upstream of an ActionRequest: it records what a lane would
    like to do and why, bound to the frozen configuration of its Run. Its
    preview_digest is derived from the whole canonical content except the digest
    itself, so editing any significant field invalidates it.
    """

    proposal_id: str
    run_id: str
    attempt_id: str
    instance_id: str
    capability: str
    arguments: Mapping[str, Any]
    scope: tuple[str, ...]
    proposed_by: str
    proposed_at: str
    timeout_seconds: int
    rationale: str
    config_digest: str
    preview_digest: str = ""
    #: The graph node this action carries out, when the run follows a graph.
    #: Absent for a run that has none, and for every action written before
    #: graphs existed -- which is why it is optional rather than a second
    #: spelling of "unknown".
    node_id: str | None = None
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)
    #: Omitted historical proposals retain their original bytes and semantics.
    #: A present marker binds material at proposal time and participates in its digest.
    input_binding: str | object = ABSENT
    feedback_ids: object = ABSENT

    _FIELDS = frozenset({
        "schema_version", "proposal_id", "run_id", "attempt_id", "instance_id",
        "capability", "arguments", "scope", "proposed_by", "proposed_at",
        "timeout_seconds", "rationale", "config_digest", "preview_digest",
        "node_id", "input_binding", "feedback_ids",
    })

    def __post_init__(self) -> None:
        for name in ("proposal_id", "run_id", "attempt_id", "instance_id",
                     "capability", "proposed_by"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "arguments", _object("arguments", self.arguments))
        object.__setattr__(self, "scope", _scope(self.scope))
        object.__setattr__(self, "proposed_at", _timestamp("proposed_at", self.proposed_at))
        if (isinstance(self.timeout_seconds, bool)
                or not isinstance(self.timeout_seconds, int)
                or not 1 <= self.timeout_seconds <= 86400):
            raise ContractError("timeout_seconds must be an integer from 1 through 86400")
        object.__setattr__(self, "rationale", _text("rationale", self.rationale))
        object.__setattr__(self, "config_digest", _digest("config_digest", self.config_digest))
        if self.node_id is not None:
            object.__setattr__(self, "node_id", _id("node_id", self.node_id))
        if self.input_binding is not ABSENT and (
                type(self.input_binding) is not str
                or self.input_binding != PROPOSAL_INPUT_BINDING):
            raise ContractError("input_binding must be proposal-v1 when present")
        if self.feedback_ids is not ABSENT:
            ids = _unique_ids("feedback_ids", self.feedback_ids)
            if not 1 <= len(ids) <= 16:
                raise ContractError("feedback_ids must contain 1 to 16 distinct references")
            object.__setattr__(self, "feedback_ids", ids)
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))
        computed = _content_digest(self._body())
        provided = self.preview_digest
        if provided:
            if not isinstance(provided, str) or _DIGEST_RE.fullmatch(provided) is None:
                raise ContractError(
                    "preview_digest must be sha256 followed by 64 lowercase hex digits")
            if provided != computed:
                raise ContractError("preview_digest does not match the proposal content")
        object.__setattr__(self, "preview_digest", computed)

    def _body(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "proposal_id": self.proposal_id,
            "run_id": self.run_id, "attempt_id": self.attempt_id,
            "instance_id": self.instance_id, "capability": self.capability,
            "arguments": _thaw_json(self.arguments), "scope": list(self.scope),
            "proposed_by": self.proposed_by, "proposed_at": self.proposed_at,
            "timeout_seconds": self.timeout_seconds, "rationale": self.rationale,
            "config_digest": self.config_digest,
        })
        # Only a real binding is written, so a proposal that names no node
        # digests exactly as it always did and no frozen example moves.
        if self.node_id is not None:
            out["node_id"] = self.node_id
        if self.input_binding is not ABSENT:
            out["input_binding"] = self.input_binding
        if self.feedback_ids is not ABSENT:
            out["feedback_ids"] = list(self.feedback_ids)
        return out

    def as_dict(self) -> dict[str, Any]:
        out = self._body()
        out["preview_digest"] = self.preview_digest
        return out

    @classmethod
    def from_dict(cls, value: object) -> "ActionProposal":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        required = {name: _take(known, name) for name in cls._FIELDS
                    if name not in (
                        "schema_version", "preview_digest", "node_id", "input_binding", "feedback_ids")}
        return cls(
            **required, preview_digest=known.pop("preview_digest", ""),
            node_id=_bound_id("node_id", known.pop("node_id", ABSENT)),
            input_binding=known.pop("input_binding", ABSENT),
            feedback_ids=known.pop("feedback_ids", ABSENT),
            schema_version=known.pop("schema_version", 2), extra=data)
