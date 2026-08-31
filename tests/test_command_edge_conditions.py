"""When a road opens, as a closed vocabulary rather than as an expression.

An edge that names no condition is what every plan written before this said: a
dependency, opening once the step behind it settles. A condition narrows that
road to ONE word the step behind it can actually produce -- and the whole of
what this module holds is that the narrowing cannot say anything else.

Four claims, each failing differently:

- **the vocabulary is closed in both directions.** `EDGE_CONDITIONS` is exactly
  the union of `_CONDITIONS_BY_KIND`, and `_CONDITIONS_BY_KIND` is keyed by
  exactly `NODE_KINDS`. Neither can grow a word alone, and the kind map is held
  to the node contract's own vocabulary rather than to a copy of it -- which is
  what `graph_values` already does for `MAX_ACTION_SECONDS`, and for the same
  reason: importing the other way would be a cycle.
- **a condition names a word its source can produce.** Per kind, both
  directions, and a capability-less task -- which is a task by kind and produces
  no word at all -- may carry none.
- **a source names a condition on every road out of it, or on none.** One
  conditional and one unconditional road is an author who meant *otherwise* and
  had no way to say it, and reading the bare road as a default would be the
  contract inventing what the plan meant.
- **absent stays absent.** The field is written only when named, so both shipped
  revisions' canonical documents and both pinned digests do not move. The
  inversion is the calibration: writing a condition INTO a shipped document
  moves its digest, so the pin above is measuring something.

This is its own module rather than more of `test_command_graph_definition.py`
for `test_command_required_evidence.py`'s reason: that file is near the line
cap, and this is a self-contained circuit -- one vocabulary, one field's
grammar, and the document rules that decide whether a set of conditions could
ever be true.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from conductor.command.contracts import ContractError, canonical_json
from conductor.command.graph_conditions import (
    EDGE_CONDITIONS,
    _CONDITIONS_BY_KIND,
    settled_edge_condition,
)
from conductor.command.graph_definition import (
    NODE_KINDS,
    GraphDefinition,
    GraphEdge,
    GraphLoop,
    GraphNode,
)
from conductor.command.graph_template import (
    TEMPLATE_DIR,
    GraphTemplate,
    RunBinding,
    TemplateError,
    TemplateNode,
    materialize,
)
from conductor.command.workflow_draft import parse_document
from tests.test_alpha6_dalio_revision import (
    REVISION_ONE_DIGEST,
    REVISION_TWO_DIGEST,
)

NOW = "2026-08-30T10:00:00Z"


def a_graph(*, nodes, edges):
    return GraphDefinition(graph_id="graph-1", run_id="run-1", created_at=NOW,
                           nodes=nodes, edges=edges)


#: One node of each kind, plus a task that carries out no work. The gate is
#: last so an effecting node can stand behind it without reordering anything.
def kind_nodes():
    return {
        "gate": GraphNode(node_id="gate", kind="gate", title="Gate",
                          gate_id="gate-1"),
        "task": GraphNode(node_id="task", kind="task", title="Task",
                          instance_id="claude-dev", capability="review"),
        "loop": GraphNode(node_id="loop", kind="loop", title="Loop",
                          loop=GraphLoop(bound=3, back_to="task")),
        "note": GraphNode(node_id="note", kind="task", title="Note"),
        "sink": GraphNode(node_id="sink", kind="task", title="Sink"),
    }


# -- the vocabulary is closed, and closed in both directions -------------------


def test_the_condition_vocabulary_is_exactly_the_union_of_the_kind_map():
    """Neither half can grow a word alone, which is what closed means here."""
    union = set().union(*_CONDITIONS_BY_KIND.values())

    assert set(EDGE_CONDITIONS) == union
    assert len(EDGE_CONDITIONS) == 8
    assert sum(len(words) for words in _CONDITIONS_BY_KIND.values()) == 8


def test_every_kind_of_step_has_its_own_words_and_no_kind_is_missing():
    """Held to the node contract's own vocabulary, not to a copy of it."""
    assert set(_CONDITIONS_BY_KIND) == set(NODE_KINDS)
    for kind, words in _CONDITIONS_BY_KIND.items():
        assert words, f"{kind} names no condition at all"
    families = list(_CONDITIONS_BY_KIND.values())
    for index, words in enumerate(families):
        for other in families[index + 1:]:
            assert not (words & other), "two kinds share a condition word"


def test_the_kind_map_cannot_be_edited_by_whoever_reads_it():
    """A contract a caller can rewrite in place is not one."""
    with pytest.raises(TypeError):
        _CONDITIONS_BY_KIND["task"] = frozenset()


@pytest.mark.parametrize("word", sorted(EDGE_CONDITIONS))
def test_every_condition_word_survives_its_own_grammar(word):
    assert settled_edge_condition(word) == word


@pytest.mark.parametrize("value", [None, "", "   "])
def test_saying_nothing_and_saying_blank_are_the_same_answer(value):
    """A Studio select spells "cleared" as an empty string; both mean absent."""
    assert settled_edge_condition(value) is None


@pytest.mark.parametrize("value", [
    "approved", "on_APPROVED", "on_succeeded == true", "always", 1, True, [],
    {"on_approved": True}])
def test_a_condition_that_is_not_one_of_the_eight_words_is_refused(value):
    with pytest.raises(ContractError):
        settled_edge_condition(value)


def test_the_refusal_says_a_condition_is_a_word_and_never_an_expression():
    with pytest.raises(ContractError) as caught:
        settled_edge_condition("on_succeeded and on_approved")
    assert "never an expression" in str(caught.value)


# -- a condition names a word its source can produce ---------------------------


@pytest.mark.parametrize("kind", sorted(_CONDITIONS_BY_KIND))
def test_each_kind_carries_its_own_words_and_refuses_every_other_kinds(kind):
    """Both directions, per kind: what it may say, and what it may not."""
    nodes = kind_nodes()
    source = nodes[kind]
    for word in sorted(EDGE_CONDITIONS):
        edges = (GraphEdge(from_node=kind, to_node="sink", condition=word),)
        rows = (nodes["task"], source, nodes["sink"]) if kind != "task" else (
            source, nodes["sink"])
        if word in _CONDITIONS_BY_KIND[kind]:
            assert a_graph(nodes=rows, edges=edges).edges[0].condition == word
            continue
        with pytest.raises(ContractError) as caught:
            a_graph(nodes=rows, edges=edges)
        assert f"a {kind} node cannot produce" in str(caught.value)


def test_the_refusal_names_the_edge_the_condition_and_the_kind():
    nodes = kind_nodes()
    with pytest.raises(ContractError) as caught:
        a_graph(nodes=(nodes["task"], nodes["gate"], nodes["sink"]),
                edges=(GraphEdge(from_node="gate", to_node="sink",
                                 condition="on_succeeded"),))
    message = str(caught.value)
    assert "'gate'->'sink'" in message
    assert "'on_succeeded'" in message and "gate node" in message


@pytest.mark.parametrize("word", sorted(_CONDITIONS_BY_KIND["task"]))
def test_a_task_that_carries_out_no_work_may_name_no_condition(word):
    """It produces no word at all, so the road would be dead by construction."""
    nodes = kind_nodes()
    with pytest.raises(ContractError) as caught:
        a_graph(nodes=(nodes["note"], nodes["sink"]),
                edges=(GraphEdge(from_node="note", to_node="sink",
                                 condition=word),))
    assert "carries out no work" in str(caught.value)


def test_the_same_road_out_of_a_working_task_is_accepted():
    """The positive control: the refusal above is about the capability."""
    nodes = kind_nodes()
    graph = a_graph(nodes=(nodes["task"], nodes["sink"]),
                    edges=(GraphEdge(from_node="task", to_node="sink",
                                     condition="on_succeeded"),))

    assert graph.edges[0].condition == "on_succeeded"


def test_a_capability_less_task_may_still_carry_an_unconditional_road():
    nodes = kind_nodes()
    graph = a_graph(nodes=(nodes["note"], nodes["sink"]),
                    edges=(GraphEdge(from_node="note", to_node="sink"),))

    assert graph.edges[0].condition is None


# -- one source names a condition on every road, or on none --------------------


def test_a_source_mixing_a_conditional_and_a_bare_road_is_refused():
    nodes = kind_nodes()
    with pytest.raises(ContractError) as caught:
        a_graph(nodes=(nodes["task"], nodes["gate"], nodes["sink"],
                       nodes["note"]),
                edges=(GraphEdge(from_node="gate", to_node="sink",
                                 condition="on_approved"),
                       GraphEdge(from_node="gate", to_node="note")))
    assert "or on none of them" in str(caught.value)


def test_two_roads_out_of_one_source_under_different_words_are_fine():
    """Routing is the point: one word opens one road and closes the other."""
    nodes = kind_nodes()
    graph = a_graph(
        nodes=(nodes["task"], nodes["gate"], nodes["sink"], nodes["note"]),
        edges=(GraphEdge(from_node="gate", to_node="sink",
                         condition="on_approved"),
               GraphEdge(from_node="gate", to_node="note",
                         condition="on_rejected")))

    assert [edge.condition for edge in graph.edges] == [
        "on_approved", "on_rejected"]


def test_two_roads_out_of_one_source_under_one_word_are_fan_out():
    nodes = kind_nodes()
    graph = a_graph(
        nodes=(nodes["task"], nodes["gate"], nodes["sink"], nodes["note"]),
        edges=(GraphEdge(from_node="gate", to_node="sink",
                         condition="on_approved"),
               GraphEdge(from_node="gate", to_node="note",
                         condition="on_approved")))

    assert [edge.to_node for edge in graph.edges] == ["sink", "note"]


def test_a_source_naming_nothing_on_any_road_is_todays_plan_unchanged():
    nodes = kind_nodes()
    graph = a_graph(
        nodes=(nodes["task"], nodes["gate"], nodes["sink"], nodes["note"]),
        edges=(GraphEdge(from_node="gate", to_node="sink"),
               GraphEdge(from_node="gate", to_node="note")))

    assert [edge.condition for edge in graph.edges] == [None, None]


@pytest.mark.parametrize("second", [None, "on_rejected"])
def test_one_source_reaching_one_step_twice_is_already_refused(second):
    """The design's convergence rule needs no code, and here is why.

    Two roads from ONE source into one step is dead under AND-only joins, and
    the definition already refuses a repeated `from`/`to` pair outright --
    whatever either edge says. Both spellings are driven, so the road stays
    closed if that rule is ever relaxed: this reds, and names the reason.
    """
    nodes = kind_nodes()
    with pytest.raises(ContractError) as caught:
        a_graph(nodes=(nodes["task"], nodes["gate"], nodes["sink"]),
                edges=(GraphEdge(from_node="gate", to_node="sink",
                                 condition="on_approved"),
                       GraphEdge(from_node="gate", to_node="sink",
                                 condition=second)))
    assert "must not repeat a from/to pair" in str(caught.value)


def test_the_template_refuses_the_same_repeated_pair():
    """The other contract that could have expressed it, held to the same rule."""
    with pytest.raises(TemplateError) as caught:
        GraphTemplate(
            template_id="t", revision=1, title="T",
            nodes=(TemplateNode(node_id="gate", kind="gate", title="Gate",
                                gate_id="gate-1"),
                   TemplateNode(node_id="sink", kind="task", title="Sink")),
            edges=(GraphEdge(from_node="gate", to_node="sink",
                             condition="on_approved"),
                   GraphEdge(from_node="gate", to_node="sink",
                             condition="on_rejected")))
    assert "must not repeat a from/to pair" in str(caught.value)


# -- the condition survives every door a plan is written through ---------------


def test_a_condition_round_trips_through_the_definitions_own_document():
    nodes = kind_nodes()
    graph = a_graph(nodes=(nodes["task"], nodes["gate"], nodes["sink"]),
                    edges=(GraphEdge(from_node="gate", to_node="sink",
                                     condition="on_approved"),))

    rebuilt = GraphDefinition.from_dict(graph.as_dict())

    assert rebuilt.as_dict() == graph.as_dict()
    assert rebuilt.edges[0].condition == "on_approved"
    assert rebuilt.digest() == graph.digest()


def test_a_condition_survives_a_template_being_materialized_into_a_plan():
    """The template is not a second edge contract; it carries the same one."""
    template = GraphTemplate(
        template_id="t", revision=1, title="T",
        nodes=(TemplateNode(node_id="gate", kind="gate", title="Gate",
                            gate_id="gate-1"),
               TemplateNode(node_id="apply", kind="task", title="Apply",
                            role_id="doer", capability="dispatch")),
        edges=(GraphEdge(from_node="gate", to_node="apply",
                         condition="on_approved"),))

    graph = materialize(
        template, RunBinding(assignments={"doer": "solo"}),
        {"instances": [{"id": "solo", "adapter": "claude-code"}]},
        graph_id="graph-1", run_id="run-1", created_at=NOW)

    assert graph.edges[0].condition == "on_approved"
    assert GraphTemplate.from_dict(template.as_dict()).settled()[1][
        0].condition == "on_approved"


def a_draft(condition: str):
    return {
        "schema_version": 1, "title": "T",
        "nodes": [{"node_id": "gate", "kind": "gate", "title": "Gate",
                   "gate_id": "gate-1"},
                  {"node_id": "sink", "kind": "task", "title": "Sink"}],
        "edges": [{"from_node": "gate", "to_node": "sink",
                   "condition": condition}],
    }


def test_a_condition_survives_the_draft_door_a_browser_writes_through():
    parsed = parse_document(a_draft("on_approved"))

    assert parsed["edges"] == [{"from_node": "gate", "to_node": "sink",
                                "condition": "on_approved"}]


def test_a_draft_edge_naming_a_word_that_is_not_one_is_refused():
    with pytest.raises(ContractError):
        parse_document(a_draft("whenever"))


# -- absent stays absent, and the inversion proves the pin measures ------------


def test_an_edge_that_names_no_condition_writes_no_key_at_all():
    """Omit-when-absent, at the one place a digest is taken over."""
    edge = GraphEdge(from_node="a", to_node="b")

    assert edge.as_dict() == {"from_node": "a", "to_node": "b"}
    assert "condition" not in canonical_json(edge.as_dict())


def test_a_document_writing_an_explicit_null_is_not_the_canonical_spelling():
    """Present-and-null is read as absent, and re-rendered without the key.

    The store compares each journal line to the contract's own rendering, so a
    line carrying `"condition": null` is not canonical JSON and is refused
    there. This is the same fact one layer up, where it can be seen.
    """
    written = {"from_node": "a", "to_node": "b", "condition": None}

    rebuilt = GraphEdge.from_dict(written)

    assert rebuilt.condition is None
    assert rebuilt.as_dict() == {"from_node": "a", "to_node": "b"}
    assert canonical_json(rebuilt.as_dict()) != canonical_json(written)


@pytest.mark.parametrize("name, pinned", [
    ("dalio-v1", REVISION_ONE_DIGEST), ("dalio-v2", REVISION_TWO_DIGEST)])
def test_both_shipped_revisions_are_byte_identical_after_the_field_arrives(
        name, pinned):
    """The digest immunity claim, asked of the shipped file itself."""
    document = json.loads(
        (TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8"))

    assert hashlib.sha256(
        canonical_json(document).encode("utf-8")).hexdigest() == pinned
    assert all("condition" not in edge for edge in document["edges"])
    assert canonical_json(
        GraphTemplate.from_dict(document).as_dict()) == canonical_json(document)


@pytest.mark.parametrize("name", ["dalio-v1", "dalio-v2"])
def test_writing_a_condition_into_a_shipped_revision_moves_its_digest(name):
    """The calibration. Without it the pin above could be measuring nothing."""
    document = json.loads(
        (TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    before = hashlib.sha256(
        canonical_json(document).encode("utf-8")).hexdigest()

    document["edges"][0]["condition"] = "on_approved"

    assert hashlib.sha256(
        canonical_json(document).encode("utf-8")).hexdigest() != before
