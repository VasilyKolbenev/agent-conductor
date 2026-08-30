"""What a plan may require of a step's verification, and why it may only ask more.

The evidence contract has exactly one degree of freedom left. Every road to
`succeeded` already carries exactly one verification row, of exactly one kind,
at exactly one uri, signed by exactly one identity the plan itself names -- and
the ONE thing none of those rules ask is whether that row names WHAT was
checked. `EvidenceRef.digest` is optional, and `attempt_replay._validate_evidence`
never reads it.

`required_evidence` is the plan's way of closing that, per step. This module
holds the DURABLE half of it: one grammar shared by both node contracts, the
pairing rule that keeps it off steps nobody verifies, the road from a drawing to
a run's frozen plan, and the two directions of "this is not a runtime word".
What the demand DOES to a run is the enforcement half and lives next door.

Three claims are held here and each fails differently:

- **it is a tightening.** The vocabulary is closed and there is no word in it
  for "less". A document saying `"none"`, `"optional"` or `"any"` is refused at
  both contracts rather than read as "no requirement", because a plan that could
  loosen the runtime's own demand is not a plan, it is a bypass.
- **it is unreachable on a step nobody verifies.** A gate and a loop are carried
  out by nobody and produce no verification, so a demand on one would be a field
  the runtime could never read. Refused where the workflow is drawn.
- **absent stays absent.** Neither shipped starter names it, `_document` and
  `as_dict` write it only when it is there, and both pinned revision digests are
  asked of the CONTRACT's own rendering rather than of the file -- so the day
  either writes a null, this reds.

This is its own module rather than more of `test_command_graph_template.py` for
`test_command_node_position.py`'s reason: that file is at the line cap, and this
is a self-contained circuit -- one value, its grammar, both its ends, and the
one name it must not be mistaken for.
"""
from __future__ import annotations

import pytest

from conductor.command.contracts import ContractError, canonical_json
from conductor.command.graph_definition import (
    RUNTIME_ONLY_FIELDS,
    GraphDefinition,
    GraphEdge,
    GraphNode,
)
from conductor.command.graph_template import (
    GraphTemplate,
    RunBinding,
    TemplateError,
    TemplateNode,
    load_template,
    materialize,
)
from conductor.command.graph_values import (
    REQUIRED_EVIDENCE,
    settled_required_evidence,
)
from conductor.command.workflow_draft import parse_document, publish_candidate

NOW = "2026-08-30T10:00:00Z"
SOLO = {"instances": [{"id": "solo", "adapter": "claude-code"}]}
#: Every word that would make the demand SMALLER than what the runtime already
#: holds every step to, plus the near-miss a case-folding grammar would admit.
LOOSENINGS = ("none", "optional", "any", "verified", "Digest")


def a_template_node(**changes) -> TemplateNode:
    values = {"node_id": "do", "kind": "task", "title": "Do the work",
              "role_id": "role-implementer", "capability": "dispatch",
              "arguments": {"handoff": "packet-001"}, "resources": ()}
    values.update(changes)
    return TemplateNode(**values)


def a_graph_node(**changes) -> GraphNode:
    values = {"node_id": "do", "kind": "task", "title": "Do the work",
              "instance_id": "solo", "capability": "dispatch",
              "arguments": {"handoff": "packet-001"}, "resources": ()}
    values.update(changes)
    return GraphNode(**values)


def a_drawing(step: dict) -> dict:
    """One gate and one dispatching step, as a person's own draft document."""
    return {
        "schema_version": 1,
        "title": "One reviewed dispatch",
        "nodes": [
            {"kind": "gate", "node_id": "confirm-gate", "title": "Human gate",
             "gate_id": "gate-confirm-do", "resources": []},
            step,
        ],
        "edges": [{"from_node": "confirm-gate", "to_node": "do"}],
    }


# -- the grammar --------------------------------------------------------------


def test_a_step_may_require_that_its_verification_name_what_it_checked():
    """The one word this build has, and the one thing it asks for."""
    assert settled_required_evidence("digest") == "digest"
    assert a_template_node(required_evidence="digest").required_evidence == "digest"
    assert a_graph_node(required_evidence="digest").required_evidence == "digest"


def test_saying_nothing_and_saying_whitespace_are_one_answer():
    """An empty string is the same answer as saying nothing, so it stores nothing.

    Absent, null and blank collapsing to one fact is what lets the field be
    added at all: a document written before it existed says exactly what a
    document leaving it blank says, and neither writes a byte.
    """
    assert settled_required_evidence(None) is None
    for blank in ("", "   ", "\t"):
        assert settled_required_evidence(blank) is None
    assert a_template_node(required_evidence="").required_evidence is None
    assert a_graph_node(required_evidence="  ").required_evidence is None


@pytest.mark.parametrize("value", [17, True, ["digest"], {"kind": "digest"}, 1.5])
def test_a_requirement_that_is_not_text_is_refused_before_it_is_compared(value):
    """Refused for BEING the wrong shape, not for missing the vocabulary.

    A grammar that only asked `value not in REQUIRED_EVIDENCE` would report a
    list as an unknown word, which tells the author of the document the wrong
    thing about what is wrong with it.
    """
    with pytest.raises(ContractError, match="text, or nothing at all"):
        settled_required_evidence(value)


@pytest.mark.parametrize("word", LOOSENINGS)
def test_a_plan_may_ask_for_more_proof_and_never_for_less(word):
    """The mandatory direction. A word outside the set is REFUSED, not ignored.

    This is the whole shape of the field. A vocabulary that tolerated an
    unknown word by treating it as "no requirement" would let a document
    written by anybody turn a demand off by misspelling it -- and a plan that
    can turn a demand off is a bypass with a workflow's name on it.

    Both contracts, because a template storing a word the definition refuses is
    a plan that cannot materialize, discovered at run time. The refusal is a
    `ContractError` on BOTH sides and that is deliberate: the grammar lives in
    `graph_values` beside `settled_purpose` and `settled_bounds`, which raise the
    base for the same reason -- one rule, one home, one exception. `TemplateError`
    subclasses it, so nothing about the template's own refusals narrowed.
    """
    with pytest.raises(ContractError, match="never for less"):
        a_template_node(required_evidence=word)
    with pytest.raises(ContractError, match="never for less"):
        a_graph_node(required_evidence=word)
    # The whitespace rule is the grammar's and it runs BEFORE the vocabulary, so
    # a padded word is the word and not a sixth refusal.
    assert settled_required_evidence("  digest  ") == "digest"


def test_the_vocabulary_this_build_carries_is_exactly_one_word():
    """A dead word is a plan saying something nothing can satisfy.

    Pinned so that widening the set is a decision made here, beside the test
    that a run really can meet the demand -- which is the enforcement module's
    positive control, and it exists for `"digest"` and for nothing else.
    """
    assert REQUIRED_EVIDENCE == frozenset({"digest"})


# -- the pairing rule ---------------------------------------------------------


def test_a_step_that_carries_nothing_out_may_not_require_evidence_of_it():
    """A gate and a loop are verified by nobody; there is no row to demand of.

    The mirror of the verifier rule one field over, and it is refused rather
    than ignored for that rule's reason: a plan that stores a field the runtime
    could never reach is a plan that says something it cannot do.
    """
    with pytest.raises(ContractError, match="no verification to require"):
        GraphNode(node_id="confirm-gate", kind="gate", title="Human gate",
                  gate_id="gate-confirm-do", required_evidence="digest")
    with pytest.raises(TemplateError, match="no verification to require"):
        TemplateNode(node_id="confirm-gate", kind="gate", title="Human gate",
                     gate_id="gate-confirm-do", resources=(),
                     required_evidence="digest")


def test_a_task_that_binds_nothing_may_not_require_evidence_either():
    """Not only gates: an UNBOUND task carries nothing out and is never run.

    A rule keyed on `kind == "gate"` would pass every test above and let a task
    with no role and no capability carry a demand nothing would ever read. The
    contracts key on the binding instead, each in its own vocabulary -- the
    template on `role_id`, the definition on `capability`.
    """
    with pytest.raises(TemplateError, match="binds no role of its own"):
        TemplateNode(node_id="sketch", kind="task", title="A step nobody runs",
                     resources=(), required_evidence="digest")
    with pytest.raises(ContractError, match="names no capability"):
        GraphNode(node_id="sketch", kind="task", title="A step nobody runs",
                  resources=(), required_evidence="digest")


# -- from a drawing to a run's frozen plan ------------------------------------


def test_the_demand_survives_the_road_from_a_drawing_to_a_frozen_plan():
    """Draft, publish, materialize -- the field crosses all three unchanged.

    The draft road carries it for free because `parse_document` parses every
    node through `TemplateNode.from_dict`, and that is asserted rather than
    assumed: a second draft contract would be a second place for this word to be
    dropped, and the drop would be silent.

    `materialize` COPIES it. Unlike `verifier_role_id` there is nothing to
    resolve -- it names no role and no instance -- so the plan a run follows
    carries the template's own word.
    """
    document = parse_document(a_drawing({
        "kind": "task", "node_id": "do", "title": "Do the work",
        "role_id": "role-implementer", "capability": "dispatch",
        "arguments": {"handoff": "packet-001"}, "resources": [],
        "required_evidence": "digest"}))
    step = next(row for row in document["nodes"] if row["node_id"] == "do")
    assert step["required_evidence"] == "digest"

    template = publish_candidate(document, workflow_id="flow", revision=1)
    assert next(row for row in template.steps()
                if row.node_id == "do").required_evidence == "digest"

    plan = materialize(
        template, RunBinding(assignments={"role-implementer": "solo"}),
        SOLO, graph_id="graph-001", run_id="run-001", created_at=NOW)
    planned = next(row for row in plan.nodes if row.node_id == "do")
    assert planned.required_evidence == "digest"
    # And it is in the plan's own BYTES, which is what the store replays and
    # what every rule downstream is a pure function of.
    assert planned.as_dict()["required_evidence"] == "digest"


def test_a_draft_naming_a_word_this_build_cannot_store_is_refused_at_the_door():
    """The loosening refusal on the road a person actually takes.

    A drawing is parsed through the production contract, so the tightening rule
    reaches the Studio's save without a second copy of itself living there.
    """
    with pytest.raises(ContractError, match="never for less"):
        parse_document(a_drawing({
            "kind": "task", "node_id": "do", "title": "Do the work",
            "role_id": "role-implementer", "capability": "dispatch",
            "arguments": {"handoff": "packet-001"}, "resources": [],
            "required_evidence": "any"}))


def test_the_field_round_trips_through_each_contracts_own_spelling():
    """What `as_dict` writes is exactly what `from_dict` takes back, both ends."""
    demanding = a_template_node(required_evidence="digest")
    assert TemplateNode.from_dict(demanding.as_dict()) == demanding
    planned = a_graph_node(required_evidence="digest")
    assert GraphNode.from_dict(planned.as_dict()) == planned


# -- absent stays absent ------------------------------------------------------


def test_a_step_requiring_nothing_writes_no_such_field_at_all():
    """Absent and null are ONE fact, and a document spells it one way.

    A contract that wrote `"required_evidence": null` would move the digest of
    every template and every plan ever written, which is the one thing this
    build may not do to add a field.
    """
    for node in (a_template_node(), a_graph_node()):
        assert node.required_evidence is None
        assert "required_evidence" not in node.as_dict()
    assert a_template_node(required_evidence=None).as_dict() == (
        a_template_node().as_dict())
    assert a_graph_node(required_evidence=None).as_dict() == (
        a_graph_node().as_dict())
    # An explicit null in a document reads as "this plan requires nothing extra".
    document = a_template_node().as_dict()
    document["required_evidence"] = None
    assert TemplateNode.from_dict(document).required_evidence is None


@pytest.mark.parametrize("starter", ["dalio-v1", "dalio-v2"])
def test_a_shipped_starter_requires_nothing_and_digests_as_it_always_did(starter):
    """The backward-compatibility MEASUREMENT, not the intention.

    The pinned digests are imported from the module that owns them and asked of
    the CONTRACT's own rendering rather than of the file on disk. That is what
    makes this a witness for `_document`: the file could not change by adding a
    field here, but the renderer could -- and if it started writing a null for
    an absent requirement, every past run's template identity would move and
    this is where it would be caught.
    """
    import hashlib

    from tests.test_alpha6_dalio_revision import (
        REVISION_ONE_DIGEST,
        REVISION_TWO_DIGEST,
    )

    pinned = {"dalio-v1": REVISION_ONE_DIGEST,
              "dalio-v2": REVISION_TWO_DIGEST}[starter]
    template = load_template(starter)
    assert [node.required_evidence for node in template.nodes] == [None] * len(
        template.nodes)
    rendered = template.as_dict()
    assert all("required_evidence" not in node for node in rendered["nodes"])
    assert hashlib.sha256(
        canonical_json(rendered).encode("utf-8")).hexdigest() == pinned, (
        f"{starter} no longer renders the document it was reviewed with")


def test_a_starters_materialized_plan_carries_no_requirement_either():
    """The definition half of the same measurement, on the same shipped bytes."""
    template = load_template("dalio-v2")
    plan = materialize(
        template, RunBinding(assignments={role: "solo" for role in template.roles}),
        SOLO, graph_id="graph-run", run_id="run-001", created_at=NOW)

    assert all(node.required_evidence is None for node in plan.nodes)
    for node in plan.as_dict()["nodes"]:
        assert "required_evidence" not in node, node


# -- the name is a demand, and not a runtime word ------------------------------


def test_the_requirement_is_a_plan_word_and_the_evidence_words_are_still_refused():
    """Both directions, because the two names look alike from a distance.

    `evidence` and `evidence_refs` are what a RUN produced, and a definition may
    not carry them at any depth. `required_evidence` is a DEMAND made of a run
    that has not happened -- it names no row and resolves to nothing. The
    difference is a fact of `_reserved` matching keys exactly, so both halves are
    pinned: the new name is not reserved, and nesting an `evidence` key under it
    or anywhere else is refused exactly as it was.
    """
    assert "required_evidence" not in RUNTIME_ONLY_FIELDS
    assert {"evidence", "evidence_refs"} <= RUNTIME_ONLY_FIELDS
    assert not RUNTIME_ONLY_FIELDS & GraphNode._FIELDS

    document = a_graph_node(required_evidence="digest").as_dict()
    assert GraphNode.from_dict(dict(document)).required_evidence == "digest"
    with pytest.raises(ContractError, match="runtime-only field"):
        GraphNode.from_dict({**document, "evidence": ["evidence-001"]})
    with pytest.raises(ContractError, match="runtime-only field"):
        GraphNode.from_dict({
            **document, "resources": [{"kind": "tool", "name": "git",
                                       "evidence": "smuggled"}]})


def test_both_node_contracts_carry_the_field_under_one_name():
    """One spelling, two documents, so materialization is a copy and not a map.

    A template that called it something else would need a translation in
    `_build`, and a translation is where a demand quietly becomes a different
    demand -- or none.
    """
    assert "required_evidence" in TemplateNode._FIELDS
    assert "required_evidence" in GraphNode._FIELDS
    template = GraphTemplate.from_dict({
        "schema_version": 1, "template_id": "flow", "revision": 1,
        "title": "One reviewed dispatch",
        "nodes": a_drawing({
            "kind": "task", "node_id": "do", "title": "Do the work",
            "role_id": "role-implementer", "capability": "dispatch",
            "arguments": {"handoff": "packet-001"}, "resources": [],
            "required_evidence": "digest"})["nodes"],
        "edges": [{"from_node": "confirm-gate", "to_node": "do"}]})
    plan = materialize(
        template, RunBinding(assignments={"role-implementer": "solo"}),
        SOLO, graph_id="graph-001", run_id="run-001", created_at=NOW)
    assert GraphDefinition.from_dict(plan.as_dict()) == plan
    assert next(node for node in plan.nodes
                if node.node_id == "do").required_evidence == "digest"
    assert GraphEdge(from_node="confirm-gate", to_node="do") in plan.edges
