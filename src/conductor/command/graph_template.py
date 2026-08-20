"""The reusable half of a graph: a plan written in ROLES, before any deployment.

``graph_definition`` owns one run's immutable plan. It names an ``instance_id``
per acting node, which is exactly right for a record that must never change --
and exactly wrong for something a person wants to keep, edit and run again
somewhere else. A template that carried an instance would be a plan that could
only ever be run on the machine it was written on.

So this module owns the other half. A ``GraphTemplate`` says what the work IS:
the steps, their topology, the gates, the bounded feedback, which capability
each acting step needs and with what arguments -- and WHO does it only as a
``role_id``, a name the template itself defines. A ``RunBinding`` says who the
roles are for one run. ``materialize`` puts the two together and produces the
existing, unchanged ``GraphDefinition``.

Two things this module refuses, and each is the point of it:

- **a field this contract does not name, at any level.** The document is
  CLOSED, so a provider, an instance, an adapter or a run's pass counter is
  refused the way any unknown key is -- there is no second by-name walk beside
  that, because a closed shape leaves one nothing to catch. What a closed shape
  cannot catch is a field ADDED under one of those names later, so
  ``DEPLOYMENT_ONLY_FIELDS`` is held against this contract's own ``_FIELDS``,
  in both directions, by ``tests/test_command_graph_template.py``.
- **a topology this product's base contract would not accept.** Rather than
  restate those rules in a second place where they could drift, a template
  PROVES itself by materializing: the constructor builds a throwaway definition
  against placeholder assignments and throws it away. A template that exists is
  therefore one that materializes, and the rules it is held to are the ones
  ``GraphDefinition`` already owns.

What it does NOT decide: whether an instance is available, and whether the
adapter behind it serves the capability a role needs. Those are the runtime's
facts, and a contract module may not ask an adapter for them -- so
``materialize`` is TOLD, through ``served``, and refuses on what it is told.
"""
from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import ContractError, _id, _take, _text, frozen_config_bindings
from .graph_definition import (
    EFFECTING_CAPABILITIES,
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
    GraphResource,
    _exact,
    _json_list,
    _json_object,
    _sequence,
)

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

    _FIELDS = frozenset({
        "node_id", "kind", "title", "stage", "role_id", "capability",
        "arguments", "resources", "gate_id", "loop",
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

    def _document(self) -> dict[str, Any]:
        """This node as data, for the walks that judge it by field name."""
        out: dict[str, Any] = {"node_id": self.node_id, "kind": self.kind,
                               "title": self.title}
        if self.stage is not None:
            out["stage"] = self.stage
        if self.role_id is not None:
            out["role_id"] = self.role_id
            out["capability"] = self.capability
            out[EXEMPT_FIELD] = self.arguments
        if self.gate_id is not None:
            out["gate_id"] = self.gate_id
        if self.loop is not None:
            out["loop"] = self.loop.as_dict()
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
        data = _json_object("template node", value)
        arguments = data.pop(EXEMPT_FIELD, None)
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
            arguments={} if arguments is None else arguments,
            resources=tuple(GraphResource.from_dict(row) for row in resources),
            gate_id=data.pop("gate_id", None),
            loop=None if loop is None else GraphLoop.from_dict(loop))


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
    schema_version: int = 1

    _FIELDS = frozenset({
        "schema_version", "template_id", "revision", "title", "nodes", "edges",
    })

    def __post_init__(self) -> None:
        object.__setattr__(self, "template_id", _id("template_id", self.template_id))
        object.__setattr__(self, "title", _text("title", self.title))
        object.__setattr__(self, "revision", _revision(self.revision))
        object.__setattr__(self, "schema_version", _exact(
            "template schema_version", self.schema_version, int))
        object.__setattr__(self, "nodes", self._settled_nodes())
        object.__setattr__(self, "edges", tuple(
            _rebuilt_edge(row) for row in _sequence("template edges", self.edges)))
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
        seen: list[str] = []
        for node in nodes:
            if node.role_id is not None and node.role_id not in seen:
                seen.append(node.role_id)
        return tuple(seen)

    @property
    def roles(self) -> tuple[str, ...]:
        """Every role this template names, in the order its nodes name them.

        One role may carry several steps -- that is the whole point of a role --
        so this is the DISTINCT set, and it is what a binding must cover.
        """
        return self._roles_of(self.nodes)

    def _probe(self) -> None:
        try:
            _build(self, {role: _PROBE_INSTANCE for role in self.roles},
                   graph_id=_PROBE_GRAPH, run_id=_PROBE_RUN, created_at=_PROBE_AT)
        except ContractError as error:
            raise TemplateError(
                f"template {self.template_id!r} does not describe a graph this "
                f"product can build: {error}") from None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "template_id": self.template_id,
            "revision": self.revision,
            "title": self.title,
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, value: object) -> "GraphTemplate":
        data = _json_object("template", value)
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
            schema_version=data.pop("schema_version", 1))


def _revision(value: object) -> int:
    number = _exact("template revision", value, int)
    if number < 1:
        raise TemplateError("a template revision starts at 1 and only goes up")
    return number


def _rebuilt_node(row: object) -> TemplateNode:
    """Take a node by IDENTITY of type and rebuild it from its attributes.

    The reason is `graph_definition`'s: `isinstance` lets a subclass answer
    `as_dict()` with a word this layer refuses, and a rebuild also re-validates
    a value edited after construction.
    """
    if type(row) is not TemplateNode:
        raise TemplateError("template nodes must be TemplateNode values")
    return TemplateNode(
        node_id=row.node_id, kind=row.kind, title=row.title, stage=row.stage,
        role_id=row.role_id, capability=row.capability, arguments=row.arguments,
        resources=row.resources, gate_id=row.gate_id, loop=row.loop)


def _rebuilt_edge(row: object) -> GraphEdge:
    if type(row) is not GraphEdge:
        raise TemplateError("template edges must be GraphEdge values")
    return GraphEdge(from_node=row.from_node, to_node=row.to_node)


@dataclass(frozen=True)
class RunBinding:
    """Who the roles are, for one run. A total map, and nothing else.

    One instance may carry several roles: a small deployment might have exactly
    one, doing all of them. What is refused is a role the template does not
    name, and a role the template names that this binding leaves out -- either
    would make a plan whose steps nobody, or somebody unnamed, carries out.
    """

    assignments: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        rows = _json_object("run binding assignments", dict(self.assignments))
        settled = {
            _id("role_id", role): _id("instance_id", instance)
            for role, instance in rows.items()
        }
        object.__setattr__(self, "assignments", settled)

    @property
    def instances(self) -> tuple[str, ...]:
        """Every distinct instance this binding uses, sorted."""
        return tuple(sorted(set(self.assignments.values())))

    def covers(self, template: GraphTemplate) -> None:
        """Refuse anything but an exact, total cover of the template's roles."""
        wanted, given = set(template.roles), set(self.assignments)
        missing, extra = sorted(wanted - given), sorted(given - wanted)
        if missing:
            raise TemplateError(
                f"binding leaves role(s) {missing!r} unassigned; every role a "
                "template names must be carried by some instance")
        if extra:
            raise TemplateError(
                f"binding assigns role(s) {extra!r} the template does not name; "
                "a binding answers for this template and no other")

    def as_dict(self) -> dict[str, Any]:
        return {"assignments": dict(sorted(self.assignments.items()))}

    @classmethod
    def from_dict(cls, value: object) -> "RunBinding":
        data = _json_object("run binding", value)
        unknown = sorted(set(data) - {"assignments"})
        if unknown:
            raise TemplateError(f"run binding carries unsupported field(s) {unknown!r}")
        return cls(assignments=_json_object(
            "run binding assignments", data.get("assignments", {})))


def _build(template: GraphTemplate, assignments: Mapping[str, str], *,
           graph_id: str, run_id: str, created_at: str) -> GraphDefinition:
    """Substitute roles for instances and hand the result to the base contract."""
    nodes = tuple(
        GraphNode(
            node_id=node.node_id, kind=node.kind, title=node.title,
            stage=node.stage,
            instance_id=None if node.role_id is None else assignments[node.role_id],
            capability=node.capability,
            arguments=node.arguments if node.role_id is not None else {},
            resources=node.resources, gate_id=node.gate_id, loop=node.loop)
        for node in template.nodes)
    return GraphDefinition(graph_id=graph_id, run_id=run_id,
                           created_at=created_at, nodes=nodes,
                           edges=template.edges)


def _servable(template: GraphTemplate, binding: RunBinding,
              bound: Mapping[str, str], served: Mapping[str, Collection[str]]) -> None:
    """Hold every role to the adapter its instance is bound to, before anything.

    Two facts, both the runtime's and neither this module's to discover: which
    adapter a frozen configuration binds an instance to, and which capabilities
    that adapter serves. They are handed in, and the refusal happens HERE --
    before a definition exists -- because a plan that reaches the journal can
    never be edited, and one whose steps no adapter can carry out would stand
    in it forever answering `service_refused` to every proposal.
    """
    for node in template.nodes:
        if node.role_id is None:
            continue
        instance = binding.assignments[node.role_id]
        adapter = bound.get(instance)
        if adapter is None:
            raise TemplateError(
                f"role {node.role_id!r} is assigned instance {instance!r}, which "
                "the run's frozen configuration does not declare")
        offered = served.get(adapter)
        if offered is None:
            raise TemplateError(
                f"instance {instance!r} is bound to adapter {adapter!r}, which "
                "this build has no available provider for")
        if node.capability not in set(offered):
            raise TemplateError(
                f"role {node.role_id!r} needs {node.capability!r} and instance "
                f"{instance!r} is bound to {adapter!r}, which does not serve it")


def materialize(template: GraphTemplate, binding: RunBinding,
                config: Mapping[str, Any],
                served: Mapping[str, Collection[str]], *,
                graph_id: str, run_id: str, created_at: str) -> GraphDefinition:
    """Turn a reusable template and one run's binding into that run's own plan.

    The order is the taxonomy, and every step of it happens before a single
    field of a durable record is written:

    1. the binding covers exactly the template's roles;
    2. every assigned instance is one the run's FROZEN configuration declares,
       which is the only authority on which adapter drives it;
    3. the adapter behind each instance really serves the capability its role
       needs, according to what this build's available providers offer;
    4. only then is the definition built -- and it is built by the existing,
       unchanged ``GraphDefinition``, which judges the topology as it always has.

    Args:
        template: The reusable plan, written in roles.
        binding: Who the roles are, for this run.
        config: The run's frozen configuration snapshot.
        served: ``{adapter_id: capabilities}`` for every AVAILABLE provider.
        graph_id: The stable identity of the plan this run will follow.
        run_id: The run the plan belongs to.
        created_at: The server's clock, never a caller's.

    Returns:
        The immutable ``GraphDefinition`` this run follows.

    Raises:
        TemplateError: The binding, an instance, or a capability was refused.
        ContractError: The materialized graph is not one this product can build.
    """
    if type(template) is not GraphTemplate:
        raise TemplateError("materialize takes exactly a GraphTemplate")
    if type(binding) is not RunBinding:
        raise TemplateError("materialize takes exactly a RunBinding")
    binding.covers(template)
    _servable(template, binding, frozen_config_bindings(config), served)
    return _build(template, binding.assignments, graph_id=graph_id,
                  run_id=run_id, created_at=created_at)


#: Where the shipped templates live. Data, not code: correcting the default
#: cycle is editing one of these files, and nothing in Python or JavaScript
#: has to move for a corrected cycle to be the one a run materializes from.
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def load_template(name: str) -> GraphTemplate:
    """Read one shipped template by name, through the same door as any other.

    It goes through ``from_dict`` exactly as an operator's own file would, so
    what ships is held to the contract rather than trusted for being ours.
    """
    if not _id("template file", name).replace("-", "").replace(".", "").isalnum():
        raise TemplateError(f"template name {name!r} is not a plain file name")
    path = TEMPLATE_DIR / f"{name}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise TemplateError(f"no shipped template named {name!r}") from error
    except json.JSONDecodeError as error:
        raise TemplateError(f"shipped template {name!r} is not JSON: {error}") from None
    return GraphTemplate.from_dict(document)
