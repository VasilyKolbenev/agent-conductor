"""Publishing a revision may not destroy a draft nobody published.

`publish_revision` reads the draft, judges it against the digest the reviewer
echoed, writes the revision and then consumes the draft. Those are four steps
against one mutable file, and the server that runs them is a
`ThreadingHTTPServer`, so a second client's save could land between the judging
and the consuming. The publish then unlinked whatever was there: the reviewed
document became revision 1 correctly, and the OTHER client's work was deleted
with no revision holding it and nothing anywhere recording that it had existed.

Two mechanisms close it, and they close different halves:

- `TemplateStore.discard_draft(expecting=...)` consumes only the draft it is
  told it is consuming, so a draft that arrived in the window is left standing
  rather than unlinked. This is what makes the outcome CORRECT;
- `TemplateStore.transaction(workflow_id)`, held across `saved_draft` and
  across the whole publish chain, is what makes it ATOMIC -- so the two orders
  below are the only two that exist, rather than the two that happen to be
  survivable.

The permitted outcomes, and there are exactly two:

1. the second save lands before the review is judged -> the publish is refused
   as stale and the second draft stands;
2. the second save lands after the publish -> the revision is written and the
   second draft stands beside it.

In neither does a saved draft disappear. Each mechanism has its own witness
here, because a module that tested only the outcome would stay green if the
transaction were deleted, and one that tested only the serialization would stay
green if the comparison were.
"""
from __future__ import annotations

import threading

import pytest

from conductor.command import studio_routes
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import saved_draft, workflow_state

WORKFLOW = "release-check"
NOW = "2026-01-01T00:00:00Z"
#: Long enough that a thread which is going to make progress has made it, short
#: enough that a deadlock is a failed test rather than a hung suite.
WINDOW = 2.0


def a_document(title):
    return {
        "schema_version": 1,
        "title": title,
        "nodes": [{"node_id": "draft-notes", "kind": "task",
                   "title": "Draft the notes", "resources": []}],
        "edges": [],
    }


def a_store(tmp_path):
    (tmp_path / "conductor").mkdir(parents=True, exist_ok=True)
    return TemplateStore(tmp_path)


def save(store, title):
    return saved_draft(store, WORKFLOW, a_document(title), lambda: NOW)


def reviewing(store):
    """The publish body a window sends after reviewing the STORED draft."""
    state = workflow_state(store, WORKFLOW)
    return {"revision": state["next_revision"],
            "reviewed_digest": state["draft"]["digest"]}


def standing_title(store):
    draft = store.load_draft(WORKFLOW)
    return None if draft is None else draft.document["title"]


def blocked_while(open_window, run_the_other, *, opened, finished):
    """Start one thread, park it in its window, and prove a second cannot pass.

    The two serialization tests below are the same choreography over different
    critical sections, and each was over the project's function-length limit
    written out in full. Everything specific to a test stays in the test: this
    holds only the ordering, and it asserts the ordering.

    Args:
        open_window: Runs the operation that takes the workflow and parks.
        run_the_other: Runs the operation that must not get in.
        opened: Set by `open_window` once it is inside its critical section.
        finished: Set by `run_the_other` when it completes.

    Returns:
        The two threads, already joined.
    """
    first = threading.Thread(target=open_window)
    first.start()
    assert opened.wait(WINDOW), "the first operation never reached its window"
    second = threading.Thread(target=run_the_other)
    second.start()
    return first, second


def released(first, second, release, finished):
    """Let the parked thread go, join both, and require the second to complete."""
    release.set()
    first.join(WINDOW)
    second.join(WINDOW)
    assert finished.is_set(), "the waiting operation never completed"
    assert not first.is_alive() and not second.is_alive()


# -- the outcome: a draft saved in the window is not deleted ------------------


def test_a_save_landing_inside_the_publish_window_is_not_deleted(
        tmp_path, monkeypatch):
    """The reported defect, interleaved at exactly the point that was open.

    The second save is driven from inside `TemplateStore.save`, which is the
    one instant between "this revision is on disk" and "consume the draft".
    Measured before the fix as a published revision carrying the reviewed title
    and a workflow holding no draft at all.
    """
    store = a_store(tmp_path)
    save(store, "REVIEWED FIRST CLIENT DRAFT")
    body = reviewing(store)
    landed = []
    real_save = TemplateStore.save

    def save_then_another_client_saves(self, template):
        published = real_save(self, template)
        if not landed:
            landed.append(True)
            save(self, "SECOND CLIENT UNPUBLISHED WORK")
        return published

    monkeypatch.setattr(TemplateStore, "save", save_then_another_client_saves)

    status, payload = studio_routes.publish_revision(store, WORKFLOW, body)

    assert (status, payload["title"]) == (201, "REVIEWED FIRST CLIENT DRAFT")
    assert standing_title(store) == "SECOND CLIENT UNPUBLISHED WORK"


def test_a_save_before_the_review_is_judged_makes_the_publish_stale(tmp_path):
    """The first permitted order: the publish is refused and the draft stands."""
    from conductor.command.api_contracts import ApiRefusal

    store = a_store(tmp_path)
    save(store, "REVIEWED FIRST CLIENT DRAFT")
    body = reviewing(store)
    save(store, "SECOND CLIENT UNPUBLISHED WORK")

    with pytest.raises(ApiRefusal):
        studio_routes.publish_revision(store, WORKFLOW, body)

    assert store.revisions(WORKFLOW) == ()
    assert standing_title(store) == "SECOND CLIENT UNPUBLISHED WORK"


def test_a_stale_review_is_refused_as_a_conflict_and_not_as_a_bad_request(
        tmp_path):
    """`draft_changed`, 409 -- because the caller did nothing wrong.

    It answered `contract_invalid` and 422, which is what this route says to a
    body it cannot parse. A window told that can only offer to send the same
    review again; told this, it knows to fetch the draft that is standing and
    put THAT in front of the person. The distinction is the whole finding: the
    refusal was safe and unrecoverable at the same time.
    """
    from conductor.command.api_contracts import ApiRefusal

    store = a_store(tmp_path)
    save(store, "REVIEWED FIRST CLIENT DRAFT")
    body = reviewing(store)
    save(store, "SECOND CLIENT UNPUBLISHED WORK")

    with pytest.raises(ApiRefusal) as refused:
        studio_routes.publish_revision(store, WORKFLOW, body)

    assert refused.value.code == "draft_changed"
    assert refused.value.status == 409
    assert "read it again" in refused.value.message


def test_a_malformed_publish_body_is_still_an_ordinary_contract_refusal(
        tmp_path):
    """The over-correction control: the new code must not swallow the old one.

    A code that answered every publish refusal would tell a window to re-read
    and retry after a request that will never succeed however often it is sent.
    """
    from conductor.command.api_contracts import ApiRefusal

    store = a_store(tmp_path)
    save(store, "A DRAFT")

    with pytest.raises(ApiRefusal) as refused:
        studio_routes.publish_revision(
            store, WORKFLOW, {"revision": 1, "reviewed_digest": 17})

    assert refused.value.code == "contract_invalid"


def test_a_save_after_the_publish_stands_beside_the_revision(tmp_path):
    """The second permitted order: the revision is written, the draft is new."""
    store = a_store(tmp_path)
    save(store, "REVIEWED FIRST CLIENT DRAFT")
    status, _ = studio_routes.publish_revision(store, WORKFLOW, reviewing(store))
    assert status == 201

    save(store, "SECOND CLIENT UNPUBLISHED WORK")

    assert store.revisions(WORKFLOW) == (1,)
    assert standing_title(store) == "SECOND CLIENT UNPUBLISHED WORK"
    assert store.load(WORKFLOW, 1).as_dict()["title"] == "REVIEWED FIRST CLIENT DRAFT"


# -- the mechanism: consume only what was named ------------------------------


def test_discard_consumes_the_named_draft_and_nothing_else(tmp_path):
    """The comparison on its own, with no publish and no threads near it."""
    store = a_store(tmp_path)
    save(store, "FIRST")
    named = store.load_draft(WORKFLOW)
    save(store, "SECOND")

    assert store.discard_draft(WORKFLOW, expecting=named) is False
    assert standing_title(store) == "SECOND"


def test_discard_consumes_the_draft_it_names_when_that_is_what_stands(tmp_path):
    """The over-correction control: naming a draft must not refuse to consume it.

    A comparison that refused everything would pass every test above while
    leaving a consumed draft behind on every publish, which is the failure this
    control exists to catch.
    """
    store = a_store(tmp_path)
    save(store, "FIRST")
    named = store.load_draft(WORKFLOW)

    assert store.discard_draft(WORKFLOW, expecting=named) is True
    assert store.load_draft(WORKFLOW) is None


def test_discarding_by_hand_still_consumes_whatever_stands(tmp_path):
    """Naming none means "whatever is there", which is what a hand-discard is."""
    store = a_store(tmp_path)
    save(store, "FIRST")

    assert store.discard_draft(WORKFLOW) is True
    assert store.load_draft(WORKFLOW) is None


def test_an_ordinary_publish_still_consumes_the_draft_it_published(tmp_path):
    """The other over-correction control, on the road a person actually walks."""
    store = a_store(tmp_path)
    save(store, "THE ONLY DRAFT")

    status, _ = studio_routes.publish_revision(store, WORKFLOW, reviewing(store))

    assert status == 201
    assert store.load_draft(WORKFLOW) is None
    assert store.has_draft(WORKFLOW) is False


def test_a_caller_supplied_document_still_leaves_the_draft_standing(tmp_path):
    """A publish that named its own bytes said nothing about the draft."""
    store = a_store(tmp_path)
    save(store, "UNTOUCHED DRAFT")

    status, _ = studio_routes.publish_revision(
        store, WORKFLOW,
        {"revision": 1, "document": a_document("SUPPLIED DIRECTLY")})

    assert status == 201
    assert standing_title(store) == "UNTOUCHED DRAFT"


# -- the mechanism: one workflow, one writer at a time -----------------------


def test_a_save_cannot_run_while_a_publish_holds_the_workflow(
        tmp_path, monkeypatch):
    """The transaction, measured as serialization rather than as an outcome.

    Real threads, one real store. The publishing thread parks inside its own
    critical section and the saving thread is started there; if the workflow
    were not held, that save would complete while the publish was mid-chain --
    which is precisely the window the defect lived in. The saving thread is
    required to be still waiting, and then to complete once the publish lets go.

    This is the witness the outcome tests cannot be: with the comparison in
    place the DATA survives either way, so only a test that looks at the timing
    can tell a held workflow from an unheld one.
    """
    store = a_store(tmp_path)
    save(store, "REVIEWED FIRST CLIENT DRAFT")
    body = reviewing(store)
    inside = threading.Event()
    release = threading.Event()
    saved = threading.Event()
    real_save = TemplateStore.save

    def park_inside_the_window(self, template):
        published = real_save(self, template)
        inside.set()
        release.wait(WINDOW)
        return published

    monkeypatch.setattr(TemplateStore, "save", park_inside_the_window)

    def second_client():
        save(store, "SECOND CLIENT UNPUBLISHED WORK")
        saved.set()

    publisher, saver = blocked_while(
        lambda: studio_routes.publish_revision(store, WORKFLOW, body),
        second_client, opened=inside, finished=saved)
    try:
        # The save must be BLOCKED here. A save that completes has walked into
        # the middle of a publish, which is the whole defect.
        assert not saved.wait(0.4), (
            "a draft was saved while a publish held the workflow")
    finally:
        released(publisher, saver, release, saved)

    assert store.revisions(WORKFLOW) == (1,)
    assert standing_title(store) == "SECOND CLIENT UNPUBLISHED WORK"


def test_the_workflow_gate_holds_one_workflow_and_not_the_store(tmp_path):
    """Two workflows share nothing, so one must not wait for the other.

    A gate taken on the store rather than on the workflow would serialize every
    editor of every workflow in the project behind whichever one is publishing.
    """
    store = a_store(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def hold_one_workflow():
        with store.transaction("workflow-a"):
            entered.set()
            release.wait(WINDOW)

    def save_the_other():
        saved_draft(store, "workflow-b", a_document("OTHER"), lambda: NOW)
        finished.set()

    holder = threading.Thread(target=hold_one_workflow)
    holder.start()
    assert entered.wait(WINDOW)
    other = threading.Thread(target=save_the_other)
    other.start()
    try:
        assert finished.wait(WINDOW), (
            "a save on one workflow waited for a transaction on another")
    finally:
        release.set()
        holder.join(WINDOW)
        other.join(WINDOW)


def test_the_transaction_is_reentrant_for_the_thread_that_holds_it(tmp_path):
    """The publish chain calls store methods that take the gate for themselves.

    A non-reentrant gate would deadlock the first publish this product ever
    ran, so this is not a refinement -- it is the reason the chain works at all.
    """
    store = a_store(tmp_path)
    save(store, "FIRST")

    with store.transaction(WORKFLOW):
        assert store.load_draft(WORKFLOW) is not None
        save(store, "SECOND")
        assert store.discard_draft(WORKFLOW) is True

    assert store.load_draft(WORKFLOW) is None


def test_two_saves_cannot_both_be_the_call_that_created_the_draft(tmp_path):
    """`saved_draft` decides from a read, so the read and the write are one step.

    It reads the standing draft, decides whether this document is the same one
    (reusing its `saved_at`) or a new one (stamping the clock), and only then
    writes. Both halves take the workflow gate for their own sake, but the
    DECISION spans them: a save that completes in between leaves the first
    caller writing over a draft it was told did not exist, and both callers
    answering 201 for the same first draft.

    The window is entered through the clock, which is the one thing `saved_draft`
    calls between its read and its write.
    """
    store = a_store(tmp_path)
    stamping = threading.Event()
    release = threading.Event()
    other_finished = threading.Event()
    stamps = iter(["2026-01-01T00:00:0%dZ" % n for n in range(1, 9)])
    created = []

    def parking_clock():
        moment = next(stamps)
        if not stamping.is_set():
            stamping.set()
            release.wait(WINDOW)
        return moment

    def first_client():
        created.append(("first", saved_draft(
            store, WORKFLOW, a_document("FIRST"), parking_clock)))

    def second_client():
        created.append(("second", saved_draft(
            store, WORKFLOW, a_document("SECOND"), lambda: NOW)))
        other_finished.set()

    first, second = blocked_while(
        first_client, second_client, opened=stamping, finished=other_finished)
    try:
        assert not other_finished.wait(0.4), (
            "a second save completed inside another save's read-decide-write")
    finally:
        released(first, second, release, other_finished)

    assert [row for row in created if row[1]] == [("first", True)], created
