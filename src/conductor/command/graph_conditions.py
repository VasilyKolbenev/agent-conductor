"""What an edge may say about WHEN it opens, and every rule about saying it.

An edge without a condition is a dependency: the road opens once the step
before it has settled. That is what every plan written before this module says,
and it is why the field is optional and written only when named -- no stored
document moves a byte and no digest moves with it.

A CONDITION narrows that road to one of the words the step before it can
actually produce. The vocabulary is closed, it is one word per road, and there
is deliberately no operator, no comparison and no expression anywhere in it: a
plan that could carry an expression would be a small language, and a small
language in a durable document is a second place where what a run does is
decided. Eight words, four families, one word each, and a step produces exactly
one of them.

This is its own module for the reason `graph_values` and `graph_causality` next
door are theirs: `graph_definition` is near its line cap, and this is a
self-contained circuit -- one vocabulary, the grammar of one field, and the five
document rules that decide whether a set of conditions could ever be true. It
imports no node contract, so `_CONDITIONS_BY_KIND` spells the three kind words
rather than importing `NODE_KINDS` (the reverse would be a cycle); a test holds
the two equal in both directions, which is what `graph_values` already does for
`MAX_ACTION_SECONDS`.

The rules here refuse a plan that is DEAD rather than merely unusual. Two
out-edges under one condition are fan-out and are fine. One conditional and one
unconditional out-edge is an author who meant *otherwise* and had no way to say
it, and inferring a default for them would be a free expression by another name.
A condition naming a word its source cannot produce is a road no run could ever
travel -- and a provably dead step is the defect this vocabulary exists to make
impossible.

**A step reached from ONE source on two different words needs no rule here**,
and deliberately has none. Under AND-only joins both roads would have to open
while the source produces exactly one word, so the shape is dead -- but
`GraphDefinition._settled_edges` already refuses a repeated `from`/`to` pair
outright, whatever either edge says, and `GraphTemplate` refuses it through the
same door. There is no way to build the shape, so a guard against it could
never be shown to fail, and a guard nobody can drive is worse than the rule it
duplicates. `tests/test_command_edge_conditions.py` holds that road closed in
both spellings.
"""
from __future__ import annotations

from types import MappingProxyType

from .contract_values import ContractError

#: The whole condition vocabulary: four gate words, two task words, two loop
#: words. Closed, and closed in both directions -- a test holds it equal to the
#: union of `_CONDITIONS_BY_KIND`, so a word cannot be added to one alone.
EDGE_CONDITIONS = frozenset({
    "on_approved", "on_rejected", "on_changes_requested", "on_waived",
    "on_succeeded", "on_failed",
    "on_bound_reached", "on_bound_remaining",
})

#: Which words each kind of step can produce. `MappingProxyType` follows
#: `deep_commands.DEEP_ARGUMENT_TYPES`: the map is a contract, and a contract a
#: caller can edit in place is not one. A capability-less task is a task by kind
#: and produces NO word at all, which is a rule about the node rather than about
#: its kind and lives in `settle_edge_conditions` below.
_CONDITIONS_BY_KIND = MappingProxyType({
    "gate": frozenset({
        "on_approved", "on_rejected", "on_changes_requested", "on_waived"}),
    "task": frozenset({"on_succeeded", "on_failed"}),
    "loop": frozenset({"on_bound_reached", "on_bound_remaining"}),
})


def settled_edge_condition(value: object) -> str | None:
    """One grammar for an edge's condition, judged the same in draft and plan.

    Here for `settled_purpose`'s reason one module over: a template that stored
    a word the definition would refuse is a plan that cannot materialize, found
    out at run time rather than where it was drawn. `GraphEdge` is one contract
    shared by the template, the draft and the definition, so this runs once for
    all three.

    Absent stays absent, and so does whitespace -- an empty string is the same
    answer as saying nothing, which is what a Studio select spells when a person
    clears it -- so no document written before this field existed changes a byte
    or moves a digest.

    Args:
        value: What the document says about when this road opens.

    Returns:
        The settled word, or None when the road is unconditional.

    Raises:
        ContractError: The value is not text, or is not one of
            `EDGE_CONDITIONS`.
    """
    if value is None:
        return None
    if type(value) is not str:
        raise ContractError(
            "an edge condition is text, or nothing at all")
    settled = value.strip()
    if not settled:
        return None
    if settled not in EDGE_CONDITIONS:
        raise ContractError(
            f"an edge opens on one of {sorted(EDGE_CONDITIONS)}, and "
            f"{settled!r} is not one of them; a condition names a word a step "
            "produces, never an expression over one")
    return settled


def settle_edge_conditions(nodes, edges) -> None:
    """Refuse a set of conditions no run could ever satisfy.

    Run after both ends of every edge are known to name a node and before the
    graph is walked: reading a source's kind needs the first, and refusing
    nonsense before a traversal is what keeps the traversal's own refusals
    about shape.

    Args:
        nodes: The graph's settled nodes, in document order.
        edges: The graph's settled edges, in document order.

    Raises:
        ContractError: A condition names a word its source cannot produce, or a
            source mixes conditional and unconditional roads.
    """
    sources = {node.node_id: node for node in nodes}
    for edge in edges:
        _settle_source_can_say_it(sources[edge.from_node], edge)
    _settle_no_mixed_roads(edges)


def _settle_source_can_say_it(source, edge) -> None:
    """A road opens on a word the step behind it actually produces."""
    if edge.condition is None:
        return
    if edge.condition not in _CONDITIONS_BY_KIND[source.kind]:
        raise ContractError(
            f"edge {edge.from_node!r}->{edge.to_node!r} carries condition "
            f"{edge.condition!r}, which a {source.kind} node cannot produce")
    if source.kind == "task" and source.capability is None:
        raise ContractError(
            f"node {source.node_id!r} carries out no work, so no condition it "
            "names could ever be produced")


def _settle_no_mixed_roads(edges) -> None:
    """One source names a condition on every road out of it, or on none.

    One conditional and one unconditional out-edge is an author who meant
    *otherwise* and had no way to say it. Reading the unconditional road as a
    default would be this contract deciding what a plan meant, which is a free
    expression by another name.
    """
    named: dict[str, set[bool]] = {}
    for edge in edges:
        named.setdefault(edge.from_node, set()).add(edge.condition is not None)
    for from_node, answers in named.items():
        if len(answers) > 1:
            raise ContractError(
                f"node {from_node!r} carries both a conditional and an "
                "unconditional road out; a step names a condition on every "
                "road it leaves by, or on none of them")
