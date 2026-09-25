"""The reusable half of a graph: one step, one document, and the plan it builds.

Split out of ``graph_template`` when that module crossed the 800-line cap, along
the seam its own docstring already draws: a ``GraphTemplate`` says what the work
IS, written in roles, and a ``RunBinding`` says who those roles are for one run.
The first is a reusable DOCUMENT; the second is a DEPLOYMENT, and only a
deployment has an opinion about which machine anything runs on.

``_build`` is here rather than beside ``materialize`` next door, and that is the
seam speaking rather than convenience. It is not the deployment road: it is what
a template PROVES ITSELF with. ``GraphTemplate.__post_init__`` calls it against
placeholder assignments and throws the result away, so a template that exists is
one that materializes and the topology rules it is held to are the ones
``GraphDefinition`` already owns. A deployment cannot be a dependency of that,
which is also why the split had to go this way round: the document is what the
deployment needs, so it is the half that moves DOWN.

``graph_template`` imports every name here back under its old spelling, so no
caller anywhere learns that the split happened.

Two things this document refuses, and each is the point of it:

- **a field this contract does not name, at any level.** The document is
  CLOSED, so a provider, an instance, an adapter or a run's pass counter is
  refused the way any unknown key is. What a closed shape cannot catch is a
  field ADDED under one of those names later, so ``DEPLOYMENT_ONLY_FIELDS`` is
  held against this contract's own ``_FIELDS``, in both directions, by
  ``tests/test_command_graph_template.py``.
- **a topology this product's base contract would not accept**, by the probe
  materialization described above.

Like the module it was taken from, this has no server or adapter imports.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import ABSENT as _EXECUTION_ABSENT
from .contracts import (
    ContractError,
    _freeze_json,
    _id,
    _json_copy,
    _take,
    _text,
    canonical_json,
    frozen_config_bindings,
)
from .graph_definition import (
    EFFECTING_CAPABILITIES,
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
    GraphResource,
    _ABSENT,
    _exact,
    _json_list,
    _json_object,
    _sequence,
)

from .graph_values import (
    POSITION_LIMIT,
    NodePosition,
    _position,
    settled_bounds,
    settled_purpose,
    settled_failure_policy,
    settled_missing_artifact_policy,
    settled_success_requires,
    settled_required_evidence,
)
from .artifacts import requires_input_artifacts

#: Every word that names a DEPLOYMENT rather than a piece of work. A template
#: is meant to be run in more than one place, so a field spelled any of these
#: would pin it to one of them.
#:
#: This document is CLOSED at every level -- each `from_dict` refuses a key its
#: contract does not name -- so none of these can arrive as data; a by-name
#: walk beside that would be a guard no caller could reach. What the list is
#: for is the contract's own vocabulary: `tests/test_command_graph_template.py`
#: holds `_FIELDS` against it in both directions, so the day a field is ADDED
#: under one of these names it reds, which is the failure a closed shape cannot
#: catch on its own. It is also what the shipped documents are read against.
DEPLOYMENT_ONLY_FIELDS = frozenset({
    "adapter", "adapter_class", "adapter_id", "entrypoint", "executable",
    "instance", "instance_id", "instances", "protocol", "provider",
    "provider_id", "providers", "vendor",
})
#: The one field whose value is a capability's own payload. Lifted out by name
#: before either walk runs, exactly as ``GraphNode.from_dict`` does: its keys
#: belong to the capability's registered schema, not to this vocabulary.
EXEMPT_FIELD = "arguments"
#: What the probe materialization stands in for. Never durable, never returned,
#: and never a real instance: it exists only so the base contract's topology
#: rules judge a template the moment it is constructed.
_PROBE_INSTANCE = "role-probe"
_PROBE_RUN = "run-template-probe"
_PROBE_AT = "1970-01-01T00:00:00Z"
_PROBE_GRAPH = "graph-template-probe"

MAX_ROLES = 64
#: The one schema this contract speaks, and it is held EXACTLY rather than as a
#: floor. `graph_definition` tolerates a forward version because it is an OPEN
#: document: it carries fields it does not know through in `extra`, so a later
#: revision of itself is something it can honestly hold. This document is CLOSED
#: at every level -- every `from_dict` refuses a key its contract does not name
#: -- so it cannot read a later revision at all. Accepting one meant taking a v2
#: document that happened to use only v1 fields, and answering a v2 document
#: that used a new field with "unsupported field", which tells its author the
#: field is wrong when what is actually wrong is that this build does not speak
#: their schema.
SCHEMA_VERSION = 1


class TemplateError(ContractError):
    """A template, a binding, or a materialization was refused."""


@dataclass(frozen=True)
class TemplateNode:
    """One step of reusable work: what it is, what it needs, and WHOSE role."""

    node_id: str
    kind: str
    title: str
    stage: str | None = None
    role_id: str | None = None
    capability: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict, repr=False)
    resources: tuple[GraphResource, ...] = ()
    gate_id: str | None = None
    loop: GraphLoop | None = None
    #: The two ceilings a plan may place on one step: the longest its work may
    #: run, and the most attempts it allows. Optional, and absent means the plan
    #: constrains neither -- which is what every template written before they
    #: existed says, so `dalio-v1` digests exactly as it did.
    timeout_seconds: int | None = None
    attempt_bound: int | None = None
    #: Why this step exists, in the words of whoever drew it. Optional, so every
    #: template written before it existed digests exactly as it did.
    purpose: str | None = None
    #: WHO must confirm this step, as a ROLE. A template may not name an
    #: instance -- `DEPLOYMENT_ONLY_FIELDS` refuses one -- and that is exactly
    #: right here: a workflow says "a reviewer confirms this", and WHICH
    #: participant fills that role is a fact of the run, settled by the binding
    #: and frozen into the plan as `verifier_instance_id`.
    verifier_role_id: str | None = None
    #: Where a person put this step on the canvas, or None to let the canvas
    #: place it. Editor state and not execution semantics: `materialize` does
    #: not carry it into the run's frozen plan, so no replay and no runtime
    #: decision can depend on where a box sits.
    position: NodePosition | None = None
    #: WHAT this step's verification must name, beyond having happened. The
    #: DEFINITION's own word, carried here unchanged: it names no role, no
    #: instance and no deployment, so unlike `verifier_role_id` there is nothing
    #: for a binding to resolve and `materialize` copies it across as it stands.
    #: Optional, so every template written before it existed digests as it did.
    required_evidence: str | None = None
    #: The DEFINITION's word again, carried across unchanged: it names no
    #: role, so a binding resolves nothing. Optional, so no digest moves.
    failure_policy: str | None = None
    #: The DEFINITION's word again, carried across unchanged. Optional,
    #: so no template written before it existed moves a digest.
    missing_artifact_policy: str | None = None
    #: The DEFINITION's word again, carried across unchanged. Optional,
    #: so no template written before it existed moves a digest.
    success_requires: str | None = None

    _FIELDS = frozenset({
        "node_id", "kind", "title", "stage", "role_id", "capability",
        "arguments", "resources", "gate_id", "loop", "timeout_seconds",
        "attempt_bound", "purpose", "verifier_role_id", "position",
        "required_evidence", "failure_policy", "missing_artifact_policy",
        "success_requires",
    })

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _id("node_id", self.node_id))
        object.__setattr__(self, "title", _text("title", self.title))
        if self.role_id is not None:
            object.__setattr__(self, "role_id", _id("role_id", self.role_id))
        # A binding is a PAIR, and half of one is a step nobody can carry out
        # or a name nobody uses. The definition holds the same relation between
        # `instance_id` and `capability`; this is that relation one layer up.
        if (self.role_id is None) != (self.capability is None):
            half = ("a role with no capability" if self.capability is None
                    else "a capability with no role")
            raise TemplateError(
                f"node {self.node_id!r} names {half}; a template step binds "
                "both or neither")
        if self.capability is not None:
            object.__setattr__(self, "capability", _id("capability", self.capability))
        self._settle_arguments()
        # The DEFINITION's own rule, not a second copy of it: a template
        # ceiling the layer below would refuse is a template that cannot
        # materialize, and run time is too late to find that out.
        for name, value in settled_bounds(
                self.timeout_seconds, self.attempt_bound).items():
            object.__setattr__(self, name, value)
        # Taken through the same door a document goes through, so a caller
        # handing a raw mapping and a caller handing a value get one answer.
        object.__setattr__(self, "position", _position(self.position))
        # The DEFINITION's grammar, imported rather than restated: a purpose the
        # layer below would refuse is a template that cannot materialize.
        object.__setattr__(self, "purpose", settled_purpose(self.purpose))
        if self.verifier_role_id is not None:
            if self.role_id is None:
                raise TemplateError(
                    f"node {self.node_id!r} names a verifier role and binds no "
                    "role of its own; a step that carries nothing out has "
                    "nothing to verify")
            object.__setattr__(self, "verifier_role_id",
                               _id("verifier_role_id", self.verifier_role_id))
            if self.verifier_role_id == self.role_id:
                raise TemplateError("a step's verifier must be another participant")
        self._settle_verification_demands()
        self._settle_missing_artifact_policy()
        self._settle_success_requires()

    def _settle_missing_artifact_policy(self) -> None:
        """A policy about a missing input belongs to a step that HAS inputs.

        The DEFINITION's rule in this document's vocabulary, and its own half is
        the CAPABILITY rather than the role: a person drawing a workflow binds a
        role and picks what that role does, and being told "this step is given
        no artifacts" is the sentence that tells them which of the two to
        change. A message naming only the role would send them to the half that
        is not the problem -- a `stop` step bound to a perfectly good role is
        still a step nothing hands a document to.
        """
        object.__setattr__(
            self, "missing_artifact_policy",
            settled_missing_artifact_policy(self.missing_artifact_policy))
        if self.missing_artifact_policy is not None and not (
                requires_input_artifacts(self.capability)):
            raise TemplateError(
                f"node {self.node_id!r} names a missing-artifact policy and is "
                f"given no artifacts: {self.capability!r} takes no input "
                "documents, so there is no input for it to be missing")

    def _settle_success_requires(self) -> None:
        """The DEFINITION's rule in this document's vocabulary.

        Its own half is the KIND, said as the person drew it: they chose a step
        type from a closed list, and being told which type they chose is what
        sends them to the control they can change. The layer below refuses the
        same document; what this adds is that a workflow carrying such a step
        cannot be PUBLISHED at all, so no run is ever opened on a plan whose
        protection was never real.
        """
        object.__setattr__(self, "success_requires",
                           settled_success_requires(self.success_requires))
        if self.success_requires is not None and self.kind != "gate":
            raise TemplateError(
                f"node {self.node_id!r} names a gate success requirement and "
                f"is a {self.kind!r}, not a gate; only a gate is answered by a "
                "Human, so only a gate can demand anything of that answer")

    def _settle_verification_demands(self) -> None:
        """The two things a plan may say about a step's own outcome.

        The DEFINITION's grammars and pairing rules in this document's
        vocabulary: a step binding no role carries nothing out, so it is
        verified by nobody and it cannot fail. Refused where the workflow is
        DRAWN, not at the run it could not materialize.
        """
        object.__setattr__(self, "required_evidence",
                           settled_required_evidence(self.required_evidence))
        if self.required_evidence is not None and self.role_id is None:
            raise TemplateError(
                f"node {self.node_id!r} requires evidence and binds no role of "
                "its own; a step that carries nothing out is verified by "
                "nobody, so there is no verification to require anything of")
        object.__setattr__(self, "failure_policy",
                           settled_failure_policy(self.failure_policy))
        if self.failure_policy is not None and self.role_id is None:
            raise TemplateError(
                f"node {self.node_id!r} names a failure policy and binds no "
                "role of its own; a step that carries nothing out cannot "
                "fail, so there is no failure for a policy to answer")

    def _settle_arguments(self) -> None:
        """Take the caller's payload once, then answer only from our own copy.

        ``graph_definition`` learned this on the node next door and the reason
        carries over unchanged: validating at construction settles what the
        field WAS. Until this ran, the contract kept the caller's own mapping
        and handed that same object back out of ``as_dict`` -- so editing a
        rendered template edited the TEMPLATE, at the same ``revision``, which
        is the one thing a revision exists to make impossible.
        """
        arguments = _json_object(f"template node {self.node_id} arguments",
                                 self.arguments)
        if self.role_id is None and arguments:
            raise TemplateError(
                f"node {self.node_id!r} carries arguments with no role to read them")
        settled = _json_copy(f"template node {self.node_id} arguments",
                             dict(arguments))
        object.__setattr__(self, EXEMPT_FIELD, _freeze_json(settled))
        # What this contract hands any consumer, in ITS words rather than in the
        # caller's object -- plus the exact object it stored, so a later
        # replacement can be SEEN without being READ.
        object.__setattr__(self, "_payload_text", canonical_json(settled))
        object.__setattr__(self, "_payload_witness", self.arguments)

    def payload(self) -> dict[str, Any]:
        """The validated arguments, rebuilt from this contract's own record.

        Caught by IDENTITY, which reads nothing at all: the field is either the
        exact object settled above or it is not. A hostile mapping put there
        afterwards would otherwise answer ``items`` with its own exception, and
        that exception would leave carrying whatever it carried.
        """
        if self.arguments is not self._payload_witness:
            raise TemplateError(
                f"node {self.node_id!r} arguments were replaced after they were "
                "validated; this contract answers only for what it settled"
            ) from None
        return json.loads(self._payload_text)

    def _document(self) -> dict[str, Any]:
        """This node as data, for the walks that judge it by field name."""
        out: dict[str, Any] = {"node_id": self.node_id, "kind": self.kind,
                               "title": self.title}
        if self.stage is not None:
            out["stage"] = self.stage
        if self.role_id is not None:
            out["role_id"] = self.role_id
            out["capability"] = self.capability
            out[EXEMPT_FIELD] = self.payload()
        if self.gate_id is not None:
            out["gate_id"] = self.gate_id
        if self.loop is not None:
            out["loop"] = self.loop.as_dict()
        # Written only when named, so a template that constrains neither is the
        # document it always was and its revision digest does not move.
        if self.timeout_seconds is not None:
            out["timeout_seconds"] = self.timeout_seconds
        if self.attempt_bound is not None:
            out["attempt_bound"] = self.attempt_bound
        if self.purpose is not None:
            out["purpose"] = self.purpose
        if self.verifier_role_id is not None:
            out["verifier_role_id"] = self.verifier_role_id
        if self.required_evidence is not None:
            out["required_evidence"] = self.required_evidence
        if self.failure_policy is not None:
            out["failure_policy"] = self.failure_policy
        if self.missing_artifact_policy is not None:
            out["missing_artifact_policy"] = self.missing_artifact_policy
        if self.success_requires is not None:
            out["success_requires"] = self.success_requires
        if self.position is not None:
            out["position"] = self.position.as_dict()
        out["resources"] = [row.as_dict() for row in self.resources]
        return out

    @property
    def effecting(self) -> bool:
        """Whether this step can change the world, by its capability alone."""
        return self.capability in EFFECTING_CAPABILITIES

    def as_dict(self) -> dict[str, Any]:
        return self._document()

    @classmethod
    def from_dict(cls, value: object) -> "TemplateNode":
        # Refused exactly, then COPIED. `_json_object` hands back the caller's
        # own dict and every field below is taken with `pop`, so reading a
        # document emptied it: a caller could not read the same file twice, and
        # the second read failed claiming a required field was missing when the
        # first read is what removed it. `_raw` next door copies for this reason.
        data = dict(_json_object("template node", value))
        # The sentinel, not `None`, and `graph_definition` uses the same one for
        # the same reason: a key that is ABSENT is a step with no payload, and a
        # key present with an explicit `null` is a document that says something
        # else and says it wrongly. Defaulting to `None` spelled both as "empty"
        # and told the author of the second nothing at all.
        arguments = data.pop(EXEMPT_FIELD, _ABSENT)
        unknown = sorted(set(data) - (cls._FIELDS - {EXEMPT_FIELD}))
        if unknown:
            raise TemplateError(f"template node carries unsupported field(s) {unknown!r}")
        loop = data.pop("loop", None)
        resources = _json_list("template node resources", data.pop("resources", []))
        return cls(
            node_id=_take(data, "node_id"), kind=_take(data, "kind"),
            title=_take(data, "title"), stage=data.pop("stage", None),
            role_id=data.pop("role_id", None),
            capability=data.pop("capability", None),
            arguments={} if arguments is _ABSENT else arguments,
            resources=tuple(GraphResource.from_dict(row) for row in resources),
            gate_id=data.pop("gate_id", None),
            loop=None if loop is None else GraphLoop.from_dict(loop),
            timeout_seconds=data.pop("timeout_seconds", None),
            attempt_bound=data.pop("attempt_bound", None),
            purpose=data.pop("purpose", None),
            verifier_role_id=data.pop("verifier_role_id", None),
            position=_position(data.pop("position", None)),
            required_evidence=data.pop("required_evidence", None),
            failure_policy=data.pop("failure_policy", None),
            missing_artifact_policy=data.pop(
                "missing_artifact_policy", None),
            success_requires=data.pop("success_requires", None))


@dataclass(frozen=True)
class GraphTemplate:
    """A reusable plan: one topology, its roles, and the revision it is at.

    Editing a template does not edit anything a run followed. A change makes a
    NEW revision -- a different identity -- so every run that already
    materialized from an earlier one still replays byte for byte against the
    definition it was given.
    """

    template_id: str
    revision: int
    title: str
    nodes: tuple[TemplateNode, ...]
    edges: tuple[GraphEdge, ...] = ()
    schema_version: int = SCHEMA_VERSION
    execution_contract: object = _EXECUTION_ABSENT

    _FIELDS = frozenset({
        "schema_version", "template_id", "revision", "title", "nodes", "edges", "execution_contract",
    })

    def __post_init__(self) -> None:
        object.__setattr__(self, "template_id", _id("template_id", self.template_id))
        object.__setattr__(self, "title", _text("title", self.title))
        object.__setattr__(self, "revision", _revision(self.revision))
        object.__setattr__(self, "schema_version", _schema_spoken(self.schema_version))
        from .graph_execution import settled_execution_contract
        object.__setattr__(self, "execution_contract", settled_execution_contract(self.execution_contract))
        object.__setattr__(self, "nodes", self._settled_nodes())
        object.__setattr__(self, "edges", tuple(
            _rebuilt_edge(row) for row in _sequence("template edges", self.edges)))
        # The same snapshot-and-witness the nodes carry, one level up: the text
        # is what this contract will hand any consumer, and the two tuples are
        # the exact objects it settled, so a replacement is SEEN rather than
        # read. A tuple cannot be edited, which is precisely why an attacker
        # replaces the whole of it.
        object.__setattr__(self, "_document_text", canonical_json(self._document()))
        object.__setattr__(self, "_nodes_witness", self.nodes)
        object.__setattr__(self, "_edges_witness", self.edges)
        # The topology rules are the base contract's, and they stay there: a
        # template proves itself by materializing against placeholders, so a
        # constructed template is one that materializes and there is no second
        # copy of those rules to drift from the first.
        self._probe()

    def _settled_nodes(self) -> tuple[TemplateNode, ...]:
        rows = _sequence("template nodes", self.nodes)
        if not rows:
            raise TemplateError("a template must carry at least one node")
        rows = tuple(_rebuilt_node(row) for row in rows)
        if len({row.node_id for row in rows}) != len(rows):
            raise TemplateError("template nodes must not repeat a node_id")
        if len(self._roles_of(rows)) > MAX_ROLES:
            raise TemplateError(
                f"a template declares at most {MAX_ROLES} roles")
        return rows

    @staticmethod
    def _roles_of(nodes: Iterable[TemplateNode]) -> tuple[str, ...]:
        """Every role a binding must cover, the doing ones and the verifying ones.

        A verifier role counts. A binding that covered only the roles that do
        work would leave a step naming a verifier nobody had assigned, and
        `materialize` would then have to invent an instance or drop the field --
        both of which are the thing this contract exists to prevent.
        """
        seen: list[str] = []
        for node in nodes:
            for role in (node.role_id, node.verifier_role_id):
                if role is not None and role not in seen:
                    seen.append(role)
        return tuple(seen)

    @property
    def roles(self) -> tuple[str, ...]:
        """Every role this template names, in the order its nodes name them.

        One role may carry several steps -- that is the whole point of a role --
        so this is the DISTINCT set, and it is what a binding must cover.
        """
        return self._roles_of(self.steps())

    def _unreplaced(self) -> None:
        """Refuse if the tuples this contract settled were swapped whole.

        Nodes and edges are tuples, so nothing can be edited INSIDE the tuple
        -- which is exactly why a replacement swaps the whole of it. Identity
        catches that without calling one method on whatever arrived, so a
        hostile object's own exception never becomes this contract's answer.
        """
        if (self.nodes is not self._nodes_witness
                or self.edges is not self._edges_witness):
            raise TemplateError(
                f"template {self.template_id!r} had its nodes or edges replaced "
                "after they were validated; this contract answers only for what "
                "it settled") from None

    def settled(self) -> tuple[tuple[TemplateNode, ...], tuple[GraphEdge, ...]]:
        """Nodes and edges REBUILT from this contract's own canonical record.

        Not the live values, and the difference was a plan that disagreed with
        itself. The witness above catches a tuple swapped whole; it cannot
        catch a value edited INSIDE an intact tuple, and every scalar on
        ``TemplateNode``, ``GraphEdge``, ``GraphLoop`` and ``GraphResource`` is
        such a field. So ``as_dict`` answered from the snapshot while
        ``materialize`` walked the objects themselves, and one template at one
        ``revision`` asserted two different plans -- the document said the step
        was called `Goal` and the definition it produced said something else.

        Rebuilding from the canonical text closes all of them at once, and it
        needs no per-field guard that a fifth nested type would have to
        remember to join. Every value goes back through its own ``from_dict``,
        so what comes out is what this contract settled or it does not come out
        at all.
        """
        document = self.as_dict()
        return (tuple(TemplateNode.from_dict(row) for row in document["nodes"]),
                tuple(GraphEdge.from_dict(row) for row in document["edges"]))

    def steps(self) -> tuple[TemplateNode, ...]:
        """The nodes this contract settled, rebuilt from its own record."""
        return self.settled()[0]

    def _probe(self) -> None:
        try:
            _build(self, {role: f"{_PROBE_INSTANCE}-{index}"
                          for index, role in enumerate(self.roles)},
                   graph_id=_PROBE_GRAPH, run_id=_PROBE_RUN, created_at=_PROBE_AT)
        except ContractError as error:
            raise TemplateError(
                f"template {self.template_id!r} does not describe a graph this "
                f"product can build: {error}") from None

    def _document(self) -> dict[str, Any]:
        """This template as data, built once at construction and never again."""
        document = {
            "schema_version": self.schema_version,
            "template_id": self.template_id,
            "revision": self.revision,
            "title": self.title,
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
        }

        if self.execution_contract is not _EXECUTION_ABSENT:
            document["execution_contract"] = self.execution_contract
        return document

    def as_dict(self) -> dict[str, Any]:
        """A FRESH document, parsed from the canonical text settled at build.

        Every caller gets its own copy, so editing a rendered template is
        editing that caller's paper and nothing else. What it renders is this
        contract's own record rather than a walk over fields that may have been
        replaced since.
        """
        self._unreplaced()
        return json.loads(self._document_text)

    @classmethod
    def from_dict(cls, value: object) -> "GraphTemplate":
        data = dict(_json_object("template", value))
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise TemplateError(f"template carries unsupported field(s) {unknown!r}")
        return cls(
            template_id=_take(data, "template_id"),
            revision=_take(data, "revision"),
            title=_take(data, "title"),
            nodes=tuple(TemplateNode.from_dict(row)
                        for row in _json_list("template nodes", _take(data, "nodes"))),
            edges=tuple(GraphEdge.from_dict(row)
                        for row in _json_list("template edges", data.pop("edges", []))),
            schema_version=data.pop("schema_version", SCHEMA_VERSION),
            execution_contract=data.pop("execution_contract", _EXECUTION_ABSENT))


def _schema_spoken(value: object) -> int:
    """Exactly the one schema this closed document can honestly read."""
    number = _exact("template schema_version", value, int)
    if number != SCHEMA_VERSION:
        raise TemplateError(
            f"this build speaks template schema_version {SCHEMA_VERSION} and "
            f"this document claims {number}; a closed contract cannot read a "
            "revision of itself it has never seen")
    return number


def _revision(value: object) -> int:
    number = _exact("template revision", value, int)
    if number < 1:
        raise TemplateError("a template revision starts at 1 and only goes up")
    return number


def _rebuilt_node(row: object) -> TemplateNode:
    """Take a node by IDENTITY of type and rebuild it from its attributes.

    The reason is `graph_definition`'s: `isinstance` lets a subclass answer
    `as_dict()` with a word this layer refuses, and a rebuild also re-validates
    a value edited after construction. The payload comes from `payload()` for
    that contract's reason too -- reading the attribute WAS the polymorphic
    act, and `payload()` sees a replacement by identity and reads it never.
    """
    if type(row) is not TemplateNode:
        raise TemplateError("template nodes must be TemplateNode values")
    return TemplateNode(
        node_id=row.node_id, kind=row.kind, title=row.title, stage=row.stage,
        role_id=row.role_id, capability=row.capability, arguments=row.payload(),
        resources=row.resources, gate_id=row.gate_id, loop=row.loop,
        timeout_seconds=row.timeout_seconds, attempt_bound=row.attempt_bound,
        purpose=row.purpose, verifier_role_id=row.verifier_role_id,
        position=row.position, required_evidence=row.required_evidence,
        failure_policy=row.failure_policy,
        missing_artifact_policy=row.missing_artifact_policy,
        success_requires=row.success_requires)


def _rebuilt_edge(row: object) -> GraphEdge:
    if type(row) is not GraphEdge:
        raise TemplateError("template edges must be GraphEdge values")
    return GraphEdge(from_node=row.from_node, to_node=row.to_node,
                     condition=row.condition)


def _dispatch_payload(node) -> dict[str, Any]:
    """One step's capability payload, with its purpose carried into it.

    A purpose has to travel INSIDE the payload for a step that acts, and this is
    the one place it can be put. An adapter is handed a request and never sees
    the plan, so a value left only on the node would reach no vendor binary; and
    `graph_causality` refuses any proposal or request whose arguments are not
    byte-identical to the node's payload, so putting it here makes the PLAN the
    authority over what a child is told, durably and on replay -- rather than
    trusting whoever composes a proposal to copy it faithfully.

    A step that carries out nothing gets nothing added: a gate and a loop have
    no capability, no payload and no child, and their purpose is read by the
    Decision, Run and Inspector surfaces off the node itself.
    """
    payload = node.payload()
    if node.capability is None or node.purpose is None:
        return payload
    return {**payload, "step_purpose": node.purpose}


def _scoped_payload(node: TemplateNode, work_scope: str | None) -> dict[str, Any]:
    """The step's payload, carrying the run's task when the run has one.

    Two tasks materialized from one template would otherwise dispatch the same
    ``work_item_id`` into the same directory. The item is left EXACTLY as the
    template wrote it and the task travels beside it as ``work_scope``, which
    `harness_workspace.work_parts` turns into ``work/_tasks/<scope>/<item>`` --
    a place apart by structure. The first answer to this rewrote the item into
    one composite id, ``t<len>.<scope>.<item>``, and that id was a LEGAL legacy
    id: a task-less plan frozen before tasks existed could already carry it, and
    on a case-insensitive filesystem ``T1.a.b`` could too (the 2026-09-18
    review's R1 and R2). No spelling inside the id grammar can be apart from
    every id that grammar admits.

    A run bound to no task gets the payload untouched, byte for byte, so no
    plan written before tasks existed moves.
    """
    payload = _dispatch_payload(node)
    if work_scope is None or "work_item_id" not in payload:
        return payload
    return {**payload, "work_scope": work_scope}


def _build(template: GraphTemplate, assignments: Mapping[str, str], *,
           graph_id: str, run_id: str, created_at: str,
           work_scope: str | None = None) -> GraphDefinition:
    """Substitute roles for instances and hand the result to the base contract."""
    steps, edges = template.settled()
    nodes = tuple(
        GraphNode(
            node_id=node.node_id, kind=node.kind, title=node.title,
            stage=node.stage,
            instance_id=None if node.role_id is None else assignments[node.role_id],
            capability=node.capability, arguments=_scoped_payload(node, work_scope),
            resources=node.resources, gate_id=node.gate_id, loop=node.loop,
            # Carried across, or the plan's ceilings would be a template fact
            # the run it materializes never hears about.
            timeout_seconds=node.timeout_seconds,
            attempt_bound=node.attempt_bound, purpose=node.purpose,
            # A ROLE becomes an INSTANCE here and only here, through the same
            # assignments every other binding goes through. That is what keeps
            # the runtime adapter-agnostic: a plan names who verifies in the
            # workflow's own vocabulary, and which adapter that resolves to is
            # read from the run's frozen configuration like any other binding.
            verifier_instance_id=(
                None if node.verifier_role_id is None
                else assignments[node.verifier_role_id]),
            # Copied and not resolved. Unlike the verifier beside it this names
            # nobody: it is a demand on the verification, in the same closed
            # vocabulary both contracts share, so there is no role to substitute
            # and a run's plan carries the template's own word.
            required_evidence=node.required_evidence,
            failure_policy=node.failure_policy,
            missing_artifact_policy=node.missing_artifact_policy,
            success_requires=node.success_requires)
        for node in steps)
    return GraphDefinition(graph_id=graph_id, run_id=run_id,
                           created_at=created_at, nodes=nodes, edges=edges,
                           execution_contract=template.as_dict().get("execution_contract", _EXECUTION_ABSENT))
