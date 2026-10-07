"""Validated, canonical envelopes at the December Command write boundary.

This module deliberately has no filesystem, subprocess, server, or adapter
imports. It defines the facts those layers must carry before any writable
surface is allowed to exist.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


from .contract_values import (  # noqa: F401 -- re-exported under
    # their original names, so every existing import keeps working.
    ABSENT,
    ContractError,
    ControlMode,
    HEALTH_STATES,
    _DECISION_ACTIONS,
    _DIGEST_RE,
    _ID_RE,
    _RESULT_OUTCOMES,
    _RUN_STATES,
    _UTC_INSTANT_RE,
    _VERIFICATION_STATES,
    _bound_id,
    _content_digest,
    _digest,
    _enum,
    _extra,
    _freeze_json,
    _id,
    _ids,
    _json_copy,
    _mode,
    _object,
    _raw,
    _schema,
    _scope,
    _take,
    _text,
    _thaw_json,
    _timestamp,
    _unique_ids,
    canonical_json,
)


@dataclass(frozen=True)
class RunEnvelope:
    """Immutable identity and frozen configuration for one Orbit execution."""

    run_id: str
    cycle_id: str
    created_at: str
    config_digest: str
    mode: ControlMode | str = ControlMode.OBSERVE
    status: str = "created"
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    _FIELDS = frozenset({
        "schema_version", "run_id", "cycle_id", "created_at", "config_digest",
        "mode", "status",
    })

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _id("run_id", self.run_id))
        object.__setattr__(self, "cycle_id", _id("cycle_id", self.cycle_id))
        object.__setattr__(self, "created_at", _timestamp("created_at", self.created_at))
        object.__setattr__(self, "config_digest", _digest("config_digest", self.config_digest))
        object.__setattr__(self, "mode", _mode(self.mode))
        object.__setattr__(self, "status", _enum("status", self.status, _RUN_STATES))
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))

    def as_dict(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "run_id": self.run_id,
            "cycle_id": self.cycle_id, "created_at": self.created_at,
            "config_digest": self.config_digest, "mode": self.mode.value,
            "status": self.status,
        })
        return out

    @classmethod
    def from_dict(cls, value: object) -> "RunEnvelope":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        return cls(
            run_id=_take(known, "run_id"), cycle_id=_take(known, "cycle_id"),
            created_at=_take(known, "created_at"),
            config_digest=_take(known, "config_digest"),
            mode=known.pop("mode", ControlMode.OBSERVE.value),
            status=known.pop("status", "created"),
            schema_version=known.pop("schema_version", 2), extra=data)


@dataclass(frozen=True)
class ActionRequest:
    """One prepared, scoped request; execution requires Confirm or Policy."""

    action_id: str
    run_id: str
    attempt_id: str
    instance_id: str
    capability: str
    arguments: Mapping[str, Any]
    scope: tuple[str, ...]
    requested_by: str
    requested_at: str
    idempotency_key: str
    timeout_seconds: int
    preview_digest: str
    mode: ControlMode | str
    #: The graph node this action carries out. It is copied from the STORED
    #: proposal at authorize time and never read from a Confirm body: what a
    #: Human confirmed is the proposal they were shown, binding included.
    node_id: str | None = None
    run_authorization_id: object = ABSENT
    run_authorization_digest: object = ABSENT
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    _FIELDS = frozenset({
        "schema_version", "action_id", "run_id", "attempt_id", "instance_id",
        "capability", "arguments", "scope", "requested_by", "requested_at",
        "idempotency_key", "timeout_seconds", "preview_digest", "mode",
        "node_id", "run_authorization_id", "run_authorization_digest",
    })

    def __post_init__(self) -> None:
        for name in ("action_id", "run_id", "attempt_id", "instance_id", "capability",
                     "requested_by", "idempotency_key"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "arguments", _object("arguments", self.arguments))
        object.__setattr__(self, "scope", _scope(self.scope))
        object.__setattr__(self, "requested_at", _timestamp("requested_at", self.requested_at))
        if (isinstance(self.timeout_seconds, bool)
                or not isinstance(self.timeout_seconds, int)
                or not 1 <= self.timeout_seconds <= 86400):
            raise ContractError("timeout_seconds must be an integer from 1 through 86400")
        object.__setattr__(self, "preview_digest", _digest("preview_digest", self.preview_digest))
        mode = _mode(self.mode)
        if mode not in {ControlMode.CONFIRM, ControlMode.POLICY}:
            raise ContractError("mode for an executable action must be confirm or policy")
        object.__setattr__(self, "mode", mode)
        if self.node_id is not None:
            object.__setattr__(self, "node_id", _id("node_id", self.node_id))
        self._hold_authorization_reference()
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))

    def _hold_authorization_reference(self):
        absent_id = self.run_authorization_id is ABSENT
        absent_digest = self.run_authorization_digest is ABSENT
        if absent_id != absent_digest:
            raise ContractError("run authorization ID and digest must appear together")
        if not absent_id:
            _id("run_authorization_id", self.run_authorization_id)
            _digest("run_authorization_digest", self.run_authorization_digest)
            if self.mode is not ControlMode.POLICY:
                raise ContractError("run authorization reference requires Policy mode")

    def as_dict(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "action_id": self.action_id,
            "run_id": self.run_id, "attempt_id": self.attempt_id,
            "instance_id": self.instance_id, "capability": self.capability,
            "arguments": _thaw_json(self.arguments), "scope": list(self.scope),
            "requested_by": self.requested_by, "requested_at": self.requested_at,
            "idempotency_key": self.idempotency_key,
            "timeout_seconds": self.timeout_seconds,
            "preview_digest": self.preview_digest, "mode": self.mode.value,
        })
        # Written only when this action carries out a node, so the request
        # digest -- which covers this whole document -- moves with the binding
        # and stands still without one.
        if self.node_id is not None:
            out["node_id"] = self.node_id
        if self.run_authorization_id is not ABSENT:
            out["run_authorization_id"] = self.run_authorization_id
            out["run_authorization_digest"] = self.run_authorization_digest
        return out

    @classmethod
    def from_dict(cls, value: object) -> "ActionRequest":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        required = {name: _take(known, name) for name in cls._FIELDS
                    if name not in ("schema_version", "node_id",
                        "run_authorization_id", "run_authorization_digest")}
        return cls(**required,
                   run_authorization_id=known.pop("run_authorization_id", ABSENT),
                   run_authorization_digest=known.pop("run_authorization_digest", ABSENT),
                   node_id=_bound_id("node_id", known.pop("node_id", ABSENT)),
                   schema_version=known.pop("schema_version", 2), extra=data)


from .action_proposal import ActionProposal, PROPOSAL_INPUT_BINDING  # noqa: F401
from .feedback_payload import (FeedbackPayloadError, settled_payload, settled_feedback_bytes,
    FEEDBACK_PROTOCOL, MAX_FINDINGS, MAX_PAYLOAD_BYTES, FINDING_KINDS)  # noqa: F401


@dataclass(frozen=True)
class ObservationRecord:
    """A durable, serializable observation an adapter reported for one Run.

    It is the write-boundary twin of the live AdapterObservation: absence and an
    unknown never become ready, and future fields survive a round trip so a newer
    writer never loses meaning through an older reader.
    """

    observation_id: str
    run_id: str
    adapter_id: str
    instance_id: str
    observed_at: str
    health: str
    available_capabilities: tuple[str, ...] = ()
    detail: str = ""
    evidence_refs: tuple[str, ...] = ()
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    _FIELDS = frozenset({
        "schema_version", "observation_id", "run_id", "adapter_id", "instance_id",
        "observed_at", "health", "available_capabilities", "detail", "evidence_refs",
    })

    def __post_init__(self) -> None:
        for name in ("observation_id", "run_id", "adapter_id", "instance_id"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "observed_at", _timestamp("observed_at", self.observed_at))
        object.__setattr__(self, "health", _enum("health", self.health, HEALTH_STATES))
        object.__setattr__(
            self, "available_capabilities",
            _unique_ids("available_capabilities", self.available_capabilities))
        object.__setattr__(self, "detail", _text("detail", self.detail, empty=True))
        object.__setattr__(
            self, "evidence_refs", _unique_ids("evidence_refs", self.evidence_refs))
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))

    def as_dict(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "observation_id": self.observation_id,
            "run_id": self.run_id, "adapter_id": self.adapter_id,
            "instance_id": self.instance_id, "observed_at": self.observed_at,
            "health": self.health,
            "available_capabilities": list(self.available_capabilities),
            "detail": self.detail, "evidence_refs": list(self.evidence_refs),
        })
        return out

    @classmethod
    def from_dict(cls, value: object) -> "ObservationRecord":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        return cls(
            observation_id=_take(known, "observation_id"), run_id=_take(known, "run_id"),
            adapter_id=_take(known, "adapter_id"), instance_id=_take(known, "instance_id"),
            observed_at=_take(known, "observed_at"), health=_take(known, "health"),
            available_capabilities=known.pop("available_capabilities", ()),
            detail=known.pop("detail", ""), evidence_refs=known.pop("evidence_refs", ()),
            schema_version=known.pop("schema_version", 2), extra=data)


@dataclass(frozen=True)
class ActionResultReceipt:
    """Observed result of an action, distinct from acceptance or process start."""

    receipt_id: str
    action_id: str
    run_id: str
    attempt_id: str
    instance_id: str
    outcome: str
    observed_at: str
    evidence_refs: tuple[str, ...] = ()
    detail: str | None = None
    exit_code: int | None = None
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    _FIELDS = frozenset({
        "schema_version", "receipt_id", "action_id", "run_id", "attempt_id",
        "instance_id", "outcome", "observed_at", "evidence_refs", "detail",
        "exit_code",
    })

    def __post_init__(self) -> None:
        for name in ("receipt_id", "action_id", "run_id", "attempt_id", "instance_id"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "outcome", _enum("outcome", self.outcome, _RESULT_OUTCOMES))
        object.__setattr__(self, "observed_at", _timestamp("observed_at", self.observed_at))
        object.__setattr__(self, "evidence_refs", _ids("evidence_refs", self.evidence_refs))
        if self.detail is not None:
            object.__setattr__(self, "detail", _text("detail", self.detail, empty=True))
        if self.exit_code is not None and (isinstance(self.exit_code, bool)
                                           or not isinstance(self.exit_code, int)):
            raise ContractError("exit_code must be an integer or null")
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))

    def as_dict(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "receipt_id": self.receipt_id,
            "action_id": self.action_id, "run_id": self.run_id,
            "attempt_id": self.attempt_id, "instance_id": self.instance_id,
            "outcome": self.outcome, "observed_at": self.observed_at,
            "evidence_refs": list(self.evidence_refs), "detail": self.detail,
            "exit_code": self.exit_code,
        })
        return out

    @classmethod
    def from_dict(cls, value: object) -> "ActionResultReceipt":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        return cls(
            receipt_id=_take(known, "receipt_id"),
            action_id=_take(known, "action_id"), run_id=_take(known, "run_id"),
            attempt_id=_take(known, "attempt_id"),
            instance_id=_take(known, "instance_id"),
            outcome=_take(known, "outcome"), observed_at=_take(known, "observed_at"),
            evidence_refs=known.pop("evidence_refs", ()),
            detail=known.pop("detail", None), exit_code=known.pop("exit_code", None),
            schema_version=known.pop("schema_version", 2), extra=data)


@dataclass(frozen=True)
class EvidenceRef:
    """An evidence claim whose verification state is never inferred."""

    evidence_id: str
    run_id: str
    kind: str
    uri: str
    label: str
    created_by: str
    observed_at: str
    digest: str | None = None
    verification: str = "unverified"
    verified_by: str | None = None
    verified_at: str | None = None
    verifier_instance_id: str | None = None
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    _FIELDS = frozenset({
        "schema_version", "evidence_id", "run_id", "kind", "uri", "label", "created_by",
        "observed_at", "digest", "verification", "verified_by", "verified_at",
        "verifier_instance_id",
    })

    def __post_init__(self) -> None:
        for name in ("evidence_id", "run_id", "kind", "created_by"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "uri", _text("uri", self.uri))
        object.__setattr__(self, "label", _text("label", self.label))
        object.__setattr__(self, "observed_at", _timestamp("observed_at", self.observed_at))
        if self.digest is not None:
            object.__setattr__(self, "digest", _digest("digest", self.digest))
        object.__setattr__(self, "verification",
                           _enum("verification", self.verification, _VERIFICATION_STATES))
        if self.verification == "unverified":
            if any(value is not None for value in (
                    self.verified_by, self.verified_at, self.verifier_instance_id)):
                raise ContractError("unverified evidence cannot name a verification signer")
        else:
            if self.verified_by is None:
                raise ContractError("verified_by is required for an observed verification result")
            if self.verified_at is None:
                raise ContractError("verified_at is required for an observed verification result")
            object.__setattr__(self, "verified_by", _id("verified_by", self.verified_by))
            object.__setattr__(self, "verified_at", _timestamp("verified_at", self.verified_at))
        if self.verifier_instance_id is not None:
            object.__setattr__(self, "verifier_instance_id",
                               _id("verifier_instance_id", self.verifier_instance_id))
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))

    def as_dict(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "evidence_id": self.evidence_id,
            "run_id": self.run_id, "kind": self.kind, "uri": self.uri, "label": self.label,
            "created_by": self.created_by, "observed_at": self.observed_at,
            "digest": self.digest, "verification": self.verification,
            "verified_by": self.verified_by, "verified_at": self.verified_at,
        })
        if self.verifier_instance_id is not None:
            out["verifier_instance_id"] = self.verifier_instance_id
        return out

    @classmethod
    def from_dict(cls, value: object) -> "EvidenceRef":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        return cls(
            evidence_id=_take(known, "evidence_id"), run_id=_take(known, "run_id"),
            kind=_take(known, "kind"),
            uri=_take(known, "uri"), label=_take(known, "label"),
            created_by=_take(known, "created_by"),
            observed_at=_take(known, "observed_at"),
            digest=known.pop("digest", None),
            verification=known.pop("verification", "unverified"),
            verified_by=known.pop("verified_by", None),
            verified_at=known.pop("verified_at", None),
            verifier_instance_id=_bound_id(
                "verifier_instance_id", known.pop("verifier_instance_id", ABSENT)),
            schema_version=known.pop("schema_version", 2), extra=data)


@dataclass(frozen=True)
class DecisionReceipt:
    """Immutable Human decision; correction is another superseding receipt."""

    receipt_id: str
    run_id: str
    gate_id: str
    action: str
    actor: str
    decided_at: str
    reason: str
    scope_refs: tuple[str, ...]
    config_digest: str
    evidence_refs: tuple[str, ...] = ()
    supersedes: str | None = None
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    _FIELDS = frozenset({
        "schema_version", "receipt_id", "run_id", "gate_id", "action", "actor",
        "decided_at", "reason", "scope_refs", "config_digest", "evidence_refs",
        "supersedes",
    })

    def __post_init__(self) -> None:
        for name in ("receipt_id", "run_id", "gate_id", "actor"):
            object.__setattr__(self, name, _id(name, getattr(self, name)))
        object.__setattr__(self, "action", _enum("action", self.action, _DECISION_ACTIONS))
        object.__setattr__(self, "decided_at", _timestamp("decided_at", self.decided_at))
        object.__setattr__(self, "reason", _text("reason", self.reason, empty=True))
        if self.action in {"request_changes", "waive"} and not self.reason.strip():
            raise ContractError(f"reason is required when action is {self.action}")
        object.__setattr__(self, "scope_refs", _ids("scope_refs", self.scope_refs))
        object.__setattr__(self, "config_digest", _digest("config_digest", self.config_digest))
        object.__setattr__(self, "evidence_refs", _ids("evidence_refs", self.evidence_refs))
        if self.supersedes is not None:
            object.__setattr__(self, "supersedes", _id("supersedes", self.supersedes))
            if self.supersedes == self.receipt_id:
                raise ContractError("supersedes must not reference the receipt itself")
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))

    def as_dict(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "receipt_id": self.receipt_id,
            "run_id": self.run_id, "gate_id": self.gate_id, "action": self.action,
            "actor": self.actor, "decided_at": self.decided_at, "reason": self.reason,
            "scope_refs": list(self.scope_refs), "config_digest": self.config_digest,
            "evidence_refs": list(self.evidence_refs), "supersedes": self.supersedes,
        })
        return out

    @classmethod
    def from_dict(cls, value: object) -> "DecisionReceipt":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        return cls(
            receipt_id=_take(known, "receipt_id"), run_id=_take(known, "run_id"),
            gate_id=_take(known, "gate_id"), action=_take(known, "action"),
            actor=_take(known, "actor"), decided_at=_take(known, "decided_at"),
            reason=_take(known, "reason"), scope_refs=_take(known, "scope_refs"),
            config_digest=_take(known, "config_digest"),
            evidence_refs=known.pop("evidence_refs", ()),
            supersedes=known.pop("supersedes", None),
            schema_version=known.pop("schema_version", 2), extra=data)


def frozen_config_bindings(config: Mapping[str, Any]) -> dict[str, str]:
    """Read the instance -> adapter bindings a frozen run configuration declares.

    The frozen configuration snapshot is the one authority on which adapter drives
    each instance; an adapter a caller names alongside an instance is never trusted
    over it. Each entry of the ``instances`` list names a unique ``id`` and the
    ``adapter`` bound to it, both validated as ids. A configuration that declares
    no instances binds nothing, so every instance is unknown against it.

    Args:
        config: The frozen configuration snapshot, as replayed from a run.

    Returns:
        A fresh ``{instance_id: adapter_id}`` mapping of every declared binding.

    Raises:
        ContractError: The snapshot, its ``instances`` list, or one entry is
            malformed, or an instance id is declared more than once.
    """
    bindings: dict[str, str] = {}
    for instance_id, entry in _configured_instances(config):
        if instance_id in bindings:
            raise ContractError(
                f"frozen config declares instance {instance_id!r} more than once")
        bindings[instance_id] = _id("configured adapter id", entry.get("adapter"))
    return bindings


#: A model is a DEPLOYMENT fact and it lives exactly where the adapter binding
#: lives: on the instance, in the run's frozen configuration. Not in a template
#: -- a reusable cycle that named a model would be a durable demand made of
#: every machine that ever ran it, and `templates/README.md` says why. Not in
#: the generic runtime either: nothing in this package knows a model id, and the
#: transports that put one on a command line learn it from here.
#:
#: **Optional is not nullable.** An omitted key is a configuration that said
#: nothing; an explicit ``"model": null`` is a configuration that chose a value,
#: and the value it chose is not a model id. So absence is read through a
#: SENTINEL and a null reaches the id validator and is refused -- exactly as
#: ``result_artifact_ref`` already does it, and for the same reason: collapsing
#: the two means a file that names a model wrongly runs on whatever the provider
#: decides and reports nothing about having done so.
#:
#: The wire goes the other way and that is not a contradiction. The controls
#: route projects an instance that pinned none as an explicit ``"model": null``,
#: because a consumer must tell "pinned none" from "this server cannot say". One
#: is a configuration a person wrote; the other is a projection this build
#: computed.
#:
#: **Where the runtime reads this matters as much as what it says.** The
#: execution road reads it ONCE, from the recovered run it already replayed --
#: the same snapshot that said which adapter drives the instance. A second read
#: later would be a read of a source that may have moved between the judgement
#: and the spawn, which is the defect class this package has already paid for on
#: a durable document. The runtime holds no model id, no default and no opinion
#: of its own; it carries what this function answered and nothing else.
def frozen_config_models(config: Mapping[str, Any]) -> dict[str, str]:
    """Read the model each configured instance PINS, where one is pinned at all.

    The key is OPTIONAL and absence is not a default. An instance that pins no
    model is absent from the answer, and what runs then is whatever the
    provider's own configuration decides -- which is a different thing from this
    build having chosen it, and is reported as such. The rulings behind that,
    and behind refusing an explicit null, stand above this function.

    Args:
        config: The frozen configuration snapshot, as replayed from a run.

    Returns:
        A fresh ``{instance_id: model}`` mapping of every instance that pins one.

    Raises:
        ContractError: The snapshot, its ``instances`` list, or one entry is
            malformed, or an instance id is declared more than once.
    """
    models: dict[str, str] = {}
    seen: set[str] = set()
    for instance_id, entry in _configured_instances(config):
        if instance_id in seen:
            raise ContractError(
                f"frozen config declares instance {instance_id!r} more than once")
        seen.add(instance_id)
        pinned = entry.get("model", ABSENT)
        if pinned is not ABSENT:
            models[instance_id] = _id("configured model id", pinned)
    return models


#: The keys a frozen ``workflow`` reference carries. Both are required: half of
#: one names a workflow at no revision or a revision of nothing, and either
#: would be a provenance a reader could not act on.
_WORKFLOW_FIELDS = frozenset({"id", "revision"})


def frozen_config_workflow(
        config: Mapping[str, Any]) -> tuple[str, int] | None:
    """Read WHICH workflow revision this run froze itself to follow.

    The reference is optional, and absence is a real answer rather than a
    missing one: a run may be opened with no workflow at all -- `conduct
    preview` and the control loop both do -- and such a run follows no plan
    this store could name. ``None`` says exactly that.

    What it must never do is guess. Before this key existed the run recorded no
    template identity anywhere, and the honest consequence was that the Studio
    showed no revision at all rather than a plausible one; a wrong provenance is
    worse than an absent one, which is why the key is validated as strictly as
    an id and a revision are validated anywhere else.

    Args:
        config: The frozen configuration snapshot, as replayed from a run.

    Returns:
        The ``(workflow_id, revision)`` this run follows, or ``None`` when the
        run froze no workflow reference.

    Raises:
        ContractError: The snapshot is not an object, or the reference is
            malformed, incomplete, or carries a key this contract does not know.
    """
    if not isinstance(config, Mapping):
        raise ContractError("frozen config must be a JSON object")
    reference = config.get("workflow", ABSENT)
    if reference is ABSENT:
        return None
    if not isinstance(reference, Mapping):
        raise ContractError("frozen config workflow must be a JSON object")
    supplied = set(reference)
    if supplied != _WORKFLOW_FIELDS:
        raise ContractError(
            "frozen config workflow carries "
            f"{sorted(supplied)!r} and must carry exactly "
            f"{sorted(_WORKFLOW_FIELDS)!r}")
    revision = reference["revision"]
    # `bool` is an `int` in Python and `True` is not revision 1. The same
    # refusal `_exact_revision` makes at the wire, made again at the read,
    # because a durable document is read by more callers than wrote it.
    if type(revision) is not int or isinstance(revision, bool) or revision < 1:
        raise ContractError(
            f"frozen config workflow revision must be an integer >= 1, "
            f"got {revision!r}")
    return _id("frozen config workflow id", reference["id"]), revision


def _configured_instances(
        config: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    """One walk of the frozen configuration's instance list, for both readers.

    Two readers ask this snapshot two questions -- which adapter drives an
    instance, and which model it pins -- and a second copy of the walk is a
    second answer to "which instances are there". They would drift on exactly
    the malformed snapshots that matter: one reader refusing an entry the other
    silently skipped is a configuration that binds an adapter and routes no
    model, or the reverse.

    It returns the id ALREADY validated, and the entry unread beyond that, so
    each caller still owns the fields that are its own business.
    """
    if not isinstance(config, Mapping):
        raise ContractError("frozen config must be a JSON object")
    declared = config.get("instances", ())
    if not isinstance(declared, (list, tuple)):
        raise ContractError(
            "frozen config 'instances' must be a list of instance objects")
    rows: list[tuple[str, Mapping[str, Any]]] = []
    for entry in declared:
        if not isinstance(entry, Mapping):
            raise ContractError("each configured instance must be a JSON object")
        rows.append((_id("configured instance id", entry.get("id")), entry))
    return rows


def gate_decision(receipts: Iterable[DecisionReceipt], run_id: str, gate_id: str) -> str:
    """Project one run-scoped decision; absence remains idle, never pass."""
    wanted_run = _id("run_id", run_id)
    wanted = _id("gate_id", gate_id)
    records = list(receipts)
    for receipt in records:
        if not isinstance(receipt, DecisionReceipt):
            raise ContractError("gate_decision accepts validated DecisionReceipt values only")
    ids = [receipt.receipt_id for receipt in records]
    if len(set(ids)) != len(ids):
        raise ContractError("decision receipts contain a duplicate receipt_id")
    by_id = {receipt.receipt_id: receipt for receipt in records}
    matching = [receipt for receipt in records
                if receipt.run_id == wanted_run and receipt.gate_id == wanted]
    if not matching:
        return "idle"
    for receipt in matching:
        if receipt.supersedes is None:
            continue
        prior = by_id.get(receipt.supersedes)
        if prior is None:
            raise ContractError(
                f"decision {receipt.receipt_id!r} supersedes unknown receipt "
                f"{receipt.supersedes!r}")
        if prior.run_id != wanted_run or prior.gate_id != wanted:
            raise ContractError(
                f"decision {receipt.receipt_id!r} cannot supersede a different run or gate")
    superseded = {r.supersedes for r in matching if r.supersedes is not None}
    current = [r for r in matching if r.receipt_id not in superseded]
    if not current:
        raise ContractError(f"gate {gate_id!r} has no unsuperseded decision receipt")
    if len(current) != 1:
        raise ContractError(
            f"gate {gate_id!r} in run {run_id!r} has multiple unsuperseded decisions")
    latest = current[0]
    return {
        "approve": "satisfied",
        "reject": "failed",
        "request_changes": "changes_requested",
        "waive": "waived",
    }[latest.action]

from .result_manifest import ResultManifestError, rebuild_manifest, manifest_digest  # noqa: F401
