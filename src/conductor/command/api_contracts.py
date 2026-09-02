"""Closed browser inputs and typed sanitized refusals for C/API-1.

The value mappers construct no durable response and call no service, store,
runtime, adapter, filesystem, process, or server seam.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import FrozenInstanceError, dataclass, fields
from types import MappingProxyType
from typing import Any

from .adapters import AdapterContractError, UnsupportedCapability
from .adapters.deep_commands import DEEP_ARGUMENT_TYPES
from .artifacts import ArtifactDocument
from .contracts import (
    ActionProposal,
    ContractError,
    ControlMode,
    DecisionReceipt,
    RunEnvelope,
    _id,
)
from .graph_definition import GraphDefinition, GraphEdge, GraphNode
from .graph_template import GraphTemplate, RunBinding
from .http_transport import HttpRefusal
# `snapshot_digest` opens nothing: it is canonical JSON and a hash, and it lives
# next door only because the store was its first caller. Taking it here keeps a
# run envelope's digest and the bytes it answers for built by one function.
from .run_store import CorruptRun, RecordConflict, StoreError, snapshot_digest
from .template_store import RouteNotOwned
from .runtime import AuthorizationError, Confirmation, RunAlreadyTerminal
from .service import ServiceError
from .workflow_draft import parse_document

#: The refusal half, re-exported under the names it has always had. The split
#: went this way round because the parsers below NEED the refusal shape, so the
#: refusals are the half that moves down; every caller -- five modules in
#: `conductor.command`, the server, and the suites that reach for
#: `_REFUSAL_BUILD` and `_EXCEPTION_SLOTS` by attribute -- keeps working
#: unchanged, and the frozen-API tests go on importing from here.
from .api_refusals import (  # noqa: F401 -- re-exported under old names
    ERROR_STATUS,
    NO_PROVIDERS_MESSAGE,
    ApiRefusal,
    _EXCEPTION_SLOTS,
    _FIXED_MESSAGES,
    _ID_RE,
    _PHASE_MESSAGES,
    _REFUSAL_BUILD,
    _REVIEWED_FACTS,
    _reviewed_fact,
    _safe_detail,
    _safe_id,
)

ARGUMENT_SCHEMAS = MappingProxyType({
    capability: tuple(field.name for field in fields(contract))
    for capability, contract in DEEP_ARGUMENT_TYPES.items()
})

_PROPOSAL_REQUIRED = frozenset({
    "instance_id", "attempt_id", "capability", "arguments", "scope",
    "proposed_by", "rationale", "timeout_seconds",
})
#: A proposal may also name the graph node it carries out. Optional because a
#: run without a graph proposes exactly as it always did -- and NOT nullable,
#: because absent and null would be two spellings of the same thing.
_PROPOSAL_FIELDS = _PROPOSAL_REQUIRED | {"adapter_id", "node_id"}
_CONFIRM_FIELDS = frozenset({
    "proposal_id", "preview_digest", "capability", "scope", "config_digest",
    "confirmed_by",
})
_DECISION_FIELDS = frozenset({
    "receipt_id", "gate_id", "action", "actor", "reason", "scope_refs",
    "evidence_refs", "supersedes",
})
#: A plan is the caller's; the run it belongs to and the moment it was written
#: are the server's. `run_id` and `created_at` are refused here rather than
#: ignored, so a caller learns the server owns them.
_GRAPH_FIELDS = frozenset({"graph_id", "nodes", "edges"})
#: A template belongs to no run and carries no timestamp, so neither word
#: appears here -- and the set IS the contract's own, read off it rather
#: than spelled a second time, because a field added to `GraphTemplate` that
#: this surface silently refused would be a contract the two disagree about.
_TEMPLATE_FIELDS = frozenset(GraphTemplate._FIELDS)
#: What a run supplies to materialize one: the plan's stable identity, the
#: immutable revision to build from, and who the roles are. Nothing else --
#: `nodes` here would be a second way to say what the revision already says.
_FROM_TEMPLATE_FIELDS = frozenset({
    "graph_id", "template_id", "revision", "assignments"})
_ARTIFACT_FIELDS = frozenset({
    "artifact_id", "artifact_ref", "media_type", "content"})
#: The ONE argument-schema family this frozen API speaks. A capability an
#: adapter serves under another family -- or under none -- is a capability this
#: surface cannot write a plan for, whatever the capability is called. Spelled
#: here and in ``adapters.deep_adapters``; a test pins the two equal and pins
#: this one inside the registry's reviewed set, so neither can move alone.
COMMAND_ARGUMENT_SCHEMA = "deep-arguments-v1"
@dataclass(frozen=True)
class ProposalInput:
    """One propose ENVELOPE: a validated shape around a payload not yet admitted.

    `arguments` has met no capability schema here. The pair authority admits it
    and `canonical_arguments` rebuilds it, in that order, and both happen on
    the route rather than in this type -- so a reader who takes this as
    "ready for CommandService.propose" would be taking a shape check for a
    capability verdict. Nothing else in production consumes it.
    """

    instance_id: str
    attempt_id: str
    capability: str
    arguments: Mapping[str, Any]
    scope: tuple[str, ...]
    proposed_by: str
    rationale: str
    timeout_seconds: int
    adapter_id: str | None
    node_id: str | None = None


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


@dataclass(frozen=True)
class GraphInput:
    """One validated plan; its run and the moment it lands are injected later."""

    graph_id: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def build(self, *, run_id: str, created_at: str) -> GraphDefinition:
        return GraphDefinition(
            graph_id=self.graph_id, run_id=run_id, created_at=created_at,
            nodes=self.nodes, edges=self.edges)


@dataclass(frozen=True)
class ArtifactInput:
    """One admitted handoff document before the server binds run and time."""

    artifact_id: str
    artifact_ref: str
    media_type: str
    content: str

    def build(self, *, run_id: str, created_at: str) -> ArtifactDocument:
        return ArtifactDocument(
            artifact_id=self.artifact_id, artifact_ref=self.artifact_ref,
            run_id=run_id, created_at=created_at, media_type=self.media_type,
            content=self.content)


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


def _json_array(values: dict[str, Any], name: str) -> list[Any]:
    value = values[name]
    if not isinstance(value, list):
        raise ApiRefusal.fixed("contract_invalid")
    return value


def canonical_arguments(
        capability: str, arguments: object) -> Mapping[str, Any]:
    """Rebuild one ADMITTED payload in its capability's canonical form.

    A transformation, not a second judgement: it runs only after the pair
    authority has said the bound adapter serves this capability through the one
    family this API speaks, and has put these very values through that pair's
    schema. Judging here as well would be two doors over one value.

    It is separate from the envelope parse because the order is a contract: a
    payload may not be judged, or rebuilt, until the pair is known to support
    it at all. Doing both in one pass answered `contract_invalid` for an
    unsupported pair, where the plan route answered `capability_unsupported`
    for the same pair and the same payload.
    """
    argument_type = DEEP_ARGUMENT_TYPES.get(capability)
    if argument_type is None:
        raise ApiRefusal.fixed("capability_unsupported")
    return _contract(_contract(argument_type.from_dict, arguments).as_dict)


def parse_proposal(body: object) -> ProposalInput:
    """Validate the closed propose ENVELOPE: its SHAPE, and nothing beyond.

    A closed field set, safe ids, a scope the contract accepts, and
    `arguments` held to being a JSON object of canonical data -- all a request
    can be judged on before anyone knows which adapter would carry it out.

    Whether the capability can be SERVED is deliberately not decided here. It
    used to be, against the union of every registered manifest, before the
    frozen configuration had even been read -- a fact about the build rather
    than about this run's binding. The plan route resolves the binding first,
    so the roads gave different words for one composite case. Every capability
    verdict now belongs to the pair authority, which cannot be asked until the
    bound adapter is known.
    """
    values = _proposal_body(body)
    capability = values["capability"]
    if not _safe_id(capability):
        raise ApiRefusal.fixed("contract_invalid") from None
    scope = _json_array(values, "scope")
    probe = _contract(
        ActionProposal,
        proposal_id="api-proposal-validation", run_id="api-run-validation",
        attempt_id=values["attempt_id"], instance_id=values["instance_id"],
        capability=capability, arguments=values["arguments"], scope=scope,
        proposed_by=values["proposed_by"], proposed_at="2000-01-01T00:00:00Z",
        timeout_seconds=values["timeout_seconds"], rationale=values["rationale"],
        config_digest="sha256:" + "0" * 64)
    adapter_id = values.get("adapter_id")
    if "adapter_id" in values and not _safe_id(adapter_id):
        raise ApiRefusal.fixed("contract_invalid") from None
    # A caller either names a node or does not mention one. Present-and-null is
    # refused here rather than read as absent, because the contract's own
    # optional-id rule cannot tell the two apart once a value reaches it.
    node_id = values.get("node_id")
    if "node_id" in values and not _safe_id(node_id):
        raise ApiRefusal.fixed("contract_invalid") from None
    return ProposalInput(
        instance_id=probe.instance_id, attempt_id=probe.attempt_id,
        # The submitted value travels on, NOT the probe's copy. The contract
        # freezes what it validates, and freezing turns a sequence into a
        # tuple -- which would launder the one thing the capability schemas
        # check by exact type, that an array arrived as a JSON array. The probe
        # has already proved this is a JSON object of canonical data; what it
        # MEANS is the pair's question, and the pair must see it unaltered.
        capability=probe.capability, arguments=values["arguments"],
        scope=probe.scope,
        proposed_by=probe.proposed_by, rationale=probe.rationale,
        timeout_seconds=probe.timeout_seconds, adapter_id=adapter_id,
        node_id=node_id)


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


@dataclass(frozen=True)
class TemplateRef:
    """One run's request to follow a stored revision, with who the roles are.

    The binding is a validated ``RunBinding`` by the time this exists, so a
    caller cannot reach the store or the materializer with a mapping the
    contract would refuse. What is NOT settled here is whether the revision
    exists, whether those instances are configured, or whether their adapters
    can do the work: those are facts about a run and a build, and only a plan
    about to be WRITTEN is worth asking them for.
    """

    graph_id: str
    template_id: str
    revision: int
    binding: RunBinding


def parse_template(body: object) -> GraphTemplate:
    """Take a published revision through the contract's own door and no other.

    The same ``from_dict`` an operator's file goes through, so what arrives over
    the wire is held to the contract rather than trusted for having arrived.
    The document is closed at every level, which is what refuses a
    ``provider_id`` or an ``instance_id`` smuggled into a node: this surface
    needs no by-name screen for deployment words, because a template that
    carried one would not be a template.
    """
    return _contract(GraphTemplate.from_dict, _closed(body, _TEMPLATE_FIELDS))


def parse_graph_from_template(body: object) -> TemplateRef:
    """Validate the four caller-owned facts of a materialization request.

    ``graph_id`` is the caller's, exactly as in ``parse_graph``, and for the
    same reason: it is what makes a retry findable. ``revision`` is taken as an
    exact ``int`` -- a string that looks like one is a different document -- and
    the assignments go through ``RunBinding`` here so that a role or an instance
    the contract would refuse never reaches a store.
    """
    values = _closed(body, _FROM_TEMPLATE_FIELDS)
    revision = values["revision"]
    if type(revision) is not int or isinstance(revision, bool) or revision < 1:
        raise ApiRefusal.fixed("contract_invalid")
    binding = _contract(RunBinding.from_dict, {"assignments": values["assignments"]})
    return TemplateRef(
        graph_id=_contract(_id, "graph_id", values["graph_id"]),
        template_id=_contract(_id, "template_id", values["template_id"]),
        revision=revision, binding=binding)


def parse_graph(body: object) -> GraphInput:
    """Validate exactly the three caller-owned facts of a run's one plan.

    The whole document is taken through the production contract here, with the
    server's own run and time standing in, so a plan that would not be a valid
    graph is refused before any store is opened. What this door does NOT judge
    is the payload a bound node carries: that answer belongs to the schema the
    registry recorded for the node's own ``(adapter_id, capability)`` pair, and
    only a plan about to be WRITTEN is worth asking it for -- so the route asks
    it, through the same registry door ``CommandService.propose`` calls.
    """
    values = _closed(body, _GRAPH_FIELDS)
    probe = _contract(GraphDefinition.from_dict, {
        "graph_id": values["graph_id"], "run_id": "api-run-validation",
        "created_at": "2000-01-01T00:00:00Z",
        "nodes": _json_array(values, "nodes"),
        "edges": _json_array(values, "edges")})
    return GraphInput(
        graph_id=probe.graph_id, nodes=probe.nodes, edges=probe.edges)


def parse_artifact(body: object) -> ArtifactInput:
    """Validate exactly the four caller-owned facts of one durable handoff."""
    values = _closed(body, _ARTIFACT_FIELDS)
    probe = _contract(ArtifactDocument.from_dict, {
        **values,
        "run_id": "api-run-validation",
        "created_at": "2000-01-01T00:00:00Z",
    })
    return ArtifactInput(
        artifact_id=probe.artifact_id, artifact_ref=probe.artifact_ref,
        media_type=probe.media_type, content=probe.content)


def refusal_from_exception(error: Exception) -> ApiRefusal:
    """Translate only exception types; submitted/OS/adapter prose is discarded."""
    if isinstance(error, HttpRefusal):
        return ApiRefusal.from_http(error)
    if isinstance(error, CorruptRun):
        return ApiRefusal.fixed("run_corrupt")
    if isinstance(error, RecordConflict):
        return ApiRefusal.fixed("record_conflict")
    if isinstance(error, RouteNotOwned):
        # A route that reaches somewhere this store does not own is the same
        # fact `run_route_violations` reports for a run, and it gets the same
        # word. `store_error` would call a caller's answer a server fault.
        return ApiRefusal.fixed("route_unsafe")
    if isinstance(error, StoreError):
        return ApiRefusal.fixed("store_error")
    if isinstance(error, UnsupportedCapability):
        return ApiRefusal.fixed("capability_unsupported")
    if isinstance(error, AdapterContractError):
        return ApiRefusal.fixed("service_refused")
    if isinstance(error, ServiceError):
        return ApiRefusal.fixed("service_refused")
    # BEFORE the `AuthorizationError` arm, because it is a subclass of it: the
    # order is what makes the wire word the specific one. Coded by TYPE, never
    # by reading the message this exception happens to carry.
    if isinstance(error, RunAlreadyTerminal):
        return ApiRefusal.fixed("run_terminal")
    if isinstance(error, AuthorizationError):
        return ApiRefusal.fixed("authorization_refused")
    if isinstance(error, ContractError):
        return ApiRefusal.fixed("contract_invalid")
    raise TypeError("exception type has no frozen API translation")
