"""The five workflow routes: the same door as every other command route.

Two things are proved here and they are not the same thing.

The first is the TRANSPORT CONTRACT for all SEVEN new routes, and it is derived
rather than remembered: they are computed as ``COMMAND_ROUTES`` minus the ten
that were already frozen, so a route added to the table later inherits every
refusal in this file without anybody having to add it. Each meets a foreign
Host, a query string, a method the table does not name, and -- where it mutates
-- a missing and a foreign Origin, a missing and a foreign CSRF token, an
oversized body and a body that is not one JSON object. The two run routes take
their transport contract from here and their behaviour from the module beside
this one, which also drives one road over a real loopback socket.

The second is the WORKFLOW ROAD: a draft saved and read back, a revision
published exactly once, a publish refused with diagnostics and zero durable
bytes, two editors colliding on one number, and -- said as an ORDER rather than
as an end state -- a draft cleared only after the revision file exists.

Above all of it, a module-scoped witness digests both shipped revisions before
the first test and again after the last, and refuses to start unless those
digests are the ones ``test_alpha6_dalio_revision`` already pinned -- an auditor
that cannot be shown to have been calibrated is an auditor reporting a number.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from conductor.command import studio_routes
from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.provider import ProviderContract
from conductor.command.api_contracts import ERROR_STATUS
from conductor.command.command_routes import COMMAND_ROUTES
from conductor.command.contracts import canonical_json
from conductor.command.graph_template import TEMPLATE_DIR, load_template
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import MAX_COMMAND_BODY_BYTES, CommandSession
from conductor.command.run_store import RunStore
from conductor.command.template_store import TemplateStore
from conductor.command.workflow_draft import NOT_YET_FIELDS

from tests.test_alpha6_dalio_revision import (
    REVISION_ONE_DIGEST,
    REVISION_TWO_DIGEST,
)
from tests.test_command_schema_doubles import DeepPlanAdapter
from tests.test_command_workflow_draft import (
    FOREIGN,
    INCOMPLETE,
    WORKFLOW,
    a_document,
)

NOW = "2026-08-28T12:00:00Z"
TOKEN = "current-process-token"
PORT = 7802
HOST = f"127.0.0.1:{PORT}"
ORIGIN = f"http://{HOST}"

#: The ten routes this surface was frozen with. Spelled once, so the seven the
#: Studio added are DERIVED from the live table rather than copied out of it: a
#: route added to ``COMMAND_ROUTES`` and not to this list joins every transport
#: claim below by itself.
FROZEN_TEN = (
    ("GET", "/command/session"),
    ("GET", "/command/runs/<run_id>"),
    ("GET", "/command/runs/<run_id>/controls"),
    ("POST", "/command/runs/<run_id>/proposals"),
    ("POST", "/command/runs/<run_id>/actions"),
    ("POST", "/command/runs/<run_id>/decisions"),
    ("POST", "/command/runs/<run_id>/graph"),
    ("POST", "/command/templates"),
    ("POST", "/command/runs/<run_id>/graph/from-template"),
    ("POST", "/command/runs/<run_id>/artifacts"),
)
NEW_ROUTES = tuple(row for row in COMMAND_ROUTES if row not in FROZEN_TEN)
NEW_GETS = tuple(row for row in NEW_ROUTES if row[0] == "GET")
NEW_POSTS = tuple(row for row in NEW_ROUTES if row[0] == "POST")
#: The one path the table admits under BOTH verbs, because listing runs and
#: opening one are the same noun asked two ways. It is excluded from the
#: verb-swap claim by NAME rather than by silence.
BOTH_VERBS = "/command/runs"
#: The two shipped files this module publishes documents derived from. Nothing
#: any test does may move one byte of either.
SHIPPED = {"dalio-v1": REVISION_ONE_DIGEST, "dalio-v2": REVISION_TWO_DIGEST}


def target(path):
    """One route pattern with every identity a path can carry substituted."""
    filled = path.replace("<workflow_id>", WORKFLOW).replace("<revision>", "1")
    assert "<" not in filled, filled
    return filled


NEW_TARGETS = tuple((method, target(path)) for method, path in NEW_ROUTES)


# --- the witness over the shipped bytes -----------------------------------


def shipped_digests():
    return {name: hashlib.sha256(canonical_json(json.loads(
        (TEMPLATE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    ).encode("utf-8")).hexdigest() for name in SHIPPED}


@pytest.fixture(autouse=True, scope="module")
def the_shipped_revisions_never_move():
    """Digest both shipped revisions before the first test and after the last,
    calibrated on the way in against the digests ``test_alpha6_dalio_revision``
    already reviewed -- so it cannot report "unchanged" about a made-up number."""
    before = shipped_digests()
    assert before == SHIPPED, (
        "a shipped revision had already moved before this module ran")
    yield
    assert shipped_digests() == before, "this module moved a shipped revision"


# --- the API under test ----------------------------------------------------


def contracts(*, reachable=("claude-code", "codex"),
              known=("claude-code", "codex")):
    """Reviewed descriptors, as the factory hands them to the API. Availability
    is a STATE, so an unreachable provider is described as fully as a
    reachable one."""
    return tuple(
        ProviderContract(
            provider_id=name, display_name=f"Provider {name}", vendor="test",
            version="fake-v1", capabilities=("observe", "review", "dispatch"),
            schema_pairs=[("review", "deep-arguments-v1"),
                          ("dispatch", "deep-arguments-v1")],
            lifecycle=("observe", "prepare", "execute", "verify"),
            availability="available" if name in reachable else "executable_absent",
            available=name in reachable)
        for name in known)


def ids():
    counters = {}

    def mint(kind):
        counters[kind] = counters.get(kind, 0) + 1
        return f"{kind}-studio-{counters[kind]}"

    return mint


#: A workflow no transport test addresses. It exists so those tests run against
#: a project that already holds durable bytes: a "nothing moved" witness over an
#: empty tree reports that about nothing at all.
SEEDED = "workflow-already-published"


def api(tmp_path, *, providers=None, adapters=None, clock=lambda: NOW):
    """One API over a real run store, a real template store, real providers.

    No run is created here: the Studio opens its own, and one left standing
    would be a row every listing test had to remember.
    """
    store = RunStore(tmp_path)
    (Path(tmp_path) / "conductor").mkdir(parents=True, exist_ok=True)
    templates = TemplateStore(tmp_path)
    events = []
    subject = CommandApi(
        store, AdapterRegistry([DeepPlanAdapter()] if adapters is None else adapters),
        session=CommandSession(PORT, TOKEN), budget=PRODUCT_COMMAND_BUDGET,
        clock=clock, ids=ids(), publish_run=events.append,
        providers=contracts() if providers is None else providers,
        templates=templates)
    return subject, store, templates, events


def encode(body):
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def post_headers(body, *, token=TOKEN, origin=ORIGIN, host=HOST, length=None,
                 drop=()):
    encoded = encode(body)
    rows = [
        ("Host", host), ("Origin", origin), ("X-Conduct-CSRF", token),
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(encoded) if length is None else length)),
    ]
    return tuple(row for row in rows if row[0] not in drop)


def publishing(subject, workflow_id, revision):
    """The publish body a window sends after reviewing the stored draft.

    The echo names WHICH draft was reviewed, and it is read out of the workflow
    state -- the same place a real window reads it. Written once here so a
    contract change moves every call site together rather than eleven of them
    separately.
    """
    read = get(subject, f"/command/workflows/{workflow_id}").payload
    draft = read.get("draft")
    return {"revision": revision,
            "reviewed_digest": None if draft is None else draft["digest"]}


def post(subject, path, body, **changes):
    return subject.handle(
        "POST", path, post_headers(body, **changes), encode(body))


def get(subject, path, *, host=HOST):
    return subject.handle("GET", path, (("Host", host),))


def code_of(response):
    return response.payload["error"]["code"]


def seeded(tmp_path, **changes):
    """An API over a project that already holds a revision and a draft.

    Under :data:`SEEDED`, which nothing else addresses, so a transport claim
    asserts "no durable byte moved" against a tree that really has some.
    """
    subject, store, templates, events = api(tmp_path, **changes)
    assert post(subject, f"/command/workflows/{SEEDED}/revisions",
                {"revision": 1, "document": a_document()}).status == 201
    assert post(subject, f"/command/workflows/{SEEDED}/draft",
                INCOMPLETE["a cycle"]).status == 201
    events.clear()
    return subject, store, templates, events


def durable_digest(root):
    """Every durable byte this project holds, as one comparable value.

    The whole ``conductor/`` tree rather than one file: a read that wrote
    somewhere unexpected is what a narrower witness would miss.
    """
    conductor = Path(root) / "conductor"
    if not conductor.is_dir():
        raise AssertionError("there is no durable tree here to witness")
    rows = [(path.relative_to(conductor).as_posix(),
             hashlib.sha256(path.read_bytes()).hexdigest())
            for path in sorted(conductor.rglob("*")) if path.is_file()]
    if not rows:
        raise AssertionError("the durable tree is empty; this witness sees nothing")
    return tuple(rows)


def test_the_durable_witness_this_module_uses_can_see_a_moved_byte(tmp_path):
    """Calibrate the instrument on a known case before trusting its silence.

    A witness is worth its report only if it can be shown to notice a change,
    and one that answers about an empty collection reports about nothing."""
    subject, _store, templates, _events = api(tmp_path)
    with pytest.raises(AssertionError):
        durable_digest(tmp_path / "nowhere")
    with pytest.raises(AssertionError, match="sees nothing"):
        durable_digest(tmp_path)

    assert post(subject, f"/command/workflows/{WORKFLOW}/draft",
                a_document()).status == 201
    before = durable_digest(tmp_path)
    templates.draft_path(WORKFLOW).write_bytes(b"{}")
    assert durable_digest(tmp_path) != before


# --- the workflow road ------------------------------------------------------


def test_a_draft_saved_over_the_route_is_durable_and_answers_the_whole_state(
        tmp_path):
    """201 the first time and 200 for every later save, with the state each time.

    The answer is the WHOLE workflow state rather than an acknowledgement:
    computing the diagnostics a second way is how a screen comes to disagree
    with the route that will refuse it.
    """
    subject, _store, templates, events = api(tmp_path)
    created = post(subject, f"/command/workflows/{WORKFLOW}/draft", a_document())
    assert created.status == 201
    assert created.payload["publishable"] is True
    assert created.payload["diagnostics"] == []
    assert created.payload["next_revision"] == 1
    assert created.payload["draft"]["saved_at"] == NOW

    again = post(subject, f"/command/workflows/{WORKFLOW}/draft", a_document())
    assert again.status == 200 and again.payload == created.payload

    # A FRESH API over the same directory sees the same draft.
    later, _store, _templates, _events = api(tmp_path, clock=lambda: "x")
    assert TemplateStore(tmp_path).load_draft(WORKFLOW).settled() == \
        created.payload["draft"]["document"]
    assert later.handle("GET", "/command/workflows", (("Host", HOST),)
                        ).payload["workflows"] == [{
                            "workflow_id": WORKFLOW, "title": None,
                            "latest_revision": None, "revisions": [],
                            "has_draft": True, "unreadable": False}]
    assert events == []


def test_reading_one_workflow_answers_a_json_object_a_browser_can_read(tmp_path):
    """CURRENTLY RED. A production defect this agent found and did not fix.

    ``http_api.CommandApi._get`` answers this route with
    ``CommandResponse(200, self._workflow_state(workflow_id))`` while
    ``_workflow_state`` ALREADY returns a ``CommandResponse``, so the payload is
    that object rather than the mapping every other route answers with. Nothing
    raises inside ``handle``, so the refusal translation never sees it; the
    server then calls ``canonical_json`` on it and ``do_GET`` dies with a
    ``TypeError``. This is the route the Studio's editing screen reads, so it is
    unreachable as shipped. The fix is to RETURN ``self._workflow_state(...)``,
    which is already a response, as the other four wrappers do.
    """
    subject, _store, templates, _events = api(tmp_path)
    assert post(subject, f"/command/workflows/{WORKFLOW}/draft",
                a_document()).status == 201
    read = get(subject, f"/command/workflows/{WORKFLOW}")

    assert read.payload == studio_routes.read_workflow(templates, WORKFLOW)[1]
    # And it survives the one encoder the server puts every payload through.
    assert json.loads(canonical_json(read.payload))["workflow_id"] == WORKFLOW


def test_an_incomplete_draft_saves_over_the_route_and_refuses_to_publish(tmp_path):
    """Both halves of the draft contract, on the road a browser really takes."""
    subject, _store, templates, events = api(tmp_path)
    saved = post(subject, f"/command/workflows/{WORKFLOW}/draft",
                 INCOMPLETE["a dangling edge"])
    assert saved.status == 201 and saved.payload["publishable"] is False
    assert [row["code"] for row in saved.payload["diagnostics"]] == \
        ["template_refused"]

    before = durable_digest(tmp_path)
    refused = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                   publishing(subject, WORKFLOW, 1))
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid")
    # The refusal carries WHY beside the frozen envelope, and the rows are the
    # ones the save already reported -- one judge, two callers.
    assert refused.payload["diagnostics"] == saved.payload["diagnostics"]
    assert durable_digest(tmp_path) == before
    assert templates.revisions(WORKFLOW) == () and events == []


@pytest.mark.parametrize("reason", sorted(FOREIGN))
def test_a_foreign_draft_is_refused_over_the_route_with_no_diagnostics(
        tmp_path, reason):
    """Foreign is REFUSED and incomplete is EXPLAINED, and the wire says which.

    A foreign document gets the frozen envelope alone: what arrived is not a
    drawing this product could hold, so there is nothing to explain.
    """
    subject, _store, templates, events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    refused = post(subject, f"/command/workflows/{WORKFLOW}/draft",
                   FOREIGN[reason])
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["contract_invalid"], "contract_invalid")
    assert "diagnostics" not in refused.payload
    assert durable_digest(tmp_path) == before
    assert templates.load_draft(WORKFLOW) is None and events == []


def test_a_valid_draft_publishes_revision_one_and_the_draft_is_cleared(tmp_path):
    """The whole road: draw, save, publish, and the draft is spent."""
    subject, _store, templates, events = api(tmp_path)
    assert post(subject, f"/command/workflows/{WORKFLOW}/draft",
                a_document()).status == 201
    published = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                     publishing(subject, WORKFLOW, 1))
    assert published.status == 201
    assert published.payload == templates.load(WORKFLOW, 1).as_dict()
    assert set(published.payload) - set(a_document()) == set(NOT_YET_FIELDS)
    assert templates.load_draft(WORKFLOW) is None
    assert templates.revisions(WORKFLOW) == (1,)
    # No run is involved, so no run changed, so nothing is announced.
    assert events == []
    read = get(subject, f"/command/workflows/{WORKFLOW}/revisions/1")
    assert read.payload == {"workflow_id": WORKFLOW, "revision": 1,
                            "document": published.payload}


def test_the_draft_is_cleared_only_after_the_revision_file_exists(tmp_path):
    """An ORDER, not an end state, because the end state cannot tell them apart.

    A build that discarded the draft first would lose the only copy of a
    person's work when the write then failed, and still finish with "no draft,
    one revision" on a happy path. So both durable acts are observed as they
    happen and what is asserted is what was on disk at each moment.
    """
    subject, _store, templates, _events = api(tmp_path)
    assert post(subject, f"/command/workflows/{WORKFLOW}/draft",
                a_document()).status == 201
    draft_path = templates.draft_path(WORKFLOW)
    revision_path = templates.revision_path(WORKFLOW, 1)
    honest_save, honest_discard = templates.save, templates.discard_draft
    observed = []

    def watched_save(template):
        observed.append(("save", draft_path.exists(), revision_path.exists()))
        return honest_save(template)

    def watched_discard(workflow_id):
        observed.append(
            ("discard", draft_path.exists(), revision_path.exists()))
        return honest_discard(workflow_id)

    templates.save, templates.discard_draft = watched_save, watched_discard
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                publishing(subject, WORKFLOW, 1)).status == 201
    assert observed == [("save", True, False), ("discard", True, True)]


def test_a_publish_that_carried_its_own_document_leaves_the_draft_standing(
        tmp_path):
    """A caller that supplied a document said nothing about anybody's draft."""
    subject, _store, templates, _events = api(tmp_path)
    assert post(subject, f"/command/workflows/{WORKFLOW}/draft",
                INCOMPLETE["a cycle"]).status == 201
    standing = templates.draft_path(WORKFLOW).read_bytes()
    published = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                     {"revision": 1, "document": a_document()})
    assert published.status == 201
    assert templates.draft_path(WORKFLOW).read_bytes() == standing


def test_two_publishes_of_different_documents_at_one_revision_leave_the_first(
        tmp_path):
    """A revision is an identity, so two plans may not wear one. Asserted as
    BYTES: a conflict that rewrote the file and then reported a conflict would
    satisfy every claim about status codes."""
    subject, _store, templates, events = api(tmp_path)
    first = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                 {"revision": 1, "document": a_document()})
    assert first.status == 201
    standing = templates.revision_path(WORKFLOW, 1).read_bytes()

    refused = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                   {"revision": 1,
                    "document": a_document(title="Somebody else's cycle")})
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["record_conflict"], "record_conflict")
    assert templates.revision_path(WORKFLOW, 1).read_bytes() == standing
    assert templates.revisions(WORKFLOW) == (1,)

    # The identical re-publish agrees rather than conflicting, and moves nothing.
    again = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                 {"revision": 1, "document": a_document()})
    assert (again.status, again.payload) == (200, first.payload)
    assert templates.revision_path(WORKFLOW, 1).read_bytes() == standing
    assert events == []


def test_a_revision_number_that_skips_ahead_of_what_exists_is_refused(tmp_path):
    """A publish built on a workflow this client has not read. The number that
    WOULD be next is admitted straight after, so the refusal is about the skip
    rather than about the road."""
    subject, _store, templates, _events = seeded(tmp_path)
    before = durable_digest(tmp_path)
    for asked in (2, 7, 999_999):
        refused = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                       {"revision": asked, "document": a_document()})
        assert (refused.status, code_of(refused)) == (
            ERROR_STATUS["contract_invalid"], "contract_invalid"), asked
    assert durable_digest(tmp_path) == before

    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 1, "document": a_document()}).status == 201
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 3, "document": a_document(title="Third")}
                ).status == ERROR_STATUS["contract_invalid"]
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 2, "document": a_document(title="Second")}
                ).status == 201
    assert templates.revisions(WORKFLOW) == (1, 2)


def test_publishing_can_never_rewrite_a_revision_that_already_stands(tmp_path):
    """No mutation of a published revision, ever, by any road this file reaches.

    Later revisions, draft saves, publish refusals and reads all run against a
    workflow whose revision 1 is watched byte for byte.
    """
    subject, _store, templates, _events = api(tmp_path)
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 1, "document": a_document()}).status == 201
    frozen = templates.revision_path(WORKFLOW, 1).read_bytes()

    post(subject, f"/command/workflows/{WORKFLOW}/draft",
         a_document(title="Still drawing"))
    post(subject, f"/command/workflows/{WORKFLOW}/revisions",
         publishing(subject, WORKFLOW, 2))
    post(subject, f"/command/workflows/{WORKFLOW}/draft",
         INCOMPLETE["a dangling edge"])
    post(subject, f"/command/workflows/{WORKFLOW}/revisions",
         publishing(subject, WORKFLOW, 3))
    post(subject, f"/command/workflows/{WORKFLOW}/revisions",
         {"revision": 1, "document": a_document(title="Rewritten")})
    get(subject, f"/command/workflows/{WORKFLOW}/revisions/1")
    get(subject, "/command/workflows")

    assert templates.revision_path(WORKFLOW, 1).read_bytes() == frozen
    assert templates.revisions(WORKFLOW) == (1, 2)


@pytest.mark.parametrize("workflow_id", ["template-dalio", "dalio-v1", "dalio-v2"])
def test_a_workflow_named_after_a_bundled_document_cannot_shadow_it(
        tmp_path, workflow_id):
    """The wheel's own files are code, and no route makes them reachable.

    A project's store is rooted at its own ``conductor/templates``; the bundled
    documents live inside the installed package. Naming a workflow after one of
    them touches nothing the build ships.
    """
    subject, _store, templates, _events = api(tmp_path)
    shipped = {name: (TEMPLATE_DIR / f"{name}.json").read_bytes()
               for name in SHIPPED}
    offered = get(subject, "/command/workflows").payload["starters"]

    assert post(subject, f"/command/workflows/{workflow_id}/draft",
                a_document(title="A shadow")).status == 201
    assert post(subject, f"/command/workflows/{workflow_id}/revisions",
                publishing(subject, workflow_id, 1)).status == 201

    assert {name: (TEMPLATE_DIR / f"{name}.json").read_bytes()
            for name in SHIPPED} == shipped
    assert shipped_digests() == SHIPPED
    assert get(subject, "/command/workflows").payload["starters"] == offered
    assert load_template("dalio-v1").as_dict() == \
        next(row["document"] for row in offered if row["starter_id"] == "dalio-v1")
    # What was written is this PROJECT's workflow, under the id it was asked for.
    assert templates.load(workflow_id, 1).title == "A shadow"


def test_no_studio_read_moves_one_durable_byte(tmp_path):
    """A GET may not become a write road by another name.

    Every read this surface has, over a project holding a draft, two revisions
    and an unreadable one -- the whole tree digested on both sides.
    """
    subject, _store, templates, events = api(tmp_path)
    post(subject, f"/command/workflows/{WORKFLOW}/draft", a_document())
    post(subject, f"/command/workflows/{WORKFLOW}/revisions", {"revision": 1})
    post(subject, f"/command/workflows/{WORKFLOW}/draft", INCOMPLETE["a cycle"])
    post(subject, "/command/workflows/broken-workflow/revisions",
         {"revision": 1, "document": a_document()})
    # Unreadable in the one way this build already handles: a schema it does not
    # speak. The other shapes are a defect, named in their own test below.
    stale = dict(a_document(), template_id="broken-workflow", revision=1,
                 schema_version=99)
    templates.revision_path("broken-workflow", 1).write_text(
        json.dumps(stale), encoding="utf-8", newline="\n")
    events.clear()

    before = durable_digest(tmp_path)
    for path in ("/command/workflows", "/command/runs",
                 f"/command/workflows/{WORKFLOW}/revisions/1",
                 f"/command/workflows/{WORKFLOW}/revisions/2",
                 "/command/workflows/broken-workflow/revisions/1",
                 "/command/workflows/nobody-drew-this/revisions/1"):
        answer = get(subject, path)
        assert answer.status in {200, ERROR_STATUS["service_refused"]}, path
    assert durable_digest(tmp_path) == before
    assert events == []


@pytest.mark.parametrize("planted,reason", [
    ({"schema_version": 1}, "a document missing every required field"),
    ([], "a stored document that is not a JSON object"),
    ({"template_id": "broken-workflow", "revision": 1},
     "a document truncated after its identity"),
])
def test_one_unreadable_revision_never_hides_the_workflows_beside_it(
        tmp_path, planted, reason):
    """CURRENTLY RED. A production defect this agent found and did not fix.

    ``workflow_draft.workflow_rows``, ``workflow_draft.workflow_state`` and
    ``studio_routes.read_revision`` each guard their read with
    ``except TemplateError``. ``TemplateStore.load`` raises that for an OSError
    and for invalid JSON -- but ``GraphTemplate.from_dict`` raises a PLAIN
    ``ContractError`` for a stored document that is not an object or is missing
    a required field. Those escape the guard, so ``GET /command/workflows``
    answers ``422 contract_invalid`` and the project's WHOLE list of workflows
    disappears because one file is damaged, and the two per-workflow reads blame
    the caller for a request that was perfectly well formed.

    ``workflow_state``'s own docstring is the specification this breaks: "a
    revision you cannot read is a fact and a revision you cannot see is a lie."
    ``studio_routes.run_row`` next door already catches
    ``(StoreError, ContractError)``, so the fix is to widen the three guards to
    ``ContractError`` -- ``TemplateError`` is a subclass, so nothing narrows.
    """
    subject, _store, templates, _events = api(tmp_path)
    assert post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                {"revision": 1, "document": a_document()}).status == 201
    assert post(subject, "/command/workflows/broken-workflow/revisions",
                {"revision": 1, "document": a_document()}).status == 201
    templates.revision_path("broken-workflow", 1).write_text(
        json.dumps(planted), encoding="utf-8", newline="\n")

    listed = get(subject, "/command/workflows")
    assert listed.status == 200, (reason, listed.payload)
    rows = {row["workflow_id"]: row for row in listed.payload["workflows"]}
    assert set(rows) == {WORKFLOW, "broken-workflow"}
    assert rows[WORKFLOW]["unreadable"] is False
    assert rows["broken-workflow"] == {
        "workflow_id": "broken-workflow", "title": None, "latest_revision": 1,
        "revisions": [1], "has_draft": False, "unreadable": True}

    read = get(subject, "/command/workflows/broken-workflow/revisions/1")
    assert (read.status, code_of(read)) == (
        ERROR_STATUS["service_refused"], "service_refused")


def test_a_revision_this_build_does_not_hold_is_refused_without_a_path(tmp_path):
    """A fact about what this build has, said without naming its disk."""
    subject, _store, _templates, _events = api(tmp_path)
    refused = get(subject, f"/command/workflows/{WORKFLOW}/revisions/9")
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["service_refused"], "service_refused")
    assert refused.payload["error"]["detail"] == {
        "template_id": WORKFLOW, "revision": 9}
    rendered = json.dumps(refused.payload)
    assert str(tmp_path) not in rendered and "templates" not in rendered


@pytest.mark.parametrize("spelling", ["01", "0", "1.0", "-1", "+1", "1234567890"])
def test_a_revision_that_is_not_one_counting_number_names_no_route(
        tmp_path, spelling):
    """One number has one spelling, and a route table is not a parser."""
    subject, _store, _templates, _events = api(tmp_path)
    refused = get(subject, f"/command/workflows/{WORKFLOW}/revisions/{spelling}")
    assert (refused.status, code_of(refused)) == (
        ERROR_STATUS["route_not_found"], "route_not_found")


def test_a_tail_that_carries_a_number_it_has_no_use_for_is_no_route(tmp_path):
    """`.../draft/3` is a path this table does not contain, not `.../draft`."""
    subject, _store, _templates, _events = api(tmp_path)
    for path in (f"/command/workflows/{WORKFLOW}/draft/3",
                 f"/command/workflows/{WORKFLOW}/revisions/1/draft",
                 f"/command/workflows/{WORKFLOW}/nonsense",
                 "/command/workflows//revisions/1"):
        refused = post(subject, path, a_document())
        assert code_of(refused) == "route_not_found", path
