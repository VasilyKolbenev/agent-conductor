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
from .runtime import AuthorizationError, Confirmation
from .service import ServiceError
from .workflow_draft import parse_document

ERROR_STATUS = MappingProxyType({
    "same_origin_denied": 403,
    "csrf_denied": 403,
    "method_not_allowed": 405,
    "route_not_found": 404,
    "malformed_request": 400,
    "contract_invalid": 422,
    "run_corrupt": 409,
    "store_error": 500,
    "route_unsafe": 409,
    "service_refused": 409,
    "capability_unsupported": 409,
    "authorization_refused": 409,
    "record_conflict": 409,
    "draft_changed": 409,
})

_FIXED_MESSAGES = MappingProxyType({
    "same_origin_denied": "request origin is not allowed",
    "csrf_denied": "request CSRF token is not current",
    "method_not_allowed": "request method is not allowed for this route",
    "route_not_found": "command route does not exist",
    "malformed_request": "request transport or JSON shape is malformed",
    "contract_invalid": "request values do not satisfy the contract",
    "run_corrupt": "stored run is corrupt",
    "store_error": "run store could not complete the request",
    "route_unsafe": "run route is not structurally contained",
    "service_refused": "command service refused the request",
    "capability_unsupported": "adapter does not support this capability",
    "authorization_refused": "confirmation did not authorize the request",
    "record_conflict": "durable record identity conflicts",
    #: Its own code rather than one more `contract_invalid`, because the caller
    #: did nothing wrong and there is something specific to DO about it: the
    #: draft moved under an open review, and the window must fetch the new one
    #: and ask the person to look again. A client cannot tell that from "the
    #: request shape is invalid", so it could only offer to try again -- which
    #: would publish the same stale review a second time.
    "draft_changed": "the draft changed since it was reviewed; read it again",
})

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
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_REFUSAL_BUILD = object()
#: The attributes the interpreter and its plumbing assign to an exception in
#: flight. A frozen dataclass refuses every assignment, these included, which
#: left a refusal unable to travel the one road Python carries it on.
_EXCEPTION_SLOTS = frozenset({
    "__traceback__", "__cause__", "__context__", "__suppress_context__",
    "__notes__",
})
#: What an operator must do when this build resolved no provider at all. It is
#: a DIFFERENT situation from naming a provider that is not available, and the
#: two must never share a sentence: one person has written no configuration yet
#: and the other has written one that does not carry the id they asked for. This
#: one is actionable and says exactly what to DO. It used to say where to act
#: -- the file and its five keys -- which was the only actionable thing there
#: was to say while hand-writing that file was the only road. Now there is a
#: command, so the sentence names the command; the file is still named, because
#: an operator who prefers to write it is not being told they may not.
NO_PROVIDERS_MESSAGE = (
    "this build resolved no available provider; run `conduct providers` to "
    "configure one — it asks for the paths and the environment variable names, "
    "and writes conductor/providers.json for you")
_PHASE_MESSAGES = MappingProxyType({
    "same_origin_denied": frozenset({
        "request Host is not allowed", "request origin is not allowed"}),
    "malformed_request": frozenset({
        "request transport or JSON shape is malformed",
        "request Content-Type is not supported",
        "request body is not one JSON object",
    }),
    "service_refused": frozenset({NO_PROVIDERS_MESSAGE}),
})


def _safe_id(value: object) -> bool:
    return isinstance(value, str) and _ID_RE.fullmatch(value) is not None


def _safe_detail(value: object) -> bool:
    """One detail value: a safe id, or a counting number spelled as itself."""
    if type(value) is int and not isinstance(value, bool):
        return value >= 1
    return _safe_id(value)


#: Every refusal that may carry a detail, as `(code, fields, sentence)`. A
#: closed table rather than a condition, because the closure is the point: a
#: detail is rendered into a browser, so what may appear there is reviewed one
#: fact at a time. The sentence is built from the SAME fields the detail
#: carries, so a message and its structured half cannot drift apart -- and a
#: refusal assembled anywhere else, with any other wording, is refused at
#: construction rather than shipped.
_REVIEWED_FACTS = (
    ("service_refused", ("run_id", "instance_id"),
     lambda facts: f"frozen config declares no instance '{facts['instance_id']}'"),
    ("service_refused", ("run_id", "instance_id"),
     lambda facts: (f"instance '{facts['instance_id']}' is bound to a provider "
                    "this build cannot reach")),
    ("service_refused", ("run_id", "template_id", "revision"),
     lambda facts: (f"no stored template '{facts['template_id']}' at revision "
                    f"{facts['revision']}")),
    # The same fact asked WITHOUT a run: the workflow read routes belong to no
    # run, so a run id in their refusal would be a fact they do not have. The
    # field sets differ, which is what keeps the two reviewed rows apart.
    ("service_refused", ("template_id", "revision"),
     lambda facts: (f"no stored template '{facts['template_id']}' at revision "
                    f"{facts['revision']}")),
    ("service_refused", ("provider_id",),
     lambda facts: (f"provider '{facts['provider_id']}' is not one this build "
                    "resolved as available")),
)


def _reviewed_fact(code: str, message: str, detail: dict) -> bool:
    """Whether this refusal is one of the reviewed facts, whole."""
    for reviewed, fields, sentence in _REVIEWED_FACTS:
        if code != reviewed or set(detail) != set(fields):
            continue
        if all(_safe_detail(detail[key]) for key in fields) \
                and message == sentence(detail):
            return True
    return False


@dataclass(frozen=True, init=False)
class ApiRefusal(Exception):
    """One closed browser-safe refusal; no exception prose is carried through."""

    code: str
    message: str
    detail: Mapping[str, str]

    def __init__(
            self, build: object, code: str, message: str,
            detail: Mapping[str, str]) -> None:
        if build is not _REFUSAL_BUILD:
            raise ValueError("API refusals require a reviewed factory")
        if code not in ERROR_STATUS:
            raise ValueError("unknown API refusal code")
        copied = dict(detail)
        if copied:
            if not _reviewed_fact(code, message, copied):
                raise ValueError("API refusal detail must match a reviewed fact")
        else:
            messages = _PHASE_MESSAGES.get(code, frozenset()) | {
                _FIXED_MESSAGES[code]}
            if message not in messages:
                raise ValueError("API refusal message must match a reviewed template")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "detail", MappingProxyType(copied))
        Exception.__init__(self, message)

    @property
    def status(self) -> int:
        return ERROR_STATUS[self.code]

    def as_dict(self) -> dict[str, object]:
        """Return exactly the frozen refusal envelope."""
        return {"error": {
            "code": self.code, "message": self.message, "detail": dict(self.detail)}}

    @classmethod
    def fixed(cls, code: str) -> "ApiRefusal":
        """Build one vocabulary-complete refusal with no submitted detail."""
        if code not in _FIXED_MESSAGES:
            raise ValueError("unknown API refusal code") from None
        return cls(_REFUSAL_BUILD, code, _FIXED_MESSAGES[code], {})

    @classmethod
    def from_http(cls, refusal: HttpRefusal) -> "ApiRefusal":
        """Preserve the transport's reviewed phase-specific safe message."""
        if not isinstance(refusal, HttpRefusal):
            raise ValueError("HTTP refusal must be typed")
        return cls(_REFUSAL_BUILD, refusal.code, refusal.message, {})

    @classmethod
    def service_missing_instance(
            cls, run_id: str, instance_id: str) -> "ApiRefusal":
        """Name one validated frozen-config relation without exception prose."""
        if not _safe_id(run_id) or not _safe_id(instance_id):
            raise ValueError("service refusal identifiers must be safe IDs") from None
        detail = {"run_id": run_id, "instance_id": instance_id}
        message = f"frozen config declares no instance '{instance_id}'"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def service_missing_revision(
            cls, run_id: str, template_id: str, revision: int) -> "ApiRefusal":
        """Name a revision this build does not hold, and no path to look at."""
        detail = {"run_id": run_id, "template_id": template_id,
                  "revision": revision}
        message = f"no stored template '{template_id}' at revision {revision}"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def missing_revision(cls, template_id: str, revision: int) -> "ApiRefusal":
        """Name a revision this build does not hold, with no run and no path."""
        detail = {"template_id": template_id, "revision": revision}
        message = f"no stored template '{template_id}' at revision {revision}"
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def service_no_providers(cls) -> "ApiRefusal":
        """Say that nothing is configured, and exactly where to configure it.

        An empty roster is a first-class state of a fresh project, not a fault:
        nobody has written `conductor/providers.json` yet. So the refusal is a
        instruction rather than a diagnosis, and it carries no detail at all --
        there is no id to name, which is precisely what distinguishes it from a
        request that named a provider this build does not have.
        """
        return cls(_REFUSAL_BUILD, "service_refused", NO_PROVIDERS_MESSAGE, {})

    @classmethod
    def service_unknown_provider(cls, provider_id: str) -> "ApiRefusal":
        """Name the PROVIDER a caller chose that this build cannot reach.

        The id is the caller's own word, echoed back, so nothing about this
        build's roster leaks: a provider that is configured and unavailable and
        a provider nobody configured are refused in the same sentence, exactly
        as `service_unreachable_adapter` refuses the two by one rule.
        """
        if not _safe_id(provider_id):
            raise ValueError("service refusal identifiers must be safe IDs") from None
        detail = {"provider_id": provider_id}
        message = (f"provider '{provider_id}' is not one this build resolved as "
                   "available")
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)

    @classmethod
    def service_unreachable_adapter(
            cls, run_id: str, instance_id: str) -> "ApiRefusal":
        """Name the INSTANCE, because the product behind it is not the fact.

        Whether a provider can be reached is a state this build resolved, and
        the refusal says only that the instance a role was bound to is not
        reachable. Naming the adapter would put a vendor in a message the
        Cockpit renders, and a caller who supplied the binding already knows
        which instance they chose.
        """
        detail = {"run_id": run_id, "instance_id": instance_id}
        message = (f"instance '{instance_id}' is bound to a provider this build "
                   "cannot reach")
        return cls(_REFUSAL_BUILD, "service_refused", message, detail)


def _refusal_setattr(self: ApiRefusal, name: str, value: object) -> None:
    """Stay frozen as a value, and travel as an exception.

    Every mutating route re-checks its containment INSIDE the store
    transaction, because a route can be made unsafe between the first check and
    the lock. That second refusal never arrived: `contextlib` assigns
    `__traceback__` to an exception on its way out of a context manager, a
    frozen dataclass refuses the assignment, and what reached the boundary was
    an untranslatable `TypeError` instead of one closed `409 route_unsafe`.

    Only the attributes the interpreter and its plumbing own are let through.
    The three reviewed fields stay exactly as read-only as before, and say so
    with the dataclass's own error.
    """
    if name in _EXCEPTION_SLOTS:
        object.__setattr__(self, name, value)
        return
    raise FrozenInstanceError(f"cannot assign to field {name!r}")


# `dataclass(frozen=True)` refuses to install its guard over a `__setattr__`
# written in the class body, so the widened guard is installed right after the
# decorator has run rather than instead of it.
ApiRefusal.__setattr__ = _refusal_setattr


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
    if isinstance(error, AuthorizationError):
        return ApiRefusal.fixed("authorization_refused")
    if isinstance(error, ContractError):
        return ApiRefusal.fixed("contract_invalid")
    raise TypeError("exception type has no frozen API translation")
