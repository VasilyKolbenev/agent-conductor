"""The immutable half of a graph: what was INTENDED, never what happened.

December Command's alpha runs one graph per run, and that graph is two contracts
that never overlap. This module owns the first: the definition -- identities,
shape, stages, bindings, resources and the one bounded feedback relation. Its
sibling ``graph_projection`` owns the second: what a run was OBSERVED to do.

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
  provider door. This layer proves it is canonical JSON data and nothing more,
  because two doors judging one value is how they come to disagree.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    ContractError,
    _content_digest,
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

#: Dalio's five stages in the ONE order the product shows them. The order is
#: part of the contract: a reader numbers the stages by index, so re-spelling
#: this tuple re-numbers the product.
DALIO_STAGES: tuple[str, ...] = ("goal", "identify", "diagnose", "design", "do")
_STAGES = frozenset(DALIO_STAGES)
#: The stage a bounded loop may send work back to, and the only one.
FEEDBACK_STAGE = "identify"
#: The stage that owns the single effect-capable node.
EFFECT_STAGE = "do"
#: The whole step vocabulary. A cycle has exactly one sanctioned form -- a
#: ``loop`` node carrying a bound -- so no other kind may express repetition.
NODE_KINDS = frozenset({"task", "gate", "loop"})
#: Attachments a node declares it needs. Closed on purpose: an open vocabulary
#: here would become an untyped bag the wire has to carry.
RESOURCE_KINDS = frozenset({
    "model", "tool", "skill", "session", "sandbox", "filesystem",
})
MAX_RESOURCES = 16
MIN_LOOP_BOUND, MAX_LOOP_BOUND = 1, 99
#: The capabilities that make a node able to change the world. The runtime
#: spells this ``adapters.process.DISPATCH_CAPABILITY``; a contract module may
#: not import an adapter, so the two spellings are pinned equal by a test
#: instead of by a comment nobody executes.
EFFECTING_CAPABILITIES = frozenset({"dispatch"})
#: Every word that belongs to a RUN rather than to a plan. Refused as a field
#: name anywhere in this document, at every level, so no amount of nesting can
#: smuggle execution state into something called immutable. ``arguments`` is
#: exempt by design: it is the capability's own payload, judged by the
#: capability's own schema at the provider door.
RUNTIME_ONLY_FIELDS = frozenset({
    "attempt_id", "attempt_ids", "attempts", "availability", "bound_reached",
    "decided_at", "decision", "decisions", "evidence", "evidence_refs",
    "health", "observed_at", "outcome", "outcomes", "pass", "passes", "phase",
    "started_at", "state", "status", "timeline",
})


def _reserved(name: str, document: Mapping[str, Any]) -> None:
    """Refuse a runtime word used as a field name, at any depth."""
    found = sorted(set(document) & RUNTIME_ONLY_FIELDS)
    if found:
        raise ContractError(
            f"{name} carries runtime-only field(s) {found!r}; a graph definition "
            "records intent, and what a run did belongs to its projection")


def _positive(name: str, value: object, *, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{name} must be an integer, got {value!r}")
    if not low <= value <= high:
        raise ContractError(f"{name} must be between {low} and {high}, got {value}")
    return value


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

    ``bound`` is a plan -- how many times this work may be reopened. Which pass
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

    _FIELDS = frozenset({
        "node_id", "kind", "title", "stage", "instance_id", "capability",
        "arguments", "resources", "gate_id", "loop",
    })

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _id("node_id", self.node_id))
        object.__setattr__(self, "kind", _enum("node kind", self.kind, NODE_KINDS))
        object.__setattr__(self, "title", _text("title", self.title))
        self._settle_stage()
        self._settle_binding()
        object.__setattr__(self, "resources", self._settled_resources())
        self._settle_kind_attachments()

    def _settle_stage(self) -> None:
        if self.kind == "task":
            if self.stage is None:
                raise ContractError(f"task node {self.node_id!r} must name a stage")
            object.__setattr__(self, "stage", _enum("stage", self.stage, _STAGES))
        elif self.stage is not None:
            raise ContractError(
                f"{self.kind} node {self.node_id!r} must not name a stage: a stage is "
                "the work a task belongs to, not a gate or a loop")

    def _settle_binding(self) -> None:
        """A binding is whole or absent; half a binding names no runnable place."""
        if (self.instance_id is None) != (self.capability is None):
            raise ContractError(
                f"node {self.node_id!r} must name an instance and a capability "
                "together or neither")
        if self.instance_id is not None:
            object.__setattr__(self, "instance_id", _id("instance_id", self.instance_id))
            object.__setattr__(self, "capability", _id("capability", self.capability))
        elif self.arguments:
            raise ContractError(
                f"node {self.node_id!r} carries arguments with no capability to read them")
        object.__setattr__(self, "arguments", _freeze_json(
            _json_copy(f"node {self.node_id} arguments", dict(self.arguments))))

    def _settled_resources(self) -> tuple[GraphResource, ...]:
        rows = tuple(self.resources)
        if len(rows) > MAX_RESOURCES:
            raise ContractError(
                f"node {self.node_id!r} declares {len(rows)} resources, more than "
                f"the {MAX_RESOURCES} this contract carries")
        if any(not isinstance(row, GraphResource) for row in rows):
            raise ContractError(f"node {self.node_id!r} resources must be GraphResource")
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
            if not isinstance(self.loop, GraphLoop):
                raise ContractError(f"loop node {self.node_id!r} must carry a GraphLoop")
        elif self.loop is not None:
            raise ContractError(f"{self.kind} node {self.node_id!r} must not carry a loop")

    @property
    def effecting(self) -> bool:
        """Whether this node's capability can change the world."""
        return self.capability in EFFECTING_CAPABILITIES

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
            out["arguments"] = _thaw_json(self.arguments)
        if self.gate_id is not None:
            out["gate_id"] = self.gate_id
        if self.loop is not None:
            out["loop"] = self.loop.as_dict()
        return out

    @classmethod
    def from_dict(cls, value: object) -> "GraphNode":
        data = _raw(value)
        _reserved("node", data)
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(f"node carries unsupported field(s) {unknown!r}")
        loop = data.pop("loop", None)
        resources = data.pop("resources", ())
        if isinstance(resources, (str, bytes)) or not isinstance(resources, (list, tuple)):
            raise ContractError("node resources must be a list")
        return cls(
            node_id=_take(data, "node_id"), kind=_take(data, "kind"),
            title=_take(data, "title"), stage=data.pop("stage", None),
            instance_id=data.pop("instance_id", None),
            capability=data.pop("capability", None),
            arguments=data.pop("arguments", {}) or {},
            resources=tuple(GraphResource.from_dict(row) for row in resources),
            gate_id=data.pop("gate_id", None),
            loop=None if loop is None else GraphLoop.from_dict(loop))


@dataclass(frozen=True)
class GraphEdge:
    """One directed dependency. Edges are a DAG; feedback lives in a loop."""

    from_node: str
    to_node: str

    _FIELDS = frozenset({"from_node", "to_node"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_node", _id("edge from_node", self.from_node))
        object.__setattr__(self, "to_node", _id("edge to_node", self.to_node))
        if self.from_node == self.to_node:
            raise ContractError(f"edge {self.from_node!r} names itself on both ends")

    def as_dict(self) -> dict[str, Any]:
        return {"from_node": self.from_node, "to_node": self.to_node}

    @classmethod
    def from_dict(cls, value: object) -> "GraphEdge":
        data = _raw(value)
        _reserved("edge", data)
        unknown = sorted(set(data) - cls._FIELDS)
        if unknown:
            raise ContractError(f"edge carries unsupported field(s) {unknown!r}")
        return cls(from_node=_take(data, "from_node"), to_node=_take(data, "to_node"))


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
        _acyclic(self.nodes, self.edges)
        self._settle_dalio()
        self._settle_effect_road()

    def _settled_nodes(self) -> tuple[GraphNode, ...]:
        rows = tuple(self.nodes)
        if not rows:
            raise ContractError("a graph definition must carry at least one node")
        if any(not isinstance(row, GraphNode) for row in rows):
            raise ContractError("graph nodes must be GraphNode")
        if len({row.node_id for row in rows}) != len(rows):
            raise ContractError("graph nodes must not repeat a node_id")
        gates = [row.gate_id for row in rows if row.gate_id is not None]
        if len(set(gates)) != len(gates):
            raise ContractError("graph gates must not repeat a gate_id")
        return rows

    def _settled_edges(self) -> tuple[GraphEdge, ...]:
        rows = tuple(self.edges)
        if any(not isinstance(row, GraphEdge) for row in rows):
            raise ContractError("graph edges must be GraphEdge")
        known = {row.node_id for row in self.nodes}
        for edge in rows:
            missing = {edge.from_node, edge.to_node} - known
            if missing:
                raise ContractError(f"edge names unknown node(s) {sorted(missing)!r}")
        pairs = {(row.from_node, row.to_node) for row in rows}
        if len(pairs) != len(rows):
            raise ContractError("graph edges must not repeat a from/to pair")
        return rows

    def _settle_dalio(self) -> None:
        """Five stages, one node each, and one bounded way back to identify."""
        staged: dict[str, str] = {}
        for node in self.nodes:
            if node.stage is None:
                continue
            if node.stage in staged:
                raise ContractError(
                    f"stage {node.stage!r} is claimed by both {staged[node.stage]!r} "
                    f"and {node.node_id!r}; a graph carries one node per stage")
            staged[node.stage] = node.node_id
        missing = [stage for stage in DALIO_STAGES if stage not in staged]
        if missing:
            raise ContractError(f"graph is missing stage node(s) {missing!r}")
        loops = [node for node in self.nodes if node.loop is not None]
        if len(loops) > 1:
            raise ContractError(
                "a graph carries at most one loop; a second controlled feedback "
                "relation is a second cycle by another name")
        for node in loops:
            assert node.loop is not None
            if node.loop.back_to != staged[FEEDBACK_STAGE]:
                raise ContractError(
                    f"loop {node.node_id!r} sends work back to "
                    f"{node.loop.back_to!r}; the one feedback relation this product "
                    f"holds returns to the {FEEDBACK_STAGE!r} stage node "
                    f"{staged[FEEDBACK_STAGE]!r}")

    def _settle_effect_road(self) -> None:
        """One node may act, and only a gate may let work reach it."""
        effecting = [node.node_id for node in self.nodes if node.effecting]
        do_node = self.stage_node(EFFECT_STAGE)
        stray = [name for name in effecting if name != do_node.node_id]
        if stray:
            raise ContractError(
                f"node(s) {stray!r} carry an effecting capability; only the "
                f"{EFFECT_STAGE!r} stage node may change the world")
        gates = {node.node_id for node in self.nodes if node.kind == "gate"}
        approaches = [edge.from_node for edge in self.edges
                      if edge.to_node == do_node.node_id]
        ungated = sorted(set(approaches) - gates)
        if ungated:
            raise ContractError(
                f"node(s) {ungated!r} reach {do_node.node_id!r} without a gate; the "
                "effect-capable step is entered through a Human gate or not at all")
        if not approaches:
            raise ContractError(
                f"{do_node.node_id!r} is reachable from nowhere; the effect-capable "
                "step must stand behind its gate, not beside it")

    def stage_node(self, stage: str) -> GraphNode:
        """The one node that owns a stage; stages are unique by construction."""
        for node in self.nodes:
            if node.stage == stage:
                return node
        raise ContractError(f"graph carries no node for stage {stage!r}")

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
        nodes = _take(known, "nodes")
        edges = known.pop("edges", ())
        for name, rows in (("nodes", nodes), ("edges", edges)):
            if isinstance(rows, (str, bytes)) or not isinstance(rows, (list, tuple)):
                raise ContractError(f"graph {name} must be a list")
        return cls(
            graph_id=_take(known, "graph_id"), run_id=_take(known, "run_id"),
            created_at=_take(known, "created_at"),
            nodes=tuple(GraphNode.from_dict(row) for row in nodes),
            edges=tuple(GraphEdge.from_dict(row) for row in edges),
            schema_version=known.pop("schema_version", 2), extra=data)
