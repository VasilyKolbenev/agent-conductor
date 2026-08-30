"""Where a step SITS: a durable editor fact that no run may ever read.

The mandate asks for "real 2D editor coordinates persisted SEPARATELY from
execution semantics". Both halves of that are claims, and they fail in
different ways, so both are held here:

- **persisted.** A position is a field of the workflow document, validated by
  the same contract every other field goes through, written when it is set and
  omitted when it is not. A coordinate a window kept to itself would look
  identical to this one right up until somebody closed the tab.
- **separately.** ``materialize`` DROPS it. A run's frozen plan carries no
  coordinate at all, so no replay reads one, no runtime decision can turn on
  one, and dragging a box can never change what a run does. That is made
  mechanical rather than asserted: ``GraphNode`` has no such field, so a
  materializer that tried to carry one would not construct.

A third claim is here because it is the reason the field could be added at all:
absent stays absent. Both shipped starters name no position, so their revision
digests are exactly what they were before this existed -- and those two digests
are pinned bytes elsewhere in this suite, which is what makes "backward
compatible" a measurement rather than an intention.

This is its own module rather than more of ``test_command_graph_template``:
that file is at the line cap and this is a self-contained circuit -- one value,
its grammar, its two ends and the one road that must not carry it.
"""
from __future__ import annotations

import pytest

from conductor.command.graph_definition import GraphDefinition, GraphNode
from conductor.command.graph_template import (
    POSITION_LIMIT,
    GraphTemplate,
    NodePosition,
    RunBinding,
    TemplateError,
    TemplateNode,
    load_template,
    materialize,
)

NOW = "2026-08-30T10:00:00Z"
SOLO = {"instances": [{"id": "solo", "adapter": "claude-code"}]}


def a_node(**changes) -> TemplateNode:
    values = {"node_id": "goal", "kind": "task", "title": "Set the goal",
              "resources": ()}
    values.update(changes)
    return TemplateNode(**values)


# -- the grammar of a coordinate --------------------------------------------


@pytest.mark.parametrize("value", [1.5, "10", None, True, False, [1]])
def test_a_coordinate_is_a_whole_number_of_pixels(value):
    """A canvas is a grid of whole pixels, and a document is durable.

    `True` and `False` are in this list on purpose: they ARE integers in Python,
    so a check written as `isinstance(value, int)` admits them, and a step at
    `x=True` would be stored, read back and drawn at one pixel.
    """
    with pytest.raises(TemplateError, match="whole pixels"):
        NodePosition(x=value, y=0)
    with pytest.raises(TemplateError, match="whole pixels"):
        NodePosition(x=0, y=value)


def test_a_coordinate_stays_within_reach_of_the_origin():
    """A bound, not a free integer: a step nobody can scroll to is a step lost.

    The boundary itself is accepted, in both directions and on both axes --
    an off-by-one here would refuse a legitimate placement, which is the
    over-correction this pair exists to catch.
    """
    for sign in (1, -1):
        assert NodePosition(x=sign * POSITION_LIMIT, y=0).x == sign * POSITION_LIMIT
        assert NodePosition(x=0, y=sign * POSITION_LIMIT).y == sign * POSITION_LIMIT
        with pytest.raises(TemplateError, match="within"):
            NodePosition(x=sign * (POSITION_LIMIT + 1), y=0)
        with pytest.raises(TemplateError, match="within"):
            NodePosition(x=0, y=sign * (POSITION_LIMIT + 1))


def test_a_half_placed_step_is_refused_rather_than_completed():
    """An x with no y would be drawn at a coordinate this build invented.

    Nobody could tell that from one they chose, which is the whole reason the
    two axes are one value rather than two optional fields.
    """
    with pytest.raises(TemplateError, match="both axes"):
        NodePosition.from_dict({"x": 10})
    with pytest.raises(TemplateError, match="both axes"):
        NodePosition.from_dict({"y": 10})
    with pytest.raises(TemplateError, match="unsupported field"):
        NodePosition.from_dict({"x": 1, "y": 2, "z": 3})


def test_a_position_round_trips_through_the_documents_own_spelling():
    """What `as_dict` writes is exactly what `from_dict` takes back."""
    placed = a_node(position=NodePosition(x=48, y=-96))
    assert placed.as_dict()["position"] == {"x": 48, "y": -96}
    assert TemplateNode.from_dict(placed.as_dict()) == placed
    # And a raw mapping is taken through the same door a document goes through,
    # so a caller handing two integers and a caller handing a value agree.
    assert a_node(position={"x": 48, "y": -96}) == placed


# -- absent stays absent -----------------------------------------------------


def test_a_step_nobody_placed_writes_no_position_at_all():
    """Absent and null are ONE fact here, and a document spells it one way.

    A document that wrote `"position": null` would be a second spelling of
    "nobody placed this", and every digest of every template written before this
    field existed would have moved.
    """
    assert a_node().position is None
    assert "position" not in a_node().as_dict()
    assert a_node(position=None).as_dict() == a_node().as_dict()
    # An explicit null in a document reads as "the canvas may place it".
    document = a_node().as_dict()
    document["position"] = None
    assert TemplateNode.from_dict(document).position is None


@pytest.mark.parametrize("starter", ["dalio-v1", "dalio-v2"])
def test_a_shipped_starter_names_no_position_and_digests_as_it_always_did(
        starter):
    """The backward-compatibility measurement, not the intention.

    Both shipped documents predate this field. If either had gained a position
    -- or if `as_dict` had started writing one -- the revision digest pinned in
    `test_alpha6_dalio_revision` would move, and a frozen byte pin is the one
    thing this build may never break to add a feature.
    """
    template = load_template(starter)
    assert [node.position for node in template.nodes] == [None] * len(
        template.nodes)
    assert all("position" not in node
               for node in template.as_dict()["nodes"])


# -- separately from execution semantics -------------------------------------


def test_the_runs_frozen_plan_carries_no_coordinate_at_all():
    """The mandate's "separately", made mechanical rather than asserted.

    A placed template is materialized and every node of the result is asked for
    the field. It is not merely absent from the output: `GraphNode` has no such
    field to carry, so a materializer that tried to pass one would not
    construct -- which is a stronger guarantee than a line that drops it and
    could be deleted.
    """
    template = load_template("dalio-v2")
    document = template.as_dict()
    for at, node in enumerate(document["nodes"]):
        node["position"] = {"x": 100 * at, "y": 40 * at}
    placed = GraphTemplate.from_dict(document)
    assert all(node.position is not None for node in placed.nodes)

    definition = materialize(
        placed, RunBinding(assignments={role: "solo" for role in placed.roles}),
        SOLO, graph_id="graph-run", run_id="run-001", created_at=NOW)

    assert "position" not in GraphNode._FIELDS
    for node in definition.nodes:
        assert not hasattr(node, "position"), node.node_id
    for node in definition.as_dict()["nodes"]:
        assert "position" not in node, node


def test_moving_every_step_does_not_move_the_plan_a_run_would_follow():
    """Two materializations, one placed and one not, and the same frozen bytes.

    This is the claim a person actually cares about: rearranging a drawing may
    not change what the run does. Compared by DIGEST -- the value the store
    freezes and replays against -- rather than by reading fields back, so a
    coordinate leaking in anywhere at all would move it.
    """
    template = load_template("dalio-v2")
    binding = RunBinding(assignments={role: "solo" for role in template.roles})
    made = {"graph_id": "graph-run", "run_id": "run-001", "created_at": NOW}
    plain = materialize(template, binding, SOLO, **made)

    document = template.as_dict()
    for at, node in enumerate(document["nodes"]):
        node["position"] = {"x": 37 * at - 400, "y": 91 * at}
    rearranged = materialize(GraphTemplate.from_dict(document), binding, SOLO,
                             **made)

    assert rearranged.digest() == plain.digest()
    assert GraphDefinition.from_dict(rearranged.as_dict()).digest() == (
        plain.digest())


def test_a_position_edited_in_place_is_answered_from_the_contracts_own_copy():
    """The house model: a value is rebuilt before one field of it is read.

    `TemplateNode` snapshots what it is handed, so a caller holding a reference
    and mutating it afterwards changes nothing the document will say. Without
    this a position could be moved out of bounds after validation and written.
    """
    handed = {"x": 20, "y": 30}
    node = a_node(position=handed)
    handed["x"] = POSITION_LIMIT * 99
    assert node.position == NodePosition(x=20, y=30)
    assert node.as_dict()["position"] == {"x": 20, "y": 30}
