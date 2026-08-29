"""The editable half of a workflow: what a draft may be, and where it lives.

The whole design of this contract is one line, and it is the line these tests
are for. A draft may be **INCOMPLETE** -- a dangling edge, a loop pointing at a
step nobody has drawn, an effecting step standing beside its gate instead of
behind it, no nodes at all -- and it is STORED and EXPLAINED. A draft may not be
**FOREIGN** -- a key no template could carry, a schema this build does not
speak, a node shape the published contract would refuse -- and it is REFUSED
with nothing written. A test that proved only one of those two would leave the
distinction untested, so both sides are asserted on the same workflow.

Everything here runs against a real directory through the real contracts, and
the diagnostics are never compared against prose this file invented: what is
pinned is that the rows come from the ONE production constructor, that
:func:`draft_diagnostics` and :func:`publish_candidate` are the same judgement,
and that the code is derived from the exception TYPE.

The document builders here are shared with ``test_command_workflow_routes`` and
``test_command_run_routes``, which drive the same documents through the HTTP
boundary. There is deliberately no ``conftest.py`` in this repository, so the
helpers live in the module that owns the contract they build for.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.contracts import ContractError, canonical_json
from conductor.command.graph_template import (
    SCHEMA_VERSION,
    TEMPLATE_DIR,
    GraphTemplate,
    load_template,
)
from conductor.command.store_errors import StoreError
from conductor.command.template_store import DRAFT_NAME, TemplateStore
from conductor.command.workflow_draft import (
    DIAGNOSTIC_CODES,
    DRAFT_FIELDS,
    MAX_DRAFT_EDGES,
    MAX_DRAFT_NODES,
    NOT_YET_FIELDS,
    DraftRefused,
    WorkflowDraft,
    WorkflowDraftError,
    draft_diagnostics,
    parse_document,
    publish_candidate,
    saved_draft,
    starters,
    workflow_rows,
    workflow_state,
)

#: The workflow every test here draws into. A name its user invented: nothing
#: is stored for it until something is saved, which is the state every workflow
#: starts in.
WORKFLOW = "workflow-studio"
SAVED_AT = "2026-08-28T09:00:00Z"
LATER = "2026-08-28T10:30:00Z"


def clock_of(*moments):
    """A clock that hands out exactly these instants, then refuses to be read."""
    remaining = list(moments)

    def read():
        assert remaining, "the clock was read more times than the test allowed"
        return remaining.pop(0)

    return read


def a_document(**changes):
    """The smallest workflow this product will publish: a gate, then work.

    A dispatch step can change the world, so the published contract requires it
    to stand BEHIND a gate rather than beside one. That is where this shape came
    from -- it is the smallest document that constructs, which makes every
    incomplete variant below exactly one edit away from a publishable one.
    """
    document = {
        "schema_version": SCHEMA_VERSION,
        "title": "One reviewed dispatch",
        "nodes": [
            {"kind": "gate", "node_id": "confirm-gate", "title": "Human gate",
             "gate_id": "gate-confirm-do", "resources": []},
            {"kind": "task", "node_id": "do", "title": "Do the work",
             "stage": "do", "role_id": "role-implementer",
             "capability": "dispatch",
             "arguments": {
                 "work_item_id": "work-001",
                 "instruction_ref": "instruction-plan",
                 "profile": "implement",
                 "artifact_refs": ["artifact-plan"],
                 "output_limit_profile": "normal"},
             "resources": [{"kind": "sandbox", "name": "project-root"}]},
        ],
        "edges": [{"from_node": "confirm-gate", "to_node": "do"}],
    }
    document.update(json.loads(json.dumps(changes)))
    return document


def a_loop_node(back_to):
    return {"kind": "loop", "node_id": "again", "title": "Go round again",
            "loop": {"bound": 3, "back_to": back_to}, "resources": []}


#: Four ways a workflow under an editor's hand is not finished, each one a
#: thing a person really does halfway through drawing. Every one of these SAVES.
INCOMPLETE = {
    "a dangling edge": a_document(
        edges=[{"from_node": "confirm-gate", "to_node": "nowhere"}]),
    "a cycle": a_document(edges=[
        {"from_node": "confirm-gate", "to_node": "do"},
        {"from_node": "do", "to_node": "confirm-gate"}]),
    "an effecting step beside its gate": a_document(edges=[]),
    "a loop that reopens a step nobody has drawn": a_document(
        nodes=a_document()["nodes"] + [a_loop_node("ghost-step")],
        edges=[{"from_node": "confirm-gate", "to_node": "do"},
               {"from_node": "do", "to_node": "again"}]),
    "no nodes at all": a_document(nodes=[], edges=[]),
}

#: Nine documents that are not INCOMPLETE but FOREIGN: each carries something
#: no ``GraphTemplate`` could ever carry, so it is refused rather than stored.
FOREIGN = {
    "the identity the route already supplied": a_document(
        template_id="workflow-studio"),
    "the number a publish is asking for": a_document(revision=1),
    "a deployment word at the top level": a_document(provider_id="claude-code"),
    "a schema this build does not speak": a_document(schema_version=99),
    "a deployment word inside a node": a_document(
        nodes=[{"kind": "task", "node_id": "do", "title": "Do",
                "instance_id": "claude-dev", "resources": []}]),
    "half a binding": a_document(
        nodes=[{"kind": "task", "node_id": "do", "title": "Do",
                "role_id": "role-implementer", "resources": []}]),
    "nodes that are not a list": a_document(nodes={"do": {}}),
    "more nodes than a draft may carry": a_document(
        nodes=[{"kind": "task", "node_id": f"n{index}", "title": "T",
                "resources": []} for index in range(MAX_DRAFT_NODES + 1)],
        edges=[]),
    "more edges than a draft may carry": a_document(
        edges=[{"from_node": "confirm-gate", "to_node": "do"}]
        * (MAX_DRAFT_EDGES + 1)),
}


def store_of(tmp_path):
    return TemplateStore(tmp_path)


def save(store, document, *, workflow=WORKFLOW, saved_at=SAVED_AT):
    return store.save_draft(WorkflowDraft(
        workflow_id=workflow, saved_at=saved_at, document=document))


def publish(store, document, *, workflow=WORKFLOW, revision=1):
    return store.save(publish_candidate(
        document, workflow_id=workflow, revision=revision))


# --- the round trip ------------------------------------------------------


def test_a_saved_draft_reads_back_byte_identical_through_a_fresh_store(tmp_path):
    """A draft is durable, so a second process must see exactly what was saved.

    The re-read goes through a NEW ``TemplateStore`` over the same directory
    rather than through the instance that wrote it: a store that answered from
    something it happened to be holding would pass a same-instance read and tell
    a browser on the next process nothing.
    """
    written = save(store_of(tmp_path), a_document())
    assert written.created and written.path.name == DRAFT_NAME

    later = store_of(tmp_path).load_draft(WORKFLOW)
    assert later is not None
    assert later.workflow_id == WORKFLOW and later.saved_at == SAVED_AT
    assert later.settled() == parse_document(a_document())
    # And what is on disk is the canonical envelope, not a rendering of it:
    # canonical text and one closing newline, spelled rather than borrowed from
    # the writer, so the two cannot agree by sharing a function.
    assert written.path.read_bytes() == (
        canonical_json(later.as_dict()) + "\n").encode("utf-8")


def test_saving_the_same_draft_again_writes_nothing_and_moves_no_byte(tmp_path):
    """A client whose reply was lost re-sends the same drawing, not a change."""
    store = store_of(tmp_path)
    first = save(store, a_document())
    before = first.path.read_bytes()
    again = save(store, a_document())
    assert (first.created, again.created) == (True, False)
    assert again.path == first.path and first.path.read_bytes() == before


def test_an_identical_save_keeps_the_moment_the_screen_is_already_showing(tmp_path):
    """Idempotence here is about the DOCUMENT, not about the file.

    Re-stamping an unchanged drawing with a fresh clock would rewrite the file
    and move a timestamp a screen is displaying, which turns an identical
    request into a change. The clock is handed exactly two instants and the
    second is never spent, so a re-stamp would fail on the clock itself.
    """
    store = store_of(tmp_path)
    clock = clock_of(SAVED_AT, LATER)
    assert saved_draft(store, WORKFLOW, parse_document(a_document()), clock)
    assert not saved_draft(store, WORKFLOW, parse_document(a_document()), clock)
    assert store.load_draft(WORKFLOW).saved_at == SAVED_AT
    # A different drawing DOES spend the clock, and moves the moment with it.
    changed = parse_document(a_document(title="A different drawing"))
    assert not saved_draft(store, WORKFLOW, changed, clock)
    assert store.load_draft(WORKFLOW).saved_at == LATER


def test_discarding_a_draft_leaves_every_revision_standing(tmp_path):
    """The one delete this store has, and it removes nothing durable.

    A draft was never history. Every revision beside it is, and none of them is
    removable by any call on this store -- so the discard is asserted against
    the revisions that survive it rather than only against its own return value.
    """
    store = store_of(tmp_path)
    publish(store, a_document())
    save(store, a_document(title="Still drawing"))
    assert store.discard_draft(WORKFLOW) is True
    assert store.discard_draft(WORKFLOW) is False
    assert store.load_draft(WORKFLOW) is None
    assert store.revisions(WORKFLOW) == (1,)
    assert store.load(WORKFLOW, 1).title == a_document()["title"]


# --- a draft is never a revision -----------------------------------------


def test_a_draft_is_never_listed_as_a_revision_and_never_read_back_as_one(tmp_path):
    """The partition the two halves keep without either knowing about the other.

    ``revisions`` counts ``<digits>.json`` and a draft is not a number;
    ``revision_path`` builds its name from an ``int`` and so can never land on
    the draft. Both directions are asserted, because a build that broke only one
    of them would still pass a test that checked the other.
    """
    store = store_of(tmp_path)
    save(store, a_document())
    assert store.has_draft(WORKFLOW) and store.revisions(WORKFLOW) == ()

    draft_path = store.draft_path(WORKFLOW)
    assert draft_path.is_file() and not draft_path.stem.isdigit()
    for revision in range(1, 64):
        assert store.revision_path(WORKFLOW, revision) != draft_path

    # And a workflow that holds BOTH lists only the numbered one.
    publish(store, a_document())
    assert store.revisions(WORKFLOW) == (1,)
    assert store.load_draft(WORKFLOW) is not None
    assert {path.name for path in draft_path.parent.iterdir()} == {
        DRAFT_NAME, "1.json"}


def test_a_file_called_draft_json_that_nobody_saved_is_still_not_a_revision(
        tmp_path):
    """The rule is about the NAME, so a file put there by hand obeys it too.

    The name is SPELLED here and the production constant is pinned equal to it,
    rather than read off production and used to build the file: a test that took
    both sides from one value would agree with itself whatever that value became
    -- including a value that collides with a revision.
    """
    assert DRAFT_NAME == "draft.json"
    store = store_of(tmp_path)
    publish(store, a_document())
    directory = store.revision_path(WORKFLOW, 1).parent
    (directory / "draft.json").write_text("{}", encoding="utf-8", newline="\n")
    (directory / "notes.txt").write_text("x", encoding="utf-8", newline="\n")
    (directory / "2.json.bak").write_text("{}", encoding="utf-8", newline="\n")
    assert store.revisions(WORKFLOW) == (1,)


def test_a_draft_cannot_be_published_in_place_of_a_revision(tmp_path):
    """Publishing reads the draft and writes a TEMPLATE; it never moves a file.

    The published revision carries the two words a draft has not got, and the
    draft file is still exactly the bytes it was -- so nothing renamed a draft
    into a revision, which is the one road that could put an unfinished document
    where a finished one is promised to be.
    """
    store = store_of(tmp_path)
    draft_bytes = save(store, a_document()).path.read_bytes()
    published = publish(store, store.load_draft(WORKFLOW).settled())
    assert published.created
    assert store.draft_path(WORKFLOW).read_bytes() == draft_bytes
    document = store.load(WORKFLOW, 1).as_dict()
    assert set(document) - set(DRAFT_FIELDS) == set(NOT_YET_FIELDS)
    assert (document["template_id"], document["revision"]) == (WORKFLOW, 1)


# --- incomplete is stored and explained ----------------------------------


@pytest.mark.parametrize("reason", sorted(INCOMPLETE))
def test_an_incomplete_draft_is_stored_and_comes_back_explained(tmp_path, reason):
    """A workflow under an editor's hand is not a template, and that is fine."""
    store = store_of(tmp_path)
    document = INCOMPLETE[reason]
    assert save(store, document).created

    state = workflow_state(store, WORKFLOW)
    assert state["publishable"] is False
    assert state["draft"]["document"] == parse_document(document)
    assert state["diagnostics"], reason
    for row in state["diagnostics"]:
        assert set(row) == {"code", "message", "node_id", "field"}
        assert row["code"] in DIAGNOSTIC_CODES
        assert row["message"]
    # It survives the round trip unchanged: an unfinished drawing is not
    # repaired, normalized away, or quietly dropped on the way to disk.
    assert store_of(tmp_path).load_draft(WORKFLOW).settled() == \
        parse_document(document)


@pytest.mark.parametrize("reason", sorted(INCOMPLETE))
def test_an_incomplete_draft_is_refused_the_publish_it_was_warned_about(
        tmp_path, reason):
    """One judge, two callers: what is unpublishable is what publish refuses.

    ``draft_diagnostics`` swallows the refusal and ``publish_candidate`` raises
    it. Asking the question through two code paths is how a screen comes to say
    ``publishable`` about a document the publish route then refuses, so the two
    answers are compared row for row.
    """
    document = parse_document(INCOMPLETE[reason])
    with pytest.raises(DraftRefused) as refused:
        publish_candidate(document, workflow_id=WORKFLOW, revision=1)
    assert refused.value.diagnostics == draft_diagnostics(
        document, workflow_id=WORKFLOW, revision=1)
    assert store_of(tmp_path).revisions(WORKFLOW) == ()


def test_a_draft_that_would_construct_carries_no_diagnostics_at_all(tmp_path):
    """The other side of the same judgement, so neither direction is assumed."""
    store = store_of(tmp_path)
    save(store, a_document())
    state = workflow_state(store, WORKFLOW)
    assert state["diagnostics"] == [] and state["publishable"] is True
    assert state["next_revision"] == 1
    assert draft_diagnostics(
        parse_document(a_document()), workflow_id=WORKFLOW, revision=1) == ()
    assert isinstance(publish_candidate(
        parse_document(a_document()), workflow_id=WORKFLOW, revision=1),
        GraphTemplate)


# --- foreign is refused outright -----------------------------------------


@pytest.mark.parametrize("reason", sorted(FOREIGN))
def test_a_foreign_draft_is_refused_and_nothing_at_all_is_stored(tmp_path, reason):
    """Everything a draft carries has to be something a template could carry."""
    store = store_of(tmp_path)
    with pytest.raises(ContractError):
        parse_document(FOREIGN[reason])
    with pytest.raises(ContractError):
        WorkflowDraft(workflow_id=WORKFLOW, saved_at=SAVED_AT,
                      document=FOREIGN[reason])
    assert store.load_draft(WORKFLOW) is None
    assert not store.draft_path(WORKFLOW).exists()


def test_a_draft_missing_one_of_its_own_words_is_refused_as_foreign(tmp_path):
    """The key set is CLOSED in both directions, not merely bounded above."""
    for absent in sorted(DRAFT_FIELDS):
        document = a_document()
        document.pop(absent)
        with pytest.raises(WorkflowDraftError) as refused:
            parse_document(document)
        assert absent in str(refused.value)
    assert store_of(tmp_path).load_draft(WORKFLOW) is None


def test_incomplete_and_foreign_are_two_answers_and_not_one(tmp_path):
    """The whole design of this contract, said once, on one workflow.

    A dangling edge is saved and explained; the same document plus a word no
    template could carry is refused with nothing written. If these two ever
    became one answer, a person drawing a workflow would either be unable to
    save anything unfinished, or would be able to store a document the publish
    road could never read.
    """
    store = store_of(tmp_path)
    incomplete = INCOMPLETE["a dangling edge"]
    assert save(store, incomplete).created
    standing = store.draft_path(WORKFLOW).read_bytes()
    assert workflow_state(store, WORKFLOW)["diagnostics"]

    foreign = dict(incomplete, template_id=WORKFLOW)
    with pytest.raises(ContractError):
        save(store, foreign)
    assert store.draft_path(WORKFLOW).read_bytes() == standing


# --- the stored envelope answers for itself ------------------------------


@pytest.mark.parametrize("planted,expected", [
    ({}, WorkflowDraftError),
    ({"schema_version": 99}, WorkflowDraftError),
    ({"workflow_id": "somebody-else"}, StoreError),
])
def test_a_stored_draft_this_build_cannot_read_is_refused_not_half_read(
        tmp_path, planted, expected):
    """Written by us is not a reason to trust it coming back.

    ``load_draft`` reports a STORE fault rather than a contract one: the caller
    supplied a workflow id and a durable file contradicted it, which is nobody's
    request error.
    """
    store = store_of(tmp_path)
    path = save(store, a_document()).path
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope.update(planted)
    if not planted:
        envelope.pop("saved_at")
    path.write_text(json.dumps(envelope), encoding="utf-8", newline="\n")
    with pytest.raises((expected, StoreError)):
        store.load_draft(WORKFLOW)


def test_a_stored_draft_that_is_not_json_is_a_store_fault(tmp_path):
    store = store_of(tmp_path)
    path = save(store, a_document()).path
    path.write_text("not json at all", encoding="utf-8", newline="\n")
    with pytest.raises(StoreError, match="not JSON"):
        store.load_draft(WORKFLOW)


def test_a_draft_whose_document_was_replaced_answers_only_for_what_it_settled():
    """The snapshot-and-witness this package uses wherever a contract answers.

    Caught by IDENTITY first, which reads nothing: a mapping put here after
    validation would otherwise answer ``items`` however it liked and the
    contract would report the answer as the draft.
    """
    draft = WorkflowDraft(
        workflow_id=WORKFLOW, saved_at=SAVED_AT, document=a_document())
    settled = draft.settled()
    object.__setattr__(draft, "document", dict(settled, title="Something else"))
    with pytest.raises(WorkflowDraftError, match="answers only for what it settled"):
        draft.settled()
    with pytest.raises(WorkflowDraftError):
        draft.as_dict()


def test_the_store_takes_a_draft_and_no_lookalike(tmp_path):
    class Sneaky(WorkflowDraft):
        pass

    store = store_of(tmp_path)
    with pytest.raises(StoreError, match="exactly a WorkflowDraft"):
        store.save_draft(Sneaky(workflow_id=WORKFLOW, saved_at=SAVED_AT,
                                document=a_document()))
    with pytest.raises(StoreError):
        store.save_draft(a_document())
    assert not store.draft_path(WORKFLOW).exists()


@pytest.mark.parametrize("name", ["../escape", "has space", "", "a/b"])
def test_a_workflow_name_the_contract_refuses_never_reaches_a_draft_path(
        tmp_path, name):
    """The set of names this store accepts is the set the CONTRACT accepts."""
    store = store_of(tmp_path)
    for call in (store.draft_path, store.has_draft, store.load_draft,
                 store.discard_draft):
        with pytest.raises(StoreError):
            call(name)


# --- what a screen is told about a workflow ------------------------------


def test_a_workflow_nothing_is_stored_for_is_a_state_and_not_a_refusal(tmp_path):
    """It is where every workflow starts, and a person must be able to open it."""
    assert workflow_state(store_of(tmp_path), "workflow-nobody-drew") == {
        "workflow_id": "workflow-nobody-drew",
        "revisions": [], "latest_revision": None, "unreadable_revisions": [],
        "published": None, "draft": None, "diagnostics": [],
        # `unchanged` is False here for a reason worth stating: a workflow with
        # nothing published has nothing to be unchanged FROM, and its first
        # revision always says something new even when the drawing is empty.
        "publishable": False, "unchanged": False, "next_revision": 1,
    }


def test_a_workflow_with_revisions_and_no_draft_has_nothing_to_publish(tmp_path):
    """"Nothing to publish" and "a draft that would be refused" are two facts.

    Both answer ``publishable: false`` and they must never share a diagnostic:
    one person has drawn nothing since the last release, and the other has drawn
    something that does not construct.
    """
    store = store_of(tmp_path)
    publish(store, a_document())
    state = workflow_state(store, WORKFLOW)
    assert state["publishable"] is False and state["diagnostics"] == []
    assert state["draft"] is None and state["next_revision"] == 2
    assert state["published"] == store.load(WORKFLOW, 1).as_dict()


def test_a_revision_this_build_cannot_read_is_named_rather_than_dropped(tmp_path):
    """A revision you cannot read is a fact; a revision you cannot see is a lie."""
    store = store_of(tmp_path)
    publish(store, a_document())
    stale = store.load(WORKFLOW, 1).as_dict()
    stale["schema_version"] = 99
    store.revision_path(WORKFLOW, 1).write_text(
        json.dumps(stale), encoding="utf-8", newline="\n")
    state = workflow_state(store, WORKFLOW)
    assert state["unreadable_revisions"] == [1] and state["published"] is None
    assert state["revisions"] == [1] and state["next_revision"] == 2
    assert workflow_rows(store) == [{
        "workflow_id": WORKFLOW, "title": None, "latest_revision": 1,
        "revisions": [1], "has_draft": False, "unreadable": True}]


def test_a_list_row_reports_the_draft_without_opening_it(tmp_path):
    """Whether a workflow HAS one is a fact about the directory.

    Reading every draft in a project to render a list would make one unreadable
    file refuse the whole list, so the row is asserted to survive a draft that
    ``load_draft`` itself refuses.
    """
    store = store_of(tmp_path)
    publish(store, a_document())
    store.draft_path(WORKFLOW).write_text(
        "not a draft", encoding="utf-8", newline="\n")
    assert workflow_rows(store) == [{
        "workflow_id": WORKFLOW, "title": a_document()["title"],
        "latest_revision": 1, "revisions": [1], "has_draft": True,
        "unreadable": False}]
    with pytest.raises(StoreError):
        store.load_draft(WORKFLOW)


def test_the_starters_are_read_off_the_wheel_and_are_nobodys_workflow(tmp_path):
    """What the build ships to start from, and it is not this project's state.

    A starter carries the bundled ``template_id`` and ``revision`` because that
    is what the shipped file says. It is not a workflow: a fresh project holds
    none, and saving one as a draft is what makes it somebody's.
    """
    store = store_of(tmp_path)
    assert store.workflows() == () and workflow_rows(store) == []

    rows = starters()
    assert [row["starter_id"] for row in rows] == sorted(
        path.stem for path in TEMPLATE_DIR.glob("*.json"))
    for row in rows:
        assert set(row) == {"starter_id", "title", "document"}
        assert row["document"] == load_template(row["starter_id"]).as_dict()

    # A starter's document is a DRAFT once its two extra words are removed, and
    # that draft publishes as revision 1 of the workflow its user named.
    document = {key: value for key, value in rows[0]["document"].items()
                if key not in NOT_YET_FIELDS}
    assert save(store, document, workflow="my-own-cycle").created
    assert publish(store, document, workflow="my-own-cycle").created
    assert store.load("my-own-cycle", 1).template_id == "my-own-cycle"
