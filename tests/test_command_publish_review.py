"""Publishing says something new, or it does not happen.

`Publish` was one click with no interstitial: no target revision shown before
the write, no summary of what would change, no validation result on the same
screen, and no way to stand down once the pointer was over the button. The worst
of it was quieter than that. Publishing a draft nobody had edited created a
second revision carrying the SAME document under a new number -- a durable
record of an edit that never happened, which no reader could tell from a real
one afterwards, and which the store's own immutability then preserved forever.

This module holds the half that must be true whatever the screen does. The
refusal is on the ROUTE, not on the button: a client that never read the state,
or read it and posted anyway, must not be able to write that record. The screen
computing the same answer for the button's sake is a convenience; this is the
rule.

What is deliberately NOT here: the review panel itself. A confirmation a user
can see belongs in front of a browser, and it is held in `test_studio_*` and in
the browser gate. The claim here is narrower and stronger -- that a publish
which would say nothing new is refused even when nobody is looking.
"""
from __future__ import annotations

import pytest

from conductor.command.graph_template import GraphTemplate
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import (
    saved_draft, unchanged_from_published, workflow_state)

WORKFLOW = "release-check"


def a_document(title="Release check", node_title="Draft the notes"):
    return {
        "schema_version": 1,
        "title": title,
        "nodes": [{"node_id": "draft-notes", "kind": "task",
                   "title": node_title, "resources": []}],
        "edges": [],
    }


def a_store(tmp_path):
    (tmp_path / "conductor").mkdir(parents=True, exist_ok=True)
    return TemplateStore(tmp_path)


def a_draft(store, document):
    """Store one draft through the production road the save route takes."""
    return saved_draft(store, WORKFLOW, document, lambda: "2026-01-01T00:00:00Z")


def reviewing(store):
    """The publish body a window sends after reviewing the STORED draft.

    The digest is read out of the workflow state, which is exactly where a real
    window gets it: the read carries it, the window echoes it back, and nothing
    in the browser hashes anything.
    """
    return {"revision": workflow_state(store, WORKFLOW)["next_revision"],
            "reviewed_digest": workflow_state(store, WORKFLOW)["draft"]["digest"]}


def publish(store, document, revision):
    settled = dict(document)
    settled["template_id"] = WORKFLOW
    settled["revision"] = revision
    return store.save(GraphTemplate.from_dict(settled))


# -- the comparison itself ---------------------------------------------------


def test_a_draft_that_repeats_the_standing_revision_says_nothing_new():
    """The two documents differ in exactly the fields a draft never carries.

    Comparing the stored shapes would call every draft different from every
    revision, because a draft has no `template_id` and no `revision` at all.
    The draft is therefore turned into the candidate it would publish AS, and
    both sides are canonicalised by the contract that owns them.
    """
    published = dict(a_document(), template_id=WORKFLOW, revision=1)

    assert unchanged_from_published(
        a_document(), published, workflow_id=WORKFLOW, revision=2) is True


def test_a_draft_that_changed_one_word_says_something_new():
    """The other direction, so the comparison is not simply permissive."""
    published = dict(a_document(), template_id=WORKFLOW, revision=1)

    assert unchanged_from_published(
        a_document(node_title="Draft the release notes"), published,
        workflow_id=WORKFLOW, revision=2) is False


def test_a_workflow_with_nothing_published_is_never_unchanged():
    """A first revision always says something new, even when it is empty."""
    assert unchanged_from_published(
        a_document(), None, workflow_id=WORKFLOW, revision=1) is False


def test_a_draft_that_will_not_construct_is_refused_and_never_unchanged():
    """A broken draft is not "unchanged"; it is refused, and diagnostics say so.

    Answering True here would hide a draft nobody can publish behind a
    reassuring word, and the screen would disable the button for the wrong
    reason -- telling a user their edit was a no-op when it was a mistake.
    """
    published = dict(a_document(), template_id=WORKFLOW, revision=1)
    broken = a_document()
    broken["edges"] = [{"from_node": "draft-notes", "to_node": "nowhere"}]

    assert unchanged_from_published(
        broken, published, workflow_id=WORKFLOW, revision=2) is False


# -- what the screen is told --------------------------------------------------


def test_a_workflow_whose_draft_repeats_its_revision_is_not_publishable(tmp_path):
    store = a_store(tmp_path)
    publish(store, a_document(), 1)
    a_draft(store, a_document())

    state = workflow_state(store, WORKFLOW)

    assert state["unchanged"] is True
    assert state["publishable"] is False
    # And it is not publishable for THIS reason, not because it is invalid.
    assert state["diagnostics"] == []


def test_an_edited_draft_is_publishable_again(tmp_path):
    """The state must recover: an edit after a no-op draft publishes normally."""
    store = a_store(tmp_path)
    publish(store, a_document(), 1)
    a_draft(store, a_document(node_title="Draft them well"))

    state = workflow_state(store, WORKFLOW)

    assert state["unchanged"] is False
    assert state["publishable"] is True
    assert state["next_revision"] == 2


# -- the route refuses it, whatever the screen did ---------------------------


def test_the_route_refuses_a_publish_that_would_repeat_the_revision(tmp_path):
    """The rule is on the road, not on the button.

    Driven through the route rather than through the state, because a client
    that never read the state is exactly the caller this refusal exists for.
    """
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    publish(store, a_document(), 1)
    a_draft(store, a_document())

    with pytest.raises(ApiRefusal):
        publish_revision(store, WORKFLOW, reviewing(store))

    assert store.revisions(WORKFLOW) == (1,)


def test_the_refusal_leaves_the_draft_standing_for_the_user_to_edit(tmp_path):
    """A refusal must not discard the drawing the user still has open."""
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    publish(store, a_document(), 1)
    a_draft(store, a_document())

    with pytest.raises(ApiRefusal):
        publish_revision(store, WORKFLOW, reviewing(store))

    assert store.load_draft(WORKFLOW) is not None


def test_a_publish_that_says_something_new_still_goes_through(tmp_path):
    """The over-correction control: the refusal must not refuse real work."""
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    publish(store, a_document(), 1)
    a_draft(store, a_document(title="Release check, revised"))

    status, payload = publish_revision(store, WORKFLOW, reviewing(store))

    assert status == 201
    assert payload["revision"] == 2
    assert store.revisions(WORKFLOW) == (1, 2)


def test_a_caller_supplied_document_is_held_to_the_same_rule(tmp_path):
    """The road that bypasses the draft bypasses nothing else.

    `publish_revision` accepts a document in the body instead of publishing the
    stored draft. That road must not be a way around the rule, or the refusal
    would be an inconvenience rather than a guarantee.
    """
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    publish(store, a_document(), 1)

    with pytest.raises(ApiRefusal):
        publish_revision(store, WORKFLOW,
                         {"revision": 2, "document": a_document()})

    assert store.revisions(WORKFLOW) == (1,)


# -- the review must publish the draft it reviewed ---------------------------


def test_a_draft_replaced_after_the_review_is_refused_rather_than_published(
        tmp_path):
    """The defect this section exists for, in the shape it really took.

    A window opens the review for draft A. Another client saves draft B. The
    first window is told nothing -- saving a draft publishes no frame, so there
    is no read to close the stale review. The person confirms what they read,
    and revision 1 used to be written from B: a revision nobody reviewed, and
    the store's immutability then kept it forever.

    The echo is what closes it. The window names WHICH draft it reviewed, and
    the route compares that against the draft it is about to write.
    """
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    a_draft(store, a_document(title="Reviewed on screen"))
    body = reviewing(store)

    a_draft(store, a_document(title="UNREVIEWED SERVER CHANGE"))

    with pytest.raises(ApiRefusal):
        publish_revision(store, WORKFLOW, body)

    assert store.revisions(WORKFLOW) == ()


def test_the_refusal_leaves_the_newer_draft_exactly_where_it_was(tmp_path):
    """A refused stale publish must not touch the draft that replaced it."""
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    a_draft(store, a_document(title="Reviewed on screen"))
    body = reviewing(store)
    a_draft(store, a_document(title="UNREVIEWED SERVER CHANGE"))

    with pytest.raises(ApiRefusal):
        publish_revision(store, WORKFLOW, body)

    standing = workflow_state(store, WORKFLOW)["draft"]["document"]
    assert standing["title"] == "UNREVIEWED SERVER CHANGE"


def test_a_review_of_the_current_draft_still_publishes(tmp_path):
    """The over-correction control: the echo must not refuse honest work."""
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    a_draft(store, a_document(title="Reviewed on screen"))

    status, payload = publish_revision(store, WORKFLOW, reviewing(store))

    assert status == 201
    assert payload["title"] == "Reviewed on screen"


def test_a_publish_naming_no_reviewed_draft_is_refused(tmp_path):
    """A client that echoes nothing has reviewed nothing this route can check.

    Left optional, the whole guarantee would be advisory: any caller could omit
    the field and get the old behaviour back.
    """
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    a_draft(store, a_document())

    with pytest.raises(ApiRefusal):
        publish_revision(store, WORKFLOW, {"revision": 1})

    assert store.revisions(WORKFLOW) == ()


def test_a_supplied_document_may_not_also_name_a_reviewed_draft(tmp_path):
    """The two roads are exclusive: a supplied document IS its own identity."""
    from conductor.command.api_contracts import ApiRefusal
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    a_draft(store, a_document())
    digest = workflow_state(store, WORKFLOW)["draft"]["digest"]

    with pytest.raises(ApiRefusal):
        publish_revision(store, WORKFLOW, {
            "revision": 1, "document": a_document(), "reviewed_digest": digest})


def test_an_idempotent_re_save_keeps_the_review_valid(tmp_path):
    """A digest names a DOCUMENT and not a moment.

    Saving the same drawing again is what a client whose reply was lost does.
    It must not invalidate a review of the identical document, or an ordinary
    retry would look like someone else's edit.
    """
    from conductor.command.studio_routes import publish_revision

    store = a_store(tmp_path)
    a_draft(store, a_document(title="Steady"))
    body = reviewing(store)
    a_draft(store, a_document(title="Steady"))

    status, _payload = publish_revision(store, WORKFLOW, body)

    assert status == 201
