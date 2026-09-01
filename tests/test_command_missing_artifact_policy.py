"""What a step asks for when a document it needs is not there, and who owns it.

Two fail-closed words and no third. `fail` is what this build has always done,
now sayable out loud: the step is reached, its inputs are resolved at spawn, the
resolution refuses, and a durable `failed` receipt is written with no task
spawned and no model call spent -- the two sentences
`adapters/artifact_transport` writes on that road, one per capability. `block`
is the new one and it is the owner's requirement: the step is never offered
while the document is absent, so nothing is attempted and nothing fails.

Four claims carry this stage, and consumption is deliberately not one of them --
a field may be committed consumed by nothing, never witnessed by nothing:

- **absent IS `fail`.** Not a default chosen for convenience: it is the
  behaviour every plan already written has. The enum's `fail` exists so a
  person can say it on purpose, and the two are held behaviourally identical by
  `test_absent_and_fail_are_one_behaviour_and_differ_only_in_being_said` --
  which keeps holding after `block` starts changing verdicts, because `fail`
  must go on changing none.
- **the plan carries it, and only where a document could be missing.** Tighter
  than the two pairing rules beside it: those ask whether the step acts at all,
  this asks whether the capability it carries out is one the reviewed schemas
  hand documents to. Absent stays absent, so no shipped starter moves a byte.
- **ONE authority says which argument key names a step's inputs.**
  `artifacts._INPUT_REF_KEYS`, spent by the chain rule that judges a published
  artifact and, from the next stage, by the schedule that decides what may run.
  Two spellings would let the store and the scheduler disagree about what a
  step needs, which is a screen offering work the store is about to refuse.
- **the raw answer is unjudged on purpose.** `required_input_refs` returns the
  value; the store REFUSES a malformed one through `latest_artifacts` and the
  schedule's reading may not raise on the same value at all. Both halves are
  witnessed, because a helper that settled the value here would have to pick
  one of those answers and be wrong for the other caller.
"""
from __future__ import annotations

import hashlib

import pytest

from conductor.command.artifacts import (
    ArtifactDocument,
    required_input_refs,
    requires_input_artifacts,
    unresolved_input_refs,
)
from conductor.command.contracts import (
    ContractError,
    DecisionReceipt,
    canonical_json,
)
from conductor.command.graph_definition import (
    GraphDefinition,
    GraphEdge,
    GraphNode,
    _rebuilt_node,
)
from conductor.command.graph_schedule import schedule
from conductor.command.run_store import CorruptRun, RunStore, snapshot_digest
from conductor.command.graph_template import (
    RunBinding,
    TemplateError,
    TemplateNode,
    load_template,
    materialize,
)
from conductor.command.graph_template_document import (
    _rebuilt_node as _rebuilt_template_node,
)
from conductor.command.graph_values import (
    MISSING_ARTIFACT_POLICIES,
    settled_missing_artifact_policy,
)
from conductor.command.workflow_draft import parse_document, publish_candidate
from tests.test_command_run_store import CONFIG, a_run

NOW = "2026-09-01T10:00:00Z"
SOLO = {"instances": [{"id": "solo", "adapter": "claude-code"}]}
STARTERS = ("dalio-v1", "dalio-v2", "dalio-v3")
#: The store-backed witnesses use their own run id, because the run they open
#: is a real one built by `tests.test_command_run_store`'s own helpers.
STORE_RUN = "run-001"

#: The four capabilities the reviewed schemas hand no document to. Each names an
#: action or an attempt instead, which is why a policy about a missing DOCUMENT
#: is a word with no behaviour on one of them.
GIVEN_NOTHING = ("evidence", "stop", "retry", "switch")
#: The two that are handed documents, and the key each one's schema owns.
GIVEN_DOCUMENTS = {"dispatch": "artifact_refs", "review": "target_artifact_refs"}


def a_graph_node(**changes) -> GraphNode:
    values = {"node_id": "do", "kind": "task", "title": "Do the work",
              "instance_id": "solo", "capability": "dispatch",
              "arguments": {"artifact_refs": ["artifact-brief"]},
              "resources": ()}
    values.update(changes)
    return GraphNode(**values)


def a_template_node(**changes) -> TemplateNode:
    values = {"node_id": "do", "kind": "task", "title": "Do the work",
              "role_id": "role-implementer", "capability": "dispatch",
              "arguments": {"artifact_refs": ["artifact-brief"]},
              "resources": ()}
    values.update(changes)
    return TemplateNode(**values)


def a_drawing(step: dict) -> dict:
    """One gate and one dispatching step, as a person's own draft document."""
    return {
        "schema_version": 1,
        "title": "One waiting dispatch",
        "nodes": [
            {"kind": "gate", "node_id": "confirm-gate", "title": "Human gate",
             "gate_id": "gate-confirm-do", "resources": []},
            step,
        ],
        "edges": [{"from_node": "confirm-gate", "to_node": "do"}],
    }


def a_plan(*, policy=None) -> GraphDefinition:
    """A gate, a step that is handed a document, and a step that is not."""
    return GraphDefinition(
        graph_id="graph-wait", run_id="run-001", created_at=NOW,
        nodes=(GraphNode(node_id="gate", kind="gate", title="Gate",
                         gate_id="gate-1"),
               a_graph_node(missing_artifact_policy=policy),
               GraphNode(node_id="tell", kind="task", title="Tell",
                         instance_id="solo", capability="evidence",
                         arguments={"target_action_id": "action-1",
                                    "kinds": ["result"]})),
        edges=(GraphEdge(from_node="gate", to_node="do"),
               GraphEdge(from_node="gate", to_node="tell")))


def an_artifact(ref: str, *, at: str = "artifact-1",
                run: str = "run-001") -> ArtifactDocument:
    return ArtifactDocument(
        artifact_id=at, artifact_ref=ref, run_id=run, created_at=NOW,
        media_type="text/markdown", content="# Brief\n\nwhat to do")


# -- 1. the vocabulary, and the one direction it may grow ---------------------


def test_the_vocabulary_is_two_fail_closed_words_and_names_no_third():
    """Both directions. A word LEAVING is as much a product change as one
    arriving: `fail` disappearing would make every plan that says it
    unreadable, and `block` disappearing would make the owner's requirement
    unsayable while the field went on existing."""
    assert MISSING_ARTIFACT_POLICIES == frozenset({"fail", "block"})
    assert sorted(MISSING_ARTIFACT_POLICIES) == ["block", "fail"]


def test_the_refusal_states_which_direction_this_vocabulary_may_grow():
    """The rule a future word is judged by, said where a person meets it.

    Both words this build carries refuse to proceed without the document. A
    third that skipped the step, substituted another document, or let the run
    go on would not be a new policy -- it would be this product deciding a
    missing input is evidence the work is done.
    """
    with pytest.raises(ContractError) as refusal:
        settled_missing_artifact_policy("skip")

    said = str(refusal.value)
    assert "fail-closed" in said, said
    assert "never evidence that the work is done" in said, said
    assert "['block', 'fail']" in said, said


# -- 2. the settled grammar ---------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_saying_nothing_and_saying_blank_are_the_same_answer(value):
    """An empty string is what a Studio select spells when a person clears it."""
    assert settled_missing_artifact_policy(value) is None


@pytest.mark.parametrize("value", ["fail", "block", "  block  "])
def test_a_word_this_build_has_behaviour_for_is_kept(value):
    assert settled_missing_artifact_policy(value) == value.strip()


@pytest.mark.parametrize("value", ["skip", "substitute", "wait", "ignore",
                                   "Fail", "BLOCK", "fail_run"])
def test_a_policy_this_build_has_no_behaviour_for_is_refused(value):
    """Case included: a grammar that folded case would admit a word no reader
    of the enum would recognise, and store it under a spelling nothing reads."""
    with pytest.raises(ContractError, match="fail-closed"):
        settled_missing_artifact_policy(value)


@pytest.mark.parametrize("value", [1, True, [], {}, ["block"], 0.0])
def test_a_policy_that_is_not_text_is_refused_before_it_is_compared(value):
    with pytest.raises(ContractError, match="is text, or nothing at all"):
        settled_missing_artifact_policy(value)


# -- 3. absent IS fail --------------------------------------------------------


def test_absent_and_fail_are_one_behaviour_and_differ_only_in_being_said():
    """The defence of the ruling, and the guard that keeps it true.

    Two plans identical but for the word, one journal, one schedule: the same
    verdict for every step. This is written to keep holding through the stage
    that teaches the schedule to read the field, because what it will hold then
    is the half that matters -- `block` changes verdicts and `fail` must go on
    changing none. A build where saying `fail` out loud did something extra
    would have made every plan written before the field existed mean something
    new, silently.
    """
    silent, spoken = a_plan(), a_plan(policy="fail")

    assert schedule(silent, ()) == schedule(spoken, ())
    # And the difference really is the word: it is in the bytes of one node and
    # nowhere else in the document.
    said = [row for row in spoken.as_dict()["nodes"]
            if "missing_artifact_policy" in row]
    assert [row["node_id"] for row in said] == ["do"]
    assert [{k: v for k, v in row.items() if k != "missing_artifact_policy"}
            for row in spoken.as_dict()["nodes"]] == silent.as_dict()["nodes"]


def test_a_plan_naming_no_policy_writes_no_key_and_moves_no_digest():
    """Omit-when-absent, at the one place a digest is taken over."""
    silent, waiting = a_plan(), a_plan(policy="block")

    assert all("missing_artifact_policy" not in node.as_dict()
               for node in silent.nodes)
    assert next(node for node in waiting.nodes
                if node.node_id == "do").as_dict()[
                    "missing_artifact_policy"] == "block"
    assert silent.digest() != waiting.digest()


def test_a_document_writing_an_explicit_null_is_not_the_canonical_spelling():
    """Present-and-null reads as absent and is re-rendered without the key, so
    the store refuses such a line as non-canonical."""
    written = {**a_graph_node().as_dict(), "missing_artifact_policy": None}

    rebuilt = GraphNode.from_dict(written)

    assert rebuilt.missing_artifact_policy is None
    assert "missing_artifact_policy" not in rebuilt.as_dict()
    assert TemplateNode.from_dict(
        {**a_template_node().as_dict(),
         "missing_artifact_policy": None}).missing_artifact_policy is None


# -- 4. the pairing rule, both contracts, both directions ---------------------


@pytest.mark.parametrize("capability", GIVEN_NOTHING)
def test_a_definition_step_given_no_documents_may_name_no_policy(capability):
    with pytest.raises(ContractError, match="no input for it to be missing"):
        a_graph_node(capability=capability, arguments={},
                     missing_artifact_policy="block")


@pytest.mark.parametrize("kind,extra", [
    ("gate", {"gate_id": "gate-1"}),
    ("task", {}),
])
def test_a_definition_step_that_carries_nothing_out_may_name_no_policy(
        kind, extra):
    """A gate is answered by a person and a bare task acts through nobody, so
    neither is ever handed a document to be missing."""
    with pytest.raises(ContractError, match="no input for it to be missing"):
        GraphNode(node_id="n", kind=kind, title="N",
                  missing_artifact_policy="fail", **extra)


@pytest.mark.parametrize("capability", sorted(GIVEN_DOCUMENTS))
@pytest.mark.parametrize("policy", ["fail", "block"])
def test_a_definition_step_that_is_given_documents_may_name_it(
        capability, policy):
    node = a_graph_node(capability=capability,
                        arguments={GIVEN_DOCUMENTS[capability]: ["a-brief"]},
                        missing_artifact_policy=policy)

    assert node.missing_artifact_policy == policy


@pytest.mark.parametrize("capability", GIVEN_NOTHING)
def test_a_template_step_given_no_documents_may_name_no_policy(capability):
    """The template's refusal names the CAPABILITY, which is its own contribution.

    Both layers refuse this, and a witness matching only what they share would
    pass on a build whose template rule had been deleted -- which is exactly the
    green survivor the failure-policy slice shipped and had to correct. So this
    asks for the half only this layer says: a person drawing a workflow picked a
    capability for a role, and the capability is the half they can change.
    """
    with pytest.raises(TemplateError) as refusal:
        a_template_node(capability=capability, arguments={},
                        missing_artifact_policy="block")

    said = str(refusal.value)
    assert repr(capability) in said, said
    assert "takes no input documents" in said, said
    assert "is given no artifacts" in said, said


def test_the_template_refusal_is_its_own_and_not_the_definitions_leaking():
    """The other half of that lesson, from the other side.

    A `TemplateNode` is refused where it is CONSTRUCTED, before any definition
    exists to have an opinion -- so the sentence a person gets is written in the
    vocabulary they drew in. The definition's own words are absent from it.
    """
    with pytest.raises(TemplateError) as refusal:
        a_template_node(capability="stop", arguments={},
                        missing_artifact_policy="fail")

    said = str(refusal.value)
    assert "no capability that is given artifacts" not in said, said


@pytest.mark.parametrize("capability", sorted(GIVEN_DOCUMENTS))
def test_a_template_step_that_is_given_documents_may_name_it(capability):
    node = a_template_node(
        capability=capability,
        arguments={GIVEN_DOCUMENTS[capability]: ["a-brief"]},
        missing_artifact_policy="block")

    assert node.missing_artifact_policy == "block"


def test_a_template_step_binding_no_role_may_name_no_policy():
    """Binding no role means carrying no capability, so it is given nothing."""
    with pytest.raises(TemplateError, match="is given no artifacts"):
        TemplateNode(node_id="note", kind="task", title="Note",
                     missing_artifact_policy="block")


# -- 5. the road from a drawing to a frozen plan ------------------------------


def test_the_policy_survives_the_road_from_a_drawing_to_a_frozen_plan():
    """Draft, publish, materialize -- the field crosses all three unchanged.

    It names no role and no instance, so `materialize` COPIES it and the plan a
    run follows carries the template's own word, in the plan's own BYTES.
    """
    document = parse_document(a_drawing({
        "kind": "task", "node_id": "do", "title": "Do the work",
        "role_id": "role-implementer", "capability": "dispatch",
        "arguments": {"artifact_refs": ["artifact-brief"]}, "resources": [],
        "missing_artifact_policy": "block"}))
    step = next(row for row in document["nodes"] if row["node_id"] == "do")
    assert step["missing_artifact_policy"] == "block"

    template = publish_candidate(document, workflow_id="flow", revision=1)
    assert next(row for row in template.steps()
                if row.node_id == "do").missing_artifact_policy == "block"

    plan = materialize(
        template, RunBinding(assignments={"role-implementer": "solo"}),
        SOLO, graph_id="graph-001", run_id="run-001", created_at=NOW)
    planned = next(row for row in plan.nodes if row.node_id == "do")
    assert planned.missing_artifact_policy == "block"
    assert planned.as_dict()["missing_artifact_policy"] == "block"


def test_a_draft_naming_a_word_this_build_cannot_store_is_refused_at_the_door():
    """The vocabulary refusal on the road a person actually takes.

    A drawing is parsed through the production contract, so the grammar reaches
    the Studio's save without a second copy of itself living there. It is a
    plain `ContractError` rather than a `TemplateError` and that is the design
    speaking: the WORD is the definition's grammar, held in one home and
    imported by the template, so a word the plan would refuse cannot be stored
    in a template that promises to materialize into one. Only the PAIRING rule
    is the template's own, and that one answers in the template's words.
    """
    with pytest.raises(ContractError, match="fail-closed"):
        parse_document(a_drawing({
            "kind": "task", "node_id": "do", "title": "Do the work",
            "role_id": "role-implementer", "capability": "dispatch",
            "arguments": {"artifact_refs": ["artifact-brief"]},
            "resources": [], "missing_artifact_policy": "skip"}))


def test_the_field_round_trips_through_each_contracts_own_spelling():
    for node in (a_graph_node(missing_artifact_policy="block"),
                 a_template_node(missing_artifact_policy="block")):
        rebuilt = type(node).from_dict(node.as_dict())
        assert rebuilt.missing_artifact_policy == "block"
        assert rebuilt.as_dict() == node.as_dict()


# -- 6. the shipped bytes do not move -----------------------------------------


@pytest.mark.parametrize("starter", STARTERS)
def test_a_shipped_starter_names_no_policy_and_digests_as_it_always_did(starter):
    """The backward-compatibility MEASUREMENT, not the intention.

    Asked of the CONTRACT's own rendering rather than of the file on disk: the
    file could not change by adding a field here, but the RENDERER could -- and
    if it started writing a null for an absent policy, every past template's
    identity would move and this is where it would be caught.
    """
    from tests.test_alpha6_dalio_revision import (
        REVISION_ONE_DIGEST,
        REVISION_THREE_DIGEST,
        REVISION_TWO_DIGEST,
    )

    pinned = {"dalio-v1": REVISION_ONE_DIGEST,
              "dalio-v2": REVISION_TWO_DIGEST,
              "dalio-v3": REVISION_THREE_DIGEST}[starter]
    template = load_template(starter)
    assert [node.missing_artifact_policy for node in template.nodes] == (
        [None] * len(template.nodes))
    rendered = template.as_dict()
    assert all("missing_artifact_policy" not in node
               for node in rendered["nodes"])
    assert hashlib.sha256(
        canonical_json(rendered).encode("utf-8")).hexdigest() == pinned, (
        f"{starter} no longer renders the document it was reviewed with")


@pytest.mark.parametrize("starter", STARTERS)
def test_a_starters_materialized_plan_carries_no_policy_either(starter):
    """The definition half of the same measurement, on the same shipped bytes."""
    template = load_template(starter)
    plan = materialize(
        template, RunBinding(assignments={r: "solo" for r in template.roles}),
        SOLO, graph_id="graph-run", run_id="run-001", created_at=NOW)

    assert all(node.missing_artifact_policy is None for node in plan.nodes)
    for node in plan.as_dict()["nodes"]:
        assert "missing_artifact_policy" not in node, node


# -- 7. the two rebuilds carry it ---------------------------------------------


def test_the_definition_rebuild_carries_the_policy():
    """`_rebuilt_node` re-validates every field, so one it forgets is one the
    store silently drops from a plan a run is already following."""
    rebuilt = _rebuilt_node(a_graph_node(missing_artifact_policy="block"))

    assert rebuilt.missing_artifact_policy == "block"


def test_the_template_rebuild_carries_the_policy():
    rebuilt = _rebuilt_template_node(
        a_template_node(missing_artifact_policy="fail"))

    assert rebuilt.missing_artifact_policy == "fail"


# -- 8. the one authority on which key names a step's inputs ------------------


@pytest.mark.parametrize("capability", sorted(GIVEN_DOCUMENTS))
def test_a_capability_the_schemas_hand_documents_to_requires_them(capability):
    assert requires_input_artifacts(capability) is True


@pytest.mark.parametrize("capability",
                         [*GIVEN_NOTHING, "observe", None, "", "Dispatch"])
def test_every_other_capability_is_handed_no_document_at_all(capability):
    """Including None -- a step binding nothing -- and a near-miss spelling: a
    capability is an id and this map is keyed exactly, never case-folded."""
    assert requires_input_artifacts(capability) is False


@pytest.mark.parametrize("capability,key", sorted(GIVEN_DOCUMENTS.items()))
def test_each_capability_reads_its_own_argument_key_and_not_the_others(
        capability, key):
    """The two schemas differ on one real rule, so they are two entries and not
    one shared name. A step's own key answers; the other schema's is not read."""
    other = next(name for name in GIVEN_DOCUMENTS.values() if name != key)

    assert required_input_refs(capability, {key: ["mine"]}) == ["mine"]
    assert required_input_refs(capability, {other: ["theirs"]}) == ()


@pytest.mark.parametrize("capability", [*GIVEN_NOTHING, None, "observe"])
def test_a_capability_given_no_documents_names_no_refs(capability):
    assert required_input_refs(
        capability, {"artifact_refs": ["a"],
                     "target_artifact_refs": ["b"]}) == ()


def test_the_raw_answer_is_unjudged_and_the_two_callers_judge_it_differently():
    """The split argued for when the helper was written, proved on both sides.

    One malformed value, two readers. The store must REFUSE it: the chain rule
    hands the raw value to `latest_artifacts`, whose grammar has always refused
    a non-list, and a durable record judged by a softened rule is the defect
    that rule exists to prevent. The SCHEDULE must not raise at all: it is
    recomputed on every question from a plan whose inner argument shape no
    contract validates, and a pure reading that threw would take down the read
    of a run rather than report anything.
    """
    from conductor.command.artifacts import latest_artifacts

    malformed = {"artifact_refs": "artifact-brief"}
    assert required_input_refs("dispatch", malformed) == "artifact-brief"

    with pytest.raises(ContractError):
        latest_artifacts((), required_input_refs("dispatch", malformed))
    assert unresolved_input_refs((), "dispatch", malformed) == ()


def test_the_reading_names_what_no_document_stands_for_in_the_asked_order():
    """Order is the step's own, and a repeat is one requirement named twice.

    The refs are deliberately asked in an order that is NOT their sorted one.
    A first draft of this witness used `b, a, b, c` with `a` standing, whose
    answer is `(b, c)` either way -- so a build that sorted the answer survived
    it. What a screen shows a person waiting is the step's own list, and a
    sorted one is a different sentence about the same plan.
    """
    arguments = {"artifact_refs": ["c-ref", "a-ref", "b-ref", "c-ref"]}

    assert unresolved_input_refs((), "dispatch", arguments) == (
        "c-ref", "a-ref", "b-ref")
    assert unresolved_input_refs(
        (an_artifact("a-ref"),), "dispatch", arguments) == ("c-ref", "b-ref")


def test_a_reference_some_document_stands_for_is_not_unresolved():
    arguments = {"target_artifact_refs": ["a-ref"]}

    assert unresolved_input_refs((), "review", arguments) == ("a-ref",)
    assert unresolved_input_refs(
        (an_artifact("a-ref"),), "review", arguments) == ()


def test_the_reading_passes_over_what_is_not_a_reference():
    """A non-string is not a reference. The argument schema refuses it at the
    door where a receipt can say so, and a reading may not raise at all."""
    arguments = {"artifact_refs": ["a-ref", 7, None, {"ref": "b"}]}

    assert unresolved_input_refs((), "dispatch", arguments) == ("a-ref",)


def test_only_a_real_artifact_record_makes_a_reference_resolved():
    """A look-alike does not satisfy a requirement, and that is the point.

    `documents` is every value the run holds, so the collection this walks is
    mixed by construction. Exact typing is the house rule -- a subclass answers
    `artifact_ref` however it likes -- and here it decides whether a step is
    told to wait. A build that trusted the attribute would call a requirement
    met because some record happened to carry a matching name, which is a step
    spawned against a document that does not exist.
    """
    class LooksLikeOne:
        artifact_ref = "a-ref"

    class Subclass(ArtifactDocument):
        pass

    arguments = {"artifact_refs": ["a-ref"]}
    impostors = (LooksLikeOne(), "not a record", 5, None,
                 Subclass(artifact_id="artifact-1", artifact_ref="a-ref",
                          run_id="run-001", created_at=NOW,
                          media_type="text/markdown", content="# no"))

    assert unresolved_input_refs(impostors, "dispatch", arguments) == ("a-ref",)
    # And the real record does resolve it, so this is exact typing speaking and
    # not the reading refusing everything.
    assert unresolved_input_refs(
        (*impostors, an_artifact("a-ref")), "dispatch", arguments) == ()


# -- 9. the chain rule spends the same authority ------------------------------


def test_the_chain_rule_reads_the_review_key_through_the_one_authority():
    """The re-point, witnessed from the side that can tell it happened.

    `_artifact_answers_its_request` used to spell `target_artifact_refs` itself.
    It asks `required_input_refs` now, so breaking that map's review entry makes
    the rule resolve NO inputs -- and a legitimately published artifact, whose
    inputs really are what its request asked for, stops matching. That is a
    store refusing a chain it authorized, and `test_command_artifact_flow`'s own
    live-rule witness reds with it.

    Here the same seam is asked directly: the map answers the key the reviewed
    schema owns, and the chain rule's resolution is a pure function of it.
    """
    from conductor.command.artifacts import _INPUT_REF_KEYS, latest_artifacts

    assert _INPUT_REF_KEYS["review"] == "target_artifact_refs"
    arguments = {"target_artifact_refs": ["artifact-brief"],
                 "result_artifact_ref": "artifact-goal"}
    standing = (an_artifact("artifact-brief", at="artifact-seed-1"),)

    resolved = latest_artifacts(
        standing, required_input_refs("review", arguments))

    assert tuple(row.artifact_id for row in resolved) == ("artifact-seed-1",)
