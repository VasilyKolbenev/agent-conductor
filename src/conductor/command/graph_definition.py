"""The immutable half of a graph: what was INTENDED, never what happened.

December Command's alpha runs one graph per run, and that graph is two contracts
that never overlap. This module owns the first: the definition -- identities,
shape, stages, bindings, resources and bounded feedback. Its sibling
``graph_projection`` owns the second: what a run was OBSERVED to do.

This is the BASE contract, and it is deliberately general: an arbitrary DAG of
tasks, gates and loops, because the product exists to build different
multi-harness graphs. Dalio is the default TEMPLATE, not the only topology a
graph may have, and its extra rules -- five stages, one node each, a single
feedback loop home to identify -- live in ``graph_dalio``. Folding them in here
made every graph a Dalio graph, which is a product decision no contract should
have been able to make on its own.

The split is not tidiness. A definition that carried a pass counter, an attempt
id or an outcome would be a durable record that changes while it is being
executed, and every reader would then have to ask which copy is true. So the
words that belong to running are refused HERE, by name, at every level of the
document -- see ``RUNTIME_ONLY_FIELDS``. The refusal is what makes "immutable"
a property of the type rather than a promise in prose.

The Cockpit's panel-internal fixture is deliberately NOT this schema. That
object splices both layers together because a browser view needs them spliced;
lifting it into a durable contract would have frozen the splice. The adapter at
the wire seam maps these two contracts into that one view, which is where the
splicing belongs.

What the definition does NOT hold, and why:

- **the provider.** A node names an ``instance_id`` and a ``capability``. Which
  adapter serves that instance is a fact of the run's frozen configuration
  (``contracts.frozen_config_bindings``), and copying it here would create a
  second spelling of a vendor binding that can drift from the first.
- **the digest, as a field.** ``digest()`` is computed over this document's own
  canonical JSON. A stored digest of oneself can disagree with oneself; a
  computed one cannot.
- **arguments' inner shape.** ``arguments`` is the capability's own closed
  payload and is validated against that capability's registered schema by the
  provider door. This layer proves exactly two things about it and stops: that
  it is a JSON OBJECT, by identity of type and before anything reads it, and
  that its contents are canonical JSON data. What the keys mean is the
  capability's business, because two doors judging one value is how they come
  to disagree.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    ContractError,
    _content_digest,
    canonical_json,
    _enum,
    _extra,
    _freeze_json,
    _id,
    _json_copy,
    _raw,
    _schema,
    _take,
    _text,
    _thaw_json,
    _timestamp,
)

from .graph_conditions import settle_edge_conditions, settled_edge_condition

from .graph_values import (  # noqa: F401 -- re-exported under old names
    EXEMPT_FIELD,
    MAX_PURPOSE,
    RUNTIME_ONLY_FIELDS,
    _ABSENT,
    _exact,
    _json_list,
    _json_object,
    _positive,
    _reserved,
    _sequence,
    MAX_ACTION_SECONDS,
    MIN_LOOP_BOUND,
    MAX_LOOP_BOUND,
    POSITION_LIMIT,
    NodePosition,
    settled_bounds,
    settled_failure_policy,
    settled_missing_artifact_policy,
    settled_success_requires,
    settled_purpose,
    settled_required_evidence,
)
from .artifacts import requires_input_artifacts

#: Dalio's five stages in the ONE order the product shows them. The order is
#: part of the contract: a reader numbers the stages by index, so re-spelling
#: this tuple re-numbers the product.
DALIO_STAGES: tuple[str, ...] = ("goal", "identify", "diagnose", "design", "do")
#: The stage vocabulary is closed and product-wide; WHICH stages a graph must
#: carry, and how many nodes may claim one, is the Dalio template's business
#: (``graph_dalio``), not this contract's.
_STAGES = frozenset(DALIO_STAGES)
#: The whole step vocabulary. A cycle has exactly one sanctioned form -- a
#: ``loop`` node carrying a bound -- so no other kind may express repetition.
NODE_KINDS = frozenset({"task", "gate", "loop"})
#: Attachments a node declares it needs. Closed on purpose: an open vocabulary
#: here would become an untyped bag the wire has to carry.
RESOURCE_KINDS = frozenset({
    "model", "tool", "skill", "session", "sandbox", "filesystem",
})
MAX_RESOURCES = 16
#: The capabilities that make a node able to change the world. The runtime
#: spells this ``adapters.process.DISPATCH_CAPABILITY``; a contract module may
#: not import an adapter, so the two spellings are pinned equal by a test
#: instead of by a comment nobody executes.
EFFECTING_CAPABILITIES = frozenset({"dispatch"})

@dataclass(frozen=True)
class GraphResource:
    """One declared attachment: what kind of thing, and which one by name."""

    kind: str
    name: str

    _FIELDS = frozenset({"kind", "name"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _enum("resource kind", self.kind, RESOURCE_KINDS))
        object.__setattr__(self, "name", _id("resource name", self.name))

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "name": self.name}

    @classmethod
    def from_dict(cls, value: object) -> "GraphResource":
        data = _raw(value)
        _reserved("resource", data)
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(f"resource carries unsupported field(s) {unknown!r}")
        return cls(kind=_take(data, "kind"), name=_take(data, "name"))


@dataclass(frozen=True)
class GraphLoop:
    """The ONE sanctioned cycle: how many passes at most, and back to where.

    ``bound`` is a plan -- the greatest pass this work may reach, so a run
    standing on pass ``bound`` has no trip left. It is a ceiling on the
    position, not a count of reopenings beside it, because a screen that reads
    "pass N of B" cannot have N and B counting two different things. Which pass
    a run is on is not here and never will be: that is the projection's
    ``pass``, and the two words are kept apart so a reader can never mistake a
    ceiling for a position.
    """

    bound: int
    back_to: str

    _FIELDS = frozenset({"bound", "back_to"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "bound", _positive(
            "loop bound", self.bound, low=MIN_LOOP_BOUND, high=MAX_LOOP_BOUND))
        object.__setattr__(self, "back_to", _id("loop back_to", self.back_to))

    def as_dict(self) -> dict[str, Any]:
        return {"bound": self.bound, "back_to": self.back_to}

    @classmethod
    def from_dict(cls, value: object) -> "GraphLoop":
        data = _raw(value)
        _reserved("loop", data)
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(f"loop carries unsupported field(s) {unknown!r}")
        return cls(bound=_take(data, "bound"), back_to=_take(data, "back_to"))


@dataclass(frozen=True)
class GraphNode:
    """One step of the plan: what it is, where it runs, and what it needs."""

    node_id: str
    kind: str
    title: str
    stage: str | None = None
    instance_id: str | None = None
    capability: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict, repr=False)
    resources: tuple[GraphResource, ...] = ()
    gate_id: str | None = None
    loop: GraphLoop | None = None
    #: The longest this step's work may run, and the most attempts the plan
    #: allows it. Both are OPTIONAL and both are CEILINGS, never defaults: a
    #: node that names neither constrains neither, which is what every plan
    #: written before they existed says, and its bytes do not move.
    #:
    #: They are here rather than only on the action a Human confirms because a
    #: bound that lives only on the request is a bound the requester chooses.
    #: The plan names the ceiling; the request may ask for less and never more.
    timeout_seconds: int | None = None
    attempt_bound: int | None = None
    #: Why this step exists, as a person wrote it. Frozen into the plan so a
    #: Decision, a Run and an Inspector can all say the same sentence about the
    #: same step -- and, for a step that dispatches, carried into the frame the
    #: vendor binary is handed. It decides nothing: no traversal, no ceiling and
    #: no verdict reads it.
    purpose: str | None = None
    #: WHICH instance must confirm this step's success, when the plan names one
    #: other than the instance that does the work. Absent means the doer
    #: verifies itself, which is what every plan written before this existed
    #: says and what the runtime did unconditionally.
    #:
    #: An INSTANCE and never an adapter: the run's frozen configuration remains
    #: the only authority on which adapter drives an instance, so this changes
    #: which binding is resolved and never how one is resolved.
    verifier_instance_id: str | None = None
    #: WHAT this step's verification must name, beyond having happened. Absent
    #: means the runtime's own rule is the whole of it, which is what every plan
    #: written before this existed says and what the runtime did unconditionally.
    #:
    #: A DEMAND and never an observation: it is written by whoever drew the
    #: workflow, it names no evidence row, and it is frozen here so that the
    #: refusal it buys is the PLAN's -- held on the honest road and again
    #: against bytes this process did not write.
    required_evidence: str | None = None
    #: What happens to the REST of this run when this step fails. Absent
    #: means nothing does, which is what every plan written before this
    #: existed says. A TIGHTENING and never routing: an `on_failed` road
    #: says where the plan goes next, and this says nothing further may be
    #: authorized at all -- branches no road from here can reach included.
    failure_policy: str | None = None
    #: What happens when a document this step requires does not exist when the
    #: step is reached. Absent means `fail`, which is what this build has always
    #: done and what every plan written before this existed asks for: the input
    #: is resolved at spawn, the resolution refuses, and a durable `failed`
    #: receipt is written with no task spawned. `block` says the step is not
    #: offered at all until the document exists.
    missing_artifact_policy: str | None = None
    #: What this GATE demands of the answer that settles it. Absent means
    #: every answer this build has always allowed, `waive` included.
    #: `human_approval` says the gate may not be set aside: the server
    #: refuses a waive on it before the append, and a forged journal
    #: carrying one is refused on replay.
    success_requires: str | None = None

    _FIELDS = frozenset({
        "node_id", "kind", "title", "stage", "instance_id", "capability",
        "arguments", "resources", "gate_id", "loop", "timeout_seconds",
        "attempt_bound", "purpose", "verifier_instance_id",
        "required_evidence", "failure_policy", "missing_artifact_policy",
        "success_requires",
    })

    def __post_init__(self) -> None:
        self._settle_bounds()
        object.__setattr__(self, "purpose", settled_purpose(self.purpose))
        self._settle_verifier()
        self._settle_evidence_demand()
        self._settle_failure_policy()
        self._settle_missing_artifact_policy()
        self._settle_success_requires()
        object.__setattr__(self, "node_id", _id("node_id", self.node_id))
        object.__setattr__(self, "kind", _enum("node kind", self.kind, NODE_KINDS))
        object.__setattr__(self, "title", _text("title", self.title))
        self._settle_stage()
        self._settle_binding()
        object.__setattr__(self, "resources", self._settled_resources())
        self._settle_kind_attachments()

    def _settle_bounds(self) -> None:
        """Hold this node's two ceilings, through the one rule that owns them."""
        for name, value in settled_bounds(
                self.timeout_seconds, self.attempt_bound).items():
            object.__setattr__(self, name, value)

    def _settle_stage(self) -> None:
        """A stage is a task's optional membership, and gates and loops have none."""
        if self.kind == "task":
            if self.stage is not None:
                object.__setattr__(self, "stage", _enum("stage", self.stage, _STAGES))
        elif self.stage is not None:
            raise ContractError(
                f"{self.kind} node {self.node_id!r} must not name a stage: a stage is "
                "the work a task belongs to, not a gate or a loop")

    def _settle_verifier(self) -> None:
        """A verifier belongs to a step that has work to confirm, or to nothing.

        A gate and a loop carry nothing out, so there is no execution for a
        verifier to judge and naming one would be a field the runtime could
        never reach. Refused here rather than ignored later, for the reason the
        binding rule next door gives: a plan that stores an unreachable field is
        a plan that says something it cannot do.
        """
        if self.verifier_instance_id is None:
            return
        if self.capability is None:
            raise ContractError(
                f"node {self.node_id!r} names a verifier and no capability; a "
                "step that carries nothing out has nothing to verify")
        object.__setattr__(self, "verifier_instance_id",
                           _id("verifier_instance_id", self.verifier_instance_id))
        if self.verifier_instance_id == self.instance_id:
            raise ContractError("a step's verifier must be another participant")

    def _settle_evidence_demand(self) -> None:
        """A demand on a verification belongs to a step that produces one.

        The pairing rule next door, one field over and for the same reason: a
        gate and a loop are carried out by nobody, so no adapter ever verifies
        them and no evidence row is ever written for them. A demand on that
        verification would be a field nothing in the product could reach, and a
        plan that stores an unreachable field is a plan saying something it
        cannot do.
        """
        object.__setattr__(self, "required_evidence",
                           settled_required_evidence(self.required_evidence))
        if self.required_evidence is not None and self.capability is None:
            raise ContractError(
                f"node {self.node_id!r} requires evidence and names no "
                "capability; a step that carries nothing out is verified by "
                "nobody, so there is no verification to require anything of")

    def _settle_failure_policy(self) -> None:
        """A policy about failing belongs to a step that can fail.

        The pairing rule next door, one field over: a gate and a loop are
        carried out by nobody, so no adapter ever reports an outcome for them
        and no failure of theirs could ever fire this. A plan that stores an
        unreachable field is a plan saying something it cannot do.
        """
        object.__setattr__(self, "failure_policy",
                           settled_failure_policy(self.failure_policy))
        if self.failure_policy is not None and self.capability is None:
            raise ContractError(
                f"node {self.node_id!r} names a failure policy and no "
                "capability; a step that carries nothing out cannot fail, so "
                "there is no failure for a policy to answer")

    def _settle_missing_artifact_policy(self) -> None:
        """A policy about a missing input belongs to a step that HAS inputs.

        Tighter than the two pairing rules above, and the difference is the
        point. Those ask whether the step carries anything out at all; this asks
        whether the capability it carries out is one the reviewed schemas give
        documents to. `evidence`, `stop`, `retry` and `switch` each name an
        action or an attempt and are handed no artifact, so a policy stored on
        one of them would be a word with no behaviour -- and a person reading it
        would believe the step waits for something it is never given.

        The question is asked of `artifacts`, which owns the one map of which
        argument key each capability's inputs live under. Answering it here
        would be a second copy of that map, free to disagree with the schedule
        that spends it.
        """
        object.__setattr__(
            self, "missing_artifact_policy",
            settled_missing_artifact_policy(self.missing_artifact_policy))
        if self.missing_artifact_policy is not None and not (
                requires_input_artifacts(self.capability)):
            raise ContractError(
                f"node {self.node_id!r} names a missing-artifact policy and no "
                "capability that is given artifacts; there is no input for it "
                "to be missing")

    def _settle_success_requires(self) -> None:
        """What a GATE demands of the answer that settles it, and only a gate.

        The tightest pairing rule on this contract, and the narrowest: `waive`
        is a GATE's answer, so a demand that it may not be given is a fact about
        a gate and about nothing else. A task settles by an outcome and a loop
        by its arithmetic; neither is ever waived, so a demand stored on one
        would be a word with no behaviour, and a person reading it would believe
        the step was protected when nothing was protecting it.
        """
        object.__setattr__(self, "success_requires",
                           settled_success_requires(self.success_requires))
        if self.success_requires is not None and self.kind != "gate":
            raise ContractError(
                f"node {self.node_id!r} is a {self.kind} and names a gate "
                "success requirement; only a gate is answered by a Human, so "
                "only a gate can demand anything of that answer")

    def _settle_binding(self) -> None:
        """A binding is whole or absent; half a binding names no runnable place."""
        if (self.instance_id is None) != (self.capability is None):
            raise ContractError(
                f"node {self.node_id!r} must name an instance and a capability "
                "together or neither")
        arguments = _json_object(f"node {self.node_id} arguments", self.arguments)
        if self.instance_id is not None:
            object.__setattr__(self, "instance_id", _id("instance_id", self.instance_id))
            object.__setattr__(self, "capability", _id("capability", self.capability))
        elif arguments:
            raise ContractError(
                f"node {self.node_id!r} carries arguments with no capability to read them")
        settled = _json_copy(f"node {self.node_id} arguments", dict(arguments))
        object.__setattr__(self, "arguments", _freeze_json(settled))
        # What this contract will hand any consumer, in ITS words rather than in
        # the caller's object -- plus the exact object it stored, so a later
        # replacement can be SEEN without being READ.
        object.__setattr__(self, "_payload_text", canonical_json(settled))
        object.__setattr__(self, "_payload_witness", self.arguments)

    def _settled_resources(self) -> tuple[GraphResource, ...]:
        rows = _sequence(f"node {self.node_id} resources", self.resources)
        if len(rows) > MAX_RESOURCES:
            raise ContractError(
                f"node {self.node_id!r} declares {len(rows)} resources, more than "
                f"the {MAX_RESOURCES} this contract carries")
        rows = tuple(
            GraphResource(kind=_exact(f"node {self.node_id} resource", row,
                                      GraphResource).kind, name=row.name)
            for row in rows)
        seen = {(row.kind, row.name) for row in rows}
        if len(seen) != len(rows):
            raise ContractError(f"node {self.node_id!r} repeats a resource")
        return rows

    def _settle_kind_attachments(self) -> None:
        if self.kind == "gate":
            if self.gate_id is None:
                raise ContractError(f"gate node {self.node_id!r} must name a gate_id")
            object.__setattr__(self, "gate_id", _id("gate_id", self.gate_id))
        elif self.gate_id is not None:
            raise ContractError(f"{self.kind} node {self.node_id!r} must not name a gate_id")
        if self.kind == "loop":
            if self.loop is None:
                raise ContractError(f"loop node {self.node_id!r} must carry a GraphLoop")
            loop = _exact(f"loop node {self.node_id} loop", self.loop, GraphLoop)
            object.__setattr__(self, "loop", GraphLoop(
                bound=loop.bound, back_to=loop.back_to))
        elif self.loop is not None:
            raise ContractError(f"{self.kind} node {self.node_id!r} must not carry a loop")

    @property
    def effecting(self) -> bool:
        """Whether this node's capability can change the world."""
        return self.capability in EFFECTING_CAPABILITIES

    def payload(self) -> dict[str, Any]:
        """The validated arguments, rebuilt from this contract's own record.

        Validating at construction settles what the field WAS, not what it is:
        ``object.__setattr__`` replaces a frozen field, and every consumer that
        then read it -- ``as_dict`` here, ``_rebuilt_node`` next door -- called
        ``items`` on whatever it found. A hostile mapping answered with its own
        exception, and that exception, and whatever it carried, left as this
        contract's answer. A wrong shape was worse: it was simply thawed, so a
        node's payload stopped being an object and nobody said so.

        The replacement is caught by IDENTITY, which reads nothing at all: the
        field is either the exact object settled here or it is not. What comes
        back is parsed from the canonical text this contract wrote for itself,
        so a consumer never touches the caller's object twice.
        """
        if self.arguments is not self._payload_witness:
            raise ContractError(
                f"node {self.node_id!r} arguments were replaced after they were "
                "validated; this contract answers only for what it settled"
            ) from None
        return json.loads(self._payload_text)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "node_id": self.node_id, "kind": self.kind, "title": self.title,
            "resources": [row.as_dict() for row in self.resources],
        }
        if self.stage is not None:
            out["stage"] = self.stage
        if self.instance_id is not None:
            out["instance_id"] = self.instance_id
            out["capability"] = self.capability
            out["arguments"] = self.payload()
        if self.gate_id is not None:
            out["gate_id"] = self.gate_id
        if self.loop is not None:
            out["loop"] = self.loop.as_dict()
        # Written only when named, so a plan that constrains neither digests
        # exactly as it always did and no frozen revision moves.
        if self.timeout_seconds is not None:
            out["timeout_seconds"] = self.timeout_seconds
        if self.attempt_bound is not None:
            out["attempt_bound"] = self.attempt_bound
        if self.purpose is not None:
            out["purpose"] = self.purpose
        if self.verifier_instance_id is not None:
            out["verifier_instance_id"] = self.verifier_instance_id
        if self.required_evidence is not None:
            out["required_evidence"] = self.required_evidence
        if self.failure_policy is not None:
            out["failure_policy"] = self.failure_policy
        if self.missing_artifact_policy is not None:
            out["missing_artifact_policy"] = self.missing_artifact_policy
        if self.success_requires is not None:
            out["success_requires"] = self.success_requires
        return out

    @classmethod
    def from_dict(cls, value: object) -> "GraphNode":
        data = _raw(value)
        # The payload comes out FIRST, by its field name, so the walk that
        # follows has no exception to make and none to be fooled by.
        arguments = data.pop(EXEMPT_FIELD, _ABSENT)
        _reserved("node", data)
        unknown = sorted(set(data) - (cls._FIELDS - {EXEMPT_FIELD}))
        if unknown:
            raise ContractError(f"node carries unsupported field(s) {unknown!r}")
        loop = data.pop("loop", None)
        resources = _json_list("node resources", data.pop("resources", []))
        return cls(
            node_id=_take(data, "node_id"), kind=_take(data, "kind"),
            title=_take(data, "title"), stage=data.pop("stage", None),
            instance_id=data.pop("instance_id", None),
            capability=data.pop("capability", None),
            arguments={} if arguments is _ABSENT else arguments,
            resources=tuple(GraphResource.from_dict(row) for row in resources),
            gate_id=data.pop("gate_id", None),
            loop=None if loop is None else GraphLoop.from_dict(loop),
            timeout_seconds=data.pop("timeout_seconds", None),
            attempt_bound=data.pop("attempt_bound", None),
            purpose=data.pop("purpose", None),
            verifier_instance_id=data.pop("verifier_instance_id", None),
            required_evidence=data.pop("required_evidence", None),
            failure_policy=data.pop("failure_policy", None),
            missing_artifact_policy=data.pop("missing_artifact_policy", None),
            success_requires=data.pop("success_requires", None))


@dataclass(frozen=True)
class GraphEdge:
    """One directed dependency. Edges are a DAG; feedback lives in a loop."""

    from_node: str
    to_node: str
    #: WHEN this road opens, as one word the step behind it can produce.
    #: Absent means unconditional, which is what every plan written before
    #: conditions existed says: the road opens once that step has settled. The
    #: grammar and the document rules are `graph_conditions`' own.
    condition: str | None = None

    _FIELDS = frozenset({"from_node", "to_node", "condition"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_node", _id("edge from_node", self.from_node))
        object.__setattr__(self, "to_node", _id("edge to_node", self.to_node))
        object.__setattr__(self, "condition",
                           settled_edge_condition(self.condition))
        if self.from_node == self.to_node:
            raise ContractError(f"edge {self.from_node!r} names itself on both ends")

    def as_dict(self) -> dict[str, Any]:
        out = {"from_node": self.from_node, "to_node": self.to_node}
        # Written only when named, so an unconditional road digests exactly as
        # it always did and no frozen revision moves.
        if self.condition is not None:
            out["condition"] = self.condition
        return out

    @classmethod
    def from_dict(cls, value: object) -> "GraphEdge":
        data = _raw(value)
        _reserved("edge", data)
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(f"edge carries unsupported field(s) {unknown!r}")
        return cls(from_node=_take(data, "from_node"), to_node=_take(data, "to_node"),
                   condition=data.pop("condition", None))


def _rebuilt_node(row: object) -> "GraphNode":
    """Take a node's declared facts through the base constructor once more.

    Exact typing stops a subclass from answering for itself; rebuilding stops a
    value that was edited AFTER it was validated, because every field goes back
    through ``__post_init__``. Fields are read as attributes rather than through
    ``as_dict``, so nothing polymorphic is consulted -- except that reading the
    payload attribute WAS the polymorphic act, which is why the payload comes
    from ``payload()``, which sees a replacement by identity and reads it never.
    """
    node = _exact("graph node", row, GraphNode)
    return GraphNode(
        node_id=node.node_id, kind=node.kind, title=node.title, stage=node.stage,
        instance_id=node.instance_id, capability=node.capability,
        arguments=node.payload(), resources=node.resources,
        gate_id=node.gate_id, loop=node.loop,
        timeout_seconds=node.timeout_seconds,
        attempt_bound=node.attempt_bound, purpose=node.purpose,
        verifier_instance_id=node.verifier_instance_id,
        required_evidence=node.required_evidence,
        failure_policy=node.failure_policy,
        missing_artifact_policy=node.missing_artifact_policy,
        success_requires=node.success_requires)


def _acyclic(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...]) -> None:
    """Prove the edge set is a DAG; the one sanctioned cycle is not an edge."""
    outgoing: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for edge in edges:
        outgoing[edge.from_node].append(edge.to_node)
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(outgoing, WHITE)
    for root in outgoing:
        if colour[root] != WHITE:
            continue
        stack = [(root, iter(outgoing[root]))]
        colour[root] = GREY
        while stack:
            node, children = stack[-1]
            following = next(children, None)
            if following is None:
                colour[node] = BLACK
                stack.pop()
            elif colour[following] == GREY:
                raise ContractError(
                    f"edges form a cycle through {following!r}; the only feedback a "
                    "graph may express is a loop node's bounded back_to")
            elif colour[following] == WHITE:
                colour[following] = GREY
                stack.append((following, iter(outgoing[following])))
    return None


@dataclass(frozen=True)
class GraphDefinition:
    """One run's immutable plan: written once, digested, and never edited."""

    graph_id: str
    run_id: str
    created_at: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...] = ()
    schema_version: int = 2
    extra: Mapping[str, Any] = field(default_factory=dict, repr=False)

    _FIELDS = frozenset({
        "schema_version", "graph_id", "run_id", "created_at", "nodes", "edges",
    })

    def __post_init__(self) -> None:
        object.__setattr__(self, "graph_id", _id("graph_id", self.graph_id))
        object.__setattr__(self, "run_id", _id("run_id", self.run_id))
        object.__setattr__(self, "created_at", _timestamp("created_at", self.created_at))
        object.__setattr__(self, "schema_version", _schema(self.schema_version))
        object.__setattr__(self, "extra", _extra(self.extra, self._FIELDS))
        _reserved("graph", self.extra)
        object.__setattr__(self, "nodes", self._settled_nodes())
        object.__setattr__(self, "edges", self._settled_edges())
        settle_edge_conditions(self.nodes, self.edges)
        _acyclic(self.nodes, self.edges)
        self._settle_loops()
        self._settle_effect_roads()

    def _settled_nodes(self) -> tuple[GraphNode, ...]:
        rows = _sequence("graph nodes", self.nodes)
        if not rows:
            raise ContractError("a graph definition must carry at least one node")
        rows = tuple(_rebuilt_node(row) for row in rows)
        if len({row.node_id for row in rows}) != len(rows):
            raise ContractError("graph nodes must not repeat a node_id")
        gates = [row.gate_id for row in rows if row.gate_id is not None]
        if len(set(gates)) != len(gates):
            raise ContractError("graph gates must not repeat a gate_id")
        return rows

    def _settled_edges(self) -> tuple[GraphEdge, ...]:
        rows = tuple(
            GraphEdge(from_node=_exact("graph edge", row, GraphEdge).from_node,
                      to_node=row.to_node, condition=row.condition)
            for row in _sequence("graph edges", self.edges))
        known = {row.node_id for row in self.nodes}
        for edge in rows:
            missing = {edge.from_node, edge.to_node} - known
            if missing:
                raise ContractError(f"edge names unknown node(s) {sorted(missing)!r}")
        pairs = {(row.from_node, row.to_node) for row in rows}
        if len(pairs) != len(rows):
            raise ContractError("graph edges must not repeat a from/to pair")
        return rows

    def _settle_loops(self) -> None:
        """A loop may reopen any node this graph carries, and only one it does."""
        for node in self.nodes:
            if node.loop is None:
                continue
            if node.loop.back_to not in {row.node_id for row in self.nodes}:
                raise ContractError(
                    f"loop {node.node_id!r} reopens {node.loop.back_to!r}, which this "
                    "graph does not carry")
            if node.loop.back_to == node.node_id:
                raise ContractError(
                    f"loop {node.node_id!r} reopens itself; a loop sends work back to "
                    "the step that redoes it, and the Cockpit reads a self-target as "
                    "a corrupt graph")

    def _settle_effect_roads(self) -> None:
        """Every node that can act is reached, and only ever through a gate.

        This is a property of ACTING, not of a template: whichever nodes a graph
        binds to an effecting capability, each of them stands behind a gate. A
        graph may have none, one, or several.
        """
        gates = {node.node_id for node in self.nodes if node.kind == "gate"}
        for node in self.nodes:
            if not node.effecting:
                continue
            approaches = [edge.from_node for edge in self.edges
                          if edge.to_node == node.node_id]
            if not approaches:
                raise ContractError(
                    f"{node.node_id!r} can act and no road reaches it; an "
                    "effect-capable step stands behind its gate, not beside it")
            ungated = sorted(set(approaches) - gates)
            if ungated:
                raise ContractError(
                    f"node(s) {ungated!r} reach {node.node_id!r} without a gate; an "
                    "effect-capable step is entered through a Human gate or not at all")

    def stages(self) -> dict[str, tuple[str, ...]]:
        """Which nodes claim each stage; a stage may be shared or absent."""
        claimed: dict[str, list[str]] = {}
        for node in self.nodes:
            if node.stage is not None:
                claimed.setdefault(node.stage, []).append(node.node_id)
        return {stage: tuple(names) for stage, names in claimed.items()}

    def stage_node(self, stage: str) -> GraphNode:
        """The one node claiming a stage; refuses when none or several do."""
        claiming = [node for node in self.nodes if node.stage == stage]
        if len(claiming) != 1:
            raise ContractError(
                f"graph carries {len(claiming)} nodes for stage {stage!r}; ask "
                "stages() when a graph may share or omit one")
        return claiming[0]

    def digest(self) -> str:
        """The canonical digest of this definition, computed and never stored."""
        return _content_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        out = _thaw_json(self.extra)
        out.update({
            "schema_version": self.schema_version, "graph_id": self.graph_id,
            "run_id": self.run_id, "created_at": self.created_at,
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
        })
        return out

    @classmethod
    def from_dict(cls, value: object) -> "GraphDefinition":
        data = _raw(value)
        known = {name: data.pop(name) for name in list(data) if name in cls._FIELDS}
        _reserved("graph", data)
        nodes = _json_list("graph nodes", _take(known, "nodes"))
        edges = _json_list("graph edges", known.pop("edges", []))
        return cls(
            graph_id=_take(known, "graph_id"), run_id=_take(known, "run_id"),
            created_at=_take(known, "created_at"),
            nodes=tuple(GraphNode.from_dict(row) for row in nodes),
            edges=tuple(GraphEdge.from_dict(row) for row in edges),
            schema_version=known.pop("schema_version", 2), extra=data)
