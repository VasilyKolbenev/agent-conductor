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

What it does NOT decide: whether the adapter behind an instance can actually
DO the work a role needs. That question already has ONE authority in this
product -- the bound adapter, the schema family it serves a capability
through, and the registry-owned ``validate_arguments`` -- and a contract
module may not ask a registry anything.

It was briefly answered here anyway, from a ``served`` mapping of
``{adapter_id: capabilities}`` the caller supplied. That made a dictionary a
second authority over a fact the registry owns: a capability name nobody
validated, no argument schema, no family, and a synthetic provider that
satisfied the whole check with no registry in the room. A second authority
that can disagree with the first is worse than none, so the verdict moved to
the service and HTTP layer, which may ask.

One claim is RETIRED rather than relocated, and it should be read as a
decision rather than an oversight: ``served``'s "this build has no available
provider for that adapter" was about AVAILABILITY, which ``AdapterRegistry``
has no concept of -- an adapter can be registered while its provider is
unavailable. Availability re-enters through ``provider_projection``, at the
layer that can see it.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
        self._settle_arguments()

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
    schema_version: int = SCHEMA_VERSION

    _FIELDS = frozenset({
        "schema_version", "template_id", "revision", "title", "nodes", "edges",
    })

    def __post_init__(self) -> None:
        object.__setattr__(self, "template_id", _id("template_id", self.template_id))
        object.__setattr__(self, "title", _text("title", self.title))
        object.__setattr__(self, "revision", _revision(self.revision))
        object.__setattr__(self, "schema_version", _schema_spoken(self.schema_version))
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
            _build(self, {role: _PROBE_INSTANCE for role in self.roles},
                   graph_id=_PROBE_GRAPH, run_id=_PROBE_RUN, created_at=_PROBE_AT)
        except ContractError as error:
            raise TemplateError(
                f"template {self.template_id!r} does not describe a graph this "
                f"product can build: {error}") from None

    def _document(self) -> dict[str, Any]:
        """This template as data, built once at construction and never again."""
        return {
            "schema_version": self.schema_version,
            "template_id": self.template_id,
            "revision": self.revision,
            "title": self.title,
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
        }

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
            schema_version=data.pop("schema_version", SCHEMA_VERSION))


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
        # The raw value, and `_json_object` FIRST. Calling `dict(...)` on it
        # first ran the caller's own `keys` before anything had judged it, so a
        # hostile mapping's exception left as this contract's answer -- and a
        # `dict` subclass was laundered into a plain one rather than refused,
        # which is the same door `graph_definition` shuts for the same reason.
        rows = _json_object("run binding assignments", self.assignments)
        settled = {
            _id("role_id", role): _id("instance_id", instance)
            for role, instance in sorted(rows.items())
        }
        # Frozen, not merely rebuilt. A plain dict handed back is one a caller
        # edits in place -- and `covers` reads the role KEYS, so swapping the
        # instance a role runs on passed every check this contract makes.
        object.__setattr__(self, "assignments", _freeze_json(settled))
        object.__setattr__(self, "_assignments_text", canonical_json(settled))
        object.__setattr__(self, "_assignments_witness", self.assignments)

    def bound(self) -> dict[str, str]:
        """The assignments this contract settled, rebuilt from its own record.

        The same identity check the nodes carry, for the same reason: a mapping
        put here afterwards answers `items` however it likes, and this contract
        would have reported whatever it answered as the binding a run follows.
        """
        if self.assignments is not self._assignments_witness:
            raise TemplateError(
                "run binding assignments were replaced after they were "
                "validated; this contract answers only for what it settled"
            ) from None
        return json.loads(self._assignments_text)

    @property
    def instances(self) -> tuple[str, ...]:
        """Every distinct instance this binding uses, sorted."""
        return tuple(sorted(set(self.bound().values())))

    def covers(self, template: GraphTemplate) -> None:
        """Refuse anything but an exact, total cover of the template's roles."""
        wanted, given = set(template.roles), set(self.bound())
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
        return {"assignments": self.bound()}

    @classmethod
    def from_dict(cls, value: object) -> "RunBinding":
        data = dict(_json_object("run binding", value))
        unknown = sorted(set(data) - {"assignments"})
        if unknown:
            raise TemplateError(f"run binding carries unsupported field(s) {unknown!r}")
        return cls(assignments=_json_object(
            "run binding assignments", data.get("assignments", {})))


def _build(template: GraphTemplate, assignments: Mapping[str, str], *,
           graph_id: str, run_id: str, created_at: str) -> GraphDefinition:
    """Substitute roles for instances and hand the result to the base contract."""
    steps, edges = template.settled()
    nodes = tuple(
        GraphNode(
            node_id=node.node_id, kind=node.kind, title=node.title,
            stage=node.stage,
            instance_id=None if node.role_id is None else assignments[node.role_id],
            capability=node.capability, arguments=node.payload(),
            resources=node.resources, gate_id=node.gate_id, loop=node.loop)
        for node in steps)
    return GraphDefinition(graph_id=graph_id, run_id=run_id,
                           created_at=created_at, nodes=nodes, edges=edges)


def _declared(binding: RunBinding, bound: Mapping[str, str]) -> None:
    """Every assigned instance is one the run's FROZEN configuration declares.

    The one fact about a deployment this module may hold, and it holds it from
    the configuration snapshot the run already replays -- not from a caller's
    say-so. Which capabilities an adapter actually serves is a different kind
    of fact, and it is no longer asked here at all: see `materialize`.
    """
    for role, instance in sorted(binding.bound().items()):
        if instance not in bound:
            raise TemplateError(
                f"role {role!r} is assigned instance {instance!r}, which "
                "the run's frozen configuration does not declare")


def materialize(template: GraphTemplate, binding: RunBinding,
                config: Mapping[str, Any], *,
                graph_id: str, run_id: str, created_at: str) -> GraphDefinition:
    """Turn a reusable template and one run's binding into that run's own plan.

    Three steps, and all of them happen before a single field of a durable
    record is written:

    1. the binding covers exactly the template's roles;
    2. every assigned instance is one the run's FROZEN configuration declares,
       which is the only authority on which adapter drives it;
    3. only then is the definition built -- and it is built by the existing,
       unchanged ``GraphDefinition``, which judges the topology as it always has.

    Whether an adapter can DO the work is not decided here, and used to be;
    the module docstring says why not, and where that verdict lives now.

    Args:
        template: The reusable plan, written in roles.
        binding: Who the roles are, for this run.
        config: The run's frozen configuration snapshot.
        graph_id: The stable identity of the plan this run will follow.
        run_id: The run the plan belongs to.
        created_at: The server's clock, never a caller's.

    Returns:
        The immutable ``GraphDefinition`` this run follows.

    Raises:
        TemplateError: The binding or an instance was refused.
        ContractError: The materialized graph is not one this product can build.
    """
    if type(template) is not GraphTemplate:
        raise TemplateError("materialize takes exactly a GraphTemplate")
    if type(binding) is not RunBinding:
        raise TemplateError("materialize takes exactly a RunBinding")
    binding.covers(template)
    _declared(binding, frozen_config_bindings(config))
    return _build(template, binding.bound(), graph_id=graph_id,
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
    except OSError:
        # `from None`, and the OSError is not bound at all. Its `str` carries
        # the FULL path it failed on -- `TEMPLATE_DIR` joined with whatever the
        # caller asked for -- so chaining it printed this server's directory
        # layout under any traceback or error-reporting boundary. The name the
        # caller already knows is the whole of what this refusal owes them.
        raise TemplateError(f"no shipped template named {name!r}") from None
    except json.JSONDecodeError as error:
        raise TemplateError(f"shipped template {name!r} is not JSON: {error}") from None
    return GraphTemplate.from_dict(document)
